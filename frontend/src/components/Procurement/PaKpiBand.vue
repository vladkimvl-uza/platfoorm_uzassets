<template>
  <div class="pa-kpi-band">
    <!-- KPI #1: Чистая позиция портфеля (savings − overpay) -->
    <div
      class="kpi2 fin-shimmer"
      :style="{ '--kpi2-accent': k1.accent, '--kpi2-d': '0ms' }"
      title="Σ(экономия) − Σ(переплата) по всем компаниям с benchmark. Зелёный — портфель экономит; красный — переплачивает."
      @click="$emit('drill-netpos')"
    >
      <div class="kpi2-lbl">Чистая позиция портфеля</div>
      <div class="kpi2-val" :style="{ color: k1.accent }">
        <span v-if="k1.sign" class="kpi2-sign">{{ k1.sign }}</span>
        <span>{{ k1.value }}</span>
        <span class="kpi2-unit">{{ k1.unit }}</span>
      </div>
      <div class="kpi2-sub">{{ k1.sub }}</div>
    </div>

    <!-- KPI #2: Потенциал экономии (Σ overpay) -->
    <div
      class="kpi2 fin-shimmer"
      :style="{ '--kpi2-accent': '#EF9F27', '--kpi2-d': '80ms' }"
      title="Σ всех переплат — сколько портфель сэкономил бы при закупке по medianу."
      @click="$emit('drill-overpay')"
    >
      <div class="kpi2-lbl">Потенциал экономии</div>
      <div class="kpi2-val" style="color:#EF9F27">
        <span>{{ k2.value }}</span>
        <span class="kpi2-unit">{{ k2.unit }}</span>
      </div>
      <div class="kpi2-sub">если все закупят по минимуму</div>
    </div>

    <!-- KPI #3: Красных закупок (deviation ≥ +10% over median) -->
    <div
      class="kpi2 fin-shimmer"
      :style="{ '--kpi2-accent': '#E24B4A', '--kpi2-d': '160ms' }"
      title="Закупки где dev ≥ +10% к median по той же категории/товару."
      @click="$emit('drill-red')"
    >
      <div class="kpi2-lbl">Красных закупок</div>
      <div class="kpi2-val" style="color:#E24B4A">
        <span>{{ k3.count }}</span>
        <span class="kpi2-of">из {{ k3.total }}</span>
      </div>
      <div class="kpi2-sub">отклонение ≥ +10% от median</div>
    </div>

    <!-- KPI #4: Компаний выше рынка -->
    <div
      class="kpi2 fin-shimmer"
      :style="{ '--kpi2-accent': '#7F77DD', '--kpi2-d': '240ms' }"
      title="Доля компаний у которых средневзвешенное отклонение > 0%."
      @click="$emit('drill-above')"
    >
      <div class="kpi2-lbl">Компаний выше рынка</div>
      <div class="kpi2-val" style="color:#7F77DD">
        <span>{{ k4.pct }}</span>
        <span class="kpi2-pct">%</span>
      </div>
      <div class="kpi2-sub">из {{ k4.total }} с benchmark</div>
    </div>
  </div>
</template>

<script setup lang="ts">
/**
 * PaKpiBand · legacy _paRenderKpiBand 1:1
 *
 * 4 KPI cards (одинаковая семантика что в легасие index.html):
 *   1. Чистая позиция = Σ savings − Σ overpay (signed)
 *   2. Потенциал экономии = Σ overpay (positive)
 *   3. Красных закупок = Σ(above_count) — сколько dev ≥ +10%
 *   4. Компаний выше рынка = count(co_deviation > 0) / total с benchmark
 *
 * Pack: defensive rewrite 2026-05-23 — все computed возвращают строку,
 * безопасный parse чисел, multiple fallbacks (rating.sum_overpay/_savings
 * → rating.sum_dev → kpis.total_overpay_uzs). Никаких countUp/анимаций
 * для текста — браузер просто рендерит computed value напрямую.
 */
import { computed } from "vue";
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

// ─── safe number parser ────────────────────────────────────────────
function n(v: unknown): number {
  if (v === null || v === undefined) return 0;
  const x = typeof v === "number" ? v : Number(v);
  return Number.isFinite(x) ? x : 0;
}

// Compact number formatter — auto-picks unit by magnitude.
function fmt(uzs: number, decimals = 2): { value: string; unit: string } {
  const v = Math.abs(uzs);
  if (v >= 1e12) return { value: (uzs / 1e12).toFixed(decimals), unit: "трлн сум" };
  if (v >= 1e9)  return { value: (uzs / 1e9 ).toFixed(decimals), unit: "млрд сум" };
  if (v >= 1e6)  return { value: (uzs / 1e6 ).toFixed(decimals === 2 ? 1 : decimals), unit: "млн сум" };
  if (v >= 1e3)  return { value: Math.round(uzs / 1e3).toString(), unit: "тыс. сум" };
  return { value: Math.round(uzs).toString(), unit: "сум" };
}

// ─── aggregate over rating array (with fallback to sum_dev) ────────
const totals = computed(() => {
  const rows: CompanyRatingRow[] = Array.isArray(props.rating) ? props.rating : [];
  let overpay = 0;
  let savings = 0;
  let redCount = 0;
  let aboveCount = 0;     // companies с avg deviation > 0
  let benchmarkCount = 0; // companies у которых есть какой-то benchmark
  for (const r of rows) {
    const ov = n((r as unknown as { sum_overpay?: unknown }).sum_overpay);
    const sv = n((r as unknown as { sum_savings?: unknown }).sum_savings);
    const dv = n((r as unknown as { sum_dev?:     unknown }).sum_dev);
    // Если backend дал sum_overpay/sum_savings раздельно — используем их.
    // Иначе берём signed sum_dev: положительное → overpay, отрицательное → savings.
    if (ov || sv) {
      overpay += ov;
      savings += sv;
    } else if (dv !== 0) {
      if (dv > 0) overpay += dv;
      else        savings += -dv;
    }
    redCount += n((r as unknown as { above_count?: unknown }).above_count);
    // co_deviation > 0 → company выше рынка
    const codev = n((r as unknown as { company_deviation?: unknown }).company_deviation);
    if (codev !== 0 || dv !== 0 || ov !== 0 || sv !== 0) {
      benchmarkCount++;
      if (codev > 0 || (codev === 0 && dv > 0)) aboveCount++;
    }
  }
  return { overpay, savings, redCount, aboveCount, benchmarkCount };
});

// ─── 1. Net portfolio position ─────────────────────────────────────
const k1 = computed(() => {
  const net = totals.value.savings - totals.value.overpay;  // signed: +saved, −overpaid
  const f = fmt(Math.abs(net));
  return {
    value: f.value,
    unit: f.unit,
    sign: net === 0 ? "" : net > 0 ? "−" : "+",  // "−" перед числом если экономия, "+" если переплата
    accent: net >= 0 ? "#1D9E75" : "#E24B4A",
    sub: net >= 0 ? "экономия по портфелю" : "переплата по портфелю",
  };
});

// ─── 2. Savings potential (sum of overpay) ─────────────────────────
const k2 = computed(() => {
  let sum = totals.value.overpay;
  // Fallback: backend kpis.total_overpay_uzs если rating пустой.
  if (sum === 0) sum = n(props.kpis?.total_overpay_uzs);
  return fmt(sum);
});

// ─── 3. Red closures count ─────────────────────────────────────────
const k3 = computed(() => ({
  count: totals.value.redCount.toLocaleString("ru-RU"),
  total: (n(props.kpis?.clean_closures) || n(props.kpis?.total_closures))
    .toLocaleString("ru-RU"),
}));

// ─── 4. Companies above market — % с positive avg deviation ────────
const k4 = computed(() => {
  // Предпочтение: backend kpis.above_market_pct (готовый процент).
  const pctBackend = n(props.kpis?.above_market_pct);
  let pct = pctBackend;
  // Fallback: считаем сами из rating.
  if (!pct && totals.value.benchmarkCount > 0) {
    pct = (totals.value.aboveCount / totals.value.benchmarkCount) * 100;
  }
  const total = n(props.kpis?.clean_companies) || n(props.kpis?.total_companies)
    || totals.value.benchmarkCount;
  return { pct: Math.round(pct).toString(), total: total.toString() };
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
  background: var(--bg1, #fff);
  border-radius: 12px;
  padding: 14px 16px 12px;
  border: 1px solid rgba(15, 23, 60, .06);
  position: relative;
  overflow: hidden;
  cursor: pointer;
  animation: kpiCardIn .55s var(--ease-standard) backwards;
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

.fin-shimmer::before {
  content: "";
  position: absolute;
  top: 0; left: 0; right: 0;
  height: 3px;
  background: var(--kpi2-accent);
  opacity: .9;
  transform-origin: left center;
  animation: kpiStripeIn .8s var(--ease-standard) var(--kpi2-d, 0ms) both;
}
.fin-shimmer::after {
  content: "";
  position: absolute;
  top: 0; left: 0;
  height: 3px;
  width: 36%;
  background: linear-gradient(90deg, transparent, rgba(255, 255, 255, .85), transparent);
  animation: kpiSweep 5.5s var(--ease-standard) infinite;
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
  color: var(--t1, #1e2a4a);
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
