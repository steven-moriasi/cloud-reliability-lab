# Experiment Catalog

Every experiment states a hypothesis, controlled change, observation, and limitation. Results vary
by host, container runtime, PostgreSQL state, and concurrent workload.

## Query plan and covering index

**Hypothesis:** the filtered tenant/status/time-window aggregate can avoid scanning the complete
orders table when a matching covering index exists.

**Method:**

1. Drop the candidate index.
2. Truncate the table and generate a deterministic row set.
3. warm the query;
4. collect measured `EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON)` plans;
5. create the candidate index and run `ANALYZE`;
6. warm and measure the same query;
7. require the aggregate result to be identical.

```bash
docker compose run --rm tools -m app.benchmark \
  --rows 250000 --iterations 7 --warmups 2 \
  --output /tmp/query-index-benchmark.json
```

**Observed local run:**

| Property | Baseline | Indexed |
| --- | --- | --- |
| median execution | 6.599 ms | 0.042 ms |
| plan nodes | aggregate, gather, aggregate, sequential scan | aggregate, index-only scan |
| shared hit blocks | 8,336 | 10 |
| shared read blocks | 0 | 0 |
| aggregate count | 102 | 102 |
| aggregate cents | 2,633,934 | 2,633,934 |

The measured ratio was 157.1 times for this warm-cache synthetic run. It cannot be extrapolated to
production cardinality, write amplification, index maintenance cost, cold storage, concurrency, or
different tenant distributions.

## Cache read-through and source visibility

**Hypothesis:** the first summary read is sourced from PostgreSQL and a repeated read is sourced
from Redis.

```bash
curl http://localhost:8003/api/tenants/42/orders/summary
curl http://localhost:8003/api/tenants/42/orders/summary
```

Inspect the `source` field. Restart the API and flush Redis before a clean repeat if prior requests
have populated either cache.

## Cache outage

**Hypothesis:** Redis failure degrades latency and database load but does not make the read API
unavailable while PostgreSQL remains healthy.

```bash
docker compose run --rm tools -m app.network_faults cache down
curl http://localhost:8003/ready
curl http://localhost:8003/api/tenants/42/orders/summary
docker compose run --rm tools -m app.network_faults cache up
```

Expected observations are `degraded` readiness and a `database` response source. This does not
validate PostgreSQL capacity under a fleet-wide cache outage.

## Dual dependency outage and bounded stale data

**Hypothesis:** a previously successful database read can be served from process-local stale memory
for a finite interval when both dependencies fail.

Populate tenant 42, disable both proxies, then compare tenant 42 with an uncached tenant:

```bash
curl http://localhost:8003/api/tenants/42/orders/summary
docker compose run --rm tools -m app.network_faults cache down
docker compose run --rm tools -m app.network_faults database down
curl --include http://localhost:8003/api/tenants/42/orders/summary
curl --include http://localhost:8003/api/tenants/43/orders/summary
```

Tenant 42 should report `source=stale` and a `Warning` header. Tenant 43 should return `503`.
After the stale window expires, tenant 42 also returns `503`.

Always restore both proxies after the experiment.

## Dependency latency

**Hypothesis:** the configured query and pool timeouts bound waiting when a dependency becomes slow.

```bash
docker compose run --rm tools -m app.network_faults database latency \
  --latency-ms 2500 --jitter-ms 0
time curl --include http://localhost:8003/api/tenants/44/orders/summary
docker compose run --rm tools -m app.network_faults database clear-latency
```

The injected latency is a network condition, not a database workload. Repeat with cache latency and
inspect request-duration metrics and circuit transitions.

## Idle-transaction remediation

**Hypothesis:** a deliberately tagged session that stays idle in a transaction past the threshold
is terminated and audited, while untagged sessions are out of scope.

For a short experiment, start Compose with:

```bash
RELIABILITY_LAB_IDLE_TRANSACTION_SECONDS=5 \
RELIABILITY_LAB_REMEDIATION_INTERVAL_SECONDS=2 \
docker compose up -d --build --wait
docker compose run --rm tools -m app.faults idle-transaction --seconds 30
```

The fault command should report termination. Query `remediation_events` and the remediation metrics
endpoint. Unit tests separately verify that untagged candidates are rejected by the controller.

## Backup and restore

**Hypothesis:** a custom-format PostgreSQL dump can be restored into an isolated database and
preserve the order count.

```bash
./scripts/backup.sh
./scripts/restore_verify.sh
```

The checksum detects local artifact corruption before restore. Row-count equality is intentionally
basic: it does not verify every value, indexes, permissions, extensions, point-in-time recovery,
cross-version compatibility, recovery duration, or off-site durability.
