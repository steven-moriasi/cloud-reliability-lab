# Roadmap

## Next evidence

- add a concurrent load harness with cache-warm, cache-cold, and cache-outage profiles;
- measure pool wait, database saturation, tail latency, and error budget consumption;
- benchmark index write/storage cost and skewed tenant distributions;
- add explicit stale age to API responses and metrics;
- exercise cache breaker recovery under concurrent half-open requests;
- add PostgreSQL lock, statement-timeout, and connection-exhaustion experiments;
- validate backup schema, representative values, indexes, and application smoke behavior;
- measure restore duration and retain a machine-readable recovery report;
- make readiness capacity-aware under pool and dependency saturation;
- verify point-in-time recovery and cross-version restores.

## Production architecture

- add reviewed Terraform or AWS CDK for private networking, ECS, RDS Proxy/RDS, ElastiCache, IAM,
  secrets, telemetry, alarms, and backup;
- add deployment health, rollback, graceful drain, and migration workflows;
- implement application-level admission control and request coalescing;
- replace process-local fallback with an approved stale-data design;
- add cross-replica circuit and dependency-state considerations;
- test managed-service failover and availability-zone impairment;
- use workload identity and least-privilege authorization for remediation.

## Governance

- define SLOs, error-budget policy, stale-data authorization, RPO, and RTO;
- assign owners for alerts, remediation, index changes, and recovery exercises;
- require dry-run and approval modes for destructive automation;
- add data classification, retention, privacy, and incident-evidence rules;
- record experiment revisions and host characteristics with benchmark artifacts.

Roadmap items are intentionally not described as delivered.
