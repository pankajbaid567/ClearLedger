from datetime import UTC, date, datetime

from services.cash_position.case_timing import case_timing
from services.cash_position.service import cash_bucket_contribution
from services.normalization.policy import load_policy


def test_bucket_rows_use_exact_aggregate_contribution() -> None:
    assert cash_bucket_contribution("AT_RISK", 10000, -37, 12000) == (37, "ABSOLUTE_RESIDUAL")
    assert cash_bucket_contribution("UNRESOLVED", 0, 0, 125) == (125, "ABSOLUTE_GROSS_EXPOSURE")
    assert cash_bucket_contribution("BANK_CONFIRMED", -50, 0, 500) == (-50, "NET_SETTLEMENT")


def test_event_age_and_sla_use_source_and_run_cutoff_not_insert_time() -> None:
    policy = load_policy()
    facts = case_timing(
        [
            {"source_type": "payments", "event_at": "2026-08-03T09:00:00+00:00"},
            {"source_type": "settlements", "event_at": "2026-08-05T09:00:00+00:00"},
        ],
        as_of=datetime(2026, 8, 8, 9, tzinfo=UTC),
        policy=policy,
        case_state="ACTIONABLE_EXCEPTION",
        review_deadline=date(2026, 8, 10),
    )
    assert facts["age_days"] == 5
    assert facts["sla_due_at"].date() == date(2026, 8, 6)
    assert facts["days_past_sla"] == 2
    assert facts["review_due_at"].date() == date(2026, 8, 10)


def test_unknown_event_is_not_substituted_with_case_creation_time() -> None:
    facts = case_timing(
        [], as_of=datetime(2026, 8, 8, tzinfo=UTC), policy=None, case_state="INVALID_INPUT"
    )
    assert facts["event_at"] is None
    assert facts["age_days"] is None
    assert facts["sla_due_at"] is None
    assert facts["days_past_sla"] is None
