<script setup lang="ts">
import { computed } from "vue";

const props = defineProps<{
  status: string;
  size?: "sm" | "md";
}>();

// Точное соответствие COLS из легасиа (line 6743)
const STATUS_DEFS: Record<string, { label: string; bg: string; fg: string }> = {
  init:      { label: "Инициирование",   bg: "#E2E8F0",                  fg: "#64748B" },
  new:       { label: "Не начато",       bg: "#F1F5F9",                  fg: "#94A3B8" },
  active:    { label: "В процессе",      bg: "rgba(55,138,221,.10)",     fg: "#3B82F6" },
  review:    { label: "На согласовании", bg: "#FEF9C3",                  fg: "#F59E0B" },
  done:      { label: "Завершено",       bg: "#D1FAE5",                  fg: "#10B981" },
  quarterly: { label: "Ежеквартально",   bg: "rgba(168,85,247,.13)",     fg: "#7E22CE" },
  monthly:   { label: "Ежемесячно",      bg: "rgba(99,102,241,.13)",     fg: "#4338CA" },
  ongoing:   { label: "Постоянно",       bg: "rgba(6,182,212,.13)",      fg: "#0E7490" },
};

const meta = computed(() => STATUS_DEFS[props.status] ?? {
  label: props.status, bg: "#F1F5F9", fg: "#64748B",
});
</script>

<template>
  <span class="status-badge" :class="`size-${size || 'md'}`"
        :style="{ background: meta.bg, color: meta.fg }">
    {{ meta.label }}
  </span>
</template>

<style scoped>
.status-badge {
  display: inline-flex;
  align-items: center;
  font-weight: 500;
  border-radius: 11px;
  letter-spacing: 0;
  white-space: nowrap;
  font-variant-numeric: tabular-nums;
  line-height: 1;
}
.size-sm { padding: 2px 8px; font-size: 10px; }
.size-md { padding: 3px 10px; font-size: 11px; }
</style>
