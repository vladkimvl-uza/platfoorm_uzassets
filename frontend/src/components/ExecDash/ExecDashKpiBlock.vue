<script setup lang="ts">
/**
 * ExecDashKpiBlock — «Общее выполнение KPI» на executive-dashboard.
 *
 * Компактный hero-срез из модуля KPI (KpiSummaryDashboard) — большой %,
 * управленческий статус, распределение индикаторов и драйверы/зоны риска.
 * Чипы-переключатели по кварталам в стиле БП-трекера (.ed-bp-tab).
 *
 * Данные тянутся независимо от основного payload дашборда:
 *   GET /kpi/summary/{year}/{period} (kpiApi.getSummary).
 * Год берётся из useExecutiveDashboard (общий тумблер FY дашборда),
 * квартал — локальный chip-стейт. Блок виден только при праве kpi.view.
 */
import { computed, ref, watch, onMounted } from "vue";
import { useRouter } from "vue-router";
import { useExecutiveDashboard } from "@/composables/useExecutiveDashboard";
import { usePermissions } from "@/composables/usePermissions";
import { useFormatters } from "@/composables/useFormatters";
import { kpiApi, kpiStatusColor, type KpiSummary, type KpiStatus } from "@/api/bpKpi";
import Odometer from "@/components/Odometer.vue";

const exec = useExecutiveDashboard();
const perm = usePermissions("kpi");
const fmt = useFormatters();
const router = useRouter();

type QPeriod = "q1" | "q2" | "q3" | "q4";
const QUARTERS: QPeriod[] = ["q1", "q2", "q3", "q4"];

const period = ref<QPeriod>("q1");
// Год, за который реально показаны данные (может отличаться от FY дашборда).
const resolvedYear = ref<number>(exec.year.value);
const summary = ref<KpiSummary | null>(null);
const loading = ref(false);
const errored = ref(false);

// seq-guard: применяем только результат ПОСЛЕДНЕГО запуска. Без кэша и без
// параллельного пробинга — раньше они на гонке onMounted+watch оставляли
// summary=null, и данные появлялись только по клику. Здесь автоподбор идёт
// ПОСЛЕДОВАТЕЛЬНО (await за await) под одним seq, поэтому гонок нет.
let _seq = 0;

const hasD = (s: KpiSummary | null): boolean => !!s && s.total_count > 0;

// Возвращает сводку, null (ошибка), или "stale" если запрос устарел.
async function fetchSummary(year: number, p: QPeriod, my: number): Promise<KpiSummary | null | "stale"> {
  try {
    const r = await kpiApi.getSummary(year, p);
    return my === _seq ? r : "stale";
  } catch (e) {
    console.warn("[ExecDashKpiBlock.fetch]", year, p, e);
    return my === _seq ? null : "stale";
  }
}

// Автоподбор периода с данными: выбранный FY (Q1→Q4), затем FY-1, FY-2.
async function resolve(): Promise<void> {
  if (!perm.value.canView) return;
  const my = ++_seq;
  loading.value = true;
  errored.value = false;
  const fy = exec.year.value;
  try {
    for (let back = 0; back <= 2; back++) {
      const y = fy - back;
      for (const p of QUARTERS) {
        const r = await fetchSummary(y, p, my);
        if (r === "stale") return;
        if (hasD(r)) {
          resolvedYear.value = y;
          period.value = p;
          summary.value = r;
          return;
        }
      }
    }
    // Нигде нет данных — показываем пусто за FY/Q1.
    if (my !== _seq) return;
    resolvedYear.value = fy;
    period.value = "q1";
    summary.value = null;
  } finally {
    if (my === _seq) loading.value = false;
  }
}

// Клик по кварталу — грузим именно этот период за подобранный год (всегда).
async function setPeriod(p: QPeriod): Promise<void> {
  period.value = p;
  const my = ++_seq;
  loading.value = true;
  errored.value = false;
  const r = await fetchSummary(resolvedYear.value, p, my);
  if (r === "stale") return;
  summary.value = r;
  errored.value = r === null;
  loading.value = false;
}

onMounted(resolve);
watch(() => exec.year.value, resolve);

const yearBadge = computed(() => (resolvedYear.value !== exec.year.value ? resolvedYear.value : null));

// ─── Hero derived ────────────────────────────────────────────────
const overallText = computed(() =>
  fmt.fmtPercent(summary.value?.overall ?? null, { decimals: 1 }),
);
const overallColor = computed(() => {
  const o = summary.value?.overall;
  return o == null ? "#94A3B8" : kpiStatusColor(o);
});

const periodLabel = computed(() => period.value.toUpperCase());

// Управленческий статус (1:1 c KpiSummaryDashboard)
const execStatus = computed(() => {
  const s = summary.value;
  if (!s || s.overall == null || s.total_count === 0) return { label: "Нет данных", cls: "is-na" };
  const o = s.overall;
  const critFail = s.crit_count + s.fail_count;
  const critShare = s.total_count > 0 ? critFail / s.total_count : 0;
  if (o < 75 || critShare >= 0.35) return { label: "Критично", cls: "is-crit" };
  if (o < 90 || critShare >= 0.2) return { label: "Риск", cls: "is-risk" };
  if (o < 100 || critFail > 0) return { label: "Зона внимания", cls: "is-warn" };
  return { label: "На цели", cls: "is-ok" };
});

const distSegments = computed<{ key: KpiStatus; label: string; color: string; count: number }[]>(() => {
  const s = summary.value;
  return [
    { key: "over", label: "Превышено", color: "#1D9E75", count: s?.over_count ?? 0 },
    { key: "hit", label: "На цели", color: "#7DC4A0", count: s?.hit_count ?? 0 },
    { key: "risk", label: "В риске", color: "#EF9F27", count: s?.risk_count ?? 0 },
    { key: "crit", label: "Критично", color: "#E24B4A", count: s?.crit_count ?? 0 },
    { key: "fail", label: "Провал", color: "#B91C1C", count: s?.fail_count ?? 0 },
  ];
});

const drivers = computed(() =>
  (summary.value?.by_sector || [])
    .filter((s) => (s.pct ?? 0) >= 100)
    .slice(0, 3)
    .map((s) => s.label),
);
const risks = computed(() =>
  (summary.value?.by_sector || [])
    .filter((s) => s.pct != null && s.pct < 90)
    .sort((a, b) => (a.pct ?? 0) - (b.pct ?? 0))
    .slice(0, 3)
    .map((s) => s.label),
);

const hasData = computed(() => !!summary.value && summary.value.total_count > 0);

function openKpi(): void {
  router.push({ name: "kpi" });
}
</script>

<template>
  <section v-if="perm.canView" class="ed-kpi-card" :aria-busy="loading">
    <!-- ═══ HEADER ═══ -->
    <div class="ed-kpi-head">
      <div class="ed-kpi-head-l">
        <div class="ed-kpi-head-t">Общее выполнение KPI<span
            v-if="yearBadge"
            class="ed-kpi-badge"
            title="За выбранный FY данных по KPI нет — показан последний год с данными"
          >данные за FY {{ yearBadge }}</span></div>
        <div class="ed-kpi-head-s">
          FY {{ resolvedYear }} · {{ periodLabel }}<template v-if="summary"> · {{ summary.co_count }} компаний</template>
        </div>
      </div>
      <div class="ed-kpi-tabs" role="tablist" aria-label="Квартал">
        <button
          v-for="q in QUARTERS"
          :key="q"
          class="ed-kpi-tab"
          :class="{ on: period === q }"
          role="tab"
          :aria-selected="period === q"
          @click="setPeriod(q)"
        >
          {{ q.toUpperCase() }}
        </button>
      </div>
    </div>

    <!-- ═══ LOADING ═══ -->
    <div v-if="loading && !summary" class="ed-kpi-skel">
      <div class="ed-kpi-skel-big" />
      <div class="ed-kpi-skel-line" />
      <div class="ed-kpi-skel-bar" />
    </div>

    <!-- ═══ EMPTY / ERROR ═══ -->
    <div v-else-if="!hasData" class="ed-kpi-empty">
      <div class="ed-kpi-empty-t">
        {{ errored ? "Не удалось загрузить KPI" : "Нет данных KPI" }}
      </div>
      <div class="ed-kpi-empty-s">
        <template v-if="errored">Повторите попытку позже.</template>
        <template v-else>За {{ periodLabel }} FY {{ resolvedYear }} индикаторы с весом не заполнены.</template>
      </div>
    </div>

    <!-- ═══ HERO ═══ -->
    <template v-else>
      <div
        class="ed-kpi-hero ed-kpi-hero-btn"
        role="button"
        tabindex="0"
        aria-label="Открыть модуль KPI"
        title="Открыть модуль KPI"
        @click="openKpi"
        @keydown.enter.prevent="openKpi"
        @keydown.space.prevent="openKpi"
      >
        <div class="ed-kpi-hero-top">
          <div class="ed-kpi-big">
            <span class="ed-kpi-big-v" :style="{ color: overallColor }"><Odometer :value="overallText" /></span>
          </div>
          <span class="ed-kpi-status" :class="execStatus.cls">{{ execStatus.label }}</span>
        </div>
        <div class="ed-kpi-meta">
          {{ summary!.total_count }} индикаторов с весом ·
          <span style="color:#1D9E75">{{ summary!.over_count }} превышено</span> ·
          <span style="color:#5AA77F">{{ summary!.hit_count }} на цели</span> ·
          <span style="color:#C97F1A">{{ summary!.risk_count }} в риске</span> ·
          <span style="color:#D14343">{{ summary!.crit_count }} критично</span> ·
          <span style="color:#B91C1C">{{ summary!.fail_count }} провалено</span>
        </div>
        <div v-if="drivers.length || risks.length" class="ed-kpi-drivers">
          <span v-if="drivers.length" class="ed-kpi-drv up">▲ Драйверы: {{ drivers.join(" · ") }}</span>
          <span v-if="risks.length" class="ed-kpi-drv dn">▼ Зоны риска: {{ risks.join(" · ") }}</span>
        </div>
      </div>

      <!-- Distribution -->
      <div class="ed-kpi-dist">
        <div
          v-for="(s, i) in distSegments"
          :key="s.key"
          class="ed-kpi-dist-seg"
          :style="{ flex: s.count, background: s.color, animationDelay: `${i * 70}ms` }"
          :title="`${s.label}: ${s.count}`"
        />
      </div>
      <div class="ed-kpi-dist-leg">
        <span v-for="s in distSegments" :key="s.key" class="ed-kpi-dist-leg-i">
          <span class="sw" :style="{ background: s.color }" />
          {{ s.label }} · {{ s.count }}
        </span>
      </div>
    </template>
  </section>
</template>

<style scoped>
/* ═══ CARD (стиль ed-bp-card) ═══ */
.ed-kpi-card {
  background: var(--bg1, #fff);
  border-radius: 14px;
  border: 1px solid rgba(0, 0, 0, 0.05);
  padding: 20px 22px;
  margin-top: 14px;
  margin-bottom: 14px;
  position: relative;
  overflow: hidden;
  animation: bpCardIn 0.65s var(--ease-standard) both;
}

/* ═══ HEADER ═══ */
.ed-kpi-head {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  margin-bottom: 14px;
  margin-top: 4px;
  gap: 12px;
}
.ed-kpi-head-l { min-width: 0; flex: 1; }
.ed-kpi-head-t {
  font-size: 11.5px;
  font-weight: 700;
  color: var(--t3, var(--t-muted));
  letter-spacing: 0.07em;
  text-transform: uppercase;
}
.ed-kpi-head-s { font-size: 11px; color: var(--t3, #94A3B8); margin-top: 2px; }
.ed-kpi-badge {
  display: inline-block;
  margin-left: 8px;
  font-size: 9.5px;
  font-weight: 700;
  letter-spacing: 0.02em;
  text-transform: none;
  color: #7F77DD;
  background: rgba(127, 119, 221, 0.10);
  border-radius: 999px;
  padding: 2px 8px;
  vertical-align: middle;
  white-space: nowrap;
}

/* Chips — 1:1 со стилем .ed-bp-tab */
.ed-kpi-tabs { display: flex; gap: 4px; flex-shrink: 0; }
.ed-kpi-tab {
  padding: 5px 12px;
  border: 0.5px solid rgba(0, 0, 0, 0.1);
  background: var(--bg2, #FAFAFC);
  border-radius: 6px;
  font-size: 11px;
  color: var(--t3, #94A3B8);
  font-family: inherit;
  cursor: pointer;
  font-weight: 500;
  transition: all 0.2s var(--ease-standard);
}
.ed-kpi-tab:hover {
  color: var(--t1, #1E2A4A);
  background: var(--bg1, #fff);
  transform: translateY(-1px);
  box-shadow: 0 2px 6px rgba(0, 0, 0, 0.06);
}
.ed-kpi-tab:active { transform: translateY(0) scale(0.97); }
.ed-kpi-tab.on {
  background: var(--bg1, #fff);
  color: var(--t1, #1E2A4A);
  border-color: rgba(127, 119, 221, 0.35);
  font-weight: 600;
}

/* ═══ HERO ═══ */
.ed-kpi-hero-btn { cursor: pointer; border-radius: 10px; outline: none; padding: 6px; margin: -6px -6px 0; }
.ed-kpi-hero-btn:hover { background: rgba(127, 119, 221, 0.03); }
.ed-kpi-hero-btn:focus-visible { box-shadow: 0 0 0 2px rgba(127, 119, 221, 0.45); }

.ed-kpi-hero-top { display: flex; align-items: center; gap: 14px; }
.ed-kpi-big { display: flex; align-items: baseline; }
.ed-kpi-big-v {
  font-size: 46px;
  font-weight: 300;
  letter-spacing: -0.04em;
  line-height: 1;
  font-variant-numeric: tabular-nums;
  transition: color 0.3s;
}
.ed-kpi-status {
  flex-shrink: 0;
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0.02em;
  padding: 4px 12px;
  border-radius: 999px;
}
.ed-kpi-status.is-ok   { color: #0F6E56; background: rgba(29, 158, 117, 0.13); }
.ed-kpi-status.is-warn { color: #A36500; background: rgba(239, 159, 39, 0.16); }
.ed-kpi-status.is-risk { color: #B25E00; background: rgba(224, 122, 0, 0.15); }
.ed-kpi-status.is-crit { color: #B0322E; background: rgba(209, 67, 67, 0.13); }
.ed-kpi-status.is-na   { color: #64748B; background: rgba(100, 116, 139, 0.12); }

.ed-kpi-meta {
  font-size: 11.5px;
  color: rgba(15, 23, 60, 0.72);
  font-weight: 500;
  margin-top: 8px;
}
.ed-kpi-drivers { display: flex; flex-wrap: wrap; gap: 16px; margin-top: 8px; font-size: 11px; font-weight: 600; }
.ed-kpi-drv.up { color: #1D9E75; }
.ed-kpi-drv.dn { color: #D14343; }

/* ═══ DISTRIBUTION ═══ */
.ed-kpi-dist {
  display: flex;
  height: 12px;
  gap: 1px;
  border-radius: 6px;
  overflow: hidden;
  margin-top: 16px;
  background: rgba(15, 23, 60, 0.04);
}
.ed-kpi-dist-seg {
  height: 100%;
  animation: distGrow 0.8s var(--ease-standard) backwards;
  transform-origin: left;
}
@keyframes distGrow { from { transform: scaleX(0); } to { transform: scaleX(1); } }

.ed-kpi-dist-leg {
  display: flex;
  flex-wrap: wrap;
  gap: 14px;
  margin-top: 10px;
  font-size: 10.5px;
  color: rgba(15, 23, 60, 0.62);
}
.ed-kpi-dist-leg-i { display: flex; align-items: center; gap: 5px; }
.ed-kpi-dist-leg-i .sw { width: 10px; height: 10px; border-radius: 2px; }

/* ═══ EMPTY ═══ */
.ed-kpi-empty { padding: 30px 16px; text-align: center; color: var(--t3, #94A3B8); font-size: 12.5px; }
.ed-kpi-empty-t { margin-bottom: 6px; font-weight: 600; }
.ed-kpi-empty-s { color: var(--t3, #94A3B8); }

/* ═══ SKELETON ═══ */
.ed-kpi-skel { padding: 6px 0 4px; }
.ed-kpi-skel-big { width: 160px; height: 46px; border-radius: 8px; background: rgba(15, 23, 60, 0.06); margin-bottom: 12px; animation: kpiSkel 1.2s ease-in-out infinite; }
.ed-kpi-skel-line { width: 70%; height: 13px; border-radius: 5px; background: rgba(15, 23, 60, 0.05); margin-bottom: 16px; animation: kpiSkel 1.2s ease-in-out infinite; }
.ed-kpi-skel-bar { width: 100%; height: 12px; border-radius: 6px; background: rgba(15, 23, 60, 0.05); animation: kpiSkel 1.2s ease-in-out infinite; }
@keyframes kpiSkel { 0%, 100% { opacity: 0.55; } 50% { opacity: 1; } }

@keyframes bpCardIn {
  0% { opacity: 0; transform: translateY(14px) scale(0.985); }
  60% { opacity: 1; transform: translateY(-3px) scale(1.002); }
  100% { opacity: 1; transform: translateY(0) scale(1); }
}
</style>
