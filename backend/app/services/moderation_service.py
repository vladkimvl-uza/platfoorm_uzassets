"""Moderation service (Pack 11.1).

Responsibilities:
  1. `match_rule()`        — find the highest-priority rule that matches a submission context
  2. `create_submission()` — entry point for write-intercept
  3. `approve / reject / set_review / edit_and_approve / withdraw` — resolution helpers
  4. `add_comment`         — discussion thread
  5. Notification fan-out via app.services.notifications_service.notify()
"""
from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from typing import Any, Optional
from uuid import UUID

from sqlalchemy import and_, func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.moderation import (
    ModerationComment,
    ModerationRule,
    ModerationSubmission,
)
from app.models.user import Group, Role, User
from app.services.notifications_service import notify

log = logging.getLogger(__name__)


# ════════════════════════════════════════════════════════════
#   Action vocabulary normalization
# ════════════════════════════════════════════════════════════
# Роутеры исторически шлют свой словарь действий (update / created /
# status_changed / replace_year / upsert_data …), а каталог MODERATABLE_ACTIONS
# и UI правил оперируют каноническими кодами (edit / replace / comment /
# upload / delete / status_change / create). Без нормализации правило с
# action="edit" НИКОГДА не совпадало с роутовым "update" — пересечение было
# только по "delete". Приводим обе стороны к канону перед сравнением.
_ACTION_ALIASES: dict[str, str] = {
    # edit-семейство
    "update": "edit",
    "update_company": "edit",
    "update_issue": "edit",
    "update_member": "edit",
    "upsert_data": "edit",
    "upsert_metric": "edit",
    # ESG SWOT: без алиасов канон не совпадал с MODERATED_ACTIONS, и правки/
    # удаления выводов у внешних авторов проходили МИМО модерации.
    "upsert_swot": "edit",
    "delete_swot": "delete",
    "bulk_upsert": "edit",
    "auto_aligned": "edit",
    "save_report": "edit",
    "security_flag": "edit",
    # create-семейство
    "created": "create",
    "create_issue": "create",
    "create_member": "create",
    # status
    "status_changed": "status_change",
    "result_cleared": "status_change",
    # delete-семейство
    "archived": "delete",
    # replace-семейство
    "replace_year": "replace",
}


def _canon_action(a: Optional[str]) -> Optional[str]:
    """Map a route-emitted action onto its canonical catalog code."""
    if a is None:
        return None
    return _ACTION_ALIASES.get(a, a)


# ════════════════════════════════════════════════════════════
#   Rule matcher
# ════════════════════════════════════════════════════════════

def _eval_condition(payload: dict[str, Any], atom: dict[str, Any]) -> bool:
    """Evaluate one threshold condition against the payload."""
    field = atom.get("field")
    op = atom.get("op")
    expected = atom.get("value")

    if not field or not op:
        return True

    actual = payload.get(field) if isinstance(payload, dict) else None

    # Sub-field path like "proposed.amount"
    if "." in (field or ""):
        cur = payload
        for k in field.split("."):
            if not isinstance(cur, dict):
                cur = None; break
            cur = cur.get(k)
        actual = cur

    try:
        if op == "=":          return actual == expected
        if op == "!=":         return actual != expected
        if op == ">":          return actual is not None and float(actual) >  float(expected)
        if op == ">=":         return actual is not None and float(actual) >= float(expected)
        if op == "<":          return actual is not None and float(actual) <  float(expected)
        if op == "<=":         return actual is not None and float(actual) <= float(expected)
        if op == "in":         return actual in (expected or [])
        if op == "not_in":     return actual not in (expected or [])
        if op == "abs>":       return actual is not None and abs(float(actual)) > float(expected)
        if op == "delta>":
            # Requires both proposed and original
            p = payload.get("proposed_value", {}) if isinstance(payload, dict) else {}
            o = payload.get("original_value", {}) if isinstance(payload, dict) else {}
            try:
                base = float(o.get(field, 0) or 0)
                new  = float(p.get(field, 0) or 0)
                if base == 0:
                    return new != 0
                return abs((new - base) / base) * 100 > float(expected)
            except Exception:
                return False
    except (TypeError, ValueError):
        return False
    return False



# ════════════════════════════════════════════════════════════
#   ВСТРОЕННАЯ ПОЛИТИКА МОДЕРАЦИИ (решение владельца 03.08.2026)
# ════════════════════════════════════════════════════════════
# Конструктор правил удалён. Он давал 37 настроек на правило (кто, что, где,
# когда, пороги, двойное согласование, эскалации, авто-одобрение, срок
# годности) — при том что за всё время создали три правила, все три названы
# «Новое правило», и все три настроены одинаково: «внешние пользователи, все
# модули, все действия». Настраивать было нечего, а сломать — легко.
#
# Правило теперь одно и живёт в коде:
#   КОГО  — пользователи с флагом «внешний» (users.is_external);
#   ЧТО   — изменения данных в модулях ниже;
#   КТО   — согласует любой держатель права moderation.review (и владелец);
#   КАК   — одно решение, без второго согласующего, эскалаций и таймеров.
#
# Исключения (пишут напрямую): владелец, users.bypass_moderation,
# держатель права moderation.bypass — как и раньше.

MODERATED_MODULES: frozenset[str] = frozenset({
    "tasks", "projects", "comments", "kpi", "financials", "business_plan",
    "esg", "governance", "ratings", "procurement", "production", "credit",
    "investment", "unit_cost", "companies",
})

MODERATED_ACTIONS: frozenset[str] = frozenset({
    "edit", "replace", "delete", "status_change", "upload", "comment",
})


def should_moderate(user: User, module: str, action: str) -> bool:
    """Нужно ли отправить правку на согласование. Одно понятное правило."""
    if not getattr(user, "is_external", False):
        return False
    if module not in MODERATED_MODULES:
        return False
    return _canon_action(action) in MODERATED_ACTIONS


async def moderator_ids(db: AsyncSession) -> list[UUID]:
    """Кто может решать по заявкам: владельцы + держатели moderation.review.

    Раньше согласующий был полем в правиле, поэтому без правила заявку не мог
    закрыть никто, кроме владельца. Теперь источник один — RBAC, как и во всём
    остальном продукте. Сам расчёт — в `moderation_authority`: он учитывает и
    персональный грант, и персональный отзыв права, чего этот SQL не делал.
    """
    from app.services import moderation_authority
    return await moderation_authority.moderator_ids(db)


async def resolve_moderators(
    db: AsyncSession, proposer: User,
) -> tuple[list[UUID], str]:
    """Кому уходит заявка этого автора. Возвращает (id согласующих, маршрут).

    Порядок ровно такой, потому что частное всегда должно бить общее:

    1. ``users.moderator_ids`` — согласующие, выбранные лично при создании или
       редактировании пользователя. Если заданы, работают только они.
    2. Куратор сектора — внутренний пользователь, у которого в
       ``moderated_sector_codes`` стоит сектор компании автора. Так «авторы из
       компаний такого-то сектора» попадают к своему внутреннему согласующему.
    3. Общий фолбэк — владельцы и держатели `moderation.review`.

    Фолбэк обязателен: иначе заявка с выключенным/удалённым согласующим
    зависла бы навсегда, а таких «тихих зависаний» мы уже наелись.
    """
    from app.services import moderation_authority

    # Персональные согласующие и кураторы секторов лежат в JSONB-полях
    # пользователя и НЕ пересчитываются, когда у человека забирают право
    # согласования. Поэтому оба списка прогоняем через тот же предикат, что
    # строит список модераторов: снятый согласующий выпадает, и заявка идёт
    # дальше по цепочке, а не повисает на том, кому approve вернёт 403.
    explicit = [x for x in (getattr(proposer, "moderator_ids", None) or []) if x]
    if explicit:
        rows = await moderation_authority.filter_moderators(db, explicit)
        if rows:
            return list(rows), "explicit"

    if proposer.organization_id:
        rows = (await db.execute(text(f"""
            SELECT DISTINCT u.id
            FROM users u
            JOIN companies c ON c.id = CAST(:org AS uuid)
            JOIN sectors s   ON s.id = c.sector_id
            WHERE NOT u.is_external
              AND u.id <> CAST(:self AS uuid)
              AND u.moderated_sector_codes IS NOT NULL
              AND u.moderated_sector_codes ? s.code
              AND {moderation_authority.moderator_predicate('u')}
        """), {
            **moderation_authority.PARAMS,
            "org": str(proposer.organization_id),
            "self": str(proposer.id),
        })).scalars().all()
        if rows:
            return list(rows), "sector"

    return list(await moderator_ids(db)), "fallback"


async def _user_matches(
    db: AsyncSession, user: User, rule: ModerationRule,
) -> bool:
    """Check whether the user satisfies rule's WHO criteria."""
    matched_who = False

    if rule.trigger_user_ids and str(user.id) in [str(x) for x in rule.trigger_user_ids]:
        matched_who = True
    if not matched_who and rule.trigger_is_external and user.is_external:
        matched_who = True
    if not matched_who and rule.trigger_group_codes:
        rows = (await db.execute(
            select(func.count()).select_from(
                select(1).select_from(Group)
                .join(Group.users)
                .where(and_(User.id == user.id, Group.code.in_(rule.trigger_group_codes)))
                .subquery(),
            ),
        )).scalar() or 0
        if rows > 0:
            matched_who = True
    if not matched_who and rule.trigger_role_codes:
        rows = (await db.execute(
            select(func.count()).select_from(
                select(1).select_from(Role)
                .join(Role.users)
                .where(and_(User.id == user.id, Role.code.in_(rule.trigger_role_codes)))
                .subquery(),
            ),
        )).scalar() or 0
        if rows > 0:
            matched_who = True

    # If no WHO criteria specified at all → applies to everyone
    if not any([
        rule.trigger_user_ids, rule.trigger_is_external,
        rule.trigger_group_codes, rule.trigger_role_codes,
    ]):
        matched_who = True
    return matched_who


async def match_rule(
    db: AsyncSession,
    *,
    user: User,
    module: str,
    action: str,
    company_id: Optional[UUID] = None,
    sector_id: Optional[UUID] = None,
    year: Optional[int] = None,
    payload: Optional[dict[str, Any]] = None,
) -> Optional[ModerationRule]:
    """Return highest-priority active rule that matches, or None."""
    rules = (await db.execute(
        select(ModerationRule)
        .where(ModerationRule.is_active.is_(True))
        .order_by(ModerationRule.sort_order.asc(), ModerationRule.created_at.asc()),
    )).scalars().all()

    payload = payload or {}

    for rule in rules:
        # WHO
        if not await _user_matches(db, user, rule):
            continue

        # WHAT
        if rule.trigger_modules and module not in rule.trigger_modules:
            continue

        # WHERE
        if rule.trigger_company_ids and (not company_id or str(company_id) not in [str(x) for x in rule.trigger_company_ids]):
            continue
        if rule.trigger_sector_ids and (not sector_id or str(sector_id) not in [str(x) for x in rule.trigger_sector_ids]):
            continue
        if rule.trigger_year_from is not None and (year is None or year < rule.trigger_year_from):
            continue
        if rule.trigger_year_to is not None and (year is None or year > rule.trigger_year_to):
            continue

        # ACTION (canonicalize both sides — see _ACTION_ALIASES)
        if rule.trigger_actions:
            allowed = {_canon_action(x) for x in rule.trigger_actions}
            if _canon_action(action) not in allowed:
                continue

        # THRESHOLDS
        if rule.trigger_conditions:
            atoms = rule.trigger_conditions
            if not all(_eval_condition(payload, a) for a in atoms):
                continue

        return rule
    return None


# ════════════════════════════════════════════════════════════
#   Submission lifecycle
# ════════════════════════════════════════════════════════════

async def create_submission(
    db: AsyncSession,
    *,
    proposer: User,
    target_module: str,
    target_entity_id: Optional[str] = None,
    target_entity_label: Optional[str] = None,
    target_field: Optional[str] = None,
    target_company_id: Optional[UUID] = None,
    target_sector_id: Optional[UUID] = None,
    action: str = "edit",
    proposed_value: Optional[dict[str, Any]] = None,
    original_value: Optional[dict[str, Any]] = None,
    diff_summary: Optional[str] = None,
    attachments: Optional[list[dict[str, Any]]] = None,
    reason: Optional[str] = None,
    source_ip: Optional[str] = None,
    source_user_agent: Optional[str] = None,
    year: Optional[int] = None,
) -> ModerationSubmission:
    """Create a pending submission, match a rule, assign moderator, fire notifications."""
    rule = await match_rule(
        db, user=proposer, module=target_module, action=action,
        company_id=target_company_id, sector_id=target_sector_id, year=year,
        payload={
            "proposed_value": proposed_value or {},
            "original_value": original_value or {},
            **(proposed_value or {}),
        },
    )

    now = datetime.now(UTC)
    sub = ModerationSubmission(
        created_at=now, updated_at=now,
        proposer_user_id=proposer.id,
        proposer_is_external=bool(proposer.is_external),
        target_module=target_module,
        target_entity_id=target_entity_id,
        target_entity_label=target_entity_label,
        target_field=target_field,
        target_company_id=target_company_id,
        target_sector_id=target_sector_id,
        action=action,
        proposed_value=proposed_value,
        original_value=original_value,
        diff_summary=diff_summary,
        attachments=attachments,
        reason=reason,
        status="pending",
        approvals_given=[],
        source_ip=source_ip,
        source_user_agent=source_user_agent,
    )

    # Маршрутизация: персональные согласующие → куратор сектора → общий пул.
    routed, route_kind = await resolve_moderators(db, proposer)
    if routed:
        sub.reviewer_ids = [str(x) for x in routed]
        sub.assigned_moderator_id = routed[0] if route_kind != "fallback" else None

    if rule:
        sub.rule_id = rule.id
        sub.assigned_moderator_id = rule.moderator_primary_id
        sub.coapprover_id          = rule.moderator_coapprover_id
        sub.approval_mode          = rule.approval_mode
        sub.expires_at             = now + timedelta(days=rule.expire_after_days)

        rule.total_matches    += 1
        rule.last_matched_at   = now

    db.add(sub)
    await db.commit()
    await db.refresh(sub)

    # Fan out notifications
    await _notify_on_create(db, sub, rule)
    return sub


async def _notify_on_create(
    db: AsyncSession, sub: ModerationSubmission, rule: Optional[ModerationRule],
) -> None:
    """Notify moderator(s) about a new pending submission."""
    title = f"Новое предложение: {sub.target_entity_label or sub.target_module}"
    body  = sub.diff_summary or (sub.reason or "Открыть в очереди модерации")
    body_is_fallback = not sub.diff_summary and not sub.reason
    link  = f"/admin/moderation?sub_tab=queue&open={sub.id}"

    # Очередь общая: уведомляем всех, кто вправе её разбирать. Раньше письмо
    # уходило одному согласующему из правила — если он в отпуске, заявка висела.
    # Если заявка смаршрутизирована (персональные согласующие или куратор
    # сектора) — пишем только им; иначе общий пул, как раньше.
    routed = [UUID(str(x)) for x in (sub.reviewer_ids or []) if x]
    recipients: list[UUID] = routed or list(await moderator_ids(db))
    if sub.assigned_moderator_id:
        recipients.append(sub.assigned_moderator_id)

    payload = {
        "submission_id": str(sub.id),
        "proposer_id":   str(sub.proposer_user_id),
        "is_external":   sub.proposer_is_external,
        "module":        sub.target_module,
        "action":        sub.action,
    }

    for uid in set(recipients):
        await notify(
            db, recipient_id=uid,
            type="moderation.pending",
            title=title, body=body,
            title_template="Новое предложение: {entity}",
            body_template=("Открыть в очереди модерации" if body_is_fallback else None),
            template_vars={"entity": sub.target_entity_label or sub.target_module},
            priority="high",
            link_url=link,
            payload=payload,
            source_module="moderation",
            source_entity_id=str(sub.id),
            source_user_id=sub.proposer_user_id,
        )

    sub.last_notified_at = datetime.now(UTC)
    await db.commit()


def _can_resolve(sub: ModerationSubmission, user: User) -> bool:
    """Решать по заявке может владелец или держатель moderation.review.

    Раньше проверялось поле правила (assigned_moderator_id / coapprover_id) —
    поэтому без правила заявку не мог закрыть НИКТО, кроме владельца, а очередь
    у остальных модераторов была «только посмотреть». Теперь право одно и то же,
    что открывает саму очередь.
    """
    if user.is_owner:
        return True
    try:
        from app.core.security import _user_permission_codes
        if "moderation.review" in _user_permission_codes(user):
            return True
    except Exception:  # noqa: BLE001 — не роняем решение из-за резолва прав
        pass
    # Согласующий, назначенный маршрутизацией (персонально или как куратор
    # сектора), решает по своей заявке — иначе назначение было бы формальным.
    if sub.assigned_moderator_id and sub.assigned_moderator_id == user.id:
        return True
    if any(str(x) == str(user.id) for x in (sub.reviewer_ids or [])):
        return True
    if sub.coapprover_id and sub.coapprover_id == user.id:
        return True
    return False


# followup A5: terminal statuses cannot be re-resolved. Helper raises
# ValueError so routes can map to 409 CONFLICT.
TERMINAL_STATUSES = ("approved", "rejected", "withdrawn", "expired", "cancelled")


def _guard_open(sub: ModerationSubmission) -> None:
    if sub.status in TERMINAL_STATUSES:
        raise ValueError(
            f"Submission already in terminal status '{sub.status}' and cannot be re-resolved",
        )


async def _lock_and_reload(db, sub: ModerationSubmission) -> ModerationSubmission:
    """Re-fetch the submission with SELECT ... FOR UPDATE so concurrent
    approve/reject calls serialize. Without this, two moderators clicking
    "approve" within the same second both pass `_guard_open` (which only
    looks at the Python object state) and both write status='approved',
    causing duplicate _dispatch_apply / rule-counter increments / notifications.

    Returns a refreshed instance with the current DB status. After this
    returns, `_guard_open(refreshed)` reflects the row state under lock —
    so the second concurrent transaction will see status=approved and bail.
    """
    from sqlalchemy import select  # local to avoid top-of-file churn

    from app.models.moderation import ModerationSubmission as _MS
    result = await db.execute(
        select(_MS).where(_MS.id == sub.id).with_for_update()
    )
    locked = result.scalar_one_or_none()
    if locked is None:
        raise ValueError("Submission not found (was it deleted?)")
    return locked


# ════════════════════════════════════════════════════════════
#   Apply-dispatcher followup B1)
# ════════════════════════════════════════════════════════════
# Approve no longer just bookkeeps — it routes the approved change to a
# module-specific handler that performs the actual write.
#
# Handler signature:
#   async def apply(db, *, sub: ModerationSubmission, user: User) -> dict | None
#     `user` is the moderator who clicked approve (acts as actor).
#     Return a small "result" dict to be stored on sub.apply_result (or None).
#     Raise on hard failure — submission stays in `approved` status but
#     `apply_error` field captures the message for retry.
#
# To add a new module: write a handler in
# `app/services/moderation_apply/{module}.py` exporting `apply(db, sub, user)`
# and register it below.

APPLY_HANDLERS: dict[str, Any] = {}


def register_apply_handler(module: str, handler) -> None:
    """Register a handler that applies an approved submission to its target."""
    APPLY_HANDLERS[module] = handler


def _load_apply_handlers() -> None:
    """Import all known handler modules so they register themselves.

    Wrapped in try/except per-module — a broken handler import shouldn't
    take down the whole moderation service.
    """
    handler_modules = (
        "app.services.moderation_apply.kpi",
        "app.services.moderation_apply.business_plan",
        "app.services.moderation_apply.financials",
        "app.services.moderation_apply.ratings",
        "app.services.moderation_apply.esg",
        "app.services.moderation_apply.governance",
        "app.services.moderation_apply.tasks",
        "app.services.moderation_apply.projects",
        "app.services.moderation_apply.procurement",
        "app.services.moderation_apply.production",
        "app.services.moderation_apply.comments",
        # Skipped (deliberately):
        #   - uploads:  path storage with freeform JSON
    )
    for mod_path in handler_modules:
        try:
            __import__(mod_path)
        except Exception as e:
            log.warning("apply handler %s failed to load: %s", mod_path, e)


_load_apply_handlers()


# ════════════════════════════════════════════════════════════
#   Write-intercept helper followup B2)
# ════════════════════════════════════════════════════════════

async def gate_or_apply(
    db: AsyncSession,
    *,
    user: User,
    module: str,
    action: str,
    entity_id: Optional[str],
    entity_label: Optional[str],
    company_id: Optional[UUID],
    sector_id: Optional[UUID],
    year: Optional[int],
    payload: dict[str, Any],
    original: Optional[dict[str, Any]] = None,
    diff_summary: Optional[str] = None,
):
    """Decide whether to write through or queue for moderation.

    Returns a 2-tuple `(queued, value)`:
      - `(False, None)` → caller must perform the write itself (no rule matched
        or user has bypass).
      - `(True, submission)` → write was intercepted, caller should return
        the submission to the client (HTTP 202 with submission id).

    Bypass rules (write through directly):
      * `user.is_owner` is True
      * `user.bypass_moderation` is True
      * caller has the `moderation.bypass` permission
      * no active rule matches the (user, module, action, ...) tuple
    """
    # Owner + bypass-flagged users + bypass-perm holders write through.
    if user.is_owner:
        return False, None
    if getattr(user, "bypass_moderation", False):
        return False, None
    try:
        from app.core.security import _user_permission_codes
        if "moderation.bypass" in _user_permission_codes(user):
            return False, None
    except Exception:
        pass

    if not should_moderate(user, module, action):
        return False, None
    rule = None

    sub = await create_submission(
        db,
        proposer=user,
        target_module=module,
        target_entity_id=str(entity_id) if entity_id is not None else None,
        target_entity_label=entity_label,
        target_company_id=company_id,
        target_sector_id=sector_id,
        action=action,
        proposed_value=payload,
        original_value=original,
        diff_summary=diff_summary,
        year=year,
    )
    return True, sub


async def _dispatch_apply(
    db: AsyncSession, sub: ModerationSubmission, user: User,
) -> None:
    """Route an approved submission to its module's apply handler.

    No-op if no handler registered for sub.target_module — caller sees
    `sub.apply_error = 'no handler'` and can re-trigger from the UI once
    a handler is added.
    """
    handler = APPLY_HANDLERS.get(sub.target_module)
    if handler is None:
        sub.apply_status = "skipped"
        sub.apply_error = f"no apply handler registered for module '{sub.target_module}'"
        sub.apply_result = None
        await db.commit()
        return
    try:
        result = await handler(db, sub=sub, user=user)
        sub.apply_status = "applied"
        sub.apply_error = None
        sub.apply_result = result if isinstance(result, dict) else None
        await db.commit()
    except Exception as e:
        log.exception("apply handler for %s failed", sub.target_module)
        sub.apply_status = "failed"
        sub.apply_error = str(e)[:500]
        sub.apply_result = None
        await db.commit()



async def _assert_can_resolve(
    db: AsyncSession, sub: ModerationSubmission, user: User,
) -> None:
    """Единая проверка «этот человек вправе закрыть заявку».

    `_can_resolve` синхронный и смотрит только роли пользователя, поэтому
    персональный отзыв права (`user_permission_grant`, grant_type='deny') он не
    видит. На HTTP-путях это прикрыто `require_permission`, но Telegram-кнопки
    «Принять/Отклонить» идут через `bot_callbacks` мимо любых HTTP-гейтов —
    снятый модератор мог бы закрыть заявку из старого уведомления. Отзыв
    проверяем здесь, до всех остальных условий.
    """
    from app.services import moderation_authority
    if await moderation_authority.review_denied(db, user):
        raise PermissionError("Not authorized to resolve this submission")
    await _assert_can_resolve(db, sub, user)


async def approve(
    db: AsyncSession, *, sub: ModerationSubmission, user: User, note: Optional[str] = None,
) -> ModerationSubmission:
    """Approve a submission. If approval_mode = dual, both moderators must approve.

    On terminal approval, dispatches to the apply-handler that actually
    writes the change to the target entity (see APPLY_HANDLERS).
    """
    await _assert_can_resolve(db, sub, user)
    sub = await _lock_and_reload(db, sub)  # serialize concurrent approvals
    _guard_open(sub)

    now = datetime.now(UTC)
    given = list(sub.approvals_given or [])
    if not any(g.get("user_id") == str(user.id) for g in given):
        given.append({"user_id": str(user.id), "at": now.isoformat()})
    sub.approvals_given = given

    # Dual mode requires both
    if sub.approval_mode == "dual":
        needed = set()
        if sub.assigned_moderator_id: needed.add(str(sub.assigned_moderator_id))
        if sub.coapprover_id:         needed.add(str(sub.coapprover_id))
        # Single-user dual is meaningless — fall through to terminal approve.
        if len(needed) > 1:
            got = {g["user_id"] for g in given}
            if not needed.issubset(got):
                sub.status = "under_review"
                sub.updated_at = now
                await db.commit()
                await _notify_status_change(db, sub, "review_requested",
                                             f"{user.email} утвердил, ждём второго")
                await db.refresh(sub)
                return sub

    sub.status = "approved"
    sub.resolved_at = now
    sub.resolved_by_id = user.id
    sub.resolution_note = note
    sub.updated_at = now

    if sub.rule_id:
        rule = await db.get(ModerationRule, sub.rule_id)
        if rule: rule.total_approvals += 1

    await db.commit()
    # B1: write the approved change to the target entity. If no handler is
    # registered for the module, sub.apply_status='skipped' and admins see
    # it in the UI — they can retry once the handler is wired.
    await _dispatch_apply(db, sub, user)
    await _notify_status_change(db, sub, "approved", note)
    await db.refresh(sub)
    return sub


async def reject(
    db: AsyncSession, *, sub: ModerationSubmission, user: User, note: Optional[str] = None,
) -> ModerationSubmission:
    await _assert_can_resolve(db, sub, user)
    sub = await _lock_and_reload(db, sub)
    _guard_open(sub)
    now = datetime.now(UTC)
    sub.status = "rejected"
    sub.resolved_at = now
    sub.resolved_by_id = user.id
    sub.resolution_note = note
    sub.updated_at = now

    if sub.rule_id:
        rule = await db.get(ModerationRule, sub.rule_id)
        if rule: rule.total_rejections += 1

    await db.commit()
    await _notify_status_change(db, sub, "rejected", note)
    await db.refresh(sub)
    return sub


async def set_review(
    db: AsyncSession, *, sub: ModerationSubmission, user: User, note: Optional[str] = None,
) -> ModerationSubmission:
    if not _can_resolve(sub, user):
        raise PermissionError("Not authorized")
    sub = await _lock_and_reload(db, sub)
    _guard_open(sub)
    now = datetime.now(UTC)
    sub.status = "under_review"
    sub.resolution_note = note
    sub.updated_at = now
    await db.commit()
    await _notify_status_change(db, sub, "review_requested", note)
    await db.refresh(sub)
    return sub


async def withdraw(
    db: AsyncSession, *, sub: ModerationSubmission, user: User,
) -> ModerationSubmission:
    """Proposer withdraws their own submission."""
    if sub.proposer_user_id != user.id:
        raise PermissionError("Only the proposer can withdraw")
    sub = await _lock_and_reload(db, sub)
    _guard_open(sub)
    now = datetime.now(UTC)
    sub.status = "withdrawn"
    sub.resolved_at = now
    sub.resolved_by_id = user.id
    sub.updated_at = now
    await db.commit()
    await db.refresh(sub)
    return sub


async def edit_and_approve(
    db: AsyncSession, *, sub: ModerationSubmission, user: User,
    proposed_value: dict[str, Any], note: Optional[str] = None,
) -> ModerationSubmission:
    """Moderator edits the proposed value before approving."""
    if not _can_resolve(sub, user):
        raise PermissionError("Not authorized")
    _guard_open(sub)
    sub.proposed_value = proposed_value
    sub.updated_at = datetime.now(UTC)
    await db.commit()
    return await approve(db, sub=sub, user=user, note=note or "Изменено модератором перед одобрением")


async def _notify_status_change(
    db: AsyncSession, sub: ModerationSubmission, kind: str, note: Optional[str] = None,
) -> None:
    """Notify proposer (and optionally owner) about status transition."""
    notif_type = {
        "approved":          "moderation.approved",
        "rejected":          "moderation.rejected",
        "review_requested":  "moderation.review_requested",
    }.get(kind, "moderation.approved")

    titles = {
        "moderation.approved":          "Ваше предложение одобрено",
        "moderation.rejected":          "Ваше предложение отклонено",
        "moderation.review_requested":  "Запрошено дополнительное рассмотрение",
    }
    title = f"{titles[notif_type]}: {sub.target_entity_label or sub.target_module}"
    body = note or sub.diff_summary or None
    # Пропозер обычно НЕ имеет доступа к /admin/moderation (нужен
    # moderation.review). Для задач/проектов линкуем на саму сущность — она
    # откроется глобальной модалкой (доступна автору). Для прочих модулей —
    # fallback на очередь модерации.
    if sub.target_module in ("tasks", "projects") and sub.target_entity_id:
        link = f"/{sub.target_module}/{sub.target_entity_id}"
    else:
        link = f"/admin/moderation?sub_tab=queue&open={sub.id}"

    payload = {
        "submission_id": str(sub.id),
        "module":        sub.target_module,
    }
    await notify(
        db, recipient_id=sub.proposer_user_id, type=notif_type,
        title=title, body=body, link_url=link, payload=payload,
        title_template="{status}: {entity}",
        template_vars={
            "status": titles[notif_type],
            "entity": sub.target_entity_label or sub.target_module,
        },
        translate_vars={"status"},
        source_module="moderation", source_entity_id=str(sub.id),
        source_user_id=sub.resolved_by_id,
    )


# ════════════════════════════════════════════════════════════
#   Comments
# ════════════════════════════════════════════════════════════

async def add_comment(
    db: AsyncSession, *, sub: ModerationSubmission, user: User,
    text: str, attachments: Optional[list[dict]] = None, is_internal: bool = False,
) -> ModerationComment:
    """Add a comment to the discussion thread."""
    now = datetime.now(UTC)
    c = ModerationComment(
        created_at=now,
        submission_id=sub.id,
        user_id=user.id,
        text=text,
        attachments=attachments,
        is_internal=bool(is_internal),
    )
    db.add(c)
    sub.updated_at = now
    await db.commit()
    await db.refresh(c)

    # Notify the "other side": if commenter is proposer → notify moderators
    # if commenter is moderator → notify proposer
    if user.id == sub.proposer_user_id:
        for uid in {sub.assigned_moderator_id, sub.coapprover_id}:
            if uid: await _notify_comment(db, sub, uid, user, text)
    else:
        # internal-only comments are not seen by proposer
        if not is_internal:
            await _notify_comment(db, sub, sub.proposer_user_id, user, text)

    return c


async def _notify_comment(
    db: AsyncSession, sub: ModerationSubmission, recipient_id: UUID,
    author: User, text: str,
) -> None:
    snippet = text[:180] + ("…" if len(text) > 180 else "")
    await notify(
        db, recipient_id=recipient_id,
        type="comment.replied",
        title=f"Комментарий в модерации: {sub.target_entity_label or sub.target_module}",
        body=snippet,
        title_template="Комментарий в модерации: {entity}",
        template_vars={"entity": sub.target_entity_label or sub.target_module},
        priority="normal",
        link_url=f"/admin/moderation?sub_tab=queue&open={sub.id}",
        payload={"submission_id": str(sub.id)},
        source_module="moderation",
        source_entity_id=str(sub.id),
        source_user_id=author.id,
    )
