"""Versioned settlement-policy loading and audit checksums."""

from __future__ import annotations

import hashlib
import json
from datetime import date, time
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


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
    holidays: tuple[date, ...] = Field(default_factory=tuple)
    weekend_days: tuple[int, ...] = (5, 6)
    checksum_sha256: str = ""
    holiday_checksum_sha256: str = ""


_ROOT = Path(__file__).resolve().parents[2]
_DEFAULT_POLICY_PATH = _ROOT / "policies" / "settlement_policy.v1.json"


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _load_holidays(policy_path: Path, calendar_id: str) -> tuple[tuple[date, ...], str]:
    candidates = [
        policy_path.parent / "holidays.v1.json",
        policy_path.parent / f"{calendar_id}.json",
    ]
    for candidate in candidates:
        if not candidate.exists():
            continue
        raw = candidate.read_bytes()
        payload = json.loads(raw)
        holidays = tuple(
            sorted(date.fromisoformat(str(item["date"])) for item in payload.get("holidays", []))
        )
        return holidays, _sha256_bytes(raw)
    return (), ""


def policy_checksum(policy: SettlementPolicy) -> str:
    """Return a stable checksum of audit-relevant policy fields."""
    payload: dict[str, Any] = policy.model_dump(mode="json")
    payload.pop("checksum_sha256", None)
    payload.pop("holiday_checksum_sha256", None)
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return _sha256_bytes(encoded)


def load_policy(policy_path: str | Path | None = None) -> SettlementPolicy:
    """Load, validate, and bind the settlement policy to its holiday calendar."""
    path = Path(policy_path) if policy_path else _DEFAULT_POLICY_PATH
    raw = path.read_bytes()
    payload = json.loads(raw)
    policy = SettlementPolicy.model_validate(payload)
    holidays, holiday_checksum = _load_holidays(path, policy.holiday_calendar_id)
    policy = policy.model_copy(
        update={
            "holidays": holidays,
            "checksum_sha256": _sha256_bytes(raw),
            "holiday_checksum_sha256": holiday_checksum,
        }
    )
    return policy.model_copy(update={"checksum_sha256": policy_checksum(policy)})
