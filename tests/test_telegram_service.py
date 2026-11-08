from unittest.mock import MagicMock, patch

import httpx
import pytest

from app.core.config import settings
from app.core.errors import ConfigurationError
from app.services.telegram_service import (
    CAPTION_MAX_LENGTH,
    TelegramApiError,
    TelegramService,
)

LINK = "https://www.amazon.com.br/dp/B0CNOTE001?tag=test-20"
IMAGE = "https://m.media-amazon.com/images/I/example.jpg"
POST = "app.services.telegram_service.httpx.post"


def telegram_response(status_code: int, **body) -> httpx.Response:
    request = httpx.Request("POST", "https://api.telegram.org/bot***/sendMessage")
    return httpx.Response(status_code, json=body, request=request)


@pytest.fixture(autouse=True)
def telegram_credentials(monkeypatch):
    monkeypatch.setattr(settings, "telegram_bot_token", "123:fake-token")
    monkeypatch.setattr(settings, "telegram_chat_id", "-1000000000")


def ok_response() -> MagicMock:
    response = MagicMock()
    response.json.return_value = {"ok": True}
    return response


def test_photo_caption_keeps_the_link_when_copy_is_long():
    with patch(
        "app.services.telegram_service.httpx.post", return_value=ok_response()
    ) as post:
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
    with patch(
        "app.services.telegram_service.httpx.post", return_value=ok_response()
    ) as post:
        TelegramService().send_promotion(message="Oferta", link=LINK)

    assert post.call_count == 1
    assert post.call_args.kwargs["json"]["text"].endswith(LINK)


def test_photo_refused_by_telegram_falls_back_to_text():
    refused = telegram_response(
        400,
        ok=False,
        description="Bad Request: wrong file identifier/HTTP URL specified",
    )
    with patch(POST, side_effect=[refused, ok_response()]) as post:
        TelegramService().send_promotion(message="Oferta", link=LINK, image_url=IMAGE)

    assert post.call_count == 2
    assert post.call_args.args[0].endswith("/sendMessage")


def test_photo_timeout_does_not_also_post_the_text():
    # Telegram may have posted the photo and only the answer was lost: sending
    # the text as well would publish the promotion twice.
    with (
        patch(POST, side_effect=httpx.ReadTimeout("timed out")) as post,
        pytest.raises(httpx.ReadTimeout),
    ):
        TelegramService().send_promotion(message="Oferta", link=LINK, image_url=IMAGE)

    assert post.call_count == 1


def test_missing_credentials_fail_without_any_request(monkeypatch):
    monkeypatch.setattr(settings, "telegram_bot_token", "")

    with patch(POST) as post, pytest.raises(ConfigurationError, match="not configured"):
        TelegramService().send_promotion(message="Oferta", link=LINK, image_url=IMAGE)

    post.assert_not_called()


def test_refusal_reason_from_telegram_reaches_the_error():
    # Regression: raise_for_status() ran first, so only "400 Bad Request" (with
    # the token in the URL) survived, never Telegram's explanation.
    refused = telegram_response(
        400, ok=False, description="Bad Request: chat not found"
    )

    with (
        patch(POST, return_value=refused),
        pytest.raises(TelegramApiError, match="chat not found"),
    ):
        TelegramService().send_promotion(message="Oferta", link=LINK)


def test_error_page_that_is_not_json_raises_http_status_error():
    request = httpx.Request("POST", "https://api.telegram.org/bot***/sendMessage")
    error_page = httpx.Response(502, text="<html>Bad Gateway</html>", request=request)

    with patch(POST, return_value=error_page), pytest.raises(httpx.HTTPStatusError):
        TelegramService().send_promotion(message="Oferta", link=LINK)
