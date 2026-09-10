from contextlib import AbstractContextManager
from datetime import timedelta
from types import TracebackType
from typing import cast

import psycopg
import pytest

from app.domain.errors import DatabaseUnavailableError
from app.infrastructure.database import Database
from app.infrastructure.remediation import IdleSession, PostgresRemediationBackend


class FakeCursor:
    def __init__(
        self,
        *,
        rows: list[tuple[object, ...]] | None = None,
        row: tuple[object, ...] | None = None,
    ) -> None:
        self._rows = rows or []
        self._row = row

    def fetchall(self) -> list[tuple[object, ...]]:
        return self._rows

    def fetchone(self) -> tuple[object, ...] | None:
        return self._row


class FakeConnection:
    def __init__(self) -> None:
        self.rows: list[tuple[object, ...]] = []
        self.row: tuple[object, ...] | None = None
        self.error = False
        self.queries: list[tuple[str, tuple[object, ...] | None]] = []

    def execute(
        self,
        query: str,
        parameters: tuple[object, ...] | None = None,
    ) -> FakeCursor:
        if self.error:
            raise psycopg.OperationalError("unavailable")
        self.queries.append((query, parameters))
        return FakeCursor(rows=self.rows, row=self.row)


class FakeConnectionContext(AbstractContextManager[FakeConnection]):
    def __init__(self, connection: FakeConnection) -> None:
        self._connection = connection

    def __enter__(self) -> FakeConnection:
        return self._connection

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        return None


class FakeDatabase:
    def __init__(self) -> None:
        self.connection_value = FakeConnection()

    def connection(self) -> AbstractContextManager[FakeConnection]:
        return FakeConnectionContext(self.connection_value)


def backend_with(database: FakeDatabase) -> PostgresRemediationBackend:
    return PostgresRemediationBackend(cast(Database, database))


def test_backend_finds_scoped_idle_sessions() -> None:
    database = FakeDatabase()
    database.connection_value.rows = [
        (17, "reliability-lab-fault-test", 42.5),
    ]
    backend = backend_with(database)

    sessions = backend.find_idle_sessions(
        application_prefix="reliability-lab-fault-",
        older_than=timedelta(seconds=30),
        limit=2,
    )

    assert sessions == [IdleSession(17, "reliability-lab-fault-test", 42.5)]
    assert database.connection_value.queries[0][1] == (
        "reliability-lab-fault-%",
        30,
        2,
    )


def test_backend_terminates_and_records_session() -> None:
    database = FakeDatabase()
    backend = backend_with(database)
    session = IdleSession(17, "reliability-lab-fault-test", 42.5)

    database.connection_value.row = (True,)
    assert backend.terminate(session)

    backend.record(session=session, outcome="terminated")
    assert database.connection_value.queries[-1][1] is not None
    assert database.connection_value.queries[-1][1][:2] == (17, "terminated")


def test_backend_handles_missing_termination_result() -> None:
    database = FakeDatabase()
    backend = backend_with(database)

    assert not backend.terminate(IdleSession(17, "reliability-lab-fault-test", 42.5))


@pytest.mark.parametrize(
    ("operation", "message"),
    [
        ("find", "Idle-session query failed"),
        ("terminate", "Session termination failed"),
        ("record", "Remediation audit write failed"),
    ],
)
def test_backend_translates_database_errors(operation: str, message: str) -> None:
    database = FakeDatabase()
    database.connection_value.error = True
    backend = backend_with(database)
    session = IdleSession(17, "reliability-lab-fault-test", 42.5)

    with pytest.raises(DatabaseUnavailableError, match=message):
        if operation == "find":
            backend.find_idle_sessions(
                application_prefix="reliability-lab-fault-",
                older_than=timedelta(seconds=30),
                limit=2,
            )
        elif operation == "terminate":
            backend.terminate(session)
        else:
            backend.record(session=session, outcome="terminated")
