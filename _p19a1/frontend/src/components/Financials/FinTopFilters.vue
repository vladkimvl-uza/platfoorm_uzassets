<script setup lang="ts">
// ============================================================================
// Financials toolbar (top bar) — НСБУ/МСФО · UZS/USD/EUR · млрд/млн ·
// сектор · год · view-tabs.
//
// ============================================================================

import { computed } from "vue";
import {
  STANDARDS, CURRENCIES, UNITS,
  VIEW_TABS_IFRS, VIEW_TABS_NSBU,
} from "./financialsHelpers";
import type { SectorBrief } from "@/api/companies";

const props = defineProps<{
  standard: "IFRS" | "NSBU";
  currency: "UZS" | "USD" | "EUR";
  unit: "bln" | "mln";
  sectorCode: string;
  year: number;
  viewTab: string;
  availableYears: number[];
  sectors: SectorBrief[];
  /** ISO-ish updated date label, e.g. "2026-04-26" */
  asOfDate?: string;
}>();

const emit = defineEmits<{
  (e: "update:standard", v: "IFRS" | "NSBU"): void;
  (e: "update:currency", v: "UZS" | "USD" | "EUR"): void;
  (e: "update:unit", v: "bln" | "mln"): void;
  (e: "update:sectorCode", v: string): void;
  (e: "update:year", v: number): void;
  (e: "update:viewTab", v: string): void;
}>();

const viewTabs = computed(() =>
  props.standard === "IFRS" ? VIEW_TABS_IFRS : VIEW_TABS_NSBU,
);

const sortedSectors = computed(() =>
  [...props.sectors].sort((a, b) => (a.sort_order || 0) - (b.sort_order || 0)),
);

const activeSectorLabel = computed(() => {
  if (!props.sectorCode) return "Все секторы";
  const s = props.sectors.find(x => String(x.code).toLowerCase() === props.sectorCode);
  return s?.name_ru || props.sectorCode;
});

const yearLabel = computed(() => `FY ${props.year}`);
</script>

<template>
  <div class="ft-bar">
    <!-- Title left -->
    <div class="ft-title-block">
      <div class="ft-title">Финансовые показатели</div>
      <div class="ft-std-pills">
        <button v-for="s in STANDARDS"
                :key="s.value"
                class="ft-pill"
                :class="{ on: standard === s.value }"
                @click="emit('update:standard', s.value)">
          {{ s.label }}
        </button>
      </div>
      <div v-if="asOfDate" class="ft-asof">{{ asOfDate }}</div>
    </div>

    <!-- Right cluster -->
    <div class="ft-cluster">
      <!-- Currency -->
      <div class="ft-pill-grp">
        <button v-for="c in CURRENCIES"
                :key="c.value"
                class="ft-pill ft-pill-sm"
                :class="{ on: currency === c.value }"
                @click="emit('update:currency', c.value)">
          {{ c.label }}
        </button>
      </div>

      <!-- Unit -->
      <div class="ft-pill-grp">
        <button v-for="u in UNITS"
                :key="u.value"
                class="ft-pill ft-pill-sm"
                :class="{ on: unit === u.value }"
                @click="emit('update:unit', u.value)">
          {{ u.label }}
        </button>
      </div>

      <!-- Sector dropdown -->
      <div class="ft-dd">
        <select :value="sectorCode"
                class="ft-select"
                @change="emit('update:sectorCode', ($event.target as HTMLSelectElement).value)">
          <option value="">Все секторы</option>
          <option v-for="s in sortedSectors"
                  :key="s.code"
                  :value="String(s.code).toLowerCase()">
            {{ s.name_ru }}
          </option>
        </select>
      </div>

      <div class="ft-dd ft-dd-year">
        <select :value="year"
                class="ft-select ft-select-year"
                @change="emit('update:year', parseInt(($event.target as HTMLSelectElement).value))">
          <option v-for="y in availableYears" :key="y" :value="y">FY {{ y }}</option>
        </select>
      </div>

      <!-- View tabs (P&L / SOFP / CF — or НСБУ Финрезы / Баланс) -->
      <div class="ft-tabs">
        <button v-for="t in viewTabs"
                :key="t.value"
                class="ft-tab"
                :class="{ on: viewTab === t.value }"
                @click="emit('update:viewTab', t.value)">
          {{ t.label }}
        </button>
      </div>
    </div>
  </div>
</template>

<style scoped>
.ft-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  padding: 10px 16px;
  background: linear-gradient(180deg, #1E2A4A 0%, #182039 100%);
  color: #fff;
  border-radius: 12px;
  box-shadow: 0 4px 14px rgba(15, 23, 60, 0.15);
  flex-wrap: wrap;
}

/* Left block: title + standard pills + as-of-date */
.ft-title-block {
  display: flex;
  align-items: center;
  gap: 14px;
  min-width: 0;
}
.ft-title {
  font-size: 15px;
  font-weight: 600;
  color: #fff;
  letter-spacing: -0.005em;
  white-space: nowrap;
}
.ft-std-pills {
  display: inline-flex;
  background: rgba(255, 255, 255, 0.06);
  border: 1px solid rgba(255, 255, 255, 0.10);
  border-radius: 9px;
  padding: 2px;
  gap: 0;
}
.ft-pill {
  background: transparent;
  border: none;
  color: rgba(255, 255, 255, 0.65);
  padding: 5px 12px;
  font-size: 11px;
  font-weight: 600;
  letter-spacing: 0.04em;
  cursor: pointer;
  border-radius: 7px;
  transition: all 0.15s;
  font-family: inherit;
}
.ft-pill:hover {
  color: #fff;
  background: rgba(255, 255, 255, 0.05);
}
.ft-pill.on {
  background: rgba(127, 119, 221, 0.85);
  color: #fff;
  box-shadow: 0 2px 6px rgba(127, 119, 221, 0.25);
}
.ft-asof {
  font-size: 11px;
  color: rgba(255, 255, 255, 0.45);
  letter-spacing: 0.04em;
  font-variant-numeric: tabular-nums;
}

/* Right cluster */
.ft-cluster {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}
.ft-pill-grp {
  display: inline-flex;
  background: rgba(255, 255, 255, 0.06);
  border: 1px solid rgba(255, 255, 255, 0.10);
  border-radius: 8px;
  padding: 1px;
}
.ft-pill-sm {
  padding: 4px 10px;
  font-size: 10.5px;
  border-radius: 6px;
}

/* Selects */
.ft-dd { position: relative; }
.ft-select {
  background: rgba(255, 255, 255, 0.07);
  border: 1px solid rgba(255, 255, 255, 0.12);
  color: #fff;
  padding: 5px 26px 5px 12px;
  border-radius: 8px;
  font-size: 11.5px;
  font-weight: 500;
  cursor: pointer;
  appearance: none;
  background-image: url("data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 12 12'><path fill='rgba(255,255,255,0.55)' d='M6 8.5L2 4.5h8z'/></svg>");
  background-repeat: no-repeat;
  background-position: right 8px center;
  background-size: 10px;
  font-family: inherit;
  transition: background 0.12s, border-color 0.12s;
}
.ft-select:hover {
  background-color: rgba(255, 255, 255, 0.10);
  border-color: rgba(255, 255, 255, 0.18);
}
.ft-select option {
  background: #1E2A4A;
  color: #fff;
}
.ft-dd-year .ft-select-year {
  border-color: rgba(239, 159, 39, 0.35);
  color: #FAC775;
  background-color: rgba(239, 159, 39, 0.08);
}
.ft-dd-year .ft-select-year:hover {
  background-color: rgba(239, 159, 39, 0.14);
  border-color: rgba(239, 159, 39, 0.5);
}

/* View tabs (top-right pill group) */
.ft-tabs {
  display: inline-flex;
  background: rgba(255, 255, 255, 0.97);
  border-radius: 9px;
  padding: 2px;
  box-shadow: 0 2px 6px rgba(0, 0, 0, 0.12);
}
.ft-tab {
  background: transparent;
  border: none;
  color: rgba(30, 42, 74, 0.65);
  padding: 5px 14px;
  font-size: 11px;
  font-weight: 600;
  cursor: pointer;
  border-radius: 7px;
  transition: all 0.15s;
  font-family: inherit;
  letter-spacing: 0.02em;
}
.ft-tab:hover { color: #1E2A4A; background: rgba(127, 119, 221, 0.08); }
.ft-tab.on {
  background: #fff;
  color: #1E2A4A;
  box-shadow: 0 2px 6px rgba(15, 23, 60, 0.08);
}
</style>
