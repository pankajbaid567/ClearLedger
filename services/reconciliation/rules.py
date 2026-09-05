"""Deterministic matching rules in descending evidence strength."""

from __future__ import annotations

from collections import Counter, defaultdict
from datetime import UTC, datetime
from typing import Literal

from packages.domain.enums import ActorType, DecisionLevel, IngestionQuality
from packages.domain.exceptions import InvariantError
from services.normalization.policy import SettlementPolicy
from services.reconciliation.evidence import EvidenceEdge, EvidenceGraph
from services.reconciliation.models import (
    CandidateRelationship,
    NormalizedRecord,
    RuleApplicationResult,
    VerificationCheck,
)

RULE_VERSION = "1.0.0"
_CREATED_AT = datetime(2026, 1, 1, tzinfo=UTC)
MatchingMode = Literal["exact_id_only", "deterministic_full"]


def _records_by_entity(
    normalized_records: list[NormalizedRecord],
) -> dict[str, list[NormalizedRecord]]:
    records: dict[str, list[NormalizedRecord]] = defaultdict(list)
    for record in normalized_records:
        records[record.entity_id].append(record)
    return dict(records)


def _invalid_entity_reasons(
    candidate: CandidateRelationship,
    records_by_entity: dict[str, list[NormalizedRecord]],
) -> list[str]:
    reasons: list[str] = []
    for role, entity_id in (
        ("source", candidate.source_entity_id),
        ("target", candidate.target_entity_id),
    ):
        if any(
            record.quality == IngestionQuality.INVALID
            for record in records_by_entity.get(entity_id, [])
        ):
            reasons.append(f"{role} entity has invalid source record")
    return reasons


def _candidate_checks(candidate: CandidateRelationship) -> list[VerificationCheck]:
    return [
        VerificationCheck(
            check_id="candidate_rejection_reasons",
            passed=not candidate.rejected_reasons,
            expected_value="no rejection reasons",
            actual_value=", ".join(candidate.rejected_reasons) or "none",
            affected_entities=[candidate.source_entity_id, candidate.target_entity_id],
            message="candidate passed deterministic pre-checks",
        )
    ]


def _edge_from_candidate(
    candidate: CandidateRelationship,
    run_id: str,
    decision_level: DecisionLevel = DecisionLevel.VERIFIED,
) -> EvidenceEdge:
    return EvidenceEdge(
        source_entity_id=candidate.source_entity_id,
        target_entity_id=candidate.target_entity_id,
        relationship_type=candidate.relationship_type,
        allocated_amount_paise=candidate.allocated_amount_paise,
        rule_id=candidate.rule_id,
        rule_version=RULE_VERSION,
        evidence_fields=candidate.evidence_fields,
        decision_level=decision_level,
        actor_type=ActorType.SYSTEM,
        verification_checks=_candidate_checks(candidate),
        created_at=_CREATED_AT,
        reconciliation_run_id=run_id,
    )


def _already_allocated(
    evidence: EvidenceGraph,
    candidate: CandidateRelationship,
) -> bool:
    return any(
        edge.decision_level == DecisionLevel.VERIFIED
        and edge.relationship_type == candidate.relationship_type
        and (
            edge.source_entity_id == candidate.source_entity_id
            or edge.target_entity_id == candidate.target_entity_id
        )
        for edge in evidence.edges
    )


def _append_rejection(
    result: RuleApplicationResult,
    candidate: CandidateRelationship,
    reasons: list[str],
) -> None:
    merged = list(dict.fromkeys(candidate.rejected_reasons + reasons))
    result.rejected_candidates.append(candidate.model_copy(update={"rejected_reasons": merged}))


def _accept_candidate(
    result: RuleApplicationResult,
    evidence: EvidenceGraph,
    candidate: CandidateRelationship,
) -> None:
    try:
        edge = _edge_from_candidate(candidate, candidate.metadata.get("run_id", ""))
        evidence.add_edge(edge)
        result.accepted_edges.append(edge)
    except InvariantError as exc:
        _append_rejection(result, candidate, [f"duplicate allocation: {exc}"])


def _run_unique_pair_rule(
    *,
    rule_id: str,
    relationship_type: str,
    candidates: list[CandidateRelationship],
    records_by_entity: dict[str, list[NormalizedRecord]],
    evidence: EvidenceGraph,
    run_id: str,
    allow_many_sources_per_target: bool = False,
) -> RuleApplicationResult:
    result = RuleApplicationResult()
    rule_candidates = [
        candidate
        for candidate in candidates
        if candidate.rule_id == rule_id and candidate.relationship_type == relationship_type
    ]
    valid: list[CandidateRelationship] = []
    for candidate in rule_candidates:
        reasons = candidate.rejected_reasons + _invalid_entity_reasons(candidate, records_by_entity)
        if _already_allocated(evidence, candidate):
            reasons.append("duplicate allocation")
        if reasons:
            _append_rejection(result, candidate, reasons)
        else:
            valid.append(
                candidate.model_copy(update={"metadata": {**candidate.metadata, "run_id": run_id}})
            )

    source_counts = Counter(candidate.source_entity_id for candidate in valid)
    target_counts = Counter(candidate.target_entity_id for candidate in valid)
    for candidate in valid:
        target_conflict = (
            target_counts[candidate.target_entity_id] > 1 and not allow_many_sources_per_target
        )
        if source_counts[candidate.source_entity_id] > 1 or target_conflict:
            ambiguous = candidate.model_copy(
                update={"rejected_reasons": ["equal-strength candidates conflict"]}
            )
            result.ambiguous_candidates.append(ambiguous)
            continue
        _accept_candidate(result, evidence, candidate)
    return result


def exact_order_payment(
    candidates: list[CandidateRelationship],
    records_by_entity: dict[str, list[NormalizedRecord]],
    evidence: EvidenceGraph,
    run_id: str,
) -> RuleApplicationResult:
    return _run_unique_pair_rule(
        rule_id="exact_order_payment",
        relationship_type="order_payment",
        candidates=candidates,
        records_by_entity=records_by_entity,
        evidence=evidence,
        run_id=run_id,
    )


def settlement_membership(
    candidates: list[CandidateRelationship],
    records_by_entity: dict[str, list[NormalizedRecord]],
    evidence: EvidenceGraph,
    run_id: str,
) -> RuleApplicationResult:
    return _run_unique_pair_rule(
        rule_id="settlement_membership",
        relationship_type="payment_settlement",
        candidates=candidates,
        records_by_entity=records_by_entity,
        evidence=evidence,
        run_id=run_id,
        allow_many_sources_per_target=True,
    )


def settlement_utr_bank(
    candidates: list[CandidateRelationship],
    records_by_entity: dict[str, list[NormalizedRecord]],
    evidence: EvidenceGraph,
    run_id: str,
) -> RuleApplicationResult:
    return _run_unique_pair_rule(
        rule_id="settlement_utr_bank",
        relationship_type="settlement_bank",
        candidates=candidates,
        records_by_entity=records_by_entity,
        evidence=evidence,
        run_id=run_id,
    )


def bank_reference_amount_date(
    candidates: list[CandidateRelationship],
    records_by_entity: dict[str, list[NormalizedRecord]],
    evidence: EvidenceGraph,
    run_id: str,
) -> RuleApplicationResult:
    return _run_unique_pair_rule(
        rule_id="bank_reference_amount_date",
        relationship_type="settlement_bank",
        candidates=candidates,
        records_by_entity=records_by_entity,
        evidence=evidence,
        run_id=run_id,
    )


def unique_exact_amount_window(
    candidates: list[CandidateRelationship],
    records_by_entity: dict[str, list[NormalizedRecord]],
    evidence: EvidenceGraph,
    run_id: str,
) -> RuleApplicationResult:
    return _run_unique_pair_rule(
        rule_id="unique_exact_amount_window",
        relationship_type="settlement_bank",
        candidates=candidates,
        records_by_entity=records_by_entity,
        evidence=evidence,
        run_id=run_id,
    )


def many_to_one_aggregation(
    candidates: list[CandidateRelationship],
    records_by_entity: dict[str, list[NormalizedRecord]],
    evidence: EvidenceGraph,
    run_id: str,
) -> RuleApplicationResult:
    """Membership edges already encode many payments rolling into one settlement."""
    return RuleApplicationResult()


def one_to_many_split(
    candidates: list[CandidateRelationship],
    records_by_entity: dict[str, list[NormalizedRecord]],
    evidence: EvidenceGraph,
    run_id: str,
) -> RuleApplicationResult:
    """Split payouts require explicit bounded candidates; none are produced in Phase 1 data."""
    return RuleApplicationResult()


def adjustment_aware_balance(
    candidates: list[CandidateRelationship],
    records_by_entity: dict[str, list[NormalizedRecord]],
    evidence: EvidenceGraph,
    run_id: str,
) -> RuleApplicationResult:
    """Refund, chargeback, tax, fee, and reserve adjustments are verified by invariants."""
    return RuleApplicationResult()


def narration_token_verified(
    candidates: list[CandidateRelationship],
    records_by_entity: dict[str, list[NormalizedRecord]],
    evidence: EvidenceGraph,
    run_id: str,
) -> RuleApplicationResult:
    """Deterministic narration-token candidates are handled by bank_reference_amount_date."""
    return RuleApplicationResult()


def _register_availability(evidence: EvidenceGraph, records: list[NormalizedRecord]) -> None:
    for record in records:
        if record.amount_paise is None:
            continue
        if record.source_type == "settlements":
            evidence.register_available_amount(
                record.entity_id, "settlement_bank", record.amount_paise
            )
        elif record.source_type == "bank_transactions":
            evidence.register_available_amount(
                record.entity_id, "settlement_bank", record.signed_amount_paise or 0
            )


def _merge_results(
    aggregate: RuleApplicationResult,
    next_result: RuleApplicationResult,
) -> None:
    aggregate.accepted_edges.extend(next_result.accepted_edges)
    aggregate.rejected_candidates.extend(next_result.rejected_candidates)
    aggregate.ambiguous_candidates.extend(next_result.ambiguous_candidates)


def apply_matching_rules(
    normalized_records: list[NormalizedRecord],
    candidates: list[CandidateRelationship],
    policy: SettlementPolicy,
    run_id: str,
    mode: MatchingMode = "deterministic_full",
) -> tuple[EvidenceGraph, RuleApplicationResult]:
    """Apply deterministic rules in the PRD priority order."""
    del policy
    evidence = EvidenceGraph()
    _register_availability(evidence, normalized_records)
    records_by_entity = _records_by_entity(normalized_records)
    aggregate = RuleApplicationResult()

    rules = (
        exact_order_payment,
        settlement_membership,
        settlement_utr_bank,
        bank_reference_amount_date,
        unique_exact_amount_window,
        many_to_one_aggregation,
        one_to_many_split,
        adjustment_aware_balance,
        narration_token_verified,
    )
    active_rules = rules[:3] if mode == "exact_id_only" else rules
    for rule in active_rules:
        _merge_results(aggregate, rule(candidates, records_by_entity, evidence, run_id))

    return evidence, aggregate
