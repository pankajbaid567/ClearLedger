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
async def test_grounded_qa_is_explicitly_unavailable(api_client: httpx.AsyncClient) -> None:
    response = await api_client.post("/api/runs/example/questions")
    assert response.status_code == 501
    assert response.json()["error"]["code"] == "AI_DISABLED"
