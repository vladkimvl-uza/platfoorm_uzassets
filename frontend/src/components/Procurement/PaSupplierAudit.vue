<script setup lang="ts">
/**
 * `paRenderSupplierAudit` (index.html:22514).
 *
 * Группирует purchases[] по нормализованному имени поставщика (убирает
 * ООО/АО/MCHJ/кавычки/пунктуацию), считает sumOverpay/devPct/closures/coCount.
 * Фильтр: devPct > 10% AND closures >= 3. Top-5 по sumOverpay desc.
 */
import { computed } from "vue";
import { paFmtMoneyShort, type ClosureRow } from "@/api/procurement_analysis";

const props = defineProps<{
  purchases: ClosureRow[];
}>();

const emit = defineEmits<{
  (e: "drill-supplier", payload: { key: string; name: string }): void;
}>();

function normalize(name: string): string {
  if (!name || name === "—") return "";
  let s = name.toLowerCase();
  // Strip quotes / parens / brackets
  s = s.replace(/[«»"'""()[\]]/g, " ");
  // Strip legal forms
  s = s.replace(
    /\b(ооо|ао|оао|зао|пао|ип|чп|тоо|llc|ltd|mchj|mch|aj|aksiyadorlik|jamiyat|мчж|оаж|aksdor|ятт|yatt|mchk|sp|sho|fuqarolar|ip)\b/g,
    " ",
  );
  // Collapse whitespace / punctuation
  s = s.replace(/[\s\-,.]+/g, " ").trim();
  return s || name.toLowerCase().trim();
}

interface SupRow {
  key: string;
  name: string;             // most common original spelling
  sumSpend: number;
  sumRef: number;
  sumOverpay: number;
  devPct: number;
  closures: number;
  coCount: number;
}

const suppliers = computed<SupRow[]>(() => {
  const map: Record<string, {
    key: string;
    variants: Record<string, number>;
    sumSpend: number;
    sumRef: number;
    sumOverpay: number;
    closures: number;
    coSet: Set<string>;
  }> = {};

  for (const p of props.purchases) {
    // Fix 2026-05-25: exclude dirty closures (extreme prices ломали sumOverpay).
    if (p.is_dirty) continue;
    if (!p.supplier || p.supplier === "—") continue;
    const key = normalize(p.supplier);
    if (!key) continue;
    let s = map[key];
    if (!s) {
      s = map[key] = { key, variants: {}, sumSpend: 0, sumRef: 0, sumOverpay: 0, closures: 0, coSet: new Set() };
    }
    s.variants[p.supplier] = (s.variants[p.supplier] || 0) + 1;
    const spend = p.unit_price * p.volume;
    const ref = p.market_avg * p.volume;
    s.sumSpend += spend;
    s.sumRef += ref;
    s.closures++;
    s.coSet.add(p.company_id);
    if (spend > ref) s.sumOverpay += (spend - ref);
  }

  const out: SupRow[] = Object.values(map).map(s => {
    // Pick most common spelling
    let best = "", bestN = 0;
    for (const [name, n] of Object.entries(s.variants)) {
      if (n > bestN) { best = name; bestN = n; }
    }
    return {
      key: s.key,
      name: best,
      sumSpend: s.sumSpend,
      sumRef: s.sumRef,
      sumOverpay: s.sumOverpay,
      devPct: s.sumRef > 0 ? ((s.sumSpend - s.sumRef) / s.sumRef) * 100 : 0,
      closures: s.closures,
      coCount: s.coSet.size,
    };
  });

  return out
    .filter(s => s.devPct > 10 && s.closures >= 3)
    .sort((a, b) => b.sumOverpay - a.sumOverpay)
    .slice(0, 5);
});

function sevClass(s: SupRow): "sev-high" | "sev-mid" | "sev-low" {
  if (s.devPct >= 50) return "sev-high";
  if (s.devPct >= 25) return "sev-mid";
  return "sev-low";
}
</script>

<template>
  <div class="pa-sup-host">
    <div v-if="!suppliers.length" class="pa-empty-block">Поставщики со переплатой не выявлены</div>
    <div
      v-for="(s, i) in suppliers"
      :key="s.key"
      class="pa-sup-row"
      :class="sevClass(s)"
      :style="{ animationDelay: (i * 30) + 'ms' }"
      @click="emit('drill-supplier', { key: s.key, name: s.name })"
      title="Открыть детализацию поставщика"
    >
      <div class="pa-sup-mid">
        <div class="pa-sup-nm" :title="s.name">{{ s.name }}</div>
        <div class="pa-sup-meta">
          {{ s.closures }} закупок · {{ s.coCount }} {{ s.coCount === 1 ? 'SOE-клиент' : 'SOE-клиента' }}
        </div>
      </div>
      <div class="pa-sup-amt">+{{ paFmtMoneyShort(s.sumOverpay) }}</div>
      <div class="pa-sup-pct">+{{ s.devPct.toFixed(0) }}%</div>
    </div>
  </div>
</template>

<style scoped>
@keyframes supRowIn {
  0%   { opacity: 0; transform: translateY(6px); }
  100% { opacity: 1; transform: translateY(0); }
}

.pa-sup-host { display: flex; flex-direction: column; gap: 4px; padding: 4px 0; }

.pa-empty-block {
  padding: 28px 16px;
  text-align: center;
  color: #888780;
  font-size: 12px;
  font-style: italic;
}

.pa-sup-row {
  display: grid;
  grid-template-columns: 1fr 110px 70px;
  align-items: center;
  gap: 14px;
  padding: 10px 12px;
  border-radius: 8px;
  background: #FAFAFC;
  animation: supRowIn .3s ease both;
  transition: background .12s, transform .12s;
  position: relative; overflow: hidden;
  --sup-accent: transparent;
  cursor: pointer;
}
.pa-sup-row::before {
  content: ""; position: absolute; top: 0; left: 0; right: 0;
  height: 2px; background: var(--sup-accent);
  border-top-left-radius: inherit; border-top-right-radius: inherit;
  animation: uzaStripeDrawIn .4s cubic-bezier(0.34, 1.2, 0.64, 1) both;
  transform-origin: left center;
  pointer-events: none;
}
.pa-sup-row:hover { background: rgba(226, 75, 74, .04); transform: translateX(2px); }

.pa-sup-row.sev-high { --sup-accent: #E24B4A; background: rgba(226, 75, 74, .04); }
.pa-sup-row.sev-mid  { --sup-accent: #EF9F27; }
.pa-sup-row.sev-low  { --sup-accent: #94A3B8; }

.pa-sup-mid { min-width: 0; }
.pa-sup-nm {
  font-size: 13px; font-weight: 600; color: #1E2A4A;
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
  text-transform: capitalize;
}
.pa-sup-meta {
  font-size: 10.5px; color: #888780; margin-top: 2px;
}

.pa-sup-amt {
  text-align: right;
  font-size: 14px; font-weight: 700;
  font-feature-settings: "tnum";
}
.sev-high .pa-sup-amt { color: #A32D2D; }
.sev-mid  .pa-sup-amt { color: #B07415; }
.sev-low  .pa-sup-amt { color: #5F5E5A; }

.pa-sup-pct {
  text-align: right;
  font-size: 13px; font-weight: 600;
  font-feature-settings: "tnum";
}
.sev-high .pa-sup-pct { color: #E24B4A; }
.sev-mid  .pa-sup-pct { color: #EF9F27; }
.sev-low  .pa-sup-pct { color: #888780; }
</style>
