<script setup lang="ts">
/**
 * ExcelImportModal — bulk-import кредитов из XLSX/XLS.
 *
 * Workflow:
 *   1. Drag/drop или выбор файла → parseExcelFile() через dynamic import("xlsx")
 *   2. Preview таблица первых 8 строк + total count + validation errors
 *   3. Toggle overwrite_existing
 *   4. Submit → POST /loans/bulk → показ результата (inserted/updated/skipped/errors)
 *   5. Close → reload loans автоматически если что-то импортировано
 *
 * Маппинг Excel колонок → LoanBulkItem поля по header name (RU/EN aliases в composable).
 */
import { computed, ref } from "vue";
import { useCreditData } from "@/composables/useCreditData";
import { fmtMoneyShort, toNum } from "@/api/credit";

const credit = useCreditData();

const isOpen = computed(() => credit.excelImportOpen.value);
const rows = computed(() => credit.excelImportRows.value);
const fileName = computed(() => credit.excelImportFileName.value);
const parseErrors = computed(() => credit.excelImportParseErrors.value);
const result = computed(() => credit.excelImportResult.value);
const submitting = computed(() => credit.excelImportSubmitting.value);

const fileInput = ref<HTMLInputElement | null>(null);
const dragOver = ref(false);

const totalRows = computed(() => rows.value.length);
const validRows = computed(() => {
  return rows.value.filter((r) => r.loan_code && r.bank && r.currency &&
    (r.company_id || r.company_code || r.company_name_ru),
  ).length;
});

const previewRows = computed(() => rows.value.slice(0, 8));

function pickFile() {
  fileInput.value?.click();
}

async function onFileSelected(e: Event) {
  const input = e.target as HTMLInputElement;
  const file = input.files?.[0];
  if (file) await credit.parseExcelFile(file);
  input.value = "";
}

async function onFileDrop(e: DragEvent) {
  e.preventDefault();
  dragOver.value = false;
  const file = e.dataTransfer?.files?.[0];
  if (file) await credit.parseExcelFile(file);
}

function onDragOver(e: DragEvent) { e.preventDefault(); dragOver.value = true; }
function onDragLeave() { dragOver.value = false; }

async function onSubmit() {
  await credit.submitExcelImport();
}

function onClose() {
  credit.closeExcelImport();
}

function onBackdropClick(e: MouseEvent) {
  if (e.target === e.currentTarget) onClose();
}

function fmtCell(v: any, field: string): string {
  if (v === null || v === undefined || v === "") return "—";
  if (field === "rate") return (toNum(v) * 100).toFixed(2) + "%";
  if (field === "debt_usd" || field === "debt_currency" || field === "sum_total" || field === "sum_disbursed") {
    return fmtMoneyShort(v);
  }
  if (typeof v === "boolean") return v ? "✓" : "—";
  return String(v);
}
</script>

<template>
  <Transition name="uza-modal" appear>
  <Transition name="cp-xl-fade">
    <div v-if="isOpen" class="cp-xl-backdrop" @click="onBackdropClick">
      <Transition name="cp-xl-pop">
        <div v-if="isOpen" class="cp-xl-modal" @click.stop>
          <!-- Header -->
          <div class="cp-xl-h">
            <div class="cp-xl-h-text">
              <div class="cp-xl-h-title">Импорт кредитов из Excel</div>
              <div class="cp-xl-h-sub">XLSX или XLS · первая строка = заголовки</div>
            </div>
            <button class="cp-xl-close" @click="onClose">
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round">
                <line x1="6" y1="6" x2="18" y2="18"/>
                <line x1="18" y1="6" x2="6" y2="18"/>
              </svg>
            </button>
          </div>

          <!-- Body -->
          <div class="cp-xl-body">
            <!-- Upload zone (если файл не загружен) -->
            <div
              v-if="rows.length === 0 && parseErrors.length === 0"
              :class="['cp-xl-drop', { 'cp-xl-drop-active': dragOver }]"
              @click="pickFile"
              @drop="onFileDrop"
              @dragover="onDragOver"
              @dragleave="onDragLeave"
            >
              <svg width="42" height="42" viewBox="0 0 24 24" fill="none" stroke="#7F77DD" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
                <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>
                <polyline points="14 2 14 8 20 8"/>
                <line x1="12" y1="18" x2="12" y2="12"/>
                <polyline points="9 15 12 12 15 15"/>
              </svg>
              <div class="cp-xl-drop-title">Перетащите XLSX-файл сюда</div>
              <div class="cp-xl-drop-sub">или кликните для выбора</div>
              <input
                ref="fileInput"
                type="file"
                accept=".xlsx,.xls"
                style="display:none"
                @change="onFileSelected"
              />
            </div>

            <!-- Parse errors -->
            <div v-if="parseErrors.length > 0" class="cp-xl-parse-err">
              <div class="cp-xl-parse-err-title">
                Ошибка парсинга {{ fileName ? "· " + fileName : "" }}
              </div>
              <ul>
                <li v-for="(e, i) in parseErrors" :key="i">{{ e }}</li>
              </ul>
              <button class="cp-xl-btn-cancel" @click="pickFile">Выбрать другой файл</button>
            </div>

            <!-- Preview (если строки распарсены) -->
            <div v-if="rows.length > 0">
              <!-- Summary bar -->
              <div class="cp-xl-summary">
                <div class="cp-xl-summary-stat">
                  <span class="cp-xl-summary-num">{{ totalRows }}</span>
                  <span class="cp-xl-summary-lbl">строк прочитано</span>
                </div>
                <div class="cp-xl-summary-stat" :style="{ color: validRows === totalRows ? '#1D9E75' : '#EF9F27' }">
                  <span class="cp-xl-summary-num">{{ validRows }}</span>
                  <span class="cp-xl-summary-lbl">валидных</span>
                </div>
                <div v-if="validRows < totalRows" class="cp-xl-summary-stat" style="color:#C97070">
                  <span class="cp-xl-summary-num">{{ totalRows - validRows }}</span>
                  <span class="cp-xl-summary-lbl">с ошибками</span>
                </div>
                <div class="cp-xl-summary-file">{{ fileName }}</div>
              </div>

              <!-- Validation errors list -->
              <div v-if="parseErrors.length > 0 && rows.length > 0" class="cp-xl-warn">
                <div class="cp-xl-warn-title">
                  Внимание · {{ parseErrors.length }} {{ parseErrors.length === 1 ? "проблема" : "проблем" }}:
                </div>
                <ul class="cp-xl-warn-list">
                  <li v-for="(e, i) in parseErrors.slice(0, 5)" :key="i">{{ e }}</li>
                  <li v-if="parseErrors.length > 5">… ещё {{ parseErrors.length - 5 }}</li>
                </ul>
              </div>

              <!-- Preview table -->
              <div class="cp-xl-table-wrap">
                <table class="cp-xl-table">
                  <thead>
                    <tr>
                      <th>#</th>
                      <th>Код</th>
                      <th>Компания</th>
                      <th>Банк</th>
                      <th>Валюта</th>
                      <th>Ставка</th>
                      <th>Долг USD</th>
                      <th>Срок</th>
                    </tr>
                  </thead>
                  <tbody>
                    <tr v-for="(r, i) in previewRows" :key="i">
                      <td class="cp-xl-rank">{{ i + 1 }}</td>
                      <td>{{ r.loan_code || '—' }}</td>
                      <td :title="r.company_name_ru || r.company_code || '—'">
                        {{ (r.company_name_ru || r.company_code || '—').slice(0, 20) }}
                      </td>
                      <td :title="r.bank || ''">{{ (r.bank || '—').slice(0, 22) }}</td>
                      <td>{{ r.currency || '—' }}</td>
                      <td>{{ fmtCell(r.rate, 'rate') }}</td>
                      <td>{{ fmtCell(r.debt_usd, 'debt_usd') }}</td>
                      <td>{{ r.date_due || '—' }}</td>
                    </tr>
                  </tbody>
                </table>
                <div v-if="totalRows > 8" class="cp-xl-more">
                  … ещё {{ totalRows - 8 }} строк
                </div>
              </div>

              <!-- Overwrite toggle -->
              <label class="cp-xl-overwrite">
                <input
                  type="checkbox"
                  :checked="credit.excelImportOverwrite.value"
                  @change="credit.excelImportOverwrite.value = ($event.target as HTMLInputElement).checked"
                />
                <span>
                  <b>Перезаписать существующие</b> — кредиты с тем же loan_code будут обновлены.
                  <small>Иначе — пропущены.</small>
                </span>
              </label>
            </div>

            <!-- Result (после submit) -->
            <div v-if="result" class="cp-xl-result">
              <div class="cp-xl-result-h">
                <svg v-if="result.errors.length === 0" width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="#1D9E75" stroke-width="2" stroke-linecap="round">
                  <polyline points="20 6 9 17 4 12"/>
                </svg>
                <svg v-else width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="#EF9F27" stroke-width="2" stroke-linecap="round">
                  <path d="M12 9v3.5M12 16h.01M3.86 4h16.28a2 2 0 011.78 2.94l-8.14 13.5a2 2 0 01-3.56 0L2.08 6.94A2 2 0 013.86 4z"/>
                </svg>
                Импорт завершён
              </div>
              <div class="cp-xl-result-stats">
                <div><b style="color:#1D9E75">{{ result.inserted }}</b> создано</div>
                <div><b style="color:#7F77DD">{{ result.updated }}</b> обновлено</div>
                <div v-if="result.skipped"><b style="color:#888780">{{ result.skipped }}</b> пропущено</div>
              </div>
              <div v-if="result.errors.length > 0" class="cp-xl-result-errs">
                <div class="cp-xl-result-errs-title">{{ result.errors.length }} ошибок:</div>
                <ul>
                  <li v-for="(e, i) in result.errors.slice(0, 8)" :key="i">{{ e }}</li>
                  <li v-if="result.errors.length > 8">… ещё {{ result.errors.length - 8 }}</li>
                </ul>
              </div>
            </div>
          </div>

          <!-- Footer -->
          <div class="cp-xl-foot">
            <span v-if="!result" class="cp-xl-foot-hint">
              <span v-if="rows.length > 0">
                Будет {{ credit.excelImportOverwrite.value ? "обновлено или создано" : "создано (существующие будут пропущены)" }}: {{ validRows }} кредитов
              </span>
              <span v-else>
                Поддерживается XLSX / XLS · колонки: loan_code, company_name_ru, bank, currency, rate, debt_usd, date_due, …
              </span>
            </span>
            <button class="cp-xl-btn-cancel" @click="onClose">
              {{ result ? "Закрыть" : "Отмена" }}
            </button>
            <button
              v-if="rows.length > 0 && !result"
              class="cp-xl-btn-save"
              :disabled="submitting || validRows === 0"
              @click="onSubmit"
            >
              <span v-if="submitting" class="cp-xl-btn-spinner"/>
              {{ submitting ? "Импорт…" : `Импортировать ${validRows}` }}
            </button>
          </div>
        </div>
      </Transition>
    </div>
  </Transition>
  </Transition>
</template>

<style scoped>
.cp-xl-backdrop {
  position: fixed;
  inset: 0;
  background: rgba(15, 18, 40, 0.45);
  backdrop-filter: blur(8px);
  z-index: 1100;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 24px;
}

.cp-xl-fade-enter-active,
.cp-xl-fade-leave-active { transition: opacity 0.2s ease; }
.cp-xl-fade-enter-from, .cp-xl-fade-leave-to { opacity: 0; }

.cp-xl-modal {
  width: 100%;
  max-width: 820px;
  max-height: 90vh;
  background: #fff;
  border-radius: 16px;
  display: flex;
  flex-direction: column;
  box-shadow: 0 24px 64px rgba(15, 23, 60, 0.32);
  overflow: hidden;
}

.cp-xl-pop-enter-active,
.cp-xl-pop-leave-active {
  transition: opacity 0.2s ease, transform 0.35s cubic-bezier(0.34, 1.2, 0.64, 1);
}
.cp-xl-pop-enter-from, .cp-xl-pop-leave-to {
  opacity: 0;
  transform: scale(0.96);
}

/* Header */
.cp-xl-h {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 18px 22px 14px;
  border-bottom: 1px solid rgba(0, 0, 0, 0.06);
  flex-shrink: 0;
}
.cp-xl-h-text { flex: 1; min-width: 0; }
.cp-xl-h-title {
  font-size: 16px;
  font-weight: 500;
  color: var(--t1, #1e2a4a);
  letter-spacing: -0.01em;
  margin-bottom: 2px;
}
.cp-xl-h-sub {
  font-size: 10.5px;
  color: var(--t3, #888780);
  text-transform: uppercase;
  letter-spacing: 0.04em;
  font-weight: 500;
}
.cp-xl-close {
  width: 32px; height: 32px;
  border: none;
  background: transparent;
  color: var(--t2, #555c6e);
  cursor: pointer;
  border-radius: 8px;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: background 0.14s;
}
.cp-xl-close:hover { background: rgba(0, 0, 0, 0.05); }

/* Body */
.cp-xl-body {
  flex: 1;
  overflow-y: auto;
  padding: 18px 22px;
}

/* Drop zone */
.cp-xl-drop {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 8px;
  padding: 60px 24px;
  border: 2px dashed rgba(127, 119, 221, 0.35);
  border-radius: 14px;
  background: rgba(127, 119, 221, 0.04);
  cursor: pointer;
  transition: background 0.16s, border-color 0.16s;
}
.cp-xl-drop:hover,
.cp-xl-drop-active {
  background: rgba(127, 119, 221, 0.08);
  border-color: rgba(127, 119, 221, 0.55);
}
.cp-xl-drop-title {
  margin-top: 8px;
  font-size: 14px;
  font-weight: 500;
  color: var(--t1, #1e2a4a);
  letter-spacing: -0.005em;
}
.cp-xl-drop-sub {
  font-size: 12px;
  color: var(--t3, #888780);
}

/* Parse errors block */
.cp-xl-parse-err {
  background: rgba(201, 112, 112, 0.08);
  border: 1px solid rgba(201, 112, 112, 0.25);
  border-radius: 10px;
  padding: 14px 16px;
}
.cp-xl-parse-err-title {
  font-size: 13px;
  font-weight: 600;
  color: #C53030;
  margin-bottom: 8px;
}
.cp-xl-parse-err ul {
  margin: 0 0 12px 18px;
  font-size: 11.5px;
  color: var(--t2, #555c6e);
  line-height: 1.5;
}

/* Summary */
.cp-xl-summary {
  display: flex;
  align-items: center;
  gap: 18px;
  padding: 12px 14px;
  background: rgba(127, 119, 221, 0.04);
  border: 1px solid rgba(127, 119, 221, 0.15);
  border-radius: 10px;
  margin-bottom: 12px;
}
.cp-xl-summary-stat {
  display: flex;
  flex-direction: column;
  gap: 2px;
}
.cp-xl-summary-num {
  font-size: 22px;
  font-weight: 500;
  letter-spacing: -0.02em;
  font-feature-settings: "tnum";
  line-height: 1;
}
.cp-xl-summary-lbl {
  font-size: 9.5px;
  color: var(--t3, #888780);
  text-transform: uppercase;
  letter-spacing: 0.06em;
}
.cp-xl-summary-file {
  margin-left: auto;
  font-size: 11px;
  color: var(--t2, #555c6e);
  font-style: italic;
  font-feature-settings: "tnum";
}

/* Warning box */
.cp-xl-warn {
  background: rgba(239, 159, 39, 0.08);
  border: 1px solid rgba(239, 159, 39, 0.25);
  border-radius: 10px;
  padding: 12px 14px;
  margin-bottom: 12px;
}
.cp-xl-warn-title {
  font-size: 11.5px;
  font-weight: 600;
  color: #BA7517;
  margin-bottom: 6px;
}
.cp-xl-warn-list {
  margin: 0 0 0 18px;
  font-size: 10.5px;
  color: var(--t2, #555c6e);
  line-height: 1.5;
}

/* Preview table */
.cp-xl-table-wrap {
  border: 1px solid rgba(0, 0, 0, 0.08);
  border-radius: 10px;
  overflow: hidden;
}
.cp-xl-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 11px;
}
.cp-xl-table thead th {
  text-align: left;
  font-size: 9.5px;
  font-weight: 500;
  color: var(--t3, #888780);
  text-transform: uppercase;
  letter-spacing: 0.06em;
  padding: 8px 10px;
  background: rgba(127, 119, 221, 0.04);
  border-bottom: 1px solid rgba(0, 0, 0, 0.06);
  white-space: nowrap;
}
.cp-xl-table tbody td {
  padding: 7px 10px;
  border-bottom: 1px solid rgba(0, 0, 0, 0.04);
  color: var(--t1, #1e2a4a);
  font-feature-settings: "tnum";
}
.cp-xl-table tbody tr:last-child td { border-bottom: none; }
.cp-xl-rank {
  font-size: 10px;
  color: var(--t3, #888780);
  width: 24px;
}
.cp-xl-more {
  padding: 8px;
  text-align: center;
  font-size: 10.5px;
  color: var(--t3, #888780);
  font-style: italic;
  background: rgba(127, 119, 221, 0.02);
}

/* Overwrite toggle */
.cp-xl-overwrite {
  display: flex;
  gap: 8px;
  padding: 10px 14px;
  margin-top: 12px;
  background: rgba(0, 0, 0, 0.02);
  border-radius: 8px;
  cursor: pointer;
  font-size: 11.5px;
  color: var(--t2, #555c6e);
  line-height: 1.4;
}
.cp-xl-overwrite input[type="checkbox"] {
  flex-shrink: 0;
  margin-top: 1px;
  width: 16px;
  height: 16px;
  accent-color: #7F77DD;
}
.cp-xl-overwrite small {
  display: block;
  font-size: 10.5px;
  color: var(--t3, #888780);
  font-style: italic;
  margin-top: 2px;
}

/* Result block */
.cp-xl-result {
  margin-top: 12px;
  padding: 16px 18px;
  background: rgba(127, 119, 221, 0.04);
  border-radius: 10px;
}
.cp-xl-result-h {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 14px;
  font-weight: 500;
  color: var(--t1, #1e2a4a);
  margin-bottom: 10px;
  letter-spacing: -0.005em;
}
.cp-xl-result-stats {
  display: flex;
  gap: 18px;
  font-size: 13px;
  color: var(--t2, #555c6e);
  margin-bottom: 8px;
  font-feature-settings: "tnum";
}
.cp-xl-result-stats b {
  font-size: 18px;
  margin-right: 4px;
}
.cp-xl-result-errs {
  margin-top: 10px;
  padding: 10px 12px;
  background: rgba(201, 112, 112, 0.06);
  border-radius: 8px;
}
.cp-xl-result-errs-title {
  font-size: 11px;
  font-weight: 600;
  color: #C97070;
  margin-bottom: 6px;
}
.cp-xl-result-errs ul {
  margin: 0 0 0 18px;
  font-size: 10.5px;
  color: var(--t2, #555c6e);
  line-height: 1.5;
}

/* Footer */
.cp-xl-foot {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 14px 22px 16px;
  border-top: 1px solid rgba(0, 0, 0, 0.08);
  background: rgba(127, 119, 221, 0.02);
  flex-shrink: 0;
}
.cp-xl-foot-hint {
  flex: 1;
  font-size: 11px;
  color: var(--t3, #888780);
  font-style: italic;
}
.cp-xl-btn-cancel,
.cp-xl-btn-save {
  font-family: inherit;
  font-size: 12px;
  font-weight: 600;
  padding: 9px 16px;
  border-radius: 8px;
  cursor: pointer;
  transition: background 0.14s;
  letter-spacing: -0.005em;
  border: none;
  display: inline-flex;
  align-items: center;
  gap: 6px;
}
.cp-xl-btn-cancel {
  background: transparent;
  color: var(--t2, #555c6e);
  border: 1px solid rgba(0, 0, 0, 0.10);
}
.cp-xl-btn-cancel:hover { background: rgba(0, 0, 0, 0.04); }
.cp-xl-btn-save {
  background: #7F77DD;
  color: #fff;
}
.cp-xl-btn-save:hover { background: #534AB7; }
.cp-xl-btn-save:disabled { opacity: 0.6; cursor: not-allowed; }

.cp-xl-btn-spinner {
  width: 12px; height: 12px;
  border: 2px solid rgba(255, 255, 255, 0.3);
  border-top-color: #fff;
  border-radius: 50%;
  animation: cpXlSpin 0.7s linear infinite;
}
@keyframes cpXlSpin { to { transform: rotate(360deg); } }
</style>
