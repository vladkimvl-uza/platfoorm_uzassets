<script setup lang="ts">
import { computed, onMounted, ref, watch } from "vue";
import { useCompaniesStore } from "@/stores/companies";
import {
  finmodelApi,
  type TemplateRow, type YearLock, type MacroEffective,
} from "@/api/finmodel";

import FinModelHeader from "@/components/finmodel/FinModelHeader.vue";
import FinModelTabBar from "@/components/finmodel/FinModelTabBar.vue";
import FinModelBalanceTable from "@/components/finmodel/FinModelBalanceTable.vue";
import FinModelDashboardTab from "@/components/finmodel/FinModelDashboardTab.vue";
import FinModelMacroTab from "@/components/finmodel/FinModelMacroTab.vue";
import FinModelChecksTab from "@/components/finmodel/FinModelChecksTab.vue";
import FinModelHistoryDrawer from "@/components/finmodel/FinModelHistoryDrawer.vue";
import FinModelBottomAnalytics from "@/components/finmodel/FinModelBottomAnalytics.vue";
import FinModelFooter from "@/components/finmodel/FinModelFooter.vue";

const companiesStore = useCompaniesStore();

const selectedCompanyId = ref<string>("");
const selectedYear = ref<number | null>(null);
const yearsForCompany = ref<number[]>([]);
const activeTab = ref<string>("balance");
const unit = ref<"thousand" | "million" | "billion">("thousand");
const historyOpen = ref(false);

const divisor = computed(() => unit.value === "thousand" ? 1 : unit.value === "million" ? 1000 : 1_000_000);

const template = ref<TemplateRow[]>([]);
const cells = ref<Record<string, string | null>>({});
const lock = ref<YearLock | null>(null);
const macro = ref<MacroEffective | null>(null);
const errorMsg = ref<string | null>(null);

const allYearsCells = ref<Record<number, Record<string, string | null>>>({});
const allYearsLoading = ref(false);

onMounted(async () => {
  await companiesStore.ensureLoaded();
  try {
    template.value = await finmodelApi.getTemplate();
  } catch (e: any) {
    errorMsg.value = e?.response?.data?.detail || e?.message || "Не удалось загрузить шаблон";
  }
});

watch(selectedCompanyId, async (co) => {
  cells.value = {};
  lock.value = null;
  macro.value = null;
  selectedYear.value = null;
  yearsForCompany.value = [];
  allYearsCells.value = {};
  historyOpen.value = false;
  if (!co) return;
  try {
    const yrs = await finmodelApi.listYears(co);
    yearsForCompany.value = yrs.map(y => y.year).sort((a, b) => a - b);
    if (yearsForCompany.value.length > 0) {
      selectedYear.value = yearsForCompany.value[yearsForCompany.value.length - 1];
    }
  } catch (e: any) {
    errorMsg.value = e?.response?.data?.detail || e?.message || "Не удалось загрузить годы";
  }
});

watch(selectedYear, async (y) => {
  cells.value = {};
  lock.value = null;
  macro.value = null;
  if (!y || !selectedCompanyId.value) return;
  try {
    const [data, m] = await Promise.all([
      finmodelApi.getYear(selectedCompanyId.value, y),
      finmodelApi.getMacro(selectedCompanyId.value, y),
    ]);
    lock.value = data.lock;
    const map: Record<string, string | null> = {};
    for (const c of data.cells) map[c.row_code] = c.value;
    cells.value = map;
    allYearsCells.value = { ...allYearsCells.value, [y]: map };
    macro.value = m;
  } catch (e: any) {
    errorMsg.value = e?.response?.data?.detail || e?.message || "Не удалось загрузить данные";
  }
});

async function onMacroChanged() {
  if (!selectedCompanyId.value || !selectedYear.value) return;
  try {
    macro.value = await finmodelApi.getMacro(selectedCompanyId.value, selectedYear.value);
  } catch { /* ignore */ }
}

// ─── Client-side formula evaluation ──────────────────────────────
const sectionCodes = computed(() => {
  const map = new Map<string, TemplateRow[]>();
  for (const r of [...template.value].sort((a, b) => a.section.localeCompare(b.section) || a.order_idx - b.order_idx)) {
    const arr = map.get(r.section) ?? [];
    arr.push(r);
    map.set(r.section, arr);
  }
  return map;
});

function evalAllForYear(rawCells: Record<string, string | null>): Record<string, number> {
  const result: Record<string, number> = {};
  for (const r of template.value) {
    if (r.row_type === "input") {
      const raw = rawCells[r.code];
      result[r.code] = raw == null || raw === "" ? 0 : Number(raw);
    }
  }
  for (const r of [...template.value].sort((a, b) => a.order_idx - b.order_idx)) {
    if (r.row_type === "input" || !r.formula) continue;
    try { result[r.code] = evalFormula(r.formula, r.section, result); }
    catch { result[r.code] = 0; }
  }
  return result;
}

function evalFormula(formula: string, section: string, values: Record<string, number>): number {
  const mRange = formula.match(/^SUM\(([A-Za-z0-9_]+)\.\.([A-Za-z0-9_]+)\)$/);
  if (mRange) {
    const codes = sectionCodes.value.get(section) ?? [];
    const i = codes.findIndex(c => c.code === mRange[1]);
    const j = codes.findIndex(c => c.code === mRange[2]);
    if (i < 0 || j < 0) return 0;
    const [lo, hi] = i <= j ? [i, j] : [j, i];
    return codes.slice(lo, hi + 1).reduce((s, c) => s + (values[c.code] ?? 0), 0);
  }
  const mList = formula.match(/^SUM\(([\w_,\s]+)\)$/);
  if (mList) {
    return mList[1].split(",").map(s => s.trim()).filter(Boolean).reduce((s, c) => s + (values[c] ?? 0), 0);
  }
  let total = 0;
  const tokenRe = /([+\-]?)\s*([A-Za-z0-9_]+)/g;
  let m: RegExpExecArray | null;
  while ((m = tokenRe.exec(formula)) !== null) {
    const sign = m[1];
    const v = values[m[2]] ?? 0;
    total += sign === "-" ? -v : v;
  }
  return total;
}

const computedActive = computed<Record<string, string>>(() => {
  const r = evalAllForYear(cells.value);
  const out: Record<string, string> = {};
  for (const [k, v] of Object.entries(r)) out[k] = String(v);
  return out;
});

const prevYearComputed = computed<Record<string, string> | null>(() => {
  if (!selectedYear.value) return null;
  const idx = yearsForCompany.value.indexOf(selectedYear.value);
  if (idx <= 0) return null;
  const prevY = yearsForCompany.value[idx - 1];
  const prevCells = allYearsCells.value[prevY];
  if (!prevCells) return null;
  const r = evalAllForYear(prevCells);
  const out: Record<string, string> = {};
  for (const [k, v] of Object.entries(r)) out[k] = String(v);
  return out;
});

const multiYearComputed = computed<Record<number, Record<string, number>>>(() => {
  const out: Record<number, Record<string, number>> = {};
  for (const [yStr, rawCells] of Object.entries(allYearsCells.value)) {
    out[Number(yStr)] = evalAllForYear(rawCells);
  }
  return out;
});

const dashboardYears = computed(() =>
  Object.keys(allYearsCells.value).map(Number).sort((a, b) => a - b)
);

async function ensureAllYears() {
  if (!selectedCompanyId.value || yearsForCompany.value.length === 0) return;
  const missing = yearsForCompany.value.filter(y => !(y in allYearsCells.value));
  if (missing.length === 0) return;
  allYearsLoading.value = true;
  try {
    const results = await Promise.all(
      missing.map(y => finmodelApi.getYear(selectedCompanyId.value, y))
    );
    const next = { ...allYearsCells.value };
    for (const data of results) {
      const map: Record<string, string | null> = {};
      for (const c of data.cells) map[c.row_code] = c.value;
      next[data.year] = map;
    }
    allYearsCells.value = next;
  } catch (e: any) {
    errorMsg.value = e?.response?.data?.detail || e?.message || "Не удалось загрузить годы";
  } finally {
    allYearsLoading.value = false;
  }
}

watch(activeTab, (t) => {
  if (t === "dash_pl" || t === "dash_bs" || t === "dash_cf") void ensureAllYears();
});

// ─── Balance pill ────────────────────────────────────────────────
const balanceCheck = computed(() => {
  const asset = Number(computedActive.value["400"] || 0);
  const liab = Number(computedActive.value["780"] || 0);
  const delta = liab - asset;
  return { asset, liab, delta, isBalanced: Math.abs(delta) < 0.01 };
});

const balanceText = computed(() => {
  if (!selectedCompanyId.value || !selectedYear.value) return "Нет данных";
  const bc = balanceCheck.value;
  if (bc.asset === 0 && bc.liab === 0) return "Нет данных";
  if (bc.isBalanced) return "Баланс сходится";
  return `Расхождение: ${bc.delta.toLocaleString("ru-RU")}`;
});

const balanceStatus = computed<"neutral" | "ok" | "bad">(() => {
  if (!selectedCompanyId.value || !selectedYear.value) return "neutral";
  const bc = balanceCheck.value;
  if (bc.asset === 0 && bc.liab === 0) return "neutral";
  return bc.isBalanced ? "ok" : "bad";
});

const editable = computed(() =>
  !!selectedCompanyId.value && !!selectedYear.value &&
  !(lock.value && (lock.value.status === "locked" || lock.value.status === "approved"))
);

// ─── Cell edit ───────────────────────────────────────────────────
const saveError = ref<string | null>(null);
const savingCount = ref(0);

async function onCellEdit(payload: { code: string; value: string | null }) {
  if (!selectedCompanyId.value || !selectedYear.value) return;
  cells.value = { ...cells.value, [payload.code]: payload.value };
  const y = selectedYear.value;
  allYearsCells.value = {
    ...allYearsCells.value,
    [y]: { ...(allYearsCells.value[y] ?? {}), [payload.code]: payload.value },
  };
  savingCount.value++;
  saveError.value = null;
  try {
    await finmodelApi.patchCell(selectedCompanyId.value, selectedYear.value, payload.code, payload.value);
  } catch (e: any) {
    saveError.value = e?.response?.data?.detail || e?.message || "Сохранение не удалось";
  } finally {
    savingCount.value--;
  }
}

// ─── Year actions ────────────────────────────────────────────────
async function onCreateYear(y: number) {
  if (!selectedCompanyId.value) return;
  try {
    await finmodelApi.createYear(selectedCompanyId.value, y);
    if (!yearsForCompany.value.includes(y)) {
      yearsForCompany.value = [...yearsForCompany.value, y].sort((a, b) => a - b);
    }
    selectedYear.value = y;
  } catch (e: any) {
    errorMsg.value = e?.response?.data?.detail || e?.message || "Не удалось создать год";
  }
}

async function onDeleteYear() {
  if (!selectedCompanyId.value || !selectedYear.value) return;
  const y = selectedYear.value;
  try {
    await finmodelApi.deleteYear(selectedCompanyId.value, y);
    yearsForCompany.value = yearsForCompany.value.filter(x => x !== y);
    const cache = { ...allYearsCells.value };
    delete cache[y];
    allYearsCells.value = cache;
    selectedYear.value = yearsForCompany.value[yearsForCompany.value.length - 1] ?? null;
  } catch (e: any) {
    errorMsg.value = e?.response?.data?.detail || e?.message || "Не удалось удалить год";
  }
}

async function onLockYear() {
  if (!selectedCompanyId.value || !selectedYear.value) return;
  try {
    lock.value = await finmodelApi.lockYear(selectedCompanyId.value, selectedYear.value, "locked");
  } catch (e: any) {
    errorMsg.value = e?.response?.data?.detail || e?.message || "Не удалось заблокировать";
  }
}

async function onUnlockYear() {
  if (!selectedCompanyId.value || !selectedYear.value) return;
  try {
    lock.value = await finmodelApi.unlockYear(selectedCompanyId.value, selectedYear.value);
  } catch (e: any) {
    errorMsg.value = e?.response?.data?.detail || e?.message || "Не удалось разблокировать";
  }
}

// ─── Excel CSV download ──────────────────────────────────────────
async function onExportCsv() {
  if (!selectedCompanyId.value || !selectedYear.value) return;
  try {
    const blob = await finmodelApi.exportCsv(selectedCompanyId.value, selectedYear.value, true);
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    const co = companiesList.value.find(c => c.id === selectedCompanyId.value);
    a.href = url;
    a.download = `finmodel_${co?.code ?? "company"}_${selectedYear.value}.csv`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  } catch (e: any) {
    errorMsg.value = e?.response?.data?.detail || e?.message || "Не удалось скачать CSV";
  }
}

const companiesList = computed(() =>
  [...companiesStore.companies].sort((a, b) =>
    (a.name_short || a.name_ru).localeCompare(b.name_short || b.name_ru, "ru")
  )
);
</script>

<template>
  <div class="finmodel-page">
    <div class="finmodel-card">
      <FinModelHeader
        :companies="companiesList"
        :selected-company-id="selectedCompanyId"
        @update:selected-company-id="selectedCompanyId = $event"
        :years="yearsForCompany"
        :selected-year="selectedYear"
        @update:selected-year="selectedYear = $event"
        @create-year="onCreateYear"
        @delete-year="onDeleteYear"
        @lock-year="onLockYear"
        @unlock-year="onUnlockYear"
        @export-csv="onExportCsv"
        @toggle-history="historyOpen = !historyOpen"
        :balance-text="balanceText"
        :balance-status="balanceStatus"
        :lock-status="lock?.status ?? null"
      />
      <FinModelTabBar
        :active="activeTab"
        :unit="unit"
        @change="activeTab = $event"
        @update:unit="unit = $event"
      />

      <FinModelHistoryDrawer
        :open="historyOpen"
        :company-id="selectedCompanyId"
        :year="selectedYear"
        @close="historyOpen = false"
      />

      <div v-if="errorMsg" class="fm-banner fm-banner-err">
        {{ errorMsg }}
        <button class="fm-banner-dismiss" @click="errorMsg = null">×</button>
      </div>
      <div v-if="saveError" class="fm-banner fm-banner-err">
        Ошибка сохранения: {{ saveError }}
        <button class="fm-banner-dismiss" @click="saveError = null">×</button>
      </div>

      <FinModelBalanceTable
        v-if="activeTab === 'balance'"
        section="BS"
        :template="template"
        :values="cells"
        :computed-values="computedActive"
        :editable="editable"
        :divisor="divisor"
        @cell-edit="onCellEdit"
      />
      <FinModelBalanceTable
        v-else-if="activeTab === 'pl'"
        section="PL"
        :template="template"
        :values="cells"
        :computed-values="computedActive"
        :editable="editable"
        :divisor="divisor"
        @cell-edit="onCellEdit"
      />

      <FinModelDashboardTab
        v-else-if="activeTab === 'dash_pl'"
        variant="pl"
        :template="template"
        :multi-year-computed="multiYearComputed"
        :years="dashboardYears"
        :loading="allYearsLoading"
        :divisor="divisor"
      />
      <FinModelDashboardTab
        v-else-if="activeTab === 'dash_bs'"
        variant="bs"
        :template="template"
        :multi-year-computed="multiYearComputed"
        :years="dashboardYears"
        :loading="allYearsLoading"
        :divisor="divisor"
      />
      <FinModelDashboardTab
        v-else-if="activeTab === 'dash_cf'"
        variant="cf"
        :template="template"
        :multi-year-computed="multiYearComputed"
        :years="dashboardYears"
        :loading="allYearsLoading"
        :divisor="divisor"
      />

      <FinModelMacroTab
        v-else-if="activeTab === 'macro'"
        :company-id="selectedCompanyId"
        :year="selectedYear"
        :macro="macro"
        @macro-changed="onMacroChanged"
      />

      <FinModelChecksTab
        v-else-if="activeTab === 'checks'"
        :company-id="selectedCompanyId"
        :year="selectedYear"
      />

      <FinModelBottomAnalytics
        :computed-active="computedActive"
        :prev-computed="prevYearComputed"
        :year="selectedYear"
        :divisor="divisor"
      />
      <FinModelFooter :saving="savingCount > 0" :lock-status="lock?.status ?? null" />
    </div>
  </div>
</template>

<style scoped>
.finmodel-page {
  font-family: -apple-system, system-ui, sans-serif;
  color: var(--t1, #1E2A4A);
  padding: 12px 0;
  max-width: 1480px;
  margin: 0 auto;
}
.finmodel-card {
  background: var(--bg1, #fff);
  border: 0.5px solid #E5E7EB;
  border-radius: 14px;
  overflow: hidden;
}
.fm-banner {
  padding: 8px 14px;
  font-size: 11px;
  border-bottom: 0.5px solid #F1EFE8;
  display: flex;
  align-items: center;
  gap: 8px;
}
.fm-banner-err {
  background: rgba(226, 75, 74, .06);
  color: #C0322F;
}
.fm-banner-dismiss {
  margin-left: auto;
  background: transparent;
  border: none;
  color: inherit;
  cursor: pointer;
  font-size: 14px;
  line-height: 1;
}
</style>
