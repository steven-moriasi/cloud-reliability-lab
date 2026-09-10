# ADR 0002: Scope Idle-Transaction Remediation to Lab Fault Sessions

## Status

Accepted for the lab; not approved as a production policy.

## Context

Idle transactions can retain locks and prevent cleanup. Automated termination demonstrates
detection and remediation, but unrestricted backend termination has an unacceptable blast radius.

## Decision

The agent may consider only client backends in the current database whose state is
`idle in transaction`, age exceeds a configured threshold, and `application_name` begins with the
lab fault prefix. The backend query and controller both enforce the prefix. Each cycle has a
termination maximum and every attempt is audited.

The API does not receive remediation privileges. The remediation agent connects directly to the
database so dependency fault experiments cannot silently disable the control path.

## Consequences

- live remediation can be demonstrated without targeting normal sessions;
- mistakes are bounded by age, prefix, database, backend type, and cycle count;
- the application-name prefix is convention-based rather than strong identity;
- the agent still requires a capability capable of disrupting database sessions;
- production adoption requires stronger ownership, approval, dry-run, escalation, and rollback
  controls.
