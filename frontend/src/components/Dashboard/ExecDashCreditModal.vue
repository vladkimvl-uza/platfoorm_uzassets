<!--
  ExecDashCreditModal.vue — Pack 7.44 (fixes Pack 7.41 modal).

  Fixes:
    1. Alias "due_12mo"/"due12mo" and "expected_loss"/"el" (block sends one, modal expected another)
    2. Number() coerce on Decimal-as-string everywhere (was: crash on toFixed in case "rate")
    3. Loans table shows NATIVE currency if loan.debt_currency present
    4. Currency segment mini-KPI includes native amount
    5. Robust seg.pct handling (Number coerce)
-->
<template>
  <Teleport to="body">
    <div class="ecm-overlay" @click.self="$emit('close')">
      <div class="ecm" :style="{ '--mc': accentColor }">
        <div class="ecm-stripe"></div>
        <div class="ecm-inner">
          <div class="ecm-hdr">
            <div>
              <div class="ecm-hdr-eyebrow">{{ eyebrowText }}</div>
              <h2 class="ecm-hdr-title">{{ titleText }}</h2>
            </div>
            <button class="ecm-x" @click="$emit('close')" title="Закрыть">
              <svg width="14" height="14" viewBox="0 0 14 14" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M3.5 3.5l7 7M10.5 3.5l-7 7"/></svg>
            </button>
          </div>

          <div class="ecm-mm">
            <div v-for="mk in miniKpis" :key="mk.l" class="ecm-mmi" :style="{ '--kc': mk.c }">
              <div class="ecm-mmi-l">{{ mk.l }}</div>
              <div class="ecm-mmi-v">{{ mk.v }}</div>
              <div class="ecm-mmi-d" v-if="mk.d" :style="{ color: mk.c }">{{ mk.d }}</div>
            </div>
          </div>

          <div v-if="loading" class="ecm-skel"><div class="ecm-skel-row"></div><div class="ecm-skel-row"></div></div>

          <template v-if="!loading && companies.length">
            <div class="ecm-l">TOP {{ companies.length }} предприятий</div>
            <table class="ecm-tbl">
              <thead><tr><th>Предприятие</th><th class="r">долг $ млн</th><th class="r">%</th></tr></thead>
              <tbody>
                <tr v-for="r in companies" :key="r.key">
                  <td>
                    <div class="ecm-cell-name">{{ r.label_ru }}
                      <small v-if="r.loans_count">{{ r.loans_count }} кр<span v-if="r.banks_count"> · {{ r.banks_count }} банка</span></small>
                    </div>
                  </td>
                  <td class="r">{{ fmtUsdMln(r.debt_usd) }}</td>
                  <td class="r">
                    <div class="ecm-bar-cell">
                      <div class="ecm-bar-track"><div class="ecm-bar-fill" :style="{ background: accentColor, width: `${Math.min(100, Number(r.pct) || 0)}%` }"></div></div>
                      <span class="ecm-bar-v">{{ fmtPct(r.pct, 1) }}</span>
                    </div>
                  </td>
                </tr>
              </tbody>
            </table>
          </template>

          <template v-if="!loading && banks.length">
            <div class="ecm-l">TOP {{ banks.length }} банков-кредиторов</div>
            <table class="ecm-tbl">
              <thead><tr><th>Кредитор</th><th class="r">долг $ млн</th><th class="r">кр</th><th class="r">%</th></tr></thead>
              <tbody>
                <tr v-for="r in banks" :key="r.key">
                  <td>
                    <div class="ecm-cell-name">{{ r.label_ru }}
                      <small><span class="ecm-tag" :class="`ecm-tag-${r.lender_type}`">{{ lenderLabel(r.lender_type) }}</span></small>
                    </div>
                  </td>
                  <td class="r">{{ fmtUsdMln(r.debt_usd) }}</td>
                  <td class="r">{{ r.loans_count }}</td>
                  <td class="r">{{ fmtPct(r.pct, 1) }}</td>
                </tr>
              </tbody>
            </table>
          </template>

          <template v-if="!loading && loans.length">
            <div class="ecm-l">TOP {{ loans.length }} кредитов</div>
            <table class="ecm-tbl">
              <thead><tr>
                <th>Заёмщик / банк</th>
                <th class="r">долг (нативн.)</th>
                <th class="r">долг $ млн</th>
                <th class="r">ставка</th>
                <th class="r">срок</th>
                <th>статус</th>
              </tr></thead>
              <tbody>
                <tr v-for="r in loans" :key="r.loan_id">
                  <td>
                    <div class="ecm-cell-name">{{ r.company_name }}
                      <small>← {{ r.bank }}<span v-if="r.borrower_unit"> · {{ r.borrower_unit }}</span></small>
                    </div>
                  </td>
                  <td class="r">
                    <span v-if="r.debt_currency && r.currency">{{ fmtNative(r.debt_currency, r.currency) }}</span>
                    <span v-else class="ecm-muted">—</span>
                  </td>
                  <td class="r">{{ r.debt_usd ? fmtUsdMln(r.debt_usd) : '—' }}</td>
                  <td class="r">{{ r.rate ? fmtPct(Number(r.rate) * 100, 2) : '—' }}</td>
                  <td class="r">{{ r.date_due ? r.date_due.slice(0, 7) : '—' }}</td>
                  <td>
                    <span v-if="r.is_guaranteed" class="ecm-tag ecm-tag-guar">госгарантия</span>
                    <span v-if="(r.overdue_days || 0) > 0" class="ecm-tag ecm-tag-overdue">просрочка {{ r.overdue_days }}д</span>
                  </td>
                </tr>
              </tbody>
            </table>
          </template>

          <div class="ecm-mtt"><strong>{{ explainTitle }}</strong> {{ explainText }}</div>
        </div>

        <div class="ecm-foot">
          <div class="ecm-foot-l">источник: <strong>credit-portfolio</strong> · фильтр: <strong>{{ filterDesc }}</strong></div>
          <div class="ecm-foot-actions">
            <button class="ecm-btn" @click="$emit('close')">Закрыть</button>
            <button class="ecm-btn ecm-btn-p" @click="goCreditPortfolio">Открыть в credit-portfolio</button>
          </div>
        </div>
      </div>
    </div>
  </Teleport>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from "vue"
import * as api from "@/api/creditScenario"
import { fmtUsdMlrd, fmtUsdMln, fmtPct, fmtCount } from "@/composables/useCreditScenario"
import { useFormatters } from "@/composables/useFormatters"

const fmt = useFormatters()

const props = defineProps<{ kind: string; payload: any }>()
defineEmits<{ (e: "close"): void }>()

const loading = ref(false)
const companies = ref<any[]>([])
const banks = ref<any[]>([])
const loans = ref<any[]>([])

const overview = computed(() => props.payload?.overview)

// === Pack 7.44 — normalize kind alias (block sends both styles) ===
const kindNorm = computed(() => {
  const k = props.kind
  if (k === "due_12mo") return "due12mo"
  if (k === "expected_loss") return "el"
  return k
})

const KIND_META: Record<string, { title: string; eyebrow: string; accent: string; explain: string }> = {
  portfolio: { title: "Кредитный портфель", eyebrow: "размер программы", accent: "#534AB7",
    explain: "Сумма всех изначальных размеров кредитов по подписанным договорам, пересчитанных в USD по курсу на дату получения. SUM(sum_total_usd). Размер программы, не текущая задолженность." },
  outstanding: { title: "Общий долг outstanding", eyebrow: "детализация показателя", accent: "#7F77DD",
    explain: "Сумма колонки debt_usd по всем активным кредитам — сколько 22 предприятия должны прямо сейчас. SELECT SUM(debt_usd) WHERE deleted_at IS NULL." },
  rate: { title: "Средневзвешенная ставка", eyebrow: "по размеру долга", accent: "#EF9F27",
    explain: "Σ(rate × debt_usd) / Σ debt_usd. Большие кредиты весят больше. Не путать с простой средней." },
  guaranteed: { title: "Кредиты с государственной гарантией", eyebrow: "доля защищённого долга", accent: "#1D9E75",
    explain: "Кредиты где правительство покрывает основной долг при дефолте. Обычно льготная ставка. Снижает риск для кредиторов." },
  due12mo: { title: "Платежи следующих 12 месяцев", eyebrow: "обслуживание долга", accent: "#EF9F27",
    explain: "Сумма из loan_repayments где period_year + period_quarter попадает в окно сегодня + 365 дней." },
  fx: { title: "Валютная подверженность (FX exposure)", eyebrow: "не в сумах", accent: "#EF9F27",
    explain: "Доля кредитов в иностранной валюте (всё кроме UZS). При ослаблении сума обслуживание дорожает." },
  overdue: { title: "Просроченная задолженность", eyebrow: "требуют срочных действий", accent: "#E24B4A",
    explain: "Кредиты где date_due < сегодня и debt_usd > 0. Срочные действия: реструктуризация, доп.гарантии, списание." },
  el: { title: "Ожидаемые потери (Basel Expected Loss)", eyebrow: "потенциальные убытки", accent: "#E24B4A",
    explain: "Σ по кредитам: debt × PD × (1 − RR). PD = вероятность дефолта (2.5% базовый, ×5 для просрочки), RR = recovery rate (60% гос / 50% мест / 45% инст / 40% бонд). Формула редактируется в админ-разделе." },
}

const SEGMENT_META: Record<string, Record<string, { title: string; explain: string }>> = {
  lender_type: {
    state:   { title: "Государственные кредиты",                 explain: "Прямые кредиты от Минфина РУ и Госказначейства РУ. Льготные ставки (3–4%). Под политикой реструктуризации/списания." },
    local:   { title: "Кредиты от местных банков",               explain: "Узпромстройбанк, Национальный банк РУ, Асака, Капиталбанк. Рыночные ставки (7–14%)." },
    foreign: { title: "Кредиты от иностранных кредиторов",       explain: "Эксим Банк Китая, Азиатский банк развития, Всемирный банк, IFC, IsDB, AIIB. Часто в долларах/юанях/евро." },
    bond:    { title: "Облигационные займы",                     explain: "Долговые ценные бумаги. Фиксированная ставка купона." },
  },
  currency: {
    USD: { title: "Кредиты в долларах США",         explain: "Долларовые кредиты — самый крупный сегмент валютного долга. Прямая зависимость от курса USD/UZS." },
    UZS: { title: "Кредиты в сумах",                explain: "В национальной валюте. Без валютного риска. Обычно от местных банков." },
    CNY: { title: "Кредиты в юанях",                explain: "От китайских кредиторов (Эксим Банк Китая, AIIB). Привязка к ставке SHIBOR." },
    EUR: { title: "Кредиты в евро",                 explain: "От европейских банков и международных организаций. Привязка к EURIBOR." },
    JPY: { title: "Кредиты в иенах",                explain: "Японские льготные займы (JICA). Долгосрочные, низкая ставка." },
    RUB: { title: "Кредиты в рублях",               explain: "От российских кредитных линий. В последние годы доля снижается." },
    SDR: { title: "Кредиты в SDR (МВФ)",            explain: "Specials Drawing Rights — корзина МВФ из USD/EUR/CNY/JPY/GBP." },
    KZT: { title: "Кредиты в тенге",                explain: "От казахстанских банков и фондов." },
    GBP: { title: "Кредиты в фунтах стерлингов",    explain: "От британских банков и UK Export Finance." },
    OTHER: { title: "Кредиты в прочих валютах",     explain: "Все остальные валюты." },
  },
  maturity: {
    overdue: { title: "Просроченные кредиты",                 explain: "date_due < сегодня и debt_usd > 0. Требуют немедленных действий." },
    lt_1y:   { title: "Кредиты к погашению в течение года",   explain: "365 дней до date_due. Краткосрочная нагрузка на cash flow." },
    "1_3y":  { title: "Кредиты со сроком 1–3 года",           explain: "Среднесрочный сегмент. Основа портфеля." },
    "3_5y":  { title: "Кредиты со сроком 3–5 лет",            explain: "Долгосрочный сегмент. Капитальные проекты." },
    gt_5y:   { title: "Долгосрочные кредиты (более 5 лет)",   explain: "Стратегические инвестиции, инфраструктура. Обычно с госгарантией." },
  },
}

const isSegment = computed(() => props.kind.startsWith("segment_"))

// Match credit-portfolio palette
const LENDER_COLOR: Record<string, string> = {
  state: "#C97070", local: "#5478B0", foreign: "#5DBFA1", bond: "#C99B5C",
}
const CURRENCY_COLOR: Record<string, string> = {
  USD: "#7F77DD", EUR: "#0A7B5E", CNY: "#EF9F27", JPY: "#E24B4A",
  SDR: "#9C8AC8", RUB: "#5B7FBC", UZS: "#888780", KZT: "#7A6C9F", GBP: "#385B82",
}

const accentColor = computed(() => {
  if (isSegment.value) {
    const dim = props.payload.dimension
    if (dim === "lender_type") return LENDER_COLOR[props.payload.value] || "#7F77DD"
    if (dim === "currency") return CURRENCY_COLOR[props.payload.value] || "#888780"
    if (dim === "maturity") {
      return ({ overdue: "#E24B4A", lt_1y: "#EF9F27", "1_3y": "#7F77DD", "3_5y": "#534AB7", gt_5y: "#1D9E75" } as any)[props.payload.value] || "#7F77DD"
    }
  }
  return KIND_META[kindNorm.value]?.accent || "#7F77DD"
})

const titleText = computed(() => {
  if (isSegment.value) return SEGMENT_META[props.payload.dimension]?.[props.payload.value]?.title || "Сегмент"
  return KIND_META[kindNorm.value]?.title || "Деталь"
})

const eyebrowText = computed(() => {
  if (isSegment.value) {
    const dim = props.payload.dimension
    return `${dim === "lender_type" ? "тип кредитора" : dim === "currency" ? "валюта долга" : "срок погашения"} · детализация`
  }
  return KIND_META[kindNorm.value]?.eyebrow || ""
})

const explainTitle = computed(() => isSegment.value ? "Особенность сегмента:" : "Как считается:")
const explainText = computed(() => {
  if (isSegment.value) return SEGMENT_META[props.payload.dimension]?.[props.payload.value]?.explain || ""
  return KIND_META[kindNorm.value]?.explain || ""
})

const filterDesc = computed(() => {
  if (isSegment.value) return `${props.payload.dimension} = ${props.payload.value}`
  const k = kindNorm.value
  if (k === "guaranteed") return "is_guaranteed = true"
  if (k === "overdue") return "overdue_days > 0"
  if (k === "due12mo") return "до 365 дней до date_due"
  return "все 22 предприятия"
})

// === Native currency formatter ===
// Number portion routes through fmt.fmtNumber so digit grouping & decimal
// separator switch with UI locale. Symbol + scale word kept manual because
// fmtMoneyCompact only knows UZS/USD/EUR/RUB/CNY.
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

  if (isUZS) {
    if (abs >= 1e12) return `${num(n / 1e12, 2)} трлн ${sym}`
    if (abs >= 1e9)  return `${num(n / 1e9, 1)} млрд ${sym}`
    if (abs >= 1e6)  return `${num(n / 1e6, 0)} млн ${sym}`
    return `${num(n, 0)} ${sym}`
  }
  if (currency === "JPY") {
    if (abs >= 1e9) return `${sym}${num(n / 1e9, 2)} млрд`
    if (abs >= 1e6) return `${sym}${num(n / 1e6, 1)} млн`
    return `${sym}${num(n, 0)}`
  }
  if (abs >= 1e9) return `${sym}${num(n / 1e9, 2)} млрд`
  if (abs >= 1e6) return `${sym}${num(n / 1e6, 1)} млн`
  if (abs >= 1e3) return `${sym}${num(n / 1e3, 1)} тыс`
  return `${sym}${num(n, 0)}`
}

// === Mini KPIs (all values Number() coerced for Decimal-as-string) ===
const miniKpis = computed(() => {
  const ov = overview.value
  if (!ov) return []
  const n = (x: any) => Number(x || 0)

  if (isSegment.value) {
    const dim = props.payload.dimension
    const val = props.payload.value
    const list = dim === "lender_type" ? ov.by_lender_type : dim === "currency" ? ov.by_currency : ov.by_maturity
    const seg: any = list.find((x: any) => x[dim === "lender_type" ? "lender_type" : dim === "currency" ? "currency" : "bucket"] === val)
    if (!seg) return []

    const kpis: any[] = []
    // For currency segment — show NATIVE amount as first KPI
    if (dim === "currency") {
      kpis.push({ l: `долг в ${val}`, v: fmtNative(seg.debt_currency, val), d: "нативная валюта", c: accentColor.value })
    }
    kpis.push({ l: "сегмент outstanding", v: fmtUsdMlrd(seg.debt_usd), d: `${fmtPct(seg.pct)} от портфеля`, c: dim === "currency" ? "#534AB7" : accentColor.value })
    kpis.push({ l: "кредитов в сегменте", v: fmtCount(seg.loans_count), d: "", c: "#7F77DD" })
    kpis.push({ l: "доля от всего outstanding", v: fmtPct(seg.pct, 1), d: "", c: "#EF9F27" })
    return kpis
  }

  switch (kindNorm.value) {
    case "portfolio":
      return [
        { l: "размер программы", v: fmtUsdMlrd(ov.portfolio_total_usd), d: `${fmtCount(ov.loans_count)} кредитов`, c: "#534AB7" },
        { l: "уже возвращено", v: fmtUsdMlrd(ov.repaid_usd), d: fmtPct(ov.repaid_pct), c: "#1D9E75" },
        { l: "остаётся", v: fmtUsdMlrd(ov.outstanding_usd), d: fmtPct(100 - n(ov.repaid_pct)), c: "#7F77DD" },
        { l: "банков-кредиторов", v: fmtCount(ov.banks_count), d: `${ov.companies_count}/${ov.soes_count} предпр.`, c: "#EF9F27" },
      ]
    case "outstanding":
      return [
        { l: "outstanding total", v: fmtUsdMlrd(ov.outstanding_usd), d: `${fmtCount(ov.loans_count)} кр`, c: "#7F77DD" },
        { l: "в иностр. валюте", v: fmtUsdMlrd(ov.fx_exposure_usd), d: fmtPct(ov.fx_exposure_pct), c: "#EF9F27" },
        { l: "с госгарантией", v: fmtUsdMlrd(ov.guaranteed_usd), d: fmtPct(ov.guaranteed_pct), c: "#1D9E75" },
        { l: "под риском EL", v: fmtUsdMlrd(ov.expected_loss_usd), d: `${ov.expected_loss_loans} флагнуто`, c: "#E24B4A" },
      ]
    case "rate":
      return [
        { l: "взвеш. ставка", v: fmtPct(ov.avg_rate_weighted, 2), d: "по всем кредитам", c: "#EF9F27" },
        { l: "годовые %-ные платежи", v: fmtUsdMlrd(n(ov.outstanding_usd) * n(ov.avg_rate_weighted) / 100), d: "оценка", c: "#854F0B" },
        { l: "outstanding base", v: fmtUsdMlrd(ov.outstanding_usd), d: "", c: "#7F77DD" },
        { l: "loans count", v: fmtCount(ov.loans_count), d: "в расчёте", c: "#534AB7" },
      ]
    case "guaranteed":
      return [
        { l: "с госгарантией", v: fmtUsdMlrd(ov.guaranteed_usd), d: fmtPct(ov.guaranteed_pct), c: "#1D9E75" },
        { l: "без гарантии", v: fmtUsdMlrd(n(ov.outstanding_usd) - n(ov.guaranteed_usd)), d: fmtPct(100 - n(ov.guaranteed_pct)), c: "#888780" },
        { l: "outstanding total", v: fmtUsdMlrd(ov.outstanding_usd), d: "", c: "#7F77DD" },
        { l: "защищённость", v: fmtPct(ov.guaranteed_pct, 1), d: "доля под гарантией", c: "#0F6E56" },
      ]
    case "due12mo":
      return [
        { l: "платежи 12 мес", v: fmtUsdMlrd(ov.due_12mo_usd), d: `${ov.due_12mo_loans} кр`, c: "#EF9F27" },
        { l: "доля от outstanding", v: n(ov.outstanding_usd) > 0 ? fmtPct(n(ov.due_12mo_usd) / n(ov.outstanding_usd) * 100) : "—", d: "", c: "#854F0B" },
        { l: "из них просрочено", v: fmtUsdMlrd(ov.overdue_usd), d: `${ov.overdue_loans} кр`, c: "#E24B4A" },
        { l: "loans с date_due", v: fmtCount(ov.due_12mo_loans), d: "ближайшие 12 мес", c: "#534AB7" },
      ]
    case "fx":
      return [
        { l: "валютный долг", v: fmtUsdMlrd(ov.fx_exposure_usd), d: fmtPct(ov.fx_exposure_pct), c: "#EF9F27" },
        { l: "в сумах", v: fmtUsdMlrd(n(ov.outstanding_usd) - n(ov.fx_exposure_usd)), d: fmtPct(100 - n(ov.fx_exposure_pct)), c: "#1D9E75" },
        { l: "общий outstanding", v: fmtUsdMlrd(ov.outstanding_usd), d: "", c: "#7F77DD" },
        { l: "валют в портфеле", v: fmtCount(ov.by_currency?.length || 0), d: "разных", c: "#534AB7" },
      ]
    case "overdue":
      return [
        { l: "просрочено", v: fmtUsdMlrd(ov.overdue_usd), d: `${ov.overdue_loans} кр`, c: "#E24B4A" },
        { l: "затронуто предпр.", v: fmtCount(ov.overdue_companies), d: `из ${ov.soes_count}`, c: "#A32D2D" },
        { l: "доля от outstanding", v: n(ov.outstanding_usd) > 0 ? fmtPct(n(ov.overdue_usd) / n(ov.outstanding_usd) * 100, 2) : "—", d: "", c: "#854F0B" },
        { l: "outstanding total", v: fmtUsdMlrd(ov.outstanding_usd), d: "", c: "#7F77DD" },
      ]
    case "el":
      return [
        { l: "EL по портфелю", v: fmtUsdMlrd(ov.expected_loss_usd), d: n(ov.outstanding_usd) > 0 ? fmtPct(n(ov.expected_loss_usd) / n(ov.outstanding_usd) * 100, 2) : "—", c: "#E24B4A" },
        { l: "флагнутых кредитов", v: fmtCount(ov.expected_loss_loans), d: "EL > $1k", c: "#A32D2D" },
        { l: "просрочка в EL", v: fmtUsdMlrd(ov.overdue_usd), d: "вес ×5 PD", c: "#EF9F27" },
        { l: "outstanding base", v: fmtUsdMlrd(ov.outstanding_usd), d: "", c: "#7F77DD" },
      ]
  }
  return []
})

function lenderLabel(lt: string) {
  return ({ state: "государство", local: "местный", foreign: "иностранный", bond: "облигация" } as any)[lt] || lt
}

async function loadData() {
  loading.value = true
  try {
    let filters: any = {}
    if (isSegment.value) {
      const dim = props.payload.dimension
      const key = dim === "maturity" ? "maturity_bucket" : dim
      filters[key] = props.payload.value
    }
    else if (kindNorm.value === "guaranteed") filters.is_guaranteed = true
    else if (kindNorm.value === "overdue") filters.overdue_only = true
    else if (kindNorm.value === "due12mo") filters.maturity_bucket = "lt_1y"

    if (isSegment.value || kindNorm.value === "overdue" || kindNorm.value === "guaranteed" || kindNorm.value === "due12mo") {
      const [cos, bs, ls] = await Promise.all([
        api.getDrilldownByCompany({ ...filters, top_n: 8 }).catch(() => []),
        api.getDrilldownByBank({ ...filters, top_n: 6 }).catch(() => []),
        api.getDrilldownLoans({ ...filters, limit: 8 }).catch(() => []),
      ])
      companies.value = cos
      banks.value = bs
      loans.value = ls
    } else {
      const [cos, bs] = await Promise.all([
        api.getDrilldownByCompany({ top_n: 10 }).catch(() => []),
        api.getDrilldownByBank({ top_n: 10 }).catch(() => []),
      ])
      companies.value = cos
      banks.value = bs
      loans.value = []
    }
  } finally {
    loading.value = false
  }
}

function goCreditPortfolio() { window.location.href = "/credit-portfolio" }

onMounted(loadData)
</script>

<style scoped>
@keyframes ecmIn { from{opacity:0; transform:translateY(20px) scale(.96)} to{opacity:1; transform:translateY(0) scale(1)} }
@keyframes ecmBgIn { from{opacity:0} to{opacity:1} }
@keyframes ecmShim { 0%{background-position:-100% 0} 100%{background-position:200% 0} }
@keyframes ecmPulse { 0%,100%{opacity:1} 50%{opacity:.4} }

.ecm-overlay { position:fixed; inset:0; background:rgba(15,18,40,.45); backdrop-filter:blur(8px); display:flex; align-items:flex-start; justify-content:center; padding:48px 24px; z-index:1000; animation:ecmBgIn .25s ease both; overflow-y:auto; }
.ecm { background: var(--bg1, #fff); border:1px solid var(--card-border, transparent); border-radius:14px; box-shadow:0 24px 64px rgba(15,23,60,.22), 0 8px 24px rgba(15,23,60,.10); width:100%; max-width:880px; overflow:hidden; animation:ecmIn .45s cubic-bezier(0.34, 1.2, 0.64, 1) both; }
.ecm-stripe { height:3px; background:var(--mc, #7F77DD); position:relative; overflow:hidden; }
.ecm-stripe::after { content:""; position:absolute; inset:0; background:linear-gradient(90deg, transparent, rgba(255,255,255,.5), transparent); background-size:200% 100%; animation:ecmShim 2.2s infinite; }
.ecm-inner { padding:18px 22px 18px; }
.ecm-hdr { display:flex; justify-content:space-between; align-items:flex-start; margin-bottom:12px; gap:12px; }
.ecm-hdr-eyebrow { font-size:9.5px; color: var(--t3, #888780); text-transform:uppercase; letter-spacing:.07em; font-weight:500; }
.ecm-hdr-title { font-size:16px; font-weight:500; color: var(--t1, #1E2A4A); letter-spacing:-.005em; margin:3px 0 4px; }
.ecm-x { width:28px; height:28px; border-radius:50%; background: var(--bg2, #FAFAFC); border:1px solid rgba(0,0,0,.08); display:flex; align-items:center; justify-content:center; cursor:pointer; color: var(--t3, #888780); flex-shrink:0; }
.ecm-x:hover { color: var(--t1, #1E2A4A); background: var(--bg1, #fff); border-color:rgba(0,0,0,.20); }

.ecm-mm { display:grid; grid-template-columns:repeat(4,1fr); gap:8px; margin:4px 0 14px; }
.ecm-mmi { background: var(--bg2, #FAFAFC); border-radius:7px; padding:9px 11px; position:relative; overflow:hidden; }
.ecm-mmi::before { content:""; position:absolute; top:0; left:0; right:0; height:2px; background:var(--kc); }
.ecm-mmi-l { font-size:8.5px; font-weight:500; color: var(--t3, #888780); text-transform:uppercase; letter-spacing:.05em; line-height:1.3; min-height:22px; }
.ecm-mmi-v { font-size:14px; font-weight:400; letter-spacing:-.015em; color: var(--t1, #1E2A4A); font-feature-settings:"tnum"; margin-top:2px; }
.ecm-mmi-d { font-size:9px; margin-top:2px; font-weight:500; }

.ecm-skel { padding:14px 0; }
.ecm-skel-row { height:36px; background:linear-gradient(90deg,rgba(15,23,60,.04),rgba(15,23,60,.08),rgba(15,23,60,.04)); background-size:200% 100%; animation:ecmPulse 1.4s infinite; border-radius:6px; margin-bottom:6px; }

.ecm-l { font-size:9.5px; color: var(--t3, #888780); text-transform:uppercase; letter-spacing:.07em; font-weight:500; margin:14px 0 6px; }

.ecm-tbl { width:100%; border-collapse:separate; border-spacing:0; font-size:10.5px; background: var(--bg1, #fff); border:1px solid rgba(0,0,0,.05); border-radius:8px; overflow:hidden; }
.ecm-tbl th { font-size:8.5px; font-weight:500; color: var(--t3, #888780); text-transform:uppercase; letter-spacing:.06em; padding:8px 8px; background: var(--bg2, #FAFAFC); text-align:left; border-bottom:1px solid rgba(0,0,0,.05); }
.ecm-tbl th.r { text-align:right; }
.ecm-tbl td { padding:8px 8px; border-bottom:1px solid rgba(0,0,0,.04); font-size:10.5px; vertical-align:middle; }
.ecm-tbl td.r { text-align:right; font-weight:500; color: var(--t1, #1E2A4A); font-feature-settings:"tnum"; }
.ecm-tbl tr:last-child td { border-bottom:none; }

.ecm-cell-name { font-size:10.5px; color: var(--t1, #1E2A4A); font-weight:500; line-height:1.3; }
.ecm-cell-name small { display:block; font-size:9px; color: var(--t3, #888780); margin-top:1px; font-weight:400; }
.ecm-muted { color:#B4B2A9; }

.ecm-bar-cell { display:flex; align-items:center; gap:6px; }
.ecm-bar-track { flex:1; height:5px; background:rgba(15,23,60,.04); border-radius:2px; overflow:hidden; min-width:50px; }
.ecm-bar-fill { height:100%; border-radius:2px; }
.ecm-bar-v { font-size:9.5px; color: var(--t3, #5F5E5A); font-weight:500; font-feature-settings:"tnum"; min-width:36px; text-align:right; }

.ecm-tag { display:inline-block; font-size:8px; font-weight:500; padding:2px 5px; border-radius:3px; text-transform:uppercase; letter-spacing:.04em; }
.ecm-tag-state { background:rgba(201,112,112,.16); color:#A04F4F; }
.ecm-tag-local { background:rgba(84,120,176,.14); color:#3A5994; }
.ecm-tag-foreign { background:rgba(93,191,161,.16); color:#0F6E56; }
.ecm-tag-bond { background:rgba(201,155,92,.16); color:#854F0B; }
.ecm-tag-guar { background:rgba(29,158,117,.10); color:#0F6E56; }
.ecm-tag-overdue { background:rgba(226,75,74,.10); color:#A32D2D; margin-left:3px; }

.ecm-mtt { font-size:10px; color: var(--t3, #5F5E5A); line-height:1.5; padding:10px 12px; background:rgba(127,119,221,.06); border-radius:6px; margin-top:14px; }
.ecm-mtt strong { color:#534AB7; font-weight:500; }

.ecm-foot { display:flex; justify-content:space-between; align-items:center; padding:12px 22px; border-top:1px solid rgba(0,0,0,.04); background: var(--bg2, #FAFAFC); }
.ecm-foot-l { font-size:10px; color: var(--t3, #888780); }
.ecm-foot-l strong { color: var(--t1, #1E2A4A); font-weight:500; }
.ecm-foot-actions { display:flex; gap:8px; }
.ecm-btn { font-family:inherit; font-size:10.5px; font-weight:500; padding:6px 11px; border-radius:6px; cursor:pointer; border:1px solid rgba(0,0,0,.10); background: var(--bg1, #fff); color: var(--t3, #5F5E5A); }
.ecm-btn:hover { color: var(--t1, #1E2A4A); border-color:rgba(0,0,0,.20); }
.ecm-btn-p { background:#7F77DD; color:#fff; border-color:#7F77DD; }
.ecm-btn-p:hover { background:#534AB7; }
</style>
