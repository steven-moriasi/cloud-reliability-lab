from dataclasses import dataclass

from app.domain.models import OrderSummary
from app.infrastructure.cache import CircuitBreaker, CircuitState, MemoryStaleCache


@dataclass
class Clock:
    value: float = 0

    def __call__(self) -> float:
        return self.value


def assert_state(breaker: CircuitBreaker, expected: CircuitState) -> None:
    assert breaker.state is expected


def test_circuit_opens_and_allows_single_recovery_probe() -> None:
    clock = Clock()
    breaker = CircuitBreaker(
        failure_threshold=2,
        recovery_seconds=10,
        clock=clock,
    )

    breaker.record_failure()
    assert_state(breaker, CircuitState.CLOSED)

    breaker.record_failure()
    assert_state(breaker, CircuitState.OPEN)
    assert not breaker.allow_request()

    clock.value = 10
    assert breaker.allow_request()
    assert_state(breaker, CircuitState.HALF_OPEN)
    assert not breaker.allow_request()

    breaker.record_success()
    assert_state(breaker, CircuitState.CLOSED)
    assert breaker.allow_request()


def test_half_open_failure_reopens_recovery_window() -> None:
    clock = Clock()
    breaker = CircuitBreaker(
        failure_threshold=1,
        recovery_seconds=5,
        clock=clock,
    )

    breaker.record_failure()
    clock.value = 5
    assert breaker.allow_request()

    breaker.record_failure()
    assert_state(breaker, CircuitState.OPEN)
    clock.value = 9
    assert not breaker.allow_request()
    clock.value = 10
    assert breaker.allow_request()


def test_memory_stale_cache_expires_entries() -> None:
    clock = Clock()
    cache = MemoryStaleCache(stale_seconds=30, clock=clock)
    summary = OrderSummary(tenant_id=7, order_count=3, total_cents=1200)

    cache.set(summary)
    assert cache.get(7) == summary

    clock.value = 30
    assert cache.get(7) is None
