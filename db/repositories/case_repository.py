"""Persistence operations for reconciliation decisions and evidence."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import and_, delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import (
    AIAnalysis,
    CandidateRelationship,
    CashPositionSnapshot,
    EvidenceEdge,
    ExceptionRecord,
    InvariantResult,
    ReconciliationCase,
)


class CaseRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def clear_for_run(self, run_id: uuid.UUID) -> None:
        for model in (
            AIAnalysis,
            CashPositionSnapshot,
            ExceptionRecord,
            InvariantResult,
            EvidenceEdge,
            CandidateRelationship,
            ReconciliationCase,
        ):
            await self.session.execute(delete(model).where(model.reconciliation_run_id == run_id))

    async def create_case(self, **values: Any) -> ReconciliationCase:
        return await self._create(ReconciliationCase, values)

    async def create_candidate(self, **values: Any) -> CandidateRelationship:
        return await self._create(CandidateRelationship, values)

    async def create_evidence_edge(self, **values: Any) -> EvidenceEdge:
        return await self._create(EvidenceEdge, values)

    async def create_invariant_result(self, **values: Any) -> InvariantResult:
        return await self._create(InvariantResult, values)

    async def create_exception(self, **values: Any) -> ExceptionRecord:
        return await self._create(ExceptionRecord, values)

    async def create_cash_position(self, **values: Any) -> CashPositionSnapshot:
        return await self._create(CashPositionSnapshot, values)

    async def _create(self, model: type[Any], values: dict[str, Any]) -> Any:
        instance = model(**values)
        self.session.add(instance)
        await self.session.flush()
        return instance

    async def get_case(
        self, case_id: str, run_id: uuid.UUID | None = None
    ) -> ReconciliationCase | None:
        conditions = [ReconciliationCase.case_id == case_id]
        if run_id is not None:
            conditions.append(ReconciliationCase.reconciliation_run_id == run_id)
        result = await self.session.scalars(
            select(ReconciliationCase)
            .where(*conditions)
            .order_by(ReconciliationCase.created_at.desc())
            .limit(1)
        )
        return result.one_or_none()

    async def list_cases(
        self,
        run_id: uuid.UUID,
        *,
        offset: int = 0,
        limit: int = 50,
        state: str | None = None,
        severity: str | None = None,
        exception_code: str | None = None,
        owner: str | None = None,
        min_amount_paise: int | None = None,
        max_amount_paise: int | None = None,
        ai_involvement: bool | None = None,
        human_review: bool | None = None,
        min_age_days: int | None = None,
    ) -> tuple[list[ReconciliationCase], int]:
        conditions: list[Any] = [ReconciliationCase.reconciliation_run_id == run_id]
        if state:
            conditions.append(ReconciliationCase.case_state == state)
        if severity:
            conditions.append(ReconciliationCase.exception_severity == severity)
        if exception_code:
            conditions.append(ReconciliationCase.exception_code == exception_code)
        if owner:
            conditions.append(ReconciliationCase.owner_role == owner)
        if min_amount_paise is not None:
            conditions.append(ReconciliationCase.amount_at_risk_paise >= min_amount_paise)
        if max_amount_paise is not None:
            conditions.append(ReconciliationCase.amount_at_risk_paise <= max_amount_paise)
        if ai_involvement is not None:
            conditions.append(ReconciliationCase.ai_assisted == ai_involvement)
        if human_review is not None:
            conditions.append(ReconciliationCase.human_reviewed == human_review)
        if min_age_days is not None:
            cutoff = datetime.now(UTC).date().toordinal() - min_age_days
            cutoff_date = datetime.fromordinal(cutoff).replace(tzinfo=UTC)
            conditions.append(ReconciliationCase.created_at <= cutoff_date)

        where = and_(*conditions)
        total = await self.session.scalar(
            select(func.count()).select_from(ReconciliationCase).where(where)
        )
        result = await self.session.scalars(
            select(ReconciliationCase)
            .where(where)
            .order_by(ReconciliationCase.case_id)
            .offset(offset)
            .limit(limit)
        )
        return list(result), int(total or 0)

    async def update_case(self, case: ReconciliationCase, **values: Any) -> ReconciliationCase:
        for key, value in values.items():
            setattr(case, key, value)
        case.updated_at = datetime.now(UTC)
        await self.session.flush()
        return case

    async def evidence_for_case(self, run_id: uuid.UUID, case_id: str) -> list[EvidenceEdge]:
        result = await self.session.scalars(
            select(EvidenceEdge)
            .where(
                EvidenceEdge.reconciliation_run_id == run_id,
                EvidenceEdge.case_id == case_id,
            )
            .order_by(EvidenceEdge.relationship_type, EvidenceEdge.source_entity_id)
        )
        return list(result)

    async def invariants_for_case(self, run_id: uuid.UUID, case_id: str) -> list[InvariantResult]:
        result = await self.session.scalars(
            select(InvariantResult)
            .where(
                InvariantResult.reconciliation_run_id == run_id,
                InvariantResult.case_id == case_id,
            )
            .order_by(InvariantResult.invariant_id)
        )
        return list(result)

    async def candidates_for_case(
        self, run_id: uuid.UUID, entity_ids: list[str]
    ) -> list[CandidateRelationship]:
        result = await self.session.scalars(
            select(CandidateRelationship)
            .where(
                CandidateRelationship.reconciliation_run_id == run_id,
                CandidateRelationship.source_entity_id.in_(entity_ids),
                CandidateRelationship.target_entity_id.in_(entity_ids),
            )
            .order_by(CandidateRelationship.match_score.desc())
        )
        return list(result)

    async def exception_for_case(self, run_id: uuid.UUID, case_id: str) -> ExceptionRecord | None:
        result = await self.session.scalars(
            select(ExceptionRecord).where(
                ExceptionRecord.reconciliation_run_id == run_id,
                ExceptionRecord.case_id == case_id,
            )
        )
        return result.one_or_none()

    async def cash_position(self, run_id: uuid.UUID) -> CashPositionSnapshot | None:
        result = await self.session.scalars(
            select(CashPositionSnapshot).where(CashPositionSnapshot.reconciliation_run_id == run_id)
        )
        return result.one_or_none()
