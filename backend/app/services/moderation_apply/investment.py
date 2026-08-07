"""Investment (invest-projects storage) apply handler — Phase 0b.

Path-keyed RTDB-style JSON store. Реплеим сохранённую операцию (put/patch/delete)
через InvestProjectsService НИЖЕ гейта, автором = ПРЕДЛОЖИВШИЙ (save_doc пишет
его email; _enforce_path_scope пере-проверяет его область доступа). Операции
идемпотентны (put replace / patch merge / delete key), поэтому повтор применения
из очереди безопасен — дублей нет.

Submission shape:
  target_module    = "investment"
  target_entity_id = <rest path>
  proposed_value   = {"op": "put"|"patch"|"delete", "rest": <path>, "body": <any>}
"""
from __future__ import annotations

from sqlalchemy import select

from app.models.moderation import ModerationSubmission
from app.models.user import User
from app.services.invest_projects.service import InvestProjectsService
from app.services.moderation_service import register_apply_handler


async def apply(db, *, sub: ModerationSubmission, user: User) -> dict:
    if not sub.proposed_value:
        raise ValueError("proposed_value is empty")
    pv = dict(sub.proposed_value)
    op = str(pv.get("op") or "").lower()
    rest = pv.get("rest") or sub.target_entity_id
    if not rest:
        raise ValueError("investment apply requires 'rest' path")
    body = pv.get("body")

    proposer = (await db.execute(
        select(User).where(User.id == sub.proposer_user_id)
    )).scalar_one_or_none()
    author = proposer or user
    service = InvestProjectsService()

    if op == "put":
        await service.put_path(rest, body, db, author)
    elif op == "patch":
        await service.patch_path(rest, body, db, author)
    elif op == "delete":
        await service.delete_path(rest, db, author)
    else:
        raise ValueError(f"unknown investment op: {op!r}")
    return {"module": "investment", "op": op, "rest": rest}


register_apply_handler("investment", apply)
