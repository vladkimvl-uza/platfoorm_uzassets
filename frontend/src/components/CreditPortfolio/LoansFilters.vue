<script setup lang="ts">
/**
 * LoansFilters v2 (19c-8) — добавлены action buttons:
 *   + Новый кредит  → openLoanEditor()
 *   ↑ Импорт Excel  → openExcelImport()
 *
 * Остальное 1:1 с 19c-7: chips активных фильтров + status pills + counter.
 */
import { computed } from "vue";
import { useCreditData } from "@/composables/useCreditData";

const credit = useCreditData();

const totalCount = computed(() => credit.loans.value.length);
const filteredCount = computed(() => credit.filteredLoans.value.length);

const selectedCompanyName = computed(() => {
  if (!credit.selectedCompanyMeta.value) return null;
  return credit.selectedCompanyMeta.value.company_name_ru;
});

function setStatus(s: "overdue" | "active" | "all") { credit.filterStatus.value = s; }
function onCreateLoan() { credit.openLoanEditor(); }
function onImportExcel() { credit.openExcelImport(); }
</script>

<template>
  <div class="cp-lf-bar">
    <div class="cp-lf-chips">
      <!-- Status pills group -->
      <div class="cp-lf-status-grp">
        <button
          type="button"
          class="cp-lf-status"
          :class="{ active: credit.filterStatus.value === 'all' }"
          @click="setStatus('all')"
        >Все</button>
        <button
          type="button"
          class="cp-lf-status"
          :class="{ active: credit.filterStatus.value === 'active' }"
          @click="setStatus('active')"
        >Активные</button>
        <button
          type="button"
          class="cp-lf-status cp-lf-status-overdue"
          :class="{ active: credit.filterStatus.value === 'overdue' }"
          @click="setStatus('overdue')"
        >Просроченные</button>
      </div>

      <!-- Company chip (read-only) -->
      <div v-if="selectedCompanyName" class="cp-lf-chip cp-lf-chip-co">
        <span class="cp-lf-chip-lbl">Компания:</span>
        <span class="cp-lf-chip-val">{{ selectedCompanyName }}</span>
      </div>

      <!-- Bank chip -->
      <div v-if="credit.filterBank.value" class="cp-lf-chip">
        <span class="cp-lf-chip-lbl">Банк:</span>
        <span class="cp-lf-chip-val">{{ credit.filterBank.value }}</span>
        <button type="button" class="cp-lf-chip-x" title="Убрать" @click="credit.filterBank.value = null">×</button>
      </div>

      <!-- Currency chip -->
      <div v-if="credit.filterCurrency.value" class="cp-lf-chip">
        <span class="cp-lf-chip-lbl">Валюта:</span>
        <span class="cp-lf-chip-val">{{ credit.filterCurrency.value }}</span>
        <button type="button" class="cp-lf-chip-x" title="Убрать" @click="credit.filterCurrency.value = null">×</button>
      </div>

      <!-- Year chip -->
      <div v-if="credit.filterYear.value !== null" class="cp-lf-chip">
        <span class="cp-lf-chip-lbl">Год:</span>
        <span class="cp-lf-chip-val">{{ credit.filterYear.value }}</span>
        <button type="button" class="cp-lf-chip-x" title="Убрать" @click="credit.filterYear.value = null">×</button>
      </div>

      <button
        v-if="credit.isAnyFilterActive.value"
        type="button"
        class="cp-lf-clear"
        @click="credit.clearFilters()"
      >Сбросить все</button>
    </div>

    <!-- Action buttons -->
    <div class="cp-lf-actions">
      <button class="cp-lf-btn cp-lf-btn-import" @click="onImportExcel" title="Загрузить кредиты из XLSX">
        <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/>
          <polyline points="17 8 12 3 7 8"/>
          <line x1="12" y1="3" x2="12" y2="15"/>
        </svg>
        Импорт Excel
      </button>
      <button class="cp-lf-btn cp-lf-btn-new" @click="onCreateLoan" title="Создать кредит">
        <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round">
          <line x1="12" y1="5" x2="12" y2="19"/>
          <line x1="5" y1="12" x2="19" y2="12"/>
        </svg>
        Новый кредит
      </button>
    </div>

    <div class="cp-lf-count">
      <span class="cp-lf-count-num">{{ filteredCount }}</span>
      из {{ totalCount }} кредитов
    </div>
  </div>
</template>

<style scoped>
.cp-lf-bar {
  display: flex;
  align-items: center;
  gap: 14px;
  padding: 12px 16px;
  background: rgba(255, 255, 255, 0.96);
  border: 1px solid rgba(30, 42, 74, 0.06);
  border-radius: 12px;
  margin-bottom: 12px;
  box-shadow: 0 4px 12px rgba(15, 23, 60, 0.04);
  flex-wrap: wrap;
}

.cp-lf-chips {
  display: flex;
  align-items: center;
  gap: 8px;
  flex: 1;
  min-width: 0;
  flex-wrap: wrap;
}

.cp-lf-chip {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 5px 8px 5px 10px;
  background: rgba(127, 119, 221, 0.08);
  border: 1px solid rgba(127, 119, 221, 0.18);
  border-radius: 8px;
  font-size: 11px;
  font-weight: 500;
  animation: cpLfChipIn 0.3s cubic-bezier(0.34, 1.2, 0.64, 1) both;
}
.cp-lf-chip-co {
  background: rgba(250, 199, 117, 0.12);
  border-color: rgba(250, 199, 117, 0.3);
}
@keyframes cpLfChipIn {
  from { opacity: 0; transform: scale(0.92); }
  to   { opacity: 1; transform: scale(1); }
}

.cp-lf-chip-lbl {
  color: var(--t3, #888780);
  font-size: 10px;
  text-transform: uppercase;
  letter-spacing: 0.04em;
}
.cp-lf-chip-val {
  color: var(--t1, #1e2a4a);
  font-weight: 600;
  letter-spacing: -0.005em;
}
.cp-lf-chip-x {
  background: transparent;
  border: none;
  color: var(--t3, #888780);
  font-size: 16px;
  font-weight: 400;
  line-height: 1;
  cursor: pointer;
  padding: 0 2px;
  border-radius: 4px;
  transition: color 0.14s, background 0.14s;
}
.cp-lf-chip-x:hover {
  color: #C97070;
  background: rgba(201, 112, 112, 0.1);
}

.cp-lf-status-grp {
  display: flex;
  background: rgba(127, 119, 221, 0.06);
  border-radius: 7px;
  padding: 2px;
  gap: 1px;
}
.cp-lf-status {
  padding: 5px 11px;
  background: transparent;
  border: none;
  border-radius: 5px;
  font-family: inherit;
  font-size: 11px;
  font-weight: 500;
  color: var(--t2, #555c6e);
  cursor: pointer;
  transition: background 0.14s, color 0.14s;
  letter-spacing: -0.005em;
}
.cp-lf-status:hover { color: var(--t1, #1e2a4a); }
.cp-lf-status.active {
  background: rgba(255, 255, 255, 0.96);
  color: #7F77DD;
  font-weight: 600;
  box-shadow: 0 1px 3px rgba(15, 23, 60, 0.08);
}
.cp-lf-status-overdue.active { color: #C97070; }

.cp-lf-clear {
  padding: 6px 12px;
  background: rgba(201, 112, 112, 0.08);
  border: 1px solid rgba(201, 112, 112, 0.25);
  border-radius: 7px;
  color: #C97070;
  font-family: inherit;
  font-size: 11px;
  font-weight: 500;
  cursor: pointer;
  transition: background 0.14s;
}
.cp-lf-clear:hover { background: rgba(201, 112, 112, 0.16); }

/* Action buttons (NEW for 19c-8) */
.cp-lf-actions {
  display: flex;
  gap: 6px;
  align-items: center;
}

.cp-lf-btn {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  padding: 6px 11px;
  border-radius: 7px;
  font-family: inherit;
  font-size: 11px;
  font-weight: 600;
  cursor: pointer;
  transition: background 0.14s, transform 0.16s;
  letter-spacing: -0.005em;
  border: none;
}
.cp-lf-btn:hover { transform: translateY(-1px); }

.cp-lf-btn-import {
  background: rgba(127, 119, 221, 0.10);
  color: #534AB7;
  border: 1px solid rgba(127, 119, 221, 0.22);
}
.cp-lf-btn-import:hover { background: rgba(127, 119, 221, 0.18); }

.cp-lf-btn-new {
  background: #7F77DD;
  color: #fff;
}
.cp-lf-btn-new:hover { background: #534AB7; }

.cp-lf-count {
  font-size: 11px;
  color: var(--t3, #888780);
  font-weight: 500;
  letter-spacing: 0.02em;
  text-transform: uppercase;
  white-space: nowrap;
}
.cp-lf-count-num {
  color: var(--t1, #1e2a4a);
  font-weight: 600;
  font-feature-settings: "tnum";
  font-size: 13px;
  margin-right: 3px;
}
</style>
