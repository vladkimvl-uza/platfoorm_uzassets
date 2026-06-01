<template>
  <div class="bpe-modal-backdrop" @click.self="$emit('close')">
    <div class="bpe-modal">
      <div class="bpe-header">
        <div class="bpe-title">
          <h2>Редактор бизнес-плана</h2>
          <div class="bpe-subtitle">{{ companyName }} · FY {{ year }}</div>
        </div>
        <button class="bpe-close" @click="$emit('close')" title="Закрыть">×</button>
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
            {{ p.label }}
          </button>
        </div>
        <div class="bpe-view-toggle">
          <button
            class="bpe-view-btn"
            :class="{ on: viewMode === 'all' }"
            @click="viewMode = 'all'"
            title="Показать все 22 метрики"
          >
            Все
          </button>
          <button
            class="bpe-view-btn bpe-view-btn-inc"
            :class="{ on: viewMode === 'income' }"
            @click="viewMode = 'income'"
            title="Только доходные статьи (revenue, finIncome + subs)"
          >
            Доходы
            <span class="bpe-view-cnt">{{ incomeCount }}</span>
          </button>
          <button
            class="bpe-view-btn bpe-view-btn-exp"
            :class="{ on: viewMode === 'expenses' }"
            @click="viewMode = 'expenses'"
            title="Только расходные статьи (cogs, opExpenses, finCost, tax + sub-items)"
          >
            Расходы
            <span class="bpe-view-cnt">{{ expensesCount }}</span>
          </button>
        </div>
      </div>

      <!-- Subset summary — visible when viewMode != 'all' -->
      <div v-if="viewMode !== 'all'" class="bpe-summary" :class="`bpe-summary-${viewMode}`">
        <div class="bpe-summary-row">
          <div class="bpe-summary-cell">
            <div class="bpe-summary-l">Сумма (план)</div>
            <div class="bpe-summary-v">{{ fmtSummary(subsetTotals.plan) }}</div>
          </div>
          <div class="bpe-summary-cell">
            <div class="bpe-summary-l">Сумма (факт)</div>
            <div class="bpe-summary-v">{{ fmtSummary(subsetTotals.fact) }}</div>
          </div>
          <div class="bpe-summary-cell">
            <div class="bpe-summary-l">Δ план→факт</div>
            <div class="bpe-summary-v" :class="deltaClass(subsetTotals.delta)">
              {{ subsetTotals.delta != null ? (subsetTotals.delta >= 0 ? '+' : '') + fmtSummary(subsetTotals.delta) : '—' }}
            </div>
          </div>
          <div class="bpe-summary-cell">
            <div class="bpe-summary-l">% выручки</div>
            <div class="bpe-summary-v">
              {{ subsetTotals.pctOfRevenue != null ? subsetTotals.pctOfRevenue.toFixed(1) + '%' : '—' }}
            </div>
          </div>
        </div>
      </div>

      <div class="bpe-body" :data-readonly="!perm.canEdit">
        <table class="bpe-tbl">
          <thead>
            <tr>
              <th class="lbl">Показатель</th>
              <th>План</th>
              <th>Прогноз</th>
              <th>Факт</th>
            </tr>
          </thead>
          <tbody>
            <tr
              v-for="f in displayedFields"
              :key="f.key"
              :class="{ 'is-sub': f.sub, 'is-auto': f.auto, 'is-key': isKeyMetric(f.key), 'is-expense': f.positive }"
            >
              <td class="lbl">
                <span v-if="f.auto" class="bpe-auto-tag" :title="`Рассчитывается автоматически: ${f.formula || ''}`">∑ расчёт</span>
                {{ f.label }}
              </td>
              <td>
                <input
                  v-if="!f.auto"
                  v-model.number="data[activePeriod][f.key].plan"
                  type="number"
                  step="0.001"
                  inputmode="decimal"
                  class="bpe-in"
                  @input="markDirty"
                />
                <span v-else class="bpe-auto-val">{{ formatComputed(f.key, "plan") }}</span>
              </td>
              <td>
                <input
                  v-if="!f.auto"
                  v-model.number="data[activePeriod][f.key].expect"
                  type="number"
                  step="0.001"
                  inputmode="decimal"
                  class="bpe-in"
                  @input="markDirty"
                />
                <span v-else class="bpe-auto-val">{{ formatComputed(f.key, "expect") }}</span>
              </td>
              <td class="bpe-fact-cell">
                <input
                  v-if="!f.auto"
                  v-model.number="data[activePeriod][f.key].fact"
                  type="number"
                  step="0.001"
                  inputmode="decimal"
                  class="bpe-in"
                  :class="{ 'bpe-in-nsbu': activePeriod === 'annual' && nsbuFacts[f.key] != null && data[activePeriod][f.key].fact == null }"
                  :placeholder="activePeriod === 'annual' && nsbuFacts[f.key] != null ? String(nsbuFacts[f.key]) : '—'"
                  :title="activePeriod === 'annual' && nsbuFacts[f.key] != null ? `Автоматически из НСБУ: ${nsbuFacts[f.key]}. Введите своё значение чтобы перезаписать.` : ''"
                  @input="markDirty"
                />
                <span v-else class="bpe-auto-val">{{ formatComputed(f.key, "fact") }}</span>
                <span
                  v-if="!f.auto && activePeriod === 'annual' && nsbuFacts[f.key] != null"
                  class="bpe-nsbu-badge"
                  title="Автоматически из НСБУ"
                >
                  <svg width="7" height="7" viewBox="0 0 10 10" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M1.5 5l2.5 2.5L8.5 2.5"/></svg>
                  НСБУ
                </span>
              </td>
            </tr>
          </tbody>
        </table>
      </div>

      <div class="bpe-footer">
        <div class="bpe-status">
          <span v-if="dirty" class="bpe-status-d">Несохранённые изменения</span>
          <span v-else-if="lastSaved" class="bpe-status-s">Сохранено · {{ lastSaved }}</span>
          <span v-else-if="activePeriod === 'annual' && nsbuCount > 0" class="bpe-status-nsbu">
            <svg width="12" height="12" viewBox="0 0 12 12" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><circle cx="6" cy="6" r="5"/><path d="M4 6l1.5 1.5L8.5 4.5"/></svg>
            Из НСБУ доступно фактов: <strong>{{ nsbuCount }}</strong> · при пустом поле Факт подставится автоматически
          </span>
          <span v-else-if="activePeriod === 'annual'" class="bpe-status-h">
            НСБУ данных за {{ year }} год пока нет
          </span>
          <span v-else class="bpe-status-h">Квартальный период — ручной ввод (НСБУ не парсится по кварталам)</span>
        </div>
        <div class="bpe-actions">
          <button class="bpe-btn bpe-btn-ghost" @click="$emit('close')">{{ perm.canEdit ? "Отмена" : "Закрыть" }}</button>
          <button v-if="perm.canEdit" class="bpe-btn bpe-btn-primary" @click="save" :disabled="saving || !dirty">
            {{ saving ? "Сохранение..." : "Сохранить все периоды" }}
          </button>
          <span v-else class="bpe-status-h">Только просмотр · нет прав на редактирование</span>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import {
  BP_FIELDS,
  BP_PERIODS,
  bpApi,
  bpFieldsFor,
  type BpPeriod,
  type BpRecordUpsert,
} from "@/api/bpKpi";
import { isModerationQueued } from "@/api/client";
import { usePermissions } from "@/composables/usePermissions";

const perm = usePermissions("bp");

const props = defineProps<{
  companyId: string;
  companyName: string;
  year: number;
}>();

const emit = defineEmits<{
  (e: "close"): void;
  (e: "saved"): void;
}>();

type Cell = { plan: number | null; expect: number | null; fact: number | null };
type Period = "annual" | "q1" | "q2" | "q3" | "q4";

const PERIODS: Period[] = ["annual", "q1", "q2", "q3", "q4"];

const activePeriod = ref<Period>("annual");
const data = ref<Record<Period, Record<string, Cell>>>(makeBlank());
const dirty = ref(false);

// ─── View-mode toggle: all / income (revenue side) / expenses (positive=true)
import type { BpViewMode } from "@/api/bpKpi";
const viewMode = ref<BpViewMode>("all");
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

// NSBU autofill values for fact column (annual period only)
// key → numeric value from financial_indicators table
const nsbuFacts = ref<Record<string, number | null>>({});
const nsbuCount = computed(() =>
  Object.values(nsbuFacts.value).filter(v => v != null).length
);

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

// Compute auto fields based on currently entered values
function formatComputed(key: string, col: "plan" | "expect" | "fact"): string {
  const p = activePeriod.value;
  const get = (k: string) => data.value[p][k]?.[col];
  let v: number | null = null;

  if (key === "grossProfit") {
    const rev = get("revenue"), cogs = get("cogs");
    if (rev != null && cogs != null) v = rev - Math.abs(cogs);
  } else if (key === "opProfit") {
    const rev = get("revenue"), cogs = get("cogs"), opex = get("opExpenses"), oth = get("otherOpInc");
    if (rev != null && cogs != null && opex != null) {
      v = rev - Math.abs(cogs) - Math.abs(opex) + (oth ?? 0);
    }
  } else if (key === "hhProfit") {
    const op = computeOp(col), fi = get("finIncome"), fc = get("finCost");
    if (op != null) v = op + (fi ?? 0) - Math.abs(fc ?? 0);
  } else if (key === "pbt") {
    const hh = computeHh(col);
    if (hh != null) v = hh;
  } else if (key === "profit") {
    const pbt = computeHh(col), tax = get("tax");
    if (pbt != null && tax != null) v = pbt - Math.abs(tax);
  }
  if (v == null) return "—";
  return v.toLocaleString("ru-RU", { minimumFractionDigits: 0, maximumFractionDigits: 2 });
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
onMounted(async () => {
  try {
    const raw = await bpApi.getRaw(props.companyId, props.year);
    console.log("[BP editor] raw loaded:", { companyId: props.companyId, year: props.year, raw });

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
      for (const f of BP_FIELDS) {
        const c = annualComputed.metrics[f.key];
        if (c?.fact_auto && c.fact != null) {
          nsbu[f.key] = Number(c.fact);
        }
      }
      nsbuFacts.value = nsbu;
      console.log(`[BP editor] NSBU autofill loaded: ${Object.keys(nsbu).length} fields`);
    } catch (e) {
      // NSBU data not available for this year — no placeholder, just empty inputs
      nsbuFacts.value = {};
      console.log("[BP editor] NSBU autofill: no data", e);
    }
  } catch (e) {
    console.error("[BP editor] load failed:", e);
    error.value = "Не удалось загрузить данные";
  }
});

async function save() {
  if (saving.value || !dirty.value) return;
  saving.value = true;
  error.value = null;
  try {
    const records: BpRecordUpsert[] = [];
    for (const p of PERIODS) {
      for (const f of BP_FIELDS) {
        if (f.auto) continue; // skip computed
        const c = data.value[p][f.key];
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
    const resp = await bpApi.bulkUpsert(records);
    dirty.value = false;
    if (isModerationQueued(resp)) {
      // Gated. Interceptor has shown a toast — just close.
      emit("close");
    } else {
      lastSaved.value = new Date().toLocaleTimeString("ru-RU", { hour: "2-digit", minute: "2-digit" });
      emit("saved");
    }
  } catch (e) {
    console.error("[BP editor] save failed:", e);
    error.value = "Сохранение не удалось";
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
  backdrop-filter: blur(8px);
  z-index: 9999;
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
  max-height: 90vh;
  display: flex;
  flex-direction: column;
  box-shadow: 0 24px 64px rgba(15, 23, 60, .18);
  animation: bpeModalIn .35s var(--ease-standard);
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
.bpe-subtitle { font-size: 11px; color: rgba(15, 23, 60, .55); margin-top: 2px; }
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
.bpe-fact-cell { position: relative; }
.bpe-nsbu-badge {
  position: absolute;
  top: 3px;
  right: 8px;
  display: inline-flex;
  align-items: center;
  gap: 2px;
  padding: 1px 5px;
  background: var(--bg1, #fff);
  color: #0F6E56;
  border: 1px solid rgba(29, 158, 117, .25);
  border-radius: 3px;
  font-size: 8px;
  font-weight: 600;
  letter-spacing: .04em;
  text-transform: uppercase;
  pointer-events: none;
  z-index: 2;
}
.bpe-in-nsbu {
  background: rgba(29, 158, 117, .04) !important;
  border-color: rgba(29, 158, 117, .25) !important;
}
.bpe-in-nsbu::placeholder {
  color: #0F6E56;
  opacity: .65;
  font-style: normal;
}

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
