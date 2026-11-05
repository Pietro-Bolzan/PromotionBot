import logging
from contextlib import suppress

from sqlalchemy import inspect

from app.core.config import settings
from app.models.promotions import Promotion
from app.repositories.promotion_repo import PromotionRepository
from app.services.affiliate import build_affiliate_url
from app.services.openai_service import OpenAIService
from app.services.telegram_service import TelegramService

logger = logging.getLogger(__name__)


class PromotionDeliveryService:
    def __init__(
        self,
        promotion_repository: PromotionRepository,
        openai_service: OpenAIService,
        telegram_service: TelegramService,
    ):
        self.promotion_repository = promotion_repository
        self.openai_service = openai_service
        self.telegram_service = telegram_service

    def deliver_to_telegram(self, promotion: Promotion) -> Promotion:
        self._require_partner_tag()

        try:
            # Built before the copy so an invalid product URL fails without
            # spending an OpenAI call.
            affiliate_url = build_affiliate_url(
                promotion.product_url,
                settings.amazon_partner_tag,
            )
            message = promotion.generated_message

            if not message:
                message = self.openai_service.generate_sales_copy(promotion)

                self.promotion_repository.update_generated_message(
                    promotion=promotion,
                    generated_message=message,
                )

            self.telegram_service.send_promotion(
                message=message,
                link=affiliate_url,
                image_url=promotion.image_url,
            )
            return self.promotion_repository.mark_as_sent(promotion)

        except Exception:
            self._mark_as_failed(promotion)
            raise

    def deliver_pending_to_telegram(self, limit: int = 10) -> dict:
        self._require_partner_tag()

        promotions = self.promotion_repository.list_pending(limit=limit)

        sent = 0
        failed = 0

        for promotion in promotions:
            try:
                self.deliver_to_telegram(promotion)
                sent += 1
            except Exception:
                failed += 1

        return {
            "processed": len(promotions),
            "sent": sent,
            "failed": failed,
        }

    def _mark_as_failed(self, promotion: Promotion) -> None:
        # The original error may have come from the database, leaving the
        # session unusable until it is rolled back: without the rollback, the
        # commit below would raise PendingRollbackError, hide the real cause,
        # and poison every promotion processed after this one in the batch.
        # If marking still fails, it is only logged, so the caller always
        # receives the original exception.
        try:
            self.promotion_repository.rollback()
            self.promotion_repository.mark_as_failed(promotion)
        except Exception:
            # inspect().identity reads the primary key kept in memory: unlike
            # promotion.id it never queries a database that may be failing.
            logger.exception(
                "Could not mark promotion %s as FAILED",
                inspect(promotion).identity,
            )
            with suppress(Exception):
                self.promotion_repository.rollback()

    @staticmethod
    def _require_partner_tag() -> None:
        # A missing tag is a configuration error, not a problem with any
        # promotion: it is checked before touching one, so it neither spends an
        # OpenAI call nor marks anything as FAILED.
        if not settings.amazon_partner_tag.strip():
            raise RuntimeError(
                "AMAZON_PARTNER_TAG is not configured; refusing to send links "
                "that earn no commission"
            )
