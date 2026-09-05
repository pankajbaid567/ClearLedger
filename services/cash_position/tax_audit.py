"""Recorded gateway fee and tax consistency under a versioned synthetic policy."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from packages.domain.enums import ComponentType
from services.normalization.policy import SettlementPolicy
from services.reconciliation.models import ReconciliationCase


class TaxDiscrepancyItem(BaseModel):
    """Specific payment/case with a fee or GST tax deduction discrepancy."""

    model_config = ConfigDict(strict=True, frozen=True)

    case_id: str
    payment_id: str
    settlement_id: str | None
    gross_amount_paise: int
    actual_fee_paise: int
    expected_fee_paise: int
    fee_variance_paise: int
    actual_tax_paise: int
    expected_tax_paise: int
    tax_variance_paise: int
    exception_code: str | None
    discrepancy_code: str = "POLICY_VARIANCE"


class TaxAuditSummary(BaseModel):
    """Aggregate fee/tax arithmetic checks; external tax eligibility is not evaluated."""

    model_config = ConfigDict(strict=True, frozen=True)

    run_id: str
    currency: str
    total_cases_audited: int
    gross_payment_volume_paise: int
    total_gateway_fee_paise: int
    expected_gateway_fee_paise: int
    fee_variance_paise: int
    total_tax_paise: int
    expected_tax_paise: int
    tax_variance_paise: int
    claimable_itc_paise: int | None = None
    disputed_tax_paise: int
    tax_policy_pass_rate: float | None
    fee_policy_pass_rate: float | None
    discrepant_case_count: int
    unmatched_component_count: int
    discrepancies: list[TaxDiscrepancyItem] = Field(default_factory=list)
    itc_status: str = "UNAVAILABLE"
    evidence_status: str = "POLICY_ARITHMETIC_ONLY"
    external_tax_statement_available: bool = False
    policy_id: str | None = None
    policy_version: str | None = None
    gateway_fee_rate_numerator: int
    gateway_fee_rate_denominator: int
    tax_rate_numerator: int
    tax_rate_denominator: int
    checked_payment_count: int
    supported_tax_paise: int
    consistency_status: str


def _get_records(c: ReconciliationCase | dict[str, Any]) -> list[Any]:
    if isinstance(c, ReconciliationCase):
        return c.records
    if isinstance(c, dict):
        return c.get("records") or c.get("record_snapshot") or []
    return []


def _get_source_type(r: Any) -> str | None:
    if isinstance(r, dict):
        return r.get("source_type")
    return getattr(r, "source_type", None)


def _get_case_id(c: ReconciliationCase | dict[str, Any]) -> str:
    return c.case_id if isinstance(c, ReconciliationCase) else str(c.get("case_id", ""))


def _get_exception_code(c: ReconciliationCase | dict[str, Any]) -> str | None:
    if isinstance(c, ReconciliationCase):
        return c.exception_code.value if c.exception_code else None
    if isinstance(c, dict):
        return c.get("exception_code")
    return None


def calculate_tax_audit(
    cases: list[ReconciliationCase] | list[dict[str, Any]],
    policy: SettlementPolicy | None = None,
    run_id: str = "",
    currency: str = "INR",
) -> TaxAuditSummary:
    """Compare recorded components with synthetic fee/tax policy; do not infer ITC."""
    # Policy defaults: 200/10000 = 2.0% fee, 1800/10000 = 18.0% GST
    fee_pct = policy.fee_schedule.gateway_fee_percentage if policy else 200
    fee_denom = policy.fee_schedule.gateway_fee_percentage_denominator if policy else 10000
    tax_pct = policy.fee_schedule.tax_on_fee_percentage if policy else 1800
    tax_denom = policy.fee_schedule.tax_on_fee_percentage_denominator if policy else 10000

    total_gross = 0
    total_fee = 0
    expected_fee_total = 0
    total_tax = 0
    expected_tax_total = 0
    claimable_itc = 0
    disputed_tax = 0

    discrepancies: list[TaxDiscrepancyItem] = []
    total_payments_checked = 0
    fee_checks_passed = 0
    tax_checks_passed = 0
    fee_checks_total = 0
    tax_checks_total = 0
    unmatched_component_count = 0

    # Components can be separated from their payment into another case, so linkage
    # validity must be checked against every payment in the execution.
    payment_ids = {
        payment_id
        for case in cases
        for record in _get_records(case)
        if _get_source_type(record) == "payments"
        and (
            payment_id := (
                getattr(record, "payment_id", None)
                or (record.get("payment_id") if isinstance(record, dict) else None)
            )
        )
    }

    for c in cases:
        case_id = _get_case_id(c)
        records = _get_records(c)
        exception_code = _get_exception_code(c)

        # Map settlement id if available
        settlement_id: str | None = None
        for r in records:
            if _get_source_type(r) == "settlements":
                settlement_id = getattr(r, "settlement_id", None) or (
                    r.get("settlement_id") if isinstance(r, dict) else None
                )
                if settlement_id:
                    break

        # Group components by payment_id
        fee_by_payment: dict[str, int] = {}
        tax_by_payment: dict[str, int] = {}
        fee_component_count_by_event: dict[str, int] = {}
        tax_component_count_by_event: dict[str, int] = {}
        settlement_by_event: dict[str, str] = {}

        for r in records:
            if _get_source_type(r) != "settlement_components":
                continue
            c_type = getattr(r, "component_type", None) or (
                r.get("component_type") if isinstance(r, dict) else None
            )
            amt = (
                getattr(r, "amount_paise", None)
                or (r.get("amount_paise") if isinstance(r, dict) else 0)
                or 0
            )
            event_id = (
                getattr(r, "source_event_id", None)
                or (r.get("source_event_id") if isinstance(r, dict) else None)
                or ""
            )
            component_settlement_id = getattr(r, "settlement_id", None) or (
                r.get("settlement_id") if isinstance(r, dict) else None
            )
            if component_settlement_id:
                settlement_by_event.setdefault(event_id, component_settlement_id)

            if c_type in {ComponentType.GATEWAY_FEE.value, "GATEWAY_FEE"}:
                fee_by_payment[event_id] = fee_by_payment.get(event_id, 0) + amt
                fee_component_count_by_event[event_id] = (
                    fee_component_count_by_event.get(event_id, 0) + 1
                )
                total_fee += amt
            elif c_type in {ComponentType.TAX_ON_FEE.value, "TAX_ON_FEE"}:
                tax_by_payment[event_id] = tax_by_payment.get(event_id, 0) + amt
                tax_component_count_by_event[event_id] = (
                    tax_component_count_by_event.get(event_id, 0) + 1
                )
                total_tax += amt

        # Audit each payment in the case
        for r in records:
            if _get_source_type(r) != "payments":
                continue

            pid = (
                getattr(r, "payment_id", None)
                or (r.get("payment_id") if isinstance(r, dict) else None)
                or ""
            )
            p_amount = (
                getattr(r, "amount_paise", None)
                or (r.get("amount_paise") if isinstance(r, dict) else 0)
                or 0
            )

            if not pid or p_amount <= 0:
                continue

            total_payments_checked += 1
            fee_checks_total += 1
            tax_checks_total += 1
            total_gross += p_amount

            # Integer floor division: fee = (gross * 200) // 10000
            expected_fee = (p_amount * fee_pct) // fee_denom
            expected_tax = (expected_fee * tax_pct) // tax_denom

            expected_fee_total += expected_fee
            expected_tax_total += expected_tax

            actual_fee = fee_by_payment.get(pid, 0)
            actual_tax = tax_by_payment.get(pid, 0)

            fee_matches = actual_fee == expected_fee
            tax_matches = actual_tax == expected_tax

            if fee_matches:
                fee_checks_passed += 1
            if tax_matches:
                tax_checks_passed += 1

            if not fee_matches or not tax_matches:
                tax_variance = actual_tax - expected_tax
                fee_variance = actual_fee - expected_fee
                if tax_variance > 0:
                    disputed_tax += tax_variance
                    claimable_itc += expected_tax
                else:
                    claimable_itc += actual_tax

                discrepancies.append(
                    TaxDiscrepancyItem(
                        case_id=case_id,
                        payment_id=pid,
                        settlement_id=settlement_id,
                        gross_amount_paise=p_amount,
                        actual_fee_paise=actual_fee,
                        expected_fee_paise=expected_fee,
                        fee_variance_paise=fee_variance,
                        actual_tax_paise=actual_tax,
                        expected_tax_paise=expected_tax,
                        tax_variance_paise=tax_variance,
                        exception_code=exception_code,
                    )
                )
            else:
                claimable_itc += actual_tax

        orphan_event_ids = sorted((set(fee_by_payment) | set(tax_by_payment)) - payment_ids)
        for event_id in orphan_event_ids:
            actual_fee = fee_by_payment.get(event_id, 0)
            actual_tax = tax_by_payment.get(event_id, 0)
            unmatched_fee_count = fee_component_count_by_event.get(event_id, 0)
            unmatched_tax_count = tax_component_count_by_event.get(event_id, 0)

            unmatched_component_count += unmatched_fee_count + unmatched_tax_count
            fee_checks_total += unmatched_fee_count
            tax_checks_total += unmatched_tax_count
            if actual_tax > 0:
                disputed_tax += actual_tax

            discrepancies.append(
                TaxDiscrepancyItem(
                    case_id=case_id,
                    payment_id=event_id or "[missing source_event_id]",
                    settlement_id=settlement_by_event.get(event_id, settlement_id),
                    gross_amount_paise=0,
                    actual_fee_paise=actual_fee,
                    expected_fee_paise=0,
                    fee_variance_paise=actual_fee,
                    actual_tax_paise=actual_tax,
                    expected_tax_paise=0,
                    tax_variance_paise=actual_tax,
                    exception_code=exception_code,
                    discrepancy_code="SOURCE_EVENT_NOT_FOUND",
                )
            )

    fee_pass_rate = round(fee_checks_passed / fee_checks_total, 4) if fee_checks_total > 0 else None
    tax_pass_rate = round(tax_checks_passed / tax_checks_total, 4) if tax_checks_total > 0 else None

    consistency_status = (
        "DISCREPANCY_FLAGGED"
        if discrepancies
        else "NOT_EVALUATED"
        if not total_payments_checked
        else "CONSISTENT"
    )

    return TaxAuditSummary(
        run_id=run_id,
        currency=currency,
        total_cases_audited=len(cases),
        gross_payment_volume_paise=total_gross,
        total_gateway_fee_paise=total_fee,
        expected_gateway_fee_paise=expected_fee_total,
        fee_variance_paise=total_fee - expected_fee_total,
        total_tax_paise=total_tax,
        expected_tax_paise=expected_tax_total,
        tax_variance_paise=total_tax - expected_tax_total,
        claimable_itc_paise=None,
        supported_tax_paise=claimable_itc,
        checked_payment_count=total_payments_checked,
        policy_id=policy.policy_id if policy else None,
        policy_version=policy.version if policy else None,
        gateway_fee_rate_numerator=fee_pct,
        gateway_fee_rate_denominator=fee_denom,
        tax_rate_numerator=tax_pct,
        tax_rate_denominator=tax_denom,
        consistency_status=consistency_status,
        disputed_tax_paise=disputed_tax,
        tax_policy_pass_rate=tax_pass_rate,
        fee_policy_pass_rate=fee_pass_rate,
        discrepant_case_count=len({item.case_id for item in discrepancies}),
        unmatched_component_count=unmatched_component_count,
        discrepancies=discrepancies,
        itc_status="UNAVAILABLE",
    )
