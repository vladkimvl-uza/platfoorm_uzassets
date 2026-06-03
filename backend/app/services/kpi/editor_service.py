"""KPI editor-side service — мутации (replace_year, delete_year, upsert_comment,
load_template). Каждая операция атомарна: либо вся транзакция проходит, либо
rollback (UnitOfWork делает это автоматом при exception).
"""
from __future__ import annotations

import json
import logging
from decimal import Decimal
from pathlib import Path
from typing import Optional
from uuid import UUID

from fastapi import HTTPException
from fastapi import status as http_status

from app.models.bp_kpi import KpiIndicator, KpiManager
from app.schemas.bp_kpi import (
    KpiCommentRead,
    KpiCommentUpsert,
    KpiCompanyYearUpsert,
)
from app.uow.ports import UnitOfWorkABC

log = logging.getLogger(__name__)


class KpiEditorService:
    def __init__(self, uow: UnitOfWorkABC) -> None:
        self.uow = uow

    # ─── Replace year (the heavy editor save) ─────────────────────

    async def replace_year(
        self,
        company_id: UUID,
        year: int,
        payload: KpiCompanyYearUpsert,
    ) -> dict:
        """Replace ALL managers + indicators for (company, year) scope.

        Атомарно: delete existing → insert all новые. При любом сбое внутри
        блока — UoW.__aexit__ делает rollback. Side-effects (broadcast) — после
        successful commit.
        """
        if payload.company_id != company_id or payload.year != year:
            raise HTTPException(
                http_status.HTTP_400_BAD_REQUEST,
                "company_id/year mismatch",
            )

        async with self.uow:
            await self.uow.kpi.delete_year(company_id, year)

            inserted_mgr = 0
            inserted_ind = 0
            for mi, m in enumerate(payload.managers):
                mgr = KpiManager(
                    company_id=company_id, year=year,
                    sort_order=m.sort_order if m.sort_order is not None else mi,
                    title=m.title, short_title=m.short_title, role=m.role,
                )
                await self.uow.kpi.add_manager(mgr)  # flush — populates id

                for ii, ind in enumerate(m.indicators):
                    await self.uow.kpi.add_indicator(KpiIndicator(
                        manager_id=mgr.id,
                        sort_order=ind.sort_order if ind.sort_order is not None else ii,
                        name=ind.name, unit=ind.unit, weight=ind.weight,
                        plan_year=ind.plan_year, fact_year=ind.fact_year,
                        q1_weight=ind.q1_weight, q2_weight=ind.q2_weight,
                        q3_weight=ind.q3_weight, q4_weight=ind.q4_weight,
                        q1_plan=ind.q1_plan, q1_fact=ind.q1_fact,
                        q2_plan=ind.q2_plan, q2_fact=ind.q2_fact,
                        q3_plan=ind.q3_plan, q3_fact=ind.q3_fact,
                        q4_plan=ind.q4_plan, q4_fact=ind.q4_fact,
                        notes=ind.notes,
                    ))
                    inserted_ind += 1
                inserted_mgr += 1
            # implicit commit on __aexit__ без exception

        return {"managers": inserted_mgr, "indicators": inserted_ind}

    # ─── Bulk-add (ИИ-импорт) — аддитивно, без стирания дерева ─────

    async def bulk_add_indicators(
        self,
        company_id: UUID,
        year: int,
        manager_title: str,
        indicators: list[dict],
    ) -> dict:
        """Добавить индикаторы в (company, year) НЕ стирая существующие.

        Индикаторы кладутся под менеджера `manager_title` — существующего
        (если найден по названию) либо нового. Используется ИИ-импортом
        (/builder/bulk-kpi). Каждый indicators[i]: {name, unit?, weight?, plan?, fact?}.
        """
        def _dec(v: object) -> Optional[Decimal]:
            if v is None or str(v).strip() == "":
                return None
            try:
                return Decimal(str(v).replace(" ", "").replace(",", "."))
            except (ValueError, ArithmeticError):
                return None

        async with self.uow:
            existing = await self.uow.kpi.get_managers_with_indicators(company_id, year)
            title_norm = manager_title.strip().lower()
            mgr = next((m for m in existing if (m.title or "").strip().lower() == title_norm), None)
            if mgr is None:
                mgr = KpiManager(
                    company_id=company_id, year=year,
                    sort_order=len(existing), title=manager_title.strip() or "Импорт KPI",
                )
                await self.uow.kpi.add_manager(mgr)   # flush → id
                base_sort = 0
            else:
                base_sort = len(mgr.indicators or [])

            added = 0
            for i, ind in enumerate(indicators):
                name = str(ind.get("name") or "").strip()
                if not name:
                    continue
                await self.uow.kpi.add_indicator(KpiIndicator(
                    manager_id=mgr.id,
                    sort_order=base_sort + i,
                    name=name[:512],
                    unit=(str(ind.get("unit")).strip() or None) if ind.get("unit") else None,
                    weight=_dec(ind.get("weight")) or Decimal("0"),
                    plan_year=_dec(ind.get("plan")),
                    fact_year=_dec(ind.get("fact")),
                ))
                added += 1

            return {"manager_id": str(mgr.id), "indicators_added": added}

    # ─── Delete year ──────────────────────────────────────────────

    async def delete_year(self, company_id: UUID, year: int) -> None:
        async with self.uow:
            await self.uow.kpi.delete_year(company_id, year)
            await self.uow.kpi.delete_comments_for_year(company_id, year)

    # ─── Comments ─────────────────────────────────────────────────

    async def upsert_comment(
        self, payload: KpiCommentUpsert, author_id: UUID,
    ) -> KpiCommentRead:
        async with self.uow:
            row = await self.uow.kpi.upsert_comment(
                company_id=payload.company_id,
                year=payload.year,
                period=payload.period,
                body=payload.body,
                author_id=author_id,
            )
            # KpiCommentRead — Pydantic v2 with from_attributes=True
            return KpiCommentRead.model_validate(row)

    # ─── Template loading ─────────────────────────────────────────

    async def load_template(self, company_code: str, year: int) -> dict:
        """Bootstrap per-company KPI template из `app/scripts/kpi_templates/{code}.json`."""
        async with self.uow:
            co = await self.uow.kpi.get_company_by_code(company_code)
            if co is None:
                raise HTTPException(
                    http_status.HTTP_404_NOT_FOUND,
                    f"Company '{company_code}' not found",
                )

            existing = await self.uow.kpi.count_managers(co.id, year)
            if existing > 0:
                raise HTTPException(
                    http_status.HTTP_409_CONFLICT,
                    detail=f"{co.name_ru} already has {existing} managers for {year}. Delete year first.",
                )

            path = Path(__file__).resolve().parents[2] / "scripts" / "kpi_templates" / f"{company_code.lower()}.json"
            if not path.exists():
                raise HTTPException(
                    http_status.HTTP_404_NOT_FOUND,
                    detail=f"No template registered for '{company_code}' (expected: {path.name})",
                )
            with open(path, encoding="utf-8") as f:
                template = json.load(f)

            inserted_mgr = 0
            inserted_ind = 0
            for mi, m in enumerate(template["managers"]):
                mgr = KpiManager(
                    company_id=co.id, year=year, sort_order=mi,
                    title=m.get("title", ""),
                    short_title=m.get("shortTitle"),
                    role=m.get("role"),
                )
                await self.uow.kpi.add_manager(mgr)
                for ii, ind in enumerate(m.get("indicators", [])):
                    q = ind.get("quarters", {}) or {}
                    def _dec(v: object) -> Optional[Decimal]:
                        return Decimal(str(v)) if v is not None else None
                    await self.uow.kpi.add_indicator(KpiIndicator(
                        manager_id=mgr.id, sort_order=ii,
                        name=ind.get("name", ""), unit=ind.get("unit"),
                        weight=Decimal(str(ind.get("weight", 0))),
                        plan_year=_dec(ind.get("planYear")),
                        fact_year=_dec(ind.get("factYear")),
                        q1_weight=Decimal(str((q.get("q1") or {}).get("weight", 0))),
                        q2_weight=Decimal(str((q.get("q2") or {}).get("weight", 0))),
                        q3_weight=Decimal(str((q.get("q3") or {}).get("weight", 0))),
                        q4_weight=Decimal(str((q.get("q4") or {}).get("weight", 0))),
                        q1_plan=_dec((q.get("q1") or {}).get("plan")),
                        q1_fact=_dec((q.get("q1") or {}).get("fact")),
                        q2_plan=_dec((q.get("q2") or {}).get("plan")),
                        q2_fact=_dec((q.get("q2") or {}).get("fact")),
                        q3_plan=_dec((q.get("q3") or {}).get("plan")),
                        q3_fact=_dec((q.get("q3") or {}).get("fact")),
                        q4_plan=_dec((q.get("q4") or {}).get("plan")),
                        q4_fact=_dec((q.get("q4") or {}).get("fact")),
                    ))
                    inserted_ind += 1
                inserted_mgr += 1

            return {
                "company_id": str(co.id),
                "company_name": co.name_ru,
                "company_code": co.code,
                "year": year,
                "managers_added": inserted_mgr,
                "indicators_added": inserted_ind,
            }

    async def list_templates(self) -> dict:
        """List available per-company templates (file-based)."""
        tdir = Path(__file__).resolve().parents[2] / "scripts" / "kpi_templates"
        if not tdir.is_dir():
            return {"templates": []}
        out: list[dict] = []
        async with self.uow:
            for f in sorted(tdir.glob("*.json")):
                code = f.stem
                co = await self.uow.kpi.get_company_by_code(code)
                out.append({
                    "company_code": code,
                    "company_id": str(co.id) if co else None,
                    "company_name": co.name_ru if co else None,
                })
        return {"templates": out}
