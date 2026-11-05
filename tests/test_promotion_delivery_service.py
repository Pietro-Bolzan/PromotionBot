import logging
from unittest.mock import MagicMock

import httpx
import openai
import pytest

from app.core.config import settings
from app.models.promotions import PromotionStatus
from app.services.openai_service import OpenAIService
from app.services.promotion_delivery_service import PromotionDeliveryService


@pytest.fixture
def repository():
    repository = MagicMock()
    repository.mark_as_sent.side_effect = lambda promotion: promotion
    return repository


@pytest.fixture
def openai_service():
    service = MagicMock()
    service.generate_sales_copy.return_value = "Copy gerada"
    return service


@pytest.fixture
def telegram_service():
    return MagicMock()


@pytest.fixture
def delivery(repository, openai_service, telegram_service):
    return PromotionDeliveryService(repository, openai_service, telegram_service)


def test_sends_the_tagged_affiliate_link(delivery, telegram_service, repository, make_promotion):
    delivery.deliver_to_telegram(make_promotion())

    sent = telegram_service.send_promotion.call_args.kwargs
    assert sent["link"] == "https://www.amazon.com.br/dp/B0CNOTE001?tag=test-20"
    repository.mark_as_sent.assert_called_once()


def test_reuses_persisted_copy_instead_of_paying_again(
    delivery, openai_service, telegram_service, make_promotion
):
    delivery.deliver_to_telegram(make_promotion(generated_message="Copy existente"))

    openai_service.generate_sales_copy.assert_not_called()
    assert telegram_service.send_promotion.call_args.kwargs["message"] == "Copy existente"


def test_missing_tag_refuses_before_spending_or_failing(
    delivery, repository, openai_service, telegram_service, make_promotion, monkeypatch
):
    monkeypatch.setattr(settings, "amazon_partner_tag", "")
    promotion = make_promotion()

    with pytest.raises(RuntimeError, match="AMAZON_PARTNER_TAG"):
        delivery.deliver_to_telegram(promotion)

    openai_service.generate_sales_copy.assert_not_called()
    telegram_service.send_promotion.assert_not_called()
    repository.record_failure.assert_not_called()
    assert promotion.status == PromotionStatus.PENDING


def test_missing_tag_stops_the_batch_before_reading_pending(
    delivery, repository, monkeypatch
):
    monkeypatch.setattr(settings, "amazon_partner_tag", "")

    with pytest.raises(RuntimeError, match="AMAZON_PARTNER_TAG"):
        delivery.deliver_pending_to_telegram()

    repository.list_pending.assert_not_called()


def test_invalid_product_url_fails_without_calling_openai(
    delivery, repository, openai_service, make_promotion
):
    promotion = make_promotion(product_url="https://example.com/produto")

    with pytest.raises(ValueError):
        delivery.deliver_to_telegram(promotion)

    openai_service.generate_sales_copy.assert_not_called()
    repository.record_failure.assert_called_once()


def test_rolls_back_the_session_before_marking_as_failed(
    delivery, repository, telegram_service, make_promotion
):
    telegram_service.send_promotion.side_effect = ConnectionError("telegram down")

    with pytest.raises(ConnectionError):
        delivery.deliver_to_telegram(make_promotion())

    calls = [name for name, *_ in repository.mock_calls]
    assert calls.index("rollback") < calls.index("record_failure")


def test_original_error_reaches_the_caller_even_if_marking_fails(
    delivery, repository, telegram_service, make_promotion, caplog
):
    # Regression: marking FAILED used to commit on a broken session, raising
    # PendingRollbackError and hiding the real cause from the caller.
    telegram_service.send_promotion.side_effect = ConnectionError("telegram down")
    repository.record_failure.side_effect = RuntimeError("database down")

    with pytest.raises(ConnectionError, match="telegram down"):
        delivery.deliver_to_telegram(make_promotion())

    assert "Could not record the failure" in caplog.text


def test_one_failure_does_not_stop_the_rest_of_the_batch(
    delivery, repository, telegram_service, make_promotion
):
    # Orchestration only. A failed flush poisoning the session for the next
    # promotions can only be reproduced against a real database; that scenario
    # belongs to the integration tests.
    repository.list_pending.return_value = [
        make_promotion(asin="B0CNOTE001"),
        make_promotion(asin="B0CPHONE02"),
    ]
    telegram_service.send_promotion.side_effect = [ConnectionError("down"), None]

    result = delivery.deliver_pending_to_telegram()

    assert result == {"processed": 2, "sent": 1, "failed": 1}


def test_failure_goes_back_to_the_queue_with_the_error(
    delivery, repository, telegram_service, make_promotion
):
    telegram_service.send_promotion.side_effect = ConnectionError("telegram down")

    with pytest.raises(ConnectionError):
        delivery.deliver_to_telegram(make_promotion(attempts=0))

    recorded = repository.record_failure.call_args.kwargs
    assert recorded["attempts"] == 1
    assert recorded["give_up"] is False
    assert recorded["error"] == "ConnectionError: telegram down"


def test_last_allowed_attempt_gives_up(
    delivery, repository, telegram_service, make_promotion
):
    telegram_service.send_promotion.side_effect = ConnectionError("telegram down")

    with pytest.raises(ConnectionError):
        delivery.deliver_to_telegram(make_promotion(attempts=2))   # max is 3

    recorded = repository.record_failure.call_args.kwargs
    assert recorded["attempts"] == 3
    assert recorded["give_up"] is True


def test_stored_error_never_contains_the_bot_token(
    delivery, repository, telegram_service, make_promotion, monkeypatch
):
    token = "123456789:AAH-secret_token"
    monkeypatch.setattr(settings, "telegram_bot_token", token)
    url = f"https://api.telegram.org/bot{token}/sendPhoto"
    telegram_service.send_promotion.side_effect = httpx.HTTPStatusError(
        f"Client error '400 Bad Request' for url '{url}'",
        request=httpx.Request("POST", url),
        response=httpx.Response(400),
    )

    with pytest.raises(httpx.HTTPStatusError):
        delivery.deliver_to_telegram(make_promotion())

    error = repository.record_failure.call_args.kwargs["error"]
    assert "secret_token" not in error
    assert "/bot***/" in error


def test_message_accepted_by_telegram_is_never_requeued(
    delivery, repository, make_promotion
):
    promotion = make_promotion()
    repository.mark_as_sent.side_effect = [RuntimeError("database hiccup"), promotion]

    assert delivery.deliver_to_telegram(promotion) is promotion

    assert repository.mark_as_sent.call_count == 2
    repository.record_failure.assert_not_called()


def test_unrecordable_delivery_raises_without_requeueing(
    delivery, repository, make_promotion, caplog
):
    repository.mark_as_sent.side_effect = RuntimeError("database down")

    with caplog.at_level(logging.CRITICAL):
        with pytest.raises(RuntimeError, match="database down"):
            delivery.deliver_to_telegram(make_promotion())

    repository.record_failure.assert_not_called()
    assert "may be posted again" in caplog.text


def test_openai_outage_still_delivers_the_promotion(
    repository, telegram_service, make_promotion
):
    # Regression: an OpenAI failure used to mark the promotion as failed instead
    # of sending it with the template copy.
    openai_service = OpenAIService()
    openai_service.client = MagicMock()
    openai_service.client.responses.create.side_effect = openai.APIConnectionError(
        request=httpx.Request("POST", "https://api.openai.com/v1/responses")
    )
    delivery = PromotionDeliveryService(repository, openai_service, telegram_service)

    delivery.deliver_to_telegram(make_promotion())

    repository.mark_as_sent.assert_called_once()
    repository.record_failure.assert_not_called()
    assert telegram_service.send_promotion.call_args.kwargs["message"].startswith(
        "Oferta encontrada"
    )
