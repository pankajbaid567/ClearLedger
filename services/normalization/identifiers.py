"""Deterministic identifier cleanup and narration-token extraction."""

from __future__ import annotations

import re

from services.reconciliation.models import IdentifierToken

_NON_IDENTIFIER_CHARS = re.compile(r"[^A-Z0-9_-]+")
_TOKEN_PATTERNS: tuple[tuple[str, str, re.Pattern[str]], ...] = (
    ("payment_ids", "REGEX_PAYMENT_ID_V1", re.compile(r"\bPAY_\w+\b", re.IGNORECASE)),
    (
        "settlement_ids",
        "REGEX_SETTLEMENT_ID_V1",
        re.compile(r"\bSET_\w+\b", re.IGNORECASE),
    ),
    ("order_ids", "REGEX_ORDER_ID_V1", re.compile(r"\bORD_\w+\b", re.IGNORECASE)),
    ("utr_values", "REGEX_UTR_ALPHA_V1", re.compile(r"\bUTR\w+\b", re.IGNORECASE)),
    ("utr_values", "REGEX_UTR_NUMERIC_V1", re.compile(r"\b\d{12,22}\b")),
)


def normalize_id(raw: str) -> str:
    """Normalize source identifiers without erasing meaningful hyphen/underscore separators."""
    if raw is None:
        raise ValueError("identifier cannot be None")
    normalized = _NON_IDENTIFIER_CHARS.sub("", raw.strip().upper())
    if not normalized:
        raise ValueError("identifier cannot be empty")
    return normalized


def extract_tokens_from_narration(narration: str) -> dict[str, list[IdentifierToken]]:
    """Extract known financial identifiers from narration text using only regex rules."""
    if narration is None:
        narration = ""

    tokens: dict[str, list[IdentifierToken]] = {
        "payment_ids": [],
        "settlement_ids": [],
        "order_ids": [],
        "utr_values": [],
    }
    seen: set[tuple[str, str, str]] = set()
    for category, rule_id, pattern in _TOKEN_PATTERNS:
        for match in pattern.finditer(narration):
            raw_value = match.group(0)
            normalized = normalize_id(raw_value)
            key = (category, normalized, rule_id)
            if key in seen:
                continue
            seen.add(key)
            tokens[category].append(
                IdentifierToken(
                    category=category,
                    raw=raw_value,
                    normalized=normalized,
                    rule_id=rule_id,
                    span_start=match.start(),
                    span_end=match.end(),
                )
            )
    return tokens
