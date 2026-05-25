"""Use cases for Companies+Sectors admin v2."""
from __future__ import annotations

from typing import Optional
from uuid import UUID

from fastapi import HTTPException, status as http_status

from app.models.company import Company, CompanyYearOverride, Sector
from app.models.user import Group
from app.schemas.companies_admin import (
    Badge,
    CompanyAdminCreate, CompanyAdminRead, CompanyAdminUpdate,
    CompanyTreeNode,
    CompanyYearOverrideRead, CompanyYearOverridesBulk,
    SectorAdminCreate, SectorAdminRead, SectorAdminUpdate,
)
from app.uow.ports import UnitOfWorkABC


class CompaniesAdminV2Service:
    def __init__(self, uow: UnitOfWorkABC) -> None:
        self.uow = uow

    # ─── hydration helpers (need session) ─────────────────────────

    async def _to_admin_read(self, c: Company) -> CompanyAdminRead:
        r = self.uow.companies_admin_v2
        sector_code = sector_name = None
        if c.sector_id:
            s = await r.get_sector_by_id(c.sector_id)
            if s:
                sector_code = s.code
                sector_name = s.name_ru
        parent_code = await r.get_parent_code_by_id(c.parent_id) if c.parent_id else None
        children_count = await r.count_children(c.id)
        yo_count = await r.count_year_overrides(c.id)

        return CompanyAdminRead(
            id=c.id, code=c.code, name_ru=c.name_ru, name_short=c.name_short,
            name_uz=c.name_uz, name_en=c.name_en,
            legal_form=c.legal_form, inn=c.inn,
            sector_id=c.sector_id, sector_code=sector_code, sector_name=sector_name,
            description=c.description, logo_url=c.logo_url,
            website=c.website, address=c.address,
            ceo_name=c.ceo_name, employees_count=c.employees_count,
            founded_year=c.founded_year,
            is_active=c.is_active, is_custom=c.is_custom, sort_order=c.sort_order,
            primary_color=c.primary_color, secondary_color=c.secondary_color,
            badges=[Badge(**b) for b in (c.badges or [])] if c.badges else None,
            status=c.status,
            is_pinned=c.is_pinned, include_in_rollups=c.include_in_rollups,
            module_flags=c.module_flags,
            parent_id=c.parent_id, parent_code=parent_code,
            portfolio_start_year=c.portfolio_start_year,
            primary_currency=c.primary_currency, fy_start_month=c.fy_start_month,
            track_inflation=c.track_inflation,
            bloomberg_ticker=c.bloomberg_ticker, isin=c.isin, lei=c.lei,
            tags=c.tags, aliases=c.aliases,
            children_count=children_count, year_overrides_count=yo_count,
        )

    async def _sector_to_read(self, s: Sector) -> SectorAdminRead:
        cnt = await self.uow.companies_admin_v2.count_companies_in_sector(s.id)
        return SectorAdminRead(
            id=s.id, code=s.code,
            name_ru=s.name_ru, name_uz=s.name_uz, name_en=s.name_en,
            color_hex=s.color_hex, color_secondary=s.color_secondary,
            icon_name=s.icon_name, short_badge=s.short_badge,
            sort_order=s.sort_order, aliases=s.aliases,
            companies_count=cnt,
        )

    # ─── companies ────────────────────────────────────────────────

    async def list_companies(
        self,
        *,
        sector: Optional[str], status_filter: Optional[str],
        only_active: bool, search: Optional[str],
    ) -> list[CompanyAdminRead]:
        async with self.uow:
            rows = await self.uow.companies_admin_v2.list_companies(
                sector_code=sector, status_filter=status_filter,
                only_active=only_active, search=search,
            )
            return [await self._to_admin_read(c) for c in rows]

    async def get_company(self, code: str) -> CompanyAdminRead:
        async with self.uow:
            c = await self.uow.companies_admin_v2.get_company_by_code(code)
            if not c:
                raise HTTPException(http_status.HTTP_404_NOT_FOUND, "Company not found")
            return await self._to_admin_read(c)

    async def create_company(
        self, body: CompanyAdminCreate,
    ) -> CompanyAdminRead:
        async with self.uow:
            r = self.uow.companies_admin_v2
            existing = await r.get_company_by_code(body.code)
            if existing:
                raise HTTPException(
                    http_status.HTTP_409_CONFLICT,
                    f"Company '{body.code}' already exists",
                )
            sector_id = None
            if body.sector_code:
                sector_id = await r.get_sector_id_by_code(body.sector_code)
            parent_id = None
            if body.parent_code:
                parent_id = await r.get_company_id_by_code(body.parent_code)

            c = Company(
                code=body.code, name_ru=body.name_ru, name_short=body.name_short,
                name_uz=body.name_uz, name_en=body.name_en,
                sector_id=sector_id, legal_form=body.legal_form, inn=body.inn,
                founded_year=body.founded_year, parent_id=parent_id,
                portfolio_start_year=body.portfolio_start_year,
                status=body.status or "active",
                is_active=True, is_custom=True,
            )
            r.add(c)
            await r.flush()

            # Auto-create 1:1 Group (Pack 148)
            desired_code = c.code
            dup_grp = await r.group_exists_by_code(desired_code)
            grp_code = desired_code if not dup_grp else f"{desired_code}_co"
            r.add(Group(code=grp_code, name=c.name_ru, company_id=c.id))

            await r.flush()
            return await self._to_admin_read(c)

    async def update_company(
        self, code: str, body: CompanyAdminUpdate,
    ) -> CompanyAdminRead:
        async with self.uow:
            r = self.uow.companies_admin_v2
            c = await r.get_company_by_code(code)
            if not c:
                raise HTTPException(http_status.HTTP_404_NOT_FOUND, "Company not found")

            data = body.model_dump(exclude_unset=True)

            if "sector_code" in data:
                sc = data.pop("sector_code")
                c.sector_id = (await r.get_sector_id_by_code(sc)) if sc else None

            if "parent_code" in data:
                pc = data.pop("parent_code")
                if pc:
                    if pc == code:
                        raise HTTPException(
                            http_status.HTTP_400_BAD_REQUEST,
                            "Company cannot be its own parent",
                        )
                    pid = await r.get_company_id_by_code(pc)
                    if pid is None:
                        raise HTTPException(
                            http_status.HTTP_400_BAD_REQUEST,
                            f"Parent company '{pc}' not found",
                        )
                    # Cycle check (walks up to 10 levels)
                    current = pid
                    for _ in range(10):
                        nxt = await r.get_parent_id_for_cycle_check(current)
                        if nxt is None:
                            break
                        if nxt == c.id:
                            raise HTTPException(
                                http_status.HTTP_400_BAD_REQUEST,
                                "Hierarchy cycle detected",
                            )
                        current = nxt
                    c.parent_id = pid
                else:
                    c.parent_id = None

            if "badges" in data:
                badges = data.pop("badges")
                c.badges = [
                    b.model_dump() if hasattr(b, "model_dump") else b for b in badges
                ] if badges else None

            for k, v in data.items():
                setattr(c, k, v)

            await r.flush()
            return await self._to_admin_read(c)

    async def delete_company(self, code: str) -> None:
        async with self.uow:
            r = self.uow.companies_admin_v2
            c = await r.get_company_by_code(code)
            if not c:
                raise HTTPException(http_status.HTTP_404_NOT_FOUND, "Company not found")
            children = await r.count_children(c.id)
            if children:
                raise HTTPException(
                    http_status.HTTP_400_BAD_REQUEST,
                    f"Has {children} subsidiaries — reassign first",
                )
            await r.delete(c)
            await r.flush()

    # ─── year overrides ───────────────────────────────────────────

    async def list_year_overrides(self, code: str) -> list[CompanyYearOverrideRead]:
        async with self.uow:
            r = self.uow.companies_admin_v2
            c = await r.get_company_by_code(code)
            if not c:
                raise HTTPException(http_status.HTTP_404_NOT_FOUND, "Company not found")
            rows = await r.list_year_overrides(c.id)
            out: list[CompanyYearOverrideRead] = []
            for ov in rows:
                sec_code = None
                if ov.sector_override_id:
                    sec_code = await r.get_sector_code_by_id(ov.sector_override_id)
                out.append(CompanyYearOverrideRead(
                    id=ov.id, company_id=ov.company_id, year=ov.year,
                    is_hidden=ov.is_hidden, name_override=ov.name_override,
                    sector_override_id=ov.sector_override_id,
                    sector_override_code=sec_code,
                    exclusion_reason=ov.exclusion_reason, notes=ov.notes,
                ))
            return out

    async def replace_year_overrides(
        self, code: str, body: CompanyYearOverridesBulk,
    ) -> list[CompanyYearOverrideRead]:
        async with self.uow:
            r = self.uow.companies_admin_v2
            c = await r.get_company_by_code(code)
            if not c:
                raise HTTPException(http_status.HTTP_404_NOT_FOUND, "Company not found")
            await r.delete_overrides_for_company(c.id)
            for o in body.overrides:
                sec_id = None
                if o.sector_override_code:
                    sec_id = await r.get_sector_id_by_code(o.sector_override_code)
                r.add(CompanyYearOverride(
                    company_id=c.id, year=o.year,
                    is_hidden=o.is_hidden, name_override=o.name_override,
                    sector_override_id=sec_id,
                    exclusion_reason=o.exclusion_reason, notes=o.notes,
                ))
            await r.flush()
        # Re-read in fresh transaction
        return await self.list_year_overrides(code)

    # ─── hierarchy tree ───────────────────────────────────────────

    async def hierarchy_tree(self) -> list[CompanyTreeNode]:
        async with self.uow:
            r = self.uow.companies_admin_v2
            rows = await r.list_all_companies_for_tree()
            sids = list({c.sector_id for c in rows if c.sector_id})
            sector_codes = await r.sector_codes_map(sids)

        by_id: dict[UUID, CompanyTreeNode] = {}
        roots: list[CompanyTreeNode] = []
        for c in rows:
            node = CompanyTreeNode(
                id=c.id, code=c.code, name_short=c.name_short, name_ru=c.name_ru,
                sector_code=sector_codes.get(c.sector_id),
                primary_color=c.primary_color,
                badges=[Badge(**b) for b in (c.badges or [])] if c.badges else None,
                status=c.status,
                children=[],
            )
            by_id[c.id] = node
        for c in rows:
            node = by_id[c.id]
            if c.parent_id and c.parent_id in by_id:
                by_id[c.parent_id].children.append(node)
            else:
                roots.append(node)
        return roots

    # ─── sectors ──────────────────────────────────────────────────

    async def list_sectors(self) -> list[SectorAdminRead]:
        async with self.uow:
            rows = await self.uow.companies_admin_v2.list_sectors()
            return [await self._sector_to_read(s) for s in rows]

    async def create_sector(self, body: SectorAdminCreate) -> SectorAdminRead:
        async with self.uow:
            r = self.uow.companies_admin_v2
            existing = await r.get_sector_by_code(body.code)
            if existing:
                raise HTTPException(
                    http_status.HTTP_409_CONFLICT,
                    f"Sector '{body.code}' already exists",
                )
            s = Sector(**body.model_dump())
            r.add(s)
            await r.flush()
            return await self._sector_to_read(s)

    async def update_sector(
        self, code: str, body: SectorAdminUpdate,
    ) -> SectorAdminRead:
        async with self.uow:
            r = self.uow.companies_admin_v2
            s = await r.get_sector_by_code(code)
            if not s:
                raise HTTPException(http_status.HTTP_404_NOT_FOUND, "Sector not found")
            for k, v in body.model_dump(exclude_unset=True).items():
                setattr(s, k, v)
            await r.flush()
            return await self._sector_to_read(s)

    async def delete_sector(self, code: str) -> None:
        async with self.uow:
            r = self.uow.companies_admin_v2
            s = await r.get_sector_by_code(code)
            if not s:
                raise HTTPException(http_status.HTTP_404_NOT_FOUND, "Sector not found")
            cnt = await r.count_companies_in_sector(s.id)
            if cnt:
                raise HTTPException(
                    http_status.HTTP_400_BAD_REQUEST,
                    f"Has {cnt} companies — reassign first",
                )
            await r.delete(s)
            await r.flush()
