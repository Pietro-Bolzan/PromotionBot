import httpx

from app.core.config import settings
from app.services.affiliate import compose_with_link

# Telegram Bot API limits.
CAPTION_MAX_LENGTH = 1024
MESSAGE_MAX_LENGTH = 4096
REQUEST_TIMEOUT_SECONDS = 15


class TelegramApiError(RuntimeError):
    """Telegram answered and refused the request (ok: false)."""


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


class TelegramService:
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
            raise ValueError("Telegram credentials are not configured")

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
            raise TelegramApiError(f"{method} refused: {reason}")
