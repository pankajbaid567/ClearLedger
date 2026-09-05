from packages.domain.enums import CaseState, ExceptionCode


def test_exception_taxonomy_contains_all_prd_codes() -> None:
    assert len(ExceptionCode) == 23
    assert ExceptionCode.DOUBLE_ALLOCATION_ATTEMPT.value == "DOUBLE_ALLOCATION_ATTEMPT"


def test_case_state_uses_stable_wire_value() -> None:
    assert CaseState.PENDING_WITHIN_SLA.value == "PENDING_WITHIN_SLA"
