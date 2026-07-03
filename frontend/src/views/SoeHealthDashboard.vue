<script setup lang="ts">
/**
 * SoeHealthDashboard — полноценный дашборд «SOE Health Check» (сайдбар Финансы).
 *
 * Структура зеркалит дашборды исходного инструмента (Portfolio Level /
 * Single Company Level): KPI-полоса → светофорная матрица → портфельный
 * уровень (Pareto по компаниям + тренды агрегатов) → дриллы по компании.
 *
 * Премиум: kpi-rail, staggered-появление, Odometer, SVG-бар-чарт с
 * анимацией роста и кумулятивной линией, спарклайны с draw-анимацией,
 * редактор порогов (dirty-guard) и дрилл-модалка компании.
 */
import { computed, inject, onMounted, ref, watch } from "vue";
import { api } from "@/api/client";
import { useSavedFilter } from "@/composables/useSavedFilter";
import { usePermissions } from "@/composables/usePermissions";
import { ensureFinancialsCss } from "@/components/Financials/financialsHelpers";
import UzaSegment from "@/components/UZA/UzaSegment.vue";
import UzaYearStepper from "@/components/UZA/UzaYearStepper.vue";
import Odometer from "@/components/Odometer.vue";
import SoeHealthBoard, { type SoeHealthPayload } from "@/components/Financials/SoeHealthBoard.vue";
import SoeHealthParamsModal from "@/components/Financials/SoeHealthParamsModal.vue";

const finPerm = usePermissions("financials");

// Бургер как в FinTopFilters (инжект из AppShell): ≤1023 — drawer, иначе рейка.
const toggleSidebar = inject<() => void>("toggleSidebar", () => {});
const openMobileSidebar = inject<() => void>("openMobileSidebar", () => {});
function onBurger() {
  if (typeof window !== "undefined" && window.innerWidth <= 1023) openMobileSidebar();
  else toggleSidebar();
}

const CURRENT_FY = 2025;
const YEARS = Array.from({ length: 8 }, (_, i) => 2019 + i); // 2019..2026
const year = useSavedFilter<number>("soeHealth.year", CURRENT_FY);
const standard = useSavedFilter<"NSBU" | "IFRS">("soeHealth.standard", "NSBU");

const data = ref<SoeHealthPayload | null>(null);
const loading = ref(true);
const error = ref<string | null>(null);
let seq = 0;

async function load() {
  const my = ++seq;
  loading.value = true;
  error.value = null;
  try {
    const r = await api.get<SoeHealthPayload>("/financials/soe-health", {
      params: { year: year.value, standard: standard.value },
    });
    if (my !== seq) return;
    data.value = r.data;
  } catch (e: unknown) {
    if (my !== seq) return;
    const err = e as { response?: { data?: { detail?: string } }; message?: string };
    error.value = err?.response?.data?.detail || err?.message || "Не удалось загрузить";
  } finally {
    if (my === seq) loading.value = false;
  }
}
onMounted(() => { ensureFinancialsCss(); load(); });
watch([year, standard], load);

const paramsOpen = ref(false);

// ─── Портфельный уровень: Pareto по компаниям ──────────────────────
const PARETO_METRICS = [
  { value: "totalLiabilities", label: "Обязательства" },
  { value: "ebitda", label: "EBITDA" },
  { value: "debt", label: "Долг" },
] as const;
const paretoMetric = ref<string>("totalLiabilities");

interface ParetoBar { code: string; name: string; v: number; color: string; cum: number }
const paretoBars = computed<ParetoBar[]>(() => {
  const cos = (data.value?.companies || [])
    .map((c) => ({
      code: c.code, name: c.name,
      v: Number((c as { metrics_out?: Record<string, number | null> }).metrics_out?.[paretoMetric.value] ?? 0),
      color: c.sector_color || "#7F77DD",
    }))
    .filter((b) => b.v > 0)
    .sort((a, b) => b.v - a.v);
  const total = cos.reduce((s, b) => s + b.v, 0) || 1;
  let acc = 0;
  return cos.map((b) => { acc += b.v; return { ...b, cum: acc / total * 100 }; });
});
const paretoMax = computed(() => Math.max(1, ...paretoBars.value.map((b) => b.v)));

// SVG-геометрия Pareto
const PW = 960, PH = 300, PADL = 8, PADR = 40, PADT = 16, PADB = 44;
function barX(i: number): number {
  const n = paretoBars.value.length || 1;
  const w = (PW - PADL - PADR) / n;
  return PADL + i * w + w * 0.14;
}
function barW(): number {
  const n = paretoBars.value.length || 1;
  return ((PW - PADL - PADR) / n) * 0.72;
}
function barH(v: number): number { return (v / paretoMax.value) * (PH - PADT - PADB); }
function barY(v: number): number { return PH - PADB - barH(v); }
function cumPoints(): string {
  return paretoBars.value
    .map((b, i) => `${(barX(i) + barW() / 2).toFixed(1)},${(PADT + (1 - b.cum / 100) * (PH - PADT - PADB)).toFixed(1)}`)
    .join(" ");
}
function fmtBln(v: number): string {
  if (Math.abs(v) >= 1000) return (v / 1000).toLocaleString("ru", { maximumFractionDigits: 1 }) + " трлн";
  return v.toLocaleString("ru", { maximumFractionDigits: 0 }) + " млрд";
}

// ─── Тренды агрегатов (спарклайны) ─────────────────────────────────
const TRENDS = [
  { key: "roa", label: "ROA портфеля", fmt: "pct", accent: "#1D9E75" },
  { key: "roe", label: "ROE портфеля", fmt: "pct", accent: "#378ADD" },
  { key: "debtToEquity", label: "Долг / Капитал", fmt: "x", accent: "#EF9F27" },
  { key: "currentRatio", label: "Current Ratio", fmt: "x", accent: "#7F77DD" },
] as const;

interface TrendCard {
  key: string; label: string; accent: string;
  last: string; delta: string | null; deltaGood: boolean | null;
  points: string; area: string; lastXY: [number, number] | null;
}
const SW = 220, SH = 56;
const trendCards = computed<TrendCard[]>(() => {
  const s = data.value?.series;
  return TRENDS.map((t) => {
    const raw = (s?.ratios?.[t.key] || []) as (number | null)[];
    const vals = raw.map((v, i) => ({ v, i })).filter((p) => p.v != null) as { v: number; i: number }[];
    const fmtV = (v: number) => t.fmt === "pct" ? (v * 100).toFixed(1) + "%" : v.toFixed(2);
    let points = "", area = "", lastXY: [number, number] | null = null;
    if (vals.length >= 2) {
      const min = Math.min(...vals.map((p) => p.v));
      const max = Math.max(...vals.map((p) => p.v));
      const span = max - min || 1;
      const n = raw.length - 1 || 1;
      const xy = vals.map((p) => [
        6 + (p.i / n) * (SW - 12),
        6 + (1 - (p.v - min) / span) * (SH - 12),
      ] as [number, number]);
      points = xy.map(([x, y]) => `${x.toFixed(1)},${y.toFixed(1)}`).join(" ");
      area = `${xy[0][0].toFixed(1)},${SH - 2} ` + points + ` ${xy[xy.length - 1][0].toFixed(1)},${SH - 2}`;
      lastXY = xy[xy.length - 1];
    }
    const last = vals.length ? fmtV(vals[vals.length - 1].v) : "—";
    let delta: string | null = null, deltaGood: boolean | null = null;
    if (vals.length >= 2) {
      const d = vals[vals.length - 1].v - vals[vals.length - 2].v;
      const goodUp = t.key !== "debtToEquity";  // рост долга/капитала — плохо
      deltaGood = goodUp ? d >= 0 : d <= 0;
      delta = (d >= 0 ? "+" : "") + (t.fmt === "pct" ? (d * 100).toFixed(1) + " п.п." : d.toFixed(2));
    }
    return { key: t.key, label: t.label, accent: t.accent, last, delta, deltaGood, points, area, lastXY };
  });
});
const seriesYears = computed(() => data.value?.series?.years || []);
</script>

<template>
  <div class="sh-page">
    <!-- ═══ Топбар — тёмная плашка в стиле financials (FinTopFilters) ═══ -->
    <header class="sh-bar">
      <button class="sh-burger" @click="onBurger()" title="Меню / свернуть сайдбар">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round">
          <line x1="3" y1="6" x2="21" y2="6"/><line x1="3" y1="12" x2="21" y2="12"/><line x1="3" y1="18" x2="21" y2="18"/>
        </svg>
      </button>

      <div class="sh-head">
        <div class="sh-eyebrow">ФИНАНСЫ · ЗДОРОВЬЕ ПОРТФЕЛЯ</div>
        <div class="sh-title-row">
          <span class="sh-title">SOE Health Check</span>
          <span class="sh-sub">
            RAG-оценка устойчивости · <strong>{{ standard }}</strong> · FY {{ year }}
            <span v-if="data?.params_overridden" class="sh-ovr-badge" title="Пороги изменены относительно методики">пороги настроены</span>
          </span>
        </div>
      </div>

      <div class="sh-cluster">
        <div class="sh-tabs uza-seg on-dark" title="Стандарт отчётности">
          <button class="uza-seg-btn" :class="{ on: standard === 'NSBU' }" @click="standard = 'NSBU'">НСБУ</button>
          <button class="uza-seg-btn" :class="{ on: standard === 'IFRS' }" @click="standard = 'IFRS'">МСФО</button>
        </div>
        <div class="sh-div" aria-hidden="true"></div>
        <UzaYearStepper tone="dark" :model-value="year" :years="YEARS" prefix="FY "
                        @update:model-value="year = ($event as number) ?? year" />
        <div class="sh-div" aria-hidden="true"></div>
        <button v-if="finPerm.canEdit.value" class="sh-params-btn" type="button" @click="paramsOpen = true"
                title="Редактор порогов риска">
          <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="4" y1="21" x2="4" y2="14"/><line x1="4" y1="10" x2="4" y2="3"/><line x1="12" y1="21" x2="12" y2="12"/><line x1="12" y1="8" x2="12" y2="3"/><line x1="20" y1="21" x2="20" y2="16"/><line x1="20" y1="12" x2="20" y2="3"/><line x1="1" y1="14" x2="7" y2="14"/><line x1="9" y1="8" x2="15" y2="8"/><line x1="17" y1="16" x2="23" y2="16"/></svg>
          Пороги
        </button>
      </div>
    </header>

    <!-- Состояния -->
    <div v-if="loading && !data" class="sh-state">
      <div class="sh-skel" v-for="i in 3" :key="i" :style="{ '--d': (i * 90) + 'ms' }" />
    </div>
    <div v-else-if="error && !data" class="sh-state sh-err">
      {{ error }}
      <button class="sh-retry" type="button" @click="load">Повторить</button>
    </div>

    <template v-else-if="data">
      <!-- ═══ KPI + матрица ═══ -->
      <section class="sh-section">
        <SoeHealthBoard :data="data" />
      </section>

      <!-- ═══ Портфельный уровень: Pareto ═══ -->
      <section class="sh-section sh-grid">
        <div class="sh-card sh-pareto" style="--d:80ms">
          <div class="sh-card-hd">
            <div>
              <div class="sh-card-t">Концентрация портфеля</div>
              <div class="sh-card-s">компании по убыванию · линия — накопленная доля</div>
            </div>
            <UzaSegment
              :model-value="paretoMetric"
              :options="PARETO_METRICS as never"
              size="sm"
              @update:model-value="paretoMetric = $event as string"
            />
          </div>
          <div v-if="paretoBars.length" class="sh-pareto-svgwrap">
            <svg :viewBox="`0 0 ${PW} ${PH}`" class="sh-pareto-svg" preserveAspectRatio="xMidYMid meet">
              <!-- сетка -->
              <line v-for="f in [0.25, 0.5, 0.75]" :key="f"
                    :x1="PADL" :x2="PW - PADR"
                    :y1="PADT + (1 - f) * (PH - PADT - PADB)" :y2="PADT + (1 - f) * (PH - PADT - PADB)"
                    class="sh-grid-line" />
              <!-- бары -->
              <!-- единый бренд-пурпур (канон: без секторной радуги) -->
              <defs>
                <linearGradient id="shBarGrad" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stop-color="#8B7FFF" />
                  <stop offset="100%" stop-color="#6C5CE7" />
                </linearGradient>
              </defs>
              <g v-for="(b, i) in paretoBars" :key="b.code">
                <rect :x="barX(i)" :y="barY(b.v)" :width="barW()" :height="barH(b.v)"
                      fill="url(#shBarGrad)" rx="4" class="sh-bar" :style="{ '--d': (i * 40) + 'ms' }">
                  <title>{{ b.name }} · {{ fmtBln(b.v) }} · накоплено {{ b.cum.toFixed(0) }}%</title>
                </rect>
                <text :x="barX(i) + barW() / 2" :y="PH - PADB + 14" class="sh-bar-lbl"
                      text-anchor="middle">{{ b.code.toUpperCase() }}</text>
              </g>
              <!-- кумулятивная линия -->
              <polyline :points="cumPoints()" class="sh-cum-line" fill="none" />
              <circle v-for="(b, i) in paretoBars" :key="'c' + b.code"
                      :cx="barX(i) + barW() / 2"
                      :cy="PADT + (1 - b.cum / 100) * (PH - PADT - PADB)"
                      r="3" class="sh-cum-dot" :style="{ '--d': (i * 40 + 300) + 'ms' }">
                <title>{{ b.name }} · накоплено {{ b.cum.toFixed(0) }}%</title>
              </circle>
              <!-- правая ось % -->
              <text v-for="f in [0, 50, 100]" :key="'p' + f"
                    :x="PW - PADR + 6" :y="PADT + (1 - f / 100) * (PH - PADT - PADB) + 3"
                    class="sh-axis-lbl">{{ f }}%</text>
            </svg>
          </div>
          <div v-else class="sh-none">Нет данных за {{ data.year }} ({{ data.standard }})</div>
        </div>
      </section>

      <!-- ═══ Тренды агрегатов ═══ -->
      <section class="sh-section">
        <div class="sh-trends">
          <div v-for="(t, i) in trendCards" :key="t.key" class="sh-card sh-trend"
               :style="{ '--accent': t.accent, '--d': (i * 70) + 'ms' }">
            <div class="sh-trend-l">{{ t.label }}</div>
            <div class="sh-trend-v">
              <Odometer :value="t.last" />
              <span v-if="t.delta" class="sh-trend-d"
                    :style="{ color: t.deltaGood ? '#1D9E75' : '#E24B4A' }">{{ t.delta }}</span>
            </div>
            <svg v-if="t.points" :viewBox="`0 0 ${SW} ${SH}`" class="sh-spark">
              <polygon :points="t.area" :fill="t.accent" opacity="0.10" />
              <polyline :points="t.points" fill="none" :stroke="t.accent" stroke-width="2"
                        stroke-linecap="round" stroke-linejoin="round" class="sh-spark-line" />
              <circle v-if="t.lastXY" :cx="t.lastXY[0]" :cy="t.lastXY[1]" r="3.4"
                      :fill="t.accent" class="sh-spark-dot" />
            </svg>
            <div v-else class="sh-none sm">мало данных</div>
            <div class="sh-trend-yrs">{{ seriesYears[0] }}–{{ seriesYears[seriesYears.length - 1] }}</div>
          </div>
        </div>
      </section>
    </template>

    <SoeHealthParamsModal
      :open="paramsOpen"
      :ratios="data?.ratios_meta || []"
      @close="paramsOpen = false"
      @saved="paramsOpen = false; load()"
    />
  </div>
</template>

<style scoped>
/* Компоновка как в financials (.fd-page): бар примыкает full-bleed,
   секции — с собственными боковыми отступами */
.sh-page { padding: 0 0 32px; max-width: none; margin: 0; display: flex; flex-direction: column; gap: 12px; }
.sh-section, .sh-state { margin: 0 14px; }

/* ── Топбар — 1:1 стиль financials (.ft-bar: градиент #1E2A4A → #182039) ── */
.sh-bar {
  display: flex; align-items: center; gap: 14px; row-gap: 10px; flex-wrap: wrap;
  padding: 10px 16px; min-height: 52px;
  background: linear-gradient(180deg, #1E2A4A 0%, #182039 100%);
  color: #fff;
  /* цельно с сайдбаром: слева без радиуса (нет светлой выемки), без анимаций */
  border-radius: 0 12px 12px 0;
  box-shadow: 0 4px 14px rgba(15, 23, 60, 0.15);
  animation: none !important;
  transition: none;
}
.sh-burger {
  width: 34px; height: 34px; border-radius: 8px; flex-shrink: 0;
  border: 1px solid rgba(255,255,255,.12); background: rgba(255,255,255,.08);
  color: rgba(255,255,255,.85); cursor: pointer;
  display: inline-flex; align-items: center; justify-content: center;
  transition: background .15s ease, border-color .15s ease, transform .16s ease;
}
.sh-burger:hover { background: rgba(255,255,255,.14); border-color: rgba(255,255,255,.22); color: #fff; }
.sh-burger:active { transform: scale(.94); }
/* 1:1 значения из FinTopFilters (.ft-head/.ft-div/.ft-cluster) */
.sh-head { flex: 1 1 280px; min-width: 0; display: flex; flex-direction: column; gap: 1px; overflow: hidden; }
.sh-eyebrow { font-size: 10px; font-weight: 500; letter-spacing: .08em; text-transform: uppercase; color: rgba(255,255,255,.55); }
.sh-title-row { display: flex; align-items: baseline; gap: 10px; min-width: 0; flex-wrap: wrap; row-gap: 2px; }
.sh-title { font-size: 19px; font-weight: 500; letter-spacing: -.01em; color: #fff; line-height: 1.15; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; flex: 0 1 auto; min-width: 0; }
.sh-sub { font-size: 12px; color: rgba(255,255,255,.65); line-height: 1.45; flex: 1 1 100%; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.sh-sub strong { color: #fff; font-weight: 500; }
.sh-ovr-badge { margin-left: 7px; font-size: 9px; font-weight: 700; color: #FFD9A0; background: rgba(239,159,39,.22); border-radius: 5px; padding: 1px 6px; letter-spacing: .03em; }
.sh-cluster { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; row-gap: 6px; flex: 0 1 auto; min-width: 0; margin-left: auto; }
@media (max-width: 1440px) { .sh-cluster { flex: 1 1 100%; margin-left: 0; justify-content: flex-start; row-gap: 8px; } }
.sh-div { width: 1px; height: 20px; background: rgba(255,255,255,.12); margin: 0 2px; flex-shrink: 0; }
.sh-params-btn {
  display: inline-flex; align-items: center; gap: 6px;
  font-size: 12px; font-weight: 600; font-family: inherit; color: rgba(255,255,255,.88);
  background: rgba(255,255,255,.08); border: 1px solid rgba(255,255,255,.16); border-radius: 9px;
  padding: 7px 13px; cursor: pointer; transition: all .15s ease;
}
.sh-params-btn:hover { background: rgba(255,255,255,.15); border-color: rgba(255,255,255,.28); transform: translateY(-1px); }

/* ── Состояния ── */
.sh-state { display: flex; flex-direction: column; gap: 10px; padding: 8px 0; }
.sh-skel { height: 96px; border-radius: 14px; background: linear-gradient(90deg, #F1F0F7 25%, #FAF9FE 50%, #F1F0F7 75%); background-size: 200% 100%; animation: shShimmer 1.4s ease-in-out var(--d, 0ms) infinite; }
@keyframes shShimmer { from { background-position: 200% 0; } to { background-position: -200% 0; } }
.sh-err { align-items: center; color: #E24B4A; font-size: 12.5px; flex-direction: row; gap: 12px; }
.sh-retry { font-size: 12px; font-weight: 600; font-family: inherit; border: 1px solid var(--border-hard, #E5E7EB); background: #fff; border-radius: 9px; padding: 6px 14px; cursor: pointer; }

.sh-section { animation: shSecIn .5s var(--ease-standard, ease) both; }
@keyframes shSecIn { from { opacity: 0; transform: translateY(6px); } to { opacity: 1; transform: translateY(0); } }

/* ── Карточки ── */
.sh-card {
  background: rgba(255,255,255,.82); backdrop-filter: blur(16px) saturate(1.5);
  border: 1px solid rgba(255,255,255,.70); border-radius: 14px; padding: 16px 18px;
  box-shadow: 0 2px 12px rgba(15,23,60,.07), 0 1px 3px rgba(15,23,60,.04);
  animation: finKpiCardIn .55s var(--ease-standard, ease) var(--d, 0ms) both;
  position: relative; overflow: hidden;
}
.sh-card::before { content: ''; position: absolute; top: 0; left: 0; right: 0; height: 3px;
  background: var(--accent, #7F77DD); border-radius: 14px 14px 0 0;
  animation: finKpi2DrawIn .8s var(--ease-standard) var(--d, 0ms) both; transform-origin: left center; }
.sh-card-hd { display: flex; align-items: flex-start; justify-content: space-between; gap: 12px; margin-bottom: 10px; flex-wrap: wrap; }
.sh-card-t { font-size: 13px; font-weight: 650; color: var(--t1, #1E2A4A); }
.sh-card-s { font-size: 10.5px; color: var(--t3, #94A3B8); margin-top: 2px; }
.sh-none { padding: 26px; text-align: center; color: var(--t3, #94A3B8); font-size: 12px; }
.sh-none.sm { padding: 10px; font-size: 10.5px; }

/* ── Pareto ── */
.sh-grid { display: grid; }
.sh-pareto-svgwrap { overflow-x: auto; }
.sh-pareto-svg { width: 100%; min-width: 640px; height: auto; display: block; }
.sh-grid-line { stroke: rgba(30,42,74,.07); stroke-width: 1; }
.sh-bar { transform-origin: center bottom; transform-box: fill-box; animation: shBarGrow .6s var(--ease-standard, ease) var(--d, 0ms) both; cursor: default; transition: filter .15s; }
.sh-bar:hover { filter: brightness(1.1) saturate(1.2); }
@keyframes shBarGrow { from { transform: scaleY(0); } to { transform: scaleY(1); } }
.sh-bar-lbl { font-size: 9px; font-weight: 600; fill: var(--t3, #94A3B8); letter-spacing: .02em; }
.sh-cum-line { stroke: var(--p-deep, #534AB7); stroke-width: 2; stroke-dasharray: 1400; stroke-dashoffset: 1400; animation: shLineDraw 1.2s ease .35s forwards; }
@keyframes shLineDraw { to { stroke-dashoffset: 0; } }
.sh-cum-dot { fill: #fff; stroke: var(--p-deep, #534AB7); stroke-width: 2; opacity: 0; animation: shDotIn .3s ease var(--d, 0ms) forwards; }
@keyframes shDotIn { to { opacity: 1; } }
.sh-axis-lbl { font-size: 9px; fill: var(--t3, #94A3B8); font-variant-numeric: tabular-nums; }

/* ── Тренды ── */
.sh-trends { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 10px; }
@media (max-width: 1100px) { .sh-trends { grid-template-columns: repeat(2, minmax(0, 1fr)); } }
@media (max-width: 560px) { .sh-trends { grid-template-columns: 1fr; } }
.sh-trend { display: flex; flex-direction: column; gap: 6px; }
.sh-trend-l { font-size: 10.5px; font-weight: 600; text-transform: uppercase; letter-spacing: .05em; color: var(--t3, #94A3B8); }
.sh-trend-v { font-size: 24px; font-weight: 400; letter-spacing: -.03em; color: var(--t1, #1E2A4A); font-variant-numeric: tabular-nums; display: flex; align-items: baseline; gap: 8px; }
.sh-trend-d { font-size: 11px; font-weight: 700; }
.sh-spark { width: 100%; height: 56px; }
.sh-spark-line { stroke-dasharray: 480; stroke-dashoffset: 480; animation: shLineDraw 1s ease .25s forwards; }
.sh-spark-dot { opacity: 0; animation: shDotIn .3s ease 1.1s forwards; }
.sh-trend-yrs { font-size: 9.5px; color: var(--t3, #94A3B8); font-variant-numeric: tabular-nums; }

@media (max-width: 720px) { .sh-section, .sh-state { margin: 0 8px; } .sh-title { font-size: 15px; } }
</style>
