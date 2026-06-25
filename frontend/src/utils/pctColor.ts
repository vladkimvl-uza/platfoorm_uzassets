/**
 * pctColor.ts — единая светофорная палитра для прогресс-метрик.
 *
 * Цвета (good/warn/bad) жили скопированными в каждом блоке Executive Dashboard.
 * Пороги у блоков исторически РАЗНЫЕ (например, governance строже, sector мягче),
 * поэтому они остаются параметрами — здесь единый ИСТОЧНИК ЦВЕТА, не порогов.
 *
 *   import { pctColor } from "@/utils/pctColor";
 *   const cellColor = (p: number) => pctColor(p, 75, 55);  // свои пороги блока
 */

export const PCT_GOOD = "#1D9E75"; // зелёный — в норме
export const PCT_WARN = "#EF9F27"; // янтарь — внимание
export const PCT_BAD = "#E24B4A";  // красный — отставание

/**
 * Цвет по проценту: `>= good` → зелёный, `>= warn` → янтарь, иначе красный.
 * Пороги по умолчанию 70/40 — типовая «прогресс-светофорка».
 */
export function pctColor(pct: number, good = 70, warn = 40): string {
  if (pct >= good) return PCT_GOOD;
  if (pct >= warn) return PCT_WARN;
  return PCT_BAD;
}
