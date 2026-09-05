import base64
import copy
import hashlib

from services.reporting.verify import canonical_sha256, verify_package


def package_fixture() -> dict:
    content = b"id,amount\nentity,100\n"
    sources = [
        {
            "source_type": kind,
            "content_base64": base64.b64encode(content).decode(),
            "sha256": hashlib.sha256(content).hexdigest(),
            "row_count": 1,
            "rows": [
                {
                    "row_number": 2,
                    "quality": "VALID",
                    "raw_values": {"id": "entity", "amount": "100"},
                }
            ],
        }
        for kind in (
            "orders",
            "payments",
            "settlements",
            "settlement_components",
            "bank_transactions",
        )
    ]
    baseline = {
        "dataset_id": "fixture",
        "cases": [{"case_id": "case"}],
        "cash_position": {"bank_confirmed_paise": 100},
        "policy_version_id": "policy",
        "rule_set_version": "rule",
    }
    file_checksums = {f"{source['source_type']}.csv": source["sha256"] for source in sources}
    dataset_checksum = canonical_sha256(
        {source["source_type"]: source["sha256"] for source in sources}
    )
    payload = {
        "policy": {"version": "1", "holidays": ["2026-08-15"]},
        "input_manifest": {"dataset_id": "fixture", "file_checksums": file_checksums},
        "baseline_result": baseline,
        "sources": sources,
        "run": {
            "id": "run",
            "total_source_rows": 5,
            "total_cases": 1,
            "dataset_checksum": dataset_checksum,
            "baseline_result_checksum": canonical_sha256(baseline),
        },
        "cases": [
            {
                "case_id": "case",
                "run_id": "run",
                "case_state": "RECONCILED",
                "cash_bucket": "BANK_CONFIRMED",
                "net_amount_paise": 100,
                "residual_paise": 0,
                "gross_amount_paise": 100,
                "cash_bucket_contribution_paise": 100,
                "invariants": [
                    {"id": "INV-005", "passed": True, "expected": "100", "actual": "100"}
                ],
            }
        ],
        "cash": {
            "safe_cash_paise": 100,
            "buckets": {"BANK_CONFIRMED": {"amount_paise": 100, "case_ids": ["case"]}},
        },
    }
    payload["policy_sha256"] = canonical_sha256(payload["policy"])
    return {
        "format": "clearledger.control.v1",
        "payload": payload,
        "sha256": canonical_sha256(payload),
    }


def test_offline_package_checks_integrity_and_cash_without_application_runtime() -> None:
    package = package_fixture()
    assert verify_package(package, package["sha256"]) == []


def test_changed_cash_fails_even_when_attacker_recomputes_embedded_digest() -> None:
    package = package_fixture()
    original = package["sha256"]
    package["payload"]["cash"]["buckets"]["BANK_CONFIRMED"]["amount_paise"] = 101
    package["sha256"] = canonical_sha256(package["payload"])
    failures = verify_package(package, original)
    assert any("Cash bucket sum mismatch" in error for error in failures)
    assert any("externally recorded" in error for error in failures)


def test_source_rewrite_row_omission_policy_change_and_cross_run_history_fail() -> None:
    package = package_fixture()
    mutations = [
        lambda p: p["sources"][0].update(
            content_base64=base64.b64encode(b"id\ntampered\n").decode()
        ),
        lambda p: p["sources"][0].update(rows=[]),
        lambda p: p["policy"].update(holidays=[]),
        lambda p: p["baseline_result"].update(dataset_id="tampered"),
        lambda p: p["input_manifest"]["file_checksums"].update({"orders.csv": "0" * 64}),
        lambda p: p.update(audit=[{"run_id": "another-run"}]),
    ]
    for mutate in mutations:
        changed = copy.deepcopy(package)
        mutate(changed["payload"])
        changed["sha256"] = canonical_sha256(changed["payload"])
        assert verify_package(changed)
