import pytest

from app.core.circuit_breaker import CircuitBreaker, CircuitOpenError


class FakeClock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now


@pytest.fixture
def clock():
    return FakeClock()


@pytest.fixture
def breaker(clock):
    return CircuitBreaker("Service", failure_threshold=3, reset_timeout=60, clock=clock)


def fail():
    raise ConnectionError("down")


def bad_request():
    raise ValueError("bad request")


def fail_times(breaker, times):
    for _ in range(times):
        with pytest.raises(ConnectionError):
            breaker.call(fail)


def test_stays_closed_below_the_threshold(breaker):
    fail_times(breaker, 2)

    assert breaker.state == "closed"
    assert breaker.call(lambda: "ok") == "ok"


def test_opens_after_consecutive_failures_and_stops_calling(breaker):
    fail_times(breaker, 3)
    calls = []

    with pytest.raises(CircuitOpenError, match="Service is unavailable"):
        breaker.call(lambda: calls.append("called"))

    assert breaker.state == "open"
    assert calls == []  # the operation was not even attempted


def test_a_success_in_between_resets_the_count(breaker):
    fail_times(breaker, 2)
    breaker.call(lambda: "ok")
    fail_times(breaker, 2)

    assert breaker.state == "closed"


def test_errors_that_are_not_failures_reset_the_count(breaker):
    # A bad request means the service answered: it is healthy.
    fail_times(breaker, 2)
    with pytest.raises(ValueError):
        breaker.call(
            bad_request, is_failure=lambda error: not isinstance(error, ValueError)
        )
    fail_times(breaker, 2)

    assert breaker.state == "closed"


def test_after_the_pause_a_successful_trial_closes_it(breaker, clock):
    fail_times(breaker, 3)
    clock.now += 61

    assert breaker.state == "half_open"
    assert breaker.call(lambda: "ok") == "ok"
    assert breaker.state == "closed"


def test_a_failed_trial_opens_it_for_another_pause(breaker, clock):
    fail_times(breaker, 3)
    clock.now += 61

    fail_times(breaker, 1)

    assert breaker.state == "open"
    clock.now += 59
    with pytest.raises(CircuitOpenError):
        breaker.call(lambda: "ok")
