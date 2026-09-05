import asyncio
import json
import tempfile
import uuid
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import httpx
import psycopg
from fastapi import UploadFile
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from apps.api.app.dependencies import get_db_session
from apps.api.app.main import app
from apps.api.app.routes import runs as runs_routes
from db.models import Base, HumanDecision, ReconciliationCase, ReconciliationRun
from db.repositories import CaseRepository
from services.ai_analyst.grounded_qa import GroundedQAService
from services.ai_analyst.schemas import AIClientConfig
from services.reconciliation.review_service import ReviewService
from services.reconciliation.run_service import REQUIRED_SOURCE_TYPES, RunService

ROOT = Path.cwd()
ADMIN = "postgresql://clearledger:clearledger@localhost:5432/clearledger"
URL = "postgresql+psycopg://clearledger:clearledger@localhost:5432/clearledger"
SCHEMA = "review_" + uuid.uuid4().hex


async def main():
    with psycopg.connect(ADMIN, autocommit=True) as c:
        c.execute(f"CREATE SCHEMA {SCHEMA}")
    engine = create_async_engine(URL, connect_args={"options": f"-csearch_path={SCHEMA}"})
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with engine.begin() as c:
            await c.run_sync(Base.metadata.create_all)

        async def override():
            async with factory() as s:
                try:
                    yield s
                    await s.commit()
                except Exception:
                    await s.rollback()
                    raise

        app.dependency_overrides[get_db_session] = override
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app, raise_app_exceptions=False),
            base_url="http://test",
        ) as client:
            async with factory() as s:
                for i in range(2):
                    run = ReconciliationRun(
                        status="COMPLETED", metrics={}, config={}, cash_position={}
                    )
                    s.add(run)
                    await s.flush()
                    case = ReconciliationCase(
                        reconciliation_run_id=run.id,
                        case_id="CASE_DUPLICATE",
                        case_state="ACTIONABLE_EXCEPTION",
                        net_amount_paise=100,
                        owner_role=f"run-{i}",
                        cash_bucket="UNRESOLVED",
                    )
                    s.add(case)
                    await s.commit()
                    if i == 0:
                        first = run.id
                    else:
                        second = run.id
            response = await client.get("/api/cases/CASE_DUPLICATE")
            action = await client.post(
                "/api/cases/CASE_DUPLICATE/reject",
                json={"actor": "Old run operator"},
                headers={"Idempotency-Key": "crossrun"},
            )
            async with factory() as s:
                a = await CaseRepository(s).get_case("CASE_DUPLICATE", first)
                b = await CaseRepository(s).get_case("CASE_DUPLICATE", second)
                print(
                    json.dumps(
                        {
                            "test": "cross_run_case_routing",
                            "read_status": response.status_code,
                            "read_owner": response.json().get("owner_role"),
                            "action_status": action.status_code,
                            "first_run_state": a.case_state,
                            "second_run_state": b.case_state,
                        }
                    )
                )
            # Establish policy before racing run creations.
            await client.post("/api/runs", json={}, headers={"Idempotency-Key": "warmup"})
            original = runs_routes.replay_response
            arrived = 0
            gate = asyncio.Event()

            async def race_replay(*args, **kwargs):
                nonlocal arrived
                result = await original(*args, **kwargs)
                arrived += 1
                if arrived == 2:
                    gate.set()
                await gate.wait()
                return result

            with patch.object(runs_routes, "replay_response", race_replay):
                responses = await asyncio.gather(
                    *[
                        client.post(
                            "/api/runs", json={}, headers={"Idempotency-Key": "same-concurrent-key"}
                        )
                        for _ in range(2)
                    ]
                )
            print(
                json.dumps(
                    {
                        "test": "concurrent_same_idempotency_key",
                        "statuses": [r.status_code for r in responses],
                        "bodies": [
                            r.json() if r.status_code != 201 else {"id": r.json()["id"]}
                            for r in responses
                        ],
                    }
                )
            )
        with tempfile.TemporaryDirectory(prefix="clearledger-review-") as uploads:
            async with factory() as s:
                service = RunService(s, upload_dir=uploads)
                run = await service.create_run()
                run_id = run.id
                files = {
                    kind: UploadFile(
                        filename=f"{kind}.csv",
                        file=BytesIO((ROOT / "data" / "demo" / f"{kind}.csv").read_bytes()),
                    )
                    for kind in REQUIRED_SOURCE_TYPES
                }
                await service.add_files_to_run(run_id, files)
                await s.commit()
                await service.execute_reconciliation(run_id)
                await s.commit()
                await ReviewService(s).assign(
                    "CASE_AMB0073", actor="reviewer", owner_role="Assigned Reviewer"
                )
                await s.commit()
                case = await CaseRepository(s).get_case("CASE_AMB0073", run_id)
                before = {
                    "owner": case.owner_role,
                    "human_reviewed": case.human_reviewed,
                    "row_id": str(case.id),
                }
                await service.execute_reconciliation(run_id)
                await s.commit()
                case = await CaseRepository(s).get_case("CASE_AMB0073", run_id)
                count = await s.scalar(
                    select(func.count())
                    .select_from(HumanDecision)
                    .where(HumanDecision.reconciliation_run_id == run_id)
                )
                print(
                    json.dumps(
                        {
                            "test": "rerun_loses_review",
                            "before": before,
                            "after": {
                                "owner": case.owner_role,
                                "human_reviewed": case.human_reviewed,
                                "row_id": str(case.id),
                            },
                            "historical_decisions_retained": count,
                        }
                    )
                )
        service = GroundedQAService(session=None, config=AIClientConfig())
        run = ReconciliationRun(id=uuid.uuid4(), status="COMPLETED", total_cases=0, metrics={})
        data = service._build_computed_data(run, None, [], "accuracy")
        answer, _ = service._deterministic_answer("accuracy", data, run, None, [], set())
        print(json.dumps({"test": "unevaluated_qa_metrics", "answer": answer}))
        run.metrics = {
            "relationship_precision": 0.7,
            "relationship_recall": 0.5,
            "relationship_f1": 0.58,
            "false_positive_count": 3,
        }
        data = service._build_computed_data(run, None, [], "accuracy")
        answer, _ = service._deterministic_answer("accuracy", data, run, None, [], set())
        print(json.dumps({"test": "bad_metrics_qa", "answer": answer}))
        response = SimpleNamespace(
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(
                        content="Safe cash is ₹999999999. CASE_INVENTED is reconciled."
                    )
                )
            ]
        )
        fake = SimpleNamespace(
            chat=SimpleNamespace(
                completions=SimpleNamespace(create=AsyncMock(return_value=response))
            )
        )
        service.prompt_path = SimpleNamespace(
            read_text=lambda: "Facts {computed_data_json}. User {user_question}"
        )
        with patch("services.ai_analyst.grounded_qa.openai.AsyncOpenAI", return_value=fake):
            answer, cited = await service._call_llm("cash?", {"cash": 0}, set())
        print(json.dumps({"test": "unvalidated_llm_qa", "answer": answer, "cited_case_ids": cited}))
    finally:
        app.dependency_overrides.clear()
        await engine.dispose()
        with psycopg.connect(ADMIN, autocommit=True) as c:
            c.execute(f"DROP SCHEMA {SCHEMA} CASCADE")


asyncio.run(main())
