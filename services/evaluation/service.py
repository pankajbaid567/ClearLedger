"""Explicit evaluator boundary for API-triggered scoring."""

from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from db.models import ReconciliationRun
from db.repositories import AuditRepository
from evaluator.metrics import compute_all_metrics, compute_scenario_breakdown
from evaluator.schemas import PredictionReport
from generator.ground_truth import GroundTruthManifest
from services.reconciliation.run_service import RunServiceError


async def evaluate_persisted_run(
    session: AsyncSession, run_id: uuid.UUID, ground_truth_path: str | Path
) -> dict[str, Any]:
    run = await session.get(ReconciliationRun, run_id)
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
    if prediction.dataset_id != truth.dataset_id:
        raise RunServiceError(
            "DATASET_MISMATCH",
            "The persisted prediction and evaluator ground truth have different dataset IDs.",
            status_code=409,
            details={
                "prediction_dataset_id": prediction.dataset_id,
                "truth_dataset_id": truth.dataset_id,
            },
        )
    aggregate = compute_all_metrics(
        prediction.cases,
        truth.cases,
        duration_seconds=prediction.duration_seconds,
        total_records=prediction.total_source_records,
    )
    evaluation = {
        "run_id": str(run_id),
        "dataset_id": truth.dataset_id,
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
        actor="SYSTEM",
        details={"aggregate": aggregate, "dataset_id": truth.dataset_id},
    )
    await session.flush()
    return evaluation
