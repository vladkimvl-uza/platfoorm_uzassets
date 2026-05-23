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
  paFmtMoney,
  paFmtMoneyShort,
  type ClosureRow,
  type ProcurementAggregate,
} from "@/api/procurement_analysis";
import { useFormatters } from "@/composables/useFormatters";

const fmt = useFormatters();

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

const emit = defineEmits<{
  (e: "drill", row: ClosureRow): void;
  (e: "select-co", companyId: string): void;
}>();

const hostRef = ref<HTMLDivElement | null>(null);
const canvasRef = ref<HTMLCanvasElement | null>(null);

let chart: any = null;
let rowsCache: ClosureRow[] = [];

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
  // Top-9 overpayers (dev > 0) + Top-6 savers (dev < 0). Объединяются в
  // ОДНУ горизонтальную ленту, отсортированную DESC так что overpayers сверху,
  // savers снизу — визуальный «торнадо».
  // Прошлая Vue-имплементация брала `sorted.slice(-6)` что давало последние
  // 6 по индексу (всегда самые negative — корректно если все sorted DESC),
  // но при малых данных могло пересечься с `top`. Используем явные фильтры.
  // Pack 7.9o: exclude dirty closures from Tornado — иначе extreme outliers
  // (product_code с extreme spread) скрывают реальный picture.
  const sortedDesc = [...props.data.purchases]
    .filter((r) => !r.is_dirty)
    .sort((a, b) => b.deviation_pct - a.deviation_pct);
  const overpayers = sortedDesc.filter((r) => r.deviation_pct > 0).slice(0, 9);
  const saversRaw = sortedDesc.filter((r) => r.deviation_pct < 0);
  // Bottom-6 savers = последние 6 (наибольший savings первыми → ascending end of list)
  const savers = saversRaw.slice(-6);
  // Visual order: overpayers (high→low) затем savers (slight→deep) для tornado bookends
  const rows: ClosureRow[] = [...overpayers, ...savers];
  rowsCache = rows;

  // line 22030: labels — "company · category"
  const labels = rows.map((r) => `${r.company_name} · ${r.category_name}`);
  // line 22031: values — pct or rub-millions
  const values = rows.map((r) =>
    fmt === "rub" ? Math.round(Number(r.deviation_abs) / 1e6) : r.deviation_pct,
  );

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
        const r = rows[i];
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
        backgroundColor: rows.map((r) => paColorByDev(r.deviation_pct)),
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
              const r = rows[c.dataIndex];
              const devTxt = fmt.fmtPercent(r.deviation_pct, { decimals: 1, signed: true });
              const devRub = (r.deviation_abs >= 0 ? "+" : "") + paFmtMoneyShort(Math.abs(Number(r.deviation_abs))) + " сум";
              return [
                "Цена компании: " + paFmtMoney(r.unit_price) + " / " + (r.category_unit || "ед"),
                "Средняя рынка: " + paFmtMoney(r.market_avg),
                "Отклонение: " + devTxt + " (" + devRub + ")",
                "Кликни для детализации",
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
      // line 22126-22131: click → drill modal + select co
      onClick: (_e: any, els: any[]) => {
        if (!els.length) return;
        const r = rowsCache[els[0].index];
        if (!r) return;
        emit("drill", r);
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
.pa-tornado-host {
  position: relative;
  height: 480px;
  width: 100%;
}
.pa-tornado-host canvas {
  display: block;
  width: 100% !important;
  height: 100% !important;
}
</style>
