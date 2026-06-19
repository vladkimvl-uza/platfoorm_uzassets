<script setup lang="ts">
/**
 * CreditDonut — универсальный донат-чарт со средним числом и легендой.
 *
 * 1:1 порт cpRenderSignatureDonut (lines 25883–25974 легасиа).
 * Не зависит от shape backend-данных — принимает абстрактные DonutEntry[].
 */
import { Chart, type ChartConfiguration } from "@/utils/chartjsRegister";
import { computed, onBeforeUnmount, onMounted, ref, watch } from "vue";
import Odometer from "@/components/Odometer.vue";

export interface DonutEntry {
  label: string;
  color: string;
  value: number;
  sub?: string;
  meta?: Record<string, any>;
}

const props = defineProps<{
  entries: DonutEntry[];
  centerValue: string;
  centerLabel: string;
  hoverFmt?: (entry: DonutEntry, total: number) => [string, string];
  clickable?: boolean;
  size?: number;
}>();

const emit = defineEmits<{
  (e: "slice-click", entry: DonutEntry, idx: number): void;
}>();

const canvasEl = ref<HTMLCanvasElement | null>(null);
const centerNum = ref(props.centerValue);
const centerLbl = ref(props.centerLabel);
let chart: Chart | null = null;

const totalValue = computed(() =>
  props.entries.reduce((s, e) => s + Math.abs(e.value), 0),
);

const sizePx = computed(() => props.size || 140);

function buildConfig(): ChartConfiguration {
  const labels = props.entries.map((e) => e.label);
  const values = props.entries.map((e) => Math.abs(e.value));
  const colors = props.entries.map((e) => e.color);

  return {
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
        } as any,
      ],
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
      onHover: (e, els) => {
        const target = (e.native as MouseEvent | undefined)?.target as
          | HTMLElement
          | undefined;
        if (target) {
          target.style.cursor = els.length && props.clickable ? "pointer" : "default";
        }
        if (els.length) {
          const idx = els[0].index;
          const entry = props.entries[idx];
          const fmt =
            props.hoverFmt ||
            ((e: DonutEntry) => [String(e.value), e.label] as [string, string]);
          const [num, lbl] = fmt(entry, totalValue.value);
          centerNum.value = num;
          centerLbl.value = lbl;
        } else {
          centerNum.value = props.centerValue;
          centerLbl.value = props.centerLabel;
        }
      },
      onClick: (_evt, els) => {
        if (!els.length || !props.clickable) return;
        emit("slice-click", props.entries[els[0].index], els[0].index);
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
  centerNum.value = props.centerValue;
  centerLbl.value = props.centerLabel;
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
  () => [props.entries, props.centerValue, props.centerLabel] as const,
  render,
  { deep: true },
);

function onLegendClick(idx: number) {
  if (!props.clickable) return;
  emit("slice-click", props.entries[idx], idx);
}

// Наведение на строку легенды тоже подменяет центр-число (паритет с бывшим
// SignatureDonut — теперь единый донат покрывает оба сценария).
function onLegendEnter(idx: number) {
  const entry = props.entries[idx];
  const fmt =
    props.hoverFmt ||
    ((e: DonutEntry) => [String(e.value), e.label] as [string, string]);
  const [num, lbl] = fmt(entry, totalValue.value);
  centerNum.value = num;
  centerLbl.value = lbl;
}
function onLegendLeave() {
  centerNum.value = props.centerValue;
  centerLbl.value = props.centerLabel;
}

function pctOf(v: number): number {
  return totalValue.value ? Math.round((Math.abs(v) / totalValue.value) * 100) : 0;
}
</script>

<template>
  <div class="cp-donut-host">
    <div
      class="cp-donut-canvas-wrap"
      :style="{ width: sizePx + 'px', height: sizePx + 'px' }"
    >
      <canvas ref="canvasEl" :width="sizePx" :height="sizePx" />
      <div class="cp-donut-center">
        <div class="cp-donut-center-num"><Odometer :value="centerNum" /></div>
        <div class="cp-donut-center-lbl">{{ centerLbl }}</div>
      </div>
    </div>

    <div class="cp-donut-legend">
      <div
        v-for="(e, i) in entries"
        :key="i"
        class="cp-donut-leg-row"
        :class="{ clickable }"
        :style="{ animationDelay: i * 80 + 400 + 'ms' }"
        @click="onLegendClick(i)"
        @mouseenter="onLegendEnter(i)"
        @mouseleave="onLegendLeave()"
      >
        <div class="cp-donut-leg-dot" :style="{ background: e.color }" />
        <span class="cp-donut-leg-label">{{ e.label }}</span>
        <span v-if="e.sub" class="cp-donut-leg-sub">
          {{ e.sub }}
          <span class="cp-donut-leg-sep">·</span>
          {{ pctOf(e.value) }}%
        </span>
        <span v-else class="cp-donut-leg-pct">{{ pctOf(e.value) }}%</span>
      </div>
    </div>
  </div>
</template>

<style scoped>
.cp-donut-host {
  display: flex;
  align-items: center;
  gap: 14px;
  padding: 10px 14px;
}

.cp-donut-canvas-wrap {
  position: relative;
  flex-shrink: 0;
}

.cp-donut-center {
  position: absolute;
  inset: 0;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  pointer-events: none;
  text-align: center;
}

.cp-donut-center-num {
  font-size: 22px;
  font-weight: 500;
  color: var(--t1, #1e2a4a);
  letter-spacing: -0.04em;
  font-feature-settings: "tnum";
  animation: cpFadeNum 0.5s ease 600ms both;
}

.cp-donut-center-lbl {
  font-size: 8.5px;
  color: var(--t3, var(--t-muted));
  font-weight: 500;
  text-transform: uppercase;
  letter-spacing: 0.18em;
  margin-top: 2px;
  animation: cpFadeNum 0.5s ease 700ms both;
}

@keyframes cpFadeNum {
  from { opacity: 0; transform: translateY(4px); }
  to   { opacity: 1; transform: translateY(0); }
}

.cp-donut-legend {
  flex: 1;
  min-width: 0;
}

.cp-donut-leg-row {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 4px 8px;
  border-radius: 4px;
  animation: cpFadeSlideIn 0.3s ease both;
  transition: background 0.12s;
}

.cp-donut-leg-row.clickable { cursor: pointer; }
.cp-donut-leg-row.clickable:hover { background: rgba(0, 0, 0, 0.04); }

@keyframes cpFadeSlideIn {
  from { opacity: 0; transform: translateX(-6px); }
  to   { opacity: 1; transform: translateX(0); }
}

.cp-donut-leg-dot {
  width: 8px;
  height: 8px;
  border-radius: 2px;
  flex-shrink: 0;
  opacity: 0.85;
}

.cp-donut-leg-label {
  font-size: 11px;
  color: var(--t2, #555c6e);
  flex: 1;
  min-width: 0;
  font-weight: 500;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.cp-donut-leg-sub {
  font-size: 11px;
  font-weight: 600;
  color: var(--t1, #1e2a4a);
  font-feature-settings: "tnum";
  font-variant-numeric: tabular-nums;
  flex-shrink: 0;
  white-space: nowrap;
  text-align: right;
}

.cp-donut-leg-sep {
  color: var(--t3, var(--t-muted));
  font-weight: 400;
  margin: 0 2px;
}

.cp-donut-leg-pct {
  font-size: 11px;
  font-weight: 600;
  color: var(--t1, #1e2a4a);
  font-feature-settings: "tnum";
  font-variant-numeric: tabular-nums;
  min-width: 32px;
  text-align: right;
  flex-shrink: 0;
}
</style>
