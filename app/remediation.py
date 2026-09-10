import signal
import threading
from dataclasses import dataclass
from datetime import timedelta
from typing import Protocol

import structlog
from prometheus_client import start_http_server

from app.core.config import Settings, get_settings
from app.core.logging import configure_logging
from app.core.metrics import REMEDIATIONS
from app.infrastructure.database import Database
from app.infrastructure.remediation import IdleSession, PostgresRemediationBackend

logger = structlog.get_logger()


class RemediationBackend(Protocol):
    def find_idle_sessions(
        self,
        *,
        application_prefix: str,
        older_than: timedelta,
        limit: int,
    ) -> list[IdleSession]: ...

    def terminate(self, session: IdleSession) -> bool: ...

    def record(self, *, session: IdleSession, outcome: str) -> None: ...


@dataclass(frozen=True)
class RemediationResult:
    inspected: int
    terminated: int


class RemediationController:
    def __init__(
        self,
        backend: RemediationBackend,
        *,
        application_prefix: str,
        idle_transaction_seconds: int,
        max_terminations: int,
    ) -> None:
        self._backend = backend
        self._application_prefix = application_prefix
        self._older_than = timedelta(seconds=idle_transaction_seconds)
        self._max_terminations = max_terminations

    def run_once(self) -> RemediationResult:
        candidates = self._backend.find_idle_sessions(
            application_prefix=self._application_prefix,
            older_than=self._older_than,
            limit=self._max_terminations,
        )
        terminated = 0
        for candidate in candidates[: self._max_terminations]:
            if not candidate.application_name.startswith(self._application_prefix):
                REMEDIATIONS.labels(
                    action="terminate_idle_transaction",
                    outcome="scope_rejected",
                ).inc()
                continue
            outcome = "terminated" if self._backend.terminate(candidate) else "not_terminated"
            self._backend.record(session=candidate, outcome=outcome)
            REMEDIATIONS.labels(
                action="terminate_idle_transaction",
                outcome=outcome,
            ).inc()
            if outcome == "terminated":
                terminated += 1
        return RemediationResult(inspected=len(candidates), terminated=terminated)


def build_controller(settings: Settings) -> tuple[Database, RemediationController]:
    database = Database(
        settings.database_url,
        min_size=1,
        max_size=max(settings.remediation_max_terminations + 1, 2),
        pool_timeout_seconds=settings.pool_timeout_seconds,
        query_timeout_ms=settings.query_timeout_ms,
    )
    backend = PostgresRemediationBackend(database)
    return database, RemediationController(
        backend,
        application_prefix=settings.fault_application_prefix,
        idle_transaction_seconds=settings.idle_transaction_seconds,
        max_terminations=settings.remediation_max_terminations,
    )


def run() -> None:
    configure_logging()
    settings = get_settings()
    database, controller = build_controller(settings)
    database.open()
    stop = threading.Event()
    signal.signal(signal.SIGTERM, lambda _signum, _frame: stop.set())
    signal.signal(signal.SIGINT, lambda _signum, _frame: stop.set())
    start_http_server(9100)
    logger.info(
        "remediation_agent_started",
        interval_seconds=settings.remediation_interval_seconds,
        scope_prefix=settings.fault_application_prefix,
    )
    try:
        while not stop.is_set():
            result = controller.run_once()
            if result.inspected:
                logger.info(
                    "remediation_run",
                    inspected=result.inspected,
                    terminated=result.terminated,
                )
            stop.wait(settings.remediation_interval_seconds)
    finally:
        database.close()


if __name__ == "__main__":
    run()
