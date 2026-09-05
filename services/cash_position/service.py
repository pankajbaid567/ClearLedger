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


def cash_bucket_contribution(
    bucket: CashBucket | str | None,
    net_amount_paise: int,
    residual_paise: int,
    gross_amount_paise: int,
) -> tuple[int, str]:
    """The single definition used by aggregates, row drilldowns and exports."""
    if bucket in {
        CashBucket.BANK_CONFIRMED,
        CashBucket.SETTLEMENT_CONFIRMED_IN_TRANSIT,
        CashBucket.EXPECTED_SETTLEMENT,
    }:
        return net_amount_paise, "NET_SETTLEMENT"
    if residual_paise:
        return abs(residual_paise), "ABSOLUTE_RESIDUAL"
    if net_amount_paise:
        return abs(net_amount_paise), "ABSOLUTE_NET_EXPOSURE"
    return abs(gross_amount_paise), "ABSOLUTE_GROSS_EXPOSURE"


def _case_amount(case: ReconciliationCase) -> int:
    return cash_bucket_contribution(
        case.cash_bucket, case.net_amount_paise, case.residual_paise, case.gross_amount_paise
    )[0]


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
    settlement_in_transit = bucket_amounts[CashBucket.SETTLEMENT_CONFIRMED_IN_TRANSIT].amount_paise
    # Components have already been applied to settlement net. They are recorded
    # deductions, not new future obligations. Transit is not available bank cash.
    # This is confirmed net movement in this batch, not a whole-account balance.
    safe_cash = bank_confirmed
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
    "cash_bucket_contribution",
    "calculate_tax_audit",
]
