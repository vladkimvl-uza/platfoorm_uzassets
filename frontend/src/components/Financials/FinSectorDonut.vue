<script setup lang="ts">
// ============================================================================
// Sector donut chart for the Financials dashboard.
//
// Renders a Chart.js doughnut (cutout 84%) with sectors as slices.
// Center shows: total value (in trillion sum or unit-specific) + label.
// Legend on the right with sector colors and percentages.
//
// Hover on a slice → center number switches to that sector's value.
// ============================================================================

import { onMounted, onBeforeUnmount, ref, watch } from "vue";
import { fmtCompact } from "./financialsHelpers";

const props = defineProps<{
  donutData: Array<{ sectorCode: string; label: string; color: string; total: number; pct: number }>;
  /** Selected year for the title; donut shows this year only */
  year: number;
  /** Currency unit display: bln (млрд) or mln (млн) */
  unit: "bln" | "mln";
  currency: string;
  /** Active metric label for chart title (e.g. "Выручка") */
  metricLabel: string;
}>();

const canvasRef = ref<HTMLCanvasElement | null>(null);
const chartRef  = ref<any>(null);
const centerNum = ref<string>("—");
const centerLbl = ref<string>("");

// Total (sum of all sector totals, abs) for center display
function recomputeCenterDefault() {
  const total = props.donutData.reduce((s, d) => s + Math.abs(d.total), 0);
  centerNum.value = fmtCompact(total, props.unit);
  centerLbl.value = `${props.unit === "bln" ? "млрд" : "млн"} ${props.currency}`;
}

async function buildChart() {
  if (!canvasRef.value) return;
  const ChartJs = (window as any).Chart;
  if (!ChartJs) {
    // Try dynamic import (chart.js is in package.json — see FinancialModel.vue)
    try {
      const mod = await import("chart.js/auto");
      (window as any).Chart = mod.default || mod;
    } catch {
      console.warn("Chart.js not available");
      return;
    }
  }
  const Chart = (window as any).Chart;

  // Destroy any existing
  if (chartRef.value) {
    try { chartRef.value.destroy(); } catch (e) { /* */ }
    chartRef.value = null;
  }

  const labels = props.donutData.map(d => d.label);
  const data   = props.donutData.map(d => Math.abs(d.total));
  const colors = props.donutData.map(d => d.color);

  if (!data.length) return;

  recomputeCenterDefault();

  chartRef.value = new Chart(canvasRef.value!, {
    type: "doughnut",
    data: {
      labels,
      datasets: [{
        data,
        backgroundColor: colors,
        borderColor: "rgba(255, 255, 255, 0.92)",
        borderWidth: 3,
        hoverOffset: 8,
        borderRadius: 6,
      }],
    },
    options: {
      responsive: false,
      maintainAspectRatio: false,
      cutout: "84%",
      plugins: {
        legend: { display: false },
        tooltip: { enabled: false },
      },
      animation: { animateRotate: true, duration: 700, easing: "easeOutQuart" },
      onHover: (_evt: unknown, els: any[]) => {
        if (els && els.length) {
          const idx = els[0].index;
          const slice = props.donutData[idx];
          if (slice) {
            centerNum.value = fmtCompact(slice.total, props.unit);
            centerLbl.value = slice.label;
          }
        } else {
          recomputeCenterDefault();
        }
      },
    },
  });
}

onMounted(() => { buildChart(); });
onBeforeUnmount(() => {
  if (chartRef.value) {
    try { chartRef.value.destroy(); } catch (e) { /* */ }
  }
});

// Rebuild on data changes
watch(() => [props.donutData, props.unit, props.currency], () => {
  buildChart();
}, { deep: true });
</script>

<template>
  <div class="fsd-card">
    <div class="fsd-head">
      <div class="fsd-eyebrow">{{ metricLabel }}</div>
      <div class="fsd-title">{{ year }} · по секторам</div>
    </div>
    <div class="fsd-body">
      <div class="fsd-donut">
        <canvas ref="canvasRef" width="160" height="160" />
        <div class="fsd-center">
          <div class="fsd-c-num">{{ centerNum }}</div>
          <div class="fsd-c-lbl">{{ centerLbl }}</div>
        </div>
      </div>
      <div class="fsd-legend">
        <div v-for="(d, i) in donutData"
             :key="d.sectorCode"
             class="fsd-leg-row"
             :style="{ animationDelay: (i * 80 + 400) + 'ms' }">
          <div class="fsd-leg-swatch" :style="{ background: d.color }" />
          <span class="fsd-leg-label">{{ d.label }}</span>
          <span class="fsd-leg-pct">{{ d.pct }}%</span>
        </div>
        <div v-if="!donutData.length" class="fsd-empty">
          Нет данных по выбранной метрике для FY {{ year }}
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.fsd-card {
  background: var(--bg2, #fff);
  border: 1px solid var(--border, #E2E8F0);
  border-radius: 12px;
  padding: 14px 16px;
  animation: finFadeSlideIn .4s ease 200ms both;
}
.fsd-head {
  display: flex; align-items: baseline; justify-content: space-between;
  margin-bottom: 4px;
}
.fsd-eyebrow {
  font-size: 11px; font-weight: 600; color: #7F77DD;
  text-transform: uppercase; letter-spacing: 0.06em;
}
.fsd-title {
  font-size: 11px; font-weight: 500; color: var(--t3, #64748B);
  font-variant-numeric: tabular-nums;
}
.fsd-body {
  display: flex; align-items: center; gap: 18px; padding-top: 6px;
}
.fsd-donut {
  position: relative;
  width: 160px; height: 160px;
  flex-shrink: 0;
}
.fsd-center {
  position: absolute; inset: 0;
  display: flex; flex-direction: column; align-items: center; justify-content: center;
  pointer-events: none;
}
.fsd-c-num {
  font-size: 22px; font-weight: 500;
  color: var(--t1, #1E2A4A);
  letter-spacing: -0.04em;
  font-variant-numeric: tabular-nums;
  line-height: 1;
}
.fsd-c-lbl {
  font-size: 8.5px; color: var(--t3, #64748B); font-weight: 500;
  text-transform: uppercase; letter-spacing: 0.16em;
  margin-top: 3px;
  text-align: center;
}
.fsd-legend {
  flex: 1;
  min-width: 0;
  display: flex; flex-direction: column; gap: 1px;
}
.fsd-leg-row {
  display: flex; align-items: center; gap: 8px;
  padding: 4px 0;
  animation: finFadeSlideIn .3s ease both;
}
.fsd-leg-swatch {
  width: 9px; height: 9px; border-radius: 2px; flex-shrink: 0;
  opacity: 0.92;
}
.fsd-leg-label {
  font-size: 11px; color: var(--t1, #1E2A4A); flex: 1;
  font-weight: 500;
}
.fsd-leg-pct {
  font-size: 11px; font-weight: 600; color: var(--t1, #1E2A4A);
  font-variant-numeric: tabular-nums;
  min-width: 32px; text-align: right;
}
.fsd-empty {
  padding: 14px 0;
  font-size: 11px; color: var(--t3, #64748B);
  font-style: italic;
}
</style>
