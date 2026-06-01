<script setup lang="ts">
/**
 * Detailed audited financial reports view — UZA design system.
 *
 *   – Page wrapper: .uza-page, max-w 1500px
 *   – Toolbar: glass section .uza-section
 *   – KPI band of .kpi2 cards above the grid (mapped/total/missing/sections)
 *   – Grid: .uza-table with sticky header, alternating row bg
 *   – Preview modal: .uza-modal-backdrop + .uza-modal-card with size-xl
 *   – Pills: .uza-pill-{teal,amber,purple,red,green}
 *   – Buttons: .btn-p (primary), .btn-s (secondary)
 *   – All accent strips animate via uzaDrawIn → uzaBreathe → uzaShimmer chain
 */
import { computed, onMounted, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";

import { companiesApi, type CompanyListItem } from "@/api/companies";
import {
  detailedFinancialsApi,
  type CanonicalCatalog,
  type DetailedReport,
  type DetailedRow,
  type PreviewResult,
  type PreviewRow,
  type PreviewSection,
} from "@/api/financialsDetailed";
import { useFormatters } from "@/composables/useFormatters";

const fmt = useFormatters();

const route = useRoute();
const router = useRouter();

const companies = ref<CompanyListItem[]>([]);
const selectedCompanyCode = ref<string>("");
const selectedStandard = ref<"IFRS" | "NSBU">("IFRS");
const selectedReportType = ref<"PL" | "BS" | "CF">("BS");

const report = ref<DetailedReport | null>(null);
const catalog = ref<CanonicalCatalog | null>(null);
const loading = ref(false);
const error = ref<string | null>(null);

const fileInput = ref<HTMLInputElement | null>(null);
const bulkFileInput = ref<HTMLInputElement | null>(null);

const previewing = ref(false);
const preview = ref<PreviewResult | null>(null);
const confirming = ref(false);
const previewError = ref<string | null>(null);
const previewActiveSheet = ref<number>(0);
const previewActiveSection = ref<number>(0);


async function loadCompanies() {
  const r = await companiesApi.list({ limit: 200 });
  companies.value = r.items;
}
async function loadCatalog() {
  try { catalog.value = await detailedFinancialsApi.catalog(); }
  catch (e) { console.warn("Failed to load canonical catalog:", e); }
}
async function loadReport() {
  if (!selectedCompanyCode.value) return;
  loading.value = true;
  error.value = null;
  try {
    report.value = await detailedFinancialsApi.get(
      selectedCompanyCode.value, selectedStandard.value, selectedReportType.value,
    );
  } catch (e: any) {
    error.value = e?.response?.data?.detail || e?.message || "Не удалось загрузить отчёт";
  } finally {
    loading.value = false;
  }
}

async function onFilePicked(e: Event, mode: "single" | "bulk") {
  const input = e.target as HTMLInputElement;
  const f = input.files?.[0];
  if (!f) return;
  if (mode === "single" && !selectedCompanyCode.value) {
    alert("Сначала выберите компанию");
    input.value = "";
    return;
  }
  previewing.value = true;
  previewError.value = null;
  preview.value = null;
  try {
    preview.value = await detailedFinancialsApi.preview({
      file: f,
      standard: selectedStandard.value,
      company_code: mode === "single" ? selectedCompanyCode.value : undefined,
    });
    previewActiveSheet.value = 0;
    previewActiveSection.value = 0;
  } catch (e: any) {
    previewError.value = e?.response?.data?.detail || e?.message || "Не удалось распарсить файл";
  } finally {
    previewing.value = false;
    input.value = "";
  }
}

function closePreview() {
  preview.value = null;
  previewError.value = null;
}

async function confirmImport() {
  if (!preview.value) return;
  confirming.value = true;
  try {
    const payload = {
      standard: selectedStandard.value,
      is_audited: true,
      filename: preview.value.filename,
      sheets: preview.value.sheets.map((s) => ({
        company_code: s.company_code,
        sections: s.sections.map((sec) => ({
          report_type: sec.report_type,
          years: sec.years,
          rows: sec.rows.map((r) => ({
            code: r.code,
            label: r.label,
            canonical_code: r.canonical_code,
            is_unmapped: r.is_unmapped,
            indent_level: r.indent_level,
            section_label: r.section_label,
            is_subtotal: r.is_subtotal,
            values: r.values,
          })),
        })),
      })),
    };
    const res = await detailedFinancialsApi.confirmImport(payload);
    alert(`✓ Импортировано: ${res.companies_imported} компаний, ${res.reports_created} отчётов, ${res.lines_created} строк`);
    closePreview();
    await loadReport();
  } catch (e: any) {
    alert("❌ " + (e?.response?.data?.detail || e?.message));
  } finally {
    confirming.value = false;
  }
}

function deletePreviewRow(sheetIdx: number, secIdx: number, rowIdx: number) {
  if (!preview.value) return;
  preview.value.sheets[sheetIdx].sections[secIdx].rows.splice(rowIdx, 1);
}
function previewRowMappingChange(row: PreviewRow, newCode: string | null) {
  row.canonical_code = newCode;
  row.is_unmapped = !newCode;
}
function previewSectionMappedCount(sec: PreviewSection): number {
  return sec.rows.filter((r) => !r.is_unmapped).length;
}
function previewSectionMissing(sec: PreviewSection): string[] {
  if (!catalog.value) return sec.missing_canonical_codes;
  const present = new Set(sec.rows.map((r) => r.canonical_code).filter(Boolean) as string[]);
  const allCanonical = catalog.value[sec.report_type]?.map((c) => c.code) || [];
  return allCanonical.filter((code) => !present.has(code));
}

async function saveCell(row: DetailedRow, year: number, raw: string) {
  const trimmed = raw.replace(/\s+/g, "").replace(",", ".");
  let v: number | null = null;
  if (trimmed !== "" && trimmed !== "—" && trimmed !== "-") {
    const n = Number(trimmed);
    if (Number.isFinite(n)) v = n;
    else { alert(`«${raw}» — не число`); return; }
  }
  try {
    await detailedFinancialsApi.updateCell(
      selectedCompanyCode.value, selectedStandard.value,
      selectedReportType.value, year, row.code, v,
    );
    row.values[year] = v;
  } catch (e: any) {
    alert("Не удалось сохранить: " + (e?.response?.data?.detail || e?.message));
  }
}
async function changeMapping(row: DetailedRow, newCode: string | null) {
  try {
    await detailedFinancialsApi.updateLineMapping(
      selectedCompanyCode.value, selectedStandard.value, selectedReportType.value,
      row.code, newCode,
    );
    row.canonical_code = newCode;
    row.is_unmapped = !newCode;
  } catch (e: any) {
    alert("Не удалось обновить маппинг: " + (e?.response?.data?.detail || e?.message));
  }
}
async function renameLine(row: DetailedRow, newLabel: string) {
  if (newLabel === row.label) return;
  try {
    await detailedFinancialsApi.updateLineMapping(
      selectedCompanyCode.value, selectedStandard.value, selectedReportType.value,
      row.code, row.canonical_code, newLabel,
    );
    row.label = newLabel;
  } catch (e: any) {
    alert("Не удалось переименовать: " + (e?.response?.data?.detail || e?.message));
  }
}
async function removeLine(row: DetailedRow) {
  if (!confirm(`Удалить строку «${row.label}» из всех годов?`)) return;
  try {
    await detailedFinancialsApi.deleteLine(
      selectedCompanyCode.value, selectedStandard.value, selectedReportType.value, row.code,
    );
    if (report.value) {
      report.value.rows = report.value.rows.filter((r) => r.code !== row.code);
    }
  } catch (e: any) {
    alert("Не удалось удалить: " + (e?.response?.data?.detail || e?.message));
  }
}


// Computed
interface RenderGroup { section: string | null; rows: DetailedRow[]; }
const grouped = computed<RenderGroup[]>(() => {
  if (!report.value) return [];
  const out: RenderGroup[] = [];
  let current: RenderGroup | null = null;
  for (const row of report.value.rows) {
    if (!current || current.section !== row.section) {
      current = { section: row.section, rows: [] };
      out.push(current);
    }
    current.rows.push(row);
  }
  return out;
});
const reportUnmapped = computed(() => report.value?.rows.filter((r) => r.is_unmapped).length || 0);
const reportMapped = computed(() => (report.value?.rows.length || 0) - reportUnmapped.value);
const reportMissingCanonical = computed<string[]>(() => {
  if (!report.value || !catalog.value) return [];
  const present = new Set(report.value.rows.map((r) => r.canonical_code).filter(Boolean) as string[]);
  const all = catalog.value[selectedReportType.value]?.map((c) => c.code) || [];
  return all.filter((c) => !present.has(c));
});
function canonicalLineByCode(rtype: "BS" | "PL" | "CF", code: string | null) {
  if (!code || !catalog.value) return null;
  return catalog.value[rtype]?.find((c) => c.code === code) || null;
}


onMounted(async () => {
  await Promise.all([loadCompanies(), loadCatalog()]);
  const q = route.query;
  if (typeof q.company === "string") selectedCompanyCode.value = q.company;
  else if (companies.value.length) selectedCompanyCode.value = companies.value[0].code;
  if (q.standard === "NSBU") selectedStandard.value = "NSBU";
  if (q.report === "PL" || q.report === "CF") selectedReportType.value = q.report;
  await loadReport();
});

watch([selectedCompanyCode, selectedStandard, selectedReportType], async () => {
  router.replace({
    query: {
      ...route.query,
      company: selectedCompanyCode.value,
      standard: selectedStandard.value,
      report: selectedReportType.value,
    },
  }).catch(() => {});
  await loadReport();
});
</script>

<template>
  <div class="uza-page">
    <!-- Page header -->
    <div style="display: flex; align-items: baseline; justify-content: space-between; margin-bottom: 14px;">
      <div>
        <div class="uza-section-label">Финансы</div>
        <h1 style="font-size: 18px; font-weight: 500; color: var(--t1);
                   letter-spacing: -.02em; margin-top: 2px;">
          Детальная аудированная отчётность
          <span style="color: var(--t3); font-weight: 400; font-size: 13px;">
            · МСФО SOFP / P&amp;L / CF
          </span>
        </h1>
      </div>
      <div style="font-size: 11px; color: var(--t3); letter-spacing: .04em;">
        Единицы: млрд сум
      </div>
    </div>

    <!-- KPI band -->
    <div v-if="report?.has_data" class="kpi-row" style="grid-template-columns: repeat(4, 1fr);">
      <div class="kpi2" style="--kpi2-accent: #1D9E75; --kpi2-d: 0ms;">
        <div class="kpi2-lbl">Сопоставлено</div>
        <div class="kpi2-val">
          <span v-count-up="{ value: reportMapped, key: `det-mapped-${selectedCompanyCode}-${selectedReportType}` }">0</span>
        </div>
        <div class="kpi2-sub">из {{ report.rows.length }} строк</div>
      </div>
      <div class="kpi2" style="--kpi2-accent: #EF9F27; --kpi2-d: 80ms;">
        <div class="kpi2-lbl">Без сопоставления</div>
        <div class="kpi2-val">
          <span v-count-up="{ value: reportUnmapped, key: `det-unmapped-${selectedCompanyCode}-${selectedReportType}` }">0</span>
        </div>
        <div class="kpi2-sub">требуется проверка</div>
      </div>
      <div class="kpi2" style="--kpi2-accent: #7F77DD; --kpi2-d: 160ms;">
        <div class="kpi2-lbl">Эталон отсутствует</div>
        <div class="kpi2-val">
          <span v-count-up="{ value: reportMissingCanonical.length, key: `det-missing-${selectedCompanyCode}-${selectedReportType}` }">0</span>
        </div>
        <div class="kpi2-sub">недостающих позиций</div>
      </div>
      <div class="kpi2" style="--kpi2-accent: #378ADD; --kpi2-d: 240ms;">
        <div class="kpi2-lbl">Лет отчёта</div>
        <div class="kpi2-val">
          <span v-count-up="report.years.length">0</span>
        </div>
        <div class="kpi2-sub">{{ report.years.join(", ") }}</div>
      </div>
    </div>

    <!-- Toolbar -->
    <div class="uza-section" style="padding: 14px 18px; margin-bottom: 14px; animation: uzaCardIn .55s cubic-bezier(0.34, 1.2, 0.64, 1) 100ms both;">
      <div style="display: flex; align-items: center; gap: 10px; flex-wrap: wrap;">
        <select v-model="selectedCompanyCode" class="uza-input" style="width: auto; min-width: 200px;">
          <option value="">— компания —</option>
          <option v-for="co in companies" :key="co.code" :value="co.code">
            {{ co.name_short || co.code }}
          </option>
        </select>

        <div class="yr-track yr-track-light">
          <span class="yr-pill" :style="{
            width: '54px',
            transform: `translateX(${selectedStandard === 'IFRS' ? 0 : 54}px)`,
            top: '3px', left: '3px', height: 'calc(100% - 6px)',
          }"></span>
          <button v-for="s in (['IFRS','NSBU'] as const)" :key="s"
                  @click="selectedStandard = s"
                  class="yr-btn" :class="{ active: selectedStandard === s }"
                  style="width: 54px;">{{ s }}</button>
        </div>

        <div class="yr-track yr-track-light">
          <span class="yr-pill" :style="{
            width: '70px',
            transform: `translateX(${selectedReportType === 'PL' ? 0 : selectedReportType === 'BS' ? 70 : 140}px)`,
            top: '3px', left: '3px', height: 'calc(100% - 6px)',
          }"></span>
          <button v-for="t in (['PL','BS','CF'] as const)" :key="t"
                  @click="selectedReportType = t"
                  class="yr-btn" :class="{ active: selectedReportType === t }"
                  style="width: 70px;">
            {{ t === 'BS' ? 'SOFP' : t === 'PL' ? 'P&L' : 'Cash Flow' }}
          </button>
        </div>

        <div style="margin-left: auto; display: flex; gap: 8px;">
          <input ref="fileInput" type="file" accept=".xlsx,.xlsm,.xls" style="display:none"
                 @change="(e) => onFilePicked(e, 'single')" />
          <input ref="bulkFileInput" type="file" accept=".xlsx,.xlsm,.xls" style="display:none"
                 @change="(e) => onFilePicked(e, 'bulk')" />
          <button class="btn-s" @click="bulkFileInput?.click()" :disabled="previewing"
                  style="background: linear-gradient(135deg, #DCFCE7 0%, #BBF7D0 100%);
                         border-color: rgba(29, 158, 117, .35); color: #0F6E56;">
            <span v-if="previewing" class="uza-spinner"
                  style="border-color: rgba(15, 110, 86, .25); border-top-color: #0F6E56;"></span>
            <span v-else>↑↑</span>
            {{ previewing ? "Парсинг…" : "Bulk (все компании)" }}
          </button>
          <button class="btn-p" @click="fileInput?.click()" :disabled="previewing || !selectedCompanyCode">
            <span v-if="previewing" class="uza-spinner"
                  style="border-color: rgba(255,255,255,.30); border-top-color: #fff;"></span>
            <span v-else>↑</span>
            Загрузить (одна)
          </button>
          <button class="btn-s" @click="loadReport" title="Перезагрузить из БД">
            <svg width="13" height="13" viewBox="0 0 14 14" fill="none" stroke="currentColor"
                 stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
              <path d="M2 5a5 5 0 0 1 9-1l1 1M12 9a5 5 0 0 1-9 1l-1-1"/>
              <path d="M11 1v3h-3M3 13v-3h3"/>
            </svg>
          </button>
        </div>
      </div>
    </div>

    <!-- Diagnostics banner -->
    <div v-if="report?.has_data && (reportUnmapped > 0 || reportMissingCanonical.length > 0)"
         style="margin-bottom: 14px; padding: 12px 16px; border-radius: 12px;
                background: linear-gradient(135deg, rgba(239, 159, 39, .08), rgba(239, 159, 39, .04));
                border: 1px solid rgba(239, 159, 39, .25);
                font-size: 12px; color: #854F0B;
                display: flex; align-items: center; gap: 12px;
                animation: paRateIn .42s cubic-bezier(0.34, 1.2, 0.64, 1) both;">
      <span style="display: inline-block; width: 7px; height: 7px; border-radius: 50%;
                   background: #EF9F27; flex-shrink: 0;
                   box-shadow: 0 0 8px rgba(239, 159, 39, .55);"></span>
      <div style="flex: 1;">
        <span v-if="reportUnmapped > 0" style="margin-right: 16px;">
          <strong>{{ reportUnmapped }}</strong> строк без сопоставления с эталонной схемой
        </span>
        <span v-if="reportMissingCanonical.length > 0">
          <strong>{{ reportMissingCanonical.length }}</strong> эталонных позиций отсутствуют
        </span>
      </div>
    </div>

    <div v-if="error"
         style="margin-bottom: 14px; padding: 12px 16px; border-radius: 12px;
                background: rgba(239, 68, 68, .06); border: 1px solid rgba(239, 68, 68, .25);
                color: #B91C1C; font-size: 13px;">
      {{ error }}
    </div>

    <!-- Empty state -->
    <div v-if="!loading && (!report || !report.has_data)"
         class="uza-card" style="padding: 60px 24px; text-align: center; --uza-accent: #7F77DD;">
      <div style="width: 56px; height: 56px; border-radius: 14px;
                  background: rgba(127,119,221,.12); color: #7F77DD;
                  display: inline-flex; align-items: center; justify-content: center;
                  margin-bottom: 16px;">
        <svg width="26" height="26" viewBox="0 0 24 24" fill="none" stroke="currentColor"
             stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
          <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>
          <path d="M14 2v6h6M16 13H8M16 17H8M10 9H8"/>
        </svg>
      </div>
      <div style="font-size: 15px; color: var(--t1); font-weight: 500; margin-bottom: 6px;">
        Нет данных детальной отчётности
      </div>
      <div style="font-size: 12px; color: var(--t3); max-width: 480px; margin: 0 auto 20px;
                  line-height: 1.55;">
        Загрузите Excel с аудированной отчётностью.
        <strong style="color: var(--t2);">Bulk</strong> — общий файл со всеми компаниями
        (имена листов = коды компаний).
        <strong style="color: var(--t2);">Одна</strong> — для одного аудит-файла.
        Перед записью в БД откроется окно предпросмотра.
      </div>
      <div style="display: flex; gap: 10px; justify-content: center;">
        <button class="btn-s" @click="bulkFileInput?.click()"
                style="background: linear-gradient(135deg, #DCFCE7 0%, #BBF7D0 100%);
                       border-color: rgba(29, 158, 117, .35); color: #0F6E56;">
          ↑↑ Bulk (все компании)
        </button>
        <button class="btn-p" @click="fileInput?.click()" :disabled="!selectedCompanyCode">
          ↑ Загрузить (одна)
        </button>
      </div>
    </div>

    <!-- Saved grid -->
    <div v-else-if="!loading && report && report.has_data"
         class="uza-section" style="padding: 0; overflow: hidden;
                                    animation: uzaCardIn .55s cubic-bezier(0.34, 1.2, 0.64, 1) 200ms both;">
      <div style="overflow-x: auto;">
        <table class="uza-table">
          <thead>
            <tr>
              <th style="min-width: 320px; position: sticky; left: 0; z-index: 2;">Показатель</th>
              <th style="width: 200px;">Эталон</th>
              <th v-for="y in report.years" :key="y" class="num" style="min-width: 110px;">{{ y }}</th>
              <th style="width: 36px;"></th>
            </tr>
          </thead>
          <tbody>
            <template v-for="(g, gi) in grouped" :key="gi">
              <tr v-if="g.section" style="background: rgba(127, 119, 221, .04);">
                <td :colspan="report.years.length + 3"
                    style="padding: 7px 14px; font-size: 10px; font-weight: 600;
                           text-transform: uppercase; letter-spacing: .07em;
                           color: #7F77DD; border-bottom: 1px solid rgba(127, 119, 221, .12);">
                  {{ g.section }}
                </td>
              </tr>
              <tr v-for="row in g.rows" :key="row.code"
                  class="group"
                  :style="{
                    background: row.is_unmapped ? 'rgba(239, 159, 39, .04)'
                                  : (row.is_subtotal ? 'rgba(127, 119, 221, .03)' : 'transparent'),
                    fontWeight: row.is_subtotal ? 500 : 400,
                  }">
                <td :style="{ paddingLeft: `${14 + row.indent * 12}px`,
                              position: 'sticky', left: 0, zIndex: 1,
                              background: row.is_unmapped ? '#FEF8EE'
                                          : (row.is_subtotal ? '#FAFAFE' : '#fff') }">
                  <div style="display: flex; align-items: center; gap: 6px;">
                    <span v-if="row.is_unmapped" class="uza-dot uza-dot-mid"
                          title="Без сопоставления с эталонной схемой"
                          style="margin-right: 0; width: 6px; height: 6px;"></span>
                    <input
                      type="text" :value="row.label"
                      @blur="renameLine(row, ($event.target as HTMLInputElement).value)"
                      style="flex: 1; min-width: 0; background: transparent; outline: none;
                             border: 1px solid transparent; border-radius: 6px;
                             padding: 3px 6px; font-size: 13px; color: var(--t1);
                             font-family: var(--font);
                             transition: border-color .12s, background .12s;"
                      :style="{ fontWeight: row.is_subtotal ? 500 : 400 }"
                      onfocus="this.style.background='#fff'; this.style.borderColor='rgba(124,111,247,.45)'"
                      onblur="this.style.background='transparent'; this.style.borderColor='transparent'"
                    />
                  </div>
                </td>
                <td>
                  <select :value="row.canonical_code || ''"
                          @change="changeMapping(row, ($event.target as HTMLSelectElement).value || null)"
                          style="font-size: 11px; padding: 3px 8px; border-radius: 6px;
                                 width: 100%; font-family: var(--font); cursor: pointer;
                                 transition: all .12s;"
                          :style="row.canonical_code
                            ? 'background: #E1F5EE; border: 1px solid rgba(15, 110, 86, .25); color: #0F6E56;'
                            : 'background: #FAEEDA; border: 1px solid rgba(133, 79, 11, .25); color: #854F0B;'">
                    <option value="">— не сопоставлено —</option>
                    <option v-for="c in catalog?.[selectedReportType] || []" :key="c.code" :value="c.code"
                            style="background: var(--bg1, #fff); color: var(--t1, #0F172A);">
                      {{ c.code }} · {{ c.label }}
                    </option>
                  </select>
                </td>
                <td v-for="y in report.years" :key="y" class="num">
                  <input type="text"
                         :value="row.values[y] !== null && row.values[y] !== undefined ? row.values[y] : ''"
                         @blur="saveCell(row, y, ($event.target as HTMLInputElement).value)"
                         @keydown.enter="($event.target as HTMLInputElement).blur()"
                         placeholder="—"
                         style="width: 100%; text-align: right; padding: 3px 6px;
                                background: transparent; border: 1px solid transparent;
                                border-radius: 6px; outline: none;
                                font-family: var(--font); font-size: 13px;
                                font-variant-numeric: tabular-nums;
                                transition: border-color .12s, background .12s;"
                         :style="{ fontWeight: row.is_subtotal ? 500 : 400 }"
                         onfocus="this.style.background='#fff'; this.style.borderColor='rgba(124,111,247,.45)'"
                         onblur="this.style.background='transparent'; this.style.borderColor='transparent'" />
                </td>
                <td style="text-align: center;">
                  <button @click="removeLine(row)"
                          class="row-delete-btn"
                          style="opacity: 0; padding: 0; width: 22px; height: 22px;
                                 border: none; background: transparent;
                                 border-radius: 5px; color: var(--t3); cursor: pointer;
                                 transition: all .12s; font-size: 14px; line-height: 1;"
                          title="Удалить строку">×</button>
                </td>
              </tr>
            </template>
          </tbody>
        </table>
      </div>

      <div v-if="reportMissingCanonical.length > 0"
           style="padding: 14px 18px; border-top: 1px solid rgba(15, 23, 60, .06);
                  background: var(--bg2, #FAFAFC);">
        <div class="uza-section-label" style="margin-bottom: 6px;">
          Отсутствующие эталонные позиции ({{ reportMissingCanonical.length }})
        </div>
        <div style="display: flex; flex-wrap: wrap; gap: 5px;">
          <span v-for="code in reportMissingCanonical" :key="code"
                class="uza-pill uza-pill-purple"
                :title="canonicalLineByCode(selectedReportType, code)?.label || code">
            {{ code }}
          </span>
        </div>
      </div>

      <div style="padding: 9px 18px; font-size: 10px; color: var(--t3);
                  border-top: 1px solid rgba(15, 23, 60, .04);
                  display: flex; align-items: center; gap: 12px;">
        <span v-if="report.source_filename">Источник: {{ report.source_filename }}</span>
        <span v-if="report.imported_at">Загружено: {{ fmt.fmtDateTime(report.imported_at) }}</span>
        <span style="margin-left: auto; color: var(--t3);">
          Изменения сохраняются автоматически
        </span>
      </div>
    </div>

    <div v-else style="text-align: center; padding: 80px 0;">
      <span class="uza-spinner" style="width: 24px; height: 24px;"></span>
      <div style="font-size: 12px; color: var(--t3); margin-top: 12px;">Загрузка…</div>
    </div>


    <!-- ════════════════════════════════════════════
         PREVIEW MODAL
         ════════════════════════════════════════════ -->
    <div v-if="preview" class="uza-modal-backdrop" @click.self="closePreview">
      <div class="uza-modal-card size-xl" style="max-height: 92vh;">
        <!-- Header -->
        <div class="uza-modal-header">
          <div>
            <div class="uza-modal-sub">Предпросмотр импорта</div>
            <h2>{{ preview.filename }}</h2>
          </div>
          <div style="display: flex; align-items: center; gap: 16px;">
            <div style="font-size: 12px; color: var(--t2); display: flex; gap: 14px;
                        font-variant-numeric: tabular-nums;">
              <span><strong style="color: var(--t1);">{{ preview.summary.sheets }}</strong> компаний</span>
              <span><strong style="color: var(--t1);">{{ preview.summary.sections }}</strong> секций</span>
              <span><strong style="color: var(--t1);">{{ preview.summary.rows }}</strong> строк</span>
              <span v-if="preview.summary.unmapped_rows > 0" style="color: #854F0B;">
                <strong>{{ preview.summary.unmapped_rows }}</strong> без сопоставления
              </span>
            </div>
            <button class="uza-modal-close" @click="closePreview">×</button>
          </div>
        </div>

        <!-- Body: split layout -->
        <div style="flex: 1; display: flex; overflow: hidden; min-height: 0;">
          <!-- Sheet list -->
          <div style="width: 220px; border-right: 1px solid rgba(15, 23, 60, .06);
                      overflow-y: auto; background: var(--bg2, #FAFAFC);">
            <div class="uza-section-label" style="padding: 12px 14px 6px;">Компании</div>
            <button v-for="(sh, si) in preview.sheets" :key="sh.sheet_name"
                    @click="previewActiveSheet = si; previewActiveSection = 0"
                    style="display: block; width: 100%; text-align: left;
                           padding: 9px 14px; border: none; background: transparent;
                           border-bottom: 1px solid rgba(15, 23, 60, .04);
                           font-size: 12px; cursor: pointer; transition: background .12s;
                           font-family: var(--font);"
                    :style="previewActiveSheet === si
                      ? 'background: var(--bg1, #fff); color: var(--t1); font-weight: 500;'
                      : 'color: var(--t2);'">
              <div style="display: flex; justify-content: space-between; align-items: center;">
                <span style="font-weight: 600;">{{ sh.company_code.toUpperCase() }}</span>
                <span v-if="sh.sections.some(s => s.unmapped_count > 0)"
                      class="uza-dot uza-dot-mid"
                      style="margin-right: 0;"
                      title="Есть строки без сопоставления"></span>
              </div>
              <div style="font-size: 10px; color: var(--t3); margin-top: 1px;
                          overflow: hidden; text-overflow: ellipsis; white-space: nowrap;">
                {{ sh.company_name }}
              </div>
            </button>
          </div>

          <!-- Section content -->
          <div style="flex: 1; display: flex; flex-direction: column; overflow: hidden; min-width: 0;">
            <!-- Section tabs -->
            <div v-if="preview.sheets[previewActiveSheet]"
                 style="border-bottom: 1px solid rgba(15, 23, 60, .06);
                        padding: 10px 16px; display: flex; gap: 6px;
                        background: var(--bg1, #fff); flex-shrink: 0;">
              <button v-for="(sec, sei) in preview.sheets[previewActiveSheet].sections" :key="sei"
                      @click="previewActiveSection = sei"
                      style="padding: 5px 11px; border-radius: 8px;
                             font-size: 12px; font-family: var(--font);
                             border: 1px solid transparent; cursor: pointer;
                             display: inline-flex; align-items: center; gap: 6px;
                             transition: all .12s;"
                      :style="previewActiveSection === sei
                        ? 'background: linear-gradient(135deg, #8B7FFF 0%, #6C5CE7 100%); color: #fff; border-color: transparent; box-shadow: 0 2px 8px rgba(108, 92, 231, .30);'
                        : 'background: rgba(124, 111, 247, .06); color: var(--t2); border-color: rgba(124, 111, 247, .14);'">
                <span style="font-weight: 500;">
                  {{ sec.report_type === 'BS' ? 'SOFP' : sec.report_type === 'PL' ? 'P&L' : 'Cash Flow' }}
                </span>
                <span style="font-size: 10px; opacity: .85;
                             font-variant-numeric: tabular-nums;">
                  {{ previewSectionMappedCount(sec) }}/{{ sec.rows.length }}
                </span>
                <span v-if="sec.unmapped_count > 0"
                      style="display: inline-block; width: 5px; height: 5px;
                             border-radius: 50%; background: #EF9F27;"></span>
              </button>
            </div>

            <!-- Section grid -->
            <div style="flex: 1; overflow: auto; min-height: 0;"
                 v-if="preview.sheets[previewActiveSheet]?.sections[previewActiveSection]">
              <table class="uza-table">
                <thead>
                  <tr>
                    <th style="min-width: 280px;">Строка из Excel</th>
                    <th style="width: 200px;">Сопоставление с эталоном</th>
                    <th v-for="y in preview.sheets[previewActiveSheet].sections[previewActiveSection].years" :key="y"
                        class="num" style="min-width: 95px;">{{ y }}</th>
                    <th style="width: 36px;"></th>
                  </tr>
                </thead>
                <tbody>
                  <tr v-for="(row, ri) in preview.sheets[previewActiveSheet].sections[previewActiveSection].rows"
                      :key="ri"
                      :style="{
                        background: row.is_unmapped ? 'rgba(239, 159, 39, .04)'
                                      : (row.is_subtotal ? 'rgba(127, 119, 221, .03)' : 'transparent'),
                      }">
                    <td :style="{ paddingLeft: `${12 + row.indent_level * 10}px` }">
                      <div style="display: flex; align-items: center; gap: 6px;">
                        <span v-if="row.is_unmapped" class="uza-dot uza-dot-mid"
                              style="margin-right: 0; width: 6px; height: 6px;"
                              title="Без сопоставления"></span>
                        <input type="text" v-model="row.label"
                               style="flex: 1; min-width: 0; background: transparent; outline: none;
                                      border: 1px solid transparent; border-radius: 6px;
                                      padding: 3px 6px; font-size: 12.5px; color: var(--t1);
                                      font-family: var(--font);"
                               :style="{ fontWeight: row.is_subtotal ? 500 : 400 }"
                               onfocus="this.style.background='#fff'; this.style.borderColor='rgba(124,111,247,.45)'"
                               onblur="this.style.background='transparent'; this.style.borderColor='transparent'" />
                      </div>
                      <div v-if="row.section_label"
                           style="font-size: 10px; color: var(--t3); margin-left: 14px; margin-top: 1px;">
                        ↳ {{ row.section_label }}
                      </div>
                    </td>
                    <td>
                      <select :value="row.canonical_code || ''"
                              @change="previewRowMappingChange(row, ($event.target as HTMLSelectElement).value || null)"
                              style="font-size: 10.5px; padding: 3px 7px; border-radius: 6px;
                                     width: 100%; font-family: var(--font); cursor: pointer;"
                              :style="row.canonical_code
                                ? 'background: #E1F5EE; border: 1px solid rgba(15,110,86,.25); color: #0F6E56;'
                                : 'background: #FAEEDA; border: 1px solid rgba(133,79,11,.25); color: #854F0B;'">
                        <option value="">— не сопоставлено —</option>
                        <option v-for="c in catalog?.[preview.sheets[previewActiveSheet].sections[previewActiveSection].report_type] || []"
                                :key="c.code" :value="c.code"
                                style="background: var(--bg1, #fff); color: var(--t1, #0F172A);">
                          {{ c.code }}
                        </option>
                      </select>
                    </td>
                    <td v-for="y in preview.sheets[previewActiveSheet].sections[previewActiveSection].years"
                        :key="y" class="num">
                      <input type="text"
                             :value="row.values[String(y)] !== null && row.values[String(y)] !== undefined ? row.values[String(y)] : ''"
                             @input="(e) => {
                               const v = (e.target as HTMLInputElement).value.replace(/\s+/g, '').replace(',', '.');
                               row.values[String(y)] = v === '' || v === '—' ? null : (Number.isFinite(Number(v)) ? Number(v) : row.values[String(y)]);
                             }"
                             placeholder="—"
                             style="width: 100%; text-align: right; padding: 3px 6px;
                                    background: transparent; border: 1px solid transparent;
                                    border-radius: 6px; outline: none;
                                    font-family: var(--font); font-size: 12.5px;
                                    font-variant-numeric: tabular-nums;"
                             :style="{ fontWeight: row.is_subtotal ? 500 : 400 }"
                             onfocus="this.style.background='#fff'; this.style.borderColor='rgba(124,111,247,.45)'"
                             onblur="this.style.background='transparent'; this.style.borderColor='transparent'" />
                    </td>
                    <td style="text-align: center;">
                      <button @click="deletePreviewRow(previewActiveSheet, previewActiveSection, ri)"
                              style="padding: 0; width: 22px; height: 22px;
                                     border: none; background: transparent;
                                     color: var(--t3); cursor: pointer;
                                     border-radius: 5px; transition: all .12s;
                                     font-size: 14px; line-height: 1;"
                              onmouseover="this.style.background='rgba(239,68,68,.10)'; this.style.color='#EF4444'"
                              onmouseout="this.style.background='transparent'; this.style.color='var(--t3)'"
                              title="Удалить строку из импорта">×</button>
                    </td>
                  </tr>
                </tbody>
              </table>

              <div v-if="previewSectionMissing(preview.sheets[previewActiveSheet].sections[previewActiveSection]).length > 0"
                   style="padding: 12px 16px; border-top: 1px solid rgba(15, 23, 60, .06);
                          background: var(--bg2, #FAFAFC);">
                <div class="uza-section-label" style="margin-bottom: 6px;">
                  Отсутствующие эталонные позиции
                  ({{ previewSectionMissing(preview.sheets[previewActiveSheet].sections[previewActiveSection]).length }})
                </div>
                <div style="display: flex; flex-wrap: wrap; gap: 5px;">
                  <span v-for="code in previewSectionMissing(preview.sheets[previewActiveSheet].sections[previewActiveSection])"
                        :key="code"
                        class="uza-pill uza-pill-purple"
                        :title="canonicalLineByCode(preview.sheets[previewActiveSheet].sections[previewActiveSection].report_type, code)?.label || code">
                    {{ code }}
                  </span>
                </div>
              </div>
            </div>
          </div>
        </div>

        <!-- Footer -->
        <div class="uza-modal-footer">
          <div style="font-size: 11px; color: var(--t3); display: flex; gap: 14px;">
            <span style="display: inline-flex; align-items: center; gap: 5px;">
              <span class="uza-dot uza-dot-mid" style="margin-right: 0;"></span>
              без сопоставления — нужно проверить
            </span>
            <span style="display: inline-flex; align-items: center; gap: 5px;">
              <span class="uza-dot uza-dot-good" style="margin-right: 0;"></span>
              сопоставлено с эталонной схемой
            </span>
          </div>
          <div style="display: flex; gap: 8px;">
            <button class="btn-s" @click="closePreview" :disabled="confirming">Отмена</button>
            <button class="btn-p" @click="confirmImport" :disabled="confirming">
              <span v-if="confirming" class="uza-spinner"
                    style="border-color: rgba(255,255,255,.30); border-top-color: #fff;"></span>
              <span v-else>✓</span>
              {{ confirming ? "Запись…" : "Подтвердить и импортировать" }}
            </button>
          </div>
        </div>
      </div>
    </div>

    <!-- Preview error -->
    <div v-if="previewError" class="uza-modal-backdrop" @click.self="previewError = null">
      <div class="uza-modal-card" style="width: min(440px, 96vw); padding: 0;">
        <div class="uza-modal-header">
          <div>
            <div class="uza-modal-sub" style="color: #B91C1C;">Ошибка</div>
            <h2 style="color: #B91C1C;">Не удалось распарсить файл</h2>
          </div>
          <button class="uza-modal-close" @click="previewError = null">×</button>
        </div>
        <div class="uza-modal-body">
          <div style="font-size: 13px; color: var(--t2); line-height: 1.55;">
            {{ previewError }}
          </div>
        </div>
        <div class="uza-modal-footer" style="justify-content: flex-end;">
          <button class="btn-s" @click="previewError = null">Закрыть</button>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
/* Delete-button hover reveal — scoped to keep the rest of the table clean */
tr:hover .row-delete-btn { opacity: 1 !important; }
.row-delete-btn:hover {
  background: rgba(239, 68, 68, .10) !important;
  color: #EF4444 !important;
}
</style>
