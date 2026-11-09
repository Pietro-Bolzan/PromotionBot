import logging
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta

from pydantic import HttpUrl

from app.core.config import settings
from app.core.errors import AppError
from app.core.security import describe_error
from app.models.promotions import Promotion, PromotionStatus, Store
from app.repositories.promotion_repo import PromotionRepository
from app.schemas.promotion_schema import (
    CuratedPromotionRequest,
    PromotionCandidate,
    PromotionProcessingResult,
)
from app.services.affiliate import AMAZON_DOMAIN
from app.sources.base import PromotionSource

logger = logging.getLogger(__name__)


class DuplicatePromotionError(AppError):
    """The product is already queued, or was collected or posted recently."""

    status_code = 409
    error_code = "duplicate_promotion"


class PromotionService:
    def __init__(
        self,
        sources: Sequence[PromotionSource],
        promotion_repository: PromotionRepository,
    ):
        self.sources = sources
        self.promotion_repository = promotion_repository

    def collect_pending_promotions(self) -> PromotionProcessingResult:
        cutoff = datetime.now(UTC) - timedelta(hours=settings.dedup_window_hours)
        result = PromotionProcessingResult()

        for source in self.sources:
            try:
                candidates = source.fetch_promotions()
            except Exception as error:
                # One store being down must not stop collection from the others.
                logger.warning(
                    "Source %s failed, collecting from the others: %s",
                    source.name,
                    describe_error(error),
                )
                result.failed_sources.append(source.name)
                continue

            result.fetched += len(candidates)
            for candidate in candidates:
                self._collect(candidate, cutoff, result)

        return result

    def add_curated_amazon(self, request: CuratedPromotionRequest) -> Promotion:
        """Queue an Amazon product picked by hand, under the same dedup rules."""
        asin = request.product
        cutoff = datetime.now(UTC) - timedelta(hours=settings.dedup_window_hours)
        duplicate = DuplicatePromotionError(
            f"Amazon product {asin} is queued, or was collected or posted in "
            f"the last {settings.dedup_window_hours} hours"
        )

        if self.promotion_repository.has_open_or_recent(
            store=Store.AMAZON, external_id=asin, cutoff=cutoff
        ):
            raise duplicate

        promotion = Promotion(
            store=Store.AMAZON,
            external_id=asin,
            title=request.title,
            category=request.category,
            # Canonical: whatever tracking the pasted URL carried is dropped,
            # and the partner tag is added at delivery.
            product_url=f"https://www.{AMAZON_DOMAIN}/dp/{asin}",
            generated_message=request.message,
            status=PromotionStatus.PENDING,
        )
        if not self.promotion_repository.save_unless_duplicate(promotion):
            raise duplicate

        return promotion

    def _collect(
        self,
        candidate: PromotionCandidate,
        cutoff: datetime,
        result: PromotionProcessingResult,
    ) -> None:
        # Applied here rather than in each source, so the rule is the same for
        # every store. A product without a known discount is not a promotion.
        if (
            candidate.discount_percentage is None
            or candidate.discount_percentage < settings.min_discount_percent
        ):
            result.below_min_discount += 1
            return

        if self.promotion_repository.has_open_or_recent(
            store=candidate.store,
            external_id=candidate.external_id,
            cutoff=cutoff,
        ):
            result.duplicates_skipped += 1
            return

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
            result.saved += 1
        else:
            result.duplicates_skipped += 1


def _optional_url(url: HttpUrl | None) -> str | None:
    return str(url) if url else None
