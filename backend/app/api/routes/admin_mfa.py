"""Admin MFA overview + force-disable (Pack 13.1.2) — thin HTTP shim
(refactored 2026-05-25).

GET  /admin/users/mfa-overview                — admin.users / admin.security
POST /admin/users/{user_id}/mfa-force-disable — owner-only
"""
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import get_current_user
from app.database import get_db
from app.dependencies.admin_mfa import AdminMfaServiceDep
from app.models.user import User
from app.services.admin_mfa.service import MfaOverviewResponse

router = APIRouter(prefix="/admin/users", tags=["admin-mfa"])


@router.get("/mfa-overview", response_model=MfaOverviewResponse)
async def mfa_overview(
    service: AdminMfaServiceDep,
    # 2026-05-26: добавлена пагинация — раньше грузило всех active users
    # в память (DoS-вектор на 100k+ user платформах).
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    search: str = Query("", max_length=128, description="email/full_name/username substring"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await service.overview(current_user, db, limit=limit, offset=offset, search=search)


@router.post(
    "/{user_id}/mfa-force-disable",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def force_disable_mfa(
    user_id: UUID,
    request: Request,
    service: AdminMfaServiceDep,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await service.force_disable_mfa(user_id, request, current_user, db)
