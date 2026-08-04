<template>
  <div class="bps-scroll">
    <div class="bps-body" :class="{ 'bps-refreshing': loading }">
      <!-- 4 KPI cards -->
      <div class="bps-kgrid kpi-rail">
        <div
          v-for="(cfg, i) in kpiCfgs"
          :key="cfg.m"
          class="kpi2 fin-shimmer bps-kpi-click"
          :style="kpiStyle(cfg.ac, i * 80)"
          @click="$emit('open-kpi', cfg.m)"
          :title="t('Открыть детализацию') + ' · ' + t(cfg.l)"
        >
          <div class="kpi2-lbl">{{ t(cfg.l) }}</div>
          <div v-if="metric(cfg.m).fact == null" class="kpi2-val kpi2-val-na">{{ t("— нет данных —") }}</div>
          <div v-else class="kpi2-val">
            <span><Odometer :value="fmtVal(metric(cfg.m).fact)" /></span>
          </div>
          <div class="kpi2-sub">{{ t(unitLabel(metric(cfg.m).fact)) }} · {{ t("факт") }}</div>

          <div class="bps-row">
            <div class="bps-cell">
              <span class="bps-cl">{{ t("План") }}</span>
              <span class="bps-cv"><Odometer :value="fmtVal(metric(cfg.m).plan)" /></span>
            </div>
            <div class="bps-cell">
              <span class="bps-cl">{{ t("Прогноз") }}</span>
              <span class="bps-cv"><Odometer :value="fmtVal(metric(cfg.m).expect)" /></span>
            </div>
            <div class="bps-cell">
              <span
                class="bps-cl"
                :style="deltaPctValue(cfg.m) != null ? { color: deltaColor(deltaPctValue(cfg.m)!) } : {}"
              >{{ t("Δ план") }}</span>
              <span
                class="bps-cv"
                :style="deltaPctValue(cfg.m) != null ? { color: deltaColor(deltaPctValue(cfg.m)!) } : {}"
              >{{ deltaPct(cfg.m) }}</span>
            </div>
          </div>

          <div v-if="yoy(cfg.m) != null" class="bps-yoy" :class="yoyClass(yoy(cfg.m)!)">
            YoY {{ fmt.fmtPercent(yoy(cfg.m), { decimals: 1, signed: true }) }}
          </div>

          <!-- Нарастающим итогом — под разделителем (только квартальные срезы) -->
          <div v-if="cum(cfg.m)" class="bps-cum" :title="t('С начала года (нарастающим итогом). Сумма «за квартал» по кварталам может отличаться: в итог входят и компании без данных предыдущего квартала.')">
            <span class="bps-cum-l">{{ t("Нараст. итогом") }}</span>
            <span class="bps-cum-v">
              {{ t("план") }} {{ cumTxt(cum(cfg.m)!.plan) }} · {{ t("факт") }} {{ cumTxt(cum(cfg.m)!.fact) }}<template v-if="cumPct(cfg.m) != null"> · <b :style="{ color: cumPct(cfg.m)! >= 100 ? '#1D9E75' : cumPct(cfg.m)! >= 80 ? '#A36500' : '#C5352F' }">{{ cumPct(cfg.m) }}%</b></template>
            </span>
          </div>
        </div>
      </div>

      <!-- Bottom row: 3 widgets -->
      <div class="bps-bot">
        <!-- Quarterly combo chart (бары план/факт + линия нараст. итога + drill) -->
        <div class="bps-w">
          <BpQuarterlyChart :quarters="(summary.by_quarter as any)" :label="t(headlineLabel)" :fmt="fmtBn" :forecast="quarterOutlook" @drill="onQuarterDrill" />
        </div>

        <!-- Top-3 leaders + laggards -->
        <div class="bps-w">
          <div class="bps-w-t">{{ t("Топ-3 лидеры") }}</div>
          <div class="bps-co-list">
            <div
              v-for="(c, i) in leaders"
              :key="c.company_id"
              class="bps-co-row"
              :style="{ '--cl': pctColor(c.pct), animationDelay: `${i * 60}ms` }"
              @click="$emit('open-company', c.company_id)"
            >
              <span class="nm">{{ resolveCompanyDisplayName(c.company_name_ru, c.company_id) }}</span>
              <span class="pc" :style="{ color: pctColor(c.pct) }">
                {{ fmt.fmtPercent(c.pct, { decimals: 1 }) }}
              </span>
            </div>
            <UzaStateBlock v-if="!leaders.length" state="empty" variant="inline" :text="t('Нет данных по {m}', { m: t(headlineGenitive) })" />
          </div>

          <div class="bps-w-t" style="margin-top: 14px">{{ t("Топ-3 отстающие") }}</div>
          <div class="bps-co-list">
            <div
              v-for="(c, i) in laggards"
              :key="c.company_id"
              class="bps-co-row"
              :style="{ '--cl': pctColor(c.pct), animationDelay: `${i * 60}ms` }"
              @click="$emit('open-company', c.company_id)"
            >
              <span class="nm">{{ resolveCompanyDisplayName(c.company_name_ru, c.company_id) }}</span>
              <span class="pc" :style="{ color: pctColor(c.pct) }">
                {{ fmt.fmtPercent(c.pct, { decimals: 1 }) }}
              </span>
            </div>
            <UzaStateBlock v-if="!laggards.length" state="empty" variant="inline" :text="t('Нет данных по {m}', { m: t(headlineGenitive) })" />
          </div>
        </div>

        <!-- Sectors -->
        <div class="bps-w">
          <div class="bps-sec-hd">
            <div class="bps-w-t" style="margin-bottom: 0">{{ t("По секторам") }} · {{ t(sectorMetricLabel) }}</div>
            <div class="bps-sec-toggle">
              <button :class="{ on: sectorMetric === 'headline' }" @click="sectorMetric = 'headline'">{{ t(headlineLabel) }}</button>
              <button :class="{ on: sectorMetric === 'profit' }" @click="sectorMetric = 'profit'">{{ t("Чистая прибыль") }}</button>
            </div>
          </div>
          <UzaStateBlock v-if="sectorMetric === 'profit' && profitLoading && !sectors.length" state="loading" variant="text" />
          <div v-else class="bps-sec-grid">
            <div
              v-for="s in sectors"
              :key="s.sector_code"
              class="bps-sec-card bps-sec-click"
              :style="{ '--cl': s.color, '--bg': s.color + '12', animationDelay: `${s.idx * 80}ms` }"
              @click="$emit('open-sector', s.sector_code, s.label)"
              :title="t('Открыть сектор') + ' · ' + s.label"
            >
              <div class="bps-sec-card-l">{{ t(s.label) }}</div>
              <div class="bps-sec-card-v">
                <Odometer :value="fmtBn(s.sum_revenue)" /><span class="bps-sec-card-u">{{ t(unitLabel(s.sum_revenue)) }}</span>
              </div>
              <div class="bps-sec-card-d">{{ s.share != null ? t("{p} портфеля", { p: fmt.fmtPercent(s.share, { decimals: 1 }) }) : "—" }}</div>
              <div class="bps-sec-card-bar" :style="{ '--w': s.shareBar + '%' }" />
            </div>
            <UzaStateBlock v-if="!sectors.length" state="empty" variant="inline" :text="t('Нет данных по секторам')" />
          </div>
        </div>
      </div>

      <!-- P&L Waterfall -->
      <div class="bps-w bps-wf-wrap" style="--d: 560ms">
        <div class="bps-w-t">{{ t("P&L каскад · от выручки до чистой прибыли") }}</div>
        <div class="bps-wf">
          <div
            v-for="(b, i) in waterfall"
            :key="b.k"
            class="bps-wfc bps-wf-click"
            @click="$emit('open-pnl-line', b.k)"
            :title="t('Открыть строку P&L') + ' · ' + t(b.label)"
          >
            <div
              v-if="b.h > 8"
              class="bps-wfb"
              :style="{ '--h': b.h + '%', height: b.h + '%', background: b.color, animationDelay: `${i * 100}ms` }"
            >
              {{ fmtBn(b.value) }}
            </div>
            <div
              v-else
              class="bps-wfb-out"
              :class="b.value < 0 ? 'neg' : 'pos'"
              :style="{ animationDelay: `${i * 100}ms` }"
            >
              {{ fmtBn(b.value) }}
            </div>
            <div class="bps-wfl">{{ t(b.label) }}</div>
          </div>
        </div>
        <div class="bps-wf-leg">
          <span><span class="sw" style="background: #A39EE6" /> {{ t("Доходы") }}</span>
          <span><span class="sw" style="background: #E89B9A" /> {{ t("Расходы") }}</span>
          <span><span class="sw" style="background: #7DC4A0" /> {{ t("Прибыль") }}</span>
        </div>
      </div>
    </div>

    <BpQuarterDrillModal v-if="quarterDrill" v-bind="quarterDrill" :fmt="fmtBn" @close="quarterDrill = null" />
  </div>
</template>

<script setup lang="ts">
import { computed, ref, watch } from "vue";
import {
  bpApi,
  bpFmtScaled,
  bpDeltaColor,
  num,
  type BpQuarterOutlook,
  type BpSummary,
} from "@/api/bpKpi";

import { useSectorMeta } from "@/utils/sectorMeta";
import { useFormatters } from "@/composables/useFormatters";
import BpQuarterlyChart from "./BpQuarterlyChart.vue";
import BpQuarterDrillModal from "./BpQuarterDrillModal.vue";
import Odometer from "@/components/Odometer.vue";
import UzaStateBlock from "@/components/UZA/UzaStateBlock.vue";
import { useI18n } from "@/composables/useI18n";
import { i18nKey } from "@/locale/keys";
import { resolveCompanyDisplayName } from "@/utils/displayNames";


const { t } = useI18n();

const fmt = useFormatters();

// Drill-разбор квартала (открывается из BpQuarterlyChart).
// КАНОН: кварталы хранятся нарастающим итогом — «итог» берётся из САМОЙ строки
// (раньше здесь был acc+= по уже-кумулятивным значениям → двойной счёт), дельты
// «за квартал» приходят с бэка (plan_delta/fact_delta, per-company null-guard).
const quarterDrill = ref<null | {
  q: string; plan: number | null; fact: number | null; expect?: number | null;
  planDelta: number | null; factDelta: number | null;
  cum: number | null; label: string; unit: string;
}>(null);
function onQuarterDrill(e: { row: any; index: number }) {
  const r = e.row;
  const numOr = (v: any): number | null => (v == null ? null : Number(v));
  const cum = numOr(r.cum_fact ?? r.fact) ?? numOr(r.cum_expect ?? r.expect) ?? numOr(r.cum_plan ?? r.plan);
  quarterDrill.value = {
    q: r.q,
    plan: numOr(r.cum_plan ?? r.plan), fact: numOr(r.cum_fact ?? r.fact),
    expect: numOr(r.cum_expect ?? r.expect),
    planDelta: numOr(r.plan_delta), factDelta: numOr(r.fact_delta),
    cum, label: t(headlineLabel.value), unit: t(unitLabel(cum)),
  };
}

const props = withDefaults(defineProps<{
  summary: BpSummary;
  lens?: "all" | "income" | "expenses";
  /** Идёт перезагрузка сводки (смена периода/года) — вуаль поверх старых данных,
   *  чтобы прошлый график не читался как актуальный. */
  loading?: boolean;
}>(), {
  lens: "all",
});

defineEmits<{
  (e: "open-company", id: string): void;
  (e: "open-kpi", metric: string): void;
  (e: "open-sector", code: string, label: string): void;
  (e: "open-pnl-line", lineKey: string): void;
}>();

// 4 KPI cards swap based on parent «lens» (Все / Доходы / Расходы)
const KPI_BY_LENS = {
  all: [
    { m: "revenue",    l: i18nKey("Выручка"),             ac: "#A39EE6" },
    { m: "opProfit",   l: i18nKey("Операционная прибыль"), ac: "#7DC4A0" },
    { m: "pbt",        l: i18nKey("Прибыль до налогов"),   ac: "#7DB4DC" },
    { m: "profit",     l: i18nKey("Чистая прибыль"),       ac: "#E8B575" },
  ],
  income: [
    { m: "revenue",    l: i18nKey("Выручка"),              ac: "#7DC4A0" },
    { m: "finIncome",  l: i18nKey("Финансовые доходы"),    ac: "#7DC4A0" },
    { m: "otherOpInc", l: i18nKey("Прочие опер. доходы"),  ac: "#7DC4A0" },
    { m: "opProfit",   l: i18nKey("Операционная прибыль"), ac: "#7DC4A0" },
    { m: "profit",     l: i18nKey("Чистая прибыль"),       ac: "#7DC4A0" },
  ],
  expenses: [
    { m: "cogs",       l: i18nKey("Себестоимость"),        ac: "#E8B575" },
    { m: "opExpenses", l: i18nKey("Расходы периода"),      ac: "#E8B575" },
    { m: "finCost",    l: i18nKey("Финансовые расходы"),   ac: "#E8B575" },
    { m: "tax",        l: i18nKey("Налог на прибыль"),     ac: "#E8B575" },
  ],
} as const;

const kpiCfgs = computed(() => KPI_BY_LENS[props.lens]);

function metric(key: string) {
  const t = props.summary.totals.find((m) => m.metric === key);
  if (!t) return { plan: null, expect: null, fact: null };
  return {
    plan: t.has_plan ? num(t.plan) : null,
    expect: t.has_expect ? num(t.expect) : null,
    fact: t.has_fact ? num(t.fact) : null,
  };
}

// Нарастающим итогом (квартальные срезы; annual → бэк отдаёт null → блок скрыт).
// Σ дельт ≠ итог при разном покрытии (компания без q1 в итоге есть, в дельте нет).
function cum(key: string): { plan: number | null; fact: number | null } | null {
  const t = props.summary.totals.find((m) => m.metric === key);
  if (!t || (t.cum_plan == null && t.cum_fact == null)) return null;
  return {
    plan: t.cum_plan != null ? num(t.cum_plan) : null,
    fact: t.cum_fact != null ? num(t.cum_fact) : null,
  };
}
function cumTxt(v: number | null): string {
  if (v == null) return "—";
  const s = bpFmtScaled(v);
  return `${s.value} ${t(s.unit)}`;
}
function cumPct(key: string): number | null {
  const c = cum(key);
  if (!c || c.plan == null || c.plan === 0 || c.fact == null) return null;
  return Math.round((c.fact / c.plan) * 100);
}

function prevFact(key: string): number | null {
  const t = props.summary.prev_totals.find((m) => m.metric === key);
  if (!t || !t.has_fact) return null;
  return num(t.fact);
}

function fmtVal(v: number | null): string {
  if (v == null) return "—";
  const s = bpFmtScaled(v);
  return s.value;
}

function fmtBn(v: number | string | null | undefined): string {
  if (v == null) return "—";
  const s = bpFmtScaled(v);
  return s.value;
}

function unitLabel(v: number | string | null | undefined): string {
  if (v == null) return "—";
  return Math.abs(num(v)) >= 1000 ? t('трлн') : t('млрд');
}

function deltaPctValue(key: string): number | null {
  const m = metric(key);
  const ref = m.fact != null ? m.fact : m.expect;
  if (ref == null || m.plan == null || m.plan === 0) return null;
  return (ref / m.plan - 1) * 100;
}

function deltaPct(key: string): string {
  const d = deltaPctValue(key);
  return fmt.fmtPercent(d, { decimals: 1, signed: true });
}

function deltaColor(d: number): string {
  return bpDeltaColor(d);
}

function yoy(key: string): number | null {
  const m = metric(key);
  const prev = prevFact(key);
  if (m.fact == null || prev == null || prev === 0) return null;
  return (m.fact / prev - 1) * 100;
}

function yoyClass(v: number): string {
  if (v > 1) return "up";
  if (v < -1) return "dn";
  return "flat";
}

function kpiStyle(accent: string, delay: number) {
  return {
    "--kpi2-accent": accent,
    "--kpi2-d": `${delay}ms`,
    animation: `kpiCardIn .55s cubic-bezier(0.34, 1.2, 0.64, 1) ${delay}ms both`,
  };
}

// For expenses lens, pct semantics flip: fact/plan < 100% means SPENT LESS
// THAN PLAN (good), > 100% means overrun (bad). For revenue, ≥100% is good.
function pctColor(p: number | null): string {
  if (p == null) return "#94A3B8";
  if (props.lens === "expenses") {
    if (p <= 100) return "#1D9E75";  // under budget — good
    if (p <= 110) return "#EF9F27";  // slight overrun
    return "#E24B4A";                // big overrun
  }
  if (p >= 100) return "#1D9E75";
  if (p >= 90) return "#EF9F27";
  return "#E24B4A";
}

// Human label for the current headline metric (drives widget titles).
const headlineLabel = computed(() => {
  if (props.lens === "expenses") return t("Расходы периода");
  return t("Выручка");
});

// ─── Прогноз оставшихся кварталов (ghost-бары «Динамики по кварталам») ───
const headlineKey = computed(() => (props.lens === "expenses" ? "opExpenses" : "revenue"));
const quarterOutlook = ref<BpQuarterOutlook | null>(null);
watch(
  () => [props.summary.year, headlineKey.value],
  async () => {
    quarterOutlook.value = null;
    try {
      quarterOutlook.value = await bpApi.getQuarterOutlook(props.summary.year, headlineKey.value);
    } catch {
      quarterOutlook.value = null;   // прогноз — прогрессив-энханс, без него график живёт
    }
  },
  { immediate: true },
);
const headlineGenitive = computed(() => {
  if (props.lens === "expenses") return i18nKey("расходам периода");
  return i18nKey("выручке");
});

// Leaders / laggards.
// For revenue: leader = highest pct (exceeded plan). Laggard = lowest pct (missed plan).
// For expenses: leader = LOWEST pct (under budget — best cost control). Laggard = highest pct (overran).
const leaders = computed(() => {
  const arr = props.summary.by_company.filter((c) => c.pct != null);
  if (props.lens === "expenses") {
    arr.sort((a, b) => (a.pct ?? 1e9) - (b.pct ?? 1e9));  // ascending — lowest first
  } else {
    arr.sort((a, b) => (b.pct ?? -1e9) - (a.pct ?? -1e9));  // descending — highest first
  }
  return arr.slice(0, 3);
});
const laggards = computed(() => {
  const arr = props.summary.by_company.filter((c) => c.pct != null);
  if (props.lens === "expenses") {
    arr.sort((a, b) => (b.pct ?? -1e9) - (a.pct ?? -1e9));  // descending — overruns first
  } else {
    arr.sort((a, b) => (a.pct ?? 1e9) - (b.pct ?? 1e9));  // ascending — laggards first
  }
  return arr.slice(0, 3);
});

// Pack 7.20: sector metadata comes from useSectorMeta() — single source of
// truth that reads sector.name_ru from companies store and applies fixed
// colours/canonical-code normalisation.
const secMeta = useSectorMeta();

// #16: переключатель метрики секторов — Выручка (headline) ⇄ Чистая прибыль.
// Профильную разбивку тянем отдельным запросом summary(metric=profit) лениво.
const sectorMetric = ref<"headline" | "profit">("headline");
const profitSummary = ref<BpSummary | null>(null);
const profitLoading = ref(false);

async function ensureProfit() {
  if (profitSummary.value || profitLoading.value) return;
  profitLoading.value = true;
  try {
    profitSummary.value = await bpApi.getSummary(props.summary.year, props.summary.period, "profit");
  } catch {
    profitSummary.value = null;
  } finally {
    profitLoading.value = false;
  }
}
watch(sectorMetric, (m) => { if (m === "profit") ensureProfit(); });
watch(() => [props.summary.year, props.summary.period], () => {
  profitSummary.value = null;
  if (sectorMetric.value === "profit") ensureProfit();
});

const sectorMetricLabel = computed(() =>
  sectorMetric.value === "profit" ? i18nKey("Чистая прибыль") : headlineLabel.value,
);
const sectorRows = computed(() =>
  sectorMetric.value === "profit"
    ? (profitSummary.value?.by_sector ?? [])
    : props.summary.by_sector,
);

const sectors = computed(() => {
  const rows = sectorRows.value;
  const total = rows.reduce((s, x) => s + num(x.sum_revenue), 0);
  return rows.map((s, i) => ({
    sector_code: s.sector_code,
    label: s.label,
    sum_revenue: num(s.sum_revenue),
    color: secMeta.byCode(s.sector_code).color,
    share: total > 0 ? (num(s.sum_revenue) / total) * 100 : null,
    shareBar: total > 0 ? Math.min(100, (num(s.sum_revenue) / total) * 100) : 0,
    idx: i,
  }));
});

// Waterfall — 6 bars: Revenue → COGS → GrossProfit → OpExp → OpProfit → Profit
const waterfall = computed(() => {
  const get = (k: string) => metric(k).fact;
  const items = [
    { k: "revenue", label: i18nKey("Выручка"), value: get("revenue") ?? 0, color: "#A39EE6" },
    { k: "cogs", label: i18nKey("Себестоимость"), value: -Math.abs(get("cogs") ?? 0), color: "#E89B9A" },
    { k: "grossProfit", label: i18nKey("Валовая"), value: get("grossProfit") ?? 0, color: "#7DC4A0" },
    { k: "opExpenses", label: i18nKey("Опер. расходы"), value: -Math.abs(get("opExpenses") ?? 0), color: "#E89B9A" },
    { k: "opProfit", label: i18nKey("Опер. прибыль"), value: get("opProfit") ?? 0, color: "#7DC4A0" },
    { k: "profit", label: i18nKey("Чистая прибыль"), value: get("profit") ?? 0, color: "#1D9E75" },
  ];
  const max = Math.max(...items.map((x) => Math.abs(x.value)));
  return items.map((x) => ({
    ...x,
    h: max > 0 ? Math.max(2, (Math.abs(x.value) / max) * 100) : 0,
  }));
});
</script>

<style scoped>
.bps-scroll {
  background: #f4f3f9;
  min-height: 100%;
  padding: 0;
}

.bps-body {
  padding: 18px 22px 28px;
}

.bps-kgrid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
  gap: 12px;
  margin-bottom: 14px;
}

@media (max-width: 1100px) {
  .bps-kgrid { grid-template-columns: repeat(2, 1fr); }
}

.kpi2 {
  position: relative;
  background: var(--card-bg, rgba(255, 255, 255, 0.82));
  backdrop-filter: blur(16px) saturate(1.5);
  -webkit-backdrop-filter: blur(16px) saturate(1.5);
  border: 1px solid var(--card-border, rgba(15, 23, 60, .06));
  border-radius: 16px;
  padding: 14px 16px;
  box-shadow: 0 2px 12px rgba(15, 23, 60, .07), 0 1px 3px rgba(15, 23, 60, .04);
  overflow: hidden;
}

/* Pack 155c: removed scoped .kpi2::before override (height 2px, no
   animation). Global .kpi2::before in main.css now applies — 3px stripe
   with drawIn + breathe + shimmer like the rest of the app. */

.fin-shimmer::after {
  content: "";
  position: absolute;
  top: 0; left: -100%;
  width: 60%; height: 100%;
  background: linear-gradient(100deg, transparent 35%, rgba(255,255,255,.55) 50%, transparent 65%);
  animation: shimmer 2.4s ease infinite;
  pointer-events: none;
}

@keyframes shimmer { 0%,20%{left:-60%} 60%,100%{left:100%} }
@keyframes kpiCardIn { from{opacity:0;transform:translateY(8px)} to{opacity:1;transform:translateY(0)} }

.kpi2-lbl {
  font-size: 10px;
  font-weight: 500;
  letter-spacing: .07em;
  text-transform: uppercase;
  color: rgba(15, 23, 60, .5);
  margin-bottom: 8px;
}

.kpi2-val {
  font-size: 24px;
  font-weight: 400;
  letter-spacing: -.025em;
  color: var(--t1, #1e2a4a);
  font-feature-settings: "tnum";
}
.kpi2-val-na { color: rgba(15, 23, 60, .45); font-size: 18px; }
.kpi2-sub { margin-top: 4px; font-size: 11px; color: rgba(15, 23, 60, .55); }

.bps-row {
  display: flex;
  justify-content: space-between;
  align-items: flex-end;
  margin-top: 11px;
  padding-top: 9px;
  border-top: .5px solid rgba(0, 0, 0, .05);
  font-size: 10px;
  font-variant-numeric: tabular-nums;
}

.bps-cell { display: flex; flex-direction: column; gap: 2px; }
.bps-cl {
  font-size: 9px;
  color: rgba(15, 23, 60, .5);
  letter-spacing: .04em;
  text-transform: uppercase;
  font-weight: 600;
}
.bps-cv { font-size: 11px; font-weight: 600; color: var(--t1, #1e2a4a); }

.bps-yoy {
  margin-top: 8px;
  font-size: 10.5px;
  font-weight: 600;
}
.bps-yoy.up { color: #3D9C72; }
.bps-yoy.dn { color: #C36868; }
.bps-yoy.flat { color: rgba(15, 23, 60, .5); }

/* Перезагрузка сводки: вуаль поверх СТАРЫХ данных (смена периода/года) — иначе
   прошлый график секунду читается как актуальный. Плавно, без layout-сдвига. */
.bps-refreshing {
  opacity: .45;
  filter: saturate(.55);
  pointer-events: none;
  transition: opacity .18s ease, filter .18s ease;
}

/* «Нарастающим итогом» — под разделителем (квартальные срезы) */
.bps-cum {
  display: flex; align-items: baseline; justify-content: space-between; gap: 10px;
  margin-top: 9px; padding-top: 8px;
  border-top: 1px dashed rgba(15, 23, 60, .12);
  cursor: help;
}
.bps-cum-l {
  font-size: 8.5px; font-weight: 700; text-transform: uppercase; letter-spacing: .06em;
  color: rgba(15, 23, 60, .45); white-space: nowrap;
}
.bps-cum-v {
  font-size: 10.5px; color: rgba(15, 23, 60, .68); font-variant-numeric: tabular-nums;
  text-align: right;
}
.bps-cum-v b { font-weight: 700; }

/* Bottom row */
.bps-bot {
  display: grid;
  grid-template-columns: 1.4fr 1fr 1fr;
  gap: 12px;
  margin-top: 14px;
  /* Виджеты равной высоты (stretch) — ряд без просветов-пустот; график
     заполняет свою карточку целиком (.bqc-chart flex:1). */
  align-items: stretch;
}
@media (max-width: 1100px) { .bps-bot { grid-template-columns: 1fr; } }

.bps-w {
  background: var(--card-bg, rgba(255, 255, 255, 0.82));
  backdrop-filter: blur(16px) saturate(1.5);
  -webkit-backdrop-filter: blur(16px) saturate(1.5);
  border: 1px solid var(--card-border, rgba(0, 0, 0, .05));
  border-radius: 12px;
  padding: 14px 16px;
  display: flex;
  flex-direction: column;
}

.bps-w-t {
  font-size: 10.5px;
  color: rgba(15, 23, 60, .55);
  font-weight: 600;
  letter-spacing: .06em;
  text-transform: uppercase;
  margin-bottom: 10px;
}

/* Quarterly bars */
.bps-qbars {
  display: flex;
  align-items: flex-end;
  justify-content: space-around;
  gap: 4px;
  height: 110px;
  padding: 0 6px;
  margin-top: auto;
}
.bps-qb {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 6px;
  min-width: 0;
}
.bps-qb-bars {
  display: flex;
  align-items: flex-end;
  justify-content: center;
  gap: 6px;
  height: 86px;
  width: 100%;
}
.bps-qb-col {
  position: relative;
  width: 22px;
  height: 100%;
  display: flex;
  flex-direction: column;
  justify-content: flex-end;
}
.bps-qb-vtop {
  position: absolute;
  top: -1px;
  left: 50%;
  transform: translate(-50%, -100%);
  font-size: 9px;
  font-variant-numeric: tabular-nums;
  letter-spacing: -.005em;
  white-space: nowrap;
  line-height: 1;
  pointer-events: none;
}
.bps-qb-vtop-plan { color: rgba(15,23,60,.45); font-weight: 500; }
.bps-qb-vtop-fact { color: #4B4193; font-weight: 600; }
.bps-qb-bp {
  width: 100%;
  background: rgba(163, 158, 230, .35);
  border-radius: 3px 3px 0 0;
  transition: height .8s var(--ease-standard);
  min-height: 1px;
}
.bps-qb-bf {
  width: 100%;
  background: #A39EE6;
  border-radius: 3px 3px 0 0;
  transition: height .8s var(--ease-standard);
  min-height: 1px;
  box-shadow: 0 1px 3px rgba(127,119,221,.18);
}
.bps-qb-l {
  font-size: 10px;
  color: rgba(15, 23, 60, .55);
  font-weight: 600;
  letter-spacing: .04em;
}

.bps-qb-legend {
  display: flex;
  justify-content: center;
  gap: 14px;
  margin-top: 8px;
  font-size: 10px;
  color: rgba(15,23,60,.55);
  font-weight: 500;
}
.bps-qb-legend span { display: inline-flex; align-items: center; gap: 5px; }
.bps-qb-sw { width: 9px; height: 9px; border-radius: 2px; }
.bps-qb-sw-plan { background: rgba(163, 158, 230, .35); }
.bps-qb-sw-fact { background: #A39EE6; }

/* Companies list */
.bps-co-list {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.bps-co-row {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 11px;
  padding: 7px 10px 7px 14px;
  border-radius: 6px;
  cursor: pointer;
  transition: background .12s, transform .12s;
  background: #FCFAFF;
  position: relative;
  overflow: hidden;
  animation: rowFade .35s ease both;
}

@keyframes rowFade { from{opacity:0;transform:translateX(-3px)} to{opacity:1;transform:translateX(0)} }

.bps-co-row::before {
  content: "";
  position: absolute;
  left: 0; top: 0; bottom: 0;
  width: 4px;
  background: var(--cl, #7F77DD);
}

.bps-co-row:hover { background: #F4F1FE; transform: translateX(2px); }
.bps-co-row .nm {
  flex: 1;
  color: var(--t1, #1e2a4a);
  font-weight: 500;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.bps-co-row .pc {
  font-weight: 600;
  font-size: 11px;
  min-width: 42px;
  text-align: right;
}
/* Sector cards */
.bps-sec-hd {
  display: flex; align-items: center; justify-content: space-between; gap: 8px;
  margin-bottom: 10px; flex-wrap: wrap;
}
.bps-sec-toggle {
  display: inline-flex; background: rgba(15, 23, 60, .05); border-radius: 7px; padding: 2px;
}
.bps-sec-toggle button {
  border: none; background: transparent; cursor: pointer;
  font-size: 10px; font-weight: 600; letter-spacing: .01em; color: rgba(15, 23, 60, .55);
  padding: 4px 9px; border-radius: 5px; transition: all .15s;
}
.bps-sec-toggle button:hover { color: rgba(15, 23, 60, .8); }
.bps-sec-toggle button.on {
  background: #fff; color: #1e2a4a; box-shadow: 0 1px 3px rgba(15, 23, 60, .1);
}

.bps-sec-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 8px;
}

.bps-sec-card {
  padding: 10px 12px 11px 16px;
  border-radius: 9px;
  background: linear-gradient(135deg, var(--bg) 0%, #fff 100%);
  border: .5px solid rgba(0, 0, 0, .06);
  position: relative;
  overflow: hidden;
  cursor: pointer;
  transition: transform .15s, box-shadow .15s;
  animation: secIn .55s var(--ease-standard) backwards;
}

@keyframes secIn { from{opacity:0;transform:translateY(4px)} to{opacity:1;transform:translateY(0)} }

.bps-sec-card::before {
  content: "";
  position: absolute;
  top: 0; left: 0; right: 0;
  height: 3px;
  background: var(--cl);
  border-top-left-radius: inherit;
  border-top-right-radius: inherit;
  transform-origin: left center;
  animation:
    uzaStripeDrawIn .8s var(--ease-standard) 100ms both,
    uzaStripeBreathe 2.8s ease-in-out 1s infinite;
  pointer-events: none;
  z-index: 1;
}

.bps-sec-card-l {
  font-size: 9.5px;
  color: rgba(15, 23, 60, .55);
  font-weight: 600;
  letter-spacing: .04em;
  text-transform: uppercase;
}
.bps-sec-card-v {
  font-size: 18px;
  font-weight: 300;
  color: var(--t1, #1e2a4a);
  letter-spacing: -.035em;
  margin-top: 5px;
  font-variant-numeric: tabular-nums;
}
.bps-sec-card-u {
  font-size: 10px;
  color: rgba(15, 23, 60, .45);
  font-weight: 500;
  margin-left: 3px;
}
.bps-sec-card-d {
  font-size: 9.5px;
  color: rgba(15, 23, 60, .55);
  font-weight: 500;
  margin-top: 4px;
  font-variant-numeric: tabular-nums;
}
.bps-sec-card-bar {
  position: absolute;
  bottom: 0; left: 0;
  height: 2px;
  background: var(--cl);
  animation: secBar .9s var(--ease-standard) forwards;
  width: 0;
}
@keyframes secBar { to { width: var(--w); } }

/* Waterfall */
.bps-wf-wrap { margin-top: 14px; }
.bps-wf {
  position: relative;
  height: 240px;
  display: flex;
  align-items: flex-end;
  gap: 10px;
  padding: 42px 6px 0;
  background: linear-gradient(180deg, #FAFAFF 0%, #FFFFFF 100%);
  border-radius: 8px;
  border: .5px solid rgba(0, 0, 0, .04);
}

.bps-wfc {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  height: 100%;
  justify-content: flex-end;
  position: relative;
}

.bps-wfb {
  width: 100%;
  border-radius: 3px 3px 0 0;
  position: relative;
  animation: wfGrow .9s var(--ease-standard) forwards;
  display: flex;
  align-items: flex-start;
  justify-content: center;
  padding-top: 5px;
  color: #fff;
  font-weight: 600;
  font-size: 11px;
  font-variant-numeric: tabular-nums;
  white-space: nowrap;
}

@keyframes wfGrow {
  0% { height: 0; opacity: .2; }
  100% { height: var(--h); opacity: 1; }
}

.bps-wfb-out {
  position: absolute;
  bottom: 100%;
  left: 50%;
  transform: translateX(-50%);
  margin-bottom: 4px;
  font-size: 11px;
  font-weight: 600;
  font-variant-numeric: tabular-nums;
  white-space: nowrap;
  animation: wfNumIn .5s ease forwards;
}
.bps-wfb-out.neg { color: #B91C1C; }
.bps-wfb-out.pos { color: var(--t1, #1e2a4a); }

@keyframes wfNumIn { from{opacity:0;transform:translateX(-50%) translateY(4px)} to{opacity:1;transform:translateX(-50%) translateY(0)} }

.bps-wfl {
  font-size: 10.5px;
  color: var(--t1, #1e2a4a);
  font-weight: 600;
  text-align: center;
  line-height: 1.3;
  margin-top: 8px;
  min-height: 32px;
}

.bps-wf-leg {
  display: flex;
  flex-wrap: wrap;
  gap: 14px;
  font-size: 10px;
  color: rgba(15, 23, 60, .55);
  margin-top: 12px;
  padding-left: 6px;
  font-weight: 500;
}
.bps-wf-leg span { display: flex; align-items: center; gap: 5px; }
.bps-wf-leg .sw { width: 10px; height: 10px; border-radius: 2px; }

/* ─── Pack 8.2: drill-down clickability ─────────────── */
.bps-kpi-click { cursor: pointer; transition: transform .15s, box-shadow .15s; }
.bps-kpi-click:hover { transform: translateY(-1px); box-shadow: 0 4px 14px rgba(15,23,60,.08); }

.bps-sec-click { cursor: pointer; }
/* .bps-sec-card already has hover styles in legacy CSS */

.bps-wf-click { cursor: pointer; transition: transform .15s; }
.bps-wf-click:hover { transform: translateY(-2px); }
.bps-wf-click:hover .bps-wfb { filter: brightness(1.08); }
</style>
