from prometheus_client import Counter, Gauge, Histogram

SUMMARY_REQUESTS = Counter(
    "reliability_lab_summary_requests_total",
    "Order-summary requests by selected source",
    ["source", "outcome"],
)
SUMMARY_DURATION = Histogram(
    "reliability_lab_summary_duration_seconds",
    "Order-summary request duration",
    ["source"],
)
DEPENDENCY_AVAILABLE = Gauge(
    "reliability_lab_dependency_available",
    "Whether a dependency probe succeeded",
    ["dependency"],
)
CACHE_CIRCUIT_TRANSITIONS = Counter(
    "reliability_lab_cache_circuit_transitions_total",
    "Cache circuit-breaker state transitions",
    ["state"],
)
REMEDIATIONS = Counter(
    "reliability_lab_remediations_total",
    "Bounded remediation actions",
    ["action", "outcome"],
)
POOL_CONNECTIONS = Gauge(
    "reliability_lab_pool_connections",
    "Psycopg pool connection statistics",
    ["state"],
)
