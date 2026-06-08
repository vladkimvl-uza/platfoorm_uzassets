<script setup lang="ts">
import { ref, onMounted, computed } from "vue";
import { useRouter } from "vue-router";
import { watchesApi, type WatchedItem } from "@/api/watches";

const router = useRouter();
const items = ref<WatchedItem[]>([]);
const loading = ref(true);

const HEALTH: Record<string, { c: string; l: string }> = {
  on_track: { c: "#1D9E75", l: "В графике" },
  at_risk:  { c: "#EF9F27", l: "Под риском" },
  delayed:  { c: "#E24B4A", l: "Задержка" },
  blocked:  { c: "#7A1F1F", l: "Блокер" },
};
const STATUS: Record<string, { c: string; l: string }> = {
  init: { c: "#94A3B8", l: "Инициировано" }, new: { c: "#94A3B8", l: "Не начато" },
  active: { c: "#378ADD", l: "В процессе" }, review: { c: "#7F77DD", l: "На проверке" },
  done: { c: "#1D9E75", l: "Завершено" }, quarterly: { c: "#7F77DD", l: "Ежеквартально" },
  monthly: { c: "#7F77DD", l: "Ежемесячно" }, ongoing: { c: "#7F77DD", l: "Постоянно" },
  deferred: { c: "#94A3B8", l: "Отложено" },
};

async function load() {
  loading.value = true;
  try { items.value = await watchesApi.mine(); } catch { /* ignore */ } finally { loading.value = false; }
}
onMounted(load);

const projects = computed(() => items.value.filter((i) => i.entity_type === "project"));
const tasks = computed(() => items.value.filter((i) => i.entity_type === "task"));

function overdueDays(due: string | null): number | null {
  if (!due) return null;
  const d = new Date(due); if (Number.isNaN(d.getTime())) return null;
  const diff = Math.floor((Date.now() - d.getTime()) / 86400000);
  return diff > 0 ? diff : null;
}
function fmtDue(due: string | null): string {
  if (!due) return "—";
  const d = new Date(due);
  return `${String(d.getDate()).padStart(2, "0")}.${String(d.getMonth() + 1).padStart(2, "0")}.${d.getFullYear()}`;
}
function openItem(it: WatchedItem) {
  if (it.company_id) router.push(`/library/companies/${it.company_id}`);
}
async function unfollow(it: WatchedItem, ev: Event) {
  ev.stopPropagation();
  try { await watchesApi.unfollow(it.entity_type, it.entity_id); items.value = items.value.filter((x) => !(x.entity_type === it.entity_type && x.entity_id === it.entity_id)); } catch { /* ignore */ }
}
</script>

<template>
  <div class="fl-page">
    <div class="fl-head">
      <div>
        <div class="fl-eyebrow">UzAssets · Отслеживание</div>
        <h1 class="fl-title">Отслеживаемое</h1>
        <div class="fl-sub">Проекты и задачи, об изменениях которых вы получаете уведомления</div>
      </div>
      <div class="fl-count">{{ items.length }}</div>
    </div>

    <div v-if="loading" class="fl-state">Загрузка…</div>
    <div v-else-if="!items.length" class="fl-empty">
      <svg width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="#C7CCD9" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M1 12s4-7 11-7 11 7 11 7-4 7-11 7-11-7-11-7z"/><circle cx="12" cy="12" r="3"/></svg>
      <div class="fl-empty-t">Пока ничего не отслеживается</div>
      <div class="fl-empty-s">Откройте проект или задачу и нажмите «Отслеживать». Подписка добавляется автоматически, когда вы создаёте, комментируете или обновляете статус.</div>
    </div>

    <template v-else>
      <section v-for="(grp, gi) in [{ k: 'project', l: 'Проекты', rows: projects }, { k: 'task', l: 'Задачи', rows: tasks }]" :key="gi">
        <template v-if="grp.rows.length">
          <div class="fl-group-label">{{ grp.l }} · {{ grp.rows.length }}</div>
          <div class="fl-list">
            <div v-for="it in grp.rows" :key="it.entity_id" class="fl-row" @click="openItem(it)">
              <span class="fl-dot" :style="{ background: (it.current_health && HEALTH[it.current_health]) ? HEALTH[it.current_health].c : '#C7CCD9' }"
                    :title="(it.current_health && HEALTH[it.current_health]) ? HEALTH[it.current_health].l : 'Нет оценки хода'"></span>
              <div class="fl-main">
                <div class="fl-row-title">
                  <span v-if="it.num" class="fl-num">{{ it.num }}</span>{{ it.title }}
                </div>
                <div class="fl-row-meta">{{ it.company_name || "—" }}</div>
              </div>
              <span class="fl-status" :style="{ '--sc': (STATUS[it.status]?.c || '#94A3B8') }">
                <span class="fl-status-dot"></span>{{ STATUS[it.status]?.l || it.status }}
              </span>
              <div class="fl-due" :class="{ overdue: overdueDays(it.due_date) }">
                {{ fmtDue(it.due_date) }}
                <span v-if="overdueDays(it.due_date)" class="fl-overdue">просрочено {{ overdueDays(it.due_date) }} дн</span>
              </div>
              <button class="fl-unfollow" @click="unfollow(it, $event)" title="Перестать отслеживать">
                <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19m-6.72-1.07a3 3 0 1 1-4.24-4.24"/><line x1="1" y1="1" x2="23" y2="23"/></svg>
              </button>
            </div>
          </div>
        </template>
      </section>
    </template>
  </div>
</template>

<style scoped>
.fl-page { max-width: 1100px; margin: 0 auto; padding: 28px 24px 60px; }
.fl-head { display: flex; align-items: flex-start; justify-content: space-between; margin-bottom: 22px; }
.fl-eyebrow { font-size: 10px; font-weight: 600; text-transform: uppercase; letter-spacing: .08em; color: var(--t3, #94A3B8); }
.fl-title { font-size: 22px; font-weight: 500; letter-spacing: -.02em; color: var(--t1, #1E2A4A); margin: 4px 0 3px; }
.fl-sub { font-size: 12.5px; color: var(--t3, #94A3B8); }
.fl-count { font-size: 22px; font-weight: 400; color: var(--p-deep, #534AB7); background: rgba(127,119,221,.10); border-radius: 12px; padding: 6px 16px; }
.fl-state, .fl-empty { text-align: center; color: var(--t3, #94A3B8); padding: 50px 20px; }
.fl-empty { display: flex; flex-direction: column; align-items: center; gap: 10px; }
.fl-empty-t { font-size: 15px; font-weight: 500; color: var(--t1, #1E2A4A); }
.fl-empty-s { font-size: 12.5px; max-width: 440px; line-height: 1.5; }
.fl-group-label { font-size: 10px; font-weight: 600; text-transform: uppercase; letter-spacing: .07em; color: var(--t3, #94A3B8); margin: 18px 0 8px; }
.fl-list { display: flex; flex-direction: column; gap: 6px; }
.fl-row {
  display: grid; grid-template-columns: 10px 1fr 150px 150px 32px; gap: 14px; align-items: center;
  padding: 12px 16px; border-radius: 12px; background: #fff;
  border: 1px solid rgba(15,23,60,.06); box-shadow: 0 1px 3px rgba(15,23,60,.04);
  cursor: pointer; transition: box-shadow .14s, transform .14s, border-color .14s;
}
.fl-row:hover { box-shadow: 0 6px 18px rgba(15,23,60,.10); transform: translateY(-1px); border-color: rgba(127,119,221,.25); }
.fl-dot { width: 10px; height: 10px; border-radius: 50%; box-shadow: 0 0 0 3px color-mix(in srgb, currentColor 0%, transparent); }
.fl-main { min-width: 0; }
.fl-row-title { font-size: 13.5px; font-weight: 500; color: var(--t1, #1E2A4A); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.fl-num { font-size: 11px; color: var(--t3, #94A3B8); margin-right: 7px; font-variant-numeric: tabular-nums; }
.fl-row-meta { font-size: 11.5px; color: var(--t3, #94A3B8); margin-top: 2px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.fl-status { display: inline-flex; align-items: center; gap: 6px; font-size: 11.5px; font-weight: 500; color: var(--sc); }
.fl-status-dot { width: 7px; height: 7px; border-radius: 50%; background: var(--sc); }
.fl-due { font-size: 12px; font-weight: 500; color: rgba(30,42,74,.65); font-variant-numeric: tabular-nums; text-align: right; }
.fl-due.overdue { color: #E24B4A; font-weight: 600; }
.fl-overdue { display: block; font-size: 10px; font-weight: 600; color: #E24B4A; margin-top: 2px; }
.fl-unfollow { width: 30px; height: 30px; border-radius: 8px; border: none; background: transparent; color: var(--t3, #94A3B8); cursor: pointer; display: flex; align-items: center; justify-content: center; opacity: 0; transition: opacity .14s, background .14s, color .14s; }
.fl-row:hover .fl-unfollow { opacity: 1; }
.fl-unfollow:hover { background: rgba(226,75,74,.10); color: #E24B4A; }
@media (max-width: 700px) {
  .fl-row { grid-template-columns: 10px 1fr auto; }
  .fl-status, .fl-due { display: none; }
}
</style>
