from collections.abc import Mapping
from contextlib import AbstractContextManager
from typing import cast

import psycopg
from psycopg import Connection
from psycopg_pool import ConnectionPool, PoolTimeout

from app.core.metrics import DEPENDENCY_AVAILABLE, POOL_CONNECTIONS
from app.domain.errors import DatabaseUnavailableError
from app.domain.models import OrderSummary

DatabaseRow = tuple[object, ...]

SUMMARY_QUERY = """
    SELECT tenant_id, COUNT(*)::bigint, COALESCE(SUM(total_cents), 0)::bigint
    FROM orders
    WHERE tenant_id = %s
      AND status = 'completed'
      AND created_at >= now() - interval '30 days'
    GROUP BY tenant_id
"""


class Database:
    def __init__(
        self,
        url: str,
        *,
        min_size: int,
        max_size: int,
        pool_timeout_seconds: float,
        query_timeout_ms: int,
    ) -> None:
        self._pool = ConnectionPool[Connection[DatabaseRow]](
            conninfo=url,
            min_size=min_size,
            max_size=max_size,
            timeout=pool_timeout_seconds,
            kwargs={
                "autocommit": True,
                "options": f"-c statement_timeout={query_timeout_ms}",
            },
            open=False,
        )
        self._pool_timeout_seconds = pool_timeout_seconds

    def open(self) -> None:
        try:
            self._pool.open(wait=True, timeout=self._pool_timeout_seconds)
        except (psycopg.Error, PoolTimeout) as error:
            raise DatabaseUnavailableError("Database pool could not open") from error

    def close(self) -> None:
        self._pool.close()

    def connection(self) -> AbstractContextManager[Connection[DatabaseRow]]:
        return self._pool.connection()

    def get_order_summary(self, tenant_id: int) -> OrderSummary:
        try:
            with self._pool.connection() as connection:
                row = connection.execute(SUMMARY_QUERY, (tenant_id,)).fetchone()
        except (psycopg.Error, PoolTimeout) as error:
            DEPENDENCY_AVAILABLE.labels(dependency="database").set(0)
            raise DatabaseUnavailableError("Database query failed") from error

        DEPENDENCY_AVAILABLE.labels(dependency="database").set(1)
        if row is None:
            return OrderSummary(tenant_id=tenant_id, order_count=0, total_cents=0)
        return OrderSummary(
            tenant_id=cast(int, row[0]),
            order_count=cast(int, row[1]),
            total_cents=cast(int, row[2]),
        )

    def probe(self) -> bool:
        try:
            with self._pool.connection() as connection:
                connection.execute("SELECT 1").fetchone()
        except (psycopg.Error, PoolTimeout):
            DEPENDENCY_AVAILABLE.labels(dependency="database").set(0)
            self._record_pool_stats()
            return False
        DEPENDENCY_AVAILABLE.labels(dependency="database").set(1)
        self._record_pool_stats()
        return True

    def _record_pool_stats(self) -> None:
        stats: Mapping[str, int] = self._pool.get_stats()
        POOL_CONNECTIONS.labels(state="total").set(stats.get("pool_size", 0))
        POOL_CONNECTIONS.labels(state="available").set(stats.get("pool_available", 0))
        POOL_CONNECTIONS.labels(state="waiting").set(stats.get("requests_waiting", 0))
