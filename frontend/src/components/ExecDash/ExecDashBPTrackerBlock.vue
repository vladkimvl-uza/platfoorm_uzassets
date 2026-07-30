<script setup lang="ts">
/**
 * ExecDashBPTrackerBlock — Pack 7.27.
 *
 * Полный 1:1 порт логики и дизайна из легасиа (_execBPHtml + _execBPData),
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
import { useSectorMeta, SECTOR_COLORS } from "@/utils/sectorMeta";
import { useFormatters } from "@/composables/useFormatters";
import { useNumberTween } from "@/composables/useNumberTween";
import BusinessPlanDrillModal, { type BpKind } from "@/components/UZA/BusinessPlanDrillModal.vue";
import { useI18n } from "@/composables/useI18n";
import { i18nKey } from "@/locale/keys";


const { t } = useI18n();

const fmt = useFormatters();
const exec = useExecutiveDashboard();
const secMeta = useSectorMeta();

const block = computed(() => exec.data.value?.bp_tracker || null);
const isFallback = computed(() =>
  !!block.value?.requested_year && block.value.requested_year !== block.value.year);

// 2026-05-26: countup tweens для 3 ключевых числовых выводов внизу
const tOnTarget  = useNumberTween(() => Number(block.value?.on_target) || 0, { duration: 900 });
const tAttention = useNumberTween(() => Number(block.value?.attention) || 0, { duration: 900 });
const tBehind    = useNumberTween(() => Number(block.value?.behind) || 0, { duration: 900 });
const rows = computed(() => block.value?.rows || []);

const METRIC_TITLES: Record<string, string> = {
  revenue: i18nKey("Выручка"),
  ebitda: "EBITDA",
  profit: i18nKey("Прибыль"),
};

const METRIC_LABELS: Record<string, string> = {
  revenue: i18nKey("выручки"),
  ebitda: "EBITDA",
  profit: i18nKey("чистой прибыли"),
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

// ─── Период: Год (annual) · Q1..Q4 ───────────────────────────
const activePeriod = ref<string>("annual");

watch(() => block.value?.period, (p) => {
  if (p && p !== activePeriod.value) activePeriod.value = p;
});
watch(() => exec.bpPeriod.value, (p) => {
  if (p && p !== activePeriod.value) activePeriod.value = p;
});

function setPeriod(p: string): void {
  if (activePeriod.value === p) return;
  activePeriod.value = p;
  exec.setBpPeriod(p);
}

const PERIOD_TABS: { key: string; label: string }[] = [
  { key: "annual", label: i18nKey("Год") },
  { key: "q1", label: "Q1" },
  { key: "q2", label: "Q2" },
  { key: "q3", label: "Q3" },
  { key: "q4", label: "Q4" },
];

// Pack 7.33: BP drill-down modal
const sectorColorMap = SECTOR_COLORS as Record<string, string>;
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
  // Удобство для мыши: клик по «пустому» месту карточки открывает overall.
  // Клики по табам / distribution-сегментам / hero-кнопке игнорим — у них свои
  // handlers (+ stopPropagation), клавиатурный путь — через .ed-bp-hero-btn.
  const t = e.target as HTMLElement | null;
  if (!t) return;
  if (t.closest(".ed-bp-tab") || t.closest(".ed-bp-distrib-seg") || t.closest(".ed-bp-hero-btn")) return;
  openDrill("overall");
}

// ─── Number formatters ─────────────────────────────────────────
// Note: input value is already scaled to "млрд" (billions). 1000 input = 1 трлн.
// ВАЖНО: возвращает значение УЖЕ С ЕДИНИЦЕЙ (млрд/трлн) — вызывающий код НЕ
// должен дописывать « млрд» (иначе для больших сумм выходит «475 трлн млрд»).
function fmtNum(v: number | null | undefined): string {
  if (v == null || isNaN(v)) return "—";
  if (Math.abs(v) >= 1000) return fmt.fmtNumber(v / 1000, { decimals: 1 }) + " " + t("трлн");
  if (Math.abs(v) >= 100) return fmt.fmtNumber(Math.round(v)) + " " + t("млрд");
  return fmt.fmtNumber(v, { decimals: 1, minDecimals: 1 }) + " " + t("млрд");
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
      bigColor = pctVal >= 95 ? "#5DC093" : pctVal >= 80 ? "#EFB373" : "#E2807F";
    } else {
      bigColor = pctVal >= 100 ? "#5DC093" : pctVal >= 95 ? "#EFB373" : "#E2807F";
    }
    bigVal = String(pctVal);
    bigUnit = "%";
  } else if (b.is_signed_metric && b.overall_label) {
    const v = b.overall_delta ?? 0;
    bigVal = v >= 0 ? "+" + fmtNum(v) : fmtNum(v);
    bigUnit = "";  // fmtNum уже включает единицу (млрд/трлн)
    const positiveSignedLabels: readonly string[] = [i18nKey("выход из убытка"), i18nKey("убыток сокращён"), i18nKey("значительный рост"), i18nKey("план перевыполнен")];
    bigColor = positiveSignedLabels.includes(b.overall_label) ? "#5DC093" : "#E2807F";
  }

  if (b.overall_label) {
    bigSub = `${t(b.overall_label)} · ${t(mLabel)}`;
  } else if (b.mode === "plan-fact") {
    bigSub = t("выполнение плана {metric} по портфелю", { metric: t(mLabel) });
  } else if (b.mode === "yoy") {
    bigSub = t("динамика {metric} к {year} году", { metric: t(mLabel), year: b.prev_year });
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
      l1: t("План (сравнимые)"),
      v1: fmtNum(b.sum_plan_ll),
      l2: t("Факт (сравнимые)"),
      v2: fmtNum(b.sum_fact_plan_ll),
    };
  } else {
    llkLabels = {
      l1: t("{year} (сравнимые)", { year: b.prev_year }),
      v1: fmtNum(b.sum_prev_ll),
      l2: t("{year} (сравнимые)", { year: b.year }),
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

// SVG dimensions (1:1 from legacy)
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
  // Единый стиль с «Рейтинг компаний по исполнению» (мягкая пастель).
  return cls === "ok" ? "#5DC093" : cls === "warn" ? "#EFB373" : cls === "bad" ? "#E2807F" : "#B8B7B0";
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
    onTargetL = t("В росте/восстановление");
    attentionL = t("Лёгкое снижение");
    behindL = t("Снижение/убыток");
  } else if (b.mode === "plan-fact") {
    onTargetL = t("На цели (≥95%)");
    attentionL = t("Внимание (80–94%)");
    behindL = t("Отстают (<80%)");
  } else {
    onTargetL = t("В росте (≥100%)");
    attentionL = t("Лёгкое снижение (95–99%)");
    behindL = t("Снижение (<95%)");
  }

  const srcL = b.mode === "plan-fact"
    ? t("Источник: БП + НСБУ")
    : t("Источник: НСБУ · режим YoY (план не заполнен)");

  return { w1, w2, w3, onTargetL, attentionL, behindL, srcL };
});

// Tooltip text per bar
function tooltipFor(b: RenderBar): string {
  const parts = [b.name, t(b.labelFull)];
  if (b.delta != null) {
    parts.push((b.delta >= 0 ? "+" : "") + fmtNum(b.delta));
  }
  return parts.join(" · ");
}
</script>

<template>
  <!-- a11y: карточка больше НЕ role=button — внутри живут кнопки-табы и
       distribution-сегменты (это был nested-interactive). Клик по пустому месту
       открывает overall (удобство для мыши); клавиатурный вход в overall — через
       фокусируемый hero-блок ниже, у сегментов — свои role=button. -->
  <section
    class="ed-bp-card"
    @click="onCardClick"
    :title="t('Подробнее: бизнес-план портфеля')"
  >
    <!-- ═══ HEADER ═══ -->
    <div class="ed-bp-head">
      <div class="ed-bp-head-l">
        <div class="ed-bp-head-t">{{ t("Бизнес-план портфеля · годовое исполнение") }}
          <span v-if="isFallback" class="ed-bp-fallback">{{ t("данные за FY {year}", { year: block?.year }) }}</span>
        </div>
        <div class="ed-bp-head-s">{{ block?.head_sub || t("Загрузка…") }}</div>
      </div>
      <div class="ed-bp-head-controls">
        <div class="ed-bp-tabs ed-bp-tabs--period">
          <button
            v-for="p in PERIOD_TABS"
            :key="p.key"
            class="ed-bp-tab"
            :class="{ on: activePeriod === p.key }"
            @click="setPeriod(p.key)"
          >
            {{ t(p.label) }}
          </button>
        </div>
        <div class="ed-bp-tabs">
          <button
            v-for="m in tabs"
            :key="m"
            class="ed-bp-tab"
            :class="{ on: activeMetric === m }"
            @click="setMetric(m)"
          >
            {{ t(METRIC_TITLES[m]) }}
          </button>
        </div>
      </div>
    </div>

    <!-- ═══ EMPTY STATE ═══ -->
    <div v-if="!block || block.mode === 'empty'" class="ed-bp-empty">
      <div class="ed-bp-empty-t">{{ t("Нет данных для сравнения") }}</div>
      <div class="ed-bp-empty-s">
        {{ t("Для года {year} не заполнен план в бизнес-плане, а факта прошлого года ({prev}) недостаточно для расчёта YoY.", {
          year: block?.year || exec.year.value,
          prev: block?.prev_year || (exec.year.value - 1),
        }) }}
      </div>
    </div>

    <template v-else-if="hero">
      <!-- ═══ HERO ═══ -->
      <div class="ed-bp-spine-hero">
        <div
          class="ed-bp-spine-hero-l ed-bp-hero-btn"
          role="button"
          tabindex="0"
          :aria-label="t('Подробнее: бизнес-план портфеля')"
          @click.stop="openDrill('overall', $event)"
          @keydown.enter.prevent="openDrill('overall')"
          @keydown.space.prevent="openDrill('overall')"
        >
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
              {{ fmt.fmtNumber(hero.deltaPP, { decimals: 1, minDecimals: 1, signed: true }) }} {{ t("п.п.") }}
            </span>
          </div>
          <div class="ed-bp-big-sub">{{ hero.bigSub }}</div>
        </div>
        <div class="ed-bp-spine-hero-r">
          <div class="ed-bp-llk">
            <span class="l">{{ hero.llkLabels.l1 }}</span>
            <span class="v">{{ hero.llkLabels.v1 }}</span>
          </div>
          <div class="ed-bp-llk">
            <span class="l">{{ hero.llkLabels.l2 }}</span>
            <span class="v" :style="{ color: hero.bigColor }">{{ hero.llkLabels.v2 }}</span>
          </div>
        </div>
      </div>

      <!-- ═══ PERFORMANCE SPINE ═══ -->
      <div v-if="renderBars.length === 0" class="ed-bp-empty-mini">
        {{ t("Недостаточно данных для построения performance-шкалы") }}
      </div>
      <div v-else class="ed-bp-spine-wrap">
        <svg
          class="ed-bp-spine-svg"
          :viewBox="`0 0 ${SVG_W} ${SVG_H}`"
          preserveAspectRatio="xMidYMid meet"
          role="img"
          :aria-label="t('Performance spine — выполнение плана по компаниям')"
        >
          <!-- Белый «глянец» сверху бара — как в «Рейтинг компаний по исполнению» -->
          <defs>
            <linearGradient id="bpSpineSheen" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0" stop-color="#fff" stop-opacity="0.34" />
              <stop offset="0.55" stop-color="#fff" stop-opacity="0" />
            </linearGradient>
          </defs>
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
              rx="2.5" :fill="b.color"
            >
              <title>{{ tooltipFor(b) }}</title>
            </rect>
            <rect
              :x="b.x.toFixed(1)" :y="b.y.toFixed(1)"
              :width="b.barW.toFixed(1)" :height="b.barH.toFixed(1)"
              rx="2.5" fill="url(#bpSpineSheen)" pointer-events="none"
            />

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
              <title>{{ t(b.labelFull) }}</title>
              {{ t(b.label) }}
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
          <span class="l">↑ {{ t("опережают") }}</span>
          <span class="r">{{ t("отстают") }} ↓</span>
        </div>
      </div>

      <!-- ═══ FOOTER DISTRIBUTION (Pack 7.33: clickable segments) ═══ -->
      <div v-if="distrib" class="ed-bp-distrib">
        <div class="ed-bp-distrib-bar">
          <div v-if="distrib.w1 > 0" class="ed-bp-distrib-fill ed-bp-distrib-seg"
               :style="{ '--bpw': distrib.w1 + '%', width: distrib.w1 + '%', background: '#5DC093' }"
               :title="t('Подробнее: {label} ({n})', { label: distrib.onTargetL, n: block.on_target })"
               role="button"
               tabindex="0"
               @click="openDrill('leaders', $event)"
               @keydown.enter.prevent="openDrill('leaders')"
               @keydown.space.prevent="openDrill('leaders')" />
          <div v-if="distrib.w2 > 0" class="ed-bp-distrib-fill ed-bp-distrib-seg"
               :style="{ '--bpw': distrib.w2 + '%', width: distrib.w2 + '%', background: '#EFB373', 'animation-delay': '80ms' }"
               :title="t('Подробнее: {label} ({n})', { label: distrib.attentionL, n: block.attention })"
               role="button"
               tabindex="0"
               @click="openDrill('tracking', $event)"
               @keydown.enter.prevent="openDrill('tracking')"
               @keydown.space.prevent="openDrill('tracking')" />
          <div v-if="distrib.w3 > 0" class="ed-bp-distrib-fill ed-bp-distrib-seg"
               :style="{ '--bpw': distrib.w3 + '%', width: distrib.w3 + '%', background: '#E2807F', 'animation-delay': '160ms' }"
               :title="t('Подробнее: {label} ({n})', { label: distrib.behindL, n: block.behind })"
               role="button"
               tabindex="0"
               @click="openDrill('behind', $event)"
               @keydown.enter.prevent="openDrill('behind')"
               @keydown.space.prevent="openDrill('behind')" />
        </div>
        <div class="ed-bp-distrib-labels">
          <!-- UI-аудит 2026-06: число перекрашено в тёмный он-тон оттенок
               (контраст AA на белом), цветовую ассоциацию держит
               маленькая яркая точка ed-bp-distrib-dot рядом. -->
          <span><span class="ed-bp-distrib-dot" style="background:#5DC093" /><strong style="color:#0F6E56">{{ Math.round(tOnTarget) }}</strong> {{ distrib.onTargetL }}</span>
          <span><span class="ed-bp-distrib-dot" style="background:#EFB373" /><strong style="color:#8A5F15">{{ Math.round(tAttention) }}</strong> {{ distrib.attentionL }}</span>
          <span><span class="ed-bp-distrib-dot" style="background:#E2807F" /><strong style="color:#933632">{{ Math.round(tBehind) }}</strong> {{ distrib.behindL }}</span>
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
  background: var(--bg1, #fff);
  border-radius: 12px;
  border: 1px solid rgba(0, 0, 0, 0.05);
  padding: 20px 22px;
  margin-top: 14px;
  margin-bottom: 14px;
  position: relative;
  overflow: hidden;
  cursor: pointer;
  animation: bpCardIn 0.65s var(--ease-standard) both;
  transition: border-color 0.25s ease, box-shadow 0.25s ease, transform 0.18s ease;
}
.ed-bp-card:hover {
  border-color: rgba(127, 119, 221, 0.22);
  box-shadow: 0 1px 0 rgba(0, 0, 0, 0.02), 0 10px 30px -10px rgba(127, 119, 221, 0.22);
  transform: translateY(-1px);
}
/* a11y: фокус теперь живёт на hero-кнопке (overall drill), не на всей карточке */
.ed-bp-hero-btn { cursor: pointer; border-radius: 10px; outline: none; }
.ed-bp-hero-btn:focus-visible {
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
  font-size: 11px; font-weight: 600;
  color: var(--t3, var(--t-muted));
  letter-spacing: 0.07em; text-transform: uppercase;
}
.ed-bp-head-s { font-size: 11px; color: var(--t3, #94A3B8); margin-top: 2px; }
.ed-bp-fallback {
  display: inline-block;
  margin-left: 8px;
  font-size: 9.5px;
  font-weight: 600;
  letter-spacing: 0.03em;
  text-transform: none;
  color: #92610B;
  background: rgba(239, 159, 39, 0.14);
  border: 1px solid rgba(239, 159, 39, 0.3);
  padding: 2px 8px;
  border-radius: 999px;
  vertical-align: middle;
}

.ed-bp-head-controls {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-shrink: 0;
  flex-wrap: wrap;
  justify-content: flex-end;
}
.ed-bp-tabs {
  display: flex; gap: 4px;
  flex-shrink: 0;
  animation: bpFade 0.5s ease 250ms both;
}
/* Период-чипы (Год · Q1..Q4) — те же ed-bp-tab, отделены тонким сепаратором */
.ed-bp-tabs--period {
  animation-delay: 200ms;
  padding-right: 12px;
  border-right: 0.5px solid rgba(0, 0, 0, 0.1);
}
.ed-bp-tab {
  padding: 5px 12px;
  border: 0.5px solid rgba(0, 0, 0, 0.1);
  background: var(--bg2, #FAFAFC);
  border-radius: 6px;
  font-size: 11px;
  color: var(--t3, #94A3B8);
  font-family: inherit;
  cursor: pointer;
  font-weight: 500;
  transition: all 0.2s var(--ease-standard);
  position: relative;
  overflow: hidden;
}
.ed-bp-tab:hover {
  color: var(--t1, #1E2A4A);
  background: var(--bg1, #fff);
  transform: translateY(-1px);
  box-shadow: 0 2px 6px rgba(0, 0, 0, 0.06);
}
.ed-bp-tab:active { transform: translateY(0) scale(0.97); }
.ed-bp-tab.on {
  background: var(--bg1, #fff);
  color: var(--t1, #1E2A4A);
  border-color: rgba(127, 119, 221, 0.35);
  font-weight: 600;
  animation: bpTabGlow 2.4s ease-in-out 1;
}

/* ═══ EMPTY STATE ═══ */
.ed-bp-empty {
  padding: 40px 20px;
  text-align: center;
  color: var(--t3, #94A3B8);
  font-size: 12.5px;
}
.ed-bp-empty-t {
  margin-bottom: 6px;
  font-weight: 600;
  color: var(--t3, var(--t3));
}
.ed-bp-empty-s { color: var(--t3, #94A3B8); }
.ed-bp-empty-mini {
  padding: 24px 12px;
  text-align: center;
  color: var(--t3, var(--t-muted));
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
  font-weight: 400;
  letter-spacing: -0.03em;
  line-height: 1;
  font-feature-settings: "tnum";
  transition: color 0.3s;
}
.ed-bp-big-u {
  font-size: 20px;
  font-weight: 500;
  color: var(--t3, #94A3B8);
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
  color: var(--t3, var(--t-muted));
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
  color: var(--t3, var(--t-muted));
  text-transform: uppercase;
  letter-spacing: 0.05em;
  font-weight: 600;
}
.ed-bp-llk .v {
  font-size: 14px;
  font-weight: 500;
  color: var(--t1, #1E2A4A);
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
  animation: bpFade 0.55s var(--ease-standard) 200ms both;
}
.ed-bp-spine-bar {
  cursor: default;
  animation: bpSpineBar 0.45s var(--ease-standard) var(--bsd, 0ms) both;
  transform-origin: center bottom;
  transform-box: fill-box;
}
.ed-bp-spine-bar rect { transition: filter 0.2s ease; }
.ed-bp-spine-bar:hover rect { filter: brightness(1.12) saturate(1.1); }

.ed-bp-spine-sides {
  display: flex;
  justify-content: space-between;
  font-size: 10.5px;
  color: var(--t3, var(--t-muted));
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
  animation: bpFillIn 0.65s var(--ease-standard) both;
  transform-origin: left center;
  /* 2026-05-26: smooth width transition on year switch (was hard cut). */
  transition: width 900ms var(--ease-out);
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
  justify-content: flex-start;
  align-items: center;
  font-size: 11px;
  color: var(--t3, var(--t-muted));
  font-weight: 500;
  flex-wrap: wrap;
  gap: 6px 18px;
}
/* каждый пункт легенды — точка+число+подпись вместе, не растягиваем по ширине */
.ed-bp-distrib-labels > span {
  display: inline-flex;
  align-items: center;
  white-space: nowrap;
}
.ed-bp-distrib-labels strong { font-weight: 600; margin-right: 4px; }
.ed-bp-distrib-dot {
  display: inline-block;
  width: 8px;
  height: 8px;
  border-radius: 50%;
  margin-right: 7px;
  flex-shrink: 0;
  box-shadow: 0 0 0 2px color-mix(in srgb, currentColor 0%, transparent);
}
.ed-bp-distrib-src {
  color: #6B6A66;
  font-size: 10.5px;
  margin-left: auto;  /* источник — к правому краю, отдельно от легенды */
}

/* ═══ KEYFRAMES (1:1 from legacy) ═══ */
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
