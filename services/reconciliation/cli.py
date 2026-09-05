"""CLI for producing deterministic reconciliation predictions."""

from __future__ import annotations

import argparse
from pathlib import Path

from services.normalization.policy import load_policy
from services.reconciliation.orchestrator import run_reconciliation, to_prediction_report

_ROOT = Path(__file__).resolve().parents[2]
_DEFAULT_FILES = {
    "orders": "orders.csv",
    "payments": "payments.csv",
    "settlements": "settlements.csv",
    "settlement_components": "settlement_components.csv",
    "bank_transactions": "bank_transactions.csv",
}


def _source_files(data_dir: Path) -> dict[str, str]:
    return {
        source_type: str(data_dir / filename)
        for source_type, filename in _DEFAULT_FILES.items()
        if (data_dir / filename).exists()
    }


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Run ClearLedger deterministic reconciliation")
    parser.add_argument(
        "--data-dir",
        type=str,
        default=str(_ROOT / "data" / "demo"),
    )
    parser.add_argument(
        "--policy",
        type=str,
        default=str(_ROOT / "policies" / "settlement_policy.v1.json"),
    )
    parser.add_argument("--run-id", type=str, default="demo-run-phase-2")
    parser.add_argument(
        "--mode",
        choices=["exact_id_only", "deterministic_full"],
        default="deterministic_full",
    )
    parser.add_argument(
        "--output",
        type=str,
        default=str(_ROOT / "out" / "reconciliation_report.json"),
    )
    args = parser.parse_args(argv)

    data_dir = Path(args.data_dir)
    output = Path(args.output)
    policy = load_policy(args.policy)
    result = run_reconciliation(
        _source_files(data_dir),
        policy,
        args.run_id,
        matching_mode=args.mode,
    )
    report = to_prediction_report(result)

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(report.model_dump_json(indent=2) + "\n")
    print(f"Reconciliation run: {result.run_id}")
    print(f"Cases: {len(result.cases)}")
    print(f"Evidence edges: {len(result.evidence_edges)}")
    print(f"Exceptions: {len(result.exceptions)}")
    print(f"Mode: {args.mode}")
    print(f"Output: {output}")


if __name__ == "__main__":
    main()
