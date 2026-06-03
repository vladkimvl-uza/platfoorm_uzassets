<script setup lang="ts">
/**
 * Анализ закупочной деятельности государственных компаний —
 *
 * Topbar (dark navy):
 *   • Title «Анализ закупочной деятельности государственных компаний»
 *   • Decree badge (Р-59 dropdown — future-proof for F-60+)
 *   • Sector badge (всё / mining / oilgas / energy / transport / other)
 *   • Year badge (2024/2025/2026 from backend)
 *   • Quarter segmented (Q1/Q2/Q3/Q4) — UI hint; backend agg is annual
 *   • Tabs (Обзор / Сравнение / По категориям)
 *   • Fmt segmented (% / сум) — для Tornado deviation rendering
 *   • Edit menu (▤) — Import/Template/Edit/Export/Clear
 *
 * Tab "Overview"  → KpiBand + (Tornado | SidePanel) split
 * Tab "Compare"   → KpiBand + CategoryCompareTable
 * Tab "Category"  → KpiBand + PaCategoryGrid (15 categories accordion)
 *
 * (paCompute output). All sub-components (PaKpiBand, PaTornado, PaSidePanel,
 * PaCategoryGrid, CategoryCompareTable, CompanyProfileModal) exist.
 */
import { computed, onMounted, ref } from "vue";
import { useSavedFilter } from "@/composables/useSavedFilter";
import { usePermissions } from "@/composables/usePermissions";
const _perm = usePermissions("procurement_analysis");
import {
  procurementAnalysisApi,
  type ClosureRow,
  type CompanyRatingRow,
  type ProcurementAggregate,
} from "@/api/procurement_analysis";
import PaKpiBand from "@/components/Procurement/PaKpiBand.vue";
import PaTornado from "@/components/Procurement/PaTornado.vue";
import PaSidePanel from "@/components/Procurement/PaSidePanel.vue";
import PaCategoryGrid from "@/components/Procurement/PaCategoryGrid.vue";
import PaPainPoints from "@/components/Procurement/PaPainPoints.vue";
import PaLeaders from "@/components/Procurement/PaLeaders.vue";
import PaSupplierAudit from "@/components/Procurement/PaSupplierAudit.vue";
import CategoryCompareTable from "@/components/Procurement/CategoryCompareTable.vue";
import CompanyProfileModal from "@/components/Procurement/CompanyProfileModal.vue";
import PaKpiDrillModal, { type KpiDrillType } from "@/components/Procurement/PaKpiDrillModal.vue";
import PaPurchaseDrillModal from "@/components/Procurement/PaPurchaseDrillModal.vue";
import PaProductDrillModal from "@/components/Procurement/PaProductDrillModal.vue";
import PaEditTableModal from "@/components/Procurement/PaEditTableModal.vue";
import PaSupplierDrillModal from "@/components/Procurement/PaSupplierDrillModal.vue";
import { exportProcurementYear, downloadProcurementTemplate } from "@/utils/procurementExport";
import ForensicUploadModal from "@/components/Procurement/ForensicUploadModal.vue";
import { api } from "@/api/client";
import { useFormatters } from "@/composables/useFormatters";

const fmt = useFormatters();

// ─── State ───────────────────────────────────────────────────────
const aggregate = ref<ProcurementAggregate | null>(null);
const year = useSavedFilter<number | null>("procurement.year", null);
const sectorCode = useSavedFilter<string | null>("procurement.sectorCode", null);
const loading = ref(false);
const error = ref<string | null>(null);

type Tab = "overview" | "compare" | "by_category";
type Fmt = "pct" | "rub";
type Quarter = "Q1" | "Q2" | "Q3" | "Q4";
type Decree = "f59";

const tab = useSavedFilter<Tab>("procurement.tab", "overview");
const fmtMode = useSavedFilter<Fmt>("procurement.fmtMode", "pct");
const quarter = useSavedFilter<Quarter>("procurement.quarter", "Q1");
const decree = useSavedFilter<Decree>("procurement.decree", "f59");
const selectedCoId = useSavedFilter<string | null>("procurement.selectedCoId", null);
const compareTopN = useSavedFilter<"1" | "3" | "5" | "all">("procurement.compareTopN", "all");

const drillCompany = ref<CompanyRatingRow | null>(null);

// New drill modals (Phase 1)
const kpiDrillType = ref<KpiDrillType | null>(null);
const purchaseDrill = ref<ClosureRow | null>(null);
const productDrillCode = ref<string | null>(null);

// Phase 2 (2026-05-26): supplier drill
const supplierDrill = ref<{ key: string; name: string } | null>(null);
function onDrillSupplier(payload: { key: string; name: string }) {
  supplierDrill.value = payload;
}
function onSupplierSelectCompany(companyId: string) {
  supplierDrill.value = null;
  // Open the rewritten CompanyProfileModal for that company
  const co = aggregate.value?.rating.find(c => c.company_id === companyId) || null;
  drillCompany.value = co;
}

// Dropdown toggles
const decreeOpen = ref(false);
const sectorOpen = ref(false);
const yearOpen = ref(false);
const editMenuOpen = ref(false);

// Zoom card
type ZoomKey = "tornado" | "side" | "compare" | "category" | "pain" | "leaders" | "suppliers";
const zoomed = ref<ZoomKey | null>(null);
function toggleZoom(k: ZoomKey) { zoomed.value = zoomed.value === k ? null : k; }

function onDrillProduct(productCode: string) {
  productDrillCode.value = productCode;
}

function onPurchaseDrill(p: ClosureRow) {
  // Close KPI drill if open (chain drill)
  kpiDrillType.value = null;
  purchaseDrill.value = p;
  selectedCoId.value = p.company_id;
}

function onChainSelectCo(id: string) {
  kpiDrillType.value = null;
  purchaseDrill.value = null;
  selectedCoId.value = id;
}

const DECREE_META: Record<Decree, { label: string; full: string; beta: boolean }> = {
  f59: { label: "Р-59", full: "Распоряжение Президента №Ф-59 от 18.11.2025 — 15 категорий централизованных закупок госкомпаний", beta: true },
};

const SECTOR_META: Array<{ id: string; label: string; color: string }> = [
  { id: "mining",    label: "Горнодобывающий",     color: "#9B8EC4" },
  { id: "oilgas",    label: "Нефтегазовый",        color: "#1D9E75" },
  { id: "energy",    label: "Энергетика",          color: "#EF9F27" },
  { id: "transport", label: "Транспорт",           color: "#378ADD" },
  { id: "other",     label: "Другой сектор",       color: "#888780" },
];

const sectorMeta = computed(() =>
  sectorCode.value ? SECTOR_META.find(s => s.id === sectorCode.value) : null,
);
const sectorLabel = computed(() => sectorMeta.value?.label || "Все секторы");
const sectorColor = computed(() => sectorMeta.value?.color || "#FAC775");

// ─── Load ────────────────────────────────────────────────────────
async function load() {
  loading.value = true;
  error.value = null;
  try {
    aggregate.value = await procurementAnalysisApi.getAggregate({
      year: year.value ?? undefined,
      sector_code: sectorCode.value ?? undefined,
    });
    // Auto-pick first company for SidePanel if none selected
    if (!selectedCoId.value && aggregate.value?.rating?.length) {
      // null = show rating list, user opens profile via click
    }
  } catch (e: unknown) {
    const err = e as { response?: { data?: { detail?: string } }; message?: string };
    error.value = err?.response?.data?.detail || err?.message || "Не удалось загрузить анализ";
  } finally {
    loading.value = false;
  }
}

function setYear(v: number | null) {
  year.value = v;
  yearOpen.value = false;
  load();
}
function setSector(v: string | null) {
  sectorCode.value = v;
  sectorOpen.value = false;
  load();
}

function onDrillCompany(co: CompanyRatingRow) {
  drillCompany.value = co;
}
function onSelectCo(id: string | null) {
  selectedCoId.value = id;
}
function onDrillClosure(closure: ClosureRow) {
  // Future: open product/closure drill modal
  console.log("[pa] drill closure:", closure.id);
}
async function onDetailSaved() {
  await load();
}

const drillCompanyPurchases = computed<ClosureRow[]>(() => {
  if (!aggregate.value || !drillCompany.value) return [];
  return aggregate.value.purchases.filter(p => p.company_id === drillCompany.value!.company_id);
});

// Upload modal state
const showUploadModal = ref(false);
// Pack 7.9g: per-row edit table modal
const editTableOpen = ref(false);

function fmtPaUploadResult(data: unknown): string {
  const r = data as { inserted?: number; sheets_processed?: number; benchmark_rows?: number };
  return `Загружено: ${r?.inserted ?? "?"} закупок · ${r?.sheets_processed ?? "?"} листов · ${r?.benchmark_rows ?? "?"} с benchmark`;
}

function editAction(action: "import-price" | "template" | "edit" | "export" | "import-contracts" | "delete-contracts" | "clear") {
  editMenuOpen.value = false;
  switch (action) {
    case "import-contracts":
    case "import-price":
      showUploadModal.value = true;
      return;
    case "clear":
      if (window.confirm(`Удалить все закупки за ${year.value || "выбранный год"}? Это действие нельзя отменить.`)) {
        api.delete("/procurement/closures", {
          params: year.value
            ? { year: year.value, source: "manual-upload" }
            : { source: "manual-upload" },
        })
          .then(r => {
            const cleared = (r.data as { cleared?: number })?.cleared ?? 0;
            window.alert(`Удалено ${cleared} закупок (только manual-upload, сидовые q1-2026-xlsx сохранены).`);
            load();
          })
          .catch((e: { response?: { data?: { detail?: string } }; message?: string }) => {
            window.alert("Ошибка: " + (e?.response?.data?.detail || e?.message || "—"));
          });
      }
      return;
    case "delete-contracts":
      if (window.confirm("Удалить ВСЕ закупки за Q1 2026 (включая сид-данные)? Это действие нельзя отменить.")) {
        api.delete("/procurement/closures", { params: { year: 2026 } })
          .then(r => {
            const cleared = (r.data as { cleared?: number })?.cleared ?? 0;
            window.alert(`Удалено ${cleared} закупок.`);
            load();
          })
          .catch((e: { response?: { data?: { detail?: string } }; message?: string }) => {
            window.alert("Ошибка: " + (e?.response?.data?.detail || e?.message || "—"));
          });
      }
      return;
    case "template":
      downloadProcurementTemplate().catch((e) => {
        window.alert("Не удалось сгенерировать шаблон: " + (e?.message || "—"));
      });
      return;
    case "edit":
      if (!aggregate.value || !aggregate.value.purchases?.length) {
        window.alert("Нет загруженных закупок для редактирования.");
        return;
      }
      editTableOpen.value = true;
      return;
    case "export":
      exportProcurementYear(aggregate.value, year.value).catch((e) => {
        window.alert("Ошибка экспорта: " + (e?.message || "—"));
      });
      return;
  }
}

function closeAllDropdowns() {
  decreeOpen.value = false;
  sectorOpen.value = false;
  yearOpen.value = false;
  editMenuOpen.value = false;
}

onMounted(load);
</script>

<template>
  <!-- 2026-05-26: убран outer <Transition mode=out-in> + :key=composite —
       при смене tab/year/sector/quarter DOM полностью пересоздавался. -->
  <div class="pa-view" @click="closeAllDropdowns()">

        <!-- ═══ Topbar (dark navy) ═══ -->
        <div class="pa-topbar" @click.stop>
          <div class="pa-tb-l">
            <h1 class="pa-tb-title">
              Анализ закупочной деятельности государственных компаний
            </h1>
            <div class="pa-tb-sub" v-if="aggregate?.kpis">
              <span><b>{{ aggregate.kpis.total_companies }}</b> компаний</span>
              <span class="pa-dot">·</span>
              <span><b>{{ fmt.fmtNumber(aggregate.kpis.clean_closures) }}</b> закупок</span>
              <span class="pa-dot">·</span>
              <span>{{ year ? `FY ${year}` : 'все годы' }}</span>
              <span v-if="sectorCode" class="pa-dot">·</span>
              <span v-if="sectorCode">{{ sectorLabel }}</span>
            </div>
          </div>

          <div class="pa-tb-r" @click="closeAllDropdowns()">

            <!-- Decree badge -->
            <div class="pa-badge-wrap" @click.stop>
              <button class="pa-badge" @click="decreeOpen = !decreeOpen" :title="DECREE_META[decree].full">
                <svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="#FAC775" stroke-width="1.5">
                  <rect x="3" y="2" width="10" height="12" rx="1.5"/>
                  <path d="M5.5 6h5M5.5 9h5M5.5 11.5h3" stroke-linecap="round"/>
                </svg>
                <span style="color:#FAC775">{{ DECREE_META[decree].label }}</span>
                <svg class="pa-chev" width="10" height="10" viewBox="0 0 10 10" fill="none" stroke="#FAC775" stroke-width="1.6">
                  <path d="M2 4l3 3 3-3"/>
                </svg>
              </button>
              <div v-if="decreeOpen" class="pa-dd">
                <div class="pa-dd-item active" @click="decreeOpen = false">
                  {{ DECREE_META.f59.label }}
                  <span class="pa-beta">BETA</span>
                </div>
                <div class="pa-dd-item disabled">скоро · другие разделы</div>
              </div>
            </div>

            <!-- Sector badge -->
            <div class="pa-badge-wrap" @click.stop>
              <button class="pa-badge" @click="sectorOpen = !sectorOpen" title="Фильтр по сектору">
                <span class="pa-sec-icon" :style="{ background: sectorColor + '33', borderColor: sectorColor }"></span>
                <span :style="{ color: sectorColor }">{{ sectorLabel }}</span>
                <svg class="pa-chev" width="10" height="10" viewBox="0 0 10 10" fill="none" :stroke="sectorColor" stroke-width="1.6">
                  <path d="M2 4l3 3 3-3"/>
                </svg>
              </button>
              <div v-if="sectorOpen" class="pa-dd">
                <div class="pa-dd-item" :class="{ active: !sectorCode }" @click="setSector(null)">Все секторы</div>
                <div v-for="s in SECTOR_META" :key="s.id"
                     class="pa-dd-item" :class="{ active: sectorCode === s.id }"
                     @click="setSector(s.id)">
                  <span class="pa-sec-dot" :style="{ background: s.color }"></span>{{ s.label }}
                </div>
              </div>
            </div>

            <!-- Year badge -->
            <div class="pa-badge-wrap" @click.stop>
              <button class="pa-badge" @click="yearOpen = !yearOpen" title="Год">
                <svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="#FAC775" stroke-width="1.5">
                  <rect x="2" y="3" width="12" height="11" rx="1.5"/>
                  <path d="M2 7h12M5 1.5v3M11 1.5v3" stroke-linecap="round"/>
                </svg>
                <span style="color:#FAC775">{{ year || 'Все годы' }}</span>
                <svg class="pa-chev" width="10" height="10" viewBox="0 0 10 10" fill="none" stroke="#FAC775" stroke-width="1.6">
                  <path d="M2 4l3 3 3-3"/>
                </svg>
              </button>
              <div v-if="yearOpen" class="pa-dd">
                <div class="pa-dd-item" :class="{ active: !year }" @click="setYear(null)">Все годы</div>
                <div v-for="y in (aggregate?.available_years || [])" :key="y"
                     class="pa-dd-item" :class="{ active: year === y }"
                     @click="setYear(y)">{{ y }}</div>
              </div>
            </div>

            <!-- Quarter segmented -->
            <div class="pa-seg" title="Квартал">
              <button v-for="q in (['Q1','Q2','Q3','Q4'] as const)" :key="q"
                :class="{ on: quarter === q }" @click="quarter = q">{{ q }}</button>
            </div>

            <!-- Tabs -->
            <div class="pa-seg">
              <button :class="{ on: tab === 'overview' }"    @click="tab = 'overview'">Обзор</button>
              <button :class="{ on: tab === 'compare' }"     @click="tab = 'compare'">Сравнение</button>
              <button :class="{ on: tab === 'by_category' }" @click="tab = 'by_category'">По категориям</button>
            </div>

            <!-- Fmt toggle -->
            <div class="pa-seg">
              <button :class="{ on: fmtMode === 'pct' }" @click="fmtMode = 'pct'">%</button>
              <button :class="{ on: fmtMode === 'rub' }" @click="fmtMode = 'rub'">сум</button>
            </div>

            <!-- Edit menu (▤) — gated by permissions -->
            <div v-if="_perm.canEdit.value || _perm.canExport.value" class="pa-edit-wrap" @click.stop>
              <button class="pa-edit-btn" @click="editMenuOpen = !editMenuOpen" title="Действия">
                <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
                  <circle cx="8" cy="3"  r="1.4" fill="currentColor"/>
                  <circle cx="8" cy="8"  r="1.4" fill="currentColor"/>
                  <circle cx="8" cy="13" r="1.4" fill="currentColor"/>
                </svg>
              </button>
              <div v-if="editMenuOpen" class="pa-edit-menu">
                <button v-if="_perm.canEdit.value" @click="editAction('edit')"><span class="pa-em-ico"></span>Редактировать данные</button>
                <div v-if="_perm.canDelete.value" class="pa-em-sep"></div>
                <button v-if="_perm.canDelete.value" class="danger" @click="editAction('clear')"><span class="pa-em-ico">×</span>Очистить данные года</button>
              </div>
            </div>

          </div>
        </div>

        <!-- ═══ Body ═══ -->
        <div v-if="loading && !aggregate" class="pa-loading">Загрузка анализа закупок…</div>
        <div v-else-if="error && !aggregate" class="pa-error">⚠ {{ error }}</div>

        <div v-else-if="aggregate" class="pa-body">

          <!-- KPI band — always at top of every tab -->
          <PaKpiBand
            :kpis="aggregate.kpis"
            :rating="aggregate.rating"
            @drill-netpos="kpiDrillType = 'netpos'"
            @drill-overpay="kpiDrillType = 'overpay'"
            @drill-red="kpiDrillType = 'red'"
            @drill-above="kpiDrillType = 'above'"
          />

          <!-- Empty state -->
          <div v-if="!aggregate.rating.length" class="pa-empty-pane">
            <div class="pa-empty-icon">
              <svg width="48" height="48" viewBox="0 0 48 48" fill="none" stroke="#7F77DD" stroke-width="1.5">
                <rect x="8" y="10" width="32" height="32" rx="3"/>
                <path d="M8 18h32M16 4v8M32 4v8"/>
                <path d="M16 26h16M16 32h12"/>
              </svg>
            </div>
            <h3>Анализ закупок · нет данных за {{ year || 'выбранный год' }}</h3>
            <p v-if="year || sectorCode">
              Активные фильтры могут скрывать данные:
              <template v-if="year"><b>год {{ year }}</b></template>
              <template v-if="year && sectorCode">, </template>
              <template v-if="sectorCode"><b>сектор {{ sectorCode }}</b></template>.
              Попробуйте сбросить — возможно данные есть в других периодах.
            </p>
            <p v-else>
              Загрузите контракты Q1 2026 (8&nbsp;346 закупок · 22 SOE · benchmark по productCode)
              или прайс-лист Excel со средними ценами рынка для классического сравнения.
            </p>
            <div class="pa-empty-actions">
              <button
                v-if="year || sectorCode"
                class="pa-mf-btn primary"
                @click="year = null; sectorCode = null"
              >↻ Сбросить фильтры</button>
              <button class="pa-mf-btn" :class="{ primary: !year && !sectorCode }" @click="editAction('import-contracts')">↓ Импорт контрактов</button>
              <button class="pa-mf-btn" @click="editAction('import-price')">Импорт прайс-листа</button>
            </div>
          </div>

          <!-- ═══ TAB: OVERVIEW ═══ -->
          <template v-else-if="tab === 'overview'">
            <div class="pa-split">
              <!-- Tornado: top-9 over + top-6 under by deviation -->
              <div class="pa-card" :class="{ 'pa-zoomed': zoomed === 'tornado' }">
                <div class="pa-card-h">
                  <div class="pa-card-t-wrap">
                    <span class="pa-card-t">Топ закупок по отклонению от средней цены рынка</span>
                    <span class="pa-card-s">экономия ◀ │ ▶ переплата</span>
                  </div>
                  <button class="pa-zoom-btn" @click="toggleZoom('tornado')" :title="zoomed === 'tornado' ? 'Свернуть' : 'Развернуть'">
                    <svg v-if="zoomed !== 'tornado'" width="14" height="14" viewBox="0 0 16 16" fill="none">
                      <path d="M2 6V2h4M10 2h4v4M14 10v4h-4M6 14H2v-4"
                        stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/>
                    </svg>
                    <svg v-else width="14" height="14" viewBox="0 0 16 16" fill="none">
                      <path d="M6 2v4H2M10 6h4V2M10 14v-4h4M6 10H2v4"
                        stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/>
                    </svg>
                  </button>
                </div>
                <div class="pa-tornado-host">
                  <PaTornado
                    :data="aggregate"
                    :fmt="fmtMode"
                    @drill="onPurchaseDrill"
                    @select-co="onSelectCo"
                  />
                </div>
              </div>

              <!-- Side panel: Rating list ↔ Selected company Profile -->
              <div class="pa-card pa-side" :class="{ 'pa-zoomed': zoomed === 'side' }">
                <div class="pa-side-tabs">
                  <button class="pa-side-tab" :class="{ active: !selectedCoId }" @click="onSelectCo(null)">
                    Рейтинг компаний
                  </button>
                  <button class="pa-side-tab" :class="{ active: !!selectedCoId }"
                    @click="onSelectCo(selectedCoId || aggregate.rating[0]?.company_id || null)">
                    Профиль
                  </button>
                  <button class="pa-zoom-btn" style="margin-left:auto" @click="toggleZoom('side')" :title="zoomed === 'side' ? 'Свернуть' : 'Развернуть'">
                    <svg v-if="zoomed !== 'side'" width="14" height="14" viewBox="0 0 16 16" fill="none">
                      <path d="M2 6V2h4M10 2h4v4M14 10v4h-4M6 14H2v-4"
                        stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/>
                    </svg>
                    <svg v-else width="14" height="14" viewBox="0 0 16 16" fill="none">
                      <path d="M6 2v4H2M10 6h4V2M10 14v-4h4M6 10H2v4"
                        stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/>
                    </svg>
                  </button>
                </div>
                <PaSidePanel
                  :rating="aggregate.rating"
                  :categories="aggregate.categories"
                  :selected-co-id="selectedCoId"
                  @select-co="onSelectCo"
                />
              </div>
            </div>

            <!-- ─── Top-10 болевых товаров ─── -->
            <div class="pa-card" :class="{ 'pa-zoomed': zoomed === 'pain' }">
              <div class="pa-card-h">
                <div class="pa-card-t-wrap">
                  <span class="pa-card-t">Топ-10 болевых товаров портфеля</span>
                  <span class="pa-card-s">по абсолютной переплате · клик — все покупатели</span>
                </div>
                <button class="pa-zoom-btn" @click="toggleZoom('pain')" :title="zoomed === 'pain' ? 'Свернуть' : 'Развернуть'">
                  <svg v-if="zoomed !== 'pain'" width="14" height="14" viewBox="0 0 16 16" fill="none">
                    <path d="M2 6V2h4M10 2h4v4M14 10v4h-4M6 14H2v-4"
                      stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/>
                  </svg>
                  <svg v-else width="14" height="14" viewBox="0 0 16 16" fill="none">
                    <path d="M6 2v4H2M10 6h4V2M10 14v-4h4M6 10H2v4"
                      stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/>
                  </svg>
                </button>
              </div>
              <PaPainPoints
                :purchases="aggregate.purchases"
                @drill-product="onDrillProduct"
              />
            </div>

            <!-- ─── Лидеры + Поставщики (2-col bottom) ─── -->
            <div class="pa-bottom-grid">
              <div class="pa-card" :class="{ 'pa-zoomed': zoomed === 'leaders' }">
                <div class="pa-card-h">
                  <div class="pa-card-t-wrap">
                    <span class="pa-card-t">Лидеры портфеля</span>
                    <span class="pa-card-s">SOE с экономией · клик — профиль</span>
                  </div>
                  <button class="pa-zoom-btn" @click="toggleZoom('leaders')" :title="zoomed === 'leaders' ? 'Свернуть' : 'Развернуть'">
                    <svg v-if="zoomed !== 'leaders'" width="14" height="14" viewBox="0 0 16 16" fill="none">
                      <path d="M2 6V2h4M10 2h4v4M14 10v4h-4M6 14H2v-4"
                        stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/>
                    </svg>
                    <svg v-else width="14" height="14" viewBox="0 0 16 16" fill="none">
                      <path d="M6 2v4H2M10 6h4V2M10 14v-4h4M6 10H2v4"
                        stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/>
                    </svg>
                  </button>
                </div>
                <PaLeaders
                  :rating="aggregate.rating"
                  :purchases="aggregate.purchases"
                  :categories="aggregate.categories"
                  @select-co="onSelectCo"
                />
              </div>

              <div class="pa-card" :class="{ 'pa-zoomed': zoomed === 'suppliers' }">
                <div class="pa-card-h">
                  <div class="pa-card-t-wrap">
                    <span class="pa-card-t">Поставщики-overcharge</span>
                    <span class="pa-card-s">кандидаты на аудит</span>
                  </div>
                  <button class="pa-zoom-btn" @click="toggleZoom('suppliers')" :title="zoomed === 'suppliers' ? 'Свернуть' : 'Развернуть'">
                    <svg v-if="zoomed !== 'suppliers'" width="14" height="14" viewBox="0 0 16 16" fill="none">
                      <path d="M2 6V2h4M10 2h4v4M14 10v4h-4M6 14H2v-4"
                        stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/>
                    </svg>
                    <svg v-else width="14" height="14" viewBox="0 0 16 16" fill="none">
                      <path d="M6 2v4H2M10 6h4V2M10 14v-4h4M6 10H2v4"
                        stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/>
                    </svg>
                  </button>
                </div>
                <PaSupplierAudit :purchases="aggregate.purchases" @drill-supplier="onDrillSupplier" />
              </div>
            </div>
          </template>

          <!-- ═══ TAB: COMPARE ═══ -->
          <template v-else-if="tab === 'compare'">
            <div class="pa-card" :class="{ 'pa-zoomed': zoomed === 'compare' }">
              <div class="pa-card-h">
                <div class="pa-card-t-wrap">
                  <span class="pa-card-t">Сравнение цен по компаниям и категориям</span>
                  <span class="pa-card-s">отклонение от средней цены рынка</span>
                </div>
                <div class="pa-card-rt">
                  <div class="pa-seg pa-seg-light">
                    <span class="pa-seg-lbl">Топ</span>
                    <button v-for="n in (['1','3','5','all'] as const)" :key="n"
                      :class="{ on: compareTopN === n }" @click="compareTopN = n">
                      {{ n === 'all' ? 'все' : n }}
                    </button>
                  </div>
                  <button class="pa-zoom-btn" @click="toggleZoom('compare')" :title="zoomed === 'compare' ? 'Свернуть' : 'Развернуть'">
                    <svg v-if="zoomed !== 'compare'" width="14" height="14" viewBox="0 0 16 16" fill="none">
                      <path d="M2 6V2h4M10 2h4v4M14 10v4h-4M6 14H2v-4"
                        stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/>
                    </svg>
                    <svg v-else width="14" height="14" viewBox="0 0 16 16" fill="none">
                      <path d="M6 2v4H2M10 6h4V2M10 14v-4h4M6 10H2v4"
                        stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/>
                    </svg>
                  </button>
                </div>
              </div>
              <CategoryCompareTable
                :rating="aggregate.rating"
                :categories="aggregate.categories"
                @drill-company="onDrillCompany"
              />
            </div>
          </template>

          <!-- ═══ TAB: BY CATEGORY ═══ -->
          <template v-else-if="tab === 'by_category'">
            <div class="pa-card" :class="{ 'pa-zoomed': zoomed === 'category' }">
              <div class="pa-card-h">
                <div class="pa-card-t-wrap">
                  <span class="pa-card-t">15 категорий централизованных закупок</span>
                  <span class="pa-card-s">клик по строке — top-15 товаров · клик по товару — все покупатели</span>
                </div>
                <button class="pa-zoom-btn" @click="toggleZoom('category')" :title="zoomed === 'category' ? 'Свернуть' : 'Развернуть'">
                  <svg v-if="zoomed !== 'category'" width="14" height="14" viewBox="0 0 16 16" fill="none">
                    <path d="M2 6V2h4M10 2h4v4M14 10v4h-4M6 14H2v-4"
                      stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/>
                  </svg>
                  <svg v-else width="14" height="14" viewBox="0 0 16 16" fill="none">
                    <path d="M6 2v4H2M10 6h4V2M10 14v-4h4M6 10H2v4"
                      stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/>
                  </svg>
                </button>
              </div>
              <PaCategoryGrid
                :categories="aggregate.categories"
                :category-aggregates="aggregate.category_aggregates"
                :products-by-code="aggregate.products_by_code"
                :source="aggregate.meta?.source"
                :purchases="aggregate.purchases"
                @drill-closure="onPurchaseDrill"
                @drill-product="onDrillProduct"
              />
            </div>
          </template>

        </div>

        <!-- Per-company drill modal (existing) -->
        <CompanyProfileModal
          v-if="drillCompany"
          :company="drillCompany"
          :categories="aggregate?.categories || []"
          :purchases="drillCompanyPurchases"
          :total-companies="aggregate?.rating.length || 0"
          @close="drillCompany = null"
          @drill-closure="onPurchaseDrill"
        />

        <!-- KPI drill (Phase 1 new) -->
        <PaKpiDrillModal
          v-if="kpiDrillType && aggregate"
          :type="kpiDrillType"
          :data="aggregate"
          @close="kpiDrillType = null"
          @select-co="onChainSelectCo"
          @drill-purchase="onPurchaseDrill"
        />

        <!-- Purchase drill (Phase 1 new) -->
        <PaPurchaseDrillModal
          v-if="purchaseDrill && aggregate"
          :purchase="purchaseDrill"
          :data="aggregate"
          @close="purchaseDrill = null"
          @select-co="onChainSelectCo"
        />

        <!-- Product drill (Phase 1 new) -->
        <PaProductDrillModal
          v-if="productDrillCode && aggregate"
          :product-code="productDrillCode"
          :data="aggregate"
          @close="productDrillCode = null"
          @drill-purchase="onPurchaseDrill"
        />

        <!-- Supplier drill (Phase 2 — new) -->
        <PaSupplierDrillModal
          v-if="supplierDrill && aggregate"
          :supplier-key="supplierDrill.key"
          :supplier-name="supplierDrill.name"
          :purchases="aggregate.purchases"
          :companies="aggregate.rating"
          :categories="aggregate.categories"
          @close="supplierDrill = null"
          @drill-closure="(c: ClosureRow) => { supplierDrill = null; onPurchaseDrill(c); }"
          @select-company="onSupplierSelectCompany"
        />

        <!-- Bulk upload modal (xarid format, 22 sheets) -->
        <ForensicUploadModal
          v-if="showUploadModal"
          :year="year"
          endpoint="/procurement/closures/import-excel"
          title="Импорт закупок · Excel"
          description="Формат xarid_corporate_contracts: 22 листа (1 per SOE) или одиночный лист. Headers: lotId / organ / vendor / Unit price / amount / Category / productCode. Median per productCode → benchmark."
          :sheet-match="null"
          :format-result="fmtPaUploadResult"
          @close="showUploadModal = false"
          @uploaded="load"
        />

        <!-- Pack 7.9g: per-row edit table -->
        <PaEditTableModal
          v-model="editTableOpen"
          :rows="aggregate?.purchases || []"
          :year="year"
          :can-edit="_perm.canEdit.value"
          @saved="load"
        />
      </div>
</template>

<style scoped>
.pa-view {
  background: #f4f3f9;
  min-height: 100%;
  font-family: var(--font, system-ui);
}

@keyframes paFadeUp {
  0%   { opacity: 0; transform: translateY(6px); }
  100% { opacity: 1; transform: translateY(0); }
}
@keyframes paCardIn {
  0%   { opacity: 0; transform: translateY(10px) scale(.98); }
  60%  { opacity: 1; transform: translateY(-1px) scale(1.005); }
  100% { opacity: 1; transform: translateY(0) scale(1); }
}

/* ─── Topbar ─── */
.pa-topbar {
  background: linear-gradient(95deg, #1E2A4A 0%, #2D3760 60%, #4B477E 100%);
  padding: 12px 22px;
  display: flex; align-items: center; justify-content: space-between;
  gap: 12px; flex-wrap: wrap;
}
.pa-tb-l { display: flex; flex-direction: column; gap: 2px; min-width: 0; flex: 1; }
.pa-tb-title {
  font-size: 16px; font-weight: 600; color: #fff; margin: 0;
  letter-spacing: -.005em;
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
}
.pa-tb-sub {
  font-size: 11px; color: rgba(255, 255, 255, .55);
  display: flex; align-items: center; gap: 6px;
}
.pa-tb-sub b { color: rgba(255, 255, 255, .95); font-weight: 600; }
.pa-dot { opacity: .4; }
.pa-tb-r {
  display: flex; align-items: center; gap: 6px;
  flex-wrap: wrap;
}

.pa-badge-wrap { position: relative; }
.pa-badge {
  display: flex; align-items: center; gap: 6px;
  background: rgba(255, 255, 255, .08);
  border: 1px solid rgba(255, 255, 255, .15);
  color: #fff;
  padding: 5px 10px;
  border-radius: 8px;
  font-size: 11.5px; font-weight: 500;
  cursor: pointer;
  font-family: inherit;
  transition: background .12s;
}
.pa-badge:hover { background: rgba(255, 255, 255, .15); }
.pa-chev { transition: transform .15s; flex-shrink: 0; }
.pa-sec-icon {
  width: 12px; height: 12px;
  border-radius: 3px;
  border: 1px solid;
  flex-shrink: 0;
}
.pa-dd {
  position: absolute; top: calc(100% + 4px); right: 0;
  background: var(--bg1, #fff);
  border: 1px solid rgba(0, 0, 0, .08);
  border-radius: 8px;
  box-shadow: 0 12px 32px rgba(15, 23, 60, .14);
  min-width: 220px;
  padding: 4px;
  z-index: 100;
  animation: paFadeUp .15s ease;
}
.pa-dd-item {
  padding: 7px 10px;
  border-radius: 5px;
  font-size: 12px;
  color: var(--t1, #1E2A4A);
  cursor: pointer;
  display: flex; align-items: center; gap: 6px;
  transition: background .1s;
}
.pa-dd-item:hover { background: #F4F3F9; }
.pa-dd-item.active { background: rgba(127, 119, 221, .12); color: var(--p-deep); font-weight: 600; }
.pa-dd-item.disabled { opacity: .45; cursor: default; font-style: italic; font-size: 11px; }
.pa-dd-item.disabled:hover { background: transparent; }
.pa-sec-dot { width: 8px; height: 8px; border-radius: 2px; flex-shrink: 0; }
.pa-beta {
  display: inline-block;
  background: rgba(239, 159, 39, .25); color: #B07415;
  font-size: 8px; font-weight: 700;
  padding: 1px 4px;
  border-radius: 3px;
  letter-spacing: .04em;
  margin-left: auto;
}

/* Segmented (works in both dark topbar & light body) */
.pa-seg {
  display: inline-flex;
  background: rgba(255, 255, 255, .10);
  border-radius: 7px;
  padding: 2px;
}
.pa-seg button {
  background: transparent; border: 0;
  font-size: 11px; padding: 4px 10px;
  border-radius: 5px;
  color: rgba(255, 255, 255, .65);
  cursor: pointer;
  font-family: inherit; font-weight: 500;
  transition: all .12s;
}
.pa-seg button:hover { color: #fff; }
.pa-seg button.on {
  background: var(--bg1, #fff); color: var(--t1, #1E2A4A);
  box-shadow: 0 1px 3px rgba(0, 0, 0, .12);
}
.pa-seg-light {
  background: rgba(0, 0, 0, .04);
}
.pa-seg-light button { color: var(--t3, var(--t-muted)); }
.pa-seg-light button:hover { color: var(--t1, #1E2A4A); }
.pa-seg-light button.on { box-shadow: 0 1px 3px rgba(0, 0, 0, .08); }
.pa-seg-lbl {
  font-size: 10px; color: var(--t3, var(--t-muted));
  padding: 0 6px 0 4px;
  align-self: center;
  letter-spacing: .04em;
  text-transform: uppercase;
  font-weight: 600;
}

/* Edit menu (▤) */
.pa-edit-wrap { position: relative; }
.pa-edit-btn {
  background: rgba(255, 255, 255, .12);
  border: 1px solid rgba(255, 255, 255, .15);
  color: #fff;
  width: 32px; height: 32px;
  border-radius: 8px;
  cursor: pointer;
  display: flex; align-items: center; justify-content: center;
  transition: background .15s;
}
.pa-edit-btn:hover { background: rgba(255, 255, 255, .2); }
.pa-edit-menu {
  position: absolute; top: 38px; right: 0;
  background: var(--bg1, #fff);
  border: 1px solid rgba(0, 0, 0, .08);
  border-radius: 10px;
  box-shadow: 0 12px 32px rgba(15, 23, 60, .14);
  min-width: 240px;
  padding: 6px;
  z-index: 100;
  animation: paFadeUp .15s ease;
}
.pa-edit-menu button {
  display: flex; align-items: center; gap: 8px;
  width: 100%;
  background: transparent; border: 0;
  padding: 8px 10px;
  border-radius: 6px;
  font-size: 12.5px;
  text-align: left;
  cursor: pointer;
  font-family: inherit;
  color: var(--t1, #1E2A4A);
  transition: background .12s;
}
.pa-edit-menu button:hover { background: #F4F3F9; }
.pa-edit-menu button.danger { color: var(--sev-critical); }
.pa-edit-menu button.danger:hover { background: rgba(226, 75, 74, .08); }
.pa-em-ico { width: 14px; text-align: center; color: var(--t3, var(--t-muted)); font-weight: 600; }
.pa-em-sep { height: 1px; background: rgba(0, 0, 0, .06); margin: 4px 0; }

/* ─── States ─── */
.pa-loading, .pa-error { padding: 60px 22px; text-align: center; color: rgba(15, 23, 60, .55); font-size: 13px; }
.pa-error { color: var(--sev-high); }

.pa-body {
  padding: 16px 20px 24px;
  display: flex; flex-direction: column;
  gap: 14px;
}

/* ─── Empty state ─── */
.pa-empty-pane {
  background: var(--bg1, #fff);
  border-radius: 12px;
  padding: 50px 30px;
  text-align: center;
  border: 1px solid rgba(15, 23, 60, .06);
}
.pa-empty-icon { opacity: .8; margin-bottom: 12px; display: flex; justify-content: center; }
.pa-empty-pane h3 {
  font-size: 14px; font-weight: 600; color: var(--t1, #1E2A4A);
  margin: 0 0 8px;
}
.pa-empty-pane p {
  font-size: 12px; color: rgba(15, 23, 60, .55);
  max-width: 540px; margin: 0 auto 16px;
  line-height: 1.55;
}
.pa-empty-actions { display: inline-flex; gap: 8px; flex-wrap: wrap; justify-content: center; }
.pa-mf-btn {
  font-size: 12px; font-weight: 500;
  padding: 7px 14px;
  border-radius: 7px;
  border: 1px solid rgba(15, 23, 60, .12);
  background: var(--bg1, #fff);
  color: var(--t1, #1E2A4A);
  cursor: pointer;
  font-family: inherit;
  transition: all .12s;
}
.pa-mf-btn:hover { background: #F4F3F9; }
.pa-mf-btn.primary {
  background: #7F77DD; color: #fff;
  border-color: #7F77DD;
}
.pa-mf-btn.primary:hover { background: #6F66D0; }

.pa-card {
  background: var(--bg1, #fff);
  border: 1px solid rgba(0, 0, 0, .05);
  border-radius: 12px;
  padding: 14px 16px;
  animation: paCardIn .5s var(--ease-standard) both;
}
.pa-card-h {
  display: flex; align-items: center; justify-content: space-between;
  gap: 8px; margin-bottom: 10px;
  flex-wrap: wrap;
}
.pa-card-t-wrap {
  display: flex; align-items: baseline; gap: 8px; flex-wrap: wrap;
  min-width: 0; flex: 1;
}
.pa-card-t { font-size: 13px; font-weight: 600; color: var(--t1, #1E2A4A); }
.pa-card-s { font-size: 11px; color: var(--t3, var(--t-muted)); font-weight: 500; }
.pa-card-rt { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }

/* Zoom card overlay (mirrors Governance gv-zoomed) */
.pa-zoom-btn {
  background: transparent; border: 0;
  width: 26px; height: 26px;
  border-radius: 6px;
  display: flex; align-items: center; justify-content: center;
  color: var(--t3, var(--t-muted));
  cursor: pointer;
  transition: background .15s, color .15s;
  flex-shrink: 0;
}
.pa-zoom-btn:hover { background: #F4F3F9; color: var(--t1, #1E2A4A); }
.pa-zoomed {
  position: fixed !important;
  inset: 24px !important;
  z-index: 200 !important;
  background: var(--bg1, #fff) !important;
  box-shadow: 0 24px 64px rgba(15, 23, 60, .25) !important;
  margin: 0 !important;
  overflow: auto !important;
  display: flex; flex-direction: column;
}

/* Overview split: Tornado (left, wider) + Side panel (right) */
.pa-split {
  display: grid;
  grid-template-columns: minmax(0, 2fr) minmax(0, 1fr);
  gap: 12px;
}
@media (max-width: 1100px) { .pa-split { grid-template-columns: 1fr; } }

/* Overview bottom: Leaders + Suppliers side-by-side */
.pa-bottom-grid {
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(0, 1fr);
  gap: 12px;
}
@media (max-width: 1100px) { .pa-bottom-grid { grid-template-columns: 1fr; } }

.pa-tornado-host { min-height: 360px; position: relative; }

/* Side panel */
.pa-side { display: flex; flex-direction: column; padding: 0; }
.pa-side-tabs {
  display: flex; align-items: center; gap: 2px;
  padding: 10px 12px 0;
  border-bottom: 0.5px solid rgba(0, 0, 0, .06);
}
.pa-side-tab {
  background: transparent; border: 0;
  font-size: 12px; font-weight: 500;
  padding: 8px 12px;
  color: var(--t3, var(--t-muted));
  border-bottom: 2px solid transparent;
  cursor: pointer;
  font-family: inherit;
  margin-bottom: -1px;
  transition: color .12s, border-color .12s;
}
.pa-side-tab:hover { color: var(--t1, #1E2A4A); }
.pa-side-tab.active {
  color: var(--p-deep);
  border-bottom-color: #7F77DD;
}
</style>
