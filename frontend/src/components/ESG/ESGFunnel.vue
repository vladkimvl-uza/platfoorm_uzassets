<script setup lang="ts">
/**
 * ESGFunnel — горизонтальная воронка этапов (климат 4 / риски 3).
 * Бары убывающей ширины (passed_N / total), премиум-заливка с анимацией входа.
 * Данные приходят из heatmap (climate_funnel / risk_funnel) — без бэкенда.
 */
import { computed } from "vue";

const props = defineProps<{
  title: string;
  hint?: string;
  stages: { label: string; count: number }[];
  total: number;
  scheme: "climate" | "risk";
}>();
const emit = defineEmits<{ (e: "stage-click", index: number): void }>();

const SCHEMES: Record<string, string[]> = {
  climate: ["#C7E9FF", "#7FC8E8", "#4FB89A", "#1D9E75"],
  risk: ["#D9D4FB", "#9D92EE", "#6C5CE7"],
};
const colors = computed(() => SCHEMES[props.scheme] || SCHEMES.climate);
function pct(n: number): number { return props.total ? Math.round((n / props.total) * 100) : 0; }
</script>

<template>
  <div class="fn">
    <div class="fn-h">
      <span class="fn-t">{{ title }}</span>
      <span v-if="hint" class="fn-hint">{{ hint }}</span>
    </div>
    <div class="fn-body">
      <div v-for="(s, i) in stages" :key="i" class="fn-row" role="button" tabindex="0"
           :title="`Показать компании на стадии: ${s.label}`"
           @click="emit('stage-click', i)" @keydown.enter="emit('stage-click', i)">
        <div class="fn-lbl"><span class="fn-no" :style="{ background: colors[i] || colors[colors.length - 1] }">{{ i + 1 }}</span>{{ s.label }}</div>
        <div class="fn-track">
          <div class="fn-bar" :style="{ width: Math.max(pct(s.count), 4) + '%', background: colors[i] || colors[colors.length - 1], '--d': (i * 90) + 'ms' }">
            <span class="fn-cnt">{{ s.count }}</span>
          </div>
        </div>
        <div class="fn-pct">{{ pct(s.count) }}%</div>
      </div>
    </div>
    <div class="fn-foot">из {{ total }} компаний</div>
  </div>
</template>

<style scoped>
.fn { background: var(--bg1, #fff); border: 1px solid rgba(0,0,0,.06); border-radius: 14px; padding: 14px 16px 12px; display: flex; flex-direction: column; }
.fn-h { display: flex; align-items: baseline; justify-content: space-between; gap: 8px; margin-bottom: 12px; }
.fn-t { font-size: 12px; font-weight: 700; text-transform: uppercase; letter-spacing: .04em; color: var(--t1, #1E2A4A); }
.fn-hint { font-size: 10px; color: var(--t3, #94A3B8); }
.fn-body { display: flex; flex-direction: column; gap: 9px; position: relative; }
/* Вертикальный «степпер»-рельс: визуально связывает шаги 1→N в единый процесс */
.fn-body::before { content: ''; position: absolute; left: 7.5px; top: 14px; bottom: 14px; width: 2px; background: #E4E2F0; border-radius: 1px; z-index: 0; }
.fn-row { display: grid; grid-template-columns: 1fr 1.3fr 34px; gap: 10px; align-items: center; cursor: pointer; padding: 3px 6px; margin: 0 -6px; border-radius: 8px; transition: background .14s; outline: none; }
.fn-row:hover, .fn-row:focus-visible { background: color-mix(in srgb, #7C6FF7 7%, transparent); }
.fn-lbl { display: flex; align-items: center; gap: 7px; font-size: 11px; color: var(--t2, #475569); line-height: 1.2; }
.fn-no { position: relative; z-index: 1; flex-shrink: 0; width: 17px; height: 17px; border-radius: 50%; display: inline-flex; align-items: center; justify-content: center; font-size: 9.5px; font-weight: 700; color: #fff; box-shadow: 0 0 0 2px #fff; }
.fn-track { height: 22px; background: #F1F0F7; border-radius: 6px; overflow: hidden; }
.fn-bar {
  height: 100%; border-radius: 6px; display: flex; align-items: center; justify-content: flex-end;
  padding: 0 8px; min-width: 22px;
  transform-origin: left center;
  animation: fnGrow .6s var(--ease-standard, cubic-bezier(.34,1.2,.64,1)) var(--d, 0ms) backwards;
}
@keyframes fnGrow { from { transform: scaleX(0); opacity: .4; } to { transform: scaleX(1); opacity: 1; } }
.fn-cnt { font-size: 11px; font-weight: 700; color: #15324a; font-feature-settings: 'tnum'; }
.fn-pct { font-size: 11px; font-weight: 600; color: var(--t3, #94A3B8); text-align: right; font-feature-settings: 'tnum'; }
.fn-foot { margin-top: 10px; font-size: 10px; color: var(--t3, #94A3B8); }

@media (min-width: 2200px) {
  .fn-t { font-size: 15px; }
  .fn-lbl { font-size: 14px; }
  .fn-no { width: 22px; height: 22px; font-size: 12px; }
  .fn-track { height: 30px; }
  .fn-cnt, .fn-pct { font-size: 14px; }
  .fn-foot { font-size: 13px; }
}
</style>
