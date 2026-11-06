import logging
from unittest.mock import patch

import pytest
from pydantic import ValidationError

from app.core.config import Settings, settings
from app.scheduler import jobs
from app.services.promotion_delivery_service import DeliveryInProgressError

EMPTY_COLLECTION = {"fetched": 0, "saved": 0, "duplicates_skipped": 0}


def test_job_never_overlaps_and_uses_the_configured_timezone(monkeypatch):
    monkeypatch.setattr(settings, "scheduler_enabled", True)

    jobs.start_scheduler()
    try:
        job = jobs.scheduler.get_job("process_promotion_cycle")
        assert job.max_instances == 1
        assert job.coalesce is True
        assert str(jobs.scheduler.timezone) == settings.scheduler_timezone
    finally:
        jobs.stop_scheduler()


def test_cycle_leaves_delivery_for_later_when_another_one_is_running(caplog):
    with (
        patch.object(jobs, "SessionLocal"),
        patch.object(jobs, "PromotionService") as promotion_service,
        patch.object(jobs, "PromotionDeliveryService") as delivery_service,
    ):
        collect = promotion_service.return_value.collect_pending_promotions
        collect.return_value = EMPTY_COLLECTION
        deliver = delivery_service.return_value.deliver_pending_to_telegram
        deliver.side_effect = DeliveryInProgressError("busy")

        with caplog.at_level(logging.INFO):
            jobs.process_promotion_cycle()

    assert "another one is in progress" in caplog.text
    assert "Promotion cycle failed" not in caplog.text


def test_cycle_failure_is_logged_and_not_raised(caplog):
    # Regression: the cycle re-raised after logging, so APScheduler logged the
    # same failure a second time.
    with (
        patch.object(jobs, "SessionLocal"),
        patch.object(jobs, "PromotionService") as promotion_service,
    ):
        collect = promotion_service.return_value.collect_pending_promotions
        collect.side_effect = RuntimeError("amazon down")

        jobs.process_promotion_cycle()  # must not raise

    assert "Promotion cycle failed" in caplog.text


def test_unknown_timezone_is_rejected():
    with pytest.raises(ValidationError, match="unknown timezone"):
        Settings(scheduler_timezone="Mars/Olympus")
