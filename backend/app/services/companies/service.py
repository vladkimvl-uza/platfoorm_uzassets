"""Use cases for Companies + Sectors."""
from __future__ import annotations

from collections.abc import Sequence
from typing import Optional
from uuid import UUID

from fastapi import HTTPException
from fastapi import status as http_status

from app.models.company import Company, Sector
from app.models.user import Group
from app.schemas.company import (
    CompanyCreatePayload,
    CompanyDetail,
    CompanyListItem,
    CompanyListResponse,
    CompanyUpdatePayload,
    FinancialLineBrief,
    FinancialReportBrief,
    GovernanceBrief,
    SectorBrief,
    SectorCreatePayload,
    SectorUpdatePayload,
)
from app.uow.ports import UnitOfWorkABC


def _company_to_detail(co: Company) -> CompanyDetail:
    return CompanyDetail(
        id=co.id, code=co.code,
        name_ru=co.name_ru, name_uz=co.name_uz, name_en=co.name_en,
        name_short=co.name_short, legal_form=co.legal_form, inn=co.inn,
        sector=SectorBrief.model_validate(co.sector) if co.sector else None,
        description=co.description, website=co.website,
        address=co.address, ceo_name=co.ceo_name,
        employees_count=co.employees_count, founded_year=co.founded_year,
        is_active=co.is_active, is_custom=co.is_custom, extra=co.extra,
        hidden_years=co.hidden_years or None,
        created_at=co.created_at, updated_at=co.updated_at,
    )


class CompaniesService:
    def __init__(self, uow: UnitOfWorkABC) -> None:
        self.uow = uow

    # ─── list / detail ────────────────────────────────────────────

    async def list_companies(
        self,
        *,
        active_only: bool,
        custom_only: Optional[bool],
        sector_code: Optional[str],
        search: Optional[str],
        scope_company_ids: Optional[Sequence[UUID]],
        sort_by: str,
        sort_dir: str,
        limit: int,
        offset: int,
        hidden_for_year: Optional[int] = None,
    ) -> CompanyListResponse:
        async with self.uow:
            rows, total = await self.uow.companies.list_companies(
                active_only=active_only, custom_only=custom_only,
                sector_code=sector_code, search=search,
                scope_company_ids=scope_company_ids,
                sort_by=sort_by, sort_dir=sort_dir,
                limit=limit, offset=offset,
                hidden_for_year=hidden_for_year,
            )
            company_ids = [c.id for c in rows]
            latest_fin = await self.uow.companies.latest_financials_by_companies(company_ids)
            gov_score = await self.uow.companies.latest_gov_scores_by_companies(company_ids)
            sec_rows = await self.uow.companies.list_sectors()

        items: list[CompanyListItem] = []
        for c in rows:
            fin = latest_fin.get(str(c.id))
            items.append(CompanyListItem(
                id=c.id, code=c.code,
                name_ru=c.name_ru, name_short=c.name_short,
                sector_code=c.sector.code if c.sector else None,
                sector_name=c.sector.name_ru if c.sector else None,
                sector_color=c.sector.color_hex if c.sector else None,
                is_active=c.is_active, is_custom=c.is_custom,
                hidden_years=c.hidden_years or None,
                governance_score=gov_score.get(str(c.id)),
                latest_revenue=fin[1] if fin else None,
                latest_revenue_year=fin[0] if fin else None,
                has_financials=str(c.id) in latest_fin,
                has_governance=str(c.id) in gov_score,
            ))

        # Post-aggregation sorts (need computed fields)
        if sort_by == "governance_score":
            items.sort(key=lambda x: (x.governance_score or -1),
                       reverse=(sort_dir == "desc"))
        elif sort_by == "latest_revenue":
            items.sort(key=lambda x: (x.latest_revenue or 0),
                       reverse=(sort_dir == "desc"))

        sectors = [SectorBrief.model_validate(s) for s in sec_rows]
        return CompanyListResponse(items=items, total=total, sectors=sectors)

    async def get_company_by_code(
        self,
        code: str,
        *,
        scope_company_ids: Optional[Sequence[UUID]],
    ) -> CompanyDetail:
        async with self.uow:
            co = await self.uow.companies.get_by_code(code)
            if co is None:
                raise HTTPException(
                    http_status.HTTP_404_NOT_FOUND,
                    f"Company with code '{code}' not found",
                )
            if scope_company_ids is not None and co.id not in scope_company_ids:
                # 2026-05-26: uniform 404 чтобы не палить факт существования
                # компании через timing/status-code разницу 403 vs 404.
                raise HTTPException(http_status.HTTP_404_NOT_FOUND, "Company not found")
            return _company_to_detail(co)

    async def get_company_financials(
        self,
        code: str,
        *,
        scope_company_ids: Optional[Sequence[UUID]],
    ) -> list[FinancialReportBrief]:
        async with self.uow:
            co = await self.uow.companies.get_by_code_lite(code)
            if not co:
                raise HTTPException(404, f"Company '{code}' not found")
            if scope_company_ids is not None and co.id not in scope_company_ids:
                # 2026-05-26: uniform 404 чтобы не палить факт существования
                # компании через timing/status-code разницу 403 vs 404.
                raise HTTPException(http_status.HTTP_404_NOT_FOUND, "Company not found")
            reports = await self.uow.companies.list_company_financial_reports(co.id)
        return [
            FinancialReportBrief(
                year=r.year, quarter=r.quarter,
                standard=r.standard, report_type=r.report_type,
                currency=r.currency, unit_scale=r.unit_scale,
                source=r.source, is_audited=r.is_audited, notes=r.notes,
                lines=[
                    FinancialLineBrief(
                        line_code=l.line_code,
                        line_name=l.line_name,
                        value=l.value,
                        sort_order=l.sort_order,
                    ) for l in sorted(r.lines, key=lambda x: x.sort_order)
                ],
            )
            for r in reports
        ]

    async def get_company_governance(
        self,
        code: str,
        *,
        scope_company_ids: Optional[Sequence[UUID]],
    ) -> list[GovernanceBrief]:
        async with self.uow:
            co = await self.uow.companies.get_by_code_lite(code)
            if not co:
                raise HTTPException(404, f"Company '{code}' not found")
            if scope_company_ids is not None and co.id not in scope_company_ids:
                # 2026-05-26: uniform 404 чтобы не палить факт существования
                # компании через timing/status-code разницу 403 vs 404.
                raise HTTPException(http_status.HTTP_404_NOT_FOUND, "Company not found")
            rows = await self.uow.companies.list_company_governance(co.id)

        return [
            GovernanceBrief(
                year=r.year,
                board_size=r.board_size,
                independent_directors_count=r.independent_directors_count,
                women_directors_count=r.women_directors_count,
                foreign_directors_count=r.foreign_directors_count,
                avg_age=r.avg_age,
                has_audit_committee=r.has_audit_committee,
                has_strategy_committee=r.has_strategy_committee,
                meetings_per_year=r.meetings_per_year,
                avg_attendance_pct=r.avg_attendance_pct,
                score=r.payload.get("score") if isinstance(r.payload, dict) else None,
                payload=r.payload,
            )
            for r in rows
        ]

    # ─── mutations ────────────────────────────────────────────────

    async def create_company(
        self,
        payload: CompanyCreatePayload,
    ) -> tuple[CompanyDetail, str]:
        """Returns (detail, group_code) — caller uses group_code for audit notes."""
        async with self.uow:
            dup = await self.uow.companies.get_by_code_lite(payload.code)
            if dup:
                raise HTTPException(409, f"Company with code '{payload.code}' already exists")

            sector = None
            if payload.sector_code:
                sector = await self.uow.companies.get_sector_by_code(payload.sector_code)
                if not sector:
                    raise HTTPException(400, f"Unknown sector code: {payload.sector_code}")

            name_ru_clean = (payload.name_ru or "").strip()
            if not name_ru_clean:
                raise HTTPException(422, "name_ru is required")
            name_short_clean = (payload.name_short or "").strip() or name_ru_clean[:128]

            co = Company(
                code=payload.code.lower(),
                name_ru=name_ru_clean, name_short=name_short_clean,
                name_uz=payload.name_uz, name_en=payload.name_en,
                sector_id=sector.id if sector else None,
                legal_form=payload.legal_form, inn=payload.inn,
                description=payload.description, website=payload.website,
                address=payload.address, ceo_name=payload.ceo_name,
                employees_count=payload.employees_count, founded_year=payload.founded_year,
                is_active=True, is_custom=True, sort_order=10000,
            )
            self.uow.companies.add(co)
            await self.uow.companies.flush()

            # Auto-create 1:1 Group for the company             desired_code = co.code
            dup_grp = await self.uow.companies.group_exists_by_code(desired_code)
            grp_code = desired_code if not dup_grp else f"{desired_code}_co"
            grp = Group(code=grp_code, name=co.name_ru, company_id=co.id)
            self.uow.companies.add(grp)

            await self.uow.companies.flush()
            await self.uow.companies.refresh(co)

            # Re-fetch with sector eager-loaded for the response
            co_full = await self.uow.companies.get_by_code(co.code)
            assert co_full is not None
            return _company_to_detail(co_full), grp_code

    async def update_company(
        self,
        code: str,
        payload: CompanyUpdatePayload,
        *,
        scope_company_ids: Optional[Sequence[UUID]],
    ) -> tuple[CompanyDetail, list[str]]:
        """Returns (detail, changes_list) — caller uses changes for audit notes."""
        # Pre-clean payload
        if payload.name_ru is not None:
            nru = payload.name_ru.strip()
            if not nru:
                raise HTTPException(422, "name_ru cannot be empty")
            payload.name_ru = nru
        if payload.name_short is not None:
            ns = payload.name_short.strip()
            if not ns:
                ns = (payload.name_ru or "")[:128]
            payload.name_short = ns

        async with self.uow:
            co = await self.uow.companies.get_by_code_lite(code)
            if not co:
                raise HTTPException(404, f"Company '{code}' not found")
            if scope_company_ids is not None and co.id not in scope_company_ids:
                # 2026-05-26: uniform 404 чтобы не палить факт существования
                # компании через timing/status-code разницу 403 vs 404.
                raise HTTPException(http_status.HTTP_404_NOT_FOUND, "Company not found")

            changes: list[str] = []
            field_map = {
                "name_ru": payload.name_ru, "name_short": payload.name_short,
                "name_uz": payload.name_uz, "name_en": payload.name_en,
                "legal_form": payload.legal_form, "inn": payload.inn,
                "description": payload.description, "website": payload.website,
                "address": payload.address, "ceo_name": payload.ceo_name,
                "employees_count": payload.employees_count,
                "founded_year": payload.founded_year,
                "is_active": payload.is_active, "sort_order": payload.sort_order,
                "hidden_years": payload.hidden_years,
            }
            # name_short fallback to name_ru (post-empty-strip)
            if payload.name_short and payload.name_ru:
                if not payload.name_short.strip():
                    field_map["name_short"] = (payload.name_ru or co.name_ru or co.name_short or co.code)[:128]

            for field, value in field_map.items():
                if value is None:
                    continue
                old = getattr(co, field)
                if old != value:
                    setattr(co, field, value)
                    changes.append(f"{field}: {old!r} → {value!r}")

            if payload.sector_code is not None:
                sector = None
                if payload.sector_code:
                    sector = await self.uow.companies.get_sector_by_code(payload.sector_code)
                    if not sector:
                        raise HTTPException(400, f"Unknown sector code: {payload.sector_code}")
                new_sector_id = sector.id if sector else None
                if co.sector_id != new_sector_id:
                    co.sector_id = new_sector_id
                    changes.append(f"sector_code: → {payload.sector_code!r}")

            await self.uow.companies.flush()
            await self.uow.companies.refresh(co)
            co_full = await self.uow.companies.get_by_code(co.code)
            assert co_full is not None
            return _company_to_detail(co_full), changes

    async def delete_company(
        self,
        code: str,
        *,
        cascade: bool,
        actor_is_owner: bool,
        scope_company_ids: Optional[Sequence[UUID]],
    ) -> tuple[Company, str]:
        """Returns (deleted_co_snapshot, audit_label)."""
        async with self.uow:
            co = await self.uow.companies.get_by_code_lite(code)
            if not co:
                raise HTTPException(404, f"Company '{code}' not found")
            if scope_company_ids is not None and co.id not in scope_company_ids:
                # 2026-05-26: uniform 404 чтобы не палить факт существования
                # компании через timing/status-code разницу 403 vs 404.
                raise HTTPException(http_status.HTTP_404_NOT_FOUND, "Company not found")

            if cascade:
                if not actor_is_owner:
                    raise HTTPException(
                        403,
                        "Cascade delete requires owner status. "
                        "Use soft-delete (?cascade=false) for permanent deactivation.",
                    )
                co_label = f"{co.code} ({co.name_short or co.name_ru})"
                # Snapshot before delete (caller logs it)
                snapshot_co = Company()
                snapshot_co.id = co.id
                snapshot_co.code = co.code
                snapshot_co.name_short = co.name_short
                snapshot_co.name_ru = co.name_ru
                await self.uow.companies.delete(co)
                await self.uow.companies.flush()
                return snapshot_co, co_label
            else:
                co.is_active = False
                await self.uow.companies.flush()
                return co, co.code

    async def delete_company_financials(
        self,
        code: str,
        *,
        standard: Optional[str],
        year: Optional[int],
        scope_company_ids: Optional[Sequence[UUID]],
    ) -> tuple[UUID, int]:
        """Returns (company_id, deleted_count) for audit logging."""
        async with self.uow:
            co = await self.uow.companies.get_by_code_lite(code)
            if not co:
                raise HTTPException(404, f"Company '{code}' not found")
            if scope_company_ids is not None and co.id not in scope_company_ids:
                # 2026-05-26: uniform 404 чтобы не палить факт существования
                # компании через timing/status-code разницу 403 vs 404.
                raise HTTPException(http_status.HTTP_404_NOT_FOUND, "Company not found")
            reports = await self.uow.companies.list_company_financial_reports_filtered(
                co.id, standard=standard, year=year,
            )
            deleted = len(reports)
            for r in reports:
                await self.uow.companies.delete(r)
            await self.uow.companies.flush()
            return co.id, deleted


class SectorsService:
    def __init__(self, uow: UnitOfWorkABC) -> None:
        self.uow = uow

    async def list_sectors(self, *, include_counts: bool) -> list[SectorBrief]:
        async with self.uow:
            if include_counts:
                rows = await self.uow.companies.list_sectors_with_counts()
                return [
                    SectorBrief(
                        id=r.Sector.id, code=r.Sector.code,
                        name_ru=r.Sector.name_ru, name_uz=r.Sector.name_uz, name_en=r.Sector.name_en,
                        color_hex=r.Sector.color_hex, sort_order=r.Sector.sort_order,
                        company_count=r.cnt or 0,
                    )
                    for r in rows
                ]
            else:
                rows = await self.uow.companies.list_sectors()
                return [SectorBrief.model_validate(s) for s in rows]

    async def create_sector(self, payload: SectorCreatePayload) -> SectorBrief:
        async with self.uow:
            dup = await self.uow.companies.get_sector_by_code(payload.code)
            if dup:
                raise HTTPException(409, f"Sector '{payload.code}' already exists")
            s = Sector(
                code=payload.code,
                name_ru=payload.name_ru, name_uz=payload.name_uz, name_en=payload.name_en,
                color_hex=payload.color_hex, sort_order=payload.sort_order,
            )
            self.uow.companies.add(s)
            await self.uow.companies.flush()
            await self.uow.companies.refresh(s)
            return SectorBrief.model_validate(s)

    async def update_sector(self, code: str, payload: SectorUpdatePayload) -> tuple[SectorBrief, list[str]]:
        async with self.uow:
            s = await self.uow.companies.get_sector_by_code(code)
            if not s:
                raise HTTPException(404, f"Sector '{code}' not found")
            changes: list[str] = []
            for field in ("name_ru", "name_uz", "name_en", "color_hex", "sort_order"):
                v = getattr(payload, field)
                if v is None:
                    continue
                old = getattr(s, field)
                if old != v:
                    setattr(s, field, v)
                    changes.append(f"{field}: {old!r}→{v!r}")
            await self.uow.companies.flush()
            await self.uow.companies.refresh(s)
            return SectorBrief.model_validate(s), changes

    async def delete_sector(self, code: str) -> UUID:
        async with self.uow:
            s = await self.uow.companies.get_sector_by_code(code)
            if not s:
                raise HTTPException(404, f"Sector '{code}' not found")
            dep_count = await self.uow.companies.count_active_companies_in_sector(s.id)
            if dep_count > 0:
                raise HTTPException(
                    409,
                    f"Sector '{code}' is in use by {dep_count} active company(ies). "
                    "Repoint them to a different sector first.",
                )
            sid = s.id
            await self.uow.companies.delete(s)
            await self.uow.companies.flush()
            return sid
