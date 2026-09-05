"""Strict input and output contracts for bounded AI analysis."""

from __future__ import annotations

import uuid
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, SecretStr


class ExtractedIdentifier(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    token: str = Field(min_length=1, max_length=160)
    identifier_type: Literal["payment_id", "settlement_id", "utr", "order_id"]
    source_field: str = Field(min_length=1, max_length=200)
    confidence_note: Literal["deterministic_regex", "ai_extracted"]


class AIAnalysisResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    case_id: str = Field(min_length=1, max_length=160)
    hypothesis_code: str = Field(min_length=1, max_length=100, pattern=r"^[A-Z][A-Z0-9_]*$")
    ranked_candidate_ids: list[str] = Field(max_length=20)
    supporting_evidence_ids: list[str] = Field(max_length=50)
    contradicting_evidence_ids: list[str] = Field(max_length=50)
    missing_evidence: list[str] = Field(max_length=20)
    recommended_exception_code: str = Field(min_length=1, max_length=100)
    recommended_action_code: str = Field(min_length=1, max_length=100)
    explanation: str = Field(min_length=1, max_length=500)
    extracted_identifiers: list[ExtractedIdentifier] | None = Field(max_length=20)


class ValidationResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    valid: bool
    errors: list[dict[str, str]] = Field(default_factory=list)


class AIClientConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    enabled: bool = False
    provider: str = "none"
    model: str = ""
    api_key: SecretStr = Field(default_factory=lambda: SecretStr(""))
    base_url: str | None = None
    timeout_seconds: int = Field(default=20, ge=1, le=120)
    max_retries: int = Field(default=1, ge=0, le=1)
    max_cases_per_run: int = Field(default=20, ge=1, le=100)
    prompt_version: str = "exception_analyst.v1"
    max_packet_chars: int = Field(default=12_000, ge=2_000, le=100_000)
    input_cost_per_1k_tokens: float = Field(default=0.0, ge=0)
    output_cost_per_1k_tokens: float = Field(default=0.0, ge=0)


class AIClientResult(BaseModel):
    model_config = ConfigDict(extra="forbid", arbitrary_types_allowed=True)

    response: AIAnalysisResponse | None = None
    raw_response: dict[str, Any] | None = None
    validation: ValidationResult | None = None
    prompt_tokens: int = 0
    completion_tokens: int = 0
    latency_ms: int = 0
    estimated_cost: int = 0  # Micro-dollars ($0.000001)
    attempts: int = 0
    failure_reason: str | None = None
    failure_type: str | None = None


class AIAnalysisOutcome(BaseModel):
    model_config = ConfigDict(extra="forbid")

    analysis_id: uuid.UUID | None = None
    case_id: str
    status: str
    case_state: str
    suggestion: AIAnalysisResponse | None = None
    validation: ValidationResult | None = None
    deterministic_checks: list[dict[str, Any]] = Field(default_factory=list)
    failure_reason: str | None = None
