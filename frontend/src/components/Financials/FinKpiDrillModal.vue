<script setup lang="ts">
/**
 * FinKpiDrillModal.vue — Pack 7.48
 * ─────────────────────────────────────────────────────────────────
 * Drill-down модалка для 6 KPI-карточек блока FinKpiBand.
 *
 * Объединённый компонент с двумя режимами:
 *   Mode A (financial): revenue | opMargin | ebitda | netMargin
 *     • Hero + chip-summary + 4 mini-KPI по секторам
 *     • Динамика 2021-2027 (bar chart, план как пунктир)
 *     • Список топ-компаний (отсортирован по value desc)
 *   Mode B (status):    loss
 *     • Hero + chip-summary + 4 mini-KPI по статусам
 *     • Status filter chips (Все / МСФО / Forensic / требуют внимания)
 *     • Список компаний со status-badges
 *
 * Все данные computed клиентски из переданных summary + companies + sectors.
 * Стиль 1:1 DirectionDrillModal (ddm-*).
 */
import { computed, onMounted, onUnmounted, ref } from "vue";
import { useRouter } from "vue-router";
import type {
  PortfolioSummaryResponse,
  PortfolioCompanyMetrics,
} from "@/api/financials";
import type { CompanyListItem, SectorBrief } from "@/api/companies";
import { fmtBigNumber } from "./financialsHelpers";
import { useFormatters } from "@/composables/useFormatters";
import { useI18n } from "@/composables/useI18n";
import { i18nKey } from "@/locale/keys";
import { resolveCompanyDisplayName, sectorDisplayName } from "@/utils/displayNames";

const fmt = useFormatters();
const { t } = useI18n();

type KpiId = "revenue" | "opMargin" | "ebitda" | "netMargin" | "loss";

const props = defineProps<{
  kpi: KpiId;
  summary: PortfolioSummaryResponse;
  companies: CompanyListItem[];
  sectors: SectorBrief[];
  year: number;
  unit: "bln" | "mln";
  currency: "UZS" | "USD" | "EUR";
  standard: "IFRS" | "NSBU";
}>();
const localizedUnit = () => t(props.unit === "bln" ? i18nKey("млрд") : i18nKey("млн"));

const emit = defineEmits<{ close: [] }>();
const router = useRouter();

// ─── Mode detection ───
const mode = computed<"financial" | "status">(() =>
  props.kpi === "loss" ? "status" : "financial",
);

// ─── KPI config (label, accent, hero metric, hero unit, etc.) ───
const KPI_CONFIG: Record<KpiId, {
  label: string; title: string; accent: string;
  metric: "revenue" | "opProfit" | "opMargin" | "ebitda" | "netProfit" | "netMargin" | null;
  heroUnit: "value" | "pct" | "count";
  showMargin: "opMargin" | "ebitdaMargin" | "netMargin" | null;
}> = {
  revenue:   { label: i18nKey("FINANCIAL KPI · ВЫРУЧКА"),         title: i18nKey("Совокупная выручка портфеля"),   accent: "#1D9E75", metric: "revenue",   heroUnit: "value", showMargin: null },
  opMargin:  { label: i18nKey("FINANCIAL KPI · ОПЕР. МАРЖА"),     title: i18nKey("Операционная маржа портфеля"),   accent: "#7F77DD", metric: "opMargin",  heroUnit: "pct",   showMargin: "opMargin" },
  ebitda:    { label: "FINANCIAL KPI · EBITDA",          title: i18nKey("EBITDA портфеля"),               accent: "#EF9F27", metric: "ebitda",    heroUnit: "value", showMargin: "ebitdaMargin" },
  netMargin: { label: i18nKey("FINANCIAL KPI · ЧИСТАЯ МАРЖА"),    title: i18nKey("Чистая маржа портфеля"),         accent: "#378ADD", metric: "netMargin", heroUnit: "pct",   showMargin: "netMargin" },
  loss:      { label: i18nKey("STATUS · УБЫТОЧНЫЕ"),              title: i18nKey("Убыточные компании портфеля"),   accent: "#E24B4A", metric: null,        heroUnit: "count", showMargin: null },
};

const cfg = computed(() => KPI_CONFIG[props.kpi]);

// ─── Sector lookup ───
const sectorByCode = computed<Map<string, SectorBrief>>(() => {
  const m = new Map<string, SectorBrief>();
  for (const s of props.sectors) m.set(s.code.toLowerCase(), s);
  return m;
});
function sectorColor(code: string | null): string {
  if (!code) return "#888780";
  const s = sectorByCode.value.get(code.toLowerCase());
  return s?.color_hex || "#888780";
}
function sectorLabel(code: string | null): string {
  if (!code) return "—";
  const s = sectorByCode.value.get(code.toLowerCase());
  return sectorDisplayName(s) || code;
}

// ─── Core values per KPI ───
function getMetricValue(it: PortfolioCompanyMetrics, year: number): number {
  const y = it.by_year[year];
  if (!y) return 0;
  switch (props.kpi) {
    case "revenue":   return (y.revenue ?? 0) as number;
    case "opMargin":  {
      const r = y.revenue ?? 0;
      return r ? ((y.opProfit ?? 0) / r) * 100 : 0;
    }
    case "ebitda":    return (y.ebitda ?? 0) as number;
    case "netMargin": {
      const r = y.revenue ?? 0;
      return r ? ((y.profit ?? 0) / r) * 100 : 0;
    }
    case "loss":      return (y.profit ?? 0) as number;
    default:          return (y.revenue ?? 0) as number;
  }
}

const totalsForYear = computed(() => props.summary.portfolio_totals_by_year[props.year] || {});

// Дрилл считал маржи и YoY заново, из портфельных сумм, — и расходился с
// плиткой, по которой в него кликнули (на плитке +16% like-for-like, здесь
// −8% по сырым итогам). Формулы здесь те же, что в computePortfolioKpis:
// в дробь попадает компания, у которой есть ОБА слагаемых.
function pairMargin(field: "opProfit" | "ebitda" | "profit", y: number) {
  let num = 0, den = 0, pairs = 0;
  for (const item of props.summary.items) {
    const d = item.by_year[y];
    const v = d?.[field];
    const rev = d?.revenue;
    if (v != null && rev != null) { num += v; den += rev; pairs += 1; }
  }
  return { pct: den > 0 ? (num / den) * 100 : null, pairs };
}
function pairYoY(field: "revenue" | "ebitda", y: number) {
  let cur = 0, prev = 0, pairs = 0;
  for (const item of props.summary.items) {
    const c = item.by_year[y]?.[field];
    const p = item.by_year[y - 1]?.[field];
    if (c != null && p != null) { cur += c; prev += p; pairs += 1; }
  }
  return { pct: prev > 0 ? ((cur - prev) / prev) * 100 : null, pairs };
}
const revenueYoYPair = computed(() => pairYoY("revenue", props.year));
const ebitdaYoYPair = computed(() => pairYoY("ebitda", props.year));
/** Подпись «по скольким компаниям» — та же логика, что на плитке. */
const basisNote = computed(() => {
  if (mode.value !== "financial") return "";
  if (props.kpi === "revenue") {
    const n = revenueYoYPair.value.pairs;
    return n ? t("сравнение по {n} сопоставимым", { n }) : "";
  }
  if (props.kpi === "ebitda") {
    const n = ebitdaYoYPair.value.pairs;
    return n ? t("сравнение по {n} сопоставимым", { n }) : "";
  }
  if (props.kpi === "opMargin") {
    const n = pairMargin("opProfit", props.year).pairs;
    return n ? t("по {n} компаниям с обеими строками", { n }) : "";
  }
  if (props.kpi === "netMargin") {
    const n = pairMargin("profit", props.year).pairs;
    return n ? t("по {n} компаниям с обеими строками", { n }) : "";
  }
  return "";
});

const heroValue = computed<number>(() => {
  const t = totalsForYear.value;
  const revenue = t.revenue || 0;
  switch (props.kpi) {
    case "revenue":   return revenue;
    case "opMargin":  return pairMargin("opProfit", props.year).pct ?? 0;
    case "ebitda":    return t.ebitda || 0;
    case "netMargin": return pairMargin("profit", props.year).pct ?? 0;
    case "loss":      return countLossMakers.value;
  }
  return 0;
});

const heroUnit = computed(() => {
  const u = localizedUnit();
  switch (cfg.value.heroUnit) {
    case "value": return `${u} ${props.currency}`;
    case "pct":   return "%";
    case "count": return t("компаний");
  }
  return "";
});

// EBITDA / op margin / net margin shown as sub-text
const marginText = computed(() => {
  const tot = totalsForYear.value;
  const r = tot.revenue || 0;
  const m = cfg.value.showMargin;
  if (!m || !r) return "";
  const u = localizedUnit();
  if (m === "ebitdaMargin") return t("маржа {v}", { v: fmt.fmtPercent(pairMargin("ebitda", props.year).pct ?? 0, { decimals: 0 }) });
  if (m === "opMargin")     return t("опер. прибыль {v} {u}", { v: fmtBigNumber(tot.opProfit || 0, props.unit), u });
  if (m === "netMargin")    return t("чистая прибыль {v} {u}", { v: fmtBigNumber(tot.profit || 0, props.unit), u });
  return "";
});

// YoY for financial mode
const yoyPct = computed<number | null>(() => {
  if (mode.value !== "financial") return null;
  switch (props.kpi) {
    case "revenue": return revenueYoYPair.value.pct;
    case "ebitda":  return ebitdaYoYPair.value.pct;
    case "opMargin": {
      const c = pairMargin("opProfit", props.year).pct;
      const p = pairMargin("opProfit", props.year - 1).pct;
      return c != null && p != null ? c - p : null; // delta in p.p.
    }
    case "netMargin": {
      const c = pairMargin("profit", props.year).pct;
      const p = pairMargin("profit", props.year - 1).pct;
      return c != null && p != null ? c - p : null;
    }
  }
  return null;
});

const yoyIsPp = computed(() => props.kpi === "opMargin" || props.kpi === "netMargin");

// ─── Loss-makers ───
const countLossMakers = computed<number>(() => {
  let n = 0;
  for (const it of props.summary.items) {
    const y = it.by_year[props.year];
    if (!y) continue;
    if (y.profit != null && y.profit < 0) n += 1;
  }
  return n;
});

// ─── Sector breakdown (financial mode: 4 mini-KPIs) ───
interface SectorBucket { code: string; label: string; color: string; sum: number; }
const sectorBuckets = computed<SectorBucket[]>(() => {
  if (mode.value !== "financial") return [];
  const map: Record<string, SectorBucket> = {};
  for (const it of props.summary.items) {
    const sec = it.sector_code || "other";
    if (!map[sec]) {
      map[sec] = { code: sec, label: sectorLabel(sec), color: sectorColor(sec), sum: 0 };
    }
    const v = getMetricValue(it, props.year);
    // For margins, can't simply sum — use revenue-weighted avg
    if (cfg.value.heroUnit === "pct") {
      const y = it.by_year[props.year];
      map[sec].sum += (y?.revenue ?? 0); // store revenue, recompute below
    } else {
      map[sec].sum += v;
    }
  }
  // For margins: recompute sum as the weighted-avg by recomputing aggregated numerator/denominator
  if (cfg.value.heroUnit === "pct") {
    const num: Record<string, number> = {};
    const den: Record<string, number> = {};
    for (const it of props.summary.items) {
      const sec = it.sector_code || "other";
      const y = it.by_year[props.year];
      if (!y) continue;
      den[sec] = (den[sec] || 0) + (y.revenue ?? 0);
      if (props.kpi === "opMargin")  num[sec] = (num[sec] || 0) + (y.opProfit ?? 0);
      if (props.kpi === "netMargin") num[sec] = (num[sec] || 0) + (y.profit ?? 0);
    }
    for (const sec of Object.keys(map)) {
      const d = den[sec] || 0;
      map[sec].sum = d ? ((num[sec] || 0) / d) * 100 : 0;
    }
  }
  return Object.values(map)
    .filter(b => Math.abs(b.sum) > 0.001)
    .sort((a, b) => b.sum - a.sum)
    .slice(0, 4);
});

const portfolioTotal = computed<number>(() => {
  if (cfg.value.heroUnit === "pct") return 0; // no portfolio-share for margins
  return heroValue.value || 1;
});

function fmtBucketValue(b: SectorBucket): string {
  if (cfg.value.heroUnit === "pct") return fmt.fmtPercent(b.sum, { decimals: 0 });
  return fmtBigNumber(b.sum, props.unit);
}
function fmtBucketSub(b: SectorBucket): string {
  if (cfg.value.heroUnit === "pct") return t("ср.-взв. маржа");
  const pct = portfolioTotal.value ? (b.sum / portfolioTotal.value * 100) : 0;
  const u = localizedUnit();
  return `${u} · ${fmt.fmtPercent(pct, { decimals: 0 })} ${t("портф.")}`;
}

// ─── Yearly time-series (financial mode) ───
const trendYears = computed<number[]>(() => {
  const ys = (props.summary.years || []).slice().sort((a, b) => a - b);
  if (ys.length) return ys;
  return [props.year - 3, props.year - 2, props.year - 1, props.year];
});
interface TrendPoint { year: number; value: number; isCurrent: boolean; isPlan: boolean; }
const trendPoints = computed<TrendPoint[]>(() => {
  const totals = props.summary.portfolio_totals_by_year;
  return trendYears.value.map(y => {
    const t = totals[y] || {};
    let v = 0;
    switch (props.kpi) {
      case "revenue":   v = t.revenue || 0; break;
      case "opMargin":  v = t.revenue ? ((t.opProfit || 0) / t.revenue) * 100 : 0; break;
      case "ebitda":    v = t.ebitda || 0; break;
      case "netMargin": v = t.revenue ? ((t.profit || 0) / t.revenue) * 100 : 0; break;
    }
    return {
      year: y,
      value: v,
      isCurrent: y === props.year,
      isPlan: y > props.year,
    };
  });
});
const trendMax = computed(() =>
  Math.max(0.001, ...trendPoints.value.map(p => Math.abs(p.value))),
);
function trendHeight(p: TrendPoint): number {
  return Math.max(4, (Math.abs(p.value) / trendMax.value) * 70);
}

// ─── Companies list (financial mode: top by metric; status mode: filtered) ───
interface CompanyRow {
  code: string;
  name: string;
  sector: string;
  value: number;
  marginPct: number | null; // for financial
  sharePct: number | null; // for financial (% of portfolio)
  loss: number | null; // for loss mode
}

const allCompanyRows = computed<CompanyRow[]>(() => {
  const rows: CompanyRow[] = [];
  for (const it of props.summary.items) {
    const y = it.by_year[props.year];
    if (!y) continue;
    let value = 0;
    let marginPct: number | null = null;
    if (mode.value === "financial") {
      value = getMetricValue(it, props.year);
      if (props.kpi === "revenue" || props.kpi === "ebitda") {
        const r = y.revenue ?? 0;
        if (r && props.kpi === "ebitda") marginPct = ((y.ebitda || 0) / r) * 100;
      }
    } else {
      value = y.profit ?? 0;
    }
    rows.push({
      code:      it.company_code,
      name:      resolveCompanyDisplayName(
        it.company_name_short || it.company_name || it.company_code,
        it.company_code,
      ),
      sector:    it.sector_code || "other",
      value,
      marginPct,
      sharePct:  null, // computed below
      loss:      y.profit ?? null,
    });
  }
  // sharePct
  const total = heroValue.value || 1;
  for (const r of rows) {
    if (mode.value === "financial" && cfg.value.heroUnit === "value") {
      r.sharePct = (r.value / total) * 100;
    }
  }
  return rows;
});

// Filtered rows per kpi
const filteredRows = computed<CompanyRow[]>(() => {
  let rows = allCompanyRows.value.slice();
  if (props.kpi === "loss") {
    rows = rows.filter(r => r.loss != null && r.loss < 0);
    rows.sort((a, b) => (a.loss ?? 0) - (b.loss ?? 0)); // most negative first
  } else {
    // financial: sort by |value| desc
    rows.sort((a, b) => Math.abs(b.value) - Math.abs(a.value));
  }
  return rows;
});

const TOP_VISIBLE = 5;
const fullyShown = ref(false);
const visibleRows = computed(() =>
  fullyShown.value ? filteredRows.value : filteredRows.value.slice(0, TOP_VISIBLE),
);

// ─── Sector color for row border-left ───
function rowSectorColor(r: CompanyRow): string {
  return sectorColor(r.sector);
}

// ─── Close + navigation ───
function close() { emit("close"); }
function onBackdrop(e: MouseEvent) { if (e.target === e.currentTarget) close(); }
function onKey(e: KeyboardEvent) { if (e.key === "Escape") { e.preventDefault(); close(); } }

function gotoCompany(code: string) {
  router.push({ name: "company-workspace", params: { code } });
  close();
}
// «Detailed Financials» → блок «Высокоуровневые показатели» на той же странице /financials.
function gotoDetailed() {
  close();
  setTimeout(() => {
    document.getElementById("hlf-anchor")?.scrollIntoView({ behavior: "smooth", block: "start" });
  }, 60);
}
// «Финмодель портфеля» → внешний дашборд финмодели.
const FINMODEL_URL = "https://dashboard.uz-assets.uz/soe-dashboard/finmodel-3?modelId=109&currency=UZS&unit=B";
function gotoFinModel() {
  window.open(FINMODEL_URL, "_blank", "noopener");
  close();
}
function gotoForensic() {
  gotoDetailed();
}

let prevOverflow = "";
onMounted(() => {
  prevOverflow = document.body.style.overflow;
  document.body.style.overflow = "hidden";
  window.addEventListener("keydown", onKey);
});
onUnmounted(() => {
  document.body.style.overflow = prevOverflow;
  window.removeEventListener("keydown", onKey);
});

// ─── Display helpers ───
function fmtHero(v: number): string {
  if (cfg.value.heroUnit === "pct")   return fmt.fmtNumber(v, { decimals: 0 });
  if (cfg.value.heroUnit === "count") return String(Math.round(v));
  return fmtBigNumber(v, props.unit);
}
function fmtSigned(v: number, pp = false): string {
  if (pp) {
    const signed = fmt.fmtNumber(v, { decimals: 0 });
    return t("{v} п.п.", { v: `${v >= 0 ? "+" : ""}${signed}` });
  }
  return fmt.fmtPercent(v, { decimals: 0, signed: true });
}
function fmtRowValue(r: CompanyRow): string {
  if (mode.value === "financial") {
    if (cfg.value.heroUnit === "pct") return fmt.fmtPercent(r.value, { decimals: 0 });
    return `${fmtBigNumber(r.value, props.unit)} ${localizedUnit()}`;
  }
  if (props.kpi === "loss") {
    return `${fmtBigNumber(r.loss || 0, props.unit)} ${localizedUnit()}`;
  }
  return "";
}

const summaryChip = computed(() => {
  if (mode.value === "financial") {
    const yoy = yoyPct.value;
    const yoyStr = yoy != null ? t("{v} к {y} году", { v: fmtSigned(yoy, yoyIsPp.value), y: props.year - 1 }) + " · " : "";
    return `${yoyStr}${t("{n} из {m} компаний с данными", { n: countWithData.value, m: props.summary.coverage.companies_total })}`;
  }
  if (props.kpi === "loss") {
    return t("{a} убыточных · {b} прибыльных · YoY к {y}", { a: heroValue.value, b: countWithData.value, y: props.year - 1 });
  }
  return "";
});

const countWithData = computed(() => {
  let n = 0;
  for (const it of props.summary.items) {
    const y = it.by_year[props.year];
    if (y && Object.values(y).some(v => v != null)) n += 1;
  }
  return n;
});
</script>

<template>
  <Teleport to="body">
    <Transition name="uza-fade">
      <div class="ddm-bd" @click="onBackdrop" role="dialog" aria-modal="true">
        <div class="ddm-card" :style="{ '--sc': cfg.accent }">
          <div class="ddm-stripe" aria-hidden="true" />
          <div class="ddm-shim" aria-hidden="true" />
          <div class="ddm-glow" aria-hidden="true" />

          <button class="ddm-x" @click="close" :aria-label="t('Закрыть')">
            <svg viewBox="0 0 14 14" class="svg-ic" width="13" height="13"><path d="M3.5 3.5l7 7M10.5 3.5l-7 7"/></svg>
          </button>

          <!-- ─── Header ─── -->
          <div class="ddm-sect ddm-row" style="--si:0; padding-top:20px;">
            <div class="ddm-h-top">
              <div>
                <div class="ddm-h-l">{{ t(cfg.label) }} · {{ standard }} · FY{{ year }}</div>
                <div class="ddm-h-title">{{ t(cfg.title) }}</div>
                <div class="ddm-h-v">
                  <span class="num" :style="{ color: cfg.accent }">{{ fmtHero(heroValue) }}</span>
                  <span class="unit">{{ heroUnit }}</span>
                  <span v-if="marginText" class="unit"><span style="color: var(--sc, #1E2A4A);">·</span> {{ marginText }}</span>
                </div>
                <span class="ddm-h-d">{{ summaryChip }}</span>
              </div>
              <div class="ddm-h-right">
                <template v-if="mode === 'financial' && yoyPct != null">
                  <div :style="{ color: yoyPct >= 0 ? '#0F6E56' : '#A32D2D' }">
                    {{ t("{v} к прошлому году", { v: fmtSigned(yoyPct, yoyIsPp) }) }}
                    <span v-if="basisNote" class="fkd-basis"> · {{ basisNote }}</span>
                  </div>
                </template>
                <template v-else-if="kpi === 'loss'">
                  <div :style="{ color: heroValue > 0 ? '#A32D2D' : '#0F6E56' }">
                    {{ heroValue > 0 ? t("требуется внимание") : t("все прибыльные") }}
                  </div>
                </template>
                <div class="ddm-h-year">{{ year }} · FY · {{ standard }}</div>
              </div>
            </div>
          </div>

          <!-- ─── Financial mode: 4 sector mini-KPIs ─── -->
          <div v-if="mode === 'financial' && sectorBuckets.length" class="ddm-sect ddm-row" style="--si:1;">
            <div class="ddm-mini-grid">
              <div v-for="(b, i) in sectorBuckets" :key="b.code"
                   class="ddm-mini"
                   :style="{ '--kc': b.color, '--ki': i }">
                <div class="ddm-mk-l">{{ t(b.label) }}</div>
                <div class="ddm-mk-v">{{ fmtBucketValue(b) }}<span class="ddm-mk-u">{{ fmtBucketSub(b) }}</span></div>
              </div>
            </div>
          </div>

          <!-- ─── Status mode: 4 status mini-KPIs ─── -->
          <div v-if="mode === 'status'" class="ddm-sect ddm-row" style="--si:1;">
            <div class="ddm-mini-grid">
              <template v-if="kpi === 'loss'">
                <div class="ddm-mini" style="--kc:#E24B4A; --ki:0;">
                  <div class="ddm-mk-l">{{ t("Убыточных компаний") }}</div>
                  <div class="ddm-mk-v">{{ countLossMakers }}<span class="ddm-mk-u">{{ t("из {n} с данными", { n: countWithData }) }}</span></div>
                </div>
                <div class="ddm-mini" style="--kc:#1D9E75; --ki:1;">
                  <div class="ddm-mk-l">{{ t("Прибыльных") }}</div>
                  <div class="ddm-mk-v">{{ countWithData - countLossMakers }}<span class="ddm-mk-u">{{ t("компаний") }}</span></div>
                </div>
                <div class="ddm-mini" style="--kc:#888780; --ki:2;">
                  <div class="ddm-mk-l">{{ t("Без данных") }}</div>
                  <div class="ddm-mk-v">{{ summary.coverage.companies_total - countWithData }}<span class="ddm-mk-u">{{ t("компаний") }}</span></div>
                </div>
                <div class="ddm-mini" style="--kc:#534AB7; --ki:3;">
                  <div class="ddm-mk-l">{{ t("Всего портфель") }}</div>
                  <div class="ddm-mk-v">{{ summary.coverage.companies_total }}<span class="ddm-mk-u">{{ t("компаний") }}</span></div>
                </div>
              </template>
            </div>
          </div>

          <!-- ─── Financial mode: trend chart ─── -->
          <div v-if="mode === 'financial' && trendPoints.length > 1" class="ddm-sect ddm-row" style="--si:2;">
            <div class="ddm-l-sec">
              <span>{{ t("Динамика") }} · {{ trendYears[0] }}–{{ trendYears[trendYears.length-1] }}</span>
              <span class="side">{{ cfg.heroUnit === "pct" ? "%" : t(unit === "bln" ? t('млрд') : t('млн')) + " " + currency }}</span>
            </div>
            <div class="ddm-trend">
              <div v-for="p in trendPoints" :key="p.year" class="ddm-trend-col">
                <div class="ddm-trend-val">{{ p.isCurrent ? fmtHero(p.value) : "" }}</div>
                <div class="ddm-trend-bar-wrap">
                  <div class="ddm-trend-bar"
                       :class="{ plan: p.isPlan, current: p.isCurrent }"
                       :style="{ height: trendHeight(p) + 'px', '--bar-c': cfg.accent }"></div>
                </div>
                <div class="ddm-trend-year" :class="{ current: p.isCurrent, plan: p.isPlan }">{{ p.year }}</div>
              </div>
            </div>
          </div>

          <!-- ─── Companies list ─── -->
          <div class="ddm-sect ddm-row" :style="`--si:${mode === 'financial' ? 3 : 2};`">
            <div class="ddm-l-sec">
              <span>
                <template v-if="kpi === 'loss'">{{ t("Убыточные компании") }} · {{ filteredRows.length }}</template>
                <template v-else>{{ cfg.heroUnit === "pct" ? t("Топ компаний по марже") : t("Топ компаний по значению") }}</template>
              </span>
              <span class="side">{{ t("{n} компаний", { n: filteredRows.length }) }}</span>
            </div>

            <div v-if="!visibleRows.length" class="ddm-empty">
              <template v-if="kpi === 'loss'">{{ t("Нет убыточных компаний в {y} году", { y: year }) }}</template>
              <template v-else>{{ t("Нет данных по фильтрам") }}</template>
            </div>

            <div v-else class="ddm-items">
              <div
                v-for="r in visibleRows"
                :key="r.code"
                class="ddm-bord-row uza-side-stripe uza-side-stripe-tight"
                :class="`grid-${kpi}`"
                :style="{ '--stripe-color': rowSectorColor(r) }"
                @click="gotoCompany(r.code)"
                :title="t('Открыть карточку — {name}', { name: r.name })"
              >
                <span class="ddm-code-pill">{{ r.code.toUpperCase() }}</span>
                <span class="ddm-itm-name">{{ r.name }}</span>

                <!-- Financial mode columns -->
                <template v-if="mode === 'financial'">
                  <span class="ddm-itm-val">{{ fmtRowValue(r) }}</span>
                  <span v-if="r.marginPct != null" class="ddm-itm-meta" :style="{ color: r.marginPct >= 30 ? '#0F6E56' : r.marginPct >= 10 ? '#854F0B' : '#A32D2D' }">
                    {{ t("маржа {v}", { v: fmt.fmtPercent(r.marginPct, { decimals: 0 }) }) }}
                  </span>
                  <span v-else class="ddm-itm-meta">{{ t(sectorLabel(r.sector)) }}</span>
                  <span v-if="r.sharePct != null" class="ddm-itm-share">{{ fmt.fmtPercent(r.sharePct, { decimals: 0 }) }} {{ t("портф.") }}</span>
                  <span v-else></span>
                </template>

                <!-- Loss mode columns -->
                <template v-else-if="kpi === 'loss'">
                  <span class="ddm-itm-val" style="color:#A32D2D">{{ fmtRowValue(r) }}</span>
                  <span class="ddm-itm-meta">{{ t(sectorLabel(r.sector)) }}</span>
                  <span class="ddm-itm-status" style="color:#A32D2D">{{ t("убыток") }}</span>
                </template>
              </div>
            </div>

            <div v-if="!fullyShown && filteredRows.length > TOP_VISIBLE"
                 class="ddm-show-more" @click="fullyShown = true">
              {{ t("показать ещё {n} компаний", { n: filteredRows.length - TOP_VISIBLE }) }} →
            </div>
          </div>

          <!-- ─── Footer ─── -->
          <div class="ddm-ftr ddm-row" style="--si:4;">
            <button class="ddm-btn ddm-btn-g" @click="close">{{ t("Закрыть") }}</button>
            <template v-if="mode === 'financial'">
              <button class="ddm-btn ddm-btn-w" @click="gotoDetailed">
                {{ t("Высокоуровневые показатели") }}
                <svg viewBox="0 0 14 14" class="svg-ic" width="12" height="12"><path d="M3 7h8M7.5 3.5L11 7l-3.5 3.5"/></svg>
              </button>
              <button class="ddm-btn ddm-btn-p" @click="gotoFinModel">
                {{ t("Финмодель портфеля") }}
                <svg viewBox="0 0 14 14" class="svg-ic" width="12" height="12"><path d="M3 7h8M7.5 3.5L11 7l-3.5 3.5"/></svg>
              </button>
            </template>
            <template v-else>
              <button class="ddm-btn ddm-btn-p" @click="gotoForensic">
                {{ t("Высокоуровневые показатели") }}
                <svg viewBox="0 0 14 14" class="svg-ic" width="12" height="12"><path d="M3 7h8M7.5 3.5L11 7l-3.5 3.5"/></svg>
              </button>
            </template>
          </div>
        </div>
      </div>
    </Transition>
  </Teleport>
</template>

<style scoped>
/* DDM base — imported from DirectionDrillModal pattern */
.ddm-bd { position: fixed; inset: 0; background: rgba(15, 18, 40, 0.45); -webkit-backdrop-filter: blur(8px); backdrop-filter: blur(8px); z-index: var(--z-top, 9990); display: flex; align-items: center; justify-content: center; padding: 24px 16px; overflow-y: auto; }
.ddm-card { position: relative; background: var(--bg1, #fff); border: 1px solid var(--card-border, transparent); border-radius: 14px; box-shadow: 0 24px 64px rgba(15, 23, 60, 0.22), 0 8px 24px rgba(15, 23, 60, 0.10); width: 100%; max-width: 860px; overflow: hidden; animation: ddmIn .55s var(--ease-standard) .08s both; }
.ddm-stripe { position: absolute; top: 0; left: 0; right: 0; height: 3px; background: var(--sc); transform-origin: left center; animation: ddmStripe .75s var(--ease-standard) .2s both; z-index: 3; }
.ddm-shim { position: absolute; top: 0; left: 0; right: 0; height: 3px; background: linear-gradient(90deg, transparent, rgba(255, 255, 255, 0.75), transparent); transform: translateX(-120%); animation: ddmShim 6s ease-in-out 1.5s infinite; pointer-events: none; z-index: 4; }
.ddm-glow { position: absolute; inset: 0; background: radial-gradient(circle at 92% -6%, var(--sc), transparent 42%); opacity: 0.07; pointer-events: none; z-index: 1; }
.ddm-x { position: absolute; top: 14px; right: 14px; width: 28px; height: 28px; border-radius: 8px; display: flex; align-items: center; justify-content: center; cursor: pointer; color: var(--t3, var(--t-muted)); border: 1px solid rgba(0, 0, 0, 0.06); background: var(--bg1, #fff); z-index: 6; transition: all .14s; }
.ddm-x:hover { background: var(--bg2, #FAFAFC); color: var(--t1, #1E2A4A); }

.ddm-row { animation: ddmUp .42s ease both; animation-delay: calc(.32s + var(--si, 0) * .06s); opacity: 0; position: relative; z-index: 2; }
.ddm-sect { padding: 14px 22px; }
.ddm-sect + .ddm-sect { padding-top: 0; }

.ddm-h-top { display: flex; justify-content: space-between; align-items: flex-end; gap: 18px; flex-wrap: wrap; }
.ddm-h-l { font-size: 10.5px; font-weight: 500; color: var(--t3, var(--t-muted)); text-transform: uppercase; letter-spacing: .08em; }
.ddm-h-title { font-size: 19px; font-weight: 500; color: var(--t1, #1E2A4A); margin-top: 3px; letter-spacing: -.01em; }
.ddm-h-v { font-size: 42px; font-weight: 500; letter-spacing: -.035em; line-height: 1; color: var(--t1, #1E2A4A); font-feature-settings: "tnum"; margin-top: 6px; display: flex; align-items: baseline; gap: 8px; flex-wrap: wrap; }
.ddm-h-v .unit { font-size: 13px; color: var(--t3, var(--t-muted)); font-weight: 500; letter-spacing: 0; }
.ddm-h-d { display: inline-flex; align-items: center; gap: 6px; font-size: 11px; font-weight: 500; padding: 3px 9px; border-radius: 999px; margin-top: 8px; background: rgba(127, 119, 221, .08); color: var(--p-deep); }
.ddm-h-right { text-align: right; font-size: 11px; color: var(--t3, var(--t-muted)); font-weight: 500; line-height: 1.7; }
.ddm-h-year { color: var(--t1, #1E2A4A); }

.ddm-mini-grid { display: grid; grid-template-columns: repeat(4, 1fr); gap: 7px; }
.ddm-mini { position: relative; background: var(--bg2, #FAFAFC); border-radius: 9px; padding: 9px 10px 8px; overflow: hidden; }
.ddm-mini::before { content: ""; position: absolute; top: 0; left: 0; right: 0; height: 2px; background: var(--kc); transform-origin: left; transform: scaleX(0); animation: ddmKpiTop .65s var(--ease-standard) calc(.78s + var(--ki) * .09s) forwards; }
.ddm-mk-l { font-size: 8.5px; font-weight: 500; color: var(--t3, var(--t-muted)); text-transform: uppercase; letter-spacing: .05em; line-height: 1.25; min-height: 22px; }
.ddm-mk-v { font-size: 15px; font-weight: 400; letter-spacing: -.02em; color: var(--t1, #1E2A4A); line-height: 1.15; margin-top: 4px; font-feature-settings: "tnum"; }
.ddm-mk-u { font-size: 9.5px; color: var(--t3, var(--t-muted)); font-weight: 500; margin-left: 4px; letter-spacing: 0; }

.ddm-l-sec { font-size: 10px; color: var(--t3, var(--t-muted)); text-transform: uppercase; letter-spacing: .07em; font-weight: 500; margin-bottom: 8px; display: flex; justify-content: space-between; align-items: center; gap: 12px; }
.ddm-l-sec .side { font-size: 9.5px; color: #B4B2A9; text-transform: none; letter-spacing: .02em; font-weight: 400; }

/* Trend chart */
.ddm-trend { background: var(--bg2, #FAFAFC); border-radius: 9px; padding: 12px 14px; display: flex; align-items: flex-end; gap: 10px; min-height: 110px; position: relative; }
.ddm-trend-col { flex: 1; display: flex; flex-direction: column; align-items: center; gap: 4px; min-width: 0; }
.ddm-trend-val { font-size: 10px; color: var(--t1, #1E2A4A); font-weight: 500; min-height: 12px; font-feature-settings: "tnum"; }
.ddm-trend-bar-wrap { width: 100%; display: flex; justify-content: center; align-items: flex-end; min-height: 70px; }
.ddm-trend-bar { width: 18px; background: var(--bar-c, var(--t-muted)); border-radius: 3px 3px 0 0; transition: height .4s var(--ease-standard); }
.ddm-trend-bar.plan { background: rgba(127, 119, 221, .25); border: 1px dashed var(--bar-c, var(--t-muted)); }
.ddm-trend-bar.current { box-shadow: 0 0 0 2px rgba(127, 119, 221, .2); }
.ddm-trend-year { font-size: 9px; color: var(--t3, var(--t-muted)); }
.ddm-trend-year.current { color: var(--t1, #1E2A4A); font-weight: 500; }
.ddm-trend-year.plan { color: #B4B2A9; }

/* Items / rows */
.ddm-items { display: flex; flex-direction: column; gap: 4px; }
.ddm-bord-row { display: grid; gap: 8px; align-items: center; padding: 7px 10px 7px 16px; border-radius: 6px; font-size: 11px; cursor: pointer; background: rgba(15, 23, 60, .015); transition: all .14s; }
.ddm-bord-row:hover { background: rgba(127, 119, 221, .04); transform: translateX(2px); }
.ddm-bord-row.grid-revenue,
.ddm-bord-row.grid-opMargin,
.ddm-bord-row.grid-ebitda,
.ddm-bord-row.grid-netMargin { grid-template-columns: 42px 1fr 100px 90px 70px; }
.ddm-bord-row.grid-loss { grid-template-columns: 42px 1fr 120px 100px 70px; }

.ddm-code-pill { display: inline-flex; align-items: center; justify-content: center; font-size: 8.5px; font-weight: 500; padding: 1px 5px; background: rgba(127, 119, 221, .10); color: var(--p-deep); border-radius: 999px; letter-spacing: .04em; }
.svg-ic { stroke: currentColor; stroke-width: 1.9; fill: none; stroke-linecap: round; stroke-linejoin: round; }
.ddm-itm-name { color: var(--t1, #1E2A4A); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-weight: 500; }
.ddm-itm-val { text-align: right; font-feature-settings: "tnum"; color: var(--t1, #1E2A4A); font-weight: 500; }
.ddm-itm-meta { color: var(--t3, var(--t-muted)); font-size: 10px; text-align: right; font-feature-settings: "tnum"; }
.ddm-itm-share { text-align: right; font-size: 10px; font-weight: 500; color: var(--p-deep); }
.ddm-itm-status { font-size: 10px; font-weight: 500; text-align: right; }

.ddm-show-more { text-align: center; padding: 8px 0 0; font-size: 10.5px; color: var(--p-deep); cursor: pointer; font-weight: 500; transition: color .14s; }
.ddm-show-more:hover { color: #3C3489; }

.ddm-empty { padding: 18px 20px; text-align: center; color: #B4B2A9; font-size: 12px; font-style: italic; background: var(--bg2, #FAFAFC); border-radius: 8px; }

.ddm-ftr { padding: 13px 22px 14px; display: flex; justify-content: flex-end; gap: 9px; border-top: 1px solid rgba(0, 0, 0, 0.05); background: var(--bg2, #FAFAFC); margin-top: 4px; }
.ddm-btn { display: inline-flex; align-items: center; gap: 6px; font-size: 12px; font-weight: 500; padding: 9px 14px; border-radius: 8px; cursor: pointer; transition: all .14s; border: 1px solid transparent; font-family: inherit; }
.ddm-btn-g { background: var(--bg1, #fff); color: var(--t3, #5F5E5A); border-color: rgba(0, 0, 0, 0.10); }
.ddm-btn-g:hover { background: #F5F4F9; color: var(--t1, #1E2A4A); }
.ddm-btn-w { background: var(--bg1, #fff); color: var(--t1, #1E2A4A); border-color: rgba(0, 0, 0, 0.10); }
.ddm-btn-w:hover { background: #F5F4F9; }
.ddm-btn-p { background: var(--sc); color: #fff; }
.ddm-btn-p:hover { filter: brightness(.93); }

.ddm-fade-enter-active, .ddm-fade-leave-active { transition: opacity .28s ease; }
.ddm-fade-enter-from, .ddm-fade-leave-to { opacity: 0; }

@keyframes ddmIn { 0% { opacity: 0; transform: translateY(22px) scale(.96); } 100% { opacity: 1; transform: translateY(0) scale(1); } }
@keyframes ddmStripe { from { transform: scaleX(0); } to { transform: scaleX(1); } }
@keyframes ddmShim { 0% { transform: translateX(-120%); } 60% { transform: translateX(220%); } 100% { transform: translateX(220%); } }
@keyframes ddmUp { from { opacity: 0; transform: translateY(8px); } to { opacity: 1; transform: translateY(0); } }
@keyframes ddmKpiTop { from { transform: scaleX(0); } to { transform: scaleX(1); } }

@media (max-width: 720px) {
  .ddm-mini-grid { grid-template-columns: repeat(2, 1fr); }
  .ddm-bord-row.grid-revenue,
  .ddm-bord-row.grid-opMargin,
  .ddm-bord-row.grid-ebitda,
  .ddm-bord-row.grid-netMargin,
  .ddm-bord-row.grid-loss { grid-template-columns: 42px 1fr 80px; }
  .ddm-bord-row .ddm-itm-share,
  .ddm-bord-row .ddm-itm-status,
  .ddm-bord-row .ddm-itm-meta { display: none; }
}

.fkd-basis { color: var(--t3, #94A3B8); font-weight: 400; }
</style>
