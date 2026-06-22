<script setup lang="ts">
/**
 * PmoTab — PMO-вкладка воркспейса (P1: Расписание / Гантт).
 *
 * Видна только при праве pmo.view (гейтится в CompanyTabBar). Показывает
 * таймлайн портфеля за год: проекты + задачи, базовый план (тень), вехи (ромб),
 * критический путь (красный), слип-бейдж, блокировки, стрелки зависимостей.
 * Данные и расчёты (критпуть/слип) — с бэкенда `/pmo/companies/{code}/schedule`.
 */
import { ref, computed, watch, onMounted, onBeforeUnmount } from "vue";
import UzaStateBlock from "@/components/UZA/UzaStateBlock.vue";
import PmoRaid from "./PmoRaid.vue";
import PmoHealth from "./PmoHealth.vue";
import PmoStakeholders from "./PmoStakeholders.vue";
import PmoLog from "./PmoLog.vue";
import PmoCharter from "./PmoCharter.vue";
import PmoEvm from "./PmoEvm.vue";
import { api } from "@/api/client";
import { pmoApi, type ScheduleResponse, type ScheduleBar } from "@/api/pmo";

const props = defineProps<{
  companyCode: string;
  year: number;
  canEdit?: boolean;
  refreshTick?: number;   // меняется после сохранения в редакторе → перезагрузка
}>();

const emit = defineEmits<{
  (e: "open", p: { id: string; kind: "project" | "task" }): void;
}>();

function openBar(b: ScheduleBar) {
  emit("open", { id: b.id, kind: b.kind });
}

// Саб-навигация PMO: Расписание / RAID / Стейкхолдеры / Журнал / Здоровье
const view = ref<"schedule" | "charter" | "raid" | "stakeholders" | "log" | "health" | "evm">("schedule");

const loading = ref(true);
const error = ref<string | null>(null);
const data = ref<ScheduleResponse | null>(null);

async function load() {
  loading.value = true;
  error.value = null;
  try {
    data.value = await pmoApi.getSchedule(props.companyCode, props.year);
  } catch (e: any) {
    error.value = e?.response?.data?.detail || e?.message || "Не удалось загрузить расписание";
  } finally {
    loading.value = false;
  }
}
onMounted(load);
watch(() => [props.companyCode, props.year], load);
watch(() => props.refreshTick, load);

// Список проектов (для устава) — из баров расписания.
const projectList = computed(() =>
  (data.value?.bars || [])
    .filter((b) => b.kind === "project")
    .map((b) => ({ id: String(b.id), title: b.title })),
);

// ── Шкала года ────────────────────────────────────────────────────────
const ROW_H = 34;
const MONTHS = ["Янв", "Фев", "Мар", "Апр", "Май", "Июн", "Июл", "Авг", "Сен", "Окт", "Ноя", "Дек"];

const yearStart = computed(() => new Date(props.year, 0, 1).getTime());
const yearEnd = computed(() => new Date(props.year, 11, 31).getTime());
const yearSpan = computed(() => Math.max(yearEnd.value - yearStart.value, 1));

function parse(d: string | null): number | null {
  if (!d) return null;
  const t = new Date(d + "T00:00:00").getTime();
  return Number.isFinite(t) ? t : null;
}
function clampFrac(ms: number): number {
  return Math.max(0, Math.min(1, (ms - yearStart.value) / yearSpan.value));
}

interface Geo { left: number; width: number; }

interface GRow {
  bar: ScheduleBar;
  indent: boolean;
  top: number;
  geo: Geo | null;
  baseGeo: Geo | null;
  milestoneLeft: number | null;
  groupHeader?: string;
}

// Геометрия бара: start..due → проценты. Если start нет — короткий бар к due.
function barGeo(start: string | null, due: string | null): Geo | null {
  let s = parse(start);
  let d = parse(due);
  if (s == null && d == null) return null;
  if (s == null) s = d! - 7 * 86400000;  // нет старта → неделя до срока
  if (d == null) d = s + 7 * 86400000;
  const l = clampFrac(s) * 100;
  const r = clampFrac(d) * 100;
  return { left: l, width: Math.max(r - l, 1.2) };
}

// Плоский список строк: проекты + их задачи (с отступом) + сироты.
const rows = computed<GRow[]>(() => {
  if (!data.value) return [];
  const bars = data.value.bars;
  const projects = bars.filter((b) => b.kind === "project");
  const tasks = bars.filter((b) => b.kind === "task");
  const byProject = new Map<string, ScheduleBar[]>();
  const orphans: ScheduleBar[] = [];
  for (const t of tasks) {
    if (t.project_id && projects.some((p) => p.id === t.project_id)) {
      const arr = byProject.get(t.project_id) || [];
      arr.push(t);
      byProject.set(t.project_id, arr);
    } else {
      orphans.push(t);
    }
  }

  const out: GRow[] = [];
  let i = 0;
  const push = (bar: ScheduleBar, indent: boolean) => {
    out.push({
      bar,
      indent,
      top: i * ROW_H,
      geo: bar.is_milestone ? null : barGeo(bar.start, bar.due),
      baseGeo: barGeo(bar.baseline_start, bar.baseline_due),
      milestoneLeft: bar.is_milestone ? barGeo(bar.start, bar.due)?.left ?? null : null,
    });
    i++;
  };
  for (const p of projects) {
    push(p, false);
    for (const t of byProject.get(p.id) || []) push(t, true);
  }
  if (orphans.length) {
    out.push({ bar: orphans[0], indent: false, top: i * ROW_H, geo: null, baseGeo: null, milestoneLeft: null, groupHeader: "Без проекта" });
    i++;
    for (const t of orphans) push(t, true);
  }
  return out;
});

const totalHeight = computed(() => Math.max(rows.value.length * ROW_H, ROW_H));

// Стрелки зависимостей: pred (правый край) → succ (левый край).
interface Arrow { x1: number; y1: number; x2: number; y2: number; critical: boolean; }
const arrows = computed<Arrow[]>(() => {
  const idToRow = new Map<string, GRow>();
  for (const r of rows.value) idToRow.set(r.bar.id, r);
  const cp = new Set(data.value?.critical_path_ids || []);
  const res: Arrow[] = [];
  for (const r of rows.value) {
    if (r.bar.kind !== "task" || !r.geo) continue;
    for (const pid of r.bar.predecessor_ids || []) {
      const pr = idToRow.get(pid);
      if (!pr || !pr.geo) continue;
      res.push({
        x1: (pr.geo.left + pr.geo.width) * 10,        // viewBox 0..1000
        y1: pr.top + ROW_H / 2,
        x2: r.geo.left * 10,
        y2: r.top + ROW_H / 2,
        critical: cp.has(pid) && cp.has(r.bar.id),
      });
    }
  }
  return res;
});

function statusColor(b: ScheduleBar): string {
  if (b.on_critical_path) return "#E24B4A";
  if (b.status === "done") return "#1D9E75";
  if (b.blocked) return "#888780";
  if (b.kind === "project") return "#534AB7";
  return "#7F77DD";
}

// ══ Drag-слой: перепланирование баров + протягивание зависимостей ══════
const trackRef = ref<HTMLElement | null>(null);
const DAY = 86400000;

interface DragState {
  mode: "move" | "resize-start" | "resize-end";
  bar: ScheduleBar;
  startX: number;
  origStart: number; origDue: number;
  newStart: number; newDue: number;
  moved: boolean;
}
const drag = ref<DragState | null>(null);
let suppressClick = false;

interface LinkState { source: ScheduleBar; sx: number; sy: number; cx: number; cy: number; targetId: string | null; }
const link = ref<LinkState | null>(null);

function trackRect(): DOMRect {
  return trackRef.value?.getBoundingClientRect() ?? ({ left: 0, top: 0, width: 1, height: 1 } as DOMRect);
}
function xToMs(clientX: number): number {
  const r = trackRect();
  const frac = Math.max(0, Math.min(1, (clientX - r.left) / (r.width || 1)));
  return yearStart.value + frac * yearSpan.value;
}
function snapDay(ms: number): number { const d = new Date(ms); d.setHours(0, 0, 0, 0); return d.getTime(); }
function msToStr(ms: number): string {
  const d = new Date(ms);
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}
function barMs(bar: ScheduleBar): { s: number; d: number } {
  let s = parse(bar.start); let d = parse(bar.due);
  if (s == null && d == null) { const t = snapDay(yearStart.value); return { s: t, d: t + 7 * DAY }; }
  if (s == null) s = d! - 7 * DAY;
  if (d == null) d = s + 7 * DAY;
  return { s, d };
}

// Live-геометрия с учётом текущего перетаскивания (превью)
function liveGeo(r: GRow): Geo | null {
  const st = drag.value;
  if (st && st.bar.id === r.bar.id && !r.bar.is_milestone) {
    return barGeo(msToStr(st.newStart), msToStr(st.newDue));
  }
  return r.geo;
}
function barStyle(r: GRow) {
  const g = liveGeo(r) || r.geo!;
  return {
    top: (r.top + (r.bar.kind === "project" ? 7 : 9)) + "px",
    left: g.left + "%",
    width: g.width + "%",
    background: statusColor(r.bar),
    animationDelay: Math.min((r.top / ROW_H) * 0.025, 0.55) + "s",
  };
}
function milestoneLeftLive(r: GRow): number {
  const st = drag.value;
  if (st && st.bar.id === r.bar.id) return barGeo(msToStr(st.newStart), msToStr(st.newDue))?.left ?? (r.milestoneLeft ?? 0);
  return r.milestoneLeft ?? 0;
}

function onBarDown(e: MouseEvent, bar: ScheduleBar, mode: DragState["mode"]) {
  if (!props.canEdit) return;                       // без права — только клик-открытие
  if (bar.is_milestone && mode !== "move") return;  // веху не ресайзим
  e.preventDefault();
  const { s, d } = barMs(bar);
  drag.value = { mode, bar, startX: e.clientX, origStart: s, origDue: d, newStart: s, newDue: d, moved: mode !== "move" };
  window.addEventListener("mousemove", onDragMove);
  window.addEventListener("mouseup", onDragUp);
}
function onDragMove(e: MouseEvent) {
  const st = drag.value; if (!st) return;
  if (st.mode === "move") {
    if (!st.moved && Math.abs(e.clientX - st.startX) < 4) return;
    st.moved = true;
    const deltaDays = Math.round((xToMs(e.clientX) - xToMs(st.startX)) / DAY);
    st.newStart = snapDay(st.origStart + deltaDays * DAY);
    st.newDue = snapDay(st.origDue + deltaDays * DAY);
  } else if (st.mode === "resize-start") {
    let ns = snapDay(xToMs(e.clientX));
    if (ns >= st.newDue) ns = st.newDue - DAY;
    st.newStart = ns;
  } else {
    let nd = snapDay(xToMs(e.clientX));
    if (nd <= st.newStart) nd = st.newStart + DAY;
    st.newDue = nd;
  }
}
async function onDragUp() {
  window.removeEventListener("mousemove", onDragMove);
  window.removeEventListener("mouseup", onDragUp);
  const st = drag.value; drag.value = null;
  if (!st) return;
  suppressClick = true; setTimeout(() => { suppressClick = false; }, 60);  // гасим native click
  if (st.mode === "move" && !st.moved) { openBar(st.bar); return; }         // это был клик
  if (st.newStart === st.origStart && st.newDue === st.origDue) return;
  await saveDates(st.bar, msToStr(st.newStart), msToStr(st.newDue));
}
async function saveDates(bar: ScheduleBar, startStr: string, dueStr: string) {
  try {
    const url = (bar.kind === "project" ? "/projects/" : "/tasks/") + bar.id;
    await api.patch(url, { start_date: startStr, due_date: dueStr });
    await load();
  } catch (e: any) {
    error.value = e?.response?.data?.detail || "Не удалось сохранить даты";
  }
}
function onBarClick(bar: ScheduleBar) {
  if (suppressClick) { suppressClick = false; return; }
  openBar(bar);
}

// Протягивание зависимости (узелок на правом крае задачи → другая задача)
function onLinkDown(e: MouseEvent, bar: ScheduleBar) {
  if (!props.canEdit) return;
  e.preventDefault(); e.stopPropagation();
  const r = trackRect();
  const row = rows.value.find((x) => x.bar.id === bar.id);
  const geo = row?.geo;
  const sx = geo ? (geo.left + geo.width) / 100 * r.width : 0;
  const sy = (row?.top ?? 0) + ROW_H / 2;
  link.value = { source: bar, sx, sy, cx: sx, cy: sy, targetId: null };
  window.addEventListener("mousemove", onLinkMove);
  window.addEventListener("mouseup", onLinkUp);
}
function onLinkMove(e: MouseEvent) {
  const st = link.value; if (!st) return;
  const r = trackRect();
  st.cx = e.clientX - r.left;
  st.cy = e.clientY - r.top;
  const idx = Math.floor(st.cy / ROW_H);
  const target = rows.value[idx];
  st.targetId = (target && !target.groupHeader && target.bar.kind === "task" && target.bar.id !== st.source.id)
    ? target.bar.id : null;
}
async function onLinkUp() {
  window.removeEventListener("mousemove", onLinkMove);
  window.removeEventListener("mouseup", onLinkUp);
  const st = link.value; link.value = null;
  if (!st || !st.targetId) return;
  try {
    await pmoApi.createDependency({ predecessor_id: st.source.id, successor_id: st.targetId });
    await load();
  } catch (e: any) {
    error.value = e?.response?.data?.detail || "Не удалось создать зависимость";
  }
}
const linkPath = computed(() => {
  const st = link.value; if (!st) return "";
  const w = trackRect().width || 1;
  const x1 = st.sx / w * 1000, x2 = st.cx / w * 1000;
  return `M ${x1} ${st.sy} C ${x1 + 24} ${st.sy}, ${x2 - 24} ${st.cy}, ${x2} ${st.cy}`;
});

onBeforeUnmount(() => {
  window.removeEventListener("mousemove", onDragMove);
  window.removeEventListener("mouseup", onDragUp);
  window.removeEventListener("mousemove", onLinkMove);
  window.removeEventListener("mouseup", onLinkUp);
});

const fmtD = (s: string | null) =>
  s ? new Date(s + "T00:00:00").toLocaleDateString("ru-RU", { day: "numeric", month: "short" }) : "—";
</script>

<template>
  <div class="pmo-root">
    <!-- Саб-навигация PMO -->
    <div class="pmo-subnav">
      <button class="pmo-sn" :class="{ on: view === 'schedule' }" @click="view = 'schedule'">Расписание</button>
      <button class="pmo-sn" :class="{ on: view === 'charter' }" @click="view = 'charter'">Устав</button>
      <button class="pmo-sn" :class="{ on: view === 'raid' }" @click="view = 'raid'">Риски (RAID)</button>
      <button class="pmo-sn" :class="{ on: view === 'stakeholders' }" @click="view = 'stakeholders'">Стейкхолдеры</button>
      <button class="pmo-sn" :class="{ on: view === 'log' }" @click="view = 'log'">Журнал</button>
      <button class="pmo-sn" :class="{ on: view === 'health' }" @click="view = 'health'">Здоровье</button>
      <button class="pmo-sn" :class="{ on: view === 'evm' }" @click="view = 'evm'">Освоенный объём</button>
    </div>

    <div v-show="view === 'schedule'" class="pmo">
    <UzaStateBlock v-if="loading" state="loading" :text="`Построение расписания ${year}…`" />
    <UzaStateBlock v-else-if="error" state="error" variant="block" title="Не удалось загрузить расписание" :text="error" retry @retry="load" />

    <template v-else-if="data">
      <!-- KPI-лента портфеля -->
      <div class="pmo-kpis kpi-rail">
        <div class="pmo-kpi" :style="{ '--accent': data.portfolio_slip_days > 0 ? '#E24B4A' : '#1D9E75' }">
          <div class="pmo-kpi-l">Слип портфеля</div>
          <div class="pmo-kpi-v" :style="{ color: data.portfolio_slip_days > 0 ? '#E24B4A' : 'var(--t1)' }">
            {{ data.portfolio_slip_days > 0 ? "+" : "" }}{{ data.portfolio_slip_days }} дн
          </div>
        </div>
        <div class="pmo-kpi">
          <div class="pmo-kpi-l">Прогноз финиша</div>
          <div class="pmo-kpi-v">{{ fmtD(data.forecast_finish) }}</div>
        </div>
        <div class="pmo-kpi">
          <div class="pmo-kpi-l">База (план)</div>
          <div class="pmo-kpi-v">{{ fmtD(data.baseline_finish) }}</div>
        </div>
        <div class="pmo-kpi" :style="{ '--accent': data.overdue_count ? '#E24B4A' : '#94a3b8' }">
          <div class="pmo-kpi-l">Просрочено</div>
          <div class="pmo-kpi-v" :style="{ color: data.overdue_count ? '#E24B4A' : 'var(--t1)' }">{{ data.overdue_count }}</div>
        </div>
        <div class="pmo-kpi" :style="{ '--accent': data.blocked_count ? '#D97706' : '#94a3b8' }">
          <div class="pmo-kpi-l">Заблокировано</div>
          <div class="pmo-kpi-v">{{ data.blocked_count }}</div>
        </div>
        <div class="pmo-kpi" :style="{ '--accent': '#E24B4A' }">
          <div class="pmo-kpi-l">Критический путь</div>
          <div class="pmo-kpi-v">{{ data.critical_path_ids.length }} зад.</div>
        </div>
      </div>

      <!-- Легенда -->
      <div class="pmo-legend">
        <span><i class="lg-bar" style="background:#7F77DD"></i> задача</span>
        <span><i class="lg-bar" style="background:#E24B4A"></i> критический путь</span>
        <span><i class="lg-base"></i> базовый план</span>
        <span><i class="lg-dia"></i> веха</span>
        <span><i class="lg-slip">+Nд</i> слип</span>
      </div>

      <UzaStateBlock
        v-if="!rows.length"
        state="empty"
        variant="block"
        title="Нет данных для расписания"
        text="Добавьте проекты/задачи с датами начала и срока — они появятся на таймлайне."
      />

      <!-- Гантт -->
      <div v-else class="pmo-gantt">
        <!-- Заголовок месяцев -->
        <div class="pg-head">
          <div class="pg-head-label">Проект / задача</div>
          <div class="pg-head-track">
            <div v-for="(m, mi) in MONTHS" :key="m" class="pg-month" :style="{ left: (mi / 12 * 100) + '%' }">{{ m }}</div>
          </div>
        </div>

        <div class="pg-body" :style="{ height: totalHeight + 'px' }">
          <!-- Левая колонка строк -->
          <div class="pg-labels">
            <div
              v-for="r in rows"
              :key="'l-' + r.bar.id"
              class="pg-label"
              :class="{ 'is-proj': r.bar.kind === 'project', 'is-indent': r.indent, 'is-click': !r.groupHeader }"
              :style="{ top: r.top + 'px', height: ROW_H + 'px' }"
              :title="r.groupHeader ? '' : 'Открыть: ' + r.bar.title"
              @click="!r.groupHeader && openBar(r.bar)"
            >
              <span v-if="r.groupHeader" class="pg-grp">{{ r.groupHeader }}</span>
              <template v-else>
                <span v-if="r.bar.on_critical_path" class="pg-cp-dot" title="Критический путь"></span>
                <span v-if="r.bar.blocked" class="pg-lock" title="Заблокировано предшественником" aria-hidden="true">
                  <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4"><rect x="5" y="11" width="14" height="9" rx="2"/><path d="M8 11V8a4 4 0 0 1 8 0v3"/></svg>
                </span>
                <span class="pg-label-txt">{{ r.bar.title }}</span>
              </template>
            </div>
          </div>

          <!-- Трек с барами -->
          <div class="pg-track" ref="trackRef" :class="{ 'is-dragging': !!drag || !!link }">
            <!-- Вертикальные гридлайны месяцев -->
            <div v-for="mi in 12" :key="'g' + mi" class="pg-grid" :style="{ left: ((mi - 1) / 12 * 100) + '%' }"></div>

            <!-- Стрелки зависимостей -->
            <svg class="pg-arrows" :viewBox="'0 0 1000 ' + totalHeight" preserveAspectRatio="none" aria-hidden="true">
              <defs>
                <marker id="pmoArrow" markerWidth="6" markerHeight="6" refX="4" refY="3" orient="auto">
                  <path d="M0,0 L6,3 L0,6 Z" fill="#94a3b8" />
                </marker>
                <marker id="pmoArrowCp" markerWidth="6" markerHeight="6" refX="4" refY="3" orient="auto">
                  <path d="M0,0 L6,3 L0,6 Z" fill="#E24B4A" />
                </marker>
              </defs>
              <path
                v-for="(a, ai) in arrows"
                :key="'a' + ai"
                :d="`M ${a.x1} ${a.y1} C ${a.x1 + 24} ${a.y1}, ${a.x2 - 24} ${a.y2}, ${a.x2} ${a.y2}`"
                fill="none"
                :stroke="a.critical ? '#E24B4A' : '#94a3b8'"
                stroke-width="1.3"
                :marker-end="a.critical ? 'url(#pmoArrowCp)' : 'url(#pmoArrow)'"
                vector-effect="non-scaling-stroke"
                :opacity="a.critical ? 0.85 : 0.5"
              />
              <!-- Временная линия при протягивании зависимости -->
              <path
                v-if="link"
                :d="linkPath"
                fill="none"
                stroke="#7c6ff7"
                stroke-width="1.7"
                stroke-dasharray="5 4"
                vector-effect="non-scaling-stroke"
                opacity="0.9"
              />
            </svg>

            <!-- Бары -->
            <template v-for="r in rows" :key="'b-' + r.bar.id">
              <!-- Базовый план (тень) -->
              <div
                v-if="r.baseGeo"
                class="pg-base"
                :style="{ top: (r.top + ROW_H / 2 - 2) + 'px', left: r.baseGeo.left + '%', width: r.baseGeo.width + '%' }"
              ></div>

              <!-- Веха -->
              <div
                v-if="r.milestoneLeft != null"
                class="pg-milestone"
                :style="{ top: (r.top + ROW_H / 2) + 'px', left: milestoneLeftLive(r) + '%' }"
                :title="(canEdit ? 'Тяни — сдвинуть · клик — открыть\n' : '') + 'Веха: ' + r.bar.title + ' · ' + fmtD(r.bar.due)"
                @mousedown="onBarDown($event, r.bar, 'move')"
                @click="onBarClick(r.bar)"
              ></div>

              <!-- Бар -->
              <div
                v-else-if="r.geo"
                class="pg-bar"
                :class="{ 'is-proj': r.bar.kind === 'project', 'is-done': r.bar.status === 'done', 'is-drag': drag && drag.bar.id === r.bar.id, 'is-link-target': link && link.targetId === r.bar.id }"
                :style="barStyle(r)"
                :title="(canEdit ? 'Тяни края — даты · тяни узелок — зависимость · клик — открыть\n' : 'Открыть: ') + r.bar.title + ' · ' + fmtD(r.bar.start) + ' → ' + fmtD(r.bar.due) + (r.bar.slip_days > 0 ? ' · слип +' + r.bar.slip_days + 'д' : '')"
                @mousedown="onBarDown($event, r.bar, 'move')"
                @click="onBarClick(r.bar)"
              >
                <span class="pg-bar-fill" :style="{ width: (r.bar.progress_percent || 0) + '%' }"></span>
                <span v-if="r.bar.slip_days > 0" class="pg-slip">+{{ r.bar.slip_days }}д</span>
                <template v-if="canEdit">
                  <span class="pg-h pg-h-l" title="Сдвинуть старт" @mousedown.stop="onBarDown($event, r.bar, 'resize-start')"></span>
                  <span class="pg-h pg-h-r" title="Сдвинуть дедлайн" @mousedown.stop="onBarDown($event, r.bar, 'resize-end')"></span>
                  <span v-if="r.bar.kind === 'task'" class="pg-link" title="Протянуть зависимость к другой задаче" @mousedown.stop="onLinkDown($event, r.bar)"></span>
                </template>
              </div>
            </template>
          </div>
        </div>
      </div>
    </template>
    </div>

    <PmoCharter v-if="view === 'charter'" :company-code="companyCode" :can-edit="canEdit" :projects="projectList" />
    <PmoRaid v-if="view === 'raid'" :company-code="companyCode" :can-edit="canEdit" />
    <PmoStakeholders v-if="view === 'stakeholders'" :company-code="companyCode" :can-edit="canEdit" />
    <PmoLog v-if="view === 'log'" :company-code="companyCode" :can-edit="canEdit" :projects="projectList" />
    <PmoHealth
      v-if="view === 'health'"
      :company-code="companyCode"
      :can-edit="canEdit"
      :refresh-tick="refreshTick"
      @open="(p) => emit('open', p)"
    />
    <PmoEvm v-if="view === 'evm'" :company-code="companyCode" :year="year" />
  </div>
</template>

<style scoped>
.pmo-root { padding: 2px; }
.pmo-subnav { display: flex; gap: 4px; margin-bottom: 12px; border-bottom: 1px solid var(--border, rgba(99,102,180,.12)); overflow-x: auto; scrollbar-width: none; }
.pmo-subnav::-webkit-scrollbar { display: none; }
.pmo-sn { padding: 8px 14px; border: none; background: none; border-bottom: 2px solid transparent; margin-bottom: -1px; color: var(--t3, #94a3b8); font-size: var(--fs-md, 12.5px); font-weight: 500; cursor: pointer; font-family: inherit; white-space: nowrap; flex-shrink: 0; transition: color .12s, border-color .12s; }
.pmo-sn:hover { color: var(--t1, #1e2a4a); }
.pmo-sn.on { color: var(--p-deep, #534ab7); border-bottom-color: var(--p, #7c6ff7); }
.pmo { padding: 4px 2px 24px; }

/* KPI-лента */
.pmo-kpis { display: grid; grid-template-columns: repeat(6, 1fr); margin-bottom: 12px; animation: pgFadeUp .4s var(--ease-out) both; }
@keyframes pgFadeUp { from { opacity: 0; transform: translateY(8px); } to { opacity: 1; transform: translateY(0); } }
.pmo-kpi { padding: 12px 14px; }
.pmo-kpi-l { font-size: var(--fs-2xs, 9px); text-transform: uppercase; letter-spacing: .06em; color: var(--t3, #94a3b8); font-weight: 600; }
.pmo-kpi-v { font-size: var(--fs-xl, 18px); font-weight: 400; color: var(--t1, #1e2a4a); margin-top: 4px; font-variant-numeric: tabular-nums; }

.pmo-legend { display: flex; flex-wrap: wrap; gap: 16px; font-size: var(--fs-xs, 10px); color: var(--t3, #94a3b8); margin-bottom: 10px; padding-left: 2px; }
.pmo-legend span { display: inline-flex; align-items: center; gap: 5px; }
.lg-bar { width: 14px; height: 7px; border-radius: 3px; display: inline-block; }
.lg-base { width: 14px; height: 3px; border-radius: 2px; background: repeating-linear-gradient(90deg, #c7cbe0 0 4px, transparent 4px 7px); display: inline-block; }
.lg-dia { width: 8px; height: 8px; background: #534AB7; transform: rotate(45deg); display: inline-block; }
.lg-slip { font-size: 8.5px; font-weight: 700; color: #E24B4A; }

/* Гантт */
.pmo-gantt { border: 1px solid var(--border, rgba(99,102,180,.12)); border-radius: var(--r, 10px); overflow: hidden; background: var(--bg1, #fff); animation: pgFadeUp .45s var(--ease-out) both; animation-delay: .06s; }
.pg-head { display: flex; border-bottom: 1px solid var(--border, rgba(99,102,180,.12)); background: var(--bg2, #fafafc); }
.pg-head-label { width: 230px; flex-shrink: 0; padding: 8px 12px; font-size: var(--fs-2xs, 9px); text-transform: uppercase; letter-spacing: .06em; color: var(--t3, #94a3b8); font-weight: 600; }
.pg-head-track { position: relative; flex: 1; height: 30px; }
.pg-month { position: absolute; top: 8px; font-size: var(--fs-2xs, 9px); color: var(--t3, #94a3b8); font-weight: 600; transform: translateX(4px); }

.pg-body { display: flex; position: relative; }
.pg-labels { width: 230px; flex-shrink: 0; position: relative; border-right: 1px solid var(--border, rgba(99,102,180,.12)); }
.pg-label { position: absolute; left: 0; right: 0; display: flex; align-items: center; gap: 5px; padding: 0 10px; font-size: var(--fs-sm, 11px); color: var(--t1, #1e2a4a); overflow: hidden; }
.pg-label.is-proj { font-weight: 600; }
.pg-label.is-indent { padding-left: 22px; color: var(--t2, #475569); }
.pg-label.is-click { cursor: pointer; transition: background .12s; }
.pg-label.is-click:hover { background: rgba(124,111,247,.07); }
.pg-label-txt { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.pg-grp { font-size: var(--fs-2xs, 9px); text-transform: uppercase; letter-spacing: .05em; color: var(--t3, #94a3b8); font-weight: 700; }
.pg-cp-dot { width: 6px; height: 6px; border-radius: 50%; background: #E24B4A; flex-shrink: 0; }
.pg-lock { color: #888780; display: inline-flex; flex-shrink: 0; }

.pg-track { position: relative; flex: 1; }
.pg-grid { position: absolute; top: 0; bottom: 0; width: 1px; background: rgba(99,102,180,.07); }
.pg-arrows { position: absolute; inset: 0; width: 100%; height: 100%; pointer-events: none; z-index: 1; }

.pg-base { position: absolute; height: 4px; border-radius: 2px; background: repeating-linear-gradient(90deg, #c7cbe0 0 5px, transparent 5px 9px); }
.pg-bar { position: absolute; height: 16px; border-radius: 5px; box-shadow: 0 1px 3px rgba(15,23,60,.12); overflow: hidden; z-index: 2; min-width: 5px; cursor: pointer; transition: filter .12s, transform .12s, box-shadow .12s; animation: pgBarDraw .7s var(--ease-out) both; }
@keyframes pgBarDraw { from { clip-path: inset(0 100% 0 0); } to { clip-path: inset(0 0 0 0); } }
.pg-bar:hover { filter: brightness(1.08); transform: translateY(-1px); box-shadow: 0 4px 10px rgba(15,23,60,.22); z-index: 4; }
.pg-bar.is-proj { height: 18px; border-radius: 6px; }
.pg-bar.is-done { opacity: .72; }
.pg-bar-fill { position: absolute; left: 0; top: 0; bottom: 0; background: rgba(255,255,255,.32); pointer-events: none; }
.pg-slip { position: absolute; right: 4px; top: 50%; transform: translateY(-50%); font-size: 8px; font-weight: 700; color: #fff; background: rgba(0,0,0,.22); padding: 0 3px; border-radius: 3px; pointer-events: none; }
.pg-milestone { position: absolute; width: 11px; height: 11px; background: #534AB7; transform: translate(-50%, -50%) rotate(45deg); border: 1.5px solid #fff; box-shadow: 0 1px 3px rgba(15,23,60,.2); z-index: 3; cursor: pointer; transition: transform .12s; animation: pgFade .6s var(--ease-out) both; animation-delay: .3s; }
@keyframes pgFade { from { opacity: 0; } to { opacity: 1; } }
.pg-milestone:hover { transform: translate(-50%, -50%) rotate(45deg) scale(1.25); }

/* Drag-слой: ресайз-края, узелок зависимости, состояния */
.pg-track.is-dragging { user-select: none; }
.pg-bar.is-drag { z-index: 7; box-shadow: 0 5px 16px rgba(15,23,60,.32); opacity: .92; }
.pg-bar.is-link-target { outline: 2px solid #7c6ff7; outline-offset: 1px; }
.pg-h { position: absolute; top: 0; bottom: 0; width: 8px; z-index: 5; cursor: ew-resize; opacity: 0; }
.pg-h-l { left: -1px; }
.pg-h-r { right: -1px; }
.pg-bar:hover .pg-h { opacity: 1; background: rgba(255,255,255,.3); }
.pg-link { position: absolute; right: -6px; top: 50%; transform: translateY(-50%); width: 11px; height: 11px; border-radius: 50%; background: #fff; border: 2px solid #7c6ff7; z-index: 6; cursor: crosshair; opacity: 0; transition: opacity .12s, transform .12s; }
.pg-bar:hover .pg-link { opacity: 1; }
.pg-link:hover { transform: translateY(-50%) scale(1.3); }

/* ≤14″ ноутбуки (контент ~990–1100px при сайдбаре) */
@media (max-width: 1366px) {
  .pmo-kpis { grid-template-columns: repeat(3, 1fr); }
  .pg-head-label, .pg-labels { width: 180px; }
  .pmo-legend { gap: 11px; }
}
@media (max-width: 768px) {
  .pmo-kpis { grid-template-columns: repeat(2, 1fr); }
  .pg-head-label, .pg-labels { width: 140px; }
}
</style>
