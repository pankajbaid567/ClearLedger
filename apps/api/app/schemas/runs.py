"""Run-management API contracts."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class RunCreateRequest(BaseModel):
    policy_version_id: uuid.UUID | None = None


class SourceFileResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    filename: str
    source_type: str
    file_checksum: str
    file_size_bytes: int | None
    row_count: int | None
    ingestion_quality: str
    created_at: datetime


class RunResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    status: str
    policy_version_id: uuid.UUID | None
    dataset_checksum: str | None
    rule_set_version: str | None
    app_version: str | None
    ai_model: str | None
    ai_prompt_version: str | None
    policy_id: str | None = None
    policy_version: str | None = None
    started_at: datetime | None
    completed_at: datetime | None
    duration_ms: int | None
    total_source_rows: int | None
    total_cases: int | None
    result_checksum: str | None
    failure_reason: str | None
    created_at: datetime
    files: list[SourceFileResponse] = Field(default_factory=list)


class DemoRunResponse(BaseModel):
    run: RunResponse
    validation: dict[str, Any]


class RunStatusResponse(BaseModel):
    run_id: uuid.UUID
    status: str
    failure_reason: str | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None


class ReconciliationResponse(BaseModel):
    run_id: uuid.UUID
    status: str
    total_source_records: int
    total_cases: int
    evidence_edges: int
    exceptions: int
    result_checksum: str


class MetricsResponse(BaseModel):
    run_id: uuid.UUID
    status: str
    metrics: dict[str, Any]


class EvaluationResponse(BaseModel):
    run_id: uuid.UUID
    dataset_id: str
    aggregate: dict[str, Any]
    scenario_breakdown: dict[str, dict[str, Any]]


class QuestionRequest(BaseModel):
    question: str


class QuestionResponse(BaseModel):
    run_id: str
    question: str
    answer: str
    cited_case_ids: list[str] = Field(default_factory=list)
    provider: str
    model: str
    grounded: bool = True

