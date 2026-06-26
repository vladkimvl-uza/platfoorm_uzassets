"""Governance API — thin HTTP layer (refactored 2026-05-25).

Endpoints (URLs preserved):
  GET    /governance/overview                       Overview dashboard
  GET    /governance/companies/{company_id}         Per-company detail
  PUT    /governance/data                           Upsert GovernanceData
  GET    /governance/companies/{company_id}/members List board members
  POST   /governance/member                         Add a board member
  PATCH  /governance/member/{member_id}             Update board member
  DELETE /governance/member/{member_id}             Delete board member
"""
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi import status as http_status
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.access import allowed_company_ids, has_unrestricted_view
from app.core.security import get_current_user, has_effective_permission
from app.database import get_db
from app.dependencies.governance import GovernanceServiceDep
from app.models.user import User
from app.schemas.governance import (
    BoardMemberBrief,
    BoardMemberCreate,
    BoardMemberUpdate,
    CommitteeMeetingPeriodCreate,
    CommitteeMeetingPeriodCreateResult,
    CommitteeMeetingsResponse,
    CommitteeMeetingUpsert,
    CommitteeMeetingUpsertResult,
    GovernanceCompanyDetail,
    GovernanceDataBrief,
    GovernanceDataEdit,
    GovernanceOverviewResponse,
)

router = APIRouter(prefix="/governance", tags=["governance"])


async def _require(db: AsyncSession, user: User, code: str) -> None:
    if not await has_effective_permission(db, user, code):
        raise HTTPException(403, "Forbidden")


async def _scope(db: AsyncSession, user: User) -> Optional[list[UUID]]:
    """None = unrestricted, else explicit list (possibly empty)."""
    if has_unrestricted_view(user):
        return None
    allowed = await allowed_company_ids(db, user)
    return list(allowed) if allowed is not None else []


# ─── Overview ─────────────────────────────────────────────────────

@router.get("/overview", response_model=GovernanceOverviewResponse)
async def get_overview(
    service: GovernanceServiceDep,
    year: Optional[int] = None,
    sector_code: Optional[str] = None,
    rankings_limit: int = Query(30, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    await _require(db, user, "governance.view")
    return await service.get_overview(
        year=year, sector_code=sector_code,
        rankings_limit=rankings_limit,
        scope_company_ids=await _scope(db, user),
    )


# ─── Company detail ───────────────────────────────────────────────

@router.get("/companies/{company_id}", response_model=GovernanceCompanyDetail)
async def get_company_detail(
    company_id: UUID,
    service: GovernanceServiceDep,
    year: Optional[int] = None,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    await _require(db, user, "governance.view")
    return await service.get_company_detail(
        company_id, year=year,
        scope_company_ids=await _scope(db, user),
    )


# ─── governance_data upsert ───────────────────────────────────────

@router.put("/data", response_model=GovernanceDataBrief)
async def upsert_governance_data(
    payload: GovernanceDataEdit,
    service: GovernanceServiceDep,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    await _require(db, user, "governance.edit")

    # Moderation gate
    from app.services.moderation_service import gate_or_apply
    queued, sub = await gate_or_apply(
        db, user=user,
        module="governance", action="upsert_data",
        entity_id=None,
        entity_label=f"Governance data {payload.year}",
        company_id=payload.company_id, sector_id=None, year=payload.year,
        payload=payload.model_dump(mode="json"),
        diff_summary=f"Сохранение governance-данных за {payload.year}",
    )
    if queued:
        return JSONResponse(
            status_code=http_status.HTTP_202_ACCEPTED,
            content={"queued": True, "submission_id": str(sub.id), "status": sub.status},
        )

    return await service.upsert_governance_data(
        payload, scope_company_ids=await _scope(db, user),
    )


# ─── committee meetings (кол-во заседаний по периодам) ─────────────

@router.get("/committee-meetings", response_model=CommitteeMeetingsResponse)
async def get_committee_meetings(
    service: GovernanceServiceDep,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    await _require(db, user, "companies.view")
    return await service.get_committee_meetings(
        scope_company_ids=await _scope(db, user),
    )


@router.put("/committee-meetings", response_model=CommitteeMeetingUpsertResult)
async def upsert_committee_meeting(
    payload: CommitteeMeetingUpsert,
    service: GovernanceServiceDep,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    await _require(db, user, "companies.edit")
    return await service.upsert_committee_meeting(
        payload, scope_company_ids=await _scope(db, user),
    )


@router.post("/committee-meetings/period", response_model=CommitteeMeetingPeriodCreateResult)
async def create_committee_period(
    payload: CommitteeMeetingPeriodCreate,
    service: GovernanceServiceDep,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    await _require(db, user, "companies.edit")
    return await service.create_committee_period(payload)


# ─── board members ────────────────────────────────────────────────

@router.get("/companies/{company_id}/members", response_model=list[BoardMemberBrief])
async def list_board_members(
    company_id: UUID,
    service: GovernanceServiceDep,
    include_past: bool = False,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    await _require(db, user, "governance.view")
    return await service.list_board_members(
        company_id, include_past=include_past,
        scope_company_ids=await _scope(db, user),
    )


@router.post("/member", response_model=BoardMemberBrief, status_code=http_status.HTTP_201_CREATED)
async def create_board_member(
    payload: BoardMemberCreate,
    service: GovernanceServiceDep,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    await _require(db, user, "governance.edit")

    from app.services.moderation_service import gate_or_apply
    queued, sub = await gate_or_apply(
        db, user=user,
        module="governance", action="create_member",
        entity_id=None, entity_label=f"Член СД: {payload.full_name}",
        company_id=payload.company_id, sector_id=None, year=None,
        payload=payload.model_dump(mode="json"),
        diff_summary=f"Добавление члена СД: {payload.full_name} ({payload.role_type})",
    )
    if queued:
        return JSONResponse(
            status_code=http_status.HTTP_202_ACCEPTED,
            content={"queued": True, "submission_id": str(sub.id), "status": sub.status},
        )

    return await service.create_board_member(
        payload, scope_company_ids=await _scope(db, user),
    )


@router.patch("/member/{member_id}", response_model=BoardMemberBrief)
async def update_board_member(
    member_id: UUID,
    payload: BoardMemberUpdate,
    service: GovernanceServiceDep,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    await _require(db, user, "governance.edit")
    scope_ids = await _scope(db, user)

    # Moderation gate needs full_name + company_id from existing record
    m = await service.get_member_for_moderation(member_id, scope_company_ids=scope_ids)

    from app.services.moderation_service import gate_or_apply
    queued, sub = await gate_or_apply(
        db, user=user,
        module="governance", action="update_member",
        entity_id=str(member_id), entity_label=f"Член СД: {m.full_name}",
        company_id=m.company_id, sector_id=None, year=None,
        payload=payload.model_dump(mode="json", exclude_unset=True),
        diff_summary=f"Обновление члена СД '{m.full_name}'",
    )
    if queued:
        return JSONResponse(
            status_code=http_status.HTTP_202_ACCEPTED,
            content={"queued": True, "submission_id": str(sub.id), "status": sub.status},
        )

    _, brief = await service.update_board_member(
        member_id, payload, scope_company_ids=scope_ids,
    )
    return brief


@router.delete("/member/{member_id}", status_code=http_status.HTTP_204_NO_CONTENT)
async def delete_board_member(
    member_id: UUID,
    service: GovernanceServiceDep,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    await _require(db, user, "governance.edit")
    await service.delete_board_member(
        member_id, scope_company_ids=await _scope(db, user),
    )
