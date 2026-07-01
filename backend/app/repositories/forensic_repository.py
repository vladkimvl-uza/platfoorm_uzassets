"""Data access for Forensic (procurement plan/fact JSONB snapshot)."""
from __future__ import annotations

import json
from collections.abc import Sequence
from uuid import UUID

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.company import Company

_SNAPSHOT_KEY = "raw_snapshot.procurementData"


class ForensicRepository:
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
            "d": "Procurement plan/fact data (PROCUREMENT_DATA) mutable via /forensic endpoints",
        })

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
