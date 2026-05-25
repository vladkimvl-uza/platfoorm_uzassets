"""User-search use-case: substring search for autocomplete + @-mentions.

Any authenticated user can call this. Returns only public-safe fields.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.user_search_repository import UserSearchRepository


def _make_initials(full_name: Optional[str], email: str) -> str:
    if full_name:
        parts = full_name.strip().split()
        if len(parts) >= 2:
            return (parts[0][:1] + parts[1][:1]).upper()
        if parts:
            return parts[0][:2].upper()
    return email.split("@", 1)[0][:2].upper()


@dataclass
class UserSearchService:
    async def search(
        self,
        db: AsyncSession,
        *,
        q: str,
        active_only: bool,
        limit: int,
    ) -> dict:
        needle = q.strip().lower()
        rows = await UserSearchRepository(db).search(
            needle=needle, active_only=active_only, limit=limit,
        )
        return {
            "items": [
                {
                    "id": str(u.id),
                    "email": u.email,
                    "full_name": u.full_name,
                    "username": u.username,
                    "initials": _make_initials(u.full_name, u.email),
                    "department": u.department,
                    "is_active": bool(u.is_active),
                }
                for u in rows
            ],
            "count": len(rows),
            "query": q,
        }
