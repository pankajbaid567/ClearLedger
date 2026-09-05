"""Shared route-level lookup and serialization helpers."""

from __future__ import annotations

import math
import uuid
from datetime import date, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.app.auth import principal_from_session
from apps.api.app.schemas.cases import CaseDetail, CaseSummary
from apps.api.app.schemas.runs import RunResponse, SourceFileResponse
from db.models import FollowUpTask, ReconciliationCase, ReconciliationRun
from db.repositories import RunRepository, SourceRepository
from services.cash_position.case_timing import case_timing
from services.cash_position.service import cash_bucket_contribution
from services.normalization.policy import SettlementPolicy
from services.normalization.snapshot import recorded_policy
from services.reconciliation.run_service import RunServiceError


async def require_run(session: AsyncSession, run_id: uuid.UUID) -> ReconciliationRun:
    principal = principal_from_session(session)
    run = await RunRepository(session).get(run_id)
    if run is None or run.owner_subject != principal.subject:
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


def case_summary(
    case: ReconciliationCase,
    *,
    policy: SettlementPolicy | None = None,
    as_of: datetime | None = None,
    review_deadline: date | None = None,
) -> CaseSummary:
    amount, basis = cash_bucket_contribution(
        case.cash_bucket, case.net_amount_paise, case.residual_paise, case.gross_amount_paise
    )
    values = CaseSummary.model_validate(case).model_dump()
    values.update(cash_bucket_contribution_paise=amount, cash_contribution_basis=basis)
    if as_of is not None:
        values.update(
            case_timing(
                case.record_snapshot or [],
                as_of=as_of,
                policy=policy,
                case_state=case.case_state,
                review_deadline=review_deadline,
            )
        )
    return CaseSummary.model_validate(values)


async def case_summaries(
    session: AsyncSession,
    run: ReconciliationRun,
    cases: list[ReconciliationCase],
) -> list[CaseSummary]:
    policy = await recorded_policy(session, run)
    tasks = (
        list(
            await session.scalars(
                select(FollowUpTask).where(
                    FollowUpTask.reconciliation_run_id == run.id,
                    FollowUpTask.case_id.in_([case.case_id for case in cases]),
                    FollowUpTask.status == "OPEN",
                )
            )
        )
        if cases
        else []
    )
    deadlines: dict[str, date] = {}
    for task in tasks:
        if task.deadline is not None:
            deadlines[task.case_id] = min(task.deadline, deadlines.get(task.case_id, task.deadline))
    return [
        case_summary(
            case, policy=policy, as_of=run.as_of_at, review_deadline=deadlines.get(case.case_id)
        )
        for case in cases
    ]


def case_detail(case: ReconciliationCase, summary: CaseSummary | None = None) -> CaseDetail:
    return CaseDetail(
        **(summary or case_summary(case)).model_dump(),
        source_entity_ids=case.source_entity_ids,
        records=case.record_snapshot,
    )


def page_count(total: int, page_size: int) -> int:
    return math.ceil(total / page_size) if total else 0
