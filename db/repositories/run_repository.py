"""Persistence operations for reconciliation runs and policies."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import PolicyVersion, ReconciliationRun
from db.repositories.base import AsyncRepository


class RunRepository(AsyncRepository[ReconciliationRun]):
    model = ReconciliationRun

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session)

    async def get_for_update(self, run_id: uuid.UUID) -> ReconciliationRun | None:
        result = await self.session.scalars(
            select(ReconciliationRun).where(ReconciliationRun.id == run_id).with_for_update()
        )
        return result.one_or_none()

    async def update(self, run: ReconciliationRun, **values: Any) -> ReconciliationRun:
        for key, value in values.items():
            setattr(run, key, value)
        await self.session.flush()
        return run

    async def get_policy(self, policy_version_id: uuid.UUID) -> PolicyVersion | None:
        return await self.session.get(PolicyVersion, policy_version_id)

    async def get_policy_by_version(self, policy_id: str, version: str) -> PolicyVersion | None:
        result = await self.session.scalars(
            select(PolicyVersion).where(
                PolicyVersion.policy_id == policy_id,
                PolicyVersion.version == version,
            )
        )
        return result.one_or_none()

    async def create_policy(self, **values: Any) -> PolicyVersion:
        policy = PolicyVersion(**values)
        self.session.add(policy)
        await self.session.flush()
        return policy
