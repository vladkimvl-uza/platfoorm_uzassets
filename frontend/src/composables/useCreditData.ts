/**
 * useCreditData v5 — добавлено для 19c-8:
 *   • loanEditorOpen / loanEditorMode / loanEditorDraft / loanEditorErrors
 *   • Backup в localStorage с auto-save (debounce 800ms)
 *   • openLoanEditor(loan?) / closeLoanEditor() / saveLoanEditor()
 *   • restoreLoanEditorBackup() / clearLoanEditorBackup()
 *   • excelImportOpen / excelImportRows / excelImportResult
 *   • parseExcelFile(file) / submitExcelImport(overwrite)
 */
import { computed, reactive, ref, watch } from "vue";
import {
  type CompaniesWithLoansResponse,
  type CompanyAggregateRow,
  type CompanyWithLoansRow,
  type CreditPortfolioAggregate,
  type FxRateRead,
  type LoanCreate,
  type LoanRead,
  type LoanUpdate,
  type LoanBulkItem,
  type LoansFilter,
  type BulkImportResponse,
  type RiskBubblePoint,
  type RiskMetrics,
  type SankeyFlow,
  bulkImport,
  createLoan,
  deleteLoan,
  getAggregate,
  getCompaniesOverview,
  getCompaniesWithLoans,
  getFxRates,
  getLoan,
  getLoans,
  getRiskBubble,
  getRiskMetrics,
  getSankey,
  toNum,
  updateLoan,
  yearOf,
} from "@/api/credit";

/* ─────────────────────────── Types ─────────────────────────── */

export type View = "overview" | "lenders" | "risk" | "payments" | "loans";
export type Fmt = "usd" | "uzs";
export type SortKey = "bank" | "company" | "currency" | "rate" | "debt_usd" | "date_due";
export type SortDir = "asc" | "desc";
export type EditorMode = "create" | "edit";

const BACKUP_PREFIX = "uz_loan_backup_";
const BACKUP_NEW_KEY = BACKUP_PREFIX + "NEW";
const BACKUP_TTL_DAYS = 7;

/* ─────────────────────────── State ─────────────────────────── */
// filter state (view/fmt/selectedCompany) persists через useSavedFilter.
// Loan-editor backup (BACKUP_PREFIX выше) — отдельная независимая система для
// черновиков формы редактирования займа.
import { useSavedFilter } from "@/composables/useSavedFilter";

const view = useSavedFilter<View>("credit.view", "overview");
const fmt = useSavedFilter<Fmt>("credit.fmt", "usd");

const selectedCompanyId = useSavedFilter<string | null>("credit.selectedCompanyId", null);
const selectedCompanyMeta = ref<CompanyWithLoansRow | null>(null);

const aggregate = ref<CreditPortfolioAggregate | null>(null);
const loans = ref<LoanRead[]>([]);
const companiesWithLoans = ref<CompanyWithLoansRow[]>([]);
const companiesOverview = ref<CompanyAggregateRow[]>([]);
const fxRates = ref<FxRateRead[]>([]);

const riskMetrics = ref<RiskMetrics | null>(null);
const riskBubble = ref<RiskBubblePoint[]>([]);
const sankeyFlows = ref<SankeyFlow[]>([]);

const loanDetail = ref<LoanRead | null>(null);
const loanDetailOpen = ref(false);
const loanDetailLoading = ref(false);

// 19c-8 — Editor state
const loanEditorOpen = ref(false);
const loanEditorMode = ref<EditorMode>("create");
const loanEditorDraft = ref<LoanCreate | null>(null);
const loanEditorOriginalId = ref<string | null>(null);
const loanEditorErrors = ref<Record<string, string>>({});
const loanEditorSaving = ref(false);
const loanEditorBackupAvailable = ref<{ ageDays: number; loanCode: string } | null>(null);

// 19c-8 — Excel import state
const excelImportOpen = ref(false);
const excelImportRows = ref<LoanBulkItem[]>([]);
const excelImportFileName = ref<string | null>(null);
const excelImportParseErrors = ref<string[]>([]);
const excelImportSubmitting = ref(false);
const excelImportResult = ref<BulkImportResponse | null>(null);
const excelImportOverwrite = ref(false);

const loading = reactive({
  aggregate: false, loans: false, companies: false, overview: false,
  fx: false, risk: false, sankey: false,
});
const error = ref<string | null>(null);

const asOfDate = ref<string>("2026-01-01");

const filterBank = ref<string | null>(null);
const filterYear = ref<number | null>(null);
const filterCurrency = ref<string | null>(null);
const filterStatus = ref<"overdue" | "active" | "all">("all");
const sortKey = ref<SortKey>("debt_usd");
const sortDir = ref<SortDir>("desc");

/* ─────────────────────────── Computed ─────────────────────────── */

const isAllCompanies = computed(() => selectedCompanyId.value === null);
const asOfYear = computed(() => parseInt(asOfDate.value.slice(0, 4), 10));

const totalsBanner = computed(() => {
  const agg = aggregate.value;
  if (!agg) return null;
  return {
    totalUsd: toNum(agg.total_usd), loansCount: agg.loans_count,
    banksCount: agg.banks_count, avgRate: toNum(agg.avg_rate),
    loanedUsd: toNum(agg.loaned_total_usd), repaidUsd: toNum(agg.repaid_total_usd),
    repaidPct: agg.repaid_pct,
    paymentThisYear: toNum(agg.payment_this_year),
    paymentNextYear: toNum(agg.payment_next_year),
    overdueAmount: toNum(agg.overdue_amount),
    topPayment: agg.top_payment_loan, nearestPayment: agg.nearest_payment_loan,
  };
});

const topPaymentsCurrentYear = computed<LoanRead[]>(() => {
  const y = asOfYear.value;
  return loans.value
    .filter((l) => l.date_due && yearOf(l.date_due) === y)
    .slice()
    .sort((a, b) => toNum(b.debt_usd) - toNum(a.debt_usd))
    .slice(0, 15);
});

const allPaymentsCurrentYearCount = computed<number>(() => {
  const y = asOfYear.value;
  return loans.value.filter((l) => l.date_due && yearOf(l.date_due) === y).length;
});

const filteredLoans = computed<LoanRead[]>(() => {
  let rows = loans.value.slice();
  if (selectedCompanyId.value !== null) rows = rows.filter((l) => l.company_id === selectedCompanyId.value);
  if (filterBank.value) {
    const b = filterBank.value;
    rows = rows.filter((l) => l.bank === b || l.bank_short_name === b);
  }
  if (filterCurrency.value) rows = rows.filter((l) => l.currency === filterCurrency.value);
  if (filterYear.value !== null) {
    const y = filterYear.value;
    rows = rows.filter((l) => yearOf(l.date_due) === y);
  }
  if (filterStatus.value === "overdue") {
    const today = asOfDate.value;
    rows = rows.filter((l) => l.date_due !== null && l.date_due! < today);
  } else if (filterStatus.value === "active") {
    const today = asOfDate.value;
    rows = rows.filter((l) => l.date_due === null || l.date_due! >= today);
  }
  const key = sortKey.value;
  const dir = sortDir.value === "asc" ? 1 : -1;
  rows.sort((a, b) => {
    let av: any, bv: any;
    switch (key) {
      case "bank": av = a.bank_short_name || a.bank; bv = b.bank_short_name || b.bank; return av.localeCompare(bv) * dir;
      case "company": av = a.company_name_ru || ""; bv = b.company_name_ru || ""; return av.localeCompare(bv) * dir;
      case "currency": return a.currency.localeCompare(b.currency) * dir;
      case "rate": return (toNum(a.rate) - toNum(b.rate)) * dir;
      case "debt_usd": return (toNum(a.debt_usd) - toNum(b.debt_usd)) * dir;
      case "date_due":
        av = a.date_due || "9999-12-31"; bv = b.date_due || "9999-12-31";
        return av.localeCompare(bv) * dir;
      default: return 0;
    }
  });
  return rows;
});

const isAnyFilterActive = computed(() =>
  filterBank.value !== null || filterYear.value !== null ||
  filterCurrency.value !== null || filterStatus.value !== "all",
);

/* ─────────────────────────── Loaders ─────────────────────────── */

function _scopeParams() {
  return selectedCompanyId.value
    ? { company_id: selectedCompanyId.value, as_of: asOfDate.value }
    : { as_of: asOfDate.value };
}

async function loadAggregate(): Promise<void> {
  loading.aggregate = true; error.value = null;
  try { aggregate.value = await getAggregate(_scopeParams()); }
  catch (e: any) {
    aggregate.value = null;
    error.value = e?.response?.data?.detail || e?.message || "Failed to load aggregate";
    console.error("[useCreditData.loadAggregate]", e);
  } finally { loading.aggregate = false; }
}
async function loadLoans(): Promise<void> {
  loading.loans = true;
  try { loans.value = await getLoans({}); }
  catch (e: any) {
    loans.value = [];
    error.value = e?.response?.data?.detail || e?.message || "Failed to load loans";
  } finally { loading.loans = false; }
}
async function loadCompaniesWithLoans(): Promise<void> {
  loading.companies = true;
  try { const r: CompaniesWithLoansResponse = await getCompaniesWithLoans(); companiesWithLoans.value = r.items; }
  catch (e: any) { companiesWithLoans.value = []; }
  finally { loading.companies = false; }
}
async function loadCompaniesOverview(): Promise<void> {
  loading.overview = true;
  try { companiesOverview.value = await getCompaniesOverview(asOfDate.value); }
  catch (e: any) { companiesOverview.value = []; }
  finally { loading.overview = false; }
}
async function loadFxRates(): Promise<void> {
  loading.fx = true;
  try { fxRates.value = await getFxRates(asOfDate.value); }
  catch (e: any) { fxRates.value = []; }
  finally { loading.fx = false; }
}
async function loadRiskMetricsFn(): Promise<void> {
  loading.risk = true;
  try { riskMetrics.value = await getRiskMetrics(_scopeParams()); }
  catch (e: any) { riskMetrics.value = null; }
  finally { loading.risk = false; }
}
async function loadRiskBubbleFn(): Promise<void> {
  try { riskBubble.value = await getRiskBubble(_scopeParams()); }
  catch (e: any) { riskBubble.value = []; }
}
async function loadSankeyFn(): Promise<void> {
  loading.sankey = true;
  try { sankeyFlows.value = await getSankey(_scopeParams()); }
  catch (e: any) { sankeyFlows.value = []; }
  finally { loading.sankey = false; }
}

async function loadAll(): Promise<void> {
  await Promise.allSettled([
    loadAggregate(), loadLoans(), loadCompaniesWithLoans(),
    loadCompaniesOverview(), loadFxRates(),
    loadRiskMetricsFn(), loadRiskBubbleFn(), loadSankeyFn(),
  ]);
  _detectStaleBackups();
}

async function setSelectedCompany(co: CompanyWithLoansRow | null): Promise<void> {
  selectedCompanyId.value = co?.company_id || null;
  selectedCompanyMeta.value = co;
  filterBank.value = null; filterYear.value = null;
  filterCurrency.value = null; filterStatus.value = "all";
  await Promise.allSettled([loadAggregate(), loadRiskMetricsFn(), loadRiskBubbleFn(), loadSankeyFn()]);
}
async function setSelectedCompanyById(id: string): Promise<void> {
  const co = companiesWithLoans.value.find((c) => c.company_id === id) || null;
  await setSelectedCompany(co);
  setView("overview");
}

function setView(v: View) { view.value = v; }
function setFmt(f: Fmt) { fmt.value = f; }
function filterByBank(b: string | null) { filterBank.value = b; view.value = "loans"; }
function filterByYear(y: number | null) { filterYear.value = y; view.value = "payments"; }
function filterByCurrency(c: string | null) { filterCurrency.value = c; view.value = "loans"; }
function filterOverdue(on: boolean) { filterStatus.value = on ? "overdue" : "all"; view.value = "loans"; }
function setSort(key: SortKey) {
  if (sortKey.value === key) sortDir.value = sortDir.value === "asc" ? "desc" : "asc";
  else { sortKey.value = key; sortDir.value = "desc"; }
}
function clearFilters() {
  filterBank.value = null; filterYear.value = null;
  filterCurrency.value = null; filterStatus.value = "all";
}

/* ─────────────────────────── Loan Detail Modal ─────────────────────────── */

async function openLoanDetail(loanId: string): Promise<void> {
  loanDetailOpen.value = true; loanDetailLoading.value = true;
  try { loanDetail.value = await getLoan(loanId); }
  catch (e: any) {
    loanDetail.value = null;
    error.value = e?.response?.data?.detail || e?.message || "Failed to load loan";
  } finally { loanDetailLoading.value = false; }
}
function closeLoanDetail(): void {
  loanDetailOpen.value = false;
  setTimeout(() => { loanDetail.value = null; }, 300);
}

/* ─────────────────────────── Loan Editor (19c-8) ─────────────────────────── */

function _emptyDraft(): LoanCreate {
  return {
    loan_code: "", company_id: "", borrower_unit: null,
    bank: "", bank_short_name: null, contract_ref: null,
    currency: "USD", rate: null, rate_text: null,
    sum_total: null, sum_disbursed: null,
    debt_currency: null, debt_usd: null,
    date_get: null, date_due: null,
    is_guaranteed: false, lender_type: null,
    auto_flags: {}, notes: null,
    as_of_date: asOfDate.value,
  };
}

function _draftFromLoan(loan: LoanRead): LoanCreate {
  return {
    loan_code: loan.loan_code, company_id: loan.company_id,
    borrower_unit: loan.borrower_unit ?? null,
    bank: loan.bank, bank_short_name: loan.bank_short_name ?? null,
    contract_ref: loan.contract_ref ?? null,
    currency: loan.currency,
    rate: loan.rate ?? null, rate_text: loan.rate_text ?? null,
    sum_total: loan.sum_total ?? null, sum_disbursed: loan.sum_disbursed ?? null,
    debt_currency: loan.debt_currency ?? null, debt_usd: loan.debt_usd ?? null,
    date_get: loan.date_get ?? null, date_due: loan.date_due ?? null,
    is_guaranteed: loan.is_guaranteed,
    lender_type: loan.lender_type ?? null,
    auto_flags: loan.auto_flags || {},
    notes: loan.notes ?? null,
    as_of_date: loan.as_of_date ?? asOfDate.value,
  };
}

function _backupKeyFor(draft: LoanCreate, mode: EditorMode): string {
  if (mode === "edit" && draft.loan_code) return BACKUP_PREFIX + draft.loan_code;
  return BACKUP_NEW_KEY;
}

function _saveBackup() {
  if (!loanEditorDraft.value) return;
  const key = _backupKeyFor(loanEditorDraft.value, loanEditorMode.value);
  try {
    localStorage.setItem(key, JSON.stringify({
      draft: loanEditorDraft.value,
      mode: loanEditorMode.value,
      originalId: loanEditorOriginalId.value,
      ts: Date.now(),
    }));
  } catch (e) {
    console.warn("[useCreditData._saveBackup] localStorage write failed", e);
  }
}

function _readBackup(key: string): { draft: LoanCreate; mode: EditorMode; originalId: string | null; ts: number } | null {
  try {
    const raw = localStorage.getItem(key);
    if (!raw) return null;
    return JSON.parse(raw);
  } catch (e) {
    console.warn("[useCreditData._readBackup] failed", e);
    return null;
  }
}

function _clearBackup(loanCode: string | null) {
  try {
    if (loanCode) localStorage.removeItem(BACKUP_PREFIX + loanCode);
    localStorage.removeItem(BACKUP_NEW_KEY);
  } catch { /* noop */ }
}

/** Авто-cleanup старых бэкапов > BACKUP_TTL_DAYS дней. */
function _detectStaleBackups() {
  try {
    const now = Date.now();
    const ttlMs = BACKUP_TTL_DAYS * 24 * 60 * 60 * 1000;
    const keys: string[] = [];
    for (let i = 0; i < localStorage.length; i++) {
      const k = localStorage.key(i);
      if (k && k.startsWith(BACKUP_PREFIX)) keys.push(k);
    }
    for (const k of keys) {
      const b = _readBackup(k);
      if (b && now - b.ts > ttlMs) localStorage.removeItem(k);
    }
  } catch { /* noop */ }
}

function openLoanEditor(loan?: LoanRead | null): void {
  loanEditorErrors.value = {};
  loanEditorBackupAvailable.value = null;

  if (loan) {
    loanEditorMode.value = "edit";
    loanEditorOriginalId.value = loan.id;
    loanEditorDraft.value = _draftFromLoan(loan);
  } else {
    loanEditorMode.value = "create";
    loanEditorOriginalId.value = null;
    loanEditorDraft.value = _emptyDraft();
  }

  // Check if there's a backup more recent than this snapshot
  const key = _backupKeyFor(loanEditorDraft.value, loanEditorMode.value);
  const b = _readBackup(key);
  if (b) {
    const ageDays = Math.floor((Date.now() - b.ts) / (1000 * 60 * 60 * 24));
    if (ageDays <= BACKUP_TTL_DAYS) {
      loanEditorBackupAvailable.value = {
        ageDays,
        loanCode: b.draft.loan_code || "(новый)",
      };
    }
  }

  loanEditorOpen.value = true;
}

function closeLoanEditor(): void {
  loanEditorOpen.value = false;
  setTimeout(() => {
    loanEditorDraft.value = null;
    loanEditorErrors.value = {};
    loanEditorBackupAvailable.value = null;
  }, 300);
}

function restoreLoanEditorBackup(): void {
  if (!loanEditorDraft.value) return;
  const key = _backupKeyFor(loanEditorDraft.value, loanEditorMode.value);
  const b = _readBackup(key);
  if (!b) return;
  loanEditorDraft.value = b.draft;
  loanEditorMode.value = b.mode;
  loanEditorOriginalId.value = b.originalId;
  loanEditorBackupAvailable.value = null;
}

function dismissLoanEditorBackup(): void {
  if (!loanEditorDraft.value) return;
  _clearBackup(loanEditorDraft.value.loan_code || null);
  loanEditorBackupAvailable.value = null;
}

function _validate(d: LoanCreate): Record<string, string> {
  const errs: Record<string, string> = {};
  if (!d.loan_code || d.loan_code.length < 1) errs.loan_code = "Обязательное поле";
  if (d.loan_code && d.loan_code.length > 32) errs.loan_code = "Не более 32 символов";
  if (!d.company_id) errs.company_id = "Выберите компанию";
  if (!d.bank || d.bank.length < 1) errs.bank = "Обязательное поле";
  if (!d.currency || d.currency.length < 3) errs.currency = "Валюта обязательна";
  const r = d.rate;
  if (r !== null && r !== undefined && r !== "") {
    const n = toNum(r);
    if (n < 0 || n >= 1) errs.rate = "Ставка от 0 до <1 (десятичная: 0.085 = 8.5%)";
  }
  if (d.date_get && d.date_due && d.date_get > d.date_due) {
    errs.date_due = "Дата погашения раньше даты получения";
  }
  return errs;
}

const loanEditorIsValid = computed<boolean>(() => {
  if (!loanEditorDraft.value) return false;
  return Object.keys(_validate(loanEditorDraft.value)).length === 0;
});

async function saveLoanEditor(): Promise<boolean> {
  if (!loanEditorDraft.value) return false;
  const draft = loanEditorDraft.value;
  loanEditorErrors.value = _validate(draft);
  if (Object.keys(loanEditorErrors.value).length > 0) return false;

  loanEditorSaving.value = true;
  try {
    if (loanEditorMode.value === "edit" && loanEditorOriginalId.value) {
      const updated = await updateLoan(loanEditorOriginalId.value, draft as LoanUpdate);
      // Update local list
      const idx = loans.value.findIndex((l) => l.id === updated.id);
      if (idx >= 0) loans.value.splice(idx, 1, updated);
      // Update current detail if same
      if (loanDetail.value?.id === updated.id) loanDetail.value = updated;
    } else {
      const created = await createLoan(draft);
      loans.value = [created, ...loans.value];
    }
    _clearBackup(draft.loan_code || null);
    // Reload aggregates (counts changed)
    await Promise.allSettled([loadAggregate(), loadCompaniesOverview()]);
    closeLoanEditor();
    return true;
  } catch (e: any) {
    const detail = e?.response?.data?.detail;
    error.value = typeof detail === "string" ? detail : e?.message || "Save failed";
    if (typeof detail === "string" && /already exists/i.test(detail)) {
      loanEditorErrors.value = { ...loanEditorErrors.value, loan_code: "Код кредита уже используется" };
    }
    console.error("[useCreditData.saveLoanEditor]", e);
    return false;
  } finally {
    loanEditorSaving.value = false;
  }
}

// Auto-save backup with debounce
let _backupTimer: number | null = null;
watch(
  () => loanEditorDraft.value,
  () => {
    if (!loanEditorDraft.value || !loanEditorOpen.value) return;
    if (_backupTimer !== null) clearTimeout(_backupTimer);
    _backupTimer = window.setTimeout(_saveBackup, 800);
  },
  { deep: true },
);

/* ─────────────────────────── Excel Import (19c-8) ─────────────────────────── */

function openExcelImport(): void {
  excelImportRows.value = [];
  excelImportFileName.value = null;
  excelImportParseErrors.value = [];
  excelImportResult.value = null;
  excelImportOverwrite.value = false;
  excelImportOpen.value = true;
}

function closeExcelImport(): void {
  excelImportOpen.value = false;
  setTimeout(() => {
    excelImportRows.value = [];
    excelImportFileName.value = null;
    excelImportParseErrors.value = [];
    excelImportResult.value = null;
  }, 300);
}

/** Parse XLSX file via SheetJS (xlsx).
 *  Header row = first row. Column → field mapping by header name (RU/EN). */
async function parseExcelFile(file: File): Promise<void> {
  excelImportFileName.value = file.name;
  excelImportRows.value = [];
  excelImportParseErrors.value = [];
  excelImportResult.value = null;

  let XLSX: any;
  try { XLSX = await import("xlsx"); }
  catch (e) {
    excelImportParseErrors.value = [
      "Библиотека xlsx не установлена. Выполни:  npm install xlsx --workspace=frontend",
      "и пересобери frontend контейнер.",
    ];
    return;
  }

  let workbook: any;
  try {
    const buf = await file.arrayBuffer();
    workbook = XLSX.read(buf, { type: "array", cellDates: true });
  } catch (e: any) {
    excelImportParseErrors.value = ["Не удалось прочитать файл: " + e.message];
    return;
  }

  const sheetName = workbook.SheetNames[0];
  if (!sheetName) {
    excelImportParseErrors.value = ["В файле нет листов"];
    return;
  }
  const sheet = workbook.Sheets[sheetName];
  const rows: Record<string, any>[] = XLSX.utils.sheet_to_json(sheet, { defval: null, raw: false });

  if (rows.length === 0) {
    excelImportParseErrors.value = ["Лист пуст"];
    return;
  }

  // Header → field mapping (case-insensitive, accepts RU and EN names)
  const fieldAliases: Record<string, string> = {
    "loan_code": "loan_code", "код": "loan_code", "loan code": "loan_code", "id": "loan_code",
    "company_name_ru": "company_name_ru", "компания": "company_name_ru", "company": "company_name_ru",
    "company_code": "company_code",
    "borrower_unit": "borrower_unit", "филиал": "borrower_unit",
    "bank": "bank", "банк": "bank", "кредитор": "bank",
    "bank_short_name": "bank_short_name",
    "contract_ref": "contract_ref", "контракт": "contract_ref", "договор": "contract_ref",
    "currency": "currency", "валюта": "currency",
    "rate": "rate", "ставка": "rate",
    "rate_text": "rate_text",
    "sum_total": "sum_total", "сумма": "sum_total", "сумма всего": "sum_total",
    "sum_disbursed": "sum_disbursed", "выбрано": "sum_disbursed",
    "debt_currency": "debt_currency", "долг": "debt_currency",
    "debt_usd": "debt_usd", "долг usd": "debt_usd",
    "date_get": "date_get", "дата получения": "date_get",
    "date_due": "date_due", "дата погашения": "date_due", "срок": "date_due",
    "is_guaranteed": "is_guaranteed", "гарантия": "is_guaranteed",
    "lender_type": "lender_type", "тип": "lender_type",
    "notes": "notes", "примечания": "notes",
  };

  function mapHeader(h: string): string | null {
    const norm = h.trim().toLowerCase();
    return fieldAliases[norm] || null;
  }

  function parseDate(v: any): string | null {
    if (v === null || v === undefined || v === "") return null;
    if (v instanceof Date) {
      const y = v.getFullYear(), m = String(v.getMonth() + 1).padStart(2, "0"), d = String(v.getDate()).padStart(2, "0");
      return `${y}-${m}-${d}`;
    }
    const s = String(v).trim();
    // RU: 31.12.2026  →  2026-12-31
    let m = /^(\d{1,2})\.(\d{1,2})\.(\d{4})$/.exec(s);
    if (m) return `${m[3]}-${m[2].padStart(2, "0")}-${m[1].padStart(2, "0")}`;
    // ISO already
    m = /^(\d{4})-(\d{2})-(\d{2})/.exec(s);
    if (m) return `${m[1]}-${m[2]}-${m[3]}`;
    return null;
  }

  function parseRate(v: any): number | null {
    if (v === null || v === undefined || v === "") return null;
    const s = String(v).trim().replace(",", ".").replace(/\s/g, "");
    if (s.endsWith("%")) {
      const n = parseFloat(s.slice(0, -1));
      return Number.isFinite(n) ? n / 100 : null;
    }
    const n = parseFloat(s);
    if (!Number.isFinite(n)) return null;
    // Heuristic: > 1 → assume percent; < 1 → assume decimal
    return n >= 1 ? n / 100 : n;
  }

  function parseNum(v: any): number | null {
    if (v === null || v === undefined || v === "") return null;
    const s = String(v).trim().replace(/\s/g, "").replace(",", ".");
    const n = parseFloat(s);
    return Number.isFinite(n) ? n : null;
  }

  function parseBool(v: any): boolean {
    if (typeof v === "boolean") return v;
    const s = String(v || "").trim().toLowerCase();
    return ["1", "true", "да", "yes", "y", "+", "guaranteed", "гарантирован"].includes(s);
  }

  const items: LoanBulkItem[] = [];
  const errors: string[] = [];
  rows.forEach((r, i) => {
    const item: any = { is_guaranteed: false, auto_flags: {} };
    for (const k in r) {
      const f = mapHeader(k);
      if (!f) continue;
      const v = r[k];
      if (v === null || v === undefined || v === "") continue;
      switch (f) {
        case "rate": item[f] = parseRate(v); break;
        case "sum_total": case "sum_disbursed":
        case "debt_currency": case "debt_usd":
          item[f] = parseNum(v); break;
        case "date_get": case "date_due":
          item[f] = parseDate(v); break;
        case "is_guaranteed": item[f] = parseBool(v); break;
        case "currency": item[f] = String(v).trim().toUpperCase(); break;
        default: item[f] = String(v).trim();
      }
    }
    // Validate minimum fields
    const rowNum = i + 2; // +1 header, +1 zero-indexed
    if (!item.loan_code) errors.push(`Строка ${rowNum}: нет loan_code`);
    if (!item.bank) errors.push(`Строка ${rowNum}: нет bank`);
    if (!item.currency) errors.push(`Строка ${rowNum}: нет currency`);
    if (!item.company_name_ru && !item.company_code && !item.company_id) {
      errors.push(`Строка ${rowNum}: нет компании (нужно company_name_ru или company_code)`);
    }
    items.push(item);
  });

  excelImportRows.value = items;
  excelImportParseErrors.value = errors;
}

async function submitExcelImport(): Promise<boolean> {
  if (excelImportRows.value.length === 0) return false;
  excelImportSubmitting.value = true;
  excelImportResult.value = null;
  try {
    const resp = await bulkImport({
      items: excelImportRows.value,
      overwrite_existing: excelImportOverwrite.value,
    });
    excelImportResult.value = resp;
    if (resp.inserted > 0 || resp.updated > 0) {
      await Promise.allSettled([loadLoans(), loadAggregate(), loadCompaniesOverview()]);
    }
    return true;
  } catch (e: any) {
    error.value = e?.response?.data?.detail || e?.message || "Import failed";
    console.error("[useCreditData.submitExcelImport]", e);
    return false;
  } finally {
    excelImportSubmitting.value = false;
  }
}

/* ─────────────────────────── Composable export ─────────────────────────── */

export function useCreditData() {
  return {
    view, fmt,
    selectedCompanyId, selectedCompanyMeta, isAllCompanies,
    asOfDate, asOfYear,
    aggregate, loans, companiesWithLoans, companiesOverview, fxRates,
    riskMetrics, riskBubble, sankeyFlows,
    loanDetail, loanDetailOpen, loanDetailLoading,
    loanEditorOpen, loanEditorMode, loanEditorDraft, loanEditorErrors,
    loanEditorSaving, loanEditorIsValid, loanEditorBackupAvailable,
    loanEditorOriginalId,
    excelImportOpen, excelImportRows, excelImportFileName,
    excelImportParseErrors, excelImportSubmitting, excelImportResult,
    excelImportOverwrite,
    loading, error,
    totalsBanner, filteredLoans, isAnyFilterActive,
    topPaymentsCurrentYear, allPaymentsCurrentYearCount,
    filterBank, filterYear, filterCurrency, filterStatus,
    sortKey, sortDir,
    loadAll, loadAggregate, loadLoans,
    loadCompaniesWithLoans, loadCompaniesOverview, loadFxRates,
    loadRiskMetrics: loadRiskMetricsFn,
    loadRiskBubble: loadRiskBubbleFn,
    loadSankey: loadSankeyFn,
    setSelectedCompany, setSelectedCompanyById,
    setView, setFmt,
    filterByBank, filterByYear, filterByCurrency, filterOverdue,
    setSort, clearFilters,
    openLoanDetail, closeLoanDetail,
    openLoanEditor, closeLoanEditor, saveLoanEditor,
    restoreLoanEditorBackup, dismissLoanEditorBackup,
    openExcelImport, closeExcelImport, parseExcelFile, submitExcelImport,
    deleteLoan,
  };
}
