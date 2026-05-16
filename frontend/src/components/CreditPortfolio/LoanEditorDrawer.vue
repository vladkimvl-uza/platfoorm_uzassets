<script setup lang="ts">
/**
 * LoanEditorDrawer — slide-in справа 520px форма создания/редактирования кредита.
 *
 * Открывается через credit.openLoanEditor(loan?). Если loan — edit mode,
 * иначе create. Backup в localStorage с auto-save (debounce 800ms via watcher
 * в composable). При open показывается banner если есть backup.
 *
 * 4 секции:
 *   1. Основные        — loan_code, company, bank, contract_ref
 *   2. Финансы         — currency, rate, rate_text, sum_total/disbursed,
 *                        debt_currency/usd
 *   3. Сроки           — date_get, date_due
 *   4. Классификация   — lender_type (auto if empty), is_guaranteed,
 *                        borrower_unit, notes
 */
import { computed, watch } from "vue";
import { useCreditData } from "@/composables/useCreditData";
import {
  CP_CURRENCIES,
  CP_LENDER_LABELS,
  toNum,
  type LenderType,
} from "@/api/credit";

const credit = useCreditData();

const isOpen = computed(() => credit.loanEditorOpen.value);
const draft = computed(() => credit.loanEditorDraft.value);
const errors = computed(() => credit.loanEditorErrors.value);
const isEdit = computed(() => credit.loanEditorMode.value === "edit");
const saving = computed(() => credit.loanEditorSaving.value);
const backupBanner = computed(() => credit.loanEditorBackupAvailable.value);

const titleText = computed(() =>
  isEdit.value
    ? `Редактирование · ${draft.value?.loan_code || ""}`
    : "Новый кредит",
);

// Helper to update field directly on draft
function setField<K extends keyof typeof draft.value & string>(field: K, value: any) {
  if (!draft.value) return;
  (draft.value as any)[field] = value;
}

// Compute auto-classified lender_type preview based on bank name
function classifyClient(bank: string): LenderType {
  const b = (bank || "").toLowerCase();
  if (b.includes("евробонд") || b.includes("eurobond")) return "bond";
  if (b.includes("нбу")) return "state";
  if (b.includes("фонд") && (b.includes("реконстр") || b.includes("развит"))) return "state";
  if (b.includes("фрр") || b.includes("шелковог") || b.includes("silk road")) return "state";
  for (const kw of ["china development", "korea exim", "eximbank", "jbic", "ebrd", "world bank", "adb", "aiib", "jica", "kfw", "абр"]) {
    if (b.includes(kw)) return "state";
  }
  for (const kw of ["узпромстрой", "капиталбанк", "алока", "хамкор", "ипотека", "ziraat bank", "kdb bank", "банк развития", "асака", "ситибанк", "микрокредит", "anor bank", "анор", "хумо", "trustbank", "узнацбанк", "узуниверсал", "узагроэкспорт", "узмилбанк", "ткб", "infinbank"]) {
    if (b.includes(kw)) return "local";
  }
  return "foreign";
}

const autoTypeHint = computed<LenderType | null>(() => {
  if (!draft.value || !draft.value.bank || draft.value.lender_type) return null;
  return classifyClient(draft.value.bank);
});

const companies = computed(() =>
  credit.companiesWithLoans.value
    .slice()
    .sort((a, b) => a.company_name_ru.localeCompare(b.company_name_ru)),
);

async function onSave() {
  await credit.saveLoanEditor();
}

function onCancel() {
  credit.closeLoanEditor();
}

function onBackdropClick(e: MouseEvent) {
  if (e.target === e.currentTarget) onCancel();
}

function onKeyDown(e: KeyboardEvent) {
  if (e.key === "Escape" && isOpen.value) onCancel();
}

watch(isOpen, (open) => {
  if (open) document.addEventListener("keydown", onKeyDown);
  else document.removeEventListener("keydown", onKeyDown);
});

// Restore from backup
function onRestore() { credit.restoreLoanEditorBackup(); }
function onDismissBackup() { credit.dismissLoanEditorBackup(); }
</script>

<template>
  <Transition name="uza-modal" appear>
  <Transition name="cp-ed-fade">
    <div
      v-if="isOpen"
      class="cp-ed-backdrop"
      @click="onBackdropClick"
    >
      <Transition name="cp-ed-slide">
        <div v-if="isOpen && draft" class="cp-ed-panel" @click.stop>
          <!-- Header -->
          <div class="cp-ed-h">
            <div class="cp-ed-h-text">
              <div class="cp-ed-h-title">{{ titleText }}</div>
              <div class="cp-ed-h-sub">{{ isEdit ? "Изменения сохраняются по PUT /loans/{id}" : "Создание кредита через POST /loans" }}</div>
            </div>
            <button class="cp-ed-close" @click="onCancel" title="Esc">
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round">
                <line x1="6" y1="6" x2="18" y2="18"/>
                <line x1="18" y1="6" x2="6" y2="18"/>
              </svg>
            </button>
          </div>

          <!-- Backup banner -->
          <div v-if="backupBanner" class="cp-ed-backup">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round">
              <polyline points="1 4 1 10 7 10"/>
              <path d="M3.51 15a9 9 0 1 0 2.13-9.36L1 10"/>
            </svg>
            <span>
              Найден черновик · код "{{ backupBanner.loanCode }}"
              · {{ backupBanner.ageDays === 0 ? "сегодня" : backupBanner.ageDays + " дн. назад" }}
            </span>
            <button class="cp-ed-backup-btn" @click="onRestore">Восстановить</button>
            <button class="cp-ed-backup-x" @click="onDismissBackup" title="Удалить черновик">×</button>
          </div>

          <!-- Form body -->
          <div class="cp-ed-body">
            <!-- Section 1: Основные -->
            <fieldset class="cp-ed-fs">
              <legend>Основные</legend>

              <div class="cp-ed-row">
                <div class="cp-ed-fld">
                  <label class="cp-ed-lbl">Код кредита <span class="cp-ed-req">*</span></label>
                  <input
                    type="text"
                    class="cp-ed-input"
                    :class="{ 'cp-ed-err': errors.loan_code }"
                    :value="draft.loan_code"
                    :disabled="isEdit"
                    placeholder="L001"
                    maxlength="32"
                    @input="setField('loan_code', ($event.target as HTMLInputElement).value)"
                  />
                  <div v-if="errors.loan_code" class="cp-ed-err-msg">{{ errors.loan_code }}</div>
                  <div v-else-if="isEdit" class="cp-ed-hint">Изменить код кредита нельзя</div>
                </div>

                <div class="cp-ed-fld">
                  <label class="cp-ed-lbl">Компания <span class="cp-ed-req">*</span></label>
                  <select
                    class="cp-ed-input"
                    :class="{ 'cp-ed-err': errors.company_id }"
                    :value="draft.company_id"
                    @change="setField('company_id', ($event.target as HTMLSelectElement).value)"
                  >
                    <option value="" disabled>— выберите —</option>
                    <option v-for="c in companies" :key="c.company_id" :value="c.company_id">
                      {{ c.company_name_ru }}
                    </option>
                  </select>
                  <div v-if="errors.company_id" class="cp-ed-err-msg">{{ errors.company_id }}</div>
                </div>
              </div>

              <div class="cp-ed-fld">
                <label class="cp-ed-lbl">Банк / Кредитор <span class="cp-ed-req">*</span></label>
                <input
                  type="text"
                  class="cp-ed-input"
                  :class="{ 'cp-ed-err': errors.bank }"
                  :value="draft.bank"
                  placeholder="АО «Узпромстройбанк»"
                  @input="setField('bank', ($event.target as HTMLInputElement).value)"
                />
                <div v-if="errors.bank" class="cp-ed-err-msg">{{ errors.bank }}</div>
                <div v-else-if="autoTypeHint" class="cp-ed-hint">
                  Автотип: <span :style="{ color: CP_LENDER_LABELS[autoTypeHint].color }">{{ CP_LENDER_LABELS[autoTypeHint].label }}</span>
                </div>
              </div>

              <div class="cp-ed-fld">
                <label class="cp-ed-lbl">Краткое имя банка <small>опц., для группировки</small></label>
                <input
                  type="text"
                  class="cp-ed-input"
                  :value="draft.bank_short_name || ''"
                  placeholder="УПСБ"
                  @input="setField('bank_short_name', ($event.target as HTMLInputElement).value || null)"
                />
              </div>

              <div class="cp-ed-fld">
                <label class="cp-ed-lbl">Договор / Контракт</label>
                <input
                  type="text"
                  class="cp-ed-input"
                  :value="draft.contract_ref || ''"
                  placeholder="№ 12-345 от 10.01.2026"
                  @input="setField('contract_ref', ($event.target as HTMLInputElement).value || null)"
                />
              </div>
            </fieldset>

            <!-- Section 2: Финансы -->
            <fieldset class="cp-ed-fs">
              <legend>Финансы</legend>

              <div class="cp-ed-row">
                <div class="cp-ed-fld">
                  <label class="cp-ed-lbl">Валюта <span class="cp-ed-req">*</span></label>
                  <select
                    class="cp-ed-input"
                    :class="{ 'cp-ed-err': errors.currency }"
                    :value="draft.currency"
                    @change="setField('currency', ($event.target as HTMLSelectElement).value)"
                  >
                    <option v-for="c in CP_CURRENCIES" :key="c" :value="c">{{ c }}</option>
                  </select>
                </div>

                <div class="cp-ed-fld">
                  <label class="cp-ed-lbl">Ставка <small>десятичная: 0.085</small></label>
                  <input
                    type="number"
                    class="cp-ed-input"
                    :class="{ 'cp-ed-err': errors.rate }"
                    step="0.000001"
                    min="0" max="1"
                    :value="draft.rate || ''"
                    placeholder="0.0850"
                    @input="setField('rate', ($event.target as HTMLInputElement).value === '' ? null : Number(($event.target as HTMLInputElement).value))"
                  />
                  <div v-if="errors.rate" class="cp-ed-err-msg">{{ errors.rate }}</div>
                  <div v-else-if="draft.rate" class="cp-ed-hint">
                    {{ (toNum(draft.rate) * 100).toFixed(2) }}% годовых
                  </div>
                </div>
              </div>

              <div class="cp-ed-fld">
                <label class="cp-ed-lbl">Описание ставки <small>опц.</small></label>
                <input
                  type="text"
                  class="cp-ed-input"
                  :value="draft.rate_text || ''"
                  placeholder="SHIBOR 6M + 0.50%"
                  @input="setField('rate_text', ($event.target as HTMLInputElement).value || null)"
                />
              </div>

              <div class="cp-ed-row">
                <div class="cp-ed-fld">
                  <label class="cp-ed-lbl">Сумма всего</label>
                  <input
                    type="number"
                    class="cp-ed-input"
                    step="0.01"
                    :value="draft.sum_total || ''"
                    placeholder="100000000"
                    @input="setField('sum_total', ($event.target as HTMLInputElement).value === '' ? null : Number(($event.target as HTMLInputElement).value))"
                  />
                </div>
                <div class="cp-ed-fld">
                  <label class="cp-ed-lbl">Выбрано</label>
                  <input
                    type="number"
                    class="cp-ed-input"
                    step="0.01"
                    :value="draft.sum_disbursed || ''"
                    @input="setField('sum_disbursed', ($event.target as HTMLInputElement).value === '' ? null : Number(($event.target as HTMLInputElement).value))"
                  />
                </div>
              </div>

              <div class="cp-ed-row">
                <div class="cp-ed-fld">
                  <label class="cp-ed-lbl">Долг (валюта)</label>
                  <input
                    type="number"
                    class="cp-ed-input"
                    step="0.01"
                    :value="draft.debt_currency || ''"
                    @input="setField('debt_currency', ($event.target as HTMLInputElement).value === '' ? null : Number(($event.target as HTMLInputElement).value))"
                  />
                </div>
                <div class="cp-ed-fld">
                  <label class="cp-ed-lbl">Долг (USD экв.)</label>
                  <input
                    type="number"
                    class="cp-ed-input"
                    step="0.01"
                    :value="draft.debt_usd || ''"
                    @input="setField('debt_usd', ($event.target as HTMLInputElement).value === '' ? null : Number(($event.target as HTMLInputElement).value))"
                  />
                </div>
              </div>
            </fieldset>

            <!-- Section 3: Сроки -->
            <fieldset class="cp-ed-fs">
              <legend>Сроки</legend>

              <div class="cp-ed-row">
                <div class="cp-ed-fld">
                  <label class="cp-ed-lbl">Дата получения</label>
                  <input
                    type="date"
                    class="cp-ed-input"
                    :value="draft.date_get || ''"
                    @input="setField('date_get', ($event.target as HTMLInputElement).value || null)"
                  />
                </div>
                <div class="cp-ed-fld">
                  <label class="cp-ed-lbl">Дата погашения</label>
                  <input
                    type="date"
                    class="cp-ed-input"
                    :class="{ 'cp-ed-err': errors.date_due }"
                    :value="draft.date_due || ''"
                    @input="setField('date_due', ($event.target as HTMLInputElement).value || null)"
                  />
                  <div v-if="errors.date_due" class="cp-ed-err-msg">{{ errors.date_due }}</div>
                </div>
              </div>

              <div class="cp-ed-fld">
                <label class="cp-ed-lbl">As-of дата <small>дата актуальности остатков</small></label>
                <input
                  type="date"
                  class="cp-ed-input"
                  :value="draft.as_of_date || ''"
                  @input="setField('as_of_date', ($event.target as HTMLInputElement).value || null)"
                />
              </div>
            </fieldset>

            <!-- Section 4: Классификация -->
            <fieldset class="cp-ed-fs">
              <legend>Классификация</legend>

              <div class="cp-ed-row">
                <div class="cp-ed-fld">
                  <label class="cp-ed-lbl">
                    Тип кредитора
                    <small>пусто = авто-классификация по имени банка</small>
                  </label>
                  <select
                    class="cp-ed-input"
                    :value="draft.lender_type || ''"
                    @change="setField('lender_type', ($event.target as HTMLSelectElement).value || null)"
                  >
                    <option value="">— автоматически —</option>
                    <option v-for="(meta, key) in CP_LENDER_LABELS" :key="key" :value="key">
                      {{ meta.label }}
                    </option>
                  </select>
                </div>

                <div class="cp-ed-fld">
                  <label class="cp-ed-lbl">Госгарантия</label>
                  <label class="cp-ed-checkbox">
                    <input
                      type="checkbox"
                      :checked="draft.is_guaranteed"
                      @change="setField('is_guaranteed', ($event.target as HTMLInputElement).checked)"
                    />
                    <span>Кредит под гарантию государства</span>
                  </label>
                </div>
              </div>

              <div class="cp-ed-fld">
                <label class="cp-ed-lbl">Подразделение / Филиал заёмщика <small>опц.</small></label>
                <input
                  type="text"
                  class="cp-ed-input"
                  :value="draft.borrower_unit || ''"
                  placeholder="Сирдарё ИЭС филиали"
                  @input="setField('borrower_unit', ($event.target as HTMLInputElement).value || null)"
                />
              </div>

              <div class="cp-ed-fld">
                <label class="cp-ed-lbl">Примечания</label>
                <textarea
                  class="cp-ed-input cp-ed-textarea"
                  rows="3"
                  :value="draft.notes || ''"
                  placeholder="любая дополнительная информация…"
                  @input="setField('notes', ($event.target as HTMLTextAreaElement).value || null)"
                />
              </div>
            </fieldset>
          </div>

          <!-- Footer -->
          <div class="cp-ed-foot">
            <span v-if="Object.keys(errors).length > 0" class="cp-ed-err-summary">
              {{ Object.keys(errors).length }} {{ Object.keys(errors).length === 1 ? "ошибка" : "ошибок" }} в форме
            </span>
            <span v-else class="cp-ed-foot-hint">
              Черновик автосохраняется в браузере на 7 дней
            </span>
            <button class="cp-ed-btn-cancel" :disabled="saving" @click="onCancel">Отмена</button>
            <button class="cp-ed-btn-save" :disabled="saving" @click="onSave">
              <span v-if="saving" class="cp-ed-btn-spinner"/>
              {{ saving ? "Сохранение…" : (isEdit ? "Сохранить" : "Создать") }}
            </button>
          </div>
        </div>
      </Transition>
    </div>
  </Transition>
  </Transition>
</template>

<style scoped>
.cp-ed-backdrop {
  position: fixed;
  inset: 0;
  background: rgba(15, 18, 40, 0.45);
  backdrop-filter: blur(8px);
  z-index: 1100;
  display: flex;
  justify-content: flex-end;
}

.cp-ed-fade-enter-active,
.cp-ed-fade-leave-active { transition: opacity 0.2s ease; }
.cp-ed-fade-enter-from,
.cp-ed-fade-leave-to { opacity: 0; }

.cp-ed-panel {
  width: 520px;
  max-width: 100vw;
  height: 100vh;
  background: rgba(255, 255, 255, 0.99);
  display: flex;
  flex-direction: column;
  box-shadow: -24px 0 64px rgba(15, 23, 60, 0.18);
}

.cp-ed-slide-enter-active,
.cp-ed-slide-leave-active {
  transition: transform 0.35s cubic-bezier(0.34, 1.2, 0.64, 1);
}
.cp-ed-slide-enter-from,
.cp-ed-slide-leave-to { transform: translateX(100%); }

/* Header */
.cp-ed-h {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 18px 20px 14px;
  border-bottom: 1px solid rgba(0, 0, 0, 0.06);
  flex-shrink: 0;
}

.cp-ed-h-text { flex: 1; min-width: 0; }

.cp-ed-h-title {
  font-size: 16px;
  font-weight: 500;
  color: var(--t1, #1e2a4a);
  letter-spacing: -0.01em;
  margin-bottom: 2px;
}

.cp-ed-h-sub {
  font-size: 10.5px;
  color: var(--t3, #888780);
  text-transform: uppercase;
  letter-spacing: 0.04em;
  font-weight: 500;
}

.cp-ed-close {
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
.cp-ed-close:hover { background: rgba(0, 0, 0, 0.05); }

/* Backup banner */
.cp-ed-backup {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 16px;
  background: rgba(127, 119, 221, 0.10);
  border-bottom: 1px solid rgba(127, 119, 221, 0.18);
  font-size: 11.5px;
  color: var(--t1, #1e2a4a);
  flex-shrink: 0;
}
.cp-ed-backup svg { color: #7F77DD; flex-shrink: 0; }
.cp-ed-backup span { flex: 1; }
.cp-ed-backup-btn {
  background: #7F77DD; color: #fff; border: none;
  padding: 4px 10px; border-radius: 6px;
  font-size: 11px; font-weight: 600; cursor: pointer;
  transition: background 0.14s;
}
.cp-ed-backup-btn:hover { background: #534AB7; }
.cp-ed-backup-x {
  background: transparent; border: none; color: var(--t3, #888780);
  cursor: pointer; padding: 0 4px; font-size: 16px;
}

/* Body */
.cp-ed-body {
  flex: 1;
  overflow-y: auto;
  padding: 16px 20px 24px;
}

.cp-ed-fs {
  border: 1px solid rgba(0, 0, 0, 0.08);
  border-radius: 10px;
  padding: 12px 14px 14px;
  margin: 0 0 14px;
}

.cp-ed-fs legend {
  font-size: 10.5px;
  font-weight: 500;
  color: var(--t3, #888780);
  text-transform: uppercase;
  letter-spacing: 0.06em;
  padding: 0 6px;
}

.cp-ed-row {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 12px;
  margin-bottom: 8px;
}

.cp-ed-fld {
  display: flex;
  flex-direction: column;
  margin-bottom: 8px;
  min-width: 0;
}

.cp-ed-lbl {
  font-size: 10.5px;
  font-weight: 500;
  color: var(--t3, #888780);
  text-transform: uppercase;
  letter-spacing: 0.04em;
  margin-bottom: 4px;
  display: flex;
  align-items: center;
  gap: 4px;
}
.cp-ed-lbl small {
  font-size: 9px;
  font-weight: 400;
  text-transform: none;
  letter-spacing: 0;
  color: var(--t3, #888780);
  font-style: italic;
  margin-left: 4px;
}

.cp-ed-req { color: #C97070; }

.cp-ed-input {
  font-family: inherit;
  font-size: 12.5px;
  font-weight: 500;
  color: var(--t1, #1e2a4a);
  padding: 8px 10px;
  border: 1px solid rgba(0, 0, 0, 0.10);
  border-radius: 7px;
  background: #fff;
  transition: border-color 0.14s, box-shadow 0.14s;
  width: 100%;
  font-feature-settings: "tnum";
}

.cp-ed-input:focus {
  outline: none;
  border-color: #7F77DD;
  box-shadow: 0 0 0 3px rgba(127, 119, 221, 0.18);
}

.cp-ed-input:disabled {
  background: rgba(127, 119, 221, 0.04);
  color: var(--t3, #888780);
  cursor: not-allowed;
}

.cp-ed-textarea {
  resize: vertical;
  min-height: 56px;
  font-family: inherit;
}

.cp-ed-err {
  border-color: #C97070;
}
.cp-ed-err:focus {
  box-shadow: 0 0 0 3px rgba(201, 112, 112, 0.18);
}

.cp-ed-err-msg {
  margin-top: 3px;
  font-size: 10.5px;
  color: #C97070;
  font-weight: 500;
}

.cp-ed-hint {
  margin-top: 3px;
  font-size: 10.5px;
  color: var(--t3, #888780);
  font-style: italic;
}

.cp-ed-checkbox {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 0;
  font-size: 12px;
  color: var(--t2, #555c6e);
  cursor: pointer;
}
.cp-ed-checkbox input[type="checkbox"] {
  width: 16px;
  height: 16px;
  accent-color: #7F77DD;
}

/* Footer */
.cp-ed-foot {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 14px 20px 16px;
  border-top: 1px solid rgba(0, 0, 0, 0.08);
  background: rgba(127, 119, 221, 0.02);
  flex-shrink: 0;
}

.cp-ed-foot-hint {
  flex: 1;
  font-size: 10.5px;
  color: var(--t3, #888780);
  font-style: italic;
}

.cp-ed-err-summary {
  flex: 1;
  font-size: 11px;
  color: #C97070;
  font-weight: 600;
}

.cp-ed-btn-cancel,
.cp-ed-btn-save {
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

.cp-ed-btn-cancel {
  background: transparent;
  color: var(--t2, #555c6e);
  border: 1px solid rgba(0, 0, 0, 0.10);
}
.cp-ed-btn-cancel:hover { background: rgba(0, 0, 0, 0.04); }

.cp-ed-btn-save {
  background: #7F77DD;
  color: #fff;
}
.cp-ed-btn-save:hover { background: #534AB7; }
.cp-ed-btn-save:disabled { opacity: 0.6; cursor: not-allowed; }

.cp-ed-btn-spinner {
  width: 12px; height: 12px;
  border: 2px solid rgba(255, 255, 255, 0.3);
  border-top-color: #fff;
  border-radius: 50%;
  animation: cpEdSpin 0.7s linear infinite;
}

@keyframes cpEdSpin { to { transform: rotate(360deg); } }
</style>
