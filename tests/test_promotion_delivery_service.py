from unittest.mock import MagicMock

import pytest

from app.core.config import settings
from app.models.promotions import PromotionStatus
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
    repository.mark_as_failed.assert_not_called()
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
    repository.mark_as_failed.assert_called_once_with(promotion)


def test_rolls_back_the_session_before_marking_as_failed(
    delivery, repository, telegram_service, make_promotion
):
    telegram_service.send_promotion.side_effect = ConnectionError("telegram down")

    with pytest.raises(ConnectionError):
        delivery.deliver_to_telegram(make_promotion())

    calls = [name for name, *_ in repository.mock_calls]
    assert calls.index("rollback") < calls.index("mark_as_failed")


def test_original_error_reaches_the_caller_even_if_marking_fails(
    delivery, repository, telegram_service, make_promotion, caplog
):
    # Regression: marking FAILED used to commit on a broken session, raising
    # PendingRollbackError and hiding the real cause from the caller.
    telegram_service.send_promotion.side_effect = ConnectionError("telegram down")
    repository.mark_as_failed.side_effect = RuntimeError("database down")

    with pytest.raises(ConnectionError, match="telegram down"):
        delivery.deliver_to_telegram(make_promotion())

    assert "Could not mark promotion" in caplog.text


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
