<script setup lang="ts">
import { ref, computed } from 'vue';
import { MODULE_REGISTRY } from '@/composables/usePermissions';
import type { AccessLevel } from '@/composables/usePermissions';
import { useI18n } from '@/composables/useI18n';
import AccessCard from './AccessCard.vue';

const { t } = useI18n();

const props = defineProps<{
  /** Map of moduleCode -> level. Modules not in map default to 'none'. */
  modelValue: Record<string, AccessLevel>;
  /** If true, cards render <select> instead of static pill. */
  editable?: boolean;
  /** Source of each module's access ('via role: X' or 'manual grant'). */
  sources?: Record<string, string>;
  columns?: number;
}>();
defineEmits<{ (e: 'update:modelValue', value: Record<string, AccessLevel>): void }>();

const q = ref('');
// Поиск идёт и по переведённой подписи, и по русскому оригиналу: администратор
// с любой локалью найдёт модуль по привычному названию.
const filtered = computed(() => {
  const s = q.value.trim().toLowerCase();
  if (!s) return MODULE_REGISTRY;
  return MODULE_REGISTRY.filter(
    (m) => m.label.toLowerCase().includes(s)
        || t(m.label).toLowerCase().includes(s)
        || m.code.toLowerCase().includes(s),
  );
});
const grantedCount = computed(
  () => MODULE_REGISTRY.filter((m) => props.modelValue[m.code] && props.modelValue[m.code] !== 'none').length,
);
</script>

<template>
  <div class="rv3-grid-wrap">
    <div class="rv3-grid-bar">
      <div class="rv3-grid-search">
        <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round">
          <circle cx="11" cy="11" r="7" /><path d="M21 21l-4-4" />
        </svg>
        <input v-model="q" :placeholder="t('Поиск модуля…')" />
      </div>
      <span class="rv3-grid-count">{{ t("{n} из {total} с доступом", { n: grantedCount, total: MODULE_REGISTRY.length }) }}</span>
    </div>
    <div class="rv3-grid" :style="{ gridTemplateColumns: `repeat(${columns || 2}, 1fr)` }">
      <AccessCard
        v-for="(m, i) in filtered"
        :key="m.code"
        class="rv3-grid-item"
        :style="{ '--gi': Math.min(i, 24) * 18 + 'ms' }"
        :module-code="m.code"
        :module-label="t(m.label)"
        :level="modelValue[m.code] || 'none'"
        :explain="sources?.[m.code] || (modelValue[m.code] && modelValue[m.code] !== 'none' ? t('персональный доступ') : t('нет доступа'))"
        :editable="editable"
        @change="(lvl) => $emit('update:modelValue', { ...modelValue, [m.code]: lvl })"
      />
      <div v-if="!filtered.length" class="rv3-grid-empty">{{ t("Модули не найдены") }}</div>
    </div>
  </div>
</template>

<style scoped>
.rv3-grid-wrap { font-family: var(--font); }
.rv3-grid-bar {
  display: flex; align-items: center; justify-content: space-between;
  gap: 12px; margin-bottom: 10px; flex-wrap: wrap;
}
.rv3-grid-search {
  display: flex; align-items: center; gap: 7px;
  background: #fff; border: 1px solid rgba(99,102,180,.14);
  border-radius: 9px; padding: 6px 11px; color: #94A3B8;
  flex: 1; min-width: 180px; max-width: 320px;
  transition: border-color .15s;
}
.rv3-grid-search:focus-within { border-color: #7C6FF7; color: #7C6FF7; }
.rv3-grid-search input {
  border: none; outline: none; background: transparent;
  font-size: 13px; font-family: var(--font); color: var(--t1, #0F172A); flex: 1; min-width: 0;
}
.rv3-grid-count { font-size: 11.5px; color: var(--t3, #94A3B8); font-variant-numeric: tabular-nums; white-space: nowrap; }
.rv3-grid {
  display: grid;
  gap: 9px;
}
.rv3-grid-item { animation: rv3GridIn .35s var(--ease-standard, cubic-bezier(.25,.8,.25,1)) var(--gi, 0ms) both; }
.rv3-grid-empty { grid-column: 1 / -1; text-align: center; color: #94A3B8; font-size: 13px; padding: 26px; }
@keyframes rv3GridIn { from { opacity: 0; transform: translateY(7px); } to { opacity: 1; transform: translateY(0); } }
</style>