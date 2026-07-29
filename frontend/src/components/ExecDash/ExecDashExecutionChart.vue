<script setup lang="ts">
/**
 * ExecDashExecutionChart — Row 2 правая половина.
 * Вертикальный бар-чарт по компаниям (с задачами), сортировка по pct desc.
 * Цвет бара по threshold: ≥60 green / 30-59 amber / <30 red.
 * Референс-линии: средний факт и средний план по портфелю (значения из данных).
 *
 * Pure CSS implementation, без Chart.js (легковесно).
 */
import { computed, onMounted, ref } from "vue";
import { useExecutiveDashboard } from "@/composables/useExecutiveDashboard";
import { useCompaniesStore } from "@/stores/companies";
import { resolveCompanyDisplayName } from "@/utils/displayNames";
import UzaStateBlock from "@/components/UZA/UzaStateBlock.vue";
import { useI18n } from "@/composables/useI18n";

const { t } = useI18n();
const exec = useExecutiveDashboard();
const companiesStore = useCompaniesStore();

// Pack 7.12: ensure companies cache is loaded so we can resolve display names
// (name_short || name_ru) by company_id, regardless of what the chart endpoint sends.
onMounted(() => { void companiesStore.ensureLoaded(); });

const rows = computed(() => exec.data.value?.execution_chart || []);
const avgPct = computed(() => exec.data.value?.avg_execution_pct || 0);
// Средний план по портфелю (среднее plan_pct компаний) — вторая референс-линия.
const avgPlanPct = computed(() => {
  const ps = rows.value.map((c: any) => Number(c.plan_pct ?? 0));
  if (!ps.length) return 0;
  return Math.round(ps.reduce((a, b) => a + b, 0) / ps.length);
});

// Pack 7.31: hover state — единый индекс, синхронизирующий подсветку
// бара и его подписи (поскольку bar и label живут в разных flex-контейнерах).
const hoveredIdx = ref<number | null>(null);
function onBarEnter(i: number) { hoveredIdx.value = i; }
function onBarLeave() { hoveredIdx.value = null; }

const subTitle = computed(() => {
  if (!rows.value.length) return "";
  return t("{n} компаний · ранжирование по % задач", { n: rows.value.length });
});

function barColor(pct: number): string {
  if (pct >= 60) return "#5DC093";  // green
  if (pct >= 30) return "#EFB373";  // amber
  return "#E2807F";                 // red
}

/**
 * Дельта к СОБСТВЕННОМУ плану компании (пп): факт − план_этой_компании.
 * Знаковая: > 0 опережение, < 0 отставание. null — если у компании нет плана.
 * Считается от плана конкретной компании (ghost-бар), НЕ от среднего плана.
 */
function planGap(c: { pct: number; plan_pct?: number | null }): number | null {
  const plan = Number(c.plan_pct ?? 0);
  if (!(plan > 0)) return null;
  return Math.round(c.pct - plan);
}
/** Подпись дельты со знаком: «+5%», «−8%», «0%». */
function gapText(c: { pct: number; plan_pct?: number | null }): string {
  const g = planGap(c);
  if (g === null) return "";
  return g > 0 ? `+${g}%` : `${g}%`;   // отрицательное число уже несёт «−»
}
/** Класс для отставания (красный). */
function gapClass(c: { pct: number; plan_pct?: number | null }): string {
  const g = planGap(c);
  return g !== null && g < 0 ? "neg" : "";
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

/**
 * Строка данных бара (факт/план/перевыполнение/rank) — единый источник
 * для нативного :title и a11y :aria-label, чтобы они не расходились.
 */
function barDataText(c: { company_id: string; name: string; pct: number; plan_pct?: number | null }, i: number): string {
  const g = planGap(c);
  const gapStr = g === null
    ? ""
    : " · " + t("к плану {g} пп ({dir})", {
        g: `${g > 0 ? "+" : ""}${g}`,
        dir: g >= 0 ? t("опережение") : t("отставание"),
      });
  const base = t("{name} · факт {fact}% · план {plan}%", {
    name: companyFullName(c), fact: c.pct, plan: c.plan_pct ?? 0,
  });
  return `${base}${gapStr} · ` + t("{i} из {n}", { i: i + 1, n: rows.value.length });
}
</script>

<template>
  <div class="ed-card">
    <!-- Header (with inline legend) -->
    <div class="ed-card-ttl">
      <span>{{ t("Рейтинг компаний по исполнению") }}</span>
      <span class="ed-card-meta">
        <span class="sub">{{ subTitle }}</span>
        <span class="vc-legend">
          <span class="vc-leg-item"><span class="vc-leg-dot" style="background: #5DC093" />≥60%</span>
          <span class="vc-leg-item"><span class="vc-leg-dot" style="background: #EFB373" />30–59%</span>
          <span class="vc-leg-item"><span class="vc-leg-dot" style="background: #E2807F" />&lt;30%</span>
          <span class="vc-leg-item"><span class="vc-leg-ghost" />{{ t("план") }}</span>
        </span>
      </span>
    </div>

    <UzaStateBlock v-if="!rows.length" state="empty" variant="inline" :text="t('Нет данных о компаниях с задачами для FY {year}', { year: exec.year.value })" />

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
            role="img"
            :aria-label="barDataText(c, i)"
            :title="barDataText(c, i)"
          >
            <div
              v-if="planGap(c) !== null"
              class="vc-bar-over"
              :class="gapClass(c)"
              :title="(planGap(c) as number) >= 0
                ? t('Опережение собственного плана: {n} пп', { n: Math.abs(planGap(c) as number) })
                : t('Отставание собственного плана: {n} пп', { n: Math.abs(planGap(c) as number) })"
            >{{ gapText(c) }}</div>
            <div class="vc-bar-val">{{ c.pct }}%</div>
            <!-- План (прозрачный бар по дедлайнам) — позади факт-бара -->
            <div
              class="vc-bar-plan"
              :style="{ '--ph': (c.plan_pct ?? 0) + '%' }"
            />
            <div
              class="vc-bar"
              :style="{ '--h': c.pct + '%', '--bg': barColor(c.pct) }"
            />
          </div>
        </div>

        <!-- Average PLAN line (purple) -->
        <div
          v-if="avgPlanPct > 0"
          class="vc-plan-line"
          :style="{ bottom: `${avgPlanPct}%` }"
        >
          <span class="vc-plan-lbl">{{ t("Ср. план") }} {{ avgPlanPct }}%</span>
        </div>

        <!-- Average FACT line -->
        <div
          class="vc-avg-line"
          :style="{ bottom: `${avgPct}%` }"
        >
          <span class="vc-avg-lbl">{{ t("Ср. факт") }} {{ avgPct }}%</span>
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
  color: #6B6A66;
  font-weight: 500;
  text-transform: none;
  letter-spacing: 0;
}

.ed-empty {
  padding: 60px 20px;
  text-align: center;
  color: #6B6A66;
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
  color: #6B6A66;
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

/* Перевыполнение плана — зелёный «+N%» над значением факта */
.vc-bar-over {
  font-size: 8.5px;
  font-weight: 700;
  color: #1D9E75;
  font-feature-settings: "tnum";
  line-height: 1;
  margin-bottom: 1px;
  white-space: nowrap;
  position: relative;
  z-index: 3;
  transition: font-size 0.2s ease, transform 0.2s ease, opacity 0.2s ease;
  transform-origin: center bottom;
}
/* Отставание от собственного плана — красный «−N%» */
.vc-bar-over.neg { color: #C0504D; }
.vc-bar-col.is-hovered .vc-bar-over { font-size: 10px; transform: scale(1.1); }
.vc-bar-col.is-dimmed .vc-bar-over { opacity: 0.38; }

.vc-bar-val {
  font-size: 9px;
  font-weight: 600;
  color: var(--t1, #1E2A4A);
  font-feature-settings: "tnum";
  margin-bottom: 3px;
  letter-spacing: -0.01em;
  position: relative;
  z-index: 3;          /* подпись поверх план-бара */
  transition: font-size 0.2s ease, color 0.2s ease, transform 0.2s ease, opacity 0.2s ease;
  transform-origin: center bottom;
}

.vc-bar {
  width: 100%;
  max-width: 22px;
  height: var(--h, 0%);
  background-color: var(--bg, var(--t-muted));
  /* Премиум: верхний светлый хайлайт поверх цвета бара → объёмный «глянец». */
  background-image: linear-gradient(180deg, rgba(255, 255, 255, 0.30) 0%, rgba(255, 255, 255, 0) 55%);
  border-radius: 5px 5px 0 0;
  animation: vcBarGrow 0.7s var(--ease-standard) var(--d, 0ms) both;
  transform-origin: left center;
  transform-origin: bottom;
  position: relative;
  z-index: 2;              /* факт-бар поверх плана */
  /* 2026-05-26: smooth height transition on year switch (was hard cut to new). */
  transition: filter 0.2s ease, opacity 0.2s ease, box-shadow 0.2s ease, max-width 0.2s ease,
              height 900ms var(--ease-out);
}

/* План-бар (по дедлайнам) — прозрачный «таргет» позади факт-бара.
 * Та же шкала и baseline, что у факт-бара; верхняя пунктирная грань
 * отмечает плановый уровень. Виден там, где план > факта (отставание). */
.vc-bar-plan {
  position: absolute;
  bottom: 0;
  left: 50%;
  transform: translateX(-50%);
  width: 100%;
  max-width: 22px;
  height: var(--ph, 0%);
  background: rgba(124, 111, 247, 0.10);
  border: 1px dashed rgba(124, 111, 247, 0.50);
  border-bottom: none;
  border-radius: 4px 4px 0 0;
  z-index: 1;
  pointer-events: none;
  transition: height 900ms var(--ease-out);
}
.vc-bar-col.is-dimmed .vc-bar-plan { opacity: 0.32; }

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

/* Average PLAN line — светло-фиолетовая (цвет ghost-плана), подпись слева */
.vc-plan-line {
  position: absolute;
  left: 0;
  right: 0;
  height: 1px;
  background: repeating-linear-gradient(90deg, rgba(124, 111, 247, 0.85) 0 5px, transparent 5px 9px);
  pointer-events: none;
  z-index: 3;
  animation: vcAvgFade 0.6s ease 0.6s both;
}
.vc-plan-lbl {
  position: absolute;
  left: 0;
  top: -16px;
  font-size: 9.5px;
  font-weight: 600;
  color: #7C6FF7;
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
.vc-leg-ghost {
  width: 9px;
  height: 9px;
  border-radius: 2px;
  display: inline-block;
  background: rgba(124, 111, 247, 0.10);
  border: 1px dashed rgba(124, 111, 247, 0.50);
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
