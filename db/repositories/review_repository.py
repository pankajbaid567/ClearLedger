"""Persistence operations for human decisions, tasks, and AI analyses."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import AIAnalysis, FollowUpTask, HumanDecision, ReconciliationRun


class ReviewRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create_human_decision(self, **values: Any) -> HumanDecision:
        run = await self.session.get(ReconciliationRun, values["reconciliation_run_id"])
        if run is not None:
            values.update(
                execution_revision=run.execution_revision, review_revision=run.review_revision
            )
        return await self._create(HumanDecision, values)

    async def create_follow_up_task(self, **values: Any) -> FollowUpTask:
        return await self._create(FollowUpTask, values)

    async def create_ai_analysis(self, **values: Any) -> AIAnalysis:
        return await self._create(AIAnalysis, values)

    async def latest_ai_analysis(
        self, case_id: str, run_id: uuid.UUID | None = None
    ) -> AIAnalysis | None:
        conditions = [AIAnalysis.case_id == case_id]
        if run_id is not None:
            conditions.append(AIAnalysis.reconciliation_run_id == run_id)
        result = await self.session.scalars(
            select(AIAnalysis)
            .where(*conditions)
            .order_by(AIAnalysis.created_at.desc(), AIAnalysis.id.desc())
            .limit(1)
        )
        return result.one_or_none()

    async def _create(self, model: type[Any], values: dict[str, Any]) -> Any:
        instance = model(**values)
        self.session.add(instance)
        await self.session.flush()
        return instance
