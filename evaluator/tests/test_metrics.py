"""Tests for the evaluator metric functions."""

from __future__ import annotations

from evaluator.metrics import (
    case_state_accuracy,
    cash_bucket_accuracy,
    compute_all_metrics,
    exception_code_accuracy,
    false_positive_amount_paise,
    false_positive_count,
    hidden_row_count,
    open_exception_residual_paise,
    relationship_f1,
    relationship_precision,
    relationship_recall,
    stp_rate,
    unexplained_residual_paise,
)
from evaluator.schemas import PredictedCase, PredictedEdge
from generator.ground_truth import GroundTruthCase, GroundTruthEdge
from packages.domain.enums import CaseState, CashBucket, ExceptionCode

# ── Fixtures ───────────────────────────────────────────────────────────────


def _make_truth(
    case_id: str,
    state: CaseState,
    edges: list[tuple] | None = None,
) -> GroundTruthCase:
    gt_edges = [
        GroundTruthEdge(
            source_entity_id=s, target_entity_id=t, relationship_type=r, allocated_amount_paise=a
        )
        for s, t, r, a in (edges or [])
    ]
    return GroundTruthCase(
        case_id=case_id,
        scenario_id=f"sc_{case_id}",
        scenario_label="test",
        expected_relationships=gt_edges,
        expected_case_state=state,
        expected_exception_code=ExceptionCode.FEE_VARIANCE
        if state == CaseState.ACTIONABLE_EXCEPTION
        else None,
        expected_cash_bucket=CashBucket.BANK_CONFIRMED
        if state == CaseState.RECONCILED
        else CashBucket.AT_RISK,
        expected_gross_amount_paise=100000,
        expected_net_amount_paise=96000,
        expected_residual_paise=0 if state == CaseState.RECONCILED else 96000,
        source_entity_ids=["ORD_1", "PAY_1"],
    )


def _make_pred(case_id: str, state: CaseState, edges: list[tuple] | None = None) -> PredictedCase:
    pr_edges = [
        PredictedEdge(
            source_entity_id=s, target_entity_id=t, relationship_type=r, allocated_amount_paise=a
        )
        for s, t, r, a in (edges or [])
    ]
    return PredictedCase(
        case_id=case_id,
        predicted_relationships=pr_edges,
        predicted_case_state=state,
        predicted_exception_code=ExceptionCode.FEE_VARIANCE
        if state == CaseState.ACTIONABLE_EXCEPTION
        else None,
        predicted_cash_bucket=CashBucket.BANK_CONFIRMED
        if state == CaseState.RECONCILED
        else CashBucket.AT_RISK,
        predicted_gross_amount_paise=100000,
        predicted_net_amount_paise=96000,
        predicted_residual_paise=0 if state == CaseState.RECONCILED else 96000,
    )


EDGES_A = [("ORD_1", "PAY_1", "order_payment", 100000)]
EDGES_B = [("PAY_1", "SET_1", "payment_settlement", 96000)]


# ── Perfect prediction tests ──────────────────────────────────────────────


class TestPerfectPrediction:
    def test_precision_1(self):
        truth = [_make_truth("C1", CaseState.RECONCILED, EDGES_A)]
        pred = [_make_pred("C1", CaseState.RECONCILED, EDGES_A)]
        assert relationship_precision(pred, truth) == 1.0

    def test_recall_1(self):
        truth = [_make_truth("C1", CaseState.RECONCILED, EDGES_A)]
        pred = [_make_pred("C1", CaseState.RECONCILED, EDGES_A)]
        assert relationship_recall(pred, truth) == 1.0

    def test_f1_1(self):
        assert relationship_f1(1.0, 1.0) == 1.0

    def test_case_state_accuracy_1(self):
        truth = [_make_truth("C1", CaseState.RECONCILED)]
        pred = [_make_pred("C1", CaseState.RECONCILED)]
        assert case_state_accuracy(pred, truth) == 1.0

    def test_zero_false_positives(self):
        truth = [_make_truth("C1", CaseState.RECONCILED)]
        pred = [_make_pred("C1", CaseState.RECONCILED)]
        assert false_positive_count(pred, truth) == 0

    def test_full_metrics(self):
        truth = [_make_truth("C1", CaseState.RECONCILED, EDGES_A)]
        pred = [_make_pred("C1", CaseState.RECONCILED, EDGES_A)]
        m = compute_all_metrics(pred, truth)
        assert m["relationship_precision"] == 1.0
        assert m["relationship_recall"] == 1.0
        assert m["relationship_f1"] == 1.0
        assert m["relationship_true_positive_count"] == 1
        assert m["relationship_predicted_count"] == 1
        assert m["relationship_expected_count"] == 1
        assert m["stp_reconciled_case_count"] == 1
        assert m["reconciled_gross_amount_paise"] == 100000
        assert m["total_gross_amount_paise"] == 100000
        assert m["false_positive_count"] == 0


# ── Wrong prediction tests ────────────────────────────────────────────────


class TestWrongPrediction:
    def test_false_positive_counted(self):
        """Predicted RECONCILED but truth is ACTIONABLE_EXCEPTION."""
        truth = [_make_truth("C1", CaseState.ACTIONABLE_EXCEPTION)]
        pred = [_make_pred("C1", CaseState.RECONCILED)]
        assert false_positive_count(pred, truth) == 1

    def test_false_positive_amount(self):
        truth = [_make_truth("C1", CaseState.ACTIONABLE_EXCEPTION)]
        pred = [_make_pred("C1", CaseState.RECONCILED)]
        assert false_positive_amount_paise(pred, truth) == 100000

    def test_wrong_state_lowers_accuracy(self):
        truth = [
            _make_truth("C1", CaseState.RECONCILED),
            _make_truth("C2", CaseState.ACTIONABLE_EXCEPTION),
        ]
        pred = [
            _make_pred("C1", CaseState.RECONCILED),
            _make_pred("C2", CaseState.RECONCILED),  # wrong
        ]
        assert case_state_accuracy(pred, truth) == 0.5


# ── Missing prediction tests ──────────────────────────────────────────────


class TestMissingPrediction:
    def test_recall_drops_when_edges_missing(self):
        truth = [_make_truth("C1", CaseState.RECONCILED, EDGES_A + EDGES_B)]
        pred = [_make_pred("C1", CaseState.RECONCILED, EDGES_A)]  # missing EDGES_B
        recall = relationship_recall(pred, truth)
        assert recall < 1.0
        assert recall == 0.5

    def test_hidden_row_count(self):
        truth = [
            _make_truth("C1", CaseState.RECONCILED),
            _make_truth("C2", CaseState.RECONCILED),
        ]
        pred = [_make_pred("C1", CaseState.RECONCILED)]  # C2 missing
        assert hidden_row_count(pred, truth) == 1


# ── Aggregate metric tests ────────────────────────────────────────────────


class TestAggregateMetrics:
    def test_stp_rate(self):
        pred = [
            _make_pred("C1", CaseState.RECONCILED),
            _make_pred("C2", CaseState.ACTIONABLE_EXCEPTION),
        ]
        assert stp_rate(pred) == 0.5

    def test_unexplained_residual(self):
        pred = [
            _make_pred("C1", CaseState.RECONCILED),  # residual=0
            _make_pred("C2", CaseState.ACTIONABLE_EXCEPTION),  # residual=96000
        ]
        assert unexplained_residual_paise(pred) == 0
        assert open_exception_residual_paise(pred) == 96000

    def test_residual_in_reconciled_case_is_unexplained(self):
        invalid = _make_pred("C1", CaseState.RECONCILED).model_copy(
            update={"predicted_residual_paise": 10}
        )
        assert unexplained_residual_paise([invalid]) == 10

    def test_exception_code_accuracy(self):
        truth = [_make_truth("C1", CaseState.ACTIONABLE_EXCEPTION)]
        pred = [_make_pred("C1", CaseState.ACTIONABLE_EXCEPTION)]
        assert exception_code_accuracy(pred, truth) == 1.0

    def test_cash_bucket_accuracy(self):
        truth = [_make_truth("C1", CaseState.RECONCILED)]
        pred = [_make_pred("C1", CaseState.RECONCILED)]
        assert cash_bucket_accuracy(pred, truth) == 1.0
