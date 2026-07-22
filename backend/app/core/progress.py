"""Единый расчёт прогресса задач/проектов (backend-зеркало frontend
`utils/progress.ts`).

Правило (согласовано с пользователем 2026-06):
  Прогресс ЗАДАЧИ определяется статусом:
    • Не начато (new)        → 0%
    • Инициирование (init)   → 25%
    • В процессе (active)    → 50%
    • На согласовании (review) → 75%
    • Завершено (done)       → 100%
  Ежеквартальная (quarterly) → закрытых кварталов × 25% (1→25, 2→50, 3→75, 4→100).
  Ежемесячная/Постоянная (monthly/ongoing) → исключаются из расчёта (None).
  Прогресс ПРОЕКТА/компании = СРЕДНЕЕ по весам задач (Σвес/total × 100),
  где total НЕ включает исключённые (monthly/ongoing).

Держим логику в одном месте, чтобы дашборды, списки, PMO и редактор не расходились.
"""
from __future__ import annotations

from datetime import date
from typing import Any, Iterable, Optional, Tuple

# Статусы без точки завершения — исключаются из процента целиком.
EXCLUDED_FROM_PCT = frozenset({"monthly", "ongoing"})

# Статусы без финального дедлайна → задача не бывает «просрочена»: завершённые
# (done) + рекуррентные (quarterly/monthly/ongoing повторяются каждый период).
# Единый набор для всех модулей — раньше tasks/ai считали recurring просроченными,
# а consultants/фронт-дрилл нет (аудит здоровья кода, P0).
NON_OVERDUE_STATUSES = frozenset({"done", "quarterly", "monthly", "ongoing"})

# Статус → доля выполнения (0..1). quarterly считается отдельно по кварталам.
_STATUS_WEIGHT: dict[str, float] = {
    "new": 0.0,
    "init": 0.25,
    "active": 0.5,
    "review": 0.75,
    "done": 1.0,
    "deferred": 0.0,
}


def _quarters_closed_count(extra: Any) -> int:
    q = (extra or {}).get("quarters") if isinstance(extra, dict) else None
    if not isinstance(q, dict):
        return 0
    return sum(1 for k in ("q1", "q2", "q3", "q4") if q.get(k))


def task_weight(status: Optional[str], extra: Any = None) -> Optional[float]:
    """Вес задачи 0..1 для расчёта прогресса. None = исключить из расчёта.

    new→0, init→0.25, active→0.5, review→0.75, done→1.0;
    quarterly → закрытых кварталов / 4; monthly/ongoing → None.
    """
    if not status:
        return 0.0
    if status in EXCLUDED_FROM_PCT:
        return None
    if status == "quarterly":
        return _quarters_closed_count(extra) / 4.0
    return _STATUS_WEIGHT.get(status, 0.0)


def task_pct(status: Optional[str], extra: Any = None) -> Optional[int]:
    """Процент одной задачи 0..100 (None = исключена)."""
    w = task_weight(status, extra)
    return None if w is None else round(w * 100)


def weighted_pct(items: Iterable[Tuple[Optional[str], Any]]) -> int:
    """Прогресс группы = round(Σвес / total × 100), total без исключённых."""
    s = 0.0
    n = 0
    for status, extra in items:
        w = task_weight(status, extra)
        if w is None:
            continue
        n += 1
        s += w
    return round(s / n * 100) if n else 0


def compute_done_total(items: Iterable[Tuple[Optional[str], Any]]) -> Tuple[int, int]:
    """Для набора (status, extra) → (done, total).

    done — число ПОЛНОСТЬЮ завершённых (вес = 1.0); total — без исключённых.
    Для процента используйте weighted_pct() (среднее по весам), а не done/total.
    """
    done = 0
    total = 0
    for status, extra in items:
        w = task_weight(status, extra)
        if w is None:
            continue
        total += 1
        if w >= 1.0:
            done += 1
    return done, total


def is_task_overdue(
    status: Optional[str], due: Optional[date], *, today: Optional[date] = None
) -> bool:
    """Единый предикат просрочки задачи. Рекуррентные (quarterly/monthly/ongoing)
    и завершённые статусы не имеют финального дедлайна → не просрочены. Иначе
    просрочена, если due-дата прошла."""
    if due is None:
        return False
    if (status or "").lower() in NON_OVERDUE_STATUSES:
        return False
    return due < (today if today is not None else date.today())
