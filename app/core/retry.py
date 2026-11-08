"""Retry with exponential backoff for calls to external services."""

import logging
import random
import time
from collections.abc import Callable

from app.core.security import describe_error

logger = logging.getLogger(__name__)


def call_with_retry[T](
    operation: Callable[[], T],
    *,
    should_retry: Callable[[Exception], bool],
    description: str,
    attempts: int = 3,
    base_delay: float = 0.5,
    max_delay: float = 8.0,
    delay_hint: Callable[[Exception], float | None] = lambda error: None,
    sleep: Callable[[float], None] = time.sleep,
) -> T:
    """Run `operation`, retrying errors that `should_retry` accepts.

    The wait doubles at each attempt (0.5 s, 1 s, 2 s...) up to `max_delay`,
    with jitter so that many callers failing together do not retry in lockstep.
    When the service says how long to wait (`delay_hint`, such as Telegram's
    retry_after), that wait is used instead. The last error is re-raised once
    `attempts` run out, or immediately when it is not retryable.
    """
    for attempt in range(1, attempts + 1):
        try:
            return operation()
        except Exception as error:
            if attempt == attempts or not should_retry(error):
                raise

            delay = delay_hint(error)
            if delay is None:
                backoff = min(max_delay, base_delay * 2 ** (attempt - 1))
                delay = random.uniform(backoff / 2, backoff)  # noqa: S311 - jitter, not security

            logger.warning(
                "%s failed (attempt %d of %d), retrying in %.1fs: %s",
                description,
                attempt,
                attempts,
                delay,
                describe_error(error),
            )
            sleep(delay)

    raise AssertionError("unreachable: the loop returns or raises")
