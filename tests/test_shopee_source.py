import hashlib
import json
from decimal import Decimal
from unittest.mock import patch

import httpx
import pytest
from pydantic import ValidationError

from app.core.circuit_breaker import CircuitOpenError
from app.core.config import Settings, settings
from app.core.security import describe_error
from app.models.promotions import Store
from app.sources.shopee import ENDPOINT, ShopeeApiError, ShopeeSource

POST = "app.sources.shopee.httpx.post"
NOW = 1_762_700_000


def offer(item_id: int = 22912345678, **fields) -> dict:
    node = {
        "itemId": item_id,
        "productName": "Fone Bluetooth JBL Tune 520BT",
        "priceMin": "199.9",
        "priceMax": "199.9",
        "priceDiscountRate": 35,
        "imageUrl": "https://down-br.img.susercontent.com/file/abc",
        "productLink": f"https://shopee.com.br/product/1/{item_id}",
        "offerLink": "https://s.shopee.com.br/AbC123",
        "ratingStar": "4.8",
    }
    node.update(fields)
    return node


def answer(*nodes: dict) -> httpx.Response:
    request = httpx.Request("POST", ENDPOINT)
    body = {"data": {"productOfferV2": {"nodes": list(nodes)}}}
    return httpx.Response(200, json=body, request=request)


def refusal(code: int, message: str) -> httpx.Response:
    request = httpx.Request("POST", ENDPOINT)
    body = {"errors": [{"message": message, "extensions": {"code": code}}]}
    return httpx.Response(200, json=body, request=request)


@pytest.fixture(autouse=True)
def shopee_settings(monkeypatch):
    monkeypatch.setattr(settings, "shopee_app_id", "18300000001")
    monkeypatch.setattr(settings, "shopee_secret", "shopee-test-secret")
    monkeypatch.setattr(settings, "shopee_keywords", ["fone bluetooth"])
    monkeypatch.setattr(settings, "shopee_items_per_keyword", 10)


@pytest.fixture
def shopee():
    return ShopeeSource(clock=lambda: NOW, sleep=lambda seconds: None)


def test_request_is_signed_over_the_exact_body_sent(shopee):
    with patch(POST, return_value=answer()) as post:
        shopee.fetch_promotions()

    sent_body = post.call_args.kwargs["content"]
    expected = hashlib.sha256(
        f"18300000001{NOW}{sent_body}shopee-test-secret".encode()
    ).hexdigest()
    assert post.call_args.kwargs["headers"]["Authorization"] == (
        f"SHA256 Credential=18300000001, Timestamp={NOW}, Signature={expected}"
    )


def test_query_searches_each_keyword_by_sales(shopee, monkeypatch):
    monkeypatch.setattr(settings, "shopee_keywords", ['fone "jbl"', "smartwatch"])

    with patch(POST, return_value=answer()) as post:
        shopee.fetch_promotions()

    queries = [
        json.loads(call.kwargs["content"])["query"] for call in post.call_args_list
    ]
    assert queries[0] == (
        '{productOfferV2(keyword:"fone \\"jbl\\"",sortType:2,page:1,limit:10)'
        "{nodes{itemId productName priceMin priceMax priceDiscountRate imageUrl "
        "productLink offerLink ratingStar}}}"
    )
    assert 'keyword:"smartwatch"' in queries[1]


def test_offer_becomes_a_candidate_with_its_tracked_link(shopee):
    with patch(POST, return_value=answer(offer())):
        (candidate,) = shopee.fetch_promotions()

    assert candidate.store == Store.SHOPEE
    assert candidate.external_id == "22912345678"
    assert candidate.discounted_price == Decimal("199.9")
    assert candidate.original_price is None  # Shopee reports only the discount
    assert candidate.discount_percentage == Decimal("35")
    assert str(candidate.affiliate_url) == "https://s.shopee.com.br/AbC123"
    assert candidate.rating == Decimal("4.8")


@pytest.mark.parametrize(
    "unpostable",
    [
        {"priceMax": "249.9"},  # variations with different prices: no one price
        {"offerLink": None},  # no tracked link, no commission
        {"priceMin": "grátis"},
    ],
)
def test_offers_that_cannot_be_posted_are_skipped(shopee, unpostable):
    with patch(POST, return_value=answer(offer(**unpostable))):
        assert shopee.fetch_promotions() == []


def test_product_found_by_two_keywords_is_collected_once(shopee, monkeypatch):
    monkeypatch.setattr(settings, "shopee_keywords", ["fone", "fone bluetooth"])

    with patch(POST, return_value=answer(offer())):
        assert len(shopee.fetch_promotions()) == 1


def test_refusal_carries_shopee_code_and_is_not_retried(shopee):
    with (
        patch(POST, return_value=refusal(10020, "Invalid Signature")) as post,
        pytest.raises(ShopeeApiError, match="Invalid Signature") as raised,
    ):
        shopee.fetch_promotions()

    assert raised.value.code == 10020
    assert post.call_count == 1


def test_connection_failures_are_retried_then_raised(shopee):
    with (
        patch(POST, side_effect=httpx.ConnectError("refused")) as post,
        pytest.raises(httpx.ConnectError),
    ):
        shopee.fetch_promotions()

    assert post.call_count == 3


def test_repeated_rate_limits_pause_the_source(shopee):
    for _ in range(3):
        with (
            patch(POST, return_value=refusal(10030, "Rate limit exceeded")),
            pytest.raises(ShopeeApiError),
        ):
            shopee.fetch_promotions()

    with patch(POST) as post, pytest.raises(CircuitOpenError):
        shopee.fetch_promotions()

    post.assert_not_called()


def test_a_wrong_signature_does_not_pause_the_source(shopee):
    # Answered at once: a configuration problem, not Shopee being unwell.
    for _ in range(4):
        with (
            patch(POST, return_value=refusal(10020, "Invalid Signature")),
            pytest.raises(ShopeeApiError),
        ):
            shopee.fetch_promotions()


def test_secret_never_reaches_logs_or_stored_errors():
    error = RuntimeError("signing with shopee-test-secret failed")

    assert "shopee-test-secret" not in describe_error(error)


def test_enabling_shopee_requires_its_credentials():
    with pytest.raises(ValidationError, match="SHOPEE_APP_ID, SHOPEE_SECRET"):
        Settings(promotion_sources="shopee", shopee_keywords="fone")


def test_keywords_are_read_as_a_comma_separated_list():
    configured = Settings(
        promotion_sources="shopee",
        shopee_app_id="1",
        shopee_secret="s",
        shopee_keywords="fone bluetooth, smartwatch ,",
    )

    assert configured.shopee_keywords == ["fone bluetooth", "smartwatch"]
