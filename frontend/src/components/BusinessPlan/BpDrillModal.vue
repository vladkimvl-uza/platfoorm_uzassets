<script setup lang="ts">
/**
 * BpDrillModal — Pack 8.3 Best Mix.
 *
 * 4 distinct visual modes:
 *   kpi      → Variant 1 "Ranked Bars"        (companies ranked by metric, dual bars plan/fact)
 *   pnl-line → Variant 4 "Treemap"            (P&L line decomposed across companies)
 *   company  → Variant 2 "Executive Dashboard" (full profile: KPI cluster + chart + table)
 *   sector   → Variant 3 "Sector Profile"     (donut + company list + benchmarks)
 *
 * All save operations route through bpApi → backend → PostgreSQL.
 */
import { computed, onMounted, ref, watch } from "vue";
import {
  BP_FIELDS,
  bpApi,
  bpFmt,
  num,
  ytdToDeltas,
  type BpComputed,
  type BpPeriod,
  type BpSummary,
} from "@/api/bpKpi";
import { useCompaniesStore } from "@/stores/companies";
import { useFormatters } from "@/composables/useFormatters";
import Odometer from "@/components/Odometer.vue";
const fmt2 = useFormatters();

const companies = useCompaniesStore();
onMounted(() => { void companies.ensureLoaded(); });

const props = defineProps<{
  mode: "kpi" | "company" | "sector" | "pnl-line";
  metric?: string;
  companyId?: string;
  companyName?: string;
  sectorCode?: string;
  sectorLabel?: string;
  lineKey?: string;
  summary: BpSummary;
  year: number;
  period: BpPeriod;
}>();

defineEmits<{ (e: "close"): void }>();

// ──────────────────────────────────────────────────────────────────
//   Shared state
// ──────────────────────────────────────────────────────────────────

const activeMetric = computed(() => props.metric ?? props.lineKey ?? "revenue");

interface CoRow {
  company_id: string;
  name: string;
  color: string;
  plan: number | null;
  fact: number | null;
  ratio: number | null;
}

const coRows = ref<CoRow[]>([]);
const computedData = ref<BpComputed | null>(null);
// YoY-база: ТОТ ЖЕ период прошлого года (для кварталов — та же дельта).
const prevYearBase = ref<BpComputed | null>(null);
const quarterly = ref<{ q: string; plan: number | null; expect: number | null; fact: number | null }[]>([]);

// ──────────────────────────────────────────────────────────────────
//   Load functions per mode
// ──────────────────────────────────────────────────────────────────

// «ЗА КВАРТАЛ»: при period=q2..q4 модалка показывает дельты ytd(q)−ytd(q−1)
// (консистентно со сводкой/company-вью); хранение — нарастающим итогом (НСБУ).
const PREV_Q: Record<string, string | null> = { annual: null, q1: null, q2: "q1", q3: "q2", q4: "q3" };
// Пред. квартал пуст → company-профиль показан нарастающим итогом (ярлык в шапке).
const ytdFallback = ref(false);
function dOf(a: string | number | null | undefined, b: string | number | null | undefined): number | null {
  return (a != null && b != null) ? num(a) - num(b) : null;
}

async function loadKpiOrPnlMode() {
  if (props.mode !== "kpi" && props.mode !== "pnl-line") return;
  if (!activeMetric.value) return;
  const pq = PREV_Q[props.period] ?? null;
  const rows: CoRow[] = [];
  const cos = await bpApi.availableCompanies();
  for (const co of cos) {
    if (!co.years.includes(props.year)) continue;
    try {
      const c = await bpApi.getComputed(co.company_id, props.year, props.period);
      const cell = c.metrics[activeMetric.value];
      if (!cell) continue;
      let plan = cell.plan != null ? num(cell.plan) : null;
      let fact = cell.fact != null ? num(cell.fact) : null;
      if (pq) {
        const pc = await bpApi.getComputed(co.company_id, props.year, pq as BpPeriod);
        const pcell = pc.metrics[activeMetric.value];
        plan = dOf(cell.plan, pcell?.plan);
        fact = dOf(cell.fact, pcell?.fact);
      }
      rows.push({
        company_id: co.company_id,
        name: co.company_name_ru,
        color: co.sector_color || "#888780",
        plan,
        fact,
        ratio: plan != null && plan !== 0 && fact != null ? fact / plan : null,
      });
    } catch { /* skip */ }
  }
  coRows.value = rows;
}

async function loadCompanyMode() {
  if (props.mode !== "company" || !props.companyId) return;
  try {
    const cur = await bpApi.getComputed(props.companyId, props.year, props.period);
    const pq = PREV_Q[props.period] ?? null;
    if (pq) {
      let prevM: Record<string, any> | undefined;
      try { prevM = (await bpApi.getComputed(props.companyId, props.year, pq as BpPeriod)).metrics; } catch { prevM = undefined; }
      const prevEmpty = !prevM || Object.values(prevM).every(
        (c: any) => c.plan == null && c.expect == null && c.fact == null);
      if (prevEmpty) {
        // Пред. квартал пуст → дельты не вычислимы НИ по одной метрике.
        // YTD-фолбэк с ярлыком (прятать имеющийся факт за «—» хуже).
        ytdFallback.value = true;
        computedData.value = cur;
      } else {
        ytdFallback.value = false;
        const metrics: typeof cur.metrics = {};
        for (const k of Object.keys(cur.metrics)) {
          const c = cur.metrics[k];
          const p = prevM?.[k];
          metrics[k] = { plan: dOf(c.plan, p?.plan), expect: dOf(c.expect, p?.expect), fact: dOf(c.fact, p?.fact), fact_auto: false };
        }
        computedData.value = { ...cur, metrics };
      }
    } else {
      ytdFallback.value = false;
      computedData.value = cur;
    }
  } catch (e) { console.error("[bpDrill] company:", e); }

  // Previous year for YoY — ТОТ ЖЕ период прошлого года (для кварталов — дельта
  // того же квартала; раньше квартал сравнивался с годовым фактом → бессмыслица).
  try {
    const pcur = await bpApi.getComputed(props.companyId, props.year - 1, props.period);
    const pq = PREV_Q[props.period] ?? null;
    if (pq) {
      let ppm: Record<string, any> | undefined;
      try { ppm = (await bpApi.getComputed(props.companyId, props.year - 1, pq as BpPeriod)).metrics; } catch { ppm = undefined; }
      const metrics: typeof pcur.metrics = {};
      for (const k of Object.keys(pcur.metrics)) {
        const c = pcur.metrics[k];
        const p = ppm?.[k];
        metrics[k] = { plan: dOf(c.plan, p?.plan), expect: dOf(c.expect, p?.expect), fact: dOf(c.fact, p?.fact), fact_auto: false };
      }
      prevYearBase.value = { ...pcur, metrics };
    } else {
      prevYearBase.value = pcur;
    }
  } catch { prevYearBase.value = null; }

  // Quarterly trend (4 calls). КАНОН: хранимые кварталы — НАРАСТАЮЩИМ ИТОГОМ
  // (НСБУ) → «динамика кварталов» показывает дельты «за квартал» (честный null,
  // когда предыдущий квартал не заполнен).
  try {
    const ytd: typeof quarterly.value = [];
    for (const q of ["q1", "q2", "q3", "q4"] as const) {
      const r = await bpApi.getComputed(props.companyId, props.year, q);
      const c = r.metrics["revenue"] || { plan: null, expect: null, fact: null };
      ytd.push({
        q,
        plan: c.plan != null ? num(c.plan) : null,
        expect: c.expect != null ? num(c.expect) : null,
        fact: c.fact != null ? num(c.fact) : null,
      });
    }
    const dp = ytdToDeltas(ytd.map(d => d.plan));
    const de = ytdToDeltas(ytd.map(d => d.expect));
    const df = ytdToDeltas(ytd.map(d => d.fact));
    quarterly.value = ytd.map((d, i) => ({ q: d.q, plan: dp[i], expect: de[i], fact: df[i] }));
  } catch { quarterly.value = []; }
}

// ──────────────────────────────────────────────────────────────────
//   Variant 1 (kpi/pnl-line): Ranked rows
// ──────────────────────────────────────────────────────────────────

type SortKey = "fact" | "pct" | "delta";
const sortKey = ref<SortKey>("fact");
const filterLow = ref(false);

const sortedRows = computed(() => {
  let arr = coRows.value.slice();
  if (filterLow.value) {
    arr = arr.filter(r => r.ratio != null && r.ratio < 0.9);
  }
  if (sortKey.value === "fact") {
    arr.sort((a, b) => (b.fact ?? 0) - (a.fact ?? 0));
  } else if (sortKey.value === "pct") {
    arr.sort((a, b) => (b.ratio ?? 0) - (a.ratio ?? 0));
  } else { // delta
    arr.sort((a, b) => {
      const da = a.ratio != null ? Math.abs(a.ratio - 1) : 0;
      const db = b.ratio != null ? Math.abs(b.ratio - 1) : 0;
      return db - da;
    });
  }
  return arr;
});

// 2026-05-26: Number-coerce — backend numeric/decimal приходят строками;
// `0 + "500"` = "0500" (concat) ломает totals → wrong overall percentage.
const totalFact = computed(() => coRows.value.reduce((s, x) => s + Number(x.fact ?? 0), 0));
const totalPlan = computed(() => coRows.value.reduce((s, x) => s + Number(x.plan ?? 0), 0));

// ─── Сортируемая таблица декомпозиции по компаниям (вместо treemap) ──
type TblKey = "name" | "fact" | "plan" | "pct" | "share";
const tblSort = ref<{ key: TblKey; dir: "asc" | "desc" }>({ key: "fact", dir: "desc" });
function setTblSort(key: TblKey) {
  if (tblSort.value.key === key) tblSort.value = { key, dir: tblSort.value.dir === "desc" ? "asc" : "desc" };
  else tblSort.value = { key, dir: key === "name" ? "asc" : "desc" };
}
function sortArrow(key: TblKey): string { return tblSort.value.key === key ? (tblSort.value.dir === "desc" ? "▾" : "▴") : "⇅"; }
function pctColor(r: number | null): string {
  if (r == null) return "#888780";
  return r >= 1 ? "#0F6E56" : r >= 0.9 ? "#A36500" : "#A32D2D";
}
const tableRows = computed(() => {
  const tot = totalFact.value || 0;
  const arr = coRows.value.map(r => ({
    ...r,
    share: (tot > 0 && r.fact != null) ? (Number(r.fact) / tot) * 100 : null,
  }));
  const { key, dir } = tblSort.value;
  const sign = dir === "desc" ? -1 : 1;
  const NEG = Number.NEGATIVE_INFINITY;
  arr.sort((a, b) => {
    if (key === "name") return sign * a.name.localeCompare(b.name, "ru");
    const pick = (x: typeof a) => key === "fact" ? (x.fact ?? NEG) : key === "plan" ? (x.plan ?? NEG) : key === "pct" ? (x.ratio ?? NEG) : (x.share ?? NEG);
    return sign * (Number(pick(a)) - Number(pick(b)));
  });
  return arr;
});
const overallPct = computed(() => totalPlan.value > 0 ? totalFact.value / totalPlan.value : null);

const maxFactPlan = computed(() => {
  const arr = coRows.value.flatMap(r => [r.fact ?? 0, r.plan ?? 0]);
  if (!arr.length) return 1;
  const m = Math.max(...arr);
  return m === 0 ? 1 : m;
});

function ratioColor(r: number | null): string {
  if (r == null) return "#94A3B8";
  if (r >= 1.0) return "#0F6E56";
  if (r >= 0.9) return "#A36500";
  return "#A32D2D";
}
function ratioBg(r: number | null): string {
  if (r == null) return "rgba(148,163,184,.12)";
  if (r >= 1.0) return "rgba(29,158,117,.1)";
  if (r >= 0.9) return "rgba(239,159,39,.12)";
  return "rgba(226,75,74,.12)";
}
function ratioStripe(r: number | null): string {
  if (r == null) return "#B8B7B0";
  if (r >= 1.0) return "#5DC093";
  if (r >= 0.9) return "#EFB373";
  return "#E2807F";
}

// ──────────────────────────────────────────────────────────────────
//   Variant 4 (pnl-line): Treemap
// ──────────────────────────────────────────────────────────────────

interface TreemapTile {
  name: string;
  value: number;
  ratio: number | null;
  x: number; y: number; w: number; h: number;
  color: string;
}

// Simple binary partition treemap (sorted by value desc)
function partitionTreemap(
  items: { name: string; value: number; ratio: number | null }[],
  x: number, y: number, w: number, h: number, vertical: boolean,
): TreemapTile[] {
  if (!items.length) return [];
  if (items.length === 1) {
    return [{
      name: items[0].name,
      value: items[0].value,
      ratio: items[0].ratio,
      x, y, w, h,
      color: tileColorByRatio(items[0].ratio),
    }];
  }
  const total = items.reduce((s, i) => s + Math.abs(i.value), 0);
  let acc = 0, split = 1;
  for (let i = 0; i < items.length; i++) {
    acc += Math.abs(items[i].value);
    if (acc >= total / 2) { split = i + 1; break; }
  }
  const g1 = items.slice(0, split);
  const g2 = items.slice(split);
  const sum1 = g1.reduce((s, i) => s + Math.abs(i.value), 0);
  const ratio = total > 0 ? sum1 / total : 0.5;

  if (vertical) {
    const sw = w * ratio;
    return [
      ...partitionTreemap(g1, x, y, sw, h, false),
      ...partitionTreemap(g2, x + sw, y, w - sw, h, false),
    ];
  } else {
    const sh = h * ratio;
    return [
      ...partitionTreemap(g1, x, y, w, sh, true),
      ...partitionTreemap(g2, x, y + sh, w, h - sh, true),
    ];
  }
}

function tileColorByRatio(r: number | null): string {
  if (r == null) return "#B8B7B0";
  if (r >= 1.0) return "#5DC093";
  if (r >= 0.9) return "#EFB373";
  if (r < 0) return "#E2807F"; // negative profit
  return "#E2807F";
}

const treemapTiles = computed<TreemapTile[]>(() => {
  const items = coRows.value
    .filter(r => r.fact != null && r.fact !== 0)
    .map(r => ({ name: r.name, value: r.fact!, ratio: r.ratio }))
    .sort((a, b) => Math.abs(b.value) - Math.abs(a.value));
  if (!items.length) return [];

  // Aggregate tail into "Прочие" if more than 12 items
  const TOP = 11;
  let main = items;
  if (items.length > TOP + 1) {
    const head = items.slice(0, TOP);
    const tail = items.slice(TOP);
    const tailSum = tail.reduce((s, i) => s + Number(i.value), 0);
    main = [...head, { name: `${tail.length} прочих`, value: tailSum, ratio: null }];
  }
  return partitionTreemap(main, 0, 0, 680, 260, true);
});

const treemapTotal = computed(() => coRows.value.reduce((s, r) => s + Number(r.fact ?? 0), 0));
const treemapTop3Share = computed(() => {
  const sorted = coRows.value.filter(r => r.fact != null).sort((a, b) => Number(b.fact ?? 0) - Number(a.fact ?? 0));
  const top3 = sorted.slice(0, 3).reduce((s, r) => s + Number(r.fact ?? 0), 0);
  return treemapTotal.value > 0 ? (top3 / treemapTotal.value) * 100 : 0;
});
const treemapTop3Names = computed(() => {
  const sorted = coRows.value.filter(r => r.fact != null).sort((a, b) => (b.fact ?? 0) - (a.fact ?? 0));
  return sorted.slice(0, 3).map(r => shortName(r.name)).join(" · ");
});

function shortName(n: string): string {
  // Убираем правовую форму (АО/АК/…) и кавычки, берём содержательное имя —
  // иначе «АО «Узбекнефтегаз»» давало просто «АО» (топ-3 = «АО · АО · АО»).
  let s = (n || "").trim()
    .replace(/^(АО|АК|АЖ|ОАО|ООО|АТ|МЧЖ|ДК|UE|GUP|ГУП)\s+/i, "")
    .replace(/[«»"„""]/g, "")
    .trim();
  if (!s) s = (n || "").trim();
  return s.length > 18 ? s.slice(0, 17) + "…" : s;
}

// ──────────────────────────────────────────────────────────────────
//   Variant 2 (company): Executive Dashboard
// ──────────────────────────────────────────────────────────────────

interface KpiHero {
  key: string;
  label: string;
  accent: string;
  fact: number | null;
  plan: number | null;
  factAuto: boolean;
  pctOfPlan: number | null;
  yoyPct: number | null;
}

const kpiHeroes = computed<KpiHero[]>(() => {
  if (!computedData.value) return [];
  const m = computedData.value.metrics;
  const prev = prevYearBase.value?.metrics || {};
  const build = (key: string, label: string, accent: string): KpiHero => {
    const c = m[key] || { plan: null, expect: null, fact: null };
    const fact = c.fact != null ? num(c.fact) : null;
    const plan = c.plan != null ? num(c.plan) : null;
    const prevFact = prev[key]?.fact != null ? num(prev[key]!.fact!) : null;
    return {
      key, label, accent,
      fact, plan,
      factAuto: !!c.fact_auto,
      pctOfPlan: (fact != null && plan != null && plan !== 0) ? fact / plan : null,
      yoyPct: (fact != null && prevFact != null && prevFact !== 0) ? (fact - prevFact) / Math.abs(prevFact) : null,
    };
  };
  return [
    build("revenue",  "Выручка",             "#7F77DD"),
    build("opProfit", "Операционная прибыль", "#1D9E75"),
    build("profit",   "Чистая прибыль",       "#378ADD"),
    build("opProfit", "EBITDA (≈ opProfit)",  "#EF9F27"),
  ];
});

const nsbuAutoCount = computed(() => {
  if (!computedData.value) return 0;
  return Object.values(computedData.value.metrics).filter(c => c.fact_auto).length;
});

const chartMax = computed(() => {
  const vals = quarterly.value.flatMap(d => [d.plan, d.expect, d.fact]).filter((v): v is number => v != null);
  if (!vals.length) return 1;
  const m = Math.max(0, ...vals);
  return m === 0 ? 1 : m;
});
// Нижняя граница: отрицательная дельта рисуется вниз от нулевой базы, а не
// исчезает (SVG отбрасывает rect с отрицательной высотой).
const chartMin = computed(() => {
  const vals = quarterly.value.flatMap(d => [d.plan, d.expect, d.fact]).filter((v): v is number => v != null);
  return vals.length ? Math.min(0, ...vals) : 0;
});
const chartRange = computed(() => (chartMax.value - chartMin.value) || 1);
function qY(v: number) { return 14 + (1 - (v - chartMin.value) / chartRange.value) * 92; }
const qBaseY = computed(() => qY(0));
function qBarY(v: number) { return Math.min(qY(v), qBaseY.value); }
function qBarH(v: number) { return v === 0 ? 0 : Math.max(1, Math.abs(qY(v) - qBaseY.value)); }
const hasQuarterly = computed(() => quarterly.value.some(d => d.plan != null || d.fact != null || d.expect != null));

const achievements = computed(() => {
  if (!computedData.value) return [];
  const m = computedData.value.metrics;
  const res: { title: string; ratio: number; fact: number; plan: number }[] = [];
  for (const f of BP_FIELDS) {
    if (f.sub || f.positive) continue;
    const c = m[f.key];
    if (!c || c.plan == null || num(c.plan) === 0 || c.fact == null) continue;
    const r = num(c.fact) / num(c.plan);
    if (r >= 1.0) res.push({ title: f.label, ratio: r, fact: num(c.fact), plan: num(c.plan) });
  }
  return res.sort((a, b) => b.ratio - a.ratio).slice(0, 3);
});

const detailsExpanded = ref(false);
const visibleFields = computed(() => {
  if (detailsExpanded.value) return BP_FIELDS.filter(f => !f.sub);
  return BP_FIELDS.filter(f => !f.sub && (f.auto || ["revenue", "cogs", "opExpenses"].includes(f.key)));
});

// ──────────────────────────────────────────────────────────────────
//   Variant 3 (sector): Sector Profile
// ──────────────────────────────────────────────────────────────────

const sectorRows = computed(() => {
  if (props.mode !== "sector" || !props.sectorCode) return [];
  return props.summary.by_company
    .filter(c => c.sector_code === props.sectorCode)
    .sort((a, b) => num(b.rev_fact) - num(a.rev_fact));
});

const sectorTotalRevenue = computed(() =>
  sectorRows.value.reduce((s, c) => s + num(c.rev_fact), 0),
);

const portfolioTotalRevenue = computed(() =>
  props.summary.by_company.reduce((s, c) => s + num(c.rev_fact), 0),
);

const sectorShare = computed(() =>
  portfolioTotalRevenue.value > 0 ? (sectorTotalRevenue.value / portfolioTotalRevenue.value) * 100 : 0,
);

const sectorBenchmarks = computed(() => {
  const rows = sectorRows.value;
  if (!rows.length) return null;
  const avgPct = rows.reduce((s, c) => s + (c.pct ?? 0), 0) / rows.length;
  const leader = rows.reduce((best, c) => (best == null || num(c.rev_fact) > num(best.rev_fact)) ? c : best, rows[0]);
  return {
    avgPct,
    leaderName: shortName(leader?.company_name_ru || "—"),
    coCount: rows.length,
  };
});

// SVG Donut segments for sector ring (companies as slices)
interface DonutSeg { color: string; len: number; offset: number; label: string; }
const DONUT_R = 70;
const DONUT_C = 2 * Math.PI * DONUT_R;

const donutSegments = computed<DonutSeg[]>(() => {
  const rows = sectorRows.value;
  if (!rows.length) return [];
  const total = sectorTotalRevenue.value || 1;
  const palette = ["#378ADD", "#7F77DD", "#1D9E75", "#EF9F27", "#E24B4A", "#888780"];
  let offset = 0;
  const segs: DonutSeg[] = [];
  for (let i = 0; i < rows.length; i++) {
    const v = num(rows[i].rev_fact);
    const len = (v / total) * DONUT_C;
    segs.push({
      color: palette[i % palette.length],
      len,
      offset: -offset,
      label: shortName(rows[i].company_name_ru),
    });
    offset += len;
  }
  return segs;
});

// ──────────────────────────────────────────────────────────────────
//   Header (mode-aware)
// ──────────────────────────────────────────────────────────────────

const headerEyebrow = computed(() => {
  if (props.mode === "kpi") return "KPI · детализация по портфелю";
  if (props.mode === "pnl-line") return "Строка P&L · декомпозиция по компаниям";
  if (props.mode === "company") return "Бизнес-план компании · полный профиль";
  if (props.mode === "sector") return "Сектор · профиль и компании";
  return "";
});

const headerTitle = computed(() => {
  if (props.mode === "kpi" || props.mode === "pnl-line") {
    const f = BP_FIELDS.find(x => x.key === activeMetric.value);
    return f?.label ?? activeMetric.value ?? "—";
  }
  if (props.mode === "company") return props.companyName ?? "—";
  if (props.mode === "sector") return props.sectorLabel ?? props.sectorCode ?? "—";
  return "—";
});

const periodLabel = computed(() => {
  // Квартальный срез = величины ЗА квартал (дельты YTD-хранения);
  // пустой пред. квартал → YTD-фолбэк с честным ярлыком.
  const p = props.period === "annual"
    ? "годовой итог"
    : ytdFallback.value
      ? `нарастающим итогом за ${props.period.toUpperCase()} (пред. квартал не заполнен)`
      : `за квартал ${props.period.toUpperCase()}`;
  return `FY ${props.year} · ${p}`;
});

const headerSub = computed(() => {
  if (props.mode === "kpi" || props.mode === "pnl-line") {
    return `${periodLabel.value} · ${coRows.value.length} компаний · млрд UZS`;
  }
  if (props.mode === "sector") {
    return `${periodLabel.value} · ${sectorRows.value.length} компаний сектора · млрд UZS`;
  }
  return `${periodLabel.value} · млрд UZS`;
});

function fmt(v: number | null | undefined): string {
  if (v == null) return "—";
  return bpFmt(v);
}

// ──────────────────────────────────────────────────────────────────
//   Lifecycle
// ──────────────────────────────────────────────────────────────────

function loadForCurrentMode() {
  if (props.mode === "kpi" || props.mode === "pnl-line") loadKpiOrPnlMode();
  if (props.mode === "company") loadCompanyMode();
  // sector mode uses props.summary directly — no extra load
}

onMounted(() => loadForCurrentMode());
watch(
  () => [props.mode, props.metric, props.lineKey, props.companyId, props.sectorCode, props.year, props.period],
  () => loadForCurrentMode(),
);
</script>

<template>
  <Transition name="bpd-modal">
    <div class="bpd-backdrop" @click.self="$emit('close')">
      <div class="bpd-modal" :class="`bpd-${mode}`">

        <!-- Header (common) -->
        <div class="bpd-header">
          <div class="bpd-h-left">
            <div class="bpd-h-eyebrow">
              <span v-if="mode === 'sector' && sectorRows.length" class="bpd-sector-chip" :style="{ background: donutSegments[0]?.color || '#888780' }"></span>
              {{ headerEyebrow }}
            </div>
            <div class="bpd-h-title">{{ headerTitle }}</div>
            <div class="bpd-h-sub">
              {{ headerSub }}
              <span v-if="mode === 'company' && nsbuAutoCount > 0" class="bpd-h-nsbu">
                <svg width="9" height="9" viewBox="0 0 10 10" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M1.5 5l2.5 2.5L8.5 2.5"/></svg>
                авто из НСБУ: {{ nsbuAutoCount }}
              </span>
            </div>
          </div>
          <button class="bpd-h-close" @click="$emit('close')" aria-label="Закрыть">×</button>
        </div>

        <!-- ════════════════ Variant 1: Ranked Bars (kpi mode) ════════════════ -->
        <div v-if="mode === 'kpi'" class="bpd-body bpd-body-ranked">
          <div v-if="coRows.length === 0" class="bpd-empty">Загрузка данных по компаниям…</div>
          <template v-else>
            <div class="bpd-stat-band">
              <div class="bpd-stat" style="--sc:#7F77DD">
                <div class="bpd-stat-lbl">Сумма факт</div>
                <div class="bpd-stat-val"><Odometer :value="fmt(totalFact)" /></div>
                <div class="bpd-stat-sub">млрд UZS</div>
              </div>
              <div class="bpd-stat" style="--sc:#888780">
                <div class="bpd-stat-lbl">Сумма план</div>
                <div class="bpd-stat-val"><Odometer :value="fmt(totalPlan)" /></div>
                <div class="bpd-stat-sub">млрд UZS</div>
              </div>
              <div class="bpd-stat bpd-stat-status" :class="overallPct != null ? (overallPct >= 1 ? 'ok' : overallPct >= 0.9 ? 'warn' : 'bad') : 'neutral'">
                <div class="bpd-stat-lbl">Выполнение</div>
                <div class="bpd-stat-val"><Odometer :value="overallPct != null ? fmt2.fmtPercent(overallPct * 100, { decimals: 1 }) : '—'" /></div>
                <div class="bpd-stat-sub">{{ overallPct != null ? ((overallPct - 1) * 100 >= 0 ? '▲ ' : '▼ ') + fmt2.fmtPercent(Math.abs((overallPct - 1) * 100), { decimals: 1 }) + ' к плану' : '' }}</div>
              </div>
            </div>

            <div class="bpd-toolbar">
              <button class="bpd-pill" :class="{ active: sortKey === 'fact' }" @click="sortKey = 'fact'">По факту</button>
              <button class="bpd-pill" :class="{ active: sortKey === 'pct' }" @click="sortKey = 'pct'">По % плана</button>
              <button class="bpd-pill" :class="{ active: sortKey === 'delta' }" @click="sortKey = 'delta'">По отклонению</button>
              <div class="bpd-tb-spacer"></div>
              <button class="bpd-pill" :class="{ active: filterLow }" @click="filterLow = !filterLow">Только &lt;90%</button>
            </div>

            <div class="bpd-ranked-list">
              <div v-for="(r, idx) in sortedRows" :key="r.company_id" class="bpd-ranked-row" :style="{ '--d': (idx * 25) + 'ms' }">
                <div class="bpd-rr-stripe" :style="{ background: ratioStripe(r.ratio) }"></div>
                <div class="bpd-rr-body">
                  <div class="bpd-rr-name">{{ r.name }}</div>
                  <div class="bpd-rr-bars">
                    <div class="bpd-rr-bar-plan" :style="{ width: ((r.plan ?? 0) / maxFactPlan * 100) + '%' }"></div>
                    <div class="bpd-rr-bar-fact" :style="{ width: ((r.fact ?? 0) / maxFactPlan * 100) + '%' }"></div>
                  </div>
                </div>
                <div class="bpd-rr-vals">
                  <div class="bpd-rr-fact">{{ fmt(r.fact) }}</div>
                  <div class="bpd-rr-plan">план {{ fmt(r.plan) }}</div>
                </div>
                <div class="bpd-rr-pill" :style="{ background: ratioBg(r.ratio), color: ratioColor(r.ratio) }">
                  {{ r.ratio != null ? fmt2.fmtPercent(r.ratio * 100, { decimals: 1 }) : '—' }}
                </div>
              </div>
            </div>
          </template>
        </div>

        <!-- ════════════════ Variant 4: Treemap (pnl-line mode) ════════════════ -->
        <div v-else-if="mode === 'pnl-line'" class="bpd-body bpd-body-treemap">
          <div v-if="coRows.length === 0" class="bpd-empty">Загрузка декомпозиции по компаниям…</div>
          <template v-else>
            <div class="bpd-stat-band">
              <div class="bpd-stat" style="--sc:#378ADD">
                <div class="bpd-stat-lbl">Итого факт</div>
                <div class="bpd-stat-val"><Odometer :value="fmt(treemapTotal)" /></div>
                <div class="bpd-stat-sub">млрд UZS</div>
              </div>
              <div class="bpd-stat" style="--sc:#7F77DD; background:rgba(127,119,221,.06)">
                <div class="bpd-stat-lbl" style="color:#534AB7">Топ-3 доля</div>
                <div class="bpd-stat-val"><Odometer :value="fmt2.fmtPercent(treemapTop3Share, { decimals: 1 })" /></div>
                <div class="bpd-stat-sub" style="color:#534AB7">{{ treemapTop3Names }}</div>
              </div>
              <div class="bpd-stat bpd-stat-status" :class="overallPct != null ? (overallPct >= 1 ? 'ok' : overallPct >= 0.9 ? 'warn' : 'bad') : 'neutral'">
                <div class="bpd-stat-lbl">% плана</div>
                <div class="bpd-stat-val"><Odometer :value="overallPct != null ? fmt2.fmtPercent(overallPct * 100, { decimals: 1 }) : '—'" /></div>
                <div class="bpd-stat-sub">из плана {{ fmt(totalPlan) }}</div>
              </div>
            </div>

            <div class="bpd-tm-header">
              <span class="bpd-tm-h-l">Декомпозиция по компаниям · клик по столбцу — сортировка</span>
              <span class="bpd-tm-legend">
                <span><span class="dot" style="background:#0F6E56"></span>≥100%</span>
                <span><span class="dot" style="background:#A36500"></span>90-100%</span>
                <span><span class="dot" style="background:#A32D2D"></span>&lt;90%</span>
              </span>
            </div>

            <div class="bpd-tbl-wrap">
              <table class="bpd-tbl">
                <thead>
                  <tr>
                    <th class="bpd-th name" :class="{ on: tblSort.key === 'name' }" @click="setTblSort('name')">Компания <span class="bpd-sort">{{ sortArrow('name') }}</span></th>
                    <th class="bpd-th num" :class="{ on: tblSort.key === 'fact' }" @click="setTblSort('fact')">Факт <span class="bpd-sort">{{ sortArrow('fact') }}</span></th>
                    <th class="bpd-th num" :class="{ on: tblSort.key === 'plan' }" @click="setTblSort('plan')">План <span class="bpd-sort">{{ sortArrow('plan') }}</span></th>
                    <th class="bpd-th num" :class="{ on: tblSort.key === 'pct' }" @click="setTblSort('pct')">% плана <span class="bpd-sort">{{ sortArrow('pct') }}</span></th>
                    <th class="bpd-th share" :class="{ on: tblSort.key === 'share' }" @click="setTblSort('share')">Доля <span class="bpd-sort">{{ sortArrow('share') }}</span></th>
                  </tr>
                </thead>
                <tbody>
                  <tr v-for="r in tableRows" :key="r.company_id">
                    <td class="bpd-td-name"><span class="bpd-co-dot" :style="{ background: r.color }"></span>{{ r.name }}</td>
                    <td class="num strong">{{ r.fact != null ? fmt(r.fact) : '—' }}</td>
                    <td class="num muted">{{ r.plan != null ? fmt(r.plan) : '—' }}</td>
                    <td class="num"><span :style="{ color: pctColor(r.ratio) }">{{ r.ratio != null ? (r.ratio >= 1 ? '▲ ' : r.ratio >= 0.9 ? '● ' : '▼ ') + Math.round(r.ratio * 100) + '%' : '—' }}</span></td>
                    <td class="bpd-td-share">
                      <div class="bpd-share-mini"><div class="bpd-share-mini-fill" :style="{ width: (r.share ?? 0) + '%', background: r.color }"></div></div>
                      <span class="bpd-share-pct">{{ r.share != null ? r.share.toFixed(1) + '%' : '—' }}</span>
                    </td>
                  </tr>
                </tbody>
                <tfoot>
                  <tr>
                    <td class="bpd-td-name">ИТОГО · {{ coRows.length }} комп.</td>
                    <td class="num strong">{{ fmt(totalFact) }}</td>
                    <td class="num muted">{{ fmt(totalPlan) }}</td>
                    <td class="num"><span :style="{ color: pctColor(overallPct) }">{{ overallPct != null ? Math.round(overallPct * 100) + '%' : '—' }}</span></td>
                    <td class="bpd-td-share">100%</td>
                  </tr>
                </tfoot>
              </table>
            </div>
          </template>
        </div>

        <!-- ════════════════ Variant 2: Executive Dashboard (company mode) ════════════════ -->
        <div v-else-if="mode === 'company'" class="bpd-body bpd-body-dashboard">
          <div v-if="!computedData" class="bpd-empty">Загрузка профиля компании…</div>
          <template v-else>
            <div class="bpd-kpi-cluster kpi-rail">
              <div v-for="k in kpiHeroes" :key="k.key + k.label" class="bpd-kpi" :style="{ '--ac': k.accent }">
                <span v-if="k.factAuto" class="bpd-kpi-auto">
                  <svg width="7" height="7" viewBox="0 0 10 10" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"><path d="M1.5 5l2.5 2.5L8.5 2.5"/></svg>
                  НСБУ
                </span>
                <div class="bpd-kpi-lbl">{{ k.label }}</div>
                <div class="bpd-kpi-val"><Odometer :value="fmt(k.fact)" /></div>
                <div class="bpd-kpi-foot">
                  <span v-if="k.pctOfPlan != null" :style="{ color: k.pctOfPlan >= 1 ? '#0F6E56' : k.pctOfPlan >= 0.9 ? '#A36500' : '#A32D2D' }">
                    {{ k.pctOfPlan >= 1 ? '▲' : '●' }} {{ Math.round(k.pctOfPlan * 100) }}% плана
                  </span>
                </div>
              </div>
            </div>

            <div class="bpd-row2">
              <div class="bpd-row2-card">
                <div class="bpd-row2-ttl">Динамика кварталов · выручка</div>
                <div v-if="!hasQuarterly" class="bpd-empty-mini">Квартальные данные не введены</div>
                <svg v-else viewBox="0 0 320 130" style="width:100%;height:130px" preserveAspectRatio="xMidYMid meet">
                  <line v-for="(g, gi) in [0, 0.25, 0.5, 0.75]" :key="gi" :x1="28" :y1="14 + (1 - g) * 92" :x2="312" :y2="14 + (1 - g) * 92" stroke="#E2E8F0" stroke-width="0.5" stroke-dasharray="2 3"/>
                  <line x1="28" :y1="qBaseY" x2="312" :y2="qBaseY" stroke="#1E2A4A" stroke-width="0.8"/>
                  <g v-for="(d, di) in quarterly" :key="d.q">
                    <rect v-if="d.plan != null" :x="48 + di * 70" :y="qBarY(d.plan)" width="11" :height="qBarH(d.plan)" fill="#CECBF6" rx="2"/>
                    <rect v-if="d.expect != null" :x="60 + di * 70" :y="qBarY(d.expect)" width="11" :height="qBarH(d.expect)" fill="#FAC775" rx="2"/>
                    <rect v-if="d.fact != null" :x="72 + di * 70" :y="qBarY(d.fact)" width="11" :height="qBarH(d.fact)" fill="#5DC093" rx="2"/>
                    <text :x="65 + di * 70" y="120" font-size="10" fill="#64748B" text-anchor="middle" font-weight="500">{{ d.q.toUpperCase() }}</text>
                  </g>
                </svg>
                <div class="bpd-chart-lgd">
                  <span><span class="dot" style="background:#CECBF6"></span>План</span>
                  <span><span class="dot" style="background:#FAC775"></span>Ожидание</span>
                  <span><span class="dot" style="background:#5DC093"></span>Факт</span>
                </div>
              </div>

              <div class="bpd-row2-card">
                <div class="bpd-row2-ttl">Достижения периода</div>
                <div v-if="!achievements.length" class="bpd-empty-mini">Нет показателей ≥100% плана</div>
                <div v-else>
                  <div v-for="a in achievements" :key="a.title" class="bpd-ach">
                    <div>
                      <div class="bpd-ach-ttl">{{ a.title }}</div>
                      <div class="bpd-ach-d">факт {{ fmt(a.fact) }} · план {{ fmt(a.plan) }}</div>
                    </div>
                    <div class="bpd-ach-val">{{ Math.round(a.ratio * 100) }}%</div>
                  </div>
                </div>
              </div>
            </div>

            <div class="bpd-pnl">
              <div class="bpd-pnl-hd">
                <div>
                  <div class="bpd-pnl-ttl">Структура ОФР</div>
                  <div class="bpd-pnl-sub">{{ visibleFields.length }} из {{ BP_FIELDS.filter(f => !f.sub).length }} строк</div>
                </div>
                <button class="bpd-pnl-tgl" @click="detailsExpanded = !detailsExpanded">
                  {{ detailsExpanded ? 'Свернуть' : 'Раскрыть все' }}
                </button>
              </div>
              <div class="bpd-pnl-tbl-wrap">
                <table class="bpd-pnl-tbl">
                  <thead><tr><th class="lbl">Показатель</th><th class="r">План</th><th class="r">Ожидание</th><th class="r">Факт</th><th class="r">%</th></tr></thead>
                  <tbody>
                    <tr v-for="f in visibleFields" :key="f.key" :class="{ tot: ['grossProfit','opProfit','hhProfit','pbt','profit'].includes(f.key) }">
                      <td class="lbl">
                        <span v-if="f.auto" class="bpd-auto-tag">∑ расчёт</span>
                        {{ f.label }}
                      </td>
                      <td class="r">{{ fmt(computedData.metrics[f.key]?.plan != null ? num(computedData.metrics[f.key].plan) : null) }}</td>
                      <td class="r">{{ fmt(computedData.metrics[f.key]?.expect != null ? num(computedData.metrics[f.key].expect) : null) }}</td>
                      <td class="r">{{ fmt(computedData.metrics[f.key]?.fact != null ? num(computedData.metrics[f.key].fact) : null) }}</td>
                      <td class="r">
                        <span class="bpd-pct" :style="{
                          background: ratioBg(computedData.metrics[f.key]?.plan != null && num(computedData.metrics[f.key].plan) !== 0 && computedData.metrics[f.key]?.fact != null ? num(computedData.metrics[f.key].fact) / num(computedData.metrics[f.key].plan) : null),
                          color: ratioColor(computedData.metrics[f.key]?.plan != null && num(computedData.metrics[f.key].plan) !== 0 && computedData.metrics[f.key]?.fact != null ? num(computedData.metrics[f.key].fact) / num(computedData.metrics[f.key].plan) : null),
                        }">
                          {{ computedData.metrics[f.key]?.plan != null && num(computedData.metrics[f.key].plan) !== 0 && computedData.metrics[f.key]?.fact != null ? Math.round(num(computedData.metrics[f.key].fact) / num(computedData.metrics[f.key].plan) * 100) + '%' : '—' }}
                        </span>
                      </td>
                    </tr>
                  </tbody>
                </table>
              </div>
            </div>
          </template>
        </div>

        <!-- ════════════════ Variant 3: Sector Profile (sector mode) ════════════════ -->
        <div v-else-if="mode === 'sector'" class="bpd-body bpd-body-sector">
          <div v-if="!sectorRows.length" class="bpd-empty">В выбранном секторе нет компаний с данными</div>
          <template v-else>
            <div class="bpd-sector-grid">
              <div class="bpd-sector-left">
                <div class="bpd-donut-wrap">
                  <svg viewBox="0 0 180 180" style="width:180px;height:180px">
                    <circle cx="90" cy="90" r="70" fill="none" stroke="#F4F3F9" stroke-width="22"/>
                    <circle v-for="(seg, si) in donutSegments" :key="si"
                      cx="90" cy="90" r="70" fill="none"
                      :stroke="seg.color" stroke-width="22"
                      :stroke-dasharray="`${seg.len} ${DONUT_C - seg.len}`"
                      :stroke-dashoffset="seg.offset"
                      stroke-linecap="butt"
                      transform="rotate(-90 90 90)"/>
                  </svg>
                  <div class="bpd-donut-center">
                    <div class="bpd-donut-lbl">Выручка</div>
                    <div class="bpd-donut-val"><Odometer :value="fmt(sectorTotalRevenue)" /></div>
                    <div class="bpd-donut-sub">млрд UZS</div>
                  </div>
                </div>
                <div class="bpd-share-card">
                  <div class="bpd-share-lbl">Доля сектора в портфеле</div>
                  <div class="bpd-share-row">
                    <div class="bpd-share-val"><Odometer :value="fmt2.fmtPercent(sectorShare, { decimals: 1 })" /></div>
                    <div class="bpd-share-of">от {{ fmt(portfolioTotalRevenue) }}</div>
                  </div>
                  <div class="bpd-share-bar">
                    <div class="bpd-share-bar-fill" :style="{ width: sectorShare + '%' }"></div>
                  </div>
                </div>
              </div>

              <div class="bpd-sector-right">
                <div class="bpd-sector-rh">Компании сектора</div>
                <div v-for="(c, ci) in sectorRows" :key="c.company_id" class="bpd-sec-co" :style="{ '--d': (ci * 40) + 'ms' }">
                  <div class="bpd-sec-co-body">
                    <div class="bpd-sec-co-name">{{ c.company_name_ru }}</div>
                    <div class="bpd-sec-co-bar">
                      <div class="bpd-sec-co-fill" :style="{ width: (num(c.rev_fact) / (sectorRows[0] ? num(sectorRows[0].rev_fact) : 1) * 100) + '%', background: donutSegments[ci]?.color || '#888780' }"></div>
                    </div>
                  </div>
                  <div class="bpd-sec-co-vals">
                    <div class="bpd-sec-co-fact">{{ fmt(num(c.rev_fact)) }}</div>
                    <div class="bpd-sec-co-pct" :style="{ color: c.pct != null ? (c.pct >= 100 ? '#0F6E56' : c.pct >= 90 ? '#A36500' : '#A32D2D') : '#888780' }">
                      {{ c.pct != null ? (c.pct >= 100 ? '▲ ' : c.pct >= 90 ? '● ' : '▼ ') + fmt2.fmtPercent(c.pct, { decimals: 1 }) : '—' }}
                    </div>
                  </div>
                </div>
              </div>
            </div>

            <div v-if="sectorBenchmarks" class="bpd-bench-grid">
              <div class="bpd-bench">
                <div class="bpd-bench-lbl">Средн. % плана</div>
                <div class="bpd-bench-val"><Odometer :value="fmt2.fmtPercent(sectorBenchmarks.avgPct, { decimals: 1 })" /></div>
              </div>
              <div class="bpd-bench">
                <div class="bpd-bench-lbl">Компаний</div>
                <div class="bpd-bench-val"><Odometer :value="sectorBenchmarks.coCount" /></div>
              </div>
              <div class="bpd-bench">
                <div class="bpd-bench-lbl">Лидер сектора</div>
                <div class="bpd-bench-val bpd-bench-val-sm">{{ sectorBenchmarks.leaderName }}</div>
              </div>
              <div class="bpd-bench">
                <div class="bpd-bench-lbl">Доля портфеля</div>
                <div class="bpd-bench-val"><Odometer :value="sectorShare.toFixed(1)" />%</div>
              </div>
            </div>
          </template>
        </div>

      </div>
    </div>
  </Transition>
</template>

<style scoped>
/* ─── Backdrop + modal frame ────────────────────────────── */
.bpd-backdrop {
  position: fixed; inset: 0;
  background: rgba(15, 18, 40, .45);
  -webkit-backdrop-filter: blur(8px);
  backdrop-filter: blur(8px);
  z-index: var(--z-overlay, 9000);
  display: flex; align-items: center; justify-content: center;
  padding: 20px;
}
.bpd-modal {
  background: var(--bg1, #fff);
  border-radius: 14px;
  width: 100%; max-width: 760px;
  max-height: 92dvh;
  display: flex; flex-direction: column;
  box-shadow: 0 24px 64px rgba(15, 23, 60, .18);
  overflow: hidden;
  font-family: var(--font, system-ui, -apple-system, "Segoe UI", sans-serif);
}
.bpd-modal-enter-active { transition: opacity .25s ease, transform .35s var(--ease-standard); }
.bpd-modal-leave-active { transition: opacity .15s ease, transform .15s ease; }
.bpd-modal-enter-from, .bpd-modal-leave-to { opacity: 0; transform: scale(.96) translateY(8px); }

/* Wide modal for company mode */
.bpd-modal.bpd-company { max-width: 800px; }
.bpd-modal.bpd-sector { max-width: 720px; }
.bpd-modal.bpd-kpi, .bpd-modal.bpd-pnl-line { max-width: 740px; }

/* ─── Header ────────────────────────────────────────────── */
.bpd-header {
  padding: 22px 26px 16px;
  border-bottom: 1px solid rgba(15, 23, 60, .06);
  display: flex; justify-content: space-between; align-items: flex-start;
  flex-shrink: 0;
}
.bpd-h-eyebrow {
  font-size: 10px; letter-spacing: .08em; text-transform: uppercase;
  color: var(--t3, var(--t-muted)); font-weight: 500; margin-bottom: 5px;
  display: flex; align-items: center; gap: 8px;
}
.bpd-sector-chip {
  display: inline-block; width: 12px; height: 12px;
  border-radius: 3px;
}
.bpd-h-title {
  font-size: 17px; font-weight: 500; color: var(--t1, #1E2A4A);
  letter-spacing: -.01em;
}
.bpd-h-sub {
  font-size: 11px; color: var(--t3, #5F5E5A); margin-top: 5px;
  display: flex; align-items: center; gap: 8px; flex-wrap: wrap;
}
.bpd-h-nsbu {
  display: inline-flex; align-items: center; gap: 4px;
  padding: 2px 7px; background: rgba(29, 158, 117, .1); color: #0F6E56;
  border-radius: 4px; font-size: 9.5px; font-weight: 500;
  letter-spacing: .04em; text-transform: uppercase;
}
.bpd-h-close {
  background: none; border: 0; color: var(--t3, var(--t-muted));
  padding: 2px 6px; cursor: pointer;
  font-size: 22px; line-height: 1;
  transition: color .15s;
}
.bpd-h-close:hover { color: var(--t1, #1E2A4A); }

/* ─── Body (scrollable) ─────────────────────────────────── */
.bpd-body { overflow-y: auto; flex: 1; padding-bottom: 16px; }
.bpd-empty {
  padding: 60px 26px; text-align: center;
  color: var(--t3, var(--t-muted)); font-size: 13px;
}
.bpd-empty-mini { padding: 20px 0; text-align: center; color: var(--t3, var(--t-muted)); font-size: 11px; }

/* ─── Stat band (3 cards) — reused in V1 and V4 ─────────── */
.bpd-stat-band {
  display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 10px;
  padding: 18px 26px 8px;
}
.bpd-stat {
  background: #F4F3F9; border-radius: 10px; padding: 12px 14px;
  position: relative; overflow: hidden;
}
.bpd-stat::before {
  content: ''; position: absolute; top: 0; left: 0; right: 0;
  height: 2px; background: var(--sc, #7F77DD);
}
.bpd-stat-lbl {
  font-size: 9.5px; text-transform: uppercase; letter-spacing: .06em;
  color: var(--t3, var(--t-muted)); font-weight: 500;
}
.bpd-stat-val {
  font-size: 22px; font-weight: 400; color: var(--t1, #1E2A4A);
  letter-spacing: -.025em; margin-top: 4px; font-variant-numeric: tabular-nums;
}
.bpd-stat-sub {
  font-size: 10px; color: var(--t3, var(--t-muted)); margin-top: 2px;
}
.bpd-stat-status.ok      { background: rgba(29, 158, 117, .08); }
.bpd-stat-status.ok::before { background: var(--green); }
.bpd-stat-status.ok .bpd-stat-lbl,
.bpd-stat-status.ok .bpd-stat-val,
.bpd-stat-status.ok .bpd-stat-sub { color: #0F6E56; }
.bpd-stat-status.warn    { background: rgba(239, 159, 39, .08); }
.bpd-stat-status.warn::before { background: var(--amber); }
.bpd-stat-status.warn .bpd-stat-lbl,
.bpd-stat-status.warn .bpd-stat-val,
.bpd-stat-status.warn .bpd-stat-sub { color: #A36500; }
.bpd-stat-status.bad     { background: rgba(226, 75, 74, .08); }
.bpd-stat-status.bad::before { background: var(--sev-high); }
.bpd-stat-status.bad .bpd-stat-lbl,
.bpd-stat-status.bad .bpd-stat-val,
.bpd-stat-status.bad .bpd-stat-sub { color: var(--sev-critical); }

/* ════════════ Variant 1: Ranked Bars ════════════ */
.bpd-toolbar {
  padding: 14px 26px 6px;
  display: flex; gap: 5px; align-items: center;
  font-size: 11px;
}
.bpd-pill {
  padding: 4px 11px; border-radius: 11px;
  background: var(--bg1, #fff); border: 1px solid rgba(15, 23, 60, .1);
  color: var(--t3, #5F5E5A); cursor: pointer; font-family: inherit;
  transition: all .15s;
}
.bpd-pill:hover { background: #FAFAF8; color: var(--t1, #1E2A4A); }
.bpd-pill.active {
  background: #1E2A4A; color: #fff; border-color: #1E2A4A;
  font-weight: 500;
}
.bpd-tb-spacer { flex: 1; }

.bpd-ranked-list { padding: 6px 26px 18px; }
.bpd-ranked-row {
  display: grid;
  grid-template-columns: 4px 1fr 100px 64px;
  gap: 12px; align-items: center;
  padding: 10px 0;
  border-bottom: 0.5px solid rgba(15, 23, 60, .06);
  animation: bpdRowIn .35s cubic-bezier(.22,.61,.36,1) var(--d, 0ms) both;
}
.bpd-ranked-row:last-child { border-bottom: 0; }
@keyframes bpdRowIn { from { opacity: 0; transform: translateY(4px); } to { opacity: 1; transform: translateY(0); } }
.bpd-rr-stripe { width: 4px; height: 30px; border-radius: 2px; }
.bpd-rr-name { font-size: 12.5px; color: var(--t1, #1E2A4A); font-weight: 500; }
.bpd-rr-bars {
  margin-top: 7px; position: relative;
  height: 7px; background: #F4F3F9; border-radius: 4px;
  overflow: hidden;
}
.bpd-rr-bar-plan {
  position: absolute; left: 0; top: 0; height: 100%;
  background: rgba(127, 119, 221, .30); border-radius: 4px;
  transition: width .8s var(--ease-standard);
}
.bpd-rr-bar-fact {
  position: absolute; left: 0; top: 0; height: 100%;
  background: #7F77DD; border-radius: 4px;
  transition: width .8s var(--ease-standard) .1s;
}
.bpd-rr-vals { text-align: right; font-variant-numeric: tabular-nums; }
.bpd-rr-fact { font-size: 12.5px; color: var(--t1, #1E2A4A); font-weight: 500; }
.bpd-rr-plan { font-size: 10px; color: var(--t3, var(--t-muted)); }
.bpd-rr-pill {
  text-align: center; padding: 3px 8px; border-radius: 5px;
  font-size: 11px; font-weight: 500; font-variant-numeric: tabular-nums;
}

/* ════════════ Variant 4: Treemap ════════════ */
.bpd-tm-header {
  padding: 14px 26px 8px;
  display: flex; justify-content: space-between; align-items: center;
  font-size: 10px;
}
.bpd-tm-h-l {
  text-transform: uppercase; letter-spacing: .07em;
  color: var(--t3, var(--t-muted)); font-weight: 500;
}
.bpd-tm-legend {
  display: flex; gap: 10px; color: var(--t3, var(--t-muted));
}
.bpd-tm-legend span { display: inline-flex; align-items: center; gap: 4px; }
.bpd-tm-legend .dot { display: inline-block; width: 9px; height: 9px; border-radius: 2px; }
.bpd-tm-wrap { padding: 0 26px 18px; }
.bpd-tm-rect {
  animation: bpdTmIn .45s var(--ease-standard) var(--d, 0ms) both;
  transform-origin: center;
}
@keyframes bpdTmIn { from { opacity: 0; transform: scale(.85); } to { opacity: 1; transform: scale(1); } }

/* ─── Сортируемая таблица декомпозиции ─── */
.bpd-tbl-wrap { padding: 0 26px 20px; overflow-x: auto; }
.bpd-tbl { width: 100%; border-collapse: collapse; font-size: 12.5px; }
.bpd-tbl thead th {
  position: sticky; top: 0; z-index: 1; background: var(--bg1, #fff);
  padding: 8px 10px; font-size: 10px; font-weight: 600; text-transform: uppercase; letter-spacing: .05em;
  color: var(--t3, #8A8C99); border-bottom: 1.5px solid rgba(15,23,60,.1);
  cursor: pointer; user-select: none; white-space: nowrap; text-align: right;
}
.bpd-tbl thead th.name { text-align: left; }
.bpd-tbl thead th:hover { color: #534AB7; }
.bpd-tbl thead th.on { color: #534AB7; }
.bpd-sort { opacity: .5; font-size: 9px; }
.bpd-tbl thead th.on .bpd-sort { opacity: 1; }
.bpd-tbl tbody td { padding: 7px 10px; border-bottom: 1px solid rgba(15,23,60,.05); vertical-align: middle; }
.bpd-tbl tbody tr:hover td { background: rgba(127,119,221,.045); }
.bpd-tbl .num { text-align: right; font-variant-numeric: tabular-nums; white-space: nowrap; color: var(--t1, #1E2A4A); }
.bpd-tbl .num.strong { font-weight: 600; }
.bpd-tbl .num.muted { color: var(--t3, #8A8C99); }
.bpd-td-name { color: var(--t1, #1E2A4A); white-space: nowrap; }
.bpd-co-dot { display: inline-block; width: 8px; height: 8px; border-radius: 2px; margin-right: 8px; vertical-align: middle; }
.bpd-td-share { display: flex; align-items: center; gap: 9px; min-width: 120px; justify-content: flex-end; }
.bpd-share-mini { flex: 1; max-width: 90px; height: 7px; background: rgba(15,23,60,.06); border-radius: 4px; overflow: hidden; }
.bpd-share-mini-fill { height: 100%; border-radius: 4px; }
.bpd-share-pct { font-size: 11.5px; font-variant-numeric: tabular-nums; color: var(--t2, #475569); min-width: 42px; text-align: right; }
.bpd-tbl tfoot td { padding: 9px 10px; border-top: 1.5px solid rgba(15,23,60,.12); font-weight: 700; background: rgba(127,119,221,.04); }
.bpd-tbl tfoot .bpd-td-name { font-weight: 700; }

/* ════════════ Variant 2: Executive Dashboard ════════════ */
.bpd-kpi-cluster {
  display: grid; grid-template-columns: repeat(4, 1fr); gap: 10px;
  padding: 18px 26px 8px;
}
.bpd-kpi {
  background: var(--bg1, #fff); border: 1px solid rgba(15, 23, 60, .06);
  border-radius: 10px; padding: 12px 14px;
  position: relative; overflow: hidden;
  animation: bpdKpiIn .55s var(--ease-standard) both;
}
.bpd-kpi:nth-child(1) { animation-delay: 100ms; }
.bpd-kpi:nth-child(2) { animation-delay: 160ms; }
.bpd-kpi:nth-child(3) { animation-delay: 220ms; }
.bpd-kpi:nth-child(4) { animation-delay: 280ms; }
@keyframes bpdKpiIn { from { opacity: 0; transform: translateY(8px); } to { opacity: 1; transform: translateY(0); } }
.bpd-kpi::before {
  content: ''; position: absolute; top: 0; left: 0; right: 0;
  height: 3px; background: var(--ac, #7F77DD);
}
.bpd-kpi-auto {
  position: absolute; top: 8px; right: 10px;
  display: inline-flex; align-items: center; gap: 3px;
  padding: 1px 5px; background: rgba(29, 158, 117, .1); color: #0F6E56;
  border-radius: 3px; font-size: 8.5px; font-weight: 500;
  letter-spacing: .04em; text-transform: uppercase;
}
.bpd-kpi-lbl {
  font-size: 9px; text-transform: uppercase; letter-spacing: .07em;
  color: var(--t3, var(--t-muted)); font-weight: 500;
}
.bpd-kpi-val {
  font-size: 24px; font-weight: 400; color: var(--t1, #1E2A4A);
  letter-spacing: -.03em; margin-top: 6px; line-height: 1;
  font-variant-numeric: tabular-nums;
}
.bpd-kpi-foot { font-size: 10px; margin-top: 6px; min-height: 14px; }

.bpd-row2 {
  display: grid; grid-template-columns: 1.2fr 1fr; gap: 12px;
  padding: 8px 26px 12px;
}
.bpd-row2-card {
  background: var(--bg1, #fff); border: 1px solid rgba(15, 23, 60, .06);
  border-radius: 10px; padding: 14px 16px;
}
.bpd-row2-ttl {
  font-size: 10px; text-transform: uppercase; letter-spacing: .07em;
  color: var(--t3, var(--t-muted)); font-weight: 500; margin-bottom: 12px;
}
.bpd-chart-lgd {
  display: flex; gap: 14px; margin-top: 8px;
  font-size: 10px; color: var(--t3, var(--t-muted));
}
.bpd-chart-lgd span { display: inline-flex; align-items: center; gap: 5px; }
.bpd-chart-lgd .dot { display: inline-block; width: 9px; height: 9px; border-radius: 2px; }

.bpd-ach::before { content:""; position:absolute; left:6px; top:8px; bottom:8px; width:4px; border-radius:4px; background:var(--green); }
.bpd-ach {
  position: relative; overflow: hidden;
  padding: 7px 11px 7px 18px; border-radius: 8px; background: rgba(29, 158, 117, .06);
  margin-bottom: 5px;
  display: flex; justify-content: space-between; align-items: flex-start; gap: 8px;
}
.bpd-ach:last-child { margin-bottom: 0; }
.bpd-ach-ttl { font-size: 11.5px; color: var(--t1, #1E2A4A); font-weight: 500; }
.bpd-ach-d { font-size: 10px; color: var(--t3, #5F5E5A); }
.bpd-ach-val { font-size: 11px; color: #0F6E56; font-weight: 500; font-variant-numeric: tabular-nums; }

.bpd-pnl { padding: 0 26px 18px; }
.bpd-pnl-hd {
  display: flex; justify-content: space-between; align-items: flex-start;
  margin-bottom: 8px;
}
.bpd-pnl-ttl {
  font-size: 11px; font-weight: 500; color: var(--t1, #1E2A4A);
}
.bpd-pnl-sub {
  font-size: 10px; color: var(--t3, var(--t-muted)); margin-top: 2px;
}
.bpd-pnl-tgl {
  padding: 5px 12px; font-size: 10.5px;
  background: var(--bg1, #fff); border: 1px solid rgba(15, 23, 60, .1);
  border-radius: 6px; color: var(--t3, #5F5E5A); cursor: pointer;
  font-family: inherit; transition: all .15s;
}
.bpd-pnl-tgl:hover { background: #F4F3F9; color: #7F77DD; }
.bpd-pnl-tbl-wrap {
  background: var(--bg1, #fff); border: 1px solid rgba(15, 23, 60, .06);
  border-radius: 10px; overflow: hidden;
}
.bpd-pnl-tbl { width: 100%; border-collapse: collapse; font-size: 11.5px; }
.bpd-pnl-tbl th {
  padding: 8px 12px; font-size: 9.5px; font-weight: 500; color: var(--t3, var(--t-muted));
  text-transform: uppercase; letter-spacing: .05em;
  border-bottom: 1px solid rgba(15, 23, 60, .06);
}
.bpd-pnl-tbl th.lbl { text-align: left; }
.bpd-pnl-tbl th.r { text-align: right; width: 90px; }
.bpd-pnl-tbl td { padding: 7px 12px; vertical-align: middle; }
.bpd-pnl-tbl td.lbl { color: var(--t1, #1E2A4A); }
.bpd-pnl-tbl td.r { text-align: right; font-variant-numeric: tabular-nums; color: var(--t1, #1E2A4A); }
.bpd-pnl-tbl tr { border-bottom: 0.5px solid rgba(15, 23, 60, .04); }
.bpd-pnl-tbl tr.tot td { font-weight: 500; background: rgba(127, 119, 221, .03); }
.bpd-auto-tag {
  display: inline-block; margin-right: 5px;
  padding: 1px 5px; background: rgba(239, 159, 39, .12); color: #A36500;
  border-radius: 3px; font-size: 8.5px; font-weight: 500;
  letter-spacing: .04em; text-transform: uppercase; vertical-align: 1px;
}
.bpd-pct {
  display: inline-block; padding: 1px 7px; border-radius: 3px;
  font-size: 10px; font-weight: 500;
}

/* ════════════ Variant 3: Sector Profile ════════════ */
.bpd-sector-grid {
  display: grid; grid-template-columns: 220px 1fr; gap: 18px;
  padding: 18px 26px;
}
.bpd-sector-left { display: flex; flex-direction: column; }
.bpd-donut-wrap {
  position: relative; display: flex;
  align-items: center; justify-content: center;
  margin-bottom: 14px;
}
.bpd-donut-center {
  position: absolute; text-align: center;
}
.bpd-donut-lbl {
  font-size: 10px; text-transform: uppercase; letter-spacing: .07em;
  color: var(--t3, var(--t-muted)); font-weight: 500;
}
.bpd-donut-val {
  font-size: 22px; font-weight: 400; color: var(--t1, #1E2A4A);
  letter-spacing: -.025em; line-height: 1; margin-top: 4px;
  font-variant-numeric: tabular-nums;
}
.bpd-donut-sub { font-size: 10px; color: var(--t3, var(--t-muted)); margin-top: 3px; }
.bpd-share-card {
  background: rgba(55, 138, 221, .06);
  border-radius: 10px; padding: 12px 14px;
}
.bpd-share-lbl {
  font-size: 9.5px; text-transform: uppercase; letter-spacing: .06em;
  color: #185FA5; font-weight: 500; margin-bottom: 6px;
}
.bpd-share-row {
  display: flex; align-items: baseline; gap: 8px;
}
.bpd-share-val {
  font-size: 22px; font-weight: 400; color: var(--t1, #1E2A4A);
  letter-spacing: -.025em; font-variant-numeric: tabular-nums;
}
.bpd-share-of { font-size: 10px; color: var(--t3, var(--t-muted)); }
.bpd-share-bar {
  margin-top: 6px; position: relative; height: 5px;
  background: var(--bg1, #fff); border-radius: 3px; overflow: hidden;
}
.bpd-share-bar-fill {
  position: absolute; left: 0; top: 0; height: 100%;
  background: var(--blue); border-radius: 3px;
  transition: width .8s var(--ease-standard);
}
.bpd-sector-right {}
.bpd-sector-rh {
  font-size: 10px; text-transform: uppercase; letter-spacing: .07em;
  color: var(--t3, var(--t-muted)); font-weight: 500; margin-bottom: 8px;
}
.bpd-sec-co {
  background: var(--bg1, #fff); border: 1px solid rgba(15, 23, 60, .06);
  border-radius: 8px; padding: 10px 12px; margin-bottom: 6px;
  display: flex; justify-content: space-between; align-items: flex-start; gap: 10px;
  animation: bpdRowIn .35s cubic-bezier(.22,.61,.36,1) var(--d, 0ms) both;
}
.bpd-sec-co:last-child { margin-bottom: 0; }
.bpd-sec-co-body { flex: 1; min-width: 0; }
.bpd-sec-co-name { font-size: 12px; color: var(--t1, #1E2A4A); font-weight: 500; }
.bpd-sec-co-bar {
  margin-top: 6px; position: relative; height: 5px;
  background: #F4F3F9; border-radius: 3px; overflow: hidden;
}
.bpd-sec-co-fill {
  position: absolute; left: 0; top: 0; height: 100%;
  border-radius: 3px;
  transition: width .8s var(--ease-standard);
}
.bpd-sec-co-vals { text-align: right; flex-shrink: 0; font-variant-numeric: tabular-nums; }
.bpd-sec-co-fact { font-size: 12px; color: var(--t1, #1E2A4A); font-weight: 500; }
.bpd-sec-co-pct { font-size: 9.5px; }

.bpd-bench-grid {
  display: grid; grid-template-columns: 1fr 1fr 1fr 1fr; gap: 8px;
  padding: 0 26px 18px;
}
.bpd-bench {
  padding: 11px 13px; background: #F4F3F9; border-radius: 8px;
}
.bpd-bench-lbl {
  font-size: 9px; text-transform: uppercase; letter-spacing: .06em;
  color: var(--t3, var(--t-muted)); font-weight: 500;
}
.bpd-bench-val {
  font-size: 18px; font-weight: 400; color: var(--t1, #1E2A4A);
  letter-spacing: -.02em; margin-top: 3px; font-variant-numeric: tabular-nums;
}
.bpd-bench-val-sm { font-size: 12px; font-weight: 500; margin-top: 4px; }
</style>
