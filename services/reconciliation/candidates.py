"""Bounded deterministic candidate generation."""

from __future__ import annotations

from datetime import date

from generator.schemas import SettlementRecord
from services.normalization.dates import expected_bank_date
from services.normalization.policy import SettlementPolicy
from services.reconciliation.models import CandidateRelationship, NormalizedRecord

_ORDER_PAYMENT_SCORE = 100
_SETTLEMENT_MEMBERSHIP_SCORE = 95
_UTR_BANK_SCORE = 90
_BANK_REFERENCE_SCORE = 80
_AMOUNT_WINDOW_SCORE = 60


def _records(
    normalized_records: list[NormalizedRecord], source_type: str
) -> list[NormalizedRecord]:
    return [r for r in normalized_records if r.source_type == source_type]


def _field_value(record: NormalizedRecord, field_name: str) -> str | None:
    field = record.normalized_fields.get(field_name)
    if field is None or field.normalized is None:
        return None
    return str(field.normalized)


def _settlement_date(record: NormalizedRecord) -> date | None:
    raw = record.raw_record
    if isinstance(raw, SettlementRecord):
        if raw.processed_at is not None:
            return raw.processed_at.date()
        return raw.initiated_at.date()
    if record.event_at is not None:
        return record.event_at.date()
    return None


def _date_in_bank_window(
    settlement: NormalizedRecord,
    bank: NormalizedRecord,
    policy: SettlementPolicy,
) -> bool:
    if bank.value_date is None:
        return False
    settlement_day = _settlement_date(settlement)
    if settlement_day is None:
        return False
    policy_due = expected_bank_date(settlement_day, policy)
    declared_due = settlement.event_date or policy_due
    deadline = max(policy_due, declared_due)
    return settlement_day <= bank.value_date <= deadline


def _same_currency(left: NormalizedRecord, right: NormalizedRecord) -> bool:
    if left.currency is None or right.currency is None:
        return True
    return left.currency == right.currency


def _same_merchant(left: NormalizedRecord, right: NormalizedRecord) -> bool:
    if left.merchant_id is None or right.merchant_id is None:
        return True
    return left.merchant_id == right.merchant_id


def _amount_matches(left_amount: int | None, right_amount: int | None) -> bool:
    return left_amount is not None and right_amount is not None and left_amount == right_amount


def _candidate_reasons(
    *,
    currency: bool,
    merchant: bool,
    amount: bool,
    date_window: bool = True,
) -> list[str]:
    reasons: list[str] = []
    if not currency:
        reasons.append("currency conflict")
    if not merchant:
        reasons.append("merchant conflict")
    if not amount:
        reasons.append("amount mismatch")
    if not date_window:
        reasons.append("date outside policy")
    return reasons


def _bank_utr_values(bank: NormalizedRecord) -> set[str]:
    values: set[str] = set()
    utr = _field_value(bank, "utr")
    if utr:
        values.add(utr)
    for token in bank.narration_tokens.get("utr_values", []):
        values.add(token.normalized)
    return values


def _bank_settlement_tokens(bank: NormalizedRecord) -> set[str]:
    return {token.normalized for token in bank.narration_tokens.get("settlement_ids", [])}


def _append_unique(
    candidates: list[CandidateRelationship],
    candidate: CandidateRelationship,
    seen: set[tuple[str, str, str, str]],
) -> None:
    key = (
        candidate.source_entity_id,
        candidate.target_entity_id,
        candidate.relationship_type,
        candidate.rule_id,
    )
    if key not in seen:
        seen.add(key)
        candidates.append(candidate)


def _payment_net_by_settlement(records: list[NormalizedRecord]) -> dict[tuple[str, str], int]:
    totals: dict[tuple[str, str], int] = {}
    for component in _records(records, "settlement_components"):
        if component.source_event_id is None or component.settlement_id is None:
            continue
        signed = component.signed_amount_paise
        if signed is None:
            continue
        key = (component.source_event_id, component.settlement_id)
        totals[key] = totals.get(key, 0) + signed
    return totals


def generate_candidates(
    normalized_records: list[NormalizedRecord],
    policy: SettlementPolicy,
) -> list[CandidateRelationship]:
    """Generate bounded candidate relationships from strongest to weakest evidence."""
    orders = _records(normalized_records, "orders")
    payments = _records(normalized_records, "payments")
    settlements = _records(normalized_records, "settlements")
    banks = _records(normalized_records, "bank_transactions")
    candidates: list[CandidateRelationship] = []
    seen: set[tuple[str, str, str, str]] = set()

    payments_by_order: dict[str, list[NormalizedRecord]] = {}
    for payment in payments:
        if payment.order_id:
            payments_by_order.setdefault(payment.order_id, []).append(payment)

    for order in orders:
        if order.order_id is None:
            continue
        for payment in payments_by_order.get(order.order_id, []):
            amount_ok = _amount_matches(order.amount_paise, payment.amount_paise)
            currency_ok = _same_currency(order, payment)
            merchant_ok = _same_merchant(order, payment)
            _append_unique(
                candidates,
                CandidateRelationship(
                    source_entity_id=order.entity_id,
                    target_entity_id=payment.entity_id,
                    relationship_type="order_payment",
                    evidence_fields=["order.order_id", "payment.order_id"],
                    match_strength_score=_ORDER_PAYMENT_SCORE,
                    rule_id="exact_order_payment",
                    source_record_type=order.source_type,
                    target_record_type=payment.source_type,
                    allocated_amount_paise=payment.amount_paise or order.amount_paise or 0,
                    rejected_reasons=_candidate_reasons(
                        currency=currency_ok,
                        merchant=merchant_ok,
                        amount=amount_ok,
                    ),
                ),
                seen,
            )

    payment_net = _payment_net_by_settlement(normalized_records)
    settlements_by_id = {
        settlement.settlement_id: settlement
        for settlement in settlements
        if settlement.settlement_id is not None
    }
    payments_by_id = {
        payment.payment_id: payment for payment in payments if payment.payment_id is not None
    }
    for (payment_id, settlement_id), net in sorted(payment_net.items()):
        payment = payments_by_id.get(payment_id)
        settlement = settlements_by_id.get(settlement_id)
        if payment is None or settlement is None:
            continue
        _append_unique(
            candidates,
            CandidateRelationship(
                source_entity_id=payment.entity_id,
                target_entity_id=settlement.entity_id,
                relationship_type="payment_settlement",
                evidence_fields=[
                    "settlement_component.source_event_id",
                    "settlement_component.settlement_id",
                ],
                match_strength_score=_SETTLEMENT_MEMBERSHIP_SCORE,
                rule_id="settlement_membership",
                source_record_type=payment.source_type,
                target_record_type=settlement.source_type,
                allocated_amount_paise=net,
                rejected_reasons=_candidate_reasons(
                    currency=_same_currency(payment, settlement),
                    merchant=_same_merchant(payment, settlement),
                    amount=True,
                ),
            ),
            seen,
        )

    for settlement in settlements:
        settlement_utr = _field_value(settlement, "utr")
        settlement_tokens = {settlement.settlement_id} if settlement.settlement_id else set()
        for bank in banks:
            amount_ok = _amount_matches(settlement.amount_paise, bank.signed_amount_paise)
            currency_ok = _same_currency(settlement, bank)
            merchant_ok = _same_merchant(settlement, bank)
            date_ok = _date_in_bank_window(settlement, bank, policy)
            reasons = _candidate_reasons(
                currency=currency_ok,
                merchant=merchant_ok,
                amount=amount_ok,
                date_window=date_ok,
            )
            bank_utrs = _bank_utr_values(bank)
            if settlement_utr and settlement_utr in bank_utrs:
                _append_unique(
                    candidates,
                    CandidateRelationship(
                        source_entity_id=settlement.entity_id,
                        target_entity_id=bank.entity_id,
                        relationship_type="settlement_bank",
                        evidence_fields=["settlement.utr", "bank.utr"],
                        match_strength_score=_UTR_BANK_SCORE,
                        rule_id="settlement_utr_bank",
                        source_record_type=settlement.source_type,
                        target_record_type=bank.source_type,
                        allocated_amount_paise=bank.signed_amount_paise or 0,
                        rejected_reasons=reasons,
                    ),
                    seen,
                )

            if settlement_tokens & _bank_settlement_tokens(bank):
                _append_unique(
                    candidates,
                    CandidateRelationship(
                        source_entity_id=settlement.entity_id,
                        target_entity_id=bank.entity_id,
                        relationship_type="settlement_bank",
                        evidence_fields=[
                            "bank.narration.settlement_id",
                            "bank.amount",
                            "bank.value_date",
                        ],
                        match_strength_score=_BANK_REFERENCE_SCORE,
                        rule_id="bank_reference_amount_date",
                        source_record_type=settlement.source_type,
                        target_record_type=bank.source_type,
                        allocated_amount_paise=bank.signed_amount_paise or 0,
                        rejected_reasons=reasons,
                    ),
                    seen,
                )

            if amount_ok and currency_ok and merchant_ok and date_ok:
                _append_unique(
                    candidates,
                    CandidateRelationship(
                        source_entity_id=settlement.entity_id,
                        target_entity_id=bank.entity_id,
                        relationship_type="settlement_bank",
                        evidence_fields=[
                            "settlement.net_amount_paise",
                            "bank.signed_amount_paise",
                            "bank.value_date",
                        ],
                        match_strength_score=_AMOUNT_WINDOW_SCORE,
                        rule_id="unique_exact_amount_window",
                        source_record_type=settlement.source_type,
                        target_record_type=bank.source_type,
                        allocated_amount_paise=bank.signed_amount_paise or 0,
                        rejected_reasons=[],
                        metadata={"date_window_valid": True},
                    ),
                    seen,
                )

    return candidates
