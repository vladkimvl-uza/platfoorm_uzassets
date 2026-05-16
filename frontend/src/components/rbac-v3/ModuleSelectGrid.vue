<script setup lang="ts">
import { MODULE_REGISTRY } from '@/composables/usePermissions';
import type { AccessLevel } from '@/composables/usePermissions';
import AccessCard from './AccessCard.vue';

defineProps<{
  /** Map of moduleCode -> level. Modules not in map default to 'none'. */
  modelValue: Record<string, AccessLevel>;
  /** If true, cards render <select> instead of static pill. */
  editable?: boolean;
  /** Source of each module's access ('via role: X' or 'manual grant'). */
  sources?: Record<string, string>;
  columns?: number;
}>();
defineEmits<{ (e: 'update:modelValue', value: Record<string, AccessLevel>): void }>();
</script>

<template>
  <div class="rv3-grid" :style="{ gridTemplateColumns: `repeat(${columns || 2}, 1fr)` }">
    <AccessCard
      v-for="m in MODULE_REGISTRY"
      :key="m.code"
      :module-code="m.code"
      :module-label="m.label"
      :level="modelValue[m.code] || 'none'"
      :explain="sources?.[m.code] || (modelValue[m.code] && modelValue[m.code] !== 'none' ? 'via permissions' : 'нет в роли')"
      :editable="editable"
      @change="(lvl) => $emit('update:modelValue', { ...modelValue, [m.code]: lvl })"
    />
  </div>
</template>

<style scoped>
.rv3-grid {
  display: grid;
  gap: 8px;
}
</style>