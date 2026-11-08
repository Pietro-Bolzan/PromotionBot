"""Logging setup for the running application."""

import json
import logging
from datetime import UTC, datetime

from app.core.request_context import request_id_var
from app.core.security import mask_secrets

TEXT_FORMAT = "%(asctime)s %(levelname)-8s [%(request_id)s] %(name)s: %(message)s"

# Loggers whose handlers get secret masking and the request id: the root one,
# which writes the application's records, and uvicorn's, which print the
# access log and the traceback of any error a route does not handle.
_HANDLED_LOGGERS = ("", "uvicorn", "uvicorn.access")


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


class RequestIdFilter(logging.Filter):
    """Stamp each record with the id of the request (or cycle) producing it."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = request_id_var.get() or "-"
        return True


class JsonFormatter(logging.Formatter):
    """One JSON object per line, ready for a log aggregator."""

    def format(self, record: logging.LogRecord) -> str:
        request_id = getattr(record, "request_id", "-")
        entry = {
            "timestamp": datetime.fromtimestamp(record.created, UTC).isoformat(
                timespec="milliseconds"
            ),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "request_id": None if request_id == "-" else request_id,
        }
        if record.exc_info or record.exc_text:
            entry["exception"] = record.exc_text or self.formatException(
                record.exc_info
            )
        return json.dumps(entry, ensure_ascii=False)


def configure_logging(level: str, log_format: str = "text") -> None:
    """Show the application's own records from `level`, libraries from WARNING.

    Libraries stay at WARNING on purpose: httpx, for one, logs the URL of every
    request at INFO, and Telegram URLs contain the bot token.
    """
    root = logging.getLogger()
    if not root.handlers:  # a host that already configured logging keeps it
        handler = logging.StreamHandler()
        handler.setFormatter(
            JsonFormatter() if log_format == "json" else logging.Formatter(TEXT_FORMAT)
        )
        root.addHandler(handler)
        root.setLevel(logging.WARNING)

    logging.getLogger("app").setLevel(level)

    if log_format == "json":
        # A single stream of JSON lines: uvicorn's records go through the root
        # handler instead of its own plain-text ones.
        for name in ("uvicorn", "uvicorn.access"):
            uvicorn_logger = logging.getLogger(name)
            uvicorn_logger.handlers.clear()
            uvicorn_logger.propagate = True

    for name in _HANDLED_LOGGERS:
        for handler in logging.getLogger(name).handlers:
            for filter_class in (SecretMaskingFilter, RequestIdFilter):
                if not any(isinstance(f, filter_class) for f in handler.filters):
                    handler.addFilter(filter_class())
