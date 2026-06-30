<script setup lang="ts">
/**
 * TabRisk — composer таба «Риски».
 *
 * Layout:
 *   Row 1: RiskKpiBand (5 cards)
 *   Row 2: Overdue alert (если overdue_count > 0)
 *   Row 3: RiskBubbleChart (span 4)
 */
import { computed } from "vue";
import { useCreditData } from "@/composables/useCreditData";
import { fmtDate, fmtMoneyLoan, fmtMoneyShort, toNum } from "@/api/credit";
import RiskKpiBand from "./RiskKpiBand.vue";
import RiskBubbleChart from "./RiskBubbleChart.vue";

const credit = useCreditData();

const overdueLoans = computed(() => {
  const today = credit.asOfDate.value;
  return credit.loans.value
    .filter((l) => {
      if (!l.date_due) return false;
      // Apply selectedCompany scope
      if (
        credit.selectedCompanyId.value !== null &&
        l.company_id !== credit.selectedCompanyId.value
      ) {
        return false;
      }
      return l.date_due < today;
    })
    .sort((a, b) => toNum(b.debt_usd) - toNum(a.debt_usd));
});

const overdueAmt = computed(() =>
  overdueLoans.value.reduce((s, l) => s + toNum(l.debt_usd), 0),
);

function showOverdue() {
  credit.filterOverdue(true);
}
</script>

<template>
  <div v-if="!credit.riskMetrics.value && !credit.loading.risk" class="cp-tab-loading">
    <div class="cp-spinner" />
    <div>Загружаю риск-метрики…</div>
  </div>

  <div v-else class="cp-risk-grid">
    <!-- Row 1: 5 KPI cards -->
    <RiskKpiBand />

    <!-- Row 2: Overdue alert -->
    <div v-if="overdueLoans.length > 0" class="cp-risk-alert">
      <div class="cp-risk-alert-icon">
        <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="#E24B4A" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <path d="M12 9v3.5M12 16h.01M3.86 4h16.28a2 2 0 011.78 2.94l-8.14 13.5a2 2 0 01-3.56 0L2.08 6.94A2 2 0 013.86 4z"/>
        </svg>
      </div>
      <div class="cp-risk-alert-body">
        <div class="cp-risk-alert-title">
          Внимание: {{ overdueLoans.length }}
          {{ overdueLoans.length === 1 ? 'просроченный кредит' : 'просроченных кредитов' }}
          на {{ fmtMoneyShort(overdueAmt) }}
        </div>
        <div class="cp-risk-alert-list">
          <span v-for="(l, i) in overdueLoans.slice(0, 3)" :key="l.id">
            <span v-if="i > 0" class="cp-risk-sep">·</span>
            {{ l.bank_short_name || l.bank }}
            ·
            {{ fmtMoneyLoan(l.debt_currency, l.currency) }}
            · срок {{ fmtDate(l.date_due) }}
          </span>
          <span v-if="overdueLoans.length > 3" class="cp-risk-more">
            · +{{ overdueLoans.length - 3 }} ещё
          </span>
        </div>
      </div>
      <button class="cp-risk-alert-btn" @click="showOverdue">Показать →</button>
    </div>

    <!-- Row 3: Bubble chart -->
    <div class="pa-card">
      <div class="pa-card-h">
        <span class="pa-card-t">Карта рисков «Срок × Ставка»</span>
        <span class="pa-card-s">
          точка = кредит · размер = объём · цвет = валюта · клик — детализация
        </span>
      </div>
      <RiskBubbleChart />
    </div>
  </div>
</template>

<style scoped>
.cp-risk-grid {
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.cp-risk-alert {
  display: flex;
  align-items: center;
  gap: 14px;
  padding: 14px 18px;
  background: linear-gradient(135deg, rgba(226, 75, 74, 0.06), rgba(226, 75, 74, 0.02));
  border: 1px solid rgba(226, 75, 74, 0.18);
  border-radius: 12px;
  animation: cpAlertIn 0.5s var(--ease-standard) both;
  position: relative; overflow: hidden;
}

@keyframes cpAlertIn {
  from { opacity: 0; transform: translateY(8px); }
  to   { opacity: 1; transform: translateY(0); }
}
.cp-risk-alert::before {
  content: ""; position: absolute; top: 0; left: 0; right: 0;
  height: 4px; background: var(--sev-high);
  border-top-left-radius: inherit; border-top-right-radius: inherit;
  animation:
    uzaStripeDrawIn .8s var(--ease-standard) 100ms both,
    uzaStripeBreathe 2.8s ease-in-out 1s infinite;
  pointer-events: none;
}

.cp-risk-alert-icon {
  width: 40px;
  height: 40px;
  border-radius: 10px;
  background: rgba(226, 75, 74, 0.15);
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}

.cp-risk-alert-body {
  flex: 1;
  min-width: 0;
}

.cp-risk-alert-title {
  font-size: 13px;
  font-weight: 700;
  color: #C53030;
  letter-spacing: -0.01em;
  margin-bottom: 4px;
}

.cp-risk-alert-list {
  font-size: 11.5px;
  color: var(--t2, #555c6e);
  line-height: 1.55;
  font-feature-settings: "tnum";
}

.cp-risk-sep {
  color: var(--t3, var(--t-muted));
  margin: 0 4px;
}

.cp-risk-more {
  color: var(--t3, var(--t-muted));
  margin-left: 4px;
  font-style: italic;
}

.cp-risk-alert-btn {
  background: var(--sev-high);
  color: #fff;
  border: none;
  padding: 8px 14px;
  border-radius: 8px;
  font-family: inherit;
  font-weight: 600;
  font-size: 12px;
  cursor: pointer;
  flex-shrink: 0;
  transition: background 0.14s;
}

.cp-risk-alert-btn:hover {
  background: #C53030;
}

.cp-tab-loading {
  display: flex;
  align-items: center;
  justify-content: center;
  flex-direction: column;
  min-height: 50dvh;
  padding: 40px 20px;
  gap: 14px;
  color: var(--t3, var(--t-muted));
  font-size: 12px;
  font-style: italic;
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
</style>
