<script setup lang="ts">
/**
 * RiskBubbleChart — карта рисков «Срок × Ставка».
 *
 *
 * Данные: useCreditData.riskBubble — RiskBubblePoint[] от backend
 *   { loan_id, bank, currency, years_to_due, rate_pct, debt_usd, date_due }
 *
 * Группировка по валютам — каждый dataset = валюта.
 * Радиус: sqrt(debt_usd/1e6) * 1.5 + 3 (минимум 3px чтобы видно).
 *
 * Click → openLoanDetail.
 */
import { Chart, type ChartConfiguration } from "chart.js/auto";
import { onBeforeUnmount, onMounted, ref, watch } from "vue";
import { useCreditData } from "@/composables/useCreditData";
import {
  CURRENCY_COLORS,
  cpCurrencyColor,
  fmtDate,
  fmtMoneyLoan,
  fmtMoneyShort,
  toNum,
} from "@/api/credit";

const credit = useCreditData();

const canvasEl = ref<HTMLCanvasElement | null>(null);
let chart: Chart | null = null;

function buildConfig(): ChartConfiguration {
  // Group points by currency
  const groups: Record<string, any[]> = {};
  for (const p of credit.riskBubble.value) {
    const cur = p.currency;
    if (!groups[cur]) groups[cur] = [];
    const debtUsd = toNum(p.debt_usd);
    const radius = Math.sqrt(debtUsd / 1e6) * 1.5 + 3;
    groups[cur].push({
      x: Math.max(0, p.years_to_due),
      y: p.rate_pct,
      r: radius,
      _loan: p,
    });
  }

  const datasets = Object.keys(groups)
    .sort((a, b) => groups[b].length - groups[a].length)
    .map((cur) => ({
      label: cur,
      data: groups[cur],
      backgroundColor: cpCurrencyColor(cur) + "80",
      borderColor: cpCurrencyColor(cur),
      borderWidth: 1.2,
    }));

  return {
    type: "bubble" as const,
    data: { datasets },
    options: {
      maintainAspectRatio: false,
      responsive: true,
      animation: { duration: 800, easing: "easeOutQuart" },
      onClick: (_e, elements) => {
        if (!elements.length) return;
        const el = elements[0];
        const ds = (chart?.data.datasets[el.datasetIndex] as any)?.data;
        const pt = ds?.[el.index];
        if (pt?._loan?.loan_id) {
          credit.openLoanDetail(pt._loan.loan_id);
        }
      },
      onHover: (e, els) => {
        const target = (e.native as MouseEvent | undefined)?.target as
          | HTMLElement
          | undefined;
        if (target) target.style.cursor = els.length ? "pointer" : "default";
      },
      plugins: {
        legend: {
          display: true,
          position: "top",
          labels: {
            font: { size: 11 },
            color: "#1e2a4a",
            boxWidth: 12,
            boxHeight: 12,
            padding: 10,
            usePointStyle: true,
          },
        },
        tooltip: {
          backgroundColor: "#0F172A",
          padding: 11,
          cornerRadius: 8,
          titleColor: "#fff",
          bodyColor: "rgba(255,255,255,.88)",
          displayColors: false,
          callbacks: {
            title: (items: any) => {
              const ln = items[0].raw._loan;
              return ln.bank_short_name || ln.bank;
            },
            label: (c: any) => {
              const ln = c.raw._loan;
              const cur = fmtMoneyLoan(ln.debt_currency, ln.currency);
              const usd = fmtMoneyShort(ln.debt_usd);
              return [
                `${cur} (≈ ${usd})`,
                `Ставка: ${ln.rate_pct.toFixed(2)}%`,
                `Срок: ${fmtDate(ln.date_due)}`,
                `Клик — детализация`,
              ];
            },
          },
        },
      },
      scales: {
        x: {
          title: {
            display: true,
            text: "Срок до погашения, лет",
            color: "#888780",
            font: { size: 10 },
          },
          grid: { color: "rgba(127,127,127,.08)" },
          ticks: { color: "#555c6e", font: { size: 10 } },
          beginAtZero: true,
          suggestedMax: 8,
        },
        y: {
          title: {
            display: true,
            text: "Эффективная ставка, %",
            color: "#888780",
            font: { size: 10 },
          },
          grid: { color: "rgba(127,127,127,.08)" },
          ticks: {
            color: "#555c6e",
            font: { size: 10 },
            callback: (v: any) => v.toFixed(0) + "%",
          },
          beginAtZero: true,
        },
      },
    },
  };
}

function render() {
  if (!canvasEl.value) return;
  if (chart) {
    try { chart.destroy(); } catch { /* noop */ }
    chart = null;
  }
  chart = new Chart(canvasEl.value, buildConfig());
}

onMounted(render);

onBeforeUnmount(() => {
  if (chart) {
    try { chart.destroy(); } catch { /* noop */ }
    chart = null;
  }
});

watch(() => credit.riskBubble.value, render, { deep: true });
</script>

<template>
  <div class="cp-rb-host">
    <canvas v-if="credit.riskBubble.value.length > 0" ref="canvasEl" />
    <div v-else class="cp-rb-empty">
      Нет данных для построения карты рисков
      <small>(нужны кредиты с указанной ставкой и сроком погашения)</small>
    </div>
  </div>
</template>

<style scoped>
.cp-rb-host {
  height: 480px;
  padding: 8px 4px;
  position: relative;
}

.cp-rb-host canvas {
  max-height: 100%;
}

.cp-rb-empty {
  position: absolute;
  inset: 0;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  font-size: 13px;
  color: var(--t3, #888780);
  font-style: italic;
  gap: 6px;
}

.cp-rb-empty small {
  font-size: 11px;
  opacity: 0.7;
}
</style>
