from dataclasses import dataclass, field

import pytest

from app.domain.errors import CacheUnavailableError, DatabaseUnavailableError
from app.domain.models import DataSource, OrderSummary
from app.resilience import ResilientOrderService


@dataclass
class FakeRepository:
    summary: OrderSummary
    available: bool = True
    calls: int = 0

    def get_order_summary(self, tenant_id: int) -> OrderSummary:
        self.calls += 1
        if not self.available:
            raise DatabaseUnavailableError("unavailable")
        assert tenant_id == self.summary.tenant_id
        return self.summary

    def probe(self) -> bool:
        return self.available


@dataclass
class FakeCache:
    value: OrderSummary | None = None
    available: bool = True
    get_calls: int = 0
    set_calls: int = 0

    def get(self, tenant_id: int) -> OrderSummary | None:
        self.get_calls += 1
        if not self.available:
            raise CacheUnavailableError("unavailable")
        if self.value is not None:
            assert tenant_id == self.value.tenant_id
        return self.value

    def set(self, summary: OrderSummary) -> None:
        self.set_calls += 1
        if not self.available:
            raise CacheUnavailableError("unavailable")
        self.value = summary

    def probe(self) -> bool:
        return self.available


@dataclass
class FakeStaleCache:
    entries: dict[int, OrderSummary] = field(default_factory=dict)

    def get(self, tenant_id: int) -> OrderSummary | None:
        return self.entries.get(tenant_id)

    def set(self, summary: OrderSummary) -> None:
        self.entries[summary.tenant_id] = summary


def test_cache_hit_avoids_database() -> None:
    summary = OrderSummary(tenant_id=7, order_count=3, total_cents=1200)
    repository = FakeRepository(summary)
    cache = FakeCache(value=summary)
    service = ResilientOrderService(repository, cache, FakeStaleCache())

    result = service.get_summary(7)

    assert result.source is DataSource.CACHE
    assert result.summary == summary
    assert repository.calls == 0


def test_cache_failure_falls_back_to_database_and_stale_copy() -> None:
    summary = OrderSummary(tenant_id=7, order_count=3, total_cents=1200)
    repository = FakeRepository(summary)
    cache = FakeCache(available=False)
    stale = FakeStaleCache()
    service = ResilientOrderService(repository, cache, stale)

    result = service.get_summary(7)

    assert result.source is DataSource.DATABASE
    assert result.summary == summary
    assert stale.get(7) == summary


def test_database_failure_serves_bounded_stale_value() -> None:
    summary = OrderSummary(tenant_id=7, order_count=3, total_cents=1200)
    repository = FakeRepository(summary, available=False)
    stale = FakeStaleCache(entries={7: summary})
    service = ResilientOrderService(repository, FakeCache(), stale)

    result = service.get_summary(7)

    assert result.source is DataSource.STALE
    assert result.summary == summary


def test_database_failure_without_stale_value_is_unavailable() -> None:
    summary = OrderSummary(tenant_id=7, order_count=3, total_cents=1200)
    service = ResilientOrderService(
        FakeRepository(summary, available=False),
        FakeCache(),
        FakeStaleCache(),
    )

    with pytest.raises(DatabaseUnavailableError):
        service.get_summary(7)


def test_dependency_status_preserves_cache_degradation() -> None:
    summary = OrderSummary(tenant_id=7, order_count=3, total_cents=1200)
    service = ResilientOrderService(
        FakeRepository(summary),
        FakeCache(available=False),
        FakeStaleCache(),
    )

    assert service.dependency_status() == (True, False)
