# Operations Runbook

## Start and inspect

```bash
cp .env.example .env
docker compose up -d --build --wait
docker compose ps
curl --fail http://localhost:8003/health
curl --fail http://localhost:8003/ready
```

Use `docker compose logs --tail=200 api remediation db cache toxiproxy` for sanitized service logs.
Do not attach production dumps, connection strings, or customer query text to incidents.

## Readiness degraded

If `/ready` returns `200 degraded`:

1. inspect Redis and Toxiproxy health;
2. check cache dependency and circuit-transition metrics;
3. restore the cache proxy if an experiment left it disabled;
4. monitor database pool occupancy and request duration;
5. reduce traffic or stop the experiment if database load rises.

```bash
docker compose run --rm tools -m app.network_faults cache up
docker compose run --rm tools -m app.network_faults cache clear-latency
```

## Readiness unavailable

If `/ready` returns `503`:

1. stop new fault injection;
2. restore the database proxy;
3. inspect PostgreSQL health and API pool metrics;
4. check whether uncached requests return `503` and whether any stale responses are labeled;
5. verify recovery with a tenant that was not previously cached.

```bash
docker compose run --rm tools -m app.network_faults database up
docker compose run --rm tools -m app.network_faults database clear-latency
curl --include http://localhost:8003/api/tenants/43/orders/summary
```

Do not extend the stale window during an incident without an explicit business decision about
serving older data.

## Cache circuit open

The circuit opens after the configured consecutive failure threshold. During the recovery interval,
Redis operations fail fast. One half-open probe is then allowed.

Investigate the dependency rather than repeatedly restarting the API. An API restart resets the
process-local breaker and stale cache, which can increase load and remove fallback data.

## Pool pressure

Inspect:

```bash
curl --silent http://localhost:8003/metrics |
  grep reliability_lab_pool_connections
```

If waiting approaches the maximum:

1. identify query-duration changes and PostgreSQL saturation;
2. stop artificial latency;
3. reduce request concurrency;
4. inspect active and idle-in-transaction sessions;
5. change pool sizes only after calculating fleet-wide connection limits.

Increasing the pool can shift failure into PostgreSQL rather than resolve it.

## Remediation agent

Inspect agent health and outcomes:

```bash
curl --fail http://localhost:9103/metrics
docker compose logs --tail=100 remediation
docker compose exec db psql -U reliability -d reliability \
  -c "SELECT occurred_at, action, target_pid, outcome, details
      FROM remediation_events ORDER BY id DESC LIMIT 20"
```

If an unexpected session appears in the audit log, stop the agent and preserve the evidence:

```bash
docker compose stop remediation
```

Do not broaden the prefix or remove the per-cycle limit as an incident shortcut.

## Backup and restore

Create and checksum a dump:

```bash
./scripts/backup.sh
sha256sum --check .artifacts/reliability.dump.sha256
```

Verify an isolated restore:

```bash
./scripts/restore_verify.sh
```

A successful count comparison is not an RPO/RTO test. Record artifact size, runtime, PostgreSQL
version, schema verification, and application smoke checks for a formal recovery exercise.

## Return the lab to a known state

```bash
docker compose run --rm tools -m app.network_faults database up
docker compose run --rm tools -m app.network_faults cache up
docker compose run --rm tools -m app.network_faults database clear-latency
docker compose run --rm tools -m app.network_faults cache clear-latency
docker compose restart api remediation
docker compose ps
```

To remove generated data and volumes:

```bash
docker compose down --volumes
```

That command is destructive to local lab data.
