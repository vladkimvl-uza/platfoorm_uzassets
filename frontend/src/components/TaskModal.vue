<script setup lang="ts">
import { ref, watch, computed, onMounted } from "vue";
import { api } from "@/api/client";
import ModalShell from "./ModalShell.vue";
import DirectionBadge from "./DirectionBadge.vue";

const props = defineProps<{
  open: boolean;
  // null/undefined = create new, otherwise = edit
  taskId?: string | null;
  // Pre-fill values when creating new
  defaultBoardId?: string | null;
  defaultStatus?: string;
  defaultDirection?: string;
  defaultIsProject?: boolean;
}>();

const emit = defineEmits<{
  (e: "close"): void;
  (e: "saved", taskId: string): void;
  (e: "deleted", taskId: string): void;
}>();

// ─── Form state ────────────────────────────────────────────────
const entityType = ref<"task" | "project">(props.defaultIsProject ? "project" : "task");
const title = ref("");
const description = ref("");
const num = ref("");
const boardId = ref<string>("");
const directionCode = ref<string>("");
const startDate = ref<string>("");      // YYYY-MM-DD
const deadline = ref<string>("");        // YYYY-MM-DD
const status = ref<string>("new");
const priority = ref<string>("medium");
const assigneeEmail = ref<string>("");
const consultantId = ref<string>("");
const linkedYearEnabled = ref(false);
const linkedYear = ref<number | null>(null);
const linkedTaskId = ref<string>("");

// ─── Loaded data ───────────────────────────────────────────────
const boards = ref<{ id: string; name: string }[]>([]);
const directions = ref<{ id: string; code: string; label: string; color: string }[]>([]);
const consultantsList = ref<{ id: string; name: string }[]>([]);

const isEdit = computed(() => !!props.taskId);
const submitLabel = computed(() => {
  if (isEdit.value) return "Сохранить";
  return entityType.value === "project" ? "Создать проект" : "Создать задачу";
});
const titleText = computed(() => isEdit.value
  ? `Редактирование ${entityType.value === "project" ? "проекта" : "задачи"}`
  : `Новая ${entityType.value === "project" ? "запись (проект)" : "запись (задача)"}`
);

const titleError = ref(false);
const saving = ref(false);
const errorMsg = ref<string | null>(null);

// ─── Lookup direction object by code (for badge preview) ──────
const directionObj = computed(() => directions.value.find(d => d.code === directionCode.value) || null);

// ─── Status definitions (matches legacy COLS) ───────────────
const STATUSES = [
  { id: "init",      label: "Инициирование",  fg: "#64748B" },
  { id: "new",       label: "Не начато",      fg: "#94A3B8" },
  { id: "active",    label: "В процессе",     fg: "#3B82F6" },
  { id: "review",    label: "На согласовании", fg: "#F59E0B" },
  { id: "done",      label: "Завершено",      fg: "#10B981" },
  { id: "quarterly", label: "Ежеквартально",  fg: "#7E22CE" },
  { id: "monthly",   label: "Ежемесячно",     fg: "#4338CA" },
  { id: "ongoing",   label: "Постоянно",      fg: "#0E7490" },
];

// ─── Load lookups ──────────────────────────────────────────────
async function loadLookups() {
  try {
    const [bd, dr] = await Promise.all([
      api.get<{ companies: any[] }>("/companies?limit=100"),
      api.get<{ directions: any[] }>("/directions"),
    ]);
    boards.value = (bd.data.companies || []).map(c => ({ id: c.id, name: c.name_short || c.name_ru }));
    directions.value = dr.data.directions || [];
  } catch (e) {
    console.warn("Could not load lookups", e);
  }
}

// ─── Load task data when editing ──────────────────────────────
async function loadTask() {
  if (!props.taskId) return;
  try {
    const r = await api.get<any>(`/tasks/${props.taskId}`);
    const t = r.data;
    title.value = t.title || "";
    description.value = t.description || "";
    num.value = t.num || "";
    boardId.value = t.board_id || "";
    directionCode.value = t.direction || "";
    startDate.value = t.start_date ? t.start_date.slice(0, 10) : "";
    deadline.value = t.due_date ? t.due_date.slice(0, 10) : "";
    status.value = t.status || "new";
    priority.value = t.priority || "medium";
    assigneeEmail.value = t.assignee_email || "";
    consultantId.value = t.consultant || (t.consultants?.[0] ?? "");
    linkedYear.value = t.linked_year || null;
    linkedTaskId.value = t.linked_task_id || "";
    linkedYearEnabled.value = !!t.linked_year;
    entityType.value = t.is_project ? "project" : "task";
  } catch (e: any) {
    errorMsg.value = e?.response?.data?.detail || "Не удалось загрузить задачу";
  }
}

// ─── Init defaults when creating new ──────────────────────────
function applyDefaults() {
  if (!isEdit.value) {
    boardId.value = props.defaultBoardId || "";
    status.value = props.defaultStatus || "new";
    directionCode.value = props.defaultDirection || "";
    entityType.value = props.defaultIsProject ? "project" : "task";
    title.value = "";
    description.value = "";
    num.value = "";
    startDate.value = "";
    deadline.value = "";
    priority.value = "medium";
    assigneeEmail.value = "";
    consultantId.value = "";
    linkedYear.value = null;
    linkedTaskId.value = "";
    linkedYearEnabled.value = false;
  }
}

watch(() => props.open, (v) => {
  if (v) {
    errorMsg.value = null;
    titleError.value = false;
    if (isEdit.value) {
      loadTask();
    } else {
      applyDefaults();
    }
  }
});

onMounted(loadLookups);

// ─── Save ──────────────────────────────────────────────────────
async function handleSave() {
  if (!title.value.trim()) {
    titleError.value = true;
    return;
  }
  if (!boardId.value) {
    errorMsg.value = "Выберите компанию";
    return;
  }
  saving.value = true;
  errorMsg.value = null;
  try {
    const payload: any = {
      title: title.value.trim(),
      description: description.value.trim() || null,
      num: num.value.trim() || null,
      board_id: boardId.value,
      direction: directionCode.value || null,
      start_date: startDate.value || null,
      due_date: deadline.value || null,
      status: status.value,
      priority: priority.value,
      assignee_email: assigneeEmail.value || null,
      is_project: entityType.value === "project",
    };
    if (linkedYearEnabled.value && linkedYear.value) {
      payload.linked_year = linkedYear.value;
      payload.linked_task_id = linkedTaskId.value || null;
    }

    let savedId: string;
    if (isEdit.value) {
      const r = await api.patch<any>(`/tasks/${props.taskId}`, payload);
      savedId = r.data.id;
    } else {
      const r = await api.post<any>("/tasks", payload);
      savedId = r.data.id;
    }
    emit("saved", savedId);
    emit("close");
  } catch (e: any) {
    errorMsg.value = e?.response?.data?.detail || e?.message || "Ошибка сохранения";
  } finally {
    saving.value = false;
  }
}

async function handleDelete() {
  if (!props.taskId) return;
  if (!confirm("Удалить задачу безвозвратно?")) return;
  saving.value = true;
  try {
    await api.delete(`/tasks/${props.taskId}`);
    emit("deleted", props.taskId);
    emit("close");
  } catch (e: any) {
    errorMsg.value = e?.response?.data?.detail || "Не удалось удалить";
  } finally {
    saving.value = false;
  }
}

// Auto-grow title textarea
function autoGrow(el: Event) {
  const t = el.target as HTMLTextAreaElement;
  t.style.height = "auto";
  t.style.height = t.scrollHeight + "px";
}
</script>

<template>
  <ModalShell :open="open" :title="titleText" size="md" @close="emit('close')">
    <div class="tm-form">
      <!-- Segment toggle (Задача / Проект) — only for create mode -->
      <div v-if="!isEdit" class="seg-toggle">
        <button :class="['seg-btn', { active: entityType === 'task' }]"
                @click="entityType = 'task'">Задача</button>
        <button :class="['seg-btn', { active: entityType === 'project' }]"
                @click="entityType = 'project'">Проект</button>
      </div>

      <!-- Title (auto-grow textarea) -->
      <div class="tm-field">
        <label class="tm-lbl">Название *</label>
        <textarea v-model="title" rows="1" placeholder="Введите название…"
                  class="tm-input tm-input-title"
                  :class="{ 'tm-error': titleError }"
                  @input="(e) => { autoGrow(e); titleError = false; }"></textarea>
      </div>

      <!-- Company -->
      <div class="tm-field">
        <label class="tm-lbl">Компания</label>
        <select v-model="boardId" class="tm-select">
          <option value="">— выберите —</option>
          <option v-for="b in boards" :key="b.id" :value="b.id">{{ b.name }}</option>
        </select>
      </div>

      <!-- Number + Direction (2 cols) -->
      <div class="tm-row" style="grid-template-columns: 80px 1fr;">
        <div>
          <label class="tm-lbl">Номер</label>
          <input v-model="num" :placeholder="entityType === 'project' ? '3' : '3.1'"
                 class="tm-input" style="text-align: center;" />
        </div>
        <div>
          <label class="tm-lbl">Направление</label>
          <select v-model="directionCode" class="tm-select">
            <option value="">— не выбрано —</option>
            <option v-for="d in directions" :key="d.code" :value="d.code">{{ d.label }}</option>
          </select>
          <DirectionBadge v-if="directionObj" :direction="directionObj"
                          variant="bar" size="sm" style="margin-top: 4px;" />
        </div>
      </div>

      <!-- Dates + Status (3 cols) -->
      <div class="tm-row" style="grid-template-columns: 1fr 1fr 1fr;">
        <div>
          <label class="tm-lbl">Дата начала</label>
          <input type="date" v-model="startDate" class="tm-input" />
        </div>
        <div>
          <label class="tm-lbl">Дедлайн</label>
          <input type="date" v-model="deadline" class="tm-input" />
        </div>
        <div>
          <label class="tm-lbl">Статус</label>
          <select v-model="status" class="tm-select">
            <option v-for="s in STATUSES" :key="s.id" :value="s.id"
                    :style="{ color: s.fg }">{{ s.label }}</option>
          </select>
        </div>
      </div>

      <!-- Priority + Assignee + Consultant (3 cols) -->
      <div class="tm-row" style="grid-template-columns: 1fr 1fr 1fr;">
        <div>
          <label class="tm-lbl">Приоритет</label>
          <select v-model="priority" class="tm-select">
            <option value="low">Низкий</option>
            <option value="medium">Средний</option>
            <option value="high">Высокий</option>
          </select>
        </div>
        <div>
          <label class="tm-lbl">Ответственный (email)</label>
          <input v-model="assigneeEmail" placeholder="user@uz-assets.uz" class="tm-input" />
        </div>
        <div>
          <label class="tm-lbl">Консультант</label>
          <select v-model="consultantId" class="tm-select">
            <option value="">— нет —</option>
            <option v-for="f in consultantsList" :key="f.id" :value="f.id">{{ f.name }}</option>
          </select>
        </div>
      </div>

      <!-- Description -->
      <div class="tm-field">
        <label class="tm-lbl">Описание</label>
        <textarea v-model="description" rows="3" placeholder="Необязательно…"
                  class="tm-input" style="resize: vertical; min-height: 60px; max-height: 200px;"></textarea>
      </div>

      <!-- Linked year (transfer to other year) -->
      <div class="tm-link-block" v-if="isEdit">
        <div class="tm-link-head">
          <label class="tm-link-lbl">
            <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor"
                 stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" style="opacity: .7;">
              <path d="M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71"/>
              <path d="M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71"/>
            </svg>
            Перенесена в другой год
          </label>
          <label class="tm-link-toggle">
            <input type="checkbox" v-model="linkedYearEnabled" />
            <span>{{ linkedYearEnabled ? "связано" : "указать" }}</span>
          </label>
        </div>
        <div v-if="linkedYearEnabled" class="tm-link-fields">
          <label class="tm-link-sub">Перенести на:</label>
          <select v-model.number="linkedYear" class="tm-select" style="font-size: 11px;">
            <option v-for="y in [2024, 2025, 2026, 2027, 2028]" :key="y" :value="y">{{ y }}</option>
          </select>
        </div>
      </div>

      <!-- Error message -->
      <div v-if="errorMsg" class="tm-err">⚠ {{ errorMsg }}</div>
    </div>

    <template #footer>
      <button v-if="isEdit" class="btn-d" @click="handleDelete" :disabled="saving">Удалить</button>
      <div style="flex: 1;"></div>
      <button class="btn-s" @click="emit('close')" :disabled="saving">Отмена</button>
      <button class="btn-p" @click="handleSave" :disabled="saving">
        {{ saving ? "Сохранение…" : submitLabel }}
      </button>
    </template>
  </ModalShell>
</template>

<style scoped>
.tm-form {
  display: flex;
  flex-direction: column;
  gap: 10px;
  font-family: var(--font, system-ui);
}

/* Segment toggle */
.seg-toggle {
  display: flex;
  background: var(--bg3, #F1F5F9);
  border-radius: 10px;
  padding: 2px;
  gap: 2px;
  margin-bottom: 4px;
}
.seg-btn {
  flex: 1;
  padding: 6px 0;
  border: none;
  border-radius: 8px;
  font-size: 12px;
  cursor: pointer;
  transition: all .15s;
  background: transparent;
  color: var(--t3, var(--t3));
  font-weight: 400;
}
.seg-btn.active {
  background: var(--bg1, #fff);
  color: #7F77DD;
  font-weight: 600;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.08);
}

.tm-field { display: flex; flex-direction: column; }
.tm-row { display: grid; gap: 8px; }

.tm-lbl {
  display: block;
  font-size: 9px;
  font-weight: 600;
  color: var(--t3, #94A3B8);
  text-transform: uppercase;
  letter-spacing: 0.06em;
  margin-bottom: 4px;
}

.tm-input, .tm-select {
  padding: 8px 10px;
  border: 1.5px solid var(--border-input);
  border-radius: 10px;
  background: var(--bg2, #F8FAFC);
  font-family: inherit;
  font-size: 12px;
  color: var(--t1, #1E2A4A);
  outline: none;
  width: 100%;
  box-sizing: border-box;
  transition: border-color .18s, box-shadow .18s;
}
.tm-input-title {
  font-size: 13px;
  font-weight: 500;
  resize: none;
  overflow: hidden;
  min-height: 36px;
}
.tm-input:focus, .tm-select:focus {
  border-color: #7F77DD;
  box-shadow: 0 0 0 3px rgba(127, 119, 221, 0.15);
}
.tm-input.tm-error {
  border-color: var(--sev-high);
  background: rgba(226, 75, 74, 0.04);
}
.tm-select {
  appearance: none;
  -webkit-appearance: none;
  padding-right: 28px;
  background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='12' height='12' viewBox='0 0 12 12'%3E%3Cpath d='M3 4.5l3 3 3-3' fill='none' stroke='%239CA3AF' stroke-width='1.5' stroke-linecap='round'/%3E%3C/svg%3E");
  background-repeat: no-repeat;
  background-position: right 8px center;
  cursor: pointer;
}

.tm-link-block {
  padding: 10px 12px;
  background: rgba(127, 119, 221, 0.05);
  border: 0.5px solid rgba(127, 119, 221, 0.20);
  border-radius: 8px;
}
.tm-link-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 8px;
}
.tm-link-lbl {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 11px;
  color: var(--t2, #475569);
  font-weight: 500;
}
.tm-link-toggle {
  display: flex;
  align-items: center;
  gap: 6px;
  cursor: pointer;
  font-size: 11px;
  color: var(--t2, #475569);
}
.tm-link-fields {
  display: grid;
  grid-template-columns: 90px 1fr;
  gap: 8px;
  align-items: center;
}
.tm-link-sub {
  font-size: 11px;
  color: var(--t3, #94A3B8);
}

.tm-err {
  padding: 8px 12px;
  background: rgba(226, 75, 74, 0.08);
  border: 0.5px solid rgba(226, 75, 74, 0.30);
  border-radius: 8px;
  color: #993D3D;
  font-size: 11.5px;
}

/* Footer buttons (in modal footer slot) */
.btn-p {
  padding: 8px 16px;
  background: #7F77DD;
  color: white;
  border: none;
  border-radius: 8px;
  font-size: 12px;
  font-weight: 500;
  cursor: pointer;
  transition: background .12s;
}
.btn-p:hover:not(:disabled) { background: #6E66CC; }
.btn-p:disabled { opacity: 0.6; cursor: not-allowed; }

.btn-s {
  padding: 8px 16px;
  background: transparent;
  color: var(--t2, #475569);
  border: 1px solid var(--border-input);
  border-radius: 8px;
  font-size: 12px;
  cursor: pointer;
  transition: all .12s;
}
.btn-s:hover { background: var(--bg3, #F1F5F9); }

.btn-d {
  padding: 8px 16px;
  background: rgba(226, 75, 74, 0.08);
  color: var(--sev-critical);
  border: 1px solid rgba(226, 75, 74, 0.20);
  border-radius: 8px;
  font-size: 11px;
  cursor: pointer;
  transition: all .12s;
}
.btn-d:hover { background: rgba(226, 75, 74, 0.12); }
</style>
