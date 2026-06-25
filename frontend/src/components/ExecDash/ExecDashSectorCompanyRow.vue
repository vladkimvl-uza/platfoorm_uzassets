<script setup lang="ts">
/**
 * ExecDashSectorCompanyRow — one company row inside a sector card.
 *
 * Tweens its `pct` independently (composables must be called at component
 * setup top-level, so per-row tween needs its own component).
 *
 * 2026-05-26: extracted so per-company numbers animate on year change
 * alongside the sector card's avg_pct.
 */
import { useNumberTween } from "@/composables/useNumberTween";

interface CoData {
  company_id: string;
  board_id?: string | null;
  name: string;
  pct: number;
  task_total: number;
  task_done: number;
}

const props = defineProps<{
  co: CoData;
  displayName: string;
  pctColor: string;
}>();

defineEmits<{ click: [] }>();

const tPct = useNumberTween(() => Number(props.co.pct) || 0, { duration: 900 });
</script>

<template>
  <div
    class="va-sec-co va-sec-co-clickable"
    role="button"
    tabindex="0"
    :aria-label="`Открыть карточку компании ${displayName}`"
    @click.stop="$emit('click')"
    @keydown.enter.prevent="$emit('click')"
    @keydown.space.prevent="$emit('click')"
    title="Открыть карточку компании"
  >
    <span class="co">{{ displayName }}</span>
    <span class="pct" :style="{ color: pctColor }">{{ Math.round(tPct) }}%</span>
  </div>
</template>

<style scoped>
/* a11y: видимый фокус-ринг при навигации с клавиатуры (стили строки — в родителе) */
.va-sec-co-clickable {
  outline: none;
  border-radius: 6px;
}
.va-sec-co-clickable:focus-visible {
  box-shadow: 0 0 0 2px rgba(127, 119, 221, 0.45);
}
</style>
