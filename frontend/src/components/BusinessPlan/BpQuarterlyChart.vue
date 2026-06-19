<script setup lang="ts">
/**
 * BpQuarterlyChart — премиум-комбо: бары план/факт по кварталам + линия
 * нарастающего итога (YTD) + % выполнения (цветом). Hover-тултип, клик → drill,
 * анимации роста баров и draw-in линии.
 */
import { computed, onMounted, onUnmounted, ref } from "vue";

interface QuarterRow { q: string; plan: number | null; fact: number | null; expect?: number | null }

const props = defineProps<{
  quarters: QuarterRow[];
  label?: string;
  /** Форматтер значения (напр. fmtBn) */
  fmt: (n: number) => string;
}>();

const emit = defineEmits<{ drill: [{ row: QuarterRow; index: number }] }>();

// ─── Геометрия (адаптивная: график заполняет виджет по высоте через
// ResizeObserver — бары крупные и прижаты к низу, без пустого места снизу) ───
const chartEl = ref<HTMLElement | null>(null);
const W = ref(560);
const H = ref(240);
const PAD = { t: 26, r: 14, b: 44, l: 14 };
const plotW = computed(() => W.value - PAD.l - PAD.r);
const plotH = computed(() => H.value - PAD.t - PAD.b);

const rows = computed(() => props.quarters || []);
const n = computed(() => Math.max(1, rows.value.length));
const slot = computed(() => plotW.value / n.value);

let ro: ResizeObserver | null = null;
onMounted(() => {
  const el = chartEl.value;
  if (el && typeof ResizeObserver !== "undefined") {
    ro = new ResizeObserver((entries) => {
      const r = entries[0]?.contentRect;
      if (r && r.width > 4 && r.height > 4) { W.value = Math.round(r.width); H.value = Math.round(r.height); }
    });
    ro.observe(el);
  }
});
onUnmounted(() => { ro?.disconnect(); ro = null; });

// Нарастающий итог (факт → ожидание → план как оценка)
const cumVals = computed(() => {
  let acc = 0;
  return rows.value.map((q) => (acc += (q.fact ?? q.expect ?? q.plan ?? 0)));
});
// ЕДИНАЯ шкала для баров и линии итога: первая точка итога (= Q1) совпадает по
// высоте с баром Q1, а линия всегда ≥ баров (как и должно быть у нарастающего
// итога). Раньше бары и линия масштабировались по разным максимумам — из-за
// чего точка Q1 «проваливалась» под бар.
const scaleMax = computed(() => {
  let m = 0;
  for (const q of rows.value) {
    if (q.plan != null) m = Math.max(m, q.plan);
    if (q.fact != null) m = Math.max(m, q.fact);
  }
  for (const c of cumVals.value) m = Math.max(m, c);
  return m || 1;
});

function centerX(i: number) { return PAD.l + slot.value * i + slot.value / 2; }
function barY(v: number) { return PAD.t + plotH.value - (v / scaleMax.value) * plotH.value; }
function barHt(v: number) { return (v / scaleMax.value) * plotH.value; }

const cumPoints = computed(() => {
  const cum = cumVals.value;
  const out: { x: number; y: number; v: number }[] = [];
  rows.value.forEach((_, i) => {
    out.push({ x: centerX(i), y: PAD.t + plotH.value - (cum[i] / scaleMax.value) * plotH.value, v: cum[i] });
  });
  return out;
});
const cumLine = computed(() => cumPoints.value.map((p) => `${p.x},${p.y}`).join(" "));
const cumLen = computed(() => {
  let len = 0;
  const pts = cumPoints.value;
  for (let i = 1; i < pts.length; i++) {
    len += Math.hypot(pts[i].x - pts[i - 1].x, pts[i].y - pts[i - 1].y);
  }
  return Math.ceil(len) || 1;
});

function execPct(q: QuarterRow): number | null {
  if (q.plan == null || q.plan === 0 || q.fact == null) return null;
  return Math.round((q.fact / q.plan) * 100);
}
function execColor(pct: number | null): string {
  if (pct == null) return "#94A3B8";
  if (pct >= 100) return "#1D9E75";
  if (pct >= 80) return "#A36500";
  return "#C5352F";
}

const hovered = ref<number | null>(null);
function tip(i: number) {
  const q = rows.value[i];
  const pct = execPct(q);
  const delta = (q.fact != null && q.plan != null) ? q.fact - q.plan : null;
  return { q, pct, delta, cum: cumPoints.value[i]?.v ?? 0 };
}
</script>

<template>
  <div class="bqc">
    <div class="bqc-hd">
      <span class="bqc-t">Динамика по кварталам<span v-if="label"> · {{ label }}</span></span>
      <span class="bqc-legend">
        <span><i class="bqc-sw bqc-sw-plan" />План</span>
        <span><i class="bqc-sw bqc-sw-fact" />Факт</span>
        <span><i class="bqc-sw bqc-sw-cum" />Нараст. итог</span>
      </span>
    </div>

    <div class="bqc-chart" ref="chartEl">
      <svg :viewBox="`0 0 ${W} ${H}`" class="bqc-svg" preserveAspectRatio="none">
        <!-- Бары + значения -->
        <g v-for="(q, i) in rows" :key="q.q"
           class="bqc-grp" :class="{ on: hovered === i }"
           @mouseenter="hovered = i" @mouseleave="hovered = null"
           @click="emit('drill', { row: q, index: i })">
          <!-- hover-подсветка слота -->
          <rect :x="PAD.l + slot * i" :y="PAD.t" :width="slot" :height="plotH" class="bqc-slot" />
          <!-- план -->
          <rect v-if="q.plan != null" class="bqc-bar bqc-bar-plan"
                :x="centerX(i) - 17" :y="barY(q.plan)" width="15" :height="barHt(q.plan)" rx="3"
                :style="{ '--gh': barHt(q.plan) + 'px', animationDelay: i * 90 + 'ms' }" />
          <!-- факт -->
          <rect v-if="q.fact != null" class="bqc-bar bqc-bar-fact"
                :x="centerX(i) + 2" :y="barY(q.fact)" width="15" :height="barHt(q.fact)" rx="3"
                :style="{ '--gh': barHt(q.fact) + 'px', animationDelay: i * 90 + 60 + 'ms' }" />
          <!-- значение сверху (факт приоритетнее) -->
          <text v-if="q.fact != null" class="bqc-val bqc-val-fact" :x="centerX(i) + 9" :y="barY(q.fact) - 7" text-anchor="middle">{{ fmt(q.fact) }}</text>
          <text v-else-if="q.plan != null" class="bqc-val" :x="centerX(i) - 9" :y="barY(q.plan) - 7" text-anchor="middle">{{ fmt(q.plan) }}</text>
          <!-- метка квартала -->
          <text class="bqc-qlbl" :x="centerX(i)" :y="H - 28" text-anchor="middle">{{ q.q.toUpperCase() }}</text>
          <!-- % выполнения -->
          <text class="bqc-pct" :x="centerX(i)" :y="H - 12" text-anchor="middle"
                :style="{ fill: execColor(execPct(q)) }">
            {{ execPct(q) != null ? execPct(q) + '%' : '—' }}
          </text>
        </g>

        <!-- Линия нарастающего итога -->
        <polyline class="bqc-cum-line" :points="cumLine" fill="none"
                  :style="{ strokeDasharray: cumLen, strokeDashoffset: cumLen }" />
        <g v-for="(p, i) in cumPoints" :key="'c' + i">
          <circle class="bqc-cum-dot" :cx="p.x" :cy="p.y" r="3.5" :style="{ animationDelay: 500 + i * 110 + 'ms' }" />
        </g>
      </svg>

      <!-- Hover-тултип -->
      <div v-if="hovered != null" class="bqc-tip"
           :style="{ left: (centerX(hovered) / W * 100) + '%' }">
        <div class="bqc-tip-h">{{ rows[hovered].q.toUpperCase() }}</div>
        <div class="bqc-tip-r"><span>План</span><b>{{ rows[hovered].plan != null ? fmt(rows[hovered].plan!) : '—' }}</b></div>
        <div class="bqc-tip-r"><span>Факт</span><b>{{ rows[hovered].fact != null ? fmt(rows[hovered].fact!) : '—' }}</b></div>
        <div class="bqc-tip-r" v-if="tip(hovered).pct != null"><span>Выполнение</span><b :style="{ color: execColor(tip(hovered).pct) }">{{ tip(hovered).pct }}%</b></div>
        <div class="bqc-tip-r" v-if="tip(hovered).delta != null"><span>Дельта</span><b :style="{ color: tip(hovered).delta! >= 0 ? '#1D9E75' : '#C5352F' }">{{ tip(hovered).delta! >= 0 ? '+' : '' }}{{ fmt(tip(hovered).delta!) }}</b></div>
        <div class="bqc-tip-r"><span>Нараст. итог</span><b>{{ fmt(tip(hovered).cum) }}</b></div>
        <div class="bqc-tip-cta">Открыть разбор →</div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.bqc { display: flex; flex-direction: column; flex: 1; min-height: 0; }
.bqc-hd { display: flex; align-items: center; justify-content: space-between; gap: 10px; flex-wrap: wrap; margin-bottom: 6px; }
.bqc-t { font-size: 11px; font-weight: 600; text-transform: uppercase; letter-spacing: .05em; color: var(--t3, #94A3B8); }
.bqc-legend { display: inline-flex; gap: 12px; font-size: 10px; color: var(--t3, #8B889C); }
.bqc-legend span { display: inline-flex; align-items: center; gap: 4px; }
.bqc-sw { width: 9px; height: 9px; border-radius: 2px; display: inline-block; }
.bqc-sw-plan { background: #C7C2F0; }
.bqc-sw-fact { background: #7F77DD; }
.bqc-sw-cum { background: #EF9F27; border-radius: 50%; }

.bqc-chart { position: relative; height: clamp(220px, 26vh, 340px); }
.bqc-svg { width: 100%; height: 100%; display: block; overflow: visible; }

.bqc-grp { cursor: pointer; }
.bqc-slot { fill: transparent; rx: 8; transition: fill .14s; }
.bqc-grp.on .bqc-slot { fill: rgba(124,111,247,.06); }

.bqc-bar { transform-origin: bottom; transform-box: fill-box; animation: bqcGrow .55s cubic-bezier(.34,1.1,.64,1) both; }
.bqc-bar-plan { fill: #C7C2F0; }
.bqc-bar-fact { fill: #7F77DD; }
.bqc-grp.on .bqc-bar-fact { fill: #6C5CE7; }
@keyframes bqcGrow { from { transform: scaleY(0); opacity: .3; } to { transform: scaleY(1); opacity: 1; } }

.bqc-val { font-size: 10px; font-weight: 500; fill: var(--t3, #94A3B8); font-variant-numeric: tabular-nums; }
.bqc-val-fact { fill: var(--t1, #1A1730); font-weight: 700; }
.bqc-qlbl { font-size: 11px; font-weight: 600; fill: var(--t2, #6B6880); }
.bqc-pct { font-size: 10px; font-weight: 700; font-variant-numeric: tabular-nums; }

.bqc-cum-line {
  stroke: #EF9F27; stroke-width: 2; stroke-linecap: round; stroke-linejoin: round;
  animation: bqcDraw 1s ease .35s forwards;
}
@keyframes bqcDraw { to { stroke-dashoffset: 0; } }
.bqc-cum-dot { fill: #fff; stroke: #EF9F27; stroke-width: 2; animation: bqcDot .3s ease both; }
@keyframes bqcDot { from { opacity: 0; transform: scale(0); } to { opacity: 1; transform: scale(1); } }

.bqc-tip {
  position: absolute; top: 0; transform: translateX(-50%);
  background: #1B1730; color: #fff; border-radius: 10px; padding: 9px 11px;
  font-size: 11px; min-width: 150px; pointer-events: none; z-index: 5;
  box-shadow: 0 12px 30px rgba(20,16,50,.4); animation: bqcTipIn .14s ease;
}
@keyframes bqcTipIn { from { opacity: 0; transform: translateX(-50%) translateY(-4px); } to { opacity: 1; transform: translateX(-50%); } }
.bqc-tip-h { font-size: 12px; font-weight: 700; margin-bottom: 5px; }
.bqc-tip-r { display: flex; justify-content: space-between; gap: 14px; padding: 1.5px 0; }
.bqc-tip-r span { color: rgba(255,255,255,.55); }
.bqc-tip-r b { font-weight: 600; font-variant-numeric: tabular-nums; }
.bqc-tip-cta { margin-top: 6px; padding-top: 5px; border-top: 1px solid rgba(255,255,255,.12); color: #C7C2F0; font-size: 10px; }

@media (prefers-reduced-motion: reduce) {
  .bqc-bar, .bqc-cum-line, .bqc-cum-dot { animation: none; }
  .bqc-cum-line { stroke-dashoffset: 0 !important; }
}
</style>
