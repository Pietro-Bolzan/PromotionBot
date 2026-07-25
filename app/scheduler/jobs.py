from apscheduler.schedulers.background import BackgroundScheduler

from app.core.config import settings
from app.db.database import SessionLocal
from app.repositories.promotion_repo import PromotionRepository
from app.services.openai_service import OpenAIService
from app.services.promotion_service import PromotionService
from app.services.promotion_delivery_service import PromotionDeliveryService
from app.services.telegram_service import TelegramService
from app.services.amazon_service import AmazonService
import logging

scheduler = BackgroundScheduler()
logger = logging.getLogger(__name__)

def process_pending_promotions() -> None:
    with SessionLocal() as db:
        promotion_repository = PromotionRepository(db)

        delivery_service = PromotionDeliveryService(
            promotion_repository=promotion_repository,
            openai_service=OpenAIService(),
            telegram_service=TelegramService(),
        )

        delivery_service.deliver_pending_to_telegram(
            limit=settings.scheduler_delivery_limit
        )


def start_scheduler() -> None:
    if not settings.scheduler_enabled:
        return

    if scheduler.running:
        return

    scheduler.add_job(
        process_promotion_cycle,
        "interval",
        seconds=settings.scheduler_interval_seconds,
        id="process_promotion_cycle",
        replace_existing=True,
    )

    scheduler.start()


def stop_scheduler() -> None:
    if scheduler.running:
        scheduler.shutdown()
        
        
def process_promotion_cycle() -> None:
    logger.info("Starting promotion cycle")

    try:
        with SessionLocal() as db:
            promotion_repository = PromotionRepository(db)

            promotion_service = PromotionService(
                amazon_service=AmazonService(),
                promotion_repository=promotion_repository,
            )

            collection_result = promotion_service.collect_pending_promotions()

            logger.info(
                "Promotion collection finished: fetched=%s saved=%s duplicates_skipped=%s",
                collection_result["fetched"],
                collection_result["saved"],
                collection_result["duplicates_skipped"],
            )

            delivery_service = PromotionDeliveryService(
                promotion_repository=promotion_repository,
                openai_service=OpenAIService(),
                telegram_service=TelegramService(),
            )

            delivery_result = delivery_service.deliver_pending_to_telegram(
                limit=settings.scheduler_delivery_limit
            )

            logger.info(
                "Promotion delivery finished: processed=%s sent=%s failed=%s",
                delivery_result["processed"],
                delivery_result["sent"],
                delivery_result["failed"],
            )

    except Exception:
        logger.exception("Promotion cycle failed")
        raise