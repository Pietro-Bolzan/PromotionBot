from datetime import UTC, datetime
from decimal import Decimal

import pytest

from app.services.formatting import format_brl, format_discount, format_price_details

# 17:11 UTC is 14:11 in Brasília.
CHECKED_AT = datetime(2026, 11, 9, 17, 11, tzinfo=UTC)


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (Decimal("4299.90"), "R$ 4.299,90"),
        (Decimal("79.9"), "R$ 79,90"),
        (Decimal("1234567.891"), "R$ 1.234.567,89"),
        (Decimal("0.5"), "R$ 0,50"),
    ],
)
def test_prices_use_the_brazilian_format(value, expected):
    assert format_brl(value) == expected


@pytest.mark.parametrize(
    ("percentage", "expected"),
    [
        (Decimal("23.26"), "23%"),
        (Decimal("23.99"), "23%"),  # never advertised as bigger than it is
        (Decimal("50"), "50%"),
    ],
)
def test_discount_is_a_whole_number_rounded_down(percentage, expected):
    assert format_discount(percentage) == expected


def test_price_details_show_the_price_and_when_it_was_checked():
    details = format_price_details(
        discounted_price=Decimal("3299.90"),
        original_price=Decimal("4299.90"),
        discount_percentage=Decimal("23.26"),
        checked_at=CHECKED_AT,
    )

    assert details == (
        "R$ 3.299,90 (antes R$ 4.299,90, 23% de desconto)\n"
        "Preço verificado em 09/11/2026 às 14:11 (horário de Brasília). "
        "Preços e disponibilidade podem mudar."
    )


def test_price_details_without_an_original_price():
    # Shopee reports the discount, not the price before it.
    details = format_price_details(
        discounted_price=Decimal("49.90"),
        original_price=None,
        discount_percentage=Decimal("35"),
        checked_at=CHECKED_AT,
    )

    assert details.startswith("R$ 49,90 (35% de desconto)\n")


def test_no_price_means_no_price_details():
    # Curated Amazon promotions: the Associates rules forbid prices not read
    # from their API.
    assert (
        format_price_details(
            discounted_price=None,
            original_price=None,
            discount_percentage=None,
            checked_at=CHECKED_AT,
        )
        == ""
    )
