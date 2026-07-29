/**
 * api/credit.ts v2 — добавлено для 19c-8:
 *   • LoanBulkItem (extends LoanCreate с company_code/company_name_ru)
 *   • BulkImportRequest, BulkImportResponse (уже было)
 *   • bulkImport()  POST /credit-portfolio/loans/bulk
 */
import { api as apiClient } from "./client";
import { fmtNumber } from "@/locale";
import { getCurrentLocale, t } from "@/locale/i18n";
import { i18nKey } from "@/locale/keys";

export type Decimal = string | number;
export function toNum(v: Decimal | null | undefined): number {
  if (v === null || v === undefined || v === "") return 0;
  if (typeof v === "number") return Number.isFinite(v) ? v : 0;
  const n = parseFloat(v);
  return Number.isFinite(n) ? n : 0;
}

export type LenderType = "bond" | "foreign" | "local" | "state";

export const CP_LENDER_LABELS: Record<LenderType, { label: string; color: string }> = {
  bond:    { label: i18nKey("Бонд"),          color: "#C99B5C" },
  foreign: { label: i18nKey("Иностранный"),   color: "#5DBFA1" },
  local:   { label: i18nKey("Местный"),       color: "#5478B0" },
  state:   { label: i18nKey("Государственный"),color: "#C97070" },
};

export const CP_CURRENCIES = ["USD", "EUR", "CNY", "JPY", "RUB", "SDR", "UZS", "KZT", "GBP"] as const;

export const CURRENCY_COLORS: Record<string, string> = {
  USD: "#7F77DD", EUR: "#0A7B5E", CNY: "#EF9F27", JPY: "#E24B4A",
  SDR: "#9C8AC8", RUB: "#5B7FBC", UZS: "#888780", KZT: "#7A6C9F", GBP: "#385B82",
};
export function cpCurrencyColor(c: string): string { return CURRENCY_COLORS[c] || "#888780"; }

/* ─────────────────────────── Loan schemas ─────────────────────────── */

export interface LoanRead {
  id: string;
  loan_code: string;
  company_id: string;
  company_name_ru?: string | null;
  borrower_unit?: string | null;
  bank: string;
  bank_short_name?: string | null;
  contract_ref?: string | null;
  currency: string;
  rate?: Decimal | null;
  rate_text?: string | null;
  sum_total?: Decimal | null;
  sum_disbursed?: Decimal | null;
  debt_currency?: Decimal | null;
  debt_usd?: Decimal | null;
  date_get?: string | null;
  date_due?: string | null;
  is_guaranteed: boolean;
  lender_type?: LenderType | null;
  auto_flags: Record<string, any>;
  notes?: string | null;
  as_of_date?: string | null;
  deleted_at?: string | null;
  created_at: string;
  updated_at: string;
}

export interface LoanCreate {
  loan_code: string;
  company_id: string;
  borrower_unit?: string | null;
  bank: string;
  bank_short_name?: string | null;
  contract_ref?: string | null;
  currency: string;
  rate?: Decimal | null;
  rate_text?: string | null;
  sum_total?: Decimal | null;
  sum_disbursed?: Decimal | null;
  debt_currency?: Decimal | null;
  debt_usd?: Decimal | null;
  date_get?: string | null;
  date_due?: string | null;
  is_guaranteed?: boolean;
  lender_type?: LenderType | null;
  auto_flags?: Record<string, any>;
  notes?: string | null;
  as_of_date?: string | null;
}
export type LoanUpdate = Partial<LoanCreate>;

/** LoanBulkItem — для импорта из Excel/JSON. company_id опционален —
 *  можно использовать company_code или company_name_ru для разрешения. */
export interface LoanBulkItem extends Omit<LoanCreate, "company_id"> {
  company_id?: string | null;
  company_code?: string | null;
  company_name_ru?: string | null;
}

export interface BulkImportRequest {
  items: LoanBulkItem[];
  overwrite_existing?: boolean;
}

export interface BulkImportResponse {
  inserted: number;
  updated: number;
  skipped: number;
  errors: string[];
}

/* ─────────────────────────── Aggregate schemas ─────────────────────────── */

export interface CurrencyBreakdown {
  currency: string; debt_usd: Decimal; debt_currency: Decimal;
  pct_of_total: number; avg_rate?: Decimal | null; loans_count: number;
}
export interface LenderTypeBreakdown {
  lender_type: LenderType; label: string; color: string;
  debt_usd: Decimal; pct_of_total: number; loans_count: number;
}
export interface BankBreakdown {
  bank_short_name: string; debt_usd: Decimal; pct_of_total: number; loans_count: number;
}
export interface BankRow {
  bank: string; bank_short_name: string; lender_type?: LenderType | null;
  debt_usd: Decimal; loans_count: number; pct_of_total: number;
}
export interface YearBucket { year: number; debt_usd: Decimal; loans_count: number; }
export interface MaturityBucket { bucket: string; debt_usd: Decimal; loans_count: number; }
export interface RateMatrixCell {
  lender_type: LenderType; currency: string; rate: Decimal;
  debt_usd: Decimal; loans_count: number;
}
export interface TopLoanRef {
  id: string; loan_code: string; bank: string; bank_short_name: string;
  company_name_ru: string; debt_usd: Decimal;
  date_due?: string | null; days_until_due?: number | null;
  currency?: string | null; debt_currency?: Decimal | null; rate?: Decimal | null;
}

export interface CreditPortfolioAggregate {
  as_of_date: string;
  total_usd: Decimal; total_local: Record<string, Decimal>;
  loans_count: number; banks_count: number; avg_rate: Decimal;
  loaned_total_usd: Decimal; repaid_total_usd: Decimal; repaid_pct: number;
  by_currency: CurrencyBreakdown[];
  by_lender_type: LenderTypeBreakdown[];
  by_bank_top10: BankBreakdown[];
  by_bank_full: BankRow[];
  by_year: YearBucket[];
  by_bucket: MaturityBucket[];
  rate_matrix: RateMatrixCell[];
  guaranteed_amount: Decimal; unguaranteed_amount: Decimal;
  payment_this_year: Decimal; payment_next_year: Decimal; overdue_amount: Decimal;
  top_payment_loan?: TopLoanRef | null;
  nearest_payment_loan?: TopLoanRef | null;
  avg_rate_by_currency: Record<string, Decimal>;
}

export interface CompanyWithLoansRow {
  company_id: string; company_name_ru: string; company_code?: string | null;
  sector?: string | null; sector_color?: string | null;
  loans_count: number; debt_usd: Decimal;
}
export interface CompaniesWithLoansResponse {
  items: CompanyWithLoansRow[]; total_loans: number; total_debt_usd: Decimal;
}

export interface RiskMetrics {
  ebitda_usd?: Decimal | null; ebitda_year?: number | null;
  ebitda_source_company?: string | null; ebitda_unit_assumed?: string | null;
  ebitda_sane: boolean;
  debt_to_ebitda?: Decimal | null; icr?: Decimal | null;
  annual_interest_expense_usd: Decimal;
  refi_12mo_pct: number; concentration_top1_pct: number;
  overdue_count: number; overdue_amount_usd: Decimal;
}
export interface RiskBubblePoint {
  loan_id: string; loan_code: string; bank: string; bank_short_name: string;
  currency: string; years_to_due: number; rate_pct: number;
  debt_usd: Decimal; date_due: string;
}
export interface SankeyFlow { bank_short_name: string; year_label: string; debt_usd: Decimal; }
export interface CompanyPaymentByYear { year: number; debt_usd: Decimal; }
export interface CompanyAggregateRow {
  company_id: string; company_name_ru: string; company_code?: string | null;
  sector_code?: string | null; sector_color?: string | null;
  loans_count: number; debt_usd: Decimal;
  loaned_total_usd: Decimal; repaid_total_usd: Decimal; repaid_pct: number;
  avg_rate: Decimal;
  payment_this_year: Decimal; payment_next_year: Decimal;
  pay_by_year: CompanyPaymentByYear[]; pay_gt2032: Decimal;
}
export interface FxRateRead {
  id: string; as_of_date: string; currency: string;
  rate_to_uzs: Decimal; notes?: string | null;
}

/* ─────────────────────────── Filters ─────────────────────────── */

export interface LoansFilter {
  company_id?: string; company_code?: string; currency?: string;
  lender_type?: LenderType; search?: string; include_deleted?: boolean;
}
export interface AggregateFilter {
  company_id?: string; company_code?: string; as_of?: string;
}

/* ─────────────────────────── API functions ─────────────────────────── */

const BASE = "/credit-portfolio";

export async function getLoans(filter: LoansFilter = {}): Promise<LoanRead[]> {
  const { data } = await apiClient.get(`${BASE}/loans`, { params: filter });
  return data;
}
export async function getLoan(id: string): Promise<LoanRead> {
  const { data } = await apiClient.get(`${BASE}/loans/${id}`);
  return data;
}
export async function createLoan(payload: LoanCreate): Promise<LoanRead> {
  const { data } = await apiClient.post(`${BASE}/loans`, payload);
  return data;
}
export async function updateLoan(id: string, payload: LoanUpdate): Promise<LoanRead> {
  const { data } = await apiClient.put(`${BASE}/loans/${id}`, payload);
  return data;
}
export async function deleteLoan(id: string): Promise<void> {
  await apiClient.delete(`${BASE}/loans/${id}`);
}
/** Bulk import (Excel/JSON) — POST /credit-portfolio/loans/bulk */
export async function bulkImport(payload: BulkImportRequest): Promise<BulkImportResponse> {
  const { data } = await apiClient.post(`${BASE}/loans/bulk`, payload);
  return data;
}
export async function getAggregate(filter: AggregateFilter = {}): Promise<CreditPortfolioAggregate> {
  const { data } = await apiClient.get(`${BASE}/aggregate`, { params: filter });
  return data;
}
export async function getCompaniesWithLoans(): Promise<CompaniesWithLoansResponse> {
  const { data } = await apiClient.get(`${BASE}/companies-with-loans`);
  return data;
}
export async function getRiskMetrics(filter: AggregateFilter = {}): Promise<RiskMetrics> {
  const { data } = await apiClient.get(`${BASE}/risk-metrics`, { params: filter });
  return data;
}
export async function getRiskBubble(filter: AggregateFilter = {}): Promise<RiskBubblePoint[]> {
  const { data } = await apiClient.get(`${BASE}/risk-bubble`, { params: filter });
  return data;
}
export async function getSankey(filter: AggregateFilter = {}): Promise<SankeyFlow[]> {
  const { data } = await apiClient.get(`${BASE}/sankey`, { params: filter });
  return data;
}
export async function getCompaniesOverview(as_of?: string): Promise<CompanyAggregateRow[]> {
  const { data } = await apiClient.get(`${BASE}/companies-overview`, {
    params: as_of ? { as_of } : undefined,
  });
  return data;
}
export async function getFxRates(as_of?: string): Promise<FxRateRead[]> {
  const { data } = await apiClient.get(`${BASE}/fx-rates`, {
    params: as_of ? { as_of } : undefined,
  });
  return data;
}

// ─── Loan payments (manual repayment events) ─────────────────────────

export interface PaymentRead {
  id: string;
  loan_id: string;
  paid_date: string;             // ISO date
  principal_paid: Decimal;
  interest_paid: Decimal;
  penalty_paid: Decimal;
  currency: string;
  fx_rate_to_uzs: Decimal | null;
  note: string | null;
  created_by_user_id: string | null;
  created_at: string | null;
}

export interface PaymentCreate {
  paid_date: string;
  principal_paid: Decimal;
  interest_paid?: Decimal;
  penalty_paid?: Decimal;
  fx_rate_to_uzs?: Decimal | null;
  note?: string | null;
}

export interface PaymentUpdate {
  paid_date?: string;
  principal_paid?: Decimal;
  interest_paid?: Decimal;
  penalty_paid?: Decimal;
  fx_rate_to_uzs?: Decimal | null;
  note?: string | null;
}

export interface LoanPaymentsSummary {
  loan_id: string;
  payments_count: number;
  total_principal_paid: Decimal;
  total_interest_paid: Decimal;
  total_penalty_paid: Decimal;
  last_paid_date: string | null;
}

export async function listLoanPayments(loanId: string, includeDeleted = false): Promise<PaymentRead[]> {
  const { data } = await apiClient.get(`${BASE}/loans/${loanId}/payments`, {
    params: { include_deleted: includeDeleted },
  });
  return data;
}

export async function createLoanPayment(loanId: string, payload: PaymentCreate): Promise<PaymentRead> {
  const { data } = await apiClient.post(`${BASE}/loans/${loanId}/payments`, payload);
  return data;
}

export async function updatePayment(paymentId: string, payload: PaymentUpdate): Promise<PaymentRead> {
  const { data } = await apiClient.patch(`${BASE}/payments/${paymentId}`, payload);
  return data;
}

export async function deletePayment(paymentId: string): Promise<void> {
  await apiClient.delete(`${BASE}/payments/${paymentId}`);
}

export async function getLoanPaymentsSummary(loanId: string): Promise<LoanPaymentsSummary> {
  const { data } = await apiClient.get(`${BASE}/loans/${loanId}/payments/summary`);
  return data;
}

/* ─────────────────────────── Formatting helpers ─────────────────────────── */

export function fmtMoneyShort(usd: Decimal | null | undefined): string {
  const n = toNum(usd);
  const a = Math.abs(n);
  if (a >= 1e9) return "$" + (n / 1e9).toFixed(2) + "B";
  if (a >= 1e6) return "$" + (n / 1e6).toFixed(0) + "M";
  if (a >= 1e3) return "$" + (n / 1e3).toFixed(0) + "K";
  return "$" + n.toFixed(0);
}
export function fmtMoneyLoan(amount: Decimal | null | undefined, currency: string): string {
  const n = toNum(amount);
  const a = Math.abs(n);
  let body: string;
  if (a >= 1e9) body = `${fmtNumber(n / 1e9, getCurrentLocale(), { decimals: 2 })} ${t("млрд")}`;
  else if (a >= 1e6) body = `${fmtNumber(n / 1e6, getCurrentLocale(), { decimals: 1 })} ${t("млн")}`;
  else if (a >= 1e3) body = `${fmtNumber(n / 1e3, getCurrentLocale(), { decimals: 0 })} ${t("тыс")}`;
  else body = fmtNumber(n, getCurrentLocale(), { decimals: 0 });
  return body + " " + currency;
}
export function fmtPct(v: Decimal | null | undefined, alreadyPct = false): string {
  const n = toNum(v);
  const pct = alreadyPct ? n : n * 100;
  return pct.toFixed(1) + "%";
}
export function fmtRate(rate: Decimal | null | undefined): string {
  const n = toNum(rate);
  return (n * 100).toFixed(2) + "%";
}
export function fmtDate(iso: string | null | undefined): string {
  if (!iso) return "—";
  const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(iso);
  if (!m) return iso;
  return `${m[3]}.${m[2]}.${m[1]}`;
}
export function yearOf(iso: string | null | undefined): number | null {
  if (!iso) return null;
  const m = /^(\d{4})/.exec(iso);
  return m ? parseInt(m[1], 10) : null;
}
