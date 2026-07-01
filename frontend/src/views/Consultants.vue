<script setup lang="ts">
/**
 * Consultants — 1:1 port of legacy `showConsultantsView` (index.html:44309).
 *
 * Layout:
 *   • Dark navy topbar + year badge + edit-menu (▤)
 *   • 4 KPI cells (.kpi2 .fin-shimmer with count-up):
 *       Задач охвачено · Компаний · Консультантов · Среднее завершение
 *   • 2-col grid: Consultants list (Big4 + Others) | Heatmap (board × consultant)
 *   • 2-col grid: Direction stats | Project list (with CSV export)
 *
 * Backend `/consultants/overview` already returns full shape (kpis, consultants,
 * heatmap, dirs, projects). No backend changes.
 */
import { ref, computed, onMounted, nextTick, watch } from "vue";
import SidebarBurger from "@/components/SidebarBurger.vue";
import { api } from "@/api/client";
import { useCountUpScan } from "@/composables/useCountUp";
import { usePermissions } from "@/composables/usePermissions";
import ConsultantsDrillModal from "@/components/Consultants/ConsultantsDrillModal.vue";
import UzaStateBlock from "@/components/UZA/UzaStateBlock.vue";
import UzaYearStepper from "@/components/UZA/UzaYearStepper.vue";
import TaskProjectEditor from "@/components/TaskProjectEditor.vue";
import { tasksApi, type TaskDetail } from "@/api/tasks";
import { useToast } from "@/composables/useToast";
const _perm = usePermissions("consultants");
const toast = useToast();

// ─── Types ───────────────────────────────────────────────────────
interface KPIs {
  tasks_covered: number;
  companies_covered: number;
  consultants_active: number;
  avg_completion_pct: number;
}

interface ConsultantRow {
  id: string; code: string; name: string; abbr: string | null;
  color: string | null; is_big4: boolean;
  tasks_total: number; tasks_done: number; tasks_overdue: number;
  completion_pct: number;
}

interface HeatmapBoard { id: string; name: string; sector_color: string; }
interface HeatmapRow { board: HeatmapBoard; counts: number[]; }
interface Heatmap {
  consultants: { id: string; code: string; name: string; abbr: string | null;
                 color: string | null; is_big4: boolean }[];
  rows: HeatmapRow[];
  max: number;
}

interface DirRow {
  id: string; label: string; color: string;
  tasks_total: number; tasks_done: number; tasks_overdue: number;
  completion_pct: number;
  consultant_codes: string[];
}

interface ProjectRow {
  id: string; num: string | null; title: string;
  board_id: string | null;
  board_name: string | null;
  company_id: string | null;
  company_name: string | null;
  status: string;
  due_date: string | null;
  direction_id: string | null;
  direction_label: string | null;
  consultants: { id?: string; code: string; abbr: string | null; color: string | null }[];
}

interface OverviewResponse {
  kpis: KPIs;
  consultants: ConsultantRow[];
  heatmap: Heatmap;
  dirs: DirRow[];
  projects: ProjectRow[];
  available_years: number[];
  selected_year: number | null;
}

// ─── State ───────────────────────────────────────────────────────
const data = ref<OverviewResponse | null>(null);
const loading = ref(true);
const errorMsg = ref<string | null>(null);
const year = ref<number | null>(null);
const filterConsultantCode = ref<string | null>(null);
const heatmapZoomed = ref(false);

// ─── Derived ─────────────────────────────────────────────────────
const big4 = computed(() => (data.value?.consultants || []).filter(c => c.is_big4));
const others = computed(() => (data.value?.consultants || []).filter(c => !c.is_big4));

const filteredProjects = computed(() => {
  if (!data.value) return [];
  if (!filterConsultantCode.value) return data.value.projects;
  return data.value.projects.filter(p =>
    p.consultants.some(c => c.code === filterConsultantCode.value),
  );
});

const consultantByCode = computed<Record<string, ConsultantRow>>(() => {
  const m: Record<string, ConsultantRow> = {};
  for (const c of data.value?.consultants || []) m[c.code] = c;
  return m;
});

// ─── Helpers ─────────────────────────────────────────────────────
function pctColor(p: number): string {
  if (p >= 60) return "#1D9E75";
  if (p >= 30) return "#D97706";
  return "#993D3D";
}

function statusDot(status: string): string {
  // Aligned with the design guide palette — was using off-palette tailwind colors.
  const m: Record<string, string> = {
    done: "#1D9E75", active: "#378ADD", overdue: "#E24B4A",
    init: "#888780", new: "#E5E7EB", review: "#EF9F27",
  };
  return m[status] || "#E5E7EB";
}

// Heat-map cell colour (1:1 legacy line 44420)
function cellBg(count: number, max: number): string {
  if (count === 0) return "#F4F3F9";
  const pct = count / Math.max(max, 1);
  if (pct >= 0.75) return "#7F77DD";
  if (pct >= 0.5)  return "#8B7FEE";
  if (pct >= 0.3)  return "#A89CE8";
  if (pct >= 0.15) return "#CCC8F4";
  return "#E8E6FB";
}
function cellFg(count: number, max: number): string {
  if (count === 0) return "transparent";
  const pct = count / Math.max(max, 1);
  return pct >= 0.3 ? "#fff" : "#7F77DD";
}

function fmtDate(s: string | null): string {
  if (!s) return "—";
  const d = new Date(s);
  if (isNaN(d.getTime())) return "—";
  return d.toLocaleDateString("ru-RU", { day: "2-digit", month: "short", year: "numeric" });
}

// ─── Count-up scan ───────────────────────────────────────────────
const scanRoot = ref<HTMLElement | null>(null);
const { rescan } = useCountUpScan(scanRoot, { baseDelay: 40, stagger: 80 });

// ─── Load ────────────────────────────────────────────────────────
async function load() {
  loading.value = true;
  errorMsg.value = null;
  try {
    const params: Record<string, unknown> = {};
    if (year.value) params.year = year.value;
    const res = await api.get<OverviewResponse>("/consultants/overview", { params });
    data.value = res.data;
    await nextTick();
    rescan();
  } catch (e: unknown) {
    const err = e as { response?: { data?: { detail?: string } }; message?: string };
    errorMsg.value = err?.response?.data?.detail || err?.message || "Ошибка загрузки";
    data.value = null;
  } finally {
    loading.value = false;
  }
}

function selectConsultant(code: string | null) {
  filterConsultantCode.value = filterConsultantCode.value === code ? null : code;
}

// ─── Drill-modal state (consultant / cell / direction) ───────────
type DrillKind = "consultant" | "cell" | "direction";
const drillOpen = ref(false);
const drillKind = ref<DrillKind>("consultant");
const drillConsultant = ref<ConsultantRow | null>(null);
const drillCellBoard = ref<HeatmapBoard | null>(null);
const drillCellConsultant = ref<ConsultantRow | null>(null);
const drillCellCount = ref(0);
const drillDirection = ref<DirRow | null>(null);

function openDrillConsultant(c: ConsultantRow) {
  drillKind.value = "consultant";
  drillConsultant.value = c;
  drillOpen.value = true;
}
function openDrillCell(boardId: string, consultantId: string, count: number) {
  if (count <= 0 || !data.value) return;
  const board = data.value.heatmap.rows.find(r => r.board.id === boardId)?.board || null;
  // Heatmap consultants are slim, need to find full ConsultantRow by id
  const cFull = data.value.consultants.find(c => c.id === consultantId) || null;
  if (!board || !cFull) return;
  drillCellBoard.value = board;
  drillCellConsultant.value = cFull;
  drillCellCount.value = count;
  drillKind.value = "cell";
  drillOpen.value = true;
}
function openDrillDirection(d: DirRow) {
  drillKind.value = "direction";
  drillDirection.value = d;
  drillOpen.value = true;
}
function closeDrill() {
  drillOpen.value = false;
  drillConsultant.value = null;
  drillCellBoard.value = null;
  drillCellConsultant.value = null;
  drillDirection.value = null;
}

// ─── Task editor (opened from drill-modal task rows OR from main proj-row) ─
const editorOpen = ref(false);
const editorEntity = ref<TaskDetail | null>(null);
const editorLoading = ref(false);

async function openTaskEditor(taskId: string) {
  editorLoading.value = true;
  try {
    editorEntity.value = await tasksApi.getOne(taskId);
    editorOpen.value = true;
  } catch (e) {
    console.warn("[consultants] openTaskEditor failed:", e);
    const err = e as { response?: { data?: { detail?: string } }; message?: string };
    toast.error(err?.response?.data?.detail || "Не удалось открыть задачу");
  } finally {
    editorLoading.value = false;
  }
}
function closeEditor() {
  editorOpen.value = false;
  editorEntity.value = null;
}
function onEditorSaved() {
  // Reload overview to reflect any edits
  closeEditor();
  load();
}

function setYear(y: number | null) {
  year.value = y;
}

// ─── CSV export (legacy cvExport) ──────────────────────────────
function cvExport() {
  if (!data.value) return;
  const rows = filteredProjects.value;
  if (!rows.length) {
    toast.info("Нет проектов для экспорта.");
    return;
  }
  const escape = (v: unknown) => {
    if (v == null) return "";
    let s = String(v);
    // CSV formula injection: значения с ведущими = + - @ TAB CR обезвреживаем
    // (иначе Excel/LibreOffice выполнит формулу из title/имени компании).
    if (/^[=+\-@\t\r]/.test(s)) s = "'" + s;
    s = s.replace(/"/g, '""');
    return /[",\n;]/.test(s) ? `"${s}"` : s;
  };
  const headers = ["#", "Компания", "Направление", "Задача", "Статус", "Срок", "Консультанты"];
  const lines: string[] = [headers.join(";")];
  for (const p of rows) {
    lines.push([
      p.num || "",
      p.board_name || "—",
      p.direction_label || "—",
      p.title || "",
      p.status || "",
      p.due_date ? fmtDate(p.due_date) : "—",
      p.consultants.map(c => c.abbr || c.code).join(" + "),
    ].map(escape).join(";"));
  }
  const blob = new Blob(["﻿" + lines.join("\n")], { type: "text/csv;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  const yr = year.value || "all";
  const co = filterConsultantCode.value || "all";
  a.download = `consultants_${yr}_${co}.csv`;
  document.body.appendChild(a);
  a.click();
  setTimeout(() => { document.body.removeChild(a); URL.revokeObjectURL(url); }, 100);
}

watch(year, load);
onMounted(load);
</script>

<template>
  <div class="cv-view">

    <!-- ═══ Topbar (dark navy) ═══ -->
    <div class="cv-topbar" @click.stop>
      <SidebarBurger />
      <div class="cv-tb-l">
        <h1 class="cv-tb-title">Консультанты</h1>
        <div class="cv-tb-sub" v-if="data?.kpis">
          <span><b v-count-up="data.kpis.consultants_active">0</b> активны</span>
          <span class="cv-dot">·</span>
          <span><b v-count-up="data.kpis.tasks_covered">0</b> задач</span>
          <span class="cv-dot">·</span>
          <span><b v-count-up="data.kpis.companies_covered">0</b> компаний</span>
        </div>
      </div>

      <div class="cv-tb-r">
        <!-- Year switcher — единый степпер «‹ FY 2026 ›» + «Все годы» -->
        <div @click.stop>
          <UzaYearStepper tone="dark" :years="data?.available_years || []"
                          :model-value="year" @update:model-value="setYear" allow-all prefix="FY " />
        </div>
      </div>
    </div>

    <!-- ═══ Body ═══ -->
    <UzaStateBlock v-if="loading && !data" state="loading" />
    <UzaStateBlock v-else-if="errorMsg" state="error" variant="block" :text="errorMsg" />

    <div v-else-if="data" ref="scanRoot" class="cv-body">

      <!-- ═══ 1. KPI strip (4 cells, .kpi2 .fin-shimmer with count-up) ═══ -->
      <div class="kpi-row cv-kpi-row kpi-rail">
        <div class="kpi2 fin-shimmer cv-kpi" style="--kpi2-accent:#3B82F6; --kpi2-d:0ms">
          <div class="kpi2-lbl">Задач охвачено</div>
          <div class="kpi2-val"><span :data-countup="data.kpis.tasks_covered">{{ data.kpis.tasks_covered }}</span></div>
        </div>
        <div class="kpi2 fin-shimmer cv-kpi" style="--kpi2-accent:#7F77DD; --kpi2-d:80ms">
          <div class="kpi2-lbl">Компаний</div>
          <div class="kpi2-val"><span :data-countup="data.kpis.companies_covered">{{ data.kpis.companies_covered }}</span></div>
        </div>
        <div class="kpi2 fin-shimmer cv-kpi" style="--kpi2-accent:#EF9F27; --kpi2-d:160ms">
          <div class="kpi2-lbl">Консультантов</div>
          <div class="kpi2-val"><span :data-countup="data.kpis.consultants_active">{{ data.kpis.consultants_active }}</span></div>
        </div>
        <div class="kpi2 fin-shimmer cv-kpi" style="--kpi2-accent:#1D9E75; --kpi2-d:240ms">
          <div class="kpi2-lbl">Среднее завершение</div>
          <div class="kpi2-val" style="color:#1D9E75">
            <span :data-countup="data.kpis.avg_completion_pct">{{ data.kpis.avg_completion_pct }}</span><span class="cv-pct-sign">%</span>
          </div>
        </div>
      </div>

      <!-- ═══ 2. 2-col grid: Consultants list | Heatmap ═══ -->
      <div class="cv-mid-grid">

        <!-- LEFT: Consultants list (1.5fr 2fr 1fr 1fr) -->
        <div class="cv-cc" style="--d:300ms">
          <div class="cv-cc-h">
            <span class="cv-cc-t">Консультанты</span>
            <span v-if="filterConsultantCode" class="cv-filter-chip">
              {{ consultantByCode[filterConsultantCode]?.name }}
              <span class="cv-filter-x" @click="filterConsultantCode = null">×</span>
            </span>
          </div>
          <div class="cv-list-head">
            <span>КОНСУЛЬТАНТ</span>
            <span>ПРОГРЕСС</span>
            <span class="r">ЗАДАЧИ</span>
            <span class="r">ПРОСРОЧЕНО</span>
          </div>
          <div class="cv-list-body">
            <!-- Big4 -->
            <div
              v-for="(c, i) in big4"
              :key="c.id"
              :class="['cv-row', { active: filterConsultantCode === c.code, big4: true }]"
              :style="{ '--stripe-color': c.color || '#888', animationDelay: (i * 30) + 'ms' }"
              role="button" tabindex="0"
              @click="openDrillConsultant(c)"
              @keydown.enter="openDrillConsultant(c)"
              @keydown.space.prevent="openDrillConsultant(c)"
              title="Открыть детализацию"
            >
              <span class="uza-stripe-el" :style="{ '--stripe-color': c.color || '#888' }" />
              <div class="cv-name">
                <span v-if="filterConsultantCode === c.code" class="cv-active-strip" :style="{ background: c.color || '#888' }"></span>
                <span class="cv-name-text">{{ c.name }}</span>
                <span class="big4-badge" :style="{ background: (c.color || '#888') + '15', color: c.color || '#888', borderColor: (c.color || '#888') + '25' }">Big 4</span>
                <button
                  class="cv-filter-mini"
                  :class="{ active: filterConsultantCode === c.code }"
                  :title="filterConsultantCode === c.code ? 'Снять фильтр' : 'Фильтровать список задач'"
                  @click.stop="selectConsultant(c.code)"
                >
                  <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
                    <path d="M3 6h18l-7 8v6l-4-2v-4z"/>
                  </svg>
                </button>
              </div>
              <div class="cv-bar-wrap">
                <div class="cv-bar"><div class="cv-bar-fill" :style="{ width: c.completion_pct + '%' }"></div></div>
                <span class="cv-pct" :style="{ color: pctColor(c.completion_pct) }">{{ c.completion_pct }}%</span>
              </div>
              <div class="cv-num r">{{ c.tasks_done }} / {{ c.tasks_total }}</div>
              <div class="cv-overdue r" :style="{ color: c.tasks_overdue > 0 ? '#993D3D' : 'var(--t3,#888780)' }">
                {{ c.tasks_overdue > 0 ? c.tasks_overdue : "—" }}
              </div>
            </div>

            <div v-if="others.length" class="cv-section-label">Другие консультанты</div>

            <!-- Others -->
            <div
              v-for="(c, i) in others"
              :key="c.id"
              :class="['cv-row', { active: filterConsultantCode === c.code }]"
              :style="{ animationDelay: ((big4.length + i) * 30) + 'ms' }"
              role="button" tabindex="0"
              @click="openDrillConsultant(c)"
              @keydown.enter="openDrillConsultant(c)"
              @keydown.space.prevent="openDrillConsultant(c)"
              title="Открыть детализацию"
            >
              <div class="cv-name">
                <span v-if="filterConsultantCode === c.code" class="cv-active-strip" :style="{ background: c.color || '#888' }"></span>
                <span class="cv-name-text">{{ c.name }}</span>
                <button
                  class="cv-filter-mini"
                  :class="{ active: filterConsultantCode === c.code }"
                  :title="filterConsultantCode === c.code ? 'Снять фильтр' : 'Фильтровать список задач'"
                  @click.stop="selectConsultant(c.code)"
                >
                  <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
                    <path d="M3 6h18l-7 8v6l-4-2v-4z"/>
                  </svg>
                </button>
              </div>
              <div class="cv-bar-wrap">
                <div class="cv-bar"><div class="cv-bar-fill" :style="{ width: c.completion_pct + '%' }"></div></div>
                <span class="cv-pct" :style="{ color: pctColor(c.completion_pct) }">{{ c.completion_pct }}%</span>
              </div>
              <div class="cv-num r">{{ c.tasks_done }} / {{ c.tasks_total }}</div>
              <div class="cv-overdue r" :style="{ color: c.tasks_overdue > 0 ? '#993D3D' : 'var(--t3,#888780)' }">
                {{ c.tasks_overdue > 0 ? c.tasks_overdue : "—" }}
              </div>
            </div>
          </div>
        </div>

        <!-- RIGHT: Heatmap (board × consultant) -->
        <div class="cv-cc cv-heat-card" :class="{ 'cv-zoomed': heatmapZoomed }" style="--d:380ms">
          <div class="cv-cc-h">
            <span class="cv-cc-t">Покрытие: доска × консультант</span>
            <div class="cv-cc-rt">
              <div class="cv-heat-legend">
                <div class="cv-heat-grad"></div>
                <span class="cv-heat-grad-label">мало → много</span>
              </div>
              <button class="cv-zoom-btn" @click="heatmapZoomed = !heatmapZoomed" :title="heatmapZoomed ? 'Свернуть' : 'Развернуть'">
                <svg v-if="!heatmapZoomed" width="14" height="14" viewBox="0 0 16 16" fill="none">
                  <path d="M2 6V2h4M10 2h4v4M14 10v4h-4M6 14H2v-4"
                    stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/>
                </svg>
                <svg v-else width="14" height="14" viewBox="0 0 16 16" fill="none">
                  <path d="M6 2v4H2M10 6h4V2M10 14v-4h4M6 10H2v4"
                    stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/>
                </svg>
              </button>
            </div>
          </div>
          <div class="cv-heat-scroll">
            <table class="cv-heat-table" v-if="data.heatmap.rows.length">
              <thead>
                <tr>
                  <th></th>
                  <th
                    v-for="c in data.heatmap.consultants"
                    :key="c.id"
                    class="cv-heat-th"
                    :title="c.name"
                    :style="{ color: c.is_big4 ? (c.color || '#888780') : '#888780', fontWeight: c.is_big4 ? 700 : 600 }"
                  >
                    {{ c.name }}{{ c.is_big4 ? " ●" : "" }}
                  </th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="r in data.heatmap.rows" :key="r.board.id">
                  <td class="cv-heat-board-name">
                    <span class="cv-heat-board-pill" :style="{ background: r.board.sector_color }"></span>
                    {{ r.board.name }}
                  </td>
                  <td v-for="(cnt, ci) in r.counts" :key="ci" class="cv-heat-cell">
                    <div
                      class="cv-heat-cell-inner"
                      :class="{ 'cv-heat-cell-clickable': cnt > 0 }"
                      :style="{ background: cellBg(cnt, data.heatmap.max), color: cellFg(cnt, data.heatmap.max) }"
                      :role="cnt > 0 ? 'button' : undefined"
                      :tabindex="cnt > 0 ? 0 : undefined"
                      :title="cnt > 0 ? `${r.board.name} × ${data.heatmap.consultants[ci].name}: ${cnt} задач — клик для детализации` : ''"
                      @click="cnt > 0 && openDrillCell(r.board.id, data.heatmap.consultants[ci].id, cnt)"
                      @keydown.enter="cnt > 0 && openDrillCell(r.board.id, data.heatmap.consultants[ci].id, cnt)"
                      @keydown.space.prevent="cnt > 0 && openDrillCell(r.board.id, data.heatmap.consultants[ci].id, cnt)"
                    >{{ cnt || "" }}</div>
                  </td>
                </tr>
              </tbody>
            </table>
            <UzaStateBlock v-else state="empty" variant="inline" text="Нет данных для тепловой карты" />
          </div>
        </div>
      </div>

      <!-- ═══ 3. 2-col grid: Direction stats | Project list ═══ -->
      <div class="cv-bot-grid">

        <!-- LEFT: Direction stats -->
        <div class="cv-cc" style="--d:460ms">
          <div class="cv-cc-h">
            <span class="cv-cc-t">Статистика по направлениям</span>
          </div>
          <div class="dir-list-head">
            <span style="grid-column: span 4">НАПРАВЛЕНИЕ</span>
            <span style="grid-column: span 4">ПРОГРЕСС</span>
            <span style="grid-column: span 1; text-align: center">ПРОСРОЧЕНО</span>
            <span style="grid-column: span 3; text-align: right">КОНСУЛЬТАНТЫ</span>
          </div>
          <div class="dir-list-body">
            <div
              v-for="(d, i) in data.dirs" :key="d.id"
              class="dir-row dir-row-clickable"
              :style="{ animationDelay: (i * 30) + 'ms' }"
              role="button" tabindex="0"
              @click="openDrillDirection(d)"
              @keydown.enter="openDrillDirection(d)"
              @keydown.space.prevent="openDrillDirection(d)"
              title="Открыть детализацию по направлению"
            >
              <span class="dir-label">{{ d.label }}</span>
              <div class="dir-bar-wrap">
                <div class="dir-bar"><div class="dir-bar-fill" :style="{ width: d.completion_pct + '%' }"></div></div>
                <span class="dir-pct">{{ d.tasks_done }}/{{ d.tasks_total }} ({{ d.completion_pct }}%)</span>
              </div>
              <div class="dir-overdue" :style="{ color: d.tasks_overdue > 0 ? '#993D3D' : '#888780' }">
                {{ d.tasks_overdue > 0 ? d.tasks_overdue : "—" }}
              </div>
              <div class="dir-badges">
                <span
                  v-for="cc in d.consultant_codes.slice(0, 2)"
                  :key="cc"
                  class="dir-badge"
                  :style="{
                    background: ((consultantByCode[cc]?.color) || '#888') + '18',
                    color: consultantByCode[cc]?.color || '#888',
                    borderColor: ((consultantByCode[cc]?.color) || '#888') + '30',
                  }"
                >{{ consultantByCode[cc]?.abbr || cc }}</span>
                <span v-if="d.consultant_codes.length > 2" class="dir-badge-extra">+{{ d.consultant_codes.length - 2 }}</span>
              </div>
            </div>
            <UzaStateBlock v-if="!data.dirs.length" state="empty" variant="inline" text="Нет данных по направлениям" />
          </div>
        </div>

        <!-- RIGHT: Project list (with CSV export) -->
        <div class="cv-cc" style="--d:520ms">
          <div class="cv-cc-h">
            <span class="cv-cc-t">
              Задачи с участием консультантов
              <span v-if="filterConsultantCode" class="cv-filter-chip-inline">
                · {{ consultantByCode[filterConsultantCode]?.name }}
                <span class="cv-filter-x" @click="filterConsultantCode = null">×</span>
              </span>
            </span>
            <button class="cv-csv-btn" @click="cvExport" title="Экспорт в CSV">↓ CSV</button>
          </div>
          <div class="proj-list">
            <div
              v-for="(p, i) in filteredProjects.slice(0, 50)"
              :key="p.id"
              class="proj-row"
              :style="{ animationDelay: (i * 25) + 'ms' }"
              role="button" tabindex="0"
              @click="openTaskEditor(p.id)"
              @keydown.enter="openTaskEditor(p.id)"
              @keydown.space.prevent="openTaskEditor(p.id)"
              title="Открыть задачу"
            >
              <span class="proj-status-dot" :style="{ background: statusDot(p.status) }"></span>
              <div class="proj-main">
                <div class="proj-title">{{ p.title }}</div>
                <div class="proj-meta">
                  <span v-if="p.board_name">{{ p.board_name }}</span>
                  <span v-if="p.num"> · #{{ p.num }}</span>
                  <span v-if="p.direction_label"> · {{ p.direction_label }}</span>
                  <span v-if="p.due_date"> · {{ fmtDate(p.due_date) }}</span>
                </div>
              </div>
              <div class="proj-cons">
                <span
                  v-for="c in p.consultants.slice(0, 3)"
                  :key="c.code"
                  class="proj-cons-pill"
                  :style="{ background: (c.color || '#888') + '18', color: c.color || '#888' }"
                >{{ c.abbr || c.code }}</span>
                <span v-if="p.consultants.length > 3" class="proj-cons-pill extra">+{{ p.consultants.length - 3 }}</span>
              </div>
            </div>
            <UzaStateBlock v-if="!filteredProjects.length" state="empty" variant="inline" text="Нет проектов" />
            <div v-else class="proj-foot">
              <span>{{ filteredProjects.length }} задач{{ filterConsultantCode ? " · " + consultantByCode[filterConsultantCode]?.name : "" }}</span>
              <span v-if="filteredProjects.length > 50" class="proj-more">показано первые 50</span>
            </div>
          </div>
        </div>
      </div>

    </div>

    <!-- ═══ Drill modal (consultant / cell / direction) ═══ -->
    <ConsultantsDrillModal
      v-if="drillOpen && data"
      :kind="drillKind"
      :consultant="drillConsultant"
      :cell-board="drillCellBoard"
      :cell-consultant="drillCellConsultant"
      :cell-count="drillCellCount"
      :direction="drillDirection"
      :all-tasks="data.projects as any"
      :consultants-by-code="consultantByCode as any"
      @close="closeDrill"
      @open-task="(id: string) => { closeDrill(); openTaskEditor(id); }"
    />

    <!-- ═══ Task editor (opened from project rows or from drill modal) ═══ -->
    <TaskProjectEditor
      v-if="editorOpen"
      :entity="editorEntity"
      kind="task"
      @close="closeEditor"
      @saved="onEditorSaved"
    />
  </div>
</template>

<style scoped>
.cv-view { background: var(--bg, #F4F3F9); min-height: 100%; font-family: var(--font, system-ui); }

@keyframes cvFadeUp {
  0% { opacity: 0; transform: translateY(6px); }
  100% { opacity: 1; transform: translateY(0); }
}
@keyframes cvCardIn {
  0%   { opacity: 0; transform: translateY(10px) scale(.98); }
  60%  { opacity: 1; transform: translateY(-2px) scale(1.005); }
  100% { opacity: 1; transform: translateY(0) scale(1); }
}
@keyframes cvRowIn {
  0% { opacity: 0; transform: translateX(-4px); }
  100% { opacity: 1; transform: translateX(0); }
}

/* ─── Topbar ─── */
.cv-topbar {
  background: linear-gradient(95deg, #1E2A4A 0%, #2D3760 60%, #4B477E 100%);
  padding: 12px 22px;
  display: flex; align-items: center; justify-content: space-between;
  gap: 14px; flex-wrap: wrap;
}
.cv-tb-l { display: flex; flex-direction: column; gap: 2px; min-width: 0; flex: 1; }
.cv-tb-title { font-size: 16px; font-weight: 600; color: #fff; margin: 0; }
.cv-tb-sub {
  font-size: 11px; color: rgba(255, 255, 255, .55);
  display: flex; align-items: center; gap: 6px;
}
.cv-tb-sub b { color: rgba(255, 255, 255, .95); font-weight: 600; }
.cv-dot { opacity: .4; }
.cv-tb-r { display: flex; align-items: center; gap: 8px; }

/* (Год-дропдаун и edit-меню удалены — переключатель года теперь UzaYearStepper.) */

.cv-body { padding: 16px 20px 24px; }

/* ─── KPI row ─── */
.cv-kpi-row { grid-template-columns: repeat(4, minmax(0, 1fr)); margin-bottom: 14px; }
@media (max-width: 1100px) { .cv-kpi-row { grid-template-columns: repeat(2, 1fr); } }
@media (max-width: 600px)  { .cv-kpi-row { grid-template-columns: 1fr; } }
.cv-kpi {
  animation: kpiCardIn .5s var(--ease-standard) var(--kpi2-d, 0ms) both;
}
.cv-pct-sign { font-size: 16px; color: var(--t3, var(--t-muted)); font-weight: 400; margin-left: 1px; }

/* ─── Cards (cc) ─── */
.cv-cc {
  background: var(--bg1, #fff);
  border: 1px solid rgba(0, 0, 0, .05);
  border-radius: 12px;
  overflow: hidden;
  display: flex; flex-direction: column;
  animation: cvCardIn .55s var(--ease-standard) var(--d, 0ms) both;
  min-width: 0;
}
.cv-cc-h {
  padding: 12px 16px;
  border-bottom: 0.5px solid rgba(0, 0, 0, .06);
  display: flex; align-items: center; justify-content: space-between;
  gap: 8px;
  flex-shrink: 0;
}
.cv-cc-t {
  font-size: 13px; font-weight: 600; color: var(--t1, #1E2A4A);
  text-transform: uppercase; letter-spacing: .04em;
}
.cv-cc-rt { display: flex; align-items: center; gap: 10px; }

.cv-filter-chip {
  display: inline-flex; align-items: center; gap: 5px;
  font-size: 11px; font-weight: 500;
  padding: 3px 9px;
  border-radius: 11px;
  background: rgba(127, 119, 221, .12);
  color: var(--p-deep);
  text-transform: none; letter-spacing: 0;
}
.cv-filter-chip-inline {
  display: inline-flex; align-items: center; gap: 5px;
  font-size: 11px; font-weight: 500;
  color: var(--p-deep);
  text-transform: none; letter-spacing: 0;
  margin-left: 6px;
}
.cv-filter-x {
  cursor: pointer;
  font-weight: 700;
  color: var(--t3, var(--t-muted));
  font-size: 13px;
  line-height: 1;
}
.cv-filter-x:hover { color: var(--sev-critical); }

/* Zoom card */
.cv-zoom-btn {
  background: transparent; border: 0;
  width: 24px; height: 24px;
  border-radius: 6px;
  display: flex; align-items: center; justify-content: center;
  color: var(--t3, var(--t-muted));
  cursor: pointer;
  transition: background .15s, color .15s;
}
.cv-zoom-btn:hover { background: #F4F3F9; color: var(--t1, #1E2A4A); }
.cv-zoomed {
  position: fixed !important;
  inset: 24px !important;
  z-index: 200 !important;
  box-shadow: 0 24px 64px rgba(15, 23, 60, .25) !important;
  margin: 0 !important;
}

/* ─── Mid grid: 1fr 2fr (consultants 1/3, heatmap 2/3) ─── */
.cv-mid-grid {
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(0, 2fr);
  gap: 12px;
  margin-bottom: 12px;
  align-items: stretch;
}
/* 13–14": список консультантов и матрица занимают полную ширину по очереди —
   имена консультантов перестают обрезаться (раньше панель была ~1/3 ширины). */
@media (max-width: 1440px) { .cv-mid-grid { grid-template-columns: 1fr; } }

/* ─── Bot grid: 1fr 1fr ─── */
.cv-bot-grid {
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(0, 1fr);
  gap: 12px;
}
@media (max-width: 1440px) { .cv-bot-grid { grid-template-columns: 1fr; } }

/* ─── Consultants list ─── */
.cv-list-head {
  display: grid; grid-template-columns: minmax(0, 1.9fr) 1.2fr 0.8fr 0.95fr;
  column-gap: 14px;
  padding: 8px 16px;
  border-bottom: 0.5px solid rgba(0, 0, 0, .04);
  font-size: 10px; font-weight: 600; color: var(--t3, var(--t-muted));
  letter-spacing: .06em; text-transform: uppercase;
}
.cv-list-head .r { text-align: right; }
.cv-list-body { padding: 4px 0; flex: 1; min-height: 0; overflow-y: auto; }

.cv-row {
  display: grid; grid-template-columns: minmax(0, 1.9fr) 1.2fr 0.8fr 0.95fr;
  align-items: center; column-gap: 14px;
  padding: 7px 16px 7px 18px;
  border-bottom: 0.5px solid rgba(0, 0, 0, .04);
  cursor: pointer;
  transition: background .12s;
  animation: cvRowIn .3s cubic-bezier(.34, 1.1, .64, 1) both;
  position: relative; overflow: hidden;
}
.cv-row.active::before {
  content: ""; position: absolute; top: 0; left: 0; right: 0;
  height: 2px; background: #7F77DD;
  animation: uzaStripeDrawIn .4s var(--ease-standard) both;
  transform-origin: left center;
  pointer-events: none;
}
.cv-row.big4 { padding-left: 18px; }
.cv-row:hover { background: rgba(127, 119, 221, .04); }
.cv-row.active { background: rgba(127, 119, 221, .06); }

.cv-name { display: flex; align-items: center; gap: 6px; min-width: 0; overflow: hidden; }
.cv-active-strip { display: inline-block; width: 2px; height: 14px; border-radius: 1px; flex-shrink: 0; }
.cv-name-text {
  font-size: 13px; font-weight: 500; color: var(--t1, #1E2A4A);
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}
.big4-badge {
  font-size: 9px; font-weight: 700;
  padding: 1px 5px;
  border-radius: 3px;
  border: 0.5px solid;
  letter-spacing: .03em;
  flex-shrink: 0;
}

/* Inline filter button — visible on row hover, persistent when active */
.cv-filter-mini {
  margin-left: auto;
  background: transparent;
  border: 1px solid rgba(127, 119, 221, 0.25);
  color: var(--p-deep);
  width: 20px; height: 20px;
  border-radius: 5px;
  display: inline-flex; align-items: center; justify-content: center;
  cursor: pointer;
  opacity: 0;
  transition: opacity .12s, background .12s, border-color .12s;
  flex-shrink: 0;
  padding: 0;
}
.cv-row:hover .cv-filter-mini { opacity: 1; }
.cv-filter-mini:hover { background: rgba(127, 119, 221, .12); border-color: #7F77DD; }
.cv-filter-mini.active {
  opacity: 1;
  background: #7F77DD;
  color: #fff;
  border-color: #7F77DD;
}

.cv-bar-wrap { display: flex; align-items: center; gap: 8px; min-width: 0; }
.cv-bar {
  flex: 1; height: 4px; border-radius: 3px;
  background: rgba(0, 0, 0, .05);
  overflow: hidden;
}
.cv-bar-fill {
  height: 100%; background: var(--green);
  border-radius: 3px;
  transition: width .5s var(--ease-standard);
}
.cv-pct {
  font-size: 12px; font-weight: 600;
  flex-shrink: 0;
  font-feature-settings: 'tnum';
  min-width: 36px; text-align: right;
}
.cv-num, .cv-overdue {
  font-size: 13px;
  font-feature-settings: 'tnum';
}
.cv-num { color: var(--t3, #5F5E5A); font-weight: 500; }
.cv-num.r, .cv-overdue.r { text-align: right; }
.cv-overdue { font-weight: 600; }

.cv-section-label {
  padding: 10px 16px 4px;
  font-size: 10px; font-weight: 600; color: var(--t3, var(--t-muted));
  text-transform: uppercase; letter-spacing: .06em;
}

/* ─── Heat map ─── */
.cv-heat-card { padding: 0; }
.cv-heat-legend { display: flex; align-items: center; gap: 6px; }
.cv-heat-grad {
  width: 40px; height: 6px; border-radius: 3px;
  background: linear-gradient(to right, #E8E6FB, #7F77DD);
}
.cv-heat-grad-label { font-size: 11px; color: var(--t3, var(--t-muted)); }
.cv-heat-scroll { padding: 12px 16px; overflow: auto; flex: 1; min-height: 0; }
.cv-heat-table { border-collapse: separate; border-spacing: 0; width: 100%; }
/* Липкие шапка (подписи консультантов) и первая колонка (имя компании): при
   ~18 колонках без них имя/подписи уезжают при скролле. Фон полупрозрачный +
   blur (как .bl-thead), hairline-тень вместо жирной границы. */
.cv-heat-th {
  padding: 4px 2px; text-align: center; font-size: 10px;
  white-space: nowrap; writing-mode: vertical-lr;
  transform: rotate(180deg);
  height: 100px; vertical-align: bottom;
  position: sticky; top: 0; z-index: 3;
  background: rgba(248, 250, 252, 0.97);
  backdrop-filter: blur(8px); -webkit-backdrop-filter: blur(8px);
}
.cv-heat-board-name {
  padding: 4px 10px 4px 0;
  font-size: 12px; font-weight: 500;
  color: var(--t3, #5F5E5A);
  white-space: nowrap;
  position: sticky; left: 0; z-index: 2;
  background: rgba(248, 250, 252, 0.97);
  backdrop-filter: blur(8px); -webkit-backdrop-filter: blur(8px);
  box-shadow: 1px 0 0 rgba(30, 42, 74, 0.06);
}
.cv-heat-table thead th:first-child {
  position: sticky; left: 0; top: 0; z-index: 4;
  background: rgba(248, 250, 252, 0.97);
  backdrop-filter: blur(8px); -webkit-backdrop-filter: blur(8px);
}
.cv-heat-board-pill {
  display: inline-block; width: 3px; height: 14px;
  border-radius: 2px;
  vertical-align: middle;
  margin-right: 6px;
}
.cv-heat-cell { padding: 2px 1px; }
.cv-heat-cell-inner {
  height: 20px; min-width: 22px;
  border-radius: 3px;
  display: flex; align-items: center; justify-content: center;
  font-size: 11px; font-weight: 700;
  font-feature-settings: 'tnum';
  animation: cvFadeUp .2s ease both;
  transition: transform .12s, box-shadow .12s;
}
.cv-heat-cell-clickable { cursor: pointer; }
.cv-heat-cell-clickable:hover {
  transform: scale(1.18);
  box-shadow: 0 2px 8px rgba(127, 119, 221, .35);
  z-index: 2;
  position: relative;
}

/* Direction row click */
.dir-row-clickable { cursor: pointer; transition: background .1s; }
.dir-row-clickable:hover { background: rgba(127, 119, 221, .04); }

/* ─── Direction stats ─── */
.dir-list-head {
  display: grid; grid-template-columns: repeat(12, 1fr);
  gap: 0 14px;
  padding: 8px 16px;
  border-bottom: 0.5px solid rgba(0, 0, 0, .04);
  font-size: 10px; font-weight: 600; color: var(--t3, var(--t-muted));
  letter-spacing: .06em; text-transform: uppercase;
}
.dir-list-body { padding: 4px 0; flex: 1; min-height: 0; overflow-y: auto; }
.dir-row {
  display: grid; grid-template-columns: repeat(12, 1fr);
  gap: 0 14px; align-items: center;
  padding: 8px 16px;
  border-bottom: 0.5px solid rgba(0, 0, 0, .04);
  animation: cvRowIn .3s cubic-bezier(.34, 1.1, .64, 1) both;
}
.dir-row:last-child { border-bottom: none; }
.dir-label {
  grid-column: span 4;
  font-size: 13px; font-weight: 500; color: var(--t1, #1E2A4A);
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}
.dir-bar-wrap {
  grid-column: span 4;
  display: flex; align-items: center; gap: 6px; min-width: 0;
}
.dir-bar {
  flex: 1; height: 4px; border-radius: 3px;
  background: rgba(0, 0, 0, .05);
  overflow: hidden; min-width: 20px;
}
.dir-bar-fill { height: 100%; background: var(--green); border-radius: 3px; transition: width .5s; }
.dir-pct {
  font-size: 11px; color: var(--t3, var(--t-muted));
  flex-shrink: 0;
  font-feature-settings: 'tnum';
}
.dir-overdue {
  grid-column: span 1; text-align: center;
  font-size: 13px; font-weight: 600;
  font-feature-settings: 'tnum';
}
.dir-badges {
  grid-column: span 3;
  display: flex; gap: 3px;
  justify-content: flex-end; flex-wrap: wrap;
}
.dir-badge {
  font-size: 11px; font-weight: 700;
  padding: 1px 5px;
  border-radius: 3px;
  border: 0.5px solid;
  white-space: nowrap;
}
.dir-badge-extra {
  font-size: 11px; font-weight: 700;
  padding: 1px 5px;
  border-radius: 3px;
  background: #F4F3F9;
  color: var(--t3, var(--t-muted));
}

/* ─── Project list ─── */
.cv-csv-btn {
  background: transparent;
  border: 0.5px solid rgba(0, 0, 0, .12);
  padding: 4px 10px;
  border-radius: 5px;
  font-size: 11px;
  font-family: inherit;
  color: var(--t3, #5F5E5A);
  cursor: pointer;
  transition: all .12s;
}
.cv-csv-btn:hover {
  background: rgba(127, 119, 221, .08);
  color: var(--p-deep);
  border-color: rgba(127, 119, 221, .35);
}
.proj-list { padding: 4px 0; flex: 1; min-height: 0; overflow-y: auto; }
.proj-row {
  display: flex; align-items: center; gap: 10px;
  padding: 9px 16px;
  border-bottom: 0.5px solid rgba(0, 0, 0, .04);
  cursor: pointer;
  animation: cvRowIn .3s cubic-bezier(.34, 1.1, .64, 1) both;
  transition: background .1s;
}
.proj-row:hover { background: rgba(127, 119, 221, .04); }
.proj-status-dot {
  width: 7px; height: 7px;
  border-radius: 50%;
  flex-shrink: 0;
}
.proj-main { flex: 1; min-width: 0; }
.proj-title {
  font-size: 13px; font-weight: 500; color: var(--t1, #1E2A4A);
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}
.proj-meta {
  font-size: 11px; color: var(--t3, var(--t-muted));
  margin-top: 2px;
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}
.proj-cons { display: flex; gap: 3px; flex-shrink: 0; }
.proj-cons-pill {
  font-size: 11px; font-weight: 700;
  padding: 1px 5px;
  border-radius: 3px;
  white-space: nowrap;
}
.proj-cons-pill.extra {
  background: #F4F3F9;
  color: var(--t3, var(--t-muted));
}
.proj-foot {
  padding: 10px 16px;
  display: flex; justify-content: space-between; align-items: center;
  font-size: 11px; color: var(--t3, var(--t-muted));
  border-top: 0.5px solid rgba(0, 0, 0, .04);
}
.proj-more { color: var(--p-deep); font-weight: 500; }

@media (max-width: 480px) {
  .dir-row { grid-template-columns: 1fr; gap: 4px 0; }
  .cv-list-head, .cv-row { gap: 8px; }
  .cv-heat-scroll { overflow-x: auto; }
}
</style>
