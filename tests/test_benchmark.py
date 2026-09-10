from typing import cast

import psycopg
import pytest

from app.benchmark import (
    INDEX_NAME,
    ExplainDocument,
    PlanNode,
    apply_index,
    measure,
    measurement_from_explains,
    positive,
    prepare_data,
    query_result,
)


def explain(execution_ms: float, planning_ms: float) -> ExplainDocument:
    return ExplainDocument(
        **{
            "Planning Time": planning_ms,
            "Execution Time": execution_ms,
            "Plan": {
                "Node Type": "Aggregate",
                "Shared Hit Blocks": 4,
                "Shared Read Blocks": 1,
                "Plans": [
                    {
                        "Node Type": "Index Only Scan",
                        "Actual Rows": 12,
                        "Shared Hit Blocks": 3,
                        "Shared Read Blocks": 2,
                    }
                ],
            },
        }
    )


def test_measurement_uses_medians_and_recursive_plan_details() -> None:
    measurement = measurement_from_explains(
        [
            explain(10, 2),
            explain(2, 1),
            explain(5, 3),
        ]
    )

    assert measurement.median_ms == 5
    assert measurement.planning_median_ms == 2
    assert measurement.plan_nodes == ["Aggregate", "Index Only Scan"]
    assert measurement.shared_hit_blocks == 7
    assert measurement.shared_read_blocks == 3


def test_measurement_requires_samples() -> None:
    with pytest.raises(ValueError, match="At least one"):
        measurement_from_explains([])


def test_positive_rejects_invalid_experiment_sizes() -> None:
    assert positive(1, "rows") == 1

    with pytest.raises(ValueError, match="rows must be positive"):
        positive(0, "rows")


def test_plan_node_flattens_nested_nodes() -> None:
    plan = PlanNode(
        **{
            "Node Type": "Aggregate",
            "Plans": [
                {
                    "Node Type": "Bitmap Heap Scan",
                    "Plans": [{"Node Type": "Bitmap Index Scan"}],
                }
            ],
        }
    )

    assert plan.node_types() == [
        "Aggregate",
        "Bitmap Heap Scan",
        "Bitmap Index Scan",
    ]


class FakeCursor:
    def __init__(self, row: tuple[object, ...] | None) -> None:
        self._row = row

    def fetchone(self) -> tuple[object, ...] | None:
        return self._row


class FakeConnection:
    def __init__(self, rows: list[tuple[object, ...] | None] | None = None) -> None:
        self.rows = rows or []
        self.queries: list[tuple[str, tuple[object, ...] | None]] = []

    def execute(
        self,
        query: str,
        parameters: tuple[object, ...] | None = None,
    ) -> FakeCursor:
        self.queries.append((query, parameters))
        row = self.rows.pop(0) if self.rows else None
        return FakeCursor(row)


def benchmark_connection(
    connection: FakeConnection,
) -> psycopg.Connection[tuple[object, ...]]:
    return cast(psycopg.Connection[tuple[object, ...]], connection)


def test_prepare_data_escapes_modulo_operators_and_applies_index() -> None:
    connection = FakeConnection()
    typed_connection = benchmark_connection(connection)

    prepare_data(typed_connection, 250)
    apply_index(typed_connection)

    assert connection.queries[0][0] == f"DROP INDEX IF EXISTS {INDEX_NAME}"
    assert "series %% 200" in connection.queries[2][0]
    assert connection.queries[2][1] == (250,)
    assert f"CREATE INDEX {INDEX_NAME}" in connection.queries[4][0]


def test_query_result_maps_aggregate_and_requires_a_row() -> None:
    connection = FakeConnection([(12, 5000), None])
    typed_connection = benchmark_connection(connection)

    assert query_result(typed_connection, (42, "completed", 30)).model_dump() == {
        "order_count": 12,
        "total_cents": 5000,
    }
    with pytest.raises(RuntimeError, match="Aggregate query returned no row"):
        query_result(typed_connection, (42, "completed", 30))


def test_measure_decodes_measured_explain_plans() -> None:
    plan = [
        explain(3, 1).model_dump(by_alias=True),
    ]
    connection = FakeConnection(
        [
            (plan,),
            (plan,),
            (plan,),
        ]
    )

    measurement = measure(
        benchmark_connection(connection),
        (42, "completed", 30),
        warmups=1,
        iterations=2,
    )

    assert measurement.samples_ms == [3, 3]
    assert len(connection.queries) == 3


def test_measure_requires_explain_row() -> None:
    connection = FakeConnection([None])

    with pytest.raises(RuntimeError, match="EXPLAIN returned no row"):
        measure(
            benchmark_connection(connection),
            (42, "completed", 30),
            warmups=0,
            iterations=1,
        )
