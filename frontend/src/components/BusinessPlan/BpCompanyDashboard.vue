<script setup lang="ts">
/**
 * BpCompanyDashboard — Pack 8.2 rewrite, 1:1 port легасиного _bpRenderShell + _bpRepaint.
 *
 * Структура:
 *  1. Status bar (4 cells): Общий прогресс / На цели / Критичных / YoY
 *  2. 4 KPI hero cards: revenue / opProfit / profit / EBITDA
 *  3. Row 2 (1.2fr/1fr/1fr): Quarterly chart (SVG) + Attention + Achievements
 *  4. Comment block (manual exec summary, editable)
 *  5. Details ОФР (hierarchical P&L table с "Раскрыть все" toggle)
 *
 * Все вычисления (overall, ontrack, critical, achievements, ebitda) — клиентский расчёт
 * по правилам из легасиа (_bpRepaintStatBar, _bpAchievements).
 *
 * Данные:
 *  - props.computedData — current period (всегда передан; кварталы = YTD-хранение,
 *    отображение при q2..q4 — дельты «за квартал» через displayMetrics)
 *  - prevYearCur/prevYearPrevQ — YoY-база: тот же период прошлого года (дельта)
 *  - annualForFooter — fetched когда period != annual (для KPI footer "Итог года")
 *  - quarterlyData — fetched 4 раза для SVG chart (дельты; qYtdData — нараст. итог)
 *
 * Все save операции (комментарий) идут через bpApi → backend → PostgreSQL.
 */
import { computed, ref, watch } from "vue";
import Odometer from "@/components/Odometer.vue";
import UzaStateBlock from "@/components/UZA/UzaStateBlock.vue";
import BpQuarterDrillModal from "./BpQuarterDrillModal.vue";
import { useToast } from "@/composables/useToast";
import {
  BP_FIELDS,
  bpApi,
  bpFmt,
  bpPctColor,
  num,
  type BpAttentionIssue,
  type BpCell,
  type BpComment,
  type BpComputed,
  type BpPeriod,
} from "@/api/bpKpi";

const props = withDefaults(defineProps<{
  computedData: BpComputed;
  attention: BpAttentionIssue[];
  comment: BpComment | null;
  companyName: string;
  year: number;
  period: BpPeriod;
  canEdit: boolean;
  lens?: "all" | "income" | "expenses";
}>(), {
  lens: "all",
});

const emit = defineEmits<{
  (e: "comment-saved", c: BpComment): void;
}>();

// ─── Helpers ─────────────────────────────────────────────
// «ЗА КВАРТАЛ» (решение владельца): при period=q2..q4 карточки/статусы/таблица
// показывают ДЕЛЬТЫ ytd(period)−ytd(prev_q) — хранение и редактор остаются
// нарастающим итогом (НСБУ). q1/annual — значения как есть. Null-guard: без
// предыдущего YTD дельта не вычислима (полугодие не должно выглядеть «за Q2»).
const PREV_Q: Record<string, string | null> = { annual: null, q1: null, q2: "q1", q3: "q2", q4: "q3" };
const prevQComputed = ref<BpComputed | null>(null);

async function loadPrevQuarter() {
  const pq = PREV_Q[props.period] ?? null;
  if (!pq) { prevQComputed.value = null; return; }
  try {
    prevQComputed.value = await bpApi.getComputed(props.computedData.company_id, props.year, pq as BpPeriod);
  } catch {
    prevQComputed.value = null;
  }
}
watch(() => [props.computedData.company_id, props.year, props.period], () => loadPrevQuarter(), { immediate: true });

function deltaMetrics(cur: Record<string, BpCell>, prev: Record<string, BpCell> | undefined): Record<string, BpCell> {
  const out: Record<string, BpCell> = {};
  for (const k of Object.keys(cur)) {
    const c = cur[k] || { plan: null, expect: null, fact: null };
    const p = prev?.[k];
    const d = (a: string | number | null | undefined, b: string | number | null | undefined) =>
      (a != null && b != null) ? num(a) - num(b) : null;
    out[k] = { plan: d(c.plan, p?.plan), expect: d(c.expect, p?.expect), fact: d(c.fact, p?.fact), fact_auto: false };
  }
  return out;
}

function _metricsEmpty(m?: Record<string, BpCell>): boolean {
  if (!m) return true;
  return Object.values(m).every(c => c.plan == null && c.expect == null && c.fact == null);
}
/** Пред. квартал ПУСТ целиком (напр. УНГ: полугодие введено, Q1 нет) →
 *  дельты «за квартал» не вычислимы НИ по одной метрике. Прятать имеющийся
 *  YTD-факт за «—» хуже, чем показать его с честным ярлыком — фолбэк на
 *  нарастающий итог + баннер. */
const prevQMissing = computed(() => {
  const pq = PREV_Q[props.period] ?? null;
  if (!pq) return false;
  return _metricsEmpty(prevQComputed.value?.metrics);
});

/** Метрики для ОТОБРАЖЕНИЯ: q2..q4 → дельты «за квартал»; ПО-СТРОЧНЫЙ фолбэк:
 *  если факт-дельта метрики не вычислима (в пред. квартале нет факта, как у
 *  УНГ: Q1-план есть, Q1-факта нет), а YTD-факт существует — строка ЦЕЛИКОМ
 *  (план/ожид/факт) показывается нарастающим итогом с меткой «нараст.».
 *  Пары не смешиваем: % такой строки = YTD-факт / YTD-план. */
const displayComputed = computed<{ metrics: Record<string, BpCell>; ytdKeys: Set<string> }>(() => {
  const cur = props.computedData.metrics;
  const pq = PREV_Q[props.period] ?? null;
  if (!pq) return { metrics: cur, ytdKeys: new Set() };
  if (prevQMissing.value) return { metrics: cur, ytdKeys: new Set(Object.keys(cur)) };
  const prev = prevQComputed.value?.metrics;
  const out: Record<string, BpCell> = {};
  const ytd = new Set<string>();
  const d = (a: string | number | null | undefined, b: string | number | null | undefined) =>
    (a != null && b != null) ? num(a) - num(b) : null;
  for (const k of Object.keys(cur)) {
    const c = cur[k] || { plan: null, expect: null, fact: null };
    const p = prev?.[k];
    const df = d(c.fact, p?.fact);
    if (df == null && c.fact != null) {
      out[k] = { plan: c.plan, expect: c.expect, fact: c.fact, fact_auto: false };
      ytd.add(k);
    } else {
      out[k] = { plan: d(c.plan, p?.plan), expect: d(c.expect, p?.expect), fact: df, fact_auto: false };
    }
  }
  return { metrics: out, ytdKeys: ytd };
});
const displayMetrics = computed<Record<string, BpCell>>(() => displayComputed.value.metrics);
const ytdKeys = computed(() => displayComputed.value.ytdKeys);

function cell(key: string): BpCell {
  return displayMetrics.value[key] || { plan: null, expect: null, fact: null };
}

function fmtV(v: string | number | null | undefined): string {
  if (v == null) return "—";
  return bpFmt(v);
}

function pctOf(c: BpCell): number | null {
  if (c.plan == null || num(c.plan) === 0 || c.fact == null) return null;
  return num(c.fact) / num(c.plan);
}

// ─── Status bar — 4 cells ───────────────────────────────
interface StatCell {
  id: string;
  severity: "ok" | "warn" | "bad" | "neutral";
  label: string;
  value: string;
  sub: string;
}

// YoY-база: ТОТ ЖЕ период прошлого года (для кварталов — дельта того же
// квартала; раньше квартал сравнивался с ГОДОВЫМ фактом прошлого года).
const prevYearCur = ref<BpComputed | null>(null);
const prevYearPrevQ = ref<BpComputed | null>(null);
const annualForFooter = ref<BpComputed | null>(null);

async function loadPrevYearAnnual() {
  try {
    prevYearCur.value = await bpApi.getComputed(
      props.computedData.company_id,
      props.year - 1,
      props.period,
    );
  } catch {
    prevYearCur.value = null;
  }
  const pq = PREV_Q[props.period] ?? null;
  if (!pq) { prevYearPrevQ.value = null; return; }
  try {
    prevYearPrevQ.value = await bpApi.getComputed(
      props.computedData.company_id, props.year - 1, pq as BpPeriod,
    );
  } catch {
    prevYearPrevQ.value = null;
  }
}

/** YoY-метрики прошлого года В ТЕХ ЖЕ единицах, что displayMetrics:
 *  строки-«нараст.» сравниваются с YTD прошлого года, дельта-строки — с
 *  дельтой того же квартала прошлого года. */
const prevDisplayMetrics = computed<Record<string, BpCell>>(() => {
  const cur = prevYearCur.value?.metrics;
  if (!cur) return {};
  const pq = PREV_Q[props.period] ?? null;
  if (!pq) return cur;
  if (prevQMissing.value) return cur;
  const deltas = deltaMetrics(cur, prevYearPrevQ.value?.metrics);
  const out: Record<string, BpCell> = {};
  for (const k of Object.keys(cur)) out[k] = ytdKeys.value.has(k) ? cur[k] : deltas[k];
  return out;
});

async function loadAnnualForFooter() {
  // Если просматриваемый period не annual, загружаем annual для KPI footer ("Итог года")
  if (props.period === "annual") {
    annualForFooter.value = null;
    return;
  }
  try {
    annualForFooter.value = await bpApi.getComputed(
      props.computedData.company_id,
      props.year,
      "annual",
    );
  } catch {
    annualForFooter.value = null;
  }
}

watch(
  () => [props.computedData.company_id, props.year, props.period],
  () => loadPrevYearAnnual(),
  { immediate: true },
);
watch(
  () => [props.computedData.company_id, props.year, props.period],
  () => loadAnnualForFooter(),
  { immediate: true },
);

const statBand = computed<StatCell[]>(() => {
  const m = displayMetrics.value;

  // 1. Общий прогресс — среднее % по revenue/opProfit/profit, capped at 1.5
  let sumPct = 0, cntPct = 0;
  for (const k of ["revenue", "opProfit", "profit"]) {
    const c = m[k];
    if (c && c.plan != null && num(c.plan) !== 0 && c.fact != null) {
      sumPct += Math.min(num(c.fact) / num(c.plan), 1.5);
      cntPct++;
    }
  }
  const overall = cntPct > 0 ? sumPct / cntPct : null;
  const overallSev = overall == null ? "neutral" : overall >= 0.95 ? "ok" : overall >= 0.80 ? "warn" : "bad";
  const overallVal = overall == null ? "—" : Math.round(overall * 100) + "%";
  const overallSub = overall == null ? "нет данных" : `взвешенно · ${cntPct} метрик`;

  // 2. На цели (≥95%) + 3. Критичных (<70%)
  let ontrack = 0, total = 0, critical = 0;
  for (const f of BP_FIELDS) {
    if (f.sub) continue;
    const c = m[f.key];
    if (!c || c.plan == null || num(c.plan) === 0 || c.fact == null) continue;
    total++;
    const r = num(c.fact) / num(c.plan);
    if (r >= 0.95) ontrack++;
    if (r < 0.70) critical++;
  }
  const ontrackSev = total === 0 ? "neutral" : (ontrack / total >= 0.7 ? "ok" : ontrack / total >= 0.4 ? "warn" : "bad");
  const ontrackVal = total === 0 ? "—" : `${ontrack} / ${total}`;
  const ontrackSub = total === 0 ? "нет фактов" : "показателей";

  const critSev = critical === 0 ? "ok" : critical <= 2 ? "warn" : "bad";
  const critSub = critical === 0 ? "всё в норме" : "требуют решения";

  // 4. YoY (revenue) — тот же период прошлого года (для кварталов — та же дельта).
  let yoyVal = "—", yoySev: StatCell["severity"] = "neutral", yoySub = `нет данных за ${props.year - 1}`;
  const curRev = m["revenue"]?.fact;
  const prevRev = prevDisplayMetrics.value["revenue"]?.fact;
  if (curRev != null && prevRev != null && num(prevRev) !== 0) {
    const d = (num(curRev) - num(prevRev)) / Math.abs(num(prevRev));
    yoyVal = (d >= 0 ? "▲ +" : "▼ ") + Math.round(Math.abs(d) * 100) + "%";
    yoySev = d >= 0.10 ? "ok" : d >= 0 ? "neutral" : d >= -0.10 ? "warn" : "bad";
    yoySub = `по выручке к ${props.year - 1}`;
  }

  return [
    { id: "overall", severity: overallSev as StatCell["severity"], label: "Общий прогресс", value: overallVal, sub: overallSub },
    { id: "ontrack", severity: ontrackSev as StatCell["severity"], label: "На цели (≥95%)", value: ontrackVal, sub: ontrackSub },
    { id: "crit",    severity: critSev as StatCell["severity"],    label: "Критичных (<70%)", value: String(critical), sub: critSub },
    { id: "yoy",     severity: yoySev,                              label: "Год к году", value: yoyVal, sub: yoySub },
  ];
});

// ─── 4 KPI hero cards ───────────────────────────────────
interface KpiCard {
  key: string;
  label: string;
  accent: string;
  delay: number;
  fact: number | null;
  plan: number | null;
  factAuto: boolean;
  ytd: boolean;                 // строка показана нарастающим итогом (фолбэк)
  pctOfPlan: number | null;
  yoyPct: number | null;
  footerFactAnnual: number | null;
  footerPlanAnnual: number | null;
}

const kpiCards = computed<KpiCard[]>(() => {
  const m = displayMetrics.value;
  const annualSrc = props.period === "annual" ? m : (annualForFooter.value?.metrics || {});
  const prev = prevDisplayMetrics.value;

  const build = (key: string, label: string, accent: string, delay: number): KpiCard => {
    const c = m[key] || { plan: null, expect: null, fact: null };
    const annualC = annualSrc[key] || { plan: null, expect: null, fact: null };
    const fact = c.fact != null ? num(c.fact) : null;
    const plan = c.plan != null ? num(c.plan) : null;
    const prevFact = prev[key]?.fact != null ? num(prev[key]!.fact!) : null;
    const yoyPct = (fact != null && prevFact != null && prevFact !== 0)
      ? (fact - prevFact) / Math.abs(prevFact)
      : null;
    return {
      key, label, accent, delay,
      fact, plan,
      factAuto: !!c.fact_auto,
      ytd: ytdKeys.value.has(key),
      pctOfPlan: (fact != null && plan != null && plan !== 0) ? fact / plan : null,
      yoyPct,
      footerFactAnnual: annualC.fact != null ? num(annualC.fact) : null,
      footerPlanAnnual: annualC.plan != null ? num(annualC.plan) : null,
    };
  };

  // Lens-aware card set. "all" — historical revenue/opProfit/profit/EBITDA;
  // "income" — top income drivers; "expenses" — main spending buckets.
  if (props.lens === "expenses") {
    return [
      build("cogs",        "Себестоимость",     "#E8B575", 120),
      build("opExpenses",  "Расходы периода",   "#E89B9A", 180),
      build("finCost",     "Финансовые расходы", "#E24B4A", 240),
      build("tax",         "Налог на прибыль",  "#C36868", 300),
    ];
  }
  if (props.lens === "income") {
    return [
      build("revenue",    "Выручка",                "#7F77DD", 120),
      build("finIncome",  "Финансовые доходы",      "#7DC4A0", 180),
      build("otherOpInc", "Прочие опер. доходы",    "#A39EE6", 240),
      build("opProfit",   "Операционная прибыль",   "#1D9E75", 300),
    ];
  }

  // EBITDA — placeholder using opProfit (proper requires depreciation API endpoint)
  // TODO: add /bp/depreciation/{co}/{year} backend endpoint, then compute opProfit + |D&A|
  const ebitdaCard = build("opProfit", "EBITDA (≈ opProfit)", "#EF9F27", 300);
  ebitdaCard.key = "_ebitda";

  return [
    build("revenue",  "Выручка",             "#7F77DD", 120),
    build("opProfit", "Операционная прибыль", "#1D9E75", 180),
    build("profit",   "Чистая прибыль",       "#378ADD", 240),
    ebitdaCard,
  ];
});

// ─── Achievements (top 5 metrics with ratio ≥ 1.0, not positive-type) ──
interface Achievement {
  title: string;
  ratio: number;
  fact: number;
  plan: number;
}

const achievements = computed<Achievement[]>(() => {
  const m = displayMetrics.value;
  const res: Achievement[] = [];
  for (const f of BP_FIELDS) {
    if (f.sub) continue;
    if (f.positive) continue; // exclude "less is better" fields
    const c = m[f.key];
    if (!c || c.plan == null || num(c.plan) === 0 || c.fact == null) continue;
    const r = num(c.fact) / num(c.plan);
    if (r >= 1.0) {
      res.push({ title: f.label, ratio: r, fact: num(c.fact), plan: num(c.plan) });
    }
  }
  return res.sort((a, b) => b.ratio - a.ratio).slice(0, 5);
});

// ─── Quarterly chart data (lens-aware headline metric) ───
interface QData { q: string; plan: number | null; expect: number | null; fact: number | null; }
const quarterlyData = ref<QData[] | null>(null);   // дельты «за квартал» (бары)
const qYtdData = ref<QData[] | null>(null);        // нарастающий итог (тултип/дрилл)

// Headline metric for the quarterly chart, matches the lens choice.
// expenses → opExpenses (главный расходный бакет). all/income → revenue.
const chartMetric = computed(() =>
  props.lens === "expenses" ? "opExpenses" : "revenue",
);
const chartLabel = computed(() =>
  props.lens === "expenses" ? "Расходы периода" : "Выручка",
);

async function loadQuarterly() {
  try {
    const metric = chartMetric.value;
    const ytd: QData[] = [];
    for (const q of ["q1", "q2", "q3", "q4"] as const) {
      const r = await bpApi.getComputed(props.computedData.company_id, props.year, q);
      const c = r.metrics[metric] || { plan: null, expect: null, fact: null };
      ytd.push({
        q,
        plan: c.plan != null ? num(c.plan) : null,
        expect: c.expect != null ? num(c.expect) : null,
        fact: c.fact != null ? num(c.fact) : null,
      });
    }
    // КАНОН: хранимые кварталы — НАРАСТАЮЩИМ ИТОГОМ (НСБУ). «Квартальный тренд»
    // показывает величины ЗА квартал → конвертируем в дельты (честный null,
    // когда предыдущий квартал не заполнен); YTD-ряд оставляем для тултипа/дрилла.
    const dp = ytdToDeltas(ytd.map(d => d.plan));
    const de = ytdToDeltas(ytd.map(d => d.expect));
    const df = ytdToDeltas(ytd.map(d => d.fact));
    qYtdData.value = ytd;
    quarterlyData.value = ytd.map((d, i) => ({ q: d.q, plan: dp[i], expect: de[i], fact: df[i] }));
  } catch {
    quarterlyData.value = null;
    qYtdData.value = null;
  }
  // Прогноз оставшихся кварталов (ghost-бары) — прогрессив-энханс.
  try {
    coOutlook.value = await bpApi.getQuarterOutlook(
      props.year, chartMetric.value, props.computedData.company_id,
    );
  } catch {
    coOutlook.value = null;
  }
}

// ─── Прогноз кварталов компании (движок forecast_quarters на дельтах) ───
const coOutlook = ref<BpQuarterOutlook | null>(null);
const coProj = computed<Map<number, { value: number; low: number | null; high: number | null }>>(() => {
  const m = new Map();
  for (const p of coOutlook.value?.projections || []) {
    const i = Number(p.period?.[1]) - 1;
    if (Number.isFinite(i) && i >= 0 && i < 4 && p.value != null) m.set(i, { value: p.value, low: p.low, high: p.high });
  }
  return m;
});
const _FC_METHOD_RU: Record<string, string> = {
  pace: "план × темп", seasonal: "сезонность прошлого года", run_rate: "run-rate",
  plan: "по плану", actual: "год закрыт", mixed: "смешанный", none: "нет данных",
};
const _FC_CONF_RU: Record<string, string> = { high: "высокая", medium: "средняя", low: "низкая", none: "—" };
const coForecastMeta = computed(() => {
  const f = coOutlook.value;
  if (!f || !coProj.value.size) return null;
  return `${_FC_METHOD_RU[f.method] || f.method} · увер.: ${_FC_CONF_RU[f.confidence] || f.confidence}`;
});

// ─── Интерактив «Квартального тренда»: hover-тултип + клик → разбор квартала ──
const hoveredQ = ref<number | null>(null);
const qDrill = ref<null | {
  q: string; plan: number | null; fact: number | null; expect?: number | null;
  planDelta: number | null; factDelta: number | null;
  cum: number | null; label: string; unit: string;
}>(null);

function qTip(i: number) {
  const d = quarterlyData.value?.[i];
  const y = qYtdData.value?.[i];
  const pct = (y?.plan != null && y.plan !== 0 && y.fact != null)
    ? Math.round((y.fact / y.plan) * 100) : null;
  return { d, y, pct, gap: d?.fact == null && y?.fact != null };
}
function openQuarterDrill(i: number) {
  const y = qYtdData.value?.[i];
  const d = quarterlyData.value?.[i];
  if (!y || !d) return;
  qDrill.value = {
    q: y.q, plan: y.plan, fact: y.fact, expect: y.expect,
    planDelta: d.plan, factDelta: d.fact,
    cum: y.fact ?? y.expect ?? y.plan,
    label: chartLabel.value, unit: "млрд сум",
  };
}
watch(
  () => [props.computedData.company_id, props.year, props.lens],
  () => loadQuarterly(),
  { immediate: true },
);

const chartMax = computed(() => {
  if (!quarterlyData.value) return 1;
  const all = quarterlyData.value.flatMap(d => [d.plan, d.expect, d.fact]).filter((v): v is number => v != null);
  for (const p of coProj.value.values()) {
    all.push(p.value);
    if (p.high != null) all.push(p.high);
  }
  if (!all.length) return 1;
  const max = Math.max(0, ...all);
  return max === 0 ? 1 : max;
});
// Нижняя граница шкалы: отрицательная дельта (коррекция/убыточный квартал)
// рисуется вниз от нулевой базы, а не исчезает.
const chartMin = computed(() => {
  if (!quarterlyData.value) return 0;
  const all = quarterlyData.value.flatMap(d => [d.plan, d.expect, d.fact]).filter((v): v is number => v != null);
  for (const p of coProj.value.values()) {
    all.push(p.value);
    if (p.low != null) all.push(p.low);
  }
  return Math.min(0, ...all);
});
const chartRange = computed(() => (chartMax.value - chartMin.value) || 1);

const hasQuarterly = computed(() => {
  if (!quarterlyData.value) return false;
  // Treat all-zero/all-null as «нет данных» — иначе рисуется пустой график
  // с осью 0–1 без баров (вводит в заблуждение).
  return quarterlyData.value.some(d =>
    (d.plan != null && d.plan !== 0) ||
    (d.fact != null && d.fact !== 0) ||
    (d.expect != null && d.expect !== 0),
  );
});

// SVG chart geometry
const CHART_W = 520, CHART_H = 160, PAD_L = 34, PAD_R = 8, PAD_T = 12, PAD_B = 24;
const innerH = CHART_H - PAD_T - PAD_B;
const gw = (CHART_W - PAD_L - PAD_R) / 4;
const barW = 10;

function chartY(v: number) { return PAD_T + innerH * (1 - (v - chartMin.value) / chartRange.value); }
const chartBaseY = computed(() => chartY(0));

// computed (НЕ const!): const вычислялся один раз при setup (chartMax ещё 1) —
// ось навсегда застывала на 0.00–1.00, даже когда данные загрузились.
const gridLines = computed(() => [0, 0.25, 0.5, 0.75, 1].map(p => ({
  y: PAD_T + innerH * (1 - p),
  label: bpFmt(chartMin.value + chartRange.value * p),
})));

// ВАЖНО: у SVG <rect> атрибуты width/height — {w, h} через v-bind молча давал
// нулевые размеры (бары никогда не рисовались, «пустой» график).
function barGeometry(value: number | null, idx: number, offset: number) {
  if (value == null) return null;
  const cx = PAD_L + gw * (idx + 0.5);
  const y = chartY(value);
  return {
    x: cx + offset * barW,
    y: Math.min(y, chartBaseY.value),
    width: barW,
    height: value === 0 ? 0 : Math.max(1, Math.abs(y - chartBaseY.value)),
  };
}

// ─── Details — hierarchical toggle + view-mode (all/income/expenses) ───
// viewMode initialises from parent `lens` prop and stays in sync — top-level
// toggle on BusinessPlan.vue drives both summary & company dashboards.
import { bpFieldsFor, ytdToDeltas, type BpQuarterOutlook, type BpViewMode } from "@/api/bpKpi";
const detailsExpanded = ref(false);
const viewMode = ref<BpViewMode>(props.lens);
watch(() => props.lens, (l) => { viewMode.value = l; });
const detailsFields = computed(() => {
  const base = bpFieldsFor(viewMode.value);
  return detailsExpanded.value ? base : base.filter(f => !f.sub);
});

// ─── Period label ──────────────────────────────────────
const periodLabel = computed(() => {
  // Значения экрана при квартале — ДЕЛЬТЫ «за квартал» (displayMetrics);
  // при пустом пред. квартале — YTD-фолбэк с соответствующим ярлыком.
  if (props.period === "annual") return "годовой итог";
  return prevQMissing.value
    ? `нарастающим итогом за ${props.period.toUpperCase()}`
    : `за квартал ${props.period.toUpperCase()}`;
});

const factAutoCount = computed(() => {
  if (props.period !== "annual") return 0;
  return Object.values(props.computedData.metrics).filter(c => c.fact_auto).length;
});

// ─── Comment block ─────────────────────────────────────
const editingComment = ref(false);
const commentDraft = ref(props.comment?.body ?? "");
const savingComment = ref(false);

watch(() => props.comment, (v) => {
  commentDraft.value = v?.body ?? "";
  editingComment.value = false;
});

async function saveComment() {
  if (savingComment.value) return;
  savingComment.value = true;
  try {
    const saved = await bpApi.upsertComment(
      props.computedData.company_id,
      props.year,
      props.period,
      commentDraft.value.trim(),
    );
    emit("comment-saved", saved);
    editingComment.value = false;
    useToast().success("Комментарий сохранён");
  } catch (e) {
    console.error("[BP] comment save failed:", e);
    useToast().error("Не удалось сохранить");
  } finally {
    savingComment.value = false;
  }
}

// ─── Attention dot color ───────────────────────────────
const attentionDotColor = computed(() => {
  if (!props.attention.length) return "#1D9E75";
  return props.attention[0].severity === "high" ? "#A32D2D" : "#BA7517";
});

// ─── Helpers for arrows in KPI ─────────────────────────
function arrowFor(pct: number): "up" | "down" | "dot" {
  if (pct >= 1) return "up";
  if (pct >= 0.9) return "dot";
  return "down";
}
</script>

<template>
  <div class="bpv-scroll">
    <div class="bpv-body">

      <!-- Header context line (eyebrow) -->
      <div class="bpv-context">
        <span class="bpv-ctx-co">{{ companyName }}</span>
        <span class="bpv-ctx-sep">·</span>
        <span class="bpv-ctx-period">FY {{ year }} · {{ periodLabel }} · млрд сум</span>
        <span v-if="factAutoCount > 0" class="bpv-ctx-auto">
          <svg width="10" height="10" viewBox="0 0 10 10" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M1.5 5l2.5 2.5L8.5 2.5"/></svg>
          авто из НСБУ: {{ factAutoCount }}
        </span>
      </div>

      <!-- YTD-фолбэк: пред. квартал пуст → показываем нарастающий итог, не «—» -->
      <div v-if="prevQMissing" class="bpv-ytd-note">
        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="9"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg>
        {{ (PREV_Q[period] || '').toUpperCase() }} не заполнен — показатели показаны
        <b>нарастающим итогом с начала года</b>; разбивка «за квартал» появится после
        заполнения предыдущего квартала в редакторе.
      </div>
      <!-- Частичный фолбэк: в пред. квартале нет ФАКТА по части строк -->
      <div v-else-if="ytdKeys.size" class="bpv-ytd-note">
        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="9"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg>
        Строки с меткой <span class="bpv-ytd-chip">нараст.</span> показаны
        <b>нарастающим итогом</b>: в {{ (PREV_Q[period] || '').toUpperCase() }} не заполнен факт —
        «за квартал» не вычислить. Внесите факт {{ (PREV_Q[period] || '').toUpperCase() }} в редакторе,
        и строки переключатся на «за квартал».
      </div>

      <!-- ═══ 1. Status bar (4 cells) ═══ -->
      <div class="bpv-stat-bar kpi-rail">
        <div
          v-for="(s, i) in statBand"
          :key="s.id"
          class="bpv-stat-cell"
          :class="s.severity"
          :style="{ '--d': (i * 50 + 40) + 'ms' }"
        >
          <div class="bpv-stat-lbl">{{ s.label }}</div>
          <div class="bpv-stat-val"><Odometer :value="s.value" /></div>
          <div class="bpv-stat-sub">{{ s.sub }}</div>
        </div>
      </div>

      <!-- ═══ 2. KPI hero cards (4) ═══ -->
      <div class="bpv-grid kpi-rail">
        <div
          v-for="k in kpiCards"
          :key="k.key"
          class="kpi2 fin-shimmer bpv-kpi-cell"
          :style="{ '--kpi2-accent': k.accent, '--kpi2-d': k.delay + 'ms', '--d': k.delay + 'ms' }"
        >
          <span v-if="k.factAuto" class="bpv-kpi-auto" title="Факт подставлен автоматически из НСБУ">
            <svg width="8" height="8" viewBox="0 0 10 10" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M1.5 5l2.5 2.5L8.5 2.5"/></svg>
            НСБУ
          </span>
          <div class="kpi2-lbl bpv-kpi-l">{{ k.label }}</div>
          <div class="kpi2-val bpv-kpi-v" :class="{ 'is-empty': k.fact == null }">
            <Odometer :value="k.fact != null ? bpFmt(k.fact) : '—'" />
          </div>
          <div class="kpi2-sub bpv-kpi-u">млрд сум · факт<template v-if="k.ytd"> · <span class="bpv-ytd-chip" title="Показано нарастающим итогом с начала года: в предыдущем квартале нет факта — «за квартал» не вычислить">нараст.</span></template></div>
          <div class="bpv-kpi-foot">
            <span class="bpv-kpi-plan" :style="k.pctOfPlan != null ? { color: bpPctColor(k.pctOfPlan) } : { color: 'var(--t3,#888780)' }">
              <template v-if="k.pctOfPlan != null">
                <svg v-if="arrowFor(k.pctOfPlan) === 'up'" width="9" height="9" viewBox="0 0 10 10" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="vertical-align:-1px;margin-right:3px"><path d="M5 2v6M2.5 4.5L5 2l2.5 2.5"/></svg>
                <svg v-else-if="arrowFor(k.pctOfPlan) === 'down'" width="9" height="9" viewBox="0 0 10 10" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="vertical-align:-1px;margin-right:3px"><path d="M5 2v6M2.5 5.5L5 8l2.5-2.5"/></svg>
                <svg v-else width="9" height="9" viewBox="0 0 10 10" fill="none" style="vertical-align:-1px;margin-right:3px"><circle cx="5" cy="5" r="2.5" fill="currentColor"/></svg>
                {{ Math.round(k.pctOfPlan * 100) }}% плана
              </template>
              <template v-else>—</template>
            </span>
            <span class="bpv-kpi-yoy" :style="k.yoyPct != null ? { color: k.yoyPct >= 0 ? '#0F6E56' : '#933632' } : { color: 'var(--t3,#888780)' }">
              <template v-if="k.yoyPct != null">
                <svg v-if="k.yoyPct >= 0" width="9" height="9" viewBox="0 0 10 10" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="vertical-align:-1px;margin-right:3px"><path d="M5 2v6M2.5 4.5L5 2l2.5 2.5"/></svg>
                <svg v-else width="9" height="9" viewBox="0 0 10 10" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="vertical-align:-1px;margin-right:3px"><path d="M5 2v6M2.5 5.5L5 8l2.5-2.5"/></svg>
                {{ Math.round(Math.abs(k.yoyPct) * 100) }}% г/г
              </template>
              <template v-else>— г/г</template>
            </span>
          </div>
          <div class="bpv-kpi-fc">
            <template v-if="k.footerFactAnnual != null && k.footerPlanAnnual != null">
              Итог года: <b>{{ bpFmt(k.footerFactAnnual) }}</b> · план {{ bpFmt(k.footerPlanAnnual) }}
            </template>
            <template v-else-if="k.footerPlanAnnual != null">
              План года: <b>{{ bpFmt(k.footerPlanAnnual) }}</b>
            </template>
            <template v-else>—</template>
          </div>
        </div>
      </div>

      <!-- ═══ 3. Row 2: Chart + Attention + Achievements ═══ -->
      <div class="bpv-row2">

        <!-- Quarterly chart -->
        <div class="bpv-card" style="--d:360ms">
          <div class="bpv-card-ttl">Квартальный тренд · {{ chartLabel.toLowerCase() }}</div>
          <div class="bpv-chart-wrap">
            <div v-if="!hasQuarterly" class="bpv-chart-empty">Нет квартальных данных за {{ year }} · {{ chartLabel.toLowerCase() }}<br><span class="bpv-chart-empty-sub">показатель разнесён только по году или не заведён</span></div>
            <svg v-else :viewBox="`0 0 ${CHART_W} ${CHART_H}`" preserveAspectRatio="xMidYMid meet" style="width:100%;height:100%">
              <!-- Белый «глянец» сверху баров — единый стиль с барами портфеля -->
              <defs>
                <linearGradient id="bpvBarSheen" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0" stop-color="#fff" stop-opacity="0.30" />
                  <stop offset="0.55" stop-color="#fff" stop-opacity="0" />
                </linearGradient>
              </defs>
              <!-- Grid -->
              <g class="bpv-grid-g">
                <template v-for="(g, gi) in gridLines" :key="gi">
                  <line :x1="PAD_L" :y1="g.y" :x2="CHART_W - PAD_R" :y2="g.y" stroke="#E2E8F0" stroke-width="0.5" stroke-dasharray="2 3"/>
                  <text :x="PAD_L - 6" :y="g.y + 3" font-size="9" fill="#94A3B8" text-anchor="end">{{ g.label }}</text>
                </template>
                <!-- нулевая база (заметна при отрицательных дельтах) -->
                <line v-if="chartMin < 0" :x1="PAD_L" :y1="chartBaseY" :x2="CHART_W - PAD_R" :y2="chartBaseY" stroke="#B9B6C9" stroke-width="1" stroke-dasharray="3 3"/>
              </g>
              <!-- Bars (кликабельные группы: hover-тултип + дрилл квартала) -->
              <g v-for="(d, idx) in quarterlyData" :key="d.q"
                 class="bpvq-grp" :class="{ on: hoveredQ === idx }"
                 @mouseenter="hoveredQ = idx" @mouseleave="hoveredQ = null"
                 @click="openQuarterDrill(idx)">
                <!-- hover-подсветка слота -->
                <rect :x="PAD_L + gw * idx" :y="PAD_T" :width="gw" :height="innerH" class="bpvq-slot" rx="6"/>
                <!-- Plan (offset -1.5) -->
                <rect v-if="barGeometry(d.plan, idx, -1.5)" v-bind="barGeometry(d.plan, idx, -1.5)!" fill="#CECBF6" rx="2"/>
                <rect v-if="barGeometry(d.plan, idx, -1.5)" v-bind="barGeometry(d.plan, idx, -1.5)!" fill="url(#bpvBarSheen)" rx="2" pointer-events="none"/>
                <!-- Expect (offset -0.5) -->
                <rect v-if="barGeometry(d.expect, idx, -0.5)" v-bind="barGeometry(d.expect, idx, -0.5)!" fill="#FAC775" rx="2"/>
                <rect v-if="barGeometry(d.expect, idx, -0.5)" v-bind="barGeometry(d.expect, idx, -0.5)!" fill="url(#bpvBarSheen)" rx="2" pointer-events="none"/>
                <!-- Fact (offset +0.5) -->
                <rect v-if="barGeometry(d.fact, idx, 0.5)" v-bind="barGeometry(d.fact, idx, 0.5)!" fill="#5DC093" rx="2"/>
                <rect v-if="barGeometry(d.fact, idx, 0.5)" v-bind="barGeometry(d.fact, idx, 0.5)!" fill="url(#bpvBarSheen)" rx="2" pointer-events="none"/>
                <!-- ПРОГНОЗ: ghost-бар на месте факта + коридор low..high -->
                <template v-if="d.fact == null && coProj.get(idx)">
                  <rect v-bind="barGeometry(coProj.get(idx)!.value, idx, 0.5)!" class="bpvq-ghost" rx="2"/>
                  <line v-if="coProj.get(idx)!.low != null && coProj.get(idx)!.high != null"
                        class="bpvq-whisker"
                        :x1="PAD_L + gw * (idx + 0.5) + 0.5 * barW + barW / 2"
                        :x2="PAD_L + gw * (idx + 0.5) + 0.5 * barW + barW / 2"
                        :y1="chartY(coProj.get(idx)!.high!)" :y2="chartY(coProj.get(idx)!.low!)"/>
                </template>
                <!-- Quarter label -->
                <text :x="PAD_L + gw * (idx + 0.5)" :y="CHART_H - 8" font-size="10" fill="#64748B" text-anchor="middle" font-weight="500">{{ d.q.toUpperCase() }}</text>
              </g>
            </svg>

            <!-- Hover-тултип: за квартал / нараст. итогом / % с начала года -->
            <div v-if="hoveredQ != null && quarterlyData" class="bpvq-tip"
                 :style="{ left: ((PAD_L + gw * (hoveredQ + 0.5)) / CHART_W * 100) + '%' }">
              <div class="bpvq-tip-h">{{ quarterlyData[hoveredQ].q.toUpperCase() }} · {{ chartLabel.toLowerCase() }}</div>
              <div class="bpvq-tip-r"><span>За квартал · план</span><b>{{ qTip(hoveredQ).d?.plan != null ? bpFmt(qTip(hoveredQ).d!.plan!) : '—' }}</b></div>
              <div class="bpvq-tip-r"><span>За квартал · факт</span><b>{{ qTip(hoveredQ).d?.fact != null ? bpFmt(qTip(hoveredQ).d!.fact!) : '—' }}</b></div>
              <div v-if="qTip(hoveredQ).gap" class="bpvq-tip-note">за квартал не вычислимо: нет данных предыдущего квартала</div>
              <template v-if="quarterlyData[hoveredQ].fact == null && coProj.get(hoveredQ)">
                <div class="bpvq-tip-r"><span>Прогноз (за кв.)</span><b class="bpvq-tip-fc">≈{{ bpFmt(coProj.get(hoveredQ)!.value) }}</b></div>
                <div v-if="coProj.get(hoveredQ)!.low != null && coProj.get(hoveredQ)!.high != null" class="bpvq-tip-r">
                  <span>Коридор</span><b>{{ bpFmt(coProj.get(hoveredQ)!.low!) }} – {{ bpFmt(coProj.get(hoveredQ)!.high!) }}</b>
                </div>
                <div v-if="coForecastMeta" class="bpvq-tip-note bpvq-tip-note-fc">{{ coForecastMeta }}</div>
              </template>
              <div class="bpvq-tip-r"><span>Нараст. план</span><b>{{ qTip(hoveredQ).y?.plan != null ? bpFmt(qTip(hoveredQ).y!.plan!) : '—' }}</b></div>
              <div class="bpvq-tip-r"><span>Нараст. факт</span><b>{{ qTip(hoveredQ).y?.fact != null ? bpFmt(qTip(hoveredQ).y!.fact!) : '—' }}</b></div>
              <div v-if="qTip(hoveredQ).pct != null" class="bpvq-tip-r"><span>Исполнение с начала года</span><b>{{ qTip(hoveredQ).pct }}%</b></div>
              <div class="bpvq-tip-cta">Открыть разбор →</div>
            </div>
          </div>
          <div class="bpv-chart-lgd">
            <span><span class="dot" style="background:#7F77DD"></span>План</span>
            <span><span class="dot" style="background:#EF9F27"></span>Ожидание</span>
            <span><span class="dot" style="background:#5DC093"></span>Факт</span>
            <span v-if="coProj.size" :title="coForecastMeta || ''"><span class="dot bpvq-dot-ghost"></span>Прогноз</span>
          </div>
          <BpQuarterDrillModal v-if="qDrill" v-bind="qDrill" :fmt="bpFmt" @close="qDrill = null" />
        </div>

        <!-- Attention -->
        <div class="bpv-card" style="--d:420ms">
          <div class="bpv-card-ttl">
            <span><span class="bpv-att-dot" :style="{ background: attentionDotColor }"></span>Требуют решения</span>
          </div>
          <UzaStateBlock v-if="!attention.length" state="empty" variant="block" text="Критических отклонений нет">
            <template #icon>
              <svg width="22" height="22" viewBox="0 0 14 14" fill="none" stroke="#1D9E75" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M3 7l3 3 5-6"/></svg>
            </template>
          </UzaStateBlock>
          <div v-else>
            <div
              v-for="(iss, i) in attention"
              :key="i"
              class="bpv-att-row"
              :class="iss.severity === 'high' ? 'high' : 'medium'"
              :style="{ '--d': (i * 40) + 'ms' }"
            >
              <div>
                <div class="bpv-att-ttl">{{ iss.title }}</div>
                <div class="bpv-att-d">{{ iss.detail || '' }}</div>
              </div>
              <div class="bpv-att-val">{{ iss.value }}</div>
            </div>
          </div>
        </div>

        <!-- Achievements -->
        <div class="bpv-card" style="--d:480ms">
          <div class="bpv-card-ttl">
            <span><span class="bpv-att-dot" style="background:#1D9E75"></span>Достижения периода</span>
          </div>
          <UzaStateBlock v-if="!achievements.length" state="empty" variant="block" text="Нет показателей ≥100% плана" />
          <div v-else>
            <div
              v-for="(a, i) in achievements"
              :key="a.title"
              class="bpv-ach-row"
              :style="{ '--d': (i * 40) + 'ms' }"
            >
              <div>
                <div class="bpv-ach-ttl">{{ a.title }}</div>
                <div class="bpv-ach-d">факт {{ bpFmt(a.fact) }} · план {{ bpFmt(a.plan) }}</div>
              </div>
              <div class="bpv-ach-val">{{ Math.round(a.ratio * 100) }}%</div>
            </div>
          </div>
        </div>

      </div>

      <!-- ═══ 4. Comment block ═══ -->
      <div class="bpv-cmt" style="--d:540ms">
        <div class="bpv-cmt-hd">
          <span class="bpv-cmt-ttl">Комментарий руководителя</span>
          <span style="display:flex;align-items:center;gap:10px">
            <span class="bpv-cmt-meta">{{ comment?.body ? 'обновлено' : '' }}</span>
            <button v-if="canEdit && !editingComment" class="bpv-cmt-edit" @click="editingComment = true">
              {{ comment?.body ? 'Редактировать' : 'Добавить' }}
            </button>
          </span>
        </div>
        <div v-if="!editingComment">
          <div v-if="comment?.body" class="bpv-cmt-text">{{ comment.body }}</div>
          <div v-else class="bpv-cmt-text empty">Комментарий не задан. Нажмите «{{ canEdit ? 'Добавить' : '—' }}» чтобы добавить пояснение для НС.</div>
        </div>
        <div v-else>
          <textarea
            v-model="commentDraft"
            class="bpv-cmt-textarea"
            placeholder="Например: Операционный план Q1 выполнен на 104%. Отставание по IPO-процессу из-за задержки аудита — перенос на Q2..."
          ></textarea>
          <div class="bpv-cmt-btns">
            <button class="bpv-cmt-cancel" @click="editingComment = false; commentDraft = comment?.body ?? ''">Отмена</button>
            <button class="bpv-cmt-save" @click="saveComment" :disabled="savingComment">
              {{ savingComment ? 'Сохранение...' : 'Сохранить' }}
            </button>
          </div>
        </div>
      </div>

      <!-- ═══ 5. Details ОФР ═══ -->
      <div class="bpv-card" style="--d:600ms">
        <div class="bpv-card-ttl bpv-det-head">
          <div class="bpv-det-info">
            <div class="lt">Детализация ОФР</div>
            <div class="ls">Структура · {{ period === 'annual' ? 'годовой' : period.toUpperCase() }} {{ year }}</div>
          </div>
          <div class="bpv-det-actions">
            <!-- View-mode toggle (All / Income / Expenses) -->
            <div class="bpv-view-toggle">
              <button
                class="bpv-view-btn bpv-view-btn-inc"
                :class="{ on: viewMode === 'income' }"
                @click="viewMode = 'income'"
              >Доходы</button>
              <button
                class="bpv-view-btn bpv-view-btn-exp"
                :class="{ on: viewMode === 'expenses' }"
                @click="viewMode = 'expenses'"
              >Расходы</button>
            </div>
            <button class="bpv-det-tgl" @click="detailsExpanded = !detailsExpanded">
              {{ detailsExpanded ? 'Свернуть' : 'Раскрыть все' }}
            </button>
          </div>
        </div>
        <div class="bpv-det-body">
          <table class="bpv-det-tbl">
            <thead>
              <tr>
                <th class="lbl">Показатель</th>
                <th class="r">План</th>
                <th class="r">Ожидание</th>
                <th class="r">Факт</th>
                <th class="r">% плана</th>
              </tr>
            </thead>
            <tbody>
              <tr
                v-for="f in detailsFields"
                :key="f.key"
                :class="{
                  tot: ['grossProfit','opProfit','hhProfit','pbt','profit'].includes(f.key),
                  sub: f.sub,
                }"
              >
                <td class="lbl">
                  {{ f.label }}
                  <span v-if="f.auto" class="auto-tag">расчёт</span>
                  <span v-if="ytdKeys.has(f.key) && !prevQMissing" class="bpv-ytd-chip" title="Показано нарастающим итогом с начала года: в предыдущем квартале нет факта — «за квартал» не вычислить">нараст.</span>
                </td>
                <td class="r">{{ fmtV(cell(f.key).plan) }}</td>
                <td class="r">{{ fmtV(cell(f.key).expect) }}</td>
                <td class="r">
                  {{ fmtV(cell(f.key).fact) }}
                  <span v-if="cell(f.key).fact_auto" class="nsbu-badge" title="Автоматически из НСБУ">
                    <svg width="7" height="7" viewBox="0 0 10 10" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M1.5 5l2.5 2.5L8.5 2.5"/></svg>НСБУ
                  </span>
                </td>
                <td class="r">
                  <span class="bpv-det-pct" :class="(() => { const p = pctOf(cell(f.key)); return p == null ? '' : p >= 1.0 ? 'ok' : p >= 0.9 ? 'warn' : 'bad'; })()">
                    {{ pctOf(cell(f.key)) != null ? Math.round(pctOf(cell(f.key))! * 100) + '%' : '—' }}
                  </span>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>

    </div>
  </div>
</template>

<style scoped>
.bpv-scroll { background: #F4F3F9; min-height: 100%; padding: 0; }
.bpv-body { padding: 18px 22px 28px; }

/* ═══ Premium animations (1:1 legacy) ═══ */
@keyframes bpvCardIn {
  0% { opacity: 0; transform: translateY(10px) scale(.98); }
  60% { opacity: 1; transform: translateY(-2px) scale(1); }
  100% { opacity: 1; transform: translateY(0) scale(1); }
}
@keyframes bpvStripeIn {
  0% { transform: scaleX(0); }
  100% { transform: scaleX(1); }
}
@keyframes bpvNumIn {
  0% { opacity: 0; transform: translateY(6px); }
  100% { opacity: 1; transform: translateY(0); }
}
@keyframes bpvShimmer {
  0% { left: -60%; }
  100% { left: 160%; }
}
@keyframes bpvSlideIn {
  0% { opacity: 0; transform: translateX(-8px); }
  100% { opacity: 1; transform: translateX(0); }
}

/* Context line */
.bpv-context {
  display: flex; align-items: center; gap: 8px; flex-wrap: wrap;
  font-size: 11px; color: var(--t3, #5F5E5A); margin-bottom: 14px;
  animation: bpvNumIn .4s ease both;
}
.bpv-ctx-co { font-weight: 600; color: var(--t1, #1E2A4A); font-size: 13px; }
.bpv-ctx-sep { color: var(--t3, #94A3B8); }
.bpv-ctx-period { color: var(--t3, #5F5E5A); }
.bpv-ctx-auto {
  display: inline-flex; align-items: center; gap: 4px;
  padding: 2px 7px; background: rgba(29,158,117,.1); color: #0F6E56;
  border-radius: 4px; font-size: 9.5px; font-weight: 600;
  letter-spacing: .04em; text-transform: uppercase; margin-left: auto;
}

/* ═══ Status bar (4 cells) ═══ */
.bpv-stat-bar {
  display: grid; grid-template-columns: repeat(4, 1fr);
  gap: 10px; margin-bottom: 14px;
}
.bpv-stat-cell {
  background: var(--card-bg, rgba(255,255,255,0.82)); backdrop-filter: blur(16px) saturate(1.5); -webkit-backdrop-filter: blur(16px) saturate(1.5); border-radius: 10px; border: 1px solid var(--card-border, rgba(0,0,0,.05));
  padding: 12px 14px; position: relative; overflow: hidden;
  animation: bpvCardIn .5s var(--ease-standard) var(--d, 0ms) both;
  transition: background .25s, border-color .25s;
}
.bpv-stat-cell::before {
  content: ""; position: absolute; top: 0; left: 0; right: 0;
  height: 3px; background: var(--sc, #7F77DD); transform-origin: left;
  animation: bpvStripeIn .7s var(--ease-standard) var(--d, 0ms) both;
  transition: background .3s;
}
.bpv-stat-cell.ok      { --sc: var(--green); }
.bpv-stat-cell.warn    { --sc: var(--amber); }
.bpv-stat-cell.bad     { --sc: var(--sev-high); }
.bpv-stat-cell.neutral { --sc: var(--blue); }
.bpv-stat-lbl {
  font-size: 9.5px; font-weight: 600; color: var(--t3, var(--t-muted));
  text-transform: uppercase; letter-spacing: .06em; margin-bottom: 4px;
  animation: bpvNumIn .4s ease calc(var(--d, 0ms) + 50ms) both;
}
.bpv-stat-val {
  font-size: 20px; font-weight: 500; color: var(--t1, #1E2A4A);
  letter-spacing: -.015em; font-feature-settings: "tnum"; line-height: 1.1;
  transition: color .25s;
  animation: bpvNumIn .5s ease calc(var(--d, 0ms) + 200ms) both;
}
.bpv-stat-sub {
  font-size: 10.5px; color: var(--t3, var(--t-muted)); margin-top: 3px;
  animation: bpvNumIn .4s ease calc(var(--d, 0ms) + 300ms) both;
}

/* ═══ KPI grid ═══ */
.bpv-grid {
  display: grid; grid-template-columns: repeat(4, 1fr);
  gap: 12px; margin-bottom: 14px;
}
.kpi2.bpv-kpi-cell {
  position: relative; overflow: hidden;
  background: rgba(255,255,255,.92); border: 1px solid rgba(255,255,255,.7); border-radius: 12px;
  padding: 14px 16px 12px; box-shadow: 0 2px 8px rgba(15,23,60,.06);
  cursor: pointer;
  transition: box-shadow .2s, border-color .2s;
}
.kpi2.bpv-kpi-cell:hover {
  box-shadow: 0 3px 14px rgba(15,23,60,.08);
  border-color: rgba(0,0,0,.12);
}
.kpi2.bpv-kpi-cell::before {
  content: ''; position: absolute; top: 0; left: 0; right: 0; height: 3px;
  background: var(--kpi2-accent, #7F77DD); border-radius: 12px 12px 0 0;
  animation: bpvStripeIn .8s var(--ease-standard) var(--kpi2-d, 0ms) both;
  transform-origin: left;
}
.kpi2.bpv-kpi-cell.fin-shimmer::after {
  content: ""; position: absolute; top: 0; left: -60%;
  width: 60%; height: 100%;
  background: linear-gradient(90deg, transparent, rgba(127,119,221,.07), transparent);
  animation: bpvShimmer 1.1s ease-out calc(var(--d, 0ms) + 200ms) forwards;
  pointer-events: none; z-index: 2;
}
.bpv-kpi-auto {
  position: absolute; top: 10px; right: 12px;
  display: inline-flex; align-items: center; gap: 3px;
  padding: 2px 6px; background: rgba(29,158,117,.1); color: #0F6E56;
  border-radius: 4px; font-size: 9px; font-weight: 600;
  letter-spacing: .04em; text-transform: uppercase; z-index: 3;
}
.bpv-kpi-l {
  font-size: 10px; color: var(--t3, var(--t-muted)); text-transform: uppercase;
  letter-spacing: .06em; font-weight: 600; margin-bottom: 6px;
  animation: bpvNumIn .4s ease calc(var(--d, 0ms) + 50ms) both;
}
.bpv-kpi-v {
  font-size: 36px; font-weight: 400; color: var(--t1, #1E2A4A);
  letter-spacing: -.04em; line-height: 1; font-feature-settings: "tnum";
  transition: color .25s;
  animation: bpvNumIn .5s ease calc(var(--d, 0ms) + 180ms) both;
}
.bpv-kpi-v.is-empty { font-size: 26px; color: var(--t3, var(--t-muted)); font-weight: 500; }
.bpv-kpi-u {
  font-size: 12px; color: var(--t3, var(--t-muted)); margin-top: 5px; font-weight: 400;
}
.bpv-kpi-foot {
  display: flex; align-items: center; gap: 10px; margin-top: 9px;
  padding-top: 9px; border-top: 0.5px solid rgba(0,0,0,.05);
}
.bpv-kpi-plan {
  font-size: 11px; font-weight: 600; font-feature-settings: "tnum";
  display: inline-flex; align-items: center;
  animation: bpvNumIn .45s ease calc(var(--d, 0ms) + 280ms) both;
}
.bpv-kpi-yoy {
  font-size: 11px; color: var(--t3, var(--t-muted)); font-feature-settings: "tnum";
  display: inline-flex; align-items: center;
  animation: bpvNumIn .45s ease calc(var(--d, 0ms) + 340ms) both;
}
.bpv-kpi-fc {
  margin-top: 6px; font-size: 10px; color: var(--t3, var(--t-muted));
  animation: bpvNumIn .4s ease calc(var(--d, 0ms) + 400ms) both;
}
.bpv-kpi-fc b { color: var(--t1, #1E2A4A); font-weight: 600; }

/* ═══ Row 2 ═══ */
.bpv-row2 {
  display: grid; grid-template-columns: 1.2fr 1fr 1fr;
  gap: 12px; margin-bottom: 14px;
}

.bpv-card {
  background: var(--card-bg, rgba(255,255,255,0.82)); backdrop-filter: blur(16px) saturate(1.5); -webkit-backdrop-filter: blur(16px) saturate(1.5); border-radius: 12px; border: 1px solid var(--card-border, rgba(0,0,0,.05));
  padding: 16px 18px; position: relative;
  animation: bpvCardIn .65s var(--ease-standard) var(--d, 0ms) both;
}
.bpv-card-ttl {
  font-size: 11px; font-weight: 600; color: var(--t3, var(--t-muted));
  text-transform: uppercase; letter-spacing: .07em;
  margin: 0 0 12px;
  display: flex; justify-content: space-between; align-items: center;
  animation: bpvNumIn .45s ease var(--d, 0ms) both;
}

/* YTD-фолбэк баннер (пред. квартал пуст) */
.bpv-ytd-note {
  display: flex; align-items: center; gap: 8px;
  margin: 10px 0 2px; padding: 8px 13px;
  background: rgba(239, 159, 39, .08);
  border: 1px solid rgba(239, 159, 39, .3);
  border-radius: 9px;
  font-size: 11.5px; color: #A36500;
}
.bpv-ytd-note b { font-weight: 700; }
.bpv-ytd-note svg { flex-shrink: 0; }
.bpv-ytd-chip {
  display: inline-block; margin-left: 5px; padding: 1px 6px; border-radius: 5px;
  font-size: 8.5px; font-weight: 700; text-transform: uppercase; letter-spacing: .04em;
  background: rgba(239, 159, 39, .13); color: #A36500;
  border: 1px solid rgba(239, 159, 39, .35); cursor: help; vertical-align: 1px;
}

/* Chart */
.bpv-chart-wrap { height: 180px; position: relative; }
/* Интерактивные кварталы: слот подсвечивается, курсор — кликабельность */
.bpvq-grp { cursor: pointer; }
.bpvq-slot { fill: transparent; transition: fill .14s; }
.bpvq-grp.on .bpvq-slot { fill: rgba(124, 111, 247, .07); }
.bpvq-tip {
  position: absolute; top: 2px; transform: translateX(-50%);
  background: #1B1730; color: #fff; border-radius: 10px; padding: 9px 11px;
  font-size: 11px; min-width: 170px; pointer-events: none; z-index: 5;
  box-shadow: 0 12px 30px rgba(20, 16, 50, .4); animation: bpvqTipIn .14s ease;
}
@keyframes bpvqTipIn { from { opacity: 0; transform: translateX(-50%) translateY(-4px); } to { opacity: 1; transform: translateX(-50%); } }
.bpvq-tip-h { font-size: 12px; font-weight: 700; margin-bottom: 5px; }
.bpvq-tip-r { display: flex; justify-content: space-between; gap: 14px; padding: 1.5px 0; }
.bpvq-tip-r span { color: rgba(255, 255, 255, .55); }
.bpvq-tip-r b { font-weight: 600; font-variant-numeric: tabular-nums; }
.bpvq-tip-note { font-size: 9.5px; color: #F2C4C3; padding: 2px 0; }
.bpvq-tip-cta { margin-top: 6px; padding-top: 5px; border-top: 1px solid rgba(255, 255, 255, .12); color: #C7C2F0; font-size: 10px; }
/* Прогноз: ghost-бар + коридор + легенда/тултип */
.bpvq-ghost { fill: rgba(93, 192, 147, .18); stroke: #2FA97C; stroke-width: 1; stroke-dasharray: 3 2.5; }
.bpvq-whisker { stroke: #2FA97C; stroke-width: 1.2; opacity: .5; stroke-linecap: round; }
.bpvq-dot-ghost { background: rgba(93, 192, 147, .25) !important; border: 1.2px dashed #2FA97C; box-sizing: border-box; }
.bpvq-tip-fc { color: #A9E4C8; font-style: italic; }
.bpvq-tip-note-fc { color: rgba(169, 228, 200, .8); }
.bpv-chart-empty {
  display: flex; flex-direction: column; align-items: center; justify-content: center;
  height: 100%; color: var(--t3, var(--t-muted)); font-size: 12px; text-align: center; gap: 3px;
}
.bpv-chart-empty-sub { font-size: 10.5px; opacity: .7; }
.bpv-chart-lgd {
  display: flex; gap: 14px; margin-top: 10px;
  font-size: 11px; color: var(--t3, var(--t-muted));
}
.bpv-chart-lgd .dot {
  display: inline-block; width: 9px; height: 9px; border-radius: 2px;
  margin-right: 5px; vertical-align: -1px;
}

/* Attention */
.bpv-att-dot {
  display: inline-block; width: 6px; height: 6px; border-radius: 50%;
  margin-right: 6px; vertical-align: middle;
}
.bpv-att-row {
  padding: 8px 11px; border-radius: 8px; margin-bottom: 6px;
  display: flex; justify-content: space-between; align-items: flex-start;
  gap: 10px;
  animation: bpvSlideIn .35s cubic-bezier(.22,.61,.36,1) var(--d, 0ms) both;
  position: relative; overflow: hidden;
  --bpv-accent: transparent;
}
.bpv-att-row::before {
  content: ""; position: absolute; top: 0; left: 0; right: 0;
  height: 2px; background: var(--bpv-accent);
  border-top-left-radius: inherit; border-top-right-radius: inherit;
  animation: uzaStripeDrawIn .5s var(--ease-standard) both;
  pointer-events: none;
}
.bpv-att-row:last-child { margin-bottom: 0; }
.bpv-att-row.high   { background: #FEF2F2; --bpv-accent: var(--sev-high); }
.bpv-att-row.medium { background: #FFFBEB; --bpv-accent: var(--amber); }
.bpv-att-ttl { font-size: 12px; font-weight: 600; color: var(--t1, #1E2A4A); margin-bottom: 2px; }
.bpv-att-d   { font-size: 10.5px; color: var(--t3, #5F5E5A); line-height: 1.4; }
.bpv-att-val { font-size: 11px; font-weight: 700; font-feature-settings: "tnum"; white-space: nowrap; flex-shrink: 0; }
.bpv-att-row.high .bpv-att-val   { color: var(--sev-critical); }
.bpv-att-row.medium .bpv-att-val { color: #8A5F15; }

/* Achievements */
.bpv-ach-row {
  padding: 7px 11px; border-radius: 8px; margin-bottom: 6px;
  background: rgba(29,158,117,.06);
  display: flex; justify-content: space-between; align-items: flex-start;
  gap: 10px;
  animation: bpvSlideIn .35s cubic-bezier(.22,.61,.36,1) var(--d, 0ms) both;
  position: relative; overflow: hidden;
}
.bpv-ach-row::before {
  content: ""; position: absolute; top: 0; left: 0; right: 0;
  height: 2px; background: var(--green);
  border-top-left-radius: inherit; border-top-right-radius: inherit;
  animation: uzaStripeDrawIn .5s var(--ease-standard) both;
  pointer-events: none;
}
.bpv-ach-row:last-child { margin-bottom: 0; }
.bpv-ach-ttl { font-size: 12px; font-weight: 600; color: var(--t1, #1E2A4A); margin-bottom: 2px; }
.bpv-ach-d   { font-size: 10.5px; color: var(--t3, #5F5E5A); line-height: 1.4; }
.bpv-ach-val { font-size: 11px; font-weight: 700; color: #0F6E56; font-feature-settings: "tnum"; white-space: nowrap; flex-shrink: 0; }

/* ═══ Comment ═══ */
.bpv-cmt {
  padding: 14px 18px; background: var(--card-bg, rgba(255,255,255,0.82));
  backdrop-filter: blur(16px) saturate(1.5); -webkit-backdrop-filter: blur(16px) saturate(1.5);
  border: 1px solid var(--card-border, rgba(0,0,0,.05)); border-radius: 12px; margin-bottom: 14px;
  animation: bpvCardIn .55s var(--ease-standard) var(--d, 0ms) both;
}
.bpv-cmt-hd { display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px; }
.bpv-cmt-ttl { font-size: 11px; font-weight: 600; color: var(--t3, var(--t-muted)); text-transform: uppercase; letter-spacing: .07em; }
.bpv-cmt-meta { font-size: 10.5px; color: var(--t3, var(--t-muted)); font-weight: 500; }
.bpv-cmt-text { font-size: 13px; line-height: 1.6; color: var(--t1, #1E2A4A); white-space: pre-wrap; min-height: 20px; }
.bpv-cmt-text.empty { color: var(--t3, var(--t-muted)); font-style: italic; }
.bpv-cmt-edit {
  padding: 4px 12px; font-size: 11px; border: 1px solid rgba(0,0,0,.08);
  border-radius: 6px; background: var(--bg1, #fff); color: var(--t3, var(--t-muted)); cursor: pointer;
  font-family: inherit; transition: all .15s;
}
.bpv-cmt-edit:hover { background: #fafafa; color: var(--t1, #1E2A4A); border-color: rgba(0,0,0,.15); }
.bpv-cmt-textarea {
  width: 100%; min-height: 80px; padding: 10px 12px;
  border: 1px solid rgba(127,119,221,.3); border-radius: 8px;
  font-size: 13px; line-height: 1.55; font-family: inherit; color: var(--t1, #1E2A4A);
  resize: vertical; outline: none; box-sizing: border-box;
}
.bpv-cmt-textarea:focus { border-color: #7F77DD; box-shadow: 0 0 0 2px rgba(127,119,221,.15); }
.bpv-cmt-btns { display: flex; gap: 6px; justify-content: flex-end; margin-top: 8px; }
.bpv-cmt-btns button {
  padding: 5px 14px; font-size: 11px; border-radius: 6px;
  cursor: pointer; font-family: inherit; font-weight: 500; transition: all .15s;
}
.bpv-cmt-save { background: #7F77DD; color: #fff; border: none; }
.bpv-cmt-save:hover:not(:disabled) { background: #6B63D4; }
.bpv-cmt-save:disabled { opacity: .6; cursor: not-allowed; }
.bpv-cmt-cancel { background: var(--bg1, #fff); color: var(--t3, var(--t-muted)); border: 1px solid rgba(0,0,0,.08); }
.bpv-cmt-cancel:hover { background: #fafafa; color: var(--t1, #1E2A4A); }

/* ═══ Details ОФР ═══ */
.bpv-det-head { display: flex; justify-content: space-between; align-items: flex-start; }
.bpv-det-info .lt { font-size: 11px; font-weight: 600; color: var(--t1, #1E2A4A); letter-spacing: .005em; text-transform: none; }
.bpv-det-info .ls { font-size: 10px; color: var(--t3, var(--t-muted)); font-weight: 500; margin-top: 2px; text-transform: none; letter-spacing: .02em; }
.bpv-det-actions {
  display: flex; align-items: center; gap: 8px; flex-shrink: 0;
}
.bpv-view-toggle {
  display: inline-flex;
  align-items: center;
  gap: 1px;
  padding: 2px;
  background: rgba(127, 119, 221, .06);
  border: 0.5px solid rgba(127, 119, 221, .15);
  border-radius: 6px;
}
.bpv-view-btn {
  background: transparent;
  border: none;
  cursor: pointer;
  font-family: inherit;
  font-size: 10.5px;
  font-weight: 500;
  color: var(--t3, var(--t-muted));
  padding: 3px 9px;
  border-radius: 4px;
  transition: background .15s, color .15s, box-shadow .15s;
  white-space: nowrap;
}
.bpv-view-btn:hover { color: var(--p-deep); }
.bpv-view-btn.on {
  background: var(--bg1, #fff);
  color: var(--p-deep);
  box-shadow: 0 1px 2px rgba(15, 23, 60, .08);
}
.bpv-view-btn-inc.on { color: #0F6E56; }
.bpv-view-btn-exp.on { color: #B86A0E; }

.bpv-det-tgl {
  padding: 5px 12px; font-size: 11px; border: 1px solid rgba(0,0,0,.08);
  border-radius: 6px; background: var(--bg1, #fff); color: var(--t3, #5F5E5A); cursor: pointer;
  font-family: inherit; font-weight: 500; transition: all .15s;
}
.bpv-det-tgl:hover { background: #F4F3F9; color: #7F77DD; border-color: rgba(127,119,221,.25); }

.bpv-det-tbl { width: 100%; border-collapse: collapse; font-size: 11.5px; }
.bpv-det-tbl th {
  padding: 8px 10px; font-size: 9.5px; font-weight: 600; color: var(--t3, var(--t-muted));
  text-transform: uppercase; letter-spacing: .05em;
  border-bottom: 1px solid rgba(0,0,0,.06); white-space: nowrap;
}
.bpv-det-tbl th.lbl { text-align: left; }
.bpv-det-tbl th.r { text-align: right; width: 110px; }
.bpv-det-tbl td { padding: 6px 10px; vertical-align: middle; }
.bpv-det-tbl td.lbl { color: var(--t3, #5F5E5A); }
.bpv-det-tbl td.r { text-align: right; font-feature-settings: "tnum"; font-variant-numeric: tabular-nums; color: var(--t1, #1E2A4A); }
.bpv-det-tbl tr { border-bottom: 0.5px solid rgba(0,0,0,.04); }
.bpv-det-tbl tr.tot td { font-weight: 600; color: var(--t1, #1E2A4A); background: rgba(127,119,221,.03); }
.bpv-det-tbl tr.sub td.lbl { padding-left: 28px; color: var(--t3, var(--t-muted)); font-size: 11px; }
.auto-tag {
  display: inline-block; margin-left: 6px;
  padding: 1px 6px; background: rgba(239,159,39,.12); color: #A36500;
  border-radius: 3px; font-size: 9px; font-weight: 600;
  letter-spacing: .04em; text-transform: uppercase; vertical-align: 1px;
}
.nsbu-badge {
  display: inline-flex; align-items: center; gap: 2px; margin-left: 4px;
  padding: 1px 5px; background: rgba(29,158,117,.1); color: #0F6E56;
  border-radius: 3px; font-size: 9px; font-weight: 600;
  letter-spacing: .04em; text-transform: uppercase; vertical-align: 1px;
}
.bpv-det-pct {
  display: inline-block; padding: 2px 8px; border-radius: 4px;
  font-size: 11px; font-weight: 600; font-feature-settings: "tnum";
}
.bpv-det-pct.ok   { background: rgba(29,158,117,.1); color: #0F6E56; }
.bpv-det-pct.warn { background: rgba(239,159,39,.1); color: #A36500; }
.bpv-det-pct.bad  { background: rgba(226,75,74,.1); color: var(--sev-critical); }
</style>
