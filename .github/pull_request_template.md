## Summary

<!-- What changed and why? -->

## Reliability contract

<!-- Which query, index, pool, timeout, cache, fallback, remediation, recovery, or metric changes? -->

## Verification

- [ ] Ruff
- [ ] mypy
- [ ] affected experiment or fault test
- [ ] full test suite with coverage gate
- [ ] Docker or Compose validation, if runtime packaging changed
- [ ] backup/restore check, if persistence behavior changed

## Safety and evidence review

- [ ] PostgreSQL remains authoritative
- [ ] stale responses remain bounded and labeled
- [ ] pools, timeouts, circuit thresholds, and remediation batches remain bounded
- [ ] remediation cannot target untagged sessions
- [ ] benchmark results are reproducible and not generalized beyond the measured environment
- [ ] logs, metrics, fixtures, and artifacts contain no real secrets or customer data
- [ ] architecture, failure model, runbook, experiment catalog, or ADRs were updated
