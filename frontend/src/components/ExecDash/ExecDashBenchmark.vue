<script setup lang="ts">
/**
 * ExecDashBenchmark — панель сравнения выбранных компаний (ранжированные бары).
 *
 * Источник данных — клиентская агрегация per-company метрик из useExecutiveDashboard
 * (data.sectors[].companies). 1 компания → фокус (vs среднее по портфелю),
 * 2+ → бенчмаркинг (ранжированные бары + дельта от baseline).
 */
import { computed, ref } from "vue";
import { useExecutiveDashboard, type ExecCompanyOption } from "@/composables/useExecutiveDashboard";

const exec = useExecutiveDashboard();

type MetricKey = "pct" | "done_ratio" | "task_done" | "task_total";
const METRICS: { key: MetricKey; label: string; unit: string; pct: boolean }[] = [
  { key: "pct",        label: "Прогресс",          unit: "%",     pct: true },
  { key: "done_ratio", label: "Выполнено задач",   unit: "%",     pct: true },
  { key: "task_done",  label: "Задач выполнено",   unit: "",      pct: false },
  { key: "task_total", label: "Задач всего",       unit: "",      pct: false },
];
const metric = ref<MetricKey>("pct");
const activeMetric = computed(() => METRICS.find((m) => m.key === metric.value)!);

function valueOf(c: ExecCompanyOption, key: MetricKey): number {
  if (key === "done_ratio") return c.task_total > 0 ? (c.task_done / c.task_total) * 100 : 0;
  return (c as any)[key] || 0;
}

const baselineValue = computed(() => {
  const b = exec.portfolioBaseline.value;
  if (metric.value === "done_ratio") return b.task_total > 0 ? (b.task_done / b.task_total) * 100 : 0;
  return (b as any)[metric.value] || 0;
});

const rows = computed(() => {
  const list = exec.benchmarkCompanies.value.map((c) => ({
    company: c,
    value: valueOf(c, metric.value),
  }));
  list.sort((a, b) => b.value - a.value);
  return list;
});

const maxValue = computed(() => {
  const vals = rows.value.map((r) => r.value).concat(baselineValue.value);
  return Math.max(1, ...vals);
});

function fmt(v: number): string {
  return activeMetric.value.pct ? `${Math.round(v)}%` : String(Math.round(v));
}
function delta(v: number): number {
  return v - baselineValue.value;
}
</script>

<template>
  <section v-if="exec.benchmarkActive.value && rows.length" class="edb">
    <div class="edb-hd">
      <div class="edb-hd-l">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 3v18M3 7l9-4 9 4M5 21h14"/></svg>
        <span class="edb-title">{{ rows.length === 1 ? 'Фокус на компании' : `Бенчмаркинг · ${rows.length} компаний` }}</span>
      </div>
      <div class="edb-hd-r">
        <div class="edb-metrics">
          <button
            v-for="m in METRICS" :key="m.key"
            class="edb-mbtn" :class="{ on: metric === m.key }"
            @click="metric = m.key"
          >{{ m.label }}</button>
        </div>
        <button class="edb-close" title="Закрыть сравнение" @click="exec.clearCompanies()">✕</button>
      </div>
    </div>

    <div class="edb-baseline">
      Среднее по портфелю: <b>{{ fmt(baselineValue) }}</b>
    </div>

    <div class="edb-bars">
      <div v-for="(r, i) in rows" :key="r.company.company_id" class="edb-row">
        <span class="edb-rank">{{ i + 1 }}</span>
        <span class="edb-name" :title="r.company.name">{{ r.company.name }}</span>
        <div class="edb-track">
          <div class="edb-fill" :style="{ width: (r.value / maxValue * 100) + '%', background: r.company.sector_color }"></div>
          <div class="edb-baseline-mark" :style="{ left: (baselineValue / maxValue * 100) + '%' }" title="Среднее по портфелю"></div>
        </div>
        <span class="edb-val">{{ fmt(r.value) }}</span>
        <span class="edb-delta" :class="delta(r.value) >= 0 ? 'pos' : 'neg'">
          {{ delta(r.value) >= 0 ? '▲' : '▼' }}{{ fmt(Math.abs(delta(r.value))) }}
        </span>
      </div>
    </div>
  </section>
</template>

<style scoped>
.edb {
  margin: 0 0 16px;
  background: var(--bg1, #fff);
  border: 1px solid var(--card-border, rgba(30,42,74,.08));
  border-radius: 12px;
  padding: 16px 18px;
  box-shadow: 0 2px 12px rgba(15,23,60,.06);
  animation: edbIn .35s var(--ease-standard) both;
}
@keyframes edbIn { from { opacity: 0; transform: translateY(8px); } to { opacity: 1; transform: none; } }

.edb-hd { display: flex; align-items: center; justify-content: space-between; gap: 12px; flex-wrap: wrap; }
.edb-hd-l { display: flex; align-items: center; gap: 8px; }
.edb-hd-l svg { width: 16px; height: 16px; color: var(--p-deep, #534AB7); }
.edb-title { font-size: 14px; font-weight: 600; color: var(--t1, #1A1730); }
.edb-hd-r { display: flex; align-items: center; gap: 10px; }
.edb-metrics { display: inline-flex; gap: 2px; padding: 2px; background: var(--bg2, #F1F0F7); border-radius: 9px; }
.edb-mbtn {
  padding: 5px 10px; border: none; border-radius: 7px; background: transparent;
  font-size: 11px; font-weight: 500; color: var(--t2, #6B6880); cursor: pointer; font-family: inherit;
  white-space: nowrap; transition: background .14s, color .14s;
}
.edb-mbtn.on { background: #fff; color: var(--p-deep, #534AB7); box-shadow: 0 1px 4px rgba(0,0,0,.08); font-weight: 600; }
.edb-close {
  width: 26px; height: 26px; border-radius: 7px; border: none;
  background: var(--bg2, #F1F0F7); color: var(--t3, #8B889C); cursor: pointer; font-size: 13px;
}
.edb-close:hover { background: rgba(226,75,74,.1); color: #C5352F; }

.edb-baseline { font-size: 11px; color: var(--t3, #8B889C); margin: 10px 0 12px; }
.edb-baseline b { color: var(--t1, #1A1730); }

.edb-bars { display: flex; flex-direction: column; gap: 9px; }
.edb-row { display: grid; grid-template-columns: 18px minmax(90px, 150px) 1fr 48px 64px; align-items: center; gap: 10px; }
.edb-rank { font-size: 11px; font-weight: 700; color: var(--t3, #B6B3C6); text-align: center; }
.edb-name { font-size: 12px; font-weight: 500; color: var(--t1, #1A1730); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.edb-track { position: relative; height: 18px; background: rgba(30,42,74,.06); border-radius: 6px; overflow: visible; }
.edb-fill { height: 100%; border-radius: 6px; transition: width .5s var(--ease-standard); min-width: 3px; }
.edb-baseline-mark {
  position: absolute; top: -2px; bottom: -2px; width: 0;
  border-left: 1.5px dashed rgba(30,42,74,.4);
}
.edb-val { font-size: 12px; font-weight: 600; color: var(--t1, #1A1730); text-align: right; font-variant-numeric: tabular-nums; }
.edb-delta { font-size: 10.5px; font-weight: 600; text-align: right; font-variant-numeric: tabular-nums; }
.edb-delta.pos { color: #1D9E75; }
.edb-delta.neg { color: #D4537E; }
</style>
