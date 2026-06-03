<script setup lang="ts">
/**
 * ControlTower.vue — «Контрольная вышка» (прототип).
 *
 * Единый командный экран мониторинга портфеля для высшего руководства:
 * исполнение задач, бизнес-план (план/факт), рейтинги, governance,
 * экономический эффект, налоговый вклад — все прогрессы и показатели по
 * компаниям одним экраном, с периодом (год; месяц/квартал — этап B).
 *
 * Прототип построен на ЖИВЫХ данных GET /dashboard/executive/{year}.
 * Дизайн — по системе проекта (navy #1E2A4A, purple #7F77DD, weight 500,
 * карточки 12-14px, мягкие тени, stroke-иконки, border-left по перформансу).
 */
import { ref, computed, onMounted, watch } from "vue";
import {
  getExecutiveDashboard,
  type ExecutiveDashboardData,
} from "@/api/executiveDashboard";

// ─── state ──────────────────────────────────────────────────────
const data = ref<ExecutiveDashboardData | null>(null);
const loading = ref(true);
const error = ref<string | null>(null);

const year = ref<number>(new Date().getFullYear());
type Period = "month" | "quarter" | "year";
const period = ref<Period>("year");
const sectorFilter = ref<string>("");      // "" = все
const sortKey = ref<"name" | "task" | "bp">("task");

const availableYears = computed(() => data.value?.available_years || []);
const availableSectors = computed(() => data.value?.available_sectors || []);

// ─── load ───────────────────────────────────────────────────────
async function load() {
  loading.value = true;
  error.value = null;
  try {
    data.value = await getExecutiveDashboard(year.value);
  } catch (e: any) {
    error.value = e?.response?.data?.detail || e?.message || "Ошибка загрузки";
  } finally {
    loading.value = false;
  }
}
onMounted(load);
watch(year, load);

// ─── helpers ────────────────────────────────────────────────────
function perfColor(pct: number | null | undefined): string {
  const p = pct ?? 0;
  if (p >= 100) return "#1D9E75";
  if (p >= 90) return "#7F77DD";
  if (p >= 75) return "#EF9F27";
  return "#E24B4A";
}
function perfZone(pct: number | null | undefined): string {
  const p = pct ?? 0;
  if (p >= 100) return "Выполнено";
  if (p >= 90) return "В норме";
  if (p >= 75) return "Внимание";
  return "Риск";
}
function sectorColor(code: string): string {
  return availableSectors.value.find((s) => s.id === code)?.color || "#888780";
}
function sectorLabel(code: string): string {
  return availableSectors.value.find((s) => s.id === code)?.label || code;
}
function fmtMlrd(uzs: number): string {
  // значения tax/EE приходят в млрд сум
  return new Intl.NumberFormat("ru-RU", { maximumFractionDigits: 1 }).format(uzs);
}

// ─── unified per-company rows ───────────────────────────────────
interface Row {
  id: string;
  name: string;
  sector: string;
  taskPct: number;
  taskPlanPct: number;
  taskDone: number;
  taskTotal: number;
  bpPct: number | null;
  bpCls: string | null;
  govPct: number | null;
  rated: boolean;
}

const rows = computed<Row[]>(() => {
  const d = data.value;
  if (!d) return [];
  // базовый список компаний из секторов (исполнение задач)
  const exMap = new Map(d.execution_chart.map((e) => [e.company_id, e]));
  const bpMap = new Map((d.bp_tracker?.rows || []).map((b) => [b.company_id, b]));
  const govMap = new Map(
    (d.governance?.top_companies || []).map((g) => [g.company_id, g]),
  );
  const ratedSet = new Set((d.ratings?.rows || []).map((r) => r.company_id));

  const out: Row[] = [];
  for (const sec of d.sectors) {
    if (sectorFilter.value && sec.id !== sectorFilter.value) continue;
    for (const c of sec.companies) {
      const ex = exMap.get(c.company_id);
      const bp = bpMap.get(c.company_id);
      const gov = govMap.get(c.company_id);
      out.push({
        id: c.company_id,
        name: c.name,
        sector: sec.id,
        taskPct: c.pct,
        taskPlanPct: ex?.plan_pct ?? 0,
        taskDone: c.task_done,
        taskTotal: c.task_total,
        bpPct: bp?.display_pct ?? null,
        bpCls: bp?.cls ?? null,
        govPct: gov?.score_pct ?? null,
        rated: ratedSet.has(c.company_id),
      });
    }
  }
  const k = sortKey.value;
  out.sort((a, b) => {
    if (k === "name") return a.name.localeCompare(b.name, "ru");
    if (k === "bp") return (b.bpPct ?? -1) - (a.bpPct ?? -1);
    return b.taskPct - a.taskPct;
  });
  return out;
});

// ─── hero metrics (real) ────────────────────────────────────────
const hero = computed(() => {
  const d = data.value;
  if (!d) return null;
  const bp = d.bp_tracker;
  const ee = d.economic_effect?.kpi;
  const tax = d.tax_contribution?.kpi;
  const rt = d.ratings;
  return {
    exec: d.avg_execution_pct,
    execDone: d.bottom_metrics.done_tasks,
    execTotal: d.bottom_metrics.task_count,
    bpPct: bp?.overall_pct != null ? Math.round(bp.overall_pct * 100) : null,
    bpLabel: bp?.metric_label || "Бизнес-план",
    bpOnTarget: bp?.on_target ?? 0,
    bpBehind: bp?.behind ?? 0,
    bpTotal: bp?.total_count ?? 0,
    ratedUnique: rt?.rated_total_unique ?? 0,
    ratedTotal: rt?.overall_total ?? d.total_companies,
    eeConv: ee?.conversion_pct ?? null,
    eeRealized: ee?.realized_sum ?? 0,
    eePlanned: ee?.planned_sum ?? 0,
    taxTotal: tax?.total ?? null,
    taxYoY: tax?.yoy_total_pct ?? null,
    companies: d.total_companies,
  };
});

// распределение для футера (из bp_tracker)
const distribution = computed(() => {
  const bp = data.value?.bp_tracker;
  const total = bp?.total_count || 0;
  if (!total) return null;
  return {
    onTarget: bp!.on_target,
    attention: bp!.attention,
    behind: bp!.behind,
    total,
  };
});

const PERIODS: { id: Period; label: string }[] = [
  { id: "month", label: "Месяц" },
  { id: "quarter", label: "Квартал" },
  { id: "year", label: "Год" },
];
</script>

<template>
  <div class="ct-page">
    <!-- ═══════════ TOPBAR (все контролы внутри) ═══════════ -->
    <div class="ct-topbar">
      <div class="ct-tb-left">
        <div class="ct-eyebrow">МОНИТОРИНГ ПОРТФЕЛЯ · {{ hero?.companies ?? "—" }} ПРЕДПРИЯТИЙ</div>
        <h1 class="ct-title">Контрольная вышка</h1>
        <div class="ct-sub">Все прогрессы, статусы и показатели — единым экраном</div>
      </div>

      <div class="ct-tb-right">
        <!-- период -->
        <div class="ct-seg">
          <button v-for="p in PERIODS" :key="p.id"
                  class="ct-seg-btn" :class="{ on: period === p.id }"
                  @click="period = p.id">{{ p.label }}</button>
        </div>
        <!-- год -->
        <select v-model.number="year" class="ct-select">
          <option v-for="y in availableYears" :key="y" :value="y">{{ y }}</option>
        </select>
        <!-- сектор -->
        <select v-model="sectorFilter" class="ct-select">
          <option value="">Все сектора</option>
          <option v-for="s in availableSectors" :key="s.id" :value="s.id">{{ s.label }}</option>
        </select>
      </div>
    </div>

    <!-- период-нота (честно: месяц/квартал = этап B) -->
    <div v-if="period !== 'year'" class="ct-period-note">
      <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round">
        <circle cx="12" cy="12" r="9"/><path d="M12 8v4M12 16h.01"/>
      </svg>
      Показаны сводные данные за год. Помесячная / поквартальная детализация — следующий этап (снимки метрик).
    </div>

    <!-- ═══════════ LOADING / ERROR ═══════════ -->
    <div v-if="loading" class="ct-state">Загрузка контрольной вышки…</div>
    <div v-else-if="error" class="ct-state ct-err">{{ error }}</div>

    <template v-else-if="data && hero">
      <!-- ═══════════ HERO METRIC BAND ═══════════ -->
      <div class="ct-hero">
        <!-- Исполнение задач -->
        <div class="ct-metric" :style="{ '--accent': perfColor(hero.exec) }">
          <div class="ct-m-label">Исполнение задач</div>
          <div class="ct-m-value">{{ hero.exec }}<span class="ct-m-unit">%</span></div>
          <div class="ct-m-bar"><span :style="{ width: Math.min(100, hero.exec) + '%' }" /></div>
          <div class="ct-m-foot">{{ hero.execDone }} из {{ hero.execTotal }} задач</div>
        </div>

        <!-- Бизнес-план -->
        <div class="ct-metric" :style="{ '--accent': perfColor(hero.bpPct ?? 0) }">
          <div class="ct-m-label">{{ hero.bpLabel }} · план/факт</div>
          <div class="ct-m-value">
            <template v-if="hero.bpPct != null">{{ hero.bpPct }}<span class="ct-m-unit">%</span></template>
            <template v-else><span class="ct-m-na">—</span></template>
          </div>
          <div class="ct-m-bar"><span :style="{ width: Math.min(100, hero.bpPct ?? 0) + '%' }" /></div>
          <div class="ct-m-foot">{{ hero.bpOnTarget }} в норме · {{ hero.bpBehind }} отстают</div>
        </div>

        <!-- Рейтинги -->
        <div class="ct-metric" :style="{ '--accent': '#534AB7' }">
          <div class="ct-m-label">Рейтинговое покрытие</div>
          <div class="ct-m-value">{{ hero.ratedUnique }}<span class="ct-m-unit">/{{ hero.ratedTotal }}</span></div>
          <div class="ct-m-bar"><span :style="{ width: (hero.ratedTotal ? hero.ratedUnique / hero.ratedTotal * 100 : 0) + '%', background: '#534AB7' }" /></div>
          <div class="ct-m-foot">компаний с рейтингом</div>
        </div>

        <!-- Эконом-эффект -->
        <div class="ct-metric" :style="{ '--accent': '#1D9E75' }">
          <div class="ct-m-label">Эконом-эффект · конверсия</div>
          <div class="ct-m-value">
            <template v-if="hero.eeConv != null">{{ hero.eeConv }}<span class="ct-m-unit">%</span></template>
            <template v-else><span class="ct-m-na">—</span></template>
          </div>
          <div class="ct-m-bar"><span :style="{ width: Math.min(100, hero.eeConv ?? 0) + '%', background: '#1D9E75' }" /></div>
          <div class="ct-m-foot">{{ fmtMlrd(hero.eeRealized) }} из {{ fmtMlrd(hero.eePlanned) }} млрд</div>
        </div>

        <!-- Налоговый вклад -->
        <div class="ct-metric" :style="{ '--accent': '#378ADD' }">
          <div class="ct-m-label">Налоговый вклад</div>
          <div class="ct-m-value">
            <template v-if="hero.taxTotal != null">{{ fmtMlrd(hero.taxTotal) }}<span class="ct-m-unit"> млрд</span></template>
            <template v-else><span class="ct-m-na">—</span></template>
          </div>
          <div class="ct-m-delta" v-if="hero.taxYoY != null"
               :class="hero.taxYoY >= 0 ? 'up' : 'dn'">
            {{ hero.taxYoY >= 0 ? '↑' : '↓' }} {{ Math.abs(hero.taxYoY).toFixed(1) }}% к году
          </div>
          <div class="ct-m-foot" v-else>в бюджет · {{ year }}</div>
        </div>
      </div>

      <!-- ═══════════ МАТРИЦА ИСПОЛНЕНИЯ ═══════════ -->
      <div class="ct-matrix">
        <div class="ct-mx-head">
          <div class="ct-mx-title">
            <span class="ct-mx-eyebrow">МАТРИЦА ИСПОЛНЕНИЯ</span>
            <span class="ct-mx-count">{{ rows.length }} компаний</span>
          </div>
          <div class="ct-mx-sort">
            <button class="ct-sort-btn" :class="{ on: sortKey === 'task' }" @click="sortKey = 'task'">Задачи</button>
            <button class="ct-sort-btn" :class="{ on: sortKey === 'bp' }" @click="sortKey = 'bp'">Бизнес-план</button>
            <button class="ct-sort-btn" :class="{ on: sortKey === 'name' }" @click="sortKey = 'name'">Название</button>
          </div>
        </div>

        <!-- столбцы -->
        <div class="ct-row ct-row-head">
          <div class="ct-col-co">Компания</div>
          <div class="ct-col-task">Задачи · план/факт</div>
          <div class="ct-col-bp">Бизнес-план</div>
          <div class="ct-col-gov">Governance</div>
          <div class="ct-col-rt">Рейтинг</div>
          <div class="ct-col-zone">Зона</div>
        </div>

        <!-- строки -->
        <div v-for="r in rows" :key="r.id" class="ct-row ct-row-data"
             :style="{ borderLeftColor: perfColor(r.taskPct) }">
          <!-- компания -->
          <div class="ct-col-co">
            <span class="ct-co-dot" :style="{ background: sectorColor(r.sector) }" />
            <div class="ct-co-meta">
              <span class="ct-co-name">{{ r.name }}</span>
              <span class="ct-co-sector">{{ sectorLabel(r.sector) }}</span>
            </div>
          </div>

          <!-- задачи: план/факт двойной бар -->
          <div class="ct-col-task">
            <div class="ct-dual">
              <div class="ct-dual-track">
                <span class="ct-dual-plan" :style="{ width: Math.min(100, r.taskPlanPct) + '%' }" />
                <span class="ct-dual-fact" :style="{ width: Math.min(100, r.taskPct) + '%', background: perfColor(r.taskPct) }" />
              </div>
              <span class="ct-dual-val" :style="{ color: perfColor(r.taskPct) }">{{ r.taskPct }}%</span>
            </div>
            <div class="ct-dual-sub">{{ r.taskDone }}/{{ r.taskTotal }} · план {{ r.taskPlanPct }}%</div>
          </div>

          <!-- бизнес-план -->
          <div class="ct-col-bp">
            <template v-if="r.bpPct != null">
              <span class="ct-chip" :style="{
                background: perfColor(r.bpPct) + '1a', color: perfColor(r.bpPct) }">{{ r.bpPct }}%</span>
            </template>
            <span v-else class="ct-na">—</span>
          </div>

          <!-- governance -->
          <div class="ct-col-gov">
            <template v-if="r.govPct != null">
              <div class="ct-mini-track"><span :style="{ width: Math.min(100, r.govPct) + '%', background: perfColor(r.govPct) }" /></div>
              <span class="ct-mini-val">{{ r.govPct }}%</span>
            </template>
            <span v-else class="ct-na">—</span>
          </div>

          <!-- рейтинг -->
          <div class="ct-col-rt">
            <span v-if="r.rated" class="ct-rt-yes" title="Есть рейтинг">
              <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"><path d="M20 6L9 17l-5-5"/></svg>
            </span>
            <span v-else class="ct-na">—</span>
          </div>

          <!-- зона -->
          <div class="ct-col-zone">
            <span class="ct-zone" :style="{ color: perfColor(r.taskPct), background: perfColor(r.taskPct) + '14' }">
              {{ perfZone(r.taskPct) }}
            </span>
          </div>
        </div>
      </div>

      <!-- ═══════════ ФУТЕР: распределение по бизнес-плану ═══════════ -->
      <div v-if="distribution" class="ct-dist">
        <span class="ct-dist-label">Распределение по бизнес-плану</span>
        <div class="ct-dist-bar">
          <span class="seg ok"   :style="{ width: distribution.onTarget / distribution.total * 100 + '%' }" :title="`В норме: ${distribution.onTarget}`" />
          <span class="seg warn" :style="{ width: distribution.attention / distribution.total * 100 + '%' }" :title="`Внимание: ${distribution.attention}`" />
          <span class="seg bad"  :style="{ width: distribution.behind / distribution.total * 100 + '%' }" :title="`Отстают: ${distribution.behind}`" />
        </div>
        <div class="ct-dist-legend">
          <span><i style="background:#1D9E75" /> В норме {{ distribution.onTarget }}</span>
          <span><i style="background:#EF9F27" /> Внимание {{ distribution.attention }}</span>
          <span><i style="background:#E24B4A" /> Отстают {{ distribution.behind }}</span>
        </div>
      </div>
    </template>
  </div>
</template>

<style scoped>
.ct-page {
  padding: 22px 26px 60px;
  max-width: 1560px;
  margin: 0 auto;
  color: var(--t1, #1E2A4A);
}

/* ─── TOPBAR ─── */
.ct-topbar {
  display: flex; align-items: flex-start; justify-content: space-between;
  gap: 20px; flex-wrap: wrap;
  padding: 18px 22px;
  background: linear-gradient(180deg, #FFFFFF 0%, #FAFAFC 100%);
  border: 1px solid #EEF0F4;
  border-radius: 14px;
  box-shadow: 0 8px 24px rgba(15,23,60,.05);
}
.ct-eyebrow { font-size: 10px; font-weight: 500; letter-spacing: .08em; color: #7F77DD; }
.ct-title { margin: 5px 0 0; font-size: 22px; font-weight: 500; letter-spacing: -.02em; color: #1E2A4A; }
.ct-sub { margin-top: 3px; font-size: 12.5px; color: #888780; }
.ct-tb-right { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }

.ct-seg { display: inline-flex; background: #F1F2F6; border-radius: 9px; padding: 3px; }
.ct-seg-btn {
  border: 0; background: transparent; cursor: pointer;
  font-size: 12px; font-weight: 500; color: #6B7280;
  padding: 6px 14px; border-radius: 7px;
  transition: all .16s cubic-bezier(.34,1.2,.64,1);
}
.ct-seg-btn.on { background: #fff; color: #534AB7; box-shadow: 0 2px 6px rgba(15,23,60,.10); }

.ct-select {
  appearance: none; border: 1px solid #E5E7EB; background: #fff;
  border-radius: 8px; padding: 8px 14px; font-size: 12.5px; font-weight: 500;
  color: #1E2A4A; cursor: pointer; outline: none;
}
.ct-select:focus { border-color: #7F77DD; box-shadow: 0 0 0 3px rgba(127,119,221,.12); }

.ct-period-note {
  display: flex; align-items: center; gap: 8px;
  margin-top: 12px; padding: 9px 14px;
  font-size: 11.5px; color: #854F0B;
  background: rgba(239,159,39,.08); border: 1px solid rgba(239,159,39,.18);
  border-radius: 9px;
}

.ct-state { padding: 60px; text-align: center; color: #888780; font-size: 13px; }
.ct-err { color: #E24B4A; }

/* ─── HERO ─── */
.ct-hero {
  display: grid; grid-template-columns: repeat(5, 1fr); gap: 14px;
  margin-top: 16px;
}
.ct-metric {
  position: relative; overflow: hidden;
  background: #fff; border: 1px solid #EEF0F4; border-radius: 14px;
  padding: 16px 18px 15px;
  box-shadow: 0 8px 24px rgba(15,23,60,.05);
  transition: transform .14s cubic-bezier(.34,1.2,.64,1), box-shadow .14s;
}
.ct-metric::before {
  content: ""; position: absolute; left: 0; top: 0; bottom: 0; width: 3px;
  background: var(--accent, #7F77DD);
}
.ct-metric:hover { transform: translateY(-2px); box-shadow: 0 16px 40px rgba(15,23,60,.10); }
.ct-m-label { font-size: 10px; font-weight: 500; letter-spacing: .05em; text-transform: uppercase; color: #888780; }
.ct-m-value { margin-top: 8px; font-size: 30px; font-weight: 400; letter-spacing: -.025em; color: #1E2A4A; line-height: 1; }
.ct-m-unit { font-size: 14px; color: #888780; font-weight: 500; letter-spacing: 0; }
.ct-m-na { color: #C7C9D1; }
.ct-m-bar { margin-top: 11px; height: 5px; border-radius: 4px; background: #F1F2F6; overflow: hidden; }
.ct-m-bar > span {
  display: block; height: 100%; border-radius: 4px; background: var(--accent, #7F77DD);
  transition: width .6s cubic-bezier(.34,1.2,.64,1);
}
.ct-m-foot { margin-top: 9px; font-size: 11px; color: #888780; }
.ct-m-delta { margin-top: 9px; font-size: 11.5px; font-weight: 500; }
.ct-m-delta.up { color: #1D9E75; }
.ct-m-delta.dn { color: #E24B4A; }

/* ─── MATRIX ─── */
.ct-matrix {
  margin-top: 18px; background: #fff; border: 1px solid #EEF0F4;
  border-radius: 14px; box-shadow: 0 8px 24px rgba(15,23,60,.05);
  overflow: hidden;
}
.ct-mx-head {
  display: flex; align-items: center; justify-content: space-between;
  padding: 16px 20px 14px; border-bottom: 1px solid #F1F2F6;
}
.ct-mx-eyebrow { font-size: 10px; font-weight: 500; letter-spacing: .07em; color: #7F77DD; }
.ct-mx-count { margin-left: 10px; font-size: 11.5px; color: #888780; }
.ct-mx-sort { display: inline-flex; gap: 4px; }
.ct-sort-btn {
  border: 0; background: transparent; cursor: pointer; color: #6B7280;
  font-size: 11.5px; font-weight: 500; padding: 6px 11px; border-radius: 7px;
  transition: all .14s;
}
.ct-sort-btn.on { background: rgba(127,119,221,.10); color: #534AB7; }

.ct-row {
  display: grid;
  grid-template-columns: 2.4fr 2fr 1fr 1.3fr .7fr 1fr;
  align-items: center; gap: 14px;
  padding: 0 20px;
}
.ct-row-head {
  height: 38px; font-size: 10px; font-weight: 500; letter-spacing: .05em;
  text-transform: uppercase; color: #9A99A2; background: #FAFAFC;
  border-bottom: 1px solid #F1F2F6;
}
.ct-row-data {
  min-height: 58px; border-bottom: 1px solid #F5F6F8;
  border-left: 3px solid transparent;
  transition: background .12s;
}
.ct-row-data:hover { background: #FAFAFC; }
.ct-row-data:last-child { border-bottom: 0; }

.ct-col-co { display: flex; align-items: center; gap: 11px; min-width: 0; }
.ct-co-dot { width: 9px; height: 9px; border-radius: 50%; flex-shrink: 0; }
.ct-co-meta { display: flex; flex-direction: column; min-width: 0; }
.ct-co-name { font-size: 13px; font-weight: 500; color: #1E2A4A; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.ct-co-sector { font-size: 10.5px; color: #888780; }

/* dual bar (план/факт) */
.ct-dual { display: flex; align-items: center; gap: 10px; }
.ct-dual-track {
  position: relative; flex: 1; height: 7px; border-radius: 5px;
  background: #F1F2F6; overflow: hidden;
}
.ct-dual-plan {
  position: absolute; left: 0; top: 0; height: 100%; border-radius: 5px;
  background: repeating-linear-gradient(90deg, #D7D9E0 0 4px, #E8E9EE 4px 8px);
}
.ct-dual-fact {
  position: absolute; left: 0; top: 0; height: 100%; border-radius: 5px;
  transition: width .6s cubic-bezier(.34,1.2,.64,1);
}
.ct-dual-val { font-size: 12.5px; font-weight: 500; min-width: 38px; text-align: right; font-variant-numeric: tabular-nums; }
.ct-dual-sub { margin-top: 5px; font-size: 10.5px; color: #A0A0A8; }

.ct-chip {
  display: inline-block; padding: 4px 10px; border-radius: 11px;
  font-size: 12px; font-weight: 500; font-variant-numeric: tabular-nums;
}
.ct-na { color: #C7C9D1; font-size: 12px; }

.ct-mini-track { display: inline-block; width: 64px; height: 5px; border-radius: 4px; background: #F1F2F6; overflow: hidden; vertical-align: middle; }
.ct-mini-track > span { display: block; height: 100%; border-radius: 4px; }
.ct-mini-val { margin-left: 8px; font-size: 11.5px; color: #6B7280; font-variant-numeric: tabular-nums; }

.ct-rt-yes {
  display: inline-flex; align-items: center; justify-content: center;
  width: 22px; height: 22px; border-radius: 50%;
  background: rgba(29,158,117,.12); color: #1D9E75;
}

.ct-zone {
  display: inline-block; padding: 4px 11px; border-radius: 11px;
  font-size: 11px; font-weight: 500;
}

/* ─── DISTRIBUTION FOOTER ─── */
.ct-dist {
  margin-top: 16px; background: #fff; border: 1px solid #EEF0F4;
  border-radius: 14px; padding: 16px 20px; box-shadow: 0 8px 24px rgba(15,23,60,.05);
}
.ct-dist-label { font-size: 11px; font-weight: 500; letter-spacing: .05em; text-transform: uppercase; color: #888780; }
.ct-dist-bar { margin-top: 11px; height: 10px; border-radius: 6px; overflow: hidden; display: flex; background: #F1F2F6; }
.ct-dist-bar .seg { height: 100%; transition: width .6s cubic-bezier(.34,1.2,.64,1); }
.ct-dist-bar .seg.ok { background: #1D9E75; }
.ct-dist-bar .seg.warn { background: #EF9F27; }
.ct-dist-bar .seg.bad { background: #E24B4A; }
.ct-dist-legend { display: flex; gap: 18px; margin-top: 11px; }
.ct-dist-legend span { display: inline-flex; align-items: center; gap: 6px; font-size: 11.5px; color: #6B7280; }
.ct-dist-legend i { width: 9px; height: 9px; border-radius: 3px; display: inline-block; }

@media (max-width: 1200px) {
  .ct-hero { grid-template-columns: repeat(2, 1fr); }
  .ct-row { grid-template-columns: 2fr 1.6fr 1fr 1fr; }
  .ct-col-gov, .ct-col-rt { display: none; }
}
</style>
