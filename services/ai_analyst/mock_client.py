"""In-memory mock AI client for zero-latency, fail-closed offline evaluation."""

from __future__ import annotations

import time

from services.ai_analyst.evidence_packet import AIEvidencePacket
from services.ai_analyst.schemas import (
    AIAnalysisResponse,
    AIClientConfig,
    AIClientResult,
)
from services.ai_analyst.validator import validate_ai_response


class MockAIClient:
    """Deterministic, zero-network AI analyzer for live judging and offline tests."""

    def __init__(self, config: AIClientConfig) -> None:
        self.config = config

    async def analyze_case(
        self,
        case_id: str,
        evidence_packet: AIEvidencePacket,
    ) -> AIClientResult:
        del case_id
        started = time.perf_counter()

        available_evidence = sorted(evidence_packet.available_evidence_ids())
        supporting = available_evidence[:2]
        contradicting = available_evidence[2:3] if len(available_evidence) > 2 else []
        candidate_ids = [c.candidate_id for c in evidence_packet.precomputed_candidates]

        failed_invariants = [inv for inv in evidence_packet.invariant_results if not inv.passed]
        if failed_invariants:
            inv_id = failed_invariants[0].invariant_id
            if "FEE" in inv_id and "FEE_VARIANCE" in evidence_packet.allowed_exception_codes:
                rec_exception = "FEE_VARIANCE"
            elif "TAX" in inv_id and "TAX_VARIANCE" in evidence_packet.allowed_exception_codes:
                rec_exception = "TAX_VARIANCE"
            elif (
                "004" in inv_id
                and "BANK_CREDIT_MISSING" in evidence_packet.allowed_exception_codes
            ):
                rec_exception = "BANK_CREDIT_MISSING"
            elif evidence_packet.allowed_exception_codes:
                rec_exception = evidence_packet.allowed_exception_codes[0]
            else:
                rec_exception = "UNEXPLAINED_RESIDUAL"
        elif evidence_packet.allowed_exception_codes:
            rec_exception = evidence_packet.allowed_exception_codes[0]
        else:
            rec_exception = "UNEXPLAINED_RESIDUAL"

        action_map = {
            "BANK_CREDIT_MISSING": "RAISE_BANK_TRACE",
            "FEE_VARIANCE": "REVIEW_FEE_POLICY",
            "TAX_VARIANCE": "REVIEW_FEE_POLICY",
            "AMBIGUOUS_CANDIDATES": "MANUAL_EVIDENCE_REVIEW",
            "DUPLICATE_SOURCE_RECORD": "INVESTIGATE_DUPLICATE",
            "PAYMENT_MISSING_AT_GATEWAY": "REQUEST_GATEWAY_REPORT",
            "SETTLEMENT_OVERDUE": "RECHECK_AFTER_SLA",
        }
        rec_action = action_map.get(rec_exception, "")
        if rec_action not in evidence_packet.allowed_action_codes:
            rec_action = (
                evidence_packet.allowed_action_codes[0]
                if evidence_packet.allowed_action_codes
                else "MANUAL_EVIDENCE_REVIEW"
            )

        explanation = (
            f"Case {evidence_packet.case_id} evaluated under bounded policy rules. "
            f"Evidence matches exception condition {rec_exception}. "
            "Operator action recommended according to prescribed guidelines."
        )

        response = AIAnalysisResponse(
            case_id=evidence_packet.case_id,
            hypothesis_code=rec_exception,
            ranked_candidate_ids=candidate_ids,
            supporting_evidence_ids=supporting,
            contradicting_evidence_ids=contradicting,
            missing_evidence=[],
            recommended_exception_code=rec_exception,
            recommended_action_code=rec_action,
            explanation=explanation,
            extracted_identifiers=None,
        )

        validation = validate_ai_response(response, evidence_packet)
        latency = round((time.perf_counter() - started) * 1_000)

        return AIClientResult(
            response=response if validation.valid else None,
            raw_response=response.model_dump(),
            validation=validation,
            prompt_tokens=320,
            completion_tokens=95,
            latency_ms=max(1, latency),
            estimated_cost=0,  # Mock returns 0 micro-dollars
            attempts=1,
            failure_reason=None if validation.valid else "Validation failed",
            failure_type=None if validation.valid else "invalid_response",
        )
