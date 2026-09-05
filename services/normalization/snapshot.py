"""Load only the policy recorded with an execution, never the current default."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from db.models import PolicyVersion, ReconciliationRun
from services.normalization.policy import SettlementPolicy


async def recorded_policy(session: AsyncSession, run: ReconciliationRun) -> SettlementPolicy:
    payload = run.policy_snapshot
    if not payload and run.policy_version_id:
        version = await session.get(PolicyVersion, run.policy_version_id)
        payload = version.policy_data if version else {}
    if not payload:
        raise ValueError("This execution has no recorded policy; create a new execution.")
    return SettlementPolicy.model_validate(payload)
