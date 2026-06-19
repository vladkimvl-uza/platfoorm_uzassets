<!--
  ElasticityProjectsTab.vue — Pack 7.43

  Пятая вкладка /admin/system-config: «Эластичность и проекты».

  3 секции:
    1. Матрица эластичности — таблица 22 SOE × 6 факторов × 6 метрик
       (упрощено: показываем только revenue + opex + capex; остальное в "advanced")
    2. Эффекты проектов — list по проектам с inline-edit полей
    3. Декомпозиция прогноза — waterfall для (компания, метрика, год)
-->
<template>
  <div class="ep">
    <!-- ═══════════ HEADER ═══════════ -->
    <div class="ep-hdr">
      <div>
        <div class="ep-eyebrow">admin · сценарии и прогнозы</div>
        <h2 class="ep-title">
          Эластичность и эффекты проектов
          <span class="ep-tip" :title="TT.intro">?</span>
        </h2>
        <p class="ep-sub">
          Связывает макроэкономику со сценариями: <strong>эластичность</strong> = чувствительность
          к макрофакторам · <strong>эффекты проектов</strong> = эффект конкретных проектов в цифрах ·
          <strong>декомпозиция</strong> = из чего складывается прогноз.
        </p>
      </div>
      <div class="ep-hdr-r">
        <button class="ep-btn" @click="loadAll" :disabled="loading">⟳ Обновить</button>
      </div>
    </div>

    <div v-if="error" class="ep-err">{{ error }}</div>

    <!-- ═══════════ Sub-tabs ═══════════ -->
    <div class="ep-subtabs">
      <button class="ep-stab" :class="{on: sub==='elasticity'}" @click="sub='elasticity'">
        Матрица эластичности
      </button>
      <button class="ep-stab" :class="{on: sub==='projects'}" @click="sub='projects'">
        Эффекты проектов
        <small v-if="effects.length">{{ effects.length }}</small>
      </button>
      <button class="ep-stab" :class="{on: sub==='decomposition'}" @click="sub='decomposition'">
        Декомпозиция прогноза
      </button>
    </div>

    <!-- ═══════════ Sub-section 1: ELASTICITY MATRIX ═══════════ -->
    <template v-if="sub==='elasticity'">
      <div class="ep-help">
        <strong>Что это:</strong> {{ TT.elasticity }}
        <br>
        <strong>Как читать β:</strong>
        <span class="ep-help-row">
          <span class="ep-help-bullet" style="color:#1D9E75;">●</span> β &gt; 0 — растёт вместе с фактором
          <span class="ep-help-bullet" style="color:#E24B4A;">●</span> β &lt; 0 — падает при росте фактора
          <span class="ep-help-bullet" style="color: var(--t3, #888780);">●</span> β = 0 — нечувствительно
        </span>
        <br>
        <strong>Сила:</strong> |β|&lt;0.3 — слабая · 0.3–0.7 — средняя · &gt;0.7 — сильная.
      </div>

      <!-- Filter -->
      <div class="ep-filter">
        <label class="ep-field">
          <span class="ep-field-l">Сценарий</span>
          <select v-model="filterScenario" class="ep-input">
            <option :value="null">Все (глобальные дефолты)</option>
            <option v-for="s in scenarios" :key="s.id" :value="s.id">
              {{ s.name_ru || s.code }}
            </option>
          </select>
        </label>
        <label class="ep-field">
          <span class="ep-field-l">Целевая метрика</span>
          <select v-model="filterMetric" class="ep-input">
            <option :value="null">Все метрики</option>
            <option v-for="m in constants?.target_metrics || []" :key="m.code" :value="m.code">
              {{ m.label_ru }}
            </option>
          </select>
        </label>
        <div class="ep-filter-add">
          <button class="ep-btn ep-btn-p" @click="openAddCoef">+ Добавить коэффициент</button>
        </div>
      </div>

      <!-- Matrix table -->
      <div class="ep-card">
        <table class="ep-tbl" v-if="filteredCoefs.length">
          <thead>
            <tr>
              <th>Скоуп<span class="ep-tip" :title="TT.scope">?</span></th>
              <th>Макрофактор</th>
              <th>Влияет на</th>
              <th class="r">β</th>
              <th>Источник</th>
              <th>Комментарий</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="c in filteredCoefs" :key="c.id">
              <td>
                <span class="ep-scope" :class="`ep-scope-${scopeKind(c)}`">{{ scopeLabel(c) }}</span>
              </td>
              <td>{{ macroLabel(c.macro_factor) }}</td>
              <td>{{ metricLabel(c.target_metric) }}</td>
              <td class="r">
                <input
                  type="number" step="0.01"
                  class="ep-input-inline"
                  :value="Number(c.beta)"
                  @blur="updateBeta(c, $event)"
                  :style="{ color: betaColor(c.beta) }"
                />
              </td>
              <td>
                <span class="ep-tag" :class="`ep-tag-${c.source}`">{{ sourceLabel(c.source) }}</span>
              </td>
              <td><small>{{ c.notes || '—' }}</small></td>
              <td><button class="ep-x" @click="onDeleteCoef(c.id)" title="Удалить">×</button></td>
            </tr>
          </tbody>
        </table>
        <div v-else-if="loading" class="ep-empty">Загрузка…</div>
        <div v-else class="ep-empty">
          Нет коэффициентов в этом срезе. Запустите миграции и сидинг через
          <code>POST /api/elasticity/_apply-migrations</code> чтобы создать глобальные дефолты.
        </div>
      </div>
    </template>

    <!-- ═══════════ Sub-section 2: PROJECT EFFECTS ═══════════ -->
    <template v-if="sub==='projects'">
      <div class="ep-help">
        <strong>Что это:</strong> {{ TT.projects }}
        <br>
        <strong>Логика:</strong> у каждого проекта может быть много эффектов — один на каждую пару
        (год × метрика). Например: «Modernize plant X»: +50 млрд сум к revenue в 2026, +120 в 2027.
        <br>
        <strong>Заполнение:</strong> данные вносят команды проектов. Пока поля пустые — прогноз считает
        что эффект = 0. Появятся данные → автоматически отразятся в декомпозиции.
      </div>

      <div class="ep-filter">
        <label class="ep-field">
          <span class="ep-field-l">Год</span>
          <select v-model="effectYear" class="ep-input">
            <option v-for="y in availableYears" :key="y" :value="y">{{ y }}</option>
          </select>
        </label>
        <label class="ep-field">
          <span class="ep-field-l">Метрика</span>
          <select v-model="effectMetric" class="ep-input">
            <option v-for="m in constants?.target_metrics || []" :key="m.code" :value="m.code">
              {{ m.label_ru }}
            </option>
          </select>
        </label>
        <div class="ep-filter-add">
          <button class="ep-btn ep-btn-p" @click="openAddEffect">+ Добавить эффект</button>
        </div>
      </div>

      <div class="ep-card">
        <table class="ep-tbl" v-if="effects.length">
          <thead>
            <tr>
              <th>Проект</th>
              <th>Год</th>
              <th>Метрика</th>
              <th class="r">Δ млн сум</th>
              <th class="r">Δ %</th>
              <th class="r">Вероятн.</th>
              <th>Уверен.</th>
              <th>Комментарий</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="e in effects" :key="e.id">
              <td><code>{{ e.project_id.slice(0, 8) }}</code></td>
              <td>{{ e.effective_year }}</td>
              <td>{{ metricLabel(e.target_metric) }}</td>
              <td class="r">
                <input
                  type="number" step="100"
                  class="ep-input-inline"
                  :value="e.delta_value_uzs_mln != null ? Number(e.delta_value_uzs_mln) : null"
                  @blur="updateEffect(e, 'delta_value_uzs_mln', $event)"
                  placeholder="—"
                />
              </td>
              <td class="r">
                <input
                  type="number" step="0.1"
                  class="ep-input-inline"
                  :value="e.delta_pct != null ? Number(e.delta_pct) : null"
                  @blur="updateEffect(e, 'delta_pct', $event)"
                  placeholder="—"
                />
              </td>
              <td class="r">
                <input
                  type="number" step="5" min="0" max="100"
                  class="ep-input-inline"
                  :value="Number(e.probability_pct)"
                  @blur="updateEffect(e, 'probability_pct', $event)"
                />%
              </td>
              <td>
                <span class="ep-tag" :class="`ep-tag-conf-${e.confidence}`">{{ confidenceLabel(e.confidence) }}</span>
              </td>
              <td><small>{{ e.notes || '—' }}</small></td>
              <td><button class="ep-x" @click="onDeleteEffect(e.id)" title="Удалить">×</button></td>
            </tr>
          </tbody>
        </table>
        <div v-else-if="loading" class="ep-empty">Загрузка…</div>
        <div v-else class="ep-empty">
          В этом срезе ({{ effectYear }} · {{ metricLabel(effectMetric) }}) ещё никто не указал
          эффекты проектов. Заполняется через UI этого раздела или REST API.
        </div>
      </div>
    </template>

    <!-- ═══════════ Sub-section 3: DECOMPOSITION ═══════════ -->
    <template v-if="sub==='decomposition'">
      <div class="ep-help">
        <strong>Что это:</strong> {{ TT.decomposition }}
        <br>
        <strong>Формула:</strong>
        <code>Прогноз = База × Π(1 + Δfactor × β) + Σ эффекты проектов</code>
      </div>

      <div class="ep-filter">
        <label class="ep-field">
          <span class="ep-field-l">Сценарий *</span>
          <select v-model="decScenario" class="ep-input">
            <option v-for="s in scenarios" :key="s.id" :value="s.id">
              {{ s.name_ru || s.code }}
            </option>
          </select>
        </label>
        <label class="ep-field">
          <span class="ep-field-l">Метрика *</span>
          <select v-model="decMetric" class="ep-input">
            <option v-for="m in constants?.target_metrics || []" :key="m.code" :value="m.code">
              {{ m.label_ru }}
            </option>
          </select>
        </label>
        <label class="ep-field">
          <span class="ep-field-l">Год *</span>
          <select v-model="decYear" class="ep-input">
            <option v-for="y in availableYears" :key="y" :value="y">{{ y }}</option>
          </select>
        </label>
        <label class="ep-field">
          <span class="ep-field-l">Компания (опц.)</span>
          <select v-model="decCompany" class="ep-input">
            <option :value="null">Все 22 SOE (агрегат)</option>
            <option v-for="co in companies" :key="co.id" :value="co.id">{{ co.name_ru }}</option>
          </select>
          <span v-if="companiesTruncated" class="ep-trunc">
            Показаны первые {{ companies.length }} — список усечён.
          </span>
        </label>
        <div class="ep-filter-add">
          <button class="ep-btn ep-btn-p" @click="runDecomposition" :disabled="!decScenario || !decMetric || !decYear || loadingDec">
            {{ loadingDec ? 'Считаем…' : '▶ Рассчитать' }}
          </button>
        </div>
      </div>

      <div v-if="decomposition" class="ep-card ep-dec">
        <div class="ep-dec-h">
          <h3>{{ decomposition.company_name || 'Все 22 SOE' }}: {{ metricLabel(decomposition.target_metric) }} → {{ decomposition.year }}</h3>
          <p class="ep-dec-expl">{{ decomposition.explanation }}</p>
        </div>

        <!-- Waterfall -->
        <div class="ep-wf">
          <div v-for="(c, i) in decomposition.components" :key="i"
               class="ep-wf-bar"
               :class="`ep-wf-${c.kind}`"
               :style="{ width: `${Math.max(3, Math.abs(Number(c.contribution_pct)))}%` }">
            <div class="ep-wf-l">{{ c.label_ru }}</div>
            <div class="ep-wf-v">
              {{ Number(c.contribution_uzs_mln) > 0 ? '+' : '' }}{{ formatMln(c.contribution_uzs_mln) }}
              <small>{{ Number(c.contribution_pct).toFixed(1) }}%</small>
            </div>
          </div>
        </div>

        <!-- Summary table -->
        <table class="ep-tbl ep-tbl-tight" style="margin-top: 12px">
          <tbody>
            <tr><td>База ({{ decomposition.year - 1 }})</td><td class="r">{{ formatMln(decomposition.base_value_uzs_mln) }}</td></tr>
            <tr><td>+ Эффект макроэкономики</td><td class="r" :style="{color: macroColor(decomposition.macro_effect_uzs_mln)}">{{ formatMlnSigned(decomposition.macro_effect_uzs_mln) }}</td></tr>
            <tr><td>+ Эффект проектов</td><td class="r" :style="{color: macroColor(decomposition.projects_effect_uzs_mln)}">{{ formatMlnSigned(decomposition.projects_effect_uzs_mln) }}</td></tr>
            <tr class="ep-tot"><td><strong>= Прогноз {{ decomposition.year }}</strong></td><td class="r"><strong>{{ formatMln(decomposition.forecast_value_uzs_mln) }}</strong></td></tr>
          </tbody>
        </table>
      </div>
      <div v-else class="ep-empty">
        Выбери сценарий, метрику и год и нажми «Рассчитать». Если база = 0 — значит для
        этой компании нет финансовых данных за предыдущий год.
      </div>
    </template>

    <!-- ═══════════ MODAL: Add Coefficient ═══════════ -->
    <Teleport to="body">
      <div v-if="modalCoef" class="ep-modal-bg" @click.self="modalCoef=false">
        <div class="ep-modal">
          <h3>Новый коэффициент</h3>
          <div class="ep-modal-grid">
            <label class="ep-field">
              <span class="ep-field-l">Макрофактор *</span>
              <select v-model="newCoef.macro_factor" class="ep-input">
                <option v-for="f in constants?.macro_factors || []" :key="f.code" :value="f.code">
                  {{ f.label_ru }}
                </option>
              </select>
            </label>
            <label class="ep-field">
              <span class="ep-field-l">Влияет на *</span>
              <select v-model="newCoef.target_metric" class="ep-input">
                <option v-for="m in constants?.target_metrics || []" :key="m.code" :value="m.code">
                  {{ m.label_ru }}
                </option>
              </select>
            </label>
            <label class="ep-field">
              <span class="ep-field-l">β *</span>
              <input type="number" step="0.01" v-model.number="newCoef.beta" class="ep-input" placeholder="0.50" />
            </label>
            <label class="ep-field">
              <span class="ep-field-l">Сценарий (опц.)</span>
              <select v-model="newCoef.scenario_id" class="ep-input">
                <option :value="null">— глобально —</option>
                <option v-for="s in scenarios" :key="s.id" :value="s.id">{{ s.name_ru || s.code }}</option>
              </select>
            </label>
            <label class="ep-field">
              <span class="ep-field-l">Компания (опц.)</span>
              <select v-model="newCoef.company_id" class="ep-input">
                <option :value="null">— все компании —</option>
                <option v-for="co in companies" :key="co.id" :value="co.id">{{ co.name_ru }}</option>
              </select>
              <span v-if="companiesTruncated" class="ep-trunc">
                Показаны первые {{ companies.length }} — список усечён.
              </span>
            </label>
            <label class="ep-field ep-field-wide">
              <span class="ep-field-l">Комментарий</span>
              <input type="text" v-model="newCoef.notes" class="ep-input" />
            </label>
          </div>
          <div class="ep-modal-foot">
            <button class="ep-btn" @click="modalCoef=false">Отмена</button>
            <button class="ep-btn ep-btn-p" @click="saveNewCoef" :disabled="!newCoef.macro_factor || !newCoef.target_metric">Сохранить</button>
          </div>
        </div>
      </div>
    </Teleport>

    <!-- ═══════════ MODAL: Add Project Effect ═══════════ -->
    <Teleport to="body">
      <div v-if="modalEffect" class="ep-modal-bg" @click.self="modalEffect=false">
        <div class="ep-modal">
          <h3>Новый эффект проекта</h3>
          <div class="ep-modal-grid">
            <label class="ep-field ep-field-wide">
              <span class="ep-field-l">Проект *</span>
              <select v-model="newEffect.project_id" class="ep-input">
                <option v-for="p in projects" :key="p.id" :value="p.id">
                  {{ p.title }} <small v-if="p.num">({{ p.num }})</small>
                </option>
              </select>
              <span v-if="projectsTruncated" class="ep-trunc">
                Показаны первые {{ projects.length }} проектов — список усечён, часть проектов недоступна в выборе.
              </span>
            </label>
            <label class="ep-field">
              <span class="ep-field-l">Год эффекта *</span>
              <input type="number" v-model.number="newEffect.effective_year" class="ep-input" />
            </label>
            <label class="ep-field">
              <span class="ep-field-l">Метрика *</span>
              <select v-model="newEffect.target_metric" class="ep-input">
                <option v-for="m in constants?.target_metrics || []" :key="m.code" :value="m.code">
                  {{ m.label_ru }}
                </option>
              </select>
            </label>
            <label class="ep-field">
              <span class="ep-field-l">Δ млн сум</span>
              <input type="number" step="100" v-model.number="newEffect.delta_value_uzs_mln" class="ep-input" placeholder="абсолютное значение" />
            </label>
            <label class="ep-field">
              <span class="ep-field-l">Δ %</span>
              <input type="number" step="0.1" v-model.number="newEffect.delta_pct" class="ep-input" placeholder="ИЛИ в процентах" />
            </label>
            <label class="ep-field">
              <span class="ep-field-l">Вероятность %</span>
              <input type="number" min="0" max="100" v-model.number="newEffect.probability_pct" class="ep-input" />
            </label>
            <label class="ep-field">
              <span class="ep-field-l">Уверенность</span>
              <select v-model="newEffect.confidence" class="ep-input">
                <option value="low">low — низкая</option>
                <option value="medium">medium — средняя</option>
                <option value="high">high — высокая</option>
              </select>
            </label>
            <label class="ep-field ep-field-wide">
              <span class="ep-field-l">Комментарий</span>
              <input type="text" v-model="newEffect.notes" class="ep-input" />
            </label>
          </div>
          <div class="ep-modal-foot">
            <button class="ep-btn" @click="modalEffect=false">Отмена</button>
            <button class="ep-btn ep-btn-p" @click="saveNewEffect" :disabled="!newEffect.project_id || !newEffect.target_metric">Сохранить</button>
          </div>
        </div>
      </div>
    </Teleport>

  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, reactive, watch } from "vue"
import * as api from "@/api/elasticity"
import { getAuthHeaders } from "@/api/_base"
import { useConfirm } from "@/composables/useConfirm"

const { confirmDialog } = useConfirm()

// ─── State ───
const sub = ref<"elasticity" | "projects" | "decomposition">("elasticity")
const loading = ref(false)
const loadingDec = ref(false)
const error = ref<string | null>(null)

const constants = ref<api.Constants | null>(null)
const scenarios = ref<Array<{ id: string; name_ru?: string; code: string }>>([])
const companies = ref<Array<{ id: string; name_ru: string }>>([])
const companiesTruncated = ref(false)
const projects = ref<Array<{ id: string; title: string; num?: string }>>([])
const projectsTruncated = ref(false)
const coefs = ref<api.ElasticityCoef[]>([])
const effects = ref<api.ProjectEffect[]>([])
const decomposition = ref<api.DecompositionResult | null>(null)

// ─── Filters ───
const filterScenario = ref<string | null>(null)
const filterMetric = ref<string | null>(null)
const effectYear = ref(new Date().getFullYear())
const effectMetric = ref<api.TargetMetric>("revenue")
const decScenario = ref<string | null>(null)
const decMetric = ref<api.TargetMetric>("revenue")
const decYear = ref(new Date().getFullYear() + 1)
const decCompany = ref<string | null>(null)

const availableYears = computed(() => {
  const y = new Date().getFullYear()
  return [y - 1, y, y + 1, y + 2, y + 3, y + 4, y + 5]
})

const filteredCoefs = computed(() => {
  let rows = coefs.value
  if (filterMetric.value) {
    rows = rows.filter((c) => c.target_metric === filterMetric.value)
  }
  return rows
})

// ─── Modals ───
const modalCoef = ref(false)
const newCoef = reactive<api.ElasticityUpsert>({
  scenario_id: null, company_id: null,
  macro_factor: "inflation_pct", target_metric: "revenue",
  beta: 0.5, notes: "",
})

const modalEffect = ref(false)
const newEffect = reactive<api.ProjectEffectUpsert>({
  project_id: "", effective_year: new Date().getFullYear() + 1,
  target_metric: "revenue", delta_value_uzs_mln: null, delta_pct: null,
  probability_pct: 100, confidence: "medium", notes: "",
})

function openAddCoef() {
  newCoef.scenario_id = filterScenario.value
  modalCoef.value = true
}
function openAddEffect() {
  newEffect.effective_year = effectYear.value
  newEffect.target_metric = effectMetric.value
  modalEffect.value = true
}

// ─── Loaders ───
async function loadConstants() {
  try { constants.value = await api.getConstants() } catch (e: any) { error.value = e.message }
}

async function loadScenarios() {
  try {
    const res = await fetch("/api/scenarios", { headers: getAuthHeaders() })
    if (res.ok) scenarios.value = await res.json()
  } catch (e) { /* ignore */ }
}

async function loadCompanies() {
  try {
    const res = await fetch("/api/companies?limit=200", { headers: getAuthHeaders() })
    if (res.ok) {
      const data = await res.json()
      const items = Array.isArray(data) ? data : (data.items || [])
      companies.value = items
      const total = Array.isArray(data) ? items.length : Number(data.total ?? items.length)
      companiesTruncated.value = total > items.length
    }
  } catch (e) { /* ignore */ }
}

async function loadProjects() {
  try {
    const res = await fetch("/api/projects?limit=500", { headers: getAuthHeaders() })
    if (res.ok) {
      const data = await res.json()
      const items = Array.isArray(data) ? data : (data.items || [])
      projects.value = items
      const total = Array.isArray(data) ? items.length : Number(data.total ?? items.length)
      projectsTruncated.value = total > items.length
    }
  } catch (e) { /* ignore */ }
}

async function loadCoefs() {
  try {
    coefs.value = await api.listCoefficients({
      scenario_id: filterScenario.value || undefined,
      include_global: true,
    })
  } catch (e: any) {
    error.value = e.message
  }
}

async function loadEffects() {
  try {
    effects.value = await api.listProjectEffects({
      effective_year: effectYear.value,
      target_metric: effectMetric.value,
    })
  } catch (e: any) {
    error.value = e.message
  }
}

async function loadAll() {
  loading.value = true
  error.value = null
  try {
    await Promise.all([loadConstants(), loadScenarios(), loadCompanies(), loadProjects()])
    await Promise.all([loadCoefs(), loadEffects()])
  } finally {
    loading.value = false
  }
}

watch([filterScenario, filterMetric], () => loadCoefs())
watch([effectYear, effectMetric], () => loadEffects())

// ─── Save handlers ───
async function updateBeta(c: api.ElasticityCoef, ev: Event) {
  const v = parseFloat((ev.target as HTMLInputElement).value)
  if (isNaN(v) || v === Number(c.beta)) return
  await api.upsertCoefficient({
    scenario_id: c.scenario_id, company_id: c.company_id,
    macro_factor: c.macro_factor, target_metric: c.target_metric,
    beta: v, notes: c.notes,
  })
  await loadCoefs()
}

async function onDeleteCoef(id: string) {
  if (!(await confirmDialog({ message: "Удалить коэффициент?", danger: true }))) return
  await api.deleteCoefficient(id)
  await loadCoefs()
}

async function saveNewCoef() {
  try {
    await api.upsertCoefficient({ ...newCoef })
    modalCoef.value = false
    await loadCoefs()
  } catch (e: any) {
    error.value = e.message
  }
}

async function updateEffect(e: api.ProjectEffect, field: string, ev: Event) {
  const raw = (ev.target as HTMLInputElement).value
  const v = raw === "" ? null : parseFloat(raw)
  if (raw !== "" && isNaN(v as number)) return
  const cur = (e as any)[field]
  if (cur === v) return
  try {
    await api.upsertProjectEffect({
      project_id: e.project_id,
      effective_year: e.effective_year,
      target_metric: e.target_metric,
      delta_value_uzs_mln: field === "delta_value_uzs_mln" ? v : (e.delta_value_uzs_mln != null ? Number(e.delta_value_uzs_mln) : null),
      delta_pct: field === "delta_pct" ? v : (e.delta_pct != null ? Number(e.delta_pct) : null),
      probability_pct: field === "probability_pct" ? (v as number) : Number(e.probability_pct),
      confidence: e.confidence,
      notes: e.notes,
    })
    await loadEffects()
  } catch (err: any) {
    error.value = err.message
  }
}

async function onDeleteEffect(id: string) {
  if (!(await confirmDialog({ message: "Удалить эффект?", danger: true }))) return
  await api.deleteProjectEffect(id)
  await loadEffects()
}

async function saveNewEffect() {
  if (newEffect.delta_value_uzs_mln == null && newEffect.delta_pct == null) {
    error.value = "Укажите либо Δ млн сум, либо Δ %"
    return
  }
  try {
    await api.upsertProjectEffect({ ...newEffect })
    modalEffect.value = false
    await loadEffects()
  } catch (e: any) {
    error.value = e.message
  }
}

// ─── Decomposition ───
async function runDecomposition() {
  if (!decScenario.value) return
  loadingDec.value = true
  error.value = null
  try {
    decomposition.value = await api.getDecomposition({
      scenario_id: decScenario.value,
      target_metric: decMetric.value,
      target_year: decYear.value,
      company_id: decCompany.value || undefined,
    })
  } catch (e: any) {
    error.value = e.message
    decomposition.value = null
  } finally {
    loadingDec.value = false
  }
}

// ─── Helpers / labels ───
function macroLabel(code: string) {
  return constants.value?.macro_factors.find((f) => f.code === code)?.label_ru || code
}
function metricLabel(code: string) {
  return constants.value?.target_metrics.find((m) => m.code === code)?.label_ru || code
}
function scopeKind(c: api.ElasticityCoef): string {
  if (c.scenario_id && c.company_id) return "specific"
  if (c.scenario_id) return "scenario"
  if (c.company_id) return "company"
  return "global"
}
function scopeLabel(c: api.ElasticityCoef): string {
  if (c.scenario_id && c.company_id) return "сценарий + компания"
  if (c.scenario_id) return "сценарий"
  if (c.company_id) return "компания"
  return "глобально"
}
function sourceLabel(s: string): string {
  if (s === "seed_sector_default") return "дефолт"
  if (s === "manual") return "вручную"
  if (s === "imported") return "импорт"
  return s
}
function confidenceLabel(c: string): string {
  return { low: "low", medium: "medium", high: "high" }[c] || c
}
function betaColor(beta: number | string): string {
  const n = Number(beta)
  if (isNaN(n) || n === 0) return "#888780"
  if (Math.abs(n) >= 0.7) return n > 0 ? "#0F6E56" : "#A32D2D"
  if (Math.abs(n) >= 0.3) return n > 0 ? "#1D9E75" : "#E24B4A"
  return "#888780"
}
function macroColor(v: number | string): string {
  const n = Number(v)
  if (isNaN(n) || n === 0) return "#5F5E5A"
  return n > 0 ? "#0F6E56" : "#A32D2D"
}
function formatMln(v: number | string): string {
  const n = Number(v)
  if (isNaN(n)) return "—"
  const abs = Math.abs(n)
  if (abs >= 1e6) return `${(n / 1e6).toFixed(2)} трлн сум`
  if (abs >= 1e3) return `${(n / 1e3).toFixed(1)} млрд сум`
  return `${n.toFixed(0)} млн сум`
}
function formatMlnSigned(v: number | string): string {
  const n = Number(v)
  if (isNaN(n) || n === 0) return "0"
  const s = formatMln(Math.abs(n))
  return n > 0 ? `+${s}` : `−${s}`
}

const TT = {
  intro: "Раздел связывает макроэкономику со сценариями. Состоит из 3 частей: эластичность (как метрики реагируют на макрофакторы), эффекты проектов (что даёт каждый проект в цифрах), декомпозиция (из чего складывается прогноз).",
  elasticity: "Эластичность β — на сколько % изменится метрика (например revenue) при изменении макрофактора (например USD-курс) на 1%. Если β=0.85 — это значит USD вырос на 10% → revenue вырастет на 8.5%.",
  projects: "Финансовые эффекты конкретных проектов трансформации. Команда проекта указывает: проект «X» в 2027 году даст +120 млрд сум к выручке с вероятностью 75%. Программа потом суммирует все такие эффекты в декомпозиции.",
  decomposition: "Раскладывает прогноз на 3 части: База (факт прошлого года) + Эффект макроэкономики (через эластичности) + Эффект проектов (из их финансовых данных). Помогает понять что именно даёт рост.",
  scope: "Иерархия применения коэффициента: специфичный сценарий + компания > сценарий > компания > глобально. Программа берёт самый специфичный из имеющихся.",
}

onMounted(loadAll)
</script>

<style scoped>
.ep { font-family:-apple-system,BlinkMacSystemFont,"Inter",sans-serif; color: var(--t1, #1E2A4A); padding:4px 0 24px; }

.ep-hdr { display:flex; justify-content:space-between; align-items:flex-end; gap:16px; margin-bottom:14px; }
.ep-hdr-r { flex-shrink:0; }
.ep-eyebrow { font-size:10px; font-weight:500; color: var(--t3, var(--t-muted)); text-transform:uppercase; letter-spacing:.08em; }
.ep-title { font-size:20px; font-weight:500; letter-spacing:-.02em; margin:4px 0; display:flex; align-items:center; gap:8px; }
.ep-sub { font-size:11.5px; color: var(--t3, #5F5E5A); line-height:1.6; margin:0; max-width:760px; }
.ep-sub strong { color: var(--t1, #1E2A4A); font-weight:500; }
.ep-tip { display:inline-flex; align-items:center; justify-content:center; width:14px; height:14px; font-size:9px; font-weight:500; border-radius:50%; background:rgba(127,119,221,.10); color:var(--p-deep); margin-left:3px; cursor:help; }

.ep-err { padding:9px 12px; background:rgba(226,75,74,.08); border:1px solid rgba(226,75,74,.20); color:var(--sev-critical); font-size:11px; border-radius:7px; margin-bottom:10px; }

.ep-subtabs { display:inline-flex; gap:4px; padding:3px; background:rgba(15,23,60,.05); border-radius:9px; margin-bottom:14px; }
.ep-stab { background:transparent; border:none; font-size:11.5px; font-weight:500; color: var(--t3, var(--t-muted)); padding:7px 14px; border-radius:6px; cursor:pointer; font-family:inherit; transition:all .14s; display:flex; align-items:center; gap:5px; }
.ep-stab:hover:not(.on) { color: var(--t1, #1E2A4A); }
.ep-stab.on { background: var(--bg1, #fff); color: var(--t1, #1E2A4A); box-shadow:0 1px 3px rgba(15,23,60,.08); }
.ep-stab small { font-size:9px; padding:1px 5px; background:rgba(127,119,221,.15); color:var(--p-deep); border-radius:3px; }

.ep-help { font-size:11px; color: var(--t3, #5F5E5A); padding:10px 12px 10px 18px; background:rgba(127,119,221,.05); border-radius:5px; margin-bottom:14px; line-height:1.7; position:relative; overflow:hidden; }
.ep-help::before { content:""; position:absolute; left:6px; top:8px; bottom:8px; width:4px; border-radius:4px; background:#7F77DD; }
.ep-help strong { color:var(--p-deep); font-weight:500; }
.ep-help code { background: var(--bg1, #fff); padding:1px 5px; border-radius:3px; font-size:10px; font-family:'SF Mono', Consolas, monospace; color: var(--t1, #1E2A4A); }
.ep-help-row { display:inline-flex; gap:10px; align-items:center; margin-left:8px; }
.ep-help-bullet { font-size:10px; }

.ep-filter { display:flex; gap:10px; flex-wrap:wrap; align-items:flex-end; margin-bottom:10px; padding:10px; background: var(--bg2, #FAFAFC); border-radius:7px; border:1px solid rgba(0,0,0,.05); }
.ep-filter-add { margin-left:auto; }
.ep-field { display:flex; flex-direction:column; gap:3px; }
.ep-field-wide { grid-column:span 2; }
.ep-field-l { font-size:9.5px; color: var(--t3, var(--t-muted)); text-transform:uppercase; letter-spacing:.06em; font-weight:500; }
.ep-trunc { font-size:9.5px; line-height:1.4; color:#854F0B; margin-top:2px; }
.ep-input { font-family:inherit; font-size:11.5px; padding:6px 10px; border:1px solid rgba(0,0,0,.10); border-radius:6px; background: var(--bg1, #fff); color: var(--t1, #1E2A4A); min-width:170px; }
.ep-input:focus { outline:none; border-color:#7F77DD; box-shadow:0 0 0 3px rgba(127,119,221,.10); }
.ep-input-inline { font-family:inherit; font-size:10.5px; padding:3px 6px; border:1px solid rgba(0,0,0,.08); border-radius:4px; background: var(--bg2, #FAFAFC); width:80px; text-align:right; font-feature-settings:"tnum"; font-weight:500; }
.ep-input-inline:focus { outline:none; border-color:#7F77DD; background: var(--bg1, #fff); }

.ep-btn { font-family:inherit; font-size:10.5px; font-weight:500; padding:7px 12px; border-radius:6px; cursor:pointer; border:1px solid rgba(0,0,0,.10); background: var(--bg1, #fff); color: var(--t3, #5F5E5A); }
.ep-btn:hover:not(:disabled) { color: var(--t1, #1E2A4A); border-color:rgba(0,0,0,.20); }
.ep-btn:disabled { opacity:.4; cursor:not-allowed; }
.ep-btn-p { background:#7F77DD; color:#fff; border-color:#7F77DD; }
.ep-btn-p:hover:not(:disabled) { background:var(--p-deep); }
.ep-x { background:transparent; border:none; color:#B4B2A9; font-size:14px; cursor:pointer; padding:0 4px; }
.ep-x:hover { color:var(--sev-high); }

.ep-card { background: var(--card-bg, rgba(255,255,255,0.82)); backdrop-filter: blur(16px) saturate(1.5); -webkit-backdrop-filter: blur(16px) saturate(1.5); border:1px solid var(--card-border, rgba(0,0,0,.06)); border-radius:10px; padding:14px 16px; }
.ep-empty { font-size:11px; color: var(--t3, var(--t-muted)); padding:24px; text-align:center; }
.ep-empty code { background:rgba(127,119,221,.07); padding:1px 5px; border-radius:3px; font-family:'SF Mono', Consolas, monospace; font-size:10px; }

.ep-tbl { width:100%; border-collapse:separate; border-spacing:0; font-size:10.5px; }
.ep-tbl th { font-size:8.5px; font-weight:500; color: var(--t3, var(--t-muted)); text-transform:uppercase; letter-spacing:.06em; padding:8px; text-align:left; border-bottom:1px solid rgba(0,0,0,.06); }
.ep-tbl th.r { text-align:right; }
.ep-tbl td { padding:8px; border-bottom:1px solid rgba(0,0,0,.04); }
.ep-tbl td.r { text-align:right; font-feature-settings:"tnum"; font-weight:500; }
.ep-tbl tr:last-child td { border-bottom:none; }
.ep-tbl code { background:rgba(127,119,221,.07); padding:1px 5px; border-radius:3px; font-size:10px; font-family:'SF Mono', Consolas, monospace; }
.ep-tbl-tight td { padding:6px 8px; }
.ep-tot td { border-top:2px solid #7F77DD; font-size:11.5px; padding-top:8px; }

.ep-scope { display:inline-block; font-size:8.5px; font-weight:500; padding:2px 6px; border-radius:3px; text-transform:uppercase; letter-spacing:.04em; }
.ep-scope-global { background:rgba(136,135,128,.15); color: var(--t3, #5F5E5A); }
.ep-scope-scenario { background:rgba(83,74,183,.10); color:var(--p-deep); }
.ep-scope-company { background:rgba(55,138,221,.10); color:#2563A8; }
.ep-scope-specific { background:rgba(29,158,117,.10); color:#0F6E56; }

.ep-tag { display:inline-block; font-size:8.5px; font-weight:500; padding:2px 6px; border-radius:3px; text-transform:uppercase; letter-spacing:.04em; background:rgba(136,135,128,.15); color: var(--t3, #5F5E5A); }
.ep-tag-manual { background:rgba(83,74,183,.10); color:var(--p-deep); }
.ep-tag-seed_sector_default { background:rgba(136,135,128,.15); color: var(--t3, var(--t-muted)); }
.ep-tag-conf-low { background:rgba(226,75,74,.10); color:var(--sev-critical); }
.ep-tag-conf-medium { background:rgba(239,159,39,.12); color:#854F0B; }
.ep-tag-conf-high { background:rgba(29,158,117,.10); color:#0F6E56; }

/* ─── Decomposition ─── */
.ep-dec { padding:20px; }
.ep-dec-h h3 { font-size:14px; font-weight:500; margin:0 0 4px; color: var(--t1, #1E2A4A); }
.ep-dec-expl { font-size:11px; color: var(--t3, #5F5E5A); line-height:1.6; margin:0 0 14px; }

.ep-wf { display:flex; flex-direction:column; gap:4px; padding:8px 0; }
.ep-wf-bar { padding:6px 10px; border-radius:5px; display:flex; justify-content:space-between; align-items:center; min-width:200px; transition:transform .14s; }
.ep-wf-bar:hover { transform:translateX(2px); }
.ep-wf-base { background:rgba(83,74,183,.12); color:var(--p-deep); }
.ep-wf-macro { background:rgba(239,159,39,.12); color:#854F0B; }
.ep-wf-project { background:rgba(29,158,117,.12); color:#0F6E56; }
.ep-wf-total { background:#7F77DD; color:#fff; padding:8px 12px; font-weight:500; }
.ep-wf-l { font-size:10.5px; font-weight:500; }
.ep-wf-v { font-size:11px; font-feature-settings:"tnum"; }
.ep-wf-v small { font-size:9px; opacity:.7; margin-left:5px; }

/* ─── Modal ─── */
.ep-modal-bg { position:fixed; inset:0; background:rgba(15,18,40,.45); -webkit-backdrop-filter: blur(8px); backdrop-filter:blur(8px); display:flex; align-items:center; justify-content:center; z-index:1000; padding:24px; }
.ep-modal { background: var(--card-bg, rgba(255,255,255,0.86)); border: 1px solid var(--card-border, transparent); border-radius:14px; box-shadow:0 24px 64px rgba(15,23,60,.22); padding:24px; width:100%; max-width:640px; }
.ep-modal h3 { margin:0 0 16px; font-size:15px; font-weight:500; color: var(--t1, #1E2A4A); }
.ep-modal-grid { display:grid; grid-template-columns:1fr 1fr; gap:12px; }
.ep-modal-foot { display:flex; justify-content:flex-end; gap:8px; margin-top:18px; }
</style>
