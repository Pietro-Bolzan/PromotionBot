import logging

from apscheduler.schedulers.background import BackgroundScheduler

from app.core.config import settings
from app.db.database import SessionLocal
from app.dependencies import (
    get_amazon_service,
    get_openai_service,
    get_telegram_service,
)
from app.repositories.promotion_repo import PromotionRepository
from app.services.promotion_delivery_service import (
    DeliveryInProgressError,
    PromotionDeliveryService,
)
from app.services.promotion_service import PromotionService

logger = logging.getLogger(__name__)

# Explicit time zone: otherwise scheduled times follow the host clock, which
# differs between a developer machine and a server running in UTC.
scheduler = BackgroundScheduler(timezone=settings.scheduler_timezone)


def start_scheduler() -> None:
    if not settings.scheduler_enabled:
        logger.info("Scheduler disabled (SCHEDULER_ENABLED=false)")
        return

    if scheduler.running:
        return

    scheduler.add_job(
        process_promotion_cycle,
        "interval",
        seconds=settings.scheduler_interval_seconds,
        id="process_promotion_cycle",
        replace_existing=True,
        # APScheduler's current defaults, stated so they cannot change
        # silently: never two runs of this job at once, and runs missed while
        # one was busy collapse into a single one.
        max_instances=1,
        coalesce=True,
    )

    scheduler.start()
    logger.info(
        "Scheduler started: every %ss, time zone %s",
        settings.scheduler_interval_seconds,
        settings.scheduler_timezone,
    )


def stop_scheduler() -> None:
    if scheduler.running:
        scheduler.shutdown()


def process_promotion_cycle() -> None:
    logger.info("Starting promotion cycle")

    try:
        with SessionLocal() as db:
            promotion_repository = PromotionRepository(db)

            promotion_service = PromotionService(
                amazon_service=get_amazon_service(),
                promotion_repository=promotion_repository,
            )

            collection_result = promotion_service.collect_pending_promotions()

            logger.info(
                "Promotion collection finished: "
                "fetched=%s saved=%s duplicates_skipped=%s",
                collection_result.fetched,
                collection_result.saved,
                collection_result.duplicates_skipped,
            )

            delivery_service = PromotionDeliveryService(
                promotion_repository=promotion_repository,
                openai_service=get_openai_service(),
                telegram_service=get_telegram_service(),
            )

            try:
                delivery_result = delivery_service.deliver_pending_to_telegram(
                    limit=settings.scheduler_delivery_limit
                )
            except DeliveryInProgressError:
                # A manual delivery or another process is sending right now;
                # the pending promotions stay queued for the next cycle.
                logger.info("Promotion delivery skipped: another one is in progress")
                return

            logger.info(
                "Promotion delivery finished: processed=%s sent=%s failed=%s",
                delivery_result.processed,
                delivery_result.sent,
                delivery_result.failed,
            )

    except Exception:
        # Logged and not re-raised: APScheduler would only log it a second time.
        logger.exception("Promotion cycle failed")
