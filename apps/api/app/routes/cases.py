"""Case queue, evidence graph, receipt, and candidate routes."""

from __future__ import annotations

import hashlib
import json
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.app.dependencies import get_db_session
from apps.api.app.routes.helpers import case_detail, case_summaries, page_count, require_run
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


async def _require_case(repository: CaseRepository, case_id: str, run_id: uuid.UUID | None = None):
    if run_id is not None:
        await require_run(repository.session, run_id)
    case = await repository.get_case(case_id, run_id)
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
    run = await require_run(session, run_id)
    repository = CaseRepository(session)
    items, total = await repository.list_cases(
        run_id,
        offset=0 if min_age_days is not None else (page - 1) * page_size,
        limit=None if min_age_days is not None else page_size,
        state=state,
        severity=severity,
        exception_code=exception_code,
        owner=owner,
        min_amount_paise=min_amount_paise,
        max_amount_paise=max_amount_paise,
        ai_involvement=ai_involvement,
        human_review=human_review,
    )
    summaries = await case_summaries(session, run, items)
    if min_age_days is not None:
        summaries = [
            item
            for item in summaries
            if item.age_days is not None and item.age_days >= min_age_days
        ]
        total = len(summaries)
        start = (page - 1) * page_size
        summaries = summaries[start : start + page_size]
    return PaginatedCases(
        items=summaries,
        page=page,
        page_size=page_size,
        total=total,
        pages=page_count(total, page_size),
    )


@router.get("/api/cases/{case_id}")
@router.get("/api/runs/{run_id}/cases/{case_id}")
async def get_case(
    case_id: str, run_id: uuid.UUID | None = None, session: AsyncSession = Depends(get_db_session)
):
    repository = CaseRepository(session)
    case = await _require_case(repository, case_id, run_id)
    run = await require_run(session, case.reconciliation_run_id)
    summary = (await case_summaries(session, run, [case]))[0]
    return case_detail(case, summary)


@router.get("/api/cases/{case_id}/evidence", response_model=EvidenceGraphResponse)
@router.get("/api/runs/{run_id}/cases/{case_id}/evidence", response_model=EvidenceGraphResponse)
async def get_evidence(
    case_id: str, run_id: uuid.UUID | None = None, session: AsyncSession = Depends(get_db_session)
) -> EvidenceGraphResponse:
    repository = CaseRepository(session)
    case = await _require_case(repository, case_id, run_id)
    edges = await repository.evidence_for_case(case.reconciliation_run_id, case.case_id)
    return EvidenceGraphResponse(
        case_id=case.case_id,
        nodes=case.source_entity_ids,
        edges=[EvidenceEdgeResponse.model_validate(item) for item in edges],
    )


@router.get("/api/cases/{case_id}/receipt", response_model=VerificationReceiptResponse)
@router.get(
    "/api/runs/{run_id}/cases/{case_id}/receipt", response_model=VerificationReceiptResponse
)
async def get_receipt(
    case_id: str, run_id: uuid.UUID | None = None, session: AsyncSession = Depends(get_db_session)
) -> VerificationReceiptResponse:
    repository = CaseRepository(session)
    case = await _require_case(repository, case_id, run_id)
    # A short per-run lock makes the multi-query receipt one coherent projection.
    run = await RunRepository(session).get_for_share(case.reconciliation_run_id)
    case = await _require_case(repository, case_id, case.reconciliation_run_id)
    invariants = await repository.invariants_for_case(case.reconciliation_run_id, case.case_id)
    edges = await repository.evidence_for_case(case.reconciliation_run_id, case.case_id)
    invariant_responses = [InvariantResponse.model_validate(item) for item in invariants]
    edge_payloads = [
        EvidenceEdgeResponse.model_validate(item).model_dump(mode="json") for item in edges
    ]
    edge_payloads.sort(
        key=lambda item: (
            item["source_entity_id"],
            item["target_entity_id"],
            item["relationship_type"],
            item["rule_id"],
        )
    )
    payload = {
        "schema_version": "clearledger.case_review_receipt.v1",
        "run_id": str(case.reconciliation_run_id),
        "execution_revision": run.execution_revision if run else 1,
        "review_revision": run.review_revision if run else 0,
        "baseline_result_checksum": run.result_checksum if run else None,
        "case": {
            "case_id": case.case_id,
            "case_state": case.case_state,
            "decision_level": case.decision_level,
            "currency": case.currency,
            "gross_amount_paise": case.gross_amount_paise,
            "net_amount_paise": case.net_amount_paise,
            "residual_paise": case.residual_paise,
            "cash_bucket": case.cash_bucket,
            "owner_role": case.owner_role,
            "human_reviewed": case.human_reviewed,
            "updated_at": case.updated_at.isoformat(),
            "source_entity_ids": sorted(case.source_entity_ids),
        },
        "policy_checksum_sha256": run.policy_snapshot.get("checksum_sha256") if run else None,
        "input_manifest": run.input_manifest if run else {},
        "invariants": [item.model_dump(mode="json") for item in invariant_responses],
        "evidence": edge_payloads,
    }
    checksum = hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    return VerificationReceiptResponse(
        run_id=case.reconciliation_run_id,
        execution_revision=run.execution_revision if run else 1,
        review_revision=run.review_revision if run else 0,
        case_id=case.case_id,
        case_state=case.case_state,
        residual_paise=case.residual_paise,
        all_invariants_passed=bool(invariants) and all(item.passed for item in invariants),
        invariants=invariant_responses,
        evidence_edge_count=len(edges),
        result_checksum=run.result_checksum if run else None,
        baseline_result_checksum=run.result_checksum if run else None,
        current_review_checksum=checksum,
        review_checksum_payload=payload,
    )


@router.get("/api/cases/{case_id}/candidates", response_model=CandidateListResponse)
@router.get("/api/runs/{run_id}/cases/{case_id}/candidates", response_model=CandidateListResponse)
async def get_candidates(
    case_id: str, run_id: uuid.UUID | None = None, session: AsyncSession = Depends(get_db_session)
) -> CandidateListResponse:
    repository = CaseRepository(session)
    case = await _require_case(repository, case_id, run_id)
    candidates = await repository.candidates_for_case(
        case.reconciliation_run_id, case.source_entity_ids
    )
    return CandidateListResponse(
        case_id=case.case_id,
        items=[CandidateResponse.model_validate(item) for item in candidates],
    )


@router.get("/api/cases/{case_id}/ai-analysis", response_model=AIAnalysisDetailResponse)
@router.get(
    "/api/runs/{run_id}/cases/{case_id}/ai-analysis", response_model=AIAnalysisDetailResponse
)
async def get_ai_analysis(
    case_id: str, run_id: uuid.UUID | None = None, session: AsyncSession = Depends(get_db_session)
) -> AIAnalysisDetailResponse:
    case = await _require_case(CaseRepository(session), case_id, run_id)
    analysis = await ReviewRepository(session).latest_ai_analysis(
        case_id, case.reconciliation_run_id
    )
    if analysis is None:
        raise RunServiceError(
            "AI_ANALYSIS_NOT_AVAILABLE",
            "No AI analysis is available for this case.",
            status_code=404,
            details={"case_id": case_id},
        )
    return AIAnalysisDetailResponse.model_validate(analysis)
