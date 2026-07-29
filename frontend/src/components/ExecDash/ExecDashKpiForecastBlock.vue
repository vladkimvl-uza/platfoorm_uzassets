<script setup lang="ts">
/**
 * ExecDashKpiForecastBlock — Row 2.9.
 * Прогноз KPI: детерминированный движок core/forecast проецирует сводное
 * выполнение каждой компании на ближайший будущий год (OLS-тренд по годовому
 * ряду). Показывает ожидаемое выполнение портфеля, зону риска, улучшающихся/
 * ухудшающихся и топ-компании. Данные из exec.data.value.kpi_forecast.
 */
import { computed } from "vue";
import { useRouter } from "vue-router";
import { useI18n } from "@/composables/useI18n";
import { useExecutiveDashboard } from "@/composables/useExecutiveDashboard";
import { useNumberTween } from "@/composables/useNumberTween";
import type { ExecKpiForecastCompany } from "@/api/executiveDashboard";

const { t } = useI18n();
const exec = useExecutiveDashboard();
const router = useRouter();

const block = computed(() => exec.data.value?.kpi_forecast || null);
const companies = computed(() => block.value?.companies || []);
const chartRows = computed(() => companies.value.slice(0, 8));
const chartMax = computed(() =>
  Math.max(100, ...chartRows.value.map(c => c.high ?? c.forecast ?? 0)));

const tAvg = useNumberTween(() => Number(block.value?.avg_forecast) || 0, { duration: 900 });

function barColor(pct: number | null | undefined): string {
  if (pct == null) return "#9AA0AE";
  if (pct >= 100) return "#1D9E75";
  if (pct >= 75) return "#D97706";
  return "#E24B4A";
}
function fmtPct(v: number | null | undefined): string {
  return v == null ? "—" : `${Math.round(v)}%`;
}
function fmtDelta(v: number | null | undefined): string {
  if (v == null || isNaN(v)) return "";
  return `${v > 0 ? "+" : ""}${v.toFixed(1)}`;
}
function deltaColor(v: number | null | undefined): string {
  if (v == null || v === 0) return "#9AA0AE";
  return v > 0 ? "#1D9E75" : "#E24B4A";  // выше прогноз = лучше
}
function deltaArrow(v: number | null | undefined): string {
  if (v == null || v === 0) return "→";
  return v > 0 ? "▲" : "▼";
}
// Русские лейблы — ключи словаря; t() применяется в точке отображения.
const CONF_LABEL: Record<string, string> = {
  high: "высокая", medium: "средняя", low: "низкая", none: "нет данных",
};
function confLabel(c: string): string { return t(CONF_LABEL[c] || c); }

function openKpi() { router.push({ path: "/kpi" }); }
function onRowKey(e: KeyboardEvent) {
  if (e.key === "Enter" || e.key === " ") { e.preventDefault(); openKpi(); }
}
</script>

<template>
  <section class="ed-card efk-card">
    <header class="efk-hdr">
      <div class="efk-hdr-l">
        <div class="efk-eyebrow">{{ t("Прогноз KPI") }}</div>
        <div class="efk-sub">
          {{ t("FY {y} · детерминированный тренд · ожидаемое выполнение FY {fy}", { y: block?.year || exec.year.value, fy: block?.forecast_year ?? "" }) }}
        </div>
      </div>
      <div v-if="block && block.has_data" class="efk-hdr-r">
        <span class="efk-stat">{{ t("{a} / {b} с прогнозом", { a: block.scored_count, b: block.total_companies }) }}</span>
        <button class="efk-open" type="button" @click="openKpi" :title="t('Открыть модуль KPI')">
          {{ t("Подробнее") }}
          <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M5 12h14"/><path d="M13 6l6 6-6 6"/></svg>
        </button>
      </div>
    </header>

    <!-- Empty -->
    <div v-if="!block || !block.has_data" class="efk-empty">
      <svg width="36" height="36" viewBox="0 0 24 24" fill="none" stroke="currentColor"
           stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
        <path d="M3 3v18h18"/><path d="M7 14l4-4 3 3 5-6"/>
      </svg>
      <div class="efk-empty-title">{{ t("Прогноз KPI недоступен за FY {y}", { y: exec.year.value }) }}</div>
      <div class="efk-empty-text">
        {{ t("Нужно ≥2 лет истории KPI по компаниям —") }}<br>{{ t("тренд рассчитается автоматически.") }}
      </div>
    </div>

    <template v-else>
      <!-- KPI band -->
      <div class="efk-kpi-band kpi-rail">
        <div class="efk-kpi" :style="{ '--accent': barColor(block.avg_forecast), '--d': '0ms' }">
          <div class="efk-kpi-lbl">{{ t("Ожид. выполнение FY {y}", { y: block.forecast_year }) }}</div>
          <div class="efk-kpi-val">{{ tAvg.toFixed(0) }}<span class="efk-kpi-u">%</span></div>
          <div class="efk-kpi-zone efk-muted">
            {{ t("тек. {v} по портфелю", { v: fmtPct(block.avg_current) }) }}
          </div>
        </div>

        <div class="efk-kpi" style="--accent: #E24B4A; --d: 80ms;">
          <div class="efk-kpi-lbl">{{ t("В зоне риска") }}</div>
          <div class="efk-kpi-val">{{ block.at_risk }}<span class="efk-kpi-u">{{ t("компаний") }}</span></div>
          <div class="efk-kpi-zone efk-muted">{{ t("прогноз ниже 75%") }}</div>
        </div>

        <div class="efk-kpi" style="--accent: #1D9E75; --d: 160ms;">
          <div class="efk-kpi-lbl">{{ t("Динамика тренда") }}</div>
          <div class="efk-kpi-val">
            <span style="color:#1D9E75">{{ block.improving }}</span>
            <span class="efk-kpi-slash">/</span>
            <span style="color:#E24B4A">{{ block.declining }}</span>
          </div>
          <div class="efk-kpi-zone efk-muted">{{ t("улучшаются / ухудшаются") }}</div>
        </div>

        <div class="efk-kpi" style="--accent: #7F77DD; --d: 240ms;">
          <div class="efk-kpi-lbl">{{ t("Покрытие прогнозом") }}</div>
          <div class="efk-kpi-val">{{ block.scored_count }}<span class="efk-kpi-u">/ {{ block.total_companies }}</span></div>
          <div class="efk-kpi-zone efk-muted">{{ t("{n} без истории", { n: block.total_companies - block.scored_count }) }}</div>
        </div>
      </div>

      <!-- График прогноза по компаниям (топ-8) -->
      <div v-if="chartRows.length" class="efk-chart">
        <div class="efk-chart-hdr">{{ t("Прогноз выполнения FY {y} · топ-{n}", { y: block.forecast_year, n: chartRows.length }) }}</div>
        <div v-for="(c, i) in chartRows" :key="c.company_id" class="efk-bar-row"
             :style="{ '--d': (i * 55) + 'ms' }" role="button" tabindex="0"
             :title="t('Открыть KPI: {name}', { name: c.name })" @click="openKpi" @keydown="onRowKey">
          <span class="efk-bar-lbl" :title="c.name">
            <i class="efk-dot" :style="{ background: c.sector_color || '#7F77DD' }" />{{ c.name }}
          </span>
          <div class="efk-bar-track">
            <div class="efk-bar-fill" :style="{ width: Math.min((c.forecast ?? 0) / chartMax * 100, 100) + '%', background: barColor(c.forecast) }"></div>
          </div>
          <span v-if="c.delta != null" class="efk-bar-delta" :style="{ color: deltaColor(c.delta) }">
            {{ deltaArrow(c.delta) }}{{ fmtDelta(c.delta) }}
          </span>
          <span class="efk-bar-val">{{ fmtPct(c.forecast) }}</span>
        </div>
      </div>

      <!-- Риски / Лидеры -->
      <div class="efk-cols">
        <div class="efk-col">
          <div class="efk-col-t" style="color:#E24B4A">↓ {{ t("Риски недостижения") }}</div>
          <div v-for="(c, i) in (block.risks || [])" :key="c.company_id" class="efk-row"
               :style="{ '--d': (i * 60) + 'ms' }" role="button" tabindex="0"
               :title="t('Открыть KPI: {name}', { name: c.name })" @click="openKpi" @keydown="onRowKey">
            <span class="efk-dot" :style="{ background: c.sector_color || '#E24B4A' }" />
            <span class="efk-name" :title="c.name">{{ c.name }}</span>
            <span class="efk-conf" :title="t('надёжность прогноза')">{{ confLabel(c.confidence) }}</span>
            <span class="efk-score" :style="{ color: barColor(c.forecast), background: barColor(c.forecast) + '18' }">
              {{ fmtPct(c.forecast) }}
            </span>
          </div>
          <div v-if="!(block.risks || []).length" class="efk-none">{{ t("нет компаний в зоне риска") }}</div>
        </div>
        <div class="efk-col">
          <div class="efk-col-t" style="color:#1D9E75">↑ {{ t("Лидеры прогноза") }}</div>
          <div v-for="(c, i) in (block.leaders || [])" :key="c.company_id" class="efk-row"
               :style="{ '--d': (i * 60) + 'ms' }" role="button" tabindex="0"
               :title="t('Открыть KPI: {name}', { name: c.name })" @click="openKpi" @keydown="onRowKey">
            <span class="efk-dot" :style="{ background: c.sector_color || '#1D9E75' }" />
            <span class="efk-name" :title="c.name">{{ c.name }}</span>
            <span v-if="c.delta != null" class="efk-delta" :style="{ color: deltaColor(c.delta) }">
              {{ deltaArrow(c.delta) }} {{ fmtDelta(c.delta) }}
            </span>
            <span class="efk-score" :style="{ color: barColor(c.forecast), background: barColor(c.forecast) + '18' }">
              {{ fmtPct(c.forecast) }}
            </span>
          </div>
          <div v-if="!(block.leaders || []).length" class="efk-none">—</div>
        </div>
      </div>
      <div class="efk-foot">{{ t("Числа — детерминированный движок (OLS-тренд по годовому ряду выполнения); коридор надёжности учтён. Разбор и прогноз по показателям — в модуле KPI, режим «Прогноз».") }}</div>
    </template>
  </section>
</template>

<style scoped>
.efk-card {
  padding: 14px; background: var(--bg1, #fff); border-radius: 12px;
  border: 1px solid rgba(0, 0, 0, 0.05); box-shadow: 0 4px 14px rgba(15, 23, 60, 0.06); margin-top: 14px;
}
.efk-hdr { display: flex; align-items: flex-end; justify-content: space-between; gap: 12px;
  padding-bottom: 12px; border-bottom: 0.5px solid rgba(0, 0, 0, 0.08); flex-wrap: wrap; }
.efk-eyebrow { font-size: 11px; font-weight: 600; color: var(--t3, var(--t-muted));
  text-transform: uppercase; letter-spacing: 0.07em; margin-bottom: 3px; }
.efk-sub { font-size: 11px; color: var(--t3, var(--t-muted)); letter-spacing: 0.04em; }
.efk-hdr-r { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }
.efk-stat { font-size: 11px; color: var(--t3, var(--t-muted)); font-weight: 500;
  background: rgba(127, 119, 221, 0.07); padding: 4px 10px; border-radius: 8px; }
.efk-open { display: inline-flex; align-items: center; gap: 5px; font-size: 11.5px; font-weight: 600;
  font-family: inherit; color: var(--p-deep, #534AB7); background: rgba(124, 111, 247, 0.08);
  border: 1px solid rgba(124, 111, 247, 0.28); border-radius: 9px; padding: 6px 12px; cursor: pointer;
  transition: all 0.15s ease; }
.efk-open:hover { background: rgba(124, 111, 247, 0.16); transform: translateY(-1px); }
.efk-open svg { transition: transform 0.15s ease; }
.efk-open:hover svg { transform: translateX(2px); }

.efk-empty { padding: 46px 20px; text-align: center; color: #6B6A66;
  display: flex; flex-direction: column; align-items: center; gap: 10px; }
.efk-empty-title { font-size: 14px; font-weight: 700; color: var(--t3, var(--t-muted)); margin-top: 6px; }
.efk-empty-text { font-size: 12px; line-height: 1.5; color: #6B6A66; }

.efk-kpi-band { display: grid; grid-template-columns: repeat(4, 1fr); gap: 10px; margin: 14px 0; }
.efk-kpi { background: rgba(255, 255, 255, 0.82); backdrop-filter: blur(16px) saturate(1.5);
  -webkit-backdrop-filter: blur(16px) saturate(1.5); border-radius: 14px; padding: 14px 16px 12px;
  border: 1px solid rgba(255, 255, 255, 0.70);
  box-shadow: 0 2px 12px rgba(15, 23, 60, 0.07), 0 1px 3px rgba(15, 23, 60, 0.04);
  position: relative; overflow: hidden; display: flex; flex-direction: column;
  justify-content: space-between; min-height: 92px;
  animation: finKpiCardIn .55s var(--ease-standard) var(--d, 0ms) both; }
.efk-kpi::before { content: ''; position: absolute; top: 0; left: 0; right: 0; height: 3px;
  background: var(--accent, var(--border-input)); border-radius: 14px 14px 0 0;
  animation: finKpi2DrawIn .8s var(--ease-standard) var(--d, 0ms) both; transform-origin: left center; }
.efk-kpi-lbl { font-size: 11px; font-weight: 500; color: var(--t3, var(--t-muted));
  text-transform: uppercase; letter-spacing: 0.06em; margin-bottom: 6px; }
.efk-kpi-val { font-size: 26px; font-weight: 400; letter-spacing: -0.035em; line-height: 1;
  color: var(--t1, #1E2A4A); font-variant-numeric: tabular-nums; display: flex; align-items: baseline;
  gap: 5px; margin: 2px 0 4px; }
.efk-kpi-u { font-size: 11px; color: var(--t3, var(--t-muted)); font-weight: 500; letter-spacing: 0; }
.efk-kpi-slash { color: var(--t3, var(--t-muted)); font-weight: 300; }
.efk-kpi-zone { font-size: 10.5px; font-weight: 600; margin-top: 4px; }
.efk-kpi-zone.efk-muted { color: var(--t3, var(--t-muted)); font-weight: 500; }

.efk-chart { margin: 4px 0 14px; }
.efk-chart-hdr { font-size: 11px; font-weight: 700; color: var(--t3, var(--t-muted));
  text-transform: uppercase; letter-spacing: 0.06em; margin-bottom: 10px; }
.efk-bar-row { display: grid; grid-template-columns: 190px 1fr auto 44px; align-items: center; gap: 9px;
  margin: 5px 0; padding: 3px 6px; margin-left: -6px; border-radius: 8px; cursor: pointer;
  font-size: 12.5px; transition: background .15s ease;
  animation: ehlRowIn .4s var(--ease-standard, ease) var(--d, 0ms) both; }
.efk-bar-row:hover { background: rgba(127, 119, 221, .07); }
.efk-bar-row:focus-visible { outline: 2px solid rgba(124, 111, 247, .5); outline-offset: 1px; }
.efk-bar-lbl { display: flex; align-items: center; gap: 7px; color: var(--t1, #1E2A4A);
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis; min-width: 0; }
.efk-bar-track { height: 12px; background: #ECECF3; border-radius: 6px; overflow: hidden; }
.efk-bar-fill { height: 100%; border-radius: 6px; transition: width .6s var(--ease-standard, ease); }
.efk-bar-delta { font-size: 10.5px; font-weight: 700; font-variant-numeric: tabular-nums; text-align: right; }
.efk-bar-val { text-align: right; font-variant-numeric: tabular-nums; font-weight: 600; color: var(--t1, #1E2A4A); }

.efk-cols { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }
.efk-col { background: var(--bg2, #FAFAFD); border-radius: 11px; padding: 11px 13px; }
.efk-col-t { font-size: 10px; font-weight: 700; text-transform: uppercase; letter-spacing: .05em; margin-bottom: 8px; }
.efk-row { display: flex; align-items: center; gap: 8px; padding: 6px 8px; margin: 0 -8px; border-radius: 8px;
  cursor: pointer; transition: background .15s ease, transform .15s ease;
  animation: ehlRowIn .4s var(--ease-standard, ease) var(--d, 0ms) both; }
.efk-row:hover { background: rgba(127, 119, 221, .08); transform: translateX(2px); }
.efk-row:focus-visible { outline: 2px solid rgba(124, 111, 247, .5); outline-offset: 1px; }
.efk-dot { width: 8px; height: 8px; border-radius: 50%; flex-shrink: 0; display: inline-block; }
.efk-name { font-size: 12.5px; font-weight: 500; color: var(--t1, #1E2A4A);
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis; flex: 1; min-width: 0; }
.efk-conf { font-size: 10px; color: var(--t3, var(--t-muted)); font-weight: 500; flex-shrink: 0; }
.efk-delta { font-size: 10.5px; font-weight: 700; font-variant-numeric: tabular-nums; flex-shrink: 0; }
.efk-score { font-size: 12px; font-weight: 700; border-radius: 7px; padding: 2px 8px;
  font-variant-numeric: tabular-nums; flex-shrink: 0; }
.efk-none { font-size: 11px; color: #C4C8D4; font-style: italic; padding: 4px 0; }
.efk-foot { margin-top: 12px; font-size: 10.5px; line-height: 1.5; color: var(--t3, var(--t-muted)); }

@media (max-width: 1100px) {
  .efk-kpi-band { grid-template-columns: 1fr 1fr; }
  .efk-cols { grid-template-columns: 1fr; }
  .efk-bar-row { grid-template-columns: 120px 1fr auto 40px; }
}
</style>
