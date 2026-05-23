<template>
  <div class="pa-kpi-band" ref="bandRef">
    <!-- KPI #1: Чистая позиция портфеля (net = savings − overpay) -->
    <div
      class="kpi2 fin-shimmer"
      :style="{ '--kpi2-accent': netAccent, '--kpi2-d': '0ms' }"
      title="Σ(экономия) − Σ(переплата) по компаниям с benchmark. Зелёный — портфель экономит; красный — переплачивает."
      @click="$emit('drill-netpos')"
    >
      <div class="kpi2-lbl">Чистая позиция портфеля</div>
      <div class="kpi2-val" :style="{ color: netAccent }">
        <span class="kpi2-sign">{{ netSign }}</span>
        <span data-countup="" :data-cu-d="2" data-cu-sep>{{ netShortValue }}</span>
        <span class="kpi2-unit">{{ netShortUnit }}</span>
      </div>
      <div class="kpi2-sub">{{ netPosSubLabel }}</div>
    </div>

    <!-- KPI #2: Потенциал экономии (sum of price max-median × volume) -->
    <div
      class="kpi2 fin-shimmer"
      :style="{ '--kpi2-accent': '#EF9F27', '--kpi2-d': '80ms' }"
      title="Сколько портфель мог бы сэкономить, если бы все купили по minimum price per cluster"
      @click="$emit('drill-overpay')"
    >
      <div class="kpi2-lbl">Потенциал экономии</div>
      <div class="kpi2-val" style="color:#EF9F27">
        <span data-countup="" :data-cu-d="2" data-cu-sep>{{ savingsPotentialShort }}</span>
        <span class="kpi2-unit">{{ savingsPotentialUnit }}</span>
      </div>
      <div class="kpi2-sub">если все закупят по минимуму</div>
    </div>

    <!-- KPI #3: Красных закупок (deviation ≥ +10% over median) -->
    <div
      class="kpi2 fin-shimmer"
      :style="{ '--kpi2-accent': '#E24B4A', '--kpi2-d': '160ms' }"
      title="Количество закупок где компания переплатила ≥10% к median по той же категории/товару"
      @click="$emit('drill-red')"
    >
      <div class="kpi2-lbl">Красных закупок</div>
      <div class="kpi2-val" style="color:#E24B4A">
        <span data-countup="" :data-cu-d="0" data-cu-sep>{{ redCount }}</span>
        <span class="kpi2-of">из {{ kpis.clean_closures || kpis.total_closures }}</span>
      </div>
      <div class="kpi2-sub">отклонение ≥ +10% от median</div>
    </div>

    <!-- KPI #4: Компаний выше рынка -->
    <div
      class="kpi2 fin-shimmer"
      :style="{ '--kpi2-accent': '#7F77DD', '--kpi2-d': '240ms' }"
      title="Доля компаний у которых средневзвешенное отклонение > 0% (overpaid в average)"
      @click="$emit('drill-above')"
    >
      <div class="kpi2-lbl">Компаний выше рынка</div>
      <div class="kpi2-val" style="color:#7F77DD">
        <span data-countup="" :data-cu-d="0">{{ Math.round(kpis.above_market_pct) }}</span>
        <span class="kpi2-pct">%</span>
      </div>
      <div class="kpi2-sub">из {{ kpis.clean_companies || kpis.total_companies }} с benchmark</div>
    </div>
  </div>
</template>

<script setup lang="ts">
/**
 * 4 cards with kpiCardIn 3-stage bounce (delay 0/80/160/240ms),
 * shimmer accent line per --kpi2-accent, click → drill events.
 *
 *   1. Чистая позиция — net economy (signed, green/red)
 *   2. Потенциал экономии — sum of price-spread × volume potential
 *   3. Красных закупок — count(deviation ≥ +10%)
 *   4. Компаний выше рынка — % companies with avg dev > 0
 */
import { computed, ref } from "vue";
import { useCountUpScan } from "@/composables/useCountUp";
import type { CompanyRatingRow, ProcurementKpis } from "@/api/procurement_analysis";

const props = defineProps<{
  kpis: ProcurementKpis;
  rating: CompanyRatingRow[];
}>();

defineEmits<{
  (e: "drill-netpos"): void;
  (e: "drill-overpay"): void;
  (e: "drill-red"): void;
  (e: "drill-above"): void;
}>();

const bandRef = ref<HTMLElement | null>(null);
useCountUpScan(bandRef, { baseDelay: 60 });

/* ─── 1. Net portfolio position ───────────────────────────────── */
const netPosUzs = computed(() => {
  // Negate to convention "net economy" = -Σ(overpay − savings)
  // sum_dev > 0 means overpaid; sum_dev < 0 means saved
  let s = 0;
  for (const r of props.rating) s += Number(r.sum_dev) || 0;
  return -s;  // positive = saved overall; negative = overpaid overall
});
const netAccent = computed(() => (netPosUzs.value >= 0 ? "#1D9E75" : "#E24B4A"));
const netSign = computed(() => (netPosUzs.value === 0 ? "" : netPosUzs.value > 0 ? "−" : "+"));
const netShortValue = computed(() => {
  const v = Math.abs(netPosUzs.value);
  if (v >= 1e12) return (v / 1e12).toFixed(2);
  if (v >= 1e9) return (v / 1e9).toFixed(2);
  if (v >= 1e6) return (v / 1e6).toFixed(1);
  return v.toFixed(0);
});
const netShortUnit = computed(() => {
  const v = Math.abs(netPosUzs.value);
  if (v >= 1e12) return "трлн сум";
  if (v >= 1e9) return "млрд сум";
  if (v >= 1e6) return "млн сум";
  return "сум";
});
const netPosSubLabel = computed(() =>
  netPosUzs.value >= 0 ? "экономия по портфелю" : "переплата по портфелю",
);

/* ─── 2. Savings potential ─────────────────────────────────────── */
const savingsPotentialUzs = computed(() => {
  // Best proxy from rating[]: для каждой company где sum_dev > 0 (overpaid)
  // — это и есть potential savings если бы все купили по min price per cluster.
  // но product-level данные тут нет — используем agg.kpis.total_overpay_uzs.
  return Number(props.kpis.total_overpay_uzs) || 0;
});
const savingsPotentialShort = computed(() => {
  const v = savingsPotentialUzs.value;
  if (v >= 1e12) return (v / 1e12).toFixed(2);
  if (v >= 1e9) return (v / 1e9).toFixed(2);
  if (v >= 1e6) return (v / 1e6).toFixed(1);
  return v.toFixed(0);
});
const savingsPotentialUnit = computed(() => {
  const v = savingsPotentialUzs.value;
  if (v >= 1e12) return "трлн сум";
  if (v >= 1e9) return "млрд сум";
  if (v >= 1e6) return "млн сум";
  return "сум";
});

/* ─── 3. Red closures count (deviation ≥ +10%) ─────────────────── */
const redCount = computed(() => {
  // Sum of `above_count` per company — это закупки с dev ≥ +10% к median.
  let n = 0;
  for (const r of props.rating) n += Number(r.above_count) || 0;
  return n;
});
</script>

<style scoped>
.pa-kpi-band {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 10px;
}
@media (max-width: 1100px) { .pa-kpi-band { grid-template-columns: repeat(2, 1fr); } }

.kpi2 {
  background: #fff;
  border-radius: 12px;
  padding: 14px 16px 12px;
  border: 1px solid rgba(15, 23, 60, .06);
  position: relative;
  overflow: hidden;
  cursor: pointer;
  animation: kpiCardIn .55s cubic-bezier(.34, 1.2, .64, 1) backwards;
  animation-delay: var(--kpi2-d, 0ms);
  transition: transform .18s, box-shadow .18s;
}
.kpi2:hover {
  transform: translateY(-2px);
  box-shadow: 0 8px 22px rgba(15, 23, 60, .08);
}

@keyframes kpiCardIn {
  0%   { opacity: 0; transform: translateY(14px) scale(.97); }
  60%  { opacity: 1; transform: translateY(-2px) scale(1.01); }
  100% { opacity: 1; transform: translateY(0)   scale(1); }
}

/* Top accent stripe (replaces left shimmer of older Vue version — matches
.fin-shimmer::before {
  content: "";
  position: absolute;
  top: 0; left: 0; right: 0;
  height: 3px;
  background: var(--kpi2-accent);
  opacity: .9;
  transform-origin: left center;
  animation: kpiStripeIn .8s cubic-bezier(.34, 1.2, .64, 1) var(--kpi2-d, 0ms) both;
}
.fin-shimmer::after {
  content: "";
  position: absolute;
  top: 0; left: 0;
  height: 3px;
  width: 36%;
  background: linear-gradient(90deg, transparent, rgba(255, 255, 255, .85), transparent);
  animation: kpiSweep 5.5s cubic-bezier(.34, 1.2, .64, 1) infinite;
  animation-delay: 1.2s;
  pointer-events: none;
}
@keyframes kpiStripeIn {
  from { transform: scaleX(0); opacity: 0; }
  to   { transform: scaleX(1); opacity: .9; }
}
@keyframes kpiSweep {
  0%   { transform: translateX(-100%); }
  60%  { transform: translateX(280%); }
  100% { transform: translateX(280%); }
}

.kpi2-lbl {
  font-size: 10px;
  font-weight: 500;
  letter-spacing: .07em;
  text-transform: uppercase;
  color: rgba(15, 23, 60, .55);
}

.kpi2-val {
  font-size: 26px;
  font-weight: 400;
  letter-spacing: -.025em;
  color: #1e2a4a;
  margin-top: 6px;
  font-feature-settings: 'tnum';
  display: flex;
  align-items: baseline;
  gap: 4px;
  line-height: 1.1;
}
.kpi2-sign { font-size: 22px; font-weight: 500; opacity: .85; }

.kpi2-of {
  font-size: 12px;
  color: rgba(15, 23, 60, .45);
  font-weight: 500;
  margin-left: 2px;
}

.kpi2-unit {
  font-size: 11.5px;
  color: rgba(15, 23, 60, .55);
  font-weight: 500;
  margin-left: 2px;
}

.kpi2-pct {
  font-size: 20px;
  color: rgba(15, 23, 60, .35);
  margin-left: 1px;
}

.kpi2-sub {
  font-size: 10.5px;
  color: rgba(15, 23, 60, .5);
  margin-top: 4px;
}
</style>
