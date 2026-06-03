<template>
  <!-- 2026-05-26: убран outer <Transition mode=out-in> + :key=year — он
       полностью разрывал DOM на каждой смене года (unmount→mount). -->
  <div class="kpi-view">
    <!-- Top bar -->
    <div class="kpi-topbar">
      <div class="kpi-tb-left">
        <div class="kpi-tb-eyebrow">UzAssets · KPI</div>
        <div class="kpi-tb-title">{{ headerTitle }}</div>
        <div class="kpi-tb-sub">{{ headerSub }}</div>
      </div>
      <div class="kpi-tb-right">
        <!-- View toggle -->
        <div class="kpi-toggle">
          <button :class="{ on: state.viewMode.value === 'summary' }" @click="state.setViewMode('summary')">
            Сводка
          </button>
          <button :class="{ on: state.viewMode.value === 'company' }" @click="state.setViewMode('company')">
            По компании
          </button>
        </div>

        <!-- Period -->
        <div class="kpi-pd-seg">
          <button
            v-for="p in PERIODS"
            :key="p.key"
            :class="{ on: state.selectedPeriod.value === p.key }"
            @click="state.setPeriod(p.key)"
          >
            {{ p.label }}
          </button>
        </div>

        <!-- Year -->
        <div class="kpi-yr-seg">
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
        <div class="kpi-menu-wrap">
          <button class="kpi-menu-btn" @click="menuOpen = !menuOpen">⋯</button>
          <div v-if="menuOpen" class="kpi-menu" @click="menuOpen = false">
            <button v-if="canEdit" @click="openEditor">✎ Редактировать</button>
            <button v-if="canDelete" @click="confirmDelete">🗑 Удалить год</button>
          </div>
        </div>
      </div>
    </div>

    <!-- Company picker -->
    <div v-if="state.viewMode.value === 'company'" class="kpi-co-picker">
      <select
        :value="state.selectedCompanyId.value || ''"
        @change="onCompanyChange"
        class="kpi-co-select"
      >
        <option value="">— выберите компанию —</option>
        <option v-for="co in state.companies.value" :key="co.company_id" :value="co.company_id">
          {{ co.company_name_ru }}
        </option>
      </select>
    </div>

    <!-- Body -->
    <div class="kpi-body">
      <div v-if="state.error.value" class="kpi-err">{{ state.error.value }}</div>

      <!-- Summary -->
      <KpiSummaryDashboard
        v-if="state.viewMode.value === 'summary' && state.summary.value && state.summary.value.co_count > 0"
        :summary="state.summary.value"
        @open-company="onDrillCompany"
        @open-sector="onDrillSector"
      />
      <div v-else-if="state.viewMode.value === 'summary' && state.summary.value" class="kpi-empty">
        Нет данных KPI. Загрузите шаблон НГМК или заведите данные через редактор.
      </div>

      <!-- Company -->
      <KpiCompanyDashboard
        v-if="state.viewMode.value === 'company' && state.selectedCompany.value"
        :managers="state.managers.value"
        :active-manager-idx="state.selectedManagerIdx.value"
        :period="state.selectedPeriod.value"
        :company-id="state.selectedCompany.value.company_id"
        :company-name="state.selectedCompany.value.company_name_ru"
        :year="state.selectedYear.value"
        :can-edit="canEdit"
        @set-manager="state.setManager"
        @open-indicator="onIndicatorClick"
      />
      <div v-else-if="state.viewMode.value === 'company' && !state.selectedCompany.value" class="kpi-empty">
        Выберите компанию.
      </div>
    </div>

    <!-- Editor -->
    <KpiEditor
      v-if="editorOpen && state.selectedCompany.value"
      :company-id="state.selectedCompany.value.company_id"
      :company-name="state.selectedCompany.value.company_name_ru"
      :year="state.selectedYear.value"
      @close="editorOpen = false"
      @saved="onEditorSaved"
    />

    <!-- Drill -->
    <KpiDrillModal
      v-if="drill && state.summary.value"
      :mode="drill.mode"
      :status-key="drill.statusKey"
      :sector-code="drill.sectorCode"
      :sector-label="drill.sectorLabel"
      :summary="state.summary.value"
      @close="drill = null"
    />
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { kpiApi, type KpiStatus } from "@/api/bpKpi";
import { useKpiData } from "@/composables/useKpiData";
import KpiSummaryDashboard from "@/components/KPI/KpiSummaryDashboard.vue";
import KpiCompanyDashboard from "@/components/KPI/KpiCompanyDashboard.vue";
import KpiEditor from "@/components/KPI/KpiEditor.vue";
import KpiDrillModal from "@/components/KPI/KpiDrillModal.vue";
import { usePermissions } from "@/composables/usePermissions";

const _perm = usePermissions("kpi");
const canEdit = _perm.canEdit;
const canDelete = _perm.canDelete;

const state = useKpiData();
const menuOpen = ref(false);
const editorOpen = ref(false);

type DrillSpec = {
  mode: "status" | "sector";
  statusKey?: KpiStatus;
  sectorCode?: string;
  sectorLabel?: string;
};
const drill = ref<DrillSpec | null>(null);

// "Год" убрано 2026-05-23: fact_year заведён у <1% индикаторов,
// показывало 0.2%/97% (YTD-fallback) — misleading. Вернётся когда
// будут реальные годовые факты (декабрь — закрытие года).
const PERIODS = [
  { key: "q1" as const, label: "Q1" },
  { key: "q2" as const, label: "Q2" },
  { key: "q3" as const, label: "Q3" },
  { key: "q4" as const, label: "Q4" },
];

const headerTitle = computed(() =>
  state.viewMode.value === "summary"
    ? "Сводка по портфелю"
    : state.selectedCompany.value?.company_name_ru ?? "Выберите компанию",
);

const headerSub = computed(() => {
  const p = PERIODS.find((x) => x.key === state.selectedPeriod.value);
  if (state.viewMode.value === "summary" && state.summary.value) {
    return `FY ${state.selectedYear.value} · ${p?.label} · ${state.summary.value.co_count} компаний`;
  }
  return `FY ${state.selectedYear.value} · ${p?.label}`;
});

function onCompanyChange(e: Event) {
  state.setCompany((e.target as HTMLSelectElement).value || null);
}

function openEditor() {
  if (!state.selectedCompany.value) {
    alert("Сначала выберите компанию");
    return;
  }
  editorOpen.value = true;
}

async function onEditorSaved() {
  editorOpen.value = false;
  await state.loadCompanies();
  if (state.viewMode.value === "summary") await state.loadSummary();
  else await state.loadCompanyData();
}

async function confirmDelete() {
  if (!state.selectedCompany.value) {
    alert("Выберите компанию");
    return;
  }
  if (!confirm(`Удалить весь KPI ${state.selectedCompany.value.company_name_ru} за ${state.selectedYear.value}?`)) return;
  try {
    await kpiApi.deleteYear(state.selectedCompany.value.company_id, state.selectedYear.value);
    await state.loadCompanies();
    if (state.viewMode.value === "summary") await state.loadSummary();
    else await state.loadCompanyData();
  } catch (e) {
    console.error("[KPI] delete failed:", e);
    alert("Не удалось удалить");
  }
}

function onDrillCompany(id: string) {
  state.setCompany(id);
  state.setViewMode("company");
}

function onDrillSector(code: string, label: string) {
  drill.value = { mode: "sector", sectorCode: code, sectorLabel: label };
}

function onIndicatorClick(_id: string) {
  // Future: drill into indicator detail
}

onMounted(async () => {
  await state.loadCompanies();
  if (state.viewMode.value === "summary") await state.loadSummary();
  else await state.loadCompanyData();
});
</script>

<style scoped>
.kpi-view { background: #f4f3f9; min-height: 100%; font-family: var(--font, system-ui); }

.kpi-topbar {
  background: linear-gradient(95deg, #1E2A4A 0%, #2D3760 60%, #4B477E 100%);
  padding: 14px 22px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 18px;
  flex-wrap: wrap;
}

.kpi-tb-eyebrow {
  font-size: 9.5px;
  font-weight: 600;
  letter-spacing: .1em;
  text-transform: uppercase;
  color: rgba(255, 255, 255, .55);
}
.kpi-tb-title {
  font-size: 16px;
  font-weight: 600;
  color: #fff;
  margin-top: 2px;
  letter-spacing: -.005em;
}
.kpi-tb-sub {
  font-size: 10.5px;
  color: rgba(255, 255, 255, .55);
  letter-spacing: .04em;
  margin-top: 2px;
}

.kpi-tb-right { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }

.kpi-toggle, .kpi-pd-seg, .kpi-yr-seg {
  display: inline-flex;
  background: rgba(255, 255, 255, .12);
  border-radius: 8px;
  padding: 2px;
}
.kpi-toggle button, .kpi-pd-seg button, .kpi-yr-seg button {
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
.kpi-pd-seg button { padding: 4px 12px; font-size: 11px; }
.kpi-yr-seg button { padding: 5px 11px; font-size: 11px; font-variant-numeric: tabular-nums; }
.kpi-toggle button.on, .kpi-pd-seg button.on, .kpi-yr-seg button.on {
  background: rgba(255, 255, 255, .22);
  color: #fff;
  box-shadow: 0 1px 3px rgba(0, 0, 0, .18);
}

.kpi-menu-wrap { position: relative; }
.kpi-menu-btn {
  background: rgba(255, 255, 255, .12);
  border: none;
  width: 32px; height: 32px;
  border-radius: 8px;
  color: rgba(255, 255, 255, .8);
  font-size: 16px;
  font-weight: 600;
  cursor: pointer;
}
.kpi-menu-btn:hover { background: rgba(255, 255, 255, .22); }

.kpi-menu {
  position: absolute;
  top: 36px; right: 0;
  background: var(--bg1, #fff);
  border-radius: 8px;
  box-shadow: 0 8px 24px rgba(15, 23, 60, .18);
  padding: 4px;
  display: flex;
  flex-direction: column;
  min-width: 220px;
  z-index: 10;
}
.kpi-menu button {
  background: transparent;
  border: none;
  text-align: left;
  padding: 8px 12px;
  font-size: 11.5px;
  font-weight: 500;
  color: var(--t1, #1e2a4a);
  cursor: pointer;
  border-radius: 4px;
  font-family: inherit;
}
.kpi-menu button:hover { background: rgba(127, 119, 221, .07); color: #7F77DD; }

.kpi-co-picker {
  background: var(--bg1, #fff);
  padding: 10px 22px;
  border-bottom: 1px solid rgba(15, 23, 60, .06);
}
.kpi-co-select {
  font: inherit;
  font-size: 12px;
  font-weight: 500;
  padding: 6px 12px;
  border: 1px solid rgba(15, 23, 60, .12);
  border-radius: 6px;
  min-width: 360px;
  background: var(--bg1, #fff);
  color: var(--t1, #1e2a4a);
  outline: none;
}
.kpi-co-select:focus { border-color: #7F77DD; }

.kpi-body { background: #f4f3f9; }

.kpi-empty {
  padding: 60px 20px;
  text-align: center;
  color: rgba(15, 23, 60, .55);
  font-size: 13px;
}
.kpi-err {
  margin: 16px 22px;
  padding: 12px 16px;
  background: rgba(226, 75, 74, .08);
  border-radius: 4px;
  color: #B91C1C;
  font-size: 12px;
  position: relative;
  overflow: hidden;
}
.kpi-err::before {
  content: ""; position: absolute; top: 0; left: 0; right: 0;
  height: 3px; background: var(--sev-high);
  border-top-left-radius: inherit; border-top-right-radius: inherit;
  animation: uzaStripeDrawIn .6s var(--ease-standard) both;
  transform-origin: left center;
  pointer-events: none;
}
</style>
