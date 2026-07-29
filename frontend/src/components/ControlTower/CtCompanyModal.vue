<script setup lang="ts">
/**
 * CtCompanyModal — модалка компании в Execution Summary: было→стало / взвешенный
 * прогресс, конкретные цифры (задачи/проекты/комментарии) и лента изменений
 * (change-trail). a11y через ModalShell. Данные ленты грузит родитель и передаёт
 * пропами; форма чисел (Co / CoDelta) разбирается внутри.
 */
import { computed } from "vue";
import ModalShell from "@/components/ModalShell.vue";
import UzaStateBlock from "@/components/UZA/UzaStateBlock.vue";
import { useI18n } from "@/composables/useI18n";

const { t } = useI18n();

interface TrailItem { ts: string; actor: string; action: string; field: string | null; old_value?: string | null; new_value?: string | null; title: string; is_critical: boolean }

const props = defineProps<{
  co: any | null;                 // Co (live-список) | CoDelta (было→стало)
  hasSnap: boolean;
  trail: TrailItem[];
  loading: boolean;
  error: string | null;
}>();
defineEmits<{ (e: "close"): void }>();

// «прогресс-интенсивность» (бренд-фиолет) — это РОСТ, не оценка плохо/хорошо.
function progColor(_v?: number | null): string { return "#7C6FF7"; }

const modalNums = computed(() => {
  const c: any = props.co;
  if (!c) return null;
  if (c.tasks_to !== undefined) {  // CoDelta
    return {
      tasks_now: c.tasks_to, tasks_snap: c.tasks_from, tasks_total: c.tasks_total,
      projects_now: c.projects_to, projects_snap: c.projects_from, projects_total: c.projects_total,
      comments_now: c.comments_to, comments_snap: c.comments_from,
    };
  }
  return {  // Co (live-список)
    tasks_now: c.tasks_done, tasks_snap: c.tasks_done_snap, tasks_total: c.tasks_total,
    projects_now: c.projects_done, projects_snap: c.projects_done_snap, projects_total: c.projects_total,
    comments_now: c.comments, comments_snap: c.comments_snap,
  };
});

function trailTime(ts: string): string {
  return new Date(ts).toLocaleString("ru-RU", { day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit" });
}
function actionRu(a: string): string {
  return ({ status_changed: t("сменил статус"), field_updated: t("обновил"), created: t("создал"), archived: t("архивировал") } as any)[a] || a;
}
</script>

<template>
  <ModalShell :open="!!co" size="md" @close="$emit('close')">
    <template #header>
      <div v-if="co" class="cmpcell"><div class="av lg" :style="{ background: co.color }">{{ co.badge }}</div><div><div class="ph-mod-name">{{ co.name }}</div><div class="ph-mod-sec">{{ co.sector }}</div></div></div>
    </template>
    <div v-if="co" class="ph-mod-inner">
      <div v-if="co.delta != null" class="ph-mod-ab">
        <div class="ph-ab-c"><div class="ph-ab-l">{{ t("Было") }}</div><div class="ph-ab-v" :style="{ color: progColor(co.from) }">{{ co.from }}%</div></div>
        <div class="ph-ab-d" :class="co.delta > 0 ? 'up' : co.delta < 0 ? 'dn' : 'fl'"><div>{{ co.delta > 0 ? '+' : '' }}{{ co.delta }}</div><small>{{ t("пп") }}</small></div>
        <div class="ph-ab-c"><div class="ph-ab-l">{{ t("Стало") }}</div><div class="ph-ab-v" :style="{ color: progColor(co.to) }">{{ co.to }}%</div></div>
      </div>
      <div v-else class="ph-mod-ab single">
        <div class="ph-ab-c"><div class="ph-ab-l">{{ t("Взвешенный прогресс") }}</div><div class="ph-ab-v" :style="{ color: progColor(co.score) }">{{ co.score ?? '—' }}<template v-if="co.score!=null">%</template></div></div>
      </div>

      <!-- конкретные цифры: завершено на момент среза vs сейчас -->
      <div v-if="modalNums" class="ph-mod-nums">
        <div class="ph-mn">
          <span class="ph-mn-l">{{ t("Задачи завершено") }}</span>
          <div class="ph-mn-v"><b>{{ modalNums.tasks_now }}</b><em>{{ t("из") }} {{ modalNums.tasks_total }}</em>
            <i v-if="hasSnap && modalNums.tasks_snap != null">{{ t("было") }} {{ modalNums.tasks_snap }}<u v-if="modalNums.tasks_now - modalNums.tasks_snap > 0"> +{{ modalNums.tasks_now - modalNums.tasks_snap }}</u></i>
          </div>
        </div>
        <div class="ph-mn">
          <span class="ph-mn-l">{{ t("Проекты завершено") }}</span>
          <div class="ph-mn-v"><b>{{ modalNums.projects_now }}</b><em>{{ t("из") }} {{ modalNums.projects_total }}</em>
            <i v-if="hasSnap && modalNums.projects_snap != null">{{ t("было") }} {{ modalNums.projects_snap }}<u v-if="modalNums.projects_now - modalNums.projects_snap > 0"> +{{ modalNums.projects_now - modalNums.projects_snap }}</u></i>
          </div>
        </div>
        <div class="ph-mn">
          <span class="ph-mn-l">{{ t("Комментарии") }}</span>
          <div class="ph-mn-v"><b>{{ modalNums.comments_now || 0 }}</b>
            <i v-if="hasSnap && modalNums.comments_snap != null">{{ t("было") }} {{ modalNums.comments_snap }}<u v-if="(modalNums.comments_now||0) - modalNums.comments_snap > 0"> +{{ (modalNums.comments_now||0) - modalNums.comments_snap }}</u></i>
          </div>
        </div>
      </div>

      <div class="ph-trail-head">{{ t("Лента изменений") }}<span>{{ t("последние 120 дней") }}</span></div>
      <div class="ph-trail">
        <UzaStateBlock v-if="loading" state="loading" variant="text" />
        <UzaStateBlock v-else-if="error" state="error" variant="block" :text="error" />
        <UzaStateBlock v-else-if="!trail.length" state="empty" variant="inline" :text="t('Изменений нет.')" />
        <div v-for="(it,i) in trail" :key="i" class="ph-tr">
          <div class="ph-tr-rail"><div class="ph-tr-dot" :style="{ background: it.is_critical ? '#E24B4A' : '#7C6FF7' }" /></div>
          <div class="ph-tr-b">
            <div class="ph-tr-l"><b>{{ it.actor }}</b> {{ actionRu(it.action) }}<template v-if="it.field"> <span class="fld">{{ it.field }}</span></template></div>
            <div v-if="it.old_value || it.new_value" class="ph-tr-c"><span class="o">{{ it.old_value || '—' }}</span><svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4"><path d="M5 12h14M13 6l6 6-6 6"/></svg><span class="n">{{ it.new_value || '—' }}</span></div>
            <div class="ph-tr-meta">{{ it.title }}</div>
          </div>
          <div class="ph-tr-t">{{ trailTime(it.ts) }}</div>
        </div>
      </div>
    </div>
  </ModalShell>
</template>

<style scoped>
/* CSS-переменные (--line/--t3/--t4/--p-deep) наследуются от родительского .ph */
.cmpcell { display: flex; align-items: center; gap: 12px; }
.av { width: 28px; height: 28px; border-radius: 8px; display: grid; place-items: center; font-size: 8.5px; font-weight: 700; color: #fff; box-shadow: inset 0 1px 1px rgba(255,255,255,.25),0 2px 6px rgba(15,23,60,.12); }
.av.lg { width: 44px; height: 44px; border-radius: 13px; font-size: 13px; }
.ph-mod-name { font-size: 16px; font-weight: 600; color: #1E2A4A; } .ph-mod-sec { font-size: 11px; color: var(--t3); margin-top: 2px; }
.ph-mod-ab { display: grid; grid-template-columns: 1fr auto 1fr; align-items: center; gap: 16px; padding: 18px 22px; margin: 16px 22px 0; background: #FAFAFD; border: 1px solid var(--line); border-radius: 13px; }
.ph-mod-ab.single { grid-template-columns: 1fr; }
.ph-ab-c { text-align: center; } .ph-ab-l { font-size: 9.5px; text-transform: uppercase; letter-spacing: .05em; color: var(--t4); }
.ph-ab-v { font-size: 34px; font-weight: 700; letter-spacing: -.035em; margin-top: 5px; font-variant-numeric: tabular-nums; line-height: 1; }
.ph-ab-d { text-align: center; font-size: 19px; font-weight: 700; padding: 8px 14px; border-radius: 11px; font-variant-numeric: tabular-nums; } .ph-ab-d.up { background: #E3F8EE; color: #0F6E56; } .ph-ab-d.dn { background: #FCE7E7; color: #B23434; } .ph-ab-d.fl { background: #F1F2F6; color: var(--t3); } .ph-ab-d small { display: block; font-size: 8.5px; text-transform: uppercase; opacity: .7; }
.ph-mod-nums { margin: 14px 22px 0; border: 1px solid var(--line); border-radius: 13px; overflow: hidden; }
.ph-mn { display: flex; align-items: center; justify-content: space-between; padding: 11px 16px; border-bottom: 1px solid var(--line); }
.ph-mn:last-child { border-bottom: 0; }
.ph-mn-l { font-size: 11.5px; color: var(--t3); }
.ph-mn-v { display: flex; align-items: baseline; gap: 6px; font-variant-numeric: tabular-nums; }
.ph-mn-v b { font-size: 18px; font-weight: 700; color: #1E2A4A; }
.ph-mn-v em { font-size: 11px; color: var(--t4); font-style: normal; }
.ph-mn-v i { font-size: 10.5px; color: var(--t4); font-style: normal; margin-left: 6px; }
.ph-mn-v i u { color: #0F6E56; font-weight: 600; text-decoration: none; }
.ph-trail-head { display: flex; align-items: baseline; justify-content: space-between; padding: 18px 22px 10px; font-size: 11px; font-weight: 600; letter-spacing: .04em; text-transform: uppercase; color: var(--t3); } .ph-trail-head span { font-size: 10px; font-weight: 500; color: var(--t4); text-transform: none; letter-spacing: 0; }
.ph-trail { overflow-y: auto; padding: 0 22px 20px; }
.ph-tr { display: flex; gap: 12px; padding: 12px 0; }
.ph-tr-rail { position: relative; display: flex; justify-content: center; width: 8px; flex-shrink: 0; }
.ph-tr-rail::before { content: ""; position: absolute; top: 14px; bottom: -12px; width: 1.5px; background: var(--line); } .ph-tr:last-child .ph-tr-rail::before { display: none; }
.ph-tr-dot { width: 8px; height: 8px; border-radius: 50%; margin-top: 4px; box-shadow: 0 0 0 3px #fff; }
.ph-tr-b { flex: 1; min-width: 0; }
.ph-tr-l { font-size: 12.5px; color: #334155; } .ph-tr-l b { font-weight: 600; color: #1E2A4A; } .fld { color: var(--p-deep); font-weight: 600; }
.ph-tr-c { display: inline-flex; align-items: center; gap: 8px; margin-top: 5px; font-size: 11.5px; } .ph-tr-c .o { color: var(--t4); text-decoration: line-through; } .ph-tr-c .n { color: #0F6E56; font-weight: 600; } .ph-tr-c svg { color: var(--t4); }
.ph-tr-meta { font-size: 10.5px; color: var(--t4); margin-top: 5px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.ph-tr-t { font-size: 10.5px; color: var(--t4); white-space: nowrap; }
</style>
