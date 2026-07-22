/**
 * Единый расчёт достижения KPI — зеркало `kpi_ratio`/`co_pct` на бэке.
 *
 * Аудит здоровья кода (июль 2026, P0): формула исполнения существовала в
 * нескольких копиях, часть — без учёта `direction='down'` и без пола/потолка.
 * В воркспейсе `Math.min(2, fact/plan)` для показателя «снизить X» рисовал
 * перерасход как достижение >100%, а модуль /kpi — как провал. Единый источник
 * устраняет расхождение цифр между экранами.
 */

/** Потолок вклада достижения во взвешенную сводку — 150% (канон co_pct/mgr_pct). */
export const KPI_RATIO_CAP = 1.5;

/**
 * Достижение одного KPI как доля (1 = 100%). `null`, если посчитать нельзя.
 * Учитывает направление и отсекает отрицательный/нулевой план (плановый убыток
 * инвертировал бы знак → −187%): такой показатель не оцениваем.
 */
export function kpiCompletionRatio(
  plan: number | null | undefined,
  fact: number | null | undefined,
  direction?: "up" | "down" | string | null,
): number | null {
  if (plan == null || fact == null) return null;
  const dir = direction === "down" ? "down" : "up";
  if (dir === "down") return plan <= 0 || fact <= 0 ? null : plan / fact;
  return plan <= 0 ? null : fact / plan;
}

/** Взвешенный вклад достижения в сводку: пол 0, потолок 150%. */
export function kpiWeightedRatio(ratio: number): number {
  return Math.max(0, Math.min(ratio, KPI_RATIO_CAP));
}
