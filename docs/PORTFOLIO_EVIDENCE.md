# Portfolio Evidence

## Evidence map

| Capability claim | Inspectable evidence | Verification |
| --- | --- | --- |
| PostgreSQL query optimization | deterministic benchmark, JSON plans, covering index | equal aggregate assertion and measured plan report |
| database connection management | bounded psycopg pool, checkout timeout, statement timeout | typed adapter tests and pool metrics |
| caching and degraded operation | Redis read-through cache, circuit breaker, stale-if-error path | cache, database fallback, and stale-response tests |
| failure injection | Toxiproxy proxy setup and fault CLI | live cache/database outage sequence |
| self-healing boundary | tagged idle-transaction agent with termination cap | controller/backend tests and audited live termination |
| health and monitoring | liveness, dependency-aware readiness, Prometheus metrics | API tests and live endpoint checks |
| backup and recovery | custom-format dump and isolated restore scripts | 250,000-row restore count verification |
| Docker engineering | multi-stage non-root image and health-checked Compose stack | image build and healthy live services |
| AWS architecture | service mapping, IAM, capacity, recovery, and telemetry controls | documented design only; no deployment claim |
| technical leadership | ADRs, failure model, experiment method, review, and roadmap | repository review artifacts |

## Measured local evidence

The reviewed local run used PostgreSQL 17.5 in Docker and 250,000 generated orders:

- baseline median: 6.599 ms, ending in a sequential scan;
- indexed median: 0.042 ms, ending in an index-only scan;
- aggregate result unchanged: 102 rows and 2,633,934 cents;
- shared hit blocks changed from 8,336 to 10;
- reported median ratio: 157.1 times for that synthetic warm-cache run.

The same live stack demonstrated:

- database response followed by Redis cache hit;
- PostgreSQL fallback during a Redis outage;
- labeled stale response during a dual dependency outage;
- `503` for an uncached tenant during the dual outage;
- unavailable readiness while PostgreSQL was down;
- recovery after both proxies were re-enabled;
- termination and audit of one deliberately tagged idle transaction;
- backup and isolated restore count equality for 250,000 rows.

These observations are reproducible lab evidence, not production service-level results.

## Honest limitations

- no AWS resources were deployed;
- no production traffic, data distribution, concurrency, or cold-storage benchmark was used;
- no multi-replica stale-cache consistency is implemented;
- no PostgreSQL or Redis failover was exercised;
- no formal RPO, RTO, load capacity, or availability target was validated;
- remediation ownership uses a lab-only application-name prefix;
- GitHub Actions status is separate from local verification and must be checked after publication.

## Review path

A reviewer can inspect the repository in this order:

1. README for the claims and commands;
2. architecture and failure model for boundaries;
3. benchmark implementation and experiment catalog for evidence quality;
4. resilience service and cache breaker for degradation semantics;
5. remediation adapter/controller for blast-radius controls;
6. backup/restore scripts and runbook;
7. tests and CI workflow;
8. Principal Engineer review and roadmap for unresolved risk.
