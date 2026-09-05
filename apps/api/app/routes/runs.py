"""Run creation, upload, validation, execution, status, and metrics routes."""

from __future__ import annotations

import hashlib
import uuid
from io import BytesIO
from pathlib import Path
from typing import Annotated, Any

from fastapi import APIRouter, Depends, File, Header, Query, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.app.auth import principal_from_session
from apps.api.app.dependencies import get_db_session, get_run_service
from apps.api.app.errors import APIError
from apps.api.app.idempotency import replay_response, store_response
from apps.api.app.routes.helpers import page_count, require_run, run_response
from apps.api.app.schemas.cases import AuditEventResponse, PaginatedAudit
from apps.api.app.schemas.runs import (
    DemoRunResponse,
    MetricsResponse,
    ReconciliationResponse,
    RunCreateRequest,
    RunResponse,
    RunStatusResponse,
    SourceFileResponse,
)
from db.repositories import AuditRepository
from services.reconciliation.run_service import REQUIRED_SOURCE_TYPES, RunService, ValidationResult

router = APIRouter(prefix="/api/runs", tags=["runs"])
IdempotencyKey = Annotated[str, Header(alias="Idempotency-Key", min_length=1, max_length=200)]
_ROOT = Path(__file__).resolve().parents[4]


@router.post("", response_model=RunResponse, status_code=status.HTTP_201_CREATED)
async def create_run(
    payload: RunCreateRequest,
    idempotency_key: IdempotencyKey,
    session: AsyncSession = Depends(get_db_session),
    service: RunService = Depends(get_run_service),
) -> Any:
    scope = "POST:/api/runs"
    request_data = payload.model_dump(mode="json")
    replay = await replay_response(
        session, scope=scope, key=idempotency_key, request_payload=request_data
    )
    if replay:
        return replay
    run = await service.create_run(
        payload.policy_version_id, parent_run_id=payload.parent_run_id, as_of_at=payload.as_of_at
    )
    response = await run_response(session, run)
    response_data = response.model_dump(mode="json")
    await store_response(
        session,
        scope=scope,
        key=idempotency_key,
        request_payload=request_data,
        response_payload=response_data,
        status_code=status.HTTP_201_CREATED,
    )
    return response


@router.post("/demo", response_model=DemoRunResponse, status_code=status.HTTP_201_CREATED)
async def create_demo_run(
    idempotency_key: IdempotencyKey,
    session: AsyncSession = Depends(get_db_session),
    service: RunService = Depends(get_run_service),
) -> Any:
    if not principal_from_session(session).is_demo:
        raise APIError(
            "DEMO_DISABLED",
            "Synthetic demo creation is available only in explicit local demo mode.",
            status_code=403,
        )
    demo_dir = _ROOT / "data" / "demo"
    file_data = {
        source_type: (demo_dir / f"{source_type}.csv").read_bytes()
        for source_type in sorted(REQUIRED_SOURCE_TYPES)
    }
    request_data = {
        "dataset": "clearledger-demo-v1",
        "checksums": {
            source_type: hashlib.sha256(content).hexdigest()
            for source_type, content in file_data.items()
        },
    }
    scope = "POST:/api/runs/demo"
    replay = await replay_response(
        session, scope=scope, key=idempotency_key, request_payload=request_data
    )
    if replay:
        return replay

    run = await service.create_run()
    uploads = {
        source_type: UploadFile(
            filename=f"{source_type}.csv",
            file=BytesIO(content),
        )
        for source_type, content in file_data.items()
    }
    try:
        await service.add_files_to_run(run.id, uploads)
    finally:
        for upload in uploads.values():
            await upload.close()
    validation = await service.validate_run(run.id)
    response = DemoRunResponse(
        run=await run_response(session, run),
        validation=validation.model_dump(mode="json"),
    )
    await store_response(
        session,
        scope=scope,
        key=idempotency_key,
        request_payload=request_data,
        response_payload=response.model_dump(mode="json"),
        status_code=status.HTTP_201_CREATED,
    )
    return response


@router.post("/{run_id}/files", response_model=list[SourceFileResponse])
async def upload_files(
    run_id: uuid.UUID,
    idempotency_key: IdempotencyKey,
    orders: Annotated[UploadFile | None, File()] = None,
    payments: Annotated[UploadFile | None, File()] = None,
    settlements: Annotated[UploadFile | None, File()] = None,
    settlement_components: Annotated[UploadFile | None, File()] = None,
    bank_transactions: Annotated[UploadFile | None, File()] = None,
    session: AsyncSession = Depends(get_db_session),
    service: RunService = Depends(get_run_service),
) -> Any:
    await require_run(session, run_id)
    files = {
        name: upload
        for name, upload in {
            "orders": orders,
            "payments": payments,
            "settlements": settlements,
            "settlement_components": settlement_components,
            "bank_transactions": bank_transactions,
        }.items()
        if upload is not None
    }

    # Validate file sizes before reading into memory
    max_bytes = service.max_upload_bytes
    for name, upload in files.items():
        upload.file.seek(0, 2)  # Seek to end
        size = upload.file.tell()
        upload.file.seek(0)  # Reset to beginning
        if size > max_bytes:
            raise APIError(
                "FILE_TOO_LARGE",
                f"{name}.csv exceeds maximum size of {max_bytes} bytes (actual: {size} bytes)",
                status_code=413,
            )

    request_data = {}
    for name, upload in files.items():
        content = await upload.read(max_bytes + 1)
        request_data[name] = {
            "filename": upload.filename,
            "checksum": hashlib.sha256(content).hexdigest(),
            "size_bytes": len(content),
        }
        await upload.seek(0)
    scope = f"POST:/api/runs/{run_id}/files"
    replay = await replay_response(
        session, scope=scope, key=idempotency_key, request_payload=request_data
    )
    if replay:
        return replay
    uploaded = await service.add_files_to_run(run_id, files)
    response = [SourceFileResponse.model_validate(item) for item in uploaded]
    await store_response(
        session,
        scope=scope,
        key=idempotency_key,
        request_payload=request_data,
        response_payload=[item.model_dump(mode="json") for item in response],
    )
    return response


@router.post("/{run_id}/validate", response_model=ValidationResult)
async def validate_run(
    run_id: uuid.UUID,
    idempotency_key: IdempotencyKey,
    session: AsyncSession = Depends(get_db_session),
    service: RunService = Depends(get_run_service),
) -> Any:
    await require_run(session, run_id)
    scope = f"POST:/api/runs/{run_id}/validate"
    request_data = {"run_id": str(run_id)}
    replay = await replay_response(
        session, scope=scope, key=idempotency_key, request_payload=request_data
    )
    if replay:
        return replay
    result = await service.validate_run(run_id)
    response_data = result.model_dump(mode="json")
    await store_response(
        session,
        scope=scope,
        key=idempotency_key,
        request_payload=request_data,
        response_payload=response_data,
    )
    return result


@router.post("/{run_id}/reconcile", response_model=ReconciliationResponse)
async def reconcile_run(
    run_id: uuid.UUID,
    idempotency_key: IdempotencyKey,
    session: AsyncSession = Depends(get_db_session),
    service: RunService = Depends(get_run_service),
) -> Any:
    await require_run(session, run_id)
    scope = f"POST:/api/runs/{run_id}/reconcile"
    request_data = {"run_id": str(run_id)}
    replay = await replay_response(
        session, scope=scope, key=idempotency_key, request_payload=request_data
    )
    if replay:
        return replay
    result = await service.execute_reconciliation(run_id)
    run = await require_run(session, run_id)
    baseline = run.config.get("baseline_counts", {})
    response = ReconciliationResponse(
        run_id=run_id,
        execution_revision=run.execution_revision,
        review_revision=run.review_revision,
        replayed=result is None,
        status=run.status,
        total_source_records=result.total_source_records
        if result
        else baseline.get("total_source_records", run.total_source_rows or 0),
        total_cases=len(result.cases)
        if result
        else baseline.get("total_cases", run.total_cases or 0),
        evidence_edges=len(result.evidence_edges)
        if result
        else baseline.get("evidence_edges", run.metrics.get("evidence_edges", 0)),
        exceptions=len(result.exceptions)
        if result
        else baseline.get("exceptions", run.metrics.get("exception_cases", 0)),
        result_checksum=run.result_checksum or "",
    )
    response_data = response.model_dump(mode="json")
    await store_response(
        session,
        scope=scope,
        key=idempotency_key,
        request_payload=request_data,
        response_payload=response_data,
    )
    # Reconciliation is immediately followed by evaluation in the operator flow.
    # Commit both the result and idempotency record before the response is visible.
    await session.commit()
    return response


@router.get("/{run_id}", response_model=RunResponse)
async def get_run(
    run_id: uuid.UUID, session: AsyncSession = Depends(get_db_session)
) -> RunResponse:
    return await run_response(session, await require_run(session, run_id))


@router.get("/{run_id}/status", response_model=RunStatusResponse)
async def get_run_status(
    run_id: uuid.UUID, session: AsyncSession = Depends(get_db_session)
) -> RunStatusResponse:
    run = await require_run(session, run_id)
    return RunStatusResponse(
        run_id=run.id,
        execution_revision=run.execution_revision,
        review_revision=run.review_revision,
        stage=run.stage,
        progress_percent=run.progress_percent,
        processed_records=run.processed_records,
        status=run.status,
        failure_reason=run.failure_reason,
        started_at=run.started_at,
        completed_at=run.completed_at,
    )


@router.get("/{run_id}/metrics", response_model=MetricsResponse)
async def get_run_metrics(
    run_id: uuid.UUID, session: AsyncSession = Depends(get_db_session)
) -> MetricsResponse:
    run = await require_run(session, run_id)
    return MetricsResponse(
        run_id=run.id,
        status=run.status,
        execution_revision=run.execution_revision,
        review_revision=run.review_revision,
        metrics_scope=(
            "CURRENT_REVIEW_PROJECTION_WITH_BASELINE_EVALUATION"
            if run.evaluation
            else "CURRENT_REVIEW_PROJECTION"
        ),
        evaluation_scope=(run.evaluation.get("evaluation_scope") if run.evaluation else None),
        evaluated_review_revision=(
            run.evaluation.get("evaluated_review_revision") if run.evaluation else None
        ),
        metrics=run.metrics,
    )


@router.get("/{run_id}/audit", response_model=PaginatedAudit)
async def get_run_audit(
    run_id: uuid.UUID,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=500)] = 100,
    session: AsyncSession = Depends(get_db_session),
) -> PaginatedAudit:
    await require_run(session, run_id)
    items, total = await AuditRepository(session).list_for_run(
        run_id, offset=(page - 1) * page_size, limit=page_size
    )
    return PaginatedAudit(
        items=[AuditEventResponse.model_validate(item) for item in items],
        page=page,
        page_size=page_size,
        total=total,
        pages=page_count(total, page_size),
    )
