<template>
  <div class="sig-donut">
    <div class="sd-chart">
      <canvas :id="canvasId" ref="canvasRef" :width="size" :height="size" />
      <div class="sd-center">
        <div :id="centerNumId" class="sd-center-num">{{ centerValue }}</div>
        <div :id="centerLblId" class="sd-center-lbl">{{ centerLabel }}</div>
      </div>
    </div>

    <div :id="legId" class="sd-legend">
      <div
        v-for="(e, i) in entries"
        :key="i"
        class="sd-leg-row"
        :class="{ clickable: !!onSliceClick }"
        :style="{ animationDelay: `${i * 80 + 400}ms` }"
        @click="onSliceClick && onSliceClick(e, i)"
        @mouseover="onLegendHover(i)"
        @mouseleave="onLegendLeave"
      >
        <div class="sd-leg-dot" :style="{ background: e.color }" />
        <span class="sd-leg-label">{{ e.label }}</span>
        <span class="sd-leg-meta">
          <template v-if="e.sub">
            {{ e.sub }} <span class="sd-sep">·</span> {{ pctFor(e) }}%
          </template>
          <template v-else>
            {{ pctFor(e) }}%
          </template>
        </span>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
/**
 *
 *   cutout: '84%', hoverOffset: 8, borderRadius: 6,
 *   borderColor: 'rgba(255,255,255,0.90)', borderWidth: 3,
 *   animation: { duration: 700, easing: 'easeOutQuart', animateRotate: true }
 *
 * Hover on slice → center text swaps to slice value/label.
 * Hover on legend row → highlights matching slice (same swap).
 * Click on slice OR legend row → triggers onSliceClick callback.
 *
 * Center text returns to defaults on mouse leave.
 *
 */
import { onBeforeUnmount, onMounted, ref, watch } from "vue";

export interface SignatureDonutEntry {
  label: string;
  color: string;
  value: number;
  /** Optional secondary text shown before the percentage in the legend (e.g. formatted amount) */
  sub?: string;
}

const props = withDefaults(
  defineProps<{
    entries: SignatureDonutEntry[];
    /** Default text in center (when no slice hovered) */
    centerValue: string;
    centerLabel: string;
    /** Canvas size in px (square) */
    size?: number;
    /** Optional slice click callback */
    onSliceClick?: (entry: SignatureDonutEntry, idx: number) => void;
    /** Override the hover-swap formatter: returns [centerNumber, centerLabel] */
    hoverFmt?: (e: SignatureDonutEntry, total: number) => [string, string];
    /** Stable id base — auto-generated if absent */
    idBase?: string;
  }>(),
  {
    size: 220,
  },
);

const canvasRef = ref<HTMLCanvasElement | null>(null);

// Stable IDs across re-renders
const _id = props.idBase || `sd-${Math.random().toString(36).slice(2, 9)}`;
const canvasId = `${_id}-c`;
const legId = `${_id}-l`;
const centerNumId = `${_id}-n`;
const centerLblId = `${_id}-b`;

let chartInstance: unknown = null;

function getChartLib(): {
  Chart: typeof globalThis & { Chart?: unknown };
} | null {
  if (typeof window === "undefined") return null;
  const w = window as unknown as { Chart?: unknown };
  return w.Chart ? (w as unknown as { Chart: unknown } as never) : null;
}

function totalValue(): number {
  return props.entries.reduce((s, e) => s + Math.abs(e.value), 0);
}

function pctFor(e: SignatureDonutEntry): number {
  const t = totalValue();
  return t > 0 ? Math.round((Math.abs(e.value) / t) * 100) : 0;
}

function defaultHoverFmt(e: SignatureDonutEntry): [string, string] {
  return [String(e.value), e.label];
}

function onLegendHover(idx: number) {
  const numEl = document.getElementById(centerNumId);
  const lblEl = document.getElementById(centerLblId);
  if (!numEl || !lblEl) return;
  const e = props.entries[idx];
  if (!e) return;
  const fmt = props.hoverFmt || defaultHoverFmt;
  const pair = fmt(e, totalValue());
  numEl.textContent = pair[0];
  lblEl.textContent = pair[1];
}

function onLegendLeave() {
  const numEl = document.getElementById(centerNumId);
  const lblEl = document.getElementById(centerLblId);
  if (!numEl || !lblEl) return;
  numEl.textContent = props.centerValue;
  lblEl.textContent = props.centerLabel;
}

function build() {
  const cv = canvasRef.value;
  if (!cv) return;
  const w = window as unknown as { Chart?: { getChart?: (cv: HTMLCanvasElement) => { destroy: () => void } | undefined } & ((cv: HTMLCanvasElement, cfg: unknown) => unknown) };
  const ChartGlobal = w.Chart;
  if (!ChartGlobal) {
    console.warn("[SignatureDonut] Chart.js not found on window. Load it via your app entrypoint.");
    return;
  }

  // Destroy prev
  const existing = ChartGlobal.getChart && ChartGlobal.getChart(cv);
  if (existing) {
    try { existing.destroy(); } catch { /* swallow */ }
  }

  const labels = props.entries.map((e) => e.label);
  const values = props.entries.map((e) => Math.abs(e.value));
  const colors = props.entries.map((e) => e.color);

  const ctx = cv;
  const ChartCtor = ChartGlobal as unknown as new (c: HTMLCanvasElement, cfg: unknown) => unknown;
  chartInstance = new ChartCtor(ctx, {
    type: "doughnut",
    data: {
      labels,
      datasets: [
        {
          data: values,
          backgroundColor: colors,
          borderColor: "rgba(255,255,255,0.90)",
          borderWidth: 3,
          hoverOffset: 8,
          borderRadius: 6,
        },
      ],
    },
    options: {
      responsive: false,
      maintainAspectRatio: false,
      cutout: "84%",
      plugins: { legend: { display: false }, tooltip: { enabled: false } },
      animation: { animateRotate: true, duration: 700, easing: "easeOutQuart" },
      onHover: (e: { native?: { target?: HTMLElement } }, els: { index: number }[]) => {
        if (e.native && e.native.target) {
          e.native.target.style.cursor =
            els && els.length && typeof props.onSliceClick === "function" ? "pointer" : "default";
        }
        const numEl = document.getElementById(centerNumId);
        const lblEl = document.getElementById(centerLblId);
        if (!numEl || !lblEl) return;
        if (els && els.length) {
          const idx = els[0].index;
          const entry = props.entries[idx];
          if (!entry) return;
          const fmt = props.hoverFmt || defaultHoverFmt;
          const pair = fmt(entry, totalValue());
          numEl.textContent = pair[0];
          lblEl.textContent = pair[1];
        } else {
          numEl.textContent = props.centerValue;
          lblEl.textContent = props.centerLabel;
        }
      },
      onClick: (_e: unknown, els: { index: number }[]) => {
        if (!els || !els.length || typeof props.onSliceClick !== "function") return;
        const idx = els[0].index;
        const entry = props.entries[idx];
        if (entry) props.onSliceClick(entry, idx);
      },
    },
  });
}

onMounted(build);

watch(
  () => props.entries,
  () => { build(); },
  { deep: true },
);

onBeforeUnmount(() => {
  if (chartInstance && typeof (chartInstance as { destroy?: () => void }).destroy === "function") {
    try { (chartInstance as { destroy: () => void }).destroy(); } catch { /* swallow */ }
    chartInstance = null;
  }
});
</script>

<style scoped>
.sig-donut {
  display: grid;
  grid-template-columns: auto 1fr;
  gap: 18px;
  align-items: center;
}

@media (max-width: 600px) {
  .sig-donut { grid-template-columns: 1fr; }
}

.sd-chart {
  position: relative;
  width: var(--sd-size, 220px);
  height: var(--sd-size, 220px);
}

.sd-center {
  position: absolute;
  inset: 0;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  pointer-events: none;
  text-align: center;
}

.sd-center-num {
  font-size: 24px;
  font-weight: 500;
  color: var(--t1, #1e2a4a);
  letter-spacing: -.025em;
  font-feature-settings: 'tnum';
  line-height: 1.15;
}

.sd-center-lbl {
  font-size: 10px;
  font-weight: 600;
  letter-spacing: .07em;
  text-transform: uppercase;
  color: rgba(15, 23, 60, .55);
  margin-top: 3px;
}

.sd-legend {
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 0;
}

.sd-leg-row {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 4px 8px;
  border-radius: 4px;
  animation: fadeSlideIn .3s ease both;
  transition: background .12s;
}

.sd-leg-row:hover {
  background: rgba(15, 23, 60, .04);
}

.sd-leg-row.clickable {
  cursor: pointer;
}

@keyframes fadeSlideIn {
  from {
    opacity: 0;
    transform: translateX(-6px);
  }
  to {
    opacity: 1;
    transform: translateX(0);
  }
}

.sd-leg-dot {
  width: 8px;
  height: 8px;
  border-radius: 2px;
  flex-shrink: 0;
  opacity: .85;
}

.sd-leg-label {
  font-size: 11px;
  color: rgba(15, 23, 60, .65);
  flex: 1;
  min-width: 0;
  font-weight: 500;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.sd-leg-meta {
  font-size: 11px;
  font-weight: 600;
  color: var(--t1, #1e2a4a);
  font-feature-settings: 'tnum';
  font-variant-numeric: tabular-nums;
  flex-shrink: 0;
  white-space: nowrap;
  text-align: right;
  min-width: 32px;
}

.sd-sep {
  color: rgba(15, 23, 60, .35);
  font-weight: 400;
  margin: 0 2px;
}
</style>
