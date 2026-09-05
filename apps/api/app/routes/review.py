"""Invariant-gated human review routes."""

from __future__ import annotations

from datetime import UTC
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Header
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.app.dependencies import get_db_session
from apps.api.app.idempotency import replay_response, store_response
from apps.api.app.schemas.review import (
    AssignRequest,
    DeferRequest,
    ReviewActionRequest,
    ReviewActionResponse,
    TaskCreateRequest,
    TaskResponse,
)
from services.reconciliation.review_service import ReviewService

router = APIRouter(prefix="/api/cases", tags=["human-review"])
IdempotencyKey = Annotated[str, Header(alias="Idempotency-Key", min_length=1, max_length=200)]


def _decision_response(decision: Any) -> ReviewActionResponse:
    return ReviewActionResponse(
        case_id=decision.case_id,
        action=decision.action,
        previous_state=decision.previous_state,
        new_state=decision.new_state,
        invariant_passed=decision.invariant_passed,
        human_reviewed=True,
        created_at=decision.created_at.astimezone(UTC),
    )


@router.post("/{case_id}/approve", response_model=ReviewActionResponse)
async def approve_case(
    case_id: str,
    payload: ReviewActionRequest,
    idempotency_key: IdempotencyKey,
    session: AsyncSession = Depends(get_db_session),
) -> Any:
    scope = f"POST:/api/cases/{case_id}/approve"
    request_data = payload.model_dump(mode="json")
    replay = await replay_response(
        session, scope=scope, key=idempotency_key, request_payload=request_data
    )
    if replay:
        return replay
    decision, _ = await ReviewService(session).approve(
        case_id,
        actor=payload.actor,
        reason=payload.reason,
        note=payload.note,
    )
    response = _decision_response(decision)
    await store_response(
        session,
        scope=scope,
        key=idempotency_key,
        request_payload=request_data,
        response_payload=response.model_dump(mode="json"),
    )
    return response


@router.post("/{case_id}/reject", response_model=ReviewActionResponse)
async def reject_case(
    case_id: str,
    payload: ReviewActionRequest,
    idempotency_key: IdempotencyKey,
    session: AsyncSession = Depends(get_db_session),
) -> Any:
    return await _simple_action(case_id, "reject", payload, idempotency_key, session)


@router.post("/{case_id}/defer", response_model=ReviewActionResponse)
async def defer_case(
    case_id: str,
    payload: DeferRequest,
    idempotency_key: IdempotencyKey,
    session: AsyncSession = Depends(get_db_session),
) -> Any:
    scope = f"POST:/api/cases/{case_id}/defer"
    request_data = payload.model_dump(mode="json")
    replay = await replay_response(
        session, scope=scope, key=idempotency_key, request_payload=request_data
    )
    if replay:
        return replay
    decision = await ReviewService(session).defer(
        case_id,
        actor=payload.actor,
        until=payload.until,
        reason=payload.reason,
        note=payload.note,
    )
    response = _decision_response(decision)
    await store_response(
        session,
        scope=scope,
        key=idempotency_key,
        request_payload=request_data,
        response_payload=response.model_dump(mode="json"),
    )
    return response


@router.post("/{case_id}/assign", response_model=ReviewActionResponse)
async def assign_case(
    case_id: str,
    payload: AssignRequest,
    idempotency_key: IdempotencyKey,
    session: AsyncSession = Depends(get_db_session),
) -> Any:
    scope = f"POST:/api/cases/{case_id}/assign"
    request_data = payload.model_dump(mode="json")
    replay = await replay_response(
        session, scope=scope, key=idempotency_key, request_payload=request_data
    )
    if replay:
        return replay
    decision = await ReviewService(session).assign(
        case_id,
        actor=payload.actor,
        owner_role=payload.owner_role,
        reason=payload.reason,
        note=payload.note,
    )
    response = _decision_response(decision)
    await store_response(
        session,
        scope=scope,
        key=idempotency_key,
        request_payload=request_data,
        response_payload=response.model_dump(mode="json"),
    )
    return response


@router.post("/{case_id}/tasks", response_model=TaskResponse)
async def create_task(
    case_id: str,
    payload: TaskCreateRequest,
    idempotency_key: IdempotencyKey,
    session: AsyncSession = Depends(get_db_session),
) -> Any:
    scope = f"POST:/api/cases/{case_id}/tasks"
    request_data = payload.model_dump(mode="json")
    replay = await replay_response(
        session, scope=scope, key=idempotency_key, request_payload=request_data
    )
    if replay:
        return replay
    task = await ReviewService(session).create_task(
        case_id,
        actor=payload.actor,
        task_type=payload.task_type.value,
        amount_at_risk_paise=payload.amount_at_risk_paise,
        required_evidence=payload.required_evidence,
        deadline=payload.deadline,
        action_code=payload.action_code,
    )
    response = TaskResponse(
        id=task.id,
        case_id=task.case_id,
        task_type=task.task_type,
        amount_at_risk_paise=task.amount_at_risk_paise,
        currency=task.currency,
        required_evidence=task.required_evidence,
        deadline=task.deadline,
        action_code=task.action_code,
        status=task.status,
        created_at=task.created_at,
    )
    await store_response(
        session,
        scope=scope,
        key=idempotency_key,
        request_payload=request_data,
        response_payload=response.model_dump(mode="json"),
    )
    return response


async def _simple_action(
    case_id: str,
    action: str,
    payload: ReviewActionRequest,
    idempotency_key: str,
    session: AsyncSession,
) -> Any:
    scope = f"POST:/api/cases/{case_id}/{action}"
    request_data = payload.model_dump(mode="json")
    replay = await replay_response(
        session, scope=scope, key=idempotency_key, request_payload=request_data
    )
    if replay:
        return replay
    method = getattr(ReviewService(session), action)
    decision = await method(case_id, actor=payload.actor, reason=payload.reason, note=payload.note)
    response = _decision_response(decision)
    await store_response(
        session,
        scope=scope,
        key=idempotency_key,
        request_payload=request_data,
        response_payload=response.model_dump(mode="json"),
    )
    return response
