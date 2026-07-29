import { i18nKey } from "@/locale/keys";
import { t } from "@/locale/i18n";

/**
 * useNsbuSchema.ts — Pack 7.51
 * ─────────────────────────────────────────────────────────────────
 * Структура НСБУ редактора: стандартные поля, секции, формулы авто-расчёта.
 *
 * Стандартные поля и их NSBU-коды строк (форма №1 — баланс, форма №2 — ОФР).
 * Авто-формулы соответствуют логике легасиа (_fdeAutoCalc) — см. NsbuEditor.vue.
 */

export type FieldId = string;
export type SectionId = "pnl" | "sofp";

export interface FieldDef {
  id: FieldId;
  label: string;
  /** NSBU code строки в форме (например '010', '7810') */
  nsbuCode?: string;
  /** Поле-расход — вводится положительным числом */
  positiveOnly?: boolean;
  /** Подзаголовок секции, рисуемый ПЕРЕД этим полем */
  groupHeader?: string;
  /** Авто-расчёт: имя формулы из AUTO_FORMULAS */
  autoFormula?: string;
  /** Подкатегория жирная (subtotal-style row) */
  isSubtotal?: boolean;
  /** Маппинг к canonical metric для портфельных агрегаций */
  canonical?: string;
  /** Custom user-added — НЕ из стандартного списка */
  isCustom?: boolean;
}

/**
 * Pack 7.54: список canonical metric кодов, на которые можно маппить custom поле.
 * Должен совпадать с _PORTFOLIO_METRIC_ALIASES values в backend (financials.py).
 * Если custom поле смапить на одно из этих значений — его значения будут
 * учитываться в портфельных KPI Дашборда и Financials.
 */
export const CANONICAL_METRICS: { code: string; label: string; section: SectionId }[] = [
  // P&L
  { code: "revenue",       label: i18nKey("Выручка"),                 section: "pnl" },
  { code: "cogs",          label: i18nKey("Себестоимость"),           section: "pnl" },
  { code: "grossProfit",   label: i18nKey("Валовая прибыль"),         section: "pnl" },
  { code: "opProfit",      label: i18nKey("Операционная прибыль"),    section: "pnl" },
  { code: "depreciation",  label: i18nKey("Амортизация"),             section: "pnl" },
  { code: "finCost",       label: i18nKey("Финансовые расходы"),      section: "pnl" },
  { code: "finIncome",     label: i18nKey("Финансовые доходы"),       section: "pnl" },
  { code: "interestExp",   label: i18nKey("Процентные расходы"),      section: "pnl" },
  { code: "forex",         label: i18nKey("Курсовая разница"),        section: "pnl" },
  { code: "pbt",           label: i18nKey("Прибыль до налога"),       section: "pnl" },
  { code: "tax",           label: i18nKey("Налог на прибыль"),        section: "pnl" },
  { code: "profit",        label: i18nKey("Чистая прибыль"),          section: "pnl" },
  { code: "ebitda",        label: "EBITDA",                   section: "pnl" },
  // Balance Sheet
  { code: "totalAssets",      label: i18nKey("Итого активы"),            section: "sofp" },
  { code: "totalLiabilities", label: i18nKey("Итого обязательства"),     section: "sofp" },
  { code: "equity",           label: i18nKey("Собственный капитал"),     section: "sofp" },
  { code: "totalCA",          label: i18nKey("Оборотные активы"),        section: "sofp" },
  { code: "totalNCA",         label: i18nKey("Внеоборотные активы"),     section: "sofp" },
  { code: "ppe",              label: i18nKey("Основные средства"),       section: "sofp" },
  { code: "cash",             label: i18nKey("Денежные средства"),       section: "sofp" },
  { code: "debt",             label: i18nKey("Финансовый долг"),         section: "sofp" },
  { code: "ltBorrowings",     label: i18nKey("Долгосрочные обяз-ва"),    section: "sofp" },
  { code: "stBorrowings",     label: i18nKey("Краткосрочные обяз-ва"),   section: "sofp" },
  { code: "ltBankLoans",      label: i18nKey("Долгосроч. банк. кредиты"),section: "sofp" },
  { code: "inventories",      label: i18nKey("Запасы"),                  section: "sofp" },
  { code: "tradeReceivables", label: i18nKey("Дебиторская задолж-ть"),   section: "sofp" },
  { code: "accountsReceivable", label: i18nKey("Дебиторская задолженность"), section: "sofp" },
  { code: "accountsPayable",    label: i18nKey("Кредиторская задолженность"), section: "sofp" },
];

export interface SectionDef {
  id: SectionId;
  label: string;
  fields: FieldDef[];
}

/**
 * Авто-расчёты NSBU. Формат: name → {expr, label}.
 * expr — выражение в терминах FieldId (рассчитывается клиентом в useNsbuFormulas).
 */
export interface AutoFormulaDef {
  expr: string;          // displayable formula
  fn: (g: (f: string) => number | null) => number | null;
}

export const AUTO_FORMULAS: Record<string, AutoFormulaDef> = {
  grossProfit: {
    expr: "revenue − |cogs|",
    fn: (g) => {
      const r = g("revenue"), c = g("cogs");
      if (r == null && c == null) return null;
      if (r == null || c == null) return null;
      return r - Math.abs(c);
    },
  },
  pbt: {
    expr: "opProfit + finIncome − |finCost|",
    fn: (g) => {
      const op = g("opProfit"), fi = g("finIncome"), fc = g("finCost");
      if (op == null && fi == null && fc == null) return null;
      return (op || 0) + (fi || 0) - Math.abs(fc || 0);
    },
  },
  profit: {
    expr: "pbt − |tax|",
    fn: (g) => {
      const pbt = g("pbt"), tax = g("tax");
      if (pbt == null && tax == null) return null;
      if (pbt == null) return null;
      return pbt - Math.abs(tax || 0);
    },
  },
  ebitda: {
    expr: i18nKey("opProfit + |depreciation| (или profit + |tax| + |dep| + |finCost|)"),
    fn: (g) => {
      const op = g("opProfit"), dp = g("depreciation");
      if (op != null && dp != null) return op + Math.abs(dp);
      const pr = g("profit"), tx = g("tax"), fc = g("finCost");
      if (pr != null) return pr + Math.abs(tx || 0) + Math.abs(dp || 0) + Math.abs(fc || 0);
      return null;
    },
  },
  totalAssets: {
    expr: "totalNCA + totalCA",
    fn: (g) => {
      const nca = g("totalNCA"), ca = g("totalCA");
      if (nca == null && ca == null) return null;
      if (nca == null || ca == null) return null;
      return nca + ca;
    },
  },
  totalLiabilities: {
    expr: "ltBorrowings + stBorrowings",
    fn: (g) => {
      const lt = g("ltBorrowings"), st = g("stBorrowings");
      if (lt == null && st == null) return null;
      return (lt || 0) + (st || 0);
    },
  },
  debt: {
    expr: "ltBankLoans + ltOtherLoans + stBankLoans + stOtherLoans",
    fn: (g) => {
      const a = g("ltBankLoans"), b = g("ltOtherLoans"), c = g("stBankLoans"), d = g("stOtherLoans");
      if (a == null && b == null && c == null && d == null) return null;
      return (a || 0) + (b || 0) + (c || 0) + (d || 0);
    },
  },
};

/** Стандартная схема НСБУ — ОФР (форма 2) + Баланс (форма 1). БЕЗ ДДС. */
export const STANDARD_SCHEMA: SectionDef[] = [
  {
    id: "pnl",
    label: i18nKey("ОФР · Форма 2"),
    fields: [
      { id: "revenue",       label: i18nKey("Выручка"),                          nsbuCode: "010", canonical: "revenue", groupHeader: i18nKey("ДОХОДЫ И РАСХОДЫ") },
      { id: "cogs",          label: i18nKey("Себестоимость"),                    nsbuCode: "020", canonical: "cogs", positiveOnly: true },
      { id: "grossProfit",   label: i18nKey("Валовая прибыль"),                  nsbuCode: "030", canonical: "grossProfit", autoFormula: "grossProfit", isSubtotal: true },
      { id: "opProfit",      label: i18nKey("Операционная прибыль"),             nsbuCode: "060", canonical: "opProfit", groupHeader: i18nKey("ОПЕРАЦИОННЫЙ РЕЗУЛЬТАТ") },
      { id: "depreciation",  label: i18nKey("Амортизация"),                       nsbuCode: "070", canonical: "depreciation", positiveOnly: true },
      { id: "finIncome",     label: i18nKey("Доходы от фин. деятельности"),      nsbuCode: "110", canonical: "finIncome" },
      { id: "finCost",       label: i18nKey("Расходы от фин. деятельности"),     nsbuCode: "170", canonical: "finCost", positiveOnly: true },
      { id: "forex",         label: i18nKey("Курсовая разница (справочно)"),     nsbuCode: "180", canonical: "forex" },
      { id: "pbt",           label: i18nKey("Прибыль до налога"),                nsbuCode: "190", canonical: "pbt", autoFormula: "pbt", isSubtotal: true, groupHeader: i18nKey("ИТОГИ ПЕРИОДА") },
      { id: "tax",           label: i18nKey("Налог на прибыль"),                 nsbuCode: "220", canonical: "tax", positiveOnly: true },
      { id: "profit",        label: i18nKey("Чистая прибыль"),                   nsbuCode: "270", canonical: "profit", autoFormula: "profit", isSubtotal: true },
      { id: "ebitda",        label: "EBITDA",                            canonical: "ebitda", autoFormula: "ebitda", isSubtotal: true },
    ],
  },
  {
    id: "sofp",
    label: i18nKey("Баланс · Форма 1"),
    fields: [
      { id: "ppe",              label: i18nKey("Основные средства"),        nsbuCode: "010", canonical: "ppe", groupHeader: i18nKey("АКТИВЫ") },
      { id: "totalNCA",         label: i18nKey("Внеоборотные активы (итог)"), nsbuCode: "190", canonical: "totalNCA", isSubtotal: true },
      { id: "cash",             label: i18nKey("Денежные средства"),        nsbuCode: "320", canonical: "cash" },
      { id: "accountsReceivable", label: i18nKey("Дебиторская задолженность"), nsbuCode: "210", canonical: "accountsReceivable" },
      { id: "totalCA",          label: i18nKey("Оборотные активы (итог)"),  nsbuCode: "390", canonical: "totalCA", isSubtotal: true },
      { id: "totalAssets",      label: i18nKey("ИТОГО Активы"),             nsbuCode: "400", canonical: "totalAssets", autoFormula: "totalAssets", isSubtotal: true },
      { id: "equity",           label: i18nKey("Собственный капитал"),      nsbuCode: "480", canonical: "equity", groupHeader: i18nKey("СОБСТВЕННЫЙ КАПИТАЛ"), isSubtotal: true },
      { id: "ltBorrowings",     label: i18nKey("Долгосрочные обязательства (итог)"), nsbuCode: "590", canonical: "ltBorrowings", positiveOnly: true, isSubtotal: true, groupHeader: i18nKey("ОБЯЗАТЕЛЬСТВА") },
      { id: "stBorrowings",     label: i18nKey("Краткосрочные обязательства (итог)"), nsbuCode: "780", canonical: "stBorrowings", positiveOnly: true, isSubtotal: true },
      { id: "accountsPayable",  label: i18nKey("Кредиторская задолженность"), nsbuCode: "601", canonical: "accountsPayable", positiveOnly: true },
      { id: "totalLiabilities", label: i18nKey("ИТОГО Обязательства"),      canonical: "totalLiabilities", autoFormula: "totalLiabilities", isSubtotal: true },
      { id: "ltBankLoans",      label: i18nKey("Долгосроч. банк. кредиты"), nsbuCode: "7810", canonical: "ltBankLoans", positiveOnly: true, groupHeader: i18nKey("ДОЛГ (детализация)") },
      { id: "ltOtherLoans",     label: i18nKey("Долгосрочные займы"),        nsbuCode: "7820/7830/7840", positiveOnly: true },
      { id: "stBankLoans",      label: i18nKey("Краткосроч. банк. кредиты"), nsbuCode: "6810", positiveOnly: true },
      { id: "stOtherLoans",     label: i18nKey("Краткосрочные займы"),       nsbuCode: "6820/6830/6840", positiveOnly: true },
      { id: "debt",             label: i18nKey("Финансовый долг"),          canonical: "debt", autoFormula: "debt", isSubtotal: true },
    ],
  },
];

export const DEFAULT_YEARS = [2021, 2022, 2023, 2024, 2025, 2026];

/**
 * Валидация поля: возвращает массив сообщений (пусто = всё ок).
 */
export function validateField(field: FieldDef, value: number | null): string[] {
  const errors: string[] = [];
  if (value == null) return errors;
  if (!isFinite(value)) {
    errors.push(t('Значение не число'));
    return errors;
  }
  if (field.positiveOnly && value < 0) {
    errors.push(t('«{value0}» вводится положительным числом — автоматически взяли модуль', { value0: field.label }));
  }
  if (Math.abs(value) > 1_000_000) {
    errors.push(t('Слишком большое значение: {value0} млрд сум выглядит подозрительно', { value0: value }));
  }
  return errors;
}

/**
 * Возвращает auto-значение для поля (если у него есть autoFormula),
 * вычисленное из значений матрицы для указанного года.
 */
export function computeAutoValue(
  field: FieldDef,
  yearMatrix: Record<string, number | null>,
): number | null {
  if (!field.autoFormula) return null;
  const formula = AUTO_FORMULAS[field.autoFormula];
  if (!formula) return null;
  return formula.fn((f) => {
    const v = yearMatrix[f];
    return v == null ? null : v;
  });
}
