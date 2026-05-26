<script setup lang="ts">
/**
 * CompanyWorkspace.vue
 * ─────────────────────────────────────────────────────────────────
 *
 * Layout (Variant B Hero):
 *   ┌─ topbar (company name + sector badge + summary badges + year picker + actions)
 *   ├─ tabs row (Обзор / Канбан / Список / Заметки)
 *   ├─ overview content:
 *   │    ├─ HERO KPI card: 3 cols (4 ratings | progress donut 78px | stats stack)
 *   │    ├─ economic effect tile (placeholder)
 *   │    ├─ 4-col grid: directions / ranking / attention / activity (next session)
 *   │    └─ 2-col grid: KPI / business plan (next session)
 *   └─ kanban / list / notes — placeholders for next session
 *
 * UzAssets palette strict:
 *   #7F77DD purple · #1D9E75 teal · #EF9F27 amber · #378ADD blue · #E24B4A red · #1E2A4A navy
 *
 * Animations:
 *   • SVG donut: stroke-dashoffset 1.1s cubic-bezier(0.34, 1.2, 0.64, 1) delay 200ms
 *   • Counter animations via useCountUp composable on data-countup elements
 *   • Hero card: kpiCardIn .5s cubic-bezier(0.34, 1.2, 0.64, 1)
 *   • Bars: cvBarGrow .6s cubic-bezier(0.34, 1.2, 0.64, 1)
 */

import { api } from "@/api/client";
import { ref, computed, onMounted, provide, watch, nextTick } from "vue";
import { useFormatters } from "@/composables/useFormatters";

const fmt = useFormatters();
import { useRoute, useRouter, RouterLink } from "vue-router";
import { companiesApi } from "@/api/companies";
import { ratingsApi, type AgencyRatingBrief, type CompanyRatingsResponse } from "@/api/ratings";
import { projectsApi, type ProjectBrief } from "@/api/projects";
import { tasksApi, type TaskBrief } from "@/api/tasks";
import { kpiApi, bpApi, BP_FIELDS, BP_PERIODS, type KpiManager, type BpComputed, type BpPeriod, type BpFieldMeta } from "@/api/bpKpi";
import { governanceApi, ROLE_TYPE_META, type RoleType } from "@/api/governance";
import { esgApi, PILLAR_META, SEVERITY_META, ISSUE_STATUS_META, type Pillar, type Severity, type IssueStatus } from "@/api/esg";
import { consultantsApi, type ConsultantBrief, type CompanyConsultantsResponse, type CompanyConsultant } from "@/api/consultants";
import {
  getLoans,
  getAggregate as getCreditAggregate,
  CP_LENDER_LABELS,
  cpCurrencyColor,
  toNum,
  type LoanRead,
  type CreditPortfolioAggregate,
  type LenderType,
} from "@/api/credit";
import {
  procurementAnalysisApi,
  paColorByDev,
  paFmtMoneyShort,
  paFmtMoney,
  type ProcurementAggregate,
  type CompanyRatingRow,
  type ClosureRow,
  type CategoryDeviation,
} from "@/api/procurement_analysis";
import {
  financialsApi,
  type FinancialReportListItem,
  type FinancialReportFull,
  type FinancialLineEdit,
} from "@/api/financials";
import { computeProgress, EXCLUDED_FROM_PCT } from "@/utils/progress";
import CompanyNotesTab from "@/components/CompanyNotesTab.vue";
import CompanyOverviewExtras from "@/components/CompanyOverviewExtras.vue";
import CompanyDocumentsCard from "@/components/Company/CompanyDocumentsCard.vue";
import CompanyBoardList from "@/components/CompanyBoardList.vue";
import CompanyTabBar from "@/components/Company/CompanyTabBar.vue";
import { fmtCompact as fmtFinancialsCompact } from "@/components/Financials/financialsHelpers";
import InvestProjectsView from "@/views/InvestProjects.vue";
import KanbanCard from "@/components/Kanban/KanbanCard.vue";
import TaskProjectEditor from "@/components/TaskProjectEditor.vue";
import type { TaskDetail } from "@/api/tasks";
import BpEditor from "@/components/BusinessPlan/BpEditor.vue";
import KpiCompanyDashboard from "@/components/KPI/KpiCompanyDashboard.vue";
import KpiEditor from "@/components/KPI/KpiEditor.vue";
import { usePermissions } from "@/composables/usePermissions";
import { useSavedFilter } from "@/composables/useSavedFilter";

const route = useRoute();
const router = useRouter();

// =====================================================================
// Route params
// =====================================================================
const code = computed(() => String(route.params.code || route.params.id || "").toLowerCase());

// =====================================================================
// State
// =====================================================================
const company = ref<any>(null);
const sector = ref<{ id: string; code: string; name_ru: string; color_hex?: string | null } | null>(null);
const credit = ref<AgencyRatingBrief[]>([]);
const esg = ref<AgencyRatingBrief[]>([]);
// Raw all-years data — filtered client-side by `year` for instant year-switching
const allProjects = ref<ProjectBrief[]>([]);
const allTasks = ref<TaskBrief[]>([]);

// KPI state — lazy loaded when KPI tab opened
const kpiManagers = ref<KpiManager[]>([]);
const kpiLoading = ref(false);
const kpiError = ref<string | null>(null);
const kpiLoadedFor = ref<string>("");  // cache key "{company_id}:{year}"
// Pack: workspace KPI redesign — reuse KpiCompanyDashboard + KpiEditor.
// Default period = q1 потому что fact_year почти не заполнен по портфелю
// (0.16%), а q1 — 68% покрытие. См. KPI-аудит 2026-05-23.
type WsKpiPeriod = "annual" | "q1" | "q2" | "q3" | "q4";
const kpiPeriod = useSavedFilter<WsKpiPeriod>("workspace.kpi.period", "q1");
const activeKpiMgrIdx = ref(0);
const kpiEditorOpen = ref(false);
const kpiPerm = usePermissions("kpi");
function openKpiEditor() { kpiEditorOpen.value = true; }
function onKpiEditorSaved() {
  kpiEditorOpen.value = false;
  kpiLoadedFor.value = "";  // invalidate cache so loadKpi() refetches
  loadKpi();
}

// BP state — lazy loaded when БП tab opened
const bpData = ref<BpComputed | null>(null);
const bpLoading = ref(false);
const bpError = ref<string | null>(null);
const bpPeriod = ref<BpPeriod>("annual");
const bpLoadedFor = ref<string>("");  // cache key "{company_id}:{year}:{period}"
const bpEditorOpen = ref(false);
const bpPerm = usePermissions("bp");
function openBpEditor() { bpEditorOpen.value = true; }
function onBpEditorSaved() {
  bpEditorOpen.value = false;
  bpLoadedFor.value = "";  // invalidate cache so loadBp() refetches
  loadBp();
}

// Governance state
const govDetail = ref<any>(null);  // GovernanceCompanyDetail (defensive any since shape varies)
const govMembers = ref<any[]>([]);
const govLoading = ref(false);
const govError = ref<string | null>(null);
const govLoadedFor = ref<string>("");

// ESG state
const esgDetail = ref<any>(null);  // ESGCompanyDetail
const esgIssues = ref<any[]>([]);
const esgLoading = ref(false);
const esgError = ref<string | null>(null);
const esgLoadedFor = ref<string>("");

// Consultants — TWO data sources:
//   1) Per-company (primary view)  via byCompany(id, year)
//   2) Global directory (collapsible secondary)  via list()
const consPerCompany = ref<CompanyConsultantsResponse | null>(null);
const consPerCompanyLoading = ref(false);
const consPerCompanyError = ref<string | null>(null);
const consPerCompanyLoadedFor = ref<string>("");  // "{companyId}:{year}"

const consDirectory = ref<ConsultantBrief[]>([]);
const consDirectoryLoading = ref(false);
const consDirectoryError = ref<string | null>(null);
const consDirectoryLoaded = ref(false);
const consDirectoryExpanded = ref(false);  // collapsible toggle

// Legacy state (kept temporarily for backward compat — not used in template anymore)
const consultantsList = ref<ConsultantBrief[]>([]);
const consultantsLoading = ref(false);
const consultantsError = ref<string | null>(null);
const consultantsLoaded = ref(false);

// Credit portfolio state
const creditLoans = ref<LoanRead[]>([]);
const creditAggregate = ref<CreditPortfolioAggregate | null>(null);
const creditLoading = ref(false);
const creditError = ref<string | null>(null);
const creditLoadedFor = ref<string>("");

// Procurement state
const procData = ref<ProcurementAggregate | null>(null);
const procLoading = ref(false);
const procError = ref<string | null>(null);
const procLoadedFor = ref<string>("");

// Financials (МСФО + НСБУ — same code, different standard value)
const finReports = ref<FinancialReportListItem[]>([]);
const finFullReport = ref<FinancialReportFull | null>(null);
const finReportType = ref<"PL" | "BS" | "CF">("PL");
const finLoading = ref(false);
const finFullLoading = ref(false);
const finError = ref<string | null>(null);
const finLoadedFor = ref<string>("");  // companyCode:year:standard

const year = ref<number>(2026);
const VALID_TABS = ["overview", "kanban", "list", "notes",
                    "ifrs", "nsbu", "bp", "credit", "invest",
                    "kpi", "procurement",
                    "governance", "consultants", "esg"] as const;
type TabKey = typeof VALID_TABS[number];

// URL-state: ?tab=kanban etc. Default = overview.
const activeTab = computed<TabKey>({
  get: () => {
    const t = String(route.query.tab || "");
    return (VALID_TABS as readonly string[]).includes(t) ? (t as TabKey) : "overview";
  },
  set: (val: TabKey) => {
    const newQuery = { ...route.query };
    if (val === "overview") delete newQuery.tab;
    else newQuery.tab = val;
    router.replace({ path: route.path, query: newQuery });
  },
});

interface TabDef {
  key: TabKey;
  label: string;
  group: "manage" | "finance" | "ops" | "strategy";
  /** Optional: route to "full version" page if this tab is a placeholder/CTA */
  fullPageRoute?: string;
}

const TABS: TabDef[] = [
  // Управление
  { key: "overview",    label: "Обзор",        group: "manage" },
  { key: "kanban",      label: "Канбан",       group: "manage" },
  { key: "list",        label: "Список",       group: "manage" },
  { key: "notes",       label: "Заметки",      group: "manage" },
  // Финансы
  { key: "ifrs",        label: "МСФО",         group: "finance",  fullPageRoute: "/financials" },
  { key: "nsbu",        label: "НСБУ",         group: "finance",  fullPageRoute: "/financials" },
  { key: "bp",          label: "Бизнес-план",  group: "finance",  fullPageRoute: "/business-plan" },
  // Hidden per user request 2026-05-25 — раскомментировать для возврата
  // { key: "credit",      label: "Кредит",       group: "finance",  fullPageRoute: "/credit-portfolio" },
  // { key: "invest",      label: "Инвест-проекты", group: "finance", fullPageRoute: "/invest-projects" },
  // Операции
  { key: "kpi",         label: "KPI",          group: "ops",      fullPageRoute: "/kpi" },
  { key: "procurement", label: "Закупки",      group: "ops",      fullPageRoute: "/procurement/analysis" },
  // Стратегия
  { key: "governance",  label: "Корп. упр.",   group: "strategy", fullPageRoute: "/governance" },
  { key: "consultants", label: "Консультанты", group: "strategy", fullPageRoute: "/consultants" },
  { key: "esg",         label: "ESG",          group: "strategy", fullPageRoute: "/esg" },
];

const tabsByGroup = computed(() => {
  const groups = ["manage", "finance", "ops", "strategy"] as const;
  return groups.map(g => ({ id: g, tabs: TABS.filter(t => t.group === g) }));
});

const currentTabDef = computed(() => TABS.find(t => t.key === activeTab.value));

const loading = ref(true);
const error = ref<string | null>(null);
const refreshing = ref(false);

// =====================================================================
// Lifecycle
// =====================================================================
async function loadAll() {
  loading.value = true;
  refreshing.value = true;
  error.value = null;
  try {
    // Step 1: company by code (need its UUID for projects/tasks)
    const c = await companiesApi.getOne(code.value);
    company.value = c;
    sector.value = (c as any).sector || null;

    // Step 2: parallel fetch — without year filter (we filter client-side for instant year switching)
    const [ratResp, projResp, taskResp] = await Promise.allSettled([
      ratingsApi.getCompanyRatings(code.value),
      projectsApi.list({ company_id: c.id, limit: 500 }),
      tasksApi.list({ company_id: c.id }),
    ]);

    if (ratResp.status === "fulfilled") {
      credit.value = ratResp.value.credit || [];
      esg.value = ratResp.value.esg || [];
    }
    if (projResp.status === "fulfilled") {
      allProjects.value = (projResp.value as any).items || [];
    }
    if (taskResp.status === "fulfilled") {
      allTasks.value = (taskResp.value as any).items || [];
    }
  } catch (e: any) {
    error.value = e?.response?.status === 404
      ? `Компания «${code.value}» не найдена`
      : (e?.response?.data?.detail || e?.message || "Не удалось загрузить компанию");
  } finally {
    loading.value = false;
    setTimeout(() => { refreshing.value = false; }, 600);
  }
}

// Triggers the tab-specific loader for the currently-active tab. Necessary on
// initial mount and after company change, since activeTab is a URL-derived
// computed and the watcher on it fires only on CHANGE — not initial.
function loadActiveTab() {
  const t = activeTab.value;
  if (t === "kpi") loadKpi();
  else if (t === "bp") loadBp();
  else if (t === "governance") loadGovernance();
  else if (t === "esg") loadEsg();
  else if (t === "consultants") loadConsultantsPerCompany();
  else if (t === "credit") loadCredit();
  else if (t === "procurement") loadProc();
  else if (t === "ifrs" || t === "nsbu") loadFinReports();
}

onMounted(() => {
  loadAll().then(() => {
    nextTick(() => animateCounters());
    loadTopFinSnapshot();
    loadActiveTab();
  });
});
// Year change is INSTANT — only re-animate counters, no re-fetch
watch(code, () => {
  topFinSnapshotLoadedFor.value = null;  // company change → reset dedup key
  // company change → reset all per-tab dedup keys so refetch happens
  kpiLoadedFor.value = "";
  bpLoadedFor.value = "";
  govLoadedFor.value = "";
  esgLoadedFor.value = "";
  consPerCompanyLoadedFor.value = "";
  procLoadedFor.value = "";
  finLoadedFor.value = "";
  creditLoadedFor.value = "";
  loadAll().then(() => {
    nextTick(() => animateCounters());
    loadTopFinSnapshot();
    loadActiveTab();
  });
});
watch(year, () => {
  nextTick(() => animateCounters());
  loadTopFinSnapshot();
});

// =====================================================================
// =====================================================================
function animateCounters() {
  // Sprint C · Scan the WHOLE workspace shell, not just overview. data-countup
  // numbers in topbar / financial KPI strip / maturity ladder / supplier
  // concentration / etc. all animate on each load.
  const root = document.querySelector(".cw-shell") || document.querySelector(".cw-overview-scroll");
  if (!root) return;
  const elements = root.querySelectorAll<HTMLElement>("[data-countup]");
  elements.forEach((el) => {
    const target = parseFloat(el.dataset.countup || "0");
    const decimals = parseInt(el.dataset.cuD || "0", 10);
    if (isNaN(target)) return;
    const duration = 800;
    const startTs = performance.now();
    const initial = parseFloat((el.textContent || "0").replace(/[^\d.\-]/g, "")) || 0;
    function step(now: number) {
      const t = Math.min(1, (now - startTs) / duration);
      const eased = 1 - Math.pow(1 - t, 3);
      const value = initial + (target - initial) * eased;
      el.textContent = decimals > 0 ? value.toFixed(decimals) : Math.round(value).toString();
      if (t < 1) requestAnimationFrame(step);
    }
    requestAnimationFrame(step);
  });
}

// =====================================================================
// =====================================================================

function isOverdue(due: string | null | undefined): boolean {
  if (!due) return false;
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  const d = new Date(due);
  return d < today;
}

function isExcludedStatus(status: string): boolean {
  return EXCLUDED_FROM_PCT.has(status);
}

const projItems = computed(() =>
  allProjects.value.filter(p => (p as any).portfolio_year === year.value)
);
const taskItems = computed(() =>
  allTasks.value.filter(t =>
    (t as any).portfolio_year === year.value && !t.is_project
  )
);

// Available years from data (for year picker bounds)
const availableYearsFromData = computed(() => {
  const set = new Set<number>();
  allProjects.value.forEach(p => (p as any).portfolio_year && set.add((p as any).portfolio_year));
  allTasks.value.forEach(t => (t as any).portfolio_year && set.add((t as any).portfolio_year));
  return Array.from(set).sort();
});

// =====================================================================
// Kanban helpers — group tasks by status
// =====================================================================

interface KanbanColumn {
  id: string;
  label: string;
  color: string;
  bgAccent: string;
  tasks: TaskBrief[];
}

const KANBAN_STATUSES: { id: string; label: string; color: string; bgAccent: string }[] = [
  { id: "init",   label: "Инициирование",  color: "#64748B", bgAccent: "#E2E8F0" },
  { id: "new",    label: "Не начато",      color: "#94A3B8", bgAccent: "#F1F5F9" },
  { id: "active", label: "В процессе",     color: "#3B82F6", bgAccent: "rgba(55,138,221,.10)" },
  { id: "review", label: "На согласовании", color: "#F59E0B", bgAccent: "#FEF9C3" },
  { id: "done",   label: "Завершено",      color: "#10B981", bgAccent: "#D1FAE5" },
];

const kanbanColumns = computed<KanbanColumn[]>(() => {
  return KANBAN_STATUSES.map(s => ({
    ...s,
    tasks: taskItems.value.filter(t => t.status === s.id),
  }));
});

const recurringTasks = computed(() =>
  taskItems.value.filter(t => t.status === "quarterly" || t.status === "monthly" || t.status === "ongoing")
);

// Просрочено колонка (status != done, isOverdue, not recurring)
const overdueTasks = computed(() =>
  taskItems.value
    .filter(t => t.status !== "done" && !["quarterly", "monthly", "ongoing"].includes(t.status) && isOverdueTask(t))
    .sort((a, b) => new Date(a.due_date || 0).getTime() - new Date(b.due_date || 0).getTime())
);

function priorityClass(p: string | null | undefined): string {
  if (p === "high") return "kc-prio-h";
  if (p === "medium") return "kc-prio-m";
  if (p === "low") return "kc-prio-l";
  return "kc-prio-n";
}
function priorityLabel(p: string | null | undefined): string {
  if (p === "high") return "Высокий";
  if (p === "medium") return "Средний";
  if (p === "low") return "Низкий";
  return "Без приоритета";
}

// Assignee avatar color (deterministic from name hash)
const _AV_COLORS = ["#5B8DEF", "#34A853", "#D97706", "#AF52DE", "#00BCD4", "#E67E22", "#1ABC9C", "#8E44AD", "#2ECC71", "#3498DB"];
function avatarColor(name: string | null | undefined): string {
  if (!name) return _AV_COLORS[0];
  let h = 0;
  for (let i = 0; i < name.length; i++) h = (h * 31 + name.charCodeAt(i)) | 0;
  return _AV_COLORS[Math.abs(h) % _AV_COLORS.length];
}
function avatarInitials(name: string | null | undefined): string {
  if (!name) return "?";
  return name.split(/\s+/).map(w => w[0] || "").join("").slice(0, 2).toUpperCase();
}

// Consultant codes from t.consultant (string | array | null)
function taskConsultantCodes(t: any): string[] {
  const c = t.consultant;
  if (!c) return [];
  if (Array.isArray(c)) return c.slice(0, 2).map((x: any) => String(x));
  return [String(c)];
}

const _DIRS_META: Record<string, { label: string; color: string }> = {
  strategy:    { label: "Стратегическое управление",  color: "#1e2787" },
  finance:     { label: "Финансы / риски / аудит",    color: "#D97706" },
  procurement: { label: "Система закупок",            color: "#3B6D11" },
  orgdev:      { label: "Организационное развитие",   color: "#534AB7" },
  digital:     { label: "Цифровизация",               color: "#1D9E75" },
  operations:  { label: "Операционная эффективность", color: "#EF4444" },
  governance:  { label: "Корпоративное управление",   color: "#72243E" },
  esg:         { label: "ESG",                        color: "#1D9E75" },
  pr:          { label: "Связи с общественностью",    color: "#D4537E" },
  pmo:         { label: "PMO",                        color: "#2563EB" },
  analytics:   { label: "Сводный отдел",              color: "#7C3AED" },
};
function dirMeta(direction: string | null | undefined): { label: string; color: string } | null {
  if (!direction) return null;
  return _DIRS_META[String(direction).toLowerCase()] || null;
}

// Date for kanban card: short format dd.mm.yyyy → returns via fmt
function fmtCardDate(s: string | null | undefined): string {
  if (!s) return "";
  return fmt.fmtDateNumeric(s);
}

function isQuarterlyAllDone(t: any): boolean {
  const q = t.quarters;
  if (!q) return false;
  return !!(q.q1 && q.q2 && q.q3 && q.q4);
}
function quarterlyDoneCount(t: any): number {
  const q = t.quarters;
  if (!q) return 0;
  return ["q1", "q2", "q3", "q4"].filter(k => q[k]).length;
}

// =====================================================================
// List view helpers
// =====================================================================

const listFilter = ref<{ direction: string; status: string }>({ direction: "", status: "" });

const projectsForList = computed(() => {
  let items = projItems.value as any[];
  if (listFilter.value.direction) {
    items = items.filter(p => p.direction === listFilter.value.direction);
  }
  if (listFilter.value.status) {
    items = items.filter(p => p.status === listFilter.value.status);
  }
  return items;
});

function getStatusLabel(s: string): string {
  const found = KANBAN_STATUSES.find(x => x.id === s);
  if (found) return found.label;
  if (s === "quarterly") return "Ежеквартально";
  if (s === "monthly") return "Ежемесячно";
  if (s === "ongoing") return "Постоянно";
  return s;
}

function getStatusColor(s: string): string {
  const found = KANBAN_STATUSES.find(x => x.id === s);
  if (found) return found.color;
  return "#7E22CE"; // recurring
}

function fmtDate(d: string | null | undefined): string {
  if (!d) return "—";
  const date = new Date(d);
  if (isNaN(date.getTime())) return "—";
  return date.toLocaleDateString("ru-RU", { day: "2-digit", month: "short", year: "numeric" });
}

function isOverdueTask(t: any): boolean {
  return t.status !== "done" && isOverdue(t.due_date) && !isExcludedStatus(t.status);
}

// =====================================================================
// CTA icon SVG paths (rendered inline via v-html safely as path strings)
// =====================================================================
const ICON_PATHS: Record<string, string> = {
  ifrs:        '<rect x="3" y="3" width="18" height="4" rx="1"/><rect x="3" y="11" width="18" height="4" rx="1"/><rect x="3" y="19" width="18" height="2" rx="1"/>',
  nsbu:        '<rect x="3" y="3" width="18" height="4" rx="1"/><rect x="3" y="11" width="18" height="4" rx="1"/><rect x="3" y="19" width="18" height="2" rx="1"/>',
  bp:          '<path d="M3 3v18h18"/><path d="M7 14l4-4 4 4 5-5"/>',
  credit:      '<rect x="2" y="5" width="20" height="14" rx="2"/><path d="M2 10h20"/>',
  kpi:         '<circle cx="12" cy="12" r="10"/><path d="M12 6v6l4 2"/>',
  procurement: '<circle cx="9" cy="21" r="1"/><circle cx="20" cy="21" r="1"/><path d="M1 1h4l2.7 13.4a2 2 0 0 0 2 1.6h9.7a2 2 0 0 0 2-1.6L23 6H6"/>',
  governance:  '<path d="M3 21V7l9-4 9 4v14"/><path d="M9 21V12h6v9"/>',
  consultants: '<circle cx="9" cy="7" r="4"/><path d="M3 21v-2a4 4 0 0 1 4-4h4a4 4 0 0 1 4 4v2"/><circle cx="17" cy="7" r="3"/>',
  esg:         '<path d="M12 2L2 22h20L12 2z"/><path d="M12 8v6"/><circle cx="12" cy="18" r="0.5"/>',
};

function getIconPath(key: string): string {
  return ICON_PATHS[key] || ICON_PATHS.ifrs;
}

// =====================================================================
// Lazy loaders for KPI & Business Plan
// =====================================================================

// Sprint B · Prior-year baseline cache (rendered as gray reference when current year has no facts)
const kpiBaselineManagers = ref<any[]>([]);
const kpiBaselineYear = ref<number | null>(null);

async function loadKpi() {
  if (!company.value) return;
  const key = `${company.value.id}:${year.value}`;
  if (kpiLoadedFor.value === key) return;  // cache hit
  kpiLoading.value = true;
  kpiError.value = null;
  kpiBaselineManagers.value = [];
  kpiBaselineYear.value = null;
  try {
    const loaded = await kpiApi.getCompanyYear(company.value.id, year.value);
    const data = loaded.managers;
    kpiManagers.value = data || [];
    kpiLoadedFor.value = key;

    // Sprint B · Prior-year fallback: if no manager has any fact in current year,
    // fetch last year's data and expose as kpiBaseline* so template renders it
    // as a gray reference column under each indicator.
    const anyFact = (data || []).some((mgr: any) =>
      (mgr.indicators || []).some((ind: any) => {
        const f = ind.fact_year;
        const p = ind.plan_year;
        const fn = typeof f === "string" ? parseFloat(f) : (f as number | null);
        const pn = typeof p === "string" ? parseFloat(p) : (p as number | null);
        return fn != null && !Number.isNaN(fn) && pn != null && pn !== 0;
      })
    );
    if (!anyFact) {
      const prevYear = year.value - 1;
      try {
        const prev = (await kpiApi.getCompanyYear(company.value.id, prevYear)).managers;
        kpiBaselineManagers.value = prev || [];
        kpiBaselineYear.value = prevYear;
      } catch {
        kpiBaselineManagers.value = [];
        kpiBaselineYear.value = null;
      }
    }
  } catch (e: any) {
    kpiError.value = e?.response?.data?.detail || e?.message || "Не удалось загрузить KPI";
    kpiManagers.value = [];
  } finally {
    kpiLoading.value = false;
  }
}

// Map of {managerId → {indicatorName → prev_year_fact}} for quick template lookup
const kpiBaselineIndex = computed<Record<string, Record<string, { fact: number | null; plan: number | null }>>>(() => {
  const out: Record<string, Record<string, { fact: number | null; plan: number | null }>> = {};
  kpiBaselineManagers.value.forEach((mgr: any) => {
    out[String(mgr.id)] = {};
    (mgr.indicators || []).forEach((ind: any) => {
      const f = ind.fact_year;
      const p = ind.plan_year;
      out[String(mgr.id)][ind.name || ""] = {
        fact: f == null ? null : (typeof f === "string" ? parseFloat(f) : Number(f)),
        plan: p == null ? null : (typeof p === "string" ? parseFloat(p) : Number(p)),
      };
    });
  });
  return out;
});

async function loadBp() {
  if (!company.value) return;
  const key = `${company.value.id}:${year.value}:${bpPeriod.value}`;
  if (bpLoadedFor.value === key) return;
  bpLoading.value = true;
  bpError.value = null;
  try {
    const data = await bpApi.getComputed(company.value.id, year.value, bpPeriod.value);
    bpData.value = data;
    bpLoadedFor.value = key;
  } catch (e: any) {
    bpError.value = e?.response?.data?.detail || e?.message || "Не удалось загрузить Бизнес-план";
    bpData.value = null;
  } finally {
    bpLoading.value = false;
  }
}

async function loadGovernance() {
  if (!company.value) return;
  const key = `${company.value.id}:${year.value}`;
  if (govLoadedFor.value === key) return;
  govLoading.value = true;
  govError.value = null;
  try {
    const [detail, members] = await Promise.all([
      governanceApi.getCompanyDetail(company.value.id, year.value).catch(() => null),
      governanceApi.listMembers(company.value.id, false).catch(() => []),
    ]);
    govDetail.value = detail;
    govMembers.value = Array.isArray(members) ? members : [];
    govLoadedFor.value = key;
  } catch (e: any) {
    govError.value = e?.response?.data?.detail || e?.message || "Не удалось загрузить Корп. управление";
  } finally {
    govLoading.value = false;
  }
}

// Sprint C · Sector benchmark — pillar-level sector averages for comparison
const esgSectorPillars = ref<Record<string, { avgAttainment: number | null; companyCount: number }>>({});
const esgSectorLabel = ref<string | null>(null);

async function loadEsg() {
  if (!company.value) return;
  const key = `${company.value.id}:${year.value}`;
  if (esgLoadedFor.value === key) return;
  esgLoading.value = true;
  esgError.value = null;
  esgSectorPillars.value = {};
  esgSectorLabel.value = null;
  try {
    const sectorCode = (sector.value as any)?.code || null;
    const [detail, issues, overview] = await Promise.all([
      esgApi.getCompanyDetail(company.value.id, year.value).catch(() => null),
      esgApi.listIssues({ company_id: company.value.id }).catch(() => []),
      sectorCode
        ? esgApi.getOverview({ year: year.value, sector_code: sectorCode }).catch(() => null)
        : Promise.resolve(null),
    ]);
    esgDetail.value = detail;
    esgIssues.value = Array.isArray(issues) ? issues : (issues as any)?.items || [];

    // Sector pillar benchmarks
    if (overview && overview.pillars) {
      const map: Record<string, { avgAttainment: number | null; companyCount: number }> = {};
      overview.pillars.forEach((p: any) => {
        map[p.pillar] = {
          avgAttainment: p.avg_target_attainment != null ? Math.round(p.avg_target_attainment * 100) : null,
          companyCount: p.company_count || 0,
        };
      });
      esgSectorPillars.value = map;
      esgSectorLabel.value = (sector.value as any)?.name_ru || "сектору";
    }

    esgLoadedFor.value = key;
  } catch (e: any) {
    esgError.value = e?.response?.data?.detail || e?.message || "Не удалось загрузить ESG";
  } finally {
    esgLoading.value = false;
  }
}

async function loadConsultantsPerCompany() {
  if (!company.value) return;
  const key = `${company.value.id}:${year.value}`;
  if (consPerCompanyLoadedFor.value === key) return;
  consPerCompanyLoading.value = true;
  consPerCompanyError.value = null;
  try {
    consPerCompany.value = await consultantsApi.byCompany(company.value.id, year.value);
    consPerCompanyLoadedFor.value = key;
  } catch (e: any) {
    consPerCompanyError.value = e?.response?.data?.detail || e?.message || "Не удалось загрузить консультантов компании";
    consPerCompany.value = null;
  } finally {
    consPerCompanyLoading.value = false;
  }
}

async function loadConsultantsDirectory() {
  if (consDirectoryLoaded.value) return;
  consDirectoryLoading.value = true;
  consDirectoryError.value = null;
  try {
    consDirectory.value = await consultantsApi.list();
    consDirectoryLoaded.value = true;
  } catch (e: any) {
    consDirectoryError.value = e?.response?.data?.detail || e?.message || "Не удалось загрузить справочник";
  } finally {
    consDirectoryLoading.value = false;
  }
}

function toggleConsDirectory() {
  consDirectoryExpanded.value = !consDirectoryExpanded.value;
  if (consDirectoryExpanded.value && !consDirectoryLoaded.value) {
    loadConsultantsDirectory();
  }
}

// Legacy alias — kept for compatibility (unused after this refactor)
async function loadConsultants() {
  await loadConsultantsPerCompany();
}

// =====================================================================
// Credit + Procurement loaders
// =====================================================================

async function loadCredit() {
  if (!company.value) return;
  const key = company.value.id;
  if (creditLoadedFor.value === key) return;
  creditLoading.value = true;
  creditError.value = null;
  try {
    const [loans, aggregate] = await Promise.all([
      getLoans({ company_id: company.value.id }),
      getCreditAggregate({ company_id: company.value.id }).catch(() => null),
    ]);
    creditLoans.value = (loans || []).filter(l => !l.deleted_at);
    creditAggregate.value = aggregate;
    creditLoadedFor.value = key;
  } catch (e: any) {
    creditError.value = e?.response?.data?.detail || e?.message || "Не удалось загрузить кредитный портфель";
    creditLoans.value = [];
    creditAggregate.value = null;
  } finally {
    creditLoading.value = false;
  }
}

async function loadProc() {
  if (!company.value) return;
  const key = `${company.value.id}:${year.value}`;
  if (procLoadedFor.value === key) return;
  procLoading.value = true;
  procError.value = null;
  try {
    procData.value = await procurementAnalysisApi.getAggregate({
      company_id: company.value.id,
      year: year.value,
    });
    procLoadedFor.value = key;
  } catch (e: any) {
    procError.value = e?.response?.data?.detail || e?.message || "Не удалось загрузить закупки";
    procData.value = null;
  } finally {
    procLoading.value = false;
  }
}

// =====================================================================
// Financials loaders (МСФО + НСБУ — both use same logic, different standard)
// =====================================================================

const financialsStandard = computed<"IFRS" | "NSBU">(() =>
  activeTab.value === "nsbu" ? "NSBU" : "IFRS"
);

// Cache of full reports per type, populated after loadFinReports for KPI-strip.
const finFullByType = ref<Record<string, FinancialReportFull>>({});

async function loadFinReports() {
  if (!company.value) return;
  const std = financialsStandard.value;
  const cCode = (company.value as any).code || "";
  if (!cCode) return;
  const key = `${cCode}:${year.value}:${std}`;
  if (finLoadedFor.value === key) return;
  finLoading.value = true;
  finError.value = null;
  finFullReport.value = null;
  finFullByType.value = {};
  try {
    const list = await financialsApi.list({
      company_code: cCode,
      year: year.value,
      standard: std,
    });
    finReports.value = list || [];
    finLoadedFor.value = key;

    if (list && list.length > 0) {
      // Eager-fetch PL + BS in parallel so KPI-strip has all line codes ready
      const toFetch = list.filter(r => r.report_type === "PL" || r.report_type === "BS");
      const fetched = await Promise.allSettled(toFetch.map(r => financialsApi.get(r.id)));
      const byType: Record<string, FinancialReportFull> = {};
      fetched.forEach((f, i) => {
        if (f.status === "fulfilled" && f.value) {
          byType[toFetch[i].report_type] = f.value;
        }
      });
      finFullByType.value = byType;

      // Auto-select user's preferred report for the table view
      const preferred = list.find(r => r.report_type === finReportType.value) || list[0];
      finReportType.value = preferred.report_type as any;
      // Reuse eager-fetched copy if available, otherwise hit API
      if (byType[preferred.report_type]) {
        finFullReport.value = byType[preferred.report_type];
      } else {
        await loadFinFullReport(preferred.id);
      }
    }
  } catch (e: any) {
    finError.value = e?.response?.data?.detail || e?.message || "Не удалось загрузить отчётность";
    finReports.value = [];
  } finally {
    finLoading.value = false;
  }
}

async function loadFinFullReport(reportId: string) {
  finFullLoading.value = true;
  try {
    finFullReport.value = await financialsApi.get(reportId);
  } catch (e: any) {
    finError.value = e?.response?.data?.detail || e?.message || "Не удалось загрузить отчёт";
    finFullReport.value = null;
  } finally {
    finFullLoading.value = false;
  }
}

function selectFinReportType(type: "PL" | "BS" | "CF") {
  finReportType.value = type;
  // Use eager-fetched copy if available (PL + BS); otherwise hit API for CF
  if (finFullByType.value[type]) {
    finFullReport.value = finFullByType.value[type];
    return;
  }
  const r = finReports.value.find(x => x.report_type === type);
  if (r) loadFinFullReport(r.id);
}

// =====================================================================
// Financial KPI-strip (Sprint A · MSFO/NSBU summary tiles)
// =====================================================================
// Pulls Revenue/EBITDA/NetProfit from PL and Equity/Debt/TotalAssets from BS,
// then computes ratios. Y/Y comes from `prev_year_value` column on each line.

interface FinKpi {
  key: string;
  label: string;
  value: number | null;
  prev: number | null;       // previous-year absolute value
  unit: string;              // "млн UZS" / "%" / "x"
  tone: "info" | "good" | "warn" | "bad";
  hint?: string;             // small footnote (margin / ratio context)
}

function _lineValue(report: FinancialReportFull | undefined, codes: string[]): { v: number | null; prev: number | null } {
  if (!report) return { v: null, prev: null };
  for (const code of codes) {
    const ln = report.lines.find(l => l.line_code === code);
    if (!ln) continue;
    const v = typeof ln.value === "string" ? parseFloat(ln.value) : (ln.value as number | null);
    const prev = (ln as any).prev_year_value;
    const pv = prev == null ? null : (typeof prev === "string" ? parseFloat(prev) : Number(prev));
    return {
      v: (v == null || Number.isNaN(v)) ? null : v,
      prev: (pv == null || Number.isNaN(pv)) ? null : pv,
    };
  }
  return { v: null, prev: null };
}

function _scaleFactor(report: FinancialReportFull | undefined): number {
  // Reports store values pre-scaled by unit_scale. To get raw UZS multiply by it.
  return report?.unit_scale && report.unit_scale > 0 ? report.unit_scale : 1;
}

const finKpis = computed<FinKpi[]>(() => {
  const pl = finFullByType.value["PL"];
  const bs = finFullByType.value["BS"];
  if (!pl && !bs) return [];

  // unit_scale is intentionally ignored — stored values are already in млрд UZS
  // (Firebase migration set unit_scale=1000 by mistake on legacy rows). The
  // standalone /financials view uses the same convention.

  // PL — revenue / EBITDA / NetProfit
  const rev    = _lineValue(pl, ["revenue", "выручка", "net_revenue"]);
  const ebitda = _lineValue(pl, ["ebitda", "EBITDA"]);
  const np     = _lineValue(pl, ["profit", "net_profit", "profit_for_the_year", "netProfit"]);

  // BS — equity / debt / total assets
  const eq     = _lineValue(bs, ["equity", "total_equity", "totalEquity"]);
  const debt   = _lineValue(bs, ["debt", "totalDebt", "total_debt", "interestBearingDebt"]);
  const ta     = _lineValue(bs, ["totalAssets", "total_assets"]);

  const out: FinKpi[] = [];

  // 1) Revenue
  if (rev.v != null) {
    const yoy = rev.prev != null && rev.prev !== 0 ? ((rev.v - rev.prev) / Math.abs(rev.prev)) * 100 : null;
    out.push({
      key: "revenue",
      label: "Выручка",
      value: rev.v,
      prev: rev.prev,
      unit: pl?.currency || "UZS",
      tone: "info",
      hint: yoy != null ? `${yoy >= 0 ? "▲" : "▼"} ${fmt.fmtPercent(Math.abs(yoy), { decimals: 1 })} Y/Y` : "",
    });
  }

  // 2) EBITDA + margin
  if (ebitda.v != null) {
    const margin = rev.v && rev.v !== 0 ? (ebitda.v / rev.v) * 100 : null;
    out.push({
      key: "ebitda",
      label: "EBITDA",
      value: ebitda.v,
      prev: ebitda.prev,
      unit: pl?.currency || "UZS",
      tone: ebitda.v < 0 ? "bad" : "good",
      hint: margin != null ? `margin ${fmt.fmtPercent(margin, { decimals: 1 })}` : "",
    });
  }

  // 3) Net profit + margin
  if (np.v != null) {
    const margin = rev.v && rev.v !== 0 ? (np.v / rev.v) * 100 : null;
    out.push({
      key: "net_profit",
      label: "Чистая прибыль",
      value: np.v,
      prev: np.prev,
      unit: pl?.currency || "UZS",
      tone: np.v < 0 ? "bad" : (np.v > 0 ? "good" : "warn"),
      hint: margin != null ? `margin ${fmt.fmtPercent(margin, { decimals: 1 })}` : "",
    });
  }

  // 4) ROE = NetProfit / Equity (units cancel out)
  if (np.v != null && eq.v != null && eq.v !== 0) {
    const roe = (np.v / eq.v) * 100;
    out.push({
      key: "roe",
      label: "ROE",
      value: roe,
      prev: null,
      unit: "%",
      tone: roe >= 15 ? "good" : roe >= 5 ? "info" : (roe < 0 ? "bad" : "warn"),
      hint: "доходность капитала",
    });
  }

  // 5) ROA = NetProfit / TotalAssets (units cancel out)
  if (np.v != null && ta.v != null && ta.v !== 0) {
    const roa = (np.v / ta.v) * 100;
    out.push({
      key: "roa",
      label: "ROA",
      value: roa,
      prev: null,
      unit: "%",
      tone: roa >= 5 ? "good" : roa >= 1 ? "info" : (roa < 0 ? "bad" : "warn"),
      hint: "доходность активов",
    });
  }

  // 6) Debt/Equity (same units → ratio is dimensionless)
  if (debt.v != null && eq.v != null && eq.v !== 0) {
    const de = debt.v / eq.v;
    out.push({
      key: "de",
      label: "Debt / Equity",
      value: de,
      prev: null,
      unit: "x",
      tone: de <= 0.5 ? "good" : de <= 1.5 ? "info" : (de <= 2.5 ? "warn" : "bad"),
      hint: "леверидж",
    });
  }

  // 7) Equity ratio = Equity / TotalAssets
  if (eq.v != null && ta.v != null && ta.v !== 0) {
    const er = (eq.v / ta.v) * 100;
    out.push({
      key: "er",
      label: "Equity ratio",
      value: er,
      prev: null,
      unit: "%",
      tone: er >= 40 ? "good" : er >= 25 ? "info" : (er >= 10 ? "warn" : "bad"),
      hint: "доля собственного капитала",
    });
  }

  return out;
});

// Display values as-is, in млрд UZS (the canonical unit used by the standalone
// /financials view per "Единицы: млрд сум"). Stored values for NGMK etc.
// already encode billions — the Firebase migration set unit_scale=1000 by
// mistake, so we intentionally ignore unit_scale here for display.
// Format: NBSP thousands separator, comma decimal separator. Integer when
// the magnitude ≥ 1, 2 decimals when between 0 and 1.
function fmtBlnValue(v: number | null | undefined): string {
  if (v == null || Number.isNaN(v)) return "—";
  if (v === 0) return "0";
  const abs = Math.abs(v);
  const rounded = abs < 1 ? v.toFixed(2) : Math.round(v).toString();
  const parts = rounded.split(".");
  parts[0] = parts[0].replace(/\B(?=(\d{3})+(?!\d))/g, " ");
  return parts.join(",");
}

function fmtFinKpi(v: number | null, unit: string): string {
  if (v == null || Number.isNaN(v)) return "—";
  if (unit === "%") return fmt.fmtPercent(v, { decimals: 1 });
  if (unit === "x") return fmt.fmtNumber(v, { decimals: 2 }) + "x";
  return fmtBlnValue(v);
}
// Pretty currency code: avoid "UZS"/"RUB" abbreviations users don't always
// recognize — use Cyrillic equivalents for primary local currency.
function fmtCurrencyLabel(unit: string): string {
  const u = (unit || "").toUpperCase();
  if (u === "UZS" || u === "СУМ") return "сум";
  if (u === "USD") return "$";
  if (u === "EUR") return "€";
  if (u === "RUB") return "₽";
  return unit || "";
}

// Auto-load when relevant tab is opened
watch(activeTab, (tab) => {
  if (tab === "kpi") loadKpi();
  if (tab === "bp") loadBp();
  if (tab === "governance") loadGovernance();
  if (tab === "esg") loadEsg();
  if (tab === "consultants") loadConsultantsPerCompany();
  if (tab === "credit") loadCredit();
  if (tab === "procurement") loadProc();
  if (tab === "ifrs" || tab === "nsbu") loadFinReports();
  // Sprint C · re-run counter animation when tab swaps (new DOM mounts)
  nextTick(() => animateCounters());
});

// (Sprint C re-animate watcher moved BELOW all of the refs it watches —
//  TDZ-safety: see comment after topFinSnapshot is declared.)

// Reload when year changes (for tabs that depend on year)
watch(year, () => {
  kpiLoadedFor.value = "";
  bpLoadedFor.value = "";
  govLoadedFor.value = "";
  esgLoadedFor.value = "";
  consPerCompanyLoadedFor.value = "";
  procLoadedFor.value = "";
  finLoadedFor.value = "";
  loadActiveTab();
});

// Reload BP when period changes
watch(bpPeriod, () => {
  if (activeTab.value === "bp") loadBp();
});

// =====================================================================
// =====================================================================

interface KpiManagerView {
  id: string;
  title: string;
  shortTitle: string;
  pct: number;
  totalWeight: number;
  weightedSum: number;
  hasFact: boolean;
  attentionCount: number;       // indicators with weight ≥ 15 and ratio < 0.90
  indicators: KpiIndicatorView[];
}

interface KpiIndicatorView {
  name: string;
  unit: string;
  weight: number;
  plan: number | null;
  fact: number | null;
  ratio: number | null;        // capped at 2 (200%)
  pct: number | null;          // ratio * 100
  hasFact: boolean;
  isAttention: boolean;
}

function num(v: any): number {
  if (v === null || v === undefined || v === "") return 0;
  const n = typeof v === "string" ? parseFloat(v) : v;
  return isNaN(n) ? 0 : n;
}
function maybeNum(v: any): number | null {
  if (v === null || v === undefined || v === "") return null;
  const n = typeof v === "string" ? parseFloat(v) : v;
  return isNaN(n) ? null : n;
}

const kpiManagerViews = computed<KpiManagerView[]>(() => {
  return kpiManagers.value.map(mgr => {
    let totalWeight = 0;
    let weightedSum = 0;
    let hasFact = false;
    let attentionCount = 0;
    const indicators: KpiIndicatorView[] = (mgr.indicators || []).map(ind => {
      const w = num(ind.weight);
      const plan = maybeNum(ind.plan_year);
      const fact = maybeNum(ind.fact_year);
      const indHasFact = fact !== null && plan !== null && plan !== 0;
      let ratio: number | null = null;
      if (indHasFact) {
        ratio = Math.min(2, fact! / plan!);  // cap at 200%
        weightedSum += ratio * w;
        totalWeight += w;
        hasFact = true;
      } else if (plan !== null) {
        totalWeight += w;
      }
      const isAttention = indHasFact && ratio! < 0.90 && w >= 15;
      if (isAttention) attentionCount++;
      return {
        name: ind.name || "",
        unit: ind.unit || "",
        weight: w,
        plan,
        fact,
        ratio,
        pct: ratio !== null ? ratio * 100 : null,
        hasFact: indHasFact,
        isAttention,
      };
    });
    return {
      id: mgr.id,
      title: mgr.title || "",
      shortTitle: mgr.short_title || mgr.title || "",
      pct: totalWeight > 0 ? Math.round((weightedSum / totalWeight) * 100) : 0,
      totalWeight,
      weightedSum,
      hasFact,
      attentionCount,
      indicators,
    };
  });
});

const kpiOverallPct = computed(() => {
  let totW = 0, sumW = 0;
  let anyFact = false;
  kpiManagerViews.value.forEach(m => {
    totW += m.totalWeight;
    sumW += m.weightedSum;
    if (m.hasFact) anyFact = true;
  });
  if (!anyFact || totW === 0) return null;
  return Math.round((sumW / totW) * 100);
});

const kpiTotalIndicators = computed(() =>
  kpiManagerViews.value.reduce((acc, m) => acc + m.indicators.length, 0)
);
const kpiAttentionTotal = computed(() =>
  kpiManagerViews.value.reduce((acc, m) => acc + m.attentionCount, 0)
);

function pctColor(pct: number | null): string {
  if (pct === null) return "#94A3B8";
  if (pct >= 70) return "#1D9E75";
  if (pct >= 35) return "#D97706";
  return "#E24B4A";
}

// =====================================================================
// =====================================================================

interface BpFieldView {
  key: string;
  label: string;
  group: string;
  auto: boolean;
  sub: boolean;
  plan: number | null;
  expect: number | null;
  fact: number | null;
  pct: number | null;        // fact / plan * 100, only if both present
  hasFact: boolean;
}

const bpFieldViews = computed<BpFieldView[]>(() => {
  if (!bpData.value) return [];
  return BP_FIELDS.map(meta => {
    const cell = bpData.value!.metrics[meta.key] || { plan: null, expect: null, fact: null };
    const plan = maybeNum(cell.plan);
    const expect = maybeNum(cell.expect);
    const fact = maybeNum(cell.fact);
    const hasFact = fact !== null;
    let pct: number | null = null;
    if (plan !== null && plan !== 0 && fact !== null) {
      pct = Math.round((fact / plan) * 100);
    }
    return {
      key: meta.key,
      label: meta.label,
      group: meta.group,
      auto: meta.auto,
      sub: !!meta.sub,
      plan, expect, fact, pct, hasFact,
    };
  });
});

// Three top metrics for KPI cards
const bpTopMetrics = computed(() => {
  const top = ["revenue", "opProfit", "profit"];
  return top.map(k => bpFieldViews.value.find(f => f.key === k)).filter(Boolean) as BpFieldView[];
});

const bpGroups = computed(() => {
  const groups = [
    { id: "opRevenue",   label: "Выручка и себестоимость" },
    { id: "opExpenses",  label: "Расходы периода" },
    { id: "opResult",    label: "Операционный результат" },
    { id: "finActivity", label: "Финансовая деятельность" },
    { id: "final",       label: "Итог" },
  ];
  return groups.map(g => ({
    ...g,
    items: bpFieldViews.value.filter(f => f.group === g.id),
  }));
});

const bpHeaderPct = computed(() => {
  const rev = bpFieldViews.value.find(f => f.key === "revenue");
  return rev?.pct ?? null;
});

function bpFmt(v: number | null | undefined): string {
  // Per user 2026-05-23: BP-значения в БД хранятся в МЛРД UZS (раньше
  // комментарий говорил «млн» — это было неверно). Чтобы fmtMoneyCompact
  // выбрал правильный суффикс (трлн для крупных SOE-цифр), скейлим
  // значение к raw UZS = v × 10^9.
  if (v === null || v === undefined) return "—";
  return fmt.fmtMoneyCompact(v * 1_000_000_000, "UZS", { decimals: 1 });
}

function bpPctColor(pct: number | null): string {
  if (pct === null) return "#94A3B8";
  if (pct >= 95) return "#1D9E75";
  if (pct >= 80) return "#D97706";
  return "#E24B4A";
}

function fmtKpiUnit(v: number | null, unit: string): string {
  if (v === null) return "—";
  const formatted = Math.abs(v) >= 1000
    ? fmt.fmtNumber(v, { decimals: 0 })
    : fmt.fmtNumber(v, { decimals: v % 1 === 0 ? 0 : 2 });
  return unit ? `${formatted} ${unit}` : formatted;
}

// =====================================================================
// Governance computed views
// =====================================================================

interface GovKpi {
  label: string;
  value: string | number;
  raw: number | null;
  unit: string;
  color: string;
}

const govKpis = computed<GovKpi[]>(() => {
  const d = govDetail.value;
  if (!d) return [];
  
  // Try multiple shapes — backend may return data flat or nested under .data
  const data = d.data || d.governance_data || d;
  const boardSize = data.board_size ?? null;
  const indep = data.independent_directors_count ?? data.independent_count ?? null;
  const women = data.women_directors_count ?? data.women_count ?? null;
  const foreign = data.foreign_directors_count ?? data.foreign_count ?? null;
  const attendance = data.avg_attendance_pct ?? null;
  const meetings = data.meetings_per_year ?? null;
  
  const indepPct = boardSize && indep !== null ? Math.round((indep / boardSize) * 100) : null;
  const womenPct = boardSize && women !== null ? Math.round((women / boardSize) * 100) : null;
  const foreignPct = boardSize && foreign !== null ? Math.round((foreign / boardSize) * 100) : null;
  
  return [
    { label: "Размер совета", value: boardSize ?? "—", raw: boardSize, unit: "чел.", color: "#7F77DD" },
    { label: "Независимые", value: indepPct === null ? "—" : `${indepPct}%`, raw: indepPct, unit: indep !== null ? `(${indep} чел.)` : "", color: "#1D9E75" },
    { label: "Женщины", value: womenPct === null ? "—" : `${womenPct}%`, raw: womenPct, unit: women !== null ? `(${women} чел.)` : "", color: "#EF9F27" },
    { label: "Иностранцы", value: foreignPct === null ? "—" : `${foreignPct}%`, raw: foreignPct, unit: foreign !== null ? `(${foreign} чел.)` : "", color: "#378ADD" },
    { label: "Посещаемость", value: attendance !== null ? `${attendance}%` : "—", raw: attendance, unit: "", color: "#1D9E75" },
    { label: "Заседаний в год", value: meetings ?? "—", raw: meetings, unit: "", color: "#7F77DD" },
  ];
});

const govCommittees = computed(() => {
  const d = govDetail.value;
  if (!d) return [];
  const data = d.data || d.governance_data || d;
  return [
    { label: "Аудит", present: !!data.has_audit_committee },
    { label: "Вознаграждения", present: !!data.has_remuneration_committee },
    { label: "Номинирование", present: !!data.has_nomination_committee },
    { label: "Стратегия", present: !!data.has_strategy_committee },
  ];
});

interface BoardMemberView {
  id: string;
  fullName: string;
  position: string;
  roleType: RoleType | null;
  roleLabel: string;
  roleColor: string;
  isIndependent: boolean;
  isWoman: boolean;
  isForeign: boolean;
  appointed: string;
  termEnd: string;
  initials: string;
}

function getInitials(fullName: string): string {
  if (!fullName) return "?";
  const parts = fullName.trim().split(/\s+/);
  if (parts.length === 0) return "?";
  if (parts.length === 1) return parts[0][0].toUpperCase();
  return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase();
}

const boardMembersByRole = computed<BoardMemberView[]>(() => {
  const ROLE_ORDER: RoleType[] = ["chairman", "executive", "independent", "non_executive", "state_rep"];
  
  return govMembers.value
    .map((m: any) => {
      const role = m.role_type as RoleType | null;
      const meta = ROLE_TYPE_META.find(r => r.key === role);
      return {
        id: m.id,
        fullName: m.full_name || "—",
        position: m.position || "",
        roleType: role,
        roleLabel: meta?.label || "Член совета",
        roleColor: meta?.color || "#94A3B8",
        isIndependent: !!m.is_independent,
        isWoman: !!m.is_woman,
        isForeign: !!m.is_foreign,
        appointed: m.appointed_date ? fmtDate(m.appointed_date) : "—",
        termEnd: m.term_end_date ? fmtDate(m.term_end_date) : "—",
        initials: getInitials(m.full_name || ""),
      } as BoardMemberView;
    })
    .sort((a, b) => {
      const ai = ROLE_ORDER.indexOf(a.roleType as any);
      const bi = ROLE_ORDER.indexOf(b.roleType as any);
      if (ai !== bi) return (ai === -1 ? 99 : ai) - (bi === -1 ? 99 : bi);
      return a.fullName.localeCompare(b.fullName, "ru");
    });
});

// =====================================================================
// ESG computed views
// =====================================================================

interface PillarView {
  pillar: Pillar;
  label: string;
  fullLabel: string;
  color: string;
  metricCount: number;
  avgAttainment: number | null;  // 0-100
  metricsBehind: number;
  metricsOnTarget: number;
}

const esgPillarStats = computed<PillarView[]>(() => {
  const detail = esgDetail.value;
  const metrics: any[] = (detail?.metrics || []) as any[];
  
  return PILLAR_META.map(pm => {
    const pillarMetrics = metrics.filter(m => m.pillar === pm.key);
    let attSum = 0, attCount = 0;
    let onTarget = 0, behind = 0;
    
    pillarMetrics.forEach(m => {
      const val = num(m.value);
      const tgt = num(m.target);
      if (tgt > 0) {
        const ratio = val / tgt;
        attSum += Math.min(2, ratio);
        attCount++;
        if (ratio >= 1) onTarget++;
        else if (ratio < 0.85) behind++;
      }
    });
    
    return {
      pillar: pm.key,
      label: pm.key,
      fullLabel: pm.label,
      color: pm.color,
      metricCount: pillarMetrics.length,
      avgAttainment: attCount > 0 ? Math.round((attSum / attCount) * 100) : null,
      metricsOnTarget: onTarget,
      metricsBehind: behind,
    };
  });
});

interface EsgMetricView {
  id: string;
  pillar: Pillar;
  pillarColor: string;
  metric_code: string;
  metric_name: string;
  value: number | null;
  target: number | null;
  benchmark: number | null;
  unit: string;
  ratio: number | null;
  pct: number | null;
}

const esgMetricsByPillar = computed(() => {
  const detail = esgDetail.value;
  const metrics: any[] = (detail?.metrics || []) as any[];
  
  return PILLAR_META.map(pm => ({
    pillar: pm.key,
    label: pm.label,
    color: pm.color,
    metrics: metrics
      .filter(m => m.pillar === pm.key)
      .map((m: any): EsgMetricView => {
        const value = maybeNum(m.value);
        const target = maybeNum(m.target);
        const benchmark = maybeNum(m.benchmark);
        const ratio = value !== null && target !== null && target !== 0 ? value / target : null;
        return {
          id: m.id,
          pillar: pm.key,
          pillarColor: pm.color,
          metric_code: m.metric_code || "",
          metric_name: m.metric_name || "",
          value, target, benchmark,
          unit: m.unit || "",
          ratio,
          pct: ratio !== null ? Math.round(ratio * 100) : null,
        };
      }),
  }));
});

interface EsgIssueView {
  id: string;
  title: string;
  description: string;
  pillar: Pillar | null;
  pillarColor: string;
  pillarLabel: string;
  severity: Severity;
  severityLabel: string;
  severityColor: string;
  status: IssueStatus;
  statusLabel: string;
  statusColor: string;
}

const esgIssuesView = computed<EsgIssueView[]>(() => {
  return esgIssues.value.map((i: any) => {
    const pmeta = PILLAR_META.find(p => p.key === i.pillar);
    const smeta = SEVERITY_META.find(s => s.key === i.severity);
    const stmeta = ISSUE_STATUS_META.find(s => s.key === i.status);
    return {
      id: i.id,
      title: i.title || i.metric_name || "Без названия",
      description: i.description || i.note || "",
      pillar: i.pillar as Pillar | null,
      pillarColor: pmeta?.color || "#94A3B8",
      pillarLabel: pmeta?.label || "—",
      severity: i.severity || "med",
      severityLabel: smeta?.label || i.severity || "—",
      severityColor: smeta?.color || "#94A3B8",
      status: i.status || "open",
      statusLabel: stmeta?.label || i.status || "—",
      statusColor: stmeta?.color || "#94A3B8",
    };
  });
});

const esgIssuesByStatus = computed(() => {
  const groups: Record<IssueStatus, EsgIssueView[]> = {
    open: [], in_progress: [], mitigated: [], closed: [],
  };
  esgIssuesView.value.forEach(i => {
    if (groups[i.status]) groups[i.status].push(i);
  });
  return groups;
});

const esgIssuesOpen = computed(() =>
  esgIssuesView.value.filter(i => i.status === "open" || i.status === "in_progress")
);

function esgPctColor(pct: number | null): string {
  if (pct === null) return "#94A3B8";
  if (pct >= 100) return "#1D9E75";
  if (pct >= 85) return "#D97706";
  return "#E24B4A";
}

function fmtEsgValue(v: number | null, unit: string): string {
  if (v === null) return "—";
  const formatted = Math.abs(v) >= 10000
    ? fmt.fmtNumber(Math.round(v))
    : fmt.fmtNumber(v, { decimals: v % 1 === 0 ? 0 : 2 });
  return unit ? `${formatted} ${unit}` : formatted;
}

// Per-company stats (top-line KPIs for the consultants tab)
const consPerCompanyKpis = computed(() => {
  const d = consPerCompany.value;
  if (!d) return null;
  const big4Count = d.consultants.filter(c => c.is_big4).length;
  const totalDone = d.consultants.reduce((s, c) => s + c.task_done, 0);
  const totalTasks = d.consultants.reduce((s, c) => s + c.task_count, 0);
  const completionPct = totalTasks > 0 ? Math.round((totalDone / totalTasks) * 100) : 0;
  return {
    consultants: d.total_consultants,
    assignments: d.total_assignments,
    big4: big4Count,
    completionPct,
  };
});

// Directory grouping (for the collapsible secondary section showing all consultants)
const consDirectoryByGroup = computed(() => {
  const all = consDirectory.value.filter(c => c.is_active !== false);
  return {
    big4: all.filter(c => c.is_big4),
    other: all.filter(c => !c.is_big4),
    total: all.length,
  };
});

function getStatusShortLabel(s: string): string {
  if (s === "done") return "✓";
  if (s === "active") return "→";
  if (s === "review") return "⟳";
  if (s === "init") return "·";
  if (s === "new") return "○";
  return s.slice(0, 1).toUpperCase();
}

function getSourceLabel(src: string): string {
  if (src === "task") return "из задачи";
  if (src === "manual") return "вручную";
  if (src === "lookup") return "lookup";
  return src;
}

// Legacy alias — keep template-references safe
const consultantsByGroup = consDirectoryByGroup;

// =====================================================================
// Credit Portfolio computed views
// =====================================================================

const creditKpis = computed(() => {
  const loans = creditLoans.value;
  const total = loans.length;
  const totalDebt = loans.reduce((s, l) => s + toNum(l.debt_usd), 0);
  const guaranteed = loans.filter(l => l.is_guaranteed).length;
  // Weighted avg rate by debt_usd
  let rateWeightedSum = 0;
  let rateWeight = 0;
  loans.forEach(l => {
    const r = toNum(l.rate);
    const d = toNum(l.debt_usd);
    if (r > 0 && d > 0) {
      rateWeightedSum += r * d;
      rateWeight += d;
    }
  });
  const avgRate = rateWeight > 0 ? rateWeightedSum / rateWeight : 0;
  return { total, totalDebt, guaranteed, avgRate };
});

interface CreditBucket {
  key: string;
  label: string;
  color: string;
  count: number;
  debt: number;
  pct: number;       // percent of total debt
}

const creditByLender = computed<CreditBucket[]>(() => {
  const buckets: Record<string, { count: number; debt: number }> = {};
  creditLoans.value.forEach(l => {
    const lt = (l.lender_type || "other") as string;
    const b = buckets[lt] = buckets[lt] || { count: 0, debt: 0 };
    b.count++;
    b.debt += toNum(l.debt_usd);
  });
  const totalDebt = creditKpis.value.totalDebt || 1;
  return Object.entries(buckets).map(([lt, data]) => {
    const meta = (CP_LENDER_LABELS as Record<string, { label: string; color: string }>)[lt] || {
      label: lt,
      color: "#94A3B8",
    };
    return {
      key: lt,
      label: meta.label,
      color: meta.color,
      count: data.count,
      debt: data.debt,
      pct: Math.round((data.debt / totalDebt) * 100),
    };
  }).sort((a, b) => b.debt - a.debt);
});

// Sprint B · Credit maturity ladder — debt grouped by time-to-maturity bucket
interface MaturityBucket {
  key: string;
  label: string;
  color: string;
  count: number;
  debt: number;
  pct: number;
}

const creditMaturityLadder = computed<MaturityBucket[]>(() => {
  const buckets: Record<string, MaturityBucket> = {
    overdue: { key: "overdue", label: "Просрочка",   color: "#E24B4A", count: 0, debt: 0, pct: 0 },
    lt1y:    { key: "lt1y",    label: "< 1 года",    color: "#EF9F27", count: 0, debt: 0, pct: 0 },
    y1_3:    { key: "y1_3",    label: "1 – 3 лет",  color: "#378ADD", count: 0, debt: 0, pct: 0 },
    y3_5:    { key: "y3_5",    label: "3 – 5 лет",  color: "#7F77DD", count: 0, debt: 0, pct: 0 },
    gt5y:    { key: "gt5y",    label: "> 5 лет",     color: "#1D9E75", count: 0, debt: 0, pct: 0 },
    unknown: { key: "unknown", label: "Срок не указан", color: "#94A3B8", count: 0, debt: 0, pct: 0 },
  };
  const now = Date.now();
  const dayMs = 86400000;
  creditLoans.value.forEach(l => {
    const debt = toNum(l.debt_usd);
    let key = "unknown";
    if (l.date_due) {
      const d = new Date(l.date_due).getTime();
      if (!Number.isNaN(d)) {
        const daysLeft = (d - now) / dayMs;
        if (daysLeft < 0)         key = "overdue";
        else if (daysLeft < 365)  key = "lt1y";
        else if (daysLeft < 365 * 3) key = "y1_3";
        else if (daysLeft < 365 * 5) key = "y3_5";
        else                      key = "gt5y";
      }
    }
    buckets[key].count++;
    buckets[key].debt += debt;
  });
  const totalDebt = creditKpis.value.totalDebt || 1;
  return Object.values(buckets)
    .filter(b => b.count > 0)
    .map(b => ({ ...b, pct: Math.round((b.debt / totalDebt) * 100) }));
});

const creditMaturityMaxPct = computed(() => {
  let m = 0;
  creditMaturityLadder.value.forEach(b => { if (b.pct > m) m = b.pct; });
  return m || 1;
});

const creditByCurrency = computed<CreditBucket[]>(() => {
  const buckets: Record<string, { count: number; debt: number }> = {};
  creditLoans.value.forEach(l => {
    const cur = l.currency || "OTHER";
    const b = buckets[cur] = buckets[cur] || { count: 0, debt: 0 };
    b.count++;
    b.debt += toNum(l.debt_usd);
  });
  const totalDebt = creditKpis.value.totalDebt || 1;
  return Object.entries(buckets).map(([cur, data]) => ({
    key: cur,
    label: cur,
    color: cpCurrencyColor(cur),
    count: data.count,
    debt: data.debt,
    pct: Math.round((data.debt / totalDebt) * 100),
  })).sort((a, b) => b.debt - a.debt);
});

interface LoanView {
  id: string;
  loan_code: string;
  bank: string;
  bank_short: string;
  currency: string;
  rate: number;
  rateText: string;
  debt_usd: number;
  date_due: string | null;
  date_due_short: string;
  lender_type: string;
  lender_label: string;
  lender_color: string;
  is_guaranteed: boolean;
  is_overdue: boolean;
}

const creditTopLoans = computed<LoanView[]>(() => {
  return creditLoans.value
    .slice()
    .sort((a, b) => toNum(b.debt_usd) - toNum(a.debt_usd))
    .map(l => {
      const meta = (CP_LENDER_LABELS as Record<string, { label: string; color: string }>)[l.lender_type || ""] || {
        label: "—",
        color: "#94A3B8",
      };
      return {
        id: l.id,
        loan_code: l.loan_code,
        bank: l.bank || "—",
        bank_short: l.bank_short_name || l.bank || "—",
        currency: l.currency || "—",
        rate: toNum(l.rate),
        rateText: l.rate_text || (toNum(l.rate) > 0 ? fmtRate(l.rate) : "—"),
        debt_usd: toNum(l.debt_usd),
        date_due: l.date_due || null,
        date_due_short: l.date_due ? fmtDate(l.date_due) : "—",
        lender_type: l.lender_type || "other",
        lender_label: meta.label,
        lender_color: meta.color,
        is_guaranteed: !!l.is_guaranteed,
        is_overdue: l.date_due ? isOverdue(l.date_due) : false,
      };
    });
});

function fmtUsd(v: number): string {
  if (!v) return "—";
  return fmt.fmtMoneyCompact(v, "USD", { decimals: 2 });
}

function fmtRate(rate: number | string | null | undefined): string {
  const n = toNum(rate);
  if (n === 0) return "—";
  // Rate stored as decimal (0.067) or already-percent (6.7) — heuristic: <1 means decimal
  const pct = n < 1 ? n * 100 : n;
  return fmt.fmtPercent(pct, { decimals: 2 });
}

// =====================================================================
// Procurement computed views
// =====================================================================

const procCompanyRow = computed<CompanyRatingRow | null>(() => {
  if (!procData.value || !company.value) return null;
  return procData.value.rating.find(r => r.company_id === company.value!.id) || null;
});

const procPurchases = computed<ClosureRow[]>(() => {
  if (!procData.value) return [];
  // Backend may return all closures — safe filter
  return procData.value.purchases.filter(p => p.company_id === company.value?.id);
});

const procCompanyKpis = computed(() => {
  const all = procPurchases.value;
  if (all.length === 0) return null;
  const clean = all.filter(p => !p.is_dirty);
  const dirty = all.length - clean.length;
  const totalOverpay = clean
    .filter(p => (p.deviation_abs || 0) > 0)
    .reduce((s, p) => s + (p.deviation_abs || 0), 0);
  const above = clean.filter(p => (p.deviation_pct || 0) > 3).length;
  const aboveMarketPct = clean.length > 0 ? Math.round((above / clean.length) * 100) : 0;
  // Median deviation
  const devs = clean.map(p => p.deviation_pct).filter(d => d !== null && d !== undefined) as number[];
  devs.sort((a, b) => a - b);
  const median = devs.length > 0 ? devs[Math.floor(devs.length / 2)] : 0;
  return {
    total: all.length,
    clean: clean.length,
    dirty,
    totalOverpay,
    aboveMarketPct,
    medianDev: median,
  };
});

interface ProcCategoryView {
  id: string;
  name: string;
  short: string;
  deviation: number;
  closure_count: number;
  color: string;
}

const procWorstCats = computed<ProcCategoryView[]>(() => {
  const row = procCompanyRow.value;
  if (!row) return [];
  return (row.worst_cats || []).slice(0, 4).map(c => ({
    id: String(c.category_id),
    name: c.category_name,
    short: c.category_short || c.category_name,
    deviation: c.deviation_pct,
    closure_count: c.closure_count,
    color: paColorByDev(c.deviation_pct),
  }));
});

const procBestCats = computed<ProcCategoryView[]>(() => {
  const row = procCompanyRow.value;
  if (!row) return [];
  return (row.best_cats || []).slice(0, 4).map(c => ({
    id: String(c.category_id),
    name: c.category_name,
    short: c.category_short || c.category_name,
    deviation: c.deviation_pct,
    closure_count: c.closure_count,
    color: paColorByDev(c.deviation_pct),
  }));
});

// Sprint C · Supplier concentration — top suppliers by money volume
interface SupplierBucket {
  supplier: string;
  count: number;
  money: number;          // sum of unit_price × volume
  pct: number;            // share of total money %
  color: string;
}

const procSupplierConcentration = computed(() => {
  const all = procPurchases.value;
  if (all.length === 0) return { top: [] as SupplierBucket[], totalMoney: 0, otherMoney: 0, otherCount: 0, totalSuppliers: 0, isSingleSource: false, top5Share: 0 };

  const map = new Map<string, { count: number; money: number }>();
  let totalMoney = 0;
  for (const p of all) {
    const sup = (p.supplier || "Не указан").trim() || "Не указан";
    const money = (Number(p.unit_price) || 0) * (Number(p.volume) || 0);
    if (!Number.isFinite(money)) continue;
    const b = map.get(sup) || { count: 0, money: 0 };
    b.count++;
    b.money += money;
    map.set(sup, b);
    totalMoney += money;
  }
  const totalSuppliers = map.size;

  const palette = ["#7F77DD", "#378ADD", "#1D9E75", "#EF9F27", "#E24B4A", "#94A3B8"];
  const sorted = Array.from(map.entries())
    .map(([supplier, v]) => ({ supplier, ...v }))
    .sort((a, b) => b.money - a.money);

  const topRaw = sorted.slice(0, 5);
  const others = sorted.slice(5);
  const otherMoney = others.reduce((s, x) => s + x.money, 0);
  const otherCount = others.reduce((s, x) => s + x.count, 0);

  const top: SupplierBucket[] = topRaw.map((b, i) => ({
    supplier: b.supplier,
    count: b.count,
    money: b.money,
    pct: totalMoney > 0 ? Math.round((b.money / totalMoney) * 1000) / 10 : 0,
    color: palette[i] || "#94A3B8",
  }));

  const top5Share = top.reduce((s, b) => s + b.pct, 0);
  const isSingleSource = top.length > 0 && top[0].pct >= 80;

  return { top, totalMoney, otherMoney, otherCount, totalSuppliers, isSingleSource, top5Share };
});

const procRecentPurchases = computed<ClosureRow[]>(() => {
  // Top 20 most-deviating clean purchases (sorted by abs deviation desc)
  return procPurchases.value
    .filter(p => !p.is_dirty)
    .slice()
    .sort((a, b) => Math.abs(b.deviation_pct || 0) - Math.abs(a.deviation_pct || 0))
    .slice(0, 20);
});

// =====================================================================
// Financials computed views (МСФО / НСБУ — same logic)
// =====================================================================

interface FinAvailableType {
  type: "PL" | "BS" | "CF";
  label: string;
  short: string;
  available: boolean;
  reportId: string | null;
}

const finAvailableTypes = computed<FinAvailableType[]>(() => {
  const byType = new Map<string, FinancialReportListItem>();
  finReports.value.forEach(r => byType.set(r.report_type, r));
  return [
    { type: "BS", label: "Баланс", short: "BS", available: byType.has("BS"), reportId: byType.get("BS")?.id || null },
    { type: "PL", label: "ОПиУ",   short: "PL", available: byType.has("PL"), reportId: byType.get("PL")?.id || null },
    { type: "CF", label: "Cash Flow", short: "CF", available: byType.has("CF"), reportId: byType.get("CF")?.id || null },
  ];
});

interface FinLineView extends FinancialLineEdit {
  depth: number;
  valueNum: number;
}

const finLinesView = computed<FinLineView[]>(() => {
  if (!finFullReport.value) return [];
  const lines = finFullReport.value.lines || [];
  // Build code→line map for parent traversal
  const codeMap = new Map<string, FinancialLineEdit>();
  lines.forEach(l => codeMap.set(l.line_code, l));

  function depthOf(code: string, visited = new Set<string>()): number {
    if (visited.has(code)) return 0;
    visited.add(code);
    const ln = codeMap.get(code);
    if (!ln || !ln.parent_code) return 0;
    return 1 + depthOf(ln.parent_code, visited);
  }

  return [...lines]
    .sort((a, b) => a.sort_order - b.sort_order)
    .map(l => ({
      ...l,
      depth: depthOf(l.line_code),
      valueNum: typeof l.value === "string" ? parseFloat(l.value as string) || 0 : (l.value as number) || 0,
    }));
});

// Line-value formatter: render value as-is, with NBSP thousands separator.
// Stored numbers are already in млрд UZS per the /financials convention —
// unit_scale is ignored on display (the Firebase migration set it wrongly).
function fmtFinValue(v: number, _scale: number): string {
  return fmtBlnValue(v);
}

// Unit-scale label used in the table header. Per user spec all values are
// shown in billions, so the header always says "млрд".
function getUnitScaleLabel(_scale: number): string {
  return "млрд";
}

// Friendly source label — sources stored as raw migration tags ("firebase_sparse_fix",
// "ifrs-editor", …) are confusing to non-engineers. Translate to nicer text.
function fmtSourceLabel(s: string | null | undefined): string {
  const v = String(s || "").toLowerCase();
  if (!v) return "—";
  if (v.startsWith("firebase")) return "Платформа (миграция)";
  if (v === "ifrs-editor" || v === "nsbu-editor") return "Платформа (редактор)";
  if (v === "ifrs" || v === "nsbu") return "Платформа";
  if (v.startsWith("excel-confirm")) return "Excel-импорт";
  return s as string;
}

function fmtFinUpdated(s: string): string {
  if (!s) return "";
  return fmt.fmtDate(s);
}

const finStandardLabel = computed(() =>
  financialsStandard.value === "IFRS" ? "МСФО" : "НСБУ"
);

// =====================================================================
// Sprint A · Topbar financial snapshot (Revenue YTD · Debt · Rating)
// =====================================================================
// Loaded eagerly on mount so the 4 numbers appear under the company name
// regardless of which tab the user opens. IFRS standard preferred; falls
// back to NSBU if IFRS missing.

interface TopFinSnapshot {
  revenue: number | null;
  revenueUnit: string;
  debt: number | null;
  debtUnit: string;
  loadedYear: number | null;
  loadedStandard: "IFRS" | "NSBU" | null;
}

const topFinSnapshot = ref<TopFinSnapshot>({
  revenue: null, revenueUnit: "UZS",
  debt: null, debtUnit: "UZS",
  loadedYear: null, loadedStandard: null,
});

// Sprint C+ · dedupe guard — keyed by company code + year; prevents fan-out
// of duplicate /api/financials calls when watchers retrigger.
const topFinSnapshotLoadedFor = ref<string | null>(null);
let topFinSnapshotInflight: Promise<void> | null = null;

async function loadTopFinSnapshot() {
  if (!company.value) return;
  const cCode = (company.value as any).code || "";
  if (!cCode) return;

  const key = `${cCode}:${year.value}`;
  if (topFinSnapshotLoadedFor.value === key) return;          // already done
  if (topFinSnapshotInflight) return topFinSnapshotInflight;  // join in-flight
  topFinSnapshotLoadedFor.value = key;

  // Reset
  topFinSnapshot.value = {
    revenue: null, revenueUnit: "UZS", debt: null, debtUnit: "UZS",
    loadedYear: null, loadedStandard: null,
  };

  topFinSnapshotInflight = (async () => {
    try {
      // Try the selected year first, then previous (avoid blank for fresh years).
      // Per standard: prefer IFRS, fall back to NSBU.
      const years = [year.value, year.value - 1, year.value - 2];
      const stds: Array<"IFRS" | "NSBU"> = ["IFRS", "NSBU"];

      for (const std of stds) {
        for (const y of years) {
          try {
            const list = await financialsApi.list({
              company_code: cCode, year: y, standard: std,
            });
            if (!list || list.length === 0) continue;

            const pl = list.find(r => r.report_type === "PL");
            const bs = list.find(r => r.report_type === "BS");
            if (!pl && !bs) continue;

            const fetched = await Promise.allSettled([
              pl ? financialsApi.get(pl.id) : Promise.resolve(null),
              bs ? financialsApi.get(bs.id) : Promise.resolve(null),
            ]);
            const plFull = fetched[0].status === "fulfilled" ? fetched[0].value : null;
            const bsFull = fetched[1].status === "fulfilled" ? fetched[1].value : null;

            const rev = _lineValue(plFull || undefined, ["revenue", "выручка"]);
            const debt = _lineValue(bsFull || undefined, ["debt", "totalDebt", "total_debt"]);

            topFinSnapshot.value = {
              revenue: rev.v != null ? rev.v * _scaleFactor(plFull || undefined) : null,
              revenueUnit: plFull?.currency || "UZS",
              debt: debt.v != null ? debt.v * _scaleFactor(bsFull || undefined) : null,
              debtUnit: bsFull?.currency || "UZS",
              loadedYear: y,
              loadedStandard: std,
            };
            return;  // success — bail out of both loops
          } catch {
            continue;
          }
        }
      }
    } finally {
      topFinSnapshotInflight = null;
    }
  })();
  await topFinSnapshotInflight;
}

// Sprint C · Re-animate after any heavy data set lands.
// Placed AFTER all 4 watched refs are declared so Vue's effect-tracking
// can iterate them without hitting a TDZ "Cannot access X before init".
watch(
  [finKpis, creditMaturityLadder, procSupplierConcentration, topFinSnapshot],
  () => { nextTick(() => animateCounters()); },
  { deep: true },
);

const total = computed(() => taskItems.value.length);
const done = computed(() => taskItems.value.filter(t => t.status === "done").length);

const overdueTask = computed(() => taskItems.value.filter(
  t => t.status !== "done" && isOverdue(t.due_date) && !isExcludedStatus(t.status)
).length);

const overdueProj = computed(() => projItems.value.filter(
  p => p.status !== "done" && isOverdue(p.due_date) && !isExcludedStatus(p.status)
).length);

const overdue = computed(() => overdueTask.value + overdueProj.value);

// Sprint A · Overdue drill — collect actual rows for the modal
interface OverdueRow {
  kind: "task" | "project";
  id: string;
  title: string;
  owner?: string | null;
  due_date: string | null;
  daysOverdue: number;
  link?: string | null;
}

function _daysOverdueOf(due: string | null | undefined): number {
  if (!due) return 0;
  const d = new Date(due);
  if (isNaN(d.getTime())) return 0;
  const diffMs = Date.now() - d.getTime();
  return Math.max(0, Math.floor(diffMs / 86400000));
}

const overdueItems = computed<OverdueRow[]>(() => {
  const tasks: OverdueRow[] = taskItems.value
    .filter(t => t.status !== "done" && isOverdue(t.due_date) && !isExcludedStatus(t.status))
    .map((t: any) => ({
      kind: "task",
      id: String(t.id),
      title: t.title || t.name || "(без названия)",
      owner: t.assignee_name || t.owner_name || t.responsible || null,
      due_date: t.due_date,
      daysOverdue: _daysOverdueOf(t.due_date),
      link: t.project_id ? `/projects/${t.project_id}` : null,
    }));
  const projects: OverdueRow[] = projItems.value
    .filter((p: any) => p.status !== "done" && isOverdue(p.due_date) && !isExcludedStatus(p.status))
    .map((p: any) => ({
      kind: "project",
      id: String(p.id),
      title: p.name || p.title || "(без названия)",
      owner: p.manager_name || p.owner_name || p.responsible || null,
      due_date: p.due_date,
      daysOverdue: _daysOverdueOf(p.due_date),
      link: `/projects/${p.id}`,
    }));
  return [...projects, ...tasks]
    .sort((a, b) => b.daysOverdue - a.daysOverdue);
});

const overdueModalOpen = ref(false);
function openOverdueModal() { overdueModalOpen.value = true; }
function closeOverdueModal() { overdueModalOpen.value = false; }

// Provide to child components (CompanyOverviewExtras → attention card click)
provide("openOverdueModal", openOverdueModal);

const projTotal = computed(() => projItems.value.length);
const projDone = computed(() => projItems.value.filter(p => p.status === "done").length);

// ─── Results metric: every status=done должен иметь result_at заполненным ───
// "Сколько есть" = done + result_at IS NOT NULL
// "Сколько должно быть" = done (все завершённые ожидают подтверждённый результат)
function _hasResult(x: any): boolean {
  return !!(x?.result_at);
}
const taskResultsExpected = computed(() => taskItems.value.filter(t => t.status === "done").length);
const taskResultsHave     = computed(() => taskItems.value.filter(t => t.status === "done" && _hasResult(t)).length);
const projResultsExpected = computed(() => projItems.value.filter(p => p.status === "done").length);
const projResultsHave     = computed(() => projItems.value.filter(p => p.status === "done" && _hasResult(p)).length);

const resultsExpected = computed(() => taskResultsExpected.value + projResultsExpected.value);
const resultsHave     = computed(() => taskResultsHave.value + projResultsHave.value);
const resultsMissing  = computed(() => Math.max(0, resultsExpected.value - resultsHave.value));
const resultsPct      = computed(() => {
  const e = resultsExpected.value;
  return e === 0 ? 0 : Math.round((resultsHave.value / e) * 100);
});
const resultsToneClass = computed(() => {
  const e = resultsExpected.value;
  if (e === 0) return "cw-res-empty";
  const pct = resultsPct.value;
  if (pct >= 100) return "cw-res-good";
  if (pct >= 70)  return "cw-res-info";
  if (pct >= 40)  return "cw-res-warn";
  return "cw-res-bad";
});

// Progress (excludes monthly/ongoing)
const taskProgress = computed(() => computeProgress(taskItems.value as any));
const pct = computed(() => taskProgress.value.pct);

// Recurring status counts
const quartCnt = computed(() =>
  taskItems.value.filter(t => t.status === "quarterly").length +
  projItems.value.filter(p => p.status === "quarterly").length
);
const monthCnt = computed(() =>
  taskItems.value.filter(t => t.status === "monthly").length +
  projItems.value.filter(p => p.status === "monthly").length
);
const ongCnt = computed(() =>
  taskItems.value.filter(t => t.status === "ongoing").length +
  projItems.value.filter(p => p.status === "ongoing").length
);
const recurCnt = computed(() => quartCnt.value + monthCnt.value + ongCnt.value);

// Status mini-chips
const stNew = computed(() => taskItems.value.filter(t => t.status === "new").length);
const stInit = computed(() => taskItems.value.filter(t => t.status === "init").length);
const stReview = computed(() => taskItems.value.filter(t => t.status === "review").length);

// Deferred (linked to another year)
const deferredTask = computed(() =>
  taskItems.value.filter(t => !!(t as any).linked_year).length
);
const deferredProj = computed(() =>
  projItems.value.filter(p => !!(p as any).linked_year).length
);

// =====================================================================
// Rating helpers (color by credit grade, outlook label, etc.)
// =====================================================================

function creditColor(rating: string | null): string {
  if (!rating) return "#94A3B8";
  const r = rating.toUpperCase();
  if (r.startsWith("BBB") || r.startsWith("A")) return "#1D9E75";
  if (r.startsWith("BB")) return "#D97706";
  if (r.startsWith("B")) return "#E24B4A";
  return "#94A3B8";
}

interface OutlookView { label: string; fg: string; bg: string; }
const OUTLOOK_MAP: Record<string, OutlookView> = {
  Stable:     { label: "Стабильный",   fg: "#64748B", bg: "#F1F5F9" },
  Positive:   { label: "Позитивный",   fg: "#1D9E75", bg: "#ECFDF5" },
  Negative:   { label: "Негативный",   fg: "#EF4444", bg: "#FEE2E2" },
  Developing: { label: "Развивающийся", fg: "#D97706", bg: "#FEF9C3" },
  RWN:        { label: "CW Негативный", fg: "#EF4444", bg: "#FEE2E2" },
  RWP:        { label: "CW Позитивный", fg: "#1D9E75", bg: "#ECFDF5" },
};

function outlookView(r: AgencyRatingBrief | undefined): OutlookView | null {
  if (!r || !r.outlook) return null;
  return OUTLOOK_MAP[r.outlook] || null;
}

function getRating(agency: string): AgencyRatingBrief | undefined {
  return credit.value.find(r => r.agency === agency);
}

function getEsgRating(): AgencyRatingBrief | undefined {
  // Priority: Sustainable Fitch > S&P ESG > CDP > MSCI > Moody's ESG
  return esg.value.find(r => r.agency === "Sustainable Fitch")
      || esg.value.find(r => r.agency === "S&P ESG")
      || esg.value.find(r => r.agency === "CDP")
      || esg.value.find(r => r.agency === "MSCI")
      || esg.value.find(r => r.agency.includes("ESG"))
      || esg.value[0];
}

const fitchRating = computed(() => getRating("Fitch"));
const spRating = computed(() => getRating("S&P"));
const moodysRating = computed(() => getRating("Moody's"));
const esgRating = computed(() => getEsgRating());

// Sprint A · Best-available credit rating for topbar snapshot
const topCreditRating = computed(() => {
  const r = fitchRating.value || spRating.value || moodysRating.value;
  if (!r) return null;
  return {
    agency: r.agency,                       // "Fitch" / "S&P" / "Moody's"
    rating: r.rating || "—",
    outlook: r.outlook || null,             // "Stable" / "Positive" / ...
    color: creditColor(r.rating || ""),
  };
});

// ESG: parse rating value, determine if it's tier (1-5) or score (0-100)
const esgInfo = computed(() => {
  const r = esgRating.value;
  if (!r) return null;
  const rv = parseInt(r.rating || "0", 10);
  const isTier = rv >= 1 && rv <= 5;
  const isScore = rv >= 6;
  const score = r.score ? parseInt(r.score, 10) : (isScore ? rv : null);
  const pctVal = score ? Math.min(100, score) : 0;
  let color: string;
  if (isTier) {
    color = rv <= 2 ? "#1D9E75" : rv === 3 ? "#D97706" : "#E24B4A";
  } else {
    color = (score || 0) >= 60 ? "#1D9E75" : (score || 0) >= 40 ? "#D97706" : "#E24B4A";
  }
  return { rating: r.rating, isTier, isScore, score, pct: pctVal, color, agency: r.agency };
});

// =====================================================================
// Donut SVG geometry
// =====================================================================
const ringR = 30;
const ringC = 2 * Math.PI * ringR;
const ringDash = computed(() => ringC * pct.value / 100);
const ringOffset = computed(() => (ringC - ringDash.value).toFixed(2));
const taskColor = computed(() => pct.value >= 70 ? "#1D9E75" : pct.value >= 35 ? "#D97706" : "#E24B4A");
const overdueColor = computed(() => overdue.value ? "#E24B4A" : "#1D9E75");

// =====================================================================
// Helpers
// =====================================================================
function fmtPlus(): string { return "+"; }
function navigateYear(delta: number) {
  year.value = year.value + delta;
}


// === v10.1 additions: TaskProjectEditor wiring for list tab ===
const editorOpen = ref(false);
const editorEntity = ref<any>(null);
const editorKind = ref<"task" | "project">("task");
const boardListRef = ref<any>(null);

async function openTaskEditor(payload: { id: string; kind: "project" | "task" }) {
  try {
    const url = payload.kind === "project"
      ? "/projects/" + payload.id
      : "/tasks/" + payload.id;
    const { data } = await api.get(url);
    editorEntity.value = data;
    editorKind.value = payload.kind;
    editorOpen.value = true;
  } catch (e: any) {
    console.error("Failed to load entity for editor:", e);
  }
}

async function onEditorSaved() {
  editorOpen.value = false;
  editorEntity.value = null;
  if (boardListRef.value && typeof boardListRef.value.reload === "function") {
    await boardListRef.value.reload();
  }
}
function onEditorClose() {
  editorOpen.value = false;
  editorEntity.value = null;
}
</script>

<template>
  <div class="cw-page cw-shell">
    <!-- ─── Loading / Error states ─── -->
    <div v-if="loading" class="cw-loading">
      <div class="cw-spinner"></div>
      <span>Загрузка рабочего пространства…</span>
    </div>

    <div v-else-if="error" class="cw-error">
      <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="#E24B4A" stroke-width="1.5">
        <circle cx="12" cy="12" r="10"/>
        <path d="M12 8v4M12 16h.01"/>
      </svg>
      <h2>{{ error }}</h2>
      <RouterLink to="/companies" class="cw-back-btn">← К списку компаний</RouterLink>
    </div>

    <template v-else-if="company">
      <!-- ═══════ TOPBAR ═══════ -->
      <header class="cw-topbar">
        <div class="cw-topbar-l">
          <h1 :title="company.name_ru">{{ company.name_short || company.name_ru }}</h1>

          <span v-if="sector" class="cw-tbadge cw-tbadge-sector"
                :style="sector.color_hex ? `background: ${sector.color_hex}24; color: ${sector.color_hex}` : ''">
            {{ sector.name_ru }}
          </span>

          <span class="cw-tbadge cw-tbadge-clickable" @click="activeTab = 'list'"
                title="Всего проектов в компании">
            {{ projTotal }} проектов ·
            <span class="cw-tbadge-green">{{ projDone }} завершено</span>
          </span>

          <span class="cw-tbadge cw-tbadge-clickable" @click="activeTab = 'kanban'"
                title="Всего задач в компании">
            {{ total }} задач ·
            <span class="cw-tbadge-green">{{ done }} завершено</span>
          </span>
        </div>

        <div class="cw-topbar-r">
          <!-- Year picker -->
          <div class="cw-year-picker">
            <button class="cw-yr-arrow" @click="navigateYear(-1)" :disabled="year <= 2024">‹</button>
            <span class="cw-yr-label">FY {{ year }}</span>
            <button class="cw-yr-arrow" @click="navigateYear(1)" :disabled="year >= 2030">›</button>
          </div>

          <button class="cw-add-btn">+ Задача</button>
        </div>
      </header>

      <CompanyTabBar
        :active-tab="activeTab as any"
        @change="(t: any) => activeTab = t"
      />

      <!-- ═══════ TAB BODY ═══════ -->
      <main class="cw-body">
        <Transition name="cw-fade" mode="out-in">
        <!-- ─── OVERVIEW TAB ─── -->
        <div v-if="activeTab === 'overview'" :key="'overview'" class="cw-overview-scroll">

          <!-- ╔═ HERO KPI CARD: Ratings | Donut | Stats ═╗ -->
          <section class="cw-hero">
            <div class="cw-hero-grid">

              <!-- ── LEFT: 4 RATING TILES ── -->
              <div class="cw-hero-col cw-hero-col-ratings">
                <div class="cw-section-label">РЕЙТИНГИ</div>
                <div class="cw-ratings-grid">

                  <!-- Fitch -->
                  <div class="cw-rating-tile" v-if="fitchRating">
                    <div class="cw-rt-agency">Fitch Ratings</div>
                    <div class="cw-rt-value" :style="`color: ${creditColor(fitchRating.rating)}`">
                      {{ fitchRating.rating }}
                    </div>
                    <div v-if="outlookView(fitchRating)" class="cw-rt-outlook"
                         :style="`background: ${outlookView(fitchRating)!.bg}; color: ${outlookView(fitchRating)!.fg}`">
                      {{ outlookView(fitchRating)!.label }}
                    </div>
                    <div v-if="fitchRating.rating_date_text" class="cw-rt-date">
                      {{ fitchRating.rating_date_text }}
                      <a v-if="fitchRating.report_url" :href="fitchRating.report_url" target="_blank"
                         class="cw-rt-link" @click.stop title="Открыть отчёт">↗</a>
                    </div>
                  </div>
                  <div v-else class="cw-rating-tile cw-rating-empty">
                    <div class="cw-rt-agency">Fitch Ratings</div>
                    <div class="cw-rt-plus">+</div>
                  </div>

                  <!-- S&P -->
                  <div class="cw-rating-tile" v-if="spRating">
                    <div class="cw-rt-agency">S&amp;P Global</div>
                    <div class="cw-rt-value" :style="`color: ${creditColor(spRating.rating)}`">
                      {{ spRating.rating }}
                    </div>
                    <div v-if="outlookView(spRating)" class="cw-rt-outlook"
                         :style="`background: ${outlookView(spRating)!.bg}; color: ${outlookView(spRating)!.fg}`">
                      {{ outlookView(spRating)!.label }}
                    </div>
                    <div v-if="spRating.rating_date_text" class="cw-rt-date">
                      {{ spRating.rating_date_text }}
                      <a v-if="spRating.report_url" :href="spRating.report_url" target="_blank"
                         class="cw-rt-link" @click.stop title="Открыть отчёт">↗</a>
                    </div>
                  </div>
                  <div v-else class="cw-rating-tile cw-rating-empty">
                    <div class="cw-rt-agency">S&amp;P Global</div>
                    <div class="cw-rt-plus">+</div>
                  </div>

                  <!-- Moody's -->
                  <div class="cw-rating-tile" v-if="moodysRating">
                    <div class="cw-rt-agency">Moody's</div>
                    <div class="cw-rt-value" :style="`color: ${creditColor(moodysRating.rating)}`">
                      {{ moodysRating.rating }}
                    </div>
                    <div v-if="outlookView(moodysRating)" class="cw-rt-outlook"
                         :style="`background: ${outlookView(moodysRating)!.bg}; color: ${outlookView(moodysRating)!.fg}`">
                      {{ outlookView(moodysRating)!.label }}
                    </div>
                    <div v-if="moodysRating.rating_date_text" class="cw-rt-date">
                      {{ moodysRating.rating_date_text }}
                      <a v-if="moodysRating.report_url" :href="moodysRating.report_url" target="_blank"
                         class="cw-rt-link" @click.stop title="Открыть отчёт">↗</a>
                    </div>
                  </div>
                  <div v-else class="cw-rating-tile cw-rating-empty">
                    <div class="cw-rt-agency">Moody's</div>
                    <div class="cw-rt-plus">+</div>
                  </div>

                  <!-- ESG (Sustainable Fitch / S&P ESG / etc.) -->
                  <div class="cw-rating-tile" v-if="esgInfo">
                    <div class="cw-rt-agency">{{ esgInfo.agency }}</div>
                    <div class="cw-rt-value-wrap">
                      <span class="cw-rt-value" :style="`color: ${esgInfo.color}`">{{ esgInfo.rating }}</span>
                      <span v-if="esgInfo.isTier" class="cw-rt-suffix">/ 5</span>
                    </div>
                    <div v-if="!esgInfo.isTier && esgInfo.score" class="cw-rt-esg-bar-wrap">
                      <div class="cw-rt-esg-bar">
                        <div class="cw-rt-esg-bar-fill"
                             :style="`width: ${esgInfo.pct}%; background: ${esgInfo.color}`"></div>
                      </div>
                      <div class="cw-rt-esg-score" :style="`color: ${esgInfo.color}`">
                        {{ esgInfo.score }} / 100 баллов
                      </div>
                    </div>
                    <div v-if="esgRating?.rating_date_text" class="cw-rt-date">
                      {{ esgRating.rating_date_text }}
                      <a v-if="esgRating.report_url" :href="esgRating.report_url" target="_blank"
                         class="cw-rt-link" @click.stop title="Открыть отчёт">↗</a>
                    </div>
                  </div>
                  <div v-else class="cw-rating-tile cw-rating-empty">
                    <div class="cw-rt-agency">ESG</div>
                    <div class="cw-rt-plus">+</div>
                  </div>

                </div>
              </div>

              <!-- DIVIDER 1 -->
              <div class="cw-divider"></div>

              <!-- ── CENTER: PROGRESS DONUT ── -->
              <div class="cw-hero-col cw-hero-col-donut">
                <div class="cw-section-label">ПРОГРЕСС</div>

                <svg class="cw-donut-svg" viewBox="0 0 72 72" width="78" height="78">
                  <circle cx="36" cy="36" :r="ringR" fill="none" stroke="#E2E8F0" stroke-width="6"/>
                  <circle class="cw-donut-arc"
                          cx="36" cy="36" :r="ringR" fill="none"
                          :stroke="taskColor" stroke-width="6" stroke-linecap="round"
                          :stroke-dasharray="ringC.toFixed(2)"
                          :stroke-dashoffset="ringOffset"
                          transform="rotate(-90 36 36)"/>
                  <text x="36" y="42" text-anchor="middle" font-size="20" font-weight="500"
                        :fill="taskColor" style="font-variant-numeric: tabular-nums">
                    <tspan :data-countup="pct" data-cu-d="0">{{ pct }}</tspan>%
                  </text>
                </svg>

                <div class="cw-donut-sub">
                  <span :data-countup="done" data-cu-d="0">{{ done }}</span> /
                  <span :data-countup="total" data-cu-d="0">{{ total }}</span>
                  задач завершено
                </div>
                <div v-if="projTotal > 0" class="cw-donut-sub">
                  <span :data-countup="projDone" data-cu-d="0">{{ projDone }}</span> /
                  <span :data-countup="projTotal" data-cu-d="0">{{ projTotal }}</span>
                  проектов завершено
                </div>

                <!-- Recurring pill -->
                <div v-if="recurCnt > 0" class="cw-recurring-pill"
                     title="Регулярные задачи не учитываются в % прогресса">
                  <svg width="9" height="9" viewBox="0 0 12 12" fill="none" stroke="currentColor"
                       stroke-width="1.4" stroke-linecap="round">
                    <path d="M2 6a4 4 0 014-4 4 4 0 010 8 4 4 0 01-4-4z"/>
                  </svg>
                  <span v-if="quartCnt > 0">
                    <span style="color: #7E22CE; font-weight: 600">{{ quartCnt }}</span> ежекв.
                  </span>
                  <span v-if="monthCnt > 0">
                    <span style="color: #4338CA; font-weight: 600">{{ monthCnt }}</span> ежемес.
                  </span>
                  <span v-if="ongCnt > 0">
                    <span style="color: #0E7490; font-weight: 600">{{ ongCnt }}</span> постоянн.
                  </span>
                </div>
              </div>

              <!-- DIVIDER 2 -->
              <div class="cw-divider"></div>

              <!-- ── RIGHT: STATS STACK ── -->
              <!-- ── RIGHT: STATS STACK (v2) ── -->
              <div class="cw-hero-col cw-hero-col-stats cw-hero-col-stats-v2">

                <!-- TIER 1: hero stat with completion ratio + status pill -->
                <div class="cw-stats-hero">
                  <div class="cw-stats-hero-l">
                    <div class="cw-stats-hero-num">
                      <span :data-countup="done" data-cu-d="0">{{ done }}</span>
                      <span class="cw-stats-hero-sep">/</span>
                      <span :data-countup="total" data-cu-d="0">{{ total }}</span>
                    </div>
                    <div class="cw-stats-hero-sub">
                      задач завершено · <b>{{ projDone }}</b> из <b>{{ projTotal }}</b> проектов
                    </div>
                  </div>
                  <div class="cw-stats-hero-r">
                    <div v-if="!overdue" class="cw-stats-pill cw-stats-pill-good">
                      все в графике
                    </div>
                    <div v-else class="cw-stats-pill cw-stats-pill-bad">
                      просрочено: {{ overdueTask }} / {{ overdueProj }}
                    </div>
                  </div>
                </div>

                <!-- TIER 2: secondary statuses + results metric as 5-column micro grid -->
                <div class="cw-stats-grid cw-stats-grid-5">
                  <div class="cw-stats-cell">
                    <div class="cw-stats-cell-label">Не начато</div>
                    <div class="cw-stats-cell-num" :class="{ 'is-dim': stNew === 0 }"
                         :data-countup="stNew" data-cu-d="0">{{ stNew }}</div>
                  </div>
                  <div class="cw-stats-cell">
                    <div class="cw-stats-cell-label">Иниц.</div>
                    <div class="cw-stats-cell-num" :class="{ 'is-dim': stInit === 0 }"
                         :data-countup="stInit" data-cu-d="0">{{ stInit }}</div>
                  </div>
                  <div class="cw-stats-cell">
                    <div class="cw-stats-cell-label">Согл.</div>
                    <div class="cw-stats-cell-num" :class="{ 'is-dim': stReview === 0 }"
                         :data-countup="stReview" data-cu-d="0">{{ stReview }}</div>
                  </div>
                  <div class="cw-stats-cell">
                    <div class="cw-stats-cell-label">Перенес.</div>
                    <div class="cw-stats-cell-num"
                         :class="{ 'is-dim': (deferredTask + deferredProj) === 0 }"
                         :data-countup="deferredTask" data-cu-d="0">{{ deferredTask }}</div>
                  </div>
                  <div class="cw-stats-cell"
                       :class="`cw-stats-results ${resultsToneClass}`"
                       :title="resultsExpected === 0
                         ? 'Завершённых работ пока нет'
                         : `Результаты подтверждены: ${resultsHave} из ${resultsExpected} (${resultsPct}%). Ждут: ${resultsMissing}`">
                    <div class="cw-stats-cell-label">Результ.</div>
                    <div class="cw-stats-cell-num cw-stats-cell-num-ratio"
                         :class="{ 'is-dim': resultsExpected === 0 }">
                      <span :data-countup="resultsHave" data-cu-d="0">{{ resultsHave }}</span>
                      <span class="cw-stats-ratio-sep">/</span>
                      <span :data-countup="resultsExpected" data-cu-d="0">{{ resultsExpected }}</span>
                    </div>
                  </div>
                </div>

              </div>

            </div>
          </section>

          <!-- ╔═ Placeholders for next session ═╗ -->
          <!-- Overview Extras -- 6 блоков -->
          <CompanyOverviewExtras
            :company-id="company?.id || ''"
            :company-code="(route.params.code as string) || ''"
            :sector-id="(company as any)?.sector_id || (sector as any)?.id || ''"
            :sector-name="sector?.name_ru || 'Сектор'"
            :year="year"
            :overdue="overdue || 0"
          />

          <CompanyDocumentsCard
            v-if="company?.id"
            :company-id="company.id"
            style="margin-top: 16px"
          />

        </div>

        <!-- ═══ KANBAN TAB — real implementation ═══ -->
        <div v-else-if="activeTab === 'kanban'" :key="'kanban'" class="cw-kanban-scroll">
          <div class="cw-kanban-board">
            <!-- Standard 5 columns (init / new / active / review / done) -->
            <div
              v-for="col in kanbanColumns"
              :key="col.id"
              class="kol"
            >
              <div class="kol-hd">
                <div class="kol-hd-l">
                  <div class="kol-dot" :style="`background: ${col.bgAccent}`"></div>
                  <div class="kol-title">{{ col.label }}</div>
                </div>
                <div class="kol-cnt">{{ col.tasks.length }}</div>
              </div>
              <div class="kol-cards">
                <template v-if="col.tasks.length === 0">
                  <div class="kol-empty">
                    <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor"
                         stroke-width="1.2" style="opacity: .3; margin-bottom: 6px">
                      <rect x="4" y="5" width="16" height="14" rx="2"/>
                      <path d="M8 3v4M16 3v4M4 11h16"/>
                    </svg>
                    <div>Нет задач</div>
                  </div>
                </template>
                <KanbanCard
                  v-for="t in col.tasks"
                  :key="t.id"
                  :task="t"
                  :overdue="isOverdueTask(t)"
                  @click="$router.push(`/project/${(t as any).project_id || t.id}`)"
                />
              </div>
            </div>

            <div v-if="recurringTasks.length > 0" class="kol kol-recurring">
              <div class="kol-hd">
                <div class="kol-hd-l">
                  <div class="kol-dot" style="background: linear-gradient(135deg, #A855F7, #06B6D4)"></div>
                  <div class="kol-title" style="color: #7E22CE">Регулярные</div>
                </div>
                <div class="kol-cnt" style="background: rgba(168, 85, 247, .1); color: #7E22CE">
                  {{ recurringTasks.length }}
                </div>
              </div>
              <div class="kol-recurring-sub">
                <span v-if="recurringTasks.filter(t => t.status === 'quarterly').length" style="color: #7E22CE">
                  Q: {{ recurringTasks.filter(t => t.status === 'quarterly').length }}
                </span>
                <span v-if="recurringTasks.filter(t => t.status === 'monthly').length" style="color: #4338CA">
                  · М: {{ recurringTasks.filter(t => t.status === 'monthly').length }}
                </span>
                <span v-if="recurringTasks.filter(t => t.status === 'ongoing').length" style="color: #0E7490">
                  · ∞: {{ recurringTasks.filter(t => t.status === 'ongoing').length }}
                </span>
              </div>
              <div class="kol-cards">
                <KanbanCard
                  v-for="t in recurringTasks"
                  :key="t.id"
                  :task="t"
                  :overdue="false"
                  @click="$router.push(`/project/${(t as any).project_id || t.id}`)"
                />
              </div>
            </div>

            <!-- Overdue column — red, only if any overdue tasks -->
            <div v-if="overdueTasks.length > 0" class="kol kol-overdue">
              <div class="kol-hd">
                <div class="kol-hd-l">
                  <div class="kol-dot" style="background: #E24B4A"></div>
                  <div class="kol-title" style="color: #E24B4A">Просрочено</div>
                </div>
                <div class="kol-cnt" style="background: rgba(220, 38, 38, .1); color: #E24B4A">
                  {{ overdueTasks.length }}
                </div>
              </div>
              <div class="kol-cards">
                <KanbanCard
                  v-for="t in overdueTasks"
                  :key="t.id"
                  :task="t"
                  :overdue="true"
                  @click="$router.push(`/project/${(t as any).project_id || t.id}`)"
                />
              </div>
            </div>
          </div>
        </div>

        <!-- ═══ LIST TAB — real implementation ═══ -->
        <div v-else-if="activeTab === 'list'" :key="'list'" class="cw-list-scroll">
          <CompanyBoardList
            ref="boardListRef"
            :company-id="company?.id || ''"
            :company-name="company?.name_ru || company?.name_short || ''"
            :year="year"
            @openEditor="openTaskEditor"
          />
        </div>

                <CompanyNotesTab
            v-else-if="activeTab === 'notes'"
            :key="'notes'"
            :company-id="company?.id || ''"
            :company-code="(route.params.code as string) || props.code"
            :year="year"
          />
        <!-- ═══ KPI TAB — real implementation ═══ -->
        <div v-else-if="activeTab === 'kpi'" :key="'kpi'" class="cw-kpi-scroll">
          <!-- Loading state -->
          <div v-if="kpiLoading" class="cw-loading-state">
            <div class="cw-spinner"></div>
            <span>Загрузка KPI {{ year }}…</span>
          </div>

          <!-- Error state -->
          <div v-else-if="kpiError" class="cw-error-state">
            <div class="cw-err-icon">⚠</div>
            <div>
              <div class="cw-err-title">Ошибка загрузки KPI</div>
              <div class="cw-err-msg">{{ kpiError }}</div>
              <button class="cw-cta-btn" @click="loadKpi()" style="margin-top: 12px">Повторить</button>
            </div>
          </div>

          <!-- Empty state -->
          <div v-else-if="kpiManagerViews.length === 0" class="cw-empty-state">
            <div class="cw-empty-icon">○</div>
            <div class="cw-empty-title">KPI не настроены</div>
            <div class="cw-empty-msg">Для {{ company.name_short || company.name_ru }} в {{ year }} году KPI не добавлены.</div>
            <div style="display:flex;gap:8px;margin-top:12px">
              <button v-if="kpiPerm.canEdit" class="cw-cta-btn" @click="openKpiEditor">✎ Создать KPI</button>
              <RouterLink to="/kpi" class="cw-cta-btn" style="background:transparent;color:var(--uza-purple);border:1px solid var(--uza-purple)">Открыть в полной версии →</RouterLink>
            </div>
          </div>

          <!-- KPI dashboard · redesigned 2026-05-23 to reuse KpiCompanyDashboard + KpiEditor (BP-style integration) -->
          <template v-else>
            <!-- Period selector + Edit button (mirror BP-tab pattern) -->
            <div class="cw-bp-period-bar" style="margin-bottom: 12px">
              <div class="cw-bp-period-label">Период:</div>
              <!-- "Год" убран 2026-05-23: fact_year заведён у <1% индикаторов. -->
              <button
                v-for="p in [{key:'q1', label:'Q1'}, {key:'q2', label:'Q2'}, {key:'q3', label:'Q3'}, {key:'q4', label:'Q4'}]"
                :key="p.key"
                class="cw-bp-period-btn"
                :class="{ active: kpiPeriod === p.key }"
                @click="kpiPeriod = (p.key as WsKpiPeriod)"
              >{{ p.label }}</button>
              <button
                v-if="kpiPerm.canEdit"
                class="cw-bp-edit-btn"
                type="button"
                @click="openKpiEditor"
                title="Открыть редактор KPI"
              >
                <svg width="13" height="13" viewBox="0 0 24 24" fill="none"
                     stroke="currentColor" stroke-width="2"
                     stroke-linecap="round" stroke-linejoin="round">
                  <path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/>
                  <path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"/>
                </svg>
                Редактировать
              </button>
            </div>

            <!-- Sprint B · Prior-year baseline banner — only shown for annual period
                 (kpiBaselineYear is set when fact_year empty, which is global signal). -->
            <div
              v-if="kpiPeriod === 'annual' && kpiBaselineYear !== null && kpiBaselineManagers.length > 0"
              class="cw-kpi-baseline-banner"
            >
              <div class="cw-kpi-baseline-icon">↻</div>
              <div class="cw-kpi-baseline-text">
                Факт за <b>{{ year }}</b> ещё не введён.
                Внизу в деталях — <b>факт {{ kpiBaselineYear }}</b> как baseline.
                <span v-if="kpiPeriod === 'annual'">
                  Совет: переключитесь на <b>Q1</b> — там данные заполнены.
                </span>
              </div>
            </div>

            <!-- Main dashboard (KpiCompanyDashboard handles: status bar, manager cards,
                 attention + achievements panes, comment block, indicator details).
                 Period prop forwarded so quarterly tabs show right plan/fact pair. -->
            <KpiCompanyDashboard
              :managers="kpiManagers"
              :active-manager-idx="activeKpiMgrIdx"
              :period="kpiPeriod"
              :company-id="company.id"
              :company-name="company.name_short || company.name_ru || ''"
              :year="year"
              :can-edit="kpiPerm.canEdit"
              @set-manager="activeKpiMgrIdx = $event"
              @open-indicator="openKpiEditor"
            />
          </template>

          <!-- Legacy summary header block (kept as reference, replaced by KpiCompanyDashboard).
               Если KpiCompanyDashboard окажется неудобным — вернуть этот блок и удалить
               <KpiCompanyDashboard> выше. Не удаляю чтобы быстро откатить если нужно. -->
          <template v-if="false">
            <!-- Summary header -->
            <div class="cw-kpi-summary">
              <div class="cw-kpi-sum-stat">
                <div class="cw-kpi-sum-label">Общее выполнение</div>
                <div class="cw-kpi-sum-value" :style="`color: ${pctColor(kpiOverallPct)}`">
                  {{ kpiOverallPct === null ? "—" : kpiOverallPct + "%" }}
                </div>
              </div>
              <div class="cw-kpi-sum-divider"></div>
              <div class="cw-kpi-sum-stat">
                <div class="cw-kpi-sum-label">Менеджеров</div>
                <div class="cw-kpi-sum-value">{{ kpiManagerViews.length }}</div>
              </div>
              <div class="cw-kpi-sum-divider"></div>
              <div class="cw-kpi-sum-stat">
                <div class="cw-kpi-sum-label">Индикаторов</div>
                <div class="cw-kpi-sum-value">{{ kpiTotalIndicators }}</div>
              </div>
              <div class="cw-kpi-sum-divider"></div>
              <div class="cw-kpi-sum-stat">
                <div class="cw-kpi-sum-label">Требуют внимания</div>
                <div class="cw-kpi-sum-value" :class="{ 'cw-kpi-attention': kpiAttentionTotal > 0 }">
                  {{ kpiAttentionTotal }}
                </div>
              </div>
            </div>

            <!-- Manager cards -->
            <div class="cw-kpi-managers">
              <div v-for="mgr in kpiManagerViews" :key="mgr.id" class="cw-kpi-mgr">
                <div class="cw-kpi-mgr-header">
                  <div class="cw-kpi-mgr-titles">
                    <div class="cw-kpi-mgr-short">{{ mgr.shortTitle }}</div>
                    <div v-if="mgr.title !== mgr.shortTitle" class="cw-kpi-mgr-full">{{ mgr.title }}</div>
                  </div>
                  <div class="cw-kpi-mgr-pct" :style="`color: ${pctColor(mgr.hasFact ? mgr.pct : null)}`">
                    {{ mgr.hasFact ? mgr.pct + "%" : "—" }}
                  </div>
                </div>

                <div class="cw-kpi-mgr-meta">
                  {{ mgr.indicators.length }} индикаторов · вес: {{ mgr.totalWeight }}
                  <span v-if="mgr.attentionCount > 0" class="cw-kpi-mgr-attn">
                    · {{ mgr.attentionCount }} требуют внимания
                  </span>
                </div>

                <!-- Indicators list -->
                <div class="cw-kpi-ind-list">
                  <div
                    v-for="(ind, idx) in mgr.indicators"
                    :key="idx"
                    class="cw-kpi-ind"
                    :class="{ 'cw-kpi-ind-attn': ind.isAttention, 'cw-kpi-ind-nofact': !ind.hasFact }"
                  >
                    <div class="cw-kpi-ind-row1">
                      <div class="cw-kpi-ind-name" :title="ind.name">{{ ind.name }}</div>
                      <div class="cw-kpi-ind-weight">{{ ind.weight }}</div>
                    </div>
                    <div class="cw-kpi-ind-row2">
                      <div class="cw-kpi-ind-vals">
                        <span class="cw-kpi-ind-plan">План: {{ fmtKpiUnit(ind.plan, ind.unit) }}</span>
                        <span class="cw-kpi-ind-fact" :class="{ 'no-fact': !ind.hasFact }">
                          Факт: {{ ind.hasFact ? fmtKpiUnit(ind.fact, ind.unit) : "не введён" }}
                        </span>
                      </div>
                      <div v-if="ind.hasFact" class="cw-kpi-ind-pct" :style="`color: ${pctColor(ind.pct)}`">
                        {{ Math.round(ind.pct!) }}%
                      </div>
                    </div>
                    <div
                      class="cw-kpi-ind-bar-wrap"
                      :title="ind.hasFact
                        ? `План: ${fmtKpiUnit(ind.plan, ind.unit)} · Факт: ${fmtKpiUnit(ind.fact, ind.unit)} · ${Math.round(ind.pct!)}% · Δ ${fmtKpiUnit((ind.fact ?? 0) - (ind.plan ?? 0), ind.unit)}`
                        : `План: ${fmtKpiUnit(ind.plan, ind.unit)} · факт не введён`"
                    >
                      <div
                        class="cw-kpi-ind-bar"
                        :style="`width: ${ind.hasFact ? Math.min(100, ind.pct!) : 0}%; background: ${pctColor(ind.pct)}`"
                      ></div>
                    </div>

                    <!-- Sprint B · Baseline (prev year fact) — shown when current year has no fact -->
                    <div
                      v-if="!ind.hasFact && kpiBaselineYear !== null && kpiBaselineIndex[mgr.id] && kpiBaselineIndex[mgr.id][ind.name] && kpiBaselineIndex[mgr.id][ind.name].fact !== null"
                      class="cw-kpi-ind-baseline"
                    >
                      <span class="cw-kpi-ind-baseline-tag">baseline {{ kpiBaselineYear }}</span>
                      <span class="cw-kpi-ind-baseline-val">
                        {{ fmtKpiUnit(kpiBaselineIndex[mgr.id][ind.name].fact, ind.unit) }}
                      </span>
                      <span
                        v-if="ind.plan != null && ind.plan !== 0 && kpiBaselineIndex[mgr.id][ind.name].fact != null"
                        class="cw-kpi-ind-baseline-vs"
                      >
                        план {{ year }} — {{ fmt.fmtPercent((ind.plan! - kpiBaselineIndex[mgr.id][ind.name].fact!) / Math.abs(kpiBaselineIndex[mgr.id][ind.name].fact!) * 100, { decimals: 0, signed: true }) }}
                      </span>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </template>
        </div>

        <!-- ═══ BUSINESS PLAN TAB — real implementation ═══ -->
        <div v-else-if="activeTab === 'bp'" :key="'bp'" class="cw-bp-scroll">
          <!-- Period selector + Edit button (right-aligned) -->
          <div class="cw-bp-period-bar">
            <div class="cw-bp-period-label">Период:</div>
            <button
              v-for="p in BP_PERIODS"
              :key="p.key"
              class="cw-bp-period-btn"
              :class="{ active: bpPeriod === p.key }"
              @click="bpPeriod = p.key"
            >
              {{ p.label }}
            </button>
            <button
              v-if="bpPerm.canEdit"
              class="cw-bp-edit-btn"
              type="button"
              @click="openBpEditor"
              title="Открыть редактор бизнес-плана"
            >
              <svg width="13" height="13" viewBox="0 0 24 24" fill="none"
                   stroke="currentColor" stroke-width="2"
                   stroke-linecap="round" stroke-linejoin="round">
                <path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/>
                <path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"/>
              </svg>
              Редактировать
            </button>
          </div>

          <!-- Loading state -->
          <div v-if="bpLoading" class="cw-loading-state">
            <div class="cw-spinner"></div>
            <span>Загрузка Бизнес-плана {{ year }} ({{ bpPeriod }})…</span>
          </div>

          <div v-else-if="bpError" class="cw-error-state">
            <div class="cw-err-icon">⚠</div>
            <div>
              <div class="cw-err-title">Ошибка загрузки Бизнес-плана</div>
              <div class="cw-err-msg">{{ bpError }}</div>
              <button class="cw-cta-btn" @click="loadBp()" style="margin-top: 12px">Повторить</button>
            </div>
          </div>

          <div v-else-if="!bpData || bpFieldViews.length === 0" class="cw-empty-state">
            <div class="cw-empty-icon">○</div>
            <div class="cw-empty-title">Бизнес-план не загружен</div>
            <div class="cw-empty-msg">Для {{ company.name_short || company.name_ru }} в {{ year }} году записи отсутствуют.</div>
          </div>

          <template v-else>
            <!-- Top 3 KPI cards -->
            <div class="cw-bp-tops">
              <div
                v-for="m in bpTopMetrics"
                :key="m.key"
                class="cw-bp-top-card"
                :style="`--accent: ${m.key === 'revenue' ? 'var(--uza-purple)' : m.key === 'opProfit' ? 'var(--uza-teal)' : 'var(--uza-amber)'}`"
              >
                <div class="cw-bp-top-label">{{ m.label }}</div>
                <div class="cw-bp-top-value">{{ bpFmt(m.fact ?? m.plan) }}</div>
                <div class="cw-bp-top-stats">
                  <div class="cw-bp-top-stat">
                    <span class="cw-bp-top-stat-l">План:</span>
                    <span class="cw-bp-top-stat-v">{{ bpFmt(m.plan) }}</span>
                  </div>
                  <div class="cw-bp-top-stat">
                    <span class="cw-bp-top-stat-l">Факт:</span>
                    <span class="cw-bp-top-stat-v">{{ bpFmt(m.fact) }}</span>
                  </div>
                  <div class="cw-bp-top-stat" v-if="m.pct !== null">
                    <span class="cw-bp-top-stat-l">Выполнение:</span>
                    <span class="cw-bp-top-stat-v" :style="`color: ${bpPctColor(m.pct)}; font-weight: 600`">
                      {{ m.pct }}%
                    </span>
                  </div>
                </div>
              </div>
            </div>

            <!-- Detailed table grouped -->
            <div class="cw-bp-table">
              <div class="cw-bp-table-header">
                <div class="cw-bp-th cw-bp-th-name">Метрика</div>
                <div class="cw-bp-th cw-bp-th-num">План</div>
                <div class="cw-bp-th cw-bp-th-num">Ожидание</div>
                <div class="cw-bp-th cw-bp-th-num">Факт</div>
                <div class="cw-bp-th cw-bp-th-pct">%</div>
              </div>

              <template v-for="grp in bpGroups" :key="grp.id">
                <div class="cw-bp-group-header">{{ grp.label }}</div>

                <div
                  v-for="row in grp.items"
                  :key="row.key"
                  class="cw-bp-row"
                  :class="{ 'cw-bp-row-auto': row.auto, 'cw-bp-row-sub': row.sub, 'cw-bp-row-final': row.key === 'profit' }"
                >
                  <div class="cw-bp-cell cw-bp-cell-name">
                    <span v-if="row.auto" class="cw-bp-auto-mark" title="Автоматически вычисляется">∑</span>
                    {{ row.label }}
                  </div>
                  <div class="cw-bp-cell cw-bp-cell-num">{{ bpFmt(row.plan) }}</div>
                  <div class="cw-bp-cell cw-bp-cell-num">{{ bpFmt(row.expect) }}</div>
                  <div class="cw-bp-cell cw-bp-cell-num cw-bp-cell-fact">{{ bpFmt(row.fact) }}</div>
                  <div class="cw-bp-cell cw-bp-cell-pct" :style="row.pct !== null ? `color: ${bpPctColor(row.pct)}` : ''">
                    {{ row.pct === null ? "—" : row.pct + "%" }}
                  </div>
                </div>
              </template>
            </div>
          </template>
        </div>

        <!-- ═══ GOVERNANCE TAB — real implementation ═══ -->
        <div v-else-if="activeTab === 'governance'" :key="'governance'" class="cw-gov-scroll">
          <div v-if="govLoading" class="cw-loading-state">
            <div class="cw-spinner"></div>
            <span>Загрузка корпоративного управления…</span>
          </div>

          <div v-else-if="govError" class="cw-error-state">
            <div class="cw-err-icon">⚠</div>
            <div>
              <div class="cw-err-title">Ошибка загрузки</div>
              <div class="cw-err-msg">{{ govError }}</div>
              <button class="cw-cta-btn" @click="loadGovernance()" style="margin-top: 12px">Повторить</button>
            </div>
          </div>

          <div v-else-if="!govDetail && govMembers.length === 0" class="cw-empty-state">
            <div class="cw-empty-icon">○</div>
            <div class="cw-empty-title">Данные не введены</div>
            <div class="cw-empty-msg">Для {{ company.name_short || company.name_ru }} в {{ year }} году данные о корп. управлении отсутствуют.</div>
            <RouterLink to="/governance" class="cw-cta-btn" style="margin-top: 12px">Открыть редактор →</RouterLink>
          </div>

          <template v-else>
            <!-- KPI grid -->
            <div class="cw-gov-kpis">
              <div
                v-for="kpi in govKpis"
                :key="kpi.label"
                class="cw-gov-kpi-card"
                :style="`--accent: ${kpi.color}`"
              >
                <div class="cw-gov-kpi-label">{{ kpi.label }}</div>
                <div class="cw-gov-kpi-value">{{ kpi.value }}</div>
                <div v-if="kpi.unit" class="cw-gov-kpi-unit">{{ kpi.unit }}</div>
              </div>
            </div>

            <!-- Committees -->
            <div class="cw-gov-section">
              <div class="cw-section-label">Комитеты совета</div>
              <div class="cw-gov-committees">
                <div
                  v-for="c in govCommittees"
                  :key="c.label"
                  class="cw-gov-committee"
                  :class="{ 'cw-gov-committee-on': c.present, 'cw-gov-committee-off': !c.present }"
                >
                  <span class="cw-gov-committee-icon">{{ c.present ? "✓" : "○" }}</span>
                  <span>{{ c.label }}</span>
                </div>
              </div>
            </div>

            <!-- Board members -->
            <div v-if="boardMembersByRole.length > 0" class="cw-gov-section">
              <div class="cw-section-label">
                Состав совета директоров ({{ boardMembersByRole.length }} {{ boardMembersByRole.length === 1 ? 'чел.' : 'чел.' }})
              </div>
              <div class="cw-gov-members">
                <div
                  v-for="m in boardMembersByRole"
                  :key="m.id"
                  class="cw-gov-member"
                >
                  <div class="cw-gov-avatar" :style="`background: ${m.roleColor}`">
                    {{ m.initials }}
                  </div>
                  <div class="cw-gov-member-info">
                    <div class="cw-gov-member-name">{{ m.fullName }}</div>
                    <div class="cw-gov-member-pos" v-if="m.position">{{ m.position }}</div>
                    <div class="cw-gov-member-meta">
                      <span class="cw-gov-role-pill" :style="`background: ${m.roleColor}22; color: ${m.roleColor}`">
                        {{ m.roleLabel }}
                      </span>
                      <span v-if="m.isIndependent" class="cw-gov-badge">Независимый</span>
                      <span v-if="m.isWoman" class="cw-gov-badge">♀</span>
                      <span v-if="m.isForeign" class="cw-gov-badge">Иностранец</span>
                    </div>
                    <div class="cw-gov-member-dates">
                      Назначен: {{ m.appointed }} · до {{ m.termEnd }}
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </template>
        </div>

        <!-- ═══ ESG TAB — real implementation ═══ -->
        <div v-else-if="activeTab === 'esg'" :key="'esg'" class="cw-esg-scroll">
          <div v-if="esgLoading" class="cw-loading-state">
            <div class="cw-spinner"></div>
            <span>Загрузка ESG-данных…</span>
          </div>

          <div v-else-if="esgError" class="cw-error-state">
            <div class="cw-err-icon">⚠</div>
            <div>
              <div class="cw-err-title">Ошибка загрузки</div>
              <div class="cw-err-msg">{{ esgError }}</div>
              <button class="cw-cta-btn" @click="loadEsg()" style="margin-top: 12px">Повторить</button>
            </div>
          </div>

          <div
            v-else-if="!esgDetail || (esgDetail.metrics?.length === 0 && esgIssues.length === 0)"
            class="cw-empty-state"
          >
            <div class="cw-empty-icon">○</div>
            <div class="cw-empty-title">ESG-данные не введены</div>
            <div class="cw-empty-msg">Для {{ company.name_short || company.name_ru }} в {{ year }} году метрики ESG отсутствуют.</div>
            <RouterLink to="/esg" class="cw-cta-btn" style="margin-top: 12px">Открыть редактор →</RouterLink>
          </div>

          <template v-else>
            <!-- 3 pillar cards -->
            <div class="cw-esg-pillars">
              <div
                v-for="p in esgPillarStats"
                :key="p.pillar"
                class="cw-esg-pillar-card"
                :style="`--accent: ${p.color}`"
              >
                <div class="cw-esg-pillar-letter">{{ p.label }}</div>
                <div class="cw-esg-pillar-name">{{ p.fullLabel }}</div>
                <div class="cw-esg-pillar-stats">
                  <div class="cw-esg-pillar-stat">
                    <div class="cw-esg-pillar-stat-v">{{ p.metricCount }}</div>
                    <div class="cw-esg-pillar-stat-l">метрик</div>
                  </div>
                  <div class="cw-esg-pillar-stat">
                    <div class="cw-esg-pillar-stat-v" :style="`color: ${esgPctColor(p.avgAttainment)}`">
                      {{ p.avgAttainment === null ? "—" : p.avgAttainment + "%" }}
                    </div>
                    <div class="cw-esg-pillar-stat-l">средн. достижение</div>
                  </div>
                </div>
                <div v-if="p.metricCount > 0" class="cw-esg-pillar-chips">
                  <span v-if="p.metricsOnTarget > 0" class="cw-esg-chip cw-esg-chip-good">
                    ✓ {{ p.metricsOnTarget }}
                  </span>
                  <span v-if="p.metricsBehind > 0" class="cw-esg-chip cw-esg-chip-bad">
                    ⚠ {{ p.metricsBehind }}
                  </span>
                </div>

                <!-- Sprint C · Sector benchmark line -->
                <div
                  v-if="esgSectorPillars[p.pillar] && esgSectorPillars[p.pillar].avgAttainment !== null"
                  class="cw-esg-pillar-bench"
                  :title="`${esgSectorLabel}: ${esgSectorPillars[p.pillar].companyCount} компаний с данными`"
                >
                  <span class="cw-esg-pillar-bench-cap">vs сектор:</span>
                  <span class="cw-esg-pillar-bench-v">{{ esgSectorPillars[p.pillar].avgAttainment }}%</span>
                  <span
                    v-if="p.avgAttainment !== null"
                    class="cw-esg-pillar-bench-diff"
                    :class="(p.avgAttainment - esgSectorPillars[p.pillar].avgAttainment!) >= 0 ? 'cw-esg-pillar-bench-up' : 'cw-esg-pillar-bench-down'"
                  >
                    {{ (p.avgAttainment - esgSectorPillars[p.pillar].avgAttainment!) >= 0 ? '▲' : '▼' }}
                    {{ Math.abs(p.avgAttainment - esgSectorPillars[p.pillar].avgAttainment!) }} п.п.
                  </span>
                </div>
              </div>
            </div>

            <!-- Metrics by pillar -->
            <template v-for="grp in esgMetricsByPillar" :key="grp.pillar">
              <div v-if="grp.metrics.length > 0" class="cw-esg-section">
                <div class="cw-section-label" :style="`color: ${grp.color}`">
                  {{ grp.label }} · {{ grp.metrics.length }} метрик
                </div>
                <div class="cw-esg-metrics">
                  <div
                    v-for="m in grp.metrics"
                    :key="m.id"
                    class="cw-esg-metric"
                    :style="`--accent: ${grp.color}`"
                  >
                    <div class="cw-esg-m-row1">
                      <div class="cw-esg-m-name" :title="m.metric_name">{{ m.metric_name }}</div>
                      <div v-if="m.pct !== null" class="cw-esg-m-pct" :style="`color: ${esgPctColor(m.pct)}`">
                        {{ m.pct }}%
                      </div>
                    </div>
                    <div class="cw-esg-m-row2">
                      <span class="cw-esg-m-stat">
                        <span class="cw-esg-m-stat-l">Факт:</span>
                        <span class="cw-esg-m-stat-v">{{ fmtEsgValue(m.value, m.unit) }}</span>
                      </span>
                      <span class="cw-esg-m-stat">
                        <span class="cw-esg-m-stat-l">Цель:</span>
                        <span class="cw-esg-m-stat-v">{{ fmtEsgValue(m.target, m.unit) }}</span>
                      </span>
                      <span v-if="m.benchmark !== null" class="cw-esg-m-stat">
                        <span class="cw-esg-m-stat-l">Бенч.:</span>
                        <span class="cw-esg-m-stat-v">{{ fmtEsgValue(m.benchmark, m.unit) }}</span>
                      </span>
                    </div>
                    <div v-if="m.pct !== null" class="cw-esg-m-bar-wrap">
                      <div
                        class="cw-esg-m-bar"
                        :style="`width: ${Math.min(100, m.pct)}%; background: ${esgPctColor(m.pct)}`"
                      ></div>
                    </div>
                  </div>
                </div>
              </div>
            </template>

            <!-- Issues -->
            <div v-if="esgIssuesView.length > 0" class="cw-esg-section">
              <div class="cw-section-label">
                ESG-инциденты · {{ esgIssuesView.length }}
                <span v-if="esgIssuesOpen.length > 0" style="color: var(--uza-red); font-weight: 600">
                  · {{ esgIssuesOpen.length }} в работе
                </span>
              </div>
              <div class="cw-esg-issues">
                <div
                  v-for="iss in esgIssuesView"
                  :key="iss.id"
                  class="cw-esg-issue"
                  :class="`cw-esg-issue-${iss.status}`"
                >
                  <div class="cw-esg-issue-header">
                    <span class="cw-esg-pillar-tag" :style="`background: ${iss.pillarColor}22; color: ${iss.pillarColor}`">
                      {{ iss.pillar || "—" }}
                    </span>
                    <span class="cw-esg-sev-pill" :style="`background: ${iss.severityColor}22; color: ${iss.severityColor}`">
                      {{ iss.severityLabel }}
                    </span>
                    <span class="cw-esg-status-pill" :style="`background: ${iss.statusColor}22; color: ${iss.statusColor}`">
                      {{ iss.statusLabel }}
                    </span>
                  </div>
                  <div class="cw-esg-issue-title">{{ iss.title }}</div>
                  <div v-if="iss.description" class="cw-esg-issue-desc">{{ iss.description }}</div>
                </div>
              </div>
            </div>
          </template>
        </div>

        <!-- ═══ CONSULTANTS TAB — directory + per-company integration TBD ═══ -->
        <div v-else-if="activeTab === 'consultants'" :key="'consultants'" class="cw-cons-scroll">
          <!-- ─── PER-COMPANY SECTION (primary view) ─── -->
          <div v-if="consPerCompanyLoading" class="cw-loading-state">
            <div class="cw-spinner"></div>
            <span>Загрузка консультантов компании…</span>
          </div>

          <div v-else-if="consPerCompanyError" class="cw-error-state">
            <div class="cw-err-icon">⚠</div>
            <div>
              <div class="cw-err-title">Ошибка загрузки</div>
              <div class="cw-err-msg">{{ consPerCompanyError }}</div>
              <button class="cw-cta-btn" @click="loadConsultantsPerCompany()" style="margin-top: 12px">Повторить</button>
            </div>
          </div>

          <template v-else>
            <!-- KPI strip — top stats -->
            <div v-if="consPerCompanyKpis" class="cw-cons-kpis">
              <div class="cw-cons-kpi">
                <div class="cw-cons-kpi-label">Консультантов</div>
                <div class="cw-cons-kpi-value">{{ consPerCompanyKpis.consultants }}</div>
              </div>
              <div class="cw-cons-kpi-divider"></div>
              <div class="cw-cons-kpi">
                <div class="cw-cons-kpi-label">Из них Big 4</div>
                <div class="cw-cons-kpi-value">{{ consPerCompanyKpis.big4 }}</div>
              </div>
              <div class="cw-cons-kpi-divider"></div>
              <div class="cw-cons-kpi">
                <div class="cw-cons-kpi-label">Назначений</div>
                <div class="cw-cons-kpi-value">{{ consPerCompanyKpis.assignments }}</div>
              </div>
              <div class="cw-cons-kpi-divider"></div>
              <div class="cw-cons-kpi">
                <div class="cw-cons-kpi-label">Выполнение задач</div>
                <div class="cw-cons-kpi-value" :style="`color: ${pctColor(consPerCompanyKpis.completionPct)}`">
                  {{ consPerCompanyKpis.completionPct }}%
                </div>
              </div>
            </div>

            <!-- Empty state — no consultants assigned to this company -->
            <div
              v-if="consPerCompany && consPerCompany.consultants.length === 0"
              class="cw-empty-state"
            >
              <div class="cw-empty-icon">○</div>
              <div class="cw-empty-title">Консультанты не назначены</div>
              <div class="cw-empty-msg">
                Для {{ company.name_short || company.name_ru }} в {{ year }} году консультанты не привязаны ни к одной задаче.
              </div>
              <p class="cw-empty-msg" style="margin-top: 8px; font-size: 11.5px">
                Чтобы добавить консультанта — откройте задачу в проекте и укажите консультанта в редакторе.
              </p>
            </div>

            <!-- Per-company consultants cards (rich) -->
            <div v-else class="cw-cons-cards">
              <div
                v-for="c in (consPerCompany?.consultants || [])"
                :key="c.id"
                class="cw-cons-card-rich"
                :style="`--accent: ${c.color || '#7F77DD'}`"
              >
                <!-- Header -->
                <div class="cw-cons-rich-header">
                  <div class="cw-cons-rich-abbr">{{ c.abbr || c.code.toUpperCase() }}</div>
                  <div class="cw-cons-rich-titles">
                    <div class="cw-cons-rich-name">
                      {{ c.name }}
                      <span v-if="c.is_big4" class="cw-cons-rich-big4">Big 4</span>
                    </div>
                    <div class="cw-cons-rich-stats">
                      <span class="cw-cons-rich-stat">{{ c.task_count }} {{ c.task_count === 1 ? 'задача' : 'задач' }}</span>
                      <span class="cw-cons-rich-stat">·</span>
                      <span class="cw-cons-rich-stat" style="color: var(--uza-teal)">✓ {{ c.task_done }}</span>
                      <span v-if="c.task_overdue > 0" class="cw-cons-rich-stat" style="color: var(--uza-red)">
                        ⚠ {{ c.task_overdue }} просрочено
                      </span>
                    </div>
                  </div>
                  <div class="cw-cons-rich-pct" :style="`color: ${pctColor(c.completion_pct)}`">
                    {{ c.completion_pct }}%
                  </div>
                </div>

                <!-- Sources tags -->
                <div v-if="c.sources.length > 0" class="cw-cons-rich-sources">
                  <span
                    v-for="src in c.sources"
                    :key="src"
                    class="cw-cons-rich-source"
                  >
                    {{ getSourceLabel(src) }}
                  </span>
                </div>

                <!-- Sample projects -->
                <div v-if="c.projects.length > 0" class="cw-cons-rich-projects">
                  <div class="cw-cons-rich-projects-label">
                    {{ c.task_count > 5 ? `Последние 5 из ${c.task_count} задач` : 'Задачи' }}
                  </div>
                  <div
                    v-for="p in c.projects"
                    :key="p.id"
                    class="cw-cons-rich-project"
                    @click="$router.push(`/project/${p.id}`)"
                    :title="p.title"
                  >
                    <span class="cw-cons-rich-project-status" :style="`color: ${getStatusColor(p.status)}`">
                      {{ getStatusShortLabel(p.status) }}
                    </span>
                    <span class="cw-cons-rich-project-title">{{ p.title }}</span>
                    <span v-if="p.due_date" class="cw-cons-rich-project-date">{{ fmtDate(p.due_date) }}</span>
                  </div>
                </div>
              </div>
            </div>

            <!-- ─── COLLAPSIBLE FULL DIRECTORY ─── -->
            <div class="cw-cons-dir-section">
              <button class="cw-cons-dir-toggle" @click="toggleConsDirectory()">
                <span class="cw-cons-dir-toggle-icon" :class="{ open: consDirectoryExpanded }">›</span>
                <span>Полный справочник консультантов в системе</span>
                <span v-if="consDirectoryLoaded" class="cw-cons-dir-count">{{ consDirectoryByGroup.total }}</span>
              </button>

              <div v-if="consDirectoryExpanded" class="cw-cons-dir-body">
                <div v-if="consDirectoryLoading" class="cw-loading-state" style="padding: 30px">
                  <div class="cw-spinner"></div>
                  <span>Загрузка справочника…</span>
                </div>

                <div v-else-if="consDirectoryError" class="cw-error-state">
                  <div class="cw-err-icon">⚠</div>
                  <div>
                    <div class="cw-err-msg">{{ consDirectoryError }}</div>
                  </div>
                </div>

                <template v-else>
                  <div v-if="consDirectoryByGroup.big4.length > 0" class="cw-cons-group">
                    <div class="cw-section-label">Big 4 · {{ consDirectoryByGroup.big4.length }}</div>
                    <div class="cw-cons-grid">
                      <div
                        v-for="c in consDirectoryByGroup.big4"
                        :key="c.id"
                        class="cw-cons-card"
                        :style="`--accent: ${c.color_hex || '#7F77DD'}`"
                      >
                        <div class="cw-cons-abbr">{{ c.abbr || c.code.toUpperCase() }}</div>
                        <div class="cw-cons-name">{{ c.name_ru }}</div>
                        <div v-if="c.name_en" class="cw-cons-name-en">{{ c.name_en }}</div>
                        <div class="cw-cons-tag-big4">Big 4</div>
                      </div>
                    </div>
                  </div>

                  <div v-if="consDirectoryByGroup.other.length > 0" class="cw-cons-group" style="margin-top: 16px">
                    <div class="cw-section-label">Другие · {{ consDirectoryByGroup.other.length }}</div>
                    <div class="cw-cons-grid">
                      <div
                        v-for="c in consDirectoryByGroup.other"
                        :key="c.id"
                        class="cw-cons-card"
                        :style="`--accent: ${c.color_hex || '#94A3B8'}`"
                      >
                        <div class="cw-cons-abbr">{{ c.abbr || c.code.toUpperCase() }}</div>
                        <div class="cw-cons-name">{{ c.name_ru }}</div>
                        <div v-if="c.name_en" class="cw-cons-name-en">{{ c.name_en }}</div>
                      </div>
                    </div>
                  </div>

                  <div v-if="consDirectoryByGroup.total === 0" class="cw-empty-state">
                    <div class="cw-empty-icon">○</div>
                    <div class="cw-empty-title">Справочник пуст</div>
                    <div class="cw-empty-msg">Консультанты не добавлены в систему.</div>
                  </div>
                </template>
              </div>
            </div>
          </template>
        </div>

        <!-- ═══ CREDIT PORTFOLIO TAB — real implementation ═══ -->
        <div v-else-if="activeTab === 'credit'" :key="'credit'" class="cw-cred-scroll">
          <div v-if="creditLoading" class="cw-loading-state">
            <div class="cw-spinner"></div>
            <span>Загрузка кредитного портфеля…</span>
          </div>

          <div v-else-if="creditError" class="cw-error-state">
            <div class="cw-err-icon">⚠</div>
            <div>
              <div class="cw-err-title">Ошибка загрузки</div>
              <div class="cw-err-msg">{{ creditError }}</div>
              <button class="cw-cta-btn" @click="loadCredit()" style="margin-top: 12px">Повторить</button>
            </div>
          </div>

          <div v-else-if="creditLoans.length === 0" class="cw-empty-state">
            <div class="cw-empty-icon">○</div>
            <div class="cw-empty-title">Кредитов нет</div>
            <div class="cw-empty-msg">У {{ company.name_short || company.name_ru }} нет активных кредитов в портфеле.</div>
            <RouterLink to="/credit-portfolio" class="cw-cta-btn" style="margin-top: 12px">Открыть полный портфель →</RouterLink>
          </div>

          <template v-else>
            <!-- KPI strip -->
            <div class="cw-cred-kpis">
              <div class="cw-cred-kpi">
                <div class="cw-cred-kpi-label">Активных кредитов</div>
                <div class="cw-cred-kpi-value">{{ creditKpis.total }}</div>
              </div>
              <div class="cw-cred-kpi-divider"></div>
              <div class="cw-cred-kpi">
                <div class="cw-cred-kpi-label">Общая задолженность</div>
                <div class="cw-cred-kpi-value">{{ fmtUsd(creditKpis.totalDebt) }}</div>
              </div>
              <div class="cw-cred-kpi-divider"></div>
              <div class="cw-cred-kpi">
                <div class="cw-cred-kpi-label">Гарантированных</div>
                <div class="cw-cred-kpi-value">{{ creditKpis.guaranteed }}</div>
              </div>
              <div class="cw-cred-kpi-divider"></div>
              <div class="cw-cred-kpi">
                <div class="cw-cred-kpi-label">Средняя ставка</div>
                <div class="cw-cred-kpi-value">{{ fmtRate(creditKpis.avgRate) }}</div>
              </div>
            </div>

            <!-- Lender type breakdown -->
            <div v-if="creditByLender.length > 0" class="cw-cred-section">
              <div class="cw-section-label">По типу кредитора</div>
              <div class="cw-cred-buckets">
                <div
                  v-for="b in creditByLender"
                  :key="b.key"
                  class="cw-cred-bucket"
                  :style="`--accent: ${b.color}`"
                  :title="`${b.label} · ${b.count} ${b.count === 1 ? 'кредит' : 'кредитов'} · долг ${fmtUsd(b.debt)} (${b.pct}% от портфеля)`"
                >
                  <div class="cw-cred-bucket-row">
                    <span class="cw-cred-bucket-dot" :style="`background: ${b.color}`"></span>
                    <span class="cw-cred-bucket-label">{{ b.label }}</span>
                    <span class="cw-cred-bucket-count">{{ b.count }}</span>
                    <span class="cw-cred-bucket-debt">{{ fmtUsd(b.debt) }}</span>
                    <span class="cw-cred-bucket-pct">{{ b.pct }}%</span>
                  </div>
                  <div class="cw-cred-bucket-bar">
                    <div class="cw-cred-bucket-bar-fill" :style="`width: ${b.pct}%; background: ${b.color}`"></div>
                  </div>
                </div>
              </div>
            </div>

            <!-- Currency breakdown -->
            <div v-if="creditByCurrency.length > 0" class="cw-cred-section">
              <div class="cw-section-label">По валюте</div>
              <div class="cw-cred-currencies">
                <div
                  v-for="c in creditByCurrency"
                  :key="c.key"
                  class="cw-cred-currency"
                  :style="`--accent: ${c.color}`"
                >
                  <div class="cw-cred-currency-code" :style="`color: ${c.color}`">{{ c.label }}</div>
                  <div class="cw-cred-currency-debt">{{ fmtUsd(c.debt) }}</div>
                  <div class="cw-cred-currency-meta">{{ c.count }} {{ c.count === 1 ? 'кредит' : 'кредитов' }} · {{ c.pct }}%</div>
                </div>
              </div>
            </div>

            <!-- Sprint B · Maturity ladder (waterfall by time-to-due bucket) -->
            <div v-if="creditMaturityLadder.length > 0" class="cw-cred-section">
              <div class="cw-section-label">Maturity ladder · по срокам погашения</div>
              <div class="cw-cred-ladder">
                <div
                  v-for="b in creditMaturityLadder"
                  :key="b.key"
                  class="cw-cred-ladder-row"
                  :style="`--accent: ${b.color}`"
                  :title="`${b.label}: ${b.count} ${b.count === 1 ? 'кредит' : 'кредитов'} · ${fmtUsd(b.debt)}`"
                >
                  <div class="cw-cred-ladder-label">{{ b.label }}</div>
                  <div class="cw-cred-ladder-bar-track">
                    <div
                      class="cw-cred-ladder-bar-fill"
                      :style="`width: ${Math.round((b.pct / creditMaturityMaxPct) * 100)}%; background: ${b.color}`"
                    ></div>
                  </div>
                  <div class="cw-cred-ladder-debt">{{ fmtUsd(b.debt) }}</div>
                  <div class="cw-cred-ladder-meta">
                    <span :data-countup="b.count" data-cu-d="0">0</span> ·
                    <span :data-countup="b.pct" data-cu-d="0">0</span>%
                  </div>
                </div>
              </div>
            </div>

            <!-- Top loans table -->
            <div class="cw-cred-section">
              <div class="cw-section-label">Кредиты ({{ creditTopLoans.length }})</div>
              <div class="cw-cred-table">
                <div class="cw-cred-table-header">
                  <div class="cw-cred-th cw-cred-th-code">Код</div>
                  <div class="cw-cred-th cw-cred-th-bank">Банк / Кредитор</div>
                  <div class="cw-cred-th cw-cred-th-cur">Вал.</div>
                  <div class="cw-cred-th cw-cred-th-rate">Ставка</div>
                  <div class="cw-cred-th cw-cred-th-debt">Задолж. $</div>
                  <div class="cw-cred-th cw-cred-th-due">Погашение</div>
                </div>
                <div
                  v-for="l in creditTopLoans"
                  :key="l.id"
                  class="cw-cred-row"
                  :class="{ 'cw-cred-row-overdue': l.is_overdue }"
                >
                  <div class="cw-cred-cell cw-cred-cell-code">
                    {{ l.loan_code }}
                    <span v-if="l.is_guaranteed" class="cw-cred-guaranteed" title="Гарантированный">G</span>
                  </div>
                  <div class="cw-cred-cell cw-cred-cell-bank" :title="l.bank">
                    <span class="cw-cred-lender-pill" :style="`background: ${l.lender_color}22; color: ${l.lender_color}`">
                      {{ l.lender_label }}
                    </span>
                    <span class="cw-cred-bank-name">{{ l.bank_short }}</span>
                  </div>
                  <div class="cw-cred-cell cw-cred-cell-cur">
                    <span class="cw-cred-cur-pill" :style="`color: ${cpCurrencyColor(l.currency)}`">{{ l.currency }}</span>
                  </div>
                  <div class="cw-cred-cell cw-cred-cell-rate">{{ l.rateText }}</div>
                  <div class="cw-cred-cell cw-cred-cell-debt">{{ fmtUsd(l.debt_usd) }}</div>
                  <div class="cw-cred-cell cw-cred-cell-due" :class="{ 'overdue': l.is_overdue }">
                    {{ l.date_due_short }}
                  </div>
                </div>
              </div>
            </div>
          </template>
        </div>

        <!-- ═══ INVEST PROJECTS TAB — embedded reuse of InvestProjects view ═══ -->
        <div v-else-if="activeTab === 'invest'" :key="'invest'" class="cw-invest-scroll">
          <InvestProjectsView
            embedded
            :company-name="company.name_short || company.name_ru"
          />
        </div>

        <!-- ═══ PROCUREMENT TAB — real implementation ═══ -->
        <div v-else-if="activeTab === 'procurement'" :key="'procurement'" class="cw-proc-scroll">
          <div v-if="procLoading" class="cw-loading-state">
            <div class="cw-spinner"></div>
            <span>Загрузка анализа закупок {{ year }}…</span>
          </div>

          <div v-else-if="procError" class="cw-error-state">
            <div class="cw-err-icon">⚠</div>
            <div>
              <div class="cw-err-title">Ошибка загрузки</div>
              <div class="cw-err-msg">{{ procError }}</div>
              <button class="cw-cta-btn" @click="loadProc()" style="margin-top: 12px">Повторить</button>
            </div>
          </div>

          <div v-else-if="procPurchases.length === 0" class="cw-empty-state">
            <div class="cw-empty-icon">○</div>
            <div class="cw-empty-title">Закупки не загружены</div>
            <div class="cw-empty-msg">
              У {{ company.name_short || company.name_ru }} в {{ year }} году нет данных по закупкам в системе.
            </div>
            <RouterLink to="/procurement/analysis" class="cw-cta-btn" style="margin-top: 12px">Открыть полный анализ →</RouterLink>
          </div>

          <template v-else>
            <!-- KPI strip -->
            <div v-if="procCompanyKpis" class="cw-proc-kpis">
              <div class="cw-proc-kpi">
                <div class="cw-proc-kpi-label">Закрытий</div>
                <div class="cw-proc-kpi-value">{{ procCompanyKpis.total }}</div>
                <div v-if="procCompanyKpis.dirty > 0" class="cw-proc-kpi-meta">
                  чистых: {{ procCompanyKpis.clean }} · отбраковано: {{ procCompanyKpis.dirty }}
                </div>
              </div>
              <div class="cw-proc-kpi-divider"></div>
              <div class="cw-proc-kpi">
                <div class="cw-proc-kpi-label">Переплата</div>
                <div class="cw-proc-kpi-value" style="color: var(--uza-red)">
                  {{ paFmtMoneyShort(procCompanyKpis.totalOverpay) }}
                </div>
                <div class="cw-proc-kpi-meta">UZS, к рынку</div>
              </div>
              <div class="cw-proc-kpi-divider"></div>
              <div class="cw-proc-kpi">
                <div class="cw-proc-kpi-label">Выше рынка</div>
                <div
                  class="cw-proc-kpi-value"
                  :style="`color: ${paColorByDev(procCompanyKpis.aboveMarketPct)}`"
                >
                  {{ procCompanyKpis.aboveMarketPct }}%
                </div>
                <div class="cw-proc-kpi-meta">закупок &gt; +3%</div>
              </div>
              <div class="cw-proc-kpi-divider"></div>
              <div class="cw-proc-kpi">
                <div class="cw-proc-kpi-label">Медианное отклон.</div>
                <div
                  class="cw-proc-kpi-value"
                  :style="`color: ${paColorByDev(procCompanyKpis.medianDev)}`"
                >
                  {{ fmt.fmtPercent(procCompanyKpis.medianDev, { decimals: 1, signed: true }) }}
                </div>
              </div>
              <div v-if="procCompanyRow" class="cw-proc-kpi-divider"></div>
              <div v-if="procCompanyRow" class="cw-proc-kpi">
                <div class="cw-proc-kpi-label">Ранг в портфеле</div>
                <div class="cw-proc-kpi-value">#{{ procCompanyRow.rank }}</div>
              </div>
            </div>

            <!-- Best / Worst categories -->
            <div class="cw-proc-cats-row" v-if="procWorstCats.length > 0 || procBestCats.length > 0">
              <div v-if="procWorstCats.length > 0" class="cw-proc-cats-block">
                <div class="cw-section-label" style="color: var(--uza-red)">
                  Проблемные категории · {{ procWorstCats.length }}
                </div>
                <div class="cw-proc-cats">
                  <div
                    v-for="c in procWorstCats"
                    :key="c.id"
                    class="cw-proc-cat"
                    :style="`--accent: ${c.color}`"
                  >
                    <div class="cw-proc-cat-name" :title="c.name">{{ c.short }}</div>
                    <div class="cw-proc-cat-stats">
                      <span class="cw-proc-cat-dev" :style="`color: ${c.color}`">
                        {{ fmt.fmtPercent(c.deviation, { decimals: 1, signed: true }) }}
                      </span>
                      <span class="cw-proc-cat-count">{{ c.closure_count }} закр.</span>
                    </div>
                  </div>
                </div>
              </div>
              <div v-if="procBestCats.length > 0" class="cw-proc-cats-block">
                <div class="cw-section-label" style="color: var(--uza-teal)">
                  Лучшие категории · {{ procBestCats.length }}
                </div>
                <div class="cw-proc-cats">
                  <div
                    v-for="c in procBestCats"
                    :key="c.id"
                    class="cw-proc-cat"
                    :style="`--accent: ${c.color}`"
                  >
                    <div class="cw-proc-cat-name" :title="c.name">{{ c.short }}</div>
                    <div class="cw-proc-cat-stats">
                      <span class="cw-proc-cat-dev" :style="`color: ${c.color}`">
                        {{ fmt.fmtPercent(c.deviation, { decimals: 1, signed: true }) }}
                      </span>
                      <span class="cw-proc-cat-count">{{ c.closure_count }} закр.</span>
                    </div>
                  </div>
                </div>
              </div>
            </div>

            <!-- Sprint C · Supplier concentration (top-5 share + single-source warning) -->
            <div v-if="procSupplierConcentration.top.length > 0" class="cw-proc-section">
              <div class="cw-section-label">
                Концентрация поставщиков · топ-{{ procSupplierConcentration.top.length }} из {{ procSupplierConcentration.totalSuppliers }}
                <span
                  v-if="procSupplierConcentration.isSingleSource"
                  class="cw-proc-supplier-flag cw-proc-supplier-flag-warn"
                  title="Один поставщик забирает ≥80% объёма — high concentration risk"
                >⚠ single-source</span>
              </div>

              <!-- Stacked horizontal bar showing top-5 cumulative share -->
              <div class="cw-proc-supplier-bar" :title="`Топ-5 = ${fmt.fmtPercent(procSupplierConcentration.top5Share, { decimals: 1 })} от общего объёма`">
                <div
                  v-for="b in procSupplierConcentration.top"
                  :key="b.supplier"
                  class="cw-proc-supplier-bar-seg"
                  :style="`width: ${b.pct}%; background: ${b.color}`"
                  :title="`${b.supplier} · ${b.pct}% (${b.count} закр.)`"
                ></div>
                <div
                  v-if="procSupplierConcentration.otherMoney > 0"
                  class="cw-proc-supplier-bar-seg cw-proc-supplier-bar-other"
                  :style="`width: ${(100 - procSupplierConcentration.top5Share).toFixed(1)}%`"
                  :title="`Другие (${procSupplierConcentration.otherCount} закр.)`"
                ></div>
              </div>

              <!-- Detail rows -->
              <div class="cw-proc-supplier-list">
                <div
                  v-for="b in procSupplierConcentration.top"
                  :key="b.supplier"
                  class="cw-proc-supplier-row"
                  :style="`--accent: ${b.color}`"
                >
                  <span class="cw-proc-supplier-dot" :style="`background: ${b.color}`"></span>
                  <span class="cw-proc-supplier-name" :title="b.supplier">{{ b.supplier }}</span>
                  <span class="cw-proc-supplier-count">
                    <span :data-countup="b.count" data-cu-d="0">0</span> закр.
                  </span>
                  <span class="cw-proc-supplier-pct">
                    <span :data-countup="b.pct" data-cu-d="1">0</span>%
                  </span>
                </div>
                <div
                  v-if="procSupplierConcentration.otherMoney > 0"
                  class="cw-proc-supplier-row cw-proc-supplier-row-other"
                >
                  <span class="cw-proc-supplier-dot" style="background: #94A3B8"></span>
                  <span class="cw-proc-supplier-name">Остальные ({{ procSupplierConcentration.totalSuppliers - procSupplierConcentration.top.length }} поставщиков)</span>
                  <span class="cw-proc-supplier-count">{{ procSupplierConcentration.otherCount }} закр.</span>
                  <span class="cw-proc-supplier-pct">{{ fmt.fmtPercent(100 - procSupplierConcentration.top5Share, { decimals: 1 }) }}</span>
                </div>
              </div>
            </div>

            <!-- Top deviating purchases -->
            <div class="cw-proc-section">
              <div class="cw-section-label">
                Топ-{{ procRecentPurchases.length }} закупок по отклонению от рынка
              </div>
              <div class="cw-proc-purchases">
                <div class="cw-proc-purchases-header">
                  <div class="cw-proc-ph cw-proc-ph-name">Товар</div>
                  <div class="cw-proc-ph cw-proc-ph-supplier">Поставщик</div>
                  <div class="cw-proc-ph cw-proc-ph-price">Цена</div>
                  <div class="cw-proc-ph cw-proc-ph-market">Рынок</div>
                  <div class="cw-proc-ph cw-proc-ph-dev">Откл.</div>
                </div>
                <div
                  v-for="p in procRecentPurchases"
                  :key="p.id"
                  class="cw-proc-purchase"
                  :style="`--dev-color: ${paColorByDev(p.deviation_pct)}`"
                >
                  <div class="cw-proc-pcell cw-proc-pcell-name" :title="p.product_name || ''">
                    <div class="cw-proc-product">{{ p.product_name || '—' }}</div>
                    <div class="cw-proc-cat-tag">{{ p.category_name }}</div>
                  </div>
                  <div class="cw-proc-pcell cw-proc-pcell-supplier" :title="p.supplier || ''">
                    {{ p.supplier || '—' }}
                  </div>
                  <div class="cw-proc-pcell cw-proc-pcell-price">{{ paFmtMoney(p.unit_price) }}</div>
                  <div class="cw-proc-pcell cw-proc-pcell-market">{{ paFmtMoney(p.market_avg) }}</div>
                  <div
                    class="cw-proc-pcell cw-proc-pcell-dev"
                    :style="`color: ${paColorByDev(p.deviation_pct)}`"
                  >
                    {{ fmt.fmtPercent(p.deviation_pct, { decimals: 1, signed: true }) }}
                  </div>
                </div>
              </div>
            </div>
          </template>
        </div>

        <!-- ═══ FINANCIALS TAB (МСФО + НСБУ — shared logic via financialsStandard) ═══ -->
        <div v-else-if="activeTab === 'ifrs' || activeTab === 'nsbu'" :key="activeTab" class="cw-fin-scroll">
          <div v-if="finLoading" class="cw-loading-state">
            <div class="cw-spinner"></div>
            <span>Загрузка отчётности по {{ finStandardLabel }}…</span>
          </div>

          <div v-else-if="finError" class="cw-error-state">
            <div class="cw-err-icon">⚠</div>
            <div>
              <div class="cw-err-title">Ошибка загрузки</div>
              <div class="cw-err-msg">{{ finError }}</div>
              <button class="cw-cta-btn" @click="loadFinReports()" style="margin-top: 12px">Повторить</button>
            </div>
          </div>

          <div v-else-if="finReports.length === 0" class="cw-empty-state">
            <div class="cw-empty-icon">○</div>
            <div class="cw-empty-title">Отчётность по {{ finStandardLabel }} не загружена</div>
            <div class="cw-empty-msg">
              Для {{ company.name_short || company.name_ru }} в {{ year }} году
              нет отчётов по {{ finStandardLabel }}.
            </div>
            <RouterLink to="/financials" class="cw-cta-btn" style="margin-top: 12px">
              Открыть редактор отчётности →
            </RouterLink>
          </div>

          <template v-else>
            <!-- Sprint A · Sticky KPI-strip (Revenue / EBITDA / NP / ROE / ROA / D-E / ER) -->
            <section v-if="finKpis.length > 0" class="cw-fin-kpi-strip">
              <div
                v-for="k in finKpis"
                :key="k.key"
                class="cw-fin-kpi-tile"
                :class="`cw-fin-kpi-${k.tone}`"
              >
                <div class="cw-fin-kpi-label">{{ k.label }}</div>
                <div class="cw-fin-kpi-value">
                  {{ fmtFinKpi(k.value, k.unit) }}
                  <span v-if="k.unit !== '%' && k.unit !== 'x'" class="cw-fin-kpi-unit">{{ k.unit }}</span>
                </div>
                <div v-if="k.hint" class="cw-fin-kpi-hint">{{ k.hint }}</div>
              </div>
            </section>

            <!-- Report type switcher (BS / PL / CF) -->
            <div class="cw-fin-type-bar">
              <div class="cw-fin-type-label">Отчёт:</div>
              <button
                v-for="t in finAvailableTypes"
                :key="t.type"
                class="cw-fin-type-btn"
                :class="{
                  active: finReportType === t.type,
                  disabled: !t.available,
                }"
                :disabled="!t.available"
                @click="t.available && selectFinReportType(t.type)"
              >
                {{ t.label }}
                <span v-if="!t.available" class="cw-fin-type-na">нет данных</span>
              </button>
            </div>

            <!-- Loading full report -->
            <div v-if="finFullLoading" class="cw-loading-state" style="padding: 30px">
              <div class="cw-spinner"></div>
              <span>Загрузка строк отчёта…</span>
            </div>

            <!-- Full report -->
            <template v-else-if="finFullReport">
              <!-- Metadata strip -->
              <div class="cw-fin-meta">
                <div class="cw-fin-meta-item">
                  <div class="cw-fin-meta-label">Стандарт</div>
                  <div class="cw-fin-meta-value">{{ finStandardLabel }}</div>
                </div>
                <div class="cw-fin-meta-divider"></div>
                <div class="cw-fin-meta-item">
                  <div class="cw-fin-meta-label">Период</div>
                  <div class="cw-fin-meta-value">
                    {{ finFullReport.year }}{{ finFullReport.quarter ? ` · Q${finFullReport.quarter}` : "" }}
                  </div>
                </div>
                <div class="cw-fin-meta-divider"></div>
                <div class="cw-fin-meta-item">
                  <div class="cw-fin-meta-label">Валюта</div>
                  <div class="cw-fin-meta-value">{{ finFullReport.currency }}</div>
                </div>
                <div class="cw-fin-meta-divider"></div>
                <div class="cw-fin-meta-item">
                  <div class="cw-fin-meta-label">Ед. изм.</div>
                  <div class="cw-fin-meta-value">{{ getUnitScaleLabel(finFullReport.unit_scale) }}</div>
                </div>
                <div class="cw-fin-meta-divider"></div>
                <div class="cw-fin-meta-item">
                  <div class="cw-fin-meta-label">Источник</div>
                  <div class="cw-fin-meta-value cw-fin-meta-source" :title="finFullReport.source">
                    {{ fmtSourceLabel(finFullReport.source) }}
                  </div>
                </div>
                <div class="cw-fin-meta-divider"></div>
                <div class="cw-fin-meta-item">
                  <div class="cw-fin-meta-label">Обновлено</div>
                  <div class="cw-fin-meta-value">{{ fmtFinUpdated(finFullReport.updated_at) }}</div>
                </div>
                <div v-if="finFullReport.is_audited" class="cw-fin-audited-badge">
                  <span>✓</span> Аудитировано
                </div>
              </div>

              <!-- Lines table -->
              <div v-if="finLinesView.length > 0" class="cw-fin-table">
                <div class="cw-fin-table-header">
                  <div class="cw-fin-th cw-fin-th-name">Строка</div>
                  <div class="cw-fin-th cw-fin-th-value">
                    Значение, {{ getUnitScaleLabel(finFullReport.unit_scale) }} {{ finFullReport.currency }}
                  </div>
                </div>
                <div
                  v-for="line in finLinesView"
                  :key="line.line_code"
                  class="cw-fin-row"
                  :class="{
                    'cw-fin-row-subtotal': line.is_subtotal,
                    'cw-fin-row-calculated': line.is_calculated,
                    'cw-fin-row-zero': line.valueNum === 0 && !line.is_subtotal,
                  }"
                  :style="`--depth: ${line.depth}`"
                >
                  <div class="cw-fin-cell-name">
                    <span v-if="line.line_code" class="cw-fin-code">{{ line.line_code }}</span>
                    <span class="cw-fin-name">{{ line.line_name }}</span>
                    <span v-if="line.is_calculated" class="cw-fin-calc-mark" title="Вычисляется">∑</span>
                  </div>
                  <div class="cw-fin-cell-value" :class="{ 'cw-fin-value-negative': line.valueNum < 0 }">
                    {{ fmtFinValue(line.valueNum, finFullReport.unit_scale) }}
                  </div>
                </div>
              </div>

              <!-- Notes -->
              <div v-if="finFullReport.notes" class="cw-fin-section">
                <div class="cw-section-label">Примечания</div>
                <p class="cw-fin-notes">{{ finFullReport.notes }}</p>
              </div>
            </template>
          </template>
        </div>

        <!-- ═══ 9 GLOBAL-PAGE PLACEHOLDER TABS ═══ -->
        <div v-else :key="'placeholder-' + activeTab" class="cw-tab-placeholder">
          <div class="cw-cta-card" v-if="currentTabDef">
            <svg class="cw-cta-icon" width="48" height="48" viewBox="0 0 24 24"
                 fill="none" stroke="currentColor" stroke-width="1.5"
                 stroke-linecap="round" stroke-linejoin="round"
                 v-html="getIconPath(currentTabDef.key)"></svg>
            <h2>{{ currentTabDef.label }}</h2>
            <p>Раздел «{{ currentTabDef.label }}» для {{ company.name_short || company.name_ru }}</p>
            <p class="cw-cta-note">
              Полная функциональность доступна на глобальной странице.<br>
              Фильтрация по компании — в следующих сессиях.
            </p>
            <RouterLink
              v-if="currentTabDef.fullPageRoute"
              :to="currentTabDef.fullPageRoute"
              class="cw-cta-btn"
            >
              Открыть полную страницу «{{ currentTabDef.label }}» →
            </RouterLink>
          </div>
        </div>
        </Transition>
      </main>

    <!-- v10.1: TaskProjectEditor -->
    <TaskProjectEditor
      v-if="editorOpen && editorEntity"
      :entity="(editorEntity as any)"
      :kind="editorKind"
      @close="onEditorClose"
      @saved="onEditorSaved"
    />

    <!-- Sprint A · Overdue drill modal -->
    <Transition name="cw-modal">
      <div
        v-if="overdueModalOpen"
        class="cw-ov-modal-backdrop"
        @click.self="closeOverdueModal"
      >
        <div class="cw-ov-modal-card" role="dialog" aria-modal="true" aria-label="Просроченные задачи и проекты">
          <header class="cw-ov-modal-head">
            <div>
              <div class="cw-ov-modal-eyebrow">Требуют внимания</div>
              <h3 class="cw-ov-modal-title">
                Просрочено: <span class="cw-ov-modal-num">{{ overdueItems.length }}</span>
              </h3>
            </div>
            <button class="cw-ov-modal-close" @click="closeOverdueModal" title="Закрыть">×</button>
          </header>
          <div class="cw-ov-modal-body">
            <div v-if="overdueItems.length === 0" class="cw-ov-modal-empty">
              Просроченных нет — всё по графику.
            </div>
            <ul v-else class="cw-ov-list">
              <li
                v-for="r in overdueItems"
                :key="`${r.kind}-${r.id}`"
                class="cw-ov-row"
                :class="`cw-ov-row-${r.kind}`"
              >
                <div class="cw-ov-row-l">
                  <div class="cw-ov-row-tag">{{ r.kind === "project" ? "ПРОЕКТ" : "ЗАДАЧА" }}</div>
                  <div class="cw-ov-row-title">{{ r.title }}</div>
                  <div v-if="r.owner" class="cw-ov-row-owner">{{ r.owner }}</div>
                </div>
                <div class="cw-ov-row-r">
                  <div class="cw-ov-row-days">+{{ r.daysOverdue }} дн</div>
                  <div v-if="r.due_date" class="cw-ov-row-date">срок {{ new Date(r.due_date).toLocaleDateString("ru-RU") }}</div>
                  <RouterLink
                    v-if="r.link"
                    :to="r.link"
                    class="cw-ov-row-link"
                    @click="closeOverdueModal"
                  >→</RouterLink>
                </div>
              </li>
            </ul>
          </div>
        </div>
      </div>
    </Transition>
    </template>

    <!-- BP editor modal (lazy-mounted; reuses /business-plan editor 1:1) -->
    <BpEditor
      v-if="bpEditorOpen && company"
      :company-id="company.id"
      :company-name="company.name_short || company.name_ru || ''"
      :year="year"
      @close="bpEditorOpen = false"
      @saved="onBpEditorSaved"
    />

    <!-- KPI editor modal (lazy-mounted; reuses /kpi editor 1:1) -->
    <KpiEditor
      v-if="kpiEditorOpen && company"
      :company-id="company.id"
      :company-name="company.name_short || company.name_ru || ''"
      :year="year"
      @close="kpiEditorOpen = false"
      @saved="onKpiEditorSaved"
    />
  </div>
</template>

<style scoped>
/* ═══ UzAssets palette ═══ */
.cw-page {
  --uza-purple: #7F77DD;
  --uza-teal:   #1D9E75;
  --uza-amber:  #EF9F27;
  --uza-blue:   #378ADD;
  --uza-red:    #E24B4A;
  --uza-navy:   #1E2A4A;
  --uza-gray:   #888780;
  --uza-bg:     #FAFAFB;
  --uza-bg2:    #F5F4F0;
  --uza-bg3:    #EFEEE9;
  --uza-bg4:    #E2E2DC;
  --uza-border: rgba(15, 23, 60, 0.08);

  display: flex;
  flex-direction: column;
  min-height: 100vh;
  background: var(--uza-bg);
  font-family: ui-sans-serif, system-ui, -apple-system, "Segoe UI", Roboto, sans-serif;
}

/* ═══ Loading & Error ═══ */
.cw-loading {
  display: flex; align-items: center; justify-content: center;
  flex-direction: column; gap: 14px;
  flex: 1;
  color: var(--uza-gray);
  font-size: 13px;
}
.cw-spinner {
  width: 28px; height: 28px;
  border: 2.5px solid var(--uza-bg3);
  border-top-color: var(--uza-purple);
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
}
@keyframes spin { to { transform: rotate(360deg); } }

.cw-error {
  display: flex; align-items: center; justify-content: center;
  flex-direction: column; gap: 14px; padding: 60px 24px;
  text-align: center; flex: 1;
}
.cw-error h2 {
  font-size: 18px; font-weight: 500; color: var(--uza-navy);
  margin: 0;
}
.cw-back-btn {
  font-size: 13px; color: var(--uza-purple);
  text-decoration: none; padding: 8px 16px;
  border: 1px solid var(--uza-purple);
  border-radius: 8px;
  transition: all 200ms;
}
.cw-back-btn:hover {
  background: var(--uza-purple); color: white;
}


/* ═══ Topbar ═══ */
.cw-topbar {
  display: flex; align-items: center; justify-content: space-between;
  padding: 12px 24px;
  background: linear-gradient(90deg, #1E2A4A 0%, #2A3760 100%);
  color: white;
  flex-shrink: 0;
}
.cw-topbar-l, .cw-topbar-r { display: flex; align-items: center; gap: 10px; }

.cw-topbar h1 {
  font-size: 16px; font-weight: 500; margin: 0;
  color: white;
  max-width: 280px;
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}

.cw-tbadge {
  font-size: 11px; font-weight: 500;
  background: rgba(255, 255, 255, 0.10);
  color: rgba(255, 255, 255, 0.92);
  padding: 4px 10px;
  border-radius: 6px;
  white-space: nowrap;
  display: inline-flex; align-items: center; gap: 4px;
  transition: background 120ms;
}
.cw-tbadge-clickable { cursor: pointer; }
.cw-tbadge-clickable:hover { background: rgba(255, 255, 255, 0.15); transform: translateY(-1px); }
.cw-tbadge-green { color: #6EE7B7; font-weight: 600; }

/* Sprint A · Financial snapshot badges in topbar */
.cw-tbadge-fin {
  display: inline-flex; align-items: baseline; gap: 5px;
  font-variant-numeric: tabular-nums;
  font-weight: 500;
}
.cw-tbadge-fin-label {
  font-size: 10px;
  font-weight: 500;
  letter-spacing: 0.02em;
  opacity: 0.70;
  text-transform: none;
}
.cw-tbadge-fin-value {
  font-weight: 600;
  font-size: 12px;
}
.cw-tbadge-fin-ccy {
  font-size: 10px;
  opacity: 0.65;
  font-weight: 500;
  margin-left: -2px;
}
.cw-tbadge-fin-year {
  font-size: 9.5px;
  opacity: 0.45;
  font-weight: 500;
  margin-left: 1px;
  font-variant-numeric: tabular-nums;
}
.cw-tbadge-rating { font-weight: 600; letter-spacing: 0.02em; }

/* Sector chip — colored left accent strip */
.cw-tbadge-sector {
  position: relative;
  padding-left: 14px;
  font-weight: 600;
  letter-spacing: 0.1px;
}
.cw-tbadge-sector::before {
  content: "";
  position: absolute;
  left: 5px; top: 25%; bottom: 25%;
  width: 3px;
  border-radius: 2px;
  background: currentColor;
  opacity: 0.85;
}

/* Refresh spin animation */
@keyframes cwSpin { to { transform: rotate(360deg); } }
.cw-spin { animation: cwSpin 0.85s linear infinite; transform-origin: 50% 50%; }

/* Notification bell pulse dot */
.cw-bell-btn { position: relative; }
.cw-bell-dot {
  position: absolute;
  top: 2px; right: 2px;
  min-width: 14px; height: 14px; padding: 0 3px;
  background: #E24B4A;
  color: white;
  font-size: 9px; font-weight: 700;
  border-radius: 7px;
  display: inline-flex; align-items: center; justify-content: center;
  box-shadow: 0 0 0 2px var(--cw-topbar-bg, #1E2A4A);
  animation: cwBellPulse 1.8s ease-out infinite;
}
@keyframes cwBellPulse {
  0%, 100% { box-shadow: 0 0 0 2px rgba(30,42,74,1), 0 0 0 0 rgba(226,75,74,0.6); }
  50%      { box-shadow: 0 0 0 2px rgba(30,42,74,1), 0 0 0 6px rgba(226,75,74,0); }
}

/* Disabled state for action buttons */
.cw-icon-btn:disabled { opacity: 0.55; cursor: wait; }

/* Year picker — стиль .edt-pill-amber из ExecutiveDashboard */
.cw-year-picker {
  display: inline-flex; align-items: center; gap: 4px;
  background: rgba(250, 199, 117, 0.10);
  border: 1px solid rgba(250, 199, 117, 0.25);
  color: #FAC775;
  padding: 3px 6px;
  border-radius: 8px;
  font-feature-settings: "tnum";
  transition: background .15s, border-color .15s;
}
.cw-year-picker:hover {
  background: rgba(250, 199, 117, 0.15);
  border-color: rgba(250, 199, 117, 0.35);
}
.cw-yr-arrow {
  background: transparent; border: none; cursor: pointer;
  color: #FAC775; font-size: 13px; font-weight: 600;
  width: 20px; height: 20px;
  border-radius: 4px;
  display: flex; align-items: center; justify-content: center;
  transition: background .15s;
}
.cw-yr-arrow:hover:not(:disabled) { background: rgba(250, 199, 117, 0.18); }
.cw-yr-arrow:disabled { opacity: 0.35; cursor: not-allowed; }
.cw-yr-label {
  font-size: 11.5px; font-weight: 500;
  padding: 0 4px;
  color: #FAC775;
  letter-spacing: .01em;
}

.cw-icon-btn {
  background: transparent; border: none; cursor: pointer;
  width: 32px; height: 30px;
  display: flex; align-items: center; justify-content: center; gap: 4px;
  color: rgba(255, 255, 255, 0.7);
  border-radius: 6px;
  font-size: 11px; font-weight: 500;
  padding: 0;
  transition: all 150ms;
}
.cw-icon-btn-text { padding: 0 10px; width: auto; }
.cw-icon-btn:hover {
  background: rgba(255, 255, 255, 0.10);
  color: white;
}

.cw-add-btn {
  background: var(--uza-purple);
  color: white;
  border: none; cursor: pointer;
  padding: 7px 14px;
  border-radius: 7px;
  font-size: 12px; font-weight: 500;
  transition: all 200ms;
}
.cw-add-btn:hover {
  background: #6B62D2;
  box-shadow: 0 4px 12px rgba(127, 119, 221, 0.35);
}

/* ═══ Tabs ═══ */
.cw-tabs {
  display: flex; gap: 4px;
  padding: 6px 14px;
  background: white;
  border-bottom: 1px solid var(--uza-border);
  flex-shrink: 0;
}
.cw-tab {
  font-size: 12px; font-weight: 500;
  background: transparent; border: 1px solid transparent;
  color: var(--uza-navy);
  padding: 6px 14px;
  border-radius: 11px;
  cursor: pointer;
  transition: all 200ms;
}
.cw-tab:hover { background: var(--uza-bg2); }
.cw-tab.active {
  background: var(--uza-purple);
  color: white;
  box-shadow: 0 2px 8px rgba(127, 119, 221, 0.30);
}

/* ═══ Body ═══ */
.cw-body { flex: 1; overflow: hidden; display: flex; flex-direction: column; position: relative; }

/* Smooth tab switch — fade-up */
.cw-fade-enter-active {
  animation: cwFadeUp 0.28s cubic-bezier(0.34, 1.2, 0.64, 1) both;
}
.cw-fade-leave-active {
  animation: cwFadeDown 0.18s ease-in both;
}
@keyframes cwFadeUp {
  0%   { opacity: 0; transform: translateY(8px); }
  100% { opacity: 1; transform: translateY(0); }
}
@keyframes cwFadeDown {
  0%   { opacity: 1; transform: translateY(0); }
  100% { opacity: 0; transform: translateY(-4px); }
}
.cw-overview-scroll {
  padding: 16px 20px;
  display: flex; flex-direction: column; gap: 14px;
  overflow-y: auto;
  flex: 1;
}

/* ═══ HERO CARD ═══ */
.cw-hero {
  background: white;
  border-radius: 14px;
  border: 0.5px solid var(--uza-border);
  box-shadow: 0 1px 3px rgba(15, 23, 60, 0.04);
  padding: 14px 18px;
  position: relative;
  overflow: hidden;
  animation: kpiCardIn 0.5s cubic-bezier(0.34, 1.2, 0.64, 1) both;
}
.cw-hero::before {
  content: "";
  position: absolute; top: 0; left: 0; right: 0;
  height: 3px;
  background: linear-gradient(90deg, var(--uza-purple), var(--uza-teal), var(--uza-amber));
  opacity: 0.7;
}
@keyframes kpiCardIn {
  from { opacity: 0; transform: translateY(8px) scale(0.98); }
  to   { opacity: 1; transform: translateY(0) scale(1); }
}

.cw-hero-grid {
  display: grid;
  grid-template-columns: 1.45fr 1px 0.85fr 1px 1.15fr;
  gap: 18px;
  align-items: stretch;
}
.cw-hero-col { display: flex; flex-direction: column; gap: 10px; min-width: 0; }
.cw-hero-col-donut { align-items: center; justify-content: center; gap: 4px; }
.cw-hero-col-stats { gap: 7px; justify-content: center; }

/* ──────────────────────────────────────────── */
/* Status block v2 (redesign, no border-left)   */
/* ──────────────────────────────────────────── */
.cw-hero-col-stats-v2 {
  display: flex;
  flex-direction: column;
  gap: 14px;
  padding: 4px 0;
  justify-content: flex-start;
}

.cw-stats-hero {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 14px;
  padding-bottom: 12px;
  border-bottom: 0.5px solid #F1EFE8;
}
.cw-stats-hero-l { flex: 1; min-width: 0; }
.cw-stats-hero-num {
  font-size: 26px;
  font-weight: 500;
  letter-spacing: -0.025em;
  color: #1E2A4A;
  line-height: 1;
  font-variant-numeric: tabular-nums;
}
.cw-stats-hero-sep {
  color: #C8C7C0;
  margin: 0 4px;
  font-weight: 400;
}
.cw-stats-hero-sub {
  font-size: 11px;
  color: #888780;
  margin-top: 5px;
  line-height: 1.5;
}
.cw-stats-hero-sub b {
  color: #1E2A4A;
  font-weight: 500;
}

.cw-stats-pill {
  display: inline-block;
  padding: 4px 10px;
  border-radius: 8px;
  font-size: 10.5px;
  font-weight: 500;
  letter-spacing: 0.04em;
  white-space: nowrap;
}
.cw-stats-pill-good {
  background: rgba(29, 158, 117, 0.12);
  color: #0F6E56;
}
.cw-stats-pill-bad {
  background: rgba(226, 75, 74, 0.10);
  color: #A82C2B;
}

.cw-stats-grid {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 4px 12px;
}
.cw-stats-grid-5 {
  grid-template-columns: repeat(5, 1fr);
}
.cw-stats-cell {
  padding: 2px 0;
}
.cw-stats-cell-label {
  font-size: 9.5px;
  font-weight: 500;
  color: #888780;
  letter-spacing: 0.06em;
  text-transform: uppercase;
}
.cw-stats-cell-num {
  font-size: 14px;
  font-weight: 500;
  color: #1E2A4A;
  margin-top: 3px;
  font-variant-numeric: tabular-nums;
}
.cw-stats-cell-num.is-dim {
  color: #C8C7C0;
}

/* Results ratio cell — number coloured by completion tone */
.cw-stats-cell-num-ratio {
  font-feature-settings: "tnum";
}
.cw-stats-ratio-sep {
  color: rgba(30, 42, 74, 0.25);
  margin: 0 2px;
  font-weight: 400;
}
.cw-stats-results.cw-res-good  .cw-stats-cell-num-ratio { color: #1D9E75; }
.cw-stats-results.cw-res-info  .cw-stats-cell-num-ratio { color: #7F77DD; }
.cw-stats-results.cw-res-warn  .cw-stats-cell-num-ratio { color: #EF9F27; }
.cw-stats-results.cw-res-bad   .cw-stats-cell-num-ratio { color: #E24B4A; }
/* keep default colour for empty/no-data state */
.cw-divider { background: var(--uza-bg3); width: 1px; }

.cw-section-label {
  font-size: 11px; font-weight: 500;
  letter-spacing: 0.06em;
  text-transform: uppercase;
  color: var(--uza-gray);
}

/* ─── Rating tiles ─── */
.cw-ratings-grid {
  display: grid;
  grid-template-columns: 1fr 1fr 1fr 1fr;
  gap: 6px;
  flex: 1;
}
.cw-rating-tile {
  padding: 9px 10px;
  background: var(--uza-bg2);
  border-radius: 10px;
  cursor: pointer;
  transition: background 120ms;
  display: flex; flex-direction: column; gap: 5px;
}
.cw-rating-tile:hover { background: var(--uza-bg3); }
.cw-rating-empty {
  display: flex; flex-direction: column;
  align-items: center; justify-content: center; gap: 4px;
}
.cw-rt-agency { font-size: 10px; color: var(--uza-gray); }
.cw-rt-value {
  font-size: 26px; font-weight: 500; line-height: 1;
}
.cw-rt-value-wrap { display: flex; align-items: baseline; gap: 3px; }
.cw-rt-suffix { font-size: 11px; color: var(--uza-gray); }
.cw-rt-outlook {
  display: inline-block;
  font-size: 10px; font-weight: 500;
  padding: 1px 6px; border-radius: 4px;
  width: fit-content;
}
.cw-rt-date {
  font-size: 10px;
  color: var(--uza-gray);
  margin-top: 2px;
}
.cw-rt-link {
  color: var(--uza-purple);
  text-decoration: none;
  margin-left: 3px;
  font-weight: 600;
}
.cw-rt-link:hover { text-decoration: underline; }
.cw-rt-plus {
  font-size: 18px;
  color: var(--uza-bg4);
}

/* ESG bar */
.cw-rt-esg-bar-wrap { display: flex; flex-direction: column; gap: 3px; }
.cw-rt-esg-bar {
  height: 3px;
  background: rgba(0, 0, 0, 0.08);
  border-radius: 2px;
  overflow: hidden;
}
.cw-rt-esg-bar-fill {
  height: 100%;
  border-radius: 2px;
  transition: width 0.7s cubic-bezier(0.34, 1.2, 0.64, 1);
}
.cw-rt-esg-score { font-size: 10px; }

/* ─── Donut SVG ─── */
.cw-donut-svg { margin: 2px 0; }
.cw-donut-arc {
  transition: stroke-dashoffset 1.1s cubic-bezier(0.34, 1.2, 0.64, 1),
              stroke 0.35s ease;
}
.cw-hero-col-donut:hover .cw-donut-arc { filter: drop-shadow(0 0 4px currentColor); }
.cw-donut-sub {
  font-size: 11px;
  color: var(--uza-gray);
  font-variant-numeric: tabular-nums;
}
.cw-recurring-pill {
  display: flex; align-items: center; gap: 4px;
  margin-top: 5px;
  padding: 3px 8px;
  background: linear-gradient(90deg,
    rgba(168, 85, 247, 0.06),
    rgba(99, 102, 241, 0.06),
    rgba(6, 182, 212, 0.06));
  border-radius: 6px;
  font-size: 10px;
  color: var(--uza-gray);
}

/* ─── Stats stack (right column) ─── */
.cw-stat-row {
  display: flex; align-items: center; justify-content: space-between;
  padding: 7px 12px;
  border-radius: 8px;
  background: var(--uza-bg2);
  transition: background 120ms;
}
.cw-stat-row-clickable { cursor: pointer; }
.cw-stat-row-clickable:hover { background: var(--uza-bg3); }
.cw-stat-row-active {
  background: #FCFAFF;
}
.cw-stat-row-active:hover { background: #F6F2FE; }

.cw-stat-label {
  font-size: 10px; font-weight: 500;
  letter-spacing: 0.06em;
  text-transform: uppercase;
  color: var(--uza-gray);
}
.cw-stat-value {
  display: flex; align-items: baseline; gap: 4px;
  font-size: 17px; font-weight: 500;
  color: var(--uza-navy);
  font-variant-numeric: tabular-nums;
}
.cw-stat-unit {
  font-size: 10px; color: var(--uza-gray);
  margin-right: 4px; font-weight: 400;
}
.cw-stat-sep { color: var(--uza-bg4); font-size: 10px; }
.cw-stat-allgood {
  font-size: 13px; color: #1D9E75; font-weight: 500;
}

/* Mini chips */
.cw-stat-chips {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 5px;
  margin-top: 1px;
}
.cw-chip {
  padding: 4px 6px;
  border-radius: 6px;
  background: var(--uza-bg2);
  display: flex; flex-direction: column; gap: 1px;
  cursor: pointer;
  transition: background 120ms;
}
.cw-chip:hover { background: var(--uza-bg3); }
.cw-chip-label {
  font-size: 9px; font-weight: 500;
  text-transform: uppercase;
  letter-spacing: 0.04em;
  color: var(--uza-gray);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.cw-chip-value {
  font-size: 14px; font-weight: 500;
  font-variant-numeric: tabular-nums;
  line-height: 1;
}

/* ═══ Placeholders ═══ */
.cw-placeholder, .cw-card-placeholder {
  background: white;
  border-radius: 12px;
  border: 0.5px solid var(--uza-border);
  padding: 14px 16px;
}
.cw-placeholder-text {
  font-size: 12px;
  color: var(--uza-gray);
  margin: 8px 0 0;
  font-style: italic;
}
.cw-grid-4-placeholder {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 14px;
}
.cw-grid-2-placeholder {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 14px;
}
.cw-attention-count {
  display: inline-block;
  margin-left: 6px;
  font-size: 11px; font-weight: 700;
  color: var(--uza-red);
}

.cw-tab-placeholder {
  display: flex; flex-direction: column; align-items: center; justify-content: center;
  padding: 80px 24px;
  text-align: center;
  flex: 1;
  color: var(--uza-gray);
}
.cw-tab-placeholder h2 {
  font-size: 18px; font-weight: 500;
  color: var(--uza-navy);
  margin: 0 0 8px;
}

/* ═══ Responsive ═══ */
@media (max-width: 1100px) {
  .cw-hero-grid {
    grid-template-columns: 1fr;
  }
  .cw-divider { display: none; }
  .cw-grid-4-placeholder { grid-template-columns: repeat(2, 1fr); }
}
@media (max-width: 720px) {
  .cw-topbar { flex-wrap: wrap; gap: 8px; }
  .cw-grid-4-placeholder, .cw-grid-2-placeholder { grid-template-columns: 1fr; }
}

/* Reduced motion */
@media (prefers-reduced-motion: reduce) {
  .cw-hero, .cw-rt-esg-bar-fill, .cw-spinner {
    animation: none !important;
    transition: none !important;
  }
}

/* ═══════════════════════════════════════════════════════════════════ */
/* ═══ NEW: 13-tab grouped navigation                                ═══ */
/* ═══════════════════════════════════════════════════════════════════ */

.cw-tabs-grouped {
  display: flex;
  gap: 0;
  padding: 6px 14px;
  align-items: center;
  overflow-x: auto;
  scrollbar-width: thin;
  scrollbar-color: rgba(127, 119, 221, 0.30) transparent;
}
.cw-tabs-grouped::-webkit-scrollbar { height: 4px; }
.cw-tabs-grouped::-webkit-scrollbar-thumb { background: rgba(127, 119, 221, 0.30); border-radius: 2px; }

.cw-tab-group {
  display: inline-flex;
  gap: 2px;
  flex-shrink: 0;
}

.cw-tab-sep {
  width: 1px;
  height: 18px;
  background: var(--uza-border);
  margin: 0 8px;
  flex-shrink: 0;
}

/* Group tinting on tab accent (subtle hue per group) */
.cw-tab-manage.active   { background: var(--uza-purple); }
.cw-tab-finance.active  { background: var(--uza-teal);   }
.cw-tab-ops.active      { background: var(--uza-amber);  color: #1F1B0F; }
.cw-tab-strategy.active { background: var(--uza-blue);   }

.cw-tab-finance.active  { box-shadow: 0 2px 8px rgba(29, 158, 117, 0.30); }
.cw-tab-ops.active      { box-shadow: 0 2px 8px rgba(239, 159, 39, 0.30); }
.cw-tab-strategy.active { box-shadow: 0 2px 8px rgba(55, 138, 221, 0.30); }

/* ═══════════════════════════════════════════════════════════════════ */
/* ═══════════════════════════════════════════════════════════════════ */

.cw-kanban-scroll {
  flex: 1;
  overflow: hidden;
  padding: 16px 20px;
  display: flex;
  flex-direction: column;
}

.cw-kanban-board {
  display: flex;
  gap: 10px;
  flex: 1;
  min-width: max-content;
  overflow-x: auto;
  overflow-y: hidden;
  padding-bottom: 8px;
}

/* Колонка — стеклянный premium-card */
.kol {
  width: 268px;
  flex-shrink: 0;
  display: flex;
  flex-direction: column;
  background: rgba(255, 255, 255, 0.55);
  backdrop-filter: blur(12px) saturate(1.4);
  -webkit-backdrop-filter: blur(12px) saturate(1.4);
  border-radius: 16px;
  border: 1px solid rgba(255, 255, 255, 0.60);
  box-shadow:
    0 2px 8px rgba(15, 23, 60, 0.05),
    0 0 0 0.5px rgba(255, 255, 255, 0.5) inset;
  max-height: 100%;
}
.kol-overdue {
  border-color: rgba(220, 38, 38, 0.3);
  background: rgba(220, 38, 38, 0.03);
}
.kol-recurring {
  border-color: rgba(168, 85, 247, 0.25);
  background: linear-gradient(
    180deg,
    rgba(168, 85, 247, 0.03) 0%,
    rgba(99, 102, 241, 0.02) 50%,
    rgba(6, 182, 212, 0.03) 100%
  );
}

.kol-hd {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 14px 10px;
  border-bottom: 1px solid rgba(255, 255, 255, 0.50);
}
.kol-hd-l {
  display: flex;
  align-items: center;
  gap: 7px;
}
.kol-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  flex-shrink: 0;
}
.kol-title {
  font-size: 13px;
  font-weight: 700;
  color: #1E2A4A;
}
.kol-cnt {
  font-size: 12px;
  color: rgba(30, 42, 74, 0.45);
  background: rgba(0, 0, 0, 0.05);
  padding: 2px 8px;
  border-radius: 20px;
  font-weight: 500;
  font-variant-numeric: tabular-nums;
}

.kol-cards {
  flex: 1;
  overflow-y: auto;
  padding: 5px;
  display: flex;
  flex-direction: column;
  gap: 6px;
  min-height: 80px;
}
.kol-empty {
  padding: 20px 16px;
  text-align: center;
  font-size: 12px;
  color: rgba(30, 42, 74, 0.45);
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  min-height: 80px;
}

.kol-recurring-sub {
  font-size: 9.5px;
  color: rgba(30, 42, 74, 0.55);
  padding: 2px 12px 4px;
  display: flex;
  gap: 8px;
  font-weight: 600;
  font-variant-numeric: tabular-nums;
}

/* ═══════════════════════════════════════════════════════════════════ */
/* ═══ LIST VIEW                                                     ═══ */
/* ═══════════════════════════════════════════════════════════════════ */

.cw-list-scroll {
  flex: 1;
  overflow-y: auto;
  padding: 16px 20px;
}

.cw-list-filters {
  display: flex;
  align-items: center;
  gap: 16px;
  margin-bottom: 14px;
  padding: 12px 14px;
  background: white;
  border-radius: 10px;
  border: 0.5px solid var(--uza-border);
}
.cw-filter-group {
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.cw-filter-label {
  font-size: 9px;
  font-weight: 600;
  letter-spacing: 0.06em;
  text-transform: uppercase;
  color: var(--uza-gray);
}
.cw-filter-select {
  font-size: 12px;
  padding: 5px 24px 5px 10px;
  border: 0.5px solid var(--uza-border);
  border-radius: 6px;
  background: var(--uza-bg);
  color: var(--uza-navy);
  cursor: pointer;
  font-family: inherit;
}
.cw-filter-select:focus {
  outline: 2px solid var(--uza-purple);
  outline-offset: -1px;
}

.cw-list-summary {
  margin-left: auto;
  font-size: 12px;
  color: var(--uza-gray);
  font-variant-numeric: tabular-nums;
}

.cw-list-table {
  background: white;
  border-radius: 10px;
  border: 0.5px solid var(--uza-border);
  overflow: hidden;
}
.cw-list-row {
  display: grid;
  grid-template-columns: 2.5fr 1fr 1fr 1.2fr;
  gap: 14px;
  padding: 11px 14px;
  align-items: center;
  border-bottom: 0.5px solid var(--uza-border);
  font-size: 12.5px;
  color: var(--uza-navy);
  cursor: pointer;
  transition: background 150ms;
}
.cw-list-row:last-child { border-bottom: none; }
.cw-list-row:hover { background: var(--uza-bg2); }

.cw-list-row-header {
  background: var(--uza-bg2);
  cursor: default;
  font-size: 10px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  color: var(--uza-gray);
}
.cw-list-row-header:hover { background: var(--uza-bg2); }

.cw-list-row-overdue {
  background: rgba(226, 75, 74, 0.04);
}
.cw-list-row-overdue:hover {
  background: rgba(226, 75, 74, 0.08);
}

.cw-list-c-title {
  display: flex;
  align-items: center;
  gap: 8px;
  font-weight: 500;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.cw-list-type-badge {
  font-size: 9px;
  font-weight: 700;
  letter-spacing: 0.04em;
  padding: 2px 6px;
  border-radius: 3px;
  flex-shrink: 0;
}
.cw-list-type-project {
  background: rgba(127, 119, 221, 0.14);
  color: #5448B7;
}

.cw-list-status-pill {
  font-size: 11px;
  font-weight: 500;
  padding: 2px 8px;
  border-radius: 11px;
  display: inline-block;
}

.cw-list-c-deadline.overdue {
  color: var(--uza-red);
  font-weight: 600;
}

.cw-list-c-direction {
  color: var(--uza-gray);
  font-size: 11.5px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.cw-list-empty {
  padding: 40px 20px;
  text-align: center;
  color: var(--uza-gray);
  font-size: 13px;
}

/* ═══════════════════════════════════════════════════════════════════ */
/* ═══ CTA CARD (placeholder for global-page tabs)                   ═══ */
/* ═══════════════════════════════════════════════════════════════════ */

.cw-cta-card {
  max-width: 480px;
  margin: 0 auto;
  padding: 40px 32px;
  background: white;
  border-radius: 16px;
  border: 0.5px solid var(--uza-border);
  text-align: center;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 12px;
  box-shadow: 0 4px 24px rgba(15, 23, 60, 0.06);
  animation: cwCtaIn 0.4s cubic-bezier(0.34, 1.2, 0.64, 1) both;
}
@keyframes cwCtaIn {
  from { opacity: 0; transform: translateY(8px) scale(0.98); }
  to   { opacity: 1; transform: translateY(0) scale(1); }
}

.cw-cta-icon {
  color: var(--uza-purple);
  margin-bottom: 4px;
  opacity: 0.85;
}

.cw-cta-card h2 {
  font-size: 22px;
  font-weight: 500;
  color: var(--uza-navy);
  margin: 0;
}

.cw-cta-card p {
  font-size: 13px;
  color: var(--uza-gray);
  margin: 0;
  line-height: 1.5;
}

.cw-cta-note {
  font-size: 11.5px !important;
  color: #94A3B8 !important;
  margin-top: 4px !important;
  padding: 10px 14px;
  background: var(--uza-bg2);
  border-radius: 8px;
  /* top-stripe via .cw-cta-note::before — purple */
  --accent: var(--uza-purple);
  text-align: left;
  width: 100%;
  box-sizing: border-box;
}

.cw-cta-card code {
  background: var(--uza-bg3);
  padding: 1px 6px;
  border-radius: 4px;
  font-size: 10px;
  font-family: ui-monospace, "SF Mono", Consolas, monospace;
  color: var(--uza-purple);
}

.cw-cta-btn {
  display: inline-block;
  margin-top: 12px;
  padding: 10px 20px;
  background: var(--uza-purple);
  color: white;
  text-decoration: none;
  border-radius: 8px;
  font-size: 13px;
  font-weight: 500;
  transition: all 200ms;
  border: none;
  cursor: pointer;
}
.cw-cta-btn:hover {
  background: #6B62D2;
  box-shadow: 0 6px 20px rgba(127, 119, 221, 0.40);
  transform: translateY(-1px);
}

/* ═══════════════════════════════════════════════════════════════════ */
/* ═══ KPI VIEW                                                      ═══ */
/* ═══════════════════════════════════════════════════════════════════ */

.cw-kpi-scroll {
  flex: 1;
  overflow-y: auto;
  padding: 16px 20px;
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.cw-kpi-summary {
  display: flex;
  align-items: stretch;
  gap: 0;
  background: white;
  border: 0.5px solid var(--uza-border);
  border-radius: 12px;
  padding: 14px 18px;
  animation: kpiSumIn 0.4s cubic-bezier(0.34, 1.2, 0.64, 1) both;
}
@keyframes kpiSumIn {
  from { opacity: 0; transform: translateY(6px); }
  to   { opacity: 1; transform: translateY(0); }
}
.cw-kpi-sum-stat {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 4px;
  padding: 0 8px;
}
.cw-kpi-sum-label {
  font-size: 9px;
  letter-spacing: 0.06em;
  text-transform: uppercase;
  font-weight: 600;
  color: var(--uza-gray);
}
.cw-kpi-sum-value {
  font-size: 22px;
  font-weight: 400;
  letter-spacing: -0.025em;
  color: var(--uza-navy);
  font-variant-numeric: tabular-nums;
}
.cw-kpi-sum-value.cw-kpi-attention { color: var(--uza-red); }
.cw-kpi-sum-divider {
  width: 1px;
  background: var(--uza-border);
  align-self: stretch;
}

.cw-kpi-managers {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(380px, 1fr));
  gap: 14px;
}

.cw-kpi-mgr {
  background: white;
  border: 0.5px solid var(--uza-border);
  border-radius: 12px;
  padding: 16px 18px;
  display: flex;
  flex-direction: column;
  gap: 10px;
  box-shadow: 0 2px 8px rgba(15, 23, 60, 0.04);
  transition: box-shadow 200ms;
  animation: kpiSumIn 0.4s cubic-bezier(0.34, 1.2, 0.64, 1) both;
}
.cw-kpi-mgr:hover {
  box-shadow: 0 4px 16px rgba(15, 23, 60, 0.08);
}

.cw-kpi-mgr-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
}
.cw-kpi-mgr-titles {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 2px;
}
.cw-kpi-mgr-short {
  font-size: 14px;
  font-weight: 500;
  color: var(--uza-navy);
  letter-spacing: -0.01em;
}
.cw-kpi-mgr-full {
  font-size: 11px;
  color: var(--uza-gray);
}
.cw-kpi-mgr-pct {
  font-size: 24px;
  font-weight: 400;
  letter-spacing: -0.025em;
  font-variant-numeric: tabular-nums;
  flex-shrink: 0;
}

.cw-kpi-mgr-meta {
  font-size: 11px;
  color: var(--uza-gray);
  padding-bottom: 6px;
  border-bottom: 0.5px solid var(--uza-border);
}
.cw-kpi-mgr-attn {
  color: var(--uza-red);
  font-weight: 500;
}

.cw-kpi-ind-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.cw-kpi-ind {
  padding: 8px 10px 9px;
  background: var(--uza-bg2);
  border-radius: 8px;
  display: flex;
  flex-direction: column;
  gap: 4px;
  transition: background 150ms;
  position: relative; overflow: hidden;
}
.cw-kpi-ind:hover {
  background: var(--uza-bg3);
}
.cw-kpi-ind-attn {
  background: rgba(226, 75, 74, 0.04);
}
.cw-kpi-ind-attn::before {
  content: ""; position: absolute; top: 0; left: 0; right: 0;
  height: 2px; background: var(--uza-red);
  animation: uzaStripeDrawIn .4s cubic-bezier(0.34, 1.2, 0.64, 1) both;
  pointer-events: none;
}
.cw-kpi-ind-nofact {
  opacity: 0.86;
}

.cw-kpi-ind-row1 {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 10px;
}
.cw-kpi-ind-name {
  font-size: 11.5px;
  font-weight: 500;
  color: var(--uza-navy);
  line-height: 1.35;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
  flex: 1;
}
.cw-kpi-ind-weight {
  font-size: 10px;
  font-weight: 600;
  color: var(--uza-purple);
  background: rgba(127, 119, 221, 0.10);
  padding: 1px 6px;
  border-radius: 3px;
  font-variant-numeric: tabular-nums;
  flex-shrink: 0;
}

.cw-kpi-ind-row2 {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  font-size: 10.5px;
}
.cw-kpi-ind-vals {
  display: flex;
  gap: 12px;
  flex-wrap: wrap;
  color: var(--uza-gray);
}
.cw-kpi-ind-fact.no-fact {
  color: #94A3B8;
  font-style: italic;
}
.cw-kpi-ind-pct {
  font-size: 12px;
  font-weight: 600;
  font-variant-numeric: tabular-nums;
}

.cw-kpi-ind-bar-wrap {
  height: 3px;
  background: rgba(15, 23, 60, 0.06);
  border-radius: 2px;
  overflow: hidden;
}
.cw-kpi-ind-bar {
  height: 100%;
  border-radius: 2px;
  transition: width 600ms cubic-bezier(0.34, 1.2, 0.64, 1);
}

/* Sprint B · Prior-year baseline */
.cw-kpi-baseline-banner {
  display: flex; align-items: center; gap: 10px;
  background: rgba(127, 119, 221, 0.08);
  border-radius: 8px;
  /* top-stripe via .cw-act-cell::before — см. групповое правило в конце */
  padding: 10px 14px;
  margin-bottom: 12px;
  font-size: 12px;
  color: #1E2A4A;
  animation: cwBaselineSlide .35s cubic-bezier(0.34, 1.2, 0.64, 1) both;
}
@keyframes cwBaselineSlide { 0% { opacity: 0; transform: translateX(-4px); } 100% { opacity: 1; transform: translateX(0); } }
.cw-kpi-baseline-icon {
  width: 22px; height: 22px; border-radius: 50%;
  display: flex; align-items: center; justify-content: center;
  background: #7F77DD; color: white;
  font-size: 13px; font-weight: 700;
  flex-shrink: 0;
}
.cw-kpi-baseline-text { line-height: 1.4; }
.cw-kpi-baseline-text b { font-weight: 600; color: #534AB7; }

.cw-kpi-ind-baseline {
  display: flex; align-items: baseline; gap: 8px;
  margin-top: 6px;
  padding: 4px 8px;
  background: rgba(127, 119, 221, 0.06);
  border-radius: 6px;
  font-size: 11px;
  color: #6B7280;
}
.cw-kpi-ind-baseline-tag {
  font-size: 9px;
  letter-spacing: 0.05em;
  text-transform: uppercase;
  color: #7F77DD;
  font-weight: 600;
}
.cw-kpi-ind-baseline-val {
  font-variant-numeric: tabular-nums;
  font-weight: 500;
  color: #1E2A4A;
}
.cw-kpi-ind-baseline-vs {
  margin-left: auto;
  font-size: 10px;
  color: #888780;
}

/* ═══════════════════════════════════════════════════════════════════ */
/* ═══ BUSINESS PLAN VIEW                                            ═══ */
/* ═══════════════════════════════════════════════════════════════════ */

.cw-bp-scroll {
  flex: 1;
  overflow-y: auto;
  padding: 16px 20px;
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.cw-bp-period-bar {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 14px;
  background: white;
  border: 0.5px solid var(--uza-border);
  border-radius: 10px;
}
.cw-bp-period-label {
  font-size: 9px;
  font-weight: 600;
  letter-spacing: 0.06em;
  text-transform: uppercase;
  color: var(--uza-gray);
  margin-right: 4px;
}
.cw-bp-period-btn {
  font-size: 12px;
  font-weight: 500;
  padding: 6px 14px;
  border-radius: 7px;
  background: transparent;
  border: 0.5px solid var(--uza-border);
  color: var(--uza-gray);
  cursor: pointer;
  transition: all 180ms;
  font-family: inherit;
}
.cw-bp-period-btn:hover {
  background: var(--uza-bg2);
  color: var(--uza-navy);
}
.cw-bp-period-btn.active {
  background: var(--uza-teal);
  color: white;
  border-color: var(--uza-teal);
  box-shadow: 0 2px 8px rgba(29, 158, 117, 0.30);
}

/* Edit-button — primary purple, pushed to right via margin-left:auto */
.cw-bp-edit-btn {
  margin-left: auto;
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font: inherit;
  font-size: 12px;
  font-weight: 500;
  padding: 7px 14px;
  border-radius: 8px;
  border: 1px solid var(--uza-purple);
  background: var(--uza-purple);
  color: white;
  cursor: pointer;
  transition: transform 150ms, box-shadow 150ms, background 150ms;
}
.cw-bp-edit-btn:hover {
  transform: translateY(-1px);
  box-shadow: 0 4px 12px rgba(127, 119, 221, 0.35);
  background: #6A62C8;
}
.cw-bp-edit-btn:active { transform: translateY(0); }
.cw-bp-edit-btn:focus-visible {
  outline: none;
  box-shadow: 0 0 0 3px rgba(127, 119, 221, 0.30);
}

.cw-bp-tops {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 12px;
}
.cw-bp-top-card {
  background: white;
  border: 0.5px solid var(--uza-border);
  border-top: 3px solid var(--accent, var(--uza-purple));
  border-radius: 12px;
  padding: 16px 18px;
  display: flex;
  flex-direction: column;
  gap: 8px;
  box-shadow: 0 4px 16px rgba(15, 23, 60, 0.05);
  animation: kpiSumIn 0.5s cubic-bezier(0.34, 1.2, 0.64, 1) both;
}
.cw-bp-top-label {
  font-size: 11px;
  font-weight: 600;
  letter-spacing: 0.04em;
  text-transform: uppercase;
  color: var(--uza-gray);
  line-height: 1.3;
}
.cw-bp-top-value {
  font-size: 28px;
  font-weight: 400;
  letter-spacing: -0.025em;
  color: var(--uza-navy);
  font-variant-numeric: tabular-nums;
  margin: 4px 0;
}
.cw-bp-top-stats {
  display: flex;
  flex-direction: column;
  gap: 4px;
  padding-top: 6px;
  border-top: 0.5px solid var(--uza-border);
}
.cw-bp-top-stat {
  display: flex;
  justify-content: space-between;
  font-size: 11px;
  font-variant-numeric: tabular-nums;
}
.cw-bp-top-stat-l {
  color: var(--uza-gray);
}
.cw-bp-top-stat-v {
  color: var(--uza-navy);
  font-weight: 500;
}

.cw-bp-table {
  background: white;
  border: 0.5px solid var(--uza-border);
  border-radius: 12px;
  overflow: hidden;
}

.cw-bp-table-header {
  display: grid;
  grid-template-columns: 2.5fr 1fr 1fr 1fr 70px;
  gap: 12px;
  padding: 10px 16px;
  background: var(--uza-bg2);
  border-bottom: 0.5px solid var(--uza-border);
  font-size: 10px;
  font-weight: 600;
  letter-spacing: 0.05em;
  text-transform: uppercase;
  color: var(--uza-gray);
}
.cw-bp-th-num, .cw-bp-th-pct { text-align: right; }

.cw-bp-group-header {
  padding: 9px 16px;
  font-size: 10px;
  font-weight: 600;
  letter-spacing: 0.06em;
  text-transform: uppercase;
  color: var(--uza-purple);
  background: rgba(127, 119, 221, 0.05);
  border-bottom: 0.5px solid var(--uza-border);
}

.cw-bp-row {
  display: grid;
  grid-template-columns: 2.5fr 1fr 1fr 1fr 70px;
  gap: 12px;
  padding: 9px 16px;
  align-items: center;
  font-size: 12px;
  border-bottom: 0.5px solid rgba(15, 23, 60, 0.04);
}
.cw-bp-row:last-child { border-bottom: none; }
.cw-bp-row-auto {
  background: rgba(127, 119, 221, 0.03);
  font-weight: 500;
}
.cw-bp-row-sub .cw-bp-cell-name {
  padding-left: 18px;
  font-size: 11px;
  color: var(--uza-gray);
}
.cw-bp-row-final {
  background: rgba(29, 158, 117, 0.05);
  font-weight: 600;
  border-top: 0.5px solid var(--uza-border);
}
.cw-bp-row-final .cw-bp-cell-name { color: var(--uza-teal); }

.cw-bp-cell-name {
  display: flex;
  align-items: center;
  gap: 6px;
  color: var(--uza-navy);
}
.cw-bp-cell-num, .cw-bp-cell-pct {
  text-align: right;
  font-variant-numeric: tabular-nums;
  color: var(--uza-navy);
}
.cw-bp-cell-fact {
  font-weight: 500;
}
.cw-bp-cell-pct {
  font-weight: 600;
}

.cw-bp-auto-mark {
  font-size: 11px;
  color: var(--uza-purple);
  font-weight: 700;
  width: 14px;
  text-align: center;
  flex-shrink: 0;
}

/* ═══════════════════════════════════════════════════════════════════ */
/* ═══ Loading / Error / Empty States                                ═══ */
/* ═══════════════════════════════════════════════════════════════════ */

.cw-loading-state {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 12px;
  padding: 60px 20px;
  color: var(--uza-gray);
  font-size: 13px;
}
.cw-error-state {
  display: flex;
  align-items: flex-start;
  gap: 12px;
  padding: 24px;
  background: rgba(226, 75, 74, 0.06);
  border: 0.5px solid rgba(226, 75, 74, 0.20);
  border-radius: 12px;
  margin: 20px;
}
.cw-err-icon {
  font-size: 22px;
  color: var(--uza-red);
  flex-shrink: 0;
  line-height: 1;
  margin-top: 2px;
}
.cw-err-title {
  font-size: 14px;
  font-weight: 600;
  color: var(--uza-red);
  margin-bottom: 4px;
}
.cw-err-msg {
  font-size: 12px;
  color: var(--uza-gray);
  line-height: 1.5;
}
.cw-empty-state {
  text-align: center;
  padding: 40px 20px;
  background: white;
  border: 0.5px solid var(--uza-border);
  border-radius: 12px;
  margin: 20px;
}
.cw-empty-icon {
  font-size: 48px;
  color: var(--uza-bg4);
  line-height: 1;
}
.cw-empty-title {
  font-size: 16px;
  font-weight: 500;
  color: var(--uza-navy);
  margin-top: 8px;
}
.cw-empty-msg {
  font-size: 13px;
  color: var(--uza-gray);
  margin-top: 6px;
  line-height: 1.5;
}

/* ═══════════════════════════════════════════════════════════════════ */
/* ═══ GOVERNANCE VIEW                                               ═══ */
/* ═══════════════════════════════════════════════════════════════════ */

.cw-gov-scroll {
  flex: 1;
  overflow-y: auto;
  padding: 16px 20px;
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.cw-gov-kpis {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
  gap: 10px;
}
.cw-gov-kpi-card {
  background: white;
  border: 0.5px solid var(--uza-border);
  border-top: 3px solid var(--accent);
  border-radius: 10px;
  padding: 12px 14px;
  display: flex;
  flex-direction: column;
  gap: 4px;
  box-shadow: 0 2px 8px rgba(15, 23, 60, 0.04);
  animation: kpiSumIn 0.4s cubic-bezier(0.34, 1.2, 0.64, 1) both;
}
.cw-gov-kpi-label {
  font-size: 9.5px;
  font-weight: 600;
  letter-spacing: 0.05em;
  text-transform: uppercase;
  color: var(--uza-gray);
}
.cw-gov-kpi-value {
  font-size: 22px;
  font-weight: 400;
  letter-spacing: -0.025em;
  color: var(--uza-navy);
  font-variant-numeric: tabular-nums;
}
.cw-gov-kpi-unit {
  font-size: 10.5px;
  color: var(--uza-gray);
}

.cw-gov-section {
  background: white;
  border: 0.5px solid var(--uza-border);
  border-radius: 12px;
  padding: 14px 16px;
}
.cw-gov-section .cw-section-label {
  margin-bottom: 12px;
}

.cw-gov-committees {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}
.cw-gov-committee {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 6px 12px;
  border-radius: 7px;
  font-size: 12px;
  font-weight: 500;
  border: 0.5px solid var(--uza-border);
}
.cw-gov-committee-on {
  background: rgba(29, 158, 117, 0.10);
  color: var(--uza-teal);
  border-color: rgba(29, 158, 117, 0.30);
}
.cw-gov-committee-off {
  background: var(--uza-bg2);
  color: var(--uza-bg4);
  text-decoration: line-through;
}
.cw-gov-committee-icon {
  font-weight: 700;
}

.cw-gov-members {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
  gap: 10px;
}
.cw-gov-member {
  display: flex;
  gap: 12px;
  align-items: flex-start;
  padding: 12px;
  background: var(--uza-bg2);
  border-radius: 10px;
  transition: background 200ms;
}
.cw-gov-member:hover {
  background: var(--uza-bg3);
}
.cw-gov-avatar {
  width: 40px;
  height: 40px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  color: white;
  font-size: 13px;
  font-weight: 600;
  letter-spacing: 0.02em;
  flex-shrink: 0;
  box-shadow: 0 2px 6px rgba(15, 23, 60, 0.12);
}
.cw-gov-member-info {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 2px;
}
.cw-gov-member-name {
  font-size: 13px;
  font-weight: 500;
  color: var(--uza-navy);
}
.cw-gov-member-pos {
  font-size: 11px;
  color: var(--uza-gray);
}
.cw-gov-member-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
  margin-top: 4px;
}
.cw-gov-role-pill {
  font-size: 9.5px;
  font-weight: 600;
  padding: 1px 6px;
  border-radius: 3px;
  letter-spacing: 0.02em;
}
.cw-gov-badge {
  font-size: 9.5px;
  font-weight: 500;
  padding: 1px 6px;
  border-radius: 3px;
  background: rgba(127, 119, 221, 0.10);
  color: var(--uza-purple);
}
.cw-gov-member-dates {
  font-size: 10px;
  color: var(--uza-bg4);
  font-variant-numeric: tabular-nums;
  margin-top: 2px;
}

/* ═══════════════════════════════════════════════════════════════════ */
/* ═══ ESG VIEW                                                      ═══ */
/* ═══════════════════════════════════════════════════════════════════ */

.cw-esg-scroll {
  flex: 1;
  overflow-y: auto;
  padding: 16px 20px;
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.cw-esg-pillars {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 12px;
}
.cw-esg-pillar-card {
  background: white;
  border: 0.5px solid var(--uza-border);
  border-top: 4px solid var(--accent);
  border-radius: 12px;
  padding: 18px 18px 14px;
  display: flex;
  flex-direction: column;
  gap: 10px;
  box-shadow: 0 4px 16px rgba(15, 23, 60, 0.05);
  position: relative;
  animation: kpiSumIn 0.5s cubic-bezier(0.34, 1.2, 0.64, 1) both;
}
.cw-esg-pillar-letter {
  font-size: 36px;
  font-weight: 300;
  color: var(--accent);
  line-height: 1;
  letter-spacing: -0.03em;
}
.cw-esg-pillar-name {
  font-size: 13px;
  font-weight: 500;
  color: var(--uza-navy);
  letter-spacing: -0.01em;
}
.cw-esg-pillar-stats {
  display: flex;
  gap: 16px;
  padding-top: 8px;
  border-top: 0.5px solid var(--uza-border);
}
.cw-esg-pillar-stat {
  display: flex;
  flex-direction: column;
  gap: 2px;
}
.cw-esg-pillar-stat-v {
  font-size: 18px;
  font-weight: 400;
  color: var(--uza-navy);
  font-variant-numeric: tabular-nums;
  letter-spacing: -0.02em;
}
.cw-esg-pillar-stat-l {
  font-size: 9.5px;
  font-weight: 500;
  color: var(--uza-gray);
  text-transform: uppercase;
  letter-spacing: 0.05em;
}
.cw-esg-pillar-chips {
  display: flex;
  gap: 6px;
}
/* Sprint C · Sector benchmark line under pillar stats */
.cw-esg-pillar-bench {
  display: flex; align-items: baseline; gap: 6px;
  margin-top: 8px;
  padding-top: 8px;
  border-top: 0.5px dashed rgba(15, 23, 60, 0.1);
  font-size: 10.5px;
  font-variant-numeric: tabular-nums;
}
.cw-esg-pillar-bench-cap {
  color: var(--uza-gray);
  font-size: 9.5px;
  letter-spacing: 0.04em;
  text-transform: uppercase;
  font-weight: 500;
}
.cw-esg-pillar-bench-v {
  font-weight: 600;
  color: var(--uza-navy);
}
.cw-esg-pillar-bench-diff {
  margin-left: auto;
  font-weight: 600;
  padding: 1px 6px;
  border-radius: 8px;
}
.cw-esg-pillar-bench-up   { color: #1D9E75; background: rgba(29, 158, 117, 0.10); }
.cw-esg-pillar-bench-down { color: #E24B4A; background: rgba(226, 75, 74, 0.10); }
.cw-esg-chip {
  font-size: 10px;
  font-weight: 600;
  padding: 2px 8px;
  border-radius: 10px;
  font-variant-numeric: tabular-nums;
}
.cw-esg-chip-good {
  background: rgba(29, 158, 117, 0.10);
  color: var(--uza-teal);
}
.cw-esg-chip-bad {
  background: rgba(226, 75, 74, 0.10);
  color: var(--uza-red);
}

.cw-esg-section {
  background: white;
  border: 0.5px solid var(--uza-border);
  border-radius: 12px;
  padding: 14px 16px;
}
.cw-esg-section .cw-section-label {
  margin-bottom: 10px;
}

.cw-esg-metrics {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.cw-esg-metric {
  padding: 10px 12px;
  background: var(--uza-bg2);
  border-radius: 8px;
  /* top-stripe via .cw-top-stripe-accent ниже (заменяет border-left) */
  display: flex;
  flex-direction: column;
  gap: 5px;
}
.cw-esg-m-row1 {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 10px;
}
.cw-esg-m-name {
  font-size: 12px;
  font-weight: 500;
  color: var(--uza-navy);
  flex: 1;
  line-height: 1.35;
}
.cw-esg-m-pct {
  font-size: 13px;
  font-weight: 600;
  font-variant-numeric: tabular-nums;
  flex-shrink: 0;
}
.cw-esg-m-row2 {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  font-size: 10.5px;
}
.cw-esg-m-stat {
  display: inline-flex;
  gap: 4px;
}
.cw-esg-m-stat-l { color: var(--uza-gray); }
.cw-esg-m-stat-v {
  color: var(--uza-navy);
  font-weight: 500;
  font-variant-numeric: tabular-nums;
}
.cw-esg-m-bar-wrap {
  height: 3px;
  background: rgba(15, 23, 60, 0.06);
  border-radius: 2px;
  overflow: hidden;
  margin-top: 2px;
}
.cw-esg-m-bar {
  height: 100%;
  border-radius: 2px;
  transition: width 600ms cubic-bezier(0.34, 1.2, 0.64, 1);
}

.cw-esg-issues {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.cw-esg-issue {
  padding: 10px 12px;
  background: var(--uza-bg2);
  border-radius: 8px;
  display: flex;
  flex-direction: column;
  gap: 6px;
  /* top-stripe via .cw-esg-issue::before; цвет модифицируется через --accent */
  --accent: #94A3B8;
}
.cw-esg-issue-open       { --accent: var(--uza-red); }
.cw-esg-issue-in_progress { --accent: var(--uza-amber); }
.cw-esg-issue-mitigated  { --accent: #7DC4A0; }
.cw-esg-issue-closed { opacity: 0.6; }

.cw-esg-issue-header {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  align-items: center;
}
.cw-esg-pillar-tag, .cw-esg-sev-pill, .cw-esg-status-pill {
  font-size: 9.5px;
  font-weight: 600;
  padding: 2px 7px;
  border-radius: 3px;
  letter-spacing: 0.02em;
}
.cw-esg-pillar-tag { font-size: 11px; }
.cw-esg-issue-title {
  font-size: 12.5px;
  font-weight: 500;
  color: var(--uza-navy);
}
.cw-esg-issue-desc {
  font-size: 11px;
  color: var(--uza-gray);
  line-height: 1.45;
}

/* ═══════════════════════════════════════════════════════════════════ */
/* ═══ CONSULTANTS — per-company + collapsible directory             ═══ */
/* ═══════════════════════════════════════════════════════════════════ */

.cw-cons-scroll {
  flex: 1;
  overflow-y: auto;
  padding: 16px 20px;
  display: flex;
  flex-direction: column;
  gap: 16px;
}

/* ─── KPI strip ─── */
.cw-cons-kpis {
  display: flex;
  align-items: stretch;
  gap: 0;
  background: white;
  border: 0.5px solid var(--uza-border);
  border-radius: 12px;
  padding: 14px 18px;
  animation: kpiSumIn 0.4s cubic-bezier(0.34, 1.2, 0.64, 1) both;
}
.cw-cons-kpi {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 4px;
  padding: 0 12px;
}
.cw-cons-kpi-label {
  font-size: 9.5px;
  font-weight: 600;
  letter-spacing: 0.05em;
  text-transform: uppercase;
  color: var(--uza-gray);
}
.cw-cons-kpi-value {
  font-size: 22px;
  font-weight: 400;
  letter-spacing: -0.025em;
  color: var(--uza-navy);
  font-variant-numeric: tabular-nums;
}
.cw-cons-kpi-divider {
  width: 1px;
  background: var(--uza-border);
  align-self: stretch;
}

/* ─── Rich per-company cards ─── */
.cw-cons-cards {
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.cw-cons-card-rich {
  background: white;
  border: 0.5px solid var(--uza-border);
  /* top-stripe via .cw-top-stripe-accent ниже (заменяет border-left) */
  border-radius: 12px;
  padding: 14px 16px;
  display: flex;
  flex-direction: column;
  gap: 10px;
  box-shadow: 0 2px 8px rgba(15, 23, 60, 0.04);
  transition: box-shadow 200ms;
  animation: kpiSumIn 0.4s cubic-bezier(0.34, 1.2, 0.64, 1) both;
}
.cw-cons-card-rich:hover {
  box-shadow: 0 6px 20px rgba(15, 23, 60, 0.08);
}

.cw-cons-rich-header {
  display: flex;
  align-items: center;
  gap: 12px;
}
.cw-cons-rich-abbr {
  font-size: 18px;
  font-weight: 600;
  color: var(--accent);
  letter-spacing: -0.015em;
  background: rgba(127, 119, 221, 0.06);
  padding: 8px 12px;
  border-radius: 8px;
  min-width: 60px;
  text-align: center;
  flex-shrink: 0;
}
.cw-cons-rich-titles {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 4px;
  min-width: 0;
}
.cw-cons-rich-name {
  font-size: 14px;
  font-weight: 500;
  color: var(--uza-navy);
  letter-spacing: -0.01em;
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}
.cw-cons-rich-big4 {
  font-size: 9px;
  font-weight: 700;
  letter-spacing: 0.04em;
  padding: 1px 6px;
  background: linear-gradient(135deg, #FFD700, #FFA500);
  color: white;
  border-radius: 3px;
  box-shadow: 0 1px 3px rgba(255, 165, 0, 0.30);
  text-transform: uppercase;
}
.cw-cons-rich-stats {
  display: flex;
  gap: 6px;
  align-items: center;
  font-size: 11px;
  color: var(--uza-gray);
  flex-wrap: wrap;
}
.cw-cons-rich-stat {
  font-variant-numeric: tabular-nums;
}
.cw-cons-rich-pct {
  font-size: 22px;
  font-weight: 400;
  letter-spacing: -0.025em;
  font-variant-numeric: tabular-nums;
  flex-shrink: 0;
}

.cw-cons-rich-sources {
  display: flex;
  gap: 6px;
  flex-wrap: wrap;
}
.cw-cons-rich-source {
  font-size: 9.5px;
  font-weight: 500;
  padding: 2px 8px;
  background: var(--uza-bg2);
  color: var(--uza-gray);
  border-radius: 4px;
  text-transform: lowercase;
  letter-spacing: 0.02em;
}

.cw-cons-rich-projects {
  border-top: 0.5px solid var(--uza-border);
  padding-top: 10px;
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.cw-cons-rich-projects-label {
  font-size: 9.5px;
  font-weight: 600;
  letter-spacing: 0.05em;
  text-transform: uppercase;
  color: var(--uza-gray);
  margin-bottom: 4px;
}
.cw-cons-rich-project {
  display: grid;
  grid-template-columns: 18px 1fr auto;
  gap: 8px;
  align-items: center;
  padding: 5px 8px;
  border-radius: 6px;
  font-size: 11.5px;
  cursor: pointer;
  transition: background 150ms;
}
.cw-cons-rich-project:hover {
  background: var(--uza-bg2);
}
.cw-cons-rich-project-status {
  font-size: 14px;
  font-weight: 600;
  text-align: center;
  line-height: 1;
}
.cw-cons-rich-project-title {
  color: var(--uza-navy);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.cw-cons-rich-project-date {
  color: var(--uza-gray);
  font-size: 10px;
  font-variant-numeric: tabular-nums;
  white-space: nowrap;
}

/* ─── Collapsible directory section ─── */
.cw-cons-dir-section {
  background: white;
  border: 0.5px solid var(--uza-border);
  border-radius: 12px;
  overflow: hidden;
}
.cw-cons-dir-toggle {
  width: 100%;
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 12px 16px;
  background: transparent;
  border: none;
  font-size: 12px;
  font-weight: 500;
  color: var(--uza-navy);
  cursor: pointer;
  font-family: inherit;
  text-align: left;
  transition: background 150ms;
}
.cw-cons-dir-toggle:hover {
  background: var(--uza-bg2);
}
.cw-cons-dir-toggle-icon {
  display: inline-block;
  font-size: 18px;
  font-weight: 400;
  color: var(--uza-purple);
  transition: transform 200ms;
  width: 14px;
  text-align: center;
}
.cw-cons-dir-toggle-icon.open {
  transform: rotate(90deg);
}
.cw-cons-dir-count {
  margin-left: auto;
  font-size: 10px;
  font-weight: 600;
  padding: 2px 8px;
  background: var(--uza-bg2);
  color: var(--uza-gray);
  border-radius: 8px;
  font-variant-numeric: tabular-nums;
}
.cw-cons-dir-body {
  padding: 12px 16px 16px;
  border-top: 0.5px solid var(--uza-border);
  animation: cwCtaIn 0.3s ease-out both;
}

/* ─── Legacy directory grid (kept for collapsible body) ─── */
.cw-cons-group {
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.cw-cons-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(160px, 1fr));
  gap: 8px;
}
.cw-cons-card {
  background: var(--uza-bg2);
  border: 0.5px solid var(--uza-border);
  /* top-stripe via .cw-top-stripe-accent ниже (заменяет border-left) */
  border-radius: 8px;
  padding: 10px 12px;
  display: flex;
  flex-direction: column;
  gap: 3px;
  position: relative;
  transition: all 180ms;
}
.cw-cons-card:hover {
  background: white;
  box-shadow: 0 2px 8px rgba(15, 23, 60, 0.06);
}
.cw-cons-abbr {
  font-size: 15px;
  font-weight: 600;
  color: var(--accent);
  letter-spacing: -0.015em;
}
.cw-cons-name {
  font-size: 11.5px;
  font-weight: 500;
  color: var(--uza-navy);
  line-height: 1.3;
}
.cw-cons-name-en {
  font-size: 10px;
  color: var(--uza-gray);
}
.cw-cons-tag-big4 {
  position: absolute;
  top: 6px;
  right: 6px;
  font-size: 8px;
  font-weight: 700;
  letter-spacing: 0.04em;
  padding: 1px 4px;
  background: linear-gradient(135deg, #FFD700, #FFA500);
  color: white;
  border-radius: 3px;
  box-shadow: 0 1px 2px rgba(255, 165, 0, 0.25);
}

/* Notice (no longer used by default; kept for future) */
.cw-cons-notice {
  display: flex;
  align-items: flex-start;
  gap: 12px;
  padding: 12px 14px;
  background: rgba(127, 119, 221, 0.08);
  border: 0.5px solid rgba(127, 119, 221, 0.20);
  border-radius: 10px;
  /* top-stripe via .cw-rt-fact::before — purple accent */
  --accent: var(--uza-purple);
}
.cw-cons-notice-icon { font-size: 18px; color: var(--uza-purple); font-weight: 600; flex-shrink: 0; line-height: 1; margin-top: 1px; }
.cw-cons-notice-title { font-size: 12.5px; font-weight: 600; color: var(--uza-navy); margin-bottom: 3px; }
.cw-cons-notice-msg { font-size: 11.5px; color: var(--uza-gray); line-height: 1.5; }
.cw-cons-notice-link { color: var(--uza-purple); font-weight: 500; text-decoration: none; }
.cw-cons-notice-link:hover { text-decoration: underline; }

/* ═══════════════════════════════════════════════════════════════════ */
/* ═══ CREDIT PORTFOLIO VIEW                                         ═══ */
/* ═══════════════════════════════════════════════════════════════════ */

.cw-invest-scroll {
  flex: 1;
  overflow-y: auto;
  /* Embedded InvestProjects has its own internal padding & layout */
}
.cw-cred-scroll {
  flex: 1;
  overflow-y: auto;
  padding: 16px 20px;
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.cw-cred-kpis {
  display: flex;
  align-items: stretch;
  gap: 0;
  background: white;
  border: 0.5px solid var(--uza-border);
  border-radius: 12px;
  padding: 14px 18px;
  animation: kpiSumIn 0.4s cubic-bezier(0.34, 1.2, 0.64, 1) both;
}
.cw-cred-kpi {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 4px;
  padding: 0 12px;
}
.cw-cred-kpi-label {
  font-size: 9.5px;
  font-weight: 600;
  letter-spacing: 0.05em;
  text-transform: uppercase;
  color: var(--uza-gray);
}
.cw-cred-kpi-value {
  font-size: 22px;
  font-weight: 400;
  letter-spacing: -0.025em;
  color: var(--uza-navy);
  font-variant-numeric: tabular-nums;
}
.cw-cred-kpi-divider {
  width: 1px;
  background: var(--uza-border);
  align-self: stretch;
}

.cw-cred-section {
  background: white;
  border: 0.5px solid var(--uza-border);
  border-radius: 12px;
  padding: 14px 16px;
}
.cw-cred-section .cw-section-label {
  margin-bottom: 12px;
}

/* Lender breakdown */
.cw-cred-buckets {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.cw-cred-bucket {
  background: var(--uza-bg2);
  border-radius: 8px;
  padding: 8px 12px;
}
.cw-cred-bucket-row {
  display: grid;
  grid-template-columns: 12px 1fr auto auto auto;
  gap: 10px;
  align-items: center;
  font-size: 12px;
  margin-bottom: 5px;
}
.cw-cred-bucket-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  flex-shrink: 0;
}
.cw-cred-bucket-label {
  font-weight: 500;
  color: var(--uza-navy);
}
.cw-cred-bucket-count {
  font-size: 10px;
  color: var(--uza-gray);
  font-variant-numeric: tabular-nums;
  padding: 0 8px;
  border-left: 0.5px solid var(--uza-border);
}
.cw-cred-bucket-debt {
  color: var(--uza-navy);
  font-weight: 500;
  font-variant-numeric: tabular-nums;
}
.cw-cred-bucket-pct {
  font-size: 11px;
  font-weight: 600;
  color: var(--accent);
  font-variant-numeric: tabular-nums;
  min-width: 40px;
  text-align: right;
}
.cw-cred-bucket-bar {
  height: 4px;
  background: rgba(15, 23, 60, 0.06);
  border-radius: 2px;
  overflow: hidden;
}
.cw-cred-bucket-bar-fill {
  height: 100%;
  border-radius: 2px;
  transition: width 600ms cubic-bezier(0.34, 1.2, 0.64, 1);
}

/* Sprint B · Maturity ladder */
.cw-cred-ladder {
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.cw-cred-ladder-row {
  display: grid;
  grid-template-columns: 130px 1fr 140px 90px;
  align-items: center;
  gap: 12px;
  padding: 6px 10px;
  background: var(--uza-bg2);
  border: 0.5px solid var(--uza-border);
  /* top-stripe via .cw-top-stripe-accent ниже (заменяет border-left) */
  border-radius: 8px;
  transition: transform 0.18s, box-shadow 0.18s;
}
.cw-cred-ladder-row:hover {
  transform: translateX(2px);
  box-shadow: 0 4px 12px rgba(15, 23, 60, 0.06);
}
.cw-cred-ladder-label {
  font-size: 12px;
  font-weight: 500;
  color: var(--uza-navy);
}
.cw-cred-ladder-bar-track {
  height: 8px;
  background: rgba(15, 23, 60, 0.06);
  border-radius: 4px;
  overflow: hidden;
}
.cw-cred-ladder-bar-fill {
  height: 100%;
  border-radius: 4px;
  transition: width 600ms cubic-bezier(0.34, 1.2, 0.64, 1);
}
.cw-cred-ladder-debt {
  font-size: 13px;
  font-weight: 500;
  color: var(--uza-navy);
  font-variant-numeric: tabular-nums;
  text-align: right;
}
.cw-cred-ladder-meta {
  font-size: 10.5px;
  color: var(--uza-gray);
  text-align: right;
  font-variant-numeric: tabular-nums;
}
@media (max-width: 720px) {
  .cw-cred-ladder-row {
    grid-template-columns: 100px 1fr 70px;
  }
  .cw-cred-ladder-meta { display: none; }
}

/* Currency cards */
.cw-cred-currencies {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(140px, 1fr));
  gap: 8px;
}
.cw-cred-currency {
  background: var(--uza-bg2);
  border: 0.5px solid var(--uza-border);
  /* top-stripe via .cw-top-stripe-accent ниже (заменяет border-left) */
  border-radius: 8px;
  padding: 10px 12px;
  display: flex;
  flex-direction: column;
  gap: 3px;
}
.cw-cred-currency-code {
  font-size: 18px;
  font-weight: 600;
  letter-spacing: -0.015em;
  line-height: 1;
}
.cw-cred-currency-debt {
  font-size: 13px;
  color: var(--uza-navy);
  font-weight: 500;
  font-variant-numeric: tabular-nums;
}
.cw-cred-currency-meta {
  font-size: 10px;
  color: var(--uza-gray);
}

/* Loans table */
.cw-cred-table {
  border: 0.5px solid var(--uza-border);
  border-radius: 8px;
  overflow: hidden;
}
.cw-cred-table-header {
  display: grid;
  grid-template-columns: 70px 2fr 60px 70px 1fr 100px;
  gap: 10px;
  padding: 9px 12px;
  background: var(--uza-bg2);
  font-size: 10px;
  font-weight: 600;
  letter-spacing: 0.05em;
  text-transform: uppercase;
  color: var(--uza-gray);
  border-bottom: 0.5px solid var(--uza-border);
}
.cw-cred-row {
  display: grid;
  grid-template-columns: 70px 2fr 60px 70px 1fr 100px;
  gap: 10px;
  padding: 9px 12px;
  align-items: center;
  font-size: 12px;
  color: var(--uza-navy);
  border-bottom: 0.5px solid rgba(15, 23, 60, 0.04);
}
.cw-cred-row:last-child { border-bottom: none; }
.cw-cred-row:hover { background: var(--uza-bg2); }
.cw-cred-row-overdue { background: rgba(226, 75, 74, 0.04); }
.cw-cred-row-overdue:hover { background: rgba(226, 75, 74, 0.08); }

.cw-cred-cell-code {
  font-weight: 600;
  font-variant-numeric: tabular-nums;
  display: flex;
  gap: 6px;
  align-items: center;
}
.cw-cred-guaranteed {
  font-size: 9px;
  font-weight: 700;
  background: rgba(29, 158, 117, 0.15);
  color: var(--uza-teal);
  padding: 1px 4px;
  border-radius: 3px;
}
.cw-cred-cell-bank {
  display: flex;
  flex-direction: column;
  gap: 3px;
  min-width: 0;
}
.cw-cred-lender-pill {
  font-size: 9px;
  font-weight: 600;
  padding: 1px 6px;
  border-radius: 3px;
  letter-spacing: 0.02em;
  align-self: flex-start;
}
.cw-cred-bank-name {
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  font-size: 11.5px;
}
.cw-cred-cur-pill {
  font-size: 11px;
  font-weight: 600;
  letter-spacing: 0.02em;
}
.cw-cred-cell-rate, .cw-cred-cell-debt {
  font-variant-numeric: tabular-nums;
  font-weight: 500;
  text-align: right;
}
.cw-cred-cell-due {
  font-size: 11px;
  color: var(--uza-gray);
  font-variant-numeric: tabular-nums;
}
.cw-cred-cell-due.overdue {
  color: var(--uza-red);
  font-weight: 600;
}
.cw-cred-th-rate, .cw-cred-th-debt, .cw-cred-th-due { text-align: right; }

/* ═══════════════════════════════════════════════════════════════════ */
/* ═══ PROCUREMENT VIEW                                              ═══ */
/* ═══════════════════════════════════════════════════════════════════ */

.cw-proc-scroll {
  flex: 1;
  overflow-y: auto;
  padding: 16px 20px;
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.cw-proc-kpis {
  display: flex;
  align-items: stretch;
  gap: 0;
  background: white;
  border: 0.5px solid var(--uza-border);
  border-radius: 12px;
  padding: 14px 18px;
  animation: kpiSumIn 0.4s cubic-bezier(0.34, 1.2, 0.64, 1) both;
}
.cw-proc-kpi {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 4px;
  padding: 0 12px;
}
.cw-proc-kpi-label {
  font-size: 9.5px;
  font-weight: 600;
  letter-spacing: 0.05em;
  text-transform: uppercase;
  color: var(--uza-gray);
}
.cw-proc-kpi-value {
  font-size: 20px;
  font-weight: 400;
  letter-spacing: -0.025em;
  color: var(--uza-navy);
  font-variant-numeric: tabular-nums;
}
.cw-proc-kpi-meta {
  font-size: 10px;
  color: var(--uza-gray);
  margin-top: 2px;
}
.cw-proc-kpi-divider {
  width: 1px;
  background: var(--uza-border);
  align-self: stretch;
}

/* Best / Worst categories */
.cw-proc-cats-row {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 12px;
}
.cw-proc-cats-block {
  background: white;
  border: 0.5px solid var(--uza-border);
  border-radius: 12px;
  padding: 14px 16px;
}
.cw-proc-cats-block .cw-section-label {
  margin-bottom: 10px;
}
.cw-proc-cats {
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.cw-proc-cat {
  background: var(--uza-bg2);
  /* top-stripe via .cw-top-stripe-accent ниже (заменяет border-left) */
  border-radius: 6px;
  padding: 8px 10px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}
.cw-proc-cat-name {
  font-size: 12px;
  font-weight: 500;
  color: var(--uza-navy);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  flex: 1;
}
.cw-proc-cat-stats {
  display: flex;
  gap: 8px;
  align-items: center;
  flex-shrink: 0;
}
.cw-proc-cat-dev {
  font-size: 13px;
  font-weight: 600;
  font-variant-numeric: tabular-nums;
}
.cw-proc-cat-count {
  font-size: 9.5px;
  color: var(--uza-gray);
  font-variant-numeric: tabular-nums;
}

/* Purchases table */
.cw-proc-section {
  background: white;
  border: 0.5px solid var(--uza-border);
  border-radius: 12px;
  padding: 14px 16px;
}
.cw-proc-section .cw-section-label {
  margin-bottom: 10px;
}

/* Sprint C · Supplier concentration */
.cw-proc-supplier-flag {
  display: inline-block;
  margin-left: 8px;
  padding: 2px 8px;
  border-radius: 11px;
  font-size: 9.5px;
  letter-spacing: 0.05em;
  font-weight: 600;
  text-transform: none;
}
.cw-proc-supplier-flag-warn {
  background: rgba(226, 75, 74, 0.12);
  color: #A82C2B;
}
.cw-proc-supplier-bar {
  display: flex;
  height: 14px;
  border-radius: 7px;
  overflow: hidden;
  background: rgba(15, 23, 60, 0.04);
  margin-bottom: 10px;
}
.cw-proc-supplier-bar-seg {
  transition: opacity 120ms;
}
.cw-proc-supplier-bar-seg:hover { opacity: 0.85; cursor: help; }
.cw-proc-supplier-bar-other {
  background: rgba(148, 163, 184, 0.4) !important;
}
.cw-proc-supplier-list { display: flex; flex-direction: column; gap: 4px; }
.cw-proc-supplier-row {
  display: grid;
  grid-template-columns: 10px 1fr auto auto;
  align-items: center;
  gap: 8px;
  padding: 6px 8px;
  border-radius: 6px;
  /* top-stripe via .cw-proc-row-acc::before */
  background: var(--uza-bg2);
  font-size: 12px;
  transition: background 120ms;
}
.cw-proc-supplier-row:hover { background: rgba(127, 119, 221, 0.04); }
.cw-proc-supplier-row-other { opacity: 0.75; }
.cw-proc-supplier-dot { width: 10px; height: 10px; border-radius: 50%; }
.cw-proc-supplier-name {
  font-weight: 500;
  color: var(--uza-navy);
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}
.cw-proc-supplier-count {
  font-size: 11px;
  color: var(--uza-gray);
  font-variant-numeric: tabular-nums;
}
.cw-proc-supplier-pct {
  font-weight: 600;
  color: var(--uza-navy);
  font-variant-numeric: tabular-nums;
  min-width: 48px;
  text-align: right;
}

.cw-proc-purchases {
  border: 0.5px solid var(--uza-border);
  border-radius: 8px;
  overflow: hidden;
}
.cw-proc-purchases-header {
  display: grid;
  grid-template-columns: 2.5fr 1.5fr 100px 100px 80px;
  gap: 10px;
  padding: 9px 12px;
  background: var(--uza-bg2);
  font-size: 10px;
  font-weight: 600;
  letter-spacing: 0.05em;
  text-transform: uppercase;
  color: var(--uza-gray);
  border-bottom: 0.5px solid var(--uza-border);
}
.cw-proc-ph-price, .cw-proc-ph-market, .cw-proc-ph-dev { text-align: right; }
.cw-proc-purchase {
  display: grid;
  grid-template-columns: 2.5fr 1.5fr 100px 100px 80px;
  gap: 10px;
  padding: 9px 12px;
  align-items: center;
  font-size: 12px;
  border-bottom: 0.5px solid rgba(15, 23, 60, 0.04);
  /* top-stripe via .cw-table-row-purchase::before; cell uses --dev-color
     which the rule maps into --accent fallback */
  --accent: var(--dev-color);
}
.cw-proc-purchase:last-child { border-bottom: none; }
.cw-proc-purchase:hover { background: var(--uza-bg2); }

.cw-proc-pcell-name {
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 0;
}
.cw-proc-product {
  color: var(--uza-navy);
  font-weight: 500;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.cw-proc-cat-tag {
  font-size: 9.5px;
  color: var(--uza-gray);
  text-transform: uppercase;
  letter-spacing: 0.04em;
}
.cw-proc-pcell-supplier {
  color: var(--uza-gray);
  font-size: 11px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.cw-proc-pcell-price, .cw-proc-pcell-market, .cw-proc-pcell-dev {
  text-align: right;
  font-variant-numeric: tabular-nums;
}
.cw-proc-pcell-dev {
  font-weight: 600;
  font-size: 13px;
}

/* ═══════════════════════════════════════════════════════════════════ */
/* ═══ FINANCIALS VIEW (МСФО + НСБУ — same styles)                  ═══ */
/* ═══════════════════════════════════════════════════════════════════ */

.cw-fin-scroll {
  flex: 1;
  overflow-y: auto;
  padding: 16px 20px;
  display: flex;
  flex-direction: column;
  gap: 16px;
}

/* ── Sprint A: Financial KPI-strip (МСФО/НСБУ summary tiles) ── */
.cw-fin-kpi-strip {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
  gap: 8px;
  margin-bottom: 12px;
}
.cw-fin-kpi-tile {
  background: #FFFFFF;
  border: 0.5px solid var(--uza-border);
  border-radius: 11px;
  padding: 10px 12px;
  display: flex; flex-direction: column; gap: 3px;
  position: relative;
  overflow: hidden;
  transition: box-shadow 0.18s, transform 0.18s;
}
.cw-fin-kpi-tile:hover {
  box-shadow: 0 4px 16px rgba(15, 23, 60, 0.06);
  transform: translateY(-1px);
}
.cw-fin-kpi-tile::before {
  content: "";
  position: absolute;
  inset: 0 0 auto 0; height: 2px;
  background: currentColor;
  opacity: 0.6;
}
.cw-fin-kpi-label {
  font-size: 9.5px;
  letter-spacing: 0.06em;
  text-transform: uppercase;
  color: #888780;
  font-weight: 500;
}
.cw-fin-kpi-value {
  font-size: 18px;
  font-weight: 500;
  letter-spacing: -0.02em;
  color: #1E2A4A;
  font-variant-numeric: tabular-nums;
  line-height: 1.1;
  margin-top: 1px;
}
.cw-fin-kpi-unit {
  font-size: 10px;
  font-weight: 400;
  color: #888780;
  margin-left: 3px;
}
.cw-fin-kpi-hint {
  font-size: 10px;
  color: #888780;
  margin-top: 1px;
}
.cw-fin-kpi-good { color: #1D9E75; }
.cw-fin-kpi-info { color: #378ADD; }
.cw-fin-kpi-warn { color: #EF9F27; }
.cw-fin-kpi-bad  { color: #E24B4A; }
.cw-fin-kpi-good .cw-fin-kpi-hint,
.cw-fin-kpi-info .cw-fin-kpi-hint,
.cw-fin-kpi-warn .cw-fin-kpi-hint,
.cw-fin-kpi-bad  .cw-fin-kpi-hint {
  color: currentColor;
  opacity: 0.85;
}

/* Report type switcher */
.cw-fin-type-bar {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 14px;
  background: white;
  border: 0.5px solid var(--uza-border);
  border-radius: 10px;
}
.cw-fin-type-label {
  font-size: 9px;
  font-weight: 600;
  letter-spacing: 0.06em;
  text-transform: uppercase;
  color: var(--uza-gray);
  margin-right: 4px;
}
.cw-fin-type-btn {
  font-size: 12px;
  font-weight: 500;
  padding: 6px 14px;
  border-radius: 7px;
  background: transparent;
  border: 0.5px solid var(--uza-border);
  color: var(--uza-gray);
  cursor: pointer;
  transition: all 180ms;
  font-family: inherit;
  display: inline-flex;
  align-items: center;
  gap: 6px;
}
.cw-fin-type-btn:hover:not(.disabled) {
  background: var(--uza-bg2);
  color: var(--uza-navy);
}
.cw-fin-type-btn.active {
  background: var(--uza-teal);
  color: white;
  border-color: var(--uza-teal);
  box-shadow: 0 2px 8px rgba(29, 158, 117, 0.30);
}
.cw-fin-type-btn.disabled {
  opacity: 0.45;
  cursor: not-allowed;
  text-decoration: line-through;
}
.cw-fin-type-na {
  font-size: 9px;
  color: var(--uza-bg4);
  text-transform: uppercase;
  letter-spacing: 0.04em;
  font-weight: 500;
}

/* Metadata strip */
.cw-fin-meta {
  display: flex;
  align-items: stretch;
  gap: 0;
  background: white;
  border: 0.5px solid var(--uza-border);
  border-radius: 12px;
  padding: 12px 18px;
  flex-wrap: wrap;
  animation: kpiSumIn 0.4s cubic-bezier(0.34, 1.2, 0.64, 1) both;
}
.cw-fin-meta-item {
  flex: 1 1 auto;
  min-width: 100px;
  display: flex;
  flex-direction: column;
  gap: 3px;
  padding: 0 12px;
}
.cw-fin-meta-label {
  font-size: 9px;
  font-weight: 600;
  letter-spacing: 0.06em;
  text-transform: uppercase;
  color: var(--uza-gray);
}
.cw-fin-meta-value {
  font-size: 13px;
  font-weight: 500;
  color: var(--uza-navy);
  font-variant-numeric: tabular-nums;
}
.cw-fin-meta-source {
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  max-width: 220px;
}
.cw-fin-meta-divider {
  width: 1px;
  background: var(--uza-border);
  align-self: stretch;
}
.cw-fin-audited-badge {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  font-size: 11px;
  font-weight: 600;
  padding: 5px 11px;
  background: rgba(29, 158, 117, 0.10);
  color: var(--uza-teal);
  border-radius: 14px;
  align-self: center;
  margin-left: auto;
}
.cw-fin-audited-badge span {
  font-size: 14px;
  font-weight: 700;
}

/* Lines table */
.cw-fin-table {
  background: white;
  border: 0.5px solid var(--uza-border);
  border-radius: 12px;
  overflow: hidden;
}
.cw-fin-table-header {
  display: grid;
  grid-template-columns: 1fr 200px;
  gap: 16px;
  padding: 10px 16px;
  background: var(--uza-bg2);
  font-size: 10px;
  font-weight: 600;
  letter-spacing: 0.05em;
  text-transform: uppercase;
  color: var(--uza-gray);
  border-bottom: 0.5px solid var(--uza-border);
}
.cw-fin-th-value {
  text-align: right;
}

.cw-fin-row {
  display: grid;
  grid-template-columns: 1fr 200px;
  gap: 16px;
  padding: 8px 16px;
  align-items: baseline;
  font-size: 12.5px;
  border-bottom: 0.5px solid rgba(15, 23, 60, 0.04);
  color: var(--uza-navy);
}
.cw-fin-row:last-child {
  border-bottom: none;
}
.cw-fin-row:hover {
  background: var(--uza-bg2);
}

/* Indent based on parent_code depth */
.cw-fin-cell-name {
  display: flex;
  align-items: baseline;
  gap: 8px;
  padding-left: calc(var(--depth) * 16px);
  min-width: 0;
}

.cw-fin-code {
  font-size: 10px;
  font-family: ui-monospace, "SF Mono", Consolas, monospace;
  color: var(--uza-gray);
  background: var(--uza-bg3);
  padding: 1px 6px;
  border-radius: 3px;
  flex-shrink: 0;
  font-variant-numeric: tabular-nums;
}

.cw-fin-name {
  flex: 1;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.cw-fin-calc-mark {
  font-size: 11px;
  color: var(--uza-purple);
  font-weight: 700;
  flex-shrink: 0;
}

.cw-fin-cell-value {
  text-align: right;
  font-variant-numeric: tabular-nums;
  font-weight: 500;
  white-space: nowrap;
}

.cw-fin-value-negative {
  color: var(--uza-red);
}
.cw-fin-value-negative::before {
  content: "(";
}
.cw-fin-value-negative::after {
  content: ")";
}

/* Subtotal: bold, top border, slightly colored */
.cw-fin-row-subtotal {
  font-weight: 600;
  background: rgba(127, 119, 221, 0.04);
  border-top: 0.5px solid var(--uza-purple);
}
.cw-fin-row-subtotal:hover {
  background: rgba(127, 119, 221, 0.08);
}
.cw-fin-row-subtotal .cw-fin-name {
  color: var(--uza-navy);
}
.cw-fin-row-subtotal .cw-fin-cell-value {
  font-weight: 700;
}

/* Calculated: italic, light bg */
.cw-fin-row-calculated {
  font-style: italic;
  background: rgba(127, 119, 221, 0.025);
}
.cw-fin-row-calculated .cw-fin-name {
  color: var(--uza-gray);
}

.cw-fin-row-zero {
  opacity: 0.55;
}

/* Notes section */
.cw-fin-section {
  background: white;
  border: 0.5px solid var(--uza-border);
  border-radius: 12px;
  padding: 14px 16px;
}
.cw-fin-notes {
  margin: 8px 0 0;
  font-size: 12px;
  color: var(--uza-gray);
  line-height: 1.55;
  white-space: pre-wrap;
}

/* Responsive: kanban columns wrap on narrow screens */
@media (max-width: 1100px) {
  .cw-kanban-board { grid-template-columns: repeat(3, minmax(180px, 1fr)); }
  .cw-list-row { grid-template-columns: 2fr 1fr 1fr; }
  .cw-list-c-direction { display: none; }
  .cw-bp-tops { grid-template-columns: 1fr 1fr; }
  .cw-esg-pillars { grid-template-columns: 1fr 1fr; }
  .cw-cred-table-header, .cw-cred-row { grid-template-columns: 60px 2fr 50px 70px 1fr 90px; }
  .cw-proc-purchases-header, .cw-proc-purchase { grid-template-columns: 2fr 1.2fr 90px 90px 70px; }
}
@media (max-width: 720px) {
  .cw-kanban-board { grid-template-columns: 1fr 1fr; }
  .cw-list-row { grid-template-columns: 2fr 1fr; }
  .cw-list-c-deadline { display: none; }
  .cw-list-filters { flex-wrap: wrap; }
  .cw-bp-tops { grid-template-columns: 1fr; }
  .cw-bp-table-header, .cw-bp-row { grid-template-columns: 2fr 1fr 1fr 60px; }
  .cw-bp-table-header > :nth-child(3), .cw-bp-row > :nth-child(3) { display: none; }
  .cw-kpi-summary { flex-wrap: wrap; }
  .cw-kpi-summary > .cw-kpi-sum-divider { display: none; }
  .cw-kpi-managers { grid-template-columns: 1fr; }
  .cw-esg-pillars { grid-template-columns: 1fr; }
  .cw-gov-kpis { grid-template-columns: 1fr 1fr; }
  .cw-gov-members { grid-template-columns: 1fr; }
  .cw-cons-kpis { flex-wrap: wrap; gap: 8px; }
  .cw-cons-kpi-divider { display: none; }
  .cw-cons-rich-header { flex-wrap: wrap; }
  .cw-cons-rich-pct { margin-left: auto; }
  .cw-cred-kpis { flex-wrap: wrap; gap: 12px; }
  .cw-cred-kpi-divider { display: none; }
  .cw-cred-kpi { flex: 1 1 calc(50% - 6px); }
  .cw-cred-table-header, .cw-cred-row { grid-template-columns: 50px 2fr 50px 1fr 80px; }
  .cw-cred-th-rate, .cw-cred-cell-rate { display: none; }
  .cw-proc-cats-row { grid-template-columns: 1fr; }
  .cw-proc-kpis { flex-wrap: wrap; gap: 12px; }
  .cw-proc-kpi-divider { display: none; }
  .cw-proc-kpi { flex: 1 1 calc(50% - 6px); }
  .cw-proc-purchases-header, .cw-proc-purchase { grid-template-columns: 2fr 1fr 70px 70px; }
  .cw-proc-ph-market, .cw-proc-pcell-market { display: none; }
  .cw-fin-meta { flex-wrap: wrap; gap: 8px; padding: 12px; }
  .cw-fin-meta-divider { display: none; }
  .cw-fin-meta-item { flex: 1 1 calc(50% - 4px); padding: 4px 0; }
  .cw-fin-audited-badge { margin-left: 0; }
  .cw-fin-table-header, .cw-fin-row { grid-template-columns: 1fr 130px; }
  .cw-fin-code { display: none; }
}

/* ── Sprint A · Overdue drill modal ── */
.cw-ov-modal-backdrop {
  position: fixed; inset: 0;
  background: rgba(15, 18, 40, 0.45);
  backdrop-filter: blur(8px);
  z-index: 1000;
  display: flex; align-items: center; justify-content: center;
  padding: 24px;
}
.cw-ov-modal-card {
  background: #FFFFFF;
  border-radius: 14px;
  width: 100%; max-width: 640px;
  max-height: calc(100vh - 48px);
  display: flex; flex-direction: column;
  box-shadow: 0 24px 64px rgba(15, 23, 60, 0.18), 0 8px 24px rgba(15, 23, 60, 0.08);
  overflow: hidden;
  animation: uzaModalIn .45s cubic-bezier(0.34, 1.2, 0.64, 1);
}
@keyframes uzaModalIn {
  0%   { opacity: 0; transform: translateY(20px) scale(0.97); }
  60%  { opacity: 1; transform: translateY(-2px) scale(1.005); }
  100% { opacity: 1; transform: translateY(0)   scale(1); }
}
.cw-ov-modal-head {
  display: flex; align-items: flex-start; justify-content: space-between;
  padding: 18px 20px;
  border-bottom: 0.5px solid var(--uza-border);
}
.cw-ov-modal-eyebrow {
  font-size: 10px;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: #888780;
  font-weight: 500;
}
.cw-ov-modal-title {
  font-size: 16px;
  font-weight: 500;
  letter-spacing: -0.01em;
  color: #1E2A4A;
  margin: 4px 0 0 0;
}
.cw-ov-modal-num {
  color: #E24B4A;
  font-weight: 600;
  font-variant-numeric: tabular-nums;
}
.cw-ov-modal-close {
  background: transparent; border: none; cursor: pointer;
  font-size: 24px; line-height: 1; color: #888780;
  padding: 0 4px;
  transition: color 120ms;
}
.cw-ov-modal-close:hover { color: #1E2A4A; }
.cw-ov-modal-body {
  flex: 1; overflow-y: auto;
  padding: 8px 0;
}
.cw-ov-modal-empty {
  text-align: center;
  padding: 32px;
  color: #888780;
  font-size: 13px;
}
.cw-ov-list {
  list-style: none; margin: 0; padding: 0;
}
.cw-ov-row {
  display: flex; align-items: flex-start; gap: 12px;
  padding: 12px 20px;
  border-bottom: 0.5px solid #F4F4F2;
  transition: background 120ms;
}
.cw-ov-row:last-child { border-bottom: none; }
.cw-ov-row:hover { background: #FAFAFC; }
.cw-ov-row-l { flex: 1; min-width: 0; }
.cw-ov-row-r {
  display: flex; align-items: center; gap: 12px;
  flex-shrink: 0;
}
.cw-ov-row-tag {
  font-size: 9px;
  letter-spacing: 0.08em;
  font-weight: 600;
  color: #888780;
  text-transform: uppercase;
}
.cw-ov-row-project .cw-ov-row-tag { color: #7F77DD; }
.cw-ov-row-title {
  font-size: 13px;
  font-weight: 500;
  color: #1E2A4A;
  margin-top: 3px;
  line-height: 1.3;
}
.cw-ov-row-owner {
  font-size: 11px;
  color: #888780;
  margin-top: 2px;
}
.cw-ov-row-days {
  font-size: 13px;
  font-weight: 600;
  color: #E24B4A;
  font-variant-numeric: tabular-nums;
}
.cw-ov-row-date {
  font-size: 10px;
  color: #888780;
  text-align: right;
  margin-top: 1px;
}
.cw-ov-row-link {
  font-size: 18px;
  color: #7F77DD;
  text-decoration: none;
  padding: 4px 8px;
  border-radius: 6px;
  transition: background 120ms;
}
.cw-ov-row-link:hover { background: rgba(127, 119, 221, 0.1); }

.cw-modal-enter-active { animation: cwModalFadeIn .25s ease both; }
.cw-modal-leave-active { animation: cwModalFadeOut .18s ease both; }
@keyframes cwModalFadeIn  { 0% { opacity: 0; } 100% { opacity: 1; } }
@keyframes cwModalFadeOut { 0% { opacity: 1; } 100% { opacity: 0; } }

/* ─── Top-stripe accent (replaces former `border-left: 3px solid …`).
 *      One unified rule for all card-like blocks that previously had a
 *      coloured left bar. Animation references uzaStripe* keyframes
 *      defined globally in uza-top-stripe.css. ─── */
:where(
  .cw-cta-note,
  .cw-esg-metric,
  .cw-cons-card-rich,
  .cw-cons-card,
  .cw-cred-account,
  .cw-cred-currency,
  .cw-proc-cat,
  .cw-act-cell,
  .cw-esg-issue,
  .cw-rt-fact,
  .cw-proc-row-acc,
  .cw-table-row-purchase
) {
  position: relative;
  overflow: hidden;
}
:where(
  .cw-cta-note,
  .cw-esg-metric,
  .cw-cons-card-rich,
  .cw-cons-card,
  .cw-cred-account,
  .cw-cred-currency,
  .cw-proc-cat,
  .cw-act-cell,
  .cw-esg-issue,
  .cw-rt-fact,
  .cw-proc-row-acc,
  .cw-table-row-purchase
)::before {
  content: "";
  position: absolute;
  top: 0; left: 0; right: 0;
  height: 3px;
  background: var(--accent, var(--uza-purple, #7F77DD));
  border-top-left-radius: inherit;
  border-top-right-radius: inherit;
  transform-origin: left center;
  animation:
    uzaStripeDrawIn .8s cubic-bezier(0.34, 1.2, 0.64, 1) 100ms both,
    uzaStripeBreathe 2.8s ease-in-out 1s infinite;
  pointer-events: none;
  z-index: 1;
}
@media (prefers-reduced-motion: reduce) {
  :where(.cw-cta-note, .cw-esg-metric, .cw-cons-card-rich, .cw-cons-card,
         .cw-cred-account, .cw-cred-currency, .cw-proc-cat, .cw-act-cell,
         .cw-esg-issue, .cw-rt-fact, .cw-proc-row-acc, .cw-table-row-purchase)::before {
    animation: none;
  }
}
</style>
