"""Compare exact-ID, full deterministic, and optional AI-assisted modes."""

from __future__ import annotations

import asyncio
import json
import time
from typing import Any

from apps.api.app.config import Settings
from evaluator.metrics import compute_all_metrics
from scripts.benchmark_common import ROOT, correctly_classified, load_truth, source_files
from services.ai_analyst.client import OpenAICompatibleClient
from services.ai_analyst.evidence_packet import build_evidence_packet
from services.normalization.policy import load_policy
from services.reconciliation.orchestrator import (
    run_reconciliation,
    select_ai_analysis_cases,
    to_prediction_report,
)


async def _run_optional_ai(result: Any, policy: Any) -> dict[str, Any]:
    config = Settings().ai_client_config()
    eligible = select_ai_analysis_cases(result.cases)
    if not config.enabled:
        return {
            "enabled": False,
            "status": "disabled",
            "eligible_cases": len(eligible),
            "assisted_cases": 0,
            "calls": 0,
            "estimated_cost": 0,  # Micro-dollars
        }

    client = OpenAICompatibleClient(config)
    results = []
    for case in eligible:
        packet = build_evidence_packet(case, policy, max_chars=config.max_packet_chars)
        results.append(await client.analyze_case(case.case_id, packet))
    return {
        "enabled": True,
        "status": "completed",
        "eligible_cases": len(eligible),
        "assisted_cases": sum(item.response is not None for item in results),
        "calls": sum(item.attempts for item in results),
        "estimated_cost": sum(item.estimated_cost for item in results),  # Already in micro-dollars
    }


def _measure_mode(mode: str, policy: Any, truth: Any) -> tuple[dict[str, Any], Any]:
    matching_mode = "exact_id_only" if mode == "exact_id_only" else "deterministic_full"
    started = time.perf_counter()
    result = run_reconciliation(
        source_files(ROOT / "data" / "demo"),
        policy,
        f"ablation-{mode}",
        matching_mode=matching_mode,
    )
    report = to_prediction_report(result)
    runtime = time.perf_counter() - started
    metrics = compute_all_metrics(
        report.cases,
        truth.cases,
        duration_seconds=runtime,
        total_records=report.total_source_records,
    )
    row = {
        "mode": mode,
        "description": {
            "exact_id_only": "Rules 1-3 only",
            "deterministic_full": "All 9 deterministic rules; AI off",
            "deterministic_plus_ai": "Full deterministic engine plus bounded AI analyst",
        }[mode],
        "precision": metrics["relationship_precision"],
        "recall": metrics["relationship_recall"],
        "f1": metrics["relationship_f1"],
        "stp_rate": metrics["stp_rate"],
        "exception_count": len(result.exceptions),
        "cases_correctly_classified": correctly_classified(report.cases, truth.cases),
        "total_cases": len(truth.cases),
        "runtime_seconds": round(runtime, 6),
        "ai_calls": None,
        "ai_cost_usd": None,
        "ai_assisted_cases": None,
        "ai_status": "not_applicable",
    }
    return row, result


def main() -> None:
    output_json = ROOT / "out" / "ablation_report.json"
    output_md = ROOT / "out" / "ablation_report.md"
    policy = load_policy(ROOT / "policies" / "settlement_policy.v1.json")
    truth = load_truth("demo")

    exact, _ = _measure_mode("exact_id_only", policy, truth)
    deterministic, _ = _measure_mode("deterministic_full", policy, truth)

    ai_row, ai_result = _measure_mode("deterministic_plus_ai", policy, truth)
    ai_started = time.perf_counter()
    ai_metrics = asyncio.run(_run_optional_ai(ai_result, policy))
    ai_row["runtime_seconds"] = round(
        ai_row["runtime_seconds"] + (time.perf_counter() - ai_started),
        6,
    )
    ai_row["ai_calls"] = ai_metrics["calls"]
    ai_row["ai_cost_usd"] = ai_metrics["estimated_cost"] / 1_000_000.0  # Convert micro-dollars to USD
    ai_row["ai_assisted_cases"] = ai_metrics["assisted_cases"]
    ai_row["ai_status"] = ai_metrics["status"]

    rows = [exact, deterministic, ai_row]
    payload = {
        "dataset_id": truth.dataset_id,
        "authoritative_boundary": (
            "AI may rank or explain precomputed candidates but cannot change verified state."
        ),
        "modes": rows,
    }
    output_json.parent.mkdir(parents=True, exist_ok=True)
    output_json.write_text(json.dumps(payload, indent=2) + "\n")

    lines = [
        "# ClearLedger Ablation Study",
        "",
        f"Dataset: `{truth.dataset_id}` ({len(truth.cases)} economic cases).",
        "",
        (
            "| Mode | Precision | Recall | F1 | STP | Exceptions | Correct cases | "
            "Runtime (s) | AI calls | AI cost |"
        ),
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for row in rows:
        ai_calls = "—" if row["ai_calls"] is None else str(row["ai_calls"])
        ai_cost = "—" if row["ai_cost_usd"] is None else f"${row['ai_cost_usd']:.6f}"
        lines.append(
            f"| `{row['mode']}` | {row['precision']:.4f} | {row['recall']:.4f} | "
            f"{row['f1']:.4f} | {row['stp_rate']:.4f} | {row['exception_count']} | "
            f"{row['cases_correctly_classified']}/{row['total_cases']} | "
            f"{row['runtime_seconds']:.6f} | {ai_calls} | {ai_cost} |"
        )
    lines.extend(
        [
            "",
            "## Interpretation",
            "",
            "The authoritative precision, recall, case state, and STP metrics come from "
            "deterministic evidence and invariants. AI is intentionally non-authoritative: "
            "its measurable value is "
            "bounded exception triage, not an artificial increase in verified matches.",
            "",
            f"AI status for this run: `{ai_row['ai_status']}`; assisted cases: "
            f"{ai_row['ai_assisted_cases']}; provider calls: {ai_row['ai_calls']}.",
        ]
    )
    output_md.write_text("\n".join(lines) + "\n")
    print(f"Ablation report: {output_md}")


if __name__ == "__main__":
    main()
