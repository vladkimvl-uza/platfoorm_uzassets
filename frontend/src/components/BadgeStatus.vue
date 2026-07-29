<script setup lang="ts">
import { computed } from "vue";
import { i18nKey } from "@/locale/keys";
import { useI18n } from "@/composables/useI18n";
const { t } = useI18n();



const props = defineProps<{
  status: string;
  size?: "sm" | "md";
}>();

// Точное соответствие COLS из легасиа (line 6743)
const STATUS_DEFS: Record<string, { label: string; bg: string; fg: string }> = {
  init:      { label: i18nKey("Инициирование"),   bg: "#E2E8F0",                  fg: "#64748B" },
  new:       { label: i18nKey("Не начато"),       bg: "#F1F5F9",                  fg: "#94A3B8" },
  active:    { label: i18nKey("В процессе"),      bg: "rgba(55,138,221,.10)",     fg: "#3B82F6" },
  review:    { label: i18nKey("На согласовании"), bg: "#FEF9C3",                  fg: "#F59E0B" },
  done:      { label: i18nKey("Завершено"),       bg: "#D1FAE5",                  fg: "#10B981" },
  quarterly: { label: i18nKey("Ежеквартально"),   bg: "rgba(168,85,247,.13)",     fg: "#7E22CE" },
  monthly:   { label: i18nKey("Ежемесячно"),      bg: "rgba(99,102,241,.13)",     fg: "#4338CA" },
  ongoing:   { label: i18nKey("Постоянно"),       bg: "rgba(6,182,212,.13)",      fg: "#0E7490" },
};

const meta = computed(() => STATUS_DEFS[props.status] ?? {
  label: props.status, bg: "#F1F5F9", fg: "#64748B",
});
</script>

<template>
  <span class="status-badge" :class="`size-${size || 'md'}`"
        :style="{ background: meta.bg, color: meta.fg }">
    {{ t(meta.label) }}
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
