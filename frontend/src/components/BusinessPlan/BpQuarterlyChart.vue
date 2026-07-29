<script setup lang="ts">
/**
 * BpQuarterlyChart — премиум-комбо: бары «ЗА квартал» (дельты) + линия
 * нарастающего итога + % исполнения с начала года. Hover-тултип, клик → drill,
 * анимации роста баров и draw-in линии.
 *
 * КАНОН: кварталы БП хранятся НАРАСТАЮЩИМ ИТОГОМ (НСБУ: q1=1 кв, q2=полугодие,
 * q3=9 мес, q4=год). Бары = *_delta с бэка (или клиентская конвертация
 * ytdToDeltas для старого payload); линия итога = хранимые cum-значения КАК
 * ЕСТЬ — раньше здесь был acc+= по уже-кумулятивным значениям (двойной счёт).
 * Линии факта и плана раздельны (не смешиваем колонки в одной линии — иначе
 * «нарастающий итог» мог падать на стыке факт→план).
 */
import { computed, onMounted, onUnmounted, ref } from "vue";
import { ytdToDeltas, type BpQuarterOutlook, type BpQuarterRow } from "@/api/bpKpi";
import { useI18n } from "@/composables/useI18n";
import { i18nKey } from "@/locale/keys";

const { t } = useI18n();

type QuarterRow = BpQuarterRow;

const props = defineProps<{
  quarters: QuarterRow[];
  label?: string;
  /** Форматтер значения (напр. fmtBn) */
  fmt: (n: number) => string;
  /** Прогноз оставшихся кварталов (ghost-бары + пунктирное продление итога). */
  forecast?: BpQuarterOutlook | null;
}>();

const emit = defineEmits<{ drill: [{ row: QuarterRow; index: number }] }>();

// ─── Геометрия (адаптивная: график заполняет виджет по высоте через
// ResizeObserver — бары крупные и прижаты к низу, без пустого места снизу) ───
const chartEl = ref<HTMLElement | null>(null);
const W = ref(560);
const H = ref(240);
const PAD = { t: 26, r: 14, b: 44, l: 14 };
const plotW = computed(() => W.value - PAD.l - PAD.r);
const plotH = computed(() => H.value - PAD.t - PAD.b);

const rows = computed(() => props.quarters || []);
const n = computed(() => Math.max(1, rows.value.length));
const slot = computed(() => plotW.value / n.value);

let ro: ResizeObserver | null = null;
let raf = 0;
onMounted(() => {
  const el = chartEl.value;
  if (el && typeof ResizeObserver !== "undefined") {
    ro = new ResizeObserver((entries) => {
      const r = entries[0]?.contentRect;
      if (!r || r.width <= 4 || r.height <= 4) return;
      const w = Math.round(r.width), h = Math.round(r.height);
      // Обновляем только при реальном изменении и на след. кадре — чтобы не
      // ловить «ResizeObserver loop» и не дёргать viewBox на суб-пиксельный шум.
      if (raf) cancelAnimationFrame(raf);
      raf = requestAnimationFrame(() => {
        if (w !== W.value) W.value = w;
        if (h !== H.value) H.value = h;
      });
    });
    ro.observe(el);
  }
});
onUnmounted(() => { ro?.disconnect(); ro = null; if (raf) cancelAnimationFrame(raf); });

function N(v: string | number | null | undefined): number | null {
  return v == null ? null : Number(v);
}

// Нарастающий итог = хранимые значения (cum_* с бэка; старый payload: plan/fact
// и ЕСТЬ YTD — фолбэк без пересчёта).
const cumPlan = computed(() => rows.value.map(r => N(r.cum_plan ?? r.plan)));
const cumFact = computed(() => rows.value.map(r => N(r.cum_fact ?? r.fact)));
// «За квартал» = дельты с бэка (per-company null-guard) либо клиентская
// конвертация YTD→дельты (payload без новых полей).
const hasDeltaFields = computed(() => rows.value.some(r => "plan_delta" in r || "fact_delta" in r));
const dPlan = computed(() =>
  hasDeltaFields.value ? rows.value.map(r => N(r.plan_delta)) : ytdToDeltas(cumPlan.value));
const dFact = computed(() =>
  hasDeltaFields.value ? rows.value.map(r => N(r.fact_delta)) : ytdToDeltas(cumFact.value));

// Прогноз: проекция по индексу квартала (ghost-бар рисуем только там, где нет
// факт-дельты — прогнозные кварталы).
const projByIdx = computed<Map<number, { value: number; low: number | null; high: number | null }>>(() => {
  const m = new Map();
  for (const p of props.forecast?.projections || []) {
    const i = Number(p.period?.[1]) - 1;
    if (Number.isFinite(i) && i >= 0 && i < 4 && p.value != null) {
      m.set(i, { value: p.value, low: p.low, high: p.high });
    }
  }
  return m;
});
const hasForecast = computed(() => projByIdx.value.size > 0);

// Пунктирное продление линии итога прогнозными кварталами: от последнего
// фактического YTD накапливаем прогнозные дельты. ЗНАЧЕНИЯ отдельно от
// ГЕОМЕТРИИ — иначе цикл computed (шкала зависит от значений, точки от шкалы).
const cumForecastVals = computed<{ i: number; v: number }[]>(() => {
  if (!projByIdx.value.size) return [];
  let lastI = -1, acc = 0;
  cumFact.value.forEach((v, i) => { if (v != null) { lastI = i; acc = v; } });
  const out: { i: number; v: number }[] = [];
  for (const i of [...projByIdx.value.keys()].sort((a, b) => a - b)) {
    if (i <= lastI) continue;
    acc += projByIdx.value.get(i)!.value;
    out.push({ i, v: acc });
  }
  return out;
});

// Шкала с нулевой базой: отрицательная дельта (напр. убыточный квартал по
// прибыли) рисуется ВНИЗ от базовой линии, а не исчезает (SVG молча отбрасывает
// rect с отрицательной высотой). Прогнозные значения/коридор — тоже в шкале.
const scaleMin = computed(() => {
  let m = 0;
  for (const arr of [dPlan.value, dFact.value]) for (const v of arr) if (v != null) m = Math.min(m, v);
  for (const p of projByIdx.value.values()) {
    m = Math.min(m, p.value);
    if (p.low != null) m = Math.min(m, p.low);
  }
  return m;
});
const scaleMax = computed(() => {
  let m = 0;
  for (const arr of [dPlan.value, dFact.value, cumPlan.value, cumFact.value]) {
    for (const v of arr) if (v != null) m = Math.max(m, v);
  }
  for (const p of projByIdx.value.values()) {
    m = Math.max(m, p.value);
    if (p.high != null) m = Math.max(m, p.high);
  }
  for (const p of cumForecastVals.value) m = Math.max(m, p.v);
  return m || 1;
});
const range = computed(() => (scaleMax.value - scaleMin.value) || 1);

function centerX(i: number) { return PAD.l + slot.value * i + slot.value / 2; }
function yOf(v: number) { return PAD.t + plotH.value * (1 - (v - scaleMin.value) / range.value); }
const baseY = computed(() => yOf(0));
function barY(v: number) { return Math.min(yOf(v), baseY.value); }
function barHt(v: number) { return v === 0 ? 0 : Math.max(Math.abs(yOf(v) - baseY.value), 1); }

// Линии нарастающего итога: факт (сплошная, до последнего квартала с фактом) и
// план (пунктирная референс-линия). Точки строго одной колонки.
function cumPts(arr: (number | null)[]) {
  const out: { x: number; y: number; v: number; i: number }[] = [];
  arr.forEach((v, i) => { if (v != null) out.push({ x: centerX(i), y: yOf(v), v, i }); });
  return out;
}
const cumFactPts = computed(() => cumPts(cumFact.value));
// Линия нараст. ПЛАНА — только кварталы с ПОЛНЫМ покрытием компаний: планы
// часто разнесены лишь до Q2, и «провал» линии на Q3 (3 компании вместо 21)
// был бы артефактом покрытия, а не падением плана.
const cumPlanPts = computed(() => {
  const covs = rows.value.map(r => r.co_count_cum_plan);
  const known = covs.filter((c): c is number => c != null);
  if (!known.length) return cumPts(cumPlan.value);   // старый payload — как раньше
  const maxCov = Math.max(...known);
  const vals = cumPlan.value.map((v, i) =>
    (covs[i] != null && covs[i]! < maxCov ? null : v));
  return cumPts(vals);
});
const cumFactLine = computed(() => cumFactPts.value.map((p) => `${p.x},${p.y}`).join(" "));
const cumPlanLine = computed(() => cumPlanPts.value.map((p) => `${p.x},${p.y}`).join(" "));
const cumLen = computed(() => {
  let len = 0;
  const pts = cumFactPts.value;
  for (let i = 1; i < pts.length; i++) {
    len += Math.hypot(pts[i].x - pts[i - 1].x, pts[i].y - pts[i - 1].y);
  }
  return Math.ceil(len) || 1;
});

// Геометрия прогнозного продления (стык с последней фактической точкой).
const cumForecastPts = computed(() => {
  const vals = cumForecastVals.value;
  if (!vals.length) return [] as { x: number; y: number; v: number; i: number }[];
  const pts = vals.map(p => ({ x: centerX(p.i), y: yOf(p.v), v: p.v, i: p.i }));
  const factPts = cumFactPts.value;
  return factPts.length ? [factPts[factPts.length - 1], ...pts] : pts;
});
const cumForecastLine = computed(() => cumForecastPts.value.map(p => `${p.x},${p.y}`).join(" "));

const _FC_METHOD_RU: Record<string, string> = {
  pace: i18nKey("план × темп"), seasonal: i18nKey("сезонность прошлого года"), run_rate: "run-rate",
  plan: i18nKey("по плану"), actual: i18nKey("год закрыт"), mixed: i18nKey("смешанный"), none: i18nKey("нет данных"),
};
const _FC_CONF_RU: Record<string, string> = { high: i18nKey("высокая"), medium: i18nKey("средняя"), low: i18nKey("низкая"), none: "—" };
const forecastMeta = computed(() => {
  const f = props.forecast;
  if (!f || !hasForecast.value) return null;
  return `${t(_FC_METHOD_RU[f.method] || f.method)} · ${t("увер.")}: ${t(_FC_CONF_RU[f.confidence] || f.confidence)}`;
});

// % исполнения — С НАЧАЛА ГОДА (YTD-факт / YTD-план того же квартала): это
// конвенция НСБУ-отчётности («исполнение за полугодие»), не % бара-дельты.
function execPct(i: number): number | null {
  const p = cumPlan.value[i], f = cumFact.value[i];
  if (p == null || p === 0 || f == null) return null;
  return Math.round((f / p) * 100);
}
function execColor(pct: number | null): string {
  if (pct == null) return "#94A3B8";
  if (pct >= 100) return "#1D9E75";
  if (pct >= 80) return "#A36500";
  return "#C5352F";
}
// Значение над баром: факт-дельта, иначе план-дельта.
function barLabel(i: number): { v: number; fact: boolean } | null {
  const f = dFact.value[i], p = dPlan.value[i];
  if (f != null) return { v: f, fact: true };
  if (p != null) return { v: p, fact: false };
  return null;
}

const hovered = ref<number | null>(null);
const maxPlanCov = computed(() => {
  const known = rows.value.map(r => r.co_count_cum_plan).filter((c): c is number => c != null);
  return known.length ? Math.max(...known) : null;
});
function tip(i: number) {
  const r = rows.value[i];
  return {
    q: r,
    dp: dPlan.value[i], df: dFact.value[i],
    ytdPlan: cumPlan.value[i], ytdFact: cumFact.value[i],
    pct: execPct(i),
    // дельта не вычислима при наличии YTD → нет данных предыдущего квартала
    deltaGap: dFact.value[i] == null && cumFact.value[i] != null,
    covCum: r.co_count_cum_fact, covDelta: r.co_count_fact_delta,
    // план этого квартала разнесён лишь частью компаний → бар/линия неполные
    planPartial: maxPlanCov.value != null && r.co_count_cum_plan != null
      && r.co_count_cum_plan < maxPlanCov.value
      ? `${r.co_count_cum_plan} / ${maxPlanCov.value}` : null,
    proj: dFact.value[i] == null ? (projByIdx.value.get(i) ?? null) : null,
  };
}
</script>

<template>
  <div class="bqc">
    <div class="bqc-hd">
      <span class="bqc-t">{{ t("Динамика по кварталам") }}<span v-if="label"> · {{ t(label) }}</span></span>
      <span class="bqc-legend">
        <span><i class="bqc-sw bqc-sw-plan" />{{ t("План (за кв.)") }}</span>
        <span><i class="bqc-sw bqc-sw-fact" />{{ t("Факт (за кв.)") }}</span>
        <span v-if="hasForecast" :title="forecastMeta || ''"><i class="bqc-sw bqc-sw-ghost" />{{ t("Прогноз") }}</span>
        <span><i class="bqc-sw bqc-sw-cum" />{{ t("Нараст. итог") }}</span>
        <span><i class="bqc-sw bqc-sw-cumplan" />{{ t("Нараст. план") }}</span>
      </span>
    </div>

    <div class="bqc-chart" ref="chartEl">
      <svg :viewBox="`0 0 ${W} ${H}`" class="bqc-svg" preserveAspectRatio="none">
        <!-- Нулевая база (видна, когда есть отрицательные дельты) -->
        <line v-if="scaleMin < 0" :x1="PAD.l" :x2="W - PAD.r" :y1="baseY" :y2="baseY" class="bqc-zero" />
        <!-- Бары «за квартал» + значения -->
        <g v-for="(q, i) in rows" :key="q.q"
           class="bqc-grp" :class="{ on: hovered === i }"
           @mouseenter="hovered = i" @mouseleave="hovered = null"
           @click="emit('drill', { row: q, index: i })">
          <!-- hover-подсветка слота -->
          <rect :x="PAD.l + slot * i" :y="PAD.t" :width="slot" :height="plotH" class="bqc-slot" />
          <!-- план (дельта) -->
          <rect v-if="dPlan[i] != null" class="bqc-bar bqc-bar-plan" :class="{ neg: dPlan[i]! < 0 }"
                :x="centerX(i) - 17" :y="barY(dPlan[i]!)" width="15" :height="barHt(dPlan[i]!)" rx="3"
                :style="{ '--gh': barHt(dPlan[i]!) + 'px', animationDelay: i * 90 + 'ms' }" />
          <!-- факт (дельта) -->
          <rect v-if="dFact[i] != null" class="bqc-bar bqc-bar-fact" :class="{ neg: dFact[i]! < 0 }"
                :x="centerX(i) + 2" :y="barY(dFact[i]!)" width="15" :height="barHt(dFact[i]!)" rx="3"
                :style="{ '--gh': barHt(dFact[i]!) + 'px', animationDelay: i * 90 + 60 + 'ms' }" />
          <!-- значение «за квартал» сверху (факт приоритетнее); знак сохраняем -->
          <text v-if="barLabel(i)" class="bqc-val" :class="{ 'bqc-val-fact': barLabel(i)!.fact }"
                :x="centerX(i) + (barLabel(i)!.fact ? 9 : -9)"
                :y="barLabel(i)!.v < 0 ? barY(barLabel(i)!.v) + barHt(barLabel(i)!.v) + 13 : barY(barLabel(i)!.v) - 7"
                text-anchor="middle">{{ barLabel(i)!.v < 0 ? '−' + fmt(Math.abs(barLabel(i)!.v)) : fmt(barLabel(i)!.v) }}</text>
          <!-- дельта не вычислима (нет пред. квартала), но итог есть — честный маркер -->
          <text v-else-if="cumFact[i] != null" class="bqc-val" :x="centerX(i)" :y="baseY - 7" text-anchor="middle">—</text>
          <!-- ПРОГНОЗ: ghost-бар на месте факта + коридор low..high -->
          <template v-if="dFact[i] == null && projByIdx.get(i)">
            <rect class="bqc-bar-ghost"
                  :x="centerX(i) + 2" :y="barY(projByIdx.get(i)!.value)" width="15"
                  :height="barHt(projByIdx.get(i)!.value)" rx="3" />
            <line v-if="projByIdx.get(i)!.low != null && projByIdx.get(i)!.high != null"
                  class="bqc-whisker"
                  :x1="centerX(i) + 9.5" :x2="centerX(i) + 9.5"
                  :y1="yOf(projByIdx.get(i)!.high!)" :y2="yOf(projByIdx.get(i)!.low!)" />
            <text class="bqc-val bqc-val-ghost" :x="centerX(i) + 9"
                  :y="barY(projByIdx.get(i)!.value) - 7" text-anchor="middle">≈{{ fmt(projByIdx.get(i)!.value) }}</text>
          </template>
          <!-- метка квартала -->
          <text class="bqc-qlbl" :x="centerX(i)" :y="H - 28" text-anchor="middle">{{ q.q.toUpperCase() }}</text>
          <!-- % исполнения с начала года (YTD/YTD) -->
          <text class="bqc-pct" :x="centerX(i)" :y="H - 12" text-anchor="middle"
                :style="{ fill: execColor(execPct(i)) }">
            <title>{{ t("Исполнение с начала года (нарастающим итогом)") }}</title>
            {{ execPct(i) != null ? execPct(i) + '%' : '—' }}
          </text>
        </g>

        <!-- Нарастающий план — пунктирная референс-линия (только план-колонка) -->
        <polyline v-if="cumPlanPts.length > 1" class="bqc-cumplan-line" :points="cumPlanLine" fill="none" />
        <!-- Нарастающий итог (факт) — сплошная, до последнего квартала с фактом -->
        <polyline v-if="cumFactPts.length > 1" class="bqc-cum-line" :points="cumFactLine" fill="none"
                  :style="{ strokeDasharray: cumLen, strokeDashoffset: cumLen }" />
        <!-- Прогнозное продление итога (пунктир, полые точки) -->
        <polyline v-if="cumForecastPts.length > 1" class="bqc-cum-fc" :points="cumForecastLine" fill="none" />
        <g v-for="p in cumForecastPts.slice(1)" :key="'f' + p.i">
          <circle class="bqc-cum-dot-fc" :cx="p.x" :cy="p.y" r="3.2" />
        </g>
        <g v-for="p in cumFactPts" :key="'c' + p.i">
          <circle class="bqc-cum-dot" :cx="p.x" :cy="p.y" r="3.5" :style="{ animationDelay: 500 + p.i * 110 + 'ms' }" />
        </g>
      </svg>

      <!-- Hover-тултип -->
      <div v-if="hovered != null" class="bqc-tip"
           :style="{ left: (centerX(hovered) / W * 100) + '%' }">
        <div class="bqc-tip-h">{{ rows[hovered].q.toUpperCase() }}</div>
        <div class="bqc-tip-r"><span>{{ t("За квартал · план") }}</span><b>{{ tip(hovered).dp != null ? fmt(tip(hovered).dp!) : '—' }}</b></div>
        <div v-if="tip(hovered).planPartial" class="bqc-tip-note">{{ t("план разнесён лишь частью компаний ({v})", { v: tip(hovered).planPartial! }) }}</div>
        <div class="bqc-tip-r"><span>{{ t("За квартал · факт") }}</span><b>{{ tip(hovered).df != null ? fmt(tip(hovered).df!) : '—' }}</b></div>
        <div v-if="tip(hovered).deltaGap" class="bqc-tip-note">{{ t("за квартал не вычислимо: нет данных предыдущего квартала") }}</div>
        <template v-if="tip(hovered).proj">
          <div class="bqc-tip-r"><span>{{ t("Прогноз (за кв.)") }}</span><b class="bqc-tip-fc">≈{{ fmt(tip(hovered).proj!.value) }}</b></div>
          <div class="bqc-tip-r" v-if="tip(hovered).proj!.low != null && tip(hovered).proj!.high != null">
            <span>{{ t("Коридор") }}</span><b>{{ fmt(tip(hovered).proj!.low!) }} – {{ fmt(tip(hovered).proj!.high!) }}</b>
          </div>
          <div v-if="forecastMeta" class="bqc-tip-note bqc-tip-note-fc">{{ forecastMeta }}</div>
        </template>
        <div class="bqc-tip-r"><span>{{ t("Нараст. план") }}</span><b>{{ tip(hovered).ytdPlan != null ? fmt(tip(hovered).ytdPlan!) : '—' }}</b></div>
        <div class="bqc-tip-r"><span>{{ t("Нараст. факт") }}</span><b>{{ tip(hovered).ytdFact != null ? fmt(tip(hovered).ytdFact!) : '—' }}</b></div>
        <div class="bqc-tip-r" v-if="tip(hovered).pct != null"><span>{{ t("Исполнение с начала года") }}</span><b :style="{ color: execColor(tip(hovered).pct) }">{{ tip(hovered).pct }}%</b></div>
        <template v-if="tip(hovered).covDelta != null && tip(hovered).covCum != null && tip(hovered).covDelta !== tip(hovered).covCum">
          <div class="bqc-tip-r"><span>{{ t("Покрытие") }}</span><b>{{ tip(hovered).covDelta }} / {{ tip(hovered).covCum }} {{ t("комп.") }}</b></div>
          <div class="bqc-tip-note">{{ t("в итог входят компании без данных пред. квартала — поэтому Σ баров ≠ нараст. итогу") }}</div>
        </template>
        <div class="bqc-tip-cta">{{ t("Открыть разбор →") }}</div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.bqc { display: flex; flex-direction: column; flex: 1; min-height: 0; }
.bqc-hd { display: flex; align-items: center; justify-content: space-between; gap: 10px; flex-wrap: wrap; margin-bottom: 6px; }
.bqc-t { font-size: 11px; font-weight: 600; text-transform: uppercase; letter-spacing: .05em; color: var(--t3, #94A3B8); }
.bqc-legend { display: inline-flex; gap: 12px; font-size: 10px; color: var(--t3, #8B889C); }
.bqc-legend span { display: inline-flex; align-items: center; gap: 4px; }
.bqc-sw { width: 9px; height: 9px; border-radius: 2px; display: inline-block; }
.bqc-sw-plan { background: #C7C2F0; }
.bqc-sw-fact { background: #7F77DD; }
.bqc-sw-cum { background: #EF9F27; border-radius: 50%; }
.bqc-sw-cumplan { background: transparent; border: 1.5px dashed #D9A648; border-radius: 50%; box-sizing: border-box; }

.bqc-chart { position: relative; flex: 1; min-height: 220px; }
/* SVG вынесен из потока (absolute), чтобы НЕ участвовать в расчёте высоты
   контейнера: иначе height:100% при неопределённой высоте родителя считался бы
   из aspect-ratio viewBox, ResizeObserver писал бы её обратно в H → viewBox →
   пересчёт → монотонный рост при смене масштаба/монитора. Теперь SVG просто
   заполняет .bqc-chart, а высоту задаёт flex/min-height — петли нет. */
.bqc-svg { position: absolute; inset: 0; width: 100%; height: 100%; display: block; overflow: visible; }

.bqc-grp { cursor: pointer; }
.bqc-slot { fill: transparent; rx: 8; transition: fill .14s; }
.bqc-grp.on .bqc-slot { fill: rgba(124,111,247,.06); }

.bqc-bar { transform-origin: bottom; transform-box: fill-box; animation: bqcGrow .55s cubic-bezier(.34,1.1,.64,1) both; }
.bqc-bar-plan { fill: #C7C2F0; }
.bqc-bar-fact { fill: #7F77DD; }
.bqc-grp.on .bqc-bar-fact { fill: #6C5CE7; }
/* Отрицательная дельта (напр. убыточный квартал по прибыли) — растёт вниз от
   нулевой базы, красный тон, чтобы не читалась как обычный бар. */
.bqc-bar-plan.neg { fill: #F2C4C3; transform-origin: top; }
.bqc-bar-fact.neg { fill: #E2807F; transform-origin: top; }
.bqc-zero { stroke: #B9B6C9; stroke-width: 1; stroke-dasharray: 3 3; }
@keyframes bqcGrow { from { transform: scaleY(0); opacity: .3; } to { transform: scaleY(1); opacity: 1; } }

.bqc-val { font-size: 10px; font-weight: 500; fill: var(--t3, #94A3B8); font-variant-numeric: tabular-nums; }
.bqc-val-fact { fill: var(--t1, #1A1730); font-weight: 700; }
.bqc-qlbl { font-size: 11px; font-weight: 600; fill: var(--t2, #6B6880); }
.bqc-pct { font-size: 10px; font-weight: 700; font-variant-numeric: tabular-nums; }

.bqc-cum-line {
  stroke: #EF9F27; stroke-width: 2; stroke-linecap: round; stroke-linejoin: round;
  animation: bqcDraw 1s ease .35s forwards;
}
/* Нарастающий ПЛАН — светлее и пунктиром: референс, не факт. */
.bqc-cumplan-line { stroke: #D9A648; stroke-width: 1.4; stroke-dasharray: 5 4; opacity: .55; }
/* ── ПРОГНОЗ: ghost-бар (полупрозрачный, пунктирная обводка) + коридор + линия ── */
.bqc-bar-ghost {
  fill: rgba(124, 111, 247, .16);
  stroke: #7C6FF7; stroke-width: 1.2; stroke-dasharray: 4 3;
  animation: bqcGhostIn .5s ease .4s both;
}
@keyframes bqcGhostIn { from { opacity: 0; } to { opacity: 1; } }
.bqc-whisker { stroke: #6C5CE7; stroke-width: 1.4; opacity: .45; stroke-linecap: round; }
.bqc-val-ghost { fill: #6C5CE7; font-style: italic; font-weight: 600; }
.bqc-cum-fc { stroke: #EF9F27; stroke-width: 1.6; stroke-dasharray: 4 4; opacity: .6; }
.bqc-cum-dot-fc { fill: #fff; stroke: #EF9F27; stroke-width: 1.6; stroke-dasharray: 2 1.5; opacity: .75; }
.bqc-sw-ghost { background: rgba(124,111,247,.18); border: 1.2px dashed #7C6FF7; box-sizing: border-box; }
.bqc-tip-fc { color: #C7C2F0; font-style: italic; }
.bqc-tip-note-fc { color: rgba(199,194,240,.75); }
@keyframes bqcDraw { to { stroke-dashoffset: 0; } }
.bqc-cum-dot { fill: #fff; stroke: #EF9F27; stroke-width: 2; animation: bqcDot .3s ease both; }
@keyframes bqcDot { from { opacity: 0; transform: scale(0); } to { opacity: 1; transform: scale(1); } }

.bqc-tip {
  position: absolute; top: 0; transform: translateX(-50%);
  background: #1B1730; color: #fff; border-radius: 10px; padding: 9px 11px;
  font-size: 11px; min-width: 150px; pointer-events: none; z-index: 5;
  box-shadow: 0 12px 30px rgba(20,16,50,.4); animation: bqcTipIn .14s ease;
}
@keyframes bqcTipIn { from { opacity: 0; transform: translateX(-50%) translateY(-4px); } to { opacity: 1; transform: translateX(-50%); } }
.bqc-tip-h { font-size: 12px; font-weight: 700; margin-bottom: 5px; }
.bqc-tip-r { display: flex; justify-content: space-between; gap: 14px; padding: 1.5px 0; }
.bqc-tip-r span { color: rgba(255,255,255,.55); }
.bqc-tip-r b { font-weight: 600; font-variant-numeric: tabular-nums; }
.bqc-tip-note { font-size: 9.5px; color: #F2C4C3; padding: 2px 0; }
.bqc-tip-cta { margin-top: 6px; padding-top: 5px; border-top: 1px solid rgba(255,255,255,.12); color: #C7C2F0; font-size: 10px; }

@media (prefers-reduced-motion: reduce) {
  .bqc-bar, .bqc-cum-line, .bqc-cum-dot { animation: none; }
  .bqc-cum-line { stroke-dashoffset: 0 !important; }
}
</style>
