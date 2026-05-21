/**
 * cpHelpers — клиентские helpers для Кредитного портфеля.
 *
 *   - cpClassifyLender (line 25982)
 *   - cpBankShortName (line 25870)
 *   - cpMatBucket (line 25845)
 *   - cpFmtDateShort (line 25854)
 *   - cpDaysBetween, cpYearOf
 *   - fmtMoneyLoan (line 26483)
 *
 * Эти функции работают на одном кредите/строке и НЕ требуют backend.
 */
import type { Loan } from "@/api/creditPortfolio";

export type LenderType = "bond" | "foreign" | "local" | "state";

export const LENDER_TYPE_LABEL: Record<LenderType, string> = {
  bond: "Бонд",
  foreign: "Иностранный",
  local: "Местный",
  state: "Государственный",
};

export const LENDER_TYPE_FULL: Record<LenderType, string> = {
  bond: "Еврооблигации",
  foreign: "Иностранные банки и фонды",
  local: "Местные коммерческие банки",
  state: "Государственные банки и фонды",
};

export const LENDER_TYPE_COLOR: Record<LenderType, string> = {
  bond: "#C99B5C",
  foreign: "#5DBFA1",
  local: "#5478B0",
  state: "#C97070",
};

export const CURRENCY_COLOR: Record<string, string> = {
  USD: "#7F77DD",
  EUR: "#0A7B5E",
  CNY: "#EF9F27",
  JPY: "#E24B4A",
  SDR: "#9C8AC8",
  RUB: "#5B7FBC",
  UZS: "#888780",
};

export function asOfDate(asOf: string | null | undefined): Date {
  if (!asOf) return new Date("2026-01-01");
  const d = new Date(asOf);
  return isNaN(d.getTime()) ? new Date("2026-01-01") : d;
}

/** Классификация банка → тип кредитора (если backend не выставил) */
export function classifyLender(bank: string | null | undefined): LenderType {
  const b = (bank || "").toLowerCase();
  if (
    b.indexOf("евробонд") >= 0 ||
    b.indexOf("eurobond") >= 0 ||
    b.indexOf("(келажак)") >= 0 ||
    b.indexOf("(хумо)") >= 0
  )
    return "bond";
  if (b.indexOf("нбу") >= 0) return "state";
  if (b.indexOf("фонд") >= 0 && (b.indexOf("реконстр") >= 0 || b.indexOf("развит") >= 0))
    return "state";
  if (b.indexOf("фрр") >= 0) return "state";
  if (b.indexOf("фонд шелкового") >= 0 || b.indexOf("silk road") >= 0) return "state";
  if (
    b.indexOf("china development") >= 0 ||
    b.indexOf("korea exim") >= 0 ||
    b.indexOf("eximbank") >= 0 ||
    b.indexOf("jbic") >= 0 ||
    b.indexOf("ebrd") >= 0 ||
    b.indexOf("world bank") >= 0 ||
    b.indexOf("adb") >= 0 ||
    b.indexOf("aiib") >= 0
  )
    return "state";
  const localKw = [
    "узпромстройбанк",
    "капиталбанк",
    "алока",
    "хамкор",
    "ипотека",
    "ziraat bank uzbekistan",
    "kdb bank uzbekistan",
    "банк развития",
    "асака",
    "ситибанк",
    "микрокредит",
  ];
  for (let i = 0; i < localKw.length; i++) {
    if (b.indexOf(localKw[i]) >= 0) return "local";
  }
  return "foreign";
}

/** Короткое имя банка (без АКБ/АО/ЧАБ/ООО, без кавычек) */
export function bankShortName(b: string | null | undefined): string {
  if (!b) return "";
  return b.replace(/АКБ |АО |ЧАБ |ООО /g, "").replace(/"/g, "").trim();
}

/** Дни между двумя датами (ISO/yyyy-mm-dd) */
export function daysBetween(a: Date | string, b: Date | string): number {
  const da = a instanceof Date ? a : new Date(a);
  const db = b instanceof Date ? b : new Date(b);
  return Math.floor((db.getTime() - da.getTime()) / 86400_000);
}

/** Год даты или null */
export function yearOf(s: string | null | undefined): number | null {
  if (!s) return null;
  const d = new Date(s);
  return isNaN(d.getTime()) ? null : d.getFullYear();
}

/** Бакет погашения относительно даты отчётности */
export type MatBucket = "overdue" | "<1 года" | "1–3 года" | "3–5 лет" | ">5 лет" | "unknown";

export function matBucket(due: string | null | undefined, asOf: Date): MatBucket {
  if (!due) return "unknown";
  const d = daysBetween(asOf, due);
  if (isNaN(d)) return "unknown";
  if (d < 0) return "overdue";
  if (d <= 365) return "<1 года";
  if (d <= 365 * 3) return "1–3 года";
  if (d <= 365 * 5) return "3–5 лет";
  return ">5 лет";
}

/** @deprecated Locale-blind helper. Use `useFormatters().fmtDateNumeric(s)` instead. */
export function fmtDateShort(s: string | null | undefined): string {
  if (!s) return "—";
  const d = new Date(s);
  if (isNaN(d.getTime())) return "—";
  return d.toLocaleDateString("ru-RU", {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
  });
}

/** @deprecated Locale-blind helper. Use `useFormatters().fmtMoneyCompact(amt, currency)` instead. */
export function fmtMoneyLoan(loan: Pick<Loan, "currency" | "debt_currency">): string {
  const amt = Number(loan.debt_currency ?? 0);
  if (!amt) return "—";
  const cur = loan.currency || "USD";
  if (cur === "UZS") {
    if (amt >= 1e12) return `${(amt / 1e12).toFixed(2)} трлн сум`;
    if (amt >= 1e9) return `${(amt / 1e9).toFixed(1)} млрд сум`;
    if (amt >= 1e6) return `${(amt / 1e6).toFixed(0)} млн сум`;
    return `${amt.toLocaleString("ru-RU")} сум`;
  }
  const sym: Record<string, string> = {
    USD: "$",
    EUR: "€",
    GBP: "£",
    JPY: "¥",
    CNY: "¥",
  };
  const suf: Record<string, string> = { RUB: " ₽", KRW: " ₩", SDR: " SDR" };
  let fmt: string;
  if (amt >= 1e9) fmt = `${(amt / 1e9).toFixed(2)}B`;
  else if (amt >= 1e6) fmt = `${(amt / 1e6).toFixed(1)}M`;
  else if (amt >= 1e3) fmt = `${(amt / 1e3).toFixed(0)}K`;
  else fmt = amt.toFixed(0);
  if (sym[cur]) return sym[cur] + fmt;
  if (suf[cur]) return fmt + suf[cur];
  return fmt + " " + cur;
}

/** @deprecated Locale-blind helper. Use `useFormatters().fmtMoneyCompact(usd, "USD")` instead. */
export function fmtUsdMln(usd: number, decimals = 0): string {
  return `$${(usd / 1e6).toFixed(decimals)}M`;
}

/** Безопасный escape HTML (для inline title=""/.innerHTML вкраплений) */
export function esc(s: string | null | undefined): string {
  if (s == null) return "";
  return String(s)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}
