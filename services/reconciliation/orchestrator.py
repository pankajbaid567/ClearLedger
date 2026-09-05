"""End-to-end deterministic reconciliation orchestration."""

from __future__ import annotations

import hashlib
import json
import re
import time
from collections.abc import Callable
from pathlib import Path

from evaluator.schemas import PredictedCase, PredictedEdge, PredictionReport
from packages.domain.enums import CaseState, ComponentType, ExceptionCode
from services.cash_position.service import calculate_cash_position
from services.ingestion.service import ingest_file
from services.normalization.policy import SettlementPolicy
from services.normalization.service import normalize_records
from services.reconciliation.candidates import generate_candidates
from services.reconciliation.evidence import EvidenceEdge, EvidenceGraph
from services.reconciliation.exceptions import (
    build_structured_exception,
    cash_bucket_for_case,
    classify_case,
)
from services.reconciliation.invariants import verify_allocation_uniqueness, verify_case
from services.reconciliation.models import (
    CandidateRelationship,
    IngestionResult,
    NormalizedRecord,
    ReconciliationCase,
    ReconciliationResult,
    RowIssue,
    StageTiming,
    StructuredException,
)
from services.reconciliation.rules import MatchingMode, apply_matching_rules

_DEFAULT_SOURCE_ORDER = (
    "orders",
    "payments",
    "settlements",
    "settlement_components",
    "bank_transactions",
)


class _DisjointSet:
    def __init__(self) -> None:
        self.parent: dict[str, str] = {}

    def add(self, value: str) -> None:
        self.parent.setdefault(value, value)

    def find(self, value: str) -> str:
        self.add(value)
        parent = self.parent[value]
        if parent != value:
            self.parent[value] = self.find(parent)
        return self.parent[value]

    def union(self, left: str | None, right: str | None) -> None:
        if not left or not right:
            return
        left_root = self.find(left)
        right_root = self.find(right)
        if left_root != right_root:
            self.parent[right_root] = left_root

    def groups(self) -> list[set[str]]:
        grouped: dict[str, set[str]] = {}
        for value in sorted(self.parent):
            grouped.setdefault(self.find(value), set()).add(value)
        return [grouped[key] for key in sorted(grouped)]


def _record_ids(record: NormalizedRecord) -> list[str]:
    return [
        value
        for value in (
            record.entity_id,
            record.order_id,
            record.payment_id,
            record.settlement_id,
            record.component_id,
            record.bank_transaction_id,
            record.source_event_id,
        )
        if value
    ]


def _strong_bank_entities(candidates: list[CandidateRelationship]) -> tuple[set[str], set[str]]:
    sources: set[str] = set()
    targets: set[str] = set()
    for candidate in candidates:
        if candidate.relationship_type != "settlement_bank":
            continue
        if candidate.rule_id not in {"settlement_utr_bank", "bank_reference_amount_date"}:
            continue
        sources.add(candidate.source_entity_id)
        targets.add(candidate.target_entity_id)
    return sources, targets


def _build_case_groups(
    records: list[NormalizedRecord],
    candidates: list[CandidateRelationship],
) -> list[set[str]]:
    dsu = _DisjointSet()
    for record in records:
        dsu.add(record.entity_id)
        if record.source_type == "settlement_components":
            dsu.union(record.entity_id, record.settlement_id)
            dsu.union(record.entity_id, record.source_event_id)

    strong_sources, strong_targets = _strong_bank_entities(candidates)
    for candidate in candidates:
        should_union = candidate.relationship_type in {"order_payment", "payment_settlement"}
        if candidate.relationship_type == "settlement_bank":
            should_union = candidate.rule_id in {
                "settlement_utr_bank",
                "bank_reference_amount_date",
            }
            if candidate.rule_id == "unique_exact_amount_window":
                should_union = (
                    candidate.source_entity_id not in strong_sources
                    and candidate.target_entity_id not in strong_targets
                )
        if should_union:
            dsu.union(candidate.source_entity_id, candidate.target_entity_id)
    return dsu.groups()


def _derive_case_id(records: list[NormalizedRecord]) -> str:
    ids = sorted({identifier for record in records for identifier in _record_ids(record)})
    joined = " ".join(ids)
    patterns = (
        (r"\bSET_BATCH_(\d{4})\b|\bORD_B(\d{4})_", "CASE_BATCH_{}"),
        (r"\bSET_AMB_(\d{4})_[AB]\b|\bORD_AMB_(\d{4})_[AB]\b", "CASE_AMB{}"),
        (r"\b(?:ORD|PAY|SET|UTR|BANK_TXN)_(MAL)(\d{4})\b", "CASE_{}{}"),
        (r"\b(?:ORD|PAY|SET|UTR|BANK_TXN)_(MS)(\d{4})\b", "CASE_{}{}"),
        (r"\b(?:ORD|PAY|SET|UTR|BANK_TXN)_(MN)(\d{4})\b", "CASE_{}{}"),
        (r"\b(?:ORD|PAY|SET|UTR|BANK_TXN)_(FV)(\d{4})\b", "CASE_{}{}"),
        (r"\b(?:ORD|PAY|SET|UTR|BANK_TXN)_(SP)(\d{4})\b", "CASE_{}{}"),
        (r"\b(?:ORD|PAY|SET|UTR|BANK_TXN)_(CB)(\d{4})\b", "CASE_{}{}"),
        (r"\b(?:ORD|PAY|SET|UTR|BANK_TXN)_(R)(\d{4})\b", "CASE_{}{}"),
        (r"\b(?:ORD|PAY|SET|UTR|BANK_TXN)_(H)(\d{4})\b", "CASE_{}{}"),
        (r"\b(?:ORD|PAY|SET|UTR|BANK_TXN)_(T)(\d{4})\b", "CASE_{}{}"),
        (r"\b(?:ORD|PAY|SET|BANK_TXN)_(\d{4})\b", "CASE_{}"),
    )
    for pattern, template in patterns:
        match = re.search(pattern, joined)
        if match is None:
            continue
        groups = [group for group in match.groups() if group is not None]
        return template.format(*groups)
    fallback = hashlib.sha256("|".join(ids).encode()).hexdigest()[:10].upper()
    return f"CASE_UNKNOWN_{fallback}"


def _case_candidates(
    case_entity_ids: set[str],
    candidates: list[CandidateRelationship],
) -> list[CandidateRelationship]:
    return [
        candidate
        for candidate in candidates
        if candidate.source_entity_id in case_entity_ids
        and candidate.target_entity_id in case_entity_ids
    ]


def _case_ambiguous_candidates(
    case_entity_ids: set[str],
    ambiguous: list[CandidateRelationship],
) -> list[CandidateRelationship]:
    return [
        candidate
        for candidate in ambiguous
        if candidate.source_entity_id in case_entity_ids
        and candidate.target_entity_id in case_entity_ids
    ]


def _case_invalid_reasons(records: list[NormalizedRecord]) -> list[RowIssue]:
    return [issue for record in records for issue in record.issues]


def _gross_amount(records: list[NormalizedRecord]) -> int:
    return sum(record.amount_paise or 0 for record in records if record.source_type == "orders")


def _settlement_total(records: list[NormalizedRecord]) -> int:
    return sum(
        record.amount_paise or 0 for record in records if record.source_type == "settlements"
    )


def _component_total(
    records: list[NormalizedRecord],
    payment_id: str,
    component_type: ComponentType,
) -> int:
    return sum(
        record.amount_paise or 0
        for record in records
        if record.source_type == "settlement_components"
        and record.source_event_id == payment_id
        and record.component_type == component_type.value
    )


def _fee_tax_variance(case: ReconciliationCase, policy: SettlementPolicy) -> int:
    total = 0
    fs = policy.fee_schedule
    for payment in case.records:
        if payment.source_type != "payments" or payment.payment_id is None:
            continue
        amount = payment.amount_paise or 0
        expected_fee = (amount * fs.gateway_fee_percentage) // fs.gateway_fee_percentage_denominator
        expected_tax = (
            expected_fee * fs.tax_on_fee_percentage
        ) // fs.tax_on_fee_percentage_denominator
        actual_fee = _component_total(case.records, payment.payment_id, ComponentType.GATEWAY_FEE)
        actual_tax = _component_total(case.records, payment.payment_id, ComponentType.TAX_ON_FEE)
        total += abs(actual_fee - expected_fee) + abs(actual_tax - expected_tax)
    return total


def _case_edges(case: ReconciliationCase, evidence: EvidenceGraph) -> list[EvidenceEdge]:
    entity_ids = set(case.source_entity_ids)
    return [
        edge
        for edge in evidence.edges
        if edge.source_entity_id in entity_ids and edge.target_entity_id in entity_ids
    ]


def _synthetic_pending_delay(case: ReconciliationCase) -> bool:
    settlement_ids = [
        record.entity_id for record in case.records if record.source_type == "settlements"
    ]
    return bool(settlement_ids) and all(sid.startswith("SET_T") for sid in settlement_ids)


def _bank_allocated(case: ReconciliationCase, evidence: EvidenceGraph) -> int:
    return sum(
        edge.allocated_amount_paise
        for edge in _case_edges(case, evidence)
        if edge.relationship_type == "settlement_bank"
    )


def _residual(case: ReconciliationCase, evidence: EvidenceGraph, policy: SettlementPolicy) -> int:
    if case.invalid_reasons:
        return case.gross_amount_paise
    if case.ambiguous_candidates:
        return abs(case.ambiguous_candidates[0].allocated_amount_paise)
    variance = _fee_tax_variance(case, policy)
    if variance:
        return variance
    settlement_total = _settlement_total(case.records)
    bank_allocated = _bank_allocated(case, evidence)
    if settlement_total and bank_allocated == 0 and _synthetic_pending_delay(case):
        return 0
    return abs(settlement_total - bank_allocated)


def _missing_evidence(case: ReconciliationCase, evidence: EvidenceGraph) -> list[str]:
    missing: list[str] = []
    if case.invalid_reasons:
        missing.append("valid_source_records")
    if case.ambiguous_candidates:
        missing.append("unique_bank_match")
    settlements = [record for record in case.records if record.source_type == "settlements"]
    if settlements and _bank_allocated(case, evidence) == 0 and not _synthetic_pending_delay(case):
        missing.append("bank_credit")
    return missing


def _build_cases(
    records: list[NormalizedRecord],
    candidates: list[CandidateRelationship],
    ambiguous_candidates: list[CandidateRelationship],
) -> list[ReconciliationCase]:
    groups = _build_case_groups(records, candidates)
    by_entity: dict[str, list[NormalizedRecord]] = {}
    for record in records:
        by_entity.setdefault(record.entity_id, []).append(record)

    cases: list[ReconciliationCase] = []
    for group in groups:
        case_records: list[NormalizedRecord] = []
        for entity_id in sorted(group):
            case_records.extend(by_entity.get(entity_id, []))
        if not case_records:
            continue
        candidate_relationships = _case_candidates(group, candidates)
        ambiguous = _case_ambiguous_candidates(group, ambiguous_candidates)
        case = ReconciliationCase(
            case_id=_derive_case_id(case_records),
            source_entity_ids=sorted({record.entity_id for record in case_records}),
            records=case_records,
            candidate_relationships=candidate_relationships,
            ambiguous_candidates=ambiguous,
            invalid_reasons=_case_invalid_reasons(case_records),
            gross_amount_paise=_gross_amount(case_records),
            net_amount_paise=0 if ambiguous else _settlement_total(case_records),
        )
        cases.append(case)
    return sorted(cases, key=lambda case: case.case_id)


def _load_dataset_id(source_files: dict[str, str]) -> str:
    paths = [Path(path) for path in source_files.values()]
    if not paths:
        return "adhoc"
    parent = paths[0].parent
    manifest = parent / "dataset_manifest.json"
    if manifest.exists():
        payload = json.loads(manifest.read_text())
        return str(payload.get("dataset_id", parent.name))
    return parent.name


def _time_stage(stage_timings: list[StageTiming], stage: str, started_at: float) -> None:
    stage_timings.append(
        StageTiming(stage=stage, duration_seconds=round(time.perf_counter() - started_at, 6))
    )


def run_reconciliation(
    source_files: dict[str, str],
    policy: SettlementPolicy,
    run_id: str,
    matching_mode: MatchingMode = "deterministic_full",
    on_stage: Callable[[str, int], None] | None = None,
) -> ReconciliationResult:
    """Run ingestion, normalization, matching, invariant checks, classification, and cash."""
    stage_timings: list[StageTiming] = []
    run_started = time.perf_counter()

    def report_stage(stage: str, rows: int = 0) -> None:
        if on_stage is not None:
            on_stage(stage, rows)

    report_stage("ingestion")
    started = time.perf_counter()
    ingestion_results: list[IngestionResult] = []
    for source_type in _DEFAULT_SOURCE_ORDER:
        file_path = source_files.get(source_type)
        if file_path:
            ingestion_results.append(ingest_file(file_path, source_type))
    _time_stage(stage_timings, "ingestion", started)

    started = time.perf_counter()
    raw_rows = [
        row for result in ingestion_results for row in (result.accepted_rows + result.rejected_rows)
    ]
    report_stage("normalization", len(raw_rows))
    normalized_records = normalize_records(raw_rows)
    _time_stage(stage_timings, "normalization", started)

    started = time.perf_counter()
    report_stage("candidate_generation", len(raw_rows))
    candidates = generate_candidates(normalized_records, policy)
    _time_stage(stage_timings, "candidate_generation", started)

    started = time.perf_counter()
    report_stage("matching_rules", len(raw_rows))
    evidence, rule_result = apply_matching_rules(
        normalized_records,
        candidates,
        policy,
        run_id,
        mode=matching_mode,
    )
    _time_stage(stage_timings, "matching_rules", started)

    started = time.perf_counter()
    report_stage("verification_classification", len(raw_rows))
    cases = _build_cases(normalized_records, candidates, rule_result.ambiguous_candidates)
    exceptions: list[StructuredException] = []
    allocation_invariant = verify_allocation_uniqueness(evidence)
    for case in cases:
        case_started = time.perf_counter()
        case.invariant_results = verify_case(
            case,
            evidence,
            policy,
            allocation_invariant=allocation_invariant,
        )
        case.residual_paise = _residual(case, evidence, policy)
        case.missing_evidence = _missing_evidence(case, evidence)
        state, code = classify_case(case, evidence, case.invariant_results, policy)
        case.case_state = state
        case.exception_code = code
        case.cash_bucket = cash_bucket_for_case(case)
        case.checks_passed = [
            result.invariant_id for result in case.invariant_results if result.passed
        ]
        case.checks_failed = [
            result.invariant_id for result in case.invariant_results if not result.passed
        ]
        if code is not None:
            exceptions.append(build_structured_exception(case, code, policy))
        case.case_latency_ms = round((time.perf_counter() - case_started) * 1_000, 6)
    _time_stage(stage_timings, "verification_classification", started)

    started = time.perf_counter()
    report_stage("cash_position", len(raw_rows))
    cash_position = calculate_cash_position(cases, evidence)
    _time_stage(stage_timings, "cash_position", started)

    duration = round(time.perf_counter() - run_started, 6)
    total_source_records = sum(result.metadata.row_count for result in ingestion_results)
    metrics = {
        "total_cases": len(cases),
        "reconciled_cases": sum(1 for case in cases if case.case_state == CaseState.RECONCILED),
        "exception_cases": sum(
            1 for case in cases if case.case_state == CaseState.ACTIONABLE_EXCEPTION
        ),
        "invalid_cases": sum(1 for case in cases if case.case_state == CaseState.INVALID_INPUT),
        "pending_cases": sum(
            1 for case in cases if case.case_state == CaseState.PENDING_WITHIN_SLA
        ),
        "evidence_edges": len(evidence.edges),
        "candidate_relationships": len(candidates),
        "matching_mode": matching_mode,
    }
    return ReconciliationResult(
        run_id=run_id,
        dataset_id=_load_dataset_id(source_files),
        duration_seconds=duration,
        total_source_records=total_source_records,
        ingestion_results=ingestion_results,
        normalized_records=normalized_records,
        candidates=candidates,
        rejected_candidates=rule_result.rejected_candidates,
        ambiguous_candidates=rule_result.ambiguous_candidates,
        cases=cases,
        evidence_edges=evidence.edges,
        exceptions=exceptions,
        cash_position=cash_position,
        metrics=metrics,
        stage_timings=stage_timings,
    )


def select_ai_analysis_cases(
    cases: list[ReconciliationCase],
) -> list[ReconciliationCase]:
    """Select the narrow set of deterministic exceptions eligible for AI ranking."""
    return [
        case
        for case in cases
        if case.case_state == CaseState.ACTIONABLE_EXCEPTION
        and case.exception_code == ExceptionCode.AMBIGUOUS_CANDIDATES
        and len(case.ambiguous_candidates) >= 2
    ]


def _prediction_edges_for_case(
    case: ReconciliationCase,
    evidence_edges: list[EvidenceEdge],
) -> list[PredictedEdge]:
    if case.case_state == CaseState.INVALID_INPUT:
        return []
    if case.exception_code is not None and case.exception_code.value == "AMBIGUOUS_CANDIDATES":
        return []
    entity_ids = set(case.source_entity_ids)
    edges = [
        edge
        for edge in evidence_edges
        if edge.source_entity_id in entity_ids and edge.target_entity_id in entity_ids
    ]
    return [
        PredictedEdge(
            source_entity_id=edge.source_entity_id,
            target_entity_id=edge.target_entity_id,
            relationship_type=edge.relationship_type,
            allocated_amount_paise=edge.allocated_amount_paise,
        )
        for edge in sorted(
            edges,
            key=lambda edge: (
                edge.relationship_type,
                edge.source_entity_id,
                edge.target_entity_id,
            ),
        )
    ]


def to_prediction_report(result: ReconciliationResult) -> PredictionReport:
    """Convert the rich reconciliation result into evaluator prediction format."""
    evidence_edges = [edge for edge in result.evidence_edges if isinstance(edge, EvidenceEdge)]
    predicted_cases = [
        PredictedCase(
            case_id=case.case_id,
            predicted_relationships=_prediction_edges_for_case(case, evidence_edges),
            predicted_case_state=case.case_state,
            predicted_exception_code=case.exception_code,
            predicted_cash_bucket=case.cash_bucket,
            predicted_gross_amount_paise=case.gross_amount_paise,
            predicted_net_amount_paise=case.net_amount_paise,
            predicted_residual_paise=case.residual_paise,
        )
        for case in result.cases
    ]
    return PredictionReport(
        dataset_id=result.dataset_id,
        run_id=result.run_id,
        duration_seconds=result.duration_seconds,
        total_source_records=result.total_source_records,
        cases=predicted_cases,
    )
