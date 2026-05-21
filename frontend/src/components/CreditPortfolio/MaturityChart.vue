<script setup lang="ts">
/**
 * MaturityChart — «Календарь погашений по годам».
 *
 * Adapter v2 — теперь принимает массив YearBucket[] из backend.
 * Внутренняя логика Chart.js та же, итерация по массиву.
 */
import { Chart, type ChartConfiguration } from "chart.js/auto";
import { onBeforeUnmount, onMounted, ref, watch } from "vue";
import type { YearBucket } from "@/api/credit";
import { toNum } from "@/api/credit";
import { useFormatters } from "@/composables/useFormatters";
const fmt = useFormatters();

const props = defineProps<{
  years: YearBucket[];
  asOfYear: number;
}>();

const emit = defineEmits<{
  (e: "drill-year", year: number): void;
}>();

const canvasEl = ref<HTMLCanvasElement | null>(null);
let chart: Chart | null = null;

function colorByAmount(usd: number): string {
  const m = usd / 1e6;
  if (m >= 1000) return "#E89B9A";
  if (m >= 400) return "#F2C188";
  if (m >= 200) return "#FCE0B8";
  if (m >= 50) return "#A8DBC4";
  return "#7DBFA1";
}

function buildConfig(): ChartConfiguration {
  const sorted = props.years
    .filter((y) => y.year >= props.asOfYear)
    .slice()
    .sort((a, b) => a.year - b.year);

  const labels = sorted.map((y) => String(y.year));
  const amountsM = sorted.map((y) => toNum(y.debt_usd) / 1e6);
  const counts = sorted.map((y) => y.loans_count);
  const colors = amountsM.map((v) => colorByAmount(v * 1e6));
  const yearsArr = sorted.map((y) => y.year);

  return {
    type: "bar",
    data: {
      labels,
      datasets: [
        {
          data: amountsM,
          backgroundColor: colors,
          borderRadius: 5,
          borderSkipped: false,
          barPercentage: 0.78,
          categoryPercentage: 0.92,
        },
      ],
    },
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
      onClick: (_evt, elements) => {
        if (!elements.length) return;
        emit("drill-year", yearsArr[elements[0].index]);
      },
      plugins: {
        legend: { display: false },
        tooltip: {
          backgroundColor: "#0F172A",
          padding: 10,
          cornerRadius: 8,
          titleColor: "#fff",
          bodyColor: "rgba(255,255,255,.88)",
          displayColors: false,
          callbacks: {
            title: (items) => items[0].label + " г.",
            label: (c) =>
              ([
                fmt.fmtMoneyCompact((c.parsed.y as number) * 1e6, "USD", { decimals: 1 }),
                "к погашению: " + counts[c.dataIndex] + " кред.",
              ] as unknown) as string,
          },
        },
      },
      scales: {
        x: {
          grid: { display: false },
          ticks: { color: "#666", font: { size: 10 } },
        },
        y: {
          grid: { color: "rgba(127,127,127,.08)" },
          ticks: {
            color: "#888780",
            font: { size: 10 },
            callback: (v) => "$" + v + "M",
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
watch(() => [props.years, props.asOfYear] as const, render, { deep: true });
</script>

<template>
  <div class="cp-maturity-chart">
    <canvas ref="canvasEl" />
    <div v-if="!years.length" class="cp-maturity-empty">
      Нет данных по годам погашения
    </div>
  </div>
</template>

<style scoped>
.cp-maturity-chart {
  height: 280px;
  padding: 8px 0;
  position: relative;
}
.cp-maturity-chart canvas {
  max-height: 100%;
}
.cp-maturity-empty {
  position: absolute;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 12px;
  color: var(--t3, #888780);
  font-style: italic;
}
</style>
