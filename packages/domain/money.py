from decimal import Decimal, InvalidOperation

from packages.domain.exceptions import InvariantError, MoneyParseError, MoneyPrecisionError

type Paise = int

_PAISE_PER_MAJOR_UNIT = Decimal(100)
_MAX_DECIMAL_PLACES = 2
_CURRENCY_SYMBOLS = {"INR": "₹"}


def _validate_currency(currency: str) -> str:
    normalized = currency.strip().upper()
    if len(normalized) != 3 or not normalized.isalpha():
        raise MoneyParseError("currency must be a three-letter alphabetic code")
    return normalized


def parse_money(value: str | int | float, currency: str = "INR") -> int:
    """Convert a major-unit amount to integer paise without binary-float arithmetic."""
    _validate_currency(currency)
    if value is None:
        raise MoneyParseError("money amount cannot be None")
    if isinstance(value, bool):
        raise MoneyParseError("boolean values are not valid money amounts")

    raw_value = value.strip() if isinstance(value, str) else str(value)
    raw_value = (
        raw_value.replace(",", "")
        .replace("₹", "")
        .replace(currency.upper(), "")
        .replace(currency.lower(), "")
        .strip()
    )
    if raw_value == "":
        raise MoneyParseError("money amount cannot be empty")

    try:
        decimal_value = Decimal(raw_value)
    except (InvalidOperation, ValueError) as exc:
        raise MoneyParseError(f"invalid money amount: {value!r}") from exc

    if not decimal_value.is_finite():
        raise MoneyParseError("money amount must be finite")

    exponent = decimal_value.as_tuple().exponent
    if not isinstance(exponent, int):
        raise MoneyParseError("money amount must be finite")

    decimal_places = max(0, -exponent)
    if decimal_places > _MAX_DECIMAL_PLACES:
        raise MoneyPrecisionError(
            f"{currency.upper()} amount has more than {_MAX_DECIMAL_PLACES} decimal places"
        )

    return int(decimal_value * _PAISE_PER_MAJOR_UNIT)


def _format_indian_integer(value: int) -> str:
    digits = str(abs(value))
    if len(digits) <= 3:
        return digits

    head = digits[:-3]
    tail = digits[-3:]
    groups: list[str] = []
    while len(head) > 2:
        groups.insert(0, head[-2:])
        head = head[:-2]
    if head:
        groups.insert(0, head)
    groups.append(tail)
    return ",".join(groups)


def format_paise(paise: int, currency: str = "INR") -> str:
    """Format integer paise with Indian digit grouping."""
    normalized_currency = _validate_currency(currency)
    if isinstance(paise, bool) or not isinstance(paise, int):
        raise MoneyParseError("paise must be an integer")

    sign = "-" if paise < 0 else ""
    absolute_paise = abs(paise)
    major = absolute_paise // 100
    minor = absolute_paise % 100
    symbol = _CURRENCY_SYMBOLS.get(normalized_currency, f"{normalized_currency} ")
    return f"{sign}{symbol}{_format_indian_integer(major)}.{minor:02d}"


def assert_exact_balance(expected_paise: int, actual_paise: int) -> None:
    """Raise if two integer-paise values differ by even one paise."""
    if expected_paise != actual_paise:
        raise InvariantError(
            f"expected {expected_paise} paise, got {actual_paise} paise"
        )
