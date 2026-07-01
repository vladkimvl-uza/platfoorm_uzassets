<script setup lang="ts">
/**
 * ProjectsStatusReport — «Отчёт по проектам, задачам и статусам».
 * Премиум-отчёт уровня министра/совета: официальная тройная шапка
 * (Минэкономфин · Единая платформа трансформации · UzAssets), сводка со
 * сегментными барами, статус-pill, «ход проекта». Печать в АЛЬБОМНОЙ
 * ориентации через teleport-оверлей; печатный лист — строго в фирменной
 * монохромной палитре (без «светофора»).
 *
 * Порядок и состав строк — 1:1 как в /workspace?tab=work (CompanyBoardList):
 *   проекты по (sort_order, num) → вложенные задачи по (sort_order, num) →
 *   задачи без проекта в конце. «Ход проекта» берётся из поля current_status
 *   (последний статус-апдейт), как колонка «Ход проекта» в work-табе.
 * Любую ячейку (срок/статус/комментарий) можно отредактировать вручную —
 * правки сохраняются оверрайдами в report_wizard config. Экспорт в Word (.doc).
 */
import { ref, computed, watch, onMounted, onUnmounted, nextTick } from "vue";
import { HEALTH_META, type StatusHealth } from "@/api/statusUpdates";
import { reportWizardApi } from "@/api/reportWizard";
import { useToast } from "@/composables/useToast";
import { useDirectionsStore } from "@/stores/directions";
import { api } from "@/api/client";
import { bpApi, kpiApi, num, BP_FIELDS, type KpiManager, type BpCell } from "@/api/bpKpi";
import UzaSkeleton from "@/components/UZA/UzaSkeleton.vue";
import ReportAppendix from "@/components/reporting/ReportAppendix.vue";
import EptLogo from "@/components/EptLogo.vue";
import minfinLogoUrl from "@/assets/minfin-logo.png";
import uzassetsLogoUrl from "@/assets/uzassets-logo-wide.png";

const props = defineProps<{
  companyId: string;
  companyName: string;
  companyCode: string;
  sectorName?: string | null;
  year: number;
  projects: any[];
  tasks: any[];
  credit?: any[];
  esg?: any[];
}>();

const toast = useToast();
const directionsStore = useDirectionsStore();

// ─── Статусы: палитра 1:1 c work-табом (экран) ───────────────────
const STATUS_META: Record<string, { label: string; color: string }> = {
  init:      { label: "Инициировано",   color: "#7F77DD" },
  new:       { label: "Не начато",       color: "#94A3B8" },
  active:    { label: "В процессе",      color: "#378ADD" },
  review:    { label: "На согласовании", color: "#EF9F27" },
  done:      { label: "Завершено",       color: "#1D9E75" },
  quarterly: { label: "Ежеквартально",   color: "#A855F7" },
  monthly:   { label: "Ежемесячно",      color: "#6366F1" },
  ongoing:   { label: "Постоянно",       color: "#06B6D4" },
  deferred:  { label: "Отложено",        color: "#94A3B8" },
};
const STATUS_OPTIONS = ["new", "init", "active", "review", "done", "quarterly", "monthly", "ongoing", "deferred"];
function statusLabel(s: string) { return STATUS_META[s]?.label || s || "—"; }
function statusColor(s: string) { return STATUS_META[s]?.color || "#94A3B8"; }

// ─── Печать: СТРОГО фирменная монохромная палитра (без «светофора») ──
//   done       → насыщенный бренд-индиго (плашка)
//   в процессе → бренд-фиолет (init/active/review)
//   повторяющ. → бренд-пурпур (quarterly/monthly/ongoing)
//   не начато  → нейтральный графит (new/deferred)
function printStatusStyle(s: string): { bg: string; color: string; weight: number } {
  if (s === "done") return { bg: "#1e2787", color: "#FFFFFF", weight: 700 };
  if (s === "new" || s === "deferred") return { bg: "#EFF0F5", color: "#7C8198", weight: 600 };
  if (s === "quarterly" || s === "monthly" || s === "ongoing")
    return { bg: "rgba(83,74,183,.10)", color: "#5B53B8", weight: 600 };
  return { bg: "rgba(67,56,202,.12)", color: "#4338CA", weight: 600 }; // init/active/review
}

const ROMAN = ["", "I", "II", "III", "IV"];
function quarterOf(due: string | null | undefined): string {
  if (!due) return "—";
  const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(String(due));
  if (!m) return String(due);
  return `${ROMAN[Math.ceil(Number(m[2]) / 3)] || ""} кв. ${m[1]}`;
}
function stampToday(): string {
  try { return new Date().toLocaleDateString("ru-RU", { day: "2-digit", month: "long", year: "numeric" }); }
  catch { return ""; }
}

// ─── Направления (label + цвет) из store — 1:1 с work-табом ──────
function dirLabel(code: string | null | undefined): string {
  return code ? directionsStore.labelFor(code) : "Без направления";
}
function dirColor(code: string | null | undefined): string {
  return code ? directionsStore.colorFor(code) : "#8A8FA3";
}

// ─── Оверрайды + сохранение в report_wizard config ──────────────
type Override = { srok?: string; status?: string; comment?: string };
const overrides = ref<Record<string, Override>>({});
const baseConfig = ref<Record<string, unknown>>({});
const CFG_KEY = "projects_status_report";
const loadingCfg = ref(false);
const saving = ref(false);
// Приложение-секции в конце листа (тумблеры + общий выбор периода + оверрайды).
const showMatrix = ref(false);
const showFin = ref(false);
const showKpi = ref(false);
const showBp = ref(false);
const showRatings = ref(false);
const apxYear = ref<number>(props.year);
const apxPeriod = ref<"year" | "q1" | "q2" | "q3" | "q4">("year");
const finOv = ref<Record<string, string>>({});
const kpiOv = ref<Record<string, string>>({});
const bpOv = ref<Record<string, string>>({});
const ratOv = ref<Record<string, string>>({});
let saveTimer: ReturnType<typeof setTimeout> | null = null;

async function loadConfig() {
  loadingCfg.value = true;
  try {
    const r = await reportWizardApi.get(props.companyCode, props.year);
    baseConfig.value = r.config || {};
    const block = (r.config as any)?.[CFG_KEY] || {};
    overrides.value = (block.overrides && typeof block.overrides === "object") ? block.overrides : {};
    excluded.value = (block.excluded && typeof block.excluded === "object") ? block.excluded : {};
    showMatrix.value = !!block.showMatrix;
    showFin.value = !!block.showFin;
    showKpi.value = !!block.showKpi;
    showBp.value = !!block.showBp;
    showRatings.value = !!block.showRatings;
    if (Number.isFinite(block.apxYear)) apxYear.value = block.apxYear;
    if (["year", "q1", "q2", "q3", "q4"].includes(block.apxPeriod)) apxPeriod.value = block.apxPeriod;
    finOv.value = (block.finOv && typeof block.finOv === "object") ? block.finOv : {};
    kpiOv.value = (block.kpiOv && typeof block.kpiOv === "object") ? block.kpiOv : {};
    bpOv.value = (block.bpOv && typeof block.bpOv === "object") ? block.bpOv : {};
    ratOv.value = (block.ratOv && typeof block.ratOv === "object") ? block.ratOv : {};
    if (showFin.value) loadFin();
    if (showKpi.value) loadKpi();
    if (showBp.value) loadBp();
  } catch { overrides.value = {}; } finally { loadingCfg.value = false; }
}
function scheduleSave() { if (saveTimer) clearTimeout(saveTimer); saveTimer = setTimeout(doSave, 800); }
async function doSave() {
  saving.value = true;
  try {
    const cfg = { ...baseConfig.value, [CFG_KEY]: {
      overrides: overrides.value, excluded: excluded.value, showMatrix: showMatrix.value,
      showFin: showFin.value, showKpi: showKpi.value, showBp: showBp.value, showRatings: showRatings.value,
      apxYear: apxYear.value, apxPeriod: apxPeriod.value,
      finOv: finOv.value, kpiOv: kpiOv.value, bpOv: bpOv.value, ratOv: ratOv.value,
    } };
    const r = await reportWizardApi.save(props.companyCode, props.year, cfg);
    baseConfig.value = r.config || cfg;
  } catch (e: any) {
    toast.error("Не удалось сохранить: " + (e?.response?.data?.detail || e?.message || ""));
  } finally { saving.value = false; }
}
function setOverride(id: string, field: keyof Override, value: string) {
  overrides.value = { ...overrides.value, [id]: { ...(overrides.value[id] || {}), [field]: value } };
  scheduleSave();
}
function resetOverrides() {
  overrides.value = {}; scheduleSave();
  toast.info("Ручные правки сброшены — данные снова из системы");
}

// ─── Строки: порядок 1:1 c work-табом (CompanyBoardList.groups) ──
interface Row {
  id: string; kind: "project" | "task"; num: string; title: string;
  dirCode: string | null; srok: string; status: string;
  comment: string; health: StatusHealth | null;
  due: string | null;  // сырой due_date — для детекта просроченных
}
function _ord(x: any): number { return Number(x?.sort_order) || 0; }
function _bySortThenNum(a: any, b: any): number {
  const d = _ord(a) - _ord(b);
  if (d !== 0) return d;
  return String(a?.num || "").localeCompare(String(b?.num || ""), "en", { numeric: true });
}
const normNum = (n: any) => String(n || "").replace(/\.+$/, "").trim();

const rows = computed<Row[]>(() => {
  const projs = [...props.projects].filter(p => !p.is_archived).sort(_bySortThenNum);
  const allTasks = [...props.tasks].filter(t => !t.is_archived);
  const claimed = new Set<string>();
  const out: Row[] = [];
  let pNo = 0;
  for (const p of projs) {
    pNo++;
    const pId = String(p.id || "");
    const pNum = normNum(p.num);
    const nested = allTasks.filter(t => {
      const tPid = String(t.project_id || "");
      if (tPid && pId && tPid === pId) return true;
      const tNum = normNum(t.num);
      if (!pNum || !tNum) return false;
      return tNum.startsWith(pNum + ".");
    }).sort(_bySortThenNum);
    nested.forEach(t => claimed.add(String(t.id)));
    out.push({ id: p.id, kind: "project", num: String(pNo), title: p.title || "—",
      dirCode: p.direction || null, srok: quarterOf(p.due_date), status: p.status || "new",
      comment: p.current_status || "", health: (p.current_health as StatusHealth) || null, due: p.due_date || null });
    nested.forEach((t, i) => out.push({ id: t.id, kind: "task", num: `${pNo}.${i + 1}`, title: t.title || "—",
      dirCode: t.direction || null, srok: quarterOf(t.due_date), status: t.status || "new",
      comment: t.current_status || "", health: (t.current_health as StatusHealth) || null, due: t.due_date || null }));
  }
  const orphans = allTasks.filter(t => !claimed.has(String(t.id))).sort(_bySortThenNum);
  orphans.forEach(t => {
    pNo++;
    out.push({ id: t.id, kind: "task", num: String(pNo), title: t.title || "—",
      dirCode: t.direction || null, srok: quarterOf(t.due_date), status: t.status || "new",
      comment: t.current_status || "", health: (t.current_health as StatusHealth) || null, due: t.due_date || null });
  });
  return out;
});

function effSrok(r: Row) { return overrides.value[r.id]?.srok ?? r.srok; }
function effStatus(r: Row) { return overrides.value[r.id]?.status ?? r.status; }
function effComment(r: Row) { return overrides.value[r.id]?.comment ?? r.comment; }
function isEdited(r: Row) {
  const o = overrides.value[r.id];
  return !!(o && (o.srok !== undefined || o.status !== undefined || o.comment !== undefined));
}

// ─── Выбор строк для печати (чекбоксы) ──────────────────────────
// excluded[id] = true → строка НЕ попадает в печать/экспорт/сводку/матрицу,
// но остаётся видимой (снятая галочка) в редактируемой таблице на экране.
const excluded = ref<Record<string, boolean>>({});
function isIncluded(id: string) { return !excluded.value[id]; }
function toggleRow(id: string) {
  const e = { ...excluded.value };
  if (e[id]) delete e[id]; else e[id] = true;
  excluded.value = e; scheduleSave();
}
const allIncluded = computed(() => rows.value.length > 0 && rows.value.every(r => !excluded.value[r.id]));
function toggleAll() {
  if (allIncluded.value) { const e: Record<string, boolean> = {}; for (const r of rows.value) e[r.id] = true; excluded.value = e; }
  else excluded.value = {};
  scheduleSave();
}
const printableRows = computed(() => rows.value.filter(r => !excluded.value[r.id]));

// ─── Фильтр по статусу (чипы) + просроченные ────────────────────
const statusFilter = ref<string | null>(null);
function isOverdue(r: Row): boolean {
  if (!r.due || effStatus(r) === "done") return false;
  const t = new Date(r.due).getTime();
  return !isNaN(t) && t < Date.now();
}
const displayRows = computed<Row[]>(() => {
  const f = statusFilter.value;
  if (!f) return rows.value;
  if (f === "overdue") return rows.value.filter(isOverdue);
  return rows.value.filter(r => effStatus(r) === f);
});
const filterChips = computed(() => {
  const counts: Record<string, number> = {};
  let overdue = 0;
  for (const r of rows.value) {
    counts[effStatus(r)] = (counts[effStatus(r)] || 0) + 1;
    if (isOverdue(r)) overdue++;
  }
  const chips = STATUS_OPTIONS
    .filter((s) => counts[s])
    .map((s) => ({ key: s, label: statusLabel(s), color: statusColor(s), count: counts[s] }));
  return { chips, overdue, total: rows.value.length };
});

// ─── Сводка ──────────────────────────────────────────────────────
function bucket(s: string): "done" | "notstarted" | "inprogress" {
  if (s === "done") return "done";
  if (s === "new" || s === "deferred") return "notstarted";
  return "inprogress";
}
function tally(list: Row[]) {
  const t = { total: list.length, done: 0, inprogress: 0, notstarted: 0 };
  for (const r of list) t[bucket(effStatus(r))]++;
  return t;
}
const summary = computed(() => ({
  projects: tally(printableRows.value.filter(r => r.kind === "project")),
  tasks: tally(printableRows.value.filter(r => r.kind === "task")),
}));
function pct(n: number, total: number) { return total > 0 ? Math.round(n / total * 100) : 0; }
function autoGrow(e: Event) {
  const el = e.target as HTMLTextAreaElement;
  el.style.height = "auto"; el.style.height = el.scrollHeight + "px";
}

// ─── Статус-матрица (направления × статусы) ──────────────────────
//   Тепловая сетка в фирменной монохромной палитре (без «светофора»):
//   интенсивность ячейки = доля от макс. значения; «Завершено» — глубокий
//   индиго, остальные статусы — бренд-фиолет.
const MATRIX_COLS: { key: string; label: string; statuses: string[] }[] = [
  { key: "notstarted", label: "Не начато",      statuses: ["new", "deferred"] },
  { key: "init",       label: "Инициировано",   statuses: ["init"] },
  { key: "active",     label: "В процессе",      statuses: ["active"] },
  { key: "review",     label: "Согласование",    statuses: ["review"] },
  { key: "done",       label: "Завершено",       statuses: ["done"] },
  { key: "recurring",  label: "Регулярные",      statuses: ["quarterly", "monthly", "ongoing"] },
];
const STATUS_TO_COL: Record<string, string> = (() => {
  const m: Record<string, string> = {};
  for (const c of MATRIX_COLS) for (const s of c.statuses) m[s] = c.key;
  return m;
})();
interface MxRow { code: string; label: string; color: string; counts: Record<string, number>; total: number; }
const matrix = computed(() => {
  const byDir = new Map<string, MxRow>();
  const colTotals: Record<string, number> = {};
  let grand = 0, maxCell = 0;
  for (const r of printableRows.value) {
    const code = r.dirCode || "__none__";
    let e = byDir.get(code);
    if (!e) { e = { code, label: dirLabel(r.dirCode), color: dirColor(r.dirCode), counts: {}, total: 0 }; byDir.set(code, e); }
    const col = STATUS_TO_COL[effStatus(r)] || "notstarted";
    e.counts[col] = (e.counts[col] || 0) + 1; e.total++;
    if (e.counts[col] > maxCell) maxCell = e.counts[col];
    colTotals[col] = (colTotals[col] || 0) + 1; grand++;
  }
  const dirRows = [...byDir.values()].sort((a, b) => b.total - a.total || a.label.localeCompare(b.label, "ru"));
  return { dirRows, colTotals, grand, maxCell };
});
function mxCellStyle(colKey: string, n: number): Record<string, string> {
  if (!n) return {};
  const a = 0.10 + 0.42 * (n / (matrix.value.maxCell || 1));
  const rgb = colKey === "done" ? "30,39,135" : "83,74,183";
  return { background: `rgba(${rgb},${a.toFixed(3)})`, color: a > 0.42 ? "#FFFFFF" : "#23264A", fontWeight: "600" };
}
function matrixDocHtml(): string {
  const m = matrix.value;
  const hcell = (x: string, al = "center") => `<th style="border:1px solid #2a375a;background:#1e2a4a;color:#fff;font:700 9.5px Arial;padding:5px;text-align:${al}">${x}</th>`;
  const headCols = MATRIX_COLS.map(c => hcell(c.label)).join("");
  const body = m.dirRows.map(d => {
    const cells = MATRIX_COLS.map(c => {
      const n = d.counts[c.key] || 0;
      const st = mxCellStyle(c.key, n);
      const bg = (st.background as string) || "#fff";
      const col = n ? (st.color as string) : "#B9BCC9";
      const w = n ? (st.fontWeight as string) : "400";
      return `<td style="border:1px solid #d7d9e0;text-align:center;font:${w} 10px Arial;padding:4px;background:${bg};color:${col}">${n || "·"}</td>`;
    }).join("");
    return `<tr><td style="border:1px solid #d7d9e0;font:600 10px Arial;padding:4px">${esc(d.label)}</td>${cells}<td style="border:1px solid #d7d9e0;text-align:center;font:700 10px Arial;padding:4px;background:#f3f2fb">${d.total}</td></tr>`;
  }).join("");
  const foot = MATRIX_COLS.map(c => `<td style="border:1px solid #d7d9e0;text-align:center;font:800 10px Arial;padding:4px;background:#eceaf6">${m.colTotals[c.key] || 0}</td>`).join("");
  const cw = (60 / MATRIX_COLS.length).toFixed(1);
  const cols = `<colgroup><col style="width:28%"/>${MATRIX_COLS.map(() => `<col style="width:${cw}%"/>`).join("")}<col style="width:8%"/></colgroup>`;
  return `<div style="margin-top:18px">
    <div style="font:800 12px Arial;color:#14171F;margin-bottom:6px">СТАТУС-МАТРИЦА <span style="font:400 10px Arial;color:#8A8C99">· направления × статусы</span></div>
    <table style="border-collapse:collapse;width:100%;table-layout:fixed">${cols}
      <thead><tr>${hcell("Направление", "left")}${headCols}${hcell("Всего")}</tr></thead>
      <tbody>${body}</tbody>
      <tfoot><tr><td style="border:1px solid #d7d9e0;font:800 10px Arial;padding:4px;background:#eceaf6">Итого</td>${foot}<td style="border:1px solid #d7d9e0;text-align:center;font:800 10px Arial;padding:4px;background:#e3e0f4">${m.grand}</td></tr></tfoot>
    </table></div>`;
}

// ═══════════════════════════════════════════════════════════════
// Приложение-секции: Фин. показатели / Исполнение KPI / Бизнес-план
// ═══════════════════════════════════════════════════════════════
function numOrNull(s: string): number | null {
  const n = Number(String(s).replace(/\s/g, "").replace(",", "."));
  return Number.isFinite(n) ? n : null;
}
function money(v: number | null): string {
  if (v == null) return "—";
  const a = Math.abs(v); let s: string;
  if (a >= 1000) s = Math.round(v).toLocaleString("ru-RU");
  else if (a >= 10) s = v.toLocaleString("ru-RU", { maximumFractionDigits: 1 });
  else s = v.toLocaleString("ru-RU", { maximumFractionDigits: 2 });
  // Неразрывные пробелы/запятые → разряды «1 520» не ломаются на 2 строки в Word.
  return s.replace(/[\s,]/g, " ");
}
const KPI_PERIODS: { key: "year" | "q1" | "q2" | "q3" | "q4"; label: string }[] = [
  { key: "year", label: "Год" }, { key: "q1", label: "I кв." }, { key: "q2", label: "II кв." },
  { key: "q3", label: "III кв." }, { key: "q4", label: "IV кв." },
];
function periodLabel(p: string): string { return KPI_PERIODS.find(x => x.key === p)?.label || "Год"; }
const apxYearOptions = computed(() => { const y = props.year; return [y + 1, y, y - 1, y - 2, y - 3]; });

// ─── Фин. показатели (editor-эндпоинт, последний доступный год) ──
const FIN_METRICS = [
  { key: "revenue", label: "Выручка" }, { key: "ebitda", label: "EBITDA" },
  { key: "profit", label: "Чистая прибыль" }, { key: "totalAssets", label: "Итого активы" },
  { key: "equity", label: "Капитал" }, { key: "debt", label: "Итого долг" },
];
const finStandard = ref<"IFRS" | "NSBU">("IFRS");
const finValues = ref<Record<string, Record<string, number | null>>>({});
const finLoaded = ref(false);
const finLoading = ref(false);
async function loadFin() {
  if (!props.companyCode) return;
  finLoading.value = true;
  try {
    let std: "IFRS" | "NSBU" = "IFRS";
    let resp = await api.get(`/financials/companies/${props.companyCode}/ifrs-editor?period=FY&consolidated=true`).catch(() => null);
    let vals = (resp?.data?.values || {}) as Record<string, Record<string, number | null>>;
    if (!Object.keys(vals).length) {
      std = "NSBU";
      resp = await api.get(`/financials/companies/${props.companyCode}/nsbu-editor`).catch(() => null);
      vals = (resp?.data?.values || {}) as Record<string, Record<string, number | null>>;
    }
    finStandard.value = std; finValues.value = vals;
  } finally { finLoading.value = false; finLoaded.value = true; }
}
const finLatestYear = computed(() => {
  const ys = new Set<number>();
  for (const k of ["revenue", "profit", "totalAssets"]) {
    const fm = finValues.value[k];
    if (fm) for (const y of Object.keys(fm)) if (fm[y] != null) { const n = Number(y); if (Number.isFinite(n)) ys.add(n); }
  }
  const arr = [...ys].sort((a, b) => b - a);
  return arr[0] ?? props.year;
});
function finRaw(key: string, year: number): number | null { const v = finValues.value[key]?.[String(year)]; return v == null ? null : Number(v); }
function effFin(key: string, year: number): number | null {
  const o = finOv.value[`${key}:${year}`];
  if (o !== undefined && o !== "") return numOrNull(o);
  return finRaw(key, year);
}
const finVM = computed(() => {
  const y = finLatestYear.value, p = y - 1;
  return {
    loading: finLoading.value,
    empty: finLoaded.value && !FIN_METRICS.some(m => finRaw(m.key, y) != null),
    standard: finStandard.value, year: y, prev: p,
    rows: FIN_METRICS.map(m => {
      const cur = effFin(m.key, y), prev = effFin(m.key, p);
      const yoy = (cur != null && prev != null && prev !== 0) ? (cur - prev) / Math.abs(prev) : null;
      return { key: m.key, label: m.label, cur, prev, yoy, curKey: `${m.key}:${y}`, prevKey: `${m.key}:${p}` };
    }),
  };
});

// ─── KPI (managers за год; период year/q1..q4) ──────────────────
const kpiManagers = ref<KpiManager[]>([]);
const kpiLoaded = ref(false);
const kpiLoading = ref(false);
async function loadKpi() {
  if (!props.companyId) return;
  kpiLoading.value = true;
  try { const r = await kpiApi.getCompanyYear(props.companyId, apxYear.value); kpiManagers.value = r.managers || []; }
  catch { kpiManagers.value = []; }
  finally { kpiLoading.value = false; kpiLoaded.value = true; }
}
function kpiRawPlan(ind: any, p: string): number | null { const v = p === "year" ? ind.plan_year : ind[`${p}_plan`]; return v == null ? null : Number(v); }
function kpiRawFact(ind: any, p: string): number | null { const v = p === "year" ? ind.fact_year : ind[`${p}_fact`]; return v == null ? null : Number(v); }
function kpiWeight(ind: any, p: string): number { return num(p === "year" ? ind.weight : ind[`${p}_weight`]) || num(ind.weight); }
function effKpiPlan(ind: any): number | null { const o = kpiOv.value[`${ind.id}:${apxPeriod.value}:plan`]; if (o !== undefined && o !== "") return numOrNull(o); return kpiRawPlan(ind, apxPeriod.value); }
function effKpiFact(ind: any): number | null { const o = kpiOv.value[`${ind.id}:${apxPeriod.value}:fact`]; if (o !== undefined && o !== "") return numOrNull(o); return kpiRawFact(ind, apxPeriod.value); }
function kpiRatio(ind: any): number | null {
  let plan = effKpiPlan(ind), fact = effKpiFact(ind);
  if (apxPeriod.value === "year" && !(plan != null && plan !== 0 && fact != null)) {
    let sp = 0, sf = 0, had = false;
    for (const q of ["q1", "q2", "q3", "q4"]) {
      const qp = kpiRawPlan(ind, q), qf = kpiRawFact(ind, q);
      if (qp != null && qf != null && qp !== 0) { sp += qp; sf += qf; had = true; }
    }
    if (had && sp !== 0) { plan = sp; fact = sf; } else return null;
  }
  if (plan == null || fact == null) return null;
  const dir = ind.direction === "down" ? "down" : "up";
  if (dir === "down") return fact === 0 ? null : plan / fact;
  return plan === 0 ? null : fact / plan;
}
const kpiOverall = computed(() => {
  let sw = 0, swt = 0;
  for (const m of kpiManagers.value) for (const ind of m.indicators) {
    const w = kpiWeight(ind, apxPeriod.value); if (!w) continue;
    const r = kpiRatio(ind); if (r == null) continue;
    sw += w; swt += Math.min(r, 1.5) * w;
  }
  return sw > 0 ? swt / sw : null;
});
const kpiVM = computed(() => ({
  loading: kpiLoading.value,
  empty: kpiLoaded.value && !kpiManagers.value.length,
  overall: kpiOverall.value, periodLabel: periodLabel(apxPeriod.value), year: apxYear.value,
  groups: kpiManagers.value.map(m => ({
    id: m.id, title: m.short_title || m.title || "Руководитель", role: m.role,
    inds: m.indicators.map(ind => ({
      id: ind.id, name: ind.name, unit: ind.unit, weight: kpiWeight(ind, apxPeriod.value),
      plan: effKpiPlan(ind), fact: effKpiFact(ind), ratio: kpiRatio(ind),
      planKey: `${ind.id}:${apxPeriod.value}:plan`, factKey: `${ind.id}:${apxPeriod.value}:fact`,
    })),
  })),
}));

// ─── Бизнес-план (getComputed за период) ────────────────────────
const BP_SHOW = BP_FIELDS.filter(f => !f.sub);
const bpMetrics = ref<Record<string, BpCell>>({});
const bpLoaded = ref(false);
const bpLoading = ref(false);
async function loadBp() {
  if (!props.companyId) return;
  bpLoading.value = true;
  try {
    const p = apxPeriod.value === "year" ? "annual" : apxPeriod.value;
    const r = await bpApi.getComputed(props.companyId, apxYear.value, p as any);
    bpMetrics.value = r.metrics || {};
  } catch { bpMetrics.value = {}; } finally { bpLoading.value = false; bpLoaded.value = true; }
}
function bpRaw(metric: string, which: "plan" | "expect" | "fact"): number | null { const c = bpMetrics.value[metric]; const v = c ? (c as any)[which] : null; return v == null ? null : Number(v); }
function effBp(metric: string, which: "plan" | "expect" | "fact"): number | null {
  const o = bpOv.value[`${metric}:${apxYear.value}:${apxPeriod.value}:${which}`];
  if (o !== undefined && o !== "") return numOrNull(o);
  return bpRaw(metric, which);
}
function bpRatio(metric: string): number | null { const plan = effBp(metric, "plan"), fact = effBp(metric, "fact"); if (plan == null || fact == null || plan === 0) return null; return fact / plan; }
const bpOverall = computed(() => {
  let s = 0, c = 0;
  for (const k of ["revenue", "opProfit", "profit"]) { const r = bpRatio(k); if (r != null) { s += Math.min(r, 1.5); c++; } }
  return c > 0 ? s / c : null;
});
const bpVM = computed(() => ({
  loading: bpLoading.value,
  empty: bpLoaded.value && !Object.keys(bpMetrics.value).length,
  overall: bpOverall.value, periodLabel: periodLabel(apxPeriod.value), year: apxYear.value,
  rows: BP_SHOW.map(f => ({
    key: f.key, label: f.label, group: f.group, auto: !!f.auto,
    plan: effBp(f.key, "plan"), expect: effBp(f.key, "expect"), fact: effBp(f.key, "fact"), ratio: bpRatio(f.key),
    planKey: `${f.key}:${apxYear.value}:${apxPeriod.value}:plan`,
    expectKey: `${f.key}:${apxYear.value}:${apxPeriod.value}:expect`,
    factKey: `${f.key}:${apxYear.value}:${apxPeriod.value}:fact`,
  })),
}));

// ─── Рейтинги (кредитный + ESG) ─────────────────────────────────
function effRat(kind: "credit" | "esg", agency: string, field: string, fallback: string | null): string {
  const o = ratOv.value[`${kind}:${agency}:${field}`];
  return o !== undefined ? o : (fallback ?? "");
}
function ratRows(list: any[] | undefined, kind: "credit" | "esg") {
  return (list || []).map(r => ({
    agency: r.agency,
    rating: effRat(kind, r.agency, "rating", r.rating),
    outlook: effRat(kind, r.agency, "outlook", r.outlook),
    date: effRat(kind, r.agency, "date", r.rating_date_text || (r.rating_date ? String(r.rating_date).slice(0, 10) : "")),
    ratingKey: `${kind}:${r.agency}:rating`,
    outlookKey: `${kind}:${r.agency}:outlook`,
    dateKey: `${kind}:${r.agency}:date`,
  }));
}
const ratingsVM = computed(() => ({
  empty: !((props.credit?.length || 0) + (props.esg?.length || 0)),
  credit: ratRows(props.credit, "credit"),
  esg: ratRows(props.esg, "esg"),
}));
function ratingsDocHtml(): string {
  const v = ratingsVM.value; if (v.empty) return "";
  const th = (x: string, al = "center") => `<th style="border:1px solid #2a375a;background:#1e2a4a;color:#fff;font:700 9.5px Arial;padding:5px;text-align:${al}">${x}</th>`;
  const tbl = (title: string, rows: ReturnType<typeof ratRows>) => {
    if (!rows.length) return "";
    const body = rows.map(r => `<tr><td style="border:1px solid #d7d9e0;font:600 10px Arial;padding:4px">${esc(r.agency)}</td>
      <td style="border:1px solid #d7d9e0;text-align:center;font:700 10px Arial;padding:4px;color:#1e2787">${esc(r.rating || "—")}</td>
      <td style="border:1px solid #d7d9e0;text-align:center;font:400 10px Arial;padding:4px">${esc(r.outlook || "—")}</td>
      <td style="border:1px solid #d7d9e0;text-align:center;font:400 10px Arial;padding:4px;color:#5F6270">${esc(r.date || "—")}</td></tr>`).join("");
    return `<div style="margin-bottom:8px"><div style="font:700 10.5px Arial;color:#3A3D48;margin:6px 0 4px">${title}</div>
      <table style="border-collapse:collapse;width:100%;table-layout:fixed"><colgroup><col style="width:40%"/><col style="width:24%"/><col style="width:18%"/><col style="width:18%"/></colgroup>
      <thead><tr>${th("Агентство", "left")}${th("Рейтинг")}${th("Прогноз")}${th("Дата")}</tr></thead><tbody>${body}</tbody></table></div>`;
  };
  return `<div style="margin-top:18px"><div style="font:800 12px Arial;color:#14171F;margin-bottom:6px">РЕЙТИНГИ</div>${tbl("Кредитные рейтинги", v.credit)}${tbl("ESG-рейтинги", v.esg)}</div>`;
}

// ─── Тумблеры + правки приложения ───────────────────────────────
function toggleMatrix() { showMatrix.value = !showMatrix.value; scheduleSave(); }
function toggleRatings() { showRatings.value = !showRatings.value; scheduleSave(); }
function toggleFin() { showFin.value = !showFin.value; if (showFin.value && !finLoaded.value) loadFin(); scheduleSave(); }
function toggleKpi() { showKpi.value = !showKpi.value; if (showKpi.value && !kpiLoaded.value) loadKpi(); scheduleSave(); }
function toggleBp() { showBp.value = !showBp.value; if (showBp.value && !bpLoaded.value) loadBp(); scheduleSave(); }
function onApxEdit(kind: "fin" | "kpi" | "bp" | "rat", key: string, value: string) {
  if (kind === "fin") finOv.value = { ...finOv.value, [key]: value };
  else if (kind === "kpi") kpiOv.value = { ...kpiOv.value, [key]: value };
  else if (kind === "bp") bpOv.value = { ...bpOv.value, [key]: value };
  else ratOv.value = { ...ratOv.value, [key]: value };
  scheduleSave();
}

// ─── Doc-билдеры секций приложения (фирменная палитра) ──────────
function finDocHtml(): string {
  const v = finVM.value; if (v.empty) return "";
  const th = (x: string, al = "center") => `<th style="border:1px solid #2a375a;background:#1e2a4a;color:#fff;font:700 9.5px Arial;padding:5px;text-align:${al}">${x}</th>`;
  const rows = v.rows.map(r => `<tr><td style="border:1px solid #d7d9e0;font:600 10px Arial;padding:4px">${esc(r.label)}</td>
    <td style="border:1px solid #d7d9e0;text-align:right;font:400 10px Arial;padding:4px">${money(r.prev)}</td>
    <td style="border:1px solid #d7d9e0;text-align:right;font:700 10px Arial;padding:4px">${money(r.cur)}</td>
    <td style="border:1px solid #d7d9e0;text-align:right;font:400 10px Arial;padding:4px;color:#5F6270">${r.yoy == null ? "" : (r.yoy > 0 ? "+" : "−") + Math.abs(Math.round(r.yoy * 100)) + "%"}</td></tr>`).join("");
  return `<div style="margin-top:18px"><div style="font:800 12px Arial;color:#14171F;margin-bottom:6px">ОСНОВНЫЕ ФИНАНСОВЫЕ ПОКАЗАТЕЛИ <span style="font:400 10px Arial;color:#8A8C99">· за ${v.year} год · млрд сум · ${v.standard}</span></div>
    <table style="border-collapse:collapse;width:100%;table-layout:fixed"><colgroup><col style="width:46%"/><col style="width:18%"/><col style="width:18%"/><col style="width:18%"/></colgroup><thead><tr>${th("Показатель", "left")}${th(String(v.prev))}${th(String(v.year))}${th("Δ г/г")}</tr></thead><tbody>${rows}</tbody></table></div>`;
}
function kpiDocHtml(): string {
  const v = kpiVM.value; if (v.empty) return "";
  const th = (x: string, al = "center") => `<th style="border:1px solid #2a375a;background:#1e2a4a;color:#fff;font:700 9.5px Arial;padding:5px;text-align:${al}">${x}</th>`;
  const body = v.groups.map(g => {
    const head = `<tr><td colspan="6" style="border:1px solid #d7d9e0;background:#eceaf6;font:700 10px Arial;padding:4px">${esc(g.title)}${g.role ? " · " + esc(g.role) : ""}</td></tr>`;
    const inds = g.inds.map(ind => `<tr><td style="border:1px solid #d7d9e0;font:400 10px Arial;padding:4px">${esc(ind.name)}</td>
      <td style="border:1px solid #d7d9e0;text-align:center;font:400 10px Arial;padding:4px">${esc(ind.unit || "—")}</td>
      <td style="border:1px solid #d7d9e0;text-align:right;font:400 10px Arial;padding:4px">${money(ind.plan)}</td>
      <td style="border:1px solid #d7d9e0;text-align:right;font:400 10px Arial;padding:4px">${money(ind.fact)}</td>
      <td style="border:1px solid #d7d9e0;text-align:center;font:400 10px Arial;padding:4px">${ind.weight || "—"}</td>
      <td style="border:1px solid #d7d9e0;text-align:center;font:700 10px Arial;padding:4px">${ind.ratio == null ? "—" : Math.round(ind.ratio * 100) + "%"}</td></tr>`).join("");
    return head + inds;
  }).join("");
  const ov = v.overall == null ? "" : ` · итого ${Math.round(v.overall * 100)}%`;
  return `<div style="margin-top:18px"><div style="font:800 12px Arial;color:#14171F;margin-bottom:6px">ИСПОЛНЕНИЕ KPI <span style="font:400 10px Arial;color:#8A8C99">· ${v.year} · ${v.periodLabel}${ov}</span></div>
    <table style="border-collapse:collapse;width:100%;table-layout:fixed"><colgroup><col style="width:44%"/><col style="width:8%"/><col style="width:15%"/><col style="width:15%"/><col style="width:8%"/><col style="width:10%"/></colgroup><thead><tr>${th("КПЭ", "left")}${th("Ед.")}${th("План")}${th("Факт")}${th("Вес")}${th("Исполн.")}</tr></thead><tbody>${body}</tbody></table></div>`;
}
function bpDocHtml(): string {
  const v = bpVM.value; if (v.empty) return "";
  const th = (x: string, al = "center") => `<th style="border:1px solid #2a375a;background:#1e2a4a;color:#fff;font:700 9.5px Arial;padding:5px;text-align:${al}">${x}</th>`;
  const rows = v.rows.map(r => `<tr><td style="border:1px solid #d7d9e0;font:${r.auto ? 700 : 400} 10px Arial;padding:4px">${esc(r.label)}</td>
    <td style="border:1px solid #d7d9e0;text-align:right;font:400 10px Arial;padding:4px">${money(r.plan)}</td>
    <td style="border:1px solid #d7d9e0;text-align:right;font:400 10px Arial;padding:4px">${money(r.expect)}</td>
    <td style="border:1px solid #d7d9e0;text-align:right;font:400 10px Arial;padding:4px">${money(r.fact)}</td>
    <td style="border:1px solid #d7d9e0;text-align:center;font:700 10px Arial;padding:4px">${r.ratio == null ? "—" : Math.round(r.ratio * 100) + "%"}</td></tr>`).join("");
  const ov = v.overall == null ? "" : ` · выручка ${Math.round(v.overall * 100)}%`;
  return `<div style="margin-top:18px"><div style="font:800 12px Arial;color:#14171F;margin-bottom:6px">ИСПОЛНЕНИЕ БИЗНЕС-ПЛАНА <span style="font:400 10px Arial;color:#8A8C99">· ${v.year} · ${v.periodLabel} · млрд сум${ov}</span></div>
    <table style="border-collapse:collapse;width:100%;table-layout:fixed"><colgroup><col style="width:44%"/><col style="width:16%"/><col style="width:16%"/><col style="width:16%"/><col style="width:8%"/></colgroup><thead><tr>${th("Показатель", "left")}${th("План")}${th("Ожид.")}${th("Факт")}${th("Исполн.")}</tr></thead><tbody>${rows}</tbody></table></div>`;
}

// ─── Печать (альбомная ориентация, teleport-оверлей) ─────────────
const printOpen = ref(false);
function ensureLandscapeStyle() {
  let st = document.getElementById("psr-landscape") as HTMLStyleElement | null;
  if (!st) { st = document.createElement("style"); st.id = "psr-landscape"; document.head.appendChild(st); }
  st.textContent = "@media print { @page { size: A4 landscape; margin: 9mm; } }";
}
function removeLandscapeStyle() { document.getElementById("psr-landscape")?.remove(); }
function openPrint() { printOpen.value = true; document.body.classList.add("pdoc-open"); ensureLandscapeStyle(); }
function closePrint() { printOpen.value = false; document.body.classList.remove("pdoc-open"); removeLandscapeStyle(); }
async function doPrint() { ensureLandscapeStyle(); await nextTick(); window.print(); }
onUnmounted(() => { document.body.classList.remove("pdoc-open"); removeLandscapeStyle(); });

// ─── Экспорт .doc (печатный формат, фирменная палитра) ──────────
function esc(s: string) { return String(s ?? "").replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;"); }
// Знак → PNG data-URI через canvas (даунскейл + нормализация формата: Word
// надёжно показывает компактный PNG, а большой исходный base64/SVG — нет).
function rasterize(src: string, h: number): Promise<string> {
  return new Promise((resolve) => {
    const img = new Image();
    img.crossOrigin = "anonymous";
    img.onload = () => {
      try {
        const nh = img.naturalHeight || h, nw = img.naturalWidth || h;
        const w = Math.max(1, Math.round((nw / nh) * h));
        const c = document.createElement("canvas");
        c.width = w * 2; c.height = h * 2; // 2× для чёткости
        const ctx = c.getContext("2d");
        if (!ctx) return resolve("");
        ctx.drawImage(img, 0, 0, c.width, c.height);
        resolve(c.toDataURL("image/png"));
      } catch { resolve(""); }
    };
    img.onerror = () => resolve("");
    img.src = src;
  });
}
// Фирменная EPT-стрелка (градиент пурпур→бирюза) — как в логотипе платформы.
const EPT_SVG = `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 240 220"><defs><linearGradient id="g" x1="0" y1="0.5" x2="1" y2="0.5"><stop offset="0%" stop-color="#7F77DD"/><stop offset="100%" stop-color="#1D9E75"/></linearGradient></defs><path d="M 80 30 L 210 110 L 80 190 L 115 110 Z" fill="url(#g)"/></svg>`;
const exporting = ref(false);
async function exportDoc() {
  if (exporting.value) return;
  exporting.value = true;
  try {
    const s = summary.value;
    const sumLine = (t: typeof s.projects) =>
      `завершено ${t.done} (${pct(t.done, t.total)}%) · в процессе ${t.inprogress} (${pct(t.inprogress, t.total)}%) · не начато ${t.notstarted} (${pct(t.notstarted, t.total)}%)`;
    const [minfinB64, uzaB64, eptB64] = await Promise.all([
      rasterize(minfinLogoUrl, 46),
      rasterize(uzassetsLogoUrl, 30),
      rasterize("data:image/svg+xml;charset=utf-8," + encodeURIComponent(EPT_SVG), 30),
    ]);
    const eptCell = `<table style="margin:0 auto;border-collapse:collapse"><tr>${eptB64 ? `<td style="vertical-align:middle;padding-right:7px"><img src="${eptB64}" height="30" style="height:30px"/></td>` : ""}<td style="vertical-align:middle;text-align:left;font:800 11px Arial;color:#4B4A9A;letter-spacing:.5px;line-height:1.2">ЕДИНАЯ ПЛАТФОРМА<br/>ТРАНСФОРМАЦИИ</td></tr></table>`;
    // Официальная тройная шапка (как в печати): Минфин · EPT · UzAssets.
    const head = `
      <table style="width:100%;border-collapse:collapse;border-bottom:2.5px solid #4B4A9A;margin-bottom:10px"><tr>
        <td style="width:32%;text-align:left;padding-bottom:8px;vertical-align:middle">${minfinB64 ? `<img src="${minfinB64}" height="46" style="height:46px"/>` : `<span style="font:700 11px Arial;color:#1E2A4A">Иқтисодиёт ва молия вазирлиги</span>`}</td>
        <td style="width:36%;text-align:center;padding-bottom:8px;vertical-align:middle">${eptCell}</td>
        <td style="width:32%;text-align:right;padding-bottom:8px;vertical-align:middle">${uzaB64 ? `<img src="${uzaB64}" height="30" style="height:30px"/>` : `<span style="font:800 14px Arial;color:#6C5CE7">UzAssets</span>`}</td>
      </tr><tr>
        <td colspan="2" style="padding-top:8px;font:800 17px Arial;color:#14171F">${esc(props.companyName)}</td>
        <td style="padding-top:8px;text-align:right;font:600 10px Arial;color:#8A8C99;text-transform:uppercase">${props.sectorName ? esc(props.sectorName) + " · " : ""}отчёт по проектам</td>
      </tr></table>
      <div style="font:11px Arial;color:#3A3D48;margin:0 0 12px;line-height:1.5">
        <b>Проекты:</b> ${s.projects.total} — ${sumLine(s.projects)}<br/>
        <b>Задачи:</b> ${s.tasks.total} — ${sumLine(s.tasks)}
        <div style="color:#8A8C99;font-size:10px;margin-top:3px">FY ${props.year} · по состоянию на ${stampToday()}</div>
      </div>`;
    const th = (x: string) => `<th style="border:1px solid #2a375a;background:#1e2a4a;color:#fff;font:700 10px Arial;padding:6px;text-align:left">${x}</th>`;
    const td = (x: string, b = false) => `<td style="border:1px solid #d7d9e0;font:${b ? "700" : "400"} 10.5px Arial;padding:5px;vertical-align:top">${esc(x)}</td>`;
    const body = printableRows.value.map(r => {
      const proj = r.kind === "project";
      const bg = proj ? ' style="background:#f3f2fb"' : "";
      const st = printStatusStyle(effStatus(r));
      return `<tr${bg}>${td(r.num, proj)}${td(dirLabel(r.dirCode))}${td(r.title, proj)}${td(effSrok(r))}
        <td style="border:1px solid #d7d9e0;font:${st.weight} 10.5px Arial;padding:5px;color:${st.color};background:${st.bg}">${esc(statusLabel(effStatus(r)))}</td>
        ${td(effComment(r))}</tr>`;
    }).join("");
    const mainCols = `<colgroup><col style="width:4%"/><col style="width:15%"/><col style="width:33%"/><col style="width:9%"/><col style="width:12%"/><col style="width:27%"/></colgroup>`;
    const sections = `${showMatrix.value ? matrixDocHtml() : ""}${showFin.value ? finDocHtml() : ""}${showKpi.value ? kpiDocHtml() : ""}${showBp.value ? bpDocHtml() : ""}${showRatings.value ? ratingsDocHtml() : ""}`;
    const html = `<html xmlns:o='urn:schemas-microsoft-com:office:office' xmlns:w='urn:schemas-microsoft-com:office:word'>
      <head><meta charset="utf-8"><!--[if gte mso 9]><xml><w:WordDocument><w:View>Print</w:View><w:Zoom>100</w:Zoom></w:WordDocument>
      <o:OfficeDocumentSettings/></xml><![endif]-->
      <style>
        @page WordSection1 { size: 841.9pt 595.3pt; mso-page-orientation: landscape; margin: 1.0cm 1.2cm; }
        div.WordSection1 { page: WordSection1; }
        body { font-family: Arial, sans-serif; color: #1E2A4A; }
        table { border-collapse: collapse; }
        td, th { mso-line-height-rule: exactly; }
      </style></head>
      <body><div class="WordSection1">${head}
      <table style="border-collapse:collapse;width:100%;table-layout:fixed">${mainCols}
        <thead><tr>${["№", "Направление", "Проект / Задача", "Срок", "Статус", "Комментарий / статус"].map(th).join("")}</tr></thead>
        <tbody>${body}</tbody></table>${sections}</div></body></html>`;
    const blob = new Blob(["﻿", html], { type: "application/msword" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url; a.download = `Отчёт по проектам — ${props.companyName} — FY${props.year}.doc`;
    document.body.appendChild(a); a.click(); a.remove(); URL.revokeObjectURL(url);
  } catch (e: any) {
    toast.error("Не удалось сформировать Word: " + (e?.message || ""));
  } finally { exporting.value = false; }
}

onMounted(() => { directionsStore.ensureLoaded(); loadConfig(); });
watch(() => [props.year, props.companyCode], loadConfig);
// Приложение-секции реагируют на выбор года/квартала и позднюю инициализацию companyId.
watch(() => props.companyId, () => { if (showKpi.value) loadKpi(); if (showBp.value) loadBp(); });
watch(apxYear, () => { scheduleSave(); if (showKpi.value) loadKpi(); if (showBp.value) loadBp(); });
watch(apxPeriod, () => { scheduleSave(); if (showBp.value) loadBp(); });
</script>

<template>
  <div class="psr">
    <!-- ── Официальная тройная шапка ── -->
    <table class="psr-lh">
      <tbody>
        <tr class="lh-logos">
          <td class="lh-left"><img :src="minfinLogoUrl" alt="Иқтисодиёт ва молия вазирлиги" class="lh-minfin" /></td>
          <td class="lh-center">
            <div class="lh-ept">
              <EptLogo :size="30" class="lh-ept-mark" />
              <div class="lh-ept-t">ЕДИНАЯ ПЛАТФОРМА<br />ТРАНСФОРМАЦИИ</div>
            </div>
          </td>
          <td class="lh-right"><img :src="uzassetsLogoUrl" alt="UzAssets" class="lh-uza" /></td>
        </tr>
        <tr class="lh-titlerow">
          <td colspan="2" class="lh-company">{{ companyName }}</td>
          <td class="lh-sector">{{ sectorName || "—" }} · отчёт по проектам</td>
        </tr>
      </tbody>
    </table>

    <!-- ── Тулбар действий (вне печати) ── -->
    <div class="psr-toolbar">
      <span class="psr-tb-sub">Реализация мероприятий трансформации · FY {{ year }}</span>
      <span class="psr-tb-sp" />
      <transition name="psr-fade"><span v-if="saving" class="psr-saving">● сохранение</span></transition>
      <button class="psr-btn ghost" @click="resetOverrides" title="Вернуть данные из системы">Сбросить правки</button>
      <button class="psr-btn ghost" @click="exportDoc">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4M7 10l5 5 5-5M12 15V3"/></svg>
        Экспорт в Word
      </button>
      <button class="psr-btn" @click="openPrint">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M6 9V2h12v7M6 18H4a2 2 0 0 1-2-2v-5a2 2 0 0 1 2-2h16a2 2 0 0 1 2 2v5a2 2 0 0 1-2 2h-2M6 14h12v8H6z"/></svg>
        Печать
      </button>
    </div>

    <!-- ── Приложение: разделы в конце листа + выбор периода (вне печати) ── -->
    <div class="psr-apxbar">
      <span class="psr-apx-label">В конце листа:</span>
      <label class="psr-toggle" :class="{ on: showMatrix }">
        <input type="checkbox" :checked="showMatrix" @change="toggleMatrix" />
        <span class="psr-toggle-track"><span class="psr-toggle-knob" /></span>Статус-матрица
      </label>
      <label class="psr-toggle" :class="{ on: showFin }">
        <input type="checkbox" :checked="showFin" @change="toggleFin" />
        <span class="psr-toggle-track"><span class="psr-toggle-knob" /></span>Фин. показатели
      </label>
      <label class="psr-toggle" :class="{ on: showKpi }">
        <input type="checkbox" :checked="showKpi" @change="toggleKpi" />
        <span class="psr-toggle-track"><span class="psr-toggle-knob" /></span>Исполнение KPI
      </label>
      <label class="psr-toggle" :class="{ on: showBp }">
        <input type="checkbox" :checked="showBp" @change="toggleBp" />
        <span class="psr-toggle-track"><span class="psr-toggle-knob" /></span>Бизнес-план
      </label>
      <label class="psr-toggle" :class="{ on: showRatings }">
        <input type="checkbox" :checked="showRatings" @change="toggleRatings" />
        <span class="psr-toggle-track"><span class="psr-toggle-knob" /></span>Рейтинги
      </label>
      <template v-if="showKpi || showBp">
        <span class="psr-apx-sep" />
        <span class="psr-apx-label">Период:</span>
        <select class="psr-sel" :value="apxYear" @change="apxYear = Number(($event.target as HTMLSelectElement).value)">
          <option v-for="y in apxYearOptions" :key="y" :value="y">{{ y }}</option>
        </select>
        <div class="psr-segctl">
          <button v-for="p in KPI_PERIODS" :key="p.key" :class="{ on: apxPeriod === p.key }" @click="apxPeriod = p.key">{{ p.label }}</button>
        </div>
      </template>
    </div>

    <!-- ── Фильтр-чипы по статусу (вне печати) ── -->
    <div v-if="rows.length" class="psr-filterbar">
      <span class="psr-fb-l">Статус:</span>
      <button class="psr-chip" :class="{ on: statusFilter === null }" @click="statusFilter = null">
        Все <b>{{ filterChips.total }}</b>
      </button>
      <button v-for="c in filterChips.chips" :key="c.key" class="psr-chip"
              :class="{ on: statusFilter === c.key }"
              :style="statusFilter === c.key ? { background: c.color + '18', borderColor: c.color, color: c.color } : {}"
              @click="statusFilter = statusFilter === c.key ? null : c.key">
        <span class="psr-chip-dot" :style="{ background: c.color }" />{{ c.label }} <b>{{ c.count }}</b>
      </button>
      <button v-if="filterChips.overdue" class="psr-chip psr-chip-od" :class="{ on: statusFilter === 'overdue' }"
              @click="statusFilter = statusFilter === 'overdue' ? null : 'overdue'">
        <span class="psr-chip-dot" style="background:#E24B4A" />Просроченные <b>{{ filterChips.overdue }}</b>
      </button>
    </div>

    <!-- ── Таблица (порядок как в work-табе) ── -->
    <div class="psr-table-wrap">
      <UzaSkeleton v-if="loadingCfg" variant="rows" :rows="8" rowHeight="34px" />
      <table v-else class="psr-table">
        <thead>
          <tr>
            <th class="c-pick" title="Отметьте, что включить в печать/экспорт">
              <input type="checkbox" class="psr-cb" :checked="allIncluded" @change="toggleAll" title="Выбрать всё / снять всё" />
            </th>
            <th class="c-num">№</th>
            <th class="c-dir">Направление</th>
            <th class="c-title">Проект / Задача</th>
            <th class="c-srok">Срок</th>
            <th class="c-status">Статус</th>
            <th class="c-com">Комментарий / статус</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="r in displayRows" :key="r.id" :class="{ 'is-project': r.kind === 'project', 'is-edited': isEdited(r), 'is-excluded': !isIncluded(r.id) }">
            <td class="c-pick"><input type="checkbox" class="psr-cb" :checked="isIncluded(r.id)" @change="toggleRow(r.id)" :title="isIncluded(r.id) ? 'Включено в отчёт' : 'Исключено из отчёта'" /></td>
            <td class="c-num">{{ r.num }}</td>
            <td class="c-dir">
              <span class="psr-dir-dot" :style="{ background: dirColor(r.dirCode) }" />
              <span class="psr-dir-l" :style="{ color: dirColor(r.dirCode) }">{{ dirLabel(r.dirCode) }}</span>
            </td>
            <td class="c-title"><span class="psr-title-txt" :class="{ proj: r.kind === 'project' }">{{ r.title }}</span></td>
            <td class="c-srok"><input class="psr-in" :value="effSrok(r)" @change="setOverride(r.id, 'srok', ($event.target as HTMLInputElement).value)" /></td>
            <td class="c-status">
              <span class="psr-pill" :style="{ color: statusColor(effStatus(r)), background: statusColor(effStatus(r)) + '1a' }">
                {{ statusLabel(effStatus(r)) }}
                <select class="psr-pill-sel" :value="effStatus(r)" @change="setOverride(r.id, 'status', ($event.target as HTMLSelectElement).value)">
                  <option v-for="o in STATUS_OPTIONS" :key="o" :value="o">{{ statusLabel(o) }}</option>
                </select>
              </span>
            </td>
            <td class="c-com">
              <div class="psr-com">
                <span v-if="r.health" class="psr-health" :title="HEALTH_META[r.health].label" :style="{ background: HEALTH_META[r.health].color }" />
                <textarea class="psr-ta" :value="effComment(r)" rows="1" placeholder="—"
                          @focus="autoGrow" @input="autoGrow"
                          @change="setOverride(r.id, 'comment', ($event.target as HTMLTextAreaElement).value)"></textarea>
              </div>
            </td>
          </tr>
          <tr v-if="!rows.length"><td colspan="7" class="psr-empty">Нет проектов и задач за {{ year }} год.</td></tr>
        </tbody>
      </table>
    </div>

    <!-- ── Приложение-секции (экран, редактируемо) ── -->
    <ReportAppendix
      v-if="showMatrix || showFin || showKpi || showBp || showRatings"
      :readonly="false"
      :show="{ matrix: showMatrix, fin: showFin, kpi: showKpi, bp: showBp, ratings: showRatings }"
      :matrix="matrix"
      :matrix-cols="MATRIX_COLS"
      :fin="finVM"
      :kpi="kpiVM"
      :bp="bpVM"
      :rat="ratingsVM"
      @edit="onApxEdit"
    />

    <!-- ── ПЕЧАТНЫЙ ОВЕРЛЕЙ (альбомный, фирменная палитра) ── -->
    <Teleport to="body">
      <div v-if="printOpen" class="pdoc-overlay">
        <div class="pdoc-toolbar">
          <span class="pdt-title">Предпросмотр печати · альбомная ориентация</span>
          <span class="pdt-sp" />
          <button class="pdt-btn" @click="doPrint">Печать</button>
          <button class="pdt-btn ghost" @click="closePrint">Закрыть</button>
        </div>
        <div class="pdoc-scroll">
          <div class="pdoc-sheet psr-print">
            <table class="psr-lh">
              <tbody>
                <tr class="lh-logos">
                  <td class="lh-left"><img :src="minfinLogoUrl" alt="" class="lh-minfin" /></td>
                  <td class="lh-center">
                    <div class="lh-ept">
                      <EptLogo :size="30" class="lh-ept-mark" />
                      <div class="lh-ept-t">ЕДИНАЯ ПЛАТФОРМА<br />ТРАНСФОРМАЦИИ</div>
                    </div>
                  </td>
                  <td class="lh-right"><img :src="uzassetsLogoUrl" alt="" class="lh-uza" /></td>
                </tr>
                <tr class="lh-titlerow">
                  <td colspan="2" class="lh-company">{{ companyName }}</td>
                  <td class="lh-sector">{{ sectorName || "—" }} · отчёт по проектам</td>
                </tr>
              </tbody>
            </table>
            <div class="psr-print-sum">
              <b>Проекты:</b> {{ summary.projects.total }} — завершено {{ summary.projects.done }} ({{ pct(summary.projects.done, summary.projects.total) }}%) · в процессе {{ summary.projects.inprogress }} ({{ pct(summary.projects.inprogress, summary.projects.total) }}%) · не начато {{ summary.projects.notstarted }} ({{ pct(summary.projects.notstarted, summary.projects.total) }}%)<br />
              <b>Задачи:</b> {{ summary.tasks.total }} — завершено {{ summary.tasks.done }} ({{ pct(summary.tasks.done, summary.tasks.total) }}%) · в процессе {{ summary.tasks.inprogress }} ({{ pct(summary.tasks.inprogress, summary.tasks.total) }}%) · не начато {{ summary.tasks.notstarted }} ({{ pct(summary.tasks.notstarted, summary.tasks.total) }}%)
              <span class="psr-print-stamp">по состоянию на {{ stampToday() }}</span>
            </div>
            <table class="psr-print-tbl">
              <thead>
                <tr><th>№</th><th>Направление</th><th>Проект / Задача</th><th>Срок</th><th>Статус</th><th>Комментарий / статус</th></tr>
              </thead>
              <tbody>
                <tr v-for="r in printableRows" :key="r.id" :class="{ proj: r.kind === 'project' }">
                  <td class="pn">{{ r.num }}</td>
                  <td class="pd">{{ dirLabel(r.dirCode) }}</td>
                  <td :class="{ pt: r.kind === 'project' }">{{ r.title }}</td>
                  <td class="ps">{{ effSrok(r) }}</td>
                  <td class="pst">
                    <span class="psr-print-pill" :style="{ background: printStatusStyle(effStatus(r)).bg, color: printStatusStyle(effStatus(r)).color, fontWeight: printStatusStyle(effStatus(r)).weight }">{{ statusLabel(effStatus(r)) }}</span>
                  </td>
                  <td class="pc">{{ effComment(r) }}</td>
                </tr>
              </tbody>
            </table>
            <ReportAppendix
              v-if="showMatrix || showFin || showKpi || showBp || showRatings"
              :readonly="true"
              :show="{ matrix: showMatrix, fin: showFin, kpi: showKpi, bp: showBp, ratings: showRatings }"
              :matrix="matrix"
              :matrix-cols="MATRIX_COLS"
              :fin="finVM"
              :kpi="kpiVM"
              :bp="bpVM"
              :rat="ratingsVM"
            />
            <div class="psr-print-foot">Единая платформа трансформации · UzAssets — сформировано {{ stampToday() }}</div>
          </div>
        </div>
      </div>
    </Teleport>
  </div>
</template>

<style scoped>
.psr { display: flex; flex-direction: column; gap: 14px; }

/* ── Официальная тройная шапка ── */
.psr-lh { width: 100%; border-collapse: collapse; table-layout: fixed; position: relative; }
/* Полоса-разделитель шапки — флаг Узбекистана (как edt-flag на execdash), статично для печати */
.psr-lh::after {
  content: ""; position: absolute; left: 0; right: 0; bottom: -3px; height: 3px; border-radius: 1px;
  background: linear-gradient(90deg,
    #0099B5 0 33%, #CE1126 33% 33.4%, #E9E9EE 33.4% 66.6%,
    #CE1126 66.6% 67%, #1EB53A 67% 100%);
  box-shadow: 0 0 0 0.5px rgba(30,42,74,.10);  /* тонкий контур — белая часть видна на белой бумаге */
  -webkit-print-color-adjust: exact; print-color-adjust: exact;
}
.psr-lh td { vertical-align: middle; padding: 0; }
/* Логотипы — на одной оптической линии: фикс-высота строки + центрирование. */
.lh-logos td { height: 50px; padding-bottom: 12px; vertical-align: middle; }
.lh-left { width: 33%; text-align: left; }
.lh-center { width: 34%; text-align: center; }
.lh-right { width: 33%; text-align: right; }
.lh-minfin { height: 48px; width: auto; object-fit: contain; vertical-align: middle; display: inline-block; }
.lh-uza { height: 30px; width: auto; object-fit: contain; vertical-align: middle; display: inline-block; }
.lh-ept { display: inline-flex; align-items: center; gap: 9px; vertical-align: middle; }
.lh-ept-mark { width: 24px; height: 24px; flex-shrink: 0; }
.lh-ept-t { font-size: 11px; font-weight: 800; letter-spacing: .12em; color: #4B4A9A; text-align: left; line-height: 1.18; }
.lh-titlerow td { padding-top: 9px; padding-bottom: 7px; }
.lh-company { font-size: 19px; font-weight: 800; color: var(--t1, #14171F); letter-spacing: -.01em; }
.lh-sector { text-align: right; font-size: 11px; font-weight: 600; color: #8A8C99; text-transform: uppercase; letter-spacing: .04em; white-space: nowrap; }

/* ── Тулбар ── */
.psr-toolbar { display: flex; align-items: center; gap: 9px; flex-wrap: wrap; }
.psr-tb-sub { font-size: 11.5px; color: var(--t3, #64748B); }
.psr-tb-sp { flex: 1; }
.psr-saving { font-size: 11px; color: #7F77DD; }
.psr-btn { display: inline-flex; align-items: center; gap: 7px; background: linear-gradient(135deg, #8B7FFF, #6C5CE7); color: #fff; border: none; font: 600 12px inherit; padding: 8px 14px; border-radius: 10px; cursor: pointer; box-shadow: 0 4px 14px rgba(108,92,231,.28); transition: transform .15s; }
.psr-btn:hover { transform: translateY(-1px); }
.psr-btn.ghost { background: transparent; color: var(--t3, #64748B); border: 1px solid rgba(99,102,180,.22); box-shadow: none; }
.psr-btn.ghost:hover { color: #6C5CE7; border-color: #6C5CE7; transform: none; }
.psr-fade-enter-active, .psr-fade-leave-active { transition: opacity .25s; }
.psr-fade-enter-from, .psr-fade-leave-to { opacity: 0; }
/* Тумблер «Статус-матрица» */
.psr-toggle { display: inline-flex; align-items: center; gap: 7px; font: 600 12px inherit; color: var(--t3, #64748B); cursor: pointer; user-select: none; }
.psr-toggle.on { color: #6C5CE7; }
.psr-toggle input { position: absolute; opacity: 0; width: 0; height: 0; }
.psr-toggle-track { width: 32px; height: 18px; border-radius: 999px; background: #D8DAE6; position: relative; transition: background .2s; flex: 0 0 auto; }
.psr-toggle.on .psr-toggle-track { background: linear-gradient(135deg, #8B7FFF, #6C5CE7); }
.psr-toggle-knob { position: absolute; top: 2px; left: 2px; width: 14px; height: 14px; border-radius: 50%; background: #fff; box-shadow: 0 1px 3px rgba(0,0,0,.25); transition: transform .2s; }
.psr-toggle.on .psr-toggle-knob { transform: translateX(14px); }

/* ── Приложение: бар разделов + выбор периода ── */
.psr-apxbar { display: flex; align-items: center; gap: 12px; flex-wrap: wrap; padding: 9px 14px; background: rgba(127,119,221,.05); border: 1px solid rgba(99,102,180,.12); border-radius: 12px; }

/* Фильтр-чипы по статусу (клик → фильтр таблицы; вне печати) */
.psr-filterbar { display: flex; align-items: center; gap: 7px; flex-wrap: wrap; margin: 12px 0 2px; }
.psr-fb-l { font-size: 10.5px; font-weight: 600; color: var(--t3, #64748b); text-transform: uppercase; letter-spacing: .05em; margin-right: 2px; }
.psr-chip { display: inline-flex; align-items: center; gap: 6px; padding: 4px 11px; border-radius: 999px;
  border: 1px solid rgba(99,102,180,.20); background: #fff; font: 500 12px inherit; color: var(--t2, #475569);
  cursor: pointer; transition: background .13s, border-color .13s, color .13s, box-shadow .13s; }
.psr-chip:hover { border-color: rgba(99,102,180,.42); background: rgba(127,119,221,.04); }
.psr-chip.on { font-weight: 600; box-shadow: 0 1px 5px rgba(15,23,60,.09); }
.psr-chip b { font-weight: 700; font-feature-settings: 'tnum'; opacity: .7; }
.psr-chip-dot { width: 8px; height: 8px; border-radius: 50%; flex-shrink: 0; }
.psr-chip-od { color: #C0392B; border-color: rgba(226,75,74,.28); }
.psr-chip-od:hover { border-color: rgba(226,75,74,.5); background: rgba(226,75,74,.05); }
.psr-chip-od.on { background: rgba(226,75,74,.10); border-color: #E24B4A; }
.psr-apx-label { font-size: 10.5px; font-weight: 600; letter-spacing: .04em; text-transform: uppercase; color: var(--t3, #8A8C99); }
.psr-apx-sep { width: 1px; align-self: stretch; background: rgba(99,102,180,.18); margin: 0 2px; }
.psr-sel { font: 600 12px inherit; color: var(--t1, #1e2a4a); background: #fff; border: 1px solid rgba(99,102,180,.25); border-radius: 8px; padding: 5px 9px; cursor: pointer; }
.psr-sel:focus { outline: none; border-color: #7F77DD; }
.psr-segctl { display: inline-flex; border: 1px solid rgba(99,102,180,.22); border-radius: 8px; overflow: hidden; }
.psr-segctl button { font: 600 11.5px inherit; color: var(--t3, #64748B); background: #fff; border: none; padding: 5px 11px; cursor: pointer; border-left: 1px solid rgba(99,102,180,.14); }
.psr-segctl button:first-child { border-left: none; }
.psr-segctl button.on { background: linear-gradient(135deg, #8B7FFF, #6C5CE7); color: #fff; }
.psr-segctl button:not(.on):hover { background: rgba(127,119,221,.08); }

/* ── Сводка ── */
.psr-stats { display: grid; grid-template-columns: 1fr 1fr; gap: 14px; }
@media (max-width: 760px) { .psr-stats { grid-template-columns: 1fr; } }
.psr-stat { background: #fff; border: 1px solid rgba(99,102,180,.12); border-radius: 14px; padding: 14px 18px; position: relative; overflow: hidden; box-shadow: 0 4px 14px rgba(15,23,60,.05); }
.psr-stat::before { content: ""; position: absolute; left: 0; top: 0; right: 0; height: 3px; background: linear-gradient(90deg, #9D97E6, #7F77DD); }
.psr-stat-top { display: flex; align-items: baseline; justify-content: space-between; }
.psr-stat-h { font-size: 10.5px; font-weight: 600; letter-spacing: .07em; text-transform: uppercase; color: var(--t3, #64748B); }
.psr-stat-n { font-size: 30px; font-weight: 400; color: var(--t1, #1e2a4a); font-variant-numeric: tabular-nums; line-height: 1; letter-spacing: -.02em; }
.psr-seg { display: flex; height: 9px; border-radius: 5px; overflow: hidden; background: #EEF0F6; margin: 11px 0 9px; }
.psr-seg-p { height: 100%; transition: width .7s cubic-bezier(.22,1,.36,1); }
.psr-seg-p.done { background: linear-gradient(90deg, #34C088, #1D9E75); }
.psr-seg-p.ip { background: linear-gradient(90deg, #5BA3F0, #2563EB); }
.psr-seg-p.ns { background: #CBD2DE; }
.psr-leg { display: flex; flex-wrap: wrap; gap: 5px 16px; font-size: 11.5px; color: var(--t3, #5F6B80); }
.psr-leg-i { display: inline-flex; align-items: center; gap: 5px; }
.psr-leg-i b { color: var(--t1, #1e2a4a); font-weight: 600; font-variant-numeric: tabular-nums; }
.psr-leg-i i { width: 8px; height: 8px; border-radius: 2px; }
.psr-leg-i i.done { background: #1D9E75; } .psr-leg-i i.ip { background: #2563EB; } .psr-leg-i i.ns { background: #CBD2DE; }

/* ── Таблица (экран) ── */
.psr-table-wrap { overflow-x: auto; border: 1px solid rgba(99,102,180,.14); border-radius: 14px; background: #fff; box-shadow: 0 4px 14px rgba(15,23,60,.05); }
.psr-table { width: 100%; border-collapse: collapse; font-size: 12px; }
.psr-table thead th { background: #1e2a4a; color: #fff; font-size: 10px; font-weight: 600; letter-spacing: .05em; text-transform: uppercase; text-align: left; padding: 10px 12px; position: sticky; top: 0; z-index: 2; white-space: nowrap; }
.psr-table td { border-bottom: 1px solid rgba(15,23,60,.05); padding: 5px 12px; vertical-align: top; color: var(--t1, #1e2a4a); }
.psr-table tr.is-project { background: rgba(127,119,221,.05); }
.psr-table tr.is-project:hover, .psr-table tbody tr:hover { background: rgba(127,119,221,.09); }
.psr-table tr.is-edited td.c-num { box-shadow: inset 3px 0 0 #EF9F27; }
.c-pick { width: 34px; text-align: center; }
.psr-cb { width: 15px; height: 15px; accent-color: #6C5CE7; cursor: pointer; vertical-align: middle; }
.psr-table tr.is-excluded { opacity: .42; }
.psr-table tr.is-excluded:hover { opacity: .7; }
.psr-table tr.is-excluded .c-pick { opacity: 1; }
.c-num { width: 46px; font-variant-numeric: tabular-nums; color: var(--t3, #8A90A6); font-size: 11px; }
.c-dir { width: 168px; }
.psr-dir-dot { display: inline-block; width: 7px; height: 7px; border-radius: 2px; vertical-align: middle; margin-right: 6px; }
.psr-dir-l { font-size: 11px; font-weight: 500; }
.c-title { min-width: 260px; }
.psr-title-txt { line-height: 1.4; }
.psr-title-txt.proj { font-weight: 600; }
.c-srok { width: 108px; }
.c-status { width: 156px; }
.c-com { min-width: 300px; }
.psr-in { width: 100%; border: 1px solid transparent; background: transparent; font: inherit; color: inherit; border-radius: 6px; padding: 3px 6px; }
.psr-in:hover { background: rgba(127,119,221,.06); }
.psr-in:focus { outline: none; border-color: #7F77DD; background: #fff; }
.psr-pill { position: relative; display: inline-flex; align-items: center; font-size: 11px; font-weight: 600; padding: 3px 10px; border-radius: 999px; white-space: nowrap; cursor: pointer; }
.psr-pill::after { content: "▾"; font-size: 8px; margin-left: 5px; opacity: .55; }
.psr-pill-sel { position: absolute; inset: 0; opacity: 0; cursor: pointer; width: 100%; }
.psr-com { display: flex; align-items: flex-start; gap: 7px; }
.psr-health { flex: 0 0 auto; width: 8px; height: 8px; border-radius: 50%; margin-top: 7px; box-shadow: 0 0 0 2px rgba(255,255,255,.7); }
.psr-ta { width: 100%; border: 1px solid transparent; background: transparent; font: inherit; color: inherit; border-radius: 6px; padding: 3px 6px; resize: none; min-height: 26px; line-height: 1.45; font-size: 11.5px; overflow: hidden; }
.psr-ta:hover { background: rgba(127,119,221,.06); }
.psr-ta:focus { outline: none; border-color: #7F77DD; background: #fff; }
.psr-empty { text-align: center; padding: 30px; color: var(--t3, #64748B); font-style: italic; }

/* ── Печатный оверлей ── */
.pdoc-overlay { position: fixed; inset: 0; z-index: 9000; background: #5b5e72; display: flex; flex-direction: column; }
.pdoc-toolbar { display: flex; align-items: center; gap: 10px; padding: 10px 16px; background: #1e2a4a; color: #fff; }
.pdt-title { font-size: 12.5px; font-weight: 600; }
.pdt-sp { flex: 1; }
.pdt-btn { background: #7F77DD; color: #fff; border: none; font: 600 12px inherit; padding: 7px 16px; border-radius: 8px; cursor: pointer; }
.pdt-btn.ghost { background: transparent; border: 1px solid rgba(255,255,255,.3); }
.pdoc-scroll { flex: 1; overflow: auto; padding: 22px; display: flex; justify-content: center; }
.pdoc-sheet.psr-print {
  background: #fff; color: #14171F; width: 297mm; max-width: 100%; min-height: 210mm;
  padding: 9mm 10mm; box-sizing: border-box; box-shadow: 0 10px 40px rgba(0,0,0,.3);
  font-family: var(--font, "Geist Variable", system-ui, sans-serif); font-size: 11px; align-self: flex-start;
}
.psr-print-sum { display: block; margin: 10px 0 12px; font-size: 11px; color: #3A3D48; line-height: 1.5; }
.psr-print-stamp { display: block; color: #8A8C99; font-size: 10px; margin-top: 3px; }
.psr-print-tbl { width: 100%; border-collapse: collapse; }
.psr-print-tbl th { background: #1e2a4a; color: #fff; font-size: 9.5px; font-weight: 700; text-transform: uppercase; letter-spacing: .03em; text-align: left; padding: 6px 7px; border: 1px solid #2a375a; }
.psr-print-tbl td { border: 1px solid #d7d9e0; padding: 4px 7px; vertical-align: top; font-size: 10.5px; line-height: 1.35; }
.psr-print-tbl tr.proj { background: #f3f2fb; }
.psr-print-tbl tr.proj .pt { font-weight: 700; }
.psr-print-tbl .pn { width: 34px; font-variant-numeric: tabular-nums; color: #6A6D7C; }
.psr-print-tbl .pd { width: 132px; color: #5F6270; }
.psr-print-tbl .ps { width: 78px; white-space: nowrap; }
.psr-print-tbl .pst { width: 118px; white-space: nowrap; }
.psr-print-pill { display: inline-block; padding: 2px 9px; border-radius: 999px; font-size: 9.5px; letter-spacing: .01em; }
.psr-print-tbl .pc { color: #3A3D48; }
.psr-print-foot { margin-top: 12px; padding-top: 7px; border-top: 1px solid #E6E7EE; font-size: 9.5px; color: #A1A3AE; text-align: center; }

@media print {
  .pdoc-sheet.psr-print { width: auto; min-height: 0; padding: 0; box-shadow: none; font-size: 10px; -webkit-print-color-adjust: exact; print-color-adjust: exact; }
  .psr-print-tbl tr { break-inside: avoid; page-break-inside: avoid; }
  .psr-print-tbl thead { display: table-header-group; }
}
@media (prefers-reduced-motion: reduce) { .psr-seg-p, .psr-btn { transition: none; } }
</style>
