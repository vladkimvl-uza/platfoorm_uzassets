<script setup lang="ts">
// ============================================================================
// Metric tabs (pill row) for the Financials dashboard.
//
// 4–6 tabs depending on standard + viewTab:
//   IFRS PL:    Выручка / Себестоимость / Вал.прибыль / Опер.прибыль / Чистая прибыль / EBITDA
//   IFRS SOFP:  Активы / Капитал / Обязательства / Долг / Денежные ср-ва
//   IFRS CF:    CFO / CFI / CFF / Дивиденды
//   NSBU PL:    Выручка / Валовая прибыль / EBITDA / Чистая прибыль
//   NSBU BS:    Итого активы / Обязательства / Собственный капитал / Денежные ср-ва / Долг
// ============================================================================

import type { MetricDef } from "./financialsHelpers";

const props = defineProps<{
  metrics: MetricDef[];
  active: string;
}>();

const emit = defineEmits<{
  (e: "update:active", v: string): void;
}>();
</script>

<template>
  <div class="fmt-row">
    <button v-for="(m, i) in metrics"
            :key="m.id"
            class="fmt-pill"
            :class="{ on: active === m.id }"
            :style="{ '--i': i }"
            @click="emit('update:active', m.id)">
      <span class="fmt-pill-txt">{{ m.label }}</span>
    </button>
  </div>
</template>

<style scoped>
.fmt-row {
  display: inline-flex;
  gap: 3px;
  flex-wrap: wrap;
  padding: 4px;
  margin: 4px 0;
  border-radius: 12px;
  background: linear-gradient(180deg, rgba(15, 23, 60, .05), rgba(15, 23, 60, .03));
  box-shadow: inset 0 1px 2px rgba(15, 23, 60, .06);
}

.fmt-pill {
  position: relative;
  overflow: hidden;
  background: transparent;
  border: none;
  color: var(--t2, #4B5468);
  padding: 5px 13px;
  border-radius: 8px;
  font-size: 11px;
  font-weight: 500;
  letter-spacing: 0.01em;
  cursor: pointer;
  font-family: inherit;
  transition: color .2s var(--ease-standard),
              background .2s var(--ease-standard),
              transform .25s cubic-bezier(.34, 1.4, .5, 1),
              box-shadow .2s var(--ease-standard);
  /* staggered mount-in */
  animation: fmtIn .45s var(--ease-standard) backwards;
  animation-delay: calc(var(--i, 0) * 45ms);
}
.fmt-pill-txt { position: relative; z-index: 1; }

@keyframes fmtIn {
  from { opacity: 0; transform: translateY(5px) scale(.96); }
  to   { opacity: 1; transform: translateY(0) scale(1); }
}

.fmt-pill:hover:not(.on) {
  background: rgba(127, 119, 221, .10);
  color: var(--t1, #1E2A4A);
  transform: translateY(-1px);
}
.fmt-pill:active:not(.on) { transform: translateY(0) scale(.97); }

/* Active — premium gradient + glow + shimmer sweep */
.fmt-pill.on {
  color: #fff;
  font-weight: 600;
  background: linear-gradient(135deg, #8B7FF0 0%, #6C5CE7 100%);
  box-shadow:
    0 3px 10px rgba(108, 92, 231, .38),
    0 1px 2px rgba(108, 92, 231, .3),
    inset 0 1px 0 rgba(255, 255, 255, .22);
  transform: translateY(-1px);
  animation: fmtPop .35s cubic-bezier(.34, 1.5, .5, 1);
}
@keyframes fmtPop {
  0%   { transform: translateY(-1px) scale(.9); }
  55%  { transform: translateY(-1px) scale(1.06); }
  100% { transform: translateY(-1px) scale(1); }
}
.fmt-pill.on::after {
  content: "";
  position: absolute;
  inset: 0;
  z-index: 0;
  background: linear-gradient(100deg, transparent 30%, rgba(255, 255, 255, .5) 50%, transparent 70%);
  transform: translateX(-130%);
  animation: fmtShimmer 2.8s ease-in-out infinite;
  animation-delay: .35s;
  pointer-events: none;
}
@keyframes fmtShimmer {
  0%        { transform: translateX(-130%); }
  55%, 100% { transform: translateX(130%); }
}
.fmt-pill.on:hover {
  box-shadow:
    0 5px 16px rgba(108, 92, 231, .5),
    inset 0 1px 0 rgba(255, 255, 255, .25);
  transform: translateY(-2px);
}

@media (prefers-reduced-motion: reduce) {
  .fmt-pill, .fmt-pill.on { animation: none; }
  .fmt-pill.on::after { animation: none; display: none; }
}
</style>
