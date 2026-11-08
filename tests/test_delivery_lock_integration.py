"""Concurrent deliveries against a real Postgres.

These tests need several connections to see the same rows, so they commit for
real instead of rolling back, and delete everything they created at the end.
"""

import threading
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from app.core.config import settings
from app.db.database import SessionLocal
from app.main import app
from app.models.promotions import PromotionStatus
from app.repositories.promotion_repo import PromotionRepository
from app.schemas.promotion_schema import PendingDeliveryResponse
from app.services.promotion_delivery_service import (
    DeliveryInProgressError,
    PromotionDeliveryService,
)

pytestmark = pytest.mark.integration

API_KEY = {"X-API-KEY": settings.app_api_key}


def delivery_with(db, telegram_service) -> PromotionDeliveryService:
    return PromotionDeliveryService(
        PromotionRepository(db), MagicMock(), telegram_service
    )


def test_concurrent_deliveries_post_the_promotion_once(committed):
    # Regression: the scheduler and a manual route delivering at the same time
    # both read the same PENDING row and posted it twice.
    committed()
    inside_send, release_send = threading.Event(), threading.Event()
    posted = []

    def slow_send(**kwargs):
        posted.append(kwargs["link"])
        if len(posted) == 1:  # the first delivery stays in the middle of sending
            inside_send.set()
            release_send.wait(timeout=10)

    telegram = MagicMock()
    telegram.send_promotion.side_effect = slow_send
    outcome = {}

    def scheduled_delivery():
        with SessionLocal() as db:
            service = delivery_with(db, telegram)
            outcome["scheduler"] = service.deliver_pending_to_telegram()

    worker = threading.Thread(target=scheduled_delivery)
    worker.start()
    assert inside_send.wait(timeout=10)

    with SessionLocal() as db, pytest.raises(DeliveryInProgressError):
        delivery_with(db, telegram).deliver_pending_to_telegram()

    release_send.set()
    worker.join(timeout=10)

    assert len(posted) == 1
    assert outcome["scheduler"] == PendingDeliveryResponse(
        processed=1, sent=1, failed=0
    )


def test_lock_is_free_again_after_a_delivery(committed):
    committed()
    telegram = MagicMock()

    with SessionLocal() as db:
        delivery_with(db, telegram).deliver_pending_to_telegram()
    with SessionLocal() as db:
        delivery_with(db, telegram).deliver_pending_to_telegram()  # must not raise


def test_manual_route_answers_409_while_a_delivery_runs(committed):
    with (
        SessionLocal() as db,
        PromotionRepository(db).delivery_lock() as acquired,
        TestClient(app) as client,
    ):
        assert acquired
        response = client.post("/api/promotions/send-pending-telegram", headers=API_KEY)

    assert response.status_code == 409


def test_sent_promotion_is_not_sent_again_by_the_route(committed):
    promotion = committed(status=PromotionStatus.SENT)

    with TestClient(app) as client:
        response = client.post(
            f"/api/promotions/{promotion.id}/send-telegram", headers=API_KEY
        )

    assert response.status_code == 409
    assert response.json() == {"detail": "Promotion was already sent"}
