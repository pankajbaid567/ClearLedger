from __future__ import annotations

import csv
import random
import tempfile
from datetime import UTC, date, datetime
from functools import lru_cache
from pathlib import Path

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from generator.policies import holiday_dates, load_holidays
from generator.scenarios import generate_clean_lifecycle
from packages.domain.enums import ActorType, DecisionLevel, Direction
from packages.domain.exceptions import InvariantError
from scripts.benchmark_common import ROOT, SOURCE_FILENAMES, source_files
from services.normalization.policy import load_policy
from services.reconciliation.evidence import EvidenceEdge, EvidenceGraph
from services.reconciliation.orchestrator import run_reconciliation, to_prediction_report

POLICY = load_policy(ROOT / "policies" / "settlement_policy.v1.json")
HOLIDAYS = holiday_dates(load_holidays())


@given(seed=st.integers(min_value=0, max_value=2**31 - 1))
@settings(max_examples=30, deadline=None)
def test_generated_settlement_components_balance_exactly(seed: int) -> None:
    scenario = generate_clean_lifecycle(seed, 1, POLICY, HOLIDAYS, date(2026, 8, 1))
    settlement = scenario.records.settlements[0]
    signed_components = sum(
        component.amount_paise
        if component.direction == Direction.CREDIT
        else -component.amount_paise
        for component in scenario.records.settlement_components
    )
    assert signed_components == settlement.net_amount_paise


def _edge(target: str, amount: int) -> EvidenceEdge:
    return EvidenceEdge(
        source_entity_id="SET_001",
        target_entity_id=target,
        relationship_type="settlement_bank",
        allocated_amount_paise=amount,
        rule_id="property-test",
        rule_version="1.0.0",
        evidence_fields=["amount_paise"],
        decision_level=DecisionLevel.VERIFIED,
        actor_type=ActorType.SYSTEM,
        verification_checks=[],
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
        reconciliation_run_id="property-test",
    )


@given(
    available=st.integers(min_value=1, max_value=10**9),
    first_fraction=st.floats(min_value=0.01, max_value=1.0, allow_nan=False),
    excess=st.integers(min_value=1, max_value=10**6),
)
@settings(max_examples=50, deadline=None)
def test_verified_allocation_cannot_exceed_availability(
    available: int,
    first_fraction: float,
    excess: int,
) -> None:
    first = max(1, min(available, int(available * first_fraction)))
    graph = EvidenceGraph()
    graph.register_available_amount("SET_001", "settlement_bank", available)
    graph.register_available_amount("BANK_A", "settlement_bank", first)
    graph.register_available_amount("BANK_B", "settlement_bank", available + excess)
    graph.add_edge(_edge("BANK_A", first))

    with pytest.raises(InvariantError):
        graph.add_edge(_edge("BANK_B", available - first + excess))


@lru_cache(maxsize=1)
def _baseline_cases() -> tuple[dict, ...]:
    result = run_reconciliation(source_files(ROOT / "data" / "demo"), POLICY, "property-base")
    return tuple(case.model_dump(mode="json") for case in to_prediction_report(result).cases)


def test_reconciliation_is_idempotent_for_identical_inputs() -> None:
    first = run_reconciliation(source_files(ROOT / "data" / "demo"), POLICY, "idempotent-a")
    second = run_reconciliation(source_files(ROOT / "data" / "demo"), POLICY, "idempotent-b")
    assert to_prediction_report(first).cases == to_prediction_report(second).cases
    assert first.total_source_records == second.total_source_records


@given(shuffle_seed=st.integers(min_value=0, max_value=2**31 - 1))
@settings(max_examples=4, deadline=None)
def test_reconciliation_is_independent_of_csv_row_order(shuffle_seed: int) -> None:
    with tempfile.TemporaryDirectory(prefix="clearledger-order-") as directory_name:
        directory = Path(directory_name)
        for filename in SOURCE_FILENAMES.values():
            source = ROOT / "data" / "demo" / filename
            with source.open(newline="") as handle:
                reader = csv.DictReader(handle)
                rows = list(reader)
                fieldnames = reader.fieldnames or []
            random.Random(f"{shuffle_seed}:{filename}").shuffle(rows)
            with (directory / filename).open("w", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=fieldnames)
                writer.writeheader()
                writer.writerows(rows)
        result = run_reconciliation(source_files(directory), POLICY, "order-independent")
        actual = tuple(case.model_dump(mode="json") for case in to_prediction_report(result).cases)
        assert actual == _baseline_cases()
