<template>
  <div class="bpd-spark" :style="{ '--clr': color }">
    <svg
      class="bpd-spark-svg"
      :viewBox="`0 0 ${W} ${H}`"
      preserveAspectRatio="xMidYMid meet"
    >
      <!-- Zero baseline (only if min < 0) -->
      <line
        v-if="bounds.min < 0"
        :x1="pad.l"
        :y1="sy(0)"
        :x2="W - pad.r"
        :y2="sy(0)"
        stroke="rgba(30, 42, 74, .18)"
        stroke-width="0.5"
        stroke-dasharray="2 3"
      />

      <!-- Plan line (dashed grey) -->
      <polyline
        v-if="planPts.length >= 2"
        class="bpd-spark-plan"
        :points="planPtsStr"
        fill="none"
        stroke="#94A3B8"
        stroke-width="1.4"
        stroke-dasharray="3 4"
      />

      <!-- Fact line (solid colored) -->
      <path
        v-if="factPts.length >= 2"
        class="bpd-spark-fact"
        :d="factPath"
        fill="none"
        :stroke="color"
        stroke-width="2"
        stroke-linecap="round"
        stroke-linejoin="round"
      />

      <!-- Dots + value labels -->
      <template v-for="(pt, i) in factPts" :key="`dot-${i}`">
        <circle
          v-if="pt"
          :cx="pt.x"
          :cy="pt.y"
          r="3.5"
          fill="#fff"
          :stroke="color"
          stroke-width="1.5"
          class="bpd-spark-dot"
          :style="{ '--bpd-dd': `${i * 100}ms` }"
        />
        <text
          v-if="pt"
          :x="pt.x"
          :y="pt.y + (i === 0 || (factVals[i - 1] != null && factVals[i - 1]! < factVals[i]!) ? -10 : 16)"
          font-size="10"
          font-weight="600"
          fill="#1E2A4A"
          text-anchor="middle"
          class="bpd-spark-vl"
          :style="{ '--bpd-dd': `${i * 100 + 200}ms` }"
        >{{ formatVal(factVals[i]) }}</text>
      </template>

      <!-- Year labels along bottom -->
      <text
        v-for="(yr, i) in years"
        :key="`yr-${yr}`"
        :x="sx(i)"
        :y="H - pad.b + 14"
        font-size="9.5"
        :fill="'rgba(15, 23, 60, .55)'"
        text-anchor="middle"
        font-family="Geist, system-ui"
      >{{ yr }}</text>
    </svg>

    <!-- Legend -->
    <div class="bpd-spark-legend" v-if="showLegend">
      <span class="bpd-leg-i">
        <span class="bpd-leg-line" :style="{ background: color }" />факт
      </span>
      <span v-if="planPts.length >= 2" class="bpd-leg-i">
        <span class="bpd-leg-line bpd-leg-dashed" />план
      </span>
    </div>
  </div>
</template>

<script setup lang="ts">
/**
 *
 * Renders a small multi-year line chart with fact (solid colored) + optional plan
 * (dashed grey), value labels above/below dots, year labels along the bottom.
 *
 *   viewBox 0 0 800 120, padding L30 R30 T18 B22
 *   Dot radius 3.5, fact stroke-width 2, plan stroke-width 1.4 dashed 3 4
 *   Value labels offset -10px or +16px depending on relation to prior point
 *   Year labels font-size 9.5px Geist, fill var(--t3)
 *   Animations bpd-spark-dot / bpd-spark-vl with i*100ms / (i*100 + 200)ms staggers
 *
 * Auto-scales: if all values >0, baseline locked to 0; if any <0, shows dashed
 * zero line and scale extends to actual min.
 */
import { computed } from "vue";

const props = withDefaults(
  defineProps<{
    /** Array of fact values; null/undefined → gap in the line */
    fact: (number | null)[];
    /** Optional plan values (same length) — shown as dashed grey */
    plan?: (number | null)[];
    /** Year labels for x-axis (same length as fact) */
    years: number[];
    /** Line color (purple by default) */
    color?: string;
    /** Width in viewBox units (px) */
    width?: number;
    /** Height in viewBox units (px) */
    height?: number;
    /** Show plan/fact legend at bottom */
    showLegend?: boolean;
    /** Custom value formatter (defaults to compact short form) */
    fmt?: (v: number | null) => string;
  }>(),
  {
    color: "#7F77DD",
    width: 800,
    height: 120,
    showLegend: true,
  },
);

const W = props.width;
const H = props.height;
const pad = { l: 30, r: 30, t: 18, b: 22 };

// Bounds across both fact + plan
const bounds = computed(() => {
  const all = ([] as (number | null)[])
    .concat(props.fact)
    .concat(props.plan ?? [])
    .filter((v): v is number => v != null);
  if (!all.length) return { min: 0, max: 1 };
  let mn = Math.min(...all);
  let mx = Math.max(...all);
  if (mn === mx) {
    mn -= 1;
    mx += 1;
  }
  return { min: mn, max: mx };
});

const factVals = computed(() => props.fact);

function sx(i: number): number {
  const n = props.years.length - 1 || 1;
  const iw = W - pad.l - pad.r;
  return pad.l + (iw * i) / n;
}

function sy(v: number): number {
  const ih = H - pad.t - pad.b;
  const rng = bounds.value.max - bounds.value.min || 1;
  return pad.t + ih * (1 - (v - bounds.value.min) / rng);
}

interface Pt { x: number; y: number; }

const factPts = computed<(Pt | null)[]>(() =>
  props.fact.map((v, i) => (v != null ? { x: sx(i), y: sy(v) } : null)),
);

const planPts = computed<Pt[]>(() => {
  const arr: Pt[] = [];
  (props.plan ?? []).forEach((v, i) => {
    if (v != null) arr.push({ x: sx(i), y: sy(v) });
  });
  return arr;
});

const planPtsStr = computed(() =>
  planPts.value.map((p) => `${p.x},${p.y}`).join(" "),
);

const factPath = computed(() => {
  const pts = factPts.value.filter((p): p is Pt => p !== null);
  if (pts.length < 2) return "";
  let d = `M ${pts[0].x} ${pts[0].y}`;
  for (let i = 1; i < pts.length; i++) d += ` L ${pts[i].x} ${pts[i].y}`;
  return d;
});

function formatVal(v: number | null | undefined): string {
  if (v == null) return "";
  if (props.fmt) return props.fmt(v);
  // Default compact format
  const a = Math.abs(v);
  const sign = v < 0 ? "-" : "";
  if (a >= 1e9) return sign + (a / 1e9).toFixed(1).replace(/\.0$/, "");
  if (a >= 1e6) return sign + (a / 1e6).toFixed(1).replace(/\.0$/, "");
  if (a >= 1e3) return sign + (a / 1e3).toFixed(1).replace(/\.0$/, "");
  if (a >= 1) return sign + a.toFixed(0);
  return sign + a.toFixed(2);
}
</script>

<style scoped>
.bpd-spark {
  width: 100%;
}

.bpd-spark-svg {
  width: 100%;
  height: auto;
  display: block;
}

.bpd-spark-fact {
  stroke-dasharray: 3000;
  stroke-dashoffset: 3000;
  animation: drawFact 1.4s var(--ease-standard) forwards;
}

@keyframes drawFact {
  to { stroke-dashoffset: 0; }
}

.bpd-spark-plan {
  opacity: 0;
  animation: fadePlan .6s ease forwards;
  animation-delay: 200ms;
}

@keyframes fadePlan {
  to { opacity: 1; }
}

.bpd-spark-dot {
  opacity: 0;
  animation: dotIn .35s var(--ease-standard) forwards;
  animation-delay: var(--bpd-dd, 0ms);
}

@keyframes dotIn {
  from { opacity: 0; transform: scale(.4); }
  to { opacity: 1; transform: scale(1); }
}

.bpd-spark-dot {
  transform-origin: center;
  transform-box: fill-box;
}

.bpd-spark-vl {
  opacity: 0;
  animation: vlIn .3s ease forwards;
  animation-delay: var(--bpd-dd, 0ms);
}

@keyframes vlIn {
  from { opacity: 0; transform: translateY(-3px); }
  to { opacity: 1; transform: translateY(0); }
}

.bpd-spark-vl {
  transform-origin: center;
  transform-box: fill-box;
}

.bpd-spark-legend {
  display: flex;
  gap: 14px;
  margin-top: 8px;
  font-size: 10px;
  color: rgba(15, 23, 60, .55);
}

.bpd-leg-i {
  display: inline-flex;
  align-items: center;
  gap: 5px;
}

.bpd-leg-line {
  display: inline-block;
  width: 16px;
  height: 2px;
  border-radius: 1px;
  background: var(--clr, #7F77DD);
}

.bpd-leg-dashed {
  background: transparent;
  background-image: linear-gradient(to right, #94A3B8 50%, transparent 50%);
  background-size: 4px 2px;
  background-repeat: repeat-x;
}
</style>
