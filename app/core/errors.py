"""Expected failures, each carrying how the API answers it.

Every subclass sets an HTTP status and a stable `error_code` that clients can
branch on; the message is the human-readable part of the response.
"""


class AppError(Exception):
    status_code: int = 500
    error_code: str = "internal_error"


class ConfigurationError(AppError):
    """A setting the operation needs is missing (an API key, the partner tag)."""

    status_code = 503
    error_code = "not_configured"


class DeliveryError(AppError):
    """A promotion could not be delivered to a messaging channel."""

    status_code = 502
    error_code = "delivery_failed"
