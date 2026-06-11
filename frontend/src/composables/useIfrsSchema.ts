/**
 * useIfrsSchema — IFRS-editor schema (Pack 7.60).
 *
 * Mirrors useNsbuSchema but with 4 sections (P&L / OCI / SOFP / CF)
 * and IFRS-specific auto-formulas (Free Cash Flow, Total Comprehensive Income,
 * Net Debt, etc.).
 *
 * Section keys (must match backend section_to_rtype map):
 *   pnl  → PL    (Profit & Loss / ОФР)
 *   oci  → OCI   (Other Comprehensive Income / ОПД)
 *   sofp → BS    (Statement of Financial Position / Балансовый отчёт)
 *   cf   → CF    (Cash Flow Statement / ДДС)
 */

export type FieldId = string;
export type SectionId = "pnl" | "oci" | "sofp" | "cf";

export interface FieldDef {
  id: FieldId;
  label: string;
  /** Подзаголовок секции, рисуемый ПЕРЕД этим полем */
  groupHeader?: string;
  /** Поле-расход — вводится положительным числом */
  positiveOnly?: boolean;
  /** Авто-расчёт: имя формулы из AUTO_FORMULAS */
  autoFormula?: string;
  /** Подкатегория жирная (subtotal-style row) */
  isSubtotal?: boolean;
  /** Маппинг к canonical metric для портфельных агрегаций */
  canonical?: string;
  /** Custom user-added — НЕ из стандартного списка */
  isCustom?: boolean;
}

export interface SectionDef {
  id: SectionId;
  label: string;
  fields: FieldDef[];
}

export interface AutoFormulaDef {
  expr: string;
  fn: (g: (f: string) => number | null) => number | null;
}

/**
 * Список canonical metric кодов — общий для NSBU и IFRS.
 * Должен совпадать с _PORTFOLIO_METRIC_ALIASES values в backend.
 */
export const CANONICAL_METRICS: { code: string; label: string; section: SectionId }[] = [
  { code: "revenue",       label: "Выручка",                 section: "pnl" },
  { code: "cogs",          label: "Себестоимость",           section: "pnl" },
  { code: "grossProfit",   label: "Валовая прибыль",         section: "pnl" },
  { code: "opProfit",      label: "Операционная прибыль",    section: "pnl" },
  { code: "depreciation",  label: "Амортизация",             section: "pnl" },
  { code: "finCost",       label: "Финансовые расходы",      section: "pnl" },
  { code: "finIncome",     label: "Финансовые доходы",       section: "pnl" },
  { code: "interestExp",   label: "Процентные расходы",      section: "pnl" },
  { code: "forex",         label: "Курсовая разница",        section: "pnl" },
  { code: "pbt",           label: "Прибыль до налога",       section: "pnl" },
  { code: "tax",           label: "Налог на прибыль",        section: "pnl" },
  { code: "profit",        label: "Чистая прибыль",          section: "pnl" },
  { code: "ebitda",        label: "EBITDA",                   section: "pnl" },
  { code: "total_comprehensive_income", label: "Совокупный доход", section: "oci" },
  { code: "totalAssets",      label: "Итого активы",            section: "sofp" },
  { code: "totalLiabilities", label: "Итого обязательства",     section: "sofp" },
  { code: "equity",           label: "Собственный капитал",     section: "sofp" },
  { code: "totalCA",          label: "Оборотные активы",        section: "sofp" },
  { code: "totalNCA",         label: "Внеоборотные активы",     section: "sofp" },
  { code: "ppe",              label: "Основные средства",       section: "sofp" },
  { code: "cash",             label: "Денежные средства",       section: "sofp" },
  { code: "debt",             label: "Финансовый долг",         section: "sofp" },
  { code: "ltBorrowings",     label: "Долгосрочные обяз-ва",    section: "sofp" },
  { code: "stBorrowings",     label: "Краткосрочные обяз-ва",   section: "sofp" },
  { code: "cfo",              label: "Денежный поток от опер.",    section: "cf" },
  { code: "cfi",              label: "Денежный поток от инвест.",  section: "cf" },
  { code: "cff",              label: "Денежный поток от фин.",     section: "cf" },
  { code: "freeCashFlow",     label: "Свободный денежный поток",   section: "cf" },
];

/** IFRS-specific auto-formulas. */
export const AUTO_FORMULAS: Record<string, AutoFormulaDef> = {
  grossProfit: {
    expr: "revenue − |cogs|",
    fn: (g) => {
      const r = g("revenue"), c = g("cogs");
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
      if (pbt == null) return null;
      return pbt - Math.abs(tax || 0);
    },
  },
  ebitda: {
    expr: "opProfit + |depreciation|",
    fn: (g) => {
      const op = g("opProfit"), dp = g("depreciation");
      if (op != null && dp != null) return op + Math.abs(dp);
      const pr = g("profit"), tx = g("tax"), fc = g("finCost");
      if (pr != null) return pr + Math.abs(tx || 0) + Math.abs(dp || 0) + Math.abs(fc || 0);
      return null;
    },
  },
  // IFRS-specific
  total_comprehensive_income: {
    expr: "profit + OCI components",
    fn: (g) => {
      const p = g("profit");
      if (p == null) return null;
      const ct = g("oci_currency_translation") || 0;
      const rv = g("oci_revaluation_ppe") || 0;
      const ac = g("oci_actuarial") || 0;
      const hg = g("oci_hedge_reserve") || 0;
      const fv = g("oci_fvtoci") || 0;
      return p + ct + rv + ac + hg + fv;
    },
  },
  totalAssets: {
    expr: "totalNCA + totalCA",
    fn: (g) => {
      const nca = g("totalNCA"), ca = g("totalCA");
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
  // CF auto-formulas
  cfo: {
    expr: "cfo_pbt + |cfo_depreciation| + cfo_working_capital − |cfo_interest_paid| − |cfo_tax_paid|",
    fn: (g) => {
      const pbt = g("cfo_pbt"), dep = g("cfo_depreciation"), wc = g("cfo_working_capital");
      const ip = g("cfo_interest_paid"), tp = g("cfo_tax_paid");
      if (pbt == null && dep == null && wc == null) return null;
      return (pbt || 0) + Math.abs(dep || 0) + (wc || 0) - Math.abs(ip || 0) - Math.abs(tp || 0);
    },
  },
  cfi: {
    expr: "−|cfi_capex| − |cfi_acquisitions|",
    fn: (g) => {
      const cx = g("cfi_capex"), ac = g("cfi_acquisitions");
      if (cx == null && ac == null) return null;
      return -Math.abs(cx || 0) - Math.abs(ac || 0);
    },
  },
  cff: {
    expr: "cff_borrowings − |cff_repayments| − |dividendsPaid|",
    fn: (g) => {
      const b = g("cff_borrowings"), r = g("cff_repayments"), d = g("dividendsPaid");
      if (b == null && r == null && d == null) return null;
      return (b || 0) - Math.abs(r || 0) - Math.abs(d || 0);
    },
  },
  netCashChange: {
    expr: "cfo + cfi + cff",
    fn: (g) => {
      const o = g("cfo"), i = g("cfi"), f = g("cff");
      if (o == null && i == null && f == null) return null;
      return (o || 0) + (i || 0) + (f || 0);
    },
  },
  freeCashFlow: {
    expr: "cfo − |cfi_capex|",
    fn: (g) => {
      const o = g("cfo"), cx = g("cfi_capex");
      if (o == null) return null;
      return o - Math.abs(cx || 0);
    },
  },
};

/** Стандартная схема IFRS — 4 секции: P&L / OCI / Balance / Cash Flow. */
export const STANDARD_SCHEMA: SectionDef[] = [
  {
    id: "pnl",
    label: "ОФР · Profit & Loss",
    fields: [
      { id: "revenue",       label: "Revenue · Выручка",                  canonical: "revenue", groupHeader: "CONTINUING OPERATIONS" },
      { id: "cogs",          label: "Cost of sales · Себестоимость",      canonical: "cogs", positiveOnly: true },
      { id: "grossProfit",   label: "Gross profit · Валовая прибыль",     canonical: "grossProfit", autoFormula: "grossProfit", isSubtotal: true },
      { id: "opProfit",      label: "Operating profit · Опер. прибыль",   canonical: "opProfit", groupHeader: "OPERATING RESULT" },
      { id: "depreciation",  label: "D&A · Амортизация",                   canonical: "depreciation", positiveOnly: true },
      { id: "finIncome",     label: "Finance income · Фин. доходы",       canonical: "finIncome" },
      { id: "finCost",       label: "Finance costs · Фин. расходы",       canonical: "finCost", positiveOnly: true },
      { id: "interestExp",   label: "  Interest expense (детализация)",  canonical: "interestExp", positiveOnly: true },
      { id: "forex",         label: "Forex gains/losses · Курсовая разница", canonical: "forex" },
      { id: "pbt",           label: "Profit before tax · Прибыль до налога", canonical: "pbt", autoFormula: "pbt", isSubtotal: true, groupHeader: "PERIOD RESULTS" },
      { id: "tax",           label: "Income tax · Налог на прибыль",      canonical: "tax", positiveOnly: true },
      { id: "profit",        label: "Net profit · Чистая прибыль",        canonical: "profit", autoFormula: "profit", isSubtotal: true },
      { id: "ebitda",        label: "EBITDA",                              canonical: "ebitda", autoFormula: "ebitda", isSubtotal: true },
    ],
  },
  {
    id: "oci",
    label: "ОПД · OCI",
    fields: [
      { id: "oci_currency_translation", label: "Currency translation · Курсовые разницы пересчёта", groupHeader: "OTHER COMPREHENSIVE INCOME" },
      { id: "oci_revaluation_ppe",      label: "PPE revaluation · Переоценка основных средств" },
      { id: "oci_actuarial",            label: "Actuarial gains/losses · Актуарные доходы/расходы" },
      { id: "oci_hedge_reserve",        label: "Hedge reserve · Резерв хеджирования" },
      { id: "oci_fvtoci",               label: "FVTOCI · Финансовые активы по справедливой стоимости" },
      { id: "total_comprehensive_income", label: "Total comprehensive income · Совокупный доход",
        canonical: "total_comprehensive_income", autoFormula: "total_comprehensive_income", isSubtotal: true },
    ],
  },
  {
    id: "sofp",
    label: "Баланс · SOFP",
    fields: [
      { id: "ppe",              label: "PPE · Основные средства",          canonical: "ppe", groupHeader: "ASSETS" },
      { id: "totalNCA",         label: "Total non-current assets",         canonical: "totalNCA", isSubtotal: true },
      { id: "cash",             label: "Cash & equivalents · Денежные средства", canonical: "cash" },
      { id: "totalCA",          label: "Total current assets",             canonical: "totalCA", isSubtotal: true },
      { id: "totalAssets",      label: "TOTAL ASSETS · ИТОГО Активы",      canonical: "totalAssets", autoFormula: "totalAssets", isSubtotal: true },
      { id: "equity",           label: "Equity · Собственный капитал",     canonical: "equity", groupHeader: "EQUITY & LIABILITIES", isSubtotal: true },
      { id: "ltBorrowings",     label: "LT borrowings (total)",             canonical: "ltBorrowings", positiveOnly: true, isSubtotal: true, groupHeader: "LIABILITIES" },
      { id: "stBorrowings",     label: "ST borrowings (total)",             canonical: "stBorrowings", positiveOnly: true, isSubtotal: true },
      { id: "totalLiabilities", label: "TOTAL LIABILITIES",                  canonical: "totalLiabilities", autoFormula: "totalLiabilities", isSubtotal: true },
      { id: "ltBankLoans",      label: "  LT bank loans",                   canonical: "ltBankLoans", positiveOnly: true, groupHeader: "DEBT (detail)" },
      { id: "ltOtherLoans",     label: "  LT other loans",                  positiveOnly: true },
      { id: "stBankLoans",      label: "  ST bank loans",                   positiveOnly: true },
      { id: "stOtherLoans",     label: "  ST other loans",                  positiveOnly: true },
      { id: "longTermDebt",     label: "Long-term debt (separately)",      positiveOnly: true },
      { id: "debt",             label: "Total debt · Финансовый долг",     canonical: "debt", autoFormula: "debt", isSubtotal: true },
    ],
  },
  {
    id: "cf",
    label: "ДДС · Cash Flow",
    fields: [
      { id: "cfo",                 label: "CFO · Поток от операц. деятельности",      canonical: "cfo", autoFormula: "cfo", isSubtotal: true, groupHeader: "OPERATING ACTIVITIES" },
      { id: "cfo_pbt",             label: "  Profit before tax (adj)" },
      { id: "cfo_depreciation",    label: "  Depreciation (adj)",                      positiveOnly: true },
      { id: "cfo_working_capital", label: "  Change in working capital" },
      { id: "cfo_interest_paid",   label: "  Interest paid",                            positiveOnly: true },
      { id: "cfo_tax_paid",        label: "  Income tax paid",                          positiveOnly: true },
      { id: "cfi",                 label: "CFI · Поток от инвест. деятельности",       canonical: "cfi", autoFormula: "cfi", isSubtotal: true, groupHeader: "INVESTING ACTIVITIES" },
      { id: "cfi_capex",           label: "  CapEx · Капитальные затраты",              positiveOnly: true },
      { id: "cfi_acquisitions",    label: "  Acquisitions",                              positiveOnly: true },
      { id: "cff",                 label: "CFF · Поток от фин. деятельности",          canonical: "cff", autoFormula: "cff", isSubtotal: true, groupHeader: "FINANCING ACTIVITIES" },
      { id: "cff_borrowings",      label: "  Proceeds from borrowings" },
      { id: "cff_repayments",      label: "  Repayments of borrowings",                positiveOnly: true },
      { id: "dividendsPaid",       label: "  Dividends paid",                            positiveOnly: true },
      { id: "netCashChange",       label: "Net change in cash",                          autoFormula: "netCashChange", isSubtotal: true, groupHeader: "TOTALS" },
      { id: "freeCashFlow",        label: "Free Cash Flow (FCF)",                        canonical: "freeCashFlow", autoFormula: "freeCashFlow", isSubtotal: true },
    ],
  },
];

export const DEFAULT_YEARS = [2021, 2022, 2023, 2024, 2025, 2026];

/** Validate field value. Returns array of error messages. */
export function validateField(field: FieldDef, value: number | null): string[] {
  const errors: string[] = [];
  if (value == null) return errors;
  if (!isFinite(value)) {
    errors.push("Значение не число");
    return errors;
  }
  if (field.positiveOnly && value < 0) {
    errors.push(`«${field.label}» вводится положительным числом — автоматически взяли модуль`);
  }
  if (Math.abs(value) > 1_000_000) {
    errors.push(`Слишком большое значение: ${value} млрд UZS выглядит подозрительно`);
  }
  return errors;
}

/** Compute auto-value for a field given the year matrix. */
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
