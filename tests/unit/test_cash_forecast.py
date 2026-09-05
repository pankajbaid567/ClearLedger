from __future__ import annotations

from datetime import date
from pathlib import Path

from services.cash_position.forecast import calculate_cash_forecast
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


def test_cash_forecast_generates_eight_day_timeline() -> None:
    result, policy = _demo_reconciliation()
    forecast = calculate_cash_forecast(
        result.cases,
        policy=policy,
        safe_cash_paise=result.cash_position.safe_cash_paise,
    )
    assert len(forecast.days) == 8
    assert forecast.days[0].label == "T+0 (As of)"
    assert forecast.days[1].label == "T+1"
    assert forecast.days[7].label == "T+7"
    assert forecast.forecast_scope == "SETTLEMENT_RECEIPTS_ONLY"
    assert all(day.confidence_score is None for day in forecast.days)
    assert all(day.confidence_basis == "SCHEDULE_ONLY_NOT_CALIBRATED" for day in forecast.days)


def test_cash_forecast_exact_integer_balance_invariant() -> None:
    result, policy = _demo_reconciliation()
    forecast = calculate_cash_forecast(
        result.cases,
        policy=policy,
        safe_cash_paise=result.cash_position.safe_cash_paise,
    )

    for day in forecast.days:
        # Strict equation: closing == opening + inflow - deductions
        assert (
            day.closing_cash_paise
            == day.opening_cash_paise + day.expected_inflow_paise - day.scheduled_deductions_paise
        )
        assert isinstance(day.opening_cash_paise, int)
        assert isinstance(day.closing_cash_paise, int)
        assert isinstance(day.expected_inflow_paise, int)

    # Chaining invariant: day N opening == day N-1 closing
    for idx in range(1, len(forecast.days)):
        assert forecast.days[idx].opening_cash_paise == forecast.days[idx - 1].closing_cash_paise


def test_cash_forecast_reconciles_all_in_transit_settlements() -> None:
    result, policy = _demo_reconciliation()
    forecast = calculate_cash_forecast(
        result.cases,
        as_of_date=date(2026, 8, 4),
        policy=policy,
        safe_cash_paise=result.cash_position.safe_cash_paise,
    )

    # All 7 in-transit settlements in demo dataset land between 2026-08-04 and 2026-08-11
    expected_transit_total = result.cash_position.settlement_confirmed_in_transit_paise
    assert expected_transit_total == 1119439
    assert forecast.total_projected_inflow_paise == expected_transit_total
    expected_final = forecast.baseline_safe_cash_paise + expected_transit_total
    assert forecast.projected_final_cash_paise == expected_final


def test_cash_forecast_respects_non_banking_days() -> None:
    result, policy = _demo_reconciliation()
    forecast = calculate_cash_forecast(
        result.cases,
        as_of_date=date(2026, 8, 4),
        policy=policy,
    )
    # 2026-08-09 is Sunday (T+5 from 2026-08-04)
    sunday_day = forecast.days[5]
    assert sunday_day.date == "2026-08-09"
    assert sunday_day.is_banking_day is False


def test_cash_forecast_handles_empty_cases() -> None:
    forecast = calculate_cash_forecast([], as_of_date=date(2026, 8, 1), safe_cash_paise=500000)
    assert len(forecast.days) == 8
    assert forecast.total_projected_inflow_paise == 0
    assert forecast.baseline_safe_cash_paise == 500000
    assert forecast.projected_final_cash_paise == 500000
    for day in forecast.days:
        assert day.closing_cash_paise == 500000
        assert day.expected_inflow_paise == 0
