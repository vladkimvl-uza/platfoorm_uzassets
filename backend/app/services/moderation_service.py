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

from sqlalchemy import and_, func, select
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

        # ACTION
        if rule.trigger_actions and action not in rule.trigger_actions:
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
    link  = f"/admin/moderation?sub_tab=queue&open={sub.id}"

    recipients: list[UUID] = []
    if sub.assigned_moderator_id:
        recipients.append(sub.assigned_moderator_id)
    if rule and rule.notify_coapprovers_cc and sub.coapprover_id:
        recipients.append(sub.coapprover_id)

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
    if user.is_owner:
        return True
    if sub.assigned_moderator_id and sub.assigned_moderator_id == user.id:
        return True
    if sub.coapprover_id and sub.coapprover_id == user.id:
        return True
    return False


# Pack 148-followup A5: terminal statuses cannot be re-resolved. Helper raises
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
#   Apply-dispatcher (Pack 148-followup B1)
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
        "app.services.moderation_apply.procurement",
        # Skipped (deliberately):
        #   - comments: nested under projects/tasks, author-only edits
        #               conflict with moderator-approval semantics
        #   - uploads:  Firebase-style path storage with freeform JSON
    )
    for mod_path in handler_modules:
        try:
            __import__(mod_path)
        except Exception as e:
            log.warning("apply handler %s failed to load: %s", mod_path, e)


_load_apply_handlers()


# ════════════════════════════════════════════════════════════
#   Write-intercept helper (Pack 148-followup B2)
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

    rule = await match_rule(
        db, user=user, module=module, action=action,
        company_id=company_id, sector_id=sector_id, year=year,
        payload={"proposed_value": payload, "original_value": original or {}, **payload},
    )
    if rule is None:
        return False, None

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


async def approve(
    db: AsyncSession, *, sub: ModerationSubmission, user: User, note: Optional[str] = None,
) -> ModerationSubmission:
    """Approve a submission. If approval_mode = dual, both moderators must approve.

    On terminal approval, dispatches to the apply-handler that actually
    writes the change to the target entity (see APPLY_HANDLERS).
    """
    if not _can_resolve(sub, user):
        raise PermissionError("Not authorized to resolve this submission")
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
    if not _can_resolve(sub, user):
        raise PermissionError("Not authorized to resolve this submission")
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
    link = f"/admin/moderation?sub_tab=queue&open={sub.id}"

    payload = {
        "submission_id": str(sub.id),
        "module":        sub.target_module,
    }
    await notify(
        db, recipient_id=sub.proposer_user_id, type=notif_type,
        title=title, body=body, link_url=link, payload=payload,
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
        priority="normal",
        link_url=f"/admin/moderation?sub_tab=queue&open={sub.id}",
        payload={"submission_id": str(sub.id)},
        source_module="moderation",
        source_entity_id=str(sub.id),
        source_user_id=author.id,
    )
