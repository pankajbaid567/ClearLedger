"""Persistence operations for source files, raw rows, and ingestion issues."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import IngestionIssue, RawSourceRow, SourceFile
from db.repositories.base import AsyncRepository


class SourceRepository(AsyncRepository[SourceFile]):
    model = SourceFile

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session)

    async def list_for_run(self, run_id: uuid.UUID) -> list[SourceFile]:
        result = await self.session.scalars(
            select(SourceFile)
            .where(SourceFile.reconciliation_run_id == run_id)
            .order_by(SourceFile.source_type)
        )
        return list(result)

    async def get_for_run_type(self, run_id: uuid.UUID, source_type: str) -> SourceFile | None:
        result = await self.session.scalars(
            select(SourceFile).where(
                SourceFile.reconciliation_run_id == run_id,
                SourceFile.source_type == source_type,
            )
        )
        return result.one_or_none()

    async def update(self, source_file: SourceFile, **values: Any) -> SourceFile:
        for key, value in values.items():
            setattr(source_file, key, value)
        await self.session.flush()
        return source_file

    async def clear_rows(self, source_file_id: uuid.UUID) -> None:
        await self.session.execute(
            delete(IngestionIssue).where(IngestionIssue.source_file_id == source_file_id)
        )
        await self.session.execute(
            delete(RawSourceRow).where(RawSourceRow.source_file_id == source_file_id)
        )

    async def create_raw_row(self, **values: Any) -> RawSourceRow:
        row = RawSourceRow(**values)
        self.session.add(row)
        await self.session.flush()
        return row

    async def create_issue(self, **values: Any) -> IngestionIssue:
        issue = IngestionIssue(**values)
        self.session.add(issue)
        await self.session.flush()
        return issue

    async def list_rows(self, source_file_id: uuid.UUID) -> list[RawSourceRow]:
        result = await self.session.scalars(
            select(RawSourceRow)
            .where(RawSourceRow.source_file_id == source_file_id)
            .order_by(RawSourceRow.row_number)
        )
        return list(result)
