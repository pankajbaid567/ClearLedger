"""Prediction schemas — what the reconciliation engine outputs for evaluation."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from packages.domain.enums import CaseState, CashBucket, ExceptionCode


class PredictedEdge(BaseModel):
    model_config = ConfigDict(strict=True, frozen=True)

    source_entity_id: str
    target_entity_id: str
    relationship_type: str
    allocated_amount_paise: int


class PredictedCase(BaseModel):
    model_config = ConfigDict(strict=True, frozen=True)

    case_id: str
    predicted_relationships: list[PredictedEdge]
    predicted_case_state: CaseState
    predicted_exception_code: ExceptionCode | None = None
    predicted_cash_bucket: CashBucket
    predicted_gross_amount_paise: int
    predicted_net_amount_paise: int
    predicted_residual_paise: int


class PredictionReport(BaseModel):
    model_config = ConfigDict(strict=True, frozen=True)

    dataset_id: str
    run_id: str
    duration_seconds: float
    total_source_records: int
    cases: list[PredictedCase]
