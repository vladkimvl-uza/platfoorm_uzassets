<script setup lang="ts">
import Odometer from "@/components/Odometer.vue";
import { ref, onMounted, computed, watch } from "vue";
import { watchesApi, type WatchedItem } from "@/api/watches";
import { getPlatformUpdatingMessage } from "@/api/client";
import { useEntityEditor } from "@/composables/useEntityEditor";
import { useToast } from "@/composables/useToast";
import { useI18n } from "@/composables/useI18n";
import { i18nKey } from "@/locale/keys";
import { resolveCompanyDisplayName } from "@/utils/displayNames";

const { t } = useI18n();


const { openTask, openProject } = useEntityEditor();
const toast = useToast();
const items = ref<WatchedItem[]>([]);
const loading = ref(true);
const loadError = ref(false);

const HEALTH: Record<string, { c: string; l: string }> = {
  on_track: { c: "#1D9E75", l: i18nKey("В графике") },
  at_risk:  { c: "#EF9F27", l: i18nKey("Под риском") },
  delayed:  { c: "#E24B4A", l: i18nKey("Задержка") },
  blocked:  { c: "#7A1F1F", l: i18nKey("Блокер") },
};
const STATUS: Record<string, { c: string; l: string }> = {
  init: { c: "#94A3B8", l: i18nKey("Инициировано") }, new: { c: "#94A3B8", l: i18nKey("Не начато") },
  active: { c: "#378ADD", l: i18nKey("В процессе") }, review: { c: "#7F77DD", l: i18nKey("На проверке") },
  done: { c: "#1D9E75", l: i18nKey("Завершено") }, quarterly: { c: "#7F77DD", l: i18nKey("Ежеквартально") },
  monthly: { c: "#7F77DD", l: i18nKey("Ежемесячно") }, ongoing: { c: "#7F77DD", l: i18nKey("Постоянно") },
  deferred: { c: "#94A3B8", l: i18nKey("Отложено") },
};
const RISK_HEALTH = new Set(["at_risk", "delayed", "blocked"]);

async function load() {
  loading.value = true; loadError.value = false;
  try {
    items.value = await watchesApi.mine();
  } catch (e: any) {
    loadError.value = true;
    toast.error(e?.message || t('Не удалось загрузить отслеживаемое'));
  } finally { loading.value = false; }
}
onMounted(load);

// ─── filters ──────────────────────────────────────────────
type TypeFilter = "all" | "project" | "task";
const fType = ref<TypeFilter>("all");
const fOverdue = ref(false);
const search = ref("");

function overdueDays(due: string | null, status?: string): number | null {
  if (!due) return null;
  // Завершённые и бессрочно-повторяющиеся не бывают «просроченными».
  if (status === "done" || status === "monthly" || status === "ongoing") return null;
  const d = new Date(due); if (Number.isNaN(d.getTime())) return null;
  // due приходит как дата-only (UTC-полночь) → нормализуем к ЛОКАЛЬНОЙ полуночи,
  // иначе сравнение с wall-clock даёт сдвиг ±1 день по часу суток.
  d.setHours(0, 0, 0, 0);
  const today = new Date(); today.setHours(0, 0, 0, 0);
  const diff = Math.floor((today.getTime() - d.getTime()) / 86400000);
  return diff > 0 ? diff : null;
}
function dueTs(due: string | null): number {
  if (!due) return Number.POSITIVE_INFINITY;
  const d = new Date(due); return Number.isNaN(d.getTime()) ? Number.POSITIVE_INFINITY : d.getTime();
}
function fmtDue(due: string | null): string {
  if (!due) return "—";
  const d = new Date(due);
  return `${String(d.getDate()).padStart(2, "0")}.${String(d.getMonth() + 1).padStart(2, "0")}.${d.getFullYear()}`;
}

const filtered = computed(() => {
  const q = search.value.trim().toLowerCase();
  return items.value
    .filter((i) => fType.value === "all" || i.entity_type === fType.value)
    .filter((i) => !fOverdue.value || overdueDays(i.due_date, i.status) !== null)
    .filter((i) => !q || `${i.num || ""} ${i.title} ${i.company_name || ""} ${resolveCompanyDisplayName(i.company_name, i.company_id)}`.toLowerCase().includes(q))
    .slice()
    .sort((a, b) => {
      const oa = overdueDays(a.due_date, a.status), ob = overdueDays(b.due_date, b.status);
      if ((oa !== null) !== (ob !== null)) return oa !== null ? -1 : 1; // overdue first
      return dueTs(a.due_date) - dueTs(b.due_date);                      // then by due date
    });
});

// ─── stats (animated count-up) ────────────────────────────
const stats = computed(() => {
  const total = items.value.length;
  const overdue = items.value.filter((i) => overdueDays(i.due_date, i.status) !== null).length;
  const risk = items.value.filter((i) => i.current_health && RISK_HEALTH.has(i.current_health)).length;
  const done = items.value.filter((i) => i.status === "done").length;
  return { total, overdue, risk, done };
});

const disp = ref({ total: 0, overdue: 0, risk: 0, done: 0 });
let _raf = 0;
function animateCounts() {
  cancelAnimationFrame(_raf);
  const from = { ...disp.value };
  const to = stats.value;
  const start = performance.now();
  const dur = 600;
  const ease = (t: number) => 1 - Math.pow(1 - t, 3);
  const step = (now: number) => {
    const p = Math.min(1, (now - start) / dur);
    const e = ease(p);
    disp.value = {
      total: Math.round(from.total + (to.total - from.total) * e),
      overdue: Math.round(from.overdue + (to.overdue - from.overdue) * e),
      risk: Math.round(from.risk + (to.risk - from.risk) * e),
      done: Math.round(from.done + (to.done - from.done) * e),
    };
    if (p < 1) _raf = requestAnimationFrame(step);
  };
  _raf = requestAnimationFrame(step);
}
watch(() => stats.value, animateCounts, { deep: true });
watch(loading, (v) => { if (!v) animateCounts(); });

function openItem(it: WatchedItem) {
  // Открываем глобальную карточку проекта/задачи (как в Календаре), а не страницу компании.
  if (it.entity_type === "project") openProject(it.entity_id);
  else openTask(it.entity_id);
}
const _unfollowing = ref<Set<string>>(new Set());
async function unfollow(it: WatchedItem, ev: Event) {
  ev.stopPropagation();
  const key = it.entity_type + ":" + it.entity_id;
  if (_unfollowing.value.has(key)) return;            // защита от двойного клика
  _unfollowing.value.add(key);
  const snapshot = items.value;
  items.value = items.value.filter((x) => !(x.entity_type === it.entity_type && x.entity_id === it.entity_id));
  try {
    await watchesApi.unfollow(it.entity_type, it.entity_id);
    toast.success(t('Вы перестали отслеживать'));
  } catch (e: any) {
    items.value = snapshot;                            // откат оптимистичного удаления
    toast.error(e?.message || t('Не удалось отписаться'));
  } finally { _unfollowing.value.delete(key); }
}
</script>

<template>
  <div class="fl-page">
    <!-- Header -->
    <div class="fl-head">
      <div class="fl-head-l">
        <div class="fl-eyebrow">{{ t('UzAssets · Отслеживание') }}</div>
        <h1 class="fl-title">{{ t('Отслеживаемое') }}</h1>
        <div class="fl-sub">{{ t('Проекты и задачи, об изменениях которых вы получаете уведомления') }}</div>
      </div>
      <div class="fl-live" :title="t('{value0} в отслеживании', { value0: items.length })">
        <span class="fl-live-dot"></span><Odometer :value="items.length" />
      </div>
    </div>

    <!-- Stat tiles -->
    <div class="fl-stats">
      <div class="fl-stat" :class="{ pop: !loading }" style="--d:0ms">
        <div class="fl-stat-n">{{ disp.total }}</div>
        <div class="fl-stat-l">{{ t('Всего') }}</div>
      </div>
      <div class="fl-stat danger" :class="{ pop: !loading, on: stats.overdue > 0 }" style="--d:60ms">
        <div class="fl-stat-n">{{ disp.overdue }}</div>
        <div class="fl-stat-l">{{ t('Просрочено') }}</div>
      </div>
      <div class="fl-stat warn" :class="{ pop: !loading, on: stats.risk > 0 }" style="--d:120ms">
        <div class="fl-stat-n">{{ disp.risk }}</div>
        <div class="fl-stat-l">{{ t('Под риском') }}</div>
      </div>
      <div class="fl-stat ok" :class="{ pop: !loading, on: stats.done > 0 }" style="--d:180ms">
        <div class="fl-stat-n">{{ disp.done }}</div>
        <div class="fl-stat-l">{{ t('Завершено') }}</div>
      </div>
    </div>

    <!-- Toolbar -->
    <div v-if="!loading && items.length" class="fl-toolbar">
      <div class="uza-seg">
        <button :class="['uza-seg-btn', { on: fType === 'all' }]" @click="fType = 'all'">{{ t('Все') }}</button>
        <button :class="['uza-seg-btn', { on: fType === 'project' }]" @click="fType = 'project'">{{ t('Проекты') }}</button>
        <button :class="['uza-seg-btn', { on: fType === 'task' }]" @click="fType = 'task'">{{ t('Задачи') }}</button>
      </div>
      <button class="fl-chip" :class="{ active: fOverdue }" @click="fOverdue = !fOverdue">
        <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/></svg>
        {{ t('Просроченные') }}
      </button>
      <div class="fl-search">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="11" cy="11" r="7"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg>
        <input v-model="search" type="text" :placeholder="t('Поиск по названию, № или компании')" />
        <button v-if="search" class="fl-search-x" @click="search = ''" :title="t('Очистить')">
          <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
        </button>
      </div>
    </div>

    <!-- Loading skeletons -->
    <div v-if="loading" class="fl-list">
      <div v-for="n in 5" :key="n" class="fl-skel" :style="{ '--d': (n * 70) + 'ms' }">
        <span class="fl-skel-bar"></span>
        <div class="fl-skel-main"><span class="fl-skel-line w60"></span><span class="fl-skel-line w35"></span></div>
        <span class="fl-skel-pill"></span>
      </div>
    </div>

    <!-- Error state (load failed) -->
    <div v-else-if="loadError" class="fl-empty">
      <div class="fl-empty-ic">
        <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="#E24B4A" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="9"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg>
      </div>
      <div class="fl-empty-t">{{ t('Не удалось загрузить') }}</div>
      <div class="fl-empty-s">{{ getPlatformUpdatingMessage() }}</div>
      <button class="fl-reset" @click="load">{{ t('Повторить') }}</button>
    </div>

    <!-- Empty (nothing followed at all) -->
    <div v-else-if="!items.length" class="fl-empty">
      <div class="fl-empty-ic">
        <svg width="34" height="34" viewBox="0 0 24 24" fill="none" stroke="#C7CCD9" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M1 12s4-7 11-7 11 7 11 7-4 7-11 7-11-7-11-7z"/><circle cx="12" cy="12" r="3"/></svg>
      </div>
      <div class="fl-empty-t">{{ t('Пока ничего не отслеживается') }}</div>
      <div class="fl-empty-s">{{ t('Откройте проект или задачу и нажмите «Отслеживать». Подписка добавляется автоматически, когда вы создаёте, комментируете или обновляете статус.') }}</div>
    </div>

    <!-- Empty (filtered out) -->
    <div v-else-if="!filtered.length" class="fl-empty sm">
      <div class="fl-empty-t">{{ t('Ничего не найдено') }}</div>
      <div class="fl-empty-s">{{ t('Под текущие фильтры ничего не подошло.') }}</div>
      <button class="fl-reset" @click="fType = 'all'; fOverdue = false; search = ''">{{ t('Сбросить фильтры') }}</button>
    </div>

    <!-- List -->
    <TransitionGroup v-else tag="div" name="fl" class="fl-list">
      <div
        v-for="(it, i) in filtered"
        :key="it.entity_type + ':' + it.entity_id"
        class="fl-row"
        role="button"
        tabindex="0"
        :style="{ '--i': i, '--hc': (it.current_health && HEALTH[it.current_health]) ? HEALTH[it.current_health].c : '#C7CCD9' }"
        @click="openItem(it)"
        @keydown.enter.prevent="openItem(it)"
        @keydown.space.prevent="openItem(it)"
      >
        <span class="fl-accent"></span>
        <span
          class="fl-dot"
          :class="{ pulse: it.current_health && RISK_HEALTH.has(it.current_health) }"
          :title="(it.current_health && HEALTH[it.current_health]) ? t(HEALTH[it.current_health].l) : t('Нет оценки хода')"
        ></span>
        <div class="fl-main">
          <div class="fl-row-title">
            <span v-if="it.num" class="fl-num">{{ it.num }}</span>{{ it.title }}
          </div>
          <div class="fl-row-meta">
            <span class="fl-type">{{ it.entity_type === "project" ? t('Проект') : t('Задача') }}</span>
            <span class="fl-meta-sep">·</span>
            <span class="fl-co">{{ resolveCompanyDisplayName(it.company_name, it.company_id) || "—" }}</span>
            <template v-if="it.current_health && HEALTH[it.current_health]">
              <span class="fl-meta-sep">·</span>
              <span class="fl-health" :style="{ color: HEALTH[it.current_health].c }">{{ t(HEALTH[it.current_health].l) }}</span>
            </template>
          </div>
        </div>
        <span class="fl-status" :style="{ '--sc': (STATUS[it.status]?.c || '#94A3B8') }">
          <span class="fl-status-dot"></span>{{ STATUS[it.status]?.l ? t(STATUS[it.status].l) : it.status }}
        </span>
        <div class="fl-due" :class="{ overdue: overdueDays(it.due_date, it.status) }">
          <span class="fl-due-d">{{ fmtDue(it.due_date) }}</span>
          <span v-if="overdueDays(it.due_date, it.status)" class="fl-overdue">{{ t('просрочено') }} {{ overdueDays(it.due_date, it.status) }} {{ t('дн') }}</span>
        </div>
        <button class="fl-unfollow" @click="unfollow(it, $event)" :title="t('Перестать отслеживать')">
          <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19m-6.72-1.07a3 3 0 1 1-4.24-4.24"/><line x1="1" y1="1" x2="23" y2="23"/></svg>
        </button>
      </div>
    </TransitionGroup>
  </div>
</template>

<style scoped>
.fl-page { max-width: 1100px; margin: 0 auto; padding: 28px 24px 60px; --ease: cubic-bezier(.34, 1.2, .64, 1); }

/* Header */
.fl-head { display: flex; align-items: flex-start; justify-content: space-between; margin-bottom: 20px; animation: flFade .5s var(--ease) backwards; }
.fl-eyebrow { font-size: 10px; font-weight: 600; text-transform: uppercase; letter-spacing: .08em; color: var(--t3, #94A3B8); }
.fl-title { font-size: 22px; font-weight: 500; letter-spacing: -.02em; color: var(--t1, #1E2A4A); margin: 4px 0 3px; }
.fl-sub { font-size: 12.5px; color: var(--t3, #94A3B8); }
.fl-live { display: inline-flex; align-items: center; gap: 7px; font-size: 16px; font-weight: 500; color: var(--p-deep, #534AB7); background: rgba(127,119,221,.10); border-radius: 11px; padding: 7px 14px; font-variant-numeric: tabular-nums; }
.fl-live-dot { width: 7px; height: 7px; border-radius: 50%; background: #7F77DD; box-shadow: 0 0 0 0 rgba(127,119,221,.5); animation: flLive 2.2s var(--ease) infinite; }
@keyframes flLive { 0% { box-shadow: 0 0 0 0 rgba(127,119,221,.5); } 70% { box-shadow: 0 0 0 6px rgba(127,119,221,0); } 100% { box-shadow: 0 0 0 0 rgba(127,119,221,0); } }

/* Stat tiles */
.fl-stats { display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px; margin-bottom: 20px; }
.fl-stat { position: relative; overflow: hidden; background: #fff; border: 1px solid rgba(15,23,60,.06); border-radius: 14px; padding: 16px 18px; box-shadow: 0 1px 3px rgba(15,23,60,.04); opacity: 0; transform: translateY(8px); }
.fl-stat.pop { animation: flUp .5s var(--ease) forwards; animation-delay: var(--d, 0ms); }
.fl-stat::after { content: ""; position: absolute; left: 0; right: 0; top: 0; height: 3px; background: #C7CCD9; opacity: .5; border-radius: inherit; border-bottom-left-radius: 0; border-bottom-right-radius: 0; }
.fl-stat.danger.on::after { background: #E24B4A; opacity: 1; }
.fl-stat.warn.on::after { background: #EF9F27; opacity: 1; }
.fl-stat.ok.on::after { background: #1D9E75; opacity: 1; }
.fl-stat-n { font-size: 26px; font-weight: 400; letter-spacing: -.025em; color: var(--t1, #1E2A4A); font-variant-numeric: tabular-nums; line-height: 1; }
.fl-stat.danger.on .fl-stat-n { color: #E24B4A; }
.fl-stat.warn.on .fl-stat-n { color: #C77A0A; }
.fl-stat.ok.on .fl-stat-n { color: #1D9E75; }
.fl-stat-l { font-size: 10px; font-weight: 500; text-transform: uppercase; letter-spacing: .06em; color: var(--t3, #94A3B8); margin-top: 8px; }

/* Toolbar */
.fl-toolbar { display: flex; align-items: center; gap: 10px; margin-bottom: 16px; flex-wrap: wrap; animation: flFade .5s var(--ease) backwards .12s; }
.fl-chip { display: inline-flex; align-items: center; gap: 6px; font-size: 12px; font-weight: 500; color: var(--t3, #6B7280); background: rgba(15,23,60,.05); border: 1px solid transparent; border-radius: 10px; padding: 7px 12px; cursor: pointer; transition: all .18s var(--ease); }
.fl-chip:hover { background: rgba(15,23,60,.08); }
.fl-chip.active { color: #E24B4A; background: rgba(226,75,74,.08); border-color: rgba(226,75,74,.25); }
.fl-search { display: inline-flex; align-items: center; gap: 8px; flex: 1; min-width: 200px; background: #fff; border: 1px solid rgba(15,23,60,.08); border-radius: 10px; padding: 0 12px; color: var(--t3, #94A3B8); transition: border-color .18s var(--ease), box-shadow .18s var(--ease); }
.fl-search:focus-within { border-color: rgba(127,119,221,.45); box-shadow: 0 0 0 3px rgba(127,119,221,.10); }
.fl-search input { flex: 1; border: none; outline: none; background: transparent; font-size: 12.5px; color: var(--t1, #1E2A4A); padding: 9px 0; }
.fl-search input::placeholder { color: var(--t3, #B0B6C3); }
.fl-search-x { border: none; background: transparent; color: var(--t3, #94A3B8); cursor: pointer; display: flex; padding: 2px; border-radius: 6px; transition: color .15s, background .15s; }
.fl-search-x:hover { color: #E24B4A; background: rgba(226,75,74,.08); }

/* List */
.fl-list { display: flex; flex-direction: column; gap: 7px; position: relative; }
.fl-row {
  position: relative; display: grid;
  grid-template-columns: 10px 1fr 154px 150px 32px; gap: 14px; align-items: center;
  padding: 13px 16px 13px 18px; border-radius: 12px; background: #fff;
  border: 1px solid rgba(15,23,60,.06); box-shadow: 0 1px 3px rgba(15,23,60,.04);
  cursor: pointer; overflow: hidden;
  transition: box-shadow .16s var(--ease), transform .16s var(--ease), border-color .16s var(--ease);
  animation: flRowIn .42s var(--ease) backwards; animation-delay: calc(var(--i, 0) * 38ms);
}
.fl-row:hover { box-shadow: 0 8px 22px rgba(15,23,60,.11); transform: translateY(-2px); border-color: rgba(127,119,221,.22); }
/* Акцент = ВЕРХНЯЯ полоса (top-accent), не цветной left-border (UI-эталон). */
.fl-accent { position: absolute; left: 0; right: 0; top: 0; height: 3px; background: var(--hc); border-radius: 3px 3px 0 0; transform: scaleX(.55); transform-origin: left; opacity: .8; transition: transform .18s var(--ease), opacity .18s var(--ease); }
.fl-row:hover .fl-accent { transform: scaleX(1); opacity: 1; }
.fl-row:focus-visible { outline: 2px solid #7F77DD; outline-offset: 2px; }
.fl-dot { width: 10px; height: 10px; border-radius: 50%; background: var(--hc); }
.fl-dot.pulse { animation: flDot 1.8s var(--ease) infinite; }
@keyframes flDot { 0% { box-shadow: 0 0 0 0 var(--hc); } 70% { box-shadow: 0 0 0 5px transparent; } 100% { box-shadow: 0 0 0 0 transparent; } }
.fl-main { min-width: 0; }
.fl-row-title { font-size: 13.5px; font-weight: 500; color: var(--t1, #1E2A4A); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.fl-num { font-size: 11px; color: var(--t3, #94A3B8); margin-right: 7px; font-variant-numeric: tabular-nums; }
.fl-row-meta { font-size: 11.5px; color: var(--t3, #94A3B8); margin-top: 3px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; display: flex; align-items: center; gap: 6px; }
.fl-type { font-size: 10px; font-weight: 600; text-transform: uppercase; letter-spacing: .05em; color: var(--p, #7F77DD); background: rgba(127,119,221,.10); border-radius: 5px; padding: 2px 6px; }
.fl-meta-sep { opacity: .5; }
.fl-co { overflow: hidden; text-overflow: ellipsis; }
.fl-health { font-weight: 500; }
.fl-status { display: inline-flex; align-items: center; gap: 6px; font-size: 11.5px; font-weight: 500; color: var(--sc); }
.fl-status-dot { width: 7px; height: 7px; border-radius: 50%; background: var(--sc); flex-shrink: 0; }
.fl-due { font-size: 12px; font-weight: 500; color: rgba(30,42,74,.62); font-variant-numeric: tabular-nums; text-align: right; }
.fl-due.overdue .fl-due-d { color: #E24B4A; font-weight: 600; }
.fl-overdue { display: block; font-size: 10px; font-weight: 600; color: #E24B4A; margin-top: 2px; }
.fl-unfollow { width: 30px; height: 30px; border-radius: 8px; border: none; background: transparent; color: var(--t3, #94A3B8); cursor: pointer; display: flex; align-items: center; justify-content: center; opacity: 0; transform: scale(.8); transition: opacity .16s var(--ease), background .16s, color .16s, transform .16s var(--ease); }
.fl-row:hover .fl-unfollow,
.fl-row:focus-within .fl-unfollow { opacity: 1; transform: scale(1); }
.fl-unfollow:hover { background: rgba(226,75,74,.10); color: #E24B4A; }
.fl-unfollow:active { transform: scale(.88); }
.fl-unfollow:focus-visible { opacity: 1; transform: scale(1); outline: 2px solid #E24B4A; outline-offset: 1px; }
/* На тач-устройствах hover недоступен → кнопка отписки всегда видима. */
@media (hover: none) { .fl-unfollow { opacity: 1; transform: none; } }

/* TransitionGroup: leave + move (FLIP) */
.fl-move { transition: transform .4s var(--ease); }
.fl-leave-active { transition: opacity .3s var(--ease), transform .3s var(--ease); position: absolute; width: 100%; z-index: 0; }
.fl-leave-to { opacity: 0; transform: translateX(28px) scale(.97); }

/* Skeletons */
.fl-skel { display: grid; grid-template-columns: 10px 1fr 120px; gap: 14px; align-items: center; padding: 14px 16px; border-radius: 12px; background: #fff; border: 1px solid rgba(15,23,60,.05); opacity: 0; animation: flFade .4s var(--ease) forwards; animation-delay: var(--d, 0ms); }
.fl-skel-bar, .fl-skel-line, .fl-skel-pill { background: linear-gradient(90deg, #EEF0F5 25%, #F6F7FA 37%, #EEF0F5 63%); background-size: 400% 100%; animation: flShimmer 1.4s ease infinite; border-radius: 6px; }
.fl-skel-bar { width: 10px; height: 10px; border-radius: 50%; }
.fl-skel-main { display: flex; flex-direction: column; gap: 7px; }
.fl-skel-line { height: 11px; } .fl-skel-line.w60 { width: 60%; } .fl-skel-line.w35 { width: 35%; }
.fl-skel-pill { height: 18px; width: 100px; border-radius: 9px; }
@keyframes flShimmer { 0% { background-position: 100% 0; } 100% { background-position: 0 0; } }

/* Empty */
.fl-empty { text-align: center; color: var(--t3, #94A3B8); padding: 56px 20px; display: flex; flex-direction: column; align-items: center; gap: 10px; animation: flUp .5s var(--ease) backwards; }
.fl-empty.sm { padding: 40px 20px; }
.fl-empty-ic { width: 68px; height: 68px; border-radius: 50%; display: flex; align-items: center; justify-content: center; background: rgba(127,119,221,.07); margin-bottom: 2px; }
.fl-empty-t { font-size: 15px; font-weight: 500; color: var(--t1, #1E2A4A); }
.fl-empty-s { font-size: 12.5px; max-width: 440px; line-height: 1.5; }
.fl-reset { margin-top: 8px; border: 1px solid rgba(127,119,221,.30); background: rgba(127,119,221,.06); color: var(--p-deep, #534AB7); font-size: 12px; font-weight: 500; border-radius: 8px; padding: 7px 16px; cursor: pointer; transition: background .16s var(--ease); }
.fl-reset:hover { background: rgba(127,119,221,.12); }

/* Keyframes */
@keyframes flFade { from { opacity: 0; } to { opacity: 1; } }
@keyframes flUp { from { opacity: 0; transform: translateY(10px); } to { opacity: 1; transform: translateY(0); } }
@keyframes flRowIn { from { opacity: 0; transform: translateY(10px); } to { opacity: 1; transform: translateY(0); } }

@media (max-width: 760px) {
  .fl-stats { grid-template-columns: repeat(2, 1fr); }
  /* Дедлайн критичен — оставляем его на мобиле; прячем только текст статуса
     (его дублирует цветная точка хода). */
  .fl-row { grid-template-columns: 10px 1fr auto auto; }
  .fl-status { display: none; }
  .fl-search { min-width: 100%; order: 3; }
}
@media (prefers-reduced-motion: reduce) {
  .fl-row, .fl-stat, .fl-head, .fl-toolbar, .fl-empty, .fl-skel { animation: none !important; opacity: 1 !important; transform: none !important; }
  .fl-dot.pulse, .fl-live-dot { animation: none !important; }
}
</style>
