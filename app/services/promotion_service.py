from datetime import UTC, datetime, timedelta

from pydantic import HttpUrl

from app.models.promotions import Promotion, PromotionStatus
from app.repositories.promotion_repo import PromotionRepository
from app.schemas.promotion_schema import PromotionProcessingResult
from app.services.amazon_service import AmazonService


class PromotionService:
    def __init__(
        self,
        amazon_service: AmazonService,
        promotion_repository: PromotionRepository,
    ):
        self.amazon_service = amazon_service
        self.promotion_repository = promotion_repository

    def collect_pending_promotions(self) -> PromotionProcessingResult:
        candidates = self.amazon_service.fetch_promotions()
        cutoff = datetime.now(UTC) - timedelta(hours=24)

        saved = 0
        duplicates_skipped = 0

        for candidate in candidates:
            if self.promotion_repository.has_open_or_recent(
                store=candidate.store,
                external_id=candidate.external_id,
                cutoff=cutoff,
            ):
                duplicates_skipped += 1
                continue

            promotion = Promotion(
                store=candidate.store,
                external_id=candidate.external_id,
                title=candidate.title,
                original_price=candidate.original_price,
                discounted_price=candidate.discounted_price,
                discount_percentage=candidate.discount_percentage,
                product_url=str(candidate.product_url),
                affiliate_url=_optional_url(candidate.affiliate_url),
                image_url=_optional_url(candidate.image_url),
                category=candidate.category,
                rating=candidate.rating,
                status=PromotionStatus.PENDING,
            )

            if self.promotion_repository.save_unless_duplicate(promotion):
                saved += 1
            else:
                duplicates_skipped += 1

        return PromotionProcessingResult(
            fetched=len(candidates),
            saved=saved,
            duplicates_skipped=duplicates_skipped,
        )


def _optional_url(url: HttpUrl | None) -> str | None:
    return str(url) if url else None
