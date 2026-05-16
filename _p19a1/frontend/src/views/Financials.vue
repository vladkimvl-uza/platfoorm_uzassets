<script setup lang="ts">
// ============================================================================
// Financials dashboard — portfolio-wide view.                  [Phase 19a-1]
//
// Replaces the previous per-company file browser. The previous functionality
// (per-company report management) is preserved at /financials-detailed and
// /financials/edit/:id — those views are unchanged.
//
//   1. Topbar                  — НСБУ/МСФО · UZS/USD/EUR · млрд/млн · сектор · год · view
//   2. KPI band                — 5–6 cards (depending on standard)
//   3. Donut + sector tabs     — placeholder (Phase 19a-2)
//   4. Big sector-grouped table — placeholder (Phase 19a-2)
//   5. Scoreboard panel        — placeholder (Phase 19a-3)
// ============================================================================

import { computed, onMounted, ref, watch } from "vue";

import { financialsApi, type PortfolioSummaryResponse } from "@/api/financials";
import { companiesApi, type SectorBrief } from "@/api/companies";

import FinTopFilters from "@/components/Financials/FinTopFilters.vue";
import FinKpiBand    from "@/components/Financials/FinKpiBand.vue";

import {
  computePortfolioKpis, filterBySector, ensureFinancialsCss,
} from "@/components/Financials/financialsHelpers";

// ─── State ────────────────────────────────────────────────────────────────
const standard  = ref<"IFRS" | "NSBU">("IFRS");
const currency  = ref<"UZS" | "USD" | "EUR">("UZS");
const unit      = ref<"bln" | "mln">("bln");
const sectorCode = ref<string>("");
const year      = ref<number>(2024);
const viewTab   = ref<string>("PL");

const summary  = ref<PortfolioSummaryResponse | null>(null);
const sectors  = ref<SectorBrief[]>([]);
const loading  = ref(true);
const errorMsg = ref<string | null>(null);
const lastUpdated = ref<string>("");

const yearScope = (() => {
  const now = new Date().getFullYear();
  const out: number[] = [];
  for (let y = 2021; y <= now + 1; y++) out.push(y);
  return out;
})();

// ─── Reset view tab when standard changes (IFRS vs NSBU have different tabs) ──
watch(standard, (s) => {
  viewTab.value = s === "IFRS" ? "PL" : "PL";
});

// ─── Data load ────────────────────────────────────────────────────────────
async function loadAll() {
  loading.value = true;
  errorMsg.value = null;
  try {
    const [companiesResp, sumResp] = await Promise.all([
      companiesApi.list({ limit: 200 }),
      financialsApi.portfolioSummary({
        standard: standard.value,
        years: yearScope,
        currency: currency.value,
      }),
    ]);
    sectors.value = companiesResp.sectors || [];
    summary.value = sumResp;
    lastUpdated.value = new Date().toISOString().slice(0, 10);
  } catch (e: any) {
    errorMsg.value =
      e?.response?.data?.detail || e?.message || "Не удалось загрузить данные";
    console.error("Financials portfolio-summary load failed:", e);
  } finally {
    loading.value = false;
  }
}

// Reload when standard or currency changes (server filters by both)
watch([standard, currency], () => {
  loadAll();
});

onMounted(() => {
  ensureFinancialsCss();
  loadAll();
});

// ─── Derived data ─────────────────────────────────────────────────────────
const filteredItems = computed(() =>
  summary.value ? filterBySector(summary.value.items, sectorCode.value) : [],
);

const portfolioForKpis = computed<PortfolioSummaryResponse | null>(() => {
  if (!summary.value) return null;
  if (!sectorCode.value) return summary.value;

  // Recompute portfolio_totals from filtered items
  const items = filteredItems.value;
  const totals: Record<number, Record<string, number>> = {};
  for (const item of items) {
    for (const [yStr, metrics] of Object.entries(item.by_year)) {
      const y = parseInt(yStr);
      const t = totals[y] || (totals[y] = {});
      for (const [m, v] of Object.entries(metrics)) {
        if (v == null) continue;
        t[m] = (t[m] || 0) + v;
      }
    }
  }
  return {
    ...summary.value,
    items,
    portfolio_totals_by_year: totals,
  };
});

const kpis = computed(() =>
  portfolioForKpis.value
    ? computePortfolioKpis(portfolioForKpis.value, year.value)
    : null,
);

const inYearCount = computed(() => kpis.value?.companiesInYear || 0);
const totalCount = computed(() => filteredItems.value.length);
const noDataCount = computed(() => Math.max(0, totalCount.value - inYearCount.value));
</script>

<template>
  <div class="fd-page">
    <!-- Top filter bar -->
    <FinTopFilters
      v-model:standard="standard"
      v-model:currency="currency"
      v-model:unit="unit"
      v-model:sector-code="sectorCode"
      v-model:year="year"
      v-model:view-tab="viewTab"
      :available-years="yearScope"
      :sectors="sectors"
      :as-of-date="lastUpdated" />

    <!-- Loading / error -->
    <div v-if="loading" class="fd-state">Загрузка финансовых данных…</div>
    <div v-else-if="errorMsg" class="fd-state fd-state-err">
      ⚠ {{ errorMsg }}
      <button class="fd-state-btn" @click="loadAll">Повторить</button>
    </div>

    <template v-else>
      <!-- KPI band -->
      <div class="fd-section">
        <FinKpiBand
          :kpis="kpis"
          :unit="unit"
          :currency="currency"
          :standard="standard"
          :in-year="inYearCount"
          :total-companies="totalCount"
          :no-data-count="noDataCount" />
      </div>

      <!-- Placeholders for upcoming sub-phases -->
      <div class="fd-row-mid">
        <div class="fd-placeholder">
          <div class="fd-ph-eyebrow">Phase 19a-2</div>
          <div class="fd-ph-title">{{ year - 5 }}–{{ year + 1 }}, {{ unit === 'bln' ? 'млрд' : 'млн' }} {{ currency }}</div>
          <div class="fd-ph-sub">
            Сюда придёт Donut по секторам + табы метрик (Выручка / Себестоимость / Вал.прибыль /
            Опер.прибыль / Чистая прибыль / EBITDA) + большая таблица всех компаний по секторам с
            колонками годов и mini-bar для YoY.
          </div>
          <div class="fd-ph-debug">
            Загружено компаний: {{ summary?.items.length || 0 }} ·
            Покрытие FY {{ year }}: {{ inYearCount }}/{{ totalCount }}
          </div>
        </div>
        <div class="fd-placeholder">
          <div class="fd-ph-eyebrow">Phase 19a-3</div>
          <div class="fd-ph-title">СКОРБОРД · {{ viewTab }}</div>
          <div class="fd-ph-sub">
            Скорборд: компании × ключевые метрики × sparkline тренда. Клик по строке откроет
            <code>CompanyFinCard</code>.
          </div>
        </div>
      </div>
    </template>
  </div>
</template>

<style scoped>
.fd-page {
  padding: 14px 18px 28px;
  max-width: 1900px;
  margin: 0 auto;
  display: flex;
  flex-direction: column;
  gap: 14px;
}

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
.fd-state-btn:hover { background: rgba(153, 61, 61, .12); }

.fd-section { animation: finFadeSlideIn .4s ease 120ms both; }

.fd-row-mid {
  display: grid;
  grid-template-columns: 3fr 2fr;
  gap: 12px;
  margin-top: 4px;
}
@media (max-width: 1280px) { .fd-row-mid { grid-template-columns: 1fr; } }

.fd-placeholder {
  background: linear-gradient(135deg, rgba(127, 119, 221, 0.05) 0%, rgba(55, 138, 221, 0.04) 100%);
  border: 1px dashed rgba(127, 119, 221, 0.30);
  border-radius: 12px;
  padding: 24px 22px;
  display: flex;
  flex-direction: column;
  gap: 6px;
  min-height: 240px;
  animation: finFadeSlideIn .4s ease 200ms both;
}
.fd-ph-eyebrow {
  font-size: 9.5px;
  font-weight: 700;
  letter-spacing: 0.10em;
  text-transform: uppercase;
  color: #7F77DD;
  margin-bottom: 2px;
}
.fd-ph-title {
  font-size: 14px;
  font-weight: 600;
  color: var(--t1, #1E2A4A);
  letter-spacing: -0.005em;
}
.fd-ph-sub {
  font-size: 12px;
  color: var(--t2, #4B5468);
  line-height: 1.5;
}
.fd-ph-sub code {
  background: rgba(127, 119, 221, 0.10);
  padding: 1px 6px;
  border-radius: 4px;
  font-size: 11px;
  font-family: ui-monospace, monospace;
  color: #534AB7;
}
.fd-ph-debug {
  margin-top: auto;
  font-size: 11px;
  color: var(--t3, #64748B);
  font-variant-numeric: tabular-nums;
  font-family: ui-monospace, monospace;
}
</style>
