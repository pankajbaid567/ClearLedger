"""Invariant-gated human review transitions and aggregate recalculation."""

from __future__ import annotations

import json
import logging
import uuid
from datetime import UTC, date, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import EvidenceEdge as DBEvidenceEdge
from db.models import ReconciliationCase as DBReconciliationCase
from db.models import ReconciliationRun
from db.repositories import AuditRepository, CaseRepository, ReviewRepository, RunRepository
from packages.domain.enums import ActorType, CaseState, CashBucket, DecisionLevel
from packages.domain.exceptions import InvariantError
from services.normalization.policy import SettlementPolicy
from services.reconciliation.evidence import EvidenceEdge, EvidenceGraph
from services.reconciliation.invariants import verify_case
from services.reconciliation.models import (
    InvariantResult as DomainInvariantResult,
)
from services.reconciliation.models import NormalizedRecord, VerificationCheck
from services.reconciliation.models import ReconciliationCase as DomainReconciliationCase
from services.reconciliation.run_service import RunServiceError

logger = logging.getLogger(__name__)


class ReviewService:
    def __init__(
        self,
        session: AsyncSession,
        *,
        run_id: uuid.UUID | None = None,
        expected_review_revision: int | None = None,
    ) -> None:
        self.session = session
        self.run_id = run_id
        self.expected_review_revision = expected_review_revision
        self.cases = CaseRepository(session)
        self.reviews = ReviewRepository(session)
        self.audit = AuditRepository(session)

    async def approve(
        self,
        case_id: str,
        *,
        actor: str,
        reason: str | None = None,
        note: str | None = None,
    ) -> tuple[Any, bool]:
        case = await self._require_case(case_id)
        suggestion_edge: DBEvidenceEdge | None = None
        refreshed_invariants: list[DomainInvariantResult] = []
        approved_net_paise = case.net_amount_paise
        if case.case_state == CaseState.SUGGESTED_FOR_REVIEW.value and case.ai_assisted:
            (
                suggestion_edge,
                refreshed_invariants,
                approved_net_paise,
            ) = await self._reverify_suggestion(case)
            invariant_passed = bool(refreshed_invariants) and all(
                item.passed for item in refreshed_invariants
            )
        else:
            _, refreshed_invariants, approved_net_paise = await self._reverify_suggestion(
                case, include_suggestion=False
            )
            invariant_passed = bool(refreshed_invariants) and all(
                item.passed for item in refreshed_invariants
            )
            invariant_passed = invariant_passed and case.residual_paise == 0
        previous_state = case.case_state
        new_state = (
            CaseState.RECONCILED.value
            if invariant_passed
            else CaseState.APPROVED_PENDING_VERIFICATION.value
        )
        decision = await self.reviews.create_human_decision(
            case_id=case.case_id,
            reconciliation_run_id=case.reconciliation_run_id,
            action="APPROVE",
            actor=actor,
            previous_state=previous_state,
            new_state=new_state,
            reason=reason,
            note=note,
            invariant_passed=invariant_passed,
        )
        if invariant_passed and suggestion_edge is not None:
            await self._promote_suggestion(
                case,
                suggestion_edge,
                refreshed_invariants,
            )
        await self.cases.update_case(
            case,
            case_state=new_state,
            decision_level=(
                DecisionLevel.VERIFIED.value if invariant_passed else case.decision_level
            ),
            net_amount_paise=(approved_net_paise if invariant_passed else case.net_amount_paise),
            residual_paise=(0 if invariant_passed else case.residual_paise),
            amount_at_risk_paise=(0 if invariant_passed else case.amount_at_risk_paise),
            bank_receipt_state=(
                "CONFIRMED"
                if invariant_passed and suggestion_edge is not None
                else case.bank_receipt_state
            ),
            cash_bucket=(
                CashBucket.BANK_CONFIRMED.value
                if invariant_passed
                and (case.bank_receipt_state == "CONFIRMED" or suggestion_edge is not None)
                else CashBucket.UNRESOLVED.value
            ),
            human_reviewed=True,
        )
        exception = await self.cases.exception_for_case(
            case.reconciliation_run_id,
            case.case_id,
        )
        if exception is not None:
            exception.human_review_state = new_state
        await self._audit_transition(case, decision, invariant_passed=invariant_passed)
        await self.recalculate_aggregates(case.reconciliation_run_id)
        return decision, invariant_passed

    async def _reverify_suggestion(
        self,
        case: DBReconciliationCase,
        *,
        include_suggestion: bool = True,
    ) -> tuple[DBEvidenceEdge | None, list[DomainInvariantResult], int]:
        db_edges = await self.cases.evidence_for_case(
            case.reconciliation_run_id,
            case.case_id,
        )
        suggestions = [
            edge
            for edge in db_edges
            if edge.actor_type == ActorType.AI_SUGGESTION.value
            and edge.decision_level == DecisionLevel.SUGGESTED.value
        ]
        if include_suggestion and len(suggestions) != 1:
            return None, [], case.net_amount_paise
        suggestion = suggestions[0] if include_suggestion else None
        if suggestion is not None:
            stored_checks = suggestion.verification_checks or []
            if not stored_checks or not all(item.get("passed") is True for item in stored_checks):
                return None, [], case.net_amount_paise

        try:
            records = [
                NormalizedRecord.model_validate_json(json.dumps(item))
                for item in case.record_snapshot
            ]
            domain_case = DomainReconciliationCase(
                case_id=case.case_id,
                source_entity_ids=case.source_entity_ids,
                records=records,
                invalid_reasons=[issue for record in records for issue in record.issues],
                case_state=CaseState.SUGGESTED_FOR_REVIEW,
                cash_bucket=CashBucket(case.cash_bucket or CashBucket.UNRESOLVED.value),
                gross_amount_paise=case.gross_amount_paise,
                net_amount_paise=case.net_amount_paise,
                residual_paise=case.residual_paise,
            )
            evidence = EvidenceGraph()
            for record in records:
                if record.amount_paise is None:
                    continue
                if record.source_type == "settlements":
                    evidence.register_available_amount(
                        record.entity_id,
                        "settlement_bank",
                        record.amount_paise,
                    )
                elif record.source_type == "bank_transactions":
                    evidence.register_available_amount(
                        record.entity_id,
                        "settlement_bank",
                        record.signed_amount_paise or 0,
                    )

            for db_edge in db_edges:
                is_reviewed_suggestion = suggestion is not None and db_edge.id == suggestion.id
                if (
                    db_edge.decision_level != DecisionLevel.VERIFIED.value
                    and not is_reviewed_suggestion
                ):
                    continue
                evidence.add_edge(
                    EvidenceEdge(
                        source_entity_id=db_edge.source_entity_id,
                        target_entity_id=db_edge.target_entity_id,
                        relationship_type=db_edge.relationship_type,
                        allocated_amount_paise=db_edge.allocated_amount_paise,
                        rule_id=db_edge.rule_id,
                        rule_version=db_edge.rule_version,
                        evidence_fields=db_edge.evidence_fields,
                        decision_level=DecisionLevel.VERIFIED,
                        actor_type=ActorType(db_edge.actor_type),
                        verification_checks=[
                            VerificationCheck.model_validate(item)
                            for item in db_edge.verification_checks or []
                        ],
                        created_at=db_edge.created_at,
                        reconciliation_run_id=str(db_edge.reconciliation_run_id),
                    )
                )
            run = await self.session.get(ReconciliationRun, case.reconciliation_run_id)
            if run is None:
                return None, [], case.net_amount_paise
            snapshot = run.policy_snapshot
            if not snapshot and run.policy_version_id:
                record = await RunRepository(self.session).get_policy(run.policy_version_id)
                snapshot = record.policy_data if record else {}
            policy = SettlementPolicy.model_validate(snapshot)
            refreshed = verify_case(domain_case, evidence, policy)
        except (InvariantError, ValueError, TypeError) as exc:
            logger.warning(
                "Reviewed suggestion failed full verification for case %s: %s",
                case.case_id,
                type(exc).__name__,
            )
            return None, [], case.net_amount_paise

        approved_net_paise = sum(
            record.amount_paise or 0 for record in records if record.source_type == "settlements"
        )
        return suggestion, refreshed, approved_net_paise

    async def _promote_suggestion(
        self,
        case: DBReconciliationCase,
        suggestion: DBEvidenceEdge,
        refreshed_invariants: list[DomainInvariantResult],
    ) -> None:
        suggestion.decision_level = DecisionLevel.VERIFIED.value
        candidates = await self.cases.candidates_for_case(
            case.reconciliation_run_id,
            case.source_entity_ids,
        )
        for candidate in candidates:
            if (
                candidate.actor_type == ActorType.AI_SUGGESTION.value
                and candidate.source_entity_id == suggestion.source_entity_id
                and candidate.target_entity_id == suggestion.target_entity_id
                and candidate.relationship_type == suggestion.relationship_type
            ):
                candidate.decision_level = DecisionLevel.VERIFIED.value

        persisted = {
            item.invariant_id: item
            for item in await self.cases.invariants_for_case(
                case.reconciliation_run_id,
                case.case_id,
            )
        }
        for invariant in refreshed_invariants:
            row = persisted.get(invariant.invariant_id)
            if row is None:
                await self.cases.create_invariant_result(
                    reconciliation_run_id=case.reconciliation_run_id,
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
                continue
            row.passed = invariant.passed
            row.expected_value = (
                None if invariant.expected_value is None else str(invariant.expected_value)
            )
            row.actual_value = (
                None if invariant.actual_value is None else str(invariant.actual_value)
            )
            row.affected_entities = invariant.affected_entities
            row.message = invariant.message

        exception = await self.cases.exception_for_case(
            case.reconciliation_run_id,
            case.case_id,
        )
        if exception is not None:
            exception.human_review_state = CaseState.RECONCILED.value
        await self.session.flush()

    async def reject(
        self,
        case_id: str,
        *,
        actor: str,
        reason: str | None = None,
        note: str | None = None,
    ) -> Any:
        case = await self._require_case(case_id)
        if case.case_state == CaseState.RECONCILED.value:
            raise self._invalid_transition(case, "rejected")
        return await self._transition(
            case,
            action="REJECT",
            new_state=CaseState.REJECTED_SUGGESTION.value,
            actor=actor,
            reason=reason,
            note=note,
            cash_bucket=CashBucket.UNRESOLVED.value,
        )

    async def defer(
        self,
        case_id: str,
        *,
        actor: str,
        until: date,
        reason: str | None = None,
        note: str | None = None,
    ) -> Any:
        case = await self._require_case(case_id)
        if case.case_state == CaseState.RECONCILED.value:
            raise self._invalid_transition(case, "deferred")
        if until < datetime.now(UTC).date():
            raise RunServiceError(
                "INVALID_DEFER_DATE",
                "The defer date cannot be in the past.",
                details={"case_id": case_id, "until": until.isoformat()},
            )
        decision = await self._transition(
            case,
            action="DEFER",
            new_state=CaseState.DEFERRED.value,
            actor=actor,
            reason=reason,
            note=note,
            cash_bucket=CashBucket.UNRESOLVED.value,
        )
        await self.reviews.create_follow_up_task(
            case_id=case.case_id,
            reconciliation_run_id=case.reconciliation_run_id,
            task_type="RECHECK_AFTER_SLA",
            amount_at_risk_paise=case.amount_at_risk_paise,
            required_evidence="Recheck source and bank evidence after defer date",
            deadline=until,
            action_code="RECHECK_DEFERRED_CASE",
        )
        return decision

    async def assign(
        self,
        case_id: str,
        *,
        actor: str,
        owner_role: str,
        reason: str | None = None,
        note: str | None = None,
    ) -> Any:
        case = await self._require_case(case_id)
        previous_state = case.case_state
        decision = await self.reviews.create_human_decision(
            case_id=case.case_id,
            reconciliation_run_id=case.reconciliation_run_id,
            action="ASSIGN",
            actor=actor,
            previous_state=previous_state,
            new_state=previous_state,
            reason=reason,
            note=note,
        )
        await self.cases.update_case(case, owner_role=owner_role, human_reviewed=True)
        exception = await self.cases.exception_for_case(case.reconciliation_run_id, case.case_id)
        if exception is not None:
            exception.owner_role = owner_role
        await self._audit_transition(case, decision, details={"owner_role": owner_role})
        await self.recalculate_aggregates(case.reconciliation_run_id)
        return decision

    async def create_task(self, case_id: str, *, actor: str, **values: Any) -> Any:
        case = await self._require_case(case_id)
        task = await self.reviews.create_follow_up_task(
            case_id=case.case_id, reconciliation_run_id=case.reconciliation_run_id, **values
        )
        await self.audit.create(
            reconciliation_run_id=case.reconciliation_run_id,
            case_id=case.case_id,
            event_type="FOLLOW_UP_TASK_CREATED",
            stage="human_review",
            actor=actor,
            details={"task_id": str(task.id), "task_type": task.task_type},
        )
        await self.recalculate_aggregates(case.reconciliation_run_id)
        return task

    async def _transition(
        self,
        case: DBReconciliationCase,
        *,
        action: str,
        new_state: str,
        actor: str,
        reason: str | None,
        note: str | None,
        cash_bucket: str,
    ) -> Any:
        previous_state = case.case_state
        decision = await self.reviews.create_human_decision(
            case_id=case.case_id,
            reconciliation_run_id=case.reconciliation_run_id,
            action=action,
            actor=actor,
            previous_state=previous_state,
            new_state=new_state,
            reason=reason,
            note=note,
        )
        await self.cases.update_case(
            case,
            case_state=new_state,
            cash_bucket=cash_bucket,
            human_reviewed=True,
        )
        exception = await self.cases.exception_for_case(case.reconciliation_run_id, case.case_id)
        if exception is not None:
            exception.human_review_state = new_state
        await self._audit_transition(case, decision)
        await self.recalculate_aggregates(case.reconciliation_run_id)
        return decision

    async def _audit_transition(
        self,
        case: DBReconciliationCase,
        decision: Any,
        *,
        invariant_passed: bool | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        await self.audit.create(
            reconciliation_run_id=case.reconciliation_run_id,
            case_id=case.case_id,
            event_type="HUMAN_DECISION_RECORDED",
            stage="human_review",
            severity="INFO" if invariant_passed is not False else "WARNING",
            actor=decision.actor,
            details={
                "decision_id": str(decision.id),
                "action": decision.action,
                "previous_state": decision.previous_state,
                "new_state": decision.new_state,
                "invariant_passed": invariant_passed,
                **(details or {}),
            },
        )

    async def recalculate_aggregates(self, run_id: uuid.UUID) -> None:
        result = await self.session.scalars(
            select(DBReconciliationCase).where(DBReconciliationCase.reconciliation_run_id == run_id)
        )
        cases = list(result)
        from services.cash_position.service import calculate_cash_position

        domain_cases = [
            DomainReconciliationCase(
                case_id=case.case_id,
                source_entity_ids=case.source_entity_ids,
                records=[
                    NormalizedRecord.model_validate_json(json.dumps(item))
                    for item in case.record_snapshot
                ],
                case_state=CaseState(case.case_state),
                cash_bucket=CashBucket(case.cash_bucket or "UNRESOLVED"),
                gross_amount_paise=case.gross_amount_paise,
                net_amount_paise=case.net_amount_paise,
                residual_paise=case.residual_paise,
            )
            for case in cases
        ]
        cash = calculate_cash_position(domain_cases, EvidenceGraph()).model_dump(mode="json")
        snapshot = await self.cases.cash_position(run_id)
        if snapshot is not None:
            for key, value in cash.items():
                setattr(snapshot, key, value)
        run = await self.session.get(ReconciliationRun, run_id)
        if run is not None:
            state_counts: dict[str, int] = {}
            for case in cases:
                state_counts[case.case_state] = state_counts.get(case.case_state, 0) + 1
            run.metrics = {
                **run.metrics,
                "cases_by_state": state_counts,
                "total_cases": len(cases),
                "reconciled_cases": state_counts.get(CaseState.RECONCILED.value, 0),
                "exception_cases": sum(
                    state_counts.get(state.value, 0)
                    for state in (
                        CaseState.ACTIONABLE_EXCEPTION,
                        CaseState.SUGGESTED_FOR_REVIEW,
                        CaseState.APPROVED_PENDING_VERIFICATION,
                        CaseState.REJECTED_SUGGESTION,
                        CaseState.DEFERRED,
                    )
                ),
            }
            run.cash_position = cash
        await self.session.flush()

    @staticmethod
    def _case_amount(case: DBReconciliationCase) -> int:
        from services.cash_position.service import cash_bucket_contribution

        return cash_bucket_contribution(
            case.cash_bucket or "UNRESOLVED",
            case.net_amount_paise,
            case.residual_paise,
            case.gross_amount_paise,
        )[0]

    async def _require_case(self, case_id: str) -> DBReconciliationCase:
        case = await self.cases.get_case(case_id, self.run_id)
        if case is None:
            raise RunServiceError(
                "CASE_NOT_FOUND",
                "The requested reconciliation case was not found.",
                status_code=404,
                details={"case_id": case_id},
            )
        run = await RunRepository(self.session).get_for_update(case.reconciliation_run_id)
        if run is None or run.status != "COMPLETED":
            raise RunServiceError(
                "RUN_NOT_REVIEWABLE", "Review requires a completed execution.", status_code=409
            )
        if self.expected_review_revision is None:
            raise RunServiceError(
                "REVIEW_REVISION_REQUIRED",
                "A review revision is required for every human mutation.",
                status_code=409,
                details={"review_revision": run.review_revision},
            )
        if run.review_revision != self.expected_review_revision:
            raise RunServiceError(
                "STALE_REVIEW_REVISION",
                "This run changed. Refresh the evidence before reviewing.",
                status_code=409,
                details={"review_revision": run.review_revision},
            )
        # Refetch after the run lock: another operator may have committed while this
        # request waited. All review writes and aggregate reads now serialize per run.
        case = await self.cases.get_case(case_id, run.id)
        if case is None:
            raise RunServiceError("CASE_NOT_FOUND", "The case is unavailable.", status_code=404)
        run.review_revision += 1
        await self.session.flush()
        return case

    @staticmethod
    def _invalid_transition(case: DBReconciliationCase, action: str) -> RunServiceError:
        return RunServiceError(
            "INVALID_STATE_TRANSITION",
            f"A reconciled case cannot be {action}.",
            status_code=409,
            details={"case_id": case.case_id, "current_state": case.case_state},
        )
