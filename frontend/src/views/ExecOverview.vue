<script setup lang="ts">
/**
 * ExecOverview — министерский «Сводный обзор портфеля».
 *
 * Сектор → компания → текущие проекты с дедлайнами, направлением и кратким
 * описанием. Два режима: «Дерево» (карточки) и «Таблица» (плотная, на лист A4).
 * Кнопка «Печать» печатает чистую таблицу (teleport-портал + @media print).
 */
import { ref, computed, onMounted, watch } from "vue";
import UzaStateBlock from "@/components/UZA/UzaStateBlock.vue";
import { execOverviewApi, type ExecOverviewResponse, type ExecOverviewProject, type DeadlineState } from "@/api/execOverview";

const loading = ref(true);
const error = ref<string | null>(null);
const data = ref<ExecOverviewResponse | null>(null);
const year = ref<number>(new Date().getFullYear());
const mode = ref<"tree" | "table" | "roadmap">("tree");

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
</script>

<template>
  <div class="eo-root">
    <!-- header -->
    <div class="eo-head">
      <div class="eo-head-l">
        <h1 class="eo-title">Сводный обзор портфеля</h1>
        <div v-if="data" class="eo-sub">Сектор → компания → текущие проекты и дедлайны · на {{ new Date(data.as_of).toLocaleDateString("ru-RU") }}</div>
      </div>
      <div class="eo-head-r">
        <div class="eo-year">
          <button @click="year--" title="Предыдущий год">‹</button>
          <span>FY {{ year }}</span>
          <button @click="year++" title="Следующий год">›</button>
        </div>
        <div class="eo-toggle">
          <button :class="{ on: mode === 'tree' }" @click="mode = 'tree'">Дерево</button>
          <button :class="{ on: mode === 'table' }" @click="mode = 'table'">Таблица</button>
          <button :class="{ on: mode === 'roadmap' }" @click="mode = 'roadmap'">Дорожная карта</button>
        </div>
        <button class="eo-print" @click="doPrint">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="6 9 6 2 18 2 18 9"/><path d="M6 18H4a2 2 0 0 1-2-2v-5a2 2 0 0 1 2-2h16a2 2 0 0 1 2 2v5a2 2 0 0 1-2 2h-2"/><rect x="6" y="14" width="12" height="8"/></svg>
          Печать
        </button>
      </div>
    </div>

    <UzaStateBlock v-if="error" state="error" variant="banner" :text="error" dismissible @dismiss="error = null" />
    <UzaStateBlock v-if="loading" state="loading" text="Собираем обзор…" />

    <template v-else-if="data">
      <!-- summary -->
      <div class="eo-stats">
        <div class="eo-stat"><span class="eo-stat-n">{{ data.total }}</span><span class="eo-stat-l">проектов</span></div>
        <div class="eo-stat eo-stat-red" :class="{ dim: !data.overdue }"><span class="eo-stat-n">{{ data.overdue }}</span><span class="eo-stat-l">просрочено</span></div>
        <div class="eo-stat eo-stat-amber" :class="{ dim: !data.due_this_month }"><span class="eo-stat-n">{{ data.due_this_month }}</span><span class="eo-stat-l">срок в этом месяце</span></div>
        <div class="eo-stat"><span class="eo-stat-n">{{ data.sector_count }}</span><span class="eo-stat-l">секторов</span></div>
        <div class="eo-stat"><span class="eo-stat-n">{{ data.company_count }}</span><span class="eo-stat-l">компаний</span></div>
        <div v-if="mode === 'tree'" class="eo-expand">
          <button @click="expandAll">Развернуть всё</button>
          <button @click="collapseAll">Свернуть всё</button>
        </div>
      </div>

      <UzaStateBlock v-if="!data.sectors.length" state="empty" variant="block" title="Нет текущих проектов" text="За выбранный год не найдено открытых проектов. Смените год или проверьте портфель." />

      <!-- ── ДЕРЕВО ── -->
      <div v-else-if="mode === 'tree'" class="eo-tree">
        <div v-for="(s, si) in data.sectors" :key="secKey(s.id)" class="eo-sector" :style="{ animationDelay: Math.min(si*0.04, 0.4)+'s', '--sc': s.color || '#7C6FF7' }">
          <button class="eo-sec-head" @click="toggleSec(s.id)">
            <span class="eo-chev" :class="{ open: isOpen(s.id) }"></span>
            <span class="eo-sec-badge">{{ s.short_badge || s.name.slice(0, 3).toUpperCase() }}</span>
            <span class="eo-sec-name">{{ s.name }}</span>
            <span class="eo-sec-meta">{{ s.company_count }} комп · {{ s.total }} проектов</span>
            <span v-if="s.overdue" class="eo-ov-badge">{{ s.overdue }} просрочка</span>
          </button>
          <div v-show="isOpen(s.id)" class="eo-companies">
            <div v-for="c in s.companies" :key="c.id" class="eo-company">
              <div class="eo-co-head">
                <span class="eo-co-name">{{ c.name }}</span>
                <span class="eo-co-meta">{{ c.total }}</span>
                <span v-if="c.overdue" class="eo-ov-dot" :title="c.overdue + ' просрочено'">{{ c.overdue }}</span>
                <span v-if="c.revenue != null || c.profit != null" class="eo-fin" :title="'Финпоказатели' + (c.fin_year ? ' за ' + c.fin_year : '')">
                  <span v-if="c.revenue != null" class="eo-fin-i"><span class="eo-fin-l">Выручка</span><b>{{ fmtFin(c.revenue) }}</b></span>
                  <span v-if="c.profit != null" class="eo-fin-i"><span class="eo-fin-l">Прибыль</span><b :class="{ neg: (c.profit ?? 0) < 0 }">{{ fmtFin(c.profit) }}</b></span>
                  <span v-if="c.fin_year" class="eo-fin-y">FY{{ String(c.fin_year).slice(2) }}</span>
                </span>
              </div>
              <div class="eo-projects">
                <div v-for="p in c.projects" :key="p.id" class="eo-proj">
                  <span class="eo-due" :style="{ color: DL[p.deadline_state].c, background: DL[p.deadline_state].c + '15' }">
                    {{ fmtDue(p.due_date) }}
                  </span>
                  <div class="eo-proj-main">
                    <div class="eo-proj-title">{{ p.title }}</div>
                    <div class="eo-proj-meta">
                      <span v-if="p.direction" class="eo-dir">{{ p.direction }}</span>
                      <span class="eo-st" :data-s="p.status">{{ stLabel(p.status) }}</span>
                      <span class="eo-pct">{{ p.progress_percent }}%</span>
                    </div>
                    <div v-if="p.description" class="eo-proj-desc">{{ p.description }}</div>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- ── ТАБЛИЦА ── -->
      <div v-else-if="mode === 'table'" class="eo-tablewrap">
        <table class="eo-table">
          <thead>
            <tr><th>Сектор</th><th>Компания</th><th>Направление</th><th>Проект</th><th>Дедлайн</th><th>Статус</th></tr>
          </thead>
          <tbody>
            <tr v-for="(r, i) in flatRows" :key="r.p.id" :class="{ 'eo-tr-sec': r.firstOfSector }">
              <td class="eo-td-sec">
                <template v-if="r.firstOfSector"><span class="eo-tdot" :style="{ background: r.sectorColor || '#7C6FF7' }"></span>{{ r.sectorName }}</template>
              </td>
              <td class="eo-td-co">{{ r.firstOfCompany ? r.companyName : "" }}</td>
              <td class="eo-td-dir">{{ r.p.direction || "—" }}</td>
              <td>
                <div class="eo-td-title">{{ r.p.title }}</div>
                <div v-if="r.p.description" class="eo-td-desc">{{ r.p.description }}</div>
              </td>
              <td><span class="eo-due" :style="{ color: DL[r.p.deadline_state].c, background: DL[r.p.deadline_state].c + '15' }">{{ fmtDue(r.p.due_date) }}</span></td>
              <td><span class="eo-st" :data-s="r.p.status">{{ stLabel(r.p.status) }}</span></td>
            </tr>
          </tbody>
        </table>
      </div>
      <!-- ── ДОРОЖНАЯ КАРТА ── -->
      <div v-else class="eo-rm-wrap">
        <div class="eo-rm-legend">
          <span class="eo-rm-leg-t">Поток по фазам реализации</span>
          <span v-for="ph in PHASES" :key="ph.key" class="eo-rm-leg"><span class="eo-rm-leg-d" :style="{ background: ph.c }"></span>{{ ph.label }}</span>
        </div>
        <div class="eo-rm">
          <!-- шапка фаз -->
          <div class="eo-rm-grid eo-rm-head">
            <div class="eo-rm-corner">Направление</div>
            <template v-for="(ph, i) in PHASES" :key="ph.key">
              <div class="eo-rm-ph" :style="{ '--pc': ph.c }">{{ ph.label }}<span v-if="i < PHASES.length - 1" class="eo-rm-arr">›</span></div>
            </template>
          </div>
          <!-- лейны направлений -->
          <div v-for="(lane, li) in roadmapLanes" :key="lane.id" class="eo-rm-grid eo-rm-lane" :style="{ animationDelay: Math.min(li*0.05, 0.5)+'s' }">
            <div class="eo-rm-label"><span class="eo-rm-label-n">{{ lane.name }}</span><span class="eo-rm-label-c">{{ lane.projects.length }}</span></div>
            <div v-for="ph in PHASES" :key="ph.key" class="eo-rm-cell" :style="{ '--pc': ph.c }">
              <div v-for="x in lanePhase(lane, ph)" :key="x.p.id" class="eo-rm-card" :title="x.p.description || x.p.title">
                <div class="eo-rm-card-title">{{ x.p.title }}</div>
                <div class="eo-rm-card-meta">
                  <span class="eo-rm-card-co">{{ x.companyName }}</span>
                  <span class="eo-rm-card-due" :style="{ color: DL[x.p.deadline_state].c, background: DL[x.p.deadline_state].c + '15' }">{{ fmtDue(x.p.due_date) }}</span>
                </div>
              </div>
              <div v-if="!lanePhase(lane, ph).length" class="eo-rm-empty"></div>
            </div>
          </div>
        </div>
        <div v-if="!roadmapLanes.length" class="eo-rm-none">У текущих проектов не заполнено направление — назначьте проектам направления, чтобы построить дорожную карту.</div>
      </div>

    </template>

    <!-- print portal: чистая таблица для печати/PDF -->
    <Teleport to="body">
      <div v-if="data" class="eo-print-portal">
        <div class="eo-print-head">
          <h2>Сводный обзор портфеля · FY {{ year }}</h2>
          <div class="eo-print-sub">{{ data.total }} проектов · {{ data.overdue }} просрочено · {{ data.company_count }} компаний · на {{ new Date(data.as_of).toLocaleDateString("ru-RU") }}</div>
        </div>
        <table class="eo-print-table">
          <thead><tr><th>Сектор</th><th>Компания</th><th>Направление</th><th>Проект</th><th>Дедлайн</th><th>Статус</th></tr></thead>
          <tbody>
            <tr v-for="r in flatRows" :key="'p_' + r.p.id" :class="{ 'eo-pr-sec': r.firstOfSector }">
              <td>{{ r.firstOfSector ? r.sectorName : "" }}</td>
              <td>{{ r.firstOfCompany ? r.companyName : "" }}</td>
              <td>{{ r.p.direction || "—" }}</td>
              <td><b>{{ r.p.title }}</b><template v-if="r.p.description"><br><span class="eo-pr-desc">{{ r.p.description }}</span></template></td>
              <td>{{ fmtDue(r.p.due_date) }}<template v-if="r.p.deadline_state === 'overdue'"> ⚠</template></td>
              <td>{{ stLabel(r.p.status) }}</td>
            </tr>
          </tbody>
        </table>
      </div>
    </Teleport>
  </div>
</template>

<style scoped>
.eo-root { padding: 18px 22px 40px; max-width: 1280px; margin: 0 auto; }

.eo-head { display: flex; align-items: flex-start; justify-content: space-between; gap: 16px; flex-wrap: wrap; margin-bottom: 16px; }
.eo-title { font-size: 22px; font-weight: 500; color: var(--t1, #1e2a4a); margin: 0; letter-spacing: -.01em; }
.eo-sub { font-size: 12px; color: var(--t3, #94a3b8); margin-top: 4px; }
.eo-head-r { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.eo-year { display: inline-flex; align-items: center; gap: 8px; height: 34px; padding: 0 6px; border: 1px solid var(--border, rgba(99,102,180,.16)); border-radius: 9px; background: var(--bg1, #fff); font-size: 12.5px; font-weight: 600; color: var(--t1, #1e2a4a); font-variant-numeric: tabular-nums; }
.eo-year button { border: none; background: transparent; cursor: pointer; font-size: 16px; color: var(--t3, #94a3b8); width: 22px; height: 26px; border-radius: 6px; }
.eo-year button:hover { background: rgba(124,111,247,.1); color: var(--p-deep, #534ab7); }
.eo-toggle { display: inline-flex; gap: 2px; background: var(--bg2, #fafafc); border-radius: 9px; padding: 2px; border: 1px solid var(--border, rgba(99,102,180,.12)); }
.eo-toggle button { padding: 6px 13px; border: none; background: transparent; border-radius: 7px; font-size: 12px; font-weight: 500; color: var(--t3, #94a3b8); cursor: pointer; font-family: inherit; transition: all .14s; }
.eo-toggle button.on { background: #fff; color: var(--p-deep, #534ab7); box-shadow: 0 1px 3px rgba(15,23,60,.1); }
.eo-print { display: inline-flex; align-items: center; gap: 7px; height: 34px; padding: 0 14px; border: none; border-radius: 9px; background: linear-gradient(135deg, #7f77dd, #6b62cc); color: #fff; font-size: 12px; font-weight: 500; cursor: pointer; font-family: inherit; box-shadow: 0 2px 8px rgba(127,119,221,.28); transition: transform .15s; }
.eo-print:hover { transform: translateY(-1px); }

.eo-stats { display: flex; align-items: center; gap: 9px; flex-wrap: wrap; margin-bottom: 18px; }
.eo-stat { display: flex; flex-direction: column; align-items: center; min-width: 92px; padding: 9px 14px; border: 1px solid var(--border, rgba(99,102,180,.12)); border-radius: 12px; background: var(--bg1, #fff); }
.eo-stat-n { font-size: 20px; font-weight: 400; color: var(--t1, #1e2a4a); font-variant-numeric: tabular-nums; }
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
.eo-sec-badge { display: inline-flex; align-items: center; justify-content: center; min-width: 34px; height: 22px; padding: 0 7px; border-radius: 7px; background: var(--sc); color: #fff; font-size: 9.5px; font-weight: 800; letter-spacing: .02em; flex-shrink: 0; }
.eo-sec-name { font-size: 14px; font-weight: 600; color: var(--t1, #1e2a4a); }
.eo-sec-meta { font-size: 11px; color: var(--t3, #94a3b8); font-variant-numeric: tabular-nums; }
.eo-ov-badge { margin-left: auto; font-size: 10px; font-weight: 700; color: #E24B4A; background: rgba(226,75,74,.1); padding: 2px 9px; border-radius: 8px; }
.eo-companies { padding: 4px 14px 14px; display: flex; flex-direction: column; gap: 12px; }
.eo-company { border-left: none; }
.eo-co-head { display: flex; align-items: center; gap: 8px; padding: 6px 2px; }
.eo-co-name { font-size: 12.5px; font-weight: 600; color: var(--t1, #1e2a4a); }
.eo-co-meta { font-size: 10px; color: var(--t3, #94a3b8); background: rgba(30,42,74,.06); border-radius: 8px; padding: 0 7px; font-weight: 600; }
.eo-ov-dot { font-size: 10px; font-weight: 700; color: #fff; background: #E24B4A; border-radius: 8px; padding: 0 7px; }
.eo-fin { margin-left: auto; display: inline-flex; align-items: center; gap: 13px; flex-wrap: wrap; }
.eo-fin-i { display: inline-flex; align-items: baseline; gap: 5px; }
.eo-fin-l { font-size: 9px; text-transform: uppercase; letter-spacing: .03em; color: var(--t3, #94a3b8); font-weight: 600; }
.eo-fin-i b { font-size: 12px; font-weight: 600; color: var(--t1, #1e2a4a); font-variant-numeric: tabular-nums; }
.eo-fin-i b.neg { color: #E24B4A; }
.eo-fin-y { font-size: 9px; font-weight: 700; color: var(--t3, #94a3b8); background: rgba(30,42,74,.06); border-radius: 6px; padding: 1px 6px; }
.eo-projects { display: grid; grid-template-columns: repeat(auto-fill, minmax(330px, 1fr)); gap: 7px; }
.eo-proj { display: flex; gap: 10px; padding: 9px 11px; border: 1px solid var(--border, rgba(99,102,180,.1)); border-radius: 10px; background: var(--bg2, #fafafc); transition: box-shadow .16s, transform .16s; }
.eo-proj:hover { box-shadow: 0 4px 12px rgba(15,23,60,.06); transform: translateY(-1px); background: #fff; }
.eo-due { flex-shrink: 0; align-self: flex-start; font-size: 10px; font-weight: 700; padding: 3px 8px; border-radius: 7px; font-variant-numeric: tabular-nums; white-space: nowrap; }
.eo-proj-main { min-width: 0; flex: 1; }
.eo-proj-title { font-size: 12.5px; font-weight: 500; color: var(--t1, #1e2a4a); line-height: 1.35; }
.eo-proj-meta { display: flex; flex-wrap: wrap; align-items: center; gap: 7px; margin-top: 4px; }
.eo-dir { font-size: 9.5px; font-weight: 600; color: var(--p-deep, #534ab7); background: rgba(127,119,221,.1); border-radius: 8px; padding: 1px 7px; }
.eo-st { font-size: 9.5px; font-weight: 600; color: var(--t2, #475569); }
.eo-st[data-s="done"] { color: #1D9E75; }
.eo-st[data-s="active"] { color: #7C6FF7; }
.eo-st[data-s="review"] { color: #D97706; }
.eo-pct { font-size: 9.5px; color: var(--t3, #94a3b8); font-variant-numeric: tabular-nums; margin-left: auto; }
.eo-proj-desc { font-size: 10.5px; color: var(--t3, #94a3b8); line-height: 1.45; margin-top: 5px; display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; }

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
  .eo-root { padding: 14px; }
  .eo-projects { grid-template-columns: 1fr; }
}
</style>

<!-- Глобальные стили печати: при печати показываем только портал -->
<style>
@media print {
  #app { display: none !important; }
  .eo-print-portal { display: block !important; padding: 0; font-family: -apple-system, "Segoe UI", Roboto, sans-serif; color: #111; }
  .eo-print-head h2 { font-size: 16px; margin: 0 0 4px; }
  .eo-print-sub { font-size: 10px; color: #555; margin-bottom: 10px; }
  .eo-print-table { border-collapse: collapse; width: 100%; font-size: 9.5px; }
  .eo-print-table th { text-align: left; border-bottom: 1.5px solid #333; padding: 4px 6px; font-size: 9px; text-transform: uppercase; }
  .eo-print-table td { padding: 4px 6px; border-bottom: 0.5px solid #ddd; vertical-align: top; }
  .eo-print-table tr.eo-pr-sec td { border-top: 1.2px solid #999; }
  .eo-pr-desc { color: #666; font-size: 8.5px; }
  @page { size: A4 landscape; margin: 12mm; }
}
</style>
