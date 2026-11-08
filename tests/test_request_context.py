import json
import logging
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.config import settings
from app.core.logging_config import JsonFormatter, RequestIdFilter, SecretMaskingFilter
from app.core.request_context import RequestIdMiddleware, request_id_var
from app.scheduler import jobs
from app.schemas.promotion_schema import PromotionProcessingResult


def app_reporting_its_request_id() -> FastAPI:
    test_app = FastAPI()
    test_app.add_middleware(RequestIdMiddleware)

    @test_app.get("/id")
    def current_id():  # sync, so it runs in the threadpool like the real routes
        return {"request_id": request_id_var.get()}

    return test_app


def test_every_response_carries_the_id_its_code_saw():
    client = TestClient(app_reporting_its_request_id())

    response = client.get("/id")

    assert response.headers["x-request-id"] == response.json()["request_id"]


def test_a_valid_incoming_id_is_kept():
    client = TestClient(app_reporting_its_request_id())

    response = client.get("/id", headers={"X-Request-ID": "proxy-abc-123"})

    assert response.json()["request_id"] == "proxy-abc-123"


def test_an_id_that_could_inject_text_into_logs_is_replaced():
    client = TestClient(app_reporting_its_request_id())

    response = client.get("/id", headers={"X-Request-ID": 'x" level="ERROR'})

    assert response.json()["request_id"] != 'x" level="ERROR'
    assert response.headers["x-request-id"] == response.json()["request_id"]


def test_the_id_does_not_leak_out_of_the_request():
    TestClient(app_reporting_its_request_id()).get("/id")

    assert request_id_var.get() is None


def test_scheduler_cycle_gets_its_own_id():
    seen = []

    def collect():
        seen.append(request_id_var.get())
        return PromotionProcessingResult(fetched=0, saved=0, duplicates_skipped=0)

    with (
        patch.object(jobs, "SessionLocal"),
        patch.object(jobs, "PromotionService") as promotion_service,
        patch.object(jobs, "PromotionDeliveryService"),
    ):
        promotion_service.return_value.collect_pending_promotions.side_effect = collect
        jobs.process_promotion_cycle()

    assert seen[0].startswith("cycle-")
    assert request_id_var.get() is None


def test_json_lines_carry_level_logger_message_and_request_id():
    record = logging.LogRecord(
        "app.test", logging.INFO, __file__, 1, "sent %s", ("ok",), None
    )
    token = request_id_var.set("abc123")
    try:
        RequestIdFilter().filter(record)
    finally:
        request_id_var.reset(token)

    entry = json.loads(JsonFormatter().format(record))

    assert entry["level"] == "INFO"
    assert entry["logger"] == "app.test"
    assert entry["message"] == "sent ok"
    assert entry["request_id"] == "abc123"


def test_json_exception_is_masked(monkeypatch):
    token = "123456789:AA" + "x" * 33
    monkeypatch.setattr(settings, "telegram_bot_token", token)
    try:
        raise RuntimeError(f"https://api.telegram.org/bot{token}/sendPhoto")
    except RuntimeError as error:
        record = logging.LogRecord(
            "app.test",
            logging.ERROR,
            __file__,
            1,
            "failed",
            None,
            (type(error), error, error.__traceback__),
        )

    SecretMaskingFilter().filter(record)
    RequestIdFilter().filter(record)
    entry = json.loads(JsonFormatter().format(record))

    assert "RuntimeError" in entry["exception"]
    assert token not in entry["exception"]
    assert entry["request_id"] is None
