from contextlib import AbstractContextManager
from types import TracebackType
from typing import cast

import psycopg
import pytest
from psycopg import Connection
from psycopg_pool import ConnectionPool, PoolTimeout

from app.domain.errors import DatabaseUnavailableError
from app.domain.models import OrderSummary
from app.infrastructure.database import Database, DatabaseRow


class FakeCursor:
    def __init__(self, row: DatabaseRow | None) -> None:
        self._row = row

    def fetchone(self) -> DatabaseRow | None:
        return self._row


class FakeConnection:
    def __init__(self, row: DatabaseRow | None) -> None:
        self.row = row
        self.queries: list[tuple[str, tuple[object, ...] | None]] = []

    def execute(
        self,
        query: str,
        parameters: tuple[object, ...] | None = None,
    ) -> FakeCursor:
        self.queries.append((query, parameters))
        return FakeCursor(self.row)


class FakeConnectionContext(AbstractContextManager[FakeConnection]):
    def __init__(
        self,
        connection: FakeConnection,
        error: BaseException | None = None,
    ) -> None:
        self._connection = connection
        self._error = error

    def __enter__(self) -> FakeConnection:
        if self._error is not None:
            raise self._error
        return self._connection

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        return None


class FakePool:
    def __init__(self, row: DatabaseRow | None = None) -> None:
        self.connection_value = FakeConnection(row)
        self.connection_error: BaseException | None = None
        self.open_error: BaseException | None = None
        self.opened = False
        self.closed = False
        self.stats: dict[str, int] = {
            "pool_size": 5,
            "pool_available": 3,
            "requests_waiting": 1,
        }

    def open(self, *, wait: bool, timeout: float) -> None:
        assert wait
        assert timeout == 2
        if self.open_error is not None:
            raise self.open_error
        self.opened = True

    def close(self) -> None:
        self.closed = True

    def connection(self) -> AbstractContextManager[FakeConnection]:
        return FakeConnectionContext(self.connection_value, self.connection_error)

    def get_stats(self) -> dict[str, int]:
        return self.stats


def database_with(pool: FakePool) -> Database:
    database = Database(
        "postgresql://unused",
        min_size=1,
        max_size=5,
        pool_timeout_seconds=2,
        query_timeout_ms=1000,
    )
    database._pool = cast(ConnectionPool[Connection[DatabaseRow]], pool)
    return database


def test_database_returns_summary_and_empty_tenant() -> None:
    pool = FakePool((7, 3, 1200))
    database = database_with(pool)

    assert database.get_order_summary(7) == OrderSummary(7, 3, 1200)
    assert pool.connection_value.queries[-1][1] == (7,)

    pool.connection_value.row = None
    assert database.get_order_summary(9) == OrderSummary(9, 0, 0)


def test_database_translates_query_failure() -> None:
    pool = FakePool()
    pool.connection_error = psycopg.OperationalError("unavailable")
    database = database_with(pool)

    with pytest.raises(DatabaseUnavailableError, match="Database query failed"):
        database.get_order_summary(7)


def test_database_probe_records_pool_state() -> None:
    pool = FakePool((1,))
    database = database_with(pool)

    assert database.probe()

    pool.connection_error = PoolTimeout("busy")
    assert not database.probe()


def test_database_open_close_and_connection_access() -> None:
    pool = FakePool((1,))
    database = database_with(pool)

    database.open()
    assert pool.opened
    with database.connection() as connection:
        assert connection is not None
    database.close()
    assert pool.closed


def test_database_open_translates_pool_failure() -> None:
    pool = FakePool()
    pool.open_error = PoolTimeout("busy")
    database = database_with(pool)

    with pytest.raises(DatabaseUnavailableError, match="pool could not open"):
        database.open()
