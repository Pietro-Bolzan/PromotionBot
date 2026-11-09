"""Shopee Affiliate Open API (GraphQL): products on sale, with tracked links.

The Open API documentation is only visible to approved affiliates. What this
module relies on (endpoint, signature, productOfferV2 fields) was checked
against public client libraries; confirm it with real credentials before
enabling the source in production.
"""

import hashlib
import json
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

ENDPOINT = "https://open-api.affiliate.shopee.com.br/graphql"
REQUEST_TIMEOUT_SECONDS = 15
MAX_ATTEMPTS = 3
BREAKER_FAILURE_THRESHOLD = 3
BREAKER_RESET_SECONDS = 600

# productOfferV2 sortType: 2 = most sold first, so a discount on a product
# people actually buy comes before one on a product nobody does.
SORT_BY_SALES = 2

# Shopee error codes that mean "not now" rather than "never": the request was
# fine and may work later (10030: rate limit exceeded).
RATE_LIMITED = 10030

NODE_FIELDS = (
    "itemId productName priceMin priceMax priceDiscountRate imageUrl "
    "productLink offerLink ratingStar"
)


class ShopeeApiError(PromotionSourceError):
    """Shopee answered and refused the request."""

    def __init__(self, message: str, code: int | None = None) -> None:
        super().__init__(message)
        self.code = code


def _safe_to_retry(error: Exception) -> bool:
    # Searching changes nothing on Shopee's side, so any transport failure,
    # read timeouts included, can be repeated.
    if isinstance(error, httpx.HTTPStatusError):
        return error.response.status_code >= 500
    return isinstance(error, httpx.TransportError)


def _is_service_trouble(error: Exception) -> bool:
    if isinstance(error, ShopeeApiError):
        return error.code == RATE_LIMITED
    return _safe_to_retry(error)


class ShopeeSource:
    name = "shopee"

    def __init__(
        self,
        clock: Callable[[], float] = time.time,
        sleep: Callable[[float], None] = time.sleep,
        breaker: CircuitBreaker | None = None,
    ) -> None:
        self._clock = clock
        self._sleep = sleep
        self._breaker = breaker or CircuitBreaker(
            "Shopee",
            failure_threshold=BREAKER_FAILURE_THRESHOLD,
            reset_timeout=BREAKER_RESET_SECONDS,
        )

    def fetch_promotions(self) -> list[PromotionCandidate]:
        candidates: dict[str, PromotionCandidate] = {}

        for keyword in settings.shopee_keywords:
            for node in self._search(keyword):
                candidate = _to_candidate(node)
                # Popular products show up under several keywords.
                if candidate is not None:
                    candidates.setdefault(candidate.external_id, candidate)

        return list(candidates.values())

    def _search(self, keyword: str) -> list[dict[str, Any]]:
        # Arguments are written into the query: json.dumps produces a valid
        # GraphQL string literal, quotes and accents escaped.
        query = (
            "{productOfferV2("
            f"keyword:{json.dumps(keyword)},"
            f"sortType:{SORT_BY_SALES},"
            "page:1,"
            f"limit:{settings.shopee_items_per_keyword}"
            f"){{nodes{{{NODE_FIELDS}}}}}}}"
        )
        data = self._breaker.call(
            lambda: call_with_retry(
                lambda: self._post(query),
                should_retry=_safe_to_retry,
                attempts=MAX_ATTEMPTS,
                sleep=self._sleep,
                description="Shopee productOfferV2",
            ),
            is_failure=_is_service_trouble,
        )
        return data["productOfferV2"]["nodes"] or []

    def _post(self, query: str) -> dict[str, Any]:
        # The signature covers the exact bytes sent, so the body is serialized
        # once and sent as is.
        body = json.dumps({"query": query}, separators=(",", ":"))
        timestamp = str(int(self._clock()))
        signature = hashlib.sha256(
            f"{settings.shopee_app_id}{timestamp}{body}{settings.shopee_secret}".encode()
        ).hexdigest()

        response = httpx.post(
            ENDPOINT,
            content=body,
            headers={
                "Content-Type": "application/json",
                "Authorization": (
                    f"SHA256 Credential={settings.shopee_app_id}, "
                    f"Timestamp={timestamp}, Signature={signature}"
                ),
            },
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
        response.raise_for_status()

        result = response.json()
        if result.get("errors"):
            error = result["errors"][0]
            extensions = error.get("extensions") or {}
            raise ShopeeApiError(
                f"Shopee refused the request: {error.get('message', 'unknown error')}",
                code=extensions.get("code"),
            )
        return result["data"]


def _to_candidate(node: dict[str, Any]) -> PromotionCandidate | None:
    """Map a productOfferV2 node; None for products that cannot be posted."""
    try:
        price = Decimal(str(node["priceMin"]))
        highest = Decimal(str(node["priceMax"]))
        discount = Decimal(str(node.get("priceDiscountRate") or 0))
    except (KeyError, InvalidOperation):
        logger.debug("Shopee product %s skipped: no usable price", node.get("itemId"))
        return None

    # A range (variations priced differently) has no single price to post,
    # and "from R$ X" would read as the price of what the reader clicks on.
    if highest != price:
        return None

    try:
        return PromotionCandidate(
            store=Store.SHOPEE,
            external_id=str(node["itemId"]),
            title=str(node["productName"])[:500],
            discounted_price=price,
            discount_percentage=discount or None,
            product_url=node["productLink"],
            affiliate_url=node["offerLink"],
            image_url=node.get("imageUrl") or None,
            rating=_rating(node.get("ratingStar")),
        )
    except (KeyError, ValidationError):
        logger.debug("Shopee product %s skipped: incomplete data", node.get("itemId"))
        return None


def _rating(value: Any) -> Decimal | None:
    try:
        rating = Decimal(str(value))
    except InvalidOperation:
        return None
    return rating if 0 < rating <= 5 else None
