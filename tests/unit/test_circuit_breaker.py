import time
import pytest
from circuit_breaker import CircuitBreaker


@pytest.fixture
def cb():
    return CircuitBreaker(failure_threshold=3, recovery_timeout=1)


def test_starts_closed(cb):
    assert cb.get_state() == "closed"
    assert cb.allow_request() is True


def test_opens_after_threshold(cb):
    for _ in range(3):
        cb.record_failure()
    assert cb.get_state() == "open"
    assert cb.allow_request() is False


def test_success_resets_count(cb):
    cb.record_failure()
    cb.record_failure()
    assert cb.failure_count == 2
    cb.record_success()
    assert cb.failure_count == 0
    assert cb.get_state() == "closed"


def test_not_open_below_threshold(cb):
    cb.record_failure()
    cb.record_failure()
    assert cb.get_state() == "closed"
    assert cb.allow_request() is True


def test_half_open_after_timeout(cb):
    for _ in range(3):
        cb.record_failure()
    assert cb.get_state() == "open"
    time.sleep(1.05)
    assert cb.allow_request() is True
    assert cb.get_state() == "half-open"


def test_half_open_then_success_closes(cb):
    for _ in range(3):
        cb.record_failure()
    time.sleep(1.05)
    cb.allow_request()
    assert cb.get_state() == "half-open"
    cb.record_success()
    assert cb.get_state() == "closed"


def test_open_blocks_before_timeout(cb):
    for _ in range(3):
        cb.record_failure()
    assert cb.allow_request() is False
    assert cb.allow_request() is False


def test_failure_after_half_open_reopens(cb):
    for _ in range(3):
        cb.record_failure()
    time.sleep(1.05)
    cb.allow_request()
    cb.record_failure()
    assert cb.get_state() == "open"
