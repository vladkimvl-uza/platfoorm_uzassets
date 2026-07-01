"""Data access for Production indicators (производственные показатели).

Storage — JSONB snapshot in `system_config` (key `raw_snapshot.productionData`),
mirroring `forensic_repository.py`. The snapshot is a list of per-(company,
year, period) records, each holding a tree of product `lines` with raw
natura/money for base(prior fact)/plan/expected. Derived growth/execution %
are NEVER stored — computed honestly in the service (audit lesson «флаг≠факт»).
"""
from __future__ import annotations

import json
from collections.abc import Sequence
from uuid import UUID

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.company import Company, Sector

_SNAPSHOT_KEY = "raw_snapshot.productionData"


class ProductionRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def load_snapshot(self) -> list[dict]:
        res = await self.session.execute(
            text("SELECT value FROM system_config WHERE key = :k LIMIT 1"),
            {"k": _SNAPSHOT_KEY},
        )
        row = res.first()
        if not row or not row[0]:
            return []
        snap = row[0]
        if isinstance(snap, str):
            try:
                snap = json.loads(snap)
            except json.JSONDecodeError:
                return []
        return snap if isinstance(snap, list) else []

    async def save_snapshot(self, snap: list[dict]) -> None:
        payload = json.dumps(snap, ensure_ascii=False)
        await self.session.execute(text("""
            INSERT INTO system_config (id, key, value, description, is_secret,
                                       created_at, updated_at)
            VALUES (gen_random_uuid(), :k, CAST(:v AS jsonb), :d, FALSE,
                    NOW(), NOW())
            ON CONFLICT (key) DO UPDATE
            SET value = EXCLUDED.value, updated_at = NOW()
        """), {
            "k": _SNAPSHOT_KEY,
            "v": payload,
            "d": "Production plan/fact data — mutable via /production endpoints",
        })

    async def companies_meta(self) -> list[dict]:
        """Каноничные метаданные компаний (имя из name_short||name_ru + сектор).
        Используется и для отображения (имена как в /admin/companies), и для
        сопоставления листов Excel → code при импорте."""
        res = await self.session.execute(
            select(
                Company.code, Company.name_short, Company.name_ru,
                Company.name_uz, Company.name_en,
                Sector.code, Sector.name_ru,
            ).join(Sector, Company.sector_id == Sector.id, isouter=True)
            .where(Company.is_active.is_(True))
        )
        out: list[dict] = []
        for code, ns, nr, nu, ne, scode, sname in res.all():
            if not code:
                continue
            out.append({
                "code": code,
                "name_short": ns, "name_ru": nr, "name_uz": nu, "name_en": ne,
                "sector_code": scode, "sector_name": sname,
            })
        return out

    async def codes_for_company_ids(self, company_ids: Sequence[UUID]) -> set[str]:
        if not company_ids:
            return set()
        res = await self.session.execute(
            select(Company.code).where(Company.id.in_(list(company_ids)))
        )
        return {c.lower() for (c,) in res.all() if c}
