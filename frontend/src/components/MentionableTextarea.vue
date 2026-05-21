<script setup lang="ts">
/**
 * MentionableTextarea — textarea с @-mention popup.
 *
 * При вводе "@" + букв показывает выпадающий список пользователей.
 * Выбор подставляет `@username` (или `@email-prefix`) в текст
 * + emit("mention", user) для регистрации упоминания.
 *
 * Usage:
 *   <MentionableTextarea
 *     v-model="text"
 *     rows="3"
 *     placeholder="..."
 *     @mention="onMention"
 *   />
 */
import { ref, computed, watch, onBeforeUnmount, nextTick } from "vue";
import { api } from "@/api/client";

interface UserSearchItem {
  id: string;
  email: string;
  full_name: string | null;
  username: string | null;
  initials: string;
  department: string | null;
}

const props = defineProps<{
  modelValue: string;
  rows?: number | string;
  placeholder?: string;
  disabled?: boolean;
}>();

const emit = defineEmits<{
  (e: "update:modelValue", v: string): void;
  (e: "mention", user: UserSearchItem): void;
}>();

const textarea = ref<HTMLTextAreaElement | null>(null);
const value = computed({
  get: () => props.modelValue,
  set: v => emit("update:modelValue", v),
});

// ─── Mention state ────────────────────────────────────────────
const popupOpen = ref(false);
const popupQuery = ref("");
const popupStart = ref(0);    // position of the '@' in textarea value
const results = ref<UserSearchItem[]>([]);
const highlight = ref(-1);
const popupPos = ref({ top: 0, left: 0 });
let debounceTimer: any = null;

/** Find the active @-token under the cursor. Returns null if not in one. */
function activeMentionToken(text: string, caret: number): { start: number; query: string } | null {
  if (caret === 0) return null;
  let i = caret - 1;
  while (i >= 0) {
    const ch = text[i];
    if (ch === "@") {
      // @ must be at start of text OR preceded by whitespace/newline
      const before = i === 0 ? " " : text[i - 1];
      if (/\s/.test(before) || i === 0) {
        return { start: i, query: text.slice(i + 1, caret) };
      }
      return null;
    }
    if (/\s/.test(ch)) return null;
    if (caret - i > 32) return null;  // too long, abort
    i--;
  }
  return null;
}

async function searchMentions(q: string) {
  try {
    const { data } = await api.get<{ items: UserSearchItem[] }>("/users/search", {
      params: { q, limit: 8, active_only: true },
    });
    results.value = data.items || [];
    highlight.value = results.value.length > 0 ? 0 : -1;
  } catch {
    results.value = [];
  }
}

function onInput(e: Event) {
  const el = e.target as HTMLTextAreaElement;
  emit("update:modelValue", el.value);
  const token = activeMentionToken(el.value, el.selectionStart || 0);
  if (token) {
    popupStart.value = token.start;
    popupQuery.value = token.query;
    popupOpen.value = true;
    updatePopupPos(el, token.start);
    if (debounceTimer) clearTimeout(debounceTimer);
    debounceTimer = setTimeout(() => searchMentions(token.query), 150);
  } else {
    popupOpen.value = false;
    results.value = [];
  }
}

/** Caret-precise popup placement via a hidden mirror element.
 * The mirror copies the textarea's layout-affecting CSS, holds the text
 * up to the @ position, and uses a span marker to measure exact coords.
 */
function updatePopupPos(el: HTMLTextAreaElement, charIdx: number) {
  const cs = getComputedStyle(el);
  const mirror = document.createElement("div");
  const copyProps = [
    "boxSizing", "width", "paddingTop", "paddingRight", "paddingBottom", "paddingLeft",
    "borderTopWidth", "borderRightWidth", "borderBottomWidth", "borderLeftWidth",
    "fontFamily", "fontSize", "fontWeight", "fontStyle", "lineHeight",
    "letterSpacing", "textTransform", "wordSpacing", "textIndent",
    "whiteSpace", "wordWrap", "overflowWrap", "tabSize",
  ];
  for (const p of copyProps) (mirror.style as any)[p] = (cs as any)[p];
  mirror.style.position = "absolute";
  mirror.style.visibility = "hidden";
  mirror.style.height = "auto";
  mirror.style.whiteSpace = "pre-wrap";
  mirror.style.wordWrap = "break-word";
  mirror.style.overflow = "hidden";

  const text = el.value;
  const before = document.createTextNode(text.slice(0, charIdx));
  const marker = document.createElement("span");
  marker.textContent = "@";
  marker.style.display = "inline-block";
  mirror.appendChild(before);
  mirror.appendChild(marker);

  const parent = (el.offsetParent as HTMLElement) || document.body;
  parent.appendChild(mirror);
  const elRect = el.getBoundingClientRect();
  const parentRect = parent.getBoundingClientRect();
  mirror.style.left = (elRect.left - parentRect.left) + "px";
  mirror.style.top = (elRect.top - parentRect.top) + "px";

  const mRect = marker.getBoundingClientRect();
  const lineHeight = parseFloat(cs.lineHeight) || parseFloat(cs.fontSize) * 1.4;
  popupPos.value = {
    top: (mRect.top - parentRect.top) + lineHeight + 2 - el.scrollTop,
    left: (mRect.left - parentRect.left) - el.scrollLeft,
  };

  parent.removeChild(mirror);
}

function insertMention(u: UserSearchItem) {
  const el = textarea.value;
  if (!el) return;
  const text = value.value;
  const tag = u.username || u.email.split("@")[0];
  const before = text.slice(0, popupStart.value);
  const afterCaret = el.selectionStart || 0;
  const after = text.slice(afterCaret);
  const replacement = `@${tag} `;
  const newText = before + replacement + after;
  emit("update:modelValue", newText);
  emit("mention", u);
  popupOpen.value = false;
  results.value = [];
  nextTick(() => {
    el.focus();
    const newCaret = before.length + replacement.length;
    el.setSelectionRange(newCaret, newCaret);
  });
}

function onKeydown(e: KeyboardEvent) {
  if (!popupOpen.value || results.value.length === 0) return;
  if (e.key === "ArrowDown") { e.preventDefault(); highlight.value = (highlight.value + 1) % results.value.length; }
  else if (e.key === "ArrowUp") { e.preventDefault(); highlight.value = (highlight.value - 1 + results.value.length) % results.value.length; }
  else if (e.key === "Enter" || e.key === "Tab") {
    if (highlight.value >= 0) {
      e.preventDefault();
      insertMention(results.value[highlight.value]);
    }
  }
  else if (e.key === "Escape") { popupOpen.value = false; }
}

function onBlur() {
  // Slight delay so a mousedown on the popup registers before close
  window.setTimeout(() => { popupOpen.value = false; }, 150);
}

onBeforeUnmount(() => { if (debounceTimer) clearTimeout(debounceTimer); });
</script>

<template>
  <div class="mt-root">
    <textarea
      ref="textarea"
      :value="value"
      :rows="rows || 3"
      :placeholder="placeholder"
      :disabled="disabled"
      @input="onInput"
      @keydown="onKeydown"
      @blur="onBlur"
    ></textarea>
    <div v-if="popupOpen && results.length > 0"
         class="mt-popup"
         :style="{ top: popupPos.top + 'px', left: popupPos.left + 'px' }">
      <button
        v-for="(u, i) in results"
        :key="u.id"
        type="button"
        class="mt-item"
        :class="{ active: i === highlight }"
        @mousedown.prevent="insertMention(u)"
        @mouseenter="highlight = i"
      >
        <span class="mt-avatar">{{ u.initials }}</span>
        <span class="mt-info">
          <span class="mt-name">{{ u.full_name || u.email }}</span>
          <span class="mt-email">{{ u.email }}</span>
        </span>
      </button>
    </div>
  </div>
</template>

<style scoped>
.mt-root { position: relative; width: 100%; flex: 1; min-width: 0; }
textarea {
  width: 100%;
  padding: 8px 10px;
  border: 0.5px solid #E5E7EB;
  border-radius: 7px;
  font-size: 12.5px;
  font-family: inherit;
  background: #FAFAFC;
  color: #1E2A4A;
  outline: none;
  resize: vertical;
}
textarea:focus { border-color: #7F77DD; background: white; }
textarea:disabled { opacity: 0.55; cursor: not-allowed; }

.mt-popup {
  position: absolute;
  background: white;
  border: 0.5px solid #E5E7EB;
  border-radius: 8px;
  box-shadow: 0 8px 24px rgba(15,23,60,.10);
  max-height: 280px; overflow-y: auto;
  z-index: 100;
  padding: 4px;
  min-width: 280px;
  margin-top: 4px;
}
.mt-item {
  display: flex; align-items: center; gap: 10px;
  width: 100%;
  padding: 7px 10px;
  border: none; border-radius: 6px;
  background: transparent;
  cursor: pointer; text-align: left; font-family: inherit;
}
.mt-item.active, .mt-item:hover { background: rgba(127,119,221,.10); }
.mt-avatar {
  width: 24px; height: 24px; border-radius: 50%;
  background: #7F77DD; color: white;
  display: inline-flex; align-items: center; justify-content: center;
  font-size: 10px; font-weight: 600; flex-shrink: 0;
}
.mt-info { display: flex; flex-direction: column; min-width: 0; }
.mt-name { font-size: 12px; color: #1E2A4A; font-weight: 500; }
.mt-email { font-size: 10px; color: #888780; font-family: ui-monospace, monospace; }
</style>
