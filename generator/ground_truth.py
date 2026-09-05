"""Ground-truth models used by the generator and scored by the evaluator.

Ground truth is *never* imported by the reconciliation engine at runtime.
"""

from __future__ import annotations

from datetime import date

from pydantic import BaseModel, ConfigDict

from packages.domain.enums import CaseState, CashBucket, ExceptionCode


class GroundTruthEdge(BaseModel):
    model_config = ConfigDict(strict=True, frozen=True)

    source_entity_id: str
    target_entity_id: str
    relationship_type: str
    allocated_amount_paise: int


class GroundTruthCase(BaseModel):
    model_config = ConfigDict(strict=True, frozen=True)

    case_id: str
    scenario_id: str
    scenario_label: str
    expected_relationships: list[GroundTruthEdge]
    expected_case_state: CaseState
    expected_exception_code: ExceptionCode | None = None
    expected_cash_bucket: CashBucket
    expected_gross_amount_paise: int
    expected_net_amount_paise: int
    expected_residual_paise: int  # must be 0 for RECONCILED cases
    source_entity_ids: list[str]


class GroundTruthManifest(BaseModel):
    model_config = ConfigDict(strict=True, frozen=True)

    dataset_id: str
    seed: int
    generator_version: str
    policy_version: str
    currency: str = "INR"
    date_range_start: date
    date_range_end: date
    scenario_counts: dict[str, int]
    total_cases: int
    total_source_records: int
    file_checksums: dict[str, str]
    cases: list[GroundTruthCase]
