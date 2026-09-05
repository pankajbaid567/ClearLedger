"""Durable orchestration around the deterministic Phase 2 engine."""

from __future__ import annotations

import asyncio
import csv
import hashlib
import io
import json
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from fastapi import UploadFile
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import ReconciliationRun, SourceFile
from db.repositories import (
    AuditRepository,
    CaseRepository,
    EntityRepository,
    RunRepository,
    SourceRepository,
)
from generator.schemas import (
    BankTransactionRecord,
    OrderRecord,
    PaymentRecord,
    SettlementComponentRecord,
    SettlementRecord,
)
from packages.domain.enums import CaseState, DecisionLevel, IngestionQuality
from services.ai_analyst.client import AIAnalyzerClient
from services.ai_analyst.fallback import ai_disabled_metrics
from services.ai_analyst.schemas import AIClientConfig
from services.ai_analyst.service import AIAnalystService
from services.normalization.policy import SettlementPolicy, load_policy
from services.reconciliation.evidence import EvidenceEdge
from services.reconciliation.models import (
    IngestionResult,
    RawSourceRow,
    ReconciliationResult,
)
from services.reconciliation.orchestrator import (
    run_reconciliation,
    select_ai_analysis_cases,
    to_prediction_report,
)
from services.reconciliation.rules import RULE_VERSION

REQUIRED_SOURCE_TYPES = frozenset(
    {"orders", "payments", "settlements", "settlement_components", "bank_transactions"}
)
APP_VERSION = "0.1.0"


class RunServiceError(Exception):
    def __init__(
        self,
        code: str,
        message: str,
        *,
        status_code: int = 400,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code
        self.details = details or {}


class FileValidation(BaseModel):
    model_config = ConfigDict(strict=True)

    source_type: str
    filename: str
    quality: IngestionQuality
    row_count: int
    accepted_count: int
    rejected_count: int
    control_total_paise: int = 0
    errors: list[dict[str, Any]] = Field(default_factory=list)


class ValidationResult(BaseModel):
    model_config = ConfigDict(strict=True)

    run_id: uuid.UUID
    valid: bool
    missing_source_types: list[str] = Field(default_factory=list)
    files: list[FileValidation] = Field(default_factory=list)
    total_rows: int = 0
    invalid_rows: int = 0


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _stable_checksum(value: Any) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    return _sha256(encoded)


def _quality_for_result(result: IngestionResult) -> IngestionQuality:
    if result.file_errors or (
        result.metadata.rejected_count and not result.metadata.accepted_count
    ):
        return IngestionQuality.INVALID
    if result.metadata.rejected_count:
        return IngestionQuality.PARTIAL
    return IngestionQuality.VALID


def _control_total_paise(result: IngestionResult) -> int:
    total = 0
    for row in result.accepted_rows:
        record = row.record
        if record is None:
            continue
        for field_name in ("order_amount_paise", "net_amount_paise", "amount_paise"):
            value = getattr(record, field_name, None)
            if value is not None:
                total += abs(int(value))
                break
    return total


def _result_currency(result: ReconciliationResult) -> str:
    return next(
        (record.currency for record in result.normalized_records if record.currency),
        "INR",
    )


class RunService:
    """Coordinates uploads, validation, execution, and durable result replacement."""

    def __init__(
        self,
        session: AsyncSession,
        *,
        upload_dir: str | Path,
        policy_path: str | Path | None = None,
        max_upload_bytes: int = 10 * 1024 * 1024,
        ai_config: AIClientConfig | None = None,
        ai_client: AIAnalyzerClient | None = None,
    ) -> None:
        self.session = session
        self.upload_dir = Path(upload_dir)
        self.policy_path = Path(policy_path) if policy_path else None
        self.max_upload_bytes = max_upload_bytes
        self.ai_config = ai_config or AIClientConfig()
        self.ai_client = ai_client
        self.runs = RunRepository(session)
        self.sources = SourceRepository(session)
        self.entities = EntityRepository(session)
        self.cases = CaseRepository(session)
        self.audit = AuditRepository(session)

    async def create_run(self, policy_version_id: uuid.UUID | None = None) -> ReconciliationRun:
        if policy_version_id is None:
            policy_version_id = (await self._ensure_default_policy()).id
        elif await self.runs.get_policy(policy_version_id) is None:
            raise RunServiceError(
                "POLICY_NOT_FOUND",
                "The requested policy version does not exist.",
                status_code=404,
                details={"policy_version_id": str(policy_version_id)},
            )

        run = await self.runs.create(
            policy_version_id=policy_version_id,
            status="CREATED",
            rule_set_version=RULE_VERSION,
            app_version=APP_VERSION,
            ai_model=self.ai_config.model or None,
            ai_prompt_version=self.ai_config.prompt_version,
            config={
                "required_source_types": sorted(REQUIRED_SOURCE_TYPES),
                "ai_enabled": self.ai_config.enabled,
                "ai_provider": self.ai_config.provider,
            },
        )
        await self.audit.create(
            reconciliation_run_id=run.id,
            event_type="RUN_CREATED",
            stage="creation",
            actor="SYSTEM",
            details={"policy_version_id": str(policy_version_id)},
        )
        return run

    async def add_files_to_run(
        self, run_id: uuid.UUID, files: dict[str, UploadFile]
    ) -> list[SourceFile]:
        run = await self._require_run(run_id)
        if run.status in {"RECONCILING"}:
            raise RunServiceError(
                "INVALID_STATE_TRANSITION",
                "Files cannot be changed while reconciliation is running.",
                status_code=409,
                details={"run_id": str(run_id), "current_state": run.status},
            )

        run_dir = self.upload_dir / str(run_id)
        run_dir.mkdir(parents=True, exist_ok=True)
        uploaded: list[SourceFile] = []
        for source_type, upload in sorted(files.items()):
            if source_type not in REQUIRED_SOURCE_TYPES:
                raise RunServiceError(
                    "UNSUPPORTED_SOURCE_TYPE",
                    f"Unsupported source type: {source_type}.",
                    details={"source_type": source_type},
                )
            if not (upload.filename or "").lower().endswith(".csv"):
                raise RunServiceError(
                    "INVALID_FILE_TYPE",
                    "Only CSV source files are accepted.",
                    details={"filename": upload.filename, "source_type": source_type},
                )
            data = await upload.read()
            if len(data) > self.max_upload_bytes:
                raise RunServiceError(
                    "FILE_TOO_LARGE",
                    "The uploaded file exceeds the configured size limit.",
                    status_code=413,
                    details={"source_type": source_type, "max_bytes": self.max_upload_bytes},
                )
            checksum = _sha256(data)
            existing = await self.sources.get_for_run_type(run_id, source_type)
            if existing is not None:
                if existing.file_checksum == checksum:
                    raise RunServiceError(
                        "DUPLICATE_UPLOAD",
                        "This source file is already registered for the run.",
                        status_code=409,
                        details={
                            "source_type": source_type,
                            "source_file_id": str(existing.id),
                            "checksum": checksum,
                        },
                    )
                raise RunServiceError(
                    "IMMUTABLE_SOURCE_FILE",
                    "A different file is already registered for this source type; "
                    "create a new run.",
                    status_code=409,
                    details={"source_type": source_type, "source_file_id": str(existing.id)},
                )

            try:
                decoded = data.decode("utf-8-sig")
                row_count = sum(1 for _ in csv.DictReader(io.StringIO(decoded)))
            except UnicodeDecodeError as exc:
                raise RunServiceError(
                    "INVALID_FILE_ENCODING",
                    "CSV files must use UTF-8 encoding.",
                    details={"source_type": source_type},
                ) from exc

            path = run_dir / f"{source_type}.csv"
            path.write_bytes(data)
            source_file = await self.sources.create(
                filename=upload.filename or path.name,
                source_type=source_type,
                file_checksum=checksum,
                file_size_bytes=len(data),
                row_count=row_count,
                ingestion_quality=IngestionQuality.PARTIAL.value,
                reconciliation_run_id=run_id,
            )
            await self.audit.create(
                reconciliation_run_id=run_id,
                source_file_id=source_file.id,
                event_type="SOURCE_FILE_ADDED",
                stage="upload",
                actor="SYSTEM",
                details={
                    "source_type": source_type,
                    "filename": upload.filename,
                    "checksum": checksum,
                    "size_bytes": len(data),
                    "row_count": row_count,
                },
            )
            uploaded.append(source_file)

        all_files = await self.sources.list_for_run(run_id)
        dataset_checksum = _stable_checksum(
            {item.source_type: item.file_checksum for item in all_files}
        )
        dataset_manifest = self._dataset_manifest(all_files, dataset_checksum)
        (run_dir / "dataset_manifest.json").write_text(
            json.dumps(dataset_manifest, indent=2) + "\n"
        )
        await self.runs.update(
            run,
            status="FILES_UPLOADED",
            dataset_checksum=dataset_checksum,
            total_source_rows=sum(item.row_count or 0 for item in all_files),
            config={**run.config, "dataset_id": dataset_manifest["dataset_id"]},
        )
        return uploaded

    async def validate_run(self, run_id: uuid.UUID) -> ValidationResult:
        run = await self._require_run(run_id)
        source_files = await self.sources.list_for_run(run_id)
        by_type = {item.source_type: item for item in source_files}
        missing = sorted(REQUIRED_SOURCE_TYPES - by_type.keys())
        validations: list[FileValidation] = []
        invalid_rows = 0
        if not missing:
            from services.ingestion.service import ingest_file

            for source_type in sorted(REQUIRED_SOURCE_TYPES):
                source_file = by_type[source_type]
                result = await asyncio.to_thread(
                    ingest_file, str(self._file_path(run_id, source_type)), source_type
                )
                quality = _quality_for_result(result)
                invalid_rows += result.metadata.rejected_count
                errors = [issue.model_dump(mode="json") for issue in result.file_errors]
                errors.extend(
                    issue.model_dump(mode="json")
                    for row in result.rejected_rows
                    for issue in row.issues
                )
                validations.append(
                    FileValidation(
                        source_type=source_type,
                        filename=source_file.filename,
                        quality=quality,
                        row_count=result.metadata.row_count,
                        accepted_count=result.metadata.accepted_count,
                        rejected_count=result.metadata.rejected_count,
                        control_total_paise=_control_total_paise(result),
                        errors=errors,
                    )
                )
                await self.sources.update(
                    source_file,
                    ingestion_quality=quality.value,
                    row_count=result.metadata.row_count,
                )

        valid = not missing and all(
            item.quality != IngestionQuality.INVALID for item in validations
        )
        await self.runs.update(
            run,
            status="READY_FOR_RECONCILIATION" if valid else "VALIDATION_FAILED",
            failure_reason=(
                None if valid else "Missing required files or one or more files failed validation."
            ),
        )
        result = ValidationResult(
            run_id=run_id,
            valid=valid,
            missing_source_types=missing,
            files=validations,
            total_rows=sum(item.row_count for item in validations),
            invalid_rows=invalid_rows,
        )
        await self.audit.create(
            reconciliation_run_id=run_id,
            event_type="RUN_VALIDATED",
            stage="validation",
            severity="INFO" if valid else "ERROR",
            actor="SYSTEM",
            details=result.model_dump(mode="json"),
        )
        return result

    async def execute_reconciliation(self, run_id: uuid.UUID) -> ReconciliationResult:
        run = await self.runs.get_for_update(run_id)
        if run is None:
            raise self._not_found(run_id)
        validation = await self.validate_run(run_id)
        if not validation.valid:
            raise RunServiceError(
                "RUN_VALIDATION_FAILED",
                "The run must have all required source files and valid schemas.",
                status_code=409,
                details=validation.model_dump(mode="json"),
            )

        policy = await self._policy_for_run(run)
        source_files = {
            source_type: str(self._file_path(run_id, source_type))
            for source_type in REQUIRED_SOURCE_TYPES
        }
        started_at = datetime.now(UTC)
        await self.runs.update(
            run,
            status="RECONCILING",
            started_at=started_at,
            completed_at=None,
            failure_reason=None,
        )
        await self.audit.create(
            reconciliation_run_id=run_id,
            event_type="RECONCILIATION_STARTED",
            stage="orchestration",
            actor="SYSTEM",
            details={"dataset_checksum": run.dataset_checksum},
        )

        try:
            result = await asyncio.to_thread(run_reconciliation, source_files, policy, str(run_id))
            await self._persist_result(run, result)
            await self._run_ai_stage(run, result, policy)
            await self.session.flush()
            return result
        except Exception as exc:
            await self.session.rollback()
            failed_run = await self.runs.get(run_id)
            if failed_run is not None:
                await self.runs.update(
                    failed_run,
                    status="FAILED",
                    completed_at=datetime.now(UTC),
                    failure_reason=str(exc)[:1000],
                )
                await self.audit.create(
                    reconciliation_run_id=run_id,
                    event_type="RECONCILIATION_FAILED",
                    stage="orchestration",
                    severity="ERROR",
                    actor="SYSTEM",
                    details={"error_type": type(exc).__name__, "message": str(exc)[:1000]},
                )
                await self.session.commit()
            raise

    async def _run_ai_stage(
        self,
        run: ReconciliationRun,
        result: ReconciliationResult,
        policy: SettlementPolicy,
    ) -> None:
        eligible_cases = select_ai_analysis_cases(result.cases)[: self.ai_config.max_cases_per_run]
        eligible_ids = [case.case_id for case in eligible_cases]
        baseline_states = self._state_counts(result.cases)
        if self.ai_config.enabled:
            service = AIAnalystService(
                self.session,
                config=self.ai_config,
                policy=policy,
                client=self.ai_client,
            )
            prepared = await service.prepare_cases(run.id, eligible_ids)
            await service.analyze_unresolved_cases(
                run.id,
                prepared,
                total_cases=len(result.cases),
            )
            ai_metrics = service.metrics
            from services.reconciliation.review_service import ReviewService

            await ReviewService(self.session).recalculate_aggregates(run.id)
        else:
            ai_metrics = ai_disabled_metrics(
                total_cases=len(result.cases),
                eligible_cases=len(eligible_ids),
            )

        persisted_cases, _ = await self.cases.list_cases(run.id, limit=10_000)
        assisted_states: dict[str, int] = {}
        for case in persisted_cases:
            assisted_states[case.case_state] = assisted_states.get(case.case_state, 0) + 1
        current_run = await self.runs.get(run.id)
        if current_run is None:
            raise RuntimeError("Reconciliation run disappeared during AI analysis")
        metrics = {
            **current_run.metrics,
            "ai": ai_metrics.model_dump(mode="json"),
            "ablation": {
                "eligible_case_ids": eligible_ids,
                "deterministic_only": {"cases_by_state": baseline_states},
                "deterministic_plus_ai": {"cases_by_state": assisted_states},
            },
        }
        await self.runs.update(
            current_run,
            status="COMPLETED",
            metrics=metrics,
            ai_model=self.ai_config.model or None,
            ai_prompt_version=self.ai_config.prompt_version,
        )
        await self.audit.create(
            reconciliation_run_id=run.id,
            event_type="AI_STAGE_COMPLETED" if self.ai_config.enabled else "AI_STAGE_SKIPPED",
            stage="ai_exception_analysis",
            severity="INFO" if not ai_metrics.warnings else "WARNING",
            actor="SYSTEM",
            details={
                "enabled": self.ai_config.enabled,
                "eligible_cases": len(eligible_ids),
                "calls": ai_metrics.calls,
                "cases_improved": ai_metrics.cases_improved,
                "rejected_outputs": ai_metrics.rejected_outputs,
                "warnings": ai_metrics.warnings,
            },
        )

    @staticmethod
    def _state_counts(cases: list[Any]) -> dict[str, int]:
        counts: dict[str, int] = {}
        for case in cases:
            state = case.case_state.value if hasattr(case.case_state, "value") else case.case_state
            counts[state] = counts.get(state, 0) + 1
        return counts

    async def _persist_result(self, run: ReconciliationRun, result: ReconciliationResult) -> None:
        run_id = run.id
        await self.cases.clear_for_run(run_id)
        raw_row_ids = await self._persist_source_data(run_id, result.ingestion_results)

        edge_keys = {
            (edge.source_entity_id, edge.target_entity_id, edge.relationship_type)
            for edge in result.evidence_edges
            if isinstance(edge, EvidenceEdge)
        }
        rejected_reasons: dict[tuple[str, str, str, str], list[str]] = {}
        for rejected in result.rejected_candidates + result.ambiguous_candidates:
            rejected_reasons[
                (
                    rejected.source_entity_id,
                    rejected.target_entity_id,
                    rejected.relationship_type,
                    rejected.rule_id,
                )
            ] = rejected.rejected_reasons
        for candidate in result.candidates:
            key = (
                candidate.source_entity_id,
                candidate.target_entity_id,
                candidate.relationship_type,
            )
            reasons = rejected_reasons.get(
                (
                    candidate.source_entity_id,
                    candidate.target_entity_id,
                    candidate.relationship_type,
                    candidate.rule_id,
                ),
                candidate.rejected_reasons,
            )
            if key in edge_keys:
                decision = DecisionLevel.VERIFIED.value
            elif reasons:
                decision = DecisionLevel.REJECTED.value
            else:
                decision = DecisionLevel.UNRESOLVED.value
            await self.cases.create_candidate(
                reconciliation_run_id=run_id,
                source_entity_id=candidate.source_entity_id,
                target_entity_id=candidate.target_entity_id,
                relationship_type=candidate.relationship_type,
                match_score=int(candidate.match_strength_score * 10000),  # Scale to 0-10000
                decision_level=decision,
                rejection_reason="; ".join(reasons) or None,
                evidence_fields=candidate.evidence_fields,
                allocated_amount_paise=candidate.allocated_amount_paise,
                currency=_result_currency(result),
                rule_id=candidate.rule_id,
            )

        exception_by_case = {item.case_id: item for item in result.exceptions}
        case_by_entity: dict[str, str] = {}
        for case in result.cases:
            structured_exception = exception_by_case.get(case.case_id)
            settlement_ids = [
                record.settlement_id
                for record in case.records
                if record.source_type == "settlements" and record.settlement_id
            ]
            has_bank_edge = any(
                isinstance(edge, EvidenceEdge)
                and edge.relationship_type == "settlement_bank"
                and edge.source_entity_id in case.source_entity_ids
                for edge in result.evidence_edges
            )
            await self.cases.create_case(
                case_id=case.case_id,
                reconciliation_run_id=run_id,
                case_state=case.case_state.value,
                decision_level=(
                    DecisionLevel.VERIFIED.value
                    if case.case_state == CaseState.RECONCILED
                    else DecisionLevel.UNRESOLVED.value
                ),
                gross_amount_paise=case.gross_amount_paise,
                net_amount_paise=case.net_amount_paise,
                residual_paise=case.residual_paise,
                currency=_result_currency(result),
                exception_code=case.exception_code.value if case.exception_code else None,
                exception_severity=(
                    structured_exception.severity.value if structured_exception else None
                ),
                amount_at_risk_paise=(
                    structured_exception.amount_at_risk_paise
                    if structured_exception
                    else abs(case.residual_paise)
                ),
                cash_bucket=case.cash_bucket.value,
                settlement_id=",".join(sorted(set(settlement_ids))) or None,
                bank_receipt_state=(
                    "CONFIRMED"
                    if has_bank_edge
                    else "MISSING"
                    if settlement_ids
                    else "NOT_APPLICABLE"
                ),
                owner_role=structured_exception.owner_role if structured_exception else None,
                next_action=structured_exception.next_action if structured_exception else None,
                ai_assisted=False,
                human_reviewed=False,
                source_entity_ids=case.source_entity_ids,
                record_snapshot=[record.model_dump(mode="json") for record in case.records],
            )
            for entity_id in case.source_entity_ids:
                case_by_entity[entity_id] = case.case_id

            for invariant in case.invariant_results:
                await self.cases.create_invariant_result(
                    reconciliation_run_id=run_id,
                    case_id=case.case_id,
                    invariant_id=invariant.invariant_id,
                    passed=invariant.passed,
                    expected_value=(
                        None if invariant.expected_value is None else str(invariant.expected_value)
                    ),
                    actual_value=(
                        None if invariant.actual_value is None else str(invariant.actual_value)
                    ),
                    affected_entities=invariant.affected_entities,
                    message=invariant.message,
                )

        for edge in result.evidence_edges:
            if not isinstance(edge, EvidenceEdge):
                continue
            case_id = case_by_entity.get(edge.source_entity_id) or case_by_entity.get(
                edge.target_entity_id
            )
            if case_id is None:
                raise RuntimeError("Evidence edge does not belong to a reconciliation case")
            await self.cases.create_evidence_edge(
                reconciliation_run_id=run_id,
                case_id=case_id,
                source_entity_id=edge.source_entity_id,
                target_entity_id=edge.target_entity_id,
                relationship_type=edge.relationship_type,
                allocated_amount_paise=edge.allocated_amount_paise,
                currency=_result_currency(result),
                rule_id=edge.rule_id,
                rule_version=edge.rule_version,
                evidence_fields=edge.evidence_fields,
                decision_level=edge.decision_level.value,
                actor_type=edge.actor_type.value,
                verification_checks=[
                    check.model_dump(mode="json") for check in edge.verification_checks
                ],
            )

        for item in result.exceptions:
            await self.cases.create_exception(
                reconciliation_run_id=run_id,
                case_id=item.case_id,
                exception_code=item.code.value,
                severity=item.severity.value,
                amount_at_risk_paise=item.amount_at_risk_paise,
                currency=_result_currency(result),
                summary=item.summary,
                checks_passed=item.checks_passed,
                checks_failed=item.checks_failed,
                missing_evidence=item.missing_evidence,
                next_action=item.next_action,
                owner_role=item.owner_role,
                ai_assisted=item.ai_assisted,
            )

        cash = result.cash_position.model_dump(mode="json")
        await self.cases.create_cash_position(
            reconciliation_run_id=run_id,
            bank_confirmed_paise=result.cash_position.bank_confirmed_paise,
            settlement_confirmed_in_transit_paise=(
                result.cash_position.settlement_confirmed_in_transit_paise
            ),
            expected_settlement_paise=result.cash_position.expected_settlement_paise,
            at_risk_paise=result.cash_position.at_risk_paise,
            unresolved_paise=result.cash_position.unresolved_paise,
            scheduled_refunds_paise=result.cash_position.scheduled_refunds_paise,
            known_disputes_paise=result.cash_position.known_disputes_paise,
            known_reserve_holds_paise=result.cash_position.known_reserve_holds_paise,
            safe_cash_paise=result.cash_position.safe_cash_paise,
            currency=_result_currency(result),
            buckets=cash["buckets"],
        )

        prediction = to_prediction_report(result).model_dump(mode="json")
        deterministic_payload = {
            "dataset_id": prediction["dataset_id"],
            "cases": prediction["cases"],
            "cash_position": cash,
            "policy_version_id": str(run.policy_version_id),
            "rule_set_version": RULE_VERSION,
        }
        result_checksum = _stable_checksum(deterministic_payload)
        completed_at = datetime.now(UTC)
        metrics = dict(result.metrics)
        metrics.update(
            {
                "duration_seconds": result.duration_seconds,
                "total_source_records": result.total_source_records,
                "result_checksum": result_checksum,
                "stage_timings": [
                    timing.model_dump(mode="json") for timing in result.stage_timings
                ],
            }
        )
        await self.runs.update(
            run,
            status="COMPLETED",
            completed_at=completed_at,
            duration_ms=int(result.duration_seconds * 1000),
            total_source_rows=result.total_source_records,
            total_cases=len(result.cases),
            metrics=metrics,
            cash_position=cash,
            evaluation={},
            result_checksum=result_checksum,
            config={**run.config, "prediction_report": prediction},
        )
        for timing in result.stage_timings:
            await self.audit.create(
                reconciliation_run_id=run_id,
                event_type="STAGE_COMPLETED",
                stage=timing.stage,
                actor="SYSTEM",
                duration_ms=round(timing.duration_seconds * 1000),
                details={"duration_seconds": timing.duration_seconds},
            )
        await self.audit.create(
            reconciliation_run_id=run_id,
            event_type="RECONCILIATION_COMPLETED",
            stage="orchestration",
            actor="SYSTEM",
            duration_ms=int(result.duration_seconds * 1000),
            details={
                "total_cases": len(result.cases),
                "evidence_edges": len(result.evidence_edges),
                "result_checksum": result_checksum,
                "raw_rows_persisted": len(raw_row_ids),
            },
        )

    async def _persist_source_data(
        self, run_id: uuid.UUID, ingestion_results: list[IngestionResult]
    ) -> dict[tuple[str, int], uuid.UUID]:
        source_files = {item.source_type: item for item in await self.sources.list_for_run(run_id)}
        existing_map: dict[tuple[str, int], uuid.UUID] = {}
        for source_type, source_file in source_files.items():
            for row in await self.sources.list_rows(source_file.id):
                existing_map[(source_type, row.row_number)] = row.id
        if existing_map:
            return existing_map

        for result in ingestion_results:
            source_type = result.metadata.detected_source_type
            source_file = source_files[source_type]
            all_rows = result.accepted_rows + result.rejected_rows
            for row in sorted(all_rows, key=lambda item: item.row_number):
                raw = await self.sources.create_raw_row(
                    source_file_id=source_file.id,
                    row_number=row.row_number,
                    raw_payload=row.raw_values,
                    quality=row.quality.value,
                    validation_errors=[issue.model_dump(mode="json") for issue in row.issues]
                    or None,
                )
                existing_map[(source_type, row.row_number)] = raw.id
                for issue in row.issues:
                    await self.sources.create_issue(
                        source_file_id=source_file.id,
                        raw_row_id=raw.id,
                        field_name=issue.field,
                        issue_type=issue.code.value if issue.code else "VALIDATION_ERROR",
                        rejected_value=issue.value,
                        reason=issue.reason,
                    )
            for issue in result.file_errors:
                await self.sources.create_issue(
                    source_file_id=source_file.id,
                    field_name=issue.field,
                    issue_type=issue.code.value if issue.code else "FILE_VALIDATION_ERROR",
                    rejected_value=issue.value,
                    reason=issue.reason,
                )

        for result in ingestion_results:
            for row in result.accepted_rows:
                await self._persist_entity(
                    run_id,
                    row,
                    existing_map[(row.source_type, row.row_number)],
                )
        return existing_map

    async def _persist_entity(
        self, run_id: uuid.UUID, row: RawSourceRow, raw_row_id: uuid.UUID
    ) -> None:
        record = row.record
        if isinstance(record, OrderRecord):
            await self.entities.create_order(
                **record.model_dump(mode="python"),
                raw_row_id=raw_row_id,
                reconciliation_run_id=run_id,
            )
        elif isinstance(record, PaymentRecord):
            await self.entities.create_payment(
                **record.model_dump(mode="python"),
                raw_row_id=raw_row_id,
                reconciliation_run_id=run_id,
            )
        elif isinstance(record, SettlementRecord):
            await self.entities.create_settlement(
                **record.model_dump(mode="python"),
                raw_row_id=raw_row_id,
                reconciliation_run_id=run_id,
            )
        elif isinstance(record, SettlementComponentRecord):
            values = record.model_dump(mode="python")
            values["currency"] = "INR"
            await self.entities.create_settlement_component(
                **values,
                raw_row_id=raw_row_id,
                reconciliation_run_id=run_id,
            )
        elif isinstance(record, BankTransactionRecord):
            await self.entities.create_bank_transaction(
                **record.model_dump(mode="python"),
                raw_row_id=raw_row_id,
                reconciliation_run_id=run_id,
            )

    async def _ensure_default_policy(self) -> Any:
        policy = load_policy(self.policy_path)
        existing = await self.runs.get_policy_by_version(policy.policy_id, policy.version)
        if existing is not None:
            if existing.policy_checksum != policy.checksum_sha256:
                raise RunServiceError(
                    "POLICY_CHECKSUM_CONFLICT",
                    "The stored policy version has a different checksum.",
                    status_code=409,
                    details={"policy_id": policy.policy_id, "version": policy.version},
                )
            return existing
        return await self.runs.create_policy(
            policy_id=policy.policy_id,
            version=policy.version,
            policy_checksum=policy.checksum_sha256,
            policy_data=policy.model_dump(mode="json"),
        )

    async def _policy_for_run(self, run: ReconciliationRun) -> SettlementPolicy:
        if run.policy_version_id is None:
            raise RunServiceError("POLICY_NOT_FOUND", "The run has no policy version.")
        stored = await self.runs.get_policy(run.policy_version_id)
        if stored is None:
            raise RunServiceError("POLICY_NOT_FOUND", "The run policy no longer exists.")
        return SettlementPolicy.model_validate(stored.policy_data)

    async def _require_run(self, run_id: uuid.UUID) -> ReconciliationRun:
        run = await self.runs.get(run_id)
        if run is None:
            raise self._not_found(run_id)
        return run

    def _not_found(self, run_id: uuid.UUID) -> RunServiceError:
        return RunServiceError(
            "RUN_NOT_FOUND",
            "The requested reconciliation run was not found.",
            status_code=404,
            details={"run_id": str(run_id)},
        )

    def _file_path(self, run_id: uuid.UUID, source_type: str) -> Path:
        return self.upload_dir / str(run_id) / f"{source_type}.csv"

    def _dataset_manifest(
        self, source_files: list[SourceFile], dataset_checksum: str
    ) -> dict[str, Any]:
        checksums = {f"{item.source_type}.csv": item.file_checksum for item in source_files}
        project_root = (
            self.policy_path.resolve().parent.parent
            if self.policy_path
            else Path(__file__).resolve().parents[2]
        )
        for manifest_path in sorted((project_root / "data").glob("*/dataset_manifest.json")):
            manifest = json.loads(manifest_path.read_text())
            if manifest.get("file_checksums") == checksums:
                return manifest
        return {
            "dataset_id": f"upload_{dataset_checksum[:12]}",
            "file_checksums": checksums,
        }
