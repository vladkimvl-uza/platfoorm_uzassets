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
from typing import Any, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi import status as http_status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import require_permission
from app.database import get_db
from app.dependencies.invest_projects import InvestProjectsServiceDep
from app.models.company import Company
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


async def _company_id_for_parts(db: AsyncSession, parts: list[str]) -> Optional[UUID]:
    """id компании из пути `companies/<code>/...` (для scope модератора на
    resolve). Вне ветки companies → None (такие пути доступны только
    unrestricted-юзерам, которых scope не ограничивает)."""
    if len(parts) >= 2 and parts[0] == "companies" and parts[1]:
        return (await db.execute(
            select(Company.id).where(func.lower(Company.code) == str(parts[1]).lower())
        )).scalar_one_or_none()
    return None


async def _gate_invest(
    db: AsyncSession, user: User, service, rest: str, op: str, body: Any,
):
    """Модерация записи в invest-store. Возвращает (queued, sub). Область АВТОРА
    (_enforce_path_scope) проверяется ДО гейта — иначе внешний автор queue'ил бы
    запись вне своей ветки companies/<code>/."""
    parts = service.parse_path(rest)
    await service._enforce_path_scope(db, user, parts)
    company_id = await _company_id_for_parts(db, parts)
    from app.services.moderation_service import gate_or_apply
    action = "delete" if op == "delete" else "edit"
    return await gate_or_apply(
        db, user=user, module="investment", action=action,
        entity_id=rest, entity_label=f"Инвест-данные: {rest}",
        company_id=company_id, sector_id=None, year=None,
        payload={"op": op, "rest": rest, "body": body},
        diff_summary=f"Инвест-проекты: {op} {rest}",
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
    queued, sub = await _gate_invest(db, user, service, rest, "put", body)
    if queued:
        return {"queued": True, "submission_id": str(sub.id), "status": sub.status}
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
    queued, sub = await _gate_invest(db, user, service, rest, "patch", body)
    if queued:
        return {"queued": True, "submission_id": str(sub.id), "status": sub.status}
    return await service.patch_path(rest, body, db, user)


@router.delete("/root/{rest:path}")
async def delete_path(
    rest: str,
    service: InvestProjectsServiceDep,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(_require_investment_edit),
) -> Any:
    queued, sub = await _gate_invest(db, user, service, rest, "delete", None)
    if queued:
        return {"queued": True, "submission_id": str(sub.id), "status": sub.status}
    return await service.delete_path(rest, db, user)
