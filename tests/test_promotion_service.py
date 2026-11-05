from decimal import Decimal
from unittest.mock import MagicMock

from app.schemas.promotion_schema import PromotionCandidate
from app.services.promotion_service import PromotionService


def candidate(asin: str = "B0CNOTE001") -> PromotionCandidate:
    return PromotionCandidate(
        asin=asin,
        title="Notebook",
        original_price=Decimal("100.00"),
        discounted_price=Decimal("70.00"),
        discount_percentage=Decimal("30.00"),
        product_url=f"https://www.amazon.com.br/dp/{asin}",
        category="Computers",
    )


def test_insert_lost_to_a_concurrent_run_counts_as_duplicate():
    amazon = MagicMock()
    amazon.fetch_promotions.return_value = [candidate()]
    repository = MagicMock()
    repository.has_open_or_recent.return_value = False
    repository.save_unless_duplicate.return_value = False  # the index said no

    result = PromotionService(amazon, repository).collect_pending_promotions()

    assert result == {"fetched": 1, "saved": 0, "duplicates_skipped": 1}
