<template>
  <div class="sim-page">
    <header class="sim-head">
      <div>
        <div class="sim-eyebrow">What-if · макро-сценарии</div>
        <h1 class="sim-title">Симулятор сценариев</h1>
        <p class="sim-sub">Двигайте факторы — портфель пересчитывается мгновенно</p>
      </div>
      <div class="sim-metric-seg">
        <button v-for="m in metrics" :key="m.code"
                :class="['sim-seg-btn', { active: metric === m.code }]"
                @click="metric = m.code; run()">{{ m.label }}</button>
      </div>
    </header>

    <div class="sim-grid">
      <!-- Слайдеры -->
      <section class="sim-card sim-controls">
        <div class="sim-card-h">
          <span>Макро-факторы</span>
          <button v-if="anyShock" class="sim-reset" @click="reset">Сбросить</button>
        </div>
        <div v-for="f in factors" :key="f.code" class="sim-slider-row">
          <div class="sim-slider-top">
            <span class="sim-slider-label">{{ f.label }}</span>
            <span class="sim-slider-val" :class="valClass(shocks[f.code])" :style="{ '--ac': f.accent }">
              {{ fmtPct(shocks[f.code] || 0) }}
            </span>
          </div>
          <input
            type="range"
            :min="f.min" :max="f.max" :step="f.step"
            :value="shocks[f.code] || 0"
            :style="{ '--ac': f.accent }"
            @input="onSlide(f.code, $event)"
          />
          <div class="sim-slider-scale">
            <span>{{ f.min }}%</span><span>0</span><span>+{{ f.max }}%</span>
          </div>
        </div>
      </section>

      <!-- Результат -->
      <section class="sim-card sim-result">
        <div class="sim-result-hero">
          <div class="sim-hero-lbl">{{ metricLabel }} {{ year }} · влияние сценария</div>
          <div class="sim-hero-val" :class="deltaClass(totals.delta)">
            {{ totals.delta >= 0 ? '+' : '' }}{{ fmtNum(totals.delta) }}
            <span class="sim-hero-unit">{{ unit }}</span>
          </div>
          <div class="sim-hero-row">
            <span class="sim-hero-chip" :class="deltaClass(totals.delta)">
              {{ totals.delta_pct >= 0 ? '+' : '' }}{{ totals.delta_pct.toFixed(1) }}%
            </span>
            <span class="sim-hero-base">база {{ fmtNum(totals.base) }} → прогноз <b>{{ fmtNum(totals.forecast) }}</b></span>
          </div>
        </div>

        <div v-if="loading" class="sim-loading">Пересчёт…</div>

        <div v-else-if="lowCoverage" class="sim-empty">
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="9"/><path d="M12 8v4M12 16h.01"/></svg>
          <div>
            Недостаточно данных эластичности/финансов для расчёта по этой метрике.
            Заполните коэффициенты β и финпоказатели — и сценарий оживёт.
            <span class="sim-cov">покрытие: {{ coverage.with_beta }}/{{ coverage.companies }} компаний с β, {{ coverage.with_base }} с базой</span>
          </div>
        </div>

        <div v-else class="sim-companies">
          <div class="sim-comp-head">
            <span>Компания</span><span class="r">База</span><span class="r">Δ</span><span class="r">Прогноз</span>
          </div>
          <div v-for="c in topCompanies" :key="c.company_id"
               class="sim-comp-row uza-side-stripe"
               :style="{ '--stripe-color': c.delta >= 0 ? '#1D9E75' : '#E24B4A' }">
            <span class="sim-comp-name" :title="c.name">{{ c.name }}</span>
            <span class="r sim-comp-base">{{ fmtNum(c.base) }}</span>
            <span class="r sim-comp-delta" :class="deltaClass(c.delta)">
              {{ c.delta >= 0 ? '+' : '' }}{{ fmtNum(c.delta) }}
            </span>
            <span class="r sim-comp-fc">{{ fmtNum(c.forecast) }}</span>
          </div>
        </div>

        <button v-if="!lowCoverage" class="sim-ai" @click="askAi">
          <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/></svg>
          Спросить ИИ: «объясни этот сценарий»
        </button>
      </section>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed, onMounted } from "vue";
import { useRouter } from "vue-router";
import { api } from "@/api/client";
import { usePortfolioYearStore } from "@/stores/portfolioYear";

interface Factor { code: string; label: string; min: number; max: number; step: number; accent: string; }
interface Metric { code: string; label: string; }
interface CompRow { company_id: string; name: string; base: number; delta: number; forecast: number; delta_pct: number; }

const router = useRouter();
const yearStore = usePortfolioYearStore();

const factors = ref<Factor[]>([]);
const metrics = ref<Metric[]>([]);
const metric = ref("revenue");
const shocks = reactive<Record<string, number>>({});
const loading = ref(false);

const totals = reactive({ base: 0, delta: 0, forecast: 0, delta_pct: 0 });
const byCompany = ref<CompRow[]>([]);
const coverage = reactive({ companies: 0, with_base: 0, with_beta: 0 });
const unit = ref("млн UZS");

const year = computed(() => yearStore.year || 2026);
const metricLabel = computed(() => metrics.value.find((m) => m.code === metric.value)?.label || "Выручка");
const anyShock = computed(() => Object.values(shocks).some((v) => v));
const topCompanies = computed(() => byCompany.value.filter((c) => c.base !== 0).slice(0, 12));
const lowCoverage = computed(() => !loading.value && coverage.with_beta === 0);

function fmtPct(v: number) { return (v > 0 ? "+" : "") + v + "%"; }
function fmtNum(v: number) {
  const a = Math.abs(v);
  if (a >= 1e6) return (v / 1e6).toFixed(1) + " трлн";
  if (a >= 1e3) return (v / 1e3).toFixed(1) + " млрд";
  return Math.round(v).toLocaleString("ru-RU");
}
function valClass(v?: number) { return v && v > 0 ? "pos" : v && v < 0 ? "neg" : ""; }
function deltaClass(v: number) { return v > 0 ? "pos" : v < 0 ? "neg" : ""; }

let _timer: any = null;
function onSlide(code: string, e: Event) {
  shocks[code] = Number((e.target as HTMLInputElement).value);
  scheduleRun();
}
function scheduleRun() {
  if (_timer) clearTimeout(_timer);
  _timer = setTimeout(run, 220);
}
function reset() {
  for (const k of Object.keys(shocks)) shocks[k] = 0;
  run();
}

async function run() {
  loading.value = true;
  try {
    const { data } = await api.post("/simulator/run", {
      target_metric: metric.value,
      year: year.value,
      shocks: { ...shocks },
    });
    Object.assign(totals, data.totals);
    byCompany.value = data.by_company || [];
    Object.assign(coverage, data.coverage || {});
    unit.value = data.unit || "млн UZS";
  } catch { /* keep previous */ }
  finally { loading.value = false; }
}

function askAi() {
  const parts = Object.entries(shocks).filter(([, v]) => v)
    .map(([k, v]) => `${factors.value.find((f) => f.code === k)?.label || k}: ${v > 0 ? "+" : ""}${v}%`);
  const q = `Объясни сценарий: при изменениях [${parts.join(", ")}] прогноз по «${metricLabel.value}» меняется на ${totals.delta_pct.toFixed(1)}% (${fmtNum(totals.delta)} ${unit.value}). Какие компании в зоне риска и что предпринять?`;
  try { sessionStorage.setItem("uza_ai_prefill", q); } catch { /* noop */ }
  router.push("/ai-chat");
}

onMounted(async () => {
  try {
    const { data } = await api.get("/simulator/factors");
    factors.value = data.factors || [];
    metrics.value = data.metrics || [];
    for (const f of factors.value) shocks[f.code] = 0;
  } catch { /* noop */ }
  run();
});
</script>

<style scoped>
.sim-page { padding: 24px 32px; max-width: 1400px; margin: 0 auto; }
.sim-head { display: flex; align-items: flex-start; justify-content: space-between; gap: 16px; margin-bottom: 18px; flex-wrap: wrap; }
.sim-eyebrow { font-size: 10px; font-weight: 500; letter-spacing: 0.08em; text-transform: uppercase; color: var(--t3, #94A3B8); margin-bottom: 6px; }
.sim-title { font-size: 22px; font-weight: 500; letter-spacing: -0.01em; margin: 0 0 4px; color: var(--t1, #1E2A4A); }
.sim-sub { font-size: 13px; color: var(--t3, #94A3B8); margin: 0; }

.sim-metric-seg { display: inline-flex; gap: 2px; padding: 3px; background: var(--bg3, #F1F5F9); border-radius: 11px; }
.sim-seg-btn { padding: 7px 14px; font-size: 12.5px; font-weight: 500; border: 0; background: transparent; color: var(--t2, #475569); border-radius: 8px; cursor: pointer; transition: all .15s; }
.sim-seg-btn.active { background: #fff; color: #534AB7; box-shadow: 0 1px 4px rgba(15,23,60,.1); }

.sim-grid { display: grid; grid-template-columns: minmax(300px, 0.9fr) minmax(360px, 1.3fr); gap: 16px; align-items: start; }
@media (max-width: 980px) { .sim-grid { grid-template-columns: 1fr; } }

.sim-card { background: var(--card-bg, #fff); border: 1px solid var(--card-border, rgba(30,42,74,.06)); border-radius: 16px; padding: 18px; box-shadow: 0 2px 12px rgba(15,23,60,.06); }
.sim-card-h { display: flex; align-items: center; justify-content: space-between; font-size: 12px; font-weight: 500; text-transform: uppercase; letter-spacing: .06em; color: var(--t3, #94A3B8); margin-bottom: 14px; }
.sim-reset { font-size: 11px; color: #7F77DD; background: transparent; border: 0; cursor: pointer; font-weight: 500; }
.sim-reset:hover { text-decoration: underline; }

.sim-slider-row { margin-bottom: 16px; }
.sim-slider-top { display: flex; align-items: center; justify-content: space-between; margin-bottom: 6px; }
.sim-slider-label { font-size: 13px; color: var(--t1, #1E2A4A); font-weight: 500; }
.sim-slider-val { font-size: 13px; font-weight: 600; font-variant-numeric: tabular-nums; color: var(--t3, #94A3B8); min-width: 48px; text-align: right; }
.sim-slider-val.pos { color: #1D9E75; }
.sim-slider-val.neg { color: #E24B4A; }

input[type="range"] {
  -webkit-appearance: none; appearance: none;
  width: 100%; height: 6px; border-radius: 4px;
  background: linear-gradient(90deg, #E5E7EB, #E5E7EB);
  outline: none; cursor: pointer;
}
input[type="range"]::-webkit-slider-thumb {
  -webkit-appearance: none; appearance: none;
  width: 18px; height: 18px; border-radius: 50%;
  background: #fff; border: 3px solid var(--ac, #7F77DD);
  box-shadow: 0 2px 8px rgba(15,23,60,.18);
  transition: transform .12s;
}
input[type="range"]::-webkit-slider-thumb:hover { transform: scale(1.15); }
input[type="range"]::-moz-range-thumb {
  width: 18px; height: 18px; border-radius: 50%;
  background: #fff; border: 3px solid var(--ac, #7F77DD);
  box-shadow: 0 2px 8px rgba(15,23,60,.18);
}
.sim-slider-scale { display: flex; justify-content: space-between; font-size: 9.5px; color: var(--t3, #CBD5E1); margin-top: 3px; }

/* Result */
.sim-result-hero {
  padding: 18px 20px; border-radius: 13px; margin-bottom: 14px;
  background: linear-gradient(135deg, #1E2A4A 0%, #2A2065 60%, #534AB7 100%);
  color: #fff;
}
.sim-hero-lbl { font-size: 11px; text-transform: uppercase; letter-spacing: .06em; color: rgba(255,255,255,.7); margin-bottom: 8px; }
.sim-hero-val { font-size: 38px; font-weight: 400; letter-spacing: -.025em; font-variant-numeric: tabular-nums; line-height: 1; }
.sim-hero-val.pos { color: #6EE7B7; }
.sim-hero-val.neg { color: #FCA5A5; }
.sim-hero-unit { font-size: 15px; color: rgba(255,255,255,.6); margin-left: 6px; letter-spacing: 0; }
.sim-hero-row { display: flex; align-items: center; gap: 10px; margin-top: 10px; flex-wrap: wrap; }
.sim-hero-chip { padding: 3px 10px; border-radius: 999px; font-size: 12px; font-weight: 600; background: rgba(255,255,255,.14); }
.sim-hero-chip.pos { color: #6EE7B7; }
.sim-hero-chip.neg { color: #FCA5A5; }
.sim-hero-base { font-size: 12px; color: rgba(255,255,255,.72); font-variant-numeric: tabular-nums; }

.sim-loading { padding: 24px; text-align: center; color: var(--t3); font-size: 13px; }
.sim-empty { display: flex; gap: 11px; padding: 16px; border-radius: 12px; background: #FEF9F0; border: 1px solid #FDE9C8; color: #92610B; font-size: 12.5px; line-height: 1.5; }
.sim-empty svg { flex-shrink: 0; color: #EF9F27; margin-top: 1px; }
.sim-cov { display: block; margin-top: 5px; font-size: 11px; color: #B58A3A; }

.sim-companies { }
.sim-comp-head, .sim-comp-row { display: grid; grid-template-columns: 2fr 1fr 1fr 1fr; gap: 8px; align-items: center; }
.sim-comp-head { font-size: 10px; text-transform: uppercase; letter-spacing: .05em; color: var(--t3, #94A3B8); padding: 0 8px 8px; }
.sim-comp-head .r, .sim-comp-row .r { text-align: right; }
.sim-comp-row { padding: 9px 8px; border-radius: 9px; font-size: 12.5px; font-variant-numeric: tabular-nums; transition: background .12s; }
.sim-comp-row:hover { background: rgba(127,119,221,.05); }
.sim-comp-name { color: var(--t1, #1E2A4A); font-weight: 500; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.sim-comp-base { color: var(--t3, #94A3B8); }
.sim-comp-delta.pos { color: #1D9E75; font-weight: 600; }
.sim-comp-delta.neg { color: #E24B4A; font-weight: 600; }
.sim-comp-fc { color: var(--t1, #1E2A4A); font-weight: 500; }

.sim-ai {
  margin-top: 14px; display: inline-flex; align-items: center; gap: 7px;
  padding: 8px 14px; border-radius: 999px;
  border: 1px solid rgba(127,119,221,.3); background: rgba(127,119,221,.06);
  color: #534AB7; font-size: 12px; font-weight: 500; cursor: pointer; transition: all .15s;
}
.sim-ai:hover { background: #fff; border-color: rgba(127,119,221,.5); transform: translateY(-1px); box-shadow: 0 4px 14px rgba(127,119,221,.14); }
</style>
