/**
 * Locale codes + Intl mapping (Level 1 i18n foundation).
 *
 * The app uses 4 user-facing locales. Each maps to a standard Intl BCP-47
 * code so Intl.NumberFormat / Intl.DateTimeFormat / Intl.RelativeTimeFormat
 * handle the heavy lifting.
 */

export type AppLocale = "ru" | "uz-latn" | "uz-cyr" | "en";

export const APP_LOCALES: AppLocale[] = ["ru", "uz-latn", "uz-cyr", "en"];

export const INTL_LOCALE: Record<AppLocale, string> = {
  "ru":      "ru-RU",
  "uz-latn": "uz-Latn-UZ",
  "uz-cyr":  "uz-Cyrl-UZ",
  "en":      "en-US",
};

/** Default fallback when no language preference exists. */
export const DEFAULT_LOCALE: AppLocale = "ru";

/** All date displays are anchored to Tashkent regardless of user TZ. */
export const APP_TIMEZONE = "Asia/Tashkent";

/** Human-readable names for the language switcher UI. */
export const LOCALE_NAME: Record<AppLocale, string> = {
  "ru":      "Русский",
  "uz-latn": "Oʻzbekcha",
  "uz-cyr":  "Ўзбекча",
  "en":      "English",
};

/** Short code for menus / chips. */
export const LOCALE_SHORT: Record<AppLocale, string> = {
  "ru":      "RU",
  "uz-latn": "UZ",
  "uz-cyr":  "ЎЗ",
  "en":      "EN",
};

/** Type guard for runtime validation of strings (e.g. from localStorage). */
export function isAppLocale(v: unknown): v is AppLocale {
  return typeof v === "string" && (APP_LOCALES as string[]).includes(v);
}
