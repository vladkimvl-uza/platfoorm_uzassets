"""Use cases for Company Library (MDM).

WebSocket broadcasts via `app/services/sync_broadcaster.py` (core, not touched).
"""
from __future__ import annotations

import logging
from datetime import UTC, datetime
from decimal import Decimal
from types import SimpleNamespace
from typing import Any, Optional
from uuid import UUID

from fastapi import HTTPException
from fastapi import status as http_status

from app.models.company_library import (
    FIELD_TYPES,
    SCOPE_TYPES,
    CompanyLibraryTab,
    CompanyLibraryView,
    FieldDefinition,
)
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
from app.services.company_library._helpers import (
    LINE_ASSETS,
    LINE_DEBT,
    LINE_EBITDA,
    LINE_EQUITY,
    LINE_PROFIT,
    LINE_REVENUE,
    LibraryDataPrefetch,
    applies_to_scope,
    compute_value,
    pick_first,
)
from app.services.sync_broadcaster import broadcaster
from app.uow.ports import UnitOfWorkABC

log = logging.getLogger(__name__)


class _QueuedResult:
    """Сигнал роуту: правка ушла на модерацию (202), а не записана напрямую."""
    def __init__(self, submission_id, status: str) -> None:
        self.queued = True
        self.submission_id = submission_id
        self.status = status


class CompanyLibraryService:
    def __init__(self, uow: UnitOfWorkABC) -> None:
        self.uow = uow

    # ─── prefetch ─────────────────────────────────────────────────

    async def _prefetch(self, company_ids: list[UUID]) -> LibraryDataPrefetch:
        """Batch prefetch financials + ratings + kpi for ALL companies in scope."""
        pref = LibraryDataPrefetch()
        if not company_ids:
            return pref

        r = self.uow.company_library

        # Financial reports + lines
        reports = await r.list_financial_reports(company_ids)
        if reports:
            report_ids = [rep.id for rep in reports]
            lines = await r.list_financial_lines_for_reports(report_ids)
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

            by_cid_type: dict[tuple[str, str], list[tuple[int, int, dict[str, float | None]]]] = {}
            for rep in reports:
                cid = str(rep.company_id)
                rtype = rep.report_type
                scale = rep.unit_scale or 1
                codes = lines_by_report.get(str(rep.id), {})
                by_cid_type.setdefault((cid, rtype), []).append((rep.year, scale, codes))

            picked: dict[str, dict[str, tuple[int, int, dict[str, float | None]]]] = {}
            for (cid, rtype), entries in by_cid_type.items():
                entries.sort(key=lambda e: -e[0])
                chosen = None
                for yr, scale, codes in entries:
                    disc = (
                        pick_first(codes, LINE_REVENUE) if rtype == "PL"
                        else (pick_first(codes, LINE_EQUITY) or pick_first(codes, LINE_ASSETS))
                    )
                    if disc and disc != 0:
                        chosen = (yr, scale, codes)
                        break
                if chosen is None and entries:
                    chosen = entries[0]
                if chosen is not None:
                    picked.setdefault(cid, {})[rtype] = chosen
                    if pref.year is None or chosen[0] > (pref.year or 0):
                        pref.year = chosen[0]

            for cid, by_type in picked.items():
                pl_entry = by_type.get("PL")
                bs_entry = by_type.get("BS")
                pl_scale, pl_codes = (pl_entry[1], pl_entry[2]) if pl_entry else (1, {})
                bs_scale, bs_codes = (bs_entry[1], bs_entry[2]) if bs_entry else (1, {})

                def _v(codes, names, scale):
                    raw = pick_first(codes, names)
                    return None if raw is None else raw * scale

                revenue = _v(pl_codes, LINE_REVENUE, pl_scale)
                ebitda  = _v(pl_codes, LINE_EBITDA,  pl_scale)
                profit  = _v(pl_codes, LINE_PROFIT,  pl_scale)
                equity  = _v(bs_codes, LINE_EQUITY,  bs_scale)
                debt    = _v(bs_codes, LINE_DEBT,    bs_scale)
                assets  = _v(bs_codes, LINE_ASSETS,  bs_scale)
                de = (debt / ebitda) if (debt is not None and ebitda not in (None, 0)) else None
                pref.fin[cid] = {
                    "revenue": revenue, "ebitda": ebitda,
                    "net_profit": profit,
                    "total_debt": debt, "total_assets": assets,
                    "debt_to_ebitda": de, "equity": equity,
                }

        # Ratings
        ratings = await r.list_agency_ratings(company_ids)
        for ar in ratings:
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

        # KPI completion
        latest_year = await r.kpi_latest_year_map(company_ids)
        if latest_year:
            mgrs = await r.list_kpi_managers(company_ids)
            relevant_mgrs = [
                m for m in mgrs
                if str(m.company_id) in latest_year
                   and m.year == latest_year[str(m.company_id)]
            ]
            mgr_ids = [m.id for m in relevant_mgrs]
            inds = await r.list_kpi_indicators(mgr_ids)
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

    async def _list_applicable_fields(
        self, *,
        sector_code: Optional[str] = None,
        company_id: Optional[UUID] = None,
    ) -> list[FieldDefinition]:
        r = self.uow.company_library
        all_fields = await r.list_field_definitions()
        return [
            f for f in all_fields
            if applies_to_scope(f, sector_code=sector_code, company_id=company_id)
        ]

    # ─── library list/detail/activity ─────────────────────────────

    async def list_library(
        self, *,
        sector: Optional[str], search: Optional[str], view_id: Optional[UUID],
        limit: int, offset: int, user_id: UUID,
    ) -> LibraryListResponse:
        async with self.uow:
            r = self.uow.company_library
            companies = await r.list_companies(
                sector=sector, search=search, limit=limit, offset=offset,
            )
            total = await r.count_companies(sector=sector, search=search)
            fields_def = await self._list_applicable_fields(sector_code=sector)
            prefetch = await self._prefetch([c.id for c in companies])
            views = await r.list_views(user_id)

        rows: list[LibraryCompanyRow] = []
        for co in companies:
            co_fields: dict[str, Any] = {}
            for f in fields_def:
                try:
                    co_fields[f.code] = compute_value(co, f, prefetch)
                except Exception:
                    co_fields[f.code] = None
            rows.append(LibraryCompanyRow(
                id=co.id,
                code=getattr(co, "code", None),
                name_ru=co.name_ru,
                name_short=getattr(co, "name_short", None),
                sector_id=getattr(co, "sector_id", None),
                sector_name=getattr(co.sector, "name_ru", None)
                            if getattr(co, "sector", None) else None,
                fields=co_fields,
            ))

        return LibraryListResponse(
            items=rows, total=total,
            columns=[FieldDefinitionRead.model_validate(f) for f in fields_def],
            available_views=[LibraryViewRead.model_validate(v) for v in views],
            active_view_id=view_id,
        )

    async def get_library_detail(self, company_id: UUID) -> LibraryCompanyDetail:
        async with self.uow:
            r = self.uow.company_library
            co = await r.get_company_with_sector(company_id)
            if co is None:
                raise HTTPException(http_status.HTTP_404_NOT_FOUND, "Company not found")
            sector_code = (
                getattr(co.sector, "code", None) if getattr(co, "sector", None) else None
            )
            fields_def = await self._list_applicable_fields(
                sector_code=sector_code, company_id=company_id,
            )
            prefetch = await self._prefetch([co.id])
            tabs = await r.list_tabs()

        fields: list[LibraryFieldValue] = []
        for f in fields_def:
            try:
                v = compute_value(co, f, prefetch)
            except Exception:
                v = None
            fields.append(LibraryFieldValue(
                code=f.code, value=v,
                source_module=f.source_module,
                source_updated_at=None, source_actor=None,
            ))
        return LibraryCompanyDetail(
            company_id=co.id,
            company_code=getattr(co, "code", None),
            company_name=co.name_ru,
            sector_id=getattr(co, "sector_id", None),
            sector_name=getattr(co.sector, "name_ru", None)
                        if getattr(co, "sector", None) else None,
            fields=fields,
            tabs=[LibraryTabRead.model_validate(t) for t in tabs],
            activity=[],
        )

    async def get_activity(
        self, company_id: UUID, *, limit: int,
    ) -> list[LibraryActivityEntry]:
        async with self.uow:
            rows = await self.uow.company_library.list_audit_for_company(
                company_id, limit=limit,
            )
        out: list[LibraryActivityEntry] = []
        for ar in rows:
            fc: Optional[str] = None
            if isinstance(ar.diff, dict):
                fc = ar.diff.get("field_code")
            if fc is None and isinstance(getattr(ar, "meta", None), dict):
                fc = ar.meta.get("field_code")
            module = getattr(ar, "module", None)
            if not module and isinstance(ar.diff, dict):
                module = ar.diff.get("source_module")
            out.append(LibraryActivityEntry(
                ts=ar.created_at,
                actor_email=ar.actor_email,
                module=module,
                action=ar.action,
                field_code=fc,
                diff=ar.diff if isinstance(ar.diff, dict) else None,
            ))
        return out

    # ─── field write (multi-route) ────────────────────────────────

    async def write_field(
        self, company_id: UUID, field_code: str, body: FieldWriteRequest,
        *, user, db, api_key=None,
    ):
        new_value = body.value
        queued_result: Optional[_QueuedResult] = None
        async with self.uow:
            r = self.uow.company_library
            co = await r.get_company(company_id)
            if co is None:
                raise HTTPException(http_status.HTTP_404_NOT_FOUND, "Company not found")
            fdef = await r.get_field_definition(field_code)
            if fdef is None:
                raise HTTPException(
                    http_status.HTTP_404_NOT_FOUND,
                    f"Field '{field_code}' not defined",
                )

            routed_to: Optional[str] = None
            src = fdef.source_module
            rating_row = None          # затронутая строка рейтинга (для истории)
            rating_action: Optional[str] = None

            # P0 (аудит /ratings): право per-source. ratings-поля → ratings.edit
            # (+ модерация как канон-путь /ratings); всё прочее → companies.edit.
            from app.core.security import has_effective_permission
            required_perm = "ratings.edit" if src == "ratings" else "companies.edit"
            if not await has_effective_permission(db, user, required_perm):
                raise HTTPException(
                    http_status.HTTP_403_FORBIDDEN,
                    f"Permission required: {required_perm}",
                )
            # Scope-ceiling API-ключа (как в require_permission): ключ не может писать
            # сверх своих scopes, даже если у сервис-аккаунта есть право.
            if api_key is not None:
                from app.services.api_key_service import check_scope
                if not check_scope(api_key, required_perm):
                    raise HTTPException(
                        http_status.HTTP_403_FORBIDDEN,
                        f"API key scope missing: {required_perm}",
                    )

            if src is None or src == "library":
                cd = dict(co.custom_data or {})
                cd[field_code] = new_value
                co.custom_data = cd
                await r.flush()
                routed_to = "companies.custom_data"

            elif src == "companies":
                if (
                    fdef.source_path and "." not in fdef.source_path
                    and hasattr(co, fdef.source_path)
                ):
                    setattr(co, fdef.source_path, new_value)
                    await r.flush()
                    routed_to = f"companies.{fdef.source_path}"
                else:
                    raise HTTPException(
                        http_status.HTTP_400_BAD_REQUEST,
                        f"Field '{field_code}' source_path is invalid for Company attribute",
                    )

            elif src == "ratings":
                # Через модерацию (канон-путь /ratings). gate_or_apply: queued → 202
                # (применит moderation_apply/ratings.py); write-through (owner/bypass/
                # нет правила) → прямая запись + история как раньше.
                gated = await self._gate_rating_write(
                    db, r, user, company_id, field_code, new_value,
                )
                if isinstance(gated, _QueuedResult):
                    queued_result = gated
                else:
                    routed_to, rating_row, rating_action = gated

            elif src in ("finmodel", "financials"):
                routed_to = await self._write_financial(
                    r, company_id, field_code, new_value,
                )

            elif src == "kpi":
                raise HTTPException(
                    http_status.HTTP_409_CONFLICT,
                    "KPI completion is computed from indicators. "
                    "Edit specific KPI indicators in the KPI editor.",
                )
            else:
                raise HTTPException(
                    http_status.HTTP_501_NOT_IMPLEMENTED,
                    f"Routing writes to source_module='{src}' is not yet wired",
                )

            await r.flush()
            now = datetime.now(UTC)
            actor_id_str = str(user.id)
            actor_email = user.email
            source_module = src

            # Снимок рейтинга для истории (пока сессия открыта: после flush id есть,
            # после выхода из UoW атрибуты detached-объекта истекут).
            rating_snap = None
            if rating_row is not None and rating_action:
                rating_snap = SimpleNamespace(
                    id=rating_row.id, company_id=rating_row.company_id,
                    agency=rating_row.agency, is_esg=rating_row.is_esg,
                    rating=rating_row.rating, outlook=rating_row.outlook,
                    score=rating_row.score, rating_date_text=rating_row.rating_date_text,
                    rating_date=rating_row.rating_date, report_url=rating_row.report_url,
                )

        # Правка ушла на модерацию — прямой записи/аудита/истории нет (сделает apply).
        if queued_result is not None:
            return queued_result

        # Audit + broadcast (post-commit, best-effort)
        try:
            from app.core.audit_chain import append_audit_entry
            from app.database import AsyncSessionLocal
            async with AsyncSessionLocal() as session2:
                await append_audit_entry(
                    session2,
                    actor_id=actor_id_str, actor_email=actor_email,
                    action="library.field.update",
                    entity_type="company",
                    entity_id=str(company_id),
                    diff={
                        "field_code": field_code, "new_value": new_value,
                        "source_module": source_module, "routed_to": routed_to,
                    },
                    notes=f"library write · {field_code}",
                )
                await session2.commit()
        except Exception:
            log.warning(
                "audit append failed for library write %s/%s",
                company_id, field_code, exc_info=True,
            )

        try:
            await broadcaster.broadcast_field_update(
                company_id=str(company_id),
                field_code=field_code,
                value=new_value,
                source_module=source_module,
                actor_id=actor_id_str,
            )
        except Exception:
            log.warning(
                "ws broadcast failed for %s/%s",
                company_id, field_code, exc_info=True,
            )

        # История рейтинга (третий путь записи AgencyRating — через библиотеку полей).
        # Best-effort, свежая сессия, чтобы правка попадала в /rating-history-таймлайн.
        if rating_snap is not None:
            try:
                from app.database import AsyncSessionLocal
                from app.services.ratings.history import record_rating_history
                async with AsyncSessionLocal() as s3:
                    await record_rating_history(s3, rec=rating_snap, action=rating_action, user=user)
            except Exception:
                log.warning("rating history (library write) failed for %s/%s",
                            company_id, field_code, exc_info=True)

        return FieldWriteResponse(
            code=field_code, value=new_value,
            source_module=source_module,
            updated_at=now, routed_to=routed_to,
        )

    async def _gate_rating_write(
        self, db, r, user, company_id: UUID, field_code: str, new_value: Any,
    ):
        """Гейтит запись рейтинга через модерацию (module="ratings"). Возвращает
        _QueuedResult (ушло на модерацию) ИЛИ tuple _write_rating (write-through /
        no-op). Payload — в форме AgencyRatingCreate/Update, чтобы moderation_apply/
        ratings.py применил его без изменений."""
        agency_map = {
            "rating_fitch":  "Fitch",
            "rating_sp":     "S&P",
            "rating_moodys": "Moody's",
            "rating_esg":    "Sustainable Fitch",
        }
        if field_code not in agency_map:
            raise HTTPException(
                http_status.HTTP_400_BAD_REQUEST,
                f"Unknown ratings field '{field_code}'",
            )
        from app.models.agency_rating import is_esg_agency
        agency_name = agency_map[field_code]
        is_esg = is_esg_agency(agency_name)
        new_str = "" if new_value is None else str(new_value).strip()
        existing = await r.latest_agency_rating(company_id, agency_name)

        # no-op: нечего создавать — обычный ответ (без модерации/записи)
        if existing is None and not new_str:
            return ("agency_ratings (no-op)", None, None)

        if existing is None:
            action, entity_id = "create", None
            payload = {
                "company_id": str(company_id), "agency": agency_name,
                "rating": None if is_esg else (new_str[:16] or None),
                "score":  (new_str[:16] or None) if is_esg else None,
                "rating_date": datetime.now(UTC).date().isoformat(),
            }
            diff = f"Новый рейтинг от {agency_name}: {new_str or '—'}"
        else:
            action, entity_id = "update", str(existing.id)
            payload = ({"score": new_str[:16] or None} if is_esg
                       else {"rating": new_str[:16] or None})
            payload["rating_date"] = datetime.now(UTC).date().isoformat()
            diff = f"Обновление рейтинга {agency_name}"

        from app.services.moderation_service import gate_or_apply
        queued, sub = await gate_or_apply(
            db, user=user, module="ratings", action=action,
            entity_id=entity_id, entity_label=f"Рейтинг {agency_name}",
            company_id=company_id, sector_id=None, year=None,
            payload=payload, diff_summary=diff,
        )
        if queued:
            return _QueuedResult(sub.id, sub.status)
        # write-through (owner / bypass / нет правила) — прямая запись как раньше
        return await self._write_rating(r, company_id, field_code, new_value)

    async def _write_rating(
        self, r, company_id: UUID, field_code: str, new_value: Any,
    ) -> tuple[str, Any, Optional[str]]:
        """Возвращает (routed_to, затронутая_строка|None, действие 'create'|'update'|None)
        — чтобы вызывающий записал историю рейтинга (record_rating_history)."""
        agency_map = {
            "rating_fitch":  "Fitch",
            "rating_sp":     "S&P",
            "rating_moodys": "Moody's",
            "rating_esg":    "Sustainable Fitch",
        }
        if field_code not in agency_map:
            raise HTTPException(
                http_status.HTTP_400_BAD_REQUEST,
                f"Unknown ratings field '{field_code}'",
            )
        try:
            from app.models.agency_rating import AgencyRating, is_esg_agency
        except Exception:
            raise HTTPException(
                http_status.HTTP_501_NOT_IMPLEMENTED,
                "AgencyRating model unavailable",
            )
        agency_name = agency_map[field_code]
        # is_esg — из единого канона (app.models.agency_rating.is_esg_agency),
        # не хардкод: чтобы 3 пути записи классифицировали одинаково (аудит /ratings).
        is_esg = is_esg_agency(agency_name)
        row = await r.latest_agency_rating(company_id, agency_name)
        new_str = "" if new_value is None else str(new_value).strip()
        if row is None:
            if not new_str:
                return "agency_ratings (no-op)", None, None
            row = AgencyRating(
                company_id=company_id, agency=agency_name, is_esg=is_esg,
            )
            if is_esg:
                row.score = new_str[:16]
            else:
                row.rating = new_str[:16]
            row.rating_date = datetime.now(UTC).date()
            r.add(row)
            return "agency_ratings (insert)", row, "create"
        else:
            if is_esg:
                row.score = new_str[:16] or None
            else:
                row.rating = new_str[:16] or None
            row.rating_date = datetime.now(UTC).date()
            return "agency_ratings (update)", row, "update"

    async def _write_financial(
        self, r, company_id: UUID, field_code: str, new_value: Any,
    ) -> str:
        line_map = {
            "revenue":     ("PL", LINE_REVENUE[0]),
            "ebitda":      ("PL", LINE_EBITDA[0]),
            "net_profit":  ("PL", LINE_PROFIT[0]),
            "total_debt":  ("BS", LINE_DEBT[0]),
            "total_assets":("BS", LINE_ASSETS[0]),
            "equity":      ("BS", LINE_EQUITY[0]),
        }
        if field_code not in line_map:
            raise HTTPException(
                http_status.HTTP_400_BAD_REQUEST,
                f"Field '{field_code}' is not writable through the library "
                "(use FinModel editor for derived metrics)",
            )
        try:
            from app.models.financial import FinancialLine
        except Exception:
            raise HTTPException(
                http_status.HTTP_501_NOT_IMPLEMENTED, "Financial models unavailable",
            )
        rtype, line_code = line_map[field_code]
        rep = await r.get_latest_ifrs_report(company_id, rtype)
        if rep is None:
            raise HTTPException(
                http_status.HTTP_409_CONFLICT,
                f"Нет IFRS {rtype} отчёта для компании. "
                "Создайте через FinModel editor сначала.",
            )
        ln = await r.get_financial_line(rep.id, line_code)
        scale = rep.unit_scale or 1
        try:
            scaled_val = (float(new_value) / scale) if new_value is not None else None
        except (TypeError, ValueError):
            raise HTTPException(
                http_status.HTTP_400_BAD_REQUEST, "value must be numeric",
            )
        if ln is None:
            ln = FinancialLine(
                report_id=rep.id, line_code=line_code, line_name=line_code,
                value=(None if scaled_val is None else Decimal(str(scaled_val))),
                is_subtotal=False, is_calculated=False,
                sort_order=0, indent_level=0,
            )
            r.add(ln)
        else:
            ln.value = None if scaled_val is None else Decimal(str(scaled_val))
        return f"financial_lines ({rtype} y{rep.year} · {line_code})"

    # ─── field definitions CRUD ───────────────────────────────────

    async def list_field_definitions(
        self, *, sector: Optional[str], scope_type: Optional[str],
    ) -> list[FieldDefinitionRead]:
        async with self.uow:
            fields = await self.uow.company_library.list_field_definitions_filtered(
                scope_type=scope_type,
            )
        if sector:
            fields = [
                f for f in fields
                if f.scope_type != "sector"
                   or (isinstance(f.scope_value, list) and sector in f.scope_value)
            ]
        return [FieldDefinitionRead.model_validate(f) for f in fields]

    async def create_field_definition(
        self, body: FieldDefinitionCreate, *, actor_id: UUID,
    ) -> FieldDefinitionRead:
        if body.field_type not in FIELD_TYPES:
            raise HTTPException(http_status.HTTP_400_BAD_REQUEST, "Invalid field_type")
        if body.scope_type not in SCOPE_TYPES:
            raise HTTPException(http_status.HTTP_400_BAD_REQUEST, "Invalid scope_type")
        async with self.uow:
            r = self.uow.company_library
            existing = await r.get_field_definition(body.code)
            if existing:
                raise HTTPException(
                    http_status.HTTP_409_CONFLICT,
                    f"Field '{body.code}' already exists",
                )
            f = FieldDefinition(
                code=body.code, name_ru=body.name_ru,
                name_uz=body.name_uz, name_en=body.name_en,
                field_type=body.field_type, unit=body.unit,
                format_pattern=body.format_pattern,
                enum_values=body.enum_values, formula=body.formula,
                scope_type=body.scope_type, scope_value=body.scope_value,
                source_module=body.source_module, source_path=body.source_path,
                permission_view=body.permission_view,
                permission_edit=body.permission_edit,
                is_system=False, sort_order=body.sort_order,
                created_by=actor_id,
            )
            r.add(f)
            await r.flush()
            await r.refresh(f)
            return FieldDefinitionRead.model_validate(f)

    async def update_field_definition(
        self, code: str, body: FieldDefinitionUpdate,
    ) -> FieldDefinitionRead:
        async with self.uow:
            r = self.uow.company_library
            f = await r.get_field_definition(code)
            if f is None:
                raise HTTPException(http_status.HTTP_404_NOT_FOUND, "Field not found")
            if f.is_system:
                raise HTTPException(
                    http_status.HTTP_403_FORBIDDEN,
                    "System fields cannot be modified",
                )
            for k, v in body.model_dump(exclude_unset=True).items():
                setattr(f, k, v)
            await r.flush()
            await r.refresh(f)
            return FieldDefinitionRead.model_validate(f)

    async def delete_field_definition(self, code: str) -> bool:
        """Returns True if deleted, False if was missing (idempotent 204)."""
        async with self.uow:
            r = self.uow.company_library
            f = await r.get_field_definition(code)
            if f is None:
                return False
            if f.is_system:
                raise HTTPException(
                    http_status.HTTP_403_FORBIDDEN,
                    "System fields cannot be deleted",
                )
            # Best-effort clear values across all companies
            companies = await r.list_all_companies()
            for co in companies:
                if co.custom_data and code in co.custom_data:
                    cd = dict(co.custom_data)
                    cd.pop(code, None)
                    co.custom_data = cd
            await r.delete(f)
            await r.flush()
            return True

    # ─── views CRUD ───────────────────────────────────────────────

    async def list_my_views(self, user_id: UUID) -> list[LibraryViewRead]:
        async with self.uow:
            rows = await self.uow.company_library.list_views(user_id)
        return [LibraryViewRead.model_validate(v) for v in rows]

    async def create_view(
        self, body: LibraryViewCreate, *, user_id: UUID,
    ) -> LibraryViewRead:
        async with self.uow:
            r = self.uow.company_library
            if body.is_default:
                existing = await r.list_default_views_other_than(user_id, None)
                for v in existing:
                    v.is_default = False
            v = CompanyLibraryView(
                user_id=user_id, name=body.name, is_default=body.is_default,
                visible_columns=body.visible_columns, filters=body.filters,
                sort_by=body.sort_by, sort_dir=body.sort_dir,
            )
            r.add(v)
            await r.flush()
            await r.refresh(v)
            return LibraryViewRead.model_validate(v)

    async def update_view(
        self, view_id: UUID, body: LibraryViewUpdate, *, user_id: UUID,
    ) -> LibraryViewRead:
        async with self.uow:
            r = self.uow.company_library
            v = await r.get_view(view_id)
            if v is None or v.user_id != user_id:
                raise HTTPException(http_status.HTTP_404_NOT_FOUND, "View not found")
            data = body.model_dump(exclude_unset=True)
            if data.get("is_default"):
                existing = await r.list_default_views_other_than(user_id, view_id)
                for other in existing:
                    other.is_default = False
            for k, val in data.items():
                setattr(v, k, val)
            await r.flush()
            await r.refresh(v)
            return LibraryViewRead.model_validate(v)

    async def delete_view(self, view_id: UUID, *, user_id: UUID) -> None:
        async with self.uow:
            r = self.uow.company_library
            v = await r.get_view(view_id)
            if v is None or v.user_id != user_id:
                return  # idempotent
            await r.delete(v)
            await r.flush()

    # ─── tabs CRUD ────────────────────────────────────────────────

    async def list_tabs(self) -> list[LibraryTabRead]:
        async with self.uow:
            rows = await self.uow.company_library.list_tabs()
        return [LibraryTabRead.model_validate(t) for t in rows]

    async def create_tab(
        self, body: LibraryTabCreate, *, actor_id: UUID,
    ) -> LibraryTabRead:
        async with self.uow:
            r = self.uow.company_library
            existing = await r.get_tab(body.code)
            if existing:
                raise HTTPException(
                    http_status.HTTP_409_CONFLICT,
                    f"Tab '{body.code}' already exists",
                )
            t = CompanyLibraryTab(
                code=body.code, name_ru=body.name_ru,
                name_uz=body.name_uz, name_en=body.name_en,
                field_codes=body.field_codes, layout=body.layout,
                is_system=False, sort_order=body.sort_order,
                scope_type=body.scope_type, scope_value=body.scope_value,
                created_by=actor_id,
            )
            r.add(t)
            await r.flush()
            await r.refresh(t)
            return LibraryTabRead.model_validate(t)

    async def update_tab(
        self, code: str, body: LibraryTabUpdate,
    ) -> LibraryTabRead:
        async with self.uow:
            r = self.uow.company_library
            t = await r.get_tab(code)
            if t is None:
                raise HTTPException(http_status.HTTP_404_NOT_FOUND, "Tab not found")
            if t.is_system:
                raise HTTPException(
                    http_status.HTTP_403_FORBIDDEN,
                    "System tabs cannot be modified",
                )
            for k, v in body.model_dump(exclude_unset=True).items():
                setattr(t, k, v)
            await r.flush()
            await r.refresh(t)
            return LibraryTabRead.model_validate(t)

    async def delete_tab(self, code: str) -> bool:
        async with self.uow:
            r = self.uow.company_library
            t = await r.get_tab(code)
            if t is None:
                return False
            if t.is_system:
                raise HTTPException(
                    http_status.HTTP_403_FORBIDDEN,
                    "System tabs cannot be deleted",
                )
            await r.delete(t)
            await r.flush()
            return True
