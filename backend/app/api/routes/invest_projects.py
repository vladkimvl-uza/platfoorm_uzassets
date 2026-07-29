"""Pack 8.0 — Invest Projects legacy store-RTDB storage — thin HTTP shim
(refactored 2026-05-25).

Routes:
    GET    /invest-projects-storage/root/{path}.json   read at nested path
    PUT    /invest-projects-storage/root/{path}.json   replace
    PATCH  /invest-projects-storage/root/{path}.json   shallow-merge
    DELETE /invest-projects-storage/root/{path}.json   remove key

Scope (C3b): scoped users see only `companies/<own_code>/...`; owner +
`companies.view_all` — unrestricted. Root-DELETE refused as safety.

Права: `investment.view` — чтение, `investment.edit` — запись. Скоуп по
компаниям (_enforce_path_scope) остаётся нетронутым: право отвечает на вопрос
«пускать ли в модуль», скоуп — «к чьим данным».
"""
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi import status as http_status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import require_permission
from app.database import get_db
from app.dependencies.invest_projects import InvestProjectsServiceDep
from app.models.user import User

router = APIRouter(
    prefix="/invest-projects-storage", tags=["invest-projects-storage"]
)

# До этой правки хранилище инвест-проектов проверяло только аутентификацию и
# скоуп по компании: право `investment.view` жило лишь в meta роута фронта, а
# запись мог выполнить любой пользователь со скоупом — включая роль viewer,
# у которой есть только `investment.view`. Теперь право модуля проверяется на
# сервере, и чтение отделено от записи.
_require_investment_view = require_permission("investment.view")
_require_investment_edit = require_permission("investment.edit")


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
    user: User = Depends(_require_investment_view),
) -> Any:
    return await service.get_path(rest, db, user)


@router.put("/root/{rest:path}")
async def put_path(
    rest: str,
    request: Request,
    service: InvestProjectsServiceDep,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(_require_investment_edit),
) -> Any:
    body = await _parse_body(request)
    return await service.put_path(rest, body, db, user)


@router.patch("/root/{rest:path}")
async def patch_path(
    rest: str,
    request: Request,
    service: InvestProjectsServiceDep,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(_require_investment_edit),
) -> Any:
    body = await _parse_body(request)
    return await service.patch_path(rest, body, db, user)


@router.delete("/root/{rest:path}")
async def delete_path(
    rest: str,
    service: InvestProjectsServiceDep,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(_require_investment_edit),
) -> Any:
    return await service.delete_path(rest, db, user)
