<script setup lang="ts">
/**
 * ESGDrillModal — единый премиум drill-down для матрицы зрелости.
 * Переиспользуется для KPI-карточек, чипов «Требует внимания» и ступеней воронок:
 * везде один паттерн «клик → список компаний с метрикой → переход в профиль».
 */
import ModalShell from "@/components/ModalShell.vue";
import { useI18n } from "@/composables/useI18n";

export interface ESGDrillRow {
  id: string;
  name: string;
  sector?: string | null;
  color?: string | null;
  value: string | number;
  valueColor?: string | null;
  badge?: string | null;
  badgeColor?: string | null;
}

const props = defineProps<{
  open: boolean;
  title: string;
  subtitle?: string;
  description?: string;
  accent?: string;
  rows: ESGDrillRow[];
}>();
const emit = defineEmits<{ (e: "close"): void; (e: "open-company", id: string): void }>();
void props;
const { t } = useI18n();
</script>

<template>
  <ModalShell :open="open" size="md" @close="emit('close')">
    <template #header>
      <div class="dm-head">
        <span class="dm-accent" :style="{ background: accent || '#7C6FF7' }"></span>
        <div class="dm-head-t">
          <div class="dm-title">{{ title }}<span class="dm-cnt" :style="{ background: (accent || '#7C6FF7') + '1A', color: accent || '#7C6FF7' }">{{ rows.length }}</span></div>
          <div v-if="subtitle" class="dm-sub">{{ subtitle }}</div>
        </div>
      </div>
    </template>

    <div class="dm-body">
      <p v-if="description" class="dm-desc">{{ description }}</p>
      <div class="dm-list">
        <button v-for="(r, i) in rows" :key="r.id" type="button" class="dm-row"
                :style="{ '--d': (i * 32) + 'ms' }" @click="emit('open-company', r.id)">
          <span class="dm-dot" :style="{ background: r.color || '#7C6FF7' }"></span>
          <span class="dm-name">{{ r.name }}</span>
          <span v-if="r.sector" class="dm-sec">{{ r.sector }}</span>
          <span v-if="r.badge" class="dm-badge" :style="{ color: r.badgeColor || '#64748B', background: (r.badgeColor || '#64748B') + '14' }">{{ r.badge }}</span>
          <span class="dm-val" :style="{ color: r.valueColor || 'var(--t1, #1E2A4A)' }">{{ r.value }}</span>
          <svg class="dm-chev" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M9 6l6 6-6 6"/></svg>
        </button>
        <div v-if="!rows.length" class="dm-empty">{{ t("Нет компаний по этому критерию") }}</div>
      </div>
    </div>
  </ModalShell>
</template>

<style scoped>
.dm-head { display: flex; align-items: center; gap: 12px; width: 100%; }
.dm-accent { width: 4px; height: 30px; border-radius: 3px; flex-shrink: 0; }
.dm-head-t { min-width: 0; }
.dm-title { font-size: 16px; font-weight: 600; color: var(--t1, #1E2A4A); display: inline-flex; align-items: center; gap: 8px; }
.dm-cnt { font-size: 12px; font-weight: 600; border-radius: 20px; padding: 1px 9px; }
.dm-sub { font-size: 11px; color: var(--t3, #94A3B8); margin-top: 2px; }

.dm-body { display: flex; flex-direction: column; gap: 12px; }
.dm-desc { font-size: 12px; color: var(--t2, #475569); line-height: 1.45; margin: 0; padding: 9px 12px; background: var(--surface-2, #FAFAFC); border-radius: 10px; }
.dm-list { display: flex; flex-direction: column; gap: 6px; max-height: 56dvh; overflow-y: auto; }

.dm-row {
  display: flex; align-items: center; gap: 10px;
  width: 100%; text-align: left; cursor: pointer;
  padding: 10px 12px; border-radius: 10px;
  border: 1px solid var(--border, #ECEAF5); background: var(--bg1, #fff);
  font-family: inherit;
  animation: dmRowIn .4s var(--ease-standard, cubic-bezier(.4,0,.2,1)) var(--d, 0ms) both;
  transition: border-color .14s, background .14s, transform .14s;
}
.dm-row:hover { border-color: #C7C2F0; background: color-mix(in srgb, #7C6FF7 5%, #fff); transform: translateX(2px); }
@keyframes dmRowIn { from { opacity: 0; transform: translateY(6px); } to { opacity: 1; transform: translateY(0); } }

.dm-dot { width: 8px; height: 8px; border-radius: 50%; flex-shrink: 0; }
.dm-name { font-size: 13px; font-weight: 500; color: var(--t1, #1E2A4A); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; flex: 1 1 auto; min-width: 0; }
.dm-sec { font-size: 10.5px; color: var(--t3, #94A3B8); white-space: nowrap; flex-shrink: 0; }
.dm-badge { font-size: 10px; font-weight: 600; border-radius: 6px; padding: 2px 7px; white-space: nowrap; flex-shrink: 0; }
.dm-val { font-size: 13.5px; font-weight: 600; font-feature-settings: 'tnum'; flex-shrink: 0; min-width: 38px; text-align: right; }
.dm-chev { color: #C4C8D4; flex-shrink: 0; transition: color .14s, transform .14s; }
.dm-row:hover .dm-chev { color: #7C6FF7; transform: translateX(2px); }
.dm-empty { font-size: 12px; color: var(--t3, #94A3B8); text-align: center; padding: 22px; }

@media (prefers-reduced-motion: reduce) { .dm-row { animation: none; } }
@media (max-width: 560px) { .dm-sec { display: none; } }
@media (min-width: 2200px) {
  .dm-title { font-size: 20px; } .dm-name { font-size: 15px; } .dm-val { font-size: 16px; }
  .dm-row { padding: 13px 16px; }
}
</style>
