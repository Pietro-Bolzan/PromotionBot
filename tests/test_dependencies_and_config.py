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
        {"min_discount_percent": 101},
        {"dedup_window_hours": 0},
        {"promotion_sources": "mock,ebay"},
        {"promotion_sources": "mock,mock"},
    ],
)
def test_nonsensical_settings_stop_the_app_from_starting(invalid):
    with pytest.raises(ValidationError):
        Settings(**invalid)


def test_sources_are_read_as_a_comma_separated_list(monkeypatch):
    monkeypatch.setenv("PROMOTION_SOURCES", " Mock , ")

    assert Settings().promotion_sources == ["mock"]


def test_no_source_is_allowed_for_curation_only():
    assert Settings(promotion_sources="").promotion_sources == []


def test_scheduler_refuses_to_post_mock_products():
    with pytest.raises(ValidationError, match="fictitious products"):
        Settings(scheduler_enabled=True, promotion_sources="mock")

    assert Settings(scheduler_enabled=True, promotion_sources="").scheduler_enabled
