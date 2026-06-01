<script setup lang="ts">
/**
 * BanksFullList — топ-12 банков по объёму долга с типом кредитора.
 *
 * Источник: aggregate.by_bank_full (BankRow[] sorted by debt_usd desc).
 *
 * Layout: rank | bank name + short | type pill | debt_usd + pct + bar | loans_count
 *
 * Click → filter by bank (TabLoans).
 */
import { computed } from "vue";
import { useCreditData } from "@/composables/useCreditData";
import {
  CP_LENDER_LABELS,
  fmtMoneyShort,
  fmtPct,
  toNum,
  type BankRow,
  type LenderType,
} from "@/api/credit";

const credit = useCreditData();

const banks = computed<BankRow[]>(() => {
  const list = credit.aggregate.value?.by_bank_full || [];
  return list.slice(0, 12);
});

const maxDebt = computed(() => {
  if (!banks.value.length) return 1;
  return toNum(banks.value[0].debt_usd) || 1;
});

function typeColor(t: LenderType | null | undefined): string {
  return t ? CP_LENDER_LABELS[t]?.color || "#888780" : "#888780";
}

function typeLabel(t: LenderType | null | undefined): string {
  return t ? CP_LENDER_LABELS[t]?.label || t : "—";
}

function onBankClick(b: BankRow) {
  credit.filterByBank(b.bank_short_name);
}
</script>

<template>
  <div class="pa-card">
    <div class="pa-card-h">
      <span class="pa-card-t">Топ-12 банков</span>
      <span class="pa-card-s">по объёму долга · клик — фильтр по банку</span>
    </div>

    <div v-if="!banks.length" class="cp-bf-empty">
      Загружаю данные…
    </div>

    <div v-else class="cp-bf-body">
      <div
        v-for="(b, i) in banks"
        :key="b.bank_short_name + i"
        class="cp-bf-row"
        :style="{ animationDelay: i * 50 + 'ms' }"
        :title="'Фильтр по банку: ' + b.bank"
        @click="onBankClick(b)"
      >
        <div class="cp-bf-rank">{{ i + 1 }}</div>

        <div class="cp-bf-bank">
          <div class="cp-bf-bank-full">{{ b.bank }}</div>
          <div class="cp-bf-bank-short" v-if="b.bank_short_name !== b.bank">
            {{ b.bank_short_name }}
          </div>
        </div>

        <div class="cp-bf-type">
          <span
            class="cp-bf-pill"
            :style="{
              background: typeColor(b.lender_type) + '22',
              color: typeColor(b.lender_type),
              borderColor: typeColor(b.lender_type) + '55',
            }"
          >
            {{ typeLabel(b.lender_type) }}
          </span>
        </div>

        <div class="cp-bf-debt">
          <div class="cp-bf-debt-bar">
            <div
              class="cp-bf-debt-fill"
              :style="{
                width: Math.max(2, (toNum(b.debt_usd) / maxDebt) * 100) + '%',
                background: typeColor(b.lender_type),
              }"
            />
          </div>
          <div class="cp-bf-debt-row">
            <span class="cp-bf-debt-amt">{{ fmtMoneyShort(b.debt_usd) }}</span>
            <span class="cp-bf-debt-pct">{{ fmtPct(b.pct_of_total) }}</span>
          </div>
        </div>

        <div class="cp-bf-count">
          {{ b.loans_count }}
          <small>{{ b.loans_count === 1 ? 'кредит' : 'кред.' }}</small>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.cp-bf-body {
  padding: 4px 14px 12px;
}

.cp-bf-row {
  display: grid;
  grid-template-columns: 26px 2.4fr 0.9fr 1.5fr 0.7fr;
  align-items: center;
  gap: 12px;
  padding: 9px 4px;
  border-bottom: 1px solid rgba(0, 0, 0, 0.04);
  cursor: pointer;
  transition: background 0.12s;
  animation: cpBfIn 0.4s var(--ease-standard) both;
}

@keyframes cpBfIn {
  from { opacity: 0; transform: translateY(4px); }
  to   { opacity: 1; transform: translateY(0); }
}

.cp-bf-row:hover {
  background: rgba(127, 119, 221, 0.04);
}

.cp-bf-rank {
  font-size: 11px;
  font-weight: 500;
  color: var(--t3, var(--t-muted));
  text-align: center;
  font-feature-settings: "tnum";
}

.cp-bf-bank {
  min-width: 0;
}

.cp-bf-bank-full {
  font-size: 12.5px;
  font-weight: 500;
  color: var(--t1, #1e2a4a);
  letter-spacing: -0.005em;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  margin-bottom: 1px;
}

.cp-bf-bank-short {
  font-size: 10px;
  color: var(--t3, var(--t-muted));
  font-weight: 400;
}

.cp-bf-type {
  display: flex;
}

.cp-bf-pill {
  font-size: 9.5px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.04em;
  padding: 3px 9px;
  border-radius: 9px;
  border: 1px solid;
  white-space: nowrap;
}

.cp-bf-debt-bar {
  height: 5px;
  border-radius: 3px;
  background: rgba(127, 119, 221, 0.08);
  overflow: hidden;
}

.cp-bf-debt-fill {
  height: 100%;
  border-radius: 3px;
  transition: width 0.6s ease;
}

.cp-bf-debt-row {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 8px;
  margin-top: 3px;
}

.cp-bf-debt-amt {
  font-size: 11.5px;
  font-weight: 600;
  color: var(--t1, #1e2a4a);
  font-feature-settings: "tnum";
  letter-spacing: -0.005em;
}

.cp-bf-debt-pct {
  font-size: 10px;
  color: var(--t3, var(--t-muted));
  font-weight: 500;
  font-feature-settings: "tnum";
}

.cp-bf-count {
  font-size: 13px;
  font-weight: 500;
  color: var(--t1, #1e2a4a);
  text-align: right;
  font-feature-settings: "tnum";
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  gap: 1px;
}

.cp-bf-count small {
  font-size: 9.5px;
  font-weight: 400;
  color: var(--t3, var(--t-muted));
  text-transform: uppercase;
  letter-spacing: 0.04em;
}

.cp-bf-empty {
  padding: 30px 18px;
  text-align: center;
  font-size: 12px;
  color: var(--t3, var(--t-muted));
  font-style: italic;
}

@media (max-width: 980px) {
  .cp-bf-row {
    grid-template-columns: 22px 2fr 1fr 1fr;
    gap: 8px;
  }
  .cp-bf-row > :nth-child(5) { display: none; }
}
</style>
