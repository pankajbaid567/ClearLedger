"""Forward Cash Forecasting (T+0 to T+7) engine."""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from packages.domain.enums import CashBucket
from services.normalization.dates import is_business_day, next_business_day
from services.normalization.policy import SettlementPolicy
from services.reconciliation.models import ReconciliationCase


class CashForecastDay(BaseModel):
    """Daily projected cash flow entry in the forecast horizon."""

    model_config = ConfigDict(strict=True, frozen=True)

    day_offset: int
    label: str
    date: str
    is_banking_day: bool
    opening_cash_paise: int
    expected_inflow_paise: int
    scheduled_deductions_paise: int
    closing_cash_paise: int
    confidence_score: float | None = None
    confidence_basis: str = "SCHEDULE_ONLY_NOT_CALIBRATED"
    case_count: int
    case_ids: list[str] = Field(default_factory=list)
    settlement_ids: list[str] = Field(default_factory=list)


class CashForecastResponse(BaseModel):
    """Container for the complete T+0 to T+7 forward cash forecast."""

    model_config = ConfigDict(strict=True, frozen=True)

    run_id: str
    as_of_date: str
    currency: str
    days: list[CashForecastDay]
    total_projected_inflow_paise: int
    baseline_safe_cash_paise: int
    projected_final_cash_paise: int
    forecast_scope: str = "SETTLEMENT_RECEIPTS_ONLY"
    overdue_inflow_paise: int = 0
    undated_inflow_paise: int = 0


def _extract_settlement_date(case: ReconciliationCase) -> tuple[date | None, str | None]:
    """Extract expected bank landing date and settlement id from case records."""
    for record in case.records:
        if record.source_type == "settlements":
            settle_date: date | None = None
            if record.event_date is not None:
                settle_date = record.event_date
            elif (
                record.raw_record is not None
                and hasattr(record.raw_record, "expected_bank_date")
                and isinstance(record.raw_record.expected_bank_date, date)
            ):
                settle_date = record.raw_record.expected_bank_date
            elif record.raw_values and "expected_bank_date" in record.raw_values:
                try:
                    settle_date = date.fromisoformat(record.raw_values["expected_bank_date"])
                except ValueError:
                    pass
            elif record.event_at is not None:
                settle_date = record.event_at.date()
            if settle_date is not None:
                return settle_date, record.settlement_id
    return None, None


def _extract_case_from_dict(raw: dict[str, Any]) -> tuple[date | None, str | None, int, str]:
    """Helper for reading cases from serialized dictionary snapshots."""
    case_id = raw.get("case_id", "")
    net_paise = raw.get("net_amount_paise", 0)
    records = raw.get("records") or raw.get("record_snapshot") or []
    for r in records:
        if isinstance(r, dict) and r.get("source_type") == "settlements":
            raw_vals = r.get("raw_values", {})
            event_date_str = r.get("event_date") or raw_vals.get("expected_bank_date")
            settlement_id = r.get("settlement_id")
            if event_date_str:
                try:
                    if isinstance(event_date_str, date):
                        return event_date_str, settlement_id, net_paise, case_id
                    return (
                        date.fromisoformat(str(event_date_str)[:10]),
                        settlement_id,
                        net_paise,
                        case_id,
                    )
                except ValueError:
                    pass
    return None, None, net_paise, case_id


def calculate_cash_forecast(
    cases: list[ReconciliationCase] | list[dict[str, Any]],
    as_of_date: date | str | None = None,
    policy: SettlementPolicy | None = None,
    run_id: str = "",
    currency: str = "INR",
    safe_cash_paise: int | None = None,
) -> CashForecastResponse:
    """Calculate daily cash inflows and projected liquidity across T+0 to T+7."""
    holidays = policy.holidays if policy is not None else ()
    weekend_days = policy.weekend_days if policy is not None else (5, 6)

    # 1. Normalize cases and extract in-transit / expected settlement events
    # Items: (date, settlement_id, amount, case_id)
    in_transit_events: list[tuple[date, str, int, str]] = []
    bank_confirmed_paise = 0
    undated_inflow = 0

    for c in cases:
        if isinstance(c, ReconciliationCase):
            bucket = c.cash_bucket
            case_id = c.case_id
            net_paise = c.net_amount_paise
            if bucket == CashBucket.BANK_CONFIRMED:
                bank_confirmed_paise += net_paise
            elif bucket in {
                CashBucket.SETTLEMENT_CONFIRMED_IN_TRANSIT,
                CashBucket.EXPECTED_SETTLEMENT,
            }:
                s_date, s_id = _extract_settlement_date(c)
                if s_date is not None:
                    in_transit_events.append((s_date, s_id or "", net_paise, case_id))
                else:
                    undated_inflow += net_paise
        elif isinstance(c, dict):
            bucket_str = c.get("cash_bucket", "")
            net_paise = c.get("net_amount_paise", 0)
            case_id = c.get("case_id", "")
            if bucket_str == "BANK_CONFIRMED":
                bank_confirmed_paise += net_paise
            elif bucket_str in {"SETTLEMENT_CONFIRMED_IN_TRANSIT", "EXPECTED_SETTLEMENT"}:
                s_date, s_id, _, _ = _extract_case_from_dict(c)
                if s_date is not None:
                    in_transit_events.append((s_date, s_id or "", net_paise, case_id))
                else:
                    undated_inflow += net_paise

    # Baseline safe cash starting liquidity
    baseline_cash = safe_cash_paise if safe_cash_paise is not None else bank_confirmed_paise

    # 2. Determine anchor date (T+0)
    anchor: date
    if as_of_date is not None:
        if isinstance(as_of_date, str):
            anchor = date.fromisoformat(as_of_date)
        elif isinstance(as_of_date, datetime):
            anchor = as_of_date.date()
        else:
            anchor = as_of_date
    else:
        anchor = date.today()

    # Apply the recorded banking calendar. Overdue receipts remain visible as
    # overdue; they are not invented as future inflows on a guessed new date.
    in_transit_events = [
        (next_business_day(d, holidays, weekend_days), sid, amount, cid)
        for d, sid, amount, cid in in_transit_events
    ]
    overdue_inflow = sum(amount for d, _, amount, _ in in_transit_events if d < anchor)

    # 3. Project 8 calendar days (T+0 to T+7)
    days: list[CashForecastDay] = []
    running_cash = baseline_cash
    total_inflow = 0

    for day_offset in range(8):
        current_date = anchor + timedelta(days=day_offset)
        is_banking = is_business_day(current_date, holidays, weekend_days)

        # Collect all in-transit cases scheduled for this exact date
        matching = [item for item in in_transit_events if item[0] == current_date]
        day_inflow = sum(item[2] for item in matching)
        day_case_ids = [item[3] for item in matching]
        day_settlement_ids = [item[1] for item in matching if item[1]]

        opening = running_cash
        day_deductions = 0  # Deductions can be allocated or tracked per day if scheduled
        closing = opening + day_inflow - day_deductions
        running_cash = closing
        total_inflow += day_inflow

        label = "T+0 (As of)" if day_offset == 0 else f"T+{day_offset}"
        days.append(
            CashForecastDay(
                day_offset=day_offset,
                label=label,
                date=current_date.isoformat(),
                is_banking_day=is_banking,
                opening_cash_paise=opening,
                expected_inflow_paise=day_inflow,
                scheduled_deductions_paise=day_deductions,
                closing_cash_paise=closing,
                confidence_score=None,
                case_count=len(matching),
                case_ids=day_case_ids,
                settlement_ids=day_settlement_ids,
            )
        )

    return CashForecastResponse(
        run_id=run_id,
        as_of_date=anchor.isoformat(),
        currency=currency,
        days=days,
        total_projected_inflow_paise=total_inflow,
        baseline_safe_cash_paise=baseline_cash,
        projected_final_cash_paise=running_cash,
        overdue_inflow_paise=overdue_inflow,
        undated_inflow_paise=undated_inflow,
    )
