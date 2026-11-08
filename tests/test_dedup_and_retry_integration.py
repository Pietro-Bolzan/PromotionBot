"""Deduplication and retry against a real Postgres.

These rules live in SQL (the dedup query) and in the database (the partial
unique index), so they can only be proven against a real database.
"""

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from unittest.mock import MagicMock, patch

import httpx
import pytest
from sqlalchemy import func, select

from app.core.config import settings
from app.models.promotions import Promotion, PromotionStatus
from app.repositories.promotion_repo import PromotionRepository
from app.schemas.promotion_schema import (
    PendingDeliveryResponse,
    PromotionCandidate,
    PromotionProcessingResult,
)
from app.services.promotion_delivery_service import PromotionDeliveryService
from app.services.promotion_service import PromotionService
from app.services.telegram_service import TelegramService

pytestmark = pytest.mark.integration

ASIN = "B0CNOTE001"


def ago(hours: float) -> datetime:
    return datetime.now(UTC) - timedelta(hours=hours)


def add_row(db, make_promotion, **fields) -> Promotion:
    promotion = make_promotion(**fields)
    db.add(promotion)
    db.commit()
    return promotion


def collect(db, *asins: str) -> PromotionProcessingResult:
    amazon = MagicMock()
    amazon.fetch_promotions.return_value = [
        PromotionCandidate(
            asin=asin,
            title="Produto",
            original_price=Decimal("100.00"),
            discounted_price=Decimal("70.00"),
            discount_percentage=Decimal("30.00"),
            product_url=f"https://www.amazon.com.br/dp/{asin}",
            category="Computers",
        )
        for asin in asins
    ]
    return PromotionService(
        amazon, PromotionRepository(db)
    ).collect_pending_promotions()


def rows_for(db, asin: str = ASIN) -> int:
    return db.scalar(select(func.count()).where(Promotion.asin == asin))


@pytest.fixture
def telegram_service():
    return MagicMock()


@pytest.fixture
def delivery(db_session, telegram_service):
    openai_service = MagicMock()
    openai_service.generate_sales_copy.return_value = "Copy"
    return PromotionDeliveryService(
        PromotionRepository(db_session), openai_service, telegram_service
    )


# --- deduplication ---


def test_failed_product_is_not_collected_again_inside_the_window(
    db_session, make_promotion
):
    # Regression: FAILED rows matched neither old check (sent_at is NULL, status
    # is not PENDING), so the product came back as a new row on every cycle.
    add_row(db_session, make_promotion, status=PromotionStatus.FAILED, attempts=3)

    result = collect(db_session, ASIN)

    assert result == PromotionProcessingResult(fetched=1, saved=0, duplicates_skipped=1)
    assert rows_for(db_session) == 1


def test_open_row_blocks_the_product_even_outside_the_window(
    db_session, make_promotion
):
    add_row(
        db_session, make_promotion, status=PromotionStatus.PENDING, created_at=ago(30)
    )

    # Checked on the query itself: otherwise the unique index would hide a
    # broken query by rejecting the insert anyway.
    assert PromotionRepository(db_session).has_open_or_recent(ASIN, cutoff=ago(24))
    assert collect(db_session, ASIN).saved == 0


def test_product_can_return_after_the_window(db_session, make_promotion):
    add_row(
        db_session,
        make_promotion,
        status=PromotionStatus.SENT,
        created_at=ago(30),
        sent_at=ago(26),
    )

    assert collect(db_session, ASIN).saved == 1
    assert rows_for(db_session) == 2


def test_unique_index_settles_a_race_the_check_cannot_see(db_session, make_promotion):
    add_row(db_session, make_promotion, status=PromotionStatus.PENDING)
    repository = PromotionRepository(db_session)

    assert repository.save_unless_duplicate(make_promotion()) is False
    assert rows_for(db_session) == 1  # and the session is still usable


# --- retry ---


def test_failed_delivery_is_retried_until_attempts_run_out(
    db_session, make_promotion, delivery, telegram_service
):
    promotion = add_row(db_session, make_promotion)
    telegram_service.send_promotion.side_effect = ConnectionError("telegram down")

    states = []
    for _ in range(settings.delivery_max_attempts):
        delivery.deliver_pending_to_telegram()
        db_session.refresh(promotion)
        states.append((promotion.status, promotion.attempts))

    assert states == [
        (PromotionStatus.PENDING, 1),
        (PromotionStatus.PENDING, 2),
        (PromotionStatus.FAILED, 3),
    ]
    assert promotion.last_error == "ConnectionError: telegram down"
    assert PromotionRepository(db_session).list_pending() == []


def test_retry_that_succeeds_is_sent_once(
    db_session, make_promotion, delivery, telegram_service
):
    promotion = add_row(db_session, make_promotion)
    telegram_service.send_promotion.side_effect = [
        ConnectionError("telegram down"),
        None,
    ]

    delivery.deliver_pending_to_telegram()
    delivery.deliver_pending_to_telegram()
    db_session.refresh(promotion)

    assert promotion.status == PromotionStatus.SENT
    assert promotion.attempts == 2
    assert telegram_service.send_promotion.call_count == 2


def test_stored_error_from_telegram_has_no_token(
    db_session, make_promotion, delivery, telegram_service, monkeypatch
):
    token = "123456789:AAH-secret_token"
    monkeypatch.setattr(settings, "telegram_bot_token", token)
    url = f"https://api.telegram.org/bot{token}/sendPhoto"
    telegram_service.send_promotion.side_effect = httpx.HTTPStatusError(
        f"Client error '400 Bad Request' for url '{url}'",
        request=httpx.Request("POST", url),
        response=httpx.Response(400),
    )
    promotion = add_row(db_session, make_promotion)

    delivery.deliver_pending_to_telegram()
    db_session.refresh(promotion)

    assert "secret_token" not in promotion.last_error


def test_database_error_does_not_poison_the_rest_of_the_batch(
    db_session, make_promotion, telegram_service
):
    # Item 6 scenario, now permanent: a failed flush used to leave the session
    # unusable, so every promotion after the broken one failed too.
    broken = add_row(db_session, make_promotion, asin="B0BROKEN01", created_at=ago(2))
    healthy = add_row(db_session, make_promotion, asin="B0HEALTHY1", created_at=ago(1))

    def copy_that_breaks_the_first(promotion):
        if promotion.asin == "B0BROKEN01":
            promotion.title = "x" * 600  # String(500): the next commit fails
        return "Copy"

    openai_service = MagicMock()
    openai_service.generate_sales_copy.side_effect = copy_that_breaks_the_first
    delivery = PromotionDeliveryService(
        PromotionRepository(db_session), openai_service, telegram_service
    )

    result = delivery.deliver_pending_to_telegram()
    db_session.refresh(broken)
    db_session.refresh(healthy)

    assert result == PendingDeliveryResponse(processed=2, sent=1, failed=1)
    assert healthy.status == PromotionStatus.SENT
    assert broken.status == PromotionStatus.PENDING  # back in the queue
    assert broken.last_error.startswith("DataError")


def test_telegram_outage_spends_the_attempts_of_only_a_few_promotions(
    db_session, make_promotion, monkeypatch
):
    # Without the circuit breaker, every queued promotion would spend an
    # attempt on each cycle of an outage and end up FAILED for good.
    monkeypatch.setattr(settings, "telegram_bot_token", "123:fake-token")
    monkeypatch.setattr(settings, "telegram_chat_id", "-1000000000")
    for index in range(5):
        add_row(
            db_session,
            make_promotion,
            asin=f"B0OUTAGE0{index}",
            created_at=ago(5 - index),
        )
    openai_service = MagicMock()
    openai_service.generate_sales_copy.return_value = "Copy"
    delivery = PromotionDeliveryService(
        PromotionRepository(db_session),
        openai_service,
        TelegramService(sleep=lambda seconds: None),
    )

    with patch(
        "app.services.telegram_service.httpx.post",
        side_effect=httpx.ConnectError("telegram down"),
    ):
        first = delivery.deliver_pending_to_telegram()
        second = delivery.deliver_pending_to_telegram()

    attempts = sorted(
        db_session.scalars(
            select(Promotion.attempts).where(Promotion.asin.like("B0OUTAGE%"))
        )
    )
    assert first == PendingDeliveryResponse(processed=3, sent=0, failed=3)
    assert second == PendingDeliveryResponse(processed=0, sent=0, failed=0)
    assert attempts == [0, 0, 1, 1, 1]
