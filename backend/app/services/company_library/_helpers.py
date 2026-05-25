"""Pure helpers + constants for Company Library."""
from __future__ import annotations

from typing import Any, Optional
from uuid import UUID

from app.models.company import Company
from app.models.company_library import FieldDefinition


# Financial line code aliases (multiple naming conventions across reports)
LINE_REVENUE = ("revenue", "выручка", "net_revenue")
LINE_EBITDA  = ("ebitda", "EBITDA")
LINE_PROFIT  = ("profit", "net_profit", "profit_for_the_year", "netProfit")
LINE_EQUITY  = ("equity", "total_equity", "totalEquity")
LINE_DEBT    = ("debt", "totalDebt", "total_debt", "interestBearingDebt")
LINE_ASSETS  = ("totalAssets", "total_assets")


class LibraryDataPrefetch:
    """In-memory per-request cache for sync field values."""

    def __init__(self) -> None:
        # company_id → {revenue, ebitda, net_profit, total_debt, total_assets,
        #               debt_to_ebitda, equity}
        self.fin:     dict[str, dict[str, float | None]] = {}
        self.kpi:     dict[str, float | None] = {}
        self.ratings: dict[str, dict[str, str | None]] = {}
        self.year:    Optional[int] = None


def pick_first(row_map: dict[str, float | None], codes: tuple[str, ...]) -> float | None:
    for c in codes:
        v = row_map.get(c)
        if v is not None:
            return v
    return None


def company_attr_value(co: Company, source_path: str) -> Any:
    """Resolve a dotted path on the Company ORM instance."""
    if not source_path:
        return None
    obj: Any = co
    for part in source_path.split("."):
        if obj is None:
            return None
        obj = getattr(obj, part, None)
    return obj


def applies_to_scope(
    f: FieldDefinition, *,
    sector_code: Optional[str], company_id: Optional[UUID],
) -> bool:
    if f.scope_type == "all":
        return True
    if f.scope_type == "sector":
        if not sector_code:
            return False
        sv = f.scope_value or []
        return sector_code in sv if isinstance(sv, list) else False
    if f.scope_type == "companies":
        if not company_id:
            return False
        sv = f.scope_value or []
        if isinstance(sv, list):
            return str(company_id) in [str(x) for x in sv]
        return False
    return False


def compute_value(
    co: Company, field: FieldDefinition,
    prefetch: LibraryDataPrefetch,
) -> Any:
    """Resolve a field's current value from prefetch cache or company attrs."""
    src = field.source_module
    cid = str(co.id)

    if src == "companies":
        if field.source_path:
            return company_attr_value(co, field.source_path)
        return getattr(co, field.code, None)

    if src is None:
        return (co.custom_data or {}).get(field.code)

    if src in ("finmodel", "financials"):
        fin = prefetch.fin.get(cid) or {}
        if field.code in fin:
            return fin[field.code]
        return (co.custom_data or {}).get(field.code)

    if src == "kpi":
        return prefetch.kpi.get(cid)

    if src == "ratings":
        d = prefetch.ratings.get(cid) or {}
        if field.code == "rating_fitch":  return d.get("fitch")
        if field.code == "rating_sp":     return d.get("sp")
        if field.code == "rating_moodys": return d.get("moodys")
        if field.code == "rating_esg":    return d.get("esg")
        return None

    return (co.custom_data or {}).get(field.code)
