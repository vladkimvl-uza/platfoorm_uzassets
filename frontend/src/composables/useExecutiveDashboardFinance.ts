/**
 * useExecutiveDashboardFinance — singleton state для финансового блока Pack 3.
 *
 * Независимый year (≠ exec dashboard year), standard, currency, viewMode, unit.
 * sectors filter — берётся из useExecutiveDashboard (общий фильтр на весь дашборд).
 *
 * Дёргает существующий financialsApi.portfolioSummary() — без новых endpoints.
 */
import { reactive, ref } from "vue";
import { financialsApi, type PortfolioSummaryResponse } from "@/api/financials";
import { t } from "@/locale/i18n";


const LS_KEY = "uz_exec_dash_finance_v1";

interface Prefs {
  year: number;
  standard: "IFRS" | "NSBU";
  currency: "UZS" | "USD" | "EUR";
  viewMode: "summary" | "company";
  unit: "bln" | "mln" | "ths";
  selectedCompanyId: string | null;
}

const DEFAULTS: Prefs = {
  year: 2024,
  standard: "IFRS",
  currency: "UZS",
  viewMode: "summary",
  unit: "bln",
  selectedCompanyId: null,
};

function _isValidViewMode(v: any): v is "summary" | "company" {
  return v === "summary" || v === "company";
}

function loadPrefs(): Prefs {
  try {
    const raw = localStorage.getItem(LS_KEY);
    if (raw) {
      const p = JSON.parse(raw);
      return {
        year: typeof p.year === "number" ? p.year : DEFAULTS.year,
        standard: p.standard === "NSBU" ? "NSBU" : "IFRS",
        currency: ["UZS", "USD", "EUR"].includes(p.currency) ? p.currency : "UZS",
        viewMode: p.viewMode === "company" ? "company" : "summary",
        unit: ["bln", "mln", "ths"].includes(p.unit) ? p.unit : "bln",
        selectedCompanyId: typeof p.selectedCompanyId === "string" ? p.selectedCompanyId : null,
      };
    }
  } catch (_) { /* noop */ }
  return { ...DEFAULTS };
}

function savePrefs() {
  try {
    localStorage.setItem(LS_KEY, JSON.stringify({
      year: year.value,
      standard: standard.value,
      currency: currency.value,
      viewMode: viewMode.value,
      unit: unit.value,
      selectedCompanyId: selectedCompanyId.value,
    }));
  } catch (_) { /* noop */ }
}

const _initial = loadPrefs();

const year = ref<number>(_initial.year);
const standard = ref<"IFRS" | "NSBU">(_initial.standard);
const currency = ref<"UZS" | "USD" | "EUR">(_initial.currency);
const viewMode = ref<"summary" | "company">(_initial.viewMode);
const unit = ref<"bln" | "mln" | "ths">(_initial.unit);
const selectedCompanyId = ref<string | null>(_initial.selectedCompanyId);

const summary = ref<PortfolioSummaryResponse | null>(null);
const loading = reactive({ data: false });
const error = ref<string | null>(null);

async function loadData(): Promise<void> {
  loading.data = true;
  error.value = null;
  try {
    // Запрашиваем все годы что легаси — для YoY и для year-pills.
    // financialsApi.portfolioSummary ожидает years: number[]
    const yearsList: number[] = [];
    for (let y = year.value - 4; y <= year.value + 1; y++) {
      if (y >= 2018 && y <= 2030) yearsList.push(y);
    }
    summary.value = await financialsApi.portfolioSummary({
      standard: standard.value,
      currency: currency.value,
      years: yearsList,
    });
  } catch (e: any) {
    summary.value = null;
    error.value = e?.response?.data?.detail || e?.message || t('Не удалось загрузить финансовые данные');
    console.error("[useExecutiveDashboardFinance.loadData]", e);
  } finally {
    loading.data = false;
  }
}

function setYear(y: number): void {
  if (year.value === y) return;
  year.value = y; savePrefs(); loadData();
}
function setStandard(s: "IFRS" | "NSBU"): void {
  if (standard.value === s) return;
  standard.value = s; savePrefs(); loadData();
}
function setCurrency(c: "UZS" | "USD" | "EUR"): void {
  if (currency.value === c) return;
  currency.value = c; savePrefs(); loadData();
}
function setViewMode(m: "summary" | "company"): void {
  if (viewMode.value === m) return;
  viewMode.value = m; savePrefs();
}
function setUnit(u: "bln" | "mln" | "ths"): void {
  if (unit.value === u) return;
  unit.value = u; savePrefs();
}
function setCompany(id: string | null): void {
  selectedCompanyId.value = id; savePrefs();
}

export function useExecutiveDashboardFinance() {
  return {
    year, standard, currency, viewMode, unit, selectedCompanyId,
    summary, loading, error,
    loadData,
    setYear, setStandard, setCurrency, setViewMode, setUnit, setCompany,
  };
}