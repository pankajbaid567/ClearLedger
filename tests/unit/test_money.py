import pytest

from packages.domain.exceptions import InvariantError, MoneyParseError, MoneyPrecisionError
from packages.domain.money import assert_exact_balance, format_paise, parse_money


@pytest.mark.parametrize(
    ("value", "expected"),
    [("1000.50", 100050), (1000, 100000), (10.25, 1025), ("-1.05", -105)],
)
def test_parse_money(value: str | int | float, expected: int) -> None:
    assert parse_money(value) == expected


def test_parse_money_rejects_excess_precision() -> None:
    with pytest.raises(MoneyPrecisionError):
        parse_money("1.001")


@pytest.mark.parametrize("value", ["", "not-money", float("nan"), float("inf"), True])
def test_parse_money_rejects_invalid_values(value: str | float | bool) -> None:
    with pytest.raises(MoneyParseError):
        parse_money(value)


def test_parse_money_rejects_none() -> None:
    with pytest.raises(MoneyParseError):
        parse_money(None)  # type: ignore[arg-type]


def test_format_paise() -> None:
    assert format_paise(48879000) == "₹4,88,790.00"
    assert format_paise(123456) == "₹1,234.56"
    assert format_paise(-105) == "-₹1.05"


def test_assert_exact_balance() -> None:
    assert_exact_balance(100, 100)
    with pytest.raises(InvariantError):
        assert_exact_balance(100, 99)
