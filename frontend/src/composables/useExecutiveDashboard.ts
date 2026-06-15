/**
 * useExecutiveDashboard — singleton state для Executive Dashboard view.
 *
 * Refs: year, selectedSectors (filter), data, loading, error
 * Methods: setYear, setSectors, toggleSector, clearSectors, loadData
 */
import { computed, reactive, ref, watch } from "vue";
import {
  getExecutiveDashboard,
  type ExecutiveDashboardData,
} from "@/api/executiveDashboard";

const LS_KEY = "uz_exec_dash_prefs_v1";

interface Prefs {
  year: number;
  sectors: string[];
  companies: string[];
}

function loadPrefs(): Prefs {
  try {
    const raw = localStorage.getItem(LS_KEY);
    if (raw) {
      const p = JSON.parse(raw);
      return {
        year: typeof p.year === "number" ? p.year : 2025,
        sectors: Array.isArray(p.sectors) ? p.sectors.filter((x: any) => typeof x === "string") : [],
        companies: Array.isArray(p.companies) ? p.companies.filter((x: any) => typeof x === "string") : [],
      };
    }
  } catch (_) { /* noop */ }
  return { year: 2025, sectors: [], companies: [] };
}

function savePrefs() {
  try {
    localStorage.setItem(LS_KEY, JSON.stringify({
      year: year.value,
      sectors: selectedSectors.value,
      companies: selectedCompanies.value,
    }));
  } catch (_) { /* noop */ }
}

const _initial = loadPrefs();

const year = ref<number>(_initial.year);
const selectedSectors = ref<string[]>(_initial.sectors);
// Выбор компаний: [] = весь портфель, 1 = фокус на компании, 2+ = бенчмаркинг.
const selectedCompanies = ref<string[]>(_initial.companies);
const bpMetric = ref<string>("revenue");  // Pack 7.27
const data = ref<ExecutiveDashboardData | null>(null);

const loading = reactive({ data: false });
const error = ref<string | null>(null);

const filteredSectorsLabel = computed(() => {
  if (!selectedSectors.value.length) return "Все секторы";
  if (!data.value) return `Секторы: ${selectedSectors.value.length}`;
  if (selectedSectors.value.length === 1) {
    const s = data.value.available_sectors.find((x) => x.id === selectedSectors.value[0]);
    return s ? s.label : "Сектор";
  }
  return `Секторы: ${selectedSectors.value.length}`;
});

// ─── Company picker / benchmarking (клиентская агрегация из data.sectors) ───
export interface ExecCompanyOption {
  company_id: string;
  name: string;
  sector_label: string;
  sector_color: string;
  pct: number;
  task_total: number;
  task_done: number;
}

/** Плоский список компаний из всех секторов (для пикера и бенчмарка). */
const availableCompanies = computed<ExecCompanyOption[]>(() => {
  const out: ExecCompanyOption[] = [];
  for (const s of data.value?.sectors || []) {
    for (const c of s.companies || []) {
      out.push({
        company_id: c.company_id,
        name: c.name,
        sector_label: s.label,
        sector_color: s.color,
        pct: c.pct,
        task_total: c.task_total,
        task_done: c.task_done,
      });
    }
  }
  return out.sort((a, b) => a.name.localeCompare(b.name, "ru"));
});

/** Выбранные компании с метриками (для бенчмарка). */
const benchmarkCompanies = computed<ExecCompanyOption[]>(() => {
  if (!selectedCompanies.value.length) return [];
  const set = new Set(selectedCompanies.value);
  return availableCompanies.value.filter((c) => set.has(c.company_id));
});

/** Среднее по портфелю — baseline для дельт в бенчмарке. */
const portfolioBaseline = computed(() => {
  const all = availableCompanies.value;
  if (!all.length) return { pct: 0, task_total: 0, task_done: 0 };
  const n = all.length;
  return {
    pct: all.reduce((s, c) => s + (c.pct || 0), 0) / n,
    task_total: all.reduce((s, c) => s + (c.task_total || 0), 0) / n,
    task_done: all.reduce((s, c) => s + (c.task_done || 0), 0) / n,
  };
});

const benchmarkActive = computed(() => selectedCompanies.value.length >= 1);
const companyFilterLabel = computed(() => {
  const n = selectedCompanies.value.length;
  if (!n) return "Компании";
  if (n === 1) {
    const c = availableCompanies.value.find((x) => x.company_id === selectedCompanies.value[0]);
    return c ? c.name : "1 компания";
  }
  return `Сравнение: ${n}`;
});

function toggleCompany(id: string): void {
  const idx = selectedCompanies.value.indexOf(id);
  if (idx >= 0) selectedCompanies.value.splice(idx, 1);
  else selectedCompanies.value.push(id);
  savePrefs();
}
function clearCompanies(): void {
  if (!selectedCompanies.value.length) return;
  selectedCompanies.value = [];
  savePrefs();
}

// Dedup: ключ последней успешной загрузки. Повторный вызов с тем же
// year|sectors|metric (re-mount, дубль-триггер) не дёргает сеть. Реальная
// смена фильтра меняет ключ → fetch. force=true — обойти (явный refresh).
let _lastKey = "";
function _fetchKey(): string {
  return `${year.value}|${selectedSectors.value.slice().sort().join(",")}|${bpMetric.value}`;
}

async function loadData(force = false): Promise<void> {
  const key = _fetchKey();
  if (!force && key === _lastKey && data.value && !error.value) return;
  loading.data = true;
  error.value = null;
  try {
    data.value = await getExecutiveDashboard(year.value, selectedSectors.value.length ? selectedSectors.value : undefined, bpMetric.value);
    _lastKey = key;
  } catch (e: any) {
    data.value = null;
    _lastKey = "";  // ошибка → разрешить повтор
    error.value = e?.response?.data?.detail || e?.message || "Не удалось загрузить Executive Dashboard";
    console.error("[useExecutiveDashboard.loadData]", e);
  } finally {
    loading.data = false;
  }
}

function setYear(y: number): void {
  if (year.value === y) return;
  year.value = y;
  savePrefs();
  loadData();
}

function setSectors(list: string[]): void {
  selectedSectors.value = list.slice();
  savePrefs();
  loadData();
}

function toggleSector(code: string): void {
  const idx = selectedSectors.value.indexOf(code);
  if (idx >= 0) {
    selectedSectors.value.splice(idx, 1);
  } else {
    selectedSectors.value.push(code);
  }
  savePrefs();
  loadData();
}

function clearSectors(): void {
  if (!selectedSectors.value.length) return;
  selectedSectors.value = [];
  savePrefs();
  loadData();
}

function setBpMetric(m: string): void {
  if (bpMetric.value === m) return;
  bpMetric.value = m;
  loadData();
}

export function useExecutiveDashboard() {
  return {
    year,
    selectedSectors,
    data,
    loading,
    error,
    filteredSectorsLabel,
    loadData,
    setYear,
    setSectors,
    toggleSector,
    clearSectors,
    bpMetric,
    setBpMetric,
    // company picker / benchmarking
    selectedCompanies,
    availableCompanies,
    benchmarkCompanies,
    portfolioBaseline,
    benchmarkActive,
    companyFilterLabel,
    toggleCompany,
    clearCompanies,
  };
}
