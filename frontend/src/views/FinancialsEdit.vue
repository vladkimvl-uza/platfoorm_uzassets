<script setup lang="ts">
import { ref, onMounted, onUnmounted, computed, watch } from "vue";
import { useRoute, useRouter, RouterLink, onBeforeRouteLeave } from "vue-router";
import { financialsApi } from "@/api/financials";
import { isModerationQueued } from "@/api/client";
import { companiesApi } from "@/api/companies";
import {
  SECTIONS, ROWS_BY_SECTION, BASE_YEARS, EXPENSE_FIELDS, CALCULATED_FIELDS,
  autoCalc, labelFor,
  type Section, type FinRow,
} from "@/utils/financialsSchema";
import {
  stash, readBackup, clearBackup,
} from "@/utils/financialsBackup";
import type {
  FinancialReportFull, FinancialLineEdit, FinancialReportSavePayload,
} from "@/api/financials";

const route   = useRoute();
const router  = useRouter();

// Either /financials/:id (legacy single-report URL) or /companies/:code/financials
const reportId = computed(() => String(route.params.id || ""));
const companyCode = computed(() => String(route.params.code || ""));

// =====================================================================
// State
// =====================================================================

const loading = ref(true);
const error   = ref<string | null>(null);

const selectedCompanyCode = ref<string>("");
const selectedStandard    = ref<"IFRS" | "NSBU">("IFRS");
const selectedTab         = ref<Section>("pnl");

const companiesIndex = ref<Map<string, { code: string; name_short: string | null; name_ru: string }>>(new Map());

// Years currently in the editor (BASE_YEARS + extras from data)
const yearsInEditor = ref<number[]>([...BASE_YEARS]);

// Map: { "year:fieldCode": numericValue | null }
// One unified key-value space across all 3 sections (PL/BS/CF).
const cellValues = ref<Record<string, number | null>>({});

// Map of report IDs we loaded — { "PL": "uuid…", "BS": "uuid…", "CF": "uuid…" }
const reportIds = ref<Record<string, string>>({});
const reportChecksums = ref<Record<string, string>>({});

const dirty = ref(false);
const saving = ref(false);
const lastSavedAt = ref<string | null>(null);
const saveStatus = ref<"idle" | "saving" | "saved" | "error" | "conflict">("idle");
const statusMsg  = ref<string>("");

// Recovery banner
const recoveryAvailable = ref<{ savedAt: string } | null>(null);

let autoSaveTimer: number | null = null;
let backupTimer: number | null = null;
const AUTO_SAVE_DEBOUNCE_MS = 1500;
const PERIODIC_BACKUP_INTERVAL_MS = 20000;

// =====================================================================
// Computed
// =====================================================================

const selectedCompanyDisplay = computed(() => {
  const c = companiesIndex.value.get(selectedCompanyCode.value);
  if (!c) return selectedCompanyCode.value;
  return c.name_short || c.name_ru || c.code;
});

const currentSectionRows = computed(() => ROWS_BY_SECTION[selectedTab.value]);

/** byCode for a single year — for autoCalc lookups */
function valuesForYear(year: number): Record<string, number | null> {
  const out: Record<string, number | null> = {};
  for (const k of Object.keys(cellValues.value)) {
    const [yr, code] = k.split(":");
    if (parseInt(yr, 10) === year) {
      out[code] = cellValues.value[k];
    }
  }
  return out;
}

// =====================================================================
// Load
// =====================================================================

async function loadCompanies() {
  const r = await companiesApi.list({ limit: 200 });
  companiesIndex.value = new Map(
    r.items.map(c => [c.code, { code: c.code, name_short: c.name_short, name_ru: c.name_ru }])
  );
}

/** Load all 3 reports (PL, BS, CF) for one company × one standard. */
async function loadReports(companyCode: string, standard: "IFRS" | "NSBU") {
  loading.value = true;
  error.value = null;
  try {
    // Fetch the list of reports for this company × standard
    const list = await financialsApi.list({ company_code: companyCode, standard });
    const reports: FinancialReportFull[] = await Promise.all(
      list.map(item => financialsApi.get(item.id))
    );

    reportIds.value = {};
    reportChecksums.value = {};
    cellValues.value = {};
    yearsInEditor.value = [...BASE_YEARS];

    for (const r of reports) {
      reportIds.value[r.report_type] = r.id;
      reportChecksums.value[r.report_type] = r.checksum || "";

      // Add report's year if not in base range
      if (!yearsInEditor.value.includes(r.year)) {
        yearsInEditor.value.push(r.year);
      }

      // Map all lines into cellValues
      for (const ln of r.lines) {
        const v = ln.value === null || ln.value === undefined ? null : Number(ln.value);
        cellValues.value[`${r.year}:${ln.line_code}`] = v;
      }
    }
    yearsInEditor.value.sort((a, b) => a - b);

    // Check for recovery: localStorage draft for THIS company × standard
    const recoveryKey = `${companyCode}__${standard}`;
    const draft = readBackup(recoveryKey);
    if (draft && draft.payload) {
      recoveryAvailable.value = { savedAt: draft.savedAt };
    } else {
      recoveryAvailable.value = null;
    }

    dirty.value = false;
    saveStatus.value = "idle";
  } catch (e: any) {
    error.value = e?.response?.data?.detail || e?.message || "Не удалось загрузить отчёты";
  } finally {
    loading.value = false;
  }
}

async function init() {
  await loadCompanies();

  // Determine target company: from URL param OR from /financials/:id legacy redirect
  if (companyCode.value && companiesIndex.value.has(companyCode.value)) {
    selectedCompanyCode.value = companyCode.value;
  } else if (reportId.value) {
    try {
      const single = await financialsApi.get(reportId.value);
      selectedCompanyCode.value = single.company_code;
      selectedStandard.value = single.standard;
    } catch { /* ignore */ }
  }

  // Pick first company if still unset
  if (!selectedCompanyCode.value && companiesIndex.value.size > 0) {
    selectedCompanyCode.value = Array.from(companiesIndex.value.keys())[0];
  }

  if (selectedCompanyCode.value) {
    await loadReports(selectedCompanyCode.value, selectedStandard.value);
  } else {
    loading.value = false;
  }
}

watch([selectedCompanyCode, selectedStandard], async ([co, std]) => {
  if (co) await loadReports(co, std);
});

onMounted(async () => {
  await init();

  backupTimer = window.setInterval(() => {
    if (dirty.value) instantStash();
  }, PERIODIC_BACKUP_INTERVAL_MS);

  window.addEventListener("beforeunload", onBeforeUnload);
});

onUnmounted(() => {
  if (autoSaveTimer) window.clearTimeout(autoSaveTimer);
  if (backupTimer)   window.clearInterval(backupTimer);
  window.removeEventListener("beforeunload", onBeforeUnload);
});

function onBeforeUnload(ev: BeforeUnloadEvent) {
  if (dirty.value) {
    instantStash();
    ev.preventDefault();
    ev.returnValue = "У вас есть несохранённые изменения. Они сохранены в черновике.";
  }
}

onBeforeRouteLeave((to, from, next) => {
  if (dirty.value) {
    if (confirm("Несохранённые изменения. Они сохранены в черновике. Уйти со страницы?")) {
      next();
    } else {
      next(false);
    }
  } else {
    next();
  }
});

// =====================================================================
// Edit + auto-save
// =====================================================================

function instantStash() {
  if (!selectedCompanyCode.value) return;
  const recoveryKey = `${selectedCompanyCode.value}__${selectedStandard.value}`;
  stash(recoveryKey, {
    savedAt: new Date().toISOString(),
    payload: {
      company_code: selectedCompanyCode.value,
      standard: selectedStandard.value,
      cellValues: cellValues.value,
      yearsInEditor: yearsInEditor.value,
    },
    baseChecksum: null,
    reportLabel: `${selectedCompanyDisplay.value} · ${selectedStandard.value}`,
  });
}

function onCellEdit(year: number, code: string, raw: string) {
  if (CALCULATED_FIELDS.has(code)) return; // Read-only
  const trimmed = String(raw).trim();
  let value: number | null = null;
  if (trimmed !== "") {
    const num = parseFloat(trimmed.replace(/\s/g, "").replace(",", "."));
    if (Number.isFinite(num)) {
      // Apply expense sign: user enters positive, store negative for accounting consistency.
      // To stay consistent, we store as the user enters: positive for expense fields,
      value = num;
    }
  }
  cellValues.value[`${year}:${code}`] = value;
  dirty.value = true;
  saveStatus.value = "idle";
  instantStash();
  scheduleAutoSave();
}

function scheduleAutoSave() {
  if (autoSaveTimer) window.clearTimeout(autoSaveTimer);
  autoSaveTimer = window.setTimeout(() => {
    if (dirty.value && !saving.value) {
      void doSave(false);
    }
  }, AUTO_SAVE_DEBOUNCE_MS);
}

function applyRecoveredDraft() {
  const recoveryKey = `${selectedCompanyCode.value}__${selectedStandard.value}`;
  const draft = readBackup(recoveryKey);
  if (!draft || !draft.payload) return;
  cellValues.value = { ...draft.payload.cellValues };
  yearsInEditor.value = [...draft.payload.yearsInEditor];
  recoveryAvailable.value = null;
  dirty.value = true;
  statusMsg.value = "Черновик восстановлен из локального хранилища";
}

function dismissRecovery() {
  const recoveryKey = `${selectedCompanyCode.value}__${selectedStandard.value}`;
  clearBackup(recoveryKey);
  recoveryAvailable.value = null;
}

// =====================================================================
// Cell value with auto-calc fallback
// =====================================================================

function getCellValue(year: number, code: string): number | null {
  if (CALCULATED_FIELDS.has(code)) {
    // Compute on the fly from other cells in the SAME year
    const yv = valuesForYear(year);
    const calc = autoCalc(code, yv);
    if (calc !== null) return calc;
    // Fall back to stored value if autoCalc failed (some inputs missing)
    return cellValues.value[`${year}:${code}`] ?? null;
  }
  return cellValues.value[`${year}:${code}`] ?? null;
}

function formatNum(v: number | null): string {
  if (v === null || v === undefined) return "";
  return v.toLocaleString("ru-RU", { maximumFractionDigits: 2 });
}

// =====================================================================
// Save: split values by section → 3 reports (PL/BS/CF) → upsert each
// =====================================================================

function buildPayloadForSection(year: number, section: Section): FinancialLineEdit[] {
  const rows = ROWS_BY_SECTION[section];
  const lines: FinancialLineEdit[] = [];
  for (let i = 0; i < rows.length; i++) {
    const row = rows[i];
    const v = getCellValue(year, row.code);
    // Don't send null values — backend persists them as missing rows
    if (v === null) continue;
    lines.push({
      line_code: row.code,
      line_name: labelFor(row, selectedStandard.value),
      value: v,
      is_subtotal: !!row.is_subtotal,
      is_calculated: !!row.is_calculated,
      sort_order: i * 10,
    });
  }
  return lines;
}

async function doSave(manual = true) {
  if (saving.value || !selectedCompanyCode.value) return;
  saving.value = true;
  saveStatus.value = "saving";
  statusMsg.value = manual ? "Сохранение…" : "Авто-сохранение…";

  try {
    // For each (year × section), upsert the report. We loop years × sections.
    let savedCount = 0;
    let totalLines = 0;

    for (const year of yearsInEditor.value) {
      for (const section of (["pnl", "sofp", "cashflow"] as Section[])) {
        const reportType: "PL" | "BS" | "CF" =
          section === "pnl" ? "PL" : section === "sofp" ? "BS" : "CF";

        const lines = buildPayloadForSection(year, section);
        if (lines.length === 0) continue;   // Nothing to save for this year/section

        let reportId = reportIds.value[reportType];

        // If we don't have a report for this (year, type) yet, create it
        if (!reportId) {
          const co = companiesIndex.value.get(selectedCompanyCode.value);
          if (!co) continue;
          // We need company UUID; companies API returns code. Lookup by code:
          const fullCo = await companiesApi.getOne(co.code);
          const newRep = await financialsApi.create({
            company_id: fullCo.id,
            year, standard: selectedStandard.value, report_type: reportType,
            currency: "UZS", unit_scale: 1_000_000_000, source: "manual",
          });
          reportId = newRep.id;
          reportIds.value[reportType] = reportId;
          reportChecksums.value[reportType] = newRep.checksum || "";
        }

        const payload: FinancialReportSavePayload = {
          year, standard: selectedStandard.value, report_type: reportType,
          currency: "UZS", unit_scale: 1_000_000_000, source: "manual",
          is_audited: false, lines,
          expected_prev_checksum: reportChecksums.value[reportType] || null,
        };
        const resp = await financialsApi.save(reportId, payload);
        if (isModerationQueued(resp)) {
          // Gated submission — interceptor toasted, leave checksum/state alone
          // so user can retry once approved. Bail out of the whole save.
          saveStatus.value = "saved";
          statusMsg.value = "Изменения отправлены на модерацию";
          return;
        }
        reportChecksums.value[reportType] = resp.server_checksum;
        savedCount++;
        totalLines += resp.lines_total;
      }
    }

    dirty.value = false;
    saveStatus.value = "saved";
    lastSavedAt.value = new Date().toISOString();
    statusMsg.value = `✓ Сохранено: ${savedCount} отчёт(ов), ${totalLines} строк`;
    const recoveryKey = `${selectedCompanyCode.value}__${selectedStandard.value}`;
    clearBackup(recoveryKey);
  } catch (e: any) {
    if (e?.response?.status === 409) {
      saveStatus.value = "conflict";
      statusMsg.value = "⚠ Конфликт: данные изменены другим пользователем. Перезагрузите страницу.";
    } else {
      saveStatus.value = "error";
      statusMsg.value = `Ошибка: ${e?.response?.data?.detail || e?.message || "сохранение не удалось"}`;
    }
  } finally {
    saving.value = false;
  }
}

// =====================================================================
// Year management
// =====================================================================

function addYear() {
  const next = Math.max(...yearsInEditor.value) + 1;
  if (next > 2100) return;
  if (yearsInEditor.value.includes(next)) return;
  yearsInEditor.value.push(next);
  yearsInEditor.value.sort((a, b) => a - b);
  dirty.value = true;
  saveStatus.value = "idle";
}

function removeYear(year: number) {
  if (BASE_YEARS.includes(year)) {
    if (!confirm(`Удалить базовый год ${year}? Все данные за этот год будут потеряны.`)) return;
  } else {
    if (!confirm(`Удалить год ${year} вместе со всеми данными?`)) return;
  }
  yearsInEditor.value = yearsInEditor.value.filter(y => y !== year);
  // Also wipe cell values for that year
  for (const k of Object.keys(cellValues.value)) {
    if (k.startsWith(`${year}:`)) {
      delete cellValues.value[k];
    }
  }
  dirty.value = true;
  saveStatus.value = "idle";
}

// =====================================================================
// Bulk delete (all data for this company × standard)
// =====================================================================

async function deleteAllData() {
  const label = `${selectedCompanyDisplay.value} · ${selectedStandard.value}`;
  if (!confirm(`Удалить ВСЕ финансовые данные ${label}? Это действие необратимо.`)) return;
  try {
    await companiesApi.deleteFinancials(selectedCompanyCode.value, { standard: selectedStandard.value });
    await loadReports(selectedCompanyCode.value, selectedStandard.value);
    statusMsg.value = `✓ Удалено: ${label}`;
    saveStatus.value = "saved";
  } catch (e: any) {
    statusMsg.value = `Ошибка удаления: ${e?.response?.data?.detail || e?.message}`;
    saveStatus.value = "error";
  }
}
</script>

<template>
  <div class="p-6 max-w-[1400px] mx-auto">
    <!-- Header -->
    <div class="mb-4 flex items-end justify-between flex-wrap gap-3">
      <div>
        <div class="uza-section-label">Финансы</div>
        <h1 class="text-[15px] font-medium tracking-uza-snug mt-1">
          Финансовый редактор
          <span class="text-slate-400 font-normal">· МСФО / НСБУ</span>
        </h1>
      </div>

      <!-- Save status + button -->
      <div class="flex items-center gap-3">
        <span v-if="saveStatus !== 'idle'" class="text-xs"
              :class="{
                'text-uza-teal':   saveStatus === 'saved',
                'text-uza-purple': saveStatus === 'saving',
                'text-uza-red':    saveStatus === 'error' || saveStatus === 'conflict',
              }">
          {{ statusMsg }}
        </span>
        <span v-else-if="dirty" class="text-xs text-uza-amber">● Несохранено</span>
        <span v-else class="text-xs text-slate-400">Сохранено</span>
        <button @click="doSave(true)" :disabled="saving || !dirty"
                class="px-4 py-2 text-sm bg-uza-purple text-white rounded-uza-pill hover:bg-uza-purple/90 disabled:opacity-40 disabled:cursor-not-allowed">
          Сохранить
        </button>
      </div>
    </div>

    <!-- Recovery banner -->
    <div v-if="recoveryAvailable" class="uza-card p-4 mb-4 border-l-2" style="border-left-color: #EF9F27">
      <div class="flex items-center gap-3 flex-wrap">
        <div class="flex-1 min-w-[300px]">
          <div class="text-sm font-medium text-slate-700">Найден несохранённый черновик</div>
          <div class="text-xs text-slate-500 mt-0.5">
            Сохранён {{ new Date(recoveryAvailable.savedAt).toLocaleString("ru-RU") }}
          </div>
        </div>
        <button @click="applyRecoveredDraft"
                class="px-3 py-1.5 text-xs bg-amber-50 text-amber-700 rounded-uza-pill hover:bg-amber-100">
          ↺ Восстановить
        </button>
        <button @click="dismissRecovery"
                class="px-3 py-1.5 text-xs text-slate-500 hover:text-uza-red">
          Удалить черновик
        </button>
      </div>
    </div>

    <!-- Selectors row -->
    <div class="uza-card p-4 mb-4 flex items-center gap-3 flex-wrap">
      <select v-model="selectedCompanyCode"
              class="px-3 py-2 text-sm rounded-uza-pill border border-slate-200 bg-white focus:border-uza-purple flex-1 min-w-[260px]">
        <option v-for="[code, c] in companiesIndex" :key="code" :value="code">
          {{ c.name_short || c.name_ru }}
        </option>
      </select>

      <!-- Standard toggle -->
      <div class="flex bg-slate-100 rounded-uza-pill p-0.5">
        <button v-for="std in (['IFRS', 'NSBU'] as const)" :key="std"
                @click="selectedStandard = std"
                class="px-4 py-1.5 text-sm rounded-uza-pill transition-colors"
                :class="selectedStandard === std ? 'bg-white shadow-sm font-medium' : 'text-slate-500'">
          {{ std === 'IFRS' ? 'МСФО' : 'НСБУ' }}
        </button>
      </div>

      <button @click="addYear"
              class="px-3 py-2 text-xs text-slate-500 hover:text-uza-purple border border-slate-200 rounded-uza-pill">
        + Год
      </button>
      <button @click="deleteAllData"
              class="px-3 py-2 text-xs text-uza-red hover:bg-red-50 border border-red-200 rounded-uza-pill">
        Удалить всё
      </button>
    </div>

    <!-- Loading / error -->
    <div v-if="loading" class="uza-card p-12 text-center text-slate-400 text-sm">Загрузка…</div>
    <div v-else-if="error" class="uza-card p-6 text-uza-red text-sm">{{ error }}</div>

    <template v-else-if="selectedCompanyCode">
      <!-- Section tabs -->
      <div class="flex gap-1 mb-4 border-b border-slate-200">
        <button v-for="sec in SECTIONS" :key="sec.id"
                @click="selectedTab = sec.id"
                class="px-4 py-2 text-sm transition-colors relative"
                :class="selectedTab === sec.id ? 'text-uza-purple font-medium' : 'text-slate-500 hover:text-slate-700'">
          {{ selectedStandard === 'IFRS' ? sec.label_ifrs : sec.label_nsbu }}
          <span v-if="selectedTab === sec.id" class="absolute bottom-0 left-0 right-0 h-0.5 bg-uza-purple"></span>
        </button>
      </div>

      <!-- Editor table -->
      <div class="uza-card overflow-x-auto">
        <table class="w-full text-sm" style="min-width: 800px">
          <thead class="bg-slate-50/60 border-b border-slate-100 text-[10px] uppercase tracking-uza-label2 text-slate-500">
            <tr>
              <th class="text-left px-4 py-3 font-medium sticky left-0 bg-slate-50 z-10" style="min-width: 280px">
                Статья
              </th>
              <th v-for="y in yearsInEditor" :key="y"
                  class="text-right px-3 py-3 font-medium relative" style="min-width: 110px">
                {{ y }}
                <button v-if="!saving" @click="removeYear(y)"
                        class="absolute top-1 right-1 text-slate-300 hover:text-uza-red text-[10px]"
                        :title="`Удалить год ${y}`">×</button>
              </th>
            </tr>
          </thead>
          <tbody class="divide-y divide-slate-100">
            <template v-for="(row, idx) in currentSectionRows" :key="row.code">
              <!-- Group header (UPPERCASE label spanning all columns) -->
              <tr v-if="row.group_header_ifrs && (selectedStandard === 'IFRS' ? row.group_header_ifrs : row.group_header_nsbu)"
                  class="bg-slate-50/40">
                <td :colspan="yearsInEditor.length + 1"
                    class="px-4 py-2 text-[10px] font-medium tracking-uza-label2 text-slate-500">
                  {{ selectedStandard === 'IFRS' ? row.group_header_ifrs : row.group_header_nsbu }}
                </td>
              </tr>

              <!-- Data row -->
              <tr :class="{ 'bg-slate-50/30': row.is_subtotal }">
                <td class="px-4 py-2 sticky left-0 bg-white z-10"
                    :class="{ 'font-medium': row.is_subtotal }">
                  <div class="flex items-center gap-2">
                    <span class="text-slate-900">{{ labelFor(row, selectedStandard) }}</span>
                    <span v-if="row.is_expense" class="text-[8px] text-slate-400 font-normal"
                          title="Введите положительное число — система учтёт знак автоматически">(+)</span>
                    <span v-if="row.is_calculated" class="text-[8px] text-uza-blue uppercase tracking-uza-label2"
                          :title="row.auto_calc_hint">f(x)</span>
                    <code class="text-[8px] text-slate-300 ml-auto">{{ row.code }}</code>
                  </div>
                </td>
                <td v-for="year in yearsInEditor" :key="year" class="px-2 py-1 text-right">
                  <input
                    :value="getCellValue(year, row.code) === null ? '' : getCellValue(year, row.code)"
                    @input="(e: any) => onCellEdit(year, row.code, e.target.value)"
                    :readonly="row.is_calculated"
                    type="text"
                    inputmode="decimal"
                    placeholder="—"
                    class="w-full px-2 py-1.5 text-right text-sm tabular-nums rounded border border-transparent hover:border-slate-200 focus:border-uza-purple focus:bg-white focus:outline-none transition-colors"
                    :class="[
                      row.is_subtotal ? 'font-medium' : '',
                      row.is_calculated ? 'text-uza-blue cursor-not-allowed bg-blue-50/30' : '',
                    ]"
                  />
                </td>
              </tr>
            </template>
          </tbody>
        </table>
      </div>

      <!-- Footer hints -->
      <div class="mt-3 flex items-center gap-4 text-[10px] text-slate-400 px-1">
        <span><code class="text-uza-blue">f(x)</code> — рассчитывается автоматически</span>
        <span><span class="text-slate-400">(+)</span> — вводите положительное число, знак учтётся</span>
        <span class="ml-auto">Единицы: млрд сум</span>
      </div>
    </template>
  </div>
</template>
