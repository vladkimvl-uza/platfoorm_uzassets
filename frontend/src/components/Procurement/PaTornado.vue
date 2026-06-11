<template>
  <!-- Source: paRenderTornado line 21964-22136 -->
  <div class="pa-tornado-host" ref="hostRef">
    <canvas ref="canvasRef" />
  </div>
</template>

<script setup lang="ts">
/**
 * PaTornado — TRUE 1:1 port of paRenderTornado (line 21964-22136).
 *
 * Horizontal bar chart showing Top-9 overpay + Top-6 savings.
 * Each bar:
 *   - color = paColorByDev(deviationPct)
 *   - 3px wide vertical sector indicator (companyColor) on left side
 *   - borderRadius 4, barPercentage 0.78, categoryPercentage 0.92
 * Animation: easeOutQuart 850ms (line 22050)
 * Tooltip: multi-line with cena/median/dev/click hint (line 22063-22091)
 * Click → emit('drill', purchase) — line 22130
 */
import { onMounted, onBeforeUnmount, ref, watch } from "vue";
import {
  paColorByDev,
  paFmtMoneyShort,
  type CompanyRatingRow,
  type ClosureRow,
  type ProcurementAggregate,
} from "@/api/procurement_analysis";
import { useFormatters } from "@/composables/useFormatters";

// Pack 7.9r: renamed from `fmt` → `fmtUtil` to avoid shadowing by the
// local `const fmt = props.fmt || "pct"` inside build() — shadowing made
// `fmt.fmtPercent(...)` call inside Chart.js tooltip throw TypeError and
// crash the whole Procurement view rendering.
const fmtUtil = useFormatters();

declare global {
  interface Window {
    Chart?: any;
    _paTornadoChart?: any;
  }
}

const props = defineProps<{
  data: ProcurementAggregate;
  fmt?: "pct" | "rub";       // window._paFmt — line 21970
}>();

// `drill` остался в типе для совместимости с parent template, но в company-mode
// мы emit-им только `select-co`. Parent может ловить оба события.
const emit = defineEmits<{
  (e: "drill", row: ClosureRow): void;
  (e: "select-co", companyId: string): void;
}>();
void emit;  // typecheck satisfaction; drill emit unused в company-mode

const hostRef = ref<HTMLDivElement | null>(null);
const canvasRef = ref<HTMLCanvasElement | null>(null);

let chart: any = null;
let rowsCache: CompanyRatingRow[] = [];

function destroy() {
  if (chart) { try { chart.destroy(); } catch {} chart = null; }
  if (window._paTornadoChart) { try { window._paTornadoChart.destroy(); } catch {} window._paTornadoChart = null; }
}

function build() {
  destroy();
  if (!canvasRef.value || !window.Chart) return;
  const ctx = canvasRef.value.getContext("2d");
  if (!ctx) return;

  const fmt = props.fmt || "pct";
  // Per user feedback 2026-05-25: показываем все 22 компании (по одной полоске
  // на SOE), отсортированные по компанийному среднему отклонению. Раньше брали
  // top-9 overpay + bottom-6 savings из purchases — выводилось 6 уникальных
  // компаний с дублями (Узметкомбинат × 6 строк, РЭС × 2 и т.д.).
  const rows: CompanyRatingRow[] = [...(props.data.rating || [])]
    .filter((r) => r && r.company_id)
    .sort((a, b) => (Number(b.company_deviation) || 0) - (Number(a.company_deviation) || 0));
  rowsCache = rows;

  // Подгоняем высоту канваса под количество компаний (≥ 22 × 22px + padding).
  if (hostRef.value) {
    const h = Math.max(480, rows.length * 24 + 60);
    hostRef.value.style.height = `${h}px`;
  }

  const labels = rows.map((r) => r.company_name || r.company_code || "—");
  const values = rows.map((r) => {
    if (fmt === "rub") return Math.round(Number(r.sum_dev || 0) / 1e9);  // млрд сум, signed
    return Number(r.company_deviation || 0);
  });

  // ─── Plugin: vertical sector indicator (line 22034-22057) ───
  const sectorIndicatorPlugin = {
    id: "paSectorIndicator",
    afterDraw(chart: any) {
      const meta = chart.getDatasetMeta(0);
      if (!meta || !meta.data) return;
      const ctx2 = chart.ctx;
      const leftPad = chart.chartArea.left;
      ctx2.save();
      meta.data.forEach((bar: any, i: number) => {
        const r = rows[i] as CompanyRatingRow;
        if (!r || !r.company_color) return;
        const y = bar.y;
        const h = Math.min(18, bar.height || 14);
        ctx2.fillStyle = r.company_color;
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
        backgroundColor: rows.map((r) => paColorByDev(Number(r.company_deviation) || 0)),
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
      // line 22050
      animation: { duration: 850, easing: "easeOutQuart" },
      // line 22052
      layout: { padding: { left: 14 } },
      plugins: {
        legend: { display: false },
        // line 22055-22091: tooltip
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
              const r = rows[c.dataIndex] as CompanyRatingRow;
              const dev = Number(r.company_deviation) || 0;
              const sumDev = Number(r.sum_dev) || 0;
              const devTxt = fmtUtil.fmtPercent(dev, { decimals: 1, signed: true });
              const sumTxt = (sumDev >= 0 ? "+" : "−") + paFmtMoneyShort(Math.abs(sumDev)) + " сум";
              return [
                "Средневзвеш. отклонение: " + devTxt,
                "Сумма откл.: " + sumTxt,
                "Красных закупок: " + (r.above_count || 0) + " из " + (r.total_count || 0),
                "Кликни — открыть профиль компании",
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
            callback: (v: number) => fmt === "rub" ? (v + " млн") : ((v > 0 ? "+" : "") + v + "%"),
          },
          border: { display: false },
        },
        y: {
          grid: { display: false },
          ticks: { color: "#1e2a4a", font: { size: 11 } },
          border: { display: false },
        },
      },
      // line 22125: hover cursor pointer
      onHover: (_e: any, els: any[]) => {
        if (canvasRef.value) canvasRef.value.style.cursor = els.length ? "pointer" : "default";
      },
      // Click → select company (company-level bars; no per-closure drill).
      onClick: (_e: any, els: any[]) => {
        if (!els.length) return;
        const r = rowsCache[els[0].index] as CompanyRatingRow;
        if (!r) return;
        emit("select-co", r.company_id);
      },
    },
  });
  window._paTornadoChart = chart;
}

onMounted(build);
onBeforeUnmount(destroy);
watch(() => [props.data, props.fmt], build, { deep: true });
</script>

<style scoped>
/* line 22042 in legacy uses .pa-tornado-host for canvas wrapper */
.pa-tornado-host {
  position: relative;
  /* Высота динамически выставляется JS под кол-во компаний (см. build()).
     Здесь дефолт для первого рендера до прихода data. */
  min-height: 480px;
  width: 100%;
}
.pa-tornado-host canvas {
  display: block;
  width: 100% !important;
  height: 100% !important;
}
</style>
