from dataclasses import dataclass
from datetime import timedelta
from typing import cast

import psycopg
from psycopg.types.json import Jsonb
from psycopg_pool import PoolTimeout

from app.domain.errors import DatabaseUnavailableError
from app.infrastructure.database import Database


@dataclass(frozen=True)
class IdleSession:
    pid: int
    application_name: str
    idle_for_seconds: float


class PostgresRemediationBackend:
    def __init__(self, database: Database) -> None:
        self._database = database

    def find_idle_sessions(
        self,
        *,
        application_prefix: str,
        older_than: timedelta,
        limit: int,
    ) -> list[IdleSession]:
        try:
            with self._database.connection() as connection:
                rows = connection.execute(
                    """
                    SELECT
                        pid,
                        application_name,
                        EXTRACT(EPOCH FROM (clock_timestamp() - xact_start))::double precision
                    FROM pg_stat_activity
                    WHERE datname = current_database()
                      AND pid <> pg_backend_pid()
                      AND backend_type = 'client backend'
                      AND state = 'idle in transaction'
                      AND application_name LIKE %s
                      AND xact_start < clock_timestamp() - make_interval(secs => %s)
                    ORDER BY xact_start
                    LIMIT %s
                    """,
                    (
                        f"{application_prefix}%",
                        int(older_than.total_seconds()),
                        limit,
                    ),
                ).fetchall()
        except (psycopg.Error, PoolTimeout) as error:
            raise DatabaseUnavailableError("Idle-session query failed") from error
        return [
            IdleSession(
                pid=cast(int, row[0]),
                application_name=cast(str, row[1]),
                idle_for_seconds=cast(float, row[2]),
            )
            for row in rows
        ]

    def terminate(self, session: IdleSession) -> bool:
        try:
            with self._database.connection() as connection:
                row = connection.execute(
                    "SELECT pg_terminate_backend(%s)",
                    (session.pid,),
                ).fetchone()
        except (psycopg.Error, PoolTimeout) as error:
            raise DatabaseUnavailableError("Session termination failed") from error
        return bool(row and row[0] is True)

    def record(
        self,
        *,
        session: IdleSession,
        outcome: str,
    ) -> None:
        details = {
            "application_name": session.application_name,
            "idle_for_seconds": f"{session.idle_for_seconds:.3f}",
        }
        try:
            with self._database.connection() as connection:
                connection.execute(
                    """
                    INSERT INTO remediation_events (
                        action,
                        target_pid,
                        outcome,
                        details
                    )
                    VALUES ('terminate_idle_transaction', %s, %s, %s)
                    """,
                    (session.pid, outcome, Jsonb(details)),
                )
        except (psycopg.Error, PoolTimeout) as error:
            raise DatabaseUnavailableError("Remediation audit write failed") from error
