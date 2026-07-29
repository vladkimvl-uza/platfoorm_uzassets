<template>
  <!-- 2026-05-26: убран outer <Transition mode=out-in> + :key=year — он
       полностью разрывал DOM (unmount → mount) на каждой смене года, что
       выглядело как «прыжок» страницы. Теперь reactive-обновление in-place,
       плавность даёт useNumberTween на цифрах + CSS transition на барах. -->
  <div class="bp-view">
    <!-- Top bar -->
    <div class="bp-topbar">
      <SidebarBurger />
      <div class="bp-tb-left">
        <div class="bp-tb-eyebrow">UzAssets · {{ t("Бизнес-план") }}</div>
        <div class="bp-tb-title">{{ headerTitle }}</div>
        <div class="bp-tb-sub">{{ headerSub }}</div>
      </div>
      <div class="bp-tb-right">
        <UzaSegment tone="dark" :options="TOPTAB_OPTS"
                    :model-value="topTab" @update:model-value="(v) => topTab = v as 'financial' | 'production'" />
        <template v-if="topTab === 'financial'">
        <!-- Единые чипы + дропдаун года (UzaSegment / UzaSelect) -->
        <UzaSegment tone="dark" :options="VIEW_OPTS"
                    :model-value="state.viewMode.value" @update:model-value="(v) => state.setViewMode(v as any)" />
        <UzaSegment tone="dark" :options="LENS_OPTS" v-model="lens" />
        <UzaSegment tone="dark" :options="periodOpts"
                    :model-value="state.selectedPeriod.value" @update:model-value="(v) => state.setPeriod(v as any)" />
        <UzaYearStepper tone="dark" :years="state.availableYears.value"
                        :model-value="state.selectedYear.value" @update:model-value="(v) => state.setYear(v)" />

        <!-- Menu -->
        <div class="bp-menu-wrap">
          <button class="bp-menu-btn" @click="menuOpen = !menuOpen">⋯</button>
          <div v-if="menuOpen" class="bp-menu" @click="menuOpen = false">
            <button v-if="canEdit" @click="openEditor">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 20h9"/><path d="M16.5 3.5a2.12 2.12 0 0 1 3 3L7 19l-4 1 1-4z"/></svg>
              {{ t("Редактировать") }}
            </button>
            <button v-if="canDelete" @click="confirmDelete">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="3 6 5 6 21 6"/><path d="M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6"/><path d="M10 11v6M14 11v6"/></svg>
              {{ t("Удалить год") }}
            </button>
          </div>
        </div>
        </template>
        <div class="bp-tb-ai">
          <BpAiAnalysis :companies="state.companies.value" :year="state.selectedYear.value"
                        :period="state.selectedPeriod.value" :selected-id="state.selectedCompanyId.value" />
        </div>
      </div>
    </div>

    <!-- Company picker (only for company mode) -->
    <div v-if="topTab === 'financial' && state.viewMode.value === 'company'" class="bp-co-picker">
      <select
        :value="state.selectedCompanyId.value || ''"
        @change="onCompanyChange"
        class="bp-co-select"
      >
        <option value="">{{ t("— выберите компанию —") }}</option>
        <option
          v-for="co in state.companies.value"
          :key="co.company_id"
          :value="co.company_id"
        >
          {{ co.company_name_ru }}
        </option>
      </select>
      <button v-if="canCreateCompany" class="bp-co-add" @click="addCompanyOpen = true" :title="t('Добавить новую компанию')">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg>
        {{ t("Компания") }}
      </button>
    </div>

    <!-- Body (финансовые показатели) -->
    <div v-if="topTab === 'financial'" class="bp-body">
      <div v-if="state.error.value" class="bp-err">
        {{ state.error.value }}
      </div>

      <!-- Summary mode -->
      <BpSummaryDashboard
        v-if="state.viewMode.value === 'summary' && state.summary.value && state.summary.value.co_count > 0"
        :summary="state.summary.value"
        :lens="lens"
        :loading="state.isLoadingSummary.value"
        @open-company="onDrillCompany"
        @open-kpi="onDrillKpi"
        @open-sector="onDrillSector"
        @open-pnl-line="onDrillPnlLine"
      />
      <!-- Загрузка сводки: скелетон вместо старого графика (stale не показываем) -->
      <div v-else-if="state.viewMode.value === 'summary' && state.isLoadingSummary.value" class="bp-sum-skel">
        <div class="bp-skel-row"><UzaSkeleton v-for="i in 4" :key="i" variant="block" height="132px" /></div>
        <div class="bp-skel-row bp-skel-row-bot">
          <UzaSkeleton variant="block" height="300px" />
          <UzaSkeleton variant="block" height="300px" />
          <UzaSkeleton variant="block" height="300px" />
        </div>
      </div>
      <div v-else-if="state.viewMode.value === 'summary' && state.summary.value && state.summary.value.co_count === 0" class="bp-empty uza-empty">
        {{ t("Нет данных бизнес-плана. Перейдите в режим «По компании» и заведите данные.") }}
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
      <div v-else-if="state.viewMode.value === 'company' && !state.selectedCompany.value" class="bp-empty uza-empty">
        {{ t("Выберите компанию для просмотра деталей.") }}
      </div>
    </div>

    <!-- Body (производственные показатели) -->
    <div v-else class="bp-prod-wrap">
      <BpProductionDashboard :key="prodReloadKey"
                             :can-import="canEdit"
                             @drill="prodDrill = $event"
                             @edit="prodEdit = $event" />
    </div>

    <!-- Production: drill -->
    <ProductionDrillModal v-if="prodDrill" :company="prodDrill.company"
      :year="prodDrill.year" :period="prodDrill.period"
      @close="prodDrill = null"
      @edit="() => { const d = prodDrill; prodDrill = null; if (d) prodEdit = d; }" />
    <!-- Production: editor -->
    <ProductionEditModal v-if="prodEdit" :company="prodEdit.company"
      :year="prodEdit.year" :period="prodEdit.period"
      @close="prodEdit = null"
      @saved="() => { prodEdit = null; prodReloadKey++; }" />

    <!-- Editor -->
    <BpEditor
      v-if="editorOpen && state.selectedCompany.value"
      :company-id="state.selectedCompany.value.company_id"
      :company-name="state.selectedCompany.value.company_name_ru"
      :year="state.selectedYear.value"
      :companies="state.companies.value"
      @switch-company="(id) => state.setCompany(id)"
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

    <!-- Новая компания -->
    <AddCompanyModal
      v-if="addCompanyOpen"
      @close="addCompanyOpen = false"
      @created="onCompanyCreated"
    />
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from "vue";
import { useRoute } from "vue-router";
import SidebarBurger from "@/components/SidebarBurger.vue";
import { useSavedFilter } from "@/composables/useSavedFilter";
import { useAiPageContext } from "@/composables/useAiPageContext";
import { BP_PERIODS, bpApi } from "@/api/bpKpi";
import { useBusinessPlanData } from "@/composables/useBusinessPlanData";
import { useToast } from "@/composables/useToast";
import { useConfirm } from "@/composables/useConfirm";
import BpSummaryDashboard from "@/components/BusinessPlan/BpSummaryDashboard.vue";
import UzaSkeleton from "@/components/UZA/UzaSkeleton.vue";
import BpCompanyDashboard from "@/components/BusinessPlan/BpCompanyDashboard.vue";
import BpEditor from "@/components/BusinessPlan/BpEditor.vue";
import BpDrillModal from "@/components/BusinessPlan/BpDrillModal.vue";
import AddCompanyModal from "@/components/AddCompanyModal.vue";
import UzaSegment from "@/components/UZA/UzaSegment.vue";
import UzaYearStepper from "@/components/UZA/UzaYearStepper.vue";
import BpProductionDashboard from "@/components/BusinessPlan/BpProductionDashboard.vue";
import ProductionDrillModal from "@/components/BusinessPlan/ProductionDrillModal.vue";
import ProductionEditModal from "@/components/BusinessPlan/ProductionEditModal.vue";
import BpAiAnalysis from "@/components/BusinessPlan/BpAiAnalysis.vue";
import type { ProdCompany } from "@/api/production";
import { usePermissions } from "@/composables/usePermissions";
import { useAuthStore } from "@/stores/auth";
import { useI18n } from "@/composables/useI18n";
import type { CompanyDetail } from "@/api/companies";

const perm = usePermissions("bp");
const canEdit = perm.canEdit;
const canDelete = perm.canDelete;

const auth = useAuthStore();
const canCreateCompany = computed(() => auth.hasPermission("companies.create"));

const { confirmDialog } = useConfirm();
const { t } = useI18n();

const state = useBusinessPlanData();
const menuOpen = ref(false);
const editorOpen = ref(false);
const addCompanyOpen = ref(false);

// ─── Верхний таб: Финансовые | Производственные показатели ───
const route = useRoute();
const topTab = ref<"financial" | "production">(route.query.tab === "production" ? "production" : "financial");
// computed, а не константа — labels через t() должны обновляться при смене языка
const TOPTAB_OPTS = computed(() => [
  { value: "financial", label: t("Финансовые") },
  { value: "production", label: t("Производственные") },
]);
const prodDrill = ref<{ company: ProdCompany; year: number; period: string } | null>(null);
const prodEdit = ref<{ company: ProdCompany; year: number; period: string } | null>(null);
const prodReloadKey = ref(0);

async function onCompanyCreated(co: CompanyDetail) {
  addCompanyOpen.value = false;
  await state.loadCompanies();
  const match = state.companies.value.find((c) => c.company_id === co.id);
  if (match) { await state.setViewMode("company"); await state.setCompany(co.id); }
}

// Top-level «lens» — passes down to summary + company dashboards. Опция «Все»
// убрана: только Доходы/Расходы. Дефолт — Доходы; сохранённый «all» мигрируем.
const lens = useSavedFilter<"all" | "income" | "expenses">("bp.lens", "income");
if (lens.value === "all") lens.value = "income";

// Опции единых чипов/дропдауна (UzaSegment/UzaSelect) — computed ради реактивной смены языка
const VIEW_OPTS = computed(() => [{ value: "summary", label: t("Сводка") }, { value: "company", label: t("По компании") }]);
const LENS_OPTS = computed(() => [
  { value: "income", label: t("Доходы"), dot: "#1D9E75" },
  { value: "expenses", label: t("Расходы"), dot: "#EF9F27" },
]);
const periodOpts = computed(() => BP_PERIODS.map((p) => ({ value: p.key, label: t(p.label) })));
const yearOpts = computed(() => state.availableYears.value.map((y) => ({ value: y, label: String(y) })));

// Pack 7.9e: AI Bubble context
useAiPageContext({
  key: "business-plan",
  label: t("Бизнес-план"),
  describeState: () => `Линза: ${lens.value === "all" ? "все статьи" : lens.value === "income" ? "только доходы" : "только расходы"}`,
  quickActions: [
    { label: t("План vs Факт по портфелю"),
      prompt: "Сравни план и факт BP по портфелю за текущий год. Где наибольшие отклонения? Используй get_business_plan для топ-3 компаний." },
    { label: t("Где провал?"),
      prompt: "Найди компании где выполнение BP сильно отстаёт от плана (< 80%). Объясни причины через комментарии. search_comments для контекста." },
    { label: t("Сравни 2025 vs 2026"),
      prompt: "Сравни BP по revenue 2025 vs 2026 — используй compare_companies(metric=task_completion_2026) + get_business_plan для деталей." },
    { label: t("Сводка расходов"),
      prompt: "Дай сводку портфельных расходов: топ статьи opExpenses/COGS/finCost по году. Где экономия, где перерасход?" },
  ],
});

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
    ? t("Сводка по портфелю")
    : state.selectedCompany.value?.company_name_ru ?? t("Выберите компанию"),
);

const headerSub = computed(() => {
  const p = BP_PERIODS.find((x) => x.key === state.selectedPeriod.value);
  // Квартальный срез показывает величины ЗА квартал (дельты YTD-хранения).
  const lbl = p?.key === "annual" ? t("годовой итог") : t("за квартал {q}", { q: p?.label });
  if (state.viewMode.value === "summary" && state.summary.value) {
    return t("FY {year} · {period} · {n} компаний · млрд сум", { year: state.selectedYear.value, period: lbl, n: state.summary.value.co_count });
  }
  return t("FY {year} · {period} · млрд сум", { year: state.selectedYear.value, period: lbl });
});

function onCompanyChange(e: Event) {
  state.setCompany((e.target as HTMLSelectElement).value || null);
}

function openEditor() {
  if (!state.selectedCompany.value) {
    useToast().info(t("Сначала выберите компанию в режиме «По компании»"));
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
    useToast().info(t("Выберите компанию"));
    return;
  }
  if (!(await confirmDialog({ message: t("Удалить весь бизнес-план {name} за {year}?", { name: state.selectedCompany.value.company_name_ru, year: state.selectedYear.value }), danger: true }))) return;
  try {
    await bpApi.deleteYear(state.selectedCompany.value.company_id, state.selectedYear.value);
    await state.loadCompanies();
    if (state.viewMode.value === "summary") await state.loadSummary(headlineMetricFor(lens.value));
    else await state.loadCompanyData();
  } catch (e) {
    console.error("[BP] delete failed:", e);
    useToast().error(t("Не удалось удалить"));
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
  gap: 14px;
  flex-wrap: wrap;
  /* Container-контекст: контролы реагируют на СВОЮ ширину (её меняет сайдбар),
     а не на ширину вьюпорта — из-за этого media-запросы раньше не срабатывали
     при развёрнутом сайдбаре. См. @container bptop ниже. */
  container-type: inline-size;
  container-name: bptop;
}
/* Заголовок растягивается → прижат к бургеру слева, контролы уезжают вправо;
   при нехватке места — переносятся в ряд 2 слева (без «лесенки»). */
.bp-tb-left { flex: 1 1 auto; min-width: 0; }

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

/* Один ряд контролов. flex-wrap: wrap — только сеть безопасности от overflow на
   экстремально узком/зуме; в норме компакт-режим (@container ниже) держит всё в
   одну строку. */
.bp-tb-right { display: flex; gap: 8px; row-gap: 10px; align-items: center; flex-wrap: wrap; justify-content: flex-end; min-width: 0; }
/* Кнопка «Анализ ИИ» — последним элементом у правого края (выравнивание даёт
   justify-content: flex-end), не сжимается. */
.bp-tb-ai { flex-shrink: 0; }

/* КОМПАКТ: когда СОБСТВЕННАЯ ширина топбара мала (узкое окно, развёрнутый
   сайдбар или зум) — прячем подписи групп (ВКЛАДКА/ВИД/…/ГОД) и ужимаем гэпы,
   чтобы контролы остались одной строкой без переноса и обрезки. Реагирует на
   ширину контейнера, поэтому работает при любом состоянии сайдбара. */
@container bptop (max-width: 1240px) {
  .bp-tb-right { gap: 6px; }
  .bp-tb-right :deep(.uza-seg-grp-l),
  .bp-tb-right :deep(.uza-ys-l) { display: none; }
}
/* Экстремально узко/сильный зум: компакта уже мало — при переносе выравниваем
   контролы по левому краю (аккуратнее правого «прижатия»). */
@container bptop (max-width: 640px) {
  .bp-tb-right { justify-content: flex-start; }
}

/* Скелетон сводки (загрузка/смена периода): вместо старого графика */
.bp-sum-skel { padding: 18px 22px; display: flex; flex-direction: column; gap: 12px; }
.bp-skel-row { display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px; }
.bp-skel-row-bot { grid-template-columns: 1.4fr 1fr 1fr; }
@media (max-width: 1100px) { .bp-skel-row, .bp-skel-row-bot { grid-template-columns: 1fr 1fr; } }

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
  background: var(--bg1, #fff);
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
  color: var(--t1, #1e2a4a);
  cursor: pointer;
  border-radius: 4px;
  font-family: inherit;
  display: flex; align-items: center; gap: 8px;
}
.bp-menu button svg { flex-shrink: 0; opacity: .75; }
.bp-menu button:hover { background: rgba(127, 119, 221, .07); color: #7F77DD; }

.bp-co-picker {
  background: var(--bg1, #fff);
  padding: 10px 22px;
  border-bottom: 1px solid rgba(15, 23, 60, .06);
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}
.bp-co-add {
  display: inline-flex; align-items: center; gap: 6px;
  font-size: 12px; font-weight: 500; font-family: inherit;
  color: var(--p-deep, #534AB7);
  background: rgba(127, 119, 221, .10);
  border: 1px solid rgba(127, 119, 221, .28);
  border-radius: 6px; padding: 6px 12px; cursor: pointer; white-space: nowrap;
  transition: background .14s, border-color .14s, transform .14s;
}
.bp-co-add:hover { background: rgba(127, 119, 221, .18); border-color: rgba(127, 119, 221, .45); transform: translateY(-1px); }
.bp-co-select {
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
  height: 3px; background: var(--sev-high);
  border-top-left-radius: inherit; border-top-right-radius: inherit;
  animation: uzaStripeDrawIn .6s var(--ease-standard) both;
  transform-origin: left center;
  pointer-events: none;
}
</style>
