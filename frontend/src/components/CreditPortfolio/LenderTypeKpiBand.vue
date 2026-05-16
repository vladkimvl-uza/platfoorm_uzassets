<script setup lang="ts">
/**
 * LenderTypeKpiBand — 4 KPI карточки типов кредитора.
 *
 * Источник: aggregate.by_lender_type (LenderTypeBreakdown[]).
 * Backend уже возвращает label, color, debt_usd, pct_of_total, loans_count.
 *
 * Каждая карточка имеет цветной accent-стрип сверху и большое число (debt_usd).
 *
 * Click → emit('select-type', lender_type).
 */
import { computed } from "vue";
import { useCreditData } from "@/composables/useCreditData";
import { fmtMoneyShort, fmtPct, type LenderTypeBreakdown } from "@/api/credit";

const credit = useCreditData();
const types = computed<LenderTypeBreakdown[]>(
  () => credit.aggregate.value?.by_lender_type || [],
);

const emit = defineEmits<{
  (e: "select-type", lenderType: string): void;
}>();
</script>

<template>
  <div v-if="!types.length" class="cp-lt-skel">
    <div v-for="i in 4" :key="i" class="cp-lt-skel-card" />
  </div>

  <div v-else class="cp-lt-grid">
    <div
      v-for="(t, i) in types"
      :key="t.lender_type"
      class="cp-lt-card"
      :style="{
        '--lt-accent': t.color,
        animationDelay: i * 80 + 'ms',
      }"
      @click="emit('select-type', t.lender_type)"
    >
      <div class="cp-lt-h">{{ t.label }}</div>
      <div class="cp-lt-num">{{ fmtMoneyShort(t.debt_usd) }}</div>
      <div class="cp-lt-row">
        <span class="cp-lt-pct">{{ fmtPct(t.pct_of_total) }} от портфеля</span>
      </div>
      <div class="cp-lt-row">
        <span class="cp-lt-sub">{{ t.loans_count }} кредитов</span>
      </div>
      <div class="cp-lt-bar">
        <div
          class="cp-lt-bar-fill"
          :style="{
            width: Math.max(2, Math.min(100, t.pct_of_total * 100)) + '%',
            background: t.color,
          }"
        />
      </div>
    </div>
  </div>
</template>

<style scoped>
.cp-lt-grid,
.cp-lt-skel {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 12px;
  padding: 14px 0;
}

@media (max-width: 1280px) {
  .cp-lt-grid,
  .cp-lt-skel {
    grid-template-columns: repeat(2, 1fr);
  }
}

@media (max-width: 720px) {
  .cp-lt-grid,
  .cp-lt-skel {
    grid-template-columns: 1fr;
  }
}

.cp-lt-card {
  position: relative;
  background: rgba(255, 255, 255, 0.96);
  border: 1px solid rgba(30, 42, 74, 0.06);
  border-radius: 14px;
  padding: 18px 18px 14px;
  overflow: hidden;
  box-shadow:
    0 24px 64px rgba(15, 23, 60, 0.06),
    0 4px 12px rgba(15, 23, 60, 0.04);
  animation: cpLtCardIn 0.45s cubic-bezier(0.34, 1.2, 0.64, 1) both;
  cursor: pointer;
  transition: transform 0.16s ease;
}

.cp-lt-card:hover {
  transform: translateY(-2px);
}

.cp-lt-card::before {
  content: "";
  position: absolute;
  inset: 0 0 auto 0;
  height: 3px;
  background: var(--lt-accent, #7F77DD);
  opacity: 0.85;
}

@keyframes cpLtCardIn {
  from { opacity: 0; transform: translateY(10px); }
  to   { opacity: 1; transform: translateY(0); }
}

.cp-lt-skel-card {
  background: linear-gradient(
    100deg,
    rgba(127, 119, 221, 0.04) 30%,
    rgba(127, 119, 221, 0.08) 50%,
    rgba(127, 119, 221, 0.04) 70%
  );
  background-size: 220% 100%;
  animation: cpLtSkel 1.4s ease-in-out infinite;
  height: 132px;
  border-radius: 14px;
}

@keyframes cpLtSkel {
  from { background-position: 220% 0; }
  to   { background-position: -220% 0; }
}

.cp-lt-h {
  font-size: 10px;
  font-weight: 500;
  color: var(--t3, #888780);
  text-transform: uppercase;
  letter-spacing: 0.08em;
  margin-bottom: 10px;
}

.cp-lt-num {
  font-size: 26px;
  font-weight: 400;
  color: var(--t1, #1e2a4a);
  letter-spacing: -0.025em;
  font-feature-settings: "tnum";
  font-variant-numeric: tabular-nums;
  line-height: 1.05;
  animation: cpLtNumIn 0.5s ease 200ms both;
}

@keyframes cpLtNumIn {
  from { opacity: 0; transform: translateY(4px); }
  to   { opacity: 1; transform: translateY(0); }
}

.cp-lt-row {
  margin-top: 6px;
  display: flex;
  align-items: center;
  gap: 6px;
}

.cp-lt-pct {
  font-size: 11.5px;
  color: var(--lt-accent);
  font-weight: 600;
  letter-spacing: -0.005em;
  font-feature-settings: "tnum";
}

.cp-lt-sub {
  font-size: 10.5px;
  color: var(--t2, #555c6e);
  font-weight: 500;
  letter-spacing: 0.02em;
}

.cp-lt-bar {
  margin-top: 10px;
  height: 4px;
  border-radius: 4px;
  background: rgba(127, 119, 221, 0.10);
  overflow: hidden;
}

.cp-lt-bar-fill {
  height: 100%;
  border-radius: 4px;
  animation: cpLtBarFill 0.9s cubic-bezier(0.34, 1.2, 0.64, 1) 250ms both;
  transform-origin: left center;
}

@keyframes cpLtBarFill {
  from { transform: scaleX(0); }
  to   { transform: scaleX(1); }
}
</style>
