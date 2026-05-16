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

import { ref, computed, onMounted, watch } from "vue";
import { api } from "@/api/client";
import { tasksApi, projectsApi } from "@/api/tasks";
import { consultantsApi, type ConsultantBrief } from "@/api/consultants";

const props = defineProps<{
  companyId: string;
  companyName?: string;
  year?: number | null;
}>();

const emit = defineEmits<{
  (e: "openEditor", payload: { id: string; kind: "project" | "task" }): void;
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
  consultant_id?: string | null;
  consultant?: any;
  portfolio_year?: number | null;
  is_archived?: boolean;
  extra?: any;
}

interface TaskItem extends ProjectItem {
  project_id?: string | null;
}

const projects = ref<ProjectItem[]>([]);
const tasks = ref<TaskItem[]>([]);
const directions = ref<{ id: string; code: string; name_ru: string; name_en?: string }[]>([]);
const DIR_PALETTE = ["#7F77DD","#1D9E75","#EF9F27","#378ADD","#A855F7","#06B6D4","#6366F1","#E24B4A","#10B981","#EC4899"];
const DIR_LABELS: Record<string, string> = {
  strategy: "Стратегическое управление",
  finance: "Финансы / риски / аудит",
  procurement: "Система закупок",
  orgdev: "Организационное развитие",
  digital: "Цифровизация",
  governance: "Корпоративное управление",
  esg: "ESG / устойчивое развитие",
  operations: "Операционная эффективность",
  hr: "Управление персоналом",
  sales: "Продажи / коммерция",
  legal: "Юридическая",
  marketing: "Маркетинг",
};
function colorForDirCode(code: string): string {
  if (!code) return "#94A3B8";
  let h = 0;
  for (let i = 0; i < code.length; i++) h = ((h * 31) + code.charCodeAt(i)) >>> 0;
  return DIR_PALETTE[h % DIR_PALETTE.length];
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

onMounted(loadAll);
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

interface ResultMeta {
  dot: string;
  label: string;
  color: string;
}
const RESULT_META: Record<string, ResultMeta> = {
  review: { dot: "#6366F1", label: "На рассмотрении", color: "#4338CA" },
  agreement: { dot: "#EF9F27", label: "На согласовании", color: "#B45309" },
  accepted: { dot: "#1D9E75", label: "Принят", color: "#0F6E56" },
  rejected: { dot: "#E24B4A", label: "Отклонён", color: "#B91C1C" },
};
function resultMeta(s: string | null | undefined): ResultMeta | null {
  if (!s) return null;
  return RESULT_META[s] || null;
}

function directionInfo(t: ProjectItem | TaskItem): { label: string; color: string } | null {
  const code = (t as any).direction || ((t as any).direction_meta && (t as any).direction_meta.code) || null;
  if (code) {
    const codeStr = String(code);
    const d = directions.value.find((x) => x.code === codeStr);
    const label = (d && d.name_ru) || DIR_LABELS[codeStr] || codeStr;
    return { label, color: colorForDirCode(codeStr) };
  }
  if ((t as any).direction_id) {
    const d = directions.value.find((x) => x.id === (t as any).direction_id);
    if (d) return { label: d.name_ru || DIR_LABELS[d.code] || d.code, color: colorForDirCode(d.code) };
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
    const di = directionInfo(t);
    if (!di) return false;
    const code = t.direction || (t.extra && (t.extra as any).direction) || "";
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

const groups = computed<Group[]>(() => {
  const out: Group[] = [];
  const sortedProjects = [...filteredProjects.value].sort((a, b) =>
    String(a.num || "").localeCompare(String(b.num || ""), "en", { numeric: true })
  );
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
    nested.sort((a, b) =>
      String(a.num || "").localeCompare(String(b.num || ""), "en", { numeric: true })
    );
    nested.forEach((t) => claimed.add(String((t as any).id)));
    out.push({ project: p, tasks: nested });
  }
  const orphans = filteredTasks.value.filter((t) => !claimed.has(String((t as any).id)));
  if (orphans.length > 0) {
    orphans.sort((a, b) =>
      String(a.num || "").localeCompare(String(b.num || ""), "en", { numeric: true })
    );
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

const dirChipsData = computed(() => {
  const all = [...projects.value, ...tasks.value].filter((x) => !x.is_archived);
  const map = new Map<string, number>();
  for (const t of all) {
    const code = t.direction || (t.extra && (t.extra as any).direction) || null;
    if (!code) continue;
    map.set(code, (map.get(code) || 0) + 1);
  }
  return Array.from(map.entries()).map(([code, count]) => {
    const d = directions.value.find((x) => x.code === code);
    return {
      code,
      count,
      label: d?.label || code,
      color: d?.color || "#94A3B8",
    };
  });
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
      <!-- Direction chips -->
      <div v-if="dirChipsData.length" class="bl-chips">
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

      <!-- Status filters -->
      <div class="bl-chips bl-chips-status">
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
      </div>

      <button v-if="dirFilter || statusFilter" class="bl-clear" @click="clearFilters">
        × Сбросить
      </button>
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

    <!-- ═══ TABLE ═══ -->
    <div v-else class="bl-table">
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
          :class="{ overdue: isOverdue(g.project) }"
          @click="openProject(g.project)"
        >
          <div class="bl-handle">⋮⋮</div>
          <div class="bl-title-cell">
            <span class="bl-num">{{ g.project.num || "" }}</span>
            <span class="bl-title bl-title-bold">{{ g.project.title }}</span>
          </div>
          <div class="bl-cell-dir">
            <span
              v-if="directionInfo(g.project)"
              class="bl-dir-label"
              :style="{ color: directionInfo(g.project)!.color }"
            >
              {{ directionInfo(g.project)!.label }}
            </span>
          </div>
          <div class="bl-cell-cons">
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
          </div>
          <div class="bl-cell-status">
            <span class="bl-status-pill">
              <span class="bl-status-dot" :style="{ background: statusMeta(g.project.status).dot }"></span>
              {{ statusMeta(g.project.status).label }}
            </span>
          </div>
          <div class="bl-cell-result">
            <span
              v-if="resultMeta(g.project.result_status)"
              class="bl-result-pill"
              :style="{ color: resultMeta(g.project.result_status)!.color }"
            >
              <span
                class="bl-status-dot"
                :style="{ background: resultMeta(g.project.result_status)!.dot }"
              ></span>
              {{ resultMeta(g.project.result_status)!.label }}
            </span>
          </div>
          <div class="bl-cell-dates">
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
          </div>
        </div>

        <!-- Tasks under this project -->
        <div
          v-for="t in g.tasks"
          :key="t.id"
          class="bl-row bl-row-task"
          :class="{ overdue: isOverdue(t), nested: !!g.project }"
          @click="openTask(t)"
        >
          <div class="bl-handle bl-handle-sub">{{ g.project ? "└" : "⋮⋮" }}</div>
          <div class="bl-title-cell">
            <span class="bl-num">{{ t.num || "" }}</span>
            <span class="bl-title">{{ t.title }}</span>
          </div>
          <div class="bl-cell-dir">
            <span
              v-if="directionInfo(t)"
              class="bl-dir-label"
              :style="{ color: directionInfo(t)!.color }"
            >
              {{ directionInfo(t)!.label }}
            </span>
          </div>
          <div class="bl-cell-cons">
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
          </div>
          <div class="bl-cell-status">
            <span class="bl-status-pill">
              <span class="bl-status-dot" :style="{ background: statusMeta(t.status).dot }"></span>
              {{ statusMeta(t.status).label }}
            </span>
          </div>
          <div class="bl-cell-result">
            <span
              v-if="resultMeta(t.result_status)"
              class="bl-result-pill"
              :style="{ color: resultMeta(t.result_status)!.color }"
            >
              <span class="bl-status-dot" :style="{ background: resultMeta(t.result_status)!.dot }"></span>
              {{ resultMeta(t.result_status)!.label }}
            </span>
          </div>
          <div class="bl-cell-dates">
            <div v-if="t.start_date || t.due_date" class="bl-dates-stack">
              <span v-if="t.start_date" class="bl-date-start">{{ fmtDate(t.start_date) }}</span>
              <span v-if="t.due_date" class="bl-date-due" :class="{ overdue: isOverdue(t) }">
                <span v-if="t.start_date" class="bl-arrow">→</span>
                {{ fmtDate(t.due_date) }}
              </span>
            </div>
          </div>
        </div>
      </template>
    </div>
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
  flex-wrap: wrap;
  gap: 14px;
  align-items: center;
  padding: 12px 16px;
  background: rgba(127, 119, 221, 0.04);
  border: 1px solid rgba(30, 42, 74, 0.06);
  border-radius: 10px;
}
.bl-chips {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}
.bl-chips-status {
  flex: 1;
  justify-content: flex-end;
}
.bl-chip {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 4px 11px;
  border-radius: 11px;
  border: 0.5px solid rgba(30, 42, 74, 0.10);
  background: white;
  font-size: 12px;
  font-weight: 500;
  color: #1E2A4A;
  cursor: pointer;
  transition: all 0.18s cubic-bezier(0.4, 0, 0.2, 1);
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
  width: 6px;
  height: 6px;
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
  color: #1E2A4A;
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
  color: #E24B4A;
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

/* ─── Table ─── */
.bl-table {
  display: flex;
  flex-direction: column;
  gap: 1px;
  background: rgba(30, 42, 74, 0.05);
  border-radius: 10px;
  overflow: hidden;
  border: 1px solid rgba(30, 42, 74, 0.06);
}
.bl-thead {
  display: grid;
  grid-template-columns: 22px minmax(0, 2.4fr) minmax(0, 1fr) 110px 140px 130px 140px;
  gap: 12px;
  padding: 10px 16px;
  background: rgba(127, 119, 221, 0.06);
  font-size: 10.5px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  color: rgba(30, 42, 74, 0.55);
}
.bl-th {
  align-self: center;
}
.bl-center { text-align: center; }
.bl-right { text-align: right; }

.bl-row {
  display: grid;
  grid-template-columns: 22px minmax(0, 2.4fr) minmax(0, 1fr) 110px 140px 130px 140px;
  gap: 12px;
  padding: 10px 16px;
  background: white;
  cursor: pointer;
  transition: background 0.12s ease;
  align-items: center;
  min-height: 40px;
}
.bl-row:hover {
  background: rgba(127, 119, 221, 0.05);
}
.bl-row-project {
  background: rgba(127, 119, 221, 0.025);
}
.bl-row-project:hover {
  background: rgba(127, 119, 221, 0.08);
}
.bl-row-task.nested {
  padding-left: 28px;
}
.bl-row.overdue::before {
  content: "";
  position: absolute;
  left: 0;
  top: 0;
  bottom: 0;
  width: 3px;
  background: #E24B4A;
}
.bl-row {
  position: relative;
}

.bl-handle {
  color: rgba(30, 42, 74, 0.25);
  font-size: 14px;
  letter-spacing: -1px;
  user-select: none;
}
.bl-handle-sub {
  color: rgba(30, 42, 74, 0.35);
  font-size: 12px;
}

.bl-title-cell {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
}
.bl-num {
  font-size: 11px;
  color: rgba(30, 42, 74, 0.45);
  font-variant-numeric: tabular-nums;
  flex-shrink: 0;
  min-width: 22px;
  font-weight: 500;
}
.bl-title {
  font-size: 13px;
  color: #1E2A4A;
  font-weight: 400;
  letter-spacing: -0.005em;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  flex: 1;
}
.bl-title-bold {
  font-weight: 500;
  letter-spacing: -0.015em;
}

.bl-cell-dir,
.bl-cell-cons,
.bl-cell-status,
.bl-cell-result,
.bl-cell-dates {
  display: flex;
  align-items: center;
  min-width: 0;
}
.bl-cell-cons,
.bl-cell-status,
.bl-cell-result {
  justify-content: center;
}
.bl-cell-dates {
  justify-content: flex-end;
}

.bl-dir-label {
  font-size: 12px;
  font-weight: 500;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.bl-cons-badge {
  font-size: 10px;
  font-weight: 600;
  padding: 2px 7px;
  border-radius: 5px;
  white-space: nowrap;
  letter-spacing: 0.02em;
}

.bl-status-pill,
.bl-result-pill {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: 11.5px;
  font-weight: 500;
  white-space: nowrap;
  color: rgba(30, 42, 74, 0.75);
}
.bl-status-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  flex-shrink: 0;
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
  font-size: 12px;
  font-weight: 500;
  color: rgba(30, 42, 74, 0.65);
  font-variant-numeric: tabular-nums;
  white-space: nowrap;
  display: inline-flex;
  align-items: center;
  gap: 3px;
}
.bl-date-due.overdue {
  color: #E24B4A;
  font-weight: 600;
}
.bl-arrow {
  font-size: 10px;
  color: rgba(30, 42, 74, 0.35);
}

@media (max-width: 1100px) {
  .bl-thead,
  .bl-row {
    grid-template-columns: 22px minmax(0, 2fr) 110px 130px 130px;
  }
  .bl-th:nth-child(3),
  .bl-th:nth-child(4),
  .bl-cell-dir,
  .bl-cell-cons {
    display: none;
  }
}
</style>
