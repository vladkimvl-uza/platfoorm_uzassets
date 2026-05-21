/**
 * Locale Pinia store — single source of truth for the active UI language.
 *
 * platform doesn't yet have full string translations, but it DOES support
 * locale-aware number/date/currency formatting via useFormatters. This store
 * holds the locale; when it changes, every component using useFormatters
 * re-renders automatically.
 *
 * Persistence: localStorage `uza-locale-v1`. Default: 'ru'.
 */
import { defineStore } from "pinia";
import { computed, ref } from "vue";
import {
  APP_LOCALES,
  DEFAULT_LOCALE,
  INTL_LOCALE,
  LOCALE_NAME,
  LOCALE_SHORT,
  isAppLocale,
  type AppLocale,
} from "@/locale/locales";

const LS_KEY = "uza-locale-v1";

function _loadInitial(): AppLocale {
  try {
    const raw = localStorage.getItem(LS_KEY);
    if (isAppLocale(raw)) return raw;
  } catch {
    // SSR / disabled storage — fall through
  }
  return DEFAULT_LOCALE;
}

export const useLocaleStore = defineStore("locale", () => {
  const current = ref<AppLocale>(_loadInitial());

  const intl = computed<string>(() => INTL_LOCALE[current.value]);
  const name = computed<string>(() => LOCALE_NAME[current.value]);
  const short = computed<string>(() => LOCALE_SHORT[current.value]);

  function set(loc: AppLocale): void {
    if (!APP_LOCALES.includes(loc)) return;
    if (current.value === loc) return;
    current.value = loc;
    try {
      localStorage.setItem(LS_KEY, loc);
    } catch {
      /* ignore */
    }
    // Reflect in <html lang> for accessibility / native pseudo-elements
    try {
      const tag = loc === "uz-latn" ? "uz" : (loc === "uz-cyr" ? "uz-Cyrl" : loc);
      document.documentElement.setAttribute("lang", tag);
    } catch {
      /* SSR */
    }
  }

  function next(): void {
    const i = APP_LOCALES.indexOf(current.value);
    set(APP_LOCALES[(i + 1) % APP_LOCALES.length]);
  }

  return { current, intl, name, short, set, next };
});

/** Backwards-compat alias for the composable-style API the handoff describes. */
export function useLocale() {
  return useLocaleStore();
}
