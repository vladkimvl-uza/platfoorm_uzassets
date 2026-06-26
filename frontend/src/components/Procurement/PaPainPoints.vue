<script setup lang="ts">
/**
 * PaPainPoints — Топ-10 «болевых товаров портфеля».
 *
 * Использует БЭКЕНД-агрегат `products_by_code` (band-методика): только товары
 * (product_type === 'PRODUCT'), грязные коды (spread > 1000%) уже исключены
 * (их potential_saving = 0), потенциал считается к лучшей сопоставимой цене в
 * полосе [медиана×0.5…×2]. Никаких клиентских пересчётов — иначе всплывали
 * аномальные «+12117% vs median» от несопоставимых кодов.
 *
 * Top-10 по potential_saving desc.
 */
import { computed } from "vue";
import { paFmtMoneyShort, type ProductAgg } from "@/api/procurement_analysis";

const props = defineProps<{
  productsByCode: Record<string, ProductAgg>;
}>();

defineEmits<{
  (e: "drill-product", productCode: string): void;
}>();

const products = computed<ProductAgg[]>(() => {
  return Object.values(props.productsByCode || {})
    .filter(p => p.product_type === "PRODUCT" && Number(p.potential_saving) > 0)
    .sort((a, b) => Number(b.potential_saving) - Number(a.potential_saving))
    .slice(0, 10);
});

/** Превышение максимальной цены над медианой (товары, в полосе сопоставимости). */
function devPct(p: ProductAgg): number {
  const med = Number(p.avg_price) || 0;
  const mx = Number(p.max_price) || 0;
  return med > 0 ? (mx / med - 1) * 100 : 0;
}

function sevClass(p: ProductAgg): "sev-high" | "sev-mid" | "sev-low" {
  const d = devPct(p);
  if (d >= 25) return "sev-high";
  if (d >= 5) return "sev-mid";
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
          {{ p.code }} · max {{ paFmtMoneyShort(p.max_price) }} при median {{ paFmtMoneyShort(p.avg_price) }}
          · {{ p.unique_buyers }} SOE × {{ p.contract_count }} закупок
        </div>
      </div>
      <div class="pa-pain-pot">
        <div class="pa-pain-pot-v">+{{ paFmtMoneyShort(p.potential_saving) }}</div>
        <div class="pa-pain-pot-l">потенциал</div>
      </div>
      <div class="pa-pain-dev">
        <div class="pa-pain-dev-v">+{{ devPct(p).toFixed(0) }}%</div>
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
  color: var(--t3, var(--t-muted));
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
  background: var(--bg2, #FAFAFC);
  animation: painRowIn .3s ease both;
  animation-delay: var(--delay, 0ms);
  transition: background .12s, transform .12s;
  position: relative; overflow: hidden;
  --pain-accent: transparent;
}
.pa-pain-row:hover { background: rgba(127, 119, 221, .06); transform: translateX(2px); }

.pa-pain-row.sev-high { --pain-accent: var(--sev-high); }
.pa-pain-row.sev-mid  { --pain-accent: var(--amber); }
.pa-pain-row.sev-low  { --pain-accent: #94A3B8; }

.pa-pain-num {
  font-size: 14px; font-weight: 700;
  color: var(--t3, var(--t-muted));
  text-align: center;
  font-feature-settings: "tnum";
}
.pa-pain-mid { min-width: 0; }
.pa-pain-nm {
  font-size: 13px; font-weight: 600; color: var(--t1, #1E2A4A);
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}
.pa-pain-meta {
  font-size: 10.5px; color: var(--t3, var(--t-muted)); margin-top: 2px;
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}

.pa-pain-pot { text-align: right; }
.pa-pain-pot-v {
  font-size: 14px; font-weight: 600; color: var(--green);
  font-feature-settings: "tnum";
}
.pa-pain-pot-l {
  font-size: 9px; color: var(--t3, var(--t-muted));
  text-transform: uppercase; letter-spacing: .06em;
  margin-top: 1px;
}

.pa-pain-dev { text-align: right; }
.pa-pain-dev-v {
  font-size: 14px; font-weight: 600;
  font-feature-settings: "tnum";
}
.sev-high .pa-pain-dev-v { color: var(--sev-high); }
.sev-mid  .pa-pain-dev-v { color: var(--amber); }
.sev-low  .pa-pain-dev-v { color: var(--t3, var(--t-muted)); }
.pa-pain-dev-l {
  font-size: 9px; color: var(--t3, var(--t-muted));
  text-transform: uppercase; letter-spacing: .06em;
  margin-top: 1px;
}
</style>
