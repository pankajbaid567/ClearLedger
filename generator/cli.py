"""Generator CLI — produces synthetic source CSVs and ground truth.

Usage::

    python -m generator.cli --dataset demo --seed 20260827
    python -m generator.cli --dataset stress --seed 99999 --count 1000
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from datetime import date
from pathlib import Path

from generator.ground_truth import GroundTruthManifest
from generator.policies import holiday_dates, load_holidays, load_policy
from generator.scenarios import generate_all_scenarios

_VERSION = "1.0.0"
_ROOT = Path(__file__).resolve().parent.parent
_DEFAULT_OUTPUT = {
    "demo": _ROOT / "data" / "demo",
    "dev": _ROOT / "data" / "development",
    "stress": _ROOT / "data" / "stress",
}
_GROUND_TRUTH_DIR = _ROOT / "evaluator_private"


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    h.update(path.read_bytes())
    return h.hexdigest()


def _write_csv(path: Path, rows: list[dict]) -> None:
    if not rows:
        path.write_text("")
        return
    fieldnames = list(rows[0].keys())
    with open(path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def _record_to_dict(record) -> dict:
    """Serialize a Pydantic model to a plain dict suitable for CSV."""
    d = record.model_dump()
    # Convert datetimes / dates / enums to strings for CSV
    for k, v in d.items():
        if hasattr(v, "isoformat"):
            d[k] = v.isoformat()
        elif hasattr(v, "value"):
            d[k] = v.value
        elif v is None:
            d[k] = ""
    return d


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="ClearLedger synthetic data generator")
    parser.add_argument(
        "--dataset",
        choices=["demo", "dev", "stress"],
        default="demo",
    )
    parser.add_argument("--seed", type=int, default=20260827)
    parser.add_argument("--output-dir", type=str, default=None)
    parser.add_argument(
        "--count",
        type=int,
        default=None,
        help="Override total case count (for stress testing)",
    )
    args = parser.parse_args(argv)

    output_dir = Path(args.output_dir) if args.output_dir else _DEFAULT_OUTPUT.get(args.dataset)
    if output_dir is None:
        output_dir = _ROOT / "data" / args.dataset
    output_dir.mkdir(parents=True, exist_ok=True)

    policy = load_policy()
    calendar = load_holidays()
    holidays = holiday_dates(calendar)
    base_date = date(2026, 8, 1)

    print(f"Generating dataset '{args.dataset}' with seed={args.seed} ...")

    results = generate_all_scenarios(
        seed=args.seed,
        policy=policy,
        holidays=holidays,
        base_date=base_date,
        count_override=args.count,
        stress_mode=args.dataset == "stress",
    )

    # Aggregate all source records
    all_orders = []
    all_payments = []
    all_settlements = []
    all_components = []
    all_bank_txns = []
    all_truths = []
    scenario_counts: dict[str, int] = {}

    for sr in results:
        rec = sr.records
        truth = sr.truth
        all_orders.extend(rec.orders)
        all_payments.extend(rec.payments)
        all_settlements.extend(rec.settlements)
        all_components.extend(rec.settlement_components)
        all_bank_txns.extend(rec.bank_transactions)
        all_truths.append(truth)
        scenario_counts[truth.scenario_label] = scenario_counts.get(truth.scenario_label, 0) + 1

    # Write CSVs
    csv_files = {
        "orders.csv": [_record_to_dict(r) for r in all_orders],
        "payments.csv": [_record_to_dict(r) for r in all_payments],
        "settlements.csv": [_record_to_dict(r) for r in all_settlements],
        "settlement_components.csv": [_record_to_dict(r) for r in all_components],
        "bank_transactions.csv": [_record_to_dict(r) for r in all_bank_txns],
    }

    for filename, rows in csv_files.items():
        _write_csv(output_dir / filename, rows)

    # Compute file checksums
    file_checksums = {name: _sha256(output_dir / name) for name in csv_files}

    total_records = (
        len(all_orders)
        + len(all_payments)
        + len(all_settlements)
        + len(all_components)
        + len(all_bank_txns)
    )

    # Determine date range from generated data
    all_dates = []
    for o in all_orders:
        all_dates.append(o.order_created_at.date())
    for b in all_bank_txns:
        all_dates.append(b.value_date)
    date_start = min(all_dates) if all_dates else base_date
    date_end = max(all_dates) if all_dates else base_date

    # Write dataset manifest (public, in output_dir)
    manifest_data = {
        "dataset_id": f"{args.dataset}_{args.seed}",
        "seed": args.seed,
        "generator_version": _VERSION,
        "policy_version": policy.version,
        "currency": policy.currency,
        "date_range_start": date_start.isoformat(),
        "date_range_end": date_end.isoformat(),
        "scenario_counts": scenario_counts,
        "total_cases": len(all_truths),
        "total_source_records": total_records,
        "file_checksums": file_checksums,
    }
    manifest_path = output_dir / "dataset_manifest.json"
    manifest_path.write_text(json.dumps(manifest_data, indent=2) + "\n")

    # Write ground truth (PRIVATE — outside data/)
    _GROUND_TRUTH_DIR.mkdir(parents=True, exist_ok=True)
    gt_manifest = GroundTruthManifest(
        dataset_id=f"{args.dataset}_{args.seed}",
        seed=args.seed,
        generator_version=_VERSION,
        policy_version=policy.version,
        currency=policy.currency,
        date_range_start=date_start,
        date_range_end=date_end,
        scenario_counts=scenario_counts,
        total_cases=len(all_truths),
        total_source_records=total_records,
        file_checksums=file_checksums,
        cases=all_truths,
    )
    gt_path = _GROUND_TRUTH_DIR / f"ground_truth_{args.dataset}.json"
    gt_path.write_text(gt_manifest.model_dump_json(indent=2) + "\n")

    # Summary
    print(f"  Cases:          {len(all_truths)}")
    print(f"  Source records: {total_records}")
    print(f"  Scenarios:      {scenario_counts}")
    print(f"  Output:         {output_dir}")
    print(f"  Ground truth:   {gt_path}")
    print(f"  Manifest:       {manifest_path}")
    print("Done.")


if __name__ == "__main__":
    main()
