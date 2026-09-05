"""Bounded, case-scoped evidence supplied to the exception analyst."""

from __future__ import annotations

import hashlib
from collections.abc import Iterable
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from packages.domain.enums import ExceptionCode, FollowUpTaskType
from services.normalization.policy import SettlementPolicy
from services.reconciliation.models import (
    CandidateRelationship,
    InvariantResult,
    NormalizedRecord,
    ReconciliationCase,
)

DEFAULT_MAX_PACKET_CHARS = 12_000
MAX_NARRATION_SNIPPETS = 5
MAX_NARRATION_CHARS = 500
MAX_CANDIDATES = 20


class EvidencePacketTooLarge(ValueError):
    """Raised when a packet cannot fit after deterministic bounding."""


class CandidateInfo(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    candidate_id: str
    source_entity_id: str
    target_entity_id: str
    relationship_type: str
    allocated_amount_paise: int
    currency: str
    rule_id: str
    match_strength_score: int
    evidence_ids: list[str] = Field(default_factory=list)
    rejection_reasons: list[str] = Field(default_factory=list)


class InvariantInfo(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    evidence_id: str
    invariant_id: str
    passed: bool
    expected_value: str | int | None = None
    actual_value: str | int | None = None
    affected_entities: list[str] = Field(default_factory=list)
    message: str = ""


class PolicyFacts(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    policy_id: str
    version: str
    currency: str
    capture_to_settlement_days: int
    settlement_to_bank_days: int
    cutoff_time: str
    timezone: str
    weekend_rule: str
    weekend_days: list[int]
    holiday_calendar_id: str
    holiday_dates: list[str]
    fee_schedule: dict[str, int]
    materiality_rules: dict[str, int]
    effective_from: str
    effective_to: str | None = None


class AIEvidencePacket(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    case_id: str
    case_summary: str
    canonical_facts: dict[str, Any]
    raw_narration_snippets: list[str]
    precomputed_candidates: list[CandidateInfo]
    invariant_results: list[InvariantInfo]
    policy_facts: PolicyFacts
    allowed_exception_codes: list[str]
    allowed_action_codes: list[str]

    def available_evidence_ids(self) -> set[str]:
        ids = {item.evidence_id for item in self.invariant_results}
        ids.update(f"entity:{item}" for item in self.canonical_facts.get("entity_ids", []))
        for candidate in self.precomputed_candidates:
            ids.add(candidate.candidate_id)
            ids.update(candidate.evidence_ids)
        return ids

    def available_identifier_values(self) -> set[str]:
        return {
            str(item["value"])
            for item in self.canonical_facts.get("identifiers", [])
            if isinstance(item, dict) and item.get("value")
        }


def candidate_id(candidate: CandidateRelationship) -> str:
    value = "|".join(
        (
            candidate.source_entity_id,
            candidate.target_entity_id,
            candidate.relationship_type,
            candidate.rule_id,
        )
    )
    return f"candidate:{hashlib.sha256(value.encode()).hexdigest()[:16]}"


def _record_facts(record: NormalizedRecord) -> dict[str, Any]:
    facts: dict[str, Any] = {
        "evidence_id": f"entity:{record.entity_id}",
        "entity_id": record.entity_id,
        "source_type": record.source_type,
        "source_record_id": record.source_record_id,
    }
    fields = (
        "merchant_id",
        "account_id",
        "order_id",
        "payment_id",
        "settlement_id",
        "component_id",
        "bank_transaction_id",
        "source_event_id",
        "component_type",
        "status",
        "direction",
        "amount_paise",
        "signed_amount_paise",
        "currency",
        "event_at",
        "event_date",
        "value_date",
    )
    for field_name in fields:
        value = getattr(record, field_name)
        if value is not None:
            facts[field_name] = value.isoformat() if hasattr(value, "isoformat") else value
    return facts


def _identifier_facts(records: Iterable[NormalizedRecord]) -> list[dict[str, str]]:
    identifier_fields = (
        "entity_id",
        "order_id",
        "payment_id",
        "settlement_id",
        "component_id",
        "bank_transaction_id",
        "source_event_id",
    )
    found: dict[str, str] = {}
    for record in records:
        for field_name in identifier_fields:
            value = getattr(record, field_name, None)
            if value:
                found.setdefault(str(value), field_name)
        for tokens in record.narration_tokens.values():
            for token in tokens:
                found.setdefault(token.normalized, token.category)
    return [
        {"type": found[value], "value": value}
        for value in sorted(found)
    ]


def _narration_snippets(records: Iterable[NormalizedRecord]) -> list[str]:
    snippets: list[str] = []
    for record in records:
        if record.source_type != "bank_transactions" or record.raw_record is None:
            continue
        narration = getattr(record.raw_record, "narration", None)
        if not narration:
            continue
        source_field = f"bank_narration:{record.entity_id}"
        snippets.append(f"{source_field}: {str(narration)[:MAX_NARRATION_CHARS]}")
    return snippets[:MAX_NARRATION_SNIPPETS]


def _candidate_info(candidate: CandidateRelationship, currency: str) -> CandidateInfo:
    item_id = candidate_id(candidate)
    evidence_ids = [
        f"entity:{candidate.source_entity_id}",
        f"entity:{candidate.target_entity_id}",
    ]
    return CandidateInfo(
        candidate_id=item_id,
        source_entity_id=candidate.source_entity_id,
        target_entity_id=candidate.target_entity_id,
        relationship_type=candidate.relationship_type,
        allocated_amount_paise=candidate.allocated_amount_paise,
        currency=currency,
        rule_id=candidate.rule_id,
        match_strength_score=candidate.match_strength_score,
        evidence_ids=evidence_ids,
        rejection_reasons=candidate.rejected_reasons,
    )


def _invariant_info(result: InvariantResult) -> InvariantInfo:
    return InvariantInfo(
        evidence_id=f"invariant:{result.invariant_id}",
        invariant_id=result.invariant_id,
        passed=result.passed,
        expected_value=result.expected_value,
        actual_value=result.actual_value,
        affected_entities=result.affected_entities,
        message=result.message[:160],
    )


def _policy_facts(policy: SettlementPolicy) -> PolicyFacts:
    return PolicyFacts(
        policy_id=policy.policy_id,
        version=policy.version,
        currency=policy.currency,
        capture_to_settlement_days=policy.capture_to_settlement_days,
        settlement_to_bank_days=policy.settlement_to_bank_days,
        cutoff_time=policy.cutoff_time.isoformat(),
        timezone=policy.timezone,
        weekend_rule=policy.weekend_rule,
        weekend_days=list(policy.weekend_days),
        holiday_calendar_id=policy.holiday_calendar_id,
        holiday_dates=[item.isoformat() for item in policy.holidays],
        fee_schedule={
            "gateway_fee_percentage": policy.fee_schedule.gateway_fee_percentage,
            "gateway_fee_percentage_denominator": (
                policy.fee_schedule.gateway_fee_percentage_denominator
            ),
            "tax_on_fee_percentage": policy.fee_schedule.tax_on_fee_percentage,
            "tax_on_fee_percentage_denominator": (
                policy.fee_schedule.tax_on_fee_percentage_denominator
            ),
        },
        materiality_rules={
            "amount_variance_threshold_paise": (
                policy.materiality_rules.amount_variance_threshold_paise
            ),
            "critical_amount_paise": policy.materiality_rules.critical_amount_paise,
        },
        effective_from=policy.effective_from.isoformat(),
        effective_to=policy.effective_to.isoformat() if policy.effective_to else None,
    )


def build_evidence_packet(
    case: ReconciliationCase,
    policy: SettlementPolicy,
    *,
    candidates: list[CandidateRelationship] | None = None,
    max_chars: int = DEFAULT_MAX_PACKET_CHARS,
) -> AIEvidencePacket:
    """Build a deterministic packet containing only facts scoped to one case."""
    if max_chars < 2_000:
        raise ValueError("max_chars must be at least 2000")
    selected = candidates if candidates is not None else case.ambiguous_candidates
    if not selected:
        selected = case.candidate_relationships
    currency = next(
        (record.currency for record in case.records if record.currency),
        policy.currency,
    )
    record_facts = [_record_facts(record) for record in case.records]
    packet = AIEvidencePacket(
        case_id=case.case_id,
        case_summary=(
            f"state={case.case_state.value}; exception="
            f"{case.exception_code.value if case.exception_code else 'NONE'}; "
            f"records={len(case.records)}; candidates={len(selected)}; "
            f"failed_invariants={','.join(case.checks_failed) or 'NONE'}"
        ),
        canonical_facts={
            "entity_ids": sorted(case.source_entity_ids),
            "records": record_facts,
            "identifiers": _identifier_facts(case.records),
            "gross_amount_paise": case.gross_amount_paise,
            "net_amount_paise": case.net_amount_paise,
            "residual_paise": case.residual_paise,
            "currency": currency,
            "missing_evidence": sorted(case.missing_evidence),
        },
        raw_narration_snippets=_narration_snippets(case.records),
        precomputed_candidates=[
            _candidate_info(item, currency)
            for item in sorted(
                selected,
                key=lambda value: (
                    -value.match_strength_score,
                    value.source_entity_id,
                    value.target_entity_id,
                    value.rule_id,
                ),
            )[:MAX_CANDIDATES]
        ],
        invariant_results=[_invariant_info(item) for item in case.invariant_results],
        policy_facts=_policy_facts(policy),
        allowed_exception_codes=[item.value for item in ExceptionCode],
        allowed_action_codes=[item.value for item in FollowUpTaskType],
    )
    encoded = packet.model_dump_json()
    if len(encoded) > max_chars:
        raise EvidencePacketTooLarge(
            f"Evidence packet for {case.case_id} is {len(encoded)} chars; limit is {max_chars}"
        )
    return packet
