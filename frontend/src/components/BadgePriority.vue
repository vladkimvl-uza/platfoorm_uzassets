<script setup lang="ts">
import { computed } from "vue";

const props = defineProps<{
  priority: string | null | undefined;
  size?: "sm" | "md";
  // showMedium: показывать ли medium (по умолчанию false — как в легасие)
  showMedium?: boolean;
}>();

// Точные цвета из легасиа (line 51409 + .notes-card-priority)
const PRIO_DEFS: Record<string, { label: string; bg: string; fg: string }> = {
  high:   { label: "ВЫСОКИЙ",  bg: "rgba(226,75,74,.10)",   fg: "#A32D2D" },
  medium: { label: "СРЕДНИЙ",  bg: "rgba(239,159,39,.10)",  fg: "#A56708" },
  low:    { label: "НИЗКИЙ",   bg: "rgba(127,119,221,.08)", fg: "#534AB7" },
};

const visible = computed(() => {
  if (!props.priority) return false;
  if (props.priority === "medium" && !props.showMedium) return false;
  return PRIO_DEFS[props.priority] != null;
});

const meta = computed(() => PRIO_DEFS[props.priority || ""] ?? {
  label: "", bg: "#F1F5F9", fg: "#64748B",
});
</script>

<template>
  <span v-if="visible" class="prio-badge"
        :class="`size-${size || 'md'}`"
        :style="{ background: meta.bg, color: meta.fg }">
    {{ meta.label }}
  </span>
</template>

<style scoped>
.prio-badge {
  display: inline-flex;
  align-items: center;
  font-weight: 600;
  border-radius: 3px;
  text-transform: uppercase;
  letter-spacing: 0.04em;
  white-space: nowrap;
  line-height: 1;
}
.size-sm { padding: 1px 5px; font-size: 9px; }
.size-md { padding: 2px 6px; font-size: 10px; }
</style>
