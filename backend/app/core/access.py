"""Centralized access-scope helpers.

A single user.allowed_companies field gates visibility across the entire
API surface — companies, tasks, projects, financials, ratings, etc.
This module provides reusable helpers so each route file applies the
exact same scoping logic, which is critical for security: any place that
forgets to apply it would leak data to organization-restricted users.

Visibility tiers (top to bottom — first match wins):

  1. user.is_owner=True                 → see EVERYTHING
  2. user has companies.view_all perm   → see EVERYTHING
  3. user.allowed_companies = [<list>]  → see ONLY those (codes or UUIDs)
  4. user.organization_id = <uuid>      → see ONLY that one company
  5. otherwise                          → see NOTHING
"""
from typing import List, Optional, Union
from uuid import UUID

from fastapi import HTTPException, status as http_status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import _has_permission
from app.models.company import Company
from app.models.user import User


def has_unrestricted_view(user: User) -> bool:
    """True if the user can see all companies regardless of allowed_companies.

    These are the privileged users: platform owners and anyone with the
    `companies.view_all` permission. They bypass per-company scoping.
    """
    if user.is_owner:
        return True
    if _has_permission(user, "companies.view_all"):
        return True
    return False


async def allowed_company_ids(db: AsyncSession, user: User) -> Optional[List[UUID]]:
    """Resolve the list of company UUIDs the user is permitted to see.

    Returns:
      - None  → user can see ALL companies (bypass any company filter)
      - []    → user can see NO companies (use this to short-circuit
                queries to empty results rather than running them)
      - [...] → list of UUIDs to filter by

    `user.allowed_companies` may contain a mix of UUIDs (already-resolved)
    and company codes (string slugs). We resolve codes via a single batched
    SELECT — N+1 here would be very expensive across the API.
    """
    if has_unrestricted_view(user):
        return None  # Sentinel: no filter needed

    raw = list(user.allowed_companies or [])
    org_id = user.organization_id

    if not raw and org_id is None:
        return []  # No access at all

    # Split into already-UUIDs vs codes-to-resolve.
    # UUID() парсит и с дефисами, и hex32 без дефисов, и в любом регистре —
    # это надёжнее эвристики "ровно 36 символов и 4 дефиса".
    uuid_ids: list[UUID] = []
    code_strs: list[str] = []
    for v in raw:
        s = str(v).strip()
        if not s:
            continue
        try:
            uuid_ids.append(UUID(s))
        except (ValueError, AttributeError):
            code_strs.append(s.lower())

    # Resolve codes to UUIDs in one batched query
    if code_strs:
        q = await db.execute(
            select(Company.id).where(Company.code.in_(code_strs))
        )
        for row in q.scalars().all():
            uuid_ids.append(row)

    # Always include organization_id if set
    if org_id is not None and org_id not in uuid_ids:
        uuid_ids.append(org_id)

    return uuid_ids


async def ensure_company_access(
    db: AsyncSession,
    user: User,
    company_id: Union[UUID, str, None],
    *,
    detail: str = "Access to this company is not allowed",
) -> None:
    """Raise 403 if `user` has no access to `company_id`.

    Используй в любом endpoint, который принимает company_id (в path, query
    или payload) и должен соблюдать per-company scoping. Owner и носители
    `companies.view_all` — bypass.

    `company_id=None` трактуется как 400 (вызывающий код должен
    отвергать пустой company_id раньше — здесь это safety net).
    """
    if company_id is None:
        raise HTTPException(http_status.HTTP_400_BAD_REQUEST, "company_id is required")

    if has_unrestricted_view(user):
        return

    allowed = await allowed_company_ids(db, user)
    if allowed is None:
        return  # consistency: unrestricted view

    target: UUID
    if isinstance(company_id, UUID):
        target = company_id
    else:
        try:
            target = UUID(str(company_id))
        except (ValueError, TypeError):
            raise HTTPException(http_status.HTTP_400_BAD_REQUEST, "invalid company_id")

    if target not in allowed:
        raise HTTPException(http_status.HTTP_403_FORBIDDEN, detail)
