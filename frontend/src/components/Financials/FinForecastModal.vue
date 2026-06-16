<script setup lang="ts">
/**
 * FinForecastModal — инструмент прогнозирования финансовых показателей.
 * Пользователь: выбирает компанию (или портфель) → модель → заполняет входные
 * данные модели → получает прогноз на будущие годы. Прогнозные значения ВСЕГДА
 * явно помечены (пунктир + бейдж «прогноз») — это не факт.
 */
import { computed, ref, watch } from "vue";
import type { PortfolioSummaryResponse } from "@/api/financials";
import { fmtCompact } from "./financialsHelpers";
import {
  FORECAST_MODELS, runForecast, lastYoY,
  type ForecastModel, type HistPoint,
} from "@/utils/forecast";

const props = defineProps<{
  summary: PortfolioSummaryResponse;
  unit: "bln" | "mln";
}>();
const emit = defineEmits<{ (e: "close"): void }>();

const METRICS = [
  { id: "revenue", label: "Выручка" },
  { id: "grossProfit", label: "Валовая прибыль" },
  { id: "ebitda", label: "EBITDA" },
  { id: "profit", label: "Чистая прибыль" },
];

const PORTFOLIO = "__portfolio__";
const companyCode = ref<string>(PORTFOLIO);
const model = ref<ForecastModel>("cagr");

const companies = computed(() =>
  [...props.summary.items].sort((a, b) => (a.company_name || "").localeCompare(b.company_name || "", "ru")),
);
const histYears = computed(() => [...props.summary.years].sort((a, b) => a - b));

function rawValue(metric: string, year: number): number | null {
  if (companyCode.value === PORTFOLIO) {
    const v = props.summary.portfolio_totals_by_year?.[year]?.[metric];
    return typeof v === "number" ? v : null;
  }
  const item = props.summary.items.find((i) => i.company_code === companyCode.value);
  const v = item?.by_year?.[year]?.[metric];
  return typeof v === "number" ? v : null;
}
function history(metric: string): HistPoint[] {
  return histYears.value.map((y) => ({ year: y, value: rawValue(metric, y) }));
}

// Последний год факта (по выручке) и целевые прогнозные годы.
const lastActualYear = computed(() => {
  const hist = history("revenue");
  let last = histYears.value[0] ?? new Date().getFullYear();
  for (const h of hist) if (h.value != null && h.value !== 0) last = h.year;
  return last;
});
const targetYears = computed(() => {
  const future = histYears.value.filter((y) => y > lastActualYear.value);
  if (future.length) return future;
  const l = lastActualYear.value;
  return [l + 1, l + 2, l + 3];
});

// ── входные данные модели ──
const modelMeta = computed(() => FORECAST_MODELS.find((m) => m.id === model.value)!);
const cagrFrom = ref<number>(0);
const cagrTo = ref<number>(0);
const linearWindow = ref<number>(3);
const growthPct = ref<number[]>([10, 10, 10]);

watch([lastActualYear, () => companyCode.value], () => {
  const acts = history("revenue").filter((h) => h.value != null && h.value !== 0).map((h) => h.year);
  cagrFrom.value = acts[0] ?? histYears.value[0];
  cagrTo.value = acts[acts.length - 1] ?? lastActualYear.value;
}, { immediate: true });
watch(targetYears, (ty) => {
  if (growthPct.value.length !== ty.length) growthPct.value = ty.map(() => 10);
}, { immediate: true });

const revYoYHint = computed(() => {
  const v = lastYoY(history("revenue"));
  return v == null ? null : Math.round(v);
});

// ── прогноз по каждому показателю ──
const forecastRows = computed(() => {
  const params = {
    cagrFrom: cagrFrom.value, cagrTo: cagrTo.value,
    linearWindow: linearWindow.value, growthPct: growthPct.value,
  };
  return METRICS.map((m) => {
    const hist = history(m.id);
    const fc = runForecast(model.value, hist, targetYears.value, params);
    const fcMap = new Map(fc.map((p) => [p.year, p.value]));
    return {
      label: m.label,
      cells: [
        ...histYears.value.map((y) => ({ year: y, value: rawValue(m.id, y), forecast: false })),
        ...targetYears.value
          .filter((y) => !histYears.value.includes(y))
          .map((y) => ({ year: y, value: fcMap.get(y) ?? null, forecast: true })),
      ],
      // если targetYears пересекаются с histYears (пустые будущие колонки) — перекрыть
    };
  });
});

// Полный список колонок (история + прогнозные, без дублей), по возрастанию.
const allYears = computed(() => {
  const set = new Set<number>([...histYears.value, ...targetYears.value]);
  return [...set].sort((a, b) => a - b);
});
function cellFor(metricIdx: number, year: number): { value: number | null; forecast: boolean } {
  const m = METRICS[metricIdx];
  if (year <= lastActualYear.value && histYears.value.includes(year)) {
    return { value: rawValue(m.id, year), forecast: false };
  }
  // прогнозный год
  const params = {
    cagrFrom: cagrFrom.value, cagrTo: cagrTo.value,
    linearWindow: linearWindow.value, growthPct: growthPct.value,
  };
  const fc = runForecast(model.value, history(m.id), targetYears.value, params);
  const hit = fc.find((p) => p.year === year);
  return { value: hit ? hit.value : null, forecast: true };
}

function fmt(v: number | null): string {
  return fmtCompact(v, props.unit);
}
</script>

<template>
  <div class="ffc-back" @click.self="emit('close')" role="dialog" aria-modal="true">
    <div class="ffc-card">
      <header class="ffc-hd">
        <div>
          <div class="ffc-eyebrow">Инструмент прогнозирования</div>
          <h2 class="ffc-title">Прогноз финансовых показателей</h2>
        </div>
        <button class="ffc-x" @click="emit('close')" aria-label="Закрыть">×</button>
      </header>

      <div class="ffc-body">
        <!-- Шаг 1: объект -->
        <div class="ffc-field">
          <label class="ffc-lbl">1 · Объект прогноза</label>
          <select v-model="companyCode" class="ffc-select">
            <option :value="PORTFOLIO">Весь портфель</option>
            <option v-for="c in companies" :key="c.company_code" :value="c.company_code">
              {{ c.company_name_short || c.company_name || c.company_code }}
            </option>
          </select>
        </div>

        <!-- Шаг 2: модель -->
        <div class="ffc-field">
          <label class="ffc-lbl">2 · Модель прогнозирования</label>
          <div class="ffc-models">
            <button v-for="m in FORECAST_MODELS" :key="m.id"
                    class="ffc-model" :class="{ on: model === m.id }" @click="model = m.id">
              {{ m.label }}
            </button>
          </div>
          <div class="ffc-model-desc">{{ modelMeta.desc }}</div>
        </div>

        <!-- Шаг 3: входные данные модели -->
        <div v-if="modelMeta.inputs.length" class="ffc-field">
          <label class="ffc-lbl">3 · Данные для расчёта</label>

          <div v-if="modelMeta.inputs.includes('cagrRange')" class="ffc-inputs">
            <div class="ffc-in">
              <span>Базовый год (от)</span>
              <select v-model.number="cagrFrom" class="ffc-select sm">
                <option v-for="y in histYears" :key="y" :value="y">{{ y }}</option>
              </select>
            </div>
            <div class="ffc-in">
              <span>Базовый год (до)</span>
              <select v-model.number="cagrTo" class="ffc-select sm">
                <option v-for="y in histYears" :key="y" :value="y">{{ y }}</option>
              </select>
            </div>
            <div v-if="revYoYHint != null" class="ffc-hint">Реализованный YoY выручки: {{ revYoYHint }}%</div>
          </div>

          <div v-if="modelMeta.inputs.includes('linearWindow')" class="ffc-inputs">
            <div class="ffc-in">
              <span>Глубина истории, лет</span>
              <input type="number" min="2" max="10" v-model.number="linearWindow" class="ffc-num" />
            </div>
          </div>

          <div v-if="modelMeta.inputs.includes('growthPct')" class="ffc-inputs">
            <div v-for="(y, i) in targetYears" :key="y" class="ffc-in">
              <span>Рост {{ y }}, %</span>
              <input type="number" v-model.number="growthPct[i]" class="ffc-num" />
            </div>
          </div>
        </div>

        <!-- Результат -->
        <div class="ffc-field">
          <label class="ffc-lbl">Результат <span class="ffc-fc-badge">прогноз</span></label>
          <div class="ffc-table-wrap">
            <table class="ffc-table">
              <thead>
                <tr>
                  <th class="ffc-th-name">Показатель</th>
                  <th v-for="y in allYears" :key="y" class="ffc-th-num" :class="{ fc: y > lastActualYear }">
                    {{ y }}<span v-if="y > lastActualYear" class="ffc-th-fc">П</span>
                  </th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="(m, mi) in METRICS" :key="m.id">
                  <td class="ffc-td-name">{{ m.label }}</td>
                  <td v-for="y in allYears" :key="y" class="ffc-td-num"
                      :class="{ fc: cellFor(mi, y).forecast }">
                    {{ fmt(cellFor(mi, y).value) }}
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
          <div class="ffc-note">
            Прогнозные колонки выделены пунктиром и буквой «П». Метод: <b>{{ modelMeta.label }}</b>.
            Это расчётная оценка, не факт — проверяйте допущения.
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.ffc-back {
  position: fixed; inset: 0; z-index: 9400;
  background: rgba(20,16,40,.5); backdrop-filter: blur(5px);
  display: flex; align-items: center; justify-content: center; padding: 20px;
}
.ffc-card {
  width: min(880px, 96vw); max-height: 90vh; overflow-y: auto;
  background: var(--bg1, #fff); border-radius: 16px;
  box-shadow: 0 30px 70px -15px rgba(30,20,70,.5);
  font-family: Geist, system-ui, sans-serif;
  animation: ffcPop .3s cubic-bezier(.34,1.4,.5,1);
}
@keyframes ffcPop { from { opacity:0; transform: translateY(14px) scale(.97); } to { opacity:1; transform:none; } }
.ffc-hd { display: flex; align-items: center; justify-content: space-between; padding: 18px 22px 14px; border-bottom: 1px solid rgba(15,23,60,.07); }
.ffc-eyebrow { font-size: 9.5px; font-weight: 600; letter-spacing: .07em; text-transform: uppercase; color: rgba(15,23,60,.5); }
.ffc-title { font-size: 17px; font-weight: 600; margin: 3px 0 0; color: var(--t1, #1e2a4a); }
.ffc-x { background: transparent; border: none; font-size: 22px; color: rgba(15,23,60,.45); cursor: pointer; padding: 0 6px; }
.ffc-body { padding: 16px 22px 22px; display: flex; flex-direction: column; gap: 18px; }

.ffc-field { display: flex; flex-direction: column; gap: 8px; }
.ffc-lbl { font-size: 11px; font-weight: 700; letter-spacing: .02em; color: rgba(15,23,60,.7); display: flex; align-items: center; gap: 8px; }
.ffc-select { padding: 8px 11px; border: 1px solid rgba(15,23,60,.14); border-radius: 9px; font-size: 13px; font-family: inherit; background: #fff; color: var(--t1, #1e2a4a); }
.ffc-select.sm { padding: 6px 9px; font-size: 12px; }
.ffc-num { width: 90px; padding: 6px 9px; border: 1px solid rgba(15,23,60,.14); border-radius: 8px; font-size: 12px; font-family: inherit; }

.ffc-models { display: flex; flex-wrap: wrap; gap: 6px; }
.ffc-model { background: var(--bg2, #F4F3F9); border: 1px solid rgba(15,23,60,.08); border-radius: 9px; padding: 7px 13px; font-size: 12px; font-weight: 600; color: var(--t2, #4B5468); cursor: pointer; font-family: inherit; transition: all .15s; }
.ffc-model:hover { background: rgba(127,119,221,.1); }
.ffc-model.on { background: linear-gradient(135deg, #8B7FF0, #6C5CE7); color: #fff; border-color: transparent; box-shadow: 0 3px 9px rgba(108,92,231,.3); }
.ffc-model-desc { font-size: 11.5px; color: rgba(15,23,60,.6); line-height: 1.4; }

.ffc-inputs { display: flex; flex-wrap: wrap; gap: 14px; align-items: flex-end; }
.ffc-in { display: flex; flex-direction: column; gap: 4px; }
.ffc-in > span { font-size: 10.5px; font-weight: 600; color: rgba(15,23,60,.55); }
.ffc-hint { font-size: 10.5px; color: rgba(108,92,231,.85); font-weight: 600; align-self: center; }

.ffc-fc-badge, .ffc-th-fc { font-size: 8.5px; font-weight: 700; color: #A36500; background: rgba(224,146,47,.16); border-radius: 4px; padding: 1px 6px; letter-spacing: .02em; }
.ffc-th-fc { padding: 0 3px; margin-left: 3px; }

.ffc-table-wrap { overflow-x: auto; border: 1px solid rgba(15,23,60,.08); border-radius: 11px; }
.ffc-table { width: 100%; border-collapse: collapse; font-size: 12px; }
.ffc-table th { padding: 8px 12px; font-size: 9.5px; font-weight: 600; text-transform: uppercase; letter-spacing: .04em; color: rgba(15,23,60,.5); background: #FAFAFC; border-bottom: 1px solid rgba(15,23,60,.08); }
.ffc-th-name { text-align: left; }
.ffc-th-num { text-align: right; white-space: nowrap; }
.ffc-th-num.fc { color: #A36500; background: rgba(224,146,47,.07); }
.ffc-table td { padding: 8px 12px; border-bottom: 1px solid rgba(15,23,60,.04); white-space: nowrap; }
.ffc-td-name { text-align: left; font-weight: 500; color: var(--t1, #1e2a4a); }
.ffc-td-num { text-align: right; font-variant-numeric: tabular-nums; color: var(--t1, #1e2a4a); }
.ffc-td-num.fc { color: #8A5A12; background: rgba(224,146,47,.06); border-left: 1px dashed rgba(224,146,47,.4); font-style: italic; }
.ffc-table tbody tr:last-child td { border-bottom: none; }

.ffc-note { font-size: 11px; color: rgba(15,23,60,.6); line-height: 1.4; }
</style>
