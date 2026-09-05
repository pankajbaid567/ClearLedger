"""PostgreSQL integration tests for AI fallback and bounded suggestions."""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from io import BytesIO
from pathlib import Path

import psycopg
import pytest
import pytest_asyncio
from fastapi import UploadFile
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from db.models import AIAnalysis, Base, EvidenceEdge, ReconciliationCase, ReconciliationRun
from services.ai_analyst.schemas import AIAnalysisResponse, AIClientConfig, AIClientResult
from services.reconciliation.review_service import ReviewService
from services.reconciliation.run_service import REQUIRED_SOURCE_TYPES, RunService

ROOT = Path(__file__).resolve().parents[2]
DATABASE_NAME = "clearledger_ai_test"
DATABASE_URL = f"postgresql+psycopg://clearledger:clearledger@localhost:5432/{DATABASE_NAME}"
ADMIN_DATABASE_URL = "postgresql://clearledger:clearledger@localhost:5432/clearledger"


def _ensure_database() -> None:
    with psycopg.connect(ADMIN_DATABASE_URL, autocommit=True) as connection:
        exists = connection.execute(
            "SELECT 1 FROM pg_database WHERE datname = %s",
            (DATABASE_NAME,),
        ).fetchone()
        if exists is None:
            connection.execute(f'CREATE DATABASE "{DATABASE_NAME}"')


@pytest_asyncio.fixture(scope="module", loop_scope="module")
async def session_factory() -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    _ensure_database()
    engine = create_async_engine(DATABASE_URL, pool_pre_ping=True)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.drop_all)
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    yield factory
    await engine.dispose()


class NeverCalledClient:
    def __init__(self) -> None:
        self.case_ids: list[str] = []

    async def analyze_case(self, case_id: str, evidence_packet) -> AIClientResult:
        self.case_ids.append(case_id)
        raise AssertionError("AI client must not run when AI is disabled")


class TimeoutClient:
    def __init__(self) -> None:
        self.case_ids: list[str] = []

    async def analyze_case(self, case_id: str, evidence_packet) -> AIClientResult:
        self.case_ids.append(case_id)
        return AIClientResult(
            attempts=1,
            latency_ms=20,
            failure_type="timeout",
            failure_reason="AI provider timed out.",
        )


class InvalidReferenceClient:
    def __init__(self) -> None:
        self.case_ids: list[str] = []

    async def analyze_case(self, case_id: str, evidence_packet) -> AIClientResult:
        self.case_ids.append(case_id)
        response = AIAnalysisResponse(
            case_id=case_id,
            hypothesis_code="AMBIGUOUS_BANK_MATCH",
            ranked_candidate_ids=["candidate:fabricated"],
            supporting_evidence_ids=["invariant:fabricated"],
            contradicting_evidence_ids=[],
            missing_evidence=["unique bank reference"],
            recommended_exception_code="AMBIGUOUS_CANDIDATES",
            recommended_action_code="MANUAL_EVIDENCE_REVIEW",
            explanation="A candidate requires human review.",
            extracted_identifiers=None,
        )
        return AIClientResult(response=response, attempts=1, latency_ms=5)


class ValidSuggestionClient:
    def __init__(self) -> None:
        self.case_ids: list[str] = []

    async def analyze_case(self, case_id: str, evidence_packet) -> AIClientResult:
        self.case_ids.append(case_id)
        candidate = evidence_packet.precomputed_candidates[0]
        response = AIAnalysisResponse(
            case_id=case_id,
            hypothesis_code="AMBIGUOUS_BANK_MATCH",
            ranked_candidate_ids=[candidate.candidate_id],
            supporting_evidence_ids=[candidate.candidate_id, "invariant:INV-004"],
            contradicting_evidence_ids=["invariant:INV-005"],
            missing_evidence=["unique bank reference"],
            recommended_exception_code="AMBIGUOUS_CANDIDATES",
            recommended_action_code="MANUAL_EVIDENCE_REVIEW",
            explanation="The first code-generated candidate is preferred for human review.",
            extracted_identifiers=None,
        )
        return AIClientResult(
            response=response,
            raw_response=response.model_dump(mode="json"),
            attempts=1,
            prompt_tokens=100,
            completion_tokens=50,
            latency_ms=10,
            estimated_cost=1000,  # 1000 micro-dollars = $0.001
        )


async def _execute_run(
    session: AsyncSession,
    upload_dir: Path,
    *,
    config: AIClientConfig,
    client,
) -> tuple[ReconciliationRun, RunService]:
    service = RunService(
        session,
        upload_dir=upload_dir,
        ai_config=config,
        ai_client=client,
    )
    run = await service.create_run()
    uploads = {
        source_type: UploadFile(
            file=BytesIO((ROOT / "data" / "demo" / f"{source_type}.csv").read_bytes()),
            filename=f"{source_type}.csv",
        )
        for source_type in REQUIRED_SOURCE_TYPES
    }
    await service.add_files_to_run(run.id, uploads)
    result = await service.execute_reconciliation(run.id)
    assert len(result.cases) == 75
    await session.commit()
    persisted = await session.get(ReconciliationRun, run.id)
    assert persisted is not None
    return persisted, service


async def _case(session: AsyncSession, run_id: uuid.UUID, case_id: str) -> ReconciliationCase:
    result = await session.scalars(
        select(ReconciliationCase).where(
            ReconciliationCase.reconciliation_run_id == run_id,
            ReconciliationCase.case_id == case_id,
        )
    )
    return result.one()


@pytest.mark.asyncio(loop_scope="module")
async def test_ai_disabled_preserves_full_deterministic_batch(
    session_factory: async_sessionmaker[AsyncSession],
    tmp_path_factory: pytest.TempPathFactory,
) -> None:
    client = NeverCalledClient()
    async with session_factory() as session:
        run, _ = await _execute_run(
            session,
            tmp_path_factory.mktemp("ai-disabled"),
            config=AIClientConfig(enabled=False),
            client=client,
        )
        ambiguous = await _case(session, run.id, "CASE_AMB0073")
        injection = await _case(session, run.id, "CASE_MN0060")
        assert ambiguous.case_state == "ACTIONABLE_EXCEPTION"
        assert injection.case_state == "RECONCILED"
        assert client.case_ids == []
        assert run.status == "COMPLETED"
        assert run.metrics["ai"]["enabled"] is False
        assert run.metrics["ai"]["calls"] == 0
        assert (
            run.metrics["ablation"]["deterministic_only"]
            == run.metrics["ablation"]["deterministic_plus_ai"]
        )


@pytest.mark.asyncio(loop_scope="module")
async def test_ai_timeout_completes_batch_and_restores_exception(
    session_factory: async_sessionmaker[AsyncSession],
    tmp_path_factory: pytest.TempPathFactory,
) -> None:
    client = TimeoutClient()
    async with session_factory() as session:
        run, _ = await _execute_run(
            session,
            tmp_path_factory.mktemp("ai-timeout"),
            config=AIClientConfig(enabled=True, provider="test", model="fake", api_key="test"),
            client=client,
        )
        case = await _case(session, run.id, "CASE_AMB0073")
        injection = await _case(session, run.id, "CASE_MN0060")
        analysis = (
            await session.scalars(
                select(AIAnalysis).where(
                    AIAnalysis.reconciliation_run_id == run.id,
                    AIAnalysis.case_id == case.case_id,
                )
            )
        ).one()
        assert run.status == "COMPLETED"
        assert case.case_state == "ACTIONABLE_EXCEPTION"
        assert case.ai_assisted is False
        assert injection.case_state == "RECONCILED"
        assert set(client.case_ids) == {"CASE_AMB0073", "CASE_AMB0074", "CASE_AMB0075"}
        assert "CASE_MN0060" not in client.case_ids
        assert analysis.status == "TIMEOUT"
        assert run.metrics["ai"]["timeouts"] == 3
        assert run.metrics["ai"]["cases_improved"] == 0


@pytest.mark.asyncio(loop_scope="module")
async def test_invalid_ai_references_are_rejected(
    session_factory: async_sessionmaker[AsyncSession],
    tmp_path_factory: pytest.TempPathFactory,
) -> None:
    client = InvalidReferenceClient()
    async with session_factory() as session:
        run, _ = await _execute_run(
            session,
            tmp_path_factory.mktemp("ai-invalid"),
            config=AIClientConfig(enabled=True, provider="test", model="fake", api_key="test"),
            client=client,
        )
        case = await _case(session, run.id, "CASE_AMB0073")
        analysis = (
            await session.scalars(
                select(AIAnalysis).where(
                    AIAnalysis.reconciliation_run_id == run.id,
                    AIAnalysis.case_id == case.case_id,
                )
            )
        ).one()
        error_codes = {item["code"] for item in analysis.validation_errors}
        assert case.case_state == "ACTIONABLE_EXCEPTION"
        assert analysis.status == "VALIDATION_REJECTED"
        assert {"UNKNOWN_EVIDENCE_ID", "UNKNOWN_CANDIDATE_ID"} <= error_codes
        assert run.metrics["ai"]["rejected_outputs"] == 3


@pytest.mark.asyncio(loop_scope="module")
async def test_valid_ai_candidate_is_reverified_and_only_suggested(
    session_factory: async_sessionmaker[AsyncSession],
    tmp_path_factory: pytest.TempPathFactory,
) -> None:
    client = ValidSuggestionClient()
    async with session_factory() as session:
        run, _ = await _execute_run(
            session,
            tmp_path_factory.mktemp("ai-valid"),
            config=AIClientConfig(enabled=True, provider="test", model="fake", api_key="test"),
            client=client,
        )
        case = await _case(session, run.id, "CASE_AMB0073")
        analysis = (
            await session.scalars(
                select(AIAnalysis).where(
                    AIAnalysis.reconciliation_run_id == run.id,
                    AIAnalysis.case_id == case.case_id,
                )
            )
        ).one()
        suggested_edge = (
            await session.scalars(
                select(EvidenceEdge).where(
                    EvidenceEdge.reconciliation_run_id == run.id,
                    EvidenceEdge.case_id == case.case_id,
                    EvidenceEdge.actor_type == "AI_SUGGESTION",
                )
            )
        ).one()
        assert case.case_state == "SUGGESTED_FOR_REVIEW"
        assert case.case_state not in {"RECONCILED", "VERIFIED"}
        assert case.ai_assisted is True
        assert analysis.status == "SUGGESTED_FOR_REVIEW"
        assert analysis.validation_passed is True
        assert all(item["passed"] for item in analysis.deterministic_checks)
        assert suggested_edge.decision_level == "SUGGESTED"
        assert run.metrics["ai"]["calls"] == 3
        assert run.metrics["ai"]["cases_improved"] == 3
        assert run.metrics["ai"]["prompt_tokens"] == 300
        assert run.metrics["ai"]["estimated_cost"] == 3000  # 3000 micro-dollars = $0.003

        review_service = ReviewService(session)
        decision, invariant_passed = await review_service.approve(
            case.case_id,
            actor="finance.reviewer@example.test",
            reason="Reviewed the AI-ranked bank relationship.",
        )
        await session.commit()
        await session.refresh(case)
        await session.refresh(suggested_edge)
        refreshed_invariants = await review_service.cases.invariants_for_case(
            run.id,
            case.case_id,
        )
        _, approval_checks, _ = await review_service._reverify_suggestion(case)

        assert invariant_passed is False
        assert decision.previous_state == "SUGGESTED_FOR_REVIEW"
        assert decision.new_state == "APPROVED_PENDING_VERIFICATION"
        assert case.case_state == "APPROVED_PENDING_VERIFICATION"
        assert case.decision_level == "SUGGESTED"
        assert case.residual_paise > 0
        assert case.amount_at_risk_paise > 0
        assert case.cash_bucket == "UNRESOLVED"
        assert suggested_edge.decision_level == "SUGGESTED"
        assert refreshed_invariants
        assert any(not item.passed for item in approval_checks)
