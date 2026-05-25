"""ESG API — thin HTTP layer (refactored 2026-05-25).

Endpoints (URLs preserved):
  GET    /esg/overview                  Overview dashboard
  GET    /esg/companies/{company_id}    Per-company detail
  PUT    /esg/metric                    Upsert a metric
  DELETE /esg/metric/{metric_id}        Remove a metric
  GET    /esg/issues                    List issues
  POST   /esg/issue                     Create issue
  PATCH  /esg/issue/{issue_id}          Update issue
  DELETE /esg/issue/{issue_id}          Delete issue
"""
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status as http_status
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.access import allowed_company_ids, has_unrestricted_view
from app.core.security import get_current_user, has_effective_permission
from app.database import get_db
from app.dependencies.esg import (
    ESGCompanyServiceDep, ESGEditorServiceDep, ESGOverviewServiceDep,
)
from app.models.user import User
from app.schemas.esg import (
    ESGCompanyDetail, ESGIssueBrief, ESGIssueCreate, ESGIssueUpdate,
    ESGMetricBrief, ESGMetricUpsert, ESGOverviewResponse,
)


router = APIRouter(prefix="/esg", tags=["esg"])


async def _require(db: AsyncSession, user: User, code: str) -> None:
    if not await has_effective_permission(db, user, code):
        raise HTTPException(403, "Forbidden")


async def _scope(db: AsyncSession, user: User) -> Optional[list[UUID]]:
    """None = unrestricted, else explicit list (possibly empty)."""
    if has_unrestricted_view(user):
        return None
    allowed = await allowed_company_ids(db, user)
    return list(allowed) if allowed is not None else []


# ─── overview ─────────────────────────────────────────────────────

@router.get("/overview", response_model=ESGOverviewResponse)
async def get_overview(
    service: ESGOverviewServiceDep,
    year: Optional[int] = None,
    sector_code: Optional[str] = None,
    rankings_limit: int = Query(30, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    await _require(db, user, "esg.view")
    return await service.get_overview(
        year=year, sector_code=sector_code,
        rankings_limit=rankings_limit,
        scope_company_ids=await _scope(db, user),
    )


# ─── company detail ───────────────────────────────────────────────

@router.get("/companies/{company_id}", response_model=ESGCompanyDetail)
async def get_company_detail(
    company_id: UUID,
    service: ESGCompanyServiceDep,
    year: Optional[int] = None,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    await _require(db, user, "esg.view")
    return await service.get_company_detail(
        company_id, year=year, scope_company_ids=await _scope(db, user),
    )


# ─── metrics CRUD ─────────────────────────────────────────────────

@router.put("/metric", response_model=ESGMetricBrief)
async def upsert_metric(
    payload: ESGMetricUpsert,
    service: ESGEditorServiceDep,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    await _require(db, user, "esg.edit")

    from app.services.moderation_service import gate_or_apply
    queued, sub = await gate_or_apply(
        db, user=user,
        module="esg", action="upsert_metric",
        entity_id=None,
        entity_label=f"ESG metric {payload.metric_code} {payload.year}",
        company_id=payload.company_id, sector_id=None, year=payload.year,
        payload=payload.model_dump(mode="json"),
        diff_summary=f"ESG · {payload.pillar} · {payload.metric_code}",
    )
    if queued:
        return JSONResponse(
            status_code=http_status.HTTP_202_ACCEPTED,
            content={"queued": True, "submission_id": str(sub.id), "status": sub.status},
        )

    return await service.upsert_metric(payload, scope_company_ids=await _scope(db, user))


@router.delete("/metric/{metric_id}", status_code=http_status.HTTP_204_NO_CONTENT)
async def delete_metric(
    metric_id: UUID,
    service: ESGEditorServiceDep,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    await _require(db, user, "esg.edit")
    await service.delete_metric(metric_id, scope_company_ids=await _scope(db, user))


# ─── issues CRUD ──────────────────────────────────────────────────

@router.get("/issues", response_model=List[ESGIssueBrief])
async def list_issues(
    service: ESGEditorServiceDep,
    company_id: Optional[UUID] = None,
    pillar: Optional[str] = None,
    severity: Optional[str] = None,
    status: Optional[str] = None,
    limit: int = Query(100, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    await _require(db, user, "esg.view")
    return await service.list_issues(
        company_id=company_id, pillar=pillar,
        severity=severity, status=status,
        limit=limit,
        scope_company_ids=await _scope(db, user),
    )


@router.post("/issue", response_model=ESGIssueBrief, status_code=http_status.HTTP_201_CREATED)
async def create_issue(
    payload: ESGIssueCreate,
    service: ESGEditorServiceDep,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    await _require(db, user, "esg.edit")

    from app.services.moderation_service import gate_or_apply
    queued, sub = await gate_or_apply(
        db, user=user,
        module="esg", action="create_issue",
        entity_id=None, entity_label=f"ESG issue: {payload.title}",
        company_id=payload.company_id, sector_id=None, year=None,
        payload=payload.model_dump(mode="json"),
        diff_summary=f"ESG · {payload.pillar} · {payload.severity} · {payload.title}",
    )
    if queued:
        return JSONResponse(
            status_code=http_status.HTTP_202_ACCEPTED,
            content={"queued": True, "submission_id": str(sub.id), "status": sub.status},
        )

    return await service.create_issue(payload, scope_company_ids=await _scope(db, user))


@router.patch("/issue/{issue_id}", response_model=ESGIssueBrief)
async def update_issue(
    issue_id: UUID,
    payload: ESGIssueUpdate,
    service: ESGEditorServiceDep,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    await _require(db, user, "esg.edit")
    scope_ids = await _scope(db, user)
    pre = await service.get_issue_for_moderation(issue_id, scope_company_ids=scope_ids)

    from app.services.moderation_service import gate_or_apply
    queued, sub = await gate_or_apply(
        db, user=user,
        module="esg", action="update_issue",
        entity_id=str(issue_id), entity_label=f"ESG issue: {pre.title}",
        company_id=pre.company_id, sector_id=None, year=None,
        payload=payload.model_dump(mode="json", exclude_unset=True),
        diff_summary=f"Обновление ESG-issue '{pre.title}'",
    )
    if queued:
        return JSONResponse(
            status_code=http_status.HTTP_202_ACCEPTED,
            content={"queued": True, "submission_id": str(sub.id), "status": sub.status},
        )

    return await service.update_issue(issue_id, payload, scope_company_ids=scope_ids)


@router.delete("/issue/{issue_id}", status_code=http_status.HTTP_204_NO_CONTENT)
async def delete_issue(
    issue_id: UUID,
    service: ESGEditorServiceDep,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    await _require(db, user, "esg.edit")
    await service.delete_issue(issue_id, scope_company_ids=await _scope(db, user))
