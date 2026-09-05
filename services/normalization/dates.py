"""Date parsing and settlement-calendar policy helpers."""

from __future__ import annotations

from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from services.normalization.policy import SettlementPolicy


def _zoneinfo(timezone_name: str) -> ZoneInfo:
    try:
        return ZoneInfo(timezone_name)
    except ZoneInfoNotFoundError as exc:
        raise ValueError(f"unknown timezone: {timezone_name}") from exc


def parse_date(raw: str, timezone: str = "Asia/Kolkata") -> datetime:
    """Parse a date or timestamp into a canonical UTC-aware datetime."""
    if raw is None:
        raise ValueError("date cannot be None")
    value = raw.strip()
    if not value:
        raise ValueError("date cannot be empty")

    tz = _zoneinfo(timezone)
    try:
        if len(value) == 10:
            parsed = datetime.combine(date.fromisoformat(value), time.min, tzinfo=tz)
        else:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=tz)
    except ValueError as exc:
        raise ValueError(f"invalid date: {raw!r}") from exc

    return parsed.astimezone(UTC)


def is_business_day(
    d: date,
    holidays: list[date] | tuple[date, ...],
    weekend_days: list[int] | tuple[int, ...] = (5, 6),
) -> bool:
    return d.weekday() not in weekend_days and d not in holidays


def next_business_day(
    d: date,
    holidays: list[date] | tuple[date, ...],
    weekend_days: list[int] | tuple[int, ...] = (5, 6),
) -> date:
    candidate = d
    while not is_business_day(candidate, holidays, weekend_days):
        candidate += timedelta(days=1)
    return candidate


def expected_settlement_date(capture_date: datetime, policy: SettlementPolicy) -> date:
    """Apply T+N, cutoff, weekend, and holiday settlement policy."""
    local_capture = capture_date.astimezone(_zoneinfo(policy.timezone))
    base_date = local_capture.date()
    if local_capture.time() > policy.cutoff_time:
        base_date += timedelta(days=1)
    raw_due = base_date + timedelta(days=policy.capture_to_settlement_days)
    return next_business_day(raw_due, policy.holidays, policy.weekend_days)


def expected_bank_date(settlement_date: date, policy: SettlementPolicy) -> date:
    """Apply settlement-to-bank delay and business calendar shifting."""
    raw_due = settlement_date + timedelta(days=policy.settlement_to_bank_days)
    return next_business_day(raw_due, policy.holidays, policy.weekend_days)


def is_within_sla(event_date: date | None, deadline: date, reference_date: date) -> bool:
    """Return whether an observed or still-missing event is within the policy deadline."""
    if event_date is not None:
        return event_date <= deadline
    return reference_date <= deadline
