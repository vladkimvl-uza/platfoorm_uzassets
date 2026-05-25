"""Audit log REST endpoints (Pack 9.0) — thin HTTP shim (refactored 2026-05-25).

All routes require permission `audit.view` (owner + admin auto-bypass).
Export route requires `audit.admin`.
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import require_permission
from app.database import get_db
from app.dependencies.audit import AuditAdminServiceDep
from app.models.user import User
from app.schemas.audit import (
    AuditEventDetail, AuditEventList, AuditOverviewResponse,
    AuditStatsResponse, AuditTimelineResponse,
)


router = APIRouter(prefix="/admin/audit", tags=["audit"])


@router.get("/overview", response_model=AuditOverviewResponse)
async def overview(
    service: AuditAdminServiceDep,
    hours: int = Query(24, ge=1, le=720),
    db: AsyncSession = Depends(get_db),
    _u: User = Depends(require_permission("audit.view")),
):
    return await service.overview(db, hours=hours)


@router.get("/events", response_model=AuditEventList)
async def list_events(
    service: AuditAdminServiceDep,
    actor_email: Optional[str] = Query(None),
    module: Optional[str] = Query(None),
    action: Optional[str] = Query(None),
    hours: Optional[int] = Query(None, ge=1, le=720),
    since: Optional[datetime] = Query(None),
    until: Optional[datetime] = Query(None),
    search: Optional[str] = Query(None),
    only_critical: bool = Query(False),
    api_key_id: Optional[UUID] = Query(None, description="Pack 12.4: filter by API key"),
    only_api_key: bool = Query(False, description="Pack 12.4: only entries authed via API key"),
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    _u: User = Depends(require_permission("audit.view")),
):
    return await service.list_events(
        db,
        actor_email=actor_email, module=module, action=action,
        hours=hours, since=since, until=until,
        search=search, only_critical=only_critical,
        api_key_id=api_key_id, only_api_key=only_api_key,
        page=page, per_page=per_page,
    )


@router.get("/events/{event_id}", response_model=AuditEventDetail)
async def event_detail(
    event_id: UUID,
    service: AuditAdminServiceDep,
    db: AsyncSession = Depends(get_db),
    _u: User = Depends(require_permission("audit.view")),
):
    return await service.event_detail(event_id, db)


@router.get("/stats", response_model=AuditStatsResponse)
async def stats_only(
    service: AuditAdminServiceDep,
    hours: int = Query(24, ge=1, le=720),
    db: AsyncSession = Depends(get_db),
    _u: User = Depends(require_permission("audit.view")),
):
    return await service.stats_only(db, hours=hours)


@router.get("/timeline", response_model=AuditTimelineResponse)
async def timeline_endpoint(
    service: AuditAdminServiceDep,
    hours: int = Query(24, ge=1, le=720),
    bucket: str = Query("hour", regex="^(hour|day)$"),
    db: AsyncSession = Depends(get_db),
    _u: User = Depends(require_permission("audit.view")),
):
    return await service.timeline(db, hours=hours, bucket=bucket)


@router.get("/export.csv")
async def export_csv(
    service: AuditAdminServiceDep,
    hours: int = Query(24, ge=1, le=720),
    db: AsyncSession = Depends(get_db),
    _u: User = Depends(require_permission("audit.admin")),
):
    return await service.export_csv(db, hours=hours)
