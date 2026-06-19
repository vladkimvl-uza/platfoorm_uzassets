<template>
  <!-- 2026-05-26: убран outer <Transition mode=out-in> + :key=year — он
       полностью разрывал DOM на каждой смене года (unmount→mount). -->
  <div class="kpi-view">
    <!-- Top bar -->
    <div class="kpi-topbar">
      <SidebarBurger />
      <div class="kpi-tb-left">
        <div class="kpi-tb-eyebrow">UzAssets · KPI</div>
        <div class="kpi-tb-title">{{ headerTitle }}</div>
        <div class="kpi-tb-sub">{{ headerSub }}</div>
      </div>
      <div class="kpi-tb-right">
        <!-- Единые чипы + дропдаун года -->
        <UzaSegment tone="dark" label="Вид" :options="KPI_VIEW_OPTS"
                    :model-value="state.viewMode.value" @update:model-value="(v) => state.setViewMode(v as any)" />
        <UzaSegment tone="dark" label="Период" :options="kpiPeriodOpts"
                    :model-value="state.selectedPeriod.value" @update:model-value="(v) => state.setPeriod(v as any)" />
        <UzaSelect tone="dark" label="Год" :options="kpiYearOpts"
                   :model-value="state.selectedYear.value" @update:model-value="(v) => state.setYear(v as number)" />

        <!-- Menu -->
        <div class="kpi-menu-wrap">
          <button class="kpi-menu-btn" @click="menuOpen = !menuOpen">⋯</button>
          <div v-if="menuOpen" class="kpi-menu" @click="menuOpen = false">
            <button v-if="canEdit" @click="openEditor">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 20h9"/><path d="M16.5 3.5a2.12 2.12 0 0 1 3 3L7 19l-4 1 1-4z"/></svg>
              Редактировать
            </button>
            <button v-if="canDelete" @click="confirmDelete">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="3 6 5 6 21 6"/><path d="M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6"/><path d="M10 11v6M14 11v6"/></svg>
              Удалить год
            </button>
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
      <button v-if="canCreateCompany" class="kpi-co-add" @click="addCompanyOpen = true" title="Добавить новую компанию">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg>
        Компания
      </button>
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
        @open-status="onDrillStatus"
        @open-period="(q) => state.setPeriod(q)"
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

    <!-- Новая компания -->
    <AddCompanyModal
      v-if="addCompanyOpen"
      @close="addCompanyOpen = false"
      @created="onCompanyCreated"
    />
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import SidebarBurger from "@/components/SidebarBurger.vue";
import { kpiApi, type KpiStatus } from "@/api/bpKpi";
import { useKpiData } from "@/composables/useKpiData";
import KpiSummaryDashboard from "@/components/KPI/KpiSummaryDashboard.vue";
import KpiCompanyDashboard from "@/components/KPI/KpiCompanyDashboard.vue";
import KpiEditor from "@/components/KPI/KpiEditor.vue";
import KpiDrillModal from "@/components/KPI/KpiDrillModal.vue";
import AddCompanyModal from "@/components/AddCompanyModal.vue";
import UzaSegment from "@/components/UZA/UzaSegment.vue";
import UzaSelect from "@/components/UZA/UzaSelect.vue";
import { usePermissions } from "@/composables/usePermissions";
import { useToast } from "@/composables/useToast";
import { useConfirm } from "@/composables/useConfirm";
import { useAuthStore } from "@/stores/auth";
import type { CompanyDetail } from "@/api/companies";

const _perm = usePermissions("kpi");
const toast = useToast();
const { confirmDialog } = useConfirm();
const canEdit = _perm.canEdit;
const canDelete = _perm.canDelete;

const auth = useAuthStore();
const canCreateCompany = computed(() => auth.hasPermission("companies.create"));

const state = useKpiData();
const menuOpen = ref(false);
const editorOpen = ref(false);
const addCompanyOpen = ref(false);

async function onCompanyCreated(co: CompanyDetail) {
  addCompanyOpen.value = false;
  await state.loadCompanies();
  // выбрать только что созданную компанию
  const match = state.companies.value.find((c) => c.company_id === co.id);
  if (match) { state.setViewMode("company"); state.setCompany(co.id); }
}

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

// Опции единых фильтров
const KPI_VIEW_OPTS = [{ value: "summary", label: "Сводка" }, { value: "company", label: "По компании" }];
const kpiPeriodOpts = computed(() => PERIODS.map((p) => ({ value: p.key, label: p.label })));
const kpiYearOpts = computed(() => state.availableYears.value.map((y) => ({ value: y, label: String(y) })));

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
    toast.info("Сначала выберите компанию");
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
    toast.info("Выберите компанию");
    return;
  }
  if (!(await confirmDialog({
    message: `Удалить весь KPI ${state.selectedCompany.value.company_name_ru} за ${state.selectedYear.value}?`,
    danger: true,
  }))) return;
  try {
    await kpiApi.deleteYear(state.selectedCompany.value.company_id, state.selectedYear.value);
    await state.loadCompanies();
    if (state.viewMode.value === "summary") await state.loadSummary();
    else await state.loadCompanyData();
  } catch (e) {
    console.error("[KPI] delete failed:", e);
    toast.error("Не удалось удалить");
  }
}

function onDrillCompany(id: string) {
  state.setCompany(id);
  state.setViewMode("company");
}

function onDrillSector(code: string, label: string) {
  drill.value = { mode: "sector", sectorCode: code, sectorLabel: label };
}

function onDrillStatus(statusKey: KpiStatus) {
  drill.value = { mode: "status", statusKey };
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
  gap: 18px;
  flex-wrap: wrap;
}
/* Заголовок растягивается → прижат к бургеру слева, контролы уезжают вправо;
   при нехватке места — переносятся в ряд 2 слева (а не «в середину/вправо»). */
.kpi-tb-left { flex: 1 1 auto; min-width: 0; }

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
  display: flex; align-items: center; gap: 8px;
}
.kpi-menu button svg { flex-shrink: 0; opacity: .75; }
.kpi-menu button:hover { background: rgba(127, 119, 221, .07); color: #7F77DD; }

.kpi-co-picker {
  background: var(--bg1, #fff);
  padding: 10px 22px;
  border-bottom: 1px solid rgba(15, 23, 60, .06);
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}
.kpi-co-add {
  display: inline-flex; align-items: center; gap: 6px;
  font-size: 12px; font-weight: 500; font-family: inherit;
  color: var(--p-deep, #534AB7);
  background: rgba(127, 119, 221, .10);
  border: 1px solid rgba(127, 119, 221, .28);
  border-radius: 6px; padding: 6px 12px; cursor: pointer; white-space: nowrap;
  transition: background .14s, border-color .14s, transform .14s;
}
.kpi-co-add:hover { background: rgba(127, 119, 221, .18); border-color: rgba(127, 119, 221, .45); transform: translateY(-1px); }
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

/* ═══════════ MOBILE (Phase 2) ═══════════ */
@media (max-width: 768px) {
  .kpi-topbar { padding: 12px 14px; gap: 10px; }
  .kpi-tb-right { width: 100%; }
  .kpi-co-picker { padding: 8px 14px; }
  .kpi-co-select { min-width: 0; width: 100%; }
  /* клиренс под нижнюю навигацию */
  .kpi-view { padding-bottom: calc(58px + env(safe-area-inset-bottom)); }
}
</style>
