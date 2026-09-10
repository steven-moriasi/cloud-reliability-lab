from typing import cast

import pytest
from redis import Redis
from redis.exceptions import RedisError

from app.domain.errors import CacheUnavailableError
from app.domain.models import OrderSummary
from app.infrastructure.cache import CircuitBreaker, CircuitState, ExternalCache


class FakeRedis:
    def __init__(self) -> None:
        self.value: object = None
        self.ping_result = True
        self.failure: str | None = None
        self.writes: list[tuple[str, int, str]] = []

    def get(self, key: str) -> object:
        if self.failure == "get":
            raise RedisError("unavailable")
        assert key.startswith("orders:summary:")
        return self.value

    def setex(self, key: str, ttl: int, value: str) -> None:
        if self.failure == "setex":
            raise RedisError("unavailable")
        self.writes.append((key, ttl, value))

    def ping(self) -> bool:
        if self.failure == "ping":
            raise RedisError("unavailable")
        return self.ping_result


def cache_with(
    client: FakeRedis,
    *,
    failure_threshold: int = 2,
) -> ExternalCache:
    cache = ExternalCache(
        "redis://cache",
        ttl_seconds=30,
        breaker=CircuitBreaker(
            failure_threshold=failure_threshold,
            recovery_seconds=10,
        ),
    )
    cache._client = cast(Redis, client)
    return cache


def assert_state(cache: ExternalCache, expected: CircuitState) -> None:
    assert cache.circuit_state is expected


def test_external_cache_reads_misses_and_valid_summaries() -> None:
    client = FakeRedis()
    cache = cache_with(client)

    assert cache.get(7) is None

    client.value = '{"tenant_id":7,"order_count":3,"total_cents":1200}'
    assert cache.get(7) == OrderSummary(
        tenant_id=7,
        order_count=3,
        total_cents=1200,
    )
    assert_state(cache, CircuitState.CLOSED)


def test_external_cache_invalid_value_counts_as_failure() -> None:
    client = FakeRedis()
    client.value = 42
    cache = cache_with(client, failure_threshold=1)

    with pytest.raises(CacheUnavailableError, match="Cache read failed"):
        cache.get(7)

    assert_state(cache, CircuitState.OPEN)
    with pytest.raises(CacheUnavailableError, match="circuit is open"):
        cache.get(7)


def test_external_cache_writes_compact_sorted_json() -> None:
    client = FakeRedis()
    cache = cache_with(client)

    cache.set(OrderSummary(tenant_id=8, order_count=4, total_cents=900))

    assert client.writes == [
        (
            "orders:summary:8",
            30,
            '{"order_count":4,"tenant_id":8,"total_cents":900}',
        )
    ]
    assert cache.probe()


def test_external_cache_records_redis_failures() -> None:
    client = FakeRedis()
    cache = cache_with(client, failure_threshold=1)

    client.failure = "setex"
    with pytest.raises(CacheUnavailableError, match="Cache write failed"):
        cache.set(OrderSummary(tenant_id=8, order_count=4, total_cents=900))
    assert_state(cache, CircuitState.OPEN)
    assert not cache.probe()


def test_external_cache_probe_handles_unavailable_and_false_ping() -> None:
    client = FakeRedis()
    cache = cache_with(client, failure_threshold=2)

    client.ping_result = False
    assert not cache.probe()

    client.failure = "ping"
    assert not cache.probe()
    assert_state(cache, CircuitState.CLOSED)

    assert not cache.probe()
    assert_state(cache, CircuitState.OPEN)
