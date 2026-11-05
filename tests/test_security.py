from app.core.config import settings
from app.core.security import mask_secrets


def test_masks_the_configured_telegram_token(monkeypatch):
    monkeypatch.setattr(settings, "telegram_bot_token", "123:configured-token")

    assert "configured-token" not in mask_secrets("token=123:configured-token")


def test_masks_a_telegram_token_by_its_place_in_the_url():
    # Not the configured token (tests run with an empty one): matched by shape.
    url = "https://api.telegram.org/bot999:some-other-token/sendMessage"

    assert mask_secrets(url) == "https://api.telegram.org/bot***/sendMessage"


def test_masks_the_openai_key(monkeypatch):
    monkeypatch.setattr(settings, "openai_api_key", "sk-test-key")

    assert mask_secrets("Incorrect API key provided: sk-test-key") == (
        "Incorrect API key provided: ***"
    )
