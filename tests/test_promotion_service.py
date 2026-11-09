from decimal import Decimal
from unittest.mock import MagicMock

import httpx
import pytest

from app.core.config import settings
from app.models.promotions import Store
from app.schemas.promotion_schema import (
    PromotionCandidate,
    PromotionProcessingResult,
)
from app.services.promotion_service import PromotionService


def candidate(
    external_id: str = "B0CNOTE001", discount: Decimal | None = Decimal("30.00")
) -> PromotionCandidate:
    return PromotionCandidate(
        store=Store.AMAZON,
        external_id=external_id,
        title="Notebook",
        original_price=Decimal("100.00"),
        discounted_price=Decimal("70.00"),
        discount_percentage=discount,
        product_url=f"https://www.amazon.com.br/dp/{external_id}",
        category="Computers",
    )


def source(name: str, *candidates: PromotionCandidate) -> MagicMock:
    fake = MagicMock()
    fake.name = name
    fake.fetch_promotions.return_value = list(candidates)
    return fake


@pytest.fixture
def repository():
    repository = MagicMock()
    repository.has_open_or_recent.return_value = False
    repository.save_unless_duplicate.return_value = True
    return repository


def test_insert_lost_to_a_concurrent_run_counts_as_duplicate(repository):
    repository.save_unless_duplicate.return_value = False  # the index said no

    result = PromotionService(
        [source("mock", candidate())], repository
    ).collect_pending_promotions()

    assert result == PromotionProcessingResult(fetched=1, saved=0, duplicates_skipped=1)


@pytest.mark.parametrize(
    ("minimum", "discount", "saved"),
    [
        (Decimal("20"), Decimal("23.26"), 1),
        (Decimal("23.26"), Decimal("23.26"), 1),  # exactly the minimum qualifies
        (Decimal("30"), Decimal("23.26"), 0),
        (Decimal("0"), None, 0),  # without a known discount it is not a promotion
    ],
)
def test_minimum_discount_applies_to_every_source(
    repository, monkeypatch, minimum, discount, saved
):
    monkeypatch.setattr(settings, "min_discount_percent", minimum)

    result = PromotionService(
        [source("mock", candidate(discount=discount))], repository
    ).collect_pending_promotions()

    assert result.saved == saved
    assert result.below_min_discount == 1 - saved


def test_a_failing_source_does_not_stop_the_others(repository, caplog):
    broken = source("broken")
    broken.fetch_promotions.side_effect = httpx.ConnectError("store down")
    healthy = source("healthy", candidate())

    result = PromotionService(
        [broken, healthy], repository
    ).collect_pending_promotions()

    assert result.saved == 1
    assert result.failed_sources == ["broken"]
    assert "Source broken failed" in caplog.text
