"""Evaluation and injection-safe export routes."""

from __future__ import annotations

import csv
import io
import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Header
from fastapi.responses import JSONResponse, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.app.config import Settings, get_settings
from apps.api.app.dependencies import get_db_session
from apps.api.app.idempotency import replay_response, store_response
from apps.api.app.routes.helpers import require_run
from apps.api.app.schemas.runs import EvaluationResponse
from db.models import AuditEvent, ExceptionRecord, ReconciliationCase
from services.evaluation import evaluate_persisted_run
from services.reconciliation.run_service import RunServiceError

router = APIRouter(prefix="/api/runs", tags=["evaluation-and-exports"])
IdempotencyKey = Annotated[str, Header(alias="Idempotency-Key", min_length=1, max_length=200)]
_FORMULA_PREFIXES = ("=", "+", "-", "@", "\t", "\r")


def _safe_cell(value: Any) -> Any:
    if value is None:
        return ""
    rendered = str(value)
    return f"'{rendered}" if rendered.startswith(_FORMULA_PREFIXES) else rendered


def _csv_response(headers: list[str], rows: list[list[Any]], filename: str) -> Response:
    output = io.StringIO(newline="")
    writer = csv.writer(output, lineterminator="\n")
    writer.writerow(headers)
    writer.writerows([[_safe_cell(cell) for cell in row] for row in rows])
    return Response(
        output.getvalue(),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/{run_id}/evaluate", response_model=EvaluationResponse)
async def evaluate_run(
    run_id: uuid.UUID,
    idempotency_key: IdempotencyKey,
    session: AsyncSession = Depends(get_db_session),
    config: Settings = Depends(get_settings),
) -> Any:
    scope = f"POST:/api/runs/{run_id}/evaluate"
    request_data = {"run_id": str(run_id)}
    replay = await replay_response(
        session, scope=scope, key=idempotency_key, request_payload=request_data
    )
    if replay:
        return replay
    evaluation = await evaluate_persisted_run(session, run_id, config.ground_truth_path)
    response = EvaluationResponse.model_validate(evaluation)
    await store_response(
        session,
        scope=scope,
        key=idempotency_key,
        request_payload=request_data,
        response_payload=response.model_dump(mode="json"),
    )
    return response


@router.get("/{run_id}/evaluation", response_model=EvaluationResponse)
async def get_evaluation(
    run_id: uuid.UUID, session: AsyncSession = Depends(get_db_session)
) -> EvaluationResponse:
    run = await require_run(session, run_id)
    if not run.evaluation:
        raise RunServiceError(
            "EVALUATION_NOT_AVAILABLE",
            "Run evaluation has not been executed.",
            status_code=404,
            details={"run_id": str(run_id)},
        )
    return EvaluationResponse.model_validate(run.evaluation)


@router.get("/{run_id}/exports/evaluation.json")
async def export_evaluation_json(
    run_id: uuid.UUID, session: AsyncSession = Depends(get_db_session)
) -> JSONResponse:
    evaluation = await get_evaluation(run_id, session)
    return JSONResponse(
        evaluation.model_dump(mode="json"),
        headers={"Content-Disposition": f'attachment; filename="evaluation-{run_id}.json"'},
    )


@router.get("/{run_id}/exports/evaluation.md")
async def export_evaluation_markdown(
    run_id: uuid.UUID, session: AsyncSession = Depends(get_db_session)
) -> Response:
    evaluation = await get_evaluation(run_id, session)
    aggregate = evaluation.aggregate
    precision = aggregate.get("relationship_precision", aggregate.get("precision", 0))
    recall = aggregate.get("relationship_recall", aggregate.get("recall", 0))
    lines = [
        "# ClearLedger Evaluation",
        "",
        f"- Run ID: `{run_id}`",
        f"- Dataset: `{evaluation.dataset_id}`",
        f"- Precision: {precision:.4f}",
        f"- Recall: {recall:.4f}",
        f"- F1: {aggregate.get('relationship_f1', 0):.4f}",
        f"- STP rate: {aggregate.get('stp_rate', 0):.4f}",
        "",
        "## Scenario Breakdown",
        "",
        "| Scenario | Cases | Precision | Recall | F1 |",
        "| --- | ---: | ---: | ---: | ---: |",
    ]
    for scenario, values in sorted(evaluation.scenario_breakdown.items()):
        lines.append(
            "| {scenario} | {cases} | {precision:.4f} | {recall:.4f} | {f1:.4f} |".format(
                scenario=scenario,
                cases=values.get("case_count", values.get("total_cases", "-")),
                precision=values.get("relationship_precision", values.get("precision", 0)),
                recall=values.get("relationship_recall", values.get("recall", 0)),
                f1=values.get("relationship_f1", values.get("f1", 0)),
            )
        )
    return Response(
        "\n".join(lines) + "\n",
        media_type="text/markdown; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="evaluation-{run_id}.md"'},
    )


@router.get("/{run_id}/exports/reconciliation.csv")
async def export_reconciliation(
    run_id: uuid.UUID, session: AsyncSession = Depends(get_db_session)
) -> Response:
    await require_run(session, run_id)
    result = await session.scalars(
        select(ReconciliationCase)
        .where(
            ReconciliationCase.reconciliation_run_id == run_id,
            ReconciliationCase.case_state == "RECONCILED",
        )
        .order_by(ReconciliationCase.case_id)
    )
    cases = list(result)
    headers = [
        "case_id",
        "case_state",
        "gross_amount_paise",
        "net_amount_paise",
        "residual_paise",
        "cash_bucket",
        "settlement_id",
        "bank_receipt_state",
        "human_reviewed",
    ]
    rows = [
        [
            case.case_id,
            case.case_state,
            case.gross_amount_paise,
            case.net_amount_paise,
            case.residual_paise,
            case.cash_bucket,
            case.settlement_id,
            case.bank_receipt_state,
            case.human_reviewed,
        ]
        for case in cases
    ]
    return _csv_response(headers, rows, f"reconciliation-{run_id}.csv")


@router.get("/{run_id}/exports/exceptions.csv")
async def export_exceptions(
    run_id: uuid.UUID, session: AsyncSession = Depends(get_db_session)
) -> Response:
    await require_run(session, run_id)
    result = await session.scalars(
        select(ExceptionRecord)
        .where(ExceptionRecord.reconciliation_run_id == run_id)
        .order_by(ExceptionRecord.case_id)
    )
    exceptions = list(result)
    headers = [
        "case_id",
        "exception_code",
        "severity",
        "amount_at_risk_paise",
        "summary",
        "next_action",
        "owner_role",
        "ai_assisted",
    ]
    rows = [
        [
            item.case_id,
            item.exception_code,
            item.severity,
            item.amount_at_risk_paise,
            item.summary,
            item.next_action,
            item.owner_role,
            item.ai_assisted,
        ]
        for item in exceptions
    ]
    return _csv_response(headers, rows, f"exceptions-{run_id}.csv")


@router.get("/{run_id}/exports/audit.json")
async def export_audit(
    run_id: uuid.UUID, session: AsyncSession = Depends(get_db_session)
) -> JSONResponse:
    await require_run(session, run_id)
    result = await session.scalars(
        select(AuditEvent)
        .where(AuditEvent.reconciliation_run_id == run_id)
        .order_by(AuditEvent.created_at, AuditEvent.id)
    )
    events = [
        {
            "id": str(item.id),
            "reconciliation_run_id": str(item.reconciliation_run_id),
            "case_id": item.case_id,
            "source_file_id": str(item.source_file_id) if item.source_file_id else None,
            "event_type": item.event_type,
            "stage": item.stage,
            "rule_id": item.rule_id,
            "severity": item.severity,
            "details": item.details,
            "actor": item.actor,
            "duration_ms": item.duration_ms,
            "created_at": item.created_at.isoformat(),
        }
        for item in result
    ]
    return JSONResponse({"run_id": str(run_id), "events": events})
