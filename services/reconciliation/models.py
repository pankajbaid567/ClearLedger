"""Shared typed contracts for the deterministic reconciliation engine."""

from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from generator.schemas import (
    BankTransactionRecord,
    OrderRecord,
    PaymentRecord,
    SettlementComponentRecord,
    SettlementRecord,
)
from packages.domain.enums import (
    CaseState,
    CashBucket,
    ExceptionCode,
    ExceptionSeverity,
    IngestionQuality,
)

SourceRecord = (
    OrderRecord
    | PaymentRecord
    | SettlementRecord
    | SettlementComponentRecord
    | BankTransactionRecord
)


class _BaseModel(BaseModel):
    model_config = ConfigDict(strict=True)


class RowIssue(_BaseModel):
    field: str
    value: str | None = None
    reason: str
    code: ExceptionCode | None = None


class FileMetadata(_BaseModel):
    file_path: str
    filename: str
    source_type: str
    detected_source_type: str
    checksum_sha256: str
    size_bytes: int
    row_count: int
    accepted_count: int
    rejected_count: int
    ingested_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class RawSourceRow(_BaseModel):
    source_type: str
    source_file: str
    row_number: int
    source_record_id: str
    raw_values: dict[str, str]
    record: SourceRecord | None = None
    quality: IngestionQuality
    issues: list[RowIssue] = Field(default_factory=list)
    file_checksum_sha256: str


class IngestionResult(_BaseModel):
    metadata: FileMetadata
    accepted_rows: list[RawSourceRow] = Field(default_factory=list)
    rejected_rows: list[RawSourceRow] = Field(default_factory=list)
    file_errors: list[RowIssue] = Field(default_factory=list)


class NormalizedField(_BaseModel):
    raw: Any
    normalized: Any
    rule_id: str


class IdentifierToken(_BaseModel):
    category: str
    raw: str
    normalized: str
    rule_id: str
    span_start: int
    span_end: int


class NormalizedRecord(_BaseModel):
    source_type: str
    source_record_id: str
    entity_id: str
    row_number: int
    raw_values: dict[str, str]
    raw_record: SourceRecord | None = None
    quality: IngestionQuality
    issues: list[RowIssue] = Field(default_factory=list)
    normalized_fields: dict[str, NormalizedField] = Field(default_factory=dict)
    narration_tokens: dict[str, list[IdentifierToken]] = Field(default_factory=dict)
    merchant_id: str | None = None
    account_id: str | None = None
    order_id: str | None = None
    payment_id: str | None = None
    settlement_id: str | None = None
    component_id: str | None = None
    bank_transaction_id: str | None = None
    source_event_id: str | None = None
    component_type: str | None = None
    status: str | None = None
    direction: str | None = None
    amount_paise: int | None = None
    signed_amount_paise: int | None = None
    currency: str | None = None
    event_at: datetime | None = None
    event_date: date | None = None
    value_date: date | None = None


class CandidateRelationship(_BaseModel):
    source_entity_id: str
    target_entity_id: str
    relationship_type: str
    evidence_fields: list[str]
    match_strength_score: int
    rule_id: str
    source_record_type: str | None = None
    target_record_type: str | None = None
    allocated_amount_paise: int
    rejected_reasons: list[str] = Field(default_factory=list)
    metadata: dict[str, str | int | bool | None] = Field(default_factory=dict)


class VerificationCheck(_BaseModel):
    check_id: str
    passed: bool
    expected_value: str | int | None = None
    actual_value: str | int | None = None
    affected_entities: list[str] = Field(default_factory=list)
    message: str = ""


class InvariantResult(_BaseModel):
    invariant_id: str
    passed: bool
    expected_value: str | int | None = None
    actual_value: str | int | None = None
    affected_entities: list[str] = Field(default_factory=list)
    message: str = ""


class ReconciliationCase(_BaseModel):
    model_config = ConfigDict(strict=True, frozen=False)

    case_id: str
    source_entity_ids: list[str]
    records: list[NormalizedRecord] = Field(default_factory=list)
    candidate_relationships: list[CandidateRelationship] = Field(default_factory=list)
    ambiguous_candidates: list[CandidateRelationship] = Field(default_factory=list)
    invariant_results: list[InvariantResult] = Field(default_factory=list)
    case_state: CaseState = CaseState.CREATED
    exception_code: ExceptionCode | None = None
    cash_bucket: CashBucket = CashBucket.UNRESOLVED
    gross_amount_paise: int = 0
    net_amount_paise: int = 0
    residual_paise: int = 0
    invalid_reasons: list[RowIssue] = Field(default_factory=list)
    checks_passed: list[str] = Field(default_factory=list)
    checks_failed: list[str] = Field(default_factory=list)
    missing_evidence: list[str] = Field(default_factory=list)
    case_latency_ms: float = 0.0


class StructuredException(_BaseModel):
    code: ExceptionCode
    severity: ExceptionSeverity
    amount_at_risk_paise: int
    case_id: str
    summary: str
    checks_passed: list[str] = Field(default_factory=list)
    checks_failed: list[str] = Field(default_factory=list)
    missing_evidence: list[str] = Field(default_factory=list)
    next_action: str
    owner_role: str
    ai_assisted: bool = False


class CashPositionBucket(_BaseModel):
    bucket: CashBucket
    amount_paise: int
    case_ids: list[str] = Field(default_factory=list)


class CashPosition(_BaseModel):
    buckets: dict[CashBucket, CashPositionBucket]
    bank_confirmed_paise: int
    settlement_confirmed_in_transit_paise: int
    expected_settlement_paise: int
    at_risk_paise: int
    unresolved_paise: int
    scheduled_refunds_paise: int = 0
    known_disputes_paise: int = 0
    known_reserve_holds_paise: int = 0
    safe_cash_paise: int


class RuleApplicationResult(_BaseModel):
    accepted_edges: list[Any] = Field(default_factory=list)
    rejected_candidates: list[CandidateRelationship] = Field(default_factory=list)
    ambiguous_candidates: list[CandidateRelationship] = Field(default_factory=list)


class StageTiming(_BaseModel):
    stage: str
    duration_seconds: float


class ReconciliationResult(_BaseModel):
    run_id: str
    dataset_id: str
    duration_seconds: float
    total_source_records: int
    ingestion_results: list[IngestionResult]
    normalized_records: list[NormalizedRecord]
    candidates: list[CandidateRelationship]
    rejected_candidates: list[CandidateRelationship] = Field(default_factory=list)
    ambiguous_candidates: list[CandidateRelationship] = Field(default_factory=list)
    cases: list[ReconciliationCase]
    evidence_edges: list[Any]
    exceptions: list[StructuredException]
    cash_position: CashPosition
    metrics: dict[str, int | float | str]
    stage_timings: list[StageTiming]
