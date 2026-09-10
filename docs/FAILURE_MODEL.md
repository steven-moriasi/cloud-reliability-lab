# Failure Model

## Explicit behavior

| Condition | Detection | Request behavior | Readiness | Recovery |
| --- | --- | --- | --- | --- |
| Redis unavailable | cache exception/probe | PostgreSQL fallback | 200 degraded | circuit probe and Redis recovery |
| PostgreSQL unavailable, cached Redis hit | cache hit | fresh cached response | 503 unavailable | database recovery |
| PostgreSQL unavailable, bounded stale hit | database exception | labeled stale response | 503 unavailable | database recovery or stale expiry |
| PostgreSQL unavailable, no stale value | database exception | generic 503 | 503 unavailable | database recovery |
| Redis repeatedly failing | breaker threshold | Redis calls fail fast | dependent on PostgreSQL | half-open probe |
| query exceeds statement timeout | PostgreSQL cancellation | stale or generic 503 | probe-dependent | workload/index/config correction |
| pool checkout exceeds timeout | pool exception | stale or generic 503 | probe-dependent | reduce load or restore capacity |
| tagged idle transaction | PostgreSQL activity view | no direct API effect | unchanged | bounded termination and audit |
| remediation agent unavailable | container health | no remediation | API unchanged | restart agent and inspect backlog |
| API restart | process lifecycle | temporary unavailability | removed until ready | restart; local stale data is lost |

## Cascading-failure risks

### Cache outage amplifies database load

Failing open to PostgreSQL preserves correctness but can overwhelm it. The lab makes this policy
visible but does not implement fleet-wide concurrency limits, request coalescing, load shedding, or
adaptive admission control.

### Retry amplification

The service does not perform application retries around summary reads. This avoids hidden
amplification, but upstream clients and infrastructure could still retry. A production contract
must define retry ownership, budgets, jitter, and idempotency.

### Pool multiplication

The configured pool maximum applies to one process. Replica and worker counts multiply the possible
database connections. Exceeding PostgreSQL capacity may make readiness probes and remediation
compete with customer traffic.

### Stale inconsistency

Stale values are process-local. Two replicas can return values generated at different times. Stale
responses are bounded and labeled, but there is no globally consistent staleness timestamp or
invalidation channel.

### Remediation false positives

An application-name prefix is an intentionally narrow lab control, not an identity boundary.
Production remediation should require stronger ownership signals, dry-run evidence, authorization,
change control, rate limits, and escalation.

## Unmodeled failures

- PostgreSQL primary failover and connection re-resolution
- Redis cluster failover and partial shard loss
- DNS, certificate, credential, and secret-rotation failures
- disk saturation, transaction-ID pressure, replication lag, and vacuum starvation
- CPU or memory pressure in the API
- multi-availability-zone network partitions
- schema migration incompatibility
- clock skew affecting stale windows
- telemetry pipeline loss
- backup encryption, retention, and off-site recovery

These gaps are documented rather than represented as solved.
