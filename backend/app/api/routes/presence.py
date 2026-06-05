"""Presence heartbeat — любой залогиненный пользователь отмечает «я онлайн».

Фронт пингует POST /presence/heartbeat пока вкладка активна. Бэкенд лишь
обновляет users.last_seen_at; online/away/offline вычисляется на клиенте
из давности этого timestamp. НЕ admin-only — это про самого вызывающего.
"""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from fastapi import status as http_status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import get_current_user
from app.database import get_db
from app.models.user import User

router = APIRouter(prefix="/presence", tags=["presence"])


@router.post("/heartbeat", status_code=http_status.HTTP_204_NO_CONTENT)
async def heartbeat(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Отметить присутствие текущего пользователя (last_seen_at = now)."""
    u = await db.get(User, user.id)
    if u is not None:
        u.last_seen_at = datetime.now(timezone.utc)
        await db.commit()
