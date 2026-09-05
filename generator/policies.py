"""Load and validate settlement policy and holiday calendar JSON files."""

from __future__ import annotations

import json
from datetime import date, time
from pathlib import Path

from pydantic import BaseModel, ConfigDict


class FeeSchedule(BaseModel):
    model_config = ConfigDict(frozen=True)

    gateway_fee_percentage: int
    gateway_fee_percentage_denominator: int
    tax_on_fee_percentage: int
    tax_on_fee_percentage_denominator: int
    note: str = ""


class MaterialityRules(BaseModel):
    model_config = ConfigDict(frozen=True)

    amount_variance_threshold_paise: int
    critical_amount_paise: int


class SettlementPolicy(BaseModel):
    model_config = ConfigDict(frozen=True)

    policy_id: str
    version: str
    currency: str
    capture_to_settlement_days: int
    settlement_to_bank_days: int
    cutoff_time: time
    timezone: str
    weekend_rule: str
    holiday_calendar_id: str
    fee_schedule: FeeSchedule
    materiality_rules: MaterialityRules
    effective_from: date
    effective_to: date | None = None


class HolidayEntry(BaseModel):
    model_config = ConfigDict(frozen=True)

    date: date
    name: str


class HolidayCalendar(BaseModel):
    model_config = ConfigDict(frozen=True)

    calendar_id: str
    holidays: list[HolidayEntry]


# ── Defaults ────────────────────────────────────────────────────────────────

_POLICIES_DIR = Path(__file__).resolve().parent.parent / "policies"


def load_policy(policy_path: str | Path | None = None) -> SettlementPolicy:
    path = Path(policy_path) if policy_path else _POLICIES_DIR / "settlement_policy.v1.json"
    with open(path) as f:
        return SettlementPolicy.model_validate(json.load(f))


def load_holidays(calendar_path: str | Path | None = None) -> HolidayCalendar:
    path = Path(calendar_path) if calendar_path else _POLICIES_DIR / "holidays.v1.json"
    with open(path) as f:
        return HolidayCalendar.model_validate(json.load(f))


def holiday_dates(calendar: HolidayCalendar) -> list[date]:
    """Return a sorted list of holiday dates from the calendar."""
    return sorted(h.date for h in calendar.holidays)


# ── Date helpers used by the generator ──────────────────────────────────────

WEEKEND_DAYS = (5, 6)  # Saturday=5, Sunday=6


def is_business_day(d: date, holidays: list[date]) -> bool:
    return d.weekday() not in WEEKEND_DAYS and d not in holidays


def next_business_day(d: date, holidays: list[date]) -> date:
    from datetime import timedelta

    candidate = d
    while not is_business_day(candidate, holidays):
        candidate += timedelta(days=1)
    return candidate


def expected_settlement_date(
    capture_date: date,
    policy: SettlementPolicy,
    holidays: list[date],
) -> date:
    """T+N settlement date, shifted to next business day if needed."""
    from datetime import timedelta

    raw = capture_date + timedelta(days=policy.capture_to_settlement_days)
    return next_business_day(raw, holidays)


def expected_bank_date(
    settlement_date: date,
    policy: SettlementPolicy,
    holidays: list[date],
) -> date:
    """Settlement date + bank processing days, shifted to next business day."""
    from datetime import timedelta

    raw = settlement_date + timedelta(days=policy.settlement_to_bank_days)
    return next_business_day(raw, holidays)
