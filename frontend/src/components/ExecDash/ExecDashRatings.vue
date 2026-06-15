<script setup lang="ts">
/**
 * ExecDashRatings — Row 2 левая половина.
 * 4 ring cards (FITCH/S&P/Moody's/ESG) + табличный список рейтингов компаний.
 * Pure SVG-кольца без внешних библиотек.
 */
import { computed, onMounted } from "vue";
import { useExecutiveDashboard } from "@/composables/useExecutiveDashboard";
import { useNumberTween } from "@/composables/useNumberTween";
import type { ExecRingCard, ExecRatingCell } from "@/api/executiveDashboard";
import { useCompaniesStore } from "@/stores/companies";
import ExecDashRingCard from "./ExecDashRingCard.vue";

// Pack 7.13: unified naming via store
const companies = useCompaniesStore();
onMounted(() => { void companies.ensureLoaded(); });

const exec = useExecutiveDashboard();

const ratings = computed(() => exec.data.value?.ratings || null);
const ringCards = computed<ExecRingCard[]>(() => ratings.value?.ring_cards || []);
const tableRows = computed(() => ratings.value?.rows || []);

// 2026-05-26: countup для header subtitle на смене года
const tOverallTotal = useNumberTween(() => Number(ratings.value?.overall_total) || 0, { duration: 900 });
const subTitle = computed(() => {
  const r = ratings.value;
  if (!r) return "Кредитный и ESG";
  return `Кредитный и ESG · ${Math.round(tOverallTotal.value)} компаний`;
});

const COLUMN_HEADERS = ["FITCH", "S&P", "MOODY'S", "SUST.F", "S&P ESG", "CDP"];

/** Цвет вертикальной полоски у названия компании = цвет её сектора. */
function stripeColor(row: { company_id?: string | null }): string {
  const co = row.company_id ? companies.findById(row.company_id) : undefined;
  const bySector = co?.sector_code ? companies.findSectorByCode(co.sector_code)?.color_hex : null;
  return (co?.sector_color || bySector || "#94A3B8") as string;
}

// Pack 7.31: column descriptors drive the rating-cell loop below.
// `kind` controls whether outlook is shown; `bg` returns the badge background.
type AgencyKey = "fitch" | "sp" | "moodys" | "sf" | "sp_esg" | "cdp";
interface ColDef {
  key: AgencyKey;
  kind: "credit" | "score";
  bg: (rating: string | null | undefined) => string;
}
const cols: ColDef[] = [
  { key: "fitch",  kind: "credit", bg: (r) => ratingBg(r) },
  { key: "sp",     kind: "credit", bg: (r) => ratingBg(r) },
  { key: "moodys", kind: "credit", bg: (r) => ratingBg(r) },
  { key: "sf",     kind: "score",  bg: () => "#FFF7E6" },
  { key: "sp_esg", kind: "score",  bg: () => "#F0F4FF" },
  { key: "cdp",    kind: "score",  bg: () => "#E8F5EE" },
];

function ringPct(card: ExecRingCard): number {
  if (!card.total) return 0;
  return Math.min(100, Math.round((card.rated_count / card.total) * 100));
}

function ratingBg(rating: string | null | undefined): string {
  if (!rating) return "transparent";
  const s = rating.toUpperCase();
  if (/^A/.test(s)) return "#FFF7E6";
  if (/^BB|^B/.test(s)) return "#FEF1D6";
  if (/^C|^D/.test(s)) return "#FCE4E4";
  return "#F5F4F9";
}

function outlookColor(outlook: string | null | undefined): string {
  if (!outlook) return "#888780";
  const s = outlook.toLowerCase();
  if (s.includes("стаб") || s.includes("stab")) return "#888780";
  if (s.includes("поз") || s.includes("pos")) return "#1D9E75";
  if (s.includes("нег") || s.includes("neg")) return "#E24B4A";
  return "#888780";
}

function isEmpty(cell: ExecRatingCell | null | undefined): boolean {
  if (!cell) return true;
  return !cell.rating && !cell.score;
}
</script>

<template>
  <div class="ed-card">
    <!-- Header -->
    <div class="ed-card-ttl">
      <span>Рейтинги компаний</span>
      <span class="sub">{{ subTitle }}</span>
    </div>

    <!-- 4 ring cards (2026-05-26: extracted to ExecDashRingCard for per-card useNumberTween) -->
    <div v-if="ringCards.length" class="rt-rings">
      <ExecDashRingCard
        v-for="(card, i) in ringCards"
        :key="card.label"
        :card="card"
        :stagger-delay="i * 80"
      />
    </div>

    <div v-else class="ed-empty">
      Рейтинги пока не загружены в систему
    </div>

    <!-- Таблица -->
    <div v-if="tableRows.length" class="rt-table">
      <div class="rt-hdr">
        <span class="rt-hdr-co">КОМПАНИЯ</span>
        <span v-for="h in COLUMN_HEADERS" :key="h" class="rt-hdr-cell">{{ h }}</span>
      </div>

      <div
        v-for="(row, i) in tableRows"
        :key="row.company_id"
        class="rt-row"
        :style="{ animationDelay: (i * 50) + 'ms' }"
      >
        <span class="rt-co-name" :style="{ '--stripe': stripeColor(row) }">{{ companies.getCompanyNameById(row.company_id) || row.name }}</span>

        <!-- 6 rating columns (Pack 7.31: rendered through cols[] + report_url link) -->
        <span v-for="col in cols" :key="col.key" class="rt-cell">
          <template v-if="!isEmpty(row[col.key])">
            <component
              :is="row[col.key]?.report_url ? 'a' : 'span'"
              :href="row[col.key]?.report_url || undefined"
              :target="row[col.key]?.report_url ? '_blank' : undefined"
              :rel="row[col.key]?.report_url ? 'noopener noreferrer' : undefined"
              class="rt-cell-link"
              :class="{ 'rt-cell-link--clickable': !!row[col.key]?.report_url }"
              :title="row[col.key]?.report_url
                ? `Открыть отчёт по рейтингу: ${row[col.key]?.rating || row[col.key]?.score}`
                : ''"
            >
              <span
                class="rt-badge"
                :style="{ background: col.bg(row[col.key]?.rating) }"
              >{{ col.kind === 'credit' ? row[col.key]?.rating : (row[col.key]?.score || row[col.key]?.rating) }}</span>
              <span
                v-if="col.kind === 'credit' && row[col.key]?.outlook"
                class="rt-outlook"
                :style="{ color: outlookColor(row[col.key]?.outlook) }"
              >{{ row[col.key]?.outlook }}</span>
              <span v-if="row[col.key]?.rated_at" class="rt-date">{{ row[col.key]?.rated_at }}</span>
              <svg
                v-if="row[col.key]?.report_url"
                class="rt-ext-ic"
                aria-hidden="true"
                viewBox="0 0 10 10"
                fill="none"
                stroke="currentColor"
                stroke-width="1.4"
                stroke-linecap="round"
                stroke-linejoin="round"
              >
                <path d="M3 2.5H2v5.5h5.5v-1"/>
                <path d="M5.5 1.5h3v3M5.5 4.5l3-3"/>
              </svg>
            </component>
          </template>
          <span v-else class="rt-empty">—</span>
        </span>
      </div>
    </div>
  </div>
</template>

<style scoped>
.ed-card {
  background: var(--bg1, #fff);
  border-radius: 12px;
  border: 1px solid rgba(0, 0, 0, 0.05);
  padding: 18px 20px 16px;
  box-shadow: 0 4px 14px rgba(15, 23, 60, 0.04);
  height: 100%;
  display: flex;
  flex-direction: column;
}

.ed-card-ttl {
  font-size: 11px;
  font-weight: 600;
  color: var(--t3, var(--t-muted));
  text-transform: uppercase;
  letter-spacing: 0.07em;
  margin: 0 0 14px;
  display: flex;
  justify-content: space-between;
  align-items: baseline;
  gap: 14px;
}
.ed-card-ttl .sub {
  font-size: 11.5px;
  color: #B4B2A9;
  font-weight: 500;
  text-transform: none;
  letter-spacing: 0;
}

.rt-rings {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 8px;
  margin-bottom: 14px;
}

.ed-ring-card {
  background: #F9F8FC;
  border-radius: 9px;
  padding: 8px 10px;
  display: flex;
  flex-direction: row;
  align-items: center;
  gap: 8px;
  border: 1px solid rgba(0, 0, 0, 0.03);
  animation: ringFadeIn 0.5s var(--ease-standard) both;
}

.ed-ring-sm { position: relative; width: 36px; height: 36px; flex-shrink: 0; }
.ed-ring-svg { width: 36px; height: 36px; transform: rotate(-90deg); }
.ed-ring-bg { fill: none; stroke: rgba(0, 0, 0, 0.07); stroke-width: 3; }
.ed-ring-fg {
  fill: none;
  stroke-width: 3;
  stroke-linecap: round;
  transition: stroke-dasharray 0.7s var(--ease-standard);
}
.ed-ring-sm-val {
  position: absolute;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 11px;
  font-weight: 600;
  font-feature-settings: "tnum";
  letter-spacing: -0.01em;
}

.ed-ring-info { flex: 1; min-width: 0; }
.ed-ring-lbl {
  font-size: 9px;
  font-weight: 600;
  letter-spacing: 0.08em;
  color: var(--t1, #1E2A4A);
  text-transform: uppercase;
  margin-bottom: 2px;
}
.ed-ring-cnt {
  font-size: 10.5px;
  color: var(--t1, #1E2A4A);
  display: flex;
  align-items: baseline;
  gap: 5px;
  flex-wrap: wrap;
  font-feature-settings: "tnum";
}
.ed-ring-cnt strong { font-size: 13px; font-weight: 600; margin-right: 2px; }
.ed-ring-dim { color: var(--t3, var(--t-muted)); font-weight: 500; }
.ed-ring-delta { font-size: 9px; font-weight: 600; }
.ed-ring-delta-nochange { font-size: 9px; font-weight: 500; color: #B4B2A9; }
.ed-ring-gap {
  font-size: 9px;
  color: #B4B2A9;
  font-weight: 500;
  margin-top: 2px;
  letter-spacing: 0.02em;
}

.ed-empty {
  padding: 30px 16px;
  text-align: center;
  color: #B4B2A9;
  font-size: 11.5px;
  font-style: italic;
}

.rt-table {
  display: flex;
  flex-direction: column;
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  max-height: 380px;
}

.rt-hdr {
  display: grid;
  grid-template-columns: 2.2fr repeat(6, 1fr);
  gap: 4px;
  padding: 6px 0 8px;
  border-bottom: 1px solid rgba(0, 0, 0, 0.05);
  position: sticky;
  top: 0;
  background: var(--bg1, #fff);
  z-index: 1;
}
.rt-hdr span {
  font-size: 9.5px;
  font-weight: 600;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: var(--t3, var(--t-muted));
  /* Per user 2026-05-23: рейтинг-колонки центрируем чтобы заголовок
     совпадал с центрированной ячейкой (.rt-cell flex-column align-center). */
  text-align: center;
}
.rt-hdr span:first-child {
  /* КОМПАНИЯ — оставляем left-aligned, как и сама колонка имени. */
  text-align: left;
}

.rt-row {
  display: grid;
  grid-template-columns: 2.2fr repeat(6, 1fr);
  gap: 4px;
  padding: 9px 0;
  align-items: center;
  border-bottom: 1px solid rgba(0, 0, 0, 0.03);
  animation: ringFadeIn 0.4s var(--ease-standard) both;
}
.rt-row:last-child { border-bottom: none; }

/* Мобильный: рейтинг-таблица (7 колонок) скроллится горизонтально, колонки
   остаются читаемыми (min-width), а не сжимаются в нечитаемую кашу. */
@media (max-width: 640px) {
  .rt-table { overflow-x: auto; -webkit-overflow-scrolling: touch; }
  .rt-hdr, .rt-row { min-width: 540px; }
}

.rt-co-name {
  font-size: 11.5px;
  font-weight: 500;
  color: var(--t1, #1E2A4A);
  display: flex;
  align-items: center;
  gap: 6px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.rt-co-name::before {
  content: "";
  width: 3px;
  height: 12px;
  border-radius: 2px;
  background: var(--stripe, var(--t-muted));
  flex-shrink: 0;
}

.rt-cell {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 1px;
  font-size: 9.5px;
}

/* Pack 7.31: rating cell becomes a link when report_url is present */
.rt-cell-link {
  display: inline-flex;
  flex-direction: column;
  align-items: center;
  gap: 1px;
  text-decoration: none;
  color: inherit;
  position: relative;
  padding: 3px 5px 2px;
  border-radius: 6px;
  transition: background 0.16s ease, transform 0.16s ease, box-shadow 0.16s ease;
}
.rt-cell-link--clickable {
  cursor: pointer;
}
.rt-cell-link--clickable:hover {
  background: rgba(127, 119, 221, 0.07);
  transform: translateY(-1px);
}
.rt-cell-link--clickable:hover .rt-badge {
  box-shadow: 0 3px 10px rgba(127, 119, 221, 0.22);
  transform: translateY(-0.5px);
}
.rt-cell-link--clickable:hover .rt-outlook {
  box-shadow: 0 1px 4px rgba(0, 0, 0, 0.08);
}
.rt-cell-link--clickable:focus-visible {
  outline: 2px solid rgba(127, 119, 221, 0.55);
  outline-offset: 1px;
}
.rt-badge {
  transition: box-shadow 0.16s ease, transform 0.16s ease;
}
.rt-outlook {
  transition: box-shadow 0.16s ease;
}

/* External-link affordance — appears on hover */
.rt-ext-ic {
  position: absolute;
  top: -1px;
  right: -1px;
  width: 11px;
  height: 11px;
  color: #7F77DD;
  opacity: 0;
  transform: scale(0.7) translate(2px, -2px);
  transition: opacity 0.16s ease, transform 0.16s ease;
  background: var(--bg1, #fff);
  border-radius: 50%;
  padding: 1px;
  box-shadow: 0 1px 3px rgba(127, 119, 221, 0.30);
}
.rt-cell-link--clickable:hover .rt-ext-ic {
  opacity: 1;
  transform: scale(1) translate(0, 0);
}

.rt-badge {
  display: inline-block;
  padding: 1px 7px;
  border-radius: 4px;
  font-size: 10px;
  font-weight: 700;
  color: var(--t1, #1E2A4A);
  letter-spacing: 0;
  font-feature-settings: "tnum";
}

.rt-outlook {
  font-size: 8.5px;
  font-weight: 500;
  letter-spacing: 0.02em;
  background: rgba(0, 0, 0, 0.03);
  padding: 0 5px;
  border-radius: 3px;
  margin-top: 1px;
}

.rt-date {
  font-size: 8.5px;
  color: #B4B2A9;
  font-weight: 500;
  font-feature-settings: "tnum";
  margin-top: 1px;
}

.rt-empty { color: rgba(0, 0, 0, 0.15); font-size: 11px; }

@keyframes ringFadeIn {
  0%   { opacity: 0; transform: translateY(6px); }
  100% { opacity: 1; transform: translateY(0); }
}

@media (max-width: 1100px) {
  .rt-rings { grid-template-columns: repeat(2, 1fr); }
}
</style>
