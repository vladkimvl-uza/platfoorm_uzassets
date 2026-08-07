"""Business-plan apply handler (Pack 148-followup B1).

Applies an approved BP bulk-upsert submission. Mirrors POST /bp/bulk-upsert.

Submission shape:
  target_module    = "business_plan"
  target_entity_id = <company_id UUID string>
  proposed_value   = { "records": [BpRecordUpsert, ...] }
"""
from __future__ import annotations

from sqlalchemy import func
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.models.bp_kpi import BP_METRIC_KEYS as _BP_METRIC_KEYS
from app.models.bp_kpi import BP_PERIODS as _BP_PERIODS
from app.models.bp_kpi import BpRecord
from app.models.moderation import ModerationSubmission
from app.models.user import User
from app.schemas.bp_kpi import BpBulkUpsert
from app.services.moderation_service import register_apply_handler

# P0 (аудит фин-источников): раньше здесь были самодельные списки с «year»
# вместо канонического «annual» (CHECK-констрейнт bp_records!) и 11 метрик
# вместо 22 — одобренная заявка МОЛЧА теряла все годовые ячейки и половину
# метрик. Используем канонические константы модели — единственный источник.
BP_PERIODS = set(_BP_PERIODS)          # {"annual", "q1".."q4"}
BP_METRIC_KEYS = set(_BP_METRIC_KEYS)  # все 22 канонические метрики БП


async def apply(db, *, sub: ModerationSubmission, user: User) -> dict:
    if not sub.proposed_value:
        raise ValueError("proposed_value is empty")

    try:
        payload = BpBulkUpsert.model_validate(sub.proposed_value)
    except Exception as e:
        raise ValueError(f"proposed_value does not match BpBulkUpsert: {e}") from e

    # Защита от затирания: токен scope (company, year) ПЕРВОЙ записи снят при
    # подаче (как и проверяет живой роут). Если данные изменились после подачи —
    # не применяем: даже upsert затёр бы новые значения затронутых ячеек. NULL →
    # проверки нет (legacy/не captured).
    if sub.editor_token and payload.records:
        from app.core.editor_lock import compute_bp_editor_token
        first = payload.records[0]
        current_tok = await compute_bp_editor_token(
            db, company_id=first.company_id, year=first.year,
        )
        if current_tok != sub.editor_token:
            raise ValueError(
                "Данные бизнес-плана этой компании за этот год изменились после "
                "подачи заявки — применение затёрло бы новые правки. Отклоните "
                "заявку и попросите автора пересоздать её на актуальных данных.",
            )

    n = 0
    for rec in payload.records:
        if rec.period not in BP_PERIODS or rec.metric not in BP_METRIC_KEYS:
            continue
        stmt = pg_insert(BpRecord).values(
            company_id=rec.company_id, year=rec.year,
            period=rec.period, metric=rec.metric,
            plan=rec.plan, expect=rec.expect, fact=rec.fact,
        ).on_conflict_do_update(
            index_elements=["company_id", "year", "period", "metric"],
            set_={
                "plan": rec.plan, "expect": rec.expect, "fact": rec.fact,
                "updated_at": func.now(),
            },
        )
        await db.execute(stmt)
        n += 1
    await db.commit()
    return {"upserted": n}


register_apply_handler("business_plan", apply)
