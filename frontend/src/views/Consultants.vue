<script setup lang="ts">
import { ref, computed, onMounted, watch } from "vue";
import { api } from "@/api/client";

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
interface HeatmapRow {
  board: HeatmapBoard;
  counts: number[];
}
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
  board_name: string | null;
  status: string;
  due_date: string | null;
  direction_id: string | null;
  direction_label: string | null;
  consultants: { code: string; abbr: string | null; color: string | null }[];
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

const big4 = computed(() =>
  (data.value?.consultants || []).filter(c => c.is_big4)
);
const others = computed(() =>
  (data.value?.consultants || []).filter(c => !c.is_big4)
);

const filteredProjects = computed(() => {
  if (!data.value) return [];
  if (!filterConsultantCode.value) return data.value.projects;
  return data.value.projects.filter(p =>
    p.consultants.some(c => c.code === filterConsultantCode.value)
  );
});

// ─── Helpers ─────────────────────────────────────────────────────
function pctColor(p: number): string {
  if (p >= 60) return "#1D9E75";
  if (p >= 30) return "#D97706";
  return "#993D3D";
}

function statusDot(status: string): string {
  const m: Record<string, string> = {
    done: "#1D9E75", active: "#2b7de9", overdue: "#ef4444",
    init: "#9ca3af", new: "#d1d5db", review: "#f59e0b",
  };
  return m[status] || "#d1d5db";
}

// Heat-map cell colour: white-purple gradient based on count/max
function cellBg(count: number, max: number): string {
  if (count === 0) return "var(--bg3)";
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

// ─── Load ────────────────────────────────────────────────────────
async function load() {
  loading.value = true;
  errorMsg.value = null;
  try {
    const params: Record<string, any> = {};
    if (year.value) params.year = year.value;
    const res = await api.get<OverviewResponse>("/consultants/overview", { params });
    data.value = res.data;
  } catch (e: any) {
    errorMsg.value = e?.response?.data?.detail || e?.message || "Ошибка загрузки";
    data.value = null;
  } finally {
    loading.value = false;
  }
}

function selectConsultant(code: string | null) {
  filterConsultantCode.value = filterConsultantCode.value === code ? null : code;
}

watch(year, load);
onMounted(load);
</script>

<template>
  <div class="cv-page">
    <!-- Header -->
    <div class="page-header">
      <div class="page-eyebrow">UZASSETS · КОНСУЛЬТАНТЫ</div>
      <h1 class="page-title">Big-4 и консалтинг в портфеле</h1>
      <div class="page-sub">Проекты с участием внешних консультантов</div>
    </div>

    <!-- Year filter -->
    <div class="year-filter" v-if="data?.available_years?.length">
      <button :class="['pill', { active: year === null }]" @click="year = null">Все годы</button>
      <button v-for="y in data.available_years" :key="y"
              :class="['pill', { active: year === y }]"
              @click="year = y">{{ y }}</button>
    </div>

    <div v-if="loading && !data" class="state-msg">Загрузка…</div>
    <div v-else-if="errorMsg" class="state-msg error">⚠ {{ errorMsg }}</div>

    <template v-else-if="data">
      <!-- ─── KPI bar (4 cards) ─────────────────────────────── -->
      <div class="kpi-strip">
        <div class="kpi-card" style="--kpi-accent: #3B82F6">
          <div class="kpi-label">ЗАДАЧ ОХВАЧЕНО</div>
          <div class="kpi-value">{{ data.kpis.tasks_covered }}</div>
        </div>
        <div class="kpi-card" style="--kpi-accent: #7F77DD">
          <div class="kpi-label">КОМПАНИЙ</div>
          <div class="kpi-value">{{ data.kpis.companies_covered }}</div>
        </div>
        <div class="kpi-card" style="--kpi-accent: #EF9F27">
          <div class="kpi-label">КОНСУЛЬТАНТОВ</div>
          <div class="kpi-value">{{ data.kpis.consultants_active }}</div>
        </div>
        <div class="kpi-card" style="--kpi-accent: #1D9E75">
          <div class="kpi-label">СРЕДНЕЕ ЗАВЕРШЕНИЕ</div>
          <div class="kpi-value" style="color: #1D9E75">{{ data.kpis.avg_completion_pct }}%</div>
        </div>
      </div>

      <!-- ─── 2-column grid: consultants list + dirs stats ───── -->
      <div class="grid-2">
        <!-- Consultants list -->
        <div class="cc">
          <div class="cc-title">Консультанты</div>
          <div class="cv-list-head">
            <span>КОНСУЛЬТАНТ</span>
            <span>ПРОГРЕСС</span>
            <span class="r">ЗАДАЧИ</span>
            <span class="r">ПРОСРОЧЕНО</span>
          </div>
          <div class="cv-list-body">
            <!-- Big4 -->
            <div v-for="c in big4" :key="c.id"
                 :class="['cv-row', { active: filterConsultantCode === c.code, big4: true }]"
                 :style="{ borderLeftColor: c.color || '#888' }"
                 @click="selectConsultant(c.code)">
              <div class="cv-name">
                <span class="cv-name-text">{{ c.name }}</span>
                <span class="big4-badge" :style="{ background: (c.color || '#888') + '15', color: c.color || '#888', borderColor: (c.color || '#888') + '25' }">Big 4</span>
              </div>
              <div class="cv-bar-wrap">
                <div class="cv-bar"><div class="cv-bar-fill" :style="{ width: c.completion_pct + '%' }"></div></div>
                <span class="cv-pct" :style="{ color: pctColor(c.completion_pct) }">{{ c.completion_pct }}%</span>
              </div>
              <div class="cv-num r">{{ c.tasks_done }} / {{ c.tasks_total }}</div>
              <div class="cv-overdue r" :style="{ color: c.tasks_overdue > 0 ? '#993D3D' : 'var(--t3)' }">
                {{ c.tasks_overdue > 0 ? c.tasks_overdue : "—" }}
              </div>
            </div>

            <!-- Section divider -->
            <div v-if="others.length" class="cv-section-label">Другие консультанты</div>

            <!-- Others -->
            <div v-for="c in others" :key="c.id"
                 :class="['cv-row', { active: filterConsultantCode === c.code }]"
                 @click="selectConsultant(c.code)">
              <div class="cv-name">
                <span class="cv-name-text">{{ c.name }}</span>
              </div>
              <div class="cv-bar-wrap">
                <div class="cv-bar"><div class="cv-bar-fill" :style="{ width: c.completion_pct + '%' }"></div></div>
                <span class="cv-pct" :style="{ color: pctColor(c.completion_pct) }">{{ c.completion_pct }}%</span>
              </div>
              <div class="cv-num r">{{ c.tasks_done }} / {{ c.tasks_total }}</div>
              <div class="cv-overdue r" :style="{ color: c.tasks_overdue > 0 ? '#993D3D' : 'var(--t3)' }">
                {{ c.tasks_overdue > 0 ? c.tasks_overdue : "—" }}
              </div>
            </div>
          </div>
          <div v-if="filterConsultantCode" class="cv-active-filter">
            Фильтр: <strong>{{ data.consultants.find(c => c.code === filterConsultantCode)?.name }}</strong>
            <span class="reset-link" @click="filterConsultantCode = null">сбросить ×</span>
          </div>
        </div>

        <!-- Direction stats -->
        <div class="cc">
          <div class="cc-title">Статистика по направлениям</div>
          <div class="dir-list-head">
            <span style="grid-column: span 4">НАПРАВЛЕНИЕ</span>
            <span style="grid-column: span 4">ПРОГРЕСС</span>
            <span style="grid-column: span 1; text-align: center">ПРОСРОЧЕНО</span>
            <span style="grid-column: span 3; text-align: right">КОНСУЛЬТАНТЫ</span>
          </div>
          <div class="dir-list-body">
            <div v-for="d in data.dirs" :key="d.id" class="dir-row">
              <span class="dir-label">{{ d.label }}</span>
              <div class="dir-bar-wrap">
                <div class="dir-bar"><div class="dir-bar-fill" :style="{ width: d.completion_pct + '%' }"></div></div>
                <span class="dir-pct">{{ d.tasks_done }}/{{ d.tasks_total }} ({{ d.completion_pct }}%)</span>
              </div>
              <div class="dir-overdue" :style="{ color: d.tasks_overdue > 0 ? '#993D3D' : 'var(--t3)' }">
                {{ d.tasks_overdue > 0 ? d.tasks_overdue : "—" }}
              </div>
              <div class="dir-badges">
                <span v-for="cc in d.consultant_codes.slice(0, 2)" :key="cc"
                      class="dir-badge"
                      :style="{
                        background: ((data.consultants.find(x => x.code === cc)?.color) || '#888') + '18',
                        color: (data.consultants.find(x => x.code === cc)?.color) || '#888',
                        borderColor: ((data.consultants.find(x => x.code === cc)?.color) || '#888') + '30'
                      }">
                  {{ data.consultants.find(x => x.code === cc)?.abbr || cc }}
                </span>
                <span v-if="d.consultant_codes.length > 2" class="dir-badge-extra">
                  +{{ d.consultant_codes.length - 2 }}
                </span>
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- ─── Heat map: boards × consultants ─────────────────── -->
      <div class="cc heat-card">
        <div class="heat-head">
          <span class="cc-title">Покрытие: компания × консультант</span>
          <div class="heat-legend">
            <div class="heat-grad"></div>
            <span class="heat-grad-label">мало → много</span>
          </div>
        </div>
        <div class="heat-scroll">
          <table class="heat-table" v-if="data.heatmap.rows.length">
            <thead>
              <tr>
                <th></th>
                <th v-for="c in data.heatmap.consultants" :key="c.id"
                    class="heat-th"
                    :title="c.name"
                    :style="{ color: c.is_big4 ? (c.color || 'var(--t3)') : 'var(--t3)',
                              fontWeight: c.is_big4 ? 700 : 600 }">
                  {{ c.name }}{{ c.is_big4 ? " ●" : "" }}
                </th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="r in data.heatmap.rows" :key="r.board.id">
                <td class="heat-board-name">
                  <span class="heat-board-pill" :style="{ background: r.board.sector_color }"></span>
                  {{ r.board.name }}
                </td>
                <td v-for="(cnt, ci) in r.counts" :key="ci" class="heat-cell">
                  <div class="heat-cell-inner"
                       :style="{ background: cellBg(cnt, data.heatmap.max), color: cellFg(cnt, data.heatmap.max) }">
                    {{ cnt || "" }}
                  </div>
                </td>
              </tr>
            </tbody>
          </table>
          <div v-else class="state-msg">Нет данных для тепловой карты</div>
        </div>
      </div>

      <!-- ─── Project list ───────────────────────────────────── -->
      <div class="cc">
        <div class="cc-title">
          Проекты и задачи
          <span v-if="filterConsultantCode" class="cv-filter-tag">
            · фильтр {{ data.consultants.find(c => c.code === filterConsultantCode)?.name }}
          </span>
        </div>
        <div class="proj-list">
          <div v-for="p in filteredProjects" :key="p.id" class="proj-row">
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
              <span v-for="c in p.consultants" :key="c.code"
                    class="proj-cons-pill"
                    :style="{ background: (c.color || '#888') + '18', color: c.color || '#888' }">
                {{ c.abbr || c.code }}
              </span>
            </div>
          </div>
          <div v-if="!filteredProjects.length" class="state-msg">Нет проектов</div>
        </div>
      </div>
    </template>
  </div>
</template>

<style scoped>
.cv-page { padding: 24px 32px; }

.page-header { margin-bottom: 16px; }
.page-eyebrow {
  font-size: 10px; font-weight: 500; letter-spacing: 0.08em;
  text-transform: uppercase; color: var(--t3); margin-bottom: 8px;
}
.page-title {
  font-size: 22px; font-weight: 500; letter-spacing: -0.01em;
  margin: 0 0 6px; color: var(--t1);
}
.page-sub { font-size: 13px; color: var(--t3); }

.year-filter {
  display: flex; gap: 4px; margin-bottom: 20px; flex-wrap: wrap;
}
.pill {
  padding: 4px 12px; font-size: 12px; font-weight: 500;
  border-radius: 11px; border: 1px solid var(--border1);
  background: var(--bg1); color: var(--t2); cursor: pointer;
  transition: all .15s;
}
.pill:hover { background: var(--bg3); }
.pill.active { background: #7F77DD; color: white; border-color: #7F77DD; }

.state-msg { padding: 32px; text-align: center; color: var(--t3); font-size: 13px; }
.state-msg.error { color: #993D3D; }

.kpi-strip {
  display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px; margin-bottom: 20px;
}
.kpi-card {
  background: var(--bg1); padding: 16px 18px; border-radius: 12px;
  border: 1px solid var(--border1);
  border-left: 3px solid var(--kpi-accent);
  box-shadow: 0 4px 12px rgba(15,23,60,.04);
}
.kpi-label {
  font-size: 10px; font-weight: 500; letter-spacing: 0.06em;
  text-transform: uppercase; color: var(--t3); margin-bottom: 8px;
}
.kpi-value {
  font-size: 22px; font-weight: 400; letter-spacing: -0.025em; color: var(--t1);
}

.grid-2 {
  display: grid; grid-template-columns: 1fr 1fr; gap: 16px; margin-bottom: 20px;
}
@media (max-width: 1100px) {
  .grid-2 { grid-template-columns: 1fr; }
}

.cc {
  background: var(--bg1); border-radius: 12px;
  border: 1px solid var(--border1); overflow: hidden;
  box-shadow: 0 4px 12px rgba(15,23,60,.04);
  margin-bottom: 16px;
  display: flex; flex-direction: column;
}
.cc-title {
  padding: 14px 18px 10px; font-size: 15px; font-weight: 500;
  letter-spacing: -0.01em; color: var(--t1);
  border-bottom: 1px solid var(--border1);
}
.cv-filter-tag { font-size: 12px; font-weight: 400; color: var(--t3); margin-left: 4px; }

/* Consultants list */
.cv-list-head {
  display: grid; grid-template-columns: 1.5fr 2fr 1fr 1fr; column-gap: 14px;
  padding: 8px 18px; border-bottom: 1px solid var(--border1);
  font-size: 10px; font-weight: 500; color: var(--t3);
  letter-spacing: .06em; text-transform: uppercase;
}
.cv-list-head .r { text-align: right; }
.cv-list-body { padding: 4px 0; }
.cv-row {
  display: grid; grid-template-columns: 1.5fr 2fr 1fr 1fr;
  align-items: center; column-gap: 14px;
  padding: 8px 18px; border-bottom: 1px solid var(--border1);
  cursor: pointer; transition: background .12s;
  border-left: 3px solid transparent;
}
.cv-row.big4 { padding-left: 15px; }  /* compensate 3px border */
.cv-row:hover { background: var(--bg2); }
.cv-row.active { background: rgba(127, 119, 221, .04); }
.cv-row:last-child { border-bottom: none; }

.cv-name { display: flex; align-items: center; gap: 8px; min-width: 0; }
.cv-name-text {
  font-size: 13px; font-weight: 500; color: var(--t1);
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}
.big4-badge {
  font-size: 9px; font-weight: 700; padding: 1px 5px;
  border-radius: 3px; border: 0.5px solid;
  letter-spacing: .03em; flex-shrink: 0;
}
.cv-bar-wrap { display: flex; align-items: center; gap: 8px; min-width: 0; }
.cv-bar { flex: 1; height: 4px; border-radius: 3px; background: var(--bg3); overflow: hidden; }
.cv-bar-fill { height: 100%; background: #1D9E75; transition: width .4s; }
.cv-pct { font-size: 12px; font-weight: 600; flex-shrink: 0; font-variant-numeric: tabular-nums; min-width: 36px; text-align: right; }
.cv-num { font-size: 13px; color: var(--t2); font-variant-numeric: tabular-nums; font-weight: 500; }
.cv-num.r, .cv-overdue.r { text-align: right; }
.cv-overdue { font-size: 13px; font-weight: 600; font-variant-numeric: tabular-nums; }

.cv-section-label {
  padding: 10px 18px 4px;
  font-size: 10px; font-weight: 500; color: var(--t3);
  text-transform: uppercase; letter-spacing: .06em;
}

.cv-active-filter {
  padding: 10px 18px; font-size: 12px; color: var(--t3);
  border-top: 1px solid var(--border1);
}
.reset-link { color: #7F77DD; cursor: pointer; margin-left: 4px; }
.reset-link:hover { text-decoration: underline; }

/* Direction stats */
.dir-list-head {
  display: grid; grid-template-columns: repeat(12, 1fr); gap: 0 16px;
  padding: 8px 18px; border-bottom: 1px solid var(--border1);
  font-size: 10px; font-weight: 500; color: var(--t3);
  letter-spacing: .06em; text-transform: uppercase;
}
.dir-list-body { padding: 4px 0; }
.dir-row {
  display: grid; grid-template-columns: repeat(12, 1fr);
  gap: 0 16px; align-items: center;
  padding: 9px 18px; border-bottom: 1px solid var(--border1);
}
.dir-row:last-child { border-bottom: none; }
.dir-label {
  grid-column: span 4; font-size: 13px; font-weight: 500; color: var(--t1);
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}
.dir-bar-wrap { grid-column: span 4; display: flex; align-items: center; gap: 6px; min-width: 0; }
.dir-bar { flex: 1; height: 4px; border-radius: 3px; background: var(--bg3); overflow: hidden; min-width: 20px; }
.dir-bar-fill { height: 100%; background: #1D9E75; transition: width .4s; }
.dir-pct { font-size: 11px; color: var(--t3); flex-shrink: 0; font-variant-numeric: tabular-nums; }
.dir-overdue {
  grid-column: span 1; text-align: center;
  font-size: 13px; font-weight: 600; font-variant-numeric: tabular-nums;
}
.dir-badges {
  grid-column: span 3; display: flex; gap: 3px;
  justify-content: flex-end; flex-wrap: wrap;
}
.dir-badge {
  font-size: 11px; font-weight: 700; padding: 1px 5px;
  border-radius: 3px; border: 0.5px solid; white-space: nowrap;
}
.dir-badge-extra {
  font-size: 11px; font-weight: 700; padding: 1px 5px;
  border-radius: 3px; background: var(--bg3); color: var(--t3);
}

/* Heat map */
.heat-card { padding: 0; }
.heat-head {
  padding: 14px 18px 10px;
  display: flex; align-items: center; justify-content: space-between;
  border-bottom: 1px solid var(--border1);
}
.heat-legend { display: flex; align-items: center; gap: 6px; }
.heat-grad {
  width: 40px; height: 6px; border-radius: 3px;
  background: linear-gradient(to right, #E8E6FB, #7F77DD);
}
.heat-grad-label { font-size: 11px; color: var(--t3); }
.heat-scroll { padding: 12px 16px; overflow-x: auto; }
.heat-table { border-collapse: collapse; }
.heat-th {
  padding: 4px 2px; text-align: center; font-size: 10px;
  white-space: nowrap; writing-mode: vertical-lr; transform: rotate(180deg);
  height: 80px; vertical-align: bottom;
}
.heat-board-name {
  padding: 4px 12px 4px 0; font-size: 12px; font-weight: 500;
  color: var(--t2); white-space: nowrap;
}
.heat-board-pill {
  display: inline-block; width: 3px; height: 14px;
  border-radius: 2px; vertical-align: middle; margin-right: 6px;
}
.heat-cell { padding: 2px 1px; }
.heat-cell-inner {
  height: 22px; min-width: 24px; border-radius: 3px;
  display: flex; align-items: center; justify-content: center;
  font-size: 11px; font-weight: 700;
}

/* Project list */
.proj-list { padding: 4px 0; }
.proj-row {
  display: flex; align-items: center; gap: 12px;
  padding: 10px 18px; border-bottom: 1px solid var(--border1);
}
.proj-row:last-child { border-bottom: none; }
.proj-status-dot { width: 8px; height: 8px; border-radius: 50%; flex-shrink: 0; }
.proj-main { flex: 1; min-width: 0; }
.proj-title {
  font-size: 13px; font-weight: 500; color: var(--t1);
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}
.proj-meta { font-size: 11px; color: var(--t3); margin-top: 2px; }
.proj-cons { display: flex; gap: 4px; flex-shrink: 0; }
.proj-cons-pill {
  font-size: 10px; font-weight: 700; padding: 2px 6px;
  border-radius: 3px; white-space: nowrap;
}
</style>
