<!--
  ExecDashCreditBlock.vue — Pack 7.44 (fixes Pack 7.41).

  Fixes:
    1. Data matches /credit-portfolio (backend now proxies _aggregate_impl)
    2. ALL tooltips wired correctly (was: 4 cards without tooltips)
    3. Currency donut shows NATIVE amounts ($, €, ¥, ₽, сум) not USD eq
    4. Lender/currency colors aligned with credit-portfolio palette
-->
<template>
  <div class="ecb">
    <div class="ecb-hdr">
      <div>
        <div class="ecb-eyebrow">executive dashboard · кредитный модуль</div>
        <h2 class="ecb-title">Кредитный портфель по {{ soeNumber }} SOEs <span class="ecb-tip" :title="TT.module">?</span></h2>
        <p class="ecb-sub" v-if="overview">{{ fmtCount(overview.loans_count) }} кредитов · {{ fmtCount(overview.banks_count) }} банков-кредиторов · {{ fmtCount(overview.companies_count) }}/{{ overview.soes_count }} предприятий с долгом. Снимок на {{ snapshotDate }}.</p>
      </div>
      <div class="ecb-hdr-actions">
        <button class="ecb-btn" @click="goAllLoans">Все кредиты</button>
        <button class="ecb-btn ecb-btn-p" @click="goScenarios">Сценарии</button>
      </div>
    </div>

    <div class="ecb-sync" v-if="overview"><span class="ecb-sync-dot"></span><span><strong>Синхронизировано с credit-portfolio</strong> · обновляется автоматически</span></div>
    <div v-if="overviewLoading && !overview" class="ecb-skel"><div class="ecb-skel-row"></div><div class="ecb-skel-row"></div></div>
    <div v-if="overviewError" class="ecb-err">Ошибка загрузки: {{ overviewError }}</div>

    <template v-if="overview">
      <div class="ecb-l"><span>Основные показатели<span class="ecb-tip" :title="TT.heroSection">?</span></span><span class="ecb-l-hint">клик по карточке — детали</span></div>
      <div class="ecb-hero-grid">
        <div class="ecb-hero" style="--kc:#534AB7;" @click="openModal('portfolio')"><span class="ecb-hero-click">→</span>
          <div class="ecb-hero-l">Кредитный портфель<span class="ecb-tip" :title="TT.portfolio">?</span></div>
          <div class="ecb-hero-v">{{ fmtUsdMlrd(tweenedPortfolioTotal) }}</div>
          <div class="ecb-hero-d" style="color:#534AB7;">размер программы · по договорам</div>
        </div>
        <div class="ecb-hero" style="--kc:#7F77DD;" @click="openModal('outstanding')"><span class="ecb-hero-click">→</span>
          <div class="ecb-hero-l">Общий долг outstanding<span class="ecb-tip" :title="TT.outstanding">?</span></div>
          <div class="ecb-hero-v">{{ fmtUsdMlrd(tweenedOutstanding) }}</div>
          <div class="ecb-hero-d" style="color:#7F77DD;">{{ Number(overview.portfolio_total_usd) > 0 ? fmtPct(Number(overview.outstanding_usd) / Number(overview.portfolio_total_usd) * 100) : '—' }} от портфеля</div>
        </div>
        <div class="ecb-hero" style="--kc:#EF9F27;" @click="openModal('rate')"><span class="ecb-hero-click">→</span>
          <div class="ecb-hero-l">Средневзвешенная ставка<span class="ecb-tip" :title="TT.rate">?</span></div>
          <div class="ecb-hero-v">{{ fmtPct(tweenedAvgRate, 2) }}</div>
          <div class="ecb-hero-d" style="color:#854F0B;">взвешена по размеру долга</div>
        </div>
        <div class="ecb-hero" style="--kc:#1D9E75;" @click="openModal('guaranteed')"><span class="ecb-hero-click">→</span>
          <div class="ecb-hero-l">С государственной гарантией<span class="ecb-tip" :title="TT.guaranteed">?</span></div>
          <div class="ecb-hero-v">{{ fmtPct(tweenedGuaranteed) }}</div>
          <div class="ecb-hero-d" style="color:#0F6E56;">{{ fmtUsdMlrd(overview.guaranteed_usd) }} защищены</div>
        </div>
      </div>

      <div class="ecb-lc" v-if="Number(overview.portfolio_total_usd) > 0">
        <div class="ecb-lc-seg ecb-lc-r" :style="{ flex: Math.max(1, Number(overview.repaid_pct)) }">
          <div class="ecb-lc-seg-l">Уже возвращено<span class="ecb-tip" :title="TT.repaid">?</span></div>
          <div class="ecb-lc-seg-v">{{ fmtUsdMlrd(overview.repaid_usd) }} <small>· {{ fmtPct(overview.repaid_pct) }}</small></div>
        </div>
        <div class="ecb-lc-seg ecb-lc-o" :style="{ flex: 100 - Number(overview.repaid_pct) }">
          <div class="ecb-lc-seg-l">Outstanding<span class="ecb-tip" :title="TT.outstanding">?</span></div>
          <div class="ecb-lc-seg-v">{{ fmtUsdMlrd(overview.outstanding_usd) }} <small>· {{ fmtPct(100 - Number(overview.repaid_pct)) }}</small></div>
        </div>
      </div>

      <div class="ecb-l"><span>Дополнительные индикаторы<span class="ecb-tip" :title="TT.secondary">?</span></span><span class="ecb-l-hint">фокус на риск</span></div>
      <div class="ecb-mini-grid">
        <div class="ecb-mini" @click="openModal('due_12mo')">
          <div class="ecb-mini-l">К погашению 12 месяцев<span class="ecb-tip" :title="TT.due12mo">?</span></div>
          <div class="ecb-mini-v">{{ fmtUsdMlrd(tweenedDue12) }}</div>
          <div class="ecb-mini-d" style="color:#854F0B;">{{ fmtCount(overview.due_12mo_loans) }} кредитов</div>
        </div>
        <div class="ecb-mini" @click="openModal('fx')">
          <div class="ecb-mini-l">Валютная подверженность<span class="ecb-tip" :title="TT.fx">?</span></div>
          <div class="ecb-mini-v">{{ fmtPct(tweenedFxExposure) }}</div>
          <div class="ecb-mini-d" style="color:#854F0B;">{{ fmtUsdMlrd(overview.fx_exposure_usd) }} не в сумах</div>
        </div>
        <div class="ecb-mini" @click="openModal('overdue')">
          <div class="ecb-mini-l">Просрочка<span class="ecb-tip" :title="TT.overdue">?</span></div>
          <div class="ecb-mini-v">{{ fmtUsdMlrd(tweenedOverdue) }}</div>
          <div class="ecb-mini-d" style="color:#A32D2D;">{{ fmtCount(overview.overdue_loans) }} кр · {{ fmtCount(overview.overdue_companies) }} предпр.</div>
        </div>
        <div class="ecb-mini" @click="openModal('expected_loss')">
          <div class="ecb-mini-l">Ожидаемые потери Basel EL<span class="ecb-tip" :title="TT.el">?</span></div>
          <div class="ecb-mini-v">{{ fmtUsdMlrd(tweenedExpLoss) }}</div>
          <div class="ecb-mini-d" style="color:#A32D2D;">{{ Number(overview.outstanding_usd) > 0 ? fmtPct(Number(overview.expected_loss_usd) / Number(overview.outstanding_usd) * 100, 2) : '—' }} от outstanding</div>
        </div>
      </div>

      <div class="ecb-l"><span>Структура долга outstanding ({{ fmtUsdMlrd(overview.outstanding_usd) }})<span class="ecb-tip" :title="TT.structure">?</span></span><span class="ecb-l-hint">клик по сегменту — список кредитов</span></div>
      <div class="ecb-2col">
        <!-- Lender type donut -->
        <div class="ecb-card">
          <div class="ecb-card-h">Тип кредитора<span class="ecb-tip" :title="TT.lenderType">?</span><span class="ecb-card-h-r">{{ overview.by_lender_type.length }} категории</span></div>
          <div class="ecb-donut-wrap">
            <div class="ecb-donut-svg-wrap">
              <svg viewBox="0 0 100 100" class="ecb-donut-svg">
                <circle cx="50" cy="50" r="42" stroke="rgba(15,23,60,.06)" stroke-width="6" fill="none"/>
                <circle v-for="(s, i) in lenderSegs" :key="s.lender_type"
                        class="ecb-donut-seg" cx="50" cy="50" r="42"
                        :stroke="s.color" stroke-width="6" fill="none"
                        stroke-linecap="round"
                        :stroke-dasharray="`${Math.max(0, s.length - 8).toFixed(2)} 264`"
                        :stroke-dashoffset="(s.offset - 4).toFixed(2)"
                        :style="{ '--di': i }"
                        @click="openSegmentModal('lender_type', s.lender_type)"/>
              </svg>
              <div class="ecb-donut-center">
                <span class="ecb-donut-center-v">{{ fmtUsdMlrd(overview.outstanding_usd) }}</span>
                <span class="ecb-donut-center-l">outstanding</span>
              </div>
            </div>
            <div class="ecb-donut-legend">
              <div v-for="s in lenderSegs" :key="s.lender_type" class="ecb-leg-row" @click="openSegmentModal('lender_type', s.lender_type)">
                <span class="ecb-leg-dot" :style="{ background: s.color }"></span>
                <div class="ecb-leg-mid">
                  <span class="ecb-leg-mid-l">{{ s.label_ru }}</span>
                  <div class="ecb-leg-mid-b"><div class="ecb-leg-mid-b-fill" :style="{ background: s.color, width: `${s.pct}%` }"></div></div>
                </div>
                <div class="ecb-leg-r">
                  <span class="ecb-leg-r-v">{{ fmtUsdMlrd(s.debt_usd) }}</span>
                  <span class="ecb-leg-r-p">{{ fmtPct(s.pct, 0) }}</span>
                </div>
              </div>
            </div>
          </div>
        </div>

        <!-- Currency donut (NATIVE amounts) -->
        <div class="ecb-card">
          <div class="ecb-card-h">Валюта долга<span class="ecb-tip" :title="TT.currency">?</span><span class="ecb-card-h-r">{{ overview.by_currency.length }} валют</span></div>
          <div class="ecb-donut-wrap">
            <div class="ecb-donut-svg-wrap">
              <svg viewBox="0 0 100 100" class="ecb-donut-svg">
                <circle cx="50" cy="50" r="42" stroke="rgba(15,23,60,.06)" stroke-width="6" fill="none"/>
                <circle v-for="(s, i) in currencySegs" :key="s.currency"
                        class="ecb-donut-seg" cx="50" cy="50" r="42"
                        :stroke="s.color" stroke-width="6" fill="none"
                        stroke-linecap="round"
                        :stroke-dasharray="`${Math.max(0, s.length - 8).toFixed(2)} 264`"
                        :stroke-dashoffset="(s.offset - 4).toFixed(2)"
                        :style="{ '--di': i }"
                        @click="openSegmentModal('currency', s.currency)"/>
              </svg>
              <div class="ecb-donut-center">
                <span class="ecb-donut-center-v">{{ overview.by_currency.length }}</span>
                <span class="ecb-donut-center-l">валют</span>
              </div>
            </div>
            <div class="ecb-donut-legend">
              <div v-for="s in currencySegs" :key="s.currency" class="ecb-leg-row" @click="openSegmentModal('currency', s.currency)">
                <span class="ecb-leg-dot" :style="{ background: s.color }"></span>
                <div class="ecb-leg-mid">
                  <span class="ecb-leg-mid-l">{{ s.label_ru }}</span>
                  <div class="ecb-leg-mid-b"><div class="ecb-leg-mid-b-fill" :style="{ background: s.color, width: `${s.pct}%` }"></div></div>
                </div>
                <div class="ecb-leg-r">
                  <!-- NATIVE currency amount (was: USD-equivalent) -->
                  <span class="ecb-leg-r-v">{{ fmtNative(s.debt_currency, s.currency) }}</span>
                  <span class="ecb-leg-r-p">{{ fmtPct(s.pct, 0) }}</span>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>

      <div class="ecb-l"><span>Срок погашения<span class="ecb-tip" :title="TT.maturity">?</span></span><span class="ecb-l-hint">клик — список кредитов</span></div>
      <div class="ecb-card">
        <div class="ecb-mat-wrap">
          <div v-for="(s, i) in maturitySegs" :key="s.bucket" class="ecb-mat-col" @click="openSegmentModal('maturity', s.bucket)">
            <div class="ecb-mat-l">{{ s.label_ru }}</div>
            <div class="ecb-mat-bar-area"><div class="ecb-mat-bar" :style="{ background: s.color, height: `${s.height}%`, '--mi': i }"></div></div>
            <div class="ecb-mat-v">{{ fmtUsdMln(s.debt_usd) }}</div>
            <div class="ecb-mat-d">{{ fmtCount(s.loans_count) }} кр · {{ fmtPct(s.pct, 1) }}</div>
          </div>
        </div>
      </div>
    </template>

    <ExecDashCreditModal v-if="modal.open" :kind="modal.kind" :payload="modal.payload" @close="closeModal" />
  </div>
</template>

<script setup lang="ts">
import { onMounted, computed, reactive } from "vue"
import { useNumberTween } from "@/composables/useNumberTween";
import { useCreditScenario, fmtUsdMlrd, fmtUsdMln, fmtPct, fmtCount } from "@/composables/useCreditScenario"
import { useFormatters } from "@/composables/useFormatters"
import { CP_LENDER_LABELS, CURRENCY_COLORS as CP_CURRENCY_COLORS } from "@/api/credit"
import ExecDashCreditModal from "./ExecDashCreditModal.vue"

const fmt = useFormatters()
const { overview, overviewLoading, overviewError, loadOverview } = useCreditScenario()

const soeNumber = computed(() => overview.value?.soes_count || 22)
// Snapshot = 1 января текущего FY (year-start balance), а не сейчас.
// Per user feedback 2026-05-23 — снимок кредитного портфеля
// показывается «по состоянию на начало года» как принято в фин. отчётности.
const snapshotDate = computed(() => {
  const y = new Date().getFullYear()
  return fmt.fmtDate(new Date(y, 0, 1), { long: true })
})

const C = 264

// Pack 7.44 — use the SAME palette as credit-portfolio (CP_LENDER_LABELS / CURRENCY_COLORS)
const lenderColorOf = (lt: string) => (CP_LENDER_LABELS as any)[lt]?.color || "#888780"
const currencyColorOf = (cur: string) => CP_CURRENCY_COLORS[cur] || "#888780"

const MATURITY_ORDER = ["overdue", "lt_1y", "1_3y", "3_5y", "gt_5y"]
const MATURITY_COLORS: Record<string, string> = {
  overdue: "#E24B4A", lt_1y: "#EF9F27", "1_3y": "#7F77DD", "3_5y": "#534AB7", gt_5y: "#1D9E75",
}

const lenderSegs = computed(() => {
  if (!overview.value) return []
  let cum = 0
  return overview.value.by_lender_type.map((s: any) => {
    const pct = Number(s.pct) || 0
    const length = (pct / 100) * C
    const offset = -cum
    cum += length
    return {
      ...s,
      pct,
      debt_usd: Number(s.debt_usd) || 0,
      color: lenderColorOf(s.lender_type),
      length,
      offset,
    }
  })
})

const currencySegs = computed(() => {
  if (!overview.value) return []
  let cum = 0
  return overview.value.by_currency.map((s: any) => {
    const pct = Number(s.pct) || 0
    const length = (pct / 100) * C
    const offset = -cum
    cum += length
    return {
      ...s,
      pct,
      debt_usd: Number(s.debt_usd) || 0,
      debt_currency: Number(s.debt_currency) || 0,
      color: currencyColorOf(s.currency),
      length,
      offset,
    }
  })
})

const maturitySegs = computed(() => {
  if (!overview.value) return []
  const m = new Map(overview.value.by_maturity.map((s: any) => [s.bucket, s]))
  const ord = MATURITY_ORDER.map((b) => m.get(b)).filter(Boolean) as any[]
  const max = Math.max(1, ...ord.map((s) => Number(s.debt_usd)))
  return ord.map((s) => ({
    ...s,
    pct: Number(s.pct) || 0,
    debt_usd: Number(s.debt_usd) || 0,
    color: MATURITY_COLORS[s.bucket] || "#888780",
    height: Math.max(4, (Number(s.debt_usd) / max) * 100),
  }))
})

// Native currency formatter (was: only USD formatter).
// Uses fmt.fmtNumber for digit-grouping/decimal-separator so the number portion
// reformats when UI locale changes. Symbol/scale word lists are kept here
// because fmtMoneyCompact only supports UZS/USD/EUR/RUB/CNY (JPY/SDR/KZT/GBP fall through).
function fmtNative(v: number | string | null | undefined, currency: string): string {
  const n = Number(v || 0)
  if (!isFinite(n) || n === 0) return "—"
  const SYM: Record<string, string> = {
    USD: "$", EUR: "€", CNY: "¥", JPY: "¥", RUB: "₽", UZS: "сум",
    SDR: "SDR", KZT: "₸", GBP: "£",
  }
  const sym = SYM[currency] || currency
  const isUZS = currency === "UZS"
  const abs = Math.abs(n)
  const num = (val: number, dec: number) => fmt.fmtNumber(val, { decimals: dec, minDecimals: dec })

  // UZS — мы получаем уже в сумах. Округляем до млрд/трлн.
  if (isUZS) {
    if (abs >= 1e12) return `${num(n / 1e12, 2)} трлн ${sym}`
    if (abs >= 1e9)  return `${num(n / 1e9, 1)} млрд ${sym}`
    if (abs >= 1e6)  return `${num(n / 1e6, 0)} млн ${sym}`
    return `${num(n, 0)} ${sym}`
  }

  // JPY/CNY — без копеек
  const noDec = ["JPY"]
  if (noDec.includes(currency)) {
    if (abs >= 1e9) return `${sym}${num(n / 1e9, 2)} млрд`
    if (abs >= 1e6) return `${sym}${num(n / 1e6, 1)} млн`
    return `${sym}${num(n, 0)}`
  }

  // Currency-symbol-before-value стиль
  if (abs >= 1e9) return `${sym}${num(n / 1e9, 2)} млрд`
  if (abs >= 1e6) return `${sym}${num(n / 1e6, 1)} млн`
  if (abs >= 1e3) return `${sym}${num(n / 1e3, 1)} тыс`
  return `${sym}${num(n, 0)}`
}

const modal = reactive<{ open: boolean; kind: string; payload: any }>({ open: false, kind: "", payload: {} })
function openModal(kind: string) {
  modal.kind = kind
  modal.payload = { overview: overview.value }
  modal.open = true
}
function openSegmentModal(dim: string, val: string) {
  modal.kind = `segment_${dim}`
  modal.payload = { dimension: dim, value: val, overview: overview.value }
  modal.open = true
}
function closeModal() { modal.open = false }
function goAllLoans() { window.location.href = "/credit-portfolio" }
function goScenarios() { window.location.href = "/admin/system-config?tab=scenarios" }

const TT = {
  module: "Свод всех кредитов 22 государственных предприятий. Данные синхронизированы с модулем «Кредитный портфель» один-в-один. Read-only.",
  heroSection: "4 главные метрики портфеля. Клик по любой карточке — детальная разбивка с drill-down.",
  portfolio: "Сумма всех изначальных размеров кредитов по подписанным договорам (sum_total), пересчитанная в USD по курсу на дату получения. Размер программы, не текущая задолженность.",
  outstanding: "Сколько 22 предприятия должны прямо сейчас всем кредиторам, в долларовом эквиваленте (debt_usd). Меньше портфеля — часть уже возвращена.",
  rate: "Σ(rate × debt_usd) / Σ debt_usd. Большие кредиты весят больше. Не путать с простой средней арифметической.",
  guaranteed: "Доля кредитов с государственной гарантией. Государство покрывает основной долг при дефолте — снижает риск для кредитора и предприятия.",
  repaid: "Уже возвращено = Программа − Outstanding. Включает плановые погашения и досрочные выплаты.",
  secondary: "Индикаторы рисков и срочности — что требует внимания в ближайшее время.",
  due12mo: "Платежи следующих 12 месяцев — основной долг + проценты по графику из loan_repayments. Текущий + следующий год.",
  fx: "Валютная подверженность — доля кредитов в иностранной валюте. При ослаблении сума обслуживание дорожает в национальной валюте.",
  overdue: "Просрочка — кредиты с прошедшей датой погашения и положительным остатком долга. Срочные действия: реструктуризация, доп. гарантии, списание.",
  el: "Ожидаемые потери (Basel EL) = Σ debt × PD × (1 − RR). PD — вероятность дефолта (2.5% базовый, ×5 для просрочки), RR — recovery rate (60% гос / 50% мест / 45% инст / 40% бонд). С госгарантией RR +30 п.п.",
  structure: "Outstanding разбит по 3 измерениям: кто кредитор / в какой валюте / когда платить. Клик по сегменту откроет список конкретных кредитов.",
  lenderType: "Государство = Минфин РУ + Госказначейство РУ. Местные = коммерческие банки РУ. Иностранные = EXIM Китая, ADB, World Bank, JICA и др. Облигации = облигационные займы (eurobonds, наши выпуски).",
  currency: "Валюта оригинального договора — суммы в нативной валюте, не в долларовом эквиваленте. % считается от outstanding в USD.",
  maturity: "5 сегментов по времени до погашения: просрочено / до 1 года / 1–3 / 3–5 / более 5 лет. Размер столбца = объём долга в этой группе.",
}

onMounted(() => { loadOverview() })

// Pack 7.44 — number tween для hero/mini KPI (Smooth motion system, Variant A)
const tweenedPortfolioTotal = useNumberTween(
  () => Number(overview.value?.portfolio_total_usd) || 0
);
const tweenedOutstanding = useNumberTween(
  () => Number(overview.value?.outstanding_usd) || 0
);
const tweenedAvgRate = useNumberTween(
  () => Number(overview.value?.avg_rate_weighted) || 0
);
const tweenedGuaranteed = useNumberTween(
  () => Number(overview.value?.guaranteed_pct) || 0
);
const tweenedDue12 = useNumberTween(
  () => Number(overview.value?.due_12mo_usd) || 0
);
const tweenedFxExposure = useNumberTween(
  () => Number(overview.value?.fx_exposure_pct) || 0
);
const tweenedOverdue = useNumberTween(
  () => Number(overview.value?.overdue_usd) || 0
);
const tweenedExpLoss = useNumberTween(
  () => Number(overview.value?.expected_loss_usd) || 0
);

</script>

<style scoped>
@keyframes ecbIn { from{opacity:0;transform:translateY(8px)} to{opacity:1;transform:translateY(0)} }
@keyframes ecbBarV { to{transform:scaleY(1)} }
@keyframes ecbDonut { from{opacity:0} to{opacity:1} }
@keyframes ecbPulse { 0%,100%{opacity:1} 50%{opacity:.4} }
@keyframes ecbShim { 0%{background-position:-100% 0} 100%{background-position:200% 0} }
@keyframes ecbBreathe { 0%,100%{opacity:1} 50%{opacity:.85} }

/* ═══ Контейнер блока — под эталон .ed-fin ═══ */
.ecb {
  background: var(--card-bg, rgba(255, 255, 255, 0.82));
  backdrop-filter: blur(16px) saturate(1.5);
  -webkit-backdrop-filter: blur(16px) saturate(1.5);
  border: 1px solid var(--card-border, rgba(15, 23, 60, 0.08));
  border-radius: 12px;
  padding: 16px 18px 18px;
  margin-top: 14px;
  box-shadow: 0 4px 16px rgba(15, 23, 60, 0.04);
  color: var(--t1, #1E2A4A);
  font-family: inherit;
}

/* Header */
.ecb-hdr { display:flex; justify-content:space-between; align-items:flex-start; gap:16px; margin-bottom:14px; flex-wrap:wrap; }
.ecb-hdr > div:first-child { min-width: 0; flex: 1; }
.ecb-hdr-actions { display:flex; gap:6px; flex-shrink:0; }
.ecb-btn { font-family:inherit; font-size:11px; font-weight:600; padding:6px 12px; border-radius:7px; cursor:pointer; border:none; background:rgba(15,23,60,.05); color: var(--t1, #1E2A4A); transition: background .15s; }
.ecb-btn:hover { background: rgba(15,23,60,.08); }
.ecb-btn-p { background:#7F77DD; color:#fff; }
.ecb-btn-p:hover { background:var(--p-deep); }

/* Eyebrow + title + sub */
.ecb-eyebrow { font-size:9.5px; font-weight:600; letter-spacing:.1em; color: var(--t3, var(--t-muted)); text-transform:uppercase; }
.ecb-title { font-size:15px; font-weight:500; letter-spacing:-.01em; color: var(--t1, #1E2A4A); margin:4px 0 4px; display:flex; align-items:center; gap:8px; }
.ecb-sub { font-size:11px; color: var(--t3, var(--t-muted)); font-weight:500; line-height:1.5; margin:4px 0 0; font-feature-settings:"tnum"; }
.ecb-tip { display:inline-flex; align-items:center; justify-content:center; width:14px; height:14px; font-size:9px; font-weight:600; border-radius:50%; background:rgba(127,119,221,.10); color:var(--p-deep); margin-left:3px; cursor:help; flex-shrink:0; }

/* Sync banner */
.ecb-sync { display:flex; align-items:center; gap:10px; padding:9px 12px; background:rgba(29,158,117,.06); border:0.5px solid rgba(29,158,117,.18); border-radius:8px; font-size:11px; margin-bottom:14px; font-weight:500; }
.ecb-sync-dot { width:6px; height:6px; border-radius:50%; background:var(--green); animation:ecbPulse 2.2s infinite; flex-shrink:0; }
.ecb-sync strong { color:#0F6E56; font-weight:600; }

/* States */
.ecb-skel { padding:24px 0; }
.ecb-skel-row { height:60px; background:linear-gradient(90deg,rgba(15,23,60,.04),rgba(15,23,60,.08),rgba(15,23,60,.04)); background-size:200% 100%; animation:ecbShim 1.6s infinite; border-radius:10px; margin-bottom:10px; }
.ecb-err { padding:12px; background:rgba(226,75,74,.08); border:0.5px solid rgba(226,75,74,.20); border-radius:8px; color:var(--sev-critical); font-size:11px; font-weight:500; }

/* Section label "ОСНОВНЫЕ ПОКАЗАТЕЛИ" / "СТРУКТУРА ДОЛГА" / "СРОК ПОГАШЕНИЯ" */
.ecb-l { font-size:9.5px; color: var(--t3, var(--t-muted)); text-transform:uppercase; letter-spacing:.08em; font-weight:600; margin:16px 0 8px; display:flex; justify-content:space-between; align-items:center; gap:8px; }
.ecb-l > span:first-child { display:flex; align-items:center; gap:4px; }
.ecb-l-hint { font-size:9.5px; color:#B4B2A9; text-transform:none; letter-spacing:.02em; font-weight:500; }

/* Hero KPI grid (4 крупных) — под .ed-fin-kpi-card */
.ecb-hero-grid { display:grid; grid-template-columns:repeat(4,1fr); gap:12px; }
@media (max-width: 1300px) { .ecb-hero-grid { grid-template-columns:repeat(2,1fr); } }
@media (max-width: 720px)  { .ecb-hero-grid { grid-template-columns:1fr; } }

.ecb-hero {
  position:relative;
  background:#FAFAFB;
  border:0.5px solid rgba(15,23,60,.06);
  border-radius:10px;
  padding:14px 16px 12px;
  overflow:hidden;
  cursor:pointer;
  transition: transform .16s ease, box-shadow .16s ease, border-color .16s ease;
  animation: ecbIn .42s var(--ease-standard) both;
}
.ecb-hero:hover { transform:translateY(-2px); box-shadow:0 8px 22px rgba(15,23,60,.08); border-color: rgba(127,119,221,.18); }
.ecb-hero::before {
  content:""; position:absolute; top:0; left:0; right:0; height:3px;
  background:var(--kc); z-index:1; border-radius:10px 10px 0 0;
  transform-origin:left center;
  animation: ecbBreathe 2.8s ease-in-out 1s infinite;
}
.ecb-hero::after {
  content:""; position:absolute; top:0; left:0; right:0; height:3px;
  background:linear-gradient(90deg, transparent, rgba(255,255,255,.65), transparent);
  background-size:200% 100%; animation:ecbShim 6s ease-in-out 1.2s infinite;
  z-index:2; pointer-events:none; border-radius:10px 10px 0 0;
  transform:translateX(-120%);
}
.ecb-hero-l { font-size:9.5px; font-weight:600; color: var(--t3, var(--t-muted)); letter-spacing:.06em; text-transform:uppercase; margin-bottom:8px; display:flex; align-items:center; gap:3px; line-height:1.3; }
.ecb-hero-v { font-size:28px; font-weight:400; color: var(--t1, #1E2A4A); letter-spacing:-.025em; line-height:1; font-feature-settings:"tnum"; }
.ecb-hero-d { font-size:11px; color: var(--t3, var(--t-muted)); font-weight:500; margin-top:6px; font-feature-settings:"tnum"; }
.ecb-hero-click { position:absolute; right:12px; top:12px; font-size:9px; color:#B4B2A9; opacity:0; transition:opacity .14s; }
.ecb-hero:hover .ecb-hero-click { opacity:1; }

/* Loan composition row (repaid / outstanding) */
.ecb-lc { display:flex; align-items:stretch; background:#FAFAFB; border:0.5px solid rgba(15,23,60,.06); border-radius:10px; overflow:hidden; height:56px; margin-top:10px; }
.ecb-lc-seg { padding:9px 14px; display:flex; flex-direction:column; justify-content:center; cursor:pointer; }
.ecb-lc-seg-l { font-size:9.5px; font-weight:600; text-transform:uppercase; letter-spacing:.06em; opacity:.7; display:flex; align-items:center; gap:3px; }
.ecb-lc-seg-v { font-size:15px; font-weight:500; letter-spacing:-.015em; font-feature-settings:"tnum"; margin-top:1px; }
.ecb-lc-seg-v small { font-size:10px; font-weight:500; margin-left:4px; opacity:.7; }
.ecb-lc-r { background:rgba(29,158,117,.14); color:#0F6E56; }
.ecb-lc-o { background:rgba(127,119,221,.14); color:var(--p-deep); border-left:1px dashed rgba(0,0,0,.06); }

/* Mini KPI grid (4 поменьше) */
.ecb-mini-grid { display:grid; grid-template-columns:repeat(4,1fr); gap:10px; }
@media (max-width: 1300px) { .ecb-mini-grid { grid-template-columns:repeat(2,1fr); } }
@media (max-width: 720px)  { .ecb-mini-grid { grid-template-columns:1fr; } }

.ecb-mini {
  background:#FAFAFB;
  border:0.5px solid rgba(15,23,60,.06);
  border-radius:10px;
  padding:12px 14px 10px;
  cursor:pointer;
  transition: transform .16s ease, box-shadow .16s ease, border-color .16s ease;
}
.ecb-mini:hover { transform:translateY(-2px); box-shadow:0 6px 16px rgba(15,23,60,.06); border-color:rgba(127,119,221,.14); }
.ecb-mini-l { font-size:9.5px; font-weight:600; color: var(--t3, var(--t-muted)); letter-spacing:.06em; text-transform:uppercase; margin-bottom:6px; line-height:1.3; display:flex; align-items:center; gap:2px; }
.ecb-mini-v { font-size:20px; font-weight:400; color: var(--t1, #1E2A4A); letter-spacing:-.02em; line-height:1; font-feature-settings:"tnum"; }
.ecb-mini-d { font-size:10px; font-weight:500; color: var(--t3, var(--t-muted)); margin-top:5px; font-feature-settings:"tnum"; }

/* 2-col cards (donut: тип кредитора / валюта долга) */
.ecb-2col { display:grid; grid-template-columns:1fr 1fr; gap:12px; align-items:stretch; }
@media (max-width: 1300px) { .ecb-2col { grid-template-columns:1fr; } }
.ecb-card {
  background:#FAFAFB;
  border:0.5px solid rgba(15,23,60,.06);
  border-radius:10px;
  padding:14px 16px;
  display:flex;
  flex-direction:column;
}
.ecb-card .ecb-donut-wrap { flex:1; }
.ecb-card-h { font-size:11px; font-weight:600; color: var(--t1, #1E2A4A); margin-bottom:10px; display:flex; align-items:center; gap:4px; }
.ecb-card-h-r { margin-left:auto; font-size:9.5px; color:#B4B2A9; font-weight:500; }

/* Donut */
.ecb-donut-wrap { display:grid; grid-template-columns:160px 1fr; gap:18px; align-items:center; }
.ecb-donut-svg-wrap { position:relative; width:160px; height:160px; }
.ecb-donut-svg { width:100%; height:100%; transform:rotate(-90deg); }
.ecb-donut-seg { cursor:pointer; transition:stroke-width .14s; animation:ecbDonut .5s var(--ease-standard) both; animation-delay: calc(var(--di) * 80ms); }
.ecb-donut-seg:hover { stroke-width:8; }
.ecb-donut-center { position:absolute; inset:0; display:flex; flex-direction:column; align-items:center; justify-content:center; pointer-events:none; }
.ecb-donut-center-v { font-size:18px; font-weight:500; color: var(--t1, #1E2A4A); letter-spacing:-.02em; font-feature-settings:"tnum"; text-align:center; }
.ecb-donut-center-l { font-size:9.5px; color: var(--t3, var(--t-muted)); text-transform:uppercase; letter-spacing:.07em; margin-top:4px; font-weight:600; }

/* Donut legend */
.ecb-donut-legend { display:flex; flex-direction:column; gap:6px; }
.ecb-leg-row { display:grid; grid-template-columns:auto 1fr auto; gap:8px; align-items:center; cursor:pointer; padding:4px 6px; border-radius:6px; transition:background .14s; }
.ecb-leg-row:hover { background:rgba(127,119,221,.06); }
.ecb-leg-dot { width:9px; height:9px; border-radius:2px; flex-shrink:0; }
.ecb-leg-mid { display:flex; flex-direction:column; gap:3px; min-width:0; }
.ecb-leg-mid-l { font-size:11px; color: var(--t1, #1E2A4A); font-weight:500; }
.ecb-leg-mid-b { height:3px; background:rgba(15,23,60,.06); border-radius:2px; overflow:hidden; }
.ecb-leg-mid-b-fill { height:100%; transition:width .35s ease; }
.ecb-leg-r { text-align:right; display:flex; flex-direction:column; gap:1px; }
.ecb-leg-r-v { font-size:11px; font-weight:500; font-feature-settings:"tnum"; color: var(--t1, #1E2A4A); }
.ecb-leg-r-p { font-size:10px; color: var(--t3, var(--t-muted)); font-weight:500; }

/* Maturity grid (bars) */
.ecb-mat-wrap { display:grid; grid-template-columns:repeat(5,1fr); gap:10px; padding:6px 0; }
.ecb-mat-col { display:flex; flex-direction:column; align-items:center; gap:6px; cursor:pointer; padding:6px; border-radius:8px; transition:background .14s; }
.ecb-mat-col:hover { background:rgba(127,119,221,.04); }
.ecb-mat-l { font-size:9.5px; color: var(--t3, var(--t-muted)); font-weight:600; text-transform:uppercase; letter-spacing:.06em; }
.ecb-mat-bar-area { width:100%; height:64px; display:flex; align-items:flex-end; justify-content:center; }
.ecb-mat-bar { width:78%; border-radius:4px 4px 0 0; transform:scaleY(0); transform-origin:bottom; animation:ecbBarV .5s var(--ease-standard) forwards; animation-delay:calc(var(--mi) * 70ms + 100ms); }
.ecb-mat-v { font-size:11px; font-weight:500; font-feature-settings:"tnum"; color: var(--t1, #1E2A4A); }
.ecb-mat-d { font-size:9.5px; color: var(--t3, var(--t-muted)); font-weight:500; font-feature-settings:"tnum"; }
</style>