# ADR 0001: Authoritative Database and Bounded Stale Fallback

## Status

Accepted for the lab.

## Context

The API should demonstrate useful behavior during Redis and PostgreSQL failures without hiding when
data is no longer fresh.

## Decision

PostgreSQL is authoritative. Redis is a read-through optimization. After a successful database
read, the process retains a bounded stale value. If PostgreSQL later fails, that value may be
returned only before its stale deadline and must be labeled in the body and `Warning` header.
Without a valid stale value, the API returns `503`.

## Consequences

- Redis loss does not compromise authority.
- A short PostgreSQL outage can preserve a previously read summary.
- replicas can hold different stale values;
- restarts erase stale values;
- the business must approve the stale window for a production system;
- PostgreSQL may receive substantially more load during Redis failure.

The lab accepts these limitations and does not represent the fallback as a production cache design.
