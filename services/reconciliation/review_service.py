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
from db.repositories import AuditRepository, CaseRepository, ReviewRepository
from packages.domain.enums import ActorType, CaseState, CashBucket, DecisionLevel
from packages.domain.exceptions import InvariantError
from services.normalization.policy import load_policy
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
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
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
            invariants = await self.cases.invariants_for_case(
                case.reconciliation_run_id, case.case_id
            )
            invariant_passed = bool(invariants) and all(item.passed for item in invariants)
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
        if len(suggestions) != 1:
            return None, [], case.net_amount_paise
        suggestion = suggestions[0]
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
                is_reviewed_suggestion = db_edge.id == suggestion.id
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
            refreshed = verify_case(domain_case, evidence, load_policy())
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
        await self._audit_transition(case, decision, details={"owner_role": owner_role})
        await self.recalculate_aggregates(case.reconciliation_run_id)
        return decision

    async def create_task(self, case_id: str, *, actor: str, **values: Any) -> Any:
        case = await self._require_case(case_id)
        task = await self.reviews.create_follow_up_task(case_id=case.case_id, **values)
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
        buckets: dict[str, dict[str, Any]] = {
            bucket.value: {"bucket": bucket.value, "amount_paise": 0, "case_ids": []}
            for bucket in CashBucket
        }
        for case in cases:
            bucket = case.cash_bucket or CashBucket.UNRESOLVED.value
            buckets[bucket]["amount_paise"] += self._case_amount(case)
            buckets[bucket]["case_ids"].append(case.case_id)

        snapshot = await self.cases.cash_position(run_id)
        deductions = {
            "scheduled_refunds_paise": snapshot.scheduled_refunds_paise if snapshot else 0,
            "known_disputes_paise": snapshot.known_disputes_paise if snapshot else 0,
            "known_reserve_holds_paise": snapshot.known_reserve_holds_paise if snapshot else 0,
        }
        bank = buckets[CashBucket.BANK_CONFIRMED.value]["amount_paise"]
        transit = buckets[CashBucket.SETTLEMENT_CONFIRMED_IN_TRANSIT.value]["amount_paise"]
        cash = {
            "buckets": buckets,
            "bank_confirmed_paise": bank,
            "settlement_confirmed_in_transit_paise": transit,
            "expected_settlement_paise": buckets[CashBucket.EXPECTED_SETTLEMENT.value][
                "amount_paise"
            ],
            "at_risk_paise": buckets[CashBucket.AT_RISK.value]["amount_paise"],
            "unresolved_paise": buckets[CashBucket.UNRESOLVED.value]["amount_paise"],
            **deductions,
            "safe_cash_paise": bank + transit - sum(deductions.values()),
        }
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
        if case.cash_bucket in {
            CashBucket.BANK_CONFIRMED.value,
            CashBucket.SETTLEMENT_CONFIRMED_IN_TRANSIT.value,
            CashBucket.EXPECTED_SETTLEMENT.value,
        }:
            return case.net_amount_paise
        return abs(case.residual_paise or case.net_amount_paise or case.gross_amount_paise)

    async def _require_case(self, case_id: str) -> DBReconciliationCase:
        case = await self.cases.get_case(case_id)
        if case is None:
            raise RunServiceError(
                "CASE_NOT_FOUND",
                "The requested reconciliation case was not found.",
                status_code=404,
                details={"case_id": case_id},
            )
        return case

    @staticmethod
    def _invalid_transition(case: DBReconciliationCase, action: str) -> RunServiceError:
        return RunServiceError(
            "INVALID_STATE_TRANSITION",
            f"A reconciled case cannot be {action}.",
            status_code=409,
            details={"case_id": case.case_id, "current_state": case.case_state},
        )
