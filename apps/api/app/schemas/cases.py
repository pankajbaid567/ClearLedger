"""Case and evidence API contracts."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class CaseSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    case_id: str
    reconciliation_run_id: uuid.UUID
    case_state: str
    decision_level: str | None
    gross_amount_paise: int
    net_amount_paise: int
    residual_paise: int
    currency: str
    exception_code: str | None
    exception_severity: str | None
    amount_at_risk_paise: int
    cash_bucket: str | None
    settlement_id: str | None
    bank_receipt_state: str | None
    owner_role: str | None
    next_action: str | None
    ai_assisted: bool
    human_reviewed: bool
    created_at: datetime
    updated_at: datetime
    cash_bucket_contribution_paise: int = 0
    cash_contribution_basis: str = "not_computed"
    event_at: datetime | None = None
    age_days: int | None = None
    sla_due_at: datetime | None = None
    days_past_sla: int | None = None
    review_due_at: datetime | None = None


class CaseDetail(CaseSummary):
    source_entity_ids: list[str]
    records: list[dict[str, Any]]


class PaginatedCases(BaseModel):
    items: list[CaseSummary]
    page: int
    page_size: int
    total: int
    pages: int


class EvidenceEdgeResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    source_entity_id: str
    target_entity_id: str
    relationship_type: str
    allocated_amount_paise: int
    currency: str
    rule_id: str
    rule_version: str
    evidence_fields: list[str]
    decision_level: str
    actor_type: str
    verification_checks: list[dict[str, Any]] | None
    created_at: datetime


class EvidenceGraphResponse(BaseModel):
    case_id: str
    nodes: list[str]
    edges: list[EvidenceEdgeResponse]


class InvariantResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    invariant_id: str
    passed: bool
    expected_value: str | None
    actual_value: str | None
    affected_entities: list[str] | None
    message: str | None


class VerificationReceiptResponse(BaseModel):
    run_id: uuid.UUID
    execution_revision: int = 1
    review_revision: int = 0
    snapshot_kind: str = "current_review_projection"
    case_id: str
    case_state: str
    residual_paise: int
    all_invariants_passed: bool
    invariants: list[InvariantResponse]
    evidence_edge_count: int
    result_checksum: str | None
    baseline_result_checksum: str | None
    current_review_checksum: str
    review_checksum_payload: dict[str, Any]


class CandidateResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    source_entity_id: str
    target_entity_id: str
    relationship_type: str
    match_score: float | None
    decision_level: str
    rejection_reason: str | None
    evidence_fields: list[str]
    allocated_amount_paise: int
    currency: str
    rule_id: str | None
    actor_type: str

    @classmethod
    def model_validate(cls, obj: Any, **kwargs: Any) -> CandidateResponse:
        """Convert scaled integer match_score (0-10000) to float (0.0-1.0) for API response."""
        if hasattr(obj, "match_score") and obj.match_score is not None:
            # Create a mutable copy to avoid modifying the database object
            data = {
                "source_entity_id": obj.source_entity_id,
                "target_entity_id": obj.target_entity_id,
                "relationship_type": obj.relationship_type,
                "match_score": obj.match_score / 10000.0,  # Convert scaled integer to float
                "decision_level": obj.decision_level,
                "rejection_reason": obj.rejection_reason,
                "evidence_fields": obj.evidence_fields,
                "allocated_amount_paise": obj.allocated_amount_paise,
                "currency": obj.currency,
                "rule_id": obj.rule_id,
                "actor_type": obj.actor_type,
            }
            return super().model_validate(data, **kwargs)
        return super().model_validate(obj, **kwargs)


class CandidateListResponse(BaseModel):
    case_id: str
    items: list[CandidateResponse]


class AIAnalysisDetailResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    reconciliation_run_id: uuid.UUID
    case_id: str
    evidence_packet: dict[str, Any]
    ai_response: dict[str, Any] | None
    ai_model: str | None
    ai_prompt_version: str | None
    provider: str | None
    status: str
    tokens_prompt: int | None
    tokens_completion: int | None
    latency_ms: int | None
    estimated_cost: float
    attempts: int
    validation_passed: bool | None
    validation_errors: list[dict[str, Any]] | None
    deterministic_checks: list[dict[str, Any]] | None
    error_type: str | None
    created_at: datetime

    @classmethod
    def model_validate(cls, obj: Any, **kwargs: Any) -> AIAnalysisDetailResponse:
        """Convert micro-dollar estimated_cost to USD float for API response."""
        if hasattr(obj, "estimated_cost"):
            data = {
                "id": obj.id,
                "reconciliation_run_id": obj.reconciliation_run_id,
                "case_id": obj.case_id,
                "evidence_packet": obj.evidence_packet,
                "ai_response": obj.ai_response,
                "ai_model": obj.ai_model,
                "ai_prompt_version": obj.ai_prompt_version,
                "provider": obj.provider,
                "status": obj.status,
                "tokens_prompt": obj.tokens_prompt,
                "tokens_completion": obj.tokens_completion,
                "latency_ms": obj.latency_ms,
                "estimated_cost": obj.estimated_cost / 1_000_000.0,  # Convert micro-dollars to USD
                "attempts": obj.attempts,
                "validation_passed": obj.validation_passed,
                "validation_errors": obj.validation_errors,
                "deterministic_checks": obj.deterministic_checks,
                "error_type": obj.error_type,
                "created_at": obj.created_at,
            }
            return super().model_validate(data, **kwargs)
        return super().model_validate(obj, **kwargs)


class CashPositionResponse(BaseModel):
    run_id: uuid.UUID
    currency: str
    bank_confirmed_paise: int
    settlement_confirmed_in_transit_paise: int
    expected_settlement_paise: int
    at_risk_paise: int
    unresolved_paise: int
    scheduled_refunds_paise: int
    known_disputes_paise: int
    known_reserve_holds_paise: int
    safe_cash_paise: int
    buckets: dict[str, Any]
    cash_scope: str = "CONFIRMED_BATCH_NET_MOVEMENTS"
    deductions_already_in_settlement_net: bool = True
    as_of_at: datetime | None = None
    execution_revision: int = 1
    review_revision: int = 0


class CashForecastDayResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

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
    model_config = ConfigDict(from_attributes=True)

    run_id: str
    execution_revision: int = 1
    review_revision: int = 0
    as_of_date: str
    currency: str
    days: list[CashForecastDayResponse]
    total_projected_inflow_paise: int
    baseline_safe_cash_paise: int
    projected_final_cash_paise: int
    forecast_scope: str = "SETTLEMENT_RECEIPTS_ONLY"
    overdue_inflow_paise: int = 0
    undated_inflow_paise: int = 0


class TaxDiscrepancyItemResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

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


class TaxAuditResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    run_id: str
    execution_revision: int = 1
    review_revision: int = 0
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
    discrepancies: list[TaxDiscrepancyItemResponse] = Field(default_factory=list)
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


class AuditEventResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    reconciliation_run_id: uuid.UUID | None
    case_id: str | None
    source_file_id: uuid.UUID | None
    event_type: str
    stage: str | None
    rule_id: str | None
    severity: str | None
    details: dict[str, Any] | None
    actor: str | None
    duration_ms: int | None
    created_at: datetime


class PaginatedAudit(BaseModel):
    items: list[AuditEventResponse]
    page: int
    page_size: int
    total: int
    pages: int
