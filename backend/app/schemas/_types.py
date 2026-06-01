"""Shared Pydantic type aliases.

`MoneyDecimal` — backwards-compatible drop-in for `Decimal` that serializes
to **float** in JSON responses (not string). Resolves the systematic
backend-string vs frontend-number bug class:

    # JS side: 0 + "500" → "0500"   (string concat — wrong totals!)

Precision: IEEE-754 double has 53 bits of mantissa = safe integer up to
2^53 ≈ 9.0e15. All UZS / USD / EUR amounts on this platform are well below
this threshold (GDP of Uzbekistan ≈ 1e14 UZS, ledger amounts much smaller).

Usage: replace `Decimal` with `MoneyDecimal` in API response schemas.
Internal Decimal arithmetic remains unchanged — coercion happens only at
JSON serialization boundary.

    from app.schemas._types import MoneyDecimal

    class ClosureRow(BaseModel):
        unit_price: MoneyDecimal          # was Decimal
        market_avg: MoneyDecimal
        volume: MoneyDecimal
"""
from decimal import Decimal
from typing import Annotated

from pydantic import PlainSerializer

MoneyDecimal = Annotated[
    Decimal,
    PlainSerializer(
        lambda v: float(v) if v is not None else None,
        return_type=float,
        when_used="json",
    ),
]


# Same idea for Optional[Decimal] fields — Pydantic infers Optional from
# `MoneyDecimal | None` without extra annotation, but keep this alias for
# readability when intent is "money, may be NULL".
__all__ = ["MoneyDecimal"]
