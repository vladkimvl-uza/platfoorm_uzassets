<script setup lang="ts">
import { ref, computed, onMounted, watch, nextTick, onBeforeUnmount } from "vue";
import { useSavedFilter } from "@/composables/useSavedFilter";
import { useAiPageContext } from "@/composables/useAiPageContext";
import { useNumberTween } from "@/composables/useNumberTween";
import UzaSkeleton from "@/components/UZA/UzaSkeleton.vue";
import { api } from "@/api/client";
import { Chart } from "@/utils/chartjsRegister";

const emit = defineEmits<{ (e: 'toggle-sidebar'): void }>();
import { inject } from 'vue';
const toggleSidebar = inject<() => void>('toggleSidebar', () => {});

// ─── Types ───────────────────────────────────────────────────────
interface KPIs {
  projects: number; tasks: number;
  done_proj: number; done_tasks: number;
  active_proj: number; active_tasks: number;
  overdue_proj: number; overdue_tasks: number;
  deferred_proj: number; deferred_tasks: number;
}
interface StatusRow {
  id: string; label: string; color: string;
  projects_count: number; tasks_count: number;
}
interface CompanyRow {
  code: string; name: string; company_id: string;
  projects_total: number; projects_done: number;
  tasks_total: number; tasks_done: number;
  progress_pct: number;
}
interface SectorGroup {
  sector: string; sector_label: string; sector_color: string;
  companies: CompanyRow[];
}
interface DirRow {
  id: string; label: string; color: string;
  projects_total: number; projects_done: number;
  tasks_total: number; tasks_done: number;
  progress_pct: number;
}
interface RatingValue {
  rating: string | null; score: string | null;
  date: string | null; is_esg: boolean;
}
interface RatingRingRow {
  agency: string; label: string; color: string;
  covered: number; total: number; pct: number;
}
interface RatingTableRow {
  code: string; name: string;
  fitch: RatingValue | null; sp: RatingValue | null;
  moody: RatingValue | null; sf: RatingValue | null;
  sp_esg: RatingValue | null; cdp: RatingValue | null;
}
interface RatingTableSector {
  sector: string; sector_label: string; sector_color: string;
  rows: RatingTableRow[];
}
interface CompletionRow {
  code: string; name: string;
  sector: string; sector_color: string;
  tasks_total: number; tasks_done: number;
  progress_pct: number;
  projects_total: number; projects_done: number;
}
interface CompletionSectorRow {
  sector: string; sector_label: string; sector_color: string;
  tasks_total: number; tasks_done: number; progress_pct: number;
}

interface Payload {
  kpis: KPIs;
  statuses: StatusRow[];
  companies_by_sector: SectorGroup[];
  directions: DirRow[];
  ratings: { rings: RatingRingRow[]; table: RatingTableSector[]; total_companies: number };
  completion: {
    by_company: CompletionRow[];
    by_sector: CompletionSectorRow[];
    portfolio_avg: number;
  };
  available_years: number[];
  selected_year: number | null;
}

// ─── State ───────────────────────────────────────────────────────
const data = ref<Payload | null>(null);
const loading = ref(true);
const errorMsg = ref<string | null>(null);
import { usePortfolioYearStore } from "@/stores/portfolioYear";
import { useCompaniesStore } from "@/stores/companies";
import ExecDashRatings from "@/components/ExecDash/ExecDashRatings.vue";
import ExecDashExecutionChart from "@/components/ExecDash/ExecDashExecutionChart.vue";
import ExecDashDirectionsBlock from "@/components/ExecDash/ExecDashDirectionsBlock.vue";
import KpiTileDrillModal from "@/components/Dashboard/KpiTileDrillModal.vue";
import CompanyTileDrillModal from "@/components/Dashboard/CompanyTileDrillModal.vue";
import CompanyAvatar from "@/components/CompanyAvatar.vue";
import { useExecutiveDashboard } from "@/composables/useExecutiveDashboard";

// ─── Pack 7.45: KPI tile drill-down state ────────────────────────
type KpiDrillBucket = "total" | "done" | "active" | "overdue" | "deferred";
type KpiDrillEntity = "projects" | "tasks";
const kpiDrillOpen = ref(false);
const kpiDrillBucket = ref<KpiDrillBucket>("total");
const kpiDrillEntity = ref<KpiDrillEntity>("tasks");
function openKpiDrill(bucket: KpiDrillBucket, entity: KpiDrillEntity) {
  kpiDrillBucket.value = bucket;
  kpiDrillEntity.value = entity;
  kpiDrillOpen.value = true;
}
function closeKpiDrill() { kpiDrillOpen.value = false; }

// ─── Pack 7.47: Company tile drill-down state ────────────────────
const companyDrillOpen = ref(false);
const companyDrillCode = ref<string>("");
const companyDrillTab = ref<"projects" | "tasks">("projects");
function openCompanyDrill(code: string, tab: "projects" | "tasks" = "projects") {
  if (!code) return;
  companyDrillCode.value = code;
  companyDrillTab.value = tab;
  companyDrillOpen.value = true;
}
function closeCompanyDrill() { companyDrillOpen.value = false; }
import { useRouter } from "vue-router";
const router = useRouter();
function gotoCompanyWorkspace(code: string) {
  if (!code) return;
  router.push({ name: "company-workspace", params: { code } });
}

// Pack 7.13: unified naming via store
const companies = useCompaniesStore();
onMounted(() => { void companies.ensureLoaded(); });
const yearStore = usePortfolioYearStore();
const year = computed(() => yearStore.year);
const statusEntity = useSavedFilter<"projects" | "tasks">("dashboard.statusEntity", "tasks");
const statusFormat = useSavedFilter<"count" | "percent">("dashboard.statusFormat", "count");
const expandedSectors = ref<Set<string>>(new Set());
const completionView = useSavedFilter<"company" | "sector">("dashboard.completionView", "company");
const completionSort = useSavedFilter<"progress" | "alphabetic">("dashboard.completionSort", "progress");

const donutCanvas = ref<HTMLCanvasElement | null>(null);
const completionCanvas = ref<HTMLCanvasElement | null>(null);
const ringCanvases = ref<(HTMLCanvasElement | null)[]>([]);
let donutChart: any = null;
let completionChart: any = null;
const ringCharts: any[] = [];

// ─── Helpers ─────────────────────────────────────────────────────
function pctColor(p: number): string {
  if (p >= 60) return "#1D9E75";
  if (p >= 30) return "#D97706";
  return "#E24B4A";
}

function formatStatusValue(item: StatusRow): string {
  const v = statusEntity.value === "projects" ? item.projects_count : item.tasks_count;
  if (statusFormat.value === "count") return String(v);
  const total = ringStatuses.value.reduce((s, x) =>
    s + (statusEntity.value === "projects" ? x.projects_count : x.tasks_count), 0) || 0;
  return total > 0 ? `${Math.round(v / total * 100)}%` : "0%";
}

const totalCenterValue = computed(() => {
  if (!data.value) return 0;
  return ringStatuses.value.reduce((s, x) =>
    s + (statusEntity.value === "projects" ? x.projects_count : x.tasks_count), 0);
});

const completionDataSorted = computed(() => {
  if (!data.value) return [];
  if (completionView.value === "sector") {
    const arr = [...data.value.completion.by_sector];
    if (completionSort.value === "alphabetic") arr.sort((a, b) => a.sector_label.localeCompare(b.sector_label, "ru"));
    else arr.sort((a, b) => b.progress_pct - a.progress_pct);
    return arr.map(s => ({
      label: s.sector_label, value: s.progress_pct,
      color: s.sector_color, sub: `${s.tasks_done}/${s.tasks_total}`,
    }));
  }
  const arr = [...data.value.completion.by_company];
  if (completionSort.value === "alphabetic") arr.sort((a, b) => a.name.localeCompare(b.name, "ru"));
  else arr.sort((a, b) => b.progress_pct - a.progress_pct);
  return arr.map(c => ({
    label: c.name, value: c.progress_pct,
    color: pctColor(c.progress_pct), sub: `${c.tasks_done}/${c.tasks_total}`,
  }));
});

// ─── Charts ──────────────────────────────────────────────────────
const ringStatuses = computed(() => {
  if (!data.value) return [];
  return data.value.statuses.filter(s => s.id !== "overdue");
});
// 2026-05-26: всё рендер-функции теперь UPDATE если chart существует, CREATE
// только в первый раз. Раньше destroy+recreate → анимация всегда начиналась
// с 0 (никогда не transition между старыми и новыми значениями). Теперь
// Chart.js плавно интерполирует от текущих data к новым.
function renderDonut() {
  if (!data.value || !donutCanvas.value) return;
  const labels = ringStatuses.value.map(s => s.label);
  const newData = ringStatuses.value.map(s => statusEntity.value === "projects" ? s.projects_count : s.tasks_count);
  const colors = ringStatuses.value.map(s => s.color);

  if (donutChart) {
    donutChart.data.labels = labels;
    donutChart.data.datasets[0].data = newData;
    donutChart.data.datasets[0].backgroundColor = colors;
    donutChart.update();
    return;
  }
  donutChart = new Chart(donutCanvas.value, {
    type: "doughnut",
    data: {
      labels,
      datasets: [{
        data: newData,
        backgroundColor: colors,
        borderColor: "rgba(255, 255, 255, 0.92)", borderWidth: 3, hoverOffset: 8, borderRadius: 6,
      }],
    },
    options: {
      cutout: '84%', responsive: false,
      animation: { animateRotate: true, duration: 900, easing: "easeOutCubic" },
      animations: { numbers: { duration: 900, easing: "easeOutCubic" } },
      plugins: {
        legend: { display: false },
        tooltip: {
          backgroundColor: "rgba(15,23,60,.95)",
          padding: 8, cornerRadius: 6,
          titleFont: { size: 11 }, bodyFont: { size: 11, weight: 600 },
        },
      },
    },
  });
}

function renderRings() {
  if (!data.value) return;
  data.value.ratings.rings.forEach((ring, i) => {
    const cv = ringCanvases.value[i];
    if (!cv) return;
    const existing = ringCharts[i];
    if (existing) {
      existing.data.datasets[0].data = [ring.pct, 100 - ring.pct];
      existing.data.datasets[0].backgroundColor = [ring.color, "#E2E8F0"];
      existing.update();
      return;
    }
    const chart = new Chart(cv, {
      type: "doughnut",
      data: {
        labels: ["Покрыто", "Без рейтинга"],
        datasets: [{
          data: [ring.pct, 100 - ring.pct],
          backgroundColor: [ring.color, "#E2E8F0"],
          borderWidth: 0,
        }],
      },
      options: {
        cutout: '84%', responsive: false,
        animation: { animateRotate: true, duration: 900, easing: "easeOutCubic" },
        animations: { numbers: { duration: 900, easing: "easeOutCubic" } },
        plugins: { legend: { display: false }, tooltip: { enabled: false } },
      },
    });
    ringCharts[i] = chart;
  });
  // Trim excess (if data.value.ratings.rings shrank)
  if (ringCharts.length > data.value.ratings.rings.length) {
    for (let i = data.value.ratings.rings.length; i < ringCharts.length; i++) {
      ringCharts[i]?.destroy();
    }
    ringCharts.length = data.value.ratings.rings.length;
  }
}

function renderCompletion() {
  if (!data.value || !completionCanvas.value) return;
  if (completionChart) { completionChart.destroy(); completionChart = null; }
  const items = completionDataSorted.value;
  if (!items.length) return;

  // ==== Phase 3: enriched bar chart ====
  // Per-bar conditional color: ≥60 green, 30-60 amber, <30 red
  const barColor = (pct: number) => pct >= 60 ? "#1D9E75" : pct >= 30 ? "#EF9F27" : "#E24B4A";
  const colors = items.map((i: any) => barColor(i.value));
  const avg = items.length ? Math.round(items.reduce((s: number, i: any) => s + i.value, 0) / items.length) : 0;

  // Top-3 medals (gold/silver/bronze)
  const medalsPlugin = {
    id: "topMedals",
    afterDatasetsDraw(chart: any) {
      const ctx = chart.ctx;
      const meta = chart.getDatasetMeta(0);
      const ranked = items
        .map((it: any, idx: number) => ({ idx, value: it.value }))
        .sort((a: any, b: any) => b.value - a.value)
        .slice(0, 3);
      const medalColors = ["#EAB308", "#94A3B8", "#B45309"];
      ranked.forEach((entry: any, rank: number) => {
        const bar = meta.data[entry.idx];
        if (!bar) return;
        const x = bar.x;
        const y = bar.y - 18;
        ctx.save();
        ctx.beginPath();
        ctx.arc(x, y, 9, 0, Math.PI * 2);
        ctx.fillStyle = medalColors[rank];
        ctx.fill();
        ctx.fillStyle = "#FFFFFF";
        ctx.font = "bold 10px Inter, system-ui";
        ctx.textAlign = "center";
        ctx.textBaseline = "middle";
        ctx.fillText(String(rank + 1), x, y);
        ctx.restore();
      });
    },
  };

  // Avg dashed horizontal line with label
  const avgPlugin = {
    id: "avgLine",
    afterDatasetsDraw(chart: any) {
      const ctx = chart.ctx;
      const yPos = chart.scales.y.getPixelForValue(avg);
      const area = chart.chartArea;
      ctx.save();
      ctx.setLineDash([4, 4]);
      ctx.strokeStyle = "rgba(15,23,60,.35)";
      ctx.lineWidth = 1;
      ctx.beginPath();
      ctx.moveTo(area.left, yPos);
      ctx.lineTo(area.right, yPos);
      ctx.stroke();
      ctx.setLineDash([]);
      ctx.fillStyle = "rgba(15,23,60,.7)";
      ctx.font = "600 10px Inter, system-ui";
      ctx.textAlign = "right";
      ctx.fillText("Ср. " + avg + "%", area.right - 4, yPos - 6);
      ctx.restore();
    },
  };

  // Value labels (% over each bar)
  const labelsPlugin = {
    id: "valueLabels",
    afterDatasetsDraw(chart: any) {
      const ctx = chart.ctx;
      const meta = chart.getDatasetMeta(0);
      meta.data.forEach((bar: any, idx: number) => {
        const v = items[idx].value;
        ctx.save();
        ctx.fillStyle = barColor(v);
        ctx.font = "700 10.5px Inter, system-ui";
        ctx.textAlign = "center";
        ctx.fillText(v + "%", bar.x, bar.y - 32);
        ctx.restore();
      });
    },
  };

  // 2026-05-26: bar chart использует custom plugins с closure на `items` /
  // `avg` / `barColor`. Chart.update() не пересоздаёт plugin closures →
  // medals/avg-line/value-labels останутся на старых значениях. Оставляем
  // destroy+recreate, но с улучшенными durations (900ms easeOutCubic) для
  // плавности pour-in анимации от 0.
  completionChart = new Chart(completionCanvas.value, {
    type: "bar",
    data: {
      labels: items.map((i: any) => i.label),
      datasets: [{
        data: items.map((i: any) => i.value),
        backgroundColor: colors,
        borderRadius: 4,
        barThickness: completionView.value === "sector" ? 36 : 22,
      }],
    },
    plugins: [medalsPlugin, avgPlugin, labelsPlugin],
    options: {
      responsive: false,
      maintainAspectRatio: false,
      animation: { duration: 900, easing: "easeOutCubic" },
      animations: {
        y: { duration: 900, easing: "easeOutCubic" },
        numbers: { duration: 900, easing: "easeOutCubic" },
      },
      layout: { padding: { top: 36, right: 18, left: 8, bottom: 8 } },
      plugins: {
        legend: { display: false },
        tooltip: {
          backgroundColor: "rgba(15,23,60,.95)",
          padding: 10, cornerRadius: 6,
          callbacks: {
            label(ctx: any) {
              const item = items[ctx.dataIndex];
              return " " + item.value + "% • " + (item.sub || "");
            },
          },
        },
      },
      scales: {
        x: {
          ticks: {
            font: { size: 10 },
            color: "#475569",
            maxRotation: 60,
            minRotation: 45,
            autoSkip: false,
          },
          grid: { display: false },
        },
        y: {
          beginAtZero: true,
          max: 100,
          ticks: {
            font: { size: 10 },
            color: "#94a3b8",
            stepSize: 25,
            callback: (v: any) => v + "%",
          },
          grid: { color: "rgba(15,23,60,.05)" },
        },
      },
    },
  });
}

const kpiTotal = computed(() => {
  if (!data.value) return { proj: 0, tasks: 0 };
  return { proj: data.value.kpis.projects, tasks: data.value.kpis.tasks };
});

function fmtKpi(value: number, total: number): string {
  if (statusFormat.value === "percent") {
    if (total <= 0) return "0%";
    return Math.round(value / total * 100) + "%";
  }
  return String(value);
}
watch([data, statusEntity, statusFormat], () => { nextTick(renderDonut); }, { deep: false });
watch(data, () => { nextTick(renderRings); }, { deep: false });
watch([data, completionView, completionSort], () => { nextTick(renderCompletion); }, { deep: false });

// ─── Load ────────────────────────────────────────────────────────
async function load() {
  loading.value = true;
  errorMsg.value = null;
  try {
    const params: Record<string, any> = {};
    if (year.value) params.year = year.value;
    if (sectorFilter.value) params.sector_code = sectorFilter.value;
    if (directionFilter.value) params.direction_code = directionFilter.value;
    if (companyFilter.value) params.company_code = companyFilter.value;
    const res = await api.get<Payload>("/dashboard/shareholder", { params });
    data.value = res.data;
    if (res.data?.available_years?.length) {
      yearStore.setAvailableYears(res.data.available_years);
    }
  } catch (e: any) {
    errorMsg.value = e?.response?.data?.detail || e?.message || "Ошибка загрузки";
    data.value = null;
  } finally {
    loading.value = false;
  }
}

function toggleSector(sec: string) {
  if (expandedSectors.value.has(sec)) expandedSectors.value.delete(sec);
  else expandedSectors.value.add(sec);
  expandedSectors.value = new Set(expandedSectors.value);
}

function ratingBadgeColor(r: RatingValue | null): { bg: string; fg: string } {
  if (!r || !r.rating) return { bg: "transparent", fg: "#94a3b8" };
  const rating = r.rating.toUpperCase();
  if (/^(AAA|AA\+|AA|AA-|A\+|A|A-)$/.test(rating)) return { bg: "#DCFCE7", fg: "#0E7A58" };
  if (/^(BBB\+|BBB|BBB-)$/.test(rating)) return { bg: "#FEF9C3", fg: "#9A7B00" };
  if (/^(BB\+|BB|BB-)$/.test(rating)) return { bg: "#FFEEDC", fg: "#A65A00" };
  if (/^(B\+|B|B-)$/.test(rating)) return { bg: "#FFE4E4", fg: "#993D3D" };
  return { bg: "#F1F5F9", fg: "#64748B" };
}

// === Phase 1: dropdown filters (frontend-only) ===
const sectorFilter = useSavedFilter<string>("dashboard.sectorFilter", "");
const directionFilter = useSavedFilter<string>("dashboard.directionFilter", "");
const companyFilter = useSavedFilter<string>("dashboard.companyFilter", "");
const aiQuery = ref<string>("");

// Pack 7.9e: AI Bubble context
useAiPageContext({
  key: "dashboard",
  label: "Главный дашборд",
  describeState: () => {
    const parts: string[] = [];
    if (sectorFilter.value) parts.push(`сектор: ${sectorFilter.value}`);
    if (companyFilter.value) parts.push(`компания: ${companyFilter.value}`);
    parts.push(`показано: ${statusEntity.value === "tasks" ? "задачи" : "проекты"}`);
    parts.push(`формат: ${statusFormat.value}`);
    return parts.join("; ");
  },
  quickActions: [
    { label: "Сводка дашборда", icon: "📊",
      prompt: "Дай сводку главного дашборда: статусы проектов/задач по компаниям и секторам. Что выделяется. Используй get_kpi_summary." },
    { label: "Топ-5 отстающих", icon: "⚠️",
      prompt: "Найди топ-5 отстающих компаний по выполнению задач за текущий год. Используй get_kpi_summary.top_overdue_companies + конкретные рекомендации." },
    { label: "Что просрочено?", icon: "🔴",
      prompt: "Покажи все критичные просрочки задач на сегодня. Используй list_overdue_tasks." },
  ],
});

const allCompaniesList = computed(() => {
  if (!data.value) return [];
  const out: { code: string; name: string }[] = [];
  for (const grp of data.value.companies_by_sector) {
    for (const co of grp.companies) {
      out.push({ code: co.code, name: co.name });
    }
  }
  return out.sort((a, b) => a.name.localeCompare(b.name, "ru"));
});

const hasFilters = computed(
  () => sectorFilter.value !== "" || directionFilter.value !== "" || companyFilter.value !== ""
);

const filteredData = computed(() => {
  if (!data.value) return null;
  const d = data.value;
  let coBySec = d.companies_by_sector;
  if (sectorFilter.value) {
    coBySec = coBySec.filter((g) => g.sector === sectorFilter.value);
  }
  if (companyFilter.value) {
    coBySec = coBySec.map((g) => ({
      ...g,
      companies: g.companies.filter((c) => c.code === companyFilter.value),
    })).filter((g) => g.companies.length > 0);
  }
  let dirs = d.directions;
  if (directionFilter.value) {
    dirs = dirs.filter((dr) => dr.id === directionFilter.value);
  }
  return { ...d, companies_by_sector: coBySec, directions: dirs };
});
function clearFilters() {
  sectorFilter.value = "";
  directionFilter.value = "";
  companyFilter.value = "";
}


// Pack 7.44: ExecDashRatings/ExecDashExecutionChart/ExecDashDirectionsBlock
// используют useExecutiveDashboard composable. Синхронизируем его year с dashboard year.
const exec = useExecutiveDashboard();
// Sync year + sector filter с useExecutiveDashboard
watch([() => yearStore.year, sectorFilter], ([y, sec]) => {
  if (y) {
    exec.setYear(y);
    exec.setSectors(sec ? [sec] : []);
    exec.loadData();
  }
}, { immediate: true });
watch([year, sectorFilter, directionFilter, companyFilter], load);

// Dynamic max for horizontal progress bars (companies / directions)
const maxCompanyPct = computed(() => {
  const list: any[] = (allCompaniesList.value as any[]) || [];
  if (!list.length) return 100;
  const m = Math.max(...list.map((c: any) => Number(c.progress_pct) || 0), 1);
  return m;
});
const maxDirectionPct = computed(() => {
  const list: any[] = (data.value?.directions as any[]) || [];
  if (!list.length) return 100;
  const m = Math.max(...list.map((d: any) => Number(d.progress_pct) || 0), 1);
  return m;
});
onMounted(load);
onBeforeUnmount(() => {
  if (donutChart) donutChart.destroy();
  if (completionChart) completionChart.destroy();
  ringCharts.forEach(c => c?.destroy());
});

// Pack 7.44 — count-up эффект для KPI цифр
const tweenedProjects = useNumberTween(
  () => Number(data.value?.kpis?.projects) || 0,
  { duration: 900 }
);
const tweenedTasks = useNumberTween(
  () => Number(data.value?.kpis?.tasks) || 0,
  { duration: 900 }
);
const tweenedDoneProj = useNumberTween(
  () => Number(data.value?.kpis?.done_proj) || 0,
  { duration: 900 }
);
const tweenedDoneTasks = useNumberTween(
  () => Number(data.value?.kpis?.done_tasks) || 0,
  { duration: 900 }
);
const tweenedActiveProj = useNumberTween(
  () => Number(data.value?.kpis?.active_proj) || 0,
  { duration: 900 }
);
const tweenedActiveTasks = useNumberTween(
  () => Number(data.value?.kpis?.active_tasks) || 0,
  { duration: 900 }
);
const tweenedOverdueProj = useNumberTween(
  () => Number(data.value?.kpis?.overdue_proj) || 0,
  { duration: 900 }
);
const tweenedOverdueTasks = useNumberTween(
  () => Number(data.value?.kpis?.overdue_tasks) || 0,
  { duration: 900 }
);
const tweenedDeferredProj = useNumberTween(
  () => Number(data.value?.kpis?.deferred_proj) || 0,
  { duration: 900 }
);
const tweenedDeferredTasks = useNumberTween(
  () => Number(data.value?.kpis?.deferred_tasks) || 0,
  { duration: 900 }
);
</script>

<template>
  <div class="sh-page">
    <!-- Phase 1: page-specific filters (rendered into AppTopbar via Teleport) -->
    <Teleport to="#page-filters-target" v-if="data">
      <select v-model="companyFilter" class="apt-page-select">
        <option value="">Все компании</option>
        <option v-for="c in allCompaniesList" :key="c.code" :value="c.code">{{ companies.getCompanyName(c.code) || c.name }}</option>
      </select>
      <select v-model="sectorFilter" class="apt-page-select">
        <option value="">Все секторы</option>
        <option value="mining_metallurgy">Горно-металлургический сектор</option>
        <option value="oil_gas">Нефть и газ</option>
        <option value="energy">Энергетика</option>
        <option value="transport_communications">Транспорт и коммуникации</option>
        <option value="other">Другой сектор</option>
      </select>
      <select v-model="directionFilter" class="apt-page-select">
        <option value="">Все направления</option>
        <option v-for="d in (data?.directions || [])" :key="d.id" :value="d.id">{{ d.label }}</option>
      </select>
      <button v-if="hasFilters" @click="clearFilters" title="Сбросить" class="apt-page-reset">×</button>
    </Teleport>

    <div v-if="loading && !data" class="sh-skel-stack">
      <UzaSkeleton variant="kpi" :cols="5" :stagger="70" />
      <div class="sh-skel-row-2">
        <UzaSkeleton variant="block" width="100%" height="280px" />
        <UzaSkeleton variant="block" width="100%" height="280px" />
      </div>
      <UzaSkeleton variant="block" width="100%" height="360px" />
    </div>
    <div v-else-if="errorMsg" class="state-msg error">⚠ {{ errorMsg }}</div>

    <template v-else-if="data">
      <!-- ═══ 6 KPI cards ═══ -->
      <div class="kpi-strip">
        <div class="kpi2 fin-shimmer kpi2-clickable"
             style="--kpi2-accent: #7F77DD; animation-delay: 0ms"
             @click="openKpiDrill('total','projects')">
          <div class="kpi2-lbl">ПРОЕКТОВ</div>
          <div class="kpi2-val">{{ fmtKpi(Math.round(tweenedProjects), kpiTotal.proj) }}</div>
        </div>
        <div class="kpi2 fin-shimmer kpi2-clickable"
             style="--kpi2-accent: #3B82F6; animation-delay: 80ms"
             @click="openKpiDrill('total','tasks')">
          <div class="kpi2-lbl">ВСЕГО ЗАДАЧ</div>
          <div class="kpi2-val">{{ fmtKpi(Math.round(tweenedTasks), kpiTotal.tasks) }}</div>
        </div>
        <div class="kpi2 fin-shimmer kpi2-clickable"
             style="--kpi2-accent: #1D9E75; animation-delay: 160ms"
             @click="openKpiDrill('done','tasks')">
          <div class="kpi2-lbl">ЗАВЕРШЕНО</div>
          <div class="kpi2-split">
            <div class="kpi2-half" @click.stop="openKpiDrill('done','projects')"><div class="kpi2-num" style="color:#1D9E75">{{ fmtKpi(Math.round(tweenedDoneProj), kpiTotal.proj) }}</div><div class="kpi2-sub">проектов</div></div>
            <div class="kpi2-divider"></div>
            <div class="kpi2-half" @click.stop="openKpiDrill('done','tasks')"><div class="kpi2-num" style="color:#1D9E75">{{ fmtKpi(Math.round(tweenedDoneTasks), kpiTotal.tasks) }}</div><div class="kpi2-sub">задач</div></div>
          </div>
        </div>
        <div class="kpi2 fin-shimmer kpi2-clickable"
             style="--kpi2-accent: #D97706; animation-delay: 240ms"
             @click="openKpiDrill('active','tasks')">
          <div class="kpi2-lbl">В ПРОЦЕССЕ</div>
          <div class="kpi2-split">
            <div class="kpi2-half" @click.stop="openKpiDrill('active','projects')"><div class="kpi2-num" style="color:#D97706">{{ fmtKpi(Math.round(tweenedActiveProj), kpiTotal.proj) }}</div><div class="kpi2-sub">проектов</div></div>
            <div class="kpi2-divider"></div>
            <div class="kpi2-half" @click.stop="openKpiDrill('active','tasks')"><div class="kpi2-num" style="color:#D97706">{{ fmtKpi(Math.round(tweenedActiveTasks), kpiTotal.tasks) }}</div><div class="kpi2-sub">задач</div></div>
          </div>
        </div>
        <div :class="['kpi2','fin-shimmer',{dim: data.kpis.overdue_proj+data.kpis.overdue_tasks===0, 'kpi2-clickable': data.kpis.overdue_proj+data.kpis.overdue_tasks>0}]"
             :style="`--kpi2-accent:${data.kpis.overdue_proj+data.kpis.overdue_tasks>0?'#EF4444':'#e2e8f0'};animation-delay:320ms`"
             @click="data.kpis.overdue_tasks>0 ? openKpiDrill('overdue','tasks') : (data.kpis.overdue_proj>0 && openKpiDrill('overdue','projects'))">
          <div class="kpi2-lbl">ПРОСРОЧЕНО</div>
          <div class="kpi2-split">
            <div class="kpi2-half" @click.stop="data.kpis.overdue_proj>0 && openKpiDrill('overdue','projects')"><div class="kpi2-num" :style="{color: data.kpis.overdue_proj>0?'#EF4444':'#94a3b8'}">{{ fmtKpi(Math.round(tweenedOverdueProj), kpiTotal.proj) }}</div><div class="kpi2-sub">проектов</div></div>
            <div class="kpi2-divider"></div>
            <div class="kpi2-half" @click.stop="data.kpis.overdue_tasks>0 && openKpiDrill('overdue','tasks')"><div class="kpi2-num" :style="{color: data.kpis.overdue_tasks>0?'#EF4444':'#94a3b8'}">{{ fmtKpi(Math.round(tweenedOverdueTasks), kpiTotal.tasks) }}</div><div class="kpi2-sub">задач</div></div>
          </div>
        </div>
        <div :class="['kpi2','fin-shimmer',{dim: data.kpis.deferred_proj+data.kpis.deferred_tasks===0, 'kpi2-clickable': data.kpis.deferred_proj+data.kpis.deferred_tasks>0}]"
             :style="`--kpi2-accent:${data.kpis.deferred_proj+data.kpis.deferred_tasks>0?'#7F77DD':'#e2e8f0'};animation-delay:400ms;${data.kpis.deferred_proj+data.kpis.deferred_tasks>0?'background:linear-gradient(180deg,#FFF 0%,#FCFAFF 100%);':''}`"
             @click="data.kpis.deferred_tasks>0 ? openKpiDrill('deferred','tasks') : (data.kpis.deferred_proj>0 && openKpiDrill('deferred','projects'))">
          <div class="kpi2-lbl">ПЕРЕНЕСЕНО</div>
          <div class="kpi2-split">
            <div class="kpi2-half" @click.stop="data.kpis.deferred_proj>0 && openKpiDrill('deferred','projects')"><div class="kpi2-num" :style="{color: data.kpis.deferred_proj>0?'#7F77DD':'#94a3b8'}">{{ fmtKpi(Math.round(tweenedDeferredProj), kpiTotal.proj) }}</div><div class="kpi2-sub">проектов</div></div>
            <div class="kpi2-divider"></div>
            <div class="kpi2-half" @click.stop="data.kpis.deferred_tasks>0 && openKpiDrill('deferred','tasks')"><div class="kpi2-num" :style="{color: data.kpis.deferred_tasks>0?'#7F77DD':'#94a3b8'}">{{ fmtKpi(Math.round(tweenedDeferredTasks), kpiTotal.tasks) }}</div><div class="kpi2-sub">задач</div></div>
          </div>
        </div>
      </div>

      <!-- ═══ Pack 7.46: KPI tile drill-down modal (DirectionDrill-style) ═══ -->
      <KpiTileDrillModal
        v-if="kpiDrillOpen && data"
        :bucket="kpiDrillBucket"
        :initial-entity="kpiDrillEntity"
        :year="year"
        :sector-code="sectorFilter || null"
        :direction-code="directionFilter || null"
        @close="closeKpiDrill"
      />

      <!-- ═══ Pack 7.47: Company tile drill-down modal ═══ -->
      <CompanyTileDrillModal
        v-if="companyDrillOpen"
        :company-code="companyDrillCode"
        :year="year"
        :initial-tab="companyDrillTab"
        @close="closeCompanyDrill"
      />

      <!-- ═══ 3-col: Donut | Companies | Directions ═══ -->
      <div class="three-cols">
        <div class="cc">
          <div class="cc-header">
            <div class="cc-title">Статусы</div>
            <div class="seg-controls">
              <div class="seg-ctrl">
                <button :class="['seg-btn',{active:statusEntity==='projects'}]" @click="statusEntity='projects'">Проекты</button>
                <button :class="['seg-btn',{active:statusEntity==='tasks'}]" @click="statusEntity='tasks'">Задачи</button>
              </div>
              <div class="seg-ctrl">
                <button :class="['seg-btn',{active:statusFormat==='count'}]" @click="statusFormat='count'">#</button>
                <button :class="['seg-btn',{active:statusFormat==='percent'}]" @click="statusFormat='percent'">%</button>
              </div>
            </div>
          </div>
          <div class="donut-row">
            <div class="donut-wrap">
              <canvas ref="donutCanvas" width="160" height="160"></canvas>
              <div class="donut-center">
                <div class="donut-num">{{ totalCenterValue }}</div>
                <div class="donut-lbl">{{ statusEntity==='projects'?'ПРОЕКТОВ':'ЗАДАЧ' }}</div>
              </div>
            </div>
            <div class="donut-legend">
              <div v-for="s in data.statuses" :key="s.id" class="legend-row">
                <span class="legend-dot" :style="{background:s.color}"></span>
                <span class="legend-lbl">{{ s.label }}</span>
                <span class="legend-val" :style="{color:s.id==='overdue'?'#E24B4A':'var(--t1)'}">{{ formatStatusValue(s) }}</span>
              </div>
            </div>
          </div>
        </div>

        <div class="cc">
          <div class="cc-header"><div class="cc-title">Проекты по компаниям</div></div>
          <div class="comp-list-head">
            <span>КОМПАНИЯ</span><span>ПРОГРЕСС</span><span class="r">ПРОЕКТЫ</span><span class="r">ЗАДАЧИ</span>
          </div>
          <div class="comp-body">
            <template v-for="grp in (data?.companies_by_sector || [])" :key="grp.sector">
              <div class="sector-header" @click="toggleSector(grp.sector)">
                <span class="sector-pill" :style="{background:grp.sector_color}"></span>
                <span class="sector-name">{{ grp.sector_label }}</span>
                <span class="sector-count">{{ grp.companies.length }}</span>
                <span class="sector-arrow" :class="{open: !expandedSectors.has(grp.sector)}">
                  <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor"
                       stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                    <polyline points="6 9 12 15 18 9"/>
                  </svg>
                </span>
              </div>
              <template v-if="!expandedSectors.has(grp.sector)">
                <div v-for="co in grp.companies" :key="co.code" class="co-row co-row-clickable uza-side-stripe uza-side-stripe-tight"
                     :style="{ '--stripe-color': grp.sector_color }">
                  <div class="co-name" style="display:flex; align-items:center; gap:8px; min-width:0;">
                    <CompanyAvatar :name="co.name || co.code" :color="grp.sector_color" :size="22" />
                    <span class="co-code"
                          :style="{ background: grp.sector_color + '22', color: grp.sector_color, '--cl': grp.sector_color }"
                          @click.stop="openCompanyDrill(co.code, 'projects')"
                          :title="'Открыть drill компании ' + co.name">{{ co.code }}</span>
                    <span class="co-text"
                          style="min-width:0; overflow:hidden; text-overflow:ellipsis;"
                          @click.stop="gotoCompanyWorkspace(co.code)"
                          :title="'Открыть карточку — ' + co.name">{{ co.name }}</span>
                  </div>
                  <div class="co-bar-wrap"
                       @click.stop="openCompanyDrill(co.code, 'tasks')"
                       :title="'Открыть drill компании ' + co.name">
                    <span class="co-pct" :style="{color: pctColor(co.progress_pct)}">{{ co.progress_pct }}%</span>
                  </div>
                  <div class="co-num r co-num-clickable"
                       @click.stop="openCompanyDrill(co.code, 'projects')"
                       :title="'Drill: проекты ' + co.name">{{ co.projects_done }}/{{ co.projects_total }}</div>
                  <div class="co-num r co-num-clickable"
                       @click.stop="openCompanyDrill(co.code, 'tasks')"
                       :title="'Drill: задачи ' + co.name">{{ co.tasks_done }}/{{ co.tasks_total }}</div>
                </div>
              </template>
            </template>
          </div>
        </div>

        <ExecDashDirectionsBlock />
      </div>

      <!-- Row 2: Рейтинги | Bar chart (из Executive Dashboard) -->
      <div class="two-cols">
        <ExecDashRatings />
        <ExecDashExecutionChart />
      </div>
    </template>
  </div>
</template>

<style scoped>
.sh-page { padding: 24px 32px; max-width: 1800px; margin: 0 auto; }

/* Header */
.page-header { margin-bottom: 16px; }
.page-eyebrow { font-size: 10px; font-weight: 500; letter-spacing: 0.08em; text-transform: uppercase; color: var(--t3); margin-bottom: 8px; }
.page-title { font-size: 22px; font-weight: 500; letter-spacing: -0.01em; margin: 0 0 6px; color: var(--t1); }
.page-sub { font-size: 13px; color: var(--t3); }

.year-filter { display: flex; gap: 4px; margin-bottom: 20px; flex-wrap: wrap; }
.pill { padding: 4px 12px; font-size: 12px; font-weight: 500; border-radius: 11px; border: 1px solid var(--border1); background: var(--bg1); color: var(--t2); cursor: pointer; transition: all .15s; }
.pill:hover { background: var(--bg3); }
.pill.active { background: #7F77DD; color: white; border-color: #7F77DD; }

.state-msg { padding: 32px; text-align: center; color: var(--t3); font-size: 13px; }
.state-msg.error { color: #993D3D; }

/* 2026-05-26: skeleton loader stack — mirrors page structure */
.sh-skel-stack { display: flex; flex-direction: column; gap: 16px; padding: 8px 0; }
.sh-skel-row-2 { display: grid; grid-template-columns: 1fr 1fr; gap: 14px; }
@media (max-width: 1000px) { .sh-skel-row-2 { grid-template-columns: 1fr; } }

/* KPI strip */
.kpi-strip {
  display: grid;
  grid-template-columns: repeat(6, minmax(0, 1fr));
  gap: clamp(8px, 0.8vw, 14px);
  margin-bottom: clamp(10px, 1vw, 16px);
}
@media (max-width: 1366px) {
  .kpi-strip { grid-template-columns: repeat(3, minmax(0, 1fr)); }
}
@media (max-width: 720px) {
  .kpi-strip { grid-template-columns: repeat(2, minmax(0, 1fr)); }
}
.kpi2 {
  position: relative;
  padding: clamp(12px, 1.1vw, 16px);
  background: var(--bg1, #FFFFFF);
  border: 0.5px solid rgba(30, 42, 74, 0.06);
  border-radius: 12px;
  box-shadow: 0 2px 8px rgba(15, 23, 60, 0.04);
  display: flex;
  flex-direction: column;
  gap: clamp(4px, 0.4vw, 8px);
  min-height: clamp(86px, 7vw, 100px);
  overflow: hidden;
  transition: transform 0.18s ease, box-shadow 0.18s ease;
}

/* Pack 155c: scoped .kpi2::before override removed — global rule in
   main.css applies (drawIn + breathe + shimmer unified across the app). */

.kpi2:hover {
  transform: translateY(-2px);
  box-shadow: 0 6px 16px rgba(15, 23, 60, 0.08);
}
.kpi2.dim { opacity: 0.7; }
.kpi2:hover {
  transform: translateY(-2px);
  box-shadow: 0 6px 16px rgba(15, 23, 60, 0.08);
}
.kpi2.dim {
  opacity: 0.7;
}
.kpi2-lbl {
  font-size: clamp(10px, 0.78vw, 11px);
  font-weight: 500;
  text-transform: uppercase;
  letter-spacing: 0.08em;
  color: rgba(30, 42, 74, 0.55);
  line-height: 1;
}
.kpi2-val {
  font-size: clamp(28px, 2.4vw, 36px);
  font-weight: 400;
  letter-spacing: -0.025em;
  color: var(--t1, #1E2A4A);
  line-height: 1;
  font-variant-numeric: tabular-nums;
  margin-top: 2px;
}
.kpi2-split {
  display: flex;
  align-items: flex-end;
  gap: 12px;
  margin-top: 2px;
}
.kpi2-split > div {
  display: flex;
  flex-direction: column;
  gap: 2px;
}
.kpi2-num {
  font-size: clamp(22px, 1.9vw, 28px);
  font-weight: 400;
  letter-spacing: -0.02em;
  line-height: 1;
  font-variant-numeric: tabular-nums;
  color: var(--t1, #1E2A4A);
}
.kpi2-sub {
  font-size: clamp(10px, 0.78vw, 11px);
  color: rgba(30, 42, 74, 0.55);
  font-weight: 500;
  letter-spacing: 0.02em;
  text-transform: lowercase;
}
.kpi2-divider {
  width: 1px;
  align-self: stretch;
  background: rgba(30, 42, 74, 0.08);
  margin: 4px 0;
}
.fin-shimmer {
  animation: kpi2In 0.5s cubic-bezier(0.34, 1.2, 0.64, 1) backwards;
}
@keyframes kpi2In {
  from { opacity: 0; transform: translateY(8px); }
  to { opacity: 1; transform: translateY(0); }
}
.kpi2-split > div:nth-child(3) { padding-left: 12px; }

/* ═══ Pack 7.45: KPI-tile drill-down clickability ═══ */
.kpi2-clickable {
  cursor: pointer;
}
.kpi2-clickable:hover {
  transform: translateY(-2px);
  box-shadow: 0 6px 20px rgba(15, 23, 60, .12);
  border-color: var(--kpi2-accent, rgba(127, 119, 221, 0.3));
}
.kpi2-clickable:active {
  transform: translateY(-1px);
  transition-duration: 0.08s;
}
.kpi2-half {
  cursor: pointer;
  padding: 2px 6px;
  margin: -2px -6px;
  border-radius: 6px;
  transition: background 0.15s ease;
}
.kpi2-half:hover {
  background: rgba(127, 119, 221, .06);
}
.kpi2.dim .kpi2-half { cursor: default; }
.kpi2.dim .kpi2-half:hover { background: transparent; }

/* 3-col grid */
.three-cols {
  display: grid;
  grid-template-columns: minmax(280px, 1.1fr) minmax(360px, 1.6fr) minmax(280px, 1.1fr);
  gap: clamp(8px, 0.8vw, 14px);
  margin-bottom: clamp(10px, 1vw, 16px);
  align-items: stretch;
}
@media (max-width: 1280px) {
  .three-cols { grid-template-columns: 1fr; }
}
@media (max-width: 1400px) { .three-cols { grid-template-columns: 1fr; } }

.cc {
  background: var(--bg1, #FFFFFF);
  border: 0.5px solid rgba(30, 42, 74, 0.06);
  border-radius: 12px;
  padding: clamp(12px, 1.1vw, 18px);
  display: flex;
  flex-direction: column;
  gap: clamp(8px, 0.7vw, 12px);
  box-shadow: 0 2px 8px rgba(15, 23, 60, 0.04);
  height: clamp(360px, 30vw, 440px);
  overflow: hidden;
}
.cc-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  flex-shrink: 0;
}
.cc-title {
  font-size: clamp(11px, 0.88vw, 13px);
  font-weight: 500;
  color: rgba(30, 42, 74, 0.55);
  text-transform: uppercase;
  letter-spacing: 0.07em;
  flex: 1;
  white-space: nowrap;
}
.cc-sub { font-size: 11px; color: var(--t3); margin-top: 2px; }
.seg-controls {
  display: flex;
  gap: 4px;
  flex-shrink: 0;
}
.seg-ctrl {
  display: inline-flex;
  background: rgba(127, 119, 221, 0.08);
  border-radius: 8px;
  padding: 2px;
  gap: 1px;
}
.seg-btn {
  padding: 4px 10px;
  border: none;
  background: transparent;
  font-size: 11px;
  font-weight: 500;
  color: rgba(30, 42, 74, 0.55);
  border-radius: 6px;
  cursor: pointer;
  letter-spacing: 0.02em;
}
.seg-btn.active {
  background: var(--bg1, #FFFFFF);
  color: #7F77DD;
  box-shadow: 0 1px 3px rgba(15, 23, 60, 0.08);
}
.seg-btn.active { background: var(--bg1, #fff); color: var(--t1); box-shadow: 0 1px 3px rgba(0,0,0,.06); }

/* Donut */
.donut-row {
  display: flex;
  gap: 14px;
  align-items: flex-start;
  flex: 1;
  min-height: 0;
  overflow: hidden;
}
.donut-wrap {
  position: relative;
  width: clamp(120px, 11vw, 160px);
  height: clamp(120px, 11vw, 160px);
  flex-shrink: 0;
}
.donut-center {
  position: absolute;
  top: 50%;
  left: 50%;
  transform: translate(-50%, -50%);
  text-align: center;
}
.donut-num {
  font-size: clamp(20px, 1.7vw, 24px);
  font-weight: 500;
  color: var(--t1, #1E2A4A);
  letter-spacing: -0.04em;
  font-variant-numeric: tabular-nums;
  line-height: 1;
}
.donut-lbl {
  font-size: clamp(8px, 0.65vw, 9px);
  color: var(--t3, #64748B);
  font-weight: 500;
  text-transform: uppercase;
  letter-spacing: 0.16em;
  margin-top: 3px;
  text-align: center;
}
.donut-legend {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: clamp(2px, 0.3vw, 5px);
  min-width: 0;
  overflow-y: auto;
  max-height: 100%;
  padding-right: 6px;
}
.donut-legend::-webkit-scrollbar { width: 4px; }
.donut-legend::-webkit-scrollbar-thumb { background: rgba(30,42,74,.18); border-radius: 3px; }
.donut-legend::-webkit-scrollbar { width: 5px; }
.donut-legend::-webkit-scrollbar-thumb { background: rgba(30,42,74,.18); border-radius: 3px; }
.donut-legend::-webkit-scrollbar {
  width: 5px;
}
.donut-legend::-webkit-scrollbar-thumb {
  background: rgba(30, 42, 74, 0.18);
  border-radius: 3px;
}
.legend-row {
  display: grid;
  grid-template-columns: 11px minmax(0, 1fr) auto;
  align-items: center;
  gap: 10px;
  padding: clamp(2px, 0.3vw, 4px) 0;
  font-size: clamp(11px, 0.88vw, 12.5px);
  color: var(--t1, #1E2A4A);
}
.legend-dot {
  width: 9px;
  height: 9px;
  border-radius: 2px;
  flex-shrink: 0;
  opacity: 0.92;
}
.legend-lbl {
  font-size: clamp(11px, 0.88vw, 12.5px);
  color: var(--t1, #1E2A4A);
  font-weight: 500;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  min-width: 0;
  line-height: 1.25;
}
.legend-num {
  font-size: clamp(11.5px, 0.95vw, 13px);
  font-weight: 500;
  color: var(--t1, #1E2A4A);
  font-variant-numeric: tabular-nums;
  text-align: right;
  white-space: nowrap;
  flex-shrink: 0;
  min-width: 28px;
}
.legend-val {
  font-size: 13px;
  font-weight: 500;
  font-variant-numeric: tabular-nums;
  text-align: right;
  min-width: 32px;
}

/* Companies / Directions shared */
.comp-list-head, .dir-list-head {
  display: grid;
  grid-template-columns: minmax(0, 1.6fr) clamp(60px, 6vw, 80px) clamp(48px, 5vw, 60px) clamp(48px, 5vw, 60px);
  gap: clamp(8px, 0.7vw, 12px);
  padding: 0 4px 6px;
  font-size: clamp(9.5px, 0.75vw, 10.5px);
  font-weight: 500;
  color: rgba(30, 42, 74, 0.45);
  text-transform: uppercase;
  letter-spacing: 0.06em;
  border-bottom: 0.5px solid rgba(30, 42, 74, 0.06);
}
.dir-list-head .r { text-align: right; }
.dir-list-head .r { text-align: right; }
.dir-list-head .r {
  text-align: right;
}
.comp-list-head .r, .dir-list-head .r { text-align: right; }
.comp-body, .dir-body {
  flex: 1;
  overflow-y: auto;
  min-height: 0;
  padding-right: 4px;
}
.dir-body::-webkit-scrollbar {
  width: 5px;
}
.dir-body::-webkit-scrollbar-thumb {
  background: rgba(30, 42, 74, 0.18);
  border-radius: 3px;
}
.dir-body::-webkit-scrollbar-track {
  background: transparent;
}

.sector-header {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 5px 4px;
  font-size: 10.5px;
  font-weight: 500;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  color: rgba(30, 42, 74, 0.7);
  cursor: pointer;
  user-select: none;
  margin-top: 3px;
}
.sector-header:hover { background: var(--bg3); }
.sector-pill {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  flex-shrink: 0;
}
.sector-name {
  flex: 1;
}
.sector-count {
  font-size: 10.5px;
  color: rgba(30, 42, 74, 0.45);
  font-variant-numeric: tabular-nums;
}
.sector-arrow {
  display: inline-flex;
  color: rgba(30, 42, 74, 0.4);
  transition: transform 0.18s ease;
}
.sector-arrow.open {
  transform: rotate(-90deg);
}
.sector-arrow.open { transform: rotate(-90deg); }

.co-row, .dir-row {
  display: grid;
  grid-template-columns: minmax(0, 1.6fr) clamp(60px, 6vw, 80px) clamp(48px, 5vw, 60px) clamp(48px, 5vw, 60px);
  gap: clamp(8px, 0.7vw, 12px);
  align-items: center;
  padding: 5px 4px 5px 8px;
  border-radius: 6px;
  margin-bottom: 1px;
  font-size: clamp(11px, 0.9vw, 12.5px);
  transition: background 0.15s ease, transform 0.15s ease;
  position: relative;
  overflow: hidden;
}
/* co-row: левый паддинг под боковую вставную полоску (sector_color) */
.co-row { padding-left: 18px; }
/* Pack 154 follow-up: top-stripe удалён по запросу — был визуальный шум.
   Sector color now lives in the .co-code badge below. */
.dir-row:hover {
  background: rgba(127, 119, 221, 0.05);
  transform: translateX(2px);
}
.dir-row:hover {
  background: rgba(127, 119, 221, 0.05);
  transform: translateX(2px);
}
.dir-row:hover {
  background: rgba(127, 119, 221, 0.04);
}
.dir-row:hover {
  background: rgba(127, 119, 221, 0.04);
}
.co-row:hover, .dir-row:hover { background: var(--bg2); }
.co-row:last-child, .dir-row:last-child { border-bottom: none; }
.co-name, .dir-name {
  font-size: clamp(11px, 0.9vw, 12.5px);
  color: var(--t1, #1E2A4A);
  font-weight: 500;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  min-width: 0;
  line-height: 1.25;
}
.co-code {
  font-size: 9.5px;
  font-weight: 500;
  background: rgba(30, 42, 74, 0.05);
  color: rgba(30, 42, 74, 0.7);
  padding: 2px 6px;
  border-radius: 5px;
  letter-spacing: 0.04em;
  text-transform: uppercase;
  flex-shrink: 0;
}
.co-text {
  font-size: clamp(11px, 0.9vw, 12.5px);
  color: var(--t1, #1E2A4A);
  font-weight: 500;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  min-width: 0;
  line-height: 1.25;
}
.co-bar-wrap, .dir-bar-wrap {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 6px;
}
.co-pct, .dir-pct {
  font-size: 12px;
  font-weight: 500;
  font-variant-numeric: tabular-nums;
  min-width: 36px;
  text-align: right;
}
.co-num, .dir-num {
  font-size: 12px;
  font-weight: 500;
  font-variant-numeric: tabular-nums;
  color: var(--t1, #1E2A4A);
}
.dir-num.r {
  text-align: right;
}
.co-num.r, .dir-num.r { text-align: right; }

/* ═══ Pack 7.47: Company drill clickability ═══ */
.co-row-clickable .co-code { cursor: pointer; transition: background .14s ease, filter .14s ease; }
/* Hover: just darken whatever sector tint is applied (inline-style sets bg + color).
   Falling back to neutral hover-tint only when --cl isn't provided. */
.co-row-clickable .co-code:hover { filter: brightness(0.92); background: var(--cl, rgba(127,119,221,.28)); color: #fff; }
.co-row-clickable .co-text { cursor: pointer; border-bottom: 1px dashed transparent; transition: color .14s ease, border-color .14s ease; }
.co-row-clickable .co-text:hover { color: #534AB7; border-bottom-color: rgba(127, 119, 221, .5); }
.co-row-clickable .co-bar-wrap { cursor: pointer; padding: 4px 6px; margin: -4px -6px; border-radius: 6px; transition: background .14s ease; }
.co-row-clickable .co-bar-wrap:hover { background: rgba(127, 119, 221, .05); }
.co-num-clickable { cursor: pointer; padding: 2px 8px; border-radius: 6px; transition: background .14s ease, color .14s ease; }
.co-num-clickable:hover { background: rgba(127, 119, 221, .08); color: #534AB7 !important; }

/* ═══ Row 2: Ratings | Completion ═══ */
.two-cols { display: grid; grid-template-columns: 1fr 1fr; gap: 14px; margin-bottom: 18px; align-items: stretch; }
@media (max-width: 1400px) { .two-cols { grid-template-columns: 1fr; } }

/* Ratings card */
.rating-card { animation-delay: 360ms; }
.rings-row { display: grid; grid-template-columns: repeat(4, 1fr); gap: 10px; padding: 14px 16px; border-bottom: 1px solid var(--border1); }
.ring-cell { display: flex; align-items: center; gap: 10px; padding: 8px 10px; background: var(--bg2); border-radius: 8px; }
.ring-wrap { position: relative; width: 68px; height: 68px; flex-shrink: 0; }
.ring-center { position: absolute; inset: 0; display: flex; align-items: center; justify-content: center; pointer-events: none; }
.ring-pct { font-size: 16px; font-weight: 500; letter-spacing: -.02em; font-variant-numeric: tabular-nums; }
.ring-meta { flex: 1; min-width: 0; }
.ring-label { font-size: 9px; font-weight: 500; color: var(--t3); letter-spacing: .07em; text-transform: uppercase; }
.ring-stat { display: flex; align-items: baseline; gap: 4px; margin-top: 4px; }
.ring-covered { font-size: 16px; font-weight: 500; color: var(--t1); font-variant-numeric: tabular-nums; }
.ring-of { font-size: 10px; color: var(--t3); }
.ring-uncovered { font-size: 9.5px; color: #993D3D; margin-top: 2px; }

/* Rating table */
.rating-table-head { display: grid; grid-template-columns: 1.3fr 2fr 1.5fr; padding: 6px 16px; font-size: 9px; font-weight: 500; color: var(--t3); letter-spacing: .07em; text-transform: uppercase; border-bottom: 0.5px solid var(--border1); }
.rt-col-name { padding-left: 0; }
.rt-col-group { text-align: center; }
.rating-table-sub { display: grid; grid-template-columns: 1.3fr repeat(6, 1fr); padding: 4px 16px; font-size: 8.5px; font-weight: 500; color: var(--t3); letter-spacing: .05em; text-transform: uppercase; border-bottom: 1px solid var(--border1); }
.rating-table-sub .rt-cell { text-align: center; }

.rating-table-body { padding: 4px 0; max-height: 320px; overflow-y: auto; }

.rt-sector-header { padding: 6px 16px; font-size: 9px; font-weight: 500; color: var(--t3); letter-spacing: .07em; text-transform: uppercase; background: var(--bg2); position: relative; overflow: hidden; }
.rt-sector-header::before {
  content: ""; position: absolute; top: 0; left: 0; right: 0;
  height: 2px; background: currentColor;
  animation: uzaStripeDrawIn .4s cubic-bezier(0.34, 1.2, 0.64, 1) both;
  transform-origin: left center;
  pointer-events: none;
  opacity: .7;
}
.rt-row { display: grid; grid-template-columns: 1.3fr repeat(6, 1fr); padding: 6px 16px; align-items: center; border-bottom: 0.5px solid var(--border1); }
.rt-row:hover { background: var(--bg2); }
.rt-name { display: flex; align-items: center; gap: 6px; min-width: 0; }
.rt-name-text { font-size: 11.5px; color: var(--t1); font-weight: 500; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.rt-cell { text-align: center; font-size: 11px; }
.rt-pill { display: inline-block; padding: 2px 7px; border-radius: 4px; font-size: 10.5px; font-weight: 500; font-variant-numeric: tabular-nums; }
.rt-score { display: inline-block; padding: 2px 7px; border-radius: 4px; font-size: 10.5px; font-weight: 500; background: #F1F5F9; color: var(--t2, #475569); font-variant-numeric: tabular-nums; }
.rt-empty { color: var(--t3); }

/* Completion */
.completion-card { animation-delay: 440ms; }
.completion-meta { display: flex; align-items: center; justify-content: space-between; padding: 8px 16px; border-bottom: 1px solid var(--border1); flex-wrap: wrap; gap: 10px; }
.completion-avg { display: flex; align-items: baseline; gap: 6px; }
.avg-label { font-size: 10px; color: var(--t3); }
.avg-value { font-size: 16px; font-weight: 500; color: var(--t1); letter-spacing: -.02em; font-variant-numeric: tabular-nums; }
.completion-zones { display: flex; gap: 10px; font-size: 10.5px; color: var(--t3); }
.zone { display: inline-flex; align-items: center; gap: 4px; }
.zone-dot { width: 8px; height: 8px; border-radius: 2px; }

.completion-canvas-wrap {
  padding: 12px 16px;
  overflow: hidden;
  flex: 1;
  min-height: 0;
}
.completion-canvas-wrap canvas {
  max-width: 100%;
  width: 100%;
  height: 100% !important;
  max-height: 100%;
  display: block;
  object-fit: contain;
}
/* Both cards fixed compact height */
.cc.rating-card,
.cc.completion-card {
  height: 640px;
  max-height: 640px;
  display: flex;
  flex-direction: column;
  min-height: 0;
}
/* Inner scroll for rating table */
.rating-table-body {
  flex: 1 1 auto;
  min-height: 0;
  max-height: none;
  overflow-y: auto;
}
/* Compact donuts — scaled for narrow column */
.rings-row         { padding: 8px 12px !important; gap: 4px !important; }
.ring-cell         { padding: 4px 6px !important; gap: 6px !important; }
.ring-wrap         { width: 60px !important; height: 60px !important; }
.ring-pct          { font-size: 14px !important; font-weight: 500 !important; }
.ring-label        { font-size: 9px !important; }
.ring-covered      { font-size: 14px !important; font-weight: 500 !important; }
.ring-of           { font-size: 9.5px !important; }
.ring-uncovered    { font-size: 9px !important; }
/* Compact rating table to fit more rows */
.rating-table-head { padding: 5px 16px 2px !important; }
.rating-table-sub  { padding: 2px 16px 4px !important; }
.rt-sector-header  { padding: 4px 16px !important; }
.rt-row            { padding: 4px 16px !important; }
.rt-name-text      { font-size: 12px !important; }
.rt-cell           { font-size: 11.5px !important; }
.rt-pill, .rt-score { font-size: 11px !important; }
</style>
