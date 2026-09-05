"""Cash-position routes."""

from __future__ import annotations

import uuid
from datetime import date
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.app.dependencies import get_db_session
from apps.api.app.routes.helpers import require_run
from apps.api.app.schemas.cases import (
    CashForecastResponse,
    CashPositionResponse,
    TaxAuditResponse,
)
from db.models import ReconciliationCase, ReconciliationRun
from db.repositories import CaseRepository, RunRepository
from services.cash_position.service import (
    calculate_cash_forecast,
    calculate_tax_audit,
)
from services.normalization.snapshot import recorded_policy
from services.reconciliation.run_service import RunServiceError

router = APIRouter(prefix="/api/runs", tags=["cash-position"])


async def _coherent_run(session: AsyncSession, run_id: uuid.UUID) -> ReconciliationRun:
    """Serialize projection reads with review writes while allowing concurrent readers."""
    await require_run(session, run_id)
    run = await RunRepository(session).get_for_share(run_id)
    if run is None:  # The authenticated lookup above owns the public 404 contract.
        raise RunServiceError("RUN_NOT_FOUND", "The requested run is unavailable.", status_code=404)
    return run


@router.get("/{run_id}/cash-position", response_model=CashPositionResponse)
async def get_cash_position(
    run_id: uuid.UUID, session: AsyncSession = Depends(get_db_session)
) -> CashPositionResponse:
    run = await _coherent_run(session, run_id)
    snapshot = await CaseRepository(session).cash_position(run_id)
    if snapshot is None:
        raise RunServiceError(
            "CASH_POSITION_NOT_AVAILABLE",
            "Cash position is available after reconciliation completes.",
            status_code=404,
            details={"run_id": str(run_id)},
        )
    return CashPositionResponse(
        run_id=run_id,
        currency=snapshot.currency,
        bank_confirmed_paise=snapshot.bank_confirmed_paise,
        settlement_confirmed_in_transit_paise=(snapshot.settlement_confirmed_in_transit_paise),
        expected_settlement_paise=snapshot.expected_settlement_paise,
        at_risk_paise=snapshot.at_risk_paise,
        unresolved_paise=snapshot.unresolved_paise,
        scheduled_refunds_paise=snapshot.scheduled_refunds_paise,
        known_disputes_paise=snapshot.known_disputes_paise,
        known_reserve_holds_paise=snapshot.known_reserve_holds_paise,
        safe_cash_paise=snapshot.safe_cash_paise,
        buckets=snapshot.buckets,
        as_of_at=run.as_of_at,
        execution_revision=run.execution_revision,
        review_revision=run.review_revision,
    )


@router.get("/{run_id}/cash-forecast", response_model=CashForecastResponse)
async def get_cash_forecast(
    run_id: uuid.UUID,
    anchor_date: date | None = Query(default=None),
    session: AsyncSession = Depends(get_db_session),
) -> CashForecastResponse:
    run = await _coherent_run(session, run_id)
    policy = await recorded_policy(session, run)
    case_repo = CaseRepository(session)
    snapshot = await case_repo.cash_position(run_id)
    if snapshot is None:
        raise RunServiceError(
            "CASH_POSITION_NOT_AVAILABLE",
            "Cash position is available after reconciliation completes.",
            status_code=404,
            details={"run_id": str(run_id)},
        )
    persisted_cases = list(
        await session.scalars(
            select(ReconciliationCase)
            .where(ReconciliationCase.reconciliation_run_id == run_id)
            .order_by(ReconciliationCase.case_id)
        )
    )
    forecast = calculate_cash_forecast(
        cases=[
            {
                "case_id": c.case_id,
                "cash_bucket": c.cash_bucket,
                "net_amount_paise": c.net_amount_paise,
                "gross_amount_paise": c.gross_amount_paise,
                "record_snapshot": c.record_snapshot,
                "exception_code": c.exception_code,
            }
            for c in persisted_cases
        ],
        as_of_date=anchor_date or run.as_of_at.astimezone(ZoneInfo(policy.timezone)).date(),
        policy=policy,
        run_id=str(run_id),
        currency=snapshot.currency,
        safe_cash_paise=snapshot.safe_cash_paise,
    )
    return CashForecastResponse.model_validate(
        {
            **forecast.model_dump(),
            "execution_revision": run.execution_revision,
            "review_revision": run.review_revision,
        }
    )


@router.get("/{run_id}/tax-audit", response_model=TaxAuditResponse)
async def get_tax_audit(
    run_id: uuid.UUID,
    session: AsyncSession = Depends(get_db_session),
) -> TaxAuditResponse:
    run = await _coherent_run(session, run_id)
    policy = await recorded_policy(session, run)
    case_repo = CaseRepository(session)
    snapshot = await case_repo.cash_position(run_id)
    if snapshot is None:
        raise RunServiceError(
            "CASH_POSITION_NOT_AVAILABLE",
            "Cash position is available after reconciliation completes.",
            status_code=404,
            details={"run_id": str(run_id)},
        )
    persisted_cases = list(
        await session.scalars(
            select(ReconciliationCase)
            .where(ReconciliationCase.reconciliation_run_id == run_id)
            .order_by(ReconciliationCase.case_id)
        )
    )
    audit = calculate_tax_audit(
        cases=[
            {
                "case_id": c.case_id,
                "record_snapshot": c.record_snapshot,
                "exception_code": c.exception_code,
            }
            for c in persisted_cases
        ],
        policy=policy,
        run_id=str(run_id),
        currency=snapshot.currency,
    )
    return TaxAuditResponse.model_validate(
        {
            **audit.model_dump(),
            "execution_revision": run.execution_revision,
            "review_revision": run.review_revision,
        }
    )
