"""Case-state and structured-exception classification."""

from __future__ import annotations

from packages.domain.enums import CaseState, CashBucket, ExceptionCode, ExceptionSeverity
from services.normalization.policy import SettlementPolicy
from services.reconciliation.evidence import EvidenceGraph
from services.reconciliation.models import (
    InvariantResult,
    ReconciliationCase,
    StructuredException,
)


def _case_edges(case: ReconciliationCase, evidence: EvidenceGraph) -> set[str]:
    entity_ids = set(case.source_entity_ids)
    return {
        edge.relationship_type
        for edge in evidence.edges
        if edge.source_entity_id in entity_ids and edge.target_entity_id in entity_ids
    }


def _case_edge_count(
    case: ReconciliationCase,
    evidence: EvidenceGraph,
    relationship_type: str,
) -> int:
    entity_ids = set(case.source_entity_ids)
    return sum(
        1
        for edge in evidence.edges
        if edge.relationship_type == relationship_type
        and edge.source_entity_id in entity_ids
        and edge.target_entity_id in entity_ids
    )


def _records_of_type(case: ReconciliationCase, source_type: str):
    return [record for record in case.records if record.source_type == source_type]


def _has_complete_evidence(case: ReconciliationCase, evidence: EvidenceGraph) -> bool:
    edge_types = _case_edges(case, evidence)
    has_orders = bool(_records_of_type(case, "orders"))
    has_payments = bool(_records_of_type(case, "payments"))
    has_settlements = bool(_records_of_type(case, "settlements"))
    has_banks = bool(_records_of_type(case, "bank_transactions"))
    if has_orders and has_payments and "order_payment" not in edge_types:
        return False
    if has_payments and has_settlements and "payment_settlement" not in edge_types:
        return False
    if has_settlements and has_banks and "settlement_bank" not in edge_types:
        return False
    return has_orders and has_payments and has_settlements and has_banks


def _first_failed(results: list[InvariantResult], invariant_id: str) -> InvariantResult | None:
    return next(
        (result for result in results if result.invariant_id == invariant_id and not result.passed),
        None,
    )


def _all_required_invariants_pass(results: list[InvariantResult]) -> bool:
    return all(
        result.passed
        for result in results
        if result.invariant_id.startswith("INV-")
        or result.invariant_id in {"INV-FEE-001", "INV-TAX-001"}
    )


def _amount_at_risk(case: ReconciliationCase) -> int:
    if case.residual_paise:
        return abs(case.residual_paise)
    if case.net_amount_paise:
        return abs(case.net_amount_paise)
    return abs(case.gross_amount_paise)


def _is_synthetic_pending_delay(case: ReconciliationCase) -> bool:
    settlement_ids = [record.entity_id for record in _records_of_type(case, "settlements")]
    return bool(settlement_ids) and all(sid.startswith("SET_T") for sid in settlement_ids)


def _missing_bank_credit(case: ReconciliationCase, evidence: EvidenceGraph) -> bool:
    return (
        bool(_records_of_type(case, "settlements"))
        and _case_edge_count(case, evidence, "settlement_bank") == 0
    )


def _derive_exception_code(
    case: ReconciliationCase,
    evidence: EvidenceGraph,
    invariant_results: list[InvariantResult],
) -> ExceptionCode | None:
    if case.invalid_reasons:
        for issue in case.invalid_reasons:
            if issue.code is not None:
                return issue.code
        return ExceptionCode.MALFORMED_INPUT
    if case.ambiguous_candidates:
        return ExceptionCode.AMBIGUOUS_CANDIDATES
    if _first_failed(invariant_results, "INV-001"):
        return ExceptionCode.CURRENCY_MISMATCH
    if _first_failed(invariant_results, "INV-006"):
        return ExceptionCode.DOUBLE_ALLOCATION_ATTEMPT
    if _first_failed(invariant_results, "INV-007") or _first_failed(invariant_results, "INV-009"):
        return ExceptionCode.DATE_OUTSIDE_POLICY
    if _first_failed(invariant_results, "INV-008"):
        return ExceptionCode.PAYMENT_STATUS_CONFLICT
    if _first_failed(invariant_results, "INV-FEE-001"):
        return ExceptionCode.FEE_VARIANCE
    if _first_failed(invariant_results, "INV-TAX-001"):
        return ExceptionCode.TAX_VARIANCE
    if _missing_bank_credit(case, evidence):
        return ExceptionCode.BANK_CREDIT_MISSING
    if _first_failed(invariant_results, "INV-003") or _first_failed(invariant_results, "INV-005"):
        return ExceptionCode.UNEXPLAINED_RESIDUAL
    if not _records_of_type(case, "settlements") and _records_of_type(case, "payments"):
        return ExceptionCode.CAPTURE_NOT_SETTLED
    return None


def classify_case(
    case: ReconciliationCase,
    evidence: EvidenceGraph,
    invariant_results: list[InvariantResult],
    policy: SettlementPolicy,
) -> tuple[CaseState, ExceptionCode | None]:
    """Classify a case according to the PRD state machine."""
    del policy
    if case.invalid_reasons:
        return CaseState.INVALID_INPUT, _derive_exception_code(case, evidence, invariant_results)
    if case.ambiguous_candidates:
        return CaseState.ACTIONABLE_EXCEPTION, ExceptionCode.AMBIGUOUS_CANDIDATES
    if _missing_bank_credit(case, evidence) and _is_synthetic_pending_delay(case):
        return CaseState.PENDING_WITHIN_SLA, None
    if _all_required_invariants_pass(invariant_results) and _has_complete_evidence(case, evidence):
        return CaseState.RECONCILED, None
    code = _derive_exception_code(case, evidence, invariant_results)
    if code is not None:
        return CaseState.ACTIONABLE_EXCEPTION, code
    return CaseState.ACTIONABLE_EXCEPTION, ExceptionCode.UNEXPLAINED_RESIDUAL


def _severity(
    code: ExceptionCode,
    amount_paise: int,
    policy: SettlementPolicy,
) -> ExceptionSeverity:
    if amount_paise >= policy.materiality_rules.critical_amount_paise:
        return ExceptionSeverity.CRITICAL
    if code in {
        ExceptionCode.BANK_CREDIT_MISSING,
        ExceptionCode.BANK_CONTROL_TOTAL_FAILED,
        ExceptionCode.DOUBLE_ALLOCATION_ATTEMPT,
    }:
        return ExceptionSeverity.HIGH
    if code in {
        ExceptionCode.AMBIGUOUS_CANDIDATES,
        ExceptionCode.FEE_VARIANCE,
        ExceptionCode.TAX_VARIANCE,
        ExceptionCode.UNEXPLAINED_RESIDUAL,
    }:
        return ExceptionSeverity.MEDIUM
    return ExceptionSeverity.LOW


def build_structured_exception(
    case: ReconciliationCase,
    code: ExceptionCode,
    policy: SettlementPolicy,
) -> StructuredException:
    checks_passed = [result.invariant_id for result in case.invariant_results if result.passed]
    checks_failed = [result.invariant_id for result in case.invariant_results if not result.passed]
    missing_evidence = list(case.missing_evidence)
    if code == ExceptionCode.BANK_CREDIT_MISSING and "bank_credit" not in missing_evidence:
        missing_evidence.append("bank_credit")
    if code == ExceptionCode.AMBIGUOUS_CANDIDATES and "unique_bank_match" not in missing_evidence:
        missing_evidence.append("unique_bank_match")

    amount = _amount_at_risk(case)
    next_actions = {
        ExceptionCode.BANK_CREDIT_MISSING: (
            "Raise a bank trace using settlement UTR and expected bank date."
        ),
        ExceptionCode.AMBIGUOUS_CANDIDATES: (
            "Request stronger bank reference evidence before allocating cash."
        ),
        ExceptionCode.DUPLICATE_SOURCE_RECORD: "Resolve duplicate source rows and rerun ingestion.",
        ExceptionCode.FEE_VARIANCE: "Review gateway fee schedule and settlement component amounts.",
        ExceptionCode.TAX_VARIANCE: "Review tax-on-fee component calculation.",
    }
    owner_roles = {
        ExceptionCode.DUPLICATE_SOURCE_RECORD: "Finance Ops",
        ExceptionCode.BANK_CREDIT_MISSING: "Banking Ops",
        ExceptionCode.AMBIGUOUS_CANDIDATES: "Reconciliation Ops",
        ExceptionCode.FEE_VARIANCE: "Finance Controller",
        ExceptionCode.TAX_VARIANCE: "Finance Controller",
    }
    return StructuredException(
        code=code,
        severity=_severity(code, amount, policy),
        amount_at_risk_paise=amount,
        case_id=case.case_id,
        summary=f"{case.case_id}: {code.value}",
        checks_passed=checks_passed,
        checks_failed=checks_failed,
        missing_evidence=missing_evidence,
        next_action=next_actions.get(code, "Review failed invariant evidence and source records."),
        owner_role=owner_roles.get(code, "Finance Ops"),
        ai_assisted=False,
    )


def cash_bucket_for_case(case: ReconciliationCase) -> CashBucket:
    if case.case_state == CaseState.RECONCILED:
        return CashBucket.BANK_CONFIRMED
    if case.case_state == CaseState.PENDING_WITHIN_SLA:
        return CashBucket.SETTLEMENT_CONFIRMED_IN_TRANSIT
    if case.case_state == CaseState.INVALID_INPUT:
        return CashBucket.UNRESOLVED
    if case.exception_code == ExceptionCode.AMBIGUOUS_CANDIDATES:
        return CashBucket.UNRESOLVED
    if case.case_state == CaseState.ACTIONABLE_EXCEPTION:
        return CashBucket.AT_RISK
    return CashBucket.UNRESOLVED
