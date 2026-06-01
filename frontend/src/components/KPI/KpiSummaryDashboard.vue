<template>
  <div class="kps-scroll">
    <div class="kps-body">
      <!-- Hero metric -->
      <div class="kps-hero">
        <div class="kps-hero-l">
          <div class="kps-hero-eyebrow">Общее выполнение KPI · {{ summary.co_count }} компаний</div>
          <div class="kps-hero-v">
            <span :style="{ color: overallColor }">{{ overallText }}</span>
          </div>
          <div class="kps-hero-meta">
            {{ summary.total_count }} индикаторов с весом ·
            <span style="color: #1D9E75">{{ summary.over_count }} превышено</span> ·
            <span style="color: #7DC4A0">{{ summary.hit_count }} на цели</span> ·
            <span style="color: #EF9F27">{{ summary.risk_count }} в риске</span> ·
            <span style="color: #E24B4A">{{ summary.crit_count + summary.fail_count }} критично</span>
          </div>
        </div>

        <!-- Distribution sparkline -->
        <div class="kps-distribution">
          <div
            v-for="(s, i) in distSegments"
            :key="s.key"
            class="kps-dist-seg"
            :style="{ flex: s.count, background: s.color, animationDelay: `${i * 70}ms` }"
            :title="`${s.label}: ${s.count}`"
          />
        </div>

        <div class="kps-dist-leg">
          <span v-for="s in distSegments" :key="s.key" class="kps-dist-leg-i">
            <span class="sw" :style="{ background: s.color }" />
            {{ s.label }} · {{ s.count }}
          </span>
        </div>
      </div>

      <div class="kps-grid">
        <!-- Companies leaderboard -->
        <div class="kps-w">
          <div class="kps-w-t">Компании · по % выполнения</div>
          <div class="kps-co-list">
            <div
              v-for="(c, i) in summary.by_company"
              :key="c.company_id"
              class="kps-co-row"
              :style="{ '--cl': c.sector_color || '#7F77DD', animationDelay: `${i * 30}ms` }"
              @click="$emit('open-company', c.company_id)"
            >
              <span class="nm">{{ c.co_name }}</span>
              <span class="meta">
                <span class="cnt-hit" :title="`${c.hit} на цели`">{{ c.hit }}</span>
                <span class="cnt-risk" :title="`${c.risk} в риске`">{{ c.risk }}</span>
                <span class="cnt-crit" :title="`${c.crit} критично`">{{ c.crit }}</span>
              </span>
              <span class="pc" :style="{ color: kpiStatusColor(c.pct) }">
                {{ fmt.fmtPercent(c.pct, { decimals: 1 }) }}
              </span>
            </div>
            <div v-if="!summary.by_company.length" class="kps-empty">Нет данных</div>
          </div>
        </div>

        <!-- Sectors -->
        <div class="kps-w">
          <div class="kps-w-t">По секторам</div>
          <div class="kps-sec-list">
            <div
              v-for="s in summary.by_sector"
              :key="s.sector_code"
              class="kps-sec-row kps-sec-click"
              :style="{ animationDelay: `${summary.by_sector.indexOf(s) * 60}ms` }"
              @click="$emit('open-sector', s.sector_code, s.label)"
              :title="`Открыть сектор · ${s.label}`"
            >
              <div class="kps-sec-row-l">
                <div class="kps-sec-name">{{ s.label }}</div>
                <div class="kps-sec-meta">{{ s.co_count }} компаний · {{ s.count }} индикаторов</div>
              </div>
              <div class="kps-sec-row-r">
                <div class="kps-sec-pct" :style="{ color: kpiStatusColor(s.pct ?? 0) }">
                  {{ fmt.fmtPercent(s.pct, { decimals: 1 }) }}
                </div>
                <div class="kps-sec-bar-wrap">
                  <div class="kps-sec-bar" :style="{ width: Math.min(150, s.pct ?? 0) / 1.5 + '%', background: kpiStatusColor(s.pct ?? 0) }" />
                </div>
              </div>
            </div>
            <div v-if="!summary.by_sector.length" class="kps-empty">Нет данных</div>
          </div>
        </div>

        <!-- Quarterly progress · vertical bar chart + detail grid -->
        <div class="kps-w">
          <div class="kps-w-t">Прогресс по кварталам</div>

          <!-- Bar chart: 4 vertical bars Q1-Q4, dashed 100% baseline, animated fill -->
          <div class="kps-q-chart">
            <!-- 100% baseline -->
            <div class="kps-q-chart-baseline" />
            <span class="kps-q-chart-baseline-lbl">100%</span>

            <!-- Bars -->
            <div class="kps-q-chart-bars">
              <div
                v-for="(q, i) in summary.by_quarter"
                :key="`bar-${q.q}`"
                class="kps-q-chart-col"
                :style="{ animationDelay: `${i * 90}ms` }"
              >
                <div class="kps-q-chart-bar-wrap" :title="q.fact != null
                    ? `${q.q.toUpperCase()}: ${q.fact.toFixed(1)}%`
                    : `${q.q.toUpperCase()}: нет данных`">
                  <div
                    v-if="q.fact != null"
                    class="kps-q-chart-bar"
                    :style="{
                      height: Math.min(150, q.fact) / 1.5 + '%',
                      background: kpiStatusColor(q.fact),
                      animationDelay: `${i * 90 + 80}ms`,
                    }"
                  >
                    <span class="kps-q-chart-val">{{ Math.round(q.fact) }}%</span>
                  </div>
                  <div v-else class="kps-q-chart-bar-empty">—</div>
                </div>
                <div class="kps-q-chart-lbl">{{ q.q.toUpperCase() }}</div>
              </div>
            </div>
          </div>

          <!-- Compact cards below chart for tactile reference -->
          <div class="kps-q-grid">
            <div v-for="q in summary.by_quarter" :key="q.q" class="kps-q-cell">
              <div class="kps-q-l">{{ q.q.toUpperCase() }}</div>
              <div class="kps-q-v" :style="{ color: q.fact != null ? kpiStatusColor(q.fact) : '#94A3B8' }">
                {{ fmt.fmtPercent(q.fact, { decimals: 1 }) }}
              </div>
              <div class="kps-q-bar-wrap">
                <div class="kps-q-bar" :style="{ width: Math.min(150, q.fact ?? 0) / 1.5 + '%', background: q.fact != null ? kpiStatusColor(q.fact) : '#94A3B8' }" />
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- Achievements + Issues -->
      <div class="kps-grid-2">
        <div class="kps-w">
          <div class="kps-w-t" style="color:#1D9E75">↑ Достижения · превышение плана</div>
          <div class="kps-ind-list">
            <div
              v-for="(ind, i) in summary.achievements"
              :key="ind.ind_id"
              class="kps-ind-row good"
              :style="{ animationDelay: `${i * 50}ms` }"
            >
              <div class="kps-ind-body">
                <div class="kps-ind-name">{{ ind.name }}</div>
                <div class="kps-ind-meta">{{ ind.co_name }} · {{ ind.mgr }}</div>
              </div>
              <div class="kps-ind-pct" :style="{ color: kpiStatusColor(ind.pct ?? 0) }">
                {{ fmt.fmtPercent(ind.pct, { decimals: 0 }) }}
              </div>
            </div>
            <div v-if="!summary.achievements.length" class="kps-empty">Нет достижений ≥105%</div>
          </div>
        </div>

        <div class="kps-w">
          <div class="kps-w-t" style="color:#E24B4A">↓ Зона внимания · отстают от плана</div>
          <div class="kps-ind-list">
            <div
              v-for="(ind, i) in summary.issues"
              :key="ind.ind_id"
              class="kps-ind-row bad"
              :style="{ animationDelay: `${i * 50}ms` }"
            >
              <div class="kps-ind-body">
                <div class="kps-ind-name">{{ ind.name }}</div>
                <div class="kps-ind-meta">{{ ind.co_name }} · {{ ind.mgr }} · вес {{ ind.weight }}</div>
              </div>
              <div class="kps-ind-pct" :style="{ color: kpiStatusColor(ind.pct ?? 0) }">
                {{ fmt.fmtPercent(ind.pct, { decimals: 0 }) }}
              </div>
            </div>
            <div v-if="!summary.issues.length" class="kps-empty">Нет отстающих с весом ≥5</div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from "vue";
import { kpiStatusColor, type KpiSummary } from "@/api/bpKpi";
import { useFormatters } from "@/composables/useFormatters";

const fmt = useFormatters();

const props = defineProps<{ summary: KpiSummary }>();
defineEmits<{
  (e: "open-company", id: string): void;
  (e: "open-sector", code: string, label: string): void;
}>();

const overallText = computed(() => {
  const o = props.summary.overall;
  return fmt.fmtPercent(o, { decimals: 1 });
});

const overallColor = computed(() => {
  const o = props.summary.overall;
  return o == null ? "#94A3B8" : kpiStatusColor(o);
});

const distSegments = computed(() => [
  { key: "over", label: "Превышено", color: "#1D9E75", count: props.summary.over_count },
  { key: "hit", label: "На цели", color: "#7DC4A0", count: props.summary.hit_count },
  { key: "risk", label: "В риске", color: "#EF9F27", count: props.summary.risk_count },
  { key: "crit", label: "Критично", color: "#E24B4A", count: props.summary.crit_count },
  { key: "fail", label: "Провал", color: "#B91C1C", count: props.summary.fail_count },
]);
</script>

<style scoped>
.kps-scroll { background: #f4f3f9; min-height: 100%; }
.kps-body { padding: 18px 22px 28px; }

/* Hero */
.kps-hero {
  background: linear-gradient(135deg, #fff 0%, #FAFAFD 100%);
  border: 1px solid rgba(15, 23, 60, .06);
  border-radius: 14px;
  padding: 18px 22px;
  margin-bottom: 14px;
}
.kps-hero-eyebrow {
  font-size: 10px;
  font-weight: 600;
  letter-spacing: .07em;
  text-transform: uppercase;
  color: rgba(15, 23, 60, .55);
}
.kps-hero-v {
  font-size: 48px;
  font-weight: 300;
  letter-spacing: -.04em;
  margin-top: 4px;
  font-variant-numeric: tabular-nums;
}
.kps-hero-meta {
  font-size: 11.5px;
  color: rgba(15, 23, 60, .6);
  margin-top: 6px;
}

.kps-distribution {
  display: flex;
  height: 12px;
  gap: 1px;
  border-radius: 6px;
  overflow: hidden;
  margin-top: 14px;
  background: rgba(15, 23, 60, .04);
}
.kps-dist-seg {
  height: 100%;
  animation: distGrow .8s cubic-bezier(0.34, 1.2, 0.64, 1) backwards;
  transform-origin: left;
}
@keyframes distGrow { from { transform: scaleX(0); } to { transform: scaleX(1); } }

.kps-dist-leg {
  display: flex;
  flex-wrap: wrap;
  gap: 14px;
  margin-top: 10px;
  font-size: 10.5px;
  color: rgba(15, 23, 60, .55);
}
.kps-dist-leg-i { display: flex; align-items: center; gap: 5px; }
.kps-dist-leg-i .sw { width: 10px; height: 10px; border-radius: 2px; }

/* Grid */
.kps-grid {
  display: grid;
  grid-template-columns: 1.4fr 1fr 1fr;
  gap: 12px;
  margin-bottom: 14px;
}
@media (max-width: 1200px) { .kps-grid { grid-template-columns: 1fr; } }

.kps-grid-2 {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 12px;
}
@media (max-width: 1100px) { .kps-grid-2 { grid-template-columns: 1fr; } }

.kps-w {
  background: var(--bg1, #fff);
  border: 1px solid rgba(0, 0, 0, .05);
  border-radius: 12px;
  padding: 14px 16px;
  display: flex;
  flex-direction: column;
}
.kps-w-t {
  font-size: 10.5px;
  font-weight: 600;
  letter-spacing: .06em;
  text-transform: uppercase;
  color: rgba(15, 23, 60, .55);
  margin-bottom: 10px;
}

/* Companies */
.kps-co-list { display: flex; flex-direction: column; gap: 4px; }
.kps-co-row {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 7px 10px 7px 14px;
  background: #FCFAFF;
  border-radius: 6px;
  cursor: pointer;
  transition: background .12s, transform .12s;
  position: relative;
  overflow: hidden;
  animation: rowFade .35s ease backwards;
}
@keyframes rowFade { from { opacity: 0; transform: translateX(-3px); } to { opacity: 1; transform: translateX(0); } }

/* Removed per user request 2026-05-23: top-stripe sector accent
   на каждой строке (зелёный/амбер/красный) — был визуальный шум.
   Если нужно вернуть — восстановить `.kps-co-row::before` блок:
     background: var(--cl); animation: uzaStripeDrawIn .5s ...   */

.kps-co-row:hover { background: #F4F1FE; transform: translateX(2px); }
.kps-co-row .nm {
  flex: 1;
  font-size: 11.5px;
  font-weight: 500;
  color: var(--t1, #1e2a4a);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.kps-co-row .meta { display: flex; gap: 6px; font-size: 10px; }
.kps-co-row .meta span {
  font-weight: 600;
  font-variant-numeric: tabular-nums;
  padding: 1px 5px;
  border-radius: 3px;
  min-width: 18px;
  text-align: center;
}
.cnt-hit { color: #1D9E75; background: rgba(29, 158, 117, .08); }
.cnt-risk { color: #EF9F27; background: rgba(239, 159, 39, .08); }
.cnt-crit { color: #E24B4A; background: rgba(226, 75, 74, .08); }

.kps-co-row .pc {
  font-weight: 600;
  font-size: 12px;
  min-width: 50px;
  text-align: right;
  font-variant-numeric: tabular-nums;
}

/* Sectors */
.kps-sec-list { display: flex; flex-direction: column; gap: 8px; }
.kps-sec-row {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 7px 10px;
  background: var(--bg2, #FAFAFD);
  border-radius: 6px;
  animation: rowFade .35s ease backwards;
}
.kps-sec-row-l { flex: 1; min-width: 0; }
.kps-sec-name { font-size: 11.5px; font-weight: 500; color: var(--t1, #1e2a4a); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.kps-sec-meta { font-size: 10px; color: rgba(15, 23, 60, .5); margin-top: 1px; }
.kps-sec-row-r { flex-shrink: 0; min-width: 100px; text-align: right; }
.kps-sec-pct { font-size: 13px; font-weight: 600; font-variant-numeric: tabular-nums; }
.kps-sec-bar-wrap {
  height: 4px;
  background: rgba(15, 23, 60, .05);
  border-radius: 2px;
  margin-top: 4px;
  overflow: hidden;
}
.kps-sec-bar {
  height: 100%;
  border-radius: 2px;
  transition: width .8s cubic-bezier(0.34, 1.2, 0.64, 1);
}

/* Quarterly · vertical bar chart */
.kps-q-chart {
  position: relative;
  height: 180px;
  margin: 12px 4px 14px;
  padding: 4px 6px 0;
}
.kps-q-chart-baseline {
  position: absolute;
  left: 6px; right: 6px;
  top: 4px;
  border-top: 1px dashed rgba(15, 23, 60, .18);
  pointer-events: none;
}
.kps-q-chart-baseline-lbl {
  position: absolute;
  right: 6px; top: -6px;
  background: var(--bg1, #fff);
  padding: 0 5px;
  font-size: 9px;
  color: rgba(15, 23, 60, .45);
  letter-spacing: .04em;
}
.kps-q-chart-bars {
  position: absolute;
  inset: 4px 6px 0;
  display: flex;
  align-items: flex-end;
  gap: 12%;
  justify-content: space-around;
}
.kps-q-chart-col {
  display: flex;
  flex-direction: column;
  align-items: center;
  flex: 1;
  min-width: 0;
  height: 100%;
  opacity: 0;
  animation: kpsQColIn .5s cubic-bezier(.34, 1.2, .64, 1) both;
}
@keyframes kpsQColIn {
  from { opacity: 0; transform: translateY(8px); }
  to   { opacity: 1; transform: translateY(0); }
}
.kps-q-chart-bar-wrap {
  flex: 1;
  width: 100%;
  display: flex;
  align-items: flex-end;
  justify-content: center;
  min-height: 0;
  position: relative;
}
.kps-q-chart-bar {
  width: 100%;
  max-width: 56px;
  min-height: 4px;
  border-radius: 4px 4px 0 0;
  display: flex;
  align-items: flex-start;
  justify-content: center;
  padding-top: 4px;
  position: relative;
  /* animate from 0 height */
  transform-origin: bottom center;
  animation: kpsQBarRise .85s cubic-bezier(.34, 1.2, .64, 1) both;
  box-shadow: 0 1px 4px rgba(15, 23, 60, .08);
}
@keyframes kpsQBarRise {
  from { transform: scaleY(0); }
  to   { transform: scaleY(1); }
}
.kps-q-chart-val {
  font-size: 10px;
  font-weight: 600;
  color: #fff;
  letter-spacing: -.01em;
  font-variant-numeric: tabular-nums;
  text-shadow: 0 1px 2px rgba(0, 0, 0, .15);
  white-space: nowrap;
}
.kps-q-chart-bar-empty {
  width: 100%;
  max-width: 56px;
  height: 28px;
  border: 1.5px dashed rgba(15, 23, 60, .14);
  border-radius: 4px 4px 0 0;
  display: flex;
  align-items: center;
  justify-content: center;
  color: rgba(15, 23, 60, .35);
  font-size: 13px;
  font-weight: 500;
}
.kps-q-chart-lbl {
  font-size: 10px;
  font-weight: 600;
  letter-spacing: .07em;
  color: rgba(15, 23, 60, .55);
  margin-top: 6px;
  text-transform: uppercase;
}

/* Quarterly */
.kps-q-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 8px;
  margin-top: 0;
}
.kps-q-cell {
  background: var(--bg2, #FAFAFD);
  padding: 10px 12px;
  border-radius: 6px;
}
.kps-q-l {
  font-size: 9.5px;
  font-weight: 600;
  letter-spacing: .07em;
  color: rgba(15, 23, 60, .55);
}
.kps-q-v {
  font-size: 18px;
  font-weight: 400;
  letter-spacing: -.025em;
  margin-top: 2px;
  font-variant-numeric: tabular-nums;
}
.kps-q-bar-wrap {
  height: 3px;
  background: rgba(15, 23, 60, .05);
  border-radius: 1px;
  margin-top: 4px;
  overflow: hidden;
}
.kps-q-bar { height: 100%; transition: width .8s cubic-bezier(0.34, 1.2, 0.64, 1); }

/* Indicators */
.kps-ind-list { display: flex; flex-direction: column; gap: 6px; }
.kps-ind-row {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 8px 12px;
  border-radius: 6px;
  animation: rowFade .35s ease backwards;
}
.kps-ind-row.good { background: rgba(29, 158, 117, .04); position: relative; overflow: hidden; }
.kps-ind-row.bad  { background: rgba(226, 75, 74, .04);  position: relative; overflow: hidden; }
.kps-ind-row.good::before, .kps-ind-row.bad::before {
  content: ""; position: absolute; top: 0; left: 0; right: 0;
  height: 2px;
  border-top-left-radius: inherit; border-top-right-radius: inherit;
  animation: uzaStripeDrawIn .5s cubic-bezier(0.34, 1.2, 0.64, 1) both;
  pointer-events: none;
}
.kps-ind-row.good::before { background: #1D9E75; }
.kps-ind-row.bad::before  { background: #E24B4A; }

.kps-ind-body { flex: 1; min-width: 0; }
.kps-ind-name {
  font-size: 11.5px;
  font-weight: 500;
  color: var(--t1, #1e2a4a);
  line-height: 1.3;
}
.kps-ind-meta { font-size: 10px; color: rgba(15, 23, 60, .55); margin-top: 2px; }
.kps-ind-pct { font-size: 14px; font-weight: 600; font-variant-numeric: tabular-nums; flex-shrink: 0; }

.kps-empty {
  font-size: 11px;
  color: rgba(15, 23, 60, .45);
  font-style: italic;
  padding: 12px 0;
  text-align: center;
}

/* ─── Pack 8.4: sector drill-down clickability ─── */
.kps-sec-click { cursor: pointer; transition: transform .15s, background .15s; }
.kps-sec-click:hover { background: rgba(127, 119, 221, .03); transform: translateX(1px); }
</style>
