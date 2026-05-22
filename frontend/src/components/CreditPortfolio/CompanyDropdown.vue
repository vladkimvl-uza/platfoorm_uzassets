<script setup lang="ts">
/**
 * CompanyDropdown — кастомный темный dropdown компаний для топбара.
 *
 * Adapter v2 — теперь оперирует UUID компании (id из cp_loans.company_id).
 * Источник списка — backend /credit-portfolio/companies-with-loans.
 *
 * Слушает click-outside через document listener.
 * Опции отсортированы по debt_usd убыванию.
 * Акцентный цвет — #FAC775 (мёд).
 */
import { computed, onMounted, onUnmounted, ref } from "vue";
import { useCreditData } from "@/composables/useCreditData";
import { fmtMoneyShort, toNum } from "@/api/credit";

const credit = useCreditData();
const open = ref(false);
const rootEl = ref<HTMLElement | null>(null);

const sortedCompanies = computed(() =>
  credit.companiesWithLoans.value
    .slice()
    .sort((a, b) => toNum(b.debt_usd) - toNum(a.debt_usd)),
);

const totalLoans = computed(() =>
  sortedCompanies.value.reduce((s, c) => s + c.loans_count, 0),
);

const totalDebtUsd = computed(() =>
  sortedCompanies.value.reduce((s, c) => s + toNum(c.debt_usd), 0),
);

const buttonLabel = computed(() => {
  if (credit.selectedCompanyMeta.value)
    return credit.selectedCompanyMeta.value.company_name_ru;
  return "Все компании";
});

const buttonSub = computed(() => {
  const co = credit.selectedCompanyMeta.value;
  if (co) {
    return `${co.loans_count} кред. · ${fmtMoneyShort(toNum(co.debt_usd))}`;
  }
  return `${totalLoans.value} кред. · ${fmtMoneyShort(totalDebtUsd.value)}`;
});

function toggle() {
  open.value = !open.value;
}

function selectCompany(co: any /* CompanyWithLoansRow | null */) {
  credit.setSelectedCompany(co);
  open.value = false;
}

function onDocClick(e: MouseEvent) {
  if (!rootEl.value) return;
  if (!rootEl.value.contains(e.target as Node)) {
    open.value = false;
  }
}

onMounted(() => document.addEventListener("click", onDocClick));
onUnmounted(() => document.removeEventListener("click", onDocClick));
</script>

<template>
  <div ref="rootEl" class="cp-dd-root">
    <button
      type="button"
      class="cp-dd-btn"
      :class="{ 'cp-dd-btn-open': open }"
      @click="toggle"
    >
      <span class="cp-dd-label">
        <span class="cp-dd-name">{{ buttonLabel }}</span>
        <span class="cp-dd-sub">{{ buttonSub }}</span>
      </span>
      <svg
        class="cp-dd-caret"
        :class="{ 'cp-dd-caret-open': open }"
        width="12"
        height="12"
        viewBox="0 0 12 12"
        fill="none"
      >
        <path
          d="M3 4.5L6 7.5L9 4.5"
          stroke="currentColor"
          stroke-width="1.5"
          stroke-linecap="round"
          stroke-linejoin="round"
        />
      </svg>
    </button>

    <transition name="uza-pop">
      <div v-if="open" class="cp-dd-menu">
        <!-- Все компании -->
        <button
          type="button"
          class="cp-dd-row cp-dd-row-all"
          :class="{ 'cp-dd-row-active': credit.isAllCompanies.value }"
          @click="selectCompany(null)"
        >
          <span class="cp-dd-row-name">Все компании</span>
          <span class="cp-dd-row-meta">
            {{ totalLoans }} кред. · {{ fmtMoneyShort(totalDebtUsd) }}
          </span>
        </button>

        <div class="cp-dd-sep" />

        <!-- Список -->
        <div class="cp-dd-list">
          <button
            v-for="co in sortedCompanies"
            :key="co.company_id"
            type="button"
            class="cp-dd-row"
            :class="{ 'cp-dd-row-active': credit.selectedCompanyId.value === co.company_id }"
            @click="selectCompany(co)"
          >
            <span
              v-if="co.sector_color"
              class="cp-dd-bullet"
              :style="{ background: co.sector_color }"
            />
            <span class="cp-dd-row-name">{{ co.company_name_ru }}</span>
            <span class="cp-dd-row-meta">
              {{ co.loans_count }} · {{ fmtMoneyShort(toNum(co.debt_usd)) }}
            </span>
          </button>
        </div>
      </div>
    </transition>
  </div>
</template>

<style scoped>
.cp-dd-root {
  position: relative;
  display: inline-block;
}

/* ─── Trigger (Pack 137 restyle — glass-navy like InvestProjects/FinModel) ─── */
.cp-dd-btn {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 5px 11px;
  height: 32px;
  background: rgba(255, 255, 255, 0.08);
  color: #fff;
  border: 1px solid rgba(255, 255, 255, 0.12);
  border-radius: 8px;
  cursor: pointer;
  font-family: inherit;
  font-size: 12px;
  font-weight: 500;
  text-align: left;
  min-width: 180px;
  transition: background 0.15s, border-color 0.15s;
}

.cp-dd-btn:hover,
.cp-dd-btn-open {
  background: rgba(255, 255, 255, 0.14);
  border-color: rgba(255, 255, 255, 0.22);
}

.cp-dd-label {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 1px;
  min-width: 0;
}

.cp-dd-name {
  font-size: 12px;
  font-weight: 500;
  color: #fff;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  line-height: 1.2;
}

.cp-dd-sub {
  font-size: 9.5px;
  font-weight: 500;
  color: rgba(255, 255, 255, 0.55);
  letter-spacing: 0.06em;
  font-feature-settings: "tnum";
  text-transform: uppercase;
}

.cp-dd-caret {
  flex-shrink: 0;
  color: rgba(250, 199, 117, 0.7);
  transition: transform 0.18s ease;
}

.cp-dd-caret-open {
  transform: rotate(180deg);
}

/* ─── Menu ─── */
.cp-dd-menu {
  position: absolute;
  top: calc(100% + 6px);
  right: 0;
  min-width: 320px;
  max-height: 480px;
  overflow-y: auto;
  background: rgba(15, 18, 40, 0.96);
  border: 1px solid rgba(250, 199, 117, 0.2);
  border-radius: 10px;
  box-shadow: 0 24px 64px rgba(0, 0, 0, 0.5);
  padding: 6px;
  z-index: 100;
  backdrop-filter: blur(8px);
}

.cp-dd-pop-enter-active,
.cp-dd-pop-leave-active {
  transition: opacity 0.14s ease, transform 0.18s cubic-bezier(0.34, 1.2, 0.64, 1);
}

.cp-dd-pop-enter-from,
.cp-dd-pop-leave-to {
  opacity: 0;
  transform: translateY(-6px);
}

/* ─── Row ─── */
.cp-dd-row {
  width: 100%;
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 8px 12px;
  background: transparent;
  color: rgba(255, 255, 255, 0.85);
  border: none;
  border-radius: 6px;
  cursor: pointer;
  font-family: inherit;
  font-size: 12.5px;
  font-weight: 500;
  text-align: left;
  transition: background 0.12s;
}

.cp-dd-row:hover {
  background: rgba(250, 199, 117, 0.08);
  color: rgba(255, 255, 255, 0.96);
}

.cp-dd-row-active {
  background: rgba(250, 199, 117, 0.14);
  color: #FAC775;
}

.cp-dd-row-all {
  font-weight: 600;
}

.cp-dd-bullet {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  flex-shrink: 0;
  opacity: 0.85;
}

.cp-dd-row-name {
  flex: 1;
  min-width: 0;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.cp-dd-row-meta {
  font-size: 10.5px;
  color: rgba(250, 199, 117, 0.65);
  font-weight: 400;
  font-feature-settings: "tnum";
  flex-shrink: 0;
}

.cp-dd-sep {
  height: 1px;
  background: rgba(250, 199, 117, 0.15);
  margin: 4px 0;
}

.cp-dd-list {
  display: flex;
  flex-direction: column;
  gap: 1px;
}

/* Pack 139: navy popover items (match InvestProjects style) */
.cp-dd-menu {
  background: #1E2A4A !important;
  border: 1px solid rgba(255, 255, 255, 0.12) !important;
  border-radius: 10px !important;
  box-shadow: 0 12px 32px rgba(15,23,60,.4), 0 4px 12px rgba(15,23,60,.2) !important;
  padding: 4px !important;
}
.cp-dd-menu button,
.cp-dd-menu .cp-dd-item {
  background: transparent !important;
  color: #fff !important;
  font-size: 12px !important;
  font-weight: 500 !important;
  padding: 8px 11px !important;
  border-radius: 6px !important;
  border: none !important;
  text-align: left !important;
  display: flex !important;
  align-items: center !important;
  gap: 9px !important;
  transition: background .12s !important;
}
.cp-dd-menu button:hover,
.cp-dd-menu .cp-dd-item:hover {
  background: rgba(255, 255, 255, 0.08) !important;
}
.cp-dd-menu .cp-dd-item-active,
.cp-dd-menu button.active {
  background: rgba(155, 142, 196, 0.18) !important;
}
.cp-dd-menu .cp-dd-divider,
.cp-dd-menu hr {
  border-color: rgba(255, 255, 255, 0.08) !important;
  background: rgba(255, 255, 255, 0.08) !important;
}
</style>
