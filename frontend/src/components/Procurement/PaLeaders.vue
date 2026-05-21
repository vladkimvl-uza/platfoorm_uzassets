<script setup lang="ts">
/**
 * (index.html:22474).
 *
 * Лидер = компания с net economy > 0 (sumSavings - sumOverpay > 0).
 * Top-3 по net economy desc. Click → emit('select-co', companyId) для drill
 * в SidePanel/Profile.
 *
 * Backend `CompanyRatingRow` не отдаёт sumSavings/sumOverpay/greenPct отдельно,
 * поэтому агрегируем клиентом из purchases.
 */
import { computed } from "vue";
import {
  paFmtMoneyShort,
  type ClosureRow,
  type CategoryMeta,
  type CompanyRatingRow,
} from "@/api/procurement_analysis";

const props = defineProps<{
  rating: CompanyRatingRow[];
  purchases: ClosureRow[];
  categories: CategoryMeta[];
}>();

defineEmits<{
  (e: "select-co", companyId: string): void;
}>();

interface LeaderRow {
  co: CompanyRatingRow;
  sumOverpay: number;
  sumSavings: number;
  netEconomy: number;        // sumSavings - sumOverpay
  greenPct: number;          // % покупок ниже median
  bestCatName: string | null;
  bestCatDev: number;
}

const leaders = computed<LeaderRow[]>(() => {
  // Group purchases by company_id for fast lookup
  const byCo: Record<string, ClosureRow[]> = {};
  for (const p of props.purchases) {
    (byCo[p.company_id] = byCo[p.company_id] || []).push(p);
  }
  const catById: Record<number, CategoryMeta> = {};
  for (const c of props.categories) catById[c.id] = c;

  const rows: LeaderRow[] = [];
  for (const co of props.rating) {
    const pp = byCo[co.company_id] || [];
    if (!pp.length) continue;
    let sumOverpay = 0, sumSavings = 0, greenCnt = 0;
    for (const p of pp) {
      const diff = (p.unit_price - p.market_avg) * p.volume;
      if (diff > 0) sumOverpay += diff;
      else if (diff < 0) { sumSavings += -diff; greenCnt++; }
    }
    const net = sumSavings - sumOverpay;
    if (net <= 0) continue;
    // Лучшая категория = первая из best_cats
    const bestList = (co as unknown as { best_cats?: Array<{ category_id: string | number | null; deviation_pct: number }> }).best_cats;
    let bestCatName: string | null = null;
    let bestCatDev = 0;
    if (bestList && bestList.length) {
      const b = bestList[0];
      const key = b.category_id == null ? null : Number(b.category_id);
      bestCatName = (key != null && catById[key]?.name) || null;
      bestCatDev = b.deviation_pct;
    }
    rows.push({
      co, sumOverpay, sumSavings, netEconomy: net,
      greenPct: pp.length ? (greenCnt / pp.length) * 100 : 0,
      bestCatName, bestCatDev,
    });
  }
  rows.sort((a, b) => b.netEconomy - a.netEconomy);
  return rows.slice(0, 3);
});
</script>

<template>
  <div class="pa-leaders-host">
    <div v-if="!leaders.length" class="pa-empty-block">Нет компаний с экономией</div>
    <div
      v-for="(l, i) in leaders"
      :key="l.co.company_id"
      class="pa-leader-card"
      :style="{ animationDelay: (i * 60) + 'ms' }"
      @click="$emit('select-co', l.co.company_id)"
    >
      <div class="pa-leader-h">
        <span class="pa-leader-rank">#{{ i + 1 }}</span>
        <span class="pa-leader-nm">{{ l.co.company_name }}</span>
        <span class="pa-leader-v">−{{ paFmtMoneyShort(l.netEconomy) }}</span>
      </div>
      <div class="pa-leader-meta">
        {{ l.co.cat_count }} категорий
        · {{ l.greenPct.toFixed(0) }}% закупок ниже median
        <template v-if="l.bestCatName && l.bestCatDev < 0">
          · образец в {{ l.bestCatName }} ({{ l.bestCatDev.toFixed(0) }}%)
        </template>
      </div>
    </div>
  </div>
</template>

<style scoped>
@keyframes leaderIn {
  0%   { opacity: 0; transform: translateY(8px); }
  100% { opacity: 1; transform: translateY(0); }
}

.pa-leaders-host { display: flex; flex-direction: column; gap: 8px; padding: 4px 0; }

.pa-empty-block {
  padding: 28px 16px;
  text-align: center;
  color: #888780;
  font-size: 12px;
  font-style: italic;
}

.pa-leader-card {
  background: linear-gradient(135deg, rgba(29, 158, 117, .06), rgba(29, 158, 117, .02));
  border: 1px solid rgba(29, 158, 117, .18);
  border-radius: 8px;
  padding: 10px 14px;
  cursor: pointer;
  animation: leaderIn .35s cubic-bezier(.34, 1.2, .64, 1) both;
  transition: background .12s, transform .12s, border-color .12s;
  position: relative; overflow: hidden;
}
.pa-leader-card::before {
  content: ""; position: absolute; top: 0; left: 0; right: 0;
  height: 3px; background: #1D9E75;
  border-top-left-radius: inherit; border-top-right-radius: inherit;
  animation:
    uzaStripeDrawIn .8s cubic-bezier(.4,0,.2,1) 100ms both,
    uzaStripeBreathe 2.8s ease-in-out 1s infinite;
  pointer-events: none;
}
.pa-leader-card:hover {
  background: linear-gradient(135deg, rgba(29, 158, 117, .12), rgba(29, 158, 117, .04));
  transform: translateX(2px);
  border-color: rgba(29, 158, 117, .35);
}

.pa-leader-h {
  display: flex; align-items: baseline; gap: 8px; margin-bottom: 4px;
}
.pa-leader-rank {
  font-size: 11px; font-weight: 700;
  color: #1D9E75;
  font-feature-settings: "tnum";
  letter-spacing: .02em;
}
.pa-leader-nm {
  font-size: 13px; font-weight: 600; color: #1E2A4A;
  flex: 1; min-width: 0;
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}
.pa-leader-v {
  font-size: 14px; font-weight: 700; color: #0F6E56;
  font-feature-settings: "tnum";
}
.pa-leader-meta {
  font-size: 10.5px; color: #5F5E5A;
  line-height: 1.5;
}
</style>
