import httpx
from app.core.config import settings


class TelegramService:
    def send_message(self, message: str) -> None:
        if not settings.telegram_bot_token or not settings.telegram_chat_id:
            raise ValueError("Telegram credentials are not configured")

        url = (
            f"https://api.telegram.org/"
            f"bot{settings.telegram_bot_token}/sendMessage"
        )

        response = httpx.post(
            url,
            json={
                "chat_id": settings.telegram_chat_id,
                "text": message,
            },
            timeout=15,
        )

        response.raise_for_status()

        result = response.json()

        if not result.get("ok"):
            raise RuntimeError("Telegram rejected the message")