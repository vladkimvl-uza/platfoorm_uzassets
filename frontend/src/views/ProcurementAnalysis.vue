<script setup lang="ts">
/**
 * Анализ закупочной деятельности государственных компаний — премиум-редизайн.
 *
 * 5 линз (вкладок):
 *   • Обзор          — KPI band + авто red-flags + ГЕРОЙ (торнадо компаний | рейтинг) + болевые товары
 *   • Поставщики     — топ / сквозные / дорогие + концентрация (HHI)
 *   • Способы·Площадки — разрез по purchase_type + платформам + «без торга»
 *   • Товары·Услуги  — ценовой бенчмарк по productCode + потенц. экономия (PRODUCT/SERVICE) + 15 категорий
 *   • Сравнение      — таблица компания×категория
 *
 * Backend `/procurement/aggregate` отдаёт KPI (лот-дедуплицированные деньги),
 * rating, products_by_code, suppliers_*, supplier_concentration, methods, platforms.
 * Все drill-модалки и редактор «Заключения центра экспертизы» сохранены.
 */
import { computed, onMounted, ref } from "vue";
import SidebarBurger from "@/components/SidebarBurger.vue";
import { useSavedFilter } from "@/composables/useSavedFilter";
import { usePermissions } from "@/composables/usePermissions";
import { useToast } from "@/composables/useToast";
import { useConfirm } from "@/composables/useConfirm";
const _perm = usePermissions("procurement_analysis");
const toast = useToast();
const { confirmDialog } = useConfirm();
import {
  procurementAnalysisApi,
  paFmtMoneyShort,
  type ClosureRow,
  type CompanyRatingRow,
  type ProcurementAggregate,
  type SupplierAgg,
} from "@/api/procurement_analysis";
import PaTornado from "@/components/Procurement/PaTornado.vue";
import PaWorksServicesChart from "@/components/Procurement/PaWorksServicesChart.vue";
import PaSidePanel from "@/components/Procurement/PaSidePanel.vue";
import PaCategoryGrid from "@/components/Procurement/PaCategoryGrid.vue";
import PaPainPoints from "@/components/Procurement/PaPainPoints.vue";
import CategoryCompareTable from "@/components/Procurement/CategoryCompareTable.vue";
import PaSuppliersPanel from "@/components/Procurement/PaSuppliersPanel.vue";
import PaMethodsPanel from "@/components/Procurement/PaMethodsPanel.vue";
import PaProductsPanel from "@/components/Procurement/PaProductsPanel.vue";
import CompanyProfileModal from "@/components/Procurement/CompanyProfileModal.vue";
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

type Tab = "overview" | "suppliers" | "methods" | "products" | "compare";
type Fmt = "pct" | "rub";

const tab = useSavedFilter<Tab>("procurement.tab2", "overview");
const fmtMode = useSavedFilter<Fmt>("procurement.fmtMode", "pct");
const selectedCoId = useSavedFilter<string | null>("procurement.selectedCoId", null);

const TABS: Array<{ id: Tab; label: string }> = [
  { id: "overview", label: "Обзор" },
  { id: "suppliers", label: "Поставщики" },
  { id: "methods", label: "Способы · Площадки" },
  { id: "products", label: "Товары · Услуги · Работы" },
  { id: "compare", label: "Сравнение" },
];

// drill modals
const drillCompany = ref<CompanyRatingRow | null>(null);
const purchaseDrill = ref<ClosureRow | null>(null);
const productDrillCode = ref<string | null>(null);
const supplierDrill = ref<{ key: string; name: string } | null>(null);

// dropdowns
const sectorOpen = ref(false);
const yearOpen = ref(false);
const editMenuOpen = ref(false);

// zoom (hero tornado only — единая кнопка)
const heroZoom = ref(false);

// Режим герой-торнадо: товары (отклонение цен) / услуги / работы (расход по компаниям).
// Услуги и работы несравнимы по цене за единицу → ранжируем по расходу.
type HeroMode = "products" | "services" | "works";
const heroMode = useSavedFilter<HeroMode>("procurement.heroMode", "products");
const heroTitle = computed(() =>
  heroMode.value === "products" ? "Рейтинг компаний по отклонению цен от рынка"
  : heroMode.value === "services" ? "Расход на услуги по компаниям"
  : "Расход на работы по компаниям");
const heroSub = computed(() =>
  heroMode.value === "products" ? "экономия ◀ │ ▶ переплата · клик — детализация"
  : "цена за условную единицу несравнима — ранжируем по расходу · клик — профиль");

function onDrillProduct(code: string) { productDrillCode.value = code; }
function onDrillSupplier(s: SupplierAgg) {
  // key = отображаемое имя; PaSupplierDrillModal нормализует обе стороны при матче
  supplierDrill.value = { key: s.supplier_name, name: s.supplier_name };
}
function onSupplierSelectCompany(companyId: string) {
  supplierDrill.value = null;
  drillCompany.value = aggregate.value?.rating.find(c => c.company_id === companyId) || null;
}
function onPanelSelectCompany(companyId: string) {
  drillCompany.value = aggregate.value?.rating.find(c => c.company_id === companyId) || null;
}
function onPurchaseDrill(p: ClosureRow) {
  purchaseDrill.value = p;
  selectedCoId.value = p.company_id;
}
function onChainSelectCo(id: string) {
  purchaseDrill.value = null;
  selectedCoId.value = id;
}
function onDrillCompany(co: CompanyRatingRow) { drillCompany.value = co; }
function onSelectCo(id: string | null) { selectedCoId.value = id; }
// Клик по торнадо → детализация: открываем профиль компании в модалке.
function onTornadoSelectCo(id: string) {
  const co = aggregate.value?.rating.find(c => c.company_id === id) || null;
  if (co) drillCompany.value = co;
}

// Заключение центра экспертизы — патчим строку реактивно
function onConclusionUpdated(p: {
  id: string; conclusion_text: string | null; conclusion_status: string | null;
  conclusion_date: string | null; conclusion_author_name: string | null;
}) {
  const apply = (row: ClosureRow | null | undefined) => {
    if (!row || row.id !== p.id) return;
    row.conclusion_text = p.conclusion_text;
    row.conclusion_status = p.conclusion_status;
    row.conclusion_date = p.conclusion_date;
    row.conclusion_author_name = p.conclusion_author_name;
  };
  apply(aggregate.value?.purchases.find(r => r.id === p.id));
  apply(purchaseDrill.value);
}

const SECTOR_META: Array<{ id: string; label: string; color: string }> = [
  { id: "mining",    label: "Горно-металлургический", color: "#9B8EC4" },
  { id: "oilgas",    label: "Нефтегазовый",           color: "#1D9E75" },
  { id: "energy",    label: "Энергетика",             color: "#EF9F27" },
  { id: "transport", label: "Транспорт и связь",      color: "#378ADD" },
  { id: "chemistry", label: "Химия",                  color: "#7F77DD" },
  { id: "other",     label: "Прочие",                 color: "#888780" },
];
const sectorMeta = computed(() => sectorCode.value ? SECTOR_META.find(s => s.id === sectorCode.value) : null);
const sectorLabel = computed(() => sectorMeta.value?.label || "Все секторы");
const sectorColor = computed(() => sectorMeta.value?.color || "#FAC775");

const k = computed(() => aggregate.value?.kpis ?? null);

// ─── Premium KPI band ─────────────────────────────────────────────
type KpiCard = {
  id: string; eyebrow: string; value: string; sub: string;
  accent: string; tab?: Tab; bar?: number; barColor?: string; hint?: string;
};
const kpiCards = computed<KpiCard[]>(() => {
  const kp = k.value;
  if (!kp) return [];
  return [
    {
      id: "spend", eyebrow: "Совокупный расход",
      value: paFmtMoneyShort(kp.total_spend),
      sub: `${fmt.fmtNumber(kp.total_lots)} уникальных лотов · ${kp.total_companies} компаний`,
      accent: "#7F77DD",
    },
    {
      id: "potential", eyebrow: "Потенциал экономии",
      value: paFmtMoneyShort(kp.potential_saving_uzs),
      sub: "только товары · к лучшей сопоставимой цене",
      accent: "#5DC093", tab: "products",
      hint: "Если бы товары закупались по лучшей достигнутой среди компаний цене (в полосе сопоставимости). Услуги, работы и несопоставимые «грязные» коды (разные товары под одним кодом) НЕ учитываются.",
    },
    {
      id: "notender", eyebrow: "Без конкурентной процедуры",
      value: kp.no_tender_pct.toFixed(0) + "%",
      sub: `${paFmtMoneyShort(kp.no_tender_spend)} · каталог/e-shop`,
      accent: "#E2807F", tab: "methods",
      bar: kp.no_tender_pct, barColor: "#E2807F",
      hint: `Доля спенда через НЕКОНКУРЕНТНЫЕ методы (электронный магазин/каталог), где торга нет по определению. Отдельно: ${kp.competitive_no_saving_pct.toFixed(0)}% (${paFmtMoneyShort(kp.competitive_no_saving_spend)}) — конкурентные процедуры, закрывшиеся с НУЛЕВОЙ экономией (возможная имитация торга).`,
    },
    {
      id: "suppliers", eyebrow: "Поставщиков",
      value: fmt.fmtNumber(kp.supplier_count),
      sub: `${kp.disclosed_supplier_pct.toFixed(0)}% спенда раскрыто`,
      accent: "#EFB373", tab: "suppliers",
    },
    {
      id: "split", eyebrow: "Товары / Услуги / Работы",
      value: `${(100 - kp.services_pct - kp.works_pct).toFixed(0)}/${kp.services_pct.toFixed(0)}/${kp.works_pct.toFixed(0)}%`,
      sub: `${paFmtMoneyShort(kp.goods_spend)} · ${paFmtMoneyShort(kp.services_spend)} · ${paFmtMoneyShort(kp.works_spend)}`,
      accent: "#378ADD", tab: "products",
      bar: 100 - kp.services_pct - kp.works_pct, barColor: "#93D3B0",
    },
  ];
});

// ─── Авто red-flags ──────────────────────────────────────────────
type RedFlag = { id: string; title: string; detail: string; tone: "red" | "amber"; tab?: Tab };
const redFlags = computed<RedFlag[]>(() => {
  const a = aggregate.value;
  if (!a) return [];
  const out: RedFlag[] = [];
  const exp = a.suppliers_expensive?.[0];
  if (exp && exp.excess_uzs > 0) {
    out.push({
      id: "exp", tone: "red", tab: "suppliers",
      title: `${exp.supplier_name}: цена +${exp.premium_pct.toFixed(0)}% к рынку`,
      detail: `переплата ${paFmtMoneyShort(exp.excess_uzs)} · ${exp.company_count} компани${exp.company_count === 1 ? "я" : "й"}`,
    });
  }
  const cat = (a.methods || []).find(m => !m.is_competitive && m.spend > 0 && m.saved_rate_pct < 0.5);
  if (cat) {
    out.push({
      id: "cat", tone: "amber", tab: "methods",
      title: `${cat.label}: экономия 0%`,
      detail: `${paFmtMoneyShort(cat.spend)} закуплено без торга по каталогу`,
    });
  }
  // Главный сигнал качества торгов: конкурентные процедуры с нулевой экономией
  // (имитация конкуренции). «Без конкурентной процедуры» (каталог) — норма, не флаг.
  if (a.kpis && a.kpis.competitive_no_saving_pct >= 30) {
    out.push({
      id: "cns", tone: "amber", tab: "methods",
      title: `${a.kpis.competitive_no_saving_pct.toFixed(0)}% спенда: конкурентные процедуры без экономии`,
      detail: `${paFmtMoneyShort(a.kpis.competitive_no_saving_spend)} — торг состоялся, но эффект нулевой (возможна имитация)`,
    });
  }
  // Концентрация: нераскрытый «поставщик» — это один контракт без раскрытия, а не
  // зависимость от вендора → отдельная формулировка (прозрачность), тон amber.
  const conc = (a.supplier_concentration || []).find(c => c.top1_pct >= 60);
  if (conc) {
    const undisclosed = !conc.top1_name || conc.top1_name === "(не указан)";
    out.push(undisclosed ? {
      id: "conc", tone: "amber", tab: "suppliers",
      title: `${conc.company_name}: ${conc.top1_pct.toFixed(0)}% спенда в одном нераскрытом контракте`,
      detail: `поставщик не раскрыт — требуется проверка прозрачности`,
    } : {
      id: "conc", tone: "red", tab: "suppliers",
      title: `${conc.company_name}: ${conc.top1_pct.toFixed(0)}% закупок у одного поставщика`,
      detail: `${conc.top1_name} · индекс концентрации HHI ${Math.round(conc.hhi)}`,
    });
  }
  return out.slice(0, 4);
});

const drillCompanyPurchases = computed<ClosureRow[]>(() => {
  if (!aggregate.value || !drillCompany.value) return [];
  return aggregate.value.purchases.filter(p => p.company_id === drillCompany.value!.company_id);
});

// ─── Load ────────────────────────────────────────────────────────
async function load() {
  loading.value = true;
  error.value = null;
  try {
    aggregate.value = await procurementAnalysisApi.getAggregate({
      year: year.value ?? undefined,
      sector_code: sectorCode.value ?? undefined,
    });
    // Данные только за Q1 2026 — авто-выбор единственного года, чтобы в топбаре
    // отображался чип «2026 · Q1», а не «Все годы».
    if (year.value == null && aggregate.value?.available_years?.length) {
      year.value = Math.max(...aggregate.value.available_years);
    }
  } catch (e: unknown) {
    const err = e as { response?: { data?: { detail?: string } }; message?: string };
    error.value = err?.response?.data?.detail || err?.message || "Не удалось загрузить анализ";
  } finally {
    loading.value = false;
  }
}
function setYear(v: number | null) { year.value = v; yearOpen.value = false; load(); }
function setSector(v: string | null) { sectorCode.value = v; sectorOpen.value = false; load(); }

// upload / edit
const showUploadModal = ref(false);
const editTableOpen = ref(false);
function fmtPaUploadResult(data: unknown): string {
  const r = data as { inserted?: number; sheets_processed?: number; benchmark_rows?: number };
  return `Загружено: ${r?.inserted ?? "?"} закупок · ${r?.sheets_processed ?? "?"} листов · ${r?.benchmark_rows ?? "?"} с benchmark`;
}
async function editAction(action: "import-contracts" | "template" | "edit" | "export" | "clear") {
  editMenuOpen.value = false;
  switch (action) {
    case "import-contracts":
      showUploadModal.value = true; return;
    case "template":
      downloadProcurementTemplate().catch((e) => toast.error("Не удалось сгенерировать шаблон: " + (e?.message || "—")));
      return;
    case "edit":
      if (!aggregate.value?.purchases?.length) { toast.info("Нет загруженных закупок для редактирования."); return; }
      editTableOpen.value = true; return;
    case "export":
      exportProcurementYear(aggregate.value, year.value).catch((e) => toast.error("Ошибка экспорта: " + (e?.message || "—")));
      return;
    case "clear":
      if (await confirmDialog({ message: `Удалить загруженные вручную закупки за ${year.value || "выбранный год"}? Сидовые данные сохранятся.`, danger: true })) {
        api.delete("/procurement/closures", { params: year.value ? { year: year.value, source: "manual-upload" } : { source: "manual-upload" } })
          .then(r => { const c = (r.data as { cleared?: number })?.cleared ?? 0; toast.success(`Удалено ${c} закупок (manual-upload).`); load(); })
          .catch((e: { response?: { data?: { detail?: string } }; message?: string }) => toast.error("Ошибка: " + (e?.response?.data?.detail || e?.message || "—")));
      }
      return;
  }
}
function closeAllDropdowns() { sectorOpen.value = false; yearOpen.value = false; editMenuOpen.value = false; }

onMounted(load);
</script>

<template>
  <div class="pa-view" @click="closeAllDropdowns()">

    <!-- ═══ Topbar ═══ -->
    <div class="pa-topbar" @click.stop>
      <SidebarBurger />
      <div class="pa-tb-l">
        <h1 class="pa-tb-title">Анализ закупочной деятельности государственных компаний</h1>
        <div class="pa-tb-sub" v-if="k">
          <span><b>{{ k.total_companies }}</b> компаний</span>
          <span class="pa-dot">·</span>
          <span><b>{{ fmt.fmtNumber(k.total_lots) }}</b> уник. лотов</span>
          <span class="pa-dot">·</span>
          <span><b>{{ paFmtMoneyShort(k.total_spend) }}</b></span>
          <span class="pa-dot">·</span>
          <span>{{ year ? `${year} · Q1` : 'все годы' }}</span>
          <span v-if="sectorCode" class="pa-dot">·</span>
          <span v-if="sectorCode">{{ sectorLabel }}</span>
        </div>
      </div>

      <div class="pa-tb-r" @click="closeAllDropdowns()">
        <!-- Sector -->
        <div class="pa-badge-wrap" @click.stop>
          <button class="pa-badge" @click="sectorOpen = !sectorOpen" title="Фильтр по сектору">
            <span class="pa-sec-icon" :style="{ background: sectorColor + '33', borderColor: sectorColor }"></span>
            <span :style="{ color: sectorColor }">{{ sectorLabel }}</span>
            <svg class="pa-chev" width="10" height="10" viewBox="0 0 10 10" fill="none" :stroke="sectorColor" stroke-width="1.6"><path d="M2 4l3 3 3-3"/></svg>
          </button>
          <div v-if="sectorOpen" class="pa-dd">
            <div class="pa-dd-item" :class="{ active: !sectorCode }" @click="setSector(null)">Все секторы</div>
            <div v-for="s in SECTOR_META" :key="s.id" class="pa-dd-item" :class="{ active: sectorCode === s.id }" @click="setSector(s.id)">
              <span class="pa-sec-dot" :style="{ background: s.color }"></span>{{ s.label }}
            </div>
          </div>
        </div>

        <!-- Year -->
        <div class="pa-badge-wrap" @click.stop>
          <button class="pa-badge" @click="yearOpen = !yearOpen" title="Год">
            <svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="#FAC775" stroke-width="1.5"><rect x="2" y="3" width="12" height="11" rx="1.5"/><path d="M2 7h12M5 1.5v3M11 1.5v3" stroke-linecap="round"/></svg>
            <span style="color:#FAC775">{{ year ? `${year} · Q1` : 'Все годы' }}</span>
            <svg class="pa-chev" width="10" height="10" viewBox="0 0 10 10" fill="none" stroke="#FAC775" stroke-width="1.6"><path d="M2 4l3 3 3-3"/></svg>
          </button>
          <div v-if="yearOpen" class="pa-dd">
            <div class="pa-dd-item" :class="{ active: !year }" @click="setYear(null)">Все годы</div>
            <div v-for="y in (aggregate?.available_years || [])" :key="y" class="pa-dd-item" :class="{ active: year === y }" @click="setYear(y)">{{ y }}</div>
          </div>
        </div>

        <!-- Edit menu -->
        <div v-if="_perm.canEdit.value || _perm.canExport.value" class="pa-edit-wrap" @click.stop>
          <button class="pa-edit-btn" @click="editMenuOpen = !editMenuOpen" title="Действия">
            <svg width="16" height="16" viewBox="0 0 16 16" fill="none"><circle cx="8" cy="3" r="1.4" fill="currentColor"/><circle cx="8" cy="8" r="1.4" fill="currentColor"/><circle cx="8" cy="13" r="1.4" fill="currentColor"/></svg>
          </button>
          <div v-if="editMenuOpen" class="pa-edit-menu">
            <button v-if="_perm.canEdit.value" @click="editAction('import-contracts')"><span class="pa-em-ico">↓</span>Импорт контрактов</button>
            <button v-if="_perm.canExport.value" @click="editAction('export')"><span class="pa-em-ico">↑</span>Экспорт в Excel</button>
            <button v-if="_perm.canEdit.value" @click="editAction('template')"><span class="pa-em-ico">▤</span>Шаблон импорта</button>
            <button v-if="_perm.canEdit.value" @click="editAction('edit')"><span class="pa-em-ico">✎</span>Редактировать данные</button>
            <div v-if="_perm.canDelete.value" class="pa-em-sep"></div>
            <button v-if="_perm.canDelete.value" class="danger" @click="editAction('clear')"><span class="pa-em-ico">×</span>Очистить загруженное</button>
          </div>
        </div>
      </div>
    </div>

    <!-- ═══ Tabs strip ═══ -->
    <div class="pa-tabstrip" @click.stop>
      <button v-for="t in TABS" :key="t.id" class="pa-tab" :class="{ on: tab === t.id }" @click="tab = t.id">{{ t.label }}</button>
    </div>

    <!-- ═══ States ═══ -->
    <div v-if="loading && !aggregate" class="pa-body">
      <div class="pa-kpi-band">
        <div v-for="i in 5" :key="i" class="pa-kpi pa-skel-card"><div class="pa-skel pa-skel-sm"></div><div class="pa-skel pa-skel-lg"></div><div class="pa-skel pa-skel-md"></div></div>
      </div>
      <div class="pa-card pa-skel-card" style="height:380px"></div>
    </div>
    <div v-else-if="error && !aggregate" class="pa-state pa-state-err">
      <svg width="34" height="34" viewBox="0 0 24 24" fill="none" stroke="#E2807F" stroke-width="1.6"><circle cx="12" cy="12" r="9"/><path d="M12 7v6M12 16.5v.01" stroke-linecap="round"/></svg>
      <p>{{ error }}</p>
      <button class="pa-mf-btn primary" @click="load()">Повторить</button>
    </div>

    <div v-else-if="aggregate" class="pa-body">
      <!-- ── KPI band ── -->
      <div class="pa-kpi-band">
        <button v-for="(c, i) in kpiCards" :key="c.id" class="pa-kpi" :class="{ clickable: !!c.tab }"
          :style="{ '--accent': c.accent, '--i': i }" :title="c.hint || undefined" @click="c.tab && (tab = c.tab)">
          <span class="pa-kpi-eyebrow">{{ c.eyebrow }}<span v-if="c.hint" class="pa-kpi-info" title="">ⓘ</span></span>
          <span class="pa-kpi-value">{{ c.value }}</span>
          <span class="pa-kpi-sub">{{ c.sub }}</span>
          <span v-if="c.bar != null" class="pa-kpi-track"><span class="pa-kpi-fill" :style="{ width: Math.min(100, c.bar) + '%', background: c.barColor }"></span></span>
        </button>
      </div>

      <!-- Empty -->
      <div v-if="!aggregate.rating.length" class="pa-empty-pane">
        <div class="pa-empty-icon">
          <svg width="48" height="48" viewBox="0 0 48 48" fill="none" stroke="#7F77DD" stroke-width="1.5"><rect x="8" y="10" width="32" height="32" rx="3"/><path d="M8 18h32M16 4v8M32 4v8"/><path d="M16 26h16M16 32h12"/></svg>
        </div>
        <h3>Анализ закупок · нет данных за {{ year || 'выбранный год' }}</h3>
        <p v-if="year || sectorCode">Активные фильтры могут скрывать данные. Попробуйте сбросить.</p>
        <p v-else>Загрузите контракты Q1 2026 (xarid, 22 листа) или прайс-лист Excel.</p>
        <div class="pa-empty-actions">
          <button v-if="year || sectorCode" class="pa-mf-btn primary" @click="year = null; sectorCode = null; load()">↻ Сбросить фильтры</button>
          <button v-if="_perm.canEdit.value" class="pa-mf-btn" :class="{ primary: !year && !sectorCode }" @click="editAction('import-contracts')">↓ Импорт контрактов</button>
        </div>
      </div>

      <template v-else>
        <Transition name="pa-fade" mode="out-in">
          <!-- ═══ ОБЗОР ═══ -->
          <div :key="tab" v-if="tab === 'overview'" class="pa-tabpane">
            <!-- Red flags -->
            <div v-if="redFlags.length" class="pa-flags">
              <button v-for="(f, i) in redFlags" :key="f.id" class="pa-flag" :class="`tone-${f.tone}`" :style="{ '--i': i }" @click="f.tab && (tab = f.tab)">
                <span class="pa-flag-dot"></span>
                <span class="pa-flag-body"><span class="pa-flag-title">{{ f.title }}</span><span class="pa-flag-detail">{{ f.detail }}</span></span>
                <svg class="pa-flag-arr" width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.6"><path d="M6 3l5 5-5 5" stroke-linecap="round" stroke-linejoin="round"/></svg>
              </button>
            </div>

            <!-- HERO: tornado (companies) | rating side panel -->
            <div class="pa-split">
              <div class="pa-card" :class="{ 'pa-zoomed': heroZoom }">
                <div class="pa-card-h">
                  <div class="pa-card-t-wrap">
                    <span class="pa-card-t">{{ heroTitle }}</span>
                    <span class="pa-card-s">{{ heroSub }}</span>
                  </div>
                  <div class="pa-card-rt">
                    <div class="pa-seg pa-seg-light">
                      <button :class="{ on: heroMode === 'products' }" @click="heroMode = 'products'">Товары</button>
                      <button :class="{ on: heroMode === 'services' }" @click="heroMode = 'services'">Услуги</button>
                      <button :class="{ on: heroMode === 'works' }" @click="heroMode = 'works'">Работы</button>
                    </div>
                    <div v-if="heroMode === 'products'" class="pa-seg pa-seg-light">
                      <button :class="{ on: fmtMode === 'pct' }" @click="fmtMode = 'pct'">%</button>
                      <button :class="{ on: fmtMode === 'rub' }" @click="fmtMode = 'rub'">сум</button>
                    </div>
                    <button class="pa-zoom-btn" @click="heroZoom = !heroZoom" :title="heroZoom ? 'Свернуть' : 'Развернуть'">
                      <svg v-if="!heroZoom" width="14" height="14" viewBox="0 0 16 16" fill="none"><path d="M2 6V2h4M10 2h4v4M14 10v4h-4M6 14H2v-4" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/></svg>
                      <svg v-else width="14" height="14" viewBox="0 0 16 16" fill="none"><path d="M6 2v4H2M10 6h4V2M10 14v-4h4M6 10H2v4" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/></svg>
                    </button>
                  </div>
                </div>
                <div class="pa-tornado-host">
                  <PaTornado v-if="heroMode === 'products'" :data="aggregate" :fmt="fmtMode" @drill="onPurchaseDrill" @select-co="onTornadoSelectCo" />
                  <PaWorksServicesChart v-else :items="aggregate.works_services" :mode="heroMode === 'works' ? 'works' : 'services'" @select-company="onTornadoSelectCo" />
                </div>
              </div>

              <div class="pa-card pa-side">
                <div class="pa-side-tabs">
                  <button class="pa-side-tab" :class="{ active: !selectedCoId }" @click="onSelectCo(null)">Рейтинг компаний</button>
                  <button class="pa-side-tab" :class="{ active: !!selectedCoId }" @click="onSelectCo(selectedCoId || aggregate.rating[0]?.company_id || null)">Профиль</button>
                </div>
                <PaSidePanel :rating="aggregate.rating" :categories="aggregate.categories" :selected-co-id="selectedCoId" @select-co="onSelectCo" />
              </div>
            </div>

            <!-- Pain points -->
            <div class="pa-card">
              <div class="pa-card-h"><div class="pa-card-t-wrap"><span class="pa-card-t">Топ болевых товаров портфеля</span><span class="pa-card-s">по потенциалу экономии · клик — все покупатели</span></div></div>
              <PaPainPoints :products-by-code="aggregate.products_by_code" @drill-product="onDrillProduct" />
            </div>
          </div>

          <!-- ═══ ПОСТАВЩИКИ ═══ -->
          <div :key="tab" v-else-if="tab === 'suppliers'" class="pa-tabpane">
            <PaSuppliersPanel :data="aggregate" @drill-supplier="onDrillSupplier" @select-company="onPanelSelectCompany" />
          </div>

          <!-- ═══ СПОСОБЫ · ПЛОЩАДКИ ═══ -->
          <div :key="tab" v-else-if="tab === 'methods'" class="pa-tabpane">
            <PaMethodsPanel :data="aggregate" />
          </div>

          <!-- ═══ ТОВАРЫ · УСЛУГИ ═══ -->
          <div :key="tab" v-else-if="tab === 'products'" class="pa-tabpane">
            <PaProductsPanel :data="aggregate" @drill-product="onDrillProduct" @select-company="onPanelSelectCompany" />
            <div class="pa-card">
              <div class="pa-card-h"><div class="pa-card-t-wrap"><span class="pa-card-t">15 категорий централизованных закупок</span><span class="pa-card-s">клик по строке — top-товары · клик по товару — все покупатели</span></div></div>
              <PaCategoryGrid :categories="aggregate.categories" :category-aggregates="aggregate.category_aggregates" :products-by-code="aggregate.products_by_code" :source="aggregate.meta?.source" :purchases="aggregate.purchases" @drill-closure="onPurchaseDrill" @drill-product="onDrillProduct" />
            </div>
          </div>

          <!-- ═══ СРАВНЕНИЕ ═══ -->
          <div :key="tab" v-else-if="tab === 'compare'" class="pa-tabpane">
            <div class="pa-card">
              <div class="pa-card-h"><div class="pa-card-t-wrap"><span class="pa-card-t">Сравнение цен по компаниям и категориям</span><span class="pa-card-s">отклонение от средней цены рынка</span></div></div>
              <CategoryCompareTable :rating="aggregate.rating" :categories="aggregate.categories" @drill-company="onDrillCompany" />
            </div>
          </div>
        </Transition>
      </template>
    </div>

    <!-- ═══ Drill modals (preserved) ═══ -->
    <CompanyProfileModal v-if="drillCompany" :company="drillCompany" :categories="aggregate?.categories || []" :purchases="drillCompanyPurchases" :total-companies="aggregate?.rating.length || 0" @close="drillCompany = null" @drill-closure="onPurchaseDrill" />
    <PaPurchaseDrillModal v-if="purchaseDrill && aggregate" :purchase="purchaseDrill" :data="aggregate" :can-edit="_perm.canEdit.value" @close="purchaseDrill = null" @select-co="onChainSelectCo" @updated="onConclusionUpdated" />
    <PaProductDrillModal v-if="productDrillCode && aggregate" :product-code="productDrillCode" :data="aggregate" @close="productDrillCode = null" @drill-purchase="onPurchaseDrill" />
    <PaSupplierDrillModal v-if="supplierDrill && aggregate" :supplier-key="supplierDrill.key" :supplier-name="supplierDrill.name" :purchases="aggregate.purchases" :companies="aggregate.rating" :categories="aggregate.categories" @close="supplierDrill = null" @drill-closure="(c: ClosureRow) => { supplierDrill = null; onPurchaseDrill(c); }" @select-company="onSupplierSelectCompany" />
    <ForensicUploadModal v-if="showUploadModal" :year="year" endpoint="/procurement/closures/import-excel" title="Импорт закупок · Excel" description="Формат xarid_corporate_contracts: 22 листа (1 per SOE). Headers: lotId / organ / vendor / Unit price / amount / Category / productCode. Median per productCode → benchmark." :sheet-match="null" :format-result="fmtPaUploadResult" @close="showUploadModal = false" @uploaded="load" />
    <PaEditTableModal v-model="editTableOpen" :rows="aggregate?.purchases || []" :year="year" :can-edit="_perm.canEdit.value" @saved="load" />
  </div>
</template>

<style scoped>
.pa-view { background: #f4f3f9; min-height: 100%; font-family: var(--font, system-ui); }

@keyframes paFadeUp { from { opacity: 0; transform: translateY(6px); } to { opacity: 1; transform: translateY(0); } }
@keyframes paIn { from { opacity: 0; transform: translateY(8px); } to { opacity: 1; transform: none; } }
@keyframes paSkel { 0% { background-position: -200px 0; } 100% { background-position: 200px 0; } }

/* ─── Topbar ─── */
.pa-topbar { background: linear-gradient(95deg, #1E2A4A 0%, #2D3760 60%, #4B477E 100%); padding: 12px 22px; display: flex; align-items: center; justify-content: space-between; gap: 12px; flex-wrap: wrap; }
.pa-tb-l { display: flex; flex-direction: column; gap: 2px; min-width: 0; flex: 1; }
.pa-tb-title { font-size: 16px; font-weight: 600; color: #fff; margin: 0; letter-spacing: -.005em; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.pa-tb-sub { font-size: 11px; color: rgba(255,255,255,.55); display: flex; align-items: center; gap: 6px; flex-wrap: wrap; }
.pa-tb-sub b { color: rgba(255,255,255,.95); font-weight: 600; }
.pa-dot { opacity: .4; }
.pa-tb-r { display: flex; align-items: center; gap: 6px; flex-wrap: wrap; }
.pa-badge-wrap { position: relative; }
.pa-badge { display: flex; align-items: center; gap: 6px; background: rgba(255,255,255,.08); border: 1px solid rgba(255,255,255,.15); color: #fff; padding: 5px 10px; border-radius: 8px; font-size: 11.5px; font-weight: 500; cursor: pointer; font-family: inherit; transition: background .12s; }
.pa-badge:hover { background: rgba(255,255,255,.15); }
.pa-chev { flex-shrink: 0; }
.pa-sec-icon { width: 12px; height: 12px; border-radius: 3px; border: 1px solid; flex-shrink: 0; }
.pa-dd { position: absolute; top: calc(100% + 4px); right: 0; background: #fff; border: 1px solid rgba(0,0,0,.08); border-radius: 8px; box-shadow: 0 12px 32px rgba(15,23,60,.14); min-width: 220px; padding: 4px; z-index: 100; animation: paFadeUp .15s ease; }
.pa-dd-item { padding: 7px 10px; border-radius: 5px; font-size: 12px; color: #1E2A4A; cursor: pointer; display: flex; align-items: center; gap: 6px; transition: background .1s; }
.pa-dd-item:hover { background: #F4F3F9; }
.pa-dd-item.active { background: rgba(127,119,221,.12); color: #5B53B5; font-weight: 600; }
.pa-sec-dot { width: 8px; height: 8px; border-radius: 2px; flex-shrink: 0; }
.pa-edit-wrap { position: relative; }
.pa-edit-btn { background: rgba(255,255,255,.12); border: 1px solid rgba(255,255,255,.15); color: #fff; width: 32px; height: 32px; border-radius: 8px; cursor: pointer; display: flex; align-items: center; justify-content: center; transition: background .15s; }
.pa-edit-btn:hover { background: rgba(255,255,255,.2); }
.pa-edit-menu { position: absolute; top: 38px; right: 0; background: #fff; border: 1px solid rgba(0,0,0,.08); border-radius: 10px; box-shadow: 0 12px 32px rgba(15,23,60,.14); min-width: 230px; padding: 6px; z-index: 100; animation: paFadeUp .15s ease; }
.pa-edit-menu button { display: flex; align-items: center; gap: 8px; width: 100%; background: transparent; border: 0; padding: 8px 10px; border-radius: 6px; font-size: 12.5px; text-align: left; cursor: pointer; font-family: inherit; color: #1E2A4A; transition: background .12s; }
.pa-edit-menu button:hover { background: #F4F3F9; }
.pa-edit-menu button.danger { color: #C0504D; }
.pa-edit-menu button.danger:hover { background: rgba(226,75,74,.08); }
.pa-em-ico { width: 14px; text-align: center; color: rgba(15,23,60,.5); font-weight: 600; }
.pa-em-sep { height: 1px; background: rgba(0,0,0,.06); margin: 4px 0; }

/* ─── Tabs strip (light, premium) ─── */
.pa-tabstrip { display: flex; align-items: center; gap: 2px; padding: 0 20px; background: #fff; border-bottom: 1px solid rgba(15,23,60,.07); position: sticky; top: 0; z-index: 40; box-shadow: 0 1px 0 rgba(15,23,60,.02); overflow-x: auto; }
.pa-tab { position: relative; background: transparent; border: 0; font-family: inherit; font-size: 12.5px; font-weight: 600; letter-spacing: .01em; color: rgba(15,23,60,.5); padding: 13px 16px; cursor: pointer; white-space: nowrap; transition: color .16s; }
.pa-tab::after { content: ""; position: absolute; left: 12px; right: 12px; bottom: -1px; height: 2px; border-radius: 2px 2px 0 0; background: #7F77DD; transform: scaleX(0); transform-origin: center; transition: transform .22s cubic-bezier(.22,1,.36,1); }
.pa-tab:hover { color: #1E2A4A; }
.pa-tab.on { color: #5B53B5; }
.pa-tab.on::after { transform: scaleX(1); }

/* ─── Body ─── */
.pa-body { padding: 16px 20px 26px; display: flex; flex-direction: column; gap: 14px; }
.pa-tabpane { display: flex; flex-direction: column; gap: 14px; }

/* tab fade transition */
.pa-fade-enter-active { transition: opacity .2s ease, transform .2s ease; }
.pa-fade-leave-active { transition: opacity .12s ease; }
.pa-fade-enter-from { opacity: 0; transform: translateY(6px); }
.pa-fade-leave-to { opacity: 0; }

/* ─── KPI band ─── */
.pa-kpi-band { display: grid; grid-template-columns: repeat(5, 1fr); gap: 12px; }
@media (max-width: 1180px) { .pa-kpi-band { grid-template-columns: repeat(3, 1fr); } }
@media (max-width: 720px)  { .pa-kpi-band { grid-template-columns: repeat(2, 1fr); } }
.pa-kpi { position: relative; text-align: left; display: flex; flex-direction: column; gap: 4px; background: #fff; border: 1px solid rgba(0,0,0,.05); border-radius: 14px; padding: 14px 15px 13px; overflow: hidden; font-family: inherit; animation: paIn .5s cubic-bezier(.22,1,.36,1) both; animation-delay: calc(var(--i, 0) * 50ms); transition: box-shadow .18s, transform .18s; }
.pa-kpi::before { content: ""; position: absolute; left: 0; right: 0; top: 0; height: 3px; background: var(--accent, #7F77DD); opacity: .9; }
.pa-kpi.clickable { cursor: pointer; }
.pa-kpi.clickable:hover { box-shadow: 0 8px 22px rgba(15,23,60,.10); transform: translateY(-2px); }
.pa-kpi-eyebrow { font-size: 10.5px; font-weight: 600; text-transform: uppercase; letter-spacing: .06em; color: rgba(15,23,60,.5); }
.pa-kpi-info { font-size: 9px; margin-left: 4px; color: rgba(15,23,60,.32); cursor: help; vertical-align: top; }
.pa-kpi-value { font-size: clamp(20px, 2.4vw, 27px); font-weight: 400; color: #1E2A4A; font-variant-numeric: tabular-nums; line-height: 1.05; letter-spacing: -.01em; }
.pa-kpi-sub { font-size: 11px; color: rgba(15,23,60,.5); font-weight: 500; }
.pa-kpi-track { margin-top: 6px; height: 4px; border-radius: 4px; background: rgba(15,23,60,.07); overflow: hidden; }
.pa-kpi-fill { display: block; height: 100%; border-radius: 4px; transition: width .8s cubic-bezier(.22,1,.36,1); }

/* ─── Red flags ─── */
.pa-flags { display: grid; grid-template-columns: repeat(2, 1fr); gap: 10px; }
@media (max-width: 820px) { .pa-flags { grid-template-columns: 1fr; } }
.pa-flag { display: flex; align-items: center; gap: 11px; text-align: left; background: #fff; border: 1px solid rgba(0,0,0,.05); border-radius: 12px; padding: 12px 14px; cursor: pointer; font-family: inherit; animation: paIn .45s cubic-bezier(.22,1,.36,1) both; animation-delay: calc(var(--i,0) * 45ms); transition: box-shadow .18s, transform .18s; }
.pa-flag:hover { box-shadow: 0 8px 20px rgba(15,23,60,.08); transform: translateY(-1px); }
.pa-flag-dot { width: 9px; height: 9px; border-radius: 50%; flex-shrink: 0; }
.pa-flag.tone-red { background: linear-gradient(90deg, rgba(226,128,127,.07), #fff 60%); }
.pa-flag.tone-red .pa-flag-dot { background: #E2807F; box-shadow: 0 0 0 4px rgba(226,128,127,.14); }
.pa-flag.tone-amber { background: linear-gradient(90deg, rgba(239,179,115,.08), #fff 60%); }
.pa-flag.tone-amber .pa-flag-dot { background: #EFB373; box-shadow: 0 0 0 4px rgba(239,179,115,.16); }
.pa-flag-body { display: flex; flex-direction: column; gap: 1px; min-width: 0; flex: 1; }
.pa-flag-title { font-size: 12.5px; font-weight: 600; color: #1E2A4A; line-height: 1.3; }
.pa-flag-detail { font-size: 11px; color: rgba(15,23,60,.55); }
.pa-flag-arr { color: rgba(15,23,60,.3); flex-shrink: 0; transition: transform .18s; }
.pa-flag:hover .pa-flag-arr { transform: translateX(3px); color: rgba(15,23,60,.55); }

/* ─── Cards ─── */
.pa-card { background: #fff; border: 1px solid rgba(0,0,0,.05); border-radius: 14px; padding: 14px 16px; animation: paIn .5s cubic-bezier(.22,1,.36,1) both; }
.pa-card-h { display: flex; align-items: center; justify-content: space-between; gap: 8px; margin-bottom: 10px; flex-wrap: wrap; }
.pa-card-t-wrap { display: flex; align-items: baseline; gap: 8px; flex-wrap: wrap; min-width: 0; flex: 1; }
.pa-card-t { font-size: 13px; font-weight: 600; color: #1E2A4A; }
.pa-card-s { font-size: 11px; color: rgba(15,23,60,.5); font-weight: 500; }
.pa-card-rt { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }

.pa-zoom-btn { background: transparent; border: 0; width: 26px; height: 26px; border-radius: 6px; display: flex; align-items: center; justify-content: center; color: rgba(15,23,60,.5); cursor: pointer; transition: background .15s, color .15s; flex-shrink: 0; }
.pa-zoom-btn:hover { background: #F4F3F9; color: #1E2A4A; }
.pa-zoomed { position: fixed !important; inset: 24px !important; z-index: 200 !important; background: #fff !important; box-shadow: 0 24px 64px rgba(15,23,60,.25) !important; margin: 0 !important; overflow: auto !important; display: flex; flex-direction: column; }

.pa-split { display: grid; grid-template-columns: minmax(0, 2fr) minmax(0, 1fr); gap: 12px; }
@media (max-width: 1100px) { .pa-split { grid-template-columns: 1fr; } }
.pa-tornado-host { min-height: 360px; position: relative; }

.pa-side { display: flex; flex-direction: column; padding: 0; }
.pa-side-tabs { display: flex; align-items: center; gap: 2px; padding: 10px 12px 0; border-bottom: .5px solid rgba(0,0,0,.06); }
.pa-side-tab { background: transparent; border: 0; font-size: 12px; font-weight: 500; padding: 8px 12px; color: rgba(15,23,60,.5); border-bottom: 2px solid transparent; cursor: pointer; font-family: inherit; margin-bottom: -1px; transition: color .12s, border-color .12s; }
.pa-side-tab:hover { color: #1E2A4A; }
.pa-side-tab.active { color: #5B53B5; border-bottom-color: #7F77DD; }

/* segmented */
.pa-seg { display: inline-flex; background: rgba(0,0,0,.04); border-radius: 7px; padding: 2px; }
.pa-seg button { background: transparent; border: 0; font-size: 11px; padding: 4px 10px; border-radius: 5px; color: rgba(15,23,60,.5); cursor: pointer; font-family: inherit; font-weight: 500; transition: all .12s; }
.pa-seg button:hover { color: #1E2A4A; }
.pa-seg button.on { background: #fff; color: #1E2A4A; box-shadow: 0 1px 3px rgba(0,0,0,.08); }

/* ─── States / empty / skeleton ─── */
.pa-state { padding: 70px 22px; text-align: center; display: flex; flex-direction: column; align-items: center; gap: 10px; color: rgba(15,23,60,.55); font-size: 13px; }
.pa-state-err p { color: #B3514F; max-width: 480px; }
.pa-empty-pane { background: #fff; border-radius: 14px; padding: 50px 30px; text-align: center; border: 1px solid rgba(15,23,60,.06); }
.pa-empty-icon { opacity: .8; margin-bottom: 12px; display: flex; justify-content: center; }
.pa-empty-pane h3 { font-size: 14px; font-weight: 600; color: #1E2A4A; margin: 0 0 8px; }
.pa-empty-pane p { font-size: 12px; color: rgba(15,23,60,.55); max-width: 540px; margin: 0 auto 16px; line-height: 1.55; }
.pa-empty-actions { display: inline-flex; gap: 8px; flex-wrap: wrap; justify-content: center; }
.pa-mf-btn { font-size: 12px; font-weight: 500; padding: 7px 14px; border-radius: 8px; border: 1px solid rgba(15,23,60,.12); background: #fff; color: #1E2A4A; cursor: pointer; font-family: inherit; transition: all .12s; }
.pa-mf-btn:hover { background: #F4F3F9; }
.pa-mf-btn.primary { background: #7F77DD; color: #fff; border-color: #7F77DD; }
.pa-mf-btn.primary:hover { background: #6F66D0; }

.pa-skel-card { position: relative; overflow: hidden; }
.pa-skel { border-radius: 6px; background: linear-gradient(90deg, #eee 0px, #f5f5f7 40px, #eee 80px); background-size: 400px; animation: paSkel 1.2s infinite linear; }
.pa-skel-sm { height: 10px; width: 50%; margin-bottom: 10px; }
.pa-skel-lg { height: 24px; width: 70%; margin-bottom: 8px; }
.pa-skel-md { height: 10px; width: 60%; }
</style>
