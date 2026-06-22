<!--
  CompanyNotesTab.vue -- Smart Journal вкладка для Company Workspace.

  Архитектура B+C: 5 kind (event/decision/task/risk/observation),
  tags TEXT[], event_date/due_date, is_resolved, polymorphic note_links.

  Интеграция праздников Узбекистана (holidays.ts):
  1. Timeline group headers -- pill с праздником рядом с датой
  2. Sticky widget предстоящих праздников (≤14 дней)
  3. Due-date conflict warning + CTA "сдвинуть на след. рабочий"
  4. Calendar input wrapper с подсветкой праздничных дат
  5. Filter chip "Включая праздники" -- synthetic timeline items

  10 анимаций -- см. <style> блок.
-->
<script setup lang="ts">
import {
  ref,
  computed,
  watch,
  onMounted,
  reactive,
} from "vue";
import {
  notesApi,
  NOTE_KINDS,
  NOTE_KIND_LABELS,
  NOTE_KIND_COLORS,
  NOTE_KIND_ICONS,
  LINK_ENTITY_LABELS,
  type Note,
  type NoteKind,
  type NoteLink,
  type LinkEntityType,
  type TagCount,
  type ChecklistItem,
  type ChecklistItemIn,
} from "@/api/notes";
import {
  upcomingHolidays,
  getHoliday,
  checkDueDateConflict,
  daysUntil,
  toIsoDate,
  HOLIDAY_KIND_COLORS,
  HOLIDAY_KIND_LABELS,
  type UzHoliday,
} from "@/api/holidays";
import { useConfirm } from "@/composables/useConfirm";
import { useToast } from "@/composables/useToast";
import NoteAssigneePicker from "@/components/NoteAssigneePicker.vue";

const { confirmDialog } = useConfirm();
const toast = useToast();

// Черновик пункта чек-листа в форме (id есть только у существующих).
interface ChecklistDraft {
  id: string | null;
  text: string;
  is_done: boolean;
  assignee_id: string | null;
  assignee_name: string | null;
}

const props = defineProps<{
  companyId: string;
  companyCode?: string;
  year?: number;
}>();

// ============================================================
// STATE
// ============================================================
const loading = ref(true);
const error = ref<string | null>(null);
const notes = ref<Note[]>([]);
const tagCounts = ref<TagCount[]>([]);

const search = ref("");
const activeKinds = ref<Set<NoteKind>>(new Set());
const activeTags = ref<Set<string>>(new Set());
const onlyUnresolved = ref(false);
const showResolved = ref(true);
const includeHolidays = ref(true);
// Calendar date-filter (yyyy-mm-dd) — null = no date filter
const calendarFilterDate = ref<string | null>(null);

// Modal
const modalOpen = ref(false);
const modalMode = ref<"create" | "edit">("create");
const modalSubmitting = ref(false);
const modalError = ref<string | null>(null);

const form = reactive<{
  id: string | null;
  kind: NoteKind;
  title: string;
  body: string;
  tags: string[];
  tagInput: string;
  event_date: string;
  due_date: string;
  is_pinned: boolean;
  links: NoteLink[];
  linkType: LinkEntityType;
  linkLabel: string;
  linkKey: string;
  assignee_id: string | null;
  assignee_name: string | null;
  checklist: ChecklistDraft[];
  checklistInput: string;
}>({
  id: null,
  kind: "observation",
  title: "",
  body: "",
  tags: [],
  tagInput: "",
  event_date: "",
  due_date: "",
  is_pinned: false,
  links: [],
  linkType: "project",
  linkLabel: "",
  linkKey: "",
  assignee_id: null,
  assignee_name: null,
  checklist: [],
  checklistInput: "",
});

// Прогресс чек-листа в форме (для лайв-индикатора в модалке).
const formChecklistDone = computed(() => form.checklist.filter((c) => c.is_done).length);
const formChecklistPct = computed(() =>
  form.checklist.length ? Math.round((formChecklistDone.value / form.checklist.length) * 100) : 0,
);

function addChecklistItem() {
  const t = form.checklistInput.trim();
  if (!t) return;
  form.checklist.push({ id: null, text: t, is_done: false, assignee_id: null, assignee_name: null });
  form.checklistInput = "";
}

function removeChecklistItem(idx: number) {
  form.checklist.splice(idx, 1);
}

function moveChecklistItem(idx: number, dir: -1 | 1) {
  const j = idx + dir;
  if (j < 0 || j >= form.checklist.length) return;
  const arr = form.checklist;
  [arr[idx], arr[j]] = [arr[j], arr[idx]];
}

// Прогресс чек-листа у сохранённой заметки (для карточки).
function checklistStats(n: Note): { done: number; total: number; pct: number } | null {
  if (!n.checklist || !n.checklist.length) return null;
  const total = n.checklist.length;
  const done = n.checklist.filter((c) => c.is_done).length;
  return { done, total, pct: Math.round((done / total) * 100) };
}

function sortedChecklist(n: Note): ChecklistItem[] {
  return (n.checklist || []).slice().sort((a, b) => a.position - b.position);
}

function avInitials(name?: string | null): string {
  const n = (name || "").trim();
  if (!n) return "?";
  const parts = n.split(/\s+/).filter(Boolean);
  const a = parts[0]?.[0] || "";
  const b = parts.length > 1 ? parts[parts.length - 1][0] : "";
  return (a + b).toUpperCase() || "?";
}

// Локально переключить галочку пункта прямо с карточки (+ уведомление при провале).
const togglingItem = ref<Set<string>>(new Set());
async function toggleChecklistItem(n: Note, item: ChecklistItem) {
  if (togglingItem.value.has(item.id)) return;
  togglingItem.value.add(item.id);
  const next = !item.is_done;
  // оптимистично
  item.is_done = next;
  try {
    const updated = await notesApi.patchChecklistItem(item.id, { is_done: next });
    // подменяем заметку в списке свежими данными
    const idx = notes.value.findIndex((x) => x.id === n.id);
    if (idx >= 0) notes.value[idx] = updated;
  } catch (e: any) {
    item.is_done = !next; // откат
    toast.error(e?.response?.data?.detail || "Не удалось сохранить пункт");
  } finally {
    togglingItem.value.delete(item.id);
  }
}

// ============================================================
// LOAD
// ============================================================
async function load() {
  loading.value = true;
  error.value = null;
  try {
    const resp = await notesApi.list({
      company_id: props.companyId,
      kind: activeKinds.value.size
        ? Array.from(activeKinds.value)
        : undefined,
      tag: activeTags.value.size ? Array.from(activeTags.value) : undefined,
      q: search.value.trim() || undefined,
      only_unresolved: onlyUnresolved.value,
      include_resolved: showResolved.value,
      pinned_first: true,
      limit: 500,
    });
    notes.value = resp.items;
    tagCounts.value = resp.tag_counts;
  } catch (e: any) {
    error.value = e?.message || "Не удалось загрузить заметки";
    notes.value = [];
  } finally {
    loading.value = false;
  }
}

// debounce search
let _searchTimer: any = null;
watch(search, () => {
  if (_searchTimer) clearTimeout(_searchTimer);
  _searchTimer = setTimeout(load, 350);
});

watch(
  [
    () => props.companyId,
    activeKinds,
    activeTags,
    onlyUnresolved,
    showResolved,
  ],
  load,
  { deep: true },
);

onMounted(load);

// ============================================================
// COMPUTED -- timeline groups + holidays integration
// ============================================================
interface TimelineItem {
  type: "note" | "holiday";
  date: string;
  note?: Note;
  holiday?: UzHoliday;
  sortKey: string;
}

interface TimelineGroup {
  key: string;
  label: string;
  dateIso: string; // для holiday lookup
  items: TimelineItem[];
  holiday: UzHoliday | null;
}

// Apply calendar date-filter on the full notes list before timeline grouping
const visibleNotes = computed(() => {
  if (!calendarFilterDate.value) return notes.value;
  const target = calendarFilterDate.value;
  return notes.value.filter((n) => {
    const iso = (n.event_date || n.due_date || n.created_at).slice(0, 10);
    return iso === target;
  });
});

const pinnedNotes = computed(() => visibleNotes.value.filter((n) => n.is_pinned));

const _activeNotes = computed(() => visibleNotes.value.filter((n) => !n.is_pinned));

const upcoming = computed(() => upcomingHolidays(new Date(), 14));

function _itemDate(n: Note): string {
  // event_date если есть, иначе created_at
  return (n.event_date || n.created_at).slice(0, 10);
}

const timelineGroups = computed<TimelineGroup[]>(() => {
  const map = new Map<string, TimelineGroup>();
  const today = new Date();
  const todayIso = toIsoDate(today);

  function _groupKeyAndLabel(iso: string): { key: string; label: string } {
    const d = new Date(iso);
    const diff = daysUntil(d, today);
    if (iso === todayIso) return { key: "today", label: "Сегодня" };
    if (diff === -1) return { key: "yesterday", label: "Вчера" };
    if (diff === 1) return { key: "tomorrow", label: "Завтра" };
    if (diff > 1 && diff <= 7)
      return { key: "this_week", label: "На этой неделе" };
    if (diff < -1 && diff >= -7)
      return { key: "last_week", label: "На прошлой неделе" };
    // Иначе -- по месяцам
    const months = [
      "Январь",
      "Февраль",
      "Март",
      "Апрель",
      "Май",
      "Июнь",
      "Июль",
      "Август",
      "Сентябрь",
      "Октябрь",
      "Ноябрь",
      "Декабрь",
    ];
    const key = `m_${d.getFullYear()}_${d.getMonth()}`;
    const label = `${months[d.getMonth()]} ${d.getFullYear()}`;
    return { key, label };
  }

  // Notes -> groups
  for (const n of _activeNotes.value) {
    const iso = _itemDate(n);
    const { key, label } = _groupKeyAndLabel(iso);
    if (!map.has(key)) {
      map.set(key, {
        key,
        label,
        dateIso: iso,
        items: [],
        holiday: null,
      });
    }
    map.get(key)!.items.push({
      type: "note",
      date: iso,
      note: n,
      sortKey: iso + "_" + n.id,
    });
  }

  // Если includeHolidays -- вставляем synthetic holiday items
  if (includeHolidays.value) {
    // Прошлые/будущие праздники в окне ±60 дней
    const fromD = new Date(today);
    fromD.setDate(fromD.getDate() - 60);
    const winHolidays = upcomingHolidays(fromD, 120);
    for (const h of winHolidays) {
      const iso = h.date;
      const { key, label } = _groupKeyAndLabel(iso);
      if (!map.has(key)) {
        map.set(key, {
          key,
          label,
          dateIso: iso,
          items: [],
          holiday: null,
        });
      }
      const grp = map.get(key)!;
      // Если это main holiday группы -- ставим как metadata
      if (!grp.holiday && h.is_dayoff) {
        grp.holiday = h;
      }
      grp.items.push({
        type: "holiday",
        date: iso,
        holiday: h,
        sortKey: iso + "_h_" + h.title_ru,
      });
    }
  } else {
    // Без synthetic items -- но holiday metadata в headers всё равно показываем
    for (const grp of map.values()) {
      const h = getHoliday(grp.dateIso);
      if (h && h.is_dayoff) grp.holiday = h;
    }
  }

  // Сортировка items внутри группы, групп -- по дате (DESC)
  const groups = Array.from(map.values());
  for (const g of groups) {
    g.items.sort((a, b) => b.sortKey.localeCompare(a.sortKey));
  }
  groups.sort((a, b) => {
    // future first, then today, then past
    return b.dateIso.localeCompare(a.dateIso);
  });
  return groups;
});

const isEmpty = computed(
  () =>
    !loading.value &&
    pinnedNotes.value.length === 0 &&
    timelineGroups.value.every((g) =>
      g.items.every((i) => i.type === "holiday"),
    ),
);

// ============================================================
// FILTER CHIPS
// ============================================================
function toggleKind(k: NoteKind) {
  if (activeKinds.value.has(k)) activeKinds.value.delete(k);
  else activeKinds.value.add(k);
  activeKinds.value = new Set(activeKinds.value); // trigger reactivity
}

function toggleTag(t: string) {
  if (activeTags.value.has(t)) activeTags.value.delete(t);
  else activeTags.value.add(t);
  activeTags.value = new Set(activeTags.value);
}

function kindCount(k: NoteKind): number {
  return notes.value.filter((n) => n.kind === k).length;
}

// ============================================================
// CARD ACTIONS
// ============================================================
async function togglePin(n: Note) {
  try {
    await notesApi.update(n.id, { is_pinned: !n.is_pinned });
    await load();
    toast.success(n.is_pinned ? "Откреплено" : "Закреплено вверху");
  } catch (e: any) {
    error.value = e?.message || "Ошибка при закреплении";
    toast.error("Не удалось изменить закрепление");
  }
}

async function toggleResolve(n: Note) {
  try {
    await notesApi.update(n.id, { is_resolved: !n.is_resolved });
    await load();
    toast.success(n.is_resolved ? "Снова открыто" : "Отмечено закрытым");
  } catch (e: any) {
    error.value = e?.message || "Ошибка при изменении статуса";
    toast.error("Не удалось изменить статус");
  }
}

async function removeNote(n: Note) {
  if (
    !(await confirmDialog({
      message: `Удалить заметку «${n.title || n.body.slice(0, 40)}»? Действие необратимо.`,
      danger: true,
    }))
  )
    return;
  try {
    await notesApi.delete(n.id);
    await load();
    toast.success("Запись удалена");
  } catch (e: any) {
    error.value = e?.message || "Ошибка при удалении";
    toast.error("Не удалось удалить запись");
  }
}

// expand state
const expanded = ref<Set<string>>(new Set());
function toggleExpand(id: string) {
  if (expanded.value.has(id)) expanded.value.delete(id);
  else expanded.value.add(id);
  expanded.value = new Set(expanded.value);
}

// ============================================================
// MODAL
// ============================================================
function resetForm() {
  form.id = null;
  form.kind = "observation";
  form.title = "";
  form.body = "";
  form.tags = [];
  form.tagInput = "";
  form.event_date = toIsoDate(new Date());
  form.due_date = "";
  form.is_pinned = false;
  form.links = [];
  form.linkType = "project";
  form.linkLabel = "";
  form.linkKey = "";
  form.assignee_id = null;
  form.assignee_name = null;
  form.checklist = [];
  form.checklistInput = "";
  modalError.value = null;
}

function openCreate(presetKind?: NoteKind) {
  resetForm();
  if (presetKind) form.kind = presetKind;
  modalMode.value = "create";
  modalOpen.value = true;
}

function openEdit(n: Note) {
  resetForm();
  form.id = n.id;
  form.kind = n.kind;
  form.title = n.title || "";
  form.body = n.body;
  form.tags = [...n.tags];
  form.event_date = n.event_date ? n.event_date.slice(0, 10) : "";
  form.due_date = n.due_date ? n.due_date.slice(0, 10) : "";
  form.is_pinned = n.is_pinned;
  form.links = [...n.links];
  form.assignee_id = n.assignee_id || null;
  form.assignee_name = n.assignee_name || null;
  form.checklist = (n.checklist || [])
    .slice()
    .sort((a, b) => a.position - b.position)
    .map((c) => ({
      id: c.id,
      text: c.text,
      is_done: c.is_done,
      assignee_id: c.assignee_id || null,
      assignee_name: c.assignee_name || null,
    }));
  modalMode.value = "edit";
  modalOpen.value = true;
}

function closeModal() {
  modalOpen.value = false;
  setTimeout(resetForm, 300);
}

function addTagFromInput() {
  const t = form.tagInput.trim().toLowerCase();
  if (!t) return;
  if (form.tags.includes(t)) {
    form.tagInput = "";
    return;
  }
  form.tags.push(t);
  form.tagInput = "";
}

function removeTag(t: string) {
  form.tags = form.tags.filter((x) => x !== t);
}

function addLink() {
  if (!form.linkLabel.trim()) {
    modalError.value = "Укажите название связанной сущности";
    return;
  }
  form.links.push({
    entity_type: form.linkType,
    entity_id: null,
    entity_key: form.linkKey.trim() || form.linkLabel.trim(),
    entity_label: form.linkLabel.trim(),
  });
  form.linkLabel = "";
  form.linkKey = "";
  modalError.value = null;
}

function removeLink(idx: number) {
  form.links.splice(idx, 1);
}

// === Due date / event date validation ===
const eventConflict = computed(() => {
  if (!form.event_date) return null;
  return checkDueDateConflict(form.event_date, 5);
});

const dueConflict = computed(() => {
  if (!form.due_date) return null;
  return checkDueDateConflict(form.due_date, 5);
});

function applyEventSuggestion() {
  if (eventConflict.value?.suggested) {
    form.event_date = toIsoDate(eventConflict.value.suggested);
  }
}

function applyDueSuggestion() {
  if (dueConflict.value?.suggested) {
    form.due_date = toIsoDate(dueConflict.value.suggested);
  }
}

async function submit() {
  modalError.value = null;
  if (!form.body.trim()) {
    modalError.value = "Заполните содержание заметки";
    return;
  }
  // подхватываем недобавленный пункт из поля ввода
  if (form.checklistInput.trim()) addChecklistItem();
  modalSubmitting.value = true;
  try {
    const checklist: ChecklistItemIn[] = form.checklist
      .filter((c) => c.text.trim())
      .map((c, i) => ({
        id: c.id || undefined,
        text: c.text.trim(),
        is_done: c.is_done,
        position: i,
        assignee_id: c.assignee_id || null,
        assignee_name: c.assignee_name || null,
      }));
    const payload: any = {
      company_id: props.companyId,
      kind: form.kind,
      title: form.title.trim() || null,
      body: form.body.trim(),
      tags: form.tags,
      is_pinned: form.is_pinned,
      event_date: form.event_date
        ? new Date(form.event_date).toISOString()
        : null,
      due_date: form.due_date
        ? new Date(form.due_date).toISOString()
        : null,
      assignee_id: form.assignee_id || null,
      assignee_name: form.assignee_name || null,
      links: form.links.map((l) => ({
        entity_type: l.entity_type,
        entity_id: l.entity_id || null,
        entity_key: l.entity_key || null,
        entity_label: l.entity_label || null,
      })),
      checklist,
    };
    const isCreate = modalMode.value === "create";
    if (isCreate) {
      await notesApi.create(payload);
    } else if (form.id) {
      await notesApi.update(form.id, payload);
    }
    closeModal();
    await load();
    toast.success(isCreate ? "Запись создана" : "Изменения сохранены");
  } catch (e: any) {
    modalError.value = e?.response?.data?.detail || e?.message || "Ошибка сохранения";
    toast.error("Не удалось сохранить запись");
  } finally {
    modalSubmitting.value = false;
  }
}

// ============================================================
// UI HELPERS
// ============================================================
function formatTimeAgo(iso: string): string {
  const d = new Date(iso);
  const diffMin = Math.floor((Date.now() - d.getTime()) / 60000);
  if (diffMin < 1) return "только что";
  if (diffMin < 60) return `${diffMin} мин назад`;
  const h = Math.floor(diffMin / 60);
  if (h < 24) return `${h} ч назад`;
  const days = Math.floor(h / 24);
  if (days < 7) return `${days} дн назад`;
  return d.toLocaleDateString("ru-RU", {
    day: "numeric",
    month: "short",
    year: d.getFullYear() !== new Date().getFullYear() ? "numeric" : undefined,
  });
}

function formatDateShort(iso: string): string {
  const d = new Date(iso);
  return d.toLocaleDateString("ru-RU", {
    day: "numeric",
    month: "short",
  });
}

function formatDateGroup(g: TimelineGroup): string {
  // "Сегодня · 8 мая" вместо просто "Сегодня"
  if (["today", "yesterday", "tomorrow"].includes(g.key)) {
    return `${g.label} · ${formatDateShort(g.dateIso)}`;
  }
  return g.label;
}

function dueProgress(n: Note): {
  pct: number;
  daysLeft: number;
  state: "ok" | "warn" | "overdue";
} | null {
  if (!n.due_date || n.is_resolved || n.kind !== "task") return null;
  const due = new Date(n.due_date);
  const now = Date.now();
  const dueTime = due.getTime();
  const created = new Date(n.created_at).getTime();
  const total = Math.max(86_400_000, dueTime - created);
  const elapsed = now - created;
  const pct = Math.min(100, Math.max(0, (elapsed / total) * 100));
  const daysLeft = Math.ceil((dueTime - now) / 86_400_000);
  let state: "ok" | "warn" | "overdue" = "ok";
  if (daysLeft < 0) state = "overdue";
  else if (daysLeft <= 3) state = "warn";
  return { pct, daysLeft, state };
}

function isHolidayDayoff(dateStr: string | null | undefined): UzHoliday | null {
  if (!dateStr) return null;
  const h = getHoliday(dateStr);
  if (h && h.is_dayoff) return h;
  return null;
}
</script>

<template>
  <div class="cn-root">
    <!-- ============================================================ -->
    <!-- TOP BAR -->
    <!-- ============================================================ -->
    <div class="cn-top">
      <div class="cn-top-left">
        <div class="cn-search">
          <svg
            class="cn-search-icon"
            width="14"
            height="14"
            viewBox="0 0 16 16"
            fill="none"
          >
            <circle
              cx="7"
              cy="7"
              r="5"
              stroke="currentColor"
              stroke-width="1.6"
            />
            <path
              d="M11 11 L14 14"
              stroke="currentColor"
              stroke-width="1.6"
              stroke-linecap="round"
            />
          </svg>
          <input
            v-model="search"
            type="text"
            placeholder="Поиск по заголовку и тексту..."
          />
          <button
            v-if="search"
            class="cn-search-clear"
            @click="search = ''"
            title="Очистить"
          >
            ×
          </button>
        </div>
      </div>
      <div class="cn-top-right">
        <button class="cn-btn-primary" @click="openCreate()">
          <svg width="12" height="12" viewBox="0 0 12 12" fill="none">
            <path
              d="M6 1 V11 M1 6 H11"
              stroke="currentColor"
              stroke-width="1.8"
              stroke-linecap="round"
            />
          </svg>
          <span>Добавить запись</span>
        </button>
      </div>
    </div>

    <!-- ============================================================ -->
    <!-- KIND FILTER CHIPS + toggles -->
    <!-- ============================================================ -->
    <div class="cn-filters">
      <div class="cn-chips">
        <button
          v-for="k in NOTE_KINDS"
          :key="k"
          class="cn-chip"
          :class="{ 'cn-chip-active': activeKinds.has(k) }"
          :style="{
            '--chip-color': NOTE_KIND_COLORS[k],
          }"
          @click="toggleKind(k)"
        >
          <svg
            class="cn-chip-icon"
            width="12"
            height="12"
            viewBox="0 0 16 16"
            fill="none"
            v-html="NOTE_KIND_ICONS[k]"
          />
          <span class="cn-chip-label">{{ NOTE_KIND_LABELS[k] }}</span>
          <span class="cn-chip-count">{{ kindCount(k) }}</span>
        </button>
      </div>
      <div class="cn-toggles">
        <label class="cn-toggle">
          <input
            type="checkbox"
            v-model="onlyUnresolved"
          />
          <span>Только незакрытые</span>
        </label>
        <label class="cn-toggle">
          <input
            type="checkbox"
            v-model="includeHolidays"
          />
          <span>Включая праздники</span>
        </label>
      </div>
    </div>

    <!-- ============================================================ -->
    <!-- TAG CLOUD -->
    <!-- ============================================================ -->
    <div v-if="tagCounts.length" class="cn-tag-cloud">
      <span class="cn-tag-cloud-label">Теги:</span>
      <button
        v-for="tc in tagCounts.slice(0, 20)"
        :key="tc.tag"
        class="cn-tag"
        :class="{ 'cn-tag-active': activeTags.has(tc.tag) }"
        @click="toggleTag(tc.tag)"
      >
        #{{ tc.tag }}
        <span class="cn-tag-count">{{ tc.count }}</span>
      </button>
    </div>

    <!-- Встроенный календарь модуля заметок удалён — есть общий «Календарь»
         над модулем (CompanyCalendar). Дата-фильтр заметок при необходимости
         задаётся программно через calendarFilterDate. -->

    <!-- ============================================================ -->
    <!-- HOLIDAYS WIDGET (if upcoming ≤14 days) -->
    <!-- ============================================================ -->
    <div
      v-if="includeHolidays && upcoming.length"
      class="cn-holidays-widget"
    >
      <div class="cn-hw-title">
        <svg width="14" height="14" viewBox="0 0 16 16" fill="none">
          <rect
            x="2"
            y="3"
            width="12"
            height="11"
            rx="1.5"
            stroke="currentColor"
            stroke-width="1.6"
          />
          <path
            d="M2 6 H14 M5 1 V4 M11 1 V4"
            stroke="currentColor"
            stroke-width="1.6"
            stroke-linecap="round"
          />
        </svg>
        <span>Предстоящие праздники (14 дней)</span>
      </div>
      <div class="cn-hw-items">
        <div
          v-for="h in upcoming"
          :key="h.date"
          class="cn-hw-item"
          :style="{ '--h-color': HOLIDAY_KIND_COLORS[h.kind] }"
        >
          <div class="cn-hw-date">{{ formatDateShort(h.date) }}</div>
          <div class="cn-hw-info">
            <div class="cn-hw-title-text">{{ h.title_ru }}</div>
            <div class="cn-hw-meta">
              <span class="cn-hw-kind">{{ HOLIDAY_KIND_LABELS[h.kind] }}</span>
              <span v-if="h.is_dayoff" class="cn-hw-dayoff">нерабочий</span>
              <span class="cn-hw-countdown">
                {{ daysUntil(h.date) === 0 ? "сегодня" : daysUntil(h.date) === 1 ? "завтра" : `через ${daysUntil(h.date)} дн.` }}
              </span>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- ============================================================ -->
    <!-- ERROR / LOADING -->
    <!-- ============================================================ -->
    <div v-if="error" class="cn-error">{{ error }}</div>

    <div v-if="loading" class="cn-loading">
      <div class="cn-spinner"></div>
      <span>Загрузка журнала...</span>
    </div>

    <!-- ============================================================ -->
    <!-- PINNED -->
    <!-- ============================================================ -->
    <div v-if="!loading && pinnedNotes.length" class="cn-pinned-section">
      <div class="cn-section-label">
        <svg width="11" height="11" viewBox="0 0 16 16" fill="none">
          <path
            d="M8 1 L10 6 L15 6.5 L11 10 L12 15 L8 12 L4 15 L5 10 L1 6.5 L6 6 Z"
            fill="currentColor"
          />
        </svg>
        Закреплённые
      </div>
      <div class="cn-cards-grid">
        <div
          v-for="(n, i) in pinnedNotes"
          :key="n.id"
          class="cn-card cn-card-pinned"
          :class="{ 'cn-card-resolved': n.is_resolved }"
          :data-kind="n.kind"
          :style="{
            '--kind-color': NOTE_KIND_COLORS[n.kind],
            animationDelay: `${i * 60}ms`,
          }"
          @click="toggleExpand(n.id)"
        >
          <div class="cn-card-head">
            <div class="cn-card-kind">
              <svg
                width="14"
                height="14"
                viewBox="0 0 16 16"
                fill="none"
                v-html="NOTE_KIND_ICONS[n.kind]"
              />
              <span>{{ NOTE_KIND_LABELS[n.kind] }}</span>
            </div>
            <div class="cn-card-actions" @click.stop>
              <button
                class="cn-icon-btn"
                @click="togglePin(n)"
                title="Открепить"
              >
                <svg width="12" height="12" viewBox="0 0 16 16" fill="none">
                  <path
                    d="M5 2 L11 2 L11 8 L13 10 L3 10 L5 8 Z M8 10 V14"
                    stroke="currentColor"
                    stroke-width="1.5"
                    stroke-linejoin="round"
                  />
                </svg>
              </button>
              <button
                class="cn-icon-btn"
                @click="openEdit(n)"
                title="Редактировать"
              >
                <svg width="12" height="12" viewBox="0 0 16 16" fill="none">
                  <path
                    d="M2 14 L5 13 L13 5 L11 3 L3 11 L2 14 Z"
                    stroke="currentColor"
                    stroke-width="1.5"
                    stroke-linejoin="round"
                  />
                </svg>
              </button>
              <button
                class="cn-icon-btn cn-icon-btn-danger"
                @click="removeNote(n)"
                title="Удалить"
              >
                <svg width="12" height="12" viewBox="0 0 16 16" fill="none">
                  <path
                    d="M3 5 H13 M5 5 V13 H11 V5 M6 5 V3 H10 V5"
                    stroke="currentColor"
                    stroke-width="1.5"
                    stroke-linejoin="round"
                  />
                </svg>
              </button>
            </div>
          </div>
          <div v-if="n.title" class="cn-card-title">{{ n.title }}</div>
          <div
            class="cn-card-body"
            :class="{ 'cn-card-body-collapsed': !expanded.has(n.id) }"
          >
            {{ n.body }}
          </div>

          <!-- Checklist (interactive) -->
          <div v-if="checklistStats(n)" class="cn-card-cl" @click.stop>
            <div class="cn-card-cl-head">
              <span class="cn-card-cl-track">
                <span class="cn-card-cl-fill" :style="{ width: checklistStats(n)!.pct + '%' }"></span>
              </span>
              <span class="cn-card-cl-num">{{ checklistStats(n)!.done }}/{{ checklistStats(n)!.total }}</span>
            </div>
            <div class="cn-card-cl-items">
              <div
                v-for="ci in sortedChecklist(n)"
                :key="ci.id"
                class="cn-card-cl-item"
                :class="{ 'cn-card-cl-item-done': ci.is_done }"
              >
                <button
                  type="button"
                  class="cn-cl-check cn-cl-check-card"
                  :class="{ 'cn-cl-check-on': ci.is_done }"
                  :disabled="togglingItem.has(ci.id)"
                  @click="toggleChecklistItem(n, ci)"
                >
                  <svg v-if="ci.is_done" width="10" height="10" viewBox="0 0 16 16" fill="none">
                    <path d="M3 8.5 L6.5 12 L13 4" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round" />
                  </svg>
                </button>
                <span class="cn-card-cl-text">{{ ci.text }}</span>
                <span v-if="ci.assignee_name" class="cn-card-cl-av" :title="'Ответственный: ' + ci.assignee_name">{{ avInitials(ci.assignee_name) }}</span>
              </div>
            </div>
          </div>

          <div v-if="n.tags && n.tags.length" class="cn-card-tags">
            <span v-for="t in n.tags" :key="t" class="cn-card-tag">#{{ t }}</span>
          </div>
          <div class="cn-card-foot">
            <span class="cn-card-time">{{ formatTimeAgo(n.event_date || n.created_at) }}</span>
            <span v-if="n.assignee_name" class="cn-card-assignee" :title="'Ответственный: ' + n.assignee_name">
              <span class="cn-card-assignee-av">{{ avInitials(n.assignee_name) }}</span>
              <span class="cn-card-assignee-name">{{ n.assignee_name }}</span>
            </span>
            <span
              v-if="n.kind === 'task' || n.kind === 'risk'"
              class="cn-resolve-pill"
              :class="{ 'cn-resolve-pill-active': n.is_resolved }"
              @click.stop="toggleResolve(n)"
            >
              {{ n.is_resolved ? "✓ Закрыто" : "○ Открыто" }}
            </span>
          </div>
        </div>
      </div>
    </div>

    <!-- ============================================================ -->
    <!-- TIMELINE -->
    <!-- ============================================================ -->
    <div v-if="!loading && timelineGroups.length" class="cn-timeline">
      <div
        v-for="grp in timelineGroups"
        :key="grp.key"
        class="cn-timeline-group"
      >
        <div class="cn-group-header">
          <span class="cn-group-label">{{ formatDateGroup(grp) }}</span>
          <span
            v-if="grp.holiday"
            class="cn-holiday-pill"
            :style="{
              '--h-color': HOLIDAY_KIND_COLORS[grp.holiday.kind],
            }"
            :title="grp.holiday.description || ''"
          >
            <span class="cn-holiday-dot"></span>
            {{ grp.holiday.title_ru }}
            <span v-if="grp.holiday.is_dayoff" class="cn-holiday-flag">нерабочий</span>
          </span>
        </div>

        <div class="cn-group-items">
          <template v-for="(item, i) in grp.items" :key="item.sortKey">
            <!-- Holiday synthetic item -->
            <div
              v-if="item.type === 'holiday' && item.holiday"
              class="cn-holiday-item"
              :style="{
                '--h-color': HOLIDAY_KIND_COLORS[item.holiday.kind],
                animationDelay: `${i * 60}ms`,
              }"
            >
              <div class="cn-holiday-item-icon">
                <svg width="12" height="12" viewBox="0 0 16 16" fill="none">
                  <path
                    d="M8 1 L10 6 L15 6.5 L11 10 L12 15 L8 12 L4 15 L5 10 L1 6.5 L6 6 Z"
                    fill="currentColor"
                  />
                </svg>
              </div>
              <div class="cn-holiday-item-text">
                <div class="cn-holiday-item-title">{{ item.holiday.title_ru }}</div>
                <div class="cn-holiday-item-meta">
                  {{ HOLIDAY_KIND_LABELS[item.holiday.kind] }}
                  <span v-if="item.holiday.is_dayoff"> · нерабочий</span>
                  <span v-if="item.holiday.transferred_from">
                    · перенос с {{ formatDateShort(item.holiday.transferred_from) }}
                  </span>
                </div>
              </div>
            </div>

            <!-- Note card -->
            <div
              v-else-if="item.type === 'note' && item.note"
              class="cn-card"
              :class="{ 'cn-card-resolved': item.note.is_resolved }"
              :data-kind="item.note.kind"
              :style="{
                '--kind-color': NOTE_KIND_COLORS[item.note.kind],
                animationDelay: `${i * 60}ms`,
              }"
              @click="item.note && toggleExpand(item.note.id)"
            >
              <div class="cn-card-head">
                <div class="cn-card-kind">
                  <svg
                    width="14"
                    height="14"
                    viewBox="0 0 16 16"
                    fill="none"
                    v-html="NOTE_KIND_ICONS[item.note.kind]"
                  />
                  <span>{{ NOTE_KIND_LABELS[item.note.kind] }}</span>
                </div>
                <div class="cn-card-actions" @click.stop>
                  <button
                    class="cn-icon-btn"
                    @click="item.note && togglePin(item.note)"
                    :title="item.note.is_pinned ? 'Открепить' : 'Закрепить'"
                  >
                    <svg width="12" height="12" viewBox="0 0 16 16" fill="none">
                      <path
                        d="M5 2 L11 2 L11 8 L13 10 L3 10 L5 8 Z M8 10 V14"
                        stroke="currentColor"
                        stroke-width="1.5"
                        stroke-linejoin="round"
                      />
                    </svg>
                  </button>
                  <button
                    class="cn-icon-btn"
                    @click="item.note && openEdit(item.note)"
                    title="Редактировать"
                  >
                    <svg width="12" height="12" viewBox="0 0 16 16" fill="none">
                      <path
                        d="M2 14 L5 13 L13 5 L11 3 L3 11 L2 14 Z"
                        stroke="currentColor"
                        stroke-width="1.5"
                        stroke-linejoin="round"
                      />
                    </svg>
                  </button>
                  <button
                    class="cn-icon-btn cn-icon-btn-danger"
                    @click="item.note && removeNote(item.note)"
                    title="Удалить"
                  >
                    <svg width="12" height="12" viewBox="0 0 16 16" fill="none">
                      <path
                        d="M3 5 H13 M5 5 V13 H11 V5 M6 5 V3 H10 V5"
                        stroke="currentColor"
                        stroke-width="1.5"
                        stroke-linejoin="round"
                      />
                    </svg>
                  </button>
                </div>
              </div>
              <div v-if="item.note.title" class="cn-card-title">
                {{ item.note.title }}
              </div>
              <div
                class="cn-card-body"
                :class="{ 'cn-card-body-collapsed': !expanded.has(item.note.id) }"
              >
                {{ item.note.body }}
              </div>

              <!-- Due date progress bar (kind=task) -->
              <div
                v-if="dueProgress(item.note)"
                class="cn-due-bar"
                :data-state="dueProgress(item.note)?.state"
              >
                <div
                  class="cn-due-bar-fill"
                  :style="{ width: `${dueProgress(item.note)?.pct}%` }"
                ></div>
                <div class="cn-due-bar-label">
                  <template v-if="dueProgress(item.note)?.state === 'overdue'">
                    Просрочено на {{ Math.abs(dueProgress(item.note)!.daysLeft) }} дн.
                  </template>
                  <template v-else-if="dueProgress(item.note)?.daysLeft === 0">
                    Сегодня дедлайн
                  </template>
                  <template v-else>
                    Осталось {{ dueProgress(item.note)?.daysLeft }} дн.
                  </template>
                </div>
              </div>

              <!-- Holiday warning if due_date conflicts -->
              <div
                v-if="item.note.due_date && isHolidayDayoff(item.note.due_date)"
                class="cn-due-holiday-warn"
              >
                <svg width="11" height="11" viewBox="0 0 16 16" fill="none">
                  <path
                    d="M8 1 L15 14 L1 14 Z M8 6 V10 M8 12 V12.5"
                    stroke="currentColor"
                    stroke-width="1.5"
                    stroke-linejoin="round"
                    stroke-linecap="round"
                  />
                </svg>
                Дедлайн попадает на {{ isHolidayDayoff(item.note.due_date)?.title_ru }} (нерабочий)
              </div>

              <!-- Checklist (interactive) -->
              <div v-if="checklistStats(item.note)" class="cn-card-cl" @click.stop>
                <div class="cn-card-cl-head">
                  <span class="cn-card-cl-track">
                    <span class="cn-card-cl-fill" :style="{ width: checklistStats(item.note)!.pct + '%' }"></span>
                  </span>
                  <span class="cn-card-cl-num">{{ checklistStats(item.note)!.done }}/{{ checklistStats(item.note)!.total }}</span>
                </div>
                <div class="cn-card-cl-items">
                  <div
                    v-for="ci in sortedChecklist(item.note)"
                    :key="ci.id"
                    class="cn-card-cl-item"
                    :class="{ 'cn-card-cl-item-done': ci.is_done }"
                  >
                    <button
                      type="button"
                      class="cn-cl-check cn-cl-check-card"
                      :class="{ 'cn-cl-check-on': ci.is_done }"
                      :disabled="togglingItem.has(ci.id)"
                      @click="toggleChecklistItem(item.note, ci)"
                    >
                      <svg v-if="ci.is_done" width="10" height="10" viewBox="0 0 16 16" fill="none">
                        <path d="M3 8.5 L6.5 12 L13 4" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round" />
                      </svg>
                    </button>
                    <span class="cn-card-cl-text">{{ ci.text }}</span>
                    <span v-if="ci.assignee_name" class="cn-card-cl-av" :title="'Ответственный: ' + ci.assignee_name">{{ avInitials(ci.assignee_name) }}</span>
                  </div>
                </div>
              </div>

              <!-- Tags -->
              <div v-if="item.note.tags && item.note.tags.length" class="cn-card-tags">
                <span v-for="t in item.note.tags" :key="t" class="cn-card-tag">
                  #{{ t }}
                </span>
              </div>

              <!-- Links -->
              <div v-if="item.note.links && item.note.links.length" class="cn-card-links">
                <span
                  v-for="l in item.note.links"
                  :key="(l.entity_type || '') + (l.entity_label || l.entity_key)"
                  class="cn-card-link"
                  :title="LINK_ENTITY_LABELS[l.entity_type as LinkEntityType] || l.entity_type"
                >
                  <span class="cn-card-link-type">{{ LINK_ENTITY_LABELS[l.entity_type as LinkEntityType] || l.entity_type }}</span>
                  <span class="cn-card-link-label">{{ l.entity_label || l.entity_key }}</span>
                </span>
              </div>

              <!-- Foot -->
              <div class="cn-card-foot">
                <span class="cn-card-time">{{ formatTimeAgo(item.note.event_date || item.note.created_at) }}</span>
                <span v-if="item.note.assignee_name" class="cn-card-assignee" :title="'Ответственный: ' + item.note.assignee_name">
                  <span class="cn-card-assignee-av">{{ avInitials(item.note.assignee_name) }}</span>
                  <span class="cn-card-assignee-name">{{ item.note.assignee_name }}</span>
                </span>
                <span
                  v-if="item.note.kind === 'task' || item.note.kind === 'risk'"
                  class="cn-resolve-pill"
                  :class="{ 'cn-resolve-pill-active': item.note.is_resolved }"
                  @click.stop="item.note && toggleResolve(item.note)"
                >
                  {{ item.note.is_resolved ? "✓ Закрыто" : "○ Открыто" }}
                </span>
              </div>
            </div>
          </template>
        </div>
      </div>
    </div>

    <!-- ============================================================ -->
    <!-- EMPTY STATE -->
    <!-- ============================================================ -->
    <div v-if="isEmpty" class="cn-empty">
      <div class="cn-empty-illust">
        <svg width="64" height="64" viewBox="0 0 64 64" fill="none">
          <rect
            x="10"
            y="14"
            width="44"
            height="40"
            rx="3"
            stroke="currentColor"
            stroke-width="1.5"
            opacity="0.4"
          />
          <path
            d="M10 22 H54"
            stroke="currentColor"
            stroke-width="1.5"
            opacity="0.4"
          />
          <path
            d="M18 8 V18 M46 8 V18"
            stroke="currentColor"
            stroke-width="1.5"
            stroke-linecap="round"
          />
          <path
            d="M18 32 H40 M18 38 H46 M18 44 H32"
            stroke="currentColor"
            stroke-width="1.5"
            stroke-linecap="round"
            opacity="0.6"
          />
        </svg>
      </div>
      <div class="cn-empty-title">Журнал пуст</div>
      <div class="cn-empty-desc">
        Фиксируйте события, решения, задачи, риски и наблюдения по компании в одном месте.
      </div>
      <button class="cn-btn-primary cn-empty-cta" @click="openCreate('event')">
        Создать первую запись
      </button>
    </div>

    <!-- ============================================================ -->
    <!-- MODAL -->
    <!-- ============================================================ -->
    <Teleport to="body">
      <Transition name="cn-modal">
        <div
          v-if="modalOpen"
          class="cn-modal-backdrop"
          @click.self="closeModal"
        >
          <div class="cn-modal" @click.stop>
            <div class="cn-modal-head">
              <h3>
                {{ modalMode === "create" ? "Новая запись" : "Редактирование записи" }}
              </h3>
              <button class="cn-icon-btn" @click="closeModal" title="Закрыть">
                <svg width="14" height="14" viewBox="0 0 16 16" fill="none">
                  <path
                    d="M3 3 L13 13 M13 3 L3 13"
                    stroke="currentColor"
                    stroke-width="1.6"
                    stroke-linecap="round"
                  />
                </svg>
              </button>
            </div>

            <div class="cn-modal-body">
              <!-- Kind chips -->
              <div class="cn-field">
                <label class="cn-field-label">Тип записи</label>
                <div class="cn-kind-chips">
                  <button
                    v-for="k in NOTE_KINDS"
                    :key="k"
                    type="button"
                    class="cn-kind-chip"
                    :class="{ 'cn-kind-chip-active': form.kind === k }"
                    :style="{ '--chip-color': NOTE_KIND_COLORS[k] }"
                    @click="form.kind = k"
                  >
                    <svg
                      width="14"
                      height="14"
                      viewBox="0 0 16 16"
                      fill="none"
                      v-html="NOTE_KIND_ICONS[k]"
                    />
                    <span>{{ NOTE_KIND_LABELS[k] }}</span>
                  </button>
                </div>
              </div>

              <!-- Title -->
              <div class="cn-field">
                <label class="cn-field-label">Заголовок</label>
                <input
                  v-model="form.title"
                  type="text"
                  class="cn-input"
                  placeholder="Краткое описание (опционально)"
                  maxlength="255"
                />
              </div>

              <!-- Body -->
              <div class="cn-field">
                <label class="cn-field-label">Содержание <span class="cn-req">*</span></label>
                <textarea
                  v-model="form.body"
                  class="cn-textarea"
                  rows="5"
                  placeholder="Что произошло, что решено, что нужно сделать..."
                ></textarea>
              </div>

              <!-- Responsible (note-level) -->
              <div class="cn-field">
                <label class="cn-field-label">Ответственный</label>
                <NoteAssigneePicker
                  :id="form.assignee_id"
                  :name="form.assignee_name"
                  placeholder="Назначить ответственного"
                  @update:id="form.assignee_id = $event"
                  @update:name="form.assignee_name = $event"
                />
              </div>

              <!-- Checklist -->
              <div class="cn-field">
                <label class="cn-field-label cn-cl-label">
                  <span>Чек-лист</span>
                  <span v-if="form.checklist.length" class="cn-cl-progress-mini">
                    <span class="cn-cl-progress-track">
                      <span class="cn-cl-progress-fill" :style="{ width: formChecklistPct + '%' }"></span>
                    </span>
                    <span class="cn-cl-progress-num">{{ formChecklistDone }}/{{ form.checklist.length }}</span>
                  </span>
                </label>

                <TransitionGroup name="cn-cl" tag="div" class="cn-cl-list">
                  <div
                    v-for="(ci, idx) in form.checklist"
                    :key="ci.id || 'new_' + idx"
                    class="cn-cl-row"
                    :class="{ 'cn-cl-row-done': ci.is_done }"
                  >
                    <button
                      type="button"
                      class="cn-cl-check"
                      :class="{ 'cn-cl-check-on': ci.is_done }"
                      @click="ci.is_done = !ci.is_done"
                      :title="ci.is_done ? 'Снять отметку' : 'Отметить выполненным'"
                    >
                      <svg v-if="ci.is_done" width="11" height="11" viewBox="0 0 16 16" fill="none">
                        <path d="M3 8.5 L6.5 12 L13 4" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" />
                      </svg>
                    </button>
                    <input
                      v-model="ci.text"
                      type="text"
                      class="cn-cl-text"
                      placeholder="Что нужно сделать…"
                      @keydown.enter.prevent="addChecklistItem"
                    />
                    <NoteAssigneePicker
                      size="sm"
                      :id="ci.assignee_id"
                      :name="ci.assignee_name"
                      placeholder="Кто"
                      @update:id="ci.assignee_id = $event"
                      @update:name="ci.assignee_name = $event"
                    />
                    <div class="cn-cl-row-actions">
                      <button type="button" class="cn-cl-mini" :disabled="idx === 0" @click="moveChecklistItem(idx, -1)" title="Выше">
                        <svg width="11" height="11" viewBox="0 0 16 16" fill="none"><path d="M4 10 L8 6 L12 10" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" /></svg>
                      </button>
                      <button type="button" class="cn-cl-mini" :disabled="idx === form.checklist.length - 1" @click="moveChecklistItem(idx, 1)" title="Ниже">
                        <svg width="11" height="11" viewBox="0 0 16 16" fill="none"><path d="M4 6 L8 10 L12 6" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" /></svg>
                      </button>
                      <button type="button" class="cn-cl-mini cn-cl-mini-danger" @click="removeChecklistItem(idx)" title="Удалить пункт">
                        <svg width="11" height="11" viewBox="0 0 16 16" fill="none"><path d="M3 3 L13 13 M13 3 L3 13" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" /></svg>
                      </button>
                    </div>
                  </div>
                </TransitionGroup>

                <div class="cn-cl-add">
                  <span class="cn-cl-add-icon">
                    <svg width="12" height="12" viewBox="0 0 12 12" fill="none"><path d="M6 1 V11 M1 6 H11" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" /></svg>
                  </span>
                  <input
                    v-model="form.checklistInput"
                    type="text"
                    class="cn-cl-add-input"
                    placeholder="Добавить пункт и Enter"
                    @keydown.enter.prevent="addChecklistItem"
                  />
                  <button
                    v-if="form.checklistInput.trim()"
                    type="button"
                    class="cn-cl-add-btn"
                    @click="addChecklistItem"
                  >
                    Добавить
                  </button>
                </div>
              </div>

              <!-- Tags -->
              <div class="cn-field">
                <label class="cn-field-label">Теги</label>
                <div class="cn-tags-editor">
                  <span
                    v-for="t in form.tags"
                    :key="t"
                    class="cn-card-tag cn-card-tag-removable"
                  >
                    #{{ t }}
                    <button
                      type="button"
                      class="cn-tag-remove"
                      @click="removeTag(t)"
                    >
                      ×
                    </button>
                  </span>
                  <input
                    v-model="form.tagInput"
                    type="text"
                    class="cn-tag-input"
                    placeholder="Добавить тег и Enter"
                    @keydown.enter.prevent="addTagFromInput"
                    @keydown.,.prevent="addTagFromInput"
                    @blur="addTagFromInput"
                  />
                </div>
                <div v-if="tagCounts.length" class="cn-tag-suggest">
                  <button
                    v-for="tc in tagCounts.slice(0, 8)"
                    :key="'sg_' + tc.tag"
                    type="button"
                    class="cn-tag-suggest-item"
                    :class="{ 'cn-tag-suggest-disabled': form.tags.includes(tc.tag) }"
                    :disabled="form.tags.includes(tc.tag)"
                    @click="form.tags.push(tc.tag)"
                  >
                    #{{ tc.tag }}
                  </button>
                </div>
              </div>

              <!-- Dates row -->
              <div class="cn-field-row">
                <div class="cn-field">
                  <label class="cn-field-label">
                    {{ form.kind === "task" ? "Создано" : "Дата события" }}
                  </label>
                  <input
                    v-model="form.event_date"
                    type="date"
                    class="cn-input"
                  />
                  <div
                    v-if="eventConflict?.conflicts"
                    class="cn-date-warn"
                  >
                    <svg width="11" height="11" viewBox="0 0 16 16" fill="none">
                      <path
                        d="M8 1 L15 14 L1 14 Z M8 6 V10 M8 12 V12.5"
                        stroke="currentColor"
                        stroke-width="1.5"
                        stroke-linejoin="round"
                        stroke-linecap="round"
                      />
                    </svg>
                    {{ eventConflict.holiday?.title_ru }} -- нерабочий день
                    <button
                      type="button"
                      class="cn-date-warn-cta"
                      @click="applyEventSuggestion"
                    >
                      Сдвинуть на {{ formatDateShort(toIsoDate(eventConflict.suggested!)) }}
                    </button>
                  </div>
                </div>
                <div v-if="form.kind === 'task'" class="cn-field">
                  <label class="cn-field-label">Дедлайн</label>
                  <input
                    v-model="form.due_date"
                    type="date"
                    class="cn-input"
                  />
                  <div
                    v-if="dueConflict?.conflicts"
                    class="cn-date-warn"
                  >
                    <svg width="11" height="11" viewBox="0 0 16 16" fill="none">
                      <path
                        d="M8 1 L15 14 L1 14 Z M8 6 V10 M8 12 V12.5"
                        stroke="currentColor"
                        stroke-width="1.5"
                        stroke-linejoin="round"
                        stroke-linecap="round"
                      />
                    </svg>
                    {{ dueConflict.holiday?.title_ru }} -- нерабочий день
                    <button
                      type="button"
                      class="cn-date-warn-cta"
                      @click="applyDueSuggestion"
                    >
                      Сдвинуть на {{ formatDateShort(toIsoDate(dueConflict.suggested!)) }}
                    </button>
                  </div>
                </div>
              </div>

              <!-- Pinned -->
              <div class="cn-field">
                <label class="cn-toggle">
                  <input v-model="form.is_pinned" type="checkbox" />
                  <span>Закрепить вверху списка</span>
                </label>
              </div>

              <!-- Entity links -->
              <div class="cn-field">
                <label class="cn-field-label">Связанные сущности</label>
                <div v-if="form.links.length" class="cn-links-list">
                  <div
                    v-for="(l, idx) in form.links"
                    :key="idx"
                    class="cn-link-item"
                  >
                    <span class="cn-link-item-type">
                      {{ LINK_ENTITY_LABELS[l.entity_type as LinkEntityType] || l.entity_type }}
                    </span>
                    <span class="cn-link-item-label">{{ l.entity_label }}</span>
                    <button
                      type="button"
                      class="cn-link-remove"
                      @click="removeLink(idx)"
                    >
                      ×
                    </button>
                  </div>
                </div>
                <div class="cn-link-editor">
                  <select
                    v-model="form.linkType"
                    class="cn-input cn-link-type-select"
                  >
                    <option
                      v-for="(label, key) in LINK_ENTITY_LABELS"
                      :key="key"
                      :value="key"
                    >
                      {{ label }}
                    </option>
                  </select>
                  <input
                    v-model="form.linkLabel"
                    type="text"
                    class="cn-input"
                    placeholder="Название (e.g. Проект ERP-2026)"
                  />
                  <button
                    type="button"
                    class="cn-btn-secondary"
                    @click="addLink"
                  >
                    +
                  </button>
                </div>
              </div>

              <!-- Error -->
              <div v-if="modalError" class="cn-error">{{ modalError }}</div>
            </div>

            <div class="cn-modal-foot">
              <button class="cn-btn-secondary" @click="closeModal">
                Отмена
              </button>
              <button
                class="cn-btn-primary"
                :disabled="modalSubmitting || !form.body.trim()"
                @click="submit"
              >
                <span v-if="modalSubmitting">Сохраняем...</span>
                <span v-else-if="modalMode === 'create'">Создать</span>
                <span v-else>Сохранить</span>
              </button>
            </div>
          </div>
        </div>
      </Transition>
    </Teleport>
  </div>
</template>

<style scoped>
/* ============================================================ */
/* ROOT */
/* ============================================================ */
.cn-root {
  color: var(--t1, #1e2a4a);
  padding: 4px 0 24px;
}

/* ============================================================ */
/* TOP BAR */
/* ============================================================ */
.cn-top {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  margin-bottom: 14px;
}
.cn-top-left {
  flex: 1;
  min-width: 0;
}
.cn-search {
  position: relative;
  display: flex;
  align-items: center;
  width: 100%;
  max-width: 480px;
  height: 36px;
  background: var(--bg1, #ffffff);
  border: 1px solid rgba(30, 42, 74, 0.08);
  border-radius: 8px;
  padding: 0 36px 0 34px;
  transition: all 0.18s ease;
}
.cn-search:focus-within {
  border-color: #7f77dd;
  box-shadow: 0 0 0 3px rgba(127, 119, 221, 0.1);
}
.cn-search-icon {
  position: absolute;
  left: 12px;
  color: rgba(30, 42, 74, 0.4);
}
.cn-search input {
  flex: 1;
  border: none;
  outline: none;
  background: transparent;
  font-size: 13px;
  color: var(--t1, #1e2a4a);
}
.cn-search input::placeholder {
  color: rgba(30, 42, 74, 0.35);
}
.cn-search-clear {
  position: absolute;
  right: 8px;
  width: 22px;
  height: 22px;
  border: none;
  border-radius: 4px;
  background: rgba(30, 42, 74, 0.06);
  color: rgba(30, 42, 74, 0.6);
  cursor: pointer;
  font-size: 16px;
  line-height: 1;
}
.cn-search-clear:hover {
  background: rgba(30, 42, 74, 0.12);
}

.cn-btn-primary {
  display: inline-flex;
  align-items: center;
  gap: 7px;
  height: 36px;
  padding: 0 16px;
  border: none;
  border-radius: 8px;
  background: linear-gradient(135deg, #7f77dd 0%, #6b62cc 100%);
  color: #ffffff;
  font-size: 12.5px;
  font-weight: 500;
  letter-spacing: -0.005em;
  cursor: pointer;
  transition: all 0.2s var(--ease-standard);
  box-shadow: 0 2px 6px rgba(127, 119, 221, 0.25);
}
.cn-btn-primary:hover:not(:disabled) {
  transform: translateY(-1px);
  box-shadow: 0 4px 14px rgba(127, 119, 221, 0.35);
}
.cn-btn-primary:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}
.cn-btn-secondary {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  height: 36px;
  padding: 0 14px;
  border: 1px solid rgba(30, 42, 74, 0.12);
  border-radius: 8px;
  background: var(--bg1, #ffffff);
  color: var(--t1, #1e2a4a);
  font-size: 12.5px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.18s ease;
}
.cn-btn-secondary:hover {
  border-color: #7f77dd;
  color: #7f77dd;
}

/* ============================================================ */
/* FILTERS / CHIPS */
/* ============================================================ */
.cn-filters {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  margin-bottom: 14px;
  flex-wrap: wrap;
}
.cn-chips {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}
.cn-chip {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  height: 28px;
  padding: 0 11px;
  border: 1px solid rgba(30, 42, 74, 0.1);
  border-radius: 11px;
  background: var(--bg1, #ffffff);
  color: rgba(30, 42, 74, 0.65);
  font-size: 11.5px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.22s var(--ease-standard);
  --chip-color: #7f77dd;
}
.cn-chip:hover {
  border-color: var(--chip-color);
  color: var(--chip-color);
  transform: translateY(-1px);
}
.cn-chip-active {
  background: var(--chip-color);
  border-color: var(--chip-color);
  color: #ffffff;
  box-shadow: 0 2px 8px color-mix(in srgb, var(--chip-color) 35%, transparent);
  animation: cnChipPulse 0.4s var(--ease-standard);
}
@keyframes cnChipPulse {
  0% {
    transform: scale(1);
  }
  40% {
    transform: scale(1.06);
  }
  100% {
    transform: scale(1);
  }
}
.cn-chip-icon {
  flex-shrink: 0;
}
.cn-chip-count {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 18px;
  height: 16px;
  padding: 0 5px;
  border-radius: 8px;
  background: rgba(255, 255, 255, 0.25);
  font-size: 10px;
  font-weight: 600;
}
.cn-chip:not(.cn-chip-active) .cn-chip-count {
  background: rgba(30, 42, 74, 0.06);
  color: rgba(30, 42, 74, 0.55);
}
.cn-toggles {
  display: flex;
  gap: 14px;
  align-items: center;
}
.cn-toggle {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  color: rgba(30, 42, 74, 0.7);
  cursor: pointer;
  user-select: none;
}
.cn-toggle input {
  margin: 0;
  cursor: pointer;
}

/* ============================================================ */
/* TAG CLOUD */
/* ============================================================ */
.cn-tag-cloud {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 6px;
  margin-bottom: 16px;
  padding: 10px 12px;
  background: rgba(127, 119, 221, 0.04);
  border-radius: 8px;
}
.cn-tag-cloud-label {
  font-size: 10px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  color: rgba(30, 42, 74, 0.5);
  margin-right: 4px;
}
.cn-tag {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  height: 22px;
  padding: 0 8px;
  border: 1px solid transparent;
  border-radius: 11px;
  background: var(--bg1, #ffffff);
  color: rgba(30, 42, 74, 0.7);
  font-size: 11px;
  cursor: pointer;
  transition: all 0.18s;
}
.cn-tag:hover {
  border-color: #7f77dd;
  color: #7f77dd;
}
.cn-tag-active {
  background: #7f77dd;
  color: #ffffff;
  border-color: #7f77dd;
}
.cn-tag-count {
  font-size: 9.5px;
  font-weight: 600;
  opacity: 0.7;
}

/* ============================================================ */
/* CALENDAR WRAPPER */
/* ============================================================ */
.cn-calendar-wrap {
  margin-bottom: 14px;
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.cn-calendar-filter-banner {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 12px;
  background: rgba(127, 119, 221, 0.08);
  border: 0.5px solid rgba(127, 119, 221, 0.30);
  border-radius: 8px;
  font-size: 12px;
  color: var(--p-deep);
}
.cn-calendar-filter-banner svg {
  flex-shrink: 0;
}
.cn-calendar-filter-banner b {
  font-weight: 600;
  font-variant-numeric: tabular-nums;
}
.cn-calendar-filter-clear {
  margin-left: auto;
  background: transparent;
  border: 1px solid rgba(127, 119, 221, 0.30);
  color: var(--p-deep);
  font-size: 11px;
  font-weight: 500;
  padding: 3px 9px;
  border-radius: 6px;
  cursor: pointer;
  transition: background 0.12s;
}
.cn-calendar-filter-clear:hover {
  background: rgba(127, 119, 221, 0.18);
}

/* ============================================================ */
/* HOLIDAYS WIDGET */
/* ============================================================ */
.cn-holidays-widget {
  margin-bottom: 18px;
  padding: 14px 16px;
  background: linear-gradient(
    135deg,
    rgba(29, 158, 117, 0.06) 0%,
    rgba(239, 159, 39, 0.05) 100%
  );
  border: 1px solid rgba(29, 158, 117, 0.12);
  border-radius: 10px;
  animation: cnFadeUp 0.4s var(--ease-standard);
}
@keyframes cnFadeUp {
  from {
    opacity: 0;
    transform: translateY(8px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}
.cn-hw-title {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 10px;
  font-size: 10px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.07em;
  color: rgba(30, 42, 74, 0.7);
}
.cn-hw-items {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
}
.cn-hw-item {
  display: flex;
  align-items: center;
  gap: 11px;
  padding: 8px 12px 8px 9px;
  background: var(--bg1, #ffffff);
  border-radius: 8px;
  box-shadow: 0 1px 3px rgba(15, 23, 60, 0.04);
  /* top-stripe via .cn-hw-item::before */
  position: relative;
  overflow: hidden;
  flex: 1 1 240px;
  min-width: 240px;
  transition: all 0.2s;
}
.cn-hw-item:hover {
  transform: translateY(-1px);
  box-shadow: 0 4px 10px rgba(15, 23, 60, 0.08);
}
.cn-hw-date {
  font-size: 12px;
  font-weight: 600;
  color: var(--h-color);
  flex-shrink: 0;
  min-width: 50px;
}
.cn-hw-info {
  flex: 1;
  min-width: 0;
}
.cn-hw-title-text {
  font-size: 12.5px;
  font-weight: 500;
  color: var(--t1, #1e2a4a);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.cn-hw-meta {
  display: flex;
  gap: 8px;
  margin-top: 2px;
  font-size: 10px;
  color: rgba(30, 42, 74, 0.55);
}
.cn-hw-dayoff {
  color: var(--h-color);
  font-weight: 500;
}
.cn-hw-countdown {
  margin-left: auto;
}

/* ============================================================ */
/* SECTION LABEL */
/* ============================================================ */
.cn-section-label {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: 10px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.07em;
  color: rgba(30, 42, 74, 0.55);
  margin-bottom: 10px;
}

/* ============================================================ */
/* PINNED SECTION */
/* ============================================================ */
.cn-pinned-section {
  margin-bottom: 22px;
}
.cn-cards-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(320px, 1fr));
  gap: 10px;
}

/* ============================================================ */
/* TIMELINE */
/* ============================================================ */
.cn-timeline {
  display: flex;
  flex-direction: column;
  gap: 18px;
}
.cn-timeline-group {
  position: relative;
}
.cn-group-header {
  position: sticky;
  top: 0;
  z-index: 4;
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 8px 0 8px 0;
  margin-bottom: 8px;
  background: linear-gradient(
    180deg,
    #f5f6f8 0%,
    rgba(245, 246, 248, 0.95) 80%,
    rgba(245, 246, 248, 0)
  );
  -webkit-backdrop-filter: blur(4px);
  backdrop-filter: blur(4px);
}
.cn-group-label {
  font-size: 11px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.07em;
  color: rgba(30, 42, 74, 0.6);
}
.cn-holiday-pill {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  height: 22px;
  padding: 0 9px 0 6px;
  border-radius: 11px;
  background: color-mix(in srgb, var(--h-color) 12%, transparent);
  color: var(--h-color);
  font-size: 10.5px;
  font-weight: 500;
  --h-color: var(--green);
}
.cn-holiday-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--h-color);
}
.cn-holiday-flag {
  font-size: 9.5px;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  opacity: 0.7;
  border-left: 1px solid currentColor;
  padding-left: 6px;
  margin-left: 2px;
}
.cn-group-items {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

/* ============================================================ */
/* HOLIDAY synthetic item in timeline */
/* ============================================================ */
.cn-holiday-item {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 12px 10px 11px;
  background: color-mix(in srgb, var(--h-color) 4%, #ffffff);
  border: 1px dashed color-mix(in srgb, var(--h-color) 35%, transparent);
  border-radius: 8px;
  /* top-stripe via .cn-holiday-item::before */
  position: relative;
  overflow: hidden;
  --h-color: var(--green);
  animation: cnFadeUp 0.4s both;
}
.cn-holiday-item-icon {
  color: var(--h-color);
  flex-shrink: 0;
}
.cn-holiday-item-text {
  flex: 1;
  min-width: 0;
}
.cn-holiday-item-title {
  font-size: 12.5px;
  font-weight: 500;
  color: var(--t1, #1e2a4a);
}
.cn-holiday-item-meta {
  font-size: 10.5px;
  color: rgba(30, 42, 74, 0.55);
  margin-top: 2px;
}

/* ============================================================ */
/* CARD */
/* ============================================================ */
.cn-card {
  position: relative;
  background: var(--bg1, #ffffff);
  border: 1px solid rgba(30, 42, 74, 0.06);
  border-radius: 8px;
  /* top-stripe via .cn-card::before — colour from --kind-color */
  overflow: hidden;
  padding: 12px 14px;
  cursor: pointer;
  transition:
    transform 0.22s var(--ease-standard),
    box-shadow 0.22s ease,
    border-color 0.18s ease;
  --kind-color: var(--blue);
  animation: cnFadeUp 0.4s both;
}
.cn-card:hover {
  transform: translateY(-1px);
  box-shadow:
    0 6px 16px color-mix(in srgb, var(--kind-color) 14%, transparent),
    0 1px 4px rgba(15, 23, 60, 0.06);
}
.cn-card-pinned {
  background: linear-gradient(
    135deg,
    color-mix(in srgb, var(--kind-color) 4%, #ffffff) 0%,
    #ffffff 60%
  );
}
.cn-card-resolved {
  opacity: 0.6;
}
.cn-card-resolved .cn-card-title {
  text-decoration: line-through;
  text-decoration-color: rgba(30, 42, 74, 0.5);
  transition: text-decoration-color 0.4s;
}
.cn-card-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  margin-bottom: 6px;
}
.cn-card-kind {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: 10.5px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  color: var(--kind-color);
}
.cn-card-actions {
  display: flex;
  gap: 4px;
  opacity: 0;
  transition: opacity 0.18s;
}
.cn-card:hover .cn-card-actions {
  opacity: 1;
}
.cn-icon-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 24px;
  height: 24px;
  border: none;
  border-radius: 5px;
  background: transparent;
  color: rgba(30, 42, 74, 0.55);
  cursor: pointer;
  transition: all 0.16s;
}
.cn-icon-btn:hover {
  background: rgba(127, 119, 221, 0.1);
  color: #7f77dd;
}
.cn-icon-btn-danger:hover {
  background: rgba(226, 75, 74, 0.1);
  color: var(--sev-high);
}
.cn-card-title {
  font-size: 13.5px;
  font-weight: 500;
  letter-spacing: -0.005em;
  color: var(--t1, #1e2a4a);
  margin-bottom: 4px;
}
.cn-card-body {
  font-size: 12.5px;
  line-height: 1.5;
  color: rgba(30, 42, 74, 0.78);
  white-space: pre-wrap;
  word-break: break-word;
}
.cn-card-body-collapsed {
  display: -webkit-box;
  -webkit-line-clamp: 3;
  -webkit-box-orient: vertical;
  overflow: hidden;
}
.cn-card-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 5px;
  margin-top: 8px;
}
.cn-card-tag {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 2px 7px;
  background: rgba(127, 119, 221, 0.08);
  color: #7f77dd;
  border-radius: 6px;
  font-size: 10.5px;
  font-weight: 500;
}
.cn-card-links {
  display: flex;
  flex-wrap: wrap;
  gap: 5px;
  margin-top: 8px;
}
.cn-card-link {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  padding: 3px 8px 3px 4px;
  background: rgba(55, 138, 221, 0.08);
  border-radius: 6px;
  font-size: 10.5px;
}
.cn-card-link-type {
  background: var(--blue);
  color: #ffffff;
  padding: 1px 5px;
  border-radius: 4px;
  font-size: 9.5px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.04em;
}
.cn-card-link-label {
  color: var(--t1, #1e2a4a);
  font-weight: 500;
}
.cn-card-foot {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-top: 9px;
  padding-top: 8px;
  border-top: 1px solid rgba(30, 42, 74, 0.06);
}
.cn-card-time {
  font-size: 10.5px;
  color: rgba(30, 42, 74, 0.5);
}
.cn-resolve-pill {
  display: inline-flex;
  align-items: center;
  height: 20px;
  padding: 0 9px;
  border-radius: 10px;
  background: rgba(239, 159, 39, 0.1);
  color: var(--amber);
  font-size: 10.5px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.18s;
}
.cn-resolve-pill:hover {
  background: rgba(239, 159, 39, 0.18);
}
.cn-resolve-pill-active {
  background: rgba(29, 158, 117, 0.12);
  color: var(--green);
}
.cn-resolve-pill-active:hover {
  background: rgba(29, 158, 117, 0.22);
}

/* ============================================================ */
/* CARD: ОТВЕТСТВЕННЫЙ + ЧЕК-ЛИСТ */
/* ============================================================ */
.cn-card-time { margin-right: auto; }
.cn-card-foot { gap: 8px; }

.cn-card-assignee {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  max-width: 170px;
  padding: 2px 9px 2px 3px;
  border-radius: 11px;
  background: rgba(127, 119, 221, 0.08);
  border: 1px solid rgba(127, 119, 221, 0.2);
}
.cn-card-assignee-av {
  width: 17px; height: 17px; border-radius: 50%;
  background: linear-gradient(135deg, #7f77dd, #6b62cc);
  color: #fff;
  display: inline-flex; align-items: center; justify-content: center;
  font-size: 8px; font-weight: 600; flex-shrink: 0;
}
.cn-card-assignee-name {
  font-size: 10.5px; font-weight: 500;
  color: var(--t1, #1e2a4a);
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
}

.cn-card-cl { margin-top: 10px; }
.cn-card-cl-head {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 7px;
}
.cn-card-cl-track {
  position: relative;
  flex: 1;
  height: 5px;
  border-radius: 3px;
  background: rgba(30, 42, 74, 0.07);
  overflow: hidden;
}
.cn-card-cl-fill {
  position: absolute;
  inset: 0 auto 0 0;
  height: 100%;
  border-radius: 3px;
  background: linear-gradient(90deg, #7f77dd, #1d9e75);
  transition: width 0.5s var(--ease-out, cubic-bezier(0.16, 1, 0.3, 1));
}
.cn-card-cl-num {
  font-size: 10px;
  font-weight: 600;
  color: rgba(30, 42, 74, 0.55);
  font-variant-numeric: tabular-nums;
  flex-shrink: 0;
}
.cn-card-cl-items {
  display: flex;
  flex-direction: column;
  gap: 2px;
}
.cn-card-cl-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 3px 4px;
  border-radius: 6px;
  transition: background 0.14s;
}
.cn-card-cl-item:hover { background: rgba(30, 42, 74, 0.03); }
.cn-card-cl-text {
  flex: 1;
  font-size: 12px;
  color: var(--t1, #1e2a4a);
  line-height: 1.35;
  transition: color 0.18s;
  min-width: 0;
}
.cn-card-cl-item-done .cn-card-cl-text {
  color: rgba(30, 42, 74, 0.4);
  text-decoration: line-through;
  text-decoration-color: rgba(30, 42, 74, 0.3);
}
.cn-card-cl-av {
  width: 19px; height: 19px; border-radius: 50%;
  background: rgba(127, 119, 221, 0.14);
  color: #6b62cc;
  display: inline-flex; align-items: center; justify-content: center;
  font-size: 8.5px; font-weight: 700; flex-shrink: 0;
}

/* shared checkbox (modal + card) */
.cn-cl-check {
  width: 19px; height: 19px;
  flex-shrink: 0;
  border: 1.6px solid rgba(30, 42, 74, 0.22);
  border-radius: 6px;
  background: #fff;
  color: #fff;
  display: inline-flex; align-items: center; justify-content: center;
  cursor: pointer;
  transition: all 0.18s var(--ease-out, cubic-bezier(0.16, 1, 0.3, 1));
}
.cn-cl-check:hover:not(:disabled) { border-color: #7f77dd; }
.cn-cl-check:disabled { cursor: default; opacity: 0.6; }
.cn-cl-check-on {
  background: linear-gradient(135deg, #7f77dd, #1d9e75);
  border-color: transparent;
  animation: cnClPop 0.32s var(--ease-bounce, cubic-bezier(0.34, 1.56, 0.64, 1));
}
.cn-cl-check-card { width: 18px; height: 18px; }
@keyframes cnClPop {
  0% { transform: scale(1); }
  45% { transform: scale(1.22); }
  100% { transform: scale(1); }
}

/* ============================================================ */
/* MODAL: ЧЕК-ЛИСТ РЕДАКТОР */
/* ============================================================ */
.cn-cl-label {
  display: flex;
  align-items: center;
  justify-content: space-between;
}
.cn-cl-progress-mini {
  display: inline-flex;
  align-items: center;
  gap: 7px;
  text-transform: none;
  letter-spacing: 0;
}
.cn-cl-progress-track {
  width: 64px;
  height: 5px;
  border-radius: 3px;
  background: rgba(30, 42, 74, 0.08);
  overflow: hidden;
}
.cn-cl-progress-fill {
  display: block;
  height: 100%;
  border-radius: 3px;
  background: linear-gradient(90deg, #7f77dd, #1d9e75);
  transition: width 0.5s var(--ease-out, cubic-bezier(0.16, 1, 0.3, 1));
}
.cn-cl-progress-num {
  font-size: 10.5px;
  font-weight: 600;
  color: rgba(30, 42, 74, 0.6);
  font-variant-numeric: tabular-nums;
}
.cn-cl-list {
  display: flex;
  flex-direction: column;
  gap: 5px;
  margin-bottom: 8px;
}
.cn-cl-row {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 5px 6px;
  border: 1px solid rgba(30, 42, 74, 0.08);
  border-radius: 9px;
  background: var(--bg2, #fafafc);
  transition: all 0.18s var(--ease-standard);
}
.cn-cl-row:hover { border-color: rgba(127, 119, 221, 0.3); background: #fff; }
.cn-cl-row-done { background: rgba(29, 158, 117, 0.05); }
.cn-cl-text {
  flex: 1;
  border: none;
  outline: none;
  background: transparent;
  font-size: 12.5px;
  font-family: inherit;
  color: var(--t1, #1e2a4a);
  min-width: 0;
}
.cn-cl-row-done .cn-cl-text {
  color: rgba(30, 42, 74, 0.45);
  text-decoration: line-through;
  text-decoration-color: rgba(30, 42, 74, 0.3);
}
.cn-cl-text::placeholder { color: rgba(30, 42, 74, 0.35); }
.cn-cl-row-actions {
  display: inline-flex;
  align-items: center;
  gap: 1px;
  flex-shrink: 0;
}
.cn-cl-mini {
  width: 22px; height: 22px;
  display: inline-flex; align-items: center; justify-content: center;
  border: none;
  border-radius: 5px;
  background: transparent;
  color: rgba(30, 42, 74, 0.4);
  cursor: pointer;
  transition: all 0.15s;
}
.cn-cl-mini:hover:not(:disabled) { background: rgba(30, 42, 74, 0.08); color: var(--t1, #1e2a4a); }
.cn-cl-mini:disabled { opacity: 0.3; cursor: default; }
.cn-cl-mini-danger:hover:not(:disabled) { background: rgba(226, 75, 74, 0.12); color: #e24b4a; }

.cn-cl-add {
  display: flex;
  align-items: center;
  gap: 8px;
  height: 36px;
  padding: 0 10px;
  border: 1px dashed rgba(127, 119, 221, 0.35);
  border-radius: 9px;
  background: transparent;
  transition: all 0.18s;
}
.cn-cl-add:focus-within { border-color: #7f77dd; background: rgba(127, 119, 221, 0.04); }
.cn-cl-add-icon {
  display: inline-flex;
  color: var(--p, #7f77dd);
  flex-shrink: 0;
}
.cn-cl-add-input {
  flex: 1;
  border: none;
  outline: none;
  background: transparent;
  font-size: 12.5px;
  font-family: inherit;
  color: var(--t1, #1e2a4a);
}
.cn-cl-add-input::placeholder { color: rgba(30, 42, 74, 0.4); }
.cn-cl-add-btn {
  height: 24px;
  padding: 0 11px;
  border: none;
  border-radius: 7px;
  background: rgba(127, 119, 221, 0.12);
  color: var(--p-deep, #6b62cc);
  font-size: 11.5px;
  font-weight: 600;
  font-family: inherit;
  cursor: pointer;
  transition: all 0.16s;
}
.cn-cl-add-btn:hover { background: #7f77dd; color: #fff; }

/* TransitionGroup для пунктов чек-листа в модалке */
.cn-cl-enter-active { transition: all 0.28s var(--ease-out, cubic-bezier(0.16, 1, 0.3, 1)); }
.cn-cl-leave-active { transition: all 0.2s var(--ease-standard); position: relative; }
.cn-cl-enter-from { opacity: 0; transform: translateY(-6px); }
.cn-cl-leave-to { opacity: 0; transform: translateX(12px); }
.cn-cl-move { transition: transform 0.28s var(--ease-out, cubic-bezier(0.16, 1, 0.3, 1)); }

/* ============================================================ */
/* DUE BAR */
/* ============================================================ */
.cn-due-bar {
  position: relative;
  height: 22px;
  margin-top: 9px;
  background: rgba(30, 42, 74, 0.05);
  border-radius: 11px;
  overflow: hidden;
}
.cn-due-bar-fill {
  height: 100%;
  background: linear-gradient(90deg, var(--green) 0%, #2cb98a 100%);
  transition: width 0.6s var(--ease-standard);
}
.cn-due-bar[data-state="warn"] .cn-due-bar-fill {
  background: linear-gradient(90deg, var(--amber) 0%, #f5b54e 100%);
}
.cn-due-bar[data-state="overdue"] .cn-due-bar-fill {
  background: linear-gradient(90deg, var(--sev-high) 0%, #f06866 100%);
}
.cn-due-bar-label {
  position: absolute;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 10.5px;
  font-weight: 600;
  color: #ffffff;
  text-shadow: 0 1px 2px rgba(0, 0, 0, 0.15);
}

/* ============================================================ */
/* DUE-DATE HOLIDAY WARNING (in card) */
/* ============================================================ */
.cn-due-holiday-warn {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  margin-top: 8px;
  padding: 5px 10px;
  background: rgba(239, 159, 39, 0.1);
  color: #c47e1f;
  border-radius: 6px;
  font-size: 11px;
  font-weight: 500;
}

/* ============================================================ */
/* EMPTY STATE */
/* ============================================================ */
.cn-empty {
  text-align: center;
  padding: 60px 20px 40px;
  color: rgba(30, 42, 74, 0.55);
}
.cn-empty-illust {
  margin-bottom: 14px;
  color: rgba(127, 119, 221, 0.5);
}
.cn-empty-title {
  font-size: 16px;
  font-weight: 500;
  color: var(--t1, #1e2a4a);
  letter-spacing: -0.01em;
  margin-bottom: 6px;
}
.cn-empty-desc {
  font-size: 12.5px;
  max-width: 380px;
  margin: 0 auto 18px;
  line-height: 1.55;
}
.cn-empty-cta {
  animation: cnPulse 2.4s ease-in-out infinite;
}
@keyframes cnPulse {
  0%,
  100% {
    box-shadow: 0 2px 6px rgba(127, 119, 221, 0.25);
  }
  50% {
    box-shadow: 0 2px 6px rgba(127, 119, 221, 0.25),
      0 0 0 6px rgba(127, 119, 221, 0.1);
  }
}

/* ============================================================ */
/* ERROR / LOADING */
/* ============================================================ */
.cn-error {
  padding: 9px 12px;
  margin: 8px 0;
  background: rgba(226, 75, 74, 0.08);
  color: #c63d3c;
  /* top-stripe via .cn-error::before (red) */
  position: relative;
  overflow: hidden;
  border-radius: 6px;
  font-size: 12px;
}
.cn-loading {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 12px;
  padding: 40px 20px;
  font-size: 12.5px;
  color: rgba(30, 42, 74, 0.5);
}
.cn-spinner {
  width: 18px;
  height: 18px;
  border: 2px solid rgba(127, 119, 221, 0.2);
  border-top-color: #7f77dd;
  border-radius: 50%;
  animation: cnSpin 0.7s linear infinite;
}
@keyframes cnSpin {
  to {
    transform: rotate(360deg);
  }
}

/* ============================================================ */
/* MODAL */
/* ============================================================ */
.cn-modal-backdrop {
  position: fixed;
  inset: 0;
  background: rgba(15, 18, 40, 0.45);
  backdrop-filter: blur(8px);
  -webkit-backdrop-filter: blur(8px);
  z-index: 9999;
  display: flex;
  align-items: flex-start;
  justify-content: center;
  padding: 60px 20px 40px;
  overflow-y: auto;
}
.cn-modal {
  width: 100%;
  max-width: 640px;
  background: var(--bg1, #ffffff);
  border-radius: 12px;
  box-shadow:
    0 24px 64px rgba(15, 23, 60, 0.18),
    0 8px 24px rgba(15, 23, 60, 0.08);
  overflow: hidden;
}

/* Modal slide-up + fade-in */
.cn-modal-enter-active {
  transition: all 0.45s var(--ease-standard);
}
.cn-modal-leave-active {
  transition: all 0.25s ease;
}
.cn-modal-enter-from {
  opacity: 0;
  -webkit-backdrop-filter: blur(0);
  backdrop-filter: blur(0);
}
.cn-modal-enter-from .cn-modal {
  opacity: 0;
  transform: translateY(20px) scale(0.96);
}
.cn-modal-leave-to {
  opacity: 0;
}
.cn-modal-leave-to .cn-modal {
  opacity: 0;
  transform: translateY(8px) scale(0.98);
}
.cn-modal-enter-active .cn-modal {
  transition: all 0.45s var(--ease-standard);
}

.cn-modal-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 16px 20px;
  border-bottom: 1px solid rgba(30, 42, 74, 0.06);
}
.cn-modal-head h3 {
  margin: 0;
  font-size: 15px;
  font-weight: 500;
  letter-spacing: -0.01em;
  color: var(--t1, #1e2a4a);
}
.cn-modal-body {
  padding: 16px 20px;
  display: flex;
  flex-direction: column;
  gap: 14px;
  max-height: 65vh;
  overflow-y: auto;
}
.cn-modal-foot {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
  padding: 12px 20px;
  border-top: 1px solid rgba(30, 42, 74, 0.06);
  background: rgba(245, 246, 248, 0.4);
}

/* === Form fields === */
.cn-field {
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.cn-field-row {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 12px;
}
.cn-field-label {
  font-size: 10.5px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  color: rgba(30, 42, 74, 0.6);
}
.cn-req {
  color: var(--sev-high);
}
.cn-input,
.cn-textarea {
  width: 100%;
  padding: 8px 11px;
  border: 1px solid rgba(30, 42, 74, 0.12);
  border-radius: 7px;
  background: var(--bg1, #ffffff);
  font-size: 12.5px;
  color: var(--t1, #1e2a4a);
  outline: none;
  transition: all 0.18s;
  font-family: inherit;
  box-sizing: border-box;
}
.cn-input:focus,
.cn-textarea:focus {
  border-color: #7f77dd;
  box-shadow: 0 0 0 3px rgba(127, 119, 221, 0.1);
}
.cn-textarea {
  resize: vertical;
  min-height: 90px;
  line-height: 1.5;
}

/* Kind chips in modal */
.cn-kind-chips {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}
.cn-kind-chip {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  height: 32px;
  padding: 0 12px;
  border: 1.5px solid rgba(30, 42, 74, 0.1);
  border-radius: 8px;
  background: var(--bg1, #ffffff);
  color: rgba(30, 42, 74, 0.65);
  font-size: 12px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.22s var(--ease-standard);
  --chip-color: #7f77dd;
}
.cn-kind-chip:hover {
  border-color: var(--chip-color);
  color: var(--chip-color);
}
.cn-kind-chip-active {
  background: var(--chip-color);
  border-color: var(--chip-color);
  color: #ffffff;
  box-shadow:
    0 2px 8px color-mix(in srgb, var(--chip-color) 30%, transparent),
    0 0 0 3px color-mix(in srgb, var(--chip-color) 12%, transparent);
  animation: cnChipPulse 0.4s var(--ease-standard);
}

/* Tags editor */
.cn-tags-editor {
  display: flex;
  flex-wrap: wrap;
  gap: 5px;
  align-items: center;
  padding: 6px 8px;
  border: 1px solid rgba(30, 42, 74, 0.12);
  border-radius: 7px;
  background: var(--bg1, #ffffff);
  min-height: 40px;
}
.cn-tags-editor:focus-within {
  border-color: #7f77dd;
  box-shadow: 0 0 0 3px rgba(127, 119, 221, 0.1);
}
.cn-card-tag-removable {
  padding-right: 3px;
}
.cn-tag-remove {
  background: rgba(127, 119, 221, 0.18);
  color: #7f77dd;
  border: none;
  width: 16px;
  height: 16px;
  border-radius: 50%;
  margin-left: 2px;
  cursor: pointer;
  font-size: 13px;
  line-height: 1;
  display: inline-flex;
  align-items: center;
  justify-content: center;
}
.cn-tag-remove:hover {
  background: #7f77dd;
  color: #ffffff;
}
.cn-tag-input {
  flex: 1;
  min-width: 100px;
  border: none;
  outline: none;
  background: transparent;
  font-size: 12px;
  padding: 4px 2px;
}
.cn-tag-suggest {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
  margin-top: 6px;
}
.cn-tag-suggest-item {
  border: 1px dashed rgba(127, 119, 221, 0.4);
  background: transparent;
  color: rgba(127, 119, 221, 0.85);
  padding: 2px 8px;
  border-radius: 10px;
  font-size: 10.5px;
  cursor: pointer;
  transition: all 0.16s;
}
.cn-tag-suggest-item:hover:not(:disabled) {
  background: rgba(127, 119, 221, 0.1);
}
.cn-tag-suggest-disabled {
  opacity: 0.35;
  cursor: not-allowed;
}

/* Date warn */
.cn-date-warn {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px;
  padding: 7px 10px;
  background: rgba(239, 159, 39, 0.1);
  border-radius: 6px;
  /* top-stripe via .cn-date-warn::before (amber) */
  position: relative;
  overflow: hidden;
  font-size: 11px;
  color: #8c5a13;
  margin-top: 4px;
}
.cn-date-warn-cta {
  margin-left: auto;
  background: var(--amber);
  color: #ffffff;
  border: none;
  padding: 3px 9px;
  border-radius: 5px;
  font-size: 10.5px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.18s;
}
.cn-date-warn-cta:hover {
  background: #d8881a;
  transform: translateY(-1px);
}

/* Links editor */
.cn-links-list {
  display: flex;
  flex-direction: column;
  gap: 5px;
  margin-bottom: 6px;
}
.cn-link-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 10px;
  background: rgba(55, 138, 221, 0.06);
  border-radius: 7px;
  font-size: 11.5px;
}
.cn-link-item-type {
  background: var(--blue);
  color: #ffffff;
  padding: 1px 6px;
  border-radius: 4px;
  font-size: 9.5px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.04em;
  flex-shrink: 0;
}
.cn-link-item-label {
  flex: 1;
  color: var(--t1, #1e2a4a);
}
.cn-link-remove {
  background: transparent;
  border: none;
  color: rgba(30, 42, 74, 0.5);
  cursor: pointer;
  font-size: 16px;
  line-height: 1;
  width: 20px;
  height: 20px;
}
.cn-link-remove:hover {
  color: var(--sev-high);
}
.cn-link-editor {
  display: grid;
  grid-template-columns: 140px 1fr 36px;
  gap: 6px;
}
.cn-link-type-select {
  padding-right: 4px;
}

/* ============================================================ */
/* MOBILE */
/* ============================================================ */
@media (max-width: 1100px) {
  .cn-cards-grid {
    grid-template-columns: 1fr;
  }
}
@media (max-width: 720px) {
  .cn-top {
    flex-direction: column;
    align-items: stretch;
  }
  .cn-search {
    max-width: 100%;
  }
  .cn-filters {
    flex-direction: column;
    align-items: stretch;
  }
  .cn-toggles {
    justify-content: flex-start;
  }
  .cn-field-row {
    grid-template-columns: 1fr;
  }
  .cn-link-editor {
    grid-template-columns: 1fr;
  }
}

/* ─── Top-stripe accents (заменяют border-left) ─── */
.cn-hw-item::before,
.cn-holiday-item::before,
.cn-card::before {
  content: ""; position: absolute; top: 0; left: 0; right: 0;
  height: 3px;
  background: var(--kind-color, var(--h-color, #7F77DD));
  border-top-left-radius: inherit; border-top-right-radius: inherit;
  transform-origin: left center;
  animation:
    uzaStripeDrawIn .8s var(--ease-standard) 100ms both,
    uzaStripeBreathe 2.8s ease-in-out 1s infinite;
  pointer-events: none; z-index: 1;
}
.cn-error::before {
  content: ""; position: absolute; top: 0; left: 0; right: 0;
  height: 3px;
  background: var(--sev-high);
  border-top-left-radius: inherit; border-top-right-radius: inherit;
  transform-origin: left center;
  animation: uzaStripeDrawIn .6s var(--ease-standard) both;
  pointer-events: none;
}
.cn-date-warn::before {
  content: ""; position: absolute; top: 0; left: 0; right: 0;
  height: 3px;
  background: var(--amber);
  border-top-left-radius: inherit; border-top-right-radius: inherit;
  transform-origin: left center;
  animation: uzaStripeDrawIn .6s var(--ease-standard) both;
  pointer-events: none;
}
@media (prefers-reduced-motion: reduce) {
  .cn-hw-item::before, .cn-holiday-item::before, .cn-card::before,
  .cn-error::before, .cn-date-warn::before { animation: none; }
}
</style>
