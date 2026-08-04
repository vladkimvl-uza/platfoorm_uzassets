<script setup lang="ts">
/**
 * CompanyWorkspace.vue
 * ─────────────────────────────────────────────────────────────────
 * Migrated 1:1 from legacy renderCompanyOverview (~600 lines).
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
import { ref, computed, onMounted, onUnmounted, provide, inject, watch, nextTick } from "vue";
import { useFormatters } from "@/composables/useFormatters";
import { useI18n } from "@/composables/useI18n";
import { getCurrentIntlLocale } from "@/locale/i18n";

const fmt = useFormatters();
const { t } = useI18n();
import { useRoute, useRouter, RouterLink } from "vue-router";
import { useNotificationsStore } from "@/stores/notifications";
import { companiesApi } from "@/api/companies";

const notifStore = useNotificationsStore();
import { ratingsApi, type AgencyRatingBrief } from "@/api/ratings";
import { companyLibraryApi } from "@/api/companyLibrary";
import { projectsApi, type ProjectBrief } from "@/api/projects";
import { tasksApi, type TaskBrief } from "@/api/tasks";
import { kpiApi, bpApi, BP_FIELDS, BP_PERIODS, type KpiManager, type BpComputed, type BpPeriod } from "@/api/bpKpi";
import { governanceApi, ROLE_TYPE_META, type RoleType } from "@/api/governance";
import { esgApi, PILLAR_META, SEVERITY_META, ISSUE_STATUS_META, type Pillar, type Severity, type IssueStatus } from "@/api/esg";
import { consultantsApi, type ConsultantBrief, type CompanyConsultantsResponse } from "@/api/consultants";
import {
  getLoans,
  getAggregate as getCreditAggregate,
  CP_LENDER_LABELS,
  cpCurrencyColor,
  toNum,
  type LoanRead,
  type CreditPortfolioAggregate,
} from "@/api/credit";
import {
  procurementAnalysisApi,
  paColorByDev,
  paFmtMoneyShort,
  paFmtMoney,
  type ProcurementAggregate,
  type CompanyRatingRow,
  type ClosureRow,
} from "@/api/procurement_analysis";
import {
  financialsApi,
  type FinancialReportListItem,
  type FinancialReportFull,
  type FinancialLineEdit,
} from "@/api/financials";
import { computeProgress, EXCLUDED_FROM_PCT } from "@/utils/progress";
import { kpiCompletionRatio, kpiWeightedRatio } from "@/utils/kpiRatio";
import CompanyNotesTab from "@/components/CompanyNotesTab.vue";
import CompanyCalendar from "@/components/Company/CompanyCalendar.vue";
import CompanyOverviewExtras from "@/components/CompanyOverviewExtras.vue";
import CompanyBoardList from "@/components/CompanyBoardList.vue";
import { auditorStyle, big4ChipStyle, ensureConsultants } from "@/utils/auditorStyle";
import CompanyTabBar from "@/components/Company/CompanyTabBar.vue";
import { COMPANY_TABS } from "@/components/Company/companyNavConfig";
import HighLevelFinancials from "@/components/Financials/HighLevelFinancials.vue";
import FinReportUpload from "@/components/Financials/FinReportUpload.vue";
import CompanyDrilldown from "@/components/Financials/CompanyDrilldown.vue";
import GovernanceEditor from "@/components/Governance/GovernanceEditor.vue";
import BoardMemberProfileModal from "@/components/Governance/BoardMemberProfileModal.vue";
import BoardMemberHoverCard, { type HoverAnchor } from "@/components/Governance/BoardMemberHoverCard.vue";
import ESGEditor from "@/components/ESG/ESGEditor.vue";
import ESGMaturityProfilePanel from "@/components/ESG/ESGMaturityProfilePanel.vue";
import ESGSwotPanel from "@/components/ESG/ESGSwotPanel.vue";
import UzaSegment from "@/components/UZA/UzaSegment.vue";
import UnitCostCompanyPanel from "@/components/UnitCost/UnitCostCompanyPanel.vue";
import { unitCostApi, type UCOverview, type UCCompany } from "@/api/unitCost";
import CompanyEmployeesTab from "@/components/Company/CompanyEmployeesTab.vue";
import CompanyEmployeesSummary from "@/components/Company/CompanyEmployeesSummary.vue";
import KanbanCard from "@/components/Kanban/KanbanCard.vue";
import TaskProjectEditor from "@/components/TaskProjectEditor.vue";
import BpEditor from "@/components/BusinessPlan/BpEditor.vue";
import CwProductionSection from "@/components/BusinessPlan/CwProductionSection.vue";
import KpiCompanyDashboard from "@/components/KPI/KpiCompanyDashboard.vue";
import KpiEditor from "@/components/KPI/KpiEditor.vue";
import RatingTile from "@/components/Ratings/RatingTile.vue";
import UzaStateBlock from "@/components/UZA/UzaStateBlock.vue";
import { usePermissions } from "@/composables/usePermissions";
import PmoTab from "@/components/PMO/PmoTab.vue";
import ReportingWizard from "@/components/reporting/ReportingWizard.vue";
import ProjectsStatusReport from "@/components/reporting/ProjectsStatusReport.vue";
import CompanyDocuments from "@/components/Documents/CompanyDocuments.vue";
import ExecOverview from "@/views/ExecOverview.vue";
import { useSavedFilter } from "@/composables/useSavedFilter";
import { i18nKey } from "@/locale/keys";
import { companyDisplayName, sectorDisplayName } from "@/utils/displayNames";


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
const sector = ref<{
  id: string;
  code: string;
  name_ru: string;
  name_uz?: string | null;
  name_uz_cyr?: string | null;
  name_en?: string | null;
  color_hex?: string | null;
} | null>(null);
const localizedCompanyName = computed(() => companyDisplayName(company.value));
const localizedSectorName = computed(() => sectorDisplayName(sector.value));

// Ссылка на сайт компании (премиум-пилюля в шапке)
const companyWebsite = computed<string | null>(() => {
  const raw = (company.value?.website || "").trim();
  if (!raw) return null;
  return /^https?:\/\//i.test(raw) ? raw : "https://" + raw;
});
const websiteHost = computed(() => {
  if (!companyWebsite.value) return "";
  try { return new URL(companyWebsite.value).host.replace(/^www\./, ""); }
  catch { return companyWebsite.value.replace(/^https?:\/\//, ""); }
});

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
const pmoPerm = usePermissions("pmo");
// Заметки/календарь — часть работы по задачам, поэтому право то же (tasks.edit).
// Без него вкладка «Календарь» read-only: наблюдателю не показываем кнопки,
// которые упрутся в 403 на бэкенде.
const tasksPerm = usePermissions("tasks");
// Сводный обзор внутри вкладки «Отчёт» — тот же экран, что /executive-overview,
// поэтому и право одно (exec_overview.view); иначе подвкладка была бы обходом.
const execOverviewPerm = usePermissions("exec_overview");
// Гейт вкладок воркспейса по правам. CompanyTabBar уже скрывает вкладки с
// `gated`, но адрес вида ?tab=unitcost открывал бы скрытую вкладку напрямую —
// поэтому проверяем те же права и здесь, при разборе URL.
const _tabGatePerms: Record<string, ReturnType<typeof usePermissions>> = {};
for (const g of [...new Set(COMPANY_TABS.filter(x => x.gated).map(x => x.gated as string))]) {
  _tabGatePerms[g] = usePermissions(g);
}
function tabAllowed(key: string): boolean {
  const gate = COMPANY_TABS.find(x => x.id === key)?.gated;
  return !gate || !!_tabGatePerms[gate]?.canView.value;
}
const companiesPerm = usePermissions("companies");  // для загрузки файлов отчётности (бэкенд требует companies.edit)
const pmoRefreshTick = ref(0);   // бамп после сохранения в редакторе → PmoTab перезагружает расписание
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
// Фактически показанный год отчётности (может отличаться от выбранного FY —
// у части компаний нет данных за текущий год, тогда берём последний доступный).
const finShownYear = ref<number>(0);

const year = ref<number>(new Date().getFullYear());
// Один раз после загрузки: если у выбранного (текущего) года нет ни проектов,
// ни задач, а данные есть за другой год — переключаемся на последний год с
// данными (как KPI/BP-вкладки, которые сами скатываются на доступный FY). Гвард
// не даёт перебивать ручной выбор пользователя через степпер года.
const _yearAutoAdjusted = ref(false);
function adjustYearToData() {
  if (_yearAutoAdjusted.value) return;
  const yrs = new Set<number>();
  for (const p of allProjects.value) {
    const py = (p as any).portfolio_year;
    if (py != null) yrs.add(Number(py));
  }
  for (const t of allTasks.value) {
    const py = (t as any).portfolio_year;
    if (py != null && !(t as any).is_project) yrs.add(Number(py));
  }
  if (yrs.size === 0) return;              // нет годовых данных — оставляем как есть
  if (yrs.has(year.value)) { _yearAutoAdjusted.value = true; return; }
  year.value = Math.max(...yrs);
  _yearAutoAdjusted.value = true;
}
// Подвкладки таба «Отчёт»: мастер отчёта | сводный обзор (exec-overview, scoped к компании)
const repSub = ref<"wizard" | "overview" | "projreport">("wizard");
function repSubBtn(active: boolean): string {
  const base = "padding:7px 16px;border:none;border-radius:8px;font-size:13px;font-weight:500;cursor:pointer;font-family:inherit;transition:all .14s;";
  return base + (active
    ? "background:#fff;color:var(--p-deep,#534ab7);box-shadow:0 1px 3px rgba(15,23,60,.1);"
    : "background:transparent;color:var(--t2,#475569);");
}
const VALID_TABS = ["overview", "people", "work", "documents", "kanban", "list", "pmo", "notes", "reporting",
                    "ifrs", "nsbu", "hlf", "bp", "unitcost", "credit",
                    "kpi", "procurement",
                    "governance", "consultants", "esg"] as const;
type TabKey = typeof VALID_TABS[number];

// URL-state: ?tab=kanban etc. Default = overview.
const activeTab = computed<TabKey>({
  get: () => {
    let t = String(route.query.tab || "");
    // Канбан/Список объединены в «Работа» — старые ссылки ?tab=kanban|list ведут на work.
    if (t === "kanban" || t === "list") t = "work";
    // Вкладка без права (?tab=… из ссылки) схлопывается в «Обзор» — так прямая
    // ссылка не обходит гейт, который CompanyTabBar применяет к списку вкладок.
    return (VALID_TABS as readonly string[]).includes(t) && tabAllowed(t)
      ? (t as TabKey)
      : "overview";
  },
  set: (val: TabKey) => {
    const newQuery = { ...route.query };
    if (val === "overview") delete newQuery.tab;
    else newQuery.tab = val;
    router.replace({ path: route.path, query: newQuery });
  },
});

// Вид внутри таба «Работа»: Канбан | Список. По умолчанию — Список.
// Запоминается в URL (?view=) и в профиле (localStorage), переоткрывается как оставили.
const WORK_VIEW_KEY = "cw_work_view";
const workView = computed<"kanban" | "list">({
  get: () => {
    const v = String(route.query.view || "");
    if (v === "kanban" || v === "list") return v;
    const legacy = String(route.query.tab || "");
    if (legacy === "kanban" || legacy === "list") return legacy;
    try { if (localStorage.getItem(WORK_VIEW_KEY) === "kanban") return "kanban"; } catch { /* ignore */ }
    return "list";
  },
  set: (val) => {
    try { localStorage.setItem(WORK_VIEW_KEY, val); } catch { /* ignore */ }
    const q: Record<string, any> = { ...route.query, tab: "work", view: val };
    router.replace({ path: route.path, query: q });
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
  { key: "overview",    label: i18nKey("Обзор"),        group: "manage" },
  { key: "people",      label: i18nKey("Сотрудники"),   group: "manage" },
  { key: "work",        label: i18nKey("Работа"),       group: "manage" },
  { key: "pmo",         label: "PMO",          group: "manage" },
  { key: "notes",       label: i18nKey("Календарь"),    group: "manage" },
  { key: "reporting",   label: i18nKey("Отчёт"),        group: "manage" },
  // Финансы
  { key: "ifrs",        label: i18nKey("МСФО"),         group: "finance",  fullPageRoute: "/financials" },
  { key: "nsbu",        label: i18nKey("НСБУ"),         group: "finance",  fullPageRoute: "/financials" },
  { key: "hlf",         label: i18nKey("Фин. отчётность"), group: "finance", fullPageRoute: "/financials" },
  { key: "bp",          label: i18nKey("Бизнес-план"),  group: "finance",  fullPageRoute: "/business-plan" },
  { key: "unitcost",    label: i18nKey("Себестоимость"), group: "finance", fullPageRoute: "/unit-cost" },
  // Операции
  { key: "kpi",         label: "KPI",          group: "ops",      fullPageRoute: "/kpi" },
  { key: "procurement", label: i18nKey("Закупки"),      group: "ops",      fullPageRoute: "/procurement/analysis" },
  // Стратегия
  { key: "governance",  label: i18nKey("Корп. упр."),   group: "strategy", fullPageRoute: "/governance" },
  { key: "consultants", label: i18nKey("Консультанты"), group: "strategy", fullPageRoute: "/consultants" },
  { key: "esg",         label: "ESG",          group: "strategy", fullPageRoute: "/esg" },
];

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
    // Perf: всё одним параллельным батчем. projects/tasks фильтруем по
    // company_code, поэтому НЕ ждём UUID из getOne (раньше был лишний серийный
    // round-trip). limit=500 — иначе backend капает на 50 (обрезанные KPI).
    const [cResp, ratResp, projResp, taskResp] = await Promise.allSettled([
      companiesApi.getOne(code.value),
      ratingsApi.getCompanyRatings(code.value),
      projectsApi.list({ company_code: code.value, limit: 500 }),
      tasksApi.list({ company_code: code.value, limit: 500 } as any),
    ]);

    if (cResp.status === "fulfilled") {
      company.value = cResp.value;
      sector.value = (cResp.value as any).sector || null;
      // Заход в карточку компании → гасим её красный счётчик в сайдбаре.
      const cid = (cResp.value as any)?.id;
      if (cid) notifStore.markCompanyRead(String(cid));
    } else {
      throw cResp.reason;  // загрузка компании критична
    }
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
    adjustYearToData();
  } catch (e: any) {
    error.value = e?.response?.status === 404
      ? t("Компания «{code}» не найдена", { code: code.value })
      : (e?.response?.data?.detail || e?.message || t("Не удалось загрузить компанию"));
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
  else if (t === "unitcost") loadUnitCost();
  else if (t === "credit") loadCredit();
  else if (t === "procurement") loadProc();
  else if (t === "ifrs" || t === "nsbu") loadFinReports();
}

// #3 perf: после overview прогреваем в ФОНЕ самые частые вкладки (KPI/BP),
// чтобы клик по ним был мгновенным. Загрузчики идемпотентны (dedup-ключи),
// поэтому активную вкладку повторно не дёргаем. Fire-and-forget, с idle-
// задержкой, чтобы не конкурировать с рендером overview.
function prefetchCommonTabs() {
  if (activeTab.value !== "kpi") loadKpi();
  if (activeTab.value !== "bp") loadBp();
}

onMounted(() => {
  loadAll().then(() => {
    nextTick(() => animateCounters());
    loadTopFinSnapshot();
    loadActiveTab();
    window.setTimeout(prefetchCommonTabs, 600);
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
  ucLoadedFor.value = "";
  loadAll().then(() => {
    nextTick(() => animateCounters());
    loadTopFinSnapshot();
    loadActiveTab();
    window.setTimeout(prefetchCommonTabs, 600);
  });
});
watch(year, () => {
  nextTick(() => animateCounters());
  loadTopFinSnapshot();
});

// =====================================================================
// Counter animation helper (replaces legacy _countUpScan)
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
// Computed: derived stats (mirrors legacy renderCompanyOverview logic)
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

// Предикат года ЕДИНЫЙ с виджетами Overview-Extras (CompanyOverviewExtras.vue:
// py == null || py === year): строки без portfolio_year (legacy/orphan, напр. у
// новых компаний) считаются в обоих местах, иначе hero-пончик и «По направлениям»
// показывали бы разные итоги на одном экране.
const projItems = computed(() =>
  allProjects.value.filter(p => {
    const py = (p as any).portfolio_year;
    return py == null || py === year.value;
  })
);
const taskItems = computed(() =>
  allTasks.value.filter(t => {
    const py = (t as any).portfolio_year;
    return (py == null || py === year.value) && !t.is_project;
  })
);

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

// Order + palette 1:1 с легасиом const COLS (index.html:6743)
const KANBAN_STATUSES: { id: string; label: string; color: string; bgAccent: string }[] = [
  { id: "init",   label: i18nKey("Инициирование"),  color: "#64748B", bgAccent: "#E2E8F0" },
  { id: "new",    label: i18nKey("Не начато"),      color: "#94A3B8", bgAccent: "#F1F5F9" },
  { id: "active", label: i18nKey("В процессе"),     color: "#3B82F6", bgAccent: "rgba(55,138,221,.10)" },
  { id: "review", label: i18nKey("На согласовании"), color: "#F59E0B", bgAccent: "#FEF9C3" },
  { id: "done",   label: i18nKey("Завершено"),      color: "#10B981", bgAccent: "#D1FAE5" },
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

// Direction meta (1:1 from legacy DIRS const)
const _DIRS_META: Record<string, { label: string; color: string }> = {
  strategy:    { label: i18nKey("Стратегическое управление"),  color: "#6B7FD7" },
  finance:     { label: i18nKey("Финансы / риски / аудит"),    color: "#E0A458" },
  procurement: { label: i18nKey("Система закупок"),            color: "#7BA05B" },
  orgdev:      { label: i18nKey("Организационное развитие"),   color: "#A78BC7" },
  digital:     { label: i18nKey("Цифровизация"),               color: "#5FB3C4" },
  operations:  { label: i18nKey("Операционная эффективность"), color: "#E08A7B" },
  governance:  { label: i18nKey("Корпоративное управление"),   color: "#C77B96" },
  esg:         { label: "ESG",                        color: "#5FA98A" },
  pr:          { label: i18nKey("Связи с общественностью"),    color: "#D89BB5" },
  pmo:         { label: "PMO",                        color: "#7B9BD1" },
  analytics:   { label: i18nKey("Сводный отдел"),              color: "#9B8EC4" },
};
// =====================================================================
// List view helpers
// =====================================================================

function getStatusColor(s: string): string {
  const found = KANBAN_STATUSES.find(x => x.id === s);
  if (found) return found.color;
  return "#7E22CE"; // recurring
}

function fmtDate(d: string | null | undefined): string {
  return fmt.fmtDate(d);
}

function isOverdueTask(t: any): boolean {
  return t.status !== "done" && isOverdue(t.due_date) && !isExcludedStatus(t.status);
}


// =====================================================================
// Kanban drag-and-drop (2026-05-26)
//
// Standard 5 columns (init/new/active/review/done) accept drop and let
// cards be dragged in/out. Recurring (q/m/o) tasks can be dragged OUT
// to a standard column (status conversion); dropping INTO the recurring
// column is a no-op (sub-status can't be inferred from a drop target).
// Overdue column is a filtered view — dropping INTO it makes no sense.
// =====================================================================
const draggingTask = ref<TaskBrief | null>(null);
const dragOverCol = ref<string | null>(null);
const dragSaving = ref(false);

function onTaskDragStart(t: TaskBrief, _ev: DragEvent) {
  draggingTask.value = t;
}

function onColDragOver(status: string, ev: DragEvent) {
  // Only allow drop onto standard 5 columns
  const validTarget = KANBAN_STATUSES.some(s => s.id === status);
  if (!validTarget) return;
  ev.preventDefault();
  if (ev.dataTransfer) ev.dataTransfer.dropEffect = "move";
  dragOverCol.value = status;
}

function onColDragLeave() {
  dragOverCol.value = null;
}

async function onColDrop(targetStatus: string, ev: DragEvent) {
  ev.preventDefault();
  dragOverCol.value = null;
  // Не называть переменную `t` — затеняет функцию перевода t().
  const task = draggingTask.value;
  draggingTask.value = null;
  if (!task || task.status === targetStatus) return;

  // Only standard columns accept drops
  const validTarget = KANBAN_STATUSES.some(s => s.id === targetStatus);
  if (!validTarget) return;

  const oldStatus = task.status;
  // Optimistic update on local state — find the task in allTasks and mutate
  const idx = allTasks.value.findIndex((x: any) => x.id === task.id);
  if (idx >= 0) {
    (allTasks.value[idx] as any).status = targetStatus;
  }

  dragSaving.value = true;
  try {
    await tasksApi.update(task.id, { status: targetStatus as any });
  } catch (e: any) {
    // Rollback
    if (idx >= 0) {
      (allTasks.value[idx] as any).status = oldStatus;
    }
    console.warn("[kanban] drag-drop status update failed:", e);
    error.value = t("Не удалось переместить задачу: {err}", { err: e?.response?.data?.detail || e?.message || t("ошибка") });
  } finally {
    dragSaving.value = false;
  }
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
        // Аудит P1: у связанных (bp_metric_key) строк факт живёт в resolved-полях
        // из БП/НСБУ — иначе компания с полностью связанными KPI ложно уходила
        // в прошлогодний fallback.
        const f = ind.bp_metric_key && ind.bp_fact_resolved != null ? ind.bp_fact_resolved : ind.fact_year;
        const p = ind.bp_metric_key && ind.bp_plan_resolved != null ? ind.bp_plan_resolved : ind.plan_year;
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
    kpiError.value = e?.response?.data?.detail || e?.message || t("Не удалось загрузить KPI");
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
    bpError.value = e?.response?.data?.detail || e?.message || t("Не удалось загрузить Бизнес-план");
    bpData.value = null;
  } finally {
    bpLoading.value = false;
  }
}

const govPerm = usePermissions("governance");
const govEditorOpen = ref(false);
const govShownYear = ref<number>(0);  // фактически показанный год (year-fallback)

async function loadGovernance() {
  if (!company.value) return;
  const key = `${company.value.id}:${year.value}`;
  if (govLoadedFor.value === key) return;
  govLoading.value = true;
  govError.value = null;
  govShownYear.value = year.value;
  try {
    let [detail, members] = await Promise.all([
      governanceApi.getCompanyDetail(company.value.id, year.value).catch(() => null),
      governanceApi.listMembers(company.value.id, false).catch(() => []),
    ]);
    // Year-fallback: за выбранный FY данных нет, но есть за другие годы →
    // подгружаем последний доступный (≤ FY, иначе самый свежий).
    if (detail && !(detail as any).data && Array.isArray((detail as any).available_years) && (detail as any).available_years.length) {
      const ys = [...(detail as any).available_years].sort((a: number, b: number) => b - a);
      const target = ys.find((y: number) => y <= year.value) ?? ys[0];
      if (target && target !== year.value) {
        const alt = await governanceApi.getCompanyDetail(company.value.id, target).catch(() => null);
        if (alt && (alt as any).data) { detail = alt; govShownYear.value = target; }
      }
    }
    govDetail.value = detail;
    govMembers.value = Array.isArray(members) ? members : [];
    govLoadedFor.value = key;
  } catch (e: any) {
    govError.value = e?.response?.data?.detail || e?.message || t("Не удалось загрузить Корп. управление");
  } finally {
    govLoading.value = false;
  }
}

function openGovEditor(): void { govEditorOpen.value = true; }
// Рефетч данных таба после каждого сейва (редактор остаётся открыт для
// продолжения правок; закрытие — по кнопке × / Отмена через @close).
async function onGovEditorSaved(): Promise<void> {
  govLoadedFor.value = "";
  await loadGovernance();
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
  esgShownYear.value = year.value;
  try {
    const sectorCode = (sector.value as any)?.code || null;
    const [detail0, issues, overview] = await Promise.all([
      esgApi.getCompanyDetail(company.value.id, year.value).catch(() => null),
      esgApi.listIssues({ company_id: company.value.id }).catch(() => []),
      sectorCode
        ? esgApi.getOverview({ year: year.value, sector_code: sectorCode }).catch(() => null)
        : Promise.resolve(null),
    ]);
    // Year-fallback: за выбранный FY метрик нет → последний доступный год.
    let detail = detail0;
    const _mc = (d: any) => (d?.metrics_e?.length || 0) + (d?.metrics_s?.length || 0) + (d?.metrics_g?.length || 0);
    if (detail && _mc(detail) === 0 && Array.isArray((detail as any).available_years) && (detail as any).available_years.length) {
      const ys = [...(detail as any).available_years].sort((a: number, b: number) => b - a);
      const target = ys.find((y: number) => y <= year.value) ?? ys[0];
      if (target && target !== year.value) {
        const alt = await esgApi.getCompanyDetail(company.value.id, target).catch(() => null);
        if (alt && _mc(alt) > 0) { detail = alt; esgShownYear.value = target; }
      }
    }
    esgDetail.value = detail;
    esgIssues.value = Array.isArray(issues) ? issues : (issues as any)?.items || [];

    // Sector pillar benchmarks
    if (overview && overview.pillars) {
      const map: Record<string, { avgAttainment: number | null; companyCount: number }> = {};
      overview.pillars.forEach((p: any) => {
        map[p.pillar] = {
          avgAttainment: p.avg_target_attainment != null ? Math.round(p.avg_target_attainment) : null,
          companyCount: p.company_count || 0,
        };
      });
      esgSectorPillars.value = map;
      esgSectorLabel.value = localizedSectorName.value || t("сектору");
    }

    esgLoadedFor.value = key;
  } catch (e: any) {
    esgError.value = e?.response?.data?.detail || e?.message || t("Не удалось загрузить ESG");
  } finally {
    esgLoading.value = false;
  }
}

const esgPerm = usePermissions("esg");
const esgEditorOpen = ref(false);
const esgShownYear = ref<number>(0);
// Подвкладки ESG (как в /esg): зрелость · SWOT.
const esgSubTab = ref<"maturity" | "swot">("maturity");
const ESG_SUBTABS = computed(() => [
  { value: "maturity", label: t("Зрелость") },
  { value: "swot", label: "SWOT" },
]);
function openEsgEditor(): void { esgEditorOpen.value = true; }
async function onEsgEditorSaved(): Promise<void> {
  esgLoadedFor.value = "";
  await loadEsg();          // рефетч (синк с /esg — общий бэкенд)
}
// Панель ESG (общая с /esg) сама перезагрузилась после правки — здесь освежаем
// воркспейс-состояние ESG (используется в hero/бейджах), синк с общим бэкендом.
async function onEsgPanelChanged(): Promise<void> {
  esgLoadedFor.value = "";
  await loadEsg();
}

// =====================================================================
// Удельная себестоимость — срез компании из /unit-cost (общий бэкенд →
// синхронно: правки видны и в дашборде, и здесь). overview даёт весь
// портфель за год/квартал, берём свою компанию по коду.
// =====================================================================
const ucRaw = ref<UCOverview | null>(null);
const ucLoading = ref(false);
const ucError = ref<string | null>(null);
const ucLoadedFor = ref<string>("");        // "code:year:quarter"
const ucQuarter = ref<string>("annual");
const UC_QUARTERS = computed(() => [
  { value: "annual", label: t("Год") },
  { value: "q1", label: t("I кв") },
  { value: "q2", label: t("II кв") },
  { value: "q3", label: t("III кв") },
  { value: "q4", label: t("IV кв") },
]);
async function loadUnitCost(): Promise<void> {
  if (!company.value) return;
  const key = `${code.value}:${year.value}:${ucQuarter.value}`;
  if (ucLoadedFor.value === key) return;
  ucLoading.value = true;
  ucError.value = null;
  try {
    ucRaw.value = await unitCostApi.overview(year.value, ucQuarter.value);
    ucLoadedFor.value = key;
  } catch (e: any) {
    ucError.value = e?.response?.data?.detail || e?.message || t("Не удалось загрузить себестоимость");
  } finally {
    ucLoading.value = false;
  }
}
const ucCompany = computed<UCCompany | null>(() => {
  const list = ucRaw.value?.companies || [];
  const c = code.value;
  return list.find((x) => String(x.code || "").toLowerCase() === c) || null;
});
const ucPrices = computed(() => ucRaw.value?.energyPrices || {});
const ucWorld = computed(() => ucRaw.value?.world || null);
const ucFuelLabels = computed(() => ucRaw.value?.fuel_labels || {});
async function onUnitCostSaved(): Promise<void> {
  ucLoadedFor.value = "";
  await loadUnitCost();       // рефетч (синк с /unit-cost — общий бэкенд)
}
watch(ucQuarter, () => { if (activeTab.value === "unitcost") loadUnitCost(); });

// ── Финансы (ifrs/nsbu): встроенный разбор компании как в /financials ──
// CompanyDrilldown ищет компанию в массиве по коду и берёт сектор из sectors;
// отдаём срез из одной компании воркспейса (код форсим к каноничному lower).
const finDrillCompanies = computed(() => {
  if (!company.value) return [];
  const s: any = sector.value;
  return [{
    ...company.value,
    code: code.value,
    // подстраховка сектора (акцент/лейбл в drill), если getOne их не отдал
    sector_code: company.value.sector_code ?? s?.code,
    sector_color: company.value.sector_color ?? s?.color_hex,
    sector_name: company.value.sector_name ?? sectorDisplayName(s),
  }];
});
const finDrillSectors = computed(() => (sector.value ? [sector.value] : []));

async function loadConsultantsPerCompany() {
  if (!company.value) return;
  const key = `${company.value.id}:${year.value}`;
  if (consPerCompanyLoadedFor.value === key) return;
  consPerCompanyLoading.value = true;
  consPerCompanyError.value = null;
  try {
    consPerCompany.value = await consultantsApi.byCompany(company.value.id, year.value);
    consPerCompanyLoadedFor.value = key;
    nextTick(() => animateCounters());   // count-up KPI-бэнда после загрузки данных
  } catch (e: any) {
    consPerCompanyError.value = e?.response?.data?.detail || e?.message || t("Не удалось загрузить консультантов компании");
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
    consDirectoryError.value = e?.response?.data?.detail || e?.message || t("Не удалось загрузить справочник");
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

// Inline-правка задачи/проекта в list-табе (CompanyBoardList @changed):
// её данные кэшируются отдельно от обзора и consultants-таба, поэтому при
// изменении (статус/направление/консультант/дедлайн) синхронизируем:
//  • инвалидируем кэш консультантов компании (агрегат на бэке учитывает
//    task.consultant) → переключение на таб «Консультанты» даст свежие данные
//  • перезагружаем allProjects/allTasks → обзор-донат, «По направлениям» и
//    статы консультантов на overview пересчитываются
async function onBoardListChanged() {
  consPerCompanyLoadedFor.value = "";
  if (!company.value) return;
  try {
    const [p, t] = await Promise.all([
      projectsApi.list({ company_id: company.value.id, limit: 500 }),
      tasksApi.list({ company_id: company.value.id, limit: 500 } as any),
    ]);
    allProjects.value = (p as any).items || [];
    allTasks.value = (t as any).items || [];
  } catch {
    /* при сетевой ошибке оставляем текущее — list-таб уже оптимистично обновлён */
  }
  if (activeTab.value === "consultants") loadConsultantsPerCompany();
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
    creditError.value = e?.response?.data?.detail || e?.message || t("Не удалось загрузить кредитный портфель");
    creditLoans.value = [];
    creditAggregate.value = null;
  } finally {
    creditLoading.value = false;
  }
}

// ─── Форензик-аудит компании (из /forensic/overview) ────────────────
// Procurement-таб дополняем форензик-инфо по компании: статус аудита, статус
// плана закупок, аудитор, годы аудита, план/факт за выбранный год.
const procForensic = ref<any>(null);

interface FBadge { text: string; bg: string; fg: string }
function fPlanBadge(plan: string | undefined | null): FBadge {
  if (!plan) return { text: "—", bg: "var(--bg3, #F1F5F9)", fg: "var(--t3, #64748B)" };
  if (plan === "Утверждён") return { text: t("Утверждён"), bg: "rgba(29,158,117,.12)", fg: "#1D9E75" }; // i18n-exempt: canonical API value
  return { text: t("Не утверждён"), bg: "rgba(226,75,74,.08)", fg: "#993D3D" };
}
function fForensicBadge(f: string | undefined | null): FBadge {
  if (!f) return { text: "—", bg: "var(--bg3, #F1F5F9)", fg: "var(--t3, #64748B)" };
  if (f === "Завершён") return { text: t("Завершён"), bg: "rgba(29,158,117,.12)", fg: "#1D9E75" }; // i18n-exempt: canonical API value
  if (f === "В процессе") return { text: t("В процессе"), bg: "rgba(55,138,221,.10)", fg: "#378ADD" }; // i18n-exempt: canonical API value
  if (f.indexOf("Тендер") >= 0) return { text: t(f), bg: "rgba(239,159,39,.10)", fg: "#D97706" }; // i18n-exempt: canonical API value
  return { text: t(f), bg: "rgba(226,75,74,.08)", fg: "#993D3D" };
}
// Цвет и признак Big 4 берём из справочника консультантов — того же, что
// рисует /consultants. Локальная палитра давала KPMG #378ADD, форензик —
// #0033A0, бейдж — #0091DA: одна компания трёх цветов на трёх экранах.
const _consultantList = ref<ConsultantBrief[]>([]);
onMounted(() => { void ensureConsultants().then((rows) => { _consultantList.value = rows; }); });
function fAud(a: string | undefined | null) {
  return auditorStyle(a, _consultantList.value);
}
function fAuditorColor(a: string | undefined | null): string {
  return fAud(a).color;
}
// План/факт закупок за выбранный год из years[] (млрд, как в forensic-вью)
const procForensicYear = computed(() => {
  const c = procForensic.value;
  if (!c || !Array.isArray(c.years)) return null;
  const row = c.years.find((y: any) => Number(y.y) === Number(year.value));
  if (!row) return null;
  const plan = row.plan != null ? Number(row.plan) : null;
  const fact = row.fact != null ? Number(row.fact) : null;
  const pct = plan && plan > 0 && fact != null ? Math.round((fact / plan) * 100) : null;
  return { plan, fact, pct };
});

async function loadProc() {
  if (!company.value) return;
  const key = `${company.value.id}:${year.value}`;
  if (procLoadedFor.value === key) return;
  procLoading.value = true;
  procError.value = null;
  try {
    const [agg, forensic] = await Promise.all([
      procurementAnalysisApi.getAggregate({
        company_id: company.value.id,
        year: year.value,
      }),
      api.get<{ companies: any[] }>("/forensic/overview").then(r => r.data).catch(() => null),
    ]);
    procData.value = agg;
    const cc = code.value;
    procForensic.value = forensic
      ? (forensic.companies || []).find((c: any) => String(c.k || "").toLowerCase() === cc) || null
      : null;
    procLoadedFor.value = key;
  } catch (e: any) {
    procError.value = e?.response?.data?.detail || e?.message || t("Не удалось загрузить закупки");
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

// Единый выбор «года с данными»: предпочитаем непустые отчёты (lines_count>0),
// год ≤ выбранного, иначе самый свежий. Дедуп между loadFinReports/loadTopFinSnapshot.
function pickReportYear(
  reports: { year: number; lines_count?: number }[],
  target: number,
): number | null {
  if (!reports.length) return null;
  const withData = Array.from(new Set(reports.filter(r => (r.lines_count || 0) > 0).map(r => r.year)));
  const years = (withData.length
    ? withData
    : Array.from(new Set(reports.map(r => r.year)))).sort((a, b) => b - a);
  if (!years.length) return null;
  return years.includes(target) ? target : (years.find(y => y <= target) ?? years[0]);
}

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
  finShownYear.value = year.value;
  try {
    // Тянем ВСЕ годы по компании+стандарту, затем выбираем целевой год:
    // выбранный FY если по нему есть данные, иначе — последний доступный ≤ FY,
    // иначе самый свежий вообще. Покрытие отчётности разрежено (полное только
    // до 2024; 2025-2026 у части компаний нет) → без fallback вкладка пуста.
    const all = await financialsApi.list({ company_code: cCode, standard: std });
    const allArr = all || [];
    // Год с данными — единый хелпер pickReportYear (предпочитает непустые отчёты,
    // иначе fallback к последнему ≤ FY). Пустые NSBU-2026 заглушки игнорируются.
    const targetYear = pickReportYear(allArr, year.value) ?? year.value;
    finShownYear.value = targetYear;
    // Для выбранного года берём только непустые отчёты, если они есть.
    const yearRows = allArr.filter(r => r.year === targetYear);
    const nonEmpty = yearRows.filter(r => (r.lines_count || 0) > 0);
    // Единственный источник — канонический срез редактора. На один год+тип
    // могут существовать ДВА отчёта: канон редактора и детальный импорт из
    // Excel; раньше побеждал произвольный (порядок ответа), и вкладка могла
    // показать данные старого файла. Детальный берём только если канона нет.
    const preferCanon = (rows: FinancialReportListItem[]) => {
      const canon = rows.filter(r => r.is_detailed !== true);
      return canon.length ? canon : rows;
    };
    const list = preferCanon(nonEmpty.length ? nonEmpty : yearRows);
    finReports.value = list;
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

      // Auto-select user's preferred report — предпочитаем непустой отчёт.
      const preferred =
        list.find(r => r.report_type === finReportType.value && (r.lines_count || 0) > 0)
        || list.find(r => (r.lines_count || 0) > 0)
        || list.find(r => r.report_type === finReportType.value)
        || list[0];
      finReportType.value = preferred.report_type as any;
      // Reuse eager-fetched copy if available, otherwise hit API
      if (byType[preferred.report_type]) {
        finFullReport.value = byType[preferred.report_type];
      } else {
        await loadFinFullReport(preferred.id);
      }
    }
  } catch (e: any) {
    finError.value = e?.response?.data?.detail || e?.message || t("Не удалось загрузить отчётность");
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
    finError.value = e?.response?.data?.detail || e?.message || t("Не удалось загрузить отчёт");
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
  // (legacy store migration set unit_scale=1000 by mistake on legacy rows). The
  // standalone /financials view uses the same convention.

  // PL — revenue / EBITDA / NetProfit
  const rev    = _lineValue(pl, ["revenue", "выручка", "net_revenue"]); // i18n-exempt: imported row alias
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
      label: t("Выручка"),
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
      label: t("Чистая прибыль"),
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
      hint: t("доходность капитала"),
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
      hint: t("доходность активов"),
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
      hint: t("леверидж"),
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
      hint: t("доля собственного капитала"),
    });
  }

  return out;
});

// Display values as-is, in млрд UZS (the canonical unit used by the standalone
// /financials view per "Единицы: млрд сум"). Stored values for NGMK etc.
// already encode billions — the legacy store migration set unit_scale=1000 by
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
// Auto-load when relevant tab is opened
watch(activeTab, (tab) => {
  if (tab === "kpi") loadKpi();
  if (tab === "bp") loadBp();
  if (tab === "governance") loadGovernance();
  if (tab === "esg") loadEsg();
  if (tab === "consultants") loadConsultantsPerCompany();
  if (tab === "unitcost") loadUnitCost();
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
  ucLoadedFor.value = "";
  loadActiveTab();
});

// Reload BP when period changes
watch(bpPeriod, () => {
  if (activeTab.value === "bp") loadBp();
});

// =====================================================================
// KPI computed values (mirror legacy logic)
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
      // Аудит P1: связанный (bp_metric_key) индикатор зеркалит план/факт из
      // БП/НСБУ — resolved приоритетнее статической копии (иначе связанные
      // строки показывали пусто/0, а сводка /kpi считала верно).
      const linked = !!(ind as any).bp_metric_key;
      const plan = (linked && (ind as any).bp_plan_resolved != null)
        ? maybeNum((ind as any).bp_plan_resolved) : maybeNum(ind.plan_year);
      const fact = (linked && (ind as any).bp_fact_resolved != null)
        ? maybeNum((ind as any).bp_fact_resolved) : maybeNum(ind.fact_year);
      // P0 аудита: единый direction-aware расчёт (utils/kpiRatio) вместо инлайна
      // Math.min(2, fact/plan) — иначе для 'down'-KPI перерасход рисовался как
      // достижение >100%, расходясь с модулем /kpi. Пол/потолок — во взвешенной
      // сводке (kpiWeightedRatio: пол 0, потолок 150%, как co_pct на бэке).
      const ratio = kpiCompletionRatio(plan, fact, ind.direction);
      const indHasFact = ratio !== null;
      if (indHasFact) {
        weightedSum += kpiWeightedRatio(ratio) * w;
        totalWeight += w;
        hasFact = true;
      } else if (plan !== null) {
        totalWeight += w;
      }
      const isAttention = indHasFact && ratio < 0.90 && w >= 15;
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

function pctColor(pct: number | null): string {
  if (pct === null) return "#94A3B8";
  if (pct >= 70) return "#1D9E75";
  if (pct >= 35) return "#D97706";
  return "#E24B4A";
}

// =====================================================================
// Business Plan computed views (mirror legacy _bpFmt + group rendering)
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
  /** Расходная строка: >100% плана — перерасход, а не перевыполнение */
  expense: boolean;
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
    // plan > 0: при отрицательном плане отношение факт/план меняет знак и даёт
    // бессмысленный процент (убыток «выполнен на −187%»).
    if (plan !== null && plan > 0 && fact !== null) {
      pct = Math.round((fact / plan) * 100);
    }
    return {
      key: meta.key,
      label: meta.label,
      group: meta.group,
      auto: meta.auto,
      sub: !!meta.sub,
      // Расходная строка: превышение плана — это плохо, а не «перевыполнение».
      // Модуль БП признак уважает (BpEditor.deltaClass), карточка компании —
      // нет, и себестоимость 130% плана горела зелёным.
      expense: !!meta.positive,
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
    { id: "opRevenue",   label: t("Выручка и себестоимость") },
    { id: "opExpenses",  label: t("Расходы периода") },
    { id: "opResult",    label: t("Операционный результат") },
    { id: "finActivity", label: t("Финансовая деятельность") },
    { id: "final",       label: t("Итог") },
  ];
  return groups.map(g => ({
    ...g,
    items: bpFieldViews.value.filter(f => f.group === g.id),
  }));
});

function bpFmt(v: number | null | undefined): string {
  // Per user 2026-05-23: BP-значения в БД хранятся в МЛРД UZS (раньше
  // комментарий говорил «млн» — это было неверно). Чтобы fmtMoneyCompact
  // выбрал правильный суффикс (трлн для крупных SOE-цифр), скейлим
  // значение к raw UZS = v × 10^9.
  if (v === null || v === undefined) return "—";
  return fmt.fmtMoneyCompact(v * 1_000_000_000, "UZS", { decimals: 1 });
}

function bpPctColor(pct: number | null, expense = false): string {
  if (pct === null) return "#94A3B8";
  if (expense) {
    // Для расходов «хорошо» — уложиться в план: 100% и ниже зелёное,
    // перерасход — предупреждение, значительный перерасход — критично.
    if (pct <= 100) return "#1D9E75";
    if (pct <= 110) return "#D97706";
    return "#E24B4A";
  }
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
  // «Заседания»/«решения» берём из таблицы committee_meetings (единый источник,
  // как в /governance), а не из ручного meetings_per_year; fallback к legacy,
  // если по заседаниям за год данных нет.
  const meetings = (d.sb_meetings_year ?? data.meetings_per_year) ?? null;
  const decisions = d.sb_decisions_year ?? null;

  const indepPct = boardSize && indep !== null ? Math.round((indep / boardSize) * 100) : null;
  const womenPct = boardSize && women !== null ? Math.round((women / boardSize) * 100) : null;
  const foreignPct = boardSize && foreign !== null ? Math.round((foreign / boardSize) * 100) : null;

  return [
    { label: t("Размер совета"), value: boardSize ?? "—", raw: boardSize, unit: t("чел."), color: "#7F77DD" },
    { label: t("Независимые"), value: indepPct === null ? "—" : `${indepPct}%`, raw: indepPct, unit: indep !== null ? `(${indep} ${t("чел.")})` : "", color: "#1D9E75" },
    { label: t("Женщины"), value: womenPct === null ? "—" : `${womenPct}%`, raw: womenPct, unit: women !== null ? `(${women} ${t("чел.")})` : "", color: "#EF9F27" },
    { label: t("Иностранцы"), value: foreignPct === null ? "—" : `${foreignPct}%`, raw: foreignPct, unit: foreign !== null ? `(${foreign} ${t("чел.")})` : "", color: "#378ADD" },
    { label: t("Посещаемость"), value: attendance !== null ? `${attendance}%` : "—", raw: attendance, unit: "", color: "#1D9E75" },
    { label: t("Заседаний НС"), value: meetings ?? "—", raw: meetings, unit: t("за год"), color: "#7F77DD" },
    { label: t("Решения (протоколы)"), value: decisions ?? "—", raw: decisions, unit: t("за год"), color: "#A855F7" },
  ];
});

const govCommittees = computed(() => {
  const d = govDetail.value;
  if (!d) return [];
  const data = d.data || d.governance_data || d;
  // Комитет активен, если формально есть (флаг) ИЛИ реально заседал (meetings>0)
  // — честнее «флаг≠работа». Показываем и число заседаний за год.
  const mk = (label: string, flag: boolean, meetings: number | null) => ({
    label, meetings,
    present: flag || (meetings != null && meetings > 0),
  });
  return [
    mk(t("Аудит"), !!data.has_audit_committee, d.audit_mtg_year ?? null),
    mk(t("Стратегия"), !!data.has_strategy_committee, d.strategy_mtg_year ?? null),
    mk(t("Назначения и вознагр."), !!(data.has_nomination_committee || data.has_remuneration_committee), d.nomrem_mtg_year ?? null),
    mk(t("Антикор."), !!data.has_anticorr_committee, d.anticorr_mtg_year ?? null),
    mk(t("Введение"), !!data.has_induction_program, null),
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
  appointedISO: string | null;
  termEndISO: string | null;
  email: string | null;
  phone: string | null;
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
  const ROLE_ORDER: RoleType[] = ["chairman", "independent", "state_rep"];
  
  return govMembers.value
    .map((m: any) => {
      const role = m.role_type as RoleType | null;
      const meta = ROLE_TYPE_META.find(r => r.key === role);
      return {
        id: m.id,
        fullName: m.full_name || "—",
        position: m.position || "",
        roleType: role,
        roleLabel: meta?.label ? t(meta.label) : t("Член совета"),
        roleColor: meta?.color || "#94A3B8",
        // Эффективная независимость: флаг ЛИБО роль «independent» (иначе цифры
        // расходятся с KPI-карточкой «Независимые»). Единый источник для полоски,
        // бейджа и модалки.
        isIndependent: !!m.is_independent || role === "independent",
        isWoman: !!m.is_woman,
        isForeign: !!m.is_foreign,
        appointed: m.appointed_date ? fmtDate(m.appointed_date) : "—",
        termEnd: m.term_end_date ? fmtDate(m.term_end_date) : "—",
        appointedISO: m.appointed_date || null,
        termEndISO: m.term_end_date || null,
        email: m.email || null,
        phone: m.phone || null,
        initials: getInitials(m.full_name || ""),
      } as BoardMemberView;
    })
    .sort((a, b) => {
      const ai = ROLE_ORDER.indexOf(a.roleType as any);
      const bi = ROLE_ORDER.indexOf(b.roleType as any);
      if (ai !== bi) return (ai === -1 ? 99 : ai) - (bi === -1 ? 99 : bi);
      return a.fullName.localeCompare(b.fullName, getCurrentIntlLocale());
    });
});

// Аналитика состава совета — доли + средний срок в совете (для полосок под KPI).
// Считаем от фактического числа членов (нет данных ≠ 0% — при пустом совете
// блок не показываем через v-if на длину boardMembersByRole).
const boardComposition = computed(() => {
  const members = boardMembersByRole.value;
  const n = members.length;
  if (n === 0) return null;
  const pct = (cnt: number) => Math.round((cnt / n) * 100);
  const indep = members.filter(m => m.isIndependent).length;  // isIndependent уже эффективная
  const women = members.filter(m => m.isWoman).length;
  const foreign = members.filter(m => m.isForeign).length;
  // Средний срок в совете (лет) по тем, у кого есть дата назначения.
  const now = Date.now();
  const tenures: number[] = [];
  for (const m of members) {
    if (!m.appointedISO) continue;
    const t = new Date(m.appointedISO).getTime();
    if (!isFinite(t)) continue;
    const yrs = (now - t) / (365.25 * 24 * 3600 * 1000);
    if (yrs >= 0) tenures.push(yrs);
  }
  const avgTenure = tenures.length ? tenures.reduce((a, b) => a + b, 0) / tenures.length : null;
  return {
    bars: [
      { label: t("Независимость"), pct: pct(indep), count: indep, color: "#1D9E75" },
      { label: t("Женщины"), pct: pct(women), count: women, color: "#A855F7" },
      { label: t("Иностранцы"), pct: pct(foreign), count: foreign, color: "#0E7490" },
    ],
    avgTenure,
    total: n,
  };
});

// Всплывающий профиль члена совета (новая модалка BoardMemberProfileModal).
const boardMemberModalOpen = ref(false);
const selectedBoardMember = ref<BoardMemberView | null>(null);
function openBoardMember(m: BoardMemberView) {
  selectedBoardMember.value = m;
  boardMemberModalOpen.value = true;
  bmHoverOpen.value = false;  // клик закрывает hover-карточку
}

// Быстрая hover-карточка члена совета (аналог UserCardHost у сотрудников).
const bmHoverOpen = ref(false);
const bmHoverMember = ref<BoardMemberView | null>(null);
const bmHoverAnchor = ref<HoverAnchor | null>(null);
let _bmOpenTimer: number | undefined;
let _bmCloseTimer: number | undefined;
let _bmOverCard = false;
function bmHoverEnter(m: BoardMemberView, el: HTMLElement) {
  window.clearTimeout(_bmCloseTimer);
  window.clearTimeout(_bmOpenTimer);
  const r = el.getBoundingClientRect();
  _bmOpenTimer = window.setTimeout(() => {
    bmHoverMember.value = m;
    bmHoverAnchor.value = { top: r.top, left: r.left, bottom: r.bottom, right: r.right, width: r.width, height: r.height };
    bmHoverOpen.value = true;
  }, 200);
}
function bmHoverLeave() {
  window.clearTimeout(_bmOpenTimer);
  window.clearTimeout(_bmCloseTimer);
  _bmCloseTimer = window.setTimeout(() => {
    if (!_bmOverCard) bmHoverOpen.value = false;
  }, 180);
}
function bmCardEnter() { _bmOverCard = true; window.clearTimeout(_bmCloseTimer); }
function bmCardLeave() { _bmOverCard = false; bmHoverLeave(); }

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
  const metrics: any[] = [
    ...((detail as any)?.metrics_e || []),
    ...((detail as any)?.metrics_s || []),
    ...((detail as any)?.metrics_g || []),
  ] as any[];
  
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
  const metrics: any[] = [
    ...((detail as any)?.metrics_e || []),
    ...((detail as any)?.metrics_s || []),
    ...((detail as any)?.metrics_g || []),
  ] as any[];
  
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
      title: i.title || i.metric_name || t("Без названия"),
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
  // «Выполнение задач» — ВЗВЕШЕННОЕ с бэкенда (weighted_pct по дедуп-объединению
  // консультируемых задач), а не done/total на фронте: иначе цифра расходилась
  // и со своими карточками, и с полностраничным модулем /consultants.
  const completionPct = Math.round(d.completion_pct ?? 0);
  return {
    consultants: d.total_consultants,
    assignments: d.total_assignments,
    big4: big4Count,
    completionPct,
  };
});

// Консультанты компании, сгруппированные Big4 → Другие (список как в /consultants);
// внутри группы — по числу задач ↓ (самые загруженные сверху).
const companyConsBig4 = computed(() =>
  (consPerCompany.value?.consultants || [])
    .filter(c => c.is_big4).sort((a, b) => b.task_count - a.task_count));
const companyConsOther = computed(() =>
  (consPerCompany.value?.consultants || [])
    .filter(c => !c.is_big4).sort((a, b) => b.task_count - a.task_count));
// Раскрытая строка (инлайн-список задач консультанта).
const expandedCons = ref<string | null>(null);
function toggleConsRow(id: string) { expandedCons.value = expandedCons.value === id ? null : id; }

// Directory grouping (for the collapsible secondary section showing all consultants)
const consDirectoryByGroup = computed(() => {
  const all = consDirectory.value.filter(c => c.is_active !== false);
  return {
    big4: all.filter(c => c.is_big4),
    other: all.filter(c => !c.is_big4),
    total: all.length,
  };
});

// Компактный статус-значок → inline SVG (без эмодзи; рендерится через v-html).
function getStatusShortLabel(s: string): string {
  const ic = (inner: string, sw = "2.4"): string =>
    `<svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="${sw}" stroke-linecap="round" stroke-linejoin="round" style="vertical-align:-1px">${inner}</svg>`;
  if (s === "done") return ic('<polyline points="20 6 9 17 4 12"/>');
  if (s === "active") return ic('<line x1="5" y1="12" x2="19" y2="12"/><polyline points="12 5 19 12 12 19"/>');
  if (s === "review") return ic('<polyline points="23 4 23 10 17 10"/><path d="M20.49 15a9 9 0 1 1-2.12-9.36L23 10"/>', "2");
  if (s === "init") return ic('<circle cx="12" cy="12" r="3.5" fill="currentColor" stroke="none"/>');
  if (s === "new") return ic('<circle cx="12" cy="12" r="8"/>');
  return s.slice(0, 1).toUpperCase();
}

function getSourceLabel(src: string): string {
  if (src === "task") return t("из задачи");
  if (src === "manual") return t("вручную");
  if (src === "lookup") return "lookup";
  return src;
}

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
      label: t(meta.label),
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
    overdue: { key: "overdue", label: t("Просрочка"),   color: "#E24B4A", count: 0, debt: 0, pct: 0 },
    lt1y:    { key: "lt1y",    label: t("< 1 года"),    color: "#EF9F27", count: 0, debt: 0, pct: 0 },
    y1_3:    { key: "y1_3",    label: t("1 – 3 лет"),  color: "#378ADD", count: 0, debt: 0, pct: 0 },
    y3_5:    { key: "y3_5",    label: t("3 – 5 лет"),  color: "#7F77DD", count: 0, debt: 0, pct: 0 },
    gt5y:    { key: "gt5y",    label: t("> 5 лет"),     color: "#1D9E75", count: 0, debt: 0, pct: 0 },
    unknown: { key: "unknown", label: t("Срок не указан"), color: "#94A3B8", count: 0, debt: 0, pct: 0 },
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
        lender_label: t(meta.label),
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
    const sup = (p.supplier || t("Не указан")).trim() || t("Не указан");
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
    { type: "BS", label: t("Баланс"), short: "BS", available: byType.has("BS"), reportId: byType.get("BS")?.id || null },
    { type: "PL", label: t("ОПиУ"),   short: "PL", available: byType.has("PL"), reportId: byType.get("PL")?.id || null },
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
// unit_scale is ignored on display (the legacy store migration set it wrongly).
function fmtFinValue(v: number, _scale: number): string {
  return fmtBlnValue(v);
}

// Unit-scale label used in the table header. Per user spec all values are
// shown in billions, so the header always says "млрд".
function getUnitScaleLabel(_scale: number): string {
  return t("млрд");
}

// Friendly source label — sources stored as raw migration tags ("legacy store_sparse_fix",
// "ifrs-editor", …) are confusing to non-engineers. Translate to nicer text.
function fmtSourceLabel(s: string | null | undefined): string {
  const v = String(s || "").toLowerCase();
  if (!v) return "—";
  if (v.startsWith("legacy store")) return t("Платформа (миграция)");
  if (v === "ifrs-editor" || v === "nsbu-editor") return t("Платформа (редактор)");
  if (v === "ifrs" || v === "nsbu") return t("Платформа");
  if (v.startsWith("excel-confirm")) return t("Excel-импорт");
  return s as string;
}

function fmtFinUpdated(s: string): string {
  if (!s) return "";
  return fmt.fmtDate(s);
}

const finStandardLabel = computed(() =>
  financialsStandard.value === "IFRS" ? t("МСФО") : t("НСБУ")
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
      // Perf: ОДИН list-запрос на все годы/стандарты (раньше вложенный цикл
      // 2×3 делал до 6 серийных list-вызовов). Затем выбираем непустой отчёт:
      // предпочитаем IFRS, последний год ≤ выбранного с данными (lines_count>0).
      const all = await financialsApi.list({ company_code: cCode });
      const arr = all || [];
      const pickStd = (std: "IFRS" | "NSBU") => {
        const wd = arr.filter(r => r.standard === std);
        const y = pickReportYear(wd, year.value);
        if (y == null) return null;
        const pl = wd.find(r => r.year === y && r.report_type === "PL" && (r.lines_count || 0) > 0);
        const bs = wd.find(r => r.year === y && r.report_type === "BS" && (r.lines_count || 0) > 0);
        return (pl || bs) ? { y, std, pl, bs } : null;
      };
      const chosen = pickStd("IFRS") || pickStd("NSBU");
      if (!chosen) return;

      const fetched = await Promise.allSettled([
        chosen.pl ? financialsApi.get(chosen.pl.id) : Promise.resolve(null),
        chosen.bs ? financialsApi.get(chosen.bs.id) : Promise.resolve(null),
      ]);
      const plFull = fetched[0].status === "fulfilled" ? fetched[0].value : null;
      const bsFull = fetched[1].status === "fulfilled" ? fetched[1].value : null;

      const rev = _lineValue(plFull || undefined, ["revenue", "выручка"]); // i18n-exempt: imported row alias
      const debt = _lineValue(bsFull || undefined, ["debt", "totalDebt", "total_debt"]);

      topFinSnapshot.value = {
        revenue: rev.v != null ? rev.v * _scaleFactor(plFull || undefined) : null,
        revenueUnit: plFull?.currency || "UZS",
        debt: debt.v != null ? debt.v * _scaleFactor(bsFull || undefined) : null,
        debtUnit: bsFull?.currency || "UZS",
        loadedYear: chosen.y,
        loadedStandard: chosen.std,
      };
    } catch {
      /* snapshot — best-effort, тихо игнорируем */
    } finally {
      topFinSnapshotInflight = null;
    }
  })();
  await topFinSnapshotInflight;
}

// Sprint C · Re-animate after any heavy data set lands.
// Placed AFTER all 4 watched refs are declared so Vue's effect-tracking
// can iterate them without hitting a TDZ "Cannot access X before init".
// Пересчёт анимации после ЛЮБОЙ подгрузки вкладки. Вотчера на activeTab мало:
// он срабатывает до того, как приедут данные (loadProc/loadCredit/… async),
// поэтому сканер не находил ещё не отрисованные числа — вкладка «Закупки»
// показывала готовые цифры без счёта вверх.
watch(
  [finKpis, creditMaturityLadder, procSupplierConcentration, topFinSnapshot,
   procCompanyKpis, creditKpis, govKpis],
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
    .map((tk: any) => ({
      kind: "task",
      id: String(tk.id),
      title: tk.title || tk.name || t("(без названия)"),
      owner: tk.assignee_name || tk.owner_name || tk.responsible || null,
      due_date: tk.due_date,
      daysOverdue: _daysOverdueOf(tk.due_date),
      link: tk.project_id ? `/projects/${tk.project_id}` : null,
    }));
  const projects: OverdueRow[] = projItems.value
    .filter((p: any) => p.status !== "done" && isOverdue(p.due_date) && !isExcludedStatus(p.status))
    .map((p: any) => ({
      kind: "project",
      id: String(p.id),
      title: p.name || p.title || t("(без названия)"),
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
// Клик по строке overdue-модала → открыть редактор задачи/проекта прямо в
// воркспейсе (раньше был RouterLink на несуществующий /projects/{id} → 404).
function openOverdueRow(r: OverdueRow) {
  closeOverdueModal();
  void openTaskEditor({ id: r.id, kind: r.kind });
}

// Provide to child components (CompanyOverviewExtras → attention card click)
provide("openOverdueModal", openOverdueModal);

// Скрытие/показ главного сайдбара (как в CreditPortfolio/ExecDash topbar).
const toggleSidebar = inject<() => void>("toggleSidebar", () => {});
const openMobileSidebar = inject<() => void>("openMobileSidebar", () => {});
function onBurger() {
  if (typeof window !== "undefined" && window.innerWidth <= 1023) openMobileSidebar();
  else toggleSidebar();
}

const projTotal = computed(() => projItems.value.length);
const projDone = computed(() => projItems.value.filter(p => p.status === "done").length);
// ─── CompanyTabBar indicators (year-aware) ─────────────────────────────
// 2026-05-26: раньше CompanyTabBar.vue падал к MOCK_INDICATORS — hardcoded
// числа 24/87/14/7/234 не реагировали на смену года. Теперь пробрасываем
// реальные счётчики из year-filtered taskItems/projItems.
// Company-scoped индикаторы уведомлений на табах (НЕ дублируют глобальную
// логику сайдбара): выводятся из уже загруженных задач/проектов этой компании.
const _wsItems = computed(() => [...projItems.value, ...taskItems.value] as any[]);
const _wsHasUnread = computed(() => _wsItems.value.some(x => x.has_unread_comments));
const _wsSoon = computed(() => _wsItems.value.filter(x => {
  if (x.status === "done" || isExcludedStatus(x.status) || !x.due_date) return false;
  const days = Math.floor((new Date(x.due_date).getTime() - Date.now()) / 86400000);
  return days >= 0 && days <= 3;
}).length);
const _commentAlert = computed(() => _wsHasUnread.value
  ? { alert: "warning" as const, alertTooltip: t("Есть непрочитанные комментарии") } : {});
const _calendarAlert = computed(() =>
  overdue.value ? { alert: "critical" as const, alertTooltip: t("Просрочено дедлайнов: {n}", { n: overdue.value }) }
  : _wsSoon.value ? { alert: "warning" as const, alertTooltip: t("Скоро дедлайн: {n}", { n: _wsSoon.value }) }
  : {});

const tabIndicators = computed(() => ({
  overview:    {},
  // «Работа» (Канбан+Список): счётчик задач за год + точка непрочитанных комментов
  work:        { badge: taskItems.value.length || undefined, ..._commentAlert.value },
  kanban:      { ..._commentAlert.value },
  list:        { badge: taskItems.value.length || undefined, ..._commentAlert.value },
  // Календарь: красная точка при просрочке, амбер при близком дедлайне
  notes:       { ..._calendarAlert.value },
  ifrs:        {},
  nsbu:        {},
  hlf:         {},
  bp:          {},
  // credit скрыт на уровне COMPANY_TABS — индикатор держим для
  // совместимости с typing'ом, но он никогда не отрисуется.
  credit:      {},
  kpi:         {},
  procurement: {},
  governance:  {},
  consultants: {},
  esg:         {},
}));

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

// ─── Status drill: клик по статус-плитке / герою / просрочке → премиум-модалка
//     со списком проектов+задач этого статуса. Данные уже загружены в воркспейсе
//     (projItems/taskItems) — фильтруем локально, без обращения к бэкенду. Клик по
//     строке открывает редактор сущности (openTaskEditor — как в overdue-модалке).
type StatusDrillKey =
  | "new" | "init" | "active" | "review" | "deferred" | "done"
  | "quarterly" | "monthly" | "ongoing" | "overdue";
interface StatusDrillDef { key: StatusDrillKey; label: string; color: string; sub: string }
const STATUS_DRILLS: Record<StatusDrillKey, StatusDrillDef> = {
  new:       { key: "new",       label: i18nKey("Не начато"),       color: "#94A3B8", sub: i18nKey("ожидают старта") },
  init:      { key: "init",      label: i18nKey("Инициирование"),   color: "#7F77DD", sub: i18nKey("в инициации") },
  active:    { key: "active",    label: i18nKey("В процессе"),      color: "#378ADD", sub: i18nKey("в работе") },
  review:    { key: "review",    label: i18nKey("На согласовании"), color: "#EF9F27", sub: i18nKey("на согласовании") },
  deferred:  { key: "deferred",  label: i18nKey("Перенесено"),      color: "#B08CE0", sub: i18nKey("перенесены на др. год") },
  done:      { key: "done",      label: i18nKey("Завершено"),       color: "#1D9E75", sub: i18nKey("работы завершены") },
  quarterly: { key: "quarterly", label: i18nKey("Ежеквартально"),   color: "#7E22CE", sub: i18nKey("регулярные · квартал") },
  monthly:   { key: "monthly",   label: i18nKey("Ежемесячно"),      color: "#4338CA", sub: i18nKey("регулярные · месяц") },
  ongoing:   { key: "ongoing",   label: i18nKey("Постоянно"),       color: "#0E7490", sub: i18nKey("регулярные · постоянно") },
  overdue:   { key: "overdue",   label: i18nKey("Просрочено"),      color: "#E24B4A", sub: i18nKey("срок истёк") },
};

// Полный набор статус-плиток (порядок = пайплайн работ). Считаем проекты+задачи
// каждого статуса; в шаблоне показываем только ненулевые (скрытие 0). Короткий
// лейбл — для компактной плитки; полный — в модалке (STATUS_DRILLS).
const STATUS_TILE_ORDER: { key: StatusDrillKey; short: string }[] = [
  { key: "new",       short: i18nKey("Не начато") },
  { key: "init",      short: i18nKey("Иниц.") },
  { key: "active",    short: i18nKey("В процессе") },
  { key: "review",    short: i18nKey("Согл.") },
  { key: "deferred",  short: i18nKey("Перенес.") },
  { key: "quarterly", short: i18nKey("Ежекв.") },
  { key: "monthly",   short: i18nKey("Ежемес.") },
  { key: "ongoing",   short: i18nKey("Постоянно") },
];
function _statusPred(key: StatusDrillKey) {
  return key === "deferred"
    ? (it: any) => !!it.linked_year
    : (it: any) => it.status === key;
}
const statusTiles = computed(() =>
  STATUS_TILE_ORDER
    .map((t) => {
      const pred = _statusPred(t.key);
      const count = taskItems.value.filter(pred).length + projItems.value.filter(pred).length;
      return { key: t.key, short: t.short, color: STATUS_DRILLS[t.key].color, count };
    })
    .filter((t) => t.count > 0),
);
interface StatusDrillRow {
  kind: "project" | "task"; id: string; title: string; owner: string | null;
  due_date: string | null; status: string; progress: number | null;
  isOverdue: boolean; daysOverdue: number;
}
const statusDrillKey = ref<StatusDrillKey | null>(null);
const statusDrillDef = computed(() => (statusDrillKey.value ? STATUS_DRILLS[statusDrillKey.value] : null));

function _mapStatusRow(it: any, kind: "project" | "task"): StatusDrillRow {
  return {
    kind,
    id: String(it.id),
    title: it.title || it.name || t("(без названия)"),
    owner: it.assignee_name || it.owner_name || it.manager_name || it.responsible || null,
    due_date: it.due_date ?? null,
    status: String(it.status || ""),
    progress: typeof it.progress_percent === "number" ? it.progress_percent
            : (typeof it.progress === "number" ? it.progress : null),
    isOverdue: it.status !== "done" && isOverdue(it.due_date),
    daysOverdue: _daysOverdueOf(it.due_date),
  };
}
const statusDrillRows = computed<StatusDrillRow[]>(() => {
  const k = statusDrillKey.value;
  if (!k || k === "overdue") return [];
  const pred = k === "deferred"
    ? (it: any) => !!it.linked_year
    : (it: any) => it.status === k;
  const projects = projItems.value.filter(pred).map((p: any) => _mapStatusRow(p, "project"));
  const tasks = taskItems.value.filter(pred).map((t: any) => _mapStatusRow(t, "task"));
  return [...projects, ...tasks].sort((a, b) => b.daysOverdue - a.daysOverdue);
});
function openStatusDrill(k: StatusDrillKey) {
  if (k === "overdue") { openOverdueModal(); return; }   // у просрочки своя модалка
  statusDrillKey.value = k;
}
function closeStatusDrill() { statusDrillKey.value = null; }
function openStatusRow(r: StatusDrillRow) {
  closeStatusDrill();
  void openTaskEditor({ id: r.id, kind: r.kind });
}

// =====================================================================
// Rating helpers (color by credit grade, outlook label, etc.)
// =====================================================================

// Outlook-вид рендерится внутри RatingTile (credit-mode) — workspace больше
// не дублирует маппинг.

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

// ESG-вид (балл/шкала) рендерится внутри RatingTile (mode="esg").

// =====================================================================
// Rating inline-edit (RBAC ratings.edit) + cross-view realtime sync
// =====================================================================
const ratingsPerm = usePermissions("ratings");

// Refetch only ratings — после inline-сейва (этот вью) или field_update по WS
// (правка из другого вью/вкладки). Идемпотентно, мягко к ошибкам.
async function reloadRatings(): Promise<void> {
  if (!code.value) return;
  try {
    const r = await ratingsApi.getCompanyRatings(code.value);
    credit.value = r.credit || [];
    esg.value = r.esg || [];
  } catch {
    /* оставляем текущее значение при сетевой ошибке */
  }
}

// Realtime: бэкенд шлёт field_update (source_module=ratings) в /ws/companies
// при любом сохранении рейтинга. Слушаем для ТЕКУЩЕЙ компании → рефетч,
// чтобы карточки синхронизировались во всех открытых вью без перезагрузки.
let _ratingsWs: WebSocket | null = null;
let _ratingsWsClosed = false;
async function connectRatingsSync(): Promise<void> {
  if (_ratingsWsClosed) return;
  // Сокет требует аутентификации: тикет по authenticated REST → в субпротокол.
  let ticket: string;
  try {
    ticket = (await companyLibraryApi.wsTicket()).ticket;
  } catch {
    if (!_ratingsWsClosed) setTimeout(connectRatingsSync, 4000);
    return;
  }
  if (_ratingsWsClosed) return;
  try {
    const proto = window.location.protocol === "https:" ? "wss:" : "ws:";
    _ratingsWs = new WebSocket(
      `${proto}//${window.location.host}/api/ws/companies`,
      ["uza-ws-ticket-v1", ticket],
    );
    _ratingsWs.onmessage = (ev) => {
      try {
        const m = JSON.parse(ev.data) as {
          type?: string; company_id?: string; source_module?: string;
        };
        if (
          m?.type === "field_update" &&
          m?.source_module === "ratings" &&
          company.value && m.company_id === company.value.id
        ) {
          reloadRatings();
        }
      } catch { /* malformed — ignore */ }
    };
    _ratingsWs.onclose = () => {
      _ratingsWs = null;
      if (!_ratingsWsClosed) setTimeout(connectRatingsSync, 4000);  // авто-reconnect
    };
  } catch { /* offline — деградируем тихо */ }
}
onMounted(connectRatingsSync);
onUnmounted(() => {
  _ratingsWsClosed = true;
  if (_ratingsWs) { try { _ratingsWs.close(); } catch { /* ignore */ } _ratingsWs = null; }
});

// =====================================================================
// Donut SVG geometry
// =====================================================================
const ringR = 30;
const ringC = 2 * Math.PI * ringR;
const ringDash = computed(() => ringC * pct.value / 100);
const ringOffset = computed(() => (ringC - ringDash.value).toFixed(2));
const taskColor = computed(() => pct.value >= 70 ? "#1D9E75" : pct.value >= 35 ? "#D97706" : "#E24B4A");

// План по дедлайнам: доля задач, чей срок уже наступил (due_date ≤ сегодня),
// от того же знаменателя, что и прогресс (monthly/ongoing исключены). Рисуется
// прозрачной дугой позади факт-кольца — видно отставание (план > факта).
const taskPlanPct = computed(() => {
  const items = taskItems.value as any[];
  if (!Array.isArray(items)) return 0;
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  let total = 0;
  let due = 0;
  for (const t of items) {
    if (t.status === "monthly" || t.status === "ongoing") continue;
    total++;
    if (t.due_date) {
      const d = new Date(t.due_date);
      if (!isNaN(d.getTime()) && d <= today) due++;
    }
  }
  return total ? Math.round((due / total) * 100) : 0;
});
const planRingOffset = computed(() => (ringC - ringC * taskPlanPct.value / 100).toFixed(2));

// =====================================================================
// Helpers
// =====================================================================
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

// Создание новой задачи/проекта в этой компании (кнопки в топбаре)
function openCreateTask() {
  editorEntity.value = null;          // null → редактор в режиме создания
  editorKind.value = "task";
  editorOpen.value = true;
}
function openCreateProject() {
  editorEntity.value = null;
  editorKind.value = "project";
  editorOpen.value = true;
}

async function onEditorSaved() {
  editorOpen.value = false;
  editorEntity.value = null;
  pmoRefreshTick.value++;   // PMO-Гантт перечитает расписание (даты/зависимости могли измениться)
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
    <UzaStateBlock v-if="loading" state="loading" :text="t('Загрузка рабочего пространства…')" />

    <UzaStateBlock v-else-if="error" state="error" variant="block" :text="error" />

    <template v-else-if="company">
      <!-- ═══════ TOPBAR ═══════ -->
      <header class="cw-topbar">
        <div class="cw-topbar-l">
          <button class="cw-sb-toggle" @click="onBurger()" :title="t('Меню / свернуть сайдбар')" aria-label="toggle sidebar">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round">
              <line x1="3" y1="6" x2="21" y2="6"/>
              <line x1="3" y1="12" x2="21" y2="12"/>
              <line x1="3" y1="18" x2="21" y2="18"/>
            </svg>
          </button>
          <h1 :title="localizedCompanyName">{{ localizedCompanyName }}</h1>

          <span v-if="sector" class="cw-tbadge cw-tbadge-sector"
                :style="sector.color_hex ? `background: ${sector.color_hex}24; color: ${sector.color_hex}` : ''">
            {{ localizedSectorName }}
          </span>

          <!-- Премиум-ссылка на сайт компании -->
          <a v-if="companyWebsite" :href="companyWebsite" target="_blank" rel="noopener noreferrer"
             class="cw-site-link" :title="t('Открыть сайт: {url}', { url: companyWebsite })">
            <svg class="cw-site-globe" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><path d="M2 12h20M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z"/></svg>
            <span class="cw-site-host">{{ websiteHost }}</span>
            <svg class="cw-site-ext" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M7 17 17 7M7 7h10v10"/></svg>
          </a>

        </div>

        <div class="cw-topbar-r">
          <!-- Year picker -->
          <div class="cw-year-picker">
            <button class="cw-yr-arrow" @click="navigateYear(-1)" :disabled="year <= 2024">‹</button>
            <span class="cw-yr-label">FY {{ year }}</span>
            <button class="cw-yr-arrow" @click="navigateYear(1)" :disabled="year >= 2030">›</button>
          </div>

          <!-- Переключатель вида внутри таба «Работа»: Канбан | Список -->
          <div v-if="activeTab === 'work'" class="cw-viewtoggle" role="tablist">
            <button class="cw-vt-btn" :class="{ on: workView === 'kanban' }" @click="workView = 'kanban'" :title="t('Канбан-доска')">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="3" width="6" height="18" rx="1"/><rect x="10" y="3" width="6" height="12" rx="1"/><rect x="17" y="3" width="4" height="8" rx="1"/></svg>
              {{ t("Канбан") }}
            </button>
            <button class="cw-vt-btn" :class="{ on: workView === 'list' }" @click="workView = 'list'" :title="t('Список')">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="8" y1="6" x2="21" y2="6"/><line x1="8" y1="12" x2="21" y2="12"/><line x1="8" y1="18" x2="21" y2="18"/><line x1="3" y1="6" x2="3.01" y2="6"/><line x1="3" y1="12" x2="3.01" y2="12"/><line x1="3" y1="18" x2="3.01" y2="18"/></svg>
              {{ t("Список") }}
            </button>
          </div>

          <button class="cw-add-btn cw-add-btn-ghost" @click="openCreateProject">+ {{ t("Проект") }}</button>
          <button class="cw-add-btn" @click="openCreateTask">+ {{ t("Задача") }}</button>
        </div>
      </header>

      <CompanyTabBar
        :active-tab="activeTab as any"
        :indicators="tabIndicators as any"
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
                <div class="cw-section-label">{{ t("РЕЙТИНГИ") }}</div>
                <div class="cw-ratings-grid">

                  <RatingTile
                    :company-id="company?.id || ''"
                    agency="Fitch"
                    label="Fitch Ratings"
                    :rating="fitchRating || null"
                    :can-edit="ratingsPerm.canEdit.value"
                    mode="credit"
                    @saved="reloadRatings"
                  />
                  <RatingTile
                    :company-id="company?.id || ''"
                    agency="S&P"
                    label="S&P Global"
                    :rating="spRating || null"
                    :can-edit="ratingsPerm.canEdit.value"
                    mode="credit"
                    @saved="reloadRatings"
                  />
                  <RatingTile
                    :company-id="company?.id || ''"
                    agency="Moody's"
                    label="Moody's"
                    :rating="moodysRating || null"
                    :can-edit="ratingsPerm.canEdit.value"
                    mode="credit"
                    @saved="reloadRatings"
                  />
                  <RatingTile
                    :company-id="company?.id || ''"
                    :agency="esgRating?.agency || 'Sustainable Fitch'"
                    :label="esgRating?.agency || 'ESG'"
                    :rating="esgRating || null"
                    :can-edit="ratingsPerm.canEdit.value"
                    mode="esg"
                    @saved="reloadRatings"
                  />

                </div>
              </div>

              <!-- DIVIDER 1 -->
              <div class="cw-divider"></div>

              <!-- ── CENTER: PROGRESS DONUT ── -->
              <div class="cw-hero-col cw-hero-col-donut">
                <div class="cw-section-label">{{ t("ПРОГРЕСС") }}</div>

                <svg class="cw-donut-svg" viewBox="0 0 72 72" width="78" height="78">
                  <defs>
                    <linearGradient id="cwDonutGrad" x1="0" y1="0" x2="1" y2="1">
                      <stop offset="0%" stop-color="#34D399" />
                      <stop offset="100%" stop-color="#1D9E75" />
                    </linearGradient>
                  </defs>
                  <circle cx="36" cy="36" :r="ringR" fill="none" stroke="#EEF1F7" stroke-width="6"/>
                  <!-- План (по дедлайнам) — прозрачная дуга позади факт-кольца -->
                  <circle v-if="taskPlanPct > 0"
                          cx="36" cy="36" :r="ringR" fill="none"
                          :stroke="taskColor" stroke-width="6" stroke-linecap="round"
                          :stroke-dasharray="ringC.toFixed(2)"
                          :stroke-dashoffset="planRingOffset"
                          transform="rotate(-90 36 36)"
                          opacity="0.22">
                    <title>{{ t("План по дедлайнам: {n}%", { n: taskPlanPct }) }}</title>
                  </circle>
                  <circle class="cw-donut-arc"
                          cx="36" cy="36" :r="ringR" fill="none"
                          stroke="url(#cwDonutGrad)" stroke-width="6" stroke-linecap="round"
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
                  {{ t("задач завершено") }}
                </div>
                <div v-if="projTotal > 0" class="cw-donut-sub">
                  <span :data-countup="projDone" data-cu-d="0">{{ projDone }}</span> /
                  <span :data-countup="projTotal" data-cu-d="0">{{ projTotal }}</span>
                  {{ t("проектов завершено") }}
                </div>

                <!-- Recurring pill -->
                <div v-if="recurCnt > 0" class="cw-recurring-pill"
                     :title="t('Регулярные задачи не учитываются в % прогресса')">
                  <svg width="9" height="9" viewBox="0 0 12 12" fill="none" stroke="currentColor"
                       stroke-width="1.4" stroke-linecap="round">
                    <path d="M2 6a4 4 0 014-4 4 4 0 010 8 4 4 0 01-4-4z"/>
                  </svg>
                  <span v-if="quartCnt > 0">
                    <span style="color: #7E22CE; font-weight: 600">{{ quartCnt }}</span> {{ t("ежекв.") }}
                  </span>
                  <span v-if="monthCnt > 0">
                    <span style="color: #4338CA; font-weight: 600">{{ monthCnt }}</span> {{ t("ежемес.") }}
                  </span>
                  <span v-if="ongCnt > 0">
                    <span style="color: #0E7490; font-weight: 600">{{ ongCnt }}</span> {{ t("постоянн.") }}
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
                  <div class="cw-stats-hero-l cw-stats-clickable" @click="openStatusDrill('done')"
                       :title="t('Показать завершённые задачи и проекты')">
                    <div class="cw-stats-hero-num">
                      <span :data-countup="done" data-cu-d="0">{{ done }}</span>
                      <span class="cw-stats-hero-sep">/</span>
                      <span :data-countup="total" data-cu-d="0">{{ total }}</span>
                    </div>
                    <div class="cw-stats-hero-sub">
                      {{ t("задач завершено") }} · <b>{{ projDone }}</b> {{ t("из") }} <b>{{ projTotal }}</b> {{ t("проектов") }}
                    </div>
                  </div>
                  <div class="cw-stats-hero-r">
                    <div v-if="!overdue" class="cw-stats-pill cw-stats-pill-good">
                      {{ t("все в графике") }}
                    </div>
                    <div v-else class="cw-stats-pill cw-stats-pill-bad cw-stats-clickable"
                         @click="openOverdueModal()" :title="t('Показать просроченные')">
                      {{ t("просрочено") }}: {{ overdueTask }} / {{ overdueProj }}
                    </div>
                  </div>
                </div>

                <!-- TIER 2: secondary statuses + results metric as 5-column micro grid -->
                <div class="cw-stats-grid cw-stats-grid-5">
                  <div v-for="st in statusTiles" :key="st.key"
                       class="cw-st-tile"
                       @click="openStatusDrill(st.key)"
                       :title="t('Показать: {s}', { s: t(STATUS_DRILLS[st.key].label) })">
                    <div class="cw-st-tile-num" :data-countup="st.count" data-cu-d="0">{{ st.count }}</div>
                    <div class="cw-st-tile-name">{{ t(STATUS_DRILLS[st.key].label) }}</div>
                  </div>
                  <div v-if="resultsExpected > 0"
                       class="cw-st-tile"
                       @click="openStatusDrill('done')"
                       :title="t('Результаты подтверждены: {have} из {exp} ({pct}%). Ждут: {miss}', { have: resultsHave, exp: resultsExpected, pct: resultsPct, miss: resultsMissing })">
                    <div class="cw-st-tile-num cw-st-tile-num-ratio">
                      <span :data-countup="resultsHave" data-cu-d="0">{{ resultsHave }}</span>
                      <span class="cw-st-ratio-sep">/</span>
                      <span :data-countup="resultsExpected" data-cu-d="0">{{ resultsExpected }}</span>
                    </div>
                    <div class="cw-st-tile-name">{{ t("Результаты") }}</div>
                  </div>
                </div>

              </div>

            </div>
          </section>

          <!-- Сотрудники — сразу под шапкой обзора: раньше карточка стояла
               последней, ниже документов и шести блоков, и до неё приходилось
               долго прокручивать (замечание владельца 29.07.2026). -->
          <CompanyEmployeesSummary :code="code" @open-people="activeTab = 'people'"
                                   style="margin-bottom: 16px" />

          <!-- ╔═ Placeholders for next session ═╗ -->
          <!-- Overview Extras -- 6 блоков -->
          <CompanyOverviewExtras
            :company-id="company?.id || ''"
            :company-code="(route.params.code as string) || ''"
            :sector-id="(company as any)?.sector_id || (sector as any)?.id || ''"
            :sector-name="localizedSectorName || t('Сектор')"
            :year="year"
            :overdue="overdue || 0"
          />

          <!-- Виджет «Документы компании» убран: библиотека переехала в
               отдельную вкладку «Документы» (файлы из карточек — там же). -->

        </div>

        <!-- ═══ KANBAN TAB — real implementation ═══ -->
        <!-- ═══ KANBAN TAB — 1:1 с легасиом renderBoard (kanban view: index.html:48151) ═══ -->
        <div v-else-if="activeTab === 'people'" :key="'people'" class="cw-people-scroll">
          <CompanyEmployeesTab :code="code" />
        </div>

        <div v-else-if="activeTab === 'work' && workView === 'kanban'" :key="'work-kanban'" class="cw-kanban-scroll">
          <div class="cw-kanban-board">
            <!-- Standard 5 columns (init / new / active / review / done) -->
            <div
              v-for="col in kanbanColumns"
              :key="col.id"
              class="kol"
              :class="{ 'kol--drag-over': dragOverCol === col.id }"
              :style="dragOverCol === col.id ? { '--col-accent': col.color } : {}"
              @dragover="onColDragOver(col.id, $event)"
              @dragleave="onColDragLeave"
              @drop="onColDrop(col.id, $event)"
            >
              <div class="kol-hd">
                <div class="kol-hd-l">
                  <div class="kol-dot" :style="`background: ${col.bgAccent}`"></div>
                  <div class="kol-title">{{ t(col.label) }}</div>
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
                    <div>{{ t("Нет задач") }}</div>
                  </div>
                </template>
                <KanbanCard
                  v-for="t in col.tasks"
                  :key="t.id"
                  :task="t"
                  :overdue="isOverdueTask(t)"
                  @click="openTaskEditor({ id: t.id, kind: 'task' })"
                  @dragstart="onTaskDragStart"
                />
              </div>
            </div>

            <!-- Recurring (quarterly/monthly/ongoing) — combined col like legacy -->
            <div v-if="recurringTasks.length > 0" class="kol kol-recurring">
              <div class="kol-hd">
                <div class="kol-hd-l">
                  <div class="kol-dot" style="background: linear-gradient(135deg, #A855F7, #06B6D4)"></div>
                  <div class="kol-title" style="color: #7E22CE">{{ t("Регулярные") }}</div>
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
                  · {{ t("М") }}: {{ recurringTasks.filter(t => t.status === 'monthly').length }}
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
                  @click="openTaskEditor({ id: t.id, kind: 'task' })"
                  @dragstart="onTaskDragStart"
                />
              </div>
            </div>

            <!-- Overdue column — red, only if any overdue tasks -->
            <div v-if="overdueTasks.length > 0" class="kol kol-overdue">
              <div class="kol-hd">
                <div class="kol-hd-l">
                  <div class="kol-dot" style="background: #E24B4A"></div>
                  <div class="kol-title" style="color: #E24B4A">{{ t("Просрочено") }}</div>
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
                  @click="openTaskEditor({ id: t.id, kind: 'task' })"
                  @dragstart="onTaskDragStart"
                />
              </div>
            </div>
          </div>
        </div>

        <!-- ═══ LIST TAB — real implementation ═══ -->
        <div v-else-if="activeTab === 'work' && workView === 'list'" :key="'work-list'" class="cw-list-scroll">
          <CompanyBoardList
            ref="boardListRef"
            :company-id="company?.id || ''"
            :company-name="localizedCompanyName"
            :year="year"
            @openEditor="openTaskEditor"
            @changed="onBoardListChanged"
          />
        </div>

        <!-- ═══ ДОКУМЕНТЫ — библиотека компании (файлы из карточек лежат тут же) ═══ -->
        <div v-else-if="activeTab === 'documents'" :key="'documents'" class="cw-doc-scroll">
          <CompanyDocuments :company-code="(route.params.code as string) || code" :can-edit="companiesPerm.canEdit.value" />
        </div>

        <!-- ═══ PMO TAB — расписание/Гантт (gated pmo.view) ═══ -->
        <div v-else-if="activeTab === 'pmo'" :key="'pmo'" class="cw-pmo-scroll">
          <PmoTab
            v-if="pmoPerm.canView.value"
            :company-code="(route.params.code as string) || code"
            :year="year"
            :can-edit="pmoPerm.canEdit.value"
            :refresh-tick="pmoRefreshTick"
            @open="openTaskEditor"
          />
          <UzaStateBlock
            v-else
            state="empty"
            variant="block"
            :title="t('Раздел PMO недоступен')"
            :text="t('Нужно право pmo.view. Обратитесь к администратору.')"
          />
        </div>

                <div
            v-else-if="activeTab === 'notes'"
            :key="'notes'"
            class="cw-cal-scroll"
          >
            <CompanyCalendar
              v-if="company?.id"
              :company-id="company.id"
              @open-entity="(p) => openTaskEditor({ id: p.entity_id, kind: p.entity_type })"
            />
            <div class="cw-cal-notes">
              <div class="cw-cal-notes-h">{{ t("Заметки") }}</div>
              <CompanyNotesTab
                v-if="company?.id"
                :company-id="company.id"
                :company-code="(route.params.code as string) || code"
                :year="year"
                :can-edit="tasksPerm.canEdit.value"
              />
            </div>
          </div>
        <!-- ═══ ОТЧЁТ — Reporting Wizard (печать A4, фронт-онли) ═══ -->
        <div v-else-if="activeTab === 'reporting'" :key="'reporting'" class="cw-rep-scroll" style="padding: 18px 24px 44px;">
          <div style="display:inline-flex; gap:4px; background:var(--bg2,#fafafc); border:1px solid var(--border,rgba(99,102,180,.14)); border-radius:11px; padding:3px; margin-bottom:18px;">
            <button @click="repSub = 'wizard'" :style="repSubBtn(repSub === 'wizard')">{{ t("Мастер отчёта") }}</button>
            <button @click="repSub = 'projreport'" :style="repSubBtn(repSub === 'projreport')">{{ t("Отчёт по проектам") }}</button>
            <!-- Сводный обзор = встроенный /executive-overview → то же право -->
            <button v-if="execOverviewPerm.canView.value" @click="repSub = 'overview'" :style="repSubBtn(repSub === 'overview')">{{ t("Сводный обзор") }}</button>
          </div>
          <ReportingWizard
            v-if="repSub === 'wizard'"
            :company-name="localizedCompanyName"
            :company-code="(route.params.code as string) || code"
            :sector-name="localizedSectorName || null"
            :year="year"
            :projects="projItems"
          />
          <ProjectsStatusReport
            v-else-if="repSub === 'projreport'"
            :company-id="company?.id || ''"
            :company-name="localizedCompanyName"
            :company-code="(route.params.code as string) || code"
            :sector-name="localizedSectorName || null"
            :year="year"
            :projects="projItems"
            :tasks="taskItems"
            :credit="credit"
            :esg="esg"
          />
          <!-- v-else-if, а не v-else: без права подвкладка не рисуется даже
               если repSub успел остаться 'overview' (сохранённое состояние) -->
          <ExecOverview v-else-if="execOverviewPerm.canView.value" :embed-company-id="company?.id" />
        </div>
        <!-- ═══ KPI TAB — real implementation ═══ -->
        <div v-else-if="activeTab === 'kpi'" :key="'kpi'" class="cw-kpi-scroll">
          <!-- Loading state -->
          <UzaStateBlock v-if="kpiLoading" state="loading" :text="t('Загрузка KPI {year}…', { year })" />

          <!-- Error state -->
          <UzaStateBlock v-else-if="kpiError" state="error" variant="block" :title="t('Ошибка загрузки KPI')" :text="kpiError" retry @retry="loadKpi" />

          <!-- Empty state -->
          <UzaStateBlock v-else-if="kpiManagerViews.length === 0" state="empty" variant="block" :title="t('KPI не настроены')" :text="t('Для {name} в {year} году KPI не добавлены.', { name: localizedCompanyName, year })">
            <template #actions>
              <button v-if="kpiPerm.canEdit" class="cw-cta-btn" @click="openKpiEditor">{{ t("Создать KPI") }}</button>
              <RouterLink to="/kpi" class="cw-cta-btn" style="background:transparent;color:var(--uza-purple);border:1px solid var(--uza-purple)">{{ t("Открыть в полной версии →") }}</RouterLink>
            </template>
          </UzaStateBlock>

          <!-- KPI dashboard · redesigned 2026-05-23 to reuse KpiCompanyDashboard + KpiEditor (BP-style integration) -->
          <template v-else>
            <!-- Period selector + Edit button (mirror BP-tab pattern) -->
            <div class="cw-bp-period-bar" style="margin-bottom: 12px">
              <div class="cw-bp-period-label">{{ t("Период") }}:</div>
              <!-- "Год" убран 2026-05-23: fact_year заведён у <1% индикаторов. -->
              <button
                v-for="p in [{key:'q1', label:'Q1'}, {key:'q2', label:'Q2'}, {key:'q3', label:'Q3'}, {key:'q4', label:'Q4'}]"
                :key="p.key"
                class="cw-bp-period-btn"
                :class="{ active: kpiPeriod === p.key }"
                @click="kpiPeriod = (p.key as WsKpiPeriod)"
              >{{ t(p.label) }}</button>
              <button
                v-if="kpiPerm.canEdit"
                class="cw-bp-edit-btn"
                type="button"
                @click="openKpiEditor"
                :title="t('Открыть редактор KPI')"
              >
                <svg width="13" height="13" viewBox="0 0 24 24" fill="none"
                     stroke="currentColor" stroke-width="2"
                     stroke-linecap="round" stroke-linejoin="round">
                  <path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/>
                  <path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"/>
                </svg>
                {{ t("Редактировать") }}
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
                {{ t("Факт за {year} ещё не введён. Внизу в деталях — факт {base} как baseline.", { year, base: kpiBaselineYear }) }}
                <span v-if="kpiPeriod === 'annual'">
                  {{ t("Совет: переключитесь на Q1 — там данные заполнены.") }}
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
              :company-name="localizedCompanyName"
              :year="year"
              :can-edit="kpiPerm.canEdit.value"
              @set-manager="activeKpiMgrIdx = $event"
              @open-indicator="openKpiEditor"
            />
          </template>

        </div>

        <!-- ═══ BUSINESS PLAN TAB — real implementation ═══ -->
        <div v-else-if="activeTab === 'bp'" :key="'bp'" class="cw-bp-scroll">
          <!-- Period selector + Edit button (right-aligned) -->
          <div class="cw-bp-period-bar">
            <div class="cw-bp-period-label">{{ t("Период") }}:</div>
            <button
              v-for="p in BP_PERIODS"
              :key="p.key"
              class="cw-bp-period-btn"
              :class="{ active: bpPeriod === p.key }"
              @click="bpPeriod = p.key"
            >
              {{ t(p.label) }}
            </button>
            <button
              v-if="bpPerm.canEdit"
              class="cw-bp-edit-btn"
              type="button"
              @click="openBpEditor"
              :title="t('Открыть редактор бизнес-плана')"
            >
              <svg width="13" height="13" viewBox="0 0 24 24" fill="none"
                   stroke="currentColor" stroke-width="2"
                   stroke-linecap="round" stroke-linejoin="round">
                <path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/>
                <path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"/>
              </svg>
              {{ t("Редактировать") }}
            </button>
          </div>

          <!-- Loading state -->
          <UzaStateBlock v-if="bpLoading" state="loading" :text="t('Загрузка Бизнес-плана {year} ({period})…', { year, period: bpPeriod })" />

          <UzaStateBlock v-else-if="bpError" state="error" variant="block" :title="t('Ошибка загрузки Бизнес-плана')" :text="bpError" retry @retry="loadBp" />

          <UzaStateBlock v-else-if="!bpData || bpFieldViews.length === 0" state="empty" variant="block" :title="t('Бизнес-план не загружен')" :text="t('Для {name} в {year} году записи отсутствуют.', { name: localizedCompanyName, year })" />

          <template v-else>
            <!-- Top 3 KPI cards -->
            <div class="cw-bp-tops kpi-rail">
              <div
                v-for="(m, mi) in bpTopMetrics"
                :key="m.key"
                class="kpi2 fin-shimmer cw-bp-top-card"
                :style="{
                  '--kpi2-accent': m.key === 'revenue' ? 'var(--uza-purple)' : m.key === 'opProfit' ? 'var(--uza-teal)' : 'var(--uza-amber)',
                  '--kpi2-d': (mi * 80) + 'ms',
                }"
              >
                <div class="kpi2-lbl">{{ t(m.label) }}</div>
                <div class="kpi2-val">{{ bpFmt(m.fact ?? m.plan) }}</div>
                <div class="cw-bp-top-stats">
                  <div class="cw-bp-top-stat">
                    <span class="cw-bp-top-stat-l">{{ t("План") }}:</span>
                    <span class="cw-bp-top-stat-v">{{ bpFmt(m.plan) }}</span>
                  </div>
                  <div class="cw-bp-top-stat">
                    <span class="cw-bp-top-stat-l">{{ t("Факт") }}:</span>
                    <span class="cw-bp-top-stat-v">{{ bpFmt(m.fact) }}</span>
                  </div>
                  <div class="cw-bp-top-stat" v-if="m.pct !== null">
                    <span class="cw-bp-top-stat-l">{{ t("Выполнение") }}:</span>
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
                <div class="cw-bp-th cw-bp-th-name">{{ t("Метрика") }}</div>
                <div class="cw-bp-th cw-bp-th-num">{{ t("План") }}</div>
                <div class="cw-bp-th cw-bp-th-num">{{ t("Ожидание") }}</div>
                <div class="cw-bp-th cw-bp-th-num">{{ t("Факт") }}</div>
                <div class="cw-bp-th cw-bp-th-pct">%</div>
              </div>

              <template v-for="grp in bpGroups" :key="grp.id">
                <div class="cw-bp-group-header">{{ t(grp.label) }}</div>

                <div
                  v-for="row in grp.items"
                  :key="row.key"
                  class="cw-bp-row"
                  :class="{ 'cw-bp-row-auto': row.auto, 'cw-bp-row-sub': row.sub, 'cw-bp-row-final': row.key === 'profit' }"
                >
                  <div class="cw-bp-cell cw-bp-cell-name">
                    <span v-if="row.auto" class="cw-bp-auto-mark" :title="t('Автоматически вычисляется')">∑</span>
                    {{ t(row.label) }}
                  </div>
                  <div class="cw-bp-cell cw-bp-cell-num">{{ bpFmt(row.plan) }}</div>
                  <div class="cw-bp-cell cw-bp-cell-num">{{ bpFmt(row.expect) }}</div>
                  <div class="cw-bp-cell cw-bp-cell-num cw-bp-cell-fact">{{ bpFmt(row.fact) }}</div>
                  <div class="cw-bp-cell cw-bp-cell-pct"
                       :title="row.expense ? t('Расходная строка: больше 100% — перерасход') : ''"
                       :style="row.pct !== null ? `color: ${bpPctColor(row.pct, row.expense)}` : ''">
                    {{ row.pct === null ? "—" : row.pct + "%" }}
                  </div>
                </div>
              </template>
            </div>
          </template>

          <!-- ═══ Производственные показатели этой компании (натура + деньги) ═══ -->
          <CwProductionSection
            :company-code="company?.code || code"
            :company-name="localizedCompanyName"
            :year="year"
            :can-edit="bpPerm.canEdit"
          />
        </div>

        <!-- ═══ GOVERNANCE TAB — real implementation ═══ -->
        <div v-else-if="activeTab === 'governance'" :key="'governance'" class="cw-gov-scroll">
          <UzaStateBlock v-if="govLoading" state="loading" :text="t('Загрузка корпоративного управления…')" />

          <UzaStateBlock v-else-if="govError" state="error" variant="block" :title="t('Ошибка загрузки')" :text="govError" retry @retry="loadGovernance" />

          <UzaStateBlock v-else-if="!(govDetail?.data || govDetail?.governance_data) && govMembers.length === 0" state="empty" variant="block" :title="t('Данные не введены')" :text="t('Для {name} в {year} году данные о корп. управлении отсутствуют.', { name: localizedCompanyName, year })">
            <template #actions>
              <button v-if="govPerm.canEdit.value" class="cw-cta-btn" @click="openGovEditor">{{ t("Ввести данные") }}</button>
              <RouterLink v-else to="/governance" class="cw-cta-btn">{{ t("Открыть редактор →") }}</RouterLink>
            </template>
          </UzaStateBlock>

          <template v-else>
            <!-- Header: year-fallback notice + edit -->
            <div class="cw-gov-toolbar">
              <div v-if="govShownYear && govShownYear !== year" class="cw-fin-year-notice cw-gov-notice">
                {{ t("За {year} данных нет — показан {shown} (последний доступный).", { year, shown: govShownYear }) }}
              </div>
              <span v-else></span>
              <button v-if="govPerm.canEdit.value" class="cw-gov-edit-btn" @click="openGovEditor">
                <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="vertical-align:-1px;margin-right:5px"><path d="M12 20h9"/><path d="M16.5 3.5a2.1 2.1 0 0 1 3 3L7 19l-4 1 1-4z"/></svg>{{ t("Редактировать") }}
              </button>
            </div>

            <!-- KPI grid -->
            <div class="cw-gov-kpis kpi-rail">
              <div
                v-for="(kpi, ki) in govKpis"
                :key="kpi.label"
                class="kpi2 fin-shimmer"
                :style="{ '--kpi2-accent': kpi.color, '--kpi2-d': (ki * 80) + 'ms', '--d': ki }"
              >
                <div class="kpi2-lbl">{{ t(kpi.label) }}</div>
                <!-- Анимируем только само число: сканер count-up пишет в
                     textContent голую цифру, поэтому суффикс «%» держим снаружи,
                     а форматированные значения (деньги, единицы) не трогаем. -->
                <div class="kpi2-val">
                  <template v-if="kpi.raw !== null">
                    <span :data-countup="kpi.raw">{{ kpi.raw }}</span><span v-if="String(kpi.value).endsWith('%')">%</span>
                  </template>
                  <template v-else>{{ kpi.value }}</template>
                </div>
                <div v-if="kpi.unit" class="kpi2-sub">{{ kpi.unit }}</div>
              </div>
            </div>

            <!-- Аналитика состава совета — доли + средний срок -->
            <div v-if="boardComposition" class="cw-gov-section">
              <div class="cw-section-label">{{ t("Состав и разнообразие совета") }}</div>
              <div class="cw-gov-comp">
                <div
                  v-for="(b, bi) in boardComposition.bars"
                  :key="b.label"
                  class="cw-gov-comp-bar"
                  :style="`--d: ${bi}`"
                >
                  <div class="cw-gov-comp-hd">
                    <span class="cw-gov-comp-l">{{ t(b.label) }}</span>
                    <span class="cw-gov-comp-v" :style="`color: ${b.color}`">
                      {{ b.pct }}<span class="cw-gov-comp-pc">%</span>
                      <span class="cw-gov-comp-cnt">· {{ b.count }} {{ t("из") }} {{ boardComposition.total }}</span>
                    </span>
                  </div>
                  <div class="cw-gov-comp-track">
                    <div class="cw-gov-comp-fill" :style="`width: ${b.pct}%; background: ${b.color}; --d: ${bi}`"></div>
                  </div>
                </div>
                <div v-if="boardComposition.avgTenure != null" class="cw-gov-comp-tenure">
                  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/></svg>
                  {{ t("Средний срок в совете:") }}
                  <b>{{ boardComposition.avgTenure < 1 ? '<1' : boardComposition.avgTenure.toFixed(1) }} {{ boardComposition.avgTenure >= 1 && boardComposition.avgTenure < 2 ? t('года') : t('лет') }}</b>
                </div>
              </div>
            </div>

            <!-- Committees -->
            <div class="cw-gov-section">
              <div class="cw-section-label">{{ t("Комитеты совета") }}</div>
              <div class="cw-gov-committees">
                <div
                  v-for="c in govCommittees"
                  :key="c.label"
                  class="cw-gov-committee"
                  :class="{ 'cw-gov-committee-on': c.present, 'cw-gov-committee-off': !c.present }"
                >
                  <span class="cw-gov-committee-icon"><svg v-if="c.present" width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.6" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"/></svg><svg v-else width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2"><circle cx="12" cy="12" r="8"/></svg></span>
                  <span>{{ t(c.label) }}</span>
                  <span v-if="c.meetings != null" class="cw-gov-committee-mtg" :title="t('Заседаний за {year} год', { year })">{{ c.meetings }}</span>
                </div>
              </div>
            </div>

            <!-- Board members -->
            <div v-if="boardMembersByRole.length > 0" class="cw-gov-section">
              <div class="cw-section-label">
                {{ t("Состав совета директоров") }} ({{ boardMembersByRole.length }} {{ t("чел.") }})
              </div>
              <div class="cw-gov-members">
                <div
                  v-for="(m, mi) in boardMembersByRole"
                  :key="m.id"
                  class="cw-gov-member cw-gov-member--click"
                  :style="`--d: ${mi}`"
                  role="button"
                  tabindex="0"
                  @click="openBoardMember(m)"
                  @keydown.enter.prevent="openBoardMember(m)"
                  @keydown.space.prevent="openBoardMember(m)"
                  @mouseenter="bmHoverEnter(m, $event.currentTarget as HTMLElement)"
                  @mouseleave="bmHoverLeave"
                  @focus="bmHoverEnter(m, $event.currentTarget as HTMLElement)"
                  @blur="bmHoverLeave"
                >
                  <div class="cw-gov-avatar" :style="`background: ${m.roleColor}`">
                    {{ m.initials }}
                  </div>
                  <div class="cw-gov-member-info">
                    <div class="cw-gov-member-name">{{ m.fullName }}</div>
                    <div class="cw-gov-member-pos" v-if="m.position">{{ m.position }}</div>
                    <div class="cw-gov-member-meta">
                      <span class="cw-gov-role-pill" :style="`background: ${m.roleColor}22; color: ${m.roleColor}`">
                        {{ t(m.roleLabel) }}
                      </span>
                      <span v-if="m.isIndependent && m.roleType !== 'independent'" class="cw-gov-badge">{{ t("Независимый") }}</span>
                      <span v-if="m.isWoman" class="cw-gov-badge">♀</span>
                      <span v-if="m.isForeign" class="cw-gov-badge">{{ t("Иностранец") }}</span>
                    </div>
                    <div class="cw-gov-member-dates">
                      {{ t("Назначен:") }} {{ m.appointed }} · {{ t("до") }} {{ m.termEnd }}
                    </div>
                  </div>
                  <svg class="cw-gov-member-chev" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M9 18l6-6-6-6"/></svg>
                </div>
              </div>
            </div>
          </template>
        </div>

        <!-- ═══ ESG TAB — real implementation ═══ -->
        <div v-else-if="activeTab === 'esg'" :key="'esg'" class="cw-esg-scroll">
          <!-- ESG-вкладка = весь /esg в срезе компании: подвкладки Показатели /
               Зрелость / SWOT на общих с /esg панелях (единый бэкенд → синк). -->
          <div v-if="company" class="cw-esg-subtabs" style="margin-bottom:16px">
            <UzaSegment v-model="esgSubTab" :options="ESG_SUBTABS" size="sm" />
          </div>

          <ESGMaturityProfilePanel
            v-if="company && esgSubTab === 'maturity'"
            :company-id="company.id"
            :company-code="company.code"
            :year="year"
            :can-edit="esgPerm.canEdit.value"
          />
          <ESGSwotPanel
            v-else-if="company && esgSubTab === 'swot'"
            :company-id="company.id"
            :can-edit="esgPerm.canEdit.value"
            @changed="onEsgPanelChanged"
          />
        </div>

        <!-- ═══ UNIT COST TAB — срез компании из /unit-cost (общий бэкенд → синк) ═══ -->
        <div v-else-if="activeTab === 'unitcost'" :key="'unitcost'" class="cw-uc-scroll">
          <div class="cw-uc-bar">
            <div class="cw-uc-bar-t">{{ t("Удельная себестоимость") }} <span>{{ t("факт · норма расхода · энергоёмкость по продуктам") }}</span></div>
            <UzaSegment v-model="ucQuarter" :options="UC_QUARTERS" size="sm" />
          </div>

          <UzaStateBlock v-if="ucLoading" state="loading" :text="t('Загрузка себестоимости…')" />
          <UzaStateBlock v-else-if="ucError" state="error" variant="block" :title="t('Ошибка загрузки')" :text="ucError" retry @retry="loadUnitCost" />
          <UzaStateBlock v-else-if="company && !ucCompany" state="empty" variant="block"
            :title="t('Данных по себестоимости нет')"
            :text="t('Для этой компании ещё не заведены продукты и удельный расход. Откройте модуль «Удельная себестоимость» и заполните данные.')" />

          <UnitCostCompanyPanel
            v-else-if="company && ucCompany"
            variant="embedded"
            :company="ucCompany"
            :prices="ucPrices"
            :world="ucWorld"
            :fuel-labels="ucFuelLabels"
            :year="year"
            :quarter="ucQuarter"
            @saved="onUnitCostSaved"
          />
        </div>

        <!-- ═══ CONSULTANTS TAB — directory + per-company integration TBD ═══ -->
        <div v-else-if="activeTab === 'consultants'" :key="'consultants'" class="cw-cons-scroll">
          <!-- ─── PER-COMPANY SECTION (primary view) ─── -->
          <UzaStateBlock v-if="consPerCompanyLoading" state="loading" :text="t('Загрузка консультантов компании…')" />

          <UzaStateBlock v-else-if="consPerCompanyError" state="error" variant="block" :title="t('Ошибка загрузки')" :text="consPerCompanyError" retry @retry="loadConsultantsPerCompany" />

          <template v-else>
            <!-- KPI-бэнд (эталон, как в /consultants): top-accent + count-up + shimmer -->
            <div v-if="consPerCompanyKpis" class="cw-cons2-kpis kpi-rail">
              <div class="kpi2 fin-shimmer" style="--kpi2-accent:#3B82F6; --kpi2-d:0ms">
                <div class="kpi2-lbl">{{ t("Консультантов") }}</div>
                <div class="kpi2-val"><span :data-countup="consPerCompanyKpis.consultants">{{ consPerCompanyKpis.consultants }}</span></div>
              </div>
              <div class="kpi2 fin-shimmer" style="--kpi2-accent:#7F77DD; --kpi2-d:80ms">
                <div class="kpi2-lbl">{{ t("Из них Big 4") }}</div>
                <div class="kpi2-val"><span :data-countup="consPerCompanyKpis.big4">{{ consPerCompanyKpis.big4 }}</span></div>
              </div>
              <div class="kpi2 fin-shimmer" style="--kpi2-accent:#EF9F27; --kpi2-d:160ms">
                <div class="kpi2-lbl">{{ t("Назначений") }}</div>
                <div class="kpi2-val"><span :data-countup="consPerCompanyKpis.assignments">{{ consPerCompanyKpis.assignments }}</span></div>
              </div>
              <div class="kpi2 fin-shimmer" style="--kpi2-accent:#1D9E75; --kpi2-d:240ms">
                <div class="kpi2-lbl">{{ t("Среднее выполнение") }}</div>
                <div class="kpi2-val" :style="`color:${pctColor(consPerCompanyKpis.completionPct)}`"><span :data-countup="consPerCompanyKpis.completionPct">{{ consPerCompanyKpis.completionPct }}</span><span class="cw-cons2-pctsign">%</span></div>
              </div>
            </div>

            <!-- Empty state — no consultants assigned to this company -->
            <UzaStateBlock
              v-if="consPerCompany && consPerCompany.consultants.length === 0"
              state="empty"
              variant="block"
              :title="t('Консультанты не назначены')"
            >
              {{ t("Для {name} в {year} году консультанты не привязаны ни к одной задаче.", { name: localizedCompanyName, year }) }}
              <p style="margin-top: 8px; font-size: 11.5px">
                {{ t("Чтобы добавить консультанта — откройте задачу в проекте и укажите консультанта в редакторе.") }}
              </p>
            </UzaStateBlock>

            <!-- Список консультантов компании — карточка + строки как в /consultants -->
            <div v-else class="cw-cons2-card">
              <div class="cw-cons2-h">
                <span class="cw-cons2-t">{{ t("Консультанты компании") }}</span>
                <span class="cw-cons2-hsub">{{ localizedCompanyName }} · FY {{ year }}</span>
              </div>
              <div class="cw-cons2-lhead">
                <span>{{ t("КОНСУЛЬТАНТ") }}</span><span>{{ t("ПРОГРЕСС") }}</span><span class="r">{{ t("ЗАДАЧИ") }}</span><span class="r">{{ t("ПРОСРОЧЕНО") }}</span>
              </div>
              <div class="cw-cons2-lbody">
                <template v-for="(c, i) in [...companyConsBig4, ...companyConsOther]" :key="c.id">
                  <div
                    class="cw-cons2-row"
                    :class="{ big4: c.is_big4, open: expandedCons === c.id }"
                    :style="{ '--stripe-color': c.color || '#888', animationDelay: (i * 30) + 'ms' }"
                    role="button" tabindex="0"
                    :title="c.projects.length ? t('Показать задачи') : ''"
                    @click="toggleConsRow(c.id)"
                    @keydown.enter="toggleConsRow(c.id)"
                    @keydown.space.prevent="toggleConsRow(c.id)"
                  >
                    <span v-if="c.is_big4" class="cw-cons2-stripe" :style="{ background: c.color || '#888' }" />
                    <div class="cw-cons2-name">
                      <span v-if="c.projects.length" class="cw-cons2-chevron" :class="{ open: expandedCons === c.id }"></span>
                      <span class="cw-cons2-name-t">{{ c.name }}</span>
                      <span v-if="c.is_big4" class="cw-cons2-big4"
                            :style="{ background: (c.color || '#888') + '15', color: c.color || '#888', borderColor: (c.color || '#888') + '25' }">Big 4</span>
                    </div>
                    <div class="cw-cons2-bar-wrap">
                      <div class="cw-cons2-bar"><div class="cw-cons2-bar-fill" :style="{ width: c.completion_pct + '%', background: pctColor(c.completion_pct) }" /></div>
                      <span class="cw-cons2-pct-v" :style="{ color: pctColor(c.completion_pct) }">{{ c.completion_pct }}%</span>
                    </div>
                    <div class="cw-cons2-num r">{{ c.task_done }} / {{ c.task_count }}</div>
                    <div class="cw-cons2-overdue r" :style="{ color: c.task_overdue > 0 ? '#993D3D' : 'var(--t3,#888780)' }">
                      {{ c.task_overdue > 0 ? c.task_overdue : '—' }}
                    </div>
                  </div>
                  <!-- инлайн-раскрытие: задачи консультанта -->
                  <transition name="cw-cons2-exp">
                    <div v-if="expandedCons === c.id && c.projects.length" class="cw-cons2-projects">
                      <div
                        v-for="p in c.projects"
                        :key="p.id"
                        class="cw-cons2-project"
                        :title="p.title"
                        @click.stop="openTaskEditor({ id: p.id, kind: 'task' })"
                      >
                        <span class="cw-cons2-project-status" :style="`color: ${getStatusColor(p.status)}`" v-html="getStatusShortLabel(p.status)"></span>
                        <span class="cw-cons2-project-title">{{ p.title }}</span>
                        <span v-if="p.due_date" class="cw-cons2-project-date">{{ fmtDate(p.due_date) }}</span>
                      </div>
                      <div v-if="c.task_count > c.projects.length" class="cw-cons2-project-more">
                        {{ t("показаны {shown} из {total} задач", { shown: c.projects.length, total: c.task_count }) }}
                      </div>
                    </div>
                  </transition>

                  <div v-if="c.is_big4 && i === companyConsBig4.length - 1 && companyConsOther.length"
                       :key="c.id + '-sep'" class="cw-cons2-seclabel">{{ t("Другие консультанты") }}</div>
                </template>
              </div>
            </div>

          </template>
        </div>

        <!-- ═══ CREDIT PORTFOLIO TAB — real implementation ═══ -->
        <div v-else-if="activeTab === 'credit'" :key="'credit'" class="cw-cred-scroll">
          <UzaStateBlock v-if="creditLoading" state="loading" :text="t('Загрузка кредитного портфеля…')" />

          <UzaStateBlock v-else-if="creditError" state="error" variant="block" :title="t('Ошибка загрузки')" :text="creditError" retry @retry="loadCredit" />

          <UzaStateBlock v-else-if="creditLoans.length === 0" state="empty" variant="block" :title="t('Кредитов нет')" :text="t('У {name} нет активных кредитов в портфеле.', { name: localizedCompanyName })">
            <template #actions>
              <RouterLink to="/credit-portfolio" class="cw-cta-btn">{{ t("Открыть полный портфель →") }}</RouterLink>
            </template>
          </UzaStateBlock>

          <template v-else>
            <!-- KPI strip -->
            <div class="cw-cred-kpis kpi-rail">
              <div class="kpi2 fin-shimmer" style="--kpi2-accent:#7F77DD; --kpi2-d:0ms">
                <div class="kpi2-lbl">{{ t("Активных кредитов") }}</div>
                <div class="kpi2-val"><span :data-countup="creditKpis.total">{{ creditKpis.total }}</span></div>
              </div>
              <div class="kpi2 fin-shimmer" style="--kpi2-accent:#3B82F6; --kpi2-d:80ms">
                <div class="kpi2-lbl">{{ t("Общая задолженность") }}</div>
                <div class="kpi2-val">{{ fmtUsd(creditKpis.totalDebt) }}</div>
              </div>
              <div class="kpi2 fin-shimmer" style="--kpi2-accent:#1D9E75; --kpi2-d:160ms">
                <div class="kpi2-lbl">{{ t("Гарантированных") }}</div>
                <div class="kpi2-val"><span :data-countup="creditKpis.guaranteed">{{ creditKpis.guaranteed }}</span></div>
              </div>
              <div class="kpi2 fin-shimmer" style="--kpi2-accent:#EF9F27; --kpi2-d:240ms">
                <div class="kpi2-lbl">{{ t("Средняя ставка") }}</div>
                <div class="kpi2-val">{{ fmtRate(creditKpis.avgRate) }}</div>
              </div>
            </div>

            <!-- Lender type breakdown -->
            <div v-if="creditByLender.length > 0" class="cw-cred-section">
              <div class="cw-section-label">{{ t("По типу кредитора") }}</div>
              <div class="cw-cred-buckets">
                <div
                  v-for="b in creditByLender"
                  :key="b.key"
                  class="cw-cred-bucket"
                  :style="`--accent: ${b.color}`"
                  :title="t('{label} · {n} {u} · долг {debt} ({pct}% от портфеля)', { label: b.label, n: b.count, u: b.count === 1 ? t('кредит') : t('кредитов'), debt: fmtUsd(b.debt), pct: b.pct })"
                >
                  <div class="cw-cred-bucket-row">
                    <span class="cw-cred-bucket-dot" :style="`background: ${b.color}`"></span>
                    <span class="cw-cred-bucket-label">{{ t(b.label) }}</span>
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
              <div class="cw-section-label">{{ t("По валюте") }}</div>
              <div class="cw-cred-currencies">
                <div
                  v-for="c in creditByCurrency"
                  :key="c.key"
                  class="cw-cred-currency"
                  :style="`--accent: ${c.color}`"
                >
                  <div class="cw-cred-currency-code" :style="`color: ${c.color}`">{{ t(c.label) }}</div>
                  <div class="cw-cred-currency-debt">{{ fmtUsd(c.debt) }}</div>
                  <div class="cw-cred-currency-meta">{{ c.count }} {{ c.count === 1 ? t('кредит') : t('кредитов') }} · {{ c.pct }}%</div>
                </div>
              </div>
            </div>

            <!-- Sprint B · Maturity ladder (waterfall by time-to-due bucket) -->
            <div v-if="creditMaturityLadder.length > 0" class="cw-cred-section">
              <div class="cw-section-label">{{ t("Maturity ladder · по срокам погашения") }}</div>
              <div class="cw-cred-ladder">
                <div
                  v-for="b in creditMaturityLadder"
                  :key="b.key"
                  class="cw-cred-ladder-row"
                  :style="`--accent: ${b.color}`"
                  :title="t('{label}: {n} {u} · {debt}', { label: b.label, n: b.count, u: b.count === 1 ? t('кредит') : t('кредитов'), debt: fmtUsd(b.debt) })"
                >
                  <div class="cw-cred-ladder-label">{{ t(b.label) }}</div>
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
              <div class="cw-section-label">{{ t("Кредиты") }} ({{ creditTopLoans.length }})</div>
              <div class="cw-cred-table">
                <div class="cw-cred-table-header">
                  <div class="cw-cred-th cw-cred-th-code">{{ t("Код") }}</div>
                  <div class="cw-cred-th cw-cred-th-bank">{{ t("Банк / Кредитор") }}</div>
                  <div class="cw-cred-th cw-cred-th-cur">{{ t("Вал.") }}</div>
                  <div class="cw-cred-th cw-cred-th-rate">{{ t("Ставка") }}</div>
                  <div class="cw-cred-th cw-cred-th-debt">{{ t("Задолж. $") }}</div>
                  <div class="cw-cred-th cw-cred-th-due">{{ t("Погашение") }}</div>
                </div>
                <div
                  v-for="l in creditTopLoans"
                  :key="l.id"
                  class="cw-cred-row"
                  :class="{ 'cw-cred-row-overdue': l.is_overdue }"
                >
                  <div class="cw-cred-cell cw-cred-cell-code">
                    {{ l.loan_code }}
                    <span v-if="l.is_guaranteed" class="cw-cred-guaranteed" :title="t('Гарантированный')">G</span>
                  </div>
                  <div class="cw-cred-cell cw-cred-cell-bank" :title="l.bank">
                    <span class="cw-cred-lender-pill" :style="`background: ${l.lender_color}22; color: ${l.lender_color}`">
                      {{ t(l.lender_label) }}
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

        <!-- ═══ PROCUREMENT TAB — real implementation ═══ -->
        <div v-else-if="activeTab === 'procurement'" :key="'procurement'" class="cw-proc-scroll">
          <!-- Форензик-аудит компании (из /forensic/overview) — показываем даже
               если закупок в анализе нет -->
          <section v-if="!procLoading && !procError && procForensic" class="cw-forensic">
            <div class="cw-forensic-head">
              <span class="cw-forensic-title">{{ t("Форензик-аудит") }}</span>
              <RouterLink to="/procurement/forensic" class="cw-forensic-link">{{ t("Полный аудит →") }}</RouterLink>
            </div>
            <div class="cw-forensic-grid">
              <div class="cw-forensic-cell">
                <div class="cw-forensic-label">{{ t("Статус аудита") }}</div>
                <span class="cw-forensic-badge"
                      :style="{ background: fForensicBadge(procForensic.forensic).bg, color: fForensicBadge(procForensic.forensic).fg }">
                  {{ fForensicBadge(procForensic.forensic).text }}
                </span>
              </div>
              <div class="cw-forensic-cell">
                <div class="cw-forensic-label">{{ t("План закупок") }}</div>
                <span class="cw-forensic-badge"
                      :style="{ background: fPlanBadge(procForensic.plan).bg, color: fPlanBadge(procForensic.plan).fg }">
                  {{ fPlanBadge(procForensic.plan).text }}
                </span>
              </div>
              <div class="cw-forensic-cell">
                <div class="cw-forensic-label">{{ t("Аудитор") }}</div>
                <!-- 1:1 как на /consultants: бейдж фирменного цвета, тёмное имя,
                     чип «Big 4» — и только если консультант реально из четвёрки -->
                <span v-if="procForensic.auditor" class="cw-forensic-aud">
                  <!-- Точка фирменного цвета, а не бейдж с аббревиатурой: рядом
                       стоит полное имя, и «KPMG KPMG» читалось как дубль. -->
                  <span class="cw-forensic-aud-dot" :style="{ background: fAud(procForensic.auditor).color }"></span>
                  <span class="cw-forensic-aud-name">{{ fAud(procForensic.auditor).name }}</span>
                  <span v-if="fAud(procForensic.auditor).isBig4" class="cw-big4"
                        :style="big4ChipStyle(fAud(procForensic.auditor).color)">Big 4</span>
                </span>
                <span v-else class="cw-forensic-dash">—</span>
              </div>
              <div class="cw-forensic-cell">
                <div class="cw-forensic-label">{{ t("Годы аудита") }}</div>
                <span class="cw-forensic-years">{{ procForensic.aYears || '—' }}</span>
              </div>
              <div v-if="procForensicYear" class="cw-forensic-cell cw-forensic-pf">
                <div class="cw-forensic-label">{{ t("План / Факт") }} {{ year }}</div>
                <div class="cw-forensic-pf-val">
                  <span>{{ procForensicYear.plan != null ? procForensicYear.plan + ' ' + t('млрд') : '—' }}</span>
                  <span class="cw-forensic-arrow">→</span>
                  <span :style="{ color: (procForensicYear.pct ?? 0) >= 90 ? '#1D9E75' : (procForensicYear.pct ?? 0) >= 70 ? '#D97706' : '#E24B4A' }">
                    {{ procForensicYear.fact != null ? procForensicYear.fact + ' ' + t('млрд') : '—' }}
                    <template v-if="procForensicYear.pct != null"> ({{ procForensicYear.pct }}%)</template>
                  </span>
                </div>
              </div>
            </div>
          </section>

          <UzaStateBlock v-if="procLoading" state="loading" :text="t('Загрузка анализа закупок {year}…', { year })" />

          <UzaStateBlock v-else-if="procError" state="error" variant="block" :title="t('Ошибка загрузки')" :text="procError" retry @retry="loadProc" />

          <UzaStateBlock v-else-if="procPurchases.length === 0" state="empty" variant="block" :title="t('Закупки не загружены')" :text="t('У {name} в {year} году нет данных по закупкам в системе.', { name: localizedCompanyName, year })">
            <template #actions>
              <RouterLink to="/procurement/analysis" class="cw-cta-btn">{{ t("Открыть полный анализ →") }}</RouterLink>
            </template>
          </UzaStateBlock>

          <template v-else>
            <!-- KPI strip -->
            <div v-if="procCompanyKpis" class="cw-proc-kpis kpi-rail">
              <div class="kpi2 fin-shimmer" style="--kpi2-accent:#7F77DD; --kpi2-d:0ms">
                <div class="kpi2-lbl">{{ t("Закрытий") }}</div>
                <div class="kpi2-val"><span :data-countup="procCompanyKpis.total">{{ procCompanyKpis.total }}</span></div>
                <!-- «Отбраковано» звучало как брак в закупке; на деле это строки
                     без сопоставимой рыночной цены (нет медианы по коду) либо с
                     отклонением >1000% — их исключают из ценовых метрик. -->
                <div v-if="procCompanyKpis.dirty > 0" class="kpi2-sub"
                     :title="t('Сравнимые: есть медианная цена по коду товара. Без сравнения: медианы нет или отклонение больше 1000% (цена в 11+ раз от медианы) — такие строки не участвуют в расчёте переплаты и отклонений.')">
                  {{ t("сравнимых: {a} · без сравнения: {b}", { a: procCompanyKpis.clean, b: procCompanyKpis.dirty }) }}
                </div>
              </div>
              <div class="kpi2 fin-shimmer" style="--kpi2-accent:#E24B4A; --kpi2-d:80ms">
                <div class="kpi2-lbl">{{ t("Переплата") }}</div>
                <div class="kpi2-val" style="color: var(--uza-red)">
                  {{ paFmtMoneyShort(procCompanyKpis.totalOverpay) }}
                </div>
                <div class="kpi2-sub">{{ t("UZS, к рынку") }}</div>
              </div>
              <div class="kpi2 fin-shimmer" style="--kpi2-accent:#EF9F27; --kpi2-d:160ms">
                <div class="kpi2-lbl">{{ t("Выше рынка") }}</div>
                <div
                  class="kpi2-val"
                  :style="`color: ${paColorByDev(procCompanyKpis.aboveMarketPct)}`"
                >
                  <span :data-countup="procCompanyKpis.aboveMarketPct">{{ procCompanyKpis.aboveMarketPct }}</span>%
                </div>
                <div class="kpi2-sub">{{ t("закупок > +3%") }}</div>
              </div>
              <div class="kpi2 fin-shimmer" style="--kpi2-accent:#3B82F6; --kpi2-d:240ms">
                <div class="kpi2-lbl">{{ t("Медианное отклон.") }}</div>
                <div
                  class="kpi2-val"
                  :style="`color: ${paColorByDev(procCompanyKpis.medianDev)}`"
                >
                  {{ fmt.fmtPercent(procCompanyKpis.medianDev, { decimals: 1, signed: true }) }}
                </div>
              </div>
              <!-- «Ранг в портфеле» удалён: aggregate вызывался с company_id и
                   ранжировал список из одной компании → всегда #1 (ложь). -->
            </div>

            <!-- Best / Worst categories -->
            <div class="cw-proc-cats-row" v-if="procWorstCats.length > 0 || procBestCats.length > 0">
              <div v-if="procWorstCats.length > 0" class="cw-proc-cats-block">
                <div class="cw-section-label" style="color: var(--uza-red)">
                  {{ t("Проблемные категории") }} · {{ procWorstCats.length }}
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
                      <span class="cw-proc-cat-count">{{ c.closure_count }} {{ t("закр.") }}</span>
                    </div>
                  </div>
                </div>
              </div>
              <div v-if="procBestCats.length > 0" class="cw-proc-cats-block">
                <div class="cw-section-label" style="color: var(--uza-teal)">
                  {{ t("Лучшие категории") }} · {{ procBestCats.length }}
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
                      <span class="cw-proc-cat-count">{{ c.closure_count }} {{ t("закр.") }}</span>
                    </div>
                  </div>
                </div>
              </div>
            </div>

            <!-- Sprint C · Supplier concentration (top-5 share + single-source warning) -->
            <div v-if="procSupplierConcentration.top.length > 0" class="cw-proc-section">
              <div class="cw-section-label">
                {{ t("Концентрация поставщиков · топ-{a} из {b}", { a: procSupplierConcentration.top.length, b: procSupplierConcentration.totalSuppliers }) }}
                <span
                  v-if="procSupplierConcentration.isSingleSource"
                  class="cw-proc-supplier-flag cw-proc-supplier-flag-warn"
                  :title="t('Один поставщик забирает ≥80% объёма — high concentration risk')"
                ><svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" style="vertical-align:-1px;margin-right:3px"><path d="M10.3 4 2 18.3a2 2 0 0 0 1.7 3h16.6a2 2 0 0 0 1.7-3L13.7 4a2 2 0 0 0-3.4 0z"/><line x1="12" y1="9.5" x2="12" y2="13.5"/><line x1="12" y1="17" x2="12.01" y2="17"/></svg>single-source</span>
              </div>

              <!-- Stacked horizontal bar showing top-5 cumulative share -->
              <div class="cw-proc-supplier-bar" :title="t('Топ-5 = {v} от общего объёма', { v: fmt.fmtPercent(procSupplierConcentration.top5Share, { decimals: 1 }) })">
                <div
                  v-for="b in procSupplierConcentration.top"
                  :key="b.supplier"
                  class="cw-proc-supplier-bar-seg"
                  :style="`width: ${b.pct}%; background: ${b.color}`"
                  :title="t('{s} · {pct}% ({n} закр.)', { s: b.supplier, pct: b.pct, n: b.count })"
                ></div>
                <div
                  v-if="procSupplierConcentration.otherMoney > 0"
                  class="cw-proc-supplier-bar-seg cw-proc-supplier-bar-other"
                  :style="`width: ${(100 - procSupplierConcentration.top5Share).toFixed(1)}%`"
                  :title="t('Другие ({n} закр.)', { n: procSupplierConcentration.otherCount })"
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
                    <span :data-countup="b.count" data-cu-d="0">0</span> {{ t("закр.") }}
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
                  <span class="cw-proc-supplier-name">{{ t("Остальные ({n} поставщиков)", { n: procSupplierConcentration.totalSuppliers - procSupplierConcentration.top.length }) }}</span>
                  <span class="cw-proc-supplier-count">{{ procSupplierConcentration.otherCount }} {{ t("закр.") }}</span>
                  <span class="cw-proc-supplier-pct">{{ fmt.fmtPercent(100 - procSupplierConcentration.top5Share, { decimals: 1 }) }}</span>
                </div>
              </div>
            </div>

            <!-- Top deviating purchases -->
            <div class="cw-proc-section">
              <div class="cw-section-label">
                {{ t("Топ-{n} закупок по отклонению от рынка", { n: procRecentPurchases.length }) }}
              </div>
              <div class="cw-proc-purchases">
                <div class="cw-proc-purchases-header">
                  <div class="cw-proc-ph cw-proc-ph-name">{{ t("Товар") }}</div>
                  <div class="cw-proc-ph cw-proc-ph-supplier">{{ t("Поставщик") }}</div>
                  <div class="cw-proc-ph cw-proc-ph-price">{{ t("Цена") }}</div>
                  <div class="cw-proc-ph cw-proc-ph-market">{{ t("Рынок") }}</div>
                  <div class="cw-proc-ph cw-proc-ph-dev">{{ t("Откл.") }}</div>
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
          <!-- Полный разбор компании как в /financials (KPI + ОФР/ОПД/Баланс/ДДС,
               редактирование по годам), но только данные этой компании. Общий
               компонент CompanyDrilldown с /financials → синхронно. Стандарт
               задаёт вкладка (ifrs→МСФО / nsbu→НСБУ), год — степпер воркспейса. -->
          <CompanyDrilldown
            v-if="company"
            variant="embedded"
            :company-code="code"
            :companies="finDrillCompanies"
            :sectors="finDrillSectors"
            :standard="activeTab === 'ifrs' ? 'IFRS' : 'NSBU'"
            :year="year"
            currency="UZS"
          />

          <!-- Исходные файлы отчётности (Excel/PDF) — доп. к разбору -->
          <FinReportUpload
            v-if="company?.id"
            class="cw-fin-upload"
            :company-id="company.id"
            :category="activeTab + '_report'"
            :year="year"
            :can-edit="companiesPerm.canEdit.value"
            :title="t('Загруженные исходные отчёты {std}', { std: finStandardLabel })"
          />
        </div>

        <!-- ═══ HLF TAB — Финансовая отчётность по компаниям (Pack 7.66) ═══ -->
        <div v-else-if="activeTab === 'hlf'" :key="'hlf'" class="cw-hlf-scroll">
          <HighLevelFinancials v-if="company" :companies="[company]" :initial-code="code" />
        </div>

        <!-- ═══ 9 GLOBAL-PAGE PLACEHOLDER TABS ═══ -->
        <div v-else :key="'placeholder-' + activeTab" class="cw-tab-placeholder">
          <div class="cw-cta-card" v-if="currentTabDef">
            <svg class="cw-cta-icon" width="48" height="48" viewBox="0 0 24 24"
                 fill="none" stroke="currentColor" stroke-width="1.5"
                 stroke-linecap="round" stroke-linejoin="round"
                 v-html="getIconPath(currentTabDef.key)"></svg>
            <h2>{{ t(currentTabDef.label) }}</h2>
            <p>{{ t("Раздел «{tab}» для {name}", { tab: t(currentTabDef.label), name: localizedCompanyName }) }}</p>
            <p class="cw-cta-note">
              {{ t("Полная функциональность доступна на глобальной странице.") }}<br>
              {{ t("Фильтрация по компании — в следующих сессиях.") }}
            </p>
            <RouterLink
              v-if="currentTabDef.fullPageRoute"
              :to="currentTabDef.fullPageRoute"
              class="cw-cta-btn"
            >
              {{ t("Открыть полную страницу «{tab}» →", { tab: t(currentTabDef.label) }) }}
            </RouterLink>
          </div>
        </div>
        </Transition>
      </main>

    <!-- v10.1: TaskProjectEditor (editorEntity=null → режим создания) -->
    <TaskProjectEditor
      v-if="editorOpen"
      :entity="(editorEntity as any)"
      :kind="editorKind"
      :company-id="company?.id || null"
      :company-code="(route.params.code as string) || code"
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
        <div class="cw-ov-modal-card" role="dialog" aria-modal="true" :aria-label="t('Просроченные задачи и проекты')">
          <header class="cw-ov-modal-head">
            <div>
              <div class="cw-ov-modal-eyebrow">{{ t("Требуют внимания") }}</div>
              <h3 class="cw-ov-modal-title">
                {{ t("Просрочено") }}: <span class="cw-ov-modal-num">{{ overdueItems.length }}</span>
              </h3>
            </div>
            <button class="cw-ov-modal-close" @click="closeOverdueModal" :title="t('Закрыть')">×</button>
          </header>
          <div class="cw-ov-modal-body">
            <div v-if="overdueItems.length === 0" class="cw-ov-modal-empty">
              {{ t("Просроченных нет — всё по графику.") }}
            </div>
            <ul v-else class="cw-ov-list">
              <li
                v-for="r in overdueItems"
                :key="`${r.kind}-${r.id}`"
                class="cw-ov-row"
                :class="`cw-ov-row-${r.kind}`"
              >
                <div class="cw-ov-row-l">
                  <div class="cw-ov-row-tag">{{ r.kind === "project" ? t("ПРОЕКТ") : t("ЗАДАЧА") }}</div>
                  <div class="cw-ov-row-title">{{ r.title }}</div>
                  <div v-if="r.owner" class="cw-ov-row-owner">{{ r.owner }}</div>
                </div>
                <div class="cw-ov-row-r">
                  <div class="cw-ov-row-days">+{{ r.daysOverdue }} {{ t("дн") }}</div>
                  <div v-if="r.due_date" class="cw-ov-row-date">{{ t("срок") }} {{ fmt.fmtDateNumeric(r.due_date) }}</div>
                  <button
                    type="button"
                    class="cw-ov-row-link"
                    :title="t('Открыть')"
                    @click="openOverdueRow(r)"
                  >→</button>
                </div>
              </li>
            </ul>
          </div>
        </div>
      </div>
    </Transition>

    <!-- ── STATUS DRILL MODAL — проекты+задачи выбранного статуса (премиум) ── -->
    <Transition name="cw-modal">
      <div
        v-if="statusDrillDef"
        class="cw-ov-modal-backdrop"
        @click.self="closeStatusDrill"
      >
        <div
          class="cw-ov-modal-card cw-status-modal-card"
          :style="{ '--st-accent': statusDrillDef.color }"
          role="dialog" aria-modal="true"
          :aria-label="t('{label} — проекты и задачи', { label: t(statusDrillDef.label) })"
        >
          <header class="cw-ov-modal-head">
            <div>
              <div class="cw-ov-modal-eyebrow" :style="{ color: statusDrillDef.color }">
                {{ t("Статус") }} · {{ t(statusDrillDef.sub) }}
              </div>
              <h3 class="cw-ov-modal-title">
                {{ t(statusDrillDef.label) }}: <span class="cw-ov-modal-num">{{ statusDrillRows.length }}</span>
              </h3>
            </div>
            <button class="cw-ov-modal-close" @click="closeStatusDrill" :title="t('Закрыть')">×</button>
          </header>
          <div class="cw-ov-modal-body">
            <div v-if="statusDrillRows.length === 0" class="cw-ov-modal-empty">
              {{ t("Нет элементов в этом статусе.") }}
            </div>
            <ul v-else class="cw-ov-list">
              <li
                v-for="r in statusDrillRows"
                :key="`${r.kind}-${r.id}`"
                class="cw-ov-row cw-ov-row-clickable"
                :class="`cw-ov-row-${r.kind}`"
                @click="openStatusRow(r)"
              >
                <div class="cw-ov-row-l">
                  <div class="cw-ov-row-tag">{{ r.kind === "project" ? t("ПРОЕКТ") : t("ЗАДАЧА") }}</div>
                  <div class="cw-ov-row-title">{{ r.title }}</div>
                  <div v-if="r.owner" class="cw-ov-row-owner">{{ r.owner }}</div>
                </div>
                <div class="cw-ov-row-r">
                  <div v-if="r.progress != null" class="cw-status-row-pct">{{ Math.round(r.progress) }}%</div>
                  <div v-if="r.isOverdue" class="cw-ov-row-days">{{ t("просрочено") }}</div>
                  <div v-if="r.due_date" class="cw-ov-row-date">{{ t("срок") }} {{ fmt.fmtDateNumeric(r.due_date) }}</div>
                  <span class="cw-ov-row-link" aria-hidden="true">→</span>
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
      :company-name="localizedCompanyName"
      :year="year"
      @close="bpEditorOpen = false"
      @saved="onBpEditorSaved"
    />

    <!-- KPI editor modal (lazy-mounted; reuses /kpi editor 1:1) -->
    <KpiEditor
      v-if="kpiEditorOpen && company"
      :company-id="company.id"
      :company-name="localizedCompanyName"
      :year="year"
      @close="kpiEditorOpen = false"
      @saved="onKpiEditorSaved"
    />

    <!-- Governance editor modal — правка показателей + совета директоров.
         Синк с /governance: общий бэкенд, после сейва onGovEditorSaved рефетчит. -->
    <GovernanceEditor
      v-if="govEditorOpen && company"
      :company-id="company.id"
      :company-name="localizedCompanyName"
      :year="govShownYear || year"
      :data="govDetail?.data || null"
      :members="govMembers"
      @close="govEditorOpen = false"
      @saved="onGovEditorSaved"
    />

    <!-- Быстрая hover-карточка члена совета (наведение) -->
    <BoardMemberHoverCard
      :open="bmHoverOpen"
      :member="bmHoverMember as any"
      :anchor="bmHoverAnchor"
      @enter="bmCardEnter"
      @leave="bmCardLeave"
      @open="bmHoverMember && openBoardMember(bmHoverMember)"
    />

    <!-- Всплывающий профиль члена совета директоров (клик) -->
    <BoardMemberProfileModal
      :open="boardMemberModalOpen"
      :member="selectedBoardMember as any"
      :company-name="localizedCompanyName"
      @close="boardMemberModalOpen = false"
    />

    <!-- ESG editor modal — метрики (E/S/G) + риски, синк с /esg -->
    <ESGEditor
      v-if="esgEditorOpen && company"
      :company-id="company.id"
      :company-name="localizedCompanyName"
      :year="esgShownYear || year"
      :detail="esgDetail"
      :issues="esgIssues"
      @close="esgEditorOpen = false"
      @saved="onEsgEditorSaved"
    />
  </div>
</template>

<style scoped>
/* ═══ UzAssets palette ═══ */
.cw-page {
  --uza-purple: #7F77DD;
  --uza-teal:   var(--green);
  --uza-amber:  var(--amber);
  --uza-blue:   var(--blue);
  --uza-red:    var(--sev-high);
  --uza-navy:   #1E2A4A;
  --uza-gray:   var(--t-muted);
  --uza-bg:     #FAFAFB;
  --uza-bg2:    #F5F4F0;
  --uza-bg3:    #EFEEE9;
  --uza-bg4:    #E2E2DC;
  --uza-border: rgba(15, 23, 60, 0.08);

  display: flex;
  flex-direction: column;
  min-height: 100dvh;
  background: var(--uza-bg);
  font-family: ui-sans-serif, system-ui, -apple-system, "Segoe UI", Roboto, sans-serif;
}

/* ═══ Loading & Error ═══ */
.cw-spinner {
  width: 28px; height: 28px;
  border: 2.5px solid var(--uza-bg3);
  border-top-color: var(--uza-purple);
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
}
@keyframes spin { to { transform: rotate(360deg); } }

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
  /* Единый непрерывный navy-градиент с таб-баром: низ этого бара (#0C1430)
     = верх таб-бара → шва не видно, оба читаются как единое целое. */
  background: linear-gradient(180deg, #1B2550 0%, #141D45 100%);
  color: white;
  flex-shrink: 0;
}
.cw-topbar-l, .cw-topbar-r { display: flex; align-items: center; gap: 10px; }
/* 13–14" (≤1440): правая группа контролов уходит во 2-й ряд цельным кластером,
   вторичная мета (хост сайта) прячется — заголовок и сектор-бейдж не теснятся. */
@media (max-width: 1440px) {
  .cw-topbar { flex-wrap: wrap; row-gap: 8px; }
  .cw-topbar-r { flex: 1 1 100%; justify-content: flex-end; }
  .cw-site-link { display: none; }
}

/* Кнопка скрытия/показа главного сайдбара (как в CreditPortfolio/ExecDash). */
.cw-sb-toggle {
  width: 32px; height: 32px;
  border: 1px solid rgba(255, 255, 255, 0.15);
  background: rgba(255, 255, 255, 0.06);
  border-radius: 8px;
  cursor: pointer;
  display: flex; align-items: center; justify-content: center;
  color: rgba(255, 255, 255, 0.7);
  transition: all 0.15s;
  padding: 0;
  flex-shrink: 0;
}
.cw-sb-toggle:hover { background: rgba(255, 255, 255, 0.14); color: #fff; }
.cw-sb-toggle:active { transform: scale(0.94); }

.cw-topbar h1 {
  font-size: 17px; font-weight: 600; margin: 0;
  color: white; letter-spacing: -.015em;
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

/* ─── Минимал-премиум стат-полоса: проекты/задачи · % завершения ─── */
.cw-stat-strip { display: inline-flex; align-items: center; gap: 2px; margin-left: 6px; }
.cw-stat {
  display: inline-flex; align-items: center; gap: 6px;
  background: transparent; border: none; cursor: pointer; font-family: inherit;
  padding: 5px 11px; border-radius: 9px; color: rgba(255, 255, 255, 0.9);
  transition: background 0.14s;
}
.cw-stat:hover { background: rgba(255, 255, 255, 0.08); }
.cw-stat-dot {
  width: 7px; height: 7px; border-radius: 50%; flex-shrink: 0;
  box-shadow: 0 0 0 3px rgba(255, 255, 255, 0.06);
}
.cw-stat-n { font-size: 13.5px; font-weight: 600; font-variant-numeric: tabular-nums; letter-spacing: -0.01em; }
.cw-stat-lbl { font-size: 11.5px; font-weight: 400; color: rgba(255, 255, 255, 0.58); }
.cw-stat-pct { font-size: 11.5px; font-weight: 600; font-variant-numeric: tabular-nums; margin-left: 2px; }
.cw-stat-sep { width: 1px; height: 16px; background: rgba(255, 255, 255, 0.12); margin: 0 3px; }

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

/* Премиум-ссылка на сайт компании */
/* Ссылка на сайт компании — премиум frosted-glass чип на ТЁМНОМ топбаре
   (светлый текст + мягкий брендовый акцент глобуса), хорошо читается. */
.cw-site-link {
  display: inline-flex; align-items: center; gap: 6px;
  height: 26px; padding: 0 11px 0 9px;
  border-radius: 999px;
  background: rgba(255,255,255,.09);
  border: 1px solid rgba(255,255,255,.16);
  color: rgba(255,255,255,.92);
  font-size: 11.5px; font-weight: 600; text-decoration: none;
  max-width: 220px; white-space: nowrap;
  -webkit-backdrop-filter: blur(8px); backdrop-filter: blur(8px);
  box-shadow: inset 0 1px 0 rgba(255,255,255,.08);
  transition: background .16s, border-color .16s, transform .16s, box-shadow .16s, color .16s;
}
.cw-site-link:hover {
  background: rgba(255,255,255,.16);
  border-color: rgba(179,168,255,.55);
  color: #fff;
  transform: translateY(-1px);
  box-shadow: 0 8px 20px -8px rgba(0,0,0,.5), inset 0 1px 0 rgba(255,255,255,.14);
}
.cw-site-link svg { width: 13px; height: 13px; flex-shrink: 0; }
.cw-site-globe { color: #B3A8FF; }   /* мягкий брендовый акцент — заметно, не кричит */
.cw-site-link:hover .cw-site-globe { color: #CFC7FF; }
.cw-site-host { overflow: hidden; text-overflow: ellipsis; letter-spacing: .01em; }
.cw-site-ext { opacity: .6; width: 11px !important; height: 11px !important; transition: transform .16s, opacity .16s; }
.cw-site-link:hover .cw-site-ext { opacity: .95; transform: translate(1px,-1px); }

/* Refresh spin animation */
@keyframes cwSpin { to { transform: rotate(360deg); } }
.cw-spin { animation: cwSpin 0.85s linear infinite; transform-origin: 50% 50%; }

/* Notification bell pulse dot */
.cw-bell-btn { position: relative; }
.cw-bell-dot {
  position: absolute;
  top: 2px; right: 2px;
  min-width: 14px; height: 14px; padding: 0 3px;
  background: var(--sev-high);
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

/* Year picker — нейтральный стиль тёмной шапки (как UzaYearStepper tone=dark), без золота */
.cw-year-picker {
  display: inline-flex; align-items: center; gap: 4px;
  background: rgba(255, 255, 255, 0.10);
  border: 1px solid rgba(255, 255, 255, 0.10);
  color: #fff;
  padding: 3px 6px;
  border-radius: 8px;
  font-feature-settings: "tnum";
  transition: background .15s, border-color .15s;
}
.cw-year-picker:hover {
  background: rgba(255, 255, 255, 0.16);
  border-color: rgba(255, 255, 255, 0.18);
}
.cw-yr-arrow {
  background: transparent; border: none; cursor: pointer;
  color: rgba(255, 255, 255, 0.62); font-size: 13px; font-weight: 600;
  width: 20px; height: 20px;
  border-radius: 4px;
  display: flex; align-items: center; justify-content: center;
  transition: background .15s, color .15s;
}
.cw-yr-arrow:hover:not(:disabled) { background: rgba(255, 255, 255, 0.18); color: #fff; }
.cw-yr-arrow:disabled { opacity: 0.35; cursor: not-allowed; }
.cw-yr-label {
  font-size: 11.5px; font-weight: 500;
  padding: 0 4px;
  color: #fff;
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
.cw-add-btn-ghost {
  background: transparent;
  color: var(--uza-purple);
  border: 1px solid rgba(127, 119, 221, 0.45);
  margin-right: 7px;
}
.cw-add-btn-ghost:hover {
  background: rgba(127, 119, 221, 0.10);
  box-shadow: none;
}

/* Переключатель вида «Работа»: Канбан | Список (на тёмном топбаре) */
.cw-viewtoggle {
  display: inline-flex; align-items: center; gap: 2px;
  padding: 2px; border-radius: 9px;
  background: rgba(255, 255, 255, 0.08);
  border: 1px solid rgba(255, 255, 255, 0.12);
  margin-right: 4px;
}
.cw-vt-btn {
  display: inline-flex; align-items: center; gap: 5px;
  padding: 5px 11px; border: none; border-radius: 7px;
  background: transparent; color: rgba(255, 255, 255, 0.62);
  font-size: 11.5px; font-weight: 500; font-family: inherit; cursor: pointer;
  transition: background .15s, color .15s;
}
.cw-vt-btn svg { width: 14px; height: 14px; }
.cw-vt-btn:hover { color: #fff; }
.cw-vt-btn.on {
  background: linear-gradient(135deg, #8B7FF0 0%, #7F77DD 55%, #6C5CE7 100%);
  color: #fff;
  box-shadow: 0 2px 8px rgba(127, 119, 221, 0.4);
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
  animation: cwFadeUp 0.28s var(--ease-standard) both;
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
  animation: kpiCardIn 0.5s var(--ease-standard) both;
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
  color: var(--t1, #1E2A4A);
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
  color: var(--t3, var(--t-muted));
  margin-top: 5px;
  line-height: 1.5;
}
.cw-stats-hero-sub b {
  color: var(--t1, #1E2A4A);
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
  display: flex;
  flex-wrap: wrap;        /* много статусов → перенос на 2-й ряд */
  gap: 8px;
}

/* Статус-плитки — минимализм-премиум. Без «светофора»: нейтральные карточки,
   ПОЛНОЕ имя статуса, число — фокус. Цвет статуса живёт ТОЛЬКО в drill-модалке. */
.cw-st-tile {
  flex: 1 1 124px;
  min-width: 116px;
  display: flex;
  flex-direction: column;
  gap: 4px;
  padding: 11px 13px;
  background: #fff;
  border: 1px solid var(--card-border, rgba(16, 24, 64, .06));
  border-radius: 11px;
  cursor: pointer;
  transition: transform .16s var(--ease-standard), box-shadow .16s ease, border-color .16s ease;
}
.cw-st-tile:hover {
  transform: translateY(-2px);
  border-color: rgba(127, 119, 221, .30);
  box-shadow: 0 8px 18px rgba(15, 23, 60, .10);
}
.cw-st-tile-num {
  font-size: 21px;
  font-weight: 500;
  line-height: 1;
  color: var(--t1, #1E2A4A);
  font-variant-numeric: tabular-nums;
  letter-spacing: -.015em;
}
.cw-st-tile-num-ratio { display: inline-flex; align-items: baseline; }
.cw-st-ratio-sep { color: var(--t3, #94A3B8); margin: 0 2px; font-weight: 400; }
.cw-st-tile-name {
  font-size: 10.5px;
  font-weight: 500;
  line-height: 1.25;
  color: var(--t3, #64748B);
  letter-spacing: .015em;
}

/* Кликабельные герой / пилл — премиум-аффорданс наведения */
.cw-stats-clickable { cursor: pointer; }
.cw-stats-hero-l.cw-stats-clickable { transition: color .16s ease; border-radius: 8px; }
.cw-stats-hero-l.cw-stats-clickable:hover .cw-stats-hero-num { color: #7F77DD; }
.cw-stats-pill.cw-stats-clickable { transition: filter .16s ease, transform .16s ease; }
.cw-stats-pill.cw-stats-clickable:hover { filter: brightness(.95); transform: translateY(-1px); }

/* Статус-модалка: верхняя цветная полоса под цвет статуса + кликабельные строки */
.cw-status-modal-card { position: relative; overflow: hidden; }
.cw-status-modal-card::before {
  content: ""; position: absolute; top: 0; left: 0; right: 0; height: 3px;
  background: var(--st-accent, #7F77DD); z-index: 2;
}
.cw-ov-row-clickable { cursor: pointer; transition: background .14s ease; }
.cw-ov-row-clickable:hover { background: rgba(127, 119, 221, .06); }
.cw-status-row-pct {
  font-size: 10.5px; font-weight: 600; color: #7F77DD;
  font-variant-numeric: tabular-nums;
}
.cw-stats-cell {
  padding: 2px 0;
}
/* 1:1 kit (proposal 17): статус-счётчики 5-колоночной сетки — в боксах .tk-step */
.cw-stats-grid-5 .cw-stats-cell {
  padding: 9px 10px;
  background: var(--bg2, #FAFBFF);
  border: 1px solid var(--card-border, rgba(99, 102, 180, 0.10));
  border-radius: 10px;
}
.cw-stats-cell-label {
  font-size: 9.5px;
  font-weight: 500;
  color: var(--t3, var(--t-muted));
  letter-spacing: 0.06em;
  text-transform: uppercase;
}
.cw-stats-cell-num {
  font-size: 14px;
  font-weight: 500;
  color: var(--t1, #1E2A4A);
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
.cw-stats-results.cw-res-good  .cw-stats-cell-num-ratio { color: var(--green); }
.cw-stats-results.cw-res-info  .cw-stats-cell-num-ratio { color: #7F77DD; }
.cw-stats-results.cw-res-warn  .cw-stats-cell-num-ratio { color: var(--amber); }
.cw-stats-results.cw-res-bad   .cw-stats-cell-num-ratio { color: var(--sev-high); }
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
/* Планшет (≤1023): 4 тайла → 2×2; узкий телефон (≤560) → 1 в ряд. 1fr сжимается
   в контейнер → без горизонтального скролла. */
@media (max-width: 1023px) { .cw-ratings-grid { grid-template-columns: 1fr 1fr; } }
@media (max-width: 560px)  { .cw-ratings-grid { grid-template-columns: 1fr; } }
/* Сами карточки рейтинга вынесены в <RatingTile> (components/Ratings) —
   inline-edit под RBAC ratings.edit + премиум-анимации живут там. */

/* ─── Donut SVG ─── */
.cw-donut-svg { margin: 2px 0; }
.cw-donut-arc {
  transition: stroke-dashoffset 1.1s var(--ease-standard),
              stroke 0.35s ease;
  /* Премиум: бренд-градиент тиал→зелёный + мягкое свечение (вместо плоской заливки). */
  stroke: url(#cwDonutGrad) !important;
  filter: drop-shadow(0 1px 3px rgba(29, 158, 117, 0.28));
}
/* центр доната — navy-число (kit), не цветное */
.cw-donut-svg text { fill: var(--t1, #1E2A4A) !important; }
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
  font-size: 13px; color: var(--green); font-weight: 500;
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
  .cw-topbar { flex-wrap: wrap; gap: 8px; padding: 10px 14px; }
  .cw-grid-4-placeholder, .cw-grid-2-placeholder { grid-template-columns: 1fr; }
}
@media (max-width: 640px) {
  /* Карточный список — узкие поля контейнера + клиренс под нижнюю навигацию */
  .cw-list-scroll { padding: 10px 10px calc(64px + env(safe-area-inset-bottom)); }
  .cw-kanban-scroll { padding: 10px 12px calc(64px + env(safe-area-inset-bottom)); }
  .cw-overview-scroll { padding: 12px 12px calc(64px + env(safe-area-inset-bottom)); }
}

/* Reduced motion */
@media (prefers-reduced-motion: reduce) {
  .cw-hero, .cw-spinner {
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
/* ═══ KANBAN — 1:1 с легасиом #kanban / .kol / .card (index.html:2165) ═══ */
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
  transition: border-color .12s, background .12s, box-shadow .12s;
}
/* drop-target highlight when dragging a card over a standard column */
.kol--drag-over {
  border-color: var(--col-accent, #7F77DD);
  background: rgba(127, 119, 221, .05);
  box-shadow:
    0 0 0 2px var(--col-accent, #7F77DD) inset,
    0 6px 16px rgba(15, 23, 60, .1);
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
  color: var(--t1, #1E2A4A);
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
  overflow-x: auto;  /* широкая таблица скроллится, а не обрезается на 13–14" */
  padding: 16px 20px;
}
.cw-cal-scroll {
  flex: 1;
  overflow-y: auto;
  padding: 18px 22px;
}
.cw-cal-notes {
  margin-top: 26px;
  padding-top: 22px;
  border-top: 1px solid rgba(15, 23, 60, 0.08);
}
.cw-cal-notes-h {
  font-size: 13px;
  font-weight: 600;
  letter-spacing: -0.01em;
  color: var(--t1, #1E2A4A);
  margin-bottom: 12px;
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
  animation: cwCtaIn 0.4s var(--ease-standard) both;
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
  color: var(--t3, #94A3B8) !important;
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

.cw-pmo-scroll {
  flex: 1;
  overflow-y: auto;
  overflow-x: auto;
  padding: 16px 20px;
}
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
  animation: kpiSumIn 0.4s var(--ease-standard) both;
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
  animation: kpiSumIn 0.4s var(--ease-standard) both;
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
  animation: uzaStripeDrawIn .4s var(--ease-standard) both;
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
  color: var(--t3, #94A3B8);
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
  transition: width 600ms var(--ease-standard);
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
  color: var(--t1, #1E2A4A);
  animation: cwBaselineSlide .35s var(--ease-standard) both;
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
.cw-kpi-baseline-text b { font-weight: 600; color: var(--p-deep); }

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
  color: var(--t1, #1E2A4A);
}
.cw-kpi-ind-baseline-vs {
  margin-left: auto;
  font-size: 10px;
  color: var(--t3, var(--t-muted));
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
}
/* Карточка = канон .kpi2 (стекло + 3px ::before + shimmer). Здесь только то,
   что канон не задаёт: внутренний блок План/Факт/Выполнение. */
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

.cw-gov-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}
.cw-gov-notice { flex: 1; }
.cw-gov-edit-btn {
  flex-shrink: 0;
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 8px 16px;
  border-radius: 9px;
  border: 1px solid rgba(124, 111, 247, 0.30);
  background: rgba(124, 111, 247, 0.08);
  color: var(--p-deep, #534AB7);
  font-size: 12.5px;
  font-weight: 600;
  font-family: inherit;
  cursor: pointer;
  transition: all 0.14s;
}
.cw-gov-edit-btn:hover { background: rgba(124, 111, 247, 0.16); transform: translateY(-1px); }

.cw-gov-kpis {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
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
.cw-gov-committee-mtg {
  margin-left: 2px;
  font-size: 11px;
  font-weight: 600;
  font-variant-numeric: tabular-nums;
  padding: 0 6px;
  border-radius: 999px;
  background: rgba(15, 23, 60, .08);
  color: inherit;
}
.cw-gov-committee-on .cw-gov-committee-mtg {
  background: rgba(29, 158, 117, .18);
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
  transition: background 200ms, transform .16s var(--ease-standard), box-shadow .16s, border-color .16s;
  border: 1px solid transparent;
  animation: cwGovMemberIn .4s var(--ease-standard) both;
  animation-delay: calc(var(--d, 0) * 45ms);
}
.cw-gov-member:hover {
  background: var(--uza-bg3);
}
@keyframes cwGovMemberIn { from { opacity: 0; transform: translateY(8px); } to { opacity: 1; transform: none; } }

/* Кликабельная карточка члена совета → всплывающий профиль */
.cw-gov-member--click { cursor: pointer; position: relative; }
.cw-gov-member--click:hover {
  transform: translateY(-2px);
  box-shadow: 0 10px 24px -12px rgba(40, 32, 80, 0.28);
  border-color: rgba(124, 111, 247, 0.35);
}
.cw-gov-member--click:focus-visible {
  outline: none;
  border-color: var(--p, #7C6FF7);
  box-shadow: 0 0 0 3px rgba(124, 111, 247, 0.18);
}
.cw-gov-member-chev {
  width: 16px; height: 16px; flex-shrink: 0; align-self: center;
  color: var(--uza-bg4, #C9C6DA);
  opacity: 0; transform: translateX(-4px);
  transition: opacity .16s, transform .16s, color .16s;
}
.cw-gov-member--click:hover .cw-gov-member-chev,
.cw-gov-member--click:focus-visible .cw-gov-member-chev {
  opacity: 1; transform: translateX(0); color: var(--p, #7C6FF7);
}

/* Аналитика состава совета — полоски долей */
.cw-gov-comp { display: flex; flex-direction: column; gap: 13px; }
.cw-gov-comp-bar {
  animation: cwGovMemberIn .42s var(--ease-standard) both;
  animation-delay: calc(var(--d, 0) * 70ms);
}
.cw-gov-comp-hd {
  display: flex; align-items: baseline; justify-content: space-between; gap: 10px;
  margin-bottom: 6px;
}
.cw-gov-comp-l { font-size: 12px; font-weight: 500; color: var(--uza-navy); }
.cw-gov-comp-v {
  font-size: 15px; font-weight: 400; font-variant-numeric: tabular-nums; letter-spacing: -.01em;
}
.cw-gov-comp-pc { font-size: 11px; margin-left: 1px; }
.cw-gov-comp-cnt { font-size: 11px; font-weight: 400; color: var(--uza-gray); margin-left: 6px; }
.cw-gov-comp-track {
  height: 7px; border-radius: 999px; overflow: hidden; background: var(--uza-bg3, #EEEDF4);
}
.cw-gov-comp-fill {
  height: 100%; border-radius: 999px; transform-origin: left;
  animation: cwGovBarFill .8s var(--ease-standard) both;
  animation-delay: calc(0.2s + var(--d, 0) * 70ms);
}
@keyframes cwGovBarFill { from { transform: scaleX(0); } to { transform: scaleX(1); } }
.cw-gov-comp-tenure {
  display: flex; align-items: center; gap: 7px;
  font-size: 12px; color: var(--uza-gray); margin-top: 3px;
  padding-top: 11px; border-top: 1px dashed var(--uza-border);
}
.cw-gov-comp-tenure svg { width: 15px; height: 15px; color: var(--p, #7C6FF7); }
.cw-gov-comp-tenure b { color: var(--uza-navy); font-weight: 500; }
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

/* Удельная себестоимость — вкладка (общая панель с /unit-cost) */
.cw-uc-scroll {
  flex: 1;
  overflow-y: auto;
  padding: 16px 20px;
  display: flex;
  flex-direction: column;
  gap: 14px;
}
.cw-uc-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  flex-wrap: wrap;
}
.cw-uc-bar-t {
  font-size: 12px;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: .04em;
  color: var(--p-deep, #534AB7);
  display: flex;
  align-items: baseline;
  gap: 8px;
}
.cw-uc-bar-t span {
  font-weight: 500;
  text-transform: none;
  letter-spacing: 0;
  color: var(--t3, #94A3B8);
  font-size: 10.5px;
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
  animation: kpiSumIn 0.5s var(--ease-standard) both;
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
.cw-esg-pillar-bench-up   { color: var(--green); background: rgba(29, 158, 117, 0.10); }
.cw-esg-pillar-bench-down { color: var(--sev-high); background: rgba(226, 75, 74, 0.10); }
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
  transition: width 600ms var(--ease-standard);
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

/* ═══ Consultants tab v2 — дизайн как в /consultants ═══ */
.cw-cons2-kpis {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 12px;
}
@media (max-width: 720px) { .cw-cons2-kpis { grid-template-columns: repeat(2, 1fr); } }
.cw-cons2-pctsign { font-size: 16px; color: var(--t3, #94A3B8); font-weight: 400; margin-left: 1px; }

.cw-cons2-card {
  background: var(--bg1, #fff);
  border: 1px solid rgba(0, 0, 0, .05);
  border-radius: 12px;
  overflow: hidden;
  display: flex;
  flex-direction: column;
  animation: cvCardIn .5s var(--ease-standard, ease) both;
}
@keyframes cvCardIn { from { opacity: 0; transform: translateY(8px); } to { opacity: 1; transform: translateY(0); } }
.cw-cons2-h {
  padding: 12px 16px;
  border-bottom: 0.5px solid rgba(0, 0, 0, .06);
  display: flex; align-items: baseline; justify-content: space-between; gap: 8px;
}
.cw-cons2-t { font-size: 13px; font-weight: 600; color: var(--t1, #1E2A4A); text-transform: uppercase; letter-spacing: .04em; }
.cw-cons2-hsub { font-size: 11px; color: var(--t3, #94A3B8); }

.cw-cons2-lhead {
  display: grid; grid-template-columns: minmax(0, 1.9fr) 1.2fr 0.8fr 0.95fr; column-gap: 14px;
  padding: 8px 16px; border-bottom: 0.5px solid rgba(0, 0, 0, .04);
  font-size: 10px; font-weight: 600; color: var(--t3, #94A3B8); letter-spacing: .06em; text-transform: uppercase;
}
.cw-cons2-lhead .r { text-align: right; }

.cw-cons2-row {
  display: grid; grid-template-columns: minmax(0, 1.9fr) 1.2fr 0.8fr 0.95fr; align-items: center; column-gap: 14px;
  padding: 8px 16px 8px 18px; border-bottom: 0.5px solid rgba(0, 0, 0, .04);
  cursor: pointer; transition: background .12s; position: relative; overflow: hidden;
  animation: cvRowIn .3s cubic-bezier(.34, 1.1, .64, 1) both;
}
@keyframes cvRowIn { from { opacity: 0; transform: translateY(4px); } to { opacity: 1; transform: translateY(0); } }
.cw-cons2-row:hover { background: rgba(127, 119, 221, .04); }
.cw-cons2-row.open { background: rgba(127, 119, 221, .05); }
.cw-cons2-stripe { position: absolute; left: 0; top: 0; bottom: 0; width: 2.5px; }

.cw-cons2-name { display: flex; align-items: center; gap: 6px; min-width: 0; overflow: hidden; }
.cw-cons2-chevron { width: 6px; height: 6px; border-right: 1.5px solid var(--t3, #94A3B8); border-bottom: 1.5px solid var(--t3, #94A3B8); transform: rotate(-45deg); transition: transform .2s; flex-shrink: 0; }
.cw-cons2-chevron.open { transform: rotate(45deg); }
.cw-cons2-name-t { font-size: 13px; font-weight: 500; color: var(--t1, #1E2A4A); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.cw-cons2-big4 { font-size: 9px; font-weight: 700; padding: 1px 5px; border-radius: 3px; border: 0.5px solid; letter-spacing: .03em; flex-shrink: 0; }

.cw-cons2-bar-wrap { display: flex; align-items: center; gap: 8px; min-width: 0; }
.cw-cons2-bar { flex: 1; height: 4px; border-radius: 3px; background: rgba(0, 0, 0, .05); overflow: hidden; }
.cw-cons2-bar-fill { height: 100%; border-radius: 3px; transition: width .5s var(--ease-standard, ease); }
.cw-cons2-pct-v { font-size: 12px; font-weight: 600; flex-shrink: 0; font-feature-settings: 'tnum'; min-width: 36px; text-align: right; }
.cw-cons2-num, .cw-cons2-overdue { font-size: 13px; font-feature-settings: 'tnum'; }
.cw-cons2-num { color: var(--t3, #5F5E5A); font-weight: 500; }
.cw-cons2-num.r, .cw-cons2-overdue.r { text-align: right; }
.cw-cons2-overdue { font-weight: 600; }
.cw-cons2-seclabel { padding: 10px 16px 4px; font-size: 10px; font-weight: 600; color: var(--t3, #94A3B8); text-transform: uppercase; letter-spacing: .06em; }

/* инлайн-раскрытие задач консультанта */
.cw-cons2-projects { background: var(--bg2, #FAFAFD); border-bottom: 0.5px solid rgba(0, 0, 0, .04); padding: 4px 16px 8px 30px; }
.cw-cons2-project { display: grid; grid-template-columns: 16px 1fr max-content; align-items: center; gap: 8px; padding: 5px 0; cursor: pointer; border-radius: 6px; transition: background .12s; }
.cw-cons2-project:hover { background: rgba(127, 119, 221, .06); }
.cw-cons2-project-status { display: inline-flex; }
.cw-cons2-project-title { font-size: 12px; color: var(--t2, #4B5468); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.cw-cons2-project-date { font-size: 10.5px; color: var(--t3, #94A3B8); font-variant-numeric: tabular-nums; }
.cw-cons2-project-more { font-size: 10.5px; color: var(--t3, #94A3B8); font-style: italic; padding: 4px 0 2px; }
.cw-cons2-exp-enter-active, .cw-cons2-exp-leave-active { transition: all .2s var(--ease-standard, ease); overflow: hidden; }
.cw-cons2-exp-enter-from, .cw-cons2-exp-leave-to { opacity: 0; max-height: 0; }
.cw-cons2-exp-enter-to, .cw-cons2-exp-leave-from { opacity: 1; max-height: 500px; }

/* ─── KPI strip ─── */
.cw-cons-kpis {
  display: flex;
  align-items: stretch;
  gap: 0;
  background: white;
  border: 0.5px solid var(--uza-border);
  border-radius: 12px;
  padding: 14px 18px;
  animation: kpiSumIn 0.4s var(--ease-standard) both;
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
  animation: kpiSumIn 0.4s var(--ease-standard) both;
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

.cw-cred-scroll {
  flex: 1;
  overflow-y: auto;
  padding: 16px 20px;
  display: flex;
  flex-direction: column;
  gap: 16px;
}

/* Полоса KPI = ряд канонических карточек .kpi2, а не одна карточка с
   вертикальными разделителями: рядом с другими полосами экрана это выглядело
   как отдельный стиль. */
.cw-cred-kpis {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
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
  transition: width 600ms var(--ease-standard);
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
  transition: width 600ms var(--ease-standard);
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
.cw-hlf-scroll {
  flex: 1;
  overflow-y: auto;
  padding: 16px 20px;
}

/* ─── Forensic-аудит карта (procurement-таб) ─── */
.cw-forensic {
  background: var(--card-bg, rgba(255, 255, 255, 0.82));
  border: 1px solid var(--card-border, rgba(99, 102, 180, 0.10));
  border-radius: 14px;
  padding: 14px 16px;
}
.cw-forensic-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 12px;
}
.cw-forensic-title {
  font-size: 10px;
  font-weight: 500;
  text-transform: uppercase;
  letter-spacing: 0.07em;
  color: var(--t3, #64748B);
}
.cw-forensic-link {
  font-size: 11px;
  font-weight: 500;
  color: var(--p, #7C6FF7);
  text-decoration: none;
}
.cw-forensic-link:hover { text-decoration: underline; }
.cw-forensic-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(130px, 1fr));
  gap: 14px;
}
.cw-forensic-cell { display: flex; flex-direction: column; gap: 5px; min-width: 0; }
.cw-forensic-label {
  font-size: 10px;
  font-weight: 500;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  color: var(--t3, #888780);
}
.cw-forensic-badge {
  display: inline-flex;
  align-items: center;
  width: fit-content;
  font-size: 11.5px;
  font-weight: 600;
  padding: 3px 10px;
  border-radius: 7px;
  white-space: nowrap;
}
.cw-forensic-auditor { font-size: 14px; font-weight: 600; }
.cw-forensic-aud { display: inline-flex; align-items: center; gap: 6px; min-width: 0; }
.cw-forensic-aud-dot { width: 8px; height: 8px; border-radius: 50%; flex-shrink: 0; }
.cw-forensic-aud-name {
  font-size: 13px; font-weight: 500; color: var(--t1, #1E2A4A);
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
}
.cw-big4 {
  font-size: 9px; font-weight: 700; letter-spacing: .03em;
  padding: 1px 5px; border-radius: 3px; border: 0.5px solid;
  white-space: nowrap; flex-shrink: 0; line-height: 1.5;
}
.cw-forensic-dash { font-size: 14px; color: var(--t3, #94A3B8); }
.cw-forensic-years { font-size: 13px; font-weight: 500; color: var(--t1, #1E2A4A); }
.cw-forensic-pf { grid-column: 1 / -1; }
.cw-forensic-pf-val {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 14px;
  font-weight: 600;
  color: var(--t1, #1E2A4A);
}
.cw-forensic-arrow { color: var(--t3, #94A3B8); font-weight: 400; }

.cw-proc-kpis {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
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

.cw-fin-year-notice {
  background: rgba(239, 159, 39, 0.10);
  border: 1px solid rgba(239, 159, 39, 0.28);
  color: #92660C;
  font-size: 12.5px;
  font-weight: 500;
  padding: 9px 14px;
  border-radius: 10px;
}

/* ── Sprint A: Financial KPI-strip (МСФО/НСБУ summary tiles) ── */
.cw-fin-kpi-strip {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
  gap: 8px;
  margin-bottom: 12px;
}
.cw-fin-kpi-tile {
  background: var(--bg1, #FFFFFF);
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
  color: var(--t3, var(--t-muted));
  font-weight: 500;
}
.cw-fin-kpi-value {
  font-size: 18px;
  font-weight: 500;
  letter-spacing: -0.02em;
  color: var(--t1, #1E2A4A);
  font-variant-numeric: tabular-nums;
  line-height: 1.1;
  margin-top: 1px;
}
.cw-fin-kpi-unit {
  font-size: 10px;
  font-weight: 400;
  color: var(--t3, var(--t-muted));
  margin-left: 3px;
}
.cw-fin-kpi-hint {
  font-size: 10px;
  color: var(--t3, var(--t-muted));
  margin-top: 1px;
}
.cw-fin-kpi-good { color: var(--green); }
.cw-fin-kpi-info { color: var(--blue); }
.cw-fin-kpi-warn { color: var(--amber); }
.cw-fin-kpi-bad  { color: var(--sev-high); }
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
  animation: kpiSumIn 0.4s var(--ease-standard) both;
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
  .cw-cred-kpis { grid-template-columns: 1fr 1fr; gap: 8px; }
  .cw-cred-table-header, .cw-cred-row { grid-template-columns: 50px 2fr 50px 1fr 80px; }
  .cw-cred-th-rate, .cw-cred-cell-rate { display: none; }
  .cw-proc-cats-row { grid-template-columns: 1fr; }
  .cw-proc-kpis { grid-template-columns: 1fr 1fr; gap: 8px; }
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
  -webkit-backdrop-filter: blur(8px);
  backdrop-filter: blur(8px);
  z-index: 1000;
  display: flex; align-items: center; justify-content: center;
  padding: 24px;
}
.cw-ov-modal-card {
  background: var(--bg1, #FFFFFF);
  border-radius: 14px;
  width: 100%; max-width: 640px;
  max-height: calc(100dvh - 48px);   /* dvh — низ не уезжает под браузерный UI */
  display: flex; flex-direction: column;
  box-shadow: 0 24px 64px rgba(15, 23, 60, 0.18), 0 8px 24px rgba(15, 23, 60, 0.08);
  overflow: hidden;
  animation: uzaModalIn .45s var(--ease-standard);
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
  color: var(--t3, var(--t-muted));
  font-weight: 500;
}
.cw-ov-modal-title {
  font-size: 16px;
  font-weight: 500;
  letter-spacing: -0.01em;
  color: var(--t1, #1E2A4A);
  margin: 4px 0 0 0;
}
.cw-ov-modal-num {
  color: var(--sev-high);
  font-weight: 600;
  font-variant-numeric: tabular-nums;
}
.cw-ov-modal-close {
  background: transparent; border: none; cursor: pointer;
  font-size: 24px; line-height: 1; color: var(--t3, var(--t-muted));
  padding: 0 4px;
  transition: color 120ms;
}
.cw-ov-modal-close:hover { color: var(--t1, #1E2A4A); }
.cw-ov-modal-body {
  flex: 1; overflow-y: auto;
  padding: 8px 0;
}
.cw-ov-modal-empty {
  text-align: center;
  padding: 32px;
  color: var(--t3, var(--t-muted));
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
.cw-ov-row:hover { background: var(--bg2, #FAFAFC); }
.cw-ov-row-l { flex: 1; min-width: 0; }
.cw-ov-row-r {
  display: flex; align-items: center; gap: 12px;
  flex-shrink: 0;
}
.cw-ov-row-tag {
  font-size: 9px;
  letter-spacing: 0.08em;
  font-weight: 600;
  color: var(--t3, var(--t-muted));
  text-transform: uppercase;
}
.cw-ov-row-project .cw-ov-row-tag { color: #7F77DD; }
.cw-ov-row-title {
  font-size: 13px;
  font-weight: 500;
  color: var(--t1, #1E2A4A);
  margin-top: 3px;
  line-height: 1.3;
}
.cw-ov-row-owner {
  font-size: 11px;
  color: var(--t3, var(--t-muted));
  margin-top: 2px;
}
.cw-ov-row-days {
  font-size: 13px;
  font-weight: 600;
  color: var(--sev-high);
  font-variant-numeric: tabular-nums;
}
.cw-ov-row-date {
  font-size: 10px;
  color: var(--t3, var(--t-muted));
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
  border: none;
  background: none;
  cursor: pointer;
  line-height: 1;
  font-family: inherit;
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
    uzaStripeDrawIn .8s var(--ease-standard) 100ms both,
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
