"""Canonical webhook event registry (Pack 12.1).

A central source of truth for ALL events the platform can emit.

- The subscription UI uses this list to populate the event picker
- emit_event() validates that the code is registered (preventing typos)
- Documentation generators can pull descriptions + payload schemas
"""
from typing import TypedDict


class EventDef(TypedDict):
    code:        str
    module:      str       # for grouping in UI
    label:       str       # human-readable
    description: str
    payload_keys: list[str]   # documented top-level fields in payload


EVENT_REGISTRY: list[EventDef] = [
    # ─── Portfolio / tasks ─────────────────────────────────────
    {"code": "task.created",        "module": "portfolio", "label": "Задача создана",
     "description": "Создана новая задача в любом борде",
     "payload_keys": ["task_id", "board_id", "title", "assignee_id", "company_id", "created_by_id"]},
    {"code": "task.updated",        "module": "portfolio", "label": "Задача изменена",
     "description": "Изменён любой поле задачи (status, dueDate, assignee и т.д.)",
     "payload_keys": ["task_id", "changed_fields", "previous_status", "current_status"]},
    {"code": "task.completed",      "module": "portfolio", "label": "Задача завершена",
     "description": "Задача переведена в статус Done",
     "payload_keys": ["task_id", "completed_by_id", "duration_days"]},

    # ─── Finance ─────────────────────────────────────────────
    {"code": "kpi.threshold_breached", "module": "finance", "label": "KPI: пробит порог",
     "description": "Значение KPI пересекло amber/red порог (в любую сторону)",
     "payload_keys": ["company_id", "kpi_code", "value", "threshold", "zone", "direction"]},
    {"code": "financials.imported", "module": "finance", "label": "Финансы импортированы",
     "description": "Загружен / обновлён НСБУ либо МСФО отчёт",
     "payload_keys": ["company_id", "period", "standard", "indicator_count", "imported_by_id"]},
    {"code": "rating.changed",      "module": "finance", "label": "Рейтинг изменён",
     "description": "Изменён рейтинг компании (general / financial / ESG / governance)",
     "payload_keys": ["company_id", "rating_kind", "previous", "current", "changed_by_id"]},

    # ─── Notifications .x) ────────────────────────────
    {"code": "broadcast.created",   "module": "notifications", "label": "Рассылка создана",
     "description": "Создан новый шаблон админской рассылки",
     "payload_keys": ["template_id", "name", "ack_mode", "is_sticky", "created_by_id"]},
    {"code": "broadcast.sent",      "module": "notifications", "label": "Рассылка отправлена",
     "description": "Очередная dispatch рассылки доставлена получателям",
     "payload_keys": ["template_id", "dispatch_id", "recipients_count", "scheduled_at"]},

    # ─── API & integrations .x) ───────────────────────
    {"code": "api_key.created",     "module": "api_integrations", "label": "API ключ выпущен",
     "description": "Создан новый API ключ для service account",
     "payload_keys": ["key_id", "service_account_id", "name", "environment", "scopes", "created_by_id"]},
    {"code": "api_key.revoked",     "module": "api_integrations", "label": "API ключ отозван",
     "description": "Существующий ключ отозван (revoked_at установлен)",
     "payload_keys": ["key_id", "service_account_id", "revoked_by_id", "reason"]},
    {"code": "webhook.test",        "module": "api_integrations", "label": "Тестовое событие",
     "description": "Отправлено вручную через 'Send test' для проверки endpoint",
     "payload_keys": ["subscription_id", "triggered_by_id"]},

    # ─── Moderation ───────────────────────────────
    {"code": "moderation.submitted", "module": "moderation", "label": "Изменение на модерацию",
     "description": "Внешний пользователь подал change-request",
     "payload_keys": ["submission_id", "module", "entity_type", "submitted_by_id"]},
    {"code": "moderation.decided",   "module": "moderation", "label": "Модерация: решение",
     "description": "Change-request одобрен или отклонён",
     "payload_keys": ["submission_id", "decision", "decided_by_id", "comment"]},
]

# Codes for O(1) lookup
EVENT_CODES = {e["code"] for e in EVENT_REGISTRY}


def get_grouped_events() -> dict[str, list[EventDef]]:
    """Group events by module for UI tree rendering."""
    out: dict[str, list[EventDef]] = {}
    for e in EVENT_REGISTRY:
        out.setdefault(e["module"], []).append(e)
    return out


def is_registered(code: str) -> bool:
    return code in EVENT_CODES


def matches_subscription(event_code: str, subscribed_events: list[str]) -> bool:
    """Match an event against a subscription's event list.

    Supports literal codes and wildcards:
      "*"                    → all events
      "module.*"             → all events in a module (e.g. "task.*")
      "literal.event.code"   → exact match
    """
    if not subscribed_events:
        return False
    for pat in subscribed_events:
        if pat == "*":
            return True
        if pat.endswith(".*"):
            prefix = pat[:-2]
            if event_code.startswith(prefix + "."):
                return True
        if pat == event_code:
            return True
    return False
