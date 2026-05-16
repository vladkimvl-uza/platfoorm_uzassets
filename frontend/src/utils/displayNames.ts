/**
 * displayNames.ts
 * ─────────────────────────────────────────────────────────────────
 * Единый источник истины для отображаемых имён компаний и секторов.
 *
 * ПРАВИЛО (Pack 7.12, выбранный вариант 3):
 *   • Компания:  name_short если он непустой, иначе name_ru
 *   • Сектор:    name_ru (sector.name_short нет в модели)
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

/** Минимальный shape компании, достаточный для resolving имени. */
export interface CompanyNameShape {
  name_ru?: string | null;
  name_short?: string | null;
  /** Иногда серверу передаются псевдонимы; используем как fallback. */
  name?: string | null;
}

/** Минимальный shape сектора. */
export interface SectorNameShape {
  name_ru?: string | null;
  name?: string | null;
  code?: string | null;
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
  const short = (co.name_short || "").trim();
  if (short) return short;
  const full = (co.name_ru || co.name || "").trim();
  return full;
}


/**
 * Получить отображаемое имя сектора по единому правилу.
 *
 *   sectorDisplayName({ name_ru: 'Горнодобывающий', code: 'mining' })
 *     → 'Горнодобывающий'
 */
export function sectorDisplayName(sec: SectorNameShape | null | undefined): string {
  if (!sec) return "";
  return (sec.name_ru || sec.name || sec.code || "").trim();
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
export function resolveCompanyDisplayName(name: string | null | undefined): string {
  return (name || "").trim();
}


// ═════════════════════════ Pack 7.20: sector code normalization ═════════════════════════

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
