<script setup lang="ts">
/**
 * TaskProjectEditor.vue
 * ─────────────────────────────────────────────────────────────────
 * Universal editor for Project or Task — Hero + Right-rail layout.
 *
 * Refactor 2026-05-26: K + F + G + I + J from rework menu.
 *   • Hero block top: title (inline-editable), status row + progress
 *     bar + period summary — all key state at-a-glance, no scroll.
 *   • Two-pane in Details tab: main column (description, period,
 *     эффект, attachments) + sticky right rail (assignee, consultant,
 *     direction, year, archive).
 *   • Tabs: «Детали» / «Комментарии (N)» — comments are full-height,
 *     no more deep-scroll to reach them.
 *   • Access-banner hidden for owner/admin (was always visible).
 *   • Period collapsed to ONE row (start — due) instead of two cards.
 *   • «Основание/Тип» and «Перенос FY+1» live inside <details>,
 *     collapsed by default (rare-edit).
 *
 * All original script logic preserved — only template + styles changed.
 */

import { ref, computed, onMounted, watch, nextTick, onBeforeUnmount } from "vue";
import { useAuthStore } from "@/stores/auth";
import { api, isModerationQueued, type ModerationQueuedTag } from "@/api/client";
import UserHover from "@/components/UserHover.vue";
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
  entity: ProjectDetail | TaskDetail | null;
  kind: Kind;
  projectId?: string | null;
  companyId?: string | null;   // контекст компании при создании (CompanyWorkspace)
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

// 2026-05-26: было захардкожено currentUserEmail === 'v.kim@uz-assets.uz'.
// Заменено на канонический auth.user.is_owner который backend выставляет
// в JWT-claims. Также fallback на role 'owner'/'ROLE_OWNER' для совместимости.
const isOwner = computed(() => {
  const u: any = auth.user;
  if (!u) return false;
  if (u.is_owner === true) return true;
  const roles = u.roles || [];
  return Array.isArray(roles) && roles.some((r: string) => r === "owner" || r === "ROLE_OWNER");
});
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

// 2026-05-26: hide banner for owner/admin — they have full access, banner just noise
const showAccessBanner = computed(() => !["owner", "admin"].includes(accessLevel.value));

// =====================================================================
// Form state
// =====================================================================

const isCreate = computed(() => !props.entity);

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

// Project-only
const formGroundType = ref<string>("");
const formGroundNumber = ref("");
const formProjectType = ref<"onetime" | "recurring">("onetime");
const formRecurringPeriod = ref<"ongoing" | "quarterly" | "monthly">("ongoing");
const formLinkedProjectId = ref<string | null>(null);
const formConsultantId = ref<string | null>(null);
const formConsultantLegacy = ref<string[]>([]);

// Task-only year-transfer (2026-05-26)
const formLinkedTaskId = ref<string | null>(null);

// Quarters
const formQuarters = ref<QuartersObject>({ q1: false, q2: false, q3: false, q4: false });

// Economic effect
const formHasEffect = ref(false);
const formEffectPlan = ref<number | null>(null);
const formEffectFact = ref<number | null>(null);
const formEffectCurrency = ref("UZS");
const formEffectUnit = ref("млрд");
const formEffectNote = ref("");

// Title inline edit
const titleEditing = ref(false);
const titleInput = ref<HTMLInputElement | null>(null);

// =====================================================================
// Reference data
// =====================================================================

const consultants = ref<ConsultantBrief[]>([]);
const futureProjects = ref<Array<{ id: string; title: string; portfolio_year: number }>>([]);
const futureTasks = ref<Array<{ id: string; title: string; portfolio_year: number; num: string | null }>>([]);
const parentProject = ref<{ id: string; title: string; num: string | null; portfolio_year: number | null } | null>(null);
const linkedFromYear = ref<number | null>(null);
const linkedToYear = ref<number | null>(null);

// Привязка задачи к проекту (фильтр по году + компании)
const companyProjects = ref<Array<{ id: string; title: string; num: string | null; portfolio_year: number | null }>>([]);
const selectedProjectId = ref<string | null>(null);
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
const activeTab = ref<"details" | "comments">("details");

// =====================================================================
// Computed
// =====================================================================

// 2026-05-26: для tasks разделяем pills на 2 группы — стандартные (init/
// active/review/done) и регулярные (quarterly/monthly/ongoing). Раньше
// recurring-варианты были скрыты, хотя в data-model и kanban они работают.
const STANDARD_STATUSES = ["new", "init", "active", "review", "done"];
const RECURRING_STATUSES = ["quarterly", "monthly", "ongoing"];

const statusOptions = computed(() => {
  if (props.kind === "task") {
    return STANDARD_STATUSES;
  }
  if (formProjectType.value === "onetime") {
    return STANDARD_STATUSES;
  }
  if (formRecurringPeriod.value === "ongoing") return ["ongoing"];
  if (formRecurringPeriod.value === "quarterly") return ["quarterly"];
  if (formRecurringPeriod.value === "monthly") return ["monthly"];
  return STANDARD_STATUSES;
});

// For tasks only — show recurring statuses as a separate group (visually
// distinct, with a small "Регулярные" label). Hidden for projects since
// project_type+recurring_period toggles already drive it.
const recurringStatusOptions = computed(() => {
  if (props.kind !== "task") return [];
  return RECURRING_STATUSES;
});

// Индекс текущего статуса в линейном степпере (−1 если статус регулярный)
const stepIdx = computed(() => statusOptions.value.indexOf(formStatus.value));

const computedProgress = computed(() => {
  // Проект: прогресс = среднее по задачам (считает бэкенд → progress_percent).
  // Собственный статус проекта на прогресс не влияет.
  if (props.kind === "project") {
    return Math.round(Number((props.entity as any)?.progress_percent) || 0);
  }
  // Задача: «Завершено» = 100%, остальные статусы в счёт не идут (0%).
  if (formStatus.value === "done") return 100;
  if (formStatus.value === "quarterly") {
    // Self-progress кварталов: все 4 закрыты = 100%.
    const q = formQuarters.value;
    let n = 0;
    if (q.q1) n++; if (q.q2) n++; if (q.q3) n++; if (q.q4) n++;
    return n * 25;
  }
  return 0;
});

const accessBannerText = computed(() => {
  switch (accessLevel.value) {
    case "kurator": return "Куратор · редактирование";
    case "executor": return "Исполнитель · только своя задача";
    default:        return "Read-only";
  }
});

const selectedConsultant = computed(() =>
  consultants.value.find(c => c.id === formConsultantId.value) || null
);

// Days until due — small "через N дней" / "просрочено N дн" hint near due-date
const dueHint = computed<{ text: string; tone: "ok" | "warn" | "danger" | "muted" } | null>(() => {
  if (!formDueDate.value) return null;
  const d = new Date(formDueDate.value);
  if (Number.isNaN(d.getTime())) return null;
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  d.setHours(0, 0, 0, 0);
  const diff = Math.round((d.getTime() - today.getTime()) / 86400000);
  if (diff < 0)  return { text: `просрочено ${-diff} дн`, tone: "danger" };
  if (diff === 0) return { text: "сегодня", tone: "danger" };
  if (diff <= 7)  return { text: `через ${diff} дн`, tone: "warn" };
  if (diff <= 30) return { text: `через ${diff} дн`, tone: "ok" };
  return { text: `через ${diff} дн`, tone: "muted" };
});

const commentsCount = computed(() => comments.value.length);

// =====================================================================
// Initialization
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
    formStatus.value = "init";
    formPriority.value = "medium";
    formProjectType.value = "onetime";
    formRecurringPeriod.value = "ongoing";
    formPortfolioYear.value = new Date().getFullYear();
    selectedProjectId.value = props.projectId || null;
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

  if (props.kind === "task") {
    formLinkedTaskId.value = (e as TaskDetail).linked_task_id || null;
    selectedProjectId.value = (e as any).project_id || props.projectId || null;
  }

  const q = e.quarters as QuartersObject | null;
  if (q) {
    formQuarters.value = { q1: !!q.q1, q2: !!q.q2, q3: !!q.q3, q4: !!q.q4 };
  }

  const ee: any = e;
  if (ee.linked_year && typeof ee.linked_year === "number") {
    linkedFromYear.value = ee.linked_year;
  } else if (ee.extra && ee.extra.linked_year) {
    linkedFromYear.value = Number(ee.extra.linked_year) || null;
  }

  const cons = e.consultant;
  if (typeof cons === "string" && cons.trim()) {
    formConsultantLegacy.value = cons.split(",").map(s => s.trim()).filter(Boolean);
  } else if (Array.isArray(cons)) {
    formConsultantLegacy.value = cons;
  }

  if (e.economic_effect && typeof e.economic_effect === "object") {
    formHasEffect.value = true;
    const eff: any = e.economic_effect;
    formEffectPlan.value = eff.plan ?? eff.value ?? null;
    formEffectFact.value = eff.fact ?? null;
    formEffectCurrency.value = eff.currency || "UZS";
    formEffectUnit.value = eff.unit || "млрд";
    formEffectNote.value = eff.note || "";
  }

  const cmts = (e as any).comments;
  if (Array.isArray(cmts)) {
    comments.value = cmts as Comment[];
  } else {
    comments.value = [];
  }
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
// Loaders
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

async function loadFutureTasks() {
  if (props.kind !== "task") return;
  try {
    const nextYear = (props.entity?.portfolio_year || new Date().getFullYear()) + 1;
    const companyId = (props.entity as any)?.company_id;
    const params: any = { portfolio_year: nextYear, limit: 200 };
    // Scope future tasks to the same company when we know it — avoids
    // dumping hundreds of unrelated tasks from other companies into the picker.
    if (companyId) params.company_id = companyId;
    const resp = await (await import("@/api/tasks")).tasksApi.list(params);
    const items = ((resp as any).items || []) as TaskDetail[];
    futureTasks.value = items
      .filter((t: any) => !t.is_archived)
      .map((t: any) => ({
        id: t.id,
        title: t.title,
        portfolio_year: t.portfolio_year || nextYear,
        num: t.num || null,
      }));
  } catch (e) {
    console.warn("Failed to load future tasks:", e);
  }
}

async function loadCompanyProjects() {
  if (props.kind !== "task") return;
  const companyId = props.companyId || (props.entity as any)?.company_id || null;
  if (!companyId) { companyProjects.value = []; return; }
  try {
    const resp = await projectsApi.list({
      company_id: companyId,
      portfolio_year: formPortfolioYear.value,
      limit: 200,
    });
    companyProjects.value = resp.items.map(p => ({
      id: p.id, title: p.title, num: p.num, portfolio_year: p.portfolio_year,
    }));
    // Если выбран проект (напр. родитель при edit), которого нет в выборке года —
    // подгружаем его отдельно, чтобы НЕ потерять привязку молча.
    const sel = selectedProjectId.value;
    if (sel && !companyProjects.value.some(p => p.id === sel)) {
      try {
        const p = await projectsApi.getOne(sel);
        companyProjects.value.unshift({ id: p.id, title: p.title, num: p.num, portfolio_year: p.portfolio_year });
      } catch { /* недоступен — оставляем как есть */ }
    }
  } catch (e) {
    console.warn("Failed to load company projects:", e);
  }
}

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

async function loadLinkedTaskInfo() {
  if (props.kind !== "task") return;
  const linkedId = formLinkedTaskId.value;
  if (!linkedId) return;
  try {
    const { tasksApi } = await import("@/api/tasks");
    const t = await tasksApi.getOne(linkedId);
    linkedToYear.value = t.portfolio_year;
  } catch (err) {
    console.warn("Failed to load linked task:", err);
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

  if (props.kind === "project") {
    base.ground_type = formGroundType.value || null;
    base.ground_number = formGroundNumber.value || null;
    base.project_type = formProjectType.value;
    base.recurring_period = formProjectType.value === "recurring" ? formRecurringPeriod.value : null;
    base.linked_project_id = formLinkedProjectId.value || null;
    base.consultant_id = formConsultantId.value || null;
  }

  if (props.kind === "task") {
    base.consultant_id = formConsultantId.value || null;
    base.project_id = selectedProjectId.value || null;   // привязка к проекту (или открепление)
    base.linked_task_id = formLinkedTaskId.value || null;
  }

  // Привязка к компании при создании из CompanyWorkspace (иначе задача/проект
  // создаётся без company_id и не появляется в рабочем пространстве компании).
  if (isCreate.value && props.companyId) {
    base.company_id = props.companyId;
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
    let savedId: string | null = null;

    if (props.kind === "project") {
      if (isCreate.value) {
        const created = await projectsApi.create(payload as ProjectCreate);
        if (!isModerationQueued(created)) savedId = created.id;
      } else {
        const updated = await projectsApi.update(props.entity!.id, payload as ProjectUpdate);
        if (!isModerationQueued(updated)) savedId = updated.id;
      }
    } else {
      if (isCreate.value) {
        const { data } = await api.post<TaskDetail | ModerationQueuedTag>("/tasks", payload as TaskCreate);
        if (!isModerationQueued(data)) savedId = data.id;
      } else {
        const { data } = await api.patch<TaskDetail | ModerationQueuedTag>(`/tasks/${props.entity!.id}`, payload as TaskUpdate);
        if (!isModerationQueued(data)) savedId = data.id;
      }
    }

    // Если изменение ушло на модерацию (202), savedId === null — глобальный
    // интерсептор уже показал тост «Изменение отправлено на модерацию».
    // Не эмитим "saved" (иначе родитель покажет «сохранено»), просто закрываем.
    if (savedId !== null) emit("saved", savedId);
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
// Comments
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
  if (!props.entity || !newCommentText.value.trim()) return;
  commentsBusy.value = true;
  try {
    const { data } = await api.post<Comment | ModerationQueuedTag>(commentEndpoint(), { body: newCommentText.value.trim() });
    if (isModerationQueued(data)) {
      // Комментарий ушёл на модерацию (202) — глобальный интерсептор показал
      // тост. Не добавляем в список (его ещё нет), чистим поле ввода.
      newCommentText.value = "";
      return;
    }
    if (data && data.id) {
      comments.value = [data, ...comments.value];
    }
    newCommentText.value = "";
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

function formatDateShort(iso: string | null | undefined): string {
  if (!iso) return "—";
  try {
    const d = new Date(iso);
    return d.toLocaleDateString("ru-RU", { day: "2-digit", month: "2-digit", year: "numeric" });
  } catch { return String(iso); }
}

function statusLabel(s: string): string {
  return STATUS_LABELS[s] || s;
}
function statusColor(s: string): string {
  return STATUS_COLORS[s] || "#888780";
}

function openParentProject() {
  if (!parentProject.value) return;
  emit("close");
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
}

// =====================================================================
// Lifecycle
// =====================================================================

onMounted(async () => {
  populateForm();
  await Promise.all([
    loadConsultants(),
    loadFutureProjects(),
    loadFutureTasks(),
    loadParentProject(),
    loadCompanyProjects(),
    loadLinkedProjectInfo(),
    loadLinkedTaskInfo(),
  ]);
});

watch(() => props.entity, populateForm, { deep: false });
// Фильтрация списка проектов по выбранному году задачи
watch(formPortfolioYear, () => { loadCompanyProjects(); });

function onKeydown(e: KeyboardEvent) {
  if (e.key === "Escape") emit("close");
}
onMounted(() => window.addEventListener("keydown", onKeydown));
onBeforeUnmount(() => window.removeEventListener("keydown", onKeydown));
</script>

<template>
  <div class="editor-backdrop" @click.self="emit('close')">
    <div class="editor-shell">
      <!-- ═══════════════════════════════════════════════════════ -->
      <!-- HEADER strip                                            -->
      <!-- ═══════════════════════════════════════════════════════ -->
      <header class="ed-header">
        <div class="ed-header-left">
          <span class="kind-pill" :class="`kind-${kind}`">
            {{ kind === "project" ? "ПРОЕКТ" : "ЗАДАЧА" }}
          </span>

          <input
            v-if="canEdit"
            class="num-input"
            v-model="formNum"
            placeholder="ПР-2026-014"
          />
          <span v-else-if="formNum" class="num-static">{{ formNum }}</span>

          <span v-if="linkedFromYear" class="transfer-badge from">
            <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
              <path d="M5 12h14M12 5l7 7-7 7"/>
            </svg>
            из FY{{ linkedFromYear }}
          </span>
          <span v-if="linkedToYear" class="transfer-badge to">
            <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
              <path d="M5 12h14M12 5l7 7-7 7"/>
            </svg>
            → FY{{ linkedToYear }}
          </span>
        </div>

        <div class="ed-header-right">
          <span v-if="showAccessBanner" class="access-banner">{{ accessBannerText }}</span>
          <button class="ed-close" @click="emit('close')" aria-label="Закрыть">
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <path d="M18 6L6 18M6 6l12 12"/>
            </svg>
          </button>
        </div>
      </header>

      <!-- ═══════════════════════════════════════════════════════ -->
      <!-- HERO — title + status row + progress + due hint         -->
      <!-- ═══════════════════════════════════════════════════════ -->
      <section class="ed-hero">
        <div class="hero-eyebrow">
          <span class="hero-type-pill" :class="kind === 'project' ? 'is-project' : 'is-task'">
            {{ kind === 'project' ? 'Проект' : 'Задача' }}
          </span>
        </div>
        <div class="hero-title-row" @click="!titleEditing && startEditTitle()">
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

        <!-- Status row (clickable pills) + progress bar + due summary -->
        <div class="hero-status-row">
          <div class="status-group-wrap">
            <!-- Status stepper (стандартные статусы) -->
            <div class="tpe-stepper">
              <button
                v-for="(s, i) in statusOptions" :key="s"
                class="tpe-step"
                :class="{ 'is-done': stepIdx >= 0 && i < stepIdx, 'is-current': i === stepIdx, 'line-filled': stepIdx >= 0 && i <= stepIdx }"
                :disabled="!canEdit"
                @click="formStatus = s"
                :title="statusLabel(s)"
              >
                <span class="tpe-step-node">
                  <svg v-if="stepIdx >= 0 && i < stepIdx" width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"/></svg>
                  <span v-else>{{ i + 1 }}</span>
                </span>
                <span class="tpe-step-label">{{ statusLabel(s) }}</span>
              </button>
            </div>

            <!-- Recurring sub-group (tasks only) — visually separated -->
            <div v-if="recurringStatusOptions.length" class="status-row status-row--recurring">
              <span class="status-group-label">Регулярные:</span>
              <button
                v-for="s in recurringStatusOptions" :key="s"
                class="status-badge status-badge--recurring"
                :class="{ active: formStatus === s }"
                :style="formStatus === s ? `--accent: ${statusColor(s)}` : ''"
                :disabled="!canEdit"
                @click="formStatus = s"
              >
                <span class="dot" :style="`background: ${statusColor(s)}`"></span>
                {{ statusLabel(s) }}
              </button>
            </div>
          </div>

          <!-- Прогресс + дедлайн — отдельная плашка под степпером -->
          <div class="tpe-progress-plate">
            <div class="tpe-pp-left">
              <div class="tpe-pp-track"><div class="tpe-pp-fill" :style="`width: ${computedProgress}%`"></div></div>
              <span class="tpe-pp-pct"><b>{{ computedProgress }}</b><i>%</i></span>
            </div>
            <div v-if="formDueDate" class="tpe-pp-right">
              <span class="tpe-pp-due-label">Дедлайн</span>
              <span class="tpe-pp-due-date">{{ formatDateShort(formDueDate) }}</span>
              <span v-if="dueHint" class="tpe-pp-chip" :class="`tone-${dueHint.tone}`">{{ dueHint.text }}</span>
            </div>
          </div>
        </div>

        <!-- Quarters checkboxes (only when status=quarterly) -->
        <div v-if="formStatus === 'quarterly'" class="hero-quarters">
          <label v-for="q in (['q1','q2','q3','q4'] as const)" :key="q"
                 class="quarter-check" :class="{ checked: formQuarters[q] }">
            <input type="checkbox" :checked="formQuarters[q]"
                   :disabled="!canEdit" @change="toggleQuarter(q)" />
            <span class="q-label">{{ q.toUpperCase() }}</span>
            <svg v-if="formQuarters[q]" class="q-tick" width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="#1D9E75" stroke-width="3">
              <polyline points="20 6 9 17 4 12"/>
            </svg>
          </label>
        </div>
      </section>

      <!-- Parent project card (tasks only) -->
      <section v-if="kind === 'task' && parentProject" class="parent-project-card uza-side-stripe">
        <div class="ppc-icon">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <path d="M3 7h18v12a2 2 0 01-2 2H5a2 2 0 01-2-2V7z"/>
            <path d="M3 7l2-3h6l2 3"/>
          </svg>
        </div>
        <div class="ppc-body">
          <span class="ppc-label">Относится к проекту</span>
          <div class="ppc-title-row">
            <span v-if="parentProject.num" class="ppc-num">{{ parentProject.num }}</span>
            <span class="ppc-title">{{ parentProject.title }}</span>
            <span v-if="parentProject.portfolio_year" class="ppc-year">FY{{ parentProject.portfolio_year }}</span>
          </div>
        </div>
        <button class="ppc-open" @click="openParentProject" title="Открыть проект">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <path d="M7 17L17 7M7 7h10v10"/>
          </svg>
        </button>
      </section>

      <!-- ═══════════════════════════════════════════════════════ -->
      <!-- TABS                                                    -->
      <!-- ═══════════════════════════════════════════════════════ -->
      <nav class="ed-tabs">
        <button
          class="ed-tab"
          :class="{ active: activeTab === 'details' }"
          @click="activeTab = 'details'"
        >Детали</button>
        <button
          v-if="!isCreate"
          class="ed-tab"
          :class="{ active: activeTab === 'comments' }"
          @click="activeTab = 'comments'"
        >Комментарии<span class="tab-count" v-if="commentsCount">{{ commentsCount }}</span></button>
      </nav>

      <!-- ═══════════════════════════════════════════════════════ -->
      <!-- TAB CONTENT (Details / Comments) with slide transition  -->
      <!-- ═══════════════════════════════════════════════════════ -->
      <div class="ed-tab-host">
      <Transition name="uza-tab" mode="out-in">
      <div v-if="activeTab === 'details'" key="details" class="ed-grid">

        <!-- ─── MAIN COLUMN ─── -->
        <main class="ed-main">

          <!-- Description -->
          <section class="block">
            <div class="block-label">Описание</div>
            <MentionableTextarea
              v-model="formDescription"
              :disabled="!canEdit"
              rows="4"
              placeholder="Дополнительная информация... (введите @ для упоминания)"
            />
          </section>

          <!-- Period (start + due on one row) -->
          <section class="block">
            <div class="block-label">Период</div>
            <div class="period-row">
              <div class="period-field">
                <label>Старт</label>
                <input type="date" v-model="formStartDate" :disabled="!canEdit"/>
              </div>
              <span class="period-sep">—</span>
              <div class="period-field">
                <label>Дедлайн</label>
                <input type="date" v-model="formDueDate" :disabled="!canEdit"/>
              </div>
            </div>
          </section>

          <!-- Economic effect -->
          <section class="block">
            <div class="block-label flex">
              <span>Экономический эффект</span>
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

          <!-- Attachments — Результаты + Документы -->
          <section v-if="!isCreate && props.entity?.id" class="block">
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

          <section v-if="!isCreate && props.entity?.id" class="block">
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

          <!-- Collapsible: Основание + Тип (project only) -->
          <details v-if="kind === 'project'" class="block block-foldable" :open="isCreate">
            <summary class="block-summary">
              <span class="block-label inline">Основание и тип проекта</span>
              <svg class="caret" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <polyline points="6 9 12 15 18 9"/>
              </svg>
            </summary>
            <div class="block-content">
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
                  <button class="pill" :class="{ active: formProjectType === 'onetime' }"
                          :disabled="!isCreate || !canEdit" @click="formProjectType = 'onetime'">Одноразовый</button>
                  <button class="pill" :class="{ active: formProjectType === 'recurring' }"
                          :disabled="!isCreate || !canEdit" @click="formProjectType = 'recurring'">Регулярный</button>
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
            </div>
          </details>

          <!-- Collapsible: Перенос FY+1 (project only, not on create) -->
          <details v-if="kind === 'project' && !isCreate" class="block block-foldable" :open="!!formLinkedProjectId">
            <summary class="block-summary">
              <span class="block-label inline">
                Перенос на FY+1
                <span v-if="formLinkedProjectId" class="badge-mini">перенесён</span>
              </span>
              <svg class="caret" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <polyline points="6 9 12 15 18 9"/>
              </svg>
            </summary>
            <div class="block-content">
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
            </div>
          </details>

          <!-- Collapsible: Перенос FY+1 (task only, not on create) -->
          <details v-if="kind === 'task' && !isCreate" class="block block-foldable" :open="!!formLinkedTaskId">
            <summary class="block-summary">
              <span class="block-label inline">
                Перенос на FY+1
                <span v-if="formLinkedTaskId" class="badge-mini">перенесена</span>
              </span>
              <svg class="caret" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <polyline points="6 9 12 15 18 9"/>
              </svg>
            </summary>
            <div class="block-content">
              <div class="field">
                <label>Связанная задача (год+1)</label>
                <select v-model="formLinkedTaskId" :disabled="!canEdit">
                  <option :value="null">— не перенесена —</option>
                  <option v-for="t in futureTasks" :key="t.id" :value="t.id">
                    FY{{ t.portfolio_year }} · {{ t.num ? `[${t.num}] ` : '' }}{{ t.title }}
                  </option>
                </select>
                <p class="hint">
                  Перенос связывает текущую задачу с задачей в FY{{ formPortfolioYear + 1 }} и далее.
                  Текущая задача остаётся в FY{{ formPortfolioYear }} — целевая задача получает badge «перенесена из FY{{ formPortfolioYear }}».
                  <span v-if="!futureTasks.length" class="hint-empty">
                    В FY{{ formPortfolioYear + 1 }} пока нет задач для этой компании — сначала создайте задачу в следующем году.
                  </span>
                </p>
              </div>
            </div>
          </details>

        </main>

        <!-- ─── RIGHT RAIL (sticky) ─── -->
        <aside class="ed-rail">

          <section class="rail-block">
            <div class="rail-label">Ответственный</div>
            <UserAutocomplete
              :email="formAssigneeEmail"
              :name="formAssigneeName"
              :disabled="!canEdit"
              @update:email="formAssigneeEmail = $event"
              @update:name="formAssigneeName = $event"
            />
          </section>

          <section v-if="kind === 'task'" class="rail-block">
            <div class="rail-label rail-label-flex">
              <span>Проект</span>
              <span class="rail-year-chip">FY{{ formPortfolioYear }}</span>
            </div>
            <select v-model="selectedProjectId" :disabled="!canEdit" class="rail-select">
              <option :value="null">— без проекта —</option>
              <option v-for="p in companyProjects" :key="p.id" :value="p.id">
                {{ p.num ? `[${p.num}] ` : '' }}{{ p.title }}
              </option>
            </select>
            <p v-if="!companyProjects.length" class="rail-proj-empty">
              В FY{{ formPortfolioYear }} проектов нет — задача будет без проекта.
            </p>
          </section>

          <section class="rail-block">
            <div class="rail-label">Консультант</div>
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
          </section>

          <section class="rail-block">
            <div class="rail-label">Направление</div>
            <select v-model="formDirection" :disabled="!canEdit" class="rail-select">
              <option value="">— не выбрано —</option>
              <option v-for="d in directions" :key="d" :value="d">{{ d }}</option>
            </select>
          </section>

          <section class="rail-block rail-grid-2">
            <div>
              <div class="rail-label" style="display:flex;align-items:center;gap:6px">
                Приоритет
                <span style="width:7px;height:7px;border-radius:50%;display:inline-block"
                      :style="{ background: formPriority === 'high' ? '#E24B4A' : formPriority === 'medium' ? '#EF9F27' : '#94A3B8' }"></span>
              </div>
              <select v-model="formPriority" :disabled="!canEdit" class="rail-select">
                <option value="high">Высокий</option>
                <option value="medium">Средний</option>
                <option value="low">Низкий</option>
              </select>
            </div>
            <div>
              <div class="rail-label">FY</div>
              <input type="number" v-model.number="formPortfolioYear" :disabled="!canEdit" min="2020" max="2040" class="rail-input"/>
            </div>
          </section>

          <section v-if="!isCreate && canDelete" class="rail-block">
            <button class="rail-archive" @click="handleArchive" :disabled="saving">
              <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <rect x="3" y="3" width="18" height="5" rx="1"/>
                <path d="M5 8v11a2 2 0 002 2h10a2 2 0 002-2V8M10 12h4"/>
              </svg>
              Архивировать
            </button>
          </section>

        </aside>
      </div>

      <!-- ═══════════════════════════════════════════════════════ -->
      <!-- COMMENTS TAB                                            -->
      <!-- ═══════════════════════════════════════════════════════ -->
      <div v-else-if="activeTab === 'comments'" key="comments" class="ed-comments-pane">
        <div class="comment-input-row">
          <MentionableTextarea
            v-model="newCommentText"
            rows="3"
            placeholder="Написать комментарий... (введите @ для упоминания)"
            :disabled="commentsBusy"
          />
          <button class="btn btn-primary"
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
                <UserHover :email="c.author_email" :user-id="c.author_id">
                  <span class="author">{{ c.author_name || c.author_email || "—" }}</span>
                </UserHover>
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
      </div>
      </Transition>
      </div>

      <!-- ═══════════════════════════════════════════════════════ -->
      <!-- FOOTER                                                  -->
      <!-- ═══════════════════════════════════════════════════════ -->
      <footer class="ed-footer">
        <p v-if="error" class="error-msg">{{ error }}</p>
        <div class="footer-spacer"></div>
        <button class="btn" @click="emit('close')" :disabled="saving">Отмена</button>
        <button class="btn btn-primary" @click="handleSave" :disabled="saving || !canEdit">
          {{ saving ? "Сохранение..." : (isCreate ? "Создать" : "Сохранить") }}
        </button>
      </footer>
    </div>
  </div>
</template>

<style scoped>
/* ─── Palette ──────────────────────────────────────────────────── */
.editor-shell {
  --uza-purple: #7F77DD;
  --uza-teal:   var(--green);
  --uza-amber:  var(--amber);
  --uza-blue:   var(--blue);
  --uza-red:    var(--sev-high);
  --uza-navy:   #1E2A4A;
  --uza-gray:   var(--t-muted);
  --uza-bg:     #FAFAFB;
  --uza-border: var(--border-hard);
}

/* ─── Backdrop & shell ─────────────────────────────────────────── */
.editor-backdrop {
  position: fixed; inset: 0; z-index: 1000;
  background: rgba(15, 18, 40, 0.55);
  backdrop-filter: blur(6px);
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
  width: 100%; max-width: 1040px;
  background: var(--bg1, #FFFFFF);
  border: 1px solid var(--uza-border);
  border-radius: 14px;
  box-shadow: 0 24px 64px rgba(15, 23, 60, .18), 0 8px 24px rgba(15, 23, 60, .08);
  display: flex; flex-direction: column;
  overflow: hidden;
  animation: shellIn 340ms var(--ease-standard);
}

@keyframes shellIn {
  from { opacity: 0; transform: translateY(14px) scale(0.985); }
  to   { opacity: 1; transform: translateY(0)    scale(1); }
}

/* ═══════════════════════════════════════════════════════════════ */
/* HEADER                                                          */
/* ═══════════════════════════════════════════════════════════════ */
.ed-header {
  display: flex; align-items: center; justify-content: space-between;
  padding: 12px 20px;
  border-bottom: 1px solid var(--uza-border);
  flex-shrink: 0;
}
.ed-header-left, .ed-header-right { display: flex; align-items: center; gap: 10px; }

.kind-pill {
  font-size: 10px; font-weight: 600; letter-spacing: 0.08em;
  padding: 4px 9px; border-radius: 5px;
}
.kind-pill.kind-project { background: rgba(127,119,221,0.12); color: #5B53C2; }
.kind-pill.kind-task    { background: rgba(55,138,221,0.12);  color: #2A6FB8; }

.transfer-badge {
  display: inline-flex; align-items: center; gap: 4px;
  font-size: 10px; font-weight: 500; letter-spacing: 0.02em;
  padding: 3px 8px; border-radius: 5px;
}
.transfer-badge.from { background: rgba(239,159,39,0.12); color: #B87600; }
.transfer-badge.to   { background: rgba(29,158,117,0.12); color: #137A57; }

.num-input, .num-static {
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  font-size: 12.5px; font-weight: 500;
  color: var(--uza-navy);
  background: var(--uza-bg);
  border: 1px solid var(--uza-border);
  border-radius: 6px; padding: 5px 10px;
  width: 150px;
}
.num-input:focus { outline: none; border-color: var(--uza-purple); background: var(--bg1, #fff); }

.access-banner {
  font-size: 11px; font-weight: 500; letter-spacing: 0.02em;
  color: var(--uza-amber);
  padding: 3px 9px;
  background: rgba(239, 159, 39, .08);
  border-radius: 5px;
}

.ed-close {
  background: transparent; border: none; cursor: pointer;
  padding: 6px; border-radius: 7px;
  color: var(--uza-gray);
  transition: background .15s, color .15s;
}
.ed-close:hover { background: var(--uza-bg); color: var(--uza-navy); }

/* ═══════════════════════════════════════════════════════════════ */
/* HERO — title + status + progress + due                          */
/* ═══════════════════════════════════════════════════════════════ */
.ed-hero {
  padding: 18px 24px 16px;
  border-bottom: 1px solid var(--uza-border);
  background: linear-gradient(180deg, #FAFAFC 0%, #FFFFFF 100%);
}

.hero-title-row { cursor: text; margin-bottom: 14px; }
.title-display {
  display: inline-flex; align-items: center; gap: 8px;
  font-size: 22px; font-weight: 500; letter-spacing: -0.025em;
  color: var(--uza-navy);
  margin: 0;
  line-height: 1.25;
}
.pencil-btn {
  background: transparent; border: none; cursor: pointer;
  color: var(--uza-gray); opacity: 0;
  transition: opacity .15s;
  padding: 4px;
}
.hero-title-row:hover .pencil-btn { opacity: 1; }
.title-input {
  font-size: 22px; font-weight: 500; letter-spacing: -0.025em;
  color: var(--uza-navy);
  background: transparent;
  border: none; outline: none;
  width: 100%;
  border-bottom: 2px solid var(--uza-purple);
  padding: 4px 0;
}

.hero-eyebrow { margin-bottom: 8px; }
.hero-type-pill {
  display: inline-flex; align-items: center;
  font-size: 9.5px; font-weight: 600; letter-spacing: .06em; text-transform: uppercase;
  padding: 2px 9px; border-radius: 999px;
}
.hero-type-pill.is-project { background: rgba(127,119,221,.12); color: var(--p-deep); }
.hero-type-pill.is-task { background: #F1F5F9; color: var(--t3, var(--t3)); }

.hero-status-row {
  display: flex; flex-direction: column; align-items: stretch; gap: 14px;
}

/* ─── Status stepper (C2) ─── */
.tpe-stepper { display: flex; align-items: flex-start; width: 100%; }
.tpe-step {
  flex: 1; position: relative;
  display: flex; flex-direction: column; align-items: center; gap: 6px;
  background: none; border: 0; padding: 0; cursor: pointer;
}
.tpe-step:disabled { cursor: default; }
.tpe-step::before {
  content: ""; position: absolute; top: 11px; right: 50%;
  width: 100%; height: 2px; background: var(--uza-border, var(--border-input)); z-index: 0;
}
.tpe-step:first-child::before { display: none; }
.tpe-step.line-filled::before { background: var(--green); }
.tpe-step-node {
  position: relative; z-index: 1;
  width: 24px; height: 24px; border-radius: 50%;
  display: flex; align-items: center; justify-content: center;
  font-size: 11px; font-weight: 600;
  background: var(--bg1, #fff); border: 2px solid var(--uza-border, var(--border-input)); color: var(--t3, #94A3B8);
  transition: all .2s;
}
.tpe-step.is-done .tpe-step-node { background: var(--green); border-color: var(--green); color: #fff; }
.tpe-step.is-current .tpe-step-node { background: var(--amber); border-color: var(--amber); color: #fff; box-shadow: 0 0 0 4px rgba(239,159,39,.18); }
.tpe-step:hover:not(:disabled) .tpe-step-node { border-color: #7F77DD; }
.tpe-step-label { font-size: 10.5px; font-weight: 500; color: var(--t3, #94A3B8); text-align: center; line-height: 1.2; }
.tpe-step.is-done .tpe-step-label { color: var(--green); }
.tpe-step.is-current .tpe-step-label { color: #B7791F; font-weight: 600; }

/* ─── Progress plate (C2) ─── */
.tpe-progress-plate {
  display: flex; align-items: center; justify-content: space-between; gap: 16px;
  background: var(--bg2, #F8FAFC); border: 1px solid #EEF1F5; border-radius: 10px; padding: 10px 14px;
}
.tpe-pp-left { display: flex; align-items: center; gap: 10px; flex: 1; min-width: 0; }
.tpe-pp-track { flex: 1; max-width: 260px; height: 6px; background: #E8EBF2; border-radius: 999px; overflow: hidden; }
.tpe-pp-fill { height: 100%; border-radius: 999px; background: linear-gradient(90deg, #7F77DD, var(--green)); transition: width .4s cubic-bezier(0.4,0.6,0.2,1); }
.tpe-pp-pct { font-size: 13px; color: var(--uza-navy, #1E2A4A); white-space: nowrap; font-variant-numeric: tabular-nums; }
.tpe-pp-pct b { font-weight: 600; }
.tpe-pp-pct i { font-style: normal; color: var(--t3, #94A3B8); margin-left: 1px; }
.tpe-pp-right { display: flex; align-items: center; gap: 8px; flex-shrink: 0; }
.tpe-pp-due-label { font-size: 10px; text-transform: uppercase; letter-spacing: .06em; color: var(--uza-gray, #94A3B8); }
.tpe-pp-due-date { font-size: 12.5px; font-weight: 500; color: var(--uza-navy, #1E2A4A); font-variant-numeric: tabular-nums; }
.tpe-pp-chip { font-size: 10.5px; font-weight: 600; padding: 2px 8px; border-radius: 999px; }
.tpe-pp-chip.tone-danger { background: rgba(226,75,74,.12); color: #C0392B; }
.tpe-pp-chip.tone-warn   { background: rgba(239,159,39,.14); color: #B87600; }
.tpe-pp-chip.tone-ok     { background: rgba(29,158,117,.12); color: #137A57; }
.tpe-pp-chip.tone-muted  { background: var(--uza-bg, #F1F5F9); color: var(--uza-gray, #94A3B8); }

.status-group-wrap {
  display: flex; flex-direction: column; gap: 8px;
  flex: 1; min-width: 0;
}
.status-row { display: flex; gap: 6px; flex-wrap: wrap; align-items: center; }
.status-row--recurring {
  padding-top: 8px;
  border-top: 1px dashed var(--uza-border);
}
.status-group-label {
  font-size: 10px; font-weight: 500; letter-spacing: 0.06em;
  text-transform: uppercase;
  color: var(--uza-gray);
  margin-right: 4px;
  flex-shrink: 0;
}
.status-badge {
  display: inline-flex; align-items: center; gap: 6px;
  font-size: 11px; font-weight: 500;
  padding: 5px 11px;
  background: var(--bg1, #FFFFFF);
  border: 1px solid var(--uza-border);
  border-radius: 11px;
  color: var(--uza-navy);
  cursor: pointer;
  transition: all .15s;
}
.status-badge:hover:not(:disabled):not(.active) {
  border-color: var(--uza-purple);
  background: rgba(127, 119, 221, .04);
}
.status-badge.active {
  background: var(--accent, var(--uza-purple));
  color: #fff;
  border-color: var(--accent, var(--uza-purple));
}
.status-badge.active .dot { background: var(--bg1, #fff) !important; }
.status-badge .dot { width: 6px; height: 6px; border-radius: 50%; }
.status-badge:disabled { cursor: default; opacity: .85; }

/* Recurring-pill — slightly muted base look, distinct from standard 4 */
.status-badge--recurring:not(.active) {
  background: var(--uza-bg);
  border-color: var(--uza-border);
  color: var(--uza-gray);
}
.status-badge--recurring:not(.active):hover:not(:disabled) {
  color: var(--uza-navy);
  border-color: var(--uza-purple);
  background: rgba(127, 119, 221, .04);
}

.hero-progress {
  display: flex; align-items: center; gap: 10px;
  min-width: 180px; flex: 1; max-width: 320px;
}
.progress-track {
  flex: 1;
  height: 6px;
  background: var(--uza-bg);
  border: 1px solid var(--uza-border);
  border-radius: 4px; overflow: hidden;
}
.progress-fill {
  height: 100%;
  background: linear-gradient(90deg, var(--uza-purple), var(--uza-teal));
  border-radius: 3px;
  transition: width 500ms cubic-bezier(0.4, 0.6, 0.2, 1);
}
.progress-pct {
  font-size: 13px; font-weight: 500;
  color: var(--uza-navy);
  font-variant-numeric: tabular-nums;
  min-width: 36px; text-align: right;
}

.hero-due {
  display: inline-flex; align-items: baseline; gap: 7px;
  font-size: 12px;
}
.hero-due-label {
  font-size: 10px; font-weight: 500; letter-spacing: 0.06em;
  color: var(--uza-gray); text-transform: uppercase;
}
.hero-due-date {
  font-size: 13px; font-weight: 500;
  color: var(--uza-navy);
  font-variant-numeric: tabular-nums;
}
.hero-due-hint {
  font-size: 10.5px; font-weight: 500;
  padding: 2px 7px; border-radius: 4px;
}
.hero-due-hint.tone-danger { background: rgba(226, 75, 74, .12); color: var(--uza-red); }
.hero-due-hint.tone-warn   { background: rgba(239, 159, 39, .14); color: #B87600; }
.hero-due-hint.tone-ok     { background: rgba(29, 158, 117, .12); color: #137A57; }
.hero-due-hint.tone-muted  { background: var(--uza-bg); color: var(--uza-gray); }

/* Quarters under hero */
.hero-quarters {
  display: grid; grid-template-columns: repeat(4, 1fr);
  gap: 8px; margin-top: 14px;
}
.quarter-check {
  display: flex; align-items: center; justify-content: center; gap: 6px;
  padding: 8px;
  background: var(--bg1, #FFFFFF);
  border: 1px solid var(--uza-border);
  border-radius: 8px;
  cursor: pointer;
  transition: all .15s;
  font-size: 12px; font-weight: 500;
  color: var(--uza-navy);
}
.quarter-check input { display: none; }
.quarter-check:hover { border-color: var(--uza-purple); background: rgba(127, 119, 221, .04); }
.quarter-check.checked {
  background: rgba(29, 158, 117, .08);
  border-color: var(--uza-teal);
  color: var(--uza-teal);
}

/* ═══════════════════════════════════════════════════════════════ */
/* Parent project card (tasks only)                                */
/* ═══════════════════════════════════════════════════════════════ */
.parent-project-card {
  margin: 12px 24px 0;
  padding: 10px 12px 10px 20px;
  display: flex; align-items: center; gap: 10px;
  background: rgba(127, 119, 221, .04);
  border: 1px solid rgba(127, 119, 221, .18);
  --stripe-color: #7F77DD;
  border-radius: 8px;
}
.ppc-icon {
  width: 28px; height: 28px;
  display: flex; align-items: center; justify-content: center;
  background: rgba(127, 119, 221, .12);
  color: var(--uza-purple);
  border-radius: 6px;
  flex-shrink: 0;
}
.ppc-body { flex: 1; min-width: 0; }
.ppc-label {
  font-size: 9.5px; font-weight: 500; letter-spacing: 0.06em;
  color: var(--uza-gray); text-transform: uppercase;
}
.ppc-title-row { display: flex; align-items: baseline; gap: 8px; min-width: 0; margin-top: 1px; }
.ppc-num {
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  font-size: 11px; font-weight: 500;
  color: var(--uza-gray);
  flex-shrink: 0;
}
.ppc-title {
  font-size: 13px; font-weight: 500;
  color: var(--uza-navy);
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}
.ppc-year {
  font-size: 9px; font-weight: 600;
  background: rgba(127, 119, 221, .15);
  color: #5B53C2;
  padding: 1px 6px; border-radius: 3px;
  flex-shrink: 0;
}
.ppc-open {
  background: var(--bg1, #FFFFFF);
  border: 1px solid var(--uza-border);
  border-radius: 6px;
  padding: 6px;
  cursor: pointer;
  color: var(--uza-purple);
  transition: all .15s;
  flex-shrink: 0;
}
.ppc-open:hover { background: var(--uza-purple); color: #fff; border-color: var(--uza-purple); }

/* ═══════════════════════════════════════════════════════════════ */
/* TABS                                                            */
/* ═══════════════════════════════════════════════════════════════ */
.ed-tabs {
  display: flex;
  padding: 0 24px;
  border-bottom: 1px solid var(--uza-border);
  background: var(--bg1, #FFFFFF);
  flex-shrink: 0;
}
.ed-tab {
  background: transparent;
  border: none;
  padding: 12px 4px;
  margin-right: 24px;
  font-size: 13px; font-weight: 500;
  color: var(--uza-gray);
  cursor: pointer;
  position: relative;
  transition: color .15s;
  display: inline-flex; align-items: center; gap: 8px;
}
.ed-tab:hover { color: var(--uza-navy); }
.ed-tab.active {
  color: var(--uza-navy);
  font-weight: 600;
}
.ed-tab.active::after {
  content: "";
  position: absolute;
  bottom: -1px; left: 0; right: 0;
  height: 2px;
  background: var(--uza-purple);
  border-radius: 1px;
}
.tab-count {
  font-size: 10px; font-weight: 600;
  background: rgba(127, 119, 221, .15);
  color: #5B53C2;
  padding: 1px 7px;
  border-radius: 10px;
  min-width: 18px; text-align: center;
}

/* ═══════════════════════════════════════════════════════════════ */
/* DETAILS GRID — main + sticky rail                               */
/* ═══════════════════════════════════════════════════════════════ */
.ed-grid {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 280px;
  gap: 0;
  overflow-y: auto;
  max-height: calc(100vh - 380px);
  min-height: 300px;
}

.ed-main {
  padding: 20px 24px 24px;
  display: flex; flex-direction: column; gap: 16px;
  min-width: 0;
}

.ed-rail {
  margin: 16px 16px 16px 4px;
  padding: 16px;
  border: 1px solid #ECEAFB;
  background: linear-gradient(160deg, #FAFAFE 0%, #F6F5FD 100%);
  border-radius: 14px;
  display: flex; flex-direction: column; gap: 14px;
  align-self: start;
  position: sticky; top: 16px;
}

/* ─── Blocks (in main column) ──────────────────────────────────── */
.block {
  background: transparent;
  padding: 0;
}
.block-label {
  font-size: 10px; font-weight: 600; letter-spacing: 0.08em;
  color: var(--uza-gray); text-transform: uppercase;
  margin-bottom: 8px;
}
.block-label.flex { display: flex; align-items: center; justify-content: space-between; }
.block-label.inline { margin-bottom: 0; }

/* Foldable block (details/summary) */
.block-foldable {
  border: 1px solid var(--uza-border);
  border-radius: 10px;
  background: var(--uza-bg);
  padding: 0;
}
.block-summary {
  display: flex; align-items: center; justify-content: space-between;
  padding: 11px 14px;
  cursor: pointer;
  list-style: none;
  user-select: none;
}
.block-summary::-webkit-details-marker { display: none; }
.block-summary .caret {
  color: var(--uza-gray);
  transition: transform .2s;
}
.block-foldable[open] .block-summary .caret { transform: rotate(180deg); }
.block-content {
  padding: 4px 14px 14px;
  border-top: 1px solid var(--uza-border);
  display: flex; flex-direction: column; gap: 12px;
  background: var(--bg1, #FFFFFF);
}

.badge-mini {
  display: inline-block;
  font-size: 9px; font-weight: 600;
  background: rgba(29, 158, 117, .12);
  color: #137A57;
  padding: 1px 7px;
  border-radius: 4px;
  margin-left: 8px;
  text-transform: none;
  letter-spacing: 0;
}

/* ─── Fields ───────────────────────────────────────────────────── */
.field { display: flex; flex-direction: column; }
.field label {
  font-size: 10px; font-weight: 500; letter-spacing: 0.04em;
  color: var(--uza-gray); text-transform: uppercase;
  margin-bottom: 5px;
}
.field input, .field select, .field textarea {
  width: 100%;
  font-size: 13px;
  color: var(--uza-navy);
  background: var(--bg1, #FFFFFF);
  border: 1px solid var(--uza-border);
  border-radius: 7px;
  padding: 7px 11px;
  transition: border-color .15s, background .15s;
  font-family: inherit;
}
.field input:focus, .field select:focus, .field textarea:focus {
  outline: none; border-color: var(--uza-purple);
}
.field input:disabled, .field select:disabled, .field textarea:disabled {
  opacity: 0.6; cursor: not-allowed; background: var(--uza-bg);
}

.field-grid-2 { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; }

/* Period — one row layout */
.period-row {
  display: flex; align-items: flex-end; gap: 10px;
}
.period-field { flex: 1; }
.period-field label {
  font-size: 10px; font-weight: 500; letter-spacing: 0.04em;
  color: var(--uza-gray); text-transform: uppercase;
  margin-bottom: 5px;
  display: block;
}
.period-field input {
  width: 100%;
  font-size: 13px;
  color: var(--uza-navy);
  background: var(--bg1, #FFFFFF);
  border: 1px solid var(--uza-border);
  border-radius: 7px;
  padding: 7px 11px;
}
.period-field input:disabled { opacity: 0.6; background: var(--uza-bg); }
.period-sep {
  font-size: 14px; color: var(--uza-gray);
  padding-bottom: 8px;
}

/* Description textarea overrides MentionableTextarea defaults if needed */
.block :deep(textarea) {
  width: 100%;
  font-size: 13px;
  background: var(--bg1, #FFFFFF);
  border: 1px solid var(--uza-border);
  border-radius: 7px;
  padding: 9px 12px;
  font-family: inherit;
}

/* Effect grid */
.effect-grid {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 10px;
}
.effect-grid .field.full { grid-column: span 4; }

/* Pill toggle */
.pill-toggle { display: flex; gap: 6px; flex-wrap: wrap; }
.pill {
  font-size: 12px; font-weight: 500;
  padding: 6px 12px; border-radius: 11px;
  background: var(--bg1, #FFFFFF);
  border: 1px solid var(--uza-border);
  color: var(--uza-navy);
  cursor: pointer;
  transition: all .15s;
}
.pill.sm { padding: 5px 10px; font-size: 11px; }
.pill:hover:not(:disabled) { border-color: var(--uza-purple); }
.pill.active {
  background: var(--uza-purple); color: #fff;
  border-color: var(--uza-purple);
}
.pill:disabled { opacity: 0.5; cursor: not-allowed; }

.locked-hint {
  font-size: 9px; padding: 1px 6px;
  background: rgba(232, 75, 74, .12); color: var(--uza-red);
  border-radius: 4px; margin-left: 6px;
}

.hint {
  font-size: 11px; color: var(--uza-gray);
  margin: 6px 0 0; line-height: 1.4;
}
.hint-empty {
  display: block;
  margin-top: 4px;
  color: var(--uza-amber);
  font-weight: 500;
}

/* Switch */
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
  background: var(--bg1, #fff);
  border-radius: 50%;
  transition: transform 220ms var(--ease-standard);
}
.switch input:checked + .slider { background: var(--uza-teal); }
.switch input:checked + .slider::before { transform: translateX(16px); }

/* ─── Rail (right column) ──────────────────────────────────────── */
.rail-block { display: flex; flex-direction: column; }
.rail-label {
  font-size: 10px; font-weight: 600; letter-spacing: 0.08em;
  color: var(--uza-gray); text-transform: uppercase;
  margin-bottom: 6px;
}
.rail-select, .rail-input {
  width: 100%;
  font-size: 12.5px;
  color: var(--uza-navy);
  background: var(--bg2, #F8FAFC);
  border: 1.5px solid var(--border-input);
  border-radius: 10px;
  padding: 8px 10px;
  font-family: inherit;
}
.rail-select:focus, .rail-input:focus { outline: none; border-color: #7C6FF7; box-shadow: 0 0 0 3px rgba(124,111,247,.14); }
.rail-select:disabled, .rail-input:disabled { opacity: 0.6; background: var(--uza-bg); }

.rail-grid-2 { display: grid; grid-template-columns: 1fr 80px; gap: 10px; align-items: end; }

.rail-label-flex { display: flex; align-items: center; justify-content: space-between; }
.rail-year-chip {
  font-size: 9px; font-weight: 700; letter-spacing: 0.04em;
  color: #5B53C2; background: rgba(127,119,221,.12);
  padding: 1px 6px; border-radius: 5px; text-transform: none;
}
.rail-proj-empty { font-size: 10.5px; color: var(--uza-gray); margin: 6px 0 0; line-height: 1.35; }

.rail-archive {
  display: inline-flex; align-items: center; justify-content: center; gap: 7px;
  width: 100%;
  font-size: 12px; font-weight: 500;
  background: var(--bg1, #FFFFFF);
  border: 1px solid rgba(226, 75, 74, .3);
  color: #C0392B;
  border-radius: 8px;
  padding: 9px 12px;
  cursor: pointer;
  transition: all .15s;
}
.rail-archive:hover:not(:disabled) {
  background: rgba(226, 75, 74, .07);
  color: #C0392B;
  border-color: rgba(226, 75, 74, .45);
}
.rail-archive:disabled { opacity: 0.5; cursor: not-allowed; }

/* ─── Consultant picker ────────────────────────────────────────── */
.consultant-picker { position: relative; }
.consultant-trigger {
  display: flex; align-items: center; gap: 8px;
  width: 100%;
  background: var(--bg2, #F8FAFC);
  border: 1.5px solid var(--border-input);
  border-radius: 10px;
  padding: 8px 10px;
  cursor: pointer;
  font-size: 12.5px;
  color: var(--uza-navy);
  transition: border-color .15s;
}
.consultant-trigger:hover:not(:disabled) { border-color: var(--uza-purple); }
.consultant-trigger:disabled { opacity: 0.6; cursor: not-allowed; background: var(--uza-bg); }
.consultant-name { flex: 1; text-align: left; font-weight: 500; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.consultant-placeholder { flex: 1; text-align: left; color: var(--uza-gray); }
.caret { margin-left: auto; transition: transform .15s; color: var(--uza-gray); flex-shrink: 0; }
.consultant-picker.open .caret { transform: rotate(180deg); }

.consultant-menu {
  position: absolute; top: calc(100% + 4px); left: 0; right: 0;
  background: var(--bg1, #FFFFFF);
  border: 1px solid var(--uza-border);
  border-radius: 8px;
  box-shadow: 0 8px 24px rgba(15,23,60,.12);
  max-height: 260px; overflow-y: auto;
  z-index: 1500;
  animation: menuIn 180ms ease;
}
@keyframes menuIn {
  from { opacity: 0; transform: translateY(-4px); }
  to   { opacity: 1; transform: translateY(0); }
}
.consultant-opt {
  display: flex; align-items: center; gap: 8px;
  padding: 7px 11px;
  cursor: pointer;
  font-size: 12.5px;
  transition: background .12s;
}
.consultant-opt:hover { background: rgba(127, 119, 221, .08); }
.consultant-opt.active { background: rgba(127, 119, 221, .12); font-weight: 500; }
.big4 {
  font-size: 9px; font-weight: 600;
  background: rgba(239, 159, 39, .18);
  color: #B87600;
  padding: 1px 6px; border-radius: 4px;
  margin-left: auto;
}

/* ═══════════════════════════════════════════════════════════════ */
/* COMMENTS PANE                                                   */
/* ═══════════════════════════════════════════════════════════════ */
.ed-comments-pane {
  padding: 20px 24px 24px;
  overflow-y: auto;
  max-height: calc(100vh - 380px);
  min-height: 300px;
  display: flex; flex-direction: column;
}

.comment-input-row {
  display: flex; gap: 10px;
  margin-bottom: 18px;
  align-items: flex-end;
}
.comment-input-row :deep(textarea) {
  flex: 1;
  font-size: 13px;
  background: var(--bg1, #FFFFFF);
  border: 1px solid var(--uza-border);
  border-radius: 8px;
  padding: 9px 12px;
  resize: none;
  font-family: inherit;
}

.comments-list {
  display: flex; flex-direction: column; gap: 12px;
  flex: 1;
}
.comment-item {
  padding: 11px 13px;
  background: var(--bg1, #FFFFFF);
  border: 1px solid var(--uza-border);
  border-radius: 8px;
}
.comment-head {
  display: flex; align-items: center; gap: 8px;
  margin-bottom: 6px;
}
.avatar {
  width: 26px; height: 26px;
  border-radius: 50%;
  display: flex; align-items: center; justify-content: center;
  color: #fff; font-size: 11px; font-weight: 600;
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
  opacity: 0; transition: opacity .15s;
}
.comment-item:hover .comment-actions { opacity: 1; }
.comment-body {
  font-size: 13px; line-height: 1.5; color: var(--uza-navy);
  margin: 0; white-space: pre-wrap;
}
.comment-edit textarea {
  width: 100%;
  font-size: 13px;
  background: var(--bg1, #FFFFFF);
  border: 1px solid var(--uza-purple);
  border-radius: 7px;
  padding: 8px 10px;
  font-family: inherit;
}
.comment-edit-buttons {
  display: flex; gap: 6px; margin-top: 6px;
  justify-content: flex-end;
}

.empty {
  padding: 28px 18px;
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

/* ═══════════════════════════════════════════════════════════════ */
/* FOOTER                                                          */
/* ═══════════════════════════════════════════════════════════════ */
/* 2026-05-26: tab transition host — relative chrome for the absolute-positioned
   .uza-tab-leave-active state defined in motion.css. */
.ed-tab-host {
  position: relative;
  flex: 1;
  min-height: 0;
  overflow: hidden;
  display: flex;
  flex-direction: column;
}

.ed-footer {
  display: flex; align-items: center; gap: 10px;
  padding: 12px 20px;
  border-top: 1px solid var(--uza-border);
  background: var(--bg2, #FAFAFC);
  flex-shrink: 0;
}
.footer-spacer { flex: 1; }

.btn {
  font-size: 13px; font-weight: 500;
  padding: 8px 16px;
  background: var(--bg1, #FFFFFF);
  border: 1px solid var(--uza-border);
  border-radius: 8px;
  color: var(--uza-navy);
  cursor: pointer;
  transition: all .15s;
  font-family: inherit;
}
.btn.sm { padding: 5px 11px; font-size: 12px; }
.btn:hover:not(:disabled) { border-color: var(--uza-purple); }
.btn:disabled { opacity: 0.5; cursor: not-allowed; }

.btn-primary {
  background: var(--uza-purple); color: #fff;
  border-color: var(--uza-purple);
}
.btn-primary:hover:not(:disabled) {
  background: #6B62D2; border-color: #6B62D2;
}

.error-msg {
  font-size: 12px; color: var(--uza-red);
  margin: 0;
}

/* ═══════════════════════════════════════════════════════════════ */
/* Responsive                                                      */
/* ═══════════════════════════════════════════════════════════════ */
@media (max-width: 860px) {
  .ed-grid {
    grid-template-columns: 1fr;
  }
  .ed-rail {
    border-left: none;
    border-top: 1px solid var(--uza-border);
    position: static;
  }
  .effect-grid { grid-template-columns: 1fr 1fr; }
  .effect-grid .field.full { grid-column: span 2; }
  .hero-status-row { gap: 10px; }
  .hero-progress { min-width: 140px; }
}

@media (prefers-reduced-motion: reduce) {
  .editor-shell, .progress-fill, .quarter-check, .consultant-menu, .ed-tab.active::after {
    animation: none !important;
    transition: none !important;
  }
}
</style>
