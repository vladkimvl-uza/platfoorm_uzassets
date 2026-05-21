<script setup lang="ts">
/**
 * BottomAnalytics — live KPIs computed from active year cells.
 *
 * Inputs:
 *   - computedActive: result of formula engine for the active year (Record<code, string>)
 *   - year: active year (for labels)
 *   - prevComputed: optional previous year computed (for ▲/▼ trend %)
 *   - divisor: 1/1000/1_000_000 to convert displayed KPI values
 */
import { computed, ref } from "vue";

const props = defineProps<{
  computedActive: Record<string, string>;
  prevComputed: Record<string, string> | null;
  year: number | null;
  divisor: number;
}>();

const subTab = ref<"structure" | "dynamics" | "ratios" | "compare">("structure");

function n(code: string, src?: Record<string, string>): number {
  const raw = (src ?? props.computedActive)[code];
  if (!raw) return 0;
  const v = Number(raw);
  return Number.isFinite(v) ? v : 0;
}

const totals = computed(() => ({
  assets:    n("400"),
  equity:    n("480"),
  ltLiab:    n("490"),
  stLiab:    n("600"),
  totalLiab: n("770"),
  // structure breakdown (active year)
  fixedAssets: n("130"),
  inventory:   n("140"),
  receivables: n("210"),
  cash:        n("320"),
  // P&L
  revenue:     n("PL_010"),
  netProfit:   n("PL_270"),
}));

const ratios = computed(() => {
  const t = totals.value;
  return {
    de: t.equity > 0 ? t.totalLiab / t.equity : 0,
    current: t.stLiab > 0 ? (n("140") + n("210") + n("320") + n("370") + n("380")) / t.stLiab : 0,
    roe: t.equity > 0 ? (t.netProfit / t.equity) * 100 : 0,
    roa: t.assets > 0 ? (t.netProfit / t.assets) * 100 : 0,
  };
});

const trend = computed(() => {
  if (!props.prevComputed) return { assets: null, equity: null };
  function pct(code: string): number | null {
    const prev = n(code, props.prevComputed!);
    const curr = n(code);
    if (prev === 0) return null;
    return (curr - prev) / Math.abs(prev) * 100;
  }
  return { assets: pct("400"), equity: pct("480") };
});

function fmt(v: number, decimals = 0): string {
  if (!Number.isFinite(v) || v === 0) return "—";
  const scaled = v / props.divisor;
  return scaled.toLocaleString("ru-RU", { minimumFractionDigits: decimals, maximumFractionDigits: decimals });
}

function fmtPct(v: number | null): string {
  if (v == null || !Number.isFinite(v)) return "—";
  const arrow = v >= 0 ? "▲" : "▼";
  return `${arrow} ${Math.abs(v).toFixed(1)}%`;
}

const haveData = computed(() => totals.value.assets > 0 || totals.value.totalLiab > 0);

// Structure breakdown — % of total assets
const structure = computed(() => {
  const a = totals.value.assets;
  if (a === 0) return null;
  return {
    asset: {
      total: a,
      fixed: { v: totals.value.fixedAssets, pct: totals.value.fixedAssets / a * 100 },
      inv:   { v: totals.value.inventory,   pct: totals.value.inventory / a * 100 },
      recv:  { v: totals.value.receivables, pct: totals.value.receivables / a * 100 },
      cash:  { v: totals.value.cash,        pct: totals.value.cash / a * 100 },
    },
    liab: {
      total: totals.value.equity + totals.value.totalLiab,
      eq:    { v: totals.value.equity, pct: totals.value.equity / a * 100 },
      lt:    { v: totals.value.ltLiab, pct: totals.value.ltLiab / a * 100 },
      st:    { v: totals.value.stLiab, pct: totals.value.stLiab / a * 100 },
    },
  };
});

const delta = computed(() => {
  return totals.value.totalLiab + totals.value.equity - totals.value.assets;
});
</script>

<template>
  <section class="fm-analytics">
    <div class="fm-analytics-header">
      <div class="fm-analytics-header-left">
        <span class="fm-cap">Live аналитика</span>
        <span class="fm-muted-flex">
          <span :class="['fm-pulse-dot-small', haveData ? '' : 'fm-pulse-dot-off']"></span>
          {{ haveData ? `год ${year}` : "нет данных" }}
        </span>
      </div>
      <div class="fm-subtabs">
        <button :class="['fm-subtab', { 'fm-subtab-on': subTab === 'structure' }]" @click="subTab = 'structure'">Структура</button>
        <button :class="['fm-subtab', { 'fm-subtab-on': subTab === 'dynamics' }]" @click="subTab = 'dynamics'">Динамика</button>
        <button :class="['fm-subtab', { 'fm-subtab-on': subTab === 'ratios' }]" @click="subTab = 'ratios'">Коэффициенты</button>
        <button :class="['fm-subtab', { 'fm-subtab-on': subTab === 'compare' }]" @click="subTab = 'compare'">Сравнение</button>
      </div>
    </div>

    <!-- Row 1: 4 KPI cards (always rendered) -->
    <div class="fm-kpi-row">
      <div class="fm-kpi-card">
        <div class="fm-kpi-card-header">
          <span class="fm-cap-sm">Total Assets {{ year ? `· ${year}` : "" }}</span>
          <span v-if="trend.assets !== null" :class="['fm-trend', trend.assets >= 0 ? 'fm-trend-up' : 'fm-trend-down']">{{ fmtPct(trend.assets) }}</span>
        </div>
        <div :class="['fm-kpi-value', { 'fm-kpi-empty': !haveData }]">{{ fmt(totals.assets) }}</div>
      </div>
      <div class="fm-kpi-card">
        <div class="fm-kpi-card-header">
          <span class="fm-cap-sm">Equity {{ year ? `· ${year}` : "" }}</span>
          <span v-if="trend.equity !== null" :class="['fm-trend', trend.equity >= 0 ? 'fm-trend-up' : 'fm-trend-down']">{{ fmtPct(trend.equity) }}</span>
        </div>
        <div :class="['fm-kpi-value', { 'fm-kpi-empty': !haveData }]">{{ fmt(totals.equity) }}</div>
      </div>
      <div class="fm-kpi-card">
        <div class="fm-kpi-card-header">
          <span class="fm-cap-sm">D/E ratio</span>
          <span v-if="haveData" :class="['fm-pill-sm', ratios.de <= 1.5 ? 'fm-pill-green' : ratios.de <= 3 ? 'fm-pill-amber' : 'fm-pill-red']">
            {{ ratios.de <= 1.5 ? "здоровый" : ratios.de <= 3 ? "умеренный" : "высокий" }}
          </span>
        </div>
        <div :class="['fm-kpi-value', { 'fm-kpi-empty': !haveData }]">
          {{ haveData ? `${ratios.de.toFixed(2)}×` : "—" }}
        </div>
        <div class="fm-kpi-subnote">долг / капитал</div>
      </div>
      <div class="fm-kpi-card">
        <div class="fm-kpi-card-header">
          <span class="fm-cap-sm">Current Ratio</span>
          <span v-if="haveData" :class="['fm-pill-sm', ratios.current >= 1.5 ? 'fm-pill-green' : ratios.current >= 1 ? 'fm-pill-amber' : 'fm-pill-red']">
            {{ ratios.current >= 1.5 ? "OK" : ratios.current >= 1 ? "слабо" : "риск" }}
          </span>
        </div>
        <div :class="['fm-kpi-value', { 'fm-kpi-empty': !haveData }]">
          {{ haveData ? `${ratios.current.toFixed(2)}×` : "—" }}
        </div>
        <div class="fm-kpi-subnote">тек. активы / тек. обязат.</div>
      </div>
    </div>

    <!-- Row 2: subtab content -->
    <div class="fm-analytics-row2">
      <template v-if="subTab === 'structure'">
        <div class="fm-block">
          <div class="fm-block-header">
            <span class="fm-cap-sm">Структура баланса {{ year ? `· ${year}` : "" }}</span>
            <span class="fm-muted fm-num" style="font-size: 10px;">{{ structure ? `всего ${fmt(structure.asset.total)}` : "—" }}</span>
          </div>
          <template v-if="structure">
            <div class="fm-bar-group">
              <div class="fm-bar-header">
                <span class="fm-bar-label">АКТИВ</span>
                <span class="fm-muted fm-num" style="font-size: 9.5px;">{{ fmt(structure.asset.total) }}</span>
              </div>
              <div class="fm-stacked-bar">
                <div v-if="structure.asset.fixed.pct > 0" class="fm-bar-seg" :style="`flex: ${structure.asset.fixed.pct}; background: #534AB7; font-weight: 500;`">
                  ВнА {{ structure.asset.fixed.pct.toFixed(0) }}%
                </div>
                <div v-if="structure.asset.inv.pct > 0" class="fm-bar-seg" :style="`flex: ${structure.asset.inv.pct}; background: #7F77DD; padding-left: 5px; font-weight: 500;`">
                  ТМЗ {{ structure.asset.inv.pct.toFixed(0) }}%
                </div>
                <div v-if="structure.asset.recv.pct > 0" class="fm-bar-seg" :style="`flex: ${structure.asset.recv.pct}; background: #378ADD; padding-left: 4px;`">
                  Деб {{ structure.asset.recv.pct.toFixed(0) }}%
                </div>
                <div v-if="structure.asset.cash.pct > 0" class="fm-bar-seg" :style="`flex: ${structure.asset.cash.pct}; background: #1D9E75; padding-left: 3px;`">
                  $ {{ structure.asset.cash.pct.toFixed(0) }}%
                </div>
              </div>
            </div>
            <div class="fm-bar-group">
              <div class="fm-bar-header">
                <span class="fm-bar-label">ПАССИВ</span>
                <span class="fm-muted fm-num" style="font-size: 9.5px;">{{ fmt(structure.liab.total) }}</span>
              </div>
              <div class="fm-stacked-bar">
                <div v-if="structure.liab.eq.pct > 0" class="fm-bar-seg" :style="`flex: ${structure.liab.eq.pct}; background: #1D9E75; font-weight: 500;`">
                  Капитал {{ structure.liab.eq.pct.toFixed(0) }}%
                </div>
                <div v-if="structure.liab.lt.pct > 0" class="fm-bar-seg" :style="`flex: ${structure.liab.lt.pct}; background: #EF9F27; padding-left: 5px; font-weight: 500;`">
                  Долгоср. {{ structure.liab.lt.pct.toFixed(0) }}%
                </div>
                <div v-if="structure.liab.st.pct > 0" class="fm-bar-seg" :style="`flex: ${structure.liab.st.pct}; background: #E24B4A; padding-left: 4px;`">
                  Краткоср. {{ structure.liab.st.pct.toFixed(0) }}%
                </div>
              </div>
            </div>
            <div class="fm-structure-footer">
              <svg width="13" height="13" viewBox="0 0 16 16" fill="none"
                   :stroke="Math.abs(delta) < 0.01 ? '#0F6E56' : '#C0322F'"
                   stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <circle cx="8" cy="8" r="6"/>
                <path v-if="Math.abs(delta) < 0.01" d="M5 8l2 2 4-4"/>
                <path v-else d="M5 5l6 6M5 11l6-6"/>
              </svg>
              <span :style="`color: ${Math.abs(delta) < 0.01 ? '#0F6E56' : '#C0322F'};`">
                {{ Math.abs(delta) < 0.01 ? "Баланс сошёлся · Δ = 0" : `Расхождение Δ = ${delta.toLocaleString("ru-RU")}` }}
              </span>
              <span class="fm-muted" style="margin-left: auto;">ROE {{ ratios.roe.toFixed(1) }}% · ROA {{ ratios.roa.toFixed(1) }}%</span>
            </div>
          </template>
          <div v-else class="fm-block-empty">Введите значения активов чтобы увидеть структуру</div>
        </div>
      </template>

      <template v-else-if="subTab === 'dynamics'">
        <div class="fm-block fm-block-empty">График динамики — в разработке (нужны multi-year данные)</div>
      </template>

      <template v-else-if="subTab === 'ratios'">
        <div class="fm-block">
          <div class="fm-block-header">
            <span class="fm-cap-sm">Коэффициенты {{ year ? `· ${year}` : "" }}</span>
          </div>
          <div v-if="haveData" class="fm-ratios-grid">
            <div class="fm-ratio-item">
              <span class="fm-ratio-label">D/E ratio</span>
              <span class="fm-ratio-val">{{ ratios.de.toFixed(2) }}×</span>
            </div>
            <div class="fm-ratio-item">
              <span class="fm-ratio-label">Current ratio</span>
              <span class="fm-ratio-val">{{ ratios.current.toFixed(2) }}×</span>
            </div>
            <div class="fm-ratio-item">
              <span class="fm-ratio-label">ROE</span>
              <span class="fm-ratio-val">{{ ratios.roe.toFixed(1) }}%</span>
            </div>
            <div class="fm-ratio-item">
              <span class="fm-ratio-label">ROA</span>
              <span class="fm-ratio-val">{{ ratios.roa.toFixed(1) }}%</span>
            </div>
          </div>
          <div v-else class="fm-block-empty">Нет данных для расчёта</div>
        </div>
      </template>

      <template v-else-if="subTab === 'compare'">
        <div class="fm-block fm-block-empty">Сравнение с peer-компанией — в разработке</div>
      </template>
    </div>
  </section>
</template>

<style scoped>
.fm-analytics {
  background: linear-gradient(180deg, #FAFAFC 0%, #F5F4FA 100%);
  border-top: 0.5px solid #E5E7EB;
  padding: 14px 18px;
}
.fm-analytics-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
}
.fm-analytics-header-left {
  display: flex;
  align-items: center;
  gap: 8px;
}
.fm-cap {
  font-size: 10px; font-weight: 500;
  color: #888780; letter-spacing: .08em; text-transform: uppercase;
}
.fm-cap-sm {
  font-size: 9.5px; font-weight: 500;
  color: #888780; letter-spacing: .06em; text-transform: uppercase;
}
.fm-muted { color: #888780; }
.fm-muted-flex {
  display: flex; align-items: center; gap: 4px;
  font-size: 10px; color: #888780;
}
.fm-num { font-variant-numeric: tabular-nums; }
.fm-pulse-dot-small {
  width: 5px; height: 5px; background: #1D9E75; border-radius: 50%;
  animation: fmPulse 2s infinite;
}
.fm-pulse-dot-off { background: #C8C7C0; animation: none; }
@keyframes fmPulse {
  0%, 100% { opacity: 1; transform: scale(1); }
  50% { opacity: .5; transform: scale(1.3); }
}
.fm-subtabs { display: flex; gap: 3px; }
.fm-subtab {
  padding: 4px 10px; font-size: 10px; font-family: inherit; cursor: pointer;
  background: transparent; border: none; color: #888780; border-radius: 8px;
}
.fm-subtab-on {
  background: #fff; border: 0.5px solid #E5E7EB;
  color: #1E2A4A; font-weight: 500;
}

.fm-kpi-row {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 8px;
  margin-bottom: 12px;
}
.fm-kpi-card {
  background: #fff;
  border-radius: 9px;
  padding: 10px 12px;
  border: 0.5px solid #E5E7EB;
}
.fm-kpi-card-header {
  display: flex; justify-content: space-between; align-items: center;
}
.fm-kpi-value {
  font-size: 18px; font-weight: 500;
  margin-top: 3px; letter-spacing: -.02em;
  font-variant-numeric: tabular-nums;
}
.fm-kpi-empty { color: #C8C7C0; }
.fm-kpi-subnote { font-size: 10px; margin-top: 5px; color: #888780; }
.fm-trend { font-size: 9.5px; }
.fm-trend-up { color: #1D9E75; }
.fm-trend-down { color: #C0322F; }

.fm-pill-sm {
  padding: 1px 5px; border-radius: 4px;
  font-size: 8.5px; font-weight: 500;
}
.fm-pill-green { background: rgba(29, 158, 117, .12); color: #0F6E56; }
.fm-pill-amber { background: rgba(239, 159, 39, .14); color: #B96A07; }
.fm-pill-red   { background: rgba(226, 75, 74, .12); color: #C0322F; }

.fm-analytics-row2 { display: grid; grid-template-columns: 1fr; gap: 10px; }
.fm-block {
  background: #fff;
  border-radius: 9px;
  padding: 12px 14px;
  border: 0.5px solid #E5E7EB;
}
.fm-block-header {
  display: flex; justify-content: space-between; align-items: center;
  margin-bottom: 10px;
}
.fm-block-empty {
  padding: 18px 12px;
  text-align: center;
  font-size: 11px;
  color: #C8C7C0;
  font-style: italic;
}
.fm-bar-group { margin-bottom: 9px; }
.fm-bar-group:last-of-type { margin-bottom: 0; }
.fm-bar-header {
  display: flex; justify-content: space-between; align-items: baseline;
  margin-bottom: 4px;
}
.fm-bar-label { font-size: 10.5px; color: #1E2A4A; font-weight: 500; }
.fm-stacked-bar {
  display: flex; height: 22px; border-radius: 5px; overflow: hidden;
}
.fm-bar-seg {
  display: flex; align-items: center;
  padding-left: 7px;
  color: #fff; font-size: 9.5px;
}
.fm-structure-footer {
  display: flex; align-items: center; gap: 8px;
  margin-top: 10px; padding-top: 9px;
  border-top: 0.5px solid #F1EFE8;
  font-size: 10.5px;
}

.fm-ratios-grid {
  display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px;
}
.fm-ratio-item {
  display: flex; flex-direction: column; gap: 3px;
  padding: 8px;
  background: #FAFAFC;
  border-radius: 7px;
}
.fm-ratio-label {
  font-size: 9.5px; color: #888780;
  letter-spacing: .06em; text-transform: uppercase;
}
.fm-ratio-val {
  font-size: 16px; font-weight: 500;
  color: #1E2A4A; font-variant-numeric: tabular-nums;
}
</style>
