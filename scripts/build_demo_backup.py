"""Create deterministic JSON fixtures for an offline demo fallback."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from evaluator.metrics import compute_all_metrics, compute_scenario_breakdown
from scripts.benchmark_common import ROOT, load_truth, source_files
from services.normalization.policy import load_policy
from services.reconciliation.orchestrator import run_reconciliation, to_prediction_report


def _write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, indent=2, default=str) + "\n")


def main() -> None:
    output = ROOT / "out" / "demo_backup" / "api"
    output.mkdir(parents=True, exist_ok=True)
    policy = load_policy(ROOT / "policies" / "settlement_policy.v1.json")
    truth = load_truth("demo")
    result = run_reconciliation(
        source_files(ROOT / "data" / "demo"),
        policy,
        "demo-backup-seed-20260827",
    )
    prediction = to_prediction_report(result)
    metrics = compute_all_metrics(
        prediction.cases,
        truth.cases,
        duration_seconds=result.duration_seconds,
        total_records=result.total_source_records,
    )
    fixtures: dict[str, Any] = {
        "run.json": {
            "id": result.run_id,
            "status": "COMPLETED",
            "dataset_id": result.dataset_id,
            "policy_id": policy.policy_id,
            "policy_version": policy.version,
            "rule_set_version": "1.0.0",
            "total_source_rows": result.total_source_records,
            "total_cases": len(result.cases),
        },
        "metrics.json": {"run_id": result.run_id, "status": "COMPLETED", "metrics": metrics},
        "cases.json": [case.model_dump(mode="json") for case in result.cases],
        "cash.json": result.cash_position.model_dump(mode="json"),
        "evidence.json": [edge.model_dump(mode="json") for edge in result.evidence_edges],
        "exceptions.json": [item.model_dump(mode="json") for item in result.exceptions],
        "audit.json": {
            "run_id": result.run_id,
            "events": [timing.model_dump(mode="json") for timing in result.stage_timings],
        },
        "evaluation.json": {
            "dataset_id": result.dataset_id,
            "run_id": result.run_id,
            "aggregate": metrics,
            "scenario_breakdown": compute_scenario_breakdown(prediction.cases, truth.cases),
        },
    }
    for filename, payload in fixtures.items():
        _write_json(output / filename, payload)

    checksums = {
        path.name: hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(output.glob("*.json"))
    }
    screenshot_dir = output.parent / "screenshots"
    screenshot_checksums = {
        path.name: hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(screenshot_dir.glob("*.png"))
    }
    _write_json(
        output.parent / "manifest.json",
        {
            "dataset_id": result.dataset_id,
            "seed": 20260827,
            "mode": "deterministic_full",
            "files": checksums,
            "screenshots": screenshot_checksums,
            "fallback": (
                "Serve these fixtures or use AI-off mode if a live provider is unavailable."
            ),
        },
    )
    print(f"Demo backup: {output.parent}")


if __name__ == "__main__":
    main()
