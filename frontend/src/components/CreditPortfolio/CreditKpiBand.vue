<script setup lang="ts">
/**
 * CreditKpiBand — 6 KPI cards в шапке Credit Portfolio.
 *
 * Реализация v2 — теперь читает агрегат из backend без cpCompute.
 * Все цифры приходят в готовом виде через `useCreditData().totalsBanner`.
 *
 * Карточки (порт cpKpiBandHtml легасиа, lines 25746-25868):
 *   1. Кредитный портфель — loaned + repaid_pct + progress bar
 *   2. Чистый долг — total_usd (= debt_currency in USD)
 *   3. Средневзв. ставка — avg_rate
 *   4. Платёж YYYY — payment_this_year
 *   5. Платёж YYYY+1 — payment_next_year
 *   6. Крупнейший платёж — top_payment_loan (с label банка + дни до)
 */
import { computed } from "vue";
import { useCreditData } from "@/composables/useCreditData";
import { fmtMoneyShort, fmtPct, fmtRate, toNum } from "@/api/credit";
import Odometer from "@/components/Odometer.vue";
import UzaProgressBar from "@/components/UZA/UzaProgressBar.vue";

const credit = useCreditData();

const banner = computed(() => credit.totalsBanner.value);
const asOfYear = computed(() => parseInt(credit.asOfDate.value.slice(0, 4), 10));
const cardsLoaded = computed(() => banner.value !== null);

// KPI 6: largest upcoming payment — short bank name + days
const kpi6 = computed(() => {
  const t = banner.value?.topPayment;
  if (!t) return null;
  return {
    amount: toNum(t.debt_usd),
    label: t.bank_short_name || t.bank,
    days: t.days_until_due ?? null,
    loanCode: t.loan_code,
  };
});
</script>

<template>
  <div v-if="!cardsLoaded" class="cp-kpi-skeleton">
    <div v-for="i in 6" :key="i" class="cp-kpi-card cp-kpi-card-skel" />
  </div>

  <div v-else class="cp-kpi-grid kpi-rail">
    <!-- 1. Кредитный портфель -->
    <div class="cp-kpi-card" style="--kpi-accent:#7F77DD;animation-delay:0ms">
      <div class="cp-kpi-h">Кредитный портфель</div>
      <div class="cp-kpi-num"><Odometer :value="fmtMoneyShort(banner!.loanedUsd)" /></div>
      <div class="cp-kpi-row">
        <span class="cp-kpi-sub">Погашено: {{ fmtPct(banner!.repaidPct) }}</span>
      </div>
      <UzaProgressBar
        :value="banner!.repaidPct"
        fraction
        color="#7F77DD"
        :height="4"
        style="margin-top:10px"
        aria-label="Доля погашения"
      />
    </div>

    <!-- 2. Чистый долг -->
    <div class="cp-kpi-card" style="--kpi-accent:#534AB7;animation-delay:80ms">
      <div class="cp-kpi-h">Чистый долг</div>
      <div class="cp-kpi-num"><Odometer :value="fmtMoneyShort(banner!.totalUsd)" /></div>
      <div class="cp-kpi-row">
        <span class="cp-kpi-sub">{{ banner!.loansCount }} кред. · {{ banner!.banksCount }} банков</span>
      </div>
    </div>

    <!-- 3. Средневзв. ставка -->
    <div class="cp-kpi-card" style="--kpi-accent:#0A7B5E;animation-delay:160ms">
      <div class="cp-kpi-h">Средневзв. ставка</div>
      <div class="cp-kpi-num"><Odometer :value="fmtRate(banner!.avgRate)" /></div>
      <div class="cp-kpi-row">
        <span class="cp-kpi-sub">взвеш. по остатку долга</span>
      </div>
    </div>

    <!-- 4. Платёж текущего года -->
    <div class="cp-kpi-card" style="--kpi-accent:#EF9F27;animation-delay:240ms">
      <div class="cp-kpi-h">Платёж {{ asOfYear }}</div>
      <div class="cp-kpi-num"><Odometer :value="fmtMoneyShort(banner!.paymentThisYear)" /></div>
      <div class="cp-kpi-row">
        <span v-if="banner!.overdueAmount > 0" class="cp-kpi-sub cp-kpi-warn">
          + просрочка: {{ fmtMoneyShort(banner!.overdueAmount) }}
        </span>
        <span v-else class="cp-kpi-sub">погашение в этом году</span>
      </div>
    </div>

    <!-- 5. Платёж следующего года -->
    <div class="cp-kpi-card" style="--kpi-accent:#378ADD;animation-delay:320ms">
      <div class="cp-kpi-h">Платёж {{ asOfYear + 1 }}</div>
      <div class="cp-kpi-num"><Odometer :value="fmtMoneyShort(banner!.paymentNextYear)" /></div>
      <div class="cp-kpi-row">
        <span class="cp-kpi-sub">прогноз погашения</span>
      </div>
    </div>

    <!-- 6. Крупнейший платёж -->
    <div class="cp-kpi-card" style="--kpi-accent:#E24B4A;animation-delay:400ms">
      <div class="cp-kpi-h">Крупнейший платёж</div>
      <div v-if="kpi6" class="cp-kpi-num"><Odometer :value="fmtMoneyShort(kpi6.amount)" /></div>
      <div v-else class="cp-kpi-num cp-kpi-num-empty">—</div>
      <div class="cp-kpi-row">
        <span v-if="kpi6" class="cp-kpi-sub">
          {{ kpi6.label }}<span v-if="kpi6.days !== null"> · через {{ kpi6.days }} дн.</span>
        </span>
        <span v-else class="cp-kpi-sub">нет ближайших платежей</span>
      </div>
    </div>
  </div>
</template>

<style scoped>
/* ─── Grid ─── */
.cp-kpi-grid,
.cp-kpi-skeleton {
  display: grid;
  grid-template-columns: repeat(6, 1fr);
  gap: 12px;
  padding: 14px 0 18px;
}

@media (max-width: 1280px) {
  .cp-kpi-grid,
  .cp-kpi-skeleton {
    grid-template-columns: repeat(3, 1fr);
  }
}

@media (max-width: 720px) {
  .cp-kpi-grid,
  .cp-kpi-skeleton {
    grid-template-columns: repeat(2, 1fr);
  }
}

/* ─── Card ─── */
.cp-kpi-card {
  position: relative;
  background: rgba(255, 255, 255, 0.96);
  border: 1px solid rgba(30, 42, 74, 0.06);
  border-radius: 14px;
  padding: 18px 18px 14px;
  overflow: hidden;
  box-shadow:
    0 24px 64px rgba(15, 23, 60, 0.06),
    0 4px 12px rgba(15, 23, 60, 0.04);
  animation: cpKpiCardIn 0.45s var(--ease-standard) both;
}

.cp-kpi-card::before {
  content: "";
  position: absolute;
  inset: 0 0 auto 0;
  height: 3px;
  background: var(--kpi-accent, #7F77DD);
  opacity: 0.85;
}

@keyframes cpKpiCardIn {
  from {
    opacity: 0;
    transform: translateY(10px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}

.cp-kpi-card-skel {
  background: linear-gradient(
    100deg,
    rgba(127, 119, 221, 0.04) 30%,
    rgba(127, 119, 221, 0.08) 50%,
    rgba(127, 119, 221, 0.04) 70%
  );
  background-size: 220% 100%;
  animation: cpKpiSkel 1.4s ease-in-out infinite;
  height: 124px;
}

@keyframes cpKpiSkel {
  from { background-position: 220% 0; }
  to   { background-position: -220% 0; }
}

/* ─── Content ─── */
.cp-kpi-h {
  font-size: 10px;
  font-weight: 500;
  color: var(--t3, var(--t-muted));
  text-transform: uppercase;
  letter-spacing: 0.08em;
  margin-bottom: 10px;
}

.cp-kpi-num {
  font-size: 28px;
  font-weight: 400;
  color: var(--t1, #1e2a4a);
  letter-spacing: -0.025em;
  font-feature-settings: "tnum";
  font-variant-numeric: tabular-nums;
  line-height: 1.05;
  animation: cpKpiNumIn 0.5s ease 200ms both;
}

.cp-kpi-num-empty {
  color: var(--t3, var(--t-muted));
}

@keyframes cpKpiNumIn {
  from { opacity: 0; transform: translateY(4px); }
  to   { opacity: 1; transform: translateY(0); }
}

.cp-kpi-row {
  margin-top: 8px;
  display: flex;
  align-items: center;
  gap: 6px;
}

.cp-kpi-sub {
  font-size: 11px;
  color: var(--t2, #555c6e);
  font-weight: 500;
  letter-spacing: -0.005em;
}

.cp-kpi-warn {
  color: #C97070;
}

</style>
