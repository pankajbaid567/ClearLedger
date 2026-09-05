"""Cash-position routes."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.app.dependencies import get_db_session
from apps.api.app.schemas.cases import (
    CashForecastResponse,
    CashPositionResponse,
    TaxAuditResponse,
)
from db.repositories import CaseRepository
from services.cash_position.service import (
    calculate_cash_forecast,
    calculate_tax_audit,
)
from services.reconciliation.run_service import RunServiceError

router = APIRouter(prefix="/api/runs", tags=["cash-position"])


@router.get("/{run_id}/cash-position", response_model=CashPositionResponse)
async def get_cash_position(
    run_id: uuid.UUID, session: AsyncSession = Depends(get_db_session)
) -> CashPositionResponse:
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
    )


@router.get("/{run_id}/cash-forecast", response_model=CashForecastResponse)
async def get_cash_forecast(
    run_id: uuid.UUID,
    anchor_date: str | None = Query(default=None),
    session: AsyncSession = Depends(get_db_session),
) -> CashForecastResponse:
    case_repo = CaseRepository(session)
    snapshot = await case_repo.cash_position(run_id)
    if snapshot is None:
        raise RunServiceError(
            "CASH_POSITION_NOT_AVAILABLE",
            "Cash position is available after reconciliation completes.",
            status_code=404,
            details={"run_id": str(run_id)},
        )
    persisted_cases, _ = await case_repo.list_cases(run_id, limit=10_000)
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
        as_of_date=anchor_date,
        run_id=str(run_id),
        currency=snapshot.currency,
        safe_cash_paise=snapshot.safe_cash_paise,
    )
    return CashForecastResponse(
        run_id=forecast.run_id,
        as_of_date=forecast.as_of_date,
        currency=forecast.currency,
        days=[day.model_dump() for day in forecast.days],
        total_projected_inflow_paise=forecast.total_projected_inflow_paise,
        baseline_safe_cash_paise=forecast.baseline_safe_cash_paise,
        projected_final_cash_paise=forecast.projected_final_cash_paise,
    )


@router.get("/{run_id}/tax-audit", response_model=TaxAuditResponse)
async def get_tax_audit(
    run_id: uuid.UUID,
    session: AsyncSession = Depends(get_db_session),
) -> TaxAuditResponse:
    case_repo = CaseRepository(session)
    snapshot = await case_repo.cash_position(run_id)
    if snapshot is None:
        raise RunServiceError(
            "CASH_POSITION_NOT_AVAILABLE",
            "Cash position is available after reconciliation completes.",
            status_code=404,
            details={"run_id": str(run_id)},
        )
    persisted_cases, _ = await case_repo.list_cases(run_id, limit=10_000)
    audit = calculate_tax_audit(
        cases=[
            {
                "case_id": c.case_id,
                "record_snapshot": c.record_snapshot,
                "exception_code": c.exception_code,
            }
            for c in persisted_cases
        ],
        run_id=str(run_id),
        currency=snapshot.currency,
    )
    return TaxAuditResponse(
        run_id=audit.run_id,
        currency=audit.currency,
        total_cases_audited=audit.total_cases_audited,
        gross_payment_volume_paise=audit.gross_payment_volume_paise,
        total_gateway_fee_paise=audit.total_gateway_fee_paise,
        expected_gateway_fee_paise=audit.expected_gateway_fee_paise,
        fee_variance_paise=audit.fee_variance_paise,
        total_tax_paise=audit.total_tax_paise,
        expected_tax_paise=audit.expected_tax_paise,
        tax_variance_paise=audit.tax_variance_paise,
        claimable_itc_paise=audit.claimable_itc_paise,
        disputed_tax_paise=audit.disputed_tax_paise,
        tax_policy_pass_rate=audit.tax_policy_pass_rate,
        fee_policy_pass_rate=audit.fee_policy_pass_rate,
        discrepant_case_count=audit.discrepant_case_count,
        discrepancies=[item.model_dump() for item in audit.discrepancies],
        itc_status=audit.itc_status,
    )
