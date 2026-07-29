<template>
  <div class="kps-scroll">
    <div class="kps-body">
      <!-- Hero metric -->
      <div class="kps-hero">
        <div class="kps-hero-l">
          <div class="kps-hero-top">
            <div class="kps-hero-eyebrow">{{ t("Общее выполнение KPI") }} · FY {{ summary.year }} · {{ periodLabel }} · {{ t("{n} компаний", { n: summary.co_count }) }}</div>
            <span class="kps-status" :class="execStatus.cls">{{ execStatus.label }}</span>
          </div>
          <div class="kps-hero-v">
            <span :style="{ color: overallColor }"><Odometer :value="overallText" /></span>
            <span class="kps-info" :title="formulaTip" :aria-label="t('Как считается общий процент')" tabindex="0"><svg viewBox="0 0 24 24" width="15" height="15" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><line x1="12" y1="16" x2="12" y2="12"/><line x1="12" y1="8" x2="12.01" y2="8"/></svg></span>
          </div>
          <div class="kps-hero-meta">
            {{ t("{n} индикаторов с весом", { n: summary.total_count }) }} ·
            <span class="kps-cnt-link" style="color: #1D9E75" @click="summary.over_count && $emit('open-status', 'over')">{{ t("{n} превышено", { n: summary.over_count }) }}</span> ·
            <span class="kps-cnt-link" style="color: #5AA77F" @click="summary.hit_count && $emit('open-status', 'hit')">{{ t("{n} на цели", { n: summary.hit_count }) }}</span> ·
            <span class="kps-cnt-link" style="color: #C97F1A" @click="summary.risk_count && $emit('open-status', 'risk')">{{ t("{n} в риске", { n: summary.risk_count }) }}</span> ·
            <span class="kps-cnt-link" style="color: #D14343" @click="summary.crit_count && $emit('open-status', 'crit')">{{ t("{n} критично", { n: summary.crit_count }) }}</span> ·
            <span class="kps-cnt-link" style="color: #B91C1C" @click="summary.fail_count && $emit('open-status', 'fail')">{{ t("{n} провалено", { n: summary.fail_count }) }}</span>
          </div>
          <div v-if="drivers.length || risks.length" class="kps-hero-drivers">
            <span v-if="drivers.length" class="kps-drv up">▲ {{ t("Драйверы:") }} {{ drivers.join(" · ") }}</span>
            <span v-if="risks.length" class="kps-drv dn">▼ {{ t("Зоны риска:") }} {{ risks.join(" · ") }}</span>
          </div>
        </div>

        <!-- Distribution sparkline -->
        <div class="kps-distribution">
          <div
            v-for="(s, i) in distSegments"
            :key="s.key"
            class="kps-dist-seg"
            :class="{ 'is-click': s.count > 0 }"
            :style="{ flex: s.count, backgroundColor: s.color, animationDelay: `${i * 70}ms` }"
            :title="s.count ? `${s.label}: ${s.count} · ${t('открыть список')}` : `${s.label}: 0`"
            @click="s.count && $emit('open-status', s.key)"
          />
        </div>

        <div class="kps-dist-leg">
          <span
            v-for="s in distSegments"
            :key="s.key"
            class="kps-dist-leg-i"
            :class="{ 'is-click': s.count > 0 }"
            @click="s.count && $emit('open-status', s.key)"
          >
            <span class="sw" :style="{ background: s.color }" />
            {{ s.label }} · {{ s.count }}
          </span>
        </div>
      </div>

      <div class="kps-grid">
        <!-- Companies leaderboard -->
        <div class="kps-w">
          <div class="kps-w-t">{{ t("Компании · по % выполнения") }}</div>
          <div class="kps-co-list">
            <div
              v-for="(c, i) in summary.by_company"
              :key="c.company_id"
              class="kps-co-row"
              :style="{ '--cl': c.sector_color || '#7F77DD', animationDelay: `${i * 30}ms` }"
              @click="$emit('open-company', c.company_id)"
            >
              <span class="nm">
                {{ c.co_name }}
                <span
                  v-if="c.weight_skew || c.low_sample"
                  class="kps-warn"
                  :title="c.weight_skew
                    ? t('Оценка перекошена: один индикатор тянет >60% веса компании (по сути выполнение одного KPI)')
                    : t('Оценка по малой выборке: {a} из {b} индикаторов', { a: c.count, b: c.ind_total })"
                >⚠</span>
              </span>
              <span class="meta">
                <span class="cnt-hit" :title="t('{n} на цели', { n: c.hit })">{{ c.hit }}</span>
                <span class="cnt-risk" :title="t('{n} в риске', { n: c.risk })">{{ c.risk }}</span>
                <span class="cnt-crit" :title="t('{n} критично', { n: c.crit })">{{ c.crit }}</span>
              </span>
              <span class="pc" :style="{ color: kpiStatusColor(c.pct) }">
                {{ fmt.fmtPercent(c.pct, { decimals: 1 }) }}
              </span>
            </div>
            <div v-if="!summary.by_company.length" class="kps-empty">{{ t("Нет данных") }}</div>
          </div>
        </div>

        <!-- Sectors -->
        <div class="kps-w">
          <div class="kps-w-t">{{ t("По секторам") }}</div>
          <div class="kps-sec-list">
            <div
              v-for="s in summary.by_sector"
              :key="s.sector_code"
              class="kps-sec-row kps-sec-click"
              :style="{ animationDelay: `${summary.by_sector.indexOf(s) * 60}ms` }"
              @click="$emit('open-sector', s.sector_code, s.label)"
              :title="`${t('Открыть сектор')} · ${s.label}`"
            >
              <div class="kps-sec-row-l">
                <div class="kps-sec-name">{{ s.label }}</div>
                <div class="kps-sec-meta">{{ t("{n} компаний", { n: s.co_count }) }} · {{ t("{n} индикаторов", { n: s.count }) }}</div>
              </div>
              <div class="kps-sec-row-r">
                <div class="kps-sec-pct" :style="{ color: kpiStatusColor(s.pct ?? 0) }">
                  {{ fmt.fmtPercent(s.pct, { decimals: 1 }) }}
                </div>
                <div class="kps-sec-bar-wrap">
                  <div class="kps-sec-bar" :style="{ width: Math.min(150, s.pct ?? 0) / 1.5 + '%', backgroundColor: kpiBarFill(s.pct ?? 0) }" />
                </div>
              </div>
            </div>
            <div v-if="!summary.by_sector.length" class="kps-empty">{{ t("Нет данных") }}</div>
          </div>
        </div>

        <!-- Quarterly progress · vertical bar chart + detail grid -->
        <div class="kps-w">
          <div class="kps-w-t">{{ t("Прогресс по кварталам") }}</div>

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
                class="kps-q-chart-col is-click"
                :class="{ active: q.q === summary.period }"
                :style="{ animationDelay: `${i * 90}ms` }"
                @click="$emit('open-period', q.q)"
              >
                <div class="kps-q-chart-bar-wrap" :title="(q.fact != null
                    ? `${q.q.toUpperCase()}: ${q.fact.toFixed(1)}%`
                    : `${q.q.toUpperCase()}: ${t(quarterState(q) || '')}`) + ' · ' + t('открыть период')">
                  <div
                    v-if="q.fact != null"
                    class="kps-q-chart-bar"
                    :style="{
                      height: Math.min(150, q.fact) / 1.5 + '%',
                      backgroundColor: kpiBarFill(q.fact),
                      animationDelay: `${i * 90 + 80}ms`,
                    }"
                  >
                    <span class="kps-q-chart-val">{{ fmt.fmtPercent(q.fact, { decimals: 1 }) }}</span>
                  </div>
                  <div v-else class="kps-q-chart-bar-empty">{{ t(quarterState(q) || "") }}</div>
                </div>
                <div class="kps-q-chart-lbl">{{ q.q.toUpperCase() }}</div>
              </div>
            </div>
          </div>

          <!-- Compact cards below chart for tactile reference -->
          <div class="kps-q-grid">
            <div
              v-for="q in summary.by_quarter"
              :key="q.q"
              class="kps-q-cell is-click"
              :class="{ active: q.q === summary.period }"
              :title="`${q.q.toUpperCase()} · ${t('открыть период')}`"
              @click="$emit('open-period', q.q)"
            >
              <div class="kps-q-l">{{ q.q.toUpperCase() }}</div>
              <div v-if="q.fact != null" class="kps-q-v" :style="{ color: kpiStatusColor(q.fact) }">
                {{ fmt.fmtPercent(q.fact, { decimals: 1 }) }}
              </div>
              <div v-else class="kps-q-v kps-q-v-state">{{ t(quarterState(q) || "") }}</div>
              <div class="kps-q-bar-wrap">
                <div class="kps-q-bar" :style="{ width: Math.min(150, q.fact ?? 0) / 1.5 + '%', backgroundColor: q.fact != null ? kpiBarFill(q.fact) : '#B8B7B0' }" />
              </div>
            </div>
          </div>

          <!-- FY outlook -->
          <div class="kps-q-foot">
            <span>FY {{ summary.year }} · {{ t("закрыто {n} из 4 · текущий результат", { n: closedQ }) }}
              <b :style="{ color: overallColor }">{{ overallText }}</b></span>
            <span class="kps-q-foot-status" :class="execStatus.cls">{{ execStatus.label }}</span>
          </div>
          <div v-if="hasFutureQ" class="kps-q-note">{{ t("Данные за следующие кварталы появятся после закрытия периода.") }}</div>
        </div>
      </div>

      <!-- Achievements + Issues -->
      <div class="kps-grid-2">
        <div class="kps-w">
          <div class="kps-w-t" style="color:#1D9E75">↑ {{ t("Достижения · превышение плана") }}</div>
          <div class="kps-ind-list">
            <div
              v-for="(ind, i) in summary.achievements"
              :key="ind.ind_id"
              class="kps-ind-row good"
              :class="{ anomaly: isAnomaly(ind) }"
              :style="{ animationDelay: `${i * 50}ms` }"
            >
              <div class="kps-ind-body">
                <div class="kps-ind-name">{{ ind.name }}</div>
                <div class="kps-ind-meta">{{ ind.co_name }} · {{ ind.mgr }} · {{ t("вес") }} {{ weightVal(ind) }}</div>
                <div v-if="isAnomaly(ind)" class="kps-ind-flag" :title="t('Перевыполнение выше 150% — вероятно низкая база, разовый эффект или ошибка плана. Требуется пояснение руководителя.')">
                  ⚠ {{ t("аномальное перевыполнение · требуется пояснение") }}
                </div>
              </div>
              <div class="kps-ind-pcts">
                <div class="kps-ind-pct" :style="{ color: kpiStatusColor(ind.pct ?? 0) }">
                  {{ fmt.fmtPercent(ind.pct, { decimals: 0 }) }}
                </div>
                <div class="kps-ind-capped" :title="t('В индекс KPI идёт с ограничением 150%')">{{ t("в индексе {p}%", { p: cappedPct(ind) }) }}</div>
              </div>
            </div>
            <div v-if="!summary.achievements.length" class="kps-empty">{{ t("Нет достижений ≥105%") }}</div>
          </div>
        </div>

        <div class="kps-w">
          <div class="kps-w-t" style="color:#E24B4A">↓ {{ t("Зона внимания · отстают от плана") }}</div>
          <div class="kps-ind-list">
            <div
              v-for="(ind, i) in summary.issues"
              :key="ind.ind_id"
              class="kps-ind-row bad"
              :style="{ animationDelay: `${i * 50}ms` }"
            >
              <div class="kps-ind-body">
                <div class="kps-ind-name">{{ ind.name }}</div>
                <div class="kps-ind-meta">{{ ind.co_name }} · {{ ind.mgr }} · {{ t("вес") }} {{ weightVal(ind) }} · {{ t("откл") }} {{ deltaPp(ind) }}</div>
              </div>
              <div class="kps-ind-pct" :style="{ color: kpiStatusColor(ind.pct ?? 0) }">
                {{ fmt.fmtPercent(ind.pct, { decimals: 0 }) }}
              </div>
            </div>
            <div v-if="!summary.issues.length" class="kps-empty">{{ t("Нет отстающих с весом ≥5") }}</div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from "vue";
import { kpiStatusColor, type KpiSummary, type KpiIndPayload, type KpiStatus, num } from "@/api/bpKpi";
import { useFormatters } from "@/composables/useFormatters";
import { useI18n } from "@/composables/useI18n";
import Odometer from "@/components/Odometer.vue";

const fmt = useFormatters();
const { t } = useI18n();

const props = defineProps<{ summary: KpiSummary }>();
defineEmits<{
  (e: "open-company", id: string): void;
  (e: "open-sector", code: string, label: string): void;
  (e: "open-status", status: KpiStatus): void;
  (e: "open-period", q: "q1" | "q2" | "q3" | "q4"): void;
}>();

const overallText = computed(() => {
  const o = props.summary.overall;
  return fmt.fmtPercent(o, { decimals: 1 });
});

const overallColor = computed(() => {
  const o = props.summary.overall;
  return o == null ? "#94A3B8" : kpiStatusColor(o);
});

const distSegments = computed<{ key: KpiStatus; label: string; color: string; count: number }[]>(() => [
  { key: "over", label: t("Превышено"), color: "#5DC093", count: props.summary.over_count },
  { key: "hit", label: t("На цели"), color: "#93D3B0", count: props.summary.hit_count },
  { key: "risk", label: t("В риске"), color: "#EFB373", count: props.summary.risk_count },
  { key: "crit", label: t("Критично"), color: "#E2807F", count: props.summary.crit_count },
  { key: "fail", label: t("Провал"), color: "#C76A68", count: props.summary.fail_count },
]);

/**
 * Цвет ЗАЛИВКИ баров (мягкая пастель, единый стиль с «Рейтинг компаний
 * по исполнению»). Отдельно от kpiStatusColor, который остаётся для ТЕКСТА
 * (числа %, проценты в строках) — там читаемость важнее.
 */
function kpiBarFill(pct: number): string {
  if (pct >= 100) return "#5DC093";
  if (pct >= 95) return "#93D3B0";
  if (pct >= 75) return "#EFB373";
  if (pct >= 50) return "#E2807F";
  return "#C76A68";
}

const periodLabel = computed(() => {
  const p = props.summary.period;
  return p === "year" ? t("Год") : p.toUpperCase();
});

// ─── Executive status поверх процента ─────────────────────────────
// Управленческая интерпретация: % + доля критичных/проваленных KPI.
const execStatus = computed(() => {
  const s = props.summary;
  const o = s.overall;
  if (o == null || s.total_count === 0) return { label: t("Нет данных"), cls: "is-na" };
  const critFail = s.crit_count + s.fail_count;
  const critShare = s.total_count > 0 ? critFail / s.total_count : 0;
  if (o < 75 || critShare >= 0.35) return { label: t("Критично"), cls: "is-crit" };
  if (o < 90 || critShare >= 0.2) return { label: t("Риск"), cls: "is-risk" };
  if (o < 100 || critFail > 0) return { label: t("Зона внимания"), cls: "is-warn" };
  return { label: t("На цели"), cls: "is-ok" };
});

// Раскрытие формулы общего % (tooltip)
const formulaTip = computed(() =>
  t("Общее выполнение = среднее по компаниям (каждая компания весит одинаково — защита от инфляции весов одной компании).") + " " +
  t("Внутри компании KPI взвешены по своим весам: Σ(выполнение×вес) ÷ Σвес.") + " " +
  t("Перевыполнение учитывается с ограничением 150% — сверхвыполнение одного KPI не компенсирует провал другого сверх этого порога."),
);

// Драйверы успеха / зоны риска — по секторам
const drivers = computed(() =>
  props.summary.by_sector.filter((s) => (s.pct ?? 0) >= 100).slice(0, 3).map((s) => s.label),
);
const risks = computed(() =>
  props.summary.by_sector
    .filter((s) => s.pct != null && s.pct < 90)
    .sort((a, b) => (a.pct ?? 0) - (b.pct ?? 0))
    .slice(0, 3)
    .map((s) => s.label),
);

// raw% vs capped% + флаг аномалии
const CAP = 150;
function cappedPct(ind: KpiIndPayload): number {
  return Math.round(Math.min(ind.pct ?? 0, CAP));
}
function isAnomaly(ind: KpiIndPayload): boolean {
  return (ind.pct ?? 0) > CAP;
}
function deltaPp(ind: KpiIndPayload): string {
  const d = (ind.pct ?? 0) - 100;
  return (d >= 0 ? "+" : "−") + Math.abs(Math.round(d)) + " " + t("п.п.");
}
function weightVal(ind: KpiIndPayload): number {
  return num(ind.weight);
}

// ─── Квартальный прогресс: состояние будущих кварталов + FY outlook ─
const QORDER: Record<string, number> = { q1: 1, q2: 2, q3: 3, q4: 4 };
const curQIndex = computed(() => QORDER[props.summary.period] ?? 4);
function quarterState(q: { q: string; fact: number | null }): string | null {
  if (q.fact != null) return null;
  const idx = QORDER[q.q] ?? 4;
  if (props.summary.period !== "year" && idx > curQIndex.value) return "не начато";
  return "нет данных";
}
const closedQ = computed(() => props.summary.by_quarter.filter((q) => q.fact != null).length);
const hasFutureQ = computed(() =>
  props.summary.by_quarter.some((q) => quarterState(q) === "не начато"),
);
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
  /* Премиум-глянец: светлый верхний хайлайт поверх цвета сегмента. */
  background-image: linear-gradient(180deg, rgba(255, 255, 255, 0.30) 0%, rgba(255, 255, 255, 0) 55%);
  border-radius: 3px;
  animation: distGrow .8s var(--ease-standard) backwards;
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
  background: var(--card-bg, rgba(255, 255, 255, 0.82));
  backdrop-filter: blur(16px) saturate(1.5);
  -webkit-backdrop-filter: blur(16px) saturate(1.5);
  border: 1px solid var(--card-border, rgba(0, 0, 0, .05));
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
.kps-warn { color: #C97F1A; font-size: 11px; cursor: help; margin-left: 2px; }
.kps-co-row .meta { display: flex; gap: 6px; font-size: 10px; }
.kps-co-row .meta span {
  font-weight: 600;
  font-variant-numeric: tabular-nums;
  padding: 1px 5px;
  border-radius: 3px;
  min-width: 18px;
  text-align: center;
}
.cnt-hit { color: var(--green); background: rgba(29, 158, 117, .08); }
.cnt-risk { color: var(--amber); background: rgba(239, 159, 39, .08); }
.cnt-crit { color: var(--sev-high); background: rgba(226, 75, 74, .08); }

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
  border-radius: 3px;
  background-image: linear-gradient(180deg, rgba(255, 255, 255, 0.30) 0%, rgba(255, 255, 255, 0) 55%);
  transition: width .8s var(--ease-standard);
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
  animation: kpsQColIn .5s var(--ease-standard) both;
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
  /* Премиум-глянец сверху бара (под белым значением — текст с тенью читается). */
  background-image: linear-gradient(180deg, rgba(255, 255, 255, 0.30) 0%, rgba(255, 255, 255, 0) 55%);
  display: flex;
  align-items: flex-start;
  justify-content: center;
  padding-top: 4px;
  position: relative;
  /* animate from 0 height */
  transform-origin: bottom center;
  animation: kpsQBarRise .85s var(--ease-standard) both;
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
  min-height: 30px;
  padding: 5px 3px;
  border: 1.5px dashed rgba(15, 23, 60, .16);
  border-radius: 4px 4px 0 0;
  display: flex;
  align-items: center;
  justify-content: center;
  text-align: center;
  color: rgba(15, 23, 60, .5);
  font-size: 8.5px;
  font-weight: 600;
  letter-spacing: .02em;
  line-height: 1.2;
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
.kps-q-bar { height: 100%; border-radius: 2px; background-image: linear-gradient(180deg, rgba(255, 255, 255, 0.30) 0%, rgba(255, 255, 255, 0) 55%); transition: width .8s var(--ease-standard); }

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
  animation: uzaStripeDrawIn .5s var(--ease-standard) both;
  pointer-events: none;
}
.kps-ind-row.good::before { background: var(--green); }
.kps-ind-row.bad::before  { background: var(--sev-high); }

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

/* ─── P0: executive status, формула, capped%, состояния кварталов ─── */
.kps-hero-top { display: flex; align-items: center; justify-content: space-between; gap: 12px; }
.kps-status {
  flex-shrink: 0; font-size: 11px; font-weight: 700; letter-spacing: .02em;
  padding: 4px 12px; border-radius: 999px;
}
.kps-status.is-ok   { color: #0F6E56; background: rgba(29, 158, 117, .13); }
.kps-status.is-warn { color: #A36500; background: rgba(239, 159, 39, .16); }
.kps-status.is-risk { color: #B25E00; background: rgba(224, 122, 0, .15); }
.kps-status.is-crit { color: #B0322E; background: rgba(209, 67, 67, .13); }
.kps-status.is-na   { color: #64748B; background: rgba(100, 116, 139, .12); }

.kps-info {
  display: inline-flex; align-items: center; justify-content: center;
  margin-left: 10px; color: rgba(108, 92, 231, .5);
  cursor: help; vertical-align: middle;
  transition: color .14s;
}
.kps-info svg { display: block; }
.kps-info:hover { color: #6C5CE7; }

.kps-hero-drivers { display: flex; flex-wrap: wrap; gap: 16px; margin-top: 8px; font-size: 11px; font-weight: 600; }
.kps-drv.up { color: #1D9E75; }
.kps-drv.dn { color: #D14343; }

/* Achievements: raw vs capped + anomaly */
.kps-ind-pcts { flex-shrink: 0; display: flex; flex-direction: column; align-items: flex-end; gap: 1px; }
.kps-ind-capped { font-size: 9.5px; font-weight: 600; color: rgba(15, 23, 60, .5); white-space: nowrap; }
.kps-ind-flag {
  margin-top: 3px; font-size: 9.5px; font-weight: 700; color: #A36500;
  background: rgba(224, 146, 47, .14); border-radius: 4px; padding: 2px 6px; display: inline-block;
}
.kps-ind-row.anomaly { background: rgba(224, 146, 47, .07); }
.kps-ind-row.anomaly::before { background: var(--amber, #E0922F) !important; }

/* Quarterly FY outlook */
.kps-q-v-state { font-size: 11px !important; font-weight: 600 !important; color: rgba(15, 23, 60, .5) !important; }
.kps-q-foot {
  display: flex; align-items: center; justify-content: space-between; gap: 10px; flex-wrap: wrap;
  margin-top: 12px; padding-top: 10px; border-top: .5px solid rgba(15, 23, 60, .08);
  font-size: 11px; color: rgba(15, 23, 60, .62);
}
.kps-q-foot b { font-weight: 700; }
.kps-q-foot-status { font-size: 10px; font-weight: 700; padding: 2px 9px; border-radius: 999px; }
.kps-q-foot-status.is-ok   { color: #0F6E56; background: rgba(29, 158, 117, .13); }
.kps-q-foot-status.is-warn { color: #A36500; background: rgba(239, 159, 39, .16); }
.kps-q-foot-status.is-risk { color: #B25E00; background: rgba(224, 122, 0, .15); }
.kps-q-foot-status.is-crit { color: #B0322E; background: rgba(209, 67, 67, .13); }
.kps-q-foot-status.is-na   { color: #64748B; background: rgba(100, 116, 139, .12); }
.kps-q-note { margin-top: 6px; font-size: 10px; font-style: italic; color: rgba(15, 23, 60, .5); }

/* P0: усиленный контраст вторичного текста */
.kps-hero-eyebrow { color: rgba(15, 23, 60, .62); }
.kps-hero-meta { color: rgba(15, 23, 60, .72); font-weight: 500; }
.kps-w-t { color: rgba(15, 23, 60, .62); }
.kps-sec-meta { color: rgba(15, 23, 60, .6); }
.kps-ind-meta { color: rgba(15, 23, 60, .64); }
.kps-dist-leg { color: rgba(15, 23, 60, .62); }

/* Clickable distribution + counts → status drill modal */
.kps-dist-seg.is-click { cursor: pointer; transition: filter .15s, transform .15s; }
.kps-dist-seg.is-click:hover { filter: brightness(1.12) saturate(1.1); transform: scaleY(1.35); }
.kps-dist-leg-i.is-click { cursor: pointer; padding: 2px 6px; border-radius: 5px; transition: background .15s; }
.kps-dist-leg-i.is-click:hover { background: rgba(15, 23, 60, .05); }
.kps-cnt-link { cursor: pointer; border-radius: 4px; padding: 0 2px; transition: background .15s; text-decoration: underline; text-decoration-color: transparent; text-underline-offset: 2px; }
.kps-cnt-link:hover { background: rgba(15, 23, 60, .05); text-decoration-color: currentColor; }

/* Clickable quarters → filter dashboard to that period */
.kps-q-chart-col.is-click { cursor: pointer; }
.kps-q-chart-col.is-click:hover .kps-q-chart-bar { filter: brightness(1.08); }
.kps-q-chart-col.is-click:hover .kps-q-chart-lbl { color: #6C5CE7; }
.kps-q-chart-col.active .kps-q-chart-lbl { color: #6C5CE7; font-weight: 700; }
.kps-q-cell { transition: background .15s, box-shadow .15s; }
.kps-q-cell.is-click { cursor: pointer; }
.kps-q-cell.is-click:hover { background: rgba(108, 92, 231, .07); }
.kps-q-cell.active { box-shadow: inset 0 0 0 1.5px rgba(108, 92, 231, .5); background: rgba(108, 92, 231, .06); }
</style>
