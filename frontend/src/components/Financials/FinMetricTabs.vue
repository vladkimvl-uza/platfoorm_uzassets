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
    <button v-for="m in metrics"
            :key="m.id"
            class="fmt-pill"
            :class="{ on: active === m.id }"
            @click="emit('update:active', m.id)">
      {{ m.label }}
    </button>
  </div>
</template>

<style scoped>
.fmt-row {
  display: inline-flex;
  gap: 6px;
  flex-wrap: wrap;
  padding: 8px 0 4px;
}
.fmt-pill {
  background: var(--bg3, #F1F5F9);
  border: none;
  color: var(--t2, #4B5468);
  padding: 4px 11px;
  border-radius: 7px;
  font-size: 10.5px;
  font-weight: 500;
  cursor: pointer;
  transition: all .15s cubic-bezier(.34, 1.2, .64, 1);
  font-family: inherit;
  letter-spacing: 0.01em;
}
.fmt-pill:hover {
  background: rgba(127, 119, 221, 0.10);
  color: var(--t1, #1E2A4A);
  transform: translateY(-1px);
}
.fmt-pill.on {
  background: #7F77DD;
  color: #fff;
  box-shadow: 0 2px 6px rgba(127, 119, 221, 0.25);
}
.fmt-pill.on:hover {
  background: #6F66C8;
  transform: translateY(-1px);
}
</style>
