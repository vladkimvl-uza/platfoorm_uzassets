<script setup lang="ts">
/**
 * NoteAssigneePicker — компактный пикер ответственного.
 *
 * Используется и для ответственного за заметку в целом, и для каждого
 * пункта чек-листа. Кнопка-чип: если назначен — аватар(инициалы)+имя+×,
 * иначе — пунктирный «+ Ответственный». Клик раскрывает поиск (/users/search).
 *
 *   <NoteAssigneePicker
 *      :id="form.assignee_id" :name="form.assignee_name"
 *      @update:id="form.assignee_id = $event"
 *      @update:name="form.assignee_name = $event" />
 */
import { ref, computed, nextTick, onBeforeUnmount } from "vue";
import { api } from "@/api/client";
import { useI18n } from "@/composables/useI18n";
import { i18nKey } from "@/locale/keys";

const { t } = useI18n();


interface UserSearchItem {
  id: string;
  email: string;
  full_name: string | null;
  username: string | null;
  initials: string;
  department: string | null;
  job_title?: string | null;
  is_active: boolean;
}

const props = withDefaults(defineProps<{
  id: string | null;
  name: string | null;
  disabled?: boolean;
  size?: "sm" | "md";
  placeholder?: string;
  /** Код компании: при нём список сотрудников ЭТОЙ компании показывается сразу,
   *  без ввода, и поиск не выходит за её пределы. */
  companyCode?: string | null;
  /** Разрешить ввести произвольное ФИО (человек не заведён в платформе). */
  allowCustom?: boolean;
}>(), { size: "md", placeholder: i18nKey("Ответственный"), allowCustom: false });

const emit = defineEmits<{
  (e: "update:id", v: string | null): void;
  (e: "update:name", v: string | null): void;
  (e: "pick", user: UserSearchItem): void;
}>();

const open = ref(false);
const q = ref("");
const results = ref<UserSearchItem[]>([]);
const loading = ref(false);
const highlight = ref(-1);
const rootEl = ref<HTMLElement | null>(null);
const inputEl = ref<HTMLInputElement | null>(null);
let debounceTimer: any = null;

const initials = computed(() => {
  const n = (props.name || "").trim();
  if (!n) return "?";
  const parts = n.split(/\s+/).filter(Boolean);
  const a = parts[0]?.[0] || "";
  const b = parts.length > 1 ? parts[parts.length - 1][0] : "";
  return (a + b).toUpperCase() || "?";
});

async function runSearch(text: string) {
  const scoped = !!props.companyCode;
  // Без компании пустой запрос не шлём (бэкенд требует 2 символа — защита от
  // перечисления каталога). С компанией — наоборот, показываем её сотрудников
  // сразу: это ожидаемое поведение пикера внутри карточки компании.
  if (!scoped && text.trim().length < 1) { results.value = []; return; }
  loading.value = true;
  try {
    const { data } = await api.get<{ items: UserSearchItem[] }>("/users/search", {
      params: {
        q: text, limit: scoped ? 25 : 8, active_only: true,
        ...(scoped ? { company_code: props.companyCode } : {}),
      },
    });
    results.value = data.items || [];
    highlight.value = results.value.length ? 0 : -1;
  } catch {
    results.value = [];
  } finally {
    loading.value = false;
  }
}

function onInput(e: Event) {
  q.value = (e.target as HTMLInputElement).value;
  if (debounceTimer) clearTimeout(debounceTimer);
  debounceTimer = setTimeout(() => runSearch(q.value), 200);
}

async function openPanel() {
  if (props.disabled) return;
  open.value = true;
  q.value = "";
  results.value = [];
  document.addEventListener("mousedown", onDocClick, true);
  await nextTick();
  inputEl.value?.focus();
  // Сотрудники компании подгружаются сразу — пользователю не нужно угадывать,
  // кто заведён в системе.
  if (props.companyCode) void runSearch("");
}

function closePanel() {
  open.value = false;
  document.removeEventListener("mousedown", onDocClick, true);
}

function onDocClick(e: MouseEvent) {
  if (rootEl.value && !rootEl.value.contains(e.target as Node)) closePanel();
}

function pick(u: UserSearchItem) {
  emit("update:id", u.id);
  emit("update:name", u.full_name || u.email);
  emit("pick", u);
  closePanel();
}

/** Произвольное ФИО: человек не заведён в платформе (внешний консультант,
 *  сотрудник без учётной записи). Сохраняем только имя, без user_id. */
function pickCustom() {
  const name = q.value.trim();
  if (!name) return;
  emit("update:id", null);
  emit("update:name", name);
  closePanel();
}

const canAddCustom = computed(() =>
  !!props.allowCustom
  && q.value.trim().length >= 2
  && !results.value.some(u => (u.full_name || u.email).toLowerCase() === q.value.trim().toLowerCase()),
);

function clearAssignee(e?: Event) {
  e?.stopPropagation();
  emit("update:id", null);
  emit("update:name", null);
}

function onKeydown(e: KeyboardEvent) {
  if (!open.value || !results.value.length) {
    if (e.key === "Escape") closePanel();
    return;
  }
  if (e.key === "ArrowDown") { e.preventDefault(); highlight.value = (highlight.value + 1) % results.value.length; }
  else if (e.key === "ArrowUp") { e.preventDefault(); highlight.value = (highlight.value - 1 + results.value.length) % results.value.length; }
  else if (e.key === "Enter") {
    e.preventDefault();
    if (highlight.value >= 0) pick(results.value[highlight.value]);
    else if (canAddCustom.value) pickCustom();
  }
  else if (e.key === "Escape") { closePanel(); }
}

onBeforeUnmount(() => {
  if (debounceTimer) clearTimeout(debounceTimer);
  document.removeEventListener("mousedown", onDocClick, true);
});
</script>

<template>
  <div ref="rootEl" class="ap-root" :class="[`ap-${size}`, { 'ap-disabled': disabled }]">
    <!-- Assigned chip -->
    <button
      v-if="id || name"
      type="button"
      class="ap-chip ap-chip-set"
      :disabled="disabled"
      :title="name || ''"
      @click="openPanel"
    >
      <span class="ap-avatar">{{ initials }}</span>
      <span class="ap-name">{{ name }}</span>
      <span v-if="!disabled" class="ap-clear" @click="clearAssignee" :title="t('Убрать')">
        <svg width="10" height="10" viewBox="0 0 16 16" fill="none">
          <path d="M3 3 L13 13 M13 3 L3 13" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" />
        </svg>
      </span>
    </button>

    <!-- Empty trigger -->
    <button
      v-else
      type="button"
      class="ap-chip ap-chip-empty"
      :disabled="disabled"
      @click="openPanel"
    >
      <svg width="12" height="12" viewBox="0 0 16 16" fill="none">
        <circle cx="8" cy="5.5" r="2.6" stroke="currentColor" stroke-width="1.5" />
        <path d="M3.2 13 C3.6 10.4 5.6 9 8 9 C10.4 9 12.4 10.4 12.8 13" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" />
      </svg>
      <span>{{ t(placeholder) }}</span>
    </button>

    <!-- Dropdown -->
    <Transition name="ap-pop">
      <div v-if="open" class="ap-dropdown">
        <div class="ap-search">
          <svg width="13" height="13" viewBox="0 0 16 16" fill="none">
            <circle cx="7" cy="7" r="5" stroke="currentColor" stroke-width="1.6" />
            <path d="M11 11 L14 14" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" />
          </svg>
          <input
            ref="inputEl"
            :value="q"
            type="text"
            :placeholder="t('Имя или email…')"
            @input="onInput"
            @keydown="onKeydown"
          />
        </div>
        <div class="ap-results">
          <div v-if="loading" class="ap-hint">{{ t('Поиск…') }}</div>
          <button
            v-for="(u, i) in results"
            :key="u.id"
            type="button"
            class="ap-item"
            :class="{ active: i === highlight }"
            @mousedown.prevent="pick(u)"
            @mouseenter="highlight = i"
          >
            <span class="ap-avatar ap-avatar-sm">{{ u.initials }}</span>
            <span class="ap-item-info">
              <span class="ap-item-name">{{ u.full_name || u.email }}</span>
              <span class="ap-item-meta">{{ u.job_title || u.email }}<span v-if="u.department"> · {{ u.department }}</span></span>
            </span>
          </button>
          <!-- Произвольное ФИО — для тех, кого нет в платформе -->
          <button
            v-if="canAddCustom"
            type="button"
            class="ap-item ap-item-custom"
            @mousedown.prevent="pickCustom"
          >
            <span class="ap-avatar ap-avatar-sm ap-avatar-custom">+</span>
            <span class="ap-item-info">
              <span class="ap-item-name">{{ q.trim() }}</span>
              <span class="ap-item-meta">{{ t('добавить как есть — нет учётной записи') }}</span>
            </span>
          </button>
          <div v-if="!loading && q && results.length === 0 && !canAddCustom" class="ap-hint">{{ t('Никого не найдено') }}</div>
          <div v-if="!loading && !q && !companyCode" class="ap-hint ap-hint-muted">{{ t('Начните вводить имя') }}</div>
          <div v-if="!loading && !q && companyCode && results.length === 0" class="ap-hint ap-hint-muted">{{ t('В этой компании пока нет заведённых сотрудников') }}</div>
        </div>
      </div>
    </Transition>
  </div>
</template>

<style scoped>
.ap-root { position: relative; display: inline-flex; }

.ap-chip {
  display: inline-flex; align-items: center; gap: 6px;
  height: 26px; padding: 0 8px 0 6px;
  border-radius: 13px;
  font-size: 11.5px; font-weight: 500; font-family: inherit;
  cursor: pointer;
  transition: all .18s var(--ease-standard, cubic-bezier(.4,0,.2,1));
}
.ap-sm .ap-chip { height: 23px; font-size: 11px; }
.ap-disabled .ap-chip { cursor: default; opacity: .7; }

.ap-chip-empty {
  border: 1px dashed rgba(127, 119, 221, .4);
  background: transparent;
  color: var(--p, #7f77dd);
  padding: 0 10px 0 8px;
}
.ap-chip-empty:hover:not(:disabled) {
  border-color: #7f77dd;
  background: rgba(127, 119, 221, .07);
}
.ap-chip-set {
  border: 1px solid rgba(127, 119, 221, .25);
  background: rgba(127, 119, 221, .08);
  color: var(--t1, #1e2a4a);
  max-width: 200px;
}
.ap-chip-set:hover:not(:disabled) { border-color: #7f77dd; }
.ap-name {
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
  max-width: 130px;
}

.ap-avatar {
  width: 20px; height: 20px; border-radius: 50%;
  background: linear-gradient(135deg, #7f77dd, #6b62cc);
  color: #fff;
  display: inline-flex; align-items: center; justify-content: center;
  font-size: 9px; font-weight: 600; flex-shrink: 0;
  letter-spacing: .02em;
}
.ap-sm .ap-avatar { width: 18px; height: 18px; font-size: 8.5px; }
.ap-avatar-sm { width: 26px; height: 26px; font-size: 10.5px; }

.ap-clear {
  display: inline-flex; align-items: center; justify-content: center;
  width: 15px; height: 15px; border-radius: 50%;
  color: var(--t3, #94a3b8);
  margin-left: 1px;
  transition: all .15s;
}
.ap-clear:hover { background: rgba(226, 75, 74, .14); color: #e24b4a; }

/* Dropdown */
.ap-dropdown {
  position: absolute; top: calc(100% + 6px); left: 0;
  width: 264px; z-index: 60;
  background: #fff;
  border: 1px solid rgba(30, 42, 74, .1);
  border-radius: 12px;
  box-shadow: 0 12px 32px rgba(15, 23, 60, .14);
  padding: 8px;
}
.ap-search {
  display: flex; align-items: center; gap: 7px;
  height: 34px; padding: 0 10px;
  border: 1px solid rgba(30, 42, 74, .1);
  border-radius: 8px;
  color: rgba(30, 42, 74, .4);
  margin-bottom: 6px;
  transition: all .16s;
}
.ap-search:focus-within { border-color: #7f77dd; box-shadow: 0 0 0 3px rgba(127, 119, 221, .1); }
.ap-search input {
  flex: 1; border: none; outline: none; background: transparent;
  font-size: 12.5px; font-family: inherit; color: var(--t1, #1e2a4a);
}
.ap-results { max-height: 240px; overflow-y: auto; display: flex; flex-direction: column; gap: 1px; }
.ap-item {
  display: flex; align-items: center; gap: 9px;
  width: 100%; padding: 6px 8px;
  border: none; border-radius: 8px; background: transparent;
  cursor: pointer; text-align: left; font-family: inherit;
  transition: background .12s;
}
.ap-item.active, .ap-item:hover { background: rgba(127, 119, 221, .1); }
.ap-item-info { display: flex; flex-direction: column; min-width: 0; }
.ap-item-name {
  font-size: 12.5px; font-weight: 500; color: var(--t1, #1e2a4a);
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
}
.ap-item-meta {
  font-size: 10.5px; color: var(--t3, #94a3b8);
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
}
.ap-item-custom { border-top: 1px solid rgba(30,42,74,.07); margin-top: 3px; padding-top: 8px; }
.ap-avatar-custom { background: linear-gradient(135deg, #B9C7EE, #8FA6DA); font-size: 14px; font-weight: 500; }
.ap-hint { padding: 9px 10px; font-size: 11.5px; color: var(--t3, #94a3b8); text-align: center; }
.ap-hint-muted { opacity: .8; }

/* pop animation */
.ap-pop-enter-active { transition: opacity .16s ease, transform .18s var(--ease-out, cubic-bezier(.16,1,.3,1)); }
.ap-pop-leave-active { transition: opacity .12s ease, transform .12s ease; }
.ap-pop-enter-from { opacity: 0; transform: translateY(-6px) scale(.97); }
.ap-pop-leave-to { opacity: 0; transform: translateY(-4px) scale(.98); }
</style>
