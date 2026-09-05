"""CSV source ingestion with deterministic validation and visible rejections."""

from __future__ import annotations

import csv
import hashlib
from collections import Counter
from datetime import date, datetime
from enum import Enum
from pathlib import Path
from types import UnionType
from typing import Any, get_args, get_origin

from pydantic import BaseModel, ValidationError

from generator.schemas import (
    BankTransactionRecord,
    OrderRecord,
    PaymentRecord,
    SettlementComponentRecord,
    SettlementRecord,
)
from packages.domain.enums import ExceptionCode, IngestionQuality
from packages.domain.money import parse_money
from services.normalization.dates import parse_date
from services.reconciliation.models import (
    FileMetadata,
    IngestionResult,
    RawSourceRow,
    RowIssue,
)

_SOURCE_CONFIG: dict[str, tuple[type[BaseModel], str, set[str]]] = {
    "orders": (
        OrderRecord,
        "order_id",
        {
            "order_id",
            "merchant_id",
            "order_created_at",
            "order_amount_paise",
            "currency",
            "expected_payment_status",
        },
    ),
    "payments": (
        PaymentRecord,
        "payment_id",
        {
            "payment_id",
            "merchant_id",
            "order_id",
            "payment_status",
            "amount_paise",
            "currency",
            "captured_at",
            "payment_method",
            "gateway_reference",
        },
    ),
    "settlements": (
        SettlementRecord,
        "settlement_id",
        {
            "settlement_id",
            "merchant_id",
            "settlement_status",
            "currency",
            "net_amount_paise",
            "initiated_at",
            "processed_at",
            "expected_bank_date",
            "utr",
        },
    ),
    "settlement_components": (
        SettlementComponentRecord,
        "component_id",
        {
            "component_id",
            "settlement_id",
            "component_type",
            "source_event_id",
            "amount_paise",
            "direction",
        },
    ),
    "bank_transactions": (
        BankTransactionRecord,
        "bank_transaction_id",
        {
            "bank_transaction_id",
            "merchant_id",
            "account_id",
            "posted_at",
            "value_date",
            "direction",
            "amount_paise",
            "currency",
            "narration",
            "utr",
        },
    ),
}


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _canonical_source_type(source_type: str) -> str:
    normalized = source_type.lower().strip().removesuffix(".csv").replace("-", "_")
    aliases = {
        "order": "orders",
        "payment": "payments",
        "settlement": "settlements",
        "component": "settlement_components",
        "components": "settlement_components",
        "settlement_component": "settlement_components",
        "bank": "bank_transactions",
        "bank_transaction": "bank_transactions",
        "bank_transactions": "bank_transactions",
    }
    return aliases.get(normalized, normalized)


def _detect_source_type(headers: set[str], requested: str) -> str:
    matches: list[tuple[str, int]] = []
    for source_type, (_, _, expected_headers) in _SOURCE_CONFIG.items():
        matches.append((source_type, len(headers & expected_headers)))
    matches.sort(key=lambda item: item[1], reverse=True)
    if matches and matches[0][1] > 0:
        return matches[0][0]
    return requested


def _annotation_allows_none(annotation: Any) -> bool:
    if annotation is None or annotation is type(None):
        return True
    origin = get_origin(annotation)
    if origin in (UnionType, None) and hasattr(annotation, "__args__"):
        return any(_annotation_allows_none(arg) for arg in get_args(annotation))
    return any(arg is type(None) for arg in get_args(annotation))


def _annotation_contains(annotation: Any, target: type[Any]) -> bool:
    if annotation is target:
        return True
    return any(_annotation_contains(arg, target) for arg in get_args(annotation))


def _enum_type(annotation: Any) -> type[Enum] | None:
    candidates = (annotation, *get_args(annotation))
    for candidate in candidates:
        if isinstance(candidate, type) and issubclass(candidate, Enum):
            return candidate
    return None


def _parse_paise(value: str, field_name: str) -> int:
    cleaned = value.strip()
    if not cleaned:
        raise ValueError("missing money amount")
    if "." in cleaned:
        raise ValueError(f"{field_name} must be integer paise")
    return int(cleaned)


def _convert_field(field_name: str, raw_value: str, annotation: Any) -> Any:
    value = raw_value.strip()
    if value == "":
        if _annotation_allows_none(annotation):
            return None
        raise ValueError("missing required field")

    enum_type = _enum_type(annotation)
    if enum_type is not None:
        return enum_type(value.upper())
    if _annotation_contains(annotation, datetime):
        return parse_date(value)
    if _annotation_contains(annotation, date):
        if len(value) == 10:
            return date.fromisoformat(value)
        return parse_date(value).date()
    if _annotation_contains(annotation, int):
        if field_name.endswith("_paise"):
            return _parse_paise(value, field_name)
        return parse_money(value)
    return value


def _row_to_model(
    row: dict[str, str],
    row_number: int,
    model_type: type[BaseModel],
) -> tuple[BaseModel | None, list[RowIssue]]:
    values: dict[str, Any] = {}
    issues: list[RowIssue] = []
    for field_name, field in model_type.model_fields.items():
        if field_name not in row:
            if field.is_required():
                issues.append(
                    RowIssue(
                        field=field_name,
                        reason="missing required column",
                        code=ExceptionCode.MISSING_REQUIRED_FIELD,
                    )
                )
            continue
        raw_value = row.get(field_name, "") or ""
        try:
            values[field_name] = _convert_field(field_name, raw_value, field.annotation)
        except (ValueError, TypeError) as exc:
            issues.append(
                RowIssue(
                    field=field_name,
                    value=raw_value,
                    reason=str(exc),
                    code=ExceptionCode.MALFORMED_INPUT,
                )
            )

    if issues:
        return None, issues

    try:
        return model_type.model_validate(values), []
    except ValidationError as exc:
        for error in exc.errors():
            field = ".".join(str(part) for part in error.get("loc", ())) or "__row__"
            issues.append(
                RowIssue(
                    field=field,
                    value=str(values.get(field, "")),
                    reason=str(error.get("msg", "validation error")),
                    code=ExceptionCode.MALFORMED_INPUT,
                )
            )
        return None, issues


def _exact_row_key(row: dict[str, str]) -> tuple[tuple[str, str], ...]:
    return tuple(sorted((key, value.strip()) for key, value in row.items()))


def ingest_file(file_path: str, source_type: str) -> IngestionResult:
    """Ingest and validate a single CSV source file."""
    path = Path(file_path)
    requested_type = _canonical_source_type(source_type)
    checksum = _sha256_file(path)
    size_bytes = path.stat().st_size

    with path.open(newline="") as f:
        reader = csv.DictReader(f)
        headers = set(reader.fieldnames or [])
        rows = list(reader)

    detected_type = _detect_source_type(headers, requested_type)
    model_type, id_field, expected_headers = _SOURCE_CONFIG.get(
        detected_type, (None, "", set())
    )
    file_errors: list[RowIssue] = []
    if model_type is None:
        file_errors.append(
            RowIssue(
                field="source_type",
                value=source_type,
                reason="unsupported source type",
                code=ExceptionCode.UNSUPPORTED_RECORD_TYPE,
            )
        )
    else:
        missing_headers = sorted(expected_headers - headers)
        for header in missing_headers:
            file_errors.append(
                RowIssue(
                    field=header,
                    reason="missing required column",
                    code=ExceptionCode.MISSING_REQUIRED_FIELD,
                )
            )

    preliminary: list[RawSourceRow] = []
    if model_type is not None:
        for index, row in enumerate(rows, start=2):
            source_record_id = row.get(id_field, "").strip() or f"{detected_type}:row:{index}"
            record, issues = _row_to_model(row, index, model_type)
            quality = IngestionQuality.VALID if not issues else IngestionQuality.INVALID
            raw_values = {
                str(key): "" if value is None else str(value)
                for key, value in row.items()
                if key is not None
            }
            preliminary.append(
                RawSourceRow(
                    source_type=detected_type,
                    source_file=str(path),
                    row_number=index,
                    source_record_id=source_record_id,
                    raw_values=raw_values,
                    record=record,
                    quality=quality,
                    issues=issues,
                    file_checksum_sha256=checksum,
                )
            )

    if file_errors:
        rejected = [
            row.model_copy(
                update={
                    "quality": IngestionQuality.INVALID,
                    "issues": row.issues + file_errors,
                }
            )
            for row in preliminary
        ]
        metadata = FileMetadata(
            file_path=str(path),
            filename=path.name,
            source_type=requested_type,
            detected_source_type=detected_type,
            checksum_sha256=checksum,
            size_bytes=size_bytes,
            row_count=len(rows),
            accepted_count=0,
            rejected_count=len(rejected),
        )
        return IngestionResult(metadata=metadata, rejected_rows=rejected, file_errors=file_errors)

    id_counts = Counter(row.source_record_id for row in preliminary)
    exact_counts = Counter(_exact_row_key(row.raw_values) for row in preliminary)

    accepted: list[RawSourceRow] = []
    rejected: list[RawSourceRow] = []
    for row in preliminary:
        issues = list(row.issues)
        if id_counts[row.source_record_id] > 1:
            issues.append(
                RowIssue(
                    field=id_field,
                    value=row.source_record_id,
                    reason="duplicate source ID within file",
                    code=ExceptionCode.DUPLICATE_SOURCE_RECORD,
                )
            )
        if exact_counts[_exact_row_key(row.raw_values)] > 1:
            issues.append(
                RowIssue(
                    field="__row__",
                    reason="exact duplicate row within file",
                    code=ExceptionCode.DUPLICATE_SOURCE_RECORD,
                )
            )

        if issues:
            rejected.append(
                row.model_copy(
                    update={"quality": IngestionQuality.INVALID, "issues": issues, "record": None}
                )
            )
        else:
            accepted.append(row)

    metadata = FileMetadata(
        file_path=str(path),
        filename=path.name,
        source_type=requested_type,
        detected_source_type=detected_type,
        checksum_sha256=checksum,
        size_bytes=size_bytes,
        row_count=len(rows),
        accepted_count=len(accepted),
        rejected_count=len(rejected),
    )
    return IngestionResult(
        metadata=metadata,
        accepted_rows=accepted,
        rejected_rows=rejected,
        file_errors=file_errors,
    )
