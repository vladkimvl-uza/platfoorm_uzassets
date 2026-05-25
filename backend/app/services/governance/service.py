"""Use cases for Governance domain."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional, Sequence
from uuid import UUID

from fastapi import HTTPException

from app.models.governance import BoardMember, GovernanceData
from app.schemas.governance import (
    BoardMemberBrief, BoardMemberCreate, BoardMemberUpdate,
    GovernanceCompanyDetail, GovernanceCompanyScore,
    GovernanceDataBrief, GovernanceDataEdit,
    GovernanceOverviewKpis, GovernanceOverviewResponse,
)
from app.services.governance._helpers import (
    co_data_to_score_row, data_to_brief, diversity_from_members,
    governance_score, member_to_brief,
)
from app.uow.ports import UnitOfWorkABC


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
            all_data = await self.uow.governance.list_governance_data(
                year=year, sector_code=sector_code,
                scope_company_ids=scope_company_ids,
            )

            # Latest data per company if year not specified
            by_co: dict[UUID, GovernanceData] = {}
            for d in all_data:
                existing = by_co.get(d.company_id)
                if existing is None or (d.year or 0) > (existing.year or 0):
                    by_co[d.company_id] = d

            # Rankings
            rankings: list[GovernanceCompanyScore] = []
            co_lookup = {co.id: co for co in companies}
            for co_id, d in by_co.items():
                co = co_lookup.get(co_id)
                if not co:
                    continue
                rankings.append(co_data_to_score_row(d, co))

            def _sort_key(r: GovernanceCompanyScore):
                primary = r.governance_score_1200 if r.governance_score_1200 is not None else r.governance_score
                return (primary is None, -(primary or 0))
            rankings.sort(key=_sort_key)
            for idx, r in enumerate(rankings):
                r.rank = idx + 1
            rankings = rankings[:rankings_limit]

            # KPIs
            if rankings:
                bsizes = [r.board_size for r in rankings if r.board_size]
                ipcts = [r.independent_pct for r in rankings if r.independent_pct is not None]
                wpcts = [r.women_pct for r in rankings if r.women_pct is not None]
                fpcts = [r.foreign_pct for r in rankings if r.foreign_pct is not None]
                attns = [r.attendance_pct for r in rankings if r.attendance_pct is not None]
                meets = [r.meetings_per_year for r in rankings if r.meetings_per_year is not None]
                kpis = GovernanceOverviewKpis(
                    total_companies=len(companies),
                    companies_with_data=len(rankings),
                    avg_board_size=round(sum(bsizes) / len(bsizes), 1) if bsizes else None,
                    avg_independent_pct=round(sum(ipcts) / len(ipcts), 1) if ipcts else None,
                    avg_women_pct=round(sum(wpcts) / len(wpcts), 1) if wpcts else None,
                    avg_foreign_pct=round(sum(fpcts) / len(fpcts), 1) if fpcts else None,
                    avg_attendance_pct=round(sum(attns) / len(attns), 1) if attns else None,
                    avg_meetings_per_year=round(sum(meets) / len(meets), 1) if meets else None,
                    committees_audit_count=sum(1 for d in by_co.values() if d.has_audit_committee),
                    committees_remuneration_count=sum(1 for d in by_co.values() if d.has_remuneration_committee),
                    committees_nomination_count=sum(1 for d in by_co.values() if d.has_nomination_committee),
                    committees_strategy_count=sum(1 for d in by_co.values() if d.has_strategy_committee),
                )
            else:
                kpis = GovernanceOverviewKpis(total_companies=len(companies))

            # Diversity split
            members = await self.uow.governance.list_active_board_members(
                sector_code=sector_code, scope_company_ids=scope_company_ids,
            )
            diversity_split = diversity_from_members(members)

            # Facets
            yrs = await self.uow.governance.all_data_years()
            sectors = await self.uow.governance.sectors_with_counts()

        return GovernanceOverviewResponse(
            year=year, sector_code=sector_code,
            kpis=kpis, diversity_split=diversity_split,
            rankings=rankings,
            available_years=yrs, sectors=sectors,
            generated_at=datetime.now(timezone.utc),
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
                company_name=co.name_ru,
                sector_code=(co.sector.code if co.sector else None),
                year=target_year,
                data=data_to_brief(d) if d else None,
                board_members=members,
                score=score,
                independent_pct=indep_pct,
                women_pct=wm_pct,
                foreign_pct=fo_pct,
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
            if payload.payload is not None:
                d.payload = payload.payload
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
                "appointed_date", "term_end_date", "bio",
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
