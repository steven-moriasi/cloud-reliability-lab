# Contributing

## Development checks

Use Python 3.12:

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev]"
ruff check app tests
mypy app tests
pytest --cov=app --cov-report=term-missing --cov-fail-under=80
docker compose config --quiet
docker build .
```

Changes to query shape, indexes, pool limits, cache fallback, health semantics, remediation scope,
backup/restore behavior, or fault injection require focused tests and an update to the relevant
experiment, runbook, failure model, or ADR.

Do not commit production connection strings, dumps, telemetry, credentials, customer data, or
benchmark claims that cannot be reproduced. Local fixture credentials and generated data must
remain clearly synthetic.

## Reliability review checklist

- PostgreSQL remains the authoritative data source.
- Stale responses remain bounded and explicitly labeled.
- Dependency errors remain generic at the HTTP boundary.
- Pools, timeouts, circuit thresholds, and remediation batches remain bounded.
- Remediation cannot target untagged sessions.
- Benchmarks compare equal results and disclose data size and sample count.
- Restore verification uses an isolated database and cleans it up.
- Metrics do not contain tenant identifiers, SQL text, or credentials.
