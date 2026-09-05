"""Offline control-package verification using only the Python standard library.

Checks exported integrity, row coverage and projection arithmetic. It does not
establish bank authenticity, tax eligibility or replace an independent oracle.
"""

from __future__ import annotations

import argparse
import base64
import csv
import hashlib
import io
import json
from pathlib import Path
from typing import Any


def canonical_sha256(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        ).encode()
    ).hexdigest()


def verify_package(package: dict[str, Any], expected_sha256: str | None = None) -> list[str]:
    """Return explicit failed checks. Empty means these documented checks pass."""
    errors: list[str] = []
    payload = package.get("payload")
    if not isinstance(payload, dict) or package.get("format") != "clearledger.control.v1":
        return ["Unsupported or missing package format/payload"]
    digest = canonical_sha256(payload)
    if digest != package.get("sha256"):
        errors.append("Package digest does not match contents")
    if expected_sha256 is not None and digest != expected_sha256:
        errors.append("Package differs from the externally recorded digest")
    if canonical_sha256(payload.get("policy")) != payload.get("policy_sha256"):
        errors.append("Policy/calendar snapshot digest mismatch")
    source_types: set[str] = set()
    decoded_checksums: dict[str, str] = {}
    total_rows = 0
    for source in payload.get("sources", []):
        kind = source["source_type"]
        if kind in source_types:
            errors.append(f"Duplicate source type: {kind}")
        source_types.add(kind)
        try:
            content = base64.b64decode(source["content_base64"], validate=True)
            decoded_sha256 = hashlib.sha256(content).hexdigest()
            decoded_checksums[f"{kind}.csv"] = decoded_sha256
            if decoded_sha256 != source["sha256"]:
                errors.append(f"Source checksum mismatch: {kind}")
            rows = list(csv.DictReader(io.StringIO(content.decode("utf-8-sig"))))
        except (ValueError, UnicodeError, KeyError, csv.Error):
            errors.append(f"Invalid encoded source: {kind}")
            continue
        raw = source.get("rows", [])
        if len(rows) != source["row_count"] or len(raw) != len(rows):
            errors.append(f"Source row count/coverage mismatch: {kind}")
        if len({r["row_number"] for r in raw}) != len(raw):
            errors.append(f"Duplicate source row disposition: {kind}")
        if any(r.get("quality") not in {"VALID", "INVALID", "PARTIAL"} for r in raw):
            errors.append(f"Missing source row disposition: {kind}")
        for index, row in enumerate(raw):
            if index < len(rows) and row["raw_values"] != rows[index]:
                errors.append(f"Raw row differs from source bytes: {kind}:{row['row_number']}")
        total_rows += len(rows)
    if source_types != {
        "orders",
        "payments",
        "settlements",
        "settlement_components",
        "bank_transactions",
    }:
        errors.append("Required source set is incomplete")
    run = payload.get("run", {})
    manifest = payload.get("input_manifest", {})
    manifest_checksums = manifest.get("file_checksums") if isinstance(manifest, dict) else None
    if manifest_checksums != decoded_checksums:
        errors.append("Input manifest checksums differ from decoded sources")
    dataset_checksum = canonical_sha256(
        {name.removesuffix(".csv"): value for name, value in decoded_checksums.items()}
    )
    if dataset_checksum != run.get("dataset_checksum"):
        errors.append("Run dataset checksum differs from decoded sources")
    dataset_id = manifest.get("dataset_id") if isinstance(manifest, dict) else None
    if isinstance(dataset_id, str) and dataset_id.startswith("upload_"):
        if dataset_id != f"upload_{dataset_checksum[:12]}":
            errors.append("Uploaded dataset identifier differs from source checksum")
    baseline = payload.get("baseline_result")
    if not isinstance(baseline, dict):
        errors.append("Immutable baseline result payload is unavailable")
    else:
        if canonical_sha256(baseline) != run.get("baseline_result_checksum"):
            errors.append("Baseline result checksum mismatch")
        if baseline.get("dataset_id") != payload.get("input_manifest", {}).get("dataset_id"):
            errors.append("Baseline result dataset differs from input manifest")
        baseline_cases = baseline.get("cases")
        if not isinstance(baseline_cases, list) or len(baseline_cases) != run.get("total_cases"):
            errors.append("Baseline result case count mismatch")
    if total_rows != run.get("total_source_rows"):
        errors.append("Run row total differs from source coverage")
    cases = payload.get("cases", [])
    if len(cases) != run.get("total_cases") or len({c["case_id"] for c in cases}) != len(cases):
        errors.append("Case count/identity mismatch")
    buckets: dict[str, int] = {}
    bucket_ids: dict[str, list[str]] = {}
    for case in cases:
        cid = case["case_id"]
        if case.get("run_id") != run.get("id"):
            errors.append(f"Case belongs to another run: {cid}")
        bucket = case["cash_bucket"]
        net, residual, gross = (
            case[k] for k in ("net_amount_paise", "residual_paise", "gross_amount_paise")
        )
        if not all(isinstance(x, int) and not isinstance(x, bool) for x in (net, residual, gross)):
            errors.append(f"Non-integer money: {cid}")
            continue
        contribution = (
            net
            if bucket
            in {"BANK_CONFIRMED", "SETTLEMENT_CONFIRMED_IN_TRANSIT", "EXPECTED_SETTLEMENT"}
            else abs(residual)
            if residual
            else abs(net)
            if net
            else abs(gross)
        )
        if case.get("cash_bucket_contribution_paise") != contribution:
            errors.append(f"Incorrect cash contribution: {cid}")
        buckets[bucket] = buckets.get(bucket, 0) + contribution
        bucket_ids.setdefault(bucket, []).append(cid)
        if case["case_state"] == "RECONCILED":
            if residual != 0:
                errors.append(f"Reconciled case has residual: {cid}")
            checks = case.get("invariants", [])
            if not checks or not all(check.get("passed") is True for check in checks):
                errors.append(f"Reconciled case lacks passing verification: {cid}")
            residual_checks = [check for check in checks if check.get("id") == "INV-005"]
            if len(residual_checks) != 1 or (
                residual_checks[0].get("expected") != residual_checks[0].get("actual")
            ):
                errors.append(f"Reconciled case lacks recomputable zero-residual evidence: {cid}")
    cash = payload.get("cash", {})
    for bucket, snapshot in cash.get("buckets", {}).items():
        if snapshot["amount_paise"] != buckets.get(bucket, 0):
            errors.append(f"Cash bucket sum mismatch: {bucket}")
        if sorted(snapshot["case_ids"]) != sorted(bucket_ids.get(bucket, [])):
            errors.append(f"Cash bucket membership mismatch: {bucket}")
    if set(buckets) - set(cash.get("buckets", {})):
        errors.append("Cash snapshot omits a contributing bucket")
    if cash.get("safe_cash_paise") != buckets.get("BANK_CONFIRMED", 0):
        errors.append("Confirmed net movement includes unconfirmed or duplicate adjustments")
    for event in payload.get("audit", []) + payload.get("decisions", []):
        if event.get("run_id") != run.get("id"):
            errors.append("Audit/decision belongs to another run")
    return errors


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("package", type=Path)
    parser.add_argument("--expected-sha256", help="Digest recorded separately at export time")
    args = parser.parse_args()
    try:
        package = json.loads(args.package.read_text())
        failures = verify_package(package, args.expected_sha256)
    except (ValueError, KeyError, TypeError, OSError) as exc:
        failures = [f"Invalid control package: {exc}"]
    print(
        json.dumps(
            {
                "verified": not failures,
                "scope": "integrity_row_coverage_cash_projection",
                "failures": failures,
            },
            indent=2,
        )
    )
    raise SystemExit(1 if failures else 0)


if __name__ == "__main__":
    main()
