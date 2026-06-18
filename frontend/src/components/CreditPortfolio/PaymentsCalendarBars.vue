<script setup lang="ts">
/**
 * PaymentsCalendarBars — stacked bars по годам погашения, разрез по валютам.
 *
 * Источник: useCreditData.loans (фильтрация по selectedCompany на client).
 * Бакеты: каждый год от asOfYear до asOfYear+10, после — ">YYYY".
 * Цвет: каждая валюта — отдельный stack-segment с CURRENCY_COLORS.
 *
 * Click → filterByYear (переключает на TabLoans с фильтром).
 */
import { Chart, type ChartConfiguration } from "@/utils/chartjsRegister";
import { onBeforeUnmount, onMounted, ref, watch } from "vue";
import { useCreditData } from "@/composables/useCreditData";
import {
  cpCurrencyColor,
  toNum,
  yearOf,
} from "@/api/credit";
import { useFormatters } from "@/composables/useFormatters";
const fmt = useFormatters();

const credit = useCreditData();

const canvasEl = ref<HTMLCanvasElement | null>(null);
let chart: Chart | null = null;

interface YearBucket {
  year: number;
  isGt: boolean;
  byCurrency: Record<string, number>;
}

function buildBuckets(): YearBucket[] {
  const asOf = credit.asOfYear.value;
  const buckets: Record<string, YearBucket> = {};
  // Pre-create buckets asOf..asOf+10
  for (let y = asOf; y <= asOf + 10; y++) {
    buckets[y] = { year: y, isGt: false, byCurrency: {} };
  }
  buckets["gt"] = { year: 9999, isGt: true, byCurrency: {} };

  // Aggregate
  for (const l of credit.loans.value) {
    if (!l.date_due) continue;
    if (
      credit.selectedCompanyId.value !== null &&
      l.company_id !== credit.selectedCompanyId.value
    ) {
      continue;
    }
    const y = yearOf(l.date_due);
    if (y === null) continue;
    const debtUsd = toNum(l.debt_usd);
    if (debtUsd <= 0) continue;
    const cur = l.currency;
    let target: YearBucket;
    if (y < asOf) {
      // Overdue → put into asOf bucket
      target = buckets[asOf];
    } else if (y > asOf + 10) {
      target = buckets["gt"];
    } else {
      target = buckets[y];
    }
    target.byCurrency[cur] = (target.byCurrency[cur] || 0) + debtUsd;
  }

  return Object.values(buckets);
}

function buildConfig(): ChartConfiguration {
  const bs = buildBuckets();
  const labels = bs.map((b) => (b.isGt ? `>${credit.asOfYear.value + 10}` : String(b.year)));
  // Collect all currencies present (sorted by total volume)
  const totalByCur: Record<string, number> = {};
  for (const b of bs) {
    for (const cur in b.byCurrency) {
      totalByCur[cur] = (totalByCur[cur] || 0) + b.byCurrency[cur];
    }
  }
  const currencies = Object.keys(totalByCur).sort(
    (a, b) => totalByCur[b] - totalByCur[a],
  );

  const datasets = currencies.map((cur) => ({
    label: cur,
    data: bs.map((b) => (b.byCurrency[cur] || 0) / 1e6),
    backgroundColor: cpCurrencyColor(cur),
    borderColor: cpCurrencyColor(cur),
    borderWidth: 0,
    borderRadius: 4,
    borderSkipped: false,
    stack: "year",
  }));

  const yearsArr = bs.map((b) => (b.isGt ? null : b.year));

  return {
    type: "bar",
    data: { labels, datasets },
    options: {
      maintainAspectRatio: false,
      responsive: true,
      animation: { duration: 800, easing: "easeOutQuart" },
      onHover: (e, els) => {
        const target = (e.native as MouseEvent | undefined)?.target as
          | HTMLElement
          | undefined;
        if (target) target.style.cursor = els.length ? "pointer" : "default";
      },
      onClick: (_e, elements) => {
        if (!elements.length) return;
        const idx = elements[0].index;
        const y = yearsArr[idx];
        if (y !== null) credit.filterByYear(y);
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
          mode: "index",
          intersect: false,
          callbacks: {
            label: (c: any) => {
              const v = c.parsed.y as number;
              return `${c.dataset.label}: ${fmt.fmtMoneyCompact(v * 1e6, "USD", { decimals: 1 })}`;
            },
            footer: (items: any) => {
              const total = items.reduce((s: number, i: any) => s + (i.parsed.y || 0), 0);
              return `Σ ${fmt.fmtMoneyCompact(total * 1e6, "USD", { decimals: 1 })}`;
            },
          },
        },
      },
      scales: {
        x: {
          stacked: true,
          grid: { display: false },
          ticks: { color: "#666", font: { size: 10 } },
        },
        y: {
          stacked: true,
          grid: { color: "rgba(127,127,127,.08)" },
          ticks: {
            color: "#888780",
            font: { size: 10 },
            callback: (v: any) => "$" + v + "M",
          },
          border: { display: false },
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

watch(
  () => [credit.loans.value, credit.selectedCompanyId.value, credit.asOfYear.value] as const,
  render,
  { deep: true },
);
</script>

<template>
  <div class="cp-pc-host">
    <canvas v-if="credit.loans.value.length > 0" ref="canvasEl" />
    <div v-else class="cp-pc-empty">Загружаю данные…</div>
  </div>
</template>

<style scoped>
.cp-pc-host {
  height: 360px;
  padding: 8px 4px;
  position: relative;
}

.cp-pc-host canvas {
  max-height: 100%;
}

.cp-pc-empty {
  position: absolute;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 12px;
  color: var(--t3, var(--t-muted));
  font-style: italic;
}
</style>
