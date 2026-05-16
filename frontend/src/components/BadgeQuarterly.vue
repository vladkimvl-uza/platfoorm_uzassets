<script setup lang="ts">
import { computed } from "vue";

const props = defineProps<{
  // Из task.quarters (или task.extra.quarters): { q1: {weight,plan,fact}, ... }
  quarters: Record<string, { weight?: number; plan?: number; fact?: number }> | null | undefined;
  size?: "sm" | "md";
}>();

const doneCount = computed(() => {
  if (!props.quarters) return 0;
  let cnt = 0;
  for (const k of ["q1", "q2", "q3", "q4"]) {
    const q = (props.quarters as any)[k];
    if (q && (q.fact ?? 0) >= (q.plan ?? 0) && (q.plan ?? 0) > 0) cnt++;
    else if (q && (q.fact ?? 0) > 0 && (q.plan ?? 0) === 0) cnt++; // alt: any fact counts
  }
  return cnt;
});

const isAllDone = computed(() => doneCount.value === 4);

const colors = computed(() =>
  isAllDone.value
    ? { bg: "#DCFCE7", fg: "#0E7A58", dot: "#1D9E75" }
    : { bg: "rgba(168,85,247,.13)", fg: "#7E22CE", dot: "#A855F7" }
);

const text = computed(() => {
  if (isAllDone.value) return "✓ Все кварталы закрыты";
  return `Ежеквартально · ${doneCount.value}/4`;
});
</script>

<template>
  <span v-if="quarters" class="qt-badge" :class="`size-${size || 'md'}`"
        :style="{ background: colors.bg, color: colors.fg }">
    <span class="qt-dot" :style="{ background: colors.dot }"></span>
    {{ text }}
  </span>
</template>

<style scoped>
.qt-badge {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  font-weight: 500;
  border-radius: 11px;
  white-space: nowrap;
  line-height: 1;
}
.qt-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  flex-shrink: 0;
}
.size-sm { padding: 2px 8px; font-size: 10px; }
.size-md { padding: 3px 10px; font-size: 11px; }
</style>
