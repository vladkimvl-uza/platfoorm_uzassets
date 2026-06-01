"""Invest Projects storage use-cases (Pack 8.0).

Firebase RTDB-style nested JSONB doc. Scope (C3b): scoped users see only
`companies/<own_code>/...`; owner / `companies.view_all` — unrestricted.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from urllib.parse import unquote

from fastapi import HTTPException
from fastapi import status as http_status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.access import allowed_company_ids, has_unrestricted_view
from app.models.user import User
from app.repositories.invest_projects_repository import InvestProjectsRepository


def _path_from_rest(rest: str) -> list[str]:
    rest = rest.lstrip("/")
    if rest.endswith(".json"):
        rest = rest[: -len(".json")]
    if not rest:
        return []
    return [unquote(p) for p in rest.split("/") if p]


def _nav(doc: dict, parts: list[str]) -> Any:
    cur: Any = doc
    for p in parts:
        if not isinstance(cur, dict) or p not in cur:
            return None
        cur = cur[p]
    return cur


def _set_nested(doc: dict, parts: list[str], value: Any) -> dict:
    if not parts:
        return value if isinstance(value, dict) else {}
    cur = doc
    for p in parts[:-1]:
        if not isinstance(cur.get(p), dict):
            cur[p] = {}
        cur = cur[p]
    cur[parts[-1]] = value
    return doc


@dataclass
class InvestProjectsService:
    @staticmethod
    def parse_path(rest: str) -> list[str]:
        return _path_from_rest(rest)

    async def _enforce_path_scope(
        self, db: AsyncSession, user: User, parts: list[str],
    ) -> None:
        """Allow only `companies/<allowed_code>/...` for scoped users."""
        if has_unrestricted_view(user):
            return
        if len(parts) < 2 or parts[0] != "companies":
            raise HTTPException(
                http_status.HTTP_403_FORBIDDEN,
                "Доступ только к ветке companies/<your_company_code>/...",
            )
        scope_ids = await allowed_company_ids(db, user)
        if not scope_ids:
            raise HTTPException(
                http_status.HTTP_403_FORBIDDEN, "Нет доступных компаний"
            )
        allowed_codes = await InvestProjectsRepository(
            db
        ).list_allowed_company_codes(scope_ids)
        requested = (parts[1] or "").lower()
        if requested not in allowed_codes:
            raise HTTPException(
                http_status.HTTP_403_FORBIDDEN,
                f"Нет доступа к данным компании {parts[1]}",
            )

    async def get_path(
        self, rest: str, db: AsyncSession, user: User
    ) -> Any:
        parts = self.parse_path(rest)
        await self._enforce_path_scope(db, user, parts)
        doc = await InvestProjectsRepository(db).load_doc()
        if not parts:
            return doc
        return _nav(doc, parts)

    async def put_path(
        self, rest: str, body: Any, db: AsyncSession, user: User
    ) -> Any:
        parts = self.parse_path(rest)
        await self._enforce_path_scope(db, user, parts)
        repo = InvestProjectsRepository(db)
        doc = await repo.load_doc()
        updated = _set_nested(doc, parts, body)
        await repo.save_doc(updated, user.email)
        return body

    async def patch_path(
        self, rest: str, body: Any, db: AsyncSession, user: User
    ) -> Any:
        parts = self.parse_path(rest)
        await self._enforce_path_scope(db, user, parts)
        if not isinstance(body, dict):
            raise HTTPException(
                http_status.HTTP_400_BAD_REQUEST,
                "PATCH body must be a JSON object",
            )
        repo = InvestProjectsRepository(db)
        doc = await repo.load_doc()
        target = _nav(doc, parts)
        if target is None or not isinstance(target, dict):
            _set_nested(doc, parts, body)
        else:
            target.update(body)
        await repo.save_doc(doc, user.email)
        return body

    async def delete_path(
        self, rest: str, db: AsyncSession, user: User
    ) -> dict:
        parts = self.parse_path(rest)
        await self._enforce_path_scope(db, user, parts)
        if not parts:
            raise HTTPException(
                http_status.HTTP_400_BAD_REQUEST,
                "Root-level DELETE refused. Specify a path.",
            )
        repo = InvestProjectsRepository(db)
        doc = await repo.load_doc()
        cur: Any = doc
        for p in parts[:-1]:
            if not isinstance(cur, dict) or p not in cur:
                return {"ok": True, "removed": False}
            cur = cur[p]
        leaf = parts[-1]
        if isinstance(cur, dict) and leaf in cur:
            del cur[leaf]
            await repo.save_doc(doc, user.email)
            return {"ok": True, "removed": True}
        return {"ok": True, "removed": False}
