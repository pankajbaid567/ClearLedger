"""Pydantic v2 schemas for every synthetic source-record CSV the generator produces.

All monetary fields are ``int`` (paise).  All timestamps are UTC-aware ``datetime``.
"""

from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, ConfigDict

from packages.domain.enums import ComponentType, Direction


class _Base(BaseModel):
    model_config = ConfigDict(strict=True, frozen=True)


# ── Orders ──────────────────────────────────────────────────────────────────


class OrderRecord(_Base):
    order_id: str
    merchant_id: str
    order_created_at: datetime
    order_amount_paise: int
    currency: str = "INR"
    expected_payment_status: str = "captured"


# ── Payments ────────────────────────────────────────────────────────────────


class PaymentRecord(_Base):
    payment_id: str
    merchant_id: str
    order_id: str
    payment_status: str  # authorized / captured / failed / refunded
    amount_paise: int
    currency: str = "INR"
    captured_at: datetime | None = None
    payment_method: str = "upi"
    gateway_reference: str = ""


# ── Settlements ─────────────────────────────────────────────────────────────


class SettlementRecord(_Base):
    settlement_id: str
    merchant_id: str
    settlement_status: str  # initiated / processed / failed
    currency: str = "INR"
    net_amount_paise: int
    initiated_at: datetime
    processed_at: datetime | None = None
    expected_bank_date: date
    utr: str | None = None


# ── Settlement Components ───────────────────────────────────────────────────


class SettlementComponentRecord(_Base):
    component_id: str
    settlement_id: str
    component_type: ComponentType
    source_event_id: str
    amount_paise: int
    direction: Direction


# ── Bank Transactions ───────────────────────────────────────────────────────


class BankTransactionRecord(_Base):
    bank_transaction_id: str
    merchant_id: str
    account_id: str
    posted_at: datetime
    value_date: date
    direction: Direction
    amount_paise: int
    currency: str = "INR"
    narration: str = ""
    utr: str | None = None


# ── Aggregate container returned by each scenario constructor ───────────────


class ScenarioRecords(_Base):
    """All source records produced by a single scenario constructor."""

    model_config = ConfigDict(strict=True, frozen=False)

    orders: list[OrderRecord] = []
    payments: list[PaymentRecord] = []
    settlements: list[SettlementRecord] = []
    settlement_components: list[SettlementComponentRecord] = []
    bank_transactions: list[BankTransactionRecord] = []
