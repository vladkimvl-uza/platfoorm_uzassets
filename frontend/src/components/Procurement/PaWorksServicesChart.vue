<template>
  <div v-if="!rows.length" class="pa-wsc-empty">
    <div class="pa-wsc-empty-title">Нет данных</div>
    <div class="pa-wsc-empty-sub">
      По {{ mode === 'works' ? 'работам' : 'услугам' }} нет расходов в выбранном периоде.
    </div>
  </div>
  <div v-else class="pa-wsc-host" ref="hostRef">
    <canvas ref="canvasRef" />
  </div>
</template>

<script setup lang="ts">
/**
 * PaWorksServicesChart — торнадо-чарт (горизонтальные бары chart.js) расхода
 * на услуги/работы по компаниям. Паттерн перенят 1:1 из PaTornado.vue:
 *   - chart.js берётся из window.Chart (НЕ импортируется);
 *   - sectorIndicatorPlugin: 3px цветная полоска сектора слева от бара;
 *   - динамическая высота host под кол-во строк;
 *   - тёмный tooltip с полной суммой (paFmtMoneyShort, не округлённые млрд);
 *   - onClick по строке (index-mode по Y, intersect:false) → select-company.
 */
import { onMounted, onBeforeUnmount, ref, watch, computed } from "vue";
import {
  paFmtMoneyShort,
  type WorkServiceByCompany,
} from "@/api/procurement_analysis";

declare global {
  interface Window {
    Chart?: any;
  }
}

const props = defineProps<{
  items: WorkServiceByCompany[];
  mode: "services" | "works";
}>();

const emit = defineEmits<{
  (e: "select-company", id: string): void;
}>();

const hostRef = ref<HTMLDivElement | null>(null);
const canvasRef = ref<HTMLCanvasElement | null>(null);

const PURPLE_FALLBACK = "#9D97E6";

function valueOf(r: WorkServiceByCompany): number {
  return Number(props.mode === "services" ? r.services_spend : r.works_spend) || 0;
}
function lotsOf(r: WorkServiceByCompany): number {
  return Number(props.mode === "services" ? r.services_lots : r.works_lots) || 0;
}

/** Отфильтрованные (spend > 0) + отсортированные по spend убыв. */
const rows = computed<WorkServiceByCompany[]>(() =>
  [...(props.items || [])]
    .filter((r) => r && valueOf(r) > 0)
    .sort((a, b) => valueOf(b) - valueOf(a)),
);

let chart: any = null;
let rowsCache: WorkServiceByCompany[] = [];

function destroy() {
  if (chart) {
    try { chart.destroy(); } catch {}
    chart = null;
  }
}

function build() {
  destroy();
  if (!canvasRef.value || !window.Chart) return;
  const ctx = canvasRef.value.getContext("2d");
  if (!ctx) return;

  const data = rows.value;
  rowsCache = data;
  if (!data.length) return;

  // Высота host под кол-во строк.
  if (hostRef.value) {
    const h = Math.max(320, data.length * 24 + 60);
    hostRef.value.style.height = `${h}px`;
  }

  const labels = data.map((r) => r.company_name || "—");
  // Значения в МИЛЛИАРДАХ (округлённые) для бара/оси.
  const values = data.map((r) => Math.round(valueOf(r) / 1e9));

  // ─── Plugin: вертикальная полоска сектора (3px, company_color) ───
  const sectorIndicatorPlugin = {
    id: "paWscSectorIndicator",
    afterDraw(chart: any) {
      const meta = chart.getDatasetMeta(0);
      if (!meta || !meta.data) return;
      const ctx2 = chart.ctx;
      const leftPad = chart.chartArea.left;
      ctx2.save();
      meta.data.forEach((bar: any, i: number) => {
        const r = data[i] as WorkServiceByCompany;
        const color = (r && r.company_color) || PURPLE_FALLBACK;
        const y = bar.y;
        const h = Math.min(18, bar.height || 14);
        ctx2.fillStyle = color;
        ctx2.beginPath();
        if (ctx2.roundRect) {
          ctx2.roundRect(leftPad - 9, y - h / 2, 3, h, 1.5);
        } else {
          ctx2.fillRect(leftPad - 9, y - h / 2, 3, h);
        }
        ctx2.fill();
      });
      ctx2.restore();
    },
  };

  chart = new window.Chart(ctx, {
    type: "bar",
    data: {
      labels,
      datasets: [{
        data: values,
        backgroundColor: data.map((r) => r.company_color || PURPLE_FALLBACK),
        borderRadius: 4,
        borderSkipped: false,
        barPercentage: 0.78,
        categoryPercentage: 0.92,
      }],
    },
    plugins: [sectorIndicatorPlugin],
    options: {
      indexAxis: "y",
      maintainAspectRatio: false,
      animation: { duration: 700, easing: "easeOutQuart" },
      layout: { padding: { left: 14 } },
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
            title: (items: any[]) => items[0].label,
            label: (c: any) => {
              const r = rowsCache[c.dataIndex] as WorkServiceByCompany;
              if (!r) return "";
              return [
                "Расход: " + paFmtMoneyShort(valueOf(r)),
                "Лотов: " + lotsOf(r),
              ];
            },
          },
        },
      },
      scales: {
        x: {
          grid: { color: "rgba(127,127,127,.08)" },
          ticks: {
            color: "rgba(15,23,60,.55)",
            font: { size: 10 },
            callback: (v: number) => v + " млрд",
          },
          border: { display: false },
        },
        y: {
          grid: { display: false },
          ticks: { color: "#1e2a4a", font: { size: 11 } },
          border: { display: false },
        },
      },
      onHover: (_e: any, els: any[]) => {
        if (canvasRef.value) canvasRef.value.style.cursor = els.length ? "pointer" : "default";
      },
      // Клик по ВСЕЙ строке (index-mode по Y, intersect:false) — кликаются
      // и компании с крошечным/нулевым округлённым баром.
      onClick: (e: any, els: any[]) => {
        let idx: number | null = els.length ? els[0].index : null;
        if (idx == null && chart) {
          const pts = chart.getElementsAtEventForMode(e, "index", { axis: "y", intersect: false }, false);
          if (pts.length) idx = pts[0].index;
        }
        if (idx == null) return;
        const r = rowsCache[idx] as WorkServiceByCompany;
        if (r) emit("select-company", r.company_id);
      },
    },
  });
}

onMounted(build);
onBeforeUnmount(destroy);
watch(() => [props.items, props.mode], build, { deep: true });
</script>

<style scoped>
.pa-wsc-host {
  position: relative;
  min-height: 320px;
  width: 100%;
}
.pa-wsc-host canvas {
  display: block;
  width: 100% !important;
  height: 100% !important;
}

.pa-wsc-empty {
  text-align: center;
  padding: 38px 16px;
}
.pa-wsc-empty-title {
  font-size: 14px;
  font-weight: 600;
  color: rgba(15, 23, 60, .6);
}
.pa-wsc-empty-sub {
  font-size: 12px;
  color: rgba(15, 23, 60, .45);
  margin-top: 4px;
}
</style>
