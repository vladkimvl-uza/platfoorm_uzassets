<script setup lang="ts">
// 6 KPI cards — top of Ratings page. Ports legacy showRatingsView strip
// (index.html L53980-54010). Each card uses kpiCardIn + kpi2DrawIn + shimmer.

import { computed, onMounted } from "vue";
import Odometer from "@/components/Odometer.vue";
import type { AgencyRatingBrief } from "@/api/ratings";
import type { CompanyListItem } from "@/api/companies";
import {
  CREDIT_AGENCIES, ESG_AGENCIES, RANK_ORDER,
  ratingRank, isRecentlyUpdated,
  buildRatingIndex, getRating,
  ensureRatingsCss,
} from "./ratingsHelpers";

const props = defineProps<{
  companies: CompanyListItem[];
  ratings: AgencyRatingBrief[];
}>();

onMounted(ensureRatingsCss);

const ratingIndex = computed(() => buildRatingIndex(props.ratings));
const tot = computed(() => props.companies.length);

function countWithAgency(ag: string): number {
  return props.companies.filter(c => !!getRating(ratingIndex.value, c.id, ag)).length;
}

function countRecent(ag: string): number {
  return props.companies.filter(c => {
    const r = getRating(ratingIndex.value, c.id, ag);
    return r && isRecentlyUpdated(r);
  }).length;
}

const fitchCount = computed(() => countWithAgency("Fitch"));
const spCount    = computed(() => countWithAgency("S&P"));
const moodCount  = computed(() => countWithAgency("Moody's"));

const esgCount = computed(() =>
  props.companies.filter(c =>
    ESG_AGENCIES.some(ag => !!getRating(ratingIndex.value, c.id, ag)),
  ).length,
);

const fitchRecent = computed(() => countRecent("Fitch"));
const spRecent    = computed(() => countRecent("S&P"));
const moodRecent  = computed(() => countRecent("Moody's"));
const esgRecent   = computed(() =>
  props.companies.filter(c => {
    return ESG_AGENCIES.some(ag => {
      const r = getRating(ratingIndex.value, c.id, ag);
      return r && isRecentlyUpdated(r);
    });
  }).length,
);

const medianFitch = computed(() => {
  const ranks: number[] = [];
  for (const c of props.companies) {
    const r = getRating(ratingIndex.value, c.id, "Fitch");
    if (r) {
      const rk = ratingRank(r.rating);
      if (rk >= 0) ranks.push(rk);
    }
  }
  if (!ranks.length) return "—";
  ranks.sort((a, b) => a - b);
  return RANK_ORDER[ranks[Math.floor(ranks.length / 2)]] || "—";
});

const credPct = computed(() => {
  if (!tot.value) return 0;
  const haveAny = props.companies.filter(c =>
    CREDIT_AGENCIES.some(ag => !!getRating(ratingIndex.value, c.id, ag)),
  ).length;
  return Math.round((haveAny / tot.value) * 100);
});

const esgPct = computed(() => {
  if (!tot.value) return 0;
  return Math.round((esgCount.value / tot.value) * 100);
});

function pctColor(p: number): string {
  if (p >= 70) return "#1D9E75";
  if (p >= 40) return "#EF9F27";
  return "#E24B4A";
}

function dynamicLabel(n: number): string {
  return n > 0 ? `+${n} компаний с 2024` : "= без изменений";
}
function dynamicColor(n: number): string {
  return n > 0 ? "#1D9E75" : "var(--t3, #64748B)";
}
</script>

<template>
  <div class="rkb-grid kpi-rail">
    <!-- 1. Fitch -->
    <div class="rkb-card" style="--accent:#1D9E75; --d:0ms;">
      <div class="rkb-lbl">Fitch Ratings</div>
      <div class="rkb-val">
        <Odometer :value="fitchCount" /><span class="rkb-tot"> / {{ tot }}</span>
      </div>
      <div class="rkb-sub" :style="{ color: dynamicColor(fitchRecent) }">
        {{ dynamicLabel(fitchRecent) }}
      </div>
    </div>

    <!-- 2. S&P -->
    <div class="rkb-card" style="--accent:#EF4444; --d:80ms;">
      <div class="rkb-lbl">S&amp;P Global</div>
      <div class="rkb-val">
        <Odometer :value="spCount" /><span class="rkb-tot"> / {{ tot }}</span>
      </div>
      <div class="rkb-sub" :style="{ color: dynamicColor(spRecent) }">
        {{ dynamicLabel(spRecent) }}
      </div>
    </div>

    <!-- 3. Moody's -->
    <div class="rkb-card" style="--accent:#7F77DD; --d:160ms;">
      <div class="rkb-lbl">Moody's</div>
      <div class="rkb-val">
        <Odometer :value="moodCount" /><span class="rkb-tot"> / {{ tot }}</span>
      </div>
      <div class="rkb-sub" :style="{ color: dynamicColor(moodRecent) }">
        {{ dynamicLabel(moodRecent) }}
      </div>
    </div>

    <!-- 4. ESG -->
    <div class="rkb-card" style="--accent:#378ADD; --d:240ms;">
      <div class="rkb-lbl">ESG рейтинг</div>
      <div class="rkb-val">
        <Odometer :value="esgCount" /><span class="rkb-tot"> / {{ tot }}</span>
      </div>
      <div class="rkb-sub" :style="{ color: dynamicColor(esgRecent) }">
        {{ dynamicLabel(esgRecent) }}
      </div>
    </div>

    <!-- 5. Median Fitch -->
    <div class="rkb-card" style="--accent:#EF9F27; --d:320ms;">
      <div class="rkb-lbl">Медианный рейтинг</div>
      <div class="rkb-val rkb-val-letter" style="color:#D97706">{{ medianFitch }}</div>
      <div class="rkb-sub">Fitch / портфель</div>
    </div>

    <!-- 6. Coverage (dual progress bar) -->
    <div class="rkb-card" style="--accent:#E24B4A; --d:400ms;">
      <div class="rkb-lbl">Покрытие</div>
      <div class="rkb-bars">
        <div class="rkb-bar-row">
          <div class="rkb-bar-head">
            <span class="rkb-bar-key">кредит</span>
            <span class="rkb-bar-val" :style="{ color: pctColor(credPct) }"><Odometer :value="credPct" />%</span>
          </div>
          <div class="rkb-bar-track">
            <div class="rkb-bar-fill" :style="{ width: credPct + '%', background: pctColor(credPct) }" />
          </div>
        </div>
        <div class="rkb-bar-row">
          <div class="rkb-bar-head">
            <span class="rkb-bar-key">ESG</span>
            <span class="rkb-bar-val" :style="{ color: pctColor(esgPct) }"><Odometer :value="esgPct" />%</span>
          </div>
          <div class="rkb-bar-track">
            <div class="rkb-bar-fill" :style="{ width: esgPct + '%', background: pctColor(esgPct) }" />
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.rkb-grid {
  display: grid;
  grid-template-columns: repeat(6, 1fr);
  gap: 14px;
}
@media (max-width: 1280px) { .rkb-grid { grid-template-columns: repeat(3, 1fr); } }
@media (max-width: 720px)  { .rkb-grid { grid-template-columns: repeat(2, 1fr); } }

.rkb-card {
  background: rgba(255, 255, 255, 0.82);
  backdrop-filter: blur(16px) saturate(1.5);
  -webkit-backdrop-filter: blur(16px) saturate(1.5);
  border-radius: 16px;
  padding: 16px 18px 14px;
  border: 1px solid rgba(255, 255, 255, 0.70);
  box-shadow: 0 2px 12px rgba(15, 23, 60, 0.07), 0 1px 3px rgba(15, 23, 60, 0.04);
  position: relative;
  overflow: hidden;
  display: flex;
  flex-direction: column;
  justify-content: space-between;
  min-height: 96px;
  transition: transform .2s cubic-bezier(.34,1.56,.64,1), box-shadow .2s, border-color .2s;
  animation: ratKpiCardIn .55s var(--ease-standard) var(--d, 0ms) both;
}
.rkb-card:hover {
  transform: translateY(-3px) scale(1.01);
  box-shadow: 0 12px 32px rgba(15, 23, 60, .12), 0 4px 12px rgba(15, 23, 60, .06);
  border-color: rgba(124, 111, 247, .25);
}
.rkb-card::before {
  content: '';
  position: absolute;
  top: 0; left: 0; right: 0;
  height: 3px;
  background: var(--accent, var(--border-input));
  border-radius: 16px 16px 0 0;
  animation: ratKpi2DrawIn .8s var(--ease-standard) var(--d, 0ms) both,
             ratKpi2Breathe 2.8s ease-in-out calc(var(--d, 0ms) + 1s) infinite;
  transform-origin: left center;
}
.rkb-card::after {
  content: '';
  position: absolute;
  top: 0; left: 0; right: 0;
  height: 3px;
  background: linear-gradient(90deg, transparent, rgba(255, 255, 255, .55), transparent);
  animation: ratShimmer 6s ease-in-out calc(var(--d, 0ms) + 1.2s) 1;
  transform: translateX(-120%);
  pointer-events: none;
}

.rkb-lbl {
  font-size: 12px; font-weight: 500; color: var(--t3, var(--t3));
  text-transform: uppercase; letter-spacing: 0.06em; margin-bottom: 8px;
}
.rkb-val {
  font-size: 32px; font-weight: 400; letter-spacing: -0.04em; line-height: 1;
  color: var(--t1, #1E2A4A); font-variant-numeric: tabular-nums;
}
.rkb-val-letter { font-size: 28px; font-weight: 500; letter-spacing: -0.02em; }
.rkb-tot { font-size: 16px; color: var(--t3, var(--t3)); }
.rkb-sub {
  font-size: 11px; margin-top: 6px; font-weight: 500;
}
.rkb-bars { display: flex; flex-direction: column; gap: 7px; margin-top: 4px; }
.rkb-bar-row { display: flex; flex-direction: column; gap: 3px; }
.rkb-bar-head { display: flex; justify-content: space-between; align-items: baseline; }
.rkb-bar-key {
  font-size: 10px; color: var(--t3, var(--t3)); font-weight: 500;
}
.rkb-bar-val {
  font-size: 13px; font-weight: 700; font-variant-numeric: tabular-nums;
}
.rkb-bar-track {
  height: 5px; background: rgba(241, 245, 249, .9); border-radius: 3px; overflow: hidden;
}
.rkb-bar-fill {
  height: 100%; border-radius: 3px;
  transition: width .65s var(--ease-standard);
}
</style>
