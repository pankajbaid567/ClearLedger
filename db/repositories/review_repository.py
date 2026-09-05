"""Persistence operations for human decisions, tasks, and AI analyses."""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import AIAnalysis, FollowUpTask, HumanDecision


class ReviewRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create_human_decision(self, **values: Any) -> HumanDecision:
        return await self._create(HumanDecision, values)

    async def create_follow_up_task(self, **values: Any) -> FollowUpTask:
        return await self._create(FollowUpTask, values)

    async def create_ai_analysis(self, **values: Any) -> AIAnalysis:
        return await self._create(AIAnalysis, values)

    async def latest_ai_analysis(self, case_id: str) -> AIAnalysis | None:
        result = await self.session.scalars(
            select(AIAnalysis)
            .where(AIAnalysis.case_id == case_id)
            .order_by(AIAnalysis.created_at.desc(), AIAnalysis.id.desc())
            .limit(1)
        )
        return result.one_or_none()

    async def _create(self, model: type[Any], values: dict[str, Any]) -> Any:
        instance = model(**values)
        self.session.add(instance)
        await self.session.flush()
        return instance
