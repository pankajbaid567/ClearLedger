from __future__ import annotations

import csv
import io
import uuid

import httpx
import pytest

from apps.api.app.routes.exports import _safe_cell


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
