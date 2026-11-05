from sqlalchemy.engine import make_url

from app.core.config import settings


def test_tests_never_see_real_credentials():
    # Guards tests/conftest.py: if this fails, a test could reach real services.
    assert settings.openai_api_key == ""
    assert settings.telegram_bot_token == ""
    assert settings.telegram_chat_id == ""
    assert make_url(settings.database_url).database.endswith("_test")
