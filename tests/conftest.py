"""Shared test setup.

The environment is set before any application module is imported, because
app.core.config builds Settings at import time. Every external credential is
forced to a fake or empty value: environment variables take precedence over the
developer's .env, so no test can reach the real OpenAI, Telegram or database,
even by accident.
"""

import os
from decimal import Decimal

import pytest

os.environ.update(
    {
        "DATABASE_URL": "postgresql+psycopg://test:test@localhost:5432/test",
        "APP_API_KEY": "test-api-key",
        "AMAZON_PARTNER_TAG": "test-20",
        "OPENAI_API_KEY": "",
        "TELEGRAM_BOT_TOKEN": "",
        "TELEGRAM_CHAT_ID": "",
        "SCHEDULER_ENABLED": "false",
    }
)


@pytest.fixture
def make_promotion():
    """Build an unsaved Promotion; any field can be overridden."""
    from app.models.promotions import Promotion, PromotionStatus

    def _make(**overrides) -> Promotion:
        values = {
            "asin": "B0CNOTE001",
            "title": "Notebook Acer Aspire 5",
            "original_price": Decimal("4299.90"),
            "discounted_price": Decimal("3299.90"),
            "discount_percentage": Decimal("23.26"),
            "product_url": "https://www.amazon.com.br/dp/B0CNOTE001",
            "image_url": None,
            "category": "Computers",
            "status": PromotionStatus.PENDING,
            "generated_message": None,
        }
        values.update(overrides)
        return Promotion(**values)

    return _make
