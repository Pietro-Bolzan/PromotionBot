from decimal import Decimal
from unittest.mock import MagicMock

import pytest

from app.services.formatting import format_brl, format_discount
from app.services.openai_service import OpenAIService


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


def test_template_shows_prices_in_brazilian_format(make_promotion):
    # Regression: every message sent so far read "De R$ 4299.90 por R$ 3299.90".
    message = OpenAIService()._fallback_message(make_promotion())

    assert "De R$ 4.299,90 por R$ 3.299,90" in message
    assert "Desconto de 23%" in message


def test_llm_receives_prices_in_brazilian_format(make_promotion):
    service = OpenAIService()
    service.client = MagicMock()
    service.client.responses.create.return_value.status = "completed"
    service.client.responses.create.return_value.output_text = "Copy"

    service.generate_sales_copy(make_promotion())

    prompt = service.client.responses.create.call_args.kwargs["input"]
    assert "R$ 4.299,90" in prompt
    assert "R$ 3.299,90" in prompt
