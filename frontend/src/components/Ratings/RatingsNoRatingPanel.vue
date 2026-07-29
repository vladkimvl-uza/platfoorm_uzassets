<script setup lang="ts">
// Split panel listing companies WITHOUT credit ratings and WITHOUT ESG ratings.
// Click → emit('add', companyId, agency) → parent opens RatingModal.
// Ports legacy "Компании без рейтинга" block (index.html L53989-53996).

import { computed } from "vue";
import type { AgencyRatingBrief } from "@/api/ratings";
import type { CompanyListItem, SectorBrief } from "@/api/companies";
import {
  CREDIT_AGENCIES, ESG_AGENCIES,
  buildRatingIndex, getRating,
  coSector, sectorColor,
} from "./ratingsHelpers";
import { useI18n } from "@/composables/useI18n";
const { t } = useI18n();


const props = defineProps<{
  companies: CompanyListItem[];
  ratings: AgencyRatingBrief[];
  sectors: SectorBrief[];
}>();

const emit = defineEmits<{
  (e: "add", companyId: string, agency: string): void;
}>();

const ratingIndex = computed(() => buildRatingIndex(props.ratings));

const sectorByCode = computed(() => {
  const m: Record<string, SectorBrief> = {};
  for (const s of props.sectors) m[String(s.code).toLowerCase()] = s;
  return m;
});

function colorOf(c: CompanyListItem): string {
  return c.sector_color || sectorColor(sectorByCode.value[coSector(c)]);
}

const noCredit = computed(() =>
  props.companies.filter(c =>
    !CREDIT_AGENCIES.some(ag => !!getRating(ratingIndex.value, c.id, ag)),
  ),
);

const noEsg = computed(() =>
  props.companies.filter(c =>
    !ESG_AGENCIES.some(ag => !!getRating(ratingIndex.value, c.id, ag)),
  ),
);
</script>

<template>
  <div class="rno-card">
    <div class="rno-head">
      <span>{{ t('Компании без рейтинга') }}</span>
    </div>
    <div class="rno-body">
      <!-- Left: no credit -->
      <div class="rno-col">
        <div class="rno-col-head" style="color:#378ADD">
          <span>{{ t('Без кредитного рейтинга') }}</span>
          <span class="rno-cnt">{{ noCredit.length }}</span>
        </div>
        <div class="rno-list">
          <div v-for="(co, i) in noCredit" :key="co.id"
               class="rno-row"
               :style="{ animationDelay: (i * 25) + 'ms' }"
               :title="t('Добавить рейтинг Fitch')"
               @click="emit('add', co.id, 'Fitch')">
            <div class="rno-stripe" :style="{ background: colorOf(co) }" />
            <span class="rno-name">{{ co.name_short || co.name_ru }}</span>
          </div>
          <div v-if="!noCredit.length" class="rno-empty">{{ t('— все покрыты') }}</div>
        </div>
      </div>

      <!-- Right: no ESG -->
      <div class="rno-col rno-col-r">
        <div class="rno-col-head" style="color:#1D9E75">
          <span>{{ t('Без ESG рейтинга') }}</span>
          <span class="rno-cnt">{{ noEsg.length }}</span>
        </div>
        <div class="rno-list">
          <div v-for="(co, i) in noEsg" :key="co.id"
               class="rno-row"
               :style="{ animationDelay: (i * 25) + 'ms' }"
               :title="t('Добавить ESG рейтинг')"
               @click="emit('add', co.id, 'Sustainable Fitch')">
            <div class="rno-stripe" :style="{ background: colorOf(co) }" />
            <span class="rno-name">{{ co.name_short || co.name_ru }}</span>
          </div>
          <div v-if="!noEsg.length" class="rno-empty">{{ t('— все покрыты') }}</div>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.rno-card {
  background: var(--bg2, #fff);
  border: 1px solid var(--border, var(--border-input));
  border-radius: 12px;
  display: flex;
  flex-direction: column;
  flex: 1;
  min-height: 0;
  overflow: hidden;
  animation: ratFadeSlideIn .35s ease both;
}
.rno-head {
  font-size: 12px; font-weight: 600; color: var(--t1, #1E2A4A);
  padding: 9px 14px;
  border-bottom: 0.5px solid var(--border, var(--border-input));
  flex-shrink: 0;
  letter-spacing: -0.005em;
}
.rno-body {
  display: grid;
  grid-template-columns: 1fr 1fr;
  flex: 1;
  min-height: 0;
}
.rno-col {
  padding: 9px 12px;
  overflow-y: auto;
  scrollbar-width: thin;
  display: flex;
  flex-direction: column;
}
.rno-col-r { border-left: 0.5px solid var(--border, var(--border-input)); }
.rno-col-head {
  font-size: 11px; font-weight: 600;
  text-transform: uppercase; letter-spacing: 0.06em;
  margin-bottom: 7px;
  display: flex; align-items: center; justify-content: space-between;
}
.rno-cnt {
  font-weight: 400; color: var(--t3, var(--t3)); font-size: 10px;
}
.rno-list { display: flex; flex-direction: column; }
.rno-row {
  display: flex; align-items: center; gap: 7px;
  padding: 4px 0;
  cursor: pointer;
  transition: opacity .15s, transform .15s;
  animation: ratFadeSlideIn .25s ease both;
}
.rno-row:hover {
  opacity: 0.7;
  transform: translateX(2px);
}
.rno-stripe {
  width: 3px; height: 14px; border-radius: 1px;
  flex-shrink: 0;
}
.rno-name {
  font-size: 12px; color: var(--t1, #1E2A4A); font-weight: 500;
}
.rno-empty {
  font-size: 11px; color: var(--t3, var(--t3)); padding: 6px 0;
  font-style: italic;
}
</style>
