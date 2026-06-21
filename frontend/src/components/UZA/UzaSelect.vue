<script setup lang="ts">
/**
 * UzaSelect — единый выпадающий список (для годов и прочих длинных наборов).
 * Парный к UzaSegment: где значений много (годы) — дропдаун вместо чипов.
 * Светлый/тёмный фон (tone), опциональная подпись группы и префикс ("FY ").
 *
 * A11y: паттерн WAI-ARIA «кнопка + listbox». Триггер — aria-haspopup=listbox +
 * aria-expanded; меню — role=listbox + aria-activedescendant; пункты — role=option
 * + aria-selected. Клавиатура: ↑/↓ перемещение, Home/End края, Enter/Space выбор,
 * Esc закрыть+вернуть фокус, Tab закрыть, type-ahead (печать буквы → прыжок).
 */
import { computed, getCurrentInstance, nextTick, onBeforeUnmount, onMounted, ref, watch } from "vue";

type SelValue = string | number;
interface SelOption { value: SelValue; label: string }

const props = withDefaults(defineProps<{
  modelValue: SelValue;
  options: SelOption[];
  label?: string;
  prefix?: string;
  tone?: "light" | "dark";
}>(), { tone: "light", prefix: "" });

const emit = defineEmits<{ "update:modelValue": [SelValue] }>();

const uid = getCurrentInstance()?.uid ?? 0;
const listId = `uza-sel-list-${uid}`;
const optId = (i: number) => `uza-sel-opt-${uid}-${i}`;

const open = ref(false);
const activeIndex = ref(-1);
const el = ref<HTMLElement | null>(null);
const btn = ref<HTMLButtonElement | null>(null);
const listEl = ref<HTMLElement | null>(null);

const current = computed(() => props.options.find((o) => o.value === props.modelValue));
const currentIndex = computed(() => props.options.findIndex((o) => o.value === props.modelValue));

// type-ahead buffer
let typeBuf = "";
let typeTimer: ReturnType<typeof setTimeout> | null = null;

function openMenu(toIndex?: number) {
  open.value = true;
  activeIndex.value = toIndex ?? (currentIndex.value >= 0 ? currentIndex.value : 0);
  nextTick(() => listEl.value?.focus());
}

function closeMenu(focusBtn = true) {
  open.value = false;
  activeIndex.value = -1;
  if (focusBtn) nextTick(() => btn.value?.focus());
}

function pick(v: SelValue, focusBtn = true) {
  emit("update:modelValue", v);
  closeMenu(focusBtn);
}

function move(delta: number) {
  const n = props.options.length;
  if (!n) return;
  let i = activeIndex.value;
  i = i < 0 ? (delta > 0 ? 0 : n - 1) : (i + delta + n) % n;
  activeIndex.value = i;
}

function onBtnKeydown(e: KeyboardEvent) {
  if (e.key === "ArrowDown" || e.key === "Enter" || e.key === " ") {
    e.preventDefault();
    openMenu();
  } else if (e.key === "ArrowUp") {
    e.preventDefault();
    openMenu(currentIndex.value >= 0 ? currentIndex.value : props.options.length - 1);
  }
}

function onListKeydown(e: KeyboardEvent) {
  switch (e.key) {
    case "ArrowDown": e.preventDefault(); move(1); break;
    case "ArrowUp": e.preventDefault(); move(-1); break;
    case "Home": e.preventDefault(); activeIndex.value = 0; break;
    case "End": e.preventDefault(); activeIndex.value = props.options.length - 1; break;
    case "Enter":
    case " ":
      e.preventDefault();
      if (activeIndex.value >= 0) pick(props.options[activeIndex.value].value);
      break;
    case "Escape": e.preventDefault(); closeMenu(); break;
    case "Tab": closeMenu(false); break;
    default:
      if (e.key.length === 1) onTypeahead(e.key);
  }
}

function onTypeahead(ch: string) {
  typeBuf += ch.toLowerCase();
  if (typeTimer) clearTimeout(typeTimer);
  typeTimer = setTimeout(() => { typeBuf = ""; }, 600);
  const idx = props.options.findIndex((o) =>
    `${props.prefix}${o.label}`.toLowerCase().startsWith(typeBuf),
  );
  if (idx >= 0) activeIndex.value = idx;
}

// keep highlighted option in view for long lists
watch(activeIndex, (i) => {
  if (i < 0 || !open.value) return;
  nextTick(() => {
    const node = listEl.value?.querySelector<HTMLElement>(`#${CSS.escape(optId(i))}`);
    node?.scrollIntoView({ block: "nearest" });
  });
});

function onDoc(e: MouseEvent) {
  if (el.value && !el.value.contains(e.target as Node)) closeMenu(false);
}
onMounted(() => document.addEventListener("click", onDoc));
onBeforeUnmount(() => {
  document.removeEventListener("click", onDoc);
  if (typeTimer) clearTimeout(typeTimer);
});
</script>

<template>
  <div class="uza-seg-grp">
    <span v-if="label" :id="`uza-sel-lbl-${uid}`" class="uza-sel-l" :class="'is-' + tone">{{ label }}</span>
    <div ref="el" class="uza-sel" :class="'is-' + tone">
      <button
        ref="btn"
        type="button"
        class="uza-sel-btn"
        :aria-haspopup="'listbox'"
        :aria-expanded="open"
        :aria-controls="listId"
        :aria-labelledby="label ? `uza-sel-lbl-${uid}` : undefined"
        :aria-label="label ? undefined : 'Выбор значения'"
        @click.stop="open ? closeMenu(false) : openMenu()"
        @keydown="onBtnKeydown"
      >
        <span class="uza-sel-val">{{ prefix }}{{ current?.label ?? modelValue }}</span>
        <svg class="uza-sel-chev" :class="{ open }" width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" aria-hidden="true"><polyline points="6 9 12 15 18 9"/></svg>
      </button>
      <Transition name="uza-sel-fade">
        <ul
          v-if="open"
          :id="listId"
          ref="listEl"
          class="uza-sel-menu"
          role="listbox"
          tabindex="-1"
          :aria-labelledby="label ? `uza-sel-lbl-${uid}` : undefined"
          :aria-activedescendant="activeIndex >= 0 ? optId(activeIndex) : undefined"
          @keydown="onListKeydown"
        >
          <li
            v-for="(o, i) in options"
            :id="optId(i)"
            :key="String(o.value)"
            role="option"
            :aria-selected="o.value === modelValue"
            :class="{ on: o.value === modelValue, hl: i === activeIndex }"
            @click="pick(o.value)"
            @mousemove="activeIndex = i"
          >{{ prefix }}{{ o.label }}</li>
        </ul>
      </Transition>
    </div>
  </div>
</template>

<style scoped>
.uza-seg-grp { display: inline-flex; align-items: center; gap: 7px; }
.uza-sel-l {
  font-size: 9px; font-weight: 700; text-transform: uppercase; letter-spacing: .06em; white-space: nowrap;
}
.uza-sel-l.is-light { color: var(--t3, #94A3B8); }
.uza-sel-l.is-dark  { color: rgba(255, 255, 255, .42); }

.uza-sel { position: relative; }
.uza-sel-btn {
  display: inline-flex; align-items: center; gap: 7px;
  padding: 6px 11px; border-radius: 8px;
  font-size: 11px; font-weight: 600; cursor: pointer; font-family: inherit;
  font-variant-numeric: tabular-nums; white-space: nowrap;
  transition: background .16s, border-color .16s;
}
.uza-sel-chev { transition: transform .18s; flex-shrink: 0; }
.uza-sel-chev.open { transform: rotate(180deg); }

.uza-sel-menu {
  position: absolute; right: 0; top: calc(100% + 5px); z-index: 60;
  min-width: 100%; padding: 4px; border-radius: 9px; margin: 0;
  list-style: none; max-height: 280px; overflow-y: auto;
  display: flex; flex-direction: column; gap: 1px;
}
.uza-sel-menu:focus-visible { outline: 2px solid var(--p, #7c6ff7); outline-offset: 2px; }
.uza-sel-menu li {
  text-align: left; padding: 7px 12px; border: none; border-radius: 6px;
  font-size: 11.5px; font-weight: 600; cursor: pointer; font-family: inherit;
  background: transparent; white-space: nowrap; font-variant-numeric: tabular-nums;
  transition: background .12s;
}

/* ── Светлый ── */
.uza-sel.is-light .uza-sel-btn { background: var(--bg2, #F1F0F7); border: 1px solid var(--line, rgba(30,42,74,.06)); color: var(--t1, #1A1730); }
.uza-sel.is-light .uza-sel-btn:hover { background: #E9E7F2; }
.uza-sel.is-light .uza-sel-menu { background: var(--bg1, #fff); box-shadow: 0 10px 30px rgba(15,23,60,.16); border: 1px solid var(--line, rgba(30,42,74,.06)); }
.uza-sel.is-light .uza-sel-menu li { color: var(--t2, #5F5E5A); }
.uza-sel.is-light .uza-sel-menu li.hl { background: rgba(124,111,247,.08); color: var(--p-deep, #534AB7); }
.uza-sel.is-light .uza-sel-menu li.on { background: rgba(124,111,247,.12); color: var(--p-deep, #534AB7); }

/* ── Тёмный ── */
.uza-sel.is-dark .uza-sel-btn { background: rgba(255,255,255,.10); border: 1px solid rgba(255,255,255,.10); color: #fff; }
.uza-sel.is-dark .uza-sel-btn:hover { background: rgba(255,255,255,.18); }
.uza-sel.is-dark .uza-sel-menu { background: #1B2344; box-shadow: 0 12px 32px rgba(0,0,0,.4); border: 1px solid rgba(255,255,255,.1); }
.uza-sel.is-dark .uza-sel-menu li { color: rgba(255,255,255,.7); }
.uza-sel.is-dark .uza-sel-menu li.hl { background: rgba(255,255,255,.1); color: #fff; }
.uza-sel.is-dark .uza-sel-menu li.on { background: rgba(127,119,221,.45); color: #fff; }

.uza-sel-fade-enter-active, .uza-sel-fade-leave-active { transition: opacity .15s, transform .15s; }
.uza-sel-fade-enter-from, .uza-sel-fade-leave-to { opacity: 0; transform: translateY(-4px); }
</style>
