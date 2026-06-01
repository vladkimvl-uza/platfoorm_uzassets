<script setup lang="ts">
/**
 * LoanPaymentsSection — секция с историей погашений на странице кредита.
 *
 * Список + форма добавления + редактирование/удаление. После любого write
 * вызывает re-fetch родителя через emit('changed') чтобы обновить loan.debt_currency.
 */
import { computed, ref, watch } from "vue";
import {
  listLoanPayments,
  createLoanPayment,
  updatePayment,
  deletePayment,
  getLoanPaymentsSummary,
  type PaymentRead,
  type LoanPaymentsSummary,
  fmtMoneyLoan,
  fmtDate,
} from "@/api/credit";

const props = defineProps<{
  loanId: string;
  currency: string;
  /** Текущий остаток в валюте — для валидации principal_paid ≤ outstanding. */
  outstanding: number;
}>();

const emit = defineEmits<{
  changed: [];
}>();

const payments = ref<PaymentRead[]>([]);
const summary = ref<LoanPaymentsSummary | null>(null);
const loading = ref(false);
const error = ref<string | null>(null);

async function reload() {
  loading.value = true;
  error.value = null;
  try {
    const [list, s] = await Promise.all([
      listLoanPayments(props.loanId),
      getLoanPaymentsSummary(props.loanId),
    ]);
    payments.value = list;
    summary.value = s;
  } catch (e: any) {
    error.value = e?.response?.data?.detail || e?.message || "Не удалось загрузить платежи";
  } finally {
    loading.value = false;
  }
}

watch(() => props.loanId, reload, { immediate: true });

// ─── Add-payment form ────────────────────────────────────────────
const showForm = ref(false);
const formData = ref({
  paid_date: new Date().toISOString().slice(0, 10),
  principal_paid: "",
  interest_paid: "",
  penalty_paid: "",
  fx_rate_to_uzs: "",
  note: "",
});
const submitting = ref(false);
const formError = ref<string | null>(null);

function openForm() {
  formData.value = {
    paid_date: new Date().toISOString().slice(0, 10),
    principal_paid: "",
    interest_paid: "",
    penalty_paid: "",
    fx_rate_to_uzs: "",
    note: "",
  };
  formError.value = null;
  showForm.value = true;
}
function closeForm() {
  showForm.value = false;
}

async function submitForm() {
  formError.value = null;
  const p = Number(formData.value.principal_paid.replace(",", "."));
  if (!Number.isFinite(p) || p < 0) {
    formError.value = "Тело долга должно быть числом ≥ 0";
    return;
  }
  if (p > props.outstanding + 0.01) {
    formError.value = `Тело (${p}) больше остатка (${props.outstanding})`;
    return;
  }
  const i = formData.value.interest_paid ? Number(formData.value.interest_paid.replace(",", ".")) : 0;
  const e = formData.value.penalty_paid ? Number(formData.value.penalty_paid.replace(",", ".")) : 0;
  if (!Number.isFinite(i) || i < 0 || !Number.isFinite(e) || e < 0) {
    formError.value = "Проценты и пени должны быть ≥ 0";
    return;
  }
  const fxRaw = formData.value.fx_rate_to_uzs.trim();
  const fx = fxRaw ? Number(fxRaw.replace(",", ".")) : null;
  if (fxRaw && (!Number.isFinite(fx as number) || (fx as number) <= 0)) {
    formError.value = "Курс должен быть положительным числом";
    return;
  }

  submitting.value = true;
  try {
    await createLoanPayment(props.loanId, {
      paid_date: formData.value.paid_date,
      principal_paid: String(p) as any,
      interest_paid: String(i) as any,
      penalty_paid: String(e) as any,
      fx_rate_to_uzs: fx == null ? null : (String(fx) as any),
      note: formData.value.note.trim() || null,
    });
    showForm.value = false;
    await reload();
    emit("changed");
  } catch (e: any) {
    formError.value = e?.response?.data?.detail || e?.message || "Не удалось сохранить";
  } finally {
    submitting.value = false;
  }
}

// ─── Delete (soft) ───────────────────────────────────────────────
async function onDelete(p: PaymentRead) {
  if (!confirm(`Удалить платёж от ${fmtDate(p.paid_date)} на ${fmtMoneyLoan(p.principal_paid, props.currency)}?`)) return;
  try {
    await deletePayment(p.id);
    await reload();
    emit("changed");
  } catch (e: any) {
    error.value = e?.response?.data?.detail || e?.message || "Не удалось удалить";
  }
}

// ─── Inline edit ─────────────────────────────────────────────────
const editingId = ref<string | null>(null);
const editBuf = ref<{ principal: string; interest: string; penalty: string; note: string }>({
  principal: "", interest: "", penalty: "", note: "",
});
function startEdit(p: PaymentRead) {
  editingId.value = p.id;
  editBuf.value = {
    principal: String(p.principal_paid ?? ""),
    interest: String(p.interest_paid ?? ""),
    penalty: String(p.penalty_paid ?? ""),
    note: p.note ?? "",
  };
}
async function commitEdit(p: PaymentRead) {
  try {
    await updatePayment(p.id, {
      principal_paid: editBuf.value.principal as any,
      interest_paid: editBuf.value.interest as any,
      penalty_paid: editBuf.value.penalty as any,
      note: editBuf.value.note || null,
    });
    editingId.value = null;
    await reload();
    emit("changed");
  } catch (e: any) {
    error.value = e?.response?.data?.detail || e?.message || "Не удалось сохранить правку";
  }
}
function cancelEdit() { editingId.value = null; }

// ─── Footer totals (computed from summary) ───────────────────────
const haveAny = computed(() => payments.value.length > 0);
</script>

<template>
  <div class="cp-pay-section">
    <header class="cp-pay-head">
      <span class="cp-pay-title">История погашений</span>
      <span v-if="summary" class="cp-pay-summary">
        {{ summary.payments_count }} {{ summary.payments_count === 1 ? "платёж" : "платежей" }} ·
        тело: <b>{{ fmtMoneyLoan(summary.total_principal_paid, currency) }}</b> ·
        %: {{ fmtMoneyLoan(summary.total_interest_paid, currency) }}
        <template v-if="Number(summary.total_penalty_paid) > 0">
          · пени: {{ fmtMoneyLoan(summary.total_penalty_paid, currency) }}
        </template>
      </span>
      <button v-if="!showForm" class="cp-pay-add-btn" @click="openForm">+ Внести платёж</button>
    </header>

    <!-- Add form -->
    <div v-if="showForm" class="cp-pay-form">
      <div class="cp-pay-form-row">
        <label class="cp-pay-fld">
          <span>Дата</span>
          <input v-model="formData.paid_date" type="date" class="cp-pay-input"/>
        </label>
        <label class="cp-pay-fld">
          <span>Тело долга ({{ currency }})</span>
          <input v-model="formData.principal_paid" type="text" inputmode="decimal" class="cp-pay-input" placeholder="0.00" autofocus/>
        </label>
        <label class="cp-pay-fld">
          <span>Проценты</span>
          <input v-model="formData.interest_paid" type="text" inputmode="decimal" class="cp-pay-input" placeholder="0.00"/>
        </label>
        <label class="cp-pay-fld">
          <span>Пени</span>
          <input v-model="formData.penalty_paid" type="text" inputmode="decimal" class="cp-pay-input" placeholder="0"/>
        </label>
        <label v-if="currency !== 'UZS'" class="cp-pay-fld">
          <span>Курс UZS/{{ currency }}</span>
          <input v-model="formData.fx_rate_to_uzs" type="text" inputmode="decimal" class="cp-pay-input" placeholder="опц."/>
        </label>
      </div>
      <label class="cp-pay-fld cp-pay-fld-wide">
        <span>Заметка</span>
        <input v-model="formData.note" type="text" class="cp-pay-input" placeholder="платёжное поручение №…"/>
      </label>
      <div v-if="formError" class="cp-pay-err">{{ formError }}</div>
      <div class="cp-pay-form-actions">
        <button class="cp-pay-btn-cancel" :disabled="submitting" @click="closeForm">Отмена</button>
        <button class="cp-pay-btn-primary" :disabled="submitting" @click="submitForm">
          {{ submitting ? "Сохраняем…" : "Сохранить платёж" }}
        </button>
      </div>
    </div>

    <!-- Error banner -->
    <div v-if="error" class="cp-pay-err-banner">{{ error }}</div>

    <!-- Payments list -->
    <div v-if="loading && !haveAny" class="cp-pay-loading">Загрузка платежей…</div>
    <div v-else-if="!haveAny" class="cp-pay-empty">
      Платежей по этому кредиту ещё не вносили. Нажмите «+ Внести платёж».
    </div>
    <table v-else class="cp-pay-tbl">
      <thead>
        <tr>
          <th>Дата</th>
          <th class="cp-pay-num">Тело</th>
          <th class="cp-pay-num">Проценты</th>
          <th class="cp-pay-num">Пени</th>
          <th>Заметка</th>
          <th></th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="p in payments" :key="p.id" :class="{ 'cp-pay-row-editing': editingId === p.id }">
          <td>{{ fmtDate(p.paid_date) }}</td>
          <template v-if="editingId === p.id">
            <td><input v-model="editBuf.principal" type="text" inputmode="decimal" class="cp-pay-input-sm"/></td>
            <td><input v-model="editBuf.interest" type="text" inputmode="decimal" class="cp-pay-input-sm"/></td>
            <td><input v-model="editBuf.penalty" type="text" inputmode="decimal" class="cp-pay-input-sm"/></td>
            <td><input v-model="editBuf.note" type="text" class="cp-pay-input-sm"/></td>
            <td class="cp-pay-row-acts">
              <button class="cp-pay-act-ok" title="Сохранить" @click="commitEdit(p)">✓</button>
              <button class="cp-pay-act-cancel" title="Отмена" @click="cancelEdit">×</button>
            </td>
          </template>
          <template v-else>
            <td class="cp-pay-num">{{ fmtMoneyLoan(p.principal_paid, currency) }}</td>
            <td class="cp-pay-num">{{ Number(p.interest_paid) > 0 ? fmtMoneyLoan(p.interest_paid, currency) : "—" }}</td>
            <td class="cp-pay-num">{{ Number(p.penalty_paid) > 0 ? fmtMoneyLoan(p.penalty_paid, currency) : "—" }}</td>
            <td class="cp-pay-note">{{ p.note || "—" }}</td>
            <td class="cp-pay-row-acts">
              <button class="cp-pay-act-edit" title="Редактировать" @click="startEdit(p)">✎</button>
              <button class="cp-pay-act-del" title="Удалить" @click="onDelete(p)">×</button>
            </td>
          </template>
        </tr>
      </tbody>
    </table>
  </div>
</template>

<style scoped>
.cp-pay-section {
  padding: 14px 0;
}
.cp-pay-head {
  display: flex; align-items: center; gap: 12px; margin-bottom: 10px;
}
.cp-pay-title {
  font-size: 13px; font-weight: 500; color: var(--t1, #1E2A4A);
}
.cp-pay-summary {
  font-size: 11px; color: var(--t3, #888780);
}
.cp-pay-summary b { color: var(--t1, #1E2A4A); font-weight: 500; }
.cp-pay-add-btn {
  margin-left: auto;
  height: 26px;
  padding: 0 12px;
  background: #7F77DD;
  color: #fff;
  border: none;
  border-radius: 6px;
  font-size: 11px;
  font-family: inherit;
  font-weight: 500;
  cursor: pointer;
}
.cp-pay-add-btn:hover { background: #6B62D6; }

.cp-pay-form {
  padding: 12px;
  background: var(--bg2, #FAFAFC);
  border: 0.5px solid #E5E7EB;
  border-radius: 8px;
  margin-bottom: 10px;
}
.cp-pay-form-row {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
  gap: 10px;
}
.cp-pay-fld {
  display: flex; flex-direction: column; gap: 3px;
}
.cp-pay-fld-wide { margin-top: 8px; }
.cp-pay-fld > span {
  font-size: 10px; color: var(--t3, #888780);
  letter-spacing: .06em; text-transform: uppercase;
}
.cp-pay-input {
  height: 26px; padding: 0 8px;
  border: 0.5px solid #E5E7EB; border-radius: 5px;
  font-size: 11.5px; font-family: inherit;
  background: var(--bg1, #fff); color: var(--t1, #1E2A4A); outline: none;
}
.cp-pay-input:focus { border-color: #7F77DD; }
.cp-pay-form-actions {
  display: flex; gap: 8px; justify-content: flex-end;
  margin-top: 10px;
}
.cp-pay-btn-cancel, .cp-pay-btn-primary {
  height: 26px; padding: 0 14px;
  border-radius: 6px; font-size: 11px;
  font-family: inherit; font-weight: 500; cursor: pointer;
}
.cp-pay-btn-cancel {
  background: transparent; border: 0.5px solid #E5E7EB;
  color: var(--t3, #888780);
}
.cp-pay-btn-primary {
  background: #7F77DD; color: #fff; border: none;
}
.cp-pay-btn-primary:disabled { opacity: .5; cursor: not-allowed; }
.cp-pay-err, .cp-pay-err-banner {
  margin-top: 8px;
  padding: 6px 10px;
  background: rgba(226, 75, 74, .06);
  color: #C0322F;
  border-radius: 5px;
  font-size: 11px;
}

.cp-pay-loading, .cp-pay-empty {
  padding: 24px 12px;
  text-align: center;
  font-size: 11px;
  color: var(--t3, #888780);
  font-style: italic;
}
.cp-pay-tbl {
  width: 100%; border-collapse: collapse; font-size: 11.5px;
}
.cp-pay-tbl th {
  text-align: left; padding: 6px 10px;
  background: var(--bg2, #FAFAFC);
  border-bottom: 0.5px solid #E5E7EB;
  font-size: 9.5px; font-weight: 500;
  color: var(--t3, #888780); text-transform: uppercase; letter-spacing: .06em;
}
.cp-pay-num { text-align: right; font-variant-numeric: tabular-nums; }
.cp-pay-tbl td {
  padding: 6px 10px;
  border-bottom: 0.5px solid #F1EFE8;
  color: var(--t1, #1E2A4A);
}
.cp-pay-row-editing td { background: rgba(127, 119, 221, .04); }
.cp-pay-row-acts { text-align: right; white-space: nowrap; }
.cp-pay-row-acts button {
  width: 22px; height: 22px;
  border: 0.5px solid #E5E7EB; border-radius: 4px;
  background: transparent;
  font-family: inherit; cursor: pointer;
  margin-left: 3px;
}
.cp-pay-act-edit { color: #534AB7; }
.cp-pay-act-edit:hover { background: rgba(127, 119, 221, .08); }
.cp-pay-act-del { color: #C0322F; }
.cp-pay-act-del:hover { background: rgba(226, 75, 74, .08); }
.cp-pay-act-ok { color: #0F6E56; }
.cp-pay-act-ok:hover { background: rgba(29, 158, 117, .08); }
.cp-pay-act-cancel { color: var(--t3, #888780); }
.cp-pay-input-sm {
  width: 100%; height: 22px; padding: 0 6px;
  border: 0.5px solid #E5E7EB; border-radius: 4px;
  font-size: 11px; font-family: inherit;
  background: var(--bg1, #fff); outline: none;
}
.cp-pay-input-sm:focus { border-color: #7F77DD; }
.cp-pay-note {
  color: var(--t3, #888780);
  max-width: 240px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
</style>
