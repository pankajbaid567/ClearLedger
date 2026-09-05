"""Measure deterministic engine throughput on the checked-in stress recipe."""

from __future__ import annotations

import argparse
import json
import platform
import resource
import time
from pathlib import Path

from scripts.benchmark_common import ROOT, nearest_rank, source_files
from services.normalization.policy import load_policy
from services.reconciliation.orchestrator import run_reconciliation, to_prediction_report


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the ClearLedger stress benchmark")
    parser.add_argument("--data-dir", type=Path, default=ROOT / "data" / "stress")
    parser.add_argument("--output", type=Path, default=ROOT / "out" / "stress_report.json")
    parser.add_argument(
        "--output-md",
        type=Path,
        default=ROOT / "out" / "stress_report.md",
    )
    args = parser.parse_args()

    manifest_path = args.data_dir / "dataset_manifest.json"
    if not manifest_path.exists():
        raise SystemExit("Stress data is missing. Run `make generate-stress` first.")
    manifest = json.loads(manifest_path.read_text())
    if manifest["total_source_records"] < 1_000:
        raise SystemExit("Stress data must contain at least 1,000 source records.")

    policy = load_policy(ROOT / "policies" / "settlement_policy.v1.json")
    started = time.perf_counter()
    result = run_reconciliation(
        source_files(args.data_dir),
        policy,
        "stress-seed-99999",
    )
    processing_seconds = time.perf_counter() - started
    peak_rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    peak_memory_mib = (
        peak_rss / (1024 * 1024) if platform.system() == "Darwin" else peak_rss / 1024
    )

    latencies = [case.case_latency_ms for case in result.cases]
    report = {
        "dataset_id": manifest["dataset_id"],
        "seed": manifest["seed"],
        "scenario_counts": manifest["scenario_counts"],
        "total_source_records": result.total_source_records,
        "total_cases": len(result.cases),
        "processing_time_seconds": round(processing_seconds, 6),
        "records_per_second": round(result.total_source_records / processing_seconds, 2),
        "cases_per_second": round(len(result.cases) / processing_seconds, 2),
        "p50_case_latency_ms": round(nearest_rank(latencies, 0.50), 4),
        "p95_case_latency_ms": round(nearest_rank(latencies, 0.95), 4),
        "peak_process_memory_mib": round(peak_memory_mib, 2),
        "measurement_scope": (
            "ingestion through cash-position calculation; dataset generation excluded"
        ),
        "memory_method": "OS peak resident set size for the benchmark process (approximate)",
        "python_version": platform.python_version(),
        "platform": platform.platform(),
    }

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n")
    prediction_path = args.output.parent / "stress_reconciliation_report.json"
    prediction_path.write_text(to_prediction_report(result).model_dump_json(indent=2) + "\n")
    args.output_md.write_text(
        "\n".join(
            [
                "# ClearLedger Stress Test",
                "",
                "The benchmark uses a deterministic 80% clean / 20% batched distribution. ",
                "Dataset generation is excluded from processing time.",
                "",
                "| Metric | Measured value |",
                "|---|---:|",
                f"| Total source records | {report['total_source_records']} |",
                f"| Economic cases | {report['total_cases']} |",
                f"| Processing time | {report['processing_time_seconds']:.6f} s |",
                f"| Records / second | {report['records_per_second']:.2f} |",
                f"| Cases / second | {report['cases_per_second']:.2f} |",
                f"| P50 case latency | {report['p50_case_latency_ms']:.4f} ms |",
                f"| P95 case latency | {report['p95_case_latency_ms']:.4f} ms |",
                f"| Approx. peak process memory | {report['peak_process_memory_mib']:.2f} MiB |",
                "",
                f"Memory method: {report['memory_method']}.",
                f"Runtime: Python {report['python_version']} on `{report['platform']}`.",
            ]
        )
        + "\n"
    )
    print(json.dumps(report, indent=2))
    print(f"Stress report: {args.output_md}")


if __name__ == "__main__":
    main()
