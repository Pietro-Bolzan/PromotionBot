"""AliExpress Affiliate API (Open Platform): products on sale, with tracked links.

Prices are requested in BRL for delivery to Brazil, so they follow the import
tax rules AliExpress applies to Brazilian buyers. The gateway and signature
follow the Open Platform's IOP scheme; confirm them with real credentials
before enabling the source in production.
"""

import hashlib
import hmac
import logging
import time
from collections.abc import Callable
from decimal import Decimal, InvalidOperation
from typing import Any

import httpx
from pydantic import ValidationError

from app.core.circuit_breaker import CircuitBreaker
from app.core.config import settings
from app.core.errors import PromotionSourceError
from app.core.retry import call_with_retry
from app.models.promotions import Store
from app.schemas.promotion_schema import PromotionCandidate

logger = logging.getLogger(__name__)

GATEWAY = "https://api-sg.aliexpress.com/sync"
METHOD = "aliexpress.affiliate.product.query"
RESPONSE_KEY = "aliexpress_affiliate_product_query_response"
REQUEST_TIMEOUT_SECONDS = 15
MAX_ATTEMPTS = 3
BREAKER_FAILURE_THRESHOLD = 3
BREAKER_RESET_SECONDS = 600

# Gateway error codes that mean "not now" rather than "never".
THROTTLED = {"ApiCallLimit", "AppCallLimit", "ServiceUnavailable"}


class AliExpressApiError(PromotionSourceError):
    """AliExpress answered and refused the request."""

    def __init__(self, message: str, code: str | None = None) -> None:
        super().__init__(message)
        self.code = code


def sign(params: dict[str, str], secret: str) -> str:
    """IOP signature: HMAC-SHA256 of every parameter, sorted by name.

    Each parameter contributes its name followed by its value; empty values
    and the signature itself are left out. Upper-case hex.
    """
    payload = "".join(
        f"{name}{value}"
        for name, value in sorted(params.items())
        if name != "sign" and value != ""
    )
    return (
        hmac.new(secret.encode(), payload.encode(), hashlib.sha256).hexdigest().upper()
    )


def _safe_to_retry(error: Exception) -> bool:
    # Searching changes nothing on AliExpress's side, so any transport failure
    # can be repeated.
    if isinstance(error, httpx.HTTPStatusError):
        return error.response.status_code >= 500
    return isinstance(error, httpx.TransportError)


def _is_service_trouble(error: Exception) -> bool:
    if isinstance(error, AliExpressApiError):
        return error.code in THROTTLED
    return _safe_to_retry(error)


class AliExpressSource:
    name = "aliexpress"

    def __init__(
        self,
        clock: Callable[[], float] = time.time,
        sleep: Callable[[float], None] = time.sleep,
        breaker: CircuitBreaker | None = None,
    ) -> None:
        self._clock = clock
        self._sleep = sleep
        self._breaker = breaker or CircuitBreaker(
            "AliExpress",
            failure_threshold=BREAKER_FAILURE_THRESHOLD,
            reset_timeout=BREAKER_RESET_SECONDS,
        )

    def fetch_promotions(self) -> list[PromotionCandidate]:
        candidates: dict[str, PromotionCandidate] = {}

        for keyword in settings.aliexpress_keywords:
            for product in self._search(keyword):
                candidate = _to_candidate(product)
                # Popular products show up under several keywords.
                if candidate is not None:
                    candidates.setdefault(candidate.external_id, candidate)

        return list(candidates.values())

    def _search(self, keyword: str) -> list[dict[str, Any]]:
        params = {
            "method": METHOD,
            "keywords": keyword,
            "sort": "LAST_VOLUME_DESC",  # most sold first
            "page_no": "1",
            "page_size": str(settings.aliexpress_items_per_keyword),
            "target_currency": "BRL",
            "target_language": "PT",
            "ship_to_country": "BR",
            # Without it the products come without promotion_link.
            "tracking_id": settings.aliexpress_tracking_id,
        }
        result = self._breaker.call(
            lambda: call_with_retry(
                lambda: self._post(params),
                should_retry=_safe_to_retry,
                attempts=MAX_ATTEMPTS,
                sleep=self._sleep,
                description=f"AliExpress {METHOD}",
            ),
            is_failure=_is_service_trouble,
        )
        products = (result.get("products") or {}).get("product") or []
        return list(products)

    def _post(self, business_params: dict[str, str]) -> dict[str, Any]:
        # Signed per attempt: the timestamp is part of the signature, and the
        # gateway rejects requests whose timestamp is too old.
        params = {
            **business_params,
            "app_key": settings.aliexpress_app_key,
            "timestamp": str(int(self._clock() * 1000)),
            "sign_method": "sha256",
            "format": "json",
        }
        params["sign"] = sign(params, settings.aliexpress_app_secret)

        response = httpx.post(GATEWAY, data=params, timeout=REQUEST_TIMEOUT_SECONDS)
        response.raise_for_status()
        body = response.json()

        # Gateway refusals (bad key, bad signature, throttling) come with 200.
        if "error_response" in body:
            error = body["error_response"]
            raise AliExpressApiError(
                f"AliExpress refused the request: {error.get('msg', 'unknown error')}",
                code=error.get("code"),
            )

        resp_result = body[RESPONSE_KEY]["resp_result"]
        if resp_result.get("resp_code") != 200:
            raise AliExpressApiError(
                f"AliExpress search failed: {resp_result.get('resp_msg')}",
                code=str(resp_result.get("resp_code")),
            )
        return resp_result.get("result") or {}


def _to_candidate(product: dict[str, Any]) -> PromotionCandidate | None:
    """Map a product; None for products that cannot be posted."""
    if product.get("target_sale_price_currency") != "BRL":
        return None

    try:
        price = Decimal(str(product["target_sale_price"]))
        original = Decimal(str(product["target_original_price"]))
        discount = Decimal(str(product.get("discount") or "0").rstrip("%"))
    except (KeyError, InvalidOperation):
        logger.debug(
            "AliExpress product %s skipped: no usable price", product.get("product_id")
        )
        return None

    try:
        return PromotionCandidate(
            store=Store.ALIEXPRESS,
            external_id=str(product["product_id"]),
            title=str(product["product_title"])[:500],
            original_price=original,
            discounted_price=price,
            discount_percentage=discount or None,
            product_url=product["product_detail_url"],
            affiliate_url=product["promotion_link"],
            image_url=product.get("product_main_image_url") or None,
            category=product.get("first_level_category_name") or None,
        )
    except (KeyError, ValidationError):
        logger.debug(
            "AliExpress product %s skipped: incomplete data",
            product.get("product_id"),
        )
        return None
