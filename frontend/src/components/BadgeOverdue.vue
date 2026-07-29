<script setup lang="ts">
import { useI18n } from "@/composables/useI18n";
const { t } = useI18n();
defineProps<{
  daysOverdue?: number;  // если задано — добавляет "N дн" в бейдж
  size?: "sm" | "md";
}>();
</script>

<template>
  <span class="ov-badge" :class="`size-${size || 'md'}`">
    <span class="ov-dot"></span>
    {{ t('Просрочено') }}<span v-if="daysOverdue" class="ov-days"> · {{ daysOverdue }} {{ t('дн') }}</span>
  </span>
</template>

<style scoped>
.ov-badge {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  font-weight: 600;
  border-radius: 11px;
  background: var(--red-l);
  color: var(--sev-critical);
  white-space: nowrap;
  line-height: 1;
}
.ov-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--sev-high);
  flex-shrink: 0;
}
.ov-days {
  font-weight: 500;
  opacity: 0.85;
  font-variant-numeric: tabular-nums;
}
.size-sm { padding: 2px 8px;  font-size: 10px; }
.size-md { padding: 3px 10px; font-size: 11px; }
</style>
