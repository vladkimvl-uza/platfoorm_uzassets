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
    :style="{ '--stripe-color': borderColor }"
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
  background: var(--bg2, #FAFAFC);
  border: 0.5px solid var(--border-hard);
  border-radius: 8px;
  padding: 9px 11px 9px 18px;
  cursor: pointer;
  transition: background 0.12s;
  position: relative; overflow: hidden;
}
.rv3-card::before {
  content: ""; position: absolute;
  left: 6px; top: 8px; bottom: 8px;
  width: 4px; border-radius: 4px;
  background: var(--stripe-color, #D1D5DB);
  pointer-events: none;
}
.rv3-card:hover { background: var(--bg1, #fff); }
.rv3-card.dim { opacity: 0.55; }
.rv3-card-row {
  display: flex; align-items: flex-start; justify-content: space-between;
  gap: 8px; margin-bottom: 4px;
}
.rv3-card-name {
  font-size: 12px; font-weight: 500; color: var(--t1, #1E2A4A);
  min-width: 0; line-height: 1.3;
}
.rv3-card-pill {
  padding: 1px 7px; border-radius: 9px;
  font-size: 9.5px; font-weight: 500;
  letter-spacing: .04em;
  border: none; outline: none;
  cursor: inherit;
  font-family: inherit;
}
/* editable <select>: не сжимать длинным названием модуля и не обрезать значение */
select.rv3-card-pill {
  flex-shrink: 0;
  min-width: 66px;
  max-width: 84px;
  box-sizing: border-box;
  padding: 2px 4px 2px 7px;
  cursor: pointer;
  -webkit-appearance: menulist; appearance: menulist;
}
.rv3-card-sub {
  font-size: 10px; color: var(--t3, var(--t-muted));
}
.rv3-card-sub.warn { color: #B27015; font-weight: 500; }
</style>
