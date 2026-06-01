<script setup lang="ts">
/**
 * TabOverview — главный таб «Обзор».
 *
 * Adapter v3 — теперь с реализованным «Все компании» режимом (19c-3).
 *
 * Layouts:
 *
 * Все компании:
 *   ┌─────────────────────────────────────┬─────────────────────────┐
 *   │ Лига компаний (span 3)              │ Топ-15 платежей (span 1)│
 *   ├─────────────────────────────────────┴─────────────────────────┤
 *   │ Heatmap по годам (span 4)                                     │
 *   └───────────────────────────────────────────────────────────────┘
 *
 * Single company (19c-2):
 *   ┌──────────────────────┬─────────────┐
 *   │ Календарь погашений  │ Структура   │ Тип
 *   │ (span 2)             │ валют       │ кредитора
 *   ├──────────────────────┴─────────────┤
 *   │ Концентрация по банкам (span 4)    │
 *   └────────────────────────────────────┘
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
import MaturityChart from "./MaturityChart.vue";
import CreditDonut, { type DonutEntry } from "./CreditDonut.vue";
import BanksTreemap from "./BanksTreemap.vue";
import LeagueTable from "./LeagueTable.vue";
import HeatmapPayments from "./HeatmapPayments.vue";
import TopPaymentsList from "./TopPaymentsList.vue";
import { useFormatters } from "@/composables/useFormatters";
const fmt = useFormatters();

const credit = useCreditData();

const aggregate = computed(() => credit.aggregate.value);
const isAllCompanies = computed(() => credit.isAllCompanies.value);
const asOfYear = computed(() => credit.asOfYear.value);

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
const centerLbl = "млрд $";

function currencyHover(e: DonutEntry, total: number): [string, string] {
  const pct = total ? Math.round((Math.abs(e.value) / total) * 100) : 0;
  return [fmt.fmtNumber(e.value / 1e9, { decimals: 2 }), `${e.label} · ${pct}%`];
}

function lenderHover(e: DonutEntry, total: number): [string, string] {
  const pct = total ? Math.round((Math.abs(e.value) / total) * 100) : 0;
  return [fmt.fmtNumber(e.value / 1e9, { decimals: 2 }), `${e.label.toLowerCase()} · ${pct}%`];
}

function onDrillYear(year: number) { credit.filterByYear(year); }
function onDrillBank(bank: string) { credit.filterByBank(bank); }
function onDrillCurrency(entry: DonutEntry) {
  if (entry.meta?.curCode) credit.filterByCurrency(entry.meta.curCode);
}
function onDrillLenderType(_entry: DonutEntry) { credit.setView("lenders"); }
</script>

<template>
  <!-- ─── Loading ─── -->
  <div v-if="credit.loading.aggregate && !aggregate" class="cp-tab-loading">
    <div class="cp-spinner" />
    <div class="cp-tab-loading-text">Загружаю агрегат…</div>
  </div>

  <!-- ─── Error ─── -->
  <div v-else-if="credit.error.value && !aggregate" class="cp-tab-error">
    <div class="cp-tab-error-title">Не удалось загрузить данные</div>
    <div class="cp-tab-error-msg">{{ credit.error.value }}</div>
  </div>

  <!-- ─── Empty ─── -->
  <div v-else-if="!aggregate" class="cp-tab-stub">
    <div class="cp-tab-stub-msg">Нет данных</div>
  </div>

  <!-- ─── 19c-3: Все компании ─── -->
  <div v-else-if="isAllCompanies" class="cp-pf-grid">
    <!-- Row 1: League Table (span 3) + Top-15 Payments (span 1) -->
    <div class="cp-pf-row1">
      <div class="cp-pf-league">
        <LeagueTable />
      </div>
      <div class="cp-pf-top15">
        <TopPaymentsList />
      </div>
    </div>

    <!-- Row 2: Heatmap span 4 -->
    <div class="cp-pf-heatmap">
      <HeatmapPayments />
    </div>
  </div>

  <!-- ─── 19c-2: одна компания — 4 карточки ─── -->
  <div v-else class="cp-grid">
    <div class="pa-card cp-span-2">
      <div class="pa-card-h">
        <span class="pa-card-t">Календарь погашений</span>
        <span class="pa-card-s">по годам · от {{ asOfYear }}</span>
      </div>
      <MaturityChart
        :years="aggregate.by_year"
        :as-of-year="asOfYear"
        @drill-year="onDrillYear"
      />
    </div>

    <div class="pa-card">
      <div class="pa-card-h">
        <span class="pa-card-t">Структура валют</span>
      </div>
      <CreditDonut
        v-if="currencyEntries.length > 0"
        :entries="currencyEntries"
        :center-value="centerVal"
        :center-label="centerLbl"
        :hover-fmt="currencyHover"
        :clickable="true"
        @slice-click="onDrillCurrency"
      />
      <div v-else class="cp-empty">Нет данных</div>
    </div>

    <div class="pa-card">
      <div class="pa-card-h">
        <span class="pa-card-t">Тип кредитора</span>
        <span class="pa-card-s">структура остатка</span>
      </div>
      <CreditDonut
        v-if="lenderTypeEntries.length > 0"
        :entries="lenderTypeEntries"
        :center-value="centerVal"
        :center-label="centerLbl"
        :hover-fmt="lenderHover"
        :clickable="true"
        @slice-click="onDrillLenderType"
      />
      <div v-else class="cp-empty">Нет данных</div>
    </div>

    <div class="pa-card cp-span-4">
      <div class="pa-card-h">
        <span class="pa-card-t">Концентрация по банкам</span>
        <span class="pa-card-s">топ-10 кредиторов</span>
      </div>
      <BanksTreemap
        :banks="aggregate.by_bank_top10"
        @filter-bank="onDrillBank"
      />
    </div>
  </div>
</template>

<style scoped>
/* ─── 19c-3 Все компании layout ─── */
.cp-pf-grid {
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.cp-pf-row1 {
  display: grid;
  grid-template-columns: 3fr 1fr;
  gap: 14px;
}

@media (max-width: 1280px) {
  .cp-pf-row1 {
    grid-template-columns: 1fr;
  }
}

.cp-pf-league,
.cp-pf-top15,
.cp-pf-heatmap {
  min-width: 0;
}

/* ─── 19c-2 single-co 4-col grid ─── */
.cp-grid {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 14px;
}
.cp-span-2 { grid-column: span 2; }
.cp-span-4 { grid-column: span 4; }

@media (max-width: 1200px) {
  .cp-grid { grid-template-columns: repeat(2, 1fr); }
  .cp-span-2, .cp-span-4 { grid-column: span 2; }
}

@media (max-width: 700px) {
  .cp-grid { grid-template-columns: 1fr; }
  .cp-span-2, .cp-span-4 { grid-column: span 1; }
}

/* ─── pa-card global fallback ─── */
:global(.pa-card) {
  background: rgba(255, 255, 255, 0.96);
  border: 1px solid rgba(30, 42, 74, 0.06);
  border-radius: 14px;
  box-shadow:
    0 24px 64px rgba(15, 23, 60, 0.06),
    0 4px 12px rgba(15, 23, 60, 0.04);
  overflow: hidden;
  animation: cpCardIn 0.45s var(--ease-standard) both;
}

@keyframes cpCardIn {
  from { opacity: 0; transform: translateY(8px); }
  to   { opacity: 1; transform: translateY(0); }
}

:global(.pa-card-h) {
  display: flex;
  align-items: baseline;
  gap: 10px;
  padding: 14px 18px 8px;
  border-bottom: 1px solid rgba(0, 0, 0, 0.04);
}

:global(.pa-card-t) {
  font-size: 13px;
  font-weight: 500;
  color: var(--t1, #1e2a4a);
  letter-spacing: -0.005em;
}

:global(.pa-card-s) {
  font-size: 10px;
  color: var(--t3, var(--t-muted));
  font-weight: 500;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  margin-left: auto;
}

.cp-empty {
  padding: 30px 18px;
  text-align: center;
  font-size: 12px;
  color: var(--t3, var(--t-muted));
  font-style: italic;
}

/* ─── Loading / Error / Stub ─── */
.cp-tab-loading,
.cp-tab-error,
.cp-tab-stub {
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

.cp-tab-error-title {
  font-size: 14px;
  font-weight: 500;
  color: #C97070;
}

.cp-tab-error-msg {
  font-size: 12px;
  color: var(--t3, var(--t-muted));
  max-width: 480px;
  text-align: center;
  font-family: monospace;
  background: rgba(201, 112, 112, 0.06);
  padding: 8px 12px;
  border-radius: 6px;
}

.cp-tab-stub-msg {
  font-size: 12.5px;
  color: var(--t2, #555c6e);
  text-align: center;
  background: rgba(127, 119, 221, 0.04);
  padding: 24px 28px;
  border-radius: 14px;
  border: 1px dashed rgba(127, 119, 221, 0.25);
}
</style>
