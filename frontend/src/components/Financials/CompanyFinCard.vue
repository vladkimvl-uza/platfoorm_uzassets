<script setup lang="ts">
// ============================================================================
// CompanyFinCard — full financial drill-down modal.
//
// Opens when user clicks a company in scoreboard or sector table.
// Shows for the selected company:
//   - Header: sector color dot + name + standard + year range + close
//   - 3 inner tabs: SOFP / P&L / Cash Flow
//   - 4 KPI cards (depending on tab) for the most recent year with data
//   - Two charts side-by-side:
//        Left:  bar chart (P&L structure, balance composition, or CF flows)
//        Right: line trend (multi-year evolution of key metrics)
//   - Detailed table: major / subtotal / sub rows with collapsible sections
//
// 1:1 port of legacy showCompanyFinCard (lines 43829-44081).
// ============================================================================

import { computed, onBeforeUnmount, onMounted, ref, watch, nextTick } from "vue";
import type { PortfolioSummaryResponse, PortfolioCompanyMetrics } from "@/api/financials";
import type { CompanyListItem, SectorBrief } from "@/api/companies";
import { fmtCompact, sectorColor, buildCompanyIndex } from "./financialsHelpers";

const props = defineProps<{
  companyCode: string;
  summary: PortfolioSummaryResponse | null;
  companies: CompanyListItem[];
  sectors: SectorBrief[];
  standard: "IFRS" | "NSBU";
  unit: "bln" | "mln";
  currency: string;
}>();

const emit = defineEmits<{
  (e: "close"): void;
}>();

// ─── Local state ──────────────────────────────────────────────────────────
type CardTab = "sofp" | "pnl" | "cashflow";
const activeTab = ref<CardTab>("pnl");
const collapsedGroups = ref<Set<string>>(new Set());

const TABS: Array<{ id: CardTab; label: string }> = [
  { id: "sofp",     label: "SOFP" },
  { id: "pnl",      label: "P&L" },
  { id: "cashflow", label: "Cash Flow" },
];

// ─── Lookups ─────────────────────────────────────────────────────────────
const companyIdx = computed(() => buildCompanyIndex(props.companies));
const sectorByCode = computed(() => {
  const m: Record<string, SectorBrief> = {};
  for (const s of props.sectors) m[String(s.code).toLowerCase()] = s;
  return m;
});

const item = computed<PortfolioCompanyMetrics | null>(() => {
  if (!props.summary) return null;
  return props.summary.items.find(it => it.company_code === props.companyCode) || null;
});

const company = computed(() => {
  return companyIdx.value.get(props.companyCode.toLowerCase()) || null;
});

const sectorClr = computed(() => {
  if (!company.value) return "#7F77DD";
  const sec = sectorByCode.value[String(company.value.sector_code || "").toLowerCase()];
  return sectorColor(sec);
});

const yearsAvailable = computed<number[]>(() => {
  if (!item.value) return [];
  const ys = Object.keys(item.value.by_year).map(s => parseInt(s)).filter(n => !isNaN(n));
  return ys.sort((a, b) => a - b);
});

const yearMin = computed(() => yearsAvailable.value[0] ?? 0);
const yearMax = computed(() => yearsAvailable.value[yearsAvailable.value.length - 1] ?? 0);

// "Last year with data" for KPI cards — finds rightmost year that has at
// least one of the tab's primary fields filled.
function lastYearWithData(fields: string[]): number {
  if (!item.value) return 0;
  for (let i = yearsAvailable.value.length - 1; i >= 0; i--) {
    const y = yearsAvailable.value[i];
    const data = item.value.by_year[y];
    if (data && fields.some(f => data[f] != null && data[f] !== 0)) {
      return y;
    }
  }
  return yearMax.value;
}

const kpiYear = computed(() => {
  if (activeTab.value === "sofp")
    return lastYearWithData(["totalAssets", "equity", "debt"]);
  if (activeTab.value === "pnl")
    return lastYearWithData(["revenue", "profit", "ebitda"]);
  return lastYearWithData(["cfo", "cfi", "cff", "cash"]);
});

function v(field: string, year: number): number | null {
  if (!item.value) return null;
  const d = item.value.by_year[year];
  if (!d) return null;
  const x = d[field];
  return typeof x === "number" ? x : null;
}

function fmt(value: number | null | undefined): string {
  if (value == null) return "—";
  return fmtCompact(value, props.unit);
}

// ─── KPI cards data ──────────────────────────────────────────────────────
interface Kpi { label: string; value: string; color?: string; }

const kpis = computed<Kpi[]>(() => {
  const y = kpiYear.value;
  if (activeTab.value === "sofp") {
    const eq = v("equity", y), dt = v("debt", y);
    const de = (eq && eq > 0) ? ((dt || 0) / eq).toFixed(2) + "x" : "—";
    return [
      { label: `АКТИВЫ ${y}`, value: fmt(v("totalAssets", y)) },
      { label: `КАПИТАЛ ${y}`, value: fmt(eq), color: "#1D9E75" },
      { label: `ОБЯЗАТ. ${y}`, value: fmt(v("totalLiabilities", y)), color: "#E24B4A" },
      { label: `D/E`, value: de },
    ];
  }
  if (activeTab.value === "pnl") {
    const rev = v("revenue", y), gp = v("grossProfit", y);
    const gm = (rev && rev > 0) ? Math.round(((gp || 0) / rev) * 100) + "%" : "—";
    const profit = v("profit", y);
    const nm = (rev && rev > 0) ? Math.round(((profit || 0) / rev) * 100) + "%" : "—";
    return [
      { label: `ВЫРУЧКА ${y}`, value: fmt(rev) },
      { label: `ВАЛ. МАРЖА`, value: gm },
      { label: `EBITDA ${y}`, value: fmt(v("ebitda", y)) },
      {
        label: `ЧИСТ. МАРЖА`,
        value: nm,
        color: profit != null && profit >= 0 ? "#1D9E75" : "#E24B4A",
      },
    ];
  }
  // cashflow
  const cfo = v("cfo", y), cfi = v("cfi", y), cff = v("cff", y);
  return [
    { label: `CFO ${y}`,  value: fmt(cfo), color: cfo != null && cfo >= 0 ? "#1D9E75" : "#E24B4A" },
    { label: `CFI ${y}`,  value: fmt(cfi), color: cfi != null && cfi >= 0 ? "#1D9E75" : "#E24B4A" },
    { label: `CFF ${y}`,  value: fmt(cff), color: cff != null && cff >= 0 ? "#1D9E75" : "#E24B4A" },
    { label: `КЭШ ${y}`,  value: fmt(v("cash", y)) },
  ];
});

// ─── Table rows definition (NSBU-style) ─────────────────────────────────
interface TblRow {
  label: string;
  field?: string;
  section?: boolean;
  major?: boolean;
  sub?: boolean;
  nested?: boolean;
  groupId?: string;
}

const tableRows = computed<TblRow[]>(() => {
  if (activeTab.value === "sofp") {
    return [
      { label: "БАЛАНС — АКТИВЫ", section: true, groupId: "g1" },
      { label: "Внеоборотные активы", field: "totalNCA", sub: true, groupId: "g1" },
      { label: "ОС", field: "ppe", sub: true, nested: true, groupId: "g1" },
      { label: "Оборотные активы", field: "totalCA", sub: true, groupId: "g1" },
      { label: "Денежные средства", field: "cash", sub: true, nested: true, groupId: "g1" },
      { label: "ИТОГО Активы", field: "totalAssets", major: true },
      { label: "КАПИТАЛ И ОБЯЗАТЕЛЬСТВА", section: true, groupId: "g2" },
      { label: "Собственный капитал", field: "equity", major: true },
      { label: "Долгосрочные обязательства", field: "ltBorrowings", sub: true, groupId: "g2" },
      { label: "Краткосрочные обязательства", field: "stBorrowings", sub: true, groupId: "g2" },
      { label: "Совокупный долг", field: "debt", sub: true, nested: true, groupId: "g2" },
      { label: "ИТОГО Обязательства", field: "totalLiabilities", major: true },
    ];
  }
  if (activeTab.value === "pnl") {
    return [
      { label: "ДОХОДЫ И РАСХОДЫ", section: true, groupId: "g1" },
      { label: "Выручка", field: "revenue", major: true },
      { label: "Себестоимость", field: "cogs", sub: true, groupId: "g1" },
      { label: "Валовая прибыль", field: "grossProfit", major: true },
      { label: "Операционная прибыль", field: "opProfit", sub: true, groupId: "g1" },
      { label: "Финансовые доходы", field: "finIncome", sub: true, nested: true, groupId: "g1" },
      { label: "Финансовые расходы", field: "finCost", sub: true, nested: true, groupId: "g1" },
      { label: "Прибыль до налога", field: "pbt", sub: true, groupId: "g1" },
      { label: "Налог на прибыль", field: "tax", sub: true, nested: true, groupId: "g1" },
      { label: "Чистая прибыль", field: "profit", major: true },
      { label: "EBITDA", field: "ebitda", major: true },
    ];
  }
  return [
    { label: "ДЕНЕЖНЫЕ ПОТОКИ", section: true, groupId: "g1" },
    { label: "Операционный ДДС", field: "cfo", major: true },
    { label: "Инвестиционный ДДС", field: "cfi", major: true },
    { label: "Финансовый ДДС", field: "cff", major: true },
    { label: "Дивиденды выплаченные", field: "dividendsPaid", sub: true, nested: true, groupId: "g1" },
    { label: "Изменение ДС", field: "netCashChange", major: true },
  ];
});

const hasAnyData = computed(() => {
  return tableRows.value.some(r => {
    if (!r.field) return false;
    return yearsAvailable.value.some(y => v(r.field!, y) != null);
  });
});

function toggleGroup(id: string) {
  const next = new Set(collapsedGroups.value);
  if (next.has(id)) next.delete(id);
  else next.add(id);
  collapsedGroups.value = next;
}

function rowVisible(row: TblRow): boolean {
  // section rows always visible; child rows hidden if their group is collapsed
  if (row.section) return true;
  if (!row.groupId) return true;
  return !collapsedGroups.value.has(row.groupId);
}

// ─── Charts (Chart.js) ───────────────────────────────────────────────────
const barCanvas  = ref<HTMLCanvasElement | null>(null);
const lineCanvas = ref<HTMLCanvasElement | null>(null);
let barChart: any = null;
let lineChart: any = null;

async function ensureChart() {
  if ((window as any).Chart) return;
  try {
    // 2026-05-26: chart.js/auto → cherry-picked register (shared bundle).
    const mod = await import("@/utils/chartjsRegister");
    (window as any).Chart = mod.Chart;
  } catch {
    /* */
  }
}

function destroyCharts() {
  if (barChart)  { try { barChart.destroy(); }  catch {} barChart = null; }
  if (lineChart) { try { lineChart.destroy(); } catch {} lineChart = null; }
}

async function renderCharts() {
  await ensureChart();
  const Chart = (window as any).Chart;
  if (!Chart) return;
  destroyCharts();
  await nextTick();

  const y = kpiYear.value;

  // Bar chart — structure breakdown for the active tab
  if (barCanvas.value) {
    let labels: string[], data: Array<number | null>, colors: string[];
    if (activeTab.value === "pnl") {
      labels = ["Выручка", "Себест.", "Вал.приб.", "Опер.", "Налог", "Чист."];
      data = [
        v("revenue", y),
        -(v("cogs", y) || 0),
        v("grossProfit", y),
        v("opProfit", y),
        -(v("tax", y) || 0),
        v("profit", y),
      ];
      colors = ["#7F77DD", "#E24B4A", "#1D9E75", "#378ADD", "#EF9F27", "#1D9E75"];
    } else if (activeTab.value === "sofp") {
      labels = ["Внеоб.", "Оборот.", "Активы", "Капитал", "Долг.об.", "Кратк."];
      data = [
        v("totalNCA", y), v("totalCA", y), v("totalAssets", y),
        v("equity", y), v("ltBorrowings", y), v("stBorrowings", y),
      ];
      colors = ["#7F77DD", "#9B8EC4", "#378ADD", "#1D9E75", "#E24B4A", "#EF9F27"];
    } else {
      labels = ["CFO", "CFI", "CFF", "Дивид."];
      data = [v("cfo", y), v("cfi", y), v("cff", y), -(v("dividendsPaid", y) || 0)];
      colors = ["#1D9E75", "#378ADD", "#EF9F27", "#E24B4A"];
    }

    const dataAbs = data.map(v => Math.abs(v || 0));
    const dataSigned = data;

    barChart = new Chart(barCanvas.value, {
      type: "bar",
      data: {
        labels,
        datasets: [{
          data: dataAbs,
          backgroundColor: colors,
          borderRadius: 4,
          barThickness: 12,
        }],
      },
      options: {
        indexAxis: "y",
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          legend: { display: false },
          tooltip: {
            callbacks: {
              label: (c: any) => {
                const orig = dataSigned[c.dataIndex] || 0;
                const sign = orig < 0 ? "-" : "";
                return sign + fmtCompact(Math.abs(orig), props.unit);
              },
            },
          },
        },
        scales: {
          x: { display: false },
          y: { grid: { display: false }, ticks: { font: { size: 9 }, color: "#64748B" } },
        },
        animation: { duration: 500 },
      },
    });
  }

  // Line chart — multi-year trend
  if (lineCanvas.value) {
    function arrFor(field: string): Array<number | null> {
      return yearsAvailable.value.map(y => v(field, y));
    }
    let datasets: any[];
    if (activeTab.value === "pnl") {
      datasets = [
        { label: "Выручка",   data: arrFor("revenue"), borderColor: "#7F77DD" },
        { label: "Чист.пр.",  data: arrFor("profit"),  borderColor: "#1D9E75" },
        { label: "EBITDA",    data: arrFor("ebitda"),  borderColor: "#EF9F27" },
      ];
    } else if (activeTab.value === "sofp") {
      datasets = [
        { label: "Активы",    data: arrFor("totalAssets"), borderColor: "#378ADD" },
        { label: "Капитал",   data: arrFor("equity"),      borderColor: "#1D9E75" },
        { label: "Долг",      data: arrFor("debt"),        borderColor: "#E24B4A" },
      ];
    } else {
      datasets = [
        { label: "CFO", data: arrFor("cfo"), borderColor: "#1D9E75" },
        { label: "CFI", data: arrFor("cfi"), borderColor: "#378ADD" },
        { label: "CFF", data: arrFor("cff"), borderColor: "#EF9F27" },
      ];
    }
    datasets.forEach(d => {
      d.fill = false; d.borderWidth = 2; d.tension = 0.3;
      d.pointRadius = 3; d.pointBackgroundColor = d.borderColor;
    });

    lineChart = new Chart(lineCanvas.value, {
      type: "line",
      data: { labels: yearsAvailable.value, datasets },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          legend: {
            position: "bottom",
            labels: { boxWidth: 8, font: { size: 9 }, padding: 6, usePointStyle: true },
          },
          tooltip: { mode: "index", intersect: false },
        },
        scales: {
          x: { grid: { display: false }, ticks: { font: { size: 9 } } },
          y: {
            grid: { color: "rgba(0,0,0,.04)" },
            ticks: {
              font: { size: 8 },
              callback: (val: any) => fmtCompact(val, props.unit),
            },
          },
        },
        animation: { duration: 600 },
      },
    });
  }
}

// ─── Lifecycle ───────────────────────────────────────────────────────────
function onKeydown(e: KeyboardEvent) {
  if (e.key === "Escape") emit("close");
}

onMounted(() => {
  document.addEventListener("keydown", onKeydown);
  document.body.style.overflow = "hidden";
  renderCharts();
});

onBeforeUnmount(() => {
  document.removeEventListener("keydown", onKeydown);
  document.body.style.overflow = "";
  destroyCharts();
});

watch(activeTab, () => {
  renderCharts();
});

function onBackdropClick(e: MouseEvent) {
  if (e.target === e.currentTarget) emit("close");
}

const stdLabel = computed(() => props.standard === "IFRS" ? "МСФО" : "НСБУ");
const unitLabel = computed(() => `${props.unit === "bln" ? "млрд" : "млн"} ${props.currency}`);
</script>

<template>
  <div class="cfc-overlay" @click="onBackdropClick">
    <div class="cfc-box" v-if="item">
      <!-- Header -->
      <div class="cfc-hdr">
        <div class="cfc-sec-dot" :style="{ background: sectorClr }" />
        <div class="cfc-title-block">
          <div class="cfc-title">{{ item.company_name }}</div>
          <div class="cfc-subtitle">
            {{ stdLabel }} · {{ yearMin }}–{{ yearMax }} · {{ unitLabel }}
          </div>
        </div>
        <button class="cfc-close" @click="emit('close')" aria-label="Закрыть">×</button>
      </div>

      <!-- Tab bar -->
      <div class="cfc-tabs">
        <button v-for="t in TABS"
                :key="t.id"
                class="cfc-tab"
                :class="{ on: activeTab === t.id }"
                @click="activeTab = t.id">
          {{ t.label }}
        </button>
      </div>

      <!-- Body -->
      <div class="cfc-body">
        <!-- KPI cards -->
        <div class="cfc-kpi-grid">
          <div v-for="(k, i) in kpis"
               :key="i"
               class="cfc-kpi">
            <div class="cfc-kpi-lbl">{{ k.label }}</div>
            <div class="cfc-kpi-val" :style="{ color: k.color || 'var(--t1, #1E2A4A)' }">
              {{ k.value }}
            </div>
          </div>
        </div>

        <!-- Charts row -->
        <div class="cfc-charts">
          <div class="cfc-chart-card">
            <div class="cfc-chart-lbl">
              {{ activeTab === 'pnl' ? 'P&L структура' : activeTab === 'sofp' ? 'Баланс' : 'Денежные потоки' }} {{ kpiYear }}
            </div>
            <div class="cfc-canvas-wrap">
              <canvas ref="barCanvas" />
            </div>
          </div>
          <div class="cfc-chart-card">
            <div class="cfc-chart-lbl">Тренд {{ yearMin }}–{{ yearMax }}</div>
            <div class="cfc-canvas-wrap">
              <canvas ref="lineCanvas" />
            </div>
          </div>
        </div>

        <!-- Detailed table -->
        <div class="cfc-tbl-wrap">
          <div v-if="!hasAnyData" class="cfc-empty">
            Нет данных {{ stdLabel }} по этому разделу
          </div>
          <table v-else class="cfc-tbl">
            <thead>
              <tr>
                <th class="cfc-th-l">Показатель</th>
                <th v-for="y in yearsAvailable" :key="y" class="cfc-th-r">{{ y }}</th>
              </tr>
            </thead>
            <tbody>
              <template v-for="(r, i) in tableRows" :key="i">
                <!-- Section header (clickable, collapsible) -->
                <tr v-if="r.section"
                    class="cfc-row-sect"
                    @click="r.groupId && toggleGroup(r.groupId)">
                  <td :colspan="yearsAvailable.length + 1">
                    <span class="cfc-chv"
                          :class="{ open: r.groupId && !collapsedGroups.has(r.groupId) }">▶</span>
                    {{ r.label }}
                  </td>
                </tr>
                <!-- Major row -->
                <tr v-else-if="r.major" class="cfc-row-major">
                  <td class="cfc-cell-l-major">{{ r.label }}</td>
                  <td v-for="y in yearsAvailable"
                      :key="y"
                      class="cfc-cell-r-major"
                      :style="{ color: ((v(r.field!, y) ?? 0) < 0) ? '#E24B4A' : '#1E2A4A' }">
                    {{ fmt(v(r.field!, y)) }}
                  </td>
                </tr>
                <!-- Sub row (only visible when group is open) -->
                <tr v-else-if="r.sub && rowVisible(r)"
                    class="cfc-row-sub"
                    :class="{ nested: r.nested }">
                  <td :class="r.nested ? 'cfc-cell-l-nested' : 'cfc-cell-l-sub'">{{ r.label }}</td>
                  <td v-for="y in yearsAvailable"
                      :key="y"
                      :class="r.nested ? 'cfc-cell-r-nested' : 'cfc-cell-r-sub'"
                      :style="{ color: ((v(r.field!, y) ?? 0) < 0) ? '#E24B4A' : (r.nested ? '#64748B' : '#334155') }">
                    {{ fmt(v(r.field!, y)) }}
                  </td>
                </tr>
              </template>
            </tbody>
          </table>
        </div>
      </div>
    </div>

    <!-- "no item" fallback -->
    <div v-if="!item" class="cfc-box-empty">
      <button class="cfc-close" @click="emit('close')">×</button>
      <div style="padding: 40px; text-align: center; color: var(--t3, #64748B);">
        Нет данных по этой компании
      </div>
    </div>
  </div>
</template>

<style scoped>
.cfc-overlay {
  position: fixed;
  inset: 0;
  background: rgba(15, 18, 40, 0.45);
  backdrop-filter: blur(8px);
  -webkit-backdrop-filter: blur(8px);
  z-index: 10000;
  display: flex;
  align-items: center;
  justify-content: center;
  animation: cfcFadeIn 0.18s ease;
}

@keyframes cfcFadeIn {
  from { opacity: 0; }
  to   { opacity: 1; }
}
@keyframes cfcModalIn {
  from { opacity: 0; transform: translateY(8px) scale(.97); }
  to   { opacity: 1; transform: translateY(0) scale(1); }
}

.cfc-box,
.cfc-box-empty {
  background: var(--bg1, #fff);
  border-radius: 16px;
  width: min(820px, 94vw);
  max-height: 90vh;
  display: flex;
  flex-direction: column;
  box-shadow: 0 24px 64px rgba(15, 23, 60, 0.18), 0 8px 24px rgba(15, 23, 60, 0.08);
  animation: cfcModalIn 0.28s var(--ease-standard) both;
  position: relative;
}

/* Header */
.cfc-hdr {
  padding: 14px 20px;
  border-bottom: 1px solid var(--border-input);
  display: flex;
  align-items: center;
  gap: 12px;
  flex-shrink: 0;
}
.cfc-sec-dot {
  width: 4px; height: 28px; border-radius: 3px;
  flex-shrink: 0;
}
.cfc-title-block { flex: 1; min-width: 0; }
.cfc-title {
  font-size: 16px; font-weight: 600; color: var(--t1, #1E2A4A);
  letter-spacing: -0.005em;
}
.cfc-subtitle {
  font-size: 11px; color: var(--t3, #94A3B8);
  margin-top: 2px;
}
.cfc-close {
  width: 28px; height: 28px;
  border-radius: 8px; border: none;
  background: #F1F5F9; cursor: pointer;
  font-size: 14px; color: var(--t3, var(--t3));
  font-family: inherit;
  display: flex; align-items: center; justify-content: center;
  transition: background 0.12s;
}
.cfc-close:hover { background: var(--border-input); }

/* Tab bar */
.cfc-tabs {
  padding: 10px 20px;
  display: flex; gap: 6px;
  border-bottom: 1px solid #F1F5F9;
  flex-shrink: 0;
}
.cfc-tab {
  font-size: 11px; padding: 5px 14px;
  border-radius: 6px; border: none;
  cursor: pointer; font-weight: 500;
  font-family: inherit;
  background: #F1F5F9; color: var(--t3, var(--t3));
  transition: all 0.15s;
}
.cfc-tab:hover {
  background: rgba(127, 119, 221, 0.08);
  color: var(--t1, #1E2A4A);
}
.cfc-tab.on {
  background: #7F77DD; color: #fff;
  box-shadow: 0 2px 6px rgba(127, 119, 221, 0.25);
}

/* Body */
.cfc-body {
  padding: 14px 20px 18px;
  overflow-y: auto;
  flex: 1;
}

/* KPI cards */
.cfc-kpi-grid {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 6px;
  margin-bottom: 12px;
}
.cfc-kpi {
  padding: 7px 10px;
  background: var(--bg2, #F8FAFC);
  border-radius: 8px;
}
.cfc-kpi-lbl {
  font-size: 8px; color: var(--t3, #94A3B8);
  text-transform: uppercase;
  letter-spacing: 0.04em;
  font-weight: 500;
}
.cfc-kpi-val {
  font-size: 15px; font-weight: 600;
  font-variant-numeric: tabular-nums;
  margin-top: 2px;
  letter-spacing: -0.01em;
}

/* Charts */
.cfc-charts {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 10px;
  margin-bottom: 12px;
}
.cfc-chart-card {
  background: var(--bg2, #F8FAFC);
  border-radius: 10px;
  padding: 10px;
  height: 180px;
  display: flex;
  flex-direction: column;
}
.cfc-chart-lbl {
  font-size: 9px; font-weight: 600;
  color: var(--t3, #94A3B8);
  text-transform: uppercase;
  letter-spacing: 0.04em;
  margin-bottom: 4px;
}
.cfc-canvas-wrap {
  position: relative;
  flex: 1;
  min-height: 0;
}
.cfc-canvas-wrap canvas {
  max-width: 100% !important;
  max-height: 100% !important;
}

/* Table */
.cfc-tbl-wrap { margin-top: 4px; }
.cfc-tbl {
  width: 100%;
  border-collapse: collapse;
}
.cfc-tbl thead tr {
  background: #F1F5F9;
  position: sticky; top: 0;
  z-index: 2;
}
.cfc-th-l, .cfc-th-r {
  padding: 5px 8px;
  font-size: 9px;
  font-weight: 600;
  color: var(--t3, #94A3B8);
  text-transform: uppercase;
  letter-spacing: 0.04em;
}
.cfc-th-l { text-align: left; }
.cfc-th-r { text-align: right; width: 72px; font-variant-numeric: tabular-nums; }

.cfc-row-sect {
  background: var(--bg2, #F8FAFC);
  border-top: 1px solid var(--border-input);
  cursor: pointer;
  user-select: none;
  transition: background 0.12s;
}
.cfc-row-sect:hover { background: #F1F5F9; }
.cfc-row-sect td {
  padding: 7px 8px 4px;
  font-weight: 600;
  color: var(--t3, var(--t3));
  font-size: 10px;
  text-transform: uppercase;
  letter-spacing: 0.03em;
}
.cfc-chv {
  display: inline-block;
  font-size: 8px;
  margin-right: 6px;
  transition: transform 0.25s var(--ease-standard);
  color: var(--t3, #94A3B8);
}
.cfc-chv.open { transform: rotate(90deg); }

.cfc-row-major {
  background: #EEEDFE;
  border-top: 1.5px solid #D4D0EC;
  border-bottom: 1.5px solid #D4D0EC;
}
.cfc-cell-l-major {
  padding: 6px 8px;
  font-weight: 700;
  color: var(--t1, #1E2A4A);
  font-size: 12px;
}
.cfc-cell-r-major {
  padding: 6px 8px;
  text-align: right;
  font-weight: 700;
  font-size: 12px;
  font-variant-numeric: tabular-nums;
}

.cfc-row-sub {
  border-bottom: 0.5px solid #F1F5F9;
}
.cfc-cell-l-sub {
  padding: 4px 8px 4px 12px;
  font-weight: 500;
  color: var(--t2, #334155);
  font-size: 11px;
}
.cfc-cell-r-sub {
  padding: 4px 8px;
  text-align: right;
  font-weight: 500;
  font-size: 11px;
  font-variant-numeric: tabular-nums;
}
.cfc-cell-l-nested {
  padding: 3px 8px 3px 24px;
  color: var(--t3, var(--t3));
  font-size: 10.5px;
}
.cfc-cell-r-nested {
  padding: 3px 8px;
  text-align: right;
  font-size: 10.5px;
  font-variant-numeric: tabular-nums;
}

.cfc-empty {
  padding: 30px;
  text-align: center;
  color: var(--t3, #94A3B8);
  font-size: 12px;
}

/* Responsive */
@media (max-width: 720px) {
  .cfc-kpi-grid { grid-template-columns: repeat(2, 1fr); }
  .cfc-charts { grid-template-columns: 1fr; }
  .cfc-chart-card { height: 160px; }
}
</style>
