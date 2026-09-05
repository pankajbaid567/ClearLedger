"""Shared route-level lookup and serialization helpers."""

from __future__ import annotations

import math
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.app.schemas.cases import CaseDetail, CaseSummary
from apps.api.app.schemas.runs import RunResponse, SourceFileResponse
from db.models import ReconciliationCase, ReconciliationRun
from db.repositories import RunRepository, SourceRepository
from services.reconciliation.run_service import RunServiceError


async def require_run(session: AsyncSession, run_id: uuid.UUID) -> ReconciliationRun:
    run = await RunRepository(session).get(run_id)
    if run is None:
        raise RunServiceError(
            "RUN_NOT_FOUND",
            "The requested reconciliation run was not found.",
            status_code=404,
            details={"run_id": str(run_id)},
        )
    return run


async def run_response(session: AsyncSession, run: ReconciliationRun) -> RunResponse:
    files = await SourceRepository(session).list_for_run(run.id)
    policy = (
        await RunRepository(session).get_policy(run.policy_version_id)
        if run.policy_version_id
        else None
    )
    return RunResponse(
        **RunResponse.model_validate(run).model_dump(
            exclude={"files", "policy_id", "policy_version"}
        ),
        policy_id=policy.policy_id if policy else None,
        policy_version=policy.version if policy else None,
        files=[SourceFileResponse.model_validate(item) for item in files],
    )


def case_summary(case: ReconciliationCase) -> CaseSummary:
    return CaseSummary.model_validate(case)


def case_detail(case: ReconciliationCase) -> CaseDetail:
    return CaseDetail(
        **case_summary(case).model_dump(),
        source_entity_ids=case.source_entity_ids,
        records=case.record_snapshot,
    )


def page_count(total: int, page_size: int) -> int:
    return math.ceil(total / page_size) if total else 0
