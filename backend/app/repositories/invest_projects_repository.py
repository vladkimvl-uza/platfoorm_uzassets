"""Persistence layer for Invest Projects storage (Pack 8.0).

Single-row JSONB blob in `invest_projects_storage(id=1, data)`. Raw SQL —
no ORM model exists for this table.
"""
from __future__ import annotations

from typing import Any, Sequence
from uuid import UUID

from fastapi import HTTPException, status as http_status
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.company import Company


def _json_str(d: Any) -> str:
    import json
    return json.dumps(d, ensure_ascii=False, separators=(",", ":"))


class InvestProjectsRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def load_doc(self) -> dict:
        try:
            q = await self._session.execute(
                text("SELECT data FROM invest_projects_storage WHERE id = 1")
            )
            row = q.first()
        except Exception as e:
            msg = str(e).lower()
            if "invest_projects_storage" in msg and (
                "does not exist" in msg or "undefinedtable" in msg
            ):
                return {}
            raise
        if not row:
            try:
                await self._session.execute(text(
                    "INSERT INTO invest_projects_storage (id, data) "
                    "VALUES (1, '{}'::jsonb) ON CONFLICT DO NOTHING"
                ))
                await self._session.commit()
            except Exception:
                pass
            return {}
        return row[0] or {}

    async def save_doc(self, data: dict, user_email: str) -> None:
        try:
            await self._session.execute(
                text("""INSERT INTO invest_projects_storage (id, data, updated_by)
                        VALUES (1, CAST(:data AS jsonb), :user)
                        ON CONFLICT (id) DO UPDATE
                        SET data = EXCLUDED.data,
                            updated_at = NOW(),
                            updated_by = EXCLUDED.updated_by"""),
                {"data": _json_str(data), "user": user_email},
            )
            await self._session.commit()
        except Exception as e:
            msg = str(e).lower()
            if "invest_projects_storage" in msg and (
                "does not exist" in msg or "undefinedtable" in msg
            ):
                raise HTTPException(
                    http_status.HTTP_503_SERVICE_UNAVAILABLE,
                    "Таблица invest_projects_storage не создана. "
                    "Выполни: docker exec uza-backend alembic upgrade head",
                )
            raise

    async def list_allowed_company_codes(
        self, scope_ids: Sequence[UUID]
    ) -> set[str]:
        rows = await self._session.execute(
            select(Company.code).where(Company.id.in_(list(scope_ids)))
        )
        return {(c or "").lower() for (c,) in rows.all() if c}
