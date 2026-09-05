import copy
import csv
import json
import tempfile
from datetime import date
from pathlib import Path

from evaluator.metrics import compute_all_metrics
from generator.cli import _record_to_dict
from generator.ground_truth import GroundTruthManifest
from generator.policies import holiday_dates, load_holidays
from generator.policies import load_policy as generator_policy
from generator.scenarios import (
    generate_batched_settlement,
    generate_clean_lifecycle,
    generate_refund,
    generate_timing_delay,
)
from services.normalization.policy import load_policy
from services.reconciliation.orchestrator import run_reconciliation, to_prediction_report

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(tempfile.mkdtemp(prefix="clearledger-adversarial-"))
OUT.mkdir(exist_ok=True)
p = load_policy(ROOT / "policies/settlement_policy.v1.json")
gp = generator_policy(ROOT / "policies/settlement_policy.v1.json")
holidays = holiday_dates(load_holidays(ROOT / "policies/holidays.v1.json"))


def make(fn, idx):
    return fn(
        seed=20260827, case_index=idx, policy=gp, holidays=holidays, base_date=date(2026, 8, 1)
    )


def rows(sr):
    return {
        key: [_record_to_dict(r) for r in getattr(sr.records, key)]
        for key in sr.records.model_fields
    }


def run(name, record_rows):
    folder = OUT / name
    folder.mkdir(exist_ok=True)
    files = {}
    for source, records in record_rows.items():
        if not records:
            continue
        file = folder / f"{source}.csv"
        with file.open("w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=records[0].keys())
            writer.writeheader()
            writer.writerows(records)
        files[source] = str(file)
    result = run_reconciliation(files, p, name)
    return result


def desc(r):
    return {
        "states": [
            (
                c.case_id,
                c.case_state.value,
                c.exception_code.value if c.exception_code else None,
                c.residual_paise,
                c.checks_failed,
            )
            for c in r.cases
        ],
        "edge_count": len(r.evidence_edges),
        "cash": r.cash_position.model_dump(mode="json"),
    }


results = {}
timing = rows(make(generate_timing_delay, 31))
results["timing_original"] = desc(run("timing_original", timing))
timing_opaque = copy.deepcopy(timing)
for rs in timing_opaque.values():
    for row in rs:
        for key, value in row.items():
            if isinstance(value, str):
                row[key] = value.replace("SET_T0031", "OPAQUE_SETTLEMENT_31")
results["timing_opaque"] = desc(run("timing_opaque", timing_opaque))

batch = rows(make(generate_batched_settlement, 21))
results["batch_original"] = desc(run("batch_original", batch))
batch_bad = copy.deepcopy(batch)
batch_bad["orders"][0]["order_amount_paise"] += 1000
results["batch_order_amount_plus_1000"] = desc(run("batch_order_amount_plus_1000", batch_bad))
batch_merchant = copy.deepcopy(batch)
batch_merchant["orders"][0]["merchant_id"] = "ANOTHER_MERCHANT"
results["batch_order_merchant_conflict"] = desc(
    run("batch_order_merchant_conflict", batch_merchant)
)

clean = rows(make(generate_clean_lifecycle, 1))
results["clean_original"] = desc(run("clean_original", clean))
failed = copy.deepcopy(clean)
failed["settlements"][0]["settlement_status"] = "failed"
results["failed_settlement"] = desc(run("failed_settlement", failed))
credit_bad = copy.deepcopy(clean)
credit_bad["settlement_components"][0]["amount_paise"] += 1000
credit_bad["settlements"][0]["net_amount_paise"] += 1000
credit_bad["bank_transactions"][0]["amount_paise"] += 1000
results["component_payment_plus_1000"] = desc(run("component_payment_plus_1000", credit_bad))
conflict = copy.deepcopy(clean)
conflict["bank_transactions"][0]["utr"] = "DIFFERENT_VALID_UTR"
conflict["bank_transactions"][0]["narration"] = "NEFT external payment"
results["conflicting_bank_utr"] = desc(run("conflicting_bank_utr", conflict))

refund = rows(make(generate_refund, 42))
refund_run = run("refund", refund)
results["refund"] = desc(refund_run)
results["refund"]["bank_statement_net"] = sum(
    row["amount_paise"] for row in refund["bank_transactions"]
)
results["refund"]["refund_components"] = sum(
    row["amount_paise"]
    for row in refund["settlement_components"]
    if row["component_type"] == "REFUND"
)

source = {key: str(ROOT / "data/demo" / f"{key}.csv") for key in clean}
real = run_reconciliation(source, p, "metrics_review")
report = to_prediction_report(real)
truth = GroundTruthManifest.model_validate_json(
    (ROOT / "evaluator_private/ground_truth_demo.json").read_text()
)
correct = compute_all_metrics(report.cases, truth.cases)
tampered = [
    c.model_copy(
        update={
            "predicted_gross_amount_paise": -999999999,
            "predicted_net_amount_paise": 999999999,
            "predicted_relationships": [
                e.model_copy(update={"allocated_amount_paise": 0})
                for e in c.predicted_relationships
            ],
        }
    )
    for c in report.cases
]
results["metric_original"] = correct
results["metric_zero_allocations_and_corrupt_money"] = compute_all_metrics(tampered, truth.cases)
results["metric_duplicated_predictions"] = compute_all_metrics(
    report.cases + report.cases, truth.cases
)
extra = next(c for c in report.cases if c.predicted_case_state.value == "RECONCILED").model_copy(
    update={"case_id": "GHOST_RECONCILED"}
)
results["metric_unknown_reconciled_case"] = compute_all_metrics(report.cases + [extra], truth.cases)
results["metric_empty_predictions"] = compute_all_metrics([], truth.cases)

(OUT / "results.json").write_text(json.dumps(results, indent=2))
for key, value in results.items():
    if key.startswith("metric"):
        print(
            key,
            {
                m: value[m]
                for m in (
                    "relationship_precision",
                    "relationship_recall",
                    "case_state_accuracy",
                    "monetary_reconciliation_rate",
                    "false_positive_count",
                    "hidden_row_count",
                )
            },
        )
    else:
        print(
            key,
            "states=",
            value["states"],
            "edges=",
            value["edge_count"],
            "bank=",
            value["cash"]["bank_confirmed_paise"],
            "in_transit=",
            value["cash"]["settlement_confirmed_in_transit_paise"],
            "safe_cash=",
            value["cash"]["safe_cash_paise"],
        )

print("Temporary output:", OUT)
