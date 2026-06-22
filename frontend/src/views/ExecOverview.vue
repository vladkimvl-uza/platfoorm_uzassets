<script setup lang="ts">
/**
 * ExecOverview — министерский «Сводный обзор портфеля».
 *
 * Сектор → компания → текущие проекты с дедлайнами, направлением и кратким
 * описанием. Два режима: «Дерево» (карточки) и «Таблица» (плотная, на лист A4).
 * Кнопка «Печать» печатает чистую таблицу (teleport-портал + @media print).
 */
import { ref, computed, onMounted, watch, reactive } from "vue";
import UzaStateBlock from "@/components/UZA/UzaStateBlock.vue";
import EptLogo from "@/components/EptLogo.vue";
import { execOverviewApi, type ExecOverviewResponse, type ExecOverviewProject, type ExecOverviewTask, type DeadlineState } from "@/api/execOverview";

const loading = ref(true);
const error = ref<string | null>(null);
const data = ref<ExecOverviewResponse | null>(null);
const year = ref<number>(new Date().getFullYear());

async function load() {
  loading.value = true; error.value = null;
  try {
    data.value = await execOverviewApi.get(year.value);
    // первый раз раскрываем все секторы
    if (data.value) collapsed.value = new Set();
  } catch (e: any) {
    error.value = e?.response?.data?.detail || e?.message || "Не удалось загрузить обзор";
  } finally { loading.value = false; }
}
onMounted(load);
watch(year, load);

// сворачивание секторов
const collapsed = ref<Set<string>>(new Set());
function secKey(id: string | null) { return id || "__none__"; }
function toggleSec(id: string | null) {
  const k = secKey(id);
  if (collapsed.value.has(k)) collapsed.value.delete(k); else collapsed.value.add(k);
  collapsed.value = new Set(collapsed.value);
}
function isOpen(id: string | null) { return !collapsed.value.has(secKey(id)); }
function expandAll() { collapsed.value = new Set(); }
function collapseAll() { collapsed.value = new Set((data.value?.sectors || []).map(s => secKey(s.id))); }

// дедлайны
const DL: Record<DeadlineState, { l: string; c: string }> = {
  overdue: { l: "просрочен", c: "#E24B4A" },
  month: { l: "этот месяц", c: "#D97706" },
  quarter: { l: "квартал", c: "#0891B2" },
  later: { l: "позже", c: "#64748B" },
  none: { l: "без срока", c: "#94A3B8" },
};
function fmtDue(s: string | null): string {
  if (!s) return "—";
  return new Date(s).toLocaleDateString("ru-RU", { day: "2-digit", month: "short", year: "2-digit" });
}
// финпоказатели — компактный формат UZS (трлн/млрд/млн)
function fmtFin(n: number | null): string {
  if (n == null) return "—";
  const a = Math.abs(n);
  if (a >= 1e12) return (n / 1e12).toFixed(1) + " трлн";
  if (a >= 1e9) return (n / 1e9).toFixed(1) + " млрд";
  if (a >= 1e6) return (n / 1e6).toFixed(1) + " млн";
  return new Intl.NumberFormat("ru-RU").format(Math.round(n));
}

// статусы проектов
const ST: Record<string, string> = {
  new: "Не начато", init: "Инициирование", active: "В процессе",
  review: "На согласовании", done: "Завершено", deferred: "Перенесено",
  quarterly: "Ежеквартально", monthly: "Ежемесячно", ongoing: "Постоянно",
};
const stLabel = (s: string) => ST[s] || s;

const STATUS_C: Record<string, string> = {
  new: "#94A3B8", init: "#EFA92A", active: "#7C6FF7", review: "#D97706",
  done: "#1D9E75", deferred: "#94A3B8", quarterly: "#7C6FF7", monthly: "#7C6FF7", ongoing: "#7C6FF7",
};
const stColor = (s: string) => STATUS_C[s] || "#94A3B8";

// разворот задач проекта по клику (lazy-load)
const expanded = ref<Set<string>>(new Set());
const tasksByProject = ref<Record<string, ExecOverviewTask[]>>({});
const tasksLoading = ref<Set<string>>(new Set());
async function toggleProject(id: string) {
  if (expanded.value.has(id)) {
    expanded.value.delete(id); expanded.value = new Set(expanded.value); return;
  }
  expanded.value.add(id); expanded.value = new Set(expanded.value);
  if (!(id in tasksByProject.value)) {
    tasksLoading.value.add(id); tasksLoading.value = new Set(tasksLoading.value);
    try { tasksByProject.value[id] = await execOverviewApi.projectTasks(id); }
    catch { tasksByProject.value[id] = []; }
    finally { tasksLoading.value.delete(id); tasksLoading.value = new Set(tasksLoading.value); }
  }
}

// проекты компании, сгруппированные по направлениям (колонки канбана внутри компании)
interface CoDir { id: string | null; name: string; projects: ExecOverviewProject[]; }
function companyDirections(c: { projects: ExecOverviewProject[] }): CoDir[] {
  const order = new Map((data.value?.directions || []).map((d, i) => [d.id, i]));
  const map = new Map<string, CoDir>();
  for (const p of c.projects) {
    const key = p.direction_id || "__none__";
    let col = map.get(key);
    if (!col) { col = { id: p.direction_id, name: p.direction || "Без направления", projects: [] }; map.set(key, col); }
    col.projects.push(p);
  }
  return Array.from(map.values()).sort((a, b) => {
    const oa = a.id ? (order.get(a.id) ?? 900) : 1000;
    const ob = b.id ? (order.get(b.id) ?? 900) : 1000;
    return oa - ob;
  });
}

// плоские строки для таблицы (с пометкой первой строки сектора/компании)
interface FlatRow {
  sectorName: string; sectorColor: string | null;
  companyName: string;
  p: ExecOverviewProject;
  firstOfSector: boolean; firstOfCompany: boolean;
  sectorRows: number; companyRows: number;
}
const flatRows = computed<FlatRow[]>(() => {
  const out: FlatRow[] = [];
  for (const s of data.value?.sectors || []) {
    let firstS = true;
    const sectorRows = s.total;
    for (const c of s.companies) {
      let firstC = true;
      const companyRows = c.projects.length;
      for (const p of c.projects) {
        out.push({
          sectorName: s.name, sectorColor: s.color,
          companyName: c.name, p,
          firstOfSector: firstS, firstOfCompany: firstC,
          sectorRows, companyRows,
        });
        firstS = false; firstC = false;
      }
    }
  }
  return out;
});

// ── Дорожная карта: лейны по реальным направлениям платформы ──
interface FlatProj { p: ExecOverviewProject; companyName: string; sectorColor: string | null; }
const flatProjects = computed<FlatProj[]>(() => {
  const out: FlatProj[] = [];
  for (const s of data.value?.sectors || [])
    for (const c of s.companies)
      for (const p of c.projects)
        out.push({ p, companyName: c.name, sectorColor: s.color });
  return out;
});
const PHASES = [
  { key: "new", label: "Не начато", statuses: ["new"], c: "#94A3B8" },
  { key: "init", label: "Инициирование", statuses: ["init"], c: "#EFA92A" },
  { key: "active", label: "В процессе", statuses: ["active", "quarterly", "monthly", "ongoing"], c: "#7C6FF7" },
  { key: "review", label: "На согласовании", statuses: ["review"], c: "#D97706" },
];
interface Lane { id: string; name: string; projects: FlatProj[]; }
const roadmapLanes = computed<Lane[]>(() => {
  const lanes: Lane[] = [];
  for (const d of data.value?.directions || []) {
    const projs = flatProjects.value.filter(x => x.p.direction_id === d.id);
    if (projs.length) lanes.push({ id: d.id, name: d.name, projects: projs });
  }
  const noDir = flatProjects.value.filter(x => !x.p.direction_id);
  if (noDir.length) lanes.push({ id: "__none__", name: "Без направления", projects: noDir });
  return lanes;
});
function lanePhase(lane: Lane, ph: typeof PHASES[number]): FlatProj[] {
  return lane.projects.filter(x => ph.statuses.includes(x.p.status));
}

function doPrint() { window.print(); }

// ── count-up анимация для KPI-плиток ──
const stat = reactive({ total: 0, overdue: 0, month: 0, sectors: 0, companies: 0 });
function tweenTo(key: keyof typeof stat, target: number) {
  const from = stat[key];
  if (from === target) return;
  const start = performance.now(), dur = 650;
  const tick = (now: number) => {
    const t = Math.min(1, (now - start) / dur);
    const e = 1 - Math.pow(1 - t, 3); // easeOutCubic
    stat[key] = Math.round(from + (target - from) * e);
    if (t < 1) requestAnimationFrame(tick);
  };
  requestAnimationFrame(tick);
}
watch(data, (d) => {
  if (!d) return;
  tweenTo("total", d.total);
  tweenTo("overdue", d.overdue);
  tweenTo("month", d.due_this_month);
  tweenTo("sectors", d.sector_count);
  tweenTo("companies", d.company_count);
});
</script>

<template>
  <div class="eo-root">
    <!-- ── ТОПБАР ── -->
    <div class="eo-topbar">
      <div class="eo-tb-l">
        <EptLogo :size="30" />
        <div class="eo-tb-titles">
          <h1 class="eo-title">Сводный обзор портфеля</h1>
          <div class="eo-sub">Единая платформа трансформации<template v-if="data"> · на {{ new Date(data.as_of).toLocaleDateString("ru-RU") }}</template></div>
        </div>
      </div>
      <div class="eo-tb-r">
        <div class="eo-year">
          <button @click="year--" title="Предыдущий год">‹</button>
          <span>FY {{ year }}</span>
          <button @click="year++" title="Следующий год">›</button>
        </div>
        <button class="eo-print" @click="doPrint">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="6 9 6 2 18 2 18 9"/><path d="M6 18H4a2 2 0 0 1-2-2v-5a2 2 0 0 1 2-2h16a2 2 0 0 1 2 2v5a2 2 0 0 1-2 2h-2"/><rect x="6" y="14" width="12" height="8"/></svg>
          Печать
        </button>
      </div>
    </div>
    <div class="eo-body">

    <UzaStateBlock v-if="error" state="error" variant="banner" :text="error" dismissible @dismiss="error = null" />
    <UzaStateBlock v-if="loading" state="loading" text="Собираем обзор…" />

    <template v-else-if="data">
      <!-- summary -->
      <div class="eo-stats">
        <div class="eo-stat" style="--si:0"><span class="eo-stat-n">{{ stat.total }}</span><span class="eo-stat-l">проектов</span></div>
        <div class="eo-stat eo-stat-red" style="--si:1" :class="{ dim: !data.overdue }"><span class="eo-stat-n">{{ stat.overdue }}</span><span class="eo-stat-l">просрочено</span></div>
        <div class="eo-stat eo-stat-amber" style="--si:2" :class="{ dim: !data.due_this_month }"><span class="eo-stat-n">{{ stat.month }}</span><span class="eo-stat-l">срок в этом месяце</span></div>
        <div class="eo-stat" style="--si:3"><span class="eo-stat-n">{{ stat.sectors }}</span><span class="eo-stat-l">секторов</span></div>
        <div class="eo-stat" style="--si:4"><span class="eo-stat-n">{{ stat.companies }}</span><span class="eo-stat-l">компаний</span></div>
        <div class="eo-expand">
          <button @click="expandAll">Развернуть всё</button>
          <button @click="collapseAll">Свернуть всё</button>
        </div>
      </div>

      <UzaStateBlock v-if="!data.sectors.length" state="empty" variant="block" title="Нет текущих проектов" text="За выбранный год не найдено открытых проектов. Смените год или проверьте портфель." />

      <!-- ── ДЕРЕВО (внутри компании — канбан по направлениям) ── -->
      <div v-else class="eo-tree">
        <div v-for="(s, si) in data.sectors" :key="secKey(s.id)" class="eo-sector" :style="{ animationDelay: Math.min(si*0.04, 0.4)+'s', '--sc': s.color || '#7C6FF7' }">
          <button class="eo-sec-head" @click="toggleSec(s.id)">
            <span class="eo-chev" :class="{ open: isOpen(s.id) }"></span>
            <span class="eo-sec-dot" :style="{ background: s.color || '#7C6FF7' }"></span>
            <span class="eo-sec-name">{{ s.name }}</span>
            <span class="eo-sec-meta">{{ s.company_count }} комп · {{ s.total }} проектов</span>
            <span v-if="s.overdue" class="eo-sec-ov">{{ s.overdue }} просрочено</span>
          </button>
          <div v-show="isOpen(s.id)" class="eo-companies">
            <div v-for="c in s.companies" :key="c.id" class="eo-company">
              <div class="eo-co-head">
                <span class="eo-co-name">{{ c.name }}</span>
                <span class="eo-co-meta">{{ c.total }} {{ c.total === 1 ? "проект" : "проектов" }}</span>
                <span v-if="c.overdue" class="eo-co-ov">{{ c.overdue }} просрочено</span>
                <span v-if="c.revenue != null || c.profit != null" class="eo-fin" :title="'Финпоказатели' + (c.fin_year ? ' за ' + c.fin_year : '')">
                  <span v-if="c.revenue != null" class="eo-fin-i"><span class="eo-fin-l">Выручка</span> {{ fmtFin(c.revenue) }}</span>
                  <span v-if="c.profit != null" class="eo-fin-i"><span class="eo-fin-l">Прибыль</span> <span :class="{ neg: (c.profit ?? 0) < 0 }">{{ fmtFin(c.profit) }}</span></span>
                  <span v-if="c.fin_year" class="eo-fin-y">за {{ c.fin_year }}</span>
                </span>
              </div>
              <!-- проекты компании канбаном по направлениям -->
              <div class="eo-codirs">
                <div v-for="col in companyDirections(c)" :key="col.id || '__none__'" class="eo-codir">
                  <div class="eo-codir-head"><span class="eo-codir-name">{{ col.name }}</span><span class="eo-codir-n">{{ col.projects.length }}</span></div>
                  <div class="eo-codir-body">
                    <div v-for="p in col.projects" :key="p.id" class="eo-kb-card" :class="{ open: expanded.has(p.id) }" :style="{ '--sc2': stColor(p.status) }" @click="toggleProject(p.id)">
                      <div class="eo-kb-card-title">{{ p.title }}</div>
                      <div class="eo-kb-card-meta">
                        <span class="eo-duetx" :style="{ color: DL[p.deadline_state].c }">{{ fmtDue(p.due_date) }}</span>
                        <span class="eo-pct">{{ p.progress_percent }}%</span>
                      </div>
                      <div class="eo-kb-card-foot"><span class="eo-st" :data-s="p.status">{{ stLabel(p.status) }}</span></div>
                      <div v-if="expanded.has(p.id)" class="eo-tasks" @click.stop>
                        <div v-if="tasksLoading.has(p.id)" class="eo-tasks-msg">Загрузка задач…</div>
                        <template v-else>
                          <div v-for="t in (tasksByProject[p.id] || [])" :key="t.id" class="eo-task">
                            <span class="eo-task-dot" :style="{ background: stColor(t.status) }"></span>
                            <span class="eo-task-title">{{ t.title }}</span>
                            <span v-if="t.assignee_name" class="eo-task-as">{{ t.assignee_name }}</span>
                            <span class="eo-task-due" :style="{ color: DL[t.deadline_state].c }">{{ fmtDue(t.due_date) }}</span>
                          </div>
                          <div v-if="!(tasksByProject[p.id] || []).length" class="eo-tasks-msg">У проекта нет задач</div>
                        </template>
                      </div>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>

    </template>
    </div><!-- /eo-body -->

    <!-- print portal: одна КОМПАНИЯ на лист A4 (альбом), проекты по направлениям, задачи свёрнуты -->
    <Teleport to="body">
      <div v-if="data" class="eo-print-portal">
        <template v-for="s in data.sectors" :key="'pps_' + (s.id || 'none')">
          <section v-for="c in s.companies" :key="'ppc_' + c.id" class="eo-pp-page">
            <div class="eo-pp-head">
              <div class="eo-pp-brand">
                <svg class="eo-pp-logo" viewBox="0 0 240 220" width="22" height="20" aria-hidden="true">
                  <path d="M 80 30 L 210 110 L 80 190 L 115 110 Z" fill="#534AB7" />
                  <g fill="#7F77DD"><rect x="56" y="50" width="8" height="8" /><rect x="42" y="64" width="7" height="7" /><rect x="50" y="96" width="7" height="7" /><rect x="36" y="116" width="7" height="7" /><rect x="48" y="150" width="7" height="7" /></g>
                </svg>
                <span class="eo-pp-brand-txt">Единая платформа трансформации</span>
              </div>
              <div class="eo-pp-titlerow">
                <h2>{{ c.name }}</h2>
                <span class="eo-pp-doc">{{ s.name }} · сводный обзор</span>
              </div>
              <div class="eo-pp-sub">FY {{ year }} · {{ c.total }} проектов<template v-if="c.overdue"> · {{ c.overdue }} просрочено</template><template v-if="c.revenue != null"> · Выручка {{ fmtFin(c.revenue) }}</template><template v-if="c.profit != null"> · Прибыль {{ fmtFin(c.profit) }}</template> · на {{ new Date(data.as_of).toLocaleDateString("ru-RU") }}</div>
            </div>
            <div v-for="col in companyDirections(c)" :key="col.id || '__none__'" class="eo-pp-dir">
              <div class="eo-pp-dir-head">{{ col.name }}</div>
              <table class="eo-pp-table">
                <tbody>
                  <template v-for="p in col.projects" :key="p.id">
                    <tr>
                      <td class="eo-pp-due">{{ fmtDue(p.due_date) }}<template v-if="p.deadline_state === 'overdue'"> ⚠</template></td>
                      <td class="eo-pp-title">{{ p.title }}</td>
                      <td class="eo-pp-st">{{ stLabel(p.status) }} · {{ p.progress_percent }}%</td>
                    </tr>
                    <tr v-for="t in (expanded.has(p.id) ? (tasksByProject[p.id] || []) : [])" :key="'t_' + t.id" class="eo-pp-task-row">
                      <td class="eo-pp-due">{{ fmtDue(t.due_date) }}<template v-if="t.deadline_state === 'overdue'"> ⚠</template></td>
                      <td class="eo-pp-task-title">— {{ t.title }}</td>
                      <td class="eo-pp-st">{{ stLabel(t.status) }} · {{ t.progress_percent }}%</td>
                    </tr>
                  </template>
                </tbody>
              </table>
            </div>
          </section>
        </template>
      </div>
    </Teleport>
  </div>
</template>

<style scoped>
.eo-root { padding: 0 0 40px; background: linear-gradient(180deg, rgba(127,119,221,.045), transparent 240px); min-height: 100%; }

/* ── topbar (sticky, glass) ── */
.eo-topbar {
  position: sticky; top: 0; z-index: 20;
  display: flex; align-items: center; justify-content: space-between; gap: 16px; flex-wrap: wrap;
  padding: 13px 26px;
  background: rgba(255, 255, 255, 0.72);
  -webkit-backdrop-filter: blur(16px) saturate(1.5); backdrop-filter: blur(16px) saturate(1.5);
  border-bottom: 1px solid rgba(99, 102, 180, 0.12);
  animation: eoTbIn .5s var(--ease-out, cubic-bezier(.16,1,.3,1)) both;
}
@keyframes eoTbIn { from { opacity: 0; transform: translateY(-10px); } to { opacity: 1; transform: none; } }
.eo-tb-l { display: flex; align-items: center; gap: 13px; min-width: 0; }
.eo-brandmark {
  width: 32px; height: 32px; border-radius: 9px; flex-shrink: 0; position: relative;
  background: linear-gradient(135deg, #8B7FFF, #534AB7);
  box-shadow: 0 4px 13px rgba(83, 74, 183, 0.35), inset 0 1px 1px rgba(255, 255, 255, 0.35);
}
.eo-brandmark::after { content: ""; position: absolute; inset: 10px; background: rgba(255, 255, 255, 0.92); border-radius: 2px; transform: rotate(45deg); }
.eo-tb-titles { min-width: 0; }
.eo-title { font-size: 18px; font-weight: 600; color: var(--t1, #1e2a4a); margin: 0; letter-spacing: -.01em; line-height: 1.15; }
.eo-sub { font-size: 11px; color: var(--t3, #94a3b8); margin-top: 2px; }
.eo-tb-r { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.eo-body { padding: 18px 26px 0; max-width: 1340px; margin: 0 auto; }
.eo-year { display: inline-flex; align-items: center; gap: 8px; height: 34px; padding: 0 6px; border: 1px solid var(--border, rgba(99,102,180,.16)); border-radius: 9px; background: var(--bg1, #fff); font-size: 12.5px; font-weight: 600; color: var(--t1, #1e2a4a); font-variant-numeric: tabular-nums; }
.eo-year button { border: none; background: transparent; cursor: pointer; font-size: 16px; color: var(--t3, #94a3b8); width: 22px; height: 26px; border-radius: 6px; }
.eo-year button:hover { background: rgba(124,111,247,.1); color: var(--p-deep, #534ab7); }
.eo-toggle { display: inline-flex; gap: 2px; background: var(--bg2, #fafafc); border-radius: 9px; padding: 2px; border: 1px solid var(--border, rgba(99,102,180,.12)); }
.eo-toggle button { padding: 6px 13px; border: none; background: transparent; border-radius: 7px; font-size: 12px; font-weight: 500; color: var(--t3, #94a3b8); cursor: pointer; font-family: inherit; transition: all .14s; }
.eo-toggle button.on { background: #fff; color: var(--p-deep, #534ab7); box-shadow: 0 1px 3px rgba(15,23,60,.1); }
.eo-print { display: inline-flex; align-items: center; gap: 7px; height: 34px; padding: 0 14px; border: none; border-radius: 9px; background: linear-gradient(135deg, #7f77dd, #6b62cc); color: #fff; font-size: 12px; font-weight: 500; cursor: pointer; font-family: inherit; box-shadow: 0 2px 8px rgba(127,119,221,.28); transition: transform .15s; }
.eo-print:hover { transform: translateY(-1px); }

.eo-stats { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; margin-bottom: 20px; }
.eo-stat {
  display: flex; flex-direction: column; align-items: center; min-width: 104px; padding: 12px 16px;
  border: 1px solid var(--border, rgba(99,102,180,.12)); border-radius: 14px; background: var(--bg1, #fff);
  box-shadow: 0 1px 2px rgba(15,23,60,.03);
  transition: box-shadow .2s var(--ease-out, cubic-bezier(.16,1,.3,1)), transform .2s var(--ease-out, cubic-bezier(.16,1,.3,1));
  animation: eoStatIn .5s var(--ease-out, cubic-bezier(.16,1,.3,1)) both;
  animation-delay: calc(var(--si, 0) * 70ms);
}
.eo-stat:hover { transform: translateY(-2px); box-shadow: 0 8px 20px rgba(15,23,60,.08); }
@keyframes eoStatIn { from { opacity: 0; transform: translateY(12px) scale(.97); } to { opacity: 1; transform: none; } }
.eo-stat-n { font-size: 25px; font-weight: 400; color: var(--t1, #1e2a4a); font-variant-numeric: tabular-nums; line-height: 1.05; letter-spacing: -.01em; }
.eo-stat-l { font-size: 9px; text-transform: uppercase; letter-spacing: .04em; color: var(--t3, #94a3b8); margin-top: 1px; }
.eo-stat-red { border-top: 2px solid #E24B4A; }
.eo-stat-red .eo-stat-n { color: #E24B4A; }
.eo-stat-amber { border-top: 2px solid #D97706; }
.eo-stat-amber .eo-stat-n { color: #D97706; }
.eo-stat.dim { opacity: .5; }
.eo-stat.dim { border-top-color: var(--border, rgba(99,102,180,.12)); }
.eo-stat.dim .eo-stat-n { color: var(--t3, #94a3b8); }
.eo-expand { margin-left: auto; display: flex; gap: 6px; }
.eo-expand button { padding: 6px 11px; border: 1px solid var(--border, rgba(99,102,180,.16)); border-radius: 8px; background: var(--bg1, #fff); color: var(--t2, #475569); font-size: 11px; cursor: pointer; font-family: inherit; }
.eo-expand button:hover { border-color: #7c6ff7; color: #7c6ff7; }

/* TREE */
.eo-tree { display: flex; flex-direction: column; gap: 10px; }
.eo-sector { border: 1px solid var(--border, rgba(99,102,180,.12)); border-radius: 14px; background: var(--bg1, #fff); overflow: hidden; border-top: 2px solid var(--sc); animation: eoIn .4s var(--ease-out, cubic-bezier(.16,1,.3,1)) both; }
.eo-sec-head { display: flex; align-items: center; gap: 11px; width: 100%; padding: 13px 16px; border: none; background: transparent; cursor: pointer; font-family: inherit; text-align: left; }
.eo-sec-head:hover { background: rgba(124,111,247,.03); }
.eo-chev { width: 8px; height: 8px; border-right: 2px solid var(--t3, #94a3b8); border-bottom: 2px solid var(--t3, #94a3b8); transform: rotate(-45deg); transition: transform .2s var(--ease-out, cubic-bezier(.16,1,.3,1)); flex-shrink: 0; margin-right: 2px; }
.eo-chev.open { transform: rotate(45deg); }
.eo-sec-dot { width: 9px; height: 9px; border-radius: 50%; background: var(--sc); flex-shrink: 0; }
.eo-sec-name { font-size: 14.5px; font-weight: 600; color: var(--t1, #1e2a4a); letter-spacing: -.01em; }
.eo-sec-meta { font-size: 11px; color: var(--t3, #94a3b8); font-variant-numeric: tabular-nums; }
.eo-sec-ov { margin-left: auto; font-size: 11px; font-weight: 600; color: #E24B4A; }
.eo-companies { padding: 4px 14px 14px; display: flex; flex-direction: column; gap: 12px; }
.eo-company { border-left: none; }
.eo-co-head { display: flex; align-items: center; gap: 8px; padding: 6px 2px; }
.eo-co-name { font-size: 12.5px; font-weight: 600; color: var(--t1, #1e2a4a); }
.eo-co-meta { font-size: 10.5px; color: var(--t3, #94a3b8); font-variant-numeric: tabular-nums; }
.eo-co-ov { font-size: 10.5px; font-weight: 600; color: #E24B4A; }
.eo-co-ov::before { content: "· "; color: var(--t3, #cbd5e1); font-weight: 400; }
.eo-fin { margin-left: auto; display: inline-flex; align-items: baseline; gap: 14px; flex-wrap: wrap; }
.eo-fin-i { font-size: 12px; font-weight: 600; color: var(--t1, #1e2a4a); font-variant-numeric: tabular-nums; }
.eo-fin-l { font-size: 9px; text-transform: uppercase; letter-spacing: .03em; color: var(--t3, #94a3b8); font-weight: 600; margin-right: 2px; }
.eo-fin-i .neg { color: #E24B4A; }
.eo-fin-y { font-size: 9.5px; font-weight: 600; color: var(--t3, #94a3b8); }

/* канбан направлений внутри компании — все направления в ОДИН ряд (без скролла) */
.eo-codirs { display: grid; grid-auto-flow: column; grid-auto-columns: minmax(0, 1fr); gap: 10px; padding: 2px 0 6px; margin-top: 6px; align-items: start; }
.eo-codir { min-width: 0; }
.eo-codir-head { display: flex; align-items: center; justify-content: space-between; gap: 8px; padding: 5px 9px; margin-bottom: 7px; font-size: 11px; font-weight: 600; color: var(--p-deep, #534ab7); background: rgba(127,119,221,.07); border-radius: 8px; }
.eo-codir-name { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.eo-codir-n { font-size: 9.5px; font-weight: 700; color: var(--t3, #94a3b8); flex-shrink: 0; }
.eo-codir-body { display: flex; flex-direction: column; gap: 7px; }
.eo-projects { display: grid; grid-template-columns: repeat(auto-fill, minmax(330px, 1fr)); gap: 7px; }
.eo-proj { padding: 9px 11px; border: 1px solid var(--border, rgba(99,102,180,.1)); border-radius: 10px; background: var(--bg2, #fafafc); cursor: pointer; transition: box-shadow .16s, background .16s; }
.eo-proj:hover { box-shadow: 0 4px 12px rgba(15,23,60,.06); background: #fff; }
.eo-proj.open { grid-column: 1 / -1; background: #fff; box-shadow: 0 4px 14px rgba(15,23,60,.08); }
.eo-proj-row { display: flex; gap: 10px; align-items: flex-start; }
.eo-proj-chev { width: 7px; height: 7px; border-right: 2px solid var(--t3, #94a3b8); border-bottom: 2px solid var(--t3, #94a3b8); transform: rotate(-45deg); margin: 5px 2px 0 auto; transition: transform .22s var(--ease-out, cubic-bezier(.16,1,.3,1)); flex-shrink: 0; }
.eo-proj-chev.open { transform: rotate(45deg); }
.eo-due { flex-shrink: 0; align-self: flex-start; font-size: 10px; font-weight: 700; padding: 3px 8px; border-radius: 7px; font-variant-numeric: tabular-nums; white-space: nowrap; }
.eo-proj-mark { width: 6px; height: 6px; border-radius: 50%; flex-shrink: 0; margin-top: 5px; }
.eo-duetx { font-size: 10.5px; font-weight: 700; font-variant-numeric: tabular-nums; white-space: nowrap; }
.eo-proj-main { min-width: 0; flex: 1; }
.eo-proj-title { font-size: 12.5px; font-weight: 500; color: var(--t1, #1e2a4a); line-height: 1.35; }
.eo-proj-meta { display: flex; flex-wrap: wrap; align-items: center; gap: 9px; margin-top: 4px; }
.eo-dir { font-size: 10px; font-weight: 500; color: var(--p-deep, #534ab7); }
.eo-dir::before { content: ""; display: inline-block; width: 3px; height: 3px; border-radius: 50%; background: currentColor; vertical-align: middle; margin-right: 5px; opacity: .6; }
.eo-st { font-size: 10px; font-weight: 500; color: var(--t3, #94a3b8); }
.eo-st[data-s="done"] { color: #1D9E75; }
.eo-st[data-s="active"] { color: #7C6FF7; }
.eo-st[data-s="review"] { color: #D97706; }
.eo-pct { font-size: 9.5px; color: var(--t3, #94a3b8); font-variant-numeric: tabular-nums; margin-left: auto; }
.eo-proj-desc { font-size: 10.5px; color: var(--t3, #94a3b8); line-height: 1.45; margin-top: 5px; display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; }

/* tasks expand (tree + kanban) */
.eo-tasks { margin-top: 9px; padding-top: 9px; border-top: 1px dashed var(--border, rgba(99,102,180,.18)); display: flex; flex-direction: column; gap: 2px; animation: eoTasksIn .26s var(--ease-out, cubic-bezier(.16,1,.3,1)) both; }
.eo-tasks-msg { font-size: 10.5px; color: var(--t3, #94a3b8); padding: 3px 2px; }
.eo-task { display: flex; align-items: flex-start; gap: 8px; padding: 4px; border-radius: 6px; }
.eo-task:hover { background: rgba(124,111,247,.05); }
.eo-task-dot { width: 6px; height: 6px; border-radius: 50%; flex-shrink: 0; margin-top: 5px; }
.eo-task-title { font-size: 11.5px; color: var(--t1, #1e2a4a); flex: 1; min-width: 0; line-height: 1.35; }
.eo-task-as { font-size: 10px; color: var(--t3, #94a3b8); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; max-width: 78px; flex-shrink: 0; margin-top: 1px; }
.eo-task-due { font-size: 10px; font-weight: 700; font-variant-numeric: tabular-nums; white-space: nowrap; flex-shrink: 0; margin-top: 1px; }
.eo-task-st { font-size: 10px; color: var(--t3, #94a3b8); white-space: nowrap; }
@keyframes eoTasksIn { from { opacity: 0; transform: translateY(-4px); } to { opacity: 1; transform: none; } }

/* KANBAN по направлениям */
.eo-kb-wrap { animation: eoIn .35s var(--ease-out, cubic-bezier(.16,1,.3,1)) both; }
.eo-kb { display: flex; gap: 12px; overflow-x: auto; padding-bottom: 8px; align-items: flex-start; }
.eo-kb-col { flex: 0 0 295px; max-width: 295px; background: var(--bg2, #fafafc); border: 1px solid var(--border, rgba(99,102,180,.1)); border-radius: 14px; padding: 10px; animation: eoIn .4s var(--ease-out, cubic-bezier(.16,1,.3,1)) both; }
.eo-kb-head { display: flex; align-items: center; justify-content: space-between; gap: 8px; padding: 4px 6px 10px; }
.eo-kb-head-n { font-size: 12.5px; font-weight: 600; color: var(--t1, #1e2a4a); }
.eo-kb-head-c { font-size: 10px; font-weight: 700; color: var(--t3, #94a3b8); background: rgba(30,42,74,.06); border-radius: 8px; padding: 0 7px; }
.eo-kb-body { display: flex; flex-direction: column; gap: 8px; }
.eo-kb-card { background: var(--bg1, #fff); border: 1px solid var(--border, rgba(99,102,180,.12)); border-top: 2px solid var(--sc2); border-radius: 10px; padding: 9px 11px; cursor: pointer; box-shadow: 0 1px 2px rgba(15,23,60,.03); transition: box-shadow .15s, transform .15s; }
.eo-kb-card:hover { box-shadow: 0 5px 14px rgba(15,23,60,.1); transform: translateY(-1px); }
.eo-kb-card.open { box-shadow: 0 5px 16px rgba(15,23,60,.12); }
.eo-kb-card-title { font-size: 12px; font-weight: 500; color: var(--t1, #1e2a4a); line-height: 1.35; }
.eo-kb-card-meta { display: flex; align-items: center; justify-content: space-between; gap: 8px; margin-top: 6px; }
.eo-kb-card-co { font-size: 10px; color: var(--t3, #94a3b8); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.eo-kb-card-foot { display: flex; align-items: center; gap: 8px; margin-top: 5px; }

/* TABLE */
.eo-tablewrap { overflow-x: auto; border: 1px solid var(--border, rgba(99,102,180,.12)); border-radius: 12px; }
.eo-table { border-collapse: collapse; width: 100%; font-size: 12px; min-width: 880px; }
.eo-table thead th { background: var(--bg2, #fafafc); text-align: left; font-weight: 600; color: var(--t2, #475569); padding: 10px 12px; font-size: 10.5px; text-transform: uppercase; letter-spacing: .03em; position: sticky; top: 0; }
.eo-table td { padding: 9px 12px; border-top: 1px solid var(--border, rgba(99,102,180,.07)); vertical-align: top; }
.eo-tr-sec td { border-top: 1.5px solid var(--border, rgba(99,102,180,.18)); }
.eo-td-sec { font-weight: 600; color: var(--t1, #1e2a4a); white-space: nowrap; }
.eo-tdot { display: inline-block; width: 8px; height: 8px; border-radius: 50%; margin-right: 6px; vertical-align: middle; }
.eo-td-co { font-weight: 500; color: var(--t2, #475569); white-space: nowrap; }
.eo-td-dir { color: var(--t3, #94a3b8); white-space: nowrap; }
.eo-td-title { font-weight: 500; color: var(--t1, #1e2a4a); }
.eo-td-desc { font-size: 10.5px; color: var(--t3, #94a3b8); margin-top: 2px; max-width: 380px; }

/* ROADMAP (swim-lanes по направлениям) */
.eo-rm-wrap { animation: eoIn .35s var(--ease-out, cubic-bezier(.16,1,.3,1)) both; }
.eo-rm-legend { display: flex; align-items: center; gap: 14px; flex-wrap: wrap; margin-bottom: 12px; }
.eo-rm-leg-t { font-size: 10px; text-transform: uppercase; letter-spacing: .05em; color: var(--t3, #94a3b8); font-weight: 700; }
.eo-rm-leg { display: inline-flex; align-items: center; gap: 6px; font-size: 11px; color: var(--t2, #475569); }
.eo-rm-leg-d { width: 9px; height: 9px; border-radius: 3px; }
.eo-rm { overflow-x: auto; border: 1px solid var(--border, rgba(99,102,180,.12)); border-radius: 14px; background: var(--bg1, #fff); }
.eo-rm-grid { display: grid; grid-template-columns: 170px repeat(4, minmax(165px, 1fr)); min-width: 820px; }
.eo-rm-head { position: sticky; top: 0; background: var(--bg2, #fafafc); border-bottom: 1px solid var(--border, rgba(99,102,180,.12)); z-index: 1; }
.eo-rm-corner { padding: 12px 14px; font-size: 10px; text-transform: uppercase; letter-spacing: .04em; color: var(--t3, #94a3b8); font-weight: 700; }
.eo-rm-ph { position: relative; padding: 12px 14px; font-size: 11px; font-weight: 700; color: var(--pc); border-left: 1px solid var(--border, rgba(99,102,180,.08)); }
.eo-rm-arr { position: absolute; right: -8px; top: 50%; transform: translateY(-50%); color: var(--t3, #cbd5e1); font-size: 18px; z-index: 2; }
.eo-rm-lane { border-top: 1px solid var(--border, rgba(99,102,180,.1)); animation: eoIn .4s var(--ease-out, cubic-bezier(.16,1,.3,1)) both; transition: background .14s; }
.eo-rm-lane:hover { background: rgba(124,111,247,.02); }
.eo-rm-label { padding: 12px 14px; display: flex; flex-direction: column; gap: 4px; justify-content: flex-start; }
.eo-rm-label-n { font-size: 12px; font-weight: 600; color: var(--t1, #1e2a4a); line-height: 1.3; }
.eo-rm-label-c { font-size: 10px; font-weight: 700; color: var(--t3, #94a3b8); background: rgba(30,42,74,.06); border-radius: 8px; padding: 0 7px; align-self: flex-start; }
.eo-rm-cell { padding: 10px 9px; border-left: 1px solid var(--border, rgba(99,102,180,.07)); min-height: 56px; }
.eo-rm-card { background: var(--bg1, #fff); border: 1px solid var(--border, rgba(99,102,180,.12)); border-top: 2px solid var(--pc); border-radius: 8px; padding: 7px 9px; margin-bottom: 6px; box-shadow: 0 1px 2px rgba(15,23,60,.03); transition: box-shadow .15s, transform .15s; }
.eo-rm-card:last-child { margin-bottom: 0; }
.eo-rm-card:hover { box-shadow: 0 5px 14px rgba(15,23,60,.1); transform: translateY(-1px); }
.eo-rm-card-title { font-size: 11.5px; font-weight: 500; color: var(--t1, #1e2a4a); line-height: 1.35; display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; }
.eo-rm-card-meta { display: flex; align-items: center; justify-content: space-between; gap: 6px; margin-top: 5px; }
.eo-rm-card-co { font-size: 9.5px; color: var(--t3, #94a3b8); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.eo-rm-card-due { font-size: 9px; font-weight: 700; padding: 1px 6px; border-radius: 6px; flex-shrink: 0; font-variant-numeric: tabular-nums; }
.eo-rm-empty { min-height: 20px; }
.eo-rm-none { margin-top: 14px; padding: 16px; text-align: center; font-size: 12px; color: var(--t3, #94a3b8); }

@keyframes eoIn { from { opacity: 0; transform: translateY(8px); } to { opacity: 1; transform: none; } }

/* print portal hidden on screen */
.eo-print-portal { display: none; }

@media (max-width: 640px) {
  .eo-topbar { padding: 12px 14px; }
  .eo-body { padding: 14px 14px 0; }
  .eo-projects { grid-template-columns: 1fr; }
}
</style>

<!-- Глобальные стили печати: фирменное оформление, один сектор на лист A4 (альбом) -->
<style>
@media print {
  #app { display: none !important; }
  .eo-print-portal {
    display: block !important;
    font-family: -apple-system, "Segoe UI", Roboto, "Helvetica Neue", sans-serif;
    color: #1a1f3c;
    -webkit-print-color-adjust: exact; print-color-adjust: exact;
  }
  @page { size: A4 landscape; margin: 11mm 12mm; }

  /* одна КОМПАНИЯ = одна страница */
  .eo-pp-page { break-after: page; page-break-after: always; }
  .eo-pp-page:last-child { break-after: auto; page-break-after: auto; }

  /* фирменная минималистичная шапка с логотипом платформы */
  .eo-pp-head { border-bottom: 1.5pt solid #534AB7; padding-bottom: 8px; margin-bottom: 12px; }
  .eo-pp-brand { display: flex; align-items: center; gap: 8px; margin-bottom: 8px; }
  .eo-pp-logo { display: block; flex-shrink: 0; }
  .eo-pp-brand-txt { font-size: 8pt; font-weight: 700; text-transform: uppercase; letter-spacing: .2em; color: #6B62CC; }
  .eo-pp-titlerow { display: flex; align-items: baseline; justify-content: space-between; gap: 12px; }
  .eo-pp-head h2 { font-size: 18pt; font-weight: 600; margin: 0; letter-spacing: -.01em; color: #161b33; }
  .eo-pp-doc { font-size: 8.5pt; color: #8A90A8; font-weight: 500; white-space: nowrap; }
  .eo-pp-sub { font-size: 8.5pt; color: #6b7088; margin-top: 4px; font-variant-numeric: tabular-nums; }

  /* проекты по направлениям (свёрнуто, без задач) */
  .eo-pp-dir { break-inside: avoid; margin-bottom: 8px; }
  .eo-pp-dir-head { font-size: 9pt; font-weight: 700; text-transform: uppercase; letter-spacing: .05em; color: #6B62CC; padding: 2px 0 3px; border-bottom: .5pt solid #d7d9e6; margin-bottom: 2px; }
  .eo-pp-table { border-collapse: collapse; width: 100%; font-size: 8.5pt; }
  .eo-pp-table td { padding: 2.5px 6px; border-bottom: .4pt solid #ececf3; vertical-align: top; }
  .eo-pp-due { white-space: nowrap; color: #534AB7; font-weight: 600; font-variant-numeric: tabular-nums; width: 64px; }
  .eo-pp-title { color: #1a1f3c; }
  .eo-pp-st { white-space: nowrap; color: #6b7088; text-align: right; width: 130px; }
  /* задачи раскрытого проекта в печати */
  .eo-pp-task-row td { border-bottom: .3pt solid #f1f1f7; padding-top: 1.5px; padding-bottom: 1.5px; }
  .eo-pp-task-title { color: #6b7088; font-size: 8pt; padding-left: 16px; }
}
</style>
