<script setup lang="ts">
defineProps<{
  linkedYear: number | null | undefined;
  size?: "sm" | "md";
}>();
</script>

<template>
  <span v-if="linkedYear" class="def-badge" :class="`size-${size || 'md'}`">
    <svg class="def-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor"
         stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
      <line x1="5" y1="12" x2="19" y2="12"/>
      <polyline points="12 5 19 12 12 19"/>
    </svg>
    Перенесена на {{ linkedYear }}
  </span>
</template>

<style scoped>
.def-badge {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  font-weight: 600;
  border-radius: 11px;
  background: rgba(127, 119, 221, 0.10);
  color: #7F77DD;
  white-space: nowrap;
  line-height: 1;
}
.def-icon {
  flex-shrink: 0;
}
.size-sm {
  padding: 2px 8px;
  font-size: 10px;
}
.size-sm .def-icon { width: 9px; height: 9px; }
.size-md {
  padding: 3px 10px;
  font-size: 10.5px;
}
.size-md .def-icon { width: 10px; height: 10px; }
</style>
