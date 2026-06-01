<script setup lang="ts">
/**
 * ExecDashBPTrackerBlock — Pack 7.27.
 *
 * строки 29830-30482 в исходнике index.html.
 *
 * Variant A — "Performance Spine":
 *   • Hero: огромное число % + delta vs прошлый год + like-for-like суммы справа
 *   • Performance Spine: горизонтальная шкала всех LL компаний, baseline=100%,
 *     bars вверх для лидеров (>100%), вниз для отстающих (<100%)
 *   • Guide-lines +50% / −40%, имена компаний под/над барами
 *   • Footer: segmented bar 8/2/3 с лейблами bucket
 *
 * Особенности:
 *   • 3 metrics: revenue / ebitda / profit (signed metric handling для двух последних)
 *   • Два режима: plan-fact (когда план есть у ≥30% компаний) или yoy
 *   • Empty state: без данных
 *   • Top-stripe карточки — градиент зелёный→жёлтый→красный с draw + breathe + shimmer
 *   • Анимация для каждого bar в SVG: stagger 40ms (bsd CSS var)
 */
import { computed, ref, watch } from "vue";
import { useExecutiveDashboard } from "@/composables/useExecutiveDashboard";
import { useSectorMeta } from "@/utils/sectorMeta";
import { useFormatters } from "@/composables/useFormatters";
import { useNumberTween } from "@/composables/useNumberTween";
import BusinessPlanDrillModal, { type BpKind } from "@/components/UZA/BusinessPlanDrillModal.vue";

const fmt = useFormatters();
const exec = useExecutiveDashboard();
const secMeta = useSectorMeta();

const block = computed(() => exec.data.value?.bp_tracker || null);

// 2026-05-26: countup tweens для 3 ключевых числовых выводов внизу
const tOnTarget  = useNumberTween(() => Number(block.value?.on_target) || 0, { duration: 900 });
const tAttention = useNumberTween(() => Number(block.value?.attention) || 0, { duration: 900 });
const tBehind    = useNumberTween(() => Number(block.value?.behind) || 0, { duration: 900 });
const rows = computed(() => block.value?.rows || []);

const METRIC_TITLES: Record<string, string> = {
  revenue: "Выручка",
  ebitda: "EBITDA",
  profit: "Прибыль",
};

const METRIC_LABELS: Record<string, string> = {
  revenue: "выручки",
  ebitda: "EBITDA",
  profit: "чистой прибыли",
};

const activeMetric = ref<string>("revenue");

watch(() => block.value?.metric, (m) => {
  if (m && m !== activeMetric.value) activeMetric.value = m;
});
watch(() => exec.bpMetric.value, (m) => {
  if (m && m !== activeMetric.value) activeMetric.value = m;
});

function setMetric(m: string): void {
  if (activeMetric.value === m) return;
  activeMetric.value = m;
  exec.setBpMetric(m);
}

const tabs = ["revenue", "ebitda", "profit"];

// Pack 7.33: BP drill-down modal
const sectorColorMap: Record<string, string> = {
  mining: "#7F77DD",
  oilgas: "#1D9E75",
  energy: "#EF9F27",
  transport: "#378ADD",
  other: "#888780",
};
const sectorLabelMap = computed<Record<string, string>>(() => {
  const map: Record<string, string> = {};
  const byCode = secMeta.byCodeMap.value;
  for (const code of Object.keys(byCode)) {
    map[code] = byCode[code as keyof typeof byCode]?.label || code;
  }
  return map;
});
const drillKind = ref<BpKind | null>(null);
function openDrill(kind: BpKind, e?: Event) {
  if (e) e.stopPropagation();
  if (!block.value || block.value.mode === "empty") return;
  drillKind.value = kind;
}
function closeDrill() { drillKind.value = null; }
function onCardClick(e: MouseEvent) {
  // Игнорим клики по tab-кнопкам и distribution-сегментам — у них свои handlers
  const t = e.target as HTMLElement | null;
  if (!t) return;
  if (t.closest(".ed-bp-tab") || t.closest(".ed-bp-distrib-seg")) return;
  openDrill("overall");
}
function onCardKeydown(e: KeyboardEvent) {
  if (e.key === "Enter" || e.key === " ") {
    const t = e.target as HTMLElement | null;
    if (t && (t.closest(".ed-bp-tab") || t.closest(".ed-bp-distrib-seg"))) return;
    e.preventDefault();
    openDrill("overall");
  }
}

// ─── Number formatters ─────────────────────────────────────────
// Note: input value is already scaled to "млрд" (billions). 1000 input = 1 трлн.
function fmtNum(v: number | null | undefined): string {
  if (v == null || isNaN(v)) return "—";
  if (Math.abs(v) >= 1000) return fmt.fmtNumber(v / 1000, { decimals: 1 }) + " трлн";
  if (Math.abs(v) >= 100) return fmt.fmtNumber(Math.round(v));
  return fmt.fmtNumber(v, { decimals: 1, minDecimals: 1 });
}

// ─── Hero number computed ─────────────────────────────────────
interface Hero {
  bigVal: string;
  bigUnit: string;       // 'млрд' | '%'
  bigColor: string;
  bigSub: string;
  deltaPP: number | null;  // дельта в п.п. vs предыдущий год
  llkLabels: { l1: string; v1: string; l2: string; v2: string };
}

const hero = computed<Hero | null>(() => {
  const b = block.value;
  if (!b) return null;
  const metric = b.metric || "revenue";
  const mLabel = METRIC_LABELS[metric] || metric;

  let bigVal = "—";
  let bigUnit = "";
  let bigColor = "#94A3B8";
  let bigSub = "";

  if (b.overall_pct != null) {
    const pctVal = Math.round(b.overall_pct * 100);
    if (b.mode === "plan-fact") {
      bigColor = pctVal >= 95 ? "#1D9E75" : pctVal >= 80 ? "#EF9F27" : "#E24B4A";
    } else {
      bigColor = pctVal >= 100 ? "#1D9E75" : pctVal >= 95 ? "#EF9F27" : "#E24B4A";
    }
    bigVal = String(pctVal);
    bigUnit = "%";
  } else if (b.is_signed_metric && b.overall_label) {
    const v = b.overall_delta ?? 0;
    bigVal = v >= 0 ? "+" + fmtNum(v) : fmtNum(v);
    bigUnit = "млрд";
    const positiveSignedLabels = ["выход из убытка", "убыток сокращён", "значительный рост", "план перевыполнен"];
    bigColor = positiveSignedLabels.includes(b.overall_label) ? "#1D9E75" : "#E24B4A";
  }

  if (b.overall_label) {
    bigSub = `${b.overall_label} · ${mLabel}`;
  } else if (b.mode === "plan-fact") {
    bigSub = `выполнение плана ${mLabel} по портфелю`;
  } else if (b.mode === "yoy") {
    bigSub = `динамика ${mLabel} к ${b.prev_year} году`;
  } else {
    bigSub = "";
  }

  let deltaPP: number | null = null;
  if (!b.is_signed_metric && b.prev_overall_pct != null && b.overall_pct != null) {
    deltaPP = Math.round((b.overall_pct - b.prev_overall_pct) * 1000) / 10;
    if (Math.abs(deltaPP) < 0.1) deltaPP = null;
  }

  let llkLabels;
  if (b.mode === "plan-fact") {
    llkLabels = {
      l1: "План (сравнимые)",
      v1: fmtNum(b.sum_plan_ll),
      l2: "Факт (сравнимые)",
      v2: fmtNum(b.sum_fact_plan_ll),
    };
  } else {
    llkLabels = {
      l1: `${b.prev_year} (сравнимые)`,
      v1: fmtNum(b.sum_prev_ll),
      l2: `${b.year} (сравнимые)`,
      v2: fmtNum(b.sum_fact_ll),
    };
  }

  return { bigVal, bigUnit, bigColor, bigSub, deltaPP, llkLabels };
});

// ─── Performance Spine SVG geometry ──────────────────────────
interface SpinePt {
  name: string;
  cls: string;
  p: number;       // 1.0 = baseline
  label: string;
  labelFull: string;
  delta: number | null;
}

const spinePts = computed<SpinePt[]>(() => {
  return rows.value
    .map((r) => {
      let p: number | null = null;
      let label: string | null = null;
      let labelFull: string | null = null;

      if (r.pct != null) {
        p = r.pct;
        label = r.display_pct != null ? r.display_pct + "%" : r.display_label || "";
        labelFull = r.display_label_full || label;
      } else if (r.display_label) {
        label = r.display_label;
        labelFull = r.display_label_full || label;
        if (r.cls === "ok") p = 1.20;
        else if (r.cls === "warn") p = 0.92;
        else p = 0.65;
      } else {
        return null;
      }

      return {
        name: r.name,
        cls: r.cls,
        p: p!,
        label,
        labelFull: labelFull!,
        delta: r.delta,
      } as SpinePt;
    })
    .filter((x): x is SpinePt => x != null)
    .sort((a, b) => b.p - a.p);
});

const SVG_W = 1280;
const SVG_H = 230;
const PAD = { l: 60, r: 60, t: 22, b: 70 };
const innerW = SVG_W - PAD.l - PAD.r;
const innerH = SVG_H - PAD.t - PAD.b;
const baselineY = PAD.t + innerH * 0.55;
const maxUp = baselineY - PAD.t - 8;
const maxDown = (PAD.t + innerH) - baselineY - 8;
const CLAMP_LO = 0.40;
const CLAMP_HI = 1.60;

function pctToY(p: number): number {
  if (p >= 1) {
    const up = Math.min(1, (p - 1) / (CLAMP_HI - 1));
    return baselineY - up * maxUp;
  } else {
    const dn = Math.min(1, (1 - p) / (1 - CLAMP_LO));
    return baselineY + dn * maxDown;
  }
}
function clsColor(cls: string): string {
  return cls === "ok" ? "#1D9E75" : cls === "warn" ? "#EF9F27" : cls === "bad" ? "#E24B4A" : "#888780";
}
function clsTextColor(cls: string): string {
  return cls === "ok" ? "#0F6E56" : cls === "warn" ? "#8A5F15" : cls === "bad" ? "#933632" : "#64748B";
}

interface RenderBar {
  cx: number;
  x: number;
  y: number;
  barW: number;
  barH: number;
  color: string;
  textColor: string;
  name: string;
  shortName: string;
  label: string;
  labelFull: string;
  fontSize: number;
  labelY: number;
  isAbove: boolean;
  nameY: number;
  rotated: boolean;
  rotateY: number;
  delta: number | null;
  staggerMs: number;
}

const renderBars = computed<RenderBar[]>(() => {
  const pts = spinePts.value;
  const n = pts.length;
  if (n === 0) return [];

  const slotW = innerW / n;
  const barW = Math.min(36, Math.max(14, slotW - 8));
  const dense = n > 8;

  return pts.map((pt, i) => {
    const cx = PAD.l + slotW * (i + 0.5);
    const x = cx - barW / 2;
    let y: number, barH: number;
    if (pt.p >= 1) {
      y = pctToY(pt.p);
      barH = baselineY - y;
    } else {
      y = baselineY;
      barH = pctToY(pt.p) - baselineY;
    }
    if (barH < 1.5) barH = 1.5;

    const color = clsColor(pt.cls);
    const textColor = clsTextColor(pt.cls);

    const labelLen = pt.label.length;
    const fontSize = labelLen > 7 ? 9.5 : 11;
    const isAbove = pt.p >= 1;
    const labelY = isAbove ? y - 6 : y + barH + 14;

    const maxNameLen = dense ? 18 : 12;
    const shortName = pt.name.length > maxNameLen ? pt.name.slice(0, maxNameLen - 1) + "…" : pt.name;
    const nameYRaw = isAbove ? (baselineY + 14) : (y + barH + 30);
    const rotateY = nameYRaw + 2;

    return {
      cx, x, y, barW, barH, color, textColor,
      name: pt.name, shortName,
      label: pt.label, labelFull: pt.labelFull, fontSize,
      labelY, isAbove,
      nameY: nameYRaw,
      rotated: dense,
      rotateY,
      delta: pt.delta,
      staggerMs: i * 40,
    };
  });
});

// Guide line Y positions
const yPlus50 = pctToY(1.50);
const yMinus40 = pctToY(0.60);

// Distribution bar
const distrib = computed(() => {
  const b = block.value;
  if (!b) return null;
  const total = (b.on_target || 0) + (b.attention || 0) + (b.behind || 0);
  if (total === 0) return null;
  const w1 = (b.on_target / total) * 100;
  const w2 = (b.attention / total) * 100;
  const w3 = (b.behind / total) * 100;

  let onTargetL: string, attentionL: string, behindL: string;
  if (b.is_signed_metric) {
    onTargetL = "В росте/восстановление";
    attentionL = "Лёгкое снижение";
    behindL = "Снижение/убыток";
  } else if (b.mode === "plan-fact") {
    onTargetL = "На цели (≥95%)";
    attentionL = "Внимание (80–94%)";
    behindL = "Отстают (<80%)";
  } else {
    onTargetL = "В росте (≥100%)";
    attentionL = "Лёгкое снижение (95–99%)";
    behindL = "Снижение (<95%)";
  }

  const srcL = b.mode === "plan-fact"
    ? "Источник: БП + НСБУ"
    : "Источник: НСБУ · режим YoY (план не заполнен)";

  return { w1, w2, w3, onTargetL, attentionL, behindL, srcL };
});

// Tooltip text per bar
function tooltipFor(b: RenderBar): string {
  const parts = [b.name, b.labelFull];
  if (b.delta != null) {
    parts.push((b.delta >= 0 ? "+" : "") + fmtNum(b.delta) + " млрд");
  }
  return parts.join(" · ");
}
</script>

<template>
  <section
    class="ed-bp-card"
    role="button"
    tabindex="0"
    @click="onCardClick"
    @keydown="onCardKeydown"
    title="Подробнее: бизнес-план портфеля"
  >
    <!-- ═══ HEADER ═══ -->
    <div class="ed-bp-head">
      <div class="ed-bp-head-l">
        <div class="ed-bp-head-t">Бизнес-план портфеля · годовое исполнение</div>
        <div class="ed-bp-head-s">{{ block?.head_sub || "Загрузка…" }}</div>
      </div>
      <div class="ed-bp-tabs">
        <button
          v-for="m in tabs"
          :key="m"
          class="ed-bp-tab"
          :class="{ on: activeMetric === m }"
          @click="setMetric(m)"
        >
          {{ METRIC_TITLES[m] }}
        </button>
      </div>
    </div>

    <!-- ═══ EMPTY STATE ═══ -->
    <div v-if="!block || block.mode === 'empty'" class="ed-bp-empty">
      <div class="ed-bp-empty-t">Нет данных для сравнения</div>
      <div class="ed-bp-empty-s">
        Для года {{ block?.year || exec.year.value }} не заполнен план в бизнес-плане,
        а факта прошлого года ({{ block?.prev_year || (exec.year.value - 1) }})
        недостаточно для расчёта YoY.
      </div>
    </div>

    <template v-else-if="hero">
      <!-- ═══ HERO ═══ -->
      <div class="ed-bp-spine-hero">
        <div class="ed-bp-spine-hero-l">
          <div class="ed-bp-big">
            <span class="ed-bp-big-v" :style="{ color: hero.bigColor }">{{ hero.bigVal }}</span>
            <span class="ed-bp-big-u">{{ hero.bigUnit }}</span>
            <span
              v-if="hero.deltaPP != null"
              class="ed-bp-delta"
              :class="hero.deltaPP > 0 ? 'up' : 'down'"
            >
              <svg v-if="hero.deltaPP >= 0" width="9" height="9" viewBox="0 0 10 10" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round">
                <path d="M5 8V2M2.5 4.5L5 2l2.5 2.5" />
              </svg>
              <svg v-else width="9" height="9" viewBox="0 0 10 10" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round">
                <path d="M5 2v6M2.5 5.5L5 8l2.5-2.5" />
              </svg>
              {{ fmt.fmtNumber(hero.deltaPP, { decimals: 1, minDecimals: 1, signed: true }) }} п.п.
            </span>
          </div>
          <div class="ed-bp-big-sub">{{ hero.bigSub }}</div>
        </div>
        <div class="ed-bp-spine-hero-r">
          <div class="ed-bp-llk">
            <span class="l">{{ hero.llkLabels.l1 }}</span>
            <span class="v">{{ hero.llkLabels.v1 }} млрд</span>
          </div>
          <div class="ed-bp-llk">
            <span class="l">{{ hero.llkLabels.l2 }}</span>
            <span class="v" :style="{ color: hero.bigColor }">{{ hero.llkLabels.v2 }} млрд</span>
          </div>
        </div>
      </div>

      <!-- ═══ PERFORMANCE SPINE ═══ -->
      <div v-if="renderBars.length === 0" class="ed-bp-empty-mini">
        Недостаточно данных для построения performance-шкалы
      </div>
      <div v-else class="ed-bp-spine-wrap">
        <svg
          class="ed-bp-spine-svg"
          :viewBox="`0 0 ${SVG_W} ${SVG_H}`"
          preserveAspectRatio="xMidYMid meet"
          role="img"
          aria-label="Performance spine — выполнение плана по компаниям"
        >
          <!-- Baseline 100% -->
          <line :x1="PAD.l" :y1="baselineY" :x2="SVG_W - PAD.r" :y2="baselineY"
                stroke="#1E2A4A" stroke-width="0.7" stroke-opacity="0.85" />

          <!-- +50% guide -->
          <line :x1="PAD.l" :y1="yPlus50" :x2="SVG_W - PAD.r" :y2="yPlus50"
                stroke="#888780" stroke-width="0.5" stroke-dasharray="3 4" stroke-opacity="0.4" />
          <rect :x="PAD.l - 32" :y="yPlus50 - 9" width="30" height="13" fill="#fff" rx="2" />
          <text :x="PAD.l - 4" :y="yPlus50 + 1" font-size="10" fill="#888780"
                text-anchor="end" font-family="Geist, system-ui, sans-serif">+50%</text>

          <!-- −40% guide -->
          <line :x1="PAD.l" :y1="yMinus40" :x2="SVG_W - PAD.r" :y2="yMinus40"
                stroke="#888780" stroke-width="0.5" stroke-dasharray="3 4" stroke-opacity="0.4" />
          <rect :x="PAD.l - 32" :y="yMinus40 - 9" width="30" height="13" fill="#fff" rx="2" />
          <text :x="PAD.l - 4" :y="yMinus40 + 1" font-size="10" fill="#888780"
                text-anchor="end" font-family="Geist, system-ui, sans-serif">-40%</text>

          <!-- Bars -->
          <g
            v-for="b in renderBars"
            :key="b.name"
            class="ed-bp-spine-bar"
            :style="{ '--bsd': `${b.staggerMs}ms` }"
          >
            <rect
              :x="b.x.toFixed(1)" :y="b.y.toFixed(1)"
              :width="b.barW.toFixed(1)" :height="b.barH.toFixed(1)"
              rx="2" :fill="b.color"
            >
              <title>{{ tooltipFor(b) }}</title>
            </rect>

            <!-- % label -->
            <text
              :x="b.cx.toFixed(1)"
              :y="b.labelY.toFixed(1)"
              :font-size="b.fontSize"
              font-weight="500"
              :fill="b.textColor"
              text-anchor="middle"
              font-family="Geist, system-ui, sans-serif"
            >
              <title>{{ b.labelFull }}</title>
              {{ b.label }}
            </text>

            <!-- Company name -->
            <text
              v-if="b.rotated"
              :x="b.cx.toFixed(1)"
              :y="b.rotateY.toFixed(1)"
              font-size="10"
              fill="#1E2A4A"
              text-anchor="end"
              font-family="Geist, system-ui, sans-serif"
              :transform="`rotate(-35 ${b.cx.toFixed(1)} ${b.rotateY.toFixed(1)})`"
            >
              <title>{{ b.name }}</title>
              {{ b.shortName }}
            </text>
            <text
              v-else
              :x="b.cx.toFixed(1)"
              :y="b.nameY.toFixed(1)"
              font-size="10"
              fill="#1E2A4A"
              text-anchor="middle"
              font-family="Geist, system-ui, sans-serif"
            >
              <title>{{ b.name }}</title>
              {{ b.shortName }}
            </text>
          </g>
        </svg>

        <div class="ed-bp-spine-sides">
          <span class="l">↑ опережают</span>
          <span class="r">отстают ↓</span>
        </div>
      </div>

      <!-- ═══ FOOTER DISTRIBUTION (Pack 7.33: clickable segments) ═══ -->
      <div v-if="distrib" class="ed-bp-distrib">
        <div class="ed-bp-distrib-bar">
          <div v-if="distrib.w1 > 0" class="ed-bp-distrib-fill ed-bp-distrib-seg"
               :style="{ '--bpw': distrib.w1 + '%', width: distrib.w1 + '%', background: '#1D9E75' }"
               :title="`Подробнее: ${distrib.onTargetL} (${block.on_target})`"
               role="button"
               tabindex="0"
               @click="openDrill('leaders', $event)"
               @keydown.enter.prevent="openDrill('leaders')"
               @keydown.space.prevent="openDrill('leaders')" />
          <div v-if="distrib.w2 > 0" class="ed-bp-distrib-fill ed-bp-distrib-seg"
               :style="{ '--bpw': distrib.w2 + '%', width: distrib.w2 + '%', background: '#EF9F27', 'animation-delay': '80ms' }"
               :title="`Подробнее: ${distrib.attentionL} (${block.attention})`"
               role="button"
               tabindex="0"
               @click="openDrill('tracking', $event)"
               @keydown.enter.prevent="openDrill('tracking')"
               @keydown.space.prevent="openDrill('tracking')" />
          <div v-if="distrib.w3 > 0" class="ed-bp-distrib-fill ed-bp-distrib-seg"
               :style="{ '--bpw': distrib.w3 + '%', width: distrib.w3 + '%', background: '#E24B4A', 'animation-delay': '160ms' }"
               :title="`Подробнее: ${distrib.behindL} (${block.behind})`"
               role="button"
               tabindex="0"
               @click="openDrill('behind', $event)"
               @keydown.enter.prevent="openDrill('behind')"
               @keydown.space.prevent="openDrill('behind')" />
        </div>
        <div class="ed-bp-distrib-labels">
          <!-- Per user feedback 2026-05-23: цифра окрашена в цвет сегмента
               (а не тёмный оттенок) — иначе визуально казалось что
               легенда не совпадает по цветам с сегментами. -->
          <span><span class="ed-bp-distrib-dot" style="background:#1D9E75" /><strong style="color:#1D9E75">{{ Math.round(tOnTarget) }}</strong> {{ distrib.onTargetL }}</span>
          <span><span class="ed-bp-distrib-dot" style="background:#EF9F27" /><strong style="color:#EF9F27">{{ Math.round(tAttention) }}</strong> {{ distrib.attentionL }}</span>
          <span><span class="ed-bp-distrib-dot" style="background:#E24B4A" /><strong style="color:#E24B4A">{{ Math.round(tBehind) }}</strong> {{ distrib.behindL }}</span>
          <span class="ed-bp-distrib-src">{{ distrib.srcL }}</span>
        </div>
      </div>
    </template>

    <!-- Pack 7.33: drill-down модалка -->
    <BusinessPlanDrillModal
      v-if="drillKind && block && block.mode !== 'empty'"
      :kind="drillKind"
      :block="block"
      :sector-color="sectorColorMap"
      :sector-label="sectorLabelMap"
      @close="closeDrill"
    />
  </section>
</template>

<style scoped>
/* ═══ CARD (Pack 7.33: gradient stripe removed, margin-top added for separation from EE block above) ═══ */
.ed-bp-card {
  background: #fff;
  border-radius: 14px;
  border: 1px solid rgba(0, 0, 0, 0.05);
  padding: 20px 22px;
  margin-top: 14px;
  margin-bottom: 14px;
  position: relative;
  overflow: hidden;
  cursor: pointer;
  animation: bpCardIn 0.65s cubic-bezier(0.34, 1.2, 0.64, 1) both;
  transition: border-color 0.25s ease, box-shadow 0.25s ease, transform 0.18s ease;
}
.ed-bp-card:hover {
  border-color: rgba(127, 119, 221, 0.22);
  box-shadow: 0 1px 0 rgba(0, 0, 0, 0.02), 0 10px 30px -10px rgba(127, 119, 221, 0.22);
  transform: translateY(-1px);
}
.ed-bp-card:focus-visible {
  outline: none;
  box-shadow: 0 0 0 2px rgba(127, 119, 221, 0.45);
}

/* ═══ HEADER ═══ */
.ed-bp-head {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  margin-bottom: 16px;
  margin-top: 4px;
  gap: 12px;
  animation: bpFade 0.5s ease 150ms both;
}
.ed-bp-head-l { min-width: 0; flex: 1; }
.ed-bp-head-t {
  font-size: 11.5px; font-weight: 700;
  color: #888780;
  letter-spacing: 0.07em; text-transform: uppercase;
}
.ed-bp-head-s { font-size: 11px; color: #94A3B8; margin-top: 2px; }

.ed-bp-tabs {
  display: flex; gap: 4px;
  flex-shrink: 0;
  animation: bpFade 0.5s ease 250ms both;
}
.ed-bp-tab {
  padding: 5px 12px;
  border: 0.5px solid rgba(0, 0, 0, 0.1);
  background: #FAFAFC;
  border-radius: 6px;
  font-size: 11px;
  color: #94A3B8;
  font-family: inherit;
  cursor: pointer;
  font-weight: 500;
  transition: all 0.2s cubic-bezier(0.34, 1.2, 0.64, 1);
  position: relative;
  overflow: hidden;
}
.ed-bp-tab:hover {
  color: #1E2A4A;
  background: #fff;
  transform: translateY(-1px);
  box-shadow: 0 2px 6px rgba(0, 0, 0, 0.06);
}
.ed-bp-tab:active { transform: translateY(0) scale(0.97); }
.ed-bp-tab.on {
  background: #fff;
  color: #1E2A4A;
  border-color: rgba(127, 119, 221, 0.35);
  font-weight: 600;
  animation: bpTabGlow 2.4s ease-in-out infinite;
}

/* ═══ EMPTY STATE ═══ */
.ed-bp-empty {
  padding: 40px 20px;
  text-align: center;
  color: #94A3B8;
  font-size: 12.5px;
}
.ed-bp-empty-t {
  margin-bottom: 6px;
  font-weight: 600;
  color: #64748B;
}
.ed-bp-empty-s { color: #94A3B8; }
.ed-bp-empty-mini {
  padding: 24px 12px;
  text-align: center;
  color: #888780;
  font-size: 12px;
}

/* ═══ HERO ═══ */
.ed-bp-spine-hero {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 18px;
  margin: 8px 0 14px;
  padding-bottom: 14px;
  border-bottom: 0.5px solid rgba(0, 0, 0, 0.05);
}
.ed-bp-spine-hero-l { flex: 1; min-width: 0; }
.ed-bp-spine-hero-r {
  display: flex; gap: 18px;
  flex-shrink: 0;
  align-items: flex-start;
}

.ed-bp-big {
  display: flex;
  align-items: baseline;
  gap: 10px;
  margin-bottom: 6px;
  animation: bpNumIn 0.7s cubic-bezier(0.34, 1.56, 0.64, 1) 350ms both;
}
.ed-bp-big-v {
  font-size: 48px;
  font-weight: 600;
  letter-spacing: -0.03em;
  line-height: 1;
  font-feature-settings: "tnum";
  transition: color 0.3s;
}
.ed-bp-big-u {
  font-size: 20px;
  font-weight: 500;
  color: #94A3B8;
}
.ed-bp-delta {
  display: inline-flex;
  align-items: center;
  gap: 3px;
  padding: 3px 8px;
  border-radius: 4px;
  font-size: 11px;
  font-weight: 600;
  animation: bpDeltaPop 0.6s cubic-bezier(0.34, 1.56, 0.64, 1) 700ms both;
}
.ed-bp-delta.up { background: rgba(29, 158, 117, 0.1); color: #0F6E56; }
.ed-bp-delta.down { background: rgba(226, 75, 74, 0.1); color: #933632; }
.ed-bp-big-sub {
  font-size: 11.5px;
  color: #888780;
  margin-bottom: 12px;
  animation: bpFade 0.5s ease 450ms both;
}

.ed-bp-llk {
  display: flex;
  flex-direction: column;
  gap: 2px;
}
.ed-bp-llk .l {
  font-size: 10px;
  color: #888780;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  font-weight: 600;
}
.ed-bp-llk .v {
  font-size: 14px;
  font-weight: 500;
  color: #1E2A4A;
  font-feature-settings: "tnum";
  font-variant-numeric: tabular-nums;
  letter-spacing: -0.01em;
}

/* ═══ PERFORMANCE SPINE ═══ */
.ed-bp-spine-wrap {
  margin: 8px 0 14px;
  position: relative;
}
.ed-bp-spine-svg {
  width: 100%;
  height: auto;
  max-height: 280px;
  display: block;
  animation: bpFade 0.55s cubic-bezier(0.34, 1.2, 0.64, 1) 200ms both;
}
.ed-bp-spine-bar {
  cursor: default;
  animation: bpSpineBar 0.45s cubic-bezier(0.34, 1.2, 0.64, 1) var(--bsd, 0ms) both;
  transform-origin: center bottom;
  transform-box: fill-box;
}
.ed-bp-spine-bar rect { transition: filter 0.2s ease; }
.ed-bp-spine-bar:hover rect { filter: brightness(1.12) saturate(1.1); }

.ed-bp-spine-sides {
  display: flex;
  justify-content: space-between;
  font-size: 10.5px;
  color: #888780;
  font-weight: 500;
  padding: 0 4px;
  margin-top: 4px;
}
.ed-bp-spine-sides .l { color: #0F6E56; }
.ed-bp-spine-sides .r { color: #933632; }

/* ═══ DISTRIBUTION FOOTER ═══ */
.ed-bp-distrib {
  margin-top: 14px;
  padding-top: 14px;
  border-top: 0.5px solid rgba(0, 0, 0, 0.05);
}
.ed-bp-distrib-bar {
  display: flex;
  height: 10px;
  border-radius: 5px;
  overflow: hidden;
  background: rgba(0, 0, 0, 0.04);
  gap: 2px;
  margin-bottom: 10px;
}
.ed-bp-distrib-fill {
  height: 100%;
  border-radius: 2px;
  animation: bpFillIn 0.65s cubic-bezier(0.34, 1.2, 0.64, 1) both;
  transform-origin: left center;
  /* 2026-05-26: smooth width transition on year switch (was hard cut). */
  transition: width 900ms cubic-bezier(.22, 1, .36, 1);
}
/* Pack 7.33: clickable distrib segment — взлёт + чуть ярче на hover */
.ed-bp-distrib-seg {
  cursor: pointer;
  transition: filter 0.16s ease, transform 0.16s ease, box-shadow 0.16s ease;
  outline: none;
}
.ed-bp-distrib-seg:hover {
  filter: brightness(1.08);
  transform: translateY(-1px);
  box-shadow: 0 4px 14px rgba(15, 23, 60, 0.10);
}
.ed-bp-distrib-seg:focus-visible {
  box-shadow: 0 0 0 2px rgba(127, 119, 221, 0.55);
}
.ed-bp-distrib-labels {
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-size: 11px;
  color: #888780;
  font-weight: 500;
  flex-wrap: wrap;
  gap: 8px;
}
.ed-bp-distrib-labels strong { font-weight: 600; }
.ed-bp-distrib-dot {
  display: inline-block;
  width: 6px;
  height: 6px;
  border-radius: 50%;
  margin-right: 6px;
  vertical-align: 1px;
}
.ed-bp-distrib-src {
  color: #B4B2A9;
  font-size: 10.5px;
}

@keyframes bpCardIn {
  0% { opacity: 0; transform: translateY(14px) scale(0.985); }
  60% { opacity: 1; transform: translateY(-3px) scale(1.002); }
  100% { opacity: 1; transform: translateY(0) scale(1); }
}
@keyframes bpFade {
  0% { opacity: 0; transform: translateY(4px); }
  100% { opacity: 1; transform: translateY(0); }
}
@keyframes bpTabGlow {
  0%, 100% { box-shadow: 0 1px 3px rgba(127, 119, 221, 0.08); }
  50% { box-shadow: 0 1px 8px rgba(127, 119, 221, 0.16); }
}
@keyframes bpNumIn {
  0% { opacity: 0; transform: scale(0.85); }
  60% { opacity: 1; transform: scale(1.04); }
  100% { opacity: 1; transform: scale(1); }
}
@keyframes bpDeltaPop {
  0% { opacity: 0; transform: scale(0.6); }
  60% { opacity: 1; transform: scale(1.1); }
  100% { opacity: 1; transform: scale(1); }
}
@keyframes bpSpineBar {
  0% { opacity: 0; transform: scaleY(0.4); }
  100% { opacity: 1; transform: scaleY(1); }
}
@keyframes bpFillIn {
  0% { transform: scaleX(0); }
  100% { transform: scaleX(1); }
}
</style>
