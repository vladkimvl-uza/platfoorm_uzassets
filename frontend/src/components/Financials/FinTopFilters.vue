<script setup lang="ts">
// ============================================================================
// Financials toolbar — 1:1 legacy dark style (gradient #1E2A4A → #182039),
// without the "Финансовые показатели" title and date (those live in the
// global app header). Only contextual filter controls.
// ============================================================================

import { computed, inject, ref } from "vue";
import {
  STANDARDS, CURRENCIES, UNITS,
  VIEW_TABS_IFRS, VIEW_TABS_NSBU,
} from "./financialsHelpers";
import type { SectorBrief } from "@/api/companies";
import { useCurrencyConverter } from "@/composables/useCurrencyConverter";
import { useFormatters } from "@/composables/useFormatters";
import UzaYearStepper from "@/components/UZA/UzaYearStepper.vue";
import { useI18n } from "@/composables/useI18n";
import { useCompanyScope } from "@/composables/useCompanyScope";
const fmt = useFormatters();
const { t } = useI18n();
// Область доступа: селектор секторов не нужен пользователю, ограниченному
// одной компанией (и разделитель перед ним тоже).
const scope = useCompanyScope();

// Pack 7.58.5: sidebar toggle injected from AppShell — burger renders inside topbar
const toggleSidebar = inject<() => void>("toggleSidebar", () => {});
const openMobileSidebar = inject<() => void>("openMobileSidebar", () => {});
// На планшете/телефоне (≤1023) сайдбар = drawer → бургер открывает его;
// на десктопе — сворачивает рейку.
function onBurger() {
  if (typeof window !== "undefined" && window.innerWidth <= 1023) openMobileSidebar();
  else toggleSidebar();
}

// «Вид»-поповер (стандарт/валюта/единицы)
const viewMenuOpen = ref(false);

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
  if (c === "UZS") return t("Узбекский сум · базовая валюта отчётности");
  const rate = c === "EUR" ? conv.getEurRate(props.year) : conv.getUsdRate(props.year);
  const rateStr = fmt.fmtNumber(Math.round(rate));
  return t("{rate} сум за 1 {c} (средневзв. курс ЦБ РУ за {y} год)", { rate: rateStr, c, y: props.year });
}
</script>

<template>
  <div class="ft-bar">
    <!-- Pack 7.58.5: sidebar toggle — lives inside the page topbar -->
    <button class="ft-burger" @click="onBurger()" :title="t('Меню / свернуть сайдбар')">
      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round">
        <line x1="3" y1="6" x2="21" y2="6"/>
        <line x1="3" y1="12" x2="21" y2="12"/>
        <line x1="3" y1="18" x2="21" y2="18"/>
      </svg>
    </button>

    <!-- Pack 7.50.1: header always rendered — no v-if. Fallback values if props missing. -->
    <div class="ft-head" data-pack="p750.1">
        <div class="ft-head-eyebrow">{{ t(pageEyebrow || 'РАЗДЕЛ ПОРТФЕЛЯ') }}</div>
        <div class="ft-head-title-row">
          <span class="ft-head-title">{{ t(pageTitle || 'Финансовые показатели') }}</span>
          <span class="ft-head-sub">
            <slot name="subtitle"></slot>
          </span>
        </div>
      </div>

    <!-- ALL switchers on the RIGHT cluster -->
    <div class="ft-cluster">
      <!-- Стандарт МСФО/НСБУ — первоклассный тумблер (важнейший, вызывает перезагрузку данных) -->
      <div class="ft-tabs uza-seg on-dark ft-std-seg" :title="t('Стандарт отчётности')">
        <button v-for="s in STANDARDS" :key="s.value"
                class="ft-tab uza-seg-btn"
                :class="{ on: standard === s.value }"
                @click="emit('update:standard', s.value)">{{ t(s.label) }}</button>
      </div>

      <!-- «Вид»: валюта + единицы собраны в поповер -->
      <div class="ft-view-wrap">
        <button class="ft-view-btn" :class="{ on: viewMenuOpen }" @click.stop="viewMenuOpen = !viewMenuOpen" :title="t('Валюта · единицы')">
          <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="3"/><path d="M12 2v3M12 19v3M2 12h3M19 12h3"/></svg>
          <span>{{ t("Вид") }}</span>
          <span class="ft-view-cur">{{ currency }} · {{ t(unit === 'bln' ? 'млрд' : 'млн') }}</span>
        </button>
        <div v-if="viewMenuOpen" class="ft-view-bg" @click="viewMenuOpen = false"></div>
        <div v-if="viewMenuOpen" class="ft-view-pop" @click.stop>
          <div class="ft-view-row">
            <span class="ft-view-lbl">{{ t("Валюта") }}</span>
            <div class="ft-pill-grp">
              <button v-for="c in CURRENCIES" :key="c.value" class="ft-pill ft-pill-sm" :class="{ on: currency === c.value }" :title="currencyTooltip(c.value)" @click="emit('update:currency', c.value)">{{ c.label }}</button>
            </div>
          </div>
          <div class="ft-view-row">
            <span class="ft-view-lbl">{{ t("Единицы") }}</span>
            <div class="ft-pill-grp">
              <button v-for="u in UNITS" :key="u.value" class="ft-pill ft-pill-sm" :class="{ on: unit === u.value }" @click="emit('update:unit', u.value)">{{ t(u.label) }}</button>
            </div>
          </div>
        </div>
      </div>

      <div v-if="scope.showSectorPicker.value" class="ft-div" aria-hidden="true"></div>

      <!-- Sector dropdown -->
      <select v-if="scope.showSectorPicker.value"
              :value="sectorCode"
              class="ft-select"
              @change="emit('update:sectorCode', ($event.target as HTMLSelectElement).value)">
        <option value="">{{ t("Все секторы") }}</option>
        <option v-for="s in sortedSectors"
                :key="s.code"
                :value="String(s.code).toLowerCase()">
          {{ s.name_ru }}
        </option>
      </select>

      <!-- Year — единый степпер «FY 2024» (UzaYearStepper, как в BP/KPI) -->
      <UzaYearStepper tone="dark" prefix="FY " :years="availableYears"
                      :model-value="year" @update:model-value="(v) => emit('update:year', v)" />

      <div class="ft-div" aria-hidden="true"></div>

      <!-- View tabs (P&L / SOFP / Cash Flow) -->
      <div class="ft-tabs uza-seg on-dark">
        <button v-for="vt in viewTabs"
                :key="vt.value"
                class="ft-tab uza-seg-btn"
                :class="{ on: viewTab === vt.value }"
                @click="emit('update:viewTab', vt.value)">
          {{ t(vt.label) }}
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
  gap: 14px;
  padding: 10px 16px;
  background: linear-gradient(180deg, #1E2A4A 0%, #182039 100%);
  color: #fff;
  border-radius: 12px;
  box-shadow: 0 4px 14px rgba(15, 23, 60, 0.15);
  /* Two-row layout: header (burger+title) on row 1, filter cluster on row 2
     when the page is too narrow for both. Avoids title clipping when the
     sidebar is fully expanded. */
  flex-wrap: wrap;
  min-height: 52px;
  row-gap: 10px;
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

/* Pack 7.50: page header on the LEFT of the topbar (light text on dark bg).
   `flex-basis: 280px` lets the head stay reasonably wide even when the bar
   wraps to two rows — title + eyebrow stay readable, cluster drops below. */
.ft-head {
  flex: 1 1 280px;
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
  flex-wrap: wrap;
  row-gap: 2px;
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
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  flex: 0 1 auto;
  min-width: 0;
}
.ft-head-sub {
  font-size: 12px;
  color: rgba(255, 255, 255, 0.65);
  line-height: 1.45;
  flex: 1 1 100%;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
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

/* Right cluster — wraps to row 2 when the head can't fit alongside. Inside the
   cluster pills/selects can also wrap to several lines on very narrow screens. */
.ft-cluster {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
  row-gap: 6px;
  flex: 0 1 auto;
  min-width: 0;
  margin-left: auto;
}
/* 13–14" (≤1440): кластер уходит во 2-й ряд ЦЕЛЫМ, а не рвётся по пилюле. */
@media (max-width: 1440px) {
  .ft-cluster {
    flex: 1 1 100%;
    margin-left: 0;
    justify-content: flex-start;
    row-gap: 8px;
  }
}
/* 14" и меньше (≤1366): компактный кластер — помещается в один аккуратный ряд.
   Прячем хвост «IFRS · UZS · млрд» на кнопке «Вид» (он есть в поповере),
   уменьшаем отступы/паддинги/ширину селектов. */
@media (max-width: 1366px) {
  .ft-bar { gap: 10px; padding: 10px 12px; }
  .ft-cluster { gap: 6px; }
  .ft-view-cur { display: none; }
  .ft-view-btn { padding: 6px 10px; }
  .ft-select { max-width: clamp(118px, 13vw, 162px); font-size: 11px; padding: 5px 24px 5px 10px; }
  .ft-select-year { max-width: 92px; }
  .ft-tab { padding: 5px 11px; }
}
/* Планшет (≤1024): убираем тонкие разделители, селекты тянутся, кластер
   переносится аккуратными рядами без «лесенки» из одиночных элементов. */
@media (max-width: 1024px) {
  .ft-div { display: none; }
  .ft-cluster { gap: 8px; row-gap: 8px; }
  .ft-select { flex: 1 1 130px; max-width: none; }
  .ft-select-year { flex: 0 0 auto; }
  .ft-view-wrap, .ft-tabs { flex: 0 0 auto; }
}
/* Узкие (≤640): вкладки и «Вид» тянутся на всю ширину строки. */
@media (max-width: 640px) {
  .ft-tabs { flex: 1 1 100%; justify-content: space-between; }
  .ft-tab { flex: 1 1 0; text-align: center; }
}

.ft-pill-grp {
  display: inline-flex;
  background: rgba(255, 255, 255, 0.06);
  border: 1px solid rgba(255, 255, 255, 0.10);
  border-radius: 8px;
  padding: 1px;
}

/* «Вид» — поповер со стандартом/валютой/единицами */
.ft-view-wrap { position: relative; display: inline-flex; }
.ft-view-btn {
  display: inline-flex; align-items: center; gap: 7px;
  background: rgba(255,255,255,0.06); border: 1px solid rgba(255,255,255,0.12);
  color: rgba(255,255,255,0.92); border-radius: 9px; padding: 6px 11px;
  font-size: 12px; font-weight: 600; font-family: inherit; cursor: pointer; white-space: nowrap;
  transition: background .15s, border-color .15s;
}
.ft-view-btn:hover, .ft-view-btn.on { background: rgba(127,119,221,0.28); border-color: rgba(127,119,221,0.5); }
.ft-view-cur { font-size: 10.5px; font-weight: 500; color: rgba(255,255,255,0.55); }
.ft-view-bg { position: fixed; inset: 0; z-index: 40; }
.ft-view-pop {
  position: absolute; top: calc(100% + 8px); left: 0; z-index: 50;
  background: #1b2236; border: 1px solid rgba(255,255,255,0.12); border-radius: 12px;
  box-shadow: 0 18px 44px -10px rgba(0,0,0,.55); padding: 12px 14px;
  display: flex; flex-direction: column; gap: 11px; min-width: 240px;
}
.ft-view-row { display: flex; align-items: center; justify-content: space-between; gap: 14px; }
.ft-view-lbl { font-size: 10.5px; font-weight: 600; letter-spacing: .04em; text-transform: uppercase; color: rgba(255,255,255,0.5); }
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
  /* Фикс. ширина: иначе селект «дышит» по длине выбранной опции и кластер
     рвётся по одной пилюле на 13–14". */
  max-width: clamp(150px, 12vw, 190px);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
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
  border-color: rgba(127, 119, 221, 0.42);
  color: #EBE9FF;
  background-color: rgba(127, 119, 221, 0.20);
  font-weight: 600;
}
.ft-select-year:hover {
  background-color: rgba(127, 119, 221, 0.30);
  border-color: rgba(127, 119, 221, 0.55);
}

/* View tabs (P&L/SOFP/CF) — единый стиль .uza-seg.on-dark; здесь только
   layout-хуки для адаптива (см. медиазапросы выше с .ft-tabs/.ft-tab). */
</style>
