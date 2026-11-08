"""Logging setup for the running application."""

import logging

from app.core.security import mask_secrets

LOG_FORMAT = "%(asctime)s %(levelname)-8s %(name)s: %(message)s"

# Loggers whose handlers get secret masking: the root one, which writes the
# application's records, and uvicorn's, which print the traceback of any error
# a route does not handle.
_MASKED_LOGGERS = ("", "uvicorn", "uvicorn.access")


def _mask(value: object) -> object:
    """Mask secrets in one message or argument, keeping its type when clean.

    Numbers and clean objects are returned untouched: formatters such as
    uvicorn's access log unpack the arguments and expect, for instance, an int
    status code.
    """
    if value is None or isinstance(value, int | float):
        return value

    text = str(value)
    masked = mask_secrets(text)
    if isinstance(value, str) or masked != text:
        return masked
    return value


class SecretMaskingFilter(logging.Filter):
    """Remove configured secrets from a record before a handler writes it.

    Covers the arguments and the traceback as well as the message: an httpx
    error about a Telegram call, for instance, carries the bot token in its URL.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        record.msg = _mask(record.msg)

        if isinstance(record.args, tuple):
            record.args = tuple(_mask(arg) for arg in record.args)
        elif isinstance(record.args, dict):
            record.args = {key: _mask(arg) for key, arg in record.args.items()}

        if record.exc_info and not record.exc_text:
            record.exc_text = logging.Formatter().formatException(record.exc_info)
        if record.exc_text:
            record.exc_text = mask_secrets(record.exc_text)

        return True


def configure_logging(level: str) -> None:
    """Show the application's own records from `level`, libraries from WARNING.

    Libraries stay at WARNING on purpose: httpx, for one, logs the URL of every
    request at INFO, and Telegram URLs contain the bot token.
    """
    logging.basicConfig(level=logging.WARNING, format=LOG_FORMAT)
    logging.getLogger("app").setLevel(level)

    for name in _MASKED_LOGGERS:
        for handler in logging.getLogger(name).handlers:
            if not any(isinstance(f, SecretMaskingFilter) for f in handler.filters):
                handler.addFilter(SecretMaskingFilter())
