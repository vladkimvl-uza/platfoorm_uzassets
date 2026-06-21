<script setup lang="ts">
/**
 * CapexQuarterlyModal — drill-down for the CAPEX quarterly bar block on
 * InvestProjects. Shows 4-up KPI band, big plan-vs-fact bars per quarter,
 * top-5 projects contribution. Pack 136.
 */
import { computed } from "vue";
import type { InvestProjectsCompanyData, ProjectRow } from "@/data/ngmk-invest-seed";

const props = defineProps<{
  data: InvestProjectsCompanyData;
}>();
const emit = defineEmits<{
  (e: "close"): void;
}>();

const capex = computed(() => props.data.capex);
const fiscalYear = computed(() => props.data.fiscal_year);

const ytdPct = computed(() =>
  capex.value.annual_plan_mln > 0
    ? (capex.value.annual_actual_ytd_mln / capex.value.annual_plan_mln) * 100
    : 0
);

// Forecast = sum of actual YTD + remaining plan (90-95% confidence)
// 2026-05-26: Number-coerce — `let sum = "string"` потом `sum += number`
// делает string-concat → ломает прогноз.
const forecastTotal = computed(() => {
  let sum = Number(capex.value.annual_actual_ytd_mln ?? 0);
  for (const q of capex.value.current_year_quarters) {
    if (q.actual_mln === null) sum += Number(q.plan_mln ?? 0) * 0.93;
  }
  return sum;
});
const forecastPct = computed(() =>
  capex.value.annual_plan_mln > 0
    ? (forecastTotal.value / capex.value.annual_plan_mln) * 100
    : 0
);

const maxBar = computed(() => {
  let max = 0;
  for (const q of capex.value.current_year_quarters) {
    if (q.plan_mln > max) max = q.plan_mln;
    if (q.actual_mln !== null && q.actual_mln > max) max = q.actual_mln;
  }
  return max || 1;
});

// Top-5 projects by funding_2026 contribution
const topProjects = computed(() =>
  [...props.data.projects]
    .sort((a, b) => b.funding_2026_mln - a.funding_2026_mln)
    .slice(0, 5)
    .map((p: ProjectRow) => ({
      ...p,
      pct: p.funding_2026_mln > 0 ? (p.disbursed_ytd_mln / p.funding_2026_mln) * 100 : 0,
    }))
);

function fmtM(n: number, d = 1): string {
  if (n == null) return "—";
  return n.toFixed(d).replace(".", ",");
}
function quarterTitle(q: string): string {
  return ({ Q1: "янв–мар", Q2: "апр–июн", Q3: "июл–сен", Q4: "окт–дек" } as Record<string, string>)[q] || "";
}
function pctColor(p: number): string {
  if (p >= 100) return "#1D9E75";
  if (p >= 75) return "#7F77DD";
  if (p >= 30) return "#EF9F27";
  return "#E24B4A";
}
function borderColor(p: number): string {
  return pctColor(p);
}

function onBackdrop(e: MouseEvent) {
  if (e.target === e.currentTarget) emit("close");
}
function onEsc(e: KeyboardEvent) {
  if (e.key === "Escape") emit("close");
}
window.addEventListener("keydown", onEsc);
import { onBeforeUnmount } from "vue";
onBeforeUnmount(() => window.removeEventListener("keydown", onEsc));
</script>

<template>
  <div class="cq-backdrop" @click="onBackdrop">
    <div class="cq-card" @click.stop>
      <!-- Header -->
      <div class="cq-hd">
        <div class="cq-hd-l">
          <div class="cq-hd-eyebrow">CAPEX исполнение · {{ fiscalYear }}</div>
          <div class="cq-hd-title">Квартальная разбивка · ПЛАН vs ФАКТ</div>
        </div>
        <div class="cq-hd-r">
          <button class="cq-close" @click="emit('close')" aria-label="close">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/>
            </svg>
          </button>
        </div>
      </div>

      <!-- KPI band -->
      <div class="cq-kpi">
        <div class="cq-kpi-c">
          <div class="cq-kpi-lbl">Утв. план года</div>
          <div class="cq-kpi-v">${{ fmtM(capex.annual_plan_mln) }}M</div>
        </div>
        <div class="cq-kpi-c">
          <div class="cq-kpi-lbl">Факт YTD</div>
          <div class="cq-kpi-v" style="color:#1D9E75">${{ fmtM(capex.annual_actual_ytd_mln) }}M</div>
          <div class="cq-kpi-sub">{{ fmtM(ytdPct, 1) }}% выполнения</div>
        </div>
        <div class="cq-kpi-c">
          <div class="cq-kpi-lbl">Прошлый год</div>
          <div class="cq-kpi-v">${{ fmtM(capex.prev_year_actual_mln) }}M</div>
          <div class="cq-kpi-sub" style="color:#1D9E75">{{ fmtM(capex.prev_year_exec_rate * 100, 1) }}% к плану</div>
        </div>
        <div class="cq-kpi-c">
          <div class="cq-kpi-lbl">Прогноз к концу года</div>
          <div class="cq-kpi-v" :style="{ color: forecastPct >= 95 ? '#1D9E75' : '#EF9F27' }">${{ fmtM(forecastTotal) }}M</div>
          <div class="cq-kpi-sub">{{ fmtM(forecastPct, 1) }}% к плану</div>
        </div>
      </div>

      <!-- Quarter bars -->
      <div class="cq-bars-section">
        <div class="cq-bars-hd">
          <span>Поквартальное исполнение</span>
          <span class="cq-legend">
            <span class="cq-legend-i"><span class="cq-sw" style="background:#1D9E75"></span>Факт</span>
            <span class="cq-legend-i"><span class="cq-sw" style="background:#7F77DD"></span>План</span>
            <span class="cq-legend-i"><span class="cq-sw" style="background:#7F77DD;opacity:.4"></span>Прогноз</span>
          </span>
        </div>
        <div class="cq-bars">
          <div v-for="q in capex.current_year_quarters" :key="q.q" class="cq-bar-cell">
            <div class="cq-bar-track">
              <!-- Fact (or forecast) bar -->
              <div
                class="cq-bar cq-bar-fact"
                :class="{ 'cq-bar-forecast': q.actual_mln === null }"
                :style="{ height: ((q.actual_mln ?? q.plan_mln * 0.93) / maxBar * 100) + '%' }"
              >
                <span class="cq-bar-val" :style="{ color: q.actual_mln !== null ? '#1D9E75' : '#534AB7' }">
                  {{ fmtM(q.actual_mln !== null ? q.actual_mln : q.plan_mln * 0.93, 1) }}
                </span>
              </div>
              <!-- Plan bar -->
              <div class="cq-bar cq-bar-plan" :style="{ height: (q.plan_mln / maxBar * 100) + '%' }">
                <span class="cq-bar-val" style="color:#534AB7">{{ fmtM(q.plan_mln, 1) }}</span>
              </div>
            </div>
            <div class="cq-bar-footer">
              <span class="cq-bar-q">{{ q.q }}</span>
              <span
                class="cq-bar-pct"
                :style="{ color: q.actual_mln !== null ? '#1D9E75' : '#EF9F27' }"
              >
                {{ q.actual_mln !== null
                  ? fmtM((q.actual_mln / q.plan_mln) * 100, 1) + '%'
                  : 'прогноз ' + fmtM(93, 0) + '%' }}
              </span>
            </div>
            <div class="cq-bar-note">
              {{ quarterTitle(q.q) }} · {{ q.actual_mln !== null ? 'закрыт' : 'в плане' }}
            </div>
          </div>
        </div>
      </div>

      <!-- Top-5 projects -->
      <div class="cq-top">
        <div class="cq-top-hd">
          <span>Топ-5 проектов · вклад в CAPEX {{ fiscalYear }}</span>
        </div>
        <div class="cq-top-rows">
          <div
            v-for="p in topProjects"
            :key="p.num"
            class="cq-top-row"
            :style="{ '--stripe-color': borderColor(p.pct) }"
          >
            <div class="cq-top-name">
              <div class="cq-top-title">{{ p.name }}</div>
              <div class="cq-top-meta">{{ p.capacity.substring(0, 50) }}{{ p.capacity.length > 50 ? '…' : '' }}</div>
            </div>
            <div class="cq-top-stat">
              <div class="cq-top-stat-l">ПЛАН</div>
              <div class="cq-top-stat-v">${{ fmtM(p.funding_2026_mln, 1) }}M</div>
            </div>
            <div class="cq-top-stat">
              <div class="cq-top-stat-l">ФАКТ</div>
              <div class="cq-top-stat-v" style="color:#1D9E75">${{ fmtM(p.disbursed_ytd_mln, 1) }}M</div>
            </div>
            <div class="cq-top-stat">
              <div class="cq-top-stat-l">%</div>
              <div class="cq-top-stat-v" :style="{ color: pctColor(p.pct) }">{{ fmtM(p.pct, 1) }}%</div>
            </div>
          </div>
        </div>
      </div>

      <!-- Footer -->
      <div class="cq-foot">
        <div>FTE заказчика ГУ: {{ capex.fte_deployed }} / {{ capex.fte_approved }}</div>
        <div class="cq-foot-r">
          <span class="cq-foot-link">↓ EXCEL</span>
          <span class="cq-foot-link">↓ PDF</span>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.cq-backdrop {
  position: fixed; inset: 0; z-index: 1000;
  background: rgba(15,18,40,.45);
  -webkit-backdrop-filter: blur(8px);
  backdrop-filter: blur(8px);
  display: flex; align-items: center; justify-content: center;
  padding: 36px;
  animation: cqBdIn .25s ease-out;
}
@keyframes cqBdIn { from { opacity: 0; } to { opacity: 1; } }

.cq-card {
  width: 100%; max-width: 920px;
  max-height: calc(100dvh - 72px);
  overflow-y: auto;
  background: white;
  border-radius: 14px;
  box-shadow: 0 24px 64px rgba(15,23,60,.18), 0 8px 24px rgba(15,23,60,.08);
  font-family: -apple-system, system-ui, 'Segoe UI', sans-serif;
  color: var(--t1, #1E2A4A);
  animation: cqCardIn .45s var(--ease-standard);
}
@keyframes cqCardIn {
  from { opacity: 0; transform: translateY(20px) scale(.97); }
  to   { opacity: 1; transform: translateY(0) scale(1); }
}

.cq-hd {
  padding: 16px 22px 14px;
  border-bottom: 0.5px solid var(--border-hard);
  display: flex; align-items: center; justify-content: space-between; gap: 12px;
}
.cq-hd-eyebrow { font-size: 10px; font-weight: 500; color: var(--t3, var(--t-muted)); letter-spacing: .06em; text-transform: uppercase; margin-bottom: 3px; }
.cq-hd-title   { font-size: 15px; font-weight: 500; letter-spacing: -.01em; }
.cq-close {
  width: 28px; height: 28px; background: transparent; border: none; cursor: pointer;
  display: flex; align-items: center; justify-content: center;
  color: var(--t3, var(--t-muted)); border-radius: 6px;
}
.cq-close:hover { background: #F3F4F8; color: var(--t1, #1E2A4A); }

.cq-kpi {
  display: grid; grid-template-columns: repeat(4, 1fr);
  gap: 1px; background: var(--border-hard);
  border-bottom: 0.5px solid var(--border-hard);
}
.cq-kpi-c { background: white; padding: 14px 18px; }
.cq-kpi-lbl { font-size: 10px; color: var(--t3, var(--t-muted)); font-weight: 500; letter-spacing: .06em; text-transform: uppercase; margin-bottom: 6px; }
.cq-kpi-v   { font-size: 22px; font-weight: 400; color: var(--t1, #1E2A4A); letter-spacing: -.025em; }
.cq-kpi-sub { font-size: 10px; color: var(--t3, var(--t-muted)); margin-top: 2px; }

.cq-bars-section { padding: 22px 22px 18px; }
.cq-bars-hd {
  font-size: 11px; font-weight: 500; margin-bottom: 14px;
  display: flex; align-items: center; gap: 14px; flex-wrap: wrap;
}
.cq-legend { display: inline-flex; gap: 14px; }
.cq-legend-i { display: inline-flex; align-items: center; gap: 4px; font-size: 10px; color: var(--t3, var(--t-muted)); font-weight: 400; }
.cq-sw { width: 9px; height: 9px; border-radius: 2px; }

.cq-bars { display: grid; grid-template-columns: repeat(4, 1fr); gap: 18px; }
.cq-bar-cell {}
.cq-bar-track {
  height: 200px;
  display: flex; align-items: flex-end; gap: 6px;
  border-bottom: 0.5px solid var(--border-hard);
  padding-bottom: 2px;
}
.cq-bar {
  flex: 1; border-radius: 4px 4px 0 0; position: relative;
  min-height: 4px;
  animation: cqBarUp .6s var(--ease-standard);
  transform-origin: left center;
}
@keyframes cqBarUp { from { height: 0 !important; } }
.cq-bar-fact { background: linear-gradient(180deg, var(--green) 0%, #178760 100%); }
.cq-bar-fact.cq-bar-forecast {
  background: #7F77DD; opacity: .42;
  border: 1px dashed #7F77DD;
}
.cq-bar-plan { background: #7F77DD; }
.cq-bar-val {
  position: absolute; top: -16px; left: 50%; transform: translateX(-50%);
  font-size: 9px; font-weight: 500; white-space: nowrap;
}
.cq-bar-footer { display: flex; justify-content: space-between; align-items: baseline; margin-top: 8px; }
.cq-bar-q   { font-size: 13px; font-weight: 500; }
.cq-bar-pct { font-size: 10px; font-weight: 500; }
.cq-bar-note { font-size: 10px; color: var(--t3, var(--t-muted)); margin-top: 2px; }

.cq-top { padding: 0 22px 16px; }
.cq-top-hd {
  font-size: 11px; font-weight: 500; margin-bottom: 10px;
  display: flex; justify-content: space-between; align-items: center;
}
.cq-top-rows { display: flex; flex-direction: column; gap: 6px; }
.cq-top-row {
  display: grid; grid-template-columns: 1fr auto auto auto;
  gap: 16px; padding: 9px 12px 9px 18px;
  background: var(--bg2, #F9FAFB); border-radius: 6px;
  align-items: center;
  position: relative; overflow: hidden;
}
.cq-top-row::before {
  content: ""; position: absolute;
  left: 6px; top: 6px; bottom: 6px;
  width: 4px; border-radius: 4px;
  background: var(--stripe-color, #7F77DD);
  pointer-events: none;
}
.cq-top-title { font-size: 12px; font-weight: 500; }
.cq-top-meta  { font-size: 10px; color: var(--t3, var(--t-muted)); }
.cq-top-stat { text-align: right; }
.cq-top-stat-l { font-size: 10px; color: var(--t3, var(--t-muted)); letter-spacing: .05em; }
.cq-top-stat-v { font-size: 12px; font-weight: 500; color: var(--t1, #1E2A4A); }

.cq-foot {
  padding: 12px 22px; background: var(--bg2, #F9FAFB); border-top: 0.5px solid var(--border-hard);
  display: flex; justify-content: space-between; align-items: center;
  font-size: 10px; color: var(--t3, var(--t-muted)); letter-spacing: .05em;
}
.cq-foot-r { display: flex; gap: 14px; }
.cq-foot-link { cursor: pointer; color: var(--p-deep); }
.cq-foot-link:hover { color: var(--t1, #1E2A4A); }

@media (max-width: 880px) {
  .cq-kpi  { grid-template-columns: repeat(2, 1fr); }
  .cq-bars { grid-template-columns: repeat(2, 1fr); }
  .cq-top-row { grid-template-columns: 1fr; gap: 6px; text-align: left; }
  .cq-top-stat { text-align: left; }
}
</style>
