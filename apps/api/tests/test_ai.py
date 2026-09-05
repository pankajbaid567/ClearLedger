"""AI route behavior when the optional provider is disabled."""

from __future__ import annotations

import uuid

import httpx
import pytest


@pytest.mark.asyncio(loop_scope="session")
async def test_single_case_analysis_reports_disabled(api_client: httpx.AsyncClient) -> None:
    response = await api_client.post(
        "/api/cases/CASE_AMB0073/analyze",
        headers={"Idempotency-Key": f"analyze-{uuid.uuid4()}"},
    )
    assert response.status_code == 501
    assert response.json()["error"]["code"] == "AI_DISABLED"


@pytest.mark.asyncio(loop_scope="session")
async def test_grounded_qa_falls_back_to_computed_facts_when_ai_is_disabled(
    api_client: httpx.AsyncClient,
    reconciled_run: dict[str, str],
) -> None:
    response = await api_client.post(
        f"/api/runs/{reconciled_run['run_id']}/questions",
        json={"question": "What is the cash position?"},
    )

    assert response.status_code == 200
    assert response.json()["grounded"] is True
    assert response.json()["provider"] == "deterministic_grounded_engine"
    assert "Controlled Safe Cash" in response.json()["answer"]
