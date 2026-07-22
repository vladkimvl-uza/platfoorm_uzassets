/**
 * execBand.ts — единый канон цвета/зоны исполнения плана закупок (форензик).
 *
 * Причина: пороги «светофора» исполнения жили В ДВУХ экземплярах с РАЗНЫМИ
 * значениями — таблица ForensicAudit.vue (80/50 + >110 фиолетовый) и редактор
 * ForensicEditModal.vue (70/40 без зоны переисполнения). Это M-6 аудита
 * /procurement/forensic. Здесь — единственный источник; оба компонента импортируют
 * отсюда, чтобы навсегда исключить расхождение.
 *
 * Логика 1:1 с прежним pctCol/pctZone таблицы (поведение таблицы НЕ меняется):
 *   >110%  — переисполнение: ОТДЕЛЬНАЯ зона (фиолетовый), НЕ зелёный «отлично».
 *            2-3× превышение плана — красный флаг форензика (ошибка ввода/единиц/
 *            перерасход), а не достижение (H-5).
 *   ≥80%   — в норме (зелёный)
 *   ≥50%   — отставание (янтарь)
 *   <50%   — критично (красный)
 *   null   — нет данных (серый var(--t3))
 */

export const EXEC_OVER = "#7C3AED"; // переисполнение >110%
export const EXEC_GOOD = "#1D9E75"; // в норме
export const EXEC_WARN = "#D97706"; // отставание
export const EXEC_BAD = "#993D3D";  // критично

export function execCol(p: number | null | undefined): string {
  if (p == null) return "var(--t3)";
  if (p > 110) return EXEC_OVER;
  if (p >= 80) return EXEC_GOOD;
  if (p >= 50) return EXEC_WARN;
  return EXEC_BAD;
}

export function execZone(p: number | null | undefined): string {
  if (p == null) return "";
  if (p > 110) return "переисполнение — проверить единицы/двойной ввод";
  if (p >= 80) return "в норме";
  if (p >= 50) return "отставание";
  return "критично";
}
