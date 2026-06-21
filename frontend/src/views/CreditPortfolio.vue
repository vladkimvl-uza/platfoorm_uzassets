<script setup lang="ts">
/**
 * CreditPortfolio v4 — финальная версия модуля.
 *
 * Pack 8.2 topbar refresh:
 *  - Dark navy gradient (унификация с Invest Projects / FinModel / BP)
 *  - Sidebar toggle (☰) в левой части
 *  - Все элементы (title, tabs, currency toggle, company dropdown) в одной 56px полосе
 */
import { inject, onMounted, watch, onBeforeUnmount, ref, computed } from "vue";
import { useCreditData } from "@/composables/useCreditData";
import { useFormatters } from "@/composables/useFormatters";
import { useAiPageContext } from "@/composables/useAiPageContext";
import CreditKpiBand from "@/components/CreditPortfolio/CreditKpiBand.vue";
import TabOverview from "@/components/CreditPortfolio/TabOverview.vue";
import TabLenders from "@/components/CreditPortfolio/TabLenders.vue";
import TabRisk from "@/components/CreditPortfolio/TabRisk.vue";
import TabPayments from "@/components/CreditPortfolio/TabPayments.vue";
import TabLoans from "@/components/CreditPortfolio/TabLoans.vue";
import LoanDetailModal from "@/components/CreditPortfolio/LoanDetailModal.vue";
import LoanEditorDrawer from "@/components/CreditPortfolio/LoanEditorDrawer.vue";
import ExcelImportModal from "@/components/CreditPortfolio/ExcelImportModal.vue";

const credit = useCreditData();
const fmt = useFormatters();
// Per user feedback 2026-05-25: вместо raw ISO "2026-01-01" показываем
// «1 января 2026 г.» (long format), как в ExecDashCreditBlock.
const asOfLong = computed(() => {
  const iso = credit.asOfDate.value;
  if (!iso) return "";
  const d = new Date(iso);
  return isNaN(d.getTime()) ? iso : fmt.fmtDate(d, { long: true });
});

// Pack 7.9e: AI Bubble context
useAiPageContext({
  key: "credit-portfolio",
  label: "Кредитный портфель",
  describeState: () => {
    const v = credit.view.value;
    const f = credit.fmt.value;
    const co = credit.selectedCompanyMeta.value?.name_short
      || credit.selectedCompanyMeta.value?.name_ru;
    return [
      `view: ${v}`, `format: ${f}`,
      co ? `компания: ${co}` : "все компании"
    ].join("; ");
  },
  quickActions: [
    { label: "Концентрация рисков",
      prompt: "Проанализируй концентрацию кредитного риска в портфеле: топ-3 банка по объёму долга, топ-3 компании по debt_usd, валютная разбивка. Используй get_credit_portfolio + verify_count(cp_loans)." },
    { label: "Refi-окно 2027",
      prompt: "Какие кредиты погашаются в 2026-2027? Каков risk рефинансирования с учётом текущих мировых ставок (Fed 4.25-4.50%)? Используй get_credit_portfolio + макро-блок." },
    { label: "What-if: rate +200bp",
      prompt: "What-if сценарий: ставки выросли на 200 bp. Какой annual interest expense impact на портфель? Используй list_scenarios(kind=credit) + get_credit_portfolio." },
    { label: "Валютные риски",
      prompt: "Покажи валютную разбивку портфеля. Какой FX-риск при девальвации UZS на 10%? Какие компании наиболее уязвимы (USD-доход vs USD-расход баланс)?" },
    { label: "Сводка credit-портфеля",
      prompt: "Дай сводку всего кредитного портфеля: общий debt USD, валюты, банки, средневзвешенная ставка. Топ-3 риска. Используй get_credit_portfolio." },
  ],
});

// Pack 140: inline company dropdown (matches InvestProjects glass-style)
const companyDdOpen = ref(false);
const availableCreditCompanies = computed(() => {
  const list = credit.companiesWithLoans.value || [];
  return list.filter(c => Number(c.debt_usd) > 0);
});
function toggleCompanyDd() {
  companyDdOpen.value = !companyDdOpen.value;
}
function pickCompany(companyId: string | null) {
  if (companyId === null) {
    credit.setSelectedCompany(null);
  } else {
    credit.setSelectedCompanyById(companyId);
  }
  companyDdOpen.value = false;
}
function closeDdOnOutside(e: MouseEvent) {
  if (!companyDdOpen.value) return;
  const t = e.target as HTMLElement;
  if (!t.closest('.cp-glass-select') && !t.closest('.cp-co-pop')) {
    companyDdOpen.value = false;
  }
}
onMounted(() => document.addEventListener('click', closeDdOnOutside));
onBeforeUnmount(() => document.removeEventListener('click', closeDdOnOutside));

const toggleSidebar = inject<() => void>("toggleSidebar", () => {});
const openMobileSidebar = inject<() => void>("openMobileSidebar", () => {});
function onBurger() {
  if (typeof window !== "undefined" && window.innerWidth <= 1023) openMobileSidebar();
  else toggleSidebar();
}

onMounted(async () => {
  await credit.loadAll();
});

watch(() => credit.asOfDate.value, async () => {
  await Promise.allSettled([
    credit.loadAggregate(),
    credit.loadCompaniesOverview(),
    credit.loadRiskMetrics(),
    credit.loadRiskBubble(),
    credit.loadSankey(),
  ]);
});

const tabs: Array<{ key: any; label: string }> = [
  { key: "overview", label: "Обзор" },
  { key: "lenders", label: "Кредиторы" },
  { key: "risk", label: "Риски" },
  { key: "payments", label: "Платежи" },
  { key: "loans", label: "Все кредиты" },
];
</script>

<template>
  <div class="cp-root">
    <!-- ─── TOPBAR (dark navy, единый паттерн) ─────────────── -->
    <div class="cp-topbar">
      <div class="cp-tb-l" style="position: relative;">
        <button class="cp-sb-toggle" @click="onBurger()" title="Меню / свернуть сайдбар" aria-label="toggle sidebar">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round">
            <line x1="3" y1="6" x2="21" y2="6"/>
            <line x1="3" y1="12" x2="21" y2="12"/>
            <line x1="3" y1="18" x2="21" y2="18"/>
          </svg>
        </button>

        <!-- Pack 140: inline company dropdown -->
        <button
          class="cp-glass-select"
          :class="{ open: companyDdOpen }"
          @click.stop="toggleCompanyDd"
          style="display:flex; align-items:center; gap:8px; padding:5px 11px; min-width:180px; height:32px; background:rgba(255,255,255,.08); border:1px solid rgba(255,255,255,.12); border-radius:8px; color:#fff; font-size:12px; font-weight:500; cursor:pointer;"
        >
          <span style="width:7px; height:7px; border-radius:50%; flex-shrink:0; background:#9B8EC4;"></span>
          <span style="flex:1; text-align:left; white-space:nowrap; overflow:hidden; text-overflow:ellipsis;">
            {{ credit.selectedCompanyMeta.value ? credit.selectedCompanyMeta.value.company_name_ru : 'Все компании' }}
          </span>
          <svg width="10" height="10" viewBox="0 0 12 12" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" :style="{ transform: companyDdOpen ? 'rotate(180deg)' : 'rotate(0deg)', transition: 'transform .15s' }">
            <path d="M2 4.5l4 4 4-4"/>
          </svg>
        </button>
        <div
          v-if="companyDdOpen"
          class="cp-co-pop"
          @click.stop
          style="position:absolute; top:44px; left:56px; z-index:100; min-width:260px; max-height:420px; overflow-y:auto; background:#1E2A4A; border:1px solid rgba(255,255,255,.12); border-radius:10px; padding:4px; display:flex; flex-direction:column; gap:1px; box-shadow:0 12px 32px rgba(15,23,60,.4);"
        >
          <button
            @click="pickCompany(null)"
            :style="{ display:'flex', alignItems:'center', gap:'9px', padding:'8px 11px', background: credit.selectedCompanyId.value === null ? 'rgba(155,142,196,.18)' : 'transparent', border:'none', color:'#fff', fontSize:'12px', fontWeight:'500', cursor:'pointer', borderRadius:'6px', textAlign:'left', width:'100%' }"
          >
            <span :style="{ width:'7px', height:'7px', borderRadius:'50%', flexShrink:0, background: credit.selectedCompanyId.value === null ? '#9B8EC4' : '#D1D5DB' }"></span>
            <span style="flex:1; text-align:left;">Все компании</span>
          </button>
          <button
            v-for="c in availableCreditCompanies"
            :key="c.company_id"
            @click="pickCompany(c.company_id)"
            :style="{ display:'flex', alignItems:'center', gap:'9px', padding:'8px 11px', background: credit.selectedCompanyId.value === c.company_id ? 'rgba(155,142,196,.18)' : 'transparent', border:'none', color:'#fff', fontSize:'12px', fontWeight:'500', cursor:'pointer', borderRadius:'6px', textAlign:'left', width:'100%' }"
          >
            <span :style="{ width:'7px', height:'7px', borderRadius:'50%', flexShrink:0, background: credit.selectedCompanyId.value === c.company_id ? '#9B8EC4' : '#D1D5DB' }"></span>
            <span style="flex:1; text-align:left; white-space:nowrap; overflow:hidden; text-overflow:ellipsis;">{{ c.company_name_ru }}</span>
            <span style="font-size:9.5px; color:rgba(255,255,255,.5); white-space:nowrap;">{{ c.loans_count }}</span>
          </button>
        </div>
      </div>
      <div class="cp-tb-c">
        <div class="cp-tb-eyebrow">UzAssets · Финансы</div>
        <div class="cp-tb-title-row">
          <span class="cp-tb-title">Кредитный портфель</span>
          <span class="cp-tb-asof">· по состоянию на {{ asOfLong }}</span>
        </div>
      </div>

      <div class="cp-tb-r">
        <div class="cp-tabs">
          <button
            v-for="t in tabs"
            :key="t.key"
            type="button"
            class="cp-tab"
            :class="{ on: credit.view.value === t.key }"
            @click="credit.setView(t.key)"
          >
            {{ t.label }}
          </button>
        </div>

        <div class="cp-fmt-toggle">
          <button
            type="button"
            class="cp-fmt-btn"
            :class="{ on: credit.fmt.value === 'usd' }"
            @click="credit.setFmt('usd')"
          >USD</button>
          <button
            type="button"
            class="cp-fmt-btn"
            :class="{ on: credit.fmt.value === 'uzs' }"
            @click="credit.setFmt('uzs')"
          >Сум</button>
        </div>

      </div>
    </div>

    <!-- ─── KPI BAND + tab content ────────────────────────── -->
    <div class="cp-content-wrap">
      <CreditKpiBand />

      <div class="cp-tab-content">
        <TabOverview v-if="credit.view.value === 'overview'" />
        <TabLenders  v-else-if="credit.view.value === 'lenders'" />
        <TabRisk     v-else-if="credit.view.value === 'risk'" />
        <TabPayments v-else-if="credit.view.value === 'payments'" />
        <TabLoans    v-else-if="credit.view.value === 'loans'" />
      </div>
    </div>

    <Teleport to="body">
      <LoanDetailModal />
      <LoanEditorDrawer />
      <ExcelImportModal />
    </Teleport>
  </div>
</template>

<style scoped>
.cp-root {
  background: #F4F3F9;
  min-height: calc(100vh - 48px);
  margin: 0;
  padding: 0;
  max-width: none;
}

.cp-content-wrap {
  max-width: 1680px;
  margin: 0 auto;
  padding: 18px 24px 32px;
}

/* ─── TOPBAR (dark navy) ────────────────────────────────── */
.cp-topbar {
  display: grid;
  grid-template-columns: auto 1fr auto;
  grid-template-rows: 56px;
  align-items: center;
  gap: 14px;
  padding: 0 24px;
  background: linear-gradient(180deg, #1E2A4A 0%, #1A2440 100%);
  color: #fff;
  border-bottom: 0.5px solid rgba(255, 255, 255, 0.06);
}

.cp-tb-l {
  grid-column: 1;
  display: flex;
  align-items: center;
  gap: 12px;
  min-width: 0;
}

.cp-sb-toggle {
  width: 32px;
  height: 32px;
  border: 1px solid rgba(255, 255, 255, 0.15);
  background: rgba(255, 255, 255, 0.06);
  border-radius: 8px;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  color: rgba(255, 255, 255, 0.7);
  transition: all 0.15s;
  padding: 0;
  flex-shrink: 0;
}
.cp-sb-toggle:hover { background: rgba(255, 255, 255, 0.14); color: #fff; }
.cp-sb-toggle:active { transform: scale(0.94); }

.cp-tb-titles {
  display: flex;
  flex-direction: column;
  gap: 1px;
  min-width: 0;
}
.cp-tb-eyebrow {
  font-size: 9.5px;
  font-weight: 500;
  letter-spacing: 0.1em;
  text-transform: uppercase;
  color: rgba(255, 255, 255, 0.5);
}
.cp-tb-title-row {
  display: flex;
  align-items: baseline;
  gap: 6px;
  white-space: nowrap;
  overflow: hidden;
}
.cp-tb-title {
  font-size: 14px;
  font-weight: 500;
  color: #fff;
  letter-spacing: 0.005em;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.cp-tb-asof {
  font-size: 10.5px;
  font-weight: 500;
  color: rgba(255, 255, 255, 0.55);
  font-feature-settings: "tnum";
  white-space: nowrap;
}


/* Pack 138: centered title block */
.cp-tb-c {
  grid-column: 2;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 1px;
  min-width: 0;
  text-align: center;
}
.cp-tb-r {
  grid-column: 3;
  justify-self: end;
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: nowrap;
}

/* ─── Tabs (white-text pills inside topbar) ─────────────── */
.cp-tabs {
  display: flex;
  background: rgba(255, 255, 255, 0.08);
  border: 1px solid rgba(255, 255, 255, 0.1);
  border-radius: 8px;
  padding: 2px;
  gap: 0;
}
.cp-tab {
  padding: 5px 11px;
  background: transparent;
  border: none;
  border-radius: 6px;
  font-family: inherit;
  font-size: 11.5px;
  font-weight: 500;
  color: rgba(255, 255, 255, 0.55);
  cursor: pointer;
  transition: all 0.15s;
  white-space: nowrap;
  letter-spacing: -0.005em;
}
.cp-tab:hover:not(.on) {
  color: rgba(255, 255, 255, 0.85);
  background: rgba(255, 255, 255, 0.05);
}
.cp-tab.on {
  background: rgba(255, 255, 255, 0.18);
  color: #fff;
  font-weight: 500;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.15);
}

/* ─── USD/Сум toggle ─────────────────────────────────── */
.cp-fmt-toggle {
  display: flex;
  background: rgba(255, 255, 255, 0.08);
  border: 1px solid rgba(255, 255, 255, 0.1);
  border-radius: 8px;
  padding: 2px;
}
.cp-fmt-btn {
  padding: 5px 10px;
  background: transparent;
  border: none;
  border-radius: 6px;
  font-family: inherit;
  font-size: 11px;
  font-weight: 500;
  color: rgba(255, 255, 255, 0.55);
  cursor: pointer;
  transition: all 0.15s;
  letter-spacing: 0.02em;
}
.cp-fmt-btn:hover:not(.on) {
  color: rgba(255, 255, 255, 0.85);
}
.cp-fmt-btn.on {
  background: rgba(255, 255, 255, 0.18);
  color: #fff;
  font-weight: 500;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.15);
}

/* ─── Responsive: на узких экранах перенос строки в правом блоке ─── */
@media (max-width: 1180px) {
  .cp-topbar {
    grid-template-rows: auto;
    padding: 10px 20px;
  }
  
/* Pack 138: centered title block */
.cp-tb-c {
  grid-column: 2;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 1px;
  min-width: 0;
  text-align: center;
}
.cp-tb-r {
    flex-wrap: wrap;
    gap: 6px;
  }
  .cp-tabs {
    order: 99;
    flex-basis: 100%;
  }
}
</style>
