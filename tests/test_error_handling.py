"""Every failure answers with the same body: error_code, message, request_id."""

import logging
from unittest.mock import MagicMock

import httpx
import pytest
from fastapi.testclient import TestClient

from app.core.circuit_breaker import CircuitOpenError
from app.core.config import settings
from app.core.errors import ConfigurationError
from app.dependencies import get_delivery_service
from app.main import app
from app.services.telegram_service import TelegramApiError

API_KEY = {"X-API-KEY": settings.app_api_key}
SEND_PENDING = "/api/promotions/send-pending-telegram"


@pytest.fixture
def client():
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def delivery_failing_with(error: Exception) -> None:
    delivery = MagicMock()
    delivery.deliver_pending_to_telegram.side_effect = error
    app.dependency_overrides[get_delivery_service] = lambda: delivery


def assert_error_body(response, status: int, error_code: str) -> dict:
    body = response.json()
    assert response.status_code == status
    assert body["error_code"] == error_code
    assert body["request_id"] == response.headers["x-request-id"]
    return body


def test_unknown_route(client):
    assert_error_body(client.get("/nope"), 404, "not_found")


def test_invalid_parameter_lists_what_is_wrong(client):
    response = client.get("/api/promotions?limit=0", headers=API_KEY)

    body = assert_error_body(response, 422, "validation_error")
    assert body["details"][0]["loc"] == ["query", "limit"]


def test_missing_configuration_is_a_503_not_a_crash(client):
    # Regression: the missing partner tag used to surface as a bare 500.
    delivery_failing_with(ConfigurationError("AMAZON_PARTNER_TAG is not configured"))

    response = client.post(SEND_PENDING, headers=API_KEY)

    body = assert_error_body(response, 503, "not_configured")
    assert "AMAZON_PARTNER_TAG" in body["message"]


def test_telegram_refusal_is_a_502_with_its_reason(client):
    delivery_failing_with(
        TelegramApiError("sendMessage refused: Bad Request: chat not found")
    )

    body = assert_error_body(
        client.post(SEND_PENDING, headers=API_KEY), 502, "telegram_rejected"
    )
    assert "chat not found" in body["message"]


def test_unreachable_telegram_is_a_502(client):
    delivery_failing_with(httpx.ConnectError("connection refused"))

    assert_error_body(
        client.post(SEND_PENDING, headers=API_KEY), 502, "upstream_unreachable"
    )


def test_paused_channel_is_a_503(client):
    delivery_failing_with(CircuitOpenError("Telegram is unavailable"))

    assert_error_body(
        client.post(SEND_PENDING, headers=API_KEY), 503, "service_unavailable"
    )


def test_unexpected_error_is_a_500_that_leaks_nothing(client, caplog):
    delivery_failing_with(RuntimeError("internal detail: SELECT * FROM secrets"))

    with caplog.at_level(logging.ERROR):
        response = client.post(SEND_PENDING, headers=API_KEY)

    body = assert_error_body(response, 500, "internal_error")
    assert body["message"] == "Internal server error"
    assert "internal detail" not in response.text
    # ...but it is logged, for whoever investigates the request id.
    assert (
        "Unhandled error on POST /api/promotions/send-pending-telegram" in caplog.text
    )


def test_openapi_documents_the_error_body():
    schema = app.openapi()
    responses = schema["paths"]["/api/promotions/send-pending-telegram"]["post"][
        "responses"
    ]

    for status in ("401", "409", "422", "500", "502", "503"):
        reference = responses[status]["content"]["application/json"]["schema"]["$ref"]
        assert reference.endswith("/ErrorResponse"), status
    # FastAPI's default 422 body is no longer what the API returns.
    assert "HTTPValidationError" not in schema["components"]["schemas"]
