"""Shared helpers for reproducible submission benchmarks."""

from __future__ import annotations

import math
from pathlib import Path

from generator.ground_truth import GroundTruthCase, GroundTruthManifest

ROOT = Path(__file__).resolve().parents[1]
SOURCE_FILENAMES = {
    "orders": "orders.csv",
    "payments": "payments.csv",
    "settlements": "settlements.csv",
    "settlement_components": "settlement_components.csv",
    "bank_transactions": "bank_transactions.csv",
}


def source_files(data_dir: Path) -> dict[str, str]:
    return {
        source_type: str(data_dir / filename)
        for source_type, filename in SOURCE_FILENAMES.items()
    }


def load_truth(dataset: str) -> GroundTruthManifest:
    path = ROOT / "evaluator_private" / f"ground_truth_{dataset}.json"
    return GroundTruthManifest.model_validate_json(path.read_text())


def nearest_rank(values: list[float], percentile: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = max(0, math.ceil(percentile * len(ordered)) - 1)
    return ordered[index]


def correctly_classified(predicted: list, truth: list[GroundTruthCase]) -> int:
    expected = {case.case_id: case.expected_case_state for case in truth}
    return sum(
        1
        for case in predicted
        if expected.get(case.case_id) == case.predicted_case_state
    )


def format_inr(paise: int) -> str:
    sign = "-" if paise < 0 else ""
    absolute = abs(paise)
    rupees, remainder = divmod(absolute, 100)
    digits = str(rupees)
    if len(digits) > 3:
        tail = digits[-3:]
        head = digits[:-3]
        groups: list[str] = []
        while head:
            groups.append(head[-2:])
            head = head[:-2]
        digits = ",".join(reversed(groups)) + "," + tail
    return f"{sign}₹{digits}.{remainder:02d}"
