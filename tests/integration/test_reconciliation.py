from __future__ import annotations

from pathlib import Path

from evaluator.metrics import compute_all_metrics
from generator.ground_truth import GroundTruthManifest
from packages.domain.enums import CaseState, CashBucket, ExceptionCode
from services.normalization.policy import load_policy
from services.reconciliation.orchestrator import run_reconciliation, to_prediction_report

ROOT = Path(__file__).resolve().parents[2]


def _source_files() -> dict[str, str]:
    data = ROOT / "data" / "demo"
    return {
        "orders": str(data / "orders.csv"),
        "payments": str(data / "payments.csv"),
        "settlements": str(data / "settlements.csv"),
        "settlement_components": str(data / "settlement_components.csv"),
        "bank_transactions": str(data / "bank_transactions.csv"),
    }


def _run():
    policy = load_policy(ROOT / "policies" / "settlement_policy.v1.json")
    return run_reconciliation(_source_files(), policy, "integration")


def test_full_orchestrator_matches_hidden_demo_truth() -> None:
    result = _run()
    report = to_prediction_report(result)
    truth = GroundTruthManifest.model_validate_json(
        (ROOT / "evaluator_private" / "ground_truth_demo.json").read_text()
    )
    metrics = compute_all_metrics(
        report.cases,
        truth.cases,
        duration_seconds=report.duration_seconds,
        total_records=report.total_source_records,
    )
    assert metrics["relationship_precision"] == 1.0
    assert metrics["relationship_recall"] == 1.0
    assert metrics["case_state_accuracy"] == 1.0
    assert metrics["exception_code_accuracy"] == 1.0
    assert metrics["cash_bucket_accuracy"] == 1.0
    assert metrics["false_positive_count"] == 0


def test_clean_refund_chargeback_and_fee_variance_states() -> None:
    result = _run()
    cases = {case.case_id: case for case in result.cases}
    assert cases["CASE_0001"].case_state == CaseState.RECONCILED
    assert cases["CASE_R0042"].case_state == CaseState.RECONCILED
    assert cases["CASE_CB0048"].case_state == CaseState.RECONCILED
    assert cases["CASE_FV0056"].case_state == CaseState.ACTIONABLE_EXCEPTION
    assert cases["CASE_FV0056"].exception_code == ExceptionCode.FEE_VARIANCE


def test_missing_event_and_ambiguous_cases_are_actionable() -> None:
    result = _run()
    cases = {case.case_id: case for case in result.cases}
    assert cases["CASE_MS0069"].case_state == CaseState.ACTIONABLE_EXCEPTION
    assert cases["CASE_MS0069"].exception_code == ExceptionCode.BANK_CREDIT_MISSING
    assert cases["CASE_AMB0073"].case_state == CaseState.ACTIONABLE_EXCEPTION
    assert cases["CASE_AMB0073"].exception_code == ExceptionCode.AMBIGUOUS_CANDIDATES


def test_cash_position_buckets_sum_to_case_contributions() -> None:
    result = _run()
    bucket_case_ids = [
        case_id
        for bucket in result.cash_position.buckets.values()
        for case_id in bucket.case_ids
    ]
    assert sorted(bucket_case_ids) == sorted(case.case_id for case in result.cases)
    assert len(result.cash_position.buckets[CashBucket.BANK_CONFIRMED].case_ids) == 53
    assert (
        len(
            result.cash_position.buckets[
                CashBucket.SETTLEMENT_CONFIRMED_IN_TRANSIT
            ].case_ids
        )
        == 7
    )
    assert len(result.cash_position.buckets[CashBucket.AT_RISK].case_ids) == 8
    assert len(result.cash_position.buckets[CashBucket.UNRESOLVED].case_ids) == 7
    assert result.cash_position.safe_cash_paise == (
        result.cash_position.bank_confirmed_paise
        + result.cash_position.settlement_confirmed_in_transit_paise
        - result.cash_position.scheduled_refunds_paise
        - result.cash_position.known_disputes_paise
        - result.cash_position.known_reserve_holds_paise
    )
