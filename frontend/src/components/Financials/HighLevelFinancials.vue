<script setup lang="ts">
/**
 * HighLevelFinancials — Pack 7.66 + 7.67.
 *
 * Renders + edits per-company hierarchical financial statements (HLF).
 *
 * Features:
 *  - Inline cell editing (numeric)
 *  - Edit row labels
 *  - Add/remove rows (line/subheader/subtotal/total)
 *  - Reorder rows (↑↓)
 *  - Add/remove year column
 *  - Add/remove section
 *  - KPI band (12 metrics: gross/EBITDA/net margins · ROA · ROE · Debt/EBITDA · Current ratio · Equity ratio · FCF · CapEx/Rev · YoY)
 *  - Persist via PUT /financials/companies/{code}/hlf
 *  - Import full XLSX template via POST /financials/hlf-import
 */
import { computed, onMounted, ref, watch } from "vue";
import type { CompanyListItem } from "@/api/companies";
import NumMixed from "@/components/NumMixed.vue";

const props = defineProps<{
  companies: CompanyListItem[];
  initialCode?: string;
}>();

interface HlfRow {
  type: string;
  label: string;
  values: (number | null)[];
  mapping?: string;
}
interface HlfSection { id: string; title: string; years: number[]; rows: HlfRow[]; }
interface HlfData {
  version?: string;
  imported_at?: string;
  imported_by?: string;
  updated_at?: string;
  updated_by?: string;
  filename?: string;
  currency?: string;
  unit?: "bln" | "mln";
  years: number[];
  sections: HlfSection[];
}

// ─── Local state ───
const selectedCode = ref<string>(props.initialCode || (props.companies[0]?.code || ""));
const loading      = ref(false);
const error        = ref<string>("");
const data         = ref<HlfData | null>(null);
const collapsedSec = ref<Set<string>>(new Set());
const editMode     = ref(false);
const dirty        = ref(false);
const saving       = ref(false);
const showAddYear  = ref(false);
const newYearValue = ref<number>(new Date().getFullYear());
const importLoading = ref(false);
const importResult  = ref<{ imported_count?: number; skipped_sheets?: string[]; log?: string[] } | null>(null);
const importFileRef = ref<HTMLInputElement | null>(null);

const displayCompanies = computed(() => {
  return props.companies
    .filter(c => c.is_active !== false)
    .sort((a, b) => (a.name_short || a.code).localeCompare(b.name_short || b.code, "ru"));
});

// ─── Fetch ───
async function load() {
  if (!selectedCode.value) return;
  loading.value = true;
  error.value = "";
  try {
    const { api } = await import("@/api/client");
    const resp = await api.get(`/financials/companies/${selectedCode.value}/hlf`);
    data.value = resp.data?.hlf || null;
    collapsedSec.value = new Set();
    dirty.value = false;
  } catch (e: unknown) {
    const err = e as { response?: { data?: { detail?: string } }; message?: string };
    error.value = err?.response?.data?.detail || err?.message || "Не удалось загрузить";
    data.value = null;
  } finally {
    loading.value = false;
  }
}
onMounted(load);
watch(selectedCode, async () => {
  if (dirty.value && !confirm("Есть несохранённые изменения. Сменить компанию?")) return;
  await load();
});

// ─── Save ───
async function save() {
  if (!data.value || !selectedCode.value || saving.value) return;
  saving.value = true;
  try {
    const { api } = await import("@/api/client");
    await api.put(`/financials/companies/${selectedCode.value}/hlf`, {
      years: data.value.years,
      sections: data.value.sections,
      currency: data.value.currency || "UZS",
      unit: data.value.unit || "bln",
    });
    dirty.value = false;
    // Успех = бэкенд закоммитил (API 2xx). Подтверждаем визуально.
    const { useToast } = await import("@/composables/useToast");
    useToast().success("Финансовая отчётность сохранена");
  } catch (e: unknown) {
    const err = e as { response?: { data?: { detail?: string } }; message?: string };
    const reason = err?.response?.data?.detail || err?.message || "неизвестная ошибка";
    error.value = `Не сохранено: ${reason}`;
    const { useToast } = await import("@/composables/useToast");
    useToast().error(`Отчётность не сохранена: ${reason}`);
  } finally {
    saving.value = false;
  }
}

function toggleEditMode() {
  if (editMode.value && dirty.value) {
    if (!confirm("Выйти из режима редактирования? Несохранённые изменения будут потеряны.")) return;
    load();
  }
  editMode.value = !editMode.value;
}

// ─── Cell editing ───
function onCellInput(row: HlfRow, yearIdx: number, raw: string) {
  const cleaned = raw.replace(/\s/g, "").replace(",", ".").trim();
  if (cleaned === "" || cleaned === "-") {
    row.values[yearIdx] = null;
  } else {
    const num = Number(cleaned);
    row.values[yearIdx] = isFinite(num) ? num : null;
  }
  dirty.value = true;
}

function getCellDisplay(v: number | null): string {
  if (v == null) return "";
  if (!isFinite(v)) return "";
  return v.toString().replace(".", ",");
}

function onLabelInput(row: HlfRow, raw: string) {
  row.label = raw;
  dirty.value = true;
}

function onSectionTitleInput(sec: HlfSection, raw: string) {
  sec.title = raw;
  dirty.value = true;
}

// ─── Year management ───
function openAddYear() {
  if (!data.value) return;
  const maxYear = Math.max(...data.value.years, new Date().getFullYear() - 1);
  newYearValue.value = maxYear + 1;
  showAddYear.value = true;
}

function commitAddYear() {
  if (!data.value || !newYearValue.value) return;
  const yr = Number(newYearValue.value);
  if (!isFinite(yr) || yr < 1990 || yr > 2100) {
    alert("Год должен быть от 1990 до 2100");
    return;
  }
  if (data.value.years.includes(yr)) {
    alert(`Год ${yr} уже есть в данных`);
    return;
  }
  data.value.years = [...data.value.years, yr].sort((a, b) => a - b);
  const insertIdx = data.value.years.indexOf(yr);
  for (const sec of data.value.sections) {
    sec.years = [...sec.years, yr].sort((a, b) => a - b);
    for (const row of sec.rows) {
      row.values.splice(insertIdx, 0, null);
    }
  }
  dirty.value = true;
  showAddYear.value = false;
}

function removeYear(yr: number) {
  if (!data.value) return;
  if (!confirm(`Удалить колонку «${yr}» во всех секциях? Значения будут потеряны.`)) return;
  data.value.years = data.value.years.filter(y => y !== yr);
  for (const sec of data.value.sections) {
    const idx = sec.years.indexOf(yr);
    if (idx !== -1) {
      sec.years.splice(idx, 1);
      for (const row of sec.rows) {
        row.values.splice(idx, 1);
      }
    }
  }
  dirty.value = true;
}

// ─── Row + section management ───
function addRow(sec: HlfSection, type: "line" | "subheader" | "subtotal" | "section_header" | "total") {
  sec.rows.push({
    type,
    label: type === "line" ? "Новая строка" :
           type === "subheader" ? "Новая подсекция" :
           type === "subtotal" ? "Итого" :
           type === "section_header" ? "НОВЫЙ ЗАГОЛОВОК" : "ИТОГО",
    values: sec.years.map(() => null),
  });
  dirty.value = true;
}

function removeRow(sec: HlfSection, rowIdx: number) {
  if (!confirm(`Удалить строку «${sec.rows[rowIdx].label}»?`)) return;
  sec.rows.splice(rowIdx, 1);
  dirty.value = true;
}

function moveRow(sec: HlfSection, rowIdx: number, dir: -1 | 1) {
  const newIdx = rowIdx + dir;
  if (newIdx < 0 || newIdx >= sec.rows.length) return;
  const t = sec.rows[rowIdx];
  sec.rows[rowIdx] = sec.rows[newIdx];
  sec.rows[newIdx] = t;
  dirty.value = true;
}

function addSection() {
  if (!data.value) return;
  data.value.sections.push({
    id: `custom_${Date.now()}`,
    title: "Новая секция",
    years: [...data.value.years],
    rows: [],
  });
  dirty.value = true;
}

function removeSection(secIdx: number) {
  if (!data.value) return;
  if (!confirm(`Удалить секцию «${data.value.sections[secIdx].title}»?`)) return;
  data.value.sections.splice(secIdx, 1);
  dirty.value = true;
}

// ─── Display helpers ───
function fmtNum(v: number | null): string {
  if (v == null || !isFinite(v)) return "—";
  if (v === 0) return "0";
  const abs = Math.abs(v);
  let str: string;
  if (abs >= 1000) str = Math.round(v).toLocaleString("ru", { maximumFractionDigits: 0 });
  else if (abs >= 10) str = v.toLocaleString("ru", { maximumFractionDigits: 1 });
  else str = v.toLocaleString("ru", { maximumFractionDigits: 2 });
  return str.replace(/,/g, " ").replace(/\u00a0/g, " ");
}

function toggleSection(id: string) {
  const s = new Set(collapsedSec.value);
  if (s.has(id)) s.delete(id); else s.add(id);
  collapsedSec.value = s;
}

function formatDate(iso?: string): string {
  if (!iso) return "—";
  try {
    return new Date(iso).toLocaleString("ru", {
      day: "2-digit", month: "2-digit", year: "numeric",
      hour: "2-digit", minute: "2-digit",
    });
  } catch { return iso; }
}

// ─── Import ───
function triggerFilePick() { importFileRef.value?.click(); }

async function onFileChange(evt: Event) {
  const input = evt.target as HTMLInputElement;
  const file = input.files?.[0];
  if (!file) return;
  importLoading.value = true;
  importResult.value = null;
  try {
    const { api } = await import("@/api/client");
    const fd = new FormData();
    fd.append("file", file);
    const resp = await api.post("/financials/hlf-import", fd, {
      headers: { "Content-Type": "multipart/form-data" },
    });
    importResult.value = resp.data;
    await load();
  } catch (e: unknown) {
    const err = e as { response?: { data?: { detail?: string } }; message?: string };
    error.value = err?.response?.data?.detail || err?.message || "Не удалось импортировать";
  } finally {
    importLoading.value = false;
    if (input) input.value = "";
  }
}

// ════════════════════════════════════════════════════════════════════════
// KPI EXTRACTION
// ════════════════════════════════════════════════════════════════════════
const LABEL_MATCHERS: Record<string, string[]> = {
  revenue: ["выручка", "revenue", "тушум", "sales revenue"],
  cogs: ["себестоимость", "cost of sales", "cost of goods", "cost of revenue", "таннарх", "cos"],
  gross_profit: ["gross profit", "валовая прибыль"],
  operating_profit: ["operating profit", "операционная прибыль", "profit from operations"],
  depreciation: [
    "depreciation, depletion", "depreciation and amortization", "depreciation and amortisation",
    "depreciation, depletion and amortization", "амортизация", "d&a", "d & a",
  ],
  finance_costs: ["finance costs", "finance cost", "финансовые расходы", "interest expense"],
  net_profit: [
    "profit for the year", "net profit for the year", "net income for the year",
    "соф фойда", "profit attributable to", "чистая прибыль"
  ],
  total_assets: ["total assets", "жами активлар"],
  total_equity: ["total equity", "капитал", "shareholders' equity", "shareholders equity"],
  total_current_assets: ["total current assets", "жорий активлар"],
  total_current_liabilities: ["total current liabilities", "қисқа муддатли мажб"],
  cash: [
    "денежные средства и их эквиваленты", "cash and cash equivalents at the end",
    "cash and cash equivalents", "нақд пул",
  ],
  operating_cf: [
    "operating cash flow", "cash from operating activities", "net cash from operating",
    "cash generated from operating", "cash flows from operating",
  ],
  capex: [
    "purchase of ppe", "purchases of property", "purchases of ppe",
    "purchase of property, plant", "capital expenditures", "capex",
    "капитальные затраты", "капитал қўйилмалар",
    "additions to property, plant", "additions to ppe",
  ],
  dividends_paid: ["dividends paid", "тўланган дивидендл"],
};

function matchRow(rows: HlfRow[], key: string): HlfRow | null {
  const patterns = LABEL_MATCHERS[key];
  if (!patterns) return null;
  for (const p of patterns) {
    const lp = p.toLowerCase();
    const found = rows.find(r =>
      r.type !== "section_header" && r.type !== "subheader" &&
      (r.label.toLowerCase().includes(lp) ||
       (r.mapping || "").toLowerCase().includes(lp))
    );
    if (found) return found;
  }
  return null;
}

function allRows(): HlfRow[] {
  if (!data.value) return [];
  return data.value.sections.flatMap(s => s.rows);
}

function totalDebt(yearIdx: number): number | null {
  const rows = allRows().filter(r =>
    r.type !== "section_header" && r.type !== "subheader" &&
    (r.label.toLowerCase().includes("займ") ||
     r.label.toLowerCase().includes("borrowing") ||
     (r.mapping || "").toLowerCase().includes("қарзлар"))
  );
  let sum = 0, any = false;
  for (const r of rows) {
    const v = r.values[yearIdx];
    // 2026-05-26: Number-coerce — backend numeric может приходить строкой.
    if (v != null) { sum += Number(v); any = true; }
  }
  return any ? sum : null;
}

interface KpiVal { label: string; key: string; unit: "%" | "x" | "money"; values: (number | null)[]; }

const kpis = computed<KpiVal[]>(() => {
  if (!data.value) return [];
  const years = data.value.years;
  const rows = allRows();
  const get = (key: string, yi: number): number | null => {
    const r = matchRow(rows, key);
    return r ? (r.values[yi] ?? null) : null;
  };
  const computeMetric = (fn: (yi: number) => number | null): (number | null)[] => years.map((_, yi) => fn(yi));

  return [
    {
      label: "Gross margin", key: "gm", unit: "%",
      values: computeMetric(yi => {
        const r = get("revenue", yi), g = get("gross_profit", yi);
        return (r != null && g != null && r > 0) ? (g / r) * 100 : null;
      }),
    },
    {
      label: "EBITDA margin", key: "ebitda_m", unit: "%",
      values: computeMetric(yi => {
        const r = get("revenue", yi), op = get("operating_profit", yi), d = get("depreciation", yi);
        if (r == null || r <= 0 || op == null) return null;
        return ((op + (d == null ? 0 : Math.abs(d))) / r) * 100;
      }),
    },
    {
      label: "Net margin", key: "nm", unit: "%",
      values: computeMetric(yi => {
        const r = get("revenue", yi), np = get("net_profit", yi);
        return (r != null && np != null && r > 0) ? (np / r) * 100 : null;
      }),
    },
    {
      label: "ROA", key: "roa", unit: "%",
      values: computeMetric(yi => {
        const ta = get("total_assets", yi), np = get("net_profit", yi);
        return (ta != null && np != null && ta > 0) ? (np / ta) * 100 : null;
      }),
    },
    {
      label: "ROE", key: "roe", unit: "%",
      values: computeMetric(yi => {
        const eq = get("total_equity", yi), np = get("net_profit", yi);
        return (eq != null && np != null && eq > 0) ? (np / eq) * 100 : null;
      }),
    },
    {
      label: "Debt / EBITDA", key: "de", unit: "x",
      values: computeMetric(yi => {
        const debt = totalDebt(yi);
        const op = get("operating_profit", yi), d = get("depreciation", yi);
        if (debt == null || op == null) return null;
        const ebitda = op + (d == null ? 0 : Math.abs(d));
        return ebitda > 0 ? debt / ebitda : null;
      }),
    },
    {
      label: "Current ratio", key: "cr", unit: "x",
      values: computeMetric(yi => {
        const ca = get("total_current_assets", yi), cl = get("total_current_liabilities", yi);
        return (ca != null && cl != null && cl > 0) ? ca / cl : null;
      }),
    },
    {
      label: "Equity ratio", key: "er", unit: "%",
      values: computeMetric(yi => {
        const ta = get("total_assets", yi), eq = get("total_equity", yi);
        return (ta != null && eq != null && ta > 0) ? (eq / ta) * 100 : null;
      }),
    },
    {
      label: "FCF", key: "fcf", unit: "money",
      values: computeMetric(yi => {
        const cfo = get("operating_cf", yi), cx = get("capex", yi);
        if (cfo == null) return null;
        return cfo - (cx == null ? 0 : Math.abs(cx));
      }),
    },
    {
      label: "CapEx / Revenue", key: "capex_rev", unit: "%",
      values: computeMetric(yi => {
        const r = get("revenue", yi), cx = get("capex", yi);
        return (r != null && cx != null && r > 0) ? (Math.abs(cx) / r) * 100 : null;
      }),
    },
    {
      label: "Revenue YoY", key: "rev_yoy", unit: "%",
      values: computeMetric(yi => {
        if (yi === 0) return null;
        const r = get("revenue", yi), p = get("revenue", yi - 1);
        return (r != null && p != null && p > 0) ? ((r - p) / p) * 100 : null;
      }),
    },
    {
      label: "Net profit YoY", key: "np_yoy", unit: "%",
      values: computeMetric(yi => {
        if (yi === 0) return null;
        const n = get("net_profit", yi), p = get("net_profit", yi - 1);
        return (n != null && p != null && p !== 0) ? ((n - p) / Math.abs(p)) * 100 : null;
      }),
    },
  ];
});

function fmtKpi(v: number | null, unit: string): string {
  if (v == null) return "—";
  if (unit === "%") return `${v >= 0 ? "+" : ""}${v.toFixed(1)}%`;
  if (unit === "x") return `${v.toFixed(2)}×`;
  return fmtNum(v);
}

function kpiColor(kpi: KpiVal, yi: number): string {
  const v = kpi.values[yi];
  if (v == null) return "#94A3B8";
  if (kpi.unit === "%" && ["gm", "ebitda_m", "nm", "roa", "roe", "er", "rev_yoy", "np_yoy"].includes(kpi.key)) {
    if (v < 0) return "#A32D2D";
    if (v < 5) return "#854F0B";
    return "#0F6E56";
  }
  if (kpi.key === "de") {
    if (v > 5) return "#A32D2D";
    if (v > 3) return "#854F0B";
    return "#0F6E56";
  }
  if (kpi.key === "cr") {
    if (v < 1) return "#A32D2D";
    if (v < 1.5) return "#854F0B";
    return "#0F6E56";
  }
  if (kpi.key === "fcf") return v < 0 ? "#A32D2D" : "#0F6E56";
  if (kpi.key === "capex_rev") return v > 30 ? "#854F0B" : "#534AB7";
  return "#1E2A4A";
}

// Premium: directional delta vs prior year. For most metrics higher = better;
// Debt/EBITDA and CapEx/Revenue are inverted (lower = better).
interface KpiDelta { txt: string; dir: 1 | -1 | 0; good: boolean; }
function kpiDelta(k: KpiVal, yi: number): KpiDelta | null {
  if (yi <= 0) return null;
  const cur = k.values[yi], prev = k.values[yi - 1];
  if (cur == null || prev == null) return null;
  const diff = cur - prev;
  if (Math.abs(diff) < 1e-9) return { txt: "—", dir: 0, good: true };
  const lowerBetter = k.key === "de" || k.key === "capex_rev";
  const good = lowerBetter ? diff < 0 : diff > 0;
  let txt: string;
  if (k.unit === "%") txt = `${Math.abs(diff).toFixed(1)} пп`;
  else if (k.unit === "x") txt = `${Math.abs(diff).toFixed(2)}×`;
  else txt = fmtNum(Math.abs(diff));
  return { txt, dir: diff > 0 ? 1 : -1, good };
}

const activeKpiYearIdx = ref<number>(0);

// Auto-select most recent year with data when data loads/changes
watch(data, () => {
  if (!data.value || data.value.years.length === 0) {
    activeKpiYearIdx.value = 0;
    return;
  }
  // Find revenue or any KPI row; pick last year that has a value
  const rows = allRows();
  const revenueRow = matchRow(rows, "revenue") || matchRow(rows, "net_profit") || matchRow(rows, "total_assets");
  if (revenueRow) {
    for (let i = revenueRow.values.length - 1; i >= 0; i--) {
      if (revenueRow.values[i] != null) {
        activeKpiYearIdx.value = i;
        return;
      }
    }
  }
  activeKpiYearIdx.value = data.value.years.length - 1;
}, { deep: true, immediate: true });

// Count how many KPIs have a value at this year
function kpiCoverage(yi: number): number {
  return kpis.value.filter(k => k.values[yi] != null).length;
}

// Premium: bundle per-card render data for the active year (avoids repeated
// function calls in the template).
const kpiCards = computed(() => kpis.value.map(k => ({
  k,
  color: kpiColor(k, activeKpiYearIdx.value),
  valStr: fmtKpi(k.values[activeKpiYearIdx.value], k.unit),
  delta: kpiDelta(k, activeKpiYearIdx.value),
})));
</script>

<template>
  <div class="hlf-card">

    <!-- Header -->
    <div class="hlf-hdr">
      <div class="hlf-hdr-left">
        <div class="hlf-eyebrow">ВЫСОКОУРОВНЕВЫЕ ПОКАЗАТЕЛИ</div>
        <div class="hlf-title">Финансовая отчётность по компаниям</div>
        <div class="hlf-sub">
          Иерархия из консолидированного шаблона
          <template v-if="data?.updated_at"> · ред. {{ formatDate(data.updated_at) }}</template>
          <template v-else-if="data?.imported_at"> · импорт {{ formatDate(data.imported_at) }}</template>
          <span v-if="dirty" class="hlf-dirty"> · есть несохранённые изменения</span>
        </div>
      </div>
      <div class="hlf-hdr-right">
        <select class="hlf-co-sel" v-model="selectedCode">
          <option v-for="co in displayCompanies" :key="co.code" :value="co.code">
            {{ co.code }} · {{ co.name_short || co.name_ru }}
          </option>
        </select>
        <button v-if="data" class="hlf-btn-mode" :class="{ on: editMode }"
                @click="toggleEditMode">
          <svg viewBox="0 0 14 14" width="11" height="11" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"><path d="M2 11L9 4l3 3-7 7H2v-3zM8 5l3 3"/></svg>
          {{ editMode ? "Просмотр" : "Редактировать" }}
        </button>
        <button v-if="editMode && data" class="hlf-btn-year" @click="openAddYear">
          <svg viewBox="0 0 14 14" width="11" height="11" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"><path d="M7 2v10M2 7h10"/></svg>
          + год
        </button>
        <button v-if="editMode && data" class="hlf-btn-section" @click="addSection">
          <svg viewBox="0 0 14 14" width="11" height="11" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"><rect x="2" y="3" width="10" height="8" rx="1"/><path d="M7 5v4M5 7h4"/></svg>
          + секция
        </button>
        <button v-if="dirty && data" class="hlf-btn-save" @click="save" :disabled="saving">
          {{ saving ? "Сохраняю…" : "Сохранить" }}
        </button>
        <button class="hlf-btn-import" @click="triggerFilePick" :disabled="importLoading">
          <svg viewBox="0 0 14 14" width="11" height="11" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"><path d="M7 2v8M3 6l4-4 4 4M2 12h10"/></svg>
          {{ importLoading ? "Импорт…" : "Импорт" }}
        </button>
        <input ref="importFileRef" type="file" accept=".xlsx" style="display:none" @change="onFileChange" />
      </div>
    </div>

    <!-- Add year inline form -->
    <div v-if="showAddYear" class="hlf-add-year">
      <span>Добавить колонку для года:</span>
      <input type="number" v-model.number="newYearValue" min="1990" max="2100" class="hlf-year-inp" />
      <button class="hlf-btn-save" @click="commitAddYear">Добавить</button>
      <button class="hlf-btn-g" @click="showAddYear = false">Отмена</button>
    </div>

    <!-- Import banner -->
    <div v-if="importResult" class="hlf-import-result">
      <strong>✓ Импорт завершён.</strong>
      Обработано компаний: {{ importResult.imported_count || 0 }}.
      <button class="hlf-banner-x" @click="importResult = null">×</button>
    </div>

    <!-- KPI band -->
    <div v-if="data && !error" class="hlf-kpis-wrap">
      <div class="hlf-kpis-hdr">
        <span class="hlf-kpis-lbl">KEY METRICS · {{ data.years[activeKpiYearIdx] }} (млрд UZS · derived)</span>
        <div class="hlf-kpi-yr-pills">
          <button v-for="(y, idx) in data.years" :key="y"
                  class="hlf-yr-pill" :class="{ on: idx === activeKpiYearIdx, weak: kpiCoverage(idx) < 4 }"
                  @click="activeKpiYearIdx = idx"
                  :title="`Покрытие: ${kpiCoverage(idx)}/${kpis.length} KPI`">{{ y }}</button>
        </div>
        <span class="hlf-coverage">{{ kpiCoverage(activeKpiYearIdx) }}/{{ kpis.length }} KPI</span>
      </div>
      <div class="hlf-kpis">
        <div v-for="c in kpiCards" :key="c.k.key" class="hlf-kpi" :title="c.k.label"
             :style="{ '--kpi-accent': c.color }">
          <div class="hlf-kpi-lbl">{{ c.k.label }}</div>
          <div class="hlf-kpi-val" :style="{ color: c.color }"><NumMixed :value="c.valStr" /></div>
          <div v-if="activeKpiYearIdx > 0" class="hlf-kpi-foot">
            <span v-if="c.delta && c.delta.dir !== 0" class="hlf-kpi-delta"
                  :class="c.delta.good ? 'good' : 'bad'">
              <svg viewBox="0 0 10 10" width="8" height="8" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round">
                <path v-if="c.delta.dir === 1" d="M5 8V2M2.5 4.5L5 2l2.5 2.5"/>
                <path v-else d="M5 2v6M2.5 5.5L5 8l2.5-2.5"/>
              </svg>{{ c.delta.txt }}
            </span>
            <span class="hlf-kpi-prev-y">vs {{ data.years[activeKpiYearIdx - 1] }}</span>
          </div>
        </div>
      </div>
    </div>

    <!-- States -->
    <div v-if="loading" class="hlf-state">Загрузка…</div>
    <div v-else-if="error" class="hlf-state hlf-state-error">{{ error }}</div>
    <div v-else-if="!data" class="hlf-state hlf-state-empty">
      <div class="hlf-empty-icon">
        <svg viewBox="0 0 32 32" width="40" height="40" fill="none" stroke="currentColor" stroke-width="1.4" stroke-linecap="round"><rect x="5" y="4" width="22" height="24" rx="2"/><path d="M10 11h12M10 15h12M10 19h8M10 23h6"/></svg>
      </div>
      <div class="hlf-empty-title">Данные не загружены</div>
      <div class="hlf-empty-text">
        Загрузи XLSX-шаблон с консолидированными показателями (SOFP / P&amp;L / Cash Flow)
        через кнопку «Импорт» наверху. Парсер обработает все 22 листа автоматически.
      </div>
    </div>

    <!-- Data sections -->
    <template v-else>
      <div v-for="(sec, secIdx) in data.sections" :key="sec.id" class="hlf-section">

        <div class="hlf-sec-hdr">
          <svg class="hlf-chevron" :class="{ collapsed: collapsedSec.has(sec.id) }"
               @click="toggleSection(sec.id)"
               viewBox="0 0 12 12" width="11" height="11" fill="none" stroke="currentColor"
               stroke-width="1.8" stroke-linecap="round"><path d="M4 3l4 3-4 3"/></svg>
          <span v-if="!editMode" class="hlf-sec-title" @click="toggleSection(sec.id)">{{ sec.title }}</span>
          <input v-else type="text" class="hlf-sec-title-inp" :value="sec.title"
                 @input="onSectionTitleInput(sec, ($event.target as HTMLInputElement).value)" />
          <span class="hlf-sec-meta">{{ sec.rows.length }} строк · {{ data.unit === 'bln' ? 'млрд UZS' : data.unit }}</span>
          <button v-if="editMode" class="hlf-sec-remove" @click="removeSection(secIdx)" title="Удалить секцию">×</button>
        </div>

        <div v-if="!collapsedSec.has(sec.id)" class="hlf-table-wrap">
          <table class="hlf-table">
            <thead>
              <tr>
                <th class="hlf-th-name">ПОКАЗАТЕЛЬ</th>
                <th v-for="(y, idx) in sec.years" :key="y" class="hlf-th-num"
                    :class="{ current: idx === sec.years.length - 1 }">
                  {{ y }}
                  <button v-if="editMode" class="hlf-th-x" @click="removeYear(y)" title="Удалить год">×</button>
                </th>
                <th v-if="editMode" class="hlf-th-actions"></th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="(row, rowIdx) in sec.rows" :key="`${sec.id}-${rowIdx}`"
                  :class="[`hlf-row-${row.type}`]">
                <td class="hlf-td-name">
                  <input v-if="editMode" type="text" class="hlf-label-inp" :value="row.label"
                         @input="onLabelInput(row, ($event.target as HTMLInputElement).value)" />
                  <template v-else>{{ row.label }}</template>
                </td>
                <template v-if="['section_header', 'subheader'].includes(row.type) && !editMode">
                  <td :colspan="sec.years.length" class="hlf-td-empty"></td>
                </template>
                <template v-else>
                  <td v-for="(v, j) in row.values" :key="j" class="hlf-td-num"
                      :class="{ current: j === sec.years.length - 1, negative: v != null && v < 0 }">
                    <input v-if="editMode" type="text" class="hlf-cell-inp"
                           :value="getCellDisplay(v)"
                           @input="onCellInput(row, j, ($event.target as HTMLInputElement).value)"
                           placeholder="—" />
                    <template v-else>{{ fmtNum(v) }}</template>
                  </td>
                </template>
                <td v-if="editMode" class="hlf-td-actions">
                  <button class="hlf-act-btn" @click="moveRow(sec, rowIdx, -1)" :disabled="rowIdx === 0">↑</button>
                  <button class="hlf-act-btn" @click="moveRow(sec, rowIdx, 1)" :disabled="rowIdx === sec.rows.length - 1">↓</button>
                  <button class="hlf-act-btn act-x" @click="removeRow(sec, rowIdx)">×</button>
                </td>
              </tr>
              <tr v-if="editMode" class="hlf-add-row">
                <td :colspan="sec.years.length + 2">
                  <button class="hlf-add-btn" @click="addRow(sec, 'line')">+ строка</button>
                  <button class="hlf-add-btn" @click="addRow(sec, 'subheader')">+ подсекция</button>
                  <button class="hlf-add-btn" @click="addRow(sec, 'subtotal')">+ подытог</button>
                  <button class="hlf-add-btn" @click="addRow(sec, 'total')">+ итого</button>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    </template>

  </div>
</template>

<style scoped>
/* Design code (the design guide §6):
 *   Cards 11-14px, buttons 8px, palette #7F77DD/var(--p-deep)/var(--green)/var(--amber)/var(--sev-high),
 *   borders var(--border-hard), surface light #FAFAFC, muted text var(--t-muted),
 *   headings 15px/500 letter-spacing -.01em, section labels 10px/500/uppercase/.08em,
 *   font-weight max 500, easing var(--ease-standard) */
.hlf-card {
  background: var(--bg1, #fff);
  border-radius: 14px;
  border: 1px solid var(--border-hard);
  overflow: hidden;
  margin-top: 16px;
  box-shadow: 0 1px 2px rgba(15, 23, 60, 0.04), 0 8px 28px rgba(15, 23, 60, 0.05);
  transition: box-shadow 0.2s var(--ease-standard, cubic-bezier(.34, 1.2, .64, 1));
}
.hlf-card:hover { box-shadow: 0 2px 6px rgba(15, 23, 60, 0.06), 0 14px 40px rgba(15, 23, 60, 0.08); }

.hlf-hdr {
  padding: 16px 20px;
  border-bottom: 1px solid var(--border-hard);
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 14px;
  flex-wrap: wrap;
}
.hlf-hdr-left { min-width: 0; flex: 1; }
.hlf-eyebrow {
  font-size: 10px;
  font-weight: 500;
  letter-spacing: 0.08em;
  color: var(--t3, var(--t-muted));
  text-transform: uppercase;
}
.hlf-title {
  font-size: 15px;
  font-weight: 500;
  letter-spacing: -0.01em;
  margin-top: 4px;
  color: var(--t1, #1E2A4A);
}
.hlf-sub { font-size: 12px; color: var(--t3, var(--t-muted)); margin-top: 4px; }
.hlf-dirty { color: var(--amber); font-weight: 500; }

.hlf-hdr-right { display: flex; gap: 6px; align-items: center; flex-wrap: wrap; }
.hlf-co-sel {
  padding: 6px 11px;
  font-size: 12px;
  border: 1px solid var(--border-hard);
  border-radius: 8px;
  background: var(--bg1, #fff);
  color: var(--t1, #1E2A4A);
  font-family: inherit;
  outline: none;
  cursor: pointer;
  min-width: 240px;
  transition: border-color 0.12s ease;
}
.hlf-co-sel:focus { border-color: #7F77DD; }

.hlf-btn-mode, .hlf-btn-year, .hlf-btn-section, .hlf-btn-import, .hlf-btn-save, .hlf-btn-g {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  padding: 6px 11px;
  font-size: 11px;
  font-weight: 500;
  border-radius: 8px;
  cursor: pointer;
  font-family: inherit;
  border: 1px solid;
  transition: background 0.12s ease, color 0.12s ease, border-color 0.12s ease;
}
.hlf-btn-mode { border-color: var(--border-input); background: var(--bg1, #fff); color: var(--t3, var(--t3)); }
.hlf-btn-mode:hover { background: rgba(127, 119, 221, 0.06); color: var(--p-deep); border-color: #7F77DD; }
.hlf-btn-mode.on { background: #7F77DD; color: #fff; border-color: #7F77DD; }
.hlf-btn-year, .hlf-btn-section { border-color: #7F77DD; background: rgba(127, 119, 221, 0.08); color: var(--p-deep); }
.hlf-btn-year:hover, .hlf-btn-section:hover { background: rgba(127, 119, 221, 0.16); }
.hlf-btn-import { border-color: var(--border-input); background: var(--bg1, #fff); color: var(--t3, var(--t3)); }
.hlf-btn-import:hover { background: rgba(127, 119, 221, 0.06); color: var(--p-deep); border-color: #7F77DD; }
.hlf-btn-save { border-color: var(--green); background: var(--green); color: #fff; }
.hlf-btn-save:hover { background: #178D69; }
.hlf-btn-save:disabled { opacity: 0.6; cursor: not-allowed; }
.hlf-btn-g { border-color: var(--border-input); background: var(--bg1, #fff); color: var(--t3, var(--t3)); }
.hlf-btn-g:hover { background: #F1F5F9; }

.hlf-add-year {
  padding: 10px 20px;
  background: rgba(127, 119, 221, 0.06);
  border-bottom: 1px solid var(--border-hard);
  display: flex; align-items: center; gap: 10px;
  font-size: 12px; color: var(--p-deep);
}
.hlf-year-inp {
  width: 80px;
  padding: 5px 9px;
  font-size: 12px;
  border: 1px solid var(--border-hard);
  border-radius: 8px;
  font-family: inherit;
  outline: none;
  transition: border-color 0.12s ease;
}
.hlf-year-inp:focus { border-color: #7F77DD; }

.hlf-import-result {
  margin: 12px 20px 0; padding: 9px 14px;
  background: rgba(29, 158, 117, 0.08);
  border: 1px solid rgba(29, 158, 117, 0.25);
  color: #0F6E56; font-size: 11.5px;
  border-radius: 8px; position: relative;
}
.hlf-banner-x {
  position: absolute; top: 6px; right: 8px;
  width: 20px; height: 20px;
  border: none; background: transparent;
  color: #0F6E56; cursor: pointer;
  font-size: 16px; line-height: 1;
}

.hlf-kpis-wrap { border-bottom: 1px solid var(--border-hard); background: var(--bg2, #FAFAFC); }
.hlf-kpis-hdr {
  padding: 10px 20px 6px;
  display: flex; align-items: center; gap: 12px; flex-wrap: wrap;
}
.hlf-kpis-lbl {
  font-size: 10px;
  font-weight: 500;
  color: var(--t3, var(--t-muted));
  letter-spacing: 0.08em;
  text-transform: uppercase;
}
.hlf-kpi-yr-pills { display: inline-flex; gap: 2px; padding: 2px; background: var(--bg2, #FAFAFC); border-radius: 8px; }
.hlf-yr-pill {
  padding: 4px 10px;
  font-size: 11px;
  font-weight: 500;
  border-radius: 6px;
  border: none;
  background: transparent;
  color: var(--t3, var(--t-muted));
  cursor: pointer;
  font-family: inherit;
  transition: background 0.12s ease, color 0.12s ease;
}
.hlf-yr-pill:hover { background: rgba(127, 119, 221, 0.10); color: var(--p-deep); }
.hlf-yr-pill.on { background: var(--bg1, #fff); color: var(--t1, #1E2A4A); box-shadow: 0 1px 2px rgba(15, 23, 60, 0.08); }
.hlf-yr-pill.weak { color: #C9C8C0; }
.hlf-yr-pill.weak.on { color: var(--t3, var(--t-muted)); }
.hlf-coverage {
  font-size: 10px;
  color: var(--t3, var(--t-muted));
  padding: 3px 9px;
  background: rgba(127, 119, 221, 0.08);
  border-radius: 11px;
  margin-left: auto;
}
.hlf-kpis {
  display: grid; grid-template-columns: repeat(auto-fit, minmax(120px, 1fr));
  gap: 1px; background: var(--border-hard); padding: 0 0 1px;
}
.hlf-kpi {
  background: var(--bg1, #fff);
  padding: 12px 13px 11px;
  position: relative;
  overflow: hidden;
  transition: background 0.16s var(--ease-standard, cubic-bezier(.34, 1.2, .64, 1)),
              transform 0.16s var(--ease-standard, cubic-bezier(.34, 1.2, .64, 1));
}
/* Accent bar — health colour of the metric, revealed on hover. */
.hlf-kpi::before {
  content: "";
  position: absolute;
  top: 0; left: 0; right: 0;
  height: 2px;
  background: var(--kpi-accent, #7F77DD);
  opacity: 0;
  transition: opacity 0.16s ease;
}
.hlf-kpi:hover {
  background: linear-gradient(180deg, rgba(127, 119, 221, 0.045), rgba(127, 119, 221, 0.015));
  transform: translateY(-1px);
}
.hlf-kpi:hover::before { opacity: 0.9; }
.hlf-kpi-lbl {
  font-size: 10px;
  font-weight: 500;
  color: var(--t3, var(--t-muted));
  letter-spacing: 0.06em;
  text-transform: uppercase;
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
}
.hlf-kpi-val {
  font-size: 22px;
  font-weight: 400;
  letter-spacing: -0.025em;
  margin-top: 5px;
  line-height: 1;
  font-feature-settings: 'tnum';
}
.hlf-kpi-foot {
  display: flex; align-items: center; gap: 7px;
  margin-top: 7px;
}
.hlf-kpi-delta {
  display: inline-flex; align-items: center; gap: 3px;
  font-size: 10px; font-weight: 500;
  padding: 1.5px 6px 1.5px 4px;
  border-radius: 11px;
  font-feature-settings: 'tnum';
  line-height: 1.3;
}
.hlf-kpi-delta.good { color: #0F6E56; background: rgba(29, 158, 117, 0.10); }
.hlf-kpi-delta.bad  { color: #A32D2D; background: rgba(226, 75, 74, 0.10); }
.hlf-kpi-prev-y { font-size: 10px; color: var(--t4, #C9C8C0); letter-spacing: 0.02em; }

.hlf-state { padding: 40px 24px; text-align: center; color: var(--t3, var(--t-muted)); font-size: 12px; }
.hlf-state-error { color: var(--sev-high); }
.hlf-state-empty { display: flex; flex-direction: column; align-items: center; gap: 8px; padding: 50px 24px; }
.hlf-empty-icon { color: #C9C8C0; }
.hlf-empty-title { color: var(--t1, #1E2A4A); font-size: 15px; font-weight: 500; letter-spacing: -0.01em; margin-top: 8px; }
.hlf-empty-text { color: var(--t3, var(--t-muted)); font-size: 12px; max-width: 480px; line-height: 1.55; }

.hlf-section { border-top: 1px solid var(--border-hard); }
.hlf-section:first-of-type { border-top: none; }

.hlf-sec-hdr {
  padding: 12px 20px;
  background: var(--bg2, #FAFAFC);
  display: flex; align-items: center; gap: 10px;
  border-bottom: 1px solid var(--border-hard);
}
.hlf-chevron {
  color: var(--t3, var(--t-muted));
  transition: transform 0.22s var(--ease-standard), color 0.12s ease;
  transform: rotate(90deg);
  cursor: pointer;
}
.hlf-chevron.collapsed { transform: rotate(0deg); }
.hlf-sec-title { font-size: 13px; font-weight: 500; color: var(--t1, #1E2A4A); letter-spacing: -0.01em; cursor: pointer; }
.hlf-sec-title:hover { color: var(--p-deep); }
.hlf-sec-title-inp {
  font-size: 13px;
  font-weight: 500;
  color: var(--t1, #1E2A4A);
  padding: 5px 9px;
  border: 1px solid var(--border-hard);
  border-radius: 8px;
  background: var(--bg1, #fff);
  outline: none;
  font-family: inherit;
  flex: 1;
  max-width: 400px;
  transition: border-color 0.12s ease;
}
.hlf-sec-title-inp:focus { border-color: #7F77DD; }
.hlf-sec-meta { font-size: 11px; color: var(--t3, var(--t-muted)); margin-left: auto; }
.hlf-sec-remove {
  width: 22px; height: 22px;
  border: 1px solid var(--border-hard); background: var(--bg1, #fff);
  color: var(--t3, var(--t-muted)); cursor: pointer; border-radius: 8px;
  font-size: 15px; line-height: 1;
  transition: background 0.12s ease, color 0.12s ease, border-color 0.12s ease;
}
.hlf-sec-remove:hover { background: rgba(226, 75, 74, 0.06); border-color: var(--sev-high); color: var(--sev-high); }

.hlf-table-wrap { overflow-x: auto; }
.hlf-table { width: 100%; border-collapse: collapse; font-size: 12px; }
.hlf-table thead { background: var(--bg2, #FAFAFC); }
.hlf-table th {
  padding: 8px 12px;
  text-align: left;
  font-size: 10px;
  font-weight: 500;
  color: var(--t3, var(--t-muted));
  text-transform: uppercase;
  letter-spacing: 0.06em;
  border-bottom: 1px solid var(--border-hard);
  position: relative;
}
.hlf-th-name { padding-left: 20px; min-width: 280px; }
.hlf-th-num { text-align: right; width: 110px; }
.hlf-th-num.current { color: var(--t1, #1E2A4A); padding-right: 20px; }
.hlf-th-actions { width: 80px; }
.hlf-th-x {
  position: absolute; top: 50%; right: 4px; transform: translateY(-50%);
  width: 16px; height: 16px; border: none; background: transparent;
  color: var(--t3, var(--t-muted)); cursor: pointer; font-size: 14px; line-height: 1; border-radius: 4px;
}
.hlf-th-x:hover { background: rgba(226, 75, 74, 0.10); color: var(--sev-high); }

.hlf-table td { padding: 6px 12px; border-bottom: 1px solid var(--border-hard); vertical-align: middle; }
.hlf-td-name { padding-left: 20px; color: var(--t1, #1E2A4A); font-size: 12px; max-width: 480px; }
.hlf-td-num { text-align: right; font-feature-settings: 'tnum'; color: var(--t1, #1E2A4A); white-space: nowrap; font-size: 12px; }
.hlf-td-num.current { padding-right: 20px; font-weight: 500; }
.hlf-td-num.negative { color: var(--sev-high); }
.hlf-td-empty { background: transparent; }

/* Premium: row hover for data lines + subtle current-year column tint. */
.hlf-table tbody tr.hlf-row-line td,
.hlf-table tbody tr.hlf-row-subtotal td {
  transition: background 0.1s ease;
}
.hlf-table tbody tr.hlf-row-line:hover td { background: rgba(127, 119, 221, 0.05); }
.hlf-table tbody tr.hlf-row-subtotal:hover td { background: rgba(127, 119, 221, 0.07); }
.hlf-th-num.current { background: rgba(127, 119, 221, 0.05); }
.hlf-row-line .hlf-td-num.current,
.hlf-row-subtotal .hlf-td-num.current { background: rgba(127, 119, 221, 0.035); }
.hlf-table tbody tr.hlf-row-line:hover .hlf-td-num.current { background: rgba(127, 119, 221, 0.085); }

.hlf-cell-inp {
  width: 100%;
  padding: 4px 7px;
  text-align: right;
  border: 1px solid transparent;
  background: rgba(127, 119, 221, 0.04);
  border-radius: 6px;
  font-family: inherit;
  font-size: 12px;
  color: var(--t1, #1E2A4A);
  outline: none;
  font-feature-settings: 'tnum';
  transition: border-color 0.12s ease, background 0.12s ease, box-shadow 0.12s ease;
}
.hlf-cell-inp:focus { background: var(--bg1, #fff); border-color: #7F77DD; box-shadow: 0 0 0 2px rgba(127, 119, 221, 0.15); }
.hlf-label-inp {
  width: 100%;
  padding: 4px 7px;
  border: 1px solid transparent;
  background: rgba(127, 119, 221, 0.04);
  border-radius: 6px;
  font-family: inherit;
  font-size: 12px;
  color: var(--t1, #1E2A4A);
  outline: none;
  transition: border-color 0.12s ease, background 0.12s ease, box-shadow 0.12s ease;
}
.hlf-label-inp:focus { background: var(--bg1, #fff); border-color: #7F77DD; box-shadow: 0 0 0 2px rgba(127, 119, 221, 0.15); }

.hlf-row-section_header td { background: rgba(127, 119, 221, 0.08); padding-top: 9px; padding-bottom: 9px; }
.hlf-row-section_header .hlf-td-name {
  font-size: 11px;
  font-weight: 500;
  color: var(--p-deep);
  text-transform: uppercase;
  letter-spacing: 0.06em;
}
.hlf-row-subheader td { background: rgba(127, 119, 221, 0.03); padding-top: 7px; padding-bottom: 7px; }
.hlf-row-subheader .hlf-td-name {
  font-size: 11px;
  font-weight: 500;
  color: var(--t3, var(--t-muted));
  text-transform: uppercase;
  letter-spacing: 0.06em;
  padding-left: 20px;
}
.hlf-row-line .hlf-td-name { padding-left: 36px; color: var(--t1, #1E2A4A); }
.hlf-row-subtotal td { background: rgba(127, 119, 221, 0.04); padding-top: 6px; padding-bottom: 6px; }
.hlf-row-subtotal .hlf-td-name { padding-left: 20px; font-weight: 500; color: var(--t1, #1E2A4A); }
.hlf-row-subtotal .hlf-td-num { font-weight: 500; }
.hlf-row-total td {
  background: rgba(29, 158, 117, 0.07);
  border-top: 1px solid rgba(29, 158, 117, 0.30);
  padding-top: 8px;
  padding-bottom: 8px;
  color: var(--green);
}
.hlf-row-total .hlf-td-name {
  padding-left: 20px;
  font-weight: 500;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  font-size: 11px;
}
.hlf-row-total .hlf-td-num { color: var(--green); font-weight: 500; }

.hlf-td-actions { text-align: center; white-space: nowrap; }
.hlf-act-btn {
  width: 22px;
  height: 22px;
  border: 1px solid var(--border-hard);
  background: var(--bg1, #fff);
  color: var(--t3, var(--t-muted));
  cursor: pointer;
  border-radius: 6px;
  font-size: 12px;
  line-height: 1;
  margin: 0 1px;
  transition: background 0.12s ease, color 0.12s ease, border-color 0.12s ease;
}
.hlf-act-btn:hover { background: rgba(127, 119, 221, 0.08); color: var(--p-deep); border-color: #7F77DD; }
.hlf-act-btn:disabled { opacity: 0.4; cursor: not-allowed; }
.hlf-act-btn.act-x:hover { background: rgba(226, 75, 74, 0.06); color: var(--sev-high); border-color: var(--sev-high); }

.hlf-add-row td { padding: 8px 20px; background: rgba(127, 119, 221, 0.03); border-bottom: 1px dashed rgba(127, 119, 221, 0.20); }
.hlf-add-btn {
  margin-right: 6px;
  padding: 4px 11px;
  font-size: 11px;
  font-weight: 500;
  border: 1px dashed var(--border-hard);
  background: var(--bg1, #fff);
  color: var(--t3, var(--t-muted));
  cursor: pointer;
  border-radius: 8px;
  font-family: inherit;
  transition: background 0.12s ease, color 0.12s ease, border-color 0.12s ease;
}
.hlf-add-btn:hover { background: rgba(127, 119, 221, 0.06); color: var(--p-deep); border-color: #7F77DD; }

/* ═══════════ MOBILE / TABLET (Phase 2) ═══════════ */
@media (max-width: 768px) {
  /* Шапка: заголовок сверху, контролы — отдельной строкой на всю ширину */
  .hlf-hdr { padding: 12px 14px; flex-direction: column; align-items: stretch; gap: 10px; }
  .hlf-hdr-right { width: 100%; }
  .hlf-co-sel { flex: 1 1 100%; min-width: 0; }

  /* KPI-band плотнее */
  .hlf-kpis-hdr { padding: 8px 14px 5px; }
  .hlf-kpi { padding: 10px 11px; }

  /* Таблица: первая колонка (показатель) фиксируется при горизонтальном
     скролле по годам — её всегда видно. Фон делаем непрозрачным под каждый
     тип строки, иначе цифры просвечивают. */
  .hlf-table { font-size: 12px; }
  .hlf-th, .hlf-table td { padding-left: 12px; padding-right: 10px; }
  .hlf-th-name { min-width: 150px; padding-left: 14px; }
  .hlf-td-name { padding-left: 14px; max-width: 200px; white-space: normal; }

  .hlf-th-name, .hlf-td-name {
    position: sticky;
    left: 0;
    z-index: 2;
  }
  .hlf-th-name { z-index: 3; background: #FAFAFC; }
  .hlf-row-line .hlf-td-name,
  .hlf-td-name { background: var(--bg1, #fff); }
  .hlf-row-subheader .hlf-td-name { background: #F9F8FE; }
  .hlf-row-subtotal .hlf-td-name  { background: #F7F6FD; }
  .hlf-row-section_header .hlf-td-name { background: #F1EFFB; }
  .hlf-row-total .hlf-td-name { background: #EFF8F4; }
  /* лёгкая тень-разделитель у залипшей колонки */
  .hlf-td-name, .hlf-th-name { box-shadow: 1px 0 0 var(--border-hard); }

  .hlf-section .hlf-sec-hdr { padding: 10px 14px; }
}

@media (max-width: 480px) {
  .hlf-kpis { grid-template-columns: repeat(2, minmax(0, 1fr)); }
}
</style>
