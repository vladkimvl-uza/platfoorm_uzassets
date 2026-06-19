<script setup lang="ts">
/**
 * CompanyDrilldown — adaptive company drill-down modal (Pack 7.65).
 *
 * Replaces the legacy CompanyFinCard. Layout adapts to standard prop:
 *   - NSBU: 4 KPI cards, 2 tabs (ОФР · форма 2 / Баланс · форма 1), NSBU codes column
 *   - IFRS: 6 KPI cards, 4 tabs (ОФР / ОПД / Баланс / ДДС), notes display, audit badge
 *
 * Data sources:
 *   - /financials/companies/{code}/nsbu-editor  for NSBU
 *   - /financials/companies/{code}/ifrs-editor  for IFRS  (period=FY, consolidated=true)
 *
 * Both endpoints return values in млрд UZS keyed by fieldId then yearStr.
 */

import { computed, onBeforeUnmount, onMounted, ref, watch } from "vue";
import { runForecast, type ForecastModel } from "@/utils/forecast";
import { useRouter } from "vue-router";
import type { CompanyListItem, SectorBrief } from "@/api/companies";

const props = defineProps<{
  companyCode: string;
  companies: CompanyListItem[];
  sectors: SectorBrief[];
  standard: "IFRS" | "NSBU";
  year: number;
  currency: string;
}>();

const emit = defineEmits<{ (e: "close"): void; }>();

const router = useRouter();

// Локальный выбор стандарта и года — селекторы в шапке модалки (как в обзоре
// портфеля), независимо от страницы. Синхронизируются, если родитель сменил проп.
const localStandard = ref<"IFRS" | "NSBU">(props.standard);
const localYear = ref<number>(props.year);
watch(() => props.standard, (v) => { localStandard.value = v; });
watch(() => props.year, (v) => { localYear.value = v; });

// ─── Look up company + sector ──────────────────────────────────────────
const company = computed<CompanyListItem | null>(() => {
  return props.companies.find(c => c.code === props.companyCode) || null;
});
const sector = computed<SectorBrief | null>(() => {
  if (!company.value) return null;
  const code = String(company.value.sector_code || "").toLowerCase();
  return props.sectors.find(s => String(s.code).toLowerCase() === code) || null;
});

// Status border: prefer sector_color from company, fall back to neutral gray
const statusBorder = computed(() => {
  return company.value?.sector_color || sector.value?.color_hex || "#94A3B8";
});

// Display name for sector — prefer company.sector_name (already populated by API)
const sectorLabel = computed<string>(() => {
  return company.value?.sector_name || sector.value?.name_ru || "—";
});

// ─── Schema config (fields per section) ─────────────────────────────────
interface RowSpec { id: string; label: string; code?: string; isSubtotal?: boolean; isHighlight?: boolean; groupHeader?: string; }
type SectionId = "pnl" | "oci" | "sofp" | "cf";
interface SectionDef { id: SectionId; label: string; rows: RowSpec[]; }

const NSBU_SECTIONS: SectionDef[] = [
  {
    id: "pnl",
    label: "ОФР · форма 2",
    rows: [
      { id: "revenue",     label: "Выручка",                          code: "010", groupHeader: "ДОХОДЫ И РАСХОДЫ" },
      { id: "cogs",        label: "Себестоимость",                    code: "020" },
      { id: "grossProfit", label: "Валовая прибыль",                  code: "030", isSubtotal: true },
      { id: "opProfit",    label: "Операционная прибыль",             code: "060", groupHeader: "ОПЕРАЦИОННЫЙ РЕЗУЛЬТАТ" },
      { id: "depreciation",label: "Амортизация",                       code: "070" },
      { id: "finIncome",   label: "Доходы от фин. деятельности",      code: "110" },
      { id: "finCost",     label: "Расходы от фин. деятельности",     code: "170" },
      { id: "pbt",         label: "Прибыль до налога",                code: "190", isSubtotal: true, groupHeader: "ИТОГИ ПЕРИОДА" },
      { id: "tax",         label: "Налог на прибыль",                 code: "220" },
      { id: "profit",      label: "ЧИСТАЯ ПРИБЫЛЬ",                   code: "270", isSubtotal: true, isHighlight: true },
      { id: "ebitda",      label: "EBITDA",                            isSubtotal: true },
    ],
  },
  {
    id: "sofp",
    label: "Баланс · форма 1",
    rows: [
      { id: "ppe",              label: "Основные средства",        code: "010", groupHeader: "АКТИВЫ" },
      { id: "totalNCA",         label: "Внеоборотные активы",      code: "190", isSubtotal: true },
      { id: "cash",             label: "Денежные средства",        code: "320" },
      { id: "totalCA",          label: "Оборотные активы",         code: "390", isSubtotal: true },
      { id: "totalAssets",      label: "ИТОГО Активы",             code: "400", isSubtotal: true, isHighlight: true },
      { id: "equity",           label: "Собственный капитал",      code: "480", isSubtotal: true, groupHeader: "ПАССИВЫ" },
      { id: "ltBorrowings",     label: "Долгосрочные обязательства",code:"590", isSubtotal: true },
      { id: "stBorrowings",     label: "Краткосрочные обязательства",code:"780", isSubtotal: true },
      { id: "debt",             label: "Финансовый долг",          isSubtotal: true },
    ],
  },
];

const IFRS_SECTIONS: SectionDef[] = [
  {
    id: "pnl",
    label: "ОФР",
    rows: [
      { id: "revenue",      label: "Revenue · Выручка",                  groupHeader: "CONTINUING OPERATIONS" },
      { id: "cogs",         label: "Cost of sales · Себестоимость" },
      { id: "grossProfit",  label: "Gross profit · Валовая прибыль", isSubtotal: true },
      { id: "opProfit",     label: "Operating profit · Опер. прибыль", groupHeader: "OPERATING RESULT" },
      { id: "depreciation", label: "D&A · Амортизация" },
      { id: "finCost",      label: "Finance costs · Фин. расходы" },
      { id: "interestExp",  label: "  Interest expense" },
      { id: "forex",        label: "Forex · Курсовая разница" },
      { id: "pbt",          label: "Profit before tax · Прибыль до налога", isSubtotal: true, groupHeader: "PERIOD RESULTS" },
      { id: "tax",          label: "Income tax · Налог" },
      { id: "profit",       label: "NET PROFIT · ЧИСТАЯ ПРИБЫЛЬ", isSubtotal: true, isHighlight: true },
      { id: "ebitda",       label: "EBITDA", isSubtotal: true },
    ],
  },
  {
    id: "oci",
    label: "ОПД",
    rows: [
      { id: "oci_currency_translation", label: "Currency translation · Курсовые разницы", groupHeader: "OTHER COMPREHENSIVE INCOME" },
      { id: "oci_revaluation_ppe",      label: "PPE revaluation · Переоценка ОС" },
      { id: "oci_actuarial",            label: "Actuarial · Актуарные" },
      { id: "oci_hedge_reserve",        label: "Hedge reserve · Хеджирование" },
      { id: "oci_fvtoci",               label: "FVTOCI · Финактивы по справ. ст-ти" },
      { id: "total_comprehensive_income", label: "Total comprehensive income · Совокупный доход", isSubtotal: true, isHighlight: true },
    ],
  },
  {
    id: "sofp",
    label: "Баланс",
    rows: [
      { id: "ppe",              label: "PPE · Основные средства",     groupHeader: "ASSETS" },
      { id: "totalNCA",         label: "Total non-current assets",     isSubtotal: true },
      { id: "cash",             label: "Cash · Денежные средства" },
      { id: "totalCA",          label: "Total current assets",         isSubtotal: true },
      { id: "totalAssets",      label: "TOTAL ASSETS · Итого активы",  isSubtotal: true, isHighlight: true },
      { id: "equity",           label: "Equity · Собственный капитал", isSubtotal: true, groupHeader: "EQUITY & LIABILITIES" },
      { id: "ltBorrowings",     label: "LT borrowings",                 isSubtotal: true },
      { id: "stBorrowings",     label: "ST borrowings",                 isSubtotal: true },
      { id: "totalLiabilities", label: "TOTAL LIABILITIES",             isSubtotal: true },
      { id: "debt",             label: "Total debt · Финансовый долг", isSubtotal: true },
    ],
  },
  {
    id: "cf",
    label: "ДДС",
    rows: [
      { id: "cfo",            label: "CFO · Поток от операц. деятельности", isSubtotal: true, groupHeader: "OPERATING ACTIVITIES" },
      { id: "cfo_depreciation", label: "  Depreciation (adj)" },
      { id: "cfo_working_capital", label: "  Change in working capital" },
      { id: "cfo_tax_paid",   label: "  Income tax paid" },
      { id: "cfi",            label: "CFI · Поток от инвест. деятельности", isSubtotal: true, groupHeader: "INVESTING ACTIVITIES" },
      { id: "cfi_capex",      label: "  CapEx · Капитальные затраты" },
      { id: "cff",            label: "CFF · Поток от фин. деятельности", isSubtotal: true, groupHeader: "FINANCING ACTIVITIES" },
      { id: "cff_borrowings", label: "  Proceeds from borrowings" },
      { id: "cff_repayments", label: "  Repayments of borrowings" },
      { id: "dividendsPaid",  label: "  Dividends paid" },
      { id: "netCashChange",  label: "Net change in cash", isSubtotal: true, groupHeader: "TOTALS" },
      { id: "freeCashFlow",   label: "Free Cash Flow (FCF)", isSubtotal: true, isHighlight: true },
    ],
  },
];

const sections = computed<SectionDef[]>(() => localStandard.value === "IFRS" ? IFRS_SECTIONS : NSBU_SECTIONS);

// KPI configs
interface KpiDef { id: string; label: string; format?: "money" | "pct" | "margin"; subtype?: "ratio_debt_assets" | "margin_ebitda" | "yoy"; }
const KPI_NSBU: KpiDef[] = [
  { id: "revenue", label: "Выручка" },
  { id: "ebitda",  label: "EBITDA" },
  { id: "profit",  label: "Чистая прибыль" },
  { id: "totalAssets", label: "Итого активы" },
];
const KPI_IFRS: KpiDef[] = [
  { id: "revenue", label: "Revenue" },
  { id: "ebitda",  label: "EBITDA" },
  { id: "profit",  label: "Net profit" },
  { id: "totalAssets", label: "Total assets" },
  { id: "debt",    label: "Total debt" },
  { id: "freeCashFlow", label: "FCF" },
];
const kpis = computed<KpiDef[]>(() => localStandard.value === "IFRS" ? KPI_IFRS : KPI_NSBU);

// ─── Active tab ─────────────────────────────────────────────────────────
const activeSection = ref<SectionId>("pnl");

// ─── Data fetch ─────────────────────────────────────────────────────────
const loading = ref(false);
const values = ref<Record<string, Record<string, number | null>>>({});
const notes = ref<Record<string, string>>({});
const auditMeta = ref<{ firm?: string; opinion?: string; signed_at?: string; is_restated?: boolean } | null>(null);
const renames = ref<Record<string, string>>({});
const fetchError = ref<string>("");

async function loadData() {
  if (!props.companyCode) return;
  loading.value = true;
  fetchError.value = "";
  try {
    const { api } = await import("@/api/client");
    const url = localStandard.value === "IFRS"
      ? `/financials/companies/${props.companyCode}/ifrs-editor?period=FY&consolidated=true`
      : `/financials/companies/${props.companyCode}/nsbu-editor`;
    const resp = await api.get(url);
    const data = resp.data || {};
    values.value = data.values || {};
    notes.value  = data.notes || {};
    auditMeta.value = data.audit_meta || null;
    renames.value = data.renames || {};
    // Reset to first section
    activeSection.value = "pnl";
  } catch (e: unknown) {
    const err = e as { response?: { data?: { detail?: string } }; message?: string };
    fetchError.value = err?.response?.data?.detail || err?.message || "Не удалось загрузить данные";
    values.value = {};
    notes.value = {};
    auditMeta.value = null;
  } finally {
    loading.value = false;
  }
}

// On mount and whenever standard or companyCode changes, reload
onMounted(loadData);
watch([() => localStandard.value, () => props.companyCode], loadData);

// ─── Display helpers ────────────────────────────────────────────────────
const yearList = computed<number[]>(() => {
  const y = localYear.value;
  return [y - 2, y - 1, y];
});
// Годы для выпадающего списка — из загруженных данных (ключи-годы), иначе [year-2..year].
const yearOptions = computed<number[]>(() => {
  const ys = new Set<number>();
  for (const fm of Object.values(values.value)) {
    for (const k of Object.keys(fm)) { const n = Number(k); if (Number.isFinite(n)) ys.add(n); }
  }
  const arr = [...ys].sort((a, b) => b - a);
  return arr.length ? arr : [localYear.value, localYear.value - 1, localYear.value - 2];
});

function getValue(field: string, year: number): number | null {
  const fieldMap = values.value[field];
  if (!fieldMap) return null;
  const v = fieldMap[String(year)];
  return v == null ? null : Number(v);
}

function fmtNum(v: number | null): string {
  if (v == null || !isFinite(v)) return "—";
  const abs = Math.abs(v);
  let str: string;
  if (abs >= 1000) str = Math.round(v).toLocaleString("ru", { maximumFractionDigits: 0 });
  else if (abs >= 10) str = v.toLocaleString("ru", { maximumFractionDigits: 1 });
  else str = v.toLocaleString("ru", { maximumFractionDigits: 2 });
  return str.replace(/,/g, " ");
}

function fmtYoY(curr: number | null, prev: number | null): { text: string; color: string } {
  // 0 = «нет данных» в модуле → не считаем ложные ±100% когда факта нет.
  if (curr == null || curr === 0 || prev == null || prev === 0) return { text: "—", color: "#94A3B8" };
  const pct = ((curr - prev) / Math.abs(prev)) * 100;
  const sign = pct > 0 ? "+" : "";
  const text = `${sign}${pct.toFixed(1)}%`;
  // Direction colour — but for "cost" lines positive YoY is bad
  // Keep simple: positive=green, negative=red, near-zero=gray
  let color = "#64748B";
  if (pct >= 10) color = "#1D9E75";
  else if (pct >= 0) color = "#64748B";
  else if (pct >= -5) color = "#EF9F27";
  else color = "#E24B4A";
  return { text, color };
}

function getRowValues(field: string): { values: (number | null)[]; yoy: { text: string; color: string } } {
  const vals = yearList.value.map(y => getValue(field, y));
  return { values: vals, yoy: fmtYoY(vals[vals.length - 1], vals[vals.length - 2]) };
}

// ── Прогнозные колонки (детерминированные модели, переиспользуют движок) ──
const FC_OPTS: { id: ForecastModel | "off"; label: string }[] = [
  { id: "off", label: "Прогноз: выкл" },
  { id: "runrate", label: "Прогноз: Run-rate" },
  { id: "cagr", label: "Прогноз: CAGR" },
  { id: "linear", label: "Прогноз: линейный" },
];
const fcModel = ref<ForecastModel | "off">("off");
const forecastYears = computed<number[]>(() =>
  fcModel.value === "off" ? [] : [localYear.value + 1, localYear.value + 2],
);
const displayYears = computed<number[]>(() => [...yearList.value, ...forecastYears.value]);
function isFcYear(y: number): boolean { return fcModel.value !== "off" && y > localYear.value; }
function cellValue(field: string, y: number): number | null {
  if (y <= localYear.value) return getValue(field, y);
  if (fcModel.value === "off") return null;
  const hist = yearList.value.map((yr) => ({ year: yr, value: getValue(field, yr) }));
  const fc = runForecast(fcModel.value as ForecastModel, hist, forecastYears.value);
  return fc.find((p) => p.year === y)?.value ?? null;
}

// Compute KPI values for the header band
interface KpiCardData { label: string; value: string; subtext: string; subColor: string; }
const kpiCards = computed<KpiCardData[]>(() => {
  return kpis.value.map(kpi => {
    const curr = getValue(kpi.id, localYear.value);
    const prev = getValue(kpi.id, localYear.value - 1);
    const yoy = fmtYoY(curr, prev);
    // Default subtext: YoY comparison
    let subtext = `${yoy.text} vs ${localYear.value - 1}`;
    let subColor = yoy.color;
    if (curr == null) {
      subtext = "нет данных";
      subColor = "#94A3B8";
    }
    // Special: EBITDA → show margin instead of YoY
    if (kpi.id === "ebitda") {
      const rev = getValue("revenue", localYear.value);
      if (curr != null && rev != null && rev > 0) {
        subtext = `маржа ${((curr / rev) * 100).toFixed(1)}%`;
      }
    }
    if (kpi.id === "totalAssets" && localStandard.value === "IFRS") {
      // Show debt-to-assets ratio
      const debt = getValue("debt", localYear.value);
      if (curr != null && debt != null && curr > 0) {
        subtext = `долг ${((debt / curr) * 100).toFixed(0)}% от активов`;
        subColor = "#534AB7";
      }
    }
    return { label: kpi.label, value: fmtNum(curr), subtext, subColor };
  });
});

// ─── Notes summary for current section (IFRS only) ──────────────────────
const sectionNotes = computed<Array<{ field: string; label: string; text: string }>>(() => {
  if (localStandard.value !== "IFRS") return [];
  const currentRows = sections.value.find(s => s.id === activeSection.value)?.rows || [];
  const fieldIds = new Set(currentRows.map(r => r.id));
  const result: Array<{ field: string; label: string; text: string }> = [];
  for (const [fieldId, text] of Object.entries(notes.value)) {
    if (!fieldIds.has(fieldId)) continue;
    if (!text || !text.trim()) continue;
    const rowDef = currentRows.find(r => r.id === fieldId);
    result.push({ field: fieldId, label: renames.value[fieldId] || rowDef?.label || fieldId, text });
  }
  return result;
});

function hasNote(fieldId: string): boolean {
  return !!notes.value[fieldId]?.trim();
}

// ─── Audit summary line ─────────────────────────────────────────────────
const auditLine = computed<string>(() => {
  const a = auditMeta.value;
  if (!a) return "";
  const parts: string[] = [];
  if (a.firm) parts.push(a.firm);
  if (a.opinion) {
    const lbl: Record<string, string> = { clean: "clean", qualified: "qualified", adverse: "adverse", disclaimer: "disclaimer" };
    parts.push(lbl[a.opinion] || a.opinion);
  }
  if (a.signed_at) {
    try {
      const d = new Date(a.signed_at);
      parts.push(`подписан ${d.toLocaleDateString("ru")}`);
    } catch { /* noop */ }
  }
  return parts.join(" · ");
});

// ─── Actions ────────────────────────────────────────────────────────────
function onOpenEditor() {
  const routeName = localStandard.value === "IFRS" ? "financials-edit-ifrs" : "financials-edit-nsbu";
  router.push({ name: routeName });
  emit("close");
}

function onClose() {
  emit("close");
}

function onBackdropClick(e: MouseEvent) {
  if (e.target === e.currentTarget) emit("close");
}

// Esc closes
function onKey(e: KeyboardEvent) {
  if (e.key === "Escape") emit("close");
}
onMounted(() => window.addEventListener("keydown", onKey));
onBeforeUnmount(() => window.removeEventListener("keydown", onKey));
</script>

<template>
  <div class="cdrl-bd" @click="onBackdropClick" role="dialog" aria-modal="true">
    <div class="cdrl-card" :style="{ '--stripe-color': statusBorder }">

      <!-- Header -->
      <div class="cdrl-hdr">
        <div class="cdrl-hdr-left">
          <div class="cdrl-eyebrow">{{ company?.code }} · {{ sectorLabel }}</div>
          <div class="cdrl-title">{{ company?.name_short || company?.name_ru || company?.code }}</div>
          <div class="cdrl-badges">
            <span class="cdrl-badge" :class="localStandard === 'IFRS' ? 'badge-ifrs' : 'badge-nsbu'">
              <svg viewBox="0 0 12 12" width="9" height="9" fill="none" stroke="currentColor" stroke-width="1.6"><path d="M2 6h8M2 4h8M2 8h6" /><path v-if="localStandard === 'IFRS'" d="M9 2v8" /></svg>
              {{ localStandard === 'IFRS' ? 'МСФО · 4 секции' : 'НСБУ · форма 2 + 1' }}
            </span>
            <span v-if="auditLine" class="cdrl-badge badge-audit">{{ auditLine }}</span>
            <span v-if="auditMeta?.is_restated" class="cdrl-badge badge-restated">
              <svg viewBox="0 0 12 12" width="9" height="9" fill="none" stroke="currentColor" stroke-width="1.6"><circle cx="6" cy="6" r="4.5" /><path d="M6 3.5v3M6 8v0.1" /></svg>
              RESTATED
            </span>
          </div>
        </div>
        <div class="cdrl-hdr-right">
          <div class="cdrl-seg" role="group" aria-label="Стандарт">
            <button type="button" :class="{ on: localStandard === 'IFRS' }" @click="localStandard = 'IFRS'">МСФО</button>
            <button type="button" :class="{ on: localStandard === 'NSBU' }" @click="localStandard = 'NSBU'">НСБУ</button>
          </div>
          <select v-model.number="localYear" class="cdrl-sel" title="Финансовый год">
            <option v-for="y in yearOptions" :key="y" :value="y">FY {{ y }}</option>
          </select>
          <span class="cdrl-pill-static">{{ currency }}</span>
          <span v-if="localStandard === 'IFRS'" class="cdrl-pill-static">Cons</span>
          <button class="cdrl-btn-x" @click="onClose" aria-label="Закрыть">×</button>
        </div>
      </div>

      <!-- Error state -->
      <div v-if="fetchError" class="cdrl-error">
        <svg viewBox="0 0 16 16" width="14" height="14" fill="none" stroke="currentColor" stroke-width="1.6"><circle cx="8" cy="8" r="6.5" /><path d="M8 5v4M8 11v0.1" /></svg>
        {{ fetchError }}
      </div>

      <!-- KPI band -->
      <div v-else class="cdrl-kpis" :class="{ 'cdrl-kpis-6': kpis.length === 6 }">
        <div v-for="(kpi, idx) in kpiCards" :key="idx" class="cdrl-kpi">
          <div class="cdrl-kpi-lbl">{{ kpi.label }}</div>
          <div class="cdrl-kpi-val">
            <template v-if="loading">…</template>
            <template v-else>{{ kpi.value }}</template>
          </div>
          <div class="cdrl-kpi-sub" :style="{ color: kpi.subColor }">{{ kpi.subtext }}</div>
        </div>
      </div>

      <!-- Tabs -->
      <div v-if="!fetchError" class="cdrl-tabs">
        <div class="cdrl-tabs-left">
          <button v-for="sec in sections" :key="sec.id"
                  class="cdrl-tab" :class="{ on: activeSection === sec.id }"
                  @click="activeSection = sec.id">{{ sec.label }}</button>
        </div>
        <select v-model="fcModel" class="cdrl-fc-select" title="Прогноз будущих лет">
          <option v-for="o in FC_OPTS" :key="o.id" :value="o.id">{{ o.label }}</option>
        </select>
        <button v-if="localStandard === 'IFRS'" class="cdrl-recon-btn" disabled title="Откройте редактор для сверки с НСБУ">
          <svg viewBox="0 0 12 12" width="9" height="9" fill="none" stroke="currentColor" stroke-width="1.6"><path d="M3 3h6M3 6h6M3 9h4M6 1v10"/></svg>
          сверка с НСБУ
        </button>
      </div>

      <!-- Table -->
      <div v-if="!fetchError" class="cdrl-table-wrap">
        <table class="cdrl-table">
          <thead>
            <tr>
              <th v-if="localStandard === 'NSBU'" class="cdrl-th-code">КОД</th>
              <th class="cdrl-th-name">ПОКАЗАТЕЛЬ</th>
              <th v-for="y in displayYears" :key="y" class="cdrl-th-num" :class="{ current: y === year, fc: isFcYear(y) }">{{ y }}<span v-if="isFcYear(y)" class="cdrl-fc-tag">П</span></th>
              <th class="cdrl-th-yoy">YoY</th>
              <th v-if="localStandard === 'IFRS'" class="cdrl-th-note"></th>
            </tr>
          </thead>
          <tbody>
            <template v-for="row in sections.find(s => s.id === activeSection)?.rows || []" :key="row.id">
              <tr v-if="row.groupHeader" class="cdrl-group">
                <td :colspan="displayYears.length + 3">{{ row.groupHeader }}</td>
              </tr>
              <tr :class="{ 'cdrl-sub': row.isSubtotal, 'cdrl-highlight': row.isHighlight }">
                <td v-if="localStandard === 'NSBU'" class="cdrl-td-code">{{ row.code || "" }}</td>
                <td class="cdrl-td-name">{{ renames[row.id] || row.label }}</td>
                <td v-for="y in displayYears" :key="y"
                    class="cdrl-td-num" :class="{ current: y === year, fc: isFcYear(y) }">{{ fmtNum(cellValue(row.id, y)) }}</td>
                <td class="cdrl-td-yoy" :style="{ color: getRowValues(row.id).yoy.color }">{{ getRowValues(row.id).yoy.text }}</td>
                <td v-if="localStandard === 'IFRS'" class="cdrl-td-note">
                  <span v-if="hasNote(row.id)" class="cdrl-note-dot" :title="notes[row.id]">●</span>
                </td>
              </tr>
            </template>
            <tr v-if="loading">
              <td :colspan="displayYears.length + 3" class="cdrl-loading">Загрузка…</td>
            </tr>
          </tbody>
        </table>
      </div>

      <!-- Notes for active IFRS section -->
      <div v-if="localStandard === 'IFRS' && sectionNotes.length > 0" class="cdrl-notes">
        <div v-for="(n, idx) in sectionNotes" :key="idx" class="cdrl-note-row">
          <span class="cdrl-note-dot">●</span>
          <div class="cdrl-note-content">
            <span class="cdrl-note-label">{{ n.label }}:</span>
            <span class="cdrl-note-text">{{ n.text }}</span>
          </div>
        </div>
      </div>

      <!-- Footer -->
      <div class="cdrl-ftr">
        <span class="cdrl-ftr-info">Источник: openinfo.uz · последнее обновление по реестру</span>
        <div class="cdrl-ftr-actions">
          <button class="cdrl-btn-g" disabled title="Будет в следующих паках">PDF паспорт</button>
          <button class="cdrl-btn-cta" :class="localStandard === 'IFRS' ? 'cta-ifrs' : 'cta-nsbu'" @click="onOpenEditor">
            Открыть в редакторе {{ localStandard === 'IFRS' ? 'МСФО' : 'НСБУ' }}
          </button>
        </div>
      </div>

    </div>
  </div>
</template>

<style scoped>
.cdrl-bd {
  /* z-index выше сайдбара (100): иначе на узких экранах (≤14") центрированная
     модалка заезжает под сайдбар и левый край содержимого обрезается. */
  position: fixed; inset: 0; z-index: var(--z-top, 9990);
  background: rgba(15, 18, 40, 0.45);
  -webkit-backdrop-filter: blur(8px);
  backdrop-filter: blur(8px);
  display: flex; align-items: flex-start; justify-content: center;
  padding: 32px 16px;
  overflow-y: auto;
  animation: cdrl-bd-in 0.18s ease;
}
@keyframes cdrl-bd-in { from { opacity: 0; } to { opacity: 1; } }

.cdrl-card {
  background: var(--bg1, #fff);
  border-radius: 14px;
  overflow: hidden;
  width: 100%;
  max-width: 980px;
  box-shadow: 0 24px 64px rgba(15, 23, 60, 0.18), 0 8px 24px rgba(15, 23, 60, 0.08);
  color: var(--t1, #1E2A4A);
  font-family: inherit;
  animation: cdrl-card-in 0.32s var(--ease-standard);
  position: relative;
}
.cdrl-card::before {
  content: ""; position: absolute;
  left: 0; top: 14px; bottom: 14px;
  width: 4px; border-radius: 0 4px 4px 0;
  background: var(--stripe-color, #94A3B8);
  pointer-events: none; z-index: 2;
}
@keyframes cdrl-card-in {
  from { opacity: 0; transform: translateY(10px) scale(0.985); }
  to   { opacity: 1; transform: translateY(0)    scale(1); }
}

/* ─── Header ─── */
.cdrl-hdr {
  padding: 16px 22px 12px;
  border-bottom: 1px solid var(--border-input);
  display: flex; justify-content: space-between; align-items: flex-start; gap: 12px;
}
.cdrl-hdr-left { min-width: 0; flex: 1; }
.cdrl-hdr-right { display: flex; gap: 6px; align-items: center; flex-shrink: 0; }
.cdrl-eyebrow {
  font-size: 10px; font-weight: 500; letter-spacing: 0.08em;
  color: var(--t3, #94A3B8); text-transform: uppercase;
}
.cdrl-title {
  font-size: 19px; font-weight: 500; letter-spacing: -0.01em;
  margin-top: 3px;
}
.cdrl-badges { display: flex; gap: 8px; align-items: center; margin-top: 7px; flex-wrap: wrap; }
.cdrl-badge {
  display: inline-flex; align-items: center; gap: 4px;
  padding: 3px 9px; font-size: 10.5px; font-weight: 500;
  border-radius: 999px; letter-spacing: 0.02em;
}
.badge-nsbu { background: rgba(127, 119, 221, 0.16); color: var(--p-deep); }
.badge-ifrs { background: rgba(29, 158, 117, 0.16); color: #0F6E56; }
.badge-audit { background: rgba(127, 119, 221, 0.10); color: var(--p-deep); }
.badge-restated { background: var(--sev-high); color: #fff; letter-spacing: 0.04em; text-transform: uppercase; font-size: 9.5px; }
.cdrl-completion { font-size: 10.5px; font-weight: 500; }

.cdrl-pill-static {
  padding: 5px 11px; font-size: 11px; font-weight: 500;
  border-radius: 7px; border: 1px solid var(--border-input); background: var(--bg1, #fff);
  color: var(--t3, var(--t3));
}
/* Сегмент МСФО/НСБУ + селектор года в шапке модалки */
.cdrl-seg { display: inline-flex; background: var(--bg2, #F1F0FB); border-radius: 8px; padding: 2px; gap: 2px; }
.cdrl-seg button {
  border: none; background: transparent; cursor: pointer; font-family: inherit;
  font-size: 11px; font-weight: 600; color: var(--t3, #94A3B8);
  padding: 4px 11px; border-radius: 6px; transition: all .14s;
}
.cdrl-seg button:hover { color: var(--t1, #1E2A4A); }
.cdrl-seg button.on { background: var(--bg1, #fff); color: var(--p-deep, #534AB7); box-shadow: 0 1px 3px rgba(16,24,64,.1); }
.cdrl-sel {
  padding: 5px 26px 5px 10px; font-size: 11px; font-weight: 600;
  border-radius: 7px; border: 1px solid var(--border-input); background: var(--bg1, #fff);
  color: var(--t2, #334155); font-family: inherit; cursor: pointer; outline: none;
  appearance: none;
  background-image: url("data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 12 12'><path fill='%2394A3B8' d='M6 8.5L2 4.5h8z'/></svg>");
  background-repeat: no-repeat; background-position: right 8px center; background-size: 10px;
}
.cdrl-sel:focus { border-color: var(--p, #7C6FF7); }
.cdrl-btn-x {
  width: 26px; height: 26px; border-radius: 6px;
  border: 1px solid var(--border-input); background: var(--bg1, #fff);
  cursor: pointer; color: var(--t3, var(--t3)); font-size: 16px;
  font-family: inherit; line-height: 1;
}
.cdrl-btn-x:hover { background: rgba(226, 75, 74, 0.06); border-color: rgba(226, 75, 74, 0.3); color: var(--sev-critical); }

/* ─── Error ─── */
.cdrl-error {
  margin: 16px 22px; padding: 10px 14px;
  background: rgba(226, 75, 74, 0.06);
  border: 1px solid rgba(226, 75, 74, 0.25);
  color: var(--sev-critical); font-size: 12px;
  border-radius: 8px;
  display: inline-flex; gap: 8px; align-items: center;
}

/* ─── KPI band ─── */
.cdrl-kpis {
  display: grid;
  /* Самобалансирующаяся сетка — на узкой модалке (планшет-портрет ~760px)
     ложится без сирот и без гор.скролла; hairline-разделители (gap+bg) сохранены. */
  grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
  gap: 1px; background: var(--border-input); border-bottom: 1px solid var(--border-input);
}
.cdrl-kpis-6 { grid-template-columns: repeat(auto-fit, minmax(130px, 1fr)); }
.cdrl-kpi {
  background: var(--bg1, #fff); padding: 14px 14px;
}
.cdrl-kpis-6 .cdrl-kpi { padding: 12px 11px; }
.cdrl-kpi-lbl {
  font-size: 9.5px; font-weight: 500; color: var(--t3, #94A3B8);
  letter-spacing: 0.06em; text-transform: uppercase;
}
.cdrl-kpis-6 .cdrl-kpi-lbl { font-size: 9px; }
.cdrl-kpi-val {
  font-size: 22px; font-weight: 400; letter-spacing: -0.025em;
  margin-top: 4px; font-feature-settings: 'tnum';
}
.cdrl-kpis-6 .cdrl-kpi-val { font-size: 18px; letter-spacing: -0.02em; }
.cdrl-kpi-sub { font-size: 10.5px; margin-top: 2px; }
.cdrl-kpis-6 .cdrl-kpi-sub { font-size: 10px; }

/* ─── Tabs ─── */
.cdrl-tabs {
  display: flex; gap: 2px; padding: 8px 16px;
  background: #FAFAF9; border-bottom: 1px solid var(--border-input);
  align-items: center; justify-content: space-between;
}
.cdrl-tabs-left { display: flex; gap: 2px; }
.cdrl-tab {
  padding: 6px 14px; font-size: 11px; font-weight: 500;
  border-radius: 7px; border: none;
  background: transparent; color: var(--t3, var(--t3));
  cursor: pointer; font-family: inherit;
  transition: background 0.12s ease, color 0.12s ease;
}
.cdrl-tab:hover { background: rgba(127, 119, 221, 0.08); color: var(--p-deep); }
.cdrl-tab.on { background: var(--bg1, #fff); color: var(--t1, #1E2A4A); box-shadow: 0 1px 2px rgba(15, 23, 60, 0.08); }

.cdrl-recon-btn {
  padding: 5px 10px; font-size: 10.5px; font-weight: 500;
  border-radius: 6px; border: 1px solid #7F77DD;
  background: rgba(127, 119, 221, 0.08); color: var(--p-deep);
  cursor: pointer; font-family: inherit;
  display: inline-flex; align-items: center; gap: 5px;
}
.cdrl-recon-btn:disabled { opacity: 0.6; cursor: not-allowed; }

/* ─── Table ─── */
.cdrl-table-wrap { max-height: 460px; overflow: auto; }
/* Планшет/телефон (≤1023): первая колонка (показатель/код) липкая при гор.
   скролле year-колонок — иначе имя строки уезжает. Непрозрачный фон обязателен. */
@media (max-width: 1023px) {
  .cdrl-table th:first-child, .cdrl-table td:first-child {
    position: sticky; left: 0; z-index: 2;
    background: var(--bg1, #fff); box-shadow: 1px 0 0 var(--border-input);
  }
}
.cdrl-table {
  width: 100%; border-collapse: collapse; font-size: 11.5px;
}
.cdrl-table thead {
  background: #FAFAF9; position: sticky; top: 0; z-index: 1;
}
.cdrl-table th {
  padding: 8px 12px; text-align: left; font-size: 9px; font-weight: 500;
  color: var(--t3, #94A3B8); text-transform: uppercase; letter-spacing: 0.06em;
  border-bottom: 1px solid var(--border-input);
}
.cdrl-th-code { width: 56px; padding-left: 14px; }
/* Спецификсность: .cdrl-table th (0,1,1) перебивала .cdrl-th-num (0,1,0) и
   тянула заголовки лет влево, тогда как значения справа — числа «съезжали»
   из-под годов. Поднимаем специфичность, чтобы заголовки тоже были справа. */
.cdrl-table th.cdrl-th-num  { text-align: right; }
.cdrl-table th.cdrl-th-num.current { color: var(--t1, #1E2A4A); padding-right: 14px; }
/* Прогнозные колонки */
.cdrl-fc-select { font-size: 11px; font-weight: 600; font-family: inherit; color: #4B4193; background: #ECEAFB; border: 1px solid #B9B4E8; border-radius: 7px; padding: 3px 8px; cursor: pointer; margin-left: auto; }
.cdrl-table th.cdrl-th-num.fc { color: #A36500; background: rgba(224,146,47,.08); }
.cdrl-fc-tag { font-size: 7.5px; font-weight: 700; color: #A36500; background: rgba(224,146,47,.16); border-radius: 3px; padding: 0 3px; margin-left: 2px; vertical-align: super; }
.cdrl-table td.cdrl-td-num.fc { color: #8A5A12; background: rgba(224,146,47,.05); border-left: 1px dashed rgba(224,146,47,.4); font-style: italic; }
.cdrl-table th.cdrl-th-yoy  { text-align: right; width: 64px; padding-right: 14px; }
.cdrl-th-note { width: 26px; }

.cdrl-table td {
  padding: 5px 12px; border-bottom: 1px solid #F1F5F9;
  vertical-align: middle;
}
.cdrl-td-code {
  font-family: monospace; font-size: 10px; color: var(--t3, #94A3B8);
  padding-left: 14px;
}
.cdrl-td-name { font-size: 11.5px; color: var(--t1, #1E2A4A); }
.cdrl-td-num  {
  text-align: right; font-feature-settings: 'tnum';
  color: var(--t1, #1E2A4A);
}
.cdrl-td-num.current { padding-right: 14px; font-weight: 500; }
.cdrl-td-yoy  { text-align: right; font-size: 10.5px; padding-right: 14px; font-feature-settings: 'tnum'; }
.cdrl-td-note { text-align: center; }

.cdrl-table tr.cdrl-sub td {
  background: rgba(127, 119, 221, 0.04);
  font-weight: 500;
  padding-top: 6px; padding-bottom: 6px;
}
.cdrl-table tr.cdrl-highlight td {
  background: rgba(29, 158, 117, 0.06);
  border-top: 1px solid rgba(29, 158, 117, 0.25);
  color: #0F6E56;
  padding-top: 7px; padding-bottom: 7px;
}
.cdrl-table tr.cdrl-group td {
  padding: 9px 14px 5px;
  font-size: 9px; font-weight: 500;
  color: var(--t3, #94A3B8); text-transform: uppercase; letter-spacing: 0.07em;
  background: #FAFAF9; border-bottom: none;
}

.cdrl-note-dot {
  display: inline-block; width: 14px; height: 14px;
  border-radius: 3px; background: rgba(127, 119, 221, 0.18);
  color: var(--p-deep); line-height: 14px; font-size: 9px; text-align: center;
  cursor: help;
}

.cdrl-loading {
  text-align: center; color: var(--t3, #94A3B8); font-size: 11px;
  padding: 20px 0 !important;
}

/* ─── Notes section ─── */
.cdrl-notes {
  padding: 10px 22px;
  background: rgba(127, 119, 221, 0.05);
  border-top: 1px solid rgba(127, 119, 221, 0.20);
  display: flex; flex-direction: column; gap: 6px;
}
.cdrl-note-row {
  display: flex; align-items: flex-start; gap: 8px;
}
.cdrl-note-row .cdrl-note-dot { flex-shrink: 0; margin-top: 2px; }
.cdrl-note-content { font-size: 10.5px; color: var(--p-deep); line-height: 1.45; }
.cdrl-note-label { font-weight: 500; margin-right: 4px; }
.cdrl-note-text { font-weight: 400; }

/* ─── Footer ─── */
.cdrl-ftr {
  padding: 10px 22px; background: #FAFAF9;
  border-top: 1px solid var(--border-input);
  display: flex; justify-content: space-between; align-items: center; gap: 12px;
}
.cdrl-ftr-info { font-size: 10.5px; color: var(--t3, #94A3B8); }
.cdrl-ftr-actions { display: flex; gap: 8px; }
.cdrl-btn-g {
  padding: 5px 11px; font-size: 11px; border-radius: 7px;
  border: 1px solid var(--border-input); background: var(--bg1, #fff);
  cursor: pointer; color: var(--t3, var(--t3)); font-family: inherit;
}
.cdrl-btn-g:disabled { opacity: 0.5; cursor: not-allowed; }
.cdrl-btn-cta {
  padding: 5px 11px; font-size: 11px; font-weight: 500;
  border-radius: 7px; border: 1px solid; background: ; color: #fff;
  cursor: pointer; font-family: inherit;
}
.cta-nsbu { border-color: #7F77DD; background: #7F77DD; }
.cta-nsbu:hover { background: #6E66CE; }
.cta-ifrs { border-color: var(--green); background: var(--green); }
.cta-ifrs:hover { background: #178D69; }
</style>
