<template>
  <div class="bpe-modal-backdrop" @click.self="$emit('close')">
    <div class="bpe-modal">
      <div class="bpe-header">
        <div class="bpe-title">
          <h2>{{ t("Редактор бизнес-плана") }}</h2>
          <div class="bpe-subtitle">
            <span v-if="companies && companies.length > 1" class="bpe-co-switch">
              <select class="bpe-co-select" :value="companyId" @change="onSwitchCompany" :title="t('Переключить компанию')">
                <option v-for="c in companies" :key="c.company_id" :value="c.company_id">{{ resolveCompanyDisplayName(c.company_name_ru, c.company_id) }}</option>
              </select>
              <svg class="bpe-co-caret" width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"><polyline points="6 9 12 15 18 9"/></svg>
            </span>
            <span v-else>{{ companyName }}</span>
            <span class="bpe-fy"> · FY {{ year }}</span>
          </div>
        </div>
        <button class="bpe-close" @click="$emit('close')" :title="t('Закрыть')">×</button>
      </div>

      <!-- Period tabs + view-mode toggle (all / expenses-only) -->
      <div class="bpe-controls">
        <div class="bpe-tabs">
          <button
            v-for="p in BP_PERIODS"
            :key="p.key"
            class="bpe-tab"
            :class="{ on: activePeriod === p.key }"
            @click="activePeriod = p.key"
          >
            {{ t(p.label) }}
          </button>
        </div>
        <div class="bpe-view-toggle">
          <button
            class="bpe-view-btn bpe-view-btn-inc"
            :class="{ on: viewMode === 'income' }"
            @click="viewMode = 'income'"
            :title="t('Только доходные статьи (revenue, finIncome + subs)')"
          >
            {{ t("Доходы") }}
            <span class="bpe-view-cnt">{{ incomeCount }}</span>
          </button>
          <button
            class="bpe-view-btn bpe-view-btn-exp"
            :class="{ on: viewMode === 'expenses' }"
            @click="viewMode = 'expenses'"
            :title="t('Только расходные статьи (cogs, opExpenses, finCost, tax + sub-items)')"
          >
            {{ t("Расходы") }}
            <span class="bpe-view-cnt">{{ expensesCount }}</span>
          </button>
        </div>
        <button v-if="perm.canEdit" class="bpe-draft-btn" :disabled="draftLoading" @click="openDraft"
                :title="t('Черновик плана из истории фактов (CAGR/OLS + историческая сезонность). Заполняет только пустые ячейки плана; ничего не сохраняет сам.')">
          <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M3 3v18h18"/><path d="M7 14l3-3 3 3 5-6"/></svg>
          {{ draftLoading ? t("Расчёт…") : t("Рассчитать план") }}
        </button>
      </div>

      <!-- Subset summary — visible when viewMode != 'all' -->
      <div v-if="viewMode !== 'all'" class="bpe-summary" :class="`bpe-summary-${viewMode}`">
        <div class="bpe-summary-row">
          <div class="bpe-summary-cell">
            <div class="bpe-summary-l">{{ t("Сумма (план)") }}</div>
            <div class="bpe-summary-v">{{ fmtSummary(subsetTotals.plan) }}</div>
          </div>
          <div class="bpe-summary-cell">
            <div class="bpe-summary-l">{{ t("Сумма (факт)") }}</div>
            <div class="bpe-summary-v">{{ fmtSummary(subsetTotals.fact) }}</div>
          </div>
          <div class="bpe-summary-cell">
            <div class="bpe-summary-l">{{ t("Δ план→факт") }}</div>
            <div class="bpe-summary-v" :class="deltaClass(subsetTotals.delta)">
              {{ subsetTotals.delta != null ? (subsetTotals.delta >= 0 ? '+' : '') + fmtSummary(subsetTotals.delta) : '—' }}
            </div>
          </div>
          <div class="bpe-summary-cell">
            <div class="bpe-summary-l">{{ t("% выручки") }}</div>
            <div class="bpe-summary-v">
              {{ subsetTotals.pctOfRevenue != null ? subsetTotals.pctOfRevenue.toFixed(1) + '%' : '—' }}
            </div>
          </div>
        </div>
      </div>

      <div v-if="error" class="bpe-error">
        <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="9"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg>
        <span>{{ error }}</span>
        <button v-if="loadFailed" class="bpe-error-retry" @click="load">{{ t("Повторить") }}</button>
      </div>

      <div class="bpe-body" :data-readonly="!perm.canEdit">
        <table class="bpe-tbl">
          <thead>
            <tr>
              <th class="lbl">{{ t("Показатель") }}</th>
              <th>{{ t("План") }}</th>
              <th>{{ t("Прогноз") }}</th>
              <th>{{ t("Факт") }}</th>
            </tr>
          </thead>
          <tbody>
            <tr
              v-for="f in displayedFields"
              :key="f.key"
              :class="{ 'is-sub': f.sub, 'is-auto': f.auto && !f.overridable, 'is-final': f.overridable, 'is-key': isKeyMetric(f.key), 'is-expense': f.positive }"
            >
              <td class="lbl">
                <span v-if="f.auto && !f.overridable" class="bpe-auto-tag" :title="t('Рассчитывается автоматически: {formula}', { formula: f.formula || '' })">{{ t("∑ расчёт") }}</span>
                <span v-else-if="f.overridable" class="bpe-final-tag" :title="t('Итог по формуле ({formula}), но можно переопределить вручную по компании. Факт — автоподстановка из НСБУ.', { formula: f.formula || '' })">{{ t("итог · правится") }}</span>
                {{ t(f.label) }}
              </td>
              <td :class="{ 'bpe-pe-cell': canEditRow(f) }">
                <input
                  v-if="canEditRow(f)"
                  v-model.number="data[activePeriod][f.key].plan"
                  type="number"
                  step="0.001"
                  inputmode="decimal"
                  class="bpe-in"
                  :class="{ 'bpe-in-ghost': isOverridable(f.key) && peSuggestion(f.key, 'plan') != null }"
                  :placeholder="isOverridable(f.key) ? peGhost(f.key, 'plan') : '—'"
                  :title="isOverridable(f.key) && peSuggestion(f.key, 'plan') != null ? t('Расчёт по формуле ({formula}): {value}. Введите своё значение, чтобы переопределить.', { formula: f.formula, value: peGhost(f.key, 'plan') }) : ''"
                  @input="markDirty"
                />
                <span v-else class="bpe-auto-val">{{ formatComputed(f.key, "plan") }}</span>
                <button v-if="isOverridable(f.key) && peSuggestion(f.key, 'plan') != null" class="bpe-badge bpe-badge-calc" :title="t('Подставить расчёт: {value}', { value: peGhost(f.key, 'plan') })" @click="applyComputedCol(f.key, 'plan')">{{ t("∑ расчёт") }}</button>
              </td>
              <td :class="{ 'bpe-pe-cell': canEditRow(f) }">
                <input
                  v-if="canEditRow(f)"
                  v-model.number="data[activePeriod][f.key].expect"
                  type="number"
                  step="0.001"
                  inputmode="decimal"
                  class="bpe-in"
                  :class="{ 'bpe-in-ghost': isOverridable(f.key) && peSuggestion(f.key, 'expect') != null }"
                  :placeholder="isOverridable(f.key) ? peGhost(f.key, 'expect') : '—'"
                  :title="isOverridable(f.key) && peSuggestion(f.key, 'expect') != null ? t('Расчёт по формуле ({formula}): {value}. Введите своё значение, чтобы переопределить.', { formula: f.formula, value: peGhost(f.key, 'expect') }) : ''"
                  @input="markDirty"
                />
                <span v-else class="bpe-auto-val">{{ formatComputed(f.key, "expect") }}</span>
                <button v-if="isOverridable(f.key) && peSuggestion(f.key, 'expect') != null" class="bpe-badge bpe-badge-calc" :title="t('Подставить расчёт: {value}', { value: peGhost(f.key, 'expect') })" @click="applyComputedCol(f.key, 'expect')">{{ t("∑ расчёт") }}</button>
              </td>
              <td class="bpe-fact-cell">
                <input
                  v-if="canEditRow(f)"
                  :value="factDisplay(f.key)"
                  type="number"
                  step="0.001"
                  inputmode="decimal"
                  class="bpe-in"
                  :class="{ 'bpe-in-auto': isAutoFact(f.key), 'bpe-in-manual': isManualFact(f.key), 'bpe-in-updated': sourceUpdated(f.key) }"
                  :placeholder="'—'"
                  :title="isAutoFact(f.key) ? t('Автоподстановка ({src}): {value}. Введите своё значение, чтобы переопределить.', { src: sourceLabel(f.key), value: autoFact(f.key) }) : (sourceUpdated(f.key) ? t('Источник обновился: {value} ({src}). Введено вручную: {manual}.', { value: autoFact(f.key), src: sourceLabel(f.key), manual: data[activePeriod][f.key].fact }) : '')"
                  @input="onFactInput(f.key, $event)"
                />
                <span v-else class="bpe-auto-val">{{ formatComputed(f.key, "fact") }}</span>
                <!-- per-cell метка источника/ручного ввода + кнопка применить обновление -->
                <span v-if="canEditRow(f) && isAutoFact(f.key)" class="bpe-badge bpe-badge-auto" :title="t('Автоподстановка из {src}', { src: sourceLabel(f.key) })">
                  <svg width="7" height="7" viewBox="0 0 10 10" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M1.5 5l2.5 2.5L8.5 2.5"/></svg>
                  {{ t("авто") }} · {{ t(sourceLabel(f.key)) }}
                </span>
                <span v-else-if="canEditRow(f) && isManualFact(f.key)" class="bpe-badge bpe-badge-manual" :title="t('Введено вручную')">{{ t("✎ вручную") }}</span>
                <button v-if="canEditRow(f) && sourceUpdated(f.key)" class="bpe-badge bpe-badge-upd" :title="t('Применить значение источника ({src}): {value}', { src: sourceLabel(f.key), value: autoFact(f.key) })" @click="applyAuto(f.key)">{{ t("↻ обновить") }}</button>
              </td>
            </tr>
          </tbody>
        </table>
      </div>

      <!-- Превью черновика плана (генератор) — внутренний оверлей редактора -->
      <div v-if="draftOpen && draft" class="bpe-draft-back" @click.self="draftOpen = false">
        <div class="bpe-draft">
          <div class="bpe-draft-hd">
            <div>
              <h3>{{ t("Черновик плана") }} · FY {{ year }}</h3>
              <div class="bpe-draft-sub">
                {{ t("Из истории {years} · движок CAGR/OLS + историческая сезонность · применяется только в", { years: draft.base_years.join(", ") }) }}
                <b>{{ t("пустые") }}</b> {{ t("ячейки плана · ничего не сохраняется до «Сохранить все периоды»") }}
              </div>
            </div>
            <button class="bpe-close" @click="draftOpen = false" :title="t('Закрыть')">×</button>
          </div>
          <div class="bpe-draft-body">
            <table class="bpe-draft-tbl">
              <thead>
                <tr><th class="lbl">{{ t("Показатель") }}</th><th>{{ t("Год (план)") }}</th><th>{{ t("Коридор") }}</th><th>Q1</th><th>Q2</th><th>Q3</th><th>Q4</th><th>{{ t("Метод") }}</th></tr>
              </thead>
              <tbody>
                <tr v-for="m in draft.metrics" :key="m.key" :class="{ 'is-empty': m.annual == null }">
                  <td class="lbl">
                    {{ t(m.label) }}
                    <span v-if="m.annual != null && draftBusy(m)" class="bpe-badge bpe-badge-manual" :title="t('Годовой план уже введён — черновик его не тронет')">{{ t("занято") }}</span>
                  </td>
                  <template v-if="m.annual != null">
                    <td class="num"><b>{{ m.annual.toLocaleString(getCurrentIntlLocale()) }}</b></td>
                    <td class="num bpe-draft-corr">{{ m.low != null && m.high != null ? m.low.toLocaleString(getCurrentIntlLocale()) + " – " + m.high.toLocaleString(getCurrentIntlLocale()) : "—" }}</td>
                    <template v-if="m.quarters_ytd">
                      <td v-for="(v, i) in m.quarters_ytd" :key="i" class="num">{{ v != null ? v.toLocaleString(getCurrentIntlLocale()) : "—" }}</td>
                    </template>
                    <td v-else colspan="4" class="bpe-draft-noq">{{ t("сезонности нет — только год") }}</td>
                    <td class="bpe-draft-m" :title="m.note">{{ t(DRAFT_METHOD_RU[m.method] || m.method) }} · {{ t(DRAFT_CONF_RU[m.confidence] || m.confidence) }}</td>
                  </template>
                  <template v-else>
                    <td colspan="7" class="bpe-draft-noq">{{ m.note || t("нет данных") }}</td>
                  </template>
                </tr>
              </tbody>
            </table>
          </div>
          <div class="bpe-draft-ft">
            <span class="bpe-draft-cnt">
              {{ draftFillCount > 0 ? t("Заполнит {n} пустых ячеек плана", { n: draftFillCount }) : t("Пустых ячеек плана нет — всё уже введено") }}
            </span>
            <div class="bpe-actions">
              <button class="bpe-btn bpe-btn-ghost" @click="draftOpen = false">{{ t("Отмена") }}</button>
              <button class="bpe-btn bpe-btn-primary" :disabled="!draftFillCount" @click="applyDraft">{{ t("Заполнить пустые планы") }}</button>
            </div>
          </div>
        </div>
      </div>

      <div class="bpe-footer">
        <div class="bpe-status">
          <span v-if="dirty" class="bpe-status-d">{{ t("Несохранённые изменения") }}</span>
          <span v-else-if="lastSaved" class="bpe-status-s">{{ t("Сохранено") }} · {{ lastSaved }}</span>
          <span v-else-if="activePeriod === 'annual' && updatedCount > 0" class="bpe-status-upd">
            ↻ {{ t("Отличается от источника:") }} <strong>{{ updatedCount }}</strong> {{ updatedCount === 1 ? t('ячейка') : t('ячеек') }} — {{ t("«обновить» в ячейке возьмёт значение источника (НСБУ/кварталы)") }}
          </span>
          <span v-else-if="activePeriod === 'annual' && nsbuCount > 0" class="bpe-status-nsbu">
            <svg width="12" height="12" viewBox="0 0 12 12" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><circle cx="6" cy="6" r="5"/><path d="M4 6l1.5 1.5L8.5 4.5"/></svg>
            {{ t("Автоподставлено фактов:") }} <strong>{{ nsbuCount }}</strong> · {{ t("пустой «Факт» берётся из источника, можно переопределить вручную") }}
          </span>
          <span v-else-if="activePeriod === 'annual'" class="bpe-status-h">
            {{ t("Данных источника (НСБУ / закрытые кварталы) за {year} пока нет — ручной ввод", { year }) }}
          </span>
          <span v-else class="bpe-status-h">{{ t("Квартальный период — значения НАРАСТАЮЩИМ ИТОГОМ с начала года (Q1 = 1 кв, Q2 = полугодие, Q3 = 9 мес, Q4 = год)") }}</span>
        </div>
        <div class="bpe-actions">
          <button class="bpe-btn bpe-btn-ghost" @click="$emit('close')">{{ perm.canEdit ? t("Отмена") : t("Закрыть") }}</button>
          <button v-if="perm.canEdit" class="bpe-btn bpe-btn-primary" @click="save" :disabled="saving || !dirty || loadFailed">
            {{ saving ? t("Сохранение...") : t("Сохранить все периоды") }}
          </button>
          <span v-else class="bpe-status-h">{{ t("Только просмотр · нет прав на редактирование") }}</span>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from "vue";
import { useToast } from "@/composables/useToast";
import { useConfirm } from "@/composables/useConfirm";
import { useI18n } from "@/composables/useI18n";
import { getCurrentIntlLocale } from "@/locale/i18n";
import { i18nKey } from "@/locale/keys";
import { resolveCompanyDisplayName } from "@/utils/displayNames";

const toast = useToast();
const { confirmDialog } = useConfirm();
const { t } = useI18n();
import {
  BP_FIELDS,
  BP_PERIODS,
  bpApi,
  bpFieldsFor,
  type AvailableCompany,
  type BpPlanDraft,
  type BpRecordUpsert,
} from "@/api/bpKpi";
import { isModerationQueued } from "@/api/client";
import { usePermissions } from "@/composables/usePermissions";

const perm = usePermissions("bp");

const props = defineProps<{
  companyId: string;
  companyName: string;
  year: number;
  companies?: AvailableCompany[];
}>();

const emit = defineEmits<{
  (e: "close"): void;
  (e: "saved"): void;
  (e: "switch-company", id: string): void;
}>();

// ─── Переключение компании прямо в редакторе (с dirty-guard) ──────
// Смена идёт наверх (родитель зовёт setCompany) → пропсы companyId/year
// обновляются → watcher ниже перезагружает данные редактора.
async function onSwitchCompany(e: Event) {
  const sel = e.target as HTMLSelectElement;
  const id = sel.value;
  if (!id || id === props.companyId) return;
  if (dirty.value) {
    const ok = await confirmDialog({
      message: t("Есть несохранённые изменения. Переключить компанию и потерять их?"),
      danger: true,
    });
    if (!ok) { sel.value = props.companyId; return; }   // откат селекта
  }
  emit("switch-company", id);
}
// Компания/год сменились извне → перезагрузить грид (dirty уже подтверждён выше).
watch(() => [props.companyId, props.year], () => { load(); });

type Cell = { plan: number | null; expect: number | null; fact: number | null };
type Period = "annual" | "q1" | "q2" | "q3" | "q4";

const PERIODS: Period[] = ["annual", "q1", "q2", "q3", "q4"];

const activePeriod = ref<Period>("annual");
const data = ref<Record<Period, Record<string, Cell>>>(makeBlank());
const dirty = ref(false);

// ─── View-mode toggle: all / income (revenue side) / expenses (positive=true)
import type { BpViewMode } from "@/api/bpKpi";
const viewMode = ref<BpViewMode>("income");
const displayedFields = computed(() => bpFieldsFor(viewMode.value));
const expensesCount = computed(() => bpFieldsFor("expenses").length);
const incomeCount = computed(() => bpFieldsFor("income").length);

// ─── Subset summary (sum plan/fact + delta + % выручки) ────────────
const subsetTotals = computed(() => {
  const periodData = data.value[activePeriod.value];
  let planSum = 0, factSum = 0;
  let hasPlan = false, hasFact = false;
  // Avoid double-counting: skip subs whose parent is also in the subset
  const parentKeys = new Set(
    displayedFields.value.filter(f => !f.sub).map(f => f.key),
  );
  for (const f of displayedFields.value) {
    if (f.auto) continue;
    if (f.sub) continue;  // parent already sums subs in BP semantics
    void parentKeys;
    const cell = periodData?.[f.key];
    if (!cell) continue;
    if (cell.plan != null) { planSum += Number(cell.plan); hasPlan = true; }
    if (cell.fact != null) { factSum += Number(cell.fact); hasFact = true; }
  }
  // % of revenue (always annual revenue context for stable comparison)
  const revCell = data.value[activePeriod.value]?.["revenue"];
  const revFact = revCell?.fact != null ? Number(revCell.fact) : null;
  const revPlan = revCell?.plan != null ? Number(revCell.plan) : null;
  const revBase = revFact != null && revFact !== 0 ? revFact
    : (revPlan != null && revPlan !== 0 ? revPlan : null);
  const dominantSum = hasFact ? factSum : (hasPlan ? planSum : null);
  return {
    plan: hasPlan ? planSum : null,
    fact: hasFact ? factSum : null,
    delta: (hasPlan && hasFact) ? (factSum - planSum) : null,
    pctOfRevenue: (revBase != null && dominantSum != null) ? (dominantSum / revBase) * 100 : null,
  };
});

function fmtSummary(v: number | null): string {
  if (v == null || isNaN(v)) return "—";
  if (v === 0) return "0";
  const abs = Math.abs(v);
  const rounded = abs < 1 ? v.toFixed(2) : Math.round(v).toString();
  return rounded.replace(/\B(?=(\d{3})+(?!\d))/g, " ");
}

function deltaClass(d: number | null): string {
  if (d == null) return "";
  if (viewMode.value === "expenses") {
    // For expenses: positive delta = over-spent (bad); negative = saved (good)
    return d > 0 ? "bpe-delta-bad" : d < 0 ? "bpe-delta-good" : "";
  }
  // For income (and any default): positive = good, negative = bad
  return d > 0 ? "bpe-delta-good" : d < 0 ? "bpe-delta-bad" : "";
}
const saving = ref(false);
const lastSaved = ref<string | null>(null);
const error = ref<string | null>(null);

// Автоподстановка факта (annual): key → значение источника + сам источник.
const nsbuFacts = ref<Record<string, number | null>>({});
const nsbuSource = ref<Record<string, "nsbu" | "ytd">>({});
const loadFailed = ref(false);   // загрузка упала → НЕ давать сохранять (иначе затрём данные)
const editorToken = ref<string | null>(null);   // optimistic-lock: токен состояния (company, year)
const nsbuCount = computed(() =>
  Object.values(nsbuFacts.value).filter(v => v != null).length
);
// 'ytd' = годовой факт из значения Q4 (кварталы хранятся нарастающим итогом,
// q4 = весь год) — НЕ сумма кварталов.
function sourceLabel(k: string): string { return nsbuSource.value[k] === "ytd" ? t("нараст. итог (Q4)") : t("НСБУ"); }
function autoFact(k: string): number | null {
  return activePeriod.value === "annual" ? (nsbuFacts.value[k] ?? null) : null;
}
function storedFact(k: string): number | null {
  const v = data.value[activePeriod.value][k]?.fact;
  return v == null ? null : Number(v);
}
function _eq(a: number | null, b: number | null): boolean {
  return a != null && b != null && Math.abs(a - b) <= 0.0005;
}
// «авто»: ячейка пуста (берётся источник) ИЛИ значение совпадает с источником.
function isAutoFact(k: string): boolean {
  const s = autoFact(k), m = storedFact(k);
  return s != null && (m == null || _eq(m, s));
}
// «вручную»: введено значение, ОТЛИЧНОЕ от источника (реальное переопределение).
// Где источника нет — бейджа нет (обычный ручной ввод, не шумим).
function isManualFact(k: string): boolean {
  const s = autoFact(k), m = storedFact(k);
  return m != null && s != null && !_eq(m, s);
}
// Расхождение с источником → можно «↻ обновить» (взять значение источника).
function sourceUpdated(k: string): boolean { return isManualFact(k); }
// Эффективное отображаемое значение факта: ручное, иначе авто (по умолчанию).
function factDisplay(k: string): number | null {
  const m = storedFact(k);
  return m != null ? m : autoFact(k);
}
function onFactInput(k: string, ev: Event) {
  const raw = (ev.target as HTMLInputElement).value.trim().replace(/\s/g, "").replace(",", ".");
  data.value[activePeriod.value][k].fact = raw === "" ? null : (Number.isFinite(Number(raw)) ? Number(raw) : null);
  markDirty();
}
function applyAuto(k: string) {
  const a = autoFact(k);
  if (a == null) return;
  data.value[activePeriod.value][k].fact = a;   // принять обновлённое значение источника
  markDirty();
}
const updatedCount = computed(() => {
  if (activePeriod.value !== "annual") return 0;
  return BP_FIELDS.filter(f => canEditRow(f) && sourceUpdated(f.key)).length;
});

// ─── Генератор «Рассчитать план»: черновик из истории (движок core/forecast) ──
// Черновик применяется ТОЛЬКО в пустые ячейки плана и ничего не сохраняет сам —
// пользователь проверяет и жмёт штатное «Сохранить все периоды».
const draft = ref<BpPlanDraft | null>(null);
const draftOpen = ref(false);
const draftLoading = ref(false);
const QK: Period[] = ["q1", "q2", "q3", "q4"];
const DRAFT_METHOD_RU: Record<string, string> = { cagr: "CAGR", ols: i18nKey("OLS-тренд"), none: "—" };
const DRAFT_CONF_RU: Record<string, string> = { high: i18nKey("высокая"), medium: i18nKey("средняя"), low: i18nKey("низкая"), none: "—" };

async function openDraft() {
  if (draftLoading.value) return;
  draftLoading.value = true;
  try {
    draft.value = await bpApi.getPlanDraft(props.companyId, props.year);
    draftOpen.value = true;
  } catch (e: any) {
    const reason = e?.response?.data?.detail || e?.message || t("неизвестная ошибка");
    toast.error(t("Не удалось построить черновик плана: {reason}", { reason }));
  } finally {
    draftLoading.value = false;
  }
}
/** Сколько ПУСТЫХ ячеек плана заполнит черновик (занятые не трогаем). */
const draftFillCount = computed(() => {
  let n = 0;
  for (const m of draft.value?.metrics || []) {
    if (m.annual != null && data.value.annual[m.key]?.plan == null) n++;
    m.quarters_ytd?.forEach((v, i) => {
      if (v != null && data.value[QK[i]][m.key]?.plan == null) n++;
    });
  }
  return n;
});
function draftBusy(m: { key: string }): boolean {
  return data.value.annual[m.key]?.plan != null;
}
function applyDraft() {
  const d = draft.value;
  if (!d) return;
  let n = 0;
  for (const m of d.metrics) {
    if (m.annual != null && data.value.annual[m.key]?.plan == null) {
      data.value.annual[m.key].plan = m.annual;
      n++;
    }
    m.quarters_ytd?.forEach((v, i) => {
      if (v != null && data.value[QK[i]][m.key]?.plan == null) {
        data.value[QK[i]][m.key].plan = v;
        n++;
      }
    });
  }
  if (n > 0) markDirty();
  draftOpen.value = false;
  toast.info(n > 0
    ? t("Черновик применён: заполнено {n} ячеек плана — проверьте и сохраните", { n })
    : t("Пустых ячеек плана нет — черновик ничего не менял"));
}

function makeBlank(): Record<Period, Record<string, Cell>> {
  const out = {} as Record<Period, Record<string, Cell>>;
  for (const p of PERIODS) {
    out[p] = {};
    for (const f of BP_FIELDS) out[p][f.key] = { plan: null, expect: null, fact: null };
  }
  return out;
}

function markDirty() {
  dirty.value = true;
  lastSaved.value = null;
}

function isKeyMetric(k: string): boolean {
  return ["revenue", "grossProfit", "opProfit", "pbt", "profit"].includes(k);
}

// Расчётное значение производной метрики по колонке (единый источник для
// read-only авто-строк И для подсказки план/прогноз переопределяемого итога).
function computedNum(key: string, col: "plan" | "expect" | "fact"): number | null {
  const p = activePeriod.value;
  const get = (k: string) => data.value[p][k]?.[col];
  if (key === "grossProfit") {
    const rev = get("revenue"), cogs = get("cogs");
    return (rev != null && cogs != null) ? rev - Math.abs(cogs) : null;
  }
  if (key === "opProfit") return computeOp(col);
  if (key === "hhProfit" || key === "pbt") return computeHh(col);
  if (key === "profit") {
    const pbt = computeHh(col), tax = get("tax");
    return (pbt != null && tax != null) ? pbt - Math.abs(tax) : null;
  }
  return null;
}

function formatComputed(key: string, col: "plan" | "expect" | "fact"): string {
  const v = computedNum(key, col);
  if (v == null) return "—";
  return v.toLocaleString(getCurrentIntlLocale(), { minimumFractionDigits: 0, maximumFractionDigits: 2 });
}

// ─── Переопределяемый итог (чистая прибыль): ручной ввод + подсказки ─────
function isOverridable(k: string): boolean {
  return BP_FIELDS.find(f => f.key === k)?.overridable === true;
}
function canEditRow(f: { auto: boolean; overridable?: boolean }): boolean {
  return !f.auto || f.overridable === true;
}
// Подсказка расчёта (pbt − налог) для план/прогноз — только когда ячейка пуста.
function peSuggestion(key: string, col: "plan" | "expect"): number | null {
  if (!isOverridable(key)) return null;
  if (data.value[activePeriod.value][key]?.[col] != null) return null;  // введено вручную
  return computedNum(key, col);
}
function peGhost(key: string, col: "plan" | "expect"): string {
  const v = peSuggestion(key, col);
  return v == null ? "—" : v.toLocaleString(getCurrentIntlLocale(), { maximumFractionDigits: 2 });
}
function applyComputedCol(key: string, col: "plan" | "expect") {
  const v = computedNum(key, col);
  if (v == null) return;
  data.value[activePeriod.value][key][col] = Number(v.toFixed(3));
  markDirty();
}

function computeOp(col: "plan" | "expect" | "fact"): number | null {
  const p = activePeriod.value;
  const g = (k: string) => data.value[p][k]?.[col];
  const rev = g("revenue"), cogs = g("cogs"), opex = g("opExpenses"), oth = g("otherOpInc");
  if (rev != null && cogs != null && opex != null) {
    return rev - Math.abs(cogs) - Math.abs(opex) + (oth ?? 0);
  }
  return null;
}

function computeHh(col: "plan" | "expect" | "fact"): number | null {
  const p = activePeriod.value;
  const g = (k: string) => data.value[p][k]?.[col];
  const op = computeOp(col);
  if (op == null) return null;
  return op + (g("finIncome") ?? 0) - Math.abs(g("finCost") ?? 0);
}

// Load existing
async function load() {
  error.value = null; loadFailed.value = false;
  try {
    const { data: raw, editorToken: tok } = await bpApi.getRaw(props.companyId, props.year);
    editorToken.value = tok;   // запомним для If-Match при сохранении

    // Build full new state — avoids any nested reactivity edge cases by
    // replacing data.value wholesale (single ref write triggers re-render)
    const next = makeBlank();
    let cellsLoaded = 0;
    for (const p of PERIODS) {
      for (const f of BP_FIELDS) {
        const cell = raw?.[p]?.[f.key];
        if (!cell) continue;
        next[p][f.key] = {
          plan:   cell.plan   != null ? Number(cell.plan)   : null,
          expect: cell.expect != null ? Number(cell.expect) : null,
          fact:   cell.fact   != null ? Number(cell.fact)   : null,
        };
        if (cell.plan != null || cell.expect != null || cell.fact != null) cellsLoaded++;
      }
    }
    data.value = next;
    dirty.value = false;
    console.log(`[BP editor] populated ${cellsLoaded} cells across all periods`);

    // Load NSBU autofill values for annual period — used as placeholder for empty Fact inputs.
    // Backend's getComputed returns fact_auto=true when NSBU value is auto-injected.
    try {
      const annualComputed = await bpApi.getComputed(props.companyId, props.year, "annual");
      const nsbu: Record<string, number | null> = {};
      const src: Record<string, "nsbu" | "ytd"> = {};
      for (const f of BP_FIELDS) {
        const c: any = annualComputed.metrics[f.key];
        // Значение источника приходит ВСЕГДА (а не только для автоподставленных),
        // чтобы отличить «совпадает с источником» от реального ручного переопределения.
        if (c?.fact_source_value != null) {
          nsbu[f.key] = Number(c.fact_source_value);
          src[f.key] = c.fact_source === "ytd" ? "ytd" : "nsbu";
        }
      }
      nsbuFacts.value = nsbu;
      nsbuSource.value = src;
    } catch (e) {
      // Источник недоступен (год не закрыт) — просто без автоподстановки.
      nsbuFacts.value = {}; nsbuSource.value = {};
    }
  } catch (e) {
    console.error("[BP editor] load failed:", e);
    error.value = t("Не удалось загрузить сохранённые данные. Не сохраняйте, чтобы не затереть существующие значения — нажмите «Повторить».");
    loadFailed.value = true;
  }
}
onMounted(load);

async function save() {
  if (saving.value || !dirty.value) return;
  saving.value = true;
  error.value = null;
  try {
    const records: BpRecordUpsert[] = [];
    for (const p of PERIODS) {
      for (const f of BP_FIELDS) {
        if (f.auto && !f.overridable) continue; // skip pure-computed; keep overridable finals (profit)
        const c = data.value[p][f.key];
        // null-guard: пустые ячейки НЕ отправляем — иначе (а) при сбое загрузки
        // пустой грид затёр бы реальные данные; (б) авто-подставленный годовой
        // факт (fact=null) остаётся незаписанным → продолжает тянуться из источника.
        if (c.plan == null && c.expect == null && c.fact == null) continue;
        records.push({
          company_id: props.companyId,
          year: props.year,
          period: p,
          metric: f.key,
          plan: c.plan,
          expect: c.expect,
          fact: c.fact,
        });
      }
    }
    if (!records.length) {
      toast.info(t("Нет данных для сохранения"));
      saving.value = false;
      return;
    }
    const resp = await bpApi.bulkUpsert(records, editorToken.value);
    if (isModerationQueued(resp)) {
      // Gated. Interceptor has shown a toast — just close.
      dirty.value = false;
      emit("close");
    } else {
      // Успех = бэкенд закоммитил запись (API ответил 2xx). Подтверждаем визуально.
      dirty.value = false;
      editorToken.value = (resp as any)?.editorToken ?? null;   // перевыдан — работаем дальше
      lastSaved.value = new Date().toLocaleTimeString(getCurrentIntlLocale(), { hour: "2-digit", minute: "2-digit" });
      const n = (resp as any)?.upserted;
      toast.success(typeof n === "number" ? t("Сохранено · {n} ячеек записано", { n }) : t("Бизнес-план сохранён"));
      emit("saved");
    }
  } catch (e: any) {
    console.error("[BP editor] save failed:", e);
    // 409 EditorConflict — кто-то сохранил параллельно; данные устарели.
    if (e?.response?.status === 409) {
      error.value = t("Кто-то сохранил изменения, пока вы редактировали. Перезагрузите редактор.");
      toast.error(t("Конфликт: данные изменились. Перезагрузите редактор, чтобы не затереть чужие правки."));
      return;
    }
    // Показываем РЕАЛЬНУЮ причину, а не общий текст.
    const reason = e?.response?.data?.detail || e?.message || t("неизвестная ошибка");
    error.value = t("Не сохранено: {reason}", { reason });
    toast.error(t("Бизнес-план не сохранён: {reason}", { reason }));
  } finally {
    saving.value = false;
  }
}
</script>

<style scoped>
.bpe-modal-backdrop {
  position: fixed;
  inset: 0;
  background: rgba(15, 18, 40, .45);
  -webkit-backdrop-filter: blur(8px);
  backdrop-filter: blur(8px);
  z-index: var(--z-overlay, 9000);
  display: flex;
  align-items: center;
  justify-content: center;
  animation: bpeFade .25s ease;
}
@keyframes bpeFade { from { opacity: 0; } to { opacity: 1; } }

.bpe-modal {
  background: var(--bg1, #fff);
  border-radius: 14px;
  width: min(960px, 95vw);
  max-height: 90dvh;
  display: flex;
  flex-direction: column;
  box-shadow: 0 24px 64px rgba(15, 23, 60, .18);
  animation: bpeModalIn .35s var(--ease-standard);
  position: relative;   /* якорь для внутреннего оверлея черновика плана */
}
@keyframes bpeModalIn { from { opacity: 0; transform: scale(.96) translateY(8px); } to { opacity: 1; transform: scale(1) translateY(0); } }

.bpe-header {
  padding: 18px 22px 14px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  border-bottom: 1px solid rgba(15, 23, 60, .06);
}
.bpe-title h2 { font-size: 15px; font-weight: 600; margin: 0; color: var(--t1, #1e2a4a); }
.bpe-subtitle { font-size: 11px; color: rgba(15, 23, 60, .55); margin-top: 2px; display: flex; align-items: center; gap: 2px; }
/* Инлайн-переключатель компании прямо в шапке редактора */
.bpe-co-switch { position: relative; display: inline-flex; align-items: center; }
.bpe-co-select {
  appearance: none; -webkit-appearance: none; -moz-appearance: none;
  font: inherit; font-size: 11px; font-weight: 600;
  color: var(--p-deep, #534AB7);
  background: rgba(127, 119, 221, .08);
  border: 1px solid rgba(127, 119, 221, .20);
  border-radius: 6px; padding: 2px 20px 2px 8px; cursor: pointer;
  max-width: 340px; text-overflow: ellipsis;
  transition: background .15s, border-color .15s;
}
.bpe-co-select:hover { background: rgba(127, 119, 221, .14); border-color: rgba(127, 119, 221, .38); }
.bpe-co-select:focus { outline: none; border-color: #7F77DD; }
.bpe-co-caret { position: absolute; right: 6px; color: var(--p-deep, #534AB7); pointer-events: none; }
.bpe-fy { white-space: nowrap; }
.bpe-close {
  background: transparent;
  border: none;
  font-size: 24px;
  color: rgba(15, 23, 60, .45);
  cursor: pointer;
  padding: 0 8px;
  line-height: 1;
}
.bpe-close:hover { color: var(--t1, #1e2a4a); }

.bpe-controls {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 22px;
  border-bottom: 1px solid rgba(15, 23, 60, .06);
  background: var(--bg2, #FAFAFD);
  gap: 12px;
}
.bpe-tabs {
  display: flex;
  gap: 0;
}
/* View-mode toggle (All / Expenses only) — premium-segmented control */
.bpe-view-toggle {
  display: inline-flex;
  align-items: center;
  gap: 1px;
  padding: 3px;
  background: rgba(127, 119, 221, .06);
  border: 0.5px solid rgba(127, 119, 221, .15);
  border-radius: 7px;
  margin: 6px 0;
}
.bpe-view-btn {
  background: transparent;
  border: none;
  cursor: pointer;
  font-family: inherit;
  font-size: 10.5px;
  font-weight: 500;
  letter-spacing: .01em;
  color: var(--t3, var(--t-muted));
  padding: 4px 10px;
  border-radius: 5px;
  display: inline-flex;
  align-items: center;
  gap: 5px;
  transition: background .15s, color .15s, box-shadow .15s;
  white-space: nowrap;
}
.bpe-view-btn:hover { color: var(--p-deep); }
.bpe-view-btn.on {
  background: var(--bg1, #fff);
  color: var(--p-deep);
  box-shadow: 0 1px 3px rgba(15, 23, 60, .08);
}
.bpe-view-btn-inc.on   { color: #0F6E56; }
.bpe-view-btn-exp.on   { color: #B86A0E; }
.bpe-view-cnt {
  background: rgba(127, 119, 221, .15);
  color: var(--p-deep);
  padding: 0 6px;
  border-radius: 7px;
  font-size: 9.5px;
  font-weight: 500;
  font-variant-numeric: tabular-nums;
}
.bpe-view-btn.on .bpe-view-cnt {
  background: rgba(127, 119, 221, .22);
}
.bpe-view-btn-inc.on .bpe-view-cnt { background: rgba(29, 158, 117, .18); color: #0F6E56; }
.bpe-view-btn-exp.on .bpe-view-cnt { background: rgba(239, 159, 39, .18); color: #B86A0E; }
/* Expense-row premium highlight (in expenses-only mode) */
.bpe-tbl tbody tr.is-expense {
  animation: bpeRowFadeIn .4s var(--ease-standard) backwards;
}
.bpe-tbl tbody tr.is-expense:not(.is-sub) td.lbl {
  position: relative;
}
.bpe-tbl tbody tr.is-expense:not(.is-sub) td.lbl::before {
  content: "";
  position: absolute;
  top: 8px; bottom: 8px; left: 2px;
  width: 2px;
  background: linear-gradient(180deg, var(--amber), transparent);
  border-radius: 1px;
}
@keyframes bpeRowFadeIn {
  from { opacity: 0; transform: translateY(4px); }
  to   { opacity: 1; transform: translateY(0); }
}

/* ─── Subset summary banner ─── */
.bpe-summary {
  padding: 12px 22px;
  background: linear-gradient(180deg, rgba(127, 119, 221, .04), rgba(127, 119, 221, .01));
  border-bottom: 1px solid rgba(15, 23, 60, .06);
  animation: bpeSummaryIn .4s var(--ease-standard) both;
  position: relative;
  overflow: hidden;
}
.bpe-summary::before {
  content: "";
  position: absolute;
  top: 0; left: 0; right: 0;
  height: 2px;
  background: var(--bpe-sum-accent, #7F77DD);
  transform-origin: left center;
  animation:
    uzaStripeDrawIn .8s var(--ease-standard) 100ms both,
    uzaStripeBreathe 2.8s ease-in-out 1s infinite;
  pointer-events: none;
}
.bpe-summary-income   { --bpe-sum-accent: var(--green); }
.bpe-summary-expenses { --bpe-sum-accent: var(--amber); }
.bpe-summary-row {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 14px;
}
.bpe-summary-cell {
  min-width: 0;
}
.bpe-summary-l {
  font-size: 9.5px;
  font-weight: 500;
  color: rgba(15, 23, 60, .55);
  text-transform: uppercase;
  letter-spacing: .06em;
}
.bpe-summary-v {
  font-size: 18px;
  font-weight: 400;
  color: var(--t1, #1E2A4A);
  letter-spacing: -.025em;
  margin-top: 3px;
  font-variant-numeric: tabular-nums;
}
.bpe-delta-good { color: #0F6E56; }
.bpe-delta-bad  { color: var(--sev-critical); }

@keyframes bpeSummaryIn {
  from { opacity: 0; transform: translateY(-4px); }
  to   { opacity: 1; transform: translateY(0); }
}
.bpe-tab {
  background: transparent;
  border: none;
  padding: 10px 18px;
  font-size: 11.5px;
  font-weight: 500;
  color: rgba(15, 23, 60, .55);
  cursor: pointer;
  position: relative;
}
.bpe-tab.on {
  color: #7F77DD;
  font-weight: 600;
}
.bpe-tab.on::after {
  content: "";
  position: absolute;
  bottom: -1px;
  left: 0; right: 0;
  height: 2px;
  background: #7F77DD;
}

.bpe-body {
  overflow-y: auto;
  padding: 14px 22px 18px;
  flex: 1;
}

.bpe-tbl {
  width: 100%;
  border-collapse: collapse;
  font-variant-numeric: tabular-nums;
  font-size: 11.5px;
}

.bpe-tbl th {
  font-size: 9.5px;
  font-weight: 600;
  letter-spacing: .04em;
  text-transform: uppercase;
  color: rgba(15, 23, 60, .5);
  text-align: right;
  padding: 6px 8px;
  border-bottom: 1px solid rgba(15, 23, 60, .08);
  position: sticky;
  top: 0;
  background: var(--bg1, #fff);
  z-index: 1;
}
.bpe-tbl th.lbl { text-align: left; padding-left: 0; min-width: 280px; }

.bpe-tbl td {
  padding: 5px 8px;
  border-bottom: 1px solid rgba(15, 23, 60, .04);
  text-align: right;
}
.bpe-tbl td.lbl { text-align: left; padding-left: 0; font-weight: 500; color: var(--t1, #1e2a4a); }
.bpe-tbl tr.is-sub td.lbl { padding-left: 14px; color: rgba(15, 23, 60, .65); }
.bpe-tbl tr.is-key { background: rgba(127, 119, 221, .04); }
.bpe-tbl tr.is-key td.lbl { font-weight: 600; }
.bpe-tbl tr.is-auto td.lbl { font-style: italic; color: rgba(15, 23, 60, .55); }

.bpe-in {
  width: 100px;
  text-align: right;
  border: 1px solid transparent;
  border-radius: 4px;
  padding: 3px 6px;
  font: inherit;
  font-variant-numeric: tabular-nums;
  background: transparent;
  outline: none;
  transition: border-color .15s, background .15s;
}
.bpe-in:hover { border-color: rgba(127, 119, 221, .25); }
.bpe-in:focus { border-color: #7F77DD; background: rgba(127, 119, 221, .04); }

.bpe-auto-val {
  display: inline-block;
  width: 100px;
  text-align: right;
  font-style: italic;
  color: rgba(15, 23, 60, .55);
  padding: 3px 6px;
}

.bpe-footer {
  padding: 12px 22px 16px;
  border-top: 1px solid rgba(15, 23, 60, .06);
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
}
.bpe-status { font-size: 11px; }
.bpe-status-d { color: var(--amber); font-weight: 600; }
.bpe-status-s { color: var(--green); }
.bpe-status-h { color: rgba(15, 23, 60, .5); }

.bpe-actions { display: flex; gap: 8px; }
.bpe-btn {
  padding: 7px 16px;
  border-radius: 6px;
  font-size: 11.5px;
  font-weight: 600;
  border: none;
  cursor: pointer;
  font-family: inherit;
}
.bpe-btn-ghost {
  background: transparent;
  border: 1px solid rgba(15, 23, 60, .15);
  color: rgba(15, 23, 60, .65);
}
.bpe-btn-ghost:hover { background: rgba(127, 119, 221, .05); border-color: #7F77DD; color: #7F77DD; }
.bpe-btn-primary { background: #7F77DD; color: #fff; }
.bpe-btn-primary:hover:not(:disabled) { background: #6B62D6; }
.bpe-btn-primary:disabled { opacity: .5; cursor: not-allowed; }

/* ─── Pack 8.2: NSBU autofill + ∑ расчёт badges ─────── */
/* Метки факта — ПОД полем (не оверлеем число, иначе обрезалось). */
.bpe-fact-cell { position: relative; }
.bpe-fact-cell .bpe-in { width: 100%; box-sizing: border-box; }
/* спиннеры number-инпута съедали ширину и резали цифры — убираем */
.bpe-in::-webkit-outer-spin-button,
.bpe-in::-webkit-inner-spin-button { -webkit-appearance: none; margin: 0; }
.bpe-in[type="number"] { -moz-appearance: textfield; appearance: textfield; }
.bpe-badge {
  display: inline-flex; align-items: center; gap: 2px;
  margin: 3px 4px 0 0;
  padding: 1px 5px; border-radius: 4px; line-height: 1.4;
  font-size: 8px; font-weight: 700; letter-spacing: .03em; text-transform: uppercase;
}
.bpe-badge-auto { background: rgba(29,158,117,.10); color: #0F6E56; border: 1px solid rgba(29,158,117,.25); }
.bpe-badge-manual { background: rgba(99,102,180,.10); color: #534AB7; border: 1px solid rgba(99,102,180,.22); }
.bpe-badge-upd { background: #EF9F27; color: #fff; border: none; cursor: pointer; }
.bpe-badge-upd:hover { background: #d98e1c; }
/* ─── Переопределяемый итог (чистая прибыль): ручной ввод + подсказка расчёта ─ */
.bpe-tbl tbody tr.is-final td.lbl { font-weight: 600; }
.bpe-final-tag {
  display: inline-block; margin-right: 5px; padding: 2px 5px;
  background: rgba(127, 119, 221, .12); color: #534AB7; border-radius: 3px;
  font-size: 8.5px; font-weight: 600; letter-spacing: .04em; text-transform: uppercase;
  vertical-align: 1px; cursor: help;
}
.bpe-pe-cell { position: relative; }
.bpe-in-ghost { border-color: rgba(127, 119, 221, .28); }
.bpe-in-ghost::placeholder { color: rgba(83, 74, 183, .55); font-style: italic; }
.bpe-badge-calc { background: rgba(127, 119, 221, .10); color: #534AB7; border: 1px solid rgba(127, 119, 221, .25); cursor: pointer; }
.bpe-badge-calc:hover { background: rgba(127, 119, 221, .18); }
.bpe-in-auto { background: rgba(29,158,117,.05) !important; border-color: rgba(29,158,117,.28) !important; color: #0F6E56; font-style: italic; }
.bpe-in-manual { font-weight: 600; }
.bpe-in-updated { background: rgba(239,159,39,.07) !important; border-color: rgba(239,159,39,.45) !important; box-shadow: inset 0 0 0 1px rgba(239,159,39,.25); }
.bpe-status-upd { display: inline-flex; align-items: center; gap: 6px; color: #A36500; font-size: 11px; font-weight: 600; }
.bpe-status-upd strong { color: #A36500; }
.bpe-error { display: flex; align-items: center; gap: 9px; margin: 0 0 10px; padding: 10px 14px; background: rgba(226,75,74,.08); border: 1px solid rgba(226,75,74,.28); border-radius: 10px; color: #C5352F; font-size: 12.5px; }
.bpe-error-retry { margin-left: auto; border: 1px solid rgba(226,75,74,.4); background: #fff; color: #C5352F; font: 600 12px inherit; border-radius: 7px; padding: 5px 13px; cursor: pointer; flex-shrink: 0; }
.bpe-error-retry:hover { background: rgba(226,75,74,.06); }

.bpe-auto-tag {
  display: inline-block;
  margin-right: 5px;
  padding: 2px 5px;
  background: rgba(239, 159, 39, .12);
  color: #A36500;
  border-radius: 3px;
  font-size: 8.5px;
  font-weight: 600;
  letter-spacing: .04em;
  text-transform: uppercase;
  vertical-align: 1px;
  cursor: help;
}

.bpe-status-nsbu {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  color: #0F6E56;
  font-size: 11px;
}
.bpe-status-nsbu strong {
  color: #0F6E56;
  font-weight: 700;
}

/* ─── Генератор «Рассчитать план» ─────────────────────────────── */
.bpe-draft-btn {
  display: inline-flex; align-items: center; gap: 5px;
  margin: 6px 0; padding: 4px 11px;
  background: rgba(127, 119, 221, .08); border: 1px solid rgba(127, 119, 221, .28);
  border-radius: 7px; color: var(--p-deep, #534AB7);
  font: 600 10.5px/1.4 inherit; font-family: inherit; cursor: pointer; white-space: nowrap;
  transition: background .15s, border-color .15s;
}
.bpe-draft-btn:hover:not(:disabled) { background: rgba(127, 119, 221, .15); border-color: #7F77DD; }
.bpe-draft-btn:disabled { opacity: .55; cursor: default; }
.bpe-draft-back {
  position: absolute; inset: 0; z-index: 5;
  background: rgba(15, 18, 40, .35);
  -webkit-backdrop-filter: blur(4px); backdrop-filter: blur(4px);
  border-radius: 14px; display: flex; align-items: center; justify-content: center;
  animation: bpeFade .2s ease;
}
.bpe-draft {
  background: var(--bg1, #fff); border-radius: 12px; width: min(860px, 94%);
  max-height: 92%; display: flex; flex-direction: column;
  box-shadow: 0 18px 48px rgba(15, 23, 60, .22); animation: bpeModalIn .3s var(--ease-standard);
}
.bpe-draft-hd { display: flex; align-items: flex-start; justify-content: space-between; gap: 12px; padding: 16px 20px 12px; border-bottom: 1px solid rgba(15, 23, 60, .07); }
.bpe-draft-hd h3 { margin: 0; font-size: 14px; font-weight: 600; color: var(--t1, #1e2a4a); }
.bpe-draft-sub { font-size: 10.5px; color: rgba(15, 23, 60, .55); margin-top: 3px; max-width: 640px; }
.bpe-draft-sub b { color: #A36500; }
.bpe-draft-body { overflow-y: auto; padding: 10px 20px; flex: 1; }
.bpe-draft-tbl { width: 100%; border-collapse: collapse; font-size: 11px; font-variant-numeric: tabular-nums; }
.bpe-draft-tbl th { font-size: 9px; font-weight: 600; letter-spacing: .04em; text-transform: uppercase; color: rgba(15, 23, 60, .5); text-align: right; padding: 5px 7px; border-bottom: 1px solid rgba(15, 23, 60, .08); position: sticky; top: 0; background: var(--bg1, #fff); }
.bpe-draft-tbl th.lbl { text-align: left; padding-left: 0; }
.bpe-draft-tbl td { padding: 5px 7px; border-bottom: 1px solid rgba(15, 23, 60, .05); text-align: right; }
.bpe-draft-tbl td.lbl { text-align: left; padding-left: 0; font-weight: 500; color: var(--t1, #1e2a4a); }
.bpe-draft-tbl td.num b { font-weight: 600; color: var(--p-deep, #534AB7); }
.bpe-draft-corr { color: rgba(15, 23, 60, .5); font-size: 10px; white-space: nowrap; }
.bpe-draft-noq { color: rgba(15, 23, 60, .45); font-size: 10.5px; text-align: left !important; font-style: italic; }
.bpe-draft-m { font-size: 9.5px; color: rgba(15, 23, 60, .55); white-space: nowrap; cursor: help; }
.bpe-draft-tbl tr.is-empty td { opacity: .6; }
.bpe-draft-ft { display: flex; align-items: center; justify-content: space-between; gap: 12px; padding: 12px 20px 14px; border-top: 1px solid rgba(15, 23, 60, .07); }
.bpe-draft-cnt { font-size: 11px; color: rgba(15, 23, 60, .6); }

/* Read-only mode for users without bp.edit permission */
.bpe-body[data-readonly="true"] input,
.bpe-body[data-readonly="true"] textarea,
.bpe-body[data-readonly="true"] select {
  pointer-events: none;
  background: var(--bg2, #FAFAFC) !important;
  color: rgba(15, 23, 60, .55);
  cursor: not-allowed;
}
</style>
