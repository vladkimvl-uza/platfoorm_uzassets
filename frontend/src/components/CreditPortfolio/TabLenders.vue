<script setup lang="ts">
/**
 * TabLenders — таб «Кредиторы».
 *
 * Layout:
 *   Row 1: LenderTypeKpiBand (4 cards · bond/foreign/local/state)
 *   Row 2: Lender Type donut (span 2) + Currency donut (span 2)
 *   Row 3: BanksFullList (span 4 · top-12)
 *
 * Все данные приходят из aggregate.by_lender_type / by_currency / by_bank_full.
 */
import { computed } from "vue";
import { useCreditData } from "@/composables/useCreditData";
import {
  cpCurrencyColor,
  fmtMoneyShort,
  toNum,
  type CurrencyBreakdown,
  type LenderTypeBreakdown,
} from "@/api/credit";
import LenderTypeKpiBand from "./LenderTypeKpiBand.vue";
import CreditDonut, { type DonutEntry } from "./CreditDonut.vue";
import BanksFullList from "./BanksFullList.vue";
import { useFormatters } from "@/composables/useFormatters";
const fmt = useFormatters();

const credit = useCreditData();
const aggregate = computed(() => credit.aggregate.value);

const currencyEntries = computed<DonutEntry[]>(() => {
  if (!aggregate.value) return [];
  return aggregate.value.by_currency.map((c: CurrencyBreakdown) => ({
    label: c.currency,
    value: toNum(c.debt_usd),
    color: cpCurrencyColor(c.currency),
    sub: fmtMoneyShort(c.debt_usd),
    meta: { curCode: c.currency },
  }));
});

const lenderTypeEntries = computed<DonutEntry[]>(() => {
  if (!aggregate.value) return [];
  return aggregate.value.by_lender_type.map((t: LenderTypeBreakdown) => ({
    label: t.label,
    value: toNum(t.debt_usd),
    color: t.color,
    sub: fmtMoneyShort(t.debt_usd),
    meta: { typeKey: t.lender_type },
  }));
});

const centerVal = computed(() => {
  if (!aggregate.value) return "0.00";
  return fmt.fmtNumber(toNum(aggregate.value.total_usd) / 1e9, { decimals: 2 });
});

function currencyHover(e: DonutEntry, total: number): [string, string] {
  const pct = total ? Math.round((Math.abs(e.value) / total) * 100) : 0;
  return [fmt.fmtNumber(e.value / 1e9, { decimals: 2 }), `${e.label} · ${pct}%`];
}

function lenderHover(e: DonutEntry, total: number): [string, string] {
  const pct = total ? Math.round((Math.abs(e.value) / total) * 100) : 0;
  return [fmt.fmtNumber(e.value / 1e9, { decimals: 2 }), `${e.label.toLowerCase()} · ${pct}%`];
}

function onLenderClick(e: DonutEntry) {
  // Можно добавить filter by lenderType в будущем, пока — никаких действий
  console.log("[TabLenders] lender selected:", e.meta?.typeKey);
}

function onCurrencyClick(e: DonutEntry) {
  if (e.meta?.curCode) credit.filterByCurrency(e.meta.curCode);
}

function onSelectType(_t: string) {
  console.log("[TabLenders] type card clicked:", _t);
}
</script>

<template>
  <div v-if="!aggregate" class="cp-tab-loading">
    <div class="cp-spinner" />
    <div class="cp-tab-loading-text">Загружаю данные…</div>
  </div>

  <div v-else class="cp-lenders-grid">
    <!-- Row 1: 4 KPI cards (одна строка) -->
    <div class="cp-lenders-kpi">
      <LenderTypeKpiBand @select-type="onSelectType" />
    </div>

    <!-- Row 2: 2 donuts -->
    <div class="cp-lenders-donuts">
      <div class="pa-card">
        <div class="pa-card-h">
          <span class="pa-card-t">Тип кредитора</span>
          <span class="pa-card-s">структура остатка</span>
        </div>
        <CreditDonut
          v-if="lenderTypeEntries.length > 0"
          :entries="lenderTypeEntries"
          :center-value="centerVal"
          center-label="млрд $"
          :hover-fmt="lenderHover"
          :clickable="true"
          @slice-click="onLenderClick"
        />
        <div v-else class="cp-empty">Нет данных</div>
      </div>

      <div class="pa-card">
        <div class="pa-card-h">
          <span class="pa-card-t">Валюты</span>
          <span class="pa-card-s">структура остатка</span>
        </div>
        <CreditDonut
          v-if="currencyEntries.length > 0"
          :entries="currencyEntries"
          :center-value="centerVal"
          center-label="млрд $"
          :hover-fmt="currencyHover"
          :clickable="true"
          @slice-click="onCurrencyClick"
        />
        <div v-else class="cp-empty">Нет данных</div>
      </div>
    </div>

    <!-- Row 3: Banks list -->
    <div class="cp-lenders-banks">
      <BanksFullList />
    </div>
  </div>
</template>

<style scoped>
.cp-lenders-grid {
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.cp-lenders-kpi {
  margin-top: -4px;
}

.cp-lenders-donuts {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 14px;
}

@media (max-width: 1100px) {
  .cp-lenders-donuts { grid-template-columns: 1fr; }
}

.cp-empty {
  padding: 30px 18px;
  text-align: center;
  font-size: 12px;
  color: var(--t3, var(--t-muted));
  font-style: italic;
}

.cp-tab-loading {
  display: flex;
  align-items: center;
  justify-content: center;
  flex-direction: column;
  min-height: 50vh;
  padding: 40px 20px;
  gap: 14px;
}

.cp-spinner {
  width: 28px;
  height: 28px;
  border: 2.5px solid rgba(127, 119, 221, 0.2);
  border-top-color: #7F77DD;
  border-radius: 50%;
  animation: cpSpin 0.7s linear infinite;
}

@keyframes cpSpin { to { transform: rotate(360deg); } }

.cp-tab-loading-text {
  font-size: 12px;
  color: var(--t3, var(--t-muted));
  font-style: italic;
}
</style>
