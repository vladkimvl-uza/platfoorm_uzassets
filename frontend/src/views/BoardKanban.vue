<script setup lang="ts">
import { ref, onMounted, computed, watch } from "vue";
import { useRoute, useRouter, RouterLink } from "vue-router";
import { boardsApi, tasksApi } from "@/api/tasks";
import { isModerationQueued } from "@/api/client";
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
  try {
    data.value = await boardsApi.getKanban(boardId.value, py.year);
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
              class="bg-white rounded-lg p-3 shadow-sm hover:shadow-uza-card cursor-pointer transition-shadow border-l-2"
              :style="{ 'border-left-color': PRIO_COLOR[t.priority] }"
            >
              <!-- Top row: num + priority pill -->
              <div class="flex items-start justify-between gap-2 mb-1.5">
                <span v-if="t.num" class="text-[10px] uppercase tracking-uza-label2 text-slate-400 tabular-nums">
                  {{ t.num }}
                </span>
                <span
                  class="text-[9px] uppercase tracking-uza-label2 font-medium px-1.5 py-0.5 rounded"
                  :style="{ background: PRIO_COLOR[t.priority] + '15', color: PRIO_COLOR[t.priority] }"
                  :title="PRIO_LABEL[t.priority]"
                >{{ t.priority[0].toUpperCase() }}</span>
              </div>

              <!-- Title -->
              <div class="text-sm text-slate-900 leading-snug mb-2">
                {{ t.title }}
                <div v-if="t.direction_meta" style="margin-top: 6px;">
                  <DirectionBadge :direction="t.direction_meta" size="sm" variant="bar" />
                </div>

                <!-- Direction badge -->
                <div v-if="t.direction_meta" class="mb-2">
                  <DirectionBadge :direction="t.direction_meta" variant="bar" size="sm" />
                </div>

                <!-- Direction badge -->
                <div v-if="t.direction_meta" class="mb-2">
                  <DirectionBadge :direction="t.direction_meta" variant="bar" size="sm" />
                </div>
              <div v-if="t.linked_year" class="def-badge" style="display:inline-flex;align-items:center;gap:5px;margin-top:4px;padding:3px 8px;background:rgba(127,119,221,.10);border:0.5px solid rgba(127,119,221,.25);border-radius:6px;font-size:10.5px;font-weight:600;color:#534AB7;width:fit-content">
                <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                  <line x1="5" y1="12" x2="19" y2="12"/>
                  <polyline points="12 5 19 12 12 19"/>
                </svg>
                Перенесена на {{ t.linked_year }}
              </div>
                <span v-if="t.is_project" class="ml-1 text-[9px] uppercase tracking-uza-label2 text-uza-purple">
                  · Проект
                </span>
              </div>

              <!-- Quarterly badge: closed-count / 4 -->
              <div v-if="t.status === 'quarterly'" class="mb-2">
                <span class="inline-block px-2 py-0.5 text-[10px] rounded tabular-nums"
                      :style="isQuarterlyAllDone(t)
                              ? { background: '#DCFCE7', color: '#0E7A58' }
                              : { background: 'rgba(168,85,247,.13)', color: '#7E22CE' }">
                  <template v-if="isQuarterlyAllDone(t)">✓ Все кварталы</template>
                  <template v-else>Ежеквартально · {{ quarterlyDoneCount(t) }}/4</template>
                </span>
              </div>

              <!-- Recurring/excluded marker for monthly/ongoing -->
              <div v-else-if="t.status === 'monthly' || t.status === 'ongoing'" class="mb-2">
                <span class="inline-block px-2 py-0.5 text-[10px] rounded text-slate-500"
                      style="background:#F1F5F9">
                  {{ t.status === 'monthly' ? 'Ежемесячно' : 'Постоянная' }} · вне %
                </span>
              </div>

              <!-- Footer: assignee + due_date -->
              <div class="flex items-center justify-between gap-2 text-[10px]">
                <span v-if="t.assignee_name || t.assignee_email"
                      class="truncate text-slate-500"
                      :title="t.assignee_email || ''">
                  {{ t.assignee_name || t.assignee_email }}
                </span>
                <span v-else class="text-slate-300">не назначена</span>

                <span
                  v-if="t.due_date"
                  class="flex-shrink-0 tabular-nums"
                  :class="isOverdue(t) ? 'text-uza-red font-medium' : 'text-slate-500'"
                >
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
  color: #534AB7;
  white-space: nowrap;
  width: fit-content;
}
.def-badge:hover {
  background: rgba(127, 119, 221, 0.18);
}
</style>
