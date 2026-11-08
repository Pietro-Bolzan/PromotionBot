import io
import logging

import pytest
from pydantic import ValidationError
from uvicorn.logging import AccessFormatter

from app.core.config import Settings, settings
from app.core.logging_config import SecretMaskingFilter, configure_logging

TOKEN = "123456789:AA" + "x" * 33


@pytest.fixture
def telegram_token(monkeypatch):
    monkeypatch.setattr(settings, "telegram_bot_token", TOKEN)


def capture(formatter: logging.Formatter | None = None):
    """A logger writing to a string through the masking filter."""
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    handler.addFilter(SecretMaskingFilter())
    if formatter:
        handler.setFormatter(formatter)
    logger = logging.getLogger(f"test.masking.{id(stream)}")
    logger.setLevel(logging.DEBUG)  # independent of the root level
    logger.propagate = False
    logger.addHandler(handler)
    return logger, stream


def test_secret_in_message_arguments_is_masked(telegram_token):
    logger, stream = capture()

    logger.warning("POST https://api.telegram.org/bot%s/sendMessage", TOKEN)

    assert TOKEN not in stream.getvalue()


def test_secret_in_traceback_is_masked(telegram_token):
    logger, stream = capture()

    try:
        raise RuntimeError(f"failed: https://api.telegram.org/bot{TOKEN}/sendPhoto")
    except RuntimeError:
        logger.exception("Delivery failed")

    assert "Delivery failed" in stream.getvalue()
    assert TOKEN not in stream.getvalue()


def test_uvicorn_access_log_still_formats():
    # Regression: the filter replaced the record's arguments, and uvicorn's
    # access formatter, which unpacks them, failed on every request.
    logger, stream = capture(
        AccessFormatter('%(client_addr)s - "%(request_line)s" %(status_code)s')
    )

    logger.info(
        '%s - "%s %s HTTP/%s" %d', "127.0.0.1:5000", "GET", "/health", "1.1", 200
    )

    assert stream.getvalue().strip() == '127.0.0.1:5000 - "GET /health HTTP/1.1" 200 OK'


def test_app_logs_follow_the_setting_and_libraries_stay_quiet():
    app_logger = logging.getLogger("app")
    try:
        configure_logging("DEBUG")

        assert app_logger.level == logging.DEBUG
        # httpx logs every request URL at INFO, bot token included.
        assert logging.getLogger("httpx").getEffectiveLevel() >= logging.WARNING
    finally:
        app_logger.setLevel(logging.NOTSET)


def test_configuring_twice_does_not_stack_filters():
    root_handlers = logging.getLogger().handlers
    try:
        configure_logging("INFO")
        configure_logging("INFO")

        for handler in root_handlers:
            masking = [f for f in handler.filters if isinstance(f, SecretMaskingFilter)]
            assert len(masking) <= 1
    finally:
        for handler in root_handlers:
            for masking in [
                f for f in handler.filters if isinstance(f, SecretMaskingFilter)
            ]:
                handler.removeFilter(masking)
        logging.getLogger("app").setLevel(logging.NOTSET)


def test_log_level_is_validated_and_normalized():
    assert Settings(log_level="debug").log_level == "DEBUG"
    with pytest.raises(ValidationError, match="unknown log level"):
        Settings(log_level="verbose")
