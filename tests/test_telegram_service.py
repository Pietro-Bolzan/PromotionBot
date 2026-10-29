from unittest.mock import MagicMock, patch

import httpx
import pytest

from app.core.config import settings
from app.services.telegram_service import CAPTION_MAX_LENGTH, TelegramService

LINK = "https://www.amazon.com.br/dp/B0CNOTE001?tag=test-20"
IMAGE = "https://m.media-amazon.com/images/I/example.jpg"


@pytest.fixture(autouse=True)
def telegram_credentials(monkeypatch):
    monkeypatch.setattr(settings, "telegram_bot_token", "123:fake-token")
    monkeypatch.setattr(settings, "telegram_chat_id", "-1000000000")


def ok_response() -> MagicMock:
    response = MagicMock()
    response.json.return_value = {"ok": True}
    return response


def test_photo_caption_keeps_the_link_when_copy_is_long():
    with patch("app.services.telegram_service.httpx.post", return_value=ok_response()) as post:
        TelegramService().send_promotion(message="a" * 3000, link=LINK, image_url=IMAGE)

    caption = post.call_args.kwargs["json"]["caption"]
    assert caption.endswith(LINK)
    assert len(caption.encode("utf-16-le")) // 2 <= CAPTION_MAX_LENGTH


def test_text_fallback_also_carries_the_link():
    with patch(
        "app.services.telegram_service.httpx.post",
        side_effect=[httpx.ConnectError("photo failed"), ok_response()],
    ) as post:
        TelegramService().send_promotion(message="Oferta", link=LINK, image_url=IMAGE)

    assert post.call_count == 2
    assert post.call_args.kwargs["json"]["text"] == f"Oferta\n\n{LINK}"


def test_without_image_sends_text_with_link():
    with patch("app.services.telegram_service.httpx.post", return_value=ok_response()) as post:
        TelegramService().send_promotion(message="Oferta", link=LINK)

    assert post.call_count == 1
    assert post.call_args.kwargs["json"]["text"].endswith(LINK)
