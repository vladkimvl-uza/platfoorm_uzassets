<script setup lang="ts">
/**
 * ExecDashExecutionChart — Row 2 правая половина.
 * Vertical bar chart 21 компании, отсортирован по pct desc.
 * Цвет бара по threshold: ≥60 green / 30-59 amber / <30 red.
 * Линия среднего "Ср. 45%".
 *
 * Pure CSS implementation, без Chart.js (легковесно).
 */
import { computed, onMounted, ref } from "vue";
import { useExecutiveDashboard } from "@/composables/useExecutiveDashboard";
import { useCompaniesStore } from "@/stores/companies";
import { resolveCompanyDisplayName } from "@/utils/displayNames";

const exec = useExecutiveDashboard();
const companiesStore = useCompaniesStore();

// Pack 7.12: ensure companies cache is loaded so we can resolve display names
// (name_short || name_ru) by company_id, regardless of what the chart endpoint sends.
onMounted(() => { void companiesStore.ensureLoaded(); });

const rows = computed(() => exec.data.value?.execution_chart || []);
const avgPct = computed(() => exec.data.value?.avg_execution_pct || 0);

// Pack 7.31: hover state — единый индекс, синхронизирующий подсветку
// бара и его подписи (поскольку bar и label живут в разных flex-контейнерах).
const hoveredIdx = ref<number | null>(null);
function onBarEnter(i: number) { hoveredIdx.value = i; }
function onBarLeave() { hoveredIdx.value = null; }

const subTitle = computed(() => {
  if (!rows.value.length) return "";
  return `${rows.value.length} компаний · ранжирование по % задач`;
});

function barColor(pct: number): string {
  if (pct >= 60) return "#5DC093";  // green
  if (pct >= 30) return "#EFB373";  // amber
  return "#E2807F";                 // red
}

const yLabels = [100, 75, 50, 25, 0];

/**
 * Получить отображаемое имя компании по правилу name_short || name_ru.
 * Сначала пытаемся через companies store (по company_id) — он знает оба поля.
 * Фолбэк: то имя, что прислал backend (resolveCompanyDisplayName = trim).
 *
 * Pack 7.12: всё унифицировано через @/utils/displayNames + companies store.
 */
function companyLabel(row: { company_id: string; name: string }): string {
  const fromStore = companiesStore.getCompanyNameById(row.company_id);
  if (fromStore) return fromStore;
  return resolveCompanyDisplayName(row.name);
}

/** Полное name_ru для tooltip (если есть в кэше). */
function companyFullName(row: { company_id: string; name: string }): string {
  const co = companiesStore.findById(row.company_id);
  return co?.name_ru || row.name || "";
}
</script>

<template>
  <div class="ed-card">
    <!-- Header (with inline legend) -->
    <div class="ed-card-ttl">
      <span>Рейтинг компаний по исполнению</span>
      <span class="ed-card-meta">
        <span class="sub">{{ subTitle }}</span>
        <span class="vc-legend">
          <span class="vc-leg-item"><span class="vc-leg-dot" style="background: #5DC093" />≥60%</span>
          <span class="vc-leg-item"><span class="vc-leg-dot" style="background: #EFB373" />30–59%</span>
          <span class="vc-leg-item"><span class="vc-leg-dot" style="background: #E2807F" />&lt;30%</span>
        </span>
      </span>
    </div>

    <div v-if="!rows.length" class="ed-empty">
      Нет данных о компаниях с задачами для FY {{ exec.year.value }}
    </div>

    <div v-else class="vc-wrap">
      <!-- Chart area: y-grid + bars (without labels) -->
      <div class="vc-chart">
        <!-- Y-axis grid lines (без подписей % по запросу 2026-05-25) -->
        <div class="vc-grid">
          <div v-for="y in yLabels" :key="y" class="vc-grid-line" />
        </div>

        <!-- Bars -->
        <div class="vc-bars">
          <div
            v-for="(c, i) in rows"
            :key="c.company_id"
            class="vc-bar-col"
            :class="{
              'is-hovered': hoveredIdx === i,
              'is-dimmed':  hoveredIdx !== null && hoveredIdx !== i,
            }"
            :style="{ '--d': (i * 50) + 'ms', '--bg': barColor(c.pct) }"
            @mouseenter="onBarEnter(i)"
            @mouseleave="onBarLeave()"
            @focus="onBarEnter(i)"
            @blur="onBarLeave()"
            tabindex="0"
            :title="`${companyFullName(c)} · ${c.pct}% · ${i + 1} из ${rows.length}`"
          >
            <div class="vc-bar-val">{{ c.pct }}%</div>
            <div
              class="vc-bar"
              :style="{ '--h': c.pct + '%', '--bg': barColor(c.pct) }"
            />
          </div>
        </div>

        <!-- Average line -->
        <div
          class="vc-avg-line"
          :style="{ bottom: `calc(${avgPct}% * 0.93)` }"
        >
          <span class="vc-avg-lbl">Ср. {{ avgPct }}%</span>
        </div>
      </div>

      <!-- Labels row: separate from chart, mirrors bar columns -->
      <div class="vc-labels-row">
        <div
          v-for="(c, i) in rows"
          :key="`lbl-${c.company_id}`"
          class="vc-lbl-cell"
          :class="{
            'is-hovered': hoveredIdx === i,
            'is-dimmed':  hoveredIdx !== null && hoveredIdx !== i,
          }"
        >
          <span class="vc-lbl-text" :title="companyFullName(c)">{{ companyLabel(c) }}</span>
        </div>
      </div>

    </div>
  </div>
</template>

<style scoped>
.ed-card {
  background: var(--bg1, #fff);
  border-radius: 12px;
  border: 1px solid rgba(0, 0, 0, 0.05);
  padding: 18px 20px 16px;
  box-shadow: 0 4px 14px rgba(15, 23, 60, 0.04);
  height: 100%;
  display: flex;
  flex-direction: column;
}

.ed-card-ttl {
  font-size: 11px;
  font-weight: 600;
  color: var(--t3, var(--t-muted));
  text-transform: uppercase;
  letter-spacing: 0.07em;
  margin: 0 0 14px;
  display: flex;
  justify-content: space-between;
  align-items: baseline;
  gap: 14px;
}
.ed-card-ttl .sub {
  font-size: 11.5px;
  color: #B4B2A9;
  font-weight: 500;
  text-transform: none;
  letter-spacing: 0;
}

.ed-empty {
  padding: 60px 20px;
  text-align: center;
  color: #B4B2A9;
  font-size: 11.5px;
  font-style: italic;
}

/* Chart wrapper */
.vc-wrap {
  position: relative;
  flex: 1;
  min-height: 360px;
  display: flex;
  flex-direction: column;
  padding-left: 32px;   /* для y-labels */
  padding-top: 8px;
}

/* Chart area: bars + grid lines */
.vc-chart {
  position: relative;
  flex: 1;
  min-height: 240px;
  display: flex;
}

.vc-grid {
  position: absolute;
  left: 0; right: 0;
  top: 0; bottom: 0;
  display: flex;
  flex-direction: column;
  justify-content: space-between;
  pointer-events: none;
}

.vc-grid-line {
  position: relative;
  height: 1px;
}
.vc-grid-line::before {
  content: "";
  position: absolute;
  left: 32px; right: 0;
  top: 0;
  height: 1px;
  background: rgba(0, 0, 0, 0.04);
}

.vc-grid-lbl {
  position: absolute;
  left: 0;
  top: -7px;
  font-size: 9.5px;
  color: #B4B2A9;
  font-weight: 500;
  font-feature-settings: "tnum";
  width: 28px;
  text-align: right;
}

/* Bars */
.vc-bars {
  display: flex;
  align-items: flex-end;
  gap: 4px;
  flex: 1;
  position: relative;
  z-index: 2;
}

.vc-bar-col {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  position: relative;
  min-width: 0;
  height: 100%;
  justify-content: flex-end;
  /* Pack 7.31: hover sync */
  transition: opacity 0.2s ease, filter 0.2s ease;
  cursor: pointer;
  outline: none;
}

.vc-bar-val {
  font-size: 9px;
  font-weight: 600;
  color: var(--t1, #1E2A4A);
  font-feature-settings: "tnum";
  margin-bottom: 3px;
  letter-spacing: -0.01em;
  transition: font-size 0.2s ease, color 0.2s ease, transform 0.2s ease, opacity 0.2s ease;
  transform-origin: center bottom;
}

.vc-bar {
  width: 100%;
  max-width: 22px;
  height: var(--h, 0%);
  background: var(--bg, var(--t-muted));
  border-radius: 4px 4px 0 0;
  animation: vcBarGrow 0.7s var(--ease-standard) var(--d, 0ms) both;
  transform-origin: left center;
  transform-origin: bottom;
  /* 2026-05-26: smooth height transition on year switch (was hard cut to new). */
  transition: filter 0.2s ease, opacity 0.2s ease, box-shadow 0.2s ease, max-width 0.2s ease,
              height 900ms var(--ease-out);
}

/* Hover state: highlighted column */
.vc-bar-col.is-hovered .vc-bar {
  max-width: 26px;
  filter: brightness(1.06) saturate(1.1);
  box-shadow: 0 6px 18px -4px var(--bg, rgba(0, 0, 0, 0.18));
}
.vc-bar-col.is-hovered .vc-bar-val {
  font-size: 11px;
  font-weight: 700;
  color: var(--bg, #1E2A4A);
  transform: scale(1.1);
}
.vc-bar-col:focus-visible {
  outline: none;
}
.vc-bar-col:focus-visible .vc-bar {
  box-shadow: 0 0 0 2px rgba(127, 119, 221, 0.45), 0 6px 18px -4px var(--bg, rgba(0, 0, 0, 0.18));
}

/* Dimmed state: every column EXCEPT the hovered one */
.vc-bar-col.is-dimmed .vc-bar {
  opacity: 0.32;
  filter: saturate(0.55);
}
.vc-bar-col.is-dimmed .vc-bar-val {
  opacity: 0.38;
}

/* Labels row — separate from chart, sits BELOW it.
 * Same flex layout as .vc-bars so each label cell aligns with its bar column. */
.vc-labels-row {
  display: flex;
  align-items: flex-start;
  gap: 4px;
  height: 110px;        /* room for vertical labels */
  padding-top: 6px;
  flex-shrink: 0;       /* never collapse — labels must stay visible */
}

.vc-lbl-cell {
  flex: 1;
  min-width: 0;
  height: 100%;
  display: flex;
  justify-content: center;
  align-items: flex-start;
  position: relative;
  transition: opacity 0.2s ease;
}

.vc-lbl-text {
  /* Vertical text, reads bottom-to-top, centered in its cell.
   * writing-mode + rotate(180deg) gives natural bottom-up reading; the
   * resulting block width equals line-height (~14px) so it sits centered
   * inside the cell without further x-tweaks. */
  writing-mode: vertical-rl;
  transform: rotate(180deg);
  max-height: 100px;
  font-size: 10px;
  font-weight: 500;
  color: var(--t1, #1E2A4A);
  letter-spacing: -0.005em;
  line-height: 1.2;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  cursor: default;
  transition: font-weight 0.2s ease, color 0.2s ease, opacity 0.2s ease;
}

/* Pack 7.31: label hover sync — bold + accent color when its bar is hovered */
.vc-lbl-cell.is-hovered .vc-lbl-text {
  font-weight: 700;
  color: var(--t1, #1E2A4A);
}
.vc-lbl-cell.is-dimmed .vc-lbl-text {
  opacity: 0.38;
}

/* Average line */
.vc-avg-line {
  position: absolute;
  left: 0;
  right: 0;
  height: 1px;
  background: repeating-linear-gradient(90deg, #5b54b8 0 6px, transparent 6px 10px);
  pointer-events: none;
  z-index: 3;
  animation: vcAvgFade 0.6s ease 0.5s both;
}

.vc-avg-lbl {
  position: absolute;
  right: 0;
  top: -16px;
  font-size: 9.5px;
  font-weight: 600;
  color: #5b54b8;
  background: var(--bg1, #fff);
  padding: 1px 6px;
  border-radius: 3px;
  font-feature-settings: "tnum";
}

/* Legend (now inline in header) */
.ed-card-meta {
  display: inline-flex;
  align-items: baseline;
  gap: 16px;
  flex-wrap: wrap;
  justify-content: flex-end;
}
.vc-legend {
  display: inline-flex;
  align-items: center;
  gap: 12px;
  font-size: 10px;
  color: var(--t1, #1E2A4A);
  font-weight: 500;
}
.vc-leg-item {
  display: inline-flex;
  align-items: center;
  gap: 5px;
}
.vc-leg-dot {
  width: 9px;
  height: 9px;
  border-radius: 2px;
  display: inline-block;
}

@keyframes vcBarGrow {
  0%   { transform: scaleY(0); }
  100% { transform: scaleY(1); }
}

@keyframes vcAvgFade {
  0%   { opacity: 0; }
  100% { opacity: 1; }
}
</style>
