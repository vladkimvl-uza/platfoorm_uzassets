"""Pack 8.0 — Invest Projects Firebase-RTDB storage — thin HTTP shim
(refactored 2026-05-25).

Routes:
    GET    /invest-projects-storage/root/{path}.json   read at nested path
    PUT    /invest-projects-storage/root/{path}.json   replace
    PATCH  /invest-projects-storage/root/{path}.json   shallow-merge
    DELETE /invest-projects-storage/root/{path}.json   remove key

Scope (C3b): scoped users see only `companies/<own_code>/...`; owner +
`companies.view_all` — unrestricted. Root-DELETE refused as safety.
"""
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi import status as http_status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.database import get_db
from app.dependencies.invest_projects import InvestProjectsServiceDep
from app.models.user import User

router = APIRouter(
    prefix="/invest-projects-storage", tags=["invest-projects-storage"]
)


async def _parse_body(request: Request) -> Any:
    try:
        return await request.json()
    except Exception:
        raise HTTPException(
            http_status.HTTP_400_BAD_REQUEST, "Invalid JSON body"
        )


@router.get("/root/{rest:path}")
async def get_path(
    rest: str,
    service: InvestProjectsServiceDep,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Any:
    return await service.get_path(rest, db, user)


@router.put("/root/{rest:path}")
async def put_path(
    rest: str,
    request: Request,
    service: InvestProjectsServiceDep,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Any:
    body = await _parse_body(request)
    return await service.put_path(rest, body, db, user)


@router.patch("/root/{rest:path}")
async def patch_path(
    rest: str,
    request: Request,
    service: InvestProjectsServiceDep,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Any:
    body = await _parse_body(request)
    return await service.patch_path(rest, body, db, user)


@router.delete("/root/{rest:path}")
async def delete_path(
    rest: str,
    service: InvestProjectsServiceDep,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Any:
    return await service.delete_path(rest, db, user)
