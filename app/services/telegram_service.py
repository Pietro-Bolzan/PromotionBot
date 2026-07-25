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
        
    def send_photo(
        self, 
        image_url: str,
        caption: str,
    ) -> None:
        if not settings.telegram_bot_token or not settings.telegram_chat_id:
            raise ValueError("Telegram credentials are not configured")
        
        url = (
            f"https://api.telegram.org/"
            f"bot{settings.telegram_bot_token}/sendPhoto"
        )
        
        response = httpx.post(
            url,
            json={
                "chat_id": settings.telegram_chat_id,
                "photo": image_url,
                "caption": caption[:1024],
            },
            timeout=15,
        )
        
        response.raise_for_status()
        result = response.json()
        
        if not result.get("ok"):
            raise RuntimeError("Telegram rejected the photo")
        
    def send_promotion(
        self,
        message: str,
        image_url: str | None = None
    ) -> None:
        if image_url:
            try:
                self.send_photo(image_url=image_url, caption=message)
                return
            except Exception:
                self.send_message(message)
                return

        self.send_message(message)