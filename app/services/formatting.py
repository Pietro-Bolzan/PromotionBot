"""Number formatting for messages read by Brazilian customers.

Done by hand instead of through the locale module, whose output depends on the
locales installed on the host and which changes process-wide state.
"""

from decimal import ROUND_DOWN, ROUND_HALF_UP, Decimal


def format_brl(value: Decimal) -> str:
    """Decimal("4299.9") -> "R$ 4.299,90"."""
    amount = f"{value.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP):,.2f}"
    integer, cents = amount.split(".")
    return f"R$ {integer.replace(',', '.')},{cents}"


def format_discount(percentage: Decimal) -> str:
    """Decimal("23.9") -> "23%".

    Rounded down, so a discount is never advertised as bigger than it is.
    """
    return f"{percentage.quantize(Decimal('1'), rounding=ROUND_DOWN)}%"
