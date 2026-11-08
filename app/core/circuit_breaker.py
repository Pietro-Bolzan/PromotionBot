"""Stop calling a service that keeps failing, for a while."""

import logging
import threading
import time
from collections.abc import Callable

from app.core.errors import AppError

logger = logging.getLogger(__name__)


class CircuitOpenError(AppError):
    """The service is paused after repeated failures; nothing was attempted."""

    status_code = 503
    error_code = "service_unavailable"


class CircuitBreaker:
    """Counts consecutive failures of one external service.

    - closed: calls go through; failures in a row are counted.
    - open: after `failure_threshold` of them, every call fails at once with
      CircuitOpenError, for `reset_timeout` seconds.
    - half-open: once the pause is over, calls go through again as a trial;
      a success closes the circuit, a failure opens it for another pause.

    Errors that `is_failure` rejects (a bad request, say) mean the service did
    answer, so they reset the count instead. Thread-safe: the same breaker is
    shared by request threads and the scheduler.
    """

    def __init__(
        self,
        name: str,
        failure_threshold: int,
        reset_timeout: float,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.name = name
        self.failure_threshold = failure_threshold
        self.reset_timeout = reset_timeout
        self._clock = clock
        self._lock = threading.Lock()
        self._consecutive_failures = 0
        self._opened_at: float | None = None

    @property
    def state(self) -> str:
        with self._lock:
            if self._opened_at is None:
                return "closed"
            if self._clock() - self._opened_at < self.reset_timeout:
                return "open"
            return "half_open"

    def call[T](
        self,
        operation: Callable[[], T],
        is_failure: Callable[[Exception], bool] = lambda error: True,
    ) -> T:
        self._raise_if_open()
        try:
            result = operation()
        except Exception as error:
            if is_failure(error):
                self._record_failure()
            else:
                self._record_success()
            raise
        self._record_success()
        return result

    def _raise_if_open(self) -> None:
        with self._lock:
            if self._opened_at is None:
                return
            remaining = self._opened_at + self.reset_timeout - self._clock()
            if remaining > 0:
                raise CircuitOpenError(
                    f"{self.name} is unavailable after repeated failures; "
                    f"calls are paused for another {remaining:.0f}s"
                )

    def _record_failure(self) -> None:
        with self._lock:
            self._consecutive_failures += 1
            trial_failed = self._opened_at is not None
            if trial_failed or self._consecutive_failures >= self.failure_threshold:
                self._opened_at = self._clock()
                logger.warning(
                    "%s circuit opened after %d consecutive failures; "
                    "pausing calls for %.0fs",
                    self.name,
                    self._consecutive_failures,
                    self.reset_timeout,
                )

    def _record_success(self) -> None:
        with self._lock:
            if self._opened_at is not None:
                logger.info("%s circuit closed: the service answered again", self.name)
            self._consecutive_failures = 0
            self._opened_at = None
