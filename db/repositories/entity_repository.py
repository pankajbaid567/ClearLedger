"""Persistence operations for canonical financial entities."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import BankTransaction, Order, Payment, Settlement, SettlementComponent

ENTITY_MODELS = (Order, Payment, Settlement, SettlementComponent, BankTransaction)


class EntityRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def clear_for_run(self, run_id: uuid.UUID) -> None:
        for model in ENTITY_MODELS:
            await self.session.execute(delete(model).where(model.reconciliation_run_id == run_id))

    async def create_order(self, **values: Any) -> Order:
        return await self._create(Order, values)

    async def create_payment(self, **values: Any) -> Payment:
        return await self._create(Payment, values)

    async def create_settlement(self, **values: Any) -> Settlement:
        return await self._create(Settlement, values)

    async def create_settlement_component(self, **values: Any) -> SettlementComponent:
        return await self._create(SettlementComponent, values)

    async def create_bank_transaction(self, **values: Any) -> BankTransaction:
        return await self._create(BankTransaction, values)

    async def _create(self, model: type[Any], values: dict[str, Any]) -> Any:
        instance = model(**values)
        self.session.add(instance)
        await self.session.flush()
        return instance

    async def list_by_type(self, model: type[Any], run_id: uuid.UUID) -> list[Any]:
        result = await self.session.scalars(
            select(model).where(model.reconciliation_run_id == run_id)
        )
        return list(result)
