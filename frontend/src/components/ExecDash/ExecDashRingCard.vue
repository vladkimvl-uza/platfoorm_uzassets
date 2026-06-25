<script setup lang="ts">
/**
 * ExecDashRingCard — one ring KPI (FITCH/S&P/Moody's/ESG).
 *
 * Extracted as separate component so per-card useNumberTween works (Vue
 * composables can't be called in v-for loops in setup). 2026-05-26.
 */
import { useId } from "vue";
import type { ExecRingCard } from "@/api/executiveDashboard";
import { useNumberTween } from "@/composables/useNumberTween";

const props = defineProps<{
  card: ExecRingCard;
  staggerDelay?: number;
}>();

// Уникальный id градиента на каждый экземпляр (иначе SVG-градиенты столкнутся).
const gradId = "edrg-" + useId().replace(/[^a-zA-Z0-9-]/g, "");

const tScore       = useNumberTween(() => Number(props.card.score) || 0, { duration: 900 });
const tRatedCount  = useNumberTween(() => Number(props.card.rated_count) || 0, { duration: 900 });
const tTotal       = useNumberTween(() => Number(props.card.total) || 0, { duration: 900 });
const tDelta2024   = useNumberTween(() => Number(props.card.delta_2024) || 0, { duration: 900 });
const tRingPct     = useNumberTween(
  () => (props.card.total ? Math.min(100, (props.card.rated_count / props.card.total) * 100) : 0),
  { duration: 900 },
);
</script>

<template>
  <div class="ed-ring-card" :style="{ animationDelay: (staggerDelay || 0) + 'ms' }">
    <div class="ed-ring-sm">
      <svg viewBox="0 0 36 36" class="ed-ring-svg" aria-hidden="true">
        <defs>
          <linearGradient :id="gradId" x1="0" y1="0" x2="1" y2="1">
            <stop offset="0%" :stop-color="card.accent" stop-opacity="0.4" />
            <stop offset="100%" :stop-color="card.accent" stop-opacity="1" />
          </linearGradient>
        </defs>
        <path
          class="ed-ring-bg"
          d="M18 2.0845 a 15.9155 15.9155 0 0 1 0 31.831 a 15.9155 15.9155 0 0 1 0 -31.831"
        />
        <path
          class="ed-ring-fg"
          :stroke="`url(#${gradId})`"
          :stroke-dasharray="Math.round(tRingPct) + ', 100'"
          d="M18 2.0845 a 15.9155 15.9155 0 0 1 0 31.831 a 15.9155 15.9155 0 0 1 0 -31.831"
        />
      </svg>
      <div class="ed-ring-sm-val" :style="{ color: card.accent }">
        {{ Math.round(tScore) }}
      </div>
    </div>

    <div class="ed-ring-info">
      <div class="ed-ring-lbl">{{ card.label }}</div>
      <div class="ed-ring-cnt">
        <strong>{{ Math.round(tRatedCount) }}</strong>
        <span class="ed-ring-dim">из {{ Math.round(tTotal) }}</span>
        <span
          v-if="card.delta_2024 > 0"
          class="ed-ring-delta"
          :style="{ color: card.accent }"
        >+{{ Math.round(tDelta2024) }} к 2024</span>
        <span v-else-if="card.delta_2024 === 0" class="ed-ring-delta-nochange">
          = к 2024
        </span>
      </div>
      <div class="ed-ring-gap">
        {{ card.not_covered > 0 ? card.not_covered + ' не охвачено' : 'полное покрытие' }}
      </div>
    </div>
  </div>
</template>

<style scoped>
/* 2026-05-26: copied from parent ExecDashRatings.vue — child <scoped>
   doesn't inherit from parent, so без этих правил .ed-ring-bg рисовался
   чёрным заливным кругом (default SVG path = fill black). */
.ed-ring-card {
  background: #FFFFFF;
  border-radius: 11px;
  padding: 9px 11px;
  display: flex;
  flex-direction: row;
  align-items: center;
  gap: 8px;
  border: 1px solid rgba(16, 24, 64, 0.05);
  box-shadow: 0 1px 3px rgba(16, 24, 64, 0.05), 0 5px 14px rgba(16, 24, 64, 0.04);
  animation: ringFadeIn 0.5s var(--ease-standard) both;
  transition: box-shadow 0.16s ease, transform 0.16s ease;
}
.ed-ring-card:hover { box-shadow: 0 2px 6px rgba(16, 24, 64, 0.07), 0 10px 22px rgba(16, 24, 64, 0.07); transform: translateY(-1px); }
@keyframes ringFadeIn {
  from { opacity: 0; transform: translateY(6px); }
  to   { opacity: 1; transform: translateY(0); }
}

.ed-ring-sm { position: relative; width: 36px; height: 36px; flex-shrink: 0; }
.ed-ring-svg { width: 36px; height: 36px; transform: rotate(-90deg); }
.ed-ring-bg { fill: none; stroke: #EBEEF6; stroke-width: 3; }
.ed-ring-fg {
  fill: none;
  stroke-width: 3.2;
  stroke-linecap: round;
  filter: drop-shadow(0 1px 2px rgba(15, 23, 60, 0.22));
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
.ed-ring-delta-nochange { font-size: 9px; font-weight: 500; color: #6B6A66; }
.ed-ring-gap {
  font-size: 9px;
  color: #6B6A66;
  font-weight: 500;
  margin-top: 2px;
  letter-spacing: 0.02em;
}
</style>
