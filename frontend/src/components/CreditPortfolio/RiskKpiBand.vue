<script setup lang="ts">
/**
 * RiskKpiBand — 5 KPI карточек для TabRisk.
 *
 * Backend `/risk-metrics` возвращает все нужные показатели:
 *   debt_to_ebitda, icr, annual_interest_expense_usd,
 *   refi_12mo_pct, concentration_top1_pct,
 *   overdue_count, overdue_amount_usd,
 *   ebitda_sane (true если EBITDA в диапазоне $100M-$20B).
 *
 *   Debt/EBITDA: <2.5 green, 2.5-4 amber, ≥4 red
 *   ICR:         >4 green, 2-4 amber, ≤2 red
 *   Refi 12mo:   <10% green, 10-25% amber, ≥25% red
 *   Concentration: <25% green, 25-50% amber, ≥50% red
 *
 * Если EBITDA не sane — показываем "—" для Debt/EBITDA и ICR с tooltip.
 */
import { computed } from "vue";
import { useCreditData } from "@/composables/useCreditData";
import { fmtMoneyShort, fmtPct, toNum } from "@/api/credit";

const credit = useCreditData();

const m = computed(() => credit.riskMetrics.value);

const debtToEbitdaColor = computed(() => {
  const v = toNum(m.value?.debt_to_ebitda);
  if (!m.value?.ebitda_sane || v === 0) return "#888780";
  if (v < 2.5) return "#1D9E75";
  if (v < 4) return "#EF9F27";
  return "#E24B4A";
});

const icrColor = computed(() => {
  const v = toNum(m.value?.icr);
  if (!m.value?.ebitda_sane || v === 0) return "#888780";
  if (v > 4) return "#1D9E75";
  if (v > 2) return "#EF9F27";
  return "#E24B4A";
});

const refiColor = computed(() => {
  const v = (m.value?.refi_12mo_pct ?? 0) * 100;
  if (v < 10) return "#1D9E75";
  if (v < 25) return "#EF9F27";
  return "#E24B4A";
});

const concColor = computed(() => {
  const v = (m.value?.concentration_top1_pct ?? 0) * 100;
  if (v < 25) return "#1D9E75";
  if (v < 50) return "#EF9F27";
  return "#E24B4A";
});

const overdueColor = computed(() => {
  return (m.value?.overdue_count ?? 0) > 0 ? "#E24B4A" : "#1D9E75";
});

const debtEbitdaSubText = computed(() => {
  const v = toNum(m.value?.debt_to_ebitda);
  if (!m.value?.ebitda_sane || v === 0) return "нет EBITDA в финмодуле";
  if (v < 2.5) return "низкая нагрузка ✓";
  if (v < 4) return "умеренная";
  return "высокая ⚠";
});

const icrSubText = computed(() => {
  const v = toNum(m.value?.icr);
  if (!m.value?.ebitda_sane || v === 0) return "нет EBITDA";
  if (v > 4) return "комфортно ✓";
  if (v > 2) return "приемлемо";
  return "напряжённо ⚠";
});

const concSubText = computed(() => {
  const v = (m.value?.concentration_top1_pct ?? 0) * 100;
  if (v < 25) return "диверсифицир.";
  if (v < 50) return "повышенная";
  return "высокая ⚠";
});

const ebitdaSrcLabel = computed(() => {
  const x = m.value;
  if (!x) return "";
  if (!x.ebitda_usd || !x.ebitda_sane) {
    if (x.ebitda_usd && !x.ebitda_sane) {
      return `⚠ EBITDA вне разумного диапазона: ${fmtMoneyShort(x.ebitda_usd)} (${x.ebitda_year})`;
    }
    return "EBITDA не найдена в финмодуле";
  }
  return `EBITDA финмодуль (${x.ebitda_source_company || "?"}, ${x.ebitda_year}): ${fmtMoneyShort(x.ebitda_usd)} · трактовка как ${x.ebitda_unit_assumed || "—"}`;
});

const refiSubText = computed(() => {
  const v = (m.value?.refi_12mo_pct ?? 0) * 100;
  return `~${(toNum(m.value?.annual_interest_expense_usd) / 1e6).toFixed(0)}M год. %`;
});

function onClickRefi() { credit.filterByYear(credit.asOfYear.value); }
function onClickConc() { credit.setView("lenders"); }
function onClickOverdue() { credit.filterOverdue(true); }
</script>

<template>
  <div v-if="!m" class="cp-rk-skel">
    <div v-for="i in 5" :key="i" class="cp-rk-skel-card" />
  </div>

  <div v-else>
    <div class="cp-rk-grid">
      <!-- KPI 1: Debt / EBITDA -->
      <div
        class="cp-rk-card"
        :style="{ '--rk-accent': debtToEbitdaColor, animationDelay: '0ms' }"
        title="Долговая нагрузка относительно EBITDA. Норма для нефтегаза: <2.5×, повышенная 2.5-4×, критичная >4×"
      >
        <div class="cp-rk-h">Debt / EBITDA</div>
        <div v-if="!m.ebitda_sane || !m.debt_to_ebitda" class="cp-rk-num cp-rk-num-empty">
          —<span class="cp-rk-x">×</span>
        </div>
        <div v-else class="cp-rk-num" :style="{ color: debtToEbitdaColor }">
          {{ toNum(m.debt_to_ebitda).toFixed(2) }}<span class="cp-rk-x">×</span>
        </div>
        <div class="cp-rk-sub">{{ debtEbitdaSubText }}</div>
      </div>

      <!-- KPI 2: ICR -->
      <div
        class="cp-rk-card"
        :style="{ '--rk-accent': icrColor, animationDelay: '80ms' }"
        title="Interest Coverage Ratio = EBITDA / годовые %. Норма >2× (приемлемо), >4× (комфортно)"
      >
        <div class="cp-rk-h">Покрытие % (ICR)</div>
        <div v-if="!m.ebitda_sane || !m.icr" class="cp-rk-num cp-rk-num-empty">
          —<span class="cp-rk-x">×</span>
        </div>
        <div v-else class="cp-rk-num" :style="{ color: icrColor }">
          {{ toNum(m.icr).toFixed(2) }}<span class="cp-rk-x">×</span>
        </div>
        <div class="cp-rk-sub">{{ icrSubText }}</div>
      </div>

      <!-- KPI 3: Refi 12mo -->
      <div
        class="cp-rk-card cp-rk-clickable"
        :style="{ '--rk-accent': refiColor, animationDelay: '160ms' }"
        title="Доля портфеля к погашению в течение года · Клик — увидеть кредиты"
        @click="onClickRefi"
      >
        <div class="cp-rk-h">Рефи &lt;1 года</div>
        <div class="cp-rk-num" :style="{ color: refiColor }">
          {{ ((m.refi_12mo_pct || 0) * 100).toFixed(1) }}<span class="cp-rk-x">%</span>
        </div>
        <div class="cp-rk-sub">
          {{ fmtMoneyShort(toNum(m.annual_interest_expense_usd)) }} год. процентов
        </div>
      </div>

      <!-- KPI 4: Concentration top-1 -->
      <div
        class="cp-rk-card cp-rk-clickable"
        :style="{ '--rk-accent': concColor, animationDelay: '240ms' }"
        title="Доля долга на крупнейшего кредитора · Клик — открыть таб Кредиторы"
        @click="onClickConc"
      >
        <div class="cp-rk-h">Концентрация (топ-1)</div>
        <div class="cp-rk-num" :style="{ color: concColor }">
          {{ ((m.concentration_top1_pct || 0) * 100).toFixed(1) }}<span class="cp-rk-x">%</span>
        </div>
        <div class="cp-rk-sub">{{ concSubText }}</div>
      </div>

      <!-- KPI 5: Overdue -->
      <div
        class="cp-rk-card cp-rk-clickable"
        :style="{ '--rk-accent': overdueColor, animationDelay: '320ms' }"
        :title="m.overdue_count > 0 ? 'Просроченные кредиты · Клик — увидеть' : 'Просрочки нет'"
        @click="onClickOverdue"
      >
        <div class="cp-rk-h">Просрочка</div>
        <div class="cp-rk-num" :style="{ color: overdueColor }">
          {{ m.overdue_count }}
        </div>
        <div class="cp-rk-sub">
          <span v-if="m.overdue_count > 0">
            {{ fmtMoneyShort(toNum(m.overdue_amount_usd)) }} к погашению
          </span>
          <span v-else>портфель чистый ✓</span>
        </div>
      </div>
    </div>

    <!-- EBITDA source label -->
    <div v-if="ebitdaSrcLabel" class="cp-rk-ebitda-src">
      {{ ebitdaSrcLabel }}
    </div>
  </div>
</template>

<style scoped>
.cp-rk-grid,
.cp-rk-skel {
  display: grid;
  grid-template-columns: repeat(5, 1fr);
  gap: 12px;
  padding: 0 0 6px;
}

@media (max-width: 1280px) {
  .cp-rk-grid,
  .cp-rk-skel {
    grid-template-columns: repeat(3, 1fr);
  }
}

@media (max-width: 720px) {
  .cp-rk-grid,
  .cp-rk-skel {
    grid-template-columns: repeat(2, 1fr);
  }
}

.cp-rk-card {
  position: relative;
  background: rgba(255, 255, 255, 0.96);
  border: 1px solid rgba(30, 42, 74, 0.06);
  border-radius: 14px;
  padding: 18px 18px 14px;
  overflow: hidden;
  box-shadow:
    0 24px 64px rgba(15, 23, 60, 0.06),
    0 4px 12px rgba(15, 23, 60, 0.04);
  animation: cpRkIn 0.45s cubic-bezier(0.34, 1.2, 0.64, 1) both;
  transition: transform 0.16s ease;
}

.cp-rk-card.cp-rk-clickable {
  cursor: pointer;
}

.cp-rk-card.cp-rk-clickable:hover {
  transform: translateY(-2px);
}

.cp-rk-card::before {
  content: "";
  position: absolute;
  inset: 0 0 auto 0;
  height: 3px;
  background: var(--rk-accent, #7F77DD);
  opacity: 0.85;
}

@keyframes cpRkIn {
  from { opacity: 0; transform: translateY(10px); }
  to   { opacity: 1; transform: translateY(0); }
}

.cp-rk-skel-card {
  background: linear-gradient(
    100deg,
    rgba(127, 119, 221, 0.04) 30%,
    rgba(127, 119, 221, 0.08) 50%,
    rgba(127, 119, 221, 0.04) 70%
  );
  background-size: 220% 100%;
  animation: cpRkSkel 1.4s ease-in-out infinite;
  height: 124px;
  border-radius: 14px;
}

@keyframes cpRkSkel {
  from { background-position: 220% 0; }
  to   { background-position: -220% 0; }
}

.cp-rk-h {
  font-size: 10px;
  font-weight: 500;
  color: var(--t3, #888780);
  text-transform: uppercase;
  letter-spacing: 0.08em;
  margin-bottom: 10px;
}

.cp-rk-num {
  font-size: 30px;
  font-weight: 400;
  color: var(--t1, #1e2a4a);
  letter-spacing: -0.025em;
  font-feature-settings: "tnum";
  font-variant-numeric: tabular-nums;
  line-height: 1.05;
  animation: cpRkNumIn 0.5s ease 200ms both;
}

.cp-rk-num-empty {
  color: var(--t3, #888780);
}

.cp-rk-x {
  font-size: 18px;
  color: var(--t3, #888780);
  margin-left: 3px;
}

@keyframes cpRkNumIn {
  from { opacity: 0; transform: translateY(4px); }
  to   { opacity: 1; transform: translateY(0); }
}

.cp-rk-sub {
  margin-top: 6px;
  font-size: 11px;
  color: var(--t2, #555c6e);
  font-weight: 500;
  letter-spacing: -0.005em;
}

.cp-rk-ebitda-src {
  margin-top: 10px;
  font-size: 10.5px;
  color: var(--t3, #888780);
  font-style: italic;
  padding: 6px 10px;
  background: rgba(127, 119, 221, 0.04);
  border-radius: 8px;
}
</style>
