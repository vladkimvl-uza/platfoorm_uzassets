<script setup lang="ts">
/**
 * TaskProjectEditor.vue
 * ─────────────────────────────────────────────────────────────────
 * Universal editor for Project or Task — Glassmorphism Enterprise.
 * Replaces the legacy TaskModal.vue and old TaskProjectEditor.vue.
 *
 * Features:
 *   • Inline-editable title with pencil icon
 *   • № field (free text, e.g. "ПР-2026-014")
 *   • Основание dropdown (shareholder/pp/pkm/custom) + № основания
 *   • Type pill toggle (одноразовый/регулярный) — locked after creation
 *   • Recurring sub-type (постоянный/ежеквартальный/ежемесячный)
 *   • Quarter checkboxes Q1/Q2/Q3/Q4 → progress = checked × 25%
 *   • Status badges (4 for one-shot, dynamic for recurring)
 *   • Ответственный (assignee) with name + email
 *   • Консультант dropdown (multi) using BadgeConsultant
 *   • Направление (8 strategic directions + custom)
 *   • Экономический эффект (план/факт/единица/валюта/заметка)
 *   • Перенос на FY+1 (linked_project_id with future-year validation)
 *   • Комментарии: timeline + textarea, edit/delete for author/admin
 *   • RBAC banner (Owner/Admin/Куратор/Исполнитель/Read-only)
 *   • Footer: Архивировать | Отмена | Сохранить
 *
 * Design:
 *   • UzAssets palette (#7F77DD purple, #1D9E75 teal, #EF9F27 amber)
 *   • Glass surface: rgba(255,255,255,0.6) + backdrop-filter blur(28px)
 *   • Modal-in 380ms cubic-bezier(0.34, 1.2, 0.64, 1) overshoot
 *   • Stagger-animated cards (60/100/140/180/220ms delays)
 *   • Progress shimmer (700ms cubic-bezier)
 *   • prefers-reduced-motion → all animations off
 */

import { ref, computed, onMounted, watch, nextTick } from "vue";
import { useAuthStore } from "@/stores/auth";
import { api } from "@/api/client";
import { projectsApi, type ProjectDetail, type ProjectUpdate, type ProjectCreate } from "@/api/projects";
import type { TaskDetail, TaskUpdate, TaskCreate, EconomicEffect, QuartersObject } from "@/api/tasks";
import { consultantsApi, type ConsultantBrief } from "@/api/consultants";
import { STATUS_LABELS, STATUS_COLORS } from "@/utils/progress";
import BadgeConsultant from "./BadgeConsultant.vue";
import UserAutocomplete from "./UserAutocomplete.vue";
import MentionableTextarea from "./MentionableTextarea.vue";
import AttachmentsPanel from "./Attachments/AttachmentsPanel.vue";

// =====================================================================
// Props / Emits
// =====================================================================

type Kind = "project" | "task";

const props = defineProps<{
  entity: ProjectDetail | TaskDetail | null;  // null = create mode
  kind: Kind;
  projectId?: string | null;  // when creating a task inside a project
}>();

const emit = defineEmits<{
  (e: "close"): void;
  (e: "saved", id: string): void;
}>();

// =====================================================================
// Auth & RBAC
// =====================================================================

const auth = useAuthStore();
const currentUserEmail = computed(() => auth.user?.email || "");
const currentUserId = computed(() => auth.user?.id || "");

const isOwner = computed(() => currentUserEmail.value === "v.kim@uz-assets.uz");
const isAdmin = computed(() => {
  if (isOwner.value) return true;
  const u: any = auth.user;
  if (!u) return false;
  if (u.is_admin || u.is_owner) return true;
  const roles = u.roles || [];
  return Array.isArray(roles) && roles.some((r: string) => ["admin", "owner", "ROLE_ADMIN", "ROLE_OWNER"].includes(r));
});

const isAssignee = computed(() =>
  !!props.entity?.assignee_email && props.entity.assignee_email === currentUserEmail.value
);

const accessLevel = computed<"owner" | "admin" | "kurator" | "executor" | "readonly">(() => {
  if (isOwner.value) return "owner";
  if (isAdmin.value) return "admin";
  if (isAssignee.value) return "kurator";
  return "readonly";
});

const canEdit = computed(() => ["owner", "admin", "kurator"].includes(accessLevel.value));
const canDelete = computed(() => ["owner", "admin"].includes(accessLevel.value));
const canManageRefs = computed(() => ["owner", "admin"].includes(accessLevel.value));

// =====================================================================
// Form state
// =====================================================================

const isCreate = computed(() => !props.entity);

// "task" | "project" — used by AttachmentsPanel to hit the right endpoint
const entityAttachKind = computed<"task" | "project">(
  () => ((props.entity as any)?.is_project ? "project" : "task"),
);

const formTitle = ref("");
const formNum = ref("");
const formDescription = ref("");
const formStatus = ref<string>("init");
const formPriority = ref<"high" | "medium" | "low">("medium");
const formAssigneeEmail = ref("");
const formAssigneeName = ref("");
const formDueDate = ref("");
const formStartDate = ref("");
const formPortfolioYear = ref<number>(new Date().getFullYear());
const formDirection = ref("");
const formScope = ref("");
const formTags = ref<string[]>([]);

// New fields (Project Editor)
const formGroundType = ref<string>("");           // shareholder | pp | pkm | custom
const formGroundNumber = ref("");
const formProjectType = ref<"onetime" | "recurring">("onetime");
const formRecurringPeriod = ref<"ongoing" | "quarterly" | "monthly">("ongoing");
const formLinkedProjectId = ref<string | null>(null);
const formConsultantId = ref<string | null>(null);
const formConsultantLegacy = ref<string[]>([]);   // legacy string array fallback

// Quarters
const formQuarters = ref<QuartersObject>({
  q1: false, q2: false, q3: false, q4: false,
});

// Economic effect
const formHasEffect = ref(false);
const formEffectPlan = ref<number | null>(null);
const formEffectFact = ref<number | null>(null);
const formEffectCurrency = ref("UZS");
const formEffectUnit = ref("млрд");
const formEffectNote = ref("");

// Title inline edit toggle
const titleEditing = ref(false);
const titleInput = ref<HTMLInputElement | null>(null);

// =====================================================================
// Reference data (loaded async)
// =====================================================================

const consultants = ref<ConsultantBrief[]>([]);
const futureProjects = ref<Array<{ id: string; title: string; portfolio_year: number }>>([]);

// Parent project (for tasks) — shown as a "Relates to project" card
const parentProject = ref<{ id: string; title: string; num: string | null; portfolio_year: number | null } | null>(null);

// Linked-year info (transfer hint) — read-only badge
const linkedFromYear = ref<number | null>(null);   // task or project came FROM this year
const linkedToYear = ref<number | null>(null);     // this entity was transferred TO that year (linked_project_id resolved)
const directions = ref<string[]>([
  "Операционная эффективность",
  "Цифровизация",
  "ESG",
  "Система закупок",
  "Корпоративное управление",
  "Финансы / риски / аудит",
  "Стратегическое управление",
  "Организационное развитие",
]);
const groundTypes = ref([
  { value: "shareholder", label: "Ожидания Акционера" },
  { value: "pp",          label: "Поручение Президента" },
  { value: "pkm",         label: "Постановление КМ" },
]);

// =====================================================================
// Comments
// =====================================================================

interface Comment {
  id: string;
  author_id: string | null;
  author_name: string | null;
  author_email: string | null;
  body: string;
  is_edited: boolean;
  created_at: string;
  updated_at: string;
}

const comments = ref<Comment[]>([]);
const newCommentText = ref("");
const editingCommentId = ref<string | null>(null);
const editingCommentText = ref("");
const commentsBusy = ref(false);

// =====================================================================
// UI state
// =====================================================================

const saving = ref(false);
const error = ref<string | null>(null);
const consultantDropdownOpen = ref(false);

// =====================================================================
// Computed
// =====================================================================

const statusOptions = computed(() => {
  if (props.kind === "task" || formProjectType.value === "onetime") {
    return ["init", "active", "review", "done"];
  }
  // Recurring
  if (formRecurringPeriod.value === "ongoing") return ["ongoing"];
  if (formRecurringPeriod.value === "quarterly") return ["quarterly"];
  if (formRecurringPeriod.value === "monthly") return ["monthly"];
  return ["init", "active", "review", "done"];
});

const computedProgress = computed(() => {
  if (formStatus.value === "done") return 100;
  if (formStatus.value === "quarterly") {
    const q = formQuarters.value;
    let n = 0;
    if (q.q1) n++; if (q.q2) n++; if (q.q3) n++; if (q.q4) n++;
    return n * 25;
  }
  if (formStatus.value === "active" || formStatus.value === "review") return 50;
  return 0;
});

const accessBannerText = computed(() => {
  switch (accessLevel.value) {
    case "owner":   return "Режим: Owner · полный доступ";
    case "admin":   return "Режим: Admin · полный доступ";
    case "kurator": return "Режим: Куратор / Ответственный · редактирование";
    case "executor": return "Режим: Исполнитель · только своя задача";
    default:        return "Режим: Read-only";
  }
});

const selectedConsultant = computed(() =>
  consultants.value.find(c => c.id === formConsultantId.value) || null
);

// =====================================================================
// Initialization — populate form from entity OR defaults for create
// =====================================================================

function readExtra<T = any>(key: string, fallback: T): T {
  const e: any = props.entity;
  if (!e || !e.extra || typeof e.extra !== "object") return fallback;
  const v = e.extra[key];
  return v === undefined || v === null ? fallback : (v as T);
}

function populateForm() {
  const e = props.entity;
  if (!e) {
    // Create mode — defaults
    formStatus.value = "init";
    formPriority.value = "medium";
    formProjectType.value = "onetime";
    formRecurringPeriod.value = "ongoing";
    formPortfolioYear.value = new Date().getFullYear();
    return;
  }

  formTitle.value = e.title || "";
  formNum.value = e.num || "";
  formDescription.value = e.description || "";
  formStatus.value = e.status || "init";
  formPriority.value = (e.priority as any) || "medium";
  formAssigneeEmail.value = e.assignee_email || "";
  formAssigneeName.value = e.assignee_name || "";
  formDueDate.value = e.due_date ? e.due_date.split("T")[0] : "";
  formStartDate.value = e.start_date ? e.start_date.split("T")[0] : "";
  formPortfolioYear.value = e.portfolio_year || new Date().getFullYear();
  formDirection.value = e.direction || "";
  formScope.value = e.scope || "";
  formTags.value = Array.isArray(e.tags) ? [...e.tags] : [];

  // Project-only new fields
  if (props.kind === "project") {
    const pe = e as ProjectDetail & {
      ground_type?: string | null;
      project_type?: string | null;
      linked_project_id?: string | null;
      consultant_id?: string | null;
    };
    formGroundType.value = pe.ground_type || "";
    formProjectType.value = (pe.project_type as any) || "onetime";
    formLinkedProjectId.value = pe.linked_project_id || null;
    formConsultantId.value = pe.consultant_id || null;
    formGroundNumber.value = readExtra<string>("ground_number", "");
    formRecurringPeriod.value = readExtra<any>("recurring_period", "ongoing");
  }

  // Quarters
  const q = e.quarters as QuartersObject | null;
  if (q) {
    formQuarters.value = {
      q1: !!q.q1, q2: !!q.q2, q3: !!q.q3, q4: !!q.q4,
    };
  }

  // Linked-year (legacy transfer marker — Phase 13)
  // Both tasks and projects can have `linked_year` in their extra/columns.
  const ee: any = e;
  if (ee.linked_year && typeof ee.linked_year === "number") {
    linkedFromYear.value = ee.linked_year;
  } else if (ee.extra && ee.extra.linked_year) {
    linkedFromYear.value = Number(ee.extra.linked_year) || null;
  }

  // Consultant — handle legacy string/array AND new consultant_id
  const cons = e.consultant;
  if (typeof cons === "string" && cons.trim()) {
    formConsultantLegacy.value = cons.split(",").map(s => s.trim()).filter(Boolean);
  } else if (Array.isArray(cons)) {
    formConsultantLegacy.value = cons;
  }

  // Economic effect
  if (e.economic_effect && typeof e.economic_effect === "object") {
    formHasEffect.value = true;
    const ee: any = e.economic_effect;
    formEffectPlan.value = ee.plan ?? ee.value ?? null;
    formEffectFact.value = ee.fact ?? null;
    formEffectCurrency.value = ee.currency || "UZS";
    formEffectUnit.value = ee.unit || "млрд";
    formEffectNote.value = ee.note || "";
  }

  // Comments — backend now returns them in detail
  const cmts = (e as any).comments;
  if (Array.isArray(cmts)) {
    comments.value = cmts as Comment[];
  } else {
    comments.value = [];
  }
  // Defensive: also explicitly load via dedicated endpoint, since some
  // call sites pass a brief entity (no comments[]) into the editor.
  if (e && (e as any).id) {
    reloadComments();
  }
}

async function reloadComments() {
  if (!props.entity?.id) return;
  try {
    const url = (props.entity as any).is_project
      ? `/projects/${props.entity.id}/comments`
      : `/tasks/${props.entity.id}/comments`;
    const { data } = await api.get<Comment[]>(url);
    if (Array.isArray(data)) comments.value = data;
  } catch (e) {
    console.warn("[editor] reloadComments failed:", e);
  }
}

// =====================================================================
// Loading reference data
// =====================================================================

async function loadConsultants() {
  try {
    const list = await consultantsApi.list();
    consultants.value = list.filter(c => c.is_active !== false);
  } catch (e) {
    console.warn("Failed to load consultants:", e);
  }
}

async function loadFutureProjects() {
  if (props.kind !== "project") return;
  try {
    const nextYear = (props.entity?.portfolio_year || new Date().getFullYear()) + 1;
    const resp = await projectsApi.list({ portfolio_year: nextYear, limit: 100 });
    futureProjects.value = resp.items.map(p => ({
      id: p.id,
      title: p.title,
      portfolio_year: p.portfolio_year || nextYear,
    }));
  } catch (e) {
    console.warn("Failed to load future projects:", e);
  }
}

/** For tasks: load parent project info (id, title, num) to show "Relates to project" card. */
async function loadParentProject() {
  if (props.kind !== "task") return;
  const e: any = props.entity;
  const projectId = e?.project_id;
  if (!projectId) return;
  try {
    const p = await projectsApi.getOne(projectId);
    parentProject.value = {
      id: p.id,
      title: p.title,
      num: p.num,
      portfolio_year: p.portfolio_year,
    };
  } catch (err) {
    console.warn("Failed to load parent project:", err);
  }
}

/** For projects: if linked_project_id is set, fetch its year for display. */
async function loadLinkedProjectInfo() {
  if (props.kind !== "project") return;
  const linkedId = formLinkedProjectId.value;
  if (!linkedId) return;
  try {
    const p = await projectsApi.getOne(linkedId);
    linkedToYear.value = p.portfolio_year;
  } catch (err) {
    console.warn("Failed to load linked project:", err);
  }
}

// =====================================================================
// Save / Archive
// =====================================================================

function buildPayload(): any {
  const base: any = {
    title: formTitle.value.trim(),
    description: formDescription.value || null,
    num: formNum.value || null,
    status: formStatus.value,
    priority: formPriority.value,
    assignee_email: formAssigneeEmail.value || null,
    assignee_name: formAssigneeName.value || null,
    due_date: formDueDate.value || null,
    start_date: formStartDate.value || null,
    portfolio_year: formPortfolioYear.value,
    direction: formDirection.value || null,
    scope: formScope.value || null,
    tags: formTags.value.length ? formTags.value : null,
  };

  if (formStatus.value === "quarterly") {
    base.quarters = formQuarters.value;
  }

  if (formHasEffect.value) {
    const ee: EconomicEffect & { plan?: number; fact?: number; unit?: string } = {
      currency: formEffectCurrency.value,
      note: formEffectNote.value || undefined,
    };
    if (formEffectPlan.value !== null) (ee as any).plan = formEffectPlan.value;
    if (formEffectFact.value !== null) (ee as any).fact = formEffectFact.value;
    (ee as any).unit = formEffectUnit.value;
    base.economic_effect = ee;
  }

  // Project-only fields
  if (props.kind === "project") {
    base.ground_type = formGroundType.value || null;
    base.ground_number = formGroundNumber.value || null;
    base.project_type = formProjectType.value;
    base.recurring_period = formProjectType.value === "recurring" ? formRecurringPeriod.value : null;
    base.linked_project_id = formLinkedProjectId.value || null;
    base.consultant_id = formConsultantId.value || null;
  }

  // Task-only fields
  if (props.kind === "task") {
    base.consultant_id = formConsultantId.value || null;
    if (props.projectId && isCreate.value) {
      base.project_id = props.projectId;
    }
  }

  return base;
}

async function handleSave() {
  if (!formTitle.value.trim()) {
    error.value = "Название обязательно";
    return;
  }
  saving.value = true;
  error.value = null;

  try {
    const payload = buildPayload();
    let savedId: string;

    if (props.kind === "project") {
      if (isCreate.value) {
        const created = await projectsApi.create(payload as ProjectCreate);
        savedId = created.id;
      } else {
        const updated = await projectsApi.update(props.entity!.id, payload as ProjectUpdate);
        savedId = updated.id;
      }
    } else {
      // task — using direct api calls (tasksApi present but to keep this self-contained)
      if (isCreate.value) {
        const { data } = await api.post<TaskDetail>("/tasks", payload as TaskCreate);
        savedId = data.id;
      } else {
        const { data } = await api.patch<TaskDetail>(`/tasks/${props.entity!.id}`, payload as TaskUpdate);
        savedId = data.id;
      }
    }

    emit("saved", savedId);
    emit("close");
  } catch (e: any) {
    error.value = e?.response?.data?.detail || e?.message || "Ошибка сохранения";
  } finally {
    saving.value = false;
  }
}

async function handleArchive() {
  if (!props.entity) return;
  if (!confirm(`Архивировать ${props.kind === "project" ? "проект" : "задачу"} "${formTitle.value}"?`)) return;
  saving.value = true;
  try {
    if (props.kind === "project") {
      await projectsApi.archive(props.entity.id);
    } else {
      await api.delete(`/tasks/${props.entity.id}`);
    }
    emit("saved", props.entity.id);
    emit("close");
  } catch (e: any) {
    error.value = e?.response?.data?.detail || e?.message || "Ошибка архивирования";
  } finally {
    saving.value = false;
  }
}

// =====================================================================
// Comments handlers
// =====================================================================

function commentEndpoint(): string {
  return props.kind === "project"
    ? `/projects/${props.entity?.id}/comments`
    : `/tasks/${props.entity?.id}/comments`;
}

function commentItemEndpoint(commentId: string): string {
  return props.kind === "project"
    ? `/comments/projects/${commentId}`
    : `/comments/tasks/${commentId}`;
}

async function handleAddComment() {
  console.log("[editor] handleAddComment fired", {
    entityId: props.entity?.id,
    textLen: newCommentText.value?.length,
  });
  if (!props.entity || !newCommentText.value.trim()) return;
  commentsBusy.value = true;
  try {
    const { data } = await api.post<Comment>(commentEndpoint(), { body: newCommentText.value.trim() });
    console.log("[editor] comment POSTed, response:", data);
    if (data && data.id) {
      comments.value = [data, ...comments.value];
    }
    newCommentText.value = "";
    // Always reload from server — source of truth
    await reloadComments();
  } catch (e: any) {
    console.error("[editor] add comment failed:", e);
    error.value = e?.response?.data?.detail || "Не удалось добавить комментарий";
  } finally {
    commentsBusy.value = false;
  }
}

function startEditComment(c: Comment) {
  editingCommentId.value = c.id;
  editingCommentText.value = c.body;
}

function cancelEditComment() {
  editingCommentId.value = null;
  editingCommentText.value = "";
}

async function saveEditComment(commentId: string) {
  if (!editingCommentText.value.trim()) return;
  commentsBusy.value = true;
  try {
    const { data } = await api.patch<Comment>(commentItemEndpoint(commentId), { body: editingCommentText.value.trim() });
    const idx = comments.value.findIndex(c => c.id === commentId);
    if (idx >= 0) comments.value[idx] = data;
    cancelEditComment();
  } catch (e: any) {
    error.value = e?.response?.data?.detail || "Не удалось сохранить правку";
  } finally {
    commentsBusy.value = false;
  }
}

async function deleteComment(commentId: string) {
  if (!confirm("Удалить комментарий?")) return;
  commentsBusy.value = true;
  try {
    await api.delete(commentItemEndpoint(commentId));
    comments.value = comments.value.filter(c => c.id !== commentId);
  } catch (e: any) {
    error.value = e?.response?.data?.detail || "Не удалось удалить комментарий";
  } finally {
    commentsBusy.value = false;
  }
}

function canEditComment(c: Comment): boolean {
  return isAdmin.value || c.author_id === currentUserId.value;
}

// =====================================================================
// Helpers
// =====================================================================

function formatDate(iso: string | null | undefined): string {
  if (!iso) return "";
  try {
    const d = new Date(iso);
    return d.toLocaleString("ru-RU", { day: "2-digit", month: "2-digit", year: "numeric", hour: "2-digit", minute: "2-digit" });
  } catch { return iso; }
}

function statusLabel(s: string): string {
  return STATUS_LABELS[s] || s;
}
function statusColor(s: string): string {
  return STATUS_COLORS[s] || "#888780";
}

/** Open the parent project — closes current modal first, then navigates. */
function openParentProject() {
  if (!parentProject.value) return;
  emit("close");
  // The parent component (Tasks.vue / BoardKanban.vue / ProjectDetail.vue) listens
  // to a router push or emits a "navigate" event. Simplest: use window.location hash
  // OR emit a custom event. For now, we use router via window for compatibility.
  try {
    window.location.hash = `#/projects/${parentProject.value.id}`;
  } catch {}
}

function startEditTitle() {
  if (!canEdit.value) return;
  titleEditing.value = true;
  nextTick(() => titleInput.value?.focus());
}

function commitTitle() {
  titleEditing.value = false;
  if (!formTitle.value.trim()) {
    formTitle.value = props.entity?.title || "Без названия";
  }
}

function toggleQuarter(q: "q1" | "q2" | "q3" | "q4") {
  if (!canEdit.value) return;
  formQuarters.value[q] = !formQuarters.value[q];
  // Auto-switch to "done" if all 4 closed
  const all = formQuarters.value.q1 && formQuarters.value.q2 && formQuarters.value.q3 && formQuarters.value.q4;
  if (all && formStatus.value === "quarterly") {
    // keep status as quarterly but reflect 100% via computedProgress
  }
}

// =====================================================================
// Lifecycle
// =====================================================================

onMounted(async () => {
  populateForm();
  await Promise.all([
    loadConsultants(),
    loadFutureProjects(),
    loadParentProject(),
    loadLinkedProjectInfo(),
  ]);
});

watch(() => props.entity, populateForm, { deep: false });

// Close on Esc
function onKeydown(e: KeyboardEvent) {
  if (e.key === "Escape") emit("close");
}
onMounted(() => window.addEventListener("keydown", onKeydown));
import { onBeforeUnmount } from "vue";
onBeforeUnmount(() => window.removeEventListener("keydown", onKeydown));
</script>

<template>
  <div class="editor-backdrop" @click.self="emit('close')">
    <div class="editor-shell">
      <!-- ─── Header strip ─── -->
      <header class="ed-header">
        <div class="ed-header-left">
          <span class="kind-pill" :class="`kind-${kind}`">
            {{ kind === "project" ? "ПРОЕКТ" : "ЗАДАЧА" }}
          </span>

          <!-- Transfer badges -->
          <span v-if="linkedFromYear" class="transfer-badge from">
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
              <path d="M5 12h14M12 5l7 7-7 7"/>
            </svg>
            Перенесена из FY{{ linkedFromYear }}
          </span>
          <span v-if="linkedToYear" class="transfer-badge to">
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
              <path d="M5 12h14M12 5l7 7-7 7"/>
            </svg>
            Перенесён в FY{{ linkedToYear }}
          </span>

          <input
            v-if="canEdit"
            class="num-input"
            v-model="formNum"
            placeholder="ПР-2026-014"
            :disabled="!canEdit"
          />
          <span v-else class="num-static">{{ formNum || "—" }}</span>
        </div>

        <div class="ed-header-right">
          <span class="access-banner">{{ accessBannerText }}</span>
          <button class="ed-close" @click="emit('close')" aria-label="Закрыть">
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <path d="M18 6L6 18M6 6l12 12"/>
            </svg>
          </button>
        </div>
      </header>

      <!-- ─── Title row ─── -->
      <section class="title-section">
        <div class="title-row" @click="!titleEditing && startEditTitle()">
          <input
            v-if="titleEditing"
            ref="titleInput"
            v-model="formTitle"
            class="title-input"
            @blur="commitTitle"
            @keydown.enter.prevent="commitTitle"
            placeholder="Название..."
          />
          <h1 v-else class="title-display">
            {{ formTitle || "Без названия" }}
            <button v-if="canEdit" class="pencil-btn" @click.stop="startEditTitle" aria-label="Редактировать">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <path d="M17 3a2.85 2.83 0 1 1 4 4L7.5 20.5 2 22l1.5-5.5z"/>
              </svg>
            </button>
          </h1>
        </div>
      </section>

      <!-- ─── Parent project card (tasks only) ─── -->
      <section v-if="kind === 'task' && parentProject" class="parent-project-card">
        <div class="ppc-icon">
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <path d="M3 7h18v12a2 2 0 01-2 2H5a2 2 0 01-2-2V7z"/>
            <path d="M3 7l2-3h6l2 3"/>
          </svg>
        </div>
        <div class="ppc-body">
          <div class="ppc-meta">
            <span class="ppc-label">Относится к проекту</span>
            <span v-if="parentProject.portfolio_year" class="ppc-year">FY{{ parentProject.portfolio_year }}</span>
          </div>
          <div class="ppc-title-row">
            <span v-if="parentProject.num" class="ppc-num">{{ parentProject.num }}</span>
            <span class="ppc-title">{{ parentProject.title }}</span>
          </div>
        </div>
        <button class="ppc-open" @click="openParentProject" title="Открыть проект">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <path d="M7 17L17 7M7 7h10v10"/>
          </svg>
        </button>
      </section>

      <!-- ─── Body grid ─── -->
      <div class="ed-body">

        <!-- ─── Card 1: Основание + Тип ─── -->
        <section v-if="kind === 'project'" class="card stagger-1">
          <div class="card-label">ОСНОВАНИЕ И ТИП</div>

          <div class="field-grid-2">
            <div class="field">
              <label>Основание</label>
              <select v-model="formGroundType" :disabled="!canEdit">
                <option value="">— не указано —</option>
                <option v-for="g in groundTypes" :key="g.value" :value="g.value">{{ g.label }}</option>
                <option v-if="canManageRefs" value="custom">+ Добавить</option>
              </select>
            </div>

            <div class="field">
              <label>№ основания</label>
              <input v-model="formGroundNumber" placeholder="ПКМ-123 от 01.01.2026" :disabled="!canEdit"/>
            </div>
          </div>

          <div class="field">
            <label>Тип проекта <span v-if="!isCreate" class="locked-hint">залочен</span></label>
            <div class="pill-toggle">
              <button
                class="pill"
                :class="{ active: formProjectType === 'onetime' }"
                :disabled="!isCreate || !canEdit"
                @click="formProjectType = 'onetime'"
              >Одноразовый</button>
              <button
                class="pill"
                :class="{ active: formProjectType === 'recurring' }"
                :disabled="!isCreate || !canEdit"
                @click="formProjectType = 'recurring'"
              >Регулярный</button>
              <button v-if="canManageRefs" class="pill pill-ghost" disabled>+ Добавить</button>
            </div>
          </div>

          <div v-if="formProjectType === 'recurring'" class="field">
            <label>Периодичность</label>
            <div class="pill-toggle">
              <button class="pill sm" :class="{ active: formRecurringPeriod === 'ongoing' }"
                      :disabled="!canEdit" @click="formRecurringPeriod = 'ongoing'; formStatus = 'ongoing'">Постоянный</button>
              <button class="pill sm" :class="{ active: formRecurringPeriod === 'quarterly' }"
                      :disabled="!canEdit" @click="formRecurringPeriod = 'quarterly'; formStatus = 'quarterly'">Ежеквартальный</button>
              <button class="pill sm" :class="{ active: formRecurringPeriod === 'monthly' }"
                      :disabled="!canEdit" @click="formRecurringPeriod = 'monthly'; formStatus = 'monthly'">Ежемесячный</button>
            </div>
          </div>
        </section>

        <!-- ─── Card 2: Статус + Прогресс ─── -->
        <section class="card stagger-2">
          <div class="card-label">СТАТУС И ПРОГРЕСС</div>

          <div v-if="statusOptions.length > 1" class="status-row">
            <button
              v-for="s in statusOptions" :key="s"
              class="status-badge"
              :class="{ active: formStatus === s }"
              :style="formStatus === s ? `--accent: ${statusColor(s)}` : ''"
              :disabled="!canEdit"
              @click="formStatus = s"
            >
              <span class="dot" :style="`background: ${statusColor(s)}`"></span>
              {{ statusLabel(s) }}
            </button>
          </div>

          <!-- Quarters checkboxes -->
          <div v-if="formStatus === 'quarterly'" class="quarters-grid">
            <label v-for="q in (['q1','q2','q3','q4'] as const)" :key="q"
                   class="quarter-check" :class="{ checked: formQuarters[q] }">
              <input type="checkbox" :checked="formQuarters[q]"
                     :disabled="!canEdit" @change="toggleQuarter(q)" />
              <span class="q-label">{{ q.toUpperCase() }}</span>
              <svg v-if="formQuarters[q]" class="q-tick" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#1D9E75" stroke-width="3">
                <polyline points="20 6 9 17 4 12"/>
              </svg>
            </label>
          </div>

          <div class="progress-block">
            <div class="progress-label">
              <span>Прогресс</span>
              <span class="progress-pct">{{ computedProgress }}%</span>
            </div>
            <div class="progress-track">
              <div class="progress-fill" :style="`width: ${computedProgress}%`"></div>
            </div>
          </div>
        </section>

        <!-- ─── Card 3: Ответственный + Консультант + Направление ─── -->
        <section class="card stagger-3">
          <div class="card-label">ОТВЕТСТВЕННЫЕ</div>

          <div class="field">
            <label>Ответственный</label>
            <UserAutocomplete
              :email="formAssigneeEmail"
              :name="formAssigneeName"
              :disabled="!canEdit"
              @update:email="formAssigneeEmail = $event"
              @update:name="formAssigneeName = $event"
            />
          </div>

          <div class="field">
            <label>Консультант</label>
            <div class="consultant-picker" :class="{ open: consultantDropdownOpen }">
              <button class="consultant-trigger" :disabled="!canEdit"
                      @click="consultantDropdownOpen = !consultantDropdownOpen">
                <BadgeConsultant v-if="selectedConsultant"
                                 :consultants="[{ id: selectedConsultant.id, abbr: selectedConsultant.abbr || selectedConsultant.code, color: selectedConsultant.color_hex || '#7F77DD' }]"
                                 size="md" />
                <span v-if="selectedConsultant" class="consultant-name">{{ selectedConsultant.name_ru }}</span>
                <span v-else class="consultant-placeholder">— выберите —</span>
                <svg class="caret" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                  <polyline points="6 9 12 15 18 9"/>
                </svg>
              </button>
              <div v-if="consultantDropdownOpen" class="consultant-menu">
                <div class="consultant-opt" @click="formConsultantId = null; consultantDropdownOpen = false">
                  <span class="consultant-placeholder">— очистить —</span>
                </div>
                <div v-for="c in consultants" :key="c.id"
                     class="consultant-opt"
                     :class="{ active: c.id === formConsultantId }"
                     @click="formConsultantId = c.id; consultantDropdownOpen = false">
                  <BadgeConsultant
                    :consultants="[{ id: c.id, abbr: c.abbr || c.code, color: c.color_hex || '#7F77DD' }]"
                    size="md" />
                  <span>{{ c.name_ru }}</span>
                  <span v-if="c.is_big4" class="big4">Big 4</span>
                </div>
              </div>
            </div>
          </div>

          <div class="field-grid-2">
            <div class="field">
              <label>Направление</label>
              <select v-model="formDirection" :disabled="!canEdit">
                <option value="">— не выбрано —</option>
                <option v-for="d in directions" :key="d" :value="d">{{ d }}</option>
              </select>
            </div>

            <div class="field">
              <label>Год портфеля</label>
              <input type="number" v-model.number="formPortfolioYear" :disabled="!canEdit" min="2020" max="2040"/>
            </div>
          </div>
        </section>

        <!-- ─── Card 4: Сроки ─── -->
        <section class="card stagger-4">
          <div class="card-label">СРОКИ</div>
          <div class="field-grid-2">
            <div class="field">
              <label>Старт</label>
              <input type="date" v-model="formStartDate" :disabled="!canEdit"/>
            </div>
            <div class="field">
              <label>Дедлайн</label>
              <input type="date" v-model="formDueDate" :disabled="!canEdit"/>
            </div>
          </div>
        </section>

        <!-- ─── Card 5: Эконом эффект ─── -->
        <section class="card stagger-5 effect-card">
          <div class="card-label flex">
            <span>ЭКОНОМИЧЕСКИЙ ЭФФЕКТ</span>
            <label class="switch">
              <input type="checkbox" v-model="formHasEffect" :disabled="!canEdit"/>
              <span class="slider"></span>
            </label>
          </div>

          <div v-if="formHasEffect" class="effect-grid">
            <div class="field">
              <label>План</label>
              <input type="number" v-model.number="formEffectPlan" :disabled="!canEdit" placeholder="0"/>
            </div>
            <div class="field">
              <label>Факт</label>
              <input type="number" v-model.number="formEffectFact" :disabled="!canEdit" placeholder="0"/>
            </div>
            <div class="field">
              <label>Ед.</label>
              <select v-model="formEffectUnit" :disabled="!canEdit">
                <option value="млрд">млрд</option>
                <option value="млн">млн</option>
                <option value="тыс">тыс</option>
              </select>
            </div>
            <div class="field">
              <label>Валюта</label>
              <select v-model="formEffectCurrency" :disabled="!canEdit">
                <option value="UZS">UZS</option>
                <option value="USD">USD</option>
                <option value="EUR">EUR</option>
              </select>
            </div>
            <div class="field full">
              <label>Заметка</label>
              <input v-model="formEffectNote" placeholder="Комментарий к эффекту" :disabled="!canEdit"/>
            </div>
          </div>
        </section>

        <!-- ─── Card 6: Перенос на FY+1 ─── -->
        <section v-if="kind === 'project' && !isCreate" class="card stagger-6">
          <div class="card-label">ПЕРЕНОС НА FY+1</div>
          <div class="field">
            <label>Связанный проект (год+1)</label>
            <select v-model="formLinkedProjectId" :disabled="!canEdit">
              <option :value="null">— не перенесён —</option>
              <option v-for="p in futureProjects" :key="p.id" :value="p.id">
                FY{{ p.portfolio_year }} · {{ p.title }}
              </option>
            </select>
            <p class="hint">Перенос разрешён только на FY+1 и далее. Текущий проект остаётся в FY{{ formPortfolioYear }}.</p>
          </div>
        </section>

        <!-- ─── Card 7: Описание ─── -->
        <section class="card stagger-7 desc-card">
          <div class="card-label">ОПИСАНИЕ</div>
          <MentionableTextarea v-model="formDescription" :disabled="!canEdit" rows="3"
                               placeholder="Дополнительная информация... (введите @ для упоминания)" />
        </section>

        <!-- ─── Cards 7a / 7b: Результаты + Документы (attachments) ─── -->
        <section v-if="!isCreate && props.entity?.id" class="card stagger-7">
          <AttachmentsPanel
            title="РЕЗУЛЬТАТЫ"
            hint="Подтверждающие файлы (отчёты, акты, презентации)"
            :kind="entityAttachKind"
            :parent-id="String(props.entity.id)"
            :is-result-doc="true"
            filter="result"
            empty-text="Файлы-результаты не загружены"
            :current-user-id="currentUserId"
            :is-admin="isAdmin"
          />
        </section>

        <section v-if="!isCreate && props.entity?.id" class="card stagger-7">
          <AttachmentsPanel
            title="ДОКУМЕНТЫ"
            hint="Прочие файлы по этой работе"
            :kind="entityAttachKind"
            :parent-id="String(props.entity.id)"
            :is-result-doc="false"
            filter="regular"
            empty-text="Документов нет"
            :current-user-id="currentUserId"
            :is-admin="isAdmin"
          />
        </section>

        <!-- ─── Card 8: Комментарии ─── -->
        <section v-if="!isCreate" class="card stagger-8 comments-card">
          <div class="card-label">КОММЕНТАРИИ <span class="cnt">{{ comments.length }}</span></div>

          <div class="comment-input-row">
            <MentionableTextarea
              v-model="newCommentText"
              rows="2"
              placeholder="Написать комментарий... (введите @ для упоминания)"
              :disabled="commentsBusy"
            />
            <button class="btn btn-primary sm"
                    :disabled="commentsBusy || !newCommentText.trim()"
                    @click="handleAddComment">
              Отправить
            </button>
          </div>

          <div class="comments-list">
            <div v-for="c in comments" :key="c.id" class="comment-item">
              <div class="comment-head">
                <div class="avatar" :style="`background: ${statusColor('init')}`">
                  {{ (c.author_name || c.author_email || "?").charAt(0).toUpperCase() }}
                </div>
                <div class="comment-meta">
                  <span class="author">{{ c.author_name || c.author_email || "—" }}</span>
                  <span class="dot-sep">·</span>
                  <span class="date">{{ formatDate(c.created_at) }}</span>
                  <span v-if="c.is_edited" class="edited">(изменён)</span>
                </div>
                <div v-if="canEditComment(c)" class="comment-actions">
                  <button class="link-btn" @click="startEditComment(c)" v-if="editingCommentId !== c.id">Изменить</button>
                  <button class="link-btn danger" @click="deleteComment(c.id)" v-if="editingCommentId !== c.id">Удалить</button>
                </div>
              </div>

              <div v-if="editingCommentId === c.id" class="comment-edit">
                <textarea v-model="editingCommentText" rows="2"></textarea>
                <div class="comment-edit-buttons">
                  <button class="btn sm" @click="cancelEditComment">Отмена</button>
                  <button class="btn btn-primary sm" @click="saveEditComment(c.id)">Сохранить</button>
                </div>
              </div>

              <p v-else class="comment-body">{{ c.body }}</p>
            </div>

            <div v-if="!comments.length" class="empty">Пока нет комментариев</div>
          </div>
        </section>

      </div>

      <!-- ─── Footer ─── -->
      <footer class="ed-footer">
        <div class="footer-left">
          <button v-if="!isCreate && canDelete" class="btn btn-danger" @click="handleArchive" :disabled="saving">
            Архивировать
          </button>
        </div>

        <div class="footer-right">
          <p v-if="error" class="error-msg">{{ error }}</p>
          <button class="btn" @click="emit('close')" :disabled="saving">Отмена</button>
          <button class="btn btn-primary" @click="handleSave" :disabled="saving || !canEdit">
            {{ saving ? "Сохранение..." : (isCreate ? "Создать" : "Сохранить") }}
          </button>
        </div>
      </footer>
    </div>
  </div>
</template>

<style scoped>
/* ─── Palette ─── */
:root, .editor-shell {
  --uza-purple: #7F77DD;
  --uza-teal:   #1D9E75;
  --uza-amber:  #EF9F27;
  --uza-blue:   #378ADD;
  --uza-red:    #E24B4A;
  --uza-navy:   #1E2A4A;
  --uza-gray:   #888780;
  --uza-bg:     #FAFAFB;
}

/* ─── Backdrop & shell ─── */
.editor-backdrop {
  position: fixed; inset: 0; z-index: 1000;
  /* Opaque dark backdrop — solid, no transparency (per user request) */
  background: #1E2A4A;
  display: flex; align-items: flex-start; justify-content: center;
  overflow-y: auto;
  padding: 32px 16px;
  animation: fadeIn 220ms ease;
}

@keyframes fadeIn {
  from { opacity: 0; }
  to   { opacity: 1; }
}

.editor-shell {
  width: 100%; max-width: 920px;
  /* Solid white — no glass blur (per user request) */
  background: #FFFFFF;
  border: 0.5px solid #E5E7EB;
  border-radius: 20px;
  box-shadow:
    0 28px 70px -14px rgba(67,56,202,0.22),
    0 8px 24px rgba(15,23,60,0.08);
  display: flex; flex-direction: column;
  overflow: hidden;
  animation: shellIn 380ms cubic-bezier(0.34, 1.2, 0.64, 1);
}

@keyframes shellIn {
  from { opacity: 0; transform: translateY(20px) scale(0.97); }
  to   { opacity: 1; transform: translateY(0)    scale(1); }
}

/* ─── Header ─── */
.ed-header {
  display: flex; align-items: center; justify-content: space-between;
  padding: 14px 24px;
  background: linear-gradient(90deg, rgba(127,119,221,0.06), rgba(29,158,117,0.04));
  border-bottom: 1px solid rgba(15,23,60,0.06);
}
.ed-header-left, .ed-header-right { display: flex; align-items: center; gap: 12px; }

.kind-pill {
  font-size: 10px; font-weight: 600; letter-spacing: 0.08em;
  padding: 4px 10px; border-radius: 6px;
}
.kind-pill.kind-project { background: rgba(127,119,221,0.12); color: #5B53C2; }
.kind-pill.kind-task    { background: rgba(55,138,221,0.12);  color: #2A6FB8; }

/* ─── Transfer badge (legacy linked_year + new linked_project_id) ─── */
.transfer-badge {
  display: inline-flex; align-items: center; gap: 4px;
  font-size: 10px; font-weight: 500; letter-spacing: 0.02em;
  padding: 4px 8px; border-radius: 6px;
}
.transfer-badge.from {
  background: rgba(239,159,39,0.12);
  color: #B87600;
}
.transfer-badge.to {
  background: rgba(29,158,117,0.12);
  color: #137A57;
}
.transfer-badge svg { flex-shrink: 0; }

/* ─── Parent project card (tasks only) ─── */
.parent-project-card {
  margin: 0 24px 12px;
  padding: 12px 14px;
  display: flex; align-items: center; gap: 12px;
  background: linear-gradient(90deg, rgba(127,119,221,0.06), rgba(127,119,221,0.02));
  border: 1px solid rgba(127,119,221,0.18);
  border-radius: 10px;
  transition: all 200ms;
  /* top-stripe via ::before (purple) */
  position: relative;
  overflow: hidden;
}
.parent-project-card::before {
  content: ""; position: absolute; top: 0; left: 0; right: 0;
  height: 3px; background: var(--uza-purple);
  border-top-left-radius: inherit; border-top-right-radius: inherit;
  transform-origin: left center;
  animation:
    uzaStripeDrawIn .8s cubic-bezier(0.34, 1.2, 0.64, 1) 100ms both,
    uzaStripeBreathe 2.8s ease-in-out 1s infinite;
  pointer-events: none; z-index: 1;
}
.parent-project-card:hover {
  background: linear-gradient(90deg, rgba(127,119,221,0.1), rgba(127,119,221,0.04));
  border-color: rgba(127,119,221,0.3);
}
.ppc-icon {
  width: 36px; height: 36px;
  display: flex; align-items: center; justify-content: center;
  background: rgba(127,119,221,0.14);
  color: var(--uza-purple);
  border-radius: 8px;
  flex-shrink: 0;
}
.ppc-body { flex: 1; min-width: 0; }
.ppc-meta { display: flex; align-items: center; gap: 8px; margin-bottom: 2px; }
.ppc-label {
  font-size: 10px; font-weight: 500; letter-spacing: 0.06em;
  color: var(--uza-gray); text-transform: uppercase;
}
.ppc-year {
  font-size: 9px; font-weight: 600;
  background: rgba(127,119,221,0.18);
  color: #5B53C2;
  padding: 1px 6px; border-radius: 4px;
}
.ppc-title-row { display: flex; align-items: baseline; gap: 8px; min-width: 0; }
.ppc-num {
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  font-size: 11px; font-weight: 500;
  color: var(--uza-gray);
  flex-shrink: 0;
}
.ppc-title {
  font-size: 14px; font-weight: 500;
  color: var(--uza-navy);
  letter-spacing: -0.01em;
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}
.ppc-open {
  background: rgba(255,255,255,0.7);
  border: 1px solid rgba(15,23,60,0.08);
  border-radius: 8px;
  padding: 8px;
  cursor: pointer;
  color: var(--uza-purple);
  transition: all 200ms;
  flex-shrink: 0;
}
.ppc-open:hover {
  background: var(--uza-purple); color: white;
  border-color: var(--uza-purple);
  transform: translateX(2px);
}

.num-input, .num-static {
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  font-size: 13px; font-weight: 500;
  color: var(--uza-navy);
  background: rgba(255,255,255,0.6);
  border: 1px solid rgba(15,23,60,0.08);
  border-radius: 8px; padding: 6px 12px;
  width: 160px;
}
.num-input:focus { outline: none; border-color: var(--uza-purple); }

.access-banner {
  font-size: 11px; font-weight: 500; letter-spacing: 0.02em;
  color: var(--uza-gray);
  padding: 4px 10px;
  background: rgba(255,255,255,0.5);
  border-radius: 6px;
}

.ed-close {
  background: transparent; border: none; cursor: pointer;
  padding: 6px; border-radius: 8px;
  color: var(--uza-gray);
  transition: background 200ms;
}
.ed-close:hover { background: rgba(15,23,60,0.06); color: var(--uza-navy); }

/* ─── Title ─── */
.title-section { padding: 20px 24px 8px; }
.title-row { cursor: text; }
.title-display {
  display: inline-flex; align-items: center; gap: 8px;
  font-size: 22px; font-weight: 500; letter-spacing: -0.025em;
  color: var(--uza-navy);
  margin: 0;
}
.pencil-btn {
  background: transparent; border: none; cursor: pointer;
  color: var(--uza-gray); opacity: 0;
  transition: opacity 200ms;
  padding: 4px;
}
.title-row:hover .pencil-btn { opacity: 1; }

.title-input {
  font-size: 22px; font-weight: 500; letter-spacing: -0.025em;
  color: var(--uza-navy);
  background: transparent;
  border: none; outline: none;
  width: 100%;
  border-bottom: 2px solid var(--uza-purple);
  padding: 4px 0;
}

/* ─── Body grid ─── */
.ed-body {
  padding: 16px 24px 24px;
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 14px;
  overflow-y: auto;
  max-height: calc(100vh - 280px);
}
.ed-body > .desc-card,
.ed-body > .comments-card,
.ed-body > .effect-card { grid-column: span 2; }

/* ─── Cards ─── */
.card {
  background: rgba(255,255,255,0.55);
  backdrop-filter: blur(20px);
  border: 0.5px solid rgba(15,23,60,0.06);
  border-radius: 14px;
  padding: 16px;
  opacity: 0; transform: translateY(8px);
  animation: cardIn 380ms ease forwards;
}
.stagger-1 { animation-delay: 60ms; }
.stagger-2 { animation-delay: 100ms; }
.stagger-3 { animation-delay: 140ms; }
.stagger-4 { animation-delay: 180ms; }
.stagger-5 { animation-delay: 220ms; }
.stagger-6 { animation-delay: 260ms; }
.stagger-7 { animation-delay: 300ms; }
.stagger-8 { animation-delay: 340ms; }

@keyframes cardIn {
  to { opacity: 1; transform: translateY(0); }
}

.card-label {
  font-size: 10px; font-weight: 500; letter-spacing: 0.08em;
  color: var(--uza-gray); text-transform: uppercase;
  margin-bottom: 12px;
}
.card-label.flex { display: flex; align-items: center; justify-content: space-between; }

/* ─── Fields ─── */
.field { margin-bottom: 12px; }
.field:last-child { margin-bottom: 0; }
.field label {
  display: block;
  font-size: 11px; font-weight: 500; color: var(--uza-navy);
  margin-bottom: 6px;
}
.field input, .field select, .field textarea {
  width: 100%;
  font-size: 13px; font-weight: 400;
  color: var(--uza-navy);
  background: rgba(255,255,255,0.7);
  border: 1px solid rgba(15,23,60,0.08);
  border-radius: 8px;
  padding: 8px 12px;
  transition: border-color 200ms, background 200ms;
}
.field input:focus, .field select:focus, .field textarea:focus {
  outline: none; border-color: var(--uza-purple);
  background: rgba(255,255,255,0.95);
}
.field input:disabled, .field select:disabled, .field textarea:disabled {
  opacity: 0.6; cursor: not-allowed;
}

.field-grid-2 { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; }
.field.full { grid-column: span 4; }

.locked-hint {
  font-size: 9px; padding: 1px 6px;
  background: rgba(232,75,74,0.12); color: var(--uza-red);
  border-radius: 4px; margin-left: 6px;
}

.hint {
  font-size: 11px; color: var(--uza-gray);
  margin: 6px 0 0; line-height: 1.4;
}

/* ─── Pill toggle ─── */
.pill-toggle { display: flex; gap: 6px; flex-wrap: wrap; }
.pill {
  font-size: 12px; font-weight: 500;
  padding: 7px 14px; border-radius: 11px;
  background: rgba(255,255,255,0.6);
  border: 1px solid rgba(15,23,60,0.08);
  color: var(--uza-navy);
  cursor: pointer;
  transition: all 200ms;
}
.pill.sm { padding: 5px 10px; font-size: 11px; }
.pill:hover:not(:disabled) { background: rgba(255,255,255,0.9); border-color: var(--uza-purple); }
.pill.active {
  background: var(--uza-purple); color: white;
  border-color: var(--uza-purple);
  box-shadow: 0 2px 8px rgba(127,119,221,0.3);
}
.pill:disabled { opacity: 0.5; cursor: not-allowed; }
.pill.pill-ghost {
  border-style: dashed; background: transparent;
  color: var(--uza-gray);
}

/* ─── Status badges ─── */
.status-row { display: flex; gap: 6px; flex-wrap: wrap; margin-bottom: 14px; }
.status-badge {
  display: inline-flex; align-items: center; gap: 6px;
  font-size: 11px; font-weight: 500;
  padding: 6px 12px;
  background: rgba(255,255,255,0.6);
  border: 1px solid rgba(15,23,60,0.08);
  border-radius: 11px;
  color: var(--uza-navy);
  cursor: pointer;
  transition: all 200ms;
}
.status-badge .dot {
  width: 6px; height: 6px; border-radius: 50%;
}
.status-badge:hover:not(:disabled) { background: rgba(255,255,255,0.95); }
.status-badge.active {
  background: var(--accent, var(--uza-purple));
  color: white; border-color: var(--accent, var(--uza-purple));
  box-shadow: 0 2px 8px rgba(0,0,0,0.1);
}
.status-badge.active .dot { background: white !important; }

/* ─── Quarters ─── */
.quarters-grid {
  display: grid; grid-template-columns: repeat(4, 1fr);
  gap: 8px; margin-bottom: 14px;
}
.quarter-check {
  display: flex; align-items: center; justify-content: center; gap: 6px;
  padding: 10px;
  background: rgba(255,255,255,0.6);
  border: 1.5px solid rgba(15,23,60,0.1);
  border-radius: 10px;
  cursor: pointer;
  transition: all 240ms cubic-bezier(0.34, 1.2, 0.64, 1);
  font-size: 12px; font-weight: 500;
  color: var(--uza-navy);
}
.quarter-check input { display: none; }
.quarter-check:hover { background: rgba(255,255,255,0.9); }
.quarter-check.checked {
  background: rgba(29,158,117,0.08);
  border-color: var(--uza-teal);
  color: var(--uza-teal);
  box-shadow: 0 0 0 3px rgba(29,158,117,0.12);
}
.q-tick { animation: tickIn 240ms cubic-bezier(0.34, 1.2, 0.64, 1); }
@keyframes tickIn {
  from { transform: scale(0); opacity: 0; }
  to   { transform: scale(1); opacity: 1; }
}

/* ─── Progress ─── */
.progress-block { margin-top: 12px; }
.progress-label {
  display: flex; justify-content: space-between;
  font-size: 11px; font-weight: 500;
  color: var(--uza-navy);
  margin-bottom: 6px;
}
.progress-pct { color: var(--uza-purple); font-size: 14px; font-weight: 500; }
.progress-track {
  height: 8px;
  background: rgba(15,23,60,0.06);
  border-radius: 4px; overflow: hidden;
  position: relative;
}
.progress-fill {
  height: 100%;
  background: linear-gradient(90deg, var(--uza-purple), var(--uza-teal));
  border-radius: 4px;
  transition: width 700ms cubic-bezier(0.4, 0.6, 0.2, 1);
  position: relative;
  overflow: hidden;
}
.progress-fill::after {
  content: ""; position: absolute; inset: 0;
  background: linear-gradient(90deg, transparent, rgba(255,255,255,0.4), transparent);
  animation: shimmer 1.8s ease-in-out infinite;
}
@keyframes shimmer {
  0% { transform: translateX(-100%); }
  100% { transform: translateX(200%); }
}

/* ─── Consultant picker ─── */
.consultant-picker { position: relative; }
.consultant-trigger {
  display: flex; align-items: center; gap: 8px;
  width: 100%;
  background: rgba(255,255,255,0.7);
  border: 1px solid rgba(15,23,60,0.08);
  border-radius: 8px;
  padding: 8px 12px;
  cursor: pointer;
  font-size: 13px;
  color: var(--uza-navy);
  transition: all 200ms;
}
.consultant-trigger:hover:not(:disabled) {
  background: rgba(255,255,255,0.95);
  border-color: var(--uza-purple);
}
.consultant-trigger:disabled { opacity: 0.6; cursor: not-allowed; }
.consultant-name { flex: 1; text-align: left; font-weight: 500; }
.consultant-placeholder { flex: 1; text-align: left; color: var(--uza-gray); }
.caret { margin-left: auto; transition: transform 200ms; color: var(--uza-gray); }
.consultant-picker.open .caret { transform: rotate(180deg); }

.consultant-menu {
  position: absolute; top: calc(100% + 4px); left: 0; right: 0;
  background: rgba(255,255,255,0.95);
  backdrop-filter: blur(20px);
  border: 1px solid rgba(15,23,60,0.08);
  border-radius: 10px;
  box-shadow: 0 8px 24px rgba(15,23,60,0.12);
  max-height: 280px; overflow-y: auto;
  z-index: 1500;
  background: #FFFFFF;
  box-shadow: 0 12px 32px rgba(15,23,60,.18), 0 4px 12px rgba(15,23,60,.10);
  border: 1px solid rgba(30,42,74,.10);
  animation: menuIn 200ms ease;
}
@keyframes menuIn {
  from { opacity: 0; transform: translateY(-4px); }
  to   { opacity: 1; transform: translateY(0); }
}
.consultant-opt {
  display: flex; align-items: center; gap: 8px;
  padding: 8px 12px;
  cursor: pointer;
  font-size: 13px;
  transition: background 150ms;
}
.consultant-opt:hover { background: rgba(127,119,221,0.08); }
.consultant-opt.active { background: rgba(127,119,221,0.12); font-weight: 500; }
.big4 {
  font-size: 9px; font-weight: 600;
  background: rgba(239,159,39,0.18);
  color: #B87600;
  padding: 1px 6px; border-radius: 4px;
  margin-left: auto;
}

/* ─── Switch ─── */
.switch { display: inline-block; position: relative; width: 36px; height: 20px; }
.switch input { display: none; }
.switch .slider {
  position: absolute; inset: 0;
  background: rgba(15,23,60,0.15);
  border-radius: 12px;
  transition: background 200ms;
}
.switch .slider::before {
  content: ""; position: absolute;
  top: 2px; left: 2px;
  width: 16px; height: 16px;
  background: white;
  border-radius: 50%;
  transition: transform 220ms cubic-bezier(0.34, 1.2, 0.64, 1);
}
.switch input:checked + .slider { background: var(--uza-teal); }
.switch input:checked + .slider::before { transform: translateX(16px); }

/* ─── Effect grid ─── */
.effect-grid {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 10px;
}

/* ─── Description textarea ─── */
.desc-card textarea {
  width: 100%;
  font-size: 13px;
  background: rgba(255,255,255,0.7);
  border: 1px solid rgba(15,23,60,0.08);
  border-radius: 8px;
  padding: 10px 12px;
  resize: vertical;
  min-height: 70px;
  font-family: inherit;
}

/* ─── Comments ─── */
.comments-card .cnt {
  display: inline-block;
  font-size: 10px; font-weight: 500;
  background: rgba(127,119,221,0.18); color: #5B53C2;
  padding: 1px 8px; border-radius: 6px;
  margin-left: 6px;
}
.comment-input-row {
  display: flex; gap: 10px;
  margin-bottom: 16px;
  align-items: flex-end;
}
.comment-input-row textarea {
  flex: 1;
  font-size: 13px;
  background: rgba(255,255,255,0.7);
  border: 1px solid rgba(15,23,60,0.08);
  border-radius: 10px;
  padding: 10px 14px;
  resize: none;
  font-family: inherit;
}

.comments-list { display: flex; flex-direction: column; gap: 14px; }
.comment-item {
  padding: 12px 14px;
  background: rgba(255,255,255,0.5);
  border: 1px solid rgba(15,23,60,0.06);
  border-radius: 10px;
}
.comment-head {
  display: flex; align-items: center; gap: 8px;
  margin-bottom: 6px;
}
.avatar {
  width: 28px; height: 28px;
  border-radius: 50%;
  display: flex; align-items: center; justify-content: center;
  color: white; font-size: 11px; font-weight: 600;
  flex-shrink: 0;
}
.comment-meta {
  flex: 1;
  font-size: 11px;
  color: var(--uza-gray);
}
.comment-meta .author { color: var(--uza-navy); font-weight: 500; }
.dot-sep { margin: 0 6px; opacity: 0.5; }
.edited { font-style: italic; opacity: 0.7; }
.comment-actions {
  display: flex; gap: 8px;
  opacity: 0; transition: opacity 200ms;
}
.comment-item:hover .comment-actions { opacity: 1; }
.comment-body {
  font-size: 13px; line-height: 1.5; color: var(--uza-navy);
  margin: 0; white-space: pre-wrap;
}
.comment-edit textarea {
  width: 100%;
  font-size: 13px;
  background: rgba(255,255,255,0.9);
  border: 1px solid var(--uza-purple);
  border-radius: 8px;
  padding: 8px 10px;
  font-family: inherit;
}
.comment-edit-buttons {
  display: flex; gap: 6px; margin-top: 6px;
  justify-content: flex-end;
}

.empty {
  padding: 18px;
  text-align: center;
  font-size: 12px; color: var(--uza-gray);
  font-style: italic;
}

.link-btn {
  background: transparent; border: none; cursor: pointer;
  font-size: 11px; font-weight: 500;
  color: var(--uza-purple);
  padding: 2px 4px;
}
.link-btn:hover { text-decoration: underline; }
.link-btn.danger { color: var(--uza-red); }

/* ─── Footer ─── */
.ed-footer {
  display: flex; justify-content: space-between; align-items: center;
  padding: 16px 24px;
  background: linear-gradient(0deg, rgba(255,255,255,0.85), rgba(255,255,255,0.6));
  border-top: 1px solid rgba(15,23,60,0.06);
}
.footer-left, .footer-right { display: flex; align-items: center; gap: 10px; }

.btn {
  font-size: 13px; font-weight: 500;
  padding: 9px 18px;
  background: rgba(255,255,255,0.7);
  border: 1px solid rgba(15,23,60,0.1);
  border-radius: 10px;
  color: var(--uza-navy);
  cursor: pointer;
  transition: all 200ms;
}
.btn.sm { padding: 6px 12px; font-size: 12px; }
.btn:hover:not(:disabled) {
  background: rgba(255,255,255,0.95);
  border-color: var(--uza-purple);
}
.btn:disabled { opacity: 0.5; cursor: not-allowed; }

.btn-primary {
  background: var(--uza-purple); color: white;
  border-color: var(--uza-purple);
}
.btn-primary:hover:not(:disabled) {
  background: #6B62D2; border-color: #6B62D2;
  box-shadow: 0 4px 12px rgba(127,119,221,0.3);
}

.btn-danger {
  background: rgba(232,75,74,0.08);
  color: var(--uza-red);
  border-color: rgba(232,75,74,0.2);
}
.btn-danger:hover:not(:disabled) {
  background: var(--uza-red); color: white;
  border-color: var(--uza-red);
}

.error-msg {
  font-size: 11px; color: var(--uza-red);
  margin: 0 12px 0 0;
}

/* ─── Responsive ─── */
@media (max-width: 760px) {
  .ed-body { grid-template-columns: 1fr; max-height: calc(100vh - 220px); }
  .ed-body > .desc-card,
  .ed-body > .comments-card,
  .ed-body > .effect-card { grid-column: span 1; }
  .effect-grid { grid-template-columns: 1fr 1fr; }
}

/* ─── Reduced motion ─── */
@media (prefers-reduced-motion: reduce) {
  .editor-shell, .card, .progress-fill::after, .quarter-check, .q-tick, .consultant-menu {
    animation: none !important;
    transition: none !important;
  }
}
</style>
