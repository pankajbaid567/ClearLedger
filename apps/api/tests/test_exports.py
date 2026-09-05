from __future__ import annotations

import csv
import io
import uuid

import httpx
import pytest

from apps.api.app.routes.exports import _safe_cell
from services.reporting.verify import verify_package


@pytest.mark.asyncio(loop_scope="session")
async def test_csv_exports_and_formula_escape(
    api_client: httpx.AsyncClient, reconciled_run: dict[str, str]
) -> None:
    run_id = reconciled_run["run_id"]
    reconciliation = await api_client.get(f"/api/runs/{run_id}/exports/reconciliation.csv")
    assert reconciliation.status_code == 200
    rows = list(csv.DictReader(io.StringIO(reconciliation.text)))
    assert rows
    assert all(row["case_state"] == "RECONCILED" for row in rows)

    exceptions = await api_client.get(f"/api/runs/{run_id}/exports/exceptions.csv")
    assert exceptions.status_code == 200
    exception_rows = list(csv.DictReader(io.StringIO(exceptions.text)))
    assert exception_rows
    assert _safe_cell("=SUM(A1:A2)") == "'=SUM(A1:A2)"
    assert _safe_cell("@command") == "'@command"


@pytest.mark.asyncio(loop_scope="session")
async def test_audit_export_and_cash_position(
    api_client: httpx.AsyncClient, reconciled_run: dict[str, str]
) -> None:
    run_id = reconciled_run["run_id"]
    audit = await api_client.get(f"/api/runs/{run_id}/exports/audit.json")
    assert audit.status_code == 200
    assert audit.json()["events"]
    assert any(item["event_type"] == "RECONCILIATION_COMPLETED" for item in audit.json()["events"])

    cash = await api_client.get(f"/api/runs/{run_id}/cash-position")
    assert cash.status_code == 200
    assert set(cash.json()["buckets"]) == {
        "BANK_CONFIRMED",
        "SETTLEMENT_CONFIRMED_IN_TRANSIT",
        "EXPECTED_SETTLEMENT",
        "AT_RISK",
        "UNRESOLVED",
    }

    evaluation = await api_client.post(
        f"/api/runs/{run_id}/evaluate",
        headers={"Idempotency-Key": f"export-evaluation-{uuid.uuid4()}"},
    )
    assert evaluation.status_code == 200, evaluation.text

    evaluation_json = await api_client.get(f"/api/runs/{run_id}/exports/evaluation.json")
    assert evaluation_json.status_code == 200
    assert evaluation_json.json()["aggregate"]["relationship_precision"] == 1.0

    evaluation_markdown = await api_client.get(f"/api/runs/{run_id}/exports/evaluation.md")
    assert evaluation_markdown.status_code == 200
    assert "# ClearLedger Evaluation" in evaluation_markdown.text
    assert "Scenario Breakdown" in evaluation_markdown.text


@pytest.mark.asyncio(loop_scope="session")
async def test_rejected_rows_and_control_package_are_independently_verifiable(
    api_client: httpx.AsyncClient,
    reconciled_run: dict[str, str],
) -> None:
    run_id = reconciled_run["run_id"]
    rejected = await api_client.get(f"/api/runs/{run_id}/exports/rejected-rows.csv")
    assert rejected.status_code == 200
    rejected_rows = list(csv.DictReader(io.StringIO(rejected.text)))
    assert len(rejected_rows) == 8
    assert all(row["quality"] != "VALID" for row in rejected_rows)
    assert all(row["issues_json"] and row["raw_values_json"] for row in rejected_rows)

    response = await api_client.get(f"/api/runs/{run_id}/exports/control-package.json")
    assert response.status_code == 200, response.text
    package = response.json()
    assert response.headers["x-control-package-sha256"] == package["sha256"]
    assert verify_package(package, package["sha256"]) == []
    assert package["payload"]["run"]["baseline_result_checksum"] == reconciled_run[
        "result_checksum"
    ]
