<script setup lang="ts">
import { ref, computed, onMounted, watch } from "vue";
import { api } from "@/api/client";
import { useRouter, useRoute } from "vue-router";

import BadgeStatus from "@/components/BadgeStatus.vue";
import BadgePriority from "@/components/BadgePriority.vue";
import BadgeDeferred from "@/components/BadgeDeferred.vue";
import BadgeOverdue from "@/components/BadgeOverdue.vue";
import DirectionBadge from "@/components/DirectionBadge.vue";
import ChipFilter from "@/components/ChipFilter.vue";
import TaskModal from "@/components/TaskModal.vue";
import TaskProjectEditor from "@/components/TaskProjectEditor.vue";
import { useToast } from "@/composables/useToast";
import type { TaskDetail } from "@/api/tasks";

// ─── State ──────────────────────────────────────────────────────
const router = useRouter();
const route = useRoute();

const items = ref<any[]>([]);
const total = ref(0);
const byStatus = ref<Record<string, number>>({});
const loading = ref(true);
const errorMsg = ref<string | null>(null);

// Filters
const search = ref("");
const statusFilter = ref<string>(""); // "" = all
const directionFilter = ref<string>("");
const priorityFilter = ref<string>("");
const onlyOverdue = ref(false);
const portfolioYear = ref<number | null>(2025);
const sortBy = ref("num");
const sortDir = ref<"asc" | "desc">("asc");

// Lookups
const directionsList = ref<{ code: string; label: string; color: string }[]>([]);

// Modal state
const modalOpen = ref(false);
const modalTaskId = ref<string | null>(null);
const modalDefaultStatus = ref<string>("new");

// === v9.1 additions ===
const editorEntity = ref<TaskDetail | null>(null);
const toast = useToast();
const editorReady = computed(() => {
  if (!modalOpen.value) return false;
  if (modalTaskId.value === null) return true; // create mode
  return editorEntity.value !== null && (editorEntity.value as any).id === modalTaskId.value;
});

watch(modalTaskId, async (id) => {
  if (id === null) {
    editorEntity.value = null;
    return;
  }
  try {
    const { data } = await api.get<TaskDetail>(`/tasks/${id}`);
    editorEntity.value = data;
  } catch (e: any) {
    toast.error("Ошибка загрузки задачи: " + (e?.message || ""));
    modalOpen.value = false;
  }
});

function onEditorSaved(id: string) {
  toast.success("Задача сохранена");
  modalOpen.value = false;
  if (typeof load === "function") load();
}
function onEditorClose() {
  modalOpen.value = false;
  // Перезагрузка для случая когда editor сделал archive/delete
  if (typeof load === "function") load();
}

// ─── Status definitions for chips ──────────────────────────────
const STATUS_CHIPS = [
  { id: "new",       label: "Не начато",       accent: "#94A3B8", accentBg: "#F1F5F9" },
  { id: "init",      label: "Инициирование",   accent: "#64748B", accentBg: "#E2E8F0" },
  { id: "active",    label: "В процессе",      accent: "#3B82F6", accentBg: "rgba(55,138,221,.10)" },
  { id: "review",    label: "На согласовании", accent: "#F59E0B", accentBg: "#FEF9C3" },
  { id: "done",      label: "Завершено",       accent: "#10B981", accentBg: "#D1FAE5" },
  { id: "quarterly", label: "Ежеквартально",   accent: "#7E22CE", accentBg: "rgba(168,85,247,.13)" },
  { id: "monthly",   label: "Ежемесячно",      accent: "#4338CA", accentBg: "rgba(99,102,241,.13)" },
  { id: "ongoing",   label: "Постоянно",       accent: "#0E7490", accentBg: "rgba(6,182,212,.13)" },
];

// ─── URL → state sync ──────────────────────────────────────────
function syncFromQuery() {
  const q = route.query;
  if (q.status && typeof q.status === "string") statusFilter.value = q.status;
  if (q.direction && typeof q.direction === "string") directionFilter.value = q.direction;
  if (q.priority && typeof q.priority === "string") priorityFilter.value = q.priority;
  if (q.search && typeof q.search === "string") search.value = q.search;
  if (q.year && typeof q.year === "string") portfolioYear.value = parseInt(q.year);
  if (q.overdue === "1") onlyOverdue.value = true;
}

function syncToQuery() {
  const q: Record<string, string> = {};
  if (statusFilter.value) q.status = statusFilter.value;
  if (directionFilter.value) q.direction = directionFilter.value;
  if (priorityFilter.value) q.priority = priorityFilter.value;
  if (search.value) q.search = search.value;
  if (portfolioYear.value) q.year = String(portfolioYear.value);
  if (onlyOverdue.value) q.overdue = "1";
  router.replace({ query: q });
}

// ─── Data load ─────────────────────────────────────────────────
async function load() {
  loading.value = true;
  errorMsg.value = null;
  try {
    const params: any = {
      limit: 200,
      sort_by: sortBy.value,
      sort_dir: sortDir.value,
    };
    if (statusFilter.value) params.status = statusFilter.value;
    if (directionFilter.value) params.direction = directionFilter.value;
    if (priorityFilter.value) params.priority = priorityFilter.value;
    if (search.value.trim()) params.search = search.value.trim();
    if (onlyOverdue.value) params.only_overdue = true;
    if (portfolioYear.value) params.portfolio_year = portfolioYear.value;

    const r = await api.get<any>("/tasks", { params });
    items.value = r.data.items || [];
    total.value = r.data.total || 0;
    byStatus.value = r.data.by_status || {};
  } catch (e: any) {
    errorMsg.value = e?.response?.data?.detail || e?.message || "Ошибка загрузки";
    items.value = [];
  } finally {
    loading.value = false;
  }
}

async function loadDirections() {
  try {
    const r = await api.get<any>("/directions");
    directionsList.value = r.data.directions || [];
  } catch (e) {
    console.warn("Could not load directions");
  }
}

// ─── Helpers ────────────────────────────────────────────────────
function formatDate(d: string | null | undefined): string {
  if (!d) return "—";
  return d.slice(0, 10).split("-").reverse().join(".");
}

function isOverdue(t: any): boolean {
  if (!t.due_date || t.status === "done") return false;
  const d = new Date(t.due_date);
  return d < new Date();
}

function daysUntil(d: string | null | undefined): number | null {
  if (!d) return null;
  const diff = (new Date(d).getTime() - Date.now()) / 86400000;
  return Math.floor(diff);
}

function toggleStatus(s: string) {
  statusFilter.value = statusFilter.value === s ? "" : s;
}

function toggleSort(col: string) {
  if (sortBy.value === col) {
    sortDir.value = sortDir.value === "asc" ? "desc" : "asc";
  } else {
    sortBy.value = col;
    sortDir.value = "asc";
  }
}

function clearFilters() {
  statusFilter.value = "";
  directionFilter.value = "";
  priorityFilter.value = "";
  search.value = "";
  onlyOverdue.value = false;
}

const hasFilters = computed(() =>
  !!(statusFilter.value || directionFilter.value || priorityFilter.value
     || search.value || onlyOverdue.value)
);

// ─── Modal ──────────────────────────────────────────────────────
function openCreate(status?: string) {
  modalTaskId.value = null;
  modalDefaultStatus.value = status || "new";
  modalOpen.value = true;
}

function openEdit(taskId: string) {
  modalTaskId.value = taskId;
  modalOpen.value = true;
}

function onSaved() {
  load();
}

function onDeleted(_id: string) {
  load();
}

// ─── Watches ────────────────────────────────────────────────────
watch([statusFilter, directionFilter, priorityFilter, onlyOverdue, portfolioYear, sortBy, sortDir],
      () => { syncToQuery(); load(); });

let searchTimer: number | null = null;
watch(search, () => {
  if (searchTimer) clearTimeout(searchTimer);
  searchTimer = setTimeout(() => {
    syncToQuery();
    load();
  }, 250) as any;
});

onMounted(() => {
  syncFromQuery();
  loadDirections();
  load();
});
</script>

<template>
  <div class="tasks-page">
    <!-- Header -->
    <div class="page-header">
      <div class="page-eyebrow">ПОРТФЕЛЬ <span style="color: #7F77DD;">{{ portfolioYear || "Все годы" }}</span></div>
      <h1 class="page-title">Задачи</h1>
      <div class="page-sub">
        <span style="font-variant-numeric: tabular-nums;">{{ total }}</span>
        <span style="color: var(--t3); margin-left: 6px;">{{
          total === 1 ? "задача" : (total < 5 ? "задачи" : "задач")
        }}</span>
      </div>
    </div>

    <!-- Status chips row -->
    <div class="chip-row">
      <ChipFilter v-for="s in STATUS_CHIPS" :key="s.id"
                  :label="s.label"
                  :count="byStatus[s.id]"
                  :active="statusFilter === s.id"
                  :accent="s.accent"
                  :accent-bg="s.accentBg"
                  :animate-in="true"
                  @click="toggleStatus(s.id)" />
      <!-- Deferred chip -->
      <ChipFilter v-if="byStatus['deferred']"
                  label="Перенесено"
                  :count="byStatus['deferred']"
                  :active="statusFilter === 'deferred'"
                  accent="#7F77DD"
                  accent-bg="rgba(127,119,221,.10)"
                  :animate-in="true"
                  @click="toggleStatus('deferred')">
        <template #icon>
          <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor"
               stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <line x1="5" y1="12" x2="19" y2="12"/>
            <polyline points="12 5 19 12 12 19"/>
          </svg>
        </template>
      </ChipFilter>
    </div>

    <!-- Filter bar -->
    <div class="filter-bar">
      <input v-model="search"
             class="filter-search"
             placeholder="Поиск по номеру, названию, исполнителю…" />
      <select v-model="directionFilter" class="filter-select">
        <option value="">Все направления</option>
        <option v-for="d in directionsList" :key="d.code" :value="d.code">{{ d.label }}</option>
      </select>
      <select v-model="priorityFilter" class="filter-select">
        <option value="">Все приоритеты</option>
        <option value="high">Высокий</option>
        <option value="medium">Средний</option>
        <option value="low">Низкий</option>
      </select>
      <label class="filter-overdue">
        <input type="checkbox" v-model="onlyOverdue" />
        <span>Только просроченные</span>
      </label>
      <button v-if="hasFilters" class="btn-clear" @click="clearFilters">Очистить</button>
      <button class="btn-create" @click="openCreate()">+ Задача</button>
    </div>

    <!-- Error -->
    <div v-if="errorMsg" class="state-msg error">⚠ {{ errorMsg }}</div>

    <!-- Loading -->
    <div v-else-if="loading && items.length === 0" class="state-msg">Загрузка…</div>

    <!-- Empty -->
    <div v-else-if="!loading && items.length === 0" class="state-msg">
      Ничего не найдено
    </div>

    <!-- Tasks list -->
    <div v-else class="task-list">
      <div class="list-header">
        <button class="col-num" @click="toggleSort('num')">
          № <span v-if="sortBy === 'num'" class="sort-arr">{{ sortDir === 'asc' ? '↑' : '↓' }}</span>
        </button>
        <button class="col-title" @click="toggleSort('title')">
          НАЗВАНИЕ <span v-if="sortBy === 'title'" class="sort-arr">{{ sortDir === 'asc' ? '↑' : '↓' }}</span>
        </button>
        <div class="col-status">СТАТУС</div>
        <button class="col-deadline" @click="toggleSort('due_date')">
          ДЕДЛАЙН <span v-if="sortBy === 'due_date'" class="sort-arr">{{ sortDir === 'asc' ? '↑' : '↓' }}</span>
        </button>
        <div class="col-assignee">ИСПОЛНИТЕЛЬ</div>
      </div>

      <div v-for="t in items" :key="t.id" class="task-row" @click="openEdit(t.id)">
        <div class="col-num">
          <span class="num-pill">{{ t.num || "—" }}</span>
        </div>
        <div class="col-title">
          <div class="task-title-text">{{ t.title }}</div>
          <div class="task-meta">
            <DirectionBadge v-if="t.direction_meta"
                            :direction="t.direction_meta"
                            variant="bar" size="sm" />
            <BadgePriority v-if="t.priority && t.priority !== 'medium'"
                           :priority="t.priority" size="sm" />
            <BadgeDeferred v-if="t.linked_year" :linked-year="t.linked_year" size="sm" />
          </div>
        </div>
        <div class="col-status">
          <BadgeStatus :status="t.status" size="sm" />
        </div>
        <div class="col-deadline">
          <BadgeOverdue v-if="isOverdue(t)" size="sm" />
          <span v-else class="deadline-text"
                :class="{ 'soon': daysUntil(t.due_date) != null && daysUntil(t.due_date) <= 7 && daysUntil(t.due_date) >= 0 }">
            {{ formatDate(t.due_date) }}
          </span>
        </div>
        <div class="col-assignee">
          <span v-if="t.assignee_name" class="assignee-name">{{ t.assignee_name }}</span>
          <span v-else class="assignee-empty">—</span>
        </div>
      </div>
    </div>

    <!-- Task Modal -->
    <TaskProjectEditor v-if="editorReady"
                       :entity="editorEntity"
                       kind="task"
                       @close="onEditorClose"
                       @saved="onEditorSaved" />
  </div>
</template>

<style scoped>
.tasks-page {
  padding: 24px 32px;
  max-width: 1800px;
  margin: 0 auto;
}

/* Header */
.page-header { margin-bottom: 16px; }
.page-eyebrow {
  font-size: 10px;
  font-weight: 500;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: var(--t3, #64748B);
  margin-bottom: 6px;
}
.page-title {
  font-size: 22px;
  font-weight: 500;
  letter-spacing: -0.01em;
  margin: 0 0 4px;
  color: var(--t1, #1E2A4A);
}
.page-sub {
  font-size: 13px;
  color: var(--t1, #1E2A4A);
  font-weight: 500;
}

/* Status chips row */
.chip-row {
  display: flex;
  gap: 6px;
  flex-wrap: wrap;
  margin-bottom: 14px;
}

/* Filter bar */
.filter-bar {
  display: flex;
  gap: 8px;
  align-items: center;
  margin-bottom: 18px;
  flex-wrap: wrap;
}
.filter-search {
  flex: 1;
  min-width: 240px;
  padding: 8px 12px;
  border: 1px solid #E2E8F0;
  border-radius: 11px;
  background: #fff;
  font-size: 12px;
  color: var(--t1, #1E2A4A);
  outline: none;
  transition: border-color .12s, box-shadow .12s;
}
.filter-search:focus {
  border-color: #7F77DD;
  box-shadow: 0 0 0 3px rgba(127, 119, 221, 0.10);
}
.filter-select {
  padding: 8px 28px 8px 12px;
  border: 1px solid #E2E8F0;
  border-radius: 11px;
  background-color: #fff;
  background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='12' height='12' viewBox='0 0 12 12'%3E%3Cpath d='M3 4.5l3 3 3-3' fill='none' stroke='%239CA3AF' stroke-width='1.5' stroke-linecap='round'/%3E%3C/svg%3E");
  background-repeat: no-repeat;
  background-position: right 8px center;
  font-size: 12px;
  appearance: none;
  -webkit-appearance: none;
  cursor: pointer;
  outline: none;
  min-width: 180px;
  color: var(--t1, #1E2A4A);
}
.filter-overdue {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  color: var(--t2, #475569);
  cursor: pointer;
  user-select: none;
}
.btn-clear {
  padding: 6px 12px;
  background: transparent;
  border: 1px solid #E2E8F0;
  border-radius: 11px;
  color: var(--t3, #64748B);
  font-size: 11px;
  cursor: pointer;
  transition: all .12s;
}
.btn-clear:hover { background: #F1F5F9; }

.btn-create {
  padding: 8px 14px;
  background: #7F77DD;
  color: #fff;
  border: none;
  border-radius: 11px;
  font-weight: 500;
  font-size: 12px;
  cursor: pointer;
  transition: background .12s;
  margin-left: auto;
}
.btn-create:hover { background: #6E66CC; }

/* States */
.state-msg {
  padding: 32px;
  text-align: center;
  color: var(--t3, #64748B);
  font-size: 13px;
  background: #fff;
  border-radius: 12px;
  border: 1px solid #E2E8F0;
}
.state-msg.error { color: #993D3D; }

/* Task list */
.task-list {
  background: #fff;
  border-radius: 12px;
  border: 1px solid #E2E8F0;
  overflow: hidden;
  box-shadow: 0 4px 12px rgba(15, 23, 60, 0.04);
}

.list-header {
  display: grid;
  grid-template-columns: 80px 1.7fr 130px 120px 200px;
  gap: 12px;
  padding: 10px 16px;
  border-bottom: 1px solid #E2E8F0;
  background: #FAFBFC;
  font-size: 9.5px;
  font-weight: 500;
  color: var(--t3, #64748B);
  letter-spacing: 0.06em;
  text-transform: uppercase;
}
.list-header > * {
  text-align: left;
  background: transparent;
  border: none;
  font-weight: inherit;
  font-size: inherit;
  letter-spacing: inherit;
  color: inherit;
  cursor: default;
  font-family: inherit;
  padding: 0;
}
.list-header button {
  cursor: pointer;
  transition: color .12s;
}
.list-header button:hover { color: var(--t1, #1E2A4A); }
.sort-arr {
  font-weight: 700;
  margin-left: 2px;
}

/* Task row */
.task-row {
  display: grid;
  grid-template-columns: 80px 1.7fr 130px 120px 200px;
  gap: 12px;
  padding: 12px 16px;
  border-bottom: 1px solid #F1F5F9;
  align-items: flex-start;
  cursor: pointer;
  transition: background .12s;
}
.task-row:hover { background: #FAFBFC; }
.task-row:last-child { border-bottom: none; }

.col-num {
  display: flex;
  align-items: flex-start;
}
.num-pill {
  font-size: 10.5px;
  font-weight: 600;
  padding: 3px 7px;
  background: #F1F5F9;
  color: var(--t2, #475569);
  border-radius: 5px;
  letter-spacing: 0.02em;
  font-variant-numeric: tabular-nums;
  white-space: nowrap;
}

.col-title {
  min-width: 0;
}
.task-title-text {
  color: var(--t1, #1E2A4A);
  font-size: 13px;
  font-weight: 500;
  line-height: 1.4;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}
.task-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-top: 5px;
  align-items: center;
}

.col-status, .col-deadline, .col-assignee {
  align-self: center;
}

.deadline-text {
  font-size: 11.5px;
  color: var(--t2, #475569);
  font-variant-numeric: tabular-nums;
}
.deadline-text.soon {
  color: #D97706;
  font-weight: 500;
}

.assignee-name {
  font-size: 11.5px;
  color: var(--t1, #1E2A4A);
}
.assignee-empty {
  font-size: 11.5px;
  color: var(--t3, #94A3B8);
}

/* Mobile */
@media (max-width: 900px) {
  .list-header, .task-row {
    grid-template-columns: 60px 1fr 100px;
  }
  .col-deadline, .col-assignee { display: none; }
}
</style>
