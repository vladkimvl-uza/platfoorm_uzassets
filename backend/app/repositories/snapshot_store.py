"""Общий доступ к JSONB-снапшотам в `system_config`.

Несколько модулей (forensic/production/unit_cost) хранят план/факт одним
JSONB-значением под своим ключом. Раньше идентичный raw-SQL (SELECT ... /
INSERT ... ON CONFLICT DO UPDATE) был скопирован в трёх местах байт-в-байт,
причём unit_cost делал это прямо в СЕРВИСЕ с `db.commit()` (нарушение
10-слойной архитектуры). Здесь — единственный источник.

НЕ коммитит: транзакцией владеет вызывающий слой (UoW `__aexit__` или get_db
на конце запроса). Значение — произвольный JSON (list у forensic/production,
dict у unit_cost); вызывающий приводит к своей форме.
"""
from __future__ import annotations

import json
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

_UPSERT_SQL = text("""
    INSERT INTO system_config (id, key, value, description, is_secret,
                               created_at, updated_at)
    VALUES (gen_random_uuid(), :k, CAST(:v AS jsonb), :d, FALSE, NOW(), NOW())
    ON CONFLICT (key) DO UPDATE
    SET value = EXCLUDED.value, updated_at = NOW()
""")

_SELECT_SQL = text("SELECT value FROM system_config WHERE key = :k LIMIT 1")


class SnapshotStore:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def load(self, key: str) -> Any:
        """Распарсенный JSON снапшота или None (нет строки/пустое/битый JSON)."""
        row = (await self.session.execute(_SELECT_SQL, {"k": key})).first()
        if not row or not row[0]:
            return None
        v = row[0]
        if isinstance(v, str):
            try:
                return json.loads(v)
            except json.JSONDecodeError:
                return None
        return v

    async def save(self, key: str, value: Any, description: str) -> None:
        """Upsert снапшота. НЕ коммитит — коммит на владельце транзакции."""
        await self.session.execute(_UPSERT_SQL, {
            "k": key,
            "v": json.dumps(value, ensure_ascii=False),
            "d": description,
        })
