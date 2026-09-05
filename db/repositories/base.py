"""Small reusable CRUD helpers for async repositories."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import Base


class AsyncRepository[ModelT: Base]:
    model: type[ModelT]

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(self, **values: Any) -> ModelT:
        instance = self.model(**values)
        self.session.add(instance)
        await self.session.flush()
        return instance

    async def get(self, record_id: uuid.UUID) -> ModelT | None:
        return await self.session.get(self.model, record_id)

    async def list(self, *, offset: int = 0, limit: int = 100) -> list[ModelT]:
        result = await self.session.scalars(select(self.model).offset(offset).limit(limit))
        return list(result)

    async def delete(self, record_id: uuid.UUID) -> bool:
        result = await self.session.execute(delete(self.model).where(self.model.id == record_id))
        return bool(result.rowcount)
