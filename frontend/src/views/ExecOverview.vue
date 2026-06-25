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
import minfinLogoUrl from "@/assets/minfin-logo.png";
import uzassetsLogoUrl from "@/assets/uzassets-logo-wide.png";
import { execOverviewApi, type ExecOverviewResponse, type ExecOverviewProject, type ExecOverviewCompany, type ExecOverviewTask, type DeadlineState } from "@/api/execOverview";
import { overviewMatrixApi, type MatrixConfig } from "@/api/overviewMatrix";
import MatrixEditor from "@/components/reporting/MatrixEditor.vue";
import { usePermissions } from "@/composables/usePermissions";

// Встраивание как подвкладка «Отчёт» в воркспейсе компании: фиксируем фильтр на
// одной компании и прячем портфельную «обвязку» (логотип/название, статистику, чипы).
const props = defineProps<{ embedCompanyId?: string }>();

const loading = ref(true);
const error = ref<string | null>(null);
const data = ref<ExecOverviewResponse | null>(null);
const year = ref<number>(new Date().getFullYear());
const printMode = ref<"list" | "columns">("list");
// Фильтр по компании (чипы): null = все компании. Влияет на дерево и печать.
const companyFilter = ref<string | null>(null);
const allCompanies = computed(() => {
  const out: { id: string; name: string }[] = [];
  for (const s of (data.value?.sectors || [])) for (const c of s.companies) out.push({ id: c.id, name: c.name });
  return out.sort((a, b) => a.name.localeCompare(b.name, "ru"));
});
const viewSectors = computed(() => {
  const secs = data.value?.sectors || [];
  if (!companyFilter.value) return secs;
  return secs
    .map(s => ({ ...s, companies: s.companies.filter(c => c.id === companyFilter.value) }))
    .filter(s => s.companies.length);
});

// ── Настройка матрицы (выбор/правка/свои пункты) по компании+году ──
const matrixPerm = usePermissions("tasks");
const matrixConfigs = ref<Record<string, MatrixConfig>>({});
const editingMatrix = ref<{ id: string; name: string } | null>(null);

// Standalone /executive-overview: страница превращена в «заполнить → распечатать
// отчёт». Кнопка «Заполнить отчёт» в шапке работает с выбранной в чипах компанией;
// печатается ТОЛЬКО заполненный вручную отчёт (manual_directions).
const selectedCompany = computed<{ id: string; name: string } | null>(() => {
  if (!companyFilter.value) return null;
  return allCompanies.value.find((c) => c.id === companyFilter.value) || null;
});
function hasManualReport(id: string): boolean {
  return !!(matrixConfigs.value[id]?.manual_directions?.length);
}
const filledCount = computed(() => allCompanies.value.filter((c) => hasManualReport(c.id)).length);

async function loadMatrixConfigs() {
  const cos = allCompanies.value;
  if (!cos.length) { matrixConfigs.value = {}; return; }
  const out: Record<string, MatrixConfig> = {};
  await Promise.all(cos.map(async (co) => {
    try {
      const r = await overviewMatrixApi.get(co.id, year.value);
      // храним только непустые конфиги (экономим реактивность).
      // ВКЛЮЧАЯ manual_directions — иначе ручной отчёт «то что заполняли
      // сотрудники» терялся при перезагрузке и печать откатывалась на авто-матрицу.
      if (r.config && (
        r.config.hidden.length ||
        Object.keys(r.config.overrides).length ||
        r.config.custom.length ||
        (r.config.manual_directions?.length || 0)
      )) {
        out[co.id] = r.config;
      }
    } catch { /* ignore — нет доступа/конфига */ }
  }));
  matrixConfigs.value = out;
}

function onMatrixSaved(companyId: string, config: MatrixConfig) {
  matrixConfigs.value = { ...matrixConfigs.value, [companyId]: config };
  editingMatrix.value = null;
}

async function load() {
  loading.value = true; error.value = null;
  try {
    data.value = await execOverviewApi.get(year.value);
    // первый раз раскрываем все секторы
    if (data.value) collapsed.value = new Set();
    // в embed-режиме закрепляем фильтр на компании воркспейса
    companyFilter.value = props.embedCompanyId || null;
    loadMatrixConfigs();
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

// БП за Q1: % выполнения (факт / план) и цветовой класс маркера
const bpPct = (fact: number | null, plan: number | null): number | null =>
  plan != null && plan !== 0 && fact != null ? Math.round((fact / plan) * 100) : null;
const pctCls = (p: number | null): string => (p == null ? "" : p >= 100 ? "good" : p >= 80 ? "warn" : "bad");
const hasBp = (c: ExecOverviewCompany): boolean =>
  c.q1_revenue_plan != null || c.q1_revenue_fact != null ||
  c.q1_profit_plan != null || c.q1_profit_fact != null;

// Рейтинги: цвет кредитного грейда / ESG-балла, метаданные outlook, имя агентства
const creditCls = (g: string | null): string => {
  if (!g) return "";
  const u = g.toUpperCase();
  if (u.startsWith("A") || u.startsWith("BBB")) return "good";
  if (u.startsWith("BB")) return "warn";
  return "bad";
};
const OL: Record<string, { l: string; c: string }> = {
  Positive: { l: "поз.", c: "#1D9E75" }, Negative: { l: "нег.", c: "#E24B4A" },
  Stable: { l: "стаб.", c: "#94A3B8" }, Developing: { l: "разв.", c: "#D97706" },
  RWN: { l: "RWN", c: "#E24B4A" }, RWP: { l: "RWP", c: "#1D9E75" },
};
const olMeta = (o: string | null): { l: string; c: string } | null =>
  o ? OL[o] || { l: o, c: "#94A3B8" } : null;
const agShort = (a: string): string =>
  ({ "Sustainable Fitch": "Sust.F" } as Record<string, string>)[a] || a;
const creditStr = (c: ExecOverviewCompany): string =>
  c.credit_ratings.map(r => {
    const ol = olMeta(r.outlook);
    return `${agShort(r.agency)} ${r.rating ?? ""}${ol ? " (" + ol.l + ")" : ""}`;
  }).join(" · ");
const esgStr = (c: ExecOverviewCompany): string =>
  c.esg_ratings.map(r => `${agShort(r.agency)} ${r.score ?? ""}`).join(" · ");

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

// разом раскрыть/свернуть задачи во ВСЕХ проектах текущего вида (учитывает фильтр
// компании). Догружает задачи батчами по 8, чтобы не положить бэкенд, затем
// раскрывает — попадают в печать.
const expandingAll = ref(false);
async function expandAllTasks() {
  if (expandingAll.value) return;
  expandingAll.value = true;
  try {
    const ids: string[] = [];
    for (const s of viewSectors.value) for (const c of s.companies) for (const p of c.projects) ids.push(p.id);
    const toLoad = ids.filter(id => !(id in tasksByProject.value));
    const CHUNK = 8;
    for (let i = 0; i < toLoad.length; i += CHUNK) {
      await Promise.all(toLoad.slice(i, i + CHUNK).map(async (id) => {
        try { tasksByProject.value[id] = await execOverviewApi.projectTasks(id); }
        catch { tasksByProject.value[id] = []; }
      }));
    }
    expanded.value = new Set(ids);
  } finally { expandingAll.value = false; }
}
function collapseAllTasks() { expanded.value = new Set(); }

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

// Квартальная матрица для печати: направления (строки) × Q1–Q4 (столбцы),
// проекты раскладываются по кварталу своего дедлайна (по календарным месяцам).
// Применяется ручной конфиг (выбор/правка/свои пункты) из matrixConfigs.
interface MatrixItem { id: string; title: string; due_date: string | null; deadline_state: string; isCustom?: boolean; }
// Гант-бар: проект может занимать диапазон кварталов qStart..qEnd (одиночный → qStart==qEnd).
interface MatrixBar { id: string; title: string; due_date: string | null; deadline_state: string; qStart: number; qEnd: number; }
interface QRow { id: string | null; name: string; bars: MatrixBar[]; noDate: MatrixItem[]; }
function projQuarter(due: string | null | undefined): number | null {
  if (!due) return null;
  const d = new Date(due);
  if (isNaN(d.getTime())) return null;
  return Math.floor(d.getMonth() / 3); // 0..3 → Q1..Q4
}
function companyQuarterMatrix(c: ExecOverviewCompany): QRow[] {
  const cfg = matrixConfigs.value[c.id];
  const hidden = new Set(cfg?.hidden || []);
  const overrides = cfg?.overrides || {};
  const rows: QRow[] = companyDirections(c).map((col) => {
    const bars: MatrixBar[] = [];
    const noDate: MatrixItem[] = [];
    for (const p of col.projects) {
      if (hidden.has(p.id)) continue;
      const o = overrides[p.id] || {};
      const due = o.due_date != null ? o.due_date : p.due_date;
      const title = o.title || p.title;
      const qs = (o.quarter != null && o.quarter !== undefined) ? o.quarter : projQuarter(due);
      if (qs == null) { noDate.push({ id: p.id, title, due_date: due, deadline_state: p.deadline_state }); continue; }
      const qeRaw = (o.quarter_end != null && o.quarter_end !== undefined) ? o.quarter_end : qs;
      bars.push({ id: p.id, title, due_date: due, deadline_state: p.deadline_state, qStart: qs, qEnd: Math.max(qs, qeRaw) });
    }
    return { id: col.id, name: col.name, bars, noDate };
  });
  // свои пункты (custom): кладём в существующую строку направления или создаём новую
  for (const cust of (cfg?.custom || [])) {
    let row = rows.find(r =>
      (cust.direction_id && r.id === cust.direction_id) ||
      (!cust.direction_id && r.name === (cust.direction_name || "")));
    if (!row) {
      row = { id: cust.direction_id || null, name: cust.direction_name || "Прочее", bars: [], noDate: [] };
      rows.push(row);
    }
    const due = cust.due_date || null;
    const qs = (cust.quarter != null && cust.quarter !== undefined) ? cust.quarter : projQuarter(due);
    if (qs == null) { row.noDate.push({ id: cust.id, title: cust.title, due_date: due, deadline_state: "none", isCustom: true }); continue; }
    const qeRaw = (cust.quarter_end != null && cust.quarter_end !== undefined) ? cust.quarter_end : qs;
    row.bars.push({ id: cust.id, title: cust.title, due_date: due, deadline_state: "none", qStart: qs, qEnd: Math.max(qs, qeRaw) });
  }
  for (const r of rows) r.bars.sort((a, b) => a.qStart - b.qStart || a.qEnd - b.qEnd);
  return rows.filter((r) => r.bars.length > 0 || r.noDate.length > 0);
}

function openMatrixEditor(c: { id: string; name: string }) {
  editingMatrix.value = { id: c.id, name: c.name };
}
function projectsForCompany(id: string): ExecOverviewProject[] {
  for (const s of (data.value?.sectors || [])) for (const c of s.companies) if (c.id === id) return c.projects;
  return [];
}

// ── Ручной отчёт (новый режим): рендерим из config.manual_directions ──────────
// Строки = направления (вписаны вручную), бары = проекты (квартал..quarter_end),
// детали проектов нумеруются и собираются в выноску внизу отчёта.
interface ManualBar { id: string; title: string; due_date: string | null; qStart: number; qEnd: number; note: number | null; details: string; }
interface ManualRow { id: string; name: string; bars: ManualBar[]; }
interface ManualNote { num: number; title: string; details: string; }
function isManual(c: ExecOverviewCompany): boolean {
  const cfg = matrixConfigs.value[c.id];
  return !!(cfg?.manual_directions && cfg.manual_directions.length);
}
function buildManualReport(c: ExecOverviewCompany): { rows: ManualRow[]; notes: ManualNote[] } {
  const cfg = matrixConfigs.value[c.id];
  const md = cfg?.manual_directions || [];
  const notes: ManualNote[] = [];
  const rows: ManualRow[] = md.map((d) => {
    const bars: ManualBar[] = [];
    for (const p of (d.projects || [])) {
      const title = (p.title || "").trim();
      const details = (p.details || "").trim();
      if (!title && !details) continue;
      const due = p.due_date || null;
      const qsRaw = (p.quarter != null && p.quarter !== undefined) ? p.quarter : projQuarter(due);
      const qs = qsRaw == null ? 0 : qsRaw;   // ручной режим: без квартала/срока → Q1
      const qe = (p.quarter_end != null && p.quarter_end !== undefined) ? Math.max(qs, p.quarter_end) : qs;
      // Номер проставим ниже, ПОСЛЕ сортировки — чтобы индексы шли в порядке отображения.
      bars.push({ id: p.id, title: title || "—", due_date: due, qStart: qs, qEnd: qe, note: null, details });
    }
    bars.sort((a, b) => a.qStart - b.qStart || a.qEnd - b.qEnd);
    return { id: d.id, name: (d.name || "").trim() || "—", bars };
  }).filter((r) => r.bars.length > 0);

  // Сквозная нумерация СТРОГО в порядке отображения: строки сверху-вниз, внутри строки
  // бары слева-направо (уже отсортированы). КАЖДЫЙ проект получает верхний индекс и строку
  // в выноске → в матрице и в «Подробностях» единый ряд 1..N без пропусков и перестановок.
  let noteSeq = 0;
  for (const r of rows) {
    for (const b of r.bars) {
      b.note = ++noteSeq;
      notes.push({
        num: b.note,
        title: b.title === "—" ? "(без названия)" : b.title,
        details: b.details || "",
      });
    }
  }
  return { rows, notes };
}
const manualReports = computed<Record<string, { rows: ManualRow[]; notes: ManualNote[] }>>(() => {
  const out: Record<string, { rows: ManualRow[]; notes: ManualNote[] }> = {};
  for (const s of (data.value?.sectors || [])) for (const c of s.companies) {
    if (isManual(c)) out[c.id] = buildManualReport(c);
  }
  return out;
});

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
  <div class="eo-root" :class="{ embed: embedCompanyId }">
    <!-- ── ТОПБАР ── -->
    <div class="eo-topbar" :class="{ embed: embedCompanyId }">
      <div v-if="!embedCompanyId" class="eo-tb-l">
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
        <div v-if="embedCompanyId" class="eo-pmode" title="Вид печати">
          <button :class="{ on: printMode === 'list' }" @click="printMode = 'list'" title="Матрица: направления × кварталы">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="3" width="18" height="18" rx="1.5"/><path d="M3 9h18M9 9v12M15 9v12"/></svg>
          </button>
          <button :class="{ on: printMode === 'columns' }" @click="printMode = 'columns'" title="Направления колонками">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="3" width="6" height="18" rx="1"/><rect x="10" y="3" width="6" height="18" rx="1"/><rect x="17" y="3" width="4" height="18" rx="1"/></svg>
          </button>
        </div>
        <button
          v-if="!embedCompanyId && matrixPerm.canEdit.value"
          class="eo-fill"
          :disabled="!selectedCompany"
          :title="selectedCompany ? ('Заполнить отчёт: ' + selectedCompany.name) : 'Сначала выберите компанию в списке ниже'"
          @click="selectedCompany && openMatrixEditor(selectedCompany)"
        >
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="3" width="18" height="18" rx="1.5"/><path d="M3 9h18M9 9v12"/></svg>
          Заполнить отчёт
          <span v-if="selectedCompany && hasManualReport(selectedCompany.id)" class="eo-fill-dot" title="Отчёт заполнен"></span>
        </button>
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
        <template v-if="!embedCompanyId">
        <div class="eo-stat" style="--si:0"><span class="eo-stat-n">{{ stat.total }}</span><span class="eo-stat-l">проектов</span></div>
        <div class="eo-stat eo-stat-red" style="--si:1" :class="{ dim: !data.overdue }"><span class="eo-stat-n">{{ stat.overdue }}</span><span class="eo-stat-l">просрочено</span></div>
        <div class="eo-stat eo-stat-amber" style="--si:2" :class="{ dim: !data.due_this_month }"><span class="eo-stat-n">{{ stat.month }}</span><span class="eo-stat-l">срок в этом месяце</span></div>
        <div class="eo-stat" style="--si:3"><span class="eo-stat-n">{{ stat.sectors }}</span><span class="eo-stat-l">секторов</span></div>
        <div class="eo-stat" style="--si:4"><span class="eo-stat-n">{{ stat.companies }}</span><span class="eo-stat-l">компаний</span></div>
        </template>
        <div v-if="embedCompanyId" class="eo-expand">
          <button @click="expandAll">Развернуть всё</button>
          <button @click="collapseAll">Свернуть всё</button>
          <button class="eo-exp-tasks" :disabled="expandingAll" @click="expanded.size ? collapseAllTasks() : expandAllTasks()">
            {{ expandingAll ? 'Загрузка задач…' : (expanded.size ? 'Свернуть задачи' : 'Развернуть задачи') }}
          </button>
        </div>
      </div>

      <!-- чипы компаний: фильтр дерева + выбор компании для печати по одной -->
      <div v-if="allCompanies.length && !embedCompanyId" class="eo-chips">
        <button class="eo-chip" :class="{ on: companyFilter === null }" @click="companyFilter = null">Все компании</button>
        <button v-for="co in allCompanies" :key="co.id" class="eo-chip" :class="{ on: companyFilter === co.id }" @click="companyFilter = co.id">{{ co.name }}</button>
      </div>

      <UzaStateBlock v-if="!data.sectors.length" state="empty" variant="block" title="Нет текущих проектов" text="За выбранный год не найдено открытых проектов. Смените год или проверьте портфель." />

      <!-- ── ДЕРЕВО (только embed / воркспейс компании; в standalone убрано) ── -->
      <div v-else-if="embedCompanyId" class="eo-tree">
        <div v-for="(s, si) in viewSectors" :key="secKey(s.id)" class="eo-sector" :style="{ animationDelay: Math.min(si*0.04, 0.4)+'s', '--sc': s.color || '#7C6FF7' }">
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
                <button v-if="matrixPerm.canEdit.value" class="eo-co-mtx" title="Заполнить «Сводный обзор» вручную: направления, проекты по кварталам и детали в выноску" @click="openMatrixEditor(c)">
                  <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="3" width="18" height="18" rx="1.5"/><path d="M3 9h18M9 9v12"/></svg>
                  Заполнить отчёт<span v-if="matrixConfigs[c.id]" class="eo-co-mtx-dot" title="Отчёт заполнен"></span>
                </button>
                <div class="eo-co-aside">
                  <span v-if="hasBp(c)" class="eo-bp" title="Ключевые результаты бизнес-плана за Q1 (факт / план)">
                    <span class="eo-bp-tag">БП Q1</span>
                    <span v-if="c.q1_revenue_fact != null || c.q1_revenue_plan != null" class="eo-bp-i">
                      <span class="eo-bp-l">Выручка</span> {{ fmtFin(c.q1_revenue_fact) }}<span class="eo-bp-sep">/</span>{{ fmtFin(c.q1_revenue_plan) }}
                      <span v-if="bpPct(c.q1_revenue_fact, c.q1_revenue_plan) != null" class="eo-bp-pct" :class="pctCls(bpPct(c.q1_revenue_fact, c.q1_revenue_plan))">{{ bpPct(c.q1_revenue_fact, c.q1_revenue_plan) }}%</span>
                    </span>
                    <span v-if="c.q1_profit_fact != null || c.q1_profit_plan != null" class="eo-bp-i">
                      <span class="eo-bp-l">Прибыль</span> <span :class="{ neg: (c.q1_profit_fact ?? 0) < 0 }">{{ fmtFin(c.q1_profit_fact) }}</span><span class="eo-bp-sep">/</span>{{ fmtFin(c.q1_profit_plan) }}
                      <span v-if="bpPct(c.q1_profit_fact, c.q1_profit_plan) != null" class="eo-bp-pct" :class="pctCls(bpPct(c.q1_profit_fact, c.q1_profit_plan))">{{ bpPct(c.q1_profit_fact, c.q1_profit_plan) }}%</span>
                    </span>
                  </span>
                  <span v-if="c.credit_ratings.length || c.esg_ratings.length" class="eo-rt">
                    <span v-for="r in c.credit_ratings" :key="'cr_' + r.agency" class="eo-rt-chip" :class="creditCls(r.rating)" :title="r.agency + ' — кредитный рейтинг'">
                      <span class="eo-rt-ag">{{ agShort(r.agency) }}</span>{{ r.rating }}<span v-if="olMeta(r.outlook)" class="eo-rt-ol" :style="{ color: olMeta(r.outlook).c }">{{ olMeta(r.outlook).l }}</span>
                    </span>
                    <span v-for="r in c.esg_ratings" :key="'esg_' + r.agency" class="eo-rt-chip esg" :title="r.agency + ' — ESG'">
                      <span class="eo-rt-ag">{{ agShort(r.agency) }}</span>{{ r.score }}
                    </span>
                  </span>
                </div>
              </div>
              <!-- проекты компании канбаном по направлениям -->
              <div class="eo-codirs">
                <div v-for="col in companyDirections(c)" :key="col.id || '__none__'" class="eo-codir">
                  <div class="eo-codir-head"><span class="eo-codir-name">{{ col.name }}</span><span class="eo-codir-n">{{ col.projects.length }}</span></div>
                  <div class="eo-codir-body">
                    <div v-for="p in col.projects" :key="p.id" class="eo-kb-card" :class="{ open: expanded.has(p.id) }" @click="toggleProject(p.id)">
                      <div class="eo-kb-card-title">{{ p.title }}</div>
                      <div class="eo-kb-card-meta">
                        <span class="eo-duetx" :style="{ color: DL[p.deadline_state].c }">{{ fmtDue(p.due_date) }}</span>
                      </div>
                      <div v-if="p.last_update" class="eo-kb-upd"><span class="eo-kb-upd-d">Ход{{ p.last_update_at ? ' · ' + fmtDue(p.last_update_at) : '' }}:</span> {{ p.last_update }}</div>
                      <div v-if="expanded.has(p.id)" class="eo-tasks" @click.stop>
                        <div v-if="tasksLoading.has(p.id)" class="eo-tasks-msg">Загрузка задач…</div>
                        <template v-else>
                          <div v-for="t in (tasksByProject[p.id] || [])" :key="t.id" class="eo-task">
                            <span class="eo-task-dot"></span>
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

      <!-- ── Standalone: панель «заполнить → распечатать отчёт» (заменяет дерево) ── -->
      <div v-else class="eo-report-panel">
        <UzaStateBlock
          v-if="selectedCompany"
          state="empty"
          variant="block"
          :title="selectedCompany.name"
          :desc="hasManualReport(selectedCompany.id)
            ? 'Отчёт заполнен. Нажмите «Печать», чтобы распечатать, или «Заполнить отчёт» для правки.'
            : 'Отчёт ещё не заполнен. Нажмите «Заполнить отчёт», чтобы внести направления и проекты по кварталам.'"
        />
        <UzaStateBlock
          v-else
          state="empty"
          variant="block"
          title="Выберите компанию"
          :desc="`Заполнено отчётов: ${filledCount} из ${allCompanies.length}. Выберите компанию в списке выше, заполните отчёт и распечатайте.`"
        />
      </div>

    </template>
    </div><!-- /eo-body -->

    <!-- print portal: одна КОМПАНИЯ на лист A4 (альбом), проекты по направлениям, задачи свёрнуты -->
    <Teleport to="body">
      <div v-if="data" class="eo-print-portal">
        <template v-for="s in viewSectors" :key="'pps_' + (s.id || 'none')">
          <section v-for="c in (embedCompanyId ? s.companies : s.companies.filter(cc => isManual(cc)))" :key="'ppc_' + c.id" class="eo-pp-page">
            <div class="eo-pp-head">
              <div class="eo-pp-toprow">
                <img :src="minfinLogoUrl" class="eo-pp-imv-img" alt="Иқтисодиёт ва молия вазирлиги" />
                <div class="eo-pp-brand">
                  <svg class="eo-pp-logo" viewBox="0 0 240 220" width="26" height="24" aria-hidden="true">
                    <path d="M 80 30 L 210 110 L 80 190 L 115 110 Z" fill="#534AB7" />
                    <g fill="#7F77DD"><rect x="56" y="50" width="8" height="8" /><rect x="42" y="64" width="7" height="7" /><rect x="50" y="96" width="7" height="7" /><rect x="36" y="116" width="7" height="7" /><rect x="48" y="150" width="7" height="7" /></g>
                  </svg>
                  <span class="eo-pp-brand-txt">Единая платформа<br />трансформации</span>
                </div>
                <img :src="uzassetsLogoUrl" class="eo-pp-uza-img" alt="UzAssets" />
              </div>
              <div class="eo-pp-titlerow">
                <h2>{{ c.name }}</h2>
                <span class="eo-pp-doc">{{ s.name }} · сводный обзор</span>
              </div>
            </div>
            <!-- режим «матрица»: направления (строки) × Q1–Q4 (столбцы). В standalone — всегда. -->
            <template v-if="!embedCompanyId || printMode === 'list'">
              <table class="eo-qm">
                <thead>
                  <tr>
                    <th class="eo-qm-h-dir">Направление</th>
                    <th class="eo-qm-h-q">Q1<span class="eo-qm-h-mon">янв–мар</span></th>
                    <th class="eo-qm-h-q">Q2<span class="eo-qm-h-mon">апр–июн</span></th>
                    <th class="eo-qm-h-q">Q3<span class="eo-qm-h-mon">июл–сен</span></th>
                    <th class="eo-qm-h-q">Q4<span class="eo-qm-h-mon">окт–дек</span></th>
                  </tr>
                </thead>
                <!-- Ручной отчёт: строки = направления, бары = вписанные проекты -->
                <tbody v-if="isManual(c)">
                  <tr v-for="row in (manualReports[c.id]?.rows || [])" :key="row.id" class="eo-qm-row">
                    <td class="eo-qm-dir"><div class="eo-qm-dir-name">{{ row.name }}</div></td>
                    <td colspan="4" class="eo-qm-lane">
                      <div class="eo-qm-track">
                        <div
                          v-for="(b, bi) in row.bars"
                          :key="b.id"
                          class="eo-qm-bar"
                          :class="{ 'eo-qm-bar-span': b.qEnd > b.qStart }"
                          :style="{ gridColumn: (b.qStart + 1) + ' / ' + (b.qEnd + 2), gridRow: bi + 1 }"
                        >
                          <span class="eo-qm-bar-due"><sup v-if="b.note" class="eo-qm-note">{{ b.note }}</sup><template v-if="b.due_date">{{ fmtDue(b.due_date) }}</template></span>
                          <span class="eo-qm-bar-t">{{ b.title }}</span>
                        </div>
                      </div>
                    </td>
                  </tr>
                </tbody>
                <!-- Авто-матрица: только embed/воркспейс. В standalone печатается ЛИШЬ ручной отчёт. -->
                <tbody v-else-if="embedCompanyId">
                  <tr v-for="row in companyQuarterMatrix(c)" :key="row.id || '__none__'" class="eo-qm-row">
                    <td class="eo-qm-dir">
                      <div class="eo-qm-dir-name">{{ row.name }}</div>
                      <div v-if="row.noDate.length" class="eo-qm-nodate">
                        <div v-for="p in row.noDate" :key="p.id" class="eo-qm-chip eo-qm-chip-nd">
                          <span class="eo-qm-chip-t">{{ p.title }}</span>
                        </div>
                      </div>
                    </td>
                    <td colspan="4" class="eo-qm-lane">
                      <div class="eo-qm-track">
                        <div
                          v-for="(b, bi) in row.bars"
                          :key="b.id"
                          class="eo-qm-bar"
                          :class="{ 'eo-qm-bar-od': b.deadline_state === 'overdue', 'eo-qm-bar-span': b.qEnd > b.qStart }"
                          :style="{ gridColumn: (b.qStart + 1) + ' / ' + (b.qEnd + 2), gridRow: bi + 1 }"
                        >
                          <span class="eo-qm-bar-due">{{ fmtDue(b.due_date) }}</span>
                          <span class="eo-qm-bar-t">{{ b.title }}</span>
                        </div>
                      </div>
                    </td>
                  </tr>
                </tbody>
              </table>
              <!-- Выноска: подробности по проектам (ручной отчёт) -->
              <div v-if="isManual(c) && (manualReports[c.id]?.notes || []).length" class="eo-qm-foot">
                <div class="eo-qm-foot-h">Подробности по проектам</div>
                <p v-for="(n, ni) in (manualReports[c.id]?.notes || [])" :key="ni" class="eo-qm-fn">
                  <sup class="eo-qm-fn-num">{{ n.num || (ni + 1) }}</sup><span class="eo-qm-fn-t"><b>{{ n.title }}</b><template v-if="n.details"> — {{ n.details }}</template></span>
                </p>
              </div>
            </template>

            <!-- режим «колонки»: направления столбцами, под ними проекты и развёрнутые задачи -->
            <div v-else class="eo-ppc-cols">
              <div v-for="col in companyDirections(c)" :key="col.id || '__none__'" class="eo-ppc-col">
                <div class="eo-ppc-col-head">{{ col.name }}</div>
                <div v-for="p in col.projects" :key="p.id" class="eo-ppc-card">
                  <div class="eo-ppc-title">{{ p.title }}</div>
                  <div class="eo-ppc-meta">
                    <span class="eo-ppc-due" :class="{ 'eo-pp-overdue': p.deadline_state === 'overdue' }">{{ fmtDue(p.due_date) }}</span>
                  </div>
                  <div v-if="p.last_update" class="eo-ppc-upd"><span class="eo-ppc-upd-tag">Ход{{ p.last_update_at ? ' · ' + fmtDue(p.last_update_at) : '' }}:</span> {{ p.last_update }}</div>
                  <div v-if="expanded.has(p.id) && (tasksByProject[p.id] || []).length" class="eo-ppc-tasks">
                    <div v-for="t in (tasksByProject[p.id] || [])" :key="'ct_' + t.id" class="eo-ppc-task"><span class="eo-ppc-task-t">— {{ t.title }}</span><span class="eo-ppc-task-m" :class="{ 'eo-pp-overdue': t.deadline_state === 'overdue' }"> · {{ fmtDue(t.due_date) }}</span></div>
                  </div>
                </div>
              </div>
            </div>
          </section>
        </template>
      </div>
    </Teleport>

    <MatrixEditor
      v-if="editingMatrix"
      :company-id="editingMatrix.id"
      :company-name="editingMatrix.name"
      :year="year"
      :projects="projectsForCompany(editingMatrix.id)"
      :directions="data?.directions || []"
      @close="editingMatrix = null"
      @saved="onMatrixSaved"
    />
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
/* embed: подвкладка «Отчёт» воркспейса — без sticky-стекла и страничных полей */
.eo-root.embed { padding: 0; background: none; min-height: 0; }
.eo-root.embed .eo-body { padding: 12px 0 0; max-width: none; }
.eo-topbar.embed { position: static; padding: 0 0 12px; background: transparent; -webkit-backdrop-filter: none; backdrop-filter: none; border-bottom: 1px solid var(--border, rgba(99,102,180,.12)); justify-content: flex-end; animation: none; }
.eo-year { display: inline-flex; align-items: center; gap: 8px; height: 34px; padding: 0 6px; border: 1px solid var(--border, rgba(99,102,180,.16)); border-radius: 9px; background: var(--bg1, #fff); font-size: 12.5px; font-weight: 600; color: var(--t1, #1e2a4a); font-variant-numeric: tabular-nums; }
.eo-year button { border: none; background: transparent; cursor: pointer; font-size: 16px; color: var(--t3, #94a3b8); width: 22px; height: 26px; border-radius: 6px; }
.eo-year button:hover { background: rgba(124,111,247,.1); color: var(--p-deep, #534ab7); }
.eo-toggle { display: inline-flex; gap: 2px; background: var(--bg2, #fafafc); border-radius: 9px; padding: 2px; border: 1px solid var(--border, rgba(99,102,180,.12)); }
.eo-toggle button { padding: 6px 13px; border: none; background: transparent; border-radius: 7px; font-size: 12px; font-weight: 500; color: var(--t3, #94a3b8); cursor: pointer; font-family: inherit; transition: all .14s; }
.eo-toggle button.on { background: #fff; color: var(--p-deep, #534ab7); box-shadow: 0 1px 3px rgba(15,23,60,.1); }
.eo-pmode { display: inline-flex; gap: 2px; background: var(--bg2, #fafafc); border-radius: 9px; padding: 2px; border: 1px solid var(--border, rgba(99,102,180,.12)); }
.eo-pmode button { display: inline-flex; align-items: center; justify-content: center; width: 30px; height: 28px; border: none; background: transparent; border-radius: 7px; color: var(--t3, #94a3b8); cursor: pointer; transition: all .14s; }
.eo-pmode button.on { background: #fff; color: var(--p-deep, #534ab7); box-shadow: 0 1px 3px rgba(15,23,60,.1); }
.eo-pmode button:hover:not(.on) { color: var(--t2, #475569); }
.eo-print { display: inline-flex; align-items: center; gap: 7px; height: 34px; padding: 0 14px; border: none; border-radius: 9px; background: linear-gradient(135deg, #7f77dd, #6b62cc); color: #fff; font-size: 12px; font-weight: 500; cursor: pointer; font-family: inherit; box-shadow: 0 2px 8px rgba(127,119,221,.28); transition: transform .15s; }
.eo-print:hover { transform: translateY(-1px); }

/* Кнопка «Заполнить отчёт» в шапке (standalone) — рядом с «Печать» */
.eo-fill {
  display: inline-flex; align-items: center; gap: 7px; height: 34px; padding: 0 13px;
  border: 1px solid rgba(127, 119, 221, .35); border-radius: 9px;
  background: rgba(127, 119, 221, .08); color: var(--p-deep, #534ab7);
  font-size: 12px; font-weight: 500; cursor: pointer; font-family: inherit; transition: all .15s;
}
.eo-fill:hover:not(:disabled) { background: #7f77dd; color: #fff; border-color: #7f77dd; }
.eo-fill:disabled { opacity: .5; cursor: not-allowed; }
.eo-fill-dot { width: 6px; height: 6px; border-radius: 50%; background: #1D9E75; display: inline-block; flex-shrink: 0; }

/* Standalone: панель «заполнить → распечатать» вместо дерева проектов */
.eo-report-panel {
  border: 1px solid var(--border, rgba(99,102,180,.12)); border-radius: 14px;
  background: var(--bg1, #fff); margin-top: 4px;
}

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
.eo-expand button:disabled { opacity: .6; cursor: default; }
.eo-exp-tasks { border-color: rgba(127,119,221,.45); color: var(--p-deep, #534ab7); font-weight: 600; }

/* чипы компаний */
.eo-chips { display: flex; gap: 7px; flex-wrap: wrap; margin: 2px 0 16px; }
.eo-chip { font-size: 11.5px; font-weight: 500; padding: 5px 13px; border: 1px solid var(--border, rgba(99,102,180,.18)); border-radius: 999px; background: var(--bg1, #fff); color: var(--t2, #475569); cursor: pointer; font-family: inherit; white-space: nowrap; transition: all .14s var(--ease-out, cubic-bezier(.16,1,.3,1)); }
.eo-chip:hover { border-color: var(--p, #7f77dd); color: var(--p-deep, #534ab7); transform: translateY(-1px); }
.eo-chip.on { background: linear-gradient(135deg, #7f77dd, #6b62cc); color: #fff; border-color: transparent; box-shadow: 0 3px 10px rgba(127,119,221,.3); }

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
.eo-co-head { display: flex; align-items: center; gap: 8px 12px; padding: 6px 2px; flex-wrap: wrap; }
.eo-co-aside { margin-left: auto; display: inline-flex; align-items: center; gap: 10px 16px; flex-wrap: wrap; justify-content: flex-end; }
.eo-rt { display: inline-flex; align-items: center; gap: 6px; flex-wrap: wrap; }
.eo-rt-chip { display: inline-flex; align-items: baseline; gap: 3px; font-size: 11px; font-weight: 700; padding: 2px 8px; border-radius: 7px; font-variant-numeric: tabular-nums; background: var(--bg2, #f4f4f8); color: var(--t1, #1e2a4a); }
.eo-rt-chip.good { background: rgba(29,158,117,.12); color: #167a5b; }
.eo-rt-chip.warn { background: rgba(217,119,6,.13); color: #b45309; }
.eo-rt-chip.bad { background: rgba(226,75,74,.12); color: #c0392b; }
.eo-rt-chip.esg { background: rgba(127,119,221,.1); color: #534ab7; }
.eo-rt-ag { font-size: 8.5px; font-weight: 700; text-transform: uppercase; letter-spacing: .03em; opacity: .65; }
.eo-rt-ol { font-size: 9px; font-weight: 700; margin-left: 1px; }
.eo-co-name { font-size: 12.5px; font-weight: 600; color: var(--t1, #1e2a4a); }
.eo-co-meta { font-size: 10.5px; color: var(--t3, #94a3b8); font-variant-numeric: tabular-nums; }
.eo-co-ov { font-size: 10.5px; font-weight: 600; color: #E24B4A; }
.eo-co-ov::before { content: "· "; color: var(--t3, #cbd5e1); font-weight: 400; }
.eo-co-mtx {
  display: inline-flex; align-items: center; gap: 5px;
  padding: 3px 10px; border-radius: 7px; font-size: 11px; font-weight: 500;
  font-family: inherit; cursor: pointer;
  background: rgba(127, 119, 221, .08);
  border: 1px solid rgba(127, 119, 221, .22);
  color: var(--p-deep, #5B53B8); transition: all .15s;
}
.eo-co-mtx:hover { background: #7F77DD; color: #fff; border-color: #7F77DD; }
.eo-co-mtx-dot { width: 6px; height: 6px; border-radius: 50%; background: #1D9E75; display: inline-block; }
.eo-bp { display: inline-flex; align-items: center; gap: 13px; flex-wrap: wrap; }
.eo-bp-tag { font-size: 9px; font-weight: 700; text-transform: uppercase; letter-spacing: .04em; color: #fff; background: linear-gradient(135deg, #7f77dd, #6b62cc); border-radius: 6px; padding: 2px 7px; }
.eo-bp-i { font-size: 12px; font-weight: 600; color: var(--t1, #1e2a4a); font-variant-numeric: tabular-nums; }
.eo-bp-l { font-size: 9px; text-transform: uppercase; letter-spacing: .03em; color: var(--t3, #94a3b8); font-weight: 600; margin-right: 3px; }
.eo-bp-sep { color: var(--t3, #cbd5e1); font-weight: 400; margin: 0 1px; }
.eo-bp-i .neg { color: #E24B4A; }
.eo-bp-pct { font-size: 10px; font-weight: 700; margin-left: 4px; font-variant-numeric: tabular-nums; }
.eo-bp-pct.good { color: #1D9E75; }
.eo-bp-pct.warn { color: #D97706; }
.eo-bp-pct.bad { color: #E24B4A; }

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
.eo-task-dot { width: 5px; height: 5px; border-radius: 50%; flex-shrink: 0; margin-top: 6px; background: #cbd5e1; }
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
.eo-kb-card { background: var(--bg1, #fff); border: 1px solid var(--border, rgba(99,102,180,.12)); border-top: 2px solid var(--sc2, #e5e3f2); border-radius: 10px; padding: 9px 11px; cursor: pointer; box-shadow: 0 1px 2px rgba(15,23,60,.03); transition: box-shadow .15s, transform .15s; }
.eo-kb-card:hover { box-shadow: 0 5px 14px rgba(15,23,60,.1); transform: translateY(-1px); }
.eo-kb-card.open { box-shadow: 0 5px 16px rgba(15,23,60,.12); }
.eo-kb-card-title { font-size: 12px; font-weight: 500; color: var(--t1, #1e2a4a); line-height: 1.35; }
.eo-kb-card-meta { display: flex; align-items: center; justify-content: space-between; gap: 8px; margin-top: 6px; }
.eo-kb-card-co { font-size: 10px; color: var(--t3, #94a3b8); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.eo-kb-upd { font-size: 10.5px; color: var(--t2, #6b7088); line-height: 1.4; margin-top: 7px; display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; }
.eo-kb-upd-d { color: var(--p-deep, #534ab7); font-weight: 600; }

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
  /* поля = 0 → Chrome не печатает свои колонтитулы (URL/дата-время/заголовок);
     визуальные поля задаём внутренним паддингом страницы */
  @page { size: A4 landscape; margin: 0; }

  /* одна КОМПАНИЯ = одна страница */
  .eo-pp-page { padding: 11mm 13mm; break-after: page; page-break-after: always; }
  .eo-pp-page:last-child { break-after: auto; page-break-after: auto; }

  /* фирменная шапка: слева — платформа, справа — эмблема министерства (симметрично) */
  .eo-pp-head { border-bottom: 1.5pt solid #534AB7; padding-bottom: 9px; margin-bottom: 12px; }
  .eo-pp-toprow { display: flex; align-items: center; justify-content: space-between; gap: 16px; margin-bottom: 9px; }
  .eo-pp-brand { display: flex; align-items: center; gap: 9px; }
  .eo-pp-logo { display: block; flex-shrink: 0; }
  .eo-pp-brand-txt { font-size: 8.5pt; font-weight: 700; text-transform: uppercase; letter-spacing: .12em; color: #534AB7; line-height: 1.25; }
  .eo-pp-imv-img { height: 42px; width: auto; flex-shrink: 0; }
  .eo-pp-uza-img { height: 27px; width: auto; flex-shrink: 0; }
  .eo-pp-titlerow { display: flex; align-items: baseline; justify-content: space-between; gap: 12px; }
  .eo-pp-head h2 { font-size: 18pt; font-weight: 600; margin: 0; letter-spacing: -.01em; color: #161b33; }
  .eo-pp-doc { font-size: 8.5pt; color: #8A90A8; font-weight: 500; white-space: nowrap; }
  .eo-pp-sub { font-size: 8.5pt; color: #6b7088; margin-top: 4px; font-variant-numeric: tabular-nums; }
  .eo-pp-rt { font-size: 8pt; color: #4a4f6b; margin-top: 3px; font-variant-numeric: tabular-nums; }
  .eo-pp-rt-l { font-weight: 700; color: #6B62CC; }
  .eo-pp-rt-esg { margin-left: 12px; }

  /* направления секциями на всю ширину листа (одна колонка — без разрывов колонок) */
  /* проекты по направлениям (свёрнуто, без задач) */
  .eo-pp-dir { break-inside: avoid; margin-bottom: 8px; }
  .eo-pp-dir-head { font-size: 9pt; font-weight: 700; text-transform: uppercase; letter-spacing: .05em; color: #6B62CC; padding: 2px 0 3px; border-bottom: .5pt solid #d7d9e6; margin-bottom: 2px; }
  .eo-pp-table { border-collapse: collapse; width: 100%; font-size: 8.5pt; }
  .eo-pp-table td { padding: 2.5px 6px; border-bottom: .4pt solid #ececf3; vertical-align: top; }
  .eo-pp-due { white-space: nowrap; color: #534AB7; font-weight: 600; font-variant-numeric: tabular-nums; width: 64px; }
  .eo-pp-due.eo-pp-overdue { color: #E24B4A; font-weight: 700; }
  .eo-pp-title { color: #1a1f3c; }
  /* «ход проекта» — последний апдейт под проектом (перед задачами) */
  .eo-pp-upd-row td { border-bottom: none; padding-top: 0; padding-bottom: 2px; }
  .eo-pp-upd-d { font-size: 7.5pt; color: #8a90a8; font-style: italic; white-space: nowrap; vertical-align: top; }
  .eo-pp-upd { font-size: 8pt; color: #4a4f6b; line-height: 1.35; font-style: italic; }
  .eo-pp-upd-tag { font-style: normal; font-weight: 700; color: #6B62CC; }
  /* задачи раскрытого проекта в печати */
  .eo-pp-task-row td { border-bottom: .3pt solid #f1f1f7; padding-top: 1.5px; padding-bottom: 1.5px; }
  .eo-pp-task-title { color: #6b7088; font-size: 8pt; padding-left: 16px; }

  /* режим «матрица»: направления (строки) × Q1–Q4 (столбцы), проекты по кварталу дедлайна */
  .eo-qm { width: 100%; border-collapse: collapse; table-layout: fixed; font-size: 8pt; }
  .eo-qm thead th {
    font-weight: 700; color: #534AB7; background: rgba(127, 119, 221, .10);
    border: .5pt solid #d7d9e6; padding: 4px 6px; text-align: left; vertical-align: middle;
  }
  .eo-qm-h-dir { width: 25%; font-size: 8pt; text-transform: uppercase; letter-spacing: .04em; }
  .eo-qm-h-q { width: 18.75%; text-align: center !important; font-size: 9pt; }
  .eo-qm-h-mon { display: block; font-size: 6.5pt; font-weight: 500; color: #8a90a8; }
  .eo-qm-row { break-inside: avoid; }
  .eo-qm td { border: .5pt solid #e3e4ee; padding: 4px 5px; vertical-align: top; }
  .eo-qm-dir { background: #fafafd; }
  .eo-qm-dir-name { font-size: 8pt; font-weight: 700; text-transform: uppercase; letter-spacing: .03em; color: #6B62CC; line-height: 1.2; }
  .eo-qm-nodate { margin-top: 4px; }
  .eo-qm-chip {
    break-inside: avoid; background: rgba(127, 119, 221, .07);
    border-radius: 3px; padding: 2.5px 6px; margin-bottom: 3px; line-height: 1.25;
  }
  .eo-qm-chip:last-child { margin-bottom: 0; }
  .eo-qm-chip-due { display: block; font-size: 7pt; font-weight: 700; color: #534AB7; font-variant-numeric: tabular-nums; }
  .eo-qm-chip-t { display: block; font-size: 7.8pt; color: #161b33; }
  .eo-qm-chip-od { background: rgba(226, 75, 74, .08); }
  .eo-qm-chip-od .eo-qm-chip-due { color: #E24B4A; }
  .eo-qm-chip-nd { background: #f3f3f7; }
  .eo-qm-chip-nd .eo-qm-chip-t { color: #5a6072; }

  /* Гант-дорожка: один td (colspan=4) с CSS-grid 4 колонки; бар занимает диапазон кварталов */
  .eo-qm-lane { padding: 4px 4px !important; }
  .eo-qm-track { display: grid; grid-template-columns: repeat(4, 1fr); gap: 3px 4px; align-items: start; }
  .eo-qm-bar {
    break-inside: avoid; background: rgba(127, 119, 221, .07);
    /* верхний паддинг даёт место надстрочному индексу-сноске; overflow visible,
       чтобы цифра-индекс не срезалась сверху (была padding 2.5px + overflow hidden) */
    border-radius: 3px; padding: 5.5px 6px 2.5px; line-height: 1.25; overflow: visible;
  }
  .eo-qm-bar-due { display: block; font-size: 7pt; font-weight: 700; color: #534AB7; font-variant-numeric: tabular-nums; }
  .eo-qm-bar-t { display: block; font-size: 7.8pt; color: #161b33; }
  .eo-qm-bar-od { background: rgba(226, 75, 74, .08); }
  .eo-qm-bar-od .eo-qm-bar-due { color: #E24B4A; }
  /* растянутый на кварталы (Гант) — рамка + градиент-заливка, чтобы читалось как полоса */
  .eo-qm-bar-span {
    background: linear-gradient(90deg, rgba(127, 119, 221, .16), rgba(127, 119, 221, .07));
    border: .5pt solid rgba(127, 119, 221, .35);
  }
  .eo-qm-bar-span.eo-qm-bar-od {
    background: linear-gradient(90deg, rgba(226, 75, 74, .16), rgba(226, 75, 74, .07));
    border-color: rgba(226, 75, 74, .35);
  }
  /* сноска-маркер у проекта (ручной отчёт) — числовой верхний индекс */
  .eo-qm-note { font-size: 6pt; font-weight: 700; color: #534AB7; vertical-align: super; line-height: 0; margin-right: 2pt; }
  /* выноска внизу отчёта: подробности по проектам */
  .eo-qm-foot {
    margin-top: 5mm; padding-top: 3mm; border-top: .75pt solid #d6d3ee; break-inside: avoid;
  }
  .eo-qm-foot-h {
    font-size: 8pt; font-weight: 700; text-transform: uppercase; letter-spacing: .04em;
    color: #534AB7; margin-bottom: 2mm;
  }
  /* запись подробностей = абзац с числовым верхним индексом (как у проекта) */
  .eo-qm-fn { margin: 0 0 1.4mm; break-inside: avoid; font-size: 7.8pt; line-height: 1.35; color: #161b33; }
  .eo-qm-fn-num { font-size: 6pt; font-weight: 700; color: #534AB7; vertical-align: super; margin-right: 2.5pt; }
  .eo-qm-fn-t { color: #161b33; }
  .eo-qm-fn-t b { font-weight: 600; color: #2a2150; }

  /* режим «колонки» (вертикальный): направления — равные колонки-сетка,
     под ними проекты + развёрнутые задачи. Сетка = ровные ширины и выравнивание. */
  .eo-ppc-cols { display: grid; grid-template-columns: repeat(auto-fit, minmax(50mm, 1fr)); gap: 4mm 5mm; align-items: start; }
  .eo-ppc-col { break-inside: avoid; }
  .eo-ppc-col-head { font-size: 8pt; font-weight: 700; text-transform: uppercase; letter-spacing: .03em; color: #534AB7; background: rgba(127,119,221,.1); padding: 3px 7px; border-radius: 3px; margin-bottom: 6px; line-height: 1.2; min-height: 2.6em; display: flex; align-items: center; }
  .eo-ppc-card { break-inside: avoid; margin-bottom: 6px; padding-bottom: 5px; border-bottom: .4pt solid #e7e7f0; }
  .eo-ppc-card:last-child { border-bottom: none; margin-bottom: 0; padding-bottom: 0; }
  .eo-ppc-title { font-size: 8pt; color: #161b33; font-weight: 600; line-height: 1.3; }
  .eo-ppc-meta { font-size: 7.5pt; margin-top: 2px; }
  .eo-ppc-due { color: #534AB7; font-weight: 600; white-space: nowrap; font-variant-numeric: tabular-nums; }
  .eo-ppc-due.eo-pp-overdue { color: #E24B4A; font-weight: 700; }
  .eo-ppc-upd { font-size: 7pt; color: #4a4f6b; line-height: 1.35; font-style: italic; margin-top: 2px; }
  .eo-ppc-upd-tag { font-style: normal; font-weight: 700; color: #6B62CC; }
  .eo-ppc-tasks { margin-top: 3px; margin-left: 1px; padding-left: 6px; border-left: .6pt solid #d7d9e6; }
  .eo-ppc-task { font-size: 7pt; color: #5a6072; line-height: 1.4; margin-bottom: 1.5px; }
  .eo-ppc-task-m { color: #9a9fb0; white-space: nowrap; font-variant-numeric: tabular-nums; }
  .eo-ppc-task-m.eo-pp-overdue { color: #E24B4A; font-weight: 700; }
}
</style>
