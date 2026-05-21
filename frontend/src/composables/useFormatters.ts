/**
 * useFormatters — reactive wrapper around the pure functions in @/locale.
 *
 * Returns 10 plain functions. Each reads `localeStore.current.value` at call
 * time, so Vue's reactivity tracks the dependency and re-renders the calling
 * component when the language changes. No need to wrap result in computed().
 *
 * Usage:
 *   const fmt = useFormatters();
 *   {{ fmt.fmtMoney(revenue) }}
 *   {{ fmt.fmtDate(loan.signed_at, { long: true }) }}
 */
import {
  fmtNumber,
  fmtNumberCompact,
  fmtPercent,
  fmtMoney,
  fmtMoneyCompact,
  fmtDate,
  fmtDateNumeric,
  fmtTime,
  fmtDateTime,
  fmtRelativeTime,
  type AppLocale,
} from "@/locale";
import type { CurrencyCode } from "@/locale/currencyNames";
import { useLocaleStore } from "@/stores/locale";

type NumberOpts = Parameters<typeof fmtNumber>[2];
type PercentOpts = Parameters<typeof fmtPercent>[2];
type MoneyOpts = Parameters<typeof fmtMoney>[3];
type MoneyCompactOpts = Parameters<typeof fmtMoneyCompact>[3];
type DateOpts = Parameters<typeof fmtDate>[2];
type NumberCompactOpts = Parameters<typeof fmtNumberCompact>[2];

export function useFormatters() {
  const locale = useLocaleStore();

  return {
    /** Reactive ref to the current locale code ('ru' | 'uz-latn' | 'uz-cyr' | 'en'). */
    locale: locale.current,

    /** "62 480 000" / "62,480,000" */
    fmtNumber: (v: number | null | undefined, opts?: NumberOpts) =>
      fmtNumber(v, locale.current as AppLocale, opts),

    /** "62,48 млрд" / "62.48 B" (without currency) */
    fmtNumberCompact: (v: number | null | undefined, opts?: NumberCompactOpts) =>
      fmtNumberCompact(v, locale.current as AppLocale, opts),

    /** "94,3 %" / "94.3%" */
    fmtPercent: (v: number | null | undefined, opts?: PercentOpts) =>
      fmtPercent(v, locale.current as AppLocale, opts),

    /** "62 480 000 сум" / "$1,200.00" */
    fmtMoney: (
      v: number | null | undefined,
      currency: CurrencyCode = "UZS",
      opts?: MoneyOpts,
    ) => fmtMoney(v, locale.current as AppLocale, currency, opts),

    /** "62,48 млрд сум" / "$1.2B" */
    fmtMoneyCompact: (
      v: number | null | undefined,
      currency: CurrencyCode = "UZS",
      opts?: MoneyCompactOpts,
    ) => fmtMoneyCompact(v, locale.current as AppLocale, currency, opts),

    /** "14 мар 2026" / "Mar 14, 2026" */
    fmtDate: (v: string | Date | null | undefined, opts?: DateOpts) =>
      fmtDate(v, locale.current as AppLocale, opts),

    /** "14.03.2026" / "03/14/2026" */
    fmtDateNumeric: (v: string | Date | null | undefined) =>
      fmtDateNumeric(v, locale.current as AppLocale),

    /** "14:32" / "2:32 PM" */
    fmtTime: (v: string | Date | null | undefined) =>
      fmtTime(v, locale.current as AppLocale),

    /** "14 мар, 14:32" */
    fmtDateTime: (v: string | Date | null | undefined) =>
      fmtDateTime(v, locale.current as AppLocale),

    /** "2 ч назад" / "2h ago" */
    fmtRelativeTime: (v: string | Date | null | undefined) =>
      fmtRelativeTime(v, locale.current as AppLocale),
  };
}
