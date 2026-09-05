"""Fail the submission build when a published claim is not reproducible."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

from generator.cli import main as generate_dataset
from scripts.benchmark_common import ROOT, source_files
from services.normalization.policy import load_policy
from services.reconciliation.orchestrator import run_reconciliation, to_prediction_report


def _require(condition: bool, claim: str, value: object) -> None:
    if not condition:
        raise SystemExit(f"CLAIM FAILED: {claim} (actual: {value})")
    print(f"PASS: {claim} ({value})")


def _verify_reproducibility() -> None:
    policy = load_policy(ROOT / "policies" / "settlement_policy.v1.json")
    with tempfile.TemporaryDirectory(prefix="clearledger-repro-a-") as first_dir_name:
        with tempfile.TemporaryDirectory(prefix="clearledger-repro-b-") as second_dir_name:
            first_dir = Path(first_dir_name)
            second_dir = Path(second_dir_name)
            for output_dir in (first_dir, second_dir):
                generate_dataset(
                    [
                        "--dataset",
                        "demo",
                        "--seed",
                        "20260827",
                        "--output-dir",
                        str(output_dir),
                    ]
                )
            first_manifest = json.loads((first_dir / "dataset_manifest.json").read_text())
            second_manifest = json.loads((second_dir / "dataset_manifest.json").read_text())
            _require(
                first_manifest["file_checksums"] == second_manifest["file_checksums"],
                "same seed produces identical source checksums",
                first_manifest["file_checksums"],
            )
            first_result = to_prediction_report(
                run_reconciliation(source_files(first_dir), policy, "repro-a")
            )
            second_result = to_prediction_report(
                run_reconciliation(source_files(second_dir), policy, "repro-b")
            )
            _require(
                first_result.cases == second_result.cases,
                "same source checksums produce identical case results",
                len(first_result.cases),
            )


def main() -> None:
    evaluation = json.loads((ROOT / "out" / "evaluation.json").read_text())
    prediction = json.loads((ROOT / "out" / "reconciliation_report.json").read_text())
    manifest = json.loads((ROOT / "data" / "demo" / "dataset_manifest.json").read_text())
    stress = json.loads((ROOT / "out" / "stress_report.json").read_text())
    aggregate = evaluation["aggregate"]

    _require(
        aggregate["relationship_precision"] >= 1.0,
        "verified precision >= 1.0",
        aggregate["relationship_precision"],
    )
    _require(
        aggregate["relationship_recall"] >= 0.95,
        "relationship recall >= 0.95",
        aggregate["relationship_recall"],
    )
    _require(
        aggregate["false_positive_count"] == 0,
        "false positive count is zero",
        aggregate["false_positive_count"],
    )
    _require(
        aggregate["unexplained_residual_paise"] == 0,
        "reconciled cases have zero unexplained residual",
        aggregate["unexplained_residual_paise"],
    )
    _require(
        prediction["duration_seconds"] < 10,
        "demo batch completes in under 10 seconds",
        prediction["duration_seconds"],
    )
    _require(
        manifest["total_cases"] >= 75,
        "evaluation contains at least 75 cases",
        manifest["total_cases"],
    )
    _require(
        manifest["total_source_records"] >= 150,
        "evaluation contains at least 150 source records",
        manifest["total_source_records"],
    )
    _require(
        stress["total_source_records"] >= 1_000,
        "stress set contains at least 1,000 source records",
        stress["total_source_records"],
    )

    predicted_cases = prediction["cases"]
    bad_reconciled = [
        case["case_id"]
        for case in predicted_cases
        if case["predicted_case_state"] == "RECONCILED"
        and case["predicted_residual_paise"] != 0
    ]
    _require(not bad_reconciled, "no reconciled case has a nonzero residual", bad_reconciled)
    _verify_reproducibility()
    print("All ClearLedger claims verified.")


if __name__ == "__main__":
    main()
