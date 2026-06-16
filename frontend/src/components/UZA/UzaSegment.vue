<script setup lang="ts">
/**
 * UzaSegment — единый сегментированный фильтр-чип для всех дашбордов/карточек/виджетов.
 *
 * Один визуальный язык активного состояния (без разноцветья), опциональная
 * подпись группы, семантические точки. Работает на светлом и тёмном фоне (tone).
 *
 * Usage:
 *   <UzaSegment v-model="period" :options="[{value:'Y',label:'Год'},{value:'Q1',label:'Q1'}]" label="Период" />
 *   <UzaSegment v-model="lens" tone="dark"
 *     :options="[{value:'income',label:'Доходы',dot:'#1D9E75'},{value:'expenses',label:'Расходы',dot:'#EF9F27'}]" />
 */
type SegValue = string | number;
interface SegOption {
  value: SegValue;
  label: string;
  dot?: string;        // семантическая точка перед текстом
  title?: string;
}

withDefaults(defineProps<{
  modelValue: SegValue;
  options: SegOption[];
  label?: string;
  tone?: "light" | "dark";
  size?: "sm" | "md";
}>(), { tone: "light", size: "md" });

const emit = defineEmits<{ "update:modelValue": [SegValue] }>();
</script>

<template>
  <div class="uza-seg-grp">
    <span v-if="label" class="uza-seg-grp-l" :class="'is-' + tone">{{ label }}</span>
    <div class="uza-seg" :class="['is-' + tone, 'sz-' + size]" role="tablist">
      <button
        v-for="o in options"
        :key="String(o.value)"
        type="button"
        role="tab"
        :class="{ on: modelValue === o.value }"
        :title="o.title || o.label"
        :aria-selected="modelValue === o.value"
        @click="emit('update:modelValue', o.value)"
      >
        <span v-if="o.dot" class="uza-seg-dot" :style="{ background: o.dot }"></span>{{ o.label }}
      </button>
    </div>
  </div>
</template>

<style scoped>
.uza-seg-grp { display: inline-flex; align-items: center; gap: 7px; }
.uza-seg-grp-l {
  font-size: 9px; font-weight: 700; text-transform: uppercase; letter-spacing: .06em; white-space: nowrap;
}
.uza-seg-grp-l.is-light { color: var(--t3, #94A3B8); }
.uza-seg-grp-l.is-dark  { color: rgba(255, 255, 255, .42); }

.uza-seg {
  display: inline-flex; border-radius: 8px; padding: 2px; gap: 0;
}
.uza-seg button {
  display: inline-flex; align-items: center;
  background: transparent; border: none;
  font-size: 11px; font-weight: 600;
  padding: 5px 12px; border-radius: 6px;
  cursor: pointer; font-family: inherit; white-space: nowrap;
  font-variant-numeric: tabular-nums;
  transition: background .18s, color .18s;
}
.uza-seg.sz-sm button { padding: 4px 10px; font-size: 10.5px; }

/* Точка-семантика (цвет передаётся inline) */
.uza-seg-dot { width: 6px; height: 6px; border-radius: 50%; display: inline-block; margin-right: 6px; flex-shrink: 0; }

/* ── Светлый фон (карточки/виджеты на белом) ── */
.uza-seg.is-light { background: var(--bg2, #F1F0F7); border: 1px solid var(--line, rgba(30,42,74,.06)); }
.uza-seg.is-light button { color: var(--t2, #6B6880); }
.uza-seg.is-light button:hover { color: var(--t1, #1A1730); }
.uza-seg.is-light button.on {
  background: var(--bg1, #fff); color: var(--p-deep, #534AB7);
  box-shadow: 0 1px 4px rgba(0, 0, 0, .08); font-weight: 600;
}

/* ── Тёмный фон (навы-топбары) ── */
.uza-seg.is-dark { background: rgba(255, 255, 255, .10); border: 1px solid rgba(255, 255, 255, .08); }
.uza-seg.is-dark button { color: rgba(255, 255, 255, .62); }
.uza-seg.is-dark button:hover { color: #fff; }
.uza-seg.is-dark button.on {
  background: rgba(255, 255, 255, .22); color: #fff;
  box-shadow: 0 1px 3px rgba(0, 0, 0, .18);
}
</style>
