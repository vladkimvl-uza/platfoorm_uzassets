"""Lightweight user search — thin HTTP shim.

Pack 149. Used by autocomplete @-mention pickers in task/project/comment editors.
Returns only public-safe fields (id, email, full_name, initials, department).

2026-05-26 hardening:
  • Min query length 2 (was 0) — prevents bulk enumeration via empty `q`
  • Rate-limited via RATE_LIMIT_USER_SEARCH (defaults to RATE_LIMIT_DEFAULT)
  • Cap limit to 25 (was 50) — autocomplete UX needs ~10 results anyway
"""
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from sqlalchemy import func

from app.api.deps import get_current_user, get_db
from app.core.access import ensure_company_access
from app.config import settings
from app.core.rate_limit import limiter
from app.dependencies.user_search import UserSearchServiceDep
from app.models.audit import AuditLog
from app.models.company import Company, Sector
from app.models.user import User

router = APIRouter(prefix="/users", tags=["users"])

# Палитра акцентов аватара (синхронна с аудитом/карточкой)
_ACCENT_PALETTE = ["#7F77DD", "#1D9E75", "#378ADD", "#EF9F27", "#D4537E", "#0E7490", "#9333EA"]


def _initials(name: str) -> str:
    parts = [p for p in (name or "").split() if p]
    if not parts:
        return (name or "?")[:1].upper()
    return "".join(p[0] for p in parts[:2]).upper()


def _accent(seed: str) -> str:
    """Детерминированный акцент по id (стабилен между запросами)."""
    h = 0
    for ch in seed:
        h = (h * 31 + ord(ch)) & 0xFFFFFFFF
    return _ACCENT_PALETTE[h % len(_ACCENT_PALETTE)]


@router.get("/card")
async def user_card(
    email: Optional[str] = Query(None),
    id: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    _u: User = Depends(get_current_user),
):
    """Мини-карточка пользователя для hover-поповера (по email или id)."""
    if not email and not id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "email или id обязателен")
    q = select(User).options(selectinload(User.roles))
    if id:
        try:
            q = q.where(User.id == UUID(id))
        except Exception as e:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Некорректный id") from e
    else:
        q = q.where(User.email == email)
    u = (await db.execute(q)).scalar_one_or_none()
    if not u:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Пользователь не найден")
    role = None
    if getattr(u, "roles", None):
        r0 = u.roles[0]
        role = getattr(r0, "name_ru", None) or getattr(r0, "name", None) or getattr(r0, "code", None)
    elif getattr(u, "is_owner", False):
        role = "Владелец"

    # Принадлежность: компания/сектор/цвет сектора из organization_id
    company = sector = sector_color = None
    org_id = getattr(u, "organization_id", None)
    if org_id:
        row = (await db.execute(
            select(
                Company.name_short,
                Company.name_ru,
                Sector.name_ru.label("sector"),
                Sector.color_hex.label("color"),
            )
            .outerjoin(Sector, Sector.id == Company.sector_id)
            .where(Company.id == org_id)
        )).first()
        if row:
            company = row.name_short or row.name_ru
            sector = row.sector
            sector_color = row.color

    # Последняя активность — самый свежий аудит-эвент пользователя
    last_active = None
    last_dt = (await db.execute(
        select(func.max(AuditLog.created_at)).where(AuditLog.actor_id == u.id)
    )).scalar()
    if last_dt:
        last_active = last_dt.isoformat()

    return {
        "id": str(u.id),
        "full_name": u.full_name,
        "email": u.email,
        "initials": _initials(u.full_name or u.email),
        "department": u.department,
        "job_title": u.job_title,
        "phone": u.phone,
        "avatar_url": u.avatar_url,
        "is_external": u.is_external,
        "is_active": u.is_active,
        "is_owner": bool(getattr(u, "is_owner", False)),
        "role": role,
        "company": company,
        "sector": sector,
        "sector_color": sector_color,
        "accent": _accent(str(u.id)),
        "last_active": last_active,
        "linkedin_url": getattr(u, "linkedin_url", None),
        "website_url": getattr(u, "website_url", None),
        "telegram_username": getattr(u, "telegram_username", None),
    }


@router.get("/search")
@limiter.limit(getattr(settings, "RATE_LIMIT_USER_SEARCH", settings.RATE_LIMIT_DEFAULT))
async def search_users(
    request: Request,
    service: UserSearchServiceDep,
    q: str = Query("", max_length=128,
                   description="Подстрока для поиска (минимум 2 символа)"),
    company_code: Optional[str] = Query(
        None, max_length=32,
        description="Ограничить сотрудниками компании (её код). Тогда пустой q "
                    "разрешён — возвращается список сотрудников этой компании.",
    ),
    limit: int = Query(10, ge=1, le=25),
    active_only: bool = True,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    q_clean = (q or "").strip()
    company_id = None
    if company_code:
        row = (await db.execute(
            select(Company.id).where(Company.code == company_code.lower())
        )).first()
        if row is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Company not found")
        company_id = row[0]
        # Область запроса — своя компания, поэтому список её сотрудников без
        # поисковой строки НЕ является перечислением каталога платформы.
        # Но доступ к самой компании обязателен.
        await ensure_company_access(db, user, company_id)
    elif len(q_clean) < 2:
        # 2026-05-26: defensive — пустой `q` или 1 символ позволяет enumeration
        # всего user-каталога. Минимум 2 символа = ~676 combinations при ASCII,
        # ~3M при кириллице → достаточно ограничивает scraping.
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "Минимум 2 символа для поиска пользователей",
        )
    return await service.search(
        db, q=q_clean, active_only=active_only, limit=limit,
        company_id=company_id,
    )
