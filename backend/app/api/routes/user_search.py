"""Lightweight user search — thin HTTP shim.

Pack 149. Used by autocomplete @-mention pickers in task/project/comment editors.
Returns only public-safe fields (id, email, full_name, initials, department).

2026-05-26 hardening:
  • Min query length 2 (was 0) — prevents bulk enumeration via empty `q`
  • Rate-limited via RATE_LIMIT_USER_SEARCH (defaults to RATE_LIMIT_DEFAULT)
  • Cap limit to 25 (was 50) — autocomplete UX needs ~10 results anyway
"""
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db
from app.config import settings
from app.core.rate_limit import limiter
from app.dependencies.user_search import UserSearchServiceDep
from app.models.user import User

router = APIRouter(prefix="/users", tags=["users"])


@router.get("/search")
@limiter.limit(getattr(settings, "RATE_LIMIT_USER_SEARCH", settings.RATE_LIMIT_DEFAULT))
async def search_users(
    request: Request,
    service: UserSearchServiceDep,
    q: str = Query("", max_length=128,
                   description="Подстрока для поиска (минимум 2 символа)"),
    limit: int = Query(10, ge=1, le=25),
    active_only: bool = True,
    db: AsyncSession = Depends(get_db),
    _u: User = Depends(get_current_user),
):
    # 2026-05-26: defensive — пустой `q` или 1 символ позволяет enumeration
    # всего user-каталога. Минимум 2 символа = ~676 combinations при ASCII,
    # ~3M при кириллице → достаточно ограничивает scraping.
    q_clean = (q or "").strip()
    if len(q_clean) < 2:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "Минимум 2 символа для поиска пользователей",
        )
    return await service.search(
        db, q=q_clean, active_only=active_only, limit=limit,
    )
