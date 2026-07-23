"""Data access for Forensic (procurement plan/fact JSONB snapshot)."""
from __future__ import annotations

from collections.abc import Sequence
from uuid import UUID

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.company import Company
from app.repositories.snapshot_store import SnapshotStore

_SNAPSHOT_KEY = "raw_snapshot.procurementData"


class ForensicRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def load_snapshot(self) -> list[dict]:
        snap = await SnapshotStore(self.session).load(_SNAPSHOT_KEY)
        return snap if isinstance(snap, list) else []

    async def save_snapshot(self, snap: list[dict]) -> None:
        await SnapshotStore(self.session).save(
            _SNAPSHOT_KEY, snap,
            "Procurement plan/fact data (PROCUREMENT_DATA) mutable via /forensic endpoints",
        )

    async def names_by_code(self) -> dict[str, str]:
        """Каноничные имена компаний из таблицы Company, ключ — code в нижнем
        регистре. Нужен, чтобы forensic-snapshot (где имена запечены легаси-сидом)
        показывал актуальные названия из /admin/companies (name_short || name_ru)."""
        res = await self.session.execute(
            select(Company.code, Company.name_short, Company.name_ru)
        )
        out: dict[str, str] = {}
        for code, name_short, name_ru in res.all():
            if not code:
                continue
            out[code.strip().lower()] = (name_short or name_ru or code)
        return out

    async def codes_for_company_ids(self, company_ids: Sequence[UUID]) -> set[str]:
        if not company_ids:
            return set()
        res = await self.session.execute(
            select(Company.code).where(Company.id.in_(company_ids))
        )
        return {c.lower() for (c,) in res.all() if c}

    async def active_companies(self) -> list[dict]:
        """Активные компании из таблицы Company (код, каноничное имя, сектор в
        разрезе 5 forensic-корзин). Нужны, чтобы forensic-ростер строился
        динамически (новая компания видна пустой строкой) и чтобы правки могли
        создавать строку снапшота для любой активной компании."""
        res = await self.session.execute(text(
            "SELECT c.code, COALESCE(c.name_short, c.name_ru) AS name, "
            "       s.code AS sector_code, s.name_ru AS sector_name "
            "FROM companies c LEFT JOIN sectors s ON s.id = c.sector_id "
            "WHERE c.is_active = true AND c.code <> 'uzassets'"
        ))
        out: list[dict] = []
        for code, name, sector_code, sector_name in res.all():
            if not code:
                continue
            out.append({
                "k": code.strip().lower(),
                "n": name or code,
                "s": _forensic_sector_bucket(sector_code, sector_name),
            })
        return out


_FORENSIC_BUCKETS = {"mining", "oilgas", "energy", "transport", "other"}


def _forensic_sector_bucket(sector_code: str | None, sector_name: str | None) -> str:
    """Сектор компании -> одна из 5 forensic-корзин (та же логика, что в
    exec_dashboard.sector_code): по коду сектора, иначе по названию."""
    c = (sector_code or "").lower().strip()
    n = (sector_name or "").lower()
    if c in _FORENSIC_BUCKETS:
        return c
    if "нефт" in n or "газ" in n or "oil" in c or "gas" in c:
        return "oilgas"
    if "горн" in n or "metall" in n or "mining" in c:
        return "mining"
    if "энерг" in n or "energ" in c:
        return "energy"
    if "трансп" in n or "телек" in n or "transport" in c or "telecom" in c:
        return "transport"
    return "other"
