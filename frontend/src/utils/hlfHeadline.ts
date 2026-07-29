import { i18nKey } from "@/locale/keys";
/**
 * Компактный экстрактор ключевых финансовых строк из HLF-данных компании
 * (для ИИ-анализа KPI — связь операционных KPI с финансовым результатом даже
 * когда у KPI нет прямой привязки к строкам ОФР). Самодостаточен: НЕ зависит
 * от HighLevelFinancials.vue (там своя, более полная логика buildKpis).
 */
type HlfRow = {
  label: string; mapping?: string | null; type?: string;
  values: (number | null)[]; _secYears?: number[];
};
type HlfSection = { years: number[]; rows: HlfRow[] };
export type HlfData = { years: number[]; sections: HlfSection[] };

// i18n-exempt-start: multilingual aliases classify imported financial rows; they are never rendered.
const MATCHERS: Record<string, string[]> = {
  revenue: ["выручка", "revenue", "тушум", "sales revenue"],
  cogs: ["себестоимость", "cost of sales", "cost of goods", "таннарх"],
  gross_profit: ["gross profit", "валовая прибыль"],
  operating_profit: ["operating profit", "операционная прибыль", "profit from operations"],
  net_profit: ["profit for the year", "net profit for the year", "чистая прибыль", "соф фойда", "profit attributable to"],
  total_assets: ["total assets", "жами активлар"],
  total_equity: ["total equity", "капитал", "shareholders' equity"],
  total_current_assets: ["total current assets", "жорий активлар"],
  total_current_liabilities: ["total current liabilities", "қисқа муддатли мажб"],
};
// i18n-exempt-end

export const HLF_LABELS: Record<string, string> = {
  revenue: i18nKey("Выручка"), cogs: i18nKey("Себестоимость"), gross_profit: i18nKey("Валовая прибыль"),
  operating_profit: i18nKey("Операционная прибыль"), net_profit: i18nKey("Чистая прибыль"),
  total_assets: i18nKey("Активы (итого)"), total_equity: i18nKey("Капитал (итого)"),
  total_current_assets: i18nKey("Оборотные активы"), total_current_liabilities: i18nKey("Краткосрочные обязательства"),
};

function rowValueForYear(r: HlfRow, year: number): number | null {
  const sy = r._secYears;
  if (!sy) return null;
  const i = sy.indexOf(year);
  return i === -1 ? null : (r.values[i] ?? null);
}
function matchRow(rows: HlfRow[], key: string): HlfRow | null {
  for (const p of (MATCHERS[key] || [])) {
    const lp = p.toLowerCase();
    const f = rows.find(r => r.type !== "section_header" && r.type !== "subheader" &&
      (r.label.toLowerCase().includes(lp) || (r.mapping || "").toLowerCase().includes(lp)));
    if (f) return f;
  }
  return null;
}

/** Ключевые фин-строки за ПОСЛЕДНИЙ год с данными: { year, kpis:{revenue,…} } или null. */
export function extractHlfHeadline(hlf: HlfData | null): { year: number; kpis: Record<string, number | null> } | null {
  if (!hlf?.years?.length || !hlf.sections?.length) return null;
  const rows = hlf.sections.flatMap(s => s.rows.map(r => ({ ...r, _secYears: s.years })));
  const anchor = matchRow(rows, "revenue") || matchRow(rows, "net_profit") || matchRow(rows, "total_assets");
  let year = hlf.years[hlf.years.length - 1];
  if (anchor) {
    for (let yi = hlf.years.length - 1; yi >= 0; yi--) {
      if (rowValueForYear(anchor, hlf.years[yi]) != null) { year = hlf.years[yi]; break; }
    }
  }
  const kpis: Record<string, number | null> = {};
  let any = false;
  for (const key of Object.keys(MATCHERS)) {
    const r = matchRow(rows, key);
    const v = r ? rowValueForYear(r, year) : null;
    kpis[key] = v;
    if (v != null) any = true;
  }
  return any ? { year, kpis } : null;
}
