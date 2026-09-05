"""Cross-file validation for an evaluation run.

These checks prevent a prediction report from selecting a subset of the oracle
or claiming throughput for a different dataset.
"""

from __future__ import annotations

from evaluator.schemas import PredictionReport
from generator.ground_truth import GroundTruthManifest


def validate_evaluation_inputs(
    prediction: PredictionReport,
    truth: GroundTruthManifest,
) -> None:
    errors: list[str] = []
    if prediction.dataset_id != truth.dataset_id:
        errors.append(
            f"dataset ID mismatch: prediction={prediction.dataset_id!r}, truth={truth.dataset_id!r}"
        )
    if prediction.total_source_records != truth.total_source_records:
        errors.append(
            "source-record total mismatch: "
            f"prediction={prediction.total_source_records}, "
            f"truth={truth.total_source_records}"
        )
    if truth.total_cases != len(truth.cases):
        errors.append(
            f"ground-truth case total mismatch: declared={truth.total_cases}, "
            f"actual={len(truth.cases)}"
        )
    truth_ids = [case.case_id for case in truth.cases]
    if len(truth_ids) != len(set(truth_ids)):
        errors.append("ground truth contains duplicate case IDs")
    if errors:
        raise ValueError("; ".join(errors))
