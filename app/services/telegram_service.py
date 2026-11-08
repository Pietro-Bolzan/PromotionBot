import time
from collections.abc import Callable

import httpx

from app.core.config import settings
from app.core.errors import ConfigurationError, DeliveryError
from app.core.retry import call_with_retry
from app.services.affiliate import compose_with_link

# Telegram Bot API limits.
CAPTION_MAX_LENGTH = 1024
MESSAGE_MAX_LENGTH = 4096
REQUEST_TIMEOUT_SECONDS = 15

MAX_ATTEMPTS = 3
# Longest wait Telegram may ask for (429 retry_after) that is still worth
# spending inside one delivery; beyond it the promotion waits for a later one.
MAX_RETRY_AFTER_SECONDS = 10


class TelegramApiError(DeliveryError):
    """Telegram answered and refused the request (ok: false)."""

    error_code = "telegram_rejected"

    def __init__(
        self,
        message: str,
        telegram_code: int | None = None,
        retry_after: int | None = None,
    ) -> None:
        super().__init__(message)
        self.telegram_code = telegram_code
        self.retry_after = retry_after


# Failures after which the photo was certainly not posted, so posting the text
# instead cannot publish the promotion twice. A read timeout is not one of
# them: Telegram may have posted the photo and only its answer was lost.
PHOTO_NOT_POSTED = (
    TelegramApiError,
    httpx.HTTPStatusError,
    httpx.ConnectError,
    httpx.ConnectTimeout,
    httpx.PoolTimeout,
)


def _safe_to_retry(error: Exception) -> bool:
    """Whether the failed request certainly posted nothing.

    Only then is repeating it harmless: retrying after a read timeout, for one,
    could publish the same promotion twice.
    """
    if isinstance(error, TelegramApiError):
        if error.telegram_code == 429:
            return (
                error.retry_after is None
                or error.retry_after <= MAX_RETRY_AFTER_SECONDS
            )
        # Telegram itself saying the failure was on its side.
        return error.telegram_code is not None and error.telegram_code >= 500
    if isinstance(error, httpx.HTTPStatusError):
        # A proxy in front of Telegram that could not reach it. Not 504: the
        # request may have arrived and only the answer timed out.
        return error.response.status_code in (502, 503)
    return isinstance(
        error, httpx.ConnectError | httpx.ConnectTimeout | httpx.PoolTimeout
    )


def _requested_wait(error: Exception) -> float | None:
    if isinstance(error, TelegramApiError) and error.retry_after is not None:
        return float(error.retry_after)
    return None


class TelegramService:
    def __init__(self, sleep: Callable[[float], None] = time.sleep) -> None:
        self._sleep = sleep

    def send_message(self, message: str) -> None:
        self._call("sendMessage", {"text": message})

    def send_photo(self, image_url: str, caption: str) -> None:
        self._call("sendPhoto", {"photo": image_url, "caption": caption})

    def send_promotion(
        self,
        message: str,
        link: str,
        image_url: str | None = None,
    ) -> None:
        if image_url:
            try:
                self.send_photo(
                    image_url=image_url,
                    caption=compose_with_link(message, link, CAPTION_MAX_LENGTH),
                )
                return
            except PHOTO_NOT_POSTED:
                pass  # usually a bad image URL: the text below still carries the link

        self.send_message(compose_with_link(message, link, MESSAGE_MAX_LENGTH))

    def _call(self, method: str, payload: dict) -> None:
        if not settings.telegram_bot_token or not settings.telegram_chat_id:
            raise ConfigurationError("Telegram credentials are not configured")

        call_with_retry(
            lambda: self._post(method, payload),
            should_retry=_safe_to_retry,
            delay_hint=_requested_wait,
            attempts=MAX_ATTEMPTS,
            sleep=self._sleep,
            description=f"Telegram {method}",
        )

    def _post(self, method: str, payload: dict) -> None:
        response = httpx.post(
            f"https://api.telegram.org/bot{settings.telegram_bot_token}/{method}",
            json={"chat_id": settings.telegram_chat_id, **payload},
            timeout=REQUEST_TIMEOUT_SECONDS,
        )

        try:
            result = response.json()
        except ValueError:
            # Not Telegram's JSON (a proxy error page, for instance).
            response.raise_for_status()
            raise

        if not result.get("ok"):
            # Read before the HTTP status on purpose: Telegram explains its
            # refusals, and that explanation is what ends up in last_error.
            reason = result.get("description", response.status_code)
            raise TelegramApiError(
                f"{method} refused: {reason}",
                telegram_code=result.get("error_code"),
                retry_after=(result.get("parameters") or {}).get("retry_after"),
            )
