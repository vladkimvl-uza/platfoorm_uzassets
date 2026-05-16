"""
Credit Portfolio service helpers — ported 1:1 from the monolith.

Source: index.html lines 25835-25895 (cpDaysBetween/cpMatBucket/cpYearOf/
cpBankShortName) and 24170/25982 (two versions of cpClassifyLender; we use
the more comprehensive one at line 25982).

These helpers are also re-used by the import script and the aggregate
endpoint to keep classification consistent with the monolith.
"""
from __future__ import annotations

from datetime import date
from typing import Optional


# ─── Lender type classification ────────────────────────────────────

def classify_lender(bank: Optional[str]) -> str:
    """Auto-classify a bank/lender into bond/foreign/local/state.

    Port of cpClassifyLender() at index.html:25982 (the comprehensive one).
    """
    if not bank:
        return "local"
    b = bank.lower()

    # Bonds
    if "евробонд" in b or "eurobond" in b or "(келажак)" in b or "(хумо)" in b:
        return "bond"

    # State (sovereign-grade lenders)
    if "нбу" in b:
        return "state"
    if "фонд" in b and ("реконстр" in b or "развит" in b):
        return "state"
    if "фрр" in b:
        return "state"
    if "фонд шелкового" in b or "silk road" in b:
        return "state"
    state_keywords = (
        "china development",
        "korea exim",
        "eximbank",
        "jbic",
        "ebrd",
        "world bank",
        "adb",
        "aiib",
        "jica",   # Japan International Cooperation Agency — sovereign donor
        "kfw",    # Kreditanstalt für Wiederaufbau
        "abr",    # Asian Development Bank (RU abbr)
        "абр",
    )
    for kw in state_keywords:
        if kw in b:
            return "state"

    # Local (Uzbek banks)
    local_keywords = (
        "узпромстройбанк",
        "капиталбанк",
        "алока",
        "хамкор",
        "ипотека",
        "ziraat bank uzbekistan",
        "kdb bank uzbekistan",
        "банк развития",
        "асака",
        "ситибанк",
        "микрокредит",
        "анор",
        "anor bank",
        "аксиома",
        "хумо",
        "тенге банк",
        "trustbank",
        "узнацбанк",
        "узуниверсалбанк",
        "узагроэкспортбанк",
        "узмилбанк",
        "ткб",
        "ариф",
        "узбекистон почтаси",
        "iзберегательный",
        "infinbank",
    )
    for kw in local_keywords:
        if kw in b:
            return "local"

    # Default to foreign for everything else
    return "foreign"


def classify_lender_simple(bank: Optional[str]) -> str:
    """Lighter classifier for cases where the verbose one over-aggregates.

    Port of cpClassifyLender() at index.html:24170.
    """
    if not bank:
        return "local"
    b = bank.lower()
    if "евробонд" in b or "eurobond" in b:
        return "bond"
    if any(
        kw in b
        for kw in (
            "mufg",
            "abu dhabi",
            "jp morgan",
            "china development",
            "шелкового",
            "шёлкового",
            "korea exim",
            "ifi",
            "ebrd",
        )
    ):
        return "foreign"
    if "нбу" in b or "фрру" in b or "фонд реконструкции" in b:
        return "state"
    return "local"


# ─── Bank short name ──────────────────────────────────────────────

def bank_short_name(bank: Optional[str]) -> str:
    """Strip legal-entity prefixes and quotes for grouping concentration.

    Port of cpBankShortName() at index.html:25870.
    """
    if not bank:
        return ""
    s = bank
    for prefix in ("АКБ ", "АО ", "ЧАБ ", "ООО "):
        s = s.replace(prefix, "")
    s = s.replace('"', "").strip()
    return s


# ─── Date helpers ─────────────────────────────────────────────────

def days_between(d1: Optional[date], d2: Optional[date]) -> Optional[int]:
    """Days from d1 to d2 (positive if d2 is later)."""
    if d1 is None or d2 is None:
        return None
    return (d2 - d1).days


def maturity_bucket(due: Optional[date], as_of: date) -> str:
    """Categorize a date_due into UI bucket strings.

    Port of cpMatBucket() at index.html:25845.
    Buckets: 'overdue', '<1 года', '1–3 года', '3–5 лет', '>5 лет', 'unknown'
    """
    if due is None:
        return "unknown"
    d = days_between(as_of, due)
    if d is None:
        return "unknown"
    if d < 0:
        return "overdue"
    if d <= 365:
        return "<1 года"
    if d <= 365 * 3:
        return "1–3 года"
    if d <= 365 * 5:
        return "3–5 лет"
    return ">5 лет"


def year_of(due: Optional[date]) -> Optional[int]:
    """Return year, or None for None input."""
    if due is None:
        return None
    return due.year


# ─── Lender type metadata (color/label) ───────────────────────────

LENDER_TYPE_META = {
    "bond": {"label": "Бонд", "full": "Еврооблигации", "color": "#C99B5C"},
    "foreign": {
        "label": "Иностранный",
        "full": "Иностранные банки и фонды",
        "color": "#5DBFA1",
    },
    "local": {
        "label": "Местный",
        "full": "Местные коммерческие банки",
        "color": "#5478B0",
    },
    "state": {
        "label": "Государственный",
        "full": "Государственные банки и фонды",
        "color": "#C97070",
    },
}


CURRENCY_COLORS = {
    "USD": "#7F77DD",
    "EUR": "#0A7B5E",
    "CNY": "#EF9F27",
    "JPY": "#E24B4A",
    "SDR": "#9C8AC8",
    "RUB": "#5B7FBC",
    "UZS": "#888780",
}
