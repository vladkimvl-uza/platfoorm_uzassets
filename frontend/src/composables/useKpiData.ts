/**
 * useKpiData — singleton state для KPI модуля.
 *
 * Восстановлен 1:1 под потребности views/KPI.vue + KpiCompanyDashboard.vue
 * + KpiSummaryDashboard.vue + KpiEditor.vue + KpiDrillModal.vue.
 *
 * API:
 *   refs: viewMode, selectedYear, selectedPeriod, availableYears,
 *         selectedCompanyId, selectedCompany, companies, summary,
 *         managers, selectedManagerIdx, error, loading
 *   methods: setViewMode, setPeriod, setYear, setCompany, setManager,
 *            loadCompanies, loadSummary, loadCompanyData
 */
import { computed, reactive, ref } from "vue";
import { kpiApi } from "@/api/bpKpi";
import { useToast } from "@/composables/useToast";
import type {
  AvailableCompany,
  KpiManager,
  KpiSummary,
} from "@/api/bpKpi";
import { t } from "@/locale/i18n";


export type KpiViewMode = "summary" | "company";
export type KpiPeriod = "annual" | "q1" | "q2" | "q3" | "q4";

/* ─────────────────────────── Persisted preferences ─────────────────────────── */

const LS_KEY = "uz_kpi_prefs_v1";

function loadPrefs(): {
  viewMode: KpiViewMode;
  year: number;
  period: KpiPeriod;
  companyId: string | null;
} {
  try {
    const raw = localStorage.getItem(LS_KEY);
    if (raw) {
      const p = JSON.parse(raw);
      // 2026-05-23: "annual" убрано из UI (нет данных) → migrate в q1.
      const rawPeriod = ["annual", "q1", "q2", "q3", "q4"].includes(p.period) ? p.period : "q1";
      const period = rawPeriod === "annual" ? "q1" : rawPeriod;
      return {
        viewMode: p.viewMode === "company" ? "company" : "summary",
        year: typeof p.year === "number" ? p.year : new Date().getFullYear(),
        period,
        companyId: typeof p.companyId === "string" ? p.companyId : null,
      };
    }
  } catch (_) { /* noop */ }
  return {
    viewMode: "summary",
    year: new Date().getFullYear(),
    period: "q1",
    companyId: null,
  };
}

function savePrefs() {
  try {
    localStorage.setItem(LS_KEY, JSON.stringify({
      viewMode: viewMode.value,
      year: selectedYear.value,
      period: selectedPeriod.value,
      companyId: selectedCompanyId.value,
    }));
  } catch (_) { /* noop */ }
}

/* ─────────────────────────── State ─────────────────────────── */

const _initial = loadPrefs();

const viewMode = ref<KpiViewMode>(_initial.viewMode);
const selectedYear = ref<number>(_initial.year);
const selectedPeriod = ref<KpiPeriod>(_initial.period);
const selectedCompanyId = ref<string | null>(_initial.companyId);
const selectedManagerIdx = ref<number>(0);

const companies = ref<AvailableCompany[]>([]);
const summary = ref<KpiSummary | null>(null);
const managers = ref<KpiManager[]>([]);

const loading = reactive({
  companies: false,
  summary: false,
  company: false,
});

const error = ref<string | null>(null);

// seq-guard: защита от гонки при быстрой смене фильтров — применяем
// результат только если это последний запущенный запрос.
let _reqSeq = 0;

const selectedCompany = computed<AvailableCompany | null>(() => {
  if (!selectedCompanyId.value) return null;
  return companies.value.find((c) => c.company_id === selectedCompanyId.value) || null;
});

const availableYears = computed<number[]>(() => {
  const yset = new Set<number>();
  for (const co of companies.value) {
    for (const y of co.years || []) yset.add(y);
  }
  // Текущий год и соседние добавляем ВСЕГДА (а не только при пустом наборе) —
  // как в Бизнес-плане. Иначе у компании с данными за один год степпер имел
  // единственную позицию и выглядел неработающим, а завести данные за новый
  // год было нельзя: до него не доехать.
  const cy = new Date().getFullYear();
  [cy - 1, cy, cy + 1].forEach((y) => yset.add(y));
  return Array.from(yset).sort((a, b) => b - a).slice(0, 4);
});

/* ─────────────────────────── Loaders ─────────────────────────── */

async function loadCompanies(): Promise<void> {
  loading.companies = true;
  try {
    companies.value = await kpiApi.availableCompanies();
  } catch (e: any) {
    companies.value = [];
    // P1-6: не глотаем молча — явный фидбэк (правило feedback_everywhere_rule).
    error.value = e?.response?.data?.detail || e?.message || t('Не удалось загрузить список компаний KPI');
    console.error("[useKpiData.loadCompanies]", e);
    try { useToast().error(t("Не удалось загрузить список компаний KPI")); } catch (_) { /* noop */ }
  } finally {
    loading.companies = false;
  }
}

async function loadSummary(): Promise<void> {
  const my = ++_reqSeq;
  loading.summary = true;
  error.value = null;
  try {
    const res = await kpiApi.getSummary(selectedYear.value, selectedPeriod.value);
    if (my !== _reqSeq) return; // устаревший ответ — игнорируем
    summary.value = res;
  } catch (e: any) {
    if (my !== _reqSeq) return;
    summary.value = null;
    error.value = e?.response?.data?.detail || e?.message || t('Не удалось загрузить KPI сводку');
    console.error("[useKpiData.loadSummary]", e);
  } finally {
    if (my === _reqSeq) loading.summary = false;
  }
}

async function loadCompanyData(): Promise<void> {
  if (!selectedCompanyId.value) {
    managers.value = [];
    return;
  }
  const my = ++_reqSeq;
  loading.company = true;
  error.value = null;
  try {
    const res = await kpiApi.getCompanyYear(selectedCompanyId.value, selectedYear.value);
    if (my !== _reqSeq) return; // устаревший ответ — игнорируем
    managers.value = res.managers;
    // Сбрасываем активного менеджера если он за пределами
    if (selectedManagerIdx.value >= managers.value.length) {
      selectedManagerIdx.value = 0;
    }
  } catch (e: any) {
    if (my !== _reqSeq) return;
    managers.value = [];
    error.value = e?.response?.data?.detail || e?.message || t('Не удалось загрузить KPI компании');
    console.error("[useKpiData.loadCompanyData]", e);
  } finally {
    if (my === _reqSeq) loading.company = false;
  }
}

/* ─────────────────────────── Setters ─────────────────────────── */

function setViewMode(mode: KpiViewMode): void {
  if (viewMode.value === mode) return;
  viewMode.value = mode;
  savePrefs();
  if (mode === "summary") loadSummary();
  else loadCompanyData();
}

function setPeriod(p: KpiPeriod): void {
  if (selectedPeriod.value === p) return;
  selectedPeriod.value = p;
  savePrefs();
  // Period влияет только на сводку (расчёты по кварталу/году)
  if (viewMode.value === "summary") loadSummary();
}

function setYear(y: number): void {
  if (selectedYear.value === y) return;
  selectedYear.value = y;
  savePrefs();
  if (viewMode.value === "summary") loadSummary();
  else loadCompanyData();
}

function setCompany(id: string | null): void {
  selectedCompanyId.value = id;
  selectedManagerIdx.value = 0;
  savePrefs();
  if (viewMode.value === "company") loadCompanyData();
}

function setManager(idx: number): void {
  selectedManagerIdx.value = idx;
}

/* ─────────────────────────── Public API ─────────────────────────── */

export function useKpiData() {
  return {
    // refs
    viewMode,
    selectedYear,
    selectedPeriod,
    selectedCompanyId,
    selectedCompany,
    selectedManagerIdx,
    companies,
    availableYears,
    summary,
    managers,
    error,
    loading,
    // setters
    setViewMode,
    setPeriod,
    setYear,
    setCompany,
    setManager,
    // loaders
    loadCompanies,
    loadSummary,
    loadCompanyData,
  };
}
