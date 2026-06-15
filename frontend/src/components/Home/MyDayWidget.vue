<script setup lang="ts">
/**
 * MyDayWidget — личный виджет «Мой день» на главной.
 *
 * Вкладки: Обновления · Задачи · Уведомления. Сводные чипы сверху.
 * Источники: мои задачи (tasksApi assignee=me), стор уведомлений (обновления +
 * непрочитанные). Премиум-анимации (смена вкладок, stagger списков).
 */
import { computed, onMounted, ref } from "vue";
import { useRouter } from "vue-router";
import { useAuthStore } from "@/stores/auth";
import { useNotificationsStore } from "@/stores/notifications";
import { useEntityEditor } from "@/composables/useEntityEditor";
import { describeNotification, NOTIF_ICON_PATHS } from "@/composables/useNotificationMeta";
import { formatRelativeTime } from "@/api/notifications";
import { tasksApi, type TaskBrief } from "@/api/tasks";

const auth = useAuthStore();
const notif = useNotificationsStore();
const router = useRouter();
const entityEditor = useEntityEditor();

type TabKey = "updates" | "tasks" | "notifs";
const tab = ref<TabKey>("updates");

// ─── Мои задачи ───
const myTasks = ref<TaskBrief[]>([]);
const tasksLoading = ref(true);
onMounted(async () => {
  notif.refreshRecent?.();
  if (!auth.user?.email) { tasksLoading.value = false; return; }
  try {
    const res = await tasksApi.list({ assignee_email: auth.user.email, limit: 30 });
    const items = (res as any).items || (Array.isArray(res) ? res : []);
    myTasks.value = items.filter((t: any) => t.status !== "done");
  } catch { myTasks.value = []; }
  finally { tasksLoading.value = false; }
});

function dueRank(t: any): number {
  if (!t.due_date) return 3;
  const d = new Date(t.due_date).getTime();
  const today = new Date(); today.setHours(0, 0, 0, 0);
  if (d < today.getTime()) return 0;          // просрочено
  if (d < today.getTime() + 86400000) return 1; // сегодня
  return 2;
}
const sortedTasks = computed(() =>
  [...myTasks.value].sort((a, b) => {
    const r = dueRank(a) - dueRank(b);
    if (r !== 0) return r;
    return (new Date(a.due_date || 0).getTime()) - (new Date(b.due_date || 0).getTime());
  }).slice(0, 8),
);
function dueLabel(t: any): { text: string; tone: string } {
  if (!t.due_date) return { text: "без срока", tone: "muted" };
  const d = new Date(t.due_date); d.setHours(0, 0, 0, 0);
  const today = new Date(); today.setHours(0, 0, 0, 0);
  const diff = Math.round((d.getTime() - today.getTime()) / 86400000);
  if (diff < 0) return { text: `просрочено ${-diff} дн`, tone: "bad" };
  if (diff === 0) return { text: "сегодня", tone: "warn" };
  if (diff === 1) return { text: "завтра", tone: "warn" };
  return { text: d.toLocaleDateString("ru-RU", { day: "2-digit", month: "short" }), tone: "muted" };
}

// ─── Обновления / Уведомления (из стора) ───
const recent = computed(() => notif.recent.filter((n: any) => !n.is_archived));
const updates = computed(() =>
  recent.value.filter((n: any) =>
    n.type?.startsWith("status.") || n.type?.startsWith("deadline.") ||
    n.type === "assignment" || n.type?.includes("update") || (n.payload as any)?.diff,
  ).slice(0, 8),
);
const notifs = computed(() => recent.value.slice(0, 8));
const desc = (n: any) => describeNotification(n);
const iconPath = (k: string) => NOTIF_ICON_PATHS[k] || NOTIF_ICON_PATHS.bell;

// ─── Сводные чипы ───
const openTasks = computed(() => myTasks.value.length);
const overdueTasks = computed(() => myTasks.value.filter((t: any) => dueRank(t) === 0).length);
const unread = computed(() => notif.unreadCount || 0);

const list = computed(() => (tab.value === "tasks" ? sortedTasks.value : tab.value === "updates" ? updates.value : notifs.value));

function openTask(t: any) {
  const link = `/tasks/${t.id}`;
  if (entityEditor.openFromLink(link)) return;
  router.push(link);
}
function openNotif(n: any) {
  if (n.id) notif.markRead?.(n.id);
  const link = n.link_url;
  if (link && entityEditor.openFromLink(link)) return;
  if (link) router.push(link);
  else router.push("/notifications");
}
</script>

<template>
  <div class="myday">
    <div class="myday-hd">
      <div class="myday-hd-l">
        <span class="myday-title">Мой день</span>
        <div class="myday-chips">
          <span v-if="openTasks" class="myday-chip" :class="{ bad: overdueTasks > 0 }">
            {{ openTasks }} {{ openTasks === 1 ? 'задача' : 'задач' }}<template v-if="overdueTasks"> · {{ overdueTasks }} просроч.</template>
          </span>
          <span v-if="unread" class="myday-chip myday-chip-accent">{{ unread }} новых</span>
        </div>
      </div>
      <div class="myday-tabs">
        <button :class="{ on: tab === 'updates' }" @click="tab = 'updates'">Обновления</button>
        <button :class="{ on: tab === 'tasks' }" @click="tab = 'tasks'">Задачи<span v-if="openTasks" class="myday-tabnum">{{ openTasks }}</span></button>
        <button :class="{ on: tab === 'notifs' }" @click="tab = 'notifs'">Уведомления<span v-if="unread" class="myday-tabnum">{{ unread }}</span></button>
      </div>
    </div>

    <div class="myday-body">
      <Transition name="myday-fade" mode="out-in">
        <div :key="tab" class="myday-list">
          <!-- ЗАДАЧИ -->
          <template v-if="tab === 'tasks'">
            <div v-if="tasksLoading" class="myday-empty">Загрузка задач…</div>
            <div v-else-if="!sortedTasks.length" class="myday-empty myday-empty-good">✓ Назначенных задач нет</div>
            <button v-for="(t, i) in sortedTasks" :key="t.id" class="myday-row" :style="{ '--d': i * 45 + 'ms' }" @click="openTask(t)">
              <span class="myday-dot" :class="'tone-' + dueLabel(t).tone"></span>
              <span class="myday-row-main">
                <span class="myday-row-title">{{ t.title }}</span>
                <span class="myday-row-sub">{{ (t as any).company_code || (t as any).board_title || 'задача' }}</span>
              </span>
              <span class="myday-due" :class="'tone-' + dueLabel(t).tone">{{ dueLabel(t).text }}</span>
            </button>
          </template>

          <!-- ОБНОВЛЕНИЯ / УВЕДОМЛЕНИЯ -->
          <template v-else>
            <div v-if="!list.length" class="myday-empty myday-empty-good">Пока ничего нового</div>
            <button v-for="(n, i) in (list as any[])" :key="n.id" class="myday-row" :class="{ unread: !n.is_read }" :style="{ '--d': i * 45 + 'ms', '--accent': desc(n).accent }" @click="openNotif(n)">
              <span class="myday-nicon" :style="{ color: desc(n).accent, background: desc(n).accent + '16' }">
                <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" v-html="iconPath(desc(n).icon)" />
              </span>
              <span class="myday-row-main">
                <span class="myday-row-title">{{ desc(n).entity || n.title }}</span>
                <span class="myday-row-sub">{{ desc(n).verb }}</span>
              </span>
              <span class="myday-time">{{ formatRelativeTime(n.created_at) }}</span>
            </button>
          </template>
        </div>
      </Transition>
    </div>

    <button class="myday-foot" @click="router.push(tab === 'tasks' ? '/tasks' : '/notifications')">
      {{ tab === 'tasks' ? 'Все мои задачи' : 'Все уведомления' }}
      <svg width="12" height="12" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M5 3l5 5-5 5"/></svg>
    </button>
  </div>
</template>

<style scoped>
.myday {
  background: var(--bg1, #fff); border-radius: 18px;
  border: 1px solid var(--line, rgba(30,42,74,.07));
  box-shadow: 0 4px 18px rgba(15,23,60,.06);
  overflow: hidden; display: flex; flex-direction: column;
}
.myday-hd { padding: 16px 18px 0; }
.myday-hd-l { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }
.myday-title { font-size: 15px; font-weight: 600; color: var(--t1, #1A1730); }
.myday-chips { display: flex; gap: 6px; flex-wrap: wrap; }
.myday-chip { font-size: 10.5px; font-weight: 600; padding: 2px 9px; border-radius: 999px; background: var(--bg2, #F1F0F7); color: var(--t2, #6B6880); }
.myday-chip.bad { background: rgba(226,75,74,.12); color: #C5352F; }
.myday-chip-accent { background: rgba(124,111,247,.12); color: #534AB7; }

.myday-tabs { display: flex; gap: 2px; margin-top: 13px; }
.myday-tabs button {
  position: relative; background: transparent; border: none; padding: 8px 12px 11px;
  font-size: 12px; font-weight: 500; color: var(--t3, #8B889C); cursor: pointer; font-family: inherit;
  border-bottom: 2px solid transparent; display: inline-flex; align-items: center; gap: 5px;
}
.myday-tabs button:hover { color: var(--t1, #1A1730); }
.myday-tabs button.on { color: var(--p-deep, #534AB7); border-bottom-color: #7F77DD; font-weight: 600; }
.myday-tabnum { font-size: 9.5px; font-weight: 700; background: rgba(124,111,247,.16); color: #534AB7; border-radius: 7px; padding: 0 5px; }

.myday-body { border-top: 1px solid var(--line, rgba(30,42,74,.06)); }
.myday-list { padding: 6px; min-height: 180px; }
.myday-row {
  width: 100%; display: flex; align-items: center; gap: 11px;
  padding: 9px 11px; border: none; background: transparent; border-radius: 10px;
  cursor: pointer; font-family: inherit; text-align: left;
  animation: mydayIn .34s var(--ease-standard) both; animation-delay: var(--d, 0ms);
  transition: background .12s;
}
.myday-row:hover { background: rgba(124,111,247,.06); }
.myday-row.unread { box-shadow: inset 2px 0 0 var(--accent, #7C6FF7); }
@keyframes mydayIn { from { opacity: 0; transform: translateY(6px); } to { opacity: 1; transform: none; } }

.myday-dot { width: 8px; height: 8px; border-radius: 50%; flex-shrink: 0; background: #C9C6DA; }
.myday-nicon { width: 28px; height: 28px; border-radius: 8px; display: inline-flex; align-items: center; justify-content: center; flex-shrink: 0; }
.tone-bad { background: #E24B4A; color: #C5352F; }
.tone-warn { background: #EF9F27; color: #A36500; }
.tone-muted { background: #C9C6DA; color: var(--t3, #8B889C); }
.myday-due.tone-bad, .myday-due.tone-warn, .myday-due.tone-muted { background: transparent; }

.myday-row-main { flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 2px; }
.myday-row-title { font-size: 13px; font-weight: 500; color: var(--t1, #1A1730); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.myday-row-sub { font-size: 11px; color: var(--t3, #8B889C); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.myday-due { font-size: 11px; font-weight: 600; flex-shrink: 0; }
.myday-time { font-size: 10.5px; color: var(--t3, #A6A3B8); flex-shrink: 0; }

.myday-empty { padding: 40px 16px; text-align: center; font-size: 12.5px; color: var(--t3, #8B889C); }
.myday-empty-good { color: #0F6E56; }

.myday-foot {
  display: flex; align-items: center; justify-content: center; gap: 5px;
  padding: 11px; border: none; border-top: 1px solid var(--line, rgba(30,42,74,.06));
  background: var(--bg2, #FAFAFC); color: var(--p-deep, #534AB7);
  font-size: 12px; font-weight: 600; cursor: pointer; font-family: inherit;
}
.myday-foot:hover { background: rgba(124,111,247,.06); }

.myday-fade-enter-active, .myday-fade-leave-active { transition: opacity .18s ease, transform .18s ease; }
.myday-fade-enter-from { opacity: 0; transform: translateY(6px); }
.myday-fade-leave-to { opacity: 0; transform: translateY(-6px); }
</style>
