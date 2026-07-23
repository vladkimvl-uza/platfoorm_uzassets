"""Авто-генератор возможностей ценности из детекторов платформы.

Сканирует существующие детекторы неэффективности и предлагает кандидатов в
реестр возможностей ценности. Каждый кандидат несёт стабильный `fingerprint` →
повторный запуск не создаёт дубликатов (уже существующие пропускаются).

Источники (только с ЧЕСТНОЙ денежной суммой — в каноне «не выдумывай»):
  • unit_cost — перерасход энергозатрат к норме (overrun_cost, сум → млрд сум);
  • business_plan — недобор прибыли/выручки vs плана + перерасход доли
    себестоимости (bp_compute, уже в млрд сум).
Forensic (закупки) намеренно НЕ используется: его методика помечена аудитом как
ненадёжная («флаг≠факт»), денежные суммы оттуда были бы недостоверны.
"""
from __future__ import annotations

import logging
from decimal import Decimal
from typing import Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.bp_kpi import BP_METRIC_LABELS, BpRecord
from app.models.company import Company
from app.models.value import ValueOpportunity
from app.services.bp_kpi_helpers import bp_compute
from app.services.unit_cost.service import UnitCostService
from app.uow.ports import UnitOfWorkABC

log = logging.getLogger(__name__)

_UC_MIN = 0.05   # млрд сум — минимум перерасхода, чтобы не плодить шум
_BP_MIN = 0.10   # млрд сум — минимум разрыва для БП-возможностей


def _fnum(x: object) -> Optional[float]:
    if x is None:
        return None
    try:
        return float(x)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


async def generate_value_opportunities(
    uow: UnitOfWorkABC, *,
    year: int,
    quarter: str = "annual",
    user_id: UUID,
    user_name: str,
    scope_company_ids: Optional[list[UUID]] = None,
) -> dict:
    async with uow:
        session: AsyncSession = uow._session  # type: ignore[attr-defined]
        scope = set(scope_company_ids) if scope_company_ids is not None else None

        # Ростер компаний в scope: id → (code, name), code → id.
        rows = (await session.execute(
            select(Company.id, Company.code, Company.name_short, Company.name_ru)
            .where(Company.is_active.is_(True))
        )).all()
        id_meta: dict[UUID, tuple[Optional[str], str]] = {}
        code_to_id: dict[str, UUID] = {}
        for cid, code, ns, nr in rows:
            if scope is not None and cid not in scope:
                continue
            nm = ns or nr or code or "—"
            id_meta[cid] = (code, nm)
            if code:
                code_to_id[code] = cid

        candidates: list[dict] = []

        # ── 1. Unit cost — перерасход к норме ──
        try:
            ov = await UnitCostService().overview(
                session, year=year, quarter=quarter,
                scope_ids=list(scope) if scope is not None else None,
            )
            for co in ov.get("companies", []):
                code = co.get("code")
                ovc = _fnum(co.get("overrun_cost"))
                if code not in code_to_id or ovc is None:
                    continue
                amt = ovc / 1e9  # сум → млрд сум; >0 = перерасход (возможность экономии)
                if amt <= _UC_MIN:
                    continue
                cid = code_to_id[code]
                nm = id_meta[cid][1]
                candidates.append({
                    "company_id": cid, "year": year, "source": "unit_cost", "kind": "economy",
                    "title": f"Снижение перерасхода энергозатрат к норме — {nm}",
                    "description": (
                        "Перерасход топлива/энергии против нормы расхода (модуль «Удельная "
                        "себестоимость»). Потенциал — приведение фактического расхода к норме."
                    ),
                    "value_amount": Decimal(str(round(amt, 3))),
                    "fingerprint": f"unit_cost:{code}:{year}:{quarter}",
                })
        except Exception:
            log.debug("unit_cost detector failed for year %s — skipping", year, exc_info=True)

        # ── 2. Business plan — недобор + перерасход доли себестоимости ──
        bp_cids = {
            cid for (cid,) in (await session.execute(
                select(BpRecord.company_id).where(BpRecord.year == year).distinct()
            )).all()
            if cid in id_meta
        }
        for cid in bp_cids:
            code, nm = id_meta[cid]
            try:
                comp = await bp_compute(session, cid, year, "annual")
            except Exception:
                log.debug("bp_compute failed for company %s year %s — skipping", cid, year, exc_info=True)
                continue
            fp_co = code or str(cid)

            # 2a. Недобор нижней строки: profit, иначе revenue (не задваиваем).
            for k in ("profit", "revenue"):
                c = comp.get(k) or {}
                plan, fact = _fnum(c.get("plan")), _fnum(c.get("fact"))
                if plan is not None and fact is not None and plan > 0:
                    ratio = fact / plan
                    if ratio < 0.85:
                        gap = plan - fact
                        if gap >= _BP_MIN:
                            candidates.append({
                                "company_id": cid, "year": year, "source": "business_plan",
                                "kind": "uplift",
                                "title": f"Закрыть отставание: {BP_METRIC_LABELS.get(k, k)} — {nm}",
                                "description": (
                                    f"Факт {round(fact, 1)} vs план {round(plan, 1)} млрд сум "
                                    f"({round(ratio * 100)}%). Потенциал восстановления до плана."
                                ),
                                "value_amount": Decimal(str(round(gap, 3))),
                                "fingerprint": f"business_plan:{fp_co}:{year}:{k}",
                            })
                        break  # profit важнее revenue — берём первый доступный

            # 2b. Перерасход доли себестоимости к плановой.
            cogs, rev = comp.get("cogs") or {}, comp.get("revenue") or {}
            cf, rf = _fnum(cogs.get("fact")), _fnum(rev.get("fact"))
            cp, rp = _fnum(cogs.get("plan")), _fnum(rev.get("plan"))
            if None not in (cf, rf, cp, rp) and rf > 0 and rp > 0:  # type: ignore[operator]
                cr, crp = abs(cf) / rf, abs(cp) / rp  # type: ignore[operator]
                if cr > crp * 1.10:
                    extra = (cr - crp) * rf  # избыточная себестоимость сверх плановой доли
                    if extra >= _BP_MIN:
                        candidates.append({
                            "company_id": cid, "year": year, "source": "business_plan",
                            "kind": "economy",
                            "title": f"Снизить долю себестоимости до плана — {nm}",
                            "description": (
                                f"Доля себестоимости {round(cr * 100)}% vs план {round(crp * 100)}%. "
                                "Потенциал экономии при возврате к плановой доле."
                            ),
                            "value_amount": Decimal(str(round(extra, 3))),
                            "fingerprint": f"business_plan:{fp_co}:{year}:cost_ratio",
                        })

        # ── Дедуп по fingerprint + вставка ──
        fps = [c["fingerprint"] for c in candidates]
        existing = await uow.value.find_fingerprints(fps)
        fresh = [c for c in candidates if c["fingerprint"] not in existing]
        by_source: dict[str, int] = {}
        for c in fresh:
            uow.value.add(ValueOpportunity(
                status="identified", created_by=user_id, created_by_name=user_name, **c,
            ))
            by_source[c["source"]] = by_source.get(c["source"], 0) + 1
        await uow.value.flush()
        return {
            "created": len(fresh),
            "skipped_existing": len(candidates) - len(fresh),
            "scanned": len(candidates),
            "by_source": by_source,
            "year": year,
        }
