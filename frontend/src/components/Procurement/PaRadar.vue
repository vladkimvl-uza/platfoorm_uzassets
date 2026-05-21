<template>
  <!-- Source: paRenderRadar line 22237-22293 -->
  <div class="pa-radar-host" ref="hostRef">
    <canvas ref="canvasRef" />
  </div>
</template>

<script setup lang="ts">
/**
 * PaRadar — TRUE 1:1 port of paRenderRadar (line 22237-22293).
 *
 * Chart.js radar with TWO datasets:
 *   1. Company polygon — filled rgba(127,119,221,.18), border #7F77DD 1.8px
 *   2. Benchmark — dashed orange circle at value 100
 *
 * Polygon = 100 + (deviation_pct).
 * Scale: suggestedMin 60, suggestedMax 140 (±40% range).
 * Animation: 600ms easeOutQuart.
 * Custom tooltip with deviation %.
 * Long category names wrapped via paWrapLabel(name, 14).
 */
import { onMounted, onBeforeUnmount, ref, watch } from "vue";
import { paWrapLabel, type CategoryMeta, type CompanyRatingRow } from "@/api/procurement_analysis";
import { useFormatters } from "@/composables/useFormatters";

const fmt = useFormatters();

declare global {
  interface Window {
    Chart?: any;
    _paRadarChart?: any;
  }
}

const props = defineProps<{
  company: CompanyRatingRow;
  categories: CategoryMeta[];
}>();

const hostRef = ref<HTMLDivElement | null>(null);
const canvasRef = ref<HTMLCanvasElement | null>(null);

let chart: any = null;

function destroy() {
  if (chart) { try { chart.destroy(); } catch {} chart = null; }
  if (window._paRadarChart) { try { window._paRadarChart.destroy(); } catch {} window._paRadarChart = null; }
}

function build() {
  destroy();
  if (!canvasRef.value || !window.Chart) return;
  const ctx = canvasRef.value.getContext("2d");
  if (!ctx) return;

  // line 22245-22246: wrap long labels to 14 chars max
  const labels = props.categories.map((c) => paWrapLabel(c.name, 14));

  // line 22248-22251: company polygon = 100 + deviation
  const coData = props.categories.map((c) => {
    const d = props.company.cat_dev[String(c.id)];
    if (!d || !d.sum_ref) return 100;
    return 100 + (d.sum_dev / d.sum_ref * 100);
  });

  // line 22252: benchmark = 100 for every axis
  const benchData = props.categories.map(() => 100);

  chart = new window.Chart(ctx, {
    type: "radar",
    data: {
      labels,
      // line 22255-22258
      datasets: [
        {
          label: "Компания",
          data: coData,
          backgroundColor: "rgba(127,119,221,.18)",
          borderColor: "#7F77DD",
          borderWidth: 1.8,
          pointBackgroundColor: "#7F77DD",
          pointRadius: 3,
          pointHoverRadius: 5,
        },
        {
          label: "Средняя рынка",
          data: benchData,
          backgroundColor: "rgba(239,159,39,.06)",
          borderColor: "rgba(239,159,39,.7)",
          borderWidth: 1,
          borderDash: [3, 2],
          pointRadius: 0,
        },
      ],
    },
    options: {
      maintainAspectRatio: false,
      // line 22262
      animation: { duration: 600, easing: "easeOutQuart" },
      plugins: {
        legend: { display: false },
        // line 22265-22276
        tooltip: {
          backgroundColor: "#0F172A",
          padding: 8,
          cornerRadius: 6,
          titleColor: "#fff",
          bodyColor: "rgba(255,255,255,.85)",
          callbacks: {
            label: (c: any) => {
              if (c.datasetIndex === 1) return "средняя: 100%";
              const dev = c.parsed.r - 100;
              return "компания: " + fmt.fmtPercent(dev, { decimals: 1, signed: true });
            },
          },
        },
      },
      // line 22279-22288
      scales: {
        r: {
          suggestedMin: 60,
          suggestedMax: 140,
          ticks: { display: false, stepSize: 20 },
          grid: { color: "rgba(127,127,127,.10)" },
          angleLines: { color: "rgba(127,127,127,.10)" },
          pointLabels: { font: { size: 9.5 }, color: "rgba(15,23,60,.65)" },
        },
      },
    },
  });
  window._paRadarChart = chart;
}

onMounted(build);
onBeforeUnmount(destroy);
watch(() => [props.company, props.categories], build, { deep: true });
</script>

<style scoped>
.pa-radar-host {
  position: relative;
  height: 280px;
  width: 100%;
}
.pa-radar-host canvas {
  display: block;
  width: 100% !important;
  height: 100% !important;
}
</style>
