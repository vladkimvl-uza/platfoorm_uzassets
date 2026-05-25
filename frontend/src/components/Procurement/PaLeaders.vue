<script setup lang="ts">
/**
 * `paRenderLeaders` (index.html:22474).
 *
 * Лидер = SOE с net economy > 0 (sum_savings - sum_overpay > 0).
 *
 * Pack: rewrite 2026-05-25 — используем backend `rating[].sum_savings/
 * sum_overpay` (Pack 7.9p), без ручного aggregate из purchases. Раньше
 * ручной aggregate включал dirty rows (15k closures, ~9k dirty) →
 * расходящиеся outliers (extreme prices) гнали лидеров в трлн. Backend
 * исключает dirty при aggregation → числа честные (НГМК ≈ 70 млрд
 * net вместо 107 трлн).
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
  purchases: ClosureRow[];  // kept в props для совместимости
  categories: CategoryMeta[];
}>();
void (null as unknown as ClosureRow);  // suppress unused-import warning

defineEmits<{
  (e: "select-co", companyId: string): void;
}>();

interface LeaderRow {
  co: CompanyRatingRow;
  netEconomy: number;        // sum_savings - sum_overpay (UZS)
  greenPct: number;          // (total - above) / total · % closures ниже median
  bestCatName: string | null;
  bestCatDev: number;
}

const leaders = computed<LeaderRow[]>(() => {
  const catById: Record<number, CategoryMeta> = {};
  for (const c of props.categories) catById[c.id] = c;

  const rows: LeaderRow[] = [];
  for (const co of props.rating) {
    const r = co as unknown as {
      sum_overpay?: number | string;
      sum_savings?: number | string;
      above_count?: number;
      total_count?: number;
      best_cats?: Array<{ category_id: string | number | null; deviation_pct: number }>;
    };
    const sumOverpay = Number(r.sum_overpay) || 0;
    const sumSavings = Number(r.sum_savings) || 0;
    const net = sumSavings - sumOverpay;
    if (net <= 0) continue;
    const above = Number(r.above_count) || 0;
    const total = Number(r.total_count) || 0;
    const greenPct = total > 0 ? ((total - above) / total) * 100 : 0;
    let bestCatName: string | null = null;
    let bestCatDev = 0;
    if (r.best_cats && r.best_cats.length) {
      const b = r.best_cats[0];
      const key = b.category_id == null ? null : Number(b.category_id);
      bestCatName = (key != null && catById[key]?.name) || null;
      bestCatDev = b.deviation_pct;
    }
    rows.push({ co, netEconomy: net, greenPct, bestCatName, bestCatDev });
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
  animation: leaderIn .35s cubic-bezier(0.34, 1.2, 0.64, 1) both;
  transition: background .12s, transform .12s, border-color .12s;
  position: relative; overflow: hidden;
}
.pa-leader-card::before {
  content: ""; position: absolute; top: 0; left: 0; right: 0;
  height: 3px; background: #1D9E75;
  border-top-left-radius: inherit; border-top-right-radius: inherit;
  animation:
    uzaStripeDrawIn .8s cubic-bezier(0.34, 1.2, 0.64, 1) 100ms both,
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
