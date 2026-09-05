"""Cash-confidence bucket calculation."""

from __future__ import annotations

from packages.domain.enums import CashBucket, ComponentType
from services.cash_position.forecast import (
    CashForecastDay,
    CashForecastResponse,
    calculate_cash_forecast,
)
from services.cash_position.tax_audit import (
    TaxAuditSummary,
    TaxDiscrepancyItem,
    calculate_tax_audit,
)
from services.reconciliation.evidence import EvidenceGraph
from services.reconciliation.models import CashPosition, CashPositionBucket, ReconciliationCase


def _case_amount(case: ReconciliationCase) -> int:
    if case.cash_bucket in {
        CashBucket.BANK_CONFIRMED,
        CashBucket.SETTLEMENT_CONFIRMED_IN_TRANSIT,
        CashBucket.EXPECTED_SETTLEMENT,
    }:
        return case.net_amount_paise
    if case.residual_paise:
        return abs(case.residual_paise)
    if case.net_amount_paise:
        return abs(case.net_amount_paise)
    return abs(case.gross_amount_paise)


def _component_total(cases: list[ReconciliationCase], component_type: ComponentType) -> int:
    total = 0
    for case in cases:
        for record in case.records:
            if record.source_type != "settlement_components":
                continue
            if record.component_type == component_type.value:
                total += abs(record.amount_paise or 0)
    return total


def calculate_cash_position(
    cases: list[ReconciliationCase],
    evidence: EvidenceGraph,
) -> CashPosition:
    """Calculate safe cash and confidence buckets from classified cases."""
    del evidence
    bucket_amounts = {
        bucket: CashPositionBucket(bucket=bucket, amount_paise=0, case_ids=[])
        for bucket in CashBucket
    }
    for case in cases:
        bucket = case.cash_bucket
        amount = _case_amount(case)
        current = bucket_amounts[bucket]
        bucket_amounts[bucket] = current.model_copy(
            update={
                "amount_paise": current.amount_paise + amount,
                "case_ids": current.case_ids + [case.case_id],
            }
        )

    scheduled_refunds = _component_total(cases, ComponentType.REFUND)
    known_disputes = _component_total(cases, ComponentType.CHARGEBACK)
    reserve_holds = _component_total(cases, ComponentType.RESERVE_HOLD)
    bank_confirmed = bucket_amounts[CashBucket.BANK_CONFIRMED].amount_paise
    settlement_in_transit = bucket_amounts[
        CashBucket.SETTLEMENT_CONFIRMED_IN_TRANSIT
    ].amount_paise
    safe_cash = (
        bank_confirmed
        + settlement_in_transit
        - scheduled_refunds
        - known_disputes
        - reserve_holds
    )
    return CashPosition(
        buckets=bucket_amounts,
        bank_confirmed_paise=bank_confirmed,
        settlement_confirmed_in_transit_paise=settlement_in_transit,
        expected_settlement_paise=bucket_amounts[CashBucket.EXPECTED_SETTLEMENT].amount_paise,
        at_risk_paise=bucket_amounts[CashBucket.AT_RISK].amount_paise,
        unresolved_paise=bucket_amounts[CashBucket.UNRESOLVED].amount_paise,
        scheduled_refunds_paise=scheduled_refunds,
        known_disputes_paise=known_disputes,
        known_reserve_holds_paise=reserve_holds,
        safe_cash_paise=safe_cash,
    )


__all__ = [
    "CashForecastDay",
    "CashForecastResponse",
    "TaxAuditSummary",
    "TaxDiscrepancyItem",
    "calculate_cash_forecast",
    "calculate_cash_position",
    "calculate_tax_audit",
]
