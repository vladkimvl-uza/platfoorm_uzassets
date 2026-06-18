/**
 * useCurrencyConverter.ts
 * ─────────────────────────────────────────────────────────────────
 * Singleton composable для конвертации сумм UZS → USD / EUR с использованием
 * среднегодовых курсов Центрального Банка Республики Узбекистан.
 *
 * Pack 7.34: курсы USD и бюджет были захардкожены.
 * Pack 7.35: значения загружаются из API /system-config/yearly-rates
 * (admin-редактируемая таблица year_registry).
 * Pack 7.37: добавлена поддержка EUR — `eur_rate` per year, third currency
 * option "EUR", format() возвращает соответствующие лейблы.
 *
 * Если загрузка из API не удалась (бэкенд недоступен, миграция не накатилась,
 * нет прав) — используется hardcoded fallback. Это гарантирует, что dashboard
 * и модалки всегда работают, даже без backend.
 *
 * State хранится на уровне модуля (singleton): любой компонент, который
 * импортирует useCurrencyConverter(), получает ту же реактивную ссылку
 * на текущую валюту и тот же кэш курсов.
 *
 * Выбранная валюта персистится в localStorage под ключом `uza_currency_v1`.
 *
 * Pack 7.37
 */
import { ref, computed, watch, readonly } from "vue";
import { systemConfigApi, type YearlyRate } from "@/api/systemConfig";

export type Currency = "UZS" | "USD" | "EUR";

const STORAGE_KEY = "uza_currency_v1";

// ── Hardcoded fallbacks ──
// Источники: ЦБ РУ + exchange-rates.org (среднегодовые)
export const USD_RATES_FALLBACK: Readonly<Record<number, number>> = Object.freeze({
  2021: 10610.00,
  2022: 11050.00,
  2023: 11420.00,
  2024: 12650.91,
  2025: 12576.41,
  2026: 12200.00,
});
const DEFAULT_USD_RATE = 12576.41;

export const EUR_RATES_FALLBACK: Readonly<Record<number, number>> = Object.freeze({
  2021: 12520.00,
  2022: 11600.00,
  2023: 12330.00,
  2024: 13691.00,
  2025: 14140.00,
  2026: 14250.00,
});
const DEFAULT_EUR_RATE = 14140.00;

export const UZ_BUDGET_TRLN_FALLBACK: Readonly<Record<number, number>> = Object.freeze({
  2021: 230.0,
  2022: 260.0,
  2023: 290.0,
  2024: 320.0,
  2025: 350.0,
  2026: 380.0,
});

// ── Singleton state ──
function _readInitial(): Currency {
  if (typeof window === "undefined" || typeof localStorage === "undefined") return "UZS";
  try {
    const v = localStorage.getItem(STORAGE_KEY);
    if (v === "USD") return "USD";
    if (v === "EUR") return "EUR";
    return "UZS";
  } catch { return "UZS"; }
}

const _currency = ref<Currency>(_readInitial());

const _usdRates = ref<Record<number, number> | null>(null);
const _eurRates = ref<Record<number, number> | null>(null);
const _uzBudgets = ref<Record<number, number> | null>(null);
const _loaded = ref(false);
const _loading = ref(false);
let _loadPromise: Promise<void> | null = null;

let _watchAttached = false;
function _attachPersistence() {
  if (_watchAttached) return;
  _watchAttached = true;
  watch(_currency, (v) => {
    try {
      if (typeof localStorage !== "undefined") localStorage.setItem(STORAGE_KEY, v);
    } catch { /* noop */ }
  });
}

function _loadFromApi(force = false): Promise<void> {
  if (_loaded.value && !force) return Promise.resolve();
  if (_loadPromise && !force) return _loadPromise;

  _loading.value = true;
  _loadPromise = systemConfigApi
    .listYearlyRates()
    .then((rows: YearlyRate[]) => {
      const usdMap: Record<number, number> = {};
      const eurMap: Record<number, number> = {};
      const budMap: Record<number, number> = {};
      for (const r of rows) {
        if (r.usd_rate != null && isFinite(r.usd_rate)) usdMap[r.year] = r.usd_rate;
        if (r.eur_rate != null && isFinite(r.eur_rate)) eurMap[r.year] = r.eur_rate;
        if (r.uz_budget_trln != null && isFinite(r.uz_budget_trln)) budMap[r.year] = r.uz_budget_trln;
      }
      _usdRates.value = Object.keys(usdMap).length ? usdMap : null;
      _eurRates.value = Object.keys(eurMap).length ? eurMap : null;
      _uzBudgets.value = Object.keys(budMap).length ? budMap : null;
      _loaded.value = true;
    })
    .catch((err) => {
       
      console.warn("[useCurrencyConverter] загрузка из API не удалась, использую fallback:", err);
      _usdRates.value = null;
      _eurRates.value = null;
      _uzBudgets.value = null;
      _loaded.value = true;
    })
    .finally(() => {
      _loading.value = false;
      _loadPromise = null;
    });

  return _loadPromise;
}

// ── Format helpers ──
export interface FormattedAmount {
  value: string;
  unit: string;
  full: string;
}

function _fmt3(v: number): string {
  if (!isFinite(v)) return "—";
  const rounded = Math.round(v * 1000) / 1000;
  const parts = rounded.toFixed(3).split(".");
  parts[0] = parts[0].replace(/\B(?=(\d{3})+(?!\d))/g, "\u00A0");
  return parts.join(".").replace(/\u00A0/g, " ");
}

function _lookupRate(year: number, src: Record<number, number>, dflt: number): number {
  if (src[year] != null) return src[year];
  const years = Object.keys(src).map(Number).sort((a, b) => b - a);
  for (const y of years) {
    if (y <= year) return src[y];
  }
  return dflt;
}

export function useCurrencyConverter() {
  _attachPersistence();

  if (!_loaded.value && !_loading.value) {
    void _loadFromApi();
  }

  function getUsdRate(year: number): number {
    return _lookupRate(year, _usdRates.value || USD_RATES_FALLBACK, DEFAULT_USD_RATE);
  }

  function getEurRate(year: number): number {
    return _lookupRate(year, _eurRates.value || EUR_RATES_FALLBACK, DEFAULT_EUR_RATE);
  }

  function getBudgetMlrd(year: number): number | null {
    const src = _uzBudgets.value || UZ_BUDGET_TRLN_FALLBACK;
    const trln = src[year];
    return trln != null ? trln * 1000 : null;
  }

  /**
   * Конвертация значения из млрд UZS в выбранную валюту.
   * Возвращает scaled value + unit + полная строка.
   * Если currency = UZS — возвращает в млрд или трлн сум.
   * Если currency = USD/EUR — конвертирует и возвращает в млн или млрд валюты.
   */
  function format(
    amountInMlrdUzs: number | null | undefined,
    year: number,
    opts?: { force?: Currency }
  ): FormattedAmount {
    if (amountInMlrdUzs == null || !isFinite(amountInMlrdUzs)) {
      return { value: "—", unit: "", full: "—" };
    }
    const c = opts?.force ?? _currency.value;
    if (c === "UZS") {
      if (Math.abs(amountInMlrdUzs) >= 1000) {
        const v = amountInMlrdUzs / 1000;
        return { value: _fmt3(v), unit: "триллион сум", full: `${_fmt3(v)} триллион сум` };
      }
      return { value: _fmt3(amountInMlrdUzs), unit: "миллиард сум", full: `${_fmt3(amountInMlrdUzs)} миллиард сум` };
    }
    // USD / EUR
    const rate = c === "EUR" ? getEurRate(year) : getUsdRate(year);
    const foreign = (amountInMlrdUzs * 1e9) / rate;
    const foreignMln = foreign / 1e6;
    const curLabel = c;
    if (Math.abs(foreignMln) >= 1000) {
      const v = foreignMln / 1000;
      return { value: _fmt3(v), unit: `миллиард ${curLabel}`, full: `${_fmt3(v)} миллиард ${curLabel}` };
    }
    return { value: _fmt3(foreignMln), unit: `миллион ${curLabel}`, full: `${_fmt3(foreignMln)} миллион ${curLabel}` };
  }

  function formatValueOnly(amountInMlrdUzs: number | null | undefined, year: number, opts?: { force?: Currency }): string {
    return format(amountInMlrdUzs, year, opts).value;
  }
  function getUnit(amountInMlrdUzs: number, year: number, opts?: { force?: Currency }): string {
    return format(amountInMlrdUzs, year, opts).unit;
  }

  /**
   * Конвертирует млрд UZS в выбранную валюту:
   *   - UZS → возвращает то же значение (млрд сум)
   *   - USD/EUR → возвращает млн USD/EUR
   */
  function convert(amountInMlrdUzs: number, year: number, to?: Currency): number {
    const c = to ?? _currency.value;
    if (c === "UZS") return amountInMlrdUzs;
    const rate = c === "EUR" ? getEurRate(year) : getUsdRate(year);
    return (amountInMlrdUzs * 1e9) / rate / 1e6;
  }

  function toggle() {
    // Three-way cycle: UZS → USD → EUR → UZS
    _currency.value = _currency.value === "UZS" ? "USD" : _currency.value === "USD" ? "EUR" : "UZS";
  }
  function setCurrency(c: Currency) { _currency.value = c; }
  const currencyLabel = computed(() => {
    if (_currency.value === "UZS") return "сум";
    if (_currency.value === "EUR") return "EUR";
    return "USD";
  });

  function getRateLabel(year: number): string {
    if (_currency.value === "UZS") return "";
    const r = _currency.value === "EUR" ? getEurRate(year) : getUsdRate(year);
    const cur = _currency.value;
    return `${Math.round(r).toLocaleString("ru-RU").replace(/\u00A0/g, " ")} сум за 1 ${cur}`;
  }

  async function reload(): Promise<void> {
    await _loadFromApi(true);
  }

  return {
    currency: readonly(_currency),
    currencyLabel,
    toggle,
    setCurrency,
    format,
    formatValueOnly,
    getUnit,
    convert,
    getUsdRate,
    getEurRate,
    getRateLabel,
    getBudgetMlrd,
    reload,
    isLoading: readonly(_loading),
    isLoaded: readonly(_loaded),
    rates: USD_RATES_FALLBACK,
    budgets: UZ_BUDGET_TRLN_FALLBACK,
  };
}

// ── Legacy exports — for /7.35 imports ──
export const USD_RATES_BY_YEAR = USD_RATES_FALLBACK;
export const EUR_RATES_BY_YEAR = EUR_RATES_FALLBACK;
export const UZ_BUDGET_TRLN_BY_YEAR = UZ_BUDGET_TRLN_FALLBACK;
