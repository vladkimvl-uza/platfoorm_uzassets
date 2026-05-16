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
//   4. CompanyFinCard modal opens when user clicks scoreboard row.
// ============================================================================

import { computed, onMounted, ref, watch } from "vue";

import { financialsApi, type PortfolioSummaryResponse } from "@/api/financials";
import { companiesApi, type CompanyListItem, type SectorBrief } from "@/api/companies";
import { useCurrencyConverter } from "@/composables/useCurrencyConverter";

import FinTopFilters    from "@/components/Financials/FinTopFilters.vue";
import FinKpiBand       from "@/components/Financials/FinKpiBand.vue";
import FinSectorDonut   from "@/components/Financials/FinSectorDonut.vue";
import FinMetricTabs    from "@/components/Financials/FinMetricTabs.vue";
import FinSectorTable   from "@/components/Financials/FinSectorTable.vue";
import FinScoreboard    from "@/components/Financials/FinScoreboard.vue";
import CompanyFinCard   from "@/components/Financials/CompanyFinCard.vue";
import CompanyDrilldown from "@/components/Financials/CompanyDrilldown.vue";
import FinKpiDrillModal from "@/components/Financials/FinKpiDrillModal.vue";
import HighLevelFinancials from "@/components/Financials/HighLevelFinancials.vue";

import {
  computePortfolioKpis, filterBySector,
  metricsFor, aggregateBySector, buildCompanyIndex,
  ensureFinancialsCss,
} from "@/components/Financials/financialsHelpers";

const conv = useCurrencyConverter();

// Pack 7.40.4 — diagnostic version banner (visible in browser DevTools)
if (typeof console !== "undefined") {
  console.info(
    "%c[Financials.vue] Pack 7.40.4 loaded — diagnostic build",
    "color: #7F77DD; font-weight: bold;",
  );
}

const standard   = ref<"IFRS" | "NSBU">("IFRS");
// Pack 7.37: currency теперь синхронизирована с глобальным useCurrencyConverter.
// Бэкенд всегда получает UZS — конвертация в USD/EUR делается на клиенте по
// среднегодовым курсам ЦБ РУ из таблицы year_registry. Это позволяет
// переключать валюту мгновенно без перезагрузки данных и держать единый
// источник истины (курсы редактируются в /admin/system-config).
const currency = computed<"UZS" | "USD" | "EUR">({
  get: () => conv.currency.value,
  set: (v) => conv.setCurrency(v),
});
const unit       = ref<"bln" | "mln">("bln");
const sectorCode = ref<string>("");
const year       = ref<number>(2024);
const viewTab    = ref<string>("PL");
const activeMetric = ref<string>("revenue");

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

// Pack 7.40.4 — log currency changes so we can see if FinTopFilters dropdown
// actually emits update:currency events. If you switch UZS↔USD↔EUR and
// nothing logs here, the dropdown isn't wired correctly.
watch(currency, (next, prev) => {
  console.info(
    "%c[Financials] currency changed",
    "color: #EF9F27; font-weight: bold;",
    { from: prev, to: next, conv_currency: conv.currency.value },
  );
});

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

onMounted(() => {
  ensureFinancialsCss();
  loadAll();
});

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
    console.info("[Financials] summaryConverted: summary.value is null");
    return null;
  }
  if (currency.value === "UZS") {
    console.info("[Financials] summaryConverted: currency=UZS, returning raw");
    return summary.value;
  }

  const rateFn = (y: number): number =>
    currency.value === "EUR" ? conv.getEurRate(y) : conv.getUsdRate(y);

  // Pack 7.40.4 — diagnostic: log rate + sample values
  const sampleRate2024 = rateFn(2024);
  const sampleTotal2024 = (summary.value.portfolio_totals_by_year as any)?.[2024]?.revenue;
  console.info(
    "%c[Financials] summaryConverted RUNNING",
    "color: #1D9E75; font-weight: bold;",
    {
      currency: currency.value,
      rate_2024: sampleRate2024,
      raw_revenue_2024: sampleTotal2024,
      expected_converted: sampleTotal2024 && sampleRate2024 > 0 ? sampleTotal2024 / sampleRate2024 : "?",
    },
  );

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
  console.info(
    "[Financials] summaryConverted DONE — converted_revenue_2024:",
    (cloned.portfolio_totals_by_year as any)?.[2024]?.revenue,
  );
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
          @drill="openKpiDrill" />
      </div>

      <div class="fd-body">
        <div class="fd-col">
          <FinSectorDonut
            v-if="aggregation"
            :donut-data="aggregation.donutByYear"
            :year="year"
            :unit="unit"
            :currency="currency"
            :metric-label="activeMetricLabel" />

          <FinMetricTabs
            v-model:active="activeMetric"
            :metrics="metricList" />

          <div class="fd-col-grow">
            <FinSectorTable
              v-if="aggregation"
              :buckets="aggregation.buckets"
              :years="yearScope"
              :unit="unit"
              :metric-label="activeMetricLabel"
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
      <div class="fd-section">
        <HighLevelFinancials :companies="companies" />
      </div>
    </template>

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

    <!-- Legacy drill-down kept for fallback / can be deleted next pack
    <CompanyFinCard
      v-if="false && drillCompanyCode && summary"
      :company-code="drillCompanyCode"
      :summary="summary"
      :companies="companies"
      :sectors="sectors"
      :standard="standard"
      :unit="unit"
      :currency="currency"
      @close="onModalClose" /> -->

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
  background: #fff;
  border-radius: 10px;
  box-shadow: 0 12px 32px rgba(15, 23, 60, 0.22), 0 4px 12px rgba(15, 23, 60, 0.08);
  border: 1px solid rgba(15, 23, 60, 0.06);
  padding: 5px;
  z-index: 100;
  animation: fd-menu-in 0.18s cubic-bezier(0.34, 1.2, 0.64, 1);
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
  color: #1E2A4A;
  font-size: 12px;
  font-weight: 500;
  cursor: pointer;
  border-radius: 6px;
  text-align: left;
  font-family: inherit;
  text-decoration: none;
  transition: background 0.1s ease;
}
.fd-menu-item:hover { background: rgba(127, 119, 221, 0.06); color: #534AB7; }
.fd-menu-item svg { flex-shrink: 0; color: #94A3B8; }
.fd-menu-item:hover svg { color: #7F77DD; }

.fd-state {
  padding: 36px;
  text-align: center;
  color: var(--t3, #64748B);
  font-size: 13px;
  background: var(--bg2, #fff);
  border: 1px solid var(--border, #E2E8F0);
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
@media (max-width: 1280px) { .fd-body { grid-template-columns: 1fr; } }

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
</style>
