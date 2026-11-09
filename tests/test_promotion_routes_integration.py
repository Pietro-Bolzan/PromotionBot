"""HTTP routes end to end, against the test database.

External services are swapped through app.dependency_overrides: the providers
in app.dependencies are what makes that possible without patching internals.
"""

import uuid
from decimal import Decimal
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from app.core.config import settings
from app.dependencies import (
    get_openai_service,
    get_promotion_sources,
    get_telegram_service,
)
from app.main import app
from app.models.promotions import Store
from app.schemas.promotion_schema import PromotionCandidate

pytestmark = pytest.mark.integration

API_KEY = {"X-API-KEY": settings.app_api_key}


@pytest.fixture(autouse=True)
def _reset_overrides():
    yield
    app.dependency_overrides.clear()


@pytest.fixture
def client(test_engine):
    with TestClient(app) as test_client:
        yield test_client


def override(provider, fake):
    app.dependency_overrides[provider] = lambda: fake
    return fake


def test_send_route_delivers_through_the_injected_telegram(committed, client):
    telegram = override(get_telegram_service, MagicMock())
    promotion = committed()

    response = client.post(
        f"/api/promotions/{promotion.id}/send-telegram", headers=API_KEY
    )

    assert response.status_code == 200
    assert response.json()["status"] == "SENT"
    assert telegram.send_promotion.call_args.kwargs["link"].endswith("tag=test-20")


def test_pending_route_returns_the_counts(committed, client):
    override(get_telegram_service, MagicMock())
    committed()

    response = client.post("/api/promotions/send-pending-telegram", headers=API_KEY)

    assert response.json() == {"processed": 1, "sent": 1, "failed": 0}


def test_run_route_collects_from_the_injected_source(committed, client):
    source = MagicMock()
    override(get_promotion_sources, (source,))
    source.fetch_promotions.return_value = [
        PromotionCandidate(
            store=Store.AMAZON,
            external_id="B0INJECT01",
            title="Produto injetado",
            original_price=Decimal("100.00"),
            discounted_price=Decimal("70.00"),
            discount_percentage=Decimal("30.00"),
            product_url="https://www.amazon.com.br/dp/B0INJECT01",
            category="Test",
        )
    ]

    first = client.post("/api/promotions/run", headers=API_KEY).json()
    second = client.post("/api/promotions/run", headers=API_KEY).json()

    assert first["saved"] == 1
    assert second["saved"] == 0
    assert second["duplicates_skipped"] == 1


def test_generate_copy_route_persists_the_injected_copy(committed, client):
    openai_service = override(get_openai_service, MagicMock())
    openai_service.generate_sales_copy.return_value = "Copy injetada"
    promotion = committed(generated_message=None)

    response = client.post(
        f"/api/promotions/{promotion.id}/generate-copy", headers=API_KEY
    )
    listed = client.get("/api/promotions", headers=API_KEY).json()

    assert response.json()["message"] == "Copy injetada"
    assert listed[0]["generated_message"] == "Copy injetada"


def test_list_route_shows_delivery_attempts(committed, client):
    committed(attempts=2, last_error="ConnectionError: telegram down")

    promotion = client.get("/api/promotions", headers=API_KEY).json()[0]

    assert promotion["attempts"] == 2
    assert promotion["last_error"] == "ConnectionError: telegram down"


def test_unknown_promotion_answers_404(client):
    response = client.post(
        f"/api/promotions/{uuid.uuid4()}/send-telegram", headers=API_KEY
    )

    assert response.status_code == 404
