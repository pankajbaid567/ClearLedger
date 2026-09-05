"""Persistence operations for immutable audit events."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import AuditEvent


class AuditRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(self, **values: Any) -> AuditEvent:
        event = AuditEvent(**values)
        self.session.add(event)
        await self.session.flush()
        return event

    async def list_for_run(
        self, run_id: uuid.UUID, *, offset: int = 0, limit: int = 100
    ) -> tuple[list[AuditEvent], int]:
        condition = AuditEvent.reconciliation_run_id == run_id
        total = await self.session.scalar(
            select(func.count()).select_from(AuditEvent).where(condition)
        )
        result = await self.session.scalars(
            select(AuditEvent)
            .where(condition)
            .order_by(AuditEvent.created_at, AuditEvent.id)
            .offset(offset)
            .limit(limit)
        )
        return list(result), int(total or 0)
