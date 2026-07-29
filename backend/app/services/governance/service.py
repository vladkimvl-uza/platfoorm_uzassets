"""Use cases for Governance domain."""
from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Optional
from uuid import UUID

from fastapi import HTTPException

from app.core.i18n import current_locale, tr
from app.models.governance import BoardMember, CommitteeMeeting, GovernanceData
from app.schemas.governance import (
    COMMITTEE_MEETING_FIELDS,
    BoardMemberBrief,
    BoardMemberCreate,
    BoardMemberUpdate,
    CommitteeMeetingCell,
    CommitteeMeetingCompanyRow,
    CommitteeMeetingPeriod,
    CommitteeMeetingPeriodCreate,
    CommitteeMeetingPeriodCreateResult,
    CommitteeMeetingsResponse,
    CommitteeMeetingUpsert,
    CommitteeMeetingUpsertResult,
    GovernanceCompanyDetail,
    GovernanceCompanyScore,
    GovernanceDataBrief,
    GovernanceDataEdit,
    GovernanceOverviewKpis,
    GovernanceOverviewResponse,
)
from app.services.governance._helpers import (
    co_data_to_score_row,
    data_to_brief,
    diversity_from_members,
    governance_score,
    member_to_brief,
)
from app.uow.ports import UnitOfWorkABC


# Периоды, которые GET всегда отдаёт по умолчанию (даже на пустой таблице) —
# совпадают с seed'ом (2025 годовой + 2026 Q1).
_DEFAULT_COMMITTEE_PERIODS: tuple[tuple[int, Optional[int]], ...] = (
    (2025, None),
    (2026, 1),
)


def _period_key(year: int, quarter: Optional[int]) -> str:
    """Ключ ячейки: '<year>:<quarter|0>' (0 = годовой период)."""
    return f"{year}:{quarter or 0}"


def _period_label(year: int, quarter: Optional[int]) -> str:
    """Подпись периода: '2025' (годовой) | '2026 · Q1' (квартал)."""
    return str(year) if not quarter else f"{year} · Q{quarter}"


def _committee_cell(m: CommitteeMeeting) -> CommitteeMeetingCell:
    return CommitteeMeetingCell(
        sb_meetings=m.sb_meetings,
        sb_decisions=m.sb_decisions,
        audit_mtg=m.audit_mtg,
        strategy_mtg=m.strategy_mtg,
        nomrem_mtg=m.nomrem_mtg,
        anticorr_mtg=m.anticorr_mtg,
    )


_CM_FIELDS = ("sb_meetings", "sb_decisions", "audit_mtg",
              "strategy_mtg", "nomrem_mtg", "anticorr_mtg")


def _aggregate_committee_meetings(rows: list) -> dict:
    """Годовой агрегат заседаний БЕЗ двойного счёта: если есть квартальные строки
    (quarter не NULL) — суммируем их; иначе берём годовую (quarter IS NULL).
    Каждое поле None, если ни одна учтённая строка его не заполнила (нет данных ≠ 0)."""
    quarterly = [r for r in rows if r.quarter is not None]
    used = quarterly if quarterly else [r for r in rows if r.quarter is None]
    out: dict = {f: None for f in _CM_FIELDS}
    for r in used:
        for f in _CM_FIELDS:
            v = getattr(r, f, None)
            if v is not None:
                out[f] = (out[f] or 0) + v
    return out


class GovernanceService:
    def __init__(self, uow: UnitOfWorkABC) -> None:
        self.uow = uow

    # ─── Overview dashboard ───────────────────────────────────────

    async def get_overview(
        self,
        *,
        year: Optional[int],
        sector_code: Optional[str],
        rankings_limit: int,
        scope_company_ids: Optional[Sequence[UUID]],
    ) -> GovernanceOverviewResponse:
        async with self.uow:
            companies = await self.uow.governance.list_companies(
                sector_code=sector_code,
                scope_company_ids=scope_company_ids,
            )
            if scope_company_ids is None:
                # Только для ПОРТФЕЛЬНОГО запроса: демо и непрофильные компании не
                # должны искажать сводные цифры КУ (средние, счётчики комитетов,
                # ранжирование, total_companies). При явной области выборка уже
                # сужена вызывающим, и отсеивать её второй раз нельзя — иначе
                # пользователь с областью из такой компании увидит пустой экран.
                companies = [co for co in companies if co.include_in_rollups]
            all_data = await self.uow.governance.list_governance_data(
                year=year, sector_code=sector_code,
                scope_company_ids=scope_company_ids,
            )
            # companies уже сужен (is_active, для портфельного запроса — и rollups); данные КУ — нет.
            # Отсекаем данные компаний вне свода, иначе committee-счётчики их считали.
            active_ids = {co.id for co in companies}
            all_data = [d for d in all_data if d.company_id in active_ids]

            # Latest data per company if year not specified
            by_co: dict[UUID, GovernanceData] = {}
            for d in all_data:
                existing = by_co.get(d.company_id)
                if existing is None or (d.year or 0) > (existing.year or 0):
                    by_co[d.company_id] = d

            # Committee-meeting evidence per company (за год данных компании).
            # Аудит governance «флаг≠работа»: KPI-плитки комитетов считаем по ФАКТУ
            # (комитет заявлен флагом И были заседания в этом году), а не по одному
            # булеву флагу. Headline-балл (legacy 0..1200) и ранги не трогаем.
            cm_rows = await self.uow.governance.list_committee_meetings(
                scope_company_ids=scope_company_ids,
            )
            cm_by_co: dict[UUID, list] = {}
            for m in cm_rows:
                if m.company_id in active_ids:
                    cm_by_co.setdefault(m.company_id, []).append(m)
            cm_agg_by_co: dict[UUID, dict] = {}
            for _cid, _d in by_co.items():
                _rows = [r for r in cm_by_co.get(_cid, []) if r.year == _d.year]
                cm_agg_by_co[_cid] = _aggregate_committee_meetings(_rows)

            def _cm_met(cid: UUID, field: str) -> bool:
                return (cm_agg_by_co.get(cid, {}).get(field) or 0) > 0

            # Rankings
            rankings: list[GovernanceCompanyScore] = []
            co_lookup = {co.id: co for co in companies}
            for co_id, d in by_co.items():
                co = co_lookup.get(co_id)
                if not co:
                    continue
                rankings.append(co_data_to_score_row(d, co))

            def _sort_key(r: GovernanceCompanyScore):
                # Единая шкала 0..100: legacy 0..1200 нормируем /12 (иначе смешение шкал
                # рушит порядок — компания с legacy-баллом 800 обгоняла computed-95).
                primary = (r.governance_score_1200 / 12) if r.governance_score_1200 is not None else r.governance_score
                return (primary is None, -(primary or 0))
            rankings.sort(key=_sort_key)
            for idx, r in enumerate(rankings):
                r.rank = idx + 1
            full_rankings = rankings                  # все компании с данными
            rankings = rankings[:rankings_limit]       # обрезка ТОЛЬКО для списка рейтинга

            # KPIs — по ПОЛНОМУ набору (обрезка rankings_limit не должна занижать портфель;
            # committee-счётчики уже по by_co.values() = полный набор → согласованно).
            if full_rankings:
                bsizes = [r.board_size for r in full_rankings if r.board_size]
                ipcts = [r.independent_pct for r in full_rankings if r.independent_pct is not None]
                wpcts = [r.women_pct for r in full_rankings if r.women_pct is not None]
                fpcts = [r.foreign_pct for r in full_rankings if r.foreign_pct is not None]
                attns = [r.attendance_pct for r in full_rankings if r.attendance_pct is not None]
                meets = [r.meetings_per_year for r in full_rankings if r.meetings_per_year is not None]
                kpis = GovernanceOverviewKpis(
                    total_companies=len(companies),
                    companies_with_data=len(full_rankings),
                    avg_board_size=round(sum(bsizes) / len(bsizes), 1) if bsizes else None,
                    avg_independent_pct=round(sum(ipcts) / len(ipcts), 1) if ipcts else None,
                    avg_women_pct=round(sum(wpcts) / len(wpcts), 1) if wpcts else None,
                    avg_foreign_pct=round(sum(fpcts) / len(fpcts), 1) if fpcts else None,
                    avg_attendance_pct=round(sum(attns) / len(attns), 1) if attns else None,
                    avg_meetings_per_year=round(sum(meets) / len(meets), 1) if meets else None,
                    # Флаг И есть заседания за год (флаг≠работа): комитет без единого
                    # заседания больше не засчитывается как действующий.
                    committees_audit_count=sum(
                        1 for cid, d in by_co.items()
                        if d.has_audit_committee and _cm_met(cid, "audit_mtg")),
                    # «Назначения и вознаграждения» — ОДИН комитет (nomination||remuneration);
                    # оба поля отражают его (раньше считали раздельно → колонки NULL → всегда 0).
                    committees_remuneration_count=sum(
                        1 for cid, d in by_co.items()
                        if (d.has_nomination_committee or d.has_remuneration_committee)
                        and _cm_met(cid, "nomrem_mtg")),
                    committees_nomination_count=sum(
                        1 for cid, d in by_co.items()
                        if (d.has_nomination_committee or d.has_remuneration_committee)
                        and _cm_met(cid, "nomrem_mtg")),
                    committees_strategy_count=sum(
                        1 for cid, d in by_co.items()
                        if d.has_strategy_committee and _cm_met(cid, "strategy_mtg")),
                )
            else:
                kpis = GovernanceOverviewKpis(total_companies=len(companies))

            # Diversity split
            members = await self.uow.governance.list_active_board_members(
                sector_code=sector_code, scope_company_ids=scope_company_ids,
            )
            # Не учитываем составы советов деактивированных компаний.
            members = [m for m in members if m.company_id in active_ids]
            diversity_split = diversity_from_members(members)

            # Facets
            yrs = await self.uow.governance.all_data_years()
            sectors = await self.uow.governance.sectors_with_counts()

        return GovernanceOverviewResponse(
            year=year, sector_code=sector_code,
            kpis=kpis, diversity_split=diversity_split,
            rankings=rankings,
            available_years=yrs, sectors=sectors,
            generated_at=datetime.now(UTC),
        )

    # ─── Company detail ───────────────────────────────────────────

    async def get_company_detail(
        self,
        company_id: UUID,
        *,
        year: Optional[int],
        scope_company_ids: Optional[Sequence[UUID]],
    ) -> GovernanceCompanyDetail:
        async with self.uow:
            co = await self.uow.governance.get_company(
                company_id, scope_company_ids=scope_company_ids,
            )
            if not co:
                raise HTTPException(404, detail="Company not found")

            available_years = await self.uow.governance.list_years_for(company_id)
            target_year = year or (available_years[0] if available_years else datetime.now().year)
            d = await self.uow.governance.get_data_for(company_id, target_year)
            members_rows = await self.uow.governance.list_company_board_members(company_id)
            members = [member_to_brief(m) for m in members_rows]

            # Агрегат заседаний за год из committee_meetings — ЕДИНЫЙ источник.
            # Правило без двойного счёта: если есть квартальные строки — суммируем
            # ИХ; иначе берём годовую (quarter IS NULL). Пустой агрегат → None.
            cm_rows = await self.uow.governance.list_committee_meetings_for_company_year(
                company_id, target_year,
            )
            cm_agg = _aggregate_committee_meetings(cm_rows)

            indep_pct = wm_pct = fo_pct = score = None
            if d:
                bs = d.board_size or 0
                if bs:
                    if d.independent_directors_count is not None:
                        indep_pct = round(100 * d.independent_directors_count / bs, 1)
                    if d.women_directors_count is not None:
                        wm_pct = round(100 * d.women_directors_count / bs, 1)
                    if d.foreign_directors_count is not None:
                        fo_pct = round(100 * d.foreign_directors_count / bs, 1)
                score = governance_score(d)

            return GovernanceCompanyDetail(
                company_id=co.id,
                company_code=co.code,
                company_name=co.name_short or co.name_ru,   # короткое имя (как в финансах)
                sector_code=(co.sector.code if co.sector else None),
                year=target_year,
                data=data_to_brief(d) if d else None,
                board_members=members,
                score=score,
                independent_pct=indep_pct,
                women_pct=wm_pct,
                foreign_pct=fo_pct,
                sb_meetings_year=cm_agg["sb_meetings"],
                sb_decisions_year=cm_agg["sb_decisions"],
                audit_mtg_year=cm_agg["audit_mtg"],
                strategy_mtg_year=cm_agg["strategy_mtg"],
                nomrem_mtg_year=cm_agg["nomrem_mtg"],
                anticorr_mtg_year=cm_agg["anticorr_mtg"],
                available_years=available_years,
            )

    # ─── governance_data upsert ───────────────────────────────────

    async def upsert_governance_data(
        self,
        payload: GovernanceDataEdit,
        *,
        scope_company_ids: Optional[Sequence[UUID]],
    ) -> GovernanceDataBrief:
        # Sanity checks (independent of DB state)
        if payload.board_size is not None:
            for fld in ("independent_directors_count", "women_directors_count", "foreign_directors_count"):
                v = getattr(payload, fld)
                if v is not None and v > payload.board_size:
                    raise HTTPException(
                        400,
                        detail=f"{fld} ({v}) cannot exceed board_size ({payload.board_size})",
                    )

        # Scope
        if scope_company_ids is not None and payload.company_id not in scope_company_ids:
            raise HTTPException(403, detail="No access to this company")

        async with self.uow:
            d = await self.uow.governance.get_data_for(payload.company_id, payload.year)
            if d is None:
                d = GovernanceData(
                    company_id=payload.company_id, year=payload.year,
                )
                self.uow.governance.add(d)

            d.board_size = payload.board_size
            d.independent_directors_count = payload.independent_directors_count
            d.women_directors_count = payload.women_directors_count
            d.foreign_directors_count = payload.foreign_directors_count
            d.avg_age = payload.avg_age
            d.has_audit_committee = payload.has_audit_committee
            d.has_remuneration_committee = payload.has_remuneration_committee
            d.has_nomination_committee = payload.has_nomination_committee
            d.has_strategy_committee = payload.has_strategy_committee
            d.meetings_per_year = payload.meetings_per_year
            d.avg_attendance_pct = payload.avg_attendance_pct
            # Расширенные комитеты/практики хранятся в payload — мержим, не затирая
            # прочие ключи (vacant/exec/nonexec/score/ageAvg…).
            pl = dict(d.payload or {})
            if payload.payload is not None:
                pl.update(payload.payload)
            for fld, key in (
                ("has_anticorr_committee", "anticorr"),
                ("has_procurement_committee", "procurement"),
                ("has_esg_committee", "esg"),
                ("has_dno_insurance", "dno"),
                ("has_induction_program", "induction"),
            ):
                v = getattr(payload, fld, None)
                if v is not None:
                    pl[key] = v
            d.payload = pl or None
            d.notes = payload.notes

            await self.uow.governance.flush()
            await self.uow.governance.refresh(d)
            return data_to_brief(d)

    # ─── board members ────────────────────────────────────────────

    async def list_board_members(
        self,
        company_id: UUID,
        *,
        include_past: bool,
        scope_company_ids: Optional[Sequence[UUID]],
    ) -> list[BoardMemberBrief]:
        if scope_company_ids is not None and company_id not in scope_company_ids:
            raise HTTPException(404, detail="Company not found")
        async with self.uow:
            rows = await self.uow.governance.list_company_board_members(
                company_id, include_past=include_past,
            )
        return [member_to_brief(m) for m in rows]

    async def create_board_member(
        self,
        payload: BoardMemberCreate,
        *,
        scope_company_ids: Optional[Sequence[UUID]],
    ) -> BoardMemberBrief:
        if scope_company_ids is not None and payload.company_id not in scope_company_ids:
            raise HTTPException(403, detail="Forbidden")
        async with self.uow:
            m = BoardMember(
                company_id=payload.company_id,
                full_name=payload.full_name,
                position=payload.position,
                role_type=payload.role_type,
                is_independent=payload.is_independent,
                is_woman=payload.is_woman,
                is_foreign=payload.is_foreign,
                appointed_date=payload.appointed_date,
                term_end_date=payload.term_end_date,
                email=payload.email,
                phone=payload.phone,
                bio=payload.bio,
            )
            self.uow.governance.add(m)
            await self.uow.governance.flush()
            await self.uow.governance.refresh(m)
            return member_to_brief(m)

    async def update_board_member(
        self,
        member_id: UUID,
        payload: BoardMemberUpdate,
        *,
        scope_company_ids: Optional[Sequence[UUID]],
    ) -> tuple[BoardMember, BoardMemberBrief]:
        """Returns (member_orm, brief) — route can read m.company_id/full_name for moderation gate."""
        async with self.uow:
            m = await self.uow.governance.get_member(member_id)
            if not m:
                raise HTTPException(404, detail="Member not found")
            if scope_company_ids is not None and m.company_id not in scope_company_ids:
                raise HTTPException(403, detail="Forbidden")

            for field in (
                "full_name", "position", "role_type",
                "is_independent", "is_woman", "is_foreign",
                "appointed_date", "term_end_date",
                "email", "phone", "bio",
            ):
                v = getattr(payload, field)
                if v is not None:
                    setattr(m, field, v)

            await self.uow.governance.flush()
            await self.uow.governance.refresh(m)
            return m, member_to_brief(m)

    async def get_member_for_moderation(
        self,
        member_id: UUID,
        *,
        scope_company_ids: Optional[Sequence[UUID]],
    ) -> BoardMember:
        """Lookup helper for route's moderation gate (needs full_name + company_id)."""
        async with self.uow:
            m = await self.uow.governance.get_member(member_id)
        if not m:
            raise HTTPException(404, detail="Member not found")
        if scope_company_ids is not None and m.company_id not in scope_company_ids:
            raise HTTPException(403, detail="Forbidden")
        return m

    async def delete_board_member(
        self,
        member_id: UUID,
        *,
        scope_company_ids: Optional[Sequence[UUID]],
    ) -> None:
        async with self.uow:
            m = await self.uow.governance.get_member(member_id)
            if not m:
                return  # idempotent
            if scope_company_ids is not None and m.company_id not in scope_company_ids:
                raise HTTPException(403, detail="Forbidden")
            await self.uow.governance.delete(m)
            await self.uow.governance.flush()

    # ─── committee meetings (кол-во заседаний по периодам) ────────

    async def get_committee_meetings(
        self,
        *,
        scope_company_ids: Optional[Sequence[UUID]],
    ) -> CommitteeMeetingsResponse:
        async with self.uow:
            companies = await self.uow.governance.list_companies(
                sector_code=None, scope_company_ids=scope_company_ids,
            )
            rows = await self.uow.governance.list_committee_meetings(
                scope_company_ids=scope_company_ids,
            )

        # Периоды: дефолтные + те, что реально присутствуют в строках.
        period_set: set[tuple[int, Optional[int]]] = set(_DEFAULT_COMMITTEE_PERIODS)
        cells_by_co: dict[UUID, dict[str, CommitteeMeetingCell]] = {}
        for m in rows:
            period_set.add((m.year, m.quarter))
            cells_by_co.setdefault(m.company_id, {})[
                _period_key(m.year, m.quarter)
            ] = _committee_cell(m)

        # Сортировка периодов: по году, затем годовой(0) → кварталы 1..4.
        periods = sorted(period_set, key=lambda p: (p[0], p[1] or 0))
        period_models = [
            CommitteeMeetingPeriod(year=y, quarter=q, label=_period_label(y, q))
            for y, q in periods
        ]

        co_rows: list[CommitteeMeetingCompanyRow] = []
        for co in companies:
            co_rows.append(CommitteeMeetingCompanyRow(
                company_id=co.id,
                name=co.name_ru,
                name_short=co.name_short,
                sector_code=(co.sector.code if co.sector else None),
                cells=cells_by_co.get(co.id, {}),
            ))
        # Стабильный порядок: по названию (RU).
        co_rows.sort(key=lambda r: (r.name or "").lower())

        return CommitteeMeetingsResponse(periods=period_models, companies=co_rows)

    async def upsert_committee_meeting(
        self,
        payload: CommitteeMeetingUpsert,
        *,
        scope_company_ids: Optional[Sequence[UUID]],
    ) -> CommitteeMeetingUpsertResult:
        if payload.field not in COMMITTEE_MEETING_FIELDS:
            raise HTTPException(
                400,
                detail=tr(
                    "Недопустимое поле: {field}",
                    current_locale(), field=payload.field,
                ),
            )
        if scope_company_ids is not None and payload.company_id not in scope_company_ids:
            raise HTTPException(403, detail="No access to this company")

        async with self.uow:
            m = await self.uow.governance.get_committee_meeting(
                payload.company_id, payload.year, payload.quarter,
            )
            if m is None:
                m = CommitteeMeeting(
                    company_id=payload.company_id,
                    year=payload.year,
                    quarter=payload.quarter,
                )
                self.uow.governance.add(m)
            setattr(m, payload.field, payload.value)
            await self.uow.governance.flush()
            await self.uow.governance.refresh(m)
            cell = _committee_cell(m)

        return CommitteeMeetingUpsertResult(
            company_id=payload.company_id,
            year=payload.year,
            quarter=payload.quarter,
            cell=cell,
        )

    async def create_committee_period(
        self,
        payload: CommitteeMeetingPeriodCreate,
    ) -> CommitteeMeetingPeriodCreateResult:
        """Период создаётся лениво — строки появляются при первом PUT. Здесь только
        валидация (Pydantic) + эхо периода для фронта."""
        return CommitteeMeetingPeriodCreateResult(
            ok=True,
            period=CommitteeMeetingPeriod(
                year=payload.year,
                quarter=payload.quarter,
                label=_period_label(payload.year, payload.quarter),
            ),
        )
