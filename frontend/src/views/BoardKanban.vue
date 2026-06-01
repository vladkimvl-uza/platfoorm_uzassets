<script setup lang="ts">
import { ref, onMounted, computed, watch } from "vue";
import { useRoute, useRouter, RouterLink } from "vue-router";
import { boardsApi, tasksApi } from "@/api/tasks";
import { api, isModerationQueued } from "@/api/client";
import { usePortfolioYearStore } from "@/stores/portfolioYear";
import type { BoardKanban, TaskBrief, TaskDetail } from "@/api/tasks";
import TaskProjectEditor from "@/components/TaskProjectEditor.vue";
import {
  computeProgress, quarterlyDoneCount, isQuarterlyAllDone, progressColor,
} from "@/utils/progress";
import DirectionBadge from "@/components/DirectionBadge.vue";

const route   = useRoute();
const router  = useRouter();
const py      = usePortfolioYearStore();
const boardId = computed(() => String(route.params.id || ""));

const data    = ref<BoardKanban | null>(null);
const loading = ref(true);
const error   = ref<string | null>(null);

// Кэш входящих задач для карточек-проектов (lazy-load /projects/{id}/tasks)
const subtasksCache = ref<Record<string, TaskBrief[]>>({});

// Editor state
const editorOpen   = ref(false);
const editorEntity = ref<TaskDetail | null>(null);

async function openTaskEditor(t: TaskBrief, ev?: MouseEvent) {
  if (ev) ev.stopPropagation();
  try {
    editorEntity.value = await tasksApi.getOne(t.id);
    editorOpen.value = true;
  } catch (e: any) {
    error.value = e?.response?.data?.detail || e?.message || "Не удалось открыть задачу";
  }
}

async function onEditorSaved() {
  editorOpen.value = false;
  editorEntity.value = null;
  await load();
}

const boardProgress = computed(() => {
  if (!data.value) return { done: 0, total: 0, pct: 0, excluded: 0 };
  const allTasks = data.value.columns.flatMap(c => c.tasks);
  return computeProgress(allTasks);
});

// Drag state
const dragging = ref<TaskBrief | null>(null);
const dragOverColumn = ref<string | null>(null);

async function load() {
  loading.value = true;
  error.value = null;
  subtasksCache.value = {};
  try {
    data.value = await boardsApi.getKanban(boardId.value, py.year);
    void loadProjectSubtasks();
  } catch (e: any) {
    error.value = e?.response?.status === 404
      ? "Доска не найдена"
      : (e?.response?.data?.detail || e?.message || "Не удалось загрузить доску");
  } finally {
    loading.value = false;
  }
}

onMounted(load);
watch(boardId, load);
watch(() => py.year, load);

const PRIO_COLOR: Record<string, string> = {
  high:   "#E24B4A",
  medium: "#EF9F27",
  low:    "#94A3B8",
};

const PRIO_LABEL: Record<string, string> = {
  high:   "Высокий",
  medium: "Средний",
  low:    "Низкий",
};

// Инициалы для аватара исполнителя (2 буквы)
function initials(name: string | null): string {
  if (!name) return "?";
  const parts = name.trim().split(/\s+/).filter(Boolean);
  if (!parts.length) return "?";
  if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase();
  return (parts[0][0] + parts[1][0]).toUpperCase();
}

// ─── Входящие задачи проекта (для карточек is_project) ───
async function loadProjectSubtasks() {
  if (!data.value) return;
  const projects = data.value.columns.flatMap(c => c.tasks).filter(t => t.is_project);
  await Promise.all(projects.map(async (p) => {
    if (subtasksCache.value[p.id]) return;
    try {
      const { data: subs } = await api.get<TaskBrief[]>(`/projects/${p.id}/tasks`);
      subtasksCache.value = { ...subtasksCache.value, [p.id]: (subs as any) || [] };
    } catch { /* карточка просто без списка */ }
  }));
}

const SUB_STATUS: Record<string, { c: string; w: string }> = {
  done:   { c: "#1D9E75", w: "Готово" },
  review: { c: "#EF9F27", w: "На утверждении" },
  active: { c: "#7F77DD", w: "В работе" },
  new:    { c: "#94A3B8", w: "Не начато" },
  init:   { c: "#64748B", w: "Инициирование" },
};
function subOverdue(s: any): boolean {
  return !!s.due_date && s.status !== "done" && new Date(s.due_date) < new Date();
}
function subDot(s: any): string {
  return subOverdue(s) ? "#E24B4A" : (SUB_STATUS[s.status]?.c || "#7F77DD");
}
function subWord(s: any): string {
  return subOverdue(s) ? "Просрочено" : (SUB_STATUS[s.status]?.w || "В работе");
}
function subDone(id: string): number {
  return (subtasksCache.value[id] || []).filter(s => s.status === "done").length;
}
function subPct(id: string): number {
  const arr = subtasksCache.value[id] || [];
  return arr.length ? Math.round((subDone(id) / arr.length) * 100) : 0;
}

function fmtDate(s: string | null): string {
  if (!s) return "";
  return new Date(s).toLocaleDateString("ru-RU", { day: "numeric", month: "short" });
}

function isOverdue(t: TaskBrief): boolean {
  return t.is_overdue;
}

// Drag-and-drop
function onDragStart(t: TaskBrief, ev: DragEvent) {
  dragging.value = t;
  if (ev.dataTransfer) {
    ev.dataTransfer.effectAllowed = "move";
    ev.dataTransfer.setData("text/plain", t.id);
  }
}

function onDragOver(status: string, ev: DragEvent) {
  ev.preventDefault();
  if (ev.dataTransfer) ev.dataTransfer.dropEffect = "move";
  dragOverColumn.value = status;
}

function onDragLeave() {
  dragOverColumn.value = null;
}

async function onDrop(targetStatus: string, ev: DragEvent) {
  ev.preventDefault();
  dragOverColumn.value = null;
  if (!dragging.value || dragging.value.status === targetStatus) {
    dragging.value = null;
    return;
  }
  const task = dragging.value;
  const oldStatus = task.status;
  dragging.value = null;

  // Optimistic update
  if (data.value) {
    const sourceCol = data.value.columns.find(c => c.status === oldStatus);
    const targetCol = data.value.columns.find(c => c.status === targetStatus);
    if (sourceCol && targetCol) {
      sourceCol.tasks = sourceCol.tasks.filter(t => t.id !== task.id);
      sourceCol.count = sourceCol.tasks.length;
      task.status = targetStatus as any;
      targetCol.tasks.unshift(task);
      targetCol.count = targetCol.tasks.length;
    }
  }

  try {
    const resp = await tasksApi.update(task.id, { status: targetStatus as any });
    if (isModerationQueued(resp)) {
      // Gated. Rollback the optimistic drag so the user doesn't think it
      // landed — the toast tells them it's in moderation now.
      await load();
    }
  } catch (e: any) {
    // Rollback
    error.value = "Не удалось переместить задачу: " + (e?.response?.data?.detail || e?.message);
    await load();
  }
}

function openTask(t: TaskBrief) {
  void openTaskEditor(t);
}
</script>

<template>
  <div class="p-8 max-w-[1600px] mx-auto">
    <!-- Loading -->
    <div v-if="loading" class="uza-card p-12 text-center text-slate-400 text-sm">
      Загрузка…
    </div>

    <!-- Error -->
    <div v-else-if="error" class="uza-card p-6">
      <div class="text-uza-red text-sm">{{ error }}</div>
      <RouterLink to="/boards" class="mt-4 inline-block text-xs text-uza-purple hover:underline">
        ← Назад к доскам
      </RouterLink>
    </div>

    <template v-else-if="data">
      <!-- Breadcrumbs -->
      <nav class="flex items-center gap-2 text-xs text-slate-400 mb-4">
        <RouterLink to="/boards" class="hover:text-uza-purple">Доски</RouterLink>
        <span>›</span>
        <span class="text-slate-600">{{ data.board.name }}</span>
      </nav>

      <!-- Header -->
      <div class="mb-4 flex items-end justify-between flex-wrap gap-4">
        <div>
          <div class="uza-section-label">{{ data.board.company_name || "Доска" }}</div>
          <h1 class="text-[22px] font-normal tracking-uza-tight mt-1">{{ data.board.name }}</h1>
          <div v-if="data.board.description" class="text-sm text-slate-500 mt-1">
            {{ data.board.description }}
          </div>
          <div class="text-xs text-slate-400 mt-1 tabular-nums">
            {{ data.board.tasks_total }} задач
          </div>
        </div>
      </div>

      <div class="uza-card p-4 mb-4 flex items-center gap-6">
        <div class="flex-1">
          <div class="text-[10px] uppercase tracking-uza-label2 text-slate-500 mb-1">Прогресс доски</div>
          <div class="flex items-center gap-3">
            <div class="text-[24px] font-medium tabular-nums leading-none"
                 :style="{ color: progressColor(boardProgress.pct) }">
              {{ boardProgress.pct }}%
            </div>
            <div class="text-xs text-slate-500">
              <div><span class="tabular-nums">{{ boardProgress.done }}</span> завершено
                из <span class="tabular-nums">{{ boardProgress.total }}</span></div>
              <div v-if="boardProgress.excluded > 0" class="text-slate-400 mt-0.5">
                {{ boardProgress.excluded }} исключено (ежемес./постоянные)
              </div>
            </div>
          </div>
        </div>
        <div class="flex-1">
          <div class="h-2 bg-slate-100 rounded-uza-pill overflow-hidden">
            <div class="h-full rounded-uza-pill transition-all"
                 :style="{ width: boardProgress.pct + '%', background: progressColor(boardProgress.pct) }"></div>
          </div>
        </div>
      </div>

      <!-- Kanban columns -->
      <div class="grid grid-cols-1 md:grid-cols-3 lg:grid-cols-5 gap-3">
        <div
          v-for="col in data.columns"
          :key="col.status"
          class="bg-slate-50 rounded-xl p-3 min-h-[400px] transition-colors"
          :class="dragOverColumn === col.status ? 'ring-2' : ''"
          :style="dragOverColumn === col.status ? { '--tw-ring-color': col.color } : {}"
          @dragover="onDragOver(col.status, $event)"
          @dragleave="onDragLeave"
          @drop="onDrop(col.status, $event)"
        >
          <!-- Column header -->
          <div class="flex items-center justify-between mb-3 px-1">
            <div class="flex items-center gap-2">
              <span class="w-2 h-2 rounded-full" :style="{ background: col.color }"></span>
              <span class="text-[10px] uppercase tracking-uza-label2 font-medium" :style="{ color: col.color }">
                {{ col.label }}
              </span>
            </div>
            <span class="text-xs text-slate-500 tabular-nums">{{ col.count }}</span>
          </div>

          <!-- Cards -->
          <div class="space-y-2">
            <div
              v-for="t in col.tasks"
              :key="t.id"
              draggable="true"
              @dragstart="onDragStart(t, $event)"
              @click="openTask(t)"
              class="uza-side-stripe bg-white rounded-lg p-3 pl-[18px] shadow-sm hover:shadow-uza-card cursor-pointer transition-shadow"
              :style="{ '--stripe-color': PRIO_COLOR[t.priority] }"
            >
              <!-- Top row: num + priority pill -->
              <div class="flex items-start justify-between gap-2 mb-1.5">
                <span v-if="t.num" class="text-[10px] uppercase tracking-uza-label2 text-slate-400 tabular-nums">
                  {{ t.num }}
                </span>
                <span
                  class="text-[9px] uppercase tracking-uza-label2 font-medium px-1.5 py-0.5 rounded whitespace-nowrap"
                  :style="{ background: PRIO_COLOR[t.priority] + '15', color: PRIO_COLOR[t.priority] }"
                >{{ PRIO_LABEL[t.priority] }}</span>
              </div>

              <!-- Title -->
              <div class="text-sm text-slate-900 leading-snug mb-2">{{ t.title }}</div>

              <!-- Badges — единый ряд с переносом -->
              <div
                v-if="t.direction_meta || t.linked_year || t.is_project || ['quarterly','monthly','ongoing'].includes(t.status)"
                class="flex flex-wrap items-center gap-[5px] mb-2"
              >
                <DirectionBadge v-if="t.direction_meta" :direction="t.direction_meta" variant="bar" size="sm" />

                <span v-if="t.linked_year"
                      class="inline-flex items-center gap-1 px-2 py-0.5 rounded-md text-[10px] font-medium"
                      style="background:rgba(239,159,39,.12);border:0.5px solid rgba(239,159,39,.30);color:#B87600"
                      title="Перенесена из прошлого года">
                  <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                    <line x1="19" y1="12" x2="5" y2="12"/><polyline points="12 19 5 12 12 5"/>
                  </svg>
                  FY{{ t.linked_year }}
                </span>

                <span v-if="t.is_project"
                      class="inline-flex items-center px-2 py-0.5 rounded-md text-[9px] uppercase tracking-uza-label2 font-medium"
                      style="background:rgba(127,119,221,.10);color:#534AB7">Проект</span>

                <span v-if="t.status === 'quarterly'"
                      class="inline-block px-2 py-0.5 text-[10px] rounded tabular-nums"
                      :style="isQuarterlyAllDone(t)
                              ? { background: '#DCFCE7', color: '#0E7A58' }
                              : { background: 'rgba(168,85,247,.13)', color: '#7E22CE' }">
                  <template v-if="isQuarterlyAllDone(t)">✓ Все кварталы</template>
                  <template v-else>Кв · {{ quarterlyDoneCount(t) }}/4</template>
                </span>

                <span v-else-if="t.status === 'monthly' || t.status === 'ongoing'"
                      class="inline-block px-2 py-0.5 text-[10px] rounded text-slate-500" style="background:#F1F5F9">
                  {{ t.status === 'monthly' ? 'Ежемесячно' : 'Постоянная' }} · вне %
                </span>
              </div>

              <!-- Входящие задачи проекта -->
              <div v-if="t.is_project && subtasksCache[t.id] && subtasksCache[t.id].length"
                   class="mb-2 rounded-md px-2 py-1.5" style="background:rgba(127,119,221,.05)">
                <div class="flex items-center justify-between mb-1">
                  <span class="text-[9px] uppercase tracking-uza-label2 text-slate-400 font-medium">Задачи</span>
                  <span class="text-[9px] text-slate-400 tabular-nums">
                    {{ subDone(t.id) }} из {{ subtasksCache[t.id].length }} · {{ subPct(t.id) }}%
                  </span>
                </div>
                <div class="space-y-0.5">
                  <div v-for="s in subtasksCache[t.id].slice(0, 5)" :key="s.id" class="flex items-center gap-1.5">
                    <span class="flex-shrink-0 rounded-full" style="width:7px;height:7px"
                          :style="{ background: subDot(s) }"></span>
                    <span class="flex-1 truncate text-[10.5px] leading-tight"
                          :class="s.status === 'done' ? 'text-slate-400 line-through' : 'text-slate-600'">{{ s.title }}</span>
                    <span class="flex-shrink-0 text-[9px] whitespace-nowrap" :style="{ color: subDot(s) }">{{ subWord(s) }}</span>
                  </div>
                  <div v-if="subtasksCache[t.id].length > 5" class="text-[9px] text-slate-400" style="padding-left:13px">
                    ещё {{ subtasksCache[t.id].length - 5 }}
                  </div>
                </div>
              </div>

              <!-- Footer: assignee (аватар инициалов) + due_date (иконка-календарь) -->
              <div class="flex items-center justify-between gap-2 text-[10px]">
                <span v-if="t.assignee_name || t.assignee_email"
                      class="flex items-center gap-1.5 min-w-0"
                      :title="t.assignee_email || ''">
                  <span class="inline-flex items-center justify-center flex-shrink-0 text-white font-medium"
                        style="width:20px;height:20px;border-radius:6px;font-size:9px;letter-spacing:.02em;background:linear-gradient(135deg,#8B7FFF,#6C5CE7)">
                    {{ initials(t.assignee_name || t.assignee_email) }}
                  </span>
                  <span class="truncate text-slate-600">{{ t.assignee_name || t.assignee_email }}</span>
                </span>
                <span v-else class="text-slate-300">не назначена</span>

                <span
                  v-if="t.due_date"
                  class="flex items-center gap-1 flex-shrink-0 tabular-nums"
                  :class="isOverdue(t) ? 'text-uza-red font-medium' : 'text-slate-500'"
                >
                  <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                    <rect x="3" y="4" width="18" height="18" rx="2"/><line x1="16" y1="2" x2="16" y2="6"/><line x1="8" y1="2" x2="8" y2="6"/><line x1="3" y1="10" x2="21" y2="10"/>
                  </svg>
                  {{ fmtDate(t.due_date) }}
                </span>
              </div>

              <!-- Progress bar -->
              <div v-if="t.progress_percent > 0" class="mt-2 h-1 bg-slate-100 rounded-uza-pill overflow-hidden">
                <div
                  class="h-full rounded-uza-pill"
                  :style="{ width: t.progress_percent + '%', background: col.color }"
                ></div>
              </div>
            </div>

            <!-- Empty column placeholder -->
            <div v-if="col.tasks.length === 0" class="text-[10px] text-slate-300 text-center py-6 uppercase tracking-uza-label2">
              Пусто
            </div>
          </div>
        </div>
      </div>
    </template>

    <!-- Editor modal -->
    <TaskProjectEditor v-if="editorOpen"
                       :entity="editorEntity"
                       kind="task"
                       @close="editorOpen = false"
                       @saved="onEditorSaved"/>
  </div>
</template>

<style scoped>
.line-clamp-2 {
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.def-badge {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  margin-top: 4px;
  padding: 3px 8px;
  background: rgba(127, 119, 221, 0.10);
  border: 0.5px solid rgba(127, 119, 221, 0.25);
  border-radius: 6px;
  font-size: 10.5px;
  font-weight: 600;
  color: var(--p-deep);
  white-space: nowrap;
  width: fit-content;
}
.def-badge:hover {
  background: rgba(127, 119, 221, 0.18);
}
</style>
