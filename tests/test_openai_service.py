import logging
from unittest.mock import MagicMock, patch

import httpx
import openai
import pytest

from app.core.config import settings
from app.services.openai_service import MAX_RETRIES, OpenAIService

RESPONSES_URL = "https://api.openai.com/v1/responses"


def service_with_response(output_text: str = "Copy gerada", status: str = "completed"):
    service = OpenAIService()
    service.client = MagicMock()
    response = service.client.responses.create.return_value
    response.output_text = output_text
    response.status = status
    return service


def service_raising(error: Exception):
    service = OpenAIService()
    service.client = MagicMock()
    service.client.responses.create.side_effect = error
    return service


def connection_error() -> openai.APIConnectionError:
    return openai.APIConnectionError(request=httpx.Request("POST", RESPONSES_URL))


def status_error(cls, status_code: int, message: str):
    request = httpx.Request("POST", RESPONSES_URL)
    return cls(
        message, response=httpx.Response(status_code, request=request), body=None
    )


def test_client_has_a_bounded_timeout_and_uses_sdk_retries(monkeypatch):
    monkeypatch.setattr(settings, "openai_api_key", "sk-test")

    with patch("app.services.openai_service.OpenAI") as client_class:
        OpenAIService()

    kwargs = client_class.call_args.kwargs
    assert kwargs["timeout"] == settings.openai_timeout_seconds
    assert kwargs["max_retries"] == MAX_RETRIES


def test_returns_the_generated_copy(make_promotion):
    assert (
        service_with_response("  Oferta!  ").generate_sales_copy(make_promotion())
        == "Oferta!"
    )


def test_prompt_does_not_give_the_product_url_to_the_llm(make_promotion):
    service = service_with_response()

    service.generate_sales_copy(make_promotion())

    prompt = service.client.responses.create.call_args.kwargs["input"]
    assert "amazon.com.br" not in prompt


def test_fallback_copy_has_no_link(make_promotion):
    service = OpenAIService()
    assert service.client is None  # tests run without an OpenAI key

    assert "http" not in service.generate_sales_copy(make_promotion())


def test_api_outage_falls_back_to_the_template(make_promotion, caplog):
    # Regression: the exception used to escape and mark the promotion FAILED.
    service = service_raising(connection_error())
    promotion = make_promotion()

    with caplog.at_level(logging.WARNING):
        copy = service.generate_sales_copy(promotion)

    assert copy == service._fallback_message(promotion)
    assert "APIConnectionError" in caplog.text


@pytest.mark.parametrize(
    ("output_text", "status"),
    [
        ("", "completed"),  # nothing came back
        ("Oferta imperdível, corre que", "incomplete"),  # cut by max_output_tokens
    ],
)
def test_unusable_response_falls_back_to_the_template(
    output_text, status, make_promotion
):
    service = service_with_response(output_text, status)
    promotion = make_promotion()

    assert service.generate_sales_copy(promotion) == service._fallback_message(
        promotion
    )


def test_wrong_key_is_logged_as_an_error_without_the_key(
    make_promotion, caplog, monkeypatch
):
    key = "sk-proj-real-looking-secret"
    monkeypatch.setattr(settings, "openai_api_key", key)
    service = service_raising(
        status_error(
            openai.AuthenticationError, 401, f"Incorrect API key provided: {key}"
        )
    )

    with caplog.at_level(logging.WARNING):
        service.generate_sales_copy(make_promotion())

    record = caplog.records[-1]
    assert record.levelno == logging.ERROR  # needs a human, not a retry
    assert key not in caplog.text


def test_rate_limit_is_only_a_warning(make_promotion, caplog):
    service = service_raising(
        status_error(openai.RateLimitError, 429, "Rate limit reached")
    )

    with caplog.at_level(logging.WARNING):
        service.generate_sales_copy(make_promotion())

    assert caplog.records[-1].levelno == logging.WARNING


def test_repeated_outages_skip_openai_and_use_the_template(make_promotion):
    # Each failed call already waited up to three timeouts; after three of
    # them the template is used straight away.
    service = service_raising(connection_error())
    promotion = make_promotion()

    for _ in range(3):
        service.generate_sales_copy(promotion)
    service.client.responses.create.reset_mock()

    copy = service.generate_sales_copy(promotion)

    assert copy == service._fallback_message(promotion)
    service.client.responses.create.assert_not_called()


def test_a_wrong_key_does_not_pause_openai(make_promotion):
    # Answered at once, so there is nothing to save by pausing calls.
    service = service_raising(
        status_error(openai.AuthenticationError, 401, "Incorrect API key")
    )

    for _ in range(4):
        service.generate_sales_copy(make_promotion())

    assert service.client.responses.create.call_count == 4
