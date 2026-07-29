<template>
  <div class="aic" v-if="ok">
    <div v-if="spec.title" class="aic-title">{{ spec.title }}</div>
    <div class="aic-canvas-wrap">
      <canvas ref="cv"></canvas>
    </div>
  </div>
  <div v-else class="aic aic-err">{{ t('График не удалось построить') }}</div>
</template>

<script setup lang="ts">
import { ref, onMounted, onBeforeUnmount, computed } from "vue";
import { useI18n } from "@/composables/useI18n";
import { Chart } from "@/utils/chartjsRegister";

const { t } = useI18n();

interface ChartSpec {
  type?: string;
  title?: string;
  labels?: (string | number)[];
  datasets?: { label?: string; data?: number[] }[];
  // упрощённая форма: values вместо datasets
  values?: number[];
}

const props = defineProps<{ spec: ChartSpec }>();

const cv = ref<HTMLCanvasElement | null>(null);
let chart: any = null;

// Брендовая палитра
const PALETTE = ["#7F77DD", "#1D9E75", "#EF9F27", "#378ADD", "#E24B4A", "#534AB7", "#0F6E56", "#854F0B"];
// Зарегистрированы только: bar, line, doughnut, radar. pie → doughnut.
const ALLOWED = new Set(["bar", "line", "doughnut", "radar"]);

const type = computed(() => {
  let chartType = (props.spec?.type || "bar").toLowerCase();
  if (chartType === "pie" || chartType === "polararea") chartType = "doughnut";
  return ALLOWED.has(chartType) ? chartType : "bar";
});

const datasets = computed(() => {
  const s = props.spec || {};
  if (Array.isArray(s.datasets) && s.datasets.length) {
    return s.datasets.map((d) => ({
      label: d.label || "",
      data: (d.data || []).map(Number),
    }));
  }
  if (Array.isArray(s.values)) {
    return [{ label: s.title || "", data: s.values.map(Number) }];
  }
  return [];
});

const ok = computed(() => {
  const labels = props.spec?.labels;
  return Array.isArray(labels) && labels.length > 0 && datasets.value.length > 0;
});

function buildColors(n: number, single: boolean): string[] {
  if (single) return Array.from({ length: n }, (_, i) => PALETTE[i % PALETTE.length]);
  return [PALETTE[0]];
}

function render() {
  if (!cv.value || !ok.value) return;
  const t = type.value;
  const isCategorical = t === "doughnut";
  const ds = datasets.value.map((d, di) => {
    const colors = isCategorical
      ? buildColors(d.data.length, true)
      : [PALETTE[di % PALETTE.length]];
    return {
      label: d.label,
      data: d.data,
      backgroundColor: isCategorical ? colors : (t === "line" ? "transparent" : colors[0]),
      borderColor: isCategorical ? "#fff" : colors[0],
      borderWidth: isCategorical ? 2 : (t === "line" ? 2.5 : 0),
      borderRadius: t === "bar" ? 5 : 0,
      tension: t === "line" ? 0.35 : 0,
      pointBackgroundColor: colors[0],
      pointRadius: t === "line" ? 3 : 0,
      fill: false,
    };
  });

  chart = new Chart(cv.value, {
    type: t as any,
    data: { labels: (props.spec.labels || []).map(String), datasets: ds },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      animation: { duration: 700, easing: "easeOutCubic" },
      plugins: {
        legend: {
          display: ds.length > 1 || isCategorical,
          position: "bottom",
          labels: { font: { size: 11 }, color: "#475569", boxWidth: 12, padding: 10 },
        },
        tooltip: {
          backgroundColor: "rgba(15,23,60,.95)",
          padding: 9, cornerRadius: 7,
          titleFont: { size: 11 }, bodyFont: { size: 11, weight: 600 },
        },
      },
      scales: isCategorical ? {} : {
        x: { ticks: { font: { size: 10 }, color: "#64748B", maxRotation: 50 }, grid: { display: false } },
        y: { beginAtZero: true, ticks: { font: { size: 10 }, color: "#94A3B8" }, grid: { color: "rgba(15,23,60,.05)" } },
      },
    },
  });
}

onMounted(render);
onBeforeUnmount(() => { if (chart) { chart.destroy(); chart = null; } });
</script>

<style scoped>
.aic {
  margin: 12px 0;
  padding: 14px 14px 10px;
  border: 1px solid #E5E7EB;
  border-radius: 13px;
  background: linear-gradient(180deg, #FFFFFF 0%, #FAFAFC 100%);
  box-shadow: 0 2px 10px rgba(15, 23, 60, 0.05);
}
.aic-title {
  font-size: 12.5px;
  font-weight: 500;
  color: var(--uza-navy, #1E2A4A);
  letter-spacing: -0.01em;
  margin-bottom: 10px;
}
.aic-canvas-wrap {
  position: relative;
  height: 240px;
}
.aic-err {
  font-size: 12px;
  color: var(--uza-muted, #888780);
  text-align: center;
  padding: 18px;
}
</style>
