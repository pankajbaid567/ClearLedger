"""Financial invariant verifier for reconciliation cases."""

from __future__ import annotations

from datetime import date

from packages.domain.enums import ComponentType, DecisionLevel, Direction
from services.normalization.dates import expected_bank_date
from services.normalization.policy import SettlementPolicy
from services.reconciliation.evidence import EvidenceEdge, EvidenceGraph
from services.reconciliation.models import (
    CandidateRelationship,
    InvariantResult,
    NormalizedRecord,
    ReconciliationCase,
    VerificationCheck,
)


def _case_edges(case: ReconciliationCase, evidence: EvidenceGraph) -> list[EvidenceEdge]:
    entity_ids = set(case.source_entity_ids)
    return [
        edge
        for edge in evidence.edges
        if edge.source_entity_id in entity_ids and edge.target_entity_id in entity_ids
    ]


def _records_by_type(case: ReconciliationCase, source_type: str) -> list[NormalizedRecord]:
    return [record for record in case.records if record.source_type == source_type]


def _record_map(case: ReconciliationCase) -> dict[str, NormalizedRecord]:
    return {record.entity_id: record for record in case.records}


def _pass(
    invariant_id: str,
    message: str,
    affected_entities: list[str] | None = None,
    expected_value: int | str | None = None,
    actual_value: int | str | None = None,
) -> InvariantResult:
    return InvariantResult(
        invariant_id=invariant_id,
        passed=True,
        expected_value=expected_value,
        actual_value=actual_value,
        affected_entities=affected_entities or [],
        message=message,
    )


def _fail(
    invariant_id: str,
    message: str,
    affected_entities: list[str] | None = None,
    expected_value: int | str | None = None,
    actual_value: int | str | None = None,
) -> InvariantResult:
    return InvariantResult(
        invariant_id=invariant_id,
        passed=False,
        expected_value=expected_value,
        actual_value=actual_value,
        affected_entities=affected_entities or [],
        message=message,
    )


def _component_signed_amount(component: NormalizedRecord) -> int:
    amount = component.amount_paise or 0
    if component.direction == Direction.DEBIT.value:
        return -amount
    return amount


def _settlement_components(
    case: ReconciliationCase,
    settlement_id: str,
) -> list[NormalizedRecord]:
    return [
        component
        for component in _records_by_type(case, "settlement_components")
        if component.settlement_id == settlement_id
    ]


def _components_for_payment(
    case: ReconciliationCase,
    payment_id: str,
    component_type: ComponentType,
) -> list[NormalizedRecord]:
    return [
        component
        for component in _records_by_type(case, "settlement_components")
        if component.source_event_id == payment_id
        and component.component_type == component_type.value
    ]


def _settlement_day(record: NormalizedRecord) -> date | None:
    if record.event_at is not None:
        return record.event_at.date()
    return record.event_date


def _verify_currency(case: ReconciliationCase) -> InvariantResult:
    currencies = sorted({record.currency for record in case.records if record.currency is not None})
    if len(currencies) <= 1:
        return _pass(
            "INV-001",
            "all monetary records share one currency",
            actual_value=",".join(currencies),
        )
    return _fail(
        "INV-001",
        "currency mismatch inside case",
        affected_entities=case.source_entity_ids,
        expected_value=currencies[0],
        actual_value=",".join(currencies),
    )


def _verify_order_payment_amount(
    case: ReconciliationCase,
    edges: list[EvidenceEdge],
    records: dict[str, NormalizedRecord],
) -> InvariantResult:
    failures: list[str] = []
    for edge in edges:
        if edge.relationship_type != "order_payment":
            continue
        order = records.get(edge.source_entity_id)
        payment = records.get(edge.target_entity_id)
        if order is None or payment is None:
            failures.append(f"{edge.source_entity_id}->{edge.target_entity_id}: missing record")
            continue
        if order.amount_paise != payment.amount_paise:
            failures.append(
                f"{order.entity_id}->{payment.entity_id}: "
                f"{order.amount_paise}!={payment.amount_paise}"
            )
    if failures:
        return _fail("INV-002", "; ".join(failures), affected_entities=case.source_entity_ids)
    return _pass("INV-002", "order amount equals captured payment amount")


def _verify_settlement_composition(case: ReconciliationCase) -> InvariantResult:
    failures: list[str] = []
    checked: list[str] = []
    for settlement in _records_by_type(case, "settlements"):
        components = _settlement_components(case, settlement.entity_id)
        calculated = sum(_component_signed_amount(component) for component in components)
        expected = settlement.amount_paise or 0
        checked.append(settlement.entity_id)
        if calculated != expected:
            failures.append(f"{settlement.entity_id}: expected {expected}, actual {calculated}")
    if failures:
        return _fail("INV-003", "; ".join(failures), affected_entities=checked)
    return _pass("INV-003", "settlement net equals signed component sum", affected_entities=checked)


def _verify_settlement_bank_receipt(
    case: ReconciliationCase,
    edges: list[EvidenceEdge],
) -> InvariantResult:
    failures: list[str] = []
    checked: list[str] = []
    bank_edges = [edge for edge in edges if edge.relationship_type == "settlement_bank"]
    for settlement in _records_by_type(case, "settlements"):
        allocated = sum(
            edge.allocated_amount_paise
            for edge in bank_edges
            if edge.source_entity_id == settlement.entity_id
        )
        expected = settlement.amount_paise or 0
        checked.append(settlement.entity_id)
        if allocated != expected:
            failures.append(f"{settlement.entity_id}: expected {expected}, actual {allocated}")
    if failures:
        return _fail("INV-004", "; ".join(failures), affected_entities=checked)
    return _pass(
        "INV-004",
        "settlement bank receipts equal reported net",
        affected_entities=checked,
    )


def _verify_zero_residual(
    case: ReconciliationCase,
    edges: list[EvidenceEdge],
) -> InvariantResult:
    settlements = _records_by_type(case, "settlements")
    if not settlements:
        expected = sum(record.amount_paise or 0 for record in _records_by_type(case, "orders"))
        return _fail(
            "INV-005",
            "no settlement evidence explains expected order amount",
            affected_entities=case.source_entity_ids,
            expected_value=expected,
            actual_value=0,
        )

    expected = sum(settlement.amount_paise or 0 for settlement in settlements)
    explained = sum(
        edge.allocated_amount_paise for edge in edges if edge.relationship_type == "settlement_bank"
    )
    if expected != explained:
        return _fail(
            "INV-005",
            "non-zero unexplained residual",
            affected_entities=[settlement.entity_id for settlement in settlements],
            expected_value=expected,
            actual_value=explained,
        )
    return _pass("INV-005", "zero residual", expected_value=expected, actual_value=explained)


def verify_allocation_uniqueness(evidence: EvidenceGraph) -> InvariantResult:
    checks = evidence.check_allocation_uniqueness()
    failed = [check for check in checks if not check.passed]
    if failed:
        return _fail(
            "INV-006",
            "; ".join(check.message for check in failed),
            affected_entities=[entity for check in failed for entity in check.affected_entities],
        )
    return _pass("INV-006", "verified allocations do not exceed available amounts")


def _verify_temporal_validity(
    case: ReconciliationCase,
    edges: list[EvidenceEdge],
    records: dict[str, NormalizedRecord],
) -> InvariantResult:
    failures: list[str] = []
    for edge in edges:
        if edge.relationship_type != "settlement_bank":
            continue
        settlement = records.get(edge.source_entity_id)
        bank = records.get(edge.target_entity_id)
        if settlement is None or bank is None:
            continue
        settlement_day = _settlement_day(settlement)
        if (
            settlement_day is not None
            and bank.value_date is not None
            and bank.value_date < settlement_day
        ):
            failures.append(f"{bank.entity_id} precedes {settlement.entity_id}")
    if failures:
        return _fail("INV-007", "; ".join(failures), affected_entities=case.source_entity_ids)
    return _pass("INV-007", "bank receipt does not precede settlement")


def _verify_lifecycle_validity(
    case: ReconciliationCase,
    edges: list[EvidenceEdge],
    records: dict[str, NormalizedRecord],
) -> InvariantResult:
    failures: list[str] = []
    allowed = {"CAPTURED", "REFUNDED"}
    for edge in edges:
        if edge.relationship_type != "payment_settlement":
            continue
        payment = records.get(edge.source_entity_id)
        if payment is None:
            continue
        status = payment.status or ""
        if status not in allowed:
            failures.append(f"{payment.entity_id} has non-settleable status {status}")
    if failures:
        return _fail("INV-008", "; ".join(failures), affected_entities=case.source_entity_ids)
    return _pass("INV-008", "settlement components use settleable payment lifecycle states")


def _verify_sla_validity(case: ReconciliationCase, policy: SettlementPolicy) -> InvariantResult:
    failures: list[str] = []
    for settlement in _records_by_type(case, "settlements"):
        settlement_day = _settlement_day(settlement)
        if settlement_day is None:
            continue
        expected_bank = expected_bank_date(settlement_day, policy)
        declared = settlement.event_date
        if declared is not None and declared != expected_bank:
            failures.append(
                f"{settlement.entity_id}: expected bank date {expected_bank}, declared {declared}"
            )
    if failures:
        return _fail("INV-009", "; ".join(failures), affected_entities=case.source_entity_ids)
    return _pass("INV-009", "settlement timing uses bound policy calendar")


def _verify_control_totals(case: ReconciliationCase) -> InvariantResult:
    if case.invalid_reasons:
        return _fail(
            "INV-010",
            "invalid source records prevent clean sign-off",
            affected_entities=case.source_entity_ids,
        )
    return _pass("INV-010", "no material source-level control failure")


def _verify_fee_policy(case: ReconciliationCase, policy: SettlementPolicy) -> InvariantResult:
    failures: list[str] = []
    fs = policy.fee_schedule
    for payment in _records_by_type(case, "payments"):
        if payment.amount_paise is None or payment.payment_id is None:
            continue
        expected_fee = (
            payment.amount_paise * fs.gateway_fee_percentage
        ) // fs.gateway_fee_percentage_denominator
        actual_fee = sum(
            component.amount_paise or 0
            for component in _components_for_payment(
                case,
                payment.payment_id,
                ComponentType.GATEWAY_FEE,
            )
        )
        if actual_fee != expected_fee:
            failures.append(
                f"{payment.entity_id}: expected fee {expected_fee}, actual {actual_fee}"
            )
    if failures:
        return _fail("INV-FEE-001", "; ".join(failures), affected_entities=case.source_entity_ids)
    return _pass("INV-FEE-001", "gateway fee matches policy")


def _verify_tax_policy(case: ReconciliationCase, policy: SettlementPolicy) -> InvariantResult:
    failures: list[str] = []
    fs = policy.fee_schedule
    for payment in _records_by_type(case, "payments"):
        if payment.amount_paise is None or payment.payment_id is None:
            continue
        expected_fee = (
            payment.amount_paise * fs.gateway_fee_percentage
        ) // fs.gateway_fee_percentage_denominator
        expected_tax = (
            expected_fee * fs.tax_on_fee_percentage
        ) // fs.tax_on_fee_percentage_denominator
        actual_tax = sum(
            component.amount_paise or 0
            for component in _components_for_payment(
                case,
                payment.payment_id,
                ComponentType.TAX_ON_FEE,
            )
        )
        if actual_tax != expected_tax:
            failures.append(
                f"{payment.entity_id}: expected tax {expected_tax}, actual {actual_tax}"
            )
    if failures:
        return _fail("INV-TAX-001", "; ".join(failures), affected_entities=case.source_entity_ids)
    return _pass("INV-TAX-001", "tax on fee matches policy")


def verify_case(
    case: ReconciliationCase,
    evidence: EvidenceGraph,
    policy: SettlementPolicy,
    allocation_invariant: InvariantResult | None = None,
) -> list[InvariantResult]:
    """Run all deterministic invariants for a case."""
    edges = _case_edges(case, evidence)
    records = _record_map(case)
    return [
        _verify_currency(case),
        _verify_order_payment_amount(case, edges, records),
        _verify_settlement_composition(case),
        _verify_settlement_bank_receipt(case, edges),
        _verify_zero_residual(case, edges),
        allocation_invariant or verify_allocation_uniqueness(evidence),
        _verify_temporal_validity(case, edges, records),
        _verify_lifecycle_validity(case, edges, records),
        _verify_sla_validity(case, policy),
        _verify_control_totals(case),
        _verify_fee_policy(case, policy),
        _verify_tax_policy(case, policy),
    ]


def verify_suggested_relationship(
    case: ReconciliationCase,
    candidate: CandidateRelationship,
    existing_edges: list[EvidenceEdge],
) -> list[VerificationCheck]:
    """Deterministically verify one precomputed AI-ranked relationship.

    These checks establish that the suggestion is safe to show a reviewer. They do not
    turn it into a verified financial allocation or sign off the full case.
    """
    records = _record_map(case)
    source = records.get(candidate.source_entity_id)
    target = records.get(candidate.target_entity_id)
    candidate_keys = {
        (
            item.source_entity_id,
            item.target_entity_id,
            item.relationship_type,
            item.rule_id,
            item.allocated_amount_paise,
        )
        for item in case.candidate_relationships + case.ambiguous_candidates
    }
    key = (
        candidate.source_entity_id,
        candidate.target_entity_id,
        candidate.relationship_type,
        candidate.rule_id,
        candidate.allocated_amount_paise,
    )

    def check(
        check_id: str,
        passed: bool,
        message: str,
        *,
        expected: str | int | None = None,
        actual: str | int | None = None,
        entities: list[str] | None = None,
    ) -> VerificationCheck:
        return VerificationCheck(
            check_id=check_id,
            passed=passed,
            expected_value=expected,
            actual_value=actual,
            affected_entities=entities or [],
            message=message,
        )

    source_amount = source.amount_paise if source else None
    target_amount = target.amount_paise if target else None
    source_currency = source.currency if source else None
    target_currency = target.currency if target else None
    settlement_day = _settlement_day(source) if source else None
    bank_day = target.value_date if target else None
    verified_conflicts = [
        edge
        for edge in existing_edges
        if edge.decision_level == DecisionLevel.VERIFIED
        and edge.relationship_type == candidate.relationship_type
        and (
            edge.source_entity_id in {candidate.source_entity_id, candidate.target_entity_id}
            or edge.target_entity_id in {candidate.source_entity_id, candidate.target_entity_id}
        )
        and (
            edge.source_entity_id != candidate.source_entity_id
            or edge.target_entity_id != candidate.target_entity_id
        )
    ]
    return [
        check(
            "AI-INV-001",
            key in candidate_keys,
            "relationship is a precomputed candidate",
            entities=[candidate.source_entity_id, candidate.target_entity_id],
        ),
        check(
            "AI-INV-002",
            source is not None and target is not None,
            "candidate entities belong to this case",
            expected="both entities in case",
            actual=(
                "both present"
                if source is not None and target is not None
                else "entity missing"
            ),
            entities=[candidate.source_entity_id, candidate.target_entity_id],
        ),
        check(
            "AI-INV-003",
            candidate.relationship_type == "settlement_bank"
            and source is not None
            and source.source_type == "settlements"
            and target is not None
            and target.source_type == "bank_transactions",
            "relationship has the allowed settlement-to-bank shape",
            expected="settlements->bank_transactions",
            actual=(
                f"{source.source_type if source else 'missing'}->"
                f"{target.source_type if target else 'missing'}"
            ),
            entities=[candidate.source_entity_id, candidate.target_entity_id],
        ),
        check(
            "AI-INV-004",
            source_amount is not None
            and target_amount is not None
            and candidate.allocated_amount_paise == source_amount == target_amount,
            "precomputed allocation equals both source amounts",
            expected=source_amount,
            actual=target_amount,
            entities=[candidate.source_entity_id, candidate.target_entity_id],
        ),
        check(
            "AI-INV-005",
            source_currency is not None and source_currency == target_currency,
            "candidate currencies agree",
            expected=source_currency,
            actual=target_currency,
            entities=[candidate.source_entity_id, candidate.target_entity_id],
        ),
        check(
            "AI-INV-006",
            settlement_day is not None and bank_day is not None and bank_day >= settlement_day,
            "bank value date does not precede settlement",
            expected=settlement_day.isoformat() if settlement_day else None,
            actual=bank_day.isoformat() if bank_day else None,
            entities=[candidate.source_entity_id, candidate.target_entity_id],
        ),
        check(
            "AI-INV-007",
            not verified_conflicts,
            "suggestion does not conflict with a verified allocation",
            expected=0,
            actual=len(verified_conflicts),
            entities=[candidate.source_entity_id, candidate.target_entity_id],
        ),
    ]
