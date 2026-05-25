"""Pure helpers for Executive Dashboard (no DB / IO)."""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from app.models.company import Company


SECTOR_COLORS: Dict[str, str] = {
    "mining":    "#7F77DD",
    "oilgas":    "#1D9E75",
    "energy":    "#EF9F27",
    "transport": "#378ADD",
    "other":     "#888780",
}
SECTOR_LABEL_RU: Dict[str, str] = {
    "mining":    "Горнодобывающий",
    "oilgas":    "Нефтегазовый",
    "energy":    "Энергетика",
    "transport": "Транспорт и коммуникации",
    "other":     "Другой сектор",
}
SECTOR_ORDER: List[str] = ["mining", "oilgas", "energy", "transport", "other"]

MONTHS_RU = ["янв", "фев", "мар", "апр", "май", "июн",
             "июл", "авг", "сен", "окт", "ноя", "дек"]


def sector_code(co: Optional[Company]) -> str:
    if not co or not co.sector:
        return "other"
    sec = co.sector
    code = (getattr(sec, "code", None) or "").lower().strip()
    name = (getattr(sec, "name_ru", None) or "").lower()
    if code in SECTOR_COLORS:
        return code
    if "нефт" in name or "газ" in name or "oil" in code or "gas" in code:
        return "oilgas"
    if "горн" in name or "metall" in name or "mining" in code:
        return "mining"
    if "энерг" in name or "energ" in code:
        return "energy"
    if "трансп" in name or "телек" in name or "transport" in code or "telecom" in code:
        return "transport"
    return "other"


def sector_label(code: str, fallback: str = "") -> str:
    return SECTOR_LABEL_RU.get(code, fallback or code.title())


def normalize_sector_code(s: str) -> str:
    """Pack 7.44: маппинг внешних кодов секторов (frontend) → внутренние."""
    if not s:
        return "other"
    if s in SECTOR_COLORS:
        return s
    low = s.lower()
    if "min" in low or "metal" in low:
        return "mining"
    if "oil" in low or "gas" in low or "нефт" in low:
        return "oilgas"
    if "energ" in low or "энерг" in low:
        return "energy"
    if "transp" in low or "comm" in low or "телек" in low or "транс" in low:
        return "transport"
    return "other"


def format_date_short(d: Any) -> Optional[str]:
    """date | datetime → 'окт 2025' формат."""
    if not d:
        return None
    if hasattr(d, "month") and hasattr(d, "year"):
        return f"{MONTHS_RU[d.month - 1]} {d.year}"
    return None


def normalize_agency(name: str) -> str:
    s = (name or "").strip().lower()
    if "fitch" in s and ("sust" in s or "sf" in s or "esg" in s):
        return "sf"
    if "fitch" in s:
        return "fitch"
    if "moody" in s:
        return "moodys"
    if "s&p" in s and "esg" in s:
        return "sp_esg"
    if "s&p" in s or "sp" in s:
        return "sp"
    if "cdp" in s:
        return "cdp"
    return s


def is_recent_2025_or_2026(d: Any) -> bool:
    if not d or not hasattr(d, "year"):
        return False
    return d.year >= 2025


def ring_score(rated: int, total: int) -> int:
    if total <= 0:
        return 0
    return round(rated / total * 100)
