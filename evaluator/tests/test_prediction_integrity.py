"""Adversarial checks that prevent inflated evaluation claims."""

from __future__ import annotations

from datetime import date

import pytest
from pydantic import ValidationError

from evaluator.metrics import compute_all_metrics
from evaluator.schemas import PredictedCase, PredictedEdge, PredictionReport
from evaluator.validation import validate_evaluation_inputs
from generator.ground_truth import GroundTruthCase, GroundTruthEdge, GroundTruthManifest
from packages.domain.enums import CaseState, CashBucket


def _truth_case(case_id: str = "CASE_1") -> GroundTruthCase:
    return GroundTruthCase(
        case_id=case_id,
        scenario_id="scenario",
        scenario_label="integrity",
        expected_relationships=[
            GroundTruthEdge(
                source_entity_id="PAY_1",
                target_entity_id="SET_1",
                relationship_type="payment_settlement",
                allocated_amount_paise=10_000,
            )
        ],
        expected_case_state=CaseState.RECONCILED,
        expected_cash_bucket=CashBucket.BANK_CONFIRMED,
        expected_gross_amount_paise=10_000,
        expected_net_amount_paise=9_764,
        expected_residual_paise=0,
        source_entity_ids=["PAY_1", "SET_1"],
    )


def _prediction(case_id: str = "CASE_1", amount: int = 10_000) -> PredictedCase:
    return PredictedCase(
        case_id=case_id,
        predicted_relationships=[
            PredictedEdge(
                source_entity_id="PAY_1",
                target_entity_id="SET_1",
                relationship_type="payment_settlement",
                allocated_amount_paise=amount,
            )
        ],
        predicted_case_state=CaseState.RECONCILED,
        predicted_cash_bucket=CashBucket.BANK_CONFIRMED,
        predicted_gross_amount_paise=10_000,
        predicted_net_amount_paise=9_764,
        predicted_residual_paise=0,
    )


def _truth_manifest() -> GroundTruthManifest:
    return GroundTruthManifest(
        dataset_id="integrity-data",
        seed=1,
        generator_version="1",
        policy_version="1",
        date_range_start=date(2026, 1, 1),
        date_range_end=date(2026, 1, 1),
        scenario_counts={"integrity": 1},
        total_cases=1,
        total_source_records=2,
        file_checksums={},
        cases=[_truth_case()],
    )


def _report(cases: list[PredictedCase], total_source_records: int = 2) -> PredictionReport:
    return PredictionReport(
        dataset_id="integrity-data",
        run_id="run",
        duration_seconds=0.1,
        total_source_records=total_source_records,
        cases=cases,
    )


def test_wrong_allocated_amount_cannot_score_as_a_verified_match() -> None:
    metrics = compute_all_metrics([_prediction(amount=9_999)], [_truth_case()])

    assert metrics["relationship_precision"] == 0.0
    assert metrics["relationship_recall"] == 0.0
    assert metrics["relationship_topology_true_positive_count"] == 1
    assert metrics["false_positive_count"] == 1
    assert metrics["monetary_reconciliation_rate"] == 0.0


def test_unknown_reconciled_case_counts_as_false_positive() -> None:
    metrics = compute_all_metrics([_prediction(case_id="CASE_UNKNOWN")], [_truth_case()])

    assert metrics["false_positive_count"] == 1
    assert metrics["false_positive_amount_paise"] == 10_000
    assert metrics["missing_case_count"] == 1


def test_missing_case_stays_visible_in_safety_metrics() -> None:
    metrics = compute_all_metrics([], [_truth_case()])

    assert metrics["missing_case_count"] == 1
    assert metrics["relationship_precision"] == 0.0
    assert metrics["relationship_recall"] == 0.0


def test_duplicate_cases_and_edges_are_rejected_before_scoring() -> None:
    case = _prediction()
    with pytest.raises(ValidationError, match="duplicate case IDs"):
        _report([case, case])

    edge = case.predicted_relationships[0]
    with pytest.raises(ValidationError, match="duplicate relationship edges"):
        case.model_copy(update={"predicted_relationships": [edge, edge]}).model_validate(
            {
                **case.model_dump(mode="python"),
                "predicted_relationships": [
                    edge.model_dump(mode="python"),
                    edge.model_dump(mode="python"),
                ],
            }
        )


def test_dataset_and_source_totals_must_match_oracle() -> None:
    with pytest.raises(ValueError, match="source-record total mismatch"):
        validate_evaluation_inputs(
            _report([_prediction()], total_source_records=1), _truth_manifest()
        )

    wrong_dataset = _report([_prediction()]).model_copy(update={"dataset_id": "another"})
    with pytest.raises(ValueError, match="dataset ID mismatch"):
        validate_evaluation_inputs(wrong_dataset, _truth_manifest())
