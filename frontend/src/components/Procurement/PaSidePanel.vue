<template>
  <!-- Source: paRenderSidePanel + paRadarPanelHtml line 22160-22236 -->
  <div class="pa-side-body" id="pa-side-body">
    <!-- Selected company → radar panel — line 22167-22170 -->
    <div v-if="selectedCo" class="pa-radar-wrap">
      <!-- line 22225-22227 -->
      <div class="pa-radar-h">
        <span class="pa-radar-co">{{ selectedCo.company_name }} · профиль</span>
        <button class="pa-back" @click="$emit('select-co', null)">‹ к рейтингу</button>
      </div>

      <!-- line 22228 -->
      <PaRadar :company="selectedCo" :categories="categories" />

      <!-- line 22229-22234: 4 mini KPIs -->
      <div class="pa-mini-grid kpi-rail">
        <div class="pa-mini-kpi">
          <div class="pa-mini-l">Отклонение</div>
          <div class="pa-mini-v" :class="selectedCo.company_deviation >= 0 ? 'up' : 'dn'">
            {{ selectedCo.company_deviation >= 0 ? "+" : "" }}{{ selectedCo.company_deviation.toFixed(1) }}%
          </div>
        </div>
        <div class="pa-mini-kpi">
          <div class="pa-mini-l">Потери от переплат</div>
          <!-- Fix 2026-05-25: sum_dev signed (для savers < 0 → max(0,…) = 0
               и виджет всегда показывал 0). sum_overpay из Pack 7.9p —
               positive sum of overpays, ровно эта метрика. -->
          <div class="pa-mini-v">{{ paFmtMoneyShort(Number(overpayUzs)) }}<small>сум</small></div>
        </div>
        <div class="pa-mini-kpi">
          <div class="pa-mini-l">Закупок &gt; median</div>
          <!-- Fix 2026-05-25: лейбл сменили на «Закупок» т.к. above_count/
               total_count это closures, а cat_count — отдельная метрика
               (число категорий). -->
          <div class="pa-mini-v">{{ selectedCo.above_count }}<small>из {{ selectedCo.total_count }}</small></div>
        </div>
        <div class="pa-mini-kpi">
          <div class="pa-mini-l">Место в рейтинге</div>
          <div class="pa-mini-v">{{ rank }}<small>из {{ rating.length }}</small></div>
        </div>
      </div>
    </div>

    <!-- No selection → rating panel — line 22171-22173 -->
    <PaRatingPanel
      v-else
      :rating="rating"
      @select-co="(id: string) => $emit('select-co', id)"
    />
  </div>
</template>

<script setup lang="ts">
import { computed } from "vue";
import {
  paFmtMoneyShort,
  type CategoryMeta,
  type CompanyRatingRow,
} from "@/api/procurement_analysis";
import PaRatingPanel from "./PaRatingPanel.vue";
import PaRadar from "./PaRadar.vue";

const props = defineProps<{
  rating: CompanyRatingRow[];
  categories: CategoryMeta[];
  selectedCoId: string | null;
}>();

defineEmits<{
  (e: "select-co", id: string | null): void;
}>();

const selectedCo = computed<CompanyRatingRow | null>(() => {
  if (!props.selectedCoId) return null;
  return props.rating.find((c) => c.company_id === props.selectedCoId) ?? null;
});

const rank = computed(() => {
  if (!selectedCo.value) return 0;
  return props.rating.findIndex((c) => c.company_id === selectedCo.value!.company_id) + 1;
});

// Защитный parse `sum_overpay` (может прийти как string из Pydantic Decimal).
const overpayUzs = computed(() => {
  const r = selectedCo.value as unknown as { sum_overpay?: number | string } | null;
  return Number(r?.sum_overpay) || 0;
});
</script>

<style scoped>
.pa-side-body {
  background: var(--bg1, #fff);
  border-radius: 0 0 12px 12px;
  overflow-y: auto;
  max-height: calc(100dvh - 280px);
}

/* line 22225-22227 — radar header */
.pa-radar-wrap {
  display: flex;
  flex-direction: column;
  padding: 12px 14px 16px;
}
.pa-radar-h {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 8px;
}
.pa-radar-co {
  font-size: 12px;
  font-weight: 500;
  color: var(--t1, #1e2a4a);
}
.pa-back {
  background: transparent;
  border: 1px solid rgba(15, 23, 60, .15);
  color: rgba(15, 23, 60, .65);
  font-family: inherit;
  font-size: 10.5px;
  padding: 3px 9px;
  border-radius: 4px;
  cursor: pointer;
}
.pa-back:hover { color: #7F77DD; border-color: #7F77DD; }

/* line 22229-22234 — mini KPI grid */
.pa-mini-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 8px;
  margin-top: 12px;
}
.pa-mini-kpi {
  background: var(--bg2, #FAFAFD);
  padding: 8px 10px;
  border-radius: 6px;
}
.pa-mini-l {
  font-size: 9.5px;
  font-weight: 600;
  letter-spacing: .04em;
  color: rgba(15, 23, 60, .55);
  text-transform: lowercase;
}
.pa-mini-v {
  font-size: 14px;
  font-weight: 500;
  margin-top: 2px;
  color: var(--t1, #1e2a4a);
  font-feature-settings: 'tnum';
  letter-spacing: -.015em;
}
.pa-mini-v small {
  font-size: 9.5px;
  color: rgba(15, 23, 60, .55);
  margin-left: 4px;
  font-weight: 400;
}
.pa-mini-v.up { color: #C53030; }
.pa-mini-v.dn { color: #0F6E56; }
</style>
