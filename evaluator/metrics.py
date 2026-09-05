"""Pure evaluation metrics — no side effects, no database access.

Each function accepts prediction and truth collections and returns a single metric.
"""

from __future__ import annotations

from evaluator.schemas import PredictedCase, PredictedEdge
from generator.ground_truth import GroundTruthCase, GroundTruthEdge
from packages.domain.enums import CaseState

# ── Edge-level helpers ──────────────────────────────────────────────────────


EdgeKey = tuple[str, str, str, str, int]
TopologyKey = tuple[str, str, str, str]
MetricValue = int | float | str | None
Metrics = dict[str, MetricValue]


def _edge_key(case_id: str, edge: PredictedEdge | GroundTruthEdge) -> EdgeKey:
    """An evaluated relationship includes its case and exact allocated amount."""
    return (
        case_id,
        edge.source_entity_id,
        edge.target_entity_id,
        edge.relationship_type,
        edge.allocated_amount_paise,
    )


def _topology_key(case_id: str, edge: PredictedEdge | GroundTruthEdge) -> TopologyKey:
    return (
        case_id,
        edge.source_entity_id,
        edge.target_entity_id,
        edge.relationship_type,
    )


def _truth_edge_set(cases: list[GroundTruthCase]) -> set[EdgeKey]:
    s: set[EdgeKey] = set()
    for c in cases:
        for e in c.expected_relationships:
            s.add(_edge_key(c.case_id, e))
    return s


def _pred_edge_set(cases: list[PredictedCase]) -> set[EdgeKey]:
    s: set[EdgeKey] = set()
    for c in cases:
        for e in c.predicted_relationships:
            s.add(_edge_key(c.case_id, e))
    return s


def _topology_counts(
    predicted: list[PredictedCase], truth: list[GroundTruthCase]
) -> tuple[int, int, int]:
    predicted_edges = {
        _topology_key(case.case_id, edge)
        for case in predicted
        for edge in case.predicted_relationships
    }
    truth_edges = {
        _topology_key(case.case_id, edge) for case in truth for edge in case.expected_relationships
    }
    return len(predicted_edges & truth_edges), len(predicted_edges), len(truth_edges)


def _relationship_counts(
    predicted: list[PredictedCase], truth: list[GroundTruthCase]
) -> tuple[int, int, int]:
    pred_set = _pred_edge_set(predicted)
    truth_set = _truth_edge_set(truth)
    return len(pred_set & truth_set), len(pred_set), len(truth_set)


# ── Relationship metrics ───────────────────────────────────────────────────


def relationship_precision(predicted: list[PredictedCase], truth: list[GroundTruthCase]) -> float:
    """Of the edges the engine declared, how many are correct?"""
    true_positives, predicted_count, expected_count = _relationship_counts(predicted, truth)
    if not predicted_count:
        return 1.0 if not expected_count else 0.0
    return true_positives / predicted_count


def relationship_recall(predicted: list[PredictedCase], truth: list[GroundTruthCase]) -> float:
    """Of the true edges, how many did the engine find?"""
    true_positives, predicted_count, expected_count = _relationship_counts(predicted, truth)
    if not expected_count:
        return 1.0 if not predicted_count else 0.0
    return true_positives / expected_count


def relationship_f1(precision: float, recall: float) -> float:
    if precision + recall == 0:
        return 0.0
    return 2 * precision * recall / (precision + recall)


# ── Case-level metrics ─────────────────────────────────────────────────────


def _case_truth_map(truth: list[GroundTruthCase]) -> dict[str, GroundTruthCase]:
    result = {c.case_id: c for c in truth}
    if len(result) != len(truth):
        raise ValueError("ground truth contains duplicate case IDs")
    return result


def _case_pred_map(predicted: list[PredictedCase]) -> dict[str, PredictedCase]:
    result = {c.case_id: c for c in predicted}
    if len(result) != len(predicted):
        raise ValueError("predictions contain duplicate case IDs")
    return result


def _case_is_exactly_reconciled(predicted: PredictedCase, truth: GroundTruthCase) -> bool:
    return (
        predicted.predicted_case_state == CaseState.RECONCILED
        and truth.expected_case_state == CaseState.RECONCILED
        and predicted.predicted_gross_amount_paise == truth.expected_gross_amount_paise
        and predicted.predicted_net_amount_paise == truth.expected_net_amount_paise
        and predicted.predicted_residual_paise == truth.expected_residual_paise == 0
        and predicted.predicted_cash_bucket == truth.expected_cash_bucket
        and {_edge_key(predicted.case_id, edge) for edge in predicted.predicted_relationships}
        == {_edge_key(truth.case_id, edge) for edge in truth.expected_relationships}
    )


def case_state_accuracy(predicted: list[PredictedCase], truth: list[GroundTruthCase]) -> float:
    """Fraction of cases where the predicted state matches ground truth."""
    truth_map = _case_truth_map(truth)
    if not truth_map:
        return 1.0
    pred_map = _case_pred_map(predicted)
    correct = sum(
        pred_map.get(case_id) is not None
        and pred_map[case_id].predicted_case_state == truth_case.expected_case_state
        for case_id, truth_case in truth_map.items()
    )
    return correct / len(truth_map)


def exception_code_accuracy(predicted: list[PredictedCase], truth: list[GroundTruthCase]) -> float:
    """Accuracy for cases that have an expected exception code."""
    exception_cases = [c for c in truth if c.expected_exception_code is not None]
    if not exception_cases:
        return 1.0
    correct = 0
    for tc in exception_cases:
        pc = _case_pred_map(predicted).get(tc.case_id)
        if pc and pc.predicted_exception_code == tc.expected_exception_code:
            correct += 1
    return correct / len(exception_cases)


def cash_bucket_accuracy(predicted: list[PredictedCase], truth: list[GroundTruthCase]) -> float:
    truth_map = _case_truth_map(truth)
    if not truth_map:
        return 1.0
    pred_map = _case_pred_map(predicted)
    correct = sum(
        pred_map.get(case_id) is not None
        and pred_map[case_id].predicted_cash_bucket == truth_case.expected_cash_bucket
        for case_id, truth_case in truth_map.items()
    )
    return correct / len(truth_map)


# ── Aggregate metrics ──────────────────────────────────────────────────────


def stp_rate(predicted: list[PredictedCase]) -> float:
    """Straight-through processing: fraction of cases auto-reconciled."""
    if not predicted:
        return 0.0
    reconciled = sum(1 for c in predicted if c.predicted_case_state == CaseState.RECONCILED)
    return reconciled / len(predicted)


def monetary_reconciliation_rate(
    predicted: list[PredictedCase], truth: list[GroundTruthCase]
) -> float:
    """Fraction of total gross amount that was fully reconciled."""
    total_gross = sum(c.expected_gross_amount_paise for c in truth)
    if total_gross == 0:
        return 1.0
    reconciled_gross = 0
    truth_map = _case_truth_map(truth)
    for pc in predicted:
        tc = truth_map.get(pc.case_id)
        if tc and _case_is_exactly_reconciled(pc, tc):
            reconciled_gross += tc.expected_gross_amount_paise
    return reconciled_gross / total_gross


# ── Safety metrics ─────────────────────────────────────────────────────────


def false_positive_count(predicted: list[PredictedCase], truth: list[GroundTruthCase]) -> int:
    """Cases predicted RECONCILED but ground truth is NOT RECONCILED."""
    truth_map = _case_truth_map(truth)
    count = 0
    for pc in predicted:
        tc = truth_map.get(pc.case_id)
        if pc.predicted_case_state == CaseState.RECONCILED and (
            tc is None or not _case_is_exactly_reconciled(pc, tc)
        ):
            count += 1
    return count


def false_positive_amount_paise(
    predicted: list[PredictedCase], truth: list[GroundTruthCase]
) -> int:
    """Total gross paise of false positive cases."""
    truth_map = _case_truth_map(truth)
    total = 0
    for pc in predicted:
        tc = truth_map.get(pc.case_id)
        if pc.predicted_case_state == CaseState.RECONCILED and (
            tc is None or not _case_is_exactly_reconciled(pc, tc)
        ):
            total += (
                tc.expected_gross_amount_paise
                if tc is not None
                else abs(pc.predicted_gross_amount_paise)
            )
    return total


def hidden_row_count(predicted: list[PredictedCase], truth: list[GroundTruthCase]) -> int:
    """Cases in ground truth that have no corresponding prediction."""
    pred_ids = {c.case_id for c in predicted}
    return sum(1 for c in truth if c.case_id not in pred_ids)


def unexplained_residual_paise(predicted: list[PredictedCase]) -> int:
    """Residual incorrectly left inside cases declared fully reconciled."""
    return sum(
        abs(case.predicted_residual_paise)
        for case in predicted
        if case.predicted_case_state == CaseState.RECONCILED
    )


def open_exception_residual_paise(predicted: list[PredictedCase]) -> int:
    """Visible residual carried by non-reconciled cases and their exception workflow."""
    return sum(
        abs(case.predicted_residual_paise)
        for case in predicted
        if case.predicted_case_state != CaseState.RECONCILED
    )


def throughput_records_per_second(total_records: int, duration_seconds: float) -> float:
    if duration_seconds <= 0:
        return 0.0
    return total_records / duration_seconds


# ── Full evaluation ────────────────────────────────────────────────────────


def compute_all_metrics(
    predicted: list[PredictedCase],
    truth: list[GroundTruthCase],
    duration_seconds: float = 0.0,
    total_records: int = 0,
) -> Metrics:
    # Reject duplicate case IDs before any dictionary or set operation can hide
    # them and make an invalid report appear more accurate.
    _case_pred_map(predicted)
    _case_truth_map(truth)
    true_positives, predicted_count, expected_count = _relationship_counts(predicted, truth)
    topology_true_positives, topology_predicted_count, topology_expected_count = _topology_counts(
        predicted, truth
    )
    prec = relationship_precision(predicted, truth)
    rec = relationship_recall(predicted, truth)
    f1 = relationship_f1(prec, rec)
    reconciled_case_count = sum(
        1 for case in predicted if case.predicted_case_state == CaseState.RECONCILED
    )
    total_gross_paise = sum(case.expected_gross_amount_paise for case in truth)
    truth_map = _case_truth_map(truth)
    reconciled_gross_paise = sum(
        truth_case.expected_gross_amount_paise
        for case in predicted
        if (truth_case := truth_map.get(case.case_id)) is not None
        and _case_is_exactly_reconciled(case, truth_case)
    )

    return {
        "relationship_precision": round(prec, 4),
        "relationship_recall": round(rec, 4),
        "relationship_f1": round(f1, 4),
        "relationship_true_positive_count": true_positives,
        "relationship_predicted_count": predicted_count,
        "relationship_expected_count": expected_count,
        "relationship_topology_true_positive_count": topology_true_positives,
        "relationship_topology_predicted_count": topology_predicted_count,
        "relationship_topology_expected_count": topology_expected_count,
        "case_state_accuracy": round(case_state_accuracy(predicted, truth), 4),
        "exception_code_accuracy": round(exception_code_accuracy(predicted, truth), 4),
        "cash_bucket_accuracy": round(cash_bucket_accuracy(predicted, truth), 4),
        "stp_rate": round(stp_rate(predicted), 4),
        "stp_reconciled_case_count": reconciled_case_count,
        "monetary_reconciliation_rate": round(monetary_reconciliation_rate(predicted, truth), 4),
        "reconciled_gross_amount_paise": reconciled_gross_paise,
        "total_gross_amount_paise": total_gross_paise,
        "false_positive_count": false_positive_count(predicted, truth),
        "false_positive_amount_paise": false_positive_amount_paise(predicted, truth),
        "hidden_row_count": hidden_row_count(predicted, truth),
        "missing_case_count": hidden_row_count(predicted, truth),
        "unexplained_residual_paise": unexplained_residual_paise(predicted),
        "open_exception_residual_paise": open_exception_residual_paise(predicted),
        "throughput_records_per_second": round(
            throughput_records_per_second(total_records, duration_seconds), 2
        )
        if duration_seconds > 0
        else None,
        "total_predicted_cases": len(predicted),
        "total_truth_cases": len(truth),
    }


def compute_scenario_breakdown(
    predicted: list[PredictedCase],
    truth: list[GroundTruthCase],
) -> dict[str, Metrics]:
    """Break down metrics by scenario_label."""
    # Group truth by scenario
    scenario_truths: dict[str, list[GroundTruthCase]] = {}
    for tc in truth:
        scenario_truths.setdefault(tc.scenario_label, []).append(tc)

    # Group predictions by case_id for lookup
    pred_map = _case_pred_map(predicted)

    result: dict[str, Metrics] = {}
    for label, truths in sorted(scenario_truths.items()):
        case_ids = {tc.case_id for tc in truths}
        matching_preds = [pred_map[cid] for cid in case_ids if cid in pred_map]
        result[label] = compute_all_metrics(matching_preds, truths)

    return result
