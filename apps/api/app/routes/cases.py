"""Case queue, evidence graph, receipt, and candidate routes."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.app.dependencies import get_db_session
from apps.api.app.routes.helpers import case_detail, case_summary, page_count
from apps.api.app.schemas.cases import (
    AIAnalysisDetailResponse,
    CandidateListResponse,
    CandidateResponse,
    EvidenceEdgeResponse,
    EvidenceGraphResponse,
    InvariantResponse,
    PaginatedCases,
    VerificationReceiptResponse,
)
from db.repositories import CaseRepository, ReviewRepository, RunRepository
from services.reconciliation.run_service import RunServiceError

router = APIRouter(tags=["cases"])


async def _require_case(repository: CaseRepository, case_id: str):
    case = await repository.get_case(case_id)
    if case is None:
        raise RunServiceError(
            "CASE_NOT_FOUND",
            "The requested reconciliation case was not found.",
            status_code=404,
            details={"case_id": case_id},
        )
    return case


@router.get("/api/runs/{run_id}/cases", response_model=PaginatedCases)
async def list_cases(
    run_id: uuid.UUID,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=200)] = 50,
    state: str | None = None,
    severity: str | None = None,
    exception_code: str | None = None,
    owner: str | None = None,
    min_age_days: Annotated[int | None, Query(ge=0)] = None,
    min_amount_paise: int | None = None,
    max_amount_paise: int | None = None,
    ai_involvement: bool | None = None,
    human_review: bool | None = None,
    session: AsyncSession = Depends(get_db_session),
) -> PaginatedCases:
    if await RunRepository(session).get(run_id) is None:
        raise RunServiceError(
            "RUN_NOT_FOUND", "The requested reconciliation run was not found.", status_code=404
        )
    items, total = await CaseRepository(session).list_cases(
        run_id,
        offset=(page - 1) * page_size,
        limit=page_size,
        state=state,
        severity=severity,
        exception_code=exception_code,
        owner=owner,
        min_age_days=min_age_days,
        min_amount_paise=min_amount_paise,
        max_amount_paise=max_amount_paise,
        ai_involvement=ai_involvement,
        human_review=human_review,
    )
    return PaginatedCases(
        items=[case_summary(item) for item in items],
        page=page,
        page_size=page_size,
        total=total,
        pages=page_count(total, page_size),
    )


@router.get("/api/cases/{case_id}")
async def get_case(case_id: str, session: AsyncSession = Depends(get_db_session)):
    repository = CaseRepository(session)
    return case_detail(await _require_case(repository, case_id))


@router.get("/api/cases/{case_id}/evidence", response_model=EvidenceGraphResponse)
async def get_evidence(
    case_id: str, session: AsyncSession = Depends(get_db_session)
) -> EvidenceGraphResponse:
    repository = CaseRepository(session)
    case = await _require_case(repository, case_id)
    edges = await repository.evidence_for_case(case.reconciliation_run_id, case.case_id)
    return EvidenceGraphResponse(
        case_id=case.case_id,
        nodes=case.source_entity_ids,
        edges=[EvidenceEdgeResponse.model_validate(item) for item in edges],
    )


@router.get("/api/cases/{case_id}/receipt", response_model=VerificationReceiptResponse)
async def get_receipt(
    case_id: str, session: AsyncSession = Depends(get_db_session)
) -> VerificationReceiptResponse:
    repository = CaseRepository(session)
    case = await _require_case(repository, case_id)
    invariants = await repository.invariants_for_case(case.reconciliation_run_id, case.case_id)
    edges = await repository.evidence_for_case(case.reconciliation_run_id, case.case_id)
    run = await RunRepository(session).get(case.reconciliation_run_id)
    return VerificationReceiptResponse(
        case_id=case.case_id,
        case_state=case.case_state,
        residual_paise=case.residual_paise,
        all_invariants_passed=bool(invariants) and all(item.passed for item in invariants),
        invariants=[InvariantResponse.model_validate(item) for item in invariants],
        evidence_edge_count=len(edges),
        result_checksum=run.result_checksum if run else None,
    )


@router.get("/api/cases/{case_id}/candidates", response_model=CandidateListResponse)
async def get_candidates(
    case_id: str, session: AsyncSession = Depends(get_db_session)
) -> CandidateListResponse:
    repository = CaseRepository(session)
    case = await _require_case(repository, case_id)
    candidates = await repository.candidates_for_case(
        case.reconciliation_run_id, case.source_entity_ids
    )
    return CandidateListResponse(
        case_id=case.case_id,
        items=[CandidateResponse.model_validate(item) for item in candidates],
    )


@router.get("/api/cases/{case_id}/ai-analysis", response_model=AIAnalysisDetailResponse)
async def get_ai_analysis(
    case_id: str, session: AsyncSession = Depends(get_db_session)
) -> AIAnalysisDetailResponse:
    await _require_case(CaseRepository(session), case_id)
    analysis = await ReviewRepository(session).latest_ai_analysis(case_id)
    if analysis is None:
        raise RunServiceError(
            "AI_ANALYSIS_NOT_AVAILABLE",
            "No AI analysis is available for this case.",
            status_code=404,
            details={"case_id": case_id},
        )
    return AIAnalysisDetailResponse.model_validate(analysis)
