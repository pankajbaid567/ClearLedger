"""Bounded AI analysis routes and the explicit P1 grounded-Q&A stub."""

from __future__ import annotations

import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Header
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.app.config import Settings, get_settings
from apps.api.app.dependencies import get_db_session, require_ai
from apps.api.app.errors import APIError
from apps.api.app.idempotency import replay_response, store_response
from apps.api.app.schemas.runs import QuestionRequest, QuestionResponse
from db.repositories import CaseRepository, RunRepository
from services.ai_analyst.grounded_qa import GroundedQAService
from services.ai_analyst.schemas import AIAnalysisOutcome
from services.ai_analyst.service import AIAnalystService
from services.normalization.policy import SettlementPolicy
from services.reconciliation.review_service import ReviewService

router = APIRouter(tags=["ai"])
IdempotencyKey = Annotated[str, Header(alias="Idempotency-Key", min_length=1, max_length=200)]


@router.post("/api/cases/{case_id}/analyze", response_model=AIAnalysisOutcome)
async def analyze_case(
    case_id: str,
    idempotency_key: IdempotencyKey,
    session: AsyncSession = Depends(get_db_session),
    config: Settings = Depends(require_ai),
) -> Any:
    scope = f"POST:/api/cases/{case_id}/analyze"
    request_data = {"case_id": case_id, "prompt_version": config.ai_prompt_version}
    replay = await replay_response(
        session,
        scope=scope,
        key=idempotency_key,
        request_payload=request_data,
    )
    if replay:
        return replay

    case = await CaseRepository(session).get_case(case_id)
    if case is None:
        raise APIError(
            "CASE_NOT_FOUND",
            "The requested reconciliation case was not found.",
            status_code=404,
            details={"case_id": case_id},
        )
    runs = RunRepository(session)
    run = await runs.get(case.reconciliation_run_id)
    if run is None or run.policy_version_id is None:
        raise APIError(
            "RUN_POLICY_NOT_FOUND",
            "The policy bound to this reconciliation run is unavailable.",
            status_code=409,
            details={"case_id": case_id},
        )
    policy_record = await runs.get_policy(run.policy_version_id)
    if policy_record is None:
        raise APIError(
            "RUN_POLICY_NOT_FOUND",
            "The policy bound to this reconciliation run is unavailable.",
            status_code=409,
            details={"case_id": case_id},
        )

    service = AIAnalystService(
        session,
        config=config.ai_client_config(),
        policy=SettlementPolicy.model_validate(policy_record.policy_data),
    )
    outcome = await service.analyze_single(case_id)
    await ReviewService(session).recalculate_aggregates(case.reconciliation_run_id)
    refreshed_run = await runs.get(case.reconciliation_run_id)
    if refreshed_run is not None:
        await runs.update(
            refreshed_run,
            metrics={
                **refreshed_run.metrics,
                "ai": service.metrics.model_dump(mode="json"),
            },
            ai_model=config.ai_model,
            ai_prompt_version=config.ai_prompt_version,
        )
    response_data = outcome.model_dump(mode="json")
    await store_response(
        session,
        scope=scope,
        key=idempotency_key,
        request_payload=request_data,
        response_payload=response_data,
    )
    return outcome


@router.post("/api/runs/{run_id}/questions", response_model=QuestionResponse)
async def ask_run_question(
    run_id: uuid.UUID,
    payload: QuestionRequest,
    session: AsyncSession = Depends(get_db_session),
    config: Settings = Depends(get_settings),
) -> Any:
    service = GroundedQAService(session=session, config=config.ai_client_config())
    result = await service.answer_question(run_id, payload.question)
    return QuestionResponse(
        run_id=result.run_id,
        question=result.question,
        answer=result.answer,
        cited_case_ids=result.cited_case_ids,
        provider=result.provider,
        model=result.model,
        grounded=result.grounded,
    )

