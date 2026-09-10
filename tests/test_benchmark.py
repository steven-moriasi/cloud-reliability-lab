import pytest

from app.benchmark import (
    ExplainDocument,
    PlanNode,
    measurement_from_explains,
    positive,
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
