"""Projects apply handler.

Раньше проекты (в отличие от задач) НЕ проходили модерационный гейт: ограниченный
пользователь, редактируя ЗАДАЧУ, попадал в очередь, а создавая/меняя/архивируя
ПРОЕКТ той же компании через тот же TaskProjectEditor — применял немедленно.
Роут projects.py теперь заворачивает мутации в gate_or_apply(module="projects");
этот обработчик применяет одобренную заявку.

Dispatch по sub.action:
  - "create" / "created"                 → POST /projects
  - "update" / "status_change" / "edit"  → PATCH /projects/{id}
  - "delete" / "archive" / "archived"    → DELETE /projects/{id}

Переиспользуем ProjectsEditorService (свой UoW), а не дублируем split extra-полей
и completed_at-логику — иначе апрув расходился бы с прямой правкой. Модератор
применяет БЕЗ scope-ограничения (scope_company_ids=None).
"""
from __future__ import annotations

from uuid import UUID

from app.database import AsyncSessionLocal
from app.models.moderation import ModerationSubmission
from app.models.user import User
from app.schemas.project import ProjectCreate, ProjectUpdate
from app.services.moderation_service import register_apply_handler
from app.services.projects.editor_service import ProjectsEditorService
from app.uow.impl import UnitOfWork


def _service() -> ProjectsEditorService:
    return ProjectsEditorService(uow=UnitOfWork(session_factory=AsyncSessionLocal))


def _entity_id(sub: ModerationSubmission) -> UUID:
    if not sub.target_entity_id:
        raise ValueError("missing target_entity_id")
    try:
        return UUID(sub.target_entity_id)
    except Exception as e:
        raise ValueError(f"invalid project id: {sub.target_entity_id}") from e


async def apply(db, *, sub: ModerationSubmission, user: User) -> dict:
    action = (sub.action or "").lower()
    service = _service()

    if action in ("create", "created"):
        if not sub.proposed_value:
            raise ValueError("proposed_value is empty")
        payload = ProjectCreate.model_validate(sub.proposed_value)
        detail, _info = await service.create_project(payload, creator_id=user.id)
        return {"action": "create", "project_id": str(detail.id)}

    if action in ("update", "status_change", "edit"):
        if not sub.proposed_value:
            raise ValueError("proposed_value is empty")
        pid = _entity_id(sub)
        payload = ProjectUpdate.model_validate(sub.proposed_value)
        # Модератор применяет без scope-ограничения.
        await service.update_project(pid, payload, scope_company_ids=None)
        return {"action": "update", "project_id": str(pid)}

    if action in ("delete", "archive", "archived"):
        pid = _entity_id(sub)
        await service.archive_project(pid, scope_company_ids=None)
        return {"action": "archive", "project_id": str(pid)}

    raise ValueError(f"unknown projects action: {action!r}")


register_apply_handler("projects", apply)
