/**
 * Legacy-equivalent financial editor schema.
 *
 * Replicates the EXACT row labels, sections, and group headers used in the
 * vanilla-JS legacy's "Финансовые данные" editor (function _fdeRender, ~17262).
 *
 * Three sections (tabs):
 *   pnl       — P&L / ОФР                       11 rows
 *   sofp      — SOFP / Баланс                   14 rows
 *   cashflow  — Cash Flow / ДДС                 7 rows
 *
 * Row labels differ between IFRS and NSBU because NSBU uses different
 * Russian terminology AND embeds Russian accounting plan codes (e.g. "(7810)"
 * for long-term bank loans). These exact labels MUST be preserved or the
 * editor stops being recognizable to NSBU users.
 *
 * Auto-calc rules (from legacy _fdeAutoCalc):
 *   grossProfit       = revenue − |cogs|
 *   pbt               = opProfit + finIncome − |finCost|
 *   ebitda            = opProfit + |depreciation|  (or profit + |tax| + |dep| + |finCost|)
 *   totalLiabilities  = ltBorrowings + stBorrowings
 *   debt              = ltBankLoans + ltOtherLoans + stBankLoans + stOtherLoans
 *   netCashChange     = cfo + cfi + cff
 *   totalAssets       = totalNCA + totalCA
 *
 * Expense fields where the user enters POSITIVE numbers (sign auto-applied):
 *   cogs, finCost, tax, depreciation, interestExp, dividendsPaid,
 *   ltBankLoans, ltOtherLoans, ltBorrowings, stBankLoans, stOtherLoans, stBorrowings
 */

export type Section = "pnl" | "sofp" | "cashflow";

export interface FinRow {
  code: string;
  label_ifrs: string;
  label_nsbu: string;
  is_subtotal?: boolean;
  is_calculated?: boolean;
  is_expense?: boolean;     // Show (+) hint; user enters positive, sign applied
  group_header_ifrs?: string;  // If set, render this header BEFORE the row
  group_header_nsbu?: string;
  auto_calc_hint?: string;
}

export const SECTIONS: { id: Section; label_ifrs: string; label_nsbu: string }[] = [
  { id: "pnl",      label_ifrs: "P&L",       label_nsbu: "ОФР"     },
  { id: "sofp",     label_ifrs: "SOFP",      label_nsbu: "Баланс"  },
  { id: "cashflow", label_ifrs: "Cash Flow", label_nsbu: "ДДС"     },
];

export const ROWS_BY_SECTION: Record<Section, FinRow[]> = {
  pnl: [
    { code: "revenue",     label_ifrs: "Выручка",                 label_nsbu: "Выручка",
      group_header_ifrs: "ДОХОДЫ И РАСХОДЫ", group_header_nsbu: "ДОХОДЫ И РАСХОДЫ" },
    { code: "cogs",        label_ifrs: "Себестоимость",            label_nsbu: "Себестоимость",        is_expense: true },
    { code: "grossProfit", label_ifrs: "Валовая прибыль",          label_nsbu: "Валовая прибыль",      is_subtotal: true, is_calculated: true,
      auto_calc_hint: "revenue − |cogs|" },
    { code: "depreciation",label_ifrs: "Амортизация",              label_nsbu: "Амортизация",          is_expense: true },
    { code: "opProfit",    label_ifrs: "Операционная прибыль",     label_nsbu: "Операционная прибыль", is_subtotal: true,
      group_header_ifrs: "ОПЕРАЦИОННЫЙ РЕЗУЛЬТАТ", group_header_nsbu: "ОПЕРАЦИОННЫЙ РЕЗУЛЬТАТ" },
    { code: "finIncome",   label_ifrs: "Финансовые доходы",        label_nsbu: "Доходы от фин. деятельности" },
    { code: "finCost",     label_ifrs: "Финансовые расходы",       label_nsbu: "Расходы от фин. деятельности",  is_expense: true },
    { code: "forex",       label_ifrs: "Курсовая разница",         label_nsbu: "Курсовая разница" },
    { code: "pbt",         label_ifrs: "Прибыль до налога",        label_nsbu: "Прибыль до налога",    is_subtotal: true, is_calculated: true,
      auto_calc_hint: "opProfit + finIncome − |finCost|" },
    { code: "tax",         label_ifrs: "Налог на прибыль",         label_nsbu: "Налог на прибыль",     is_expense: true },
    { code: "profit",      label_ifrs: "Чистая прибыль",           label_nsbu: "Чистая прибыль",       is_subtotal: true },
  ],

  sofp: [
    { code: "ppe",          label_ifrs: "ОС (PPE)",                          label_nsbu: "Основные средства",
      group_header_ifrs: "АКТИВЫ", group_header_nsbu: "АКТИВЫ" },
    { code: "totalNCA",     label_ifrs: "Внеоборотные активы",                label_nsbu: "Внеоборотные активы", is_subtotal: true },
    { code: "totalCA",      label_ifrs: "Оборотные активы",                   label_nsbu: "Оборотные активы",    is_subtotal: true },
    { code: "cash",         label_ifrs: "Денежные средства",                  label_nsbu: "Денежные средства" },
    { code: "totalAssets",  label_ifrs: "ИТОГО Активы",                       label_nsbu: "ИТОГО Активы",        is_subtotal: true, is_calculated: true,
      auto_calc_hint: "totalNCA + totalCA" },
    { code: "equity",       label_ifrs: "Собственный капитал",                label_nsbu: "Собственный капитал",
      group_header_ifrs: "СОБСТВЕННЫЙ КАПИТАЛ", group_header_nsbu: "СОБСТВЕННЫЙ КАПИТАЛ" },
    { code: "ltBorrowings", label_ifrs: "Долгосрочные займы",                 label_nsbu: "Долгосрочные обязательства",        is_expense: true,
      group_header_ifrs: "ОБЯЗАТЕЛЬСТВА", group_header_nsbu: "ОБЯЗАТЕЛЬСТВА" },
    { code: "stBorrowings", label_ifrs: "Краткосрочные займы",                label_nsbu: "Краткосрочные обязательства",       is_expense: true },
    { code: "totalLiabilities", label_ifrs: "Обязательства",                  label_nsbu: "Обязательства",       is_subtotal: true, is_calculated: true,
      auto_calc_hint: "ltBorrowings + stBorrowings" },
    { code: "ltBankLoans",  label_ifrs: "Долгосроч. банк. кредиты",           label_nsbu: "Долгосроч. банк. кредиты (7810)",   is_expense: true,
      group_header_ifrs: "ДОЛГ", group_header_nsbu: "ДОЛГ" },
    { code: "ltOtherLoans", label_ifrs: "Долгосрочные займы",                 label_nsbu: "Долгосрочные займы (7820,7830,7840)", is_expense: true },
    { code: "stBankLoans",  label_ifrs: "Краткосроч. банк. кредиты",          label_nsbu: "Краткосроч. банк. кредиты (6810)",  is_expense: true },
    { code: "stOtherLoans", label_ifrs: "Краткосрочные займы",                label_nsbu: "Краткосрочные займы (6820,6830,6840)", is_expense: true },
    { code: "debt",         label_ifrs: "Долг",                                label_nsbu: "Долг",                is_subtotal: true, is_calculated: true,
      auto_calc_hint: "ltBankLoans + ltOtherLoans + stBankLoans + stOtherLoans" },
  ],

  cashflow: [
    { code: "cfo",           label_ifrs: "Операционный CF",                   label_nsbu: "Операционный ДДС" },
    { code: "cfi",           label_ifrs: "Инвестиционный CF",                 label_nsbu: "Инвестиционный ДДС" },
    { code: "cff",           label_ifrs: "Финансовый CF",                     label_nsbu: "Финансовый ДДС" },
    { code: "netCashChange", label_ifrs: "Изменение ДС",                       label_nsbu: "Изменение ДС",        is_subtotal: true, is_calculated: true,
      auto_calc_hint: "cfo + cfi + cff" },
    { code: "dividendsPaid", label_ifrs: "Дивиденды",                          label_nsbu: "Дивиденды",           is_expense: true },
    { code: "interestExp",   label_ifrs: "Процентные расходы",                 label_nsbu: "Процентные расходы",  is_expense: true },
    { code: "ebitda",        label_ifrs: "EBITDA",                              label_nsbu: "EBITDA",              is_subtotal: true, is_calculated: true,
      auto_calc_hint: "opProfit + |depreciation|" },
  ],
};

/** Year range editor always shows: 2021-2026 base + any extra years from data. */
export const BASE_YEARS = [2021, 2022, 2023, 2024, 2025, 2026];

/** Fields where user enters positive but sign is applied as expense. */
export const EXPENSE_FIELDS = new Set<string>([
  "cogs", "finCost", "tax", "depreciation", "interestExp", "dividendsPaid",
  "ltBankLoans", "ltOtherLoans", "ltBorrowings",
  "stBankLoans", "stOtherLoans", "stBorrowings",
]);

/** Fields the system computes automatically from others. */
export const CALCULATED_FIELDS = new Set<string>([
  "grossProfit", "pbt", "ebitda",
  "totalLiabilities", "debt", "netCashChange", "totalAssets",
]);

/** Compute auto-calc value or null if inputs missing. */
export function autoCalc(code: string, byCode: Record<string, number | null>): number | null {
  const g = (k: string) => byCode[k];
  const has = (k: string) => byCode[k] !== null && byCode[k] !== undefined;

  switch (code) {
    case "grossProfit":
      if (!has("revenue") || !has("cogs")) return null;
      return (g("revenue")! ) - Math.abs(g("cogs")!);
    case "pbt":
      if (!has("opProfit") || !has("finIncome") || !has("finCost")) return null;
      return (g("opProfit")!) + (g("finIncome")!) - Math.abs(g("finCost")!);
    case "ebitda":
      if (has("opProfit") && has("depreciation"))
        return (g("opProfit")!) + Math.abs(g("depreciation")!);
      if (has("profit") && has("tax") && has("depreciation") && has("finCost"))
        return (g("profit")!) + Math.abs(g("tax")!) + Math.abs(g("depreciation")!) + Math.abs(g("finCost")!);
      return null;
    case "totalLiabilities":
      if (!has("ltBorrowings") || !has("stBorrowings")) return null;
      return Math.abs(g("ltBorrowings")!) + Math.abs(g("stBorrowings")!);
    case "debt":
      if (!has("ltBankLoans") || !has("ltOtherLoans") || !has("stBankLoans") || !has("stOtherLoans")) return null;
      return Math.abs(g("ltBankLoans")!) + Math.abs(g("ltOtherLoans")!)
           + Math.abs(g("stBankLoans")!) + Math.abs(g("stOtherLoans")!);
    case "netCashChange":
      if (!has("cfo") || !has("cfi") || !has("cff")) return null;
      return (g("cfo")!) + (g("cfi")!) + (g("cff")!);
    case "totalAssets":
      if (!has("totalNCA") || !has("totalCA")) return null;
      return (g("totalNCA")!) + (g("totalCA")!);
    default:
      return null;
  }
}

/** Map row.code -> display label for the given standard. */
export function labelFor(row: FinRow, standard: "IFRS" | "NSBU"): string {
  return standard === "IFRS" ? row.label_ifrs : row.label_nsbu;
}
