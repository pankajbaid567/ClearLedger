"""Evaluator CLI — scores predictions against hidden ground truth.

Usage::

    python -m evaluator.cli \\
        --predictions out/reconciliation_report.json \\
        --ground-truth evaluator_private/ground_truth_demo.json \\
        --output out/evaluation.json \\
        --output-md out/evaluation.md
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from evaluator.metrics import compute_all_metrics, compute_scenario_breakdown
from evaluator.schemas import PredictionReport
from generator.ground_truth import GroundTruthManifest

_ROOT = Path(__file__).resolve().parent.parent


def _format_markdown(metrics: dict, breakdown: dict[str, dict]) -> str:
    lines = [
        "# ClearLedger — Evaluation Results",
        "",
        "## Aggregate Metrics",
        "",
        "| Metric | Value |",
        "|---|---|",
    ]
    for k, v in metrics.items():
        label = k.replace("_", " ").title()
        if isinstance(v, float):
            lines.append(f"| {label} | {v:.4f} |")
        elif v is None:
            lines.append(f"| {label} | N/A |")
        else:
            lines.append(f"| {label} | {v} |")

    lines.extend(["", "## Scenario Breakdown", ""])
    for scenario, m in breakdown.items():
        lines.append(f"### {scenario}")
        lines.append("")
        lines.append("| Metric | Value |")
        lines.append("|---|---|")
        for k, v in m.items():
            label = k.replace("_", " ").title()
            if isinstance(v, float):
                lines.append(f"| {label} | {v:.4f} |")
            elif v is None:
                lines.append(f"| {label} | N/A |")
            else:
                lines.append(f"| {label} | {v} |")
        lines.append("")

    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="ClearLedger evaluator")
    parser.add_argument(
        "--predictions",
        type=str,
        default=str(_ROOT / "out" / "reconciliation_report.json"),
    )
    parser.add_argument(
        "--ground-truth",
        type=str,
        default=str(_ROOT / "evaluator_private" / "ground_truth_demo.json"),
    )
    parser.add_argument(
        "--manifest",
        type=str,
        default=None,
        help="Optional dataset manifest for cross-check",
    )
    parser.add_argument(
        "--output",
        type=str,
        default=str(_ROOT / "out" / "evaluation.json"),
    )
    parser.add_argument(
        "--output-md",
        type=str,
        default=str(_ROOT / "out" / "evaluation.md"),
    )
    parser.add_argument(
        "--dataset",
        type=str,
        default="demo",
        help="Used only when --ground-truth is not specified",
    )
    args = parser.parse_args(argv)

    # Resolve ground truth path based on dataset flag
    gt_path = Path(args.ground_truth)
    if not gt_path.exists() and args.dataset:
        alt = _ROOT / "evaluator_private" / f"ground_truth_{args.dataset}.json"
        if alt.exists():
            gt_path = alt

    pred_path = Path(args.predictions)
    out_path = Path(args.output)
    out_md_path = Path(args.output_md)

    # Load ground truth
    if not gt_path.exists():
        print(f"ERROR: Ground truth not found at {gt_path}", file=sys.stderr)
        print("  Run: python -m generator.cli --dataset demo", file=sys.stderr)
        sys.exit(1)

    gt_manifest = GroundTruthManifest.model_validate_json(gt_path.read_text())
    truth = gt_manifest.cases

    # Load predictions
    if not pred_path.exists():
        print(f"ERROR: Predictions not found at {pred_path}", file=sys.stderr)
        print("  The reconciliation engine must produce this file first.", file=sys.stderr)
        sys.exit(1)

    pred_report = PredictionReport.model_validate_json(pred_path.read_text())
    predicted = pred_report.cases

    # Compute metrics
    metrics = compute_all_metrics(
        predicted,
        truth,
        duration_seconds=pred_report.duration_seconds,
        total_records=pred_report.total_source_records,
    )
    breakdown = compute_scenario_breakdown(predicted, truth)

    # Write outputs
    out_path.parent.mkdir(parents=True, exist_ok=True)
    result = {
        "dataset_id": gt_manifest.dataset_id,
        "run_id": pred_report.run_id,
        "aggregate": metrics,
        "scenario_breakdown": breakdown,
    }
    out_path.write_text(json.dumps(result, indent=2) + "\n")
    out_md_path.write_text(_format_markdown(metrics, breakdown))

    # Print summary
    print("=" * 60)
    print("ClearLedger Evaluation Results")
    print("=" * 60)
    for k, v in metrics.items():
        label = k.replace("_", " ").title().ljust(35)
        if isinstance(v, float):
            print(f"  {label} {v:.4f}")
        elif v is None:
            print(f"  {label} N/A")
        else:
            print(f"  {label} {v}")
    print(f"\n  Output JSON: {out_path}")
    print(f"  Output MD:   {out_md_path}")

    # Safety gate
    fp = metrics["false_positive_count"]
    if fp > 0:
        print(f"\n⚠️  SAFETY FAILURE: {fp} false positive(s) detected!", file=sys.stderr)
        sys.exit(2)

    print("\n✅ All safety checks passed.")


if __name__ == "__main__":
    main()
