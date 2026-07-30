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
import { useCurrencyConverter } from "@/composables/useCurrencyConverter";
import { useEntityEditor } from "@/composables/useEntityEditor";

// Injected from CompanyWorkspace — opens the overdue drill modal on click
const openOverdueModal = inject<(() => void) | null>("openOverdueModal", null);
import { api } from "@/api/client";
import { computeProgress } from "@/utils/progress";
import { useDirectionsStore } from "@/stores/directions";
import ModalShell from "@/components/ModalShell.vue";
import { useI18n } from "@/composables/useI18n";
import { i18nKey } from "@/locale/keys";
import { resolveCompanyDisplayName } from "@/utils/displayNames";

const { t: tr } = useI18n();


// Единый источник цветов направлений = каталог (стор), чтобы полоски «по
// направлениям» совпадали с цветами из /admin (Каталоги), а не с легаси-хардкодом.
const directionsStore = useDirectionsStore();
function _dirColor(id: string, fallback: string): string {
  return directionsStore.byCode.get(String(id).toLowerCase())?.color || fallback;
}

const fmt = useFormatters();
// Курс USD — из живого источника (year_registry / admin), не хардкод: иначе
// экономический эффект здесь конвертировался по своим цифрам, расходясь со
// всеми модулями на useCurrencyConverter. getUsdRate сам покрывает пропуски
// года (ближайший ранний) и дефолт-фолбэк (канон ЦБУ).
const converter = useCurrencyConverter();

// DIRS catalog 1:1 with легаси (frontend/legacy/index.html line 6753)
const DIRS: { id: string; label: string; color: string }[] = [
  { id: "strategy",    label: i18nKey("Стратегическое управление"),  color: "#6B7FD7" },
  { id: "finance",     label: i18nKey("Финансы / риски / аудит"),    color: "#E0A458" },
  { id: "procurement", label: i18nKey("Система закупок"),            color: "#7BA05B" },
  { id: "orgdev",      label: i18nKey("Организационное развитие"),   color: "#A78BC7" },
  { id: "digital",     label: i18nKey("Цифровизация"),               color: "#5FB3C4" },
  { id: "operations",  label: i18nKey("Операционная эффективность"), color: "#E08A7B" },
  { id: "governance",  label: i18nKey("Корпоративное управление"),   color: "#C77B96" },
  { id: "esg",         label: "ESG",                        color: "#5FA98A" },
  { id: "pr",          label: i18nKey("Связи с общественностью"),    color: "#D89BB5" },
  { id: "pmo",         label: "PMO",                        color: "#7B9BD1" },
  { id: "analytics",   label: i18nKey("Сводный отдел"),              color: "#9B8EC4" },
];
const _DIRS_BY_ID = new Map(DIRS.map((d) => [d.id, d]));
function _dirMeta(direction: string): { id: string; label: string; color: string } {
  const key = String(direction || "").toLowerCase();
  const base = _DIRS_BY_ID.get(key) || { id: key, label: direction || i18nKey("Без направления"), color: "#94A3B8" };
  return { ...base, color: _dirColor(key, base.color) };   // цвет — из каталога
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
  sectorName: i18nKey("Сектор"),
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
  /** Есть ли у текущего пользователя доступ к этой компании (иначе строка
   *  показывается, но переход в чужой воркспейс не предлагается). */
  accessible: boolean;
}
const sectorRanking = ref<SectorRow[]>([]);

interface ActivityRow {
  kind: "task_history" | "audit_log" | string;
  ts: string;                  // ISO timestamp
  actor: string;
  actor_id?: string | null;
  actor_email?: string | null;
  actor_job_title?: string | null;
  action: string;
  field?: string | null;
  old_value?: string | null;
  new_value?: string | null;
  title?: string;              // entity title (task/project)
  detail?: string | null;      // полный текст события («что именно»)
  entity_label?: string | null;
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
// Карточка одного события: «кто · что именно · где · когда» + переход к записи.
// Раньше клик сразу уводил в задачу/проект, и подробности события (текст
// комментария, что поменяли) увидеть было негде.
const activityDetail = ref<ActivityRow | null>(null);
function openActivityDetail(it: ActivityRow) { activityDetail.value = it; }
function closeActivityDetail() { activityDetail.value = null; }

// ─── Per-widget local year + period overrides ──────────────────────────
// Each widget keeps its own year + period so the user can browse historical
// data without changing the page-level year. They sync to props.year whenever
// it changes (period stays user-controlled).
type Period = "Y" | "Q1" | "Q2" | "Q3" | "Q4";
const PERIODS: Period[] = ["Y", "Q1", "Q2", "Q3", "Q4"];

const kpiYear = ref<number>(props.year);
const bpYear  = ref<number>(props.year);
// «Актуальный» период по умолчанию = последний ЗАВЕРШЁННЫЙ квартал (у текущего
// ещё нет полного факта). Напр. в июле (кал. Q3) → Q2. В Q1 остаёмся на Q1.
function _defaultPeriod(): Period {
  const q = Math.floor(new Date().getMonth() / 3) + 1;   // 1..4 текущий кал. квартал
  const prev = q - 1;
  return (prev >= 1 ? `Q${prev}` : "Q1") as Period;
}
const kpiPeriod = ref<Period>(_defaultPeriod());
const bpPeriod  = ref<Period>(_defaultPeriod());
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
interface UpcomingRow {
  id: string;
  kind: "project" | "task";
  title: string;
  deadline: string;
  daysLeft: number;
}
const attentionList = ref<AttentionRow[]>([]);
const attentionTotal = ref(0);
const upcomingList = ref<UpcomingRow[]>([]);
const loadingAttention = ref(true);

function _isDoneStatus(s: any): boolean {
  const v = String(s || "").toLowerCase();
  // i18n-exempt-start -- canonical legacy values read from persisted records.
  return v === "done" || v === "completed" || v === "завершено" || v === "выполнено";
  // i18n-exempt-end
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
  fallbackYear?: number; // год, чьи данные реально показаны (если ≠ выбранному)
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
  fallbackYear?: number; // год, чьи данные реально показаны (если ≠ выбранному)
}
const bpData = ref<BpData | null>(null);

// ─── BP widget view-mode: Доходы / Расходы (по умолчанию Доходы) ──
const bpView = ref<"all" | "income" | "expenses">("income");
function setBpView(v: "all" | "income" | "expenses") { bpView.value = v; }
const bpDisplayedMetrics = computed(() => {
  const d = bpData.value;
  if (!d) return [];
  if (bpView.value === "income") {
    return [
      { label: i18nKey("Выручка"),         d: d.revenue,   tone: "income" as const },
      { label: i18nKey("Фин. доходы"),     d: d.finIncome, tone: "income" as const },
      { label: i18nKey("Опер. прибыль"),   d: d.opProfit,  tone: "income" as const },
    ];
  }
  if (bpView.value === "expenses") {
    return [
      { label: i18nKey("Себестоимость"),   d: d.cogs,       tone: "expense" as const },
      { label: i18nKey("Расходы периода"), d: d.opExpenses, tone: "expense" as const },
      { label: i18nKey("Фин. расходы"),    d: d.finCost,    tone: "expense" as const },
      { label: i18nKey("Налог"),           d: d.tax,        tone: "expense" as const },
    ];
  }
  return [
    { label: i18nKey("Выручка"),         d: d.revenue,  tone: "neutral" as const },
    { label: i18nKey("Опер. прибыль"),   d: d.opProfit, tone: "neutral" as const },
    { label: i18nKey("Чистая прибыль"),  d: d.profit,   tone: "neutral" as const },
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

// Reactive "now" tick — drives auto-refresh of relative timestamps every 60s
const nowTick = ref(Date.now());

// Sector peer navigation state — for skeleton flash on click
const router = useRouter();
const entityEditor = useEntityEditor();
const navigatingTo = ref<string | null>(null);
function navigateToPeer(code: string, isMine: boolean, accessible = true) {
  // Соседа по сектору видно всем в секторе, но открыть можно только компанию,
  // к которой есть доступ: иначе клик уводил бы на экран с отказом.
  if (isMine || !code || !accessible) return;
  navigatingTo.value = code;
  router.push(`/companies/${code}/workspace`).finally(() => {
    setTimeout(() => { navigatingTo.value = null; }, 400);
  });
}

function openAttentionItem(item: AttentionRow | UpcomingRow): void {
  if (item.kind === "project") {
    void entityEditor.openProject(item.id);
  } else {
    void entityEditor.openTask(item.id);
  }
}

function fmtTimeAgo(iso: string): string {
  if (!iso) return "—";
  // Read nowTick to keep this reactive — every 60s nowTick changes, forcing re-render.
  void nowTick.value;
  return fmt.fmtRelativeTime(iso);
}

// Legacy pct colour: ≥60 green / ≥30 amber / red (used by По направлениям + Sector ranking)
function pctColorMono(pct: number): string {
  if (pct >= 60) return "#1D9E75";
  if (pct >= 30) return "#D97706";
  return "#E24B4A";
}

// БП использует строже thresholds: 95/80 как в легасие
function pctClassBp(pct: number): string {
  if (pct >= 95) return "cox-pct-green";
  if (pct >= 80) return "cox-pct-amber";
  return "cox-pct-red";
}

// KPI thresholds: 70/35 как в легасие
function pctClassKpi(pct: number): string {
  if (pct >= 70) return "cox-pct-green";
  if (pct >= 35) return "cox-pct-amber";
  return "cox-pct-red";
}

// Точный _bpFmt из легасиа: ≥10000 -> трлн, ≥100 -> млрд (целое), ≥1 -> 1.5 млрд, иначе 0.05 млрд
// Input is already scaled to billions ("млрд"). Number portion routed through fmt.fmtNumber
// for locale-aware digit grouping / decimal separator.
function fmtBp(v: number | null | undefined): string {
  if (v == null || isNaN(v)) return "—";
  const av = Math.abs(v);
  if (av >= 10000) return tr('{value0} трлн', { value0: fmt.fmtNumber(v / 1000, { decimals: 1 }) });
  if (av >= 100)   return tr('{value0} млрд', { value0: fmt.fmtNumber(Math.round(v)) });
  if (av >= 1)     return tr('{value0} млрд', { value0: fmt.fmtNumber(v, { decimals: 1 }) });
  return tr('{value0} млрд', { value0: fmt.fmtNumber(v, { decimals: 2 }) });
}

// ============================================================
// LOADERS
// ============================================================
const _SANITY_CAP_PER_TASK = 100e12; // 100 трлн UZS

function _getUsdRate(year: number): number {
  return converter.getUsdRate(year);   // живой курс (year_registry) вместо хардкода
}

// Точная копия _eeExtractEffect из легасиа
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
  // i18n-exempt-start -- canonical unit codes from the API, never rendered.
  const mult =
    ov.unit === "трлн"
      ? 1e12
      : ov.unit === "млрд"
        ? 1e9
        : ov.unit === "млн"
          ? 1e6
          : 1;
  // i18n-exempt-end

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
  if (av >= 1e12) return tr('{value0} трлн', { value0: fmt.fmtNumber(v / 1e12, { decimals: 1 }) });
  if (av >= 1e9)  return tr('{value0} млрд', { value0: fmt.fmtNumber(v / 1e9,  { decimals: 1 }) });
  if (av >= 1e6)  return tr('{value0} млн', { value0: fmt.fmtNumber(Math.round(v / 1e6)) });
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
    errors.effect = e?.message || tr('Ошибка');
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
    // Параллельно: проекты + задачи компании + прогрев каталога направлений
    // (иначе merged соберётся до загрузки стора и цвета возьмутся хардкодные).
    const [projRes, taskRes] = await Promise.all([
      api.get(`/projects?company_id=${props.companyId}&limit=500`),
      api.get(`/tasks?company_id=${props.companyId}&limit=500`),
      directionsStore.ensureLoaded(),
    ]);
    let projects = _arr(projRes.data);
    let tasks = _arr(taskRes.data);

    // Year filter (как в легасие — portfolio_year или без него)
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
      // Средний прогресс по направлению — ВЗВЕШЕННО по статусу (0/25/50/75/100),
      // как канон utils/progress, по всем работам (проекты+задачи), а не done/total.
      const pPct = computeProgress([...pSlice, ...tSlice] as any).pct;
      // color — хардкод-фолбэк; фактический цвет резолвится в шаблоне через
      // _dirColor(d.id) РЕАКТИВНО (стор мог ещё не загрузиться на момент сборки).
      return { id: dir.id, label: dir.label, color: dir.color, pPct, pDone, pTotal, tDone, tTotal };
    }).filter((d) => d.pTotal > 0 || d.tTotal > 0)
      .sort((a, b) => b.pPct - a.pPct);

    dirsData.value = merged;
  } catch (e: any) {
    errors.dirs = e?.message || tr('Ошибка');
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
        kind: "task",
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
      kind: x.kind,
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
  if (days <= 7) return tr('{value0} дн.', { value0: days });
  if (days <= 30) return tr('{value0} нед.', { value0: Math.ceil(days / 7) });
  return tr('{value0} мес.', { value0: Math.ceil(days / 30) });
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
    // Рейтинг сектора приходит одним эндпоинтом: он считает те же проценты,
    // что дашборд (взвешенный прогресс), и — главное — отдаёт ВЕСЬ сектор.
    // Прежняя сборка на клиенте (/companies + /dashboard/shareholder) была
    // ограничена областью пользователя: сотрудник компании видел в «рейтинге
    // сектора» одну свою строку. Флаг accessible решает, куда можно перейти.
    const rRank = await api.get(`/companies/${props.companyCode}/sector-ranking`, {
      params: { year: props.year },
    });
    const rankItems = _arr(rRank.data?.items);
    if (rankItems.length > 0) {
      sectorRanking.value = rankItems.map((it: any) => ({
        code: String(it.code || ""),
        name: resolveCompanyDisplayName(String(it.name || it.code || ""), String(it.code || "")),
        score: _num(it.progress_pct),
        grade: "",
        isMine: !!it.is_mine,
        accessible: it.accessible !== false,
      }));
      return;
    }
    // Фолбэк на старую сборку — если эндпоинт ещё не выкачен на этот бэкенд.
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
        name: resolveCompanyDisplayName(c.name_short || c.name_ru || c.code, c.id || c.code),
        score: progressByCode.get(String(c.code || "").toLowerCase()) ?? 0,
        grade: "",
        isMine: c.id === props.companyId,
        accessible: true,   // фолбэк-список и так ограничен доступом /companies
      }))
      .sort((a, b) => b.score - a.score)
      .slice(0, 5);
  } catch (e: any) {
    errors.sector = e?.message || tr('Ошибка');
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
      errors.activity = e?.response?.data?.detail || e?.message || tr('Ошибка');
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
  assignee_email:  i18nKey("ответственного"),
  assignee_name:   i18nKey("ответственного"),
  assignee_id:     i18nKey("ответственного"),
  status:          i18nKey("статус"),
  priority:        i18nKey("приоритет"),
  title:           i18nKey("название"),
  description:     i18nKey("описание"),
  due_date:        i18nKey("срок"),
  start_date:      i18nKey("дату начала"),
  progress_percent: i18nKey("прогресс"),
  direction_id:    i18nKey("направление"),
  board_id:        i18nKey("доску"),
  result_at:       i18nKey("результат"),
  // Company fields
  name_ru:         i18nKey("название"),
  name_short:      i18nKey("короткое название"),
  sector_code:     i18nKey("сектор"),
  legal_form:      i18nKey("форму собственности"),
  inn:             i18nKey("ИНН"),
  status_ru:       i18nKey("статус"),
};

// Verb portion of "<module>.<verb>" actions
const VERB_MAP: Record<string, string> = {
  create:    i18nKey("создал"),
  created:   i18nKey("создал"),
  update:    i18nKey("обновил"),
  updated:   i18nKey("обновил"),
  delete:    i18nKey("удалил"),
  deleted:   i18nKey("удалил"),
  uploaded:  i18nKey("загрузил"),
  approved:  i18nKey("утвердил"),
  rejected:  i18nKey("отклонил"),
  submitted: i18nKey("отправил"),
  published: i18nKey("опубликовал"),
  assigned:  i18nKey("назначил"),
  revoked:   i18nKey("отозвал"),
  restored:  i18nKey("восстановил"),
  archived:  i18nKey("архивировал"),
  replied:   i18nKey("ответил"),
  read:      i18nKey("прочитал"),
  view:      i18nKey("просмотрел"),
};

// Domain noun for "<module>" portion in accusative form
const MODULE_NOUN: Record<string, string> = {
  tasks:       i18nKey("задачу"),
  projects:    i18nKey("проект"),
  companies:   i18nKey("компанию"),
  kpi:         "KPI",
  bp:          i18nKey("бизнес-план"),
  ratings:     i18nKey("рейтинг"),
  esg:         "ESG",
  governance:  i18nKey("корп. управление"),
  procurement: i18nKey("закупку"),
  credit:      i18nKey("кредит"),
  comments:    i18nKey("комментарий"),
  attachments: i18nKey("файл"),
  rbac:        i18nKey("права"),
  auth:        i18nKey("аккаунт"),
  moderation:  i18nKey("запрос на модерацию"),
  broadcasts:  i18nKey("рассылку"),
};

function activityActionLabel(it: ActivityRow): string {
  // Exact matches first (task_history actions)
  const exact: Record<string, string> = {
    status_changed: i18nKey("сменил статус"),
    archived:       i18nKey("архивировал"),
    unarchived:     i18nKey("восстановил из архива"),
    result_set:     i18nKey("отметил результат"),
    result_cleared: i18nKey("снял результат"),
    CREATE:         i18nKey("создал"),
    UPDATE:         i18nKey("обновил"),
    DELETE:         i18nKey("удалил"),
    VIEW:           i18nKey("просмотрел"),
    FAILED:         i18nKey("ошибка доступа"),
  };
  const action = it.action || "";

  if (action === "status_update.created") return tr(i18nKey("обновил(а) ход"));

  // task_history field updates → "изменил <field-label>"
  if (action === "field_updated") {
    const f = it.field || "";
    const label = FIELD_LABELS[f]
      ? tr(FIELD_LABELS[f])
      : f
        ? tr("поле «{field}»", { field: f })
        : tr("поле");
    return tr('изменил {value0}', { value0: label });
  }
  if (action in exact) return tr(exact[action]);
  if (action.startsWith("login.")) return tr('вход');

  // Namespaced "<module>.<verb>" → combine
  if (action.includes(".")) {
    const [module, verb] = action.split(".", 2);
    const verbRu = VERB_MAP[verb] || verb;
    const nounRu = MODULE_NOUN[module];
    if (nounRu && VERB_MAP[verb]) {
      return tr("{verb} {entity}", { verb: tr(verbRu), entity: tr(nounRu) });
    }
    if (VERB_MAP[verb]) return tr(verbRu);
  }
  return action || "—";
}

function statusUpdateEntityLabel(it: ActivityRow): string {
  const explicit = String(it.entity_label || "").trim();
  if (explicit) return explicit;
  const raw = String(it.detail || it.notes || it.title || "").trim();
  return raw.match(/«([^»]+)»/)?.[1]?.trim() || "";
}

function activityTargetLabel(it: ActivityRow): string {
  if (it.action === "status_update.created") return statusUpdateEntityLabel(it);
  return String(it.entity_label || it.title || "").trim();
}

function activityDisplayTitle(it: ActivityRow): string {
  if (it.action === "status_update.created") {
    const entity = statusUpdateEntityLabel(it);
    return entity
      ? tr("обновил(а) ход «{entity}»", { entity })
      : tr("обновил(а) ход");
  }
  return it.title || tr(activityActionLabel(it));
}

function activityDetailText(it: ActivityRow): string {
  const raw = String(it.detail || it.notes || "").trim();
  if (it.action !== "status_update.created" || !raw) return raw;
  return raw.replace(/^обновил\s+ход\s+(?:проекта|задачи)\s+«[^»]*»:\s*/iu, "").trim(); // i18n-exempt: legacy event parser, never rendered
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
    task:                  i18nKey("Задача"),
    project:               i18nKey("Проект"),
    comment:               i18nKey("Комментарий"),
    kpi_submission:        "KPI",
    bp_submission:         i18nKey("Бизнес-план"),
    moderation_submission: i18nKey("Модерация"),
    user:                  i18nKey("Пользователь"),
    user_session:          i18nKey("Сессия"),
    mfa_attempt:           "MFA",
    company:               i18nKey("Компания"),
    broadcast:             i18nKey("Рассылка"),
    attachment:            i18nKey("Файл"),
  };
  return map[t] ? tr(map[t]) : (t || "—");
}

// Человекочитаемые статусы задач (вместо технических кодов init/quarterly/…).
const TASK_STATUS_LABELS: Record<string, string> = {
  init: i18nKey("Инициация"), new: i18nKey("Новая"), active: i18nKey("В работе"), review: i18nKey("На проверке"),
  done: i18nKey("Завершено"), quarterly: i18nKey("Квартальная"), monthly: i18nKey("Ежемесячная"),
  ongoing: i18nKey("Постоянная"), deferred: i18nKey("Перенесена"), blocked: i18nKey("Заблокирована"),
};
// Значение diff в нормальном языке: статусы → русские лейблы, ISO-даты → ДД.ММ.ГГГГ.
function _fmtActivityVal(v: any, field?: string | null, action?: string): string {
  const s = String(v ?? "").trim();
  if (!s) return "—";
  if (action === "status_changed" || field === "status") {
    return TASK_STATUS_LABELS[s] ? tr(TASK_STATUS_LABELS[s]) : s;
  }
  if (/^\d{4}-\d{2}-\d{2}/.test(s)) return fmt.fmtDateNumeric(s);
  return s.length > 24 ? s.slice(0, 24) + "…" : s;
}

// Compact diff string for the 5-row preview — например «Новая → Завершено».
function shortDiff(it: ActivityRow): string | null {
  if (it.kind !== "task_history") return null;
  const ov = it.old_value;
  const nv = it.new_value;
  if (ov == null || nv == null) return null;
  return `${_fmtActivityVal(ov, it.field, it.action)} → ${_fmtActivityVal(nv, it.field, it.action)}`;
}

async function _computeKpiForYear(y: number): Promise<KpiData> {
    const r = await api.get(`/kpi/${props.companyId}/${y}`);
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

    // === ТОЧНАЯ ФОРМУЛА РАСЧЁТА ===
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
          // Cap at 2x как в легасие
          const r = Math.min(2, f / p);
          wSum += r * w;
          totW += w;
          mS += r * w;
          mW += w;
          mHasFact = true;
          // Attention threshold легасиа
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

    return {
      managers: mgrs.slice(0, 6),
      overallProgress,
      totalManagers: mgrs.length,
      totalIndicators: totalInd,
      attentionCount: attCount,
      hasAnyFact,
      fallbackYear: y,
    };
}

async function loadKpi() {
  loading.kpi = true;
  errors.kpi = null;
  try {
    let res = await _computeKpiForYear(kpiYear.value);
    // Если за выбранный год факт не введён — показываем последний год с фактом
    // (до 4 лет назад), отметив fallbackYear для подписи «данные за …».
    if (!res.hasAnyFact) {
      for (let back = 1; back <= 4; back++) {
        try {
          const alt = await _computeKpiForYear(kpiYear.value - back);
          if (alt.hasAnyFact) { res = alt; break; }
        } catch { /* за этот год данных нет — пробуем дальше */ }
      }
    }
    kpiData.value = res;
  } catch (e: any) {
    errors.kpi = e?.message || tr('Ошибка');
    kpiData.value = {
      managers: [], overallProgress: 0, totalManagers: 0,
      totalIndicators: 0, attentionCount: 0, hasAnyFact: false,
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

async function _computeBpForYear(y: number): Promise<BpData> {
  const r = await api.get(`/bp/raw/${props.companyId}/${y}`);
  const data = r.data;
  const periodKey = _bpPeriodKey(bpPeriod.value);

  function getMetric(metricKey: string): BpMetric {
    const c = _pickBpCell(data, periodKey, metricKey);
    return {
      plan: c.plan, fact: c.fact, expect: c.expect,
      hasPlan: c.plan != null, hasFact: c.fact != null,
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
  if (revenue.plan != null && revenue.plan !== 0 && revenue.fact != null) {
    overallPct = Math.round((revenue.fact / revenue.plan) * 100);
  }

  const hasData =
    revenue.hasPlan || revenue.hasFact ||
    opProfit.hasPlan || opProfit.hasFact ||
    profit.hasPlan || profit.hasFact ||
    cogs.hasPlan || opExpenses.hasPlan;

  return {
    revenue, opProfit, profit,
    finIncome, cogs, opExpenses, finCost, tax,
    overallPct, hasData, fallbackYear: y,
  };
}

async function loadBp() {
  loading.bp = true;
  errors.bp = null;
  bpBaseline.value = null;
  try {
    let res = await _computeBpForYear(bpYear.value);
    // Если за выбранный год данных нет — показываем последний год с данными.
    if (!res.hasData) {
      for (let back = 1; back <= 4; back++) {
        try {
          const alt = await _computeBpForYear(bpYear.value - back);
          if (alt.hasData) { res = alt; break; }
        } catch { /* за этот год данных нет — пробуем дальше */ }
      }
    }
    bpData.value = res;
  } catch (e: any) {
    errors.bp = e?.message || tr('Ошибка');
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
  directionsStore.ensureLoaded();   // цвета направлений из каталога
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
        {{ tr('Эконом. эффект ·') }} {{ year }}
        <span
          v-if="effectData && effectData.projectsWithEffect > 0"
          class="cox-card-sub"
        >
          {{ effectData.projectsWithEffect }} / {{ effectData.totalProjects }}
          {{ tr('проектов с эффектом') }}
        </span>
      </div>
      <div v-if="loading.effect" class="cox-loading">
        <div class="cox-spinner-sm"></div>
        <span>{{ tr('Извлечение эффекта из карточек проектов...') }}</span>
      </div>
      <!-- Есть эффект -->
      <div
        v-else-if="effectData && effectData.projectsWithEffect > 0"
        class="cox-effect-block"
      >
        <div class="cox-effect-stats">
          <div class="cox-effect-stat">
            <div class="cox-effect-stat-cap">{{ tr('План') }}</div>
            <div class="cox-effect-stat-num">
              {{ fmtEffectUzs(effectData.plannedTotal) }}
            </div>
          </div>
          <div class="cox-effect-stat" data-color="green">
            <div class="cox-effect-stat-cap">{{ tr('Факт') }}</div>
            <div class="cox-effect-stat-num">
              {{ fmtEffectUzs(effectData.realizedTotal) }}
            </div>
          </div>
          <div
            v-if="effectData.plannedTotal > 0"
            class="cox-effect-stat"
            data-color="purple"
          >
            <div class="cox-effect-stat-cap">{{ tr('Выполнение') }}</div>
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
          <div class="cox-effect-tops-label">{{ tr('Топ проектов по эффекту:') }}</div>
          <div
            v-for="p in effectData.topProjects"
            :key="p.id"
            class="cox-effect-top-row"
          >
            <span class="cox-effect-top-title">{{ p.title }}</span>
            <span class="cox-effect-top-vals">
              <span class="cox-effect-top-val">
                <span class="cox-effect-top-cap">{{ tr('план') }}</span>
                {{ fmtEffectUzs(p.plannedUzs) }}
              </span>
              <span v-if="p.realizedUzs > 0" class="cox-effect-top-val">
                <span class="cox-effect-top-cap">{{ tr('факт') }}</span>
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
            {{ tr('Нет проектов с введённым эффектом') }}
          </div>
          <div class="cox-effect-empty-hint">
            {{ tr('Эконом. эффект указывается вручную в карточке проекта/задачи (') }}{{ effectData.totalProjects }}
            {{
              effectData.totalProjects === 1 ? tr('проект') : effectData.totalProjects < 5 ? tr('проекта') : tr('проектов')
            }} {{ tr('в') }} {{ year }} {{ tr('году)') }}
          </div>

          <!-- Sprint B · Cumulative fallback for empty current year -->
          <div v-if="effectCumulative" class="cox-effect-cum">
            <div class="cox-effect-cum-tag">
              {{ tr('↻ Накопленный эффект') }} {{ effectCumulative.fromYear }}–{{ effectCumulative.toYear }}
            </div>
            <div class="cox-effect-cum-grid">
              <div class="cox-effect-cum-cell">
                <span class="cox-effect-cum-cap">{{ tr('План') }}</span>
                <span class="cox-effect-cum-num">{{ fmtEffectUzs(effectCumulative.plannedTotal) }}</span>
              </div>
              <div v-if="effectCumulative.realizedTotal > 0" class="cox-effect-cum-cell">
                <span class="cox-effect-cum-cap">{{ tr('Факт') }}</span>
                <span class="cox-effect-cum-num">{{ fmtEffectUzs(effectCumulative.realizedTotal) }}</span>
              </div>
              <div class="cox-effect-cum-cell">
                <span class="cox-effect-cum-cap">{{ tr('Проектов') }}</span>
                <span class="cox-effect-cum-num">{{ effectCumulative.projectsCount }}</span>
              </div>
            </div>
          </div>
        </div>
      </div>
      <div v-else class="cox-empty-line">{{ tr('Нет проектов за') }} {{ year }} {{ tr('год') }}</div>
    </section>

    <!-- ============================================================ -->
    <!-- 2-5. Grid 4: По направлениям | Sector | Внимание | Активность -->
    <!-- ============================================================ -->
    <section class="cox-grid-4">
      <!-- 2. По направлениям -->
      <div class="cox-card">
        <div class="cox-card-label">{{ tr('По направлениям') }}</div>
        <div v-if="loading.dirs" class="cox-loading-line">{{ tr('Загрузка...') }}</div>
        <template v-else-if="dirsData.length > 0">
          <div class="cox-dir-head">
            <span class="cox-dir-stripe-slot"></span>
            <span class="cox-dir-name-slot"></span>
            <span class="cox-dir-bar-slot"></span>
            <span class="cox-dir-pct-slot"></span>
            <span class="cox-dir-num-head">{{ tr('Проекты') }}</span>
            <span class="cox-dir-num-head">{{ tr('Задачи') }}</span>
          </div>
          <div class="cox-dirs-list">
            <div
              v-for="d in dirsData"
              :key="d.id"
              class="cox-dir-row"
              :title="tr('{value0}: проекты {value1}/{value2} ({value3}%) · задачи {value4}/{value5}', { value0: d.label, value1: d.pDone, value2: d.pTotal, value3: d.pPct, value4: d.tDone, value5: d.tTotal })"
            >
              <span class="cox-dir-stripe" :style="{ background: _dirColor(d.id, d.color) }"></span>
              <span class="cox-dir-name">{{ tr(d.label) }}</span>
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
        <div v-else class="cox-empty-line">{{ tr('Нет направлений') }}</div>
      </div>

      <!-- 3. Sector ranking -->
      <div class="cox-card">
        <div class="cox-card-label">{{ sectorName }}</div>
        <div v-if="loading.sector" class="cox-loading-line">{{ tr('Загрузка...') }}</div>
        <div v-else-if="sectorRanking.length > 0" class="cox-rank-list">
          <div
            v-for="(s, i) in sectorRanking"
            :key="s.code"
            class="cox-rank-row"
            :class="{
              'cox-rank-mine': s.isMine,
              'cox-rank-clickable': !s.isMine && s.accessible,
              'cox-rank-loading': navigatingTo === s.code,
            }"
            :title="s.isMine ? tr('Текущая компания')
                    : s.accessible ? tr('Открыть «{value0}»', { value0: s.name })
                    : tr('{value0} — сосед по сектору (нет доступа к карточке)', { value0: s.name })"
            @click="navigateToPeer(s.code, s.isMine, s.accessible)"
          >
            <span class="cox-rank-pos">{{ i + 1 }}</span>
            <span class="cox-rank-name">{{ s.name }}</span>
            <span
              v-if="navigatingTo === s.code"
              class="cox-rank-spinner"
              :aria-label="tr('Загрузка')"
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
        <div v-else class="cox-empty-line">{{ tr('Нет данных по сектору') }}</div>
      </div>

      <!-- 4. Требуют внимания — real list (overdue) + Дедлайны (upcoming) — 1:1 с легасиом -->
      <div class="cox-card">
        <div class="cox-card-label">
          {{ tr('Требуют внимания') }}
          <span v-if="attentionTotal > 0" class="cox-attention-badge">{{ attentionTotal }}</span>
        </div>
        <div v-if="loadingAttention" class="cox-loading-line">{{ tr('Загрузка...') }}</div>
        <template v-else>
          <div v-if="attentionList.length === 0 && upcomingList.length === 0" class="cox-attn-ok">
            {{ tr('Просроченных нет') }}
          </div>
          <div v-if="attentionList.length > 0" class="cox-attn-list">
            <button
              v-for="item in attentionList"
              :key="item.kind + ':' + item.id"
              type="button"
              class="cox-attn-row"
              :aria-label="item.title"
              @click="openAttentionItem(item)"
            >
              <span class="cox-attn-dot"></span>
              <span class="cox-attn-badge" :class="`cox-attn-badge-${item.kind}`">
                {{ item.kind === "project" ? tr('ПРОЕКТ') : tr('ЗАДАЧА') }}
              </span>
              <span class="cox-attn-title" :title="item.title">
                {{ item.title.length > 26 ? item.title.slice(0, 24) + "…" : item.title }}
              </span>
              <span v-if="item.deadline" class="cox-attn-deadline">{{ item.deadline }}</span>
            </button>
            <div
              v-if="attentionTotal > attentionList.length && openOverdueModal"
              class="cox-attn-more"
              @click="openOverdueModal && openOverdueModal()"
            >
              {{ tr('Показать все (') }}{{ attentionTotal }}) →
            </div>
          </div>
          <div v-if="upcomingList.length > 0" class="cox-attn-upcoming">
            <div class="cox-attn-upcoming-h">{{ tr('Дедлайны') }}</div>
            <button
              v-for="u in upcomingList"
              :key="u.kind + ':' + u.id"
              type="button"
              class="cox-attn-upcoming-row"
              :aria-label="u.title"
              @click="openAttentionItem(u)"
            >
              <span class="cox-attn-upcoming-days" :style="{ color: upcomingColor(u.daysLeft) }">
                {{ fmtUpcoming(u.daysLeft) }}
              </span>
              <span class="cox-attn-upcoming-title" :title="u.title">
                {{ u.title.length > 28 ? u.title.slice(0, 26) + "…" : u.title }}
              </span>
            </button>
          </div>
        </template>
      </div>

      <!-- 5. Активность — task_history + audit_log объединены. Источник:
           GET /companies/{code}/activity. 5 свежих в виджете, кнопка «Все»
           открывает модалку с полным списком. -->
      <div class="cox-card">
        <div class="cox-card-label cox-card-label-row">
          <span>{{ tr('Активность') }}</span>
          <div class="cox-activity-head-actions">
            <button
              class="cox-activity-refresh"
              :class="{ 'is-spin': activityRefreshing }"
              :disabled="activityRefreshing"
              @click="refreshActivity"
              :title="tr('Обновить')"
              :aria-label="tr('Обновить')"
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
              {{ tr('Все (') }}{{ activityTotal || activityAll.length }}) →
            </button>
          </div>
        </div>
        <div v-if="loading.activity" class="cox-loading-line">{{ tr('Загрузка...') }}</div>
        <div v-else-if="errors.activity" class="cox-empty-line">{{ errors.activity }}</div>
        <div
          v-else-if="activityData.length > 0"
          class="cox-activity-list"
        >
          <button
            v-for="(a, i) in activityData"
            :key="a.ts + ':' + i"
            type="button"
            class="cox-activity-row"
            :style="{ '--d': i * 45 + 'ms', '--acc': activityActionColor(a) }"
            :title="tr('Подробнее: {value0} — {value1}', { value0: (a.actor || '—'), value1: activityActionLabel(a) })"
            @click="openActivityDetail(a)"
          >
            <span
              class="cox-activity-icon"
              :style="{ background: activityActionColor(a) + '1F', color: activityActionColor(a) }"
            >
              <svg width="12" height="12" viewBox="0 0 16 16" fill="none" stroke="currentColor"
                   stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round">
                <path d="M3 8l3 3 7-7"/>
              </svg>
            </span>
            <span class="cox-activity-body">
              <span class="cox-activity-title" :title="activityDisplayTitle(a)">
                {{ activityDisplayTitle(a) }}
              </span>
              <span class="cox-activity-meta">
                <!-- КТО: имя автора первым — раньше строка начиналась с типа
                     записи, и «кто изменил» в карточке не было вовсе. -->
                <span class="cox-activity-actor">{{ a.actor || '—' }}</span>
                <span class="cox-activity-meta-sep">·</span>
                <span>{{ activityEntityKindRu(a.entity_type) }}</span>
                <span class="cox-activity-meta-sep">·</span>
                <span>{{ tr(activityActionLabel(a)) }}</span>
                <span v-if="shortDiff(a)" class="cox-activity-meta-diff">{{ shortDiff(a) }}</span>
                <span class="cox-activity-time">{{ fmtTimeAgo(a.ts) }}</span>
              </span>
            </span>
            <svg class="cox-activity-chev" width="13" height="13" viewBox="0 0 24 24" fill="none"
                 stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <path d="M9 18l6-6-6-6"/>
            </svg>
          </button>
        </div>
        <div v-else class="cox-empty-line">{{ tr('Нет записей') }}</div>
      </div>
    </section>

    <!-- ─── Модалка «Вся активность» — канон ModalShell ─── -->
    <ModalShell :open="activityModalOpen" size="md" :title="tr('Активность · последние 14 дней')" @close="closeActivityModal">
        <div class="cox-act-modal-body">
          <ul v-if="activityAll.length > 0" class="cox-act-full-list">
            <li
              v-for="(it, i) in activityAll"
              :key="i"
              class="cox-act-full-item is-clickable"
              :style="{ '--d': Math.min(i, 12) * 28 + 'ms' }"
              @click="openActivityDetail(it)"
            >
              <span class="cox-act-full-dot" :style="{ background: activityActionColor(it) }"></span>
              <div class="cox-act-full-row">
                <div class="cox-act-full-line1">
                  <span class="cox-act-full-actor">{{ it.actor }}</span>
                  <span class="cox-act-full-action">{{ tr(activityActionLabel(it)) }}</span>
                  <span v-if="activityTargetLabel(it)" class="cox-act-full-target" :title="activityTargetLabel(it)">{{ activityTargetLabel(it) }}</span>
                </div>
                <div class="cox-act-full-line2">
                  <span class="cox-act-full-ts">{{ fmtTimeAgo(it.ts) }}</span>
                  <span v-if="it.entity_type" class="cox-act-full-kind">{{ activityEntityKindRu(it.entity_type) }}</span>
                  <span v-if="it.kind === 'task_history' && it.old_value && it.new_value"
                        class="cox-act-full-diff"
                        :title="`${_fmtActivityVal(it.old_value, it.field, it.action)} → ${_fmtActivityVal(it.new_value, it.field, it.action)}`">
                    {{ _fmtActivityVal(it.old_value, it.field, it.action) }} → {{ _fmtActivityVal(it.new_value, it.field, it.action) }}
                  </span>
                </div>
              </div>
            </li>
          </ul>
          <div v-else class="cox-empty-line">{{ tr('Нет активности') }}</div>
        </div>
    </ModalShell>

    <!-- ─── Детали одного события: «кто · что именно · где · когда» ─── -->
    <ModalShell :open="!!activityDetail" size="sm" :title="tr('Событие')" @close="closeActivityDetail">
      <div v-if="activityDetail" class="cox-actd" :style="{ '--acc': activityActionColor(activityDetail) }">
        <div class="cox-actd-head">
          <span class="cox-actd-chip">{{ tr(activityActionLabel(activityDetail)) }}</span>
          <span class="cox-actd-ts">{{ fmtTimeAgo(activityDetail.ts) }}</span>
        </div>
        <div class="cox-actd-entity">{{ activityTargetLabel(activityDetail) || '—' }}</div>
        <!-- Что именно: полный текст события (текст комментария, суть правки) -->
        <div v-if="activityDetailText(activityDetail)" class="cox-actd-text">
          {{ activityDetailText(activityDetail) }}
        </div>
        <div v-else-if="shortDiff(activityDetail)" class="cox-actd-text">{{ shortDiff(activityDetail) }}</div>
        <div class="cox-actd-meta">
          <div class="cox-actd-row">
            <span class="cox-actd-l">{{ tr('Кто') }}</span>
            <span class="cox-actd-v">
              <b>{{ activityDetail.actor || '—' }}</b>
              <em v-if="activityDetail.actor_job_title">{{ activityDetail.actor_job_title }}</em>
            </span>
          </div>
          <div class="cox-actd-row">
            <span class="cox-actd-l">{{ tr('Где') }}</span>
            <span class="cox-actd-v">{{ activityEntityKindRu(activityDetail.entity_type) }}</span>
          </div>
          <div class="cox-actd-row">
            <span class="cox-actd-l">{{ tr('Когда') }}</span>
            <span class="cox-actd-v">{{ fmt.fmtDateTime(activityDetail.ts) }}</span>
          </div>
        </div>
      </div>
      <template #footer>
        <button
          v-if="activityDetail && isClickable(activityDetail)"
          class="cox-actd-open"
          @click="(() => { const it = activityDetail!; closeActivityDetail(); closeActivityModal(); openEntity(it); })()"
        >
          {{ activityDetail?.entity_type === 'project' ? tr('Открыть проект') : tr('Открыть задачу') }} →
        </button>
        <button class="cox-actd-close" @click="closeActivityDetail">{{ tr('Закрыть') }}</button>
      </template>
    </ModalShell>

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
                      :disabled="kpiYear <= 2020" :aria-label="tr('Предыдущий год')">‹</button>
              <span class="cox-year-val">{{ kpiYear }}</span>
              <button class="cox-year-arrow" @click="stepKpiYear(1)"
                      :disabled="kpiYear >= 2030" :aria-label="tr('Следующий год')">›</button>
            </span>
            <span v-if="kpiData && kpiData.fallbackYear && kpiData.fallbackYear !== kpiYear"
                  class="cox-fallback-badge" :title="tr('За {value0} факт не введён — показаны последние данные', { value0: kpiYear })">
              {{ tr('данные за') }} {{ kpiData.fallbackYear }}
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
            {{ kpiData.totalManagers }} {{ tr('рук. ·') }}
            {{ kpiData.totalIndicators }} {{ tr('показателей') }}
            <span
              v-if="kpiData.attentionCount > 0"
              class="cox-attention-inline"
            >
              · {{ kpiData.attentionCount }} {{ tr('требуют внимания') }}
            </span>
          </span>
        </div>
        <div v-if="loading.kpi" class="cox-loading-line">{{ tr('Загрузка KPI...') }}</div>
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
            <div class="cox-kpi-summary-cap">{{ tr('общий прогресс') }}</div>
          </div>
          <div v-else class="cox-kpi-no-fact">
            {{ tr('Факт не введён ни по одному показателю') }}
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
                  ? tr('{value0}: выполнение {value1}%', { value0: m.title, value1: m.progress })
                  : tr('{value0}: факт не введён', { value0: m.title })"
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
          {{ tr('Нет KPI данных за') }} {{ year }}
        </div>
      </div>

      <!-- 7. Бизнес-план -->
      <div class="cox-card cox-card-tall">
        <div class="cox-card-label cox-card-label-row">
          <span class="cox-card-label-left">
            <span>{{ tr('Бизнес-план ·') }}</span>
            <span class="cox-year-switcher">
              <button class="cox-year-arrow" @click="stepBpYear(-1)"
                      :disabled="bpYear <= 2020" :aria-label="tr('Предыдущий год')">‹</button>
              <span class="cox-year-val">{{ bpYear }}</span>
              <button class="cox-year-arrow" @click="stepBpYear(1)"
                      :disabled="bpYear >= 2030" :aria-label="tr('Следующий год')">›</button>
            </span>
            <span v-if="bpData && bpData.fallbackYear && bpData.fallbackYear !== bpYear"
                  class="cox-fallback-badge" :title="tr('За {value0} данных нет — показаны последние', { value0: bpYear })">
              {{ tr('данные за') }} {{ bpData.fallbackYear }}
            </span>
            <span class="cox-bp-view-switcher">
              <button class="cox-bp-view-btn cox-bp-view-btn-inc"
                      :class="{ active: bpView === 'income' }"
                      @click="setBpView('income')"
                      :title="tr('Выручка / Фин. доходы / Опер. прибыль')">{{ tr('Доходы') }}</button>
              <button class="cox-bp-view-btn cox-bp-view-btn-exp"
                      :class="{ active: bpView === 'expenses' }"
                      @click="setBpView('expenses')"
                      :title="tr('Себестоимость / Расходы / Фин.расходы / Налог')">{{ tr('Расходы') }}</button>
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
        <div v-if="loading.bp" class="cox-loading-line">{{ tr('Загрузка БП...') }}</div>
        <div
          v-else-if="bpData && bpData.hasData"
          class="cox-bp-block"
        >
          <!-- Динамические строки: переключаются по bpView (Все/Доходы/Расходы) -->
          <template v-for="m in bpDisplayedMetrics" :key="m.label">
            <div class="cox-bp-row">
              <div class="cox-bp-row-head">
                <span class="cox-bp-row-label">{{ tr(m.label) }}</span>
                <span
                  v-if="m.d.hasPlan && m.d.hasFact && m.d.plan !== 0"
                  class="cox-bp-row-pct"
                  :class="pctClassBp(Math.round(((m.d.fact ?? 0) / (m.d.plan || 1)) * 100))"
                >
                  {{ Math.round(((m.d.fact ?? 0) / (m.d.plan || 1)) * 100) }}%
                </span>
                <span v-else class="cox-bp-row-pct cox-bp-empty">—</span>
              </div>
              <div class="cox-bp-vals">
                <div class="cox-bp-val">
                  <span class="cox-bp-val-cap">{{ tr('план') }}</span>
                  <span class="cox-bp-val-num" :class="{ 'cox-bp-empty': !m.d.hasPlan }">
                    {{ m.d.hasPlan ? fmtBp(m.d.plan) : '—' }}
                  </span>
                </div>
                <div class="cox-bp-val">
                  <span class="cox-bp-val-cap">{{ tr('факт') }}</span>
                  <span class="cox-bp-val-num cox-bp-fact" :class="{ 'cox-bp-empty': !m.d.hasFact }">
                    {{ m.d.hasFact ? fmtBp(m.d.fact) : '—' }}
                  </span>
                </div>
                <div v-if="m.d.expect != null" class="cox-bp-val">
                  <span class="cox-bp-val-cap">{{ tr('ожид.') }}</span>
                  <span class="cox-bp-val-num">{{ fmtBp(m.d.expect) }}</span>
                </div>
              </div>
              <div
                class="cox-bp-bar-track"
                :title="m.d.hasPlan && m.d.hasFact && m.d.plan !== 0
                  ? tr('{value0}: план {value1} · факт {value2} · {value3}% · Δ {value4}', { value0: m.label, value1: fmtBp(m.d.plan), value2: fmtBp(m.d.fact), value3: Math.round(((m.d.fact ?? 0) / (m.d.plan || 1)) * 100), value4: fmtBp((m.d.fact ?? 0) - (m.d.plan ?? 0)) })
                  : tr('{value0}: план {value1} · факт {value2}', { value0: m.label, value1: m.d.hasPlan ? fmtBp(m.d.plan) : '—', value2: m.d.hasFact ? fmtBp(m.d.fact) : tr('не введён') })"
              >
                <div
                  v-if="m.d.hasPlan && m.d.hasFact && m.d.plan !== 0"
                  class="cox-bp-bar-fill"
                  :class="pctClassBp(Math.round(((m.d.fact ?? 0) / (m.d.plan || 1)) * 100))"
                  :style="{ width: Math.min(100, Math.max(0, Math.round(((m.d.fact ?? 0) / (m.d.plan || 1)) * 100))) + '%' }"
                ></div>
              </div>
            </div>
          </template>
        </div>
        <!-- Sprint B · Prior-year baseline (gray reference values when current empty) -->
        <div v-else-if="bpBaseline" class="cox-bp-baseline">
          <div class="cox-bp-baseline-head">
            <span class="cox-bp-baseline-icon">↻</span>
            <span>{{ tr('Бизнес-план на') }} <b>{{ year }}</b> {{ tr('не заполнен. Факт за') }} <b>{{ bpBaseline.year }}</b>:</span>
          </div>
          <div class="cox-bp-baseline-rows">
            <div v-if="bpBaseline.revenue != null" class="cox-bp-baseline-row">
              <span>{{ tr('Выручка') }}</span>
              <span class="cox-bp-baseline-num">{{ fmtBp(bpBaseline.revenue) }}</span>
            </div>
            <div v-if="bpBaseline.opProfit != null" class="cox-bp-baseline-row">
              <span>{{ tr('Опер. прибыль') }}</span>
              <span class="cox-bp-baseline-num">{{ fmtBp(bpBaseline.opProfit) }}</span>
            </div>
            <div v-if="bpBaseline.profit != null" class="cox-bp-baseline-row">
              <span>{{ tr('Чистая прибыль') }}</span>
              <span class="cox-bp-baseline-num">{{ fmtBp(bpBaseline.profit) }}</span>
            </div>
          </div>
        </div>
        <div v-else class="cox-empty-line">
          {{ tr('Бизнес-план на') }} {{ year }} {{ tr('год не заполнен') }}
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
/* 2. ПО НАПРАВЛЕНИЯМ — 1:1 с легасиом (стрипа + бар + % + проекты + задачи) */
/* ============================================================ */
.cox-dir-head,
.cox-dir-row {
  display: grid;
  /* Имя получает ненулевой floor (88px), иначе фикс. колонки вытесняли 1fr-имя
     к нулю и название вставало столбиком по буквам. */
  grid-template-columns: 3px minmax(88px, 1fr) clamp(40px, 5vw, 56px) 28px clamp(44px, 5vw, 56px) clamp(44px, 5vw, 56px);
  align-items: center;
  gap: clamp(5px, 0.6vw, 8px);
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
  /* Не сокращаем названия направлений — переносим по СЛОВАМ (не anywhere,
     иначе при узкой колонке имя вставало в столбик по буквам). */
  white-space: normal;
  word-break: normal;
  overflow-wrap: break-word;
  hyphens: none;
  line-height: 1.25;
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
/* 4. ТРЕБУЮТ ВНИМАНИЯ — 1:1 с легасиом (список + Дедлайны) */
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
  width: 100%;
  padding: 5px 0;
  border: 0;
  border-bottom: 0.5px solid rgba(30, 42, 74, 0.06);
  background: transparent;
  color: inherit;
  font: inherit;
  text-align: left;
  cursor: pointer;
  border-radius: 3px;
  transition: background 0.12s;
}
.cox-attn-row:hover {
  background: rgba(30, 42, 74, 0.04);
}
.cox-attn-row:focus-visible,
.cox-attn-upcoming-row:focus-visible {
  outline: 2px solid rgba(127, 119, 221, 0.7);
  outline-offset: 2px;
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
  width: 100%;
  padding: 4px 0;
  border: 0;
  border-bottom: 0.5px solid rgba(30, 42, 74, 0.06);
  background: transparent;
  color: inherit;
  font: inherit;
  text-align: left;
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
/* 5. АКТИВНОСТЬ — icon-badge layout 1:1 с легасиом */
/* ============================================================ */
.cox-activity-list {
  display: flex;
  flex-direction: column;
}
/* Строка ленты — кнопка: вся площадь кликабельна и доступна с клавиатуры. */
.cox-activity-row {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  width: 100%;
  padding: 8px 10px;
  margin: 1px 0;
  border-radius: 10px;
  border: 1px solid transparent;
  background: transparent;
  font-family: inherit;
  text-align: left;
  cursor: pointer;
  position: relative;
  overflow: hidden;
  animation: coxFadeUp 0.45s var(--ease-standard, cubic-bezier(.34,1.2,.64,1)) both;
  animation-delay: var(--d, 0ms);
  transition: background .16s, border-color .16s, transform .16s, box-shadow .16s;
}
/* Акцент-полоска слева выезжает на наведении (цвет действия) */
.cox-activity-row::before {
  content: "";
  position: absolute; left: 0; top: 6px; bottom: 6px; width: 2.5px;
  border-radius: 0 3px 3px 0;
  background: var(--acc, #7C6FF7);
  transform: scaleY(0); transform-origin: center;
  transition: transform .2s var(--ease-standard, cubic-bezier(.34,1.2,.64,1));
}
.cox-activity-row:hover::before,
.cox-activity-row:focus-visible::before { transform: scaleY(1); }
.cox-activity-row:hover {
  background: rgba(127, 119, 221, .05);
  border-color: rgba(127, 119, 221, .14);
  transform: translateX(2px);
  box-shadow: 0 4px 14px rgba(15, 23, 60, .06);
}
.cox-activity-row:focus-visible {
  outline: 2px solid rgba(124, 111, 247, .55);
  outline-offset: 1px;
}
.cox-activity-row:active { transform: translateX(2px) scale(.994); }
.cox-activity-chev {
  color: rgba(148, 163, 184, .7);
  flex-shrink: 0; align-self: center;
  opacity: 0; transform: translateX(-4px);
  transition: opacity .16s, transform .16s;
}
.cox-activity-row:hover .cox-activity-chev,
.cox-activity-row:focus-visible .cox-activity-chev { opacity: 1; transform: translateX(0); }
.cox-activity-actor {
  font-weight: 600;
  color: var(--t2, #4B5468);
  max-width: 42%;
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}
.cox-activity-icon {
  width: 26px;
  height: 26px;
  border-radius: 9px;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  box-shadow: 0 0 0 3px color-mix(in srgb, currentColor 9%, transparent);
  animation: coxIconPop 0.4s var(--ease-standard, cubic-bezier(.34,1.2,.64,1)) both;
  transition: transform .15s;
}
.cox-activity-row:hover .cox-activity-icon { transform: scale(1.08); }
@keyframes coxIconPop { from { transform: scale(0); opacity: 0; } to { transform: scale(1); opacity: 1; } }
.cox-activity-body {
  flex: 1;
  min-width: 0;
  display: block;
}
.cox-activity-title {
  display: block;
  font-size: 13px;
  font-weight: 500;
  color: var(--t1, #1e2a4a);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.cox-activity-meta {
  display: flex;
  align-items: center;
  gap: 3px;
  justify-content: flex-start;
  font-size: 10px;
  color: rgba(148, 163, 184, 0.8);
  margin-top: 1px;
}
.cox-activity-time {
  font-weight: 500;
  margin-left: auto;
  white-space: nowrap;
  padding-left: 6px;
}

/* ── Детали события (модалка) ── */
.cox-actd-head { display: flex; align-items: center; gap: 8px; margin-bottom: 10px; }
.cox-actd-chip {
  font-size: 10px; font-weight: 700; letter-spacing: .04em; text-transform: uppercase;
  padding: 3px 10px; border-radius: 999px;
  color: var(--acc, #7C6FF7); background: color-mix(in srgb, var(--acc, #7C6FF7) 13%, transparent);
}
.cox-actd-ts { font-size: 11px; color: var(--t3, #94A3B8); margin-left: auto; }
.cox-actd-entity {
  font-size: 14.5px; font-weight: 600; color: var(--t1, #1E2A4A);
  line-height: 1.4; margin-bottom: 10px;
}
.cox-actd-text {
  font-size: 12.5px; color: var(--t2, #4B5468); line-height: 1.6;
  border-left: 2.5px solid var(--acc, #7C6FF7);
  padding: 2px 0 2px 11px; margin-bottom: 14px;
  max-height: 220px; overflow-y: auto; white-space: pre-wrap;
}
.cox-actd-meta {
  background: var(--bg2, #F8F9FC); border: 1px solid var(--border, #EEF0F5);
  border-radius: 12px; padding: 2px 13px;
}
.cox-actd-row { display: flex; align-items: center; gap: 10px; padding: 9px 0; }
.cox-actd-row + .cox-actd-row { border-top: 1px solid var(--border, #EEF0F5); }
.cox-actd-l {
  font-size: 10px; font-weight: 600; text-transform: uppercase; letter-spacing: .06em;
  color: var(--t3, #94A3B8); width: 52px; flex-shrink: 0;
}
.cox-actd-v { font-size: 12.5px; color: var(--t1, #1E2A4A); margin-left: auto; text-align: right; }
.cox-actd-v em { display: block; font-style: normal; font-size: 10.5px; color: var(--t3, #94A3B8); }
.cox-actd-open {
  display: inline-flex; align-items: center; gap: 5px; margin-right: auto;
  font-size: 12px; font-weight: 600; font-family: inherit;
  color: var(--p-deep, #534AB7); background: transparent;
  border: 1px solid var(--border-hard, #E5E7EB); border-radius: 10px;
  padding: 8px 14px; cursor: pointer; transition: background .12s, border-color .12s;
}
.cox-actd-open:hover { background: rgba(127,119,221,.08); border-color: rgba(127,119,221,.35); }
.cox-actd-close {
  font-size: 12.5px; font-weight: 600; font-family: inherit; color: #fff;
  background: linear-gradient(135deg, #8B7FFF 0%, #6C5CE7 100%);
  border: none; border-radius: 10px; padding: 9px 20px; cursor: pointer;
  box-shadow: 0 3px 12px rgba(108, 92, 231, .34); transition: transform .14s, box-shadow .14s;
}
.cox-actd-close:hover { transform: translateY(-1px); box-shadow: 0 6px 18px rgba(108, 92, 231, .45); }

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
  font-size: 9.5px;
  font-weight: 600;
  letter-spacing: 0.02em;
  background: rgba(127, 119, 221, .09);
  border: 1px solid rgba(127, 119, 221, .18);
  padding: 1px 7px;
  border-radius: 999px;
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
.cox-fallback-badge {
  font-size: 9px; font-weight: 600; letter-spacing: .02em;
  color: #B7791F; background: rgba(239, 159, 39, .14);
  padding: 2px 7px; border-radius: 999px; white-space: nowrap;
  text-transform: none; font-variant-numeric: tabular-nums;
}
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

/* модалка «Вся активность» — chrome теперь у ModalShell; здесь только тело */
.cox-act-modal-body { display: flex; flex-direction: column; }

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
  grid-template-columns: 10px 1fr;
  gap: 12px;
  padding: 10px 12px;
  border-radius: 11px;
  border: 1px solid transparent;
  transition: background .15s, border-color .15s, transform .15s, box-shadow .15s;
  animation: coxFadeUp .42s var(--ease-standard, cubic-bezier(.34,1.2,.64,1)) both;
}
.cox-act-full-item:nth-child(1) { animation-delay: 0ms; }
.cox-act-full-item:nth-child(2) { animation-delay: 35ms; }
.cox-act-full-item:nth-child(3) { animation-delay: 70ms; }
.cox-act-full-item:nth-child(4) { animation-delay: 105ms; }
.cox-act-full-item:nth-child(5) { animation-delay: 140ms; }
.cox-act-full-item:nth-child(6) { animation-delay: 175ms; }
.cox-act-full-item:hover {
  background: rgba(127, 119, 221, .05);
  border-color: rgba(127, 119, 221, .14);
  transform: translateX(2px);
  box-shadow: 0 4px 14px rgba(15, 23, 60, .06);
}
.cox-act-full-dot {
  width: 9px;
  height: 9px;
  border-radius: 50%;
  margin-top: 6px;
  box-shadow: 0 0 0 3px var(--bg1, #fff), 0 0 0 4.5px rgba(15, 23, 60, .07);
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
