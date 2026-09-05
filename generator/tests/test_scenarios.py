"""Tests for each scenario constructor and settlement equation balance."""

from __future__ import annotations

from datetime import date

import pytest

from generator.policies import holiday_dates, load_holidays, load_policy
from generator.scenarios import (
    generate_all_scenarios,
    generate_ambiguous_case,
    generate_batched_settlement,
    generate_chargeback,
    generate_clean_lifecycle,
    generate_fee_variance,
    generate_holiday_shift,
    generate_malformed_input,
    generate_messy_narration,
    generate_missing_event,
    generate_refund,
    generate_split_settlement,
    generate_timing_delay,
)
from packages.domain.enums import CaseState, ComponentType, Direction, ExceptionCode


@pytest.fixture()
def policy():
    return load_policy()


@pytest.fixture()
def holidays():
    return holiday_dates(load_holidays())


BASE_DATE = date(2026, 8, 1)
SEED = 42


# ── Settlement equation balance ────────────────────────────────────────────


def _settlement_net(components) -> int:
    """Compute net from components using the canonical settlement equation."""
    total = 0
    for c in components:
        if c.direction == Direction.CREDIT:
            total += c.amount_paise
        else:
            total -= c.amount_paise
    return total


def _assert_settlement_equation(result, scenario_label: str) -> None:
    """For non-exception scenarios, verify settlement equation balances exactly."""
    rec = result.records

    if not rec.settlements:
        return  # no settlement to check (e.g., malformed input)

    for settlement in rec.settlements:
        sid = settlement.settlement_id
        comps = [c for c in rec.settlement_components if c.settlement_id == sid]
        computed_net = _settlement_net(comps)
        assert computed_net == settlement.net_amount_paise, (
            f"Settlement equation failed for {sid} in {scenario_label}: "
            f"computed_net={computed_net} != reported_net={settlement.net_amount_paise}"
        )


# ── Individual scenario tests ──────────────────────────────────────────────


class TestCleanLifecycle:
    def test_produces_all_record_types(self, policy, holidays):
        result = generate_clean_lifecycle(SEED, 1, policy, holidays, BASE_DATE)
        rec = result.records
        assert len(rec.orders) == 1
        assert len(rec.payments) == 1
        assert len(rec.settlements) == 1
        assert len(rec.settlement_components) == 3  # payment + fee + tax
        assert len(rec.bank_transactions) == 1

    def test_settlement_equation_balances(self, policy, holidays):
        result = generate_clean_lifecycle(SEED, 1, policy, holidays, BASE_DATE)
        _assert_settlement_equation(result, "clean_lifecycle")

    def test_ground_truth_reconciled(self, policy, holidays):
        result = generate_clean_lifecycle(SEED, 1, policy, holidays, BASE_DATE)
        assert result.truth.expected_case_state == CaseState.RECONCILED
        assert result.truth.expected_residual_paise == 0

    def test_amounts_are_integer_paise(self, policy, holidays):
        result = generate_clean_lifecycle(SEED, 1, policy, holidays, BASE_DATE)
        for o in result.records.orders:
            assert isinstance(o.order_amount_paise, int)
        for p in result.records.payments:
            assert isinstance(p.amount_paise, int)
        for s in result.records.settlements:
            assert isinstance(s.net_amount_paise, int)


class TestBatchedSettlement:
    def test_multiple_payments(self, policy, holidays):
        result = generate_batched_settlement(SEED, 100, policy, holidays, BASE_DATE)
        assert len(result.records.payments) >= 3

    def test_single_settlement(self, policy, holidays):
        result = generate_batched_settlement(SEED, 100, policy, holidays, BASE_DATE)
        assert len(result.records.settlements) == 1

    def test_equation_balances(self, policy, holidays):
        result = generate_batched_settlement(SEED, 100, policy, holidays, BASE_DATE)
        _assert_settlement_equation(result, "batched_settlement")

    def test_reconciled_zero_residual(self, policy, holidays):
        result = generate_batched_settlement(SEED, 100, policy, holidays, BASE_DATE)
        assert result.truth.expected_case_state == CaseState.RECONCILED
        assert result.truth.expected_residual_paise == 0


class TestTimingDelay:
    def test_no_bank_transaction(self, policy, holidays):
        result = generate_timing_delay(SEED, 200, policy, holidays, BASE_DATE)
        assert len(result.records.bank_transactions) == 0

    def test_pending_within_sla(self, policy, holidays):
        result = generate_timing_delay(SEED, 200, policy, holidays, BASE_DATE)
        assert result.truth.expected_case_state == CaseState.PENDING_WITHIN_SLA

    def test_equation_balances(self, policy, holidays):
        result = generate_timing_delay(SEED, 200, policy, holidays, BASE_DATE)
        _assert_settlement_equation(result, "timing_delay")


class TestHolidayShift:
    def test_reconciled(self, policy, holidays):
        result = generate_holiday_shift(SEED, 300, policy, holidays, BASE_DATE)
        assert result.truth.expected_case_state == CaseState.RECONCILED
        assert result.truth.expected_residual_paise == 0

    def test_equation_balances(self, policy, holidays):
        result = generate_holiday_shift(SEED, 300, policy, holidays, BASE_DATE)
        _assert_settlement_equation(result, "holiday_shift")


class TestRefund:
    def test_has_refund_component(self, policy, holidays):
        result = generate_refund(SEED, 400, policy, holidays, BASE_DATE)
        refund_comps = [
            c
            for c in result.records.settlement_components
            if c.component_type == ComponentType.REFUND
        ]
        assert len(refund_comps) == 1

    def test_equation_balances(self, policy, holidays):
        result = generate_refund(SEED, 400, policy, holidays, BASE_DATE)
        _assert_settlement_equation(result, "refund")

    def test_reconciled_zero_residual(self, policy, holidays):
        result = generate_refund(SEED, 400, policy, holidays, BASE_DATE)
        assert result.truth.expected_case_state == CaseState.RECONCILED
        assert result.truth.expected_residual_paise == 0


class TestChargeback:
    def test_has_chargeback_component(self, policy, holidays):
        result = generate_chargeback(SEED, 500, policy, holidays, BASE_DATE)
        cb_comps = [
            c
            for c in result.records.settlement_components
            if c.component_type == ComponentType.CHARGEBACK
        ]
        assert len(cb_comps) == 1

    def test_equation_balances(self, policy, holidays):
        result = generate_chargeback(SEED, 500, policy, holidays, BASE_DATE)
        _assert_settlement_equation(result, "chargeback")


class TestSplitSettlement:
    def test_has_reserve_hold(self, policy, holidays):
        result = generate_split_settlement(SEED, 600, policy, holidays, BASE_DATE)
        reserve = [
            c
            for c in result.records.settlement_components
            if c.component_type == ComponentType.RESERVE_HOLD
        ]
        assert len(reserve) == 1

    def test_equation_balances(self, policy, holidays):
        result = generate_split_settlement(SEED, 600, policy, holidays, BASE_DATE)
        _assert_settlement_equation(result, "split_settlement")


class TestFeeVariance:
    def test_actionable_exception(self, policy, holidays):
        result = generate_fee_variance(SEED, 700, policy, holidays, BASE_DATE)
        assert result.truth.expected_case_state == CaseState.ACTIONABLE_EXCEPTION
        assert result.truth.expected_exception_code == ExceptionCode.FEE_VARIANCE

    def test_equation_balances(self, policy, holidays):
        # Fee variance: components balance with the *actual* (bad) fee
        result = generate_fee_variance(SEED, 700, policy, holidays, BASE_DATE)
        _assert_settlement_equation(result, "fee_variance")


class TestMessyNarration:
    def test_reconciled_despite_messy_narration(self, policy, holidays):
        result = generate_messy_narration(SEED, 800, policy, holidays, BASE_DATE)
        assert result.truth.expected_case_state == CaseState.RECONCILED
        assert result.truth.expected_residual_paise == 0

    def test_has_bank_narration(self, policy, holidays):
        result = generate_messy_narration(SEED, 800, policy, holidays, BASE_DATE)
        assert len(result.records.bank_transactions) == 1
        assert len(result.records.bank_transactions[0].narration) > 0


class TestMalformedInput:
    def test_invalid_input_state(self, policy, holidays):
        result = generate_malformed_input(SEED, 900, policy, holidays, BASE_DATE)
        assert result.truth.expected_case_state == CaseState.INVALID_INPUT
        assert result.truth.expected_exception_code == ExceptionCode.DUPLICATE_SOURCE_RECORD

    def test_duplicate_order_id(self, policy, holidays):
        result = generate_malformed_input(SEED, 900, policy, holidays, BASE_DATE)
        order_ids = [o.order_id for o in result.records.orders]
        assert len(order_ids) == 2
        assert order_ids[0] == order_ids[1]  # duplicate


class TestMissingEvent:
    def test_missing_bank_credit(self, policy, holidays):
        result = generate_missing_event(SEED, 1000, policy, holidays, BASE_DATE)
        assert len(result.records.bank_transactions) == 0

    def test_actionable_exception(self, policy, holidays):
        result = generate_missing_event(SEED, 1000, policy, holidays, BASE_DATE)
        assert result.truth.expected_case_state == CaseState.ACTIONABLE_EXCEPTION
        assert result.truth.expected_exception_code == ExceptionCode.BANK_CREDIT_MISSING


class TestAmbiguousCase:
    def test_two_settlements_one_bank(self, policy, holidays):
        result = generate_ambiguous_case(SEED, 1100, policy, holidays, BASE_DATE)
        assert len(result.records.settlements) == 2
        assert len(result.records.bank_transactions) == 1

    def test_ambiguous_exception(self, policy, holidays):
        result = generate_ambiguous_case(SEED, 1100, policy, holidays, BASE_DATE)
        assert result.truth.expected_case_state == CaseState.ACTIONABLE_EXCEPTION
        assert result.truth.expected_exception_code == ExceptionCode.AMBIGUOUS_CANDIDATES

    def test_no_expected_relationships(self, policy, holidays):
        result = generate_ambiguous_case(SEED, 1100, policy, holidays, BASE_DATE)
        assert result.truth.expected_relationships == []


# ── Full dataset generation ────────────────────────────────────────────────


class TestFullGeneration:
    def test_default_distribution_produces_75_cases(self, policy, holidays):
        results = generate_all_scenarios(SEED, policy, holidays, BASE_DATE)
        assert len(results) == 75

    def test_scenario_counts_match(self, policy, holidays):
        results = generate_all_scenarios(SEED, policy, holidays, BASE_DATE)
        counts: dict[str, int] = {}
        for r in results:
            label = r.truth.scenario_label
            counts[label] = counts.get(label, 0) + 1
        assert counts["clean_lifecycle"] == 20
        assert counts["batched_settlement"] == 10
        assert counts["timing_delay"] == 7
        assert counts["holiday_shift"] == 4
        assert counts["refund"] == 6
        assert counts["chargeback"] == 4
        assert counts["split_settlement"] == 4
        assert counts["fee_variance"] == 4
        assert counts["messy_narration"] == 5
        assert counts["malformed_input"] == 4
        assert counts["missing_event"] == 4
        assert counts["ambiguous"] == 3

    def test_all_ids_are_unique(self, policy, holidays):
        results = generate_all_scenarios(SEED, policy, holidays, BASE_DATE)
        case_ids = [r.truth.case_id for r in results]
        assert len(case_ids) == len(set(case_ids)), "Duplicate case IDs found"

    def test_source_record_count_exceeds_150(self, policy, holidays):
        results = generate_all_scenarios(SEED, policy, holidays, BASE_DATE)
        total = sum(
            len(r.records.orders)
            + len(r.records.payments)
            + len(r.records.settlements)
            + len(r.records.settlement_components)
            + len(r.records.bank_transactions)
            for r in results
        )
        assert total >= 150, f"Expected ≥150 source records, got {total}"

    def test_settlement_equations_balance_for_all_non_exception_scenarios(
        self, policy, holidays
    ):
        results = generate_all_scenarios(SEED, policy, holidays, BASE_DATE)
        for r in results:
            if r.truth.expected_case_state in (
                CaseState.RECONCILED,
                CaseState.PENDING_WITHIN_SLA,
            ):
                _assert_settlement_equation(r, r.truth.scenario_label)

    def test_stress_scaling(self, policy, holidays):
        results = generate_all_scenarios(SEED, policy, holidays, BASE_DATE, count_override=150)
        assert len(results) == 150

    def test_stress_mode_is_exact_and_uses_simple_distribution(self, policy, holidays):
        results = generate_all_scenarios(
            SEED,
            policy,
            holidays,
            BASE_DATE,
            count_override=1_000,
            stress_mode=True,
        )
        counts: dict[str, int] = {}
        for result in results:
            label = result.truth.scenario_label
            counts[label] = counts.get(label, 0) + 1
        assert len(results) == 1_000
        assert counts == {"clean_lifecycle": 800, "batched_settlement": 200}
