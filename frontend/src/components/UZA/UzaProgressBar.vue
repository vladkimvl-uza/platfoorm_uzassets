<script setup lang="ts">
/**
 * UzaProgressBar — единый горизонтальный прогресс-/процент-бар.
 * Заменяет россыпь inline `<div class="…-bar"><div class="…-bar-fill" :style="{width}">`
 * по KPI-бэндам и дрилл-модалкам (Apple-аудит, консолидация).
 *
 * value/max → доля; color — заливка; track — фон дорожки; height — толщина.
 * Минимум 2% ширины при value>0, чтобы заливка не схлопывалась в ноль.
 */
import { computed } from "vue";
import { useI18n } from "@/composables/useI18n";
const { t } = useI18n();


const props = withDefaults(defineProps<{
  value: number;
  max?: number;
  color?: string;
  track?: string;
  height?: number;
  rounded?: boolean;
  /** value/max уже доля 0..1 (тогда max игнорируется) */
  fraction?: boolean;
  ariaLabel?: string;
}>(), {
  max: 100,
  color: "var(--p, #7c6ff7)",
  track: "rgba(99,102,180,.12)",
  height: 6,
  rounded: true,
});

const pct = computed(() => {
  const raw = props.fraction ? props.value * 100 : (props.value / (props.max || 1)) * 100;
  if (!Number.isFinite(raw)) return 0;
  return Math.max(0, Math.min(100, raw));
});
const fillW = computed(() => (pct.value > 0 ? Math.max(2, pct.value) : 0));
</script>

<template>
  <div
    class="uza-pbar"
    :style="{ height: height + 'px', background: track, borderRadius: rounded ? '999px' : '0' }"
    role="progressbar"
    :aria-valuenow="Math.round(pct)"
    aria-valuemin="0"
    aria-valuemax="100"
    :aria-label="ariaLabel ? t(ariaLabel) : undefined"
  >
    <div
      class="uza-pbar-fill"
      :style="{ width: fillW + '%', background: color, borderRadius: rounded ? '999px' : '0' }"
    />
  </div>
</template>

<style scoped>
.uza-pbar {
  width: 100%;
  overflow: hidden;
}
.uza-pbar-fill {
  height: 100%;
  transition: width 0.6s var(--ease-standard, cubic-bezier(0.34, 1.2, 0.64, 1));
}
@media (prefers-reduced-motion: reduce) {
  .uza-pbar-fill { transition: none; }
}
</style>
