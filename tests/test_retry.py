import pytest

from app.core.retry import call_with_retry


class Flaky:
    """Fails `failures` times with `error`, then returns "ok"."""

    def __init__(self, failures: int, error: Exception) -> None:
        self.failures = failures
        self.error = error
        self.calls = 0

    def __call__(self) -> str:
        self.calls += 1
        if self.calls <= self.failures:
            raise self.error
        return "ok"


def run(operation, waits, **options):
    return call_with_retry(
        operation,
        description="test call",
        sleep=waits.append,
        should_retry=options.pop("should_retry", lambda error: True),
        **options,
    )


def test_success_on_first_try_never_waits():
    waits = []

    assert run(Flaky(0, OSError()), waits) == "ok"
    assert waits == []


def test_error_not_worth_retrying_is_raised_at_once():
    waits = []
    operation = Flaky(1, ValueError("permanent"))

    with pytest.raises(ValueError):
        run(operation, waits, should_retry=lambda error: False)

    assert operation.calls == 1
    assert waits == []


def test_waits_grow_and_stop_at_the_cap():
    waits = []

    run(Flaky(5, OSError()), waits, attempts=6, base_delay=0.5, max_delay=2.0)

    caps = [0.5, 1.0, 2.0, 2.0, 2.0]
    for wait, cap in zip(waits, caps, strict=True):
        assert cap / 2 <= wait <= cap


def test_a_requested_wait_replaces_the_backoff():
    waits = []

    run(Flaky(1, OSError()), waits, delay_hint=lambda error: 7.0)

    assert waits == [7.0]


def test_last_error_is_raised_when_attempts_run_out():
    waits = []
    operation = Flaky(10, OSError("still down"))

    with pytest.raises(OSError, match="still down"):
        run(operation, waits, attempts=3)

    assert operation.calls == 3
    assert len(waits) == 2
