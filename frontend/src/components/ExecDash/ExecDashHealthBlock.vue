<script setup lang="ts">
/**
 * ExecDashHealthBlock — Row 2.8.
 * Здоровье портфеля (SOE Health Check · RAG): средний балл устойчивости,
 * распределение по зонам, «тянут вниз» / «опора портфеля».
 *
 * Данные из exec.data.value.health (единый источник — SoeHealthService,
 * та же методика, что и дашборд /soe-health). Сдержанный дизайн по
 * фидбэку: цвет несут только зоны риска, не «светофорим» всё.
 */
import { computed, onMounted, ref } from "vue";
import { useRouter } from "vue-router";
import { useExecutiveDashboard } from "@/composables/useExecutiveDashboard";
import { useNumberTween } from "@/composables/useNumberTween";
import { ensureFinancialsCss } from "@/components/Financials/financialsHelpers";
import { api } from "@/api/client";
import SoeHealthDrillModal from "@/components/Financials/SoeHealthDrillModal.vue";
import type { SoeCompany } from "@/components/Financials/SoeHealthBoard.vue";
import { useI18n } from "@/composables/useI18n";

const { t } = useI18n();
const exec = useExecutiveDashboard();
const router = useRouter();

onMounted(() => { ensureFinancialsCss(); });

const block = computed(() => exec.data.value?.health || null);
const isFallback = computed(() =>
  !!block.value?.requested_year && block.value.requested_year !== block.value.year);

const zones = computed(() => block.value?.zones || []);
const zoneTotal = computed(() => zones.value.reduce((s, z) => s + (z.count || 0), 0));
// сегменты распределения (ширина ∝ доле), только непустые
const zoneSegs = computed(() => {
  const t = zoneTotal.value || 1;
  return zones.value
    .filter((z) => z.count > 0)
    .map((z) => ({ ...z, pct: Math.round((z.count / t) * 100) }));
});
// «требуют внимания» = две худшие зоны (высокий + критический)
const attention = computed(() => {
  const zs = zones.value;
  if (zs.length < 2) return 0;
  return (zs[zs.length - 1]?.count || 0) + (zs[zs.length - 2]?.count || 0);
});
const support = computed(() => zones.value[0]?.count || 0);

const worst = computed(() => block.value?.worst || []);
const best = computed(() => block.value?.best || []);

const tAvg = useNumberTween(() => Number(block.value?.avg) || 0, { duration: 900 });

// ── Drill: клик по компании → полный премиум-разбор здоровья (SoeHealthDrillModal).
// Компактный exec-блок не содержит коэффициентов/Z-Score → ленивно тянем полный
// overview SOE Health и открываем ту же модалку, что и на /soe-health board.
const ovCache = ref<{ zones: any[]; companies: SoeCompany[]; year: number; standard: string } | null>(null);
const drillCompany = ref<SoeCompany | null>(null);
const drillLoadingCode = ref<string | null>(null);
async function openDrill(c: { code: string }) {
  drillLoadingCode.value = c.code;
  try {
    if (!ovCache.value) {
      const r = await api.get("/financials/soe-health", {
        params: { year: block.value?.year, standard: block.value?.standard },
      });
      ovCache.value = r.data;
    }
    const full = (ovCache.value?.companies || []).find((x) => x.code === c.code);
    if (full) drillCompany.value = full;
  } catch { /* тихо — модалка просто не откроется */ }
  finally { drillLoadingCode.value = null; }
}
function onRowKey(e: KeyboardEvent, c: { code: string }) {
  if (e.key === "Enter" || e.key === " ") { e.preventDefault(); openDrill(c); }
}

function fmtDelta(v: number | null | undefined): string {
  if (v == null || isNaN(v)) return "";
  const s = v > 0 ? "+" : "";
  return `${s}${v.toFixed(1)}`;
}
// улучшение = снижение балла (ниже = устойчивее)
function deltaColor(v: number | null | undefined): string {
  if (v == null) return "#9AA0AE";
  if (v < 0) return "#1D9E75";   // балл упал — стало лучше
  if (v > 0) return "#E24B4A";   // балл вырос — хуже
  return "#9AA0AE";
}
function deltaArrow(v: number | null | undefined): string {
  if (v == null || v === 0) return "→";
  return v < 0 ? "▼" : "▲";
}

function openBoard() {
  router.push({ path: "/soe-health" });
}
</script>

<template>
  <section class="ed-card ehl-card">
    <header class="ehl-hdr">
      <div class="ehl-hdr-l">
        <div class="ehl-eyebrow">{{ t("Здоровье портфеля") }}
          <span v-if="isFallback" class="ehl-fallback">{{ t("данные за FY {year}", { year: block?.year }) }}</span>
        </div>
        <div class="ehl-sub">
          FY {{ block?.year || exec.year.value }} · SOE Health Check Tool · {{ t("RAG-оценка устойчивости") }}
        </div>
      </div>
      <div v-if="block && block.has_data" class="ehl-hdr-r">
        <span class="ehl-stat">{{ block.scored_count }} / {{ block.total_companies }} {{ t("оценено") }} · {{ t(block.standard || "") }}</span>
        <button class="ehl-open" type="button" @click="openBoard" :title="t('Открыть SOE Health Check Tool')">
          {{ t("Подробнее") }}
          <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M5 12h14"/><path d="M13 6l6 6-6 6"/></svg>
        </button>
      </div>
    </header>

    <!-- Empty -->
    <div v-if="!block || !block.has_data" class="ehl-empty">
      <svg width="36" height="36" viewBox="0 0 24 24" fill="none" stroke="currentColor"
           stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
        <path d="M22 12h-4l-3 9L9 3l-3 9H2"/>
      </svg>
      <div class="ehl-empty-title">{{ t("Нет данных о здоровье за FY {year}", { year: exec.year.value }) }}</div>
      <div class="ehl-empty-text">
        {{ t("Заполните финансовую отчётность портфеля (НСБУ / МСФО)") }}<br>
        {{ t("— коэффициенты и оценка рассчитаются автоматически.") }}
      </div>
    </div>

    <template v-else>
      <!-- KPI band -->
      <div class="ehl-kpi-band kpi-rail">
        <div class="ehl-kpi" :style="{ '--accent': block.avg_zone_color || '#7F77DD', '--d': '0ms' }">
          <div class="ehl-kpi-lbl">{{ t("Средний балл портфеля") }}</div>
          <div class="ehl-kpi-val">
            {{ tAvg.toFixed(1) }}<span class="ehl-kpi-u">/ 5</span>
          </div>
          <div class="ehl-kpi-zone" :style="{ color: block.avg_zone_color || '#9AA0AE' }">
            {{ t(block.avg_zone_label || '—') }} · {{ t("ниже = устойчивее") }}
          </div>
        </div>

        <div class="ehl-kpi" style="--accent: #E24B4A; --d: 80ms;">
          <div class="ehl-kpi-lbl">{{ t("Требуют внимания") }}</div>
          <div class="ehl-kpi-val">
            {{ attention }}<span class="ehl-kpi-u">{{ t("компаний") }}</span>
          </div>
          <div class="ehl-kpi-zone ehl-muted">{{ t("высокий + критический риск") }}</div>
        </div>

        <div class="ehl-kpi" style="--accent: #1D9E75; --d: 160ms;">
          <div class="ehl-kpi-lbl">{{ t("Опора портфеля") }}</div>
          <div class="ehl-kpi-val">
            {{ support }}<span class="ehl-kpi-u">{{ t("компаний") }}</span>
          </div>
          <div class="ehl-kpi-zone ehl-muted">{{ t("низкий риск") }}</div>
        </div>

        <div class="ehl-kpi" style="--accent: #7F77DD; --d: 240ms;">
          <div class="ehl-kpi-lbl">{{ t("Покрытие данными") }}</div>
          <div class="ehl-kpi-val">
            {{ block.scored_count }}<span class="ehl-kpi-u">/ {{ block.total_companies }}</span>
          </div>
          <div class="ehl-kpi-zone ehl-muted">
            {{ t("{n} без отчётности", { n: block.total_companies - block.scored_count }) }}
          </div>
        </div>
      </div>

      <!-- Распределение по зонам -->
      <div v-if="zoneSegs.length" class="ehl-dist">
        <div class="ehl-dist-hdr">{{ t("Распределение риска · {n} компаний", { n: zoneTotal }) }}</div>
        <div class="ehl-dist-bar">
          <div v-for="(z, i) in zoneSegs" :key="z.key" class="ehl-dist-seg"
               :style="{ width: z.pct + '%', background: z.color, '--d': (i * 90) + 'ms' }"
               :title="t(z.label) + ': ' + z.count">
            <span v-if="z.pct >= 10" class="ehl-dist-n">{{ z.count }}</span>
          </div>
        </div>
        <div class="ehl-legend">
          <span v-for="z in zones" :key="z.key" class="ehl-leg" :class="{ off: !z.count }">
            <i :style="{ background: z.color }" />{{ t(z.label) }}
            <b>{{ z.count }}</b>
          </span>
        </div>
      </div>

      <!-- Тянут вниз / Опора -->
      <div class="ehl-cols">
        <div class="ehl-col">
          <div class="ehl-col-t" style="color:#E24B4A">↓ {{ t("Тянут вниз") }}</div>
          <div v-for="(c, i) in worst" :key="c.code" class="ehl-row ehl-row-click"
               :class="{ 'is-loading': drillLoadingCode === c.code }"
               :style="{ '--d': (i * 60) + 'ms' }"
               role="button" tabindex="0" :title="t('Открыть разбор здоровья: {name}', { name: c.name })"
               @click="openDrill(c)" @keydown="onRowKey($event, c)">
            <span class="ehl-dot" :style="{ background: c.zone_color }" />
            <span class="ehl-name" :title="c.name">{{ c.name }}</span>
            <span v-if="c.delta != null" class="ehl-delta" :style="{ color: deltaColor(c.delta) }">
              {{ deltaArrow(c.delta) }} {{ fmtDelta(c.delta) }}
            </span>
            <span class="ehl-score" :style="{ color: c.zone_color, background: c.zone_color + '18' }">
              {{ c.overall.toFixed(1) }}
            </span>
            <span class="ehl-row-arr" aria-hidden="true">
              <svg v-if="drillLoadingCode !== c.code" width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"><path d="M9 6l6 6-6 6"/></svg>
              <span v-else class="ehl-row-spin" />
            </span>
          </div>
          <div v-if="!worst.length" class="ehl-none">{{ t("нет компаний в зонах риска") }}</div>
        </div>
        <div class="ehl-col">
          <div class="ehl-col-t" style="color:#1D9E75">↑ {{ t("Опора портфеля") }}</div>
          <div v-for="(c, i) in best" :key="c.code" class="ehl-row ehl-row-click"
               :class="{ 'is-loading': drillLoadingCode === c.code }"
               :style="{ '--d': (i * 60) + 'ms' }"
               role="button" tabindex="0" :title="t('Открыть разбор здоровья: {name}', { name: c.name })"
               @click="openDrill(c)" @keydown="onRowKey($event, c)">
            <span class="ehl-dot" :style="{ background: c.zone_color }" />
            <span class="ehl-name" :title="c.name">{{ c.name }}</span>
            <span v-if="c.delta != null" class="ehl-delta" :style="{ color: deltaColor(c.delta) }">
              {{ deltaArrow(c.delta) }} {{ fmtDelta(c.delta) }}
            </span>
            <span class="ehl-score" :style="{ color: c.zone_color, background: c.zone_color + '18' }">
              {{ c.overall.toFixed(1) }}
            </span>
            <span class="ehl-row-arr" aria-hidden="true">
              <svg v-if="drillLoadingCode !== c.code" width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"><path d="M9 6l6 6-6 6"/></svg>
              <span v-else class="ehl-row-spin" />
            </span>
          </div>
          <div v-if="!best.length" class="ehl-none">—</div>
        </div>
      </div>
    </template>

    <!-- Премиум-разбор здоровья компании — та же модалка, что на /soe-health -->
    <SoeHealthDrillModal
      :open="!!drillCompany"
      :company="drillCompany"
      :zones="ovCache?.zones || zones"
      :year="ovCache?.year ?? block?.year ?? 0"
      :standard="ovCache?.standard ?? block?.standard ?? ''"
      @close="drillCompany = null"
    />
  </section>
</template>

<style scoped>
.ehl-card {
  padding: 14px;
  background: var(--bg1, #fff);
  border-radius: 12px;
  border: 1px solid rgba(0, 0, 0, 0.05);
  box-shadow: 0 4px 14px rgba(15, 23, 60, 0.06);
  margin-top: 14px;
}
.ehl-hdr { display: flex; align-items: flex-end; justify-content: space-between; gap: 12px;
  padding-bottom: 12px; border-bottom: 0.5px solid rgba(0, 0, 0, 0.08); flex-wrap: wrap; }
.ehl-eyebrow { font-size: 11px; font-weight: 600; color: var(--t3, var(--t-muted));
  text-transform: uppercase; letter-spacing: 0.07em; margin-bottom: 3px; }
.ehl-sub { font-size: 11px; color: var(--t3, var(--t-muted)); letter-spacing: 0.04em; }
.ehl-fallback { display: inline-block; margin-left: 8px; font-size: 9.5px; font-weight: 600;
  letter-spacing: 0.03em; text-transform: none; color: #92610B; background: rgba(239, 159, 39, 0.14);
  border: 1px solid rgba(239, 159, 39, 0.3); padding: 2px 8px; border-radius: 999px; vertical-align: middle; }
.ehl-hdr-r { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }
.ehl-stat { font-size: 11px; color: var(--t3, var(--t-muted)); font-weight: 500;
  background: rgba(127, 119, 221, 0.07); padding: 4px 10px; border-radius: 8px; }
.ehl-open { display: inline-flex; align-items: center; gap: 5px; font-size: 11.5px; font-weight: 600;
  font-family: inherit; color: var(--p-deep, #534AB7); background: rgba(124, 111, 247, 0.08);
  border: 1px solid rgba(124, 111, 247, 0.28); border-radius: 9px; padding: 6px 12px; cursor: pointer;
  transition: all 0.15s ease; }
.ehl-open:hover { background: rgba(124, 111, 247, 0.16); transform: translateY(-1px); }
.ehl-open svg { transition: transform 0.15s ease; }
.ehl-open:hover svg { transform: translateX(2px); }

.ehl-empty { padding: 46px 20px; text-align: center; color: #6B6A66;
  display: flex; flex-direction: column; align-items: center; gap: 10px; }
.ehl-empty-title { font-size: 14px; font-weight: 700; color: var(--t3, var(--t-muted)); margin-top: 6px; }
.ehl-empty-text { font-size: 12px; line-height: 1.5; color: #6B6A66; }

/* KPI band — тот же fkb-card kit, что и налоговый блок */
.ehl-kpi-band { display: grid; grid-template-columns: repeat(4, 1fr); gap: 10px; margin: 14px 0; }
.ehl-kpi { background: rgba(255, 255, 255, 0.82); backdrop-filter: blur(16px) saturate(1.5);
  -webkit-backdrop-filter: blur(16px) saturate(1.5); border-radius: 14px; padding: 14px 16px 12px;
  border: 1px solid rgba(255, 255, 255, 0.70);
  box-shadow: 0 2px 12px rgba(15, 23, 60, 0.07), 0 1px 3px rgba(15, 23, 60, 0.04);
  position: relative; overflow: hidden; display: flex; flex-direction: column;
  justify-content: space-between; min-height: 92px;
  animation: finKpiCardIn .55s var(--ease-standard) var(--d, 0ms) both; }
.ehl-kpi::before { content: ''; position: absolute; top: 0; left: 0; right: 0; height: 3px;
  background: var(--accent, var(--border-input)); border-radius: 14px 14px 0 0;
  animation: finKpi2DrawIn .8s var(--ease-standard) var(--d, 0ms) both; transform-origin: left center; }
.ehl-kpi-lbl { font-size: 11px; font-weight: 500; color: var(--t3, var(--t-muted));
  text-transform: uppercase; letter-spacing: 0.06em; margin-bottom: 6px; }
.ehl-kpi-val { font-size: 26px; font-weight: 400; letter-spacing: -0.035em; line-height: 1;
  color: var(--t1, #1E2A4A); font-variant-numeric: tabular-nums; display: flex; align-items: baseline;
  gap: 5px; margin: 2px 0 4px; }
.ehl-kpi-u { font-size: 11px; color: var(--t3, var(--t-muted)); font-weight: 500; letter-spacing: 0; }
.ehl-kpi-zone { font-size: 10.5px; font-weight: 600; margin-top: 4px; }
.ehl-kpi-zone.ehl-muted { color: var(--t3, var(--t-muted)); font-weight: 500; }

/* Распределение по зонам */
.ehl-dist { margin: 4px 0 14px; }
.ehl-dist-hdr { font-size: 11px; font-weight: 700; color: var(--t3, var(--t-muted));
  text-transform: uppercase; letter-spacing: 0.06em; margin-bottom: 8px; }
.ehl-dist-bar { display: flex; height: 26px; border-radius: 8px; overflow: hidden; gap: 2px; }
.ehl-dist-seg { display: flex; align-items: center; justify-content: center; min-width: 3px;
  transform-origin: left center; animation: ehlSegIn .55s var(--ease-standard, ease) var(--d, 0ms) both; }
@keyframes ehlSegIn { from { transform: scaleX(0); opacity: 0; } to { transform: scaleX(1); opacity: 1; } }
.ehl-dist-n { font-size: 11px; font-weight: 700; color: #fff; font-variant-numeric: tabular-nums;
  text-shadow: 0 1px 2px rgba(0,0,0,.2); }
.ehl-legend { display: flex; flex-wrap: wrap; gap: 12px; margin-top: 9px; }
.ehl-leg { display: inline-flex; align-items: center; gap: 5px; font-size: 11px;
  color: var(--t2, #4B5468); font-weight: 500; }
.ehl-leg.off { opacity: 0.4; }
.ehl-leg i { width: 8px; height: 8px; border-radius: 50%; display: inline-block; }
.ehl-leg b { font-weight: 700; color: var(--t1, #1E2A4A); font-variant-numeric: tabular-nums; }

/* Две колонки */
.ehl-cols { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }
.ehl-col { background: var(--bg2, #FAFAFD); border-radius: 11px; padding: 11px 13px; }
.ehl-col-t { font-size: 10px; font-weight: 700; text-transform: uppercase; letter-spacing: .05em;
  margin-bottom: 8px; }
.ehl-row { display: flex; align-items: center; gap: 8px; padding: 6px 0;
  animation: ehlRowIn .4s var(--ease-standard, ease) var(--d, 0ms) both; }
@keyframes ehlRowIn { from { opacity: 0; transform: translateX(-4px); } to { opacity: 1; transform: translateX(0); } }
/* Кликабельная строка компании → drill здоровья (премиум-аффорданс) */
.ehl-row-click { cursor: pointer; border-radius: 8px; padding: 6px 8px; margin: 0 -8px;
  transition: background .15s var(--ease-standard, ease), transform .15s var(--ease-standard, ease); }
.ehl-row-click:hover { background: rgba(127, 119, 221, .08); transform: translateX(2px); }
.ehl-row-click:active { transform: translateX(2px) scale(.995); }
.ehl-row-click:focus-visible { outline: 2px solid rgba(124, 111, 247, .5); outline-offset: 1px; }
.ehl-row-click.is-loading { background: rgba(127, 119, 221, .06); }
.ehl-row-arr { margin-left: 1px; width: 13px; height: 13px; flex-shrink: 0; display: inline-flex;
  align-items: center; justify-content: center; color: var(--p, #7C6FF7);
  opacity: 0; transform: translateX(-3px);
  transition: opacity .16s, transform .16s; }
.ehl-row-click:hover .ehl-row-arr,
.ehl-row-click:focus-visible .ehl-row-arr { opacity: .9; transform: translateX(0); }
.ehl-row-click.is-loading .ehl-row-arr { opacity: 1; transform: none; }
.ehl-row-spin { width: 12px; height: 12px; border: 2px solid rgba(124, 111, 247, .25);
  border-top-color: #7C6FF7; border-radius: 50%; animation: ehlSpin .7s linear infinite; }
@keyframes ehlSpin { to { transform: rotate(360deg); } }
.ehl-dot { width: 8px; height: 8px; border-radius: 50%; flex-shrink: 0; }
.ehl-name { font-size: 12.5px; font-weight: 500; color: var(--t1, #1E2A4A);
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis; flex: 1; min-width: 0; }
.ehl-delta { font-size: 10.5px; font-weight: 700; font-variant-numeric: tabular-nums; flex-shrink: 0; }
.ehl-score { font-size: 12px; font-weight: 700; border-radius: 7px; padding: 2px 8px;
  font-variant-numeric: tabular-nums; flex-shrink: 0; }
.ehl-none { font-size: 11px; color: #C4C8D4; font-style: italic; padding: 4px 0; }

@media (max-width: 1100px) {
  .ehl-kpi-band { grid-template-columns: 1fr 1fr; }
  .ehl-cols { grid-template-columns: 1fr; }
}
</style>
