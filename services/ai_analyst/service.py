"""Persistent, bounded AI exception analysis after deterministic reconciliation."""

from __future__ import annotations

import json
import logging
import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from db.models import (
    CandidateRelationship as DBCandidateRelationship,
)
from db.models import (
    EvidenceEdge as DBEvidenceEdge,
)
from db.models import (
    ReconciliationCase as DBReconciliationCase,
)
from db.repositories import AuditRepository, CaseRepository, ReviewRepository
from packages.domain.enums import (
    ActorType,
    CaseState,
    CashBucket,
    DecisionLevel,
    ExceptionCode,
)
from services.ai_analyst.client import AIAnalyzerClient, OpenAICompatibleClient
from services.ai_analyst.evidence_packet import (
    AIEvidencePacket,
    EvidencePacketTooLarge,
    build_evidence_packet,
    candidate_id,
)
from services.ai_analyst.fallback import AIUsageMetrics
from services.ai_analyst.mock_client import MockAIClient
from services.ai_analyst.schemas import (
    AIAnalysisOutcome,
    AIClientConfig,
    AIClientResult,
    ValidationResult,
)
from services.ai_analyst.validator import validate_ai_response
from services.normalization.policy import SettlementPolicy
from services.reconciliation.evidence import EvidenceEdge
from services.reconciliation.invariants import verify_suggested_relationship
from services.reconciliation.models import (
    CandidateRelationship,
    InvariantResult,
    NormalizedRecord,
    ReconciliationCase,
    VerificationCheck,
)

logger = logging.getLogger(__name__)


class AIAnalystService:
    """Invokes AI only for eligible unresolved cases and persists an audit trail."""

    def __init__(
        self,
        session: AsyncSession,
        *,
        config: AIClientConfig,
        policy: SettlementPolicy,
        client: AIAnalyzerClient | None = None,
    ) -> None:
        self.session = session
        self.config = config
        self.policy = policy
        if client is not None:
            self.client = client
        elif config.provider.casefold() in {"mock", "offline", "demo"}:
            self.client = MockAIClient(config)
        else:
            self.client = OpenAICompatibleClient(config)
        self.cases = CaseRepository(session)
        self.reviews = ReviewRepository(session)
        self.audit = AuditRepository(session)
        self.metrics = AIUsageMetrics(enabled=config.enabled, mode="AI_ASSISTED")

    @staticmethod
    def is_eligible(case: DBReconciliationCase) -> bool:
        return (
            case.case_state
            in {CaseState.ACTIONABLE_EXCEPTION.value, CaseState.NEEDS_ANALYSIS.value}
            and case.exception_code == ExceptionCode.AMBIGUOUS_CANDIDATES.value
        )

    async def prepare_cases(
        self,
        run_id: uuid.UUID,
        case_ids: list[str],
    ) -> list[DBReconciliationCase]:
        prepared: list[DBReconciliationCase] = []
        for case_id_value in case_ids:
            case = await self.cases.get_case(case_id_value, run_id)
            if case is None or not self.is_eligible(case):
                continue
            if case.case_state != CaseState.NEEDS_ANALYSIS.value:
                await self.cases.update_case(
                    case,
                    case_state=CaseState.NEEDS_ANALYSIS.value,
                    decision_level=DecisionLevel.UNRESOLVED.value,
                    ai_assisted=False,
                )
            prepared.append(case)
        return prepared

    async def analyze_unresolved_cases(
        self,
        run_id: uuid.UUID,
        cases: list[DBReconciliationCase],
        *,
        total_cases: int | None = None,
    ) -> list[AIAnalysisOutcome]:
        eligible = [
            case
            for case in cases
            if case.reconciliation_run_id == run_id
            and case.case_state == CaseState.NEEDS_ANALYSIS.value
            and self.is_eligible(case)
        ]
        self.metrics = AIUsageMetrics(
            enabled=True,
            mode="AI_ASSISTED",
            eligible_cases=len(eligible),
            skipped_clean_cases=max((total_cases or len(cases)) - len(eligible), 0),
            deterministic_only=True,
        )
        outcomes: list[AIAnalysisOutcome] = []
        for case in eligible:
            outcomes.append(await self._analyze_one(case))
        self.metrics.finalize()
        return outcomes

    async def analyze_single(self, case_id_value: str) -> AIAnalysisOutcome:
        case = await self.cases.get_case(case_id_value)
        if case is None:
            return AIAnalysisOutcome(
                case_id=case_id_value,
                status="CASE_NOT_FOUND",
                case_state="UNKNOWN",
                failure_reason="The requested case does not exist.",
            )
        prepared = await self.prepare_cases(case.reconciliation_run_id, [case.case_id])
        if not prepared:
            return AIAnalysisOutcome(
                case_id=case.case_id,
                status="NOT_ELIGIBLE",
                case_state=case.case_state,
                failure_reason="Only unresolved ambiguous-candidate cases can be analyzed.",
            )
        outcomes = await self.analyze_unresolved_cases(
            case.reconciliation_run_id,
            prepared,
            total_cases=1,
        )
        return outcomes[0]

    async def _analyze_one(self, case: DBReconciliationCase) -> AIAnalysisOutcome:
        await self.cases.update_case(
            case,
            case_state=CaseState.AI_ANALYSIS_PENDING.value,
            ai_assisted=False,
        )
        packet: AIEvidencePacket | None = None
        validation: ValidationResult | None = None
        checks: list[VerificationCheck] = []
        client_result = AIClientResult()
        status = "REJECTED"
        failure_reason: str | None = None
        try:
            domain_case, domain_candidates, existing_edges = await self._load_domain_case(case)
            packet = build_evidence_packet(
                domain_case,
                self.policy,
                candidates=domain_case.ambiguous_candidates,
                max_chars=self.config.max_packet_chars,
            )
            client_result = await self._invoke_client(case.case_id, packet)
            self._record_usage(client_result)
            if client_result.response is None:
                status = self._status_for_failure(client_result.failure_type)
                failure_reason = client_result.failure_reason or "AI returned no valid suggestion."
                validation = client_result.validation
            else:
                validation = validate_ai_response(client_result.response, packet)
                if not validation.valid:
                    status = "VALIDATION_REJECTED"
                    failure_reason = "AI response failed external validation."
                    self.metrics.rejected_outputs += 1
                elif not client_result.response.ranked_candidate_ids:
                    status = "VALIDATION_REJECTED"
                    failure_reason = "AI response did not rank a precomputed candidate."
                    self.metrics.rejected_outputs += 1
                else:
                    selected_id = client_result.response.ranked_candidate_ids[0]
                    selected = domain_candidates.get(selected_id)
                    if selected is None:
                        status = "VALIDATION_REJECTED"
                        failure_reason = "Ranked candidate is unavailable for deterministic checks."
                        self.metrics.rejected_outputs += 1
                    else:
                        checks = verify_suggested_relationship(
                            domain_case,
                            selected,
                            existing_edges,
                        )
                        if all(check.passed for check in checks):
                            await self._persist_suggestion(case, selected, selected_id, checks)
                            status = "SUGGESTED_FOR_REVIEW"
                            self.metrics.cases_improved += 1
                        else:
                            status = "REVERIFICATION_FAILED"
                            failure_reason = (
                                "Deterministic relationship checks rejected the suggestion."
                            )
                            self.metrics.rejected_outputs += 1
        except EvidencePacketTooLarge as exc:
            status = "PACKET_REJECTED"
            failure_reason = str(exc)
        except Exception as exc:
            logger.exception("AI analysis failed closed for case %s", case.case_id)
            status = "ANALYSIS_FAILED"
            failure_reason = f"AI analysis failed: {type(exc).__name__}"

        if status != "SUGGESTED_FOR_REVIEW":
            await self._restore_exception(case)
        analysis = await self._persist_analysis(
            case,
            packet=packet,
            client_result=client_result,
            validation=validation,
            checks=checks,
            status=status,
        )
        await self._audit_analysis(case, analysis.id, status, validation, checks, client_result)
        return AIAnalysisOutcome(
            analysis_id=analysis.id,
            case_id=case.case_id,
            status=status,
            case_state=case.case_state,
            suggestion=client_result.response if validation and validation.valid else None,
            validation=validation,
            deterministic_checks=[check.model_dump(mode="json") for check in checks],
            failure_reason=failure_reason,
        )

    async def _invoke_client(
        self,
        case_id_value: str,
        packet: AIEvidencePacket,
    ) -> AIClientResult:
        try:
            return await self.client.analyze_case(case_id_value, packet)
        except (TimeoutError, OSError) as exc:
            is_timeout = isinstance(exc, TimeoutError)
            return AIClientResult(
                attempts=1,
                failure_type="timeout" if is_timeout else "provider_error",
                failure_reason=(
                    "AI provider timed out." if is_timeout else "AI provider is unavailable."
                ),
            )
        except Exception as exc:  # Provider adapters must never fail the batch.
            logger.warning(
                "AI adapter failed for case %s: %s",
                case_id_value,
                type(exc).__name__,
            )
            return AIClientResult(
                attempts=1,
                failure_type="provider_error",
                failure_reason=f"AI provider error: {type(exc).__name__}",
            )

    async def _load_domain_case(
        self,
        case: DBReconciliationCase,
    ) -> tuple[ReconciliationCase, dict[str, CandidateRelationship], list[EvidenceEdge]]:
        records = [
            NormalizedRecord.model_validate_json(json.dumps(item))
            for item in case.record_snapshot
        ]
        record_by_id = {item.entity_id: item for item in records}
        db_candidates = await self.cases.candidates_for_case(
            case.reconciliation_run_id,
            case.source_entity_ids,
        )
        system_candidates = [
            item for item in db_candidates if item.actor_type == ActorType.SYSTEM.value
        ]
        precomputed = [
            self._domain_candidate(item, record_by_id) for item in system_candidates
        ]
        ambiguous = [
            domain_item
            for domain_item, db_item in zip(precomputed, system_candidates, strict=True)
            if db_item.relationship_type == "settlement_bank"
            and db_item.decision_level != DecisionLevel.VERIFIED.value
        ]
        db_invariants = await self.cases.invariants_for_case(
            case.reconciliation_run_id,
            case.case_id,
        )
        invariants = [
            InvariantResult(
                invariant_id=item.invariant_id,
                passed=item.passed,
                expected_value=item.expected_value,
                actual_value=item.actual_value,
                affected_entities=item.affected_entities or [],
                message=item.message or "",
            )
            for item in db_invariants
        ]
        exception = await self.cases.exception_for_case(
            case.reconciliation_run_id,
            case.case_id,
        )
        domain_case = ReconciliationCase(
            case_id=case.case_id,
            source_entity_ids=case.source_entity_ids,
            records=records,
            candidate_relationships=precomputed,
            ambiguous_candidates=ambiguous,
            invariant_results=invariants,
            case_state=CaseState.NEEDS_ANALYSIS,
            exception_code=(ExceptionCode(case.exception_code) if case.exception_code else None),
            cash_bucket=CashBucket(case.cash_bucket or CashBucket.UNRESOLVED.value),
            gross_amount_paise=case.gross_amount_paise,
            net_amount_paise=case.net_amount_paise,
            residual_paise=case.residual_paise,
            checks_passed=[item.invariant_id for item in invariants if item.passed],
            checks_failed=[item.invariant_id for item in invariants if not item.passed],
            missing_evidence=(exception.missing_evidence or []) if exception else [],
        )
        candidates_by_id = {candidate_id(item): item for item in ambiguous}
        db_edges = await self.cases.evidence_for_case(
            case.reconciliation_run_id,
            case.case_id,
        )
        return domain_case, candidates_by_id, [self._domain_edge(item) for item in db_edges]

    @staticmethod
    def _domain_candidate(
        item: DBCandidateRelationship,
        records: dict[str, NormalizedRecord],
    ) -> CandidateRelationship:
        source = records.get(item.source_entity_id)
        target = records.get(item.target_entity_id)
        return CandidateRelationship(
            source_entity_id=item.source_entity_id,
            target_entity_id=item.target_entity_id,
            relationship_type=item.relationship_type,
            evidence_fields=item.evidence_fields,
            match_strength_score=round(item.match_score or 0),
            rule_id=item.rule_id or "UNKNOWN_RULE",
            source_record_type=source.source_type if source else None,
            target_record_type=target.source_type if target else None,
            allocated_amount_paise=item.allocated_amount_paise,
            rejected_reasons=[item.rejection_reason] if item.rejection_reason else [],
        )

    @staticmethod
    def _domain_edge(item: DBEvidenceEdge) -> EvidenceEdge:
        return EvidenceEdge(
            source_entity_id=item.source_entity_id,
            target_entity_id=item.target_entity_id,
            relationship_type=item.relationship_type,
            allocated_amount_paise=item.allocated_amount_paise,
            rule_id=item.rule_id,
            rule_version=item.rule_version,
            evidence_fields=item.evidence_fields,
            decision_level=DecisionLevel(item.decision_level),
            actor_type=ActorType(item.actor_type),
            verification_checks=[
                VerificationCheck.model_validate(check)
                for check in item.verification_checks or []
            ],
            created_at=item.created_at,
            reconciliation_run_id=str(item.reconciliation_run_id),
        )

    async def _persist_suggestion(
        self,
        case: DBReconciliationCase,
        selected: CandidateRelationship,
        selected_id: str,
        checks: list[VerificationCheck],
    ) -> None:
        await self.cases.create_candidate(
            reconciliation_run_id=case.reconciliation_run_id,
            source_entity_id=selected.source_entity_id,
            target_entity_id=selected.target_entity_id,
            relationship_type=selected.relationship_type,
            match_score=int(selected.match_strength_score * 10000),  # Scale to 0-10000
            decision_level=DecisionLevel.SUGGESTED.value,
            rejection_reason=None,
            evidence_fields=[*selected.evidence_fields, selected_id],
            allocated_amount_paise=selected.allocated_amount_paise,
            currency=case.currency,
            rule_id=f"AI_RANKED:{selected.rule_id}",
            actor_type=ActorType.AI_SUGGESTION.value,
        )
        await self.cases.create_evidence_edge(
            reconciliation_run_id=case.reconciliation_run_id,
            case_id=case.case_id,
            source_entity_id=selected.source_entity_id,
            target_entity_id=selected.target_entity_id,
            relationship_type=selected.relationship_type,
            allocated_amount_paise=selected.allocated_amount_paise,
            currency=case.currency,
            rule_id=f"AI_SUGGESTION:{selected.rule_id}",
            rule_version=self.config.prompt_version,
            evidence_fields=[*selected.evidence_fields, selected_id],
            decision_level=DecisionLevel.SUGGESTED.value,
            actor_type=ActorType.AI_SUGGESTION.value,
            verification_checks=[check.model_dump(mode="json") for check in checks],
        )
        await self.cases.update_case(
            case,
            case_state=CaseState.SUGGESTED_FOR_REVIEW.value,
            decision_level=DecisionLevel.SUGGESTED.value,
            ai_assisted=True,
        )
        exception = await self.cases.exception_for_case(
            case.reconciliation_run_id,
            case.case_id,
        )
        if exception is not None:
            exception.ai_assisted = True
            exception.human_review_state = CaseState.SUGGESTED_FOR_REVIEW.value
            await self.session.flush()

    async def _restore_exception(self, case: DBReconciliationCase) -> None:
        await self.cases.update_case(
            case,
            case_state=CaseState.ACTIONABLE_EXCEPTION.value,
            decision_level=DecisionLevel.UNRESOLVED.value,
            ai_assisted=False,
        )
        exception = await self.cases.exception_for_case(
            case.reconciliation_run_id,
            case.case_id,
        )
        if exception is not None:
            exception.ai_assisted = False
            exception.human_review_state = None
            await self.session.flush()

    async def _persist_analysis(
        self,
        case: DBReconciliationCase,
        *,
        packet: AIEvidencePacket | None,
        client_result: AIClientResult,
        validation: ValidationResult | None,
        checks: list[VerificationCheck],
        status: str,
    ) -> Any:
        response = client_result.raw_response
        if response is None and client_result.response is not None:
            response = client_result.response.model_dump(mode="json")
        errors = validation.errors if validation else []
        if client_result.failure_type:
            errors = [
                *errors,
                {
                    "code": client_result.failure_type.upper(),
                    "message": client_result.failure_reason or "AI analysis failed.",
                },
            ]
        return await self.reviews.create_ai_analysis(
            reconciliation_run_id=case.reconciliation_run_id,
            case_id=case.case_id,
            evidence_packet=(
                packet.model_dump(mode="json")
                if packet
                else {"case_id": case.case_id, "status": "PACKET_NOT_AVAILABLE"}
            ),
            ai_response=response,
            ai_model=self.config.model or None,
            ai_prompt_version=self.config.prompt_version,
            provider=self.config.provider,
            status=status,
            tokens_prompt=client_result.prompt_tokens,
            tokens_completion=client_result.completion_tokens,
            latency_ms=client_result.latency_ms,
            estimated_cost=client_result.estimated_cost,
            attempts=client_result.attempts,
            validation_passed=validation.valid if validation else False,
            validation_errors=errors or None,
            deterministic_checks=[check.model_dump(mode="json") for check in checks] or None,
            error_type=client_result.failure_type,
        )

    async def _audit_analysis(
        self,
        case: DBReconciliationCase,
        analysis_id: uuid.UUID,
        status: str,
        validation: ValidationResult | None,
        checks: list[VerificationCheck],
        result: AIClientResult,
    ) -> None:
        await self.audit.create(
            reconciliation_run_id=case.reconciliation_run_id,
            case_id=case.case_id,
            event_type="AI_ANALYSIS_COMPLETED",
            stage="ai_exception_analysis",
            severity="INFO" if status == "SUGGESTED_FOR_REVIEW" else "WARNING",
            actor=ActorType.AI_SUGGESTION.value,
            details={
                "analysis_id": str(analysis_id),
                "status": status,
                "validation_passed": validation.valid if validation else False,
                "deterministic_checks_passed": bool(checks)
                and all(check.passed for check in checks),
                "tokens_prompt": result.prompt_tokens,
                "tokens_completion": result.completion_tokens,
                "latency_ms": result.latency_ms,
                "estimated_cost": result.estimated_cost,
                "failure_type": result.failure_type,
            },
        )

    def _record_usage(self, result: AIClientResult) -> None:
        self.metrics.calls += max(result.attempts, 1)
        self.metrics.prompt_tokens += result.prompt_tokens
        self.metrics.completion_tokens += result.completion_tokens
        self.metrics.estimated_cost += result.estimated_cost
        self.metrics.total_latency_ms += result.latency_ms
        if result.failure_type == "timeout":
            self.metrics.timeouts += 1
            self.metrics.warnings.append("One or more AI analyses timed out.")
        elif result.failure_type == "provider_error":
            self.metrics.provider_errors += 1
            self.metrics.warnings.append("The AI provider was unavailable for one or more cases.")
        elif result.failure_type == "invalid_response":
            self.metrics.rejected_outputs += 1

    @staticmethod
    def _status_for_failure(failure_type: str | None) -> str:
        if failure_type is None:
            return "NO_VALID_RESPONSE"
        return {
            "timeout": "TIMEOUT",
            "provider_error": "PROVIDER_ERROR",
            "invalid_response": "VALIDATION_REJECTED",
            "disabled": "AI_DISABLED",
        }.get(failure_type, "NO_VALID_RESPONSE")
