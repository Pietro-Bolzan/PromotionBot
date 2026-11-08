from unittest.mock import MagicMock, patch

import httpx
import pytest

from app.core.circuit_breaker import CircuitOpenError
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


def ok_response() -> MagicMock:
    response = MagicMock()
    response.json.return_value = {"ok": True}
    return response


def bad_image() -> httpx.Response:
    return telegram_response(
        400, ok=False, error_code=400, description="Bad Request: wrong file identifier"
    )


@pytest.fixture(autouse=True)
def telegram_credentials(monkeypatch):
    monkeypatch.setattr(settings, "telegram_bot_token", "123:fake-token")
    monkeypatch.setattr(settings, "telegram_chat_id", "-1000000000")


@pytest.fixture
def waits():
    """Seconds the service would have slept, without actually sleeping."""
    return []


@pytest.fixture
def telegram(waits):
    return TelegramService(sleep=waits.append)


# --- message composition and photo fallback ---


def test_photo_caption_keeps_the_link_when_copy_is_long(telegram):
    with patch(POST, return_value=ok_response()) as post:
        telegram.send_promotion(message="a" * 3000, link=LINK, image_url=IMAGE)

    caption = post.call_args.kwargs["json"]["caption"]
    assert caption.endswith(LINK)
    assert len(caption.encode("utf-16-le")) // 2 <= CAPTION_MAX_LENGTH


def test_refused_photo_falls_back_to_text_with_the_link(telegram):
    with patch(POST, side_effect=[bad_image(), ok_response()]) as post:
        telegram.send_promotion(message="Oferta", link=LINK, image_url=IMAGE)

    assert post.call_count == 2
    assert post.call_args.args[0].endswith("/sendMessage")
    assert post.call_args.kwargs["json"]["text"] == f"Oferta\n\n{LINK}"


def test_without_image_sends_text_with_link(telegram):
    with patch(POST, return_value=ok_response()) as post:
        telegram.send_promotion(message="Oferta", link=LINK)

    assert post.call_count == 1
    assert post.call_args.kwargs["json"]["text"].endswith(LINK)


def test_photo_timeout_does_not_also_post_the_text(telegram):
    # Telegram may have posted the photo and only the answer was lost: sending
    # the text as well would publish the promotion twice.
    with (
        patch(POST, side_effect=httpx.ReadTimeout("timed out")) as post,
        pytest.raises(httpx.ReadTimeout),
    ):
        telegram.send_promotion(message="Oferta", link=LINK, image_url=IMAGE)

    assert post.call_count == 1


def test_missing_credentials_fail_without_any_request(telegram, monkeypatch):
    monkeypatch.setattr(settings, "telegram_bot_token", "")

    with (
        patch(POST) as post,
        pytest.raises(ConfigurationError, match="not configured"),
    ):
        telegram.send_promotion(message="Oferta", link=LINK, image_url=IMAGE)

    post.assert_not_called()


def test_refusal_reason_from_telegram_reaches_the_error(telegram):
    # Regression: raise_for_status() ran first, so only "400 Bad Request" (with
    # the token in the URL) survived, never Telegram's explanation.
    refused = telegram_response(
        400, ok=False, error_code=400, description="Bad Request: chat not found"
    )

    with (
        patch(POST, return_value=refused),
        pytest.raises(TelegramApiError, match="chat not found"),
    ):
        telegram.send_promotion(message="Oferta", link=LINK)


# --- retries ---


def test_connection_failure_is_retried_with_growing_waits(telegram, waits):
    failures = [httpx.ConnectError("refused")] * 2

    with patch(POST, side_effect=[*failures, ok_response()]) as post:
        telegram.send_promotion(message="Oferta", link=LINK)

    assert post.call_count == 3
    first, second = waits
    assert 0.25 <= first <= 0.5
    assert 0.5 <= second <= 1.0


def test_telegram_asking_to_wait_is_obeyed(telegram, waits):
    too_many = telegram_response(
        429,
        ok=False,
        error_code=429,
        description="Too Many Requests: retry after 2",
        parameters={"retry_after": 2},
    )

    with patch(POST, side_effect=[too_many, ok_response()]):
        telegram.send_promotion(message="Oferta", link=LINK)

    assert waits == [2.0]


def test_a_wait_too_long_for_one_delivery_is_not_spent(telegram, waits):
    # The promotion stays queued for a later cycle instead.
    too_many = telegram_response(
        429, ok=False, error_code=429, parameters={"retry_after": 60}
    )

    with patch(POST, return_value=too_many), pytest.raises(TelegramApiError):
        telegram.send_promotion(message="Oferta", link=LINK)

    assert waits == []


def test_telegram_internal_error_is_retried(telegram):
    internal = telegram_response(500, ok=False, error_code=500, description="Internal")

    with patch(POST, side_effect=[internal, ok_response()]) as post:
        telegram.send_promotion(message="Oferta", link=LINK)

    assert post.call_count == 2


def test_text_timeout_is_not_retried(telegram):
    with (
        patch(POST, side_effect=httpx.ReadTimeout("timed out")) as post,
        pytest.raises(httpx.ReadTimeout),
    ):
        telegram.send_promotion(message="Oferta", link=LINK)

    assert post.call_count == 1


def test_bad_request_is_not_retried(telegram):
    refused = telegram_response(400, ok=False, error_code=400, description="Bad")

    with patch(POST, return_value=refused) as post, pytest.raises(TelegramApiError):
        telegram.send_promotion(message="Oferta", link=LINK)

    assert post.call_count == 1


def test_retries_stop_after_three_attempts(telegram):
    with (
        patch(POST, side_effect=httpx.ConnectError("refused")) as post,
        pytest.raises(httpx.ConnectError),
    ):
        telegram.send_promotion(message="Oferta", link=LINK)

    assert post.call_count == 3


def test_proxy_error_page_is_retried_then_raised(telegram):
    request = httpx.Request("POST", "https://api.telegram.org/bot***/sendMessage")
    error_page = httpx.Response(502, text="<html>Bad Gateway</html>", request=request)

    with (
        patch(POST, return_value=error_page) as post,
        pytest.raises(httpx.HTTPStatusError),
    ):
        telegram.send_promotion(message="Oferta", link=LINK)

    assert post.call_count == 3


# --- circuit breaker ---


def fail_sends(telegram, times):
    for _ in range(times):
        with (
            patch(POST, side_effect=httpx.ConnectError("refused")),
            pytest.raises(httpx.ConnectError),
        ):
            telegram.send_promotion(message="Oferta", link=LINK)


def test_outage_opens_the_circuit_and_stops_requests(telegram):
    fail_sends(telegram, 3)  # three calls, each already retried three times

    with patch(POST) as post, pytest.raises(CircuitOpenError):
        telegram.send_promotion(message="Oferta", link=LINK)

    post.assert_not_called()


def test_refusals_do_not_open_the_circuit(telegram):
    # A bad image or a wrong chat is Telegram answering, not Telegram down.
    for _ in range(5):
        with patch(POST, return_value=bad_image()), pytest.raises(TelegramApiError):
            telegram.send_promotion(message="Oferta", link=LINK)

    with patch(POST, return_value=ok_response()):
        telegram.send_promotion(message="Oferta", link=LINK)  # still goes through
