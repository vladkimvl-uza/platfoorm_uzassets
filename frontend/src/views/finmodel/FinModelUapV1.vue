<template>
  <div class="fm-scroll">
    <header class="fm-top">
      <div class="fm-top-l">
        <div class="fm-top-eyebrow">
          FinModel · <span class="fm-v">v1</span> · airport-style
        </div>
        <h1 class="fm-top-t">АО «Uzbekistan Airports»</h1>
        <p class="fm-top-s">
          Горизонт {{ horizon.startYear }}–{{ horizon.endYear }} ·
          {{ horizon.factYears.length }} факт-года + {{ horizon.forecastYears.length }} прогнозных ·
          Шаблон: EY/PwC airport-style (Volume × Tariffs = Revenue)
        </p>
      </div>
      <div class="fm-top-r">
        <button
          v-for="s in scenarios"
          :key="s.id"
          class="fm-scn"
          :class="{ active: scenario === s.id }"
          :style="{ '--tone': s.tone }"
          @click="scenario = s.id"
        >
          {{ s.label }}
        </button>
        <button class="fm-edit-btn" @click="editorOpen = true" title="Редактировать модель">
          <svg width="13" height="13" viewBox="0 0 24 24" fill="none"
               stroke="currentColor" stroke-width="2"
               stroke-linecap="round" stroke-linejoin="round">
            <path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/>
            <path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"/>
          </svg>
          Редактор
        </button>
      </div>
    </header>

    <div class="fm-body">
      <section class="fm-kpi-row">
        <div
          v-for="(k, i) in kpiCards"
          :key="k.label"
          class="fm-card fm-kpi"
          :style="{ '--d': (i * 60) + 'ms', '--accent': k.accent }"
        >
          <div class="fm-kpi-lbl">{{ k.label }}</div>
          <div class="fm-kpi-val" :style="{ color: k.accent }">
            {{ k.value }}<small v-if="k.unit">{{ k.unit }}</small>
          </div>
          <div class="fm-kpi-sub">{{ k.sub }}</div>
        </div>
      </section>

      <!-- P&L table — fact years + forecast years, по строкам Revenue/EBITDA/Net Income -->
      <section class="fm-card fm-pnl-card" style="--d: 480ms">
        <div class="fm-card-ttl">
          <span>P&amp;L · сценарий «{{ activeScenarioLabel }}»</span>
          <span class="fm-card-meta">млн сум</span>
        </div>
        <div class="fm-pnl-wrap">
          <table class="fm-pnl">
            <thead>
              <tr>
                <th>Показатель</th>
                <th v-for="y in allYears" :key="y" :class="{ forecast: !isFactYear(y) }">
                  {{ y }}<span v-if="!isFactYear(y)" class="fm-pnl-flag">П</span>
                </th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="row in pnlRows" :key="row.code" :class="row.cls">
                <td class="fm-pnl-name">{{ row.label }}</td>
                <td
                  v-for="y in allYears"
                  :key="y"
                  :class="{ forecast: !isFactYear(y), neg: outputs[y][row.code] < 0 }"
                >{{ fmtMln(outputs[y][row.code]) }}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </section>

      <section class="fm-card fm-airports-card" style="--d: 560ms">
        <div class="fm-card-ttl">
          <span>Загрузка по аэропортам · {{ activeModel.airportLoad.length }}</span>
          <span class="fm-card-meta">load factor (0..1.2)</span>
        </div>
        <div class="fm-airports">
          <div
            v-for="(ap, i) in activeModel.airportLoad"
            :key="ap.name"
            class="fm-ap-row"
            :style="{ '--d': (i * 30) + 'ms' }"
          >
            <div class="fm-ap-name">{{ ap.name }}</div>
            <div class="fm-ap-bar">
              <div
                class="fm-ap-fill"
                :style="{
                  width: Math.min(100, ap.load * 100) + '%',
                  background: ap.load >= 0.7 ? '#1D9E75' : ap.load >= 0.4 ? '#EF9F27' : '#E24B4A',
                }"
              />
            </div>
            <div class="fm-ap-pct" :class="{ hi: ap.load >= 0.7, mid: ap.load >= 0.4 && ap.load < 0.7, lo: ap.load < 0.4 }">
              {{ (ap.load * 100).toFixed(0) }}%
            </div>
          </div>
        </div>
      </section>

      <!-- Drivers grid: Volumes / Tariffs / Costs / CAPEX -->
      <section class="fm-driv-grid">
        <FmDriverList
          title="Объёмы (Volumes)"
          accent="#7F77DD"
          :items="activeModel.drivers.volumes"
          :years="allYears"
          :fact-years="horizon.factYears"
        />
        <FmDriverList
          title="Тарифы (Tariffs)"
          accent="#534AB7"
          :items="activeModel.drivers.tariffs"
          :years="allYears"
          :fact-years="horizon.factYears"
        />
        <FmDriverList
          title="OPEX (Costs)"
          accent="#EF9F27"
          :items="activeModel.drivers.costs"
          :years="allYears"
          :fact-years="horizon.factYears"
        />
        <FmDriverList
          title="CAPEX"
          accent="#378ADD"
          :items="activeModel.drivers.capex"
          :years="allYears"
          :fact-years="horizon.factYears"
        />
      </section>

      <!-- Assumptions card -->
      <section class="fm-card fm-asm-card" style="--d: 740ms">
        <div class="fm-card-ttl">
          <span>Допущения</span>
          <span class="fm-card-meta">DCF parameters</span>
        </div>
        <div class="fm-asm-grid">
          <div class="fm-asm-item">
            <div class="fm-asm-lbl">Налог на прибыль</div>
            <div class="fm-asm-val">{{ fmtPct(activeModel.assumptions.taxRate) }}</div>
          </div>
          <div class="fm-asm-item">
            <div class="fm-asm-lbl">WACC</div>
            <div class="fm-asm-val">{{ fmtPct(activeModel.assumptions.wacc) }}</div>
          </div>
          <div class="fm-asm-item">
            <div class="fm-asm-lbl">Cost of debt</div>
            <div class="fm-asm-val">{{ fmtPct(activeModel.assumptions.effectiveCostOfDebt) }}</div>
          </div>
          <div class="fm-asm-item">
            <div class="fm-asm-lbl">Терминальный рост</div>
            <div class="fm-asm-val">{{ fmtPct(activeModel.assumptions.terminalGrowth) }}</div>
          </div>
          <div class="fm-asm-item">
            <div class="fm-asm-lbl">Дивиденды (payout)</div>
            <div class="fm-asm-val">{{ fmtPct(activeModel.assumptions.dividendPayout) }}</div>
          </div>
          <div class="fm-asm-item">
            <div class="fm-asm-lbl">Risk-free rate</div>
            <div class="fm-asm-val">{{ fmtPct(activeModel.assumptions.riskFreeRate) }}</div>
          </div>
          <div class="fm-asm-item">
            <div class="fm-asm-lbl">Beta</div>
            <div class="fm-asm-val">{{ activeModel.assumptions.beta.toFixed(2) }}</div>
          </div>
          <div class="fm-asm-item">
            <div class="fm-asm-lbl">Market risk premium</div>
            <div class="fm-asm-val">{{ fmtPct(activeModel.assumptions.marketRiskPremium) }}</div>
          </div>
        </div>
      </section>

      <footer class="fm-foot">
        <span>
          модель сохраняется в localStorage (key: <code>uza_fm_uap_v1</code>) ·
          v1 для аэропортов
        </span>
      </footer>
    </div>

    <!-- Editor modal -->
    <FmEditorModal v-if="editorOpen" :model="activeModel" :scenario="scenario"
                    @close="editorOpen = false" @saved="onSaved" />
  </div>
</template>

<script setup lang="ts">
import { computed, ref, watch } from "vue";
import { useSavedFilter } from "@/composables/useSavedFilter";
import {
  UAP_SEED, SCENARIOS,
  computeOutputs, fmtMln, fmtPct,
  type ScenarioId, type FmAllScenarios, type FmScenarioModel, type FmYearOutputs,
} from "./fmUapSeed";
import FmDriverList from "./FmDriverList.vue";
import FmEditorModal from "./FmEditorModal.vue";

const LS_KEY = "uza_fm_uap_v1";

// Persisted full model (3 scenarios)
const persistedModel = useSavedFilter<FmAllScenarios>(LS_KEY, structuredClone(UAP_SEED));
const scenario = useSavedFilter<ScenarioId>("fm-uap.scenario", "base");
const editorOpen = ref(false);

const scenarios = SCENARIOS;
const activeModel = computed<FmScenarioModel>(() => persistedModel.value[scenario.value]);
const activeScenarioLabel = computed(() =>
  SCENARIOS.find((s) => s.id === scenario.value)?.label ?? "—",
);
const horizon = computed(() => activeModel.value.horizon);
const allYears = computed(() => [...horizon.value.factYears, ...horizon.value.forecastYears]);
function isFactYear(y: number) { return horizon.value.factYears.includes(y); }

const outputs = computed<Record<number, FmYearOutputs>>(() => computeOutputs(activeModel.value));

const kpiCards = computed(() => {
  const fy = horizon.value.forecastYears[horizon.value.forecastYears.length - 1]; // terminal
  const o = outputs.value[fy] || ({} as FmYearOutputs);
  const ebitdaMargin = o.revenue ? (o.ebitda / o.revenue) : 0;
  const netMargin = o.revenue ? (o.netIncome / o.revenue) : 0;
  const netDebtEbitda = o.ebitda ? (o.netDebt / o.ebitda) : 0;
  // CAGR revenue от первого фактического до терминального
  const firstY = horizon.value.factYears[0];
  const firstR = outputs.value[firstY]?.revenue || 1;
  const yearSpan = fy - firstY;
  const cagr = yearSpan > 0 ? Math.pow(o.revenue / firstR, 1 / yearSpan) - 1 : 0;
  return [
    { label: "Revenue " + fy, value: fmtMln(o.revenue), unit: "", accent: "#7F77DD", sub: "Σ vol × tarf" },
    { label: "EBITDA " + fy,  value: fmtMln(o.ebitda),  unit: "", accent: "#1D9E75", sub: "Revenue − OPEX" },
    { label: "EBITDA-margin", value: fmtPct(ebitdaMargin), unit: "", accent: "#1D9E75", sub: "EBITDA / Revenue" },
    { label: "Net Income " + fy, value: fmtMln(o.netIncome), unit: "", accent: o.netIncome >= 0 ? "#0F6E56" : "#E24B4A", sub: "После налога" },
    { label: "Net Margin", value: fmtPct(netMargin),  unit: "", accent: "#534AB7", sub: "NI / Revenue" },
    { label: "Net Debt / EBITDA", value: netDebtEbitda.toFixed(2) + "×", unit: "", accent: netDebtEbitda > 3 ? "#E24B4A" : "#EF9F27", sub: "Левередж" },
    { label: "CAGR Revenue", value: fmtPct(cagr), unit: "", accent: "#378ADD", sub: `${firstY}→${fy}` },
  ];
});

const pnlRows: Array<{ code: keyof FmYearOutputs; label: string; cls?: string }> = [
  { code: "revenue", label: "Revenue" },
  { code: "cogs",    label: "OPEX (без D&A)" },
  { code: "ebitda",  label: "EBITDA", cls: "fm-pnl-bold" },
  { code: "da",      label: "  D&A" },
  { code: "ebit",    label: "EBIT" },
  { code: "finCost", label: "  Фин. расходы" },
  { code: "ebt",     label: "EBT" },
  { code: "tax",     label: "  Налог" },
  { code: "netIncome", label: "Net Income", cls: "fm-pnl-bold" },
  { code: "ocf",     label: "OCF" },
  { code: "capex",   label: "  CAPEX" },
  { code: "fcf",     label: "FCF", cls: "fm-pnl-bold" },
  { code: "totalDebt", label: "Total Debt" },
  { code: "netDebt", label: "Net Debt" },
];

function onSaved(updated: FmScenarioModel) {
  persistedModel.value = {
    ...persistedModel.value,
    [scenario.value]: updated,
  };
  editorOpen.value = false;
}

// Reset model on demand (debug)
watch(scenario, () => {}, { immediate: false });
</script>

<style scoped>
/* ─── Container ─── */
.fm-scroll {
  background: #F4F3F9;
  min-height: 100%;
  padding: 0;
}

/* ─── Topbar — UzAssets navy gradient ─── */
.fm-top {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  padding: 16px 22px;
  background: linear-gradient(135deg, #1E2A4A 0%, #4B477E 100%);
  color: #fff;
}
.fm-top-l { min-width: 0; }
.fm-top-eyebrow {
  font-size: 10px;
  font-weight: 500;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: rgba(255, 255, 255, 0.65);
}
.fm-top-eyebrow .fm-v {
  display: inline-block;
  padding: 1px 6px;
  margin-left: 6px;
  border-radius: 4px;
  background: rgba(127, 119, 221, 0.5);
  color: #fff;
  font-weight: 700;
  letter-spacing: 0.05em;
}
.fm-top-t { margin: 4px 0 2px; font-size: 18px; font-weight: 500; letter-spacing: -0.01em; }
.fm-top-s { margin: 0; font-size: 11px; color: rgba(255, 255, 255, 0.6); }
.fm-top-r { display: flex; gap: 6px; align-items: center; }
.fm-scn {
  background: rgba(255, 255, 255, 0.1);
  border: 1px solid rgba(255, 255, 255, 0.18);
  color: rgba(255, 255, 255, 0.85);
  padding: 8px 14px;
  border-radius: 8px;
  font: inherit;
  font-size: 12px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.2s var(--ease-standard);
}
.fm-scn.active {
  background: var(--tone);
  border-color: var(--tone);
  color: #fff;
  box-shadow: 0 4px 12px color-mix(in srgb, var(--tone) 50%, transparent);
  transform: translateY(-1px);
}
.fm-edit-btn {
  margin-left: 8px;
  background: rgba(255, 255, 255, 0.12);
  border: 1px solid rgba(255, 255, 255, 0.25);
  color: #fff;
  padding: 8px 14px;
  border-radius: 8px;
  font: inherit;
  font-size: 12px;
  font-weight: 500;
  cursor: pointer;
  display: inline-flex; align-items: center; gap: 6px;
  transition: all 0.15s;
}
.fm-edit-btn:hover { background: rgba(255, 255, 255, 0.2); }

/* ─── Body ─── */
.fm-body { padding: 20px 22px; }

/* ─── KPI band ─── */
.fm-kpi-row {
  display: grid;
  grid-template-columns: repeat(7, 1fr);
  gap: 10px;
  margin-bottom: 16px;
}
@media (max-width: 1300px) { .fm-kpi-row { grid-template-columns: repeat(4, 1fr); } }
@media (max-width: 768px)  { .fm-kpi-row { grid-template-columns: repeat(2, 1fr); } }

.fm-card {
  background: var(--bg1, #fff);
  border-radius: 12px;
  border: 1px solid rgba(15, 23, 60, 0.05);
  padding: 16px 18px;
  position: relative;
  overflow: hidden;
  animation: fmCardIn 0.55s var(--ease-standard) var(--d, 0ms) both;
}
.fm-card::before {
  content: "";
  position: absolute; top: 0; left: 0; right: 0;
  height: 3px;
  background: var(--accent, #7F77DD);
  transform-origin: left center;
  animation: fmStripeIn 0.8s var(--ease-standard) var(--d, 0ms) both;
}
@keyframes fmCardIn {
  0%   { opacity: 0; transform: translateY(10px) scale(0.98); }
  60%  { opacity: 1; transform: translateY(-2px) scale(1); }
  100% { opacity: 1; transform: translateY(0) scale(1); }
}
@keyframes fmStripeIn {
  from { transform: scaleX(0); opacity: 0; }
  to   { transform: scaleX(1); opacity: 1; }
}

.fm-kpi-lbl {
  font-size: 9.5px;
  font-weight: 500;
  text-transform: uppercase;
  letter-spacing: 0.08em;
  color: rgba(15, 23, 60, 0.55);
}
.fm-kpi-val {
  font-size: 22px;
  font-weight: 400;
  margin-top: 6px;
  letter-spacing: -0.02em;
  font-variant-numeric: tabular-nums;
  animation: fmNumIn 0.45s ease 0.3s both;
}
.fm-kpi-val small { font-size: 11px; opacity: 0.7; margin-left: 4px; }
@keyframes fmNumIn { from { opacity: 0; transform: translateY(6px); } to { opacity: 1; transform: translateY(0); } }
.fm-kpi-sub {
  font-size: 10.5px;
  color: rgba(15, 23, 60, 0.5);
  margin-top: 4px;
}

/* ─── P&L table ─── */
.fm-card-ttl {
  display: flex;
  justify-content: space-between;
  margin-bottom: 12px;
  font-size: 11px;
  font-weight: 500;
  color: rgba(15, 23, 60, 0.65);
  text-transform: uppercase;
  letter-spacing: 0.06em;
}
.fm-card-meta { text-transform: none; letter-spacing: normal; font-size: 11px; color: rgba(15, 23, 60, 0.45); }

.fm-pnl-wrap { overflow-x: auto; }
.fm-pnl {
  width: 100%;
  border-collapse: collapse;
  font-size: 11.5px;
  font-variant-numeric: tabular-nums;
}
.fm-pnl thead th {
  position: sticky; top: 0;
  background: var(--bg2, #FAFAFD);
  padding: 8px 10px;
  text-align: right;
  font-size: 10px;
  font-weight: 600;
  letter-spacing: 0.06em;
  text-transform: uppercase;
  color: rgba(15, 23, 60, 0.6);
  border-bottom: 1px solid rgba(15, 23, 60, 0.08);
  white-space: nowrap;
}
.fm-pnl thead th:first-child { text-align: left; }
.fm-pnl thead th.forecast { background: #FFFBF4; color: #7A4A00; }
.fm-pnl-flag {
  display: inline-block;
  margin-left: 4px;
  padding: 0 4px;
  background: rgba(122, 74, 0, 0.15);
  border-radius: 3px;
  font-size: 8.5px;
}
.fm-pnl tbody td {
  padding: 6px 10px;
  text-align: right;
  color: var(--t1, #1E2A4A);
  border-bottom: 1px solid rgba(15, 23, 60, 0.03);
}
.fm-pnl tbody td.fm-pnl-name { text-align: left; color: rgba(15, 23, 60, 0.7); }
.fm-pnl tbody td.forecast { background: #FFFBF4; color: #7A4A00; }
.fm-pnl tbody td.neg { color: #C53030; }
.fm-pnl tbody tr.fm-pnl-bold td { font-weight: 600; color: var(--t1, #1E2A4A); background: rgba(127, 119, 221, 0.04); }

/* ─── Airports load section ─── */
.fm-airports {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.fm-ap-row {
  display: grid;
  grid-template-columns: 140px 1fr 60px;
  align-items: center;
  gap: 12px;
  padding: 6px 0;
  animation: fmCardIn 0.35s var(--ease-standard) var(--d) both;
}
.fm-ap-name { font-size: 12px; color: var(--t1, #1E2A4A); font-weight: 500; }
.fm-ap-bar {
  height: 10px;
  background: rgba(15, 23, 60, 0.05);
  border-radius: 6px;
  overflow: hidden;
}
.fm-ap-fill {
  height: 100%;
  border-radius: 6px;
  animation: fmBarFill 0.8s var(--ease-standard) both;
  transform-origin: left center;
}
@keyframes fmBarFill { from { width: 0 !important; } }
.fm-ap-pct { text-align: right; font-size: 12px; font-weight: 600; font-variant-numeric: tabular-nums; }
.fm-ap-pct.hi  { color: #0F6E56; }
.fm-ap-pct.mid { color: var(--sev-mid); }
.fm-ap-pct.lo  { color: #C53030; }

/* ─── Drivers grid ─── */
.fm-driv-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 12px;
  margin-top: 16px;
}
@media (max-width: 1100px) { .fm-driv-grid { grid-template-columns: 1fr; } }

/* ─── Assumptions ─── */
.fm-asm-grid {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 12px;
}
@media (max-width: 900px) { .fm-asm-grid { grid-template-columns: repeat(2, 1fr); } }
.fm-asm-item {
  padding: 10px 12px;
  background: var(--bg2, #FAFAFD);
  border-radius: 8px;
  border: 1px solid rgba(15, 23, 60, 0.04);
}
.fm-asm-lbl {
  font-size: 10px;
  text-transform: uppercase;
  letter-spacing: 0.07em;
  color: rgba(15, 23, 60, 0.55);
  font-weight: 500;
}
.fm-asm-val {
  font-size: 16px;
  font-weight: 500;
  color: var(--t1, #1E2A4A);
  margin-top: 3px;
  font-variant-numeric: tabular-nums;
}

/* ─── Card spacing ─── */
.fm-pnl-card, .fm-airports-card, .fm-asm-card { margin-top: 16px; }

/* ─── Footer ─── */
.fm-foot {
  margin-top: 20px;
  padding: 12px 4px;
  font-size: 10.5px;
  color: rgba(15, 23, 60, 0.45);
}
.fm-foot code {
  background: rgba(15, 23, 60, 0.06);
  padding: 1px 5px;
  border-radius: 3px;
  font-family: ui-monospace, "SF Mono", Menlo, monospace;
}
</style>
