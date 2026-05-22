<script setup lang="ts">
/**
 * `paRenderPainPoints` (index.html:22444).
 *
 * Backend не отдаёт product-level aggregate, поэтому считаем клиентом из
 * `purchases[]`. Группируем по product_code, считаем min/median/max price,
 * `savingPotential` (если бы все купили по minPrice), `maxDeviationPct`,
 * uniqueBuyers, contractCount. Top-10 по savingPotential desc.
 *
 *   maxDev ≥ 25  → sev-high (red)
 *   maxDev ≥  5  → sev-mid  (amber)
 *   else         → sev-low  (grey-green)
 */
import { computed } from "vue";
import { paFmtMoneyShort, type ClosureRow } from "@/api/procurement_analysis";

const props = defineProps<{
  purchases: ClosureRow[];
}>();

defineEmits<{
  (e: "drill-product", productCode: string): void;
}>();

interface ProductAgg {
  code: string;
  name: string;
  unit: string | null;
  minPrice: number;
  medianPrice: number;
  maxPrice: number;
  savingPotential: number;   // Σ max(0, (price - minPrice) * volume)
  maxDeviationPct: number;   // max((price - median) / median * 100)
  uniqueBuyers: number;
  contractCount: number;
}

function median(arr: number[]): number {
  if (!arr.length) return 0;
  const s = [...arr].sort((a, b) => a - b);
  const m = Math.floor(s.length / 2);
  return s.length % 2 ? s[m] : (s[m - 1] + s[m]) / 2;
}

const products = computed<ProductAgg[]>(() => {
  const byCode: Record<string, ClosureRow[]> = {};
  for (const p of props.purchases) {
    const code = p.product_code || p.sub_product_code || p.product_name || "";
    if (!code) continue;
    (byCode[code] = byCode[code] || []).push(p);
  }

  const agg: ProductAgg[] = [];
  for (const [code, rows] of Object.entries(byCode)) {
    const prices = rows.map(r => r.unit_price).filter(p => p > 0);
    if (!prices.length) continue;
    const minP = Math.min(...prices);
    const maxP = Math.max(...prices);
    const med = median(prices);
    let savingPotential = 0;
    let maxDevPct = 0;
    const buyerSet = new Set<string>();
    for (const r of rows) {
      if (r.unit_price > minP) savingPotential += (r.unit_price - minP) * r.volume;
      if (med > 0) {
        const dev = ((r.unit_price - med) / med) * 100;
        if (dev > maxDevPct) maxDevPct = dev;
      }
      buyerSet.add(r.company_id);
    }
    agg.push({
      code,
      name: rows[0].product_name || code,
      unit: rows[0].category_unit,
      minPrice: minP,
      medianPrice: med,
      maxPrice: maxP,
      savingPotential,
      maxDeviationPct: maxDevPct,
      uniqueBuyers: buyerSet.size,
      contractCount: rows.length,
    });
  }
  agg.sort((a, b) => b.savingPotential - a.savingPotential);
  return agg.slice(0, 10);
});

function sevClass(p: ProductAgg): "sev-high" | "sev-mid" | "sev-low" {
  if (p.maxDeviationPct >= 25) return "sev-high";
  if (p.maxDeviationPct >= 5)  return "sev-mid";
  return "sev-low";
}

function rowNum(i: number): string {
  return i < 9 ? "0" + (i + 1) : String(i + 1);
}
</script>

<template>
  <div class="pa-pain-host">
    <div v-if="!products.length" class="pa-empty-block">Нет товаров с потенциалом экономии</div>
    <div
      v-for="(p, i) in products"
      :key="p.code"
      class="pa-pain-row"
      :class="sevClass(p)"
      :style="{ animationDelay: (i * 30) + 'ms' }"
      @click="$emit('drill-product', p.code)"
    >
      <span class="pa-pain-num">{{ rowNum(i) }}</span>
      <div class="pa-pain-mid">
        <div class="pa-pain-nm">{{ p.name }}</div>
        <div class="pa-pain-meta">
          {{ p.code }} · max {{ paFmtMoneyShort(p.maxPrice) }} при median {{ paFmtMoneyShort(p.medianPrice) }}
          · {{ p.uniqueBuyers }} SOE × {{ p.contractCount }} закупок
        </div>
      </div>
      <div class="pa-pain-pot">
        <div class="pa-pain-pot-v">+{{ paFmtMoneyShort(p.savingPotential) }}</div>
        <div class="pa-pain-pot-l">потенциал</div>
      </div>
      <div class="pa-pain-dev">
        <div class="pa-pain-dev-v">+{{ p.maxDeviationPct.toFixed(0) }}%</div>
        <div class="pa-pain-dev-l">vs median</div>
      </div>
    </div>
  </div>
</template>

<style scoped>
@keyframes painRowIn {
  0%   { opacity: 0; transform: translateY(6px); }
  100% { opacity: 1; transform: translateY(0); }
}

.pa-pain-host { display: flex; flex-direction: column; gap: 4px; padding: 4px 0; }

.pa-empty-block {
  padding: 32px 16px;
  text-align: center;
  color: #888780;
  font-size: 12px;
  font-style: italic;
}

.pa-pain-row {
  display: grid;
  grid-template-columns: 36px 1fr 110px 80px;
  align-items: center;
  gap: 14px;
  padding: 10px 12px;
  border-radius: 8px;
  cursor: pointer;
  background: #FAFAFC;
  animation: painRowIn .3s ease both;
  animation-delay: var(--delay, 0ms);
  transition: background .12s, transform .12s;
  position: relative; overflow: hidden;
  --pain-accent: transparent;
}
.pa-pain-row::before {
  content: ""; position: absolute; top: 0; left: 0; right: 0;
  height: 2px; background: var(--pain-accent);
  border-top-left-radius: inherit; border-top-right-radius: inherit;
  animation: uzaStripeDrawIn .4s cubic-bezier(0.34, 1.2, 0.64, 1) both;
  transform-origin: left center;
  pointer-events: none;
}
.pa-pain-row:hover { background: rgba(127, 119, 221, .06); transform: translateX(2px); }

.pa-pain-row.sev-high { --pain-accent: #E24B4A; }
.pa-pain-row.sev-mid  { --pain-accent: #EF9F27; }
.pa-pain-row.sev-low  { --pain-accent: #94A3B8; }

.pa-pain-num {
  font-size: 14px; font-weight: 700;
  color: #888780;
  text-align: center;
  font-feature-settings: "tnum";
}
.pa-pain-mid { min-width: 0; }
.pa-pain-nm {
  font-size: 13px; font-weight: 600; color: #1E2A4A;
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}
.pa-pain-meta {
  font-size: 10.5px; color: #888780; margin-top: 2px;
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}

.pa-pain-pot { text-align: right; }
.pa-pain-pot-v {
  font-size: 14px; font-weight: 600; color: #1D9E75;
  font-feature-settings: "tnum";
}
.pa-pain-pot-l {
  font-size: 9px; color: #888780;
  text-transform: uppercase; letter-spacing: .06em;
  margin-top: 1px;
}

.pa-pain-dev { text-align: right; }
.pa-pain-dev-v {
  font-size: 14px; font-weight: 600;
  font-feature-settings: "tnum";
}
.sev-high .pa-pain-dev-v { color: #E24B4A; }
.sev-mid  .pa-pain-dev-v { color: #EF9F27; }
.sev-low  .pa-pain-dev-v { color: #888780; }
.pa-pain-dev-l {
  font-size: 9px; color: #888780;
  text-transform: uppercase; letter-spacing: .06em;
  margin-top: 1px;
}
</style>
