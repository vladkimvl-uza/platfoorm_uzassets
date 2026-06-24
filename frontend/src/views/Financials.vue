<script setup lang="ts">
// ============================================================================
// Financials dashboard — portfolio-wide view + drill-down modal.
//
// Layout:
//   1. Inline toolbar
//   2. KPI band (full width)
//   3. Two-column body, aligned heights:
//        Left:  donut + metric tabs + sector table
//        Right: scoreboard
//   4. CompanyDrilldown modal opens when user clicks scoreboard row.
// ============================================================================

import { computed, onMounted, onBeforeUnmount, ref, watch } from "vue";
import { useSavedFilter } from "@/composables/useSavedFilter";
import { useAiPageContext } from "@/composables/useAiPageContext";
import { usePermissions } from "@/composables/usePermissions";

import { financialsApi, type PortfolioSummaryResponse } from "@/api/financials";
import { companiesApi, type CompanyListItem, type SectorBrief } from "@/api/companies";
import { subsidiesApi, type SubsidySummary } from "@/api/subsidies";
import { useCurrencyConverter } from "@/composables/useCurrencyConverter";

import FinTopFilters    from "@/components/Financials/FinTopFilters.vue";
import FinKpiBand       from "@/components/Financials/FinKpiBand.vue";
import FinMetricTabs    from "@/components/Financials/FinMetricTabs.vue";
import FinSectorTable   from "@/components/Financials/FinSectorTable.vue";
import FinScoreboard    from "@/components/Financials/FinScoreboard.vue";
import CompanyDrilldown from "@/components/Financials/CompanyDrilldown.vue";
import FinKpiDrillModal from "@/components/Financials/FinKpiDrillModal.vue";
import FinSubsidiesModal from "@/components/Financials/FinSubsidiesModal.vue";
import IfrsReportHistory from "@/components/Financials/IfrsReportHistory.vue";
import HighLevelFinancials from "@/components/Financials/HighLevelFinancials.vue";
import FinCopilot from "@/components/Financials/FinCopilot.vue";
import FinForecastModal from "@/components/Financials/FinForecastModal.vue";
import { useAiActivation } from "@/composables/useAiActivation";

import {
  computePortfolioKpis, filterBySector,
  metricsFor, aggregateBySector, buildCompanyIndex,
  ensureFinancialsCss,
} from "@/components/Financials/financialsHelpers";

const conv = useCurrencyConverter();

const standard   = useSavedFilter<"IFRS" | "NSBU">("financials.standard", "IFRS");
// Pack 7.37: currency теперь синхронизирована с глобальным useCurrencyConverter.
// Бэкенд всегда получает UZS — конвертация в USD/EUR делается на клиенте по
// среднегодовым курсам ЦБ РУ из таблицы year_registry. Это позволяет
// переключать валюту мгновенно без перезагрузки данных и держать единый
// источник истины (курсы редактируются в /admin/system-config).
const currency = computed<"UZS" | "USD" | "EUR">({
  get: () => conv.currency.value,
  set: (v) => conv.setCurrency(v),
});
const unit       = useSavedFilter<"bln" | "mln">("financials.unit", "bln");
const sectorCode = useSavedFilter<string>("financials.sectorCode", "");
const year       = useSavedFilter<number>("financials.year", 2024);
const viewTab    = useSavedFilter<string>("financials.viewTab", "PL");
const activeMetric = useSavedFilter<string>("financials.activeMetric", "revenue");

// Финансовый ИИ-копилот: доступ (скрыт для тех, у кого нет) + контекст экрана
const aiAccess = useAiActivation();
aiAccess.load();
const forecastOpen = ref(false);
const copilotContext = computed(() =>
  `FY ${year.value} · ${standard.value} · ${currency.value} · ${unit.value} · ${viewTab.value} · метрика ${activeMetric.value}` +
  (sectorCode.value ? ` · сектор ${sectorCode.value}` : ""),
);

// Pack 7.9e: AI Bubble context
useAiPageContext({
  key: "financials",
  label: "Финансовая отчётность",
  describeState: () => `${standard.value} · ${year.value} · ${currency.value} · ${unit.value} · ${viewTab.value}`,
  quickActions: [
    { label: "Сводка по портфелю",
      prompt: "Дай сводку финансовых результатов портфеля за выбранный год: revenue, EBITDA, net profit топ-5 компаний. Используй get_financials." },
    { label: "EBITDA-margin тренд",
      prompt: "Проанализируй EBITDA-margin по портфелю: лидеры и отстающие, сравнение с отраслевыми бенчмарками (mining 25-45%, energy 15-25%, transport 10-20%, telecom 30-45%)." },
    { label: "Сравни 2025 vs 2026",
      prompt: "Сравни ключевые финметрики 2025 vs 2026 по портфелю (revenue, EBITDA, net profit). Что выросло, что упало? Учитывай макро (gold +15%, oil -5%)." },
    { label: "Ковенант-чек",
      prompt: "Проверь кредитные ковенанты: Debt/EBITDA, ICR, current ratio по каждой компании. Где близко к breach? Используй get_financials + get_credit_portfolio." },
  ],
});

// Pack 7.58: topbar action menu
const menuOpen = ref(false);

const summary   = ref<PortfolioSummaryResponse | null>(null);
const companies = ref<CompanyListItem[]>([]);
const sectors   = ref<SectorBrief[]>([]);
const loading   = ref(true);
const errorMsg  = ref<string | null>(null);

// ── Drill-down modal state ────────────────────────────────────────────────
const drillCompanyCode = ref<string | null>(null);

// ── Pack 7.48: KPI drill state ────────────────────────────────────────────
type KpiDrillId = "revenue" | "opMargin" | "ebitda" | "netMargin" | "loss" | "standards";
const kpiDrill = ref<KpiDrillId | null>(null);
function openKpiDrill(kpi: KpiDrillId) { kpiDrill.value = kpi; }

// ── Субсидии: метрика-карточка + реестр-модалка ───────────────────────────
const finPerm = usePermissions("financials");
const subsidiesOpen = ref(false);
const subsidiesSummary = ref<SubsidySummary | null>(null);
const subsidiesTotal = computed<number | null>(() => subsidiesSummary.value?.total ?? null);
async function loadSubsidies() {
  try {
    subsidiesSummary.value = await subsidiesApi.summary({
      year: year.value,
      sector_code: sectorCode.value || undefined,
    });
  } catch {
    subsidiesSummary.value = null;
  }
}
function closeKpiDrill() { kpiDrill.value = null; }

const yearScope = (() => {
  const now = new Date().getFullYear();
  const out: number[] = [];
  for (let y = 2021; y <= now + 1; y++) out.push(y);
  return out;
})();

const companyIdx = computed(() => buildCompanyIndex(companies.value));
const metricList = computed(() => metricsFor(standard.value, viewTab.value));

watch([standard, viewTab], () => {
  if (!metricList.value.some(m => m.id === activeMetric.value)) {
    activeMetric.value = metricList.value[0]?.id || "revenue";
  }
});

watch(standard, () => { viewTab.value = "PL"; });

async function loadAll() {
  loading.value = true;
  errorMsg.value = null;
  try {
    const [companiesResp, sumResp] = await Promise.all([
      companiesApi.list({ limit: 200 }),
      // Pack 7.37: всегда запрашиваем UZS, конвертацию делаем на клиенте
      financialsApi.portfolioSummary({
        standard: standard.value,
        years: yearScope,
        currency: "UZS",
      }),
    ]);
    companies.value = companiesResp.items || [];
    sectors.value   = companiesResp.sectors || [];
    summary.value   = sumResp;
  } catch (e: any) {
    errorMsg.value =
      e?.response?.data?.detail || e?.message || "Не удалось загрузить данные";
    console.error("Financials portfolio-summary load failed:", e);
  } finally {
    loading.value = false;
  }
}

// Pack 7.37: при смене валюты НЕ перезагружаем — клиент конвертирует summary.
// Перезагружаем только при смене стандарта (IFRS↔NSBU).
watch(standard, () => { loadAll(); });

// Субсидии перезагружаем при смене года/сектора (метрика-карточка реактивна)
watch([year, sectorCode], () => { loadSubsidies(); });

onMounted(() => {
  ensureFinancialsCss();
  loadAll();
  loadSubsidies();
  // Floating "Высокоуровневые показатели" CTA — observe target visibility
  observeHlfTarget();
});
onBeforeUnmount(() => {
  if (_hlfObserver) { _hlfObserver.disconnect(); _hlfObserver = null; }
  if (_hlfScrollListener) {
    window.removeEventListener("scroll", _hlfScrollListener);
    window.removeEventListener("resize", _hlfScrollListener);
    document.removeEventListener("scroll", _hlfScrollListener, true);
    _hlfScrollListener = null;
  }
});

// ─── Floating CTA: smooth scroll to "Высокоуровневые показатели" ───────
const hlfRef = ref<HTMLElement | null>(null);
const hlfVisible = ref(false);  // true when HLF block is in viewport → hide CTA
let _hlfObserver: IntersectionObserver | null = null;

// Tracks scroll listener for cleanup (declared above the function that registers it).
let _hlfScrollListener: (() => void) | null = null;

// `hlfVisible` here repurposed: false = "near top, show DOWN button",
// true = "scrolled down, show UP button". Button itself is always rendered.
function observeHlfTarget(): void {
  if (_hlfScrollListener) return;
  const THRESHOLD = 500;
  const compute = () => {
    const winY = window.scrollY || window.pageYOffset || 0;
    const docY = document.documentElement?.scrollTop || 0;
    const bodyY = document.body?.scrollTop || 0;
    const scrolled = Math.max(winY, docY, bodyY);
    hlfVisible.value = scrolled > THRESHOLD;
  };
  compute();
  window.addEventListener("scroll", compute, { passive: true });
  window.addEventListener("resize", compute, { passive: true });
  document.addEventListener("scroll", compute, { passive: true, capture: true });
  _hlfScrollListener = compute;
}

function onFabClick(): void {
  // Bidirectional: scroll DOWN to HLF when near top, UP to page top when below.
  if (hlfVisible.value) {
    window.scrollTo({ top: 0, behavior: "smooth" });
  } else {
    scrollToHlf();
  }
}

function scrollToHlf(): void {
  const el = hlfRef.value;
  if (!el) return;
  el.scrollIntoView({ behavior: "smooth", block: "start" });
}

const filteredItems = computed(() =>
  summaryConverted.value
    ? filterBySector(summaryConverted.value.items, companyIdx.value, sectorCode.value)
    : [],
);

// Pack 7.37: convert raw UZS values from backend to selected currency.
// Backend always returns UZS (we send currency="UZS"). Frontend applies the
// per-year UZS→USD/EUR rate from useCurrencyConverter (which loads from
// year_registry via /system-config/yearly-rates with hardcoded fallback).
//
// Conversion is applied to every monetary metric in item.by_year[year][*]
// and portfolio_totals_by_year[year][*]. Each year uses its own rate.
// Percentages (margins) are not stored — they're computed from converted
// values downstream, so they come out correct automatically.
const summaryConverted = computed<PortfolioSummaryResponse | null>(() => {
  if (!summary.value) {
    return null;
  }
  if (currency.value === "UZS") {
    return summary.value;
  }

  const rateFn = (y: number): number =>
    currency.value === "EUR" ? conv.getEurRate(y) : conv.getUsdRate(y);

  // Deep clone so we don't mutate the original (summary.value is referenced
  // elsewhere as raw UZS, e.g., for switching back to UZS).
  const cloned: PortfolioSummaryResponse = JSON.parse(JSON.stringify(summary.value));

  for (const item of cloned.items) {
    for (const [yStr, metrics] of Object.entries(item.by_year)) {
      const y = Number(yStr);
      const rate = rateFn(y);
      if (!isFinite(rate) || rate <= 0) continue;
      for (const k of Object.keys(metrics)) {
        const v = (metrics as any)[k];
        if (v != null && isFinite(v)) (metrics as any)[k] = v / rate;
      }
    }
  }
  for (const [yStr, totals] of Object.entries(cloned.portfolio_totals_by_year)) {
    const y = Number(yStr);
    const rate = rateFn(y);
    if (!isFinite(rate) || rate <= 0) continue;
    for (const k of Object.keys(totals)) {
      const v = (totals as any)[k];
      if (v != null && isFinite(v)) (totals as any)[k] = v / rate;
    }
  }
  return cloned;
});

const narrowedSummary = computed<PortfolioSummaryResponse | null>(() => {
  if (!summaryConverted.value) return null;
  if (!sectorCode.value) return summaryConverted.value;
  const items = filteredItems.value;
  const totals: Record<number, Record<string, number>> = {};
  for (const item of items) {
    for (const [yStr, metrics] of Object.entries(item.by_year)) {
      const y = parseInt(yStr);
      const t = totals[y] || (totals[y] = {});
      for (const [m, val] of Object.entries(metrics)) {
        if (val == null) continue;
        t[m] = (t[m] || 0) + val;
      }
    }
  }
  return { ...summaryConverted.value, items, portfolio_totals_by_year: totals };
});

const kpis = computed(() =>
  narrowedSummary.value ? computePortfolioKpis(narrowedSummary.value, year.value) : null,
);

const inYearCount = computed(() => kpis.value?.companiesInYear || 0);
const totalCount  = computed(() => filteredItems.value.length || summary.value?.coverage.companies_total || 0);
const noDataCount = computed(() => Math.max(0, totalCount.value - inYearCount.value));

const aggregation = computed(() => {
  if (!narrowedSummary.value) return null;
  return aggregateBySector(
    narrowedSummary.value, companyIdx.value, sectors.value,
    activeMetric.value, year.value,
  );
});

const grandTotalAllYears = computed(() => {
  if (!aggregation.value) return 0;
  return aggregation.value.buckets.reduce((sum, b) => {
    return sum + b.companies.reduce((s2, c) => s2 + Math.abs(c.sumAllYears), 0);
  }, 0) || 1;
});

const activeMetricLabel = computed(() =>
  metricList.value.find(m => m.id === activeMetric.value)?.label || activeMetric.value,
);

// ── Modal handlers ────────────────────────────────────────────────────────
function onScoreboardRowClick(companyCode: string) {
  drillCompanyCode.value = companyCode;
}

function onModalClose() {
  drillCompanyCode.value = null;
}
</script>

<template>
  <div class="fd-page">
    <!-- ═══ Pack 7.58: topbar (page header left + switchers right + actions ⋯) ═══ -->
    <FinTopFilters
      v-model:standard="standard"
      v-model:currency="currency"
      v-model:unit="unit"
      v-model:sector-code="sectorCode"
      v-model:year="year"
      v-model:view-tab="viewTab"
      :available-years="yearScope"
      :sectors="sectors"
      page-eyebrow="ФИНАНСЫ · ОБЗОР ПОРТФЕЛЯ"
      page-title="Финансовый портфель">
      <template #subtitle>
        Сводная отчётность по {{ totalCount }} компаниям портфеля ·
        стандарт <strong>{{ standard }}</strong> ·
        валюта <strong>{{ currency }}</strong> ·
        {{ year }} финансовый год
      </template>
      <template #actions>
        <button class="fd-forecast-btn" type="button" @click="forecastOpen = true" title="Прогноз показателей">Прогноз</button>
        <FinCopilot v-if="aiAccess.state.hasAccess" :context="copilotContext" />
        <div class="fd-menu-wrap">
          <button class="fd-menu-trig" :class="{ on: menuOpen }" @click.stop="menuOpen = !menuOpen" title="Действия">
            <svg viewBox="0 0 14 14" width="14" height="14" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round">
              <circle cx="7" cy="3" r="0.8" fill="currentColor" stroke="none"/>
              <circle cx="7" cy="7" r="0.8" fill="currentColor" stroke="none"/>
              <circle cx="7" cy="11" r="0.8" fill="currentColor" stroke="none"/>
            </svg>
          </button>
          <div v-if="menuOpen" class="fd-menu-bg" @click="menuOpen = false"></div>
          <div v-if="menuOpen" class="fd-menu">
            <router-link to="/financials-edit/nsbu" class="fd-menu-item" @click="menuOpen = false">
              <svg viewBox="0 0 14 14" width="13" height="13" fill="none" stroke="currentColor" stroke-width="1.6"><path d="M2 11L9 4l3 3-7 7H2v-3zM8 5l3 3"/></svg>
              Редактировать НСБУ показатели
            </router-link>
            <router-link to="/financials-edit/ifrs" class="fd-menu-item" @click="menuOpen = false">
              <svg viewBox="0 0 14 14" width="13" height="13" fill="none" stroke="currentColor" stroke-width="1.6"><path d="M2 11L9 4l3 3-7 7H2v-3zM8 5l3 3"/></svg>
              Редактировать МСФО показатели
            </router-link>
          </div>
        </div>
      </template>
    </FinTopFilters>

    <div class="fd-content">

    <div v-if="loading" class="fd-state">Загрузка финансовых данных…</div>
    <div v-else-if="errorMsg" class="fd-state fd-state-err">
      ⚠ {{ errorMsg }}
      <button class="fd-state-btn" @click="loadAll">Повторить</button>
    </div>

    <template v-else>
      <div class="fd-section">
        <FinKpiBand
          :kpis="kpis"
          :unit="unit"
          :currency="currency"
          :standard="standard"
          :in-year="inYearCount"
          :total-companies="totalCount"
          :no-data-count="noDataCount"
          :subsidies-total="subsidiesTotal"
          @drill="openKpiDrill"
          @open-subsidies="subsidiesOpen = true" />
      </div>

      <!-- метрики-чипы — наверх, видны всегда (включая чип «История отчётности» под МСФО) -->
      <div class="fd-section">
        <FinMetricTabs
          v-model:active="activeMetric"
          :metrics="metricList" />
      </div>

      <!-- История отчётности МСФО — по чипу, на всю ширину -->
      <div v-if="activeMetric === 'ifrsHistory'" class="fd-section">
        <IfrsReportHistory :companies="companies" :sectors="sectors" :can-edit="finPerm.canEdit.value" />
      </div>

      <div v-else class="fd-body">
        <div class="fd-col">
          <div class="fd-col-grow">
            <FinSectorTable
              v-if="aggregation"
              :buckets="aggregation.buckets"
              :years="yearScope"
              :unit="unit"
              :metric-label="activeMetricLabel"
              :metric-key="activeMetric"
              :current-year="year"
              :grand-total-all-years="grandTotalAllYears" />
          </div>
        </div>

        <div class="fd-col">
          <FinScoreboard
            class="fd-col-grow"
            :summary="narrowedSummary"
            :companies="companies"
            :sectors="sectors"
            :view-tab="viewTab"
            :standard="standard"
            :year="year"
            :unit="unit"
            :sector-filter="sectorCode"
            @row-click="onScoreboardRowClick" />
        </div>
      </div>

      <!-- Pack 7.66: High-Level Financials — hierarchical statements per company -->
      <div ref="hlfRef" class="fd-section">
        <HighLevelFinancials :companies="companies" />
      </div>

    </template>

    <!-- ═══ Floating CTA: bidirectional scroll — down to HLF / up to top ═══ -->
    <button
      class="fd-fab"
      type="button"
      @click="onFabClick"
      :title="hlfVisible ? 'К началу страницы' : 'К блоку «Высокоуровневые показатели»'"
    >
      <span class="fd-fab-pulse"></span>
      <span class="fd-fab-label">{{ hlfVisible ? "Наверх" : "К сводке" }}</span>
      <span class="fd-fab-icon" aria-hidden="true">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none"
             stroke="currentColor" stroke-width="2.2"
             stroke-linecap="round" stroke-linejoin="round">
          <polyline v-if="hlfVisible" points="18 15 12 9 6 15"/>
          <polyline v-else points="6 9 12 15 18 9"/>
        </svg>
      </span>
    </button>

    </div>
    <!-- ═══ /fd-content ═══ -->

    <!-- Drill-down modal (Pack 7.65 — adaptive NSBU/IFRS) -->
    <CompanyDrilldown
      v-if="drillCompanyCode"
      :company-code="drillCompanyCode"
      :companies="companies"
      :sectors="sectors"
      :standard="standard"
      :year="year"
      :currency="currency"
      @close="onModalClose" />

    <!-- ═══ Pack 7.48: KPI drill-down modal ═══ -->
    <FinKpiDrillModal
      v-if="kpiDrill && summary"
      :kpi="kpiDrill"
      :summary="summary"
      :companies="companies"
      :sectors="sectors"
      :year="year"
      :unit="unit"
      :currency="currency"
      :standard="standard"
      @close="closeKpiDrill" />

    <FinForecastModal
      v-if="forecastOpen && summaryConverted"
      :summary="summaryConverted"
      :unit="unit"
      @close="forecastOpen = false" />

    <!-- Реестр субсидий (метрика «Субсидии» → клик) -->
    <FinSubsidiesModal
      v-if="subsidiesOpen"
      :year="year"
      :sector-code="sectorCode"
      :companies="companies"
      :sectors="sectors"
      :can-edit="finPerm.canEdit.value"
      @close="subsidiesOpen = false"
      @changed="loadSubsidies" />
  </div>
</template>

<style scoped>
.fd-page {
  padding: 0 0 28px;
  max-width: none;
  margin: 0;
  display: flex;
  flex-direction: column;
  gap: 10px;
}

/* ═══ Pack 7.50: topbar flush against sidebar (full width, no radius) ═══ */
.fd-page :deep(.ft-bar) {
  border-radius: 0;
  margin: 0;
  box-shadow: 0 4px 14px rgba(15, 23, 60, 0.18);
}

/* ═══ Pack 7.48: content area (padded, aligned with header) ═══ */
.fd-content {
  padding: 12px 32px 0;
  display: flex;
  flex-direction: column;
  gap: 10px;
  max-width: 1900px;
  margin: 0 auto;
  width: 100%;
}

/* Forecast trigger — светлая «таблетка», читаемая и на тёмной панели */
.fd-forecast-btn {
  display: inline-flex; align-items: center; justify-content: center;
  background: #FFFFFF; border: 1px solid rgba(15,23,60,.14);
  color: #1e2a4a; border-radius: 9px; padding: 6px 14px;
  font-size: 12px; font-weight: 600; font-family: inherit; cursor: pointer;
  transition: background .15s, border-color .15s, transform .15s, box-shadow .15s;
}
.fd-forecast-btn:hover {
  background: #ECEAFB; border-color: #B9B4E8; color: #4B4193;
  transform: translateY(-1px); box-shadow: 0 3px 10px rgba(108,92,231,.25);
}
.fd-forecast-ai {
  background: linear-gradient(135deg, #8B7FF0, #6C5CE7);
  border-color: transparent; color: #fff;
  box-shadow: 0 3px 10px rgba(108,92,231,.3);
}
.fd-forecast-ai:hover {
  background: linear-gradient(135deg, #978CF3, #7568E8);
  border-color: transparent; color: #fff;
  box-shadow: 0 5px 16px rgba(108,92,231,.45);
}

/* ═══ Pack 7.58: topbar action menu (⋯) ═══ */
.fd-menu-wrap { position: relative; }
.fd-menu-trig {
  width: 30px;
  height: 30px;
  border-radius: 8px;
  border: 1px solid rgba(255, 255, 255, 0.12);
  background: rgba(255, 255, 255, 0.06);
  color: rgba(255, 255, 255, 0.85);
  cursor: pointer;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  transition: all 0.12s ease;
}
.fd-menu-trig:hover, .fd-menu-trig.on {
  background: rgba(127, 119, 221, 0.25);
  color: #fff;
  border-color: rgba(127, 119, 221, 0.45);
}
.fd-menu-bg { position: fixed; inset: 0; z-index: 99; }
.fd-menu {
  position: absolute;
  top: calc(100% + 8px);
  right: 0;
  min-width: 240px;
  background: var(--bg1, #fff);
  border-radius: 10px;
  box-shadow: 0 12px 32px rgba(15, 23, 60, 0.22), 0 4px 12px rgba(15, 23, 60, 0.08);
  border: 1px solid rgba(15, 23, 60, 0.06);
  padding: 5px;
  z-index: 100;
  animation: fd-menu-in 0.18s var(--ease-standard);
}
@keyframes fd-menu-in {
  from { opacity: 0; transform: translateY(-6px) scale(0.96); }
  to   { opacity: 1; transform: translateY(0) scale(1); }
}
.fd-menu-item {
  width: 100%;
  display: flex;
  align-items: center;
  gap: 9px;
  padding: 8px 12px;
  border: none;
  background: transparent;
  color: var(--t1, #1E2A4A);
  font-size: 12px;
  font-weight: 500;
  cursor: pointer;
  border-radius: 6px;
  text-align: left;
  font-family: inherit;
  text-decoration: none;
  transition: background 0.1s ease;
}
.fd-menu-item:hover { background: rgba(127, 119, 221, 0.06); color: var(--p-deep); }
.fd-menu-item svg { flex-shrink: 0; color: var(--t3, #94A3B8); }
.fd-menu-item:hover svg { color: #7F77DD; }

.fd-state {
  padding: 36px;
  text-align: center;
  color: var(--t3, var(--t3));
  font-size: 13px;
  background: var(--bg2, #fff);
  border: 1px solid var(--border, var(--border-input));
  border-radius: 12px;
}
.fd-state-err { color: #993D3D; }
.fd-state-btn {
  margin-left: 12px;
  border: 1px solid #993D3D;
  background: rgba(153, 61, 61, .05);
  color: #993D3D;
  padding: 4px 12px;
  border-radius: 8px;
  font-size: 12px;
  cursor: pointer;
}

.fd-section { animation: finFadeSlideIn .4s ease 120ms both; }

.fd-body {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 12px;
  align-items: stretch;
}
/* Bumped breakpoint: scoreboard has 10 columns and clips at < ~1600px wide
   when sharing the row with the sector table. Stack vertically earlier. */
@media (max-width: 1600px) { .fd-body { grid-template-columns: 1fr; } }

.fd-col {
  display: flex;
  flex-direction: column;
  gap: 8px;
  min-width: 0;
  min-height: 0;
}
.fd-col-grow {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
}

.fd-col-grow :deep(.fst-card),
.fd-col-grow :deep(.fsb-card) {
  flex: 1;
  display: flex;
  flex-direction: column;
  min-height: 0;
}
.fd-col-grow :deep(.fst-body),
.fd-col-grow :deep(.fsb-scroll) {
  flex: 1;
  max-height: none;
  min-height: 0;
}

/* ═══ Floating CTA — premium glass button bottom-center ═══ */
.fd-fab {
  position: fixed;
  left: 50%;
  bottom: 24px;
  transform: translateX(-50%);
  display: inline-flex;
  align-items: center;
  gap: 8px;
  padding: 10px 18px;
  background: linear-gradient(135deg, #7F77DD 0%, var(--p-deep) 100%);
  color: #fff;
  border: none;
  border-radius: 22px;
  font-family: inherit;
  font-size: 12px;
  font-weight: 500;
  letter-spacing: 0.01em;
  cursor: pointer;
  box-shadow:
    0 8px 28px rgba(83, 74, 183, 0.45),
    0 2px 8px rgba(15, 23, 60, 0.20),
    0 0 0 1px rgba(255, 255, 255, 0.10) inset;
  z-index: 800;
  transition:
    transform 0.22s var(--ease-standard),
    box-shadow 0.22s ease;
  animation: fd-fab-bob 2.4s ease-in-out infinite;
}
.fd-fab:hover {
  transform: translateX(-50%) translateY(-3px) scale(1.03);
  box-shadow:
    0 14px 36px rgba(83, 74, 183, 0.55),
    0 3px 12px rgba(15, 23, 60, 0.24),
    0 0 0 1px rgba(255, 255, 255, 0.18) inset;
  animation-play-state: paused;
}
.fd-fab:active {
  transform: translateX(-50%) translateY(-1px) scale(0.98);
}
.fd-fab-pulse {
  position: absolute;
  inset: -2px;
  border-radius: inherit;
  background: linear-gradient(135deg, rgba(127, 119, 221, 0.50), rgba(83, 74, 183, 0.50));
  z-index: -1;
  animation: fd-fab-pulse 2.4s ease-out infinite;
}
.fd-fab-label {
  position: relative;
  z-index: 1;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  font-size: 11px;
}
.fd-fab-icon {
  position: relative;
  z-index: 1;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 22px;
  height: 22px;
  border-radius: 50%;
  background: rgba(255, 255, 255, 0.18);
  animation: fd-fab-chev 1.6s ease-in-out infinite;
}

/* Premium animations */
@keyframes fd-fab-bob {
  0%, 100% { transform: translateX(-50%) translateY(0); }
  50%      { transform: translateX(-50%) translateY(-4px); }
}
@keyframes fd-fab-pulse {
  0%   { opacity: 0.55; transform: scale(1); }
  60%  { opacity: 0;    transform: scale(1.30); }
  100% { opacity: 0;    transform: scale(1.30); }
}
@keyframes fd-fab-chev {
  0%, 100% { transform: translateY(0); }
  50%      { transform: translateY(3px); }
}

/* Transition for show/hide on intersection observer toggle */
.fd-fab-enter-active,
.fd-fab-leave-active {
  transition:
    opacity 0.28s ease,
    transform 0.32s var(--ease-standard);
}
.fd-fab-enter-from {
  opacity: 0;
  transform: translateX(-50%) translateY(16px) scale(0.92);
}
.fd-fab-leave-to {
  opacity: 0;
  transform: translateX(-50%) translateY(16px) scale(0.92);
}

@media (prefers-reduced-motion: reduce) {
  .fd-fab, .fd-fab-pulse, .fd-fab-icon { animation: none; }
}
</style>
