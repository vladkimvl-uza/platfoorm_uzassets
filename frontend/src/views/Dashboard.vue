<script setup lang="ts">
import { ref, computed, onMounted, watch, nextTick, onBeforeUnmount } from "vue";
import { useSavedFilter } from "@/composables/useSavedFilter";
import { useCompanyScope } from "@/composables/useCompanyScope";
import { useAiPageContext } from "@/composables/useAiPageContext";
import { useNumberTween } from "@/composables/useNumberTween";
import UzaSkeleton from "@/components/UZA/UzaSkeleton.vue";
import Odometer from "@/components/Odometer.vue";
import { api } from "@/api/client";
import { Chart } from "@/utils/chartjsRegister";
import { useI18n } from "@/composables/useI18n";

const { t } = useI18n();
const scope = useCompanyScope();

defineEmits<{ (e: 'toggle-sidebar'): void }>();

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

const donutCanvas = ref<HTMLCanvasElement | null>(null);
let donutChart: any = null;

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

// ─── Интерактивная легенда доната (вариант A: живой донат) ───
// Hover строки легенды → её сегмент «выезжает» (hoverOffset), остальные
// приглушаются, центр морфит в число/% этого статуса. Просрочено в кольцо
// не входит (ringStatuses без overdue) — для него подсвечивать нечего, но
// центр всё равно показывает его значение.
const hoveredStatus = ref<StatusRow | null>(null);
const centerNum = computed(() =>
  hoveredStatus.value ? formatStatusValue(hoveredStatus.value) : String(totalCenterValue.value));
const centerLbl = computed(() =>
  hoveredStatus.value ? t(hoveredStatus.value.label) : (statusEntity.value === "projects" ? t("ПРОЕКТОВ") : t("ЗАДАЧ")));
function fadeColor(hex: string): string {
  const h = hex.replace("#", "");
  if (h.length < 6) return hex;
  const r = parseInt(h.slice(0, 2), 16), g = parseInt(h.slice(2, 4), 16), b = parseInt(h.slice(4, 6), 16);
  return `rgba(${r}, ${g}, ${b}, 0.18)`;
}
function onLegendEnter(s: StatusRow) {
  hoveredStatus.value = s;
  if (!donutChart) return;
  const ringIdx = ringStatuses.value.findIndex(r => r.id === s.id);
  donutChart.data.datasets[0].backgroundColor = ringStatuses.value.map((r, i) =>
    ringIdx >= 0 && i !== ringIdx ? fadeColor(r.color) : r.color);
  donutChart.setActiveElements(ringIdx >= 0 ? [{ datasetIndex: 0, index: ringIdx }] : []);
  donutChart.update("none");
}
function onLegendLeave() {
  hoveredStatus.value = null;
  if (!donutChart) return;
  donutChart.data.datasets[0].backgroundColor = ringStatuses.value.map(r => r.color);
  donutChart.setActiveElements([]);
  donutChart.update("none");
}

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
  const labels = ringStatuses.value.map(s => t(s.label));
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

const kpiTotal = computed(() => {
  if (!data.value) return { proj: 0, tasks: 0 };
  return { proj: data.value.kpis.projects, tasks: data.value.kpis.tasks };
});

// Доля (для прогресс-баров и футера «X% от всех задач»).
function pct(n: number | undefined, total: number | undefined): number {
  const t = Number(total) || 0;
  if (t <= 0) return 0;
  return Math.round(((Number(n) || 0) / t) * 100);
}

function fmtKpi(value: number, total: number): string {
  if (statusFormat.value === "percent") {
    if (total <= 0) return "0%";
    return Math.round(value / total * 100) + "%";
  }
  return String(value);
}
watch([data, statusEntity, statusFormat], () => { nextTick(renderDonut); }, { deep: false });

// Анимация «переброса» чисел KPI-плиток при переключении формата #↔%.
const fmtSwitch = ref(false);
let fmtSwitchTimer: ReturnType<typeof setTimeout> | null = null;
watch(statusFormat, () => {
  fmtSwitch.value = true;
  if (fmtSwitchTimer) clearTimeout(fmtSwitchTimer);
  fmtSwitchTimer = setTimeout(() => { fmtSwitch.value = false; }, 360);
});

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
    errorMsg.value = e?.response?.data?.detail || e?.message || t("Ошибка загрузки");
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

// === Phase 1: dropdown filters (frontend-only) ===
const sectorFilter = useSavedFilter<string>("dashboard.sectorFilter", "");
const directionFilter = useSavedFilter<string>("dashboard.directionFilter", "");
const companyFilter = useSavedFilter<string>("dashboard.companyFilter", "");

// Фильтры хранятся в localStorage устройства: на общем компьютере они могут
// остаться от ДРУГОГО пользователя (чужая компания/сектор). Скрытый селектор
// такой выбор не покажет и не даст сбросить — приводим значения к области
// доступа до первой загрузки (watch на фильтры объявлен ниже).
// Пустой фильтр = «всё, что доступно»: эндпоинт /dashboard/shareholder уже
// сужен до компаний пользователя, поэтому единственной компании достаточно
// сброса — данные придут по ней.
if (!scope.showCompanyPicker.value || !scope.allows(companyFilter.value)) {
  companyFilter.value = "";
}
if (!scope.showSectorPicker.value) sectorFilter.value = "";

// Pack 7.9e: AI Bubble context
useAiPageContext({
  key: "dashboard",
  label: t("Главный дашборд"),
  describeState: () => {
    const parts: string[] = [];
    if (sectorFilter.value) parts.push(`сектор: ${sectorFilter.value}`);
    if (companyFilter.value) parts.push(`компания: ${companyFilter.value}`);
    parts.push(`показано: ${statusEntity.value === "tasks" ? "задачи" : "проекты"}`);
    parts.push(`формат: ${statusFormat.value}`);
    return parts.join("; ");
  },
  quickActions: [
    { label: t("Сводка дашборда"),
      prompt: "Дай сводку главного дашборда: статусы проектов/задач по компаниям и секторам. Что выделяется. Используй get_kpi_summary." },
    { label: t("Топ-5 отстающих"),
      prompt: "Найди топ-5 отстающих компаний по выполнению задач за текущий год. Используй get_kpi_summary.top_overdue_companies + конкретные рекомендации." },
    { label: t("Что просрочено?"),
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

// Секторы для фильтра — ТОЛЬКО те, в которых у пользователя есть компании
// (payload companies_by_sector уже scoped на бэке). Раньше список был
// захардкожен всеми 5 секторами → ограниченный пользователь видел чужие.
const sectorOptions = computed<{ code: string; label: string }[]>(() => {
  if (!data.value) return [];
  const seen = new Map<string, string>();
  for (const grp of data.value.companies_by_sector) {
    if (!seen.has(grp.sector)) seen.set(grp.sector, grp.sector_label);
  }
  return [...seen.entries()].map(([code, label]) => ({ code, label }));
});

const hasFilters = computed(
  () => sectorFilter.value !== "" || directionFilter.value !== "" || companyFilter.value !== ""
);

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

onMounted(load);

// Обновление при возврате на вкладку: данные дашборда (в т.ч. «Проекты по
// компаниям») приходят с эндпоинта и кешируются — при возврате фокуса
// перечитываем их и ростер, чтобы новые/включённые компании появлялись без F5.
let _lastVisRefresh = 0;
function onTabVisible() {
  if (typeof document !== "undefined" && document.visibilityState === "hidden") return;
  const now = Date.now();
  if (now - _lastVisRefresh < 3000) return;
  _lastVisRefresh = now;
  void companies.reload();
  void load();
  if (yearStore.year) exec.loadData();
}
onMounted(() => {
  document.addEventListener("visibilitychange", onTabVisible);
  window.addEventListener("focus", onTabVisible);
});
onBeforeUnmount(() => {
  document.removeEventListener("visibilitychange", onTabVisible);
  window.removeEventListener("focus", onTabVisible);
  if (donutChart) donutChart.destroy();
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
      <select v-if="scope.showCompanyPicker.value" v-model="companyFilter" class="apt-page-select">
        <option value="">{{ t("Все компании") }}</option>
        <option v-for="c in allCompaniesList" :key="c.code" :value="c.code">{{ companies.getCompanyName(c.code) || c.name }}</option>
      </select>
      <select v-if="scope.showSectorPicker.value" v-model="sectorFilter" class="apt-page-select">
        <option value="">{{ t("Все секторы") }}</option>
        <option v-for="s in sectorOptions" :key="s.code" :value="s.code">{{ t(s.label) }}</option>
      </select>
      <select v-model="directionFilter" class="apt-page-select">
        <option value="">{{ t("Все направления") }}</option>
        <option v-for="d in (data?.directions || [])" :key="d.id" :value="d.id">{{ t(d.label) }}</option>
      </select>
      <button v-if="hasFilters" @click="clearFilters" :title="t('Сбросить')" class="apt-page-reset">×</button>
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
      <div class="kpi-strip" :class="{ 'fmt-switch': fmtSwitch }">
        <!-- ПРОЕКТОВ -->
        <div class="kpi2 fin-shimmer kpi2-clickable"
             style="--kpi2-accent: #7F77DD; animation-delay: 0ms"
             @click="openKpiDrill('total','projects')">
          <div class="kpi2-head">
            <div class="kpi2-lbl">{{ t("ПРОЕКТОВ") }}</div>
            <span class="kpi2-ico" style="--ico:#7F77DD">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="4" width="7" height="16" rx="1.5"/><rect x="14" y="4" width="7" height="16" rx="1.5"/></svg>
            </span>
          </div>
          <div class="kpi2-val">{{ Math.round(tweenedProjects) }}</div>
          <div class="kpi2-foot">{{ t("в портфеле") }}</div>
        </div>

        <!-- ВСЕГО ЗАДАЧ -->
        <div class="kpi2 fin-shimmer kpi2-clickable"
             style="--kpi2-accent: #3B82F6; animation-delay: 80ms"
             @click="openKpiDrill('total','tasks')">
          <div class="kpi2-head">
            <div class="kpi2-lbl">{{ t("ВСЕГО ЗАДАЧ") }}</div>
            <span class="kpi2-ico" style="--ico:#3B82F6">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M8 6h12M8 12h12M8 18h12"/><circle cx="4" cy="6" r="1"/><circle cx="4" cy="12" r="1"/><circle cx="4" cy="18" r="1"/></svg>
            </span>
          </div>
          <div class="kpi2-val">{{ Math.round(tweenedTasks) }}</div>
          <div class="kpi2-foot">{{ t("по {n} проектам", { n: kpiTotal.proj }) }}</div>
        </div>

        <!-- ЗАВЕРШЕНО -->
        <div class="kpi2 fin-shimmer kpi2-clickable"
             style="--kpi2-accent: #1D9E75; animation-delay: 160ms"
             @click="openKpiDrill('done','tasks')">
          <div class="kpi2-head">
            <div class="kpi2-lbl">{{ t("ЗАВЕРШЕНО") }}</div>
            <span class="kpi2-ico" style="--ico:#1D9E75">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M5 12.5l4.5 4.5L19 7"/></svg>
            </span>
          </div>
          <div class="kpi2-split">
            <div class="kpi2-half" role="button" tabindex="0" :aria-label="t('Завершённые проекты')" @click.stop="openKpiDrill('done','projects')" @keydown.enter.prevent="openKpiDrill('done','projects')" @keydown.space.prevent="openKpiDrill('done','projects')"><div class="kpi2-num" style="color:#1D9E75">{{ fmtKpi(Math.round(tweenedDoneProj), kpiTotal.proj) }}</div><div class="kpi2-sub">{{ t("проектов") }}</div><div class="kpi2-mbar"><span :style="{ width: pct(data.kpis.done_proj, kpiTotal.proj) + '%', background: '#1D9E75' }"></span></div></div>
            <div class="kpi2-divider"></div>
            <div class="kpi2-half" role="button" tabindex="0" :aria-label="t('Завершённые задачи')" @click.stop="openKpiDrill('done','tasks')" @keydown.enter.prevent="openKpiDrill('done','tasks')" @keydown.space.prevent="openKpiDrill('done','tasks')"><div class="kpi2-num" style="color:#1D9E75">{{ fmtKpi(Math.round(tweenedDoneTasks), kpiTotal.tasks) }}</div><div class="kpi2-sub">{{ t("задач") }}</div><div class="kpi2-mbar"><span :style="{ width: pct(data.kpis.done_tasks, kpiTotal.tasks) + '%', background: '#1D9E75' }"></span></div></div>
          </div>
          <div class="kpi2-foot">{{ t("{p}% от всех задач", { p: pct(data.kpis.done_tasks, kpiTotal.tasks) }) }}</div>
        </div>

        <!-- В ПРОЦЕССЕ -->
        <div class="kpi2 fin-shimmer kpi2-clickable"
             style="--kpi2-accent: #D97706; animation-delay: 240ms"
             @click="openKpiDrill('active','tasks')">
          <div class="kpi2-head">
            <div class="kpi2-lbl">{{ t("В ПРОЦЕССЕ") }}</div>
            <span class="kpi2-ico" style="--ico:#D97706">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="8"/><path d="M12 12V5a7 7 0 0 1 6.1 3.5z" fill="currentColor" stroke="none"/></svg>
            </span>
          </div>
          <div class="kpi2-split">
            <div class="kpi2-half" role="button" tabindex="0" :aria-label="t('Проекты в процессе')" @click.stop="openKpiDrill('active','projects')" @keydown.enter.prevent="openKpiDrill('active','projects')" @keydown.space.prevent="openKpiDrill('active','projects')"><div class="kpi2-num" style="color:#D97706">{{ fmtKpi(Math.round(tweenedActiveProj), kpiTotal.proj) }}</div><div class="kpi2-sub">{{ t("проектов") }}</div><div class="kpi2-mbar"><span :style="{ width: pct(data.kpis.active_proj, kpiTotal.proj) + '%', background: '#D97706' }"></span></div></div>
            <div class="kpi2-divider"></div>
            <div class="kpi2-half" role="button" tabindex="0" :aria-label="t('Задачи в процессе')" @click.stop="openKpiDrill('active','tasks')" @keydown.enter.prevent="openKpiDrill('active','tasks')" @keydown.space.prevent="openKpiDrill('active','tasks')"><div class="kpi2-num" style="color:#D97706">{{ fmtKpi(Math.round(tweenedActiveTasks), kpiTotal.tasks) }}</div><div class="kpi2-sub">{{ t("задач") }}</div><div class="kpi2-mbar"><span :style="{ width: pct(data.kpis.active_tasks, kpiTotal.tasks) + '%', background: '#D97706' }"></span></div></div>
          </div>
          <div class="kpi2-foot">{{ t("{p}% от всех задач", { p: pct(data.kpis.active_tasks, kpiTotal.tasks) }) }}</div>
        </div>

        <!-- ПРОСРОЧЕНО -->
        <div :class="['kpi2','fin-shimmer',{dim: data.kpis.overdue_proj+data.kpis.overdue_tasks===0, 'kpi2-clickable': data.kpis.overdue_proj+data.kpis.overdue_tasks>0, 'kpi2-alert': data.kpis.overdue_proj+data.kpis.overdue_tasks>0}]"
             :style="`--kpi2-accent:${data.kpis.overdue_proj+data.kpis.overdue_tasks>0?'#EF4444':'#e2e8f0'};animation-delay:320ms`"
             @click="data.kpis.overdue_tasks>0 ? openKpiDrill('overdue','tasks') : (data.kpis.overdue_proj>0 && openKpiDrill('overdue','projects'))">
          <div class="kpi2-head">
            <div class="kpi2-lbl">{{ t("ПРОСРОЧЕНО") }}</div>
            <span class="kpi2-ico" :style="{ '--ico': data.kpis.overdue_proj+data.kpis.overdue_tasks>0 ? '#EF4444' : '#94a3b8' }">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="9"/><path d="M12 7.5v5M12 16h.01"/></svg>
            </span>
          </div>
          <div class="kpi2-split">
            <div class="kpi2-half" @click.stop="data.kpis.overdue_proj>0 && openKpiDrill('overdue','projects')"><div class="kpi2-num" :style="{color: data.kpis.overdue_proj>0?'var(--t1, #1E2A4A)':'#94a3b8'}">{{ fmtKpi(Math.round(tweenedOverdueProj), kpiTotal.proj) }}</div><div class="kpi2-sub">{{ t("проектов") }}</div><div class="kpi2-mbar"><span :style="{ width: pct(data.kpis.overdue_proj, kpiTotal.proj) + '%', background: '#EF4444' }"></span></div></div>
            <div class="kpi2-divider"></div>
            <div class="kpi2-half" @click.stop="data.kpis.overdue_tasks>0 && openKpiDrill('overdue','tasks')"><div class="kpi2-num" :style="{color: data.kpis.overdue_tasks>0?'var(--t1, #1E2A4A)':'#94a3b8'}">{{ fmtKpi(Math.round(tweenedOverdueTasks), kpiTotal.tasks) }}</div><div class="kpi2-sub">{{ t("задач") }}</div><div class="kpi2-mbar"><span :style="{ width: pct(data.kpis.overdue_tasks, kpiTotal.tasks) + '%', background: '#EF4444' }"></span></div></div>
          </div>
          <div class="kpi2-foot">{{ data.kpis.overdue_tasks>0 ? t("{p}% от всех задач", { p: pct(data.kpis.overdue_tasks, kpiTotal.tasks) }) : t("просрочек нет") }}</div>
        </div>

        <!-- ПЕРЕНЕСЕНО — скрываем при 0, показываем когда появятся переносы -->
        <div v-if="data.kpis.deferred_proj+data.kpis.deferred_tasks>0"
             :class="['kpi2','fin-shimmer',{dim: data.kpis.deferred_proj+data.kpis.deferred_tasks===0, 'kpi2-clickable': data.kpis.deferred_proj+data.kpis.deferred_tasks>0}]"
             :style="`--kpi2-accent:${data.kpis.deferred_proj+data.kpis.deferred_tasks>0?'#7F77DD':'#e2e8f0'};animation-delay:400ms;${data.kpis.deferred_proj+data.kpis.deferred_tasks>0?'background:linear-gradient(180deg,#FFF 0%,#FCFAFF 100%);':''}`"
             @click="data.kpis.deferred_tasks>0 ? openKpiDrill('deferred','tasks') : (data.kpis.deferred_proj>0 && openKpiDrill('deferred','projects'))">
          <div class="kpi2-head">
            <div class="kpi2-lbl">{{ t("ПЕРЕНЕСЕНО") }}</div>
            <span class="kpi2-ico" :style="{ '--ico': data.kpis.deferred_proj+data.kpis.deferred_tasks>0 ? '#7F77DD' : '#94a3b8' }">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M4 8h13l-3-3M20 16H7l3 3"/></svg>
            </span>
          </div>
          <div class="kpi2-split">
            <div class="kpi2-half" @click.stop="data.kpis.deferred_proj>0 && openKpiDrill('deferred','projects')"><div class="kpi2-num" :style="{color: data.kpis.deferred_proj>0?'#7F77DD':'#94a3b8'}">{{ fmtKpi(Math.round(tweenedDeferredProj), kpiTotal.proj) }}</div><div class="kpi2-sub">{{ t("проектов") }}</div><div class="kpi2-mbar"><span :style="{ width: pct(data.kpis.deferred_proj, kpiTotal.proj) + '%', background: '#7F77DD' }"></span></div></div>
            <div class="kpi2-divider"></div>
            <div class="kpi2-half" @click.stop="data.kpis.deferred_tasks>0 && openKpiDrill('deferred','tasks')"><div class="kpi2-num" :style="{color: data.kpis.deferred_tasks>0?'#7F77DD':'#94a3b8'}">{{ fmtKpi(Math.round(tweenedDeferredTasks), kpiTotal.tasks) }}</div><div class="kpi2-sub">{{ t("задач") }}</div><div class="kpi2-mbar"><span :style="{ width: pct(data.kpis.deferred_tasks, kpiTotal.tasks) + '%', background: '#7F77DD' }"></span></div></div>
          </div>
          <div class="kpi2-foot">{{ data.kpis.deferred_tasks+data.kpis.deferred_proj>0 ? t("{p}% от всех задач", { p: pct(data.kpis.deferred_tasks, kpiTotal.tasks) }) : t("нет записей") }}</div>
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
            <div class="cc-title">{{ t("Статусы") }}</div>
            <div class="seg-controls">
              <div class="uza-seg is-sm">
                <button :class="['uza-seg-btn',{on:statusEntity==='projects'}]" @click="statusEntity='projects'">{{ t("Проекты") }}</button>
                <button :class="['uza-seg-btn',{on:statusEntity==='tasks'}]" @click="statusEntity='tasks'">{{ t("Задачи") }}</button>
              </div>
              <div class="uza-seg is-sm">
                <button :class="['uza-seg-btn',{on:statusFormat==='count'}]" @click="statusFormat='count'">#</button>
                <button :class="['uza-seg-btn',{on:statusFormat==='percent'}]" @click="statusFormat='percent'">%</button>
              </div>
            </div>
          </div>
          <div class="donut-row">
            <div class="donut-wrap">
              <canvas ref="donutCanvas" width="160" height="160"></canvas>
              <div class="donut-center" :class="{ 'is-focus': hoveredStatus }">
                <div class="donut-num"><Odometer :value="centerNum" /></div>
                <div class="donut-lbl">{{ centerLbl }}</div>
              </div>
            </div>
            <div class="donut-legend">
              <div v-for="(s, si) in data.statuses.filter(x => (statusEntity === 'projects' ? x.projects_count : x.tasks_count) > 0)"
                   :key="s.id" class="legend-row"
                   :class="{ 'is-overdue': s.id==='overdue', 'is-active': hoveredStatus && hoveredStatus.id===s.id }"
                   :style="{ '--si': si }"
                   @mouseenter="onLegendEnter(s)" @mouseleave="onLegendLeave()">
                <span class="legend-dot" :style="{background:s.color}"></span>
                <span class="legend-lbl">{{ t(s.label) }}<small v-if="s.id==='overdue'" class="legend-note" :title="t('«Просрочено» — сквозной счётчик по всем статусам, не отдельный сегмент кольца')">· {{ t("вне кольца") }}</small></span>
                <span class="legend-val" :style="{color:s.id==='overdue'?'#E24B4A':'var(--t1)'}">{{ formatStatusValue(s) }}</span>
              </div>
            </div>
          </div>
        </div>

        <div class="cc">
          <div class="cc-header"><div class="cc-title">{{ t("Проекты по компаниям") }}</div></div>
          <div class="comp-list-head">
            <span>{{ t("КОМПАНИЯ") }}</span><span :title="t('Средневзвешенный прогресс по статусам задач (не done/всего)')">{{ t("ПРОГРЕСС") }}</span><span class="r" :title="t('Завершено полностью / всего')">{{ t("ПРОЕКТЫ") }}</span><span class="r" :title="t('Завершено полностью / всего')">{{ t("ЗАДАЧИ") }}</span>
          </div>
          <div class="comp-body">
            <template v-for="grp in (data?.companies_by_sector || [])" :key="grp.sector">
              <div class="sector-header" role="button" tabindex="0"
                   :aria-expanded="!expandedSectors.has(grp.sector)"
                   @click="toggleSector(grp.sector)"
                   @keydown.enter.prevent="toggleSector(grp.sector)"
                   @keydown.space.prevent="toggleSector(grp.sector)">
                <span class="sector-pill" :style="{background:grp.sector_color}"></span>
                <span class="sector-name">{{ t(grp.sector_label) }}</span>
                <span class="sector-count">{{ grp.companies.length }}</span>
                <span class="sector-arrow" :class="{open: !expandedSectors.has(grp.sector)}">
                  <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor"
                       stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                    <polyline points="6 9 12 15 18 9"/>
                  </svg>
                </span>
              </div>
              <template v-if="!expandedSectors.has(grp.sector)">
                <div v-for="(co, idx) in grp.companies" :key="co.code" class="co-row co-row-clickable uza-side-stripe uza-side-stripe-tight"
                     :style="{ '--stripe-color': grp.sector_color }">
                  <div class="co-name" style="display:flex; align-items:center; gap:8px; min-width:0;">
                    <CompanyAvatar :name="co.name || co.code" :color="grp.sector_color" :size="22" />
                    <span class="co-code"
                          :style="{ background: grp.sector_color + '22', color: grp.sector_color, '--cl': grp.sector_color }"
                          @click.stop="openCompanyDrill(co.code, 'projects')"
                          :title="t('Открыть drill компании {name}', { name: co.name })">{{ co.code }}</span>
                    <span class="co-text"
                          style="min-width:0; overflow:hidden; text-overflow:ellipsis;"
                          @click.stop="gotoCompanyWorkspace(co.code)"
                          :title="t('Открыть карточку — {name}', { name: co.name })">{{ co.name }}</span>
                  </div>
                  <div class="co-bar-wrap" role="button" tabindex="0"
                       @click.stop="openCompanyDrill(co.code, 'tasks')"
                       @keydown.enter.prevent.stop="openCompanyDrill(co.code, 'tasks')"
                       @keydown.space.prevent.stop="openCompanyDrill(co.code, 'tasks')"
                       :aria-label="t('Открыть детализацию задач — {name}', { name: co.name })"
                       :title="t('Открыть drill компании {name}', { name: co.name })">
                    <span class="co-pct" :style="{color: pctColor(co.progress_pct)}">{{ co.progress_pct }}%</span>
                    <span class="co-bar"><i class="co-bar-fill"
                          :style="{ width: co.progress_pct + '%', '--c': pctColor(co.progress_pct), '--d': (idx * 45) + 'ms' }"></i></span>
                  </div>
                  <div class="co-num r co-num-clickable"
                       @click.stop="openCompanyDrill(co.code, 'projects')"
                       :title="t('Drill: проекты {name}', { name: co.name })">{{ co.projects_done }}/{{ co.projects_total }}</div>
                  <div class="co-num r co-num-clickable"
                       @click.stop="openCompanyDrill(co.code, 'tasks')"
                       :title="t('Drill: задачи {name}', { name: co.name })">{{ co.tasks_done }}/{{ co.tasks_total }}</div>
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
  /* auto-fit: ряд подстраивается под число ВИДИМЫХ карточек — при скрытии
     «Перенесено» не остаётся пустого столбца. */
  grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
  /* Единая лента: gap 1px → волосяные разделители «просвечивают» фоном панели
     (приём gridlines) при любом числе столбцов и переносах. */
  gap: 1px;
  margin-bottom: clamp(10px, 1vw, 16px);
  background: var(--card-border, rgba(30, 42, 74, 0.11));
  border: 1px solid var(--card-border, rgba(30, 42, 74, 0.08));
  border-radius: 16px;
  box-shadow: 0 2px 14px rgba(15, 23, 60, 0.07), 0 1px 3px rgba(15, 23, 60, 0.04);
  overflow: hidden;
}
/* Переброс чисел KPI-плиток при переключении формата #↔% */
.kpi-strip.fmt-switch .kpi2-val,
.kpi-strip.fmt-switch .kpi2-num {
  animation: kpiFmtFlip 0.34s var(--ease-standard, ease);
}
@keyframes kpiFmtFlip {
  0%   { opacity: 1; transform: translateY(0); }
  45%  { opacity: 0; transform: translateY(-7px); }
  46%  { opacity: 0; transform: translateY(7px); }
  100% { opacity: 1; transform: translateY(0); }
}
@media (max-width: 1366px) {
  .kpi-strip { grid-template-columns: repeat(auto-fit, minmax(160px, 1fr)); }
}
/* Планшет/узкий ноут (≤1023): ровно 3-в-ряд — у части карточек по 2 числа,
   и auto-fit давал «сироту» 4+1; repeat(3) кладёт 3+2 ровно (6 карт → 3+3). */
@media (max-width: 1023px) {
  .kpi-strip { grid-template-columns: repeat(3, minmax(0, 1fr)); }
}
@media (max-width: 720px) {
  .kpi-strip { grid-template-columns: repeat(2, minmax(0, 1fr)); }
}
/* Телефон: KPI-карточки — премиум горизонтально-свайпаемый ряд (как на десктопе),
   с snap. Дизайн карточек и анимации (.kpi2 ::before/::after) сохраняются. */
@media (max-width: 640px) {
  .kpi-strip {
    display: flex;
    grid-template-columns: none;
    overflow-x: auto;
    gap: 10px;
    padding-bottom: 6px;
    scroll-snap-type: x proximity;
    -webkit-overflow-scrolling: touch;
    /* Тонкий скроллбар как индикатор свайпа (раньше был скрыт → непонятно,
       что лента прокручивается). */
    scrollbar-width: thin;
    scrollbar-color: rgba(124, 111, 247, 0.4) transparent;
    /* На телефоне «лента» распадается на раздельные свайп-карточки — снимаем
       обёртку-панель и возвращаем карточный вид каждой плитке. */
    background: transparent;
    border: none;
    border-radius: 0;
    box-shadow: none;
  }
  .kpi-strip::-webkit-scrollbar { height: 4px; }
  .kpi-strip::-webkit-scrollbar-thumb { background: rgba(124, 111, 247, 0.4); border-radius: 4px; }
  .kpi-strip::-webkit-scrollbar-track { background: transparent; }
  .kpi-strip > .kpi2 {
    flex: 0 0 auto;
    width: 165px;
    scroll-snap-align: start;
    border: 1px solid var(--card-border, rgba(30, 42, 74, 0.06));
    border-radius: 11px;
    box-shadow: 0 2px 12px rgba(15, 23, 60, 0.07), 0 1px 3px rgba(15, 23, 60, 0.04);
  }
  .kpi-strip > .kpi2 .kpi2-val { font-size: 30px; }
  .kpi-strip > .kpi2 .kpi2-num { font-size: 22px; }
}
.kpi2 {
  position: relative;
  padding: clamp(15px, 1.15vw, 19px) clamp(15px, 1.2vw, 20px);
  /* Единая лента: столбец без собственной карточной обёртки — только
     непрозрачная glass-поверхность (перекрывает фон-разделитель) + акцент сверху. */
  background: var(--card-bg, rgba(255, 255, 255, 0.86));
  backdrop-filter: blur(16px) saturate(1.5);
  -webkit-backdrop-filter: blur(16px) saturate(1.5);
  border: none;
  /* Акцент-полосу сверху рисует глобальный .kpi2::before (анимированный,
     цвет из инлайнового --kpi2-accent) — свой border-top не нужен, иначе двоится. */
  border-radius: 0;
  box-shadow: none;
  display: flex;
  flex-direction: column;
  gap: clamp(4px, 0.4vw, 8px);
  min-height: clamp(98px, 7.2vw, 116px);
  overflow: hidden;
  transition: background 0.18s ease;
}

/* Pack 155c: scoped .kpi2::before override removed — global rule in
   main.css applies (drawIn + breathe + shimmer unified across the app). */

.kpi2:hover {
  background: color-mix(in srgb, var(--kpi2-accent, #7F77DD) 6%, var(--card-bg, rgba(255, 255, 255, 0.86)));
}
.kpi2.dim { opacity: 0.7; }
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

/* ─── Редизайн карточек: шапка с иконкой, мини-бары, футер ─── */
.kpi2-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 8px;
}
.kpi2-ico {
  /* Прижат к правому-верхнему углу (absolute), радиус карты ужат до 11px,
     чтобы иконка стояла близко к краю и не обрезалась overflow:hidden. */
  position: absolute;
  top: 11px; right: 11px;
  flex-shrink: 0;
  width: 30px; height: 30px;
  display: flex; align-items: center; justify-content: center;
  border-radius: 9px;
  color: var(--ico, #7F77DD);
  background: color-mix(in srgb, var(--ico, #7F77DD) 13%, transparent);
  transition: transform 0.18s var(--ease-standard);
}
.kpi2:hover .kpi2-ico { transform: scale(1.08); }
.kpi2-ico svg { width: 16px; height: 16px; }
.kpi2-mbar {
  margin-top: 6px;
  height: 4px; border-radius: 3px;
  background: rgba(15, 23, 60, 0.07);
  overflow: hidden;
}
.kpi2-mbar > span {
  display: block; height: 100%; border-radius: 3px;
  transition: width 0.7s var(--ease-standard);
}
.kpi2-foot {
  margin-top: 11px;
  font-size: 11px;
  font-weight: 500;
  color: var(--t3, #94A3B8);
  font-variant-numeric: tabular-nums;
  letter-spacing: 0.01em;
}
.fin-shimmer {
  animation: kpi2In 0.5s var(--ease-standard) backwards;
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
  background: color-mix(in srgb, var(--kpi2-accent, #7F77DD) 8%, var(--card-bg, rgba(255, 255, 255, 0.86)));
}
.kpi2-clickable:active {
  background: color-mix(in srgb, var(--kpi2-accent, #7F77DD) 12%, var(--card-bg, rgba(255, 255, 255, 0.86)));
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

/* Alert-вариант (proposal 6) — критическая метрика «Просрочено» */
.kpi2-alert {
  /* «Спокойный алерт» (Apple deference): еле заметная заливка вместо кричащего
     двойного-красного. Большие цифры — тёмные (инлайн var(--t1)); пульс-точка и
     левый бар убраны — severity сигналит красная иконка справа + полоса сверху. */
  background:
    linear-gradient(135deg, rgba(226, 75, 74, 0.05) 0%, rgba(226, 75, 74, 0.012) 100%),
    var(--card-bg, rgba(255, 255, 255, 0.82));
}

/* 3-col grid */
.three-cols {
  display: grid;
  grid-template-columns: minmax(280px, 1.1fr) minmax(360px, 1.6fr) minmax(280px, 1.1fr);
  gap: clamp(8px, 0.8vw, 14px);
  margin-bottom: clamp(10px, 1vw, 16px);
  align-items: stretch;
}
/* 13–14" (≤1440): осознанная ступень «2 в ряд», 3-й виджет — полной шириной
   (имя «по направлениям» получает 2× ширины). ≤1024 — полный стек. */
@media (max-width: 1440px) {
  .three-cols { grid-template-columns: minmax(0, 1fr) minmax(0, 1fr); }
  .three-cols > :nth-child(3) { grid-column: 1 / -1; }
}
@media (max-width: 1024px) {
  .three-cols { grid-template-columns: 1fr; }
  .three-cols > :nth-child(3) { grid-column: auto; }
}

.cc {
  /* 1:1 kit glass-карта (dark-aware) */
  background: var(--card-bg, rgba(255, 255, 255, 0.82));
  backdrop-filter: blur(16px) saturate(1.5);
  -webkit-backdrop-filter: blur(16px) saturate(1.5);
  border: 1px solid var(--card-border, rgba(30, 42, 74, 0.06));
  border-radius: 16px;
  padding: clamp(12px, 1.1vw, 18px);
  display: flex;
  flex-direction: column;
  gap: clamp(8px, 0.7vw, 12px);
  box-shadow: 0 2px 12px rgba(15, 23, 60, 0.07), 0 1px 3px rgba(15, 23, 60, 0.04);
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
  font-weight: 600;
  color: rgba(30, 42, 74, 0.55);
  text-transform: uppercase;
  letter-spacing: 0.07em;
  flex: 1;
  white-space: nowrap;
}
.cc-sub { font-size: 11px; color: var(--t3); margin-top: 2px; }
.seg-controls {
  display: flex;
  gap: 6px;
  flex-shrink: 0;
}

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
/* Канвас держим 1:1 в квадратной обёртке. Глобальный responsive.css
   `canvas{max-width:100%;height:auto}` для fixed-size chart.js (responsive:false,
   160×160) сжимал ширину, а высоту оставлял 160 → пайчарт превращался в эллипс. */
.donut-wrap canvas {
  width: 100% !important;
  height: 100% !important;
  display: block;
  aspect-ratio: 1 / 1;
}
.donut-center {
  position: absolute;
  top: 50%;
  left: 50%;
  transform: translate(-50%, -50%);
  text-align: center;
  transition: transform 0.2s var(--ease-standard, ease);
}
.donut-center.is-focus { transform: translate(-50%, -50%) scale(1.07); }
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
  color: var(--t3, var(--t3));
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
  overflow-x: hidden;
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
  padding: clamp(2px, 0.3vw, 4px) 6px;
  border-radius: 7px;
  font-size: clamp(11px, 0.88vw, 12.5px);
  color: var(--t1, #1E2A4A);
  cursor: default;
  transition: background 0.14s ease, transform 0.14s ease;
  animation: legendIn 0.42s var(--ease-standard, ease) backwards;
  animation-delay: calc(var(--si, 0) * 35ms);
}
.legend-row:hover, .legend-row.is-active { background: rgba(124, 111, 247, 0.08); }
.legend-row.is-active { transform: translateX(2px); }
.legend-row.is-active .legend-lbl { font-weight: 600; }
@keyframes legendIn {
  from { opacity: 0; transform: translateY(5px); }
  to { opacity: 1; transform: translateY(0); }
}
.legend-row.is-overdue .legend-dot { animation: legendDotPulse 1.9s ease-in-out infinite; }
@keyframes legendDotPulse {
  0%, 100% { box-shadow: 0 0 0 0 rgba(226, 75, 74, 0.5); }
  50% { box-shadow: 0 0 0 4px rgba(226, 75, 74, 0); }
}
.legend-dot {
  width: 9px;
  height: 9px;
  border-radius: 2px;
  flex-shrink: 0;
  opacity: 0.92;
}
.legend-note {
  font-size: 9px; font-weight: 500; color: var(--t4, #94A3B8);
  margin-left: 4px; letter-spacing: .02em;
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
  grid-template-columns: minmax(120px, 1.6fr) clamp(60px, 6vw, 80px) clamp(48px, 5vw, 60px) clamp(48px, 5vw, 60px);
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
  grid-template-columns: minmax(120px, 1.6fr) clamp(60px, 6vw, 80px) clamp(48px, 5vw, 60px) clamp(48px, 5vw, 60px);
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
.co-row:hover, .dir-row:hover { background: rgba(127, 119, 221, .06); }
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
/* Названия направлений не сокращаем — переносим (единый вид с CompanyOverviewExtras). */
.dir-name {
  white-space: normal;
  overflow: visible;
  text-overflow: clip;
  overflow-wrap: anywhere;
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
.co-row-clickable .co-text:hover { color: var(--p-deep); border-bottom-color: rgba(127, 119, 221, .5); }
.co-row-clickable .co-bar-wrap { cursor: pointer; padding: 4px 6px; margin: -4px -6px; border-radius: 6px; transition: background .14s ease; }
.co-row-clickable .co-bar-wrap:hover { background: rgba(127, 119, 221, .05); }
.co-num-clickable { cursor: pointer; padding: 2px 8px; border-radius: 6px; transition: background .14s ease, color .14s ease; }
.co-num-clickable:hover { background: rgba(127, 119, 221, .08); color: var(--p-deep) !important; }

/* Премиум: прогресс компании = %-число над глянцевым градиент-баром (анимация
   заливки слева→направо при загрузке, stagger по строкам сектора). */
.co-bar-wrap { flex-direction: column; align-items: stretch; justify-content: center; gap: 3px; }
.co-bar-wrap .co-pct { min-width: 0; text-align: left; }
.co-bar {
  height: 5px; border-radius: 99px;
  background: var(--surface-2, #EEF1F7);
  overflow: hidden;
}
.co-bar-fill {
  display: block; height: 100%; border-radius: 99px;
  background-color: var(--c, #7C6FF7);
  background-image: linear-gradient(180deg, rgba(255, 255, 255, .5), rgba(255, 255, 255, 0) 70%);
  transform-origin: left center;
  animation: ccBarGrow .85s cubic-bezier(.34, 1.05, .64, 1) var(--d, 0ms) both;
}
@keyframes ccBarGrow { from { transform: scaleX(0); } to { transform: scaleX(1); } }
@media (prefers-reduced-motion: reduce) { .co-bar-fill { animation: none; } }

/* ═══ Row 2: Ratings | Completion ═══ */
.two-cols { display: grid; grid-template-columns: 1fr 1fr; gap: 14px; margin-bottom: 18px; align-items: stretch; }
@media (max-width: 1400px) { .two-cols { grid-template-columns: 1fr; } }

/* Ratings card */
.rating-card { animation-delay: 360ms; }
.rings-row { display: grid; grid-template-columns: repeat(4, 1fr); gap: 10px; padding: 14px 16px; border-bottom: 1px solid var(--border1); }
/* Телефон: 4 кольца покрытия → 2-в-ряд, узкий → 1. !important перебивает компакт-оверрайды ниже. */
@media (max-width: 640px) { .rings-row { grid-template-columns: repeat(2, 1fr) !important; } }
@media (max-width: 420px) { .rings-row { grid-template-columns: 1fr !important; } }
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
  animation: uzaStripeDrawIn .4s var(--ease-standard) both;
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
