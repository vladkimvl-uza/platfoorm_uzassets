"""Pure helpers / constants for Credit Scenarios."""
from __future__ import annotations

from fastapi import HTTPException


MATURITY_LABELS = {
    "overdue": "просрочено",
    "lt_1y":   "до 1 года",
    "1_3y":    "от 1 до 3 лет",
    "3_5y":    "от 3 до 5 лет",
    "gt_5y":   "более 5 лет",
}

LENDER_LABELS_RU = {
    "state":   "государство",
    "local":   "местные банки",
    "foreign": "иностранные",
    "bond":    "облигации",
}

CURRENCY_LABELS_RU = {
    "USD": "доллар США", "UZS": "сум", "CNY": "юань", "EUR": "евро",
    "JPY": "иена", "RUB": "рубль", "SDR": "СДР",
    "KZT": "тенге", "GBP": "фунт",
}

KNOWN_CURRENCIES = ["USD", "UZS", "CNY", "EUR", "JPY", "RUB", "SDR", "KZT", "GBP"]

# Pack 7.41 default risk parameters
DEFAULT_RR_BY_LENDER = {"state": 0.6, "local": 0.5, "foreign": 0.45, "bond": 0.40}
DEFAULT_PD_BY_LENDER = {"state": 0.015, "local": 0.035, "foreign": 0.020, "bond": 0.025}


def admin_only(user) -> None:
    """Pack 7.41 — email-based admin check (matches existing pattern)."""
    email = (getattr(user, "email", "") or "").lower()
    if email not in {"v.kim@uz-assets.uz"}:
        raise HTTPException(status_code=403, detail="Admin access required")
