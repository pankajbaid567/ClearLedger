class ClearLedgerError(Exception):
    """Base exception for expected ClearLedger domain failures."""


class MoneyParseError(ClearLedgerError, ValueError):
    """Raised when a monetary input cannot be parsed safely."""


class MoneyPrecisionError(MoneyParseError):
    """Raised when an amount exceeds the currency precision policy."""


class InvariantViolation(ClearLedgerError):
    """Raised when an authoritative financial invariant fails."""


class InvariantError(InvariantViolation):
    """Raised when exact deterministic reconciliation invariants do not hold."""
