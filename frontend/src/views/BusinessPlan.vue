<template>
  <Transition name="uza-fade" mode="out-in">
    <div :key="state.selectedYear.value">
  <div class="bp-view">
    <!-- Top bar -->
    <div class="bp-topbar">
      <div class="bp-tb-left">
        <div class="bp-tb-eyebrow">UzAssets · Бизнес-план</div>
        <div class="bp-tb-title">{{ headerTitle }}</div>
        <div class="bp-tb-sub">{{ headerSub }}</div>
      </div>
      <div class="bp-tb-right">
        <!-- View toggle -->
        <div class="bp-toggle">
          <button :class="{ on: state.viewMode.value === 'summary' }" @click="state.setViewMode('summary')">
            Сводка
          </button>
          <button :class="{ on: state.viewMode.value === 'company' }" @click="state.setViewMode('company')">
            По компании
          </button>
        </div>

        <!-- Lens toggle: Все / Доходы / Расходы — applies to KPI cards in summary
             and Details table in company view -->
        <div class="bp-lens">
          <button :class="{ on: lens === 'all' }"      @click="lens = 'all'">Все</button>
          <button :class="['bp-lens-inc', { on: lens === 'income' }]"   @click="lens = 'income'">Доходы</button>
          <button :class="['bp-lens-exp', { on: lens === 'expenses' }]" @click="lens = 'expenses'">Расходы</button>
        </div>

        <!-- Period -->
        <div class="bp-pd-seg">
          <button
            v-for="p in BP_PERIODS"
            :key="p.key"
            :class="{ on: state.selectedPeriod.value === p.key }"
            @click="state.setPeriod(p.key)"
          >
            {{ p.label }}
          </button>
        </div>

        <!-- Year -->
        <div class="bp-yr-seg">
          <button
            v-for="y in state.availableYears.value"
            :key="y"
            :class="{ on: state.selectedYear.value === y }"
            @click="state.setYear(y)"
          >
            {{ y }}
          </button>
        </div>

        <!-- Menu -->
        <div class="bp-menu-wrap">
          <button class="bp-menu-btn" @click="menuOpen = !menuOpen">⋯</button>
          <div v-if="menuOpen" class="bp-menu" @click="menuOpen = false">
            <button v-if="canEdit" @click="openEditor">✎ Редактировать</button>
            <button v-if="canDelete" @click="confirmDelete">🗑 Удалить год</button>
          </div>
        </div>
      </div>
    </div>

    <!-- Company picker (only for company mode) -->
    <div v-if="state.viewMode.value === 'company'" class="bp-co-picker">
      <select
        :value="state.selectedCompanyId.value || ''"
        @change="onCompanyChange"
        class="bp-co-select"
      >
        <option value="">— выберите компанию —</option>
        <option
          v-for="co in state.companies.value"
          :key="co.company_id"
          :value="co.company_id"
        >
          {{ co.company_name_ru }}
        </option>
      </select>
    </div>

    <!-- Body -->
    <div class="bp-body">
      <div v-if="state.error.value" class="bp-err">
        {{ state.error.value }}
      </div>

      <!-- Summary mode -->
      <BpSummaryDashboard
        v-if="state.viewMode.value === 'summary' && state.summary.value && state.summary.value.co_count > 0"
        :summary="state.summary.value"
        :lens="lens"
        @open-company="onDrillCompany"
        @open-kpi="onDrillKpi"
        @open-sector="onDrillSector"
        @open-pnl-line="onDrillPnlLine"
      />
      <div v-else-if="state.viewMode.value === 'summary' && state.summary.value && state.summary.value.co_count === 0" class="bp-empty">
        Нет данных бизнес-плана. Перейдите в режим «По компании» и заведите данные.
      </div>

      <!-- Company mode -->
      <BpCompanyDashboard
        v-if="state.viewMode.value === 'company' && state.computed.value && state.selectedCompany.value"
        :computed-data="state.computed.value"
        :attention="state.attention.value"
        :comment="state.comment.value"
        :company-name="state.selectedCompany.value.company_name_ru"
        :year="state.selectedYear.value"
        :period="state.selectedPeriod.value"
        :can-edit="canEdit"
        :lens="lens"
        @comment-saved="onCommentSaved"
      />
      <div v-else-if="state.viewMode.value === 'company' && !state.selectedCompany.value" class="bp-empty">
        Выберите компанию для просмотра деталей.
      </div>
    </div>

    <!-- Editor -->
    <BpEditor
      v-if="editorOpen && state.selectedCompany.value"
      :company-id="state.selectedCompany.value.company_id"
      :company-name="state.selectedCompany.value.company_name_ru"
      :year="state.selectedYear.value"
      @close="editorOpen = false"
      @saved="onEditorSaved"
    />

    <!-- Drill modal -->
    <BpDrillModal
      v-if="drill && state.summary.value"
      :mode="drill.mode"
      :metric="drill.metric"
      :company-id="drill.companyId"
      :company-name="drill.companyName"
      :sector-code="drill.sectorCode"
      :sector-label="drill.sectorLabel"
      :line-key="drill.lineKey"
      :summary="state.summary.value"
      :year="state.selectedYear.value"
      :period="state.selectedPeriod.value"
      @close="drill = null"
    />
  </div>
    </div>
  </Transition>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from "vue";
import { BP_PERIODS, bpApi } from "@/api/bpKpi";
import { useBusinessPlanData } from "@/composables/useBusinessPlanData";
import BpSummaryDashboard from "@/components/BusinessPlan/BpSummaryDashboard.vue";
import BpCompanyDashboard from "@/components/BusinessPlan/BpCompanyDashboard.vue";
import BpEditor from "@/components/BusinessPlan/BpEditor.vue";
import BpDrillModal from "@/components/BusinessPlan/BpDrillModal.vue";
import { usePermissions } from "@/composables/usePermissions";

const perm = usePermissions("bp");
const canEdit = perm.canEdit;
const canDelete = perm.canDelete;

const state = useBusinessPlanData();
const menuOpen = ref(false);
const editorOpen = ref(false);

// Top-level «lens» — passes down to summary + company dashboards so the same
// All/Доходы/Расходы choice applies in both views.
const lens = ref<"all" | "income" | "expenses">("all");

// Headline metric driving by_company / by_sector / by_quarter aggregations
// on the portfolio summary. Maps lens → primary BP_FIELD:
//   all     → revenue (default)
//   income  → revenue
//   expenses → opExpenses (период-расходы; main spending bucket)
function headlineMetricFor(l: "all" | "income" | "expenses"): string {
  return l === "expenses" ? "opExpenses" : "revenue";
}

// Refetch portfolio summary whenever lens flips so the bottom 3 widgets
// (quarterly, top-companies, sectors) reflect the right metric.
watch(lens, async (l) => {
  if (state.viewMode.value === "summary") {
    await state.loadSummary(headlineMetricFor(l));
  }
});

type DrillSpec = {
  mode: "kpi" | "company" | "sector" | "pnl-line";
  metric?: string;
  companyId?: string;
  companyName?: string;
  sectorCode?: string;
  sectorLabel?: string;
  lineKey?: string;
};
const drill = ref<DrillSpec | null>(null);

const headerTitle = computed(() =>
  state.viewMode.value === "summary"
    ? "Сводка по портфелю"
    : state.selectedCompany.value?.company_name_ru ?? "Выберите компанию",
);

const headerSub = computed(() => {
  const p = BP_PERIODS.find((x) => x.key === state.selectedPeriod.value);
  const lbl = p?.key === "annual" ? "годовой итог" : `нарастающим итогом за ${p?.label}`;
  if (state.viewMode.value === "summary" && state.summary.value) {
    return `FY ${state.selectedYear.value} · ${lbl} · ${state.summary.value.co_count} компаний · млрд сум`;
  }
  return `FY ${state.selectedYear.value} · ${lbl} · млрд сум`;
});

function onCompanyChange(e: Event) {
  state.setCompany((e.target as HTMLSelectElement).value || null);
}

function openEditor() {
  if (!state.selectedCompany.value) {
    alert("Сначала выберите компанию в режиме «По компании»");
    return;
  }
  editorOpen.value = true;
}

async function onEditorSaved() {
  editorOpen.value = false;
  await state.loadCompanies();
  if (state.viewMode.value === "summary") await state.loadSummary(headlineMetricFor(lens.value));
  else await state.loadCompanyData();
}

async function confirmDelete() {
  if (!state.selectedCompany.value) {
    alert("Выберите компанию");
    return;
  }
  if (!confirm(`Удалить весь бизнес-план ${state.selectedCompany.value.company_name_ru} за ${state.selectedYear.value}?`)) return;
  try {
    await bpApi.deleteYear(state.selectedCompany.value.company_id, state.selectedYear.value);
    await state.loadCompanies();
    if (state.viewMode.value === "summary") await state.loadSummary(headlineMetricFor(lens.value));
    else await state.loadCompanyData();
  } catch (e) {
    console.error("[BP] delete failed:", e);
    alert("Не удалось удалить");
  }
}

function onDrillCompany(id: string) {
  const co = state.companies.value.find((c) => c.company_id === id);
  drill.value = { mode: "company", companyId: id, companyName: co?.company_name_ru };
}

function onDrillKpi(metric: string) {
  drill.value = { mode: "kpi", metric };
}

function onDrillSector(code: string, label: string) {
  drill.value = { mode: "sector", sectorCode: code, sectorLabel: label };
}

function onDrillPnlLine(lineKey: string) {
  drill.value = { mode: "pnl-line", lineKey };
}

function onCommentSaved() {
  state.loadCompanyData();
}

onMounted(async () => {
  await state.loadCompanies();
  if (state.viewMode.value === "summary") await state.loadSummary(headlineMetricFor(lens.value));
  else await state.loadCompanyData();
});
</script>

<style scoped>
.bp-view { background: #f4f3f9; min-height: 100%; font-family: var(--font, system-ui); }

.bp-topbar {
  background: linear-gradient(95deg, #1E2A4A 0%, #2D3760 60%, #4B477E 100%);
  padding: 14px 22px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 18px;
  flex-wrap: wrap;
}

.bp-tb-eyebrow {
  font-size: 9.5px;
  font-weight: 600;
  letter-spacing: .1em;
  text-transform: uppercase;
  color: rgba(255, 255, 255, .55);
}
.bp-tb-title {
  font-size: 16px;
  font-weight: 600;
  color: #fff;
  margin-top: 2px;
  letter-spacing: -.005em;
}
.bp-tb-sub {
  font-size: 10.5px;
  color: rgba(255, 255, 255, .55);
  letter-spacing: .04em;
  margin-top: 2px;
}

.bp-tb-right { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }

.bp-toggle, .bp-pd-seg, .bp-yr-seg, .bp-lens {
  display: inline-flex;
  background: rgba(255, 255, 255, .12);
  border-radius: 8px;
  padding: 2px;
  gap: 0;
}
.bp-toggle button, .bp-pd-seg button, .bp-yr-seg button, .bp-lens button {
  background: transparent;
  border: none;
  font-size: 11px;
  font-weight: 600;
  color: rgba(255, 255, 255, .5);
  padding: 5px 14px;
  border-radius: 6px;
  cursor: pointer;
  transition: all .2s;
  font-family: inherit;
}
.bp-pd-seg button { padding: 4px 12px; font-size: 11px; }
.bp-yr-seg button { padding: 5px 11px; font-size: 11px; font-variant-numeric: tabular-nums; }
.bp-lens button { padding: 5px 11px; font-size: 11px; }

.bp-toggle button.on, .bp-pd-seg button.on, .bp-yr-seg button.on, .bp-lens button.on {
  background: rgba(255, 255, 255, .22);
  color: #fff;
  box-shadow: 0 1px 3px rgba(0, 0, 0, .18);
}
/* Lens — semantic colours for active state */
.bp-lens button.bp-lens-inc.on {
  background: rgba(29, 158, 117, .35);
  color: #ECFDF5;
}
.bp-lens button.bp-lens-exp.on {
  background: rgba(239, 159, 39, .35);
  color: #FEF3C7;
}

.bp-menu-wrap { position: relative; }
.bp-menu-btn {
  background: rgba(255, 255, 255, .12);
  border: none;
  width: 32px;
  height: 32px;
  border-radius: 8px;
  color: rgba(255, 255, 255, .8);
  font-size: 16px;
  font-weight: 600;
  cursor: pointer;
}
.bp-menu-btn:hover { background: rgba(255, 255, 255, .22); }
.bp-menu {
  position: absolute;
  top: 36px; right: 0;
  background: #fff;
  border-radius: 8px;
  box-shadow: 0 8px 24px rgba(15, 23, 60, .18);
  padding: 4px;
  display: flex;
  flex-direction: column;
  min-width: 200px;
  z-index: 10;
}
.bp-menu button {
  background: transparent;
  border: none;
  text-align: left;
  padding: 8px 12px;
  font-size: 11.5px;
  font-weight: 500;
  color: #1e2a4a;
  cursor: pointer;
  border-radius: 4px;
  font-family: inherit;
}
.bp-menu button:hover { background: rgba(127, 119, 221, .07); color: #7F77DD; }

.bp-co-picker {
  background: #fff;
  padding: 10px 22px;
  border-bottom: 1px solid rgba(15, 23, 60, .06);
}
.bp-co-select {
  font: inherit;
  font-size: 12px;
  font-weight: 500;
  padding: 6px 12px;
  border: 1px solid rgba(15, 23, 60, .12);
  border-radius: 6px;
  min-width: 360px;
  background: #fff;
  color: #1e2a4a;
  outline: none;
}
.bp-co-select:focus { border-color: #7F77DD; }

.bp-body { background: #f4f3f9; }

.bp-empty {
  padding: 60px 20px;
  text-align: center;
  color: rgba(15, 23, 60, .55);
  font-size: 13px;
}
.bp-err {
  margin: 16px 22px;
  padding: 12px 16px;
  background: rgba(226, 75, 74, .08);
  border-radius: 4px;
  color: #B91C1C;
  font-size: 12px;
  position: relative;
  overflow: hidden;
}
.bp-err::before {
  content: ""; position: absolute; top: 0; left: 0; right: 0;
  height: 3px; background: #E24B4A;
  border-top-left-radius: inherit; border-top-right-radius: inherit;
  animation: uzaStripeDrawIn .6s cubic-bezier(0.34, 1.2, 0.64, 1) both;
  transform-origin: left center;
  pointer-events: none;
}
</style>
