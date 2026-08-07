"""Moderation API — thin HTTP layer (refactored 2026-05-25).

State transitions (approve/reject/withdraw/retry-apply/etc)
continue to delegate to the existing core `app/services/moderation_service.py`
(aliased as `svc` here) — that module is the gate-or-apply engine used by
all other route files, do not break its contract.

UI dashboard queries + user flags live in the new `moderation_admin/` services
(with backing ModerationRepository). Конструктор правил удалён — политика
модерации встроена в moderation_service.
"""
from __future__ import annotations

from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import get_current_user, require_permission
from app.database import get_db
from app.dependencies.moderation import (
    ModerationQueryServiceDep,
    ModerationRulesServiceDep,
)
from app.models.moderation import (
    MODERATABLE_ACTIONS,
    MODERATABLE_MODULES,
    ModerationSubmission,
)
from app.models.user import User
from app.schemas.moderation import (
    ActionInfo,
    CatalogResponse,
    CommentCreate,
    CommentRead,
    ModerationOverview,
    ModuleInfo,
    SubmissionCreate,
    SubmissionListResponse,
    SubmissionRead,
    SubmissionResolve,
)
from app.services import moderation_service as svc

router = APIRouter(prefix="/moderation", tags=["moderation"])


# ─── Overview / Catalog ───────────────────────────────────────────

async def _is_reviewer(db: AsyncSession, sub, user: User) -> bool:
    """Может ли этот человек РАЗБИРАТЬ заявку (видеть внутреннее, решать).

    Одно определение на весь роутер. Раньше их было три разных: карточка
    заявки (:143) уже пускала держателя `moderation.review` и reviewer_ids, а
    комментарии — только владельца/assigned/coapprover. При штатной
    маршрутизации assigned и coapprover пусты, поэтому модератор получал 403 на
    комментариях, фронт грузил их вместе с заявкой одним Promise.all — и
    карточка не открывалась вовсе.
    """
    from app.core.security import has_effective_permission
    if user.is_owner:
        return True
    if sub.assigned_moderator_id == user.id or sub.coapprover_id == user.id:
        return True
    if any(str(x) == str(user.id) for x in (sub.reviewer_ids or [])):
        return True
    return await has_effective_permission(db, user, "moderation.review")


async def _read(db: AsyncSession, sub, user: User) -> SubmissionRead:
    """SubmissionRead + вычисленный для этого пользователя can_resolve.

    can_resolve = ревьюер ЭТОЙ заявки И заявка в его области компаний. Без
    scope кнопки «Принять/Отклонить» показывались бы модератору из общего пула
    и для чужих компаний, а backend всё равно вернул бы 403 при клике.
    """
    out = SubmissionRead.model_validate(sub)
    out.can_resolve = (
        await _is_reviewer(db, sub, user)
        and await svc.in_resolve_scope(db, sub, user)
    )
    return out


@router.get("/overview", response_model=ModerationOverview)
async def overview(
    service: ModerationQueryServiceDep,
    user: User = Depends(require_permission("moderation.review")),
):
    return await service.overview(user_id=user.id)


@router.get("/catalog", response_model=CatalogResponse)
async def catalog(_u: User = Depends(get_current_user)):
    return CatalogResponse(
        modules=[ModuleInfo(**m) for m in MODERATABLE_MODULES],
        actions=[ActionInfo(**a) for a in MODERATABLE_ACTIONS],
    )


# ─── Submissions queue ────────────────────────────────────────────

@router.get("/queue", response_model=SubmissionListResponse)
async def queue(
    service: ModerationQueryServiceDep,
    status: Optional[list[str]] = Query(None),
    assigned_to: Optional[str] = Query(None),  # "me" | user_id
    module: Optional[str] = Query(None),
    proposer_user_id: Optional[UUID] = Query(None),
    page: int = Query(1, ge=1),
    per_page: int = Query(30, ge=1, le=100),
    # Очередь висела на голом get_current_user: её читал ЛЮБОЙ вошедший,
    # включая самого внешнего автора — вместе с diff_summary всех 22 компаний
    # и досье на коллег. Своя лента автора живёт отдельно (/my-submissions).
    user: User = Depends(require_permission("moderation.review")),
):
    return await service.list_queue(
        status_in=status, assigned_to=assigned_to,
        module=module, proposer_user_id=proposer_user_id,
        page=page, per_page=per_page, actor_id=user.id,
    )


@router.get("/my-submissions", response_model=SubmissionListResponse)
async def my_submissions(
    service: ModerationQueryServiceDep,
    status: Optional[list[str]] = Query(None),
    page: int = Query(1, ge=1),
    per_page: int = Query(30, ge=1, le=100),
    user: User = Depends(get_current_user),
):
    return await service.list_my_submissions(
        actor_id=user.id, status_in=status,
        page=page, per_page=per_page,
    )


@router.post("/submissions", response_model=SubmissionRead, status_code=status.HTTP_201_CREATED)
async def create_submission(
    body: SubmissionCreate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("moderation.submit")),
):
    sub = await svc.create_submission(
        db,
        proposer=user,
        target_module=body.target_module,
        target_entity_id=body.target_entity_id,
        target_entity_label=body.target_entity_label,
        target_field=body.target_field,
        target_company_id=body.target_company_id,
        target_sector_id=body.target_sector_id,
        action=body.action,
        proposed_value=body.proposed_value,
        original_value=body.original_value,
        diff_summary=body.diff_summary,
        attachments=body.attachments,
        reason=body.reason,
        source_ip=request.client.host if request.client else None,
        source_user_agent=request.headers.get("user-agent"),
    )
    return await _read(db, sub, user)


@router.get("/submissions/{submission_id}", response_model=SubmissionRead)
async def get_submission(
    submission_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    sub = await db.get(ModerationSubmission, submission_id)
    if not sub:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Not found")
    # Держатель moderation.review и назначенные через reviewer_ids раньше сюда
    # не попадали: очередь показывала заявку, а по клику приходил 403. Особенно
    # больно после снятия модератора — его заявки не мог разобрать НИКТО, кроме
    # владельца, а срока годности у заявки нет.
    allowed = (
        sub.proposer_user_id == user.id
        or await _is_reviewer(db, sub, user)
    )
    if not allowed:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "No access")
    return await _read(db, sub, user)


# ─── Submission state transitions ─────────────────────────────────

async def _load_sub(db: AsyncSession, submission_id: UUID):
    sub = await db.get(ModerationSubmission, submission_id)
    if not sub:
        raise HTTPException(404, "Not found")
    return sub


def _wrap_state_change(coro):
    """Run a coro and convert PermissionError → 403, ValueError → 409."""
    async def runner():
        try:
            return await coro
        except PermissionError as e:
            raise HTTPException(403, str(e))
        except ValueError as e:
            raise HTTPException(status.HTTP_409_CONFLICT, str(e))
    return runner()


@router.post("/submissions/{submission_id}/approve", response_model=SubmissionRead)
async def approve_submission(
    submission_id: UUID,
    body: SubmissionResolve,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("moderation.review")),
):
    sub = await _load_sub(db, submission_id)
    result = await _wrap_state_change(svc.approve(db, sub=sub, user=user, note=body.note))
    return await _read(db, result, user)


@router.post("/submissions/{submission_id}/reject", response_model=SubmissionRead)
async def reject_submission(
    submission_id: UUID,
    body: SubmissionResolve,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("moderation.review")),
):
    sub = await _load_sub(db, submission_id)
    result = await _wrap_state_change(svc.reject(db, sub=sub, user=user, note=body.note))
    return await _read(db, result, user)


@router.post("/submissions/{submission_id}/set-review", response_model=SubmissionRead)
async def set_review_submission(
    submission_id: UUID,
    body: SubmissionResolve,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("moderation.review")),
):
    sub = await _load_sub(db, submission_id)
    result = await _wrap_state_change(svc.set_review(db, sub=sub, user=user, note=body.note))
    return await _read(db, result, user)


# «Изменить и принять» удалено (решение владельца 03.08.2026): модератор правил
# proposed_value сырым JSON — для нетехнического согласующего это тупик, а
# молчаливая правка чужого предложения подменяла авторство. Решение теперь
# бинарное: принять как есть или отклонить с комментарием, чтобы автор прислал
# исправленный вариант. Метод svc.edit_and_approve оставлен в сервисе —
# он не вызывается из API.

@router.post("/submissions/{submission_id}/retry-apply", response_model=SubmissionRead)
async def retry_apply_submission(
    submission_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("moderation.review")),
):
    sub = await _load_sub(db, submission_id)
    if sub.status != "approved":
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"Only approved submissions can be re-applied (current: {sub.status})",
        )
    # Повтор применения — это ещё одна запись в целевой модуль, поэтому здесь
    # нужны те же гарантии, что и у approve:
    #  • право решать по ЭТОЙ заявке (единственное место, где виден
    #    персональный отзыв moderation.review — has_effective_permission для
    #    роли admin выходит раньше любых deny);
    #  • запрет на повтор уже применённой заявки: старый payload прогонял
    #    delete-and-replace и откатывал всё, что ввели после одобрения.
    if not await _is_reviewer(db, sub, user):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Not authorized to resolve this submission")
    from app.services import moderation_authority
    if await moderation_authority.review_denied(db, user):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Not authorized to resolve this submission")
    # Та же scope-проверка, что и в approve: повтор применения — это запись в
    # целевую компанию, модератор из общего пула не должен писать в чужую.
    if not await svc.in_resolve_scope(db, sub, user):
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "Not authorized to resolve this submission (out of company scope)",
        )
    if (sub.apply_status or "") == "applied":
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Заявка уже применена — повторное применение перезапишет данные "
            "старым значением",
        )
    await svc._dispatch_apply(db, sub, user)
    await db.refresh(sub)
    return await _read(db, sub, user)


@router.post("/submissions/{submission_id}/withdraw", response_model=SubmissionRead)
async def withdraw_submission(
    submission_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    sub = await _load_sub(db, submission_id)
    result = await _wrap_state_change(svc.withdraw(db, sub=sub, user=user))
    return await _read(db, result, user)


# ─── Comments ─────────────────────────────────────────────────────

@router.get("/submissions/{submission_id}/comments", response_model=list[CommentRead])
async def list_comments(
    submission_id: UUID,
    service: ModerationRulesServiceDep,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    sub = await service.get_submission_for_access(submission_id)
    if not sub:
        raise HTTPException(404, "Not found")
    is_moderator = await _is_reviewer(db, sub, user)
    is_proposer = sub.proposer_user_id == user.id
    if not (is_moderator or is_proposer):
        raise HTTPException(403, "No access")
    return await service.list_comments(submission_id, include_internal=is_moderator)


@router.post("/submissions/{submission_id}/comments", response_model=CommentRead,
             status_code=status.HTTP_201_CREATED)
async def add_comment(
    submission_id: UUID,
    body: CommentCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    sub = await _load_sub(db, submission_id)
    is_moderator = await _is_reviewer(db, sub, user)
    is_proposer = sub.proposer_user_id == user.id
    if not (is_moderator or is_proposer):
        raise HTTPException(403, "No access")
    if body.is_internal and not is_moderator:
        raise HTTPException(403, "Only moderators can post internal comments")

    c = await svc.add_comment(
        db, sub=sub, user=user, text=body.text,
        attachments=body.attachments, is_internal=body.is_internal,
    )
    return CommentRead.model_validate(c)


# ─── Правила удалены (решение владельца 03.08.2026) ───────────────
# Конструктор правил (37 настроек на правило) заменён встроенной политикой в
# moderation_service: модерируются внешние пользователи, согласует любой
# держатель moderation.review. Настраивать нечего — и сломать нечего.
# Эндпоинты /moderation/rules* сняты вместе с экраном настройки.

# ─── Moderators / External users sub-tabs ─────────────────────────

@router.get("/moderators")
async def list_moderators(
    service: ModerationQueryServiceDep,
    _u: User = Depends(require_permission("admin.users")),
):
    return {"items": await service.list_moderators()}


@router.get("/moderators/removed")
async def list_removed_moderators(
    service: ModerationQueryServiceDep,
    _u: User = Depends(require_permission("admin.users")),
):
    return {"items": await service.list_removed_moderators()}


@router.delete("/moderators/{user_id}")
async def remove_moderator(
    user_id: UUID,
    service: ModerationRulesServiceDep,
    user: User = Depends(require_permission("admin.users")),
):
    """Убрать человека из модераторов (право согласования отзывается персонально)."""
    return await service.set_moderator(user_id, active=False, actor=user)


@router.post("/moderators/{user_id}")
async def restore_moderator(
    user_id: UUID,
    service: ModerationRulesServiceDep,
    user: User = Depends(require_permission("admin.users")),
):
    """Вернуть человека в модераторы. Обратная операция к удалению —
    без неё снятие было бы необратимым: выдать `moderation.review` сеткой
    «Доступ к модулям» нельзя, этого кода в сетке нет."""
    return await service.set_moderator(user_id, active=True, actor=user)


@router.get("/submitted-users")
async def list_submitted_users(
    service: ModerationQueryServiceDep,
    # Список внешних авторов с их почтой, должностью, организацией и флагом
    # обхода модерации — административные данные, не для всех вошедших.
    _u: User = Depends(require_permission("admin.users")),
):
    return {"items": await service.list_external_users()}


@router.patch("/users/{user_id}/flags")
async def patch_user_flags(
    user_id: UUID,
    body: dict,
    service: ModerationRulesServiceDep,
    _u: User = Depends(require_permission("admin.users")),
):
    return await service.patch_user_flags(user_id, body)


# ─── Настраиваемая политика модерации (Фаза 3) ────────────────────
# Какие модули модерируются — конфиг, а не хардкод. Капабилити (какие модули
# ВООБЩЕ можно включить) — в коде (бакет A + apply-хендлер), из UI не выносится.

@router.get("/policy")
async def get_moderation_policy(
    db: AsyncSession = Depends(get_db),
    _u: User = Depends(require_permission("admin.users")),
):
    from app.services import moderation_config
    return await moderation_config.get_policy(db)


@router.patch("/policy")
async def set_moderation_policy(
    body: dict,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("admin.users")),
):
    from app.services import moderation_config
    mods = body.get("enabled_modules")
    if not isinstance(mods, list):
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, "enabled_modules (list) required",
        )
    return await moderation_config.set_enabled_modules(
        db, mods, actor_email=user.email, actor_id=str(user.id),
    )
