"""Data access for FinModel v2."""
from __future__ import annotations

from collections.abc import Sequence
from typing import Optional
from uuid import UUID

from sqlalchemy import and_, delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.company import Company
from app.models.finmodel import (
    FinModelAuditLog,
    FinModelCellComment,
    FinModelCellValue,
    FinModelMacroCompany,
    FinModelMacroGlobal,
    FinModelScenario,
    FinModelTemplateRow,
    FinModelYearLock,
)


class FinModelRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    # ─── template + company ───────────────────────────────────────

    async def load_template(self) -> list[FinModelTemplateRow]:
        q = await self.session.execute(
            select(FinModelTemplateRow).order_by(
                FinModelTemplateRow.section,
                FinModelTemplateRow.order_idx,
            )
        )
        return list(q.scalars().all())

    async def get_template_row(self, row_code: str) -> Optional[FinModelTemplateRow]:
        res = await self.session.execute(
            select(FinModelTemplateRow).where(FinModelTemplateRow.code == row_code)
        )
        return res.scalar_one_or_none()

    async def get_company(self, company_id: UUID) -> Optional[Company]:
        return await self.session.get(Company, company_id)

    # ─── cells ────────────────────────────────────────────────────

    async def load_year_cells(
        self, company_id: UUID, year: int,
    ) -> list[FinModelCellValue]:
        q = await self.session.execute(
            select(FinModelCellValue).where(and_(
                FinModelCellValue.company_id == company_id,
                FinModelCellValue.year == year,
            ))
        )
        return list(q.scalars().all())

    async def list_all_cells_for_company(
        self, company_id: UUID,
    ) -> list[FinModelCellValue]:
        q = await self.session.execute(
            select(FinModelCellValue).where(
                FinModelCellValue.company_id == company_id,
            )
        )
        return list(q.scalars().all())

    async def get_cell(
        self, company_id: UUID, year: int, row_code: str,
    ) -> Optional[FinModelCellValue]:
        res = await self.session.execute(
            select(FinModelCellValue).where(and_(
                FinModelCellValue.company_id == company_id,
                FinModelCellValue.year == year,
                FinModelCellValue.row_code == row_code,
            ))
        )
        return res.scalar_one_or_none()

    async def get_cells_by_codes(
        self, company_id: UUID, year: int, codes: Sequence[str],
    ) -> list[FinModelCellValue]:
        if not codes:
            return []
        q = await self.session.execute(
            select(FinModelCellValue).where(and_(
                FinModelCellValue.company_id == company_id,
                FinModelCellValue.year == year,
                FinModelCellValue.row_code.in_(list(codes)),
            ))
        )
        return list(q.scalars().all())

    async def delete_cells_for_year(self, company_id: UUID, year: int) -> None:
        await self.session.execute(
            delete(FinModelCellValue).where(and_(
                FinModelCellValue.company_id == company_id,
                FinModelCellValue.year == year,
            ))
        )

    async def delete_cells_for_years(
        self, company_id: UUID, years: Sequence[int],
    ) -> None:
        if not years:
            return
        await self.session.execute(
            delete(FinModelCellValue).where(and_(
                FinModelCellValue.company_id == company_id,
                FinModelCellValue.year.in_(list(years)),
            ))
        )

    # ─── year_lock ────────────────────────────────────────────────

    async def get_year_lock(
        self, company_id: UUID, year: int,
    ) -> Optional[FinModelYearLock]:
        res = await self.session.execute(
            select(FinModelYearLock).where(and_(
                FinModelYearLock.company_id == company_id,
                FinModelYearLock.year == year,
            ))
        )
        return res.scalar_one_or_none()

    async def list_year_locks(self, company_id: UUID) -> list[FinModelYearLock]:
        q = await self.session.execute(
            select(FinModelYearLock).where(
                FinModelYearLock.company_id == company_id,
            )
        )
        return list(q.scalars().all())

    async def list_year_locks_for_years(
        self, company_id: UUID, years: Sequence[int],
    ):
        if not years:
            return []
        q = await self.session.execute(
            select(FinModelYearLock).where(and_(
                FinModelYearLock.company_id == company_id,
                FinModelYearLock.year.in_(list(years)),
            ))
        )
        return list(q.scalars().all())

    async def distinct_cell_years(self, company_id: UUID) -> set[int]:
        q = await self.session.execute(
            select(FinModelCellValue.year)
            .where(FinModelCellValue.company_id == company_id)
            .distinct()
        )
        return {row[0] for row in q.all()}

    async def delete_year_lock(self, company_id: UUID, year: int) -> None:
        await self.session.execute(
            delete(FinModelYearLock).where(and_(
                FinModelYearLock.company_id == company_id,
                FinModelYearLock.year == year,
            ))
        )

    # ─── macro ────────────────────────────────────────────────────

    async def get_macro_global(self, year: int) -> Optional[FinModelMacroGlobal]:
        res = await self.session.execute(
            select(FinModelMacroGlobal).where(FinModelMacroGlobal.year == year)
        )
        return res.scalar_one_or_none()

    async def list_macro_global(self) -> list[FinModelMacroGlobal]:
        q = await self.session.execute(
            select(FinModelMacroGlobal).order_by(FinModelMacroGlobal.year)
        )
        return list(q.scalars().all())

    async def get_macro_company(
        self, company_id: UUID, year: int,
    ) -> Optional[FinModelMacroCompany]:
        res = await self.session.execute(
            select(FinModelMacroCompany).where(and_(
                FinModelMacroCompany.company_id == company_id,
                FinModelMacroCompany.year == year,
            ))
        )
        return res.scalar_one_or_none()

    async def list_macro_company_for_company(
        self, company_id: UUID,
    ) -> list[FinModelMacroCompany]:
        q = await self.session.execute(
            select(FinModelMacroCompany).where(
                FinModelMacroCompany.company_id == company_id,
            )
        )
        return list(q.scalars().all())

    async def delete_macro_company_for_year(
        self, company_id: UUID, year: int,
    ) -> None:
        await self.session.execute(
            delete(FinModelMacroCompany).where(and_(
                FinModelMacroCompany.company_id == company_id,
                FinModelMacroCompany.year == year,
            ))
        )

    async def delete_macro_company_for_years(
        self, company_id: UUID, years: Sequence[int],
    ) -> None:
        if not years:
            return
        await self.session.execute(
            delete(FinModelMacroCompany).where(and_(
                FinModelMacroCompany.company_id == company_id,
                FinModelMacroCompany.year.in_(list(years)),
            ))
        )

    # ─── scenarios ────────────────────────────────────────────────

    async def list_scenarios(self, company_id: UUID) -> list[FinModelScenario]:
        q = await self.session.execute(
            select(FinModelScenario)
            .where(FinModelScenario.company_id == company_id)
            .order_by(FinModelScenario.created_at.desc())
        )
        return list(q.scalars().all())

    async def get_scenario(
        self, company_id: UUID, scenario_id: UUID,
    ) -> Optional[FinModelScenario]:
        res = await self.session.execute(
            select(FinModelScenario).where(and_(
                FinModelScenario.id == scenario_id,
                FinModelScenario.company_id == company_id,
            ))
        )
        return res.scalar_one_or_none()

    async def deactivate_all_scenarios(self, company_id: UUID) -> None:
        await self.session.execute(
            FinModelScenario.__table__.update()
            .where(FinModelScenario.company_id == company_id)
            .values(is_active=False)
        )

    async def delete_scenario(
        self, company_id: UUID, scenario_id: UUID,
    ) -> None:
        await self.session.execute(
            delete(FinModelScenario).where(and_(
                FinModelScenario.id == scenario_id,
                FinModelScenario.company_id == company_id,
            ))
        )

    # ─── comments ─────────────────────────────────────────────────

    async def list_comments(
        self, company_id: UUID, year: Optional[int],
    ) -> list[FinModelCellComment]:
        q = select(FinModelCellComment).where(
            FinModelCellComment.company_id == company_id,
        )
        if year is not None:
            q = q.where(FinModelCellComment.year == year)
        q = q.order_by(FinModelCellComment.created_at.desc())
        return list((await self.session.execute(q)).scalars().all())

    async def delete_comments_for_year(
        self, company_id: UUID, year: int,
    ) -> None:
        await self.session.execute(
            delete(FinModelCellComment).where(and_(
                FinModelCellComment.company_id == company_id,
                FinModelCellComment.year == year,
            ))
        )

    async def delete_comment(
        self, comment_id: UUID, company_id: UUID,
    ) -> None:
        await self.session.execute(
            delete(FinModelCellComment).where(and_(
                FinModelCellComment.id == comment_id,
                FinModelCellComment.company_id == company_id,
            ))
        )

    # ─── audit ────────────────────────────────────────────────────

    async def list_audit(
        self, *,
        company_id: UUID, year: int, row_code: Optional[str], limit: int,
    ) -> tuple[list[FinModelAuditLog], int]:
        q = select(FinModelAuditLog).where(and_(
            FinModelAuditLog.company_id == company_id,
            FinModelAuditLog.year == year,
        ))
        if row_code:
            q = q.where(FinModelAuditLog.row_code == row_code)
        total = (await self.session.execute(
            select(func.count()).select_from(q.subquery())
        )).scalar_one() or 0
        items = list((await self.session.execute(
            q.order_by(FinModelAuditLog.ts.desc()).limit(limit)
        )).scalars().all())
        return items, total

    # ─── mutations ────────────────────────────────────────────────

    def add(self, obj) -> None:
        self.session.add(obj)

    async def flush(self) -> None:
        await self.session.flush()

    async def refresh(self, obj) -> None:
        await self.session.refresh(obj)
