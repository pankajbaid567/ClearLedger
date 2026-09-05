"""Independent, fail-closed validation for model output."""

from __future__ import annotations

import re

from services.ai_analyst.evidence_packet import AIEvidencePacket
from services.ai_analyst.schemas import AIAnalysisResponse, ValidationResult

_AUTHORITATIVE_STATE = re.compile(r"\b(?:reconciled|verified|approved)\b", re.IGNORECASE)
_AUTHORITATIVE_AMOUNT = re.compile(
    r"(?:\b(?:INR|USD|EUR|GBP|amount_paise|total|balance|residual)\b\s*[:=]?\s*[$₹€£]?\d)"
    r"|(?:[$₹€£]\s*\d)"
    r"|(?:\b\d[\d,]*(?:\.\d+)?\s*(?:paise|INR|USD|EUR|GBP)\b)"
    r"|(?:\b\d+(?:\.\d+)?\s*[+*/=]\s*\d+)",
    re.IGNORECASE,
)


def _error(code: str, message: str) -> dict[str, str]:
    return {"code": code, "message": message}


def validate_ai_response(
    response: AIAnalysisResponse,
    evidence_packet: AIEvidencePacket,
) -> ValidationResult:
    """Validate references and authority boundaries outside the model."""
    errors: list[dict[str, str]] = []
    if response.case_id != evidence_packet.case_id:
        errors.append(_error("CASE_ID_MISMATCH", "Response case_id does not match the packet."))

    evidence_ids = evidence_packet.available_evidence_ids()
    cited_ids = response.supporting_evidence_ids + response.contradicting_evidence_ids
    fabricated_evidence = sorted(set(cited_ids) - evidence_ids)
    if fabricated_evidence:
        errors.append(
            _error(
                "UNKNOWN_EVIDENCE_ID",
                f"Unknown evidence IDs: {', '.join(fabricated_evidence)}",
            )
        )

    candidate_ids = {item.candidate_id for item in evidence_packet.precomputed_candidates}
    fabricated_candidates = sorted(set(response.ranked_candidate_ids) - candidate_ids)
    if fabricated_candidates:
        errors.append(
            _error(
                "UNKNOWN_CANDIDATE_ID",
                f"Unknown candidate IDs: {', '.join(fabricated_candidates)}",
            )
        )
    if len(response.ranked_candidate_ids) != len(set(response.ranked_candidate_ids)):
        errors.append(_error("DUPLICATE_CANDIDATE_ID", "Candidate ranking contains duplicates."))

    if response.recommended_exception_code not in evidence_packet.allowed_exception_codes:
        errors.append(_error("UNKNOWN_EXCEPTION_CODE", "Exception code is not allowed."))
    if response.recommended_action_code not in evidence_packet.allowed_action_codes:
        errors.append(_error("UNKNOWN_ACTION_CODE", "Action code is not allowed."))
    if len(response.explanation) > 500:
        errors.append(_error("EXPLANATION_TOO_LONG", "Explanation exceeds 500 characters."))
    bounded_free_text = " ".join(
        [response.hypothesis_code, response.explanation, *response.missing_evidence]
    )
    if _AUTHORITATIVE_STATE.search(bounded_free_text):
        errors.append(
            _error("FINAL_STATE_FORBIDDEN", "AI output cannot set or authorize final case state.")
        )
    if _AUTHORITATIVE_AMOUNT.search(bounded_free_text):
        errors.append(
            _error("CALCULATED_AMOUNT_FORBIDDEN", "AI output cannot assert calculated amounts.")
        )

    known_identifiers = {
        value.casefold() for value in evidence_packet.available_identifier_values()
    }
    narration_by_source: dict[str, str] = {}
    for snippet in evidence_packet.raw_narration_snippets:
        source, separator, text = snippet.partition(": ")
        if separator:
            narration_by_source[source] = text
    for identifier in response.extracted_identifiers or []:
        source_text = narration_by_source.get(identifier.source_field)
        token_known = identifier.token.casefold() in known_identifiers
        token_in_source = (
            source_text is not None
            and identifier.token.casefold() in source_text.casefold()
        )
        if source_text is None:
            errors.append(
                _error(
                    "UNKNOWN_SOURCE_FIELD",
                    f"Identifier source field is absent: {identifier.source_field}",
                )
            )
        elif not token_known and not token_in_source:
            errors.append(
                _error(
                    "INVENTED_IDENTIFIER",
                    f"Identifier is absent from evidence: {identifier.token}",
                )
            )

    return ValidationResult(valid=not errors, errors=errors)
