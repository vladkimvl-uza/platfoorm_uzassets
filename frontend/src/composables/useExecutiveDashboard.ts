/**
 * useExecutiveDashboard — singleton state для Executive Dashboard view.
 *
 * Refs: year, selectedSectors (filter), data, loading, error
 * Methods: setYear, setSectors, toggleSector, clearSectors, loadData
 */
import { computed, reactive, ref } from "vue";
import {
  getExecutiveDashboard,
  type ExecutiveDashboardData,
} from "@/api/executiveDashboard";
import { useCompaniesStore } from "@/stores/companies";
import { t } from "@/locale/i18n";



const LS_KEY = "uz_exec_dash_prefs_v1";
// Дефолтный год — текущий календарный (а не захардкоженный 2025); при первой
// загрузке снапится к max(available_years), если выбранный год недоступен.
const DEFAULT_YEAR = new Date().getFullYear();
let _yearPinned = false;   // true = год выбран/сохранён пользователем явно

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
      if (typeof p.year === "number") _yearPinned = true;
      return {
        year: typeof p.year === "number" ? p.year : DEFAULT_YEAR,
        sectors: Array.isArray(p.sectors) ? p.sectors.filter((x: any) => typeof x === "string") : [],
        companies: Array.isArray(p.companies) ? p.companies.filter((x: any) => typeof x === "string") : [],
      };
    }
  } catch (_) { /* noop */ }
  return { year: DEFAULT_YEAR, sectors: [], companies: [] };
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
const bpPeriod = ref<string>("annual");   // период BP-трекера: annual|q1..q4
const data = ref<ExecutiveDashboardData | null>(null);

const loading = reactive({ data: false });
const error = ref<string | null>(null);

const filteredSectorsLabel = computed(() => {
  if (!selectedSectors.value.length) return t("Все секторы");
  if (!data.value) return t('Секторы: {value0}', { value0: selectedSectors.value.length });
  if (selectedSectors.value.length === 1) {
    const s = data.value.available_sectors.find((x) => x.id === selectedSectors.value[0]);
    return s ? s.label : t("Сектор");
  }
  return t('Секторы: {value0}', { value0: selectedSectors.value.length });
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

/** Полный список компаний для ПИКЕРА (из стора) — не зависит от фильтрации
 * дашборда, поэтому 2-ю компанию можно выбрать даже когда дашборд сужен до 1.
 * Метрики (pct/задачи) подмешиваются из data.sectors, если компания там есть. */
const pickerCompanies = computed<ExecCompanyOption[]>(() => {
  const store = useCompaniesStore();
  if (!store.companies.length) return availableCompanies.value;
  const metricMap = new Map(availableCompanies.value.map((c) => [c.company_id, c]));
  return store.companies
    .map((c) => {
      const m = metricMap.get(c.id);
      return {
        company_id: c.id,
        name: c.name_short || c.name_ru,
        sector_label: c.sector_name || "",
        sector_color: c.sector_color || "#94A3B8",
        pct: m?.pct ?? 0,
        task_total: m?.task_total ?? 0,
        task_done: m?.task_done ?? 0,
      };
    })
    .sort((a, b) => a.name.localeCompare(b.name, "ru"));
});

/** Выбранные компании с метриками (для бенчмарка) — из pickerCompanies,
 * чтобы выбранная компания не пропадала, даже если у неё нет задач. */
const benchmarkCompanies = computed<ExecCompanyOption[]>(() => {
  if (!selectedCompanies.value.length) return [];
  const set = new Set(selectedCompanies.value);
  return pickerCompanies.value.filter((c) => set.has(c.company_id));
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

// Бэкенд-фильтр: ровно 1 компания → сужаем весь дашборд; 0 или 2+ → портфель.
const filterCompanyId = computed(() => selectedCompanies.value.length === 1 ? selectedCompanies.value[0] : undefined);
// Бенчмарк-панель показывается при сравнении (2+); 1 компания сужает дашборд целиком.
const benchmarkActive = computed(() => selectedCompanies.value.length >= 2);
const companyFilterLabel = computed(() => {
  const n = selectedCompanies.value.length;
  if (!n) return t("Компании");
  if (n === 1) {
    const c = pickerCompanies.value.find((x) => x.company_id === selectedCompanies.value[0]);
    return c ? c.name : t("1 компания");
  }
  return t('Сравнение: {value0}', { value0: n });
});

function toggleCompany(id: string): void {
  const idx = selectedCompanies.value.indexOf(id);
  if (idx >= 0) selectedCompanies.value.splice(idx, 1);
  else selectedCompanies.value.push(id);
  savePrefs();
  // Пересечение границ 0/1/2 меняет бэкенд-фильтр (1 = фокус). loadData
  // дедупит по ключу — если эффективная компания не изменилась, сети не будет.
  loadData();
}
function clearCompanies(): void {
  if (!selectedCompanies.value.length) return;
  selectedCompanies.value = [];
  savePrefs();
  loadData();
}

// Dedup: ключ последней успешной загрузки. Повторный вызов с тем же
// year|sectors|metric (re-mount, дубль-триггер) не дёргает сеть. Реальная
// смена фильтра меняет ключ → fetch. force=true — обойти (явный refresh).
let _lastKey = "";
let _reqSeq = 0;  // защита от гонки stale-ответов
function _fetchKey(): string {
  return `${year.value}|${selectedSectors.value.slice().sort().join(",")}|${bpMetric.value}|${bpPeriod.value}|${filterCompanyId.value || ""}`;
}

async function loadData(force = false): Promise<void> {
  const key = _fetchKey();
  if (!force && key === _lastKey && data.value && !error.value) return;
  const my = ++_reqSeq;
  loading.data = true;
  error.value = null;
  try {
    const res = await getExecutiveDashboard(year.value, selectedSectors.value.length ? selectedSectors.value : undefined, bpMetric.value, filterCompanyId.value, bpPeriod.value);
    if (my !== _reqSeq) return;  // устаревший ответ — игнорируем
    data.value = res;
    _lastKey = key;
    // снап года к max(available_years), если выбранный недоступен и не закреплён вручную
    const _ays = ((res as { available_years?: number[] }).available_years || []);
    if (_ays.length && !_ays.includes(year.value) && !_yearPinned) {
      year.value = Math.max(..._ays);
      _yearPinned = true;
      savePrefs();
      void loadData(true);
      return;
    }
  } catch (e: any) {
    if (my !== _reqSeq) return;  // устаревший ответ — игнорируем
    data.value = null;
    _lastKey = "";  // ошибка → разрешить повтор
    error.value = e?.response?.data?.detail || e?.message || t('Не удалось загрузить Executive Dashboard');
    console.error("[useExecutiveDashboard.loadData]", e);
  } finally {
    if (my === _reqSeq) loading.data = false;  // флаг гасит только последний запрос
  }
}

function setYear(y: number): void {
  if (year.value === y) return;
  year.value = y;
  _yearPinned = true;
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

function setBpPeriod(p: string): void {
  if (bpPeriod.value === p) return;
  bpPeriod.value = p;
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
    bpPeriod,
    setBpPeriod,
    // company picker / benchmarking
    selectedCompanies,
    availableCompanies,
    pickerCompanies,
    filterCompanyId,
    benchmarkCompanies,
    portfolioBaseline,
    benchmarkActive,
    companyFilterLabel,
    toggleCompany,
    clearCompanies,
  };
}
