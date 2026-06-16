<script setup lang="ts">
// ============================================================================
// Big sector-grouped financials table.
//
// Layout (1:1 legacy):
//   Header: Компания | 2021 | 2022 | 2023 | 2024 | 2025 | 2026 | YoY% |  bar  | %портфеля
//   For each sector group:
//     – Sector header strip (colored, with sector total + % of portfolio)
//     – Per-company rows with year values, YoY%, mini-bar (relative magnitude)
//
// All numbers are for the selected metric. Component re-derives values from
// props instead of doing API call — orchestrator passes already-aggregated
// SectorBucket[].
// ============================================================================

import { computed, ref } from "vue";
import type { SectorBucket } from "./financialsHelpers";
import { fmtCompact, fmtPctSigned } from "./financialsHelpers";
import CompanyAvatar from "@/components/CompanyAvatar.vue";
import { runForecast, type ForecastModel } from "@/utils/forecast";

const props = defineProps<{
  buckets: SectorBucket[];
  years: number[];
  unit: "bln" | "mln";
  metricLabel: string;
  /** Year used for YoY calc (current vs current-1) */
  currentYear: number;
  /** Portfolio-wide total of metric across ALL years (for % share calc) */
  grandTotalAllYears: number;
}>();

// Find max abs value across ALL companies for bar scaling
const maxAbsAllYears = computed(() => {
  let max = 0;
  for (const b of props.buckets) {
    for (const c of b.companies) {
      const v = Math.abs(c.sumAllYears);
      if (v > max) max = v;
    }
  }
  return max || 1;
});

// Bar width % helper
function barWidthPct(value: number): number {
  return Math.min(100, Math.round(Math.abs(value) / maxAbsAllYears.value * 100));
}

// Sector total for selected year (used for sector header)
// 2026-05-26: Number-coerce — defensive против string-from-Postgres-numeric.
function bucketSumAllYears(b: SectorBucket): number {
  return b.companies.reduce((s, c) => s + Number(c.sumAllYears ?? 0), 0);
}

function bucketShareOfPortfolio(b: SectorBucket): number {
  if (!props.grandTotalAllYears) return 0;
  return Math.round(Math.abs(bucketSumAllYears(b)) / Math.abs(props.grandTotalAllYears) * 100);
}

// YoY color (positive=green, negative=red, zero=gray)
function yoyColor(yoy: number | null): string {
  if (yoy == null) return "var(--t3, #64748B)";
  if (yoy > 0.5) return "#1D9E75";
  if (yoy < -0.5) return "#E24B4A";
  return "var(--t3, #64748B)";
}

// ── Прогнозные колонки: заполняем будущие годы прогнозом по выбранной модели ──
const FORECAST_OPTS: { id: ForecastModel | "off"; label: string }[] = [
  { id: "off", label: "Прогноз: выкл" },
  { id: "runrate", label: "Прогноз: Run-rate" },
  { id: "cagr", label: "Прогноз: CAGR" },
  { id: "linear", label: "Прогноз: линейный" },
];
const forecastModel = ref<ForecastModel | "off">("off");

// Последний год факта = макс. год с ненулевыми данными по любой компании.
const lastActualYear = computed(() => {
  let last = props.years[0] ?? 0;
  for (const b of props.buckets)
    for (const c of b.companies)
      for (const y of props.years)
        if (c.valuesByYear[y] != null && c.valuesByYear[y] !== 0 && y > last) last = y;
  return last;
});
function isForecastYear(y: number): boolean { return y > lastActualYear.value; }
function cellIsForecast(y: number): boolean { return forecastModel.value !== "off" && isForecastYear(y); }

const forecastMap = computed(() => {
  const map = new Map<string, Map<number, number>>();
  if (forecastModel.value === "off") return map;
  const histY = props.years.filter((y) => !isForecastYear(y));
  const fcY = props.years.filter(isForecastYear);
  if (!fcY.length) return map;
  for (const b of props.buckets)
    for (const c of b.companies) {
      const hist = histY.map((y) => ({ year: y, value: c.valuesByYear[y] ?? null }));
      const fc = runForecast(forecastModel.value as ForecastModel, hist, fcY);
      map.set(c.company_code, new Map(fc.map((p) => [p.year, p.value])));
    }
  return map;
});

function cellValue(c: SectorBucket["companies"][number], y: number): number | null {
  if (!isForecastYear(y)) return c.valuesByYear[y] ?? null;
  return forecastMap.value.get(c.company_code)?.get(y) ?? null;
}
</script>

<template>
  <div class="fst-card">
    <!-- Header -->
    <div class="fst-head">
      <div class="fst-eyebrow">{{ years[0] }}–{{ years[years.length - 1] }}, {{ unit === 'bln' ? 'МЛРД' : 'МЛН' }} UZS</div>
      <select v-model="forecastModel" class="fst-fc-select" title="Прогноз будущих лет">
        <option v-for="o in FORECAST_OPTS" :key="o.id" :value="o.id">{{ o.label }}</option>
      </select>
    </div>

    <!-- Горизонтальный скролл (моб.): шапка + строки скроллятся по X синхронно,
         иначе на узких экранах правые колонки обрезались (card overflow:hidden). -->
    <div class="fst-scroll">
    <!-- Column headers -->
    <div class="fst-col-row">
      <div class="fst-col fst-col-co">Компания</div>
      <div v-for="y in years" :key="y" class="fst-col fst-col-num" :class="{ 'fst-col-fc': cellIsForecast(y) }">{{ y }}<span v-if="cellIsForecast(y)" class="fst-fc-tag">П</span></div>
      <div class="fst-col fst-col-yoy">YoY</div>
      <div class="fst-col fst-col-bar"></div>
      <div class="fst-col fst-col-share">%портф.</div>
    </div>

    <!-- Sector groups -->
    <div class="fst-body">
      <template v-for="b in buckets" :key="b.sectorCode">
        <!-- Sector strip -->
        <div class="fst-sec uza-side-stripe uza-side-stripe-tight"
             :style="{
               background: b.color + '0E',
               '--stripe-color': b.color,
               borderBottomColor: b.color + '24',
             }">
          <span class="fst-sec-label" :style="{ color: b.color }">
            {{ b.label }} <span class="fst-sec-cnt">({{ b.companies.length }})</span>
          </span>
          <div class="fst-sec-meta">
            <span class="fst-sec-tot">Σ {{ fmtCompact(bucketSumAllYears(b), unit) }}</span>
            <span class="fst-sec-share">· {{ bucketShareOfPortfolio(b) }}% портф.</span>
            <span class="fst-sec-pct" :style="{ color: b.color }">{{ bucketShareOfPortfolio(b) }}%</span>
          </div>
        </div>

        <!-- Company rows -->
        <div v-for="(c, i) in b.companies"
             :key="c.company_code"
             class="fst-row uza-side-stripe uza-side-stripe-tight"
             :style="{
               '--stripe-color': `${b.color}1F`,
               animationDelay: (i * 25) + 'ms',
             }">
          <div class="fst-cell-co" style="display:flex; align-items:center; gap:8px; min-width:0;">
            <CompanyAvatar :name="c.company_name_short || c.company_name" :color="b.color" :size="20" />
            <span style="min-width:0; overflow:hidden; text-overflow:ellipsis;">{{ c.company_name_short || c.company_name }}</span>
          </div>

          <div v-for="y in years" :key="y" class="fst-cell-num" :class="{ 'fst-cell-fc': cellIsForecast(y) }">
            <span :class="{ 'fst-num-empty': cellValue(c, y) == null }">
              {{ fmtCompact(cellValue(c, y), unit) }}
            </span>
          </div>

          <div class="fst-cell-yoy" :style="{ color: yoyColor(c.yoyPct) }">
            {{ c.yoyPct == null ? '—' : fmtPctSigned(c.yoyPct) }}
          </div>

          <div class="fst-cell-bar">
            <div class="fst-bar-track">
              <div class="fst-bar-fill"
                   :style="{
                     '--w': barWidthPct(c.sumAllYears) + '%',
                     background: b.color,
                     opacity: c.sumAllYears < 0 ? 0.5 : 0.85,
                   }" />
            </div>
          </div>

          <div class="fst-cell-share">
            {{ Math.round(Math.abs(c.sumAllYears) / Math.max(grandTotalAllYears, 1) * 100) }}%
          </div>
        </div>
      </template>

      <div v-if="!buckets.length" class="fst-empty">
        Нет данных по выбранной метрике «{{ metricLabel }}»
      </div>
    </div>
    </div><!-- /.fst-scroll -->
  </div>
</template>

<style scoped>
.fst-card {
  background: var(--card-bg, rgba(255, 255, 255, .82));
  backdrop-filter: blur(16px) saturate(1.5);
  -webkit-backdrop-filter: blur(16px) saturate(1.5);
  border: 1px solid var(--card-border, rgba(255, 255, 255, .70));
  border-radius: 16px;
  box-shadow: 0 2px 12px rgba(15, 23, 60, .07), 0 1px 3px rgba(15, 23, 60, .04);
  overflow: hidden;
  animation: finFadeSlideIn .4s ease 280ms both;
}

.fst-head {
  padding: 9px 14px;
  border-bottom: 0.5px solid var(--border, var(--border-input));
  display: flex; align-items: center; justify-content: space-between; gap: 12px;
}
.fst-eyebrow {
  font-size: 11px;
  font-weight: 600;
  color: var(--t1, #1E2A4A);
  letter-spacing: 0.04em;
  text-transform: uppercase;
}
.fst-fc-select {
  font-size: 11px; font-weight: 600; font-family: inherit;
  color: #4B4193; background: #ECEAFB; border: 1px solid #B9B4E8;
  border-radius: 8px; padding: 4px 9px; cursor: pointer;
}
/* Прогнозные колонки — янтарная подсветка + «П» */
.fst-col-fc { color: #A36500 !important; }
.fst-fc-tag {
  font-size: 8px; font-weight: 700; color: #A36500; background: rgba(224,146,47,.16);
  border-radius: 3px; padding: 0 3px; margin-left: 3px; vertical-align: super;
}
.fst-cell-fc { background: rgba(224,146,47,.05); border-left: 1px dashed rgba(224,146,47,.4); }
.fst-cell-fc span { color: #8A5A12; font-style: italic; }
.fst-cell-fc span.fst-num-empty { color: var(--t3, #94A3B8); font-style: normal; }

/* Column headers */
.fst-col-row {
  display: grid;
  grid-template-columns: minmax(160px, 2fr)
                         repeat(6, minmax(60px, 1fr))
                         60px
                         minmax(80px, 1.2fr)
                         60px;
  background: var(--bg3, #F1F5F9);
  border-bottom: 1px solid var(--border, var(--border-input));
  padding: 6px 12px;
  position: sticky;   /* frozen-шапка при вертикальном скролле внутри .fst-scroll */
  top: 0;
  z-index: 2;
}
.fst-col {
  font-size: 10px;
  font-weight: 600;
  color: var(--t3, var(--t3));
  text-transform: uppercase;
  letter-spacing: 0.06em;
  padding: 0 4px;
  text-align: right;
  font-variant-numeric: tabular-nums;
}
.fst-col-co { text-align: left; }
.fst-col-yoy { text-align: right; }
.fst-col-share { text-align: right; }
.fst-col-bar { text-align: left; }

/* Scroll-обёртка: вертикаль (как было у body) + горизонталь (для узких экранов).
   Один контейнер на шапку+тело → они скроллятся по X синхронно и выровнены. */
.fst-scroll {
  overflow: auto;
  max-height: 760px;
  scrollbar-width: thin;
}
.fst-scroll::-webkit-scrollbar { height: 8px; width: 8px; }
.fst-scroll::-webkit-scrollbar-thumb { background: rgba(15, 23, 60, .18); border-radius: 4px; }

/* Body */
.fst-body { /* скролл перенесён на .fst-scroll */ }

.fst-sec {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 6px 14px 6px 18px;
  border-bottom: 0.5px solid;
  animation: finFadeSlideIn .25s ease both;
}
.fst-sec-label {
  font-size: 11px; font-weight: 700;
  text-transform: uppercase; letter-spacing: 0.06em;
}
.fst-sec-cnt { font-weight: 400; opacity: 0.7; }
.fst-sec-meta {
  display: inline-flex; align-items: center; gap: 8px;
  font-size: 11px; font-weight: 500;
  color: var(--t2, #4B5468);
}
.fst-sec-tot { font-variant-numeric: tabular-nums; }
.fst-sec-share { color: var(--t3, var(--t3)); }
.fst-sec-pct {
  font-weight: 700;
  font-variant-numeric: tabular-nums;
  min-width: 36px;
  text-align: right;
}

/* Row */
.fst-row {
  display: grid;
  grid-template-columns: minmax(160px, 2fr)
                         repeat(6, minmax(60px, 1fr))
                         60px
                         minmax(80px, 1.2fr)
                         60px;
  padding: 5px 12px 5px 18px;
  border-bottom: 0.5px solid var(--border, var(--border-input));
  align-items: center;
  transition: background .12s;
  font-size: 12px;
  animation: finFadeSlideIn .22s ease both;
}
.fst-row:hover { background: rgba(127, 119, 221, .06); }

.fst-cell-co {
  font-weight: 500;
  color: var(--t1, #1E2A4A);
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
  padding-right: 4px;
}
.fst-cell-num, .fst-cell-yoy, .fst-cell-share {
  text-align: right;
  font-variant-numeric: tabular-nums;
  padding: 0 4px;
}
.fst-num-empty { color: var(--t3, var(--t3)); }

.fst-cell-yoy { font-weight: 600; }
.fst-cell-share { color: var(--t3, var(--t3)); font-weight: 500; font-size: 11px; }

.fst-cell-bar {
  padding: 0 4px;
}
.fst-bar-track {
  height: 6px;
  background: rgba(241, 245, 249, 0.5);
  border-radius: 3px;
  overflow: hidden;
}
.fst-bar-fill {
  height: 100%;
  border-radius: 3px;
  width: var(--w, 0%);
  animation: finBarGrow .65s var(--ease-standard) both;
}

.fst-empty {
  padding: 30px 14px;
  text-align: center;
  color: var(--t3, var(--t3));
  font-size: 12px;
  font-style: italic;
}
</style>
