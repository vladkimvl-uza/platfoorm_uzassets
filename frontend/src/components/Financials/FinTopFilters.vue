<script setup lang="ts">
// ============================================================================
// without the "Финансовые показатели" title and date (those live in the
// global app header). Only contextual filter controls.
// ============================================================================

import { computed, inject } from "vue";
import {
  STANDARDS, CURRENCIES, UNITS,
  VIEW_TABS_IFRS, VIEW_TABS_NSBU,
} from "./financialsHelpers";
import type { SectorBrief } from "@/api/companies";
import { useCurrencyConverter } from "@/composables/useCurrencyConverter";

// Pack 7.58.5: sidebar toggle injected from AppShell — burger renders inside topbar
const toggleSidebar = inject<() => void>("toggleSidebar", () => {});

const props = defineProps<{
  standard: "IFRS" | "NSBU";
  currency: "UZS" | "USD" | "EUR";
  unit: "bln" | "mln";
  sectorCode: string;
  year: number;
  viewTab: string;
  availableYears: number[];
  sectors: SectorBrief[];
  /** Pack 7.50: page header rendered on the LEFT side of the topbar */
  pageEyebrow?: string;
  pageTitle?: string;
  pageSubtitle?: string;
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

// Pack 7.49: rate tooltips on currency buttons.
// EUR показывает меньше USD потому что EUR стоит больше — за 1 EUR дают
// больше сум (~13 691), чем за 1 USD (~12 651). На ту же сумму в UZS
// получается меньше EUR, чем USD. Это математически корректно.
const conv = useCurrencyConverter();
function currencyTooltip(c: "UZS" | "USD" | "EUR"): string {
  if (c === "UZS") return "Узбекский сум · базовая валюта отчётности";
  const rate = c === "EUR" ? conv.getEurRate(props.year) : conv.getUsdRate(props.year);
  const fmt = Math.round(rate).toLocaleString("ru-RU").replace(/\u00A0/g, " ");
  return `${fmt} сум за 1 ${c} (средневзв. курс ЦБ РУ за ${props.year} год)`;
}
</script>

<template>
  <div class="ft-bar">
    <!-- Pack 7.58.5: sidebar toggle — lives inside the page topbar -->
    <button class="ft-burger" @click="toggleSidebar()" title="Скрыть сайдбар">
      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round">
        <line x1="3" y1="6" x2="21" y2="6"/>
        <line x1="3" y1="12" x2="21" y2="12"/>
        <line x1="3" y1="18" x2="21" y2="18"/>
      </svg>
    </button>

    <!-- Pack 7.50.1: header always rendered — no v-if. Fallback values if props missing. -->
    <div class="ft-head" data-pack="p750.1">
        <div class="ft-head-eyebrow">{{ pageEyebrow || 'РАЗДЕЛ ПОРТФЕЛЯ' }}</div>
        <div class="ft-head-title-row">
          <span class="ft-head-title">{{ pageTitle || 'Финансовые показатели' }}</span>
          <span class="ft-head-sub">
            <slot name="subtitle"></slot>
          </span>
        </div>
      </div>

    <!-- ALL switchers on the RIGHT cluster -->
    <div class="ft-cluster">
      <!-- Standard pills (НСБУ / МСФО) -->
      <div class="ft-pill-grp">
        <button v-for="s in STANDARDS"
                :key="s.value"
                class="ft-pill ft-pill-sm"
                :class="{ on: standard === s.value }"
                @click="emit('update:standard', s.value)">
          {{ s.label }}
        </button>
      </div>

      <div class="ft-div" aria-hidden="true"></div>

      <!-- Currency -->
      <div class="ft-pill-grp">
        <button v-for="c in CURRENCIES"
                :key="c.value"
                class="ft-pill ft-pill-sm"
                :class="{ on: currency === c.value }"
                :title="currencyTooltip(c.value)"
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

      <div class="ft-div" aria-hidden="true"></div>

      <!-- Sector dropdown -->
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

      <!-- Year (gold accent) -->
      <select :value="year"
              class="ft-select ft-select-year"
              @change="emit('update:year', parseInt(($event.target as HTMLSelectElement).value))">
        <option v-for="y in availableYears" :key="y" :value="y">FY {{ y }}</option>
      </select>

      <div class="ft-div" aria-hidden="true"></div>

      <!-- View tabs (P&L / SOFP / Cash Flow) -->
      <div class="ft-tabs">
        <button v-for="t in viewTabs"
                :key="t.value"
                class="ft-tab"
                :class="{ on: viewTab === t.value }"
                @click="emit('update:viewTab', t.value)">
          {{ t.label }}
        </button>
      </div>

      <!-- Pack 7.58: action menu slot — used for page-level actions (Редактировать НСБУ и др.) -->
      <slot name="actions" />
    </div>
  </div>
</template>

<style scoped>
.ft-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 18px;
  padding: 8px 18px;
  background: linear-gradient(180deg, #1E2A4A 0%, #182039 100%);
  color: #fff;
  border-radius: 12px;
  box-shadow: 0 4px 14px rgba(15, 23, 60, 0.15);
  flex-wrap: nowrap;
  min-height: 52px;
}

/* Pack 7.58.5: sidebar toggle inside topbar */
.ft-burger {
  width: 34px;
  height: 34px;
  border-radius: 8px;
  border: 1px solid rgba(255, 255, 255, 0.12);
  background: rgba(255, 255, 255, 0.08);
  color: rgba(255, 255, 255, 0.85);
  cursor: pointer;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  transition: background 0.15s ease, border-color 0.15s ease, transform 0.16s ease;
}
.ft-burger:hover {
  background: rgba(255, 255, 255, 0.14);
  border-color: rgba(255, 255, 255, 0.22);
  color: #fff;
}
.ft-burger:active { transform: scale(0.94); }

/* Pack 7.50: page header on the LEFT of the topbar (light text on dark bg) */
.ft-head {
  flex: 1 1 auto;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 1px;
  overflow: hidden;
}
.ft-head-title-row {
  display: flex;
  align-items: baseline;
  gap: 10px;
  min-width: 0;
}
.ft-head-eyebrow {
  font-size: 10px;
  font-weight: 500;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: rgba(255, 255, 255, 0.55);
}
.ft-head-title {
  font-size: 19px;
  font-weight: 500;
  letter-spacing: -0.01em;
  color: #fff;
  line-height: 1.15;
}
.ft-head-sub {
  font-size: 12px;
  color: rgba(255, 255, 255, 0.65);
  line-height: 1.45;
}
.ft-head-sub :deep(strong) {
  color: #fff;
  font-weight: 500;
}

/* Pack 7.49: vertical divider between groups inside the cluster */
.ft-div {
  width: 1px;
  height: 20px;
  background: rgba(255, 255, 255, 0.12);
  margin: 0 2px;
  flex-shrink: 0;
}

/* Standard pills (deprecated — kept for legacy classes if any) */
.ft-std-pills {
  display: inline-flex;
  background: rgba(255, 255, 255, 0.06);
  border: 1px solid rgba(255, 255, 255, 0.10);
  border-radius: 9px;
  padding: 2px;
}
.ft-pill {
  padding: 4px 10px;
  font-size: 11px;
  font-weight: 500;
  border-radius: 7px;
  background: rgba(255, 255, 255, 0.06);
  color: rgba(255, 255, 255, 0.7);
  border: 1px solid rgba(255, 255, 255, 0.08);
  cursor: pointer;
  transition: background 0.14s ease, color 0.14s ease;
  white-space: nowrap;
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

/* Right cluster */
.ft-cluster {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: nowrap;
  flex-shrink: 0;
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

/* Selects (dark theme) */
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

.ft-select-year {
  border-color: rgba(239, 159, 39, 0.35);
  color: #FAC775;
  background-color: rgba(239, 159, 39, 0.08);
  font-weight: 600;
}
.ft-select-year:hover {
  background-color: rgba(239, 159, 39, 0.14);
  border-color: rgba(239, 159, 39, 0.5);
}

/* View tabs (white pill group on right) */
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
.ft-tab:hover {
  color: #1E2A4A;
  background: rgba(127, 119, 221, 0.08);
}
.ft-tab.on {
  background: #fff;
  color: #1E2A4A;
  box-shadow: 0 2px 6px rgba(15, 23, 60, 0.08);
}
</style>
