/**
 * displayNames.ts
 * ─────────────────────────────────────────────────────────────────
 * Единый источник истины для отображаемых имён компаний и секторов.
 *
 * ПРАВИЛО:
 *   • RU: короткое имя компании, затем name_ru;
 *   • UZ: name_uz с нормализацией в выбранную графику;
 *   • EN: name_en;
 *   • если локализованное поле пусто, используется русский fallback.
 *
 * Это правило применяется ВЕЗДЕ: bar-чарты, таблицы, модалки, badges,
 * dropdowns. Если админ заполнил поле «Сокращённое имя» в Companies admin,
 * оно используется везде. Не заполнил — везде полное name_ru.
 *
 * Все компоненты ДОЛЖНЫ импортировать companyDisplayName/sectorDisplayName
 * вместо прямого `co.name_ru` / `co.name_short` или своего shortName().
 *
 * Для legacy-данных где доступен только `name` (без распакованной модели):
 *   useCompaniesStore.getCompanyName(code) — резолвит из кэшированного store.
 */

import { shallowRef } from "vue";
import { getCurrentLocale } from "@/locale/i18n";
import {
  translitCyrillicToLatin,
  translitLatinToCyrillic,
} from "@/locale/translit";

/** Минимальный shape компании, достаточный для resolving имени. */
export interface CompanyNameShape {
  id?: string | null;
  code?: string | null;
  name_ru?: string | null;
  name_uz?: string | null;
  name_en?: string | null;
  name_short?: string | null;
  /** Иногда серверу передаются псевдонимы; используем как fallback. */
  name?: string | null;
}

/** Минимальный shape сектора. */
export interface SectorNameShape {
  id?: string | null;
  name_ru?: string | null;
  name_uz?: string | null;
  name_en?: string | null;
  name?: string | null;
  code?: string | null;
}

const companyAliases = shallowRef(new Map<string, CompanyNameShape>());
const sectorAliases = shallowRef(new Map<string, SectorNameShape>());

function aliasKey(value: string | null | undefined): string {
  return (value || "")
    .trim()
    .toLocaleLowerCase()
    .replace(/[«»“”„\"]/g, "")
    .replace(/\s+/g, " ");
}

/** Keep one reactive alias catalog for legacy endpoints that only return a display string. */
export function registerDisplayNameCatalog(
  companies: readonly CompanyNameShape[],
  sectors: readonly SectorNameShape[],
): void {
  const nextCompanies = new Map<string, CompanyNameShape>();
  for (const company of companies) {
    for (const alias of [
      company.id,
      company.code,
      company.name,
      company.name_short,
      company.name_ru,
      company.name_uz,
      company.name_en,
    ]) {
      const key = aliasKey(alias);
      if (key) nextCompanies.set(key, company);
    }
  }

  const nextSectors = new Map<string, SectorNameShape>();
  for (const sector of sectors) {
    for (const alias of [
      sector.id,
      sector.code,
      sector.name,
      sector.name_ru,
      sector.name_uz,
      sector.name_en,
    ]) {
      const key = aliasKey(alias);
      if (key) nextSectors.set(key, sector);
    }
  }

  companyAliases.value = nextCompanies;
  sectorAliases.value = nextSectors;
}

const CYRILLIC_RE = /[А-Яа-яЁёЎўҒғҚқҲҳ]/; // i18n-exempt: script detector, never rendered

function localizedUzName(value: string, locale: "uz-latn" | "uz-cyr"): string {
  if (locale === "uz-latn") {
    return CYRILLIC_RE.test(value) ? translitCyrillicToLatin(value) : value;
  }
  return CYRILLIC_RE.test(value) ? value : translitLatinToCyrillic(value);
}


/**
 * Получить отображаемое имя компании по единому правилу.
 *
 *   companyDisplayName({ name_ru: 'АО «Узтрансгаз»', name_short: 'Узтрансгаз' })
 *     → 'Узтрансгаз'
 *
 *   companyDisplayName({ name_ru: 'АО «Алмалыкский ГМК»', name_short: null })
 *     → 'АО «Алмалыкский ГМК»'
 *
 *   companyDisplayName(null)        → ''
 *   companyDisplayName(undefined)   → ''
 */
export function companyDisplayName(co: CompanyNameShape | null | undefined): string {
  if (!co) return "";
  const fallback = (co.name_short || co.name_ru || co.name || "").trim();
  const locale = getCurrentLocale();
  if (locale === "en") return (co.name_en || "").trim() || fallback;
  if (locale === "uz-latn" || locale === "uz-cyr") {
    const uz = (co.name_uz || "").trim();
    return uz ? localizedUzName(uz, locale) : fallback;
  }
  return fallback;
}


/**
 * Получить отображаемое имя сектора по единому правилу.
 *
 *   sectorDisplayName({ name_ru: 'Горнодобывающий', code: 'mining' })
 *     → 'Горнодобывающий'
 */
export function sectorDisplayName(sec: SectorNameShape | null | undefined): string {
  if (!sec) return "";
  const fallback = (sec.name_ru || sec.name || sec.code || "").trim();
  const locale = getCurrentLocale();
  if (locale === "en") return (sec.name_en || "").trim() || fallback;
  if (locale === "uz-latn" || locale === "uz-cyr") {
    const uz = (sec.name_uz || "").trim();
    return uz ? localizedUzName(uz, locale) : fallback;
  }
  return fallback;
}


/**
 * Утилита для legacy-кода: если компонент имеет только строку (например
 * пришло `c.name` от старого API), эта функция применяет тот же фолбэк-шаблон.
 *
 *   resolveCompanyDisplayName('Узтрансгаз')
 *     → 'Узтрансгаз' (как есть)
 *
 *   resolveCompanyDisplayName('АО «Узтрансгаз»')
 *     → 'АО «Узтрансгаз»' (как есть — нет name_short доступного без store-lookup)
 *
 * Используй companyDisplayName(co) когда есть полная модель.
 * Используй useCompaniesStore.getCompanyName(code) когда есть только код.
 */
export function resolveCompanyDisplayName(
  name: string | null | undefined,
  idOrCode?: string | null,
): string {
  const match = companyAliases.value.get(aliasKey(idOrCode))
    || companyAliases.value.get(aliasKey(name));
  return match ? companyDisplayName(match) : (name || "").trim();
}

/** Resolve a legacy sector label or code through the same localized catalog. */
export function resolveSectorDisplayName(
  name: string | null | undefined,
  idOrCode?: string | null,
): string {
  const match = sectorAliases.value.get(aliasKey(idOrCode))
    || sectorAliases.value.get(aliasKey(name));
  return match ? sectorDisplayName(match) : (name || idOrCode || "").trim();
}


// ═════════════════════════ sector code normalization ═════════════════════════

/**
 * Canonicalize any raw sector code to one of 5 buckets:
 *   "mining" | "oilgas" | "energy" | "transport" | "other"
 *
 * Backend stores sector codes in multiple styles depending on when the row
 * was inserted: "mining" / "mining_metallurgy" / "metallurgy",
 * "oil_gas" / "oilgas", "transport" / "transport_telecom", and so on.
 * This helper folds all of them into 5 stable buckets used by the frontend
 * for filtering, colour selection, and short-label lookup.
 *
 * Examples:
 *   canonSectorCode("mining_metallurgy") → "mining"
 *   canonSectorCode("Oil & Gas")         → "oilgas"
 *   canonSectorCode("transport-telecom") → "transport"
 *   canonSectorCode("горнодобывающий")   → "mining"
 *   canonSectorCode(null)                → "other"
 */
export function canonSectorCode(raw: string | null | undefined): string {
  // i18n-exempt-start: multilingual aliases classify sector data; they are never rendered.
  const s = (raw || "").toLowerCase().replace(/[\s_\-]+/g, "");
  if (!s) return "other";
  // Energy: must check BEFORE oil/gas in case code contains both
  if (s.startsWith("energy") || s.includes("energ") || s.includes("энерг")) return "energy";
  if (s.includes("oilgas") || s.includes("oil") || s.includes("gas")
      || s.includes("нефт") || s.includes("газ")) return "oilgas";
  if (s.includes("mining") || s.includes("metallurg") || s.includes("metall")
      || s.includes("горн") || s.includes("металл")) return "mining";
  if (s.includes("transport") || s.includes("telecom") || s.includes("comm")
      || s.includes("трансп") || s.includes("связ") || s.includes("телеком")) return "transport";
  return "other";
  // i18n-exempt-end
}

/**
 * Produce a short label for a sector based on its full name.
 *   "Горнодобывающий"          → "Горн."
 *   "Нефтегазовый"             → "Нефтегаз."
 *   "Транспорт и коммуникации" → "Трансп."
 *   "Энергетика"               → "Энерг."
 *
 * Uses simple heuristics — first word + dot, capped at ~9 chars — so it
 * works for whatever name the admin enters in Companies admin without
 * needing a hardcoded translation table.
 */
export function sectorShortLabel(fullName: string | null | undefined): string {
  const name = (fullName || "").trim();
  if (!name) return "—";
  // Take the first meaningful word
  const firstWord = name.split(/[\s\-]/)[0] || name;
  // Cap at 8 chars + dot
  if (firstWord.length <= 8) return firstWord + ".";
  return firstWord.slice(0, 7) + "…";
}
