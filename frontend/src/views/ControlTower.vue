<script setup lang="ts">
/**
 * ControlTower.vue — «Контрольная вышка».
 *
 * Сплит-экран сравнения двух периодов (месяц/квартал) за год: слева период A,
 * справа период B, по центру — дельта. Для задач и проектов: план (дедлайн в
 * периоде) / факт (выполнено) / % / просрочка. Снизу — общий график всех
 * периодов с подсветкой выбранных.
 *
 * Дефолт 2026 — текущий год отслеживания. Данные: GET /monitoring/timeline.
 */
import { ref, computed, onMounted, watch } from "vue";
import { api } from "@/api/client";

interface Period { key: number; label: string; label_full: string; plan: number; done: number; pct: number; zone: string; }
interface Entity { total: number; done: number; pct: number; overdue: number; periods: Period[]; }
interface Timeline { year: number; granularity: string; tasks: Entity; projects: Entity; comments: { total: number }; }

const timeline = ref<Timeline | null>(null);
const loading = ref(true);
const error = ref<string | null>(null);

const year = ref<number>(2026);
type Gran = "month" | "quarter";
const gran = ref<Gran>("quarter");
const idxA = ref(0);
const idxB = ref(1);
const YEARS = [2026, 2025];

async function load() {
  loading.value = true;
  error.value = null;
  try {
    const { data } = await api.get<Timeline>(`/monitoring/timeline/${year.value}`, { params: { granularity: gran.value } });
    timeline.value = data;
    const n = data.tasks.periods.length;
    if (idxA.value >= n) idxA.value = 0;
    if (idxB.value >= n) idxB.value = Math.min(1, n - 1);
  } catch (e: any) {
    error.value = e?.response?.data?.detail || e?.message || "Ошибка загрузки";
  } finally {
    loading.value = false;
  }
}
onMounted(load);
watch([year, gran], load);

// ─── helpers ────────────────────────────────────────────────────
function pctColor(pct: number): string {
  if (pct >= 100) return "#1D9E75";
  if (pct >= 90) return "#7F77DD";
  if (pct >= 75) return "#EF9F27";
  return "#E24B4A";
}

interface Side { label: string; tasks: Period; projects: Period; }
function sideAt(i: number): Side | null {
  const t = timeline.value;
  if (!t) return null;
  const tp = t.tasks.periods[i], pp = t.projects.periods[i];
  if (!tp) return null;
  return { label: tp.label_full, tasks: tp, projects: pp };
}
const sideA = computed(() => sideAt(idxA.value));
const sideB = computed(() => sideAt(idxB.value));

function deltaTone(d: number): string {
  if (d > 0) return "#1D9E75";
  if (d < 0) return "#E24B4A";
  return "#888780";
}
function deltaStr(d: number): string {
  return (d > 0 ? "+" : "") + d;
}

const periodOptions = computed(() =>
  (timeline.value?.tasks.periods || []).map((p, i) => ({ i, label: p.label_full })),
);
const maxPlan = computed(() => Math.max(1, ...(timeline.value?.tasks.periods.map((p) => p.plan) || [1])));
function barH(v: number): number { return Math.round((v / maxPlan.value) * 120); }
</script>

<template>
  <div class="ct-page">
    <!-- TOPBAR -->
    <div class="ct-topbar">
      <div>
        <div class="ct-eyebrow">МОНИТОРИНГ ПОРТФЕЛЯ · ОТСЛЕЖИВАНИЕ С {{ year }}</div>
        <h1 class="ct-title">Контрольная вышка</h1>
        <div class="ct-sub">Сравнение периодов — задачи и проекты, план и факт</div>
      </div>
      <div class="ct-controls">
        <div class="ct-seg">
          <button class="ct-seg-btn" :class="{ on: gran === 'month' }" @click="gran = 'month'">Месяцы</button>
          <button class="ct-seg-btn" :class="{ on: gran === 'quarter' }" @click="gran = 'quarter'">Кварталы</button>
        </div>
        <select v-model.number="year" class="ct-select">
          <option v-for="y in YEARS" :key="y" :value="y">{{ y }}</option>
        </select>
      </div>
    </div>

    <div v-if="loading" class="ct-state">Загрузка…</div>
    <div v-else-if="error" class="ct-state ct-err">{{ error }}</div>

    <template v-else-if="timeline && sideA && sideB">
      <!-- ═══════════ СПЛИТ-СРАВНЕНИЕ ═══════════ -->
      <div class="ct-split">
        <!-- LEFT -->
        <div class="ct-panel">
          <div class="ct-panel-head">
            <span class="ct-panel-tag tag-a">Период A</span>
            <select v-model.number="idxA" class="ct-select sm">
              <option v-for="o in periodOptions" :key="o.i" :value="o.i">{{ o.label }}</option>
            </select>
          </div>
          <div class="ct-metric-block">
            <div class="ct-mb-label">Задачи</div>
            <div class="ct-mb-val" :style="{ color: pctColor(sideA.tasks.pct) }">{{ sideA.tasks.pct }}<span>%</span></div>
            <div class="ct-mb-bar"><span :style="{ width: Math.min(100, sideA.tasks.pct) + '%', background: pctColor(sideA.tasks.pct) }" /></div>
            <div class="ct-mb-sub">{{ sideA.tasks.done }} из {{ sideA.tasks.plan }} выполнено</div>
          </div>
          <div class="ct-metric-block">
            <div class="ct-mb-label">Проекты</div>
            <div class="ct-mb-val" :style="{ color: pctColor(sideA.projects.pct) }">{{ sideA.projects.pct }}<span>%</span></div>
            <div class="ct-mb-bar"><span :style="{ width: Math.min(100, sideA.projects.pct) + '%', background: pctColor(sideA.projects.pct) }" /></div>
            <div class="ct-mb-sub">{{ sideA.projects.done }} из {{ sideA.projects.plan }} завершено</div>
          </div>
        </div>

        <!-- CENTER DELTA -->
        <div class="ct-delta">
          <div class="ct-delta-vs">VS</div>
          <div class="ct-delta-item">
            <span class="ct-delta-cap">Задачи</span>
            <span class="ct-delta-val" :style="{ color: deltaTone(sideB.tasks.pct - sideA.tasks.pct) }">
              {{ deltaStr(sideB.tasks.pct - sideA.tasks.pct) }}<small>пп</small>
            </span>
          </div>
          <div class="ct-delta-item">
            <span class="ct-delta-cap">Проекты</span>
            <span class="ct-delta-val" :style="{ color: deltaTone(sideB.projects.pct - sideA.projects.pct) }">
              {{ deltaStr(sideB.projects.pct - sideA.projects.pct) }}<small>пп</small>
            </span>
          </div>
          <div class="ct-delta-hint">B относительно A</div>
        </div>

        <!-- RIGHT -->
        <div class="ct-panel">
          <div class="ct-panel-head">
            <span class="ct-panel-tag tag-b">Период B</span>
            <select v-model.number="idxB" class="ct-select sm">
              <option v-for="o in periodOptions" :key="o.i" :value="o.i">{{ o.label }}</option>
            </select>
          </div>
          <div class="ct-metric-block">
            <div class="ct-mb-label">Задачи</div>
            <div class="ct-mb-val" :style="{ color: pctColor(sideB.tasks.pct) }">{{ sideB.tasks.pct }}<span>%</span></div>
            <div class="ct-mb-bar"><span :style="{ width: Math.min(100, sideB.tasks.pct) + '%', background: pctColor(sideB.tasks.pct) }" /></div>
            <div class="ct-mb-sub">{{ sideB.tasks.done }} из {{ sideB.tasks.plan }} выполнено</div>
          </div>
          <div class="ct-metric-block">
            <div class="ct-mb-label">Проекты</div>
            <div class="ct-mb-val" :style="{ color: pctColor(sideB.projects.pct) }">{{ sideB.projects.pct }}<span>%</span></div>
            <div class="ct-mb-bar"><span :style="{ width: Math.min(100, sideB.projects.pct) + '%', background: pctColor(sideB.projects.pct) }" /></div>
            <div class="ct-mb-sub">{{ sideB.projects.done }} из {{ sideB.projects.plan }} завершено</div>
          </div>
        </div>
      </div>

      <!-- ═══════════ КОНТЕКСТ: все периоды ═══════════ -->
      <div class="ct-chart-card">
        <div class="ct-chart-head">
          <span class="ct-chart-eyebrow">ВСЕ ПЕРИОДЫ · ЗАДАЧИ</span>
          <span class="ct-chart-title">Год {{ year }} — план и факт, выбранные периоды подсвечены</span>
        </div>
        <div class="ct-chart" :class="{ q: gran === 'quarter' }">
          <div v-for="(p, i) in timeline.tasks.periods" :key="p.key" class="ct-bar-col"
               :class="{ selA: i === idxA, selB: i === idxB }">
            <div class="ct-bar-pct" :style="{ color: p.plan ? pctColor(p.pct) : '#C7C9D1' }">{{ p.plan ? p.pct + '%' : '·' }}</div>
            <div class="ct-bar-wrap">
              <div class="ct-bar-track" :style="{ height: Math.max(4, barH(p.plan)) + 'px' }">
                <div class="ct-bar-fill" :style="{ height: (p.plan ? (p.done / p.plan * 100) : 0) + '%', background: pctColor(p.pct) }" />
              </div>
            </div>
            <div class="ct-bar-count">{{ p.done }}/{{ p.plan }}</div>
            <div class="ct-bar-label">{{ p.label }}</div>
          </div>
        </div>
      </div>

      <!-- ═══════════ НОТА ОБ ОТСЛЕЖИВАНИИ ═══════════ -->
      <div class="ct-track-note">
        <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>
        </svg>
        <div>
          <b>Отслеживание прогресса по срезам — со {{ year }} года.</b>
          Сейчас сравнение строится по дедлайнам периодов (факт на текущий момент). Чтобы видеть,
          <i>как менялось исполнение во времени</i> (срез на конец каждого месяца/квартала и динамика «было → стало»),
          нужно включить фиксацию срезов с сегодняшнего дня — следующий шаг.
        </div>
      </div>
    </template>
  </div>
</template>

<style scoped>
.ct-page { padding: 22px 26px 60px; max-width: 1440px; margin: 0 auto; color: #1E2A4A; }
.ct-topbar { display: flex; align-items: flex-start; justify-content: space-between; gap: 20px; flex-wrap: wrap; padding: 18px 22px; background: linear-gradient(180deg,#fff,#FAFAFC); border: 1px solid #EEF0F4; border-radius: 14px; box-shadow: 0 8px 24px rgba(15,23,60,.05); }
.ct-eyebrow { font-size: 10px; font-weight: 500; letter-spacing: .08em; color: #7F77DD; }
.ct-title { margin: 5px 0 0; font-size: 22px; font-weight: 500; letter-spacing: -.02em; }
.ct-sub { margin-top: 3px; font-size: 12.5px; color: #888780; }
.ct-controls { display: flex; align-items: center; gap: 10px; }
.ct-seg { display: inline-flex; background: #F1F2F6; border-radius: 9px; padding: 3px; }
.ct-seg-btn { border: 0; background: transparent; cursor: pointer; font-size: 12px; font-weight: 500; color: #6B7280; padding: 7px 16px; border-radius: 7px; transition: all .16s cubic-bezier(.34,1.2,.64,1); }
.ct-seg-btn.on { background: #fff; color: #534AB7; box-shadow: 0 2px 6px rgba(15,23,60,.10); }
.ct-select { appearance: none; border: 1px solid #E5E7EB; background: #fff; border-radius: 8px; padding: 8px 14px; font-size: 12.5px; font-weight: 500; color: #1E2A4A; cursor: pointer; outline: none; }
.ct-select.sm { padding: 7px 12px; font-size: 12.5px; }
.ct-select:focus { border-color: #7F77DD; box-shadow: 0 0 0 3px rgba(127,119,221,.12); }
.ct-state { padding: 60px; text-align: center; color: #888780; font-size: 13px; }
.ct-err { color: #E24B4A; }

/* SPLIT */
.ct-split { display: grid; grid-template-columns: 1fr auto 1fr; gap: 16px; margin-top: 16px; align-items: stretch; }
.ct-panel { background: #fff; border: 1px solid #EEF0F4; border-radius: 14px; box-shadow: 0 8px 24px rgba(15,23,60,.05); padding: 18px 20px; }
.ct-panel-head { display: flex; align-items: center; justify-content: space-between; margin-bottom: 16px; }
.ct-panel-tag { font-size: 10px; font-weight: 500; letter-spacing: .06em; text-transform: uppercase; padding: 4px 10px; border-radius: 8px; }
.ct-panel-tag.tag-a { color: #534AB7; background: rgba(127,119,221,.12); }
.ct-panel-tag.tag-b { color: #378ADD; background: rgba(55,138,221,.12); }
.ct-metric-block { padding: 14px 0; border-top: 1px solid #F5F6F8; }
.ct-metric-block:first-of-type { border-top: 0; }
.ct-mb-label { font-size: 10px; font-weight: 500; letter-spacing: .05em; text-transform: uppercase; color: #888780; }
.ct-mb-val { margin-top: 6px; font-size: 32px; font-weight: 400; letter-spacing: -.025em; line-height: 1; }
.ct-mb-val span { font-size: 16px; color: #888780; font-weight: 500; }
.ct-mb-bar { margin-top: 10px; height: 6px; border-radius: 4px; background: #F1F2F6; overflow: hidden; }
.ct-mb-bar > span { display: block; height: 100%; border-radius: 4px; transition: width .6s cubic-bezier(.34,1.2,.64,1); }
.ct-mb-sub { margin-top: 8px; font-size: 11.5px; color: #888780; }

/* CENTER DELTA */
.ct-delta { display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 12px; min-width: 120px; padding: 10px; }
.ct-delta-vs { font-size: 13px; font-weight: 500; color: #C7C9D1; letter-spacing: .1em; }
.ct-delta-item { display: flex; flex-direction: column; align-items: center; }
.ct-delta-cap { font-size: 10px; text-transform: uppercase; letter-spacing: .05em; color: #A0A0A8; }
.ct-delta-val { font-size: 24px; font-weight: 400; letter-spacing: -.02em; font-variant-numeric: tabular-nums; }
.ct-delta-val small { font-size: 11px; margin-left: 2px; }
.ct-delta-hint { font-size: 10px; color: #B4B2A9; }

/* CHART */
.ct-chart-card { margin-top: 18px; background: #fff; border: 1px solid #EEF0F4; border-radius: 14px; box-shadow: 0 8px 24px rgba(15,23,60,.05); padding: 18px 22px 16px; }
.ct-chart-head { margin-bottom: 16px; }
.ct-chart-eyebrow { font-size: 10px; font-weight: 500; letter-spacing: .07em; color: #7F77DD; }
.ct-chart-title { margin-left: 10px; font-size: 14px; font-weight: 500; }
.ct-chart { display: grid; grid-template-columns: repeat(12,1fr); gap: 8px; align-items: end; padding: 6px 4px 0; }
.ct-chart.q { grid-template-columns: repeat(4,1fr); gap: 22px; max-width: 720px; margin: 0 auto; }
.ct-bar-col { display: flex; flex-direction: column; align-items: center; padding: 6px 2px; border-radius: 10px; transition: background .16s; }
.ct-bar-col.selA { background: rgba(127,119,221,.08); }
.ct-bar-col.selB { background: rgba(55,138,221,.08); }
.ct-bar-pct { font-size: 12px; font-weight: 500; margin-bottom: 6px; font-variant-numeric: tabular-nums; }
.ct-bar-wrap { display: flex; align-items: flex-end; justify-content: center; width: 100%; height: 120px; }
.ct-bar-track { position: relative; width: 100%; max-width: 42px; min-height: 4px; background: repeating-linear-gradient(135deg,#E4E5EB 0 4px,#EFF0F3 4px 8px); border-radius: 7px 7px 4px 4px; overflow: hidden; transition: height .6s cubic-bezier(.34,1.2,.64,1); }
.ct-bar-fill { position: absolute; left: 0; right: 0; bottom: 0; border-radius: 6px 6px 4px 4px; transition: height .6s cubic-bezier(.34,1.2,.64,1); }
.ct-bar-count { margin-top: 7px; font-size: 10.5px; color: #A0A0A8; font-variant-numeric: tabular-nums; }
.ct-bar-label { margin-top: 3px; font-size: 11px; font-weight: 500; color: #6B7280; }
.ct-chart.q .ct-bar-track { max-width: 88px; }

.ct-track-note { display: flex; gap: 12px; margin-top: 16px; padding: 14px 18px; background: rgba(127,119,221,.05); border: 1px solid rgba(127,119,221,.16); border-radius: 12px; font-size: 12px; color: #6B7280; line-height: 1.55; }
.ct-track-note svg { color: #7F77DD; flex-shrink: 0; margin-top: 1px; }
.ct-track-note b { color: #1E2A4A; font-weight: 500; }

@media (max-width: 1000px) {
  .ct-split { grid-template-columns: 1fr; }
  .ct-delta { flex-direction: row; min-width: 0; }
}
</style>
