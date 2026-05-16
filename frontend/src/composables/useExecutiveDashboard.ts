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
}

function loadPrefs(): Prefs {
  try {
    const raw = localStorage.getItem(LS_KEY);
    if (raw) {
      const p = JSON.parse(raw);
      return {
        year: typeof p.year === "number" ? p.year : 2025,
        sectors: Array.isArray(p.sectors) ? p.sectors.filter((x: any) => typeof x === "string") : [],
      };
    }
  } catch (_) { /* noop */ }
  return { year: 2025, sectors: [] };
}

function savePrefs() {
  try {
    localStorage.setItem(LS_KEY, JSON.stringify({
      year: year.value,
      sectors: selectedSectors.value,
    }));
  } catch (_) { /* noop */ }
}

const _initial = loadPrefs();

const year = ref<number>(_initial.year);
const selectedSectors = ref<string[]>(_initial.sectors);
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

async function loadData(): Promise<void> {
  loading.data = true;
  error.value = null;
  try {
    data.value = await getExecutiveDashboard(year.value, selectedSectors.value.length ? selectedSectors.value : undefined, bpMetric.value);
  } catch (e: any) {
    data.value = null;
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
  };
}
