<script setup lang="ts">
import { computed } from 'vue';
const props = defineProps<{
  email?: string;
  fullName?: string;
  size?: number;
}>();
const initials = computed(() => {
  const name = props.fullName?.trim();
  if (name) {
    const parts = name.split(/\s+/);
    if (parts.length >= 2) return (parts[0][0] + parts[1][0]).toUpperCase();
    return name.slice(0, 2).toUpperCase();
  }
  const email = props.email || '';
  const local = email.split('@')[0] || '';
  const parts = local.split(/[._-]/);
  if (parts.length >= 2 && parts[0] && parts[1]) return (parts[0][0] + parts[1][0]).toUpperCase();
  return local.slice(0, 2).toUpperCase() || '?';
});
const sz = computed(() => props.size || 30);
const fs = computed(() => Math.round(sz.value * 0.4));
</script>

<template>
  <div class="rv3-avatar" :style="{ width: sz + 'px', height: sz + 'px', fontSize: fs + 'px' }">
    {{ initials }}
  </div>
</template>

<style scoped>
.rv3-avatar {
  background: linear-gradient(135deg, #7F77DD, var(--p-deep));
  border-radius: 8px;
  color: #fff;
  font-weight: 500;
  display: flex; align-items: center; justify-content: center;
  flex-shrink: 0;
  user-select: none;
}
</style>