"""
backend/app/services/exec_dashboard/blocks_health.py
Executive Dashboard · Row 2.8 «Здоровье портфеля» (SOE Health Check · RAG).

Переиспользует SoeHealthService().build() как ЕДИНЫЙ источник методики —
никакого дубля порогов/бендов: exec-блок показывает ту же оценку, что и
дашборд /soe-health (средний балл, распределение по зонам, топ «тянут вниз» /
«опора»). Standard: NSBU (как налоговый вклад — база для UZ), фолбэк на IFRS,
если за год нет ни одной оценённой компании.
"""
from __future__ import annotations

from typing import Any, Optional, Sequence
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.schemas.executive_dashboard import (
    ExecHealthBlock,
    ExecHealthCompany,
    ExecHealthZone,
)


def _to_company(c: dict[str, Any]) -> ExecHealthCompany:
    z = c.get("zone") or {}
    return ExecHealthCompany(
        code=c["code"],
        name=c["name"] or c["code"],
        overall=round(float(c["overall"]), 2),
        zone_label=z.get("label", ""),
        zone_color=z.get("color", "#94A3B8"),
        delta=c.get("delta"),
    )


def _block_from_payload(payload: dict[str, Any]) -> ExecHealthBlock:
    pf = payload.get("portfolio") or {}
    zone_counts: dict[str, int] = pf.get("zone_counts") or {}
    zones = [
        ExecHealthZone(
            key=z["key"], label=z["label"], color=z["color"],
            count=int(zone_counts.get(z["key"], 0)),
        )
        for z in payload.get("zones", [])
    ]
    # companies уже отсортированы «худшие сверху, н/д в конец»
    scored = [c for c in payload.get("companies", []) if c.get("overall") is not None]
    worst = [_to_company(c) for c in scored[:3]]
    best = [_to_company(c) for c in list(reversed(scored[-3:]))] if scored else []
    avg_zone = pf.get("zone") or {}
    return ExecHealthBlock(
        year=payload["year"],
        standard=payload["standard"],
        has_data=bool(scored),
        avg=pf.get("avg"),
        avg_zone_label=avg_zone.get("label"),
        avg_zone_color=avg_zone.get("color"),
        scored_count=int(pf.get("scored_count", 0)),
        total_companies=int(pf.get("total_companies", 0)),
        zones=zones,
        worst=worst,
        best=best,
    )


async def build_health_block(
    db: AsyncSession,
    year: int,
    *,
    scope_ids: Optional[Sequence[UUID]],
    max_back: int = 4,
) -> Optional[ExecHealthBlock]:
    """Собрать блок здоровья за год (NSBU→IFRS фолбэк, затем year-fallback)."""
    from app.services.soe_health import SoeHealthService

    svc = SoeHealthService()

    async def _for(y: int) -> ExecHealthBlock:
        payload = await svc.build(db, year=y, standard="NSBU", scope_ids=scope_ids)
        blk = _block_from_payload(payload)
        if not blk.has_data:
            # NSBU пуст за год — пробуем IFRS (ранние годы до импорта НСБУ)
            payload = await svc.build(db, year=y, standard="IFRS", scope_ids=scope_ids)
            blk = _block_from_payload(payload)
        return blk

    out = await _for(year)
    if out.has_data:
        return out
    # year-fallback: последний год с оценками (до max_back назад)
    for back in range(1, max_back + 1):
        cand = await _for(year - back)
        if cand.has_data:
            cand.requested_year = year
            return cand
    return out  # ничего — отдаём пустой за исходный год
