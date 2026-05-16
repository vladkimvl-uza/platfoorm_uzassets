<script setup lang="ts">
// ============================================================================
//
//
//   [ TOPBAR: Title + sector chips ]
//   [ KPI band: 6 cards (Fitch / S&P / Moody's / ESG / Median / Coverage) ]
//   [ ┌─ Key indicators ──┐ ┌─ Recent changes (split: credit / ESG) ────┐ ]
//   [ │                    │ │                                            │ ]
//   [ └────────────────────┘ │                                            │ ]
//   [ ┌─ No-rating panel ─┐ │                                            │ ]
//   [ │ split credit/ESG   │ │                                            │ ]
//   [ └────────────────────┘ └────────────────────────────────────────────┘ ]
//   [ ┌─ Credit ratings table ─────┐ ┌─ ESG ratings table ────────────────┐ ]
//   [ │ sector-grouped, 22×3       │ │ sector-grouped, 22×3              │ ]
//   [ └────────────────────────────┘ └────────────────────────────────────┘ ]
//
// Data flow:
//   1. Load /companies → CompanyListResponse (items + sectors)
//   2. Load /ratings   → AgencyRatingListResponse (items)
//   3. Sector filter (chips) narrows companies before passing to children
// ============================================================================

import { ref, computed, onMounted } from "vue";
import { ratingsApi, type AgencyRatingBrief } from "@/api/ratings";
import { companiesApi, type CompanyListItem, type SectorBrief } from "@/api/companies";
import {
  coSector, ensureRatingsCss, pluralCompanies,
} from "@/components/Ratings/ratingsHelpers";

import RatingsKpiBand        from "@/components/Ratings/RatingsKpiBand.vue";
import RatingsKeyIndicators  from "@/components/Ratings/RatingsKeyIndicators.vue";
import RatingsNoRatingPanel  from "@/components/Ratings/RatingsNoRatingPanel.vue";
import RatingsRecentChanges  from "@/components/Ratings/RatingsRecentChanges.vue";
import RatingsSectorTable    from "@/components/Ratings/RatingsSectorTable.vue";

// ─── State ────────────────────────────────────────────────────────────────
const allCompanies = ref<CompanyListItem[]>([]);
const allRatings   = ref<AgencyRatingBrief[]>([]);
const sectors      = ref<SectorBrief[]>([]);
const loading      = ref(true);
const errorMsg     = ref<string | null>(null);

const sectorFilter = ref<string>(""); // "" = all sectors

// ─── Data load ────────────────────────────────────────────────────────────
async function load() {
  loading.value = true;
  errorMsg.value = null;
  try {
    const [companiesResp, ratingsResp] = await Promise.all([
      companiesApi.list({ limit: 200 }),
      ratingsApi.list({ limit: 1000 }),
    ]);
    allCompanies.value = companiesResp.items || [];
    sectors.value = companiesResp.sectors || [];
    allRatings.value = ratingsResp.items || [];
  } catch (e: any) {
    errorMsg.value = e?.response?.data?.detail || e?.message || "Ошибка загрузки";
    console.error("Ratings load failed:", e);
  } finally {
    loading.value = false;
  }
}

onMounted(() => {
  ensureRatingsCss();
  load();
});

// ─── Filtered company list (by sector chip) ─────────────────────────────
const filteredCompanies = computed<CompanyListItem[]>(() => {
  if (!sectorFilter.value) return allCompanies.value;
  const target = sectorFilter.value.toLowerCase();
  return allCompanies.value.filter(c => coSector(c) === target);
});

// Counts per sector — for chip badges
const sectorCounts = computed<Record<string, number>>(() => {
  const counts: Record<string, number> = {};
  for (const c of allCompanies.value) {
    const s = coSector(c) || "_orphan";
    counts[s] = (counts[s] || 0) + 1;
  }
  return counts;
});

// Sectors sorted for chip display
const sortedSectors = computed(() =>
  [...sectors.value].sort((a, b) => (a.sort_order || 0) - (b.sort_order || 0)),
);

const totalCount = computed(() => filteredCompanies.value.length);

function toggleSector(code: string) {
  sectorFilter.value = sectorFilter.value === code ? "" : code;
}

function activeSectorLabel(): string {
  if (!sectorFilter.value) return "";
  const s = sectors.value.find(x => String(x.code).toLowerCase() === sectorFilter.value);
  return s?.name_ru || sectorFilter.value;
}

// ─── Modal stubs (to be replaced by RatingModal in next phase) ────────
function onOpenRating(companyId: string, agency: string) {
  // TODO: emit upward to App-level RatingModal mount, or use a dedicated store.
  console.log("openRating →", { companyId, agency });
}
function onAddRating(companyId: string, agency: string) {
  console.log("addRating →", { companyId, agency });
}
function onShowAllChanges() {
  console.log("showAllRatingChanges → modal stub");
}
</script>

<template>
  <div class="rt-page">
    <!-- Topbar -->
    <div class="rt-topbar">
      <div class="rt-topbar-l">
        <div class="rt-eyebrow">ВНЕШНИЕ РЕЙТИНГИ</div>
        <h1 class="rt-title">Рейтинги портфеля</h1>
        <div class="rt-sub">
          <span class="rt-sub-num">{{ totalCount }}</span>
          <span class="rt-sub-word">{{ pluralCompanies(totalCount) }}</span>
          <span v-if="sectorFilter" class="rt-sub-sec">
            · сектор:
            <span class="rt-sub-sec-label">{{ activeSectorLabel() }}</span>
          </span>
        </div>
      </div>
    </div>

    <div class="rt-chips">
      <div class="rt-chip"
           :class="{ 'is-active': !sectorFilter }"
           @click="sectorFilter = ''">
        <span>Все секторы</span>
        <span class="rt-chip-cnt">{{ allCompanies.length }}</span>
      </div>
      <div v-for="s in sortedSectors"
           :key="s.code"
           class="rt-chip"
           :class="{ 'is-active': sectorFilter === String(s.code).toLowerCase() }"
           :style="{ '--chip-c': s.color_hex || '#7F77DD' }"
           @click="toggleSector(String(s.code).toLowerCase())">
        <span class="rt-chip-dot" :style="{ background: s.color_hex || '#7F77DD' }" />
        <span>{{ s.name_ru }}</span>
        <span class="rt-chip-cnt">{{ sectorCounts[String(s.code).toLowerCase()] || 0 }}</span>
      </div>
    </div>

    <!-- Loading / Error -->
    <div v-if="loading" class="rt-state">Загрузка рейтингов…</div>
    <div v-else-if="errorMsg" class="rt-state rt-state-err">
      ⚠ {{ errorMsg }}
      <button class="rt-state-btn" @click="load">Повторить</button>
    </div>

    <!-- Main content -->
    <template v-else>
      <!-- KPI band (6 cards) -->
      <div class="rt-section">
        <RatingsKpiBand :companies="filteredCompanies" :ratings="allRatings" />
      </div>

      <!-- Middle row: indicators+no-rating | recent-changes -->
      <div class="rt-mid-row">
        <div class="rt-mid-left">
          <RatingsKeyIndicators
            :companies="filteredCompanies"
            :ratings="allRatings"
            :sectors="sectors" />
          <RatingsNoRatingPanel
            :companies="filteredCompanies"
            :ratings="allRatings"
            :sectors="sectors"
            @add="onAddRating" />
        </div>
        <div class="rt-mid-right">
          <RatingsRecentChanges
            :companies="filteredCompanies"
            :ratings="allRatings"
            :sectors="sectors"
            @open-rating="onOpenRating"
            @show-all="onShowAllChanges" />
        </div>
      </div>

      <!-- Bottom row: 2 separate sector tables -->
      <div class="rt-bot-row">
        <RatingsSectorTable
          kind="credit"
          :companies="filteredCompanies"
          :ratings="allRatings"
          :sectors="sectors"
          @open-rating="onOpenRating"
          @add="onAddRating" />
        <RatingsSectorTable
          kind="esg"
          :companies="filteredCompanies"
          :ratings="allRatings"
          :sectors="sectors"
          @open-rating="onOpenRating"
          @add="onAddRating" />
      </div>
    </template>
  </div>
</template>

<style scoped>
.rt-page {
  padding: 18px 22px 28px;
  max-width: 1900px;
  margin: 0 auto;
  display: flex;
  flex-direction: column;
  gap: 14px;
}

/* Topbar */
.rt-topbar {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
}
.rt-eyebrow {
  font-size: 10px; font-weight: 500; letter-spacing: 0.08em;
  text-transform: uppercase; color: var(--t3, #64748B);
  margin-bottom: 4px;
}
.rt-title {
  font-size: 22px; font-weight: 500; letter-spacing: -0.01em;
  margin: 0 0 4px; color: var(--t1, #1E2A4A);
  animation: ratFadeSlideIn .35s ease both;
}
.rt-sub {
  font-size: 13px; color: var(--t1, #1E2A4A); font-weight: 500;
  display: inline-flex; align-items: baseline; gap: 4px;
}
.rt-sub-num { font-variant-numeric: tabular-nums; }
.rt-sub-word { color: var(--t3, #64748B); margin-left: 2px; }
.rt-sub-sec { color: var(--t3, #64748B); margin-left: 6px; }
.rt-sub-sec-label { color: #7F77DD; font-weight: 500; }

/* Chips */
.rt-chips {
  display: flex; gap: 6px; flex-wrap: wrap;
  animation: ratFadeSlideIn .35s ease 80ms both;
}
.rt-chip {
  display: inline-flex; align-items: center; gap: 6px;
  padding: 5px 11px;
  background: rgba(255, 255, 255, 0.6);
  border: 1px solid var(--border, #E2E8F0);
  border-radius: 11px;
  font-size: 12px; font-weight: 500;
  color: var(--t1, #1E2A4A);
  cursor: pointer;
  transition: all .15s cubic-bezier(.34, 1.2, .64, 1);
  user-select: none;
}
.rt-chip:hover {
  background: rgba(127, 119, 221, .08);
  border-color: var(--chip-c, #7F77DD);
  transform: translateY(-1px);
}
.rt-chip.is-active {
  background: var(--chip-c, #7F77DD);
  color: #fff;
  border-color: var(--chip-c, #7F77DD);
  box-shadow: 0 4px 12px rgba(127, 119, 221, .25);
}
.rt-chip.is-active .rt-chip-dot { background: #fff !important; }
.rt-chip.is-active .rt-chip-cnt {
  background: rgba(255, 255, 255, 0.25); color: #fff;
}
.rt-chip-dot {
  width: 7px; height: 7px; border-radius: 50%;
  flex-shrink: 0;
}
.rt-chip-cnt {
  font-size: 10.5px; font-weight: 600;
  background: rgba(127, 119, 221, .12);
  color: var(--t3, #64748B);
  padding: 1px 7px;
  border-radius: 8px;
  font-variant-numeric: tabular-nums;
  min-width: 20px;
  text-align: center;
}

/* State (loading / error) */
.rt-state {
  padding: 32px; text-align: center;
  color: var(--t3, #64748B); font-size: 13px;
  background: var(--bg2, #fff);
  border: 1px solid var(--border, #E2E8F0);
  border-radius: 12px;
}
.rt-state-err { color: #993D3D; }
.rt-state-btn {
  margin-left: 12px;
  border: 1px solid #993D3D; background: rgba(153,61,61,.05);
  color: #993D3D; padding: 4px 12px;
  border-radius: 8px; font-size: 12px; cursor: pointer;
  transition: background .12s;
}
.rt-state-btn:hover { background: rgba(153,61,61,.12); }

/* Sections */
.rt-section { animation: ratFadeSlideIn .4s ease 120ms both; }

.rt-mid-row {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 12px;
  animation: ratFadeSlideIn .4s ease 200ms both;
}
.rt-mid-left {
  display: flex;
  flex-direction: column;
  gap: 12px;
  min-height: 0;
}
.rt-mid-right {
  display: flex;
  min-height: 0;
}
@media (max-width: 1100px) {
  .rt-mid-row { grid-template-columns: 1fr; }
}

.rt-bot-row {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 12px;
  animation: ratFadeSlideIn .4s ease 280ms both;
}
@media (max-width: 1280px) {
  .rt-bot-row { grid-template-columns: 1fr; }
}
</style>
