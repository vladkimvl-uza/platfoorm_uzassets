<script setup lang="ts">
/**
 * KpiDrillModal.vue
 * ─────────────────────────────────────────────────────────────────
 * Premium drill-down modal for the 6 KPI cells of Row 2
 * (ExecDashBottomMetrics): Проектов, Задач, Завершено-проекты,
 * Завершено-задачи, Перенесено-задачи, Средний прогресс.
 *
 * Один компонент → 3 внутренних шаблона переключаются по prop `kind`:
 *   • inventory    — для 'projects' и 'tasks':
 *                    status breakdown + sector grid + top-5 компаний
 *   • funnel       — для 'done_projects', 'done_tasks', 'deferred_tasks':
 *                    воронка по статусам + % по секторам + последние 4 изменения
 *   • distribution — для 'avg_progress':
 *                    гистограмма распределения + средний по секторам + лидеры/аутсайдеры
 *
 * Данные:
 *   • Базовые агрегаты — exec.data.value.bottom_metrics + sectors[]
 *   • Status breakdown — лениво из projectsApi.list({limit:1}) / tasksApi.list({limit:1})
 *     (берём поле by_status, которое не зависит от limit/offset)
 *   • Последние завершения / переносы — projectsApi.list / tasksApi.list
 *     с status="done" / status="deferred" (бэкенд поддерживает оба)
 *
 * Pack 7.30
 */
import { computed, onMounted, onUnmounted, ref } from "vue";
import { useFocusTrap } from "@/composables/useFocusTrap";
import { useRouter } from "vue-router";
import { useExecutiveDashboard } from "@/composables/useExecutiveDashboard";
import { useCompaniesStore } from "@/stores/companies";
import { tasksApi } from "@/api/tasks";
import { projectsApi } from "@/api/projects";

export type KpiKind =
  | "projects"
  | "tasks"
  | "done_projects"
  | "done_tasks"
  | "deferred_tasks"
  | "avg_progress";

interface Props {
  kind: KpiKind;
}
const props = defineProps<Props>();
const emit = defineEmits<{ close: [] }>();

const router = useRouter();
const exec = useExecutiveDashboard();
const companies = useCompaniesStore();

// ─── KPI metadata ───
interface KpiMeta {
  label: string;
  template: "inventory" | "funnel" | "distribution";
  color: string;          // sector-color analogue для stripe
  cta: string;            // text on the primary footer button
  route: { name: string; query?: Record<string, string | number> };
  /** Какой объект показывают? проекты или задачи (влияет на надписи). */
  unit: "projects" | "tasks" | "mixed";
}

const KPI_META: Record<KpiKind, KpiMeta> = {
  projects: {
    label: "Проектов в портфеле",
    template: "inventory",
    color: "#7F77DD",
    cta: "Открыть все проекты",
    route: { name: "projects" },
    unit: "projects",
  },
  tasks: {
    label: "Задач в портфеле",
    template: "inventory",
    color: "#7F77DD",
    cta: "Открыть все задачи",
    route: { name: "dashboard" },
    unit: "tasks",
  },
  done_projects: {
    label: "Завершено · Проекты",
    template: "funnel",
    color: "#1D9E75",
    cta: "Открыть завершённые проекты",
    route: { name: "projects", query: { status: "done" } },
    unit: "projects",
  },
  done_tasks: {
    label: "Завершено · Задачи",
    template: "funnel",
    color: "#1D9E75",
    cta: "Открыть завершённые задачи",
    route: { name: "dashboard", query: { status: "done" } },
    unit: "tasks",
  },
  deferred_tasks: {
    label: "Перенесено · Задачи",
    template: "funnel",
    color: "#7F77DD",
    cta: "Открыть все задачи",
    route: { name: "dashboard" },
    unit: "tasks",
  },
  avg_progress: {
    label: "Средний прогресс портфеля",
    template: "distribution",
    color: "#EF9F27",
    cta: "Исполнение по компаниям",
    route: { name: "companies" },
    unit: "mixed",
  },
};

const meta = computed(() => KPI_META[props.kind]);

// ─── Helpers ───
function pct(num: number, den: number): number {
  if (!den) return 0;
  return Math.max(0, Math.min(100, Math.round((num / den) * 100)));
}

const bm = computed(() => exec.data.value?.bottom_metrics ?? null);
const sectors = computed(() => exec.data.value?.sectors ?? []);
const year = computed(() => exec.year.value);

// ─── Header big value + sub ───
interface HeaderValue {
  bigNum: number | string;
  sub: string | null;
  pctOfBase: number | null;
  badge: { text: string; tone: "good" | "bad" | "neutral" } | null;
}
const headerValue = computed<HeaderValue>(() => {
  const m = bm.value;
  if (!m) return { bigNum: "—", sub: null, pctOfBase: null, badge: null };
  switch (props.kind) {
    case "projects":
      return {
        bigNum: m.proj_count,
        sub: `${companies.totalCount} компаний · 5 секторов · FY ${year.value}`,
        pctOfBase: null,
        badge: null,
      };
    case "tasks":
      return {
        bigNum: m.task_count,
        sub: `${companies.totalCount} компаний · ${m.proj_count} проектов · FY ${year.value}`,
        pctOfBase: null,
        badge: null,
      };
    case "done_projects": {
      const p = pct(m.done_proj, m.proj_count);
      return {
        bigNum: m.done_proj,
        sub: `из ${m.proj_count}`,
        pctOfBase: p,
        badge: { text: `${p}% завершения`, tone: "good" },
      };
    }
    case "done_tasks": {
      const p = pct(m.done_tasks, m.task_count);
      return {
        bigNum: m.done_tasks,
        sub: `из ${m.task_count}`,
        pctOfBase: p,
        badge: { text: `${p}% завершения`, tone: "good" },
      };
    }
    case "deferred_tasks": {
      const p = pct(m.deferred_tasks, m.task_count);
      return {
        bigNum: m.deferred_tasks,
        sub: `из ${m.task_count}`,
        pctOfBase: p,
        badge: { text: `${p}% перенесённых`, tone: "bad" },
      };
    }
    case "avg_progress":
      return {
        bigNum: `${m.avg_completion}%`,
        sub: null,
        pctOfBase: null,
        badge: null,
      };
    default:
      return { bigNum: "—", sub: null, pctOfBase: null, badge: null };
  }
});

// ─── Sector breakdown — common computed from sectors[] ───
interface SectorRow {
  id: string;
  label: string;
  color: string;
  total: number;
  done: number;
  avg_pct: number;
  pct_done: number;
}
const sectorRows = computed<SectorRow[]>(() => {
  return sectors.value.map((s) => {
    const total = s.companies.reduce((a, c) => a + (c.task_total || 0), 0);
    const done = s.companies.reduce((a, c) => a + (c.task_done || 0), 0);
    return {
      id: s.id,
      label: s.label,
      color: s.color,
      total,
      done,
      avg_pct: s.avg_pct,
      pct_done: total > 0 ? Math.round((done / total) * 100) : 0,
    };
  });
});

// ─── Top-5 companies (by task_total) — for inventory ───
interface TopCompany {
  company_id: string;
  name: string;
  task_total: number;
  task_done: number;
  pct: number;
  sector_color: string;
  board_id: string | null;
}
const topCompanies = computed<TopCompany[]>(() => {
  const all: TopCompany[] = [];
  for (const s of sectors.value) {
    for (const c of s.companies) {
      all.push({
        company_id: c.company_id,
        name: companies.getCompanyNameById(c.company_id) || c.name,
        task_total: c.task_total || 0,
        task_done: c.task_done || 0,
        pct: c.pct,
        sector_color: s.color,
        board_id: c.board_id || null,
      });
    }
  }
  all.sort((a, b) => b.task_total - a.task_total);
  return all.slice(0, 5);
});

const topMaxTotal = computed(() => topCompanies.value[0]?.task_total || 1);

// ─── Histogram — for distribution ───
interface HistoBucket {
  label: string;
  min: number;
  max: number;
  color: string;
  count: number;
  pctHeight: number; // 0..100
}
const histogram = computed<HistoBucket[]>(() => {
  const buckets = [
    { label: "0–20%", min: 0, max: 20, color: "#E24B4A" },
    { label: "21–40%", min: 21, max: 40, color: "#EF9F27" },
    { label: "41–60%", min: 41, max: 60, color: "#7F77DD" },
    { label: "61–80%", min: 61, max: 80, color: "#378ADD" },
    { label: "81–100%", min: 81, max: 100, color: "#1D9E75" },
  ];
  const counts = buckets.map(() => 0);
  for (const s of sectors.value) {
    for (const c of s.companies) {
      const p = c.pct;
      for (let i = 0; i < buckets.length; i++) {
        if (p >= buckets[i].min && p <= buckets[i].max) {
          counts[i]++;
          break;
        }
      }
    }
  }
  const maxCount = Math.max(1, ...counts);
  return buckets.map((b, i) => ({
    ...b,
    count: counts[i],
    pctHeight: Math.round((counts[i] / maxCount) * 100),
  }));
});

// ─── Leaders / Laggards — top-3 / bottom-3 by pct ───
interface CompanyRanked {
  company_id: string;
  name: string;
  pct: number;
}
const leadersLaggards = computed<{ leaders: CompanyRanked[]; laggards: CompanyRanked[] }>(() => {
  const all: CompanyRanked[] = [];
  for (const s of sectors.value) {
    for (const c of s.companies) {
      all.push({
        company_id: c.company_id,
        name: companies.getCompanyNameById(c.company_id) || c.name,
        pct: c.pct,
      });
    }
  }
  const sortedDesc = [...all].sort((a, b) => b.pct - a.pct);
  const sortedAsc = [...all].sort((a, b) => a.pct - b.pct);
  return {
    leaders: sortedDesc.slice(0, 3),
    laggards: sortedAsc.slice(0, 3),
  };
});

// ─── Status breakdown (inventory: projects/tasks) — lazy fetch ───
interface StatusSeg {
  code: string;
  label: string;
  color: string;
  count: number;
}
const statusSegs = ref<StatusSeg[]>([]);
const loadingStatus = ref(false);
const totalCount = computed(() => statusSegs.value.reduce((a, s) => a + s.count, 0));

const STATUS_VIS: Array<{ codes: string[]; label: string; color: string }> = [
  { codes: ["done"],                                  label: "Завершено",     color: "#1D9E75" },
  { codes: ["active", "in_progress", "review"],       label: "В работе",      color: "#EF9F27" },
  { codes: ["init", "new"],                           label: "Инициирование", color: "#378ADD" },
  { codes: ["quarterly", "monthly", "ongoing"],       label: "Регулярные",    color: "#888780" },
];

async function loadInventoryStatus() {
  if (meta.value.template !== "inventory") return;
  loadingStatus.value = true;
  try {
    let by: Record<string, number> = {};
    const yr = year.value || undefined;
    if (props.kind === "projects") {
      // Backend /projects supports the same status enum and returns by_status aggregates
      const resp = await projectsApi.list({ portfolio_year: yr, limit: 1 });
      by = resp.by_status || {};
    } else if (props.kind === "tasks") {
      // is_project is not a backend filter; tasksApi.list aggregates over ALL items
      const resp = await tasksApi.list({ portfolio_year: yr, limit: 1 });
      by = resp.by_status || {};
    }
    const segs: StatusSeg[] = [];
    for (const vis of STATUS_VIS) {
      const cnt = vis.codes.reduce((a, c) => a + (by[c] || 0), 0);
      if (cnt > 0) segs.push({ code: vis.codes[0], label: vis.label, color: vis.color, count: cnt });
    }
    // Fallback: если backend вернул пустой by_status — используем bottom_metrics
    if (!segs.length && bm.value) {
      const total = props.kind === "projects" ? bm.value.proj_count : bm.value.task_count;
      const done = props.kind === "projects" ? bm.value.done_proj : bm.value.done_tasks;
      segs.push({ code: "done", label: "Завершено", color: "#1D9E75", count: done });
      segs.push({ code: "active", label: "В работе", color: "#EF9F27", count: Math.max(0, total - done) });
    }
    statusSegs.value = segs;
  } catch (e) {
    if (bm.value) {
      const total = props.kind === "projects" ? bm.value.proj_count : bm.value.task_count;
      const done = props.kind === "projects" ? bm.value.done_proj : bm.value.done_tasks;
      statusSegs.value = [
        { code: "done", label: "Завершено", color: "#1D9E75", count: done },
        { code: "active", label: "В работе", color: "#EF9F27", count: Math.max(0, total - done) },
      ];
    }
  } finally {
    loadingStatus.value = false;
  }
}

// ─── Funnel computed ───
interface FunnelSeg {
  label: string;
  color: string;
  count: number;
  pct: number;
  highlight?: boolean;
}
const funnelSegs = computed<FunnelSeg[]>(() => {
  const m = bm.value;
  if (!m) return [];
  const isProj = props.kind === "done_projects";
  const isDeferredTasks = props.kind === "deferred_tasks";
  const total = isProj ? m.proj_count : m.task_count;
  const done = isProj ? m.done_proj : m.done_tasks;
  const deferred = isProj ? m.deferred_proj : m.deferred_tasks;
  const inProg = Math.max(0, total - done - deferred);

  return [
    {
      label: "Завершено",
      color: "#1D9E75",
      count: done,
      pct: pct(done, total),
      highlight: props.kind === "done_projects" || props.kind === "done_tasks",
    },
    {
      label: "В работе",
      color: "#EF9F27",
      count: inProg,
      pct: pct(inProg, total),
    },
    {
      label: "Перенесено",
      color: "#7F77DD",
      count: deferred,
      pct: pct(deferred, total),
      highlight: isDeferredTasks,
    },
  ].filter((s) => s.count > 0);
});

const funnelTotal = computed(() => {
  const m = bm.value;
  if (!m) return 0;
  return props.kind === "done_projects" ? m.proj_count : m.task_count;
});

// ─── Recent items (funnel kinds) — lazy fetch ───
// Union shape — оба TaskBrief и ProjectBrief удовлетворяют этим полям
interface RecentItem {
  id: string;
  num: string | null;
  title: string;
  company_id: string | null;
  company_code: string | null;
  board_id: string | null;
  updated_at: string;
}
const recentItems = ref<RecentItem[]>([]);
const loadingRecent = ref(false);

async function loadRecent() {
  if (meta.value.template !== "funnel") return;
  loadingRecent.value = true;
  try {
    const yr = year.value || undefined;
    if (props.kind === "done_projects") {
      const resp = await projectsApi.list({
        status: "done",
        sort_by: "updated_at",
        sort_dir: "desc",
        limit: 4,
        portfolio_year: yr,
      });
      recentItems.value = resp.items.slice(0, 4) as RecentItem[];
    } else if (props.kind === "done_tasks") {
      const resp = await tasksApi.list({
        status: "done",
        sort_by: "updated_at",
        sort_dir: "desc",
        limit: 4,
        portfolio_year: yr,
      });
      recentItems.value = resp.items.slice(0, 4) as RecentItem[];
    } else if (props.kind === "deferred_tasks") {
      // Backend поддерживает status="deferred" (linked_year IS NOT NULL)
      const resp = await tasksApi.list({
        status: "deferred",
        sort_by: "updated_at",
        sort_dir: "desc",
        limit: 4,
        portfolio_year: yr,
      });
      recentItems.value = resp.items.slice(0, 4) as RecentItem[];
    }
  } catch {
    recentItems.value = [];
  } finally {
    loadingRecent.value = false;
  }
}

function fmtDate(iso: string | null): string {
  if (!iso) return "—";
  try {
    const d = new Date(iso);
    return d.toLocaleDateString("ru-RU", { day: "numeric", month: "short" });
  } catch {
    return "—";
  }
}

// ─── Count-up for header big number ───
const headerNumDisplay = ref<number | string>(
  typeof headerValue.value.bigNum === "number" ? 0 : headerValue.value.bigNum,
);
function startCountUp() {
  const target = headerValue.value.bigNum;
  if (typeof target !== "number") {
    headerNumDisplay.value = target;
    return;
  }
  const start = performance.now();
  const dur = 1200;
  function tick(now: number) {
    const t = Math.min(1, (now - start) / dur);
    const eased = 1 - Math.pow(1 - t, 3);
    headerNumDisplay.value = Math.round(target * eased);
    if (t < 1) requestAnimationFrame(tick);
  }
  setTimeout(() => requestAnimationFrame(tick), 350);
}

// ─── Close / nav ───
function close() {
  emit("close");
}
function onBackdrop(e: MouseEvent) {
  if (e.target === e.currentTarget) close();
}
function onKey(e: KeyboardEvent) {
  if (e.key === "Escape") {
    e.preventDefault();
    close();
  }
}

// a11y: фокус-трап диалога + возврат фокуса при закрытии
const cardEl = ref<HTMLElement | null>(null);
useFocusTrap(cardEl);

function gotoCta() {
  const m = meta.value;
  const query: Record<string, string | number> = { ...(m.route.query || {}) };
  if (year.value) query.year = year.value;
  router.push({ name: m.route.name, query });
  close();
}

function gotoCompany(c: { company_id: string; board_id?: string | null }) {
  const lite = companies.findById(c.company_id);
  if (lite?.code) {
    router.push({ name: "company-workspace", params: { code: lite.code } });
  } else {
    router.push({ name: "company-detail", params: { id: c.company_id } });
  }
  close();
}

function gotoTask(t: RecentItem) {
  if (t.board_id) {
    router.push({ name: "board-kanban", params: { id: t.board_id } });
  } else if (t.company_code) {
    router.push({ name: "company-workspace", params: { code: t.company_code } });
  } else {
    router.push({ name: "dashboard" });
  }
  close();
}

// ─── Lifecycle ───
let prevOverflow = "";
onMounted(() => {
  prevOverflow = document.body.style.overflow;
  document.body.style.overflow = "hidden";
  window.addEventListener("keydown", onKey);
  void companies.ensureLoaded();
  startCountUp();
  void loadInventoryStatus();
  void loadRecent();
});
onUnmounted(() => {
  document.body.style.overflow = prevOverflow;
  window.removeEventListener("keydown", onKey);
});
</script>

<template>
  <Teleport to="body">
    <Transition name="uza-fade">
      <div class="kdm-bd" @click="onBackdrop" role="dialog" aria-modal="true">
        <div ref="cardEl" tabindex="-1" class="kdm-card" :style="{ '--sc': meta.color }">
          <div class="kdm-stripe" aria-hidden="true" />
          <div class="kdm-shim" aria-hidden="true" />
          <div class="kdm-glow" aria-hidden="true" />

          <button class="kdm-x" @click="close" aria-label="Закрыть">
            <svg viewBox="0 0 14 14" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round" width="13" height="13">
              <path d="M3.5 3.5l7 7M10.5 3.5l-7 7"/>
            </svg>
          </button>

          <!-- ─── HEADER ─── -->
          <div class="kdm-hdr kdm-row" style="--si:0">
            <div class="kdm-hdr-l">
              <div class="kdm-h-l">{{ meta.label }}</div>
              <div class="kdm-h-v">
                <span class="num">{{ headerNumDisplay }}</span><span v-if="headerValue.sub" class="sub"> · {{ headerValue.sub }}</span>
              </div>
              <span
                v-if="headerValue.badge"
                class="kdm-h-d"
                :class="`kdm-h-d--${headerValue.badge.tone}`"
              >{{ headerValue.badge.text }}</span>
            </div>
            <div v-if="!headerValue.badge" class="kdm-hdr-r">
              <div class="kdm-h-tag">FY {{ year }}</div>
            </div>
          </div>

          <!-- ════════════════════════════════════════ -->
          <!--  TEMPLATE 1 · INVENTORY                  -->
          <!--  (projects, tasks)                       -->
          <!-- ════════════════════════════════════════ -->
          <template v-if="meta.template === 'inventory'">
            <!-- Status breakdown -->
            <div class="kdm-sect kdm-row" style="--si:1">
              <div class="kdm-l-sec">По статусу</div>
              <div v-if="loadingStatus && !statusSegs.length" class="kdm-skel-bar" />
              <template v-else-if="statusSegs.length">
                <div class="kdm-bar">
                  <div
                    v-for="(s, i) in statusSegs"
                    :key="s.code"
                    class="kdm-bar-seg"
                    :style="{
                      background: s.color,
                      flex: `0 0 ${pct(s.count, totalCount)}%`,
                      animationDelay: (0.5 + i * 0.13) + 's',
                    }"
                  />
                </div>
                <div class="kdm-leg">
                  <span v-for="s in statusSegs" :key="s.code">
                    <i class="kdm-dot" :style="{ background: s.color }"/>
                    {{ s.label }} · <strong>{{ s.count }}</strong>
                    <span class="kdm-leg-pct">{{ pct(s.count, totalCount) }}%</span>
                  </span>
                </div>
              </template>
              <div v-else class="kdm-empty">Нет данных по статусам</div>
            </div>

            <!-- Sector breakdown grid -->
            <div class="kdm-sect kdm-row" style="--si:2">
              <div class="kdm-l-sec">По секторам</div>
              <div class="kdm-sec-grid">
                <div
                  v-for="(s, i) in sectorRows"
                  :key="s.id"
                  class="kdm-mini-kpi"
                  :style="{ '--kc': s.color, '--ki': i }"
                >
                  <div class="kdm-mk-l">{{ s.label }}</div>
                  <div class="kdm-mk-v">{{ s.total }}</div>
                  <div class="kdm-mk-d">{{ s.done }} завершено · {{ s.pct_done }}%</div>
                </div>
              </div>
            </div>

            <!-- Top-5 companies -->
            <div class="kdm-sect kdm-row" style="--si:3">
              <div class="kdm-l-sec">Top-5 компаний по объёму</div>
              <div class="kdm-toplist">
                <div
                  v-for="(c, i) in topCompanies"
                  :key="c.company_id"
                  class="kdm-top-row"
                  @click="gotoCompany(c)"
                  :title="'Открыть карточку «' + c.name + '»'"
                >
                  <span class="kdm-top-name">
                    <i class="kdm-top-tick" :style="{ background: c.sector_color }"/>
                    {{ c.name }}
                  </span>
                  <span class="kdm-top-bar">
                    <span
                      class="kdm-top-fill"
                      :style="{
                        background: c.sector_color,
                        width: ((c.task_total / topMaxTotal) * 100) + '%',
                        animationDelay: (1.0 + i * 0.07) + 's',
                      }"
                    />
                  </span>
                  <span class="kdm-top-val">{{ c.task_total }}</span>
                </div>
              </div>
            </div>
          </template>

          <!-- ════════════════════════════════════════ -->
          <!--  TEMPLATE 2 · FUNNEL                     -->
          <!--  (done_projects, done_tasks, deferred)   -->
          <!-- ════════════════════════════════════════ -->
          <template v-if="meta.template === 'funnel'">
            <!-- Funnel bar -->
            <div class="kdm-sect kdm-row" style="--si:1">
              <div class="kdm-l-sec">Воронка статусов · всего {{ funnelTotal }}</div>
              <div class="kdm-bar kdm-bar--lg">
                <div
                  v-for="(s, i) in funnelSegs"
                  :key="s.label"
                  class="kdm-bar-seg kdm-bar-seg--lg"
                  :class="{ 'kdm-bar-seg--dim': !s.highlight && funnelSegs.some(x => x.highlight) }"
                  :style="{
                    background: s.color,
                    flex: `0 0 ${s.pct}%`,
                    animationDelay: (0.5 + i * 0.16) + 's',
                  }"
                >
                  <span v-if="s.pct >= 8" class="kdm-bar-lbl">{{ s.count }} · {{ s.pct }}%</span>
                </div>
              </div>
              <div class="kdm-leg">
                <span v-for="s in funnelSegs" :key="s.label">
                  <i class="kdm-dot" :style="{ background: s.color }"/>
                  {{ s.label }}
                </span>
              </div>
            </div>

            <!-- Per-sector progress -->
            <div class="kdm-sect kdm-row" style="--si:2">
              <div class="kdm-l-sec">% завершения по секторам</div>
              <div class="kdm-row-list">
                <div
                  v-for="(s, i) in sectorRows"
                  :key="s.id"
                  class="kdm-sec-row"
                >
                  <span class="kdm-sec-name">
                    <i class="kdm-top-tick" :style="{ background: s.color }"/>
                    {{ s.label }}
                  </span>
                  <span class="kdm-sec-bar">
                    <span
                      class="kdm-sec-fill"
                      :style="{
                        background: s.color,
                        width: s.pct_done + '%',
                        animationDelay: (0.9 + i * 0.07) + 's',
                      }"
                    />
                  </span>
                  <span class="kdm-sec-val" :style="{ color: s.color }">{{ s.done }} / {{ s.total }}</span>
                </div>
              </div>
            </div>

            <!-- Recent items -->
            <div class="kdm-sect kdm-row" style="--si:3" v-if="meta.template === 'funnel'">
              <div class="kdm-l-sec">Последние 4 изменения</div>
              <div v-if="loadingRecent && !recentItems.length" class="kdm-skel-list">
                <div class="kdm-skel-row" v-for="i in 4" :key="i"/>
              </div>
              <div v-else-if="recentItems.length" class="kdm-recent">
                <div
                  v-for="t in recentItems"
                  :key="t.id"
                  class="kdm-recent-row"
                  @click="gotoTask(t)"
                  :title="'Открыть задачу'"
                >
                  <span class="kdm-recent-ic" :style="{ color: meta.color }">
                    <svg viewBox="0 0 14 14" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" width="11" height="11">
                      <circle cx="7" cy="7" r="5.5"/>
                      <path d="M4.5 7l2 2 3-3.5"/>
                    </svg>
                  </span>
                  <span class="kdm-recent-meta">
                    <span class="kdm-recent-co">{{ companies.getCompanyNameById(t.company_id) || '—' }}</span>
                    <span class="kdm-recent-sep"> · </span>
                    <span class="kdm-recent-ttl">{{ t.num ? t.num + ' ' : '' }}{{ t.title }}</span>
                  </span>
                  <span class="kdm-recent-date">{{ fmtDate(t.updated_at) }}</span>
                </div>
              </div>
              <div v-else class="kdm-empty">Нет недавних изменений</div>
            </div>
          </template>

          <!-- ════════════════════════════════════════ -->
          <!--  TEMPLATE 3 · DISTRIBUTION               -->
          <!--  (avg_progress)                          -->
          <!-- ════════════════════════════════════════ -->
          <template v-if="meta.template === 'distribution'">
            <!-- Histogram -->
            <div class="kdm-sect kdm-row" style="--si:1">
              <div class="kdm-l-sec">Распределение компаний по % прогресса</div>
              <div class="kdm-histo">
                <div
                  v-for="(b, i) in histogram"
                  :key="b.label"
                  class="kdm-hbar-col"
                >
                  <div class="kdm-hbar-cnt">{{ b.count }}</div>
                  <div
                    class="kdm-hbar"
                    :style="{
                      background: b.color,
                      height: b.pctHeight + '%',
                      animationDelay: (0.5 + i * 0.12) + 's',
                    }"
                  />
                  <div class="kdm-hbar-l">{{ b.label }}</div>
                </div>
              </div>
            </div>

            <!-- Per-sector average -->
            <div class="kdm-sect kdm-row" style="--si:2">
              <div class="kdm-l-sec">Средний по сектору</div>
              <div class="kdm-row-list">
                <div
                  v-for="(s, i) in [...sectorRows].sort((a, b) => b.avg_pct - a.avg_pct)"
                  :key="s.id"
                  class="kdm-sec-row"
                >
                  <span class="kdm-sec-name">
                    <i class="kdm-top-tick" :style="{ background: s.color }"/>
                    {{ s.label }}
                  </span>
                  <span class="kdm-sec-bar">
                    <span
                      class="kdm-sec-fill"
                      :style="{
                        background: s.color,
                        width: s.avg_pct + '%',
                        animationDelay: (0.9 + i * 0.07) + 's',
                      }"
                    />
                  </span>
                  <span class="kdm-sec-val" :style="{ color: s.color }">{{ s.avg_pct }}%</span>
                </div>
              </div>
            </div>

            <!-- Leaders / Laggards -->
            <div class="kdm-sect kdm-row kdm-ll" style="--si:3">
              <div>
                <div class="kdm-l-sec" style="color:#0F6E56;">↑ Лидеры</div>
                <div class="kdm-ll-list">
                  <div
                    v-for="c in leadersLaggards.leaders"
                    :key="c.company_id"
                    class="kdm-ll-row"
                    @click="gotoCompany(c)"
                  >
                    <span class="name">{{ c.name }}</span>
                    <span class="val" style="color:#0F6E56;">{{ c.pct }}%</span>
                  </div>
                </div>
              </div>
              <div>
                <div class="kdm-l-sec" style="color:#A32D2D;">↓ Аутсайдеры</div>
                <div class="kdm-ll-list">
                  <div
                    v-for="c in leadersLaggards.laggards"
                    :key="c.company_id"
                    class="kdm-ll-row"
                    @click="gotoCompany(c)"
                  >
                    <span class="name">{{ c.name }}</span>
                    <span class="val" :style="{ color: c.pct < 25 ? '#A32D2D' : '#854F0B' }">{{ c.pct }}%</span>
                  </div>
                </div>
              </div>
            </div>
          </template>

          <!-- ─── FOOTER ─── -->
          <div class="kdm-ftr kdm-row" style="--si:4">
            <button class="kdm-btn kdm-btn-g" @click="close">Закрыть</button>
            <button class="kdm-btn kdm-btn-p" @click="gotoCta">
              {{ meta.cta }}
              <svg viewBox="0 0 14 14" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round" width="12" height="12">
                <path d="M3 7h8M7.5 3.5L11 7l-3.5 3.5"/>
              </svg>
            </button>
          </div>
        </div>
      </div>
    </Transition>
  </Teleport>
</template>

<style scoped>
.kdm-bd {
  position: fixed;
  inset: 0;
  background: rgba(15, 18, 40, 0.45);
  -webkit-backdrop-filter: blur(8px);
  backdrop-filter: blur(8px);
  z-index: 9000;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 24px 16px;
  overflow-y: auto;
}
.kdm-card {
  position: relative;
  background: var(--bg1, #fff);
  border: 1px solid var(--card-border, transparent);
  border-radius: 14px;
  box-shadow: 0 24px 64px rgba(15, 23, 60, 0.22), 0 8px 24px rgba(15, 23, 60, 0.10);
  width: 100%;
  max-width: 720px;
  overflow: hidden;
  animation: kdmIn .55s var(--ease-standard) .08s both;
}
.kdm-stripe {
  position: absolute;
  top: 0; left: 0; right: 0;
  height: 3px;
  background: var(--sc);
  transform-origin: left center;
  animation: kdmStripe .75s var(--ease-standard) .2s both;
  z-index: 3;
}
.kdm-shim {
  position: absolute;
  top: 0; left: 0; right: 0;
  height: 3px;
  background: linear-gradient(90deg, transparent, rgba(255, 255, 255, 0.75), transparent);
  transform: translateX(-120%);
  animation: kdmShim 6s ease-in-out 1.5s infinite;
  pointer-events: none;
  z-index: 4;
}
.kdm-glow {
  position: absolute;
  inset: 0;
  background: radial-gradient(circle at 92% -6%, var(--sc), transparent 42%);
  opacity: 0.07;
  pointer-events: none;
  z-index: 1;
}
.kdm-x {
  position: absolute;
  top: 14px; right: 14px;
  width: 28px; height: 28px;
  border-radius: 8px;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  color: var(--t3, var(--t-muted));
  border: 1px solid rgba(0, 0, 0, 0.06);
  background: var(--bg1, #fff);
  z-index: 6;
  transition: all .14s;
}
.kdm-x:hover { background: var(--bg2, #FAFAFC); color: var(--t1, #1E2A4A); border-color: rgba(0,0,0,.10); }

.kdm-row {
  animation: kdmUp .42s ease both;
  animation-delay: calc(.32s + var(--si, 0) * .06s);
  opacity: 0;
  position: relative;
  z-index: 2;
}

.kdm-hdr {
  padding: 20px 22px 14px;
  display: flex;
  justify-content: space-between;
  align-items: flex-end;
  gap: 18px;
  flex-wrap: wrap;
  border-bottom: 1px solid rgba(0, 0, 0, 0.05);
}
.kdm-h-l {
  font-size: 10.5px;
  font-weight: 500;
  color: var(--t3, var(--t-muted));
  text-transform: uppercase;
  letter-spacing: .08em;
}
.kdm-h-v {
  font-size: 46px;
  font-weight: 500;
  letter-spacing: -.035em;
  line-height: 1;
  color: var(--t1, #1E2A4A);
  font-feature-settings: "tnum";
  margin-top: 4px;
  display: flex;
  align-items: baseline;
  gap: 8px;
  flex-wrap: wrap;
}
.kdm-h-v .num { display: inline-block; min-width: 0; }
.kdm-h-v .sub {
  font-size: 13px;
  color: var(--t3, var(--t-muted));
  font-weight: 500;
  letter-spacing: 0;
}
.kdm-h-d {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: 11px;
  font-weight: 500;
  padding: 3px 9px;
  border-radius: 999px;
  margin-top: 8px;
}
.kdm-h-d--good { background: rgba(29, 158, 117, .10); color: #0F6E56; }
.kdm-h-d--bad  { background: rgba(127, 119, 221, .10); color: var(--p-deep); }
.kdm-h-d--neutral { background: rgba(136, 135, 128, .10); color: var(--t3, #5F5E5A); }
.kdm-h-tag {
  font-size: 11px;
  color: var(--t3, var(--t-muted));
  font-weight: 500;
  padding: 4px 10px;
  background: var(--bg2, #FAFAFC);
  border: 1px solid rgba(0,0,0,.05);
  border-radius: 7px;
  letter-spacing: .03em;
}

.kdm-sect { padding: 14px 22px; }
.kdm-sect + .kdm-sect { padding-top: 0; }
.kdm-l-sec {
  font-size: 10px;
  color: var(--t3, var(--t-muted));
  text-transform: uppercase;
  letter-spacing: .07em;
  font-weight: 500;
  margin-bottom: 8px;
}

/* Bars */
.kdm-bar {
  height: 11px;
  background: #F1EFE8;
  border-radius: 5px;
  overflow: hidden;
  display: flex;
}
.kdm-bar--lg { height: 36px; border-radius: 7px; }
.kdm-bar-seg {
  height: 100%;
  transform: scaleX(0);
  transform-origin: left;
  animation: kdmBar 1.1s var(--ease-standard) forwards;
}
.kdm-bar-seg--lg {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  padding: 0 9px;
  color: #fff;
  font-size: 11px;
  font-weight: 500;
}
.kdm-bar-seg--dim { opacity: .35; }
.kdm-bar-lbl { font-feature-settings: "tnum"; white-space: nowrap; }

.kdm-leg {
  display: flex;
  gap: 16px;
  margin-top: 9px;
  font-size: 11px;
  color: var(--t3, #5F5E5A);
  font-weight: 500;
  flex-wrap: wrap;
}
.kdm-leg strong { color: var(--t1, #1E2A4A); font-weight: 500; font-feature-settings: "tnum"; }
.kdm-leg-pct { color: var(--t3, var(--t-muted)); margin-left: 3px; font-feature-settings: "tnum"; }
.kdm-dot {
  display: inline-block;
  width: 8px; height: 8px;
  border-radius: 50%;
  margin-right: 6px;
  vertical-align: 1px;
}

/* Sector grid (inventory) */
.kdm-sec-grid {
  display: grid;
  grid-template-columns: repeat(5, 1fr);
  gap: 7px;
}
.kdm-mini-kpi {
  position: relative;
  background: var(--bg2, #FAFAFC);
  border-radius: 9px;
  padding: 9px 10px 8px;
  overflow: hidden;
}
.kdm-mini-kpi::before {
  content: "";
  position: absolute;
  top: 0; left: 0; right: 0;
  height: 2px;
  background: var(--kc);
  transform-origin: left;
  transform: scaleX(0);
  animation: kdmKpiTop .65s var(--ease-standard) calc(.75s + var(--ki) * .09s) forwards;
}
.kdm-mk-l {
  font-size: 8.5px;
  font-weight: 500;
  color: var(--t3, var(--t-muted));
  text-transform: uppercase;
  letter-spacing: .05em;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.kdm-mk-v {
  font-size: 17px;
  font-weight: 400;
  letter-spacing: -.02em;
  color: var(--t1, #1E2A4A);
  line-height: 1.15;
  margin-top: 3px;
  font-feature-settings: "tnum";
}
.kdm-mk-d {
  font-size: 9.5px;
  color: var(--kc, var(--t-muted));
  font-weight: 500;
  margin-top: 1px;
}

/* Top-5 list */
.kdm-toplist { display: flex; flex-direction: column; gap: 6px; }
.kdm-top-row {
  display: grid;
  grid-template-columns: 150px 1fr 40px;
  gap: 10px;
  align-items: center;
  font-size: 11.5px;
  cursor: pointer;
  padding: 3px 0;
  border-radius: 5px;
  transition: background .12s;
}
.kdm-top-row:hover { background: rgba(127, 119, 221, .04); }
.kdm-top-name {
  color: var(--t1, #1E2A4A);
  font-weight: 500;
  display: flex;
  align-items: center;
  gap: 7px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.kdm-top-tick {
  width: 3px;
  height: 12px;
  opacity: .85;
  flex-shrink: 0;
}
.kdm-top-bar {
  height: 6px;
  background: #F1EFE8;
  border-radius: 3px;
  overflow: hidden;
}
.kdm-top-fill {
  display: block;
  height: 100%;
  transform: scaleX(0);
  transform-origin: left;
  animation: kdmBar 1s var(--ease-standard) forwards;
}
.kdm-top-val {
  text-align: right;
  color: var(--t1, #1E2A4A);
  font-weight: 500;
  font-feature-settings: "tnum";
}

/* Funnel per-sector rows */
.kdm-row-list { display: flex; flex-direction: column; gap: 6px; }
.kdm-sec-row {
  display: grid;
  grid-template-columns: 140px 1fr 80px;
  gap: 10px;
  align-items: center;
  font-size: 11.5px;
}
.kdm-sec-name {
  color: var(--t1, #1E2A4A);
  font-weight: 500;
  display: flex;
  align-items: center;
  gap: 7px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.kdm-sec-bar {
  height: 6px;
  background: #F1EFE8;
  border-radius: 3px;
  overflow: hidden;
}
.kdm-sec-fill {
  display: block;
  height: 100%;
  transform: scaleX(0);
  transform-origin: left;
  animation: kdmBar 1s var(--ease-standard) forwards;
}
.kdm-sec-val {
  text-align: right;
  font-weight: 500;
  font-feature-settings: "tnum";
  white-space: nowrap;
}

/* Recent items */
.kdm-recent { display: flex; flex-direction: column; gap: 2px; }
.kdm-recent-row {
  display: flex;
  gap: 10px;
  align-items: baseline;
  padding: 6px 6px;
  border-bottom: 1px dashed rgba(0, 0, 0, 0.06);
  font-size: 11.5px;
  cursor: pointer;
  border-radius: 5px;
  margin: 0 -6px;
  transition: background .12s;
}
.kdm-recent-row:hover { background: rgba(127,119,221,.04); }
.kdm-recent-row:last-child { border-bottom: none; }
.kdm-recent-ic { flex: 0 0 11px; }
.kdm-recent-meta { flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.kdm-recent-co { color: var(--t3, #5F5E5A); font-weight: 500; }
.kdm-recent-sep { color: #6B6A66; }
.kdm-recent-ttl { color: var(--t1, #1E2A4A); font-weight: 500; }
.kdm-recent-date { color: var(--t3, var(--t-muted)); font-feature-settings: "tnum"; flex-shrink: 0; }

.kdm-note {
  display: flex;
  gap: 7px;
  align-items: flex-start;
  padding: 7px 10px;
  margin-bottom: 8px;
  background: rgba(239, 159, 39, .07);
  border: 1px solid rgba(239, 159, 39, .18);
  border-radius: 7px;
  font-size: 10.5px;
  color: #854F0B;
  font-weight: 500;
  line-height: 1.4;
}
.kdm-note svg { flex-shrink: 0; margin-top: 1px; color: var(--sev-mid); }

/* Histogram */
.kdm-histo {
  display: grid;
  grid-template-columns: repeat(5, 1fr);
  gap: 9px;
  align-items: end;
  height: 116px;
  padding: 0 4px;
}
.kdm-hbar-col {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 5px;
  height: 100%;
}
.kdm-hbar-cnt {
  font-size: 11px;
  font-weight: 500;
  color: var(--t1, #1E2A4A);
  font-feature-settings: "tnum";
  margin-top: auto;
}
.kdm-hbar {
  width: 100%;
  border-radius: 5px 5px 0 0;
  transform-origin: bottom;
  transform: scaleY(0);
  animation: kdmBarH 1s var(--ease-standard) forwards;
  min-height: 2px;
}
.kdm-hbar-l {
  font-size: 9px;
  color: var(--t3, var(--t-muted));
  font-weight: 500;
  text-transform: uppercase;
  letter-spacing: .04em;
}

/* Leaders / Laggards */
.kdm-ll {
  display: grid !important;
  grid-template-columns: 1fr 1fr;
  gap: 18px;
  padding-top: 14px;
  border-top: 1px solid rgba(0, 0, 0, 0.05);
}
.kdm-ll-list { display: flex; flex-direction: column; gap: 0; }
.kdm-ll-row {
  display: flex;
  justify-content: space-between;
  padding: 4px 4px;
  border-bottom: 1px dashed rgba(0, 0, 0, 0.06);
  font-size: 11.5px;
  cursor: pointer;
  border-radius: 4px;
  transition: background .12s;
}
.kdm-ll-row:hover { background: rgba(127,119,221,.04); }
.kdm-ll-row:last-child { border-bottom: none; }
.kdm-ll-row .name { color: var(--t1, #1E2A4A); font-weight: 500; }
.kdm-ll-row .val { font-weight: 500; font-feature-settings: "tnum"; }

/* Empty / skeleton */
.kdm-empty {
  padding: 14px;
  text-align: center;
  color: var(--t3, var(--t-muted));
  font-size: 11.5px;
  font-style: italic;
}
.kdm-skel-bar {
  height: 11px;
  background: linear-gradient(90deg, #F1EFE8, #FAFAFC, #F1EFE8);
  background-size: 200% 100%;
  border-radius: 5px;
  animation: kdmSkel 1.4s ease-in-out infinite;
}
.kdm-skel-list { display: flex; flex-direction: column; gap: 4px; }
.kdm-skel-row {
  height: 22px;
  background: linear-gradient(90deg, #F1EFE8, #FAFAFC, #F1EFE8);
  background-size: 200% 100%;
  border-radius: 4px;
  animation: kdmSkel 1.4s ease-in-out infinite;
}

/* Footer */
.kdm-ftr {
  padding: 13px 22px 14px;
  display: flex;
  justify-content: flex-end;
  gap: 9px;
  border-top: 1px solid rgba(0, 0, 0, 0.05);
  background: var(--bg2, #FAFAFC);
}
.kdm-btn {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  font-weight: 500;
  padding: 9px 14px;
  border-radius: 8px;
  cursor: pointer;
  transition: all .14s;
  border: 1px solid transparent;
  font-family: inherit;
}
.kdm-btn-g {
  background: var(--bg1, #fff);
  color: var(--t3, #5F5E5A);
  border-color: rgba(0, 0, 0, 0.10);
}
.kdm-btn-g:hover { background: #F5F4F9; color: var(--t1, #1E2A4A); }
.kdm-btn-p { background: var(--sc); color: #fff; }
.kdm-btn-p:hover { filter: brightness(.93); }

/* Transitions */
.kdm-fade-enter-active, .kdm-fade-leave-active { transition: opacity .28s ease; }
.kdm-fade-enter-from, .kdm-fade-leave-to { opacity: 0; }
.kdm-fade-leave-active .kdm-card { animation: kdmOut .24s ease forwards; }

@keyframes kdmIn {
  0%   { opacity: 0; transform: translateY(22px) scale(.96); }
  100% { opacity: 1; transform: translateY(0) scale(1); }
}
@keyframes kdmOut {
  to { opacity: 0; transform: translateY(8px) scale(.98); }
}
@keyframes kdmStripe { from { transform: scaleX(0); } to { transform: scaleX(1); } }
@keyframes kdmShim {
  0%   { transform: translateX(-120%); }
  60%  { transform: translateX(220%); }
  100% { transform: translateX(220%); }
}
@keyframes kdmUp {
  from { opacity: 0; transform: translateY(8px); }
  to   { opacity: 1; transform: translateY(0); }
}
@keyframes kdmBar { to { transform: scaleX(1); } }
@keyframes kdmBarH { to { transform: scaleY(1); } }
@keyframes kdmKpiTop { from { transform: scaleX(0); } to { transform: scaleX(1); } }
@keyframes kdmSkel {
  0%   { background-position: 200% 0; }
  100% { background-position: -200% 0; }
}

/* Responsive */
@media (max-width: 600px) {
  .kdm-sec-grid { grid-template-columns: repeat(2, 1fr); }
  .kdm-top-row { grid-template-columns: 110px 1fr 36px; font-size: 11px; }
  .kdm-sec-row { grid-template-columns: 110px 1fr 70px; font-size: 11px; }
  .kdm-h-v { font-size: 36px; }
  .kdm-ll { grid-template-columns: 1fr; }
}
</style>
