<script setup lang="ts">
/**
 * KpiDrillModal — модалка для drill-down по KPI карточкам (Pack 8.1).
 *
 * Поддерживает 8 типов KPI с разными визуализациями:
 *   - total-investment → Treemap (размер = инвестиции, цвет = статус)
 *   - npv             → Waterfall (вклад по проектам, сорт desc)
 *   - irr             → Scatter (IRR vs Investment, bubble = NPV)
 *   - disbursement / payback / jobs / capex-exec / revenue → List-bar fallback (Pack 8.2 заменит на дет. виз)
 */
import { computed, onMounted, onBeforeUnmount } from 'vue';
import type { InvestProjectsCompanyData } from '@/data/ngmk-invest-seed';

export type KpiType =
  | 'total-investment' | 'disbursement' | 'npv' | 'irr'
  | 'payback' | 'jobs' | 'capex-exec' | 'revenue';

const props = defineProps<{
  kpiType: KpiType;
  portfolio: InvestProjectsCompanyData;
}>();

const emit = defineEmits<{
  (e: 'close'): void;
}>();

// ─── KPI metadata ────────────────────────────────────────
interface KpiMeta {
  eyebrow: string;
  title: string;
  value: string;
  subtitle: string;
  accent: string;
}

const kpiMeta = computed<KpiMeta>(() => {
  const projects = props.portfolio.projects;
  // 2026-05-26: Number-coerce — backend numeric/decimal приходят строками.
  // wIRR multiplication работает через * coercion, но accumulation в s+ → bug.
  const totalInv = projects.reduce((s, p) => s + Number(p.total_investment_mln ?? 0), 0);
  const totalNPV = projects.reduce((s, p) => s + Number(p.npv_mln ?? 0), 0);
  const fundedTotal = projects.reduce((s, p) => s + Number(p.funding_2026_mln ?? 0), 0);
  const disbursed = projects.reduce((s, p) => s + Number(p.disbursed_ytd_mln ?? 0), 0);
  const totalJobs = projects.reduce((s, p) => s + Number(p.new_jobs ?? 0), 0);
  const totalRev = projects.reduce((s, p) => s + Number(p.revenue_impact_mln ?? 0), 0);

  const withIRR = projects.filter(p => p.irr_pct !== null);
  const wIRR = withIRR.length > 0
    ? withIRR.reduce((s, p) => s + Number(p.irr_pct ?? 0) * Number(p.total_investment_mln ?? 0), 0) /
      withIRR.reduce((s, p) => s + Number(p.total_investment_mln ?? 0), 0)
    : 0;

  const withPayback = projects.filter(p => p.payback_years !== null);
  const avgPayback = withPayback.length > 0
    ? withPayback.reduce((s, p) => s + Number(p.payback_years ?? 0), 0) / withPayback.length
    : 0;

  const capexExec = props.portfolio.capex.annual_exec_rate * 100;

  const fmt = (n: number, d = 0) => n.toLocaleString('ru-RU', { maximumFractionDigits: d, minimumFractionDigits: 0 });
  const fmtPct = (n: number) => n.toFixed(1).replace('.', ',') + '%';

  switch (props.kpiType) {
    case 'total-investment':
      return { eyebrow: 'KPI DRILL · ВСЕГО ИНВЕСТИЦИЙ', title: `$${fmt(totalInv)}M`, value: `${fmt(totalInv)} млн $`,
               subtitle: `структура портфеля · ${projects.length} проектов`, accent: '#7F77DD' };
    case 'npv':
      return { eyebrow: 'KPI DRILL · NPV ПОРТФЕЛЯ', title: `$${fmt(totalNPV)}M`, value: '',
               subtitle: `contribution by project · ${projects.filter(p=>p.npv_mln!==null).length} из ${projects.length} с расчётом`, accent: '#378ADD' };
    case 'irr':
      return { eyebrow: 'KPI DRILL · IRR СРЕДНИЙ', title: fmtPct(wIRR), value: '',
               subtitle: 'взвешенный · разброс по проектам', accent: '#EF9F27' };
    case 'disbursement':
      return { eyebrow: 'KPI DRILL · ОСВОЕНИЕ ПОРТФЕЛЯ', title: fmtPct((disbursed/fundedTotal)*100), value: '',
               subtitle: `$${fmt(disbursed,1)}M из $${fmt(fundedTotal,1)}M плана 2026`, accent: '#1D9E75' };
    case 'payback':
      return { eyebrow: 'KPI DRILL · СРОК ОКУПАЕМОСТИ', title: `${avgPayback.toFixed(1).replace('.', ',')} лет`, value: '',
               subtitle: `avg по ${withPayback.length} проектам`, accent: '#9B8EC4' };
    case 'jobs':
      return { eyebrow: 'KPI DRILL · НОВЫЕ РАБОЧИЕ МЕСТА', title: fmt(totalJobs), value: '',
               subtitle: 'efficiency = места / $M инвестиций', accent: '#1D9E75' };
    case 'capex-exec':
      return { eyebrow: 'KPI DRILL · CAPEX 2026 EXEC', title: fmtPct(capexExec), value: '',
               subtitle: `$${fmt(props.portfolio.capex.annual_actual_ytd_mln, 1)}M / план $${fmt(props.portfolio.capex.annual_plan_mln, 1)}M`, accent: '#E24B4A' };
    case 'revenue':
      return { eyebrow: 'KPI DRILL · ДОХОД В ГОД (STEADY)', title: `$${fmt(totalRev, 1)}M`, value: '',
               subtitle: 'после выхода на проектную мощность', accent: '#EF9F27' };
  }
  return { eyebrow: '', title: '', value: '', subtitle: '', accent: '#7F77DD' };
});

// ─── Treemap (total-investment) ──────────────────────────
interface TreemapItem {
  name: string;
  shortName: string;
  value: number;
  pct: number;
  status: string;
  color: string;
}

const treemap = computed<TreemapItem[]>(() => {
  const total = props.portfolio.projects.reduce((s, p) => s + Number(p.total_investment_mln ?? 0), 0);
  return [...props.portfolio.projects]
    .sort((a, b) => Number(b.total_investment_mln ?? 0) - Number(a.total_investment_mln ?? 0))
    .map(p => {
      let color = '#1D9E75';
      if (p.status === 'Планируется') color = '#7F77DD';
      else if (p.status === 'В процессе') color = '#EF9F27';
      const short = p.name.length > 22 ? p.name.substring(0, 20) + '…' : p.name;
      const inv = Number(p.total_investment_mln ?? 0);
      return {
        name: p.name,
        shortName: short,
        value: inv,
        pct: total > 0 ? (inv / total) * 100 : 0,
        status: p.status,
        color,
      };
    });
});

const statusCounts = computed(() => {
  const real = props.portfolio.projects.filter(p => p.status === 'Реализуется');
  const plan = props.portfolio.projects.filter(p => p.status === 'Планируется');
  const proc = props.portfolio.projects.filter(p => p.status === 'В процессе');
  return {
    real: { count: real.length, sum: real.reduce((s, p) => s + Number(p.total_investment_mln ?? 0), 0) },
    plan: { count: plan.length, sum: plan.reduce((s, p) => s + Number(p.total_investment_mln ?? 0), 0) },
    proc: { count: proc.length, sum: proc.reduce((s, p) => s + Number(p.total_investment_mln ?? 0), 0) },
  };
});

// ─── Waterfall (npv) ─────────────────────────────────────
const npvWaterfall = computed(() => {
  const withNPV = [...props.portfolio.projects]
    .filter(p => p.npv_mln !== null)
    .sort((a, b) => (b.npv_mln as number) - (a.npv_mln as number));
  const totalNPV = withNPV.reduce((s, p) => s + (p.npv_mln as number), 0);
  const maxNPV = withNPV.length > 0 ? (withNPV[0].npv_mln as number) : 1;
  const without = props.portfolio.projects.filter(p => p.npv_mln === null);

  return {
    rows: withNPV.map(p => ({
      name: p.name.length > 26 ? p.name.substring(0, 24) + '…' : p.name,
      npv: p.npv_mln as number,
      pct: ((p.npv_mln as number) / totalNPV) * 100,
      barPct: ((p.npv_mln as number) / maxNPV) * 100,
      color: p.npv_mln === maxNPV ? '#1D9E75' : ((p.npv_mln as number) >= totalNPV * 0.15 ? '#1D9E75' : '#EF9F27'),
    })),
    withoutCount: without.length,
    total: totalNPV,
  };
});

// ─── Scatter (irr) ──────────────────────────────────────
const scatterPoints = computed(() => {
  const withIRR = props.portfolio.projects.filter(p => p.irr_pct !== null);
  const maxInvest = Math.max(...withIRR.map(p => p.total_investment_mln));
  const maxNPV = Math.max(...withIRR.map(p => p.npv_mln ?? 0));
  return withIRR.map(p => {
    const npv = p.npv_mln ?? 0;
    const minSize = 12, maxSize = 36;
    const size = minSize + ((npv / maxNPV) * (maxSize - minSize));
    const short = p.name.length > 12 ? p.name.substring(0, 10) + '…' : p.name;
    return {
      name: p.name,
      shortName: short,
      irr: p.irr_pct as number,
      investment: p.total_investment_mln,
      npv,
      xPct: (p.total_investment_mln / maxInvest) * 95,
      yPct: 100 - ((p.irr_pct as number) / 40) * 100,
      size,
      title: `${p.name} · $${p.total_investment_mln.toFixed(0)}M · IRR ${(p.irr_pct as number).toFixed(1)}% · NPV ${npv.toFixed(0)}`,
    };
  });
});

const irrStats = computed(() => {
  const withIRR = props.portfolio.projects.filter(p => p.irr_pct !== null);
  const wAvg = withIRR.reduce((s, p) => s + Number(p.irr_pct ?? 0) * Number(p.total_investment_mln ?? 0), 0) /
               withIRR.reduce((s, p) => s + Number(p.total_investment_mln ?? 0), 0);
  const topIrr = [...withIRR].sort((a, b) => (b.irr_pct as number) - (a.irr_pct as number))[0];
  const below = withIRR.filter(p => (p.irr_pct as number) < wAvg);
  return {
    wAvg,
    topName: topIrr.name.length > 16 ? topIrr.name.substring(0, 14) + '…' : topIrr.name,
    topIrr: topIrr.irr_pct as number,
    avgLineYPct: 100 - (wAvg / 40) * 100,
    belowCount: below.length,
  };
});

// ─── Fallback: list view for other KPIs ──────────────────
interface ListItem {
  name: string;
  primary: string;
  primaryColor: string;
  secondary: string;
  barPct: number;
  barColor: string;
}

const fallbackList = computed<ListItem[]>(() => {
  if (!['disbursement', 'payback', 'jobs', 'capex-exec', 'revenue'].includes(props.kpiType)) return [];
  const projects = props.portfolio.projects;

  switch (props.kpiType) {
    case 'disbursement': {
      return [...projects]
        .filter(p => p.funding_2026_mln > 0)
        .map(p => {
          const pct = (p.disbursed_ytd_mln / p.funding_2026_mln) * 100;
          const isRisk = pct < 30;
          return {
            name: p.name.length > 30 ? p.name.substring(0, 28) + '…' : p.name,
            primary: pct.toFixed(2).replace('.', ',') + '%',
            primaryColor: isRisk ? '#A32D2D' : '#0F6E56',
            secondary: `$${p.disbursed_ytd_mln.toFixed(2)}M / $${p.funding_2026_mln.toFixed(1)}M`,
            barPct: Math.min(pct, 100),
            barColor: isRisk ? '#E24B4A' : '#1D9E75',
          };
        })
        .sort((a, b) => parseFloat(b.primary) - parseFloat(a.primary));
    }
    case 'payback': {
      return projects
        .filter(p => p.payback_years !== null)
        .sort((a, b) => (a.payback_years as number) - (b.payback_years as number))
        .map(p => {
          const yrs = p.payback_years as number;
          const color = yrs < 5 ? '#1D9E75' : yrs < 10 ? '#EF9F27' : '#E24B4A';
          return {
            name: p.name.length > 30 ? p.name.substring(0, 28) + '…' : p.name,
            primary: `${yrs.toFixed(1).replace('.', ',')} лет`,
            primaryColor: yrs < 5 ? '#0F6E56' : yrs < 10 ? '#BA7517' : '#A32D2D',
            secondary: `NPV $${(p.npv_mln ?? 0).toFixed(0)}M · IRR ${p.irr_pct?.toFixed(1)}%`,
            barPct: Math.min((yrs / 15) * 100, 100),
            barColor: color,
          };
        });
    }
    case 'jobs': {
      return projects
        .filter(p => p.new_jobs > 0)
        .sort((a, b) => b.new_jobs - a.new_jobs)
        .map(p => {
          const efficiency = p.new_jobs / p.total_investment_mln;
          return {
            name: p.name.length > 30 ? p.name.substring(0, 28) + '…' : p.name,
            primary: p.new_jobs.toLocaleString('ru-RU'),
            primaryColor: '#0F6E56',
            secondary: `${efficiency.toFixed(1)} мест / $M · $${p.total_investment_mln.toFixed(0)}M`,
            barPct: Math.min((p.new_jobs / 3000) * 100, 100),
            barColor: '#1D9E75',
          };
        });
    }
    case 'revenue': {
      return projects
        .filter(p => p.revenue_impact_mln > 0)
        .sort((a, b) => b.revenue_impact_mln - a.revenue_impact_mln)
        .map(p => ({
          name: p.name.length > 30 ? p.name.substring(0, 28) + '…' : p.name,
          primary: `$${p.revenue_impact_mln.toFixed(1)}M/год`,
          primaryColor: '#3C3489',
          secondary: `Inv $${p.total_investment_mln.toFixed(0)}M · ${(p.total_investment_mln / p.revenue_impact_mln).toFixed(1)} лет FCF break-even`,
          barPct: Math.min((p.revenue_impact_mln / 80) * 100, 100),
          barColor: '#7F77DD',
        }));
    }
    case 'capex-exec': {
      return projects
        .filter(p => p.capex_budget_cumul_mln !== undefined && (p.capex_budget_cumul_mln as number) > 0)
        .map(p => {
          const budget = p.capex_budget_cumul_mln as number;
          const actual = p.capex_actual_cumul_mln ?? 0;
          const pct = (actual / budget) * 100;
          const variance = pct - 100;
          return {
            name: p.name.length > 30 ? p.name.substring(0, 28) + '…' : p.name,
            primary: `${pct.toFixed(0)}%`,
            primaryColor: variance > 10 ? '#A32D2D' : variance < -20 ? '#A32D2D' : '#0F6E56',
            secondary: `Plan $${budget.toFixed(1)}M · Fact $${actual.toFixed(1)}M${variance !== 0 ? ` (${variance > 0 ? '+' : ''}${variance.toFixed(0)}%)` : ''}`,
            barPct: Math.min(pct, 150) / 1.5,
            barColor: variance > 10 ? '#E24B4A' : variance < -20 ? '#EF9F27' : '#1D9E75',
          };
        })
        .sort((a, b) => parseFloat(b.primary) - parseFloat(a.primary));
    }
    default:
      return [];
  }
});

// ─── Keyboard close ─────────────────────────────────────────
function onKeydown(e: KeyboardEvent) {
  if (e.key === 'Escape') emit('close');
}
onMounted(() => document.addEventListener('keydown', onKeydown));
onBeforeUnmount(() => document.removeEventListener('keydown', onKeydown));

function onBackdropClick(e: MouseEvent) {
  if ((e.target as HTMLElement).classList.contains('kd-backdrop')) emit('close');
}

function fmt(n: number, d = 0): string {
  return n.toLocaleString('ru-RU', { maximumFractionDigits: d, minimumFractionDigits: 0 });
}
</script>

<template>
  <div class="kd-backdrop" @mousedown="onBackdropClick">
    <div class="kd-modal" @mousedown.stop :style="{ '--ac': kpiMeta.accent } as any">
      <!-- Top animated bar -->
      <div class="kd-top-bar" :style="{ background: kpiMeta.accent }"></div>
      <div class="kd-top-shimmer"></div>

      <!-- Header -->
      <div class="kd-header">
        <div>
          <div class="kd-eyebrow">{{ kpiMeta.eyebrow }}</div>
          <div class="kd-title"><b>{{ kpiMeta.title }}</b> · {{ kpiMeta.subtitle }}</div>
        </div>
        <button class="kd-close" aria-label="close" @click="emit('close')">
          <svg width="11" height="11" viewBox="0 0 14 14" fill="none" stroke="#888780" stroke-width="1.5"><path d="M3 3l8 8M11 3l-8 8"/></svg>
        </button>
      </div>

      <!-- Body — switch by kpiType -->
      <div class="kd-body">

        <!-- Pattern: TREEMAP (total-investment) -->
        <template v-if="kpiType === 'total-investment'">
          <div class="kd-hint">Treemap · размер = инвестиции · цвет = статус</div>
          <div class="kd-treemap">
            <div v-for="(item, i) in treemap" :key="i"
              class="kd-tm-cell"
              :style="{ flexGrow: item.pct, background: item.color, animationDelay: (200 + i * 60) + 'ms' }"
              :title="`${item.name} · $${item.value.toFixed(1)}M · ${item.pct.toFixed(1)}%`">
              <div class="kd-tm-name">{{ item.shortName }}</div>
              <div class="kd-tm-val">${{ fmt(item.value) }}M · {{ item.pct.toFixed(1) }}%</div>
            </div>
          </div>
          <div class="kd-legend">
            <span class="kd-legend-item"><span class="kd-legend-sq" style="background:#1D9E75"></span>Реализуется ({{ statusCounts.real.count }} · ${{ fmt(statusCounts.real.sum) }}M)</span>
            <span class="kd-legend-item"><span class="kd-legend-sq" style="background:#7F77DD"></span>Планируется ({{ statusCounts.plan.count }} · ${{ fmt(statusCounts.plan.sum) }}M)</span>
            <span v-if="statusCounts.proc.count > 0" class="kd-legend-item"><span class="kd-legend-sq" style="background:#EF9F27"></span>В процессе ({{ statusCounts.proc.count }} · ${{ fmt(statusCounts.proc.sum) }}M)</span>
          </div>
        </template>

        <!-- Pattern: WATERFALL (npv) -->
        <template v-else-if="kpiType === 'npv'">
          <div class="kd-hint">Waterfall · вклад каждого проекта в итоговый NPV портфеля</div>
          <div class="kd-wf">
            <div v-for="(row, i) in npvWaterfall.rows" :key="i" class="kd-wf-row" :style="{ '--rd': (i * 80) + 'ms' } as any">
              <div class="kd-wf-name">{{ row.name }}</div>
              <div class="kd-wf-track">
                <div class="kd-wf-bar" :style="{ width: row.barPct + '%', background: row.color }"></div>
              </div>
              <div class="kd-wf-val">{{ fmt(row.npv) }}</div>
              <div class="kd-wf-pct">{{ row.pct.toFixed(1) }}%</div>
            </div>

            <div v-if="npvWaterfall.withoutCount > 0" class="kd-wf-row kd-wf-row-empty">
              <div class="kd-wf-name kd-wf-name-empty">{{ npvWaterfall.withoutCount }} проектов без NPV</div>
              <div class="kd-wf-track-empty"></div>
              <div class="kd-wf-val" style="color: var(--t3, #888780)">—</div>
              <div class="kd-wf-pct" style="color: var(--t3, #888780)">—</div>
            </div>

            <div class="kd-wf-row kd-wf-row-total">
              <div class="kd-wf-name" style="font-weight:500">ИТОГО</div>
              <div style="text-align:right;font-size:10.5px;color: var(--t3, #5F5E5A)">Σ NPV portfolio</div>
              <div class="kd-wf-val" style="color:#0F6E56;font-size:13px">${{ fmt(npvWaterfall.total) }}</div>
              <div class="kd-wf-pct" style="color: var(--t3, #888780)">100%</div>
            </div>
          </div>
        </template>

        <!-- Pattern: SCATTER (irr) -->
        <template v-else-if="kpiType === 'irr'">
          <div class="kd-hint">Scatter · X = инвестиции ($M) · Y = IRR (%) · размер bubble = NPV</div>
          <div class="kd-scatter-wrap">
            <div class="kd-scatter-yaxis">
              <div style="top:0">40%</div>
              <div style="top:25%">30%</div>
              <div style="top:50%">20%</div>
              <div style="top:75%">10%</div>
              <div style="top:100%">0%</div>
            </div>
            <div class="kd-scatter">
              <div class="kd-scatter-avg" :style="{ top: irrStats.avgLineYPct + '%' }"></div>
              <div class="kd-scatter-avg-lbl" :style="{ top: (irrStats.avgLineYPct - 2) + '%' }">avg {{ irrStats.wAvg.toFixed(1) }}%</div>
              <div v-for="(pt, i) in scatterPoints" :key="i"
                class="kd-scatter-pt"
                :title="pt.title"
                :style="{
                  left: pt.xPct + '%',
                  top: pt.yPct + '%',
                  width: pt.size + 'px',
                  height: pt.size + 'px',
                  animationDelay: (300 + i * 80) + 'ms',
                }"></div>
              <div v-for="(pt, i) in scatterPoints" :key="'l'+i"
                class="kd-scatter-lbl"
                :style="{ left: pt.xPct + '%', top: (pt.yPct - 4) + '%' }">{{ pt.shortName }}</div>
            </div>
          </div>
          <div class="kd-scatter-xaxis"><span>$0</span><span>$500M</span><span>$1000M</span><span>$1500M</span><span>$2000M</span></div>
          <div class="kd-scatter-stats">
            <div><b>Top IRR:</b> {{ irrStats.topName }} {{ irrStats.topIrr.toFixed(1) }}%</div>
            <div><b style="color:#A32D2D">Под avg:</b> {{ irrStats.belowCount }} проектов</div>
            <div><b>Bubble size</b> = NPV (visual weight)</div>
          </div>
        </template>

        <!-- Fallback pattern: LIST -->
        <template v-else>
          <div class="kd-hint">Per-project breakdown · {{ fallbackList.length }} проектов</div>
          <div class="kd-list">
            <div v-for="(item, i) in fallbackList" :key="i" class="kd-list-row" :style="{ '--rd': (i * 50) + 'ms' } as any">
              <div class="kd-list-name">{{ item.name }}</div>
              <div class="kd-list-bar"><div class="kd-list-bar-fill" :style="{ width: item.barPct + '%', background: item.barColor }"></div></div>
              <div class="kd-list-primary" :style="{ color: item.primaryColor }">{{ item.primary }}</div>
              <div class="kd-list-secondary">{{ item.secondary }}</div>
            </div>
          </div>
        </template>

      </div>
    </div>
  </div>
</template>

<style scoped>
.kd-backdrop {
  position: fixed; inset: 0; background: rgba(15,18,40,.45);
  backdrop-filter: blur(8px); -webkit-backdrop-filter: blur(8px);
  z-index: 10000; display: flex; align-items: flex-start; justify-content: center;
  padding: 40px 20px; overflow-y: auto;
  animation: kdBgIn .25s ease both;
}
@keyframes kdBgIn { from { opacity: 0; } to { opacity: 1; } }

.kd-modal {
  background: var(--bg1, #fff); border-radius: 14px;
  box-shadow: 0 24px 64px rgba(15,23,60,.18), 0 8px 24px rgba(15,23,60,.08);
  width: 100%; max-width: 760px; position: relative; overflow: hidden;
  animation: kdModalIn .45s var(--ease-standard) both;
  font-family: -apple-system, system-ui, 'Segoe UI', sans-serif; color: #2C2C2A;
}
@keyframes kdModalIn { from { opacity: 0; transform: translateY(20px) scale(.96); } to { opacity: 1; transform: translateY(0) scale(1); } }

.kd-top-bar { position: absolute; top: 0; left: 0; right: 0; height: 3px; animation: kdDrawIn .9s var(--ease-standard) .15s both; transform-origin: left; }
.kd-top-shimmer { position: absolute; top: 0; left: 0; right: 0; height: 3px; background: linear-gradient(90deg, transparent, rgba(255,255,255,.6), transparent); animation: kdShimmer 5s ease-in-out 1.4s 1; transform: translateX(-120%); }
@keyframes kdDrawIn { from { clip-path: inset(0 100% 0 0); } to { clip-path: inset(0 0% 0 0); } }
@keyframes kdBreathe { 0%,100% { opacity: 1; } 50% { opacity: .45; } }
@keyframes kdShimmer { 0%,75% { transform: translateX(-120%); } 85%,100% { transform: translateX(120%); } }

.kd-header { padding: 14px 18px 10px; border-bottom: 1px solid #F0EFF5; display: flex; align-items: flex-start; justify-content: space-between; gap: 10px; }
.kd-eyebrow { font-size: 9px; color: var(--t3, var(--t-muted)); text-transform: uppercase; letter-spacing: .08em; font-weight: 500; }
.kd-title { font-size: 14px; font-weight: 500; letter-spacing: -.005em; margin-top: 2px; }
.kd-title b { font-size: 18px; letter-spacing: -.025em; }
.kd-close { width: 26px; height: 26px; border: 1px solid #E5E4EE; border-radius: 6px; display: flex; align-items: center; justify-content: center; background: var(--bg1, #fff); cursor: pointer; flex-shrink: 0; }
.kd-close:hover { background: #F4F3F9; }

.kd-body { padding: 14px 18px 18px; }
.kd-hint { font-size: 10px; color: var(--t3, var(--t-muted)); margin-bottom: 10px; }

/* TREEMAP */
.kd-treemap { display: flex; flex-direction: row; gap: 3px; height: 200px; margin-bottom: 10px; flex-wrap: wrap; }
.kd-tm-cell { min-width: 80px; min-height: 60px; border-radius: 5px; padding: 8px 10px; color: #fff; display: flex; flex-direction: column; justify-content: space-between; opacity: 0; animation: kdTmIn .5s var(--ease-standard) both; cursor: pointer; transition: transform .15s, box-shadow .15s; }
.kd-tm-cell:hover { transform: scale(1.02); box-shadow: 0 4px 12px rgba(0,0,0,.15); z-index: 2; }
@keyframes kdTmIn { from { opacity: 0; transform: scale(.7); } to { opacity: 1; transform: scale(1); } }
.kd-tm-name { font-size: 10.5px; font-weight: 500; line-height: 1.2; }
.kd-tm-val { font-size: 10px; font-variant-numeric: tabular-nums; opacity: .9; }

.kd-legend { display: flex; gap: 14px; font-size: 10px; color: var(--t3, #5F5E5A); flex-wrap: wrap; padding-top: 10px; border-top: 1px solid #F0EFF5; }
.kd-legend-item { display: flex; align-items: center; gap: 5px; }
.kd-legend-sq { width: 8px; height: 8px; border-radius: 2px; }

/* WATERFALL */
.kd-wf { display: flex; flex-direction: column; gap: 7px; }
.kd-wf-row { display: grid; grid-template-columns: 160px 1fr 60px 50px; gap: 10px; align-items: center; font-size: 10.5px; opacity: 0; animation: kdRowIn .4s var(--ease-standard) var(--rd, 0ms) both; }
@keyframes kdRowIn { from { opacity: 0; transform: translateX(-6px); } to { opacity: 1; transform: translateX(0); } }
.kd-wf-name { font-weight: 500; }
.kd-wf-track { height: 14px; background: #F0EFF5; border-radius: 3px; overflow: hidden; }
.kd-wf-bar { height: 100%; border-radius: 3px; animation: kdBarFill 1.2s var(--ease-standard) calc(var(--rd, 0ms) + 200ms) both; transform-origin: left; }
@keyframes kdBarFill { from { transform: scaleX(0); } to { transform: scaleX(1); } }
.kd-wf-val { text-align: right; font-variant-numeric: tabular-nums; font-weight: 500; color: #0F6E56; }
.kd-wf-pct { text-align: right; color: var(--t3, var(--t-muted)); font-size: 9.5px; }
.kd-wf-name-empty { color: var(--t3, var(--t-muted)); font-style: italic; font-weight: 400; }
.kd-wf-track-empty { height: 14px; background: repeating-linear-gradient(45deg, #F0EFF5, #F0EFF5 4px, #fafafa 4px, #fafafa 8px); border-radius: 3px; }
.kd-wf-row-total { padding-top: 8px; border-top: 2px solid #2C2C2A; margin-top: 4px; font-size: 11px; }

/* SCATTER */
.kd-scatter-wrap { position: relative; height: 200px; margin: 0 14px 0 36px; }
.kd-scatter-yaxis { position: absolute; left: -32px; top: 0; bottom: 0; width: 28px; }
.kd-scatter-yaxis div { position: absolute; right: 0; font-size: 8.5px; color: var(--t3, var(--t-muted)); transform: translateY(-50%); }
.kd-scatter { position: absolute; inset: 0; border-left: 1px solid #E5E4EE; border-bottom: 1px solid #E5E4EE; }
.kd-scatter-avg { position: absolute; left: 0; right: 0; border-top: 1px dashed var(--green); opacity: .5; }
.kd-scatter-avg-lbl { position: absolute; right: 2px; font-size: 8px; color: #0F6E56; font-weight: 500; background: var(--bg1, #fff); padding: 0 3px; transform: translateY(-100%); }
.kd-scatter-pt {
  position: absolute; background: rgba(127,119,221,.55); border: 1.5px solid #7F77DD; border-radius: 50%;
  transform: translate(-50%, -50%); opacity: 0;
  animation: kdTmIn .5s var(--ease-standard) both;
  cursor: pointer; transition: transform .15s, box-shadow .15s;
}
.kd-scatter-pt:hover { transform: translate(-50%, -50%) scale(1.15); box-shadow: 0 0 0 4px rgba(127,119,221,.18); z-index: 2; }
.kd-scatter-lbl { position: absolute; font-size: 8px; color: var(--t3, var(--t-muted)); transform: translate(-50%, -100%); white-space: nowrap; pointer-events: none; }
.kd-scatter-xaxis { display: flex; justify-content: space-between; margin: 4px 14px 0 36px; font-size: 8.5px; color: var(--t3, var(--t-muted)); }
.kd-scatter-stats { display: flex; gap: 14px; margin-top: 10px; padding-top: 8px; border-top: 1px solid #F0EFF5; font-size: 9.5px; color: var(--t3, #5F5E5A); flex-wrap: wrap; }
.kd-scatter-stats b { color: #2C2C2A; font-weight: 500; }

/* LIST fallback */
.kd-list { display: flex; flex-direction: column; gap: 8px; }
.kd-list-row { display: grid; grid-template-columns: 220px 1fr 80px; grid-template-rows: auto auto; gap: 4px 12px; align-items: center; font-size: 11px; padding: 6px 0; border-bottom: 1px solid #F4F3F9; opacity: 0; animation: kdRowIn .4s var(--ease-standard) var(--rd, 0ms) both; }
.kd-list-name { font-weight: 500; grid-row: 1; }
.kd-list-bar { grid-row: 1; height: 8px; background: #F0EFF5; border-radius: 3px; overflow: hidden; }
.kd-list-bar-fill { height: 100%; border-radius: 3px; animation: kdBarFill 1.2s var(--ease-standard) calc(var(--rd, 0ms) + 200ms) both; transform-origin: left; }
.kd-list-primary { grid-row: 1; text-align: right; font-weight: 500; font-variant-numeric: tabular-nums; }
.kd-list-secondary { grid-row: 2; grid-column: 1 / -1; font-size: 9.5px; color: var(--t3, var(--t-muted)); padding-left: 0; }
</style>
