import json
import threading
import time
from collections.abc import Callable
from dataclasses import asdict
from enum import StrEnum

from pydantic import BaseModel, ConfigDict
from redis import Redis
from redis.exceptions import RedisError

from app.core.metrics import CACHE_CIRCUIT_TRANSITIONS, DEPENDENCY_AVAILABLE
from app.domain.errors import CacheUnavailableError
from app.domain.models import OrderSummary


class CircuitState(StrEnum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class CircuitBreaker:
    def __init__(
        self,
        *,
        failure_threshold: int,
        recovery_seconds: float,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._failure_threshold = failure_threshold
        self._recovery_seconds = recovery_seconds
        self._clock = clock
        self._failures = 0
        self._opened_at = 0.0
        self._state = CircuitState.CLOSED
        self._lock = threading.Lock()

    @property
    def state(self) -> CircuitState:
        with self._lock:
            return self._state

    def allow_request(self) -> bool:
        with self._lock:
            if self._state is CircuitState.CLOSED:
                return True
            if self._state is CircuitState.OPEN:
                if self._clock() - self._opened_at < self._recovery_seconds:
                    return False
                self._transition(CircuitState.HALF_OPEN)
                return True
            return False

    def record_success(self) -> None:
        with self._lock:
            self._failures = 0
            if self._state is not CircuitState.CLOSED:
                self._transition(CircuitState.CLOSED)

    def record_failure(self) -> None:
        with self._lock:
            self._failures += 1
            if (
                self._state is CircuitState.HALF_OPEN
                or self._failures >= self._failure_threshold
            ):
                self._opened_at = self._clock()
                self._transition(CircuitState.OPEN)

    def _transition(self, state: CircuitState) -> None:
        self._state = state
        CACHE_CIRCUIT_TRANSITIONS.labels(state=state.value).inc()


class CachedSummary(BaseModel):
    model_config = ConfigDict(frozen=True)

    tenant_id: int
    order_count: int
    total_cents: int

    def to_domain(self) -> OrderSummary:
        return OrderSummary(**self.model_dump())


class ExternalCache:
    def __init__(
        self,
        url: str,
        *,
        ttl_seconds: int,
        breaker: CircuitBreaker,
        timeout_seconds: float = 1,
    ) -> None:
        self._client = Redis.from_url(
            url,
            decode_responses=True,
            socket_connect_timeout=timeout_seconds,
            socket_timeout=timeout_seconds,
        )
        self._ttl_seconds = ttl_seconds
        self._breaker = breaker

    @property
    def circuit_state(self) -> CircuitState:
        return self._breaker.state

    def get(self, tenant_id: int) -> OrderSummary | None:
        if not self._breaker.allow_request():
            raise CacheUnavailableError("Cache circuit is open")
        try:
            value = self._client.get(self._key(tenant_id))
            if value is None:
                self._breaker.record_success()
                DEPENDENCY_AVAILABLE.labels(dependency="cache").set(1)
                return None
            if not isinstance(value, str):
                raise ValueError("Cache returned an invalid value")
            summary = CachedSummary.model_validate_json(value).to_domain()
        except (RedisError, ValueError) as error:
            self._breaker.record_failure()
            DEPENDENCY_AVAILABLE.labels(dependency="cache").set(0)
            raise CacheUnavailableError("Cache read failed") from error
        self._breaker.record_success()
        DEPENDENCY_AVAILABLE.labels(dependency="cache").set(1)
        return summary

    def set(self, summary: OrderSummary) -> None:
        if not self._breaker.allow_request():
            raise CacheUnavailableError("Cache circuit is open")
        try:
            self._client.setex(
                self._key(summary.tenant_id),
                self._ttl_seconds,
                json.dumps(asdict(summary), separators=(",", ":"), sort_keys=True),
            )
        except RedisError as error:
            self._breaker.record_failure()
            DEPENDENCY_AVAILABLE.labels(dependency="cache").set(0)
            raise CacheUnavailableError("Cache write failed") from error
        self._breaker.record_success()
        DEPENDENCY_AVAILABLE.labels(dependency="cache").set(1)

    def probe(self) -> bool:
        if not self._breaker.allow_request():
            DEPENDENCY_AVAILABLE.labels(dependency="cache").set(0)
            return False
        try:
            available = bool(self._client.ping())
        except RedisError:
            self._breaker.record_failure()
            DEPENDENCY_AVAILABLE.labels(dependency="cache").set(0)
            return False
        if available:
            self._breaker.record_success()
            DEPENDENCY_AVAILABLE.labels(dependency="cache").set(1)
        return available

    @staticmethod
    def _key(tenant_id: int) -> str:
        return f"orders:summary:{tenant_id}"


class MemoryStaleCache:
    def __init__(
        self,
        *,
        stale_seconds: float,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._stale_seconds = stale_seconds
        self._clock = clock
        self._entries: dict[int, tuple[OrderSummary, float]] = {}
        self._lock = threading.Lock()

    def set(self, summary: OrderSummary) -> None:
        with self._lock:
            self._entries[summary.tenant_id] = (
                summary,
                self._clock() + self._stale_seconds,
            )

    def get(self, tenant_id: int) -> OrderSummary | None:
        with self._lock:
            entry = self._entries.get(tenant_id)
            if entry is None:
                return None
            summary, expires_at = entry
            if self._clock() >= expires_at:
                del self._entries[tenant_id]
                return None
            return summary
