<script setup lang="ts">
import { ref, computed, onMounted, watch } from "vue";
import { useRoute, useRouter, RouterLink } from "vue-router";
import { api } from "@/api/client";

import BadgeStatus from "@/components/BadgeStatus.vue";
import BadgePriority from "@/components/BadgePriority.vue";
import BadgeDeferred from "@/components/BadgeDeferred.vue";
import BadgeOverdue from "@/components/BadgeOverdue.vue";
import DirectionBadge from "@/components/DirectionBadge.vue";
import KpiCard2 from "@/components/KpiCard2.vue";
import TaskModal from "@/components/TaskModal.vue";
import TaskProjectEditor from "@/components/TaskProjectEditor.vue";
import { useToast } from "@/composables/useToast";
import type { TaskDetail } from "@/api/tasks";
import type { ProjectDetail as PD } from "@/api/projects";

const route = useRoute();
const router = useRouter();
const projectId = computed(() => String(route.params.id || ""));

const project = ref<any>(null);
const subtasks = ref<any[]>([]);
const loading = ref(true);
const errorMsg = ref<string | null>(null);

// Modal state
const modalOpen = ref(false);
const modalTaskId = ref<string | null>(null);
const modalIsProject = ref(false);

async function load() {
  loading.value = true;
  errorMsg.value = null;
  try {
    const [pr, ts] = await Promise.all([
      api.get<any>(`/projects/${projectId.value}`),
      api.get<any[]>(`/projects/${projectId.value}/tasks`),
    ]);
    project.value = pr.data;
    subtasks.value = (ts.data as any) || [];
  } catch (e: any) {
    errorMsg.value = e?.response?.status === 404
      ? "Проект не найден"
      : (e?.response?.data?.detail || e?.message || "Не удалось загрузить проект");
  } finally {
    loading.value = false;
  }
}

onMounted(load);
watch(projectId, load);

// ─── Computed ──────────────────────────────────────────────────
const tasksTotal = computed(() => subtasks.value.length);
const tasksDone = computed(() => subtasks.value.filter(t => t.status === "done").length);
const tasksOverdue = computed(() =>
  subtasks.value.filter(t => isOverdue(t)).length
);
const progressPct = computed(() => {
  if (!tasksTotal.value) return 0;
  return Math.round(tasksDone.value / tasksTotal.value * 100);
});
const progressColor = computed(() => {
  const p = progressPct.value;
  if (p >= 60) return "#1D9E75";
  if (p >= 30) return "#D97706";
  return "#E24B4A";
});

const projectIsOverdue = computed(() =>
  project.value && isOverdue(project.value)
);

// Дни до дедлайна
const daysToDeadline = computed(() => {
  if (!project.value?.due_date) return null;
  const diff = (new Date(project.value.due_date).getTime() - Date.now()) / 86400000;
  return Math.floor(diff);
});

// Сортировка задач: незавершённые сверху, по дедлайну, по № внутри
const sortedSubtasks = computed(() => {
  return [...subtasks.value].sort((a, b) => {
    // Done в конец
    const aDone = a.status === "done" ? 1 : 0;
    const bDone = b.status === "done" ? 1 : 0;
    if (aDone !== bDone) return aDone - bDone;
    // По № (numeric sort)
    const aNum = parseFloat(a.num || "999");
    const bNum = parseFloat(b.num || "999");
    return aNum - bNum;
  });
});

// ─── Helpers ────────────────────────────────────────────────────
function isOverdue(t: any): boolean {
  if (!t.due_date || t.status === "done") return false;
  return new Date(t.due_date) < new Date();
}

function formatDate(d: string | null | undefined): string {
  if (!d) return "—";
  return d.slice(0, 10).split("-").reverse().join(".");
}

function openSubtask(taskId: string) {
  modalTaskId.value = taskId;
  modalIsProject.value = false;
  modalOpen.value = true;
}

function openCreateSubtask() {
  modalTaskId.value = null;
  modalIsProject.value = false;
  modalOpen.value = true;
}

function openEditProject() {
  modalTaskId.value = projectId.value;
  modalIsProject.value = true;
  modalOpen.value = true;
}

function onSaved() {
  modalOpen.value = false;
  load();
}

function onDeleted() {
  modalOpen.value = false;
  // Если удалили сам проект — назад на список
  if (modalIsProject.value && modalTaskId.value === projectId.value) {
    router.push("/projects");
  } else {
    load();
  }
}
// === v9.1.1 additions (placed at end to avoid TDZ) ===
const editorEntity = ref<TaskDetail | PD | null>(null);
const toast = useToast();

const editorReady = computed(() => {
  if (!modalOpen.value) return false;
  // modalTaskId may not exist in this file -- guard with try
  let tid: string | null = null;
  try { tid = (modalTaskId as any)?.value ?? null; } catch (e) { tid = null; }
  if (tid === null) return true; // create mode
  return editorEntity.value !== null && (editorEntity.value as any).id === tid;
});

const editorKind = computed<"project" | "task">(() => {
  let isP = false;
  try { isP = (modalIsProject as any)?.value ?? false; } catch (e) { isP = false; }
  return isP ? "project" : "task";
});

watch(
  () => {
    try { return (modalTaskId as any)?.value ?? null; } catch (e) { return null; }
  },
  async (id) => {
    if (!id) {
      editorEntity.value = null;
      return;
    }
    let isP = false;
    try { isP = (modalIsProject as any)?.value ?? false; } catch (e) { isP = false; }
    const url = isP ? `/projects/${id}` : `/tasks/${id}`;
    try {
      const { data } = await api.get<any>(url);
      editorEntity.value = data;
    } catch (e: any) {
      toast.error("Ошибка загрузки: " + (e?.message || ""));
      modalOpen.value = false;
    }
  }
);

function onEditorSaved(id: string) {
  toast.success("Сохранено");
  modalOpen.value = false;
  try {
    if (typeof onSaved === "function") onSaved(id);
  } catch (e) { /* ignore */ }
}

function onEditorClose() {
  modalOpen.value = false;
}

</script>

<template>
  <div class="pd-page">
    <!-- Breadcrumbs -->
    <div class="pd-breadcrumbs">
      <RouterLink to="/projects" class="pd-bc-link">Проекты</RouterLink>
      <span class="pd-bc-sep">/</span>
      <span v-if="project" class="pd-bc-current">{{ project.num || "—" }}</span>
    </div>

    <!-- Loading -->
    <div v-if="loading" class="state-msg">Загрузка проекта…</div>

    <!-- Error -->
    <div v-else-if="errorMsg" class="state-msg error">⚠ {{ errorMsg }}</div>

    <!-- Project loaded -->
    <template v-else-if="project">
      <!-- Header card -->
      <div class="pd-header-card">
        <div class="pd-header-top">
          <div class="pd-header-l">
            <div class="pd-eyebrow">
              <span v-if="project.num" class="pd-num">{{ project.num }}</span>
              <span v-if="project.board_name" class="pd-board">· {{ project.board_name }}</span>
              <span v-if="project.portfolio_year" class="pd-year">· {{ project.portfolio_year }}</span>
            </div>
            <h1 class="pd-title">{{ project.title }}</h1>
            <div class="pd-meta">
              <BadgeStatus :status="project.status" size="md" />
              <BadgePriority v-if="project.priority && project.priority !== 'medium'"
                             :priority="project.priority" size="md" />
              <BadgeDeferred v-if="project.linked_year" :linked-year="project.linked_year" size="md" />
              <BadgeOverdue v-if="projectIsOverdue" size="md" />
              <DirectionBadge v-if="project.direction_meta"
                              :direction="project.direction_meta"
                              variant="bar" size="lg" />
            </div>
          </div>
          <div class="pd-header-r">
            <button class="btn-edit" @click="openEditProject">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor"
                   stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/>
                <path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"/>
              </svg>
              Редактировать
            </button>
          </div>
        </div>

        <p v-if="project.description" class="pd-desc">{{ project.description }}</p>
      </div>

      <!-- KPI strip -->
      <div class="pd-kpi-strip">
        <KpiCard2 label="ВСЕГО ЗАДАЧ"
                  :value="tasksTotal"
                  accent="#7F77DD"
                  :animation-delay="0" />
        <KpiCard2 label="ЗАВЕРШЕНО"
                  :value="`${tasksDone} / ${tasksTotal}`"
                  accent="#1D9E75"
                  :animation-delay="80" />
        <KpiCard2 label="ПРОГРЕСС"
                  :value="`${progressPct}%`"
                  :accent="progressColor"
                  :animation-delay="160" />
        <KpiCard2 label="ДЕДЛАЙН"
                  :value="formatDate(project.due_date)"
                  :sub-value="daysToDeadline != null
                    ? (daysToDeadline >= 0
                        ? `${daysToDeadline} дн.`
                        : `просрочен на ${Math.abs(daysToDeadline)} дн.`)
                    : ''"
                  :accent="projectIsOverdue ? '#EF4444' : '#378ADD'"
                  :animation-delay="240" />
        <KpiCard2 v-if="tasksOverdue > 0"
                  label="ПРОСРОЧЕНО"
                  :value="tasksOverdue"
                  accent="#EF4444"
                  :animation-delay="320" />
      </div>

      <!-- Subtasks -->
      <div class="pd-section">
        <div class="pd-section-header">
          <h2 class="pd-section-title">
            Задачи проекта
            <span class="pd-section-count">{{ tasksTotal }}</span>
          </h2>
          <button class="btn-add-task" @click="openCreateSubtask">+ Задача</button>
        </div>

        <div v-if="!subtasks.length" class="state-msg pd-empty">
          В этом проекте ещё нет задач
        </div>

        <div v-else class="pd-task-list">
          <div v-for="t in sortedSubtasks" :key="t.id"
               class="pd-task-row"
               :class="{ 'is-done': t.status === 'done' }"
               @click="openSubtask(t.id)">
            <div class="pd-task-num">
              <span class="num-pill">{{ t.num || "—" }}</span>
            </div>
            <div class="pd-task-body">
              <div class="pd-task-title">{{ t.title }}</div>
              <div class="pd-task-meta">
                <DirectionBadge v-if="t.direction_meta"
                                :direction="t.direction_meta"
                                variant="bar" size="sm" />
                <BadgePriority v-if="t.priority && t.priority !== 'medium'"
                               :priority="t.priority" size="sm" />
                <BadgeDeferred v-if="t.linked_year" :linked-year="t.linked_year" size="sm" />
              </div>
            </div>
            <div class="pd-task-status">
              <BadgeStatus :status="t.status" size="sm" />
            </div>
            <div class="pd-task-deadline">
              <BadgeOverdue v-if="isOverdue(t)" size="sm" />
              <span v-else class="deadline-text">{{ formatDate(t.due_date) }}</span>
            </div>
            <div class="pd-task-assignee">
              <span v-if="t.assignee_name" class="assignee-name">{{ t.assignee_name }}</span>
              <span v-else class="assignee-empty">—</span>
            </div>
          </div>
        </div>
      </div>
    </template>

    <!-- Modal -->
    <TaskProjectEditor v-if="editorReady"
                       :entity="(editorEntity as any)"
                       :kind="editorKind"
                       @close="onEditorClose"
                       @saved="onEditorSaved" />
  </div>
</template>

<style scoped>
.pd-page {
  padding: 24px 32px;
  max-width: 1400px;
  margin: 0 auto;
}

/* Breadcrumbs */
.pd-breadcrumbs {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 14px;
  font-size: 11px;
  color: var(--t3, #64748B);
}
.pd-bc-link {
  color: var(--t3, #64748B);
  text-decoration: none;
  transition: color .12s;
}
.pd-bc-link:hover { color: #7F77DD; }
.pd-bc-sep { color: #CBD5E1; }
.pd-bc-current {
  font-weight: 500;
  color: var(--t1, #1E2A4A);
  font-variant-numeric: tabular-nums;
}

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
.pd-empty {
  margin-top: 12px;
}

/* Header card */
.pd-header-card {
  background: #fff;
  border-radius: 14px;
  border: 1px solid #E2E8F0;
  padding: 22px 26px;
  margin-bottom: 16px;
  box-shadow: 0 4px 12px rgba(15, 23, 60, 0.04);
}
.pd-header-top {
  display: flex;
  align-items: flex-start;
  gap: 16px;
}
.pd-header-l { flex: 1; min-width: 0; }
.pd-header-r { flex-shrink: 0; }

.pd-eyebrow {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 10.5px;
  font-weight: 500;
  color: var(--t3, #64748B);
  letter-spacing: 0.06em;
  text-transform: uppercase;
  margin-bottom: 8px;
  flex-wrap: wrap;
}
.pd-num {
  background: rgba(127, 119, 221, 0.10);
  color: #7F77DD;
  padding: 2px 7px;
  border-radius: 5px;
  font-weight: 600;
  font-variant-numeric: tabular-nums;
}
.pd-board {
  color: var(--t3, #64748B);
  font-weight: 500;
}
.pd-year {
  color: var(--t3, #64748B);
}

.pd-title {
  font-size: 22px;
  font-weight: 500;
  letter-spacing: -0.01em;
  color: var(--t1, #1E2A4A);
  margin: 0 0 12px;
  line-height: 1.3;
}

.pd-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  align-items: center;
}

.pd-desc {
  margin: 16px 0 0;
  font-size: 13px;
  color: var(--t2, #475569);
  line-height: 1.6;
  padding-top: 14px;
  border-top: 1px solid #F1F5F9;
}

.btn-edit {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 8px 14px;
  background: transparent;
  color: var(--t2, #475569);
  border: 1px solid #E2E8F0;
  border-radius: 11px;
  font-size: 12px;
  font-weight: 500;
  cursor: pointer;
  transition: all .12s;
}
.btn-edit:hover {
  background: #F1F5F9;
  border-color: #CBD5E1;
}

/* KPI strip */
.pd-kpi-strip {
  display: grid;
  grid-template-columns: repeat(5, 1fr);
  gap: 12px;
  margin-bottom: 18px;
}
@media (max-width: 1100px) {
  .pd-kpi-strip { grid-template-columns: repeat(3, 1fr); }
}
@media (max-width: 700px) {
  .pd-kpi-strip { grid-template-columns: repeat(2, 1fr); }
}

/* Section */
.pd-section {
  background: #fff;
  border-radius: 12px;
  border: 1px solid #E2E8F0;
  box-shadow: 0 4px 12px rgba(15, 23, 60, 0.04);
  overflow: hidden;
}
.pd-section-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 14px 20px;
  border-bottom: 1px solid #E2E8F0;
  background: #FAFBFC;
}
.pd-section-title {
  margin: 0;
  font-size: 14px;
  font-weight: 500;
  color: var(--t1, #1E2A4A);
  letter-spacing: -0.005em;
}
.pd-section-count {
  margin-left: 8px;
  font-size: 11px;
  font-weight: 600;
  color: var(--t3, #64748B);
  background: #F1F5F9;
  padding: 2px 8px;
  border-radius: 6px;
  font-variant-numeric: tabular-nums;
}
.btn-add-task {
  padding: 6px 14px;
  background: #7F77DD;
  color: white;
  border: none;
  border-radius: 11px;
  font-weight: 500;
  font-size: 11.5px;
  cursor: pointer;
  transition: background .12s;
}
.btn-add-task:hover { background: #6E66CC; }

/* Task list */
.pd-task-list {
  padding: 4px 0;
}
.pd-task-row {
  display: grid;
  grid-template-columns: 70px 1.5fr 110px 110px 180px;
  gap: 12px;
  padding: 11px 20px;
  border-bottom: 1px solid #F1F5F9;
  align-items: center;
  cursor: pointer;
  transition: background .12s;
}
.pd-task-row:hover { background: #FAFBFC; }
.pd-task-row:last-child { border-bottom: none; }
.pd-task-row.is-done { opacity: 0.55; }
.pd-task-row.is-done .pd-task-title { text-decoration: line-through; }

.pd-task-num { display: flex; align-items: flex-start; padding-top: 2px; }
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

.pd-task-body { min-width: 0; align-self: flex-start; }
.pd-task-title {
  font-size: 13px;
  font-weight: 500;
  color: var(--t1, #1E2A4A);
  line-height: 1.4;
}
.pd-task-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-top: 5px;
  align-items: center;
}

.deadline-text {
  font-size: 11.5px;
  color: var(--t2, #475569);
  font-variant-numeric: tabular-nums;
}

.assignee-name {
  font-size: 11.5px;
  color: var(--t1, #1E2A4A);
}
.assignee-empty {
  font-size: 11.5px;
  color: var(--t3, #94A3B8);
}

@media (max-width: 1000px) {
  .pd-task-row {
    grid-template-columns: 60px 1fr 100px 100px;
  }
  .pd-task-assignee { display: none; }
}
@media (max-width: 700px) {
  .pd-task-row {
    grid-template-columns: 50px 1fr 80px;
  }
  .pd-task-deadline { display: none; }
}
</style>
