<script setup lang="ts">
/**
 * UzaSelect — единый выпадающий список (для годов и прочих длинных наборов).
 * Парный к UzaSegment: где значений много (годы) — дропдаун вместо чипов.
 * Светлый/тёмный фон (tone), опциональная подпись группы и префикс ("FY ").
 */
import { computed, onBeforeUnmount, onMounted, ref } from "vue";

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

const open = ref(false);
const el = ref<HTMLElement | null>(null);
const current = computed(() => props.options.find((o) => o.value === props.modelValue));

function pick(v: SelValue) {
  emit("update:modelValue", v);
  open.value = false;
}
function onDoc(e: MouseEvent) {
  if (el.value && !el.value.contains(e.target as Node)) open.value = false;
}
onMounted(() => document.addEventListener("click", onDoc));
onBeforeUnmount(() => document.removeEventListener("click", onDoc));
</script>

<template>
  <div class="uza-seg-grp">
    <span v-if="label" class="uza-sel-l" :class="'is-' + tone">{{ label }}</span>
    <div ref="el" class="uza-sel" :class="'is-' + tone">
      <button type="button" class="uza-sel-btn" @click.stop="open = !open">
        <span class="uza-sel-val">{{ prefix }}{{ current?.label ?? modelValue }}</span>
        <svg class="uza-sel-chev" :class="{ open }" width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4"><polyline points="6 9 12 15 18 9"/></svg>
      </button>
      <Transition name="uza-sel-fade">
        <div v-if="open" class="uza-sel-menu">
          <button
            v-for="o in options"
            :key="String(o.value)"
            type="button"
            :class="{ on: o.value === modelValue }"
            @click="pick(o.value)"
          >{{ prefix }}{{ o.label }}</button>
        </div>
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
  min-width: 100%; padding: 4px; border-radius: 9px;
  display: flex; flex-direction: column; gap: 1px;
}
.uza-sel-menu button {
  text-align: left; padding: 7px 12px; border: none; border-radius: 6px;
  font-size: 11.5px; font-weight: 600; cursor: pointer; font-family: inherit;
  background: transparent; white-space: nowrap; font-variant-numeric: tabular-nums;
  transition: background .12s;
}

/* ── Светлый ── */
.uza-sel.is-light .uza-sel-btn { background: var(--bg2, #F1F0F7); border: 1px solid var(--line, rgba(30,42,74,.06)); color: var(--t1, #1A1730); }
.uza-sel.is-light .uza-sel-btn:hover { background: #E9E7F2; }
.uza-sel.is-light .uza-sel-menu { background: var(--bg1, #fff); box-shadow: 0 10px 30px rgba(15,23,60,.16); border: 1px solid var(--line, rgba(30,42,74,.06)); }
.uza-sel.is-light .uza-sel-menu button { color: var(--t2, #5F5E5A); }
.uza-sel.is-light .uza-sel-menu button:hover { background: rgba(124,111,247,.08); color: var(--p-deep, #534AB7); }
.uza-sel.is-light .uza-sel-menu button.on { background: rgba(124,111,247,.12); color: var(--p-deep, #534AB7); }

/* ── Тёмный ── */
.uza-sel.is-dark .uza-sel-btn { background: rgba(255,255,255,.10); border: 1px solid rgba(255,255,255,.10); color: #fff; }
.uza-sel.is-dark .uza-sel-btn:hover { background: rgba(255,255,255,.18); }
.uza-sel.is-dark .uza-sel-menu { background: #1B2344; box-shadow: 0 12px 32px rgba(0,0,0,.4); border: 1px solid rgba(255,255,255,.1); }
.uza-sel.is-dark .uza-sel-menu button { color: rgba(255,255,255,.7); }
.uza-sel.is-dark .uza-sel-menu button:hover { background: rgba(255,255,255,.1); color: #fff; }
.uza-sel.is-dark .uza-sel-menu button.on { background: rgba(127,119,221,.45); color: #fff; }

.uza-sel-fade-enter-active, .uza-sel-fade-leave-active { transition: opacity .15s, transform .15s; }
.uza-sel-fade-enter-from, .uza-sel-fade-leave-to { opacity: 0; transform: translateY(-4px); }
</style>
