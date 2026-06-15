<script setup lang="ts">
/**
 * ExecDashBottomMetrics — Pack 7.10 redesign (Variant C: funnel).
 *
 * 6 metric cells in a single row separated by thin dividers, each with
 * a micro-bar visualising the proportion. Replaces top-stripe accent with
 * the bar itself — one source of accent per cell, no dupes.
 *
 * Bars encode % of the relevant base:
 *   • Проектов / Задач         → 100% (anchor showing the totals exist)
 *   • Завершено · проекты      → done_proj / proj_count
 *   • Завершено · задачи       → done_tasks / task_count
 *   • Перенесено · задачи      → deferred_tasks / task_count
 *   • Средний прогресс         → avg_completion (already a %)
 *
 * Pack 7.30: каждая ячейка стала кликабельной — открывает KpiDrillModal
 * с соответствующим kind.
 *
 * Pack 7.30.1: цифры в ячейках теперь набегают (count-up 900ms, ease-out cubic,
 * с шагом 60ms между ячейками). Анимация перезапускается при смене года/данных.
 * Уважает prefers-reduced-motion.
 */
import { computed, onMounted, ref, watch, type Ref } from "vue";
import { useExecutiveDashboard } from "@/composables/useExecutiveDashboard";
import KpiDrillModal, { type KpiKind } from "@/components/UZA/KpiDrillModal.vue";

const exec = useExecutiveDashboard();
const m = computed(() => exec.data.value?.bottom_metrics);

function pct(num: number, den: number): number {
  if (!den) return 0;
  return Math.max(0, Math.min(100, Math.round((num / den) * 100)));
}

const projDonePct  = computed(() => m.value ? pct(m.value.done_proj,  m.value.proj_count) : 0);
const taskDonePct  = computed(() => m.value ? pct(m.value.done_tasks, m.value.task_count) : 0);
const taskDeferPct = computed(() => m.value ? pct(m.value.deferred_tasks, m.value.task_count) : 0);

// Полоски «Проектов»/«Задач» теперь несут смысл: относительный объём
// (проекты против задач), отмасштабированный к большему из двух. Раньше обе
// были width:100% и выглядели одинаково-бессмысленно.
const maxTotal     = computed(() => Math.max(1, m.value?.proj_count || 0, m.value?.task_count || 0));
const projTotalPct = computed(() => m.value ? pct(m.value.proj_count, maxTotal.value) : 0);
const taskTotalPct = computed(() => m.value ? pct(m.value.task_count, maxTotal.value) : 0);
// Проекты состоят из задач → среднее число задач на проект (иерархия).
const avgTasksPerProj = computed(() => {
  if (!m.value || !m.value.proj_count) return "0";
  return (m.value.task_count / m.value.proj_count).toFixed(1);
});

const deferredProjVisible = computed(() => (m.value?.deferred_proj ?? 0) > 0);

// ─── Drill modal state (Pack 7.30) ───
const drillKind = ref<KpiKind | null>(null);
function openDrill(kind: KpiKind) { drillKind.value = kind; }
function closeDrill() { drillKind.value = null; }

// ─── Count-up animation (Pack 7.30.1) ───
// 9 анимируемых рефов: 6 цифр + 3 процента-суффикса
const av = {
  proj:         ref(0),
  tasks:        ref(0),
  doneProj:     ref(0),
  doneTasks:    ref(0),
  deferred:     ref(0),
  avg:          ref(0),
  projDonePct:  ref(0),
  taskDonePct:  ref(0),
  taskDeferPct: ref(0),
};

const reducedMotion = typeof window !== "undefined"
  && typeof window.matchMedia === "function"
  && window.matchMedia("(prefers-reduced-motion: reduce)").matches;

function tweenTo(target: Ref<number>, value: number, duration = 900, delay = 0) {
  if (target.value === value) return;
  if (reducedMotion) { target.value = value; return; }
  const startVal = target.value;
  const t0 = performance.now() + delay;
  function step(now: number) {
    if (now < t0) { requestAnimationFrame(step); return; }
    const t = Math.min(1, (now - t0) / duration);
    const eased = 1 - Math.pow(1 - t, 3);
    target.value = Math.round(startVal + (value - startVal) * eased);
    if (t < 1) requestAnimationFrame(step);
  }
  requestAnimationFrame(step);
}

function runCountUp() {
  if (!m.value) return;
  // Шахматный stagger по 60ms — синхронно с pour-in анимацией баров
  tweenTo(av.proj,         m.value.proj_count,         900,   0);
  tweenTo(av.tasks,        m.value.task_count,         900,  60);
  tweenTo(av.doneProj,     m.value.done_proj,          900, 120);
  tweenTo(av.projDonePct,  projDonePct.value,          900, 120);
  tweenTo(av.doneTasks,    m.value.done_tasks,         900, 180);
  tweenTo(av.taskDonePct,  taskDonePct.value,          900, 180);
  tweenTo(av.deferred,     m.value.deferred_tasks,     900, 240);
  tweenTo(av.taskDeferPct, taskDeferPct.value,         900, 240);
  tweenTo(av.avg,          m.value.avg_completion,     900, 300);
}

onMounted(runCountUp);
// Перезапуск при загрузке новых данных (смена года, рефреш)
watch(m, runCountUp);
</script>

<template>
  <div v-if="m" class="va-bot">
    <!-- 1. Проектов всего -->
    <div class="va-cell va-cell-work" :title="`${m.proj_count} проектов · ${m.task_count} задач · ≈${avgTasksPerProj} задач на проект`">
      <div class="va-lbl">Портфель работ · проекты содержат задачи</div>
      <div class="va-work-row">
        <button type="button" class="va-work-node va-work-btn" @click="openDrill('projects')">
          <span class="va-work-num">{{ av.proj }}</span>
          <span class="va-work-u">проектов</span>
        </button>
        <span class="va-work-link">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M5 12h14M13 6l6 6-6 6"/></svg>
          <span class="va-work-ratio">≈{{ avgTasksPerProj }}/проект</span>
        </span>
        <button type="button" class="va-work-node va-work-btn" @click="openDrill('tasks')">
          <span class="va-work-num">{{ av.tasks }}</span>
          <span class="va-work-u">задач</span>
        </button>
      </div>
      <!-- Воронка: проекты (уже) → задачи (полная ширина) -->
      <div class="va-work-bars">
        <div class="va-work-bar"><span :style="{ width: projTotalPct + '%', background: '#7F77DD' }"></span></div>
        <div class="va-work-bar"><span :style="{ width: taskTotalPct + '%', background: '#A79CF4' }"></span></div>
      </div>
    </div>

    <!-- 3. Завершено · проекты -->
    <button type="button" class="va-cell va-cell-btn" @click="openDrill('done_projects')" :title="'Подробнее: Завершённые проекты'">
      <div class="va-lbl">Завершено · проекты</div>
      <div class="va-num-row">
        <span class="va-num va-num-green">{{ av.doneProj }}</span>
        <span class="va-pct">{{ av.projDonePct }}%</span>
      </div>
      <div class="va-bar">
        <div class="va-bar-fill" :style="{ width: projDonePct + '%', background: '#1D9E75' }"></div>
      </div>
    </button>

    <!-- 4. Завершено · задачи -->
    <button type="button" class="va-cell va-cell-btn" @click="openDrill('done_tasks')" :title="'Подробнее: Завершённые задачи'">
      <div class="va-lbl">Завершено · задачи</div>
      <div class="va-num-row">
        <span class="va-num va-num-green">{{ av.doneTasks }}</span>
        <span class="va-pct">{{ av.taskDonePct }}%</span>
      </div>
      <div class="va-bar">
        <div class="va-bar-fill" :style="{ width: taskDonePct + '%', background: '#1D9E75' }"></div>
      </div>
    </button>

    <!-- 5. Перенесено · задачи (с suffix proj если > 0) -->
    <button type="button" class="va-cell va-cell-btn" @click="openDrill('deferred_tasks')" :title="'Подробнее: Перенесённые задачи'">
      <div class="va-lbl">
        Перенесено · задачи
        <span v-if="deferredProjVisible" class="va-lbl-extra">+ {{ m.deferred_proj }} пр.</span>
      </div>
      <div class="va-num-row">
        <span class="va-num va-num-purple">{{ av.deferred }}</span>
        <span class="va-pct">{{ av.taskDeferPct }}%</span>
      </div>
      <div class="va-bar">
        <div class="va-bar-fill" :style="{ width: taskDeferPct + '%', background: '#7F77DD' }"></div>
      </div>
    </button>

    <!-- 6. Средний прогресс -->
    <button type="button" class="va-cell va-cell-btn" @click="openDrill('avg_progress')" :title="'Подробнее: Средний прогресс'">
      <div class="va-lbl">Средний прогресс</div>
      <div class="va-num-row">
        <span class="va-num va-num-amber">{{ av.avg }}%</span>
      </div>
      <div class="va-bar">
        <div class="va-bar-fill" :style="{ width: m.avg_completion + '%', background: '#BA7517' }"></div>
      </div>
    </button>

    <!-- KPI drill-down modal (Pack 7.30) -->
    <KpiDrillModal
      v-if="drillKind"
      :kind="drillKind"
      @close="closeDrill"
    />
  </div>
</template>

<style scoped>
/* Outer container — flex one-row layout with thin internal dividers */
.va-bot {
  display: flex;
  align-items: stretch;
  background: var(--bg1, #fff);
  border-radius: 12px;
  border: 1px solid rgba(0, 0, 0, 0.05);
  padding: 14px 6px;
  box-shadow: 0 4px 14px rgba(15, 23, 60, 0.04);
}

.va-cell {
  flex: 1;
  min-width: 0;
  padding: 6px 14px;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

/* Pack 7.30: cells now are buttons — strip native styling, add hover affordance */
.va-cell-btn {
  background: transparent;
  border: none;
  text-align: left;
  cursor: pointer;
  font-family: inherit;
  color: inherit;
  border-radius: 8px;
  position: relative;
  transition: background 0.15s ease;
}
.va-cell-btn:hover {
  background: rgba(127, 119, 221, 0.04);
}
.va-cell-btn:focus-visible {
  outline: 2px solid rgba(127, 119, 221, 0.5);
  outline-offset: -2px;
}

/* Thin internal divider between cells */
.va-cell + .va-cell {
  border-left: 0.5px solid rgba(15, 23, 60, 0.08);
}

.va-lbl {
  font-size: 9.5px;
  color: var(--t3, var(--t-muted));
  font-weight: 500;
  letter-spacing: 0.06em;
  text-transform: uppercase;
  line-height: 1.3;
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
  align-items: baseline;
}

.va-lbl-extra {
  font-size: 9px;
  color: rgba(127, 119, 221, 0.85);
  font-weight: 500;
  letter-spacing: 0.04em;
  text-transform: none;
}

.va-num-row {
  display: flex;
  align-items: baseline;
  gap: 8px;
  line-height: 1;
}

.va-num {
  font-size: 26px;
  font-weight: 500;
  color: var(--t1, #1E2A4A);
  letter-spacing: -0.025em;
  line-height: 1;
  font-feature-settings: "tnum";
}

.va-num-green  { color: var(--green); }
.va-num-purple { color: #7F77DD; }
.va-num-amber  { color: var(--sev-mid); }

/* ── «Портфель работ»: проекты → задачи (воронка-иерархия) ── */
.va-cell-work { flex: 1.7; }
.va-work-row { display: flex; align-items: center; gap: 10px; }
.va-work-node {
  display: inline-flex; flex-direction: column; align-items: flex-start; gap: 1px;
  background: transparent; border: none; padding: 2px 4px; margin: -2px -4px;
  border-radius: 7px; cursor: pointer; font-family: inherit; transition: background .14s;
}
.va-work-btn:hover { background: rgba(127, 119, 221, 0.08); }
.va-work-num { font-size: 26px; font-weight: 500; color: var(--t1, #1E2A4A); letter-spacing: -0.025em; line-height: 1; font-feature-settings: "tnum"; }
.va-work-u { font-size: 9.5px; color: var(--t3, var(--t-muted)); text-transform: uppercase; letter-spacing: 0.06em; font-weight: 500; }
.va-work-link { display: inline-flex; flex-direction: column; align-items: center; gap: 1px; color: #7F77DD; flex-shrink: 0; }
.va-work-link svg { width: 18px; height: 18px; opacity: .8; }
.va-work-ratio { font-size: 9px; font-weight: 600; color: #7F77DD; white-space: nowrap; font-feature-settings: "tnum"; }
.va-work-bars { display: flex; flex-direction: column; gap: 3px; margin-top: 4px; }
.va-work-bar { height: 4px; background: rgba(15, 23, 60, 0.06); border-radius: 2px; overflow: hidden; }
.va-work-bar > span {
  display: block; height: 100%; border-radius: 2px; transform-origin: left center;
  animation: vaBarPour 700ms var(--ease-out) both;
  transition: width 900ms var(--ease-out);
}

.va-pct {
  font-size: 12px;
  color: var(--t3, var(--t-muted));
  font-weight: 400;
  font-feature-settings: "tnum";
}

/* Micro-bar — pour-in animation matches exec-animations.css uzaBarPour */
.va-bar {
  height: 4px;
  background: rgba(15, 23, 60, 0.06);
  border-radius: 2px;
  overflow: hidden;
  position: relative;
  margin-top: 2px;
}

.va-bar-fill {
  position: absolute;
  top: 0;
  left: 0;
  bottom: 0;
  border-radius: 2px;
  transform-origin: left center;
  animation: vaBarPour 700ms var(--ease-out) both;
  /* 2026-05-26: smooth width transition on year switch (was hard cut). */
  transition: width 900ms var(--ease-out);
}

@keyframes vaBarPour {
  from { transform: scaleX(0); opacity: 0; }
  to   { transform: scaleX(1); opacity: 1; }
}

/* Stagger fill animation: each cell delayed by 80ms */
.va-cell:nth-child(1) .va-bar-fill { animation-delay: 0ms; }
.va-cell:nth-child(2) .va-bar-fill { animation-delay: 80ms; }
.va-cell:nth-child(3) .va-bar-fill { animation-delay: 160ms; }
.va-cell:nth-child(4) .va-bar-fill { animation-delay: 240ms; }
.va-cell:nth-child(5) .va-bar-fill { animation-delay: 320ms; }
.va-cell:nth-child(6) .va-bar-fill { animation-delay: 400ms; }

/* Responsive: at narrow viewports wrap to two rows of 3 */
@media (max-width: 1100px) {
  .va-bot {
    flex-wrap: wrap;
    padding: 10px 6px;
  }
  .va-cell {
    flex: 1 1 calc(33.333% - 1px);
    min-width: 0;
  }
  .va-cell:nth-child(4) {
    border-left: 0.5px solid transparent;
  }
  .va-cell:nth-child(n+4) {
    margin-top: 8px;
    padding-top: 12px;
    border-top: 0.5px solid rgba(15, 23, 60, 0.06);
  }
}

@media (max-width: 700px) {
  .va-cell {
    flex: 1 1 calc(50% - 1px);
  }
  .va-cell:nth-child(3),
  .va-cell:nth-child(5) {
    border-left: 0.5px solid transparent;
  }
  .va-cell:nth-child(n+3) {
    margin-top: 8px;
    padding-top: 12px;
    border-top: 0.5px solid rgba(15, 23, 60, 0.06);
  }
}

@media (prefers-reduced-motion: reduce) {
  .va-bar-fill {
    animation: none !important;
  }
}
</style>
