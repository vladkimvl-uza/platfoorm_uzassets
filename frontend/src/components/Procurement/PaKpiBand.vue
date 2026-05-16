<template>
  <div class="pa-kpi-band" id="pa-kpi-band" ref="bandRef">
    <div
      class="kpi2 fin-shimmer"
      style="--kpi2-accent: #1D9E75; --kpi2-d: 0ms"
      @click="$emit('drill-leaders')"
    >
      <div class="kpi2-lbl">Компании-лидеры</div>
      <div class="kpi2-val">
        <span data-countup="" :data-cu-d="0">{{ kpis.clean_companies - aboveCount }}</span>
        <span class="kpi2-of">из {{ kpis.clean_companies }}</span>
      </div>
      <div class="kpi2-sub">отклонение ≤ 0%</div>
    </div>

    <div
      class="kpi2 fin-shimmer"
      style="--kpi2-accent: #EF9F27; --kpi2-d: 80ms"
      @click="$emit('drill-overpay')"
    >
      <div class="kpi2-lbl">Совокупная переплата</div>
      <div class="kpi2-val">
        <span data-countup="" :data-cu-d="2" data-cu-sep>{{ overpayShortValue }}</span>
        <span class="kpi2-unit">{{ overpayShortUnit }}</span>
      </div>
      <div class="kpi2-sub">по компаниям выше median</div>
    </div>

    <div
      class="kpi2 fin-shimmer"
      style="--kpi2-accent: #378ADD; --kpi2-d: 160ms"
      @click="$emit('drill-closures')"
    >
      <div class="kpi2-lbl">Чистых закупок</div>
      <div class="kpi2-val">
        <span data-countup="" :data-cu-d="0" data-cu-sep>{{ kpis.clean_closures }}</span>
        <span class="kpi2-of">из {{ kpis.total_closures }}</span>
      </div>
      <div class="kpi2-sub">после кластеризации цен</div>
    </div>

    <div
      class="kpi2 fin-shimmer"
      style="--kpi2-accent: #7F77DD; --kpi2-d: 240ms"
      @click="$emit('drill-above')"
    >
      <div class="kpi2-lbl">Компаний выше рынка</div>
      <div class="kpi2-val">
        <span data-countup="" :data-cu-d="0">{{ Math.round(kpis.above_market_pct) }}</span>
        <span class="kpi2-pct">%</span>
      </div>
      <div class="kpi2-sub">из {{ kpis.clean_companies || kpis.total_companies }} с benchmark</div>
    </div>
  </div>
</template>

<script setup lang="ts">
/**
 *
 * 4 cards with kpiCardIn staggered animations, shimmer accent line,
 * onclick → drill events.
 */
import { computed, ref } from "vue";
import { useCountUpScan } from "@/composables/useCountUp";
import type { CompanyRatingRow, ProcurementKpis } from "@/api/procurement_analysis";

const props = defineProps<{
  kpis: ProcurementKpis;
  rating: CompanyRatingRow[];
}>();

defineEmits<{
  (e: "drill-leaders"): void;
  (e: "drill-overpay"): void;
  (e: "drill-closures"): void;
  (e: "drill-above"): void;
}>();

const bandRef = ref<HTMLElement | null>(null);
useCountUpScan(bandRef, { baseDelay: 60 });

const aboveCount = computed(() => props.rating.filter((r) => r.company_deviation > 0).length);

const totalOverpay = computed(() => {
  return props.rating.reduce((s, r) => s + Math.max(0, r.sum_dev), 0);
});

const overpayShortValue = computed(() => {
  const v = totalOverpay.value;
  if (v >= 1e12) return (v / 1e12).toFixed(2);
  if (v >= 1e9) return (v / 1e9).toFixed(2);
  if (v >= 1e6) return (v / 1e6).toFixed(1);
  return v.toFixed(0);
});
const overpayShortUnit = computed(() => {
  const v = totalOverpay.value;
  if (v >= 1e12) return "трлн сум";
  if (v >= 1e9) return "млрд сум";
  if (v >= 1e6) return "млн сум";
  return "сум";
});
</script>

<style scoped>
.pa-kpi-band {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 12px;
}
@media (max-width: 1100px) { .pa-kpi-band { grid-template-columns: repeat(2, 1fr); } }

.kpi2 {
  background: #fff;
  border-radius: 12px;
  padding: 16px 18px;
  border: 1px solid rgba(15, 23, 60, .06);
  border-left: 3px solid var(--kpi2-accent);
  position: relative;
  overflow: hidden;
  cursor: pointer;
  animation: kpiCardIn .55s cubic-bezier(.34, 1.2, .64, 1) backwards;
  animation-delay: var(--kpi2-d, 0ms);
  transition: transform .15s, box-shadow .15s;
}

.kpi2:hover {
  transform: translateY(-2px);
  box-shadow: 0 8px 16px rgba(15, 23, 60, .06);
}

@keyframes kpiCardIn {
  from { opacity: 0; transform: translateY(8px); }
  to { opacity: 1; transform: translateY(0); }
}

.fin-shimmer::before {
  content: "";
  position: absolute;
  top: 0; bottom: 0; left: -3px;
  width: 3px;
  background: linear-gradient(to bottom, transparent, var(--kpi2-accent) 50%, transparent);
  animation: shimmer 3s ease-in-out infinite;
}

@keyframes shimmer {
  0%, 100% { opacity: .4; }
  50% { opacity: 1; }
}

.kpi2-lbl {
  font-size: 9.5px;
  font-weight: 600;
  letter-spacing: .07em;
  text-transform: uppercase;
  color: rgba(15, 23, 60, .55);
}

.kpi2-val {
  font-size: 28px;
  font-weight: 400;
  letter-spacing: -.025em;
  color: #1e2a4a;
  margin-top: 4px;
  font-feature-settings: 'tnum';
  display: flex;
  align-items: baseline;
  gap: 4px;
}

.kpi2-of {
  font-size: 13px;
  color: rgba(15, 23, 60, .45);
  font-weight: 500;
}

.kpi2-unit {
  font-size: 12px;
  color: rgba(15, 23, 60, .55);
  font-weight: 500;
}

.kpi2-pct {
  font-size: 22px;
  color: rgba(15, 23, 60, .35);
}

.kpi2-sub {
  font-size: 10.5px;
  color: rgba(15, 23, 60, .5);
  margin-top: 2px;
}
</style>
