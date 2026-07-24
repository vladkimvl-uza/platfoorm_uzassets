<script setup lang="ts">
/**
 * CtPeriodDrill — дрилл периода в «Динамике исполнения» (Execution Summary).
 * Завершённые/просроченные задачи периода, сгруппированные по направлениям,
 * с разворотом группы «+N ещё». Самодостаточен: получает details+loading,
 * своё состояние разворота и группировку держит внутри.
 */
import { ref, watch } from "vue";
import UzaSkeleton from "@/components/UZA/UzaSkeleton.vue";

interface PTask { num: string | null; title: string; due_date: string | null; company: string; direction: string }

const props = defineProps<{
  details: { completed: PTask[]; overdue: PTask[] } | null;
  loading: boolean;
}>();

const expandedGroups = ref<Set<string>>(new Set());
function toggleGroup(key: string) {
  const s = new Set(expandedGroups.value);
  if (s.has(key)) s.delete(key); else s.add(key);
  expandedGroups.value = s;
}
function byDirection(tasks: PTask[]): { dir: string; items: PTask[] }[] {
  const m = new Map<string, PTask[]>();
  for (const t of tasks) { if (!m.has(t.direction)) m.set(t.direction, []); m.get(t.direction)!.push(t); }
  return [...m.entries()].map(([dir, items]) => ({ dir, items })).sort((a, b) => b.items.length - a.items.length);
}
// новые детали периода → сброс развёрнутых групп
watch(() => props.details, () => { expandedGroups.value = new Set(); });
</script>

<template>
  <div class="ph-pdrill">
    <div v-if="loading" style="padding:14px 16px"><UzaSkeleton variant="rows" :rows="4" rowHeight="34px" /></div>
    <template v-else-if="details">
      <div class="ph-pdrill-cols">
        <div class="ph-pdrill-col">
          <div class="ph-pdrill-h ok">Завершено в периоде<span>{{ details.completed.length }}</span></div>
          <div v-if="!details.completed.length" class="ph-pdrill-e">нет завершённых</div>
          <div v-for="g in byDirection(details.completed)" :key="'c'+g.dir" class="ph-pdrill-g">
            <div class="ph-pdrill-dir">{{ g.dir }}<span>{{ g.items.length }}</span></div>
            <div v-for="(t,i) in (expandedGroups.has('c-'+g.dir) ? g.items : g.items.slice(0,8))" :key="i" class="ph-pdrill-t">
              <span class="ph-pdrill-bar ok"></span>
              <span class="ph-pdrill-tt"><b v-if="t.num">{{ t.num }}</b> {{ t.title }}</span>
              <span class="ph-pdrill-co">{{ t.company }}</span>
            </div>
            <button v-if="g.items.length > 8" class="ph-pdrill-more" @click="toggleGroup('c-'+g.dir)">
              {{ expandedGroups.has('c-'+g.dir) ? 'свернуть' : '+' + (g.items.length - 8) + ' ещё' }}
            </button>
          </div>
        </div>
        <div class="ph-pdrill-col">
          <div class="ph-pdrill-h od">Просрочено в периоде<span>{{ details.overdue.length }}</span></div>
          <div v-if="!details.overdue.length" class="ph-pdrill-e">нет просроченных</div>
          <div v-for="g in byDirection(details.overdue)" :key="'o'+g.dir" class="ph-pdrill-g">
            <div class="ph-pdrill-dir">{{ g.dir }}<span>{{ g.items.length }}</span></div>
            <div v-for="(t,i) in (expandedGroups.has('o-'+g.dir) ? g.items : g.items.slice(0,8))" :key="i" class="ph-pdrill-t">
              <span class="ph-pdrill-bar od"></span>
              <span class="ph-pdrill-tt"><b v-if="t.num">{{ t.num }}</b> {{ t.title }}</span>
              <span class="ph-pdrill-co">{{ t.company }}</span>
            </div>
            <button v-if="g.items.length > 8" class="ph-pdrill-more" @click="toggleGroup('o-'+g.dir)">
              {{ expandedGroups.has('o-'+g.dir) ? 'свернуть' : '+' + (g.items.length - 8) + ' ещё' }}
            </button>
          </div>
        </div>
      </div>
    </template>
  </div>
</template>

<style scoped>
/* CSS-переменные (--line/--t3/--t4/--p-deep) наследуются от родительского .ph */
.ph-pdrill { padding: 4px 18px 14px; }
.ph-pdrill-cols { display: grid; grid-template-columns: 1fr 1fr; gap: 14px; }
.ph-pdrill-col { background: #FAFAFD; border: 1px solid var(--line); border-radius: 12px; padding: 10px 12px; min-height: 60px; }
.ph-pdrill-h { display: flex; align-items: center; gap: 8px; font-size: 11.5px; font-weight: 600; padding-bottom: 8px; border-bottom: 1px solid var(--line); margin-bottom: 8px; }
.ph-pdrill-h.ok { color: #0F6E56; } .ph-pdrill-h.od { color: #B23434; }
.ph-pdrill-h span { margin-left: auto; font-size: 10.5px; background: #fff; border: 1px solid var(--line); border-radius: 8px; padding: 1px 9px; color: var(--t3); }
.ph-pdrill-e { font-size: 11.5px; color: var(--t4); padding: 8px 2px; }
.ph-pdrill-g { margin-bottom: 9px; }
.ph-pdrill-dir { display: flex; align-items: center; gap: 7px; font-size: 10px; font-weight: 600; text-transform: uppercase; letter-spacing: .04em; color: var(--p-deep); margin: 6px 0 4px; }
.ph-pdrill-dir span { font-size: 9.5px; color: var(--t4); background: rgba(124,111,247,.10); border-radius: 7px; padding: 0 6px; }
.ph-pdrill-t { display: flex; align-items: center; gap: 8px; padding: 4px 0; }
.ph-pdrill-bar { width: 3px; height: 16px; border-radius: 2px; flex-shrink: 0; } .ph-pdrill-bar.ok { background: #5DC093; } .ph-pdrill-bar.od { background: #E2807F; }
.ph-pdrill-tt { flex: 1; min-width: 0; font-size: 11.5px; color: #28324A; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; } .ph-pdrill-tt b { color: var(--t3); font-weight: 600; margin-right: 4px; }
.ph-pdrill-co { font-size: 10px; color: var(--t4); white-space: nowrap; flex-shrink: 0; max-width: 110px; overflow: hidden; text-overflow: ellipsis; }
.ph-pdrill-more { font-size: 10.5px; color: var(--p-deep); padding: 3px 6px 3px 11px; border: 0; background: transparent; cursor: pointer; font-family: inherit; font-weight: 600; border-radius: 6px; }
.ph-pdrill-more:hover { background: rgba(108,92,231,.08); text-decoration: underline; }
.ph-pdrill-more:focus-visible { outline: 2px solid #7C6FF7; outline-offset: 1px; }
</style>
