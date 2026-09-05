"""Canonical source-record normalization."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from packages.domain.enums import Direction, IngestionQuality
from services.normalization.identifiers import extract_tokens_from_narration, normalize_id
from services.reconciliation.models import (
    NormalizedField,
    NormalizedRecord,
    RawSourceRow,
    RowIssue,
)

_ID_FIELDS = {
    "order_id",
    "payment_id",
    "settlement_id",
    "component_id",
    "bank_transaction_id",
    "merchant_id",
    "account_id",
    "source_event_id",
    "utr",
    "gateway_reference",
}

_STATUS_FIELDS = {
    "payment_status",
    "settlement_status",
    "expected_payment_status",
}


def _raw_value(row: RawSourceRow, field_name: str) -> str | None:
    value = row.raw_values.get(field_name)
    if value is None or value == "":
        return None
    return value


def _record_value(row: RawSourceRow, field_name: str) -> Any:
    if row.record is not None and hasattr(row.record, field_name):
        return getattr(row.record, field_name)
    return _raw_value(row, field_name)


def _safe_normalize(value: Any) -> str | None:
    if value is None or value == "":
        return None
    try:
        return normalize_id(str(value))
    except ValueError:
        return None


def _safe_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _normalized_fields(row: RawSourceRow) -> dict[str, NormalizedField]:
    fields: dict[str, NormalizedField] = {}
    names = set(row.raw_values)
    if row.record is not None:
        names.update(type(row.record).model_fields)
    for name in sorted(names):
        value = _record_value(row, name)
        if name in _ID_FIELDS:
            normalized = _safe_normalize(value)
            rule_id = "IDENTIFIER_NORMALIZE_V1"
        elif name in _STATUS_FIELDS:
            normalized = str(value).strip().upper() if value is not None else None
            rule_id = "STATE_NORMALIZE_V1"
        elif name == "direction":
            normalized = str(value).strip().upper() if value is not None else None
            rule_id = "DIRECTION_NORMALIZE_V1"
        elif name == "currency":
            normalized = str(value).strip().upper() if value is not None else None
            rule_id = "CURRENCY_NORMALIZE_V1"
        else:
            if isinstance(value, int):
                normalized = value
            elif value is not None:
                normalized = str(value)
            else:
                normalized = None
            rule_id = "RAW_PRESERVE_V1"
        fields[name] = NormalizedField(raw=value, normalized=normalized, rule_id=rule_id)
    return fields


def _entity_id(row: RawSourceRow, fields: dict[str, NormalizedField]) -> str:
    candidates = {
        "orders": "order_id",
        "payments": "payment_id",
        "settlements": "settlement_id",
        "settlement_components": "component_id",
        "bank_transactions": "bank_transaction_id",
    }
    id_field = candidates.get(row.source_type)
    if id_field and id_field in fields and fields[id_field].normalized:
        return str(fields[id_field].normalized)
    normalized = _safe_normalize(row.source_record_id)
    return normalized or row.source_record_id


def _field_str(fields: dict[str, NormalizedField], name: str) -> str | None:
    value = fields.get(name)
    if value is None or value.normalized is None:
        return None
    return str(value.normalized)


def _direction_value(row: RawSourceRow, fields: dict[str, NormalizedField]) -> str | None:
    raw = _record_value(row, "direction")
    if isinstance(raw, Direction):
        return raw.value
    return _field_str(fields, "direction")


def _signed_amount(
    row: RawSourceRow,
    amount_paise: int | None,
    direction: str | None,
) -> int | None:
    if amount_paise is None:
        return None
    if direction == Direction.DEBIT.value:
        return -amount_paise
    return amount_paise


def _primary_amount(row: RawSourceRow) -> int | None:
    for field_name in ("order_amount_paise", "amount_paise", "net_amount_paise"):
        value = _record_value(row, field_name)
        parsed = _safe_int(value)
        if parsed is not None:
            return parsed
    return None


def _primary_event_at(record: Any) -> datetime | None:
    for field_name in (
        "captured_at",
        "processed_at",
        "initiated_at",
        "posted_at",
        "order_created_at",
    ):
        if hasattr(record, field_name):
            value = getattr(record, field_name)
            if isinstance(value, datetime):
                return value
    return None


def _primary_event_date(record: Any, event_at: datetime | None) -> date | None:
    if hasattr(record, "expected_bank_date") and isinstance(record.expected_bank_date, date):
        return record.expected_bank_date
    if hasattr(record, "value_date") and isinstance(record.value_date, date):
        return record.value_date
    return event_at.date() if event_at is not None else None


def _build_normalized_record(row: RawSourceRow) -> NormalizedRecord:
    fields = _normalized_fields(row)
    entity_id = _entity_id(row, fields)
    amount_paise = _primary_amount(row)
    direction = _direction_value(row, fields)
    signed_amount_paise = _signed_amount(row, amount_paise, direction)
    event_at = _primary_event_at(row.record)
    event_date = _primary_event_date(row.record, event_at) if row.record is not None else None
    narration = _raw_value(row, "narration") or ""
    status = (
        _field_str(fields, "payment_status")
        or _field_str(fields, "settlement_status")
        or _field_str(fields, "expected_payment_status")
    )

    return NormalizedRecord(
        source_type=row.source_type,
        source_record_id=entity_id,
        entity_id=entity_id,
        row_number=row.row_number,
        raw_values=row.raw_values,
        raw_record=row.record,
        quality=row.quality,
        issues=list(row.issues),
        normalized_fields=fields,
        narration_tokens=extract_tokens_from_narration(narration),
        merchant_id=_field_str(fields, "merchant_id"),
        account_id=_field_str(fields, "account_id"),
        order_id=_field_str(fields, "order_id"),
        payment_id=_field_str(fields, "payment_id"),
        settlement_id=_field_str(fields, "settlement_id"),
        component_id=_field_str(fields, "component_id"),
        bank_transaction_id=_field_str(fields, "bank_transaction_id"),
        source_event_id=_field_str(fields, "source_event_id"),
        component_type=_field_str(fields, "component_type"),
        status=status,
        direction=direction,
        amount_paise=amount_paise,
        signed_amount_paise=signed_amount_paise,
        currency=_field_str(fields, "currency"),
        event_at=event_at,
        event_date=event_date,
        value_date=event_date if row.source_type == "bank_transactions" else None,
    )


def normalize_records(raw_records: list[RawSourceRow]) -> list[NormalizedRecord]:
    """Normalize records while preserving raw values and rule provenance."""
    normalized: list[NormalizedRecord] = []
    for row in raw_records:
        try:
            normalized.append(_build_normalized_record(row))
        except Exception as exc:  # pragma: no cover - defensive visibility path
            normalized.append(
                NormalizedRecord(
                    source_type=row.source_type,
                    source_record_id=row.source_record_id,
                    entity_id=row.source_record_id,
                    row_number=row.row_number,
                    raw_values=row.raw_values,
                    raw_record=row.record,
                    quality=IngestionQuality.INVALID,
                    issues=row.issues
                    + [
                        RowIssue(
                            field="__row__",
                            value=row.source_record_id,
                            reason=f"normalization failed: {exc}",
                        )
                    ],
                )
            )
    return normalized
