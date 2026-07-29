<!--
  ExecDashFinanceBlock — Pack 3 (Заход 2 из 3): Header + KPI 6-card + Sector filter + 9-col table.
  Заход 3: expand-row + sparkline 5Л
-->
<script setup lang="ts">
import { computed, onMounted, onBeforeUnmount, ref, watch } from "vue";
import { useExecutiveDashboardFinance } from "@/composables/useExecutiveDashboardFinance";
import { useExecutiveDashboard } from "@/composables/useExecutiveDashboard";
import HighLevelFinancials from "@/components/Financials/HighLevelFinancials.vue";
import UzaSegment from "@/components/UZA/UzaSegment.vue";
import UzaSelect from "@/components/UZA/UzaSelect.vue";
import { useNumberTween } from "@/composables/useNumberTween";
import {
  computePortfolioKpis,
  ensureFinancialsCss,
  fmtPct,
  fmtPctSigned,
} from "@/components/Financials/financialsHelpers";
import { useSectorMeta } from "@/utils/sectorMeta";
import { useFormatters } from "@/composables/useFormatters";
import FinanceDrillModal, { type FinKpiKind } from "@/components/UZA/FinanceDrillModal.vue";
import Odometer from "@/components/Odometer.vue";
import UzaStateBlock from "@/components/UZA/UzaStateBlock.vue";
import { useI18n } from "@/composables/useI18n";

const { t } = useI18n();
const fmt = useFormatters();

// Pack 7.23: inject fin animation kit (finKpiCardIn / finKpi2DrawIn /
// finKpi2Breathe / finShimmer) so the KPI top-stripes get the same
// drawing + breathing + shimmer treatment as the Налоговый вклад block.
onMounted(() => { ensureFinancialsCss(); });

const fin = useExecutiveDashboardFinance();
const exec = useExecutiveDashboard();

// Pack 7.15 / 7.17: the pills row is now a fully-bidirectional controller
// of the topbar sector filter. Clicking a pill calls exec.setSectors() so:
//   1) Backend re-fetches with the new sectors filter (cleaner — KPI totals
//      come from the server, not from a partial client-side narrowing of
//      summary.items)
//   2) Topbar dropdown auto-syncs because it reads the same exec.selectedSectors
//   3) Other dashboard blocks (governance, ratings, etc.) re-filter too
const finSectorFilter = ref<string>("all");

// Pack 7.17: clicking a sector pill drives the global filter
function setSector(code: string): void {
  if (code === "all") {
    exec.clearSectors();
  } else {
    exec.setSectors([code]);
  }
}

// Sync from topbar -> local on every change
watch(() => exec.selectedSectors.value, (sel) => {
  if (!sel || sel.length === 0) {
    finSectorFilter.value = "all";
  } else if (sel.length === 1) {
    finSectorFilter.value = sel[0];
  } else {
    // Multiple sectors selected — show "all" locally; narrowedSummary uses
    // the exec list directly via activeSectorSet below.
    finSectorFilter.value = "all";
  }
}, { immediate: true });

// The actual filter set used by narrowedSummary — prefer exec.selectedSectors
// when non-empty, otherwise interpret finSectorFilter (local override).
const activeSectorSet = computed<Set<string> | null>(() => {
  const sel = exec.selectedSectors.value;
  if (sel && sel.length > 0) return new Set(sel);
  if (finSectorFilter.value && finSectorFilter.value !== "all") {
    return new Set([finSectorFilter.value]);
  }
  return null;
});

const tasksYear = computed(() => exec.year.value);

const narrowedSummary = computed(() => {
  const s = fin.summary.value;
  if (!s) return null;
  const set = activeSectorSet.value;
  // Фильтр по компаниям из общего пикера экзек-дашборда (1 или несколько).
  const coSet = exec.selectedCompanies.value.length
    ? new Set(exec.selectedCompanies.value)
    : null;
  if (!set && !coSet) return s;

  // Filter items by canonicalized sector_code so legacy DB codes like
  // "mining_metallurgy" / "oil_gas" / "transport_telecom" map to the
  // bucket the pills use (mining / oilgas / transport). Затем — по компаниям.
  let filteredItems = s.items;
  if (set) filteredItems = filteredItems.filter(it => set.has(canonSector(it.sector_code)));
  if (coSet) filteredItems = filteredItems.filter(it => coSet.has(it.company_id));

  // Pack 7.18: recompute portfolio_totals_by_year from the FILTERED items.
  // The KPI cards (revenue, profit, EBITDA, assets, debt, FCF) read totals
  // from this map directly; without this recompute they would keep showing
  // the server's full-portfolio totals (the original "цифры не меняются" bug).
  const newTotals: Record<number, Record<string, number>> = {};
  for (const item of filteredItems) {
    if (!item.by_year) continue;
    for (const [yearStr, metrics] of Object.entries(item.by_year)) {
      const y = Number(yearStr);
      if (!metrics || isNaN(y)) continue;
      if (!newTotals[y]) newTotals[y] = {};
      for (const [code, value] of Object.entries(metrics)) {
        if (value == null || isNaN(Number(value))) continue;
        newTotals[y][code] = (newTotals[y][code] || 0) + Number(value);
      }
    }
  }

  // Coverage also needs updating so "N компаний с данными" reflects the filter.
  const newCoverage = s.coverage
    ? {
        ...s.coverage,
        companies_total: filteredItems.length,
        with_revenue_any_year: filteredItems.filter(it =>
          it.by_year && Object.values(it.by_year).some(m =>
            m && m.revenue != null && Number(m.revenue) !== 0
          )
        ).length,
      }
    : s.coverage;

  return {
    ...s,
    items: filteredItems,
    portfolio_totals_by_year: newTotals,
    coverage: newCoverage,
  };
});

// Year-fallback: если за выбранный год нет данных по выручке — показываем
// последний доступный год с данными (как в BP-tracker). Иначе на FY без данных
// KPI выручки/прибыли пустые, хотя за прошлый год данные есть.
const effectiveFinYear = computed(() => {
  const s = narrowedSummary.value;
  const sel = fin.year.value;
  if (!s) return sel;
  const totals: Record<number, Record<string, number>> = (s.portfolio_totals_by_year as any) || {};
  const hasData = (y: number) => {
    const m = totals[y];
    return !!m && Object.values(m).some((v) => Number(v) !== 0);
  };
  if (hasData(sel)) return sel;
  const yearsWithData = Object.keys(totals).map(Number).filter(hasData).sort((a, b) => b - a);
  const pastOrEqual = yearsWithData.filter((y) => y <= sel);
  return pastOrEqual[0] ?? yearsWithData[0] ?? sel;
});
const isFallbackYear = computed(() => effectiveFinYear.value !== fin.year.value);

const kpis = computed(() =>
  narrowedSummary.value
    ? computePortfolioKpis(narrowedSummary.value, effectiveFinYear.value)
    : null
);

// ─── Детальная отчётность компании при фокусе на 1 компании (Image #4) ───
// Раскрывается под KPI-карточками: KEY METRICS + сворачиваемый отчёт (HLF).
const showStatement = ref(true);
const hlfCompanies = computed(() =>
  (fin.summary.value?.items || []).map((it: any) => ({
    code: it.company_code,
    name_short: it.company_name_short,
    name_ru: it.company_name,
  })) as any,
);
const focusedItem = computed(() => {
  if (exec.selectedCompanies.value.length !== 1) return null;
  const id = exec.selectedCompanies.value[0];
  return (fin.summary.value?.items || []).find((x: any) => x.company_id === id) || null;
});
const focusedCompanyCode = computed<string | null>(() => (focusedItem.value as any)?.company_code || null);
const focusedCompanyName = computed(() =>
  (focusedItem.value as any)?.company_name_short || (focusedItem.value as any)?.company_name || focusedCompanyCode.value || "",
);

const cosWithRevenue = computed<number>(() => {
  if (!narrowedSummary.value) return 0;
  return narrowedSummary.value.items.filter(it => {
    const yCur = (it.by_year as any)[effectiveFinYear.value];
    if (!yCur) return false;
    const rev = Number(yCur.revenue);
    return !isNaN(rev) && rev !== 0;
  }).length;
});

const totalCos = computed<number>(() => narrowedSummary.value?.coverage?.companies_total ?? 22);
const cosMissing = computed<number>(() => Math.max(0, totalCos.value - cosWithRevenue.value));

const availableYears = computed<number[]>(() => {
  const s = fin.summary.value;
  if (!s) return [2024, 2023, 2022, 2021];
  const ys = Object.keys(s.portfolio_totals_by_year).map(Number).filter(y => !isNaN(y));
  return ys.sort((a, b) => b - a);
});

// Pack 7.20: sector metadata comes from a single source — useSectorMeta —
// which reads sector.name_ru from companies store (admin-editable in
// Companies admin) and applies fixed colours/canonical-code normalisation.
// The local maps that used to live here are gone; sectorMeta is now a
// computed Record<code, {label, short, color}> mirroring the old shape so
// the template doesn't have to change.
const secMeta = useSectorMeta();
// string-index доступ из шаблона (sectorMeta[r.sector]) — допускаем любой код.
const sectorMeta = secMeta.byCodeMap as Record<string, (typeof secMeta.byCodeMap)[keyof typeof secMeta.byCodeMap]>;
const sectorOrder = secMeta.SECTOR_ORDER;
const canonSector = secMeta.canonCode;

// Pack 7.15: show ALL sectors (sectorOrder) regardless of whether they
// have financial data. This keeps the filter pills in sync with the global
// topbar (which also lists all sectors). Sectors without data still get
// computed totals of 0; users see a complete sector list and know which
// are missing rather than the pills row silently shrinking.
const availableSectors = computed<readonly string[]>(() => sectorOrder);

const unitScale = computed(() => {
  if (fin.unit.value === "ths") return 1_000;
  if (fin.unit.value === "mln") return 1_000_000;
  return 1_000_000_000;
});
const unitLabel = computed(() => {
  if (fin.unit.value === "ths") return t("тыс.");
  if (fin.unit.value === "mln") return t("млн");
  return t("млрд");
});
const currencyLabel = computed(() => fin.currency.value);
const standardLabel = computed(() => fin.standard.value === "IFRS" ? t("МСФО") : t("НСБУ"));

function fmtNum(value: number | null | undefined): string {
  if (value == null || isNaN(value)) return "—";
  const scaled = value / unitScale.value;
  if (Math.abs(scaled) >= 1000) {
    return fmt.fmtNumber(Math.round(scaled));
  }
  return Math.abs(scaled) < 10
    ? fmt.fmtNumber(scaled, { decimals: 1, minDecimals: 1 })
    : fmt.fmtNumber(Math.round(scaled));
}

function setBriefing() { fin.setViewMode("company"); }
function setAnalytics() { fin.setViewMode("summary"); }

// Опции единых фильтров (UzaSegment / UzaSelect) — computed, чтобы label
// перерисовывался при смене языка.
const FIN_VIEW_OPTS = computed(() => [{ value: "summary", label: t("Аналитика") }, { value: "company", label: t("Брифинг") }]);
const FIN_STD_OPTS = computed(() => [{ value: "IFRS", label: t("МСФО") }, { value: "NSBU", label: t("НСБУ") }]);
const finYearOpts = computed(() => availableYears.value.map((y) => ({ value: y, label: String(y) })));

// Pack 7.32: список компаний свёрнут по умолчанию — пользователь видит
// только агрегатные KPI-карточки; разворачивает явным кликом.
const listExpanded = ref<boolean>(false);

// Pack 7.32: drill-down модалка для 6 KPI-карточек
const drillKind = ref<FinKpiKind | null>(null);
function openDrill(kind: FinKpiKind) {
  if (!extKpis.value) return; // нет данных — не открываем
  drillKind.value = kind;
}
function closeDrill() {
  drillKind.value = null;
}
function onKpiKeydown(e: KeyboardEvent, kind: FinKpiKind) {
  if (e.key === "Enter" || e.key === " ") {
    e.preventDefault();
    openDrill(kind);
  }
}

// ─── Расширенные KPI ───────────────────────────────────────────
interface ExtKpis {
  totalRevenue: number;
  revenueYoYPct: number;
  netProfit: number;
  netMargin: number;
  ebitda: number;
  ebitdaMargin: number;
  totalAssets: number;
  totalDebt: number;
  debtToEquity: number | null;
  freeCashFlow: number;
  roe: number | null;
  cfo: number;
  cfi: number;
  lossMakingCount: number;
  cosWithData: number;
  accountsReceivable: number;
  accountsPayable: number;
}

const extKpis = computed<ExtKpis | null>(() => {
  if (!narrowedSummary.value || !kpis.value) return null;
  const totals = narrowedSummary.value.portfolio_totals_by_year[effectiveFinYear.value] || {};
  const get = (k: string): number => Number(totals[k]) || 0;
  const totalAssets = get("totalAssets");
  const equity = get("equity");
  const debt = get("debt") || (get("ltBorrowings") + get("stBorrowings"));
  const cfo = get("cfo");
  const cfi = get("cfi");
  const fcf = cfo + cfi;
  const netProfit = kpis.value.totalNetProfit;
  const roe = equity > 0 ? (netProfit / equity) * 100 : null;
  const dToE = equity > 0 ? debt / equity : null;
  return {
    totalRevenue: kpis.value.totalRevenue,
    revenueYoYPct: kpis.value.revenueYoYPct,
    netProfit, netMargin: kpis.value.netMargin,
    ebitda: kpis.value.totalEbitda, ebitdaMargin: kpis.value.ebitdaMargin,
    totalAssets, totalDebt: debt, debtToEquity: dToE,
    freeCashFlow: fcf, roe, cfo, cfi,
    lossMakingCount: kpis.value.lossMakingCount,
    cosWithData: kpis.value.companiesInYear,
    accountsReceivable: get("accountsReceivable"),
    accountsPayable: get("accountsPayable"),
  };
});

// 2026-05-26: countup для 6 KPI cards (Revenue, NetProfit, EBITDA, Assets,
// Debt, FCF) — анимация перезапускается при смене года/сектора (через
// reactive extKpis). Безопасно к null (returns 0 if extKpis null).
const tRevenue       = useNumberTween(() => extKpis.value?.totalRevenue ?? 0, { duration: 900 });
const tRevenueYoY    = useNumberTween(() => extKpis.value?.revenueYoYPct ?? 0, { duration: 900 });
const tNetProfit     = useNumberTween(() => extKpis.value?.netProfit ?? 0, { duration: 900 });
const tNetMargin     = useNumberTween(() => extKpis.value?.netMargin ?? 0, { duration: 900 });
const tEbitda        = useNumberTween(() => extKpis.value?.ebitda ?? 0, { duration: 900 });
const tEbitdaMargin  = useNumberTween(() => extKpis.value?.ebitdaMargin ?? 0, { duration: 900 });
const tAssets        = useNumberTween(() => extKpis.value?.totalAssets ?? 0, { duration: 900 });
const tCosWithData   = useNumberTween(() => extKpis.value?.cosWithData ?? 0, { duration: 900 });
const tDebt          = useNumberTween(() => extKpis.value?.totalDebt ?? 0, { duration: 900 });
const tDebtToEquity  = useNumberTween(() => extKpis.value?.debtToEquity ?? 0, { duration: 900 });
const tFcf           = useNumberTween(() => extKpis.value?.freeCashFlow ?? 0, { duration: 900 });
const tRoe           = useNumberTween(() => extKpis.value?.roe ?? 0, { duration: 900 });
const tAccountsReceivable = useNumberTween(() => extKpis.value?.accountsReceivable ?? 0, { duration: 900 });
const tAccountsPayable    = useNumberTween(() => extKpis.value?.accountsPayable ?? 0, { duration: 900 });

// ─── Таблица: rows + sortable ─────────────────────────────────
interface CompanyRow {
  idx: number;
  id: string;
  code: string;
  name: string;
  sector: string;
  revenue: number | null;
  profit: number | null;
  assets: number | null;
  debt: number | null;
  cfo: number | null;
  cfi: number | null;
  ebitda: number | null;
  ebitdaPct: number | null;  // EBITDA / revenue
  yoy: number | null;        // revenue YoY
  trend5y: (number | null)[]; // [y-4 ... y]
  breakdown: YearBreakdown[]; // 5 годов с revenue/profit
  hasData: boolean;
}

type SortKey = "name" | "sector" | "revenue" | "profit" | "assets" | "debt" | "cfo" | "ebitdaPct" | "yoy";
const sortBy = ref<SortKey>("revenue");
const sortDir = ref<"asc" | "desc">("desc");
const expandedRows = ref<Set<string>>(new Set());

function toggleRow(id: string) {
  const s = new Set(expandedRows.value);
  if (s.has(id)) s.delete(id);
  else s.add(id);
  expandedRows.value = s;
}

interface YearBreakdown {
  year: number;
  revenue: number | null;
  profit: number | null;
}

function setSort(k: SortKey) {
  if (sortBy.value === k) {
    sortDir.value = sortDir.value === "asc" ? "desc" : "asc";
  } else {
    sortBy.value = k;
    sortDir.value = (k === "name" || k === "sector") ? "asc" : "desc";
  }
}

// a11y: aria-sort value для заголовка таблицы
function ariaSort(k: SortKey): "ascending" | "descending" | "none" {
  if (sortBy.value !== k) return "none";
  return sortDir.value === "asc" ? "ascending" : "descending";
}
function onSortKeydown(e: KeyboardEvent, k: SortKey) {
  if (e.key === "Enter" || e.key === " ") {
    e.preventDefault();
    setSort(k);
  }
}
function onRowKeydown(e: KeyboardEvent, id: string) {
  if (e.key === "Enter" || e.key === " ") {
    e.preventDefault();
    toggleRow(id);
  }
}

function arr(v: any): number | null {
  if (v == null || v === "") return null;
  const n = Number(v);
  return isNaN(n) ? null : n;
}

const tableRows = computed<CompanyRow[]>(() => {
  if (!narrowedSummary.value) return [];
  const Y = effectiveFinYear.value;
  const rows: CompanyRow[] = [];
  for (const it of narrowedSummary.value.items) {
    const yCur: any = (it.by_year as any)[Y] || {};
    const yPrev: any = (it.by_year as any)[Y - 1] || {};
    const revenue = arr(yCur.revenue);
    const profit = arr(yCur.profit);
    const assets = arr(yCur.totalAssets);
    const debt = arr(yCur.debt) ?? ((arr(yCur.ltBorrowings) ?? 0) + (arr(yCur.stBorrowings) ?? 0) || null);
    const cfo = arr(yCur.cfo);
    const cfi = arr(yCur.cfi);
    const ebitda = arr(yCur.ebitda);
    const ebitdaPct = (revenue && ebitda && revenue !== 0) ? (ebitda / revenue) * 100 : null;
    const prevRev = arr(yPrev.revenue);
    const yoy = (prevRev && revenue) ? ((revenue - prevRev) / prevRev) * 100 : null;
    const trend5y: (number | null)[] = [];
    const breakdown: YearBreakdown[] = [];
    for (let yr = Y - 4; yr <= Y; yr++) {
      const yd: any = (it.by_year as any)[yr] || {};
      const rv = arr(yd.revenue);
      trend5y.push(rv);
      breakdown.push({ year: yr, revenue: rv, profit: arr(yd.profit) });
    }
    const hasData = revenue !== null || profit !== null || ebitda !== null;
    if (!hasData) continue;
    rows.push({
      idx: 0,
      id: it.company_id,
      code: it.company_code,
      name: it.company_name_short || it.company_name || it.company_code,
      sector: canonSector(it.sector_code),
      revenue, profit, assets, debt, cfo, cfi, ebitda, ebitdaPct, yoy, trend5y, breakdown, hasData,
    });
  }
  // sort
  const dir = sortDir.value === "asc" ? 1 : -1;
  const k = sortBy.value;
  rows.sort((a, b) => {
    if (k === "name" || k === "sector") {
      return ((a as any)[k] || "").localeCompare((b as any)[k] || "", "ru") * dir;
    }
    const av = (a as any)[k];
    const bv = (b as any)[k];
    if (av == null && bv == null) return 0;
    if (av == null) return 1;
    if (bv == null) return -1;
    return (av - bv) * dir;
  });
  rows.forEach((r, i) => r.idx = i + 1);
  return rows;
});

// Mini sparkline
function trendPoints(values: (number | null)[]): { d: string; up: boolean } {
  const valid = values.map((v, i) => ({ v, i })).filter(p => p.v != null) as { v: number; i: number }[];
  if (valid.length < 2) return { d: "", up: true };
  const min = Math.min(...valid.map(p => p.v));
  const max = Math.max(...valid.map(p => p.v));
  const range = max - min || 1;
  const W = 64, H = 18;
  const stepX = W / (values.length - 1);
  const pts = valid.map(p => {
    const x = (p.i * stepX).toFixed(1);
    const y = (H - ((p.v - min) / range) * H).toFixed(1);
    return `${x},${y}`;
  });
  const up = valid[valid.length - 1].v >= valid[0].v;
  return { d: "M " + pts.join(" L "), up };
}

// ─── Брифинг: ИПЦ Узбекистан (год → инфляция % YoY) ────────────
// Источник: ЦБ РУз годовые данные. Cumulative deflator считается от базового года.
const CPI_UZ: Record<number, number> = {
  2020: 11.1, 2021: 10.0, 2022: 12.3, 2023: 8.8, 2024: 9.8, 2025: 9.5,
};

function cumulativeInflation(fromY: number, toY: number): number {
  if (toY <= fromY) return 0;
  let factor = 1;
  for (let y = fromY + 1; y <= toY; y++) {
    const cpi = CPI_UZ[y] ?? 9.0;
    factor *= 1 + cpi / 100;
  }
  return (factor - 1) * 100;
}

interface BriefMetric {
  label: string;
  accent: "violet" | "teal" | "red";
  current: number;
  unit: string;
  serie: { year: number; value: number | null }[];
  yoy: number | null;          // %, last vs prev year
  nominal5y: number | null;    // %, current vs first year of serie
  real5y: number | null;       // %, deflated by cumulative CPI
  comment: string;
  positiveDelta: boolean;       // для долга — рост это негатив
}

function deltaClass(value: number | null, positiveIsGood: boolean): string {
  if (value == null) return "";
  const isPos = value >= 0;
  const good = positiveIsGood ? isPos : !isPos;
  return good ? "p" : "n";
}

function buildBriefMetrics(): BriefMetric[] | null {
  if (!narrowedSummary.value || !extKpis.value) return null;
  const Y = effectiveFinYear.value;
  const totals = narrowedSummary.value.portfolio_totals_by_year;

  const buildSerie = (key: string): { year: number; value: number | null }[] => {
    const out: { year: number; value: number | null }[] = [];
    for (let y = Y - 4; y <= Y; y++) {
      const t: any = totals[y] || {};
      const raw = t[key];
      const v = raw == null ? null : Number(raw) / unitScale.value;
      out.push({ year: y, value: (v != null && !isNaN(v)) ? v : null });
    }
    return out;
  };

  const buildOne = (
    label: string, accent: "violet" | "teal" | "red", key: string,
    posIsGood: boolean, commentFn: (m: BriefMetric) => string,
    altKey?: string
  ): BriefMetric | null => {
    let serie = buildSerie(key);
    // fallback: для долга часто используется "debt" но может быть пусто — попробуем сумму ltBorrowings+stBorrowings
    if (altKey && serie.every(p => p.value == null)) {
      const lt = buildSerie("ltBorrowings");
      const st = buildSerie("stBorrowings");
      serie = lt.map((p, i) => ({
        year: p.year,
        value: (p.value != null || st[i].value != null)
          ? ((p.value || 0) + (st[i].value || 0))
          : null,
      }));
    }
    const validIdx = serie.map((p, i) => p.value != null ? i : -1).filter(i => i >= 0);
    if (validIdx.length === 0) return null;
    const lastIdx = validIdx[validIdx.length - 1];
    const firstIdx = validIdx[0];
    const last = serie[lastIdx].value!;
    const prev = lastIdx > 0 && serie[lastIdx - 1].value != null ? serie[lastIdx - 1].value! : null;
    const first = serie[firstIdx].value!;
    const yoy = (prev != null && prev !== 0) ? ((last - prev) / Math.abs(prev)) * 100 : null;
    const nom5 = (first !== 0) ? ((last - first) / Math.abs(first)) * 100 : null;
    let real5: number | null = null;
    if (nom5 != null) {
      const fromYear = serie[firstIdx].year;
      const toYear = serie[lastIdx].year;
      const cumInfl = cumulativeInflation(fromYear, toYear);
      real5 = ((1 + nom5 / 100) / (1 + cumInfl / 100) - 1) * 100;
    }
    const m: BriefMetric = {
      label, accent, current: last, unit: `${unitLabel.value} ${currencyLabel.value}`,
      serie, yoy, nominal5y: nom5, real5y: real5,
      comment: "",
      positiveDelta: posIsGood,
    };
    m.comment = commentFn(m);
    return m;
  };

  const revenue = buildOne(
    t("Совокупная выручка"), "violet", "revenue", true,
    (m) => {
      if (m.real5y == null) return "—";
      if (m.real5y > 5) return t("Номинальный рост уверенно опережает инфляцию — реальное расширение портфеля.");
      if (m.real5y > 0) return t("Номинальный рост незначительно опережает инфляцию.");
      if (m.real5y > -5) return t("Номинальный рост близок к инфляции — реальная стагнация.");
      return t("Номинальный рост отстаёт от инфляции — реальное сжатие выручки.");
    }
  );

  const profit = buildOne(
    t("Чистая прибыль"), "teal", "profit", true,
    (m) => {
      if (m.current < 0) return t("Портфель в убытке.");
      const margin = (extKpis.value && extKpis.value.totalRevenue > 0)
        ? (m.current * unitScale.value / extKpis.value.totalRevenue) * 100 : 0;
      if (m.real5y == null) return t("Чистая маржа {n}%.", { n: Math.round(margin) });
      if (m.real5y > 20) return t("Существенный рост прибыли; чистая маржа {n}%.", { n: Math.round(margin) });
      if (m.real5y > 0)  return t("Прибыль растёт; чистая маржа {n}%.", { n: Math.round(margin) });
      return t("Прибыль снижается в реальном выражении; маржа {n}%.", { n: Math.round(margin) });
    }
  );

  const debt = buildOne(
    t("Чистый долг"), "red", "debt", false,
    (m) => {
      const ratio = (extKpis.value && extKpis.value.ebitda > 0)
        ? (m.current * unitScale.value) / extKpis.value.ebitda : null;
      const ratioStr = ratio != null ? `Debt/EBITDA ${ratio.toFixed(1)}x` : "";
      if (m.real5y == null) return ratioStr || "—";
      if (m.real5y < 0)   return `${t("Долг сокращается в реальном выражении.")} ${ratioStr}`.trim();
      if (m.real5y < 10)  return `${t("Умеренный рост долга;")} ${ratioStr}`.trim();
      return `${t("Долг растёт быстрее инфляции;")} ${ratioStr}`.trim();
    },
    "debt"  // alt-fallback ltBorrowings+stBorrowings
  );

  return [revenue, profit, debt].filter(Boolean) as BriefMetric[];
}

const briefMetrics = computed<BriefMetric[] | null>(() => buildBriefMetrics());

// ─── Briefing chart helper: build SVG path + filled-area path ───
interface ChartGeom {
  line: string;
  area: string;
  pts: { x: number; y: number; year: number; value: number; isLast: boolean }[];
  width: number; height: number;
}
function makeChart(serie: { year: number; value: number | null }[], w = 520, h = 110): ChartGeom {
  const pts0 = serie.map((p, i) => ({ ...p, i }));
  const valid = pts0.filter(p => p.value != null) as { i: number; year: number; value: number }[];
  if (valid.length < 2) return { line: "", area: "", pts: [], width: w, height: h };
  const min = 0; // график от нуля
  const max = Math.max(...valid.map(p => p.value)) * 1.1 || 1;
  const padL = 30, padR = 30, padT = 16, padB = 28;
  const chartW = w - padL - padR;
  const chartH = h - padT - padB;
  const stepX = pts0.length > 1 ? chartW / (pts0.length - 1) : 0;
  const xy = pts0.map(p => {
    const x = padL + p.i * stepX;
    const y = p.value != null
      ? padT + chartH - ((p.value - min) / (max - min)) * chartH
      : padT + chartH;
    return { x, y, year: p.year, value: p.value, valid: p.value != null };
  });
  const validPts = xy.filter(p => p.valid);
  const line = "M " + validPts.map(p => `${p.x.toFixed(1)},${p.y.toFixed(1)}`).join(" L ");
  const area = line + ` L ${validPts[validPts.length - 1].x.toFixed(1)},${(padT + chartH).toFixed(1)} L ${validPts[0].x.toFixed(1)},${(padT + chartH).toFixed(1)} Z`;
  // Метки точек со значениями + годами под каждой
  const pts = xy.map((p, i) => ({
    x: p.x, y: p.y, year: p.year, value: p.value as number,
    isLast: i === pts0.length - 1,
  }));
  return { line, area, pts, width: w, height: h };
}

// ─── Единица/валюта dropdown (a11y: click-toggle + Escape + click-outside) ──
// Раньше меню открывалось ТОЛЬКО по :hover → недоступно с клавиатуры/тача.
const pdropOpen = ref(false);
const pdropRoot = ref<HTMLElement | null>(null);
function togglePdrop(): void { pdropOpen.value = !pdropOpen.value; }
function closePdrop(): void { pdropOpen.value = false; }
function onPdropClickOutside(e: MouseEvent): void {
  if (!pdropOpen.value) return;
  if (pdropRoot.value && !pdropRoot.value.contains(e.target as Node)) closePdrop();
}
function onPdropKeydown(e: KeyboardEvent): void {
  if (e.key === "Escape" && pdropOpen.value) {
    closePdrop();
    (pdropRoot.value?.querySelector(".ed-fin-pdrop-btn") as HTMLElement | null)?.focus?.();
  }
}

onMounted(() => {
  try {
    const raw = localStorage.getItem("uz_exec_dash_finance_v1");
    const wasReset = localStorage.getItem("uz_exec_dash_finance_v1_reset");
    if (raw && !wasReset) {
      fin.setViewMode("summary");
      localStorage.setItem("uz_exec_dash_finance_v1_reset", "1");
    }
  } catch { /* noop */ }
  fin.loadData();
  document.addEventListener("click", onPdropClickOutside);
  document.addEventListener("keydown", onPdropKeydown);
});
onBeforeUnmount(() => {
  document.removeEventListener("click", onPdropClickOutside);
  document.removeEventListener("keydown", onPdropKeydown);
});
</script>

<template>
  <section class="ed-fin">
    <!-- Header -->
    <header class="ed-fin-hdr">
      <div class="ed-fin-hdr-l">
        <div class="ed-fin-eyebrow">{{ t("Финансы") }} · {{ standardLabel }}</div>
        <div class="ed-fin-sub">
          <span>FY {{ fin.year.value }}</span>
          <span class="ed-fin-sep">·</span>
          <span>{{ standardLabel }}</span>
          <span class="ed-fin-sep">·</span>
          <span class="ed-fin-cov-pill">
            <span class="ed-fin-cov-dot"></span>
            <span v-count-up="cosWithRevenue">0</span> {{ t("из") }} <span v-count-up="totalCos">0</span>
          </span>
          <span v-if="cosMissing > 0" class="ed-fin-warn">
            <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"><path d="M10.29 3.86 1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/></svg>
            {{ t("{n} без данных", { n: cosMissing }) }}
          </span>
          <span class="ed-fin-sep">·</span>
          <span>{{ unitLabel }} {{ currencyLabel }}</span>
          <span class="ed-fin-sep">·</span>
          <span class="ed-fin-amber">{{ t("финансы FY{y} (задачи FY{ty})", { y: fin.year.value, ty: tasksYear }) }}</span>
          <template v-if="isFallbackYear">
            <span class="ed-fin-sep">·</span>
            <span class="ed-fin-fallback" :title="t('За FY{year} нет данных — показан последний доступный год', { year: fin.year.value })">{{ t("данные за FY{year}", { year: effectiveFinYear }) }}</span>
          </template>
        </div>
      </div>

      <div class="ed-fin-hdr-r">
        <UzaSegment :options="FIN_VIEW_OPTS" :model-value="fin.viewMode.value"
                    @update:model-value="(v) => (v === 'summary' ? setAnalytics() : setBriefing())" />

        <UzaSelect prefix="FY " :options="finYearOpts" :model-value="fin.year.value"
                   @update:model-value="(v) => fin.setYear(v as number)" />

        <UzaSegment :options="FIN_STD_OPTS" :model-value="fin.standard.value"
                    @update:model-value="(v) => fin.setStandard(v as any)" />

        <div class="ed-fin-pdrop" ref="pdropRoot">
          <button class="ed-fin-pdrop-btn" type="button" aria-haspopup="menu" :aria-expanded="pdropOpen" @click.stop="togglePdrop">
            {{ unitLabel }} {{ currencyLabel }}
            <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4"><polyline points="6 9 12 15 18 9"/></svg>
          </button>
          <div v-show="pdropOpen" class="ed-fin-pdrop-menu" role="menu">
            <div class="ed-fin-pdrop-grp">{{ t("Единица") }}</div>
            <button :class="{ on: fin.unit.value === 'bln' }" @click="fin.setUnit('bln')">{{ t("млрд") }}</button>
            <button :class="{ on: fin.unit.value === 'mln' }" @click="fin.setUnit('mln')">{{ t("млн") }}</button>
            <button :class="{ on: fin.unit.value === 'ths' }" @click="fin.setUnit('ths')">{{ t("тыс.") }}</button>
            <div class="ed-fin-pdrop-grp">{{ t("Валюта") }}</div>
            <button :class="{ on: fin.currency.value === 'UZS' }" @click="fin.setCurrency('UZS')">UZS</button>
            <button :class="{ on: fin.currency.value === 'USD' }" @click="fin.setCurrency('USD')">USD</button>
            <button :class="{ on: fin.currency.value === 'EUR' }" @click="fin.setCurrency('EUR')">EUR</button>
          </div>
        </div>
      </div>
    </header>

    <UzaStateBlock v-if="fin.loading.data && !fin.summary.value" state="loading" variant="spinner" :text="t('Загрузка финансовых данных…')" min-height="300px" />
    <UzaStateBlock v-else-if="fin.error.value" state="error" variant="block" :text="fin.error.value" retry @retry="fin.loadData()" />

    <template v-else-if="fin.viewMode.value === 'summary' && extKpis">
      <!-- 6 KPI cards -->
      <div class="ed-fin-kpi kpi-rail">
        <div
          class="ed-fin-kpi-card ed-fin-kpi-card--clickable"
          data-accent="violet"
          style="--d: 0ms;"
          role="button"
          tabindex="0"
          @click="openDrill('revenue')"
          @keydown="onKpiKeydown($event, 'revenue')"
          :title="t('Подробнее: Совокупная выручка')"
        >
          <div class="ed-fin-kpi-bar"></div>
          <div class="ed-fin-kpi-lbl">{{ t("Совокупная выручка") }}</div>
          <div class="ed-fin-kpi-val">{{ fmtNum(tRevenue) }}<span>{{ unitLabel }} {{ currencyLabel }}</span></div>
          <div class="ed-fin-kpi-d" :class="extKpis.revenueYoYPct >= 0 ? 'p' : 'n'">{{ fmtPctSigned(tRevenueYoY, 0) }} {{ t("к пред. году") }}</div>
        </div>
        <div
          class="ed-fin-kpi-card ed-fin-kpi-card--clickable"
          data-accent="teal"
          style="--d: 80ms;"
          role="button"
          tabindex="0"
          @click="openDrill('net_profit')"
          @keydown="onKpiKeydown($event, 'net_profit')"
          :title="t('Подробнее: Чистая прибыль')"
        >
          <div class="ed-fin-kpi-bar"></div>
          <div class="ed-fin-kpi-lbl">{{ t("Чистая прибыль") }}</div>
          <div class="ed-fin-kpi-val">{{ fmtNum(tNetProfit) }}<span>{{ unitLabel }} {{ currencyLabel }}</span></div>
          <div class="ed-fin-kpi-d">{{ t("Маржа") }} <strong>{{ fmtPct(tNetMargin, 0) }}</strong></div>
        </div>
        <div
          class="ed-fin-kpi-card ed-fin-kpi-card--clickable"
          data-accent="amber"
          style="--d: 160ms;"
          role="button"
          tabindex="0"
          @click="openDrill('ebitda')"
          @keydown="onKpiKeydown($event, 'ebitda')"
          :title="t('Подробнее: EBITDA')"
        >
          <div class="ed-fin-kpi-bar"></div>
          <div class="ed-fin-kpi-lbl">EBITDA</div>
          <div class="ed-fin-kpi-val">{{ fmtNum(tEbitda) }}<span>{{ unitLabel }} {{ currencyLabel }}</span></div>
          <div class="ed-fin-kpi-d">{{ t("Маржа") }} <strong>{{ fmtPct(tEbitdaMargin, 0) }}</strong></div>
        </div>
        <div
          class="ed-fin-kpi-card ed-fin-kpi-card--clickable"
          data-accent="blue"
          style="--d: 240ms;"
          role="button"
          tabindex="0"
          @click="openDrill('assets')"
          @keydown="onKpiKeydown($event, 'assets')"
          :title="t('Подробнее: Совокупные активы')"
        >
          <div class="ed-fin-kpi-bar"></div>
          <div class="ed-fin-kpi-lbl">{{ t("Совокупные активы") }}</div>
          <div class="ed-fin-kpi-val">{{ fmtNum(tAssets) }}<span>{{ unitLabel }} {{ currencyLabel }}</span></div>
          <div class="ed-fin-kpi-d">{{ t("{n} компаний с данными", { n: Math.round(tCosWithData) }) }}</div>
        </div>
        <div
          class="ed-fin-kpi-card ed-fin-kpi-card--clickable"
          data-accent="red"
          style="--d: 320ms;"
          role="button"
          tabindex="0"
          @click="openDrill('net_debt')"
          @keydown="onKpiKeydown($event, 'net_debt')"
          :title="t('Подробнее: Чистый долг')"
        >
          <div class="ed-fin-kpi-bar"></div>
          <div class="ed-fin-kpi-lbl">{{ t("Чистый долг") }}</div>
          <div class="ed-fin-kpi-val">{{ fmtNum(tDebt) }}<span>{{ unitLabel }} {{ currencyLabel }}</span></div>
          <div class="ed-fin-kpi-d">
            <span v-if="extKpis.debtToEquity != null">D/E <strong>{{ tDebtToEquity.toFixed(1) }}x</strong></span>
            <span v-else>D/E —</span>
          </div>
        </div>
        <div
          class="ed-fin-kpi-card ed-fin-kpi-card--clickable"
          data-accent="green"
          style="--d: 400ms;"
          role="button"
          tabindex="0"
          @click="openDrill('fcf')"
          @keydown="onKpiKeydown($event, 'fcf')"
          :title="t('Подробнее: Free Cash Flow')"
        >
          <div class="ed-fin-kpi-bar"></div>
          <div class="ed-fin-kpi-lbl">Free Cash Flow</div>
          <div class="ed-fin-kpi-val" :class="extKpis.freeCashFlow >= 0 ? 'p' : 'n'">{{ fmtNum(tFcf) }}<span>{{ unitLabel }} {{ currencyLabel }}</span></div>
          <div class="ed-fin-kpi-d">CFO + CFI<span v-if="extKpis.roe != null"> · ROE <strong>{{ fmtPct(tRoe, 0) }}</strong></span></div>
        </div>
        <!-- Дебиторская / Кредиторская — только НСБУ (под МСФО это tradeReceivables, остатков нет) -->
        <div v-if="fin.standard.value === 'NSBU'" class="ed-fin-kpi-card" data-accent="violet" style="--d: 480ms;">
          <div class="ed-fin-kpi-bar"></div>
          <div class="ed-fin-kpi-lbl">{{ t("Дебиторская задолженность") }}</div>
          <div class="ed-fin-kpi-val">{{ fmtNum(tAccountsReceivable) }}<span>{{ unitLabel }} {{ currencyLabel }}</span></div>
          <div class="ed-fin-kpi-d">{{ t("Средства к получению") }}</div>
        </div>
        <div v-if="fin.standard.value === 'NSBU'" class="ed-fin-kpi-card" data-accent="amber" style="--d: 560ms;">
          <div class="ed-fin-kpi-bar"></div>
          <div class="ed-fin-kpi-lbl">{{ t("Кредиторская задолженность") }}</div>
          <div class="ed-fin-kpi-val">{{ fmtNum(tAccountsPayable) }}<span>{{ unitLabel }} {{ currencyLabel }}</span></div>
          <div class="ed-fin-kpi-d">{{ t("Обязательства к оплате") }}</div>
        </div>
      </div>

      <!-- Sector filter -->
      <div class="ed-fin-secflt">
        <span class="ed-fin-secflt-lbl">{{ t("Сектор") }}:</span>
        <button class="ed-fin-secflt-pill" :class="{ on: finSectorFilter === 'all' }" @click="setSector('all')">{{ t("Все") }}</button>
        <button v-for="s in availableSectors" :key="s" class="ed-fin-secflt-pill" :class="{ on: finSectorFilter === s }" @click="setSector(s)">
          <span class="ed-fin-secflt-dot" :style="{ background: sectorMeta[s].color }"></span>
          {{ sectorMeta[s].label }}
        </button>
      </div>

      <!-- Детальная отчётность компании (при фокусе на 1 компании в пикере) -->
      <div v-if="focusedCompanyCode" class="ed-fin-stmt">
        <button class="ed-fin-stmt-hd" :aria-expanded="showStatement" @click="showStatement = !showStatement">
          <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round" :style="{ transform: showStatement ? 'rotate(180deg)' : 'none', transition: 'transform .2s' }"><polyline points="6 9 12 15 18 9"/></svg>
          <span class="ed-fin-stmt-t">{{ t("Отчётность: {name}", { name: focusedCompanyName }) }}</span>
          <span class="ed-fin-stmt-hint">{{ t("KEY METRICS + полный отчёт") }}</span>
        </button>
        <div v-if="showStatement" class="ed-fin-stmt-body">
          <HighLevelFinancials :key="focusedCompanyCode" :companies="hlfCompanies" :initial-code="focusedCompanyCode || undefined" />
        </div>
      </div>

      <!-- Accordion -->
      <button class="ed-fin-acc" @click="listExpanded = !listExpanded">
        {{ listExpanded ? t('Свернуть список') : t('Показать компаний с разбивкой') }}
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round" :style="{ transform: listExpanded ? 'rotate(180deg)' : 'none', transition: 'transform 0.2s' }">
          <polyline points="6 9 12 15 18 9"/>
        </svg>
      </button>

      <!-- Table -->
      <div v-if="listExpanded" class="ed-fin-tbl">
        <div class="ed-fin-tbl-hdr">
          <div class="c-idx">#</div>
          <div class="c-name sortable" role="button" tabindex="0" :aria-sort="ariaSort('name')" @click="setSort('name')" @keydown="onSortKeydown($event, 'name')">
            {{ t("Компания") }} <span v-if="sortBy === 'name'" class="sort-arr">{{ sortDir === 'asc' ? '↑' : '↓' }}</span>
          </div>
          <div class="c-sec sortable" role="button" tabindex="0" :aria-sort="ariaSort('sector')" @click="setSort('sector')" @keydown="onSortKeydown($event, 'sector')">
            {{ t("Сектор") }} <span v-if="sortBy === 'sector'" class="sort-arr">{{ sortDir === 'asc' ? '↑' : '↓' }}</span>
          </div>
          <div class="c-num sortable" role="button" tabindex="0" :aria-sort="ariaSort('revenue')" @click="setSort('revenue')" @keydown="onSortKeydown($event, 'revenue')">{{ t("Выручка") }} <span v-if="sortBy === 'revenue'" class="sort-arr">{{ sortDir === 'asc' ? '↑' : '↓' }}</span></div>
          <div class="c-num sortable" role="button" tabindex="0" :aria-sort="ariaSort('profit')" @click="setSort('profit')" @keydown="onSortKeydown($event, 'profit')">{{ t("Прибыль") }} <span v-if="sortBy === 'profit'" class="sort-arr">{{ sortDir === 'asc' ? '↑' : '↓' }}</span></div>
          <div class="c-num sortable" role="button" tabindex="0" :aria-sort="ariaSort('assets')" @click="setSort('assets')" @keydown="onSortKeydown($event, 'assets')">{{ t("Активы") }} <span v-if="sortBy === 'assets'" class="sort-arr">{{ sortDir === 'asc' ? '↑' : '↓' }}</span></div>
          <div class="c-num sortable" role="button" tabindex="0" :aria-sort="ariaSort('debt')" @click="setSort('debt')" @keydown="onSortKeydown($event, 'debt')">{{ t("Долг") }} <span v-if="sortBy === 'debt'" class="sort-arr">{{ sortDir === 'asc' ? '↑' : '↓' }}</span></div>
          <div class="c-num sortable" role="button" tabindex="0" :aria-sort="ariaSort('cfo')" @click="setSort('cfo')" @keydown="onSortKeydown($event, 'cfo')">CFO <span v-if="sortBy === 'cfo'" class="sort-arr">{{ sortDir === 'asc' ? '↑' : '↓' }}</span></div>
          <div class="c-num sortable" role="button" tabindex="0" :aria-sort="ariaSort('ebitdaPct')" @click="setSort('ebitdaPct')" @keydown="onSortKeydown($event, 'ebitdaPct')">EBITDA % <span v-if="sortBy === 'ebitdaPct'" class="sort-arr">{{ sortDir === 'asc' ? '↑' : '↓' }}</span></div>
          <div class="c-num sortable" role="button" tabindex="0" :aria-sort="ariaSort('yoy')" @click="setSort('yoy')" @keydown="onSortKeydown($event, 'yoy')">YOY <span v-if="sortBy === 'yoy'" class="sort-arr">{{ sortDir === 'asc' ? '↑' : '↓' }}</span></div>
          <div class="c-trend">{{ t("Тренд 5Л") }}</div>
        </div>

        <template v-for="r in tableRows" :key="r.id">
          <div
            class="ed-fin-tbl-row"
            :class="{ 'ed-fin-tbl-row-exp': expandedRows.has(r.id) }"
            role="button"
            tabindex="0"
            :aria-expanded="expandedRows.has(r.id)"
            @click="toggleRow(r.id)"
            @keydown="onRowKeydown($event, r.id)"
          >
            <div class="c-idx">{{ r.idx }}</div>
            <div class="c-name">
              <span class="ed-fin-row-bar" :style="{ background: sectorMeta[r.sector]?.color || '#888' }"></span>
              <svg class="ed-fin-chev" :class="{ open: expandedRows.has(r.id) }" width="9" height="9" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.6" stroke-linecap="round" stroke-linejoin="round">
                <polyline points="9 6 15 12 9 18"/>
              </svg>
              {{ r.name }}
            </div>
            <div class="c-sec">{{ sectorMeta[r.sector]?.short || '—' }}</div>
            <div class="c-num">{{ fmtNum(r.revenue) }}</div>
            <div class="c-num" :class="r.profit != null && r.profit < 0 ? 'c-neg' : ''">{{ fmtNum(r.profit) }}</div>
            <div class="c-num">{{ fmtNum(r.assets) }}</div>
            <div class="c-num">{{ fmtNum(r.debt) }}</div>
            <div class="c-num" :class="r.cfo != null && r.cfo < 0 ? 'c-neg' : ''">{{ fmtNum(r.cfo) }}</div>
            <div class="c-num c-pct">{{ r.ebitdaPct != null ? fmtPct(r.ebitdaPct, 0) : '—' }}</div>
            <div class="c-num c-yoy" :class="r.yoy == null ? '' : (r.yoy >= 0 ? 'p' : 'n')">{{ r.yoy != null ? fmtPctSigned(r.yoy, 0) : '—' }}</div>
            <div class="c-trend">
              <svg v-if="trendPoints(r.trend5y).d" width="64" height="18" viewBox="0 0 64 18">
                <path :d="trendPoints(r.trend5y).d" fill="none" :stroke="trendPoints(r.trend5y).up ? '#5DC093' : '#E2807F'" stroke-width="1.4" stroke-linecap="round" stroke-linejoin="round"/>
              </svg>
              <span v-else class="c-trend-empty">—</span>
            </div>
          </div>

          <!-- Expand: 5-year breakdown grid + larger sparkline -->
          <div v-if="expandedRows.has(r.id)" class="ed-fin-tbl-exp">
            <div class="ed-fin-tbl-exp-grid">
              <div class="ed-fin-exp-cell ed-fin-exp-lbl"></div>
              <div v-for="b in r.breakdown" :key="b.year" class="ed-fin-exp-cell ed-fin-exp-yr">
                {{ b.year }}
              </div>
            </div>
            <div class="ed-fin-tbl-exp-grid">
              <div class="ed-fin-exp-cell ed-fin-exp-lbl">{{ t("Выручка") }}</div>
              <div v-for="b in r.breakdown" :key="'rv-' + b.year" class="ed-fin-exp-cell ed-fin-exp-num">
                {{ fmtNum(b.revenue) }}
              </div>
            </div>
            <div class="ed-fin-tbl-exp-grid">
              <div class="ed-fin-exp-cell ed-fin-exp-lbl">{{ t("Прибыль") }}</div>
              <div
                v-for="b in r.breakdown" :key="'pr-' + b.year"
                class="ed-fin-exp-cell ed-fin-exp-num"
                :class="b.profit != null && b.profit < 0 ? 'c-neg' : ''"
              >
                {{ fmtNum(b.profit) }}
              </div>
            </div>
          </div>
        </template>

        <UzaStateBlock v-if="tableRows.length === 0" state="empty" variant="inline" :text="t('Нет компаний с данными в выборке')" />
      </div>
    </template>

    <!-- ═══════════ Брифинг mode ═══════════ -->
    <template v-else-if="fin.viewMode.value === 'company' && briefMetrics && briefMetrics.length">
      <div class="ed-brief">
        <div v-for="m in briefMetrics" :key="m.label" class="ed-brief-card" :data-accent="m.accent">
          <div class="ed-brief-bar"></div>
          <div class="ed-brief-lbl">{{ m.label }}</div>
          <div class="ed-brief-val">
            <span class="ed-brief-num"><Odometer :value="fmtNum(m.current * unitScale)" /></span>
            <span class="ed-brief-u">{{ unitLabel }} {{ currencyLabel }}</span>
          </div>
          <div class="ed-brief-deltas">
            <span class="ed-brief-yoy" :class="deltaClass(m.yoy, m.positiveDelta)">
              <template v-if="m.yoy != null">{{ m.yoy >= 0 ? '+' : '' }}{{ Math.round(m.yoy) }}%</template>
              <template v-else>—</template>
            </span>
            <span class="ed-brief-deltalbl">{{ t("к {year}", { year: fin.year.value - 1 }) }}</span>
            <span class="ed-brief-sep">—</span>
            <span class="ed-brief-deltalbl">{{ t("за 5 лет") }}</span>
          </div>
          <div class="ed-brief-real">
            <template v-if="m.nominal5y != null && m.real5y != null">
              {{ t("номинально") }} <strong :class="deltaClass(m.nominal5y, m.positiveDelta)">{{ m.nominal5y >= 0 ? '+' : '' }}{{ Math.round(m.nominal5y) }}%</strong>
              <span class="ed-brief-mid">·</span>
              {{ t("реально") }} <strong :class="deltaClass(m.real5y, m.positiveDelta)">{{ m.real5y >= 0 ? '+' : '' }}{{ Math.round(m.real5y) }}%</strong>
            </template>
            <template v-else>—</template>
          </div>

          <!-- Chart -->
          <svg :viewBox="`0 0 ${makeChart(m.serie).width} ${makeChart(m.serie).height}`" class="ed-brief-chart" preserveAspectRatio="none">
            <defs>
              <linearGradient :id="`grad-${m.accent}`" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" :stop-color="m.accent === 'violet' ? '#7F77DD' : m.accent === 'teal' ? '#5DC093' : '#E2807F'" stop-opacity="0.18"/>
                <stop offset="100%" :stop-color="m.accent === 'violet' ? '#7F77DD' : m.accent === 'teal' ? '#5DC093' : '#E2807F'" stop-opacity="0"/>
              </linearGradient>
            </defs>
            <path :d="makeChart(m.serie).area" :fill="`url(#grad-${m.accent})`"/>
            <path :d="makeChart(m.serie).line" fill="none" :stroke="m.accent === 'violet' ? '#7F77DD' : m.accent === 'teal' ? '#5DC093' : '#E2807F'" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
            <g v-for="(p, i) in makeChart(m.serie).pts" :key="i">
              <circle :cx="p.x" :cy="p.y" r="3.5" fill="#fff" :stroke="m.accent === 'violet' ? '#7F77DD' : m.accent === 'teal' ? '#5DC093' : '#E2807F'" stroke-width="1.5"/>
              <text :x="p.x" :y="p.y - 8" text-anchor="middle" font-size="10" font-weight="600" fill="#1E2A4A" font-family="system-ui">
                {{ p.value != null ? (Math.abs(p.value) >= 100 ? fmt.fmtNumber(Math.round(p.value)) : fmt.fmtNumber(p.value, { decimals: p.value < 10 ? 2 : 1, minDecimals: p.value < 10 ? 2 : 1 })) : '—' }}
              </text>
              <text :x="p.x" :y="makeChart(m.serie).height - 8" text-anchor="middle" font-size="9.5" fill="#888780" font-family="system-ui">
                {{ p.year }}
              </text>
            </g>
          </svg>

          <div class="ed-brief-comment">{{ m.comment }}</div>
        </div>
      </div>
      <div class="ed-brief-footer">
        {{ t("Реальная динамика рассчитана с учётом ИПЦ Центрального Банка Республики Узбекистан") }}
      </div>
    </template>

    <div v-else-if="fin.viewMode.value === 'company'" class="ed-fin-state">
      {{ t("Недостаточно данных для брифинга") }}
    </div>

    <div v-else class="ed-fin-state">{{ t("Нет данных") }}</div>

    <!-- Pack 7.32: KPI drill-down modal -->
    <FinanceDrillModal
      v-if="drillKind && extKpis"
      :kind="drillKind"
      :ext-kpis="extKpis"
      :rows="tableRows"
      :sector-meta="sectorMeta"
      :year="fin.year.value"
      :unit-factor="unitScale"
      :unit-label="unitLabel"
      :currency-label="currencyLabel"
      :total-companies="totalCos"
      @close="closeDrill"
    />
  </section>
</template>

<style scoped>
.ed-fin {
  background: var(--bg1, #fff); border-radius: 12px;
  border: 0.5px solid rgba(15, 23, 60, 0.08);
  padding: 16px 18px 18px; margin-top: 14px;
  box-shadow: 0 4px 16px rgba(15, 23, 60, 0.04);
}
.ed-fin-hdr { display: flex; justify-content: space-between; align-items: flex-start; gap: 16px; margin-bottom: 14px; flex-wrap: wrap; }
.ed-fin-hdr-l { min-width: 0; flex: 1; }
.ed-fin-hdr-r { display: flex; gap: 6px; align-items: center; flex-wrap: wrap; }
.ed-fin-eyebrow { font-size: 11px; font-weight: 600; letter-spacing: 0.07em; color: var(--t3, var(--t-muted)); text-transform: uppercase; }
.ed-fin-sub { display: flex; flex-wrap: wrap; align-items: center; gap: 5px; margin-top: 4px; font-size: 11px; color: var(--t3, var(--t-muted)); font-weight: 500; font-feature-settings: "tnum"; }
.ed-fin-sep { color: rgba(15, 23, 60, 0.18); }
.ed-fin-cov-pill { display: inline-flex; align-items: center; gap: 5px; background: rgba(239, 159, 39, 0.10); color: #B97612; padding: 1px 7px; border-radius: 9px; font-weight: 600; font-size: 10.5px; }
.ed-fin-cov-dot { width: 5px; height: 5px; border-radius: 50%; background: var(--amber); }
.ed-fin-warn { display: inline-flex; align-items: center; gap: 4px; color: var(--t3, var(--t-muted)); }
.ed-fin-warn svg { color: var(--amber); }
.ed-fin-amber { color: #B97612; font-weight: 600; }
.ed-fin-fallback { color: #5B54B8; font-weight: 600; background: rgba(127,119,221,.1); padding: 1px 7px; border-radius: 6px; }

.ed-fin-seg, .ed-fin-pills2 { display: inline-flex; background: rgba(15, 23, 60, 0.05); border-radius: 7px; padding: 2px; }
.ed-fin-seg button, .ed-fin-pills2 button { background: transparent; border: none; font-size: 11px; font-weight: 600; color: var(--t3, var(--t-muted)); padding: 5px 12px; border-radius: 5px; cursor: pointer; font-family: inherit; }
.ed-fin-pills2 button { padding: 5px 11px; }
.ed-fin-seg button.on, .ed-fin-pills2 button.on { background: var(--bg1, #fff); color: var(--t1, #1E2A4A); box-shadow: 0 1px 3px rgba(0,0,0,0.08); }

.ed-fin-pdrop { position: relative; }
.ed-fin-pdrop-btn { display: inline-flex; align-items: center; gap: 6px; background: rgba(15, 23, 60, 0.05); border: none; border-radius: 7px; font-size: 11px; font-weight: 600; color: var(--t1, #1E2A4A); padding: 6px 10px; cursor: pointer; font-family: inherit; font-feature-settings: "tnum"; }
.ed-fin-pdrop-btn svg { color: var(--t3, var(--t-muted)); }
/* v-show управляет показом (display:flex по умолчанию, inline display:none когда закрыт). */
.ed-fin-pdrop-menu { display: flex; position: absolute; top: calc(100% + 2px); right: 0; background: var(--bg1, #fff); border: 0.5px solid rgba(15, 23, 60, 0.10); border-radius: 8px; box-shadow: 0 8px 24px rgba(15, 23, 60, 0.15); padding: 4px; flex-direction: column; min-width: 110px; z-index: 10; }
.ed-fin-pdrop-menu button { background: transparent; border: none; text-align: left; font-size: 11px; font-weight: 600; color: var(--t1, #1E2A4A); padding: 6px 12px; border-radius: 5px; cursor: pointer; font-family: inherit; }
.ed-fin-pdrop-menu button:hover { background: rgba(127, 119, 221, 0.08); }
.ed-fin-pdrop-menu button.on { background: rgba(127, 119, 221, 0.14); color: #5B54B8; }
.ed-fin-pdrop-grp { font-size: 9px; font-weight: 600; color: var(--t3, var(--t-muted)); letter-spacing: 0.06em; text-transform: uppercase; padding: 4px 12px 2px; }

.ed-fin-state { padding: 40px 20px; text-align: center; color: var(--t3, var(--t-muted)); font-size: 12px; }
.ed-fin-state-err { color: #C36868; }

/* KPI */
/* auto-fit: переменное число карточек (6 МСФО / 8 НСБУ) укладывается в один
   ряд на широком экране и аккуратно переносится на узком. */
.ed-fin-kpi { display: grid; grid-template-columns: repeat(auto-fit, minmax(158px, 1fr)); gap: 10px; margin-bottom: 16px; }
@media (max-width: 600px)  { .ed-fin-kpi { grid-template-columns: 1fr 1fr; } }
/* Pack 7.23: KPI card in fkb-card style — draw-in + breathing + shimmer.
   Replaces flat 2px stripe with animated top-stripe via ::before/::after
   pseudo-elements. The empty <div class="ed-fin-kpi-bar"></div> in the
   template is now unused but kept for backward compatibility (display:none). */
.ed-fin-kpi-card {
  background: #FAFAFB;
  border: 0.5px solid rgba(15, 23, 60, 0.06);
  border-radius: 10px;
  padding: 13px 13px 11px;
  position: relative;
  overflow: hidden;
  animation: finKpiCardIn .55s var(--ease-standard) var(--d, 0ms) both;
}
.ed-fin-kpi-card::before {
  content: '';
  position: absolute;
  top: 0; left: 0; right: 0; height: 3px;
  background: var(--bar);
  border-radius: 10px 10px 0 0;
  animation:
    finKpi2DrawIn .8s var(--ease-standard) var(--d, 0ms) both,
    finKpi2Breathe 2.8s ease-in-out calc(var(--d, 0ms) + 1s) infinite;
  transform-origin: left center;
}
.ed-fin-kpi-card::after {
  content: '';
  position: absolute;
  top: 0; left: 0; right: 0; height: 3px;
  background: linear-gradient(90deg, transparent, rgba(255, 255, 255, .65), transparent);
  animation: finShimmer 6s ease-in-out calc(var(--d, 0ms) + 1.2s) 1;
  transform: translateX(-120%);
  pointer-events: none;
}
.ed-fin-kpi-bar { display: none; }  /* legacy element, replaced by ::before */
.ed-fin-kpi-card[data-accent="violet"] { --bar: #7F77DD; }
.ed-fin-kpi-card[data-accent="teal"]   { --bar: var(--green); }
.ed-fin-kpi-card[data-accent="amber"]  { --bar: var(--amber); }
.ed-fin-kpi-card[data-accent="blue"]   { --bar: var(--blue); }
.ed-fin-kpi-card[data-accent="red"]    { --bar: var(--sev-high); }
.ed-fin-kpi-card[data-accent="green"]  { --bar: var(--green); }

/* Pack 7.32: clickable variant — лёгкий hover-lift, focus-кольцо */
.ed-fin-kpi-card--clickable {
  cursor: pointer;
  transition: transform 0.16s ease, box-shadow 0.16s ease, border-color 0.16s ease;
  outline: none;
}
.ed-fin-kpi-card--clickable:hover {
  transform: translateY(-2px);
  box-shadow: 0 8px 22px rgba(15, 23, 60, 0.08);
  border-color: rgba(127, 119, 221, 0.18);
}
.ed-fin-kpi-card--clickable:focus-visible {
  box-shadow: 0 0 0 2px rgba(127, 119, 221, 0.45);
  border-color: rgba(127, 119, 221, 0.35);
}
.ed-fin-kpi-card--clickable:active {
  transform: translateY(-1px);
  box-shadow: 0 4px 14px rgba(15, 23, 60, 0.06);
}
.ed-fin-kpi-lbl { font-size: 9.5px; font-weight: 600; color: var(--t3, var(--t-muted)); letter-spacing: 0.06em; text-transform: uppercase; margin-bottom: 8px; }
.ed-fin-kpi-val { font-size: 28px; font-weight: 400; color: var(--t1, #1E2A4A); letter-spacing: -0.025em; font-feature-settings: "tnum"; line-height: 1; }
.ed-fin-kpi-val span { font-size: 11px; color: var(--t3, var(--t-muted)); font-weight: 500; letter-spacing: 0; margin-left: 5px; }
.ed-fin-kpi-val.n { color: var(--sev-high); }
.ed-fin-kpi-d { font-size: 11px; color: var(--t3, var(--t-muted)); font-weight: 500; margin-top: 6px; font-feature-settings: "tnum"; }
.ed-fin-kpi-d strong { color: var(--green); font-weight: 600; }
.ed-fin-kpi-d.p { color: var(--green); }
.ed-fin-kpi-d.n { color: var(--sev-high); }

/* Sector filter */
.ed-fin-secflt { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; padding: 8px 0 12px; }
.ed-fin-secflt-lbl { font-size: 9.5px; font-weight: 600; color: var(--t3, var(--t-muted)); letter-spacing: 0.08em; text-transform: uppercase; }
/* Pack 7.17: sector column in the company table */
.ed-fin-tbl-hdr .c-sec,
.ed-fin-tbl-row .c-sec { width: 90px; padding: 0 8px; font-size: 11px; color: var(--t3, #5F5E5A); font-weight: 500; }
.ed-fin-tbl-hdr .c-sec { font-weight: 600; }
.ed-fin-tbl-row .c-sec { font-size: 11px; }

.ed-fin-secflt-pill { display: inline-flex; align-items: center; gap: 6px; background: rgba(15, 23, 60, 0.05); border: none; border-radius: 11px; font-size: 11px; font-weight: 600; color: var(--t3, var(--t-muted)); padding: 4px 10px; cursor: pointer; font-family: inherit; transition: background 0.12s, color 0.12s; }
.ed-fin-secflt-pill:hover { background: rgba(127, 119, 221, 0.08); color: var(--t1, #1E2A4A); }
.ed-fin-secflt-pill.on { background: rgba(127, 119, 221, 0.14); color: #5B54B8; }
.ed-fin-secflt-dot { width: 6px; height: 6px; border-radius: 50%; flex-shrink: 0; }

/* Accordion */
.ed-fin-acc { width: 100%; display: flex; align-items: center; justify-content: center; gap: 8px; background: rgba(127, 119, 221, 0.06); border: 0.5px solid rgba(127, 119, 221, 0.15); border-radius: 8px; padding: 9px; font-size: 12px; font-weight: 600; color: #5B54B8; cursor: pointer; font-family: inherit; margin-bottom: 12px; }
.ed-fin-acc:hover { background: rgba(127, 119, 221, 0.10); }

/* Детальная отчётность компании (раскрытие под фин-блоком) */
.ed-fin-stmt { margin: 0 0 12px; border: 1px solid rgba(127,119,221,.18); border-radius: 12px; overflow: hidden; background: var(--bg1,#fff); }
.ed-fin-stmt-hd {
  width: 100%; display: flex; align-items: center; gap: 9px;
  padding: 11px 14px; background: linear-gradient(135deg, rgba(127,119,221,.08), rgba(127,119,221,.03));
  border: none; cursor: pointer; font-family: inherit; text-align: left;
  border-bottom: 1px solid rgba(127,119,221,.12);
}
.ed-fin-stmt-hd:hover { background: linear-gradient(135deg, rgba(127,119,221,.13), rgba(127,119,221,.05)); }
.ed-fin-stmt-hd svg { color: #5B54B8; flex-shrink: 0; }
.ed-fin-stmt-t { font-size: 13px; font-weight: 600; color: var(--t1, #1E2A4A); }
.ed-fin-stmt-hint { font-size: 10.5px; color: var(--t3, #94A3B8); margin-left: auto; font-weight: 500; }
.ed-fin-stmt-body { padding: 4px 6px 6px; animation: edFinStmtIn .3s var(--ease-standard) both; }
@keyframes edFinStmtIn { from { opacity: 0; transform: translateY(-6px); } to { opacity: 1; transform: none; } }

/* Table */
.ed-fin-tbl { font-feature-settings: "tnum"; }
.ed-fin-tbl-hdr {
  display: grid;
  grid-template-columns: 32px minmax(180px, 2fr) repeat(7, minmax(70px, 1fr)) 80px;
  gap: 8px;
  padding: 8px 12px;
  font-size: 9.5px;
  font-weight: 700;
  color: var(--t3, var(--t-muted));
  letter-spacing: 0.06em;
  text-transform: uppercase;
  border-bottom: 0.5px solid rgba(15, 23, 60, 0.10);
  background: #FAFAFB;
  border-radius: 6px 6px 0 0;
}
.ed-fin-tbl-hdr .c-num, .ed-fin-tbl-hdr .c-trend { text-align: right; }
.ed-fin-tbl-hdr .sortable { cursor: pointer; user-select: none; }
.ed-fin-tbl-hdr .sortable:hover { color: var(--t1, #1E2A4A); }
.ed-fin-tbl-hdr .sort-arr { color: #5B54B8; margin-left: 2px; font-size: 10px; }

.ed-fin-tbl-row {
  display: grid;
  grid-template-columns: 32px minmax(180px, 2fr) repeat(7, minmax(70px, 1fr)) 80px;
  gap: 8px;
  padding: 9px 12px;
  font-size: 12px;
  color: var(--t1, #1E2A4A);
  border-bottom: 0.5px solid rgba(15, 23, 60, 0.04);
  align-items: center;
}
.ed-fin-tbl-row:hover { background: rgba(127, 119, 221, 0.03); }

/* Мобильный: широкая финансовая таблица (10 колонок) скроллится горизонтально,
   колонки остаются читаемыми. */
@media (max-width: 640px) {
  .ed-fin-tbl { overflow-x: auto; -webkit-overflow-scrolling: touch; }
  .ed-fin-tbl-hdr, .ed-fin-tbl-row { min-width: 760px; }
}

.ed-fin-tbl-row .c-idx { color: var(--t3, var(--t-muted)); font-size: 11px; font-weight: 500; }
.ed-fin-tbl-row .c-name { font-weight: 500; display: flex; align-items: center; gap: 8px; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.ed-fin-row-bar { width: 3px; height: 14px; border-radius: 2px; flex-shrink: 0; }
.ed-fin-tbl-row .c-num { text-align: right; }
.ed-fin-tbl-row .c-pct { color: var(--green); font-weight: 500; }
.ed-fin-tbl-row .c-yoy.p { color: var(--green); font-weight: 500; }
.ed-fin-tbl-row .c-yoy.n { color: var(--sev-high); font-weight: 500; }
.ed-fin-tbl-row .c-neg { color: var(--sev-high); }
.ed-fin-tbl-row .c-trend { text-align: right; display: flex; justify-content: flex-end; align-items: center; }
.c-trend-empty { color: #6B6A66; font-size: 11px; }

/* ═══════════ Брифинг ═══════════ */
.ed-brief {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 14px;
  margin-top: 4px;
}
@media (max-width: 1300px) { .ed-brief { grid-template-columns: 1fr; } }

.ed-brief-card {
  background: #FAFAFB;
  border: 0.5px solid rgba(15, 23, 60, 0.06);
  border-radius: 10px;
  padding: 14px 18px 14px;
  position: relative;
  overflow: hidden;
}
.ed-brief-bar {
  position: absolute; top: 0; left: 0; right: 0; height: 2px;
  background: var(--bar);
}
.ed-brief-card[data-accent="violet"] { --bar: #7F77DD; }
.ed-brief-card[data-accent="teal"]   { --bar: var(--green); }
.ed-brief-card[data-accent="red"]    { --bar: var(--sev-high); }

.ed-brief-lbl {
  font-size: 9.5px;
  font-weight: 600;
  color: var(--t3, var(--t-muted));
  letter-spacing: 0.06em;
  text-transform: uppercase;
  margin-bottom: 8px;
}
.ed-brief-val {
  display: flex;
  align-items: baseline;
  gap: 6px;
  margin-bottom: 6px;
}
.ed-brief-num {
  font-size: 28px;
  font-weight: 400;
  color: var(--t1, #1E2A4A);
  letter-spacing: -0.025em;
  font-feature-settings: "tnum";
  line-height: 1;
}
.ed-brief-u {
  font-size: 11px;
  color: var(--t3, var(--t-muted));
  font-weight: 500;
}
.ed-brief-deltas {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 11px;
  color: var(--t3, var(--t-muted));
  font-weight: 500;
  margin-bottom: 4px;
  font-feature-settings: "tnum";
}
.ed-brief-yoy { font-weight: 700; font-size: 12px; }
.ed-brief-yoy.p { color: var(--green); }
.ed-brief-yoy.n { color: var(--sev-high); }
.ed-brief-deltalbl { color: var(--t3, var(--t-muted)); }
.ed-brief-sep { color: rgba(15, 23, 60, 0.18); }
.ed-brief-real {
  font-size: 11px;
  color: var(--t3, var(--t-muted));
  font-weight: 500;
  margin-bottom: 8px;
  font-feature-settings: "tnum";
}
.ed-brief-real strong { font-weight: 700; }
.ed-brief-real strong.p { color: var(--green); }
.ed-brief-real strong.n { color: var(--sev-high); }
.ed-brief-mid { color: rgba(15, 23, 60, 0.18); margin: 0 4px; }

.ed-brief-chart {
  display: block;
  width: 100%;
  height: 110px;
  margin: 8px 0 6px;
}

.ed-brief-comment {
  font-size: 11.5px;
  color: #5B6378;
  line-height: 1.4;
  font-style: italic;
  border-top: 0.5px dashed rgba(15, 23, 60, 0.08);
  padding-top: 8px;
  margin-top: 4px;
}

.ed-brief-footer {
  margin-top: 14px;
  text-align: right;
  font-size: 10.5px;
  color: #6B6A66;
  font-style: italic;
  font-weight: 500;
}

.ed-fin-tbl-empty { padding: 28px; text-align: center; color: var(--t3, var(--t-muted)); font-size: 11.5px; }

/* Chevron + clickable row */
.ed-fin-tbl-row { cursor: pointer; transition: background 0.12s; }
.ed-fin-chev { color: #6B6A66; flex-shrink: 0; transition: transform 0.18s var(--ease-standard); margin-right: -2px; }
.ed-fin-chev.open { transform: rotate(90deg); color: #5B54B8; }
.ed-fin-tbl-row-exp { background: rgba(127, 119, 221, 0.05); }
.ed-fin-tbl-row-exp:hover { background: rgba(127, 119, 221, 0.07); }

/* Expand panel — 5 columns: label + 5 years */
.ed-fin-tbl-exp {
  background: linear-gradient(180deg, rgba(127, 119, 221, 0.04) 0%, rgba(127, 119, 221, 0.01) 100%);
  border-bottom: 0.5px solid rgba(15, 23, 60, 0.06);
  padding: 8px 12px 12px;
}
.ed-fin-tbl-exp-grid {
  display: grid;
  grid-template-columns: 100px repeat(5, 1fr);
  gap: 12px;
  align-items: center;
}
.ed-fin-tbl-exp-grid + .ed-fin-tbl-exp-grid { margin-top: 4px; }
.ed-fin-exp-cell { padding: 4px 8px; font-feature-settings: "tnum"; }
.ed-fin-exp-lbl {
  font-size: 9.5px;
  font-weight: 600;
  color: var(--t3, var(--t-muted));
  letter-spacing: 0.06em;
  text-transform: uppercase;
  text-align: right;
}
.ed-fin-exp-yr {
  font-size: 10.5px;
  font-weight: 600;
  color: #6B6A66;
  letter-spacing: 0.04em;
  text-align: right;
}
.ed-fin-exp-num {
  font-size: 12px;
  font-weight: 500;
  color: var(--t1, #1E2A4A);
  text-align: right;
}
.ed-fin-exp-num.c-neg { color: var(--sev-high); }
</style>