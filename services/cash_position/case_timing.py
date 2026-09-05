"""Source-event age and contractual deadlines, independent of database row age."""

from __future__ import annotations

from datetime import UTC, date, datetime, time
from math import ceil
from typing import Any
from zoneinfo import ZoneInfo

from services.normalization.dates import (
    expected_bank_date,
    expected_settlement_date,
    parse_date,
)
from services.normalization.policy import SettlementPolicy


def _timestamp(value: Any, timezone: str) -> datetime | None:
    if isinstance(value, datetime):
        return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)
    if not value:
        return None
    try:
        return parse_date(str(value), timezone)
    except (ValueError, TypeError):
        return None


def case_timing(
    records: list[dict[str, Any]],
    *,
    as_of: datetime,
    policy: SettlementPolicy | None,
    case_state: str,
    review_deadline: date | None = None,
) -> dict[str, Any]:
    """Unknown source/policy facts remain null; all ages share the run cutoff."""
    timezone = policy.timezone if policy else "UTC"
    anchor = _timestamp(as_of, timezone)
    assert anchor is not None
    events: dict[str, list[datetime]] = {}
    deadlines: list[date] = []
    for record in records:
        source = str(record.get("source_type", ""))
        raw = record.get("raw_values") or {}
        event = _timestamp(record.get("event_at"), timezone)
        if event is None:
            for key in (
                "captured_at",
                "order_created_at",
                "processed_at",
                "initiated_at",
                "posted_at",
            ):
                event = _timestamp(raw.get(key), timezone)
                if event is not None:
                    break
        if event is not None:
            events.setdefault(source, []).append(event)
        if source == "settlements" and policy is not None:
            # Derive the contractual deadline from processing and the bound
            # calendar, rather than interpreting synthetic identifier prefixes.
            if event is not None:
                deadlines.append(
                    expected_bank_date(event.astimezone(ZoneInfo(timezone)).date(), policy)
                )
    origin: datetime | None = None
    for source in ("payments", "orders", "settlements", "bank_transactions"):
        if events.get(source):
            origin = min(events[source])
            break
    if not deadlines and events.get("payments") and policy is not None:
        deadlines = [
            expected_bank_date(expected_settlement_date(event, policy), policy)
            for event in events["payments"]
        ]
    # The earliest outstanding deadline makes partially late batches visible.
    due = (
        datetime.combine(min(deadlines), time.max, tzinfo=ZoneInfo(timezone)).astimezone(UTC)
        if deadlines
        else None
    )
    return {
        "event_at": origin,
        "age_days": max(0, (anchor.date() - origin.date()).days) if origin else None,
        "sla_due_at": due,
        "days_past_sla": (
            0
            if case_state == "RECONCILED"
            else max(0, ceil((anchor - due).total_seconds() / 86400))
        )
        if due
        else None,
        "review_due_at": datetime.combine(
            review_deadline, time.max, tzinfo=ZoneInfo(timezone)
        ).astimezone(UTC)
        if review_deadline
        else None,
    }
