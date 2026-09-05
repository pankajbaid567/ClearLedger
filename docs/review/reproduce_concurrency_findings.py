import asyncio
import json
import uuid
from unittest.mock import patch

import psycopg
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from db.models import (
    Base,
    CashPositionSnapshot,
    InvariantResult,
    ReconciliationCase,
    ReconciliationRun,
)
from db.repositories import CaseRepository
from services.reconciliation.review_service import ReviewService

ADMIN = "postgresql://clearledger:clearledger@localhost:5432/clearledger"
SCHEMA = "review_" + uuid.uuid4().hex


async def main():
    with psycopg.connect(ADMIN, autocommit=True) as c:
        c.execute(f"CREATE SCHEMA {SCHEMA}")
    engine = create_async_engine(
        ADMIN.replace("postgresql:", "postgresql+psycopg:"),
        connect_args={"options": f"-csearch_path={SCHEMA}"},
    )
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with engine.begin() as c:
            await c.run_sync(Base.metadata.create_all)
        async with factory() as s:
            run = ReconciliationRun(status="COMPLETED", metrics={}, config={})
            s.add(run)
            await s.flush()
            rid = run.id
            for name, amount in [("CASE_A", 100), ("CASE_B", 200)]:
                s.add(
                    ReconciliationCase(
                        reconciliation_run_id=rid,
                        case_id=name,
                        case_state="ACTIONABLE_EXCEPTION",
                        net_amount_paise=amount,
                        residual_paise=0,
                        cash_bucket="UNRESOLVED",
                        bank_receipt_state="CONFIRMED",
                    )
                )
                s.add(
                    InvariantResult(
                        reconciliation_run_id=rid, case_id=name, invariant_id="INV-001", passed=True
                    )
                )
            s.add(
                CashPositionSnapshot(
                    reconciliation_run_id=rid,
                    bank_confirmed_paise=0,
                    settlement_confirmed_in_transit_paise=0,
                    expected_settlement_paise=0,
                    at_risk_paise=0,
                    unresolved_paise=300,
                    scheduled_refunds_paise=0,
                    known_disputes_paise=0,
                    known_reserve_holds_paise=0,
                    safe_cash_paise=0,
                    buckets={},
                )
            )
            await s.commit()
        original = CaseRepository.cash_position
        count = 0
        gate = asyncio.Event()

        async def barrier(repo, *args):
            nonlocal count
            result = await original(repo, *args)
            count += 1
            if count == 2:
                gate.set()
            await gate.wait()
            return result

        async def approve(cid):
            async with factory() as s:
                await ReviewService(s, expected_review_revision=0).approve(
                    cid, actor="reviewer"
                )
                await s.commit()

        with patch.object(CaseRepository, "cash_position", barrier):
            await asyncio.gather(approve("CASE_A"), approve("CASE_B"))
        async with factory() as s:
            cases = list(await s.scalars(select(ReconciliationCase)))
            snapshot = await CaseRepository(s).cash_position(rid)
            run = await s.get(ReconciliationRun, rid)
            print(
                json.dumps(
                    {
                        "test": "concurrent_approvals_lose_aggregate",
                        "cases": {c.case_id: c.case_state for c in cases},
                        "expected_bank_confirmed": 300,
                        "actual_bank_confirmed": snapshot.bank_confirmed_paise,
                        "metrics": run.metrics,
                    }
                )
            )
    finally:
        await engine.dispose()
        with psycopg.connect(ADMIN, autocommit=True) as c:
            c.execute(f"DROP SCHEMA {SCHEMA} CASCADE")


asyncio.run(main())
