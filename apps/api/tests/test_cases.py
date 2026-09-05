from __future__ import annotations

import httpx
import pytest


@pytest.mark.asyncio(loop_scope="session")
async def test_list_and_filter_cases(
    api_client: httpx.AsyncClient, reconciled_run: dict[str, str]
) -> None:
    run_id = reconciled_run["run_id"]
    response = await api_client.get(
        f"/api/runs/{run_id}/cases",
        params={"state": "ACTIONABLE_EXCEPTION", "page_size": 100},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] > 0
    assert all(item["case_state"] == "ACTIONABLE_EXCEPTION" for item in payload["items"])


@pytest.mark.asyncio(loop_scope="session")
async def test_min_age_filter_uses_source_event_age(
    api_client: httpx.AsyncClient, reconciled_run: dict[str, str]
) -> None:
    run_id = reconciled_run["run_id"]
    all_response = await api_client.get(
        f"/api/runs/{run_id}/cases", params={"page_size": 200}
    )
    assert all_response.status_code == 200, all_response.text
    all_items = all_response.json()["items"]
    ages = sorted(item["age_days"] for item in all_items if item["age_days"] is not None)
    threshold = ages[len(ages) // 2]
    expected = {
        item["case_id"]
        for item in all_items
        if item["age_days"] is not None and item["age_days"] >= threshold
    }

    filtered = await api_client.get(
        f"/api/runs/{run_id}/cases",
        params={"min_age_days": threshold, "page_size": 200},
    )
    assert filtered.status_code == 200, filtered.text
    payload = filtered.json()
    assert payload["total"] == len(expected)
    assert {item["case_id"] for item in payload["items"]} == expected
    assert all(item["age_days"] >= threshold for item in payload["items"])


@pytest.mark.asyncio(loop_scope="session")
async def test_case_evidence_and_receipt(
    api_client: httpx.AsyncClient, reconciled_run: dict[str, str]
) -> None:
    detail = await api_client.get(f"/api/runs/{reconciled_run['run_id']}/cases/CASE_0001")
    assert detail.status_code == 200
    assert detail.json()["case_state"] == "RECONCILED"
    assert detail.json()["records"]

    evidence = await api_client.get(
        f"/api/runs/{reconciled_run['run_id']}/cases/CASE_0001/evidence"
    )
    assert evidence.status_code == 200
    assert len(evidence.json()["edges"]) >= 3
    assert all(edge["decision_level"] == "VERIFIED" for edge in evidence.json()["edges"])

    receipt = await api_client.get(f"/api/runs/{reconciled_run['run_id']}/cases/CASE_0001/receipt")
    assert receipt.status_code == 200
    assert receipt.json()["all_invariants_passed"] is True
    assert receipt.json()["residual_paise"] == 0


@pytest.mark.asyncio(loop_scope="session")
async def test_candidates_include_rejection_reasons(
    api_client: httpx.AsyncClient, reconciled_run: dict[str, str]
) -> None:
    response = await api_client.get(
        f"/api/runs/{reconciled_run['run_id']}/cases/CASE_AMB0073/candidates"
    )
    assert response.status_code == 200
    items = response.json()["items"]
    assert items
    assert all(0 <= item["match_score"] <= 1 for item in items if item["match_score"] is not None)
    assert any(item["rejection_reason"] for item in items)
