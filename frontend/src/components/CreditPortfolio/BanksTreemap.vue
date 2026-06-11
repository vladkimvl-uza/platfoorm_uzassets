<script setup lang="ts">
/**
 * BanksTreemap — топ-10 банков по объёму долга.
 *
 * Adapter v2 — теперь принимает BankBreakdown[] (уже sorted top-10 от backend).
 * Иначе логика рендера 1:1 с легасиом.
 *
 * Цвета:
 *   1-е место: #7F77DD
 *   2-е:       #534AB7
 *   3-5 места: #0A7B5E
 *   Остальные: #888780
 */
import { computed } from "vue";
import type { BankBreakdown } from "@/api/credit";
import { toNum } from "@/api/credit";
import { useFormatters } from "@/composables/useFormatters";
const fmt = useFormatters();

const props = defineProps<{
  banks: BankBreakdown[];
}>();

const emit = defineEmits<{
  (e: "filter-bank", bank: string): void;
}>();

const cells = computed(() => {
  return props.banks.slice(0, 10).map((b, i) => {
    const amount = toNum(b.debt_usd);
    const pct = b.pct_of_total * 100;
    const color =
      i === 0 ? "#7F77DD"
      : i === 1 ? "#534AB7"
      : i < 5 ? "#0A7B5E"
      : "#888780";
    return {
      bank: b.bank_short_name,
      amount,
      pct,
      flex: amount,
      color,
      label: `${fmt.fmtMoneyCompact(amount, "USD", { decimals: 0 })} · ${fmt.fmtPercent(pct, { decimals: 1 })}`,
      title: `${b.bank_short_name}: ${fmt.fmtMoneyCompact(amount, "USD", { decimals: 1 })} (${b.loans_count} кред.)`,
    };
  });
});
</script>

<template>
  <div v-if="!cells.length" class="cp-tmap-empty">Нет данных по банкам</div>
  <div v-else class="cp-tmap">
    <div
      v-for="(c, i) in cells"
      :key="c.bank"
      class="cp-tmap-cell"
      :style="{
        background: c.color,
        flex: c.flex,
        animationDelay: i * 40 + 'ms',
      }"
      :title="c.title"
      @click="emit('filter-bank', c.bank)"
    >
      <div class="cp-tmap-nm">{{ c.bank }}</div>
      <div class="cp-tmap-v">{{ c.label }}</div>
    </div>
  </div>
</template>

<style scoped>
.cp-tmap {
  display: flex;
  gap: 4px;
  padding: 14px;
  min-height: 180px;
  flex-wrap: wrap;
}

.cp-tmap-cell {
  min-width: 90px;
  min-height: 80px;
  padding: 12px 14px;
  border-radius: 8px;
  color: #fff;
  cursor: pointer;
  transition: transform 0.18s var(--ease-standard),
    filter 0.18s ease;
  display: flex;
  flex-direction: column;
  justify-content: flex-end;
  overflow: hidden;
  animation: cpTmapIn 0.45s var(--ease-standard) both;
  position: relative;
}

@keyframes cpTmapIn {
  from {
    opacity: 0;
    transform: scale(0.94);
  }
  to {
    opacity: 1;
    transform: scale(1);
  }
}

.cp-tmap-cell:hover {
  transform: translateY(-2px);
  filter: brightness(1.08);
}

.cp-tmap-nm {
  font-size: 11.5px;
  font-weight: 600;
  letter-spacing: -0.005em;
  line-height: 1.25;
  margin-bottom: 6px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  opacity: 0.95;
}

.cp-tmap-v {
  font-size: 11px;
  font-weight: 500;
  font-feature-settings: "tnum";
  font-variant-numeric: tabular-nums;
  opacity: 0.86;
  letter-spacing: 0.01em;
}

.cp-tmap-empty {
  padding: 30px 18px;
  text-align: center;
  font-size: 12px;
  color: var(--t3, var(--t-muted));
  font-style: italic;
}
</style>
