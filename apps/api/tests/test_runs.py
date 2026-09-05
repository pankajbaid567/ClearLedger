from __future__ import annotations

import uuid
from pathlib import Path

import httpx
import pytest

ROOT = Path(__file__).resolve().parents[3]


@pytest.mark.asyncio(loop_scope="session")
async def test_full_run_lifecycle_and_metrics(
    api_client: httpx.AsyncClient, reconciled_run: dict[str, str]
) -> None:
    run_id = reconciled_run["run_id"]
    details = await api_client.get(f"/api/runs/{run_id}")
    assert details.status_code == 200
    assert details.json()["status"] == "COMPLETED"
    assert details.json()["total_source_rows"] == 693
    assert details.json()["total_cases"] == 75
    assert len(details.json()["files"]) == 5
    assert details.json()["policy_id"] == "settlement_policy"
    assert details.json()["policy_version"] == "1.0.0"
    assert details.json()["ai_prompt_version"] == "exception_analyst.v1"

    metrics = await api_client.get(f"/api/runs/{run_id}/metrics")
    assert metrics.status_code == 200
    values = metrics.json()["metrics"]
    assert values["precision"] == 1.0
    assert values["recall"] == 1.0
    assert values["false_positive_count"] == 0


@pytest.mark.asyncio(loop_scope="session")
async def test_rerun_replaces_results_idempotently(
    api_client: httpx.AsyncClient, reconciled_run: dict[str, str]
) -> None:
    run_id = reconciled_run["run_id"]
    rerun = await api_client.post(
        f"/api/runs/{run_id}/reconcile",
        headers={"Idempotency-Key": f"rerun-{uuid.uuid4()}"},
    )
    assert rerun.status_code == 200, rerun.text
    assert rerun.json()["result_checksum"] == reconciled_run["result_checksum"]
    assert rerun.json()["evidence_edges"] == 269


@pytest.mark.asyncio(loop_scope="session")
async def test_mutation_requires_idempotency_key(api_client: httpx.AsyncClient) -> None:
    response = await api_client.post("/api/runs", json={})
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "REQUEST_VALIDATION_FAILED"


@pytest.mark.asyncio(loop_scope="session")
async def test_demo_run_bootstrap_loads_and_validates_all_sources(
    api_client: httpx.AsyncClient,
) -> None:
    response = await api_client.post(
        "/api/runs/demo",
        headers={"Idempotency-Key": f"demo-{uuid.uuid4()}"},
    )
    assert response.status_code == 201, response.text
    payload = response.json()
    assert payload["run"]["status"] == "READY_FOR_RECONCILIATION"
    assert len(payload["run"]["files"]) == 5
    assert payload["validation"]["valid"] is True
    assert payload["validation"]["total_rows"] == 693
    assert all(item["control_total_paise"] > 0 for item in payload["validation"]["files"])


@pytest.mark.asyncio(loop_scope="session")
async def test_duplicate_upload_is_rejected_without_duplicate_source_rows(
    api_client: httpx.AsyncClient,
) -> None:
    create = await api_client.post(
        "/api/runs",
        json={},
        headers={"Idempotency-Key": f"duplicate-create-{uuid.uuid4()}"},
    )
    run_id = create.json()["id"]
    content = (ROOT / "data" / "demo" / "orders.csv").read_bytes()
    files = {"orders": ("orders.csv", content, "text/csv")}
    first = await api_client.post(
        f"/api/runs/{run_id}/files",
        files=files,
        headers={"Idempotency-Key": f"duplicate-first-{uuid.uuid4()}"},
    )
    assert first.status_code == 200, first.text

    replay = await api_client.post(
        f"/api/runs/{run_id}/files",
        files=files,
        headers={"Idempotency-Key": f"duplicate-second-{uuid.uuid4()}"},
    )
    assert replay.status_code == 409
    assert replay.json()["error"]["code"] == "DUPLICATE_UPLOAD"
    details = await api_client.get(f"/api/runs/{run_id}")
    assert len(details.json()["files"]) == 1
