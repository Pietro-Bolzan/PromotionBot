import hashlib
import hmac
from decimal import Decimal
from unittest.mock import patch

import httpx
import pytest
from pydantic import ValidationError

from app.core.circuit_breaker import CircuitOpenError
from app.core.config import Settings, settings
from app.core.security import describe_error
from app.models.promotions import Store
from app.sources.aliexpress import (
    GATEWAY,
    RESPONSE_KEY,
    AliExpressApiError,
    AliExpressSource,
    sign,
)

POST = "app.sources.aliexpress.httpx.post"
NOW = 1_762_700_000.123


def product(product_id: int = 1005006123456789, **fields) -> dict:
    item = {
        "product_id": product_id,
        "product_title": "Smartwatch Amazfit Bip 5",
        "target_sale_price": "289.90",
        "target_sale_price_currency": "BRL",
        "target_original_price": "449.90",
        "discount": "35%",
        "product_detail_url": f"https://pt.aliexpress.com/item/{product_id}.html",
        "promotion_link": "https://s.click.aliexpress.com/e/_DmAbCdE",
        "product_main_image_url": "https://ae01.alicdn.com/kf/abc.jpg",
        "first_level_category_name": "Eletrônicos",
    }
    item.update(fields)
    return item


def answer(*products: dict, resp_code: int = 200) -> httpx.Response:
    body = {
        RESPONSE_KEY: {
            "resp_result": {
                "resp_code": resp_code,
                "resp_msg": "Call succeeds",
                "result": {"products": {"product": list(products)}},
            }
        }
    }
    return httpx.Response(200, json=body, request=httpx.Request("POST", GATEWAY))


def refusal(code: str, message: str) -> httpx.Response:
    body = {"error_response": {"type": "ISV", "code": code, "msg": message}}
    return httpx.Response(200, json=body, request=httpx.Request("POST", GATEWAY))


@pytest.fixture(autouse=True)
def aliexpress_settings(monkeypatch):
    monkeypatch.setattr(settings, "aliexpress_app_key", "512345")
    monkeypatch.setattr(settings, "aliexpress_app_secret", "aliexpress-test-secret")
    monkeypatch.setattr(settings, "aliexpress_tracking_id", "promobot")
    monkeypatch.setattr(settings, "aliexpress_keywords", ["smartwatch"])
    monkeypatch.setattr(settings, "aliexpress_items_per_keyword", 10)


@pytest.fixture
def aliexpress():
    return AliExpressSource(clock=lambda: NOW, sleep=lambda seconds: None)


def test_signature_covers_every_parameter_sorted_by_name():
    params = {"method": "m", "app_key": "1", "timestamp": "2", "empty": ""}

    expected = hmac.new(
        b"secret", b"app_key1methodmtimestamp2", hashlib.sha256
    ).hexdigest()

    assert sign(params, "secret") == expected.upper()
    assert sign({**params, "sign": "old"}, "secret") == expected.upper()


def test_request_asks_for_brazilian_prices_and_tracked_links(aliexpress):
    with patch(POST, return_value=answer()) as post:
        aliexpress.fetch_promotions()

    sent = post.call_args.kwargs["data"]
    assert sent["method"] == "aliexpress.affiliate.product.query"
    assert sent["keywords"] == "smartwatch"
    assert (sent["target_currency"], sent["ship_to_country"]) == ("BRL", "BR")
    assert sent["tracking_id"] == "promobot"
    assert sent["timestamp"] == "1762700000123"  # milliseconds
    assert sent["sign"] == sign(sent, "aliexpress-test-secret")


def test_product_becomes_a_candidate_with_its_tracked_link(aliexpress):
    with patch(POST, return_value=answer(product())):
        (candidate,) = aliexpress.fetch_promotions()

    assert candidate.store == Store.ALIEXPRESS
    assert candidate.external_id == "1005006123456789"
    assert candidate.discounted_price == Decimal("289.90")
    assert candidate.original_price == Decimal("449.90")
    assert candidate.discount_percentage == Decimal("35")
    assert str(candidate.affiliate_url) == "https://s.click.aliexpress.com/e/_DmAbCdE"
    assert candidate.category == "Eletrônicos"


@pytest.mark.parametrize(
    "unpostable",
    [
        {"target_sale_price_currency": "USD"},  # not a price a reader pays
        {"promotion_link": None},  # no tracked link, no commission
        {"target_sale_price": "n/a"},
    ],
)
def test_products_that_cannot_be_posted_are_skipped(aliexpress, unpostable):
    with patch(POST, return_value=answer(product(**unpostable))):
        assert aliexpress.fetch_promotions() == []


def test_product_found_by_two_keywords_is_collected_once(aliexpress, monkeypatch):
    monkeypatch.setattr(settings, "aliexpress_keywords", ["smartwatch", "relogio"])

    with patch(POST, return_value=answer(product())):
        assert len(aliexpress.fetch_promotions()) == 1


def test_gateway_refusal_carries_its_code_and_is_not_retried(aliexpress):
    with (
        patch(POST, return_value=refusal("IncompleteSignature", "bad sign")) as post,
        pytest.raises(AliExpressApiError, match="bad sign") as raised,
    ):
        aliexpress.fetch_promotions()

    assert raised.value.code == "IncompleteSignature"
    assert post.call_count == 1


def test_failed_search_is_an_error(aliexpress):
    with (
        patch(POST, return_value=answer(resp_code=500)),
        pytest.raises(AliExpressApiError, match="search failed"),
    ):
        aliexpress.fetch_promotions()


def test_connection_failures_are_retried_then_raised(aliexpress):
    with (
        patch(POST, side_effect=httpx.ConnectError("refused")) as post,
        pytest.raises(httpx.ConnectError),
    ):
        aliexpress.fetch_promotions()

    assert post.call_count == 3


def test_repeated_throttling_pauses_the_source(aliexpress):
    for _ in range(3):
        with (
            patch(POST, return_value=refusal("ApiCallLimit", "too many calls")),
            pytest.raises(AliExpressApiError),
        ):
            aliexpress.fetch_promotions()

    with patch(POST) as post, pytest.raises(CircuitOpenError):
        aliexpress.fetch_promotions()

    post.assert_not_called()


def test_secret_never_reaches_logs_or_stored_errors():
    error = RuntimeError("signing with aliexpress-test-secret failed")

    assert "aliexpress-test-secret" not in describe_error(error)


def test_enabling_aliexpress_requires_its_credentials():
    with pytest.raises(ValidationError, match="ALIEXPRESS_TRACKING_ID"):
        Settings(
            promotion_sources="aliexpress",
            aliexpress_app_key="1",
            aliexpress_app_secret="s",
            aliexpress_keywords="smartwatch",
        )
