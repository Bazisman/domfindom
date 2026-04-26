from __future__ import annotations

from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Any


MINOR_UNITS = {
    "RUB": 2,
}


class MoneyConversionError(ValueError):
    pass


def _minor_factor(currency: str) -> int:
    code = (currency or "RUB").upper()
    if code not in MINOR_UNITS:
        raise MoneyConversionError(f"Unsupported currency: {currency}")
    return 10 ** MINOR_UNITS[code]


def _as_decimal(value: Any) -> Decimal:
    if isinstance(value, bool):
        raise MoneyConversionError("Boolean is not a money value")
    try:
        decimal_value = Decimal(str(value).strip())
    except (InvalidOperation, AttributeError):
        raise MoneyConversionError(f"Invalid money value: {value!r}")
    if not decimal_value.is_finite():
        raise MoneyConversionError(f"Invalid money value: {value!r}")
    return decimal_value


def to_minor(value: Any, currency: str = "RUB") -> int:
    factor = _minor_factor(currency)
    amount = _as_decimal(value)
    quant = Decimal("1") / Decimal(factor)
    rounded = amount.quantize(quant, rounding=ROUND_HALF_UP)
    return int(rounded * factor)


def from_minor(value: int, currency: str = "RUB") -> Decimal:
    factor = _minor_factor(currency)
    if isinstance(value, bool):
        raise MoneyConversionError("Boolean is not a minor-unit value")
    try:
        minor = int(value)
    except (TypeError, ValueError):
        raise MoneyConversionError(f"Invalid minor-unit value: {value!r}")
    quant = Decimal("1") / Decimal(factor)
    return (Decimal(minor) / Decimal(factor)).quantize(quant)


def from_minor_float(value: int, currency: str = "RUB") -> float:
    return float(from_minor(value, currency))
