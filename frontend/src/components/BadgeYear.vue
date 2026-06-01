<script setup lang="ts">
defineProps<{
  year: number | string;
  variant?: "default" | "muted";
  size?: "sm" | "md";
}>();
</script>

<template>
  <span class="year-badge"
        :class="[`v-${variant || 'default'}`, `size-${size || 'md'}`]">
    {{ year }}
  </span>
</template>

<style scoped>
.year-badge {
  display: inline-flex;
  align-items: center;
  font-weight: 600;
  border-radius: 11px;
  font-variant-numeric: tabular-nums;
  letter-spacing: 0.02em;
  line-height: 1;
  white-space: nowrap;
}
.v-default {
  background: rgba(127, 119, 221, 0.10);
  color: #7F77DD;
}
.v-muted {
  background: var(--bg3, #F1F5F9);
  color: var(--t3, var(--t3));
}
.size-sm { padding: 2px 8px;  font-size: 10px; }
.size-md { padding: 3px 10px; font-size: 11px; }
</style>
