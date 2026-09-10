import argparse
import json
import statistics
from datetime import UTC, datetime
from pathlib import Path
from typing import cast

import psycopg
from pydantic import BaseModel, ConfigDict, Field, RootModel

from app.core.config import get_settings

INDEX_NAME = "orders_tenant_status_created_idx"
QUERY = """
    SELECT COUNT(*)::bigint, COALESCE(SUM(total_cents), 0)::bigint
    FROM orders
    WHERE tenant_id = %s
      AND status = %s
      AND created_at >= now() - make_interval(days => %s)
"""
EXPLAIN_QUERY = f"EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) {QUERY}"


class PlanNode(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    node_type: str = Field(alias="Node Type")
    actual_rows: float = Field(default=0, alias="Actual Rows")
    shared_hit_blocks: int = Field(default=0, alias="Shared Hit Blocks")
    shared_read_blocks: int = Field(default=0, alias="Shared Read Blocks")
    plans: list["PlanNode"] = Field(default_factory=list, alias="Plans")

    def node_types(self) -> list[str]:
        return [self.node_type, *(node for plan in self.plans for node in plan.node_types())]

    def buffer_totals(self) -> tuple[int, int]:
        child_totals = [plan.buffer_totals() for plan in self.plans]
        return (
            self.shared_hit_blocks + sum(total[0] for total in child_totals),
            self.shared_read_blocks + sum(total[1] for total in child_totals),
        )


class ExplainDocument(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    plan: PlanNode = Field(alias="Plan")
    planning_time_ms: float = Field(alias="Planning Time")
    execution_time_ms: float = Field(alias="Execution Time")


class ExplainResult(RootModel[list[ExplainDocument]]):
    pass


class QueryResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    order_count: int
    total_cents: int


class Measurement(BaseModel):
    model_config = ConfigDict(frozen=True)

    samples_ms: list[float]
    median_ms: float
    planning_median_ms: float
    plan_nodes: list[str]
    shared_hit_blocks: int
    shared_read_blocks: int


class BenchmarkReport(BaseModel):
    model_config = ConfigDict(frozen=True)

    generated_at: datetime
    postgres_version: str
    rows_loaded: int
    tenant_id: int
    status: str
    window_days: int
    result: QueryResult
    baseline: Measurement
    indexed: Measurement
    median_speedup: float


def _decode_explain(value: object) -> ExplainDocument:
    encoded = json.dumps(value)
    parsed = ExplainResult.model_validate_json(encoded)
    if len(parsed.root) != 1:
        raise ValueError("Unexpected EXPLAIN response")
    return parsed.root[0]


def measurement_from_explains(explains: list[ExplainDocument]) -> Measurement:
    if not explains:
        raise ValueError("At least one measured plan is required")
    execution_times = [result.execution_time_ms for result in explains]
    planning_times = [result.planning_time_ms for result in explains]
    final_plan = explains[-1].plan
    shared_hit_blocks, shared_read_blocks = final_plan.buffer_totals()
    return Measurement(
        samples_ms=execution_times,
        median_ms=statistics.median(execution_times),
        planning_median_ms=statistics.median(planning_times),
        plan_nodes=final_plan.node_types(),
        shared_hit_blocks=shared_hit_blocks,
        shared_read_blocks=shared_read_blocks,
    )


def prepare_data(connection: psycopg.Connection[tuple[object, ...]], rows: int) -> None:
    connection.execute(f"DROP INDEX IF EXISTS {INDEX_NAME}")
    connection.execute("TRUNCATE orders RESTART IDENTITY")
    connection.execute(
        """
        INSERT INTO orders (tenant_id, status, created_at, total_cents)
        SELECT
            (series %% 200) + 1,
            CASE
                WHEN series %% 10 < 7 THEN 'completed'
                WHEN series %% 10 < 9 THEN 'pending'
                ELSE 'failed'
            END,
            now()
                - ((series %% 365) * interval '1 day')
                - ((series %% 86400) * interval '1 second'),
            (series * 37) %% 50000
        FROM generate_series(1, %s) AS series
        """,
        (rows,),
    )
    connection.execute("VACUUM (ANALYZE) orders")


def apply_index(connection: psycopg.Connection[tuple[object, ...]]) -> None:
    connection.execute(
        f"""
        CREATE INDEX {INDEX_NAME}
        ON orders (tenant_id, status, created_at)
        INCLUDE (total_cents)
        """
    )
    connection.execute("VACUUM (ANALYZE) orders")


def query_result(
    connection: psycopg.Connection[tuple[object, ...]],
    parameters: tuple[int, str, int],
) -> QueryResult:
    row = connection.execute(QUERY, parameters).fetchone()
    if row is None:
        raise RuntimeError("Aggregate query returned no row")
    return QueryResult(
        order_count=cast(int, row[0]),
        total_cents=cast(int, row[1]),
    )


def measure(
    connection: psycopg.Connection[tuple[object, ...]],
    parameters: tuple[int, str, int],
    *,
    warmups: int,
    iterations: int,
) -> Measurement:
    for _ in range(warmups):
        connection.execute(EXPLAIN_QUERY, parameters).fetchone()
    explains: list[ExplainDocument] = []
    for _ in range(iterations):
        row = connection.execute(EXPLAIN_QUERY, parameters).fetchone()
        if row is None:
            raise RuntimeError("EXPLAIN returned no row")
        explains.append(_decode_explain(row[0]))
    return measurement_from_explains(explains)


def run_experiment(
    database_url: str,
    *,
    rows: int,
    tenant_id: int,
    status: str,
    window_days: int,
    warmups: int,
    iterations: int,
) -> BenchmarkReport:
    parameters = (tenant_id, status, window_days)
    with psycopg.connect(database_url, autocommit=True) as connection:
        prepare_data(connection, rows)
        expected = query_result(connection, parameters)
        baseline = measure(
            connection,
            parameters,
            warmups=warmups,
            iterations=iterations,
        )
        apply_index(connection)
        actual = query_result(connection, parameters)
        if actual != expected:
            raise RuntimeError("Index changed the aggregate result")
        indexed = measure(
            connection,
            parameters,
            warmups=warmups,
            iterations=iterations,
        )
        version_row = connection.execute("SHOW server_version").fetchone()
    if version_row is None:
        raise RuntimeError("PostgreSQL did not return its version")
    indexed_median = max(indexed.median_ms, 0.000001)
    return BenchmarkReport(
        generated_at=datetime.now(UTC),
        postgres_version=cast(str, version_row[0]),
        rows_loaded=rows,
        tenant_id=tenant_id,
        status=status,
        window_days=window_days,
        result=expected,
        baseline=baseline,
        indexed=indexed,
        median_speedup=baseline.median_ms / indexed_median,
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run a measured PostgreSQL indexing experiment"
    )
    parser.add_argument("--rows", type=int, default=250_000)
    parser.add_argument("--tenant-id", type=int, default=42)
    parser.add_argument("--status", choices=["pending", "completed", "failed"], default="completed")
    parser.add_argument("--window-days", type=int, default=30)
    parser.add_argument("--warmups", type=int, default=2)
    parser.add_argument("--iterations", type=int, default=7)
    parser.add_argument(
        "--output",
        type=Path,
        default=Path(".artifacts/query-index-benchmark.json"),
    )
    return parser.parse_args()


def positive(value: int, name: str) -> int:
    if value < 1:
        raise ValueError(f"{name} must be positive")
    return value


def main() -> None:
    args = parse_args()
    report = run_experiment(
        get_settings().database_url,
        rows=positive(args.rows, "rows"),
        tenant_id=positive(args.tenant_id, "tenant-id"),
        status=args.status,
        window_days=positive(args.window_days, "window-days"),
        warmups=positive(args.warmups, "warmups"),
        iterations=positive(args.iterations, "iterations"),
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(report.model_dump_json(indent=2), encoding="utf-8")
    print(report.model_dump_json(indent=2))


if __name__ == "__main__":
    main()
