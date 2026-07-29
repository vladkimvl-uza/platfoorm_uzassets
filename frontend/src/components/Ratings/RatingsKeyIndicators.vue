<script setup lang="ts">
// "Ключевые индикаторы" panel — ports legacy risksHtml block
// (index.html L53915-53935). Three categories of rows:
//   • lowest Fitch rating in portfolio   (Риск, amber)
//   • weak sectors with <50% credit cover (Слабо, amber)
//   • leader of the portfolio (highest Fitch) (Лидер, green)

import { computed } from "vue";
import type { AgencyRatingBrief } from "@/api/ratings";
import type { CompanyListItem, SectorBrief } from "@/api/companies";
import {
  CREDIT_AGENCIES,
  ratingRank,
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

const ratingIndex = computed(() => buildRatingIndex(props.ratings));

// Lowest Fitch rating
const lowest = computed(() => {
  let loRank = 999, loName = "", loVal = "";
  for (const c of props.companies) {
    const r = getRating(ratingIndex.value, c.id, "Fitch");
    if (!r) continue;
    const rk = ratingRank(r.rating);
    if (rk >= 0 && rk < loRank) {
      loRank = rk; loName = c.name_short || c.name_ru; loVal = r.rating || "";
    }
  }
  return loRank === 999 ? null : { name: loName, value: loVal };
});

// Highest Fitch rating
const highest = computed(() => {
  let hiRank = -1, hiName = "", hiVal = "";
  for (const c of props.companies) {
    const r = getRating(ratingIndex.value, c.id, "Fitch");
    if (!r) continue;
    const rk = ratingRank(r.rating);
    if (rk > hiRank) {
      hiRank = rk; hiName = c.name_short || c.name_ru; hiVal = r.rating || "";
    }
  }
  return hiRank === -1 ? null : { name: hiName, value: hiVal };
});

// Weak sectors: less than 50% credit coverage
const weakSectors = computed(() => {
  const out: { name: string; pct: number; color: string }[] = [];
  for (const sec of props.sectors) {
    const cs = props.companies.filter(c => coSector(c) === String(sec.code).toLowerCase());
    if (!cs.length) continue;
    const covered = cs.filter(c =>
      CREDIT_AGENCIES.some(ag => !!getRating(ratingIndex.value, c.id, ag)),
    ).length;
    const pct = Math.round((covered / cs.length) * 100);
    if (pct < 50) {
      out.push({ name: sec.name_ru, pct, color: sectorColor(sec) });
    }
  }
  // Worst first
  return out.sort((a, b) => a.pct - b.pct);
});

const isEmpty = computed(() =>
  !lowest.value && !highest.value && !weakSectors.value.length,
);
</script>

<template>
  <div class="rki-card">
    <div class="rki-head">{{ t('Ключевые индикаторы') }}</div>
    <div class="rki-body">
      <div v-if="isEmpty" class="rki-empty">{{ t('Нет данных для анализа') }}</div>

      <!-- Lowest -->
      <div v-if="lowest" class="rki-row" style="--idx: 0;">
        <div class="rki-dot" style="background:#EF9F27" />
        <div class="rki-text">
          <span class="rki-name">{{ lowest.name }}</span> —
          <b>{{ t('самый низкий рейтинг (') }}{{ lowest.value }})</b>
        </div>
        <span class="rki-tag tag-risk">{{ t('Риск') }}</span>
      </div>

      <!-- Weak sectors -->
      <div v-for="(ws, i) in weakSectors" :key="ws.name" class="rki-row" :style="{ '--idx': (i + 1) * 60 + 'ms' }">
        <div class="rki-dot" style="background:#EF9F27" />
        <div class="rki-text">
          <span class="rki-sec" :style="{ color: ws.color }">{{ ws.name }}</span> —
          <b>{{ t('покрытие только') }} {{ ws.pct }}%</b>
        </div>
        <span class="rki-tag tag-warn">{{ t('Слабо') }}</span>
      </div>

      <!-- Highest -->
      <div v-if="highest" class="rki-row" :style="{ '--idx': (weakSectors.length + 1) * 60 + 'ms' }">
        <div class="rki-dot" style="background:#1D9E75" />
        <div class="rki-text">
          <span class="rki-name">{{ highest.name }}</span> —
          <b>{{ t('лидер портфеля (') }}{{ highest.value }})</b>
        </div>
        <span class="rki-tag tag-leader">{{ t('Лидер') }}</span>
      </div>
    </div>
  </div>
</template>

<style scoped>
.rki-card {
  background: var(--card-bg, rgba(255, 255, 255, 0.82));
  backdrop-filter: blur(16px) saturate(1.5);
  -webkit-backdrop-filter: blur(16px) saturate(1.5);
  border: 1px solid var(--card-border, var(--border-input));
  border-radius: 12px;
  display: flex;
  flex-direction: column;
  max-height: 220px;
  animation: ratFadeSlideIn .35s ease both;
  overflow: hidden;
}
.rki-head {
  font-size: 12px; font-weight: 600; color: var(--t1, #1E2A4A);
  padding: 9px 14px;
  border-bottom: 0.5px solid var(--border, var(--border-input));
  flex-shrink: 0;
  letter-spacing: -0.005em;
}
.rki-body {
  overflow-y: auto;
  flex: 1;
  scrollbar-width: thin;
}
.rki-empty {
  padding: 18px;
  text-align: center;
  color: var(--t3, var(--t3));
  font-size: 12px;
}
.rki-row {
  display: flex; align-items: center; gap: 10px;
  padding: 9px 14px;
  border-bottom: 0.5px solid var(--border, var(--border-input));
  transition: background .12s;
  animation: ratFadeSlideIn .3s ease var(--idx, 0ms) both;
}
.rki-row:hover { background: rgba(127, 119, 221, .04); }
.rki-row:last-child { border-bottom: none; }
.rki-dot {
  width: 7px; height: 7px; border-radius: 50%;
  flex-shrink: 0;
}
.rki-text {
  font-size: 12.5px; color: var(--t1, #1E2A4A);
  flex: 1; line-height: 1.35;
}
.rki-text b { font-weight: 600; }
.rki-name { font-weight: 500; }
.rki-sec { font-weight: 600; }
.rki-tag {
  font-size: 10px; font-weight: 500;
  padding: 2px 9px;
  border-radius: 9px;
  white-space: nowrap;
  letter-spacing: 0.02em;
}
.tag-risk   { background: var(--orange-l); color: #D97706; }
.tag-warn   { background: var(--orange-l); color: #D97706; }
.tag-leader { background: var(--green-l); color: var(--green); }
</style>
