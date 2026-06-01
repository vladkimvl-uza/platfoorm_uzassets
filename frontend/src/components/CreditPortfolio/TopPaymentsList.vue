<script setup lang="ts">
/**
 * TopPaymentsList — Топ-15 крупнейших платежей текущего календарного года.
 *
 * Источник: useCreditData.topPaymentsCurrentYear (loans отсортированы desc).
 * Каждая строка: rank | (sector stripe + company short + bank short) | due short | amount.
 * Click по строке — открыть Loan detail (пока stub: switch на TabLoans + filter banks).
 *
 * Подвал — "Все N платежей YYYY" → drill на TabPayments + filterByYear.
 */
import { computed } from "vue";
import { useCreditData } from "@/composables/useCreditData";
import { fmtMoneyLoan, fmtMoneyShort, toNum, fmtDate } from "@/api/credit";

const credit = useCreditData();

const list = computed(() => credit.topPaymentsCurrentYear.value);
const allCount = computed(() => credit.allPaymentsCurrentYearCount.value);
const asOfYear = computed(() => credit.asOfYear.value);

/** Backend already gives `bank_short_name`. Use it; fallback to bank. */
function bankLabel(loan: any): string {
  return loan.bank_short_name || loan.bank;
}

/** Find sector color for a loan via companiesOverview lookup. */
function sectorColorFor(companyId: string): string | null {
  const co = credit.companiesOverview.value.find((c) => c.company_id === companyId);
  return co?.sector_color || null;
}

function shortenCo(name: string | null | undefined): string {
  if (!name) return "—";
  return name
    .replace(/^АО\s*"?/, "")
    .replace(/^"/, "")
    .replace(/"$/, "")
    .replace(/\s*ДК$/, "")
    .replace(/\s*АЖ$/, " АЖ");
}

function ddmm(iso: string | null | undefined): string {
  if (!iso) return "—";
  const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(iso);
  if (!m) return iso;
  return `${m[3]}.${m[2]}`;
}

function onLoanClick(loan: any) {
  // Заглушка — пока 19c-7 (TabLoans + LoanDetailModal) не готова, переключим в Все кредиты + фильтр банка.
  credit.filterByBank(loan.bank_short_name || loan.bank);
}

function onShowAll() {
  credit.filterByYear(asOfYear.value);
  credit.setView("payments");
}
</script>

<template>
  <div class="pa-card">
    <div class="pa-card-h">
      <span class="pa-card-t">Топ-15 платежей {{ asOfYear }}</span>
      <span class="pa-card-s">крупнейшие · клик — открыть кредит</span>
    </div>

    <div class="cp-tp-body">
      <div
        v-for="(l, i) in list"
        :key="l.id"
        class="cp-tp-row"
        :style="{ animationDelay: i * 45 + 'ms' }"
        :title="'Открыть кредит ' + l.loan_code + ' · ' + fmtMoneyShort(l.debt_usd) + ' эквивалент'"
        @click="onLoanClick(l)"
      >
        <div class="cp-tp-rank">{{ i + 1 }}</div>
        <div class="cp-tp-mid">
          <span
            v-if="sectorColorFor(l.company_id)"
            class="cp-tp-stripe"
            :style="{ background: sectorColorFor(l.company_id)! }"
          />
          <div class="cp-tp-text">
            <span class="cp-tp-nm">{{ shortenCo(l.company_name_ru) }}</span>
            <small>{{ bankLabel(l) }}</small>
          </div>
        </div>
        <div class="cp-tp-due">{{ ddmm(l.date_due) }}</div>
        <div class="cp-tp-amt" :title="fmtMoneyShort(l.debt_usd) + ' эквивалент'">
          {{ fmtMoneyLoan(l.debt_currency, l.currency) }}
        </div>
      </div>

      <div v-if="!list.length" class="cp-tp-empty">
        Нет платежей в {{ asOfYear }} г.
      </div>

      <div
        v-else-if="allCount > 15"
        class="cp-tp-foot"
        @click="onShowAll"
        :title="'Посмотреть все платежи ' + asOfYear + ' г.'"
      >
        <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <line x1="5" y1="12" x2="19" y2="12"/>
          <polyline points="12 5 19 12 12 19"/>
        </svg>
        Все {{ allCount }} платежей {{ asOfYear }} г.
      </div>
    </div>
  </div>
</template>

<style scoped>
.cp-tp-body {
  padding: 6px 14px 14px;
}

.cp-tp-row {
  display: grid;
  grid-template-columns: 22px 1.6fr 0.5fr 1fr;
  align-items: center;
  gap: 8px;
  padding: 8px 4px;
  border-bottom: 1px solid rgba(0, 0, 0, 0.04);
  cursor: pointer;
  transition: background 0.12s;
  animation: cpTpIn 0.4s var(--ease-standard) both;
}

@keyframes cpTpIn {
  from { opacity: 0; transform: translateY(4px); }
  to   { opacity: 1; transform: translateY(0); }
}

.cp-tp-row:hover {
  background: rgba(127, 119, 221, 0.04);
}

.cp-tp-rank {
  font-size: 10.5px;
  font-weight: 500;
  color: var(--t3, var(--t-muted));
  text-align: center;
  font-feature-settings: "tnum";
}

.cp-tp-mid {
  display: flex;
  align-items: center;
  gap: 7px;
  min-width: 0;
}

.cp-tp-stripe {
  width: 3px;
  height: 26px;
  border-radius: 2px;
  flex-shrink: 0;
  opacity: 0.85;
}

.cp-tp-text {
  display: flex;
  flex-direction: column;
  gap: 1px;
  min-width: 0;
}

.cp-tp-nm {
  font-size: 11.5px;
  font-weight: 500;
  color: var(--t1, #1e2a4a);
  letter-spacing: -0.005em;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.cp-tp-text small {
  font-size: 9.5px;
  font-weight: 400;
  color: var(--t3, var(--t-muted));
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.cp-tp-due {
  font-size: 11px;
  color: var(--t2, #555c6e);
  font-weight: 500;
  font-feature-settings: "tnum";
  letter-spacing: 0.02em;
}

.cp-tp-amt {
  font-size: 11.5px;
  font-weight: 600;
  color: var(--t1, #1e2a4a);
  font-feature-settings: "tnum";
  text-align: right;
  letter-spacing: -0.005em;
}

.cp-tp-empty {
  padding: 30px 0;
  text-align: center;
  font-size: 12px;
  color: var(--t3, var(--t-muted));
  font-style: italic;
}

.cp-tp-foot {
  margin-top: 8px;
  padding: 8px 12px;
  background: rgba(127, 119, 221, 0.06);
  border-radius: 8px;
  font-size: 11px;
  font-weight: 500;
  color: #7F77DD;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  cursor: pointer;
  transition: background 0.14s;
}

.cp-tp-foot:hover {
  background: rgba(127, 119, 221, 0.12);
}

.cp-tp-foot svg {
  flex-shrink: 0;
}
</style>
