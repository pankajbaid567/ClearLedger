from __future__ import annotations

from collections import defaultdict
from pathlib import Path

from packages.domain.enums import CaseState, ExceptionCode
from services.ingestion.service import ingest_file
from services.normalization.policy import load_policy
from services.normalization.service import normalize_records
from services.reconciliation.candidates import generate_candidates
from services.reconciliation.evidence import EvidenceGraph
from services.reconciliation.orchestrator import run_reconciliation
from services.reconciliation.rules import (
    adjustment_aware_balance,
    apply_matching_rules,
    bank_reference_amount_date,
    exact_order_payment,
    many_to_one_aggregation,
    narration_token_verified,
    one_to_many_split,
    settlement_membership,
    settlement_utr_bank,
    unique_exact_amount_window,
)

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


def _normalized_and_candidates():
    raw = []
    for source_type, path in _source_files().items():
        result = ingest_file(path, source_type)
        raw.extend(result.accepted_rows + result.rejected_rows)
    policy = load_policy(ROOT / "policies" / "settlement_policy.v1.json")
    records = normalize_records(raw)
    candidates = generate_candidates(records, policy)
    by_entity = defaultdict(list)
    for record in records:
        by_entity[record.entity_id].append(record)
    return records, candidates, policy, dict(by_entity)


def test_exact_order_payment_rule_accepts_identity_match() -> None:
    _, candidates, _, by_entity = _normalized_and_candidates()
    graph = EvidenceGraph()
    result = exact_order_payment(candidates, by_entity, graph, "rules")
    assert any(
        edge.source_entity_id == "ORD_0001"
        and edge.target_entity_id == "PAY_0001"
        and edge.relationship_type == "order_payment"
        for edge in result.accepted_edges
    )


def test_settlement_membership_rule_accepts_many_to_one() -> None:
    _, candidates, _, by_entity = _normalized_and_candidates()
    graph = EvidenceGraph()
    result = settlement_membership(candidates, by_entity, graph, "rules")
    batch_edges = [
        edge
        for edge in result.accepted_edges
        if edge.target_entity_id == "SET_BATCH_0021"
        and edge.relationship_type == "payment_settlement"
    ]
    assert len(batch_edges) > 1


def test_settlement_utr_bank_rule_accepts_exact_utr() -> None:
    _, candidates, _, by_entity = _normalized_and_candidates()
    graph = EvidenceGraph()
    result = settlement_utr_bank(candidates, by_entity, graph, "rules")
    assert any(
        edge.source_entity_id == "SET_0001"
        and edge.target_entity_id == "BANK_TXN_0001"
        and edge.rule_id == "settlement_utr_bank"
        for edge in result.accepted_edges
    )


def test_bank_reference_amount_date_rule_accepts_narration_token() -> None:
    _, candidates, _, by_entity = _normalized_and_candidates()
    graph = EvidenceGraph()
    result = bank_reference_amount_date(candidates, by_entity, graph, "rules")
    assert any(
        edge.source_entity_id == "SET_0001"
        and edge.target_entity_id == "BANK_TXN_0001"
        and edge.rule_id == "bank_reference_amount_date"
        for edge in result.accepted_edges
    )


def test_unique_exact_amount_window_marks_equal_strength_conflicts_ambiguous() -> None:
    _, candidates, _, by_entity = _normalized_and_candidates()
    graph = EvidenceGraph()
    result = unique_exact_amount_window(candidates, by_entity, graph, "rules")
    assert any(
        candidate.target_entity_id == "BANK_TXN_AMB_0073"
        for candidate in result.ambiguous_candidates
    )


def test_rule_priority_prefers_utr_over_weaker_amount_match() -> None:
    records, candidates, policy, _ = _normalized_and_candidates()
    graph, _ = apply_matching_rules(records, candidates, policy, "rules")
    matching_edges = [
        edge
        for edge in graph.edges
        if edge.source_entity_id == "SET_0001"
        and edge.target_entity_id == "BANK_TXN_0001"
        and edge.relationship_type == "settlement_bank"
    ]
    assert [edge.rule_id for edge in matching_edges] == ["settlement_utr_bank"]


def test_ambiguous_candidates_become_exception() -> None:
    policy = load_policy(ROOT / "policies" / "settlement_policy.v1.json")
    result = run_reconciliation(_source_files(), policy, "rules")
    case = next(case for case in result.cases if case.case_id == "CASE_AMB0073")
    assert case.case_state == CaseState.ACTIONABLE_EXCEPTION
    assert case.exception_code == ExceptionCode.AMBIGUOUS_CANDIDATES


def test_rejected_candidate_reason_tracking() -> None:
    _, candidates, _, by_entity = _normalized_and_candidates()
    conflicted = next(
        candidate for candidate in candidates if candidate.rule_id == "exact_order_payment"
    ).model_copy(update={"rejected_reasons": ["currency conflict"]})
    result = exact_order_payment([conflicted], by_entity, EvidenceGraph(), "rules")
    assert result.rejected_candidates[0].rejected_reasons == ["currency conflict"]


def test_later_rule_stubs_are_explicit_noops() -> None:
    _, candidates, _, by_entity = _normalized_and_candidates()
    graph = EvidenceGraph()
    for rule in (
        many_to_one_aggregation,
        one_to_many_split,
        adjustment_aware_balance,
        narration_token_verified,
    ):
        result = rule(candidates, by_entity, graph, "rules")
        assert result.accepted_edges == []
        assert result.rejected_candidates == []
        assert result.ambiguous_candidates == []
