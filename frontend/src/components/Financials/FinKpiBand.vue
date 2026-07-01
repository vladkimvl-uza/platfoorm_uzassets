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

const fmt = useFormatters();

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
type KpiId = "revenue" | "opMargin" | "ebitda" | "netMargin" | "loss" | "standards";
const emit = defineEmits<{
  (e: "drill", kpi: KpiId): void;
  (e: "open-subsidies"): void;
}>();
function drill(k: KpiId) { emit("drill", k); }

// Субсидии: формат в сум (млрд/трлн), не зависит от валюты страницы
const subsidiesFmt = computed(() => fmtSubsidySum(props.subsidiesTotal ?? null));

onMounted(ensureFinancialsCss);

const unitSuffix = computed(() => `${props.unit === "bln" ? "млрд" : "млн"} ${props.currency}`);

// Hidden per user request 2026-05-23 — оставлено `&& false`
// (а не удалено) чтобы быстро вернуть, сняв флаг.
const showStandardsCard = computed(() => props.standard === "IFRS" && false);

const opProfitTxt = computed(() =>
  props.kpis ? `Опер. прибыль ${fmtBigNumber(props.kpis.totalOpProfit, props.unit)}` : "—",
);
const netProfitTxt = computed(() =>
  props.kpis
    ? `Чистая прибыль ${fmtBigNumber(props.kpis.totalNetProfit, props.unit)} ${
        fmt.fmtNumber(props.kpis.netProfitDeltaPp, { decimals: 0, signed: true })
      } п.п.`
    : "",
);
const lossOutOf = computed(() =>
  props.kpis ? `из ${props.kpis.companiesWithProfit} с данными по прибыли` : "",
);
</script>

<template>
  <!-- Coverage indicator strip (above cards) -->
  <div class="fkb-cover">
    <span class="fkb-cover-pill fkb-cover-ok">
      <span class="fkb-dot" /> {{ inYear }} из {{ totalCompanies }}
    </span>
    <span v-if="noDataCount > 0" class="fkb-cover-pill fkb-cover-warn">
      <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor"
           stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round">
        <circle cx="12" cy="12" r="10"/>
        <line x1="12" y1="8" x2="12" y2="12"/>
        <line x1="12" y1="16" x2="12.01" y2="16"/>
      </svg>
      {{ noDataCount }} без данных
    </span>
    <span class="fkb-cover-note">YoY рассчитан по like-for-like basket (только компании с данными в обоих годах)</span>
  </div>

  <div class="fkb-grid kpi-rail" :class="{ 'fkb-grid-6': showStandardsCard }">
    <!-- 1. Совокупная выручка -->
    <div class="fkb-card fkb-card-clickable" style="--accent:#1D9E75; --d:0ms;"
         @click="drill('revenue')">
      <div class="fkb-lbl">Совокупная выручка</div>
      <div class="fkb-val">
        <span class="fkb-num"><Odometer :value="kpis ? fmtBigNumber(kpis.totalRevenue, unit) : '—'" /></span>
        <span class="fkb-unit">{{ unitSuffix }}</span>
      </div>
      <div class="fkb-sub" :style="{ color: (kpis?.revenueYoYPct ?? 0) >= 0 ? '#1D9E75' : '#E24B4A' }">
        {{ kpis ? fmtPctSigned(kpis.revenueYoYPct) + ' к пред. году' : '' }}
      </div>
    </div>

    <!-- 2. Операционная маржа -->
    <div class="fkb-card fkb-card-clickable" style="--accent:#7F77DD; --d:80ms;"
         @click="drill('opMargin')">
      <div class="fkb-lbl">Операционная маржа</div>
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
        <span style="color: var(--t1, #1E2A4A);">Маржа </span>
        <span style="color: #EF9F27; font-weight: 600;">{{ kpis ? fmt.fmtPercent(kpis.ebitdaMargin, { decimals: 0 }) : '' }}</span>
      </div>
    </div>

    <!-- 4. Чистая маржа -->
    <div class="fkb-card fkb-card-clickable" style="--accent:#378ADD; --d:240ms;"
         @click="drill('netMargin')">
      <div class="fkb-lbl">Чистая маржа</div>
      <div class="fkb-val">
        <span class="fkb-num"><Odometer :value="kpis ? fmt.fmtNumber(kpis.netMargin, { decimals: 0 }) : '—'" /></span>
        <span class="fkb-unit fkb-unit-pct">%</span>
      </div>
      <div class="fkb-sub">{{ netProfitTxt }}</div>
    </div>

    <!-- 5. Убыточные -->
    <div class="fkb-card fkb-card-clickable" style="--accent:#E24B4A; --d:320ms;"
         @click="drill('loss')">
      <div class="fkb-lbl">Убыточные</div>
      <div class="fkb-val">
        <span class="fkb-num" :style="{ color: (kpis?.lossMakingCount ?? 0) > 0 ? '#E24B4A' : 'var(--t1, #1E2A4A)' }"><Odometer :value="kpis ? kpis.lossMakingCount : '—'" /></span>
      </div>
      <div class="fkb-sub">{{ lossOutOf }}</div>
    </div>

    <!-- 6. Дебиторская / Кредиторская задолженность (2-в-1) — только НСБУ.
         Под МСФО этих остатков нет (там tradeReceivables), карточка была бы пустой → скрываем. -->
    <div v-if="standard === 'NSBU'" class="fkb-card fkb-card-arap" style="--accent:#534AB7; --d:400ms;">
      <div class="fkb-lbl">Деб. / Кред. задолженность</div>
      <div class="fkb-dual">
        <div class="fkb-dual-half">
          <div class="fkb-dual-v"><Odometer :value="kpis ? fmtBigNumber(kpis.totalAccountsReceivable, unit) : '—'" /></div>
          <div class="fkb-dual-l">Дебиторская</div>
        </div>
        <div class="fkb-dual-sep"></div>
        <div class="fkb-dual-half">
          <div class="fkb-dual-v"><Odometer :value="kpis ? fmtBigNumber(kpis.totalAccountsPayable, unit) : '—'" /></div>
          <div class="fkb-dual-l">Кредиторская</div>
        </div>
      </div>
      <div class="fkb-sub">остаток на конец {{ kpis ? kpis.accountsYear : '' }} г. · {{ unitSuffix }}</div>
    </div>

    <!-- Субсидии переехали в фискальный ряд (FinFiscalBand) под полосой -->

    <!-- 8. Внедрение стандартов (IFRS only) -->
    <div v-if="showStandardsCard" class="fkb-card fkb-card-clickable" style="--accent:#534AB7; --d:400ms;"
         @click="drill('standards')">
      <div class="fkb-lbl">Внедрение стандартов</div>
      <div class="fkb-std-row">
        <div class="fkb-std-mini">
          <svg width="38" height="38" viewBox="0 0 38 38">
            <circle cx="19" cy="19" r="15" fill="none" stroke="#F1F5F9" stroke-width="3.5"/>
            <circle cx="19" cy="19" r="15" fill="none" stroke="#1D9E75" stroke-width="3.5"
                    stroke-linecap="round"
                    :stroke-dasharray="`${(0.18 * 94)} 94`"
                    transform="rotate(-90 19 19)"/>
            <text x="19" y="22" text-anchor="middle" font-size="9" font-weight="600" fill="#1D9E75">18%</text>
          </svg>
          <div class="fkb-std-info">
            <div class="fkb-std-num">4<span class="fkb-std-tot">/22</span></div>
            <div class="fkb-std-name">МСФО</div>
          </div>
        </div>
        <div class="fkb-std-mini">
          <svg width="38" height="38" viewBox="0 0 38 38">
            <circle cx="19" cy="19" r="15" fill="none" stroke="#F1F5F9" stroke-width="3.5"/>
            <circle cx="19" cy="19" r="15" fill="none" stroke="#EF9F27" stroke-width="3.5"
                    stroke-linecap="round"
                    :stroke-dasharray="`${(0.36 * 94)} 94`"
                    transform="rotate(-90 19 19)"/>
            <text x="19" y="22" text-anchor="middle" font-size="9" font-weight="600" fill="#EF9F27">36%</text>
          </svg>
          <div class="fkb-std-info">
            <div class="fkb-std-num">8<span class="fkb-std-tot">/22</span></div>
            <div class="fkb-std-name">Forensic</div>
          </div>
        </div>
      </div>
      <div class="fkb-sub" style="color:#D97706">19 требуют внимания</div>
    </div>
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
  grid-template-columns: repeat(auto-fit, minmax(clamp(150px, 11vw, 180px), 1fr));
  gap: 10px;
}
/* Планшетный портрет (721–1023): ровно 3-в-ряд (3+2), без растянутой «сироты»,
   которую auto-fit давал бы как 4+1. Встык с телефонным ≤720 (2-в-ряд). */
@media (min-width: 721px) and (max-width: 1023px) { .fkb-grid, .fkb-grid-6 { grid-template-columns: repeat(3, minmax(0, 1fr)); } }
@media (max-width: 720px)  { .fkb-grid, .fkb-grid-6 { grid-template-columns: repeat(2, minmax(0, 1fr)); } }
/* Узкий телефон (≤430): 1 карта в ряд — крупные суммы с юнитом не режутся. */
@media (max-width: 430px)  { .fkb-grid, .fkb-grid-6 { grid-template-columns: 1fr; } }

/* 2-в-1 карточка дебиторской/кредиторской — занимает 2 трека (две суммы рядом) */
.fkb-card-arap { grid-column: span 2; }
@media (max-width: 430px) { .fkb-card-arap { grid-column: span 1; } }
.fkb-dual { display: flex; align-items: flex-start; gap: 12px; margin-top: 6px; }
.fkb-dual-half { flex: 1; min-width: 0; }
.fkb-dual-v { font-size: 21px; font-weight: 400; color: var(--t1, #1e2a4a); font-variant-numeric: tabular-nums; line-height: 1.1; white-space: nowrap; letter-spacing: -.01em; }
.fkb-dual-l { font-size: 10px; color: var(--t3, #94a3b8); text-transform: uppercase; letter-spacing: .03em; margin-top: 4px; }
.fkb-dual-sep { width: 1px; align-self: stretch; background: var(--border, rgba(99,102,180,.14)); }

/* Card */
.fkb-card {
  background: rgba(255, 255, 255, 0.82);
  backdrop-filter: blur(16px) saturate(1.5);
  -webkit-backdrop-filter: blur(16px) saturate(1.5);
  border-radius: 14px;
  padding: 14px 16px 12px;
  border: 1px solid rgba(255, 255, 255, 0.70);
  box-shadow: 0 2px 12px rgba(15, 23, 60, 0.07), 0 1px 3px rgba(15, 23, 60, 0.04);
  position: relative;
  overflow: hidden;
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
}
.fkb-val {
  font-size: 28px;
  font-weight: 400;
  letter-spacing: -0.04em;
  line-height: 1;
  color: var(--t1, #1E2A4A);
  font-variant-numeric: tabular-nums;
  display: flex; align-items: baseline; gap: 5px;
}
.fkb-num { display: inline-block; }
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

/* Standards card layout (6th card, IFRS only) */
.fkb-std-row {
  display: flex; gap: 12px; align-items: center;
  margin-top: 2px; margin-bottom: 4px;
}
.fkb-std-mini {
  display: flex; align-items: center; gap: 6px;
}
.fkb-std-info { display: flex; flex-direction: column; gap: 1px; }
.fkb-std-num {
  font-size: 16px; font-weight: 600; color: var(--t1, #1E2A4A);
  letter-spacing: -0.02em; line-height: 1;
}
.fkb-std-tot { font-size: 11px; color: var(--t3, var(--t3)); font-weight: 400; }
.fkb-std-name {
  font-size: 9.5px; color: var(--t3, var(--t3));
  text-transform: uppercase; letter-spacing: 0.06em; font-weight: 600;
}
</style>
