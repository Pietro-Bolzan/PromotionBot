import logging
from collections.abc import Iterator
from contextlib import contextmanager, suppress
from datetime import UTC, datetime, timedelta

from sqlalchemy import inspect

from app.core.circuit_breaker import CircuitOpenError
from app.core.config import settings
from app.core.errors import ConfigurationError, DeliveryError
from app.core.security import describe_error
from app.models.promotions import Promotion, PromotionStatus, Store
from app.repositories.promotion_repo import PromotionRepository
from app.schemas.promotion_schema import PendingDeliveryResponse
from app.services.affiliate import build_affiliate_url
from app.services.formatting import format_price_details
from app.services.openai_service import OpenAIService
from app.services.telegram_service import TelegramService

logger = logging.getLogger(__name__)

# A posted price must have been read from the store at most this long ago (the
# Amazon Associates rules, and a sensible limit for any store).
PRICE_MAX_AGE = timedelta(hours=24)


class DeliveryInProgressError(DeliveryError):
    """Another delivery is running, in this process or in another one."""

    status_code = 409
    error_code = "delivery_in_progress"


class PromotionAlreadySentError(DeliveryError):
    """Sending the promotion again would post it twice."""

    status_code = 409
    error_code = "promotion_already_sent"


class PriceExpiredError(DeliveryError):
    """The price was read too long ago to be posted."""

    status_code = 409
    error_code = "price_expired"


class PromotionDeliveryService:
    def __init__(
        self,
        promotion_repository: PromotionRepository,
        openai_service: OpenAIService,
        telegram_service: TelegramService,
    ):
        self.promotion_repository = promotion_repository
        self.openai_service = openai_service
        self.telegram_service = telegram_service

    def deliver_to_telegram(self, promotion: Promotion) -> Promotion:
        if promotion.store == Store.AMAZON:
            _require_partner_tag()

        with self._exclusive_delivery():
            # Read again under the lock: a batch may have sent it after the
            # caller loaded it.
            self.promotion_repository.refresh(promotion)
            if promotion.status == PromotionStatus.SENT:
                raise PromotionAlreadySentError(
                    f"Promotion {promotion.id} was already sent"
                )
            return self._deliver(promotion)

    def deliver_pending_to_telegram(self, limit: int = 10) -> PendingDeliveryResponse:
        # A missing tag is a configuration problem, not a problem with any
        # promotion: Amazon's stay queued, untouched (no OpenAI call, no
        # attempt spent), while the other stores' are delivered.
        skipped = [] if settings.amazon_partner_tag.strip() else [Store.AMAZON]
        if skipped:
            logger.warning(
                "Amazon promotions held: AMAZON_PARTNER_TAG is not configured"
            )

        with self._exclusive_delivery():
            promotions = self.promotion_repository.list_pending(
                limit=limit, exclude_stores=skipped
            )

            sent = 0
            failed = 0

            for position, promotion in enumerate(promotions):
                try:
                    self._deliver(promotion)
                    sent += 1
                except CircuitOpenError:
                    # The channel is paused after repeated failures: the rest
                    # of the batch stays queued, with its attempts untouched.
                    logger.warning(
                        "Telegram is paused; %d promotions left for a later cycle",
                        len(promotions) - position,
                    )
                    break
                except Exception:
                    failed += 1

        return PendingDeliveryResponse(
            processed=sent + failed,
            sent=sent,
            failed=failed,
            skipped_stores=skipped,
        )

    @contextmanager
    def _exclusive_delivery(self) -> Iterator[None]:
        # Two deliveries reading the same PENDING rows would post them twice:
        # the scheduler, the manual routes and other app processes all go
        # through this lock.
        with self.promotion_repository.delivery_lock() as acquired:
            if not acquired:
                raise DeliveryInProgressError(
                    "Another delivery is in progress; try again shortly"
                )
            yield

    def _deliver(self, promotion: Promotion) -> Promotion:
        if _price_expired(promotion):
            # Retrying cannot make the price recent again: give up at once
            # instead of spending the remaining attempts.
            self.promotion_repository.record_failure(
                promotion,
                attempts=promotion.attempts,
                error="Price read more than 24 hours ago; not posted",
                give_up=True,
            )
            raise PriceExpiredError(
                f"Promotion {promotion.id} has a price older than 24 hours"
            )

        delivered = False

        try:
            # Built before the copy so an invalid product URL fails without
            # spending an OpenAI call.
            affiliate_url = _affiliate_link(promotion)
            message = promotion.generated_message

            if not message:
                message = self.openai_service.generate_sales_copy(promotion)

                self.promotion_repository.update_generated_message(
                    promotion=promotion,
                    generated_message=message,
                )

            self.telegram_service.send_promotion(
                message=message,
                link=affiliate_url,
                image_url=promotion.image_url,
                # The price comes from the stored numbers, stamped with when it
                # was collected: a posted message is never updated.
                details=format_price_details(
                    discounted_price=promotion.discounted_price,
                    original_price=promotion.original_price,
                    discount_percentage=promotion.discount_percentage,
                    checked_at=promotion.created_at,
                ),
            )
            delivered = True
            return self.promotion_repository.mark_as_sent(promotion)

        except CircuitOpenError:
            # Nothing was attempted (the channel is paused), so this is not a
            # failed delivery attempt and must not bring the promotion closer
            # to FAILED.
            raise
        except Exception as error:
            if not delivered:
                self._record_failure(promotion, error)
                raise

            # Telegram already accepted the message: putting it back in the
            # queue would post it twice, so the only option is recording it as
            # sent.
            if self._record_sent_after_error(promotion):
                return promotion
            raise

    def _record_failure(self, promotion: Promotion, error: Exception) -> None:
        # The original error may have come from the database, leaving the
        # session unusable until it is rolled back: without the rollback, the
        # commit below would raise PendingRollbackError, hide the real cause,
        # and poison every promotion processed after this one in the batch.
        # If recording still fails, it is only logged, so the caller always
        # receives the original exception.
        try:
            self.promotion_repository.rollback()
            attempts = promotion.attempts + 1
            self.promotion_repository.record_failure(
                promotion,
                attempts=attempts,
                error=describe_error(error),
                give_up=attempts >= settings.delivery_max_attempts,
            )
        except Exception:
            # inspect().identity reads the primary key kept in memory: unlike
            # promotion.id it never queries a database that may be failing.
            logger.exception(
                "Could not record the failure of promotion %s",
                inspect(promotion).identity,
            )
            with suppress(Exception):
                self.promotion_repository.rollback()

    def _record_sent_after_error(self, promotion: Promotion) -> bool:
        try:
            self.promotion_repository.rollback()
            self.promotion_repository.mark_as_sent(promotion)
        except Exception:
            logger.critical(
                "Promotion %s was delivered to Telegram but could not be "
                "recorded as SENT; it is still PENDING and may be posted again",
                inspect(promotion).identity,
                exc_info=True,
            )
            with suppress(Exception):
                self.promotion_repository.rollback()
            return False

        logger.warning(
            "Promotion %s was recorded as SENT only on a second attempt",
            inspect(promotion).identity,
        )
        return True


def _price_expired(promotion: Promotion) -> bool:
    # Prices are read when the promotion is collected, so created_at is when
    # the store reported this one.
    return (
        promotion.discounted_price is not None
        and datetime.now(UTC) - promotion.created_at > PRICE_MAX_AGE
    )


def _affiliate_link(promotion: Promotion) -> str:
    """The link that earns the commission for this promotion's store."""
    if promotion.store == Store.AMAZON:
        return build_affiliate_url(promotion.product_url, settings.amazon_partner_tag)

    # Shopee and AliExpress return the tracked link themselves; their product
    # URL earns nothing.
    if not promotion.affiliate_url:
        raise ValueError(f"{promotion.store} promotion has no affiliate link")
    return promotion.affiliate_url


def _require_partner_tag() -> None:
    # Checked before touching the promotion, so it neither spends an OpenAI
    # call nor brings it closer to FAILED.
    if not settings.amazon_partner_tag.strip():
        raise ConfigurationError(
            "AMAZON_PARTNER_TAG is not configured; refusing to send links that "
            "earn no commission"
        )
