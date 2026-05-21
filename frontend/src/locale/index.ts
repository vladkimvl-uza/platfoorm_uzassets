/**
 * Locale-aware pure formatters (Level 1 i18n).
 *
 * Stateless — every function takes the locale explicitly. Use the reactive
 * `useFormatters()` composable instead from Vue components.
 *
 * All date displays are anchored to Asia/Tashkent regardless of user TZ so
 * dashboards across the country render the same timestamps.
 */
import {
  APP_TIMEZONE,
  INTL_LOCALE,
  type AppLocale,
} from "./locales";
import {
  CURRENCY_SYMBOL,
  CURRENCY_WORD,
  REL_SHORT,
  SCALE_SUFFIX,
  type CurrencyCode,
} from "./currencyNames";

export const DASH = "—";

// ── Numbers ────────────────────────────────────────────────────────────

/** Locale-aware number with thin-space thousand separators for ru/uz, comma for en. */
export function fmtNumber(
  v: number | null | undefined,
  locale: AppLocale,
  opts: { decimals?: number; signed?: boolean; minDecimals?: number } = {},
): string {
  if (v == null || !Number.isFinite(v)) return DASH;
  const max = opts.decimals ?? 0;
  const min = opts.minDecimals ?? max;
  return new Intl.NumberFormat(INTL_LOCALE[locale], {
    minimumFractionDigits: min,
    maximumFractionDigits: max,
    signDisplay: opts.signed ? "exceptZero" : "auto",
  }).format(v);
}

/** Compact number ("12,3 млрд" / "12.3 B") without currency. */
export function fmtNumberCompact(
  v: number | null | undefined,
  locale: AppLocale,
  opts: { decimals?: number } = {},
): string {
  if (v == null || !Number.isFinite(v)) return DASH;
  if (v === 0) return "0";
  const dec = opts.decimals ?? 2;
  const scale = SCALE_SUFFIX[locale];
  const sign = v < 0 ? "-" : "";
  const abs = Math.abs(v);
  if (abs >= 1e12) return `${sign}${fmtNumber(abs / 1e12, locale, { decimals: dec })} ${scale.trillion}`;
  if (abs >= 1e9)  return `${sign}${fmtNumber(abs / 1e9,  locale, { decimals: dec })} ${scale.billion}`;
  if (abs >= 1e6)  return `${sign}${fmtNumber(abs / 1e6,  locale, { decimals: dec })} ${scale.million}`;
  if (abs >= 1e3)  return `${sign}${fmtNumber(abs / 1e3,  locale, { decimals: 1 })} ${scale.thousand}`;
  return sign + fmtNumber(abs, locale, { decimals: 0 });
}

/** Percentage — "94,3 %" for ru/uz, "94.3%" for en. */
export function fmtPercent(
  v: number | null | undefined,
  locale: AppLocale,
  opts: { decimals?: number; signed?: boolean } = {},
): string {
  if (v == null || !Number.isFinite(v)) return DASH;
  const num = fmtNumber(v, locale, { decimals: opts.decimals ?? 1, signed: opts.signed });
  return locale === "en" ? `${num}%` : `${num} %`;
}

// ── Money ──────────────────────────────────────────────────────────────

/** Full money — "62 480 000 сум" / "$1,200.00". */
export function fmtMoney(
  v: number | null | undefined,
  locale: AppLocale,
  currency: CurrencyCode = "UZS",
  opts: { decimals?: number; useSymbol?: boolean } = {},
): string {
  if (v == null || !Number.isFinite(v)) return DASH;
  const decimals = opts.decimals ?? (currency === "UZS" ? 0 : 2);
  const num = fmtNumber(v, locale, { decimals });
  const sym = opts.useSymbol ? CURRENCY_SYMBOL[currency] : "";
  const word = CURRENCY_WORD[locale][currency];

  // For symbol-bearing currencies (USD/EUR/RUB/CNY) and useSymbol=true
  if (sym && currency !== "UZS") {
    return locale === "en" ? `${sym}${num}` : `${num} ${sym}`;
  }
  return `${num} ${word}`;
}

/** Compact money — "62,48 млрд сум" / "$1.2B". */
export function fmtMoneyCompact(
  v: number | null | undefined,
  locale: AppLocale,
  currency: CurrencyCode = "UZS",
  opts: { decimals?: number } = {},
): string {
  if (v == null || !Number.isFinite(v)) return DASH;
  if (v === 0) {
    const word = CURRENCY_WORD[locale][currency];
    return `0 ${word}`;
  }
  const sign = v < 0 ? "-" : "";
  const abs = Math.abs(v);
  const dec = opts.decimals ?? 2;
  const scale = SCALE_SUFFIX[locale];

  let bare = "", suffix = "";
  if (abs >= 1e12)      { bare = fmtNumber(abs / 1e12, locale, { decimals: dec }); suffix = scale.trillion; }
  else if (abs >= 1e9)  { bare = fmtNumber(abs / 1e9,  locale, { decimals: dec }); suffix = scale.billion; }
  else if (abs >= 1e6)  { bare = fmtNumber(abs / 1e6,  locale, { decimals: dec }); suffix = scale.million; }
  else if (abs >= 1e3)  { bare = fmtNumber(abs / 1e3,  locale, { decimals: 1 });    suffix = scale.thousand; }
  else {
    return `${sign}${fmtNumber(abs, locale, { decimals: 0 })} ${CURRENCY_WORD[locale][currency]}`;
  }

  if (currency === "USD" || currency === "EUR" || currency === "RUB" || currency === "CNY") {
    const sym = CURRENCY_SYMBOL[currency];
    if (locale === "en") return `${sign}${sym}${bare}${suffix}`;
    return `${sign}${bare} ${suffix} ${sym}`;
  }
  // UZS
  const word = CURRENCY_WORD[locale][currency];
  return locale === "en" ? `${sign}${bare}${suffix} ${word}` : `${sign}${bare} ${suffix} ${word}`;
}

// ── Dates ──────────────────────────────────────────────────────────────

/** Date short — "14 мар 2026" / "Mar 14, 2026". */
export function fmtDate(
  v: string | Date | null | undefined,
  locale: AppLocale,
  opts: { includeYear?: boolean; long?: boolean } = {},
): string {
  if (!v) return DASH;
  const d = typeof v === "string" ? new Date(v) : v;
  if (isNaN(d.getTime())) return DASH;

  const includeYear = opts.includeYear !== false;
  const dtfOpts: Intl.DateTimeFormatOptions = {
    day: "numeric",
    month: opts.long ? "long" : "short",
    timeZone: APP_TIMEZONE,
  };
  if (includeYear) dtfOpts.year = "numeric";
  return new Intl.DateTimeFormat(INTL_LOCALE[locale], dtfOpts).format(d);
}

/** Numeric date — "14.03.2026" / "03/14/2026". */
export function fmtDateNumeric(v: string | Date | null | undefined, locale: AppLocale): string {
  if (!v) return DASH;
  const d = typeof v === "string" ? new Date(v) : v;
  if (isNaN(d.getTime())) return DASH;
  return new Intl.DateTimeFormat(INTL_LOCALE[locale], {
    day: "2-digit", month: "2-digit", year: "numeric",
    timeZone: APP_TIMEZONE,
  }).format(d);
}

/** Time — "14:32" / "2:32 PM". */
export function fmtTime(v: string | Date | null | undefined, locale: AppLocale): string {
  if (!v) return DASH;
  const d = typeof v === "string" ? new Date(v) : v;
  if (isNaN(d.getTime())) return DASH;
  return new Intl.DateTimeFormat(INTL_LOCALE[locale], {
    hour: "numeric", minute: "2-digit",
    timeZone: APP_TIMEZONE,
    hour12: locale === "en",
  }).format(d);
}

/** Datetime — "14 мар, 14:32" / "Mar 14, 2:32 PM". */
export function fmtDateTime(v: string | Date | null | undefined, locale: AppLocale): string {
  if (!v) return DASH;
  return `${fmtDate(v, locale, { includeYear: false })}, ${fmtTime(v, locale)}`;
}

// ── Relative time ──────────────────────────────────────────────────────

/** "2 ч назад" / "2 soat oldin" / "2h ago". Uses Intl.RelativeTimeFormat with
 *  hand-rolled Uzbek fallback (Intl support for uz is limited in some browsers). */
export function fmtRelativeTime(v: string | Date | null | undefined, locale: AppLocale): string {
  if (!v) return DASH;
  const d = typeof v === "string" ? new Date(v) : v;
  if (isNaN(d.getTime())) return DASH;

  const diffMs = d.getTime() - Date.now();
  const absSec = Math.abs(diffMs) / 1000;
  const future = diffMs > 0;

  // Hand-rolled for uz-latn/uz-cyr because Intl's uz coverage is uneven.
  if (locale === "uz-latn" || locale === "uz-cyr") {
    const t = REL_SHORT[locale];
    if (absSec < 60)        return t.now;
    if (absSec < 3600)      return t.minute(Math.round(absSec / 60), future);
    if (absSec < 86400)     return t.hour(Math.round(absSec / 3600), future);
    if (absSec < 604800)    return t.day(Math.round(absSec / 86400), future);
    if (absSec < 2592000)   return t.week(Math.round(absSec / 604800), future);
    if (absSec < 31536000)  return t.month(Math.round(absSec / 2592000), future);
    return t.year(Math.round(absSec / 31536000), future);
  }

  try {
    const rtf = new Intl.RelativeTimeFormat(INTL_LOCALE[locale], { numeric: "auto", style: "short" });
    if (absSec < 60)        return rtf.format(Math.round(diffMs / 1000),         "second");
    if (absSec < 3600)      return rtf.format(Math.round(diffMs / 60_000),       "minute");
    if (absSec < 86400)     return rtf.format(Math.round(diffMs / 3_600_000),    "hour");
    if (absSec < 604800)    return rtf.format(Math.round(diffMs / 86_400_000),   "day");
    if (absSec < 2592000)   return rtf.format(Math.round(diffMs / 604_800_000),  "week");
    if (absSec < 31536000)  return rtf.format(Math.round(diffMs / 2_592_000_000),"month");
    return rtf.format(Math.round(diffMs / 31_536_000_000), "year");
  } catch {
    // Fallback to ru shape
    const t = REL_SHORT["ru"];
    if (absSec < 60)        return t.now;
    if (absSec < 3600)      return t.minute(Math.round(absSec / 60), future);
    if (absSec < 86400)     return t.hour(Math.round(absSec / 3600), future);
    if (absSec < 604800)    return t.day(Math.round(absSec / 86400), future);
    if (absSec < 2592000)   return t.week(Math.round(absSec / 604800), future);
    if (absSec < 31536000)  return t.month(Math.round(absSec / 2592000), future);
    return t.year(Math.round(absSec / 31536000), future);
  }
}

// ── Re-exports ──────────────────────────────────────────────────────────
export * from "./locales";
export * from "./currencyNames";
