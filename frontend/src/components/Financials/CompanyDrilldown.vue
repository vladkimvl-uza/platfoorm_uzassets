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

import { computed, onMounted, ref, watch } from "vue";
import { runForecast, type ForecastModel } from "@/utils/forecast";
import { useRouter } from "vue-router";
import EntityDrillShell from "@/components/UZA/EntityDrillShell.vue";
import { useToast } from "@/composables/useToast";
import { usePermissions } from "@/composables/usePermissions";
import { useI18n } from "@/composables/useI18n";
import { getCurrentIntlLocale } from "@/locale/i18n";
import { useAuthStore } from "@/stores/auth";
import type { CompanyListItem, SectorBrief } from "@/api/companies";
import { i18nKey } from "@/locale/keys";
import { companyDisplayName, sectorDisplayName } from "@/utils/displayNames";


const props = withDefaults(defineProps<{
  companyCode: string;
  companies: CompanyListItem[];
  sectors: SectorBrief[];
  standard: "IFRS" | "NSBU";
  year: number;
  currency: string;
  // embedded: встроен во вкладку воркспейса (без модального chrome; стандарт и
  // год задаёт воркспейс — вкладка ifrs/nsbu + степпер года, поэтому свои
  // селекторы стандарта/года в шапке скрываем).
  variant?: "modal" | "embedded";
}>(), { variant: "modal" });
const isEmbedded = computed(() => props.variant === "embedded");

const emit = defineEmits<{ (e: "close"): void; }>();

const router = useRouter();
const toast = useToast();
const { t } = useI18n();
const auth = useAuthStore();
const finPerm = usePermissions("financials");
const canEdit = computed(() => finPerm.canEdit.value);

// «Кто редактировал последний раз и когда» — для футера (вместо openinfo.uz).
const lastEdit = ref<{ at: string; by: string } | null>(null);
function meName(): string {
  const u = auth.user;
  return (u?.full_name || u?.username || u?.email || "—") as string;
}
function markEdited() { lastEdit.value = { at: new Date().toISOString(), by: meName() }; }
function fmtDateTime(iso: string | null): string {
  if (!iso) return "";
  try {
    return new Date(iso).toLocaleString(getCurrentIntlLocale(), {
      day: "2-digit", month: "2-digit", year: "numeric", hour: "2-digit", minute: "2-digit",
    });
  } catch { return iso; }
}
const lastEditedText = computed(() =>
  lastEdit.value
    ? t("Изменено: {by} · {at}", { by: lastEdit.value.by, at: fmtDateTime(lastEdit.value.at) })
    : t("Изменений ещё не было"),
);

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
  return sectorDisplayName(sector.value || {
    code: company.value?.sector_code,
    name_ru: company.value?.sector_name,
    name_uz: company.value?.sector_name_uz,
    name_uz_cyr: company.value?.sector_name_uz_cyr,
    name_en: company.value?.sector_name_en,
  }) || "—";
});

// ─── Schema config (fields per section) ─────────────────────────────────
interface RowSpec { id: string; label: string; code?: string; isSubtotal?: boolean; isHighlight?: boolean; groupHeader?: string; }
type SectionId = "pnl" | "oci" | "sofp" | "cf";
interface SectionDef { id: SectionId; label: string; rows: RowSpec[]; }

const NSBU_SECTIONS: SectionDef[] = [
  {
    id: "pnl",
    label: i18nKey("ОФР · форма 2"),
    rows: [
      { id: "revenue",     label: i18nKey("Выручка"),                          code: "010", groupHeader: i18nKey("ДОХОДЫ И РАСХОДЫ") },
      { id: "cogs",        label: i18nKey("Себестоимость"),                    code: "020" },
      { id: "grossProfit", label: i18nKey("Валовая прибыль"),                  code: "030", isSubtotal: true },
      { id: "opProfit",    label: i18nKey("Операционная прибыль"),             code: "060", groupHeader: i18nKey("ОПЕРАЦИОННЫЙ РЕЗУЛЬТАТ") },
      { id: "depreciation",label: i18nKey("Амортизация"),                       code: "070" },
      { id: "finIncome",   label: i18nKey("Доходы от фин. деятельности"),      code: "110" },
      { id: "finCost",     label: i18nKey("Расходы от фин. деятельности"),     code: "170" },
      { id: "pbt",         label: i18nKey("Прибыль до налога"),                code: "190", isSubtotal: true, groupHeader: i18nKey("ИТОГИ ПЕРИОДА") },
      { id: "tax",         label: i18nKey("Налог на прибыль"),                 code: "220" },
      { id: "profit",      label: i18nKey("ЧИСТАЯ ПРИБЫЛЬ"),                   code: "270", isSubtotal: true, isHighlight: true },
      { id: "ebitda",      label: "EBITDA",                            isSubtotal: true },
    ],
  },
  {
    id: "sofp",
    label: i18nKey("Баланс · форма 1"),
    rows: [
      { id: "ppe",              label: i18nKey("Основные средства"),        code: "010", groupHeader: i18nKey("АКТИВЫ") },
      { id: "totalNCA",         label: i18nKey("Внеоборотные активы"),      code: "190", isSubtotal: true },
      { id: "cash",             label: i18nKey("Денежные средства"),        code: "320" },
      { id: "totalCA",          label: i18nKey("Оборотные активы"),         code: "390", isSubtotal: true },
      { id: "totalAssets",      label: i18nKey("ИТОГО Активы"),             code: "400", isSubtotal: true, isHighlight: true },
      { id: "equity",           label: i18nKey("Собственный капитал"),      code: "480", isSubtotal: true, groupHeader: i18nKey("ПАССИВЫ") },
      { id: "ltBorrowings",     label: i18nKey("Долгосрочные обязательства"),code:"590", isSubtotal: true },
      { id: "stBorrowings",     label: i18nKey("Краткосрочные обязательства"),code:"780", isSubtotal: true },
      { id: "debt",             label: i18nKey("Финансовый долг"),          isSubtotal: true },
    ],
  },
];

const IFRS_SECTIONS: SectionDef[] = [
  {
    id: "pnl",
    label: i18nKey("ОФР"),
    rows: [
      { id: "revenue",      label: i18nKey("Revenue · Выручка"),                  groupHeader: "CONTINUING OPERATIONS" },
      { id: "cogs",         label: i18nKey("Cost of sales · Себестоимость") },
      { id: "grossProfit",  label: i18nKey("Gross profit · Валовая прибыль"), isSubtotal: true },
      { id: "opProfit",     label: i18nKey("Operating profit · Опер. прибыль"), groupHeader: "OPERATING RESULT" },
      { id: "depreciation", label: i18nKey("D&A · Амортизация") },
      { id: "finCost",      label: i18nKey("Finance costs · Фин. расходы") },
      { id: "interestExp",  label: "  Interest expense" },
      { id: "forex",        label: i18nKey("Forex · Курсовая разница") },
      { id: "pbt",          label: i18nKey("Profit before tax · Прибыль до налога"), isSubtotal: true, groupHeader: "PERIOD RESULTS" },
      { id: "tax",          label: i18nKey("Income tax · Налог") },
      { id: "profit",       label: i18nKey("NET PROFIT · ЧИСТАЯ ПРИБЫЛЬ"), isSubtotal: true, isHighlight: true },
      { id: "ebitda",       label: "EBITDA", isSubtotal: true },
    ],
  },
  {
    id: "oci",
    label: i18nKey("ОПД"),
    rows: [
      { id: "oci_currency_translation", label: i18nKey("Currency translation · Курсовые разницы"), groupHeader: "OTHER COMPREHENSIVE INCOME" },
      { id: "oci_revaluation_ppe",      label: i18nKey("PPE revaluation · Переоценка ОС") },
      { id: "oci_actuarial",            label: i18nKey("Actuarial · Актуарные") },
      { id: "oci_hedge_reserve",        label: i18nKey("Hedge reserve · Хеджирование") },
      { id: "oci_fvtoci",               label: i18nKey("FVTOCI · Финактивы по справ. ст-ти") },
      { id: "total_comprehensive_income", label: i18nKey("Total comprehensive income · Совокупный доход"), isSubtotal: true, isHighlight: true },
    ],
  },
  {
    id: "sofp",
    label: i18nKey("Баланс"),
    rows: [
      { id: "ppe",              label: i18nKey("PPE · Основные средства"),     groupHeader: "ASSETS" },
      { id: "totalNCA",         label: "Total non-current assets",     isSubtotal: true },
      { id: "cash",             label: i18nKey("Cash · Денежные средства") },
      { id: "totalCA",          label: "Total current assets",         isSubtotal: true },
      { id: "totalAssets",      label: i18nKey("TOTAL ASSETS · Итого активы"),  isSubtotal: true, isHighlight: true },
      { id: "equity",           label: i18nKey("Equity · Собственный капитал"), isSubtotal: true, groupHeader: "EQUITY & LIABILITIES" },
      { id: "ltBorrowings",     label: "LT borrowings",                 isSubtotal: true },
      { id: "stBorrowings",     label: "ST borrowings",                 isSubtotal: true },
      { id: "totalLiabilities", label: "TOTAL LIABILITIES",             isSubtotal: true },
      { id: "debt",             label: i18nKey("Total debt · Финансовый долг"), isSubtotal: true },
    ],
  },
  {
    id: "cf",
    label: i18nKey("ДДС"),
    rows: [
      { id: "cfo",            label: i18nKey("CFO · Поток от операц. деятельности"), isSubtotal: true, groupHeader: "OPERATING ACTIVITIES" },
      { id: "cfo_depreciation", label: "  Depreciation (adj)" },
      { id: "cfo_working_capital", label: "  Change in working capital" },
      { id: "cfo_tax_paid",   label: "  Income tax paid" },
      { id: "cfi",            label: i18nKey("CFI · Поток от инвест. деятельности"), isSubtotal: true, groupHeader: "INVESTING ACTIVITIES" },
      { id: "cfi_capex",      label: i18nKey("  CapEx · Капитальные затраты") },
      { id: "cff",            label: i18nKey("CFF · Поток от фин. деятельности"), isSubtotal: true, groupHeader: "FINANCING ACTIVITIES" },
      { id: "cff_borrowings", label: "  Proceeds from borrowings" },
      { id: "cff_repayments", label: "  Repayments of borrowings" },
      { id: "dividendsPaid",  label: "  Dividends paid" },
      { id: "netCashChange",  label: "Net change in cash", isSubtotal: true, groupHeader: "TOTALS" },
      { id: "freeCashFlow",   label: "Free Cash Flow (FCF)", isSubtotal: true, isHighlight: true },
    ],
  },
];

const sections = computed<SectionDef[]>(() => localStandard.value === "IFRS" ? IFRS_SECTIONS : NSBU_SECTIONS);

// KPI configs.
//  src: "fin" — значение из financial_lines (values), "ind" — годовой индикатор
//  компании (sponsorship/taxes/headcount), unit "people" — формат «чел.».
interface KpiDef { id: string; label: string; src?: "fin" | "ind"; unit?: "people"; }
// 3 индикатора компании показываем в обоих стандартах (метрики компании, не отчёта).
const KPI_INDICATORS: KpiDef[] = [
  { id: "sponsorship", label: i18nKey("Спонсорство"), src: "ind" },
  { id: "taxes",       label: i18nKey("Налоги"),      src: "ind" },
  { id: "headcount",   label: i18nKey("Сотрудники"),  src: "ind", unit: "people" },
];
const KPI_NSBU: KpiDef[] = [
  { id: "revenue", label: i18nKey("Выручка") },
  { id: "ebitda",  label: "EBITDA" },
  { id: "unitCostRatio", label: i18nKey("Удельная себестоимость") },
  { id: "profit",  label: i18nKey("Чистая прибыль") },
  { id: "totalAssets", label: i18nKey("Итого активы") },
  ...KPI_INDICATORS,
];
const KPI_IFRS: KpiDef[] = [
  { id: "revenue", label: "Revenue" },
  { id: "ebitda",  label: "EBITDA" },
  { id: "unitCostRatio", label: i18nKey("Удельная себестоимость") },
  { id: "profit",  label: "Net profit" },
  { id: "totalAssets", label: "Total assets" },
  { id: "debt",    label: "Total debt" },
  { id: "freeCashFlow", label: "FCF" },
  ...KPI_INDICATORS,
];
const kpis = computed<KpiDef[]>(() => localStandard.value === "IFRS" ? KPI_IFRS : KPI_NSBU);
const INDICATOR_IDS = new Set(KPI_INDICATORS.map(k => k.id));

// ─── Active tab ─────────────────────────────────────────────────────────
const activeSection = ref<SectionId>("pnl");

// ─── Data fetch ─────────────────────────────────────────────────────────
const loading = ref(false);
const values = ref<Record<string, Record<string, number | null>>>({});
const notes = ref<Record<string, string>>({});
// Индикаторы компании (стандарт-агностично): inn + sponsorship/taxes/headcount по годам.
const inn = ref<string | null>(null);
const indicators = ref<Record<string, Record<string, number | null>>>({});
// company.employees_count — фолбэк для карточки «Сотрудники», если годовой
// индикатор headcount не заполнен (как показывает exec-модалка компании).
const companyEmployees = ref<number | null>(null);
// Денежный поток / FCF из «Высокоуровневых показателей» (HLF) — фолбэк, когда в
// редакторе МСФО/НСБУ эти строки не заполнены. field → {yearStr: value} (млрд).
const hlfCash = ref<Record<string, Record<string, number>>>({});
interface HlfRowLike { label?: string; type?: string; mapping?: string; values?: (number | string | null)[]; }
// Поля редактора, которые нужно сохранить при round-trip PUT (иначе затрём кастомизацию).
const customFields = ref<unknown[]>([]);
const formulaOverrides = ref<Record<string, string>>({});
const manualFlags = ref<Record<string, Record<string, boolean>>>({});
const saving = ref(false);
// Инлайн-редактирование: одна ячейка за раз. loc — где открыт инпут (kpi/cell/inn).
const editing = ref<{ loc: "kpi" | "cell" | "inn"; field: string; year: number } | null>(null);
const editVal = ref<string>("");
const editOrig = ref<string>("");
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
    const [resp, indResp, coResp, hlfResp] = await Promise.all([
      api.get(url),
      api.get(`/financials/companies/${props.companyCode}/indicators`).catch(() => null),
      api.get(`/companies/${props.companyCode}`).catch(() => null),
      api.get(`/financials/companies/${props.companyCode}/hlf`).catch(() => null),
    ]);
    companyEmployees.value = (coResp?.data?.employees_count ?? null) as number | null;
    hlfCash.value = extractHlfCash(hlfResp?.data?.hlf);
    const data = resp.data || {};
    values.value = data.values || {};
    notes.value  = data.notes || {};
    auditMeta.value = data.audit_meta || null;
    renames.value = data.renames || {};
    // Сохраняем кастомизацию редактора для round-trip PUT (чтобы не затереть).
    customFields.value = data.customFields || [];
    formulaOverrides.value = data.formulaOverrides || {};
    manualFlags.value = data.manualFlags || {};
    if (indResp) {
      inn.value = (indResp.data?.inn ?? null) as string | null;
      indicators.value = indResp.data?.indicators || {};
    }
    // «Кто редактировал последний раз» — берём самую свежую из правок отчётности
    // (редактор) и индикаторов компании.
    const cands: { at: string; by: string }[] = [];
    if (data.updatedAt && data.updatedBy) cands.push({ at: data.updatedAt, by: data.updatedBy });
    if (indResp?.data?.updated_at && indResp?.data?.updated_by) {
      cands.push({ at: indResp.data.updated_at, by: indResp.data.updated_by });
    }
    cands.sort((a, b) => (a.at < b.at ? 1 : -1));
    lastEdit.value = cands[0] || null;
    editing.value = null;
    // Reset to first section
    activeSection.value = "pnl";
  } catch (e: unknown) {
    const err = e as { response?: { data?: { detail?: string } }; message?: string };
    fetchError.value = err?.response?.data?.detail || err?.message || t("Не удалось загрузить данные");
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

// Денежный поток из HLF: CFO / CapEx / Дивиденды / CFI / CFF (если строки есть) +
// FCF = CFO − |CapEx|. Возвращаем {field: {yearStr: value}} в той же единице (млрд).
// Аудит P1 — паритет с бэк-матчером _extract_hlf_cash (financials_portfolio):
//  1) иглы включают реальные метки БД «Operating/Investing/Financing Cash Flow»
//     (старый список их пропускал → CFI/CFF терялись);
//  2) индекс values мапится на годы СЕКЦИИ (top-level years — union по всем
//     секциям, может быть длиннее → сдвиг годов);
//  3) subtotal (итог секции) приоритетнее обычной line.
function extractHlfCash(hlf: unknown): Record<string, Record<string, number>> {
  const out: Record<string, Record<string, number>> = {};
  const h = hlf as { years?: number[]; sections?: { years?: number[]; rows?: HlfRowLike[] }[] } | null;
  if (!h || !Array.isArray(h.sections)) return out;
  const topYears = Array.isArray(h.years) ? h.years : [];
  // i18n-exempt-start: multilingual aliases classify imported financial rows; they are never rendered.
  const M: Record<string, string[]> = {
    cfo: ["operating cash flow", "net cash from operating", "cash from operating", "cash generated from operating", "cash flows from operating", "поток от операц", "операционн"],
    cfi: ["investing cash flow", "net cash used in investing", "cash from investing", "cash flows from investing", "поток от инвест", "инвестиционн"],
    cff: ["financing cash flow", "net cash from financing", "cash from financing", "cash flows from financing", "поток от фин", "финансиров"],
    cfi_capex: ["purchase of ppe", "purchases of property", "capital expenditures", "capex", "капитальные затраты", "капитал қўйилмалар", "additions to property"],
    dividendsPaid: ["dividends paid", "тўланган дивиденд", "дивиденды выпл", "дивиденды упл", "дивиденд"],
  };
  // i18n-exempt-end
  const put = (field: string, year: number, v: unknown) => {
    const n = Number(v);
    if (v == null || !isFinite(n)) return;
    (out[field] ||= {})[String(year)] = n;
  };
  for (const key of Object.keys(M)) {
    let chosen: { row: HlfRowLike; years: number[]; subtotal: boolean } | null = null;
    for (const sec of h.sections) {
      const rows = sec?.rows || [];
      const secYears = Array.isArray(sec?.years) && sec.years.length ? sec.years : topYears;
      for (const r of rows) {
        if (!r || r.type === "section_header" || r.type === "subheader") continue;
        const hay = (String(r.label || "") + " " + String(r.mapping || "")).toLowerCase();
        if (!M[key].some((p) => hay.includes(p))) continue;
        const isSub = r.type === "subtotal";
        if (!chosen || (isSub && !chosen.subtotal)) chosen = { row: r, years: secYears, subtotal: isSub };
        if (chosen.subtotal) break;
      }
      if (chosen?.subtotal) break;
    }
    if (chosen) chosen.years.forEach((year, yi) => put(key, year, chosen!.row.values?.[yi]));
  }
  // FCF = CFO − |CapEx| по годам, где есть CFO
  for (const [ys, cfoV] of Object.entries(out["cfo"] || {})) {
    const capex = out["cfi_capex"]?.[ys];
    put("freeCashFlow", Number(ys), cfoV - Math.abs(capex != null ? capex : 0));
  }
  return out;
}
const HLF_FALLBACK = new Set(["cfo", "cfi", "cff", "cfi_capex", "dividendsPaid", "freeCashFlow"]);
function getValue(field: string, year: number): number | null {
  const fieldMap = values.value[field];
  const v = fieldMap ? fieldMap[String(year)] : null;
  if (v != null) return Number(v);
  // Фолбэк на «Высокоуровневые показатели» (HLF) для денежного потока / FCF.
  if (HLF_FALLBACK.has(field)) {
    const hv = hlfCash.value[field]?.[String(year)];
    if (hv != null) return Number(hv);
  }
  return null;
}

function fmtNum(v: number | null): string {
  if (v == null || !isFinite(v)) return "—";
  const abs = Math.abs(v);
  let str: string;
  if (abs >= 1000) str = Math.round(v).toLocaleString(getCurrentIntlLocale(), { maximumFractionDigits: 0 });
  else if (abs >= 10) str = v.toLocaleString(getCurrentIntlLocale(), { maximumFractionDigits: 1 });
  else str = v.toLocaleString(getCurrentIntlLocale(), { maximumFractionDigits: 2 });
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
  { id: "off", label: i18nKey("Прогноз: выкл") },
  { id: "runrate", label: i18nKey("Прогноз: Run-rate") },
  { id: "cagr", label: i18nKey("Прогноз: CAGR") },
  { id: "linear", label: i18nKey("Прогноз: линейный") },
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

// Годовой индикатор компании (sponsorship/taxes/headcount).
function getIndicatorValue(field: string, year: number): number | null {
  const fm = indicators.value[field];
  if (!fm) return null;
  const v = fm[String(year)];
  return v == null ? null : Number(v);
}
// Текущее «сырое» значение поля (фин. или индикатор) — для редактирования.
function curRaw(field: string, year: number): number | null {
  return INDICATOR_IDS.has(field) ? getIndicatorValue(field, year) : getValue(field, year);
}

// Compute KPI values for the header band
interface KpiCardData {
  id: string; src: "fin" | "ind"; label: string; value: string;
  raw: number | null; subtext: string; subColor: string;
}
const kpiCards = computed<KpiCardData[]>(() => {
  return kpis.value.map(kpi => {
    // Удельная себестоимость = COGS / Выручка × 100% (производная, не редактируется).
    if (kpi.id === "unitCostRatio") {
      const rev = getValue("revenue", localYear.value);
      const cogs = getValue("cogs", localYear.value);
      const ratio = (rev != null && cogs != null && rev > 0) ? Math.abs(cogs / rev) * 100 : null;
      return {
        id: kpi.id, src: "fin" as const, label: kpi.label,
        value: ratio == null ? "—" : ratio.toFixed(1) + "%",
        raw: ratio, subtext: t("COGS / выручка"), subColor: "#534AB7",
      };
    }
    const indCurr = curRaw(kpi.id, localYear.value);
    // «Сотрудники»: годовой индикатор, иначе текущий штат компании (employees_count).
    const usingEmpFallback = kpi.id === "headcount" && indCurr == null && companyEmployees.value != null;
    // «Налоги»: если годовой индикатор не заполнен вручную, показываем налог на
    // прибыль из отчётности — ту же строку, что питает налоговый вклад у
    // руководителя. Карточка стояла пустой при заполненной отчётности, и связь
    // между «Налог на прибыль» в редакторе и этой плиткой была не видна.
    const taxFromReport = kpi.id === "taxes" && indCurr == null
      ? getValue("tax", localYear.value) : null;
    const usingTaxFallback = taxFromReport != null;
    const curr = usingEmpFallback
      ? companyEmployees.value
      : (usingTaxFallback ? Math.abs(taxFromReport as number) : indCurr);
    const prevRaw = curRaw(kpi.id, localYear.value - 1);
    const prevTax = kpi.id === "taxes" && prevRaw == null
      ? getValue("tax", localYear.value - 1) : null;
    const prev = prevTax != null ? Math.abs(prevTax) : prevRaw;
    const yoy = fmtYoY(curr, prev);
    // Default subtext: YoY comparison
    let subtext = `${yoy.text} vs ${localYear.value - 1}`;
    let subColor = yoy.color;
    if (curr == null) {
      subtext = t("нет данных");
      subColor = "#94A3B8";
    }
    if (usingEmpFallback) {
      subtext = t("штат компании");
      subColor = "#94A3B8";
    }
    if (usingTaxFallback) {
      subtext = t("налог на прибыль из отчётности");
      subColor = "#B45309";
    }
    // Special: EBITDA → show margin instead of YoY
    if (kpi.id === "ebitda") {
      const rev = getValue("revenue", localYear.value);
      if (curr != null && rev != null && rev > 0) {
        subtext = t("маржа {v}%", { v: ((curr / rev) * 100).toFixed(1) });
      }
    }
    if (kpi.id === "totalAssets" && localStandard.value === "IFRS") {
      // Show debt-to-assets ratio
      const debt = getValue("debt", localYear.value);
      if (curr != null && debt != null && curr > 0) {
        subtext = t("долг {v}% от активов", { v: ((debt / curr) * 100).toFixed(0) });
        subColor = "#534AB7";
      }
    }
    const value = kpi.unit === "people"
      ? (curr == null ? "—" : t("{n} чел.", { n: fmtNum(curr) }))
      : fmtNum(curr);
    return {
      id: kpi.id, src: (kpi.src || "fin"), label: kpi.label,
      value, raw: curr, subtext, subColor,
    };
  });
});

// ─── Инлайн-редактирование (значения KPI/таблицы + ИНН) ───────────────────
function errMsg(e: unknown): string {
  const err = e as { response?: { data?: { detail?: string } }; message?: string };
  return err?.response?.data?.detail || err?.message || t("ошибка");
}
function parseNum(raw: string): number | null {
  const cleaned = raw.replace(/\s/g, "").replace(",", ".").trim();
  if (cleaned === "" || cleaned === "-") return null;
  const n = Number(cleaned);
  return isFinite(n) ? n : null;
}
function isEditing(loc: "kpi" | "cell" | "inn", field: string, year: number): boolean {
  const e = editing.value;
  return !!e && e.loc === loc && e.field === field && e.year === year;
}
function startEdit(loc: "kpi" | "cell", field: string, year: number) {
  if (!canEdit.value || saving.value) return;
  if (field === "unitCostRatio") return;   // производная — не редактируется
  const v = curRaw(field, year);
  editOrig.value = v == null ? "" : String(v);
  editVal.value = editOrig.value;
  editing.value = { loc, field, year };
}
function startEditInn() {
  if (!canEdit.value || saving.value) return;
  editOrig.value = inn.value || "";
  editVal.value = editOrig.value;
  editing.value = { loc: "inn", field: "__inn__", year: 0 };
}
function closeEdit() { editing.value = null; }
function onEditMounted(el: unknown) {
  if (el && el instanceof HTMLInputElement) { el.focus(); el.select(); }
}
async function commitEdit() {
  const e = editing.value;
  if (!e) return;
  editing.value = null;                 // закрыть до blur — без двойного commit
  if (e.loc === "inn") {
    const v = editVal.value.trim();
    if (v === editOrig.value.trim()) return;
    await saveInn(v);
    return;
  }
  if (editVal.value.trim() === editOrig.value.trim()) return;
  const num = parseNum(editVal.value);
  if (INDICATOR_IDS.has(e.field)) await saveIndicator(e.field, e.year, num);
  else await saveFinancial(e.field, e.year, num);
}

async function saveInn(v: string) {
  saving.value = true;
  const prev = inn.value;
  inn.value = v || null;
  try {
    const { api } = await import("@/api/client");
    await api.put(`/financials/companies/${props.companyCode}/indicators`, { set_inn: true, inn: v });
    markEdited();
    toast.success(v ? t("ИНН сохранён") : t("ИНН очищен"));
  } catch (e: unknown) {
    inn.value = prev;   // не сохранено (queued или ошибка) → откат оптимистичного
    // 202 → на модерации: тост показал интерцептор @/api/client, не дублируем.
    if ((e as { __moderation_queued?: boolean })?.__moderation_queued === true) return;
    toast.error(t("Не удалось сохранить ИНН: {e}", { e: errMsg(e) }));
  } finally { saving.value = false; }
}

async function saveIndicator(field: string, year: number, num: number | null) {
  saving.value = true;
  const ys = String(year);
  const prevMap = { ...(indicators.value[field] || {}) };
  const next = { ...prevMap };
  if (num == null) delete next[ys]; else next[ys] = num;
  indicators.value = { ...indicators.value, [field]: next };
  try {
    const { api } = await import("@/api/client");
    await api.put(`/financials/companies/${props.companyCode}/indicators`, {
      indicators: { [field]: { [ys]: num } },
    });
    markEdited();
    toast.success(t("Сохранено"));
  } catch (e: unknown) {
    indicators.value = { ...indicators.value, [field]: prevMap };   // откат (не сохранено)
    // 202 → на модерации: тост показал интерцептор @/api/client, не дублируем.
    if ((e as { __moderation_queued?: boolean })?.__moderation_queued === true) return;
    toast.error(t("Не сохранено: {e}", { e: errMsg(e) }));
  } finally { saving.value = false; }
}

async function saveFinancial(field: string, year: number, num: number | null) {
  saving.value = true;
  const ys = String(year);
  const prevMap = { ...(values.value[field] || {}) };
  values.value = { ...values.value, [field]: { ...prevMap, [ys]: num } };
  // Отметить ручную правку — консистентность с полным редактором МСФО/НСБУ.
  const mf = { ...(manualFlags.value[field] || {}) };
  mf[ys] = true;
  manualFlags.value = { ...manualFlags.value, [field]: mf };
  try {
    const { api } = await import("@/api/client");
    const isIfrs = localStandard.value === "IFRS";
    const url = isIfrs
      ? `/financials/companies/${props.companyCode}/ifrs-editor`
      : `/financials/companies/${props.companyCode}/nsbu-editor`;
    const payload: Record<string, unknown> = {
      values: values.value,
      customFields: customFields.value,
      renames: renames.value,
      formulaOverrides: formulaOverrides.value,
      manualFlags: manualFlags.value,
    };
    if (isIfrs) {
      payload.period = "FY";
      payload.consolidated = true;
      payload.currency = props.currency || "UZS";
      payload.notes = notes.value;
      payload.audit_meta = auditMeta.value;
    }
    await api.put(url, payload);
    markEdited();
    toast.success(t("Сохранено"));
  } catch (e: unknown) {
    values.value = { ...values.value, [field]: prevMap };   // откат (не сохранено)
    // 202 → на модерации: тост показал интерцептор @/api/client, не дублируем.
    if ((e as { __moderation_queued?: boolean })?.__moderation_queued === true) return;
    toast.error(t("Не сохранено: {e}", { e: errMsg(e) }));
  } finally { saving.value = false; }
}

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
    result.push({ field: fieldId, label: renames.value[fieldId] || (rowDef?.label ? t(rowDef.label) : fieldId), text });
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
      parts.push(t("подписан {d}", { d: d.toLocaleDateString(getCurrentIntlLocale()) }));
    } catch { /* noop */ }
  }
  return parts.join(" · ");
});

// ─── Actions ────────────────────────────────────────────────────────────
function onOpenEditor() {
  const routeName = localStandard.value === "IFRS" ? "financials-edit-ifrs" : "financials-edit-nsbu";
  // Передаём компанию → редактор открывается сразу на ней (а не на первой в списке).
  router.push({ name: routeName, query: { company: props.companyCode } });
  emit("close");
}

// Закрытие (оверлей/ESC/скролл-лок берёт на себя EntityDrillShell)
function close() {
  emit("close");
}
</script>

<template>
  <EntityDrillShell :accent="statusBorder" :max-width="980" stripe="left" align="start" :embedded="isEmbedded" @close="close">

      <!-- Header -->
      <div class="cdrl-hdr">
        <div class="cdrl-hdr-left">
          <div class="cdrl-eyebrow">{{ company?.code }} · {{ t(sectorLabel) }}</div>
          <div class="cdrl-title">{{ companyDisplayName(company) || company?.code }}</div>
          <div class="cdrl-badges">
            <span class="cdrl-badge" :class="localStandard === 'IFRS' ? 'badge-ifrs' : 'badge-nsbu'">
              <svg viewBox="0 0 12 12" width="9" height="9" fill="none" stroke="currentColor" stroke-width="1.6"><path d="M2 6h8M2 4h8M2 8h6" /><path v-if="localStandard === 'IFRS'" d="M9 2v8" /></svg>
              {{ localStandard === 'IFRS' ? t('МСФО · 4 секции') : t('НСБУ · форма 2 + 1') }}
            </span>
            <span v-if="auditLine" class="cdrl-badge badge-audit">{{ auditLine }}</span>
            <span v-if="auditMeta?.is_restated" class="cdrl-badge badge-restated">
              <svg viewBox="0 0 12 12" width="9" height="9" fill="none" stroke="currentColor" stroke-width="1.6"><circle cx="6" cy="6" r="4.5" /><path d="M6 3.5v3M6 8v0.1" /></svg>
              RESTATED
            </span>
          </div>
          <!-- ИНН компании — inline-редактируемый -->
          <div class="cdrl-inn">
            <span class="cdrl-inn-lbl">{{ t("ИНН") }}</span>
            <input v-if="isEditing('inn', '__inn__', 0)"
                   :ref="onEditMounted" v-model="editVal"
                   class="cdrl-inn-inp" type="text" inputmode="numeric" maxlength="14"
                   placeholder="—"
                   @keydown.enter.prevent="commitEdit"
                   @keydown.esc.prevent="closeEdit"
                   @blur="commitEdit" />
            <button v-else type="button" class="cdrl-inn-val"
                    :class="{ editable: canEdit }" :disabled="!canEdit"
                    :title="canEdit ? t('Нажмите, чтобы изменить ИНН') : ''"
                    @click="startEditInn">{{ inn || "—" }}</button>
          </div>
        </div>
        <!-- В embedded стандарт задаёт вкладка (ifrs/nsbu), год — степпер воркспейса,
             поэтому свои селекторы прячем; в модалке — как было. -->
        <div v-if="!isEmbedded" class="cdrl-hdr-right">
          <div class="cdrl-seg" role="group" :aria-label="t('Стандарт')">
            <button type="button" :class="{ on: localStandard === 'IFRS' }" @click="localStandard = 'IFRS'">{{ t("МСФО") }}</button>
            <button type="button" :class="{ on: localStandard === 'NSBU' }" @click="localStandard = 'NSBU'">{{ t("НСБУ") }}</button>
          </div>
          <select v-model.number="localYear" class="cdrl-sel" :title="t('Финансовый год')">
            <option v-for="y in yearOptions" :key="y" :value="y">FY {{ y }}</option>
          </select>
          <span class="cdrl-pill-static">{{ currency }}</span>
          <span v-if="localStandard === 'IFRS'" class="cdrl-pill-static">Cons</span>
        </div>
        <!-- embedded: компактный статус-бейдж стандарта/года (read-only, из вкладки) -->
        <div v-else class="cdrl-hdr-right">
          <span class="cdrl-pill-static">FY {{ localYear }}</span>
          <span class="cdrl-pill-static">{{ currency }}</span>
          <span v-if="localStandard === 'IFRS'" class="cdrl-pill-static">Cons</span>
        </div>
      </div>

      <!-- Error state -->
      <div v-if="fetchError" class="cdrl-error">
        <svg viewBox="0 0 16 16" width="14" height="14" fill="none" stroke="currentColor" stroke-width="1.6"><circle cx="8" cy="8" r="6.5" /><path d="M8 5v4M8 11v0.1" /></svg>
        {{ fetchError }}
      </div>

      <!-- KPI band — все карточки в один ряд (колонок = числу карточек) -->
      <div v-else class="cdrl-kpis" :class="{ 'cdrl-kpis-many': kpiCards.length >= 7 }"
           :style="{ gridTemplateColumns: `repeat(${kpiCards.length}, minmax(0, 1fr))` }">
        <div v-for="(kpi, idx) in kpiCards" :key="idx" class="cdrl-kpi" :class="{ 'cdrl-kpi-ind': kpi.src === 'ind' }">
          <div class="cdrl-kpi-lbl">{{ t(kpi.label) }}</div>
          <div class="cdrl-kpi-val">
            <template v-if="loading">…</template>
            <input v-else-if="isEditing('kpi', kpi.id, localYear)"
                   :ref="onEditMounted" v-model="editVal"
                   class="cdrl-edit-inp cdrl-kpi-inp" type="text" inputmode="decimal"
                   @keydown.enter.prevent="commitEdit"
                   @keydown.esc.prevent="closeEdit"
                   @blur="commitEdit" />
            <button v-else type="button" class="cdrl-kpi-valbtn"
                    :class="{ editable: canEdit }" :disabled="!canEdit"
                    @click="startEdit('kpi', kpi.id, localYear)">{{ kpi.value }}</button>
          </div>
          <div class="cdrl-kpi-sub" :style="{ color: kpi.subColor }">{{ kpi.subtext }}</div>
        </div>
      </div>

      <!-- Tabs -->
      <div v-if="!fetchError" class="cdrl-tabs">
        <div class="cdrl-tabs-left">
          <button v-for="sec in sections" :key="sec.id"
                  class="cdrl-tab" :class="{ on: activeSection === sec.id }"
                  @click="activeSection = sec.id">{{ t(sec.label) }}</button>
        </div>
        <select v-model="fcModel" class="cdrl-fc-select" :title="t('Прогноз будущих лет')">
          <option v-for="o in FC_OPTS" :key="o.id" :value="o.id">{{ t(o.label) }}</option>
        </select>
      </div>

      <!-- Table -->
      <div v-if="!fetchError" class="cdrl-table-wrap">
        <table class="cdrl-table">
          <thead>
            <tr>
              <th v-if="localStandard === 'NSBU'" class="cdrl-th-code">{{ t("Код") }}</th>
              <th class="cdrl-th-name">{{ t("Показатель") }}</th>
              <th v-for="y in displayYears" :key="y" class="cdrl-th-num" :class="{ current: y === localYear, fc: isFcYear(y) }">{{ y }}<span v-if="isFcYear(y)" class="cdrl-fc-tag">{{ t("П") }}</span></th>
              <th class="cdrl-th-yoy">YoY</th>
              <th v-if="localStandard === 'IFRS'" class="cdrl-th-note"></th>
            </tr>
          </thead>
          <tbody>
            <template v-for="row in sections.find(s => s.id === activeSection)?.rows || []" :key="row.id">
              <tr v-if="row.groupHeader" class="cdrl-group">
                <td :colspan="displayYears.length + 3">{{ t(row.groupHeader) }}</td>
              </tr>
              <tr :class="{ 'cdrl-sub': row.isSubtotal, 'cdrl-highlight': row.isHighlight }">
                <td v-if="localStandard === 'NSBU'" class="cdrl-td-code">{{ row.code || "" }}</td>
                <td class="cdrl-td-name">{{ renames[row.id] || t(row.label) }}</td>
                <td v-for="y in displayYears" :key="y"
                    class="cdrl-td-num"
                    :class="{ current: y === localYear, fc: isFcYear(y), editable: canEdit && !isFcYear(y), on: isEditing('cell', row.id, y) }">
                  <input v-if="isEditing('cell', row.id, y)"
                         :ref="onEditMounted" v-model="editVal"
                         class="cdrl-edit-inp cdrl-cell-inp" type="text" inputmode="decimal"
                         @keydown.enter.prevent="commitEdit"
                         @keydown.esc.prevent="closeEdit"
                         @blur="commitEdit" />
                  <button v-else-if="canEdit && !isFcYear(y)" type="button"
                          class="cdrl-cell-btn" @click="startEdit('cell', row.id, y)">{{ fmtNum(cellValue(row.id, y)) }}</button>
                  <template v-else>{{ fmtNum(cellValue(row.id, y)) }}</template>
                </td>
                <td class="cdrl-td-yoy" :style="{ color: getRowValues(row.id).yoy.color }">{{ getRowValues(row.id).yoy.text }}</td>
                <td v-if="localStandard === 'IFRS'" class="cdrl-td-note">
                  <span v-if="hasNote(row.id)" class="cdrl-note-dot" :title="notes[row.id]">●</span>
                </td>
              </tr>
            </template>
            <tr v-if="loading">
              <td :colspan="displayYears.length + 3" class="cdrl-loading">{{ t("Загрузка…") }}</td>
            </tr>
          </tbody>
        </table>
      </div>

      <!-- Notes for active IFRS section -->
      <div v-if="localStandard === 'IFRS' && sectionNotes.length > 0" class="cdrl-notes">
        <div v-for="(n, idx) in sectionNotes" :key="idx" class="cdrl-note-row">
          <span class="cdrl-note-dot">●</span>
          <div class="cdrl-note-content">
            <span class="cdrl-note-label">{{ t(n.label) }}:</span>
            <span class="cdrl-note-text">{{ n.text }}</span>
          </div>
        </div>
      </div>

      <!-- Footer -->
      <div class="cdrl-ftr">
        <span class="cdrl-ftr-info">{{ lastEditedText }}</span>
        <div class="cdrl-ftr-actions">
          <!-- Кнопка редактора видна только при праве на правку финансов:
               маршрут редактора требует financials.edit, и без права роутер
               мягко выбрасывал пользователя на «Проекты трансформации» —
               кнопка выглядела рабочей, а вела не туда. -->
          <button v-if="canEdit" class="cdrl-btn-cta" :class="localStandard === 'IFRS' ? 'cta-ifrs' : 'cta-nsbu'" @click="onOpenEditor">
            {{ t("Открыть в редакторе {std}", { std: localStandard === 'IFRS' ? t('МСФО') : t('НСБУ') }) }}
          </button>
        </div>
      </div>

  </EntityDrillShell>
</template>

<style scoped>
/* Chrome (оверлей, карточка, акцент-полоса слева, блик, свечение, крестик, ESC,
   скролл-лок) вынесен в общий EntityDrillShell. Здесь только тело модалки. */

/* ─── Header ─── */
.cdrl-hdr {
  /* right-паддинг 50px резервирует место под крестик EntityDrillShell (он
     absolute в правом-верхнем углу), иначе пилюля валюты заезжает под него. */
  padding: 16px 50px 12px 22px;
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
  position: relative; overflow: hidden;
}
.cdrl-kpi::before {
  content: ""; position: absolute; top: 0; left: 0; right: 0; height: 3px;
  background: var(--accent, #7F77DD);
  border-radius: inherit; border-bottom-left-radius: 0; border-bottom-right-radius: 0;
  pointer-events: none;
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

/* Компактная раскладка при 7+ карточках (4/6 фин. + 3 индикатора компании) */
.cdrl-kpis-many { grid-template-columns: repeat(auto-fit, minmax(122px, 1fr)); }
.cdrl-kpis-many .cdrl-kpi { padding: 12px 11px; }
.cdrl-kpis-many .cdrl-kpi-lbl { font-size: 9px; }
.cdrl-kpis-many .cdrl-kpi-val { font-size: 18px; letter-spacing: -0.02em; }
.cdrl-kpis-many .cdrl-kpi-sub { font-size: 10px; }
/* Карточки-индикаторы компании — верхний акцент (НЕ left-border) */
.cdrl-kpi-ind { box-shadow: inset 0 2px 0 rgba(127, 119, 221, 0.45); }

/* ─── ИНН (шапка) ─── */
.cdrl-inn { display: inline-flex; align-items: center; gap: 7px; margin-top: 8px; }
.cdrl-inn-lbl {
  font-size: 9px; font-weight: 600; letter-spacing: 0.08em;
  text-transform: uppercase; color: var(--t3, #94A3B8);
}
.cdrl-inn-val {
  font-family: inherit; font-size: 12px; font-weight: 600; color: var(--t1, #1E2A4A);
  background: var(--bg2, #F1F0FB); border: 1px solid var(--border-input);
  border-radius: 6px; padding: 2px 9px; cursor: default;
  font-feature-settings: 'tnum'; letter-spacing: 0.02em;
}
.cdrl-inn-val.editable { cursor: pointer; transition: background .12s, border-color .12s; }
.cdrl-inn-val.editable:hover { background: rgba(127, 119, 221, 0.12); border-color: var(--p, #7C6FF7); }
.cdrl-inn-inp {
  font-family: inherit; font-size: 12px; font-weight: 600; width: 132px;
  padding: 2px 8px; border-radius: 6px; border: 1px solid var(--p, #7C6FF7);
  outline: none; box-shadow: 0 0 0 3px rgba(124, 111, 247, 0.15);
  font-feature-settings: 'tnum'; color: var(--t1, #1E2A4A);
}

/* ─── Inline-редактирование значений (KPI + ячейки таблицы) ─── */
.cdrl-edit-inp {
  font-family: inherit; border: 1px solid var(--p, #7C6FF7); border-radius: 6px;
  background: var(--bg1, #fff); color: var(--t1, #1E2A4A); outline: none;
  box-shadow: 0 0 0 3px rgba(124, 111, 247, 0.15); font-feature-settings: 'tnum';
}
.cdrl-kpi-inp { width: 100%; font-size: 18px; font-weight: 500; padding: 1px 6px; letter-spacing: -0.02em; }
.cdrl-cell-inp { width: 100%; max-width: 96px; text-align: right; font-size: 12px; padding: 1px 5px; }
.cdrl-kpi-valbtn {
  font-family: inherit; font-size: inherit; font-weight: inherit; letter-spacing: inherit;
  color: inherit; background: transparent; border: none; padding: 0; text-align: left;
  cursor: default; font-feature-settings: 'tnum';
}
.cdrl-kpi-valbtn.editable { cursor: pointer; border-radius: 5px; transition: background .12s, box-shadow .12s; }
.cdrl-kpi-valbtn.editable:hover { background: rgba(127, 119, 221, 0.10); box-shadow: 0 0 0 4px rgba(127, 119, 221, 0.06); }
.cdrl-cell-btn {
  font: inherit; font-size: inherit; color: inherit; background: transparent;
  border: none; padding: 1px 3px; margin: -1px -3px; cursor: pointer;
  border-radius: 4px; text-align: right; width: 100%;
  font-feature-settings: 'tnum'; transition: background .12s;
}
.cdrl-cell-btn:hover { background: rgba(127, 119, 221, 0.12); }
.cdrl-td-num.on { padding: 2px 8px; }

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
