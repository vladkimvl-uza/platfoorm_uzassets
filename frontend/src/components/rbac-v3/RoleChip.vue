<script setup lang="ts">
defineProps<{
  code: string;
  size?: 'sm' | 'md';
  removable?: boolean;
}>();
defineEmits<{ (e: 'remove'): void }>();
const COLORS: Record<string, { bg: string; fg: string }> = {
  admin:     { bg: 'rgba(226,75,74,.12)',  fg: '#A82C2B' },
  ceo:       { bg: 'rgba(239,159,39,.12)', fg: '#B27015' },
  debt:      { bg: 'rgba(29,158,117,.12)', fg: '#1D9E75' },
  readonly:  { bg: '#F3F4F8',              fg: '#888780' },
  imv_admin: { bg: 'rgba(55,138,221,.12)', fg: '#1E5AAA' },
  analyst:   { bg: 'rgba(127,119,221,.12)', fg: '#534AB7' },
};
function colorFor(code: string) {
  return COLORS[code] || { bg: 'rgba(127,119,221,.12)', fg: '#534AB7' };
}
</script>

<template>
  <span
    class="rv3-chip"
    :class="{ sm: size === 'sm' }"
    :style="{ background: colorFor(code).bg, color: colorFor(code).fg }"
  >
    {{ code }}
    <span v-if="removable" class="rv3-chip-x" @click.stop="$emit('remove')">×</span>
  </span>
</template>

<style scoped>
.rv3-chip {
  display: inline-flex; align-items: center; gap: 5px;
  padding: 4px 10px; border-radius: 14px;
  font-size: 11px; font-weight: 500;
  white-space: nowrap;
}
.rv3-chip.sm { padding: 2px 8px; font-size: 10px; }
.rv3-chip-x {
  cursor: pointer;
  opacity: 0.6;
  font-size: 13px;
  line-height: 1;
}
.rv3-chip-x:hover { opacity: 1; }
</style>