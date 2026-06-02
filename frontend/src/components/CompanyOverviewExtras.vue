<!--
  CompanyOverviewExtras.vue -- 6 блоков для Overview tab Company Workspace.

  Заменяет placeholder-секции (строки 1988-2026 в CompanyWorkspace.vue v8).

  Блоки:
    1. ЭКОНОМ. ЭФФЕКТ -- агрегаты по проектам (count, active, completed, avg progress)
    2. ПО НАПРАВЛЕНИЯМ -- группировка проектов по direction
    3. SECTOR RANKING -- top компаний сектора по composite_score
    4. ВНИМАНИЕ -- overdue badge (получает через prop)
    5. АКТИВНОСТЬ -- последние 5 обновлённых задач (тк audit_logs нет в БД)
    6. KPI · {year} -- managers с прогресс-барами (weighted average)
    7. БП · {year} -- выручка/прибыль план/факт

  Defensive: каждый блок в try/catch, graceful fallback при ошибке/empty.
-->
<script setup lang="ts">
import { ref, computed, reactive, watch, onMounted, onBeforeUnmount, inject } from "vue";
import { useRouter } from "vue-router";
import { useFormatters } from "@/composables/useFormatters";

// Injected from CompanyWorkspace — opens the overdue drill modal on click
const openOverdueModal = inject<(() => void) | null>("openOverdueModal", null);
import { api } from "@/api/client";

const fmt = useFormatters();

const DIRS: { id: string; label: string; color: string }[] = [
  { id: "strategy",    label: "Стратегическое управление",  color: "#1e2787" },
  { id: "finance",     label: "Финансы / риски / аудит",    color: "#D97706" },
  { id: "procurement", label: "Система закупок",            color: "#3B6D11" },
  { id: "orgdev",      label: "Организационное развитие",   color: "#534AB7" },
  { id: "digital",     label: "Цифровизация",               color: "#1D9E75" },
  { id: "operations",  label: "Операционная эффективность", color: "#EF4444" },
  { id: "governance",  label: "Корпоративное управление",   color: "#72243E" },
  { id: "esg",         label: "ESG",                        color: "#1D9E75" },
  { id: "pr",          label: "Связи с общественностью",    color: "#D4537E" },
  { id: "pmo",         label: "PMO",                        color: "#2563EB" },
  { id: "analytics",   label: "Сводный отдел",              color: "#7C3AED" },
];
const _DIRS_BY_ID = new Map(DIRS.map((d) => [d.id, d]));
function _dirMeta(direction: string): { id: string; label: string; color: string } {
  const key = String(direction || "").toLowerCase();
  return _DIRS_BY_ID.get(key) || { id: key, label: direction || "Без направления", color: "#94A3B8" };
}

interface Props {
  companyId: string;
  companyCode?: string;
  sectorId?: string;
  sectorName?: string;
  year: number;
  overdue?: number;
}
const props = withDefaults(defineProps<Props>(), {
  overdue: 0,
  sectorName: "Сектор",
});

// ============================================================
// STATE
// ============================================================
const loading = reactive({
  effect: true,
  dirs: true,
  sector: true,
  activity: true,
  kpi: true,
  bp: true,
});

const errors = reactive<Record<string, string | null>>({
  effect: null,
  dirs: null,
  sector: null,
  activity: null,
  kpi: null,
  bp: null,
});

interface EffectProject {
  id: string;
  title: string;
  plannedUzs: number;
  realizedUzs: number;
  source: string;
}
interface EffectData {
  plannedTotal: number; // UZS
  realizedTotal: number; // UZS
  projectsWithEffect: number;
  totalProjects: number;
  topProjects: EffectProject[];
}
const effectData = ref<EffectData | null>(null);

interface DirRow {
  id: string;
  label: string;
  color: string;
  pPct: number;
  pDone: number;
  pTotal: number;
  tDone: number;
  tTotal: number;
}
const dirsData = ref<DirRow[]>([]);

interface SectorRow {
  code: string;
  name: string;
  score: number;
  grade: string;
  isMine: boolean;
}
const sectorRanking = ref<SectorRow[]>([]);

interface ActivityRow {
  kind: "task_history" | "audit_log" | string;
  ts: string;                  // ISO timestamp
  actor: string;
  action: string;
  field?: string | null;
  old_value?: string | null;
  new_value?: string | null;
  title?: string;              // entity title (task/project)
  entity_id: string;
  entity_type: string;         // 'task' | 'project' | 'comment' | ...
  is_critical: boolean;
  notes?: string;
  http_path?: string | null;
}
const activityData = ref<ActivityRow[]>([]);
const activityAll = ref<ActivityRow[]>([]);
const activityTotal = ref<number>(0);              // honest count from backend
const activityModalOpen = ref(false);
const activityRefreshing = ref(false);             // for spin animation

// ─── Per-widget local year + period overrides ──────────────────────────
// Each widget keeps its own year + period so the user can browse historical
// data without changing the page-level year. They sync to props.year whenever
// it changes (period stays user-controlled).
type Period = "Y" | "Q1" | "Q2" | "Q3" | "Q4";
const PERIODS: Period[] = ["Y", "Q1", "Q2", "Q3", "Q4"];

const kpiYear = ref<number>(props.year);
const bpYear  = ref<number>(props.year);
const kpiPeriod = ref<Period>("Y");
const bpPeriod  = ref<Period>("Y");
watch(() => props.year, (y) => { kpiYear.value = y; bpYear.value = y; });

const KPI_MIN_YEAR = 2020;
const KPI_MAX_YEAR = 2030;
function stepKpiYear(delta: number) {
  const next = kpiYear.value + delta;
  if (next < KPI_MIN_YEAR || next > KPI_MAX_YEAR) return;
  kpiYear.value = next;
}
function stepBpYear(delta: number) {
  const next = bpYear.value + delta;
  if (next < KPI_MIN_YEAR || next > KPI_MAX_YEAR) return;
  bpYear.value = next;
}
watch(kpiYear, () => { loadKpi(); });
watch(bpYear,  () => { loadBp();  });
watch(kpiPeriod, () => { loadKpi(); });
watch(bpPeriod,  () => { loadBp();  });

// Block 4: Требуют внимания — internal list (not relying on parent prop alone)
interface AttentionRow {
  id: string;
  kind: "project" | "task";
  title: string;
  deadline: string | null;
}
interface UpcomingRow { id: string; title: string; deadline: string; daysLeft: number; }
const attentionList = ref<AttentionRow[]>([]);
const attentionTotal = ref(0);
const upcomingList = ref<UpcomingRow[]>([]);
const loadingAttention = ref(true);

function _isDoneStatus(s: any): boolean {
  const v = String(s || "").toLowerCase();
  return v === "done" || v === "completed" || v === "завершено" || v === "выполнено";
}
function _isProject(t: any): boolean {
  if (!t) return false;
  if (t.kind === "project" || t.type === "project") return true;
  if (t.is_project === true) return true;
  if (t.parent_id == null && Array.isArray(t.subtasks) && t.subtasks.length > 0) return true;
  return false;
}
function _parseDate(s: any): Date | null {
  if (!s) return null;
  const d = new Date(s);
  return isNaN(d.getTime()) ? null : d;
}

interface KpiManagerRow {
  title: string;
  role?: string;
  progress: number;
  hasFact: boolean;
  indicators: number;
}
interface KpiData {
  managers: KpiManagerRow[];
  overallProgress: number; // 0-100
  totalManagers: number;
  totalIndicators: number;
  attentionCount: number; // r<0.90 AND weight>=15
  hasAnyFact: boolean;
}
const kpiData = ref<KpiData | null>(null);

interface BpMetric {
  plan: number | null;
  fact: number | null;
  expect: number | null;
  hasPlan: boolean;
  hasFact: boolean;
}
interface BpData {
  revenue: BpMetric;
  opProfit: BpMetric;
  profit: BpMetric;
  // Income side (in addition to revenue)
  finIncome: BpMetric;
  // Expense side (sources for «Расходы» view)
  cogs: BpMetric;
  opExpenses: BpMetric;
  finCost: BpMetric;
  tax: BpMetric;
  overallPct: number | null;
  hasData: boolean;
}
const bpData = ref<BpData | null>(null);

// ─── BP widget view-mode: All / Доходы / Расходы ────────────────
const bpView = ref<"all" | "income" | "expenses">("all");
function setBpView(v: "all" | "income" | "expenses") { bpView.value = v; }
const bpDisplayedMetrics = computed(() => {
  const d = bpData.value;
  if (!d) return [];
  if (bpView.value === "income") {
    return [
      { label: "Выручка",         d: d.revenue,   tone: "income" as const },
      { label: "Фин. доходы",     d: d.finIncome, tone: "income" as const },
      { label: "Опер. прибыль",   d: d.opProfit,  tone: "income" as const },
    ];
  }
  if (bpView.value === "expenses") {
    return [
      { label: "Себестоимость",   d: d.cogs,       tone: "expense" as const },
      { label: "Расходы периода", d: d.opExpenses, tone: "expense" as const },
      { label: "Фин. расходы",    d: d.finCost,    tone: "expense" as const },
      { label: "Налог",           d: d.tax,        tone: "expense" as const },
    ];
  }
  return [
    { label: "Выручка",         d: d.revenue,  tone: "neutral" as const },
    { label: "Опер. прибыль",   d: d.opProfit, tone: "neutral" as const },
    { label: "Чистая прибыль",  d: d.profit,   tone: "neutral" as const },
  ];
});

// ============================================================
// HELPERS
// ============================================================
function _num(x: any): number {
  if (x === null || x === undefined || x === "") return 0;
  const n = Number(x);
  return isNaN(n) ? 0 : n;
}

function _arr(x: any): any[] {
  if (Array.isArray(x)) return x;
  if (x && typeof x === "object") {
    if (Array.isArray(x.items)) return x.items;
    if (Array.isArray(x.data)) return x.data;
    if (Array.isArray(x.results)) return x.results;
    if (Array.isArray(x.records)) return x.records;
  }
  return [];
}

function fmtMoney(n: number, addUnit = true): string {
  if (!n || isNaN(n)) return "—";
  if (addUnit) return fmt.fmtNumberCompact(n, { decimals: 1 });
  const abs = Math.abs(n);
  if (abs >= 1e12) return fmt.fmtNumber(n / 1e12, { decimals: 1, minDecimals: 1 });
  if (abs >= 1e9)  return fmt.fmtNumber(n / 1e9,  { decimals: 1, minDecimals: 1 });
  if (abs >= 1e6)  return fmt.fmtNumber(n / 1e6,  { decimals: 1, minDecimals: 1 });
  if (abs >= 1e3)  return fmt.fmtNumber(n / 1e3,  { decimals: 0 });
  return fmt.fmtNumber(n, { decimals: 0 });
}

// Reactive "now" tick — drives auto-refresh of relative timestamps every 60s
const nowTick = ref(Date.now());

// Sector peer navigation state — for skeleton flash on click
const router = useRouter();
const navigatingTo = ref<string | null>(null);
function navigateToPeer(code: string, isMine: boolean) {
  if (isMine || !code) return;
  navigatingTo.value = code;
  router.push(`/companies/${code}/workspace`).finally(() => {
    setTimeout(() => { navigatingTo.value = null; }, 400);
  });
}

function fmtTimeAgo(iso: string): string {
  if (!iso) return "—";
  // Read nowTick to keep this reactive — every 60s nowTick changes, forcing re-render.
  void nowTick.value;
  return fmt.fmtRelativeTime(iso);
}

function pctClass(pct: number): string {
  if (pct >= 100) return "cox-pct-green";
  if (pct >= 80) return "cox-pct-blue";
  if (pct >= 50) return "cox-pct-amber";
  return "cox-pct-red";
}

function pctColorMono(pct: number): string {
  if (pct >= 60) return "#1D9E75";
  if (pct >= 30) return "#D97706";
  return "#E24B4A";
}

function activityIconColor(status: any): string {
  if (_isDoneStatus(status)) return "#1D9E75";
  const s = String(status || "").toLowerCase();
  if (s === "in_progress" || s === "active") return "#378ADD";
  if (s === "blocked" || s === "overdue") return "#E24B4A";
  if (s === "deferred") return "#7F77DD";
  return "#D97706";
}
function activityIconBg(status: any): string {
  if (_isDoneStatus(status)) return "#DCFCE7";
  const s = String(status || "").toLowerCase();
  if (s === "in_progress" || s === "active") return "rgba(55, 138, 221, 0.10)";
  if (s === "blocked" || s === "overdue") return "#FEE2E2";
  if (s === "deferred") return "#EEEDFE";
  return "#FEF9C3";
}

function pctClassBp(pct: number): string {
  if (pct >= 95) return "cox-pct-green";
  if (pct >= 80) return "cox-pct-amber";
  return "cox-pct-red";
}

function pctClassKpi(pct: number): string {
  if (pct >= 70) return "cox-pct-green";
  if (pct >= 35) return "cox-pct-amber";
  return "cox-pct-red";
}

// Input is already scaled to billions ("млрд"). Number portion routed through fmt.fmtNumber
// for locale-aware digit grouping / decimal separator.
function fmtBp(v: number | null | undefined): string {
  if (v == null || isNaN(v)) return "—";
  const av = Math.abs(v);
  if (av >= 10000) return fmt.fmtNumber(v / 1000, { decimals: 1 }) + " трлн";
  if (av >= 100)   return fmt.fmtNumber(Math.round(v)) + " млрд";
  if (av >= 1)     return fmt.fmtNumber(v, { decimals: 1 }) + " млрд";
  return fmt.fmtNumber(v, { decimals: 2 }) + " млрд";
}

// ============================================================
// LOADERS
// ============================================================
// TODO: брать из year_registry endpoint когда будет
const USD_RATES: Record<number, number> = {
  2024: 12700,
  2025: 12750,
  2026: 13000,
  2027: 13200,
};
const _SANITY_CAP_PER_TASK = 100e12; // 100 трлн UZS

function _getUsdRate(year: number): number {
  return USD_RATES[year] || 12800;
}

function _extractEffect(
  proj: any,
  year: number,
): { plannedUzs: number; realizedUzs: number; source: string } {
  if (!proj) return { plannedUzs: 0, realizedUzs: 0, source: "none" };

  // economicEffect может быть в proj.economicEffect или proj.extra.economicEffect
  const ov =
    (proj.economicEffect && typeof proj.economicEffect === "object"
      ? proj.economicEffect
      : null) ||
    (proj.extra &&
    typeof proj.extra === "object" &&
    proj.extra.economicEffect &&
    typeof proj.extra.economicEffect === "object"
      ? proj.extra.economicEffect
      : null);

  if (!ov) return { plannedUzs: 0, realizedUzs: 0, source: "none" };

  let plannedRaw = parseFloat(ov.plannedValue);
  let realizedRaw = parseFloat(ov.realizedValue);

  // Legacy миграция: value + kind
  if (!isFinite(plannedRaw) && !isFinite(realizedRaw)) {
    const legacy = parseFloat(ov.value);
    if (isFinite(legacy) && legacy > 0) {
      if (ov.kind === "planned") {
        plannedRaw = legacy;
        realizedRaw = 0;
      } else {
        realizedRaw = legacy;
        plannedRaw = 0;
      }
    }
  }

  const planned = isFinite(plannedRaw) ? plannedRaw : 0;
  const realized = isFinite(realizedRaw) ? realizedRaw : 0;

  if (planned <= 0 && realized <= 0) {
    return { plannedUzs: 0, realizedUzs: 0, source: "none" };
  }

  // Unit multiplier
  const mult =
    ov.unit === "трлн"
      ? 1e12
      : ov.unit === "млрд"
        ? 1e9
        : ov.unit === "млн"
          ? 1e6
          : 1;

  let plannedUzs = planned * mult;
  let realizedUzs = realized * mult;

  // USD → UZS
  if (ov.currency === "USD") {
    const rate = _getUsdRate(year);
    plannedUzs *= rate;
    realizedUzs *= rate;
  }

  // Sanity cap
  const maxVal = Math.max(plannedUzs, realizedUzs);
  if (maxVal > _SANITY_CAP_PER_TASK) {
    return { plannedUzs: 0, realizedUzs: 0, source: "sanity_capped" };
  }

  return { plannedUzs, realizedUzs, source: "manual" };
}

// Формат для UZS чисел из эффекта (input in raw UZS, not pre-scaled).
function fmtEffectUzs(v: number): string {
  if (!v || isNaN(v)) return "—";
  const av = Math.abs(v);
  if (av >= 1e12) return fmt.fmtNumber(v / 1e12, { decimals: 1 }) + " трлн";
  if (av >= 1e9)  return fmt.fmtNumber(v / 1e9,  { decimals: 1 }) + " млрд";
  if (av >= 1e6)  return fmt.fmtNumber(Math.round(v / 1e6)) + " млн";
  return fmt.fmtNumber(Math.round(v));
}

// Sprint B · Cumulative econ effect for prior years (shown when current year empty)
interface EffectCumulative { fromYear: number; toYear: number; plannedTotal: number; realizedTotal: number; projectsCount: number; }
const effectCumulative = ref<EffectCumulative | null>(null);

async function loadEffect() {
  loading.effect = true;
  errors.effect = null;
  effectCumulative.value = null;
  try {
    const r = await api.get(
      `/projects?company_id=${props.companyId}&limit=500`,
    );
    const allProjects = _arr(r.data);

    // ── Current year slice ──
    let projects = allProjects;
    if (props.year) {
      projects = projects.filter((p: any) => {
        const py = p.portfolio_year;
        return py == null || py === props.year;
      });
    }

    const totalProjects = projects.length;

    const withEffect: EffectProject[] = [];
    let plannedTotal = 0;
    let realizedTotal = 0;

    for (const p of projects) {
      const eff = _extractEffect(p, props.year);
      if (eff.source === "manual" && (eff.plannedUzs > 0 || eff.realizedUzs > 0)) {
        withEffect.push({
          id: p.id,
          title: p.title || p.name || "—",
          plannedUzs: eff.plannedUzs,
          realizedUzs: eff.realizedUzs,
          source: eff.source,
        });
        plannedTotal += eff.plannedUzs;
        realizedTotal += eff.realizedUzs;
      }
    }

    const topProjects = [...withEffect]
      .sort((a, b) => b.plannedUzs - a.plannedUzs)
      .slice(0, 5);

    effectData.value = {
      plannedTotal,
      realizedTotal,
      projectsWithEffect: withEffect.length,
      totalProjects,
      topProjects,
    };

    // ── Sprint B · Cumulative fallback for empty current year ──
    if (withEffect.length === 0 && props.year) {
      const fromYear = Number(props.year) - 2;
      const toYear   = Number(props.year) - 1;
      let cumPlan = 0, cumReal = 0, cumProjects = 0;
      for (const p of allProjects) {
        const py = (p as any).portfolio_year;
        if (py == null || py < fromYear || py > toYear) continue;
        const eff = _extractEffect(p, py);
        if (eff.source === "manual" && (eff.plannedUzs > 0 || eff.realizedUzs > 0)) {
          cumPlan += eff.plannedUzs;
          cumReal += eff.realizedUzs;
          cumProjects++;
        }
      }
      if (cumProjects > 0) {
        effectCumulative.value = {
          fromYear, toYear,
          plannedTotal: cumPlan,
          realizedTotal: cumReal,
          projectsCount: cumProjects,
        };
      }
    }
  } catch (e: any) {
    errors.effect = e?.message || "Ошибка";
    effectData.value = {
      plannedTotal: 0,
      realizedTotal: 0,
      projectsWithEffect: 0,
      totalProjects: 0,
      topProjects: [],
    };
  } finally {
    loading.effect = false;
  }
}

async function loadDirs() {
  loading.dirs = true;
  errors.dirs = null;
  try {
    // Параллельно: проекты + задачи компании
    const [projRes, taskRes] = await Promise.all([
      api.get(`/projects?company_id=${props.companyId}&limit=500`),
      api.get(`/tasks?company_id=${props.companyId}&limit=500`),
    ]);
    let projects = _arr(projRes.data);
    let tasks = _arr(taskRes.data);

    if (props.year) {
      projects = projects.filter((p: any) => {
        const py = p.portfolio_year;
        return py == null || py === props.year;
      });
      tasks = tasks.filter((t: any) => {
        const py = t.portfolio_year ?? t.year;
        return py == null || py === props.year;
      });
    }

    // Stats per direction
    const merged = DIRS.map((dir) => {
      const pSlice = projects.filter((p: any) => String(p.direction || "").toLowerCase() === dir.id);
      const tSlice = tasks.filter((t: any) => String(t.direction || "").toLowerCase() === dir.id);
      const pDone = pSlice.filter((p: any) => _isDoneStatus(p.status)).length;
      const tDone = tSlice.filter((t: any) => _isDoneStatus(t.status)).length;
      const pTotal = pSlice.length;
      const tTotal = tSlice.length;
      const pPct = pTotal ? Math.round((pDone / pTotal) * 100) : 0;
      return { id: dir.id, label: dir.label, color: dir.color, pPct, pDone, pTotal, tDone, tTotal };
    }).filter((d) => d.pTotal > 0 || d.tTotal > 0)
      .sort((a, b) => b.pPct - a.pPct);

    dirsData.value = merged;
  } catch (e: any) {
    errors.dirs = e?.message || "Ошибка";
    dirsData.value = [];
  } finally {
    loading.dirs = false;
  }
}

// Block 4: Требуют внимания · реальный список из overdue tasks/projects + Дедлайны
// Фильтр по props.year — как в loadDirs/loadEffect (portfolio_year или дедлайн в этом году).
async function loadAttention() {
  loadingAttention.value = true;
  try {
    const [projRes, taskRes] = await Promise.all([
      api.get(`/projects?company_id=${props.companyId}&limit=500`),
      api.get(`/tasks?company_id=${props.companyId}&limit=500`),
    ]);
    let projects = _arr(projRes.data);
    let tasks = _arr(taskRes.data);

    // Year scope: portfolio_year matches OR deadline falls within the selected year
    if (props.year) {
      const inYear = (item: any) => {
        const py = item.portfolio_year ?? item.year;
        if (py != null) return py === props.year;
        const dl = _parseDate(item.deadline || item.due_date);
        return dl ? dl.getFullYear() === props.year : false;
      };
      projects = projects.filter(inYear);
      tasks = tasks.filter(inYear);
    }

    const today = new Date();
    today.setHours(0, 0, 0, 0);

    const allItems: { id: string; kind: "project" | "task"; title: string; deadline: Date | null; rawDl: string | null; status: any }[] = [];
    for (const p of projects) {
      allItems.push({
        id: String(p.id),
        kind: "project",
        title: String(p.title || p.name || "—"),
        deadline: _parseDate(p.deadline || p.due_date),
        rawDl: p.deadline || p.due_date || null,
        status: p.status,
      });
    }
    for (const t of tasks) {
      allItems.push({
        id: String(t.id),
        kind: _isProject(t) ? "project" : "task",
        title: String(t.title || t.name || "—"),
        deadline: _parseDate(t.deadline || t.due_date),
        rawDl: t.deadline || t.due_date || null,
        status: t.status,
      });
    }

    // Просрочены: deadline < today AND status != done
    const overdueItems = allItems
      .filter((x) => x.deadline && x.deadline < today && !_isDoneStatus(x.status))
      .sort((a, b) => (a.deadline!.getTime() - b.deadline!.getTime()));
    attentionTotal.value = overdueItems.length;
    attentionList.value = overdueItems.slice(0, 5).map((x) => ({
      id: x.id, kind: x.kind, title: x.title, deadline: x.rawDl,
    }));

    // Дедлайны: следующие 3 в течение 30 дней (status != done)
    const horizon = new Date(today.getTime() + 30 * 86_400_000);
    const upcoming = allItems
      .filter((x) => x.deadline && x.deadline >= today && x.deadline <= horizon && !_isDoneStatus(x.status))
      .sort((a, b) => a.deadline!.getTime() - b.deadline!.getTime())
      .slice(0, 3);
    upcomingList.value = upcoming.map((x) => ({
      id: x.id,
      title: x.title,
      deadline: x.rawDl || "",
      daysLeft: Math.max(0, Math.ceil((x.deadline!.getTime() - today.getTime()) / 86_400_000)),
    }));
  } catch {
    attentionList.value = [];
    upcomingList.value = [];
    attentionTotal.value = 0;
  } finally {
    loadingAttention.value = false;
  }
}

function fmtUpcoming(days: number): string {
  if (days <= 7) return days + " дн.";
  if (days <= 30) return Math.ceil(days / 7) + " нед.";
  return Math.ceil(days / 30) + " мес.";
}
function upcomingColor(days: number): string {
  if (days <= 7) return "#E24B4A";
  if (days <= 14) return "#D97706";
  return "rgba(30, 42, 74, 0.55)";
}

async function loadSector() {
  loading.sector = true;
  errors.sector = null;
  try {
    // Пиры сектора берём из /companies (id/code/sector_id), а ПРОГРЕСС (%
    // выполнения задач) — из dashboard completion.by_company[].progress_pct.
    // Раньше тянулся overall_score из /ratings, которого там нет (рейтинги —
    // кредитные грейды) → score всегда 0 → виджет показывал «—».
    const [rCo, rDash] = await Promise.all([
      api.get(`/companies`),
      api.get(`/dashboard/shareholder`, { params: { year: props.year } }).catch(() => null),
    ]);
    const allCompanies = _arr(rCo.data);

    // code(lower) → progress_pct
    const progressByCode = new Map<string, number>();
    const byCompany = _arr((rDash as any)?.data?.completion?.by_company);
    for (const row of byCompany) {
      const code = String(row.code || "").toLowerCase();
      if (code) progressByCode.set(code, _num(row.progress_pct));
    }

    // /companies list-item имеет sector_code/sector_name (НЕ sector_id и НЕ
    // вложенный sector). Прошлый фильтр сравнивал несуществующие c.sector_id /
    // c.sector → undefined===undefined → проходили ВСЕ компании (глобальный
    // топ-5 из разных секторов). Фильтруем строго по sector_code своей компании.
    const myComp = allCompanies.find((cc: any) => cc.id === props.companyId);
    const mySectorCode = String(myComp?.sector_code || "").toLowerCase();
    if (!mySectorCode) {
      sectorRanking.value = [];
      return;
    }
    const sectorMatches = allCompanies.filter(
      (c: any) => String(c.sector_code || "").toLowerCase() === mySectorCode,
    );

    if (sectorMatches.length === 0) {
      sectorRanking.value = [];
      return;
    }

    sectorRanking.value = sectorMatches
      .map((c: any) => ({
        code: c.code,
        name: c.name_short || c.name_ru || c.code,
        score: progressByCode.get(String(c.code || "").toLowerCase()) ?? 0,
        grade: "",
        isMine: c.id === props.companyId,
      }))
      .sort((a, b) => b.score - a.score)
      .slice(0, 5);
  } catch (e: any) {
    errors.sector = e?.message || "Ошибка";
  } finally {
    loading.sector = false;
  }
}

async function loadActivity(opts: { silent?: boolean } = {}) {
  if (!opts.silent) loading.activity = true;
  errors.activity = null;
  try {
    if (!props.companyCode) {
      activityData.value = [];
      activityAll.value = [];
      activityTotal.value = 0;
      return;
    }
    activityRefreshing.value = true;
    const r = await api.get(`/companies/${props.companyCode}/activity`, {
      params: { limit: 40, days: 14 },
    });
    const items: ActivityRow[] = (r.data?.items || []) as ActivityRow[];
    activityAll.value = items;
    activityData.value = items.slice(0, 5);
    activityTotal.value = Number(r.data?.total_available || items.length);
  } catch (e: any) {
    if (e?.response?.status === 403) {
      activityData.value = [];
      activityAll.value = [];
      activityTotal.value = 0;
    } else {
      errors.activity = e?.response?.data?.detail || e?.message || "Ошибка";
    }
  } finally {
    loading.activity = false;
    activityRefreshing.value = false;
  }
}

async function refreshActivity() {
  if (activityRefreshing.value) return;
  await loadActivity({ silent: true });
}

function openActivityModal() { activityModalOpen.value = true; }
function closeActivityModal() { activityModalOpen.value = false; }

// ─── Reactivity: re-load when the parent switches to a different company.
// Without this, navigating between SOEs shows STALE data of the previously
// loaded company until the entire view is remounted.
watch(
  () => props.companyCode,
  (newVal, oldVal) => {
    if (newVal !== oldVal && newVal) loadActivity();
  },
);

// Click-to-navigate from an activity row → board-kanban with taskId/projectId query.
// For `comment` events we stored entity_id = PARENT task/project UUID, but we
// don't know which kind from entity_type alone — try task first, fall back to project.
function openEntity(it: ActivityRow) {
  if (!it.entity_id) return;
  if (it.entity_type === "task" || it.entity_type === "comment") {
    router.push({ name: "board-kanban", query: { taskId: it.entity_id } });
  } else if (it.entity_type === "project") {
    router.push({ name: "board-kanban", query: { projectId: it.entity_id } });
  }
  // Other entity types (mfa_attempt / user_session / etc.) — no nav.
}

function isClickable(it: ActivityRow): boolean {
  return (it.entity_type === "task" || it.entity_type === "project"
       || it.entity_type === "comment") && !!it.entity_id;
}

// Human labels for technical field names (used by `field_updated` task_history rows).
const FIELD_LABELS: Record<string, string> = {
  assignee_email:  "ответственного",
  assignee_name:   "ответственного",
  assignee_id:     "ответственного",
  status:          "статус",
  priority:        "приоритет",
  title:           "название",
  description:     "описание",
  due_date:        "срок",
  start_date:      "дату начала",
  progress_percent: "прогресс",
  direction_id:    "направление",
  board_id:        "доску",
  result_at:       "результат",
  // Company fields
  name_ru:         "название",
  name_short:      "короткое название",
  sector_code:     "сектор",
  legal_form:      "форму собственности",
  inn:             "ИНН",
  status_ru:       "статус",
};

// Verb portion of "<module>.<verb>" actions
const VERB_MAP: Record<string, string> = {
  create:    "создал",
  created:   "создал",
  update:    "обновил",
  updated:   "обновил",
  delete:    "удалил",
  deleted:   "удалил",
  uploaded:  "загрузил",
  approved:  "утвердил",
  rejected:  "отклонил",
  submitted: "отправил",
  published: "опубликовал",
  assigned:  "назначил",
  revoked:   "отозвал",
  restored:  "восстановил",
  archived:  "архивировал",
  replied:   "ответил",
  read:      "прочитал",
  view:      "просмотрел",
};

// Domain noun for "<module>" portion in accusative form
const MODULE_NOUN: Record<string, string> = {
  tasks:       "задачу",
  projects:    "проект",
  companies:   "компанию",
  kpi:         "KPI",
  bp:          "бизнес-план",
  ratings:     "рейтинг",
  esg:         "ESG",
  governance:  "корп. управление",
  procurement: "закупку",
  credit:      "кредит",
  comments:    "комментарий",
  attachments: "файл",
  rbac:        "права",
  auth:        "аккаунт",
  moderation:  "запрос на модерацию",
  broadcasts:  "рассылку",
};

function activityActionLabel(it: ActivityRow): string {
  // Exact matches first (task_history actions)
  const exact: Record<string, string> = {
    status_changed: "сменил статус",
    archived:       "архивировал",
    unarchived:     "восстановил из архива",
    result_set:     "отметил результат",
    result_cleared: "снял результат",
    CREATE:         "создал",
    UPDATE:         "обновил",
    DELETE:         "удалил",
    VIEW:           "просмотрел",
    FAILED:         "ошибка доступа",
  };
  const action = it.action || "";

  // task_history field updates → "изменил <field-label>"
  if (action === "field_updated") {
    const f = it.field || "";
    const label = FIELD_LABELS[f] || (f ? `поле «${f}»` : "поле");
    return `изменил ${label}`;
  }
  if (action in exact) return exact[action];
  if (action.startsWith("login.")) return "вход";

  // Namespaced "<module>.<verb>" → combine
  if (action.includes(".")) {
    const [module, verb] = action.split(".", 2);
    const verbRu = VERB_MAP[verb] || verb;
    const nounRu = MODULE_NOUN[module];
    if (nounRu && VERB_MAP[verb]) return `${verbRu} ${nounRu}`;
    if (VERB_MAP[verb]) return verbRu;
  }
  return action || "—";
}

function activityActionColor(it: ActivityRow): string {
  if (it.is_critical) return "#E24B4A";
  const a = it.action || "";
  if (a === "DELETE" || a === "archived" || a.endsWith(".deleted") || a.endsWith(".archived")) return "#EF9F27";
  if (a === "CREATE" || a === "result_set" || a.endsWith(".created") || a.endsWith(".approved") || a.endsWith(".uploaded")) return "#1D9E75";
  if (a === "FAILED" || a.startsWith("FAIL") || a.endsWith(".rejected")) return "#E24B4A";
  return "#7F77DD";
}

function activityEntityKindRu(t: string): string {
  const map: Record<string, string> = {
    task:                  "Задача",
    project:               "Проект",
    comment:               "Комментарий",
    kpi_submission:        "KPI",
    bp_submission:         "Бизнес-план",
    moderation_submission: "Модерация",
    user:                  "Пользователь",
    user_session:          "Сессия",
    mfa_attempt:           "MFA",
    company:               "Компания",
    broadcast:             "Рассылка",
    attachment:            "Файл",
  };
  return map[t] || (t || "—");
}

// Compact diff string for the 5-row preview — e.g. "new → done"
function shortDiff(it: ActivityRow): string | null {
  if (it.kind !== "task_history") return null;
  const ov = it.old_value;
  const nv = it.new_value;
  if (ov == null || nv == null) return null;
  const sov = String(ov).slice(0, 20);
  const snv = String(nv).slice(0, 20);
  return `${sov} → ${snv}`;
}

async function loadKpi() {
  loading.kpi = true;
  errors.kpi = null;
  try {
    const r = await api.get(`/kpi/${props.companyId}/${kpiYear.value}`);
    const data = r.data;
    let managers: any[] = [];
    if (data?.managers) managers = _arr(data.managers);
    else if (Array.isArray(data)) managers = data;
    else managers = _arr(data);

    // Period-driven field selection: "Y" → plan_year/fact_year,
    // "Q1".."Q4" → qN_plan/qN_fact. Weight is annual-only.
    const periodKey = kpiPeriod.value;
    const planField = periodKey === "Y" ? "plan_year" : `${periodKey.toLowerCase()}_plan`;
    const factField = periodKey === "Y" ? "fact_year" : `${periodKey.toLowerCase()}_fact`;

    let totW = 0;
    let wSum = 0;
    let totalInd = 0;
    let attCount = 0;
    const mgrs: KpiManagerRow[] = [];

    for (const m of managers) {
      const indicators = _arr(m.indicators);
      let mW = 0;
      let mS = 0;
      let mHasFact = false;

      for (const i of indicators) {
        const p = i[planField] != null ? _num(i[planField]) : null;
        const f = i[factField] != null ? _num(i[factField]) : null;
        const w = _num(i.weight);
        totalInd++;

        if (p != null && p !== 0 && f != null) {
          const r = Math.min(2, f / p);
          wSum += r * w;
          totW += w;
          mS += r * w;
          mW += w;
          mHasFact = true;
          if (r < 0.9 && w >= 15) attCount++;
        } else if (p != null) {
          totW += w;
          mW += w;
        }
      }

      mgrs.push({
        title: m.short_title || m.title || "—",
        role: m.role,
        progress: mW ? Math.round((mS / mW) * 100) : 0,
        hasFact: mHasFact,
        indicators: indicators.length,
      });
    }

    const overallProgress = totW ? Math.round((wSum / totW) * 100) : 0;
    const hasAnyFact = mgrs.some((m) => m.hasFact);

    kpiData.value = {
      managers: mgrs.slice(0, 6),
      overallProgress,
      totalManagers: mgrs.length,
      totalIndicators: totalInd,
      attentionCount: attCount,
      hasAnyFact,
    };
  } catch (e: any) {
    errors.kpi = e?.message || "Ошибка";
    kpiData.value = {
      managers: [],
      overallProgress: 0,
      totalManagers: 0,
      totalIndicators: 0,
      attentionCount: 0,
      hasAnyFact: false,
    };
  } finally {
    loading.kpi = false;
  }
}

// Sprint B · Prior-year BP fallback — shown when current year is empty
interface BpBaseline { year: number; revenue: number | null; opProfit: number | null; profit: number | null; }
const bpBaseline = ref<BpBaseline | null>(null);

// Backend GET /bp/raw/{co}/{year} returns a dict-of-dicts:
//   { "annual": { "revenue": {plan, expect, fact}, "cogs": {...}, ... },
//     "q1": {...}, "q2": {...}, ... }
// `bpPeriod` UI value "Y" → "annual" in storage; "Q1".."Q4" → "q1".."q4".
function _bpPeriodKey(uiPeriod: string): string {
  const p = (uiPeriod || "").toUpperCase();
  return p === "Y" ? "annual" : p.toLowerCase();
}

function _pickBpCell(
  data: any, periodKey: string, metric: string,
): { plan: number | null; expect: number | null; fact: number | null } {
  if (!data || typeof data !== "object") return { plan: null, expect: null, fact: null };
  // Try the exact DB key first ("annual"), then legacy ("Y") that old dumps used.
  const periodDict = data[periodKey] || data[periodKey.toUpperCase()] || data["Y"] || null;
  const cell = periodDict?.[metric];
  if (!cell || typeof cell !== "object") return { plan: null, expect: null, fact: null };
  return {
    plan:   cell.plan   != null ? _num(cell.plan)   : null,
    expect: cell.expect != null ? _num(cell.expect) : null,
    fact:   cell.fact   != null ? _num(cell.fact)   : null,
  };
}

async function _fetchBpForYear(y: number) {
  const r = await api.get(`/bp/raw/${props.companyId}/${y}`);
  const data = r.data;
  return {
    revenue:  _pickBpCell(data, "annual", "revenue").fact,
    opProfit: _pickBpCell(data, "annual", "opProfit").fact,
    profit:   _pickBpCell(data, "annual", "profit").fact,
  };
}

async function loadBp() {
  loading.bp = true;
  errors.bp = null;
  bpBaseline.value = null;
  try {
    const r = await api.get(`/bp/raw/${props.companyId}/${bpYear.value}`);
    const data = r.data;
    const periodKey = _bpPeriodKey(bpPeriod.value);

    function getMetric(metricKey: string): BpMetric {
      const c = _pickBpCell(data, periodKey, metricKey);
      return {
        plan: c.plan,
        fact: c.fact,
        expect: c.expect,
        hasPlan: c.plan != null,
        hasFact: c.fact != null,
      };
    }

    const revenue    = getMetric("revenue");
    const opProfit   = getMetric("opProfit");
    const profit     = getMetric("profit");
    const finIncome  = getMetric("finIncome");
    const cogs       = getMetric("cogs");
    const opExpenses = getMetric("opExpenses");
    const finCost    = getMetric("finCost");
    const tax        = getMetric("tax");

    let overallPct: number | null = null;
    if (
      revenue.plan != null &&
      revenue.plan !== 0 &&
      revenue.fact != null
    ) {
      overallPct = Math.round((revenue.fact / revenue.plan) * 100);
    }

    const hasData =
      revenue.hasPlan || revenue.hasFact ||
      opProfit.hasPlan || opProfit.hasFact ||
      profit.hasPlan || profit.hasFact ||
      cogs.hasPlan || opExpenses.hasPlan;

    bpData.value = {
      revenue, opProfit, profit,
      finIncome, cogs, opExpenses, finCost, tax,
      overallPct, hasData,
    };

    // Sprint B · If current year is empty, fetch prev year's facts as baseline
    if (!hasData) {
      const prevY = bpYear.value - 1;
      try {
        const prevFacts = await _fetchBpForYear(prevY);
        if (prevFacts.revenue != null || prevFacts.opProfit != null || prevFacts.profit != null) {
          bpBaseline.value = { year: prevY, ...prevFacts };
        }
      } catch {
        // baseline is best-effort, ignore failure
      }
    }
  } catch (e: any) {
    errors.bp = e?.message || "Ошибка";
    const blank: BpMetric = { plan: null, fact: null, expect: null, hasPlan: false, hasFact: false };
    bpData.value = {
      revenue: blank, opProfit: blank, profit: blank,
      finIncome: blank, cogs: blank, opExpenses: blank, finCost: blank, tax: blank,
      overallPct: null,
      hasData: false,
    };
  } finally {
    loading.bp = false;
  }
}

// ============================================================
// LIFECYCLE
// ============================================================
async function loadAll() {
  await Promise.allSettled([
    loadEffect(),
    loadDirs(),
    loadSector(),
    loadActivity(),
    loadAttention(),
    loadKpi(),
    loadBp(),
  ]);
}

let nowTickInterval: number | null = null;
onMounted(() => {
  loadAll();
  nowTickInterval = window.setInterval(() => {
    nowTick.value = Date.now();
  }, 60_000);
});
onBeforeUnmount(() => {
  if (nowTickInterval != null) {
    clearInterval(nowTickInterval);
    nowTickInterval = null;
  }
});
watch(
  () => [props.companyId, props.year],
  () => {
    if (props.companyId) loadAll();
  },
);
</script>

<template>
  <div class="cox-root">
    <!-- ============================================================ -->
    <!-- 1. ЭКОНОМ. ЭФФЕКТ -- из ручного ввода в карточках проектов -->
    <!-- ============================================================ -->
    <section class="cox-section cox-effect">
      <div class="cox-section-label">
        Эконом. эффект · {{ year }}
        <span
          v-if="effectData && effectData.projectsWithEffect > 0"
          class="cox-card-sub"
        >
          {{ effectData.projectsWithEffect }} / {{ effectData.totalProjects }}
          проектов с эффектом
        </span>
      </div>
      <div v-if="loading.effect" class="cox-loading">
        <div class="cox-spinner-sm"></div>
        <span>Извлечение эффекта из карточек проектов...</span>
      </div>
      <!-- Есть эффект -->
      <div
        v-else-if="effectData && effectData.projectsWithEffect > 0"
        class="cox-effect-block"
      >
        <div class="cox-effect-stats">
          <div class="cox-effect-stat">
            <div class="cox-effect-stat-cap">План</div>
            <div class="cox-effect-stat-num">
              {{ fmtEffectUzs(effectData.plannedTotal) }}
            </div>
          </div>
          <div class="cox-effect-stat" data-color="green">
            <div class="cox-effect-stat-cap">Факт</div>
            <div class="cox-effect-stat-num">
              {{ fmtEffectUzs(effectData.realizedTotal) }}
            </div>
          </div>
          <div
            v-if="effectData.plannedTotal > 0"
            class="cox-effect-stat"
            data-color="purple"
          >
            <div class="cox-effect-stat-cap">Выполнение</div>
            <div
              class="cox-effect-stat-num"
              :class="
                pctClassBp(
                  Math.round((effectData.realizedTotal / effectData.plannedTotal) * 100),
                )
              "
            >
              {{ Math.round((effectData.realizedTotal / effectData.plannedTotal) * 100) }}%
            </div>
          </div>
        </div>
        <!-- Top-5 проектов по эффекту -->
        <div v-if="effectData.topProjects.length" class="cox-effect-tops">
          <div class="cox-effect-tops-label">Топ проектов по эффекту:</div>
          <div
            v-for="p in effectData.topProjects"
            :key="p.id"
            class="cox-effect-top-row"
          >
            <span class="cox-effect-top-title">{{ p.title }}</span>
            <span class="cox-effect-top-vals">
              <span class="cox-effect-top-val">
                <span class="cox-effect-top-cap">план</span>
                {{ fmtEffectUzs(p.plannedUzs) }}
              </span>
              <span v-if="p.realizedUzs > 0" class="cox-effect-top-val">
                <span class="cox-effect-top-cap">факт</span>
                {{ fmtEffectUzs(p.realizedUzs) }}
              </span>
            </span>
          </div>
        </div>
      </div>
      <!-- Нет проектов с введённым эффектом -->
      <div
        v-else-if="effectData && effectData.totalProjects > 0"
        class="cox-effect-empty"
      >
        <svg
          width="20"
          height="20"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          stroke-width="1.5"
        >
          <path d="M3 17l6-6 4 4 8-8" stroke-linecap="round" stroke-linejoin="round" />
          <circle cx="3" cy="17" r="1.5" fill="currentColor" />
          <circle cx="21" cy="7" r="1.5" fill="currentColor" />
        </svg>
        <div>
          <div class="cox-effect-empty-title">
            Нет проектов с введённым эффектом
          </div>
          <div class="cox-effect-empty-hint">
            Эконом. эффект указывается вручную в карточке проекта/задачи
            ({{ effectData.totalProjects }}
            {{
              effectData.totalProjects === 1 ? "проект" : effectData.totalProjects < 5 ? "проекта" : "проектов"
            }} в {{ year }} году)
          </div>

          <!-- Sprint B · Cumulative fallback for empty current year -->
          <div v-if="effectCumulative" class="cox-effect-cum">
            <div class="cox-effect-cum-tag">
              ↻ Накопленный эффект {{ effectCumulative.fromYear }}–{{ effectCumulative.toYear }}
            </div>
            <div class="cox-effect-cum-grid">
              <div class="cox-effect-cum-cell">
                <span class="cox-effect-cum-cap">План</span>
                <span class="cox-effect-cum-num">{{ fmtEffectUzs(effectCumulative.plannedTotal) }}</span>
              </div>
              <div v-if="effectCumulative.realizedTotal > 0" class="cox-effect-cum-cell">
                <span class="cox-effect-cum-cap">Факт</span>
                <span class="cox-effect-cum-num">{{ fmtEffectUzs(effectCumulative.realizedTotal) }}</span>
              </div>
              <div class="cox-effect-cum-cell">
                <span class="cox-effect-cum-cap">Проектов</span>
                <span class="cox-effect-cum-num">{{ effectCumulative.projectsCount }}</span>
              </div>
            </div>
          </div>
        </div>
      </div>
      <div v-else class="cox-empty-line">Нет проектов за {{ year }} год</div>
    </section>

    <!-- ============================================================ -->
    <!-- 2-5. Grid 4: По направлениям | Sector | Внимание | Активность -->
    <!-- ============================================================ -->
    <section class="cox-grid-4">
      <!-- 2. По направлениям -->
      <div class="cox-card">
        <div class="cox-card-label">По направлениям</div>
        <div v-if="loading.dirs" class="cox-loading-line">Загрузка...</div>
        <template v-else-if="dirsData.length > 0">
          <div class="cox-dir-head">
            <span class="cox-dir-stripe-slot"></span>
            <span class="cox-dir-name-slot"></span>
            <span class="cox-dir-bar-slot"></span>
            <span class="cox-dir-pct-slot"></span>
            <span class="cox-dir-num-head">Проекты</span>
            <span class="cox-dir-num-head">Задачи</span>
          </div>
          <div class="cox-dirs-list">
            <div
              v-for="d in dirsData"
              :key="d.id"
              class="cox-dir-row"
              :title="`${d.label}: проекты ${d.pDone}/${d.pTotal} (${d.pPct}%) · задачи ${d.tDone}/${d.tTotal}`"
            >
              <span class="cox-dir-stripe" :style="{ background: d.color }"></span>
              <span class="cox-dir-name">{{ d.label }}</span>
              <span class="cox-dir-bar">
                <span class="cox-dir-bar-fill"
                      :style="{ width: Math.min(100, d.pPct) + '%', background: pctColorMono(d.pPct) }"></span>
              </span>
              <span class="cox-dir-pct" :style="{ color: pctColorMono(d.pPct) }">{{ d.pPct }}%</span>
              <span class="cox-dir-num">{{ d.pDone }}/{{ d.pTotal }}</span>
              <span class="cox-dir-num">{{ d.tDone }}/{{ d.tTotal }}</span>
            </div>
          </div>
        </template>
        <div v-else class="cox-empty-line">Нет направлений</div>
      </div>

      <!-- 3. Sector ranking -->
      <div class="cox-card">
        <div class="cox-card-label">{{ sectorName }}</div>
        <div v-if="loading.sector" class="cox-loading-line">Загрузка...</div>
        <div v-else-if="sectorRanking.length > 0" class="cox-rank-list">
          <div
            v-for="(s, i) in sectorRanking"
            :key="s.code"
            class="cox-rank-row"
            :class="{
              'cox-rank-mine': s.isMine,
              'cox-rank-clickable': !s.isMine,
              'cox-rank-loading': navigatingTo === s.code,
            }"
            :title="s.isMine ? 'Текущая компания' : `Открыть «${s.name}»`"
            @click="navigateToPeer(s.code, s.isMine)"
          >
            <span class="cox-rank-pos">{{ i + 1 }}</span>
            <span class="cox-rank-name">{{ s.name }}</span>
            <span
              v-if="navigatingTo === s.code"
              class="cox-rank-spinner"
              aria-label="Загрузка"
            ></span>
            <span
              v-else
              class="cox-rank-pct"
              :style="{ color: pctColorMono(s.score) }"
            >
              {{ s.score > 0 ? Math.round(s.score) + '%' : '—' }}
            </span>
          </div>
        </div>
        <div v-else class="cox-empty-line">Нет данных по сектору</div>
      </div>

      <div class="cox-card">
        <div class="cox-card-label">
          Требуют внимания
          <span v-if="attentionTotal > 0" class="cox-attention-badge">{{ attentionTotal }}</span>
        </div>
        <div v-if="loadingAttention" class="cox-loading-line">Загрузка...</div>
        <template v-else>
          <div v-if="attentionList.length === 0 && upcomingList.length === 0" class="cox-attn-ok">
            Просроченных нет
          </div>
          <div v-if="attentionList.length > 0" class="cox-attn-list">
            <div
              v-for="item in attentionList"
              :key="item.kind + ':' + item.id"
              class="cox-attn-row"
            >
              <span class="cox-attn-dot"></span>
              <span class="cox-attn-badge" :class="`cox-attn-badge-${item.kind}`">
                {{ item.kind === "project" ? "ПРОЕКТ" : "ЗАДАЧА" }}
              </span>
              <span class="cox-attn-title" :title="item.title">
                {{ item.title.length > 26 ? item.title.slice(0, 24) + "…" : item.title }}
              </span>
              <span v-if="item.deadline" class="cox-attn-deadline">{{ item.deadline }}</span>
            </div>
            <div
              v-if="attentionTotal > attentionList.length && openOverdueModal"
              class="cox-attn-more"
              @click="openOverdueModal && openOverdueModal()"
            >
              Показать все ({{ attentionTotal }}) →
            </div>
          </div>
          <div v-if="upcomingList.length > 0" class="cox-attn-upcoming">
            <div class="cox-attn-upcoming-h">Дедлайны</div>
            <div
              v-for="u in upcomingList"
              :key="u.id"
              class="cox-attn-upcoming-row"
            >
              <span class="cox-attn-upcoming-days" :style="{ color: upcomingColor(u.daysLeft) }">
                {{ fmtUpcoming(u.daysLeft) }}
              </span>
              <span class="cox-attn-upcoming-title" :title="u.title">
                {{ u.title.length > 28 ? u.title.slice(0, 26) + "…" : u.title }}
              </span>
            </div>
          </div>
        </template>
      </div>

      <!-- 5. Активность — task_history + audit_log объединены. Источник:
           GET /companies/{code}/activity. 5 свежих в виджете, кнопка «Все»
           открывает модалку с полным списком. -->
      <div class="cox-card">
        <div class="cox-card-label cox-card-label-row">
          <span>Активность</span>
          <div class="cox-activity-head-actions">
            <button
              class="cox-activity-refresh"
              :class="{ 'is-spin': activityRefreshing }"
              :disabled="activityRefreshing"
              @click="refreshActivity"
              title="Обновить"
              aria-label="Обновить"
            >
              <svg width="11" height="11" viewBox="0 0 24 24" fill="none"
                   stroke="currentColor" stroke-width="2"
                   stroke-linecap="round" stroke-linejoin="round">
                <polyline points="23 4 23 10 17 10"/>
                <polyline points="1 20 1 14 7 14"/>
                <path d="M3.51 9a9 9 0 0114.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0020.49 15"/>
              </svg>
            </button>
            <button
              v-if="activityAll.length > 0"
              class="cox-activity-all-btn"
              @click="openActivityModal"
            >
              Все ({{ activityTotal || activityAll.length }}) →
            </button>
          </div>
        </div>
        <div v-if="loading.activity" class="cox-loading-line">Загрузка...</div>
        <div v-else-if="errors.activity" class="cox-empty-line">{{ errors.activity }}</div>
        <div
          v-else-if="activityData.length > 0"
          class="cox-activity-list"
        >
          <div
            v-for="(a, i) in activityData"
            :key="i"
            class="cox-activity-row"
            :class="{ 'is-clickable': isClickable(a) }"
            @click="isClickable(a) && openEntity(a)"
          >
            <div
              class="cox-activity-icon"
              :style="{ background: activityActionColor(a) + '1F', color: activityActionColor(a) }"
              :title="a.actor + ' — ' + activityActionLabel(a)"
            >
              <svg width="12" height="12" viewBox="0 0 16 16" fill="none" stroke="currentColor"
                   stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round">
                <path d="M3 8l3 3 7-7"/>
              </svg>
            </div>
            <div class="cox-activity-body">
              <div class="cox-activity-title" :title="a.title || activityActionLabel(a)">
                {{ a.title || activityActionLabel(a) }}
              </div>
              <div class="cox-activity-meta">
                <span>{{ activityEntityKindRu(a.entity_type) }}</span>
                <span class="cox-activity-meta-sep">·</span>
                <span>{{ activityActionLabel(a) }}</span>
                <span v-if="shortDiff(a)" class="cox-activity-meta-diff">{{ shortDiff(a) }}</span>
                <span class="cox-activity-time">{{ fmtTimeAgo(a.ts) }}</span>
              </div>
            </div>
          </div>
        </div>
        <div v-else class="cox-empty-line">Нет записей</div>
      </div>
    </section>

    <!-- ─── Модалка «Вся активность» ─── -->
    <div
      v-if="activityModalOpen"
      class="cox-act-modal-backdrop"
      @click.self="closeActivityModal"
    >
      <div class="cox-act-modal">
        <header class="cox-act-modal-h">
          <div class="cox-act-modal-title">Активность · последние 14 дней</div>
          <button class="cox-act-modal-close" @click="closeActivityModal" aria-label="Закрыть">×</button>
        </header>
        <div class="cox-act-modal-body">
          <ul v-if="activityAll.length > 0" class="cox-act-full-list">
            <li
              v-for="(it, i) in activityAll"
              :key="i"
              class="cox-act-full-item"
              :class="{ 'is-clickable': isClickable(it) }"
              @click="isClickable(it) && (closeActivityModal(), openEntity(it))"
            >
              <span class="cox-act-full-dot" :style="{ background: activityActionColor(it) }"></span>
              <div class="cox-act-full-row">
                <div class="cox-act-full-line1">
                  <span class="cox-act-full-actor">{{ it.actor }}</span>
                  <span class="cox-act-full-action">{{ activityActionLabel(it) }}</span>
                  <span v-if="it.title" class="cox-act-full-target" :title="it.title">{{ it.title }}</span>
                </div>
                <div class="cox-act-full-line2">
                  <span class="cox-act-full-ts">{{ fmtTimeAgo(it.ts) }}</span>
                  <span v-if="it.entity_type" class="cox-act-full-kind">{{ activityEntityKindRu(it.entity_type) }}</span>
                  <span v-if="it.kind === 'task_history' && it.old_value && it.new_value"
                        class="cox-act-full-diff"
                        :title="`${it.old_value} → ${it.new_value}`">
                    {{ String(it.old_value).slice(0, 30) }} → {{ String(it.new_value).slice(0, 30) }}
                  </span>
                </div>
              </div>
            </li>
          </ul>
          <div v-else class="cox-empty-line">Нет активности</div>
        </div>
      </div>
    </div>

    <!-- ============================================================ -->
    <!-- 6-7. Grid 2: KPI · {year} | Бизнес-план · {year} -->
    <!-- ============================================================ -->
    <section class="cox-grid-2">
      <!-- 6. KPI -->
      <div class="cox-card cox-card-tall">
        <div class="cox-card-label cox-card-label-row">
          <span class="cox-card-label-left">
            <span>KPI ·</span>
            <span class="cox-year-switcher">
              <button class="cox-year-arrow" @click="stepKpiYear(-1)"
                      :disabled="kpiYear <= 2020" aria-label="Предыдущий год">‹</button>
              <span class="cox-year-val">{{ kpiYear }}</span>
              <button class="cox-year-arrow" @click="stepKpiYear(1)"
                      :disabled="kpiYear >= 2030" aria-label="Следующий год">›</button>
            </span>
            <span class="cox-period-switcher">
              <button v-for="p in PERIODS" :key="p"
                      class="cox-period-btn"
                      :class="{ active: kpiPeriod === p }"
                      @click="kpiPeriod = p">{{ p }}</button>
            </span>
          </span>
          <span
            v-if="kpiData && kpiData.totalManagers > 0"
            class="cox-card-sub"
          >
            {{ kpiData.totalManagers }} рук. ·
            {{ kpiData.totalIndicators }} показателей
            <span
              v-if="kpiData.attentionCount > 0"
              class="cox-attention-inline"
            >
              · {{ kpiData.attentionCount }} требуют внимания
            </span>
          </span>
        </div>
        <div v-if="loading.kpi" class="cox-loading-line">Загрузка KPI...</div>
        <div
          v-else-if="kpiData && kpiData.managers.length > 0"
          class="cox-kpi-block"
        >
          <div
            v-if="kpiData.hasAnyFact"
            class="cox-kpi-summary"
          >
            <div
              class="cox-kpi-summary-num"
              :class="pctClassKpi(kpiData.overallProgress)"
            >
              {{ kpiData.overallProgress }}%
            </div>
            <div class="cox-kpi-summary-cap">общий прогресс</div>
          </div>
          <div v-else class="cox-kpi-no-fact">
            Факт не введён ни по одному показателю
          </div>
          <div class="cox-kpi-managers">
            <div
              v-for="(m, i) in kpiData.managers"
              :key="i"
              class="cox-kpi-manager"
              :style="{ animationDelay: `${i * 50}ms` }"
            >
              <div class="cox-kpi-manager-head">
                <span class="cox-kpi-manager-title">{{ m.title }}</span>
                <span
                  v-if="m.hasFact"
                  class="cox-kpi-manager-pct"
                  :class="pctClassKpi(m.progress)"
                >
                  {{ m.progress }}%
                </span>
                <span v-else class="cox-kpi-manager-pct cox-kpi-empty">—</span>
              </div>
              <div
                class="cox-kpi-bar-track"
                :title="m.hasFact
                  ? `${m.title}: выполнение ${m.progress}%${m.attentionCount ? ' · ' + m.attentionCount + ' требуют внимания' : ''}`
                  : `${m.title}: факт не введён`"
              >
                <div
                  v-if="m.hasFact"
                  class="cox-kpi-bar-fill"
                  :class="pctClassKpi(m.progress)"
                  :style="{ width: Math.min(100, m.progress) + '%' }"
                ></div>
              </div>
              <div v-if="m.role" class="cox-kpi-manager-role">{{ m.role }}</div>
            </div>
          </div>
        </div>
        <div v-else class="cox-empty-line">
          Нет KPI данных за {{ year }}
        </div>
      </div>

      <!-- 7. Бизнес-план -->
      <div class="cox-card cox-card-tall">
        <div class="cox-card-label cox-card-label-row">
          <span class="cox-card-label-left">
            <span>Бизнес-план ·</span>
            <span class="cox-year-switcher">
              <button class="cox-year-arrow" @click="stepBpYear(-1)"
                      :disabled="bpYear <= 2020" aria-label="Предыдущий год">‹</button>
              <span class="cox-year-val">{{ bpYear }}</span>
              <button class="cox-year-arrow" @click="stepBpYear(1)"
                      :disabled="bpYear >= 2030" aria-label="Следующий год">›</button>
            </span>
            <span class="cox-bp-view-switcher">
              <button class="cox-bp-view-btn"
                      :class="{ active: bpView === 'all' }"
                      @click="setBpView('all')"
                      title="Выручка / Опер. прибыль / Чистая прибыль">Все</button>
              <button class="cox-bp-view-btn cox-bp-view-btn-inc"
                      :class="{ active: bpView === 'income' }"
                      @click="setBpView('income')"
                      title="Выручка / Фин. доходы / Опер. прибыль">Доходы</button>
              <button class="cox-bp-view-btn cox-bp-view-btn-exp"
                      :class="{ active: bpView === 'expenses' }"
                      @click="setBpView('expenses')"
                      title="Себестоимость / Расходы / Фин.расходы / Налог">Расходы</button>
            </span>
            <span class="cox-period-switcher">
              <button v-for="p in PERIODS" :key="p"
                      class="cox-period-btn"
                      :class="{ active: bpPeriod === p }"
                      @click="bpPeriod = p">{{ p }}</button>
            </span>
          </span>
          <span
            v-if="bpData && bpData.overallPct != null"
            class="cox-card-sub-pct"
            :class="pctClassBp(bpData.overallPct)"
          >
            {{ bpData.overallPct }}%
          </span>
        </div>
        <div v-if="loading.bp" class="cox-loading-line">Загрузка БП...</div>
        <div
          v-else-if="bpData && bpData.hasData"
          class="cox-bp-block"
        >
          <!-- Динамические строки: переключаются по bpView (Все/Доходы/Расходы) -->
          <template v-for="m in bpDisplayedMetrics" :key="m.label">
            <div class="cox-bp-row">
              <div class="cox-bp-row-head">
                <span class="cox-bp-row-label">{{ m.label }}</span>
                <span
                  v-if="m.d.hasPlan && m.d.hasFact && m.d.plan !== 0"
                  class="cox-bp-row-pct"
                  :class="pctClassBp(Math.round((m.d.fact / m.d.plan) * 100))"
                >
                  {{ Math.round((m.d.fact / m.d.plan) * 100) }}%
                </span>
                <span v-else class="cox-bp-row-pct cox-bp-empty">—</span>
              </div>
              <div class="cox-bp-vals">
                <div class="cox-bp-val">
                  <span class="cox-bp-val-cap">план</span>
                  <span class="cox-bp-val-num" :class="{ 'cox-bp-empty': !m.d.hasPlan }">
                    {{ m.d.hasPlan ? fmtBp(m.d.plan) : '—' }}
                  </span>
                </div>
                <div class="cox-bp-val">
                  <span class="cox-bp-val-cap">факт</span>
                  <span class="cox-bp-val-num cox-bp-fact" :class="{ 'cox-bp-empty': !m.d.hasFact }">
                    {{ m.d.hasFact ? fmtBp(m.d.fact) : '—' }}
                  </span>
                </div>
                <div v-if="m.d.expect != null" class="cox-bp-val">
                  <span class="cox-bp-val-cap">ожид.</span>
                  <span class="cox-bp-val-num">{{ fmtBp(m.d.expect) }}</span>
                </div>
              </div>
              <div
                class="cox-bp-bar-track"
                :title="m.d.hasPlan && m.d.hasFact && m.d.plan !== 0
                  ? `${m.label}: план ${fmtBp(m.d.plan)} · факт ${fmtBp(m.d.fact)} · ${Math.round((m.d.fact / m.d.plan) * 100)}% · Δ ${fmtBp((m.d.fact ?? 0) - (m.d.plan ?? 0))}`
                  : `${m.label}: план ${m.d.hasPlan ? fmtBp(m.d.plan) : '—'} · факт ${m.d.hasFact ? fmtBp(m.d.fact) : 'не введён'}`"
              >
                <div
                  v-if="m.d.hasPlan && m.d.hasFact && m.d.plan !== 0"
                  class="cox-bp-bar-fill"
                  :class="pctClassBp(Math.round((m.d.fact / m.d.plan) * 100))"
                  :style="{ width: Math.min(100, Math.max(0, Math.round((m.d.fact / m.d.plan) * 100))) + '%' }"
                ></div>
              </div>
            </div>
          </template>
        </div>
        <!-- Sprint B · Prior-year baseline (gray reference values when current empty) -->
        <div v-else-if="bpBaseline" class="cox-bp-baseline">
          <div class="cox-bp-baseline-head">
            <span class="cox-bp-baseline-icon">↻</span>
            <span>Бизнес-план на <b>{{ year }}</b> не заполнен. Факт за <b>{{ bpBaseline.year }}</b>:</span>
          </div>
          <div class="cox-bp-baseline-rows">
            <div v-if="bpBaseline.revenue != null" class="cox-bp-baseline-row">
              <span>Выручка</span>
              <span class="cox-bp-baseline-num">{{ fmtBp(bpBaseline.revenue) }}</span>
            </div>
            <div v-if="bpBaseline.opProfit != null" class="cox-bp-baseline-row">
              <span>Опер. прибыль</span>
              <span class="cox-bp-baseline-num">{{ fmtBp(bpBaseline.opProfit) }}</span>
            </div>
            <div v-if="bpBaseline.profit != null" class="cox-bp-baseline-row">
              <span>Чистая прибыль</span>
              <span class="cox-bp-baseline-num">{{ fmtBp(bpBaseline.profit) }}</span>
            </div>
          </div>
        </div>
        <div v-else class="cox-empty-line">
          Бизнес-план на {{ year }} год не заполнен
        </div>
      </div>
    </section>
  </div>
</template>

<style scoped>
/* ============================================================ */
/* ROOT */
/* ============================================================ */
.cox-root {
  display: flex;
  flex-direction: column;
  gap: 14px;
  margin-top: 8px;
}

/* ============================================================ */
/* SECTION LABELS */
/* ============================================================ */
.cox-section-label,
.cox-card-label {
  font-size: 10px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.07em;
  color: rgba(30, 42, 74, 0.55);
  margin-bottom: 8px;
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}
.cox-card-sub {
  font-size: 9.5px;
  font-weight: 500;
  text-transform: none;
  letter-spacing: 0;
  color: rgba(30, 42, 74, 0.4);
  margin-left: auto;
}

/* ============================================================ */
/* CARDS */
/* ============================================================ */
/* ─── Premium card: lift + gradient glow on hover, top accent strip ─── */
.cox-card {
  position: relative;
  background: var(--bg1, #ffffff);
  border: 1px solid rgba(30, 42, 74, 0.06);
  border-radius: 10px;
  padding: 14px 16px;
  box-shadow: 0 1px 3px rgba(15, 23, 60, 0.04);
  transition:
    transform 0.28s var(--ease-standard),
    box-shadow 0.28s ease,
    border-color 0.2s ease;
  overflow: hidden;
  animation: coxCardIn 0.45s var(--ease-standard) backwards;
}
/* Top accent strip — scaled-in once on mount, becomes visible on hover */
.cox-card::before {
  content: "";
  position: absolute;
  inset: 0 0 auto 0;
  height: 2px;
  background: linear-gradient(90deg, #7F77DD, #5448B7);
  transform: scaleX(0);
  transform-origin: left center;
  transition: transform 0.45s var(--ease-standard);
  border-radius: 10px 10px 0 0;
  opacity: 0;
}
/* Subtle radial glow that lights up on hover */
.cox-card::after {
  content: "";
  position: absolute;
  inset: 0;
  border-radius: inherit;
  background: radial-gradient(circle at 50% 0%, rgba(127, 119, 221, 0.06), transparent 60%);
  opacity: 0;
  transition: opacity 0.28s ease;
  pointer-events: none;
}
.cox-card:hover {
  transform: translateY(-2px);
  box-shadow: 0 10px 28px rgba(15, 23, 60, 0.10), 0 2px 6px rgba(15, 23, 60, 0.04);
  border-color: rgba(127, 119, 221, 0.18);
}
.cox-card:hover::before { transform: scaleX(1); opacity: 1; }
.cox-card:hover::after  { opacity: 1; }

@keyframes coxCardIn {
  0%   { opacity: 0; transform: translateY(10px) scale(0.985); }
  60%  { opacity: 1; transform: translateY(-1px) scale(1.003); }
  100% { opacity: 1; transform: translateY(0)   scale(1); }
}
.cox-card-tall {
  min-height: 280px;
}

/* ============================================================ */
/* GRIDS */
/* ============================================================ */
.cox-grid-4 {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 10px;
}
.cox-grid-2 {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 10px;
}
@media (max-width: 1100px) {
  .cox-grid-4 {
    grid-template-columns: repeat(2, 1fr);
  }
}
@media (max-width: 720px) {
  .cox-grid-4,
  .cox-grid-2 {
    grid-template-columns: 1fr;
  }
}

/* ============================================================ */
/* 1. ЭКОНОМ. ЭФФЕКТ */
/* ============================================================ */
.cox-effect {
  background: linear-gradient(
    135deg,
    rgba(127, 119, 221, 0.04) 0%,
    rgba(29, 158, 117, 0.03) 100%
  );
  border: 1px solid rgba(30, 42, 74, 0.06);
  border-radius: 10px;
  padding: 14px 18px;
}
.cox-effect-block {
  display: flex;
  flex-direction: column;
  gap: 14px;
}
.cox-effect-stats {
  display: flex;
  gap: 32px;
  flex-wrap: wrap;
}
.cox-effect-stat {
  display: flex;
  flex-direction: column;
  gap: 3px;
  min-width: 100px;
}
.cox-effect-stat-cap {
  font-size: 10px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  color: rgba(30, 42, 74, 0.5);
}
.cox-effect-stat-num {
  font-size: 20px;
  font-weight: 500;
  letter-spacing: -0.025em;
  color: var(--t1, #1e2a4a);
  line-height: 1.1;
  font-variant-numeric: tabular-nums;
}
.cox-effect-stat[data-color="green"] .cox-effect-stat-num {
  color: var(--green);
}
.cox-effect-stat[data-color="purple"] .cox-effect-stat-num {
  color: #7f77dd;
}
.cox-effect-tops {
  padding-top: 10px;
  border-top: 1px dashed rgba(30, 42, 74, 0.08);
  display: flex;
  flex-direction: column;
  gap: 5px;
}
.cox-effect-tops-label {
  font-size: 10px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  color: rgba(30, 42, 74, 0.5);
  margin-bottom: 4px;
}
.cox-effect-top-row {
  display: flex;
  align-items: baseline;
  gap: 12px;
  font-size: 12px;
}
.cox-effect-top-title {
  flex: 1;
  color: var(--t1, #1e2a4a);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.cox-effect-top-vals {
  display: flex;
  gap: 14px;
  flex-shrink: 0;
}
.cox-effect-top-val {
  font-variant-numeric: tabular-nums;
  font-weight: 500;
  color: var(--t1, #1e2a4a);
}
.cox-effect-top-cap {
  font-size: 9.5px;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  color: rgba(30, 42, 74, 0.4);
  margin-right: 4px;
  font-weight: 500;
}
.cox-effect-empty {
  display: flex;
  gap: 12px;
  align-items: flex-start;
  padding: 8px 4px;
  color: rgba(30, 42, 74, 0.55);
}
.cox-effect-empty-title {
  font-size: 13px;
  color: var(--t1, #1e2a4a);
  font-weight: 500;
  margin-bottom: 2px;
}
.cox-effect-empty-hint {
  font-size: 11.5px;
  line-height: 1.5;
  color: rgba(30, 42, 74, 0.55);
}

/* Sprint B · Cumulative econ effect fallback */
.cox-effect-cum {
  margin-top: 12px;
  padding: 10px 12px;
  background: rgba(127, 119, 221, 0.06);
  border: 1px dashed rgba(127, 119, 221, 0.3);
  border-radius: 8px;
}
.cox-effect-cum-tag {
  font-size: 10px;
  letter-spacing: 0.04em;
  text-transform: uppercase;
  font-weight: 600;
  color: var(--p-deep);
  margin-bottom: 8px;
}
.cox-effect-cum-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(110px, 1fr));
  gap: 10px;
}
.cox-effect-cum-cell {
  display: flex; flex-direction: column; gap: 2px;
}
.cox-effect-cum-cap {
  font-size: 9.5px;
  letter-spacing: 0.06em;
  text-transform: uppercase;
  color: var(--t3, var(--t-muted));
  font-weight: 500;
}
.cox-effect-cum-num {
  font-size: 14px;
  font-weight: 500;
  font-variant-numeric: tabular-nums;
  color: var(--t1, #1E2A4A);
}

/* ============================================================ */
/* ============================================================ */
.cox-dir-head,
.cox-dir-row {
  display: grid;
  grid-template-columns: 3px minmax(0, 1fr) 44px 28px 56px 56px;
  align-items: center;
  gap: 8px;
}
.cox-dir-head {
  padding: 0 0 4px;
  border-bottom: 0.5px solid rgba(30, 42, 74, 0.06);
}
.cox-dir-num-head {
  font-size: 10px;
  font-weight: 700;
  color: rgba(30, 42, 74, 0.45);
  text-transform: uppercase;
  letter-spacing: 0.06em;
  text-align: center;
  white-space: nowrap;
}
.cox-dirs-list {
  display: flex;
  flex-direction: column;
  margin-top: 2px;
  max-height: 230px;
  overflow-y: auto;
}
.cox-dir-row {
  padding: 5px 0;
  font-size: 12px;
  transition: background 0.12s;
  border-radius: 6px;
  cursor: default;
}
.cox-dir-row:hover {
  background: rgba(127, 119, 221, 0.05);
}
.cox-dir-stripe {
  width: 3px;
  height: 14px;
  border-radius: 0;
}
.cox-dir-name {
  font-size: 12px;
  font-weight: 500;
  color: var(--t1, #1e2a4a);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  min-width: 0;
}
.cox-dir-bar {
  display: block;
  width: 44px;
  height: 4px;
  background: rgba(30, 42, 74, 0.08);
  border-radius: 2px;
  overflow: hidden;
}
.cox-dir-bar-fill {
  display: block;
  height: 100%;
  border-radius: 2px;
  transition: width 0.5s var(--ease-standard);
}
.cox-dir-pct {
  font-size: 12px;
  font-weight: 600;
  text-align: right;
  font-variant-numeric: tabular-nums;
}
.cox-dir-num {
  font-size: 11.5px;
  font-weight: 500;
  color: rgba(30, 42, 74, 0.78);
  font-variant-numeric: tabular-nums;
  text-align: center;
}

/* ============================================================ */
/* 3. SECTOR RANKING */
/* ============================================================ */
.cox-rank-list {
  display: flex;
  flex-direction: column;
  gap: 5px;
}
.cox-rank-row {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 5px 8px;
  border-radius: 6px;
  font-size: 12px;
  transition: background 0.18s, transform 0.18s, box-shadow 0.18s;
}
.cox-rank-mine {
  background: rgba(127, 119, 221, 0.1);
  font-weight: 500;
}
.cox-rank-clickable { cursor: pointer; }
.cox-rank-clickable:hover {
  background: rgba(127, 119, 221, 0.08);
  transform: translateX(2px);
  box-shadow: -2px 0 0 #7F77DD;
}
.cox-rank-loading {
  background: linear-gradient(
    90deg,
    rgba(127, 119, 221, 0.10) 0%,
    rgba(127, 119, 221, 0.20) 50%,
    rgba(127, 119, 221, 0.10) 100%
  );
  background-size: 200% 100%;
  animation: coxSkelShimmer 1.1s ease-in-out infinite;
  pointer-events: none;
}
@keyframes coxSkelShimmer {
  0%   { background-position: 200% 0; }
  100% { background-position: -200% 0; }
}
.cox-rank-spinner {
  width: 12px; height: 12px;
  border: 1.5px solid rgba(127, 119, 221, 0.25);
  border-top-color: #7F77DD;
  border-radius: 50%;
  animation: coxSpinnerRot 0.7s linear infinite;
  flex-shrink: 0;
}
@keyframes coxSpinnerRot { to { transform: rotate(360deg); } }
.cox-rank-pos {
  width: 16px;
  height: 16px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: rgba(30, 42, 74, 0.08);
  color: rgba(30, 42, 74, 0.65);
  border-radius: 50%;
  font-size: 10px;
  font-weight: 600;
  flex-shrink: 0;
}
.cox-rank-mine .cox-rank-pos {
  background: #7f77dd;
  color: #ffffff;
}
.cox-rank-name {
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  color: var(--t1, #1e2a4a);
}
.cox-rank-score {
  font-weight: 600;
  font-size: 11.5px;
}
.cox-rank-pct {
  font-weight: 600;
  font-size: 12px;
  font-variant-numeric: tabular-nums;
  flex-shrink: 0;
}

/* ============================================================ */
/* ============================================================ */
.cox-attention-badge {
  font-size: 11px;
  font-weight: 700;
  color: var(--sev-high);
  text-transform: none;
  letter-spacing: 0;
}
.cox-attn-ok {
  font-size: 11px;
  color: var(--green);
  padding: 12px 0;
  text-align: center;
}
.cox-attn-list {
  display: flex;
  flex-direction: column;
}
.cox-attn-row {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 5px 0;
  border-bottom: 0.5px solid rgba(30, 42, 74, 0.06);
  cursor: pointer;
  border-radius: 3px;
  transition: background 0.12s;
}
.cox-attn-row:hover {
  background: rgba(30, 42, 74, 0.04);
}
.cox-attn-dot {
  width: 5px;
  height: 5px;
  border-radius: 50%;
  background: var(--sev-high);
  flex-shrink: 0;
}
.cox-attn-badge {
  font-size: 8.5px;
  font-weight: 700;
  padding: 1px 5px;
  border-radius: 3px;
  letter-spacing: 0.04em;
  flex-shrink: 0;
}
.cox-attn-badge-project {
  background: rgba(127, 119, 221, 0.14);
  color: #5448b7;
}
.cox-attn-badge-task {
  background: rgba(217, 119, 6, 0.14);
  color: #92580b;
}
.cox-attn-title {
  flex: 1;
  font-size: 12px;
  color: var(--t1, #1e2a4a);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  min-width: 0;
}
.cox-attn-deadline {
  font-size: 9px;
  padding: 1px 4px;
  border-radius: 3px;
  background: var(--red-l);
  color: #791f1f;
  flex-shrink: 0;
  font-variant-numeric: tabular-nums;
}
.cox-attn-more {
  font-size: 11px;
  color: #7f77dd;
  cursor: pointer;
  padding: 6px 0 0;
  text-align: center;
  font-weight: 500;
  transition: opacity 0.15s;
}
.cox-attn-more:hover {
  opacity: 0.75;
}
.cox-attn-upcoming {
  margin-top: 10px;
  padding-top: 8px;
  border-top: 0.5px solid rgba(30, 42, 74, 0.06);
}
.cox-attn-upcoming-h {
  font-size: 10px;
  font-weight: 700;
  color: rgba(30, 42, 74, 0.55);
  text-transform: uppercase;
  letter-spacing: 0.06em;
  margin-bottom: 6px;
}
.cox-attn-upcoming-row {
  display: flex;
  align-items: center;
  gap: 5px;
  padding: 4px 0;
  border-bottom: 0.5px solid rgba(30, 42, 74, 0.06);
  cursor: pointer;
  border-radius: 3px;
  transition: background 0.12s;
}
.cox-attn-upcoming-row:hover {
  background: rgba(30, 42, 74, 0.04);
}
.cox-attn-upcoming-row:last-child {
  border-bottom: none;
}
.cox-attn-upcoming-days {
  font-size: 10px;
  font-weight: 500;
  min-width: 38px;
  font-variant-numeric: tabular-nums;
}
.cox-attn-upcoming-title {
  flex: 1;
  font-size: 12px;
  color: var(--t1, #1e2a4a);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  min-width: 0;
}
.cox-card-clickable { cursor: pointer; }
.cox-card-clickable:hover { transform: translateY(-2px); }

/* ============================================================ */
/* ============================================================ */
.cox-activity-list {
  display: flex;
  flex-direction: column;
}
.cox-activity-row {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  padding: 5px 0;
  border-bottom: 0.5px solid rgba(30, 42, 74, 0.06);
  animation: coxFadeUp 0.4s both;
}
.cox-activity-row:last-child {
  border-bottom: none;
}
.cox-activity-icon {
  width: 24px;
  height: 24px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}
.cox-activity-body {
  flex: 1;
  min-width: 0;
}
.cox-activity-title {
  font-size: 13px;
  font-weight: 500;
  color: var(--t1, #1e2a4a);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.cox-activity-meta {
  display: flex;
  justify-content: space-between;
  font-size: 10px;
  color: rgba(148, 163, 184, 0.8);
  margin-top: 1px;
}
.cox-activity-time {
  font-weight: 500;
}

/* ============================================================ */
/* 6. KPI */
/* ============================================================ */
.cox-kpi-block {
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.cox-kpi-summary {
  display: flex;
  align-items: baseline;
  gap: 8px;
  padding: 6px 10px;
  background: rgba(127, 119, 221, 0.05);
  border-radius: 6px;
  /* top-stripe via shared uza-top-stripe utility (replaces former border-left) */
  position: relative;
  overflow: hidden;
}
.cox-kpi-summary::before {
  content: "";
  position: absolute;
  top: 0; left: 0; right: 0;
  height: 3px;
  background: #7F77DD;
  transform-origin: left center;
  animation:
    uzaStripeDrawIn .8s var(--ease-standard) 100ms both,
    uzaStripeBreathe 2.8s ease-in-out 1s infinite;
  pointer-events: none;
}
.cox-kpi-summary-num {
  font-size: 22px;
  font-weight: 400;
  letter-spacing: -0.025em;
  line-height: 1;
}
.cox-kpi-summary-cap {
  font-size: 11px;
  color: rgba(30, 42, 74, 0.6);
}

.cox-kpi-managers {
  display: flex;
  flex-direction: column;
  gap: 8px;
  max-height: 230px;
  overflow-y: auto;
}
.cox-kpi-manager {
  display: flex;
  flex-direction: column;
  gap: 3px;
  animation: coxFadeUp 0.4s both;
}
.cox-kpi-manager-head {
  display: flex;
  justify-content: space-between;
  align-items: baseline;
  font-size: 11.5px;
}
.cox-kpi-manager-title {
  color: var(--t1, #1e2a4a);
  font-weight: 500;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  margin-right: 8px;
}
.cox-kpi-manager-pct {
  font-weight: 600;
  font-size: 11px;
  flex-shrink: 0;
}
.cox-kpi-bar-track {
  height: 5px;
  background: rgba(30, 42, 74, 0.05);
  border-radius: 3px;
  overflow: hidden;
}
.cox-kpi-bar-fill {
  height: 100%;
  border-radius: 3px;
  transition: width 0.7s var(--ease-standard);
}
.cox-kpi-bar-fill.cox-pct-green {
  background: linear-gradient(90deg, var(--green), #2cb98a);
}
.cox-kpi-bar-fill.cox-pct-blue {
  background: linear-gradient(90deg, var(--blue), #5ba4e3);
}
.cox-kpi-bar-fill.cox-pct-amber {
  background: linear-gradient(90deg, var(--amber), #f5b54e);
}
.cox-kpi-bar-fill.cox-pct-red {
  background: linear-gradient(90deg, var(--sev-high), #f06866);
}
.cox-kpi-manager-role {
  font-size: 10px;
  color: rgba(30, 42, 74, 0.4);
  margin-top: 1px;
}

/* ============================================================ */
/* 7. БП */
/* ============================================================ */
/* Sprint B · BP prior-year baseline (shown when current year empty) */
.cox-bp-baseline {
  background: rgba(127, 119, 221, 0.07);
  border: 1px dashed rgba(127, 119, 221, 0.3);
  border-radius: 8px;
  padding: 10px 12px;
  margin-top: 4px;
  animation: coxBpBaselineSlide .35s var(--ease-standard) both;
}
@keyframes coxBpBaselineSlide { 0% { opacity: 0; } 100% { opacity: 1; } }
.cox-bp-baseline-head {
  display: flex; align-items: center; gap: 6px;
  font-size: 11.5px;
  color: var(--t1, #1E2A4A);
  margin-bottom: 8px;
  line-height: 1.4;
}
.cox-bp-baseline-head b { color: var(--p-deep); font-weight: 600; }
.cox-bp-baseline-icon {
  width: 18px; height: 18px; border-radius: 50%;
  display: inline-flex; align-items: center; justify-content: center;
  background: #7F77DD; color: white;
  font-size: 11px; font-weight: 700;
  flex-shrink: 0;
}
.cox-bp-baseline-rows { display: flex; flex-direction: column; gap: 4px; }
.cox-bp-baseline-row {
  display: flex; align-items: baseline; justify-content: space-between;
  font-size: 12px;
  color: #6B7280;
}
.cox-bp-baseline-num {
  font-variant-numeric: tabular-nums;
  font-weight: 500;
  color: var(--t1, #1E2A4A);
}

.cox-bp-block {
  display: flex;
  flex-direction: column;
  gap: 14px;
}
.cox-bp-row {
  display: flex;
  flex-direction: column;
  gap: 5px;
}
.cox-bp-row-head {
  display: flex;
  justify-content: space-between;
  align-items: baseline;
}
.cox-bp-row-label {
  font-size: 12px;
  font-weight: 500;
  color: var(--t1, #1e2a4a);
}
.cox-bp-row-pct {
  font-weight: 600;
  font-size: 13px;
}
.cox-bp-vals {
  display: flex;
  gap: 14px;
  font-size: 11px;
  flex-wrap: wrap;
}
.cox-bp-val {
  display: flex;
  flex-direction: column;
  gap: 1px;
}
.cox-bp-val-cap {
  font-size: 9.5px;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  color: rgba(30, 42, 74, 0.45);
}
.cox-bp-val-num {
  font-weight: 500;
  color: var(--t1, #1e2a4a);
  font-size: 12.5px;
}
.cox-bp-bar-track {
  height: 6px;
  background: rgba(30, 42, 74, 0.05);
  border-radius: 3px;
  overflow: hidden;
}
.cox-bp-bar-fill {
  height: 100%;
  border-radius: 3px;
  transition: width 0.7s var(--ease-standard);
}
.cox-bp-bar-fill.cox-pct-green {
  background: linear-gradient(90deg, var(--green), #2cb98a);
}
.cox-bp-bar-fill.cox-pct-blue {
  background: linear-gradient(90deg, var(--blue), #5ba4e3);
}
.cox-bp-bar-fill.cox-pct-amber {
  background: linear-gradient(90deg, var(--amber), #f5b54e);
}
.cox-bp-bar-fill.cox-pct-red {
  background: linear-gradient(90deg, var(--sev-high), #f06866);
}

/* ============================================================ */
/* PCT COLORS (text) */
/* ============================================================ */
.cox-pct-green {
  color: var(--green);
}
.cox-pct-blue {
  color: var(--blue);
}
.cox-pct-amber {
  color: var(--amber);
}
.cox-pct-red {
  color: var(--sev-high);
}

/* === Дополнительные элементы v8.2 === */
.cox-attention-inline {
  color: var(--sev-high);
  font-weight: 600;
}
.cox-card-sub-pct {
  font-size: 14px;
  font-weight: 500;
  margin-left: auto;
  text-transform: none;
  letter-spacing: 0;
}
.cox-rank-grade {
  font-weight: 600;
  font-size: 12px;
  padding: 1px 7px;
  border-radius: 5px;
  background: rgba(30, 42, 74, 0.04);
}
.cox-bp-empty,
.cox-kpi-empty {
  color: rgba(30, 42, 74, 0.35) !important;
  font-style: italic;
  font-weight: 400 !important;
}
.cox-kpi-no-fact {
  font-size: 11.5px;
  color: rgba(30, 42, 74, 0.5);
  font-style: italic;
  padding: 6px 10px;
  background: rgba(30, 42, 74, 0.03);
  border-radius: 6px;
}
.cox-bp-fact {
  font-weight: 600 !important;
}

/* ============================================================ */
/* LOADING / EMPTY */
/* ============================================================ */
.cox-loading,
.cox-loading-line {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 11.5px;
  color: rgba(30, 42, 74, 0.4);
  padding: 8px 0;
}
.cox-spinner-sm {
  width: 12px;
  height: 12px;
  border: 1.5px solid rgba(127, 119, 221, 0.2);
  border-top-color: #7f77dd;
  border-radius: 50%;
  animation: coxSpin 0.7s linear infinite;
}
.cox-empty-line {
  font-size: 11.5px;
  color: rgba(30, 42, 74, 0.35);
  font-style: italic;
  padding: 12px 0;
  text-align: center;
}

/* ─── 5. Активность: header-row + кнопка «Все» + refresh + модалка ─── */
.cox-card-label-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}
.cox-activity-head-actions {
  display: flex;
  align-items: center;
  gap: 6px;
}
.cox-activity-all-btn {
  background: transparent;
  border: none;
  cursor: pointer;
  font-family: inherit;
  font-size: 10.5px;
  font-weight: 500;
  color: var(--p-deep);
  letter-spacing: .04em;
  padding: 2px 0;
  text-transform: none;
}
.cox-activity-all-btn:hover { color: #7F77DD; }
.cox-activity-refresh {
  background: transparent;
  border: none;
  cursor: pointer;
  color: var(--t3, var(--t-muted));
  padding: 3px;
  font-family: inherit;
  line-height: 0;
  border-radius: 4px;
  transition: color .12s, background .12s;
}
.cox-activity-refresh:hover { color: var(--p-deep); background: rgba(127, 119, 221, .06); }
.cox-activity-refresh:disabled { opacity: .6; cursor: default; }
.cox-activity-refresh.is-spin svg { animation: coxSpin 1s linear infinite; }
@keyframes coxSpin { to { transform: rotate(360deg); } }

.cox-activity-row.is-clickable { cursor: pointer; }
.cox-activity-row.is-clickable:hover { background: rgba(127, 119, 221, .04); }

.cox-activity-meta-sep { color: rgba(30, 42, 74, 0.20); margin: 0 1px; }
.cox-activity-meta-diff {
  color: var(--p-deep);
  font-family: ui-monospace, monospace;
  font-size: 10px;
  background: rgba(127, 119, 221, .06);
  padding: 0 5px;
  border-radius: 4px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  max-width: 180px;
}

.cox-act-full-item.is-clickable { cursor: pointer; }
.cox-act-full-item.is-clickable:hover { background: rgba(127, 119, 221, .06); }

/* ─── Year switcher для KPI / BP виджетов ─── */
.cox-card-label-left {
  display: inline-flex;
  align-items: center;
  gap: 6px;
}
.cox-year-switcher {
  display: inline-flex;
  align-items: center;
  gap: 2px;
  background: rgba(127, 119, 221, .06);
  border: 0.5px solid rgba(127, 119, 221, .15);
  border-radius: 6px;
  padding: 1px 2px;
}
.cox-year-arrow {
  background: transparent;
  border: none;
  cursor: pointer;
  width: 16px;
  height: 16px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 3px;
  color: var(--p-deep);
  font-size: 12px;
  font-weight: 500;
  font-family: inherit;
  line-height: 1;
  padding: 0;
  transition: background .12s, color .12s, opacity .12s;
}
.cox-year-arrow:hover:not(:disabled) {
  background: rgba(127, 119, 221, .18);
  color: var(--t1, #1E2A4A);
}
.cox-year-arrow:disabled { opacity: .25; cursor: default; }
.cox-year-val {
  font-size: 10.5px;
  font-weight: 500;
  color: var(--p-deep);
  font-variant-numeric: tabular-nums;
  letter-spacing: .02em;
  min-width: 30px;
  text-align: center;
  text-transform: none;
  letter-spacing: 0;
}

/* ─── Period switcher (Y / Q1-Q4) ─── */
.cox-period-switcher,
.cox-bp-view-switcher {
  display: inline-flex;
  align-items: center;
  gap: 1px;
  background: rgba(127, 119, 221, .04);
  border: 0.5px solid rgba(127, 119, 221, .12);
  border-radius: 6px;
  padding: 1px;
  margin-left: 6px;
}
.cox-bp-view-btn {
  background: transparent;
  border: none;
  cursor: pointer;
  font-family: inherit;
  font-size: 9.5px;
  font-weight: 500;
  letter-spacing: .02em;
  color: var(--t3, var(--t-muted));
  padding: 2px 7px;
  border-radius: 4px;
  text-align: center;
  transition: background .12s, color .12s;
  text-transform: none;
  white-space: nowrap;
}
.cox-bp-view-btn:hover { color: var(--p-deep); }
.cox-bp-view-btn.active {
  background: var(--bg1, #fff);
  color: var(--p-deep);
  box-shadow: 0 1px 2px rgba(15, 23, 60, .08);
}
.cox-bp-view-btn-inc.active { color: #0F6E56; }
.cox-bp-view-btn-exp.active { color: #B86A0E; }
.cox-period-btn {
  background: transparent;
  border: none;
  cursor: pointer;
  font-family: inherit;
  font-size: 9.5px;
  font-weight: 500;
  letter-spacing: .02em;
  color: var(--t3, var(--t-muted));
  padding: 2px 6px;
  border-radius: 4px;
  min-width: 18px;
  text-align: center;
  transition: background .12s, color .12s;
  text-transform: none;
}
.cox-period-btn:hover { color: var(--p-deep); }
.cox-period-btn.active {
  background: var(--bg1, #fff);
  color: var(--p-deep);
  box-shadow: 0 1px 2px rgba(15, 23, 60, .06);
}

.cox-act-modal-backdrop {
  position: fixed;
  inset: 0;
  background: rgba(15, 18, 40, 0.45);
  backdrop-filter: blur(8px);
  z-index: 1000;
  display: flex;
  align-items: center;
  justify-content: center;
  animation: coxFadeUp .2s ease-out;
}
.cox-act-modal {
  background: var(--bg1, #fff);
  border-radius: 14px;
  width: min(640px, 92vw);
  max-height: 80vh;
  display: flex;
  flex-direction: column;
  box-shadow: 0 24px 64px rgba(15, 23, 60, .18), 0 8px 24px rgba(15, 23, 60, .08);
  animation: coxFadeUp .25s var(--ease-standard);
}
.cox-act-modal-h {
  padding: 14px 18px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  border-bottom: 0.5px solid #F1EFE8;
}
.cox-act-modal-title {
  font-size: 13px;
  font-weight: 500;
  color: var(--t1, #1E2A4A);
  letter-spacing: -.01em;
}
.cox-act-modal-close {
  background: transparent;
  border: none;
  cursor: pointer;
  font-size: 20px;
  color: var(--t3, var(--t-muted));
  line-height: 1;
  padding: 2px 6px;
  border-radius: 6px;
  font-family: inherit;
}
.cox-act-modal-close:hover { background: var(--bg2, #FAFAFC); color: var(--t1, #1E2A4A); }
.cox-act-modal-body {
  flex: 1;
  overflow-y: auto;
  padding: 8px 14px 14px;
}

.cox-act-full-list {
  list-style: none;
  padding: 0;
  margin: 0;
  display: flex;
  flex-direction: column;
  gap: 2px;
}
.cox-act-full-item {
  display: grid;
  grid-template-columns: 8px 1fr;
  gap: 10px;
  padding: 8px 6px;
  border-radius: 6px;
  transition: background .1s;
}
.cox-act-full-item:hover { background: var(--bg2, #FAFAFC); }
.cox-act-full-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  margin-top: 6px;
}
.cox-act-full-row { min-width: 0; }
.cox-act-full-line1 {
  display: flex;
  align-items: baseline;
  gap: 6px;
  font-size: 12px;
  color: var(--t1, #1E2A4A);
  flex-wrap: wrap;
}
.cox-act-full-actor { font-weight: 500; color: var(--p-deep); }
.cox-act-full-action { color: var(--t3, var(--t-muted)); }
.cox-act-full-target {
  font-weight: 500;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  max-width: 100%;
}
.cox-act-full-line2 {
  font-size: 10.5px;
  color: var(--t3, var(--t-muted));
  margin-top: 2px;
  display: flex;
  gap: 8px;
  align-items: baseline;
  flex-wrap: wrap;
}
.cox-act-full-ts { font-variant-numeric: tabular-nums; }
.cox-act-full-kind {
  background: rgba(127, 119, 221, .08);
  color: var(--p-deep);
  padding: 1px 6px;
  border-radius: 4px;
  font-weight: 500;
}
.cox-act-full-diff,
.cox-act-full-note {
  color: var(--p-deep);
  font-family: ui-monospace, monospace;
  font-size: 10px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

/* ============================================================ */
/* ANIMATIONS */
/* ============================================================ */
@keyframes coxFadeUp {
  from {
    opacity: 0;
    transform: translateY(6px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}
@keyframes coxSpin {
  to {
    transform: rotate(360deg);
  }
}
</style>
