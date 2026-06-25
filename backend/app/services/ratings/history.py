"""Запись истории изменений рейтинга. Вызывается на обоих путях записи
(прямой route → service, и через модерацию apply). Best-effort: ошибка записи
истории не должна валить основную операцию (рейтинг уже сохранён)."""
from __future__ import annotations

import logging
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.agency_rating import AgencyRating
from app.models.agency_rating_history import AgencyRatingHistory

logger = logging.getLogger(__name__)


async def record_rating_history(
    db: AsyncSession, *, rec: AgencyRating, action: str, user=None,
) -> None:
    """Снимок состояния рейтинга `rec` с действием action (create|update|delete).

    Коммитит отдельной транзакцией. `rec` может быть detached — читаем только уже
    загруженные скалярные атрибуты (без ленивых обращений). Для delete rating_id
    оставляем NULL (рейтинг удалён, FK сослаться не на что).
    """
    try:
        name = None
        if user is not None:
            name = getattr(user, "full_name", None) or getattr(user, "email", None)
        db.add(AgencyRatingHistory(
            rating_id=(None if action == "delete" else rec.id),
            company_id=rec.company_id,
            agency=rec.agency,
            is_esg=bool(rec.is_esg),
            rating=rec.rating,
            outlook=rec.outlook,
            score=rec.score,
            rating_date_text=rec.rating_date_text,
            rating_date=rec.rating_date,
            report_url=rec.report_url,
            action=action,
            changed_by=getattr(user, "id", None),
            changed_by_name=name,
        ))
        await db.commit()
    except Exception:
        logger.warning("rating history record failed (action=%s)", action, exc_info=True)
        try:
            await db.rollback()
        except Exception:
            pass
