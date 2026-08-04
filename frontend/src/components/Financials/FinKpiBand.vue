<script setup lang="ts">
// ============================================================================
// Top KPI band — 5 or 6 cards (depending on standard).
//
// Layout from legacy screens:
//   1. Совокупная выручка       (с YoY %)
//   2. Операционная маржа       (с операционной прибылью на сабе)
//   3. EBITDA                   (с маржой % на сабе)
//   4. Чистая маржа             (с чистой прибылью на сабе)
//   5. Убыточные                (количество)
//   6. Внедрение стандартов     (только МСФО — с прогресс-кольцом)
// ============================================================================

import { computed, onMounted } from "vue";
import type { PortfolioKpis } from "./financialsHelpers";
import { fmtBigNumber, fmtPctSigned, ensureFinancialsCss } from "./financialsHelpers";
import { fmtSubsidySum } from "@/api/subsidies";
import { useFormatters } from "@/composables/useFormatters";
import Odometer from "@/components/Odometer.vue";
import { useI18n } from "@/composables/useI18n";
import { i18nKey } from "@/locale/keys";

const fmt = useFormatters();
const { t } = useI18n();

const props = defineProps<{
  kpis: PortfolioKpis | null;
  unit: "bln" | "mln";
  currency: string;
  standard: "IFRS" | "NSBU";
  /** Companies count "X из Y" — visual indicator above cards */
  inYear: number;
  totalCompanies: number;
  noDataCount: number;
  /** Σ субсидий (raw сум) для метрики-карточки; null = не загружено */
  subsidiesTotal?: number | null;
}>();

// Pack 7.48: drill-down events
type KpiId = "revenue" | "opMargin" | "ebitda" | "netMargin" | "loss";
const emit = defineEmits<{
  (e: "drill", kpi: KpiId): void;
  (e: "open-subsidies"): void;
}>();
function drill(k: KpiId) { emit("drill", k); }

// Субсидии: формат в сум (млрд/трлн), не зависит от валюты страницы
const subsidiesFmt = computed(() => fmtSubsidySum(props.subsidiesTotal ?? null));

onMounted(ensureFinancialsCss);

const unitKey = computed(() => props.unit === "bln" ? i18nKey("млрд") : i18nKey("млн"));
const unitSuffix = computed(() => `${t(unitKey.value)} ${props.currency}`);

const opProfitTxt = computed(() =>
  props.kpis ? t("Опер. прибыль {v}", { v: fmtBigNumber(props.kpis.totalOpProfit, props.unit) }) : "—",
);
const netProfitTxt = computed(() =>
  props.kpis
    ? t("Чистая прибыль {v} {pp} п.п.", {
        v: fmtBigNumber(props.kpis.totalNetProfit, props.unit),
        pp: fmt.fmtNumber(props.kpis.netProfitDeltaPp, { decimals: 0, signed: true }),
      })
    : "",
);
const lossOutOf = computed(() =>
  props.kpis ? t("из {n} с данными по прибыли", { n: props.kpis.companiesWithProfit }) : "",
);

// Крупное число суммирует всех, кто сдал отчётность за год, а процент считается
// like-for-like. Когда часть компаний ещё не сдала текущий год, итог оказывается
// МЕНЬШЕ прошлогоднего, а процент — плюсовым, и это читается как ошибка. Поэтому
// под процентом всегда пишем, по скольким компаниям он посчитан, и сколько
// выпало из итога.
const revenueYoYTxt = computed(() => {
  const k = props.kpis;
  if (!k) return "";
  if (k.revenueYoYPct == null) return t("нет сопоставимого прошлого года");
  return t("{v} к пред. году", { v: fmtPctSigned(k.revenueYoYPct) });
});
const revenueYoYNote = computed(() => {
  const k = props.kpis;
  if (!k || k.revenueYoYPct == null) return "";
  const base = t("сравнение по {n} сопоставимым", { n: k.revenueYoYPairCount });
  return k.revenueMissingVsPrev > 0
    ? `${base} · ${t("{n} ещё не сдали отчётность", { n: k.revenueMissingVsPrev })}`
    : base;
});
const revenueTitle = computed(() => {
  const k = props.kpis;
  if (!k) return "";
  return k.revenueMissingVsPrev > 0
    ? t("Итог — сумма по {inYear} компаниям, сдавшим отчётность за год. Процент — рост по {pair} компаниям, у которых есть данные и за прошлый год. Ещё {gone} компаний отчитались за прошлый год, но не за текущий, поэтому итог меньше прошлогоднего.",
        { inYear: k.revenueCompaniesInYear, pair: k.revenueYoYPairCount, gone: k.revenueMissingVsPrev })
    : t("Итог — сумма по {inYear} компаниям; процент — рост по {pair} сопоставимым.",
        { inYear: k.revenueCompaniesInYear, pair: k.revenueYoYPairCount });
});
</script>

<template>
  <!-- Coverage indicator strip (above cards) -->
  <div class="fkb-cover">
    <span class="fkb-cover-pill fkb-cover-ok">
      <span class="fkb-dot" /> {{ t("{n} из {m}", { n: inYear, m: totalCompanies }) }}
    </span>
    <span v-if="noDataCount > 0" class="fkb-cover-pill fkb-cover-warn">
      <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor"
           stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round">
        <circle cx="12" cy="12" r="10"/>
        <line x1="12" y1="8" x2="12" y2="12"/>
        <line x1="12" y1="16" x2="12.01" y2="16"/>
      </svg>
      {{ t("{n} без данных", { n: noDataCount }) }}
    </span>
    <span class="fkb-cover-note">{{ t("YoY рассчитан по like-for-like basket (только компании с данными в обоих годах)") }}</span>
  </div>

  <div class="fkb-grid kpi-rail">
    <!-- 1. Совокупная выручка -->
    <div class="fkb-card fkb-card-clickable" style="--accent:#1D9E75; --d:0ms;"
         :title="revenueTitle"
         @click="drill('revenue')">
      <div class="fkb-lbl">{{ t("Совокупная выручка") }}</div>
      <div class="fkb-val">
        <span class="fkb-num"><Odometer :value="kpis ? fmtBigNumber(kpis.totalRevenue, unit) : '—'" /></span>
        <span class="fkb-unit">{{ unitSuffix }}</span>
      </div>
      <div class="fkb-sub"
           :style="{ color: kpis?.revenueYoYPct == null ? 'var(--t3, #94A3B8)' : (kpis.revenueYoYPct >= 0 ? '#1D9E75' : '#E24B4A') }">
        {{ revenueYoYTxt }}
      </div>
      <div v-if="revenueYoYNote" class="fkb-note">{{ revenueYoYNote }}</div>
    </div>

    <!-- 2. Операционная маржа -->
    <div class="fkb-card fkb-card-clickable" style="--accent:#7F77DD; --d:80ms;"
         @click="drill('opMargin')">
      <div class="fkb-lbl">{{ t("Операционная маржа") }}</div>
      <div class="fkb-val">
        <span class="fkb-num"><Odometer :value="kpis ? fmt.fmtNumber(kpis.opMargin, { decimals: 0 }) : '—'" /></span>
        <span class="fkb-unit fkb-unit-pct">%</span>
      </div>
      <div class="fkb-sub">{{ opProfitTxt }}</div>
    </div>

    <!-- 3. EBITDA -->
    <div class="fkb-card fkb-card-clickable" style="--accent:#EF9F27; --d:160ms;"
         @click="drill('ebitda')">
      <div class="fkb-lbl">EBITDA</div>
      <div class="fkb-val">
        <span class="fkb-num"><Odometer :value="kpis ? fmtBigNumber(kpis.totalEbitda, unit) : '—'" /></span>
        <span class="fkb-unit">{{ unitSuffix }}</span>
      </div>
      <div class="fkb-sub">
        <span style="color: var(--t1, #1E2A4A);">{{ t("Маржа") }} </span>
        <span style="color: #EF9F27; font-weight: 600;">{{ kpis ? fmt.fmtPercent(kpis.ebitdaMargin, { decimals: 0 }) : '' }}</span>
      </div>
    </div>

    <!-- 4. Чистая маржа -->
    <div class="fkb-card fkb-card-clickable" style="--accent:#378ADD; --d:240ms;"
         @click="drill('netMargin')">
      <div class="fkb-lbl">{{ t("Чистая маржа") }}</div>
      <div class="fkb-val">
        <span class="fkb-num"><Odometer :value="kpis ? fmt.fmtNumber(kpis.netMargin, { decimals: 0 }) : '—'" /></span>
        <span class="fkb-unit fkb-unit-pct">%</span>
      </div>
      <div class="fkb-sub">{{ netProfitTxt }}</div>
    </div>

    <!-- 5. Убыточные -->
    <div class="fkb-card fkb-card-clickable" style="--accent:#E24B4A; --d:320ms;"
         @click="drill('loss')">
      <div class="fkb-lbl">{{ t("Убыточные") }}</div>
      <div class="fkb-val">
        <span class="fkb-num" :style="{ color: (kpis?.lossMakingCount ?? 0) > 0 ? '#E24B4A' : 'var(--t1, #1E2A4A)' }"><Odometer :value="kpis ? kpis.lossMakingCount : '—'" /></span>
      </div>
      <div class="fkb-sub">{{ lossOutOf }}</div>
    </div>

    <!-- 6. Дебиторская / Кредиторская задолженность (2-в-1) — только НСБУ.
         Под МСФО этих остатков нет (там tradeReceivables), карточка была бы пустой → скрываем. -->
    <div v-if="standard === 'NSBU'" class="fkb-card fkb-card-arap" style="--accent:#534AB7; --d:400ms;">
      <div class="fkb-lbl">{{ t("Деб. / Кред. задолженность") }}</div>
      <div class="fkb-dual">
        <div class="fkb-dual-half">
          <div class="fkb-dual-v"><Odometer :value="kpis ? fmtBigNumber(kpis.totalAccountsReceivable, unit) : '—'" /></div>
          <div class="fkb-dual-l">{{ t("Дебиторская") }}</div>
        </div>
        <div class="fkb-dual-sep"></div>
        <div class="fkb-dual-half">
          <div class="fkb-dual-v"><Odometer :value="kpis ? fmtBigNumber(kpis.totalAccountsPayable, unit) : '—'" /></div>
          <div class="fkb-dual-l">{{ t("Кредиторская") }}</div>
        </div>
      </div>
      <div class="fkb-sub">{{ t("остаток на конец {y} г.", { y: kpis ? kpis.accountsYear : '' }) }} · {{ unitSuffix }}</div>
    </div>

    <!-- Субсидии переехали в фискальный ряд (FinFiscalBand) под полосой -->
  </div>
</template>

<style scoped>
/* Coverage strip */
.fkb-cover {
  display: flex; align-items: center; gap: 12px;
  margin-bottom: 10px;
  flex-wrap: wrap;
}
.fkb-cover-pill {
  display: inline-flex; align-items: center; gap: 6px;
  padding: 3px 10px;
  border-radius: 8px;
  font-size: 11px; font-weight: 500;
  font-variant-numeric: tabular-nums;
}
.fkb-cover-ok {
  background: rgba(29, 158, 117, 0.12);
  color: var(--green);
}
.fkb-cover-warn {
  background: rgba(239, 159, 39, 0.12);
  color: #D97706;
}
.fkb-dot {
  width: 7px; height: 7px; border-radius: 50%; background: var(--green);
}
.fkb-cover-note {
  font-size: 10.5px; color: var(--t3, var(--t3));
  font-style: italic;
}

/* KPI grid — самобалансирующаяся сетка (эталон .kpi-strip): карточки сами
   ложатся 5/4-в-ряд на 13–14" без «сироты» 3+2 от жёсткого repeat(5)→repeat(3). */
.fkb-grid, .fkb-grid-6 {
  display: grid;
  /* Один ряд: все карточки в одну строку равной ширины (dual занимает 2 трека).
     Порядок P&L: выручка → оп.маржа → EBITDA → чист.маржа → убыточные → задолж. */
  grid-auto-flow: column;
  grid-auto-columns: minmax(0, 1fr);
  gap: 10px;
}
/* «В один ряд» на ВСЕХ десктоп-ширинах: карточки ужимаются (minmax(0,1fr) +
   clamp-шрифт числа), НЕ переносятся и без горизонтального скролла. Перенос —
   только планшет/телефон: ≤720 → 2, ≤430 → 1. */
@media (max-width: 720px)  { .fkb-grid, .fkb-grid-6 { grid-auto-flow: row; grid-template-columns: repeat(2, minmax(0, 1fr)); } }
@media (max-width: 430px)  { .fkb-grid, .fkb-grid-6 { grid-auto-flow: row; grid-template-columns: 1fr; } }

/* 2-в-1 карточка дебиторской/кредиторской — занимает 2 трека (две суммы рядом) */
.fkb-card-arap { grid-column: span 2; }
@media (max-width: 430px) { .fkb-card-arap { grid-column: span 1; } }
.fkb-dual { display: flex; align-items: flex-start; gap: 12px; margin-top: 6px; }
.fkb-dual-half { flex: 1; min-width: 0; }
.fkb-dual-v { font-size: clamp(15px, 1.3vw, 21px); font-weight: 400; color: var(--t1, #1e2a4a); font-variant-numeric: tabular-nums; line-height: 1.1; white-space: nowrap; letter-spacing: -.01em; }
.fkb-dual-l { font-size: 10px; color: var(--t3, #94a3b8); text-transform: uppercase; letter-spacing: .03em; margin-top: 4px; }
.fkb-dual-sep { width: 1px; align-self: stretch; background: var(--border, rgba(99,102,180,.14)); }

/* Card */
.fkb-card {
  background: rgba(255, 255, 255, 0.82);
  backdrop-filter: blur(16px) saturate(1.5);
  -webkit-backdrop-filter: blur(16px) saturate(1.5);
  border-radius: 14px;
  /* горизонтальный padding ужимается на узких треках, чтобы всё влезло в 1 ряд */
  padding: 14px clamp(10px, 0.9vw, 16px) 12px;
  border: 1px solid rgba(255, 255, 255, 0.70);
  box-shadow: 0 2px 12px rgba(15, 23, 60, 0.07), 0 1px 3px rgba(15, 23, 60, 0.04);
  position: relative;
  overflow: hidden;
  min-width: 0;
  display: flex;
  flex-direction: column;
  justify-content: space-between;
  min-height: 96px;
  animation: finKpiCardIn .55s var(--ease-standard) var(--d, 0ms) both;
  transition: transform .18s ease, box-shadow .18s ease, border-color .18s ease;
}
/* Pack 7.48: drill-down clickability */
.fkb-card-clickable {
  cursor: pointer;
}
.fkb-card-clickable:hover {
  transform: translateY(-2px);
  box-shadow: 0 6px 20px rgba(15, 23, 60, 0.12), 0 2px 6px rgba(15, 23, 60, 0.06);
  border-color: rgba(127, 119, 221, 0.30);
}
.fkb-card-clickable:active {
  transform: translateY(-1px);
  transition-duration: .08s;
}
.fkb-card::before {
  content: '';
  position: absolute;
  top: 0; left: 0; right: 0; height: 3px;
  background: var(--accent, var(--border-input));
  border-radius: 14px 14px 0 0;
  animation: finKpi2DrawIn .8s var(--ease-standard) var(--d, 0ms) both;
  transform-origin: left center;
}
.fkb-card::after {
  content: '';
  position: absolute;
  top: 0; left: 0; right: 0; height: 3px;
  background: linear-gradient(90deg, transparent, rgba(255, 255, 255, .55), transparent);
  animation: finShimmer 6s ease-in-out calc(var(--d, 0ms) + 1.2s) 1;
  transform: translateX(-120%);
  pointer-events: none;
}
.fkb-lbl {
  font-size: 11px; font-weight: 500;
  color: var(--t3, var(--t3));
  text-transform: uppercase; letter-spacing: 0.06em;
  margin-bottom: 6px;
  /* длинные лейблы («Операционная маржа») не переносят и не ломают высоту */
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
}
.fkb-val {
  /* число ужимается на узких треках, чтобы карточки держали 1 ряд */
  font-size: clamp(17px, 1.7vw, 28px);
  font-weight: 400;
  letter-spacing: -0.04em;
  line-height: 1;
  color: var(--t1, #1E2A4A);
  font-variant-numeric: tabular-nums;
  display: flex; align-items: baseline; gap: 5px;
  min-width: 0;
}
.fkb-num { display: inline-block; white-space: nowrap; }
.fkb-unit {
  font-size: 12px; color: var(--t3, var(--t3)); font-weight: 400;
  letter-spacing: 0;
}
.fkb-unit-pct { font-size: 16px; }

.fkb-sub {
  font-size: 11px; margin-top: 6px; font-weight: 500;
  color: var(--t1, #1E2A4A);
  font-variant-numeric: tabular-nums;
}

/* Уточнение под процентом: по какой базе он посчитан. Тише подписи, но всегда
   на виду — без него «+16%» рядом с упавшим итогом читается как ошибка. */
.fkb-note {
  font-size: 9.5px; margin-top: 3px; line-height: 1.35;
  color: var(--t3, #94A3B8);
  font-variant-numeric: tabular-nums;
}

</style>
