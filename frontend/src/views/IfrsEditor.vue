<script setup lang="ts">
/**
 * NsbuEditor.vue — Pack 7.51
 * ─────────────────────────────────────────────────────────────────
 * Полнофункциональный редактор показателей МСФО для каждой компании.
 *
 * Возможности:
 *   ✓ Grid X компании · показатели × годы (2021-2026, +Год)
 *   ✓ Авто-расчёты (grossProfit, pbt, profit, ebitda, totalAssets, totalLiab, debt)
 *   ✓ Ручное переопределение авто-полей (флаг manual)
 *   ✓ Калькулятор с ссылками на ячейки + фин-функциями (GROWTH/CAGR/MARGIN/AVG)
 *   ✓ Добавление кастомных показателей (+Поле)
 *   ✓ Переименование стандартных и кастомных
 *   ✓ Override формулы авто-поля
 *   ✓ Anti-loss: localStorage backup каждые 20с + на blur
 *   ✓ Валидация (positive-only, sanity на >1e6)
 *
 * Persistence (Phase 1 → localStorage; Phase 2 → backend API):
 *   key: uza_nsbu_editor_{companyCode}
 *   shape: { values, customFields, renames, formulaOverrides, manualFlags, savedAt }
 */
import { computed, onMounted, onUnmounted, reactive, ref, watch } from "vue";
import { useRouter } from "vue-router";
import { companiesApi, type CompanyListItem } from "@/api/companies";
import { financialsApi, type PortfolioSummaryResponse } from "@/api/financials";
import {
  STANDARD_SCHEMA, DEFAULT_YEARS, AUTO_FORMULAS,
  computeAutoValue, CANONICAL_METRICS,
  type FieldDef, type SectionId,
} from "@/composables/useIfrsSchema";
import {
  useNsbuCalculator, safeEvalExpression, type CellMatrix,
} from "@/composables/useNsbuCalculator";
import { useToast } from "@/composables/useToast";
import { usePermissions } from "@/composables/usePermissions";
const _perm = usePermissions("financials");

const emit = defineEmits<{ close: [] }>();

const router = useRouter();
const toast = useToast();
const calc = useNsbuCalculator();

// ─── State ──────────────────────────────────────────────────────
const companies = ref<CompanyListItem[]>([]);
const loadingList = ref(true);
const searchQuery = ref("");
const selectedCode = ref<string>("");

// Pack 7.60: IFRS-specific topbar state
type PeriodT = "FY" | "Q1" | "H1" | "9M";
const period = ref<PeriodT>("FY");
const consolidated = ref<boolean>(true);
// State key prefix combines code + period + scope so switching reloads correctly
function stateKey(code: string): string {
  return `${code}__${period.value}__${consolidated.value ? "c" : "s"}`;
}

const selectedSection = ref<SectionId>("pnl");
const years = ref<number[]>([...DEFAULT_YEARS]);
const focusedCell = ref<{ field: string; year: number } | null>(null);

// Per-company state (loaded on demand)
interface CompanyState {
  values: Record<string, Record<number, number | null>>;  // [field][year] = value
  customFields: FieldDef[];
  renames: Record<string, string>;          // fieldId → custom display name
  formulaOverrides: Record<string, string>; // fieldId → custom formula expression
  manualFlags: Record<string, Record<number, boolean>>;  // [field][year] = true if manually overridden
  notes: Record<string, string>;            // Pack 7.63: fieldId → markdown disclosure text
  savedAt?: number;
  dirty: boolean;
}
const companyStates = reactive<Record<string, CompanyState>>({});
const loadingCompany = ref(false);

// UI sub-state
const showAddFieldDialog = ref(false);
const newFieldDraft = ref({ label: "", section: "pnl" as SectionId, formula: "", canonical: "" });
const renamingFieldId = ref<string | null>(null);
const renameDraft = ref("");
const editingFormulaFieldId = ref<string | null>(null);
const formulaDraft = ref("");
const editingCanonicalFieldId = ref<string | null>(null);
const canonicalDraft = ref("");
// Pack 7.63: inline note editor
const editingNoteFieldId = ref<string | null>(null);
const noteDraft = ref("");

// ─── Filtered companies ────────────────────────────────────────
const filteredCompanies = computed(() => {
  const q = searchQuery.value.trim().toLowerCase();
  if (!q) return companies.value;
  return companies.value.filter((c) =>
    (c.code || "").toLowerCase().includes(q) ||
    (c.name_short || "").toLowerCase().includes(q) ||
    (c.name_ru || "").toLowerCase().includes(q),
  );
});

const currentCompany = computed<CompanyListItem | null>(() =>
  companies.value.find((c) => c.code === selectedCode.value) || null,
);

// ─── Current company state proxies ─────────────────────────────
function ensureState(code: string): CompanyState {
  if (!companyStates[code]) {
    companyStates[code] = {
      values: {},
      customFields: [],
      renames: {},
      formulaOverrides: {},
      manualFlags: {},
      notes: {},
      dirty: false,
    };
  }
  if (!companyStates[code].notes) {
    companyStates[code].notes = {};
  }
  return companyStates[code];
}

const currentState = computed<CompanyState | null>(() => {
  if (!selectedCode.value) return null;
  return companyStates[selectedCode.value] || null;
});

// ─── Display schema (standard + custom + renames + formula overrides) ──
const displaySchema = computed(() => {
  const state = currentState.value;
  if (!state) return STANDARD_SCHEMA;
  // Merge standard + custom; renames + overrides applied at render
  return STANDARD_SCHEMA.map((section) => {
    const customForSection = state.customFields.filter((f) => f.id.startsWith(`__custom_${section.id}_`));
    return { ...section, fields: [...section.fields, ...customForSection] };
  });
});

const currentSectionDef = computed(() =>
  displaySchema.value.find((s) => s.id === selectedSection.value)!,
);

// ─── Cell matrix for calculator (all fields × years for current company) ──
const cellMatrix = computed<CellMatrix>(() => {
  const state = currentState.value;
  if (!state) return {};
  // Return values as-is plus auto-computed for non-manual auto fields
  const matrix: CellMatrix = {};
  for (const section of displaySchema.value) {
    for (const field of section.fields) {
      matrix[field.id] = matrix[field.id] || {};
      for (const y of years.value) {
        let v: number | null = (state.values[field.id]?.[y]) ?? null;
        if (v == null && field.autoFormula) {
          const yearMap: Record<string, number | null> = {};
          for (const f2 of section.fields) {
            yearMap[f2.id] = state.values[f2.id]?.[y] ?? null;
          }
          v = computeAutoValue(field, yearMap);
        }
        matrix[field.id][y] = v;
      }
    }
  }
  return matrix;
});

// ─── Auto-calc on values change (reactive) ─────────────────────
function recomputeAutoFields() {
  const state = currentState.value;
  if (!state) return;
  for (const section of displaySchema.value) {
    for (const field of section.fields) {
      if (!field.autoFormula) continue;
      // Skip if user has overridden formula? For now apply override if set.
      const overrideExpr = state.formulaOverrides[field.id];
      for (const y of years.value) {
        const isManual = !!state.manualFlags[field.id]?.[y];
        if (isManual) continue;

        let computed: number | null = null;
        if (overrideExpr) {
          const { value } = safeEvalExpression(overrideExpr, cellMatrix.value, y);
          computed = value;
        } else {
          const yearMap: Record<string, number | null> = {};
          for (const f2 of section.fields) {
            yearMap[f2.id] = state.values[f2.id]?.[y] ?? null;
          }
          computed = computeAutoValue(field, yearMap);
        }
        if (!state.values[field.id]) state.values[field.id] = {};
        if (state.values[field.id][y] !== computed) {
          state.values[field.id][y] = computed;
        }
      }
    }
  }
}

// ─── Cell value get/set ────────────────────────────────────────
function getCellValue(field: FieldDef, year: number): number | null {
  const state = currentState.value;
  if (!state) return null;
  return state.values[field.id]?.[year] ?? null;
}

function getDisplayCellValue(field: FieldDef, year: number): string {
  const v = getCellValue(field, year);
  if (v == null) return "";
  // Format with Russian decimal comma
  return formatNumber(v);
}

function formatNumber(v: number): string {
  if (v === 0) return "0";
  const rounded = Math.round(v * 1000) / 1000;
  return String(rounded).replace(".", ",");
}

function parseNumber(s: string): number | null {
  if (!s || s.trim() === "") return null;
  const cleaned = s.replace(/\s+/g, "").replace(",", ".");
  const v = parseFloat(cleaned);
  return isNaN(v) ? null : v;
}

function onCellInput(field: FieldDef, year: number, raw: string) {
  const state = currentState.value;
  if (!state) return;
  let v = parseNumber(raw);
  // positive-only enforcement
  if (v != null && field.positiveOnly && v < 0) {
    v = Math.abs(v);
    toast.info(`«${getFieldLabel(field)}» — вводите положительное число (взяли модуль)`);
  }
  if (!state.values[field.id]) state.values[field.id] = {};
  state.values[field.id][year] = v;
  // If user edited an auto-field → mark manual
  if (field.autoFormula) {
    if (!state.manualFlags[field.id]) state.manualFlags[field.id] = {};
    state.manualFlags[field.id][year] = true;
  }
  state.dirty = true;
  recomputeAutoFields();
  scheduleBackup();
}

function onCellFocus(field: FieldDef, year: number) {
  focusedCell.value = { field: field.id, year };
  calc.setTarget(field.id, year);
}

function onCellBlur() {
  // Trigger immediate backup on blur (anti-loss)
  doBackup();
}

function clearManualFlag(field: FieldDef, year: number) {
  const state = currentState.value;
  if (!state) return;
  if (state.manualFlags[field.id]) {
    state.manualFlags[field.id][year] = false;
  }
  recomputeAutoFields();
  state.dirty = true;
  scheduleBackup();
}

function getFieldLabel(field: FieldDef): string {
  const state = currentState.value;
  if (state?.renames[field.id]) return state.renames[field.id];
  return field.label;
}

function getFieldFormula(field: FieldDef): string {
  const state = currentState.value;
  if (state?.formulaOverrides[field.id]) return state.formulaOverrides[field.id];
  if (field.autoFormula && AUTO_FORMULAS[field.autoFormula]) {
    return AUTO_FORMULAS[field.autoFormula].expr;
  }
  return "";
}

function isAutoField(field: FieldDef): boolean {
  return !!field.autoFormula || (currentState.value?.formulaOverrides[field.id] != null);
}

function isManualOverride(field: FieldDef, year: number): boolean {
  return !!currentState.value?.manualFlags[field.id]?.[year];
}

// ─── Calculator integration ────────────────────────────────────
const calcResult = computed(() => {
  if (!calc.expression.value.trim()) return { value: null, error: null };
  const year = focusedCell.value?.year ?? years.value[years.value.length - 1];
  return safeEvalExpression(calc.expression.value, cellMatrix.value, year);
});

function onCellClickToCalc(field: FieldDef, year: number, evt: MouseEvent) {
  // Alt+click adds cell ref to calculator instead of focusing for edit
  if (evt.altKey) {
    evt.preventDefault();
    calc.appendCellRef(field.id, year);
  }
}

function applyCalcResult() {
  const r = calcResult.value;
  if (r.value == null) {
    toast.info(r.error || "Калькулятор: нечего подставить");
    return;
  }
  if (!calc.targetField.value || calc.targetYear.value == null) {
    toast.info("Выбери целевую ячейку в таблице");
    return;
  }
  const state = currentState.value;
  if (!state) return;
  const field = displaySchema.value
    .flatMap((s) => s.fields)
    .find((f) => f.id === calc.targetField.value);
  if (!field) return;

  if (!state.values[field.id]) state.values[field.id] = {};
  state.values[field.id][calc.targetYear.value!] = r.value;
  if (field.autoFormula) {
    if (!state.manualFlags[field.id]) state.manualFlags[field.id] = {};
    state.manualFlags[field.id][calc.targetYear.value!] = true;
  }
  calc.recordHistory(r.value);
  state.dirty = true;
  recomputeAutoFields();
  scheduleBackup();
  toast.success(`Подставлено ${formatNumber(r.value)} в ${getFieldLabel(field)} / ${calc.targetYear.value}`);
}

function calcOp(token: string) { calc.appendToExpression(token); }
function calcFn(fn: string) {
  const year = focusedCell.value?.year ?? years.value[years.value.length - 1];
  const placeholders: Record<string, string> = {
    GROWTH: `GROWTH(revenue.${year}, revenue.${year - 1})`,
    CAGR: `CAGR(revenue.${year - 3}, revenue.${year}, 3)`,
    MARGIN: `MARGIN(opProfit.${year})`,
    AVG: `AVG(revenue.${year}, revenue.${year - 1})`,
  };
  calc.appendToExpression(" " + placeholders[fn]);
}

// ─── Custom field operations ───────────────────────────────────
function addCustomField() {
  const state = currentState.value;
  if (!state) return;
  const label = newFieldDraft.value.label.trim();
  if (!label) { toast.info("Введи название показателя"); return; }
  const id = `__custom_${newFieldDraft.value.section}_${Date.now()}`;
  const formula = newFieldDraft.value.formula.trim();
  const canonical = newFieldDraft.value.canonical.trim();
  const newField: FieldDef = {
    id,
    label,
    isCustom: true,
  };
  if (canonical) newField.canonical = canonical;
  if (formula) {
    state.formulaOverrides[id] = formula;
    (newField as FieldDef & { autoFormula?: string }).autoFormula = "__custom__";
  }
  state.customFields.push(newField);
  state.dirty = true;
  showAddFieldDialog.value = false;
  newFieldDraft.value = { label: "", section: "pnl", formula: "", canonical: "" };
  recomputeAutoFields();
  scheduleBackup();
  toast.success(`Добавлен показатель «${label}»`);
}

function startEditCanonical(field: FieldDef) {
  editingCanonicalFieldId.value = field.id;
  canonicalDraft.value = getFieldCanonical(field) || "";
}

function commitCanonical() {
  const state = currentState.value;
  if (!state || !editingCanonicalFieldId.value) return;
  const newCanonical = canonicalDraft.value.trim();
  const customIdx = state.customFields.findIndex((f) => f.id === editingCanonicalFieldId.value);
  if (customIdx >= 0) {
    if (newCanonical) {
      state.customFields[customIdx].canonical = newCanonical;
    } else {
      delete state.customFields[customIdx].canonical;
    }
    state.dirty = true;
    scheduleBackup();
    toast.success(newCanonical ? `Маппинг → ${newCanonical}` : "Маппинг снят");
  }
  editingCanonicalFieldId.value = null;
  canonicalDraft.value = "";
}

function cancelEditCanonical() {
  editingCanonicalFieldId.value = null;
  canonicalDraft.value = "";
}

function getFieldCanonical(field: FieldDef): string | undefined {
  if (field.canonical) return field.canonical;
  // For custom fields stored in state, the canonical might be set there
  const state = currentState.value;
  if (state) {
    const cf = state.customFields.find((f) => f.id === field.id);
    if (cf?.canonical) return cf.canonical;
  }
  return undefined;
}

// Pack 7.63: per-line notes/disclosures
function getFieldNote(field: FieldDef): string {
  const state = currentState.value;
  if (!state || !state.notes) return "";
  return state.notes[field.id] || "";
}

function hasNote(field: FieldDef): boolean {
  return getFieldNote(field).trim().length > 0;
}

function startEditNote(field: FieldDef) {
  editingNoteFieldId.value = field.id;
  noteDraft.value = getFieldNote(field);
}

function commitNote() {
  const state = currentState.value;
  if (!state || !editingNoteFieldId.value) return;
  const trimmed = noteDraft.value.trim();
  if (trimmed) {
    state.notes[editingNoteFieldId.value] = trimmed;
  } else {
    delete state.notes[editingNoteFieldId.value];
  }
  state.dirty = true;
  scheduleBackup();
  editingNoteFieldId.value = null;
  noteDraft.value = "";
}

function cancelEditNote() {
  editingNoteFieldId.value = null;
  noteDraft.value = "";
}

function startRename(field: FieldDef) {
  renamingFieldId.value = field.id;
  renameDraft.value = getFieldLabel(field);
}

function commitRename() {
  const state = currentState.value;
  if (!state || !renamingFieldId.value) return;
  const newLabel = renameDraft.value.trim();
  if (newLabel) {
    state.renames[renamingFieldId.value] = newLabel;
    state.dirty = true;
    scheduleBackup();
  }
  renamingFieldId.value = null;
  renameDraft.value = "";
}

function cancelRename() {
  renamingFieldId.value = null;
  renameDraft.value = "";
}

function startEditFormula(field: FieldDef) {
  editingFormulaFieldId.value = field.id;
  formulaDraft.value = getFieldFormula(field);
}

function commitFormula() {
  const state = currentState.value;
  if (!state || !editingFormulaFieldId.value) return;
  const expr = formulaDraft.value.trim();
  if (expr) {
    state.formulaOverrides[editingFormulaFieldId.value] = expr;
  } else {
    delete state.formulaOverrides[editingFormulaFieldId.value];
  }
  state.dirty = true;
  recomputeAutoFields();
  scheduleBackup();
  editingFormulaFieldId.value = null;
  formulaDraft.value = "";
  toast.success("Формула обновлена");
}

function cancelEditFormula() {
  editingFormulaFieldId.value = null;
  formulaDraft.value = "";
}

function removeCustomField(field: FieldDef) {
  const state = currentState.value;
  if (!state || !field.isCustom) return;
  if (!confirm(`Удалить показатель «${getFieldLabel(field)}»?`)) return;
  state.customFields = state.customFields.filter((f) => f.id !== field.id);
  delete state.values[field.id];
  delete state.renames[field.id];
  delete state.formulaOverrides[field.id];
  delete state.manualFlags[field.id];
  state.dirty = true;
  scheduleBackup();
}

// ─── Year management ───────────────────────────────────────────
function addYear() {
  const max = Math.max(...years.value);
  if (years.value.includes(max + 1)) return;
  years.value = [...years.value, max + 1].sort((a, b) => a - b);
}

// ─── Anti-loss backup ──────────────────────────────────────────
const BACKUP_KEY_PREFIX = "uza_nsbu_editor_";
let backupTimer: ReturnType<typeof setTimeout> | null = null;
let backupIntervalId: ReturnType<typeof setInterval> | null = null;

function scheduleBackup() {
  if (backupTimer) clearTimeout(backupTimer);
  backupTimer = setTimeout(doBackup, 1500);
}

function doBackup() {
  const code = selectedCode.value;
  if (!code) return;
  const state = companyStates[code];
  if (!state) return;
  // Pack 7.51.4: don't write completely empty backups — это блокировало пере-загрузку из БД.
  const hasAnyValue = Object.values(state.values).some(
    (yearMap) => yearMap && Object.values(yearMap).some((v) => v != null),
  );
  const hasCustomization =
    state.customFields.length > 0 ||
    Object.keys(state.renames).length > 0 ||
    Object.keys(state.formulaOverrides).length > 0 ||
    Object.keys(state.manualFlags).length > 0;
  if (!hasAnyValue && !hasCustomization) {
    // Empty state — purge old backup if any
    try { localStorage.removeItem(BACKUP_KEY_PREFIX + code); } catch { /* noop */ }
    return;
  }
  try {
    const payload = {
      values: state.values,
      customFields: state.customFields,
      renames: state.renames,
      formulaOverrides: state.formulaOverrides,
      manualFlags: state.manualFlags,
      savedAt: Date.now(),
    };
    localStorage.setItem(BACKUP_KEY_PREFIX + code, JSON.stringify(payload));
  } catch (e) {
    console.warn("[IfrsEditor] backup failed:", e);
  }
}

function restoreBackup(code: string): boolean {
  try {
    const raw = localStorage.getItem(BACKUP_KEY_PREFIX + code);
    if (!raw) return false;
    const parsed = JSON.parse(raw);

    // Pack 7.51.4: detect stale empty backup (from earlier versions) — auto-cleanup.
    const hasValues = parsed.values && Object.values(parsed.values).some(
      (yearMap: unknown) =>
        yearMap && typeof yearMap === "object" &&
        Object.values(yearMap as Record<string, unknown>).some((v) => v != null),
    );
    const hasCustomization =
      (parsed.customFields?.length || 0) > 0 ||
      Object.keys(parsed.renames || {}).length > 0 ||
      Object.keys(parsed.formulaOverrides || {}).length > 0 ||
      Object.keys(parsed.manualFlags || {}).length > 0;

    if (!hasValues && !hasCustomization) {
      // Stale empty backup — silently delete and let backend data show.
      localStorage.removeItem(BACKUP_KEY_PREFIX + code);
      return false;
    }

    // Merge mode: backup overlays on top of backend data (doesn't wipe loaded cells).
    const state = ensureState(code);
    if (parsed.values) {
      for (const field of Object.keys(parsed.values)) {
        if (!state.values[field]) state.values[field] = {};
        for (const yearStr of Object.keys(parsed.values[field])) {
          const v = parsed.values[field][yearStr];
          if (v != null) state.values[field][Number(yearStr)] = v;
        }
      }
    }
    if (parsed.customFields?.length) state.customFields = parsed.customFields;
    if (Object.keys(parsed.renames || {}).length) state.renames = { ...parsed.renames };
    if (Object.keys(parsed.formulaOverrides || {}).length) state.formulaOverrides = { ...parsed.formulaOverrides };
    if (Object.keys(parsed.manualFlags || {}).length) state.manualFlags = { ...parsed.manualFlags };
    state.savedAt = parsed.savedAt;
    state.dirty = false;
    return true;
  } catch (e) {
    console.warn("[IfrsEditor] restore failed:", e);
    return false;
  }
}

// ─── Data load ─────────────────────────────────────────────────
const portfolioCache = ref<PortfolioSummaryResponse | null>(null);

/** Load portfolio summary once, cache it. Returns null on error. */
async function loadPortfolio(): Promise<PortfolioSummaryResponse | null> {
  if (portfolioCache.value) return portfolioCache.value;
  try {
    const sumResp = await financialsApi.portfolioSummary({
      standard: "IFRS",
      years: years.value,
      currency: "UZS",
    });
    portfolioCache.value = sumResp;
    return sumResp;
  } catch (e) {
    console.error("[IfrsEditor] portfolio load failed:", e);
    toast.error("Не удалось загрузить данные портфеля из БД");
    return null;
  }
}

/** Populate state.values from portfolio summary for the given company. */
function applyBackendData(code: string, summary: PortfolioSummaryResponse) {
  const state = ensureState(code);
  // Backend returns canonical metric codes (revenue/opProfit/etc.) — same as our schema field IDs.
  // Values are in raw UZS (already converted from row.currency on backend), divide by 1e9 for млрд.
  const item = summary.items?.find((i) => i.company_code.toLowerCase() === code.toLowerCase());
  if (!item) return;
  for (const [yearStr, fields] of Object.entries(item.by_year)) {
    const year = Number(yearStr);
    for (const [field, value] of Object.entries(fields)) {
      if (value == null || !isFinite(value as number)) continue;
      if (!state.values[field]) state.values[field] = {};
      state.values[field][year] = (value as number) / 1_000_000_000;
    }
  }
}

async function loadCompanies() {
  try {
    loadingList.value = true;
    // Load companies + portfolio summary in parallel
    const [coResp, sumResp] = await Promise.all([
      companiesApi.list({ limit: 200 }),
      loadPortfolio(),
    ]);
    companies.value = coResp.items || [];
    // Populate state for ALL companies that have data — это даёт preview в левом списке
    if (sumResp) {
      for (const item of sumResp.items || []) {
        applyBackendData(item.company_code, sumResp);
      }
    }
    if (companies.value.length && !selectedCode.value) {
      await selectCompany(companies.value[0].code);
    }
  } catch (e) {
    console.error("[IfrsEditor] load companies failed:", e);
    toast.error("Не удалось загрузить список компаний");
  } finally {
    loadingList.value = false;
  }
}

async function selectCompany(code: string) {
  selectedCode.value = code;
  ensureState(code);

  // Если данных backend ещё нет в state — загрузим
  const state = companyStates[code];
  const hasValues = Object.keys(state.values).length > 0;
  if (!hasValues) {
    loadingCompany.value = true;
    try {
      const summary = await loadPortfolio();
      if (summary) applyBackendData(code, summary);
    } finally {
      loadingCompany.value = false;
    }
  }

  // Pack 7.52: load customization (custom fields/renames/formula overrides) from backend
  try {
    const { api } = await import("@/api/client");
    const { data } = await api.get(`/financials/companies/${code}/ifrs-editor?period=${period.value}&consolidated=${consolidated.value}`);
    if (data) {
      if (Array.isArray(data.customFields) && data.customFields.length) {
        state.customFields = data.customFields;
      }
      if (data.renames && typeof data.renames === "object") {
        state.renames = { ...state.renames, ...data.renames };
      }
      if (data.formulaOverrides && typeof data.formulaOverrides === "object") {
        state.formulaOverrides = { ...state.formulaOverrides, ...data.formulaOverrides };
      }
      if (data.manualFlags && typeof data.manualFlags === "object") {
        state.manualFlags = { ...state.manualFlags, ...data.manualFlags };
      }
      // Pack 7.63: notes per field
      if (data.notes && typeof data.notes === "object") {
        state.notes = { ...state.notes, ...data.notes };
      }
      if (data.updatedAt) state.savedAt = new Date(data.updatedAt).getTime();
    }
  } catch (e) {
    console.warn("[IfrsEditor] customization load failed (non-fatal):", e);
  }

  // localStorage backup имеет приоритет — overlay on top (если есть несохранённые правки).
  // Просто перезатираем значения из backup'а — backup это полный snapshot.
  restoreBackup(code);

  recomputeAutoFields();
}

// ─── Save ──────────────────────────────────────────────────────
const saving = ref(false);

async function saveCurrent() {
  const state = currentState.value;
  if (!state || !selectedCode.value) return;
  if (saving.value) return;
  saving.value = true;
  try {
    // Always backup to localStorage first (anti-loss: PUT could fail)
    doBackup();
    // Prepare payload — null values stay null (server will delete those lines)
    // Pack 7.60: section detection now supports 4 sections (pnl/oci/sofp/cf)
    function detectCustomSection(id: string): string {
      if (id.startsWith("__custom_pnl_")) return "pnl";
      if (id.startsWith("__custom_oci_")) return "oci";
      if (id.startsWith("__custom_sofp_")) return "sofp";
      if (id.startsWith("__custom_cf_")) return "cf";
      return "pnl"; // fallback
    }
    const payload = {
      period: period.value,
      consolidated: consolidated.value,
      currency: "UZS",
      values: state.values,
      customFields: state.customFields.map((f) => ({
        id: f.id,
        label: f.label,
        section: detectCustomSection(f.id),
        autoFormula: (f as FieldDef & { autoFormula?: string }).autoFormula,
        canonical: f.canonical,
        isCustom: true,
      })),
      renames: state.renames,
      formulaOverrides: state.formulaOverrides,
      manualFlags: state.manualFlags,
      notes: state.notes,
    };
    // Use raw api client (no wrapper exists for this endpoint yet)
    const { api } = await import("@/api/client");
    const resp = await api.put(`/financials/companies/${selectedCode.value}/ifrs-editor`, payload);
    state.dirty = false;
    state.savedAt = Date.now();
    // Verify after save: re-read the schema (defense-in-depth, mem #10 pattern)
    try {
      const verify = await api.get(`/financials/companies/${selectedCode.value}/ifrs-editor?period=${period.value}&consolidated=${consolidated.value}`);
      if (verify?.data?.updatedAt) {
        // Server confirmed — backup is now redundant for this company.
        // Keep it though, in case backend is rolled back; cleanup happens on next select.
      }
    } catch { /* verify is best-effort */ }
    const d = resp.data as { reports_created: number; reports_updated: number; lines_upserted: number; lines_deleted: number };
    toast.success(
      `Сохранено · отчётов: ${d.reports_created + d.reports_updated} · строк: ${d.lines_upserted}${d.lines_deleted ? ` · удалено: ${d.lines_deleted}` : ""}`,
    );
    // Invalidate portfolio cache so dashboards reflect saved changes next load
    portfolioCache.value = null;
  } catch (e: unknown) {
    const err = e as { response?: { data?: { detail?: string } }; message?: string };
    const msg = err?.response?.data?.detail || err?.message || "Не удалось сохранить";
    toast.error(`Ошибка сохранения: ${msg}`);
    console.error("[IfrsEditor] save failed:", e);
  } finally {
    saving.value = false;
  }
}

function revertCurrent() {
  if (!selectedCode.value) return;
  if (!confirm("Откатить несохранённые изменения?")) return;
  restoreBackup(selectedCode.value);
  recomputeAutoFields();
}

// ─── Lifecycle ─────────────────────────────────────────────────
let prevOverflow = "";

/** Pack 7.51.4: one-time sweep — remove any empty stale backups from previous versions. */
function cleanupStaleBackups() {
  try {
    const toRemove: string[] = [];
    for (let i = 0; i < localStorage.length; i++) {
      const key = localStorage.key(i);
      if (!key || !key.startsWith(BACKUP_KEY_PREFIX)) continue;
      try {
        const raw = localStorage.getItem(key);
        if (!raw) { toRemove.push(key); continue; }
        const parsed = JSON.parse(raw);
        const hasValues = parsed.values && Object.values(parsed.values).some(
          (ym: unknown) => ym && typeof ym === "object" &&
            Object.values(ym as Record<string, unknown>).some((v) => v != null),
        );
        const hasCust =
          (parsed.customFields?.length || 0) > 0 ||
          Object.keys(parsed.renames || {}).length > 0 ||
          Object.keys(parsed.formulaOverrides || {}).length > 0 ||
          Object.keys(parsed.manualFlags || {}).length > 0;
        if (!hasValues && !hasCust) toRemove.push(key);
      } catch {
        toRemove.push(key);
      }
    }
    for (const k of toRemove) localStorage.removeItem(k);
    if (toRemove.length) {
      console.info(`[IfrsEditor] cleaned up ${toRemove.length} stale empty backups`);
    }
  } catch (e) {
    console.warn("[IfrsEditor] cleanup failed:", e);
  }
}

onMounted(() => {
  prevOverflow = document.body.style.overflow;
  document.body.style.overflow = "hidden";
  cleanupStaleBackups();
  void loadCompanies();
  backupIntervalId = setInterval(doBackup, 20_000);
  window.addEventListener("keydown", onKeyDown);
});
onUnmounted(() => {
  document.body.style.overflow = prevOverflow;
  if (backupIntervalId) clearInterval(backupIntervalId);
  if (backupTimer) clearTimeout(backupTimer);
  window.removeEventListener("keydown", onKeyDown);
});

function onKeyDown(e: KeyboardEvent) {
  if (e.key === "Escape") { close(); }
  if (e.key === "Enter" && renamingFieldId.value) { commitRename(); }
  if (e.key === "Escape" && renamingFieldId.value) { cancelRename(); }
}

function close() {
  // Check for unsaved changes
  const anyDirty = Object.values(companyStates).some((s) => s.dirty);
  if (anyDirty && !confirm("Есть несохранённые изменения. Закрыть всё равно?")) return;
  emit("close");
  // If we're accessed via route, navigate back to financials
  try {
    const rn = router.currentRoute.value.name;
    if (rn === "financials-edit-ifrs" || rn === "financials-edit-nsbu") {
      router.push({ name: "financials" });
    }
  } catch { /* noop */ }
}

// ─── Pack 7.53: Excel import ───────────────────────────────────
const importing = ref(false);
const importPreview = ref<{
  filename: string;
  fields_count: number;
  cells_count: number;
  values: Record<string, Record<string, number>>;
  log: string[];
} | null>(null);
const fileInputRef = ref<HTMLInputElement | null>(null);

async function downloadTemplate() {
  if (!selectedCode.value) {
    toast.error("Выбери компанию");
    return;
  }
  try {
    const { api } = await import("@/api/client");
    const yearsParam = years.value.join(",");
    const resp = await api.get(
      `/financials/companies/${selectedCode.value}/ifrs-editor/template?years=${yearsParam}&period=${period.value}&consolidated=${consolidated.value}`,
      { responseType: "blob" },
    );
    const blob = new Blob([resp.data], { type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `ifrs_template_${selectedCode.value}_${period.value}_${consolidated.value ? "cons" : "stand"}.xlsx`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
    toast.success("Шаблон МСФО скачан");
  } catch (e) {
    console.error("[IfrsEditor] template download failed:", e);
    toast.error("Не удалось скачать шаблон");
  }
}

function pickFile() {
  if (!selectedCode.value) {
    toast.error("Выбери компанию");
    return;
  }
  fileInputRef.value?.click();
}

async function onFileChange(evt: Event) {
  const input = evt.target as HTMLInputElement;
  const file = input.files?.[0];
  if (!file) return;
  if (!selectedCode.value) return;

  importing.value = true;
  try {
    const fd = new FormData();
    fd.append("file", file);
    const { api } = await import("@/api/client");
    const resp = await api.post(
      `/financials/companies/${selectedCode.value}/ifrs-editor/parse-excel`,
      fd,
      { headers: { "Content-Type": "multipart/form-data" } },
    );
    importPreview.value = resp.data;
    if ((resp.data.cells_count || 0) === 0) {
      toast.error("В файле не распознано ни одного значения. Используй скачанный шаблон.");
    }
  } catch (e: unknown) {
    const err = e as { response?: { data?: { detail?: string } }; message?: string };
    const msg = err?.response?.data?.detail || err?.message || "Ошибка парсинга";
    toast.error(`Импорт не удался: ${msg}`);
    console.error("[IfrsEditor] import failed:", e);
  } finally {
    importing.value = false;
    if (input) input.value = ""; // reset so same file can be re-selected
  }
}

function applyImportPreview() {
  const preview = importPreview.value;
  const state = currentState.value;
  if (!preview || !state) return;

  let applied = 0;
  for (const [field, yearMap] of Object.entries(preview.values)) {
    if (!state.values[field]) state.values[field] = {};
    for (const [yearStr, val] of Object.entries(yearMap)) {
      const year = Number(yearStr);
      state.values[field][year] = val;
      applied += 1;
      // If field has autoFormula and got a value → mark manual
      const fieldDef = displaySchema.value
        .flatMap((s) => s.fields)
        .find((f) => f.id === field);
      if (fieldDef?.autoFormula) {
        if (!state.manualFlags[field]) state.manualFlags[field] = {};
        state.manualFlags[field][year] = true;
      }
    }
  }
  state.dirty = true;
  recomputeAutoFields();
  scheduleBackup();
  importPreview.value = null;
  toast.success(`Применено ${applied} значений. Нажми «Сохранить» для записи в БД.`);
}

function cancelImportPreview() {
  importPreview.value = null;
}

// ─── Helpers for template ──────────────────────────────────────
function companyStatusColor(c: CompanyListItem): string {
  const state = companyStates[c.code];
  if (!state) return "#94A3B8";
  const hasValues = Object.keys(state.values).length > 0;
  if (!hasValues) return "#94A3B8";
  // Count years with any data
  let yearCount = 0;
  for (const y of years.value) {
    if (Object.values(state.values).some((fv) => fv[y] != null)) yearCount++;
  }
  if (yearCount >= 5) return "#1D9E75";
  if (yearCount >= 3) return "#EF9F27";
  return "#E24B4A";
}

function companyYearSummary(c: CompanyListItem): string {
  const state = companyStates[c.code];
  if (!state) return "—";
  let yearCount = 0;
  for (const y of years.value) {
    if (Object.values(state.values).some((fv) => fv[y] != null)) yearCount++;
  }
  if (yearCount === 0) return "нет данных";
  return `${yearCount} ${yearCount === 1 ? "год" : yearCount < 5 ? "года" : "лет"}`;
}

const dirtyCount = computed(() =>
  Object.values(companyStates).filter((s) => s.dirty).length,
);

// Pack 7.60: when period or consolidated changes — clear state for current company and reload
watch([period, consolidated], async () => {
  if (selectedCode.value) {
    delete companyStates[selectedCode.value];
    await selectCompany(selectedCode.value);
  }
});

const sectionTabs = computed(() =>
  STANDARD_SCHEMA.map((s) => ({ id: s.id, label: s.label })),
);

// Pack 7.55: history side panel
interface HistoryEntry {
  id: string;
  at: string | null;
  actor_email: string | null;
  diff: Record<string, unknown>;
  payload: Record<string, unknown>;
  notes: string | null;
}
const historyOpen = ref(false);
const historyLoading = ref(false);
const historyEntries = ref<HistoryEntry[]>([]);

// Pack 7.56: kebab menu — all editor actions live behind ⋯ in topbar
const menuOpen = ref(false);
function toggleMenu() { menuOpen.value = !menuOpen.value; }
function closeMenu() { menuOpen.value = false; }
function onMenuAction(fn: () => void | Promise<void>) {
  closeMenu();
  void fn();
}

// Pack 7.57: company-pane (sidebar) collapse with animation + localStorage persist
const NS_COPANE_KEY = "uz_ifrs_copane_collapsed_v1";
const coPaneCollapsed = ref<boolean>(
  (() => { try { return localStorage.getItem(NS_COPANE_KEY) === "true"; } catch { return false; } })(),
);
function toggleCoPane() {
  coPaneCollapsed.value = !coPaneCollapsed.value;
  try { localStorage.setItem(NS_COPANE_KEY, String(coPaneCollapsed.value)); } catch { /* noop */ }
}

async function openHistory() {
  if (!selectedCode.value) { toast.error("Выбери компанию"); return; }
  historyOpen.value = true;
  historyLoading.value = true;
  try {
    const { api } = await import("@/api/client");
    const resp = await api.get(`/financials/companies/${selectedCode.value}/ifrs-editor/history?limit=50`);
    historyEntries.value = resp.data?.entries || [];
  } catch (e) {
    console.error("[IfrsEditor] history load failed:", e);
    toast.error("Не удалось загрузить историю");
  } finally {
    historyLoading.value = false;
  }
}

function closeHistory() {
  historyOpen.value = false;
}

function formatHistoryDate(iso: string | null): string {
  if (!iso) return "—";
  try {
    return new Date(iso).toLocaleString("ru", {
      day: "2-digit", month: "2-digit", year: "numeric",
      hour: "2-digit", minute: "2-digit",
    });
  } catch { return iso; }
}

// Pack 7.62: NSBU↔IFRS reconciliation drawer
interface DiffRow {
  metric: string;
  label: string;
  nsbu_value: number | null;
  ifrs_value: number | null;
  delta: number;
  delta_pct: number | null;
  significance: "low" | "medium" | "high" | "ifrs_only" | "nsbu_only";
}
interface DiffSummary { high: number; medium: number; low: number; ifrs_only: number; nsbu_only: number; }
const reconOpen = ref(false);
const reconLoading = ref(false);
const reconYear = ref<number>(2024);
const reconDiffs = ref<DiffRow[]>([]);
const reconSummary = ref<DiffSummary>({ high: 0, medium: 0, low: 0, ifrs_only: 0, nsbu_only: 0 });

async function openRecon() {
  if (!selectedCode.value) { toast.error("Выбери компанию"); return; }
  reconOpen.value = true;
  await loadRecon();
}

async function loadRecon() {
  if (!selectedCode.value) return;
  reconLoading.value = true;
  try {
    const { api } = await import("@/api/client");
    const resp = await api.get(
      `/financials/companies/${selectedCode.value}/ifrs-nsbu-diff?year=${reconYear.value}&consolidated=${consolidated.value}`,
    );
    reconDiffs.value = resp.data?.diffs || [];
    reconSummary.value = resp.data?.summary || { high: 0, medium: 0, low: 0, ifrs_only: 0, nsbu_only: 0 };
  } catch (e) {
    console.error("[IfrsEditor] reconciliation load failed:", e);
    toast.error("Не удалось загрузить сверку");
    reconDiffs.value = [];
  } finally {
    reconLoading.value = false;
  }
}

function closeRecon() {
  reconOpen.value = false;
}

function fmtReconNum(v: number | null): string {
  if (v == null) return "—";
  return v.toLocaleString("ru", { maximumFractionDigits: 1 });
}

function fmtReconPct(v: number | null): string {
  if (v == null) return "—";
  const sign = v > 0 ? "+" : "";
  return `${sign}${v.toFixed(1)}%`;
}

watch(reconYear, () => { if (reconOpen.value) loadRecon(); });

watch(focusedCell, () => {
  // When focused cell changes, update calculator target
  if (focusedCell.value) {
    calc.setTarget(focusedCell.value.field, focusedCell.value.year);
  }
});
</script>

<template>
  <div class="ne-bd" @click.self="close" role="dialog" aria-modal="true">
      <div class="ne-card">
        <div class="ne-stripe" />

        <!-- Header -->
        <div class="ne-hdr">
          <div class="ne-hdr-left">
            <div class="ne-eyebrow">РЕДАКТОР ФИНАНСОВ · МСФО</div>
            <div class="ne-title">Редактирование показателей МСФО</div>
            <div class="ne-sub">
              млрд UZS · до 3 знаков · поля <strong>(+)</strong> — без минуса ·
              <span v-if="dirtyCount > 0" style="color:#EF9F27">{{ dirtyCount }} компаний с несохранёнными правками</span>
              <span v-else style="color:#1D9E75">все изменения сохранены</span>
            </div>
          </div>
          <div class="ne-hdr-center">
            <!-- Pack 7.60: period selector (FY default for current data; Q1/H1/9M for future quarterly entry) -->
            <div class="ne-pgrp" role="tablist" aria-label="Период отчётности">
              <button v-for="p in (['FY','Q1','H1','9M'] as const)" :key="p"
                      class="ne-pill" :class="{ on: period === p }"
                      :title="p === 'FY' ? 'Год · annual' : p === 'Q1' ? 'I квартал' : p === 'H1' ? 'Полугодие · 6 мес.' : 'Девять месяцев'"
                      @click="period = p">{{ p }}</button>
            </div>
            <!-- Pack 7.60: consolidated vs standalone scope -->
            <div class="ne-pgrp" role="tablist" aria-label="Контур отчётности">
              <button class="ne-pill" :class="{ on: consolidated }"
                      title="Consolidated · группа в целом (значение по умолчанию для всех существующих данных)"
                      @click="consolidated = true">Cons.</button>
              <button class="ne-pill" :class="{ on: !consolidated }"
                      title="Standalone · только материнская/отдельная компания"
                      @click="consolidated = false">Stand.</button>
            </div>
          </div>
          <div class="ne-hdr-actions">
            <div class="ne-menu-wrap">
              <button class="ne-btn-kebab" :class="{ on: menuOpen }" @click.stop="toggleMenu" :disabled="!selectedCode" title="Действия">
                <svg viewBox="0 0 14 14" width="14" height="14" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round">
                  <circle cx="7" cy="3" r="0.8" fill="currentColor" stroke="none"/>
                  <circle cx="7" cy="7" r="0.8" fill="currentColor" stroke="none"/>
                  <circle cx="7" cy="11" r="0.8" fill="currentColor" stroke="none"/>
                </svg>
              </button>
              <div v-if="menuOpen" class="ne-menu-bg" @click="closeMenu"></div>
              <div v-if="menuOpen" class="ne-menu">
                <button class="ne-menu-item" @click="onMenuAction(openHistory)">
                  <svg viewBox="0 0 14 14" width="13" height="13" fill="none" stroke="currentColor" stroke-width="1.6"><circle cx="7" cy="7" r="5.5"/><path d="M7 4v3l2 2"/></svg>
                  История правок
                </button>
                <button class="ne-menu-item" @click="onMenuAction(openRecon)">
                  <svg viewBox="0 0 14 14" width="13" height="13" fill="none" stroke="currentColor" stroke-width="1.6"><path d="M3 4h8M3 7h8M3 10h8M7 2v10"/></svg>
                  Сверка с НСБУ
                </button>
                <button class="ne-menu-item" @click="onMenuAction(downloadTemplate)">
                  <svg viewBox="0 0 14 14" width="13" height="13" fill="none" stroke="currentColor" stroke-width="1.6"><path d="M2 12h10M7 2v8M3 7l4 3 4-3"/></svg>
                  Скачать шаблон XLSX
                </button>
                <button class="ne-menu-item" @click="onMenuAction(pickFile)" :disabled="importing">
                  <svg viewBox="0 0 14 14" width="13" height="13" fill="none" stroke="currentColor" stroke-width="1.6"><path d="M7 1v9M3 6l4 4 4-4M2 12h10"/></svg>
                  <template v-if="importing">Парсинг…</template>
                  <template v-else>Импорт Excel</template>
                </button>
              </div>
            </div>
            <input ref="fileInputRef" type="file" accept=".xlsx,.xls" style="display:none" @change="onFileChange" />
            <button class="ne-btn-x" @click="close">×</button>
          </div>
        </div>


        <!-- Body -->
        <div class="ne-body">

          <!-- LEFT: company list (collapsible) -->
          <div class="ne-co-pane" :class="{ collapsed: coPaneCollapsed }">
            <div class="ne-co-search">
              <input v-model="searchQuery" placeholder="Поиск компании…" />
            </div>
            <div class="ne-co-list">
              <div v-if="loadingList" class="ne-empty">Загрузка…</div>
              <div v-else-if="!filteredCompanies.length" class="ne-empty">Не найдено</div>
              <div
                v-for="c in filteredCompanies"
                :key="c.code"
                class="ne-co-row"
                :class="{ active: c.code === selectedCode }"
                :style="{ borderLeftColor: companyStatusColor(c) }"
                :title="coPaneCollapsed ? `${c.code} · ${c.name_short || c.name_ru}` : ''"
                @click="selectCompany(c.code)"
              >
                <div class="ne-co-code">{{ c.code }}</div>
                <div class="ne-co-name">{{ c.name_short || c.name_ru }}</div>
                <div class="ne-co-sub">
                  {{ companyYearSummary(c) }}
                  <span v-if="companyStates[c.code]?.dirty" class="ne-co-dirty">•</span>
                </div>
              </div>
            </div>
          </div>

          <!-- Floating sidebar toggle (Pack 7.57) -->
          <button
            class="ne-sb-toggle"
            :class="{ collapsed: coPaneCollapsed }"
            @click="toggleCoPane"
            :title="coPaneCollapsed ? 'Развернуть список' : 'Свернуть список'"
          >
            <svg viewBox="0 0 16 16" width="13" height="13" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
              <path d="M10 4 L6 8 L10 12"/>
            </svg>
          </button>

          <!-- CENTER: editor -->
          <div class="ne-edit-pane">
            <div v-if="!currentCompany" class="ne-empty">Выбери компанию слева</div>
            <template v-else>
              <!-- Company header -->
              <div class="ne-co-hdr">
                <div class="ne-co-hdr-stripe"></div>
                <div class="ne-co-hdr-info">
                  <div class="ne-co-hdr-name">{{ currentCompany.name_short || currentCompany.name_ru }}</div>
                  <div class="ne-co-hdr-meta">
                    {{ currentCompany.sector_code || "—" }} · {{ currentCompany.code }}
                    <span v-if="companyStates[selectedCode]?.savedAt">
                      · сохранено {{ new Date(companyStates[selectedCode]!.savedAt!).toLocaleString("ru") }}
                    </span>
                  </div>
                </div>
                <span class="ne-pill">МСФО</span>
              </div>

              <!-- Section tabs + actions -->
              <div class="ne-tabs-row">
                <button
                  v-for="t in sectionTabs"
                  :key="t.id"
                  class="ne-tab"
                  :class="{ on: t.id === selectedSection }"
                  @click="selectedSection = t.id"
                >{{ t.label }}</button>
                <div class="ne-spc"></div>
                <button class="ne-btn-ghost" @click="addYear">+ Год</button>
                <button class="ne-btn-ghost" @click="showAddFieldDialog = true; newFieldDraft.section = selectedSection">+ Показатель</button>
              </div>

              <!-- Add field dialog -->
              <div v-if="showAddFieldDialog" class="ne-dlg-bg" @click.self="showAddFieldDialog = false">
                <div class="ne-dlg">
                  <div class="ne-dlg-hdr">Новый показатель</div>
                  <div class="ne-dlg-row">
                    <label>Название</label>
                    <input v-model="newFieldDraft.label" placeholder="Например, «Дивидендная доходность»" />
                  </div>
                  <div class="ne-dlg-row">
                    <label>Секция</label>
                    <select v-model="newFieldDraft.section">
                      <option value="pnl">ОФР</option>
                      <option value="sofp">Баланс</option>
                    </select>
                  </div>
                  <div class="ne-dlg-row">
                    <label>Формула (опционально)</label>
                    <input v-model="newFieldDraft.formula" placeholder="например: profit / revenue * 100" />
                    <div class="ne-dlg-hint">
                      Можно ссылаться на ячейки как <code>field.year</code> или использовать функции
                      <code>GROWTH/CAGR/MARGIN/AVG</code>. Если пусто — поле будет ручным.
                    </div>
                  </div>
                  <div class="ne-dlg-row">
                    <label>Маппинг к портфельному KPI (опционально)</label>
                    <select v-model="newFieldDraft.canonical">
                      <option value="">— не учитывать в портфельных KPI —</option>
                      <optgroup label="ОФР">
                        <option v-for="m in CANONICAL_METRICS.filter(c => c.section === 'pnl')" :key="m.code" :value="m.code">
                          {{ m.label }} · {{ m.code }}
                        </option>
                      </optgroup>
                      <optgroup label="Баланс">
                        <option v-for="m in CANONICAL_METRICS.filter(c => c.section === 'sofp')" :key="m.code" :value="m.code">
                          {{ m.label }} · {{ m.code }}
                        </option>
                      </optgroup>
                    </select>
                    <div class="ne-dlg-hint">
                      Если выбрать — значения поля будут учитываться в портфельных
                      агрегациях (Дашборд, Financials KPI карточки) как указанная метрика.
                    </div>
                  </div>
                  <div class="ne-dlg-ftr">
                    <button class="ne-btn-g" @click="showAddFieldDialog = false">Отмена</button>
                    <button class="ne-btn-p" @click="addCustomField">Добавить</button>
                  </div>
                </div>
              </div>

              <!-- Pack 7.53: Import preview modal -->
              <div v-if="importPreview" class="ne-dlg-bg" @click.self="cancelImportPreview">
                <div class="ne-dlg ne-dlg-wide">
                  <div class="ne-dlg-hdr">Предпросмотр импорта · {{ importPreview.filename }}</div>
                  <div class="ne-imp-summary">
                    <div class="ne-imp-stat">
                      <div class="ne-imp-stat-val">{{ importPreview.fields_count }}</div>
                      <div class="ne-imp-stat-lbl">показателей</div>
                    </div>
                    <div class="ne-imp-stat">
                      <div class="ne-imp-stat-val">{{ importPreview.cells_count }}</div>
                      <div class="ne-imp-stat-lbl">значений</div>
                    </div>
                  </div>
                  <div v-if="importPreview.cells_count > 0" class="ne-imp-table-wrap">
                    <table class="ne-imp-table">
                      <thead>
                        <tr>
                          <th>Показатель</th>
                          <th v-for="y in years" :key="y">{{ y }}</th>
                        </tr>
                      </thead>
                      <tbody>
                        <tr v-for="(yearMap, field) in importPreview.values" :key="field">
                          <td class="ne-imp-fld">{{ field }}</td>
                          <td v-for="y in years" :key="y" class="ne-imp-val">
                            <template v-if="yearMap[String(y)] != null">{{ formatNumber(yearMap[String(y)]) }}</template>
                            <span v-else class="ne-imp-empty">—</span>
                          </td>
                        </tr>
                      </tbody>
                    </table>
                  </div>
                  <div v-if="importPreview.log?.length" class="ne-imp-log">
                    <div class="ne-imp-log-hdr">Лог парсинга</div>
                    <div v-for="(line, i) in importPreview.log" :key="i" class="ne-imp-log-line">{{ line }}</div>
                  </div>
                  <div class="ne-dlg-hint">
                    Значения попадут в редактор в текущем состоянии (не сохраняются в БД до клика «Сохранить»).
                    Существующие значения для тех же ячеек будут перезаписаны.
                  </div>
                  <div class="ne-dlg-ftr">
                    <button class="ne-btn-g" @click="cancelImportPreview">Отмена</button>
                    <button class="ne-btn-p" :disabled="importPreview.cells_count === 0" @click="applyImportPreview">
                      Применить ({{ importPreview.cells_count }})
                    </button>
                  </div>
                </div>
              </div>

              <!-- Grid -->
              <div class="ne-grid-wrap">
                <table class="ne-grid">
                  <thead>
                    <tr>
                      <th style="width:260px">Показатель</th>
                      <th v-for="y in years" :key="y" :class="{ 'cur-year': y === 2024 }">{{ y }}</th>
                      <th style="width:34px"></th>
                    </tr>
                  </thead>
                  <tbody>
                    <template v-for="field in currentSectionDef.fields" :key="field.id">
                      <tr v-if="field.groupHeader">
                        <td :colspan="years.length + 2" class="ne-group-hdr">{{ field.groupHeader }}</td>
                      </tr>
                      <tr :class="{ 'ne-row-auto': isAutoField(field), 'ne-row-sub': field.isSubtotal && !isAutoField(field) }">
                        <td class="ne-row-label">
                          <template v-if="renamingFieldId === field.id">
                            <input v-model="renameDraft" @blur="commitRename" @keyup.enter="commitRename" @keyup.escape="cancelRename" ref="renameInputRef" class="ne-rename-inp" autofocus />
                          </template>
                          <template v-else>
                            <span v-if="field.nsbuCode" class="ne-nsbu-code">{{ field.nsbuCode }}</span>
                            <span v-if="isAutoField(field)" class="ne-auto-badge" :title="getFieldFormula(field)">авто</span>
                            <span v-if="field.isCustom" class="ne-custom-badge">custom</span>
                            <span
                              v-if="field.isCustom && getFieldCanonical(field)"
                              class="ne-canon-badge"
                              :title="`Учитывается в портфельных KPI как «${getFieldCanonical(field)}». Кликни — изменить.`"
                              @click="startEditCanonical(field)"
                            >→ {{ getFieldCanonical(field) }}</span>
                            <span class="ne-row-name" @dblclick="startRename(field)" :title="'Двойной клик — переименовать'">{{ getFieldLabel(field) }}</span>
                            <span v-if="field.positiveOnly" class="ne-pos-hint">(+)</span>
                            <span v-if="getFieldFormula(field)" class="ne-formula-hint" @click="startEditFormula(field)" :title="'Кликни — редактировать формулу'">= {{ getFieldFormula(field) }}</span>
                            <button
                              class="ne-note-btn"
                              :class="{ 'has-note': hasNote(field) }"
                              @click="startEditNote(field)"
                              :title="hasNote(field) ? `Примечание: ${getFieldNote(field).slice(0, 80)}${getFieldNote(field).length > 80 ? '…' : ''}` : 'Добавить примечание / disclosure'"
                            >
                              <svg viewBox="0 0 14 14" width="11" height="11" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"><path d="M3 2h6l3 3v7H3V2z"/><path d="M9 2v3h3"/><path d="M5 8h4M5 10h3"/></svg>
                            </button>
                            <button
                              v-if="field.isCustom && !getFieldCanonical(field)"
                              class="ne-map-btn"
                              @click="startEditCanonical(field)"
                              title="Маппинг к портфельному KPI"
                            >+ маппинг</button>
                          </template>
                        </td>
                        <td v-for="y in years" :key="y" class="ne-cell">
                          <input
                            type="text"
                            :value="getDisplayCellValue(field, y)"
                            @input="onCellInput(field, y, ($event.target as HTMLInputElement).value)"
                            @focus="onCellFocus(field, y)"
                            @blur="onCellBlur"
                            @click="onCellClickToCalc(field, y, $event)"
                            :class="{
                              'ne-cell-auto': isAutoField(field) && !isManualOverride(field, y),
                              'ne-cell-manual': isManualOverride(field, y),
                              'ne-cell-sub': field.isSubtotal,
                              'ne-cell-target': calc.targetField.value === field.id && calc.targetYear.value === y,
                            }"
                            :title="isManualOverride(field, y) ? 'Ручное переопределение — клик правой кнопкой → вернуть авто' : ''"
                            @contextmenu.prevent="isAutoField(field) && isManualOverride(field, y) ? clearManualFlag(field, y) : null"
                            placeholder="—"
                          />
                        </td>
                        <td class="ne-row-actions">
                          <button v-if="field.isCustom" class="ne-row-x" @click="removeCustomField(field)" title="Удалить кастомное поле">×</button>
                        </td>
                      </tr>
                      <tr v-if="editingFormulaFieldId === field.id">
                        <td :colspan="years.length + 2" class="ne-formula-editor">
                          <div class="ne-formula-lbl">Формула для «{{ getFieldLabel(field) }}»:</div>
                          <input v-model="formulaDraft" placeholder="например: opProfit + |depreciation|" class="ne-formula-inp" />
                          <button class="ne-btn-g" @click="cancelEditFormula">Отмена</button>
                          <button class="ne-btn-p" @click="commitFormula">Применить</button>
                        </td>
                      </tr>
                      <tr v-if="editingNoteFieldId === field.id">
                        <td :colspan="years.length + 2" class="ne-note-editor">
                          <div class="ne-note-lbl">Примечание / disclosure для «{{ getFieldLabel(field) }}»:</div>
                          <textarea v-model="noteDraft"
                                    placeholder="Например: See Note 12 in audited IFRS report · обесценение списано после переоценки ОС в декабре 2024"
                                    class="ne-note-inp"
                                    rows="3"
                                    @keydown.escape="cancelEditNote"
                                    @keydown.ctrl.enter="commitNote"
                          ></textarea>
                          <div class="ne-note-ftr">
                            <span class="ne-note-hint">Ctrl+Enter — сохранить · Esc — отмена</span>
                            <button class="ne-btn-g" @click="cancelEditNote">Отмена</button>
                            <button class="ne-btn-p" @click="commitNote">Применить</button>
                          </div>
                        </td>
                      </tr>
                      <tr v-if="editingCanonicalFieldId === field.id">
                        <td :colspan="years.length + 2" class="ne-canon-editor">
                          <div class="ne-canon-lbl">Маппинг «{{ getFieldLabel(field) }}» → портфельная метрика:</div>
                          <select v-model="canonicalDraft" class="ne-canon-sel">
                            <option value="">— не учитывать в портфельных KPI —</option>
                            <optgroup label="ОФР">
                              <option v-for="m in CANONICAL_METRICS.filter(c => c.section === 'pnl')" :key="m.code" :value="m.code">{{ m.label }} · {{ m.code }}</option>
                            </optgroup>
                            <optgroup label="Баланс">
                              <option v-for="m in CANONICAL_METRICS.filter(c => c.section === 'sofp')" :key="m.code" :value="m.code">{{ m.label }} · {{ m.code }}</option>
                            </optgroup>
                          </select>
                          <button class="ne-btn-g" @click="cancelEditCanonical">Отмена</button>
                          <button class="ne-btn-p" @click="commitCanonical">Применить</button>
                        </td>
                      </tr>
                    </template>
                  </tbody>
                </table>
              </div>
            </template>
          </div>

          <!-- RIGHT: calculator -->
          <div class="ne-calc-pane">
            <div class="ne-calc-hdr">
              <svg viewBox="0 0 18 18" width="14" height="14" fill="none" stroke="#7F77DD" stroke-width="1.7"><rect x="3" y="2" width="12" height="14" rx="2"/><line x1="6" y1="6" x2="12" y2="6"/></svg>
              <div>
                <div class="ne-calc-title">Калькулятор</div>
                <div class="ne-calc-target">
                  <template v-if="calc.targetField.value && calc.targetYear.value">
                    → {{ calc.targetField.value }} / {{ calc.targetYear.value }}
                  </template>
                  <template v-else>выбери ячейку слева</template>
                </div>
              </div>
            </div>

            <div class="ne-calc-body">
              <div class="ne-calc-lbl">ВЫРАЖЕНИЕ</div>
              <textarea v-model="calc.expression.value" class="ne-calc-expr" placeholder="напр.: opProfit.2024 + finIncome.2024" rows="2"></textarea>
              <div class="ne-calc-hint">
                Alt+клик по ячейке слева → добавить ссылку
              </div>

              <div class="ne-calc-result" :class="{ err: calcResult.error }">
                <div class="ne-calc-lbl">РЕЗУЛЬТАТ</div>
                <div class="ne-calc-val">
                  <template v-if="calcResult.value != null">{{ formatNumber(calcResult.value) }}<span class="unit">млрд UZS</span></template>
                  <template v-else-if="calcResult.error"><span class="err-txt">{{ calcResult.error }}</span></template>
                  <template v-else><span class="placeholder">—</span></template>
                </div>
                <button class="ne-btn-apply" :disabled="calcResult.value == null || !calc.targetField.value" @click="applyCalcResult">
                  <svg viewBox="0 0 14 14" width="11" height="11" fill="none" stroke="currentColor" stroke-width="1.9"><path d="M3 7l3 3 5-6"/></svg>
                  Подставить
                </button>
              </div>

              <div class="ne-calc-lbl">ФИН-ФУНКЦИИ</div>
              <div class="ne-calc-fns">
                <button @click="calcFn('GROWTH')" title="(текущий − прошл.) / |прошл.| × 100">GROWTH</button>
                <button @click="calcFn('CAGR')" title="среднегодовой темп">CAGR</button>
                <button @click="calcFn('MARGIN')" title="x / выручка × 100">MARGIN</button>
                <button @click="calcFn('AVG')" title="среднее значений">AVG</button>
              </div>

              <div class="ne-calc-lbl">КЛАВИАТУРА</div>
              <div class="ne-calc-pad">
                <button @click="calc.clearExpression()" class="op">C</button>
                <button @click="calc.backspace()" class="op">⌫</button>
                <button @click="calcOp('(')" class="op">(</button>
                <button @click="calcOp(')')" class="op">)</button>
                <button @click="calcOp('7')">7</button>
                <button @click="calcOp('8')">8</button>
                <button @click="calcOp('9')">9</button>
                <button @click="calcOp(' / ')" class="op">÷</button>
                <button @click="calcOp('4')">4</button>
                <button @click="calcOp('5')">5</button>
                <button @click="calcOp('6')">6</button>
                <button @click="calcOp(' * ')" class="op">×</button>
                <button @click="calcOp('1')">1</button>
                <button @click="calcOp('2')">2</button>
                <button @click="calcOp('3')">3</button>
                <button @click="calcOp(' - ')" class="op">−</button>
                <button @click="calcOp('0')" class="span2">0</button>
                <button @click="calcOp(',')">,</button>
                <button @click="calcOp(' + ')" class="op">+</button>
              </div>

              <div v-if="calc.history.value.length" class="ne-calc-hist">
                <div class="ne-calc-lbl">ИСТОРИЯ</div>
                <div v-for="(h, i) in calc.history.value.slice(0, 5)" :key="i" class="ne-calc-hist-row" @click="calc.recallHistory(i)">
                  <span class="hexpr">{{ h.expression }}</span>
                  <span class="hres">= {{ formatNumber(h.result) }}</span>
                </div>
              </div>
            </div>
          </div>
        </div>

        <!-- Pack 7.55: history drawer -->
        <div v-if="historyOpen" class="ne-hist-drawer">
          <div class="ne-hist-hdr">
            <div>
              <div class="ne-hist-eyebrow">ИСТОРИЯ ПРАВОК</div>
              <div class="ne-hist-title">{{ currentCompany?.name_short || currentCompany?.code }}</div>
            </div>
            <button class="ne-btn-x" @click="closeHistory">×</button>
          </div>
          <div class="ne-hist-body">
            <div v-if="historyLoading" class="ne-empty">Загрузка…</div>
            <div v-else-if="!historyEntries.length" class="ne-empty">Сохранений ещё не было</div>
            <div v-else>
              <div v-for="e in historyEntries" :key="e.id" class="ne-hist-row">
                <div class="ne-hist-row-hdr">
                  <span class="ne-hist-date">{{ formatHistoryDate(e.at) }}</span>
                  <span class="ne-hist-actor">{{ e.actor_email || "—" }}</span>
                </div>
                <div class="ne-hist-row-stats">
                  <template v-if="(e.diff as any)?.lines_upserted">
                    <span class="ne-hist-pill ok">{{ (e.diff as any).lines_upserted }} значений</span>
                  </template>
                  <template v-if="(e.diff as any)?.lines_deleted">
                    <span class="ne-hist-pill warn">−{{ (e.diff as any).lines_deleted }} удалено</span>
                  </template>
                  <template v-if="(e.diff as any)?.reports_created">
                    <span class="ne-hist-pill">{{ (e.diff as any).reports_created }} новых отчёта</span>
                  </template>
                  <template v-if="((e.diff as any)?.years || []).length">
                    <span class="ne-hist-pill">годы: {{ ((e.diff as any).years || []).join(", ") }}</span>
                  </template>
                </div>
                <div v-if="((e.diff as any)?.fields || []).length" class="ne-hist-fields">
                  {{ ((e.diff as any).fields || []).join(" · ") }}
                </div>
              </div>
            </div>
          </div>
        </div>

        <!-- Pack 7.62: NSBU↔IFRS reconciliation drawer -->
        <div v-if="reconOpen" class="ne-hist-drawer ne-recon-drawer">
          <div class="ne-hist-hdr">
            <div>
              <div class="ne-hist-eyebrow">СВЕРКА НСБУ ↔ МСФО</div>
              <div class="ne-hist-title">{{ currentCompany?.name_short || currentCompany?.code }}</div>
            </div>
            <button class="ne-btn-x" @click="closeRecon">×</button>
          </div>
          <div class="ne-recon-filter">
            <label class="ne-recon-yearlbl">Год</label>
            <select v-model.number="reconYear" class="ne-recon-sel">
              <option v-for="y in years" :key="y" :value="y">{{ y }}</option>
            </select>
            <div class="ne-recon-summary">
              <span v-if="reconSummary.high > 0" class="ne-recon-pill high">⚠ {{ reconSummary.high }} крит.</span>
              <span v-if="reconSummary.medium > 0" class="ne-recon-pill medium">{{ reconSummary.medium }} замет.</span>
              <span v-if="reconSummary.low > 0" class="ne-recon-pill low">{{ reconSummary.low }} незнач.</span>
              <span v-if="reconSummary.ifrs_only + reconSummary.nsbu_only > 0" class="ne-recon-pill only">{{ reconSummary.ifrs_only + reconSummary.nsbu_only }} only</span>
            </div>
          </div>
          <div class="ne-hist-body">
            <div v-if="reconLoading" class="ne-empty">Расчёт расхождений…</div>
            <div v-else-if="!reconDiffs.length" class="ne-empty">
              Нет данных для сравнения за {{ reconYear }}.<br>
              Введи значения в МСФО редакторе и убедись что НСБУ показатели за этот год тоже есть.
            </div>
            <table v-else class="ne-recon-table">
              <thead>
                <tr>
                  <th>Показатель</th>
                  <th>НСБУ</th>
                  <th>МСФО</th>
                  <th>Δ</th>
                  <th>Δ%</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="d in reconDiffs" :key="d.metric" :class="`sig-${d.significance}`">
                  <td class="ne-recon-metric">
                    <span class="ne-recon-code">{{ d.metric }}</span>
                    <span class="ne-recon-label">{{ d.label }}</span>
                  </td>
                  <td class="ne-recon-val">{{ fmtReconNum(d.nsbu_value) }}</td>
                  <td class="ne-recon-val">{{ fmtReconNum(d.ifrs_value) }}</td>
                  <td class="ne-recon-val ne-recon-delta">{{ fmtReconNum(d.delta) }}</td>
                  <td class="ne-recon-val ne-recon-pct">
                    <template v-if="d.delta_pct != null">{{ fmtReconPct(d.delta_pct) }}</template>
                    <span v-else class="ne-recon-only-lbl">{{ d.significance === 'ifrs_only' ? 'только МСФО' : 'только НСБУ' }}</span>
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>

        <!-- Footer -->
        <div class="ne-ftr">
          <span class="ne-status">
            <span :style="{ color: dirtyCount ? '#EF9F27' : '#1D9E75' }">●</span>
            auto-backup в localStorage каждые 20с
            <template v-if="currentState?.dirty"> · есть несохранённые изменения</template>
          </span>
          <button class="ne-btn-g" @click="revertCurrent" :disabled="!currentState?.dirty">↺ Откатить</button>
          <button class="ne-btn-g" @click="close">Закрыть</button>
          <button v-if="_perm.canEdit.value" class="ne-btn-p" @click="saveCurrent" :disabled="!currentState?.dirty || saving">
            <template v-if="saving">Сохраняю…</template>
            <template v-else>Сохранить</template>
          </button>
          <span v-else style="font-size:11px;color:#888780;font-style:italic;">
            Только просмотр
          </span>
        </div>
      </div>
    </div>

</template>

<style scoped>
.ne-bd { position: fixed; inset: 0; background: rgba(15, 18, 40, .45); -webkit-backdrop-filter: blur(8px); backdrop-filter: blur(8px); z-index: 9000; display: flex; align-items: center; justify-content: center; padding: 12px; overflow: hidden; }
.ne-card { position: relative; background: #fff; border-radius: 14px; box-shadow: 0 24px 64px rgba(15, 23, 60, .22), 0 8px 24px rgba(15, 23, 60, .10); width: 100%; max-width: 1320px; height: 94vh; max-height: 920px; display: flex; flex-direction: column; overflow: hidden; }
.ne-stripe { position: absolute; top: 0; left: 0; right: 0; height: 3px; background: #7F77DD; z-index: 3; }

.ne-hdr { padding: 13px 20px; border-bottom: 1px solid #E2E8F0; display: flex; justify-content: space-between; align-items: center; gap: 12px; flex-shrink: 0; }
.ne-hdr-left { display: flex; flex-direction: column; min-width: 0; flex-shrink: 1; }
.ne-hdr-center { display: flex; gap: 10px; align-items: center; flex-shrink: 0; }
.ne-pgrp { display: inline-flex; gap: 2px; padding: 2px; background: #F1F5F9; border-radius: 8px; }
.ne-pill {
  padding: 5px 11px;
  font-size: 11px;
  font-weight: 500;
  border-radius: 6px;
  border: none;
  background: transparent;
  color: #64748B;
  cursor: pointer;
  transition: background 0.12s ease, color 0.12s ease;
  font-family: inherit;
  letter-spacing: 0;
}
.ne-pill:hover { background: rgba(127, 119, 221, 0.10); color: #534AB7; }
.ne-pill.on { background: #fff; color: #1E2A4A; box-shadow: 0 1px 2px rgba(15, 23, 60, 0.08); }
.ne-eyebrow { font-size: 10px; font-weight: 500; color: #888780; text-transform: uppercase; letter-spacing: .08em; }
.ne-title { font-size: 15px; font-weight: 500; color: #1E2A4A; margin-top: 2px; }
.ne-sub { font-size: 11px; color: #94A3B8; margin-top: 3px; }
.ne-sub strong { color: #7F77DD; }
.ne-hdr-actions { display: flex; gap: 6px; align-items: center; }
.ne-btn-sm { font-size: 10px; padding: 5px 11px; border-radius: 6px; border: 1px solid rgba(0,0,0,.08); background: #fff; color: #534AB7; cursor: pointer; font-weight: 500; display: inline-flex; gap: 5px; align-items: center; font-family: inherit; }
.ne-btn-sm:disabled { opacity: .5; cursor: not-allowed; }
.ne-btn-x { width: 28px; height: 28px; border-radius: 8px; border: none; background: #F1F5F9; cursor: pointer; color: #64748B; font-size: 15px; line-height: 1; }
.ne-btn-x:hover { background: #E2E8F0; }

/* Pack 7.56: kebab menu (⋯) — all editor actions consolidated here */
.ne-menu-wrap { position: relative; }
.ne-btn-kebab { width: 28px; height: 28px; border-radius: 8px; border: none; background: #F1F5F9; cursor: pointer; color: #534AB7; display: inline-flex; align-items: center; justify-content: center; transition: all 0.12s ease; }
.ne-btn-kebab:hover:not(:disabled), .ne-btn-kebab.on { background: rgba(127, 119, 221, 0.15); color: #534AB7; }
.ne-btn-kebab:disabled { opacity: 0.4; cursor: not-allowed; }
.ne-menu-bg { position: fixed; inset: 0; z-index: 99; }
.ne-menu { position: absolute; top: calc(100% + 6px); right: 0; min-width: 220px; background: #fff; border-radius: 10px; box-shadow: 0 12px 32px rgba(15, 23, 60, 0.18), 0 4px 12px rgba(15, 23, 60, 0.08); border: 1px solid rgba(15, 23, 60, 0.06); padding: 5px; z-index: 100; animation: ne-menu-in 0.16s cubic-bezier(0.34, 1.2, 0.64, 1); }
@keyframes ne-menu-in { from { opacity: 0; transform: translateY(-4px) scale(0.97); } to { opacity: 1; transform: translateY(0) scale(1); } }
.ne-menu-item { width: 100%; display: flex; align-items: center; gap: 9px; padding: 8px 12px; border: none; background: transparent; color: #1E2A4A; font-size: 12px; font-weight: 500; cursor: pointer; border-radius: 6px; text-align: left; font-family: inherit; transition: background 0.1s ease; }
.ne-menu-item:hover:not(:disabled) { background: rgba(127, 119, 221, 0.06); color: #534AB7; }
.ne-menu-item:disabled { opacity: 0.5; cursor: not-allowed; }
.ne-menu-item svg { flex-shrink: 0; color: #94A3B8; }
.ne-menu-item:hover:not(:disabled) svg { color: #7F77DD; }

.ne-body { display: flex; flex: 1; min-height: 0; position: relative; }

/* LEFT: companies — collapsible (Pack 7.57) */
.ne-co-pane {
  width: 200px;
  border-right: 1px solid #F1F5F9;
  display: flex;
  flex-direction: column;
  flex-shrink: 0;
  overflow: hidden;
  transition: width 0.28s cubic-bezier(0.34, 1.2, 0.64, 1);
}
.ne-co-pane.collapsed { width: 0; border-right: 0; }
.ne-co-pane.collapsed .ne-co-search,
.ne-co-pane.collapsed .ne-co-list { opacity: 0; pointer-events: none; transition: opacity 0.14s ease; }

/* Floating chevron toggle button — appears between sidebar and content */
.ne-sb-toggle {
  position: absolute;
  top: 50%;
  left: 188px; /* aside width 200 - 12 → button centered on edge */
  z-index: 10;
  width: 22px;
  height: 22px;
  margin-top: -11px;
  border-radius: 50%;
  border: 1px solid rgba(15, 23, 60, 0.10);
  background: #fff;
  color: #64748B;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  box-shadow: 0 4px 12px rgba(15, 23, 60, 0.14), 0 1px 3px rgba(15, 23, 60, 0.06);
  transition:
    left 0.28s cubic-bezier(0.34, 1.2, 0.64, 1),
    transform 0.16s ease,
    background 0.14s ease,
    color 0.14s ease;
}
.ne-sb-toggle:hover { background: #7F77DD; color: #fff; transform: scale(1.1); }
.ne-sb-toggle svg { transition: transform 0.32s cubic-bezier(0.34, 1.2, 0.64, 1); }
.ne-sb-toggle.collapsed { left: -12px; }
.ne-sb-toggle.collapsed svg { transform: rotate(180deg); }
.ne-co-search { padding: 8px 10px; border-bottom: 1px solid #F1F5F9; }
.ne-co-search input { width: 100%; font-size: 10.5px; padding: 5px 8px; border-radius: 6px; border: 1px solid #E2E8F0; font-family: inherit; outline: none; }
.ne-co-list { overflow-y: auto; padding: 6px; flex: 1; }
.ne-co-row { padding: 6px 9px; border-radius: 6px; cursor: pointer; margin-bottom: 2px; transition: background .12s; position: relative; overflow: hidden; }
.ne-co-row.active::before {
  content: ""; position: absolute; top: 0; left: 0; right: 0;
  height: 2px; background: #7F77DD;
  border-top-left-radius: inherit; border-top-right-radius: inherit;
  animation: uzaStripeDrawIn .4s cubic-bezier(0.34, 1.2, 0.64, 1) both;
  pointer-events: none;
}
.ne-co-row:hover { background: #F8FAFC; }
.ne-co-row.active { background: rgba(127, 119, 221, .08); }
.ne-co-row.active .ne-co-code { color: #534AB7; }
.ne-co-code { font-size: 11px; font-weight: 600; color: #0F172A; }
.ne-co-name { font-size: 10px; color: #475569; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.ne-co-sub { font-size: 9px; color: #94A3B8; margin-top: 1px; display: flex; align-items: center; gap: 4px; }
.ne-co-dirty { color: #EF9F27; font-size: 14px; line-height: 0; }

/* CENTER: editor */
.ne-edit-pane { flex: 1; display: flex; flex-direction: column; min-width: 0; border-right: 1px solid #F1F5F9; }
.ne-co-hdr { padding: 10px 16px; border-bottom: 1px solid #F1F5F9; display: flex; align-items: center; gap: 10px; flex-shrink: 0; }
.ne-co-hdr-stripe { width: 4px; height: 22px; border-radius: 2px; background: #7F77DD; }
.ne-co-hdr-info { flex: 1; min-width: 0; }
.ne-co-hdr-name { font-size: 14px; font-weight: 500; color: #1E2A4A; }
.ne-co-hdr-meta { font-size: 10px; color: #94A3B8; margin-top: 1px; }
.ne-pill { font-size: 10px; padding: 3px 9px; border-radius: 999px; background: rgba(127, 119, 221, .10); color: #534AB7; font-weight: 500; }

.ne-tabs-row { padding: 9px 16px; display: flex; gap: 5px; align-items: center; border-bottom: 1px solid #F1F5F9; flex-shrink: 0; }
.ne-tab { font-size: 11px; padding: 5px 13px; border-radius: 6px; border: none; background: #F1F5F9; color: #64748B; cursor: pointer; font-weight: 500; font-family: inherit; transition: all .12s; }
.ne-tab:hover { background: #E2E8F0; }
.ne-tab.on { background: #7F77DD; color: #fff; }
.ne-spc { flex: 1; }
.ne-btn-ghost { font-size: 10px; padding: 4px 10px; border-radius: 6px; border: 1px dashed #CBD5E1; background: #F8FAFC; color: #64748B; cursor: pointer; font-weight: 500; font-family: inherit; }
.ne-btn-ghost:hover { border-color: #7F77DD; color: #534AB7; }

.ne-grid-wrap { overflow: auto; flex: 1; padding: 0 16px 12px; }
.ne-grid { width: 100%; border-collapse: collapse; font-feature-settings: 'tnum'; }
.ne-grid thead tr { position: sticky; top: 0; background: #fff; z-index: 2; border-bottom: 1px solid #E2E8F0; }
.ne-grid thead th { padding: 8px 6px; text-align: center; font-size: 10px; font-weight: 500; color: #94A3B8; text-transform: uppercase; letter-spacing: .04em; }
.ne-grid thead th:first-child { text-align: left; padding-left: 10px; }
.ne-grid thead th.cur-year { color: #1E2A4A; background: rgba(127, 119, 221, .06); font-weight: 600; }

.ne-row-label { padding: 5px 10px; font-size: 11px; color: #475569; white-space: nowrap; }
.ne-nsbu-code { font-family: monospace; font-size: 9px; color: #94A3B8; margin-right: 6px; }
.ne-auto-badge { font-size: 8px; color: #EF9F27; background: #EF9F2715; padding: 1px 5px; border-radius: 3px; margin-right: 4px; font-weight: 600; }
.ne-custom-badge { font-size: 8px; color: #534AB7; background: rgba(127, 119, 221, .12); padding: 1px 5px; border-radius: 3px; margin-right: 4px; font-weight: 600; }
.ne-canon-badge { font-size: 8px; color: #0F6E56; background: rgba(29, 158, 117, .12); padding: 1px 5px; border-radius: 3px; margin-right: 4px; font-weight: 600; cursor: pointer; font-family: monospace; }
.ne-canon-badge:hover { background: rgba(29, 158, 117, .22); }
.ne-map-btn { font-size: 9px; padding: 1px 7px; border-radius: 4px; border: 1px dashed #CBD5E1; background: #fff; color: #64748B; cursor: pointer; font-weight: 500; font-family: inherit; margin-left: 8px; }
.ne-map-btn:hover { border-color: #1D9E75; color: #0F6E56; background: rgba(29, 158, 117, .04); }
.ne-canon-editor { padding: 10px 16px; background: rgba(29, 158, 117, .04); border-top: 1px solid rgba(29, 158, 117, .25); border-bottom: 1px solid rgba(29, 158, 117, .25); display: flex; gap: 8px; align-items: center; }
.ne-canon-lbl { font-size: 10px; color: #0F6E56; font-weight: 600; text-transform: uppercase; letter-spacing: 0.04em; }
.ne-canon-sel { flex: 1; padding: 6px 10px; border-radius: 6px; border: 1px solid #1D9E75; font-family: inherit; font-size: 11px; outline: none; background: #fff; }
.ne-row-name { cursor: pointer; }
.ne-row-name:hover { color: #1E2A4A; }
.ne-pos-hint { font-size: 8px; color: #94A3B8; margin-left: 3px; }
.ne-formula-hint { font-size: 9px; color: #94A3B8; margin-left: 6px; cursor: pointer; font-family: monospace; }
.ne-formula-hint:hover { color: #7F77DD; }

/* ═══ Pack 7.63: per-line notes / disclosures ═══ */
.ne-note-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 18px;
  height: 18px;
  margin-left: 8px;
  padding: 0;
  border: 1px dashed #CBD5E1;
  background: #fff;
  color: #94A3B8;
  border-radius: 4px;
  cursor: pointer;
  transition: all 0.12s ease;
  vertical-align: middle;
}
.ne-note-btn:hover {
  border-color: #7F77DD;
  background: rgba(127, 119, 221, 0.06);
  color: #534AB7;
}
.ne-note-btn.has-note {
  background: rgba(127, 119, 221, 0.18);
  border-color: #7F77DD;
  border-style: solid;
  color: #534AB7;
}
.ne-note-btn.has-note:hover {
  background: rgba(127, 119, 221, 0.28);
}
.ne-note-editor {
  padding: 12px 16px;
  background: rgba(127, 119, 221, 0.04);
  border-top: 1px solid rgba(127, 119, 221, 0.25);
  border-bottom: 1px solid rgba(127, 119, 221, 0.25);
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.ne-note-lbl {
  font-size: 10px;
  color: #534AB7;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.04em;
}
.ne-note-inp {
  width: 100%;
  padding: 8px 11px;
  border: 1px solid #CBD5E1;
  border-radius: 6px;
  font-family: inherit;
  font-size: 12px;
  line-height: 1.5;
  color: #1E2A4A;
  background: #fff;
  outline: none;
  resize: vertical;
  min-height: 60px;
}
.ne-note-inp:focus { border-color: #7F77DD; }
.ne-note-ftr {
  display: flex;
  gap: 8px;
  align-items: center;
}
.ne-note-hint {
  flex: 1;
  font-size: 9.5px;
  color: #94A3B8;
}
.ne-rename-inp { width: 220px; padding: 3px 6px; font-size: 11px; border-radius: 4px; border: 1.5px solid #7F77DD; outline: none; font-family: inherit; }

.ne-row-auto { background: #FFFBF0; }
.ne-row-sub { background: #F8FAFC; }
.ne-row-sub .ne-row-label { font-weight: 600; color: #0F172A; }

.ne-cell { padding: 3px 3px; }
.ne-cell input { width: 100%; padding: 5px 6px; border-radius: 5px; font-size: 11px; text-align: right; border: 1px solid #E2E8F0; background: #fff; font-family: inherit; outline: none; transition: all .12s; }
.ne-cell input:focus { border-color: #7F77DD; box-shadow: 0 0 0 2px rgba(127, 119, 221, .15); }
.ne-cell input.ne-cell-auto { background: #FFFBF0; border-color: #EF9F2740; color: #D97706; font-weight: 600; }
.ne-cell input.ne-cell-manual { background: #fff; border-color: #0F172A; color: #0F172A; font-weight: 600; }
.ne-cell input.ne-cell-sub { background: #F0EFF8; border-color: #D4D0EC; font-weight: 600; }
.ne-cell input.ne-cell-target { border: 1.5px solid #7F77DD; box-shadow: 0 0 0 2px rgba(127, 119, 221, .15); }

.ne-row-actions { padding: 3px; width: 34px; text-align: center; }
.ne-row-x { width: 22px; height: 22px; border-radius: 5px; border: none; background: #FEE2E2; color: #EF4444; cursor: pointer; font-size: 13px; line-height: 1; }
.ne-row-x:hover { background: #FECACA; }

.ne-group-hdr { padding: 9px 10px 3px; font-size: 9px; font-weight: 600; color: #7F77DD; text-transform: uppercase; letter-spacing: .06em; background: linear-gradient(to right, #F5F3FF 0%, #FAFBFF 100%); border-bottom: 1px solid #E0E7FF; }

.ne-formula-editor { padding: 10px 16px; background: #FFFBF0; border-top: 1px solid #EF9F2740; border-bottom: 1px solid #EF9F2740; display: flex; gap: 8px; align-items: center; }
.ne-formula-lbl { font-size: 10px; color: #D97706; font-weight: 600; text-transform: uppercase; letter-spacing: .04em; }
.ne-formula-inp { flex: 1; padding: 6px 10px; border-radius: 6px; border: 1px solid #EF9F27; font-family: monospace; font-size: 11px; outline: none; }

/* RIGHT: calculator */
.ne-calc-pane { width: 290px; display: flex; flex-direction: column; background: #FAFAFC; flex-shrink: 0; min-height: 0; }
.ne-calc-hdr { padding: 11px 14px; border-bottom: 1px solid #F1F5F9; background: #fff; display: flex; align-items: center; gap: 8px; flex-shrink: 0; }
.ne-calc-title { font-size: 11px; font-weight: 600; color: #1E2A4A; }
.ne-calc-target { font-size: 9px; color: #94A3B8; font-family: monospace; }
.ne-calc-body { overflow-y: auto; flex: 1; padding: 10px 12px; }
.ne-calc-lbl { font-size: 8.5px; font-weight: 500; color: #94A3B8; text-transform: uppercase; letter-spacing: .05em; margin: 8px 0 4px; }
.ne-calc-lbl:first-child { margin-top: 0; }
.ne-calc-expr { width: 100%; padding: 7px 9px; border-radius: 6px; border: 1px solid #E2E8F0; font-size: 11px; font-family: monospace; color: #1E2A4A; resize: vertical; outline: none; min-height: 38px; }
.ne-calc-expr:focus { border-color: #7F77DD; }
.ne-calc-hint { font-size: 9px; color: #94A3B8; margin-top: 3px; line-height: 1.4; }

.ne-calc-result { background: #fff; border: 1.5px solid rgba(127, 119, 221, .25); border-radius: 8px; padding: 9px 11px; margin-top: 10px; }
.ne-calc-result.err { border-color: rgba(226, 75, 74, .25); }
.ne-calc-val { display: flex; align-items: baseline; gap: 5px; font-size: 22px; font-weight: 500; color: #1E2A4A; letter-spacing: -.02em; font-feature-settings: 'tnum'; min-height: 28px; margin-top: 3px; }
.ne-calc-val .unit { font-size: 10px; color: #94A3B8; font-weight: 400; }
.ne-calc-val .placeholder { color: #CBD5E1; font-size: 15px; font-weight: 400; }
.ne-calc-val .err-txt { font-size: 11px; color: #A32D2D; font-weight: 500; }
.ne-btn-apply { margin-top: 7px; width: 100%; font-size: 10.5px; padding: 6px 10px; border-radius: 6px; border: none; background: linear-gradient(135deg, #7F77DD, #534AB7); color: #fff; cursor: pointer; font-weight: 600; display: flex; align-items: center; justify-content: center; gap: 5px; font-family: inherit; transition: all .12s; }
.ne-btn-apply:disabled { opacity: .45; cursor: not-allowed; background: #94A3B8; }
.ne-btn-apply:not(:disabled):hover { filter: brightness(.95); }

.ne-calc-fns { display: grid; grid-template-columns: repeat(2, 1fr); gap: 4px; }
.ne-calc-fns button { font-size: 9.5px; padding: 5px 7px; border-radius: 5px; border: 1px solid #E2E8F0; background: #fff; color: #534AB7; cursor: pointer; font-weight: 600; font-family: monospace; }
.ne-calc-fns button:hover { background: rgba(127, 119, 221, .06); border-color: #C7D2FE; }

.ne-calc-pad { display: grid; grid-template-columns: repeat(4, 1fr); gap: 3px; }
.ne-calc-pad button { padding: 7px 0; border-radius: 5px; border: 1px solid #E2E8F0; background: #fff; color: #1E2A4A; cursor: pointer; font-size: 11px; font-weight: 500; font-family: inherit; transition: all .1s; }
.ne-calc-pad button:hover { background: #F8FAFC; }
.ne-calc-pad button.op { color: #7F77DD; font-weight: 600; }
.ne-calc-pad button.span2 { grid-column: span 2; }

.ne-calc-hist { margin-top: 6px; }
.ne-calc-hist-row { display: flex; justify-content: space-between; gap: 8px; padding: 4px 6px; border-radius: 4px; cursor: pointer; font-size: 9.5px; font-family: monospace; color: #475569; }
.ne-calc-hist-row:hover { background: rgba(127, 119, 221, .06); }
.ne-calc-hist-row .hres { color: #534AB7; font-weight: 600; }

/* Footer */
.ne-ftr { padding: 11px 20px; border-top: 1px solid #E2E8F0; display: flex; align-items: center; gap: 9px; background: #fff; flex-shrink: 0; }
.ne-status { font-size: 10px; color: #94A3B8; flex: 1; }
.ne-btn-g { font-size: 11px; padding: 6px 12px; border-radius: 7px; border: 1px solid #E2E8F0; background: #fff; color: #64748B; cursor: pointer; font-weight: 500; font-family: inherit; }
.ne-btn-g:hover:not(:disabled) { background: #F8FAFC; }
.ne-btn-g:disabled { opacity: .4; cursor: not-allowed; }
.ne-btn-p { font-size: 11px; padding: 7px 18px; border-radius: 7px; border: none; background: linear-gradient(135deg, #7F77DD, #534AB7); color: #fff; cursor: pointer; font-weight: 600; font-family: inherit; }
.ne-btn-p:hover:not(:disabled) { filter: brightness(.95); }
.ne-btn-p:disabled { opacity: .45; cursor: not-allowed; background: #94A3B8; }

/* Add field dialog */
.ne-dlg-bg { position: fixed; inset: 0; background: rgba(15, 18, 40, .35); z-index: 10001; display: flex; align-items: center; justify-content: center; }
.ne-dlg { background: #fff; border-radius: 12px; padding: 16px 20px; width: 420px; box-shadow: 0 24px 64px rgba(15, 23, 60, .25); }
.ne-dlg-hdr { font-size: 14px; font-weight: 600; color: #1E2A4A; margin-bottom: 14px; }
.ne-dlg-row { margin-bottom: 12px; }
.ne-dlg-row label { display: block; font-size: 10px; color: #94A3B8; text-transform: uppercase; letter-spacing: .06em; margin-bottom: 4px; font-weight: 500; }
.ne-dlg-row input, .ne-dlg-row select { width: 100%; padding: 7px 10px; border-radius: 6px; border: 1px solid #E2E8F0; font-size: 12px; outline: none; font-family: inherit; }
.ne-dlg-row input:focus, .ne-dlg-row select:focus { border-color: #7F77DD; }
.ne-dlg-hint { font-size: 10px; color: #94A3B8; margin-top: 4px; line-height: 1.45; }
.ne-dlg-hint code { background: #F1F5F9; padding: 1px 5px; border-radius: 3px; color: #534AB7; }
.ne-dlg-ftr { display: flex; justify-content: flex-end; gap: 8px; margin-top: 6px; }

/* Pack 7.53: import preview */
.ne-dlg-wide { width: 760px; max-width: 90vw; max-height: 88vh; display: flex; flex-direction: column; }
.ne-imp-summary { display: flex; gap: 16px; margin-bottom: 14px; }
.ne-imp-stat { background: rgba(127, 119, 221, 0.06); border-radius: 8px; padding: 8px 14px; min-width: 100px; }
.ne-imp-stat-val { font-size: 22px; font-weight: 500; color: #534AB7; letter-spacing: -0.02em; font-feature-settings: 'tnum'; }
.ne-imp-stat-lbl { font-size: 10px; color: #94A3B8; text-transform: uppercase; letter-spacing: 0.05em; margin-top: 2px; }
.ne-imp-table-wrap { overflow: auto; max-height: 360px; border: 1px solid #E2E8F0; border-radius: 6px; margin-bottom: 10px; }
.ne-imp-table { width: 100%; border-collapse: collapse; font-feature-settings: 'tnum'; font-size: 11px; }
.ne-imp-table thead tr { position: sticky; top: 0; background: #F8FAFC; border-bottom: 1px solid #E2E8F0; }
.ne-imp-table th { padding: 6px 8px; text-align: center; font-size: 10px; font-weight: 600; color: #475569; text-transform: uppercase; letter-spacing: 0.04em; }
.ne-imp-table th:first-child { text-align: left; }
.ne-imp-table td { padding: 4px 8px; border-bottom: 0.5px solid #F1F5F9; }
.ne-imp-fld { font-family: monospace; font-size: 10.5px; color: #534AB7; }
.ne-imp-val { text-align: right; color: #0F172A; font-weight: 500; }
.ne-imp-empty { color: #CBD5E1; }
.ne-imp-log { background: #F8FAFC; border: 1px solid #E2E8F0; border-radius: 6px; padding: 8px 10px; margin-bottom: 10px; max-height: 100px; overflow-y: auto; }
.ne-imp-log-hdr { font-size: 10px; font-weight: 600; color: #64748B; text-transform: uppercase; letter-spacing: 0.04em; margin-bottom: 4px; }
.ne-imp-log-line { font-size: 10.5px; color: #475569; font-family: monospace; line-height: 1.5; }

/* Pack 7.55: history drawer (right-side slide-in) */
.ne-hist-drawer { position: absolute; top: 0; right: 0; bottom: 0; width: 380px; background: #fff; box-shadow: -8px 0 24px rgba(15, 23, 60, 0.12); z-index: 50; display: flex; flex-direction: column; animation: ne-hist-in 0.25s cubic-bezier(0.34, 1.2, 0.64, 1); }
@keyframes ne-hist-in { from { transform: translateX(40px); opacity: 0; } to { transform: translateX(0); opacity: 1; } }
.ne-hist-hdr { padding: 14px 18px; border-bottom: 1px solid #E2E8F0; display: flex; justify-content: space-between; align-items: center; }
.ne-hist-eyebrow { font-size: 9px; color: #888780; text-transform: uppercase; letter-spacing: 0.08em; font-weight: 500; }
.ne-hist-title { font-size: 14px; font-weight: 500; color: #1E2A4A; margin-top: 2px; }
.ne-hist-body { overflow-y: auto; flex: 1; padding: 10px 16px; }
.ne-hist-row { padding: 12px 0; border-bottom: 1px solid #F1F5F9; }
.ne-hist-row:last-child { border-bottom: none; }
.ne-hist-row-hdr { display: flex; justify-content: space-between; align-items: baseline; gap: 8px; margin-bottom: 6px; }
.ne-hist-date { font-size: 11px; color: #1E2A4A; font-weight: 500; font-feature-settings: 'tnum'; }
.ne-hist-actor { font-size: 10px; color: #94A3B8; font-family: monospace; overflow: hidden; text-overflow: ellipsis; }
.ne-hist-row-stats { display: flex; flex-wrap: wrap; gap: 4px; margin-bottom: 6px; }
.ne-hist-pill { font-size: 9.5px; padding: 2px 7px; border-radius: 999px; background: rgba(127, 119, 221, 0.08); color: #534AB7; font-weight: 500; }
.ne-hist-pill.ok { background: rgba(29, 158, 117, 0.10); color: #0F6E56; }
.ne-hist-pill.warn { background: rgba(239, 159, 39, 0.10); color: #B86A0E; }
.ne-hist-fields { font-size: 10px; font-family: monospace; color: #64748B; line-height: 1.45; padding-left: 4px; border-left: 2px solid #E2E8F0; padding-top: 1px; }

/* ═══ Pack 7.62: NSBU ↔ IFRS reconciliation ═══ */
.ne-recon-drawer { width: 460px; }
.ne-recon-filter {
  padding: 10px 16px;
  border-bottom: 1px solid #F1F5F9;
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}
.ne-recon-yearlbl {
  font-size: 9.5px;
  color: #94A3B8;
  font-weight: 500;
  text-transform: uppercase;
  letter-spacing: 0.06em;
}
.ne-recon-sel {
  padding: 5px 10px;
  border: 1px solid #E2E8F0;
  border-radius: 6px;
  font-family: inherit;
  font-size: 12px;
  color: #1E2A4A;
  background: #fff;
  outline: none;
}
.ne-recon-summary {
  display: flex;
  gap: 4px;
  flex-wrap: wrap;
  margin-left: auto;
}
.ne-recon-pill {
  font-size: 9.5px;
  font-weight: 500;
  padding: 2px 7px;
  border-radius: 999px;
}
.ne-recon-pill.high   { background: #FCEBEB; color: #A32D2D; }
.ne-recon-pill.medium { background: #FAEEDA; color: #854F0B; }
.ne-recon-pill.low    { background: #E1F5EE; color: #0F6E56; }
.ne-recon-pill.only   { background: #EEEDFE; color: #3C3489; }

.ne-recon-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 11px;
}
.ne-recon-table thead {
  background: #FAFAF9;
  position: sticky;
  top: 0;
  z-index: 1;
}
.ne-recon-table th {
  text-align: left;
  padding: 7px 10px;
  font-weight: 500;
  color: #94A3B8;
  text-transform: uppercase;
  letter-spacing: 0.04em;
  font-size: 9px;
  border-bottom: 1px solid #E2E8F0;
}
.ne-recon-table th:nth-child(n+2) { text-align: right; }
.ne-recon-table td {
  padding: 6px 10px;
  border-bottom: 1px solid #F1F5F9;
  vertical-align: middle;
}
.ne-recon-table tr.sig-high   td { background: rgba(226, 75, 74, 0.05); }
.ne-recon-table tr.sig-medium td { background: rgba(239, 159, 39, 0.05); }
.ne-recon-table tr.sig-high   td.ne-recon-pct,
.ne-recon-table tr.sig-medium td.ne-recon-pct { font-weight: 500; }
.ne-recon-table tr.sig-high   td.ne-recon-pct { color: #A32D2D; }
.ne-recon-table tr.sig-medium td.ne-recon-pct { color: #854F0B; }
.ne-recon-table tr.sig-low    td.ne-recon-pct { color: #0F6E56; }
.ne-recon-table tr.sig-ifrs_only td,
.ne-recon-table tr.sig-nsbu_only td { background: rgba(127, 119, 221, 0.04); }
.ne-recon-metric { max-width: 180px; }
.ne-recon-code   { display: block; font-family: monospace; font-size: 9px; color: #94A3B8; }
.ne-recon-label  { font-size: 11px; color: #1E2A4A; }
.ne-recon-val    { text-align: right; font-feature-settings: 'tnum'; color: #1E2A4A; }
.ne-recon-delta  { font-weight: 500; }
.ne-recon-only-lbl {
  font-size: 9.5px;
  color: #534AB7;
  background: rgba(127, 119, 221, 0.10);
  padding: 1px 6px;
  border-radius: 3px;
}

.ne-empty { padding: 24px; text-align: center; color: #94A3B8; font-size: 12px; }

@media (max-width: 1100px) {
  .ne-calc-pane { display: none; }
}
</style>
