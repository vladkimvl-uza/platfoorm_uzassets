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
import { useSavedFilter } from "@/composables/useSavedFilter";
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
import RatingEditModal       from "@/components/Ratings/RatingEditModal.vue";

// ─── State ────────────────────────────────────────────────────────────────
const allCompanies = ref<CompanyListItem[]>([]);
const allRatings   = ref<AgencyRatingBrief[]>([]);
const sectors      = ref<SectorBrief[]>([]);
const loading      = ref(true);
const errorMsg     = ref<string | null>(null);

const sectorFilter = useSavedFilter<string>("ratings.sectorFilter", "");
const sectorMenuOpen = ref<boolean>(false);

function closeMenus() { sectorMenuOpen.value = false; }
function setSector(code: string) {
  sectorFilter.value = code;
  sectorMenuOpen.value = false;
}

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

// ─── Edit modal ──────────────────────────────────────────────────────
const editModal = ref<{
  companyId: string;
  companyName: string;
  agency: string;
  existing: AgencyRatingBrief | null;
} | null>(null);

function openEditModal(companyId: string, agency: string) {
  const co = allCompanies.value.find(c => c.id === companyId);
  if (!co) return;
  // Find existing rating for this (company, agency) pair, if any
  const existing = allRatings.value.find(
    r => r.company_id === companyId && r.agency === agency,
  ) || null;
  editModal.value = {
    companyId,
    companyName: co.name_ru || co.code || "—",
    agency,
    existing,
  };
}

function onOpenRating(companyId: string, agency: string) {
  openEditModal(companyId, agency);
}
function onAddRating(companyId: string, agency: string) {
  openEditModal(companyId, agency);
}
async function onModalSaved() {
  // Reload data to reflect changes
  await load();
}
function onShowAllChanges() {
  // TODO: full timeline modal (Phase 2 — not blocking)
  console.log("showAllRatingChanges → modal stub");
}
</script>

<template>
  <div class="rt-page" @click="closeMenus()">
    <div class="rt-topbar" @click.stop>
      <div class="rt-tb-l">
        <h1 class="rt-tb-title">Рейтинги компаний портфеля</h1>
        <div class="rt-tb-sub" v-if="!loading">
          <span><b>{{ totalCount }}</b> {{ pluralCompanies(totalCount) }}</span>
          <span v-if="sectorFilter" class="rt-dot">·</span>
          <span v-if="sectorFilter">сектор: <b>{{ activeSectorLabel() }}</b></span>
        </div>
      </div>
      <div class="rt-tb-r">
        <div class="rt-badge-wrap" @click.stop>
          <button class="rt-badge" @click="sectorMenuOpen = !sectorMenuOpen" title="Фильтр по сектору">
            <span
              class="rt-sec-icon"
              :style="{
                background: (sortedSectors.find(s => String(s.code).toLowerCase() === sectorFilter)?.color_hex || '#FAC775') + '33',
                borderColor: sortedSectors.find(s => String(s.code).toLowerCase() === sectorFilter)?.color_hex || '#FAC775',
              }"
            ></span>
            <span :style="{ color: sortedSectors.find(s => String(s.code).toLowerCase() === sectorFilter)?.color_hex || '#FAC775' }">
              {{ sectorFilter ? activeSectorLabel() : 'Все секторы' }}
            </span>
            <svg
              class="rt-chev"
              :class="{ open: sectorMenuOpen }"
              width="10"
              height="10"
              viewBox="0 0 10 10"
              fill="none"
              :stroke="sortedSectors.find(s => String(s.code).toLowerCase() === sectorFilter)?.color_hex || '#FAC775'"
              stroke-width="1.6"
            >
              <path d="M2 4l3 3 3-3"/>
            </svg>
          </button>
          <div v-if="sectorMenuOpen" class="rt-dd">
            <div class="rt-dd-item" :class="{ active: !sectorFilter }" @click="setSector('')">
              <span class="rt-dd-meta">Все секторы</span>
              <span class="rt-dd-count">{{ allCompanies.length }}</span>
            </div>
            <div
              v-for="s in sortedSectors"
              :key="s.code"
              class="rt-dd-item"
              :class="{ active: sectorFilter === String(s.code).toLowerCase() }"
              @click="setSector(String(s.code).toLowerCase())"
            >
              <span class="rt-dd-dot" :style="{ background: s.color_hex || '#7F77DD' }"></span>
              <span class="rt-dd-meta">{{ s.name_ru }}</span>
              <span class="rt-dd-count">{{ sectorCounts[String(s.code).toLowerCase()] || 0 }}</span>
            </div>
          </div>
        </div>
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

    <!-- Edit / Create / Delete modal -->
    <RatingEditModal
      v-if="editModal"
      :company-id="editModal.companyId"
      :company-name="editModal.companyName"
      :agency="editModal.agency"
      :existing="editModal.existing"
      @close="editModal = null"
      @saved="onModalSaved"
    />
  </div>
</template>

<style scoped>
.rt-page {
  background: var(--bg, #F4F3F9);
  min-height: 100%;
  display: flex;
  flex-direction: column;
}

.rt-topbar {
  background: linear-gradient(95deg, #1E2A4A 0%, #2D3760 60%, #4B477E 100%);
  padding: 12px 22px;
  display: flex; align-items: center; justify-content: space-between;
  gap: 14px; flex-wrap: wrap;
}
.rt-tb-l { display: flex; flex-direction: column; gap: 2px; min-width: 0; }
.rt-tb-title { font-size: 16px; font-weight: 600; color: #fff; margin: 0; }
.rt-tb-sub {
  font-size: 11px; color: rgba(255, 255, 255, .55);
  display: flex; align-items: center; gap: 6px;
}
.rt-tb-sub b { color: rgba(255, 255, 255, .95); font-weight: 600; }
.rt-dot { opacity: .4; }
.rt-tb-r { display: flex; align-items: center; gap: 8px; }

.rt-badge-wrap { position: relative; }
.rt-badge {
  display: flex; align-items: center; gap: 6px;
  background: rgba(255, 255, 255, .08);
  border: 1px solid rgba(255, 255, 255, .15);
  color: #fff;
  padding: 5px 11px;
  border-radius: 8px;
  font-size: 12px; font-weight: 500;
  cursor: pointer;
  font-family: inherit;
  transition: background .12s;
}
.rt-badge:hover { background: rgba(255, 255, 255, .15); }
.rt-sec-icon {
  width: 12px; height: 12px;
  border-radius: 3px;
  border: 1px solid;
  flex-shrink: 0;
}
.rt-chev { transition: transform .15s; flex-shrink: 0; }
.rt-chev.open { transform: rotate(180deg); }
.rt-dd {
  position: absolute; top: calc(100% + 4px); right: 0;
  background: #fff;
  border: 1px solid rgba(0, 0, 0, .08);
  border-radius: 8px;
  box-shadow: 0 12px 32px rgba(15, 23, 60, .14);
  min-width: 220px;
  padding: 4px;
  z-index: 100;
  animation: ratFadeSlideIn .15s ease;
}
.rt-dd-item {
  padding: 7px 10px;
  border-radius: 5px;
  font-size: 12px;
  color: #1E2A4A;
  cursor: pointer;
  display: flex; align-items: center; gap: 6px;
  transition: background .1s;
}
.rt-dd-item:hover { background: #F4F3F9; }
.rt-dd-item.active { background: rgba(127, 119, 221, .12); color: #534AB7; font-weight: 600; }
.rt-dd-dot { width: 8px; height: 8px; border-radius: 2px; flex-shrink: 0; }
.rt-dd-meta { flex: 1; }
.rt-dd-count {
  font-size: 10.5px; font-weight: 600;
  background: rgba(127, 119, 221, .12);
  color: #5F5E5A;
  padding: 1px 7px;
  border-radius: 8px;
  font-feature-settings: 'tnum';
  min-width: 22px;
  text-align: center;
}

/* Body content area (sections live here) */
.rt-page > *:not(.rt-topbar) {
  margin-left: 22px;
  margin-right: 22px;
}
.rt-page > .rt-state:first-of-type,
.rt-page > .rt-section:first-of-type {
  margin-top: 16px;
}
.rt-page > .rt-bot-row:last-of-type {
  margin-bottom: 28px;
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
