"""Единый расчёт прогресса задач/проектов (backend-зеркало frontend
`utils/progress.ts`).

Правило (согласовано с пользователем):
  • задача со статусом «Завершено» (done) → 100% (вес 1);
  • остальные статусы в счёт не идут → 0%;
  • monthly / ongoing — бессрочные, исключаются из расчёта полностью;
  • quarterly — засчитывается как done только если закрыты все 4 квартала;
  • прогресс проекта/компании = среднее по задачам = done / total × 100,
    где total НЕ включает исключённые (monthly/ongoing) задачи.

Держим логику в одном месте, чтобы дашборды, списки и редактор не расходились
в процентах (как и единый источник правды на фронте).
"""
from __future__ import annotations

from typing import Any, Iterable, Optional

# Статусы без точки завершения — исключаются из процента целиком.
EXCLUDED_FROM_PCT = frozenset({"monthly", "ongoing"})


def _quarters_all_closed(extra: Any) -> bool:
    q = (extra or {}).get("quarters") if isinstance(extra, dict) else None
    if not isinstance(q, dict):
        return False
    return bool(q.get("q1") and q.get("q2") and q.get("q3") and q.get("q4"))


def task_weight(status: Optional[str], extra: Any = None) -> Optional[int]:
    """Вес задачи 0..1 для расчёта прогресса. None = исключить из расчёта.

    Зеркалит frontend taskWeight():
      done → 1; new/init/active/review → 0;
      quarterly → 1 если все 4 квартала закрыты, иначе 0;
      monthly/ongoing → None (исключить).
    """
    if not status:
        return 0
    if status in EXCLUDED_FROM_PCT:
        return None
    if status == "quarterly":
        return 1 if _quarters_all_closed(extra) else 0
    return 1 if status == "done" else 0


def compute_done_total(items: Iterable[tuple[Optional[str], Any]]) -> tuple[int, int]:
    """Для набора (status, extra) → (done, total) с учётом правила.

    total исключает monthly/ongoing; done — суммарный вес.
    Процент = round(done / total × 100) при total > 0, иначе 0.
    """
    done = 0
    total = 0
    for status, extra in items:
        w = task_weight(status, extra)
        if w is None:
            continue
        total += 1
        if w == 1:
            done += 1
    return done, total
