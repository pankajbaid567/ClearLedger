"""Real database regressions for isolation, immutable runs and concurrent mutations."""

from __future__ import annotations

import asyncio
import hashlib
import json
import threading
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx
import pytest
from sqlalchemy import select

from apps.api.app.auth import Principal, get_principal
from apps.api.app.idempotency import _request_checksum
from apps.api.app.main import app
from apps.api.app.schemas.runs import RunCreateRequest
from db.models import (
    CashPositionSnapshot,
    HumanDecision,
    IdempotencyRecord,
    ReconciliationCase,
    ReconciliationRun,
)
from db.repositories import RunRepository
from services.reconciliation import run_service as run_module
from services.reconciliation.review_service import ReviewService

ROOT = Path(__file__).resolve().parents[3]


def headers() -> dict[str, str]:
    return {"Idempotency-Key": uuid.uuid4().hex}


async def current_review_revision(client: httpx.AsyncClient, run_id: str) -> int:
    response = await client.get(f"/api/runs/{run_id}")
    assert response.status_code == 200, response.text
    return int(response.json()["review_revision"])


async def demo(client: httpx.AsyncClient, *, execute: bool = True) -> str:
    created = await client.post("/api/runs/demo", headers=headers())
    assert created.status_code == 201, created.text
    run_id = created.json()["run"]["id"]
    if execute:
        response = await client.post(f"/api/runs/{run_id}/reconcile", headers=headers())
        assert response.status_code == 200, response.text
    return run_id


@pytest.mark.asyncio(loop_scope="session")
async def test_concurrent_idempotency_returns_one_run(api_client: httpx.AsyncClient) -> None:
    key = headers()
    responses = await asyncio.gather(
        *[api_client.post("/api/runs", json={}, headers=key) for _ in range(20)]
    )
    assert all(item.status_code == 201 for item in responses), [item.text for item in responses]
    assert len({item.json()["id"] for item in responses}) == 1
    conflict = await api_client.post(
        "/api/runs", json={"as_of_at": "2026-01-01T00:00:00Z"}, headers=key
    )
    assert conflict.status_code == 409


@pytest.mark.asyncio(loop_scope="session")
async def test_unique_concurrent_claims_do_not_exhaust_connection_pool(api_client) -> None:
    responses = await asyncio.wait_for(
        asyncio.gather(
            *[
                api_client.post("/api/runs", json={}, headers=headers())
                for _ in range(24)
            ]
        ),
        timeout=10,
    )
    assert all(item.status_code == 201 for item in responses), [item.text for item in responses]
    assert len({item.json()["id"] for item in responses}) == 24


@pytest.mark.asyncio(loop_scope="session")
async def test_expired_claim_is_recovered_after_worker_loss(api_client, session_factory) -> None:
    key = uuid.uuid4().hex
    checksum = _request_checksum(RunCreateRequest().model_dump(mode="json"))
    async with session_factory() as session:
        session.add(
            IdempotencyRecord(
                scope="demo.finance.operator:POST:/api/runs",
                idempotency_key=key,
                request_checksum=checksum,
                response_status=102,
                response_payload={},
                state="IN_PROGRESS",
                claim_token="dead-worker",
                lease_expires_at=datetime.now(UTC) - timedelta(seconds=1),
            )
        )
        await session.commit()
    response = await api_client.post("/api/runs", json={}, headers={"Idempotency-Key": key})
    assert response.status_code == 201, response.text


@pytest.mark.asyncio(loop_scope="session")
async def test_completed_replay_preserves_review_and_successor_lineage(
    api_client, session_factory
) -> None:
    run_id = await demo(api_client)
    url = f"/api/runs/{run_id}/cases/CASE_AMB0073"
    assigned = await api_client.post(
        f"{url}/assign",
        json={
            "owner_role": "Treasury",
            "actor": "spoofed.person",
            "expected_review_revision": 0,
        },
        headers=headers(),
    )
    assert assigned.status_code == 200, assigned.text
    revision = assigned.json()["review_revision"]
    before = (await api_client.get(url)).json()
    original_run = (await api_client.get(f"/api/runs/{run_id}")).json()
    replay = await api_client.post(f"/api/runs/{run_id}/reconcile", headers=headers())
    assert replay.status_code == 200 and replay.json()["replayed"] is True
    after = (await api_client.get(url)).json()
    assert after["owner_role"] == "Treasury"
    assert after["human_reviewed"] is True
    assert after["updated_at"] == before["updated_at"]
    assert replay.json()["review_revision"] == revision
    assert replay.json()["result_checksum"] == original_run["result_checksum"]
    successor = await api_client.post(
        "/api/runs", json={"parent_run_id": run_id}, headers=headers()
    )
    assert successor.status_code == 201
    assert successor.json()["parent_run_id"] == run_id
    assert successor.json()["execution_revision"] == 2
    assert successor.json()["files"] == []
    duplicate_successor = await api_client.post(
        "/api/runs", json={"parent_run_id": run_id}, headers=headers()
    )
    assert duplicate_successor.status_code == 409
    assert duplicate_successor.json()["error"]["code"] == "SUCCESSOR_ALREADY_EXISTS"

    successor_id = successor.json()["id"]
    source_types = (
        "orders",
        "payments",
        "settlements",
        "settlement_components",
        "bank_transactions",
    )
    files = {
        source_type: (
            f"{source_type}.csv",
            (ROOT / "data" / "demo" / f"{source_type}.csv").read_bytes(),
            "text/csv",
        )
        for source_type in source_types
    }
    uploaded = await api_client.post(
        f"/api/runs/{successor_id}/files", files=files, headers=headers()
    )
    assert uploaded.status_code == 200, uploaded.text
    executed = await api_client.post(
        f"/api/runs/{successor_id}/reconcile", headers=headers()
    )
    assert executed.status_code == 200, executed.text
    carried_case = (
        await api_client.get(f"/api/runs/{successor_id}/cases/CASE_AMB0073")
    ).json()
    assert carried_case["owner_role"] == "Treasury"
    assert carried_case["human_reviewed"] is True
    successor_run = (await api_client.get(f"/api/runs/{successor_id}")).json()
    assert successor_run["review_revision"] == 1
    async with session_factory() as session:
        decision = await session.scalar(
            select(HumanDecision).where(HumanDecision.reconciliation_run_id == uuid.UUID(run_id))
        )
        assert decision.actor == "demo.finance.operator"
        run = await session.get(ReconciliationRun, uuid.UUID(run_id))
        assert run.policy_snapshot["holidays"]
        assert len(run.input_manifest["file_checksums"]) == 5
        carry = await session.scalar(
            select(HumanDecision).where(
                HumanDecision.reconciliation_run_id == uuid.UUID(successor_id),
                HumanDecision.action == "CARRY_FORWARD_ASSIGNMENT",
            )
        )
        assert carry is not None and str(decision.id) in (carry.note or "")
        successor_record = await session.get(ReconciliationRun, uuid.UUID(successor_id))
        assert successor_record.config["review_carry_forward"]["status"] == "applied"


@pytest.mark.asyncio(loop_scope="session")
async def test_repeated_case_ids_require_run_and_never_cross_mutate(api_client) -> None:
    first, second = await demo(api_client), await demo(api_client)
    ambiguous = await api_client.get("/api/cases/CASE_AMB0073")
    assert ambiguous.status_code == 409
    assert ambiguous.json()["error"]["code"] == "AMBIGUOUS_CASE_ID"
    response = await api_client.post(
        f"/api/runs/{first}/cases/CASE_AMB0073/reject",
        json={"expected_review_revision": 0},
        headers=headers(),
    )
    assert response.status_code == 200, response.text
    a = (await api_client.get(f"/api/runs/{first}/cases/CASE_AMB0073")).json()
    b = (await api_client.get(f"/api/runs/{second}/cases/CASE_AMB0073")).json()
    assert a["case_state"] == "REJECTED_SUGGESTION"
    assert b["case_state"] == "ACTIONABLE_EXCEPTION"


@pytest.mark.asyncio(loop_scope="session")
async def test_concurrent_review_aggregates_match_current_cases(
    api_client, session_factory
) -> None:
    run_id = await demo(api_client)
    async with session_factory() as session:
        cases = list(
            await session.scalars(
                select(ReconciliationCase).where(
                    ReconciliationCase.reconciliation_run_id == uuid.UUID(run_id),
                    ReconciliationCase.case_id.in_(["CASE_0001", "CASE_0002", "CASE_0003"]),
                )
            )
        )
        for case in cases:
            case.case_state = "ACTIONABLE_EXCEPTION"
            case.cash_bucket = "UNRESOLVED"
        await session.flush()
        await ReviewService(session).recalculate_aggregates(uuid.UUID(run_id))
        await session.commit()
    responses = await asyncio.gather(
        *[
            api_client.post(
                f"/api/runs/{run_id}/cases/{case}/approve",
                json={"expected_review_revision": 0},
                headers=headers(),
            )
            for case in ("CASE_0001", "CASE_0002", "CASE_0003")
        ]
    )
    assert sorted(response.status_code for response in responses) == [200, 409, 409]
    completed = [response for response in responses if response.status_code == 200]
    assert all(
        response.json()["error"]["code"] == "STALE_REVIEW_REVISION"
        for response in responses
        if response.status_code == 409
    )
    for response in responses:
        if response.status_code == 200:
            continue
        case_id = response.request.url.path.split("/")[-2]
        completed.append(
            await api_client.post(
                f"/api/runs/{run_id}/cases/{case_id}/approve",
                json={
                    "expected_review_revision": await current_review_revision(
                        api_client, run_id
                    )
                },
                headers=headers(),
            )
        )
    assert all(response.status_code == 200 for response in completed)
    assert sorted(response.json()["review_revision"] for response in completed) == [1, 2, 3]
    async with session_factory() as session:
        run = await session.get(ReconciliationRun, uuid.UUID(run_id))
        cases = list(
            await session.scalars(
                select(ReconciliationCase).where(ReconciliationCase.reconciliation_run_id == run.id)
            )
        )
        bank = sum(case.net_amount_paise for case in cases if case.cash_bucket == "BANK_CONFIRMED")
        assert run.cash_position["bank_confirmed_paise"] == bank
        assert run.metrics["reconciled_cases"] == sum(
            case.case_state == "RECONCILED" for case in cases
        )
    stale = await api_client.post(
        f"/api/runs/{run_id}/cases/CASE_AMB0073/assign",
        json={"owner_role": "Treasury", "expected_review_revision": 0},
        headers=headers(),
    )
    assert stale.status_code == 409 and stale.json()["error"]["code"] == "STALE_REVIEW_REVISION"


@pytest.mark.asyncio(loop_scope="session")
async def test_progress_is_committed_while_execution_is_running(api_client, monkeypatch) -> None:
    run_id = await demo(api_client, execute=False)
    entered, release = threading.Event(), threading.Event()
    original = run_module.run_reconciliation

    def controlled(source_files, policy, run_id, *, on_stage=None):
        on_stage("candidate_generation", 42)
        entered.set()
        assert release.wait(timeout=10)
        return original(source_files, policy, run_id, on_stage=on_stage)

    monkeypatch.setattr(run_module, "run_reconciliation", controlled)
    task = asyncio.create_task(api_client.post(f"/api/runs/{run_id}/reconcile", headers=headers()))
    try:
        assert await asyncio.to_thread(entered.wait, 5)
        status = await api_client.get(f"/api/runs/{run_id}/status")
        assert status.status_code == 200
        assert status.json()["status"] == "RECONCILING"
        assert status.json()["stage"] == "candidate_generation"
        assert status.json()["processed_records"] == 42
        competing = await api_client.post(f"/api/runs/{run_id}/reconcile", headers=headers())
        assert competing.status_code == 409
    finally:
        release.set()
        response = await task
    assert response.status_code == 200, response.text


@pytest.mark.asyncio(loop_scope="session")
async def test_expired_execution_is_frozen_and_recovered_with_successor(
    api_client, session_factory
) -> None:
    run_id = await demo(api_client, execute=False)
    async with session_factory() as session:
        run = await session.get(ReconciliationRun, uuid.UUID(run_id))
        run.status = "RECONCILING"
        run.stage = "persistence"
        run.execution_attempt_token = "terminated-worker"
        run.execution_lease_expires_at = datetime.now(UTC) - timedelta(seconds=1)
        await session.commit()

    response = await api_client.post(f"/api/runs/{run_id}/reconcile", headers=headers())
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "RUN_EXECUTION_ABANDONED"
    frozen = (await api_client.get(f"/api/runs/{run_id}")).json()
    assert frozen["status"] == "FAILED"
    assert frozen["stage"] == "abandoned"
    successor = await api_client.post(
        "/api/runs", json={"parent_run_id": run_id}, headers=headers()
    )
    assert successor.status_code == 201, successor.text
    assert successor.json()["execution_revision"] == 2


@pytest.mark.asyncio(loop_scope="session")
async def test_other_subject_cannot_read_or_review_run(api_client) -> None:
    run_id = await demo(api_client)
    original = app.dependency_overrides[get_principal]
    app.dependency_overrides[get_principal] = lambda: Principal("other.operator", "admin")
    try:
        for path in (f"/api/runs/{run_id}", f"/api/runs/{run_id}/cases/CASE_0001"):
            assert (await api_client.get(path)).status_code == 404
        denied = await api_client.post(
            f"/api/runs/{run_id}/cases/CASE_0001/approve",
            json={"expected_review_revision": 0},
            headers=headers(),
        )
        assert denied.status_code == 404
    finally:
        app.dependency_overrides[get_principal] = original


@pytest.mark.asyncio(loop_scope="session")
async def test_receipt_hash_distinguishes_baseline_and_current_review(api_client) -> None:
    run_id = await demo(api_client)
    url = f"/api/runs/{run_id}/cases/CASE_AMB0073"
    before = (await api_client.get(f"{url}/receipt")).json()
    repeated = (await api_client.get(f"{url}/receipt")).json()
    assert before["current_review_checksum"] == repeated["current_review_checksum"]
    assigned = await api_client.post(
        f"{url}/assign",
        json={"owner_role": "Treasury", "expected_review_revision": 0},
        headers=headers(),
    )
    assert assigned.status_code == 200
    after = (await api_client.get(f"{url}/receipt")).json()
    assert after["baseline_result_checksum"] == before["baseline_result_checksum"]
    assert after["result_checksum"] == after["baseline_result_checksum"]
    assert after["current_review_checksum"] != before["current_review_checksum"]
    encoded = json.dumps(
        after["review_checksum_payload"], sort_keys=True, separators=(",", ":")
    ).encode()
    assert hashlib.sha256(encoded).hexdigest() == after["current_review_checksum"]
    assert after["review_checksum_payload"]["case"]["owner_role"] == "Treasury"


@pytest.mark.asyncio(loop_scope="session")
async def test_evaluation_stays_bound_to_baseline_after_review(api_client) -> None:
    run_id = await demo(api_client)
    evaluated = await api_client.post(
        f"/api/runs/{run_id}/evaluate", headers=headers()
    )
    assert evaluated.status_code == 200, evaluated.text
    baseline = evaluated.json()
    assert baseline["evaluation_scope"] == "IMMUTABLE_ENGINE_BASELINE"
    assert baseline["evaluated_review_revision"] == 0
    assert baseline["current_review_revision"] == 0

    reviewed = await api_client.post(
        f"/api/runs/{run_id}/cases/CASE_AMB0073/assign",
        json={"owner_role": "Treasury", "expected_review_revision": 0},
        headers=headers(),
    )
    assert reviewed.status_code == 200, reviewed.text
    current = (await api_client.get(f"/api/runs/{run_id}/evaluation")).json()
    assert current["evaluated_review_revision"] == 0
    assert current["current_review_revision"] == 1
    assert current["baseline_result_checksum"] == baseline["baseline_result_checksum"]


@pytest.mark.asyncio(loop_scope="session")
async def test_evaluation_serializes_with_current_projection_updates(
    api_client, session_factory
) -> None:
    run_id = await demo(api_client)
    async with session_factory() as writer:
        run = await RunRepository(writer).get_for_update(uuid.UUID(run_id))
        assert run is not None
        run.review_revision = 1
        run.metrics = {**run.metrics, "concurrent_review_marker": 1}
        evaluation_task = asyncio.create_task(
            api_client.post(f"/api/runs/{run_id}/evaluate", headers=headers())
        )
        await asyncio.sleep(0.1)
        assert not evaluation_task.done()
        await writer.commit()
    evaluated = await evaluation_task
    assert evaluated.status_code == 200, evaluated.text
    assert evaluated.json()["evaluated_review_revision"] == 1
    metrics = (await api_client.get(f"/api/runs/{run_id}/metrics")).json()
    assert metrics["review_revision"] == 1
    assert metrics["metrics"]["concurrent_review_marker"] == 1


@pytest.mark.asyncio(loop_scope="session")
async def test_cash_projection_waits_for_one_coherent_review_revision(
    api_client, session_factory
) -> None:
    run_id = await demo(api_client)
    async with session_factory() as writer:
        run = await RunRepository(writer).get_for_update(uuid.UUID(run_id))
        assert run is not None
        snapshot = await writer.scalar(
            select(CashPositionSnapshot).where(
                CashPositionSnapshot.reconciliation_run_id == uuid.UUID(run_id)
            )
        )
        assert snapshot is not None
        run.review_revision = 1
        snapshot.safe_cash_paise += 7
        expected_cash = snapshot.safe_cash_paise
        forecast_task = asyncio.create_task(
            api_client.get(f"/api/runs/{run_id}/cash-forecast")
        )
        await asyncio.sleep(0.1)
        assert not forecast_task.done()
        await writer.commit()
    forecast = await forecast_task
    assert forecast.status_code == 200, forecast.text
    assert forecast.json()["review_revision"] == 1
    assert forecast.json()["baseline_safe_cash_paise"] == expected_cash


@pytest.mark.asyncio(loop_scope="session")
async def test_source_hash_mismatch_fails_before_results_are_persisted(
    api_client, session_factory
) -> None:
    from apps.api.app.config import get_settings

    run_id = await demo(api_client, execute=False)
    source_path = get_settings().upload_dir / run_id / "orders.csv"
    original = source_path.read_bytes()
    try:
        source_path.write_bytes(original + b"\n")
        response = await api_client.post(f"/api/runs/{run_id}/reconcile", headers=headers())
        assert response.status_code == 409
        assert response.json()["error"]["code"] == "SOURCE_INTEGRITY_FAILED"
        status = (await api_client.get(f"/api/runs/{run_id}/status")).json()
        assert status["status"] == "FAILED"
        async with session_factory() as session:
            cases = list(
                await session.scalars(
                    select(ReconciliationCase).where(
                        ReconciliationCase.reconciliation_run_id == uuid.UUID(run_id),
                    )
                )
            )
            assert cases == []
    finally:
        source_path.write_bytes(original)
