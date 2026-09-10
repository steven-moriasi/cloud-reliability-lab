from dataclasses import dataclass
from enum import StrEnum


class DependencyState(StrEnum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNAVAILABLE = "unavailable"


class DataSource(StrEnum):
    CACHE = "cache"
    DATABASE = "database"
    STALE = "stale"


@dataclass(frozen=True)
class OrderSummary:
    tenant_id: int
    order_count: int
    total_cents: int


@dataclass(frozen=True)
class DependencyStatus:
    database: DependencyState
    cache: DependencyState

    @property
    def ready(self) -> bool:
        return self.database is DependencyState.HEALTHY
