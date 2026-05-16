<template>
  <Transition name="uza-fade" mode="out-in">
    <div :key="year">
  <div class="pa-view">
    <!-- Top bar -->
    <div class="pa-topbar">
      <div class="pa-tb-l">
        <div class="pa-tb-eyebrow">UzAssets · Закупки <span class="pa-beta">BETA</span></div>
        <div class="pa-tb-title">Анализ закупочной деятельности государственных компаний</div>
        <div class="pa-tb-sub">{{ headerSub }}</div>
      </div>

      <div class="pa-tb-r">
        <select :value="String(year || '')" @change="onYearChange" class="pa-in">
          <option value="">Все годы</option>
          <option v-for="y in (aggregate?.available_years || [])" :key="y" :value="y">{{ y }}</option>
        </select>

        <select :value="sectorCode || ''" @change="onSectorChange" class="pa-in">
          <option value="">Все сектора</option>
          <option v-for="s in (aggregate?.sectors || [])" :key="s.code" :value="s.code">{{ s.label }}</option>
        </select>
      </div>
    </div>

    <div v-if="loading && !aggregate" class="pa-loading">Загрузка анализа закупок...</div>
    <div v-else-if="error && !aggregate" class="pa-error">{{ error }}</div>

    <div v-else-if="aggregate" class="pa-body">
      <!-- KPI band -->
      <PaKpiBand
        :kpis="aggregate.kpis"
        :rating="aggregate.rating"
        @drill-leaders="onDrillLeaders"
        @drill-overpay="onDrillOverpay"
      />

      <!-- Empty state if no data -->
      <div v-if="!aggregate.rating.length" class="pa-no-data">
        <div class="pa-no-data-i">📊</div>
        <div class="pa-no-data-t">Нет данных по закупкам</div>
        <div class="pa-no-data-h">
          Импортируйте Excel с закупочными контрактами через раздел «Финансы» или загрузите данные в таблицу <code>procurement_closures</code>.
        </div>
      </div>

      <!-- Compare table -->
      <CategoryCompareTable
        v-else
        :rating="aggregate.rating"
        :categories="aggregate.categories"
        @drill-company="onDrillCompany"
      />
    </div>

    <!-- Drill modal -->
    <CompanyProfileModal
      v-if="drillCompany"
      :company="drillCompany"
      :categories="aggregate?.categories || []"
      :purchases="drillCompanyPurchases"
      :total-companies="aggregate?.rating.length || 0"
      @close="drillCompany = null"
      @drill-closure="onDrillClosure"
    />
  </div>
    </div>
  </Transition>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import {
  procurementAnalysisApi,
  type ClosureRow,
  type CompanyRatingRow,
  type ProcurementAggregate,
} from "@/api/procurement_analysis";
import PaKpiBand from "@/components/Procurement/PaKpiBand.vue";
import CategoryCompareTable from "@/components/Procurement/CategoryCompareTable.vue";
import CompanyProfileModal from "@/components/Procurement/CompanyProfileModal.vue";

const aggregate = ref<ProcurementAggregate | null>(null);
const year = ref<number | null>(null);
const sectorCode = ref<string | null>(null);
const loading = ref(false);
const error = ref<string | null>(null);

const drillCompany = ref<CompanyRatingRow | null>(null);

async function load() {
  loading.value = true;
  error.value = null;
  try {
    aggregate.value = await procurementAnalysisApi.getAggregate({
      year: year.value ?? undefined,
      sector_code: sectorCode.value ?? undefined,
    });
  } catch (e: unknown) {
    const err = e as { response?: { data?: { detail?: string } }; message?: string };
    error.value = err?.response?.data?.detail || err?.message || "Не удалось загрузить анализ";
  } finally {
    loading.value = false;
  }
}

function onYearChange(e: Event) {
  const v = (e.target as HTMLSelectElement).value;
  year.value = v ? parseInt(v, 10) : null;
  load();
}

function onSectorChange(e: Event) {
  sectorCode.value = (e.target as HTMLSelectElement).value || null;
  load();
}

function onDrillCompany(co: CompanyRatingRow) {
  drillCompany.value = co;
}

function onDrillLeaders() {
  // Future: filter rating to leaders only
}

function onDrillOverpay() {
  // Future: open overpay drill — e.g. CpDrillModal with summary
}

function onDrillClosure(closure: ClosureRow) {
  // Future: open product/closure drill
  console.log("[pa] drill closure:", closure.id);
}

const drillCompanyPurchases = computed<ClosureRow[]>(() => {
  if (!aggregate.value || !drillCompany.value) return [];
  return aggregate.value.purchases.filter((p) => p.company_id === drillCompany.value!.company_id);
});

const headerSub = computed(() => {
  if (!aggregate.value) return "";
  const k = aggregate.value.kpis;
  const parts: string[] = [];
  parts.push(year.value ? `FY ${year.value}` : "все годы");
  if (sectorCode.value) parts.push(`сектор ${sectorCode.value}`);
  parts.push(`${k.clean_companies} компаний с benchmark`);
  parts.push(`${k.clean_closures} чистых закупок`);
  return parts.join(" · ");
});

onMounted(load);
</script>

<style scoped>
.pa-view {
  background: #f4f3f9;
  min-height: 100%;
  font-family: var(--font, system-ui);
}

.pa-topbar {
  background: linear-gradient(95deg, #1E2A4A 0%, #2D3760 60%, #4B477E 100%);
  padding: 14px 22px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 18px;
  flex-wrap: wrap;
}

.pa-tb-eyebrow {
  font-size: 9.5px;
  font-weight: 600;
  letter-spacing: .1em;
  text-transform: uppercase;
  color: rgba(255, 255, 255, .55);
  display: flex;
  align-items: center;
  gap: 6px;
}
.pa-beta {
  background: rgba(239, 159, 39, .25);
  color: #FFD27A;
  padding: 1px 6px;
  border-radius: 3px;
  font-size: 8.5px;
  font-weight: 700;
  letter-spacing: .06em;
}
.pa-tb-title { font-size: 16px; font-weight: 600; color: #fff; margin-top: 2px; letter-spacing: -.005em; }
.pa-tb-sub { font-size: 10.5px; color: rgba(255, 255, 255, .55); letter-spacing: .04em; margin-top: 2px; }

.pa-tb-r { display: flex; gap: 8px; }

.pa-in {
  font: inherit;
  font-family: inherit;
  font-size: 11.5px;
  padding: 6px 10px;
  border: 1px solid rgba(255, 255, 255, .18);
  border-radius: 5px;
  background: rgba(255, 255, 255, .12);
  color: #fff;
  outline: none;
}
.pa-in option { background: #1e2a4a; color: #fff; }

.pa-loading, .pa-error {
  padding: 60px 22px;
  text-align: center;
  font-size: 13px;
  color: rgba(15, 23, 60, .55);
}
.pa-error { color: #E24B4A; }

.pa-body { padding: 18px 22px 24px; display: flex; flex-direction: column; gap: 14px; }

.pa-no-data {
  background: #fff;
  border-radius: 12px;
  padding: 60px 30px;
  text-align: center;
  border: 1px solid rgba(15, 23, 60, .06);
}
.pa-no-data-i { font-size: 36px; opacity: .35; }
.pa-no-data-t { font-size: 14px; font-weight: 500; margin-top: 8px; color: #1e2a4a; }
.pa-no-data-h { font-size: 11.5px; color: rgba(15, 23, 60, .55); margin-top: 4px; max-width: 480px; margin-left: auto; margin-right: auto; line-height: 1.55; }
.pa-no-data-h code { background: rgba(15, 23, 60, .05); padding: 1px 5px; border-radius: 3px; font-size: 10.5px; font-family: 'SF Mono', monospace; }
</style>
