from __future__ import annotations

from datetime import timedelta
from pathlib import Path

import pytest

from packages.domain.enums import ActorType, DecisionLevel, ExceptionCode
from packages.domain.exceptions import InvariantError
from services.normalization.policy import load_policy
from services.reconciliation.evidence import EvidenceEdge, EvidenceGraph
from services.reconciliation.invariants import verify_case
from services.reconciliation.models import ReconciliationCase, RowIssue, VerificationCheck
from services.reconciliation.orchestrator import run_reconciliation

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


def _demo_case() -> tuple[ReconciliationCase, EvidenceGraph]:
    policy = load_policy(ROOT / "policies" / "settlement_policy.v1.json")
    result = run_reconciliation(_source_files(), policy, "unit-invariants")
    case = next(case for case in result.cases if case.case_id == "CASE_0001")
    graph = EvidenceGraph()
    for edge in result.evidence_edges:
        graph.add_edge(edge)
    return case, graph


def _replace_record(
    case: ReconciliationCase,
    source_type: str,
    **updates: object,
) -> ReconciliationCase:
    copied = case.model_copy(deep=True)
    for index, record in enumerate(copied.records):
        if record.source_type == source_type:
            copied.records[index] = record.model_copy(update=updates)
            return copied
    raise AssertionError(f"record type not found: {source_type}")


def _results_by_id(case: ReconciliationCase, graph: EvidenceGraph) -> dict[str, bool]:
    policy = load_policy(ROOT / "policies" / "settlement_policy.v1.json")
    return {result.invariant_id: result.passed for result in verify_case(case, graph, policy)}


def test_clean_case_passes_all_invariants() -> None:
    case, graph = _demo_case()
    assert all(_results_by_id(case, graph).values())


def test_inv_001_currency_consistency() -> None:
    case, graph = _demo_case()
    mutated = _replace_record(case, "payments", currency="USD")
    assert _results_by_id(mutated, graph)["INV-001"] is False


def test_inv_002_order_to_payment_amount() -> None:
    case, graph = _demo_case()
    mutated = _replace_record(case, "orders", amount_paise=case.gross_amount_paise + 1)
    assert _results_by_id(mutated, graph)["INV-002"] is False


def test_inv_003_settlement_composition_balance() -> None:
    case, graph = _demo_case()
    component = next(
        record for record in case.records if record.source_type == "settlement_components"
    )
    mutated = _replace_record(
        case,
        "settlement_components",
        amount_paise=(component.amount_paise or 0) + 1,
    )
    assert _results_by_id(mutated, graph)["INV-003"] is False


def test_inv_004_and_005_settlement_bank_and_zero_residual() -> None:
    case, graph = _demo_case()
    without_bank = EvidenceGraph()
    for edge in graph.edges:
        if edge.relationship_type != "settlement_bank":
            without_bank.add_edge(edge)
    results = _results_by_id(case, without_bank)
    assert results["INV-004"] is False
    assert results["INV-005"] is False


def test_inv_006_unique_allocation() -> None:
    graph = EvidenceGraph()
    graph.register_available_amount("SET_X", "settlement_bank", 100)
    graph.register_available_amount("BANK_X", "settlement_bank", 100)
    edge = EvidenceEdge(
        source_entity_id="SET_X",
        target_entity_id="BANK_X",
        relationship_type="settlement_bank",
        allocated_amount_paise=100,
        rule_id="test_rule",
        rule_version="1.0.0",
        evidence_fields=["amount"],
        decision_level=DecisionLevel.VERIFIED,
        actor_type=ActorType.SYSTEM,
        verification_checks=[
            VerificationCheck(check_id="test", passed=True, message="test")
        ],
        created_at=next(iter(_demo_case()[1].edges)).created_at,
        reconciliation_run_id="unit",
    )
    graph.add_edge(edge)
    with pytest.raises(InvariantError):
        graph.add_edge(edge.model_copy(update={"target_entity_id": "BANK_Y"}))


def test_inv_007_temporal_validity() -> None:
    case, graph = _demo_case()
    bank = next(record for record in case.records if record.source_type == "bank_transactions")
    mutated = _replace_record(
        case,
        "bank_transactions",
        value_date=bank.value_date - timedelta(days=10),
    )
    assert _results_by_id(mutated, graph)["INV-007"] is False


def test_inv_008_lifecycle_validity() -> None:
    case, graph = _demo_case()
    mutated = _replace_record(case, "payments", status="FAILED")
    assert _results_by_id(mutated, graph)["INV-008"] is False


def test_inv_009_sla_validity() -> None:
    case, graph = _demo_case()
    settlement = next(record for record in case.records if record.source_type == "settlements")
    mutated = _replace_record(
        case,
        "settlements",
        event_date=settlement.event_date + timedelta(days=2),
    )
    assert _results_by_id(mutated, graph)["INV-009"] is False


def test_inv_010_control_total_validity() -> None:
    case, graph = _demo_case()
    mutated = case.model_copy(deep=True)
    mutated.invalid_reasons = [
        RowIssue(
            field="order_id",
            value="ORD_0001",
            reason="duplicate",
            code=ExceptionCode.DUPLICATE_SOURCE_RECORD,
        )
    ]
    assert _results_by_id(mutated, graph)["INV-010"] is False
