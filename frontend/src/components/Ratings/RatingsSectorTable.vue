<script setup lang="ts">
// Sector-grouped rating table. Two instances on the page:
//   • kind="credit" → Fitch / S&P / Moody's
//   • kind="esg"    → Sustainable Fitch / S&P ESG / CDP
//
// For each sector group:
//   • coloured sector header strip
//   • one row per company in that sector (sorted by sort_order)
//   • each cell either:
//     ─ shows rating + outlook + date + ★ if sector leader + ▲ if recent
//     ─ shows dashed "+" stub → click to add via emit('add')
//
// Ports legacy crRows / esgRows generation (index.html L53984-54008).

import { computed } from "vue";
import type { AgencyRatingBrief } from "@/api/ratings";
import type { CompanyListItem, SectorBrief } from "@/api/companies";
import CompanyAvatar from "@/components/CompanyAvatar.vue";
import {
  CREDIT_AGENCIES, ESG_AGENCIES,
  badgeStyle, outlookBadge,
  ratingRank, isRecentlyUpdated, formatDate,
  buildRatingIndex, getRating,
  displayRating, coSector, sectorColor,
} from "./ratingsHelpers";
import { useI18n } from "@/composables/useI18n";
import { i18nKey } from "@/locale/keys";
import { companyDisplayName, sectorDisplayName } from "@/utils/displayNames";

const { t } = useI18n();


const props = defineProps<{
  kind: "credit" | "esg";
  companies: CompanyListItem[];
  ratings: AgencyRatingBrief[];
  sectors: SectorBrief[];
}>();

const emit = defineEmits<{
  (e: "openRating", companyId: string, agency: string): void;
  (e: "add", companyId: string, agency: string): void;
}>();

const ratingIndex = computed(() => buildRatingIndex(props.ratings));

const agencies = computed(() =>
  props.kind === "credit" ? [...CREDIT_AGENCIES] : [...ESG_AGENCIES],
);

const accent = computed(() => props.kind === "credit" ? "#378ADD" : "#1D9E75");
const titleText = computed(() => props.kind === "credit" ? i18nKey("Кредитный рейтинг") : i18nKey("ESG рейтинг"));

// Group companies by sector (using sectors[] from API as canonical list)
interface SectorGroup {
  sector: SectorBrief;
  companies: CompanyListItem[];
  color: string;
}

const groups = computed<SectorGroup[]>(() => {
  // Map sector code (lowercase) → companies array
  const byCode: Record<string, CompanyListItem[]> = {};
  for (const c of props.companies) {
    const code = coSector(c);
    if (!byCode[code]) byCode[code] = [];
    byCode[code].push(c);
  }

  // Iterate sectors in their declared sort order
  const sorted = [...props.sectors].sort((a, b) =>
    (a.sort_order || 0) - (b.sort_order || 0),
  );

  const out: SectorGroup[] = [];
  for (const sec of sorted) {
    const code = String(sec.code).toLowerCase();
    const cs = byCode[code] || [];
    if (!cs.length) continue;
    out.push({
      sector: sec,
      companies: cs,
      color: sectorColor(sec),
    });
  }

  // Companies whose sector_code doesn't match any known sector → "Другое"
  const knownCodes = new Set(sorted.map(s => String(s.code).toLowerCase()));
  const orphaned: CompanyListItem[] = [];
  for (const c of props.companies) {
    if (!knownCodes.has(coSector(c))) orphaned.push(c);
  }
  if (orphaned.length) {
    out.push({
      sector: {
        id: "_orphan",
        code: "_orphan",
      name_ru: t("Другое"),
        name_uz: null, name_en: null,
        color_hex: "#64748B",
        sort_order: 9999,
      } as SectorBrief,
      companies: orphaned,
      color: "#64748B",
    });
  }

  return out;
});

// Best in sector for the leader ★
function bestInSector(secCompanies: CompanyListItem[], agency: string): string {
  if (props.kind === "credit") {
    let bestRank = -1, bestId = "";
    for (const c of secCompanies) {
      const r = getRating(ratingIndex.value, c.id, agency);
      if (r) {
        const rk = ratingRank(r.rating);
        if (rk > bestRank) { bestRank = rk; bestId = c.id; }
      }
    }
    return bestRank > 0 ? bestId : "";
  }
  // ESG: compare scores (higher = better for S&P ESG and Sust. Fitch in 0-100 scale; CDP A>B>C)
  let bestVal = -1, bestId = "";
  for (const c of secCompanies) {
    const r = getRating(ratingIndex.value, c.id, agency);
    if (!r) continue;
    let val = -1;
    if (agency === "CDP") {
      const ch = String(r.rating || "D")[0];
      val = "DCBA".indexOf(ch) * 10;
    } else {
      val = parseInt(r.score || "0");
      if (isNaN(val)) val = -1;
    }
    if (val > bestVal) { bestVal = val; bestId = c.id; }
  }
  return bestVal > 0 ? bestId : "";
}

// Per-row derived data
interface CellData {
  rating: AgencyRatingBrief | null;
  display: string;
  bs: ReturnType<typeof badgeStyle>;
  olk: ReturnType<typeof outlookBadge>;
  isLeader: boolean;
  isNew: boolean;
}

function cell(co: CompanyListItem, agency: string, leaders: Record<string, string>): CellData {
  const r = getRating(ratingIndex.value, co.id, agency);
  if (!r) {
    return {
      rating: null, display: "", bs: { bg: "", fg: "" },
      olk: null, isLeader: false, isNew: false,
    };
  }
  return {
    rating: r,
    display: displayRating(r, agency),
    bs: badgeStyle(agency, r.rating),
    olk: outlookBadge(r.outlook),
    isLeader: leaders[agency] === co.id,
    isNew: isRecentlyUpdated(r),
  };
}

function leadersOf(secCompanies: CompanyListItem[]): Record<string, string> {
  const out: Record<string, string> = {};
  for (const ag of agencies.value) {
    out[ag] = bestInSector(secCompanies, ag);
  }
  return out;
}

function hasAnyAgency(co: CompanyListItem): boolean {
  return agencies.value.some(ag => !!getRating(ratingIndex.value, co.id, ag));
}

function onCellClick(co: CompanyListItem, ag: string, hasRating: boolean) {
  if (hasRating) emit("openRating", co.id, ag);
  else emit("add", co.id, ag);
}

// Legend rows depend on kind
const legend = computed(() => {
  if (props.kind === "credit") {
    return [
      { bg: "#DCFCE7",                fg: "#1D9E75", label: "A / AA" },
      { bg: "rgba(55,138,221,.10)",   fg: "#378ADD", label: "BBB" },
      { bg: "#FEF9C3",                fg: "#D97706", label: "BB / B" },
      { bg: "#FEE2E2",                fg: "#EF4444", label: "CCC / D" },
    ];
  }
  return [
    { bg: "#DCFCE7", fg: "#1D9E75", label: i18nKey("Лидер (1-2 / 60+ / A)") },
    { bg: "#FEF9C3", fg: "#D97706", label: i18nKey("Средний (3 / 40-59 / B)") },
    { bg: "#FEE2E2", fg: "#EF4444", label: i18nKey("Слабый (4-5 / <40 / C-D)") },
  ];
});
</script>

<template>
  <div class="rst-card">
    <!-- Header strip: title + column labels -->
    <div class="rst-head">
      <div class="rst-title-row">
        <span class="rst-title" :style="{ color: accent }">{{ titleText }}</span>
      </div>
      <div class="rst-col-row">
        <div class="rst-col rst-col-co">{{ t('Компания') }}</div>
        <div v-for="ag in agencies" :key="ag" class="rst-col">
          {{ ag === "S&P" ? "S&amp;P" : ag === "Sustainable Fitch" ? "Sust. Fitch" : ag }}
        </div>
      </div>
    </div>

    <!-- Sector groups -->
    <div class="rst-body">
      <template v-for="g in groups" :key="g.sector.code">
        <!-- Sector header strip -->
        <div class="rst-sec-head uza-side-stripe uza-side-stripe-tight"
             :style="{
               background: g.color + '0E',
               '--stripe-color': g.color,
               borderBottomColor: g.color + '22',
             }">
          <span class="rst-sec-name" :style="{ color: g.color }">{{ sectorDisplayName(g.sector) }}</span>
          <span class="rst-sec-cnt">{{ g.companies.length }}</span>
        </div>

        <!-- Rows in this sector -->
        <template v-for="(co, idx) in g.companies" :key="co.id">
          <div class="rst-row uza-side-stripe uza-side-stripe-tight"
               :class="{ 'rst-row-empty': !hasAnyAgency(co) }"
               :style="{
                 '--stripe-color': `${g.color}1F`,
                 animationDelay: (idx * 25) + 'ms',
               }">
            <!-- Company name cell -->
            <div class="rst-cell-co">
              <CompanyAvatar :name="companyDisplayName(co)" :color="g.color" :size="20" />
              <span class="rst-co-name" :class="{ 'rst-co-empty': !hasAnyAgency(co) }">
                {{ companyDisplayName(co) }}
              </span>
            </div>

            <!-- Rating cells -->
            <template v-for="ag in agencies" :key="ag">
              <div class="rst-cell"
                   @click.stop="(() => {
                     const c = cell(co, ag, leadersOf(g.companies));
                     onCellClick(co, ag, !!c.rating);
                   })()">
                <template v-for="c in [cell(co, ag, leadersOf(g.companies))]" :key="0">
                  <template v-if="c.rating">
                    <div class="rst-cell-content">
                      <div class="rst-badge-row">
                        <span class="rst-badge"
                              :style="{ background: c.bs.bg, color: c.bs.fg }">
                          {{ c.display }}
                        </span>
                        <span v-if="c.isNew" class="rst-recent" :title="t('Недавно обновлено')">▲</span>
                      </div>
                      <div class="rst-meta-row">
                        <span v-if="c.rating.rating_date || c.rating.rating_date_text" class="rst-date">
                          {{ formatDate(c.rating.rating_date) || c.rating.rating_date_text }}
                        </span>
                        <span v-if="c.olk"
                              class="rst-olk"
                              :title="t(c.olk.label)"
                              :style="{ color: c.olk.fg, background: c.olk.bg }">
                          {{ c.olk.symbol }}
                        </span>
                        <a v-if="c.rating.report_url"
                           :href="c.rating.report_url"
                           target="_blank"
                           rel="noopener"
                           class="rst-link"
                           :title="t('Открыть отчёт')"
                           @click.stop>
                          ↗
                        </a>
                      </div>
                      <span v-if="c.isLeader" class="rst-leader" :title="t('Лидер сектора')">★</span>
                    </div>
                  </template>
                  <template v-else>
                    <div class="rst-empty-circle" :title="t('Добавить рейтинг')">+</div>
                  </template>
                </template>
              </div>
            </template>
          </div>
        </template>
      </template>
    </div>

    <!-- Legend -->
    <div class="rst-legend">
      <span v-for="lg in legend" :key="lg.label" class="rst-leg-item">
        <span class="rst-leg-swatch" :style="{ background: lg.bg }" />
        <span class="rst-leg-text" :style="{ color: lg.fg }">{{ t(lg.label) }}</span>
      </span>
      <span class="rst-leg-item rst-leg-mut">
        <span class="rst-leg-empty-circle" />
        <span>{{ t('Нет') }}</span>
      </span>
      <span class="rst-leg-item rst-leg-mut">
        <span class="rst-leg-star">★</span>
        <span>{{ t('Лидер сектора') }}</span>
      </span>
      <span class="rst-leg-item" style="color:#1D9E75">
        <span style="font-size:9px">▲</span>
        <span>{{ t('обновлён в текущем году') }}</span>
      </span>
    </div>
  </div>
</template>

<style scoped>
.rst-card {
  background: var(--bg2, #fff);
  border: 1px solid var(--border, var(--border-input));
  border-radius: 12px;
  display: flex;
  flex-direction: column;
  min-height: 0;
  overflow: hidden;
  animation: ratFadeSlideIn .35s ease both;
}

/* Header */
.rst-head {
  position: sticky; top: 0; z-index: 10;
  background: var(--bg2, #fff);
  border-bottom: 1px solid var(--border, var(--border-input));
  flex-shrink: 0;
}
.rst-title-row {
  padding: 7px 14px 3px;
  display: flex; align-items: center; justify-content: space-between;
}
.rst-title {
  font-size: 11px; font-weight: 700;
  text-transform: uppercase; letter-spacing: 0.06em;
}
.rst-col-row {
  display: grid;
  grid-template-columns: minmax(120px, 3fr) 1fr 1fr 1fr;
  padding: 2px 14px 5px;
}
.rst-col {
  font-size: 10.5px; font-weight: 600;
  color: var(--t3, var(--t3));
  text-transform: uppercase; letter-spacing: 0.06em;
  text-align: center;
  padding: 3px 4px;
  white-space: nowrap;
}
.rst-col-co { text-align: left; }

/* Body */
.rst-body { overflow-y: auto; scrollbar-width: thin; flex: 1; }

/* Sector group header */
.rst-sec-head {
  padding: 4px 12px 4px 18px;
  border-bottom: 0.5px solid;
  display: flex; align-items: center; justify-content: space-between;
  animation: ratFadeSlideIn .25s ease both;
}
.rst-sec-name {
  font-size: 10.5px; font-weight: 700;
  text-transform: uppercase; letter-spacing: 0.06em;
}
.rst-sec-cnt {
  font-size: 10px; color: var(--t3, var(--t3)); font-weight: 500;
  background: rgba(255,255,255,.8);
  border-radius: 8px;
  padding: 1px 8px;
}

/* Row */
.rst-row {
  display: grid;
  grid-template-columns: minmax(120px, 3fr) 1fr 1fr 1fr;
  padding: 4px 12px 4px 18px;
  border-bottom: 0.5px solid var(--border, var(--border-input));
  align-items: center;
  cursor: default;
  transition: background .12s;
  animation: ratFadeSlideIn .22s ease both;
}
.rst-row:hover { background: rgba(127, 119, 221, .035); }
.rst-row-empty { background: rgba(254, 226, 226, 0.04); }
.rst-row-empty:hover { background: rgba(254, 226, 226, 0.08); }

.rst-cell-co {
  display: flex; align-items: center; gap: 8px;
  overflow: hidden; padding-right: 6px;
  min-width: 0;
}
.rst-co-stripe { width: 3px; height: 18px; border-radius: 1px; flex-shrink: 0; }
.rst-co-name {
  font-size: 12px; font-weight: 500;
  color: var(--t1, #1E2A4A);
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}
.rst-co-empty { color: #EF4444; }

.rst-cell {
  display: flex; align-items: center; justify-content: center;
  min-height: 38px;
  cursor: pointer;
  position: relative;
}
.rst-cell-content {
  display: flex; flex-direction: column; align-items: center;
  gap: 2px;
  position: relative;
}
.rst-badge-row { display: inline-flex; align-items: center; gap: 5px; }
.rst-badge {
  font-size: 12px; font-weight: 700;
  padding: 2px 7px; border-radius: 5px;
  white-space: nowrap;
  font-variant-numeric: tabular-nums;
  transition: box-shadow .15s;
}
.rst-cell:hover .rst-badge { box-shadow: 0 0 0 2px rgba(127, 119, 221, 0.25); }
.rst-recent {
  font-size: 9px; color: var(--green); line-height: 1;
}
.rst-meta-row {
  display: flex; align-items: center; gap: 4px;
}
.rst-date {
  font-size: 10px; color: var(--t3, var(--t3));
  white-space: nowrap;
  font-variant-numeric: tabular-nums;
}
.rst-olk {
  display: inline-flex; align-items: center; justify-content: center;
  width: 13px; height: 13px;
  border-radius: 3px;
  font-size: 10px; font-weight: 700; line-height: 1;
}
.rst-link {
  color: var(--t3, var(--t3)); text-decoration: none;
  font-size: 10px; line-height: 1;
  padding: 0 2px;
  transition: color .12s;
}
.rst-link:hover { color: var(--blue); }
.rst-leader {
  position: absolute;
  top: -2px; right: calc(50% - 26px);
  font-size: 11px; color: #EAB308; line-height: 1;
  filter: drop-shadow(0 0 2px rgba(234, 179, 8, .35));
}

.rst-empty-circle {
  width: 16px; height: 16px;
  border-radius: 50%;
  border: 1.5px dashed #CBD5E1;
  display: flex; align-items: center; justify-content: center;
  font-size: 8px; color: #CBD5E1; font-weight: 700;
  transition: border-color .15s, color .15s;
}
.rst-cell:hover .rst-empty-circle {
  border-color: #7F77DD; color: #7F77DD;
}

/* Legend */
.rst-legend {
  padding: 7px 14px;
  border-top: 0.5px solid var(--border, var(--border-input));
  display: flex; gap: 12px; flex-wrap: wrap;
  background: var(--bg2, #fff);
  flex-shrink: 0;
}
.rst-leg-item {
  display: flex; align-items: center; gap: 4px;
  font-size: 10px;
}
.rst-leg-mut { color: var(--t3, var(--t3)); }
.rst-leg-swatch {
  width: 12px; height: 8px; border-radius: 2px;
  display: inline-block;
}
.rst-leg-text { font-weight: 600; }
.rst-leg-empty-circle {
  width: 12px; height: 12px;
  border-radius: 50%;
  border: 1.5px dashed #CBD5E1;
  display: inline-block;
}
.rst-leg-star { color: #EAB308; font-size: 11px; line-height: 1; }
</style>
