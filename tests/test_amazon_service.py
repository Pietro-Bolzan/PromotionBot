from decimal import Decimal

import pytest

from app.core.config import settings
from app.services.amazon_service import AmazonService

# The mock source offers three products: 23.26%, 23.08% and 11.12% off.


@pytest.mark.parametrize(
    ("minimum", "expected"),
    [
        (Decimal("20"), {"B0CNOTE001", "B0CPHONE02"}),
        (Decimal("23.26"), {"B0CNOTE001"}),  # exactly the minimum still qualifies
        (Decimal("30"), set()),
        (Decimal("0"), {"B0CNOTE001", "B0CPHONE02", "B0LOWDISC04"}),
    ],
)
def test_only_products_at_or_above_the_minimum_discount_are_collected(
    monkeypatch, minimum, expected
):
    monkeypatch.setattr(settings, "amazon_min_discount_percent", minimum)

    collected = {
        candidate.external_id for candidate in AmazonService().fetch_promotions()
    }

    assert collected == expected
