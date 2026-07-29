"""Единый маппинг «код поля → человеко-читаемое имя» для журналов аудита и
деталей уведомлений. Используется и лентой активности (`audit_service`), и
эндпоинтом деталей уведомления (`routes/notifications`), чтобы «что именно
изменили» звучало одинаково везде.

Неизвестный код мягко очищается (snake_case → «Snake case»), а не показывается
сырым — лучше приблизительная метка, чем машинный код в глазах министра.
"""
from __future__ import annotations

from app.core.i18n import current_locale, tr

_FIELD_LABELS: dict[str, str] = {
    # ── план/факт/значения ──
    "plan_year": "План (год)", "fact_year": "Факт (год)",
    "plan": "План", "fact": "Факт", "target": "Целевое значение",
    "value": "Значение", "new_value": "Новое значение", "old_value": "Прежнее значение",
    "amount": "Сумма", "score": "Оценка", "benchmark": "Бенчмарк",
    # ── периоды ──
    "period": "Период", "year": "Год", "quarter": "Квартал", "years": "Годы",
    "consolidated": "Консолидация",
    # ── финансовые редакторы (сводные счётчики) ──
    "reports_created": "Отчётов создано", "reports_updated": "Отчётов обновлено",
    "lines_upserted": "Строк изменено", "lines_deleted": "Строк удалено",
    "fields": "Затронутые поля",
    # ── библиотека компании / маршрутизация ──
    "field_code": "Поле", "source_module": "Источник", "routed_to": "Куда записано",
    "company_code": "Компания",
    # ── RBAC ──
    "role": "Роль", "role_codes": "Роли", "permissions": "Права",
    "permission": "Право", "scope_companies": "Компании доступа",
    # ── рейтинги ──
    "rating": "Рейтинг", "outlook": "Прогноз", "agency": "Агентство",
    "report_url": "Ссылка на отчёт", "is_esg": "ESG-рейтинг",
    # ── ESG / KPI / прочее ──
    "status": "Статус", "stage": "Стадия", "dimension": "Измерение",
    "sub_key": "Подраздел", "metric_code": "Метрика", "metric_name": "Метрика",
    "unit": "Ед. изм.", "direction": "Направление", "pillar": "Компонент ESG",
    # Values are translated by field_label(); the mapping remains canonical RU.
    "severity": "Критичность", "title": "Название", "name": "Название",  # i18n-audit: ignore
    "note": "Примечание", "notes": "Примечание", "description": "Описание",
    "health": "Статус (RAG)", "evidence_url": "Ссылка-подтверждение",
    "due_date": "Срок",
}


def field_label(code: str, locale: str | None = None) -> str:
    """Код поля → читаемое имя. Неизвестное — очищаем в «Человеко-читаемый» вид."""
    if not code:
        return "—"
    key = code.strip()
    resolved_locale = locale or current_locale()
    if key in _FIELD_LABELS:
        return tr(_FIELD_LABELS[key], resolved_locale)
    low = key.lower()
    if low in _FIELD_LABELS:
        return tr(_FIELD_LABELS[low], resolved_locale)
    # snake/kebab → слова, первая заглавная
    return key.replace("_", " ").replace("-", " ").strip().capitalize() or code
