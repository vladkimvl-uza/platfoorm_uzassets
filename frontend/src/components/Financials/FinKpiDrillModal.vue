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
 *   Mode B (status):    loss | standards
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
import { useStandardsCompliance } from "@/composables/useStandardsCompliance";
const fmt = useFormatters();

type KpiId = "revenue" | "opMargin" | "ebitda" | "netMargin" | "loss" | "standards";
type StatusFilter = "all" | "msfo" | "forensic" | "attention";

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

const emit = defineEmits<{ close: [] }>();
const router = useRouter();

// ─── Mode detection ───
const mode = computed<"financial" | "status">(() =>
  props.kpi === "loss" || props.kpi === "standards" ? "status" : "financial",
);

// ─── KPI config (label, accent, hero metric, hero unit, etc.) ───
const KPI_CONFIG: Record<KpiId, {
  label: string; title: string; accent: string;
  metric: "revenue" | "opProfit" | "opMargin" | "ebitda" | "netProfit" | "netMargin" | null;
  heroUnit: "value" | "pct" | "count";
  showMargin: "opMargin" | "ebitdaMargin" | "netMargin" | null;
}> = {
  revenue:   { label: "FINANCIAL KPI · ВЫРУЧКА",         title: "Совокупная выручка портфеля",   accent: "#1D9E75", metric: "revenue",   heroUnit: "value", showMargin: null },
  opMargin:  { label: "FINANCIAL KPI · ОПЕР. МАРЖА",     title: "Операционная маржа портфеля",   accent: "#7F77DD", metric: "opMargin",  heroUnit: "pct",   showMargin: "opMargin" },
  ebitda:    { label: "FINANCIAL KPI · EBITDA",          title: "EBITDA портфеля",               accent: "#EF9F27", metric: "ebitda",    heroUnit: "value", showMargin: "ebitdaMargin" },
  netMargin: { label: "FINANCIAL KPI · ЧИСТАЯ МАРЖА",    title: "Чистая маржа портфеля",         accent: "#378ADD", metric: "netMargin", heroUnit: "pct",   showMargin: "netMargin" },
  loss:      { label: "STATUS · УБЫТОЧНЫЕ",              title: "Убыточные компании портфеля",   accent: "#E24B4A", metric: null,        heroUnit: "count", showMargin: null },
  standards: { label: "COMPLIANCE · ВНЕДРЕНИЕ СТАНДАРТОВ", title: "Внедрение стандартов",        accent: "#534AB7", metric: null,        heroUnit: "count", showMargin: null },
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
  return s?.name_ru || s?.name_en || code;
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

const heroValue = computed<number>(() => {
  const t = totalsForYear.value;
  const revenue = t.revenue || 0;
  switch (props.kpi) {
    case "revenue":   return revenue;
    case "opMargin":  return revenue ? ((t.opProfit || 0) / revenue) * 100 : 0;
    case "ebitda":    return t.ebitda || 0;
    case "netMargin": return revenue ? ((t.profit || 0) / revenue) * 100 : 0;
    case "loss":      return countLossMakers.value;
    case "standards": return msfoCount.value + forensicCount.value;
  }
  return 0;
});

const heroUnit = computed(() => {
  const u = props.unit === "bln" ? "млрд" : "млн";
  switch (cfg.value.heroUnit) {
    case "value": return `${u} ${props.currency}`;
    case "pct":   return "%";
    case "count": return "компаний";
  }
  return "";
});

// EBITDA / op margin / net margin shown as sub-text
const marginText = computed(() => {
  const t = totalsForYear.value;
  const r = t.revenue || 0;
  const m = cfg.value.showMargin;
  if (!m || !r) return "";
  if (m === "ebitdaMargin") return `маржа ${fmt.fmtPercent(((t.ebitda || 0) / r * 100), { decimals: 0 })}`;
  if (m === "opMargin")     return `опер. прибыль ${fmtBigNumber(t.opProfit || 0, props.unit)} ${props.unit === "bln" ? "млрд" : "млн"}`;
  if (m === "netMargin")    return `чистая прибыль ${fmtBigNumber(t.profit || 0, props.unit)} ${props.unit === "bln" ? "млрд" : "млн"}`;
  return "";
});

// YoY for financial mode
const yoyPct = computed<number | null>(() => {
  if (mode.value !== "financial") return null;
  const t = totalsForYear.value;
  const prev = props.summary.portfolio_totals_by_year[props.year - 1] || {};
  switch (props.kpi) {
    case "revenue": {
      const c = t.revenue || 0;
      const p = prev.revenue || 0;
      return p ? ((c - p) / p) * 100 : null;
    }
    case "ebitda": {
      const c = t.ebitda || 0;
      const p = prev.ebitda || 0;
      return p ? ((c - p) / p) * 100 : null;
    }
    case "opMargin": {
      const cr = t.revenue || 0; const pr = prev.revenue || 0;
      const c = cr ? ((t.opProfit || 0) / cr) * 100 : 0;
      const p = pr ? ((prev.opProfit || 0) / pr) * 100 : 0;
      return c - p; // delta in p.p.
    }
    case "netMargin": {
      const cr = t.revenue || 0; const pr = prev.revenue || 0;
      const c = cr ? ((t.profit || 0) / cr) * 100 : 0;
      const p = pr ? ((prev.profit || 0) / pr) * 100 : 0;
      return c - p;
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

// ─── Standards — РЕАЛЬНЫЕ данные (было: захардкоженные 4/22, 8/22 + demo-map
// STANDARDS_STATUS = фабрикация). МСФО = дата публикации в /ifrs-report-history;
// forensic = 'Завершён'+аудитор+годы. Счётчики — в пределах ПОРТФЕЛЯ (summary.items). ───
const _std = useStandardsCompliance();
const _codeById = computed<Map<string, string>>(() => {
  const m = new Map<string, string>();
  for (const c of props.companies) {
    const id = (c as { id?: string }).id;
    const code = (c as { code?: string }).code;
    if (id && code) m.set(String(id), code.toLowerCase());
  }
  return m;
});
const _msfoCodes = computed<Set<string>>(() => {
  const out = new Set<string>();
  for (const id of _std.msfoIds.value) {
    const code = _codeById.value.get(id);
    if (code) out.add(code);
  }
  return out;
});
const _portfolioCodes = computed<string[]>(() =>
  props.summary.items.map(it => (it.company_code || "").toLowerCase()).filter(Boolean));
function _stdOf(code: string): { msfo: "yes" | "no"; forensic: "yes" | "no" } {
  const c = code.toLowerCase();
  return {
    msfo: _msfoCodes.value.has(c) ? "yes" : "no",
    forensic: _std.forensicCodes.value.has(c) ? "yes" : "no",
  };
}
const msfoTotal = computed(() => _portfolioCodes.value.length || props.companies.length);
const forensicTotal = computed(() => msfoTotal.value);
const msfoCount = computed(() => _portfolioCodes.value.filter(c => _msfoCodes.value.has(c)).length);
const forensicCount = computed(() => _portfolioCodes.value.filter(c => _std.forensicCodes.value.has(c)).length);
const noAuditCount = computed(() => Math.max(0, msfoTotal.value - msfoCount.value));

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
  if (cfg.value.heroUnit === "pct") return "ср.-взв. маржа";
  const pct = portfolioTotal.value ? (b.sum / portfolioTotal.value * 100) : 0;
  const u = props.unit === "bln" ? "млрд" : "млн";
  return `${u} · ${fmt.fmtPercent(pct, { decimals: 0 })} портф.`;
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
  msfo: "yes" | "in_progress" | "no" | "na"; // for standards mode
  forensic: "yes" | "no" | "na"; // for standards mode
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
    const std = _stdOf(it.company_code);
    rows.push({
      code:      it.company_code,
      name:      it.company_name_short || it.company_name || it.company_code,
      sector:    it.sector_code || "other",
      value,
      marginPct,
      sharePct:  null, // computed below
      loss:      y.profit ?? null,
      msfo:      std.msfo,
      forensic:  std.forensic,
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
const statusFilter = ref<StatusFilter>("all");

const filteredRows = computed<CompanyRow[]>(() => {
  let rows = allCompanyRows.value.slice();
  if (props.kpi === "loss") {
    rows = rows.filter(r => r.loss != null && r.loss < 0);
    rows.sort((a, b) => (a.loss ?? 0) - (b.loss ?? 0)); // most negative first
  } else if (props.kpi === "standards") {
    if (statusFilter.value === "msfo")      rows = rows.filter(r => r.msfo === "yes");
    if (statusFilter.value === "forensic")  rows = rows.filter(r => r.forensic === "yes");
    if (statusFilter.value === "attention") rows = rows.filter(r => r.msfo === "no" || r.forensic === "no");
    rows.sort((a, b) => {
      const score = (r: CompanyRow) =>
        (r.msfo === "yes" ? 2 : r.msfo === "in_progress" ? 1 : 0) +
        (r.forensic === "yes" ? 2 : 0);
      return score(b) - score(a);
    });
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
  if (props.kpi === "standards") void _std.load();   // реальные МСФО/forensic-данные
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
    return `${v >= 0 ? "+" : ""}${signed} п.п.`;
  }
  return fmt.fmtPercent(v, { decimals: 0, signed: true });
}
function fmtRowValue(r: CompanyRow): string {
  if (mode.value === "financial") {
    if (cfg.value.heroUnit === "pct") return fmt.fmtPercent(r.value, { decimals: 0 });
    return `${fmtBigNumber(r.value, props.unit)} ${props.unit === "bln" ? "млрд" : "млн"}`;
  }
  if (props.kpi === "loss") {
    return `${fmtBigNumber(r.loss || 0, props.unit)} ${props.unit === "bln" ? "млрд" : "млн"}`;
  }
  return "";
}

const summaryChip = computed(() => {
  if (mode.value === "financial") {
    const yoy = yoyPct.value;
    const yoyStr = yoy != null ? `${fmtSigned(yoy, yoyIsPp.value)} к ${props.year - 1} году · ` : "";
    return `${yoyStr}${countWithData.value} из ${props.summary.coverage.companies_total} компаний с данными`;
  }
  if (props.kpi === "loss") {
    return `${heroValue.value} убыточных · ${countWithData.value} прибыльных · YoY к ${props.year - 1}`;
  }
  // standards
  return `${msfoCount.value} МСФО · ${forensicCount.value} FORENSIC · ${noAuditCount.value} компаний требуют внимания`;
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

          <button class="ddm-x" @click="close" aria-label="Закрыть">
            <svg viewBox="0 0 14 14" class="svg-ic" width="13" height="13"><path d="M3.5 3.5l7 7M10.5 3.5l-7 7"/></svg>
          </button>

          <!-- ─── Header ─── -->
          <div class="ddm-sect ddm-row" style="--si:0; padding-top:20px;">
            <div class="ddm-h-top">
              <div>
                <div class="ddm-h-l">{{ cfg.label }} · {{ standard }} · FY{{ year }}</div>
                <div class="ddm-h-title">{{ cfg.title }}</div>
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
                    {{ fmtSigned(yoyPct, yoyIsPp) }} к прошлому году
                  </div>
                </template>
                <template v-else-if="kpi === 'loss'">
                  <div :style="{ color: heroValue > 0 ? '#A32D2D' : '#0F6E56' }">
                    {{ heroValue > 0 ? "требуется внимание" : "все прибыльные" }}
                  </div>
                </template>
                <template v-else-if="kpi === 'standards'">
                  <div>{{ msfoCount }} МСФО · {{ forensicCount }} forensic из {{ msfoTotal }}</div>
                  <div style="color:#A32D2D">без аудированной МСФО: {{ noAuditCount }}</div>
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
                <div class="ddm-mk-l">{{ b.label }}</div>
                <div class="ddm-mk-v">{{ fmtBucketValue(b) }}<span class="ddm-mk-u">{{ fmtBucketSub(b) }}</span></div>
              </div>
            </div>
          </div>

          <!-- ─── Status mode: 4 status mini-KPIs ─── -->
          <div v-if="mode === 'status'" class="ddm-sect ddm-row" style="--si:1;">
            <div class="ddm-mini-grid">
              <template v-if="kpi === 'standards'">
                <div class="ddm-mini" style="--kc:#1D9E75; --ki:0;">
                  <div class="ddm-mk-l">МСФО внедрено</div>
                  <div class="ddm-mk-v">{{ msfoCount }}<span class="ddm-mk-u">из {{ msfoTotal }} · {{ msfoTotal ? Math.round(msfoCount/msfoTotal*100) : 0 }}%</span></div>
                </div>
                <div class="ddm-mini" style="--kc:#EF9F27; --ki:1;">
                  <div class="ddm-mk-l">Forensic-аудит</div>
                  <div class="ddm-mk-v">{{ forensicCount }}<span class="ddm-mk-u">из {{ forensicTotal }} · {{ forensicTotal ? Math.round(forensicCount/forensicTotal*100) : 0 }}%</span></div>
                </div>
                <div class="ddm-mini" style="--kc:#E24B4A; --ki:3;">
                  <div class="ddm-mk-l">Без аудита</div>
                  <div class="ddm-mk-v">{{ noAuditCount }}<span class="ddm-mk-u">компаний</span></div>
                </div>
              </template>
              <template v-else-if="kpi === 'loss'">
                <div class="ddm-mini" style="--kc:#E24B4A; --ki:0;">
                  <div class="ddm-mk-l">Убыточных компаний</div>
                  <div class="ddm-mk-v">{{ countLossMakers }}<span class="ddm-mk-u">из {{ countWithData }} с данными</span></div>
                </div>
                <div class="ddm-mini" style="--kc:#1D9E75; --ki:1;">
                  <div class="ddm-mk-l">Прибыльных</div>
                  <div class="ddm-mk-v">{{ countWithData - countLossMakers }}<span class="ddm-mk-u">компаний</span></div>
                </div>
                <div class="ddm-mini" style="--kc:#888780; --ki:2;">
                  <div class="ddm-mk-l">Без данных</div>
                  <div class="ddm-mk-v">{{ summary.coverage.companies_total - countWithData }}<span class="ddm-mk-u">компаний</span></div>
                </div>
                <div class="ddm-mini" style="--kc:#534AB7; --ki:3;">
                  <div class="ddm-mk-l">Всего портфель</div>
                  <div class="ddm-mk-v">{{ summary.coverage.companies_total }}<span class="ddm-mk-u">компаний</span></div>
                </div>
              </template>
            </div>
          </div>

          <!-- ─── Financial mode: trend chart ─── -->
          <div v-if="mode === 'financial' && trendPoints.length > 1" class="ddm-sect ddm-row" style="--si:2;">
            <div class="ddm-l-sec">
              <span>Динамика · {{ trendYears[0] }}–{{ trendYears[trendYears.length-1] }}</span>
              <span class="side">{{ cfg.heroUnit === "pct" ? "%" : (unit === "bln" ? "млрд" : "млн") + " " + currency }}</span>
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
                <template v-if="kpi === 'standards'">Компании · {{ filteredRows.length }} <span v-if="filteredRows.length !== allCompanyRows.length">из {{ allCompanyRows.length }}</span></template>
                <template v-else-if="kpi === 'loss'">Убыточные компании · {{ filteredRows.length }}</template>
                <template v-else>Топ компаний по {{ cfg.heroUnit === "pct" ? "марже" : "значению" }}</template>
              </span>

              <!-- Status filters for standards -->
              <div v-if="kpi === 'standards'" class="ddm-fltr">
                <span :class="['ddm-fltr-chip', { active: statusFilter === 'all' }]"
                      @click="statusFilter = 'all'">Все</span>
                <span :class="['ddm-fltr-chip', { active: statusFilter === 'msfo' }]"
                      @click="statusFilter = 'msfo'">МСФО</span>
                <span :class="['ddm-fltr-chip', { active: statusFilter === 'forensic' }]"
                      @click="statusFilter = 'forensic'">Forensic</span>
                <span :class="['ddm-fltr-chip', { active: statusFilter === 'attention' }]"
                      @click="statusFilter = 'attention'">Требуют внимания</span>
              </div>
              <span v-else class="side">{{ filteredRows.length }} компаний</span>
            </div>

            <div v-if="!visibleRows.length" class="ddm-empty">
              <template v-if="kpi === 'loss'">Нет убыточных компаний в {{ year }} году</template>
              <template v-else>Нет данных по фильтрам</template>
            </div>

            <div v-else class="ddm-items">
              <div
                v-for="r in visibleRows"
                :key="r.code"
                class="ddm-bord-row uza-side-stripe uza-side-stripe-tight"
                :class="`grid-${kpi}`"
                :style="{ '--stripe-color': rowSectorColor(r) }"
                @click="gotoCompany(r.code)"
                :title="'Открыть карточку — ' + r.name"
              >
                <span class="ddm-code-pill">{{ r.code.toUpperCase() }}</span>
                <span class="ddm-itm-name">{{ r.name }}</span>

                <!-- Financial mode columns -->
                <template v-if="mode === 'financial'">
                  <span class="ddm-itm-val">{{ fmtRowValue(r) }}</span>
                  <span v-if="r.marginPct != null" class="ddm-itm-meta" :style="{ color: r.marginPct >= 30 ? '#0F6E56' : r.marginPct >= 10 ? '#854F0B' : '#A32D2D' }">
                    маржа {{ fmt.fmtPercent(r.marginPct, { decimals: 0 }) }}
                  </span>
                  <span v-else class="ddm-itm-meta">{{ sectorLabel(r.sector) }}</span>
                  <span v-if="r.sharePct != null" class="ddm-itm-share">{{ fmt.fmtPercent(r.sharePct, { decimals: 0 }) }} портф.</span>
                  <span v-else></span>
                </template>

                <!-- Loss mode columns -->
                <template v-else-if="kpi === 'loss'">
                  <span class="ddm-itm-val" style="color:#A32D2D">{{ fmtRowValue(r) }}</span>
                  <span class="ddm-itm-meta">{{ sectorLabel(r.sector) }}</span>
                  <span class="ddm-itm-status" style="color:#A32D2D">убыток</span>
                </template>

                <!-- Standards mode columns -->
                <template v-else>
                  <span class="ddm-std-badge"
                        :class="{
                          'std-yes': r.msfo === 'yes',
                          'std-prog': r.msfo === 'in_progress',
                          'std-no': r.msfo === 'no',
                        }">
                    <template v-if="r.msfo === 'yes'">✓ МСФО</template>
                    <template v-else-if="r.msfo === 'in_progress'">в процессе</template>
                    <template v-else>— нет</template>
                  </span>
                  <span class="ddm-std-badge"
                        :class="{
                          'std-yes': r.forensic === 'yes',
                          'std-no': r.forensic === 'no',
                        }">
                    <template v-if="r.forensic === 'yes'">✓ Forensic</template>
                    <template v-else>— нет</template>
                  </span>
                  <span class="ddm-itm-status"
                        :style="{ color: r.msfo === 'yes' && r.forensic === 'yes' ? '#0F6E56' :
                                          r.msfo === 'no' && r.forensic === 'no' ? '#A32D2D' : '#534AB7' }">
                    <template v-if="r.msfo === 'yes' && r.forensic === 'yes'">полное соответствие</template>
                    <template v-else-if="r.msfo === 'no' && r.forensic === 'no'">критическое отставание</template>
                    <template v-else>переход требует ⚠</template>
                  </span>
                </template>
              </div>
            </div>

            <div v-if="!fullyShown && filteredRows.length > TOP_VISIBLE"
                 class="ddm-show-more" @click="fullyShown = true">
              показать ещё {{ filteredRows.length - TOP_VISIBLE }} компаний →
            </div>
          </div>

          <!-- ─── Footer ─── -->
          <div class="ddm-ftr ddm-row" style="--si:4;">
            <button class="ddm-btn ddm-btn-g" @click="close">Закрыть</button>
            <template v-if="mode === 'financial'">
              <button class="ddm-btn ddm-btn-w" @click="gotoDetailed">
                Высокоуровневые показатели
                <svg viewBox="0 0 14 14" class="svg-ic" width="12" height="12"><path d="M3 7h8M7.5 3.5L11 7l-3.5 3.5"/></svg>
              </button>
              <button class="ddm-btn ddm-btn-p" @click="gotoFinModel">
                Финмодель портфеля
                <svg viewBox="0 0 14 14" class="svg-ic" width="12" height="12"><path d="M3 7h8M7.5 3.5L11 7l-3.5 3.5"/></svg>
              </button>
            </template>
            <template v-else>
              <button class="ddm-btn ddm-btn-p" @click="gotoForensic">
                Высокоуровневые показатели
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

.ddm-fltr { display: flex; gap: 4px; }
.ddm-fltr-chip { padding: 2px 8px; border-radius: 999px; font-size: 10px; letter-spacing: 0; text-transform: none; cursor: pointer; font-weight: 500; color: var(--t3, var(--t-muted)); background: transparent; transition: all .14s; }
.ddm-fltr-chip:hover { color: var(--t1, #1E2A4A); }
.ddm-fltr-chip.active { background: rgba(127, 119, 221, .10); color: var(--p-deep); }

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
.ddm-bord-row.grid-standards { grid-template-columns: 42px 1fr 80px 80px 130px; }

.ddm-code-pill { display: inline-flex; align-items: center; justify-content: center; font-size: 8.5px; font-weight: 500; padding: 1px 5px; background: rgba(127, 119, 221, .10); color: var(--p-deep); border-radius: 999px; letter-spacing: .04em; }
.svg-ic { stroke: currentColor; stroke-width: 1.9; fill: none; stroke-linecap: round; stroke-linejoin: round; }
.ddm-itm-name { color: var(--t1, #1E2A4A); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-weight: 500; }
.ddm-itm-val { text-align: right; font-feature-settings: "tnum"; color: var(--t1, #1E2A4A); font-weight: 500; }
.ddm-itm-meta { color: var(--t3, var(--t-muted)); font-size: 10px; text-align: right; font-feature-settings: "tnum"; }
.ddm-itm-share { text-align: right; font-size: 10px; font-weight: 500; color: var(--p-deep); }
.ddm-itm-status { font-size: 10px; font-weight: 500; text-align: right; }

/* Standards badges */
.ddm-std-badge { text-align: center; font-size: 10px; font-weight: 500; padding: 2px 7px; border-radius: 999px; }
.ddm-std-badge.std-yes { color: #0F6E56; background: rgba(29, 158, 117, .10); }
.ddm-std-badge.std-prog { color: var(--p-deep); background: rgba(127, 119, 221, .10); }
.ddm-std-badge.std-no { color: var(--sev-critical); background: rgba(226, 75, 74, .10); }

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
  .ddm-bord-row.grid-loss,
  .ddm-bord-row.grid-standards { grid-template-columns: 42px 1fr 80px; }
  .ddm-bord-row .ddm-itm-share,
  .ddm-bord-row .ddm-itm-status,
  .ddm-bord-row .ddm-itm-meta { display: none; }
}
</style>
