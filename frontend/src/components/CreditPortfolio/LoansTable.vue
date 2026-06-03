<script setup lang="ts">
/**
 * LoansTable — sortable таблица всех (отфильтрованных) кредитов.
 *
 * Источник: useCreditData.filteredLoans.
 * Sort через credit.setSort + credit.sortKey/sortDir.
 *
 * Click row → openLoanDetail(loanId) — открыть LoanDetailModal.
 *
 * Колонки:
 *   # | Код | Компания | Банк | Контракт | Валюта | Ставка | Долг USD | Срок
 */
import { useCreditData } from "@/composables/useCreditData";
import {
  CP_LENDER_LABELS,
  cpCurrencyColor,
  fmtDate,
  fmtMoneyShort,
  toNum,
  type LoanRead,
} from "@/api/credit";
import type { SortKey } from "@/composables/useCreditData";
import { useFormatters } from "@/composables/useFormatters";
const fmt = useFormatters();

const credit = useCreditData();

interface ColDef {
  key: SortKey | null;
  label: string;
  align?: "left" | "right" | "center";
}

const columns: ColDef[] = [
  { key: null, label: "#", align: "center" },
  { key: null, label: "Код", align: "left" },
  { key: "company", label: "Компания", align: "left" },
  { key: "bank", label: "Банк", align: "left" },
  { key: null, label: "Контракт", align: "left" },
  { key: "currency", label: "Валюта", align: "center" },
  { key: "rate", label: "Ставка", align: "right" },
  { key: "debt_usd", label: "Долг USD", align: "right" },
  { key: "date_due", label: "Срок", align: "right" },
];

function clickHeader(c: ColDef) {
  if (c.key) credit.setSort(c.key);
}

function sortIcon(key: SortKey | null): "asc" | "desc" | null {
  if (!key) return null;
  if (credit.sortKey.value !== key) return null;
  return credit.sortDir.value;
}

function shortenCo(name: string | null | undefined): string {
  if (!name) return "—";
  return name
    .replace(/^АО\s*"?/, "")
    .replace(/^"/, "")
    .replace(/"$/, "")
    .replace(/\s*ДК$/, "")
    .replace(/\s*АЖ$/, " АЖ");
}

function rateLabel(l: LoanRead): string {
  const r = toNum(l.rate);
  if (r <= 0 || r >= 1) return "—";
  return fmt.fmtPercent(r * 100, { decimals: 2 });
}

function isOverdue(l: LoanRead): boolean {
  return l.date_due !== null && l.date_due! < credit.asOfDate.value;
}

function rowClick(l: LoanRead) {
  credit.openLoanDetail(l.id);
}
</script>

<template>
  <div class="pa-card cp-lt-card">
    <div class="cp-lt-wrap">
      <table class="cp-lt-table">
        <thead>
          <tr>
            <th
              v-for="(c, i) in columns"
              :key="i"
              :class="[
                c.align === 'right' ? 'right' : c.align === 'center' ? 'center' : 'left',
                c.key ? 'sortable' : '',
                c.key && credit.sortKey.value === c.key ? 'active' : '',
              ]"
              @click="clickHeader(c)"
            >
              {{ c.label }}
              <svg
                v-if="sortIcon(c.key) === 'desc'"
                class="cp-lt-arrow"
                viewBox="0 0 24 24"
              ><polyline points="6 9 12 15 18 9"/></svg>
              <svg
                v-else-if="sortIcon(c.key) === 'asc'"
                class="cp-lt-arrow"
                viewBox="0 0 24 24"
              ><polyline points="6 15 12 9 18 15"/></svg>
            </th>
          </tr>
        </thead>
        <tbody>
          <tr
            v-for="(l, i) in credit.filteredLoans.value"
            :key="l.id"
            :class="{ overdue: isOverdue(l) }"
            @click="rowClick(l)"
          >
            <td class="center cp-lt-rank">{{ i + 1 }}</td>
            <td class="left cp-lt-code">{{ l.loan_code }}</td>
            <td class="left">
              <div class="cp-lt-co" :title="l.company_name_ru || ''">
                {{ shortenCo(l.company_name_ru) }}
              </div>
              <div v-if="l.borrower_unit" class="cp-lt-co-sub">{{ l.borrower_unit }}</div>
            </td>
            <td class="left">
              <div class="cp-lt-bank">{{ l.bank_short_name || l.bank }}</div>
              <div v-if="l.lender_type" class="cp-lt-bank-type">
                <span
                  class="cp-lt-pill"
                  :style="{
                    background: (CP_LENDER_LABELS[l.lender_type]?.color || '#888780') + '22',
                    color: CP_LENDER_LABELS[l.lender_type]?.color || '#888780',
                  }"
                >{{ CP_LENDER_LABELS[l.lender_type]?.label || l.lender_type }}</span>
              </div>
            </td>
            <td class="left cp-lt-contract" :title="l.contract_ref || ''">
              {{ l.contract_ref || "—" }}
            </td>
            <td class="center">
              <span
                class="cp-lt-cur"
                :style="{ background: cpCurrencyColor(l.currency) + '22', color: cpCurrencyColor(l.currency) }"
              >{{ l.currency }}</span>
            </td>
            <td class="right cp-lt-rate">{{ rateLabel(l) }}</td>
            <td class="right cp-lt-debt">{{ fmtMoneyShort(l.debt_usd) }}</td>
            <td class="right cp-lt-due">{{ fmtDate(l.date_due) }}</td>
          </tr>

          <tr v-if="!credit.filteredLoans.value.length">
            <td :colspan="columns.length" class="cp-lt-empty">
              Нет кредитов под текущие фильтры
            </td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</template>

<style scoped>
.cp-lt-card {
  overflow: hidden;
}

.cp-lt-wrap {
  max-height: calc(100vh - 280px);
  overflow-y: auto;
  overflow-x: auto;
}

.cp-lt-table {
  width: 100%;
  border-collapse: separate;
  border-spacing: 0;
  font-size: 12px;
}

.cp-lt-table thead {
  position: sticky;
  top: 0;
  z-index: 5;
  background: var(--bg1, #fff);
  box-shadow: 0 1px 0 rgba(0, 0, 0, 0.06);
}

.cp-lt-table th {
  font-size: 9.5px;
  font-weight: 500;
  color: var(--t3, var(--t-muted));
  text-transform: uppercase;
  letter-spacing: 0.06em;
  padding: 12px 10px;
  user-select: none;
  white-space: nowrap;
  border-bottom: 1px solid rgba(0, 0, 0, 0.06);
}

.cp-lt-table th.sortable {
  cursor: pointer;
  transition: color 0.12s;
}

.cp-lt-table th.sortable:hover { color: var(--t2, #555c6e); }

.cp-lt-table th.active { color: #7F77DD; }

.cp-lt-table th.left { text-align: left; }
.cp-lt-table th.right { text-align: right; }
.cp-lt-table th.center { text-align: center; }

.cp-lt-arrow {
  width: 9px;
  height: 9px;
  fill: none;
  stroke: currentColor;
  stroke-width: 3;
  margin-left: 3px;
  vertical-align: middle;
}

.cp-lt-table tbody tr {
  cursor: pointer;
  transition: background 0.12s;
}

.cp-lt-table tbody tr:hover {
  background: rgba(127, 119, 221, 0.04);
}

.cp-lt-table tbody tr.overdue {
  background: rgba(226, 75, 74, 0.04);
}

.cp-lt-table tbody tr.overdue:hover {
  background: rgba(226, 75, 74, 0.10);
}

.cp-lt-table td {
  padding: 9px 10px;
  border-bottom: 1px solid rgba(0, 0, 0, 0.04);
  vertical-align: middle;
}

.cp-lt-table td.left { text-align: left; }
.cp-lt-table td.right { text-align: right; font-feature-settings: "tnum"; font-variant-numeric: tabular-nums; }
.cp-lt-table td.center { text-align: center; }

.cp-lt-rank {
  font-size: 10.5px;
  color: var(--t3, var(--t-muted));
  font-weight: 500;
}

.cp-lt-code {
  font-size: 10.5px;
  font-weight: 600;
  color: var(--t2, #555c6e);
  font-family: monospace;
  font-feature-settings: "tnum";
  white-space: nowrap;
}

.cp-lt-co {
  font-size: 12px;
  font-weight: 500;
  color: var(--t1, #1e2a4a);
  letter-spacing: -0.005em;
  max-width: 200px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.cp-lt-co-sub {
  font-size: 9.5px;
  color: var(--t3, var(--t-muted));
  margin-top: 1px;
}

.cp-lt-bank {
  font-size: 11.5px;
  font-weight: 500;
  color: var(--t1, #1e2a4a);
  letter-spacing: -0.005em;
  white-space: nowrap;
  max-width: 180px;
  overflow: hidden;
  text-overflow: ellipsis;
}

.cp-lt-bank-type {
  margin-top: 2px;
}

.cp-lt-pill {
  font-size: 9px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.04em;
  padding: 2px 6px;
  border-radius: 6px;
  white-space: nowrap;
}

.cp-lt-contract {
  font-size: 10.5px;
  color: var(--t2, #555c6e);
  max-width: 180px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.cp-lt-cur {
  display: inline-block;
  font-size: 10px;
  font-weight: 600;
  letter-spacing: 0.04em;
  padding: 3px 8px;
  border-radius: 6px;
}

.cp-lt-rate {
  font-size: 11.5px;
  font-weight: 500;
  color: var(--t1, #1e2a4a);
}

.cp-lt-debt {
  font-size: 12px;
  font-weight: 600;
  color: var(--t1, #1e2a4a);
  letter-spacing: -0.005em;
}

.cp-lt-due {
  font-size: 11px;
  color: var(--t2, #555c6e);
  white-space: nowrap;
}

.cp-lt-empty {
  text-align: center;
  padding: 40px 20px;
  color: var(--t3, var(--t-muted));
  font-style: italic;
  font-size: 12px;
}
</style>
