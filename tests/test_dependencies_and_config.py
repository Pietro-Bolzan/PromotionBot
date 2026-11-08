import pytest
from pydantic import ValidationError

from app.core.config import Settings
from app.dependencies import get_openai_service, get_telegram_service


def test_external_clients_are_built_once_per_process():
    # The OpenAI client holds a connection pool: one per request wasted it.
    assert get_openai_service() is get_openai_service()
    assert get_telegram_service() is get_telegram_service()


@pytest.mark.parametrize(
    "invalid",
    [
        {"scheduler_interval_seconds": 0},
        {"scheduler_delivery_limit": 0},
        {"openai_max_output_tokens": 0},
        {"amazon_min_discount_percent": 101},
    ],
)
def test_nonsensical_settings_stop_the_app_from_starting(invalid):
    with pytest.raises(ValidationError):
        Settings(**invalid)
