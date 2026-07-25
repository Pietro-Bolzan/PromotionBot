from app.models.promotions import Promotion
from app.repositories.promotion_repo import PromotionRepository
from app.services.openai_service import OpenAIService
from app.services.telegram_service import TelegramService


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
        try:
            message = promotion.generated_message

            if not message:
                message = self.openai_service.generate_sales_copy(promotion)

                self.promotion_repository.update_generated_message(
                    promotion=promotion,
                    generated_message=message,
                )

            self.telegram_service.send_promotion(
                message=message,
                image_url=promotion.image_url,
            )
            return self.promotion_repository.mark_as_sent(promotion)

        except Exception:
            self.promotion_repository.mark_as_failed(promotion)
            raise
        
    def deliver_pending_to_telegram(self, limit: int = 10) -> dict:
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