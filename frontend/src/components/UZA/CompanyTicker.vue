<template>
  <span
    ref="el"
    class="co-ticker"
    :class="{ 'co-ticker--chip': chip, 'co-ticker--interactive': !!code }"
    :style="tickerStyle"
    :title="title || resolvedAbbr"
    @mouseenter="onEnter"
    @mouseleave="onLeave"
    @click="onClick"
  >
    {{ resolvedAbbr }}
  </span>
</template>

<script setup lang="ts">
/**
 * CompanyTicker — единый бейдж тикера компании, окрашенный по сектору.
 *
 * Единственный источник стиля для тикеров на всей платформе: таблицы компаний,
 * карточки, списки, аудит, профиль. Где бы ни показывался тикер — только через
 * этот компонент, чтобы стиль был синхронен везде.
 *
 * Два вида:
 *   square (по умолчанию) — компактный квадратный бейдж (высота = size).
 *   chip   (:chip)        — пилюля-чип в стиле бейджей принадлежности.
 *
 * Цвет берётся, по приоритету:
 *   1) :color="'#7C6FF7'"     — явный hex сектора (sector_color из БД);
 *   2) :sector="'mining'"     — код сектора из легаси-палитры;
 *   3) other                  — нейтральный.
 *
 * Usage:
 *   <CompanyTicker abbr="NGMK" :color="c.sector_color" chip />
 *   <CompanyTicker :name="co.name" :sector="co.sector" />
 *   <CompanyTicker abbr="NUR" sector="oilgas" :size="40" />
 */

import { computed, ref } from "vue";
import { useCompanyCard } from "@/composables/useCompanyCard";

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
    /** Код компании — включает карточку-поповер по ховеру/клику */
    code?: string | null;
    /** Явный цвет сектора (hex) — приоритетнее кода сектора */
    color?: string | null;
    /** Pill-чип вместо квадратного бейджа */
    chip?: boolean;
    /** Height in px (square); для чипа влияет на размер шрифта */
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

// Verbatim legacy palette (фолбэк, если нет явного color)
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

/** #RRGGBB | #RGB → "r,g,b" (для tinted rgba); null если не hex. */
function hexToRgb(hex?: string | null): string | null {
  if (!hex) return null;
  let h = hex.trim().replace(/^#/, "");
  if (h.length === 3) h = h.split("").map((c) => c + c).join("");
  if (!/^[0-9a-fA-F]{6}$/.test(h)) return null;
  const n = parseInt(h, 16);
  return `${(n >> 16) & 255},${(n >> 8) & 255},${n & 255}`;
}

const tickerStyle = computed(() => {
  const sec = resolvedSector.value;
  const rgb = hexToRgb(props.color);

  // Цвет: явный hex > палитра сектора
  const bg = rgb ? `rgba(${rgb},.13)` : (BG_MAP[sec] || BG_MAP.other);
  const fg = rgb ? props.color! : (TX_MAP[sec] || TX_MAP.other);

  if (props.chip) {
    return {
      background: bg,
      color: fg,
      fontSize: `${props.size < 24 ? 11 : 12}px`,
    };
  }

  const s = props.size;
  return {
    minWidth: `${Math.max(s, 36)}px`,
    height: `${s}px`,
    fontSize: `${s < 24 ? 9 : 10}px`,
    background: bg,
    color: fg,
  };
});

// ── Карточка-поповер компании (если задан code) ──
const el = ref<HTMLElement | null>(null);
const card = useCompanyCard();

function cardPreview() {
  return { code: props.code || undefined, name: props.abbr || props.name, sector_color: props.color || undefined };
}
function onEnter() {
  if (props.code && el.value) card.open(props.code, el.value, cardPreview());
}
function onLeave() {
  if (props.code) card.scheduleClose();
}
function onClick(e: MouseEvent) {
  if (!props.code || !el.value) return;
  e.stopPropagation();
  card.openNow(props.code, el.value, cardPreview());
}
</script>

<style scoped>
.co-ticker {
  border-radius: 6px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  font-weight: 600;
  font-family: Geist, "SF Mono", "Menlo", monospace;
  letter-spacing: 0.03em;
  text-transform: uppercase;
  padding: 0 4px;
  user-select: none;
  white-space: nowrap;
  transition: transform .18s var(--ease-standard);
}

/* Чип-вариант — пилюля в едином стиле бейджей принадлежности */
.co-ticker--chip {
  border-radius: 999px;
  padding: 2px 10px;
  height: auto;
  line-height: 1.5;
  letter-spacing: 0.04em;
}

/* Subtle lift on hover when used inside clickable rows */
.co-ticker:hover {
  transform: translateY(-1px);
}
.co-ticker--interactive { cursor: pointer; }
</style>
