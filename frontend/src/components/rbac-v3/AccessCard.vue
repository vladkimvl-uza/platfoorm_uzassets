<script setup lang="ts">
import { computed } from 'vue';
import { useI18n } from '@/composables/useI18n';
import type { AccessLevel } from '@/composables/usePermissions';

const { t } = useI18n();

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
  write: { color: '#7C6FF7', bg: 'rgba(124,111,247,.13)', label: 'WRITE' },
  read:  { color: '#0891B2', bg: 'rgba(8,145,178,.12)',  label: 'READ' },
  none:  { color: '#94A3B8', bg: '#F1F0FB',              label: 'NONE' },
};

const stripeColor = computed(() => {
  if (props.manualGrant) return '#D97706';
  return props.level === 'none' ? '#E2E0F0' : LEVEL_META[props.level].color;
});
const meta = computed(() => LEVEL_META[props.level]);
const dim  = computed(() => props.level === 'none' && !props.editable);
</script>

<template>
  <div
    class="rv3-card"
    :class="{ dim, 'is-on': level !== 'none' }"
    :style="{ '--stripe-color': stripeColor }"
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
      <template v-if="manualGrant">{{ t("+ персональный grant") }}</template>
      <template v-else>{{ explain }}{{ scope ? ' · scope: ' + scope : '' }}</template>
    </div>
  </div>
</template>

<style scoped>
.rv3-card {
  font-family: var(--font);
  background: #fff;
  border: 1px solid rgba(99, 102, 180, .10);
  border-radius: 11px;
  padding: 12px 13px 10px;
  cursor: pointer;
  transition: transform .16s var(--ease-standard, cubic-bezier(.25,.8,.25,1)), box-shadow .16s, border-color .16s;
  box-shadow: 0 1px 2px rgba(15,23,60,.03);
  position: relative; overflow: hidden;
}
/* Верхняя акцент-полоса (эталон) */
.rv3-card::before {
  content: ""; position: absolute;
  left: 0; right: 0; top: 0; height: 3px;
  background: var(--stripe-color, #E2E0F0);
  transform: scaleX(1); transform-origin: left center;
  pointer-events: none;
}
.rv3-card.is-on { border-color: rgba(124, 111, 247, .18); }
.rv3-card:hover {
  transform: translateY(-2px);
  box-shadow: 0 6px 18px rgba(15,23,60,.09);
  border-color: rgba(124, 111, 247, .3);
}
.rv3-card.dim { opacity: 0.5; }
.rv3-card-row {
  display: flex; align-items: flex-start; justify-content: space-between;
  gap: 8px; margin-bottom: 4px;
}
.rv3-card-name {
  font-size: 12.5px; font-weight: 500; color: var(--t1, #0F172A);
  min-width: 0; line-height: 1.3;
}
.rv3-card-pill {
  padding: 2px 8px; border-radius: 999px;
  font-size: 9.5px; font-weight: 600;
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
  font-size: 10px; color: var(--t3, #94A3B8);
}
.rv3-card-sub.warn { color: #D97706; font-weight: 500; }
</style>
