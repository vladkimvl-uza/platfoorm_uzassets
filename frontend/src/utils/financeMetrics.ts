// ============================================================================
// Канонические деривации финансовых метрик — ЕДИНЫЙ источник формул.
//
// Раньше EBITDA-формула дублировалась в useIfrsSchema/useNsbuSchema и считалась
// по-своему в HLF-банде, а FCF имел ДВА несовместимых определения на разных
// экранах (CFO−CapEx в редакторе/дрилле vs CFO+CFI на всех портфельных). Здесь —
// ОДНА формула каждой; все поверхности импортируют отсюда, чтобы не расходиться.
//
// g — геттер значения метрики по коду (null, если метрики нет).
// ============================================================================

/** Канон EBITDA: первично opProfit + |depreciation|; фолбэк
 *  profit + |tax| + |depreciation| + |finCost|. Байт-в-байт совпадает с прежними
 *  формулами редакторов МСФО/НСБУ (дедуп, чисел не меняет). */
export function deriveEbitda(g: (f: string) => number | null): number | null {
  const op = g("opProfit"), dp = g("depreciation");
  if (op != null && dp != null) return op + Math.abs(dp);
  const pr = g("profit"), tx = g("tax"), fc = g("finCost");
  if (pr != null) return pr + Math.abs(tx || 0) + Math.abs(dp || 0) + Math.abs(fc || 0);
  return null;
}

/** Канон FCF = CFO − |CapEx| (решение владельца 10.08.2026). НЕ CFO+CFI.
 *  Совпадает с freeCashFlow-строкой редактора МСФО (стор-канон). null если нет CFO. */
export function deriveFcf(g: (f: string) => number | null): number | null {
  const o = g("cfo");
  if (o == null) return null;
  const cx = g("cfi_capex");
  return o - Math.abs(cx || 0);
}

/** Готовый FCF для среза метрик: сначала сохранённый/деривированный бэкендом
 *  freeCashFlow (бэкенд уже деривит cfo−|capex| где нет строки), иначе локальный
 *  фолбэк по cfo/cfi_capex. НИКОГДА не cfo+cfi. */
export function fcfFromMetrics(
  m: { freeCashFlow?: number | null; cfo?: number | null; cfi_capex?: number | null } | null | undefined,
): number | null {
  if (!m) return null;
  if (m.freeCashFlow != null) return m.freeCashFlow;
  return deriveFcf((f) => (m as Record<string, number | null | undefined>)[f] ?? null);
}
