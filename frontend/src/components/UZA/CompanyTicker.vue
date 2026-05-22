<template>
  <div class="co-ticker" :style="tickerStyle" :title="title">
    {{ resolvedAbbr }}
  </div>
</template>

<script setup lang="ts">
/**
 *
 * Renders a small pastel ticker badge with company abbreviation, colored by sector.
 * Used in tables, cards, and list rows where company identity needs visual recall.
 *
 *   mining    bg #EEEDFE  text #3C3489
 *   oilgas    bg #DCFCE7  text #1D9E75
 *   energy    bg #FEF9C3  text #633806
 *   transport bg rgba(55,138,221,.10)  text #378ADD
 *   other     bg #F1EFE8  text #444441
 *
 * Default size 22px (height); width = max(size, 36) — keeps the ticker readable
 * even for short abbreviations.
 *
 * Usage:
 *   <CompanyTicker :name="co.name" :sector="co.sector" />
 *   <CompanyTicker :name="co.name" :size="40" />            <!-- larger -->
 *   <CompanyTicker :abbr="'NGMK'" :sector="'mining'" />     <!-- explicit abbr -->
 */

interface CompanyEntry {
  name: string;
  abbr: string;
  sector: string;
}

const props = withDefaults(
  defineProps<{
    /** Full company name (looked up in the companies registry for sector + abbr) */
    name?: string;
    /** Sector code: mining | oilgas | energy | transport | other */
    sector?: string;
    /** Override abbreviation (otherwise looked up or first-3 of name) */
    abbr?: string;
    /** Height in px (width = max(size, 36)) */
    size?: number;
    /** Optional registry override (for testing); falls back to window.COMPANIES if present */
    companies?: CompanyEntry[];
    /** Optional title attribute (tooltip on hover) */
    title?: string;
  }>(),
  {
    size: 22,
  },
);

// Verbatim palette
const BG_MAP: Record<string, string> = {
  mining: "#EEEDFE",
  oilgas: "#DCFCE7",
  energy: "#FEF9C3",
  transport: "rgba(55,138,221,.10)",
  other: "#F1EFE8",
};

const TX_MAP: Record<string, string> = {
  mining: "#3C3489",
  oilgas: "#1D9E75",
  energy: "#633806",
  transport: "#378ADD",
  other: "#444441",
};

function lookupCompany(): CompanyEntry | null {
  if (!props.name) return null;
  const registry: CompanyEntry[] | undefined =
    props.companies ||
    ((typeof window !== "undefined" && (window as unknown as { COMPANIES?: CompanyEntry[] }).COMPANIES) || undefined);
  if (!registry) return null;
  return registry.find((c) => c.name === props.name) || null;
}

import { computed } from "vue";

const resolvedAbbr = computed(() => {
  if (props.abbr) return props.abbr;
  const co = lookupCompany();
  if (co?.abbr) return co.abbr;
  return (props.name || "?").substring(0, 3).toUpperCase();
});

const resolvedSector = computed(() => {
  const co = lookupCompany();
  return (co?.sector ?? props.sector ?? "other").toLowerCase();
});

const tickerStyle = computed(() => {
  const s = props.size;
  const minW = Math.max(s, 36);
  const sec = resolvedSector.value;
  return {
    minWidth: `${minW}px`,
    height: `${s}px`,
    fontSize: `${s < 24 ? 9 : 10}px`,
    background: BG_MAP[sec] || BG_MAP.other,
    color: TX_MAP[sec] || TX_MAP.other,
  };
});
</script>

<style scoped>
.co-ticker {
  border-radius: 6px;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  font-weight: 500;
  font-family: Geist, "SF Mono", "Menlo", monospace;
  letter-spacing: 0.03em;
  padding: 0 4px;
  user-select: none;
  white-space: nowrap;
  transition: transform .18s cubic-bezier(0.34, 1.2, 0.64, 1);
}

/* Subtle lift on hover when used inside clickable rows */
.co-ticker:hover {
  transform: translateY(-1px);
}
</style>
