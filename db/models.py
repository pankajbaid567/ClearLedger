"""SQLAlchemy 2.x models for the ClearLedger persistence layer."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """Declarative base shared by all database models."""


class UuidPrimaryKeyMixin:
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=text("gen_random_uuid()"),
    )


class CreatedAtMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )


class PolicyVersion(UuidPrimaryKeyMixin, CreatedAtMixin, Base):
    __tablename__ = "policy_versions"
    __table_args__ = (UniqueConstraint("policy_id", "version"),)

    policy_id: Mapped[str] = mapped_column(Text, nullable=False)
    version: Mapped[str] = mapped_column(Text, nullable=False)
    policy_checksum: Mapped[str] = mapped_column(Text, nullable=False)
    policy_data: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)


class ReconciliationRun(UuidPrimaryKeyMixin, CreatedAtMixin, Base):
    __tablename__ = "reconciliation_runs"
    __table_args__ = (
        UniqueConstraint("parent_run_id", name="uq_reconciliation_runs_parent_run_id"),
    )

    owner_subject: Mapped[str | None] = mapped_column(Text, index=True)
    parent_run_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("reconciliation_runs.id")
    )
    execution_revision: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1, server_default="1"
    )
    review_revision: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    as_of_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    stage: Mapped[str] = mapped_column(
        Text, nullable=False, default="created", server_default="created"
    )
    progress_percent: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    processed_records: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    execution_attempt_token: Mapped[str | None] = mapped_column(Text)
    execution_lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    policy_snapshot: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb")
    )
    input_manifest: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb")
    )
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default="CREATED")
    policy_version_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("policy_versions.id")
    )
    dataset_checksum: Mapped[str | None] = mapped_column(Text)
    rule_set_version: Mapped[str | None] = mapped_column(Text)
    app_version: Mapped[str | None] = mapped_column(Text)
    ai_model: Mapped[str | None] = mapped_column(Text)
    ai_prompt_version: Mapped[str | None] = mapped_column(Text)
    config: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb")
    )
    metrics: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb")
    )
    cash_position: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb")
    )
    evaluation: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb")
    )
    result_checksum: Mapped[str | None] = mapped_column(Text)
    failure_reason: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    duration_ms: Mapped[int | None] = mapped_column(BigInteger)
    total_source_rows: Mapped[int | None] = mapped_column(Integer)
    total_cases: Mapped[int | None] = mapped_column(Integer)


class SourceFile(UuidPrimaryKeyMixin, CreatedAtMixin, Base):
    __tablename__ = "source_files"
    __table_args__ = (
        UniqueConstraint("reconciliation_run_id", "source_type"),
        Index("ix_source_files_checksum", "file_checksum"),
        Index("ix_source_files_run_id", "reconciliation_run_id"),
        Index("ix_source_files_created_at", "created_at"),
    )

    filename: Mapped[str] = mapped_column(Text, nullable=False)
    source_type: Mapped[str] = mapped_column(Text, nullable=False)
    file_checksum: Mapped[str] = mapped_column(Text, nullable=False)
    file_size_bytes: Mapped[int | None] = mapped_column(BigInteger)
    row_count: Mapped[int | None] = mapped_column(Integer)
    ingestion_quality: Mapped[str] = mapped_column(Text, nullable=False)
    reconciliation_run_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("reconciliation_runs.id", ondelete="CASCADE")
    )


class RawSourceRow(UuidPrimaryKeyMixin, CreatedAtMixin, Base):
    __tablename__ = "raw_source_rows"
    __table_args__ = (
        UniqueConstraint("source_file_id", "row_number"),
        Index("ix_raw_source_rows_file_id", "source_file_id"),
        Index("ix_raw_source_rows_created_at", "created_at"),
    )

    source_file_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("source_files.id", ondelete="CASCADE"), nullable=False
    )
    row_number: Mapped[int] = mapped_column(Integer, nullable=False)
    raw_payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    quality: Mapped[str] = mapped_column(Text, nullable=False)
    validation_errors: Mapped[list[dict[str, Any]] | None] = mapped_column(JSONB)


class IngestionIssue(UuidPrimaryKeyMixin, CreatedAtMixin, Base):
    __tablename__ = "ingestion_issues"
    __table_args__ = (
        Index("ix_ingestion_issues_file_id", "source_file_id"),
        Index("ix_ingestion_issues_raw_row_id", "raw_row_id"),
    )

    source_file_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("source_files.id", ondelete="CASCADE")
    )
    raw_row_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("raw_source_rows.id", ondelete="CASCADE")
    )
    field_name: Mapped[str | None] = mapped_column(Text)
    issue_type: Mapped[str] = mapped_column(Text, nullable=False)
    rejected_value: Mapped[str | None] = mapped_column(Text)
    reason: Mapped[str] = mapped_column(Text, nullable=False)


class Order(UuidPrimaryKeyMixin, Base):
    __tablename__ = "orders"
    __table_args__ = (
        UniqueConstraint("order_id", "merchant_id", "reconciliation_run_id"),
        Index("ix_orders_order_id", "order_id"),
        Index("ix_orders_merchant_id", "merchant_id"),
        Index("ix_orders_created_at", "order_created_at"),
        Index("ix_orders_run_id", "reconciliation_run_id"),
    )

    order_id: Mapped[str] = mapped_column(Text, nullable=False)
    merchant_id: Mapped[str] = mapped_column(Text, nullable=False)
    order_created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    order_amount_paise: Mapped[int] = mapped_column(BigInteger, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, server_default="INR")
    expected_payment_status: Mapped[str | None] = mapped_column(Text)
    raw_row_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("raw_source_rows.id"), nullable=False
    )
    reconciliation_run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("reconciliation_runs.id", ondelete="CASCADE"), nullable=False
    )


class Payment(UuidPrimaryKeyMixin, Base):
    __tablename__ = "payments"
    __table_args__ = (
        UniqueConstraint("payment_id", "merchant_id", "reconciliation_run_id"),
        Index("ix_payments_payment_id", "payment_id"),
        Index("ix_payments_order_id", "order_id"),
        Index("ix_payments_captured_at", "captured_at"),
        Index("ix_payments_run_id", "reconciliation_run_id"),
    )

    payment_id: Mapped[str] = mapped_column(Text, nullable=False)
    merchant_id: Mapped[str] = mapped_column(Text, nullable=False)
    order_id: Mapped[str] = mapped_column(Text, nullable=False)
    payment_status: Mapped[str] = mapped_column(Text, nullable=False)
    amount_paise: Mapped[int] = mapped_column(BigInteger, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, server_default="INR")
    captured_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    payment_method: Mapped[str | None] = mapped_column(Text)
    gateway_reference: Mapped[str | None] = mapped_column(Text)
    raw_row_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("raw_source_rows.id"), nullable=False
    )
    reconciliation_run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("reconciliation_runs.id", ondelete="CASCADE"), nullable=False
    )


class Settlement(UuidPrimaryKeyMixin, Base):
    __tablename__ = "settlements"
    __table_args__ = (
        UniqueConstraint("settlement_id", "merchant_id", "reconciliation_run_id"),
        Index("ix_settlements_settlement_id", "settlement_id"),
        Index("ix_settlements_utr", "utr"),
        Index("ix_settlements_initiated_at", "initiated_at"),
        Index("ix_settlements_run_id", "reconciliation_run_id"),
    )

    settlement_id: Mapped[str] = mapped_column(Text, nullable=False)
    merchant_id: Mapped[str] = mapped_column(Text, nullable=False)
    settlement_status: Mapped[str] = mapped_column(Text, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, server_default="INR")
    net_amount_paise: Mapped[int] = mapped_column(BigInteger, nullable=False)
    initiated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    expected_bank_date: Mapped[date | None] = mapped_column(Date)
    utr: Mapped[str | None] = mapped_column(Text)
    raw_row_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("raw_source_rows.id"), nullable=False
    )
    reconciliation_run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("reconciliation_runs.id", ondelete="CASCADE"), nullable=False
    )


class SettlementComponent(UuidPrimaryKeyMixin, Base):
    __tablename__ = "settlement_components"
    __table_args__ = (
        CheckConstraint("direction IN ('CREDIT', 'DEBIT')", name="ck_component_direction"),
        UniqueConstraint("component_id", "reconciliation_run_id"),
        Index("ix_components_component_id", "component_id"),
        Index("ix_components_settlement_id", "settlement_id"),
        Index("ix_components_source_event_id", "source_event_id"),
        Index("ix_components_run_id", "reconciliation_run_id"),
    )

    component_id: Mapped[str] = mapped_column(Text, nullable=False)
    settlement_id: Mapped[str] = mapped_column(Text, nullable=False)
    component_type: Mapped[str] = mapped_column(Text, nullable=False)
    source_event_id: Mapped[str] = mapped_column(Text, nullable=False)
    amount_paise: Mapped[int] = mapped_column(BigInteger, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, server_default="INR")
    direction: Mapped[str] = mapped_column(Text, nullable=False)
    raw_row_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("raw_source_rows.id"), nullable=False
    )
    reconciliation_run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("reconciliation_runs.id", ondelete="CASCADE"), nullable=False
    )


class BankTransaction(UuidPrimaryKeyMixin, Base):
    __tablename__ = "bank_transactions"
    __table_args__ = (
        CheckConstraint("direction IN ('CREDIT', 'DEBIT')", name="ck_bank_direction"),
        UniqueConstraint("bank_transaction_id", "merchant_id", "reconciliation_run_id"),
        Index("ix_bank_transactions_id", "bank_transaction_id"),
        Index("ix_bank_transactions_utr", "utr"),
        Index("ix_bank_transactions_posted_at", "posted_at"),
        Index("ix_bank_transactions_run_id", "reconciliation_run_id"),
    )

    bank_transaction_id: Mapped[str] = mapped_column(Text, nullable=False)
    merchant_id: Mapped[str] = mapped_column(Text, nullable=False)
    account_id: Mapped[str] = mapped_column(Text, nullable=False)
    posted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    value_date: Mapped[date] = mapped_column(Date, nullable=False)
    direction: Mapped[str] = mapped_column(Text, nullable=False)
    amount_paise: Mapped[int] = mapped_column(BigInteger, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, server_default="INR")
    narration: Mapped[str] = mapped_column(Text, nullable=False)
    utr: Mapped[str | None] = mapped_column(Text)
    raw_row_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("raw_source_rows.id"), nullable=False
    )
    reconciliation_run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("reconciliation_runs.id", ondelete="CASCADE"), nullable=False
    )


class ReconciliationCase(UuidPrimaryKeyMixin, CreatedAtMixin, Base):
    __tablename__ = "reconciliation_cases"
    __table_args__ = (
        UniqueConstraint("case_id", "reconciliation_run_id"),
        Index("ix_cases_case_id", "case_id"),
        Index("ix_cases_state", "case_state"),
        Index("ix_cases_exception_code", "exception_code"),
        Index("ix_cases_owner_role", "owner_role"),
        Index("ix_cases_run_id", "reconciliation_run_id"),
        Index("ix_cases_created_at", "created_at"),
    )

    case_id: Mapped[str] = mapped_column(Text, nullable=False)
    reconciliation_run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("reconciliation_runs.id", ondelete="CASCADE"), nullable=False
    )
    case_state: Mapped[str] = mapped_column(Text, nullable=False)
    decision_level: Mapped[str | None] = mapped_column(Text)
    gross_amount_paise: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    net_amount_paise: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    residual_paise: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, server_default="INR")
    exception_code: Mapped[str | None] = mapped_column(Text)
    exception_severity: Mapped[str | None] = mapped_column(Text)
    amount_at_risk_paise: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    cash_bucket: Mapped[str | None] = mapped_column(Text)
    settlement_id: Mapped[str | None] = mapped_column(Text)
    bank_receipt_state: Mapped[str | None] = mapped_column(Text)
    owner_role: Mapped[str | None] = mapped_column(Text)
    next_action: Mapped[str | None] = mapped_column(Text)
    ai_assisted: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    human_reviewed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    source_entity_ids: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False, default=list, server_default=text("'[]'::jsonb")
    )
    record_snapshot: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, nullable=False, default=list, server_default=text("'[]'::jsonb")
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )


class CandidateRelationship(UuidPrimaryKeyMixin, CreatedAtMixin, Base):
    __tablename__ = "candidate_relationships"
    __table_args__ = (
        CheckConstraint("match_score BETWEEN 0 AND 10000", name="ck_candidate_match_score_range"),
        Index("ix_candidates_run_id", "reconciliation_run_id"),
        Index("ix_candidates_source", "source_entity_id"),
        Index("ix_candidates_target", "target_entity_id"),
    )

    reconciliation_run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("reconciliation_runs.id", ondelete="CASCADE"), nullable=False
    )
    source_entity_id: Mapped[str] = mapped_column(Text, nullable=False)
    target_entity_id: Mapped[str] = mapped_column(Text, nullable=False)
    relationship_type: Mapped[str] = mapped_column(Text, nullable=False)
    match_score: Mapped[int | None] = mapped_column(Integer)  # Scaled 0-10000 (0.0000-1.0000)
    decision_level: Mapped[str] = mapped_column(Text, nullable=False)
    rejection_reason: Mapped[str | None] = mapped_column(Text)
    evidence_fields: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False, default=list, server_default=text("'[]'::jsonb")
    )
    allocated_amount_paise: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, server_default="INR")
    rule_id: Mapped[str | None] = mapped_column(Text)
    actor_type: Mapped[str] = mapped_column(Text, nullable=False, server_default="SYSTEM")


class EvidenceEdge(UuidPrimaryKeyMixin, CreatedAtMixin, Base):
    __tablename__ = "evidence_edges"
    __table_args__ = (
        UniqueConstraint(
            "reconciliation_run_id",
            "source_entity_id",
            "target_entity_id",
            "relationship_type",
            "rule_id",
        ),
        Index("ix_evidence_run_id", "reconciliation_run_id"),
        Index("ix_evidence_case_id", "case_id"),
        Index("ix_evidence_source", "source_entity_id"),
        Index("ix_evidence_target", "target_entity_id"),
    )

    reconciliation_run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("reconciliation_runs.id", ondelete="CASCADE"), nullable=False
    )
    case_id: Mapped[str] = mapped_column(Text, nullable=False)
    source_entity_id: Mapped[str] = mapped_column(Text, nullable=False)
    target_entity_id: Mapped[str] = mapped_column(Text, nullable=False)
    relationship_type: Mapped[str] = mapped_column(Text, nullable=False)
    allocated_amount_paise: Mapped[int] = mapped_column(BigInteger, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, server_default="INR")
    rule_id: Mapped[str] = mapped_column(Text, nullable=False)
    rule_version: Mapped[str] = mapped_column(Text, nullable=False)
    evidence_fields: Mapped[list[str]] = mapped_column(JSONB, nullable=False)
    decision_level: Mapped[str] = mapped_column(Text, nullable=False)
    actor_type: Mapped[str] = mapped_column(Text, nullable=False, server_default="SYSTEM")
    verification_checks: Mapped[list[dict[str, Any]] | None] = mapped_column(JSONB)


class InvariantResult(UuidPrimaryKeyMixin, CreatedAtMixin, Base):
    __tablename__ = "invariant_results"
    __table_args__ = (
        UniqueConstraint("reconciliation_run_id", "case_id", "invariant_id"),
        Index("ix_invariants_run_id", "reconciliation_run_id"),
        Index("ix_invariants_case_id", "case_id"),
    )

    reconciliation_run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("reconciliation_runs.id", ondelete="CASCADE"), nullable=False
    )
    case_id: Mapped[str] = mapped_column(Text, nullable=False)
    invariant_id: Mapped[str] = mapped_column(Text, nullable=False)
    passed: Mapped[bool] = mapped_column(Boolean, nullable=False)
    expected_value: Mapped[str | None] = mapped_column(Text)
    actual_value: Mapped[str | None] = mapped_column(Text)
    affected_entities: Mapped[list[str] | None] = mapped_column(JSONB)
    message: Mapped[str | None] = mapped_column(Text)


class ExceptionRecord(UuidPrimaryKeyMixin, CreatedAtMixin, Base):
    __tablename__ = "exceptions"
    __table_args__ = (
        UniqueConstraint("reconciliation_run_id", "case_id", "exception_code"),
        Index("ix_exceptions_run_id", "reconciliation_run_id"),
        Index("ix_exceptions_case_id", "case_id"),
        Index("ix_exceptions_code", "exception_code"),
    )

    reconciliation_run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("reconciliation_runs.id", ondelete="CASCADE"), nullable=False
    )
    case_id: Mapped[str] = mapped_column(Text, nullable=False)
    exception_code: Mapped[str] = mapped_column(Text, nullable=False)
    severity: Mapped[str] = mapped_column(Text, nullable=False)
    amount_at_risk_paise: Mapped[int] = mapped_column(BigInteger, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, server_default="INR")
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    checks_passed: Mapped[list[str] | None] = mapped_column(JSONB)
    checks_failed: Mapped[list[str] | None] = mapped_column(JSONB)
    missing_evidence: Mapped[list[str] | None] = mapped_column(JSONB)
    next_action: Mapped[str | None] = mapped_column(Text)
    owner_role: Mapped[str | None] = mapped_column(Text)
    ai_assisted: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    human_review_state: Mapped[str | None] = mapped_column(Text)
    due_date: Mapped[date | None] = mapped_column(Date)


class AIAnalysis(UuidPrimaryKeyMixin, CreatedAtMixin, Base):
    __tablename__ = "ai_analyses"
    __table_args__ = (
        Index("ix_ai_analyses_run_id", "reconciliation_run_id"),
        Index("ix_ai_analyses_case_id", "case_id"),
    )

    reconciliation_run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("reconciliation_runs.id", ondelete="CASCADE"), nullable=False
    )
    case_id: Mapped[str] = mapped_column(Text, nullable=False)
    evidence_packet: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    ai_response: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    ai_model: Mapped[str | None] = mapped_column(Text)
    ai_prompt_version: Mapped[str | None] = mapped_column(Text)
    provider: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default="UNKNOWN")
    tokens_prompt: Mapped[int | None] = mapped_column(Integer)
    tokens_completion: Mapped[int | None] = mapped_column(Integer)
    latency_ms: Mapped[int | None] = mapped_column(Integer)
    estimated_cost: Mapped[int] = mapped_column(
        BigInteger, nullable=False, default=0
    )  # Micro-dollars ($0.000001)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    validation_passed: Mapped[bool | None] = mapped_column(Boolean)
    validation_errors: Mapped[list[dict[str, Any]] | None] = mapped_column(JSONB)
    deterministic_checks: Mapped[list[dict[str, Any]] | None] = mapped_column(JSONB)
    error_type: Mapped[str | None] = mapped_column(Text)


class HumanDecision(UuidPrimaryKeyMixin, CreatedAtMixin, Base):
    __tablename__ = "human_decisions"
    __table_args__ = (
        Index("ix_human_decisions_run_id", "reconciliation_run_id"),
        Index("ix_human_decisions_case_id", "case_id"),
        Index("ix_human_decisions_created_at", "created_at"),
    )

    case_id: Mapped[str] = mapped_column(Text, nullable=False)
    reconciliation_run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("reconciliation_runs.id", ondelete="CASCADE"), nullable=False
    )
    execution_revision: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1, server_default="1"
    )
    review_revision: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    action: Mapped[str] = mapped_column(Text, nullable=False)
    actor: Mapped[str] = mapped_column(Text, nullable=False)
    previous_state: Mapped[str] = mapped_column(Text, nullable=False)
    new_state: Mapped[str] = mapped_column(Text, nullable=False)
    reason: Mapped[str | None] = mapped_column(Text)
    note: Mapped[str | None] = mapped_column(Text)
    invariant_passed: Mapped[bool | None] = mapped_column(Boolean)


class FollowUpTask(UuidPrimaryKeyMixin, CreatedAtMixin, Base):
    __tablename__ = "follow_up_tasks"
    __table_args__ = (
        Index("ix_follow_up_tasks_case_id", "case_id"),
        Index("ix_follow_up_tasks_status", "status"),
    )

    case_id: Mapped[str] = mapped_column(Text, nullable=False)
    reconciliation_run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("reconciliation_runs.id"), nullable=False, index=True
    )
    task_type: Mapped[str] = mapped_column(Text, nullable=False)
    amount_at_risk_paise: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, server_default="INR")
    required_evidence: Mapped[str | None] = mapped_column(Text)
    deadline: Mapped[date | None] = mapped_column(Date)
    action_code: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default="OPEN")


class AuditEvent(UuidPrimaryKeyMixin, CreatedAtMixin, Base):
    __tablename__ = "audit_events"
    __table_args__ = (
        Index("ix_audit_events_run_id", "reconciliation_run_id"),
        Index("ix_audit_events_case_id", "case_id"),
        Index("ix_audit_events_created_at", "created_at"),
        Index("ix_audit_events_event_type", "event_type"),
    )

    reconciliation_run_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("reconciliation_runs.id", ondelete="CASCADE")
    )
    case_id: Mapped[str | None] = mapped_column(Text)
    source_file_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("source_files.id", ondelete="SET NULL")
    )
    event_type: Mapped[str] = mapped_column(Text, nullable=False)
    stage: Mapped[str | None] = mapped_column(Text)
    rule_id: Mapped[str | None] = mapped_column(Text)
    severity: Mapped[str | None] = mapped_column(Text)
    details: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    actor: Mapped[str | None] = mapped_column(Text)
    duration_ms: Mapped[int | None] = mapped_column(BigInteger)


class CashPositionSnapshot(UuidPrimaryKeyMixin, CreatedAtMixin, Base):
    __tablename__ = "cash_position_snapshots"
    __table_args__ = (
        UniqueConstraint("reconciliation_run_id"),
        Index("ix_cash_position_run_id", "reconciliation_run_id"),
    )

    reconciliation_run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("reconciliation_runs.id", ondelete="CASCADE"), nullable=False
    )
    bank_confirmed_paise: Mapped[int] = mapped_column(BigInteger, nullable=False)
    settlement_confirmed_in_transit_paise: Mapped[int] = mapped_column(BigInteger, nullable=False)
    expected_settlement_paise: Mapped[int] = mapped_column(BigInteger, nullable=False)
    at_risk_paise: Mapped[int] = mapped_column(BigInteger, nullable=False)
    unresolved_paise: Mapped[int] = mapped_column(BigInteger, nullable=False)
    scheduled_refunds_paise: Mapped[int] = mapped_column(BigInteger, nullable=False)
    known_disputes_paise: Mapped[int] = mapped_column(BigInteger, nullable=False)
    known_reserve_holds_paise: Mapped[int] = mapped_column(BigInteger, nullable=False)
    safe_cash_paise: Mapped[int] = mapped_column(BigInteger, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, server_default="INR")
    buckets: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)


class IdempotencyRecord(UuidPrimaryKeyMixin, CreatedAtMixin, Base):
    __tablename__ = "idempotency_records"
    __table_args__ = (
        CheckConstraint(
            "state IN ('IN_PROGRESS', 'COMPLETED')", name="ck_idempotency_state"
        ),
        UniqueConstraint("scope", "idempotency_key"),
        Index("ix_idempotency_created_at", "created_at"),
        Index("ix_idempotency_lease", "state", "lease_expires_at"),
    )

    scope: Mapped[str] = mapped_column(Text, nullable=False)
    idempotency_key: Mapped[str] = mapped_column(Text, nullable=False)
    request_checksum: Mapped[str] = mapped_column(Text, nullable=False)
    response_status: Mapped[int] = mapped_column(Integer, nullable=False)
    response_payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    state: Mapped[str] = mapped_column(
        Text, nullable=False, default="COMPLETED", server_default="COMPLETED"
    )
    claim_token: Mapped[str | None] = mapped_column(Text)
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
