"""Text shown to Brazilian customers: prices, discounts and the price notice.

Done by hand instead of through the locale module, whose output depends on the
locales installed on the host and which changes process-wide state.
"""

from datetime import datetime
from decimal import ROUND_DOWN, ROUND_HALF_UP, Decimal
from zoneinfo import ZoneInfo

from app.models.promotions import Store

# The audience is Brazilian, whatever the server's clock says.
BRAZIL_TIME = ZoneInfo("America/Sao_Paulo")

STORE_NAMES = {
    Store.AMAZON: "Amazon",
    Store.SHOPEE: "Shopee",
    Store.ALIEXPRESS: "AliExpress",
}

PRICE_NOTICE = "Preços e disponibilidade podem mudar."


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


def format_price_details(
    discounted_price: Decimal | None,
    original_price: Decimal | None,
    discount_percentage: Decimal | None,
    checked_at: datetime,
) -> str:
    """The price lines of a message, or "" when there is no price to show.

    Built from the stored numbers, never by the LLM: a price in the message must
    be exactly the one the store reported, together with when it was read,
    because a posted message is never updated afterwards.
    """
    if discounted_price is None:
        return ""

    extras = []
    if original_price is not None and original_price > discounted_price:
        extras.append(f"antes {format_brl(original_price)}")
    if discount_percentage:
        extras.append(f"{format_discount(discount_percentage)} de desconto")

    price = format_brl(discounted_price)
    if extras:
        price = f"{price} ({', '.join(extras)})"

    local = checked_at.astimezone(BRAZIL_TIME)
    checked = f"{local:%d/%m/%Y} às {local:%H:%M} (horário de Brasília)"

    return f"{price}\nPreço verificado em {checked}. {PRICE_NOTICE}"
