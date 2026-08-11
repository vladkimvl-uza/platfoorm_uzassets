"""Пер-сущностный журнал изменений: кто/что/когда менял конкретную запись.

Доступен пользователю, у которого ЕСТЬ доступ к самой записи (проверяем по
компании записи через ensure_company_access) — внутрикомпанийная подотчётность
«кто менял» и есть цель фичи. НЕ полагаемся на «неугадываемость UUID»: id задач
и проектов раздаются в диплинках уведомлений/@-упоминаний, поэтому scope-гейт
обязателен, иначе внешний пользователь одной компании увидел бы, кто (email/роль)
и когда правил запись чужой компании.

Разрешён только ЯВНЫЙ allow-list типов (tasks/projects) — те, для которых мы
умеем резолвить компанию и применить scope. Всё прочее (пользователи, RBAC,
рейтинги, финансы и т.д.) — только в административном журнале /admin/audit
(право audit.view). Расширять allow-list — вместе с резолвером компании.

Отдаём только автора/действие/имена изменённых полей/время — без значений
(before/after) и без IP/user-agent. Полный админ-журнал — /admin/audit.
"""
from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi import status as http_status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.access import ensure_company_access, has_unrestricted_view
from app.core.security import get_current_user
from app.database import get_db
from app.models.project import Project
from app.models.task import Task
from app.models.user import User

router = APIRouter(prefix="/history", tags=["history"])

# Allow-list: тип сущности (сегмент коллекции URL, как его пишет
# AuditLoggerMiddleware) → ORM-модель с полем company_id для scope-проверки.
_ENTITY_MODELS = {
    "tasks": Task,
    "projects": Project,
}


@router.get("/{entity_type}/{entity_id}")
async def entity_change_history(
    entity_type: str,
    entity_id: str,
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[dict]:
    """История изменений записи (новые сверху): автор, действие, изменённые поля, когда.

    Доступ — только при наличии доступа к компании записи (иначе 403); типы вне
    allow-list закрыты (403 → смотреть в /admin/audit).
    """
    model = _ENTITY_MODELS.get(entity_type.lower())
    if model is None:
        raise HTTPException(
            http_status.HTTP_403_FORBIDDEN,
            "История этого типа записей доступна только в административном журнале "
            "аудита (/admin/audit, право audit.view)",
        )
    try:
        eid = UUID(str(entity_id))
    except (ValueError, TypeError):
        raise HTTPException(http_status.HTTP_404_NOT_FOUND, "Запись не найдена")

    company_id = (await db.execute(
        select(model.company_id).where(model.id == eid)
    )).scalar_one_or_none()
    if company_id is None:
        # Записи нет ЛИБО у неё нет компании: во втором случае историю видит только
        # владелец/полный доступ (companies.view_all). Не раскрываем разницу.
        row_exists = (await db.execute(
            select(model.id).where(model.id == eid)
        )).scalar_one_or_none()
        if row_exists is None or not has_unrestricted_view(user):
            raise HTTPException(http_status.HTTP_404_NOT_FOUND, "Запись не найдена")
    else:
        await ensure_company_access(db, user, company_id)  # 403 вне scope

    from app.services import audit_service as _svc
    return await _svc.entity_history(
        db, entity_type=entity_type.lower(), entity_id=str(entity_id), limit=limit,
    )
