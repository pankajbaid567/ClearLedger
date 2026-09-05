"""Explicit evaluator boundary for API-triggered scoring."""

from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from db.repositories import AuditRepository, RunRepository
from evaluator.metrics import compute_all_metrics, compute_scenario_breakdown
from evaluator.schemas import PredictionReport
from evaluator.validation import validate_evaluation_inputs
from generator.ground_truth import GroundTruthManifest
from services.reconciliation.run_service import RunServiceError


async def evaluate_persisted_run(
    session: AsyncSession,
    run_id: uuid.UUID,
    ground_truth_path: str | Path,
    *,
    actor: str = "SYSTEM",
) -> dict[str, Any]:
    # Serialize with human review so current projection metrics and the baseline
    # evaluation version are committed from one refreshed run revision.
    run = await RunRepository(session).get_for_update(run_id)
    if run is None:
        raise RunServiceError(
            "RUN_NOT_FOUND",
            "The requested reconciliation run was not found.",
            status_code=404,
            details={"run_id": str(run_id)},
        )
    prediction_data = run.config.get("prediction_report")
    if run.status != "COMPLETED" or not prediction_data:
        raise RunServiceError(
            "RUN_NOT_RECONCILED",
            "The run must complete reconciliation before evaluation.",
            status_code=409,
            details={"run_id": str(run_id), "status": run.status},
        )
    truth_path = Path(ground_truth_path)
    if not truth_path.exists():
        raise RunServiceError(
            "GROUND_TRUTH_NOT_FOUND",
            "Evaluator ground truth is unavailable for this environment.",
            status_code=404,
        )

    prediction = PredictionReport.model_validate_json(json.dumps(prediction_data))
    truth = GroundTruthManifest.model_validate_json(truth_path.read_text())
    try:
        validate_evaluation_inputs(prediction, truth)
    except ValueError as exc:
        raise RunServiceError(
            "DATASET_MISMATCH",
            "The persisted prediction is incompatible with the evaluator ground truth.",
            status_code=409,
            details={
                "prediction_dataset_id": prediction.dataset_id,
                "truth_dataset_id": truth.dataset_id,
                "reason": str(exc),
            },
        ) from exc
    aggregate = compute_all_metrics(
        prediction.cases,
        truth.cases,
        duration_seconds=prediction.duration_seconds,
        total_records=prediction.total_source_records,
    )
    evaluation = {
        "run_id": str(run_id),
        "dataset_id": truth.dataset_id,
        "execution_revision": run.execution_revision,
        "evaluated_review_revision": run.review_revision,
        "current_review_revision": run.review_revision,
        "evaluation_scope": "IMMUTABLE_ENGINE_BASELINE",
        "baseline_result_checksum": run.result_checksum,
        "aggregate": aggregate,
        "scenario_breakdown": compute_scenario_breakdown(prediction.cases, truth.cases),
    }
    run.evaluation = evaluation
    run.metrics = {
        **run.metrics,
        **aggregate,
        "precision": aggregate["relationship_precision"],
        "recall": aggregate["relationship_recall"],
    }
    await AuditRepository(session).create(
        reconciliation_run_id=run_id,
        event_type="EVALUATION_COMPLETED",
        stage="evaluation",
        severity="INFO",
        actor=actor,
        details={
            "aggregate": aggregate,
            "dataset_id": truth.dataset_id,
            "execution_revision": run.execution_revision,
            "evaluated_review_revision": run.review_revision,
            "evaluation_scope": "IMMUTABLE_ENGINE_BASELINE",
            "baseline_result_checksum": run.result_checksum,
        },
    )
    await session.flush()
    return evaluation
