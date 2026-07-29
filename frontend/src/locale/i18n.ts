/**
 * Ядро переводов платформы (Level 2 i18n — строки интерфейса).
 *
 * Принципы:
 *  - КЛЮЧ — русская строка как она написана в коде: `t("Сохранить")`.
 *    Нет ключа в словаре → показывается русский текст (ничего не ломается).
 *  - Словари лежат в src/locale/dict/*.ts и обнаруживаются автоматически
 *    (import.meta.glob) — без общего файла-реестра, модули добавляются
 *    независимо и не конфликтуют.
 *  - Каждый dict-модуль экспортирует:
 *      uz  — ru → узбекская ЛАТИНИЦА (обязательный);
 *      en  — ru → английский (обязательный);
 *      cyr — ru → узбекская КИРИЛЛИЦА, только исключения — по умолчанию
 *            кириллица генерируется транслитерацией латиницы (translit.ts).
 *  - Интерполяция: `t("Сохранено {n} строк", { n })` — плейсхолдеры {var}
 *    переживают перевод.
 *  - Реактивность: t() читает useLocaleStore().current во время рендера,
 *    поэтому все использования перерисовываются при смене языка без
 *    перезагрузки страницы.
 *
 * Использование в компонентах:
 *   import { useI18n } from "@/composables/useI18n";
 *   const { t } = useI18n();
 * В сторах/утилитах (вне setup): import { t } from "@/locale/i18n";
 */
import { getActivePinia } from "pinia";

import { useLocaleStore } from "@/stores/locale";

import type { AppLocale } from "./locales";
import { translitLatinToCyrillic } from "./translit";

export type DictModule = {
  uz?: Record<string, string>;
  en?: Record<string, string>;
  cyr?: Record<string, string>;
};

const UZ: Record<string, string> = {};
const EN: Record<string, string> = {};
const CYR: Record<string, string> = {};

const modules = import.meta.glob("./dict/*.ts", { eager: true }) as Record<string, DictModule>;
for (const m of Object.values(modules)) {
  if (m.uz) Object.assign(UZ, m.uz);
  if (m.en) Object.assign(EN, m.en);
  if (m.cyr) Object.assign(CYR, m.cyr);
}

const cyrCache = new Map<string, string>();

function interpolate(s: string, vars?: Record<string, unknown>): string {
  if (!vars) return s;
  return s.replace(/\{(\w+)\}/g, (m, k) => (k in vars ? String(vars[k]) : m));
}

function currentLocale(): AppLocale {
  try {
    if (getActivePinia()) return useLocaleStore().current;
  } catch {
    /* до инициализации pinia (ранний импорт) — безопасный дефолт */
  }
  return "ru";
}

/** Перевод строки интерфейса. Ключ — русский текст. */
export function t(ru: string, vars?: Record<string, unknown>): string {
  const loc = currentLocale();
  let out = ru;
  if (loc === "uz-latn") {
    out = UZ[ru] ?? ru;
  } else if (loc === "uz-cyr") {
    const override = CYR[ru];
    if (override != null) {
      out = override;
    } else {
      const lat = UZ[ru];
      if (lat != null) {
        let c = cyrCache.get(lat);
        if (c == null) {
          c = translitLatinToCyrillic(lat);
          cyrCache.set(lat, c);
        }
        out = c;
      }
    }
  } else if (loc === "en") {
    out = EN[ru] ?? ru;
  }
  return interpolate(out, vars);
}

/** Счётчик покрытия — для QA-скриптов (сколько ключей в словарях). */
export function dictStats(): { uz: number; en: number; cyr: number } {
  return { uz: Object.keys(UZ).length, en: Object.keys(EN).length, cyr: Object.keys(CYR).length };
}
