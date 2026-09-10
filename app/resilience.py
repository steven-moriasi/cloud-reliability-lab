import time
from contextlib import suppress
from dataclasses import dataclass
from typing import Protocol

from app.core.metrics import SUMMARY_DURATION, SUMMARY_REQUESTS
from app.domain.errors import CacheUnavailableError, DatabaseUnavailableError
from app.domain.models import DataSource, OrderSummary


class SummaryRepository(Protocol):
    def get_order_summary(self, tenant_id: int) -> OrderSummary: ...

    def probe(self) -> bool: ...


class SummaryCache(Protocol):
    def get(self, tenant_id: int) -> OrderSummary | None: ...

    def set(self, summary: OrderSummary) -> None: ...

    def probe(self) -> bool: ...


class StaleCache(Protocol):
    def get(self, tenant_id: int) -> OrderSummary | None: ...

    def set(self, summary: OrderSummary) -> None: ...


@dataclass(frozen=True)
class SummaryResult:
    summary: OrderSummary
    source: DataSource


class ResilientOrderService:
    def __init__(
        self,
        repository: SummaryRepository,
        cache: SummaryCache,
        stale_cache: StaleCache,
    ) -> None:
        self._repository = repository
        self._cache = cache
        self._stale_cache = stale_cache

    def get_summary(self, tenant_id: int) -> SummaryResult:
        started = time.monotonic()
        try:
            cached = self._cache.get(tenant_id)
        except CacheUnavailableError:
            cached = None
        if cached is not None:
            self._observe(DataSource.CACHE, started, "success")
            return SummaryResult(summary=cached, source=DataSource.CACHE)

        try:
            summary = self._repository.get_order_summary(tenant_id)
        except DatabaseUnavailableError:
            stale = self._stale_cache.get(tenant_id)
            if stale is None:
                self._observe(DataSource.STALE, started, "unavailable")
                raise
            self._observe(DataSource.STALE, started, "success")
            return SummaryResult(summary=stale, source=DataSource.STALE)

        self._stale_cache.set(summary)
        with suppress(CacheUnavailableError):
            self._cache.set(summary)
        self._observe(DataSource.DATABASE, started, "success")
        return SummaryResult(summary=summary, source=DataSource.DATABASE)

    def dependency_status(self) -> tuple[bool, bool]:
        database = self._repository.probe()
        cache = self._cache.probe()
        return database, cache

    @staticmethod
    def _observe(source: DataSource, started: float, outcome: str) -> None:
        SUMMARY_REQUESTS.labels(source=source.value, outcome=outcome).inc()
        SUMMARY_DURATION.labels(source=source.value).observe(time.monotonic() - started)
