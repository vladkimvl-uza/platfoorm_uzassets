"""Centralized access-scope helpers (Pack 147).

Per-company access is sourced from membership in Groups bound to companies
(`groups.company_id`). The (user, group, role) row in `user_group_role`
both grants visibility to the company AND provides the role whose
permissions apply inside that scope.

Visibility tiers (first match wins):
  1. user.is_owner=True                       → see EVERYTHING
  2. user has `companies.view_all` permission → see EVERYTHING
  3. user is in groups bound to companies     → see those companies
  4. user.organization_id is set              → see that one company
  5. otherwise                                → see NOTHING
"""
from typing import List, Optional, Union
from uuid import UUID

from fastapi import HTTPException, status as http_status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import _has_permission
from app.models.user import Group, User, UserGroupRole


def has_unrestricted_view(user: User) -> bool:
    """True if the user can see all companies regardless of group membership.

    Owner and holders of `companies.view_all` bypass per-company scoping.
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
    """
    if has_unrestricted_view(user):
        return None  # Sentinel: no filter needed

    # Collect company_ids via group membership (user_group_role → groups.company_id).
    q = await db.execute(
        select(Group.company_id)
        .join(UserGroupRole, UserGroupRole.group_id == Group.id)
        .where(UserGroupRole.user_id == user.id, Group.company_id.is_not(None))
    )
    ids: list[UUID] = [row for row in q.scalars().all() if row is not None]

    # Plus legacy organization_id (if set and not already in the list).
    org_id = user.organization_id
    if org_id is not None and org_id not in ids:
        ids.append(org_id)

    return ids


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
