"""ESG Maturity Cockpit — heatmap (матрица 22×6) + EMS + upsert ячейки.

Stateless-сервис (db передаётся в методы, как в financials_ifrs). Источник:
  - esg_maturity_cells (D1 ISO / D2 отчётность 0..3 / D2A независимое заверение
    0..2 / D4 климат / D5 риски / D6 KPI)
  - agency_ratings (is_esg) → D3 рейтинги вычисляются на лету
ESG Maturity Score (EMS) — взвешенная нормализованная сумма стадий 0..4.
Заверение (D2A «пройдено») поднимает D2 до 4/4 — прежняя семантика «+ assurance».
"""
from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import Optional
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.agency_rating import AgencyRating
from app.models.bp_kpi import KpiIndicator, KpiManager
from app.models.company import Company, Sector
from app.models.esg import ESGMaturityCell, ESGReport, ESGSwotItem
from app.models.user import User
from app.schemas.esg import (
    ESGKpiBrief,
    ESGKpiCompany,
    ESGKpiCreate,
    ESGKpiManagerBrief,
    ESGKpiResponse,
    ESGMaturityBaskets,
    ESGMaturityCellBrief,
    ESGMaturityCellUpsert,
    ESGMaturityCompany,
    ESGMaturityHeatmap,
    ESGRatingMini,
    ESGReportBrief,
    ESGReportListResponse,
    ESGReportUpsert,
    ESGSwotItemBrief,
    ESGSwotResponse,
    ESGSwotUpsert,
)

# Контекстные ключевые слова для авто-отбора ESG-релевантных KPI (E/S/G, RU/UZ/EN).
_ESG_KPI_KEYWORDS = (
    # Environmental
    "эколог", "окружающ", "выброс", "парников", "co2", "co₂", "углерод", "карбон",
    "климат", "энергоэффект", "энергосбереж", "энергопотребл", "возобновляем",
    "декарбон", "сточн", "отход", "утилизац", "переработ", "загрязн", "водопотребл",
    "водозабор", "scope 1", "scope 2", "scope 3", "greenhouse", "emission", "carbon",
    "environment", "renewable", "иқлим", "чиқинди", "экологик",
    # Social
    "социальн", "охрана труда", "отипб", "промбезопас", "промышленн безопасн",
    "безопасн труд", "травматизм", "несчастн случа", "профзаболев", "текучест",
    "гендер", "инклюз", "благотворит", "спонсор", "sponsor", "меценат",
    "местн сообществ", "услови труд", "охрана здоров", "social", "ижтимоий",
    # Governance
    "корпоративн управлен", "совет директор", "наблюдательн совет", "антикорруп",
    "комплаенс", "compliance", "кодекс этик", "деловой этик", "прозрачн",
    "раскрыт информац", "governance", "конфликт интерес", "due diligence",
    # General ESG / sustainability
    "esg", "устойчив развит", "sustainab", "барқарор",
)


# Менеджер, под которым складываются KPI, добавленные вручную из ESG-дашборда.
# Все его индикаторы считаются ESG-релевантными независимо от названия.
_ESG_MANAGER_TITLE = "ESG / Устойчивое развитие"


def _is_esg_kpi(name: str) -> bool:
    n = (name or "").lower()
    return any(kw in n for kw in _ESG_KPI_KEYWORDS)


def _kpi_pct(plan, fact, direction: str) -> Optional[float]:
    """Выполнение %: для 'up' = факт/план, для 'down' = план/факт."""
    try:
        p = float(plan) if plan is not None else None
        f = float(fact) if fact is not None else None
    except (TypeError, ValueError):
        return None
    if p is None or f is None:
        return None
    if direction == "down":
        return round(p / f * 100.0, 1) if f else None
    return round(f / p * 100.0, 1) if p else None

# Веса измерений EMS (D6 пока не отслеживается в Фазе 1 — нормализуем по присутствующим).
_WEIGHTS = {"D1": 0.15, "D2": 0.20, "D3": 0.20, "D4": 0.20, "D5": 0.15}


def _iso_stage(iso_stages: list[int]) -> int:
    """3 сертификата ISO → стадия D1 0..4."""
    certified = sum(1 for s in iso_stages if s >= 2)
    inproc = sum(1 for s in iso_stages if s == 1)
    if certified >= 3:
        return 4
    if certified == 2:
        return 3
    if certified == 1:
        return 2
    if inproc > 0:
        return 1
    return 0


def _rating_stage(count: int) -> int:
    """Кол-во независимых ESG-рейтингов → стадия D3 0..4."""
    if count <= 0:
        return 0
    if count == 1:
        return 2
    if count == 2:
        return 3
    return 4


def _median(xs: list[float]) -> float:
    if not xs:
        return 0.0
    s = sorted(xs)
    n = len(s)
    mid = n // 2
    return s[mid] if n % 2 else (s[mid - 1] + s[mid]) / 2


@dataclass
class ESGMaturityService:
    async def _scoped_companies(
        self, db: AsyncSession, scope_company_ids: Optional[Sequence[UUID]],
    ) -> list[Company]:
        q = (
            select(Company)
            .where(Company.is_active.is_(True))
            .order_by(Company.sort_order, Company.name_ru)
        )
        if scope_company_ids is not None:
            q = q.where(Company.id.in_(list(scope_company_ids)))
        return list((await db.execute(q)).scalars().all())

    async def get_heatmap(
        self,
        db: AsyncSession,
        *,
        year: Optional[int],
        scope_company_ids: Optional[Sequence[UUID]],
    ) -> ESGMaturityHeatmap:
        # доступные годы
        yq = await db.execute(select(ESGMaturityCell.year).distinct())
        years = sorted({y for (y,) in yq.all()}, reverse=True)
        target_year = year or (years[0] if years else datetime.now(UTC).year)

        companies = await self._scoped_companies(db, scope_company_ids)
        co_ids = [c.id for c in companies]
        sectors = {s.id: s for s in (await db.execute(select(Sector))).scalars().all()}

        # ячейки за год
        cells_by_co: dict[UUID, list[ESGMaturityCell]] = {}
        if co_ids:
            cq = await db.execute(
                select(ESGMaturityCell).where(
                    ESGMaturityCell.company_id.in_(co_ids),
                    ESGMaturityCell.year == target_year,
                )
            )
            for cell in cq.scalars().all():
                cells_by_co.setdefault(cell.company_id, []).append(cell)

        # ESG-рейтинги (D3) — сами рейтинги (агентство/значение/ссылка) на компанию
        rating_count: dict[UUID, int] = {}
        ratings_by_co: dict[UUID, list[ESGRatingMini]] = {}
        if co_ids:
            # история для «предыдущего» значения (динамика «старый → новый»)
            hist_by: dict[tuple, list[tuple]] = {}
            try:
                from app.models.agency_rating_history import AgencyRatingHistory
                hq = await db.execute(
                    select(AgencyRatingHistory.company_id, AgencyRatingHistory.agency,
                           AgencyRatingHistory.score, AgencyRatingHistory.rating)
                    .where(AgencyRatingHistory.company_id.in_(co_ids),
                           AgencyRatingHistory.is_esg.is_(True))
                    .order_by(AgencyRatingHistory.created_at.desc())
                )
                for cid, ag, score, rating in hq.all():
                    hist_by.setdefault((cid, ag), []).append((score, rating))
            except Exception:
                hist_by = {}
            rq = await db.execute(
                select(AgencyRating).where(
                    AgencyRating.company_id.in_(co_ids),
                    AgencyRating.is_esg.is_(True),
                ).order_by(AgencyRating.agency)
            )
            for ar in rq.scalars().all():
                rating_count[ar.company_id] = rating_count.get(ar.company_id, 0) + 1
                cur_val = (ar.score or ar.rating or "").strip()
                prev = None
                for (s, r) in hist_by.get((ar.company_id, ar.agency), []):
                    v = (s or r or "").strip()
                    if v and v != cur_val:
                        prev = v
                        break
                ratings_by_co.setdefault(ar.company_id, []).append(ESGRatingMini(
                    id=ar.id, agency=ar.agency, rating=ar.rating, score=ar.score,
                    outlook=ar.outlook, report_url=ar.report_url, prev=prev,
                ))

        out_companies: list[ESGMaturityCompany] = []
        ems_list: list[float] = []
        climate_funnel = [0, 0, 0, 0]   # passed stage>=1..4
        risk_funnel = [0, 0, 0]         # passed stage>=1..3
        iso_full = 0
        # Компании вне портфельных сводных (include_in_rollups=false) — исключаются из агрегатов ниже,
        # но только когда область не задана, то есть матрица действительно портфельная. При явной
        # области выборка уже сужена вызывающим — иначе у пользователя, чья область состоит из такой
        # компании, все сводные показатели матрицы окажутся нулевыми.
        apply_rollup_filter = scope_company_ids is None
        rollup_skip: set[UUID] = set()

        for co in companies:
            cells = cells_by_co.get(co.id, [])
            briefs: list[ESGMaturityCellBrief] = []
            iso_stages = [0, 0, 0]
            d2 = d4 = d5 = 0
            d2a = 0   # D2A — прохождение независимого заверения (0 нет / 1 запл. / 2 пройдено)
            not_needed = False
            dim_nr: set[str] = set()   # измерения «не требуется» → вне статистики и EMS
            for cell in cells:
                briefs.append(ESGMaturityCellBrief(
                    dimension=cell.dimension, sub_key=cell.sub_key or "",
                    stage=cell.stage or 0, status_text=cell.status_text,
                    value_text=cell.value_text, evidence_url=cell.evidence_url,
                    due_date=cell.due_date.isoformat() if cell.due_date else None,
                ))
                if cell.dimension == "meta":
                    # служебная ячейка статуса: «не нуждается» → исключение из метрик
                    if (cell.sub_key or "") == "not_needed" and (cell.stage or 0) >= 1:
                        not_needed = True
                elif cell.dimension == "nr":
                    # «не требуется» по конкретному измерению (sub_key = D1..D5, D2A)
                    if (cell.stage or 0) >= 1 and (cell.sub_key or "") in ("D1", "D2", "D2A", "D3", "D4", "D5"):
                        dim_nr.add(cell.sub_key or "")
                elif cell.dimension == "D1":
                    idx = {"iso14001": 0, "iso45001": 1, "iso50001": 2}.get(cell.sub_key or "")
                    if idx is not None:
                        iso_stages[idx] = cell.stage or 0
                elif cell.dimension == "D2":
                    d2 = cell.stage or 0
                elif cell.dimension == "D2A":
                    d2a = cell.stage or 0
                elif cell.dimension == "D4":
                    d4 = cell.stage or 0
                elif cell.dimension == "D5":
                    d5 = cell.stage or 0

            d1 = _iso_stage(iso_stages)
            d3 = _rating_stage(rating_count.get(co.id, 0))
            d2 = min(3, d2)   # legacy D2=4 («+ assurance») → 3; заверение теперь D2A
            dim_stage = {"D1": d1, "D2": d2, "D3": d3, "D4": d4, "D5": d5}

            # EMS — нормализуем по присутствующим весам, исключая «не требуется».
            # Заверение (D2A «пройдено») — верхняя ступень отчётности: поднимает
            # D2 до 4/4 (сохраняет прежнюю семантику legacy-стадии «+ assurance»).
            d2_ems = min(4, d2 + (1 if d2a >= 2 else 0))
            ems_stage = {**dim_stage, "D2": d2_ems}
            active_w = {k: w for k, w in _WEIGHTS.items() if k not in dim_nr}
            total_w = sum(active_w.values()) or 1.0
            ems = sum((ems_stage[k] / 4.0) * w for k, w in active_w.items()) / total_w * 100.0
            ems = round(ems, 1)

            sec = sectors.get(co.sector_id) if co.sector_id else None
            out_companies.append(ESGMaturityCompany(
                company_id=co.id, company_code=co.code,
                company_name=co.name_short or co.name_ru,
                sector_code=(sec.code if sec else None),
                sector_name=(sec.name_ru if sec else None),
                sector_color=(getattr(sec, "color_hex", None) if sec else None),
                cells=briefs, dim_stage=dim_stage, ems=ems,
                rating_count=rating_count.get(co.id, 0),
                ratings=ratings_by_co.get(co.id, []),
                not_needed=not_needed,
                dim_not_required=sorted(dim_nr),
            ))

            # «Не нуждается» → компания не участвует ни в одной агрегированной метрике.
            if not_needed:
                continue
            # include_in_rollups=false → строка в матрице остаётся, но демо/непрофильные компании не искажают портфельные средние и счётчики.
            if apply_rollup_filter and not getattr(co, "include_in_rollups", True):
                rollup_skip.add(co.id)
                continue
            ems_list.append(ems)
            if "D1" not in dim_nr and d1 >= 4:
                iso_full += 1
            if "D4" not in dim_nr:
                for st in range(1, 5):
                    if d4 >= st:
                        climate_funnel[st - 1] += 1
            if "D5" not in dim_nr:
                for st in range(1, 4):
                    if d5 >= st:
                        risk_funnel[st - 1] += 1

        mean = round(sum(ems_list) / len(ems_list), 1) if ems_list else 0.0
        med = round(_median(ems_list), 1)
        baskets = ESGMaturityBaskets(
            mature=sum(1 for e in ems_list if e >= 70),
            developing=sum(1 for e in ems_list if 40 <= e < 70),
            starting=sum(1 for e in ems_list if e < 40),
        )

        return ESGMaturityHeatmap(
            year=target_year, companies=out_companies,
            ems_mean=mean, ems_median=med,
            baskets=baskets,
            climate_funnel=climate_funnel, risk_funnel=risk_funnel,
            iso_full_count=iso_full,
            rated_count=sum(1 for c in out_companies if c.rating_count > 0 and not c.not_needed and "D3" not in c.dim_not_required and c.company_id not in rollup_skip),
            total_companies=sum(1 for c in out_companies if not c.not_needed and c.company_id not in rollup_skip),
            available_years=years or [target_year],
            generated_at=datetime.now(UTC),
        )

    async def upsert_cell(
        self,
        db: AsyncSession,
        payload: ESGMaturityCellUpsert,
        *,
        scope_company_ids: Optional[Sequence[UUID]],
    ) -> ESGMaturityCellBrief:
        if scope_company_ids is not None and payload.company_id not in scope_company_ids:
            raise HTTPException(403, "No access to this company")

        q = select(ESGMaturityCell).where(
            ESGMaturityCell.company_id == payload.company_id,
            ESGMaturityCell.year == payload.year,
            ESGMaturityCell.dimension == payload.dimension,
            ESGMaturityCell.sub_key == (payload.sub_key or ""),
        )
        cell = (await db.execute(q)).scalar_one_or_none()
        if cell is None:
            cell = ESGMaturityCell(
                company_id=payload.company_id, year=payload.year,
                dimension=payload.dimension, sub_key=payload.sub_key or "",
            )
            db.add(cell)

        if payload.stage is not None:
            cell.stage = payload.stage
        if payload.status_text is not None:
            cell.status_text = payload.status_text or None
        if payload.value_text is not None:
            cell.value_text = payload.value_text or None
        if payload.evidence_url is not None:
            cell.evidence_url = payload.evidence_url or None
        if payload.due_date is not None:
            try:
                cell.due_date = date.fromisoformat(payload.due_date) if payload.due_date else None
            except ValueError:
                cell.due_date = None
        if payload.extra is not None:
            cell.extra = payload.extra or None
        cell.last_reviewed_at = datetime.now(UTC)

        await db.commit()
        await db.refresh(cell)
        return ESGMaturityCellBrief(
            dimension=cell.dimension, sub_key=cell.sub_key or "",
            stage=cell.stage or 0, status_text=cell.status_text,
            value_text=cell.value_text, evidence_url=cell.evidence_url,
            due_date=cell.due_date.isoformat() if cell.due_date else None,
        )

    # ─── SWOT / выводы ────────────────────────────────────────────
    async def get_swot(
        self, db: AsyncSession, *, scope_company_ids: Optional[Sequence[UUID]],
    ) -> ESGSwotResponse:
        co_rows = (await db.execute(select(Company.id, Company.code, Company.name_ru, Company.name_short))).all()
        co_meta = {cid: (code, short or name) for cid, code, name, short in co_rows}
        rows = (await db.execute(
            select(ESGSwotItem).order_by(ESGSwotItem.scope, ESGSwotItem.kind, ESGSwotItem.order_idx)
        )).scalars().all()

        def brief(it: ESGSwotItem) -> ESGSwotItemBrief:
            code, name = co_meta.get(it.company_id, (None, None)) if it.company_id else (None, None)
            return ESGSwotItemBrief(
                id=it.id, kind=it.kind, scope=it.scope, company_id=it.company_id,
                company_code=code, company_name=name,
                title=it.title, body=it.body, severity=it.severity, order_idx=it.order_idx,
                created_by_name=it.created_by_name, created_by_title=it.created_by_title,
                created_by_org=it.created_by_org, created_at=it.created_at,
            )

        ps, pw, comp = [], [], []
        for it in rows:
            if it.scope == "company":
                if scope_company_ids is not None and it.company_id not in scope_company_ids:
                    continue
                comp.append(brief(it))
            elif it.kind == "strength":
                ps.append(brief(it))
            else:
                pw.append(brief(it))
        return ESGSwotResponse(
            portfolio_strengths=ps, portfolio_weaknesses=pw, company_items=comp,
            generated_at=datetime.now(UTC),
        )

    @staticmethod
    async def swot_author_snapshot(db: AsyncSession, user) -> tuple:
        """(id, имя, должность, организация) автора — снимок на момент создания.

        Организация: компания из профиля пользователя; у сотрудников самой
        платформы (organization_id пуст) — «UzAssets». Снимок, а не join по
        FK: подпись должна пережить переименование компании и удаление
        аккаунта.
        """
        org = "UzAssets"
        if getattr(user, "organization_id", None):
            row = (await db.execute(
                select(Company.name_short, Company.name_ru)
                .where(Company.id == user.organization_id)
            )).first()
            if row:
                org = row[0] or row[1] or org
        name = user.full_name or user.email
        return user.id, name, getattr(user, "job_title", None), org

    async def upsert_swot(
        self, db: AsyncSession, payload: ESGSwotUpsert,
        *, scope_company_ids: Optional[Sequence[UUID]],
        actor=None,
    ) -> ESGSwotItemBrief:
        if payload.scope == "company" and scope_company_ids is not None \
                and payload.company_id not in scope_company_ids:
            raise HTTPException(403, "No access to this company")
        item: Optional[ESGSwotItem] = None
        if payload.id is not None:
            item = (await db.execute(select(ESGSwotItem).where(ESGSwotItem.id == payload.id))).scalar_one_or_none()
        if item is None:
            item = ESGSwotItem(kind=payload.kind, scope=payload.scope)
            # Автор фиксируется при создании и правками не переписывается:
            # вопрос «кто это добавил» должен иметь один ответ навсегда.
            if actor is not None:
                _uid, _name, _title, _org = await self.swot_author_snapshot(db, actor)
                item.created_by = _uid
                item.created_by_name = _name
                item.created_by_title = _title
                item.created_by_org = _org
            db.add(item)
        item.kind = payload.kind
        item.scope = payload.scope
        item.company_id = payload.company_id if payload.scope == "company" else None
        item.title = payload.title
        item.body = payload.body
        item.severity = payload.severity
        item.order_idx = payload.order_idx
        await db.commit()
        await db.refresh(item)
        return ESGSwotItemBrief(
            id=item.id, kind=item.kind, scope=item.scope, company_id=item.company_id,
            title=item.title, body=item.body, severity=item.severity, order_idx=item.order_idx,
            created_by_name=item.created_by_name, created_by_title=item.created_by_title,
            created_by_org=item.created_by_org, created_at=item.created_at,
        )

    async def delete_swot(
        self, db: AsyncSession, item_id: UUID,
        *, scope_company_ids: Optional[Sequence[UUID]],
    ) -> None:
        """Удалить вывод. Company-scoped пользователь может удалять только
        выводы своих компаний; портфельные — только пользователь без
        ограничения области (scope None)."""
        item = (await db.execute(
            select(ESGSwotItem).where(ESGSwotItem.id == item_id)
        )).scalar_one_or_none()
        if item is None:
            raise HTTPException(404, "SWOT item not found")
        if scope_company_ids is not None:
            if item.scope != "company" or item.company_id not in scope_company_ids:
                raise HTTPException(403, "No access to this item")
        await db.delete(item)
        await db.commit()

    # ─── Годовые ESG-отчёты компании (с 2021) ─────────────────────
    @staticmethod
    def _report_brief(r: ESGReport) -> ESGReportBrief:
        return ESGReportBrief(
            id=r.id, company_id=r.company_id, year=r.year, status=r.status,
            report_url=r.report_url, note=r.note,
            changed_by_name=r.changed_by_name, updated_at=r.updated_at,
        )

    async def get_reports(
        self, db: AsyncSession, *, company_id: UUID,
        scope_company_ids: Optional[Sequence[UUID]],
    ) -> ESGReportListResponse:
        if scope_company_ids is not None and company_id not in scope_company_ids:
            raise HTTPException(403, "No access to this company")
        co = (await db.execute(
            select(Company.code, Company.name_short, Company.name_ru)
            .where(Company.id == company_id)
        )).first()
        rows = list((await db.execute(
            select(ESGReport)
            .where(ESGReport.company_id == company_id)
            .order_by(ESGReport.year.desc())
        )).scalars().all())
        # последняя по времени правка — для подписи «кто менял последним»
        last = max(rows, key=lambda r: r.updated_at, default=None) if rows else None
        return ESGReportListResponse(
            company_id=company_id,
            company_code=(co[0] if co else None),
            company_name=((co[1] or co[2]) if co else None),
            items=[self._report_brief(r) for r in rows],
            last_changed_by_name=(last.changed_by_name if last else None),
            last_changed_at=(last.updated_at if last else None),
            last_changed_year=(last.year if last else None),
            generated_at=datetime.now(UTC),
        )

    async def upsert_report(
        self, db: AsyncSession, payload: ESGReportUpsert,
        *, user: User, scope_company_ids: Optional[Sequence[UUID]],
    ) -> ESGReportBrief:
        if scope_company_ids is not None and payload.company_id not in scope_company_ids:
            raise HTTPException(403, "No access to this company")
        row = (await db.execute(select(ESGReport).where(
            ESGReport.company_id == payload.company_id,
            ESGReport.year == payload.year,
        ))).scalar_one_or_none()
        if row is None:
            row = ESGReport(company_id=payload.company_id, year=payload.year)
            db.add(row)
        if payload.status is not None:
            row.status = (payload.status or "").strip() or None
        if payload.report_url is not None:
            row.report_url = (payload.report_url or "").strip() or None
        if payload.note is not None:
            row.note = (payload.note or "").strip() or None
        row.changed_by = getattr(user, "id", None)
        row.changed_by_name = getattr(user, "full_name", None) or getattr(user, "email", None)
        await db.commit()
        await db.refresh(row)
        return self._report_brief(row)

    # ─── ESG-релевантные KPI по компаниям (из модуля KPI, по контексту) ───
    async def get_esg_kpis(
        self, db: AsyncSession, *, year: int,
        scope_company_ids: Optional[Sequence[UUID]],
    ) -> ESGKpiResponse:
        q = (
            select(KpiManager)
            .where(KpiManager.year == year)
            .options(selectinload(KpiManager.indicators))
        )
        if scope_company_ids is not None:
            q = q.where(KpiManager.company_id.in_(list(scope_company_ids)))
        managers = list((await db.execute(q)).scalars().all())

        co_rows = (await db.execute(select(Company.id, Company.code))).all()
        code_map = {cid: code for cid, code in co_rows}

        by_co: dict[UUID, list[ESGKpiBrief]] = {}
        for m in managers:
            # все индикаторы под ESG-менеджером — ESG; остальные матчим по названию
            mgr_is_esg = _is_esg_kpi(m.title) or _is_esg_kpi(m.short_title or "")
            for ind in m.indicators:
                if not (mgr_is_esg or getattr(ind, "is_esg", False) or _is_esg_kpi(ind.name)):
                    continue
                direction = ind.direction or "up"
                by_co.setdefault(m.company_id, []).append(ESGKpiBrief(
                    name=ind.name,
                    unit=ind.unit,
                    manager=m.short_title or m.title,
                    plan=float(ind.plan_year) if ind.plan_year is not None else None,
                    fact=float(ind.fact_year) if ind.fact_year is not None else None,
                    pct=_kpi_pct(ind.plan_year, ind.fact_year, direction),
                    direction=direction,
                ))
        items = [
            ESGKpiCompany(company_id=cid, company_code=code_map.get(cid), kpis=ks)
            for cid, ks in by_co.items()
        ]
        return ESGKpiResponse(year=year, items=items, generated_at=datetime.now(UTC))

    async def get_kpi_managers(
        self, db: AsyncSession, *, company_id: UUID, year: int,
        scope_company_ids: Optional[Sequence[UUID]],
    ) -> list[ESGKpiManagerBrief]:
        """Существующие «должности» (менеджеры KPI) компании за год — для выбора."""
        if scope_company_ids is not None and company_id not in scope_company_ids:
            raise HTTPException(403, "No access to this company")
        rows = (await db.execute(
            select(KpiManager.id, KpiManager.title, KpiManager.short_title)
            .where(KpiManager.company_id == company_id, KpiManager.year == year)
            .order_by(KpiManager.sort_order, KpiManager.title)
        )).all()
        return [ESGKpiManagerBrief(id=i, title=t, short_title=s) for i, t, s in rows]

    async def add_esg_kpi(
        self, db: AsyncSession, payload: ESGKpiCreate,
        *, scope_company_ids: Optional[Sequence[UUID]],
    ) -> ESGKpiBrief:
        """Добавить ESG-KPI вручную → пишем в модуль KPI (kpi_managers/kpi_indicators).
        Под выбранную должность (manager_id) или общий «ESG / Устойчивое развитие».
        Сразу виден и в /kpi."""
        if scope_company_ids is not None and payload.company_id not in scope_company_ids:
            raise HTTPException(403, "No access to this company")
        from decimal import Decimal

        mgr = None
        if payload.manager_id is not None:
            # выбранная существующая должность — проверяем принадлежность компании/году
            mgr = (await db.execute(select(KpiManager).where(
                KpiManager.id == payload.manager_id,
                KpiManager.company_id == payload.company_id,
                KpiManager.year == payload.year,
            ))).scalar_one_or_none()
            if mgr is None:
                raise HTTPException(404, "Должность (менеджер KPI) не найдена для этой компании/года")
        if mgr is None:
            # дефолт: общий ESG-менеджер (создаём при отсутствии)
            mgr = (await db.execute(select(KpiManager).where(
                KpiManager.company_id == payload.company_id,
                KpiManager.year == payload.year,
                KpiManager.title == _ESG_MANAGER_TITLE,
            ))).scalar_one_or_none()
            if mgr is None:
                mgr = KpiManager(
                    company_id=payload.company_id, year=payload.year,
                    title=_ESG_MANAGER_TITLE, short_title="ESG",
                )
                db.add(mgr)
                await db.flush()

        direction = payload.direction or "up"
        ind = KpiIndicator(
            manager_id=mgr.id,
            name=payload.name.strip(),
            unit=(payload.unit or None),
            direction=direction,
            plan_year=(Decimal(str(payload.plan)) if payload.plan is not None else None),
            fact_year=(Decimal(str(payload.fact)) if payload.fact is not None else None),
            is_esg=True,   # жёсткая ESG-пометка → видна в колонке ESG-KPI независимо от названия
        )
        db.add(ind)
        await db.commit()
        await db.refresh(ind)
        return ESGKpiBrief(
            name=ind.name, unit=ind.unit, manager=mgr.short_title or mgr.title,
            plan=float(ind.plan_year) if ind.plan_year is not None else None,
            fact=float(ind.fact_year) if ind.fact_year is not None else None,
            pct=_kpi_pct(ind.plan_year, ind.fact_year, direction),
            direction=direction,
        )
