from datetime import UTC, datetime, timedelta

from app.models.promotions import Promotion, PromotionStatus
from app.repositories.promotion_repo import PromotionRepository
from app.services.amazon_service import AmazonService


class PromotionService:
    def __init__(
        self,
        amazon_service: AmazonService,
        promotion_repository: PromotionRepository,
    ):
        self.amazon_service = amazon_service
        self.promotion_repository = promotion_repository

    def collect_pending_promotions(self) -> dict:
        candidates = self.amazon_service.fetch_promotions()
        cutoff = datetime.now(UTC) - timedelta(hours=24)

        saved = 0
        duplicates_skipped = 0

        for candidate in candidates:
            already_sent = self.promotion_repository.exists_recently_sent(
                asin=candidate.asin,
                cutoff=cutoff,
            )
            already_pending = self.promotion_repository.exists_recently_pending(
                asin=candidate.asin,
                cutoff=cutoff,
            )

            if already_sent or already_pending:
                duplicates_skipped += 1
                continue

            promotion = Promotion(
                asin=candidate.asin,
                title=candidate.title,
                original_price=candidate.original_price,
                discounted_price=candidate.discounted_price,
                discount_percentage=candidate.discount_percentage,
                product_url=str(candidate.product_url),
                image_url=str(candidate.image_url) if candidate.image_url else None,
                category=candidate.category,
                rating=candidate.rating,
                status=PromotionStatus.PENDING,
            )

            self.promotion_repository.save(promotion)
            saved += 1

        return {
            "fetched": len(candidates),
            "saved": saved,
            "duplicates_skipped": duplicates_skipped,
        }
