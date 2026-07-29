<script setup lang="ts">
// "Последние изменения" panel — split: 8 latest credit changes + 8 latest ESG.
// Sorted by rating_date DESC. ▲ marker for current/previous year ratings.
// Ports legacy timeline block (index.html L53949-53977).

import { computed } from "vue";
import type { AgencyRatingBrief } from "@/api/ratings";
import type { CompanyListItem, SectorBrief } from "@/api/companies";
import {
  CREDIT_AGENCIES, ESG_AGENCIES,
  badgeStyle, outlookBadge,
  isRecentlyUpdated, formatDate, dateSortKey,
  displayRating, coSector, sectorColor,
} from "./ratingsHelpers";
import { useI18n } from "@/composables/useI18n";
const { t } = useI18n();


const props = defineProps<{
  companies: CompanyListItem[];
  ratings: AgencyRatingBrief[];
  sectors: SectorBrief[];
}>();

const emit = defineEmits<{
  (e: "openRating", companyId: string, agency: string): void;
  (e: "showAll"): void;
}>();

const sectorByCode = computed(() => {
  const m: Record<string, SectorBrief> = {};
  for (const s of props.sectors) m[String(s.code).toLowerCase()] = s;
  return m;
});

const companyById = computed(() => {
  const m: Record<string, CompanyListItem> = {};
  for (const c of props.companies) m[c.id] = c;
  return m;
});

interface Event {
  rating: AgencyRatingBrief;
  company: CompanyListItem | null;
  agency: string;
  display: string;
  isNew: boolean;
  sortKey: string;
  sectorClr: string;
  bs: ReturnType<typeof badgeStyle>;
  olk: ReturnType<typeof outlookBadge>;
}

function buildEvent(r: AgencyRatingBrief): Event {
  const company = companyById.value[r.company_id] || null;
  const sec = company ? sectorByCode.value[coSector(company)] : null;
  return {
    rating: r,
    company,
    agency: r.agency,
    display: displayRating(r, r.agency),
    isNew: isRecentlyUpdated(r),
    sortKey: dateSortKey(r.rating_date || r.rating_date_text),
    sectorClr: company?.sector_color || sectorColor(sec),
    bs: badgeStyle(r.agency, r.rating),
    olk: outlookBadge(r.outlook),
  };
}

const creditEvents = computed<Event[]>(() => {
  return props.ratings
    .filter(r => CREDIT_AGENCIES.includes(r.agency as any) && (r.rating_date || r.rating_date_text))
    .map(buildEvent)
    .sort((a, b) => b.sortKey.localeCompare(a.sortKey));
});

const esgEvents = computed<Event[]>(() => {
  return props.ratings
    .filter(r => ESG_AGENCIES.includes(r.agency as any) && (r.rating_date || r.rating_date_text))
    .map(buildEvent)
    .sort((a, b) => b.sortKey.localeCompare(a.sortKey));
});

const totalEvents = computed(() => creditEvents.value.length + esgEvents.value.length);
const hasShowAll = computed(() => totalEvents.value > 16);

const credSlice = computed(() => creditEvents.value.slice(0, 8));
const esgSlice  = computed(() => esgEvents.value.slice(0, 8));
</script>

<template>
  <div class="rrc-card">
    <div class="rrc-head">
      <span>{{ t('Последние изменения') }}</span>
      <span v-if="hasShowAll" class="rrc-all" @click="emit('showAll')">
        {{ t('Показать все (') }}{{ totalEvents }}) →
      </span>
    </div>
    <div class="rrc-body">
      <!-- Credit -->
      <div class="rrc-col">
        <div class="rrc-col-head" style="color:#378ADD">
          <span>{{ t('Кредитный рейтинг') }}</span>
          <span class="rrc-cnt">{{ creditEvents.length }}</span>
        </div>
        <div class="rrc-list">
          <div v-for="(e, i) in credSlice"
               :key="e.rating.id"
               class="rrc-row"
               :style="{ animationDelay: (i * 30) + 'ms' }"
               @click="emit('openRating', e.rating.company_id, e.agency)">
            <div class="rrc-stripe" :style="{ background: e.sectorClr }" />
            <div class="rrc-info">
              <div class="rrc-name">{{ e.company?.name_short || e.company?.name_ru || '—' }}</div>
              <div class="rrc-ag">{{ e.agency }}</div>
            </div>
            <div class="rrc-badge-col">
              <span class="rrc-badge"
                    :style="{ background: e.bs.bg, color: e.bs.fg }">
                {{ e.display }}
              </span>
              <span v-if="e.olk"
                    class="rrc-olk"
                    :title="e.olk.label"
                    :style="{ color: e.olk.fg, background: e.olk.bg }">
                {{ e.olk.symbol }}
              </span>
            </div>
            <span class="rrc-date">
              {{ formatDate(e.rating.rating_date) || e.rating.rating_date_text }}
            </span>
            <span v-if="e.isNew" class="rrc-recent">▲</span>
          </div>
          <div v-if="!credSlice.length" class="rrc-empty">{{ t('Нет данных') }}</div>
        </div>
      </div>

      <!-- ESG -->
      <div class="rrc-col rrc-col-r">
        <div class="rrc-col-head" style="color:#1D9E75">
          <span>{{ t('ESG рейтинг') }}</span>
          <span class="rrc-cnt">{{ esgEvents.length }}</span>
        </div>
        <div class="rrc-list">
          <div v-for="(e, i) in esgSlice"
               :key="e.rating.id"
               class="rrc-row"
               :style="{ animationDelay: (i * 30) + 'ms' }"
               @click="emit('openRating', e.rating.company_id, e.agency)">
            <div class="rrc-stripe" :style="{ background: e.sectorClr }" />
            <div class="rrc-info">
              <div class="rrc-name">{{ e.company?.name_short || e.company?.name_ru || '—' }}</div>
              <div class="rrc-ag">{{ e.agency }}</div>
            </div>
            <div class="rrc-badge-col">
              <span class="rrc-badge"
                    :style="{ background: e.bs.bg, color: e.bs.fg }">
                {{ e.display }}
              </span>
              <span v-if="e.olk"
                    class="rrc-olk"
                    :title="e.olk.label"
                    :style="{ color: e.olk.fg, background: e.olk.bg }">
                {{ e.olk.symbol }}
              </span>
            </div>
            <span class="rrc-date">
              {{ formatDate(e.rating.rating_date) || e.rating.rating_date_text }}
            </span>
            <span v-if="e.isNew" class="rrc-recent">▲</span>
          </div>
          <div v-if="!esgSlice.length" class="rrc-empty">{{ t('Нет данных') }}</div>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.rrc-card {
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
.rrc-head {
  font-size: 12px; font-weight: 600; color: var(--t1, #1E2A4A);
  padding: 9px 14px;
  border-bottom: 0.5px solid var(--border, var(--border-input));
  flex-shrink: 0;
  display: flex; align-items: center; justify-content: space-between;
}
.rrc-all {
  cursor: pointer; font-size: 11px; color: var(--blue); font-weight: 500;
  transition: color .12s;
}
.rrc-all:hover { color: #2563EB; }

.rrc-body { display: grid; grid-template-columns: 1fr 1fr; flex: 1; min-height: 0; }
.rrc-col {
  display: flex; flex-direction: column;
  min-height: 0;
}
.rrc-col-r { border-left: 0.5px solid var(--border, var(--border-input)); }

.rrc-col-head {
  font-size: 11px; font-weight: 600;
  text-transform: uppercase; letter-spacing: 0.06em;
  padding: 8px 12px;
  border-bottom: 0.5px solid var(--border, var(--border-input));
  display: flex; justify-content: space-between; align-items: center;
}
.rrc-cnt {
  color: var(--t3, var(--t3)); font-weight: 400; font-size: 10px;
}

.rrc-list { overflow-y: auto; scrollbar-width: thin; flex: 1; }

.rrc-row {
  display: flex; align-items: center; gap: 7px;
  padding: 6px 11px;
  border-bottom: 0.5px solid var(--border, var(--border-input));
  cursor: pointer;
  transition: background .12s;
  animation: ratFadeSlideIn .22s ease both;
}
.rrc-row:hover { background: rgba(127,119,221,.04); }
.rrc-row:last-child { border-bottom: none; }

.rrc-stripe { width: 3px; height: 28px; border-radius: 1px; flex-shrink: 0; }
.rrc-info { flex: 1; min-width: 0; }
.rrc-name {
  font-size: 11.5px; font-weight: 500; color: var(--t1, #1E2A4A);
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
}
.rrc-ag { font-size: 10px; color: var(--t3, var(--t3)); margin-top: 1px; }
.rrc-badge-col {
  display: flex; flex-direction: column; align-items: center; gap: 2px;
  flex-shrink: 0;
}
.rrc-badge {
  font-size: 11px; font-weight: 700;
  padding: 1px 6px; border-radius: 4px;
  white-space: nowrap;
  font-variant-numeric: tabular-nums;
}
.rrc-olk {
  display: inline-flex; align-items: center; justify-content: center;
  width: 13px; height: 13px;
  border-radius: 3px;
  font-size: 10px; font-weight: 700;
  line-height: 1;
}
.rrc-date {
  font-size: 10px; color: var(--t3, var(--t3));
  white-space: nowrap; min-width: 64px; text-align: right;
  font-variant-numeric: tabular-nums;
}
.rrc-recent { font-size: 9px; color: var(--green); flex-shrink: 0; }
.rrc-empty {
  padding: 14px; text-align: center;
  color: var(--t3, var(--t3)); font-size: 11px;
}
</style>
