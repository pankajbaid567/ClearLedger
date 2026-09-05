"""Export one consistent, versioned snapshot with original source bytes."""

from __future__ import annotations

import base64
import hashlib
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import (
    AuditEvent,
    CashPositionSnapshot,
    HumanDecision,
    InvariantResult,
    RawSourceRow,
    ReconciliationCase,
    ReconciliationRun,
    SourceFile,
)
from services.cash_position.service import cash_bucket_contribution
from services.normalization.snapshot import recorded_policy
from services.reconciliation.run_service import RunServiceError
from services.reporting.verify import canonical_sha256


async def build_control_package(
    session: AsyncSession,
    run: ReconciliationRun,
    upload_dir: Path,
) -> dict[str, Any]:
    # Serialize against review and execution so a receipt never mixes revisions.
    await session.refresh(run, with_for_update=True)
    if run.status != "COMPLETED":
        raise RunServiceError(
            "RUN_NOT_RECONCILED",
            "Complete the run before exporting a control package.",
            status_code=409,
        )
    sources = list(
        await session.scalars(
            select(SourceFile)
            .where(SourceFile.reconciliation_run_id == run.id)
            .order_by(SourceFile.source_type)
        )
    )
    source_payloads = []
    for source in sources:
        try:
            content = (upload_dir / str(run.id) / f"{source.source_type}.csv").read_bytes()
        except OSError as exc:
            raise RunServiceError(
                "SOURCE_UNAVAILABLE", "Original source bytes are unavailable.", status_code=409
            ) from exc
        if hashlib.sha256(content).hexdigest() != source.file_checksum:
            raise RunServiceError(
                "SOURCE_INTEGRITY_FAILURE",
                "Original source bytes no longer match the registered checksum.",
                status_code=409,
            )
        rows = list(
            await session.scalars(
                select(RawSourceRow)
                .where(RawSourceRow.source_file_id == source.id)
                .order_by(RawSourceRow.row_number)
            )
        )
        source_payloads.append(
            {
                "source_type": source.source_type,
                "filename": source.filename,
                "sha256": source.file_checksum,
                "row_count": source.row_count,
                "content_base64": base64.b64encode(content).decode(),
                "rows": [
                    {
                        "row_number": row.row_number,
                        "raw_values": row.raw_payload,
                        "quality": row.quality,
                        "issues": row.validation_errors or [],
                    }
                    for row in rows
                ],
            }
        )
    cases = list(
        await session.scalars(
            select(ReconciliationCase)
            .where(ReconciliationCase.reconciliation_run_id == run.id)
            .order_by(ReconciliationCase.case_id)
        )
    )
    checks = list(
        await session.scalars(
            select(InvariantResult)
            .where(InvariantResult.reconciliation_run_id == run.id)
            .order_by(InvariantResult.case_id, InvariantResult.invariant_id)
        )
    )
    invariants: dict[str, list[dict[str, Any]]] = {}
    for check in checks:
        invariants.setdefault(check.case_id, []).append(
            {
                "id": check.invariant_id,
                "passed": check.passed,
                "expected": check.expected_value,
                "actual": check.actual_value,
            }
        )
    cash = (
        await session.scalars(
            select(CashPositionSnapshot).where(CashPositionSnapshot.reconciliation_run_id == run.id)
        )
    ).one()
    events = list(
        await session.scalars(
            select(AuditEvent)
            .where(AuditEvent.reconciliation_run_id == run.id)
            .order_by(AuditEvent.created_at, AuditEvent.id)
        )
    )
    decisions = list(
        await session.scalars(
            select(HumanDecision)
            .where(HumanDecision.reconciliation_run_id == run.id)
            .order_by(HumanDecision.created_at, HumanDecision.id)
        )
    )
    policy = (await recorded_policy(session, run)).model_dump(mode="json")
    baseline_result = run.config.get("baseline_result_payload")
    payload = {
        "run": {
            "id": str(run.id),
            "parent_run_id": str(run.parent_run_id) if run.parent_run_id else None,
            "execution_revision": run.execution_revision,
            "review_revision": run.review_revision,
            "as_of_at": run.as_of_at.isoformat(),
            "status": run.status,
            "app_version": run.app_version,
            "rule_set_version": run.rule_set_version,
            "total_source_rows": run.total_source_rows,
            "total_cases": run.total_cases,
            "dataset_checksum": run.dataset_checksum,
            "baseline_result_checksum": run.result_checksum,
        },
        "policy": policy,
        "policy_sha256": canonical_sha256(policy),
        "baseline_result": baseline_result,
        "input_manifest": run.input_manifest,
        "sources": source_payloads,
        "cases": [
            {
                "case_id": case.case_id,
                "run_id": str(run.id),
                "case_state": case.case_state,
                "currency": case.currency,
                "gross_amount_paise": case.gross_amount_paise,
                "net_amount_paise": case.net_amount_paise,
                "residual_paise": case.residual_paise,
                "cash_bucket": case.cash_bucket,
                "cash_bucket_contribution_paise": cash_bucket_contribution(
                    case.cash_bucket,
                    case.net_amount_paise,
                    case.residual_paise,
                    case.gross_amount_paise,
                )[0],
                "owner_role": case.owner_role,
                "next_action": case.next_action,
                "exception_code": case.exception_code,
                "human_reviewed": case.human_reviewed,
                "invariants": invariants.get(case.case_id, []),
            }
            for case in cases
        ],
        "cash": {
            "currency": cash.currency,
            "buckets": cash.buckets,
            "safe_cash_paise": cash.safe_cash_paise,
        },
        "baseline_evaluation": run.evaluation or None,
        "audit": [
            {
                "id": str(event.id),
                "run_id": str(run.id),
                "case_id": event.case_id,
                "actor": event.actor,
                "event_type": event.event_type,
                "created_at": event.created_at.isoformat(),
                "details": event.details,
            }
            for event in events
        ],
        "decisions": [
            {
                "id": str(item.id),
                "run_id": str(run.id),
                "case_id": item.case_id,
                "actor": item.actor,
                "action": item.action,
                "reason": item.reason,
                "previous_state": item.previous_state,
                "new_state": item.new_state,
                "execution_revision": item.execution_revision,
                "review_revision": item.review_revision,
                "created_at": item.created_at.isoformat(),
            }
            for item in decisions
        ],
    }
    return {
        "format": "clearledger.control.v1",
        "sha256": canonical_sha256(payload),
        "payload": payload,
    }
