from dataclasses import dataclass, field
from datetime import timedelta

from app.infrastructure.remediation import IdleSession
from app.remediation import RemediationController


@dataclass
class FakeBackend:
    sessions: list[IdleSession]
    termination_outcomes: dict[int, bool] = field(default_factory=dict)
    requested_prefix: str | None = None
    requested_age: timedelta | None = None
    requested_limit: int | None = None
    terminated: list[int] = field(default_factory=list)
    records: list[tuple[int, str]] = field(default_factory=list)

    def find_idle_sessions(
        self,
        *,
        application_prefix: str,
        older_than: timedelta,
        limit: int,
    ) -> list[IdleSession]:
        self.requested_prefix = application_prefix
        self.requested_age = older_than
        self.requested_limit = limit
        return self.sessions

    def terminate(self, session: IdleSession) -> bool:
        self.terminated.append(session.pid)
        return self.termination_outcomes.get(session.pid, True)

    def record(self, *, session: IdleSession, outcome: str) -> None:
        self.records.append((session.pid, outcome))


def test_remediation_is_scoped_and_bounded() -> None:
    backend = FakeBackend(
        sessions=[
            IdleSession(1, "reliability-lab-fault-first", 90),
            IdleSession(2, "unrelated-service", 80),
            IdleSession(3, "reliability-lab-fault-third", 70),
        ]
    )
    controller = RemediationController(
        backend,
        application_prefix="reliability-lab-fault-",
        idle_transaction_seconds=30,
        max_terminations=2,
    )

    result = controller.run_once()

    assert result.inspected == 3
    assert result.terminated == 1
    assert backend.terminated == [1]
    assert backend.records == [(1, "terminated")]
    assert backend.requested_prefix == "reliability-lab-fault-"
    assert backend.requested_age == timedelta(seconds=30)
    assert backend.requested_limit == 2


def test_failed_termination_is_audited() -> None:
    backend = FakeBackend(
        sessions=[IdleSession(4, "reliability-lab-fault-fourth", 60)],
        termination_outcomes={4: False},
    )
    controller = RemediationController(
        backend,
        application_prefix="reliability-lab-fault-",
        idle_transaction_seconds=30,
        max_terminations=2,
    )

    result = controller.run_once()

    assert result.terminated == 0
    assert backend.records == [(4, "not_terminated")]
