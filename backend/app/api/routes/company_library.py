"""Company Library (MDM) — Phase 1 endpoints (Pack 9aJ).

Routes
------
GET    /companies/library                 — paginated list with computed columns
GET    /companies/library/{id}            — full detail for one company
PATCH  /companies/library/{id}/fields/{code}  — write single field value
GET    /companies/library/{id}/activity   — recent audit log entries for company

GET    /field-definitions                 — schema of all fields
POST   /field-definitions                 — create custom field
PATCH  /field-definitions/{code}          — update non-system field
DELETE /field-definitions/{code}          — delete custom field

GET    /library-views                     — my saved views
POST   /library-views                     — save new view
PATCH  /library-views/{id}                — update
DELETE /library-views/{id}                — delete

GET    /library-tabs                      — list all tabs
POST   /library-tabs                      — create custom tab
PATCH  /library-tabs/{code}               — update non-system tab
DELETE /library-tabs/{code}               — delete custom tab

Plus WebSocket:
WS     /ws/companies                      — global field-update broadcast
WS     /ws/companies/{id}                 — per-company subscription
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response, WebSocket, WebSocketDisconnect, status
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.security import get_current_user, require_permission
from app.database import get_db
from app.models.company import Company
from app.models.company_library import (
    FIELD_TYPES,
    SCOPE_TYPES,
    CompanyLibraryTab,
    CompanyLibraryView,
    FieldDefinition,
)
from app.models.user import User
from app.schemas.company_library import (
    FieldDefinitionCreate,
    FieldDefinitionRead,
    FieldDefinitionUpdate,
    FieldWriteRequest,
    FieldWriteResponse,
    LibraryActivityEntry,
    LibraryCompanyDetail,
    LibraryCompanyRow,
    LibraryFieldValue,
    LibraryListResponse,
    LibraryTabCreate,
    LibraryTabRead,
    LibraryTabUpdate,
    LibraryViewCreate,
    LibraryViewRead,
    LibraryViewUpdate,
)
from app.services.sync_broadcaster import GLOBAL_SCOPE, broadcaster

log = logging.getLogger(__name__)

router = APIRouter(tags=["company-library"])


# ────────────────────────────────────────────────────────────────────────
# Helpers
# ────────────────────────────────────────────────────────────────────────

async def _list_applicable_fields(
    db: AsyncSession,
    *,
    sector_code: Optional[str] = None,
    company_id: Optional[UUID] = None,
) -> list[FieldDefinition]:
    """Return fields applicable to the given sector/company scope."""
    res = await db.execute(
        select(FieldDefinition).order_by(FieldDefinition.sort_order, FieldDefinition.code)
    )
    all_fields = list(res.scalars().all())

    def applies(f: FieldDefinition) -> bool:
        if f.scope_type == "all":
            return True
        if f.scope_type == "sector":
            if not sector_code:
                return False
            sv = f.scope_value or []
            if isinstance(sv, list):
                return sector_code in sv
            return False
        if f.scope_type == "companies":
            if not company_id:
                return False
            sv = f.scope_value or []
            if isinstance(sv, list):
                return str(company_id) in [str(x) for x in sv]
            return False
        return False

    return [f for f in all_fields if applies(f)]


def _company_attr_value(co: Company, source_path: str) -> Any:
    """Resolve a dotted path on the Company ORM instance. For source_module='companies'."""
    if not source_path:
        return None
    obj: Any = co
    for part in source_path.split("."):
        if obj is None:
            return None
        obj = getattr(obj, part, None)
    return obj


# ── Phase 4a · Batch sync prefetch ──────────────────────────────────────
# A single _LibraryDataPrefetch is built once per list/detail request and
# stuffed with the latest finmodel/kpi/ratings facts for ALL companies in
# scope. _compute_value then reads from it in O(1).

class _LibraryDataPrefetch:
    """In-memory cache for one HTTP request."""

    def __init__(self) -> None:
        # company_id → {revenue, ebitda, profit, total_debt, total_assets,
        #               debt_to_ebitda, equity, kpi_completion}
        self.fin:     dict[str, dict[str, float | None]] = {}
        self.kpi:     dict[str, float | None] = {}
        self.ratings: dict[str, dict[str, str | None]] = {}  # co_id → {fitch, sp, moodys, esg}
        self.year:    int | None = None


_LINE_REVENUE  = ("revenue", "выручка", "net_revenue")
_LINE_EBITDA   = ("ebitda", "EBITDA")
_LINE_PROFIT   = ("profit", "net_profit", "profit_for_the_year", "netProfit")
_LINE_EQUITY   = ("equity", "total_equity", "totalEquity")
_LINE_DEBT     = ("debt", "totalDebt", "total_debt", "interestBearingDebt")
_LINE_ASSETS   = ("totalAssets", "total_assets")


def _pick_first(row_map: dict[str, float | None], codes: tuple[str, ...]) -> float | None:
    for c in codes:
        v = row_map.get(c)
        if v is not None:
            return v
    return None


async def _prefetch_for(db: AsyncSession, company_ids: list[UUID]) -> _LibraryDataPrefetch:
    """Single trip per source-module. Returns the latest-year fact for each."""
    pref = _LibraryDataPrefetch()
    if not company_ids:
        return pref

    from sqlalchemy import desc, func as sa_func

    ids_s = [str(i) for i in company_ids]

    # ── Financials: pick latest year per (company, standard, report_type)
    try:
        from app.models.financial import FinancialReport, FinancialLine
    except Exception:
        FinancialReport = None  # type: ignore
        FinancialLine   = None  # type: ignore

    if FinancialReport is not None and FinancialLine is not None:
        # Pick ALL IFRS PL+BS reports for in-scope companies. We'll pick the
        # most-recent year per company in Python with a "must have revenue/equity"
        # filter so blank placeholder rows don't drown out real prior-year data.
        reports_q = (
            select(FinancialReport)
            .where(FinancialReport.company_id.in_(company_ids))
            .where(FinancialReport.report_type.in_(("PL", "BS")))
            .where(FinancialReport.standard == "IFRS")
        )
        reports = list((await db.execute(reports_q)).scalars().all())

        if reports:
            report_ids = [r.id for r in reports]
            lines_q = select(FinancialLine).where(FinancialLine.report_id.in_(report_ids))
            lines = list((await db.execute(lines_q)).scalars().all())

            # Group lines by report_id → {code: value}
            lines_by_report: dict[str, dict[str, float | None]] = {}
            for ln in lines:
                rid = str(ln.report_id)
                v = ln.value
                if v is None:
                    continue
                try:
                    v = float(v)
                except (TypeError, ValueError):
                    continue
                lines_by_report.setdefault(rid, {})[ln.line_code] = v

            # Group reports by (cid, rtype) → list of (year, scale, code_map)
            by_cid_type: dict[tuple[str, str], list[tuple[int, int, dict[str, float | None]]]] = {}
            for r in reports:
                cid   = str(r.company_id)
                rtype = r.report_type
                scale = r.unit_scale or 1
                codes = lines_by_report.get(str(r.id), {})
                by_cid_type.setdefault((cid, rtype), []).append((r.year, scale, codes))

            # For each (cid, rtype), pick the latest year where the discriminator
            # line is non-zero. PL: discriminator = revenue. BS: discriminator = equity OR totalAssets.
            picked: dict[str, dict[str, tuple[int, int, dict[str, float | None]]]] = {}
            for (cid, rtype), entries in by_cid_type.items():
                entries.sort(key=lambda e: -e[0])  # latest year first
                chosen: tuple[int, int, dict[str, float | None]] | None = None
                for yr, scale, codes in entries:
                    disc = (_pick_first(codes, _LINE_REVENUE) if rtype == "PL"
                            else (_pick_first(codes, _LINE_EQUITY) or _pick_first(codes, _LINE_ASSETS)))
                    if disc and disc != 0:
                        chosen = (yr, scale, codes); break
                if chosen is None and entries:
                    chosen = entries[0]  # fall back to latest year, even if blank
                if chosen is not None:
                    picked.setdefault(cid, {})[rtype] = chosen
                    if pref.year is None or chosen[0] > (pref.year or 0):
                        pref.year = chosen[0]

            # Roll up into final dict (apply scale)
            for cid, by_type in picked.items():
                pl_entry = by_type.get("PL")
                bs_entry = by_type.get("BS")
                pl_scale, pl_codes = (pl_entry[1], pl_entry[2]) if pl_entry else (1, {})
                bs_scale, bs_codes = (bs_entry[1], bs_entry[2]) if bs_entry else (1, {})

                def _v(codes, names, scale):
                    raw = _pick_first(codes, names)
                    return None if raw is None else raw * scale

                revenue = _v(pl_codes, _LINE_REVENUE, pl_scale)
                ebitda  = _v(pl_codes, _LINE_EBITDA,  pl_scale)
                profit  = _v(pl_codes, _LINE_PROFIT,  pl_scale)
                equity  = _v(bs_codes, _LINE_EQUITY,  bs_scale)
                debt    = _v(bs_codes, _LINE_DEBT,    bs_scale)
                assets  = _v(bs_codes, _LINE_ASSETS,  bs_scale)
                de = (debt / ebitda) if (debt is not None and ebitda not in (None, 0)) else None
                pref.fin[cid] = {
                    "revenue":         revenue,
                    "ebitda":          ebitda,
                    "net_profit":      profit,
                    "total_debt":      debt,
                    "total_assets":    assets,
                    "debt_to_ebitda":  de,
                    "equity":          equity,
                }

    # ── Ratings (latest per agency per company)
    try:
        from app.models.agency_rating import AgencyRating
    except Exception:
        AgencyRating = None  # type: ignore
    if AgencyRating is not None:
        rq = (
            select(AgencyRating)
            .where(AgencyRating.company_id.in_(company_ids))
            .order_by(AgencyRating.company_id, AgencyRating.agency, desc(AgencyRating.rating_date))
        )
        for ar in (await db.execute(rq)).scalars().all():
            cid = str(ar.company_id)
            d = pref.ratings.setdefault(cid, {})
            ag = (ar.agency or "").lower()
            if "fitch" in ag and "sus" not in ag and "esg" not in ag:
                d.setdefault("fitch", ar.rating)
            elif "s&p" in ag or ag == "sp" or "standard" in ag:
                d.setdefault("sp", ar.rating)
            elif "moody" in ag:
                d.setdefault("moodys", ar.rating)
            elif "sus" in ag or "esg" in ag or getattr(ar, "is_esg", False):
                d.setdefault("esg", ar.rating or ar.score)

    # ── KPI completion (overall weighted, current year, no year filter — pick max year)
    try:
        from app.models.bp_kpi import KpiManager, KpiIndicator
    except Exception:
        KpiManager = None  # type: ignore
        KpiIndicator = None  # type: ignore
    if KpiManager is not None and KpiIndicator is not None:
        # Latest year per company
        year_q = (
            select(KpiManager.company_id, sa_func.max(KpiManager.year))
            .where(KpiManager.company_id.in_(company_ids))
            .group_by(KpiManager.company_id)
        )
        latest_year: dict[str, int] = {
            str(cid): yr for cid, yr in (await db.execute(year_q)).all()
        }
        if latest_year:
            # Fetch managers + indicators for those (company, year) pairs
            mgrs_q = (
                select(KpiManager)
                .where(KpiManager.company_id.in_(company_ids))
            )
            mgrs = list((await db.execute(mgrs_q)).scalars().all())
            relevant_mgrs = [m for m in mgrs if str(m.company_id) in latest_year
                             and m.year == latest_year[str(m.company_id)]]
            mgr_ids = [m.id for m in relevant_mgrs]
            inds: list[Any] = []
            if mgr_ids:
                ind_q = select(KpiIndicator).where(KpiIndicator.manager_id.in_(mgr_ids))
                inds = list((await db.execute(ind_q)).scalars().all())

            mgr_to_co = {str(m.id): str(m.company_id) for m in relevant_mgrs}
            sum_w: dict[str, float] = {}
            sum_wr: dict[str, float] = {}
            for ind in inds:
                cid = mgr_to_co.get(str(ind.manager_id))
                if not cid:
                    continue
                try:
                    w = float(ind.weight or 0)
                    plan = float(ind.plan_year) if ind.plan_year is not None else None
                    fact = float(ind.fact_year) if ind.fact_year is not None else None
                except (TypeError, ValueError):
                    continue
                if w <= 0 or plan is None or plan == 0 or fact is None:
                    continue
                ratio = min(2.0, fact / plan)
                sum_w[cid]  = sum_w.get(cid, 0.0) + w
                sum_wr[cid] = sum_wr.get(cid, 0.0) + w * ratio
            for cid, w in sum_w.items():
                if w > 0:
                    pref.kpi[cid] = round((sum_wr[cid] / w) * 100, 1)

    return pref


def _compute_value(co: Company, field: FieldDefinition, prefetch: _LibraryDataPrefetch) -> Any:
    """Compute a field's current value for a company, using the per-request
    prefetch cache for sync fields."""
    src = field.source_module
    cid = str(co.id)

    if src == "companies":
        if field.source_path:
            return _company_attr_value(co, field.source_path)
        return getattr(co, field.code, None)

    if src is None:
        return (co.custom_data or {}).get(field.code)

    if src in ("finmodel", "financials"):
        fin = prefetch.fin.get(cid) or {}
        if field.code in fin:
            return fin[field.code]
        # Cached in custom_data if any
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

    # Fallback for unknown source_module
    return (co.custom_data or {}).get(field.code)


# ────────────────────────────────────────────────────────────────────────
# /companies/library — index + detail
# ────────────────────────────────────────────────────────────────────────

@router.get("/library/companies", response_model=LibraryListResponse)
async def list_library(
    sector: Optional[str] = Query(None),
    search: Optional[str] = Query(None, max_length=128),
    view_id: Optional[UUID] = Query(None),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> LibraryListResponse:
    """Paginated company list with computed field values per row."""
    q = select(Company).options(selectinload(Company.sector))
    if sector:
        from app.models.sector import Sector
        q = q.join(Sector, Sector.id == Company.sector_id).where(Sector.code == sector)
    if search:
        needle = f"%{search.lower()}%"
        q = q.where(
            (Company.name_ru.ilike(needle))
            | (Company.name_short.ilike(needle))
            | (Company.inn.ilike(needle))
        )
    q = q.order_by(Company.sort_order, Company.name_ru).limit(limit).offset(offset)
    companies = list((await db.execute(q)).scalars().all())

    # Total — separate count
    total_q = select(Company)
    if sector:
        from app.models.sector import Sector
        total_q = total_q.join(Sector, Sector.id == Company.sector_id).where(Sector.code == sector)
    if search:
        needle = f"%{search.lower()}%"
        total_q = total_q.where(
            (Company.name_ru.ilike(needle))
            | (Company.name_short.ilike(needle))
            | (Company.inn.ilike(needle))
        )
    total = len(list((await db.execute(total_q)).scalars().all()))

    # Compute fields for each row — single prefetch round-trip for all sync data
    fields_def = await _list_applicable_fields(db, sector_code=sector)
    prefetch = await _prefetch_for(db, [c.id for c in companies])
    rows: list[LibraryCompanyRow] = []
    for co in companies:
        co_fields: dict[str, Any] = {}
        for f in fields_def:
            try:
                co_fields[f.code] = _compute_value(co, f, prefetch)
            except Exception:
                co_fields[f.code] = None
        rows.append(LibraryCompanyRow(
            id=co.id,
            code=getattr(co, "code", None),
            name_ru=co.name_ru,
            name_short=getattr(co, "name_short", None),
            sector_id=getattr(co, "sector_id", None),
            sector_name=getattr(co.sector, "name_ru", None) if getattr(co, "sector", None) else None,
            fields=co_fields,
        ))

    # User's saved views
    views = list((await db.execute(
        select(CompanyLibraryView).where(CompanyLibraryView.user_id == user.id)
        .order_by(CompanyLibraryView.is_default.desc(), CompanyLibraryView.created_at)
    )).scalars().all())

    return LibraryListResponse(
        items=rows,
        total=total,
        columns=[FieldDefinitionRead.model_validate(f) for f in fields_def],
        available_views=[LibraryViewRead.model_validate(v) for v in views],
        active_view_id=view_id,
    )


@router.get("/library/companies/{company_id}", response_model=LibraryCompanyDetail)
async def get_library_detail(
    company_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> LibraryCompanyDetail:
    co = (await db.execute(
        select(Company).where(Company.id == company_id).options(selectinload(Company.sector))
    )).scalar_one_or_none()
    if co is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Company not found")

    sector_code = getattr(co.sector, "code", None) if getattr(co, "sector", None) else None
    fields_def = await _list_applicable_fields(db, sector_code=sector_code, company_id=company_id)
    prefetch = await _prefetch_for(db, [co.id])

    fields: list[LibraryFieldValue] = []
    for f in fields_def:
        try:
            v = _compute_value(co, f, prefetch)
        except Exception:
            v = None
        fields.append(LibraryFieldValue(
            code=f.code,
            value=v,
            source_module=f.source_module,
            source_updated_at=None,
            source_actor=None,
        ))

    tabs_q = await db.execute(
        select(CompanyLibraryTab).order_by(CompanyLibraryTab.sort_order, CompanyLibraryTab.code)
    )
    tabs = [LibraryTabRead.model_validate(t) for t in tabs_q.scalars().all()]

    return LibraryCompanyDetail(
        company_id=co.id,
        company_code=getattr(co, "code", None),
        company_name=co.name_ru,
        sector_id=getattr(co, "sector_id", None),
        sector_name=getattr(co.sector, "name_ru", None) if getattr(co, "sector", None) else None,
        fields=fields,
        tabs=tabs,
        activity=[],
    )


@router.patch("/library/companies/{company_id}/fields/{field_code}", response_model=FieldWriteResponse)
async def write_library_field(
    company_id: UUID,
    field_code: str,
    body: FieldWriteRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> FieldWriteResponse:
    """Write a single field value. Routes by source_module.

    Phase 1: writes go to companies.custom_data for fields without a source_module
    OR to the Company column for source_module='companies'. Sync to FinModel/KPI/etc
    is wired in Phase 4 — for now those return 501 Not Implemented.
    """
    co = (await db.execute(select(Company).where(Company.id == company_id))).scalar_one_or_none()
    if co is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Company not found")

    fdef = (await db.execute(
        select(FieldDefinition).where(FieldDefinition.code == field_code)
    )).scalar_one_or_none()
    if fdef is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Field '{field_code}' not defined")

    new_value = body.value
    routed_to: Optional[str] = None

    if fdef.source_module is None or fdef.source_module == "library":
        cd = dict(co.custom_data or {})
        cd[field_code] = new_value
        co.custom_data = cd
        await db.flush()
        routed_to = "companies.custom_data"

    elif fdef.source_module == "companies":
        # Direct attribute on Company
        if fdef.source_path and "." not in fdef.source_path and hasattr(co, fdef.source_path):
            setattr(co, fdef.source_path, new_value)
            await db.flush()
            routed_to = f"companies.{fdef.source_path}"
        else:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                f"Field '{field_code}' source_path is invalid for Company attribute",
            )

    elif fdef.source_module == "ratings":
        # Upsert agency_ratings row for this company + agency.
        # Mapping: rating_fitch → "Fitch", rating_sp → "S&P", rating_moodys → "Moody's",
        #          rating_esg → "Sustainable Fitch" (ESG flag)
        agency_map = {
            "rating_fitch":  ("Fitch",              False),
            "rating_sp":     ("S&P",                False),
            "rating_moodys": ("Moody's",            False),
            "rating_esg":    ("Sustainable Fitch",  True),
        }
        if field_code not in agency_map:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                f"Unknown ratings field '{field_code}'",
            )
        try:
            from app.models.agency_rating import AgencyRating
        except Exception:
            raise HTTPException(status.HTTP_501_NOT_IMPLEMENTED, "AgencyRating model unavailable")
        agency_name, is_esg = agency_map[field_code]
        row = (await db.execute(
            select(AgencyRating).where(
                AgencyRating.company_id == company_id,
                AgencyRating.agency == agency_name,
            ).order_by(AgencyRating.rating_date.desc().nulls_last()).limit(1)
        )).scalar_one_or_none()
        new_str = "" if new_value is None else str(new_value).strip()
        if row is None:
            if not new_str:
                # Clearing an unset rating is a no-op
                routed_to = "agency_ratings (no-op)"
            else:
                row = AgencyRating(
                    company_id=company_id, agency=agency_name, is_esg=is_esg,
                )
                # ESG carries score; credit agencies carry rating letter
                if is_esg:
                    row.score = new_str[:16]
                else:
                    row.rating = new_str[:16]
                row.rating_date = datetime.now(timezone.utc).date()
                db.add(row)
                await db.flush()
                routed_to = "agency_ratings (insert)"
        else:
            if is_esg:
                row.score = new_str[:16] or None
            else:
                row.rating = new_str[:16] or None
            row.rating_date = datetime.now(timezone.utc).date()
            await db.flush()
            routed_to = "agency_ratings (update)"

    elif fdef.source_module in ("finmodel", "financials"):
        # Upsert a top-level financial line in the latest IFRS report of that type.
        line_map = {
            "revenue":     ("PL", _LINE_REVENUE[0]),
            "ebitda":      ("PL", _LINE_EBITDA[0]),
            "net_profit":  ("PL", _LINE_PROFIT[0]),
            "total_debt":  ("BS", _LINE_DEBT[0]),
            "total_assets":("BS", _LINE_ASSETS[0]),
            "equity":      ("BS", _LINE_EQUITY[0]),
        }
        if field_code not in line_map:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                f"Field '{field_code}' is not writable through the library (use FinModel editor for derived metrics)",
            )
        try:
            from app.models.financial import FinancialReport, FinancialLine
        except Exception:
            raise HTTPException(status.HTTP_501_NOT_IMPLEMENTED, "Financial models unavailable")

        rtype, line_code = line_map[field_code]
        rep = (await db.execute(
            select(FinancialReport)
            .where(FinancialReport.company_id == company_id)
            .where(FinancialReport.report_type == rtype)
            .where(FinancialReport.standard == "IFRS")
            .order_by(FinancialReport.year.desc())
            .limit(1)
        )).scalar_one_or_none()
        if rep is None:
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                f"Нет IFRS {rtype} отчёта для компании. Создайте через FinModel editor сначала.",
            )
        ln = (await db.execute(
            select(FinancialLine).where(
                FinancialLine.report_id == rep.id,
                FinancialLine.line_code == line_code,
            )
        )).scalar_one_or_none()

        # New value normalized to UNSCALED units of the report
        scale = rep.unit_scale or 1
        try:
            scaled_val = (float(new_value) / scale) if new_value is not None else None
        except (TypeError, ValueError):
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "value must be numeric")

        if ln is None:
            from decimal import Decimal
            ln = FinancialLine(
                report_id=rep.id,
                line_code=line_code,
                line_name=line_code,
                value=(None if scaled_val is None else Decimal(str(scaled_val))),
                is_subtotal=False,
                is_calculated=False,
                sort_order=0,
                indent_level=0,
            )
            db.add(ln)
        else:
            from decimal import Decimal
            ln.value = (None if scaled_val is None else Decimal(str(scaled_val)))
        await db.flush()
        routed_to = f"financial_lines ({rtype} y{rep.year} · {line_code})"

    elif fdef.source_module == "kpi":
        # kpi_completion is an aggregated computed — not directly writable.
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "KPI completion is computed from indicators. Edit specific KPI indicators in the KPI editor.",
        )

    else:
        raise HTTPException(
            status.HTTP_501_NOT_IMPLEMENTED,
            f"Routing writes to source_module='{fdef.source_module}' is not yet wired",
        )

    await db.commit()
    now = datetime.now(timezone.utc)

    # Append audit_log so the change shows up in /library/companies/{id}/activity
    try:
        from app.core.audit_chain import append_audit_entry
        await append_audit_entry(
            db,
            actor_id=str(user.id), actor_email=user.email,
            action="library.field.update",
            entity_type="company",
            entity_id=str(company_id),
            diff={"field_code": field_code, "new_value": new_value,
                  "source_module": fdef.source_module, "routed_to": routed_to},
            notes=f"library write · {field_code}",
        )
        await db.commit()
    except Exception:
        log.warning("audit append failed for library write %s/%s", company_id, field_code,
                    exc_info=True)
        await db.rollback()

    # Broadcast via WebSocket (best-effort, never raise)
    try:
        await broadcaster.broadcast_field_update(
            company_id=str(company_id),
            field_code=field_code,
            value=new_value,
            source_module=fdef.source_module,
            actor_id=str(user.id),
        )
    except Exception:
        log.warning("ws broadcast failed for %s/%s", company_id, field_code, exc_info=True)

    return FieldWriteResponse(
        code=field_code,
        value=new_value,
        source_module=fdef.source_module,
        updated_at=now,
        routed_to=routed_to,
    )


@router.get("/library/companies/{company_id}/activity", response_model=list[LibraryActivityEntry])
async def get_library_activity(
    company_id: UUID,
    limit: int = Query(10, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[LibraryActivityEntry]:
    """Recent audit-log entries that touched this company.

    Filters audit_log where (entity_type='company' AND entity_id=<id>)
    OR action LIKE '%library.%' AND payload->>'company_id' = <id>.
    """
    try:
        from app.models.audit import AuditLog
    except Exception:
        return []
    res = await db.execute(
        select(AuditLog)
        .where(AuditLog.entity_id == str(company_id))
        .order_by(AuditLog.created_at.desc())
        .limit(limit)
    )
    rows = res.scalars().all()
    out: list[LibraryActivityEntry] = []
    for r in rows:
        # field_code may live in `diff` (library writes) or `meta` (legacy)
        fc: str | None = None
        if isinstance(r.diff, dict):
            fc = r.diff.get("field_code")
        if fc is None and isinstance(getattr(r, "meta", None), dict):
            fc = r.meta.get("field_code")
        # Derive a "module" hint when audit_log row has no explicit module
        module = getattr(r, "module", None)
        if not module and isinstance(r.diff, dict):
            module = r.diff.get("source_module")
        out.append(LibraryActivityEntry(
            ts=r.created_at,
            actor_email=r.actor_email,
            module=module,
            action=r.action,
            field_code=fc,
            diff=r.diff if isinstance(r.diff, dict) else None,
        ))
    return out


# ────────────────────────────────────────────────────────────────────────
# /field-definitions — CRUD
# ────────────────────────────────────────────────────────────────────────

@router.get("/field-definitions", response_model=list[FieldDefinitionRead])
async def list_field_definitions(
    sector: Optional[str] = Query(None),
    scope_type: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[FieldDefinitionRead]:
    q = select(FieldDefinition).order_by(FieldDefinition.sort_order, FieldDefinition.code)
    if scope_type:
        q = q.where(FieldDefinition.scope_type == scope_type)
    fields = list((await db.execute(q)).scalars().all())
    if sector:
        fields = [
            f for f in fields
            if f.scope_type != "sector"
               or (isinstance(f.scope_value, list) and sector in f.scope_value)
        ]
    return [FieldDefinitionRead.model_validate(f) for f in fields]


@router.post("/field-definitions", response_model=FieldDefinitionRead,
             status_code=status.HTTP_201_CREATED)
async def create_field_definition(
    body: FieldDefinitionCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("library.fields.manage")),
) -> FieldDefinitionRead:
    if body.field_type not in FIELD_TYPES:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Invalid field_type")
    if body.scope_type not in SCOPE_TYPES:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Invalid scope_type")
    existing = (await db.execute(
        select(FieldDefinition).where(FieldDefinition.code == body.code)
    )).scalar_one_or_none()
    if existing:
        raise HTTPException(status.HTTP_409_CONFLICT, f"Field '{body.code}' already exists")
    f = FieldDefinition(
        code=body.code, name_ru=body.name_ru, name_uz=body.name_uz, name_en=body.name_en,
        field_type=body.field_type, unit=body.unit, format_pattern=body.format_pattern,
        enum_values=body.enum_values, formula=body.formula,
        scope_type=body.scope_type, scope_value=body.scope_value,
        source_module=body.source_module, source_path=body.source_path,
        permission_view=body.permission_view, permission_edit=body.permission_edit,
        is_system=False, sort_order=body.sort_order, created_by=user.id,
    )
    db.add(f)
    await db.commit()
    await db.refresh(f)
    return FieldDefinitionRead.model_validate(f)


@router.patch("/field-definitions/{code}", response_model=FieldDefinitionRead)
async def update_field_definition(
    code: str,
    body: FieldDefinitionUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("library.fields.manage")),
) -> FieldDefinitionRead:
    f = (await db.execute(
        select(FieldDefinition).where(FieldDefinition.code == code)
    )).scalar_one_or_none()
    if f is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Field not found")
    if f.is_system:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "System fields cannot be modified")
    data = body.model_dump(exclude_unset=True)
    for k, v in data.items():
        setattr(f, k, v)
    await db.commit()
    await db.refresh(f)
    return FieldDefinitionRead.model_validate(f)


@router.delete("/field-definitions/{code}", status_code=status.HTTP_204_NO_CONTENT, response_class=Response)
async def delete_field_definition(
    code: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("library.fields.manage")),
):
    f = (await db.execute(
        select(FieldDefinition).where(FieldDefinition.code == code)
    )).scalar_one_or_none()
    if f is None:
        return Response(status_code=204)
    if f.is_system:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "System fields cannot be deleted")

    # Best-effort clear values across companies
    cos = list((await db.execute(select(Company))).scalars().all())
    for co in cos:
        if co.custom_data and code in co.custom_data:
            cd = dict(co.custom_data)
            cd.pop(code, None)
            co.custom_data = cd
    await db.delete(f)
    await db.commit()
    return Response(status_code=204)


# ────────────────────────────────────────────────────────────────────────
# /library-views — CRUD (per-user)
# ────────────────────────────────────────────────────────────────────────

@router.get("/library-views", response_model=list[LibraryViewRead])
async def list_my_views(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[LibraryViewRead]:
    res = await db.execute(
        select(CompanyLibraryView).where(CompanyLibraryView.user_id == user.id)
        .order_by(CompanyLibraryView.is_default.desc(), CompanyLibraryView.created_at)
    )
    return [LibraryViewRead.model_validate(v) for v in res.scalars().all()]


@router.post("/library-views", response_model=LibraryViewRead, status_code=status.HTTP_201_CREATED)
async def create_view(
    body: LibraryViewCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> LibraryViewRead:
    if body.is_default:
        # Unset other defaults for this user
        existing = list((await db.execute(
            select(CompanyLibraryView).where(
                CompanyLibraryView.user_id == user.id,
                CompanyLibraryView.is_default.is_(True),
            )
        )).scalars().all())
        for v in existing:
            v.is_default = False
    v = CompanyLibraryView(
        user_id=user.id, name=body.name, is_default=body.is_default,
        visible_columns=body.visible_columns, filters=body.filters,
        sort_by=body.sort_by, sort_dir=body.sort_dir,
    )
    db.add(v)
    await db.commit()
    await db.refresh(v)
    return LibraryViewRead.model_validate(v)


@router.patch("/library-views/{view_id}", response_model=LibraryViewRead)
async def update_view(
    view_id: UUID,
    body: LibraryViewUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> LibraryViewRead:
    v = (await db.execute(
        select(CompanyLibraryView).where(CompanyLibraryView.id == view_id)
    )).scalar_one_or_none()
    if v is None or v.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "View not found")
    data = body.model_dump(exclude_unset=True)
    if data.get("is_default"):
        existing = list((await db.execute(
            select(CompanyLibraryView).where(
                CompanyLibraryView.user_id == user.id,
                CompanyLibraryView.is_default.is_(True),
                CompanyLibraryView.id != view_id,
            )
        )).scalars().all())
        for other in existing:
            other.is_default = False
    for k, val in data.items():
        setattr(v, k, val)
    await db.commit()
    await db.refresh(v)
    return LibraryViewRead.model_validate(v)


@router.delete("/library-views/{view_id}", status_code=status.HTTP_204_NO_CONTENT, response_class=Response)
async def delete_view(
    view_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    v = (await db.execute(
        select(CompanyLibraryView).where(CompanyLibraryView.id == view_id)
    )).scalar_one_or_none()
    if v is None or v.user_id != user.id:
        return Response(status_code=204)
    await db.delete(v)
    await db.commit()
    return Response(status_code=204)


# ────────────────────────────────────────────────────────────────────────
# /library-tabs — CRUD (global)
# ────────────────────────────────────────────────────────────────────────

@router.get("/library-tabs", response_model=list[LibraryTabRead])
async def list_tabs(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[LibraryTabRead]:
    res = await db.execute(
        select(CompanyLibraryTab).order_by(CompanyLibraryTab.sort_order, CompanyLibraryTab.code)
    )
    return [LibraryTabRead.model_validate(t) for t in res.scalars().all()]


@router.post("/library-tabs", response_model=LibraryTabRead, status_code=status.HTTP_201_CREATED)
async def create_tab(
    body: LibraryTabCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("library.tabs.manage")),
) -> LibraryTabRead:
    existing = (await db.execute(
        select(CompanyLibraryTab).where(CompanyLibraryTab.code == body.code)
    )).scalar_one_or_none()
    if existing:
        raise HTTPException(status.HTTP_409_CONFLICT, f"Tab '{body.code}' already exists")
    t = CompanyLibraryTab(
        code=body.code, name_ru=body.name_ru, name_uz=body.name_uz, name_en=body.name_en,
        field_codes=body.field_codes, layout=body.layout, is_system=False,
        sort_order=body.sort_order, scope_type=body.scope_type, scope_value=body.scope_value,
        created_by=user.id,
    )
    db.add(t)
    await db.commit()
    await db.refresh(t)
    return LibraryTabRead.model_validate(t)


@router.patch("/library-tabs/{code}", response_model=LibraryTabRead)
async def update_tab(
    code: str,
    body: LibraryTabUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("library.tabs.manage")),
) -> LibraryTabRead:
    t = (await db.execute(
        select(CompanyLibraryTab).where(CompanyLibraryTab.code == code)
    )).scalar_one_or_none()
    if t is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Tab not found")
    if t.is_system:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "System tabs cannot be modified")
    data = body.model_dump(exclude_unset=True)
    for k, v in data.items():
        setattr(t, k, v)
    await db.commit()
    await db.refresh(t)
    return LibraryTabRead.model_validate(t)


@router.delete("/library-tabs/{code}", status_code=status.HTTP_204_NO_CONTENT, response_class=Response)
async def delete_tab(
    code: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("library.tabs.manage")),
):
    t = (await db.execute(
        select(CompanyLibraryTab).where(CompanyLibraryTab.code == code)
    )).scalar_one_or_none()
    if t is None:
        return Response(status_code=204)
    if t.is_system:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "System tabs cannot be deleted")
    await db.delete(t)
    await db.commit()
    return Response(status_code=204)


# ────────────────────────────────────────────────────────────────────────
# WebSocket endpoints
# ────────────────────────────────────────────────────────────────────────

# Use a separate router so the WS endpoints don't appear in the OpenAPI HTTP table.
ws_router = APIRouter()


@ws_router.websocket("/ws/companies")
async def ws_companies_global(ws: WebSocket) -> None:
    """Subscribe to ALL company field updates."""
    await broadcaster.connect(ws, GLOBAL_SCOPE)
    try:
        # Keep the connection open. We accept incoming text but ignore it;
        # the client only listens for server-pushed messages.
        while True:
            try:
                await ws.receive_text()
            except WebSocketDisconnect:
                break
    finally:
        await broadcaster.disconnect(ws, GLOBAL_SCOPE)


@ws_router.websocket("/ws/companies/{company_id}")
async def ws_company_scoped(ws: WebSocket, company_id: str) -> None:
    """Subscribe to updates for one company only."""
    await broadcaster.connect(ws, company_id)
    try:
        while True:
            try:
                await ws.receive_text()
            except WebSocketDisconnect:
                break
    finally:
        await broadcaster.disconnect(ws, company_id)
