import time
from types import TracebackType

import psycopg
import pytest

from app import faults


class FakeCursor:
    def fetchone(self) -> tuple[int]:
        return (1,)


class FakeFaultConnection:
    def __init__(self) -> None:
        self.executions = 0

    def execute(self, query: str) -> FakeCursor:
        assert query == "SELECT 1"
        self.executions += 1
        if self.executions > 1:
            raise psycopg.OperationalError("terminated")
        return FakeCursor()

    def rollback(self) -> None:
        raise AssertionError("Terminated connection should not reach rollback")


class FakeConnectionContext:
    def __init__(self, connection: FakeFaultConnection) -> None:
        self._connection = connection

    def __enter__(self) -> FakeFaultConnection:
        return self._connection

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        return None


def test_idle_fault_detects_remediation_before_deadline(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    connection = FakeFaultConnection()

    def connect(
        database_url: str,
        *,
        application_name: str,
    ) -> FakeConnectionContext:
        assert database_url
        assert application_name.startswith("reliability-lab-fault-")
        return FakeConnectionContext(connection)

    monkeypatch.setattr(psycopg, "connect", connect)
    monkeypatch.setattr(time, "monotonic", lambda: 0.0)
    monkeypatch.setattr(time, "sleep", lambda _seconds: None)

    faults.inject_idle_transaction(30)

    assert "was terminated by the remediation agent" in capsys.readouterr().out
