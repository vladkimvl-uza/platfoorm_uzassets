<script setup lang="ts">
import { computed } from 'vue';
import type { AccessLevel } from '@/composables/usePermissions';

const props = defineProps<{
  moduleCode: string;
  moduleLabel: string;
  level: AccessLevel;
  explain?: string;
  scope?: string;
  manualGrant?: boolean;
  editable?: boolean;
}>();
defineEmits<{ (e: 'change', level: AccessLevel): void; (e: 'click'): void }>();

const LEVEL_META: Record<AccessLevel, { color: string; bg: string; label: string }> = {
  admin: { color: '#1D9E75', bg: 'rgba(29,158,117,.12)', label: 'ADMIN' },
  write: { color: '#534AB7', bg: 'rgba(127,119,221,.12)', label: 'WRITE' },
  read:  { color: '#1E5AAA', bg: 'rgba(55,138,221,.12)',  label: 'READ' },
  none:  { color: '#888780', bg: '#F3F4F8',               label: 'NONE' },
};

const borderColor = computed(() => {
  if (props.manualGrant) return '#EF9F27';
  return LEVEL_META[props.level].color === '#888780' ? '#D1D5DB' : LEVEL_META[props.level].color;
});
const meta = computed(() => LEVEL_META[props.level]);
const dim  = computed(() => props.level === 'none' && !props.editable);
</script>

<template>
  <div
    class="rv3-card"
    :class="{ dim }"
    :style="{ borderLeftColor: borderColor }"
    @click="$emit('click')"
  >
    <div class="rv3-card-row">
      <div class="rv3-card-name">{{ moduleLabel }}</div>
      <select
        v-if="editable"
        :value="level"
        class="rv3-card-pill"
        :style="{ color: meta.color, background: meta.bg }"
        @change="$emit('change', ($event.target as HTMLSelectElement).value as AccessLevel)"
        @click.stop
      >
        <option value="admin">ADMIN</option>
        <option value="write">WRITE</option>
        <option value="read">READ</option>
        <option value="none">NONE</option>
      </select>
      <span
        v-else
        class="rv3-card-pill"
        :style="{ color: meta.color, background: meta.bg }"
      >{{ meta.label }}</span>
    </div>
    <div class="rv3-card-sub" :class="{ warn: manualGrant }">
      <template v-if="manualGrant">+ персональный grant</template>
      <template v-else>{{ explain }}{{ scope ? ' · scope: ' + scope : '' }}</template>
    </div>
  </div>
</template>

<style scoped>
.rv3-card {
  background: #FAFAFC;
  border: 0.5px solid #E5E7EB;
  border-radius: 8px;
  padding: 9px 11px;
  cursor: pointer;
  transition: background 0.12s;
  position: relative; overflow: hidden;
}
.rv3-card::before {
  content: ""; position: absolute; top: 0; left: 0; right: 0;
  height: 2px; background: #D1D5DB;
  border-top-left-radius: inherit; border-top-right-radius: inherit;
  animation: uzaStripeDrawIn .5s cubic-bezier(.4,0,.2,1) both;
  pointer-events: none;
}
.rv3-card:hover { background: #fff; }
.rv3-card.dim { opacity: 0.55; }
.rv3-card-row {
  display: flex; align-items: flex-start; justify-content: space-between;
  gap: 8px; margin-bottom: 4px;
}
.rv3-card-name {
  font-size: 12px; font-weight: 500; color: #1E2A4A;
}
.rv3-card-pill {
  padding: 1px 7px; border-radius: 9px;
  font-size: 9.5px; font-weight: 500;
  letter-spacing: .04em;
  border: none; outline: none;
  cursor: inherit;
  font-family: inherit;
}
.rv3-card-sub {
  font-size: 10px; color: #888780;
}
.rv3-card-sub.warn { color: #B27015; font-weight: 500; }
</style>