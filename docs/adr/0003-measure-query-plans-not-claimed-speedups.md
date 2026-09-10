# ADR 0003: Measure Query Plans Instead of Claiming General Speedups

## Status

Accepted.

## Context

Performance claims are easy to overstate when data, caches, hardware, query plans, and sample counts
are not disclosed.

## Decision

The benchmark generates deterministic data, removes the candidate index, warms and measures the
baseline, creates one covering index, warms and measures the indexed query, and verifies identical
aggregate results. Reports include sample timings, medians, plan nodes, buffer counts, row count,
query parameters, PostgreSQL version, and generation time.

Documentation may cite a measured local run only with its data size and limitations. It must not
convert the measured ratio into a production forecast, availability claim, or CV-wide percentage.

## Consequences

- reviewers can reproduce and challenge the result;
- plan shape and work reduction are visible, not just wall-clock time;
- the benchmark takes longer than a single query screenshot;
- warm synthetic measurements still omit write cost, concurrency, skew, storage, and production
  infrastructure;
- future changes should retain machine-readable reports and compare equal query results.
