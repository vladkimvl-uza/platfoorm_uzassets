<script setup lang="ts">
/**
 * LoanDetailModal — большая модалка деталей кредита (1320px).
 *
 * Открывается через credit.openLoanDetail(loanId). Backend `/loans/{id}` грузит
 * полный объект и кладёт в credit.loanDetail.
 *
 * 2-кол layout:
 *   Left:  Факты кредита (company, bank, contract, currency, rate, sums, dates, ...)
 *   Right: Прогресс погашения (debt vs disbursed) + годовые расходы по %
 *
 * Кнопки:
 *   • Edit  — заглушка для 19c-8 (Drawer editor)
 *   • Delete — soft-delete с confirm
 */
import { computed, watch } from "vue";
import { useCreditData } from "@/composables/useCreditData";
import {
  CP_LENDER_LABELS,
  cpCurrencyColor,
  fmtDate,
  fmtMoneyLoan,
  fmtMoneyShort,
  fmtRate,
  toNum,
  yearOf,
} from "@/api/credit";
import { deleteLoan, getLoan } from "@/api/credit";
import { useFormatters } from "@/composables/useFormatters";
import LoanPaymentsSection from "./LoanPaymentsSection.vue";
const fmt = useFormatters();

const credit = useCreditData();

const loan = computed(() => credit.loanDetail.value);

// Re-fetch loan details (debt_currency etc) after a payment write
async function refreshLoan() {
  if (!loan.value) return;
  try {
    credit.loanDetail.value = await getLoan(loan.value.id);
  } catch {
    /* silent — payments section already showed any error */
  }
}
const isOpen = computed(() => credit.loanDetailOpen.value);
const isLoading = computed(() => credit.loanDetailLoading.value);

const daysUntilDue = computed(() => {
  if (!loan.value?.date_due) return null;
  const due = new Date(loan.value.date_due).getTime();
  const asOf = new Date(credit.asOfDate.value).getTime();
  return Math.round((due - asOf) / (1000 * 60 * 60 * 24));
});

const isOverdue = computed(() => {
  return daysUntilDue.value !== null && daysUntilDue.value < 0;
});

const lenderTypeMeta = computed(() => {
  const lt = loan.value?.lender_type;
  return lt ? CP_LENDER_LABELS[lt] : null;
});

const repaidUsd = computed(() => {
  if (!loan.value) return 0;
  const sumTotal = toNum(loan.value.sum_total);
  const debtCurrency = toNum(loan.value.debt_currency);
  const debtUsd = toNum(loan.value.debt_usd);
  // Approximate sumTotal in USD using debt ratio
  if (debtCurrency > 0 && debtUsd > 0) {
    const sumTotalUsd = sumTotal * (debtUsd / debtCurrency);
    return Math.max(0, sumTotalUsd - debtUsd);
  }
  return 0;
});

const repaidPct = computed(() => {
  if (!loan.value) return 0;
  const sumTotal = toNum(loan.value.sum_total);
  const debtCurrency = toNum(loan.value.debt_currency);
  if (sumTotal <= 0 || debtCurrency <= 0) return 0;
  return Math.max(0, Math.min(100, ((sumTotal - debtCurrency) / sumTotal) * 100));
});

const annualInterest = computed(() => {
  if (!loan.value) return 0;
  return toNum(loan.value.debt_usd) * toNum(loan.value.rate);
});

function close() {
  credit.closeLoanDetail();
}

async function onDelete() {
  if (!loan.value) return;
  const confirmed = window.confirm(
    `Удалить кредит ${loan.value.loan_code}?\n\nКредит будет помечен как удалённый (soft delete) — backend хранит запись для аудита.`,
  );
  if (!confirmed) return;
  try {
    await deleteLoan(loan.value.id);
    // Reload loans + aggregate
    await Promise.all([credit.loadLoans(), credit.loadAggregate()]);
    close();
  } catch (e: any) {
    alert("Не удалось удалить кредит: " + (e?.response?.data?.detail || e?.message));
  }
}

function onEdit() {
  if (!loan.value) return;
  // Закрываем модалку и открываем drawer-редактор с предзаполненным кредитом.
  // Modal остаётся в памяти composable до setTimeout (300ms), drawer открывается
  // моментально — так пользователь видит плавную замену UI без мерцания.
  const target = loan.value;
  credit.closeLoanDetail();
  credit.openLoanEditor(target);
}

// Close on Escape
function onKeydown(e: KeyboardEvent) {
  if (e.key === "Escape") close();
}

watch(isOpen, (v) => {
  if (v) {
    document.addEventListener("keydown", onKeydown);
    document.body.style.overflow = "hidden";
  } else {
    document.removeEventListener("keydown", onKeydown);
    document.body.style.overflow = "";
  }
});
</script>

<template>
  <Teleport to="body">
    <Transition name="cp-ldm">
      <div v-if="isOpen" class="cp-ldm-backdrop" @click.self="close">
        <div class="cp-ldm-modal">
          <!-- Loading state -->
          <div v-if="isLoading || !loan" class="cp-ldm-loading">
            <div class="cp-spinner" />
            <div>Загружаю детали кредита…</div>
          </div>

          <!-- Loaded -->
          <template v-else>
            <!-- Header -->
            <div class="cp-ldm-header">
              <div class="cp-ldm-header-left">
                <div class="cp-ldm-h-line">
                  <span class="cp-ldm-code">{{ loan.loan_code }}</span>
                  <span
                    v-if="loan.currency"
                    class="cp-ldm-cur"
                    :style="{
                      background: cpCurrencyColor(loan.currency) + '22',
                      color: cpCurrencyColor(loan.currency),
                    }"
                  >{{ loan.currency }}</span>
                  <span
                    v-if="lenderTypeMeta"
                    class="cp-ldm-pill"
                    :style="{
                      background: lenderTypeMeta.color + '22',
                      color: lenderTypeMeta.color,
                      borderColor: lenderTypeMeta.color + '55',
                    }"
                  >{{ lenderTypeMeta.label }}</span>
                  <span v-if="loan.is_guaranteed" class="cp-ldm-guard">
                    🛡 Госгарантия
                  </span>
                  <span v-if="isOverdue" class="cp-ldm-overdue">⚠ Просрочка</span>
                </div>
                <h2 class="cp-ldm-title">{{ loan.bank }}</h2>
                <div class="cp-ldm-co">{{ loan.company_name_ru }}</div>
              </div>
              <div class="cp-ldm-header-right">
                <button type="button" class="cp-ldm-btn cp-ldm-btn-edit" @click="onEdit">
                  ✎ Редактировать
                </button>
                <button type="button" class="cp-ldm-btn cp-ldm-btn-del" @click="onDelete">
                  Удалить
                </button>
                <button type="button" class="cp-ldm-close" @click="close" title="Закрыть">×</button>
              </div>
            </div>

            <!-- Body 2-col -->
            <div class="cp-ldm-body">
              <!-- LEFT col -->
              <div class="cp-ldm-col">
                <div class="cp-ldm-section">
                  <div class="cp-ldm-section-h">Контракт</div>
                  <div class="cp-ldm-fields">
                    <div class="cp-ldm-f">
                      <span class="cp-ldm-f-l">Номер контракта</span>
                      <span class="cp-ldm-f-v">{{ loan.contract_ref || "—" }}</span>
                    </div>
                    <div class="cp-ldm-f" v-if="loan.borrower_unit">
                      <span class="cp-ldm-f-l">Подразделение-заёмщик</span>
                      <span class="cp-ldm-f-v">{{ loan.borrower_unit }}</span>
                    </div>
                  </div>
                </div>

                <div class="cp-ldm-section">
                  <div class="cp-ldm-section-h">Финансовые параметры</div>
                  <div class="cp-ldm-fields">
                    <div class="cp-ldm-f">
                      <span class="cp-ldm-f-l">Эффективная ставка</span>
                      <span class="cp-ldm-f-v">
                        {{ toNum(loan.rate) > 0 && toNum(loan.rate) < 1 ? fmtRate(loan.rate) : "—" }}
                        <small v-if="loan.rate_text" class="cp-ldm-f-hint">
                          ({{ loan.rate_text }})
                        </small>
                      </span>
                    </div>
                    <div class="cp-ldm-f">
                      <span class="cp-ldm-f-l">Сумма контракта</span>
                      <span class="cp-ldm-f-v">
                        {{ toNum(loan.sum_total) > 0 ? fmtMoneyLoan(loan.sum_total, loan.currency) : "—" }}
                      </span>
                    </div>
                    <div class="cp-ldm-f" v-if="toNum(loan.sum_disbursed) > 0">
                      <span class="cp-ldm-f-l">Выбрано</span>
                      <span class="cp-ldm-f-v">
                        {{ fmtMoneyLoan(loan.sum_disbursed, loan.currency) }}
                      </span>
                    </div>
                    <div class="cp-ldm-f">
                      <span class="cp-ldm-f-l">Остаток ({{ loan.currency }})</span>
                      <span class="cp-ldm-f-v cp-ldm-f-strong">
                        {{ fmtMoneyLoan(loan.debt_currency, loan.currency) }}
                      </span>
                    </div>
                    <div class="cp-ldm-f">
                      <span class="cp-ldm-f-l">Остаток (USD)</span>
                      <span class="cp-ldm-f-v cp-ldm-f-strong">
                        {{ fmtMoneyShort(loan.debt_usd) }}
                      </span>
                    </div>
                    <div class="cp-ldm-f">
                      <span class="cp-ldm-f-l">% расходов / год</span>
                      <span class="cp-ldm-f-v">
                        {{ annualInterest > 0 ? fmtMoneyShort(annualInterest) : "—" }}
                      </span>
                    </div>
                  </div>
                </div>

                <div class="cp-ldm-section">
                  <div class="cp-ldm-section-h">Сроки</div>
                  <div class="cp-ldm-fields">
                    <div class="cp-ldm-f">
                      <span class="cp-ldm-f-l">Дата выдачи</span>
                      <span class="cp-ldm-f-v">{{ fmtDate(loan.date_get) }}</span>
                    </div>
                    <div class="cp-ldm-f">
                      <span class="cp-ldm-f-l">Дата погашения</span>
                      <span class="cp-ldm-f-v" :style="{ color: isOverdue ? '#C97070' : '' }">
                        {{ fmtDate(loan.date_due) }}
                        <small v-if="daysUntilDue !== null" class="cp-ldm-f-hint">
                          ({{ daysUntilDue >= 0 ? `через ${daysUntilDue} дн.` : `просрочка ${-daysUntilDue} дн.` }})
                        </small>
                      </span>
                    </div>
                  </div>
                </div>

                <div v-if="loan.notes" class="cp-ldm-section">
                  <div class="cp-ldm-section-h">Примечания</div>
                  <div class="cp-ldm-notes">{{ loan.notes }}</div>
                </div>
              </div>

              <!-- RIGHT col -->
              <div class="cp-ldm-col">
                <div class="cp-ldm-section">
                  <div class="cp-ldm-section-h">Прогресс погашения</div>
                  <div class="cp-ldm-progress">
                    <div class="cp-ldm-progress-bar">
                      <div
                        class="cp-ldm-progress-fill"
                        :style="{ width: repaidPct.toFixed(1) + '%' }"
                      />
                    </div>
                    <div class="cp-ldm-progress-stats">
                      <div class="cp-ldm-progress-stat">
                        <span class="cp-ldm-progress-lbl">Погашено</span>
                        <span class="cp-ldm-progress-val cp-ldm-progress-val-green">
                          {{ fmt.fmtPercent(repaidPct, { decimals: 1 }) }}
                        </span>
                        <small>≈ {{ fmtMoneyShort(repaidUsd) }}</small>
                      </div>
                      <div class="cp-ldm-progress-stat">
                        <span class="cp-ldm-progress-lbl">Осталось</span>
                        <span class="cp-ldm-progress-val cp-ldm-progress-val-purple">
                          {{ fmt.fmtPercent(100 - repaidPct, { decimals: 1 }) }}
                        </span>
                        <small>{{ fmtMoneyShort(loan.debt_usd) }}</small>
                      </div>
                    </div>
                  </div>
                </div>

                <div class="cp-ldm-section">
                  <div class="cp-ldm-section-h">Метаданные</div>
                  <div class="cp-ldm-fields">
                    <div class="cp-ldm-f">
                      <span class="cp-ldm-f-l">As-of дата</span>
                      <span class="cp-ldm-f-v">{{ fmtDate(loan.as_of_date) }}</span>
                    </div>
                    <div class="cp-ldm-f">
                      <span class="cp-ldm-f-l">Тип кредитора</span>
                      <span class="cp-ldm-f-v">
                        {{ lenderTypeMeta?.label || "—" }}
                        <small v-if="loan.auto_flags?.lenderType" class="cp-ldm-f-hint">
                          (авто-классификация)
                        </small>
                      </span>
                    </div>
                    <div class="cp-ldm-f">
                      <span class="cp-ldm-f-l">Год выдачи</span>
                      <span class="cp-ldm-f-v">{{ yearOf(loan.date_get) || "—" }}</span>
                    </div>
                    <div class="cp-ldm-f">
                      <span class="cp-ldm-f-l">Год погашения</span>
                      <span class="cp-ldm-f-v">{{ yearOf(loan.date_due) || "—" }}</span>
                    </div>
                  </div>
                </div>

                <div class="cp-ldm-section">
                  <LoanPaymentsSection
                    :loan-id="loan.id"
                    :currency="loan.currency"
                    :outstanding="Number(loan.debt_currency ?? 0)"
                    @changed="refreshLoan"
                  />
                </div>

                <div class="cp-ldm-section">
                  <div class="cp-ldm-section-h">Аудит</div>
                  <div class="cp-ldm-fields">
                    <div class="cp-ldm-f">
                      <span class="cp-ldm-f-l">Создан</span>
                      <span class="cp-ldm-f-v cp-ldm-f-mono">{{ loan.created_at.slice(0, 19).replace("T", " ") }}</span>
                    </div>
                    <div class="cp-ldm-f">
                      <span class="cp-ldm-f-l">Изменён</span>
                      <span class="cp-ldm-f-v cp-ldm-f-mono">{{ loan.updated_at.slice(0, 19).replace("T", " ") }}</span>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </template>
        </div>
      </div>
    </Transition>
  </Teleport>
</template>

<style scoped>
/* ─── Backdrop & modal animation ─── */
.cp-ldm-enter-active,
.cp-ldm-leave-active {
  transition: opacity 0.3s ease;
}

.cp-ldm-enter-active .cp-ldm-modal,
.cp-ldm-leave-active .cp-ldm-modal {
  transition: transform 0.45s cubic-bezier(0.34, 1.2, 0.64, 1), opacity 0.3s ease;
}

.cp-ldm-enter-from,
.cp-ldm-leave-to {
  opacity: 0;
}

.cp-ldm-enter-from .cp-ldm-modal,
.cp-ldm-leave-to .cp-ldm-modal {
  transform: scale(0.96) translateY(8px);
  opacity: 0;
}

.cp-ldm-backdrop {
  position: fixed;
  inset: 0;
  background: rgba(15, 18, 40, 0.45);
  backdrop-filter: blur(8px);
  -webkit-backdrop-filter: blur(8px);
  display: flex;
  align-items: flex-start;
  justify-content: center;
  z-index: 1000;
  padding: 60px 20px 40px;
  overflow-y: auto;
}

.cp-ldm-modal {
  background: #fff;
  border-radius: 16px;
  width: 100%;
  max-width: 1320px;
  box-shadow:
    0 32px 80px rgba(15, 23, 60, 0.25),
    0 12px 32px rgba(15, 23, 60, 0.10);
  overflow: hidden;
  display: flex;
  flex-direction: column;
}

/* ─── Loading ─── */
.cp-ldm-loading {
  padding: 80px 40px;
  text-align: center;
  color: var(--t3, #888780);
  font-style: italic;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 14px;
}

.cp-spinner {
  width: 28px;
  height: 28px;
  border: 2.5px solid rgba(127, 119, 221, 0.2);
  border-top-color: #7F77DD;
  border-radius: 50%;
  animation: cpSpin 0.7s linear infinite;
}

@keyframes cpSpin { to { transform: rotate(360deg); } }

/* ─── Header ─── */
.cp-ldm-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 24px;
  padding: 22px 28px 18px;
  border-bottom: 1px solid rgba(0, 0, 0, 0.06);
}

.cp-ldm-header-left {
  flex: 1;
  min-width: 0;
}

.cp-ldm-h-line {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
  margin-bottom: 10px;
}

.cp-ldm-code {
  font-size: 11px;
  font-weight: 600;
  font-family: monospace;
  color: var(--t2, #555c6e);
  background: rgba(127, 119, 221, 0.08);
  padding: 3px 8px;
  border-radius: 6px;
  letter-spacing: 0.04em;
}

.cp-ldm-cur {
  font-size: 10px;
  font-weight: 600;
  letter-spacing: 0.04em;
  padding: 3px 8px;
  border-radius: 6px;
}

.cp-ldm-pill {
  font-size: 9.5px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.04em;
  padding: 3px 8px;
  border-radius: 8px;
  border: 1px solid;
}

.cp-ldm-guard {
  font-size: 10px;
  font-weight: 600;
  color: #1D9E75;
  background: rgba(29, 158, 117, 0.12);
  padding: 3px 8px;
  border-radius: 6px;
}

.cp-ldm-overdue {
  font-size: 10px;
  font-weight: 600;
  color: #C53030;
  background: rgba(226, 75, 74, 0.14);
  padding: 3px 8px;
  border-radius: 6px;
}

.cp-ldm-title {
  font-size: 22px;
  font-weight: 500;
  color: var(--t1, #1e2a4a);
  letter-spacing: -0.02em;
  margin: 0 0 4px;
  line-height: 1.2;
}

.cp-ldm-co {
  font-size: 13px;
  font-weight: 500;
  color: var(--t2, #555c6e);
  letter-spacing: -0.005em;
}

.cp-ldm-header-right {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-shrink: 0;
}

.cp-ldm-btn {
  padding: 8px 14px;
  border-radius: 8px;
  font-family: inherit;
  font-size: 12px;
  font-weight: 500;
  cursor: pointer;
  transition: background 0.14s, color 0.14s;
  border: 1px solid transparent;
  letter-spacing: -0.005em;
}

.cp-ldm-btn-edit {
  background: rgba(127, 119, 221, 0.08);
  border-color: rgba(127, 119, 221, 0.25);
  color: #7F77DD;
}

.cp-ldm-btn-edit:hover {
  background: rgba(127, 119, 221, 0.14);
}

.cp-ldm-btn-del {
  background: transparent;
  border-color: rgba(201, 112, 112, 0.3);
  color: #C97070;
}

.cp-ldm-btn-del:hover {
  background: rgba(201, 112, 112, 0.08);
}

.cp-ldm-close {
  width: 32px;
  height: 32px;
  border-radius: 8px;
  background: transparent;
  border: 1px solid rgba(0, 0, 0, 0.08);
  font-size: 22px;
  line-height: 1;
  color: var(--t3, #888780);
  cursor: pointer;
  transition: background 0.14s, color 0.14s;
}

.cp-ldm-close:hover {
  background: rgba(0, 0, 0, 0.05);
  color: var(--t1, #1e2a4a);
}

/* ─── Body ─── */
.cp-ldm-body {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 28px;
  padding: 22px 28px 28px;
}

@media (max-width: 900px) {
  .cp-ldm-body { grid-template-columns: 1fr; gap: 16px; }
}

.cp-ldm-col {
  display: flex;
  flex-direction: column;
  gap: 18px;
  min-width: 0;
}

.cp-ldm-section {
  border-bottom: 1px solid rgba(0, 0, 0, 0.04);
  padding-bottom: 16px;
}

.cp-ldm-section:last-child {
  border-bottom: none;
  padding-bottom: 0;
}

.cp-ldm-section-h {
  font-size: 10px;
  font-weight: 500;
  color: var(--t3, #888780);
  text-transform: uppercase;
  letter-spacing: 0.08em;
  margin-bottom: 12px;
}

.cp-ldm-fields {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.cp-ldm-f {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 12px;
}

.cp-ldm-f-l {
  font-size: 11.5px;
  color: var(--t2, #555c6e);
  font-weight: 500;
  letter-spacing: -0.005em;
  flex-shrink: 0;
}

.cp-ldm-f-v {
  font-size: 12.5px;
  color: var(--t1, #1e2a4a);
  font-weight: 500;
  font-feature-settings: "tnum";
  text-align: right;
  letter-spacing: -0.005em;
}

.cp-ldm-f-strong {
  font-size: 14px;
  font-weight: 600;
}

.cp-ldm-f-mono {
  font-family: monospace;
  font-size: 11px;
  color: var(--t3, #888780);
}

.cp-ldm-f-hint {
  display: block;
  font-size: 10px;
  color: var(--t3, #888780);
  font-weight: 400;
  font-style: italic;
  margin-top: 2px;
}

.cp-ldm-notes {
  font-size: 12px;
  color: var(--t2, #555c6e);
  line-height: 1.6;
  background: rgba(127, 119, 221, 0.04);
  padding: 12px 14px;
  border-radius: 8px;
  white-space: pre-wrap;
}

/* ─── Progress block ─── */
.cp-ldm-progress {
  background: rgba(127, 119, 221, 0.04);
  padding: 16px;
  border-radius: 12px;
}

.cp-ldm-progress-bar {
  height: 10px;
  background: rgba(127, 119, 221, 0.12);
  border-radius: 6px;
  overflow: hidden;
  margin-bottom: 14px;
}

.cp-ldm-progress-fill {
  height: 100%;
  background: linear-gradient(90deg, #1D9E75, #5DBFA1);
  border-radius: 6px;
  transition: width 0.7s cubic-bezier(0.34, 1.2, 0.64, 1);
  animation: cpLdmProgressIn 0.9s cubic-bezier(0.34, 1.2, 0.64, 1) 200ms both;
  transform-origin: left center;
}

@keyframes cpLdmProgressIn {
  from { transform: scaleX(0); }
  to   { transform: scaleX(1); }
}

.cp-ldm-progress-stats {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 14px;
}

.cp-ldm-progress-stat {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.cp-ldm-progress-lbl {
  font-size: 10px;
  color: var(--t3, #888780);
  font-weight: 500;
  text-transform: uppercase;
  letter-spacing: 0.06em;
}

.cp-ldm-progress-val {
  font-size: 22px;
  font-weight: 400;
  letter-spacing: -0.025em;
  font-feature-settings: "tnum";
}

.cp-ldm-progress-val-green { color: #1D9E75; }
.cp-ldm-progress-val-purple { color: #7F77DD; }

.cp-ldm-progress-stat small {
  font-size: 11px;
  color: var(--t2, #555c6e);
  font-weight: 500;
  font-feature-settings: "tnum";
}
</style>
