<script setup lang="ts">
/**
 * UserAutocomplete — выпадающий список юзеров по подстроке.
 *
 * Использование:
 *   <UserAutocomplete
 *      v-model:email="formAssigneeEmail"
 *      v-model:name="formAssigneeName"
 *      :disabled="!canEdit"
 *      placeholder="email@uz-assets.uz или ФИО"
 *   />
 *
 * Под капотом: вызывает GET /users/search?q= при вводе (debounce 200ms),
 * показывает до 10 пользователей с аватаром-инициалами. Выбор подставляет
 * и email и full_name в parent component.
 */
import { ref, computed, watch, onBeforeUnmount } from "vue";
import { api } from "@/api/client";

interface UserSearchItem {
  id: string;
  email: string;
  full_name: string | null;
  username: string | null;
  initials: string;
  department: string | null;
  is_active: boolean;
}

const props = defineProps<{
  email: string;
  name?: string;
  disabled?: boolean;
  placeholder?: string;
  /** When true, restricts query to active users (default). */
  activeOnly?: boolean;
}>();

const emit = defineEmits<{
  (e: "update:email", v: string): void;
  (e: "update:name", v: string): void;
  (e: "pick", user: UserSearchItem): void;
}>();

const inputEmail = ref(props.email || "");
watch(() => props.email, v => { if (v !== inputEmail.value) inputEmail.value = v || ""; });

const results = ref<UserSearchItem[]>([]);
const open = ref(false);
const loading = ref(false);
const highlight = ref(-1);
let debounceTimer: any = null;

async function search(q: string) {
  if (q.trim().length < 1) {
    results.value = [];
    open.value = false;
    return;
  }
  loading.value = true;
  try {
    const { data } = await api.get<{ items: UserSearchItem[] }>("/users/search", {
      params: { q, limit: 10, active_only: props.activeOnly !== false },
    });
    results.value = data.items || [];
    open.value = results.value.length > 0;
    highlight.value = open.value ? 0 : -1;
  } catch (e) {
    results.value = [];
    open.value = false;
  } finally {
    loading.value = false;
  }
}

function onInput(e: Event) {
  const v = (e.target as HTMLInputElement).value;
  emit("update:email", v);
  if (debounceTimer) clearTimeout(debounceTimer);
  debounceTimer = setTimeout(() => search(v), 200);
}

function pick(u: UserSearchItem) {
  emit("update:email", u.email);
  emit("update:name", u.full_name || "");
  emit("pick", u);
  inputEmail.value = u.email;
  open.value = false;
  results.value = [];
}

function onKeydown(e: KeyboardEvent) {
  if (!open.value || results.value.length === 0) return;
  if (e.key === "ArrowDown") { e.preventDefault(); highlight.value = (highlight.value + 1) % results.value.length; }
  else if (e.key === "ArrowUp") { e.preventDefault(); highlight.value = (highlight.value - 1 + results.value.length) % results.value.length; }
  else if (e.key === "Enter") {
    if (highlight.value >= 0 && highlight.value < results.value.length) {
      e.preventDefault();
      pick(results.value[highlight.value]);
    }
  }
  else if (e.key === "Escape") { open.value = false; }
}

function onBlur() {
  // delay so click on dropdown registers first
  setTimeout(() => { open.value = false; }, 150);
}

onBeforeUnmount(() => { if (debounceTimer) clearTimeout(debounceTimer); });

const displayName = computed(() => props.name || "");
</script>

<template>
  <div class="ua-root">
    <div class="ua-field-grid">
      <input
        class="ua-input"
        :value="displayName"
        placeholder="Имя Фамилия"
        :disabled="disabled"
        @input="emit('update:name', ($event.target as HTMLInputElement).value)"
      />
      <div class="ua-email-wrap">
        <input
          class="ua-input"
          :value="inputEmail"
          :placeholder="placeholder || 'email или начало имени…'"
          :disabled="disabled"
          type="text"
          @input="onInput"
          @focus="search(inputEmail)"
          @blur="onBlur"
          @keydown="onKeydown"
        />
        <div v-if="open" class="ua-dropdown">
          <div v-if="loading" class="ua-loading">Поиск…</div>
          <button
            v-for="(u, i) in results"
            :key="u.id"
            type="button"
            class="ua-item"
            :class="{ active: i === highlight }"
            @mousedown.prevent="pick(u)"
            @mouseenter="highlight = i"
          >
            <span class="ua-avatar">{{ u.initials }}</span>
            <span class="ua-info">
              <span class="ua-name">{{ u.full_name || u.email }}</span>
              <span class="ua-meta">
                <span class="ua-email">{{ u.email }}</span>
                <span v-if="u.department" class="ua-dept">· {{ u.department }}</span>
              </span>
            </span>
          </button>
          <div v-if="!loading && results.length === 0" class="ua-empty">Никого не найдено</div>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.ua-root { width: 100%; }
.ua-field-grid { display: grid; grid-template-columns: 1fr 1.2fr; gap: 8px; }
.ua-input {
  width: 100%;
  padding: 8px 10px;
  border: 0.5px solid #E5E7EB;
  border-radius: 7px;
  font-size: 12.5px;
  font-family: inherit;
  background: #FAFAFC;
  color: #1E2A4A;
  outline: none;
}
.ua-input:focus { border-color: #7F77DD; background: white; }
.ua-input:disabled { opacity: 0.55; cursor: not-allowed; }
.ua-email-wrap { position: relative; }
.ua-dropdown {
  position: absolute; top: calc(100% + 4px); left: 0; right: 0;
  background: white;
  border: 0.5px solid #E5E7EB;
  border-radius: 8px;
  box-shadow: 0 8px 24px rgba(15,23,60,.10);
  max-height: 320px; overflow-y: auto;
  z-index: 50;
  padding: 4px;
}
.ua-loading, .ua-empty {
  padding: 10px 12px; font-size: 12px; color: #888780; text-align: center;
}
.ua-item {
  display: flex; align-items: center; gap: 10px;
  width: 100%;
  padding: 8px 10px;
  border: none; border-radius: 6px;
  background: transparent;
  cursor: pointer; text-align: left; font-family: inherit;
  transition: background .1s;
}
.ua-item.active, .ua-item:hover { background: rgba(127,119,221,.10); }
.ua-avatar {
  width: 28px; height: 28px; border-radius: 50%;
  background: #7F77DD; color: white;
  display: inline-flex; align-items: center; justify-content: center;
  font-size: 11px; font-weight: 600;
  flex-shrink: 0;
}
.ua-info { display: flex; flex-direction: column; min-width: 0; }
.ua-name { font-size: 12.5px; color: #1E2A4A; font-weight: 500; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.ua-meta { font-size: 10.5px; color: #888780; display: flex; gap: 4px; }
.ua-email { font-family: ui-monospace, 'SF Mono', monospace; }
</style>
