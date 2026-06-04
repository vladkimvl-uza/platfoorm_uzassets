<script setup lang="ts">
/**
 * CompanyBoardList.vue
 * ─────────────────────────────────────────────────────────────────────
 *
 * Структура (7 колонок):
 *   handle | Название | Направление | Консультант | Статус | Результат | Дедлайн
 *
 * Группировка:
 *   - Project row (bold, font-weight 500) → внутри его tasks
 *   - Orphan tasks (без project_id) — отдельной группой "Без проекта"
 *
 * Onclick:
 *   - Любой row → emit("openEditor", {entity, kind})
 *   - CompanyWorkspace откроет TaskProjectEditor
 *
 * Filters:
 *   - По направлению (chips)
 *   - По статусу (chips)
 *   - "Только просроченные" toggle
 *
 *   init=#7F77DD, new=#94A3B8, active=#378ADD, review=#EF9F27,
 *   done=#1D9E75, quarterly=#A855F7, monthly=#6366F1, ongoing=#06B6D4
 */

import { ref, computed, onMounted, onUnmounted, watch } from "vue";
import { api, isModerationQueued } from "@/api/client";
import { tasksApi, projectsResultApi } from "@/api/tasks";
import { projectsApi } from "@/api/projects";
import { consultantsApi, type ConsultantBrief } from "@/api/consultants";
import { usePermissions } from "@/composables/usePermissions";

const props = defineProps<{
  companyId: string;
  companyName?: string;
  year?: number | null;
}>();

const emit = defineEmits<{
  (e: "openEditor", payload: { id: string; kind: "project" | "task" }): void;
  // Inline-правка применена (статус/направление/консультант/дедлайн) → родитель
  // инвалидирует производные данные (обзор-донат, агрегат консультантов и т.д.)
  (e: "changed"): void;
}>();

// =====================================================================
// State
// =====================================================================

interface ProjectItem {
  id: string;
  num?: string | null;
  title: string;
  status: string;
  direction_id?: string | null;
  direction?: string | null;
  due_date?: string | null;
  start_date?: string | null;
  result_status?: string | null;
  result_at?: string | null;
  consultant_id?: string | null;
  consultant?: any;
  portfolio_year?: number | null;
  is_archived?: boolean;
  extra?: any;
  sort_order?: number;                      // ручной порядок (drag-reorder)
  quarters?: Record<string, any> | null;   // {q1,q2,q3,q4} — для quarterly "N/4"
  // Year-transfer (Phase 13) — added 2026-05-26 for transferBadge()
  linked_year?: number | null;
  linked_project_id?: string | null;
}

interface TaskItem extends ProjectItem {
  project_id?: string | null;
  linked_task_id?: string | null;
}

const projects = ref<ProjectItem[]>([]);
const tasks = ref<TaskItem[]>([]);
const directions = ref<{ id: string; code: string; name_ru: string; name_en?: string }[]>([]);

// Directions metadata — single source of truth = directions store
// (Pack 149: dynamic, replaces former hardcoded DIRS_META).
import { useDirectionsStore } from "@/stores/directions";
const directionsStore = useDirectionsStore();
// Backwards-compat shim: code → {label, color} computed from the store so
// existing call sites (`DIRS_META[code]?.label`) keep working.
const DIRS_META = computed<Record<string, { label: string; color: string }>>(() => {
  const out: Record<string, { label: string; color: string }> = {};
  for (const d of directionsStore.items) {
    out[d.code.toLowerCase()] = { label: d.label, color: d.color };
  }
  return out;
});
function dirLabelFor(code: string | null | undefined): string {
  if (!code) return "Без направления";
  return directionsStore.labelFor(code);
}
function colorForDirCode(code: string | null | undefined): string {
  return directionsStore.colorFor(code);
}
const consultants = ref<ConsultantBrief[]>([]);
const loading = ref(true);
const errorMsg = ref<string | null>(null);

// Filters
const dirFilter = ref<string>("");
const statusFilter = ref<string>("");
const onlyOverdue = ref(false);

// =====================================================================
// Loading
// =====================================================================

async function loadAll() {
  loading.value = true;
  errorMsg.value = null;
  try {
    const yearParam = props.year ? `&portfolio_year=${props.year}` : "";
    const [pRes, tRes, dRes, cRes] = await Promise.all([
      api.get(`/projects?company_id=${props.companyId}&limit=500${yearParam}`),
      api.get(`/tasks?company_id=${props.companyId}&limit=500${yearParam}`),
      api.get(`/directions`).catch(() => ({ data: [] })),
      consultantsApi.list().catch(() => []),
    ]);
    let pData = _arr(pRes.data);
    let tData = _arr(tRes.data);
    if (props.year) {
      const yr = Number(props.year);
      // Projects: только этот год
      pData = pData.filter((x: any) => Number(x.portfolio_year) === yr);
      // Tasks: оставляем если (a) их год = yr, (b) их project в этом году, (c) num совпадает с проектом этого года
      const projIds = new Set(pData.map((p: any) => p.id));
      const projNums = new Set(pData.map((p: any) => String(p.num || "").replace(/\.+$/, "").trim()).filter(Boolean));
      tData = tData.filter((x: any) => {
        if (Number(x.portfolio_year) === yr) return true;
        if (x.project_id && projIds.has(x.project_id)) return true;
        const tNum = String(x.num || "").replace(/\.+$/, "").trim();
        if (tNum) {
          const prefix = tNum.split(".")[0];
          if (projNums.has(prefix)) return true;
        }
        return false;
      });
    }
    projects.value = pData;
    tasks.value = tData;
    directions.value = _arr(dRes.data);
    consultants.value = _arr(cRes);
  } catch (e: any) {
    errorMsg.value = e?.response?.data?.detail || e?.message || "Ошибка загрузки";
  } finally {
    loading.value = false;
  }
}

function _arr(v: any): any[] {
  if (Array.isArray(v)) return v;
  if (v?.items && Array.isArray(v.items)) return v.items;
  if (v?.data && Array.isArray(v.data)) return v.data;
  return [];
}

onMounted(() => {
  directionsStore.ensureLoaded();
  loadAll();
});
watch(() => [props.companyId, props.year], loadAll);

defineExpose({ reload: loadAll });

// =====================================================================
// Helpers
// =====================================================================

function isOverdue(t: ProjectItem | TaskItem): boolean {
  if (!t.due_date) return false;
  if (t.status === "done") return false;
  const exclTaskStatus = ["quarterly", "monthly", "ongoing"];
  if (exclTaskStatus.includes(t.status)) return false;
  const d = new Date(t.due_date);
  return d.getTime() < Date.now();
}

function fmtDate(s: string | null | undefined): string {
  if (!s) return "";
  try {
    const d = new Date(s);
    const dd = String(d.getDate()).padStart(2, "0");
    const mm = String(d.getMonth() + 1).padStart(2, "0");
    return `${dd}.${mm}.${d.getFullYear()}`;
  } catch {
    return String(s);
  }
}

interface StatusMeta {
  dot: string;
  label: string;
}
const STATUS_META: Record<string, StatusMeta> = {
  init: { dot: "#7F77DD", label: "Инициировано" },
  new: { dot: "#94A3B8", label: "Не начато" },
  active: { dot: "#378ADD", label: "В процессе" },
  review: { dot: "#EF9F27", label: "На согласовании" },
  done: { dot: "#1D9E75", label: "Завершено" },
  quarterly: { dot: "#A855F7", label: "Ежеквартально" },
  monthly: { dot: "#6366F1", label: "Ежемесячно" },
  ongoing: { dot: "#06B6D4", label: "Постоянно" },
};

function statusMeta(s: string): StatusMeta {
  return STATUS_META[s] || { dot: "#94A3B8", label: s || "—" };
}

/** Кол-во закрытых кварталов для status='quarterly' (семантика как в редакторе:
 * квартал закрыт если q.qN truthy — boolean true или непустой объект). */
function quartersClosed(item: { quarters?: Record<string, any> | null }): number {
  const q = item?.quarters;
  if (!q || typeof q !== "object") return 0;
  let n = 0;
  for (const k of ["q1", "q2", "q3", "q4"]) {
    const v = (q as any)[k];
    if (v && (typeof v !== "object" || v.fact || v.done || v.closed)) n++;
  }
  return n;
}

/** Binary "результат": есть (result_at != null) или нет.
 * Alert когда status='done' и нет результата.
 */
function hasResult(item: { result_at?: string | null }): boolean {
  return !!item?.result_at;
}
function needsResultAlert(item: { status?: string; result_at?: string | null }): boolean {
  return item?.status === "done" && !item?.result_at;
}

// =====================================================================
// Inline-edit (status / direction / consultant / deadline) — прямо из строки
// RBAC: tasks.edit (бэк гейтит PATCH + пишет историю/модерацию). Один
// плавающий popover на всю таблицу — клик по ячейке открывает выбор.
// =====================================================================
const rowsPerm = usePermissions("tasks");
const canEditRows = computed(() => rowsPerm.canEdit.value);

type EditField = "status" | "direction" | "consultant" | "due";
interface EditPopover {
  id: string;
  kind: "project" | "task";
  field: EditField;
  x: number;
  y: number;
  current: any;
}
const pop = ref<EditPopover | null>(null);
const savingCell = ref(false);

function startEdit(ev: MouseEvent, kind: "project" | "task", id: string, field: EditField, current: any): void {
  if (!canEditRows.value) return;   // read-only: клик всплывает → откроется строка
  ev.stopPropagation();
  if (pop.value && pop.value.id === id && pop.value.field === field) { pop.value = null; return; }
  const el = ev.currentTarget as HTMLElement;
  const r = el.getBoundingClientRect();
  // Позиция под ячейкой, с клампом по правому/нижнему краю вьюпорта.
  const W = field === "due" ? 230 : 240;
  const x = Math.min(r.left, window.innerWidth - W - 12);
  const y = Math.min(r.bottom + 4, window.innerHeight - 320);
  pop.value = { id, kind, field, x: Math.max(8, x), y: Math.max(8, y), current };
}
function closePop(): void { pop.value = null; }

function _localRow(kind: "project" | "task", id: string): any {
  const list = kind === "task" ? tasks.value : projects.value;
  return list.find((x) => String(x.id) === String(id));
}

async function saveField(field: EditField, value: any): Promise<void> {
  if (!pop.value) return;
  const { kind, id } = pop.value;
  const payload: Record<string, any> = {};
  if (field === "status") payload.status = value;
  else if (field === "direction") payload.direction = value || null;
  else if (field === "consultant") payload.consultant = value || null;
  else if (field === "due") payload.due_date = value || null;
  savingCell.value = true;
  try {
    const res = kind === "task"
      ? await tasksApi.update(id, payload as any)
      : await projectsApi.update(id, payload as any);
    const row = _localRow(kind, id);
    if (row && !isModerationQueued(res)) {
      if (field === "status") row.status = value;
      else if (field === "direction") { row.direction = value || null; row.direction_id = null; }
      else if (field === "consultant") row.consultant = value || null;
      else if (field === "due") row.due_date = value || null;
      emit("changed");   // → родитель обновит производные вью (консультанты/обзор)
    }
    // если 202 (на модерацию) — локально НЕ трогаем, значение применится после аппрува
  } catch (e: any) {
    alert(e?.response?.data?.detail || e?.message || "Не удалось сохранить");
  } finally {
    savingCell.value = false;
    pop.value = null;
  }
}

function onDueInput(ev: Event): void {
  const v = (ev.target as HTMLInputElement).value;  // yyyy-mm-dd | ""
  saveField("due", v || null);
}
function _dueInputValue(iso: string | null | undefined): string {
  if (!iso) return "";
  try { return new Date(iso).toISOString().slice(0, 10); } catch { return ""; }
}

// =====================================================================
// Drag-reorder (ручной перенос строк через ручку ⋮⋮)
// Проекты переставляются между собой; задачи — внутри своей группы
// (один project_id или «без проекта»). Порядок персистится в sort_order
// через обычный PATCH (sequential 10,20,30…), затем computed groups
// пересортировывает строки. RBAC: tasks.edit (как inline-правки).
// =====================================================================
const dragItem = ref<{ kind: "project" | "task"; id: string; groupKey: string } | null>(null);
const dragOverKey = ref<string | null>(null);
const reordering = ref(false);

function taskGroupKey(t: { project_id?: string | null }): string {
  return t.project_id ? `p:${t.project_id}` : "__orphan__";
}

function onRowDragStart(kind: "project" | "task", id: string, groupKey: string, ev: DragEvent): void {
  if (!canEditRows.value) { ev.preventDefault(); return; }
  dragItem.value = { kind, id, groupKey };
  if (ev.dataTransfer) {
    ev.dataTransfer.effectAllowed = "move";
    try { ev.dataTransfer.setData("text/plain", id); } catch { /* ie */ }
  }
}
function onRowDragEnd(): void {
  dragItem.value = null;
  dragOverKey.value = null;
}
function _canDrop(kind: "project" | "task", groupKey: string): boolean {
  const d = dragItem.value;
  return !!d && d.kind === kind && d.groupKey === groupKey;
}
function onRowDragOver(kind: "project" | "task", id: string, groupKey: string, ev: DragEvent): void {
  if (!_canDrop(kind, groupKey)) return;
  ev.preventDefault();
  if (ev.dataTransfer) ev.dataTransfer.dropEffect = "move";
  dragOverKey.value = `${kind}:${id}`;
}
function onRowDragLeave(kind: "project" | "task", id: string): void {
  if (dragOverKey.value === `${kind}:${id}`) dragOverKey.value = null;
}
function onRowDrop(kind: "project" | "task", targetId: string, groupKey: string, ev: DragEvent): void {
  ev.preventDefault();
  const d = dragItem.value;
  dragOverKey.value = null;
  dragItem.value = null;
  if (!d || d.kind !== kind || d.groupKey !== groupKey || d.id === targetId) return;
  void _reorderWithin(kind, groupKey, d.id, targetId);
}

function _siblings(kind: "project" | "task", groupKey: string): any[] {
  if (kind === "project") {
    return groups.value.map((g) => g.project).filter(Boolean) as ProjectItem[];
  }
  const g = groups.value.find(
    (gr) => (gr.project ? `p:${gr.project.id}` : "__orphan__") === groupKey,
  );
  return g ? [...g.tasks] : [];
}

async function _reorderWithin(
  kind: "project" | "task", groupKey: string, dragId: string, targetId: string,
): Promise<void> {
  const sibs = _siblings(kind, groupKey);
  const fromIdx = sibs.findIndex((x) => String(x.id) === String(dragId));
  const toIdx = sibs.findIndex((x) => String(x.id) === String(targetId));
  if (fromIdx < 0 || toIdx < 0) return;
  const [moved] = sibs.splice(fromIdx, 1);
  sibs.splice(toIdx, 0, moved);

  // Sequential sort_order; пишем только изменившиеся.
  const changed: { id: string; sort_order: number }[] = [];
  sibs.forEach((x, i) => {
    const newOrder = (i + 1) * 10;
    if (Number(x.sort_order || 0) !== newOrder) {
      x.sort_order = newOrder;   // реактивно → groups пересортирует
      changed.push({ id: String(x.id), sort_order: newOrder });
    }
  });
  if (!changed.length) return;

  reordering.value = true;
  try {
    await Promise.all(
      changed.map((c) =>
        kind === "task"
          ? tasksApi.update(c.id, { sort_order: c.sort_order } as any)
          : projectsApi.update(c.id, { sort_order: c.sort_order } as any),
      ),
    );
    emit("changed");
  } catch (e) {
    // рассинхрон → перечитываем с сервера
    await loadAll();
  } finally {
    reordering.value = false;
  }
}

// Опции для popover
const consultantOptions = computed(() =>
  consultants.value.map((c: any) => ({
    code: c.code || c.abbr || c.name_ru,
    label: c.name_ru || c.abbr || c.code,
    abbr: c.abbr || (c.name_ru || "").slice(0, 6),
    color: c.color_hex || c.color || "#7F77DD",
  })),
);
const directionOptions = computed(() =>
  directionsStore.items.map((d: any) => ({ code: d.code.toLowerCase(), label: d.label, color: d.color })),
);

// Закрытие popover по Escape / скроллу таблицы
function _onKey(e: KeyboardEvent): void { if (e.key === "Escape") closePop(); }
onMounted(() => window.addEventListener("keydown", _onKey));
onUnmounted(() => window.removeEventListener("keydown", _onKey));

async function onToggleResult(kind: "task" | "project", id: string) {
  try {
    const resp = kind === "task"
      ? await tasksApi.toggleResult(id)
      : await projectsResultApi.toggle(id);
    // Optimistic update — patch the corresponding row in projects/tasks.
    const list = kind === "task" ? tasks.value : projects.value;
    const idx = list.findIndex((x) => String(x.id) === String(id));
    if (idx >= 0) {
      (list[idx] as any).result_at = resp.result_at;
    }
  } catch (e: any) {
    console.warn("[result] toggle failed", e);
    const msg = e?.response?.data?.detail || "Не удалось переключить результат";
    alert(msg);
  }
}

function directionInfo(t: ProjectItem | TaskItem): { label: string; color: string } | null {
  const code = (t as any).direction || ((t as any).direction_meta && (t as any).direction_meta.code) || null;
  if (code) {
    const codeStr = String(code).toLowerCase();
    const d = directions.value.find((x) => x.code === codeStr);
    const label = DIRS_META.value[codeStr]?.label || d?.name_ru || codeStr;
    return { label, color: colorForDirCode(codeStr) };
  }
  if ((t as any).direction_id) {
    const d = directions.value.find((x) => x.id === (t as any).direction_id);
    if (d) {
      const codeStr = String(d.code || "").toLowerCase();
      return {
        label: DIRS_META.value[codeStr]?.label || d.name_ru || d.code,
        color: colorForDirCode(codeStr),
      };
    }
  }
  return null;
}

// Carry-over badge — single semantic (post-migration 2026-05-26):
// linked_year = source year ("я пришла оттуда"). Если есть linked_year,
// показываем "← FY25". Если есть только linked_task_id / linked_project_id
// без linked_year — текущая запись является SOURCE → "↗" (уйдёт в FY+1).
function transferBadge(t: any): { text: string; tone: "from" | "to"; year: number | null } | null {
  const ly = t.linked_year;
  const py = t.portfolio_year;
  if (ly) {
    // Направленный бейдж: linked_year > текущего года → перенесён ВПЕРЁД («→ FY26»);
    // меньше → пришёл ИЗ прошлого («← FY25»).
    if (py != null && Number(ly) > Number(py)) {
      return { text: `→ FY${String(ly).slice(-2)}`, tone: "to", year: ly };
    }
    return { text: `← FY${String(ly).slice(-2)}`, tone: "from", year: ly };
  }
  // Сторона-цель без собственного linked_year: вычисленный reverse-link с бэка.
  if (t.carried_from_year) {
    return { text: `← FY${String(t.carried_from_year).slice(-2)}`, tone: "from", year: t.carried_from_year };
  }
  if (t.linked_task_id || t.linked_project_id) {
    return { text: "↗", tone: "to", year: null };
  }
  return null;
}

function consultantBadgeData(t: ProjectItem | TaskItem): any | null {
  // Backend возвращает поле consultant: string | list | null (готовое из extra)
  const raw: any = (t as any).consultant;
  if (!raw) return null;
  const code: string = Array.isArray(raw) ? (raw[0] || "") : String(raw);
  if (!code || !code.trim()) return null;
  // Поиск по code, abbr (case-insensitive), name_ru
  const lc = code.toLowerCase().trim();
  const c: any = consultants.value.find((x: any) =>
    (x.code && x.code.toLowerCase() === lc) ||
    (x.abbr && x.abbr.toLowerCase() === lc) ||
    (x.name_ru && x.name_ru.toLowerCase() === lc)
  );
  if (c) return c;
  // Не нашли -- возвращаем "minimal" объект чтобы badge показал хотя бы текст
  return { abbr: code.toUpperCase().slice(0, 6), name_ru: code, color_hex: "#7F77DD" };
}

// =====================================================================
// Filtering + grouping
// =====================================================================

const filteredProjects = computed(() => {
  return projects.value.filter((p) => _passes(p));
});

const filteredTasks = computed(() => {
  return tasks.value.filter((t) => _passes(t));
});

function _passes(t: ProjectItem | TaskItem): boolean {
  if (t.is_archived) return false;
  if (dirFilter.value) {
    const raw = t.direction || (t.extra && (t.extra as any).direction) || "";
    // Use the same normalization as dirChipsData so a legacy free-text
    // direction matches the canonical chip code.
    const code = _normalizeDirection(raw) || "";
    if (code !== dirFilter.value) return false;
  }
  if (statusFilter.value === "overdue") {
    if (!isOverdue(t)) return false;
  } else if (statusFilter.value) {
    if (t.status !== statusFilter.value) return false;
  }
  if (onlyOverdue.value && !isOverdue(t)) return false;
  return true;
}

interface Group {
  project: ProjectItem | null;
  tasks: TaskItem[];
}

// Сортировка строк: сначала ручной sort_order (drag-reorder), затем num.
function _ord(x: { sort_order?: number; num?: any }): number {
  return Number(x?.sort_order) || 0;
}
function _bySortThenNum(a: { sort_order?: number; num?: any }, b: { sort_order?: number; num?: any }): number {
  const d = _ord(a) - _ord(b);
  if (d !== 0) return d;
  return String(a.num || "").localeCompare(String(b.num || ""), "en", { numeric: true });
}

const groups = computed<Group[]>(() => {
  const out: Group[] = [];
  const sortedProjects = [...filteredProjects.value].sort(_bySortThenNum);
  const normNum = (n: any) => String(n || "").replace(/\.+$/, "").trim();
  const claimed = new Set<string>();
  for (const p of sortedProjects) {
    const pId = String((p as any).id || "");
    const pNum = normNum((p as any).num);
    const nested = filteredTasks.value.filter((t) => {
      // 1) FK match (с защитой от UUID-vs-string)
      const tPid = String((t as any).project_id || "");
      if (tPid && pId && tPid === pId) return true;
      // 2) num prefix fallback
      const tNum = normNum((t as any).num);
      if (!pNum || !tNum) return false;
      return tNum.startsWith(pNum + ".");
    });
    nested.sort(_bySortThenNum);
    nested.forEach((t) => claimed.add(String((t as any).id)));
    out.push({ project: p, tasks: nested });
  }
  const orphans = filteredTasks.value.filter((t) => !claimed.has(String((t as any).id)));
  if (orphans.length > 0) {
    orphans.sort(_bySortThenNum);
    out.push({ project: null, tasks: orphans });
  }
  return out;
});

// Counters for chips
const counts = computed(() => {
  const all = [...projects.value, ...tasks.value].filter((x) => !x.is_archived);
  const c: Record<string, number> = {};
  for (const s of Object.keys(STATUS_META)) {
    c[s] = all.filter((x) => x.status === s).length;
  }
  c["overdue"] = all.filter(isOverdue).length;
  c["all"] = all.length;
  return c;
});

// Reverse-lookup table: human label → canonical code.
// Reactive label→code lookup (recomputes when directions store updates).
const _LABEL_TO_CODE = computed<Record<string, string>>(() => {
  const out: Record<string, string> = {};
  for (const [code, meta] of Object.entries(DIRS_META.value)) {
    if (meta?.label) out[String(meta.label).trim().toLowerCase()] = code;
  }
  return out;
});

/** Normalize any raw direction value (code OR label OR free-text) to the
 * canonical code. Falls back to the lowercased input if no match. */
function _normalizeDirection(raw: string | null | undefined): string | null {
  if (!raw) return null;
  const s = String(raw).trim();
  if (!s) return null;
  const low = s.toLowerCase();
  if (DIRS_META.value[low]) return low;             // exact code match
  if (_LABEL_TO_CODE.value[low]) return _LABEL_TO_CODE.value[low];  // label match
  // Backend directions list (loaded async) — try to match against codes
  const d = directions.value.find(
    (x) => x.code?.toLowerCase() === low ||
           (x.name_ru || "").toLowerCase() === low,
  );
  return d?.code?.toLowerCase() || low;
}

const dirChipsData = computed(() => {
  const all = [...projects.value, ...tasks.value].filter((x) => !x.is_archived);
  const map = new Map<string, number>();
  for (const t of all) {
    const raw = t.direction || (t.extra && (t.extra as any).direction) || null;
    const code = _normalizeDirection(raw);
    if (!code) continue;
    map.set(code, (map.get(code) || 0) + 1);
  }
  return Array.from(map.entries()).map(([code, count]) => ({
    code,
    count,
    label: dirLabelFor(code),
    color: colorForDirCode(code),
  }));
});

// =====================================================================
// Click handlers
// =====================================================================

function openProject(p: ProjectItem) {
  emit("openEditor", { id: p.id, kind: "project" });
}
function openTask(t: TaskItem) {
  emit("openEditor", { id: t.id, kind: "task" });
}

function clearFilters() {
  dirFilter.value = "";
  statusFilter.value = "";
  onlyOverdue.value = false;
}
</script>

<template>
  <div class="bl-root">
    <!-- ═══ FILTERS ═══ -->
    <div class="bl-filters">
      <!-- Direction chips row -->
      <div v-if="dirChipsData.length" class="bl-chip-row">
        <span class="bl-chip-row-label">Направление</span>
        <div class="bl-chips">
          <button
            class="bl-chip"
            :class="{ active: !dirFilter }"
            @click="dirFilter = ''"
          >
            Все
            <span class="bl-chip-count">{{ counts["all"] || 0 }}</span>
          </button>
          <button
            v-for="d in dirChipsData"
            :key="d.code"
            class="bl-chip"
            :class="{ active: dirFilter === d.code }"
            :style="{ '--chip-color': d.color }"
            @click="dirFilter = dirFilter === d.code ? '' : d.code"
          >
            <span class="bl-chip-dot"></span>
            {{ d.label }}
            <span class="bl-chip-count">{{ d.count }}</span>
          </button>
        </div>
      </div>

      <!-- Status filters row -->
      <div class="bl-chip-row">
        <span class="bl-chip-row-label">Статус</span>
        <div class="bl-chips">
          <button
            class="bl-chip bl-chip-status"
            :class="{ active: statusFilter === 'overdue' }"
            :style="{ '--chip-color': '#E24B4A' }"
            @click="statusFilter = statusFilter === 'overdue' ? '' : 'overdue'"
          >
            <span class="bl-chip-dot"></span>
            Просрочены
            <span class="bl-chip-count">{{ counts["overdue"] || 0 }}</span>
          </button>
          <button
            v-for="(meta, key) in STATUS_META"
            :key="key"
            class="bl-chip bl-chip-status"
            :class="{ active: statusFilter === key }"
            :style="{ '--chip-color': meta.dot }"
            @click="statusFilter = statusFilter === key ? '' : key"
          >
            <span class="bl-chip-dot"></span>
            {{ meta.label }}
            <span class="bl-chip-count">{{ counts[key] || 0 }}</span>
          </button>
          <button v-if="dirFilter || statusFilter" class="bl-clear" @click="clearFilters">
            × Сбросить
          </button>
        </div>
      </div>
    </div>

    <!-- ═══ LOADING / ERROR / EMPTY ═══ -->
    <div v-if="loading" class="bl-state">
      <div class="bl-spinner"></div>
      <span>Загрузка...</span>
    </div>
    <div v-else-if="errorMsg" class="bl-state bl-state-err">
      {{ errorMsg }}
    </div>
    <div v-else-if="groups.length === 0" class="bl-state">
      Нет проектов и задач{{ year ? ` за ${year} год` : "" }}
    </div>

    <div v-else class="bl-list-view">
      <!-- Header -->
      <div class="bl-thead">
        <div></div>
        <div class="bl-th">Название</div>
        <div class="bl-th">Направление</div>
        <div class="bl-th bl-center">Консультант</div>
        <div class="bl-th bl-center">Статус</div>
        <div class="bl-th bl-center">Результат</div>
        <div class="bl-th bl-right">Дедлайн</div>
      </div>

      <!-- Groups -->
      <template v-for="(g, gi) in groups" :key="g.project?.id || `orphan-${gi}`">
        <!-- Project row -->
        <div
          v-if="g.project"
          class="bl-row bl-row-project"
          :class="{ overdue: isOverdue(g.project), 'bl-drop-target': dragOverKey === `project:${g.project.id}`, 'bl-dragging': dragItem?.kind === 'project' && dragItem?.id === g.project.id }"
          @click="openProject(g.project)"
          @dragover="onRowDragOver('project', g.project.id, '__projects__', $event)"
          @dragleave="onRowDragLeave('project', g.project.id)"
          @drop="onRowDrop('project', g.project.id, '__projects__', $event)"
        >
          <div
            class="bl-handle"
            :class="{ 'bl-handle-on': canEditRows }"
            :title="canEditRows ? 'Перетащите, чтобы изменить порядок' : ''"
            :draggable="canEditRows"
            @click.stop
            @dragstart="onRowDragStart('project', g.project.id, '__projects__', $event)"
            @dragend="onRowDragEnd"
          >⋮⋮</div>
          <div class="bl-row-grid">
            <div class="bl-title-cell">
              <span class="bl-num bl-num-project">{{ g.project.num || "" }}</span>
              <span class="bl-title bl-title-project">{{ g.project.title }}</span>
              <span
                v-if="transferBadge(g.project)"
                class="bl-transfer-badge"
                :class="`bl-tb-${transferBadge(g.project)!.tone}`"
                :title="transferBadge(g.project)!.tone === 'from' ? `Перенесён из FY${transferBadge(g.project)!.year}` : `Перенесён на FY${transferBadge(g.project)!.year}`"
              >{{ transferBadge(g.project)!.text }}</span>
            </div>
            <div class="bl-cell-dir" :class="{ 'bl-editable': canEditRows }"
                 @click="startEdit($event, 'project', g.project.id, 'direction', g.project.direction)">
              <span
                v-if="directionInfo(g.project)"
                class="bl-dir-label"
                :style="{ color: directionInfo(g.project)!.color }"
              >
                {{ directionInfo(g.project)!.label }}
              </span>
              <span v-else-if="canEditRows" class="bl-cell-add">+ направление</span>
            </div>
            <div class="bl-cell-cons" :class="{ 'bl-editable': canEditRows }"
                 @click="startEdit($event, 'project', g.project.id, 'consultant', g.project.consultant)">
              <span
                v-if="consultantBadgeData(g.project)"
                class="bl-cons-badge"
                :style="{
                  background: (consultantBadgeData(g.project)!.color_hex || consultantBadgeData(g.project)!.color || '#7F77DD') + '18',
                  color: consultantBadgeData(g.project)!.color_hex || consultantBadgeData(g.project)!.color || '#7F77DD',
                }"
              >
                {{ consultantBadgeData(g.project)!.abbr || consultantBadgeData(g.project)!.name_ru || consultantBadgeData(g.project)!.name }}
              </span>
              <span v-else-if="canEditRows" class="bl-cell-add">+ консультант</span>
            </div>
            <div class="bl-cell-status" :class="{ 'bl-editable': canEditRows }"
                 @click="startEdit($event, 'project', g.project.id, 'status', g.project.status)">
              <span class="bl-status-pill">
                <span class="bl-status-dot" :style="{ background: statusMeta(g.project.status).dot }"></span>
                {{ statusMeta(g.project.status).label }}
                <span v-if="g.project.status === 'quarterly'" class="bl-qcount"
                      :style="{ color: statusMeta('quarterly').dot }">{{ quartersClosed(g.project) }}/4</span>
              </span>
            </div>
            <div class="bl-cell-result">
              <button
                v-if="hasResult(g.project)"
                class="bl-result-on"
                :title="'Результат принят: ' + fmtDate(g.project.result_at)"
                @click.stop="onToggleResult('project', g.project.id)"
              >✓ Принят</button>
              <button
                v-else-if="needsResultAlert(g.project)"
                class="bl-result-alert"
                title="Завершено без результата — нажмите чтобы отметить"
                @click.stop="onToggleResult('project', g.project.id)"
              >⚠ Нужен результат</button>
              <button
                v-else
                class="bl-result-off"
                title="Отметить как принятый"
                @click.stop="onToggleResult('project', g.project.id)"
              >—</button>
            </div>
            <div class="bl-cell-dates" :class="{ 'bl-editable': canEditRows }"
                 @click="startEdit($event, 'project', g.project.id, 'due', g.project.due_date)">
              <div v-if="g.project.start_date || g.project.due_date" class="bl-dates-stack">
                <span v-if="g.project.start_date" class="bl-date-start">
                  {{ fmtDate(g.project.start_date) }}
                </span>
                <span
                  v-if="g.project.due_date"
                  class="bl-date-due"
                  :class="{ overdue: isOverdue(g.project) }"
                >
                  <span v-if="g.project.start_date" class="bl-arrow">→</span>
                  {{ fmtDate(g.project.due_date) }}
                </span>
              </div>
              <span v-else-if="canEditRows" class="bl-cell-add">+ дедлайн</span>
            </div>
          </div>
        </div>

        <div
          v-for="t in g.tasks"
          :key="t.id"
          class="bl-row bl-row-task"
          :class="{ overdue: isOverdue(t), 'bl-row-task-orphan': !g.project, 'bl-drop-target': dragOverKey === `task:${t.id}`, 'bl-dragging': dragItem?.kind === 'task' && dragItem?.id === t.id }"
          @click="openTask(t)"
          @dragover="onRowDragOver('task', t.id, taskGroupKey(t), $event)"
          @dragleave="onRowDragLeave('task', t.id)"
          @drop="onRowDrop('task', t.id, taskGroupKey(t), $event)"
        >
          <div
            class="bl-handle"
            :class="{ 'bl-handle-on': canEditRows }"
            :title="canEditRows ? 'Перетащите, чтобы изменить порядок' : ''"
            :draggable="canEditRows"
            @click.stop
            @dragstart="onRowDragStart('task', t.id, taskGroupKey(t), $event)"
            @dragend="onRowDragEnd"
          >⋮⋮</div>
          <div class="bl-row-grid">
            <div class="bl-title-cell">
              <span class="bl-num">{{ t.num || "" }}</span>
              <span
                class="bl-title"
                :class="{ 'bl-title-orphan': !g.project }"
              >{{ t.title }}</span>
              <span
                v-if="transferBadge(t)"
                class="bl-transfer-badge"
                :class="`bl-tb-${transferBadge(t)!.tone}`"
                :title="transferBadge(t)!.tone === 'from' ? `Перенесена из FY${transferBadge(t)!.year}` : `Перенесена на FY${transferBadge(t)!.year}`"
              >{{ transferBadge(t)!.text }}</span>
            </div>
            <div class="bl-cell-dir" :class="{ 'bl-editable': canEditRows }"
                 @click="startEdit($event, 'task', t.id, 'direction', t.direction)">
              <span
                v-if="directionInfo(t)"
                class="bl-dir-label"
                :style="{ color: directionInfo(t)!.color }"
              >
                {{ directionInfo(t)!.label }}
              </span>
              <span v-else-if="canEditRows" class="bl-cell-add">+ направление</span>
            </div>
            <div class="bl-cell-cons" :class="{ 'bl-editable': canEditRows }"
                 @click="startEdit($event, 'task', t.id, 'consultant', t.consultant)">
              <span
                v-if="consultantBadgeData(t)"
                class="bl-cons-badge"
                :style="{
                  background: (consultantBadgeData(t)!.color_hex || consultantBadgeData(t)!.color || '#7F77DD') + '18',
                  color: consultantBadgeData(t)!.color_hex || consultantBadgeData(t)!.color || '#7F77DD',
                }"
              >
                {{ consultantBadgeData(t)!.abbr || consultantBadgeData(t)!.name_ru || consultantBadgeData(t)!.name }}
              </span>
              <span v-else-if="canEditRows" class="bl-cell-add">+ консультант</span>
            </div>
            <div class="bl-cell-status" :class="{ 'bl-editable': canEditRows }"
                 @click="startEdit($event, 'task', t.id, 'status', t.status)">
              <span class="bl-status-pill">
                <span class="bl-status-dot" :style="{ background: statusMeta(t.status).dot }"></span>
                {{ statusMeta(t.status).label }}
                <span v-if="t.status === 'quarterly'" class="bl-qcount"
                      :style="{ color: statusMeta('quarterly').dot }">{{ quartersClosed(t) }}/4</span>
              </span>
            </div>
            <div class="bl-cell-result">
              <button
                v-if="hasResult(t)"
                class="bl-result-on"
                :title="'Результат принят: ' + fmtDate(t.result_at)"
                @click.stop="onToggleResult('task', t.id)"
              >✓ Принят</button>
              <button
                v-else-if="needsResultAlert(t)"
                class="bl-result-alert"
                title="Завершено без результата — нажмите чтобы отметить"
                @click.stop="onToggleResult('task', t.id)"
              >⚠ Нужен результат</button>
              <button
                v-else
                class="bl-result-off"
                title="Отметить как принятый"
                @click.stop="onToggleResult('task', t.id)"
              >—</button>
            </div>
            <div class="bl-cell-dates" :class="{ 'bl-editable': canEditRows }"
                 @click="startEdit($event, 'task', t.id, 'due', t.due_date)">
              <div v-if="t.start_date || t.due_date" class="bl-dates-stack">
                <span v-if="t.start_date" class="bl-date-start">{{ fmtDate(t.start_date) }}</span>
                <span v-if="t.due_date" class="bl-date-due" :class="{ overdue: isOverdue(t) }">
                  <span v-if="t.start_date" class="bl-arrow">→</span>
                  {{ fmtDate(t.due_date) }}
                </span>
              </div>
              <span v-else-if="canEditRows" class="bl-cell-add">+ дедлайн</span>
            </div>
          </div>
        </div>
      </template>
    </div>

    <!-- ═══ INLINE-EDIT POPOVER (status / direction / consultant / deadline) ═══ -->
    <template v-if="pop">
      <div class="bl-pop-backdrop" @click="closePop"></div>
      <div class="bl-pop" :style="{ left: pop.x + 'px', top: pop.y + 'px' }" @click.stop>
        <div class="bl-pop-saving" v-if="savingCell"><span class="bl-spinner bl-spinner-sm"></span></div>

        <!-- STATUS -->
        <template v-if="pop.field === 'status'">
          <div class="bl-pop-head">Статус</div>
          <button
            v-for="(m, key) in STATUS_META"
            :key="key"
            class="bl-pop-opt"
            :class="{ on: pop.current === key }"
            @click="saveField('status', key)"
          >
            <span class="bl-status-dot" :style="{ background: m.dot }"></span>
            <span class="bl-pop-opt-label">{{ m.label }}</span>
            <span v-if="pop.current === key" class="bl-pop-check">✓</span>
          </button>
        </template>

        <!-- DIRECTION -->
        <template v-else-if="pop.field === 'direction'">
          <div class="bl-pop-head">Направление</div>
          <div class="bl-pop-scroll">
            <button class="bl-pop-opt" :class="{ on: !pop.current }" @click="saveField('direction', '')">
              <span class="bl-status-dot" style="background:#CBD5E1"></span>
              <span class="bl-pop-opt-label">Без направления</span>
            </button>
            <button
              v-for="d in directionOptions"
              :key="d.code"
              class="bl-pop-opt"
              :class="{ on: String(pop.current).toLowerCase() === d.code }"
              @click="saveField('direction', d.code)"
            >
              <span class="bl-status-dot" :style="{ background: d.color }"></span>
              <span class="bl-pop-opt-label">{{ d.label }}</span>
              <span v-if="String(pop.current).toLowerCase() === d.code" class="bl-pop-check">✓</span>
            </button>
          </div>
        </template>

        <!-- CONSULTANT -->
        <template v-else-if="pop.field === 'consultant'">
          <div class="bl-pop-head">Консультант</div>
          <div class="bl-pop-scroll">
            <button class="bl-pop-opt" :class="{ on: !pop.current }" @click="saveField('consultant', '')">
              <span class="bl-status-dot" style="background:#CBD5E1"></span>
              <span class="bl-pop-opt-label">Убрать</span>
            </button>
            <button
              v-for="c in consultantOptions"
              :key="c.code"
              class="bl-pop-opt"
              :class="{ on: String(pop.current).toLowerCase() === String(c.code).toLowerCase() }"
              @click="saveField('consultant', c.code)"
            >
              <span class="bl-cons-badge bl-pop-cons" :style="{ background: c.color + '18', color: c.color }">{{ c.abbr }}</span>
              <span class="bl-pop-opt-label">{{ c.label }}</span>
            </button>
          </div>
        </template>

        <!-- DEADLINE -->
        <template v-else-if="pop.field === 'due'">
          <div class="bl-pop-head">Дедлайн</div>
          <input type="date" class="bl-pop-date" :value="_dueInputValue(pop.current)" @change="onDueInput" @click.stop />
          <button v-if="pop.current" class="bl-pop-opt bl-pop-clear" @click="saveField('due', null)">Очистить дату</button>
        </template>
      </div>
    </template>
  </div>
</template>

<style scoped>
/* ═══════════════════════════════════════════════════════════════ */
.bl-root {
  display: flex;
  flex-direction: column;
  gap: 12px;
  padding: 16px 0;
}

/* ─── Filters ─── */
.bl-filters {
  display: flex;
  flex-direction: column;
  gap: 5px;
  padding: 8px 12px;
  background: rgba(127, 119, 221, 0.04);
  border: 1px solid rgba(30, 42, 74, 0.06);
  border-radius: 10px;
}
.bl-chip-row {
  display: flex;
  align-items: flex-start;
  gap: 10px;
}
.bl-chip-row-label {
  flex-shrink: 0;
  width: 84px;
  font-size: 9.5px;
  font-weight: 500;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  color: var(--t3, var(--t-muted));
  padding: 5px 0;
  line-height: 1;
}
.bl-chips {
  display: flex;
  flex-wrap: wrap;
  gap: 5px;
  flex: 1;
  min-width: 0;
}
.bl-chip {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  padding: 3px 9px;
  border-radius: 9px;
  border: 0.5px solid rgba(30, 42, 74, 0.10);
  background: white;
  font-size: 11.5px;
  font-weight: 500;
  color: var(--t1, #1E2A4A);
  cursor: pointer;
  transition: all 0.18s var(--ease-standard);
  white-space: nowrap;
  --chip-color: #94A3B8;
}
.bl-chip:hover {
  border-color: var(--chip-color);
  transform: translateY(-1px);
}
.bl-chip.active {
  background: var(--chip-color);
  color: white;
  border-color: var(--chip-color);
}
.bl-chip.active .bl-chip-count {
  background: rgba(255, 255, 255, 0.22);
  color: white;
}
.bl-chip-dot {
  width: 5px;
  height: 5px;
  border-radius: 50%;
  background: var(--chip-color);
  flex-shrink: 0;
}
.bl-chip.active .bl-chip-dot {
  background: white;
}
.bl-chip-count {
  font-size: 10.5px;
  background: rgba(30, 42, 74, 0.06);
  padding: 1px 6px;
  border-radius: 7px;
  font-variant-numeric: tabular-nums;
  color: rgba(30, 42, 74, 0.65);
}
.bl-clear {
  margin-left: auto;
  background: transparent;
  border: none;
  color: rgba(30, 42, 74, 0.55);
  cursor: pointer;
  font-size: 12px;
  font-weight: 500;
  padding: 4px 8px;
  border-radius: 7px;
  transition: background 0.15s ease;
}
.bl-clear:hover {
  background: rgba(30, 42, 74, 0.06);
  color: var(--t1, #1E2A4A);
}

/* ─── Loading / empty ─── */
.bl-state {
  padding: 40px 16px;
  text-align: center;
  color: rgba(30, 42, 74, 0.5);
  font-size: 13px;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 10px;
}
.bl-state-err {
  color: var(--sev-high);
}
.bl-spinner {
  width: 18px;
  height: 18px;
  border: 2px solid rgba(127, 119, 221, 0.18);
  border-top-color: #7F77DD;
  border-radius: 50%;
  animation: blSpin 0.8s linear infinite;
}
@keyframes blSpin {
  to { transform: rotate(360deg); }
}

/* ═══════════════════════════════════════════════════════════════ */
/* ═══════════════════════════════════════════════════════════════ */
.bl-list-view {
  padding: 0 0 32px;
  flex: 1;
}

/* Header — sticky на верх scroll-контейнера */
.bl-thead {
  display: grid;
  grid-template-columns: 18px 1fr 170px 100px 140px 120px 110px;
  gap: 0 8px;
  align-items: center;
  padding: 8px 16px 7px 14px;
  border-bottom: 1.5px solid rgba(30, 42, 74, 0.10);
  position: sticky;
  top: 0;
  z-index: 10;
  background: rgba(248, 250, 252, 0.95);
  backdrop-filter: blur(8px);
}
.bl-th {
  font-size: 11px;
  font-weight: 700;
  color: rgba(30, 42, 74, 0.55);
  text-transform: uppercase;
  letter-spacing: 0.06em;
  white-space: nowrap;
}
.bl-center { text-align: center; }
.bl-right { text-align: right; }

/* Row — flex (handle + grid) */
.bl-row {
  display: flex;
  align-items: center;
  cursor: pointer;
  position: relative;
  transition: background 0.15s, box-shadow 0.15s, border-color 0.15s;
}

/* Project — выделенный premium-look */
.bl-row-project {
  padding: 9px 16px 9px 14px;
  background: rgba(246, 244, 255, 0.80);
  backdrop-filter: blur(6px);
  border-radius: 0 12px 12px 0;
  margin: 3px 0 1px;
  box-shadow:
    0 1px 4px rgba(124, 111, 247, 0.08),
    0 0 0 0.5px rgba(124, 111, 247, 0.10) inset;
  /* top-stripe via .bl-row::before (см. правило ниже) */
  --bl-accent: #7F77DD;
}
.bl-row-project:hover {
  background: rgba(246, 244, 255, 0.95);
  box-shadow: 0 3px 12px rgba(124, 111, 247, 0.15);
}

/* Task — лёгкий полупрозрачный белый */
.bl-row-task {
  padding: 6px 16px 6px 14px;
  background: rgba(255, 255, 255, 0.60);
  margin: 0;
  border-radius: 0;
  --bl-accent: rgba(124, 111, 247, 0.18);
}
.bl-row-task:hover {
  background: rgba(255, 255, 255, 0.90);
  --bl-accent: rgba(124, 111, 247, 0.35);
}
.bl-row-task:last-of-type {
  border-radius: 0 0 0 4px;
}

/* Overdue marker — красный акцент перекрывает обычный */
.bl-row.overdue {
  --bl-accent: var(--sev-high) !important;
}

/* Top-stripe accent removed per user request 2026-05-25 —
   ранее `.bl-row::before` рисовал горизонтальную полосу сверху каждой
   строки (var(--bl-accent)). Скрыто как визуальный шум. */

/* Drag handle — 18px, hidden by default, visible on row hover */
.bl-handle {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 18px;
  flex-shrink: 0;
  cursor: grab;
  color: rgba(99, 102, 180, 0.35);
  opacity: 0;
  transition: opacity 0.15s;
  font-size: 13px;
  letter-spacing: -0.5px;
  padding: 0 2px;
  user-select: none;
}
.bl-row:hover .bl-handle {
  opacity: 1;
}
.bl-handle:active {
  cursor: grabbing;
}
/* Только при наличии прав строка реально таскается */
.bl-handle-on { cursor: grab; }
.bl-handle-on:active { cursor: grabbing; }

/* Подсветка строки-цели при drop */
.bl-row.bl-drop-target {
  box-shadow: inset 0 2px 0 0 #7F77DD, 0 3px 12px rgba(124, 111, 247, 0.20);
}
.bl-row.bl-drop-target::after {
  content: "";
  position: absolute;
  left: 0; right: 0; top: -1px;
  height: 2px;
  background: #7F77DD;
  border-radius: 2px;
}
/* Перетаскиваемая строка — приглушена */
.bl-row.bl-dragging {
  opacity: 0.45;
}

/* Inner 6-cell grid (без слота для handle) */
.bl-row-grid {
  display: grid;
  grid-template-columns: 1fr 170px 100px 140px 120px 110px;
  gap: 0 8px;
  align-items: center;
  flex: 1;
  min-width: 0;
}

/* Title cell */
.bl-title-cell {
  display: flex;
  align-items: center;
  gap: 7px;
  min-width: 0;
}
.bl-num {
  font-size: 11px;
  font-weight: 500;
  color: rgba(30, 42, 74, 0.45);
  font-variant-numeric: tabular-nums;
  flex-shrink: 0;
  min-width: 22px;
}
.bl-num-project {
  color: var(--t3, #94A3B8);
}
.bl-title {
  font-size: 13px;
  color: rgba(30, 42, 74, 0.75);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  min-width: 0;
}
.bl-title-project {
  font-weight: 700;
  color: var(--t1, #1E2A4A);
  letter-spacing: -0.015em;
}
.bl-title-orphan {
  color: var(--t1, #1E2A4A);
}

/* Transfer badge (carry-over marker) — inline после title */
.bl-transfer-badge {
  flex-shrink: 0;
  display: inline-flex;
  align-items: center;
  font-size: 9.5px;
  font-weight: 700;
  padding: 1.5px 6px;
  border-radius: 4px;
  white-space: nowrap;
  letter-spacing: 0.02em;
  font-variant-numeric: tabular-nums;
  border: 0.5px solid transparent;
  margin-left: 2px;
}
.bl-tb-from {
  background: rgba(239, 159, 39, .14);
  color: #B87600;
  border-color: rgba(239, 159, 39, .35);
}
.bl-tb-to {
  background: rgba(127, 119, 221, .14);
  color: var(--p-deep);
  border-color: rgba(127, 119, 221, .35);
}

/* Direction label */
.bl-cell-dir {
  display: flex;
  align-items: center;
  min-width: 0;
}
.bl-dir-label {
  font-size: 12px;
  font-weight: 600;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.bl-cell-cons {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 3px;
}
.bl-cons-badge {
  font-size: 11px;
  font-weight: 700;
  padding: 2px 6px;
  border-radius: 4px;
  white-space: nowrap;
}

/* Status / Result pill */
.bl-cell-status,
.bl-cell-result {
  display: flex;
  align-items: center;
  justify-content: center;
}
.bl-status-pill,
.bl-result-pill {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: 11.5px;
  font-weight: 500;
  color: rgba(30, 42, 74, 0.7);
  white-space: nowrap;
}

/* Binary "результат" buttons */
.bl-result-on, .bl-result-off, .bl-result-alert {
  display: inline-flex; align-items: center; gap: 4px;
  padding: 3px 9px; border-radius: 10px;
  font-size: 11px; font-weight: 500;
  border: 0.5px solid transparent;
  cursor: pointer; font-family: inherit;
  transition: filter .12s, background .12s;
}
.bl-result-on {
  background: rgba(29, 158, 117, .12);
  color: #0F6E56;
  border-color: rgba(29, 158, 117, .22);
}
.bl-result-on:hover { filter: brightness(.95); }
.bl-result-off {
  background: transparent;
  color: var(--t3, var(--t-muted));
  border-color: rgba(30, 42, 74, .10);
}
.bl-result-off:hover { background: #F3F4F8; color: var(--p-deep); border-color: rgba(127,119,221,.32); }
.bl-result-alert {
  background: rgba(226, 75, 74, .12);
  color: #B91C1C;
  border-color: rgba(226, 75, 74, .30);
  animation: bl-result-pulse 1.8s ease-in-out infinite;
}
.bl-result-alert:hover { filter: brightness(.95); animation-play-state: paused; }
@keyframes bl-result-pulse {
  0%, 100% { box-shadow: 0 0 0 0 rgba(226, 75, 74, .35); }
  50%      { box-shadow: 0 0 0 5px rgba(226, 75, 74, 0);   }
}
.bl-status-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  flex-shrink: 0;
}
.bl-qcount {
  margin-left: 5px;
  font-size: 10px;
  font-weight: 600;
  letter-spacing: .02em;
  font-variant-numeric: tabular-nums;
}

/* Dates */
.bl-cell-dates {
  display: flex;
  align-items: center;
  justify-content: flex-end;
}
.bl-dates-stack {
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  gap: 1px;
}
.bl-date-start {
  font-size: 11px;
  color: rgba(30, 42, 74, 0.45);
  font-variant-numeric: tabular-nums;
  white-space: nowrap;
}
.bl-date-due {
  display: inline-flex;
  align-items: center;
  gap: 3px;
  font-size: 12px;
  font-weight: 500;
  color: rgba(30, 42, 74, 0.65);
  font-variant-numeric: tabular-nums;
  white-space: nowrap;
}
.bl-date-due.overdue {
  color: var(--sev-high);
  font-weight: 600;
}
.bl-arrow {
  font-size: 10px;
  color: rgba(30, 42, 74, 0.35);
}

@media (max-width: 1100px) {
  .bl-thead {
    grid-template-columns: 18px 1fr 100px 130px 110px;
  }
  .bl-row-grid {
    grid-template-columns: 1fr 100px 130px 110px;
  }
  .bl-th:nth-child(3),
  .bl-th:nth-child(6),
  .bl-cell-dir,
  .bl-cell-result {
    display: none;
  }
}

/* ─── Inline-edit: аффорданс ячеек ─── */
.bl-editable {
  cursor: pointer;
  border-radius: 7px;
  margin: -2px -4px;
  padding: 2px 4px;
  transition: background 0.13s var(--ease-standard), box-shadow 0.13s;
}
.bl-editable:hover {
  background: rgba(127, 119, 221, 0.09);
  box-shadow: inset 0 0 0 1px rgba(127, 119, 221, 0.22);
}
.bl-cell-add {
  font-size: 11px;
  font-weight: 500;
  color: rgba(127, 119, 221, 0.6);
  white-space: nowrap;
  opacity: 0;
  transition: opacity 0.13s;
}
.bl-row:hover .bl-cell-add { opacity: 1; }

/* ─── Inline-edit: popover ─── */
.bl-pop-backdrop {
  position: fixed;
  inset: 0;
  z-index: 200;
  background: transparent;
}
.bl-pop {
  position: fixed;
  z-index: 201;
  min-width: 200px;
  max-width: 240px;
  background: #fff;
  border: 1px solid rgba(30, 42, 74, 0.10);
  border-radius: 12px;
  box-shadow: 0 12px 40px rgba(15, 23, 60, 0.16), 0 3px 10px rgba(15, 23, 60, 0.08);
  padding: 6px;
  animation: bl-pop-in 0.16s var(--ease-standard);
  transform-origin: top left;
}
@keyframes bl-pop-in {
  from { opacity: 0; transform: scale(0.95) translateY(-3px); }
  to   { opacity: 1; transform: scale(1) translateY(0); }
}
.bl-pop-head {
  font-size: 9.5px;
  font-weight: 500;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  color: var(--t3, var(--t-muted));
  padding: 4px 8px 6px;
}
.bl-pop-scroll { max-height: 248px; overflow-y: auto; }
.bl-pop-opt {
  display: flex;
  align-items: center;
  gap: 8px;
  width: 100%;
  padding: 7px 8px;
  border: none;
  background: transparent;
  border-radius: 8px;
  font-size: 12.5px;
  font-weight: 500;
  color: var(--t1, #1E2A4A);
  font-family: inherit;
  cursor: pointer;
  text-align: left;
  transition: background 0.12s;
}
.bl-pop-opt:hover { background: rgba(127, 119, 221, 0.08); }
.bl-pop-opt.on { background: rgba(127, 119, 221, 0.12); }
.bl-pop-opt-label { flex: 1; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.bl-pop-check { color: var(--p-deep, #534AB7); font-weight: 700; }
.bl-pop-cons { font-size: 10px; padding: 1px 5px; }
.bl-pop-clear { color: var(--sev-high, #E24B4A); justify-content: center; margin-top: 2px; }
.bl-pop-date {
  width: 100%;
  box-sizing: border-box;
  border: 1.5px solid var(--border-input, #E2E8F0);
  border-radius: 8px;
  padding: 7px 9px;
  font-size: 12.5px;
  font-family: inherit;
  color: var(--t1, #1E2A4A);
  outline: none;
}
.bl-pop-date:focus { border-color: var(--p, #7C6FF7); box-shadow: 0 0 0 3px rgba(124, 111, 247, 0.14); }
.bl-pop-saving {
  position: absolute;
  inset: 0;
  background: rgba(255, 255, 255, 0.6);
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 12px;
  z-index: 1;
}
.bl-spinner-sm { width: 18px; height: 18px; border-width: 2px; }
</style>
