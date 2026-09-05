"""Run-scoped, authenticated, invariant-gated human review routes."""

from __future__ import annotations

import uuid
from datetime import UTC
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Header
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.app.auth import principal_from_session
from apps.api.app.dependencies import get_db_session
from apps.api.app.idempotency import replay_response, store_response
from apps.api.app.routes.helpers import require_run
from apps.api.app.schemas.review import (
    AssignRequest,
    DeferRequest,
    ReviewActionRequest,
    ReviewActionResponse,
    TaskCreateRequest,
    TaskResponse,
)
from db.repositories import CaseRepository
from services.reconciliation.review_service import ReviewService
from services.reconciliation.run_service import RunServiceError

router = APIRouter(tags=["human-review"])
IdempotencyKey = Annotated[str, Header(alias="Idempotency-Key", min_length=1, max_length=200)]


async def _action(
    case_id: str,
    action: str,
    payload: Any,
    key: str,
    session: AsyncSession,
    run_id: uuid.UUID | None,
) -> Any:
    if run_id is not None:
        await require_run(session, run_id)
    case = await CaseRepository(session).get_case(case_id, run_id)
    if case is None:
        raise RunServiceError(
            "CASE_NOT_FOUND", "The requested case was not found.", status_code=404
        )
    run_id = case.reconciliation_run_id
    scope = f"POST:/api/runs/{run_id}/cases/{case_id}/{action}"
    actor = principal_from_session(session).subject
    request_data = {**payload.model_dump(mode="json"), "actor": actor}
    replay = await replay_response(
        session,
        scope=scope,
        key=key,
        request_payload=request_data,
        legacy_scopes=(f"POST:/api/cases/{case_id}/{action}",),
    )
    if replay:
        return replay
    service = ReviewService(
        session, run_id=run_id, expected_review_revision=payload.expected_review_revision
    )
    values = payload.model_dump(exclude={"actor", "expected_review_revision"})
    method = service.create_task if action == "tasks" else getattr(service, action)
    if action == "tasks":
        values["task_type"] = payload.task_type.value
    result = await method(case_id, actor=actor, **values)
    if action == "approve":
        result = result[0]
    if action == "tasks":
        response = TaskResponse.model_validate(result, from_attributes=True)
    else:
        response = ReviewActionResponse(
            run_id=run_id,
            execution_revision=result.execution_revision,
            review_revision=result.review_revision,
            case_id=result.case_id,
            action=result.action,
            previous_state=result.previous_state,
            new_state=result.new_state,
            invariant_passed=result.invariant_passed,
            human_reviewed=True,
            created_at=result.created_at.astimezone(UTC),
        )
    await store_response(
        session,
        scope=scope,
        key=key,
        request_payload=request_data,
        response_payload=response.model_dump(mode="json"),
    )
    return response


@router.post("/api/cases/{case_id}/approve", response_model=ReviewActionResponse)
@router.post("/api/runs/{run_id}/cases/{case_id}/approve", response_model=ReviewActionResponse)
async def approve_case(
    case_id: str,
    payload: ReviewActionRequest,
    idempotency_key: IdempotencyKey,
    run_id: uuid.UUID | None = None,
    session: AsyncSession = Depends(get_db_session),
) -> Any:
    return await _action(case_id, "approve", payload, idempotency_key, session, run_id)


@router.post("/api/cases/{case_id}/reject", response_model=ReviewActionResponse)
@router.post("/api/runs/{run_id}/cases/{case_id}/reject", response_model=ReviewActionResponse)
async def reject_case(
    case_id: str,
    payload: ReviewActionRequest,
    idempotency_key: IdempotencyKey,
    run_id: uuid.UUID | None = None,
    session: AsyncSession = Depends(get_db_session),
) -> Any:
    return await _action(case_id, "reject", payload, idempotency_key, session, run_id)


@router.post("/api/cases/{case_id}/defer", response_model=ReviewActionResponse)
@router.post("/api/runs/{run_id}/cases/{case_id}/defer", response_model=ReviewActionResponse)
async def defer_case(
    case_id: str,
    payload: DeferRequest,
    idempotency_key: IdempotencyKey,
    run_id: uuid.UUID | None = None,
    session: AsyncSession = Depends(get_db_session),
) -> Any:
    return await _action(case_id, "defer", payload, idempotency_key, session, run_id)


@router.post("/api/cases/{case_id}/assign", response_model=ReviewActionResponse)
@router.post("/api/runs/{run_id}/cases/{case_id}/assign", response_model=ReviewActionResponse)
async def assign_case(
    case_id: str,
    payload: AssignRequest,
    idempotency_key: IdempotencyKey,
    run_id: uuid.UUID | None = None,
    session: AsyncSession = Depends(get_db_session),
) -> Any:
    return await _action(case_id, "assign", payload, idempotency_key, session, run_id)


@router.post("/api/cases/{case_id}/tasks", response_model=TaskResponse)
@router.post("/api/runs/{run_id}/cases/{case_id}/tasks", response_model=TaskResponse)
async def create_task(
    case_id: str,
    payload: TaskCreateRequest,
    idempotency_key: IdempotencyKey,
    run_id: uuid.UUID | None = None,
    session: AsyncSession = Depends(get_db_session),
) -> Any:
    return await _action(case_id, "tasks", payload, idempotency_key, session, run_id)
