<script setup lang="ts">
import { useI18n } from "@/composables/useI18n";
const { t } = useI18n();
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
    <span v-if="label" class="uza-seg-grp-l" :class="'is-' + tone">{{ t(label) }}</span>
    <div class="uza-seg" :class="[tone === 'dark' ? 'on-dark' : '', size === 'sm' ? 'is-sm' : '']" role="tablist">
      <button
        v-for="(o, i) in options"
        :key="String(o.value)"
        type="button"
        role="tab"
        class="uza-seg-btn"
        :class="{ on: modelValue === o.value }"
        :style="{ '--i': i }"
        :title="o.title || t(o.label)"
        :aria-selected="modelValue === o.value"
        @click="emit('update:modelValue', o.value)"
      >
        <span v-if="o.dot" class="uza-seg-dot" :style="{ background: o.dot }"></span>{{ t(o.label) }}
      </button>
    </div>
  </div>
</template>

<style scoped>
/* Трек и пилл берём из глобального uza-toggles.css (.uza-seg / .uza-seg-btn /
   .on-dark / .is-sm) — единый эталон переключателей (пурпурный градиент +
   glow + shimmer, 1:1 с финансовыми метрик-чипами). Здесь только обвязка
   группы (подпись) и семантическая точка, которых в эталоне нет. */
.uza-seg-grp { display: inline-flex; align-items: center; gap: 7px; }
.uza-seg-grp-l {
  font-size: 9px; font-weight: 700; text-transform: uppercase; letter-spacing: .06em; white-space: nowrap;
}
.uza-seg-grp-l.is-light { color: var(--t3, #94A3B8); }
.uza-seg-grp-l.is-dark  { color: rgba(255, 255, 255, .42); }

/* Точка-семантика (цвет передаётся inline); отступ — через gap кнопки. */
.uza-seg-dot { width: 6px; height: 6px; border-radius: 50%; display: inline-block; flex-shrink: 0; position: relative; z-index: 1; }
</style>
