<!--
  CreditNagruzkaTab.vue — Pack 7.42

  Admin-секция «Кредитная нагрузка» внутри /admin/system-config (4-я вкладка).
  Семь inline-секций в одном файле:
    1. Header (scope filter + scenario picker)
    2. KPI strip (6 cards)
    3. Assumptions editor (autosave)
    4. Risk formula editor (validate + test)
    5. Custom indicators list (inline add/edit/delete)
    6. TOP loans table (inline per-loan overrides)
    7. Read-only viz: Debt ratios + Repayment waterfall
-->
<template>
  <div class="cnt">
    <!-- ═══════════════ 1. HEADER ═══════════════ -->
    <div class="cnt-hdr">
      <div>
        <div class="cnt-eyebrow">admin · сценарии и прогнозы</div>
        <h2 class="cnt-title">
          Кредитная нагрузка по 22 SOEs
          <span class="cnt-tip" :title="TT.intro">?</span>
        </h2>
        <p class="cnt-sub" v-if="summary">
          {{ fmtCount(summary.loans_count) }} кредитов ·
          {{ fmtCount(summary.companies_count) }} предприятий ·
          {{ fmtCount(summary.banks_count) }} банков ·
          в области охвата: <strong>{{ scopeLabel }}</strong>
        </p>
      </div>
      <div class="cnt-hdr-r">
        <label class="cnt-field">
          <span class="cnt-field-l">Активный сценарий<span class="cnt-tip" :title="TT.activeScenario">?</span></span>
          <select v-model="activeScenarioIdProxy" class="cnt-input">
            <option v-for="sc in scenarios" :key="sc.id" :value="sc.id">
              {{ sc.name_ru || sc.macro_scenario_key }}
            </option>
          </select>
        </label>
      </div>
    </div>

    <!-- Scope toggle -->
    <div class="cnt-scope" :title="TT.scope">
      <button
        v-for="opt in SCOPE_OPTIONS"
        :key="opt.value"
        type="button"
        class="cnt-scope-btn"
        :class="{ on: scope === opt.value }"
        @click="setScope(opt.value)"
      >
        {{ opt.label }}
        <small v-if="opt.hint">{{ opt.hint }}</small>
      </button>
    </div>

    <div v-if="error" class="cnt-alert cnt-alert-bad">{{ error }}</div>

    <!-- ═══════════════ 2. KPI STRIP ═══════════════ -->
    <div class="cnt-l"><span>KPI портфеля<span class="cnt-tip" :title="TT.kpi">?</span></span><span class="cnt-l-hint">пересчитывается при смене scope / сценария</span></div>
    <div class="cnt-kpi-grid" v-if="summary">
      <div class="cnt-kpi" style="--kc:#534AB7;">
        <div class="cnt-kpi-l">Outstanding<span class="cnt-tip" :title="TT.outstanding">?</span></div>
        <div class="cnt-kpi-v">{{ fmtUsdMlrd(summary.debt_outstanding_usd) }}</div>
        <div class="cnt-kpi-d">из ${{ (Number(summary.sum_total_usd) / 1e9).toFixed(2) }} млрд программы</div>
      </div>
      <div class="cnt-kpi" style="--kc:#1D9E75;">
        <div class="cnt-kpi-l">Возвращено<span class="cnt-tip" :title="TT.repaid">?</span></div>
        <div class="cnt-kpi-v">{{ fmtUsdMlrd(summary.repaid_usd) }}</div>
        <div class="cnt-kpi-d">{{ fmtPct(summary.repaid_pct) }}</div>
      </div>
      <div class="cnt-kpi" style="--kc:#EF9F27;">
        <div class="cnt-kpi-l">Средневзв. ставка<span class="cnt-tip" :title="TT.rate">?</span></div>
        <div class="cnt-kpi-v">{{ fmtPct(summary.avg_rate_pct, 2) }}</div>
        <div class="cnt-kpi-d">взвеш. по долгу</div>
      </div>
      <div class="cnt-kpi" style="--kc:#378ADD;">
        <div class="cnt-kpi-l">С госгарантией<span class="cnt-tip" :title="TT.guaranteed">?</span></div>
        <div class="cnt-kpi-v">{{ fmtPct(summary.guaranteed_pct) }}</div>
        <div class="cnt-kpi-d">{{ fmtUsdMlrd(summary.guaranteed_usd) }}</div>
      </div>
      <div class="cnt-kpi" style="--kc:#7F77DD;">
        <div class="cnt-kpi-l">К погашению 12мес<span class="cnt-tip" :title="TT.due12">?</span></div>
        <div class="cnt-kpi-v">{{ fmtUsdMlrd(summary.next_12mo_payments_usd) }}</div>
        <div class="cnt-kpi-d">{{ summary.debt_outstanding_usd > 0 ? fmtPct(summary.next_12mo_payments_usd / summary.debt_outstanding_usd * 100) : '—' }} от долга</div>
      </div>
      <div class="cnt-kpi" style="--kc:#E24B4A;">
        <div class="cnt-kpi-l">Ожидаемые потери EL<span class="cnt-tip" :title="TT.el">?</span></div>
        <div class="cnt-kpi-v">{{ fmtUsdMlrd(summary.expected_loss_usd) }}</div>
        <div class="cnt-kpi-d">{{ fmtCount(summary.flagged_loans_count) }} флагнуто</div>
      </div>
    </div>

    <!-- ═══════════════ 3. ASSUMPTIONS EDITOR ═══════════════ -->
    <div class="cnt-l"><span>Базовые допущения сценария<span class="cnt-tip" :title="TT.assumptions">?</span></span><span class="cnt-l-hint">автосохранение при потере фокуса</span></div>
    <div class="cnt-card" v-if="activeScenario">
      <div class="cnt-ae-grid">
        <label class="cnt-ae-field">
          <span class="cnt-ae-l">Списание госкредитов %<span class="cnt-tip" :title="TT.stateForg">?</span></span>
          <input
            type="number" step="0.1" min="0" max="100"
            class="cnt-input cnt-input-num"
            v-model.number="form.state_forgiveness_pct"
            @blur="saveField('state_forgiveness_pct')"
            :class="{ 'cnt-saved': savedFields.state_forgiveness_pct }"
          />
          <small class="cnt-ae-hint">сколько % основного долга государство спишет</small>
        </label>

        <label class="cnt-ae-field">
          <span class="cnt-ae-l">Изм. ставки рефин. (п.п.)<span class="cnt-tip" :title="TT.refDelta">?</span></span>
          <input
            type="number" step="0.25"
            class="cnt-input cnt-input-num"
            v-model.number="form.refinance_rate_delta_pp"
            @blur="saveField('refinance_rate_delta_pp')"
            :class="{ 'cnt-saved': savedFields.refinance_rate_delta_pp }"
          />
          <small class="cnt-ae-hint">+1.5 = ставка вырастет на 1.5 п.п. для гос. и местных</small>
        </label>

        <label class="cnt-ae-field">
          <span class="cnt-ae-l">Базовый default rate %<span class="cnt-tip" :title="TT.defaultRate">?</span></span>
          <input
            type="number" step="0.5" min="0" max="100"
            class="cnt-input cnt-input-num"
            v-model.number="form.default_rate_pct"
            @blur="saveField('default_rate_pct')"
            :class="{ 'cnt-saved': savedFields.default_rate_pct }"
          />
          <small class="cnt-ae-hint">вероятность дефолта в сценарии (PD baseline)</small>
        </label>

        <label class="cnt-ae-field">
          <span class="cnt-ae-l">Ускорение выплат %<span class="cnt-tip" :title="TT.accel">?</span></span>
          <input
            type="number" step="1" min="0" max="100"
            class="cnt-input cnt-input-num"
            v-model.number="form.repayment_acceleration_pct"
            @blur="saveField('repayment_acceleration_pct')"
            :class="{ 'cnt-saved': savedFields.repayment_acceleration_pct }"
          />
          <small class="cnt-ae-hint">на сколько % быстрее графика идут выплаты</small>
        </label>
      </div>
    </div>

    <!-- ═══════════════ 4. RISK FORMULA EDITOR ═══════════════ -->
    <div class="cnt-l"><span>Формула риска (Basel EL)<span class="cnt-tip" :title="TT.formula">?</span></span><span class="cnt-l-hint">EL = долг × PD × (1 − RR)</span></div>
    <div class="cnt-card cnt-rfe">
      <div class="cnt-rfe-vars">
        <strong>Доступные переменные:</strong>
        <code>debt_usd</code>, <code>rate</code>, <code>is_guaranteed</code>,
        <code>lender_type</code>, <code>currency</code>, <code>overdue_days</code>,
        <code>days_to_maturity</code>, <code>repayments_remaining</code>,
        <code>scenario.default_rate_pct</code>, <code>scenario.state_forgiveness_pct</code>,
        <code>loan.default_probability</code>, <code>custom.&lt;key&gt;</code>.
        Функции: <code>min</code>, <code>max</code>, <code>abs</code>, <code>round</code>.
      </div>
      <textarea
        v-model="formulaText"
        class="cnt-textarea"
        rows="8"
        spellcheck="false"
        placeholder="# Введите Python-выражение или используйте дефолт..."
      ></textarea>
      <div class="cnt-rfe-actions">
        <button type="button" class="cnt-btn" @click="loadDefaultFormula">Загрузить дефолт</button>
        <button type="button" class="cnt-btn" @click="onValidate">Валидировать</button>
        <button type="button" class="cnt-btn cnt-btn-p" @click="onTest">Тестировать на крупн. кредите</button>
        <button type="button" class="cnt-btn cnt-btn-g" @click="onSaveFormula" :disabled="!formulaValid">Сохранить в сценарий</button>
      </div>

      <div v-if="formulaValidate" class="cnt-rfe-result" :class="formulaValidate.ok ? 'cnt-rfe-ok' : 'cnt-rfe-bad'">
        <strong>{{ formulaValidate.ok ? '✓ Синтаксис корректен' : '✗ Ошибка' }}</strong>
        <div v-if="formulaValidate.error">{{ formulaValidate.error }}<span v-if="formulaValidate.error_line"> (строка {{ formulaValidate.error_line }})</span></div>
        <div v-if="formulaValidate.detected_variables?.length">
          Обнаружены: <code v-for="v in formulaValidate.detected_variables" :key="v">{{ v }}</code>
        </div>
      </div>

      <div v-if="formulaTest" class="cnt-rfe-test">
        <strong>Тест на крупнейшем кредите:</strong>
        <div v-if="formulaTest.ok">
          PD = <b>{{ fmtPct((formulaTest.pd || 0) * 100, 2) }}</b> ·
          RR = <b>{{ fmtPct((formulaTest.rr || 0) * 100, 2) }}</b> ·
          EL = <b>{{ fmtUsdMln(formulaTest.el_usd) }}</b>
          <details v-if="formulaTest.steps?.length" class="cnt-rfe-steps">
            <summary>Промежуточные шаги ({{ formulaTest.steps.length }})</summary>
            <ul>
              <li v-for="(s, i) in formulaTest.steps" :key="i"><code>{{ s.name }}</code> = {{ s.value }}</li>
            </ul>
          </details>
        </div>
        <div v-else class="cnt-rfe-bad-text">✗ {{ formulaTest.error }}</div>
      </div>
    </div>

    <!-- ═══════════════ 5. CUSTOM INDICATORS ═══════════════ -->
    <div class="cnt-l"><span>Кастомные индикаторы<span class="cnt-tip" :title="TT.customInd">?</span></span><span class="cnt-l-hint">переменные доступные в формуле как custom.&lt;key&gt;</span></div>
    <div class="cnt-card">
      <table class="cnt-tbl" v-if="customIndicators.length">
        <thead>
          <tr>
            <th>Key</th><th>Название</th><th>Тип</th><th class="r">мин</th><th class="r">макс</th><th class="r">значение</th><th>агрегация</th><th></th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="ind in customIndicators" :key="ind.id">
            <td><code>{{ ind.key }}</code></td>
            <td>{{ ind.name_ru }}</td>
            <td><span class="cnt-tag">{{ ind.input_type }}</span></td>
            <td class="r">{{ ind.min_value ?? '—' }}</td>
            <td class="r">{{ ind.max_value ?? '—' }}</td>
            <td class="r">
              <input
                type="number" step="0.01"
                class="cnt-input-inline"
                :value="ind.current_value"
                @blur="updateIndicatorValue(ind, $event)"
              />
            </td>
            <td><small>{{ ind.aggregation || '—' }}</small></td>
            <td><button class="cnt-btn-x" @click="onDeleteIndicator(ind.id)" title="Удалить">×</button></td>
          </tr>
        </tbody>
      </table>
      <div v-else class="cnt-empty">Нет кастомных индикаторов. Используйте форму ниже чтобы добавить первый.</div>

      <!-- Add form -->
      <div class="cnt-ci-add">
        <strong>Добавить индикатор:</strong>
        <div class="cnt-ci-add-row">
          <input v-model="newInd.key" placeholder="key (yuan_share)" class="cnt-input" />
          <input v-model="newInd.name_ru" placeholder="Название (Доля юаня)" class="cnt-input" />
          <select v-model="newInd.input_type" class="cnt-input">
            <option v-for="t in CI_TYPES" :key="t" :value="t">{{ t }}</option>
          </select>
          <input v-model.number="newInd.min_value" type="number" step="0.01" placeholder="мин" class="cnt-input cnt-input-num" />
          <input v-model.number="newInd.max_value" type="number" step="0.01" placeholder="макс" class="cnt-input cnt-input-num" />
          <input v-model.number="newInd.current_value" type="number" step="0.01" placeholder="значение" class="cnt-input cnt-input-num" />
          <button class="cnt-btn cnt-btn-p" @click="onCreateIndicator" :disabled="!newInd.key || !newInd.name_ru">+ Добавить</button>
        </div>
      </div>
    </div>

    <!-- ═══════════════ 6. TOP LOANS TABLE ═══════════════ -->
    <div class="cnt-l"><span>TOP-{{ topLoans.length }} кредитов<span class="cnt-tip" :title="TT.topLoans">?</span></span><span class="cnt-l-hint">inline-редактирование per-loan override</span></div>
    <div class="cnt-card cnt-tl-wrap" v-if="topLoans.length">
      <table class="cnt-tbl">
        <thead>
          <tr>
            <th>Заёмщик / банк</th>
            <th class="r">долг $ млн</th>
            <th class="r">ставка</th>
            <th class="r">срок</th>
            <th class="r" title="% списания этого конкретного кредита">списать %</th>
            <th class="r" title="новая ставка для этого конкретного кредита">нов. ставка</th>
            <th>статус</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="ln in topLoans" :key="ln.loan_id">
            <td>
              <div class="cnt-tl-name">{{ ln.company_name }}<small>← {{ ln.bank }}<span v-if="ln.borrower_unit"> · {{ ln.borrower_unit }}</span></small></div>
            </td>
            <td class="r">{{ ln.debt_usd ? fmtUsdMln(ln.debt_usd) : '—' }}</td>
            <td class="r">{{ ln.rate != null ? fmtPct(ln.rate * 100, 2) : '—' }}</td>
            <td class="r">{{ ln.date_due ? ln.date_due.slice(0, 7) : '—' }}</td>
            <td class="r">
              <input
                type="number" step="1" min="0" max="100"
                class="cnt-input-inline"
                :value="overrideOf(ln.loan_id)?.forgiveness_pct ?? null"
                @blur="onLoanOverride(ln.loan_id, 'forgiveness_pct', $event)"
                placeholder="—"
              />
            </td>
            <td class="r">
              <input
                type="number" step="0.001" min="0" max="1"
                class="cnt-input-inline"
                :value="overrideOf(ln.loan_id)?.rate_override ?? null"
                @blur="onLoanOverride(ln.loan_id, 'rate_override', $event)"
                placeholder="—"
              />
            </td>
            <td>
              <span v-if="ln.is_guaranteed" class="cnt-tag cnt-tag-guar">госгарантия</span>
              <span v-if="(ln.overdue_days || 0) > 0" class="cnt-tag cnt-tag-overdue">просрочка {{ ln.overdue_days }}д</span>
              <button v-if="overrideOf(ln.loan_id)" class="cnt-btn-x" @click="onDeleteOverride(ln.loan_id)" title="Удалить override">×</button>
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <!-- ═══════════════ 7. READ-ONLY VIZ: Debt ratios + Waterfall ═══════════════ -->
    <div class="cnt-l"><span>Аналитика портфеля<span class="cnt-tip" :title="TT.viz">?</span></span><span class="cnt-l-hint">read-only: отношения долга + квартальный график</span></div>
    <div class="cnt-2col">
      <div class="cnt-card">
        <div class="cnt-card-h">TOP-6 по Debt/EBITDA<span class="cnt-tip" :title="TT.debtEbitda">?</span></div>
        <table class="cnt-tbl cnt-tbl-tight" v-if="ratios.length">
          <tbody>
            <tr v-for="r in ratios" :key="r.company_id">
              <td>{{ r.company_name }}</td>
              <td class="r"><b>{{Number(r.ratio_value || 0).toFixed(2) }}×</b></td>
              <td><span class="cnt-tag" :class="`cnt-tag-${r.status}`">{{ r.status }}</span></td>
            </tr>
          </tbody>
        </table>
        <div v-else class="cnt-empty">Нет данных.</div>
      </div>

      <div class="cnt-card">
        <div class="cnt-card-h">Квартальный график погашения<span class="cnt-tip" :title="TT.waterfall">?</span></div>
        <div class="cnt-wf" v-if="forecast.length">
          <div v-for="y in forecast" :key="y.year" class="cnt-wf-yr">
            <div class="cnt-wf-yr-l">{{ y.year }}<span v-if="y.is_actual" class="cnt-wf-tag">факт</span></div>
            <div class="cnt-wf-bar-area">
              <div class="cnt-wf-bar" :style="{ height: `${barHeight(y.total_usd)}%` }"></div>
            </div>
            <div class="cnt-wf-v">{{ fmtUsdMln(y.total_usd) }}</div>
          </div>
        </div>
        <div v-else class="cnt-empty">Нет данных.</div>
      </div>
    </div>

  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from "vue"
import { useCreditScenario, fmtUsdMlrd, fmtUsdMln, fmtPct, fmtCount } from "@/composables/useCreditScenario"
import * as creditApi from "@/api/creditScenario"

const {
  scenarios, activeScenario, activeScenarioId, scope, scopeLabel,
  summary, ratios, forecast, topLoans, loanOverrides, customIndicators,
  isLoading, error,
  loadScenarios, setActiveScenario, setScope, saveActiveScenario,
  loadAll, loadSummary, loadForecast, loadTopLoans,
  upsertLoanOverride, deleteLoanOverride,
  createCustomIndicator, updateCustomIndicator, deleteCustomIndicator,
  validateFormula, testFormula, loadDefaults, defaultFormula,
} = useCreditScenario()

// v-model proxy for select
const activeScenarioIdProxy = computed({
  get: () => activeScenarioId.value || "",
  set: (v: string) => setActiveScenario(v || null),
})

const SCOPE_OPTIONS: Array<{ value: creditApi.LenderScope; label: string; hint?: string }> = [
  { value: "all_uz", label: "Все РУ", hint: "гос+местные" },
  { value: "state", label: "Гос." },
  { value: "local", label: "Местные" },
  { value: "foreign", label: "Иностран." },
  { value: "all", label: "Все", hint: "+облигации" },
]

const CI_TYPES = ["number", "percentage", "currency_usd", "currency_uzs", "ratio", "text"]

// ─── Forward decls (must be before watch on activeScenario) ───
const formulaText = ref<string>("")

// ─── 3. Assumptions form (autosave) ───
const form = reactive({
  state_forgiveness_pct: null as number | null,
  refinance_rate_delta_pp: null as number | null,
  default_rate_pct: null as number | null,
  repayment_acceleration_pct: null as number | null,
})
const savedFields = reactive<Record<string, boolean>>({})

watch(activeScenario, (sc) => {
  if (sc) {
    form.state_forgiveness_pct = sc.state_forgiveness_pct
    form.refinance_rate_delta_pp = sc.refinance_rate_delta_pp
    form.default_rate_pct = sc.default_rate_pct
    form.repayment_acceleration_pct = sc.repayment_acceleration_pct
    formulaText.value = sc.risk_formula_text || ""
  }
}, { immediate: true })

async function saveField(field: keyof typeof form) {
  if (!activeScenario.value) return
  try {
    await saveActiveScenario({ [field]: form[field] } as any)
    savedFields[field] = true
    setTimeout(() => { savedFields[field] = false }, 1500)
    // Recompute summary with new assumption
    await loadSummary()
  } catch (e) {
    console.error("saveField failed", e)
  }
}

// ─── 4. Risk formula editor (state) — formulaText объявлен выше ───
const formulaValidate = ref<creditApi.FormulaValidateResponse | null>(null)
const formulaTest = ref<creditApi.FormulaTestResponse | null>(null)
const formulaValid = computed(() => formulaValidate.value?.ok === true)

async function loadDefaultFormula() {
  if (!defaultFormula.value) await loadDefaults()
  formulaText.value = defaultFormula.value
}
async function onValidate() {
  formulaTest.value = null
  formulaValidate.value = await validateFormula(formulaText.value)
}
async function onTest() {
  if (!formulaValidate.value?.ok) await onValidate()
  if (!formulaValidate.value?.ok) return
  formulaTest.value = await testFormula(formulaText.value)
}
async function onSaveFormula() {
  await saveActiveScenario({ risk_formula_text: formulaText.value })
  await loadSummary()
}

// ─── 5. Custom indicators ───
const newInd = reactive<Partial<creditApi.CustomIndicator>>({
  key: "", name_ru: "", input_type: "number",
  min_value: null, max_value: null, current_value: null,
})
async function onCreateIndicator() {
  if (!newInd.key || !newInd.name_ru) return
  await createCustomIndicator({ ...newInd })
  newInd.key = ""; newInd.name_ru = ""
  newInd.min_value = null; newInd.max_value = null; newInd.current_value = null
}
async function onDeleteIndicator(id: string) {
  if (!confirm("Удалить индикатор?")) return
  await deleteCustomIndicator(id)
}
async function updateIndicatorValue(ind: creditApi.CustomIndicator, ev: Event) {
  const v = parseFloat((ev.target as HTMLInputElement).value)
  if (isNaN(v) || v === ind.current_value) return
  await updateCustomIndicator(ind.id, { current_value: v })
}

// ─── 6. TOP loans overrides ───
function overrideOf(loanId: string) {
  return loanOverrides.value.find((o) => o.loan_id === loanId)
}
async function onLoanOverride(loanId: string, field: string, ev: Event) {
  const raw = (ev.target as HTMLInputElement).value
  const v = raw === "" ? null : parseFloat(raw)
  if (raw !== "" && isNaN(v as number)) return
  const cur = overrideOf(loanId)
  if (cur && (cur as any)[field] === v) return
  await upsertLoanOverride(loanId, { [field]: v } as any)
}
async function onDeleteOverride(loanId: string) {
  if (!confirm("Удалить override для этого кредита?")) return
  await deleteLoanOverride(loanId)
}

// ─── 7. Waterfall bar heights ───
const maxForecastTotal = computed(() => Math.max(1, ...forecast.value.map((y) => y.total_usd)))
function barHeight(v: number) { return Math.max(3, (v / maxForecastTotal.value) * 100) }

// ─── Mount ───
onMounted(async () => {
  await loadScenarios()
  await loadAll()
})

// ─── Tooltips ───
const TT = {
  intro: "Раздел для управления сценариями кредитной нагрузки 22 SOEs. Все правки изолированы — не влияют на factual данные в credit-portfolio.",
  activeScenario: "Выбранный сценарий применяется ко всем расчётам ниже (KPI, формула риска, прогноз погашения).",
  scope: "Выбор подмножества кредиторов для всех KPI и графиков ниже. По умолчанию — внутренние РУ (гос. + местные).",
  kpi: "Сводка по портфелю в области охвата. Пересчитывается при смене сценария.",
  outstanding: "Текущая задолженность по выбранному scope. Учитывает % списания из сценария.",
  repaid: "Возвращено = Программа − Outstanding. Включает плановые и досрочные выплаты.",
  rate: "Σ(rate × debt) / Σ debt — взвешенная по размеру долга. Учитывает изменение ставки рефинанса из сценария.",
  guaranteed: "Доля кредитов с госгарантией. Влияет на recovery rate в формуле EL.",
  due12: "Платежи следующих 12 месяцев — основной долг + проценты по графику.",
  el: "Expected Loss = Σ debt × PD × (1 − RR). PD из формулы, RR из risk_rr_by_lender или is_guaranteed.",
  assumptions: "Базовые гипотезы — применяются ко всему портфелю в этом сценарии. Сохраняются автоматически.",
  stateForg: "% основного долга, который государство простит. Применяется к кредитам с lender_type='state'.",
  refDelta: "Изменение ставки рефинансирования в процентных пунктах (+/-). Применяется к гос. + местным.",
  defaultRate: "Базовая вероятность дефолта в этом сценарии (PD baseline). Может быть переопределена per-loan.",
  accel: "% ускорения выплат от планового графика. Используется в прогнозе погашения.",
  formula: "Python-выражение для расчёта Expected Loss. Возвращает финальное значение EL в USD. Безопасный AST-eval (без simpleeval).",
  customInd: "Custom-переменные, доступные в формуле через custom.<key>. Например: 'доля юаня', 'мораторий 2026'.",
  topLoans: "Топ-N кредитов по размеру долга. Inline-редактирование override: forgiveness% (% списания) и rate_override (новая ставка).",
  viz: "Read-only визуализация: топ-должники по Debt/EBITDA и квартальный график погашения.",
  debtEbitda: "Debt/EBITDA = долг / прибыль до налогов и амортизации. <2.5 здоровый, 2.5–3 повышенный, >3 критический.",
  waterfall: "Сумма плановых выплат (основной долг + проценты) по годам 2023–2030. Источник: loan_repayments.",
}
</script>

<style scoped>
.cnt { font-family:-apple-system,BlinkMacSystemFont,"Inter",sans-serif; color: var(--t1, #1E2A4A); padding:4px 0 24px; }

.cnt-hdr { display:flex; justify-content:space-between; align-items:flex-end; gap:16px; margin-bottom:14px; }
.cnt-hdr-r { display:flex; gap:10px; flex-shrink:0; }
.cnt-eyebrow { font-size:10px; font-weight:500; color: var(--t3, var(--t-muted)); text-transform:uppercase; letter-spacing:.08em; }
.cnt-title { font-size:20px; font-weight:500; letter-spacing:-.02em; margin:4px 0 4px; display:flex; align-items:center; gap:8px; }
.cnt-sub { font-size:11.5px; color: var(--t3, #5F5E5A); line-height:1.5; margin:0; }
.cnt-sub strong { color: var(--t1, #1E2A4A); font-weight:500; }

.cnt-tip { display:inline-flex; align-items:center; justify-content:center; width:14px; height:14px; font-size:9px; font-weight:500; border-radius:50%; background:rgba(127,119,221,.10); color:var(--p-deep); margin-left:3px; cursor:help; flex-shrink:0; }

.cnt-field { display:flex; flex-direction:column; gap:3px; }
.cnt-field-l { font-size:9.5px; color: var(--t3, var(--t-muted)); text-transform:uppercase; letter-spacing:.06em; font-weight:500; display:flex; align-items:center; gap:3px; }
.cnt-input { font-family:inherit; font-size:11.5px; padding:6px 10px; border:1px solid rgba(0,0,0,.10); border-radius:6px; background: var(--bg1, #fff); color: var(--t1, #1E2A4A); min-width:200px; transition:border-color .14s, box-shadow .14s; }
.cnt-input:focus { outline:none; border-color:#7F77DD; box-shadow:0 0 0 3px rgba(127,119,221,.10); }
.cnt-input-num { min-width:90px; text-align:right; font-feature-settings:"tnum"; }
.cnt-input-inline { font-family:inherit; font-size:10.5px; padding:3px 6px; border:1px solid rgba(0,0,0,.08); border-radius:4px; background: var(--bg2, #FAFAFC); color: var(--t1, #1E2A4A); width:70px; text-align:right; font-feature-settings:"tnum"; }
.cnt-input-inline:focus { outline:none; border-color:#7F77DD; background: var(--bg1, #fff); }

.cnt-scope { display:inline-flex; gap:4px; padding:3px; background:rgba(15,23,60,.05); border-radius:9px; margin-bottom:14px; }
.cnt-scope-btn { background:transparent; border:none; font-size:11px; font-weight:500; color: var(--t3, var(--t-muted)); padding:7px 14px; border-radius:6px; cursor:pointer; font-family:inherit; transition:all .14s; letter-spacing:.01em; display:flex; align-items:center; gap:5px; }
.cnt-scope-btn:hover:not(.on) { color: var(--t1, #1E2A4A); }
.cnt-scope-btn.on { background: var(--bg1, #fff); color: var(--t1, #1E2A4A); box-shadow:0 1px 3px rgba(15,23,60,.08); }
.cnt-scope-btn small { font-size:9px; color:#B4B2A9; }
.cnt-scope-btn.on small { color: var(--t3, var(--t-muted)); }

.cnt-alert { padding:9px 12px; border-radius:7px; font-size:11px; margin-bottom:10px; }
.cnt-alert-bad { background:rgba(226,75,74,.08); border:1px solid rgba(226,75,74,.20); color:var(--sev-critical); }

.cnt-l { font-size:10px; color: var(--t3, var(--t-muted)); text-transform:uppercase; letter-spacing:.07em; font-weight:500; margin:18px 0 8px; display:flex; justify-content:space-between; align-items:center; gap:8px; }
.cnt-l > span:first-child { display:flex; align-items:center; gap:3px; }
.cnt-l-hint { font-size:9.5px; color:#B4B2A9; text-transform:none; letter-spacing:.02em; font-weight:400; }

.cnt-card { background: var(--card-bg, rgba(255,255,255,0.82)); backdrop-filter: blur(16px) saturate(1.5); -webkit-backdrop-filter: blur(16px) saturate(1.5); border:1px solid var(--card-border, rgba(0,0,0,.06)); border-radius:10px; padding:14px 16px; margin-bottom:6px; }
.cnt-card-h { font-size:11px; font-weight:500; color: var(--t1, #1E2A4A); margin-bottom:10px; display:flex; align-items:center; gap:4px; }
.cnt-empty { font-size:11px; color: var(--t3, var(--t-muted)); padding:14px; text-align:center; }

/* ─── KPI grid ─── */
.cnt-kpi-grid { display:grid; grid-template-columns:repeat(6,1fr); gap:8px; margin-bottom:4px; }
.cnt-kpi { position:relative; background: var(--bg1, #fff); border:1px solid rgba(0,0,0,.06); border-radius:10px; padding:11px 12px; overflow:hidden; }
.cnt-kpi::before { content:""; position:absolute; top:0; left:0; right:0; height:2px; background:var(--kc); }
.cnt-kpi-l { font-size:9px; font-weight:500; color: var(--t3, var(--t-muted)); text-transform:uppercase; letter-spacing:.05em; line-height:1.3; min-height:24px; display:flex; align-items:center; gap:2px; }
.cnt-kpi-v { font-size:17px; font-weight:400; letter-spacing:-.02em; line-height:1.1; margin-top:3px; font-feature-settings:"tnum"; }
.cnt-kpi-d { font-size:9px; color: var(--t3, #5F5E5A); margin-top:3px; }

/* ─── Assumptions editor ─── */
.cnt-ae-grid { display:grid; grid-template-columns:repeat(4,1fr); gap:14px; }
.cnt-ae-field { display:flex; flex-direction:column; gap:4px; }
.cnt-ae-l { font-size:10px; font-weight:500; color: var(--t3, var(--t-muted)); text-transform:uppercase; letter-spacing:.05em; display:flex; align-items:center; gap:3px; }
.cnt-ae-hint { font-size:9.5px; color:#B4B2A9; }
.cnt-saved { animation:cntFlash 1.5s ease; }
@keyframes cntFlash { 0% { background:rgba(29,158,117,.15); } 100% { background: var(--bg1, #fff); } }

/* ─── Risk formula editor ─── */
.cnt-rfe-vars { font-size:10px; color: var(--t3, #5F5E5A); padding:8px 10px; background:rgba(127,119,221,.05); border-radius:6px; margin-bottom:8px; line-height:1.6; }
.cnt-rfe-vars strong { color:var(--p-deep); }
.cnt-rfe-vars code { background: var(--bg1, #fff); padding:1px 5px; border-radius:3px; font-family:'SF Mono', 'Cascadia Code', Consolas, monospace; font-size:9.5px; color: var(--t1, #1E2A4A); }
.cnt-textarea { width:100%; padding:10px 12px; border:1px solid rgba(0,0,0,.10); border-radius:7px; font-family:'SF Mono', 'Cascadia Code', Consolas, monospace; font-size:11px; line-height:1.55; resize:vertical; min-height:140px; background: var(--bg2, #FAFAFC); color: var(--t1, #1E2A4A); }
.cnt-textarea:focus { outline:none; border-color:#7F77DD; background: var(--bg1, #fff); }
.cnt-rfe-actions { display:flex; gap:6px; margin-top:8px; flex-wrap:wrap; }
.cnt-btn { font-family:inherit; font-size:10.5px; font-weight:500; padding:7px 12px; border-radius:6px; cursor:pointer; border:1px solid rgba(0,0,0,.10); background: var(--bg1, #fff); color: var(--t3, #5F5E5A); }
.cnt-btn:hover { color: var(--t1, #1E2A4A); border-color:rgba(0,0,0,.20); }
.cnt-btn:disabled { opacity:.4; cursor:not-allowed; }
.cnt-btn-p { background:#7F77DD; color:#fff; border-color:#7F77DD; }
.cnt-btn-p:hover { background:var(--p-deep); }
.cnt-btn-g { background:var(--green); color:#fff; border-color:var(--green); }
.cnt-btn-g:hover:not(:disabled) { background:#0F6E56; }
.cnt-btn-x { background:transparent; border:none; color:#B4B2A9; font-size:14px; cursor:pointer; padding:0 4px; line-height:1; }
.cnt-btn-x:hover { color:var(--sev-high); }

.cnt-rfe-result { font-size:11px; padding:9px 11px; border-radius:6px; margin-top:8px; }
.cnt-rfe-ok { background:rgba(29,158,117,.08); border:1px solid rgba(29,158,117,.20); color:#0F6E56; }
.cnt-rfe-bad { background:rgba(226,75,74,.08); border:1px solid rgba(226,75,74,.20); color:var(--sev-critical); }
.cnt-rfe-result code { display:inline-block; background: var(--bg1, #fff); padding:1px 5px; margin:2px 3px; border-radius:3px; font-family:'SF Mono', Consolas, monospace; font-size:10px; }
.cnt-rfe-test { font-size:11px; padding:9px 11px; border-radius:6px; margin-top:8px; background:rgba(127,119,221,.06); border:1px solid rgba(127,119,221,.15); }
.cnt-rfe-test strong { color:var(--p-deep); }
.cnt-rfe-test b { font-feature-settings:"tnum"; color: var(--t1, #1E2A4A); }
.cnt-rfe-bad-text { color:var(--sev-critical); }
.cnt-rfe-steps { margin-top:6px; }
.cnt-rfe-steps summary { cursor:pointer; font-size:10px; color: var(--t3, var(--t-muted)); }
.cnt-rfe-steps ul { margin:6px 0 0; padding-left:18px; font-size:10px; }
.cnt-rfe-steps code { background: var(--bg1, #fff); padding:1px 4px; border-radius:3px; font-family:'SF Mono', Consolas, monospace; }

/* ─── Tables ─── */
.cnt-tbl { width:100%; border-collapse:separate; border-spacing:0; font-size:10.5px; }
.cnt-tbl th { font-size:8.5px; font-weight:500; color: var(--t3, var(--t-muted)); text-transform:uppercase; letter-spacing:.06em; padding:8px 8px; text-align:left; border-bottom:1px solid rgba(0,0,0,.06); }
.cnt-tbl th.r { text-align:right; }
.cnt-tbl td { padding:8px 8px; border-bottom:1px solid rgba(0,0,0,.04); font-size:10.5px; vertical-align:middle; }
.cnt-tbl td.r { text-align:right; font-weight:500; color: var(--t1, #1E2A4A); font-feature-settings:"tnum"; }
.cnt-tbl tr:last-child td { border-bottom:none; }
.cnt-tbl code { background:rgba(127,119,221,.07); padding:1px 5px; border-radius:3px; font-size:10px; }

.cnt-tbl-tight td { padding:6px 8px; }
.cnt-tl-name { font-size:10.5px; font-weight:500; color: var(--t1, #1E2A4A); line-height:1.3; }
.cnt-tl-name small { display:block; font-size:9px; color: var(--t3, var(--t-muted)); margin-top:1px; font-weight:400; }
.cnt-tl-wrap { max-height:540px; overflow-y:auto; }

.cnt-tag { display:inline-block; font-size:8.5px; font-weight:500; padding:2px 6px; border-radius:3px; text-transform:uppercase; letter-spacing:.04em; background:rgba(136,135,128,.15); color: var(--t3, #5F5E5A); }
.cnt-tag-guar { background:rgba(29,158,117,.10); color:#0F6E56; }
.cnt-tag-overdue { background:rgba(226,75,74,.10); color:var(--sev-critical); margin-left:3px; }
.cnt-tag-healthy { background:rgba(29,158,117,.10); color:#0F6E56; }
.cnt-tag-elevated { background:rgba(239,159,39,.12); color:#854F0B; }
.cnt-tag-critical { background:rgba(226,75,74,.10); color:var(--sev-critical); }

/* ─── Custom indicators add form ─── */
.cnt-ci-add { margin-top:12px; padding:10px 12px; background: var(--bg2, #FAFAFC); border-radius:7px; border:1px dashed rgba(0,0,0,.08); }
.cnt-ci-add strong { display:block; font-size:10px; color: var(--t3, var(--t-muted)); text-transform:uppercase; letter-spacing:.06em; margin-bottom:8px; font-weight:500; }
.cnt-ci-add-row { display:flex; gap:6px; flex-wrap:wrap; align-items:center; }
.cnt-ci-add-row .cnt-input { min-width:auto; flex:1 1 100px; }

/* ─── Waterfall ─── */
.cnt-2col { display:grid; grid-template-columns:1fr 1fr; gap:10px; }
.cnt-wf { display:grid; grid-template-columns:repeat(8, 1fr); gap:6px; padding:6px 4px 0; }
.cnt-wf-yr { display:flex; flex-direction:column; align-items:center; }
.cnt-wf-yr-l { font-size:9.5px; font-weight:500; color: var(--t3, var(--t-muted)); display:flex; flex-direction:column; align-items:center; }
.cnt-wf-tag { font-size:7.5px; color:#B4B2A9; font-weight:400; }
.cnt-wf-bar-area { width:100%; height:80px; display:flex; align-items:flex-end; justify-content:center; margin:6px 0 4px; }
.cnt-wf-bar { width:80%; background:#7F77DD; border-radius:3px 3px 0 0; min-height:3px; transition:height .4s ease; }
.cnt-wf-v { font-size:9px; color: var(--t1, #1E2A4A); font-weight:500; font-feature-settings:"tnum"; text-align:center; }
</style>
