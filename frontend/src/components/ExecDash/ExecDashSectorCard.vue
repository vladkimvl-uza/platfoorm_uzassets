<script setup lang="ts">
/**
 * ExecDashSectorCard — одна карточка сектора в Row 1.
 *
 * Pack 7.29: клик по любой компании (включая без board_id) → emit
 * selectCompany с расширенным payload, чтобы родитель открыл модалку
 * CompanyDrillModal. Раньше hover/click-affordance был только при
 * наличии board_id — теперь у всех строк.
 *
 * Payload:
 *   { company_id, board_id, name, pct, task_total, task_done, sector_color, sector_label }
 *
 * Click на chev → разворачивает все компании
 */
import { computed, ref, onMounted } from "vue";
import type { ExecSectorRow } from "@/api/executiveDashboard";
import { useCompaniesStore } from "@/stores/companies";

// Pack 7.13: unified naming via store
const companies = useCompaniesStore();
onMounted(() => { void companies.ensureLoaded(); });

interface Props {
  sector: ExecSectorRow;
  staggerDelay?: number;
}
const props = withDefaults(defineProps<Props>(), { staggerDelay: 0 });

export interface SectorCardSelectPayload {
  company_id: string;
  board_id: string | null;
  name: string;
  pct: number;
  task_total: number;
  task_done: number;
  sector_color: string;
  sector_label: string;
}

const emit = defineEmits<{
  selectCompany: [SectorCardSelectPayload];
}>();

const expanded = ref(false);

const visibleCompanies = computed(() => {
  if (expanded.value || props.sector.companies.length <= 3) {
    return props.sector.companies;
  }
  return props.sector.companies.slice(0, 3);
});

const hiddenCount = computed(() =>
  props.sector.companies.length > 3
    ? props.sector.companies.length - 3
    : 0,
);

function pctColor(pct: number): string {
  if (pct >= 60) return "#1D9E75";
  if (pct >= 30) return "#EF9F27";
  return "#E24B4A";
}

function onClickCompany(c: { company_id: string; board_id?: string | null; name: string; pct: number; task_total: number; task_done: number }) {
  emit("selectCompany", {
    company_id: c.company_id,
    board_id: c.board_id || null,
    name: c.name,
    pct: c.pct,
    task_total: c.task_total,
    task_done: c.task_done,
    sector_color: props.sector.color,
    sector_label: props.sector.label,
  });
}

const coWord = computed(() => {
  const n = props.sector.companies_total;
  if (n === 1) return "компания";
  if (n >= 2 && n <= 4) return "компании";
  return "компаний";
});
</script>

<template>
  <div
    class="va-sec"
    :class="{ 'va-sec-expanded': expanded, 'va-sec-clickable': hiddenCount > 0 }"
    :style="{ '--sc': sector.color, '--va-sec-d': staggerDelay + 'ms' }"
    @click.self="hiddenCount > 0 && (expanded = !expanded)"
  >
    <div class="va-sec-glow" />

    <!-- Header -->
    <div class="va-sec-h">
      <div>
        <div class="va-sec-t">{{ sector.label }}</div>
        <div class="va-sec-l">
          {{ sector.companies_active }} из {{ sector.companies_total }} {{ coWord }}
        </div>
      </div>
      <div style="text-align: right">
        <div class="va-sec-p">
          {{ sector.avg_pct }}<span class="u">%</span>
        </div>
        <div class="va-sec-l">средний</div>
      </div>
    </div>

    <!-- Companies list -->
    <div class="va-sec-cos" v-if="visibleCompanies.length">
      <div
        v-for="(c, i) in visibleCompanies"
        :key="c.company_id"
        class="va-sec-co va-sec-co-clickable"
        :class="{ 'va-sec-co-extra': i >= 3 }"
        :style="{ '--ci': i, '--ei': i - 3 }"
        @click.stop="onClickCompany(c)"
        title="Открыть карточку компании"
      >
        <span class="co">{{ companies.getCompanyNameById(c.company_id) || c.name }}</span>
        <span class="pct" :style="{ color: pctColor(c.pct) }">
          {{ c.pct }}%
        </span>
      </div>
    </div>
    <div v-else class="va-sec-empty">Нет данных</div>

    <!-- Chev -->
    <div
      v-if="hiddenCount > 0"
      class="va-sec-chev"
      @click.stop="expanded = !expanded"
      :title="expanded ? 'Свернуть' : 'Показать ещё ' + hiddenCount"
    >
      <svg
        viewBox="0 0 14 14" fill="none" stroke="currentColor"
        stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round"
        width="14" height="14"
      >
        <path d="M3.5 5.5l3.5 3.5 3.5-3.5" />
      </svg>
      <span class="va-sec-chev-n">{{ hiddenCount }}</span>
    </div>
  </div>
</template>

<style scoped>
.va-sec {
  background: linear-gradient(180deg, #FAFAFC 0%, #F5F4F9 100%);
  border-radius: 11px;
  padding: 14px 14px 10px;
  position: relative;
  overflow: hidden;
  border: 1px solid rgba(0, 0, 0, 0.04);
  cursor: default;
}
.va-sec.va-sec-clickable { cursor: pointer; }

.va-sec::before {
  content: "";
  position: absolute;
  top: 0; left: 0; right: 0;
  height: 3px;
  background: var(--sc, #888780);
  border-radius: 11px 11px 0 0;
  z-index: 2;
  animation: vaDrawIn 0.7s cubic-bezier(0.34, 1.2, 0.64, 1) var(--va-sec-d, 0ms) both;
  transform-origin: left center;
}

.va-sec::after {
  content: "";
  position: absolute;
  top: 0; left: 0; right: 0;
  height: 3px;
  border-radius: 11px 11px 0 0;
  background: linear-gradient(90deg, transparent, rgba(255, 255, 255, 0.65), transparent);
  animation: vaShimmer 6s ease-in-out calc(var(--va-sec-d, 0ms) + 1.2s) infinite;
  transform: translateX(-120%);
  pointer-events: none;
  z-index: 3;
}

.va-sec-glow {
  position: absolute;
  inset: 0;
  background: radial-gradient(circle at top right, var(--sc, #888780) 0%, transparent 60%);
  opacity: 0.04;
  pointer-events: none;
  z-index: 1;
}

.va-sec-h {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  margin-bottom: 12px;
  position: relative;
  z-index: 2;
}

.va-sec-t {
  font-size: 12px;
  font-weight: 600;
  color: #1E2A4A;
  line-height: 1.2;
  margin-bottom: 2px;
}

.va-sec-l {
  font-size: 9px;
  color: #888780;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  font-weight: 500;
}

.va-sec-p {
  font-size: 24px;
  font-weight: 600;
  color: var(--sc, #888780);
  font-feature-settings: "tnum";
  line-height: 1;
  letter-spacing: -0.02em;
  display: flex;
  align-items: baseline;
  justify-content: flex-end;
}

.va-sec-p .u {
  font-size: 13px;
  font-weight: 500;
  color: #888780;
  margin-left: 1px;
}

.va-sec-cos {
  display: flex;
  flex-direction: column;
  gap: 0;
  padding-top: 2px;
  border-top: 1px dashed rgba(0, 0, 0, 0.06);
  position: relative;
  z-index: 2;
}

.va-sec-co {
  display: flex;
  justify-content: space-between;
  padding: 6px 0;
  font-size: 11.5px;
  border-bottom: 1px dashed rgba(0, 0, 0, 0.04);
  align-items: center;
  gap: 8px;
}
.va-sec-co:last-child { border-bottom: none; }
.va-sec-co.va-sec-co-clickable { cursor: pointer; }
.va-sec-co.va-sec-co-clickable:hover .co { color: var(--sc); }

.va-sec-co .co {
  font-weight: 500;
  color: #1E2A4A;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  flex: 1;
  display: flex;
  align-items: center;
  gap: 7px;
  transition: color 0.12s;
}

.va-sec-co .co::before {
  content: "";
  width: 3px;
  height: 12px;
  border-radius: 0;
  background: var(--sc);
  flex-shrink: 0;
  opacity: 0.85;
}

.va-sec-co .pct {
  font-feature-settings: "tnum";
  font-weight: 600;
  flex-shrink: 0;
  margin-left: 8px;
}

.va-sec-empty {
  font-size: 11px;
  color: #888780;
  padding: 8px 0;
  text-align: center;
}

/* Hidden rows — animated */
.va-sec-co-extra {
  max-height: 0;
  opacity: 0;
  padding-top: 0;
  padding-bottom: 0;
  border-bottom-width: 0;
  overflow: hidden;
  transition:
    max-height 0.28s cubic-bezier(0.33, 1, 0.68, 1),
    opacity 0.22s ease,
    padding-top 0.2s ease,
    padding-bottom 0.2s ease,
    border-bottom-width 0.2s ease;
}
.va-sec.va-sec-expanded .va-sec-co-extra {
  max-height: 32px;
  opacity: 1;
  padding-top: 6px;
  padding-bottom: 6px;
  border-bottom-width: 1px;
  transition-delay: calc(var(--ei, 0) * 50ms);
}

/* Chev */
.va-sec-chev {
  margin-top: 8px;
  padding: 5px 8px;
  text-align: center;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 4px;
  font-size: 10.5px;
  font-weight: 600;
  color: var(--sc, #7F77DD);
  background: rgba(127, 119, 221, 0.05);
  border-radius: 6px;
  border: 1px dashed rgba(0, 0, 0, 0.08);
  cursor: pointer;
  transition: all 0.18s;
  position: relative;
  z-index: 2;
}
.va-sec-chev:hover {
  background: rgba(127, 119, 221, 0.10);
  border-color: rgba(127, 119, 221, 0.30);
}
.va-sec-chev svg {
  transition: transform 0.3s cubic-bezier(0.33, 1, 0.68, 1);
  opacity: 0.85;
}
.va-sec.va-sec-expanded .va-sec-chev svg {
  transform: rotate(180deg);
}

@keyframes vaDrawIn {
  0%   { transform: scaleX(0); }
  100% { transform: scaleX(1); }
}

@keyframes vaShimmer {
  0%   { transform: translateX(-120%); }
  60%  { transform: translateX(220%); }
  100% { transform: translateX(220%); }
}
</style>
