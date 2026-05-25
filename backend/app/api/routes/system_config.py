"""System Config (YearRegistry) API — thin HTTP layer (refactored 2026-05-25).

Audit-chain writes stay in route file: they are post-commit side-effects
that need the HTTP Request for IP/user-agent.
"""
from typing import List

from fastapi import APIRouter, Depends, HTTPException, Request, status as http_status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit_chain import append_audit_entry
from app.core.security import _has_permission, get_current_user
from app.database import get_db
from app.dependencies.system_config import SystemConfigServiceDep
from app.models.user import User
from app.schemas.system_config import (
    YearlyRate, YearlyRateCreate, YearlyRateUpdate,
)


router = APIRouter(prefix="/system-config", tags=["system-config"])


def _require_admin(user: User) -> None:
    if user.is_owner:
        return
    if _has_permission(user, "admin.users"):
        return
    raise HTTPException(
        http_status.HTTP_403_FORBIDDEN,
        "Permission required: admin.users (or owner status)",
    )


@router.get("/yearly-rates", response_model=List[YearlyRate])
async def list_yearly_rates(
    service: SystemConfigServiceDep,
    user: User = Depends(get_current_user),
):
    """Public read — used by every dashboard for UZS↔USD conversion."""
    return await service.list_yearly_rates()


@router.post("/yearly-rates", response_model=YearlyRate,
             status_code=http_status.HTTP_201_CREATED)
async def create_yearly_rate(
    payload: YearlyRateCreate,
    request: Request,
    service: SystemConfigServiceDep,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    _require_admin(user)
    new_year, snapshot = await service.create_yearly_rate(payload)
    await append_audit_entry(
        db,
        actor_id=str(user.id), actor_email=user.email,
        action="create", entity_type="year_registry",
        entity_id=str(payload.year),
        payload=snapshot,
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    await db.commit()
    return new_year


@router.patch("/yearly-rates/{year}", response_model=YearlyRate)
async def update_yearly_rate(
    year: int,
    payload: YearlyRateUpdate,
    request: Request,
    service: SystemConfigServiceDep,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
    allow_closed: bool = False,
):
    _require_admin(user)
    updated, diff = await service.update_yearly_rate(
        year, payload, allow_closed=allow_closed,
    )
    if diff:
        await append_audit_entry(
            db,
            actor_id=str(user.id), actor_email=user.email,
            action="update", entity_type="year_registry",
            entity_id=str(year),
            diff=diff,
            ip_address=request.client.host if request.client else None,
            user_agent=request.headers.get("user-agent"),
        )
        await db.commit()
    return updated


@router.delete("/yearly-rates/{year}", status_code=http_status.HTTP_204_NO_CONTENT)
async def delete_yearly_rate(
    year: int,
    request: Request,
    service: SystemConfigServiceDep,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
    force: bool = False,
):
    _require_admin(user)
    snapshot = await service.delete_yearly_rate(year, force=force)
    if snapshot is not None:
        await append_audit_entry(
            db,
            actor_id=str(user.id), actor_email=user.email,
            action="delete", entity_type="year_registry",
            entity_id=str(year),
            payload=snapshot,
            ip_address=request.client.host if request.client else None,
            user_agent=request.headers.get("user-agent"),
        )
        await db.commit()
    return None
