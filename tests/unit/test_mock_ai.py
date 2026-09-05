from __future__ import annotations

import uuid
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from services.ai_analyst.evidence_packet import build_evidence_packet
from services.ai_analyst.grounded_qa import GroundedQAService
from services.ai_analyst.mock_client import MockAIClient
from services.ai_analyst.schemas import AIClientConfig
from services.ai_analyst.validator import validate_ai_response
from services.normalization.policy import load_policy
from services.reconciliation.orchestrator import run_reconciliation

ROOT = Path(__file__).resolve().parents[2]


def _demo_reconciliation():
    data = ROOT / "data" / "demo"
    sources = {
        "orders": str(data / "orders.csv"),
        "payments": str(data / "payments.csv"),
        "settlements": str(data / "settlements.csv"),
        "settlement_components": str(data / "settlement_components.csv"),
        "bank_transactions": str(data / "bank_transactions.csv"),
    }
    policy = load_policy(ROOT / "policies" / "settlement_policy.v1.json")
    return run_reconciliation(sources, policy, "test"), policy


@pytest.mark.asyncio
async def test_mock_ai_client_produces_strictly_valid_response() -> None:
    result, policy = _demo_reconciliation()
    config = AIClientConfig(enabled=True, provider="mock", model="mock-analyst-v1")
    client = MockAIClient(config)

    # Test across exception cases in demo
    exception_cases = [c for c in result.cases if c.exception_code is not None]
    assert len(exception_cases) >= 10

    for case in exception_cases[:5]:
        packet = build_evidence_packet(case, policy)
        client_result = await client.analyze_case(case.case_id, packet)

        assert client_result.response is not None
        assert client_result.validation is not None
        assert client_result.validation.valid is True
        assert client_result.validation.errors == []
        assert client_result.latency_ms >= 0
        assert client_result.estimated_cost == 0  # Mock returns 0 micro-dollars

        # Independent re-validation
        re_val = validate_ai_response(client_result.response, packet)
        assert re_val.valid is True
        assert re_val.errors == []


@pytest.mark.asyncio
async def test_grounded_qa_mock_provider() -> None:
    config = AIClientConfig(enabled=True, provider="mock", model="clearledger-mock-v1")
    session = AsyncMock()
    service = GroundedQAService(session, config=config)

    # Mock DB run and cases
    mock_run = MagicMock()
    mock_run.status = "COMPLETED"
    mock_run.dataset_id = "demo_20260827"
    mock_run.duration_ms = 145
    mock_run.total_cases = 75
    mock_run.reconciled_cases = 53
    mock_run.exception_cases = 15
    mock_run.unresolved_cases = 7

    mock_case = MagicMock()
    mock_case.case_id = "CASE_AMB0073"
    mock_case.case_state = "ACTIONABLE_EXCEPTION"
    mock_case.exception_code = "AMBIGUOUS_CANDIDATES"
    mock_case.net_amount_paise = 185275
    mock_case.gross_amount_paise = 185275
    mock_case.residual_paise = 185275
    mock_case.cash_bucket = "UNRESOLVED"
    mock_case.owner_role = "OPERATIONS"
    mock_case.next_action = "MANUAL_EVIDENCE_REVIEW"
    mock_case.record_snapshot = []

    mock_cash = MagicMock()
    mock_cash.bank_confirmed_paise = 14451965
    mock_cash.settlement_confirmed_in_transit_paise = 1119439
    mock_cash.at_risk_paise = 1279344
    mock_cash.unresolved_paise = 1547747
    mock_cash.safe_cash_paise = 12231780

    service._build_computed_data = MagicMock(return_value={
        "total_cases": 75,
        "reconciled_cases": 53,
        "exception_cases": 15,
        "unresolved_cases": 7,
    })

    with pytest.MonkeyPatch.context() as mp:
        from db.repositories import CaseRepository, RunRepository
        mp.setattr(RunRepository, "get", AsyncMock(return_value=mock_run))
        mp.setattr(CaseRepository, "list_cases", AsyncMock(return_value=([mock_case], 1)))
        mp.setattr(CaseRepository, "cash_position", AsyncMock(return_value=mock_cash))

        res = await service.answer_question(uuid.uuid4(), "Why is CASE_AMB0073 unresolved?")
        assert res.grounded is True
        assert res.provider == "mock"
        assert res.model == "clearledger-mock-v1"
        assert "CASE_AMB0073" in res.cited_case_ids
