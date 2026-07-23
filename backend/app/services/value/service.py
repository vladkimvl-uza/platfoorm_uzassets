"""Value Opportunities service — реестр возможностей ценности.

Сводит выявленную экономию/рост/риск по компаниям в единый реестр с суммами,
ответственными и трекингом реализации (цикл выявлено → в работе → реализовано).
"""
from __future__ import annotations

from datetime import UTC, datetime
from typing import Optional
from uuid import UUID

from app.models.company import Company
from app.models.value import ValueOpportunity
from app.schemas.value import (
    ValueByCompany,
    ValueByStatus,
    ValueOpportunityCreate,
    ValueOpportunityRead,
    ValueOpportunityUpdate,
    ValueSummary,
)
from app.services.bp_kpi_helpers import sector_color
from app.uow.ports import UnitOfWorkABC

_SOURCES = {"unit_cost", "procurement", "business_plan", "kpi", "manual"}
_KINDS = {"economy", "uplift", "risk"}
_STATUSES = {"identified", "in_progress", "realized", "dismissed"}


def _f(x: object) -> float:
    try:
        return float(x)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return 0.0


def _to_read(opp: ValueOpportunity, co: Optional[Company]) -> ValueOpportunityRead:
    return ValueOpportunityRead(
        id=opp.id,
        company_id=opp.company_id,
        company_name=(co.name_short or co.name_ru or co.code) if co else None,
        sector_color=sector_color(co) if co else None,
        year=opp.year,
        source=opp.source,
        kind=opp.kind,
        status=opp.status,
        title=opp.title,
        description=opp.description,
        value_amount=opp.value_amount,
        realized_amount=opp.realized_amount,
        owner=opp.owner,
        target_date=opp.target_date,
        realized_at=opp.realized_at,
        fingerprint=opp.fingerprint,
        created_by_name=opp.created_by_name,
        created_at=opp.created_at,
        updated_at=opp.updated_at,
    )


class ValueService:
    def __init__(self, uow: UnitOfWorkABC) -> None:
        self.uow = uow

    async def list(
        self, *, status=None, source=None, company_id=None, scope_company_ids=None,
    ) -> list[ValueOpportunityRead]:
        async with self.uow:
            rows = await self.uow.value.list(
                status=status, source=source, company_id=company_id,
                scope_company_ids=scope_company_ids,
            )
            return [_to_read(opp, co) for opp, co in rows]

    async def summary(self, *, scope_company_ids=None) -> ValueSummary:
        async with self.uow:
            rows = await self.uow.value.list(scope_company_ids=scope_company_ids)
        by_status: dict[str, ValueByStatus] = {}
        by_source: dict[str, ValueByStatus] = {}
        by_company: dict[str, ValueByCompany] = {}
        identified = in_progress = realized = 0.0
        for opp, co in rows:
            amt = _f(opp.value_amount)
            rlz = _f(opp.realized_amount)
            st = opp.status
            if st == "realized":
                realized += (rlz or amt)
            elif st == "in_progress":
                in_progress += amt
                identified += amt
            elif st == "identified":
                identified += amt
            # by status
            s = by_status.setdefault(st, ValueByStatus(status=st))
            s.count += 1
            s.amount += amt
            s.realized += rlz
            # by source
            src = by_source.setdefault(opp.source, ValueByStatus(status=opp.source))
            src.count += 1
            src.amount += amt
            src.realized += rlz
            # by company (пропускаем портфельные без company)
            if co is not None:
                key = str(co.id)
                c = by_company.get(key)
                if c is None:
                    c = ValueByCompany(
                        company_id=co.id,
                        company_name=(co.name_short or co.name_ru or co.code or "—"),
                        sector_color=sector_color(co),
                    )
                    by_company[key] = c
                c.count += 1
                c.amount += amt
                c.realized += rlz
        return ValueSummary(
            total_count=len(rows),
            identified_amount=round(identified, 3),
            in_progress_amount=round(in_progress, 3),
            realized_amount=round(realized, 3),
            by_status=sorted(by_status.values(), key=lambda x: -x.amount),
            by_source=sorted(by_source.values(), key=lambda x: -x.amount),
            by_company=sorted(by_company.values(), key=lambda x: -(x.amount + x.realized))[:20],
        )

    async def create(
        self, payload: ValueOpportunityCreate, *, user_id: UUID, user_name: str,
    ) -> ValueOpportunityRead:
        async with self.uow:
            opp = ValueOpportunity(
                company_id=payload.company_id,
                year=payload.year,
                source=payload.source if payload.source in _SOURCES else "manual",
                kind=payload.kind if payload.kind in _KINDS else "economy",
                status=payload.status if payload.status in _STATUSES else "identified",
                title=payload.title.strip()[:300] or "—",
                description=payload.description,
                value_amount=payload.value_amount,
                realized_amount=payload.realized_amount,
                owner=payload.owner,
                target_date=payload.target_date,
                created_by=user_id,
                created_by_name=user_name,
            )
            if opp.status == "realized" and opp.realized_at is None:
                opp.realized_at = datetime.now(UTC)
                if opp.realized_amount is None:
                    opp.realized_amount = opp.value_amount
            self.uow.value.add(opp)
            await self.uow.value.flush()
            co = await self.uow.value.company_for(opp.company_id) if opp.company_id else None
            return _to_read(opp, co)

    async def update(
        self, opp_id: UUID, patch: ValueOpportunityUpdate, *, scope_company_ids=None,
    ) -> Optional[ValueOpportunityRead]:
        async with self.uow:
            opp = await self.uow.value.get(opp_id)
            if opp is None:
                return None
            if scope_company_ids is not None and opp.company_id is not None \
                    and opp.company_id not in set(scope_company_ids):
                return None  # вне scope
            data = patch.model_dump(exclude_unset=True)
            for field in ("company_id", "year", "title", "description", "value_amount",
                          "realized_amount", "owner", "target_date"):
                if field in data:
                    setattr(opp, field, data[field])
            if "source" in data and data["source"] in _SOURCES:
                opp.source = data["source"]
            if "kind" in data and data["kind"] in _KINDS:
                opp.kind = data["kind"]
            if "status" in data and data["status"] in _STATUSES:
                prev = opp.status
                opp.status = data["status"]
                if opp.status == "realized" and prev != "realized":
                    opp.realized_at = datetime.now(UTC)
                    if opp.realized_amount is None:
                        opp.realized_amount = opp.value_amount
                elif opp.status != "realized":
                    opp.realized_at = None
            if opp.title is not None:
                opp.title = str(opp.title).strip()[:300] or "—"
            await self.uow.value.flush()
            co = await self.uow.value.company_for(opp.company_id) if opp.company_id else None
            return _to_read(opp, co)

    async def delete(self, opp_id: UUID, *, scope_company_ids=None) -> bool:
        async with self.uow:
            opp = await self.uow.value.get(opp_id)
            if opp is None:
                return False
            if scope_company_ids is not None and opp.company_id is not None \
                    and opp.company_id not in set(scope_company_ids):
                return False
            await self.uow.value.delete(opp_id)
            return True
