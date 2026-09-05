"""Prediction schemas — what the reconciliation engine outputs for evaluation."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, model_validator

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

    @model_validator(mode="after")
    def relationships_are_unique(self) -> PredictedCase:
        keys = [
            (
                edge.source_entity_id,
                edge.target_entity_id,
                edge.relationship_type,
                edge.allocated_amount_paise,
            )
            for edge in self.predicted_relationships
        ]
        if len(keys) != len(set(keys)):
            raise ValueError(f"case {self.case_id} contains duplicate relationship edges")
        return self


class PredictionReport(BaseModel):
    model_config = ConfigDict(strict=True, frozen=True)

    dataset_id: str
    run_id: str
    duration_seconds: float = Field(ge=0, allow_inf_nan=False)
    total_source_records: int = Field(ge=0)
    cases: list[PredictedCase]

    @model_validator(mode="after")
    def case_ids_are_unique(self) -> PredictionReport:
        case_ids = [case.case_id for case in self.cases]
        if len(case_ids) != len(set(case_ids)):
            raise ValueError("prediction report contains duplicate case IDs")
        return self
