# Principal Engineer Review

## Verdict

The repository is credible as a local reliability engineering lab. Its strongest quality is that it
turns broad claims into controlled, inspectable experiments and labels the boundaries of the
evidence. It should not be presented as a production-ready cloud platform.

## Strengths

### Evidence over assertion

The query experiment controls data generation, records plans and buffers, changes one index, and
requires result equality. The README discloses sample size and environment dependence rather than
promoting a universal speedup.

### Explicit degradation semantics

Redis failure, PostgreSQL failure, dual failure, and missing stale data have distinct observable
outcomes. The response identifies its source and stale data is bounded and labeled.

### Bounded resources

Pool size, pool checkout, query execution, cache thresholds, stale lifetime, remediation age, and
termination count all have explicit finite limits.

### Narrow remediation

The agent is a separate process, connects through a separate path, filters candidates in SQL,
rechecks scope in the controller, caps each cycle, exports metrics, and writes an audit event.

### Operational honesty

The failure model, AWS mapping, restore caveats, and roadmap state what is not implemented. Local
credentials and generated data are not represented as production controls.

## Risks and design questions

### Cache outage capacity

Fallback to PostgreSQL is correct for data authority but may create a cache-miss storm. Before
production, add admission control, request coalescing, per-tenant limits, and a load test that proves
the database can absorb the selected degraded mode.

### Stale consistency

Process-local stale memory is simple and failure-independent, but replicas can diverge and restarts
erase fallback data. A production design needs a business-defined stale contract, timestamp
visibility, and a decision between shared cache, durable snapshot, or fail-closed behavior.

### Readiness policy

Returning ready while Redis is unavailable keeps capacity in service but can route more traffic to
PostgreSQL. This should be tied to database saturation and potentially changed dynamically rather
than treated as a permanent boolean policy.

### Remediation identity

`application_name` is useful for a safe demo but is not strong authorization. A production
automation path needs stronger workload ownership, dry-run review, permissions separated from the
API, and evidence that termination is safer than cancellation, timeout, or traffic shedding.

### Benchmark scope

The index is compelling for the generated distribution and read query. Missing evidence includes
write overhead, storage growth, cold reads, concurrent load, skew, vacuum effects, and a migration
plan for creating or removing the index under traffic.

### Recovery depth

The restore script validates tooling and one row-count invariant. It does not establish point-in-
time recovery, object integrity, permissions, extensions, cross-version compatibility, or elapsed
recovery objectives.

## Production-entry criteria

Before approving a production pilot:

1. define SLOs, stale-data policy, RPO, and RTO;
2. add load and soak evidence including cache-loss traffic;
3. provision private AWS infrastructure through reviewed IaC;
4. implement least-privilege identities and secret rotation;
5. test PostgreSQL, Redis, task, and availability-zone failover;
6. implement shared telemetry, alerting, and on-call ownership;
7. complete a measured isolated recovery exercise;
8. replace or formally approve termination remediation with stronger ownership controls;
9. run security, privacy, and data-retention reviews.

## Portfolio assessment

For a Principal Engineer portfolio, the repository demonstrates useful judgment: authority versus
optimization, availability versus staleness, automation versus blast radius, and performance
measurement versus marketing. The documented unresolved risks are part of the evidence, not a
weakness to hide.
