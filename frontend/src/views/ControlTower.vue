<script setup lang="ts">
/**
 * ControlTower.vue — «Контрольная вышка».
 *
 * Главный экран — наглядное сравнение исполнения задач ПО МЕСЯЦАМ и КВАРТАЛАМ:
 * по каждому периоду виден план (задачи с дедлайном в периоде) и факт
 * (сколько уже выполнено), % и зона. Плюс сводка года и список компаний.
 *
 * Данные: GET /monitoring/timeline/{year} + GET /dashboard/executive/{year}.
 * Дизайн — по системе проекта (navy/purple, weight 500, карточки, мягкие тени).
 */
import { ref, computed, onMounted, watch } from "vue";
import { api } from "@/api/client";
import {
  getExecutiveDashboard,
  type ExecutiveDashboardData,
} from "@/api/executiveDashboard";

interface Period {
  key: number; label: string; label_full: string;
  plan: number; done: number; pct: number; zone: string;
}
interface Timeline {
  year: number; granularity: string;
  total: number; done: number; pct: number; overdue: number;
  periods: Period[];
}

const timeline = ref<Timeline | null>(null);
const dash = ref<ExecutiveDashboardData | null>(null);
const loading = ref(true);
const error = ref<string | null>(null);

const year = ref<number>(2025);                 // дефолт — год с полными данными
type Gran = "month" | "quarter";
const gran = ref<Gran>("month");
const sectorFilter = ref<string>("");

const availableYears = computed(() => dash.value?.available_years || [2025, 2026]);
const availableSectors = computed(() => dash.value?.available_sectors || []);

async function load() {
  loading.value = true;
  error.value = null;
  try {
    const [tl, d] = await Promise.all([
      api.get<Timeline>(`/monitoring/timeline/${year.value}`, { params: { granularity: gran.value } }),
      getExecutiveDashboard(year.value),
    ]);
    timeline.value = tl.data;
    dash.value = d;
  } catch (e: any) {
    error.value = e?.response?.data?.detail || e?.message || "Ошибка загрузки";
  } finally {
    loading.value = false;
  }
}
onMounted(load);
watch([year, gran], load);

// ─── helpers ────────────────────────────────────────────────────
function zoneColor(zone: string): string {
  return { done: "#1D9E75", ok: "#7F77DD", warn: "#EF9F27", bad: "#E24B4A", empty: "#D7D9E0" }[zone] || "#7F77DD";
}
function pctColor(pct: number): string {
  if (pct >= 100) return "#1D9E75";
  if (pct >= 90) return "#7F77DD";
  if (pct >= 75) return "#EF9F27";
  return "#E24B4A";
}
function pctZoneLabel(pct: number): string {
  if (pct >= 100) return "Выполнено";
  if (pct >= 90) return "В норме";
  if (pct >= 75) return "Внимание";
  return "Риск";
}
function sectorColor(code: string): string {
  return availableSectors.value.find((s) => s.id === code)?.color || "#888780";
}
function sectorLabel(code: string): string {
  return availableSectors.value.find((s) => s.id === code)?.label || code;
}

// масштаб баров — по максимальному плану среди периодов
const maxPlan = computed(() =>
  Math.max(1, ...(timeline.value?.periods.map((p) => p.plan) || [1])),
);
function barH(v: number): number {
  return Math.round((v / maxPlan.value) * 170); // px, высота области 170
}

// компании из секторов (только task % — без прочерков)
const companies = computed(() => {
  const d = dash.value;
  if (!d) return [];
  const out: { id: string; name: string; sector: string; pct: number; done: number; total: number }[] = [];
  for (const sec of d.sectors) {
    if (sectorFilter.value && sec.id !== sectorFilter.value) continue;
    for (const c of sec.companies) {
      out.push({ id: c.company_id, name: c.name, sector: sec.id, pct: c.pct, done: c.task_done, total: c.task_total });
    }
  }
  out.sort((a, b) => b.pct - a.pct);
  return out;
});
</script>

<template>
  <div class="ct-page">
    <!-- ═══════════ TOPBAR ═══════════ -->
    <div class="ct-topbar">
      <div>
        <div class="ct-eyebrow">МОНИТОРИНГ ПОРТФЕЛЯ · {{ dash?.total_companies ?? 22 }} ПРЕДПРИЯТИЙ</div>
        <h1 class="ct-title">Контрольная вышка</h1>
        <div class="ct-sub">Исполнение задач по месяцам и кварталам · {{ year }}</div>
      </div>
      <div class="ct-controls">
        <div class="ct-seg">
          <button class="ct-seg-btn" :class="{ on: gran === 'month' }" @click="gran = 'month'">По месяцам</button>
          <button class="ct-seg-btn" :class="{ on: gran === 'quarter' }" @click="gran = 'quarter'">По кварталам</button>
        </div>
        <select v-model.number="year" class="ct-select">
          <option v-for="y in availableYears" :key="y" :value="y">{{ y }}</option>
        </select>
      </div>
    </div>

    <div v-if="loading" class="ct-state">Загрузка…</div>
    <div v-else-if="error" class="ct-state ct-err">{{ error }}</div>

    <template v-else-if="timeline">
      <!-- ═══════════ СВОДКА ГОДА ═══════════ -->
      <div class="ct-kpis">
        <div class="ct-kpi">
          <div class="ct-kpi-label">Всего задач</div>
          <div class="ct-kpi-val">{{ timeline.total }}</div>
        </div>
        <div class="ct-kpi">
          <div class="ct-kpi-label">Выполнено</div>
          <div class="ct-kpi-val" style="color:#1D9E75">{{ timeline.done }}</div>
        </div>
        <div class="ct-kpi">
          <div class="ct-kpi-label">Исполнение</div>
          <div class="ct-kpi-val" :style="{ color: pctColor(timeline.pct) }">{{ timeline.pct }}<span class="ct-kpi-unit">%</span></div>
        </div>
        <div class="ct-kpi">
          <div class="ct-kpi-label">Просрочено</div>
          <div class="ct-kpi-val" style="color:#E24B4A">{{ timeline.overdue }}</div>
        </div>
      </div>

      <!-- ═══════════ ГЛАВНЫЙ ГРАФИК: СРАВНЕНИЕ ПО ПЕРИОДАМ ═══════════ -->
      <div class="ct-chart-card">
        <div class="ct-chart-head">
          <div>
            <span class="ct-chart-eyebrow">СРАВНЕНИЕ ПО ПЕРИОДАМ</span>
            <span class="ct-chart-title">{{ gran === 'month' ? 'Помесячно' : 'Поквартально' }} — план и факт</span>
          </div>
          <div class="ct-legend">
            <span class="lg"><i class="lg-plan" /> План (дедлайн в периоде)</span>
            <span class="lg"><i class="lg-fact" /> Выполнено</span>
          </div>
        </div>

        <div class="ct-chart" :class="{ q: gran === 'quarter' }">
          <div v-for="p in timeline.periods" :key="p.key" class="ct-bar-col">
            <!-- % сверху -->
            <div class="ct-bar-pct" :style="{ color: p.plan ? pctColor(p.pct) : '#C7C9D1' }">
              {{ p.plan ? p.pct + '%' : '—' }}
            </div>
            <!-- бар: высота = план, заливка снизу = факт -->
            <div class="ct-bar-wrap" :style="{ height: '170px' }">
              <div class="ct-bar-track" :style="{ height: barH(p.plan) + 'px' }" :title="`План: ${p.plan}`">
                <div class="ct-bar-fill"
                     :style="{ height: (p.plan ? (p.done / p.plan * 100) : 0) + '%', background: pctColor(p.pct) }"
                     :title="`Выполнено: ${p.done}`" />
              </div>
            </div>
            <!-- счётчик факт/план -->
            <div class="ct-bar-count">
              <b :style="{ color: p.plan ? pctColor(p.pct) : '#C7C9D1' }">{{ p.done }}</b>
              <span>/ {{ p.plan }}</span>
            </div>
            <!-- подпись периода -->
            <div class="ct-bar-label">{{ p.label }}</div>
          </div>
        </div>
      </div>

      <!-- ═══════════ КОМПАНИИ ═══════════ -->
      <div v-if="companies.length" class="ct-co-card">
        <div class="ct-co-head">
          <div>
            <span class="ct-chart-eyebrow">ПО КОМПАНИЯМ</span>
            <span class="ct-chart-title">Исполнение задач · {{ year }}</span>
          </div>
          <select v-model="sectorFilter" class="ct-select sm">
            <option value="">Все сектора</option>
            <option v-for="s in availableSectors" :key="s.id" :value="s.id">{{ s.label }}</option>
          </select>
        </div>
        <div class="ct-co-list">
          <div v-for="c in companies" :key="c.id" class="ct-co-row" :style="{ borderLeftColor: pctColor(c.pct) }">
            <span class="ct-co-dot" :style="{ background: sectorColor(c.sector) }" />
            <div class="ct-co-name-wrap">
              <span class="ct-co-name">{{ c.name }}</span>
              <span class="ct-co-sector">{{ sectorLabel(c.sector) }}</span>
            </div>
            <div class="ct-co-track">
              <span :style="{ width: Math.min(100, c.pct) + '%', background: pctColor(c.pct) }" />
            </div>
            <span class="ct-co-pct" :style="{ color: pctColor(c.pct) }">{{ c.pct }}%</span>
            <span class="ct-co-cnt">{{ c.done }}/{{ c.total }}</span>
            <span class="ct-co-zone" :style="{ color: pctColor(c.pct), background: pctColor(c.pct) + '14' }">{{ pctZoneLabel(c.pct) }}</span>
          </div>
        </div>
      </div>
    </template>
  </div>
</template>

<style scoped>
.ct-page { padding: 22px 26px 60px; max-width: 1440px; margin: 0 auto; color: #1E2A4A; }

.ct-topbar {
  display: flex; align-items: flex-start; justify-content: space-between; gap: 20px; flex-wrap: wrap;
  padding: 18px 22px; background: linear-gradient(180deg,#fff,#FAFAFC);
  border: 1px solid #EEF0F4; border-radius: 14px; box-shadow: 0 8px 24px rgba(15,23,60,.05);
}
.ct-eyebrow { font-size: 10px; font-weight: 500; letter-spacing: .08em; color: #7F77DD; }
.ct-title { margin: 5px 0 0; font-size: 22px; font-weight: 500; letter-spacing: -.02em; }
.ct-sub { margin-top: 3px; font-size: 12.5px; color: #888780; }
.ct-controls { display: flex; align-items: center; gap: 10px; }
.ct-seg { display: inline-flex; background: #F1F2F6; border-radius: 9px; padding: 3px; }
.ct-seg-btn { border: 0; background: transparent; cursor: pointer; font-size: 12px; font-weight: 500; color: #6B7280; padding: 7px 16px; border-radius: 7px; transition: all .16s cubic-bezier(.34,1.2,.64,1); }
.ct-seg-btn.on { background: #fff; color: #534AB7; box-shadow: 0 2px 6px rgba(15,23,60,.10); }
.ct-select { appearance: none; border: 1px solid #E5E7EB; background: #fff; border-radius: 8px; padding: 8px 14px; font-size: 12.5px; font-weight: 500; color: #1E2A4A; cursor: pointer; outline: none; }
.ct-select.sm { padding: 6px 11px; font-size: 12px; }
.ct-select:focus { border-color: #7F77DD; box-shadow: 0 0 0 3px rgba(127,119,221,.12); }

.ct-state { padding: 60px; text-align: center; color: #888780; font-size: 13px; }
.ct-err { color: #E24B4A; }

/* KPI */
.ct-kpis { display: grid; grid-template-columns: repeat(4,1fr); gap: 14px; margin-top: 16px; }
.ct-kpi { background: #fff; border: 1px solid #EEF0F4; border-radius: 14px; padding: 16px 20px; box-shadow: 0 8px 24px rgba(15,23,60,.05); }
.ct-kpi-label { font-size: 10px; font-weight: 500; letter-spacing: .05em; text-transform: uppercase; color: #888780; }
.ct-kpi-val { margin-top: 8px; font-size: 30px; font-weight: 400; letter-spacing: -.025em; line-height: 1; }
.ct-kpi-unit { font-size: 15px; color: #888780; font-weight: 500; }

/* CHART */
.ct-chart-card { margin-top: 18px; background: #fff; border: 1px solid #EEF0F4; border-radius: 14px; box-shadow: 0 8px 24px rgba(15,23,60,.05); padding: 18px 22px 14px; }
.ct-chart-head { display: flex; align-items: center; justify-content: space-between; margin-bottom: 18px; }
.ct-chart-eyebrow { font-size: 10px; font-weight: 500; letter-spacing: .07em; color: #7F77DD; }
.ct-chart-title { margin-left: 10px; font-size: 14px; font-weight: 500; color: #1E2A4A; }
.ct-legend { display: flex; gap: 16px; }
.ct-legend .lg { display: inline-flex; align-items: center; gap: 7px; font-size: 11.5px; color: #6B7280; }
.ct-legend i { width: 11px; height: 11px; border-radius: 3px; display: inline-block; }
.ct-legend .lg-plan { background: repeating-linear-gradient(135deg,#D7D9E0 0 3px,#EAEBEF 3px 6px); }
.ct-legend .lg-fact { background: #7F77DD; }

.ct-chart { display: grid; grid-template-columns: repeat(12,1fr); gap: 8px; align-items: end; padding: 6px 4px 0; }
.ct-chart.q { grid-template-columns: repeat(4,1fr); gap: 22px; max-width: 720px; margin: 0 auto; }
.ct-bar-col { display: flex; flex-direction: column; align-items: center; }
.ct-bar-pct { font-size: 12px; font-weight: 500; margin-bottom: 6px; font-variant-numeric: tabular-nums; }
.ct-bar-wrap { display: flex; align-items: flex-end; justify-content: center; width: 100%; }
.ct-bar-track {
  position: relative; width: 100%; max-width: 46px; min-height: 4px;
  background: repeating-linear-gradient(135deg,#E4E5EB 0 4px,#EFF0F3 4px 8px);
  border-radius: 7px 7px 4px 4px; overflow: hidden;
  transition: height .6s cubic-bezier(.34,1.2,.64,1);
}
.ct-bar-fill { position: absolute; left: 0; right: 0; bottom: 0; border-radius: 6px 6px 4px 4px; transition: height .6s cubic-bezier(.34,1.2,.64,1); }
.ct-bar-count { margin-top: 8px; font-size: 11px; color: #A0A0A8; font-variant-numeric: tabular-nums; }
.ct-bar-count b { font-weight: 500; }
.ct-bar-label { margin-top: 4px; font-size: 11px; font-weight: 500; color: #6B7280; }
.ct-chart.q .ct-bar-track { max-width: 96px; }
.ct-chart.q .ct-bar-label { font-size: 12px; }

/* COMPANIES */
.ct-co-card { margin-top: 18px; background: #fff; border: 1px solid #EEF0F4; border-radius: 14px; box-shadow: 0 8px 24px rgba(15,23,60,.05); overflow: hidden; }
.ct-co-head { display: flex; align-items: center; justify-content: space-between; padding: 16px 20px 14px; border-bottom: 1px solid #F1F2F6; }
.ct-co-list { padding: 4px 0; }
.ct-co-row {
  display: grid; grid-template-columns: 18px 2.2fr 3fr 56px 64px 110px; align-items: center; gap: 12px;
  padding: 11px 20px; border-bottom: 1px solid #F5F6F8; border-left: 3px solid transparent;
  transition: background .12s;
}
.ct-co-row:hover { background: #FAFAFC; }
.ct-co-row:last-child { border-bottom: 0; }
.ct-co-dot { width: 9px; height: 9px; border-radius: 50%; }
.ct-co-name-wrap { display: flex; flex-direction: column; min-width: 0; }
.ct-co-name { font-size: 13px; font-weight: 500; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.ct-co-sector { font-size: 10.5px; color: #888780; }
.ct-co-track { height: 7px; border-radius: 5px; background: #F1F2F6; overflow: hidden; }
.ct-co-track > span { display: block; height: 100%; border-radius: 5px; transition: width .6s cubic-bezier(.34,1.2,.64,1); }
.ct-co-pct { font-size: 12.5px; font-weight: 500; text-align: right; font-variant-numeric: tabular-nums; }
.ct-co-cnt { font-size: 11px; color: #A0A0A8; text-align: right; font-variant-numeric: tabular-nums; }
.ct-co-zone { font-size: 11px; font-weight: 500; padding: 4px 0; border-radius: 11px; text-align: center; }

@media (max-width: 1100px) {
  .ct-kpis { grid-template-columns: repeat(2,1fr); }
  .ct-co-row { grid-template-columns: 14px 2fr 2fr 50px; }
  .ct-co-cnt, .ct-co-zone { display: none; }
}
</style>
