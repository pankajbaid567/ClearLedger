from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import httpx
import pytest


def _headers(action: str) -> dict[str, str]:
    return {"Idempotency-Key": f"{action}-{uuid.uuid4()}"}


@pytest.mark.asyncio(loop_scope="session")
async def test_valid_approval_passes_invariants(
    api_client: httpx.AsyncClient, reconciled_run: dict[str, str]
) -> None:
    response = await api_client.post(
        "/api/cases/CASE_0001/approve",
        json={"actor": "reviewer@example.test", "reason": "Verified receipt"},
        headers=_headers("approve-valid"),
    )
    assert response.status_code == 200, response.text
    assert response.json()["invariant_passed"] is True
    assert response.json()["new_state"] == "RECONCILED"


@pytest.mark.asyncio(loop_scope="session")
async def test_invariant_failed_approval_moves_to_pending_verification(
    api_client: httpx.AsyncClient, reconciled_run: dict[str, str]
) -> None:
    response = await api_client.post(
        "/api/cases/CASE_FV0056/approve",
        json={"actor": "reviewer@example.test", "reason": "Attempted override"},
        headers=_headers("approve-invalid"),
    )
    assert response.status_code == 200, response.text
    assert response.json()["invariant_passed"] is False
    assert response.json()["new_state"] == "APPROVED_PENDING_VERIFICATION"
    detail = await api_client.get("/api/cases/CASE_FV0056")
    assert detail.json()["case_state"] == "APPROVED_PENDING_VERIFICATION"
    assert detail.json()["cash_bucket"] == "UNRESOLVED"
    assert detail.json()["human_reviewed"] is True


@pytest.mark.asyncio(loop_scope="session")
async def test_reject_defer_assign_and_task(
    api_client: httpx.AsyncClient, reconciled_run: dict[str, str]
) -> None:
    rejected = await api_client.post(
        "/api/cases/CASE_FV0057/reject",
        json={"actor": "reviewer@example.test", "reason": "Bad suggestion"},
        headers=_headers("reject"),
    )
    assert rejected.status_code == 200, rejected.text
    assert rejected.json()["new_state"] == "REJECTED_SUGGESTION"

    deferred = await api_client.post(
        "/api/cases/CASE_MS0070/defer",
        json={
            "actor": "reviewer@example.test",
            "reason": "Awaiting bank trace",
            "until": (datetime.now(UTC).date() + timedelta(days=2)).isoformat(),
        },
        headers=_headers("defer"),
    )
    assert deferred.status_code == 200, deferred.text
    assert deferred.json()["new_state"] == "DEFERRED"

    assigned = await api_client.post(
        "/api/cases/CASE_FV0058/assign",
        json={"actor": "lead@example.test", "owner_role": "FINANCE_OPERATIONS"},
        headers=_headers("assign"),
    )
    assert assigned.status_code == 200, assigned.text

    task = await api_client.post(
        "/api/cases/CASE_FV0058/tasks",
        json={
            "actor": "lead@example.test",
            "task_type": "REVIEW_FEE_POLICY",
            "amount_at_risk_paise": 200,
        },
        headers=_headers("task"),
    )
    assert task.status_code == 200, task.text
    assert task.json()["status"] == "OPEN"


@pytest.mark.asyncio(loop_scope="session")
async def test_reconciled_case_cannot_be_deferred(
    api_client: httpx.AsyncClient,
    reconciled_run: dict[str, str],
) -> None:
    del reconciled_run
    response = await api_client.post(
        "/api/cases/CASE_0001/defer",
        json={
            "actor": "demo.operator@clearledger.local",
            "until": "2026-12-31",
            "reason": "failure injection",
        },
        headers=_headers("invalid-defer"),
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "INVALID_STATE_TRANSITION"
