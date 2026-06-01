<script setup lang="ts">
/**
 * Full notifications inbox at /notifications.
 * Search, filters by type/priority/period, bulk actions, archive view.
 */
import { computed, onMounted, ref, watch } from "vue";
import { useRouter } from "vue-router";
import { useNotificationsStore } from "@/stores/notifications";
import {
  notificationsApi,
  iconFor, formatRelativeTime,
  PRIORITY_LABELS,
  type Notification, type Priority,
} from "@/api/notifications";

const router = useRouter();
const store = useNotificationsStore();

const items = ref<Notification[]>([]);
const total = ref(0);
const page = ref(1);
const perPage = 30;
const loading = ref(false);
const error = ref<string | null>(null);

const filterUnread = ref(false);
const filterArchived = ref(false);
const filterPriorities = ref<Priority[]>([]);
const filterTypes = ref<string[]>([]);
const search = ref("");

const selected = ref<Set<string>>(new Set());

async function load() {
  loading.value = true;
  try {
    const r = await notificationsApi.feed({
      unread_only: filterUnread.value,
      include_archived: filterArchived.value,
      priorities: filterPriorities.value.length ? filterPriorities.value : undefined,
      types: filterTypes.value.length ? filterTypes.value : undefined,
      page: page.value, per_page: perPage,
    });
    items.value = r.items;
    total.value = r.total;
  } catch (e: any) {
    error.value = e?.response?.data?.detail || e?.message;
  } finally { loading.value = false; }
}

onMounted(load);
watch([filterUnread, filterArchived, filterPriorities, filterTypes, page], load);

const searchedItems = computed(() => {
  if (!search.value.trim()) return items.value;
  const q = search.value.toLowerCase();
  return items.value.filter((n) =>
    n.title.toLowerCase().includes(q) || (n.body || "").toLowerCase().includes(q)
  );
});

const totalPages = computed(() => Math.max(1, Math.ceil(total.value / perPage)));

function toggleSel(id: string) {
  if (selected.value.has(id)) selected.value.delete(id);
  else selected.value.add(id);
  selected.value = new Set(selected.value);
}
function selectAll() { items.value.forEach((n) => selected.value.add(n.id)); selected.value = new Set(selected.value); }
function clearSel() { selected.value = new Set(); }

async function bulkRead() {
  if (selected.value.size === 0) return;
  await notificationsApi.readBulk(Array.from(selected.value));
  await store.refreshCount();
  await load();
  clearSel();
}

async function bulkArchive() {
  if (selected.value.size === 0) return;
  await notificationsApi.archiveBulk(Array.from(selected.value));
  await store.refreshCount();
  await load();
  clearSel();
}

async function clickItem(n: Notification) {
  if (!n.is_read) await store.markRead(n.id);
  if (n.link_url) router.push(n.link_url);
}

function togglePrio(p: Priority) {
  if (filterPriorities.value.includes(p)) filterPriorities.value = filterPriorities.value.filter((x) => x !== p);
  else filterPriorities.value = [...filterPriorities.value, p];
}

function priorityBg(p: string) { return PRIORITY_LABELS[p as Priority]?.bg || ""; }
function priorityColor(p: string) { return PRIORITY_LABELS[p as Priority]?.color || "#5F5E5A"; }
</script>

<template>
  <div class="ni-wrap">
    <div class="ni-topbar">
      <div class="ni-tb-l">
        <div class="ni-eyebrow">
          <svg width="11" height="11" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="2"><path d="M8 1c2 0 4 2 4 4v3l2 2H2l2-2V5c0-2 2-4 4-4z"/></svg>
          Личный кабинет · уведомления
        </div>
        <div class="ni-title">Все уведомления</div>
        <div class="ni-sub">
          <b>{{ total }}</b> всего · <b style="color:#A32D2D">{{ store.unreadCount }}</b> непрочитанных ·
          <span v-if="store.isConnected" class="ni-live"><span class="ni-live-dot"></span> live</span>
          <span v-else class="ni-live offline"><span class="ni-live-dot"></span> polling</span>
        </div>
      </div>
      <div class="ni-tb-r">
        <button class="ni-btn ni-btn-ghost" @click="router.push('/notifications/settings')">
          <svg width="13" height="13" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="2"><circle cx="8" cy="8" r="2"/><path d="M12.5 9.5l1 1M2.5 9.5l-1 1M9.5 12.5l1 1M9.5 2.5l1-1M6.5 12.5l-1 1M6.5 2.5l-1-1M12.5 6.5l1-1M2.5 6.5l-1-1"/></svg>
          Настройки
        </button>
      </div>
    </div>

    <div class="ni-filterbar">
      <input v-model="search" placeholder="Поиск..." class="ni-search"/>
      <label class="ni-check"><input type="checkbox" v-model="filterUnread"/> только непрочитанные</label>
      <label class="ni-check"><input type="checkbox" v-model="filterArchived"/> показать архив</label>
      <span class="ni-divider"></span>
      <span class="ni-prio-label">приоритет:</span>
      <button v-for="p in (['critical','high','normal','low'] as Priority[])" :key="p"
              class="ni-prio-btn" :class="{ active: filterPriorities.includes(p) }"
              :style="filterPriorities.includes(p) ? { background: priorityBg(p), color: priorityColor(p) } : {}"
              @click="togglePrio(p)">
        {{ PRIORITY_LABELS[p].label }}
      </button>
    </div>

    <div v-if="error" class="ni-err">{{ error }}</div>

    <div v-if="selected.size > 0" class="ni-bulk-bar">
      <span>Выбрано: <b>{{ selected.size }}</b></span>
      <button class="ni-btn ni-btn-ghost" @click="bulkRead">Прочитать выбранные</button>
      <button class="ni-btn ni-btn-ghost" @click="bulkArchive">Архивировать</button>
      <button class="ni-btn ni-btn-ghost" @click="clearSel">Снять выделение</button>
    </div>

    <div class="ni-list">
      <div v-if="!loading && searchedItems.length === 0" class="ni-empty">
        Ничего не найдено
      </div>
      <div v-for="n in searchedItems" :key="n.id"
           class="ni-row"
           :class="{ unread: !n.is_read, archived: n.is_archived, sel: selected.has(n.id) }">
        <input type="checkbox" :checked="selected.has(n.id)" @change="toggleSel(n.id)" class="ni-row-cb"/>
        <span class="ni-icn" :style="{ background: priorityBg(n.priority), color: priorityColor(n.priority) }">
          <i :class="`ti ti-${iconFor(n.type)}`" aria-hidden="true"></i>
        </span>
        <div class="ni-content" @click="clickItem(n)">
          <div class="ni-meta">
            <span class="ni-prio" :style="{ background: priorityBg(n.priority), color: priorityColor(n.priority) }">
              {{ PRIORITY_LABELS[n.priority]?.label }}
            </span>
            <span v-if="(n.payload as any)?.is_external" class="ni-ext">EXTERNAL</span>
            <span class="ni-type">{{ n.type }}</span>
            <span class="ni-time">{{ formatRelativeTime(n.created_at) }}</span>
            <span v-if="n.is_archived" class="ni-archived-tag">в архиве</span>
          </div>
          <div class="ni-title-row">
            <span class="ni-title-text">{{ n.title }}</span>
          </div>
          <div v-if="n.body" class="ni-body">{{ n.body }}</div>
        </div>
        <span v-if="!n.is_read" class="ni-dot" :style="{ background: priorityColor(n.priority) }"></span>
      </div>
    </div>

    <div v-if="totalPages > 1" class="ni-pager">
      <button :disabled="page === 1" @click="page--" class="ni-btn ni-btn-ghost">← Назад</button>
      <span>Стр. {{ page }} из {{ totalPages }}</span>
      <button :disabled="page === totalPages" @click="page++" class="ni-btn ni-btn-ghost">Вперёд →</button>
    </div>
  </div>
</template>

<style scoped>
.ni-wrap { background: #F4F3F9; min-height: 100%; font-family: var(--font, system-ui); }

.ni-topbar {
  background: linear-gradient(95deg, #1E2A4A 0%, #2D3760 60%, #4B477E 100%);
  padding: 14px 22px;
  display: flex; align-items: center; justify-content: space-between;
}
.ni-tb-l { display: flex; flex-direction: column; gap: 3px; }
.ni-eyebrow {
  font-size: 10px; color: rgba(255,255,255,.55);
  letter-spacing: .08em; text-transform: uppercase; font-weight: 500;
  display: flex; align-items: center; gap: 6px;
}
.ni-title { font-size: 17px; color: #fff; font-weight: 500; }
.ni-sub {
  font-size: 11px; color: rgba(255,255,255,.65);
  display: flex; gap: 8px; align-items: center;
}
.ni-sub b { color: #fff; font-weight: 500; }
.ni-live {
  display: inline-flex; align-items: center; gap: 5px;
  background: rgba(29,158,117,.15); color: #5DCAA5;
  padding: 1px 7px; border-radius: 9px;
  font-size: 9px; font-weight: 500; letter-spacing: .04em;
  text-transform: uppercase;
}
.ni-live-dot { width: 5px; height: 5px; border-radius: 50%; background: currentColor; }
.ni-live.offline { background: rgba(239,159,39,.15); color: #FAC775; }

.ni-btn {
  background: rgba(255,255,255,.1);
  border: 0; color: #fff;
  padding: 6px 12px; border-radius: 6px;
  font-size: 11.5px; font-family: inherit;
  cursor: pointer;
  display: inline-flex; align-items: center; gap: 5px;
}
.ni-btn-ghost { background: transparent; color: var(--t3, #5F5E5A); border: 0.5px solid rgba(0,0,0,.12); }

.ni-filterbar {
  background: var(--bg2, #FAFAFC);
  padding: 10px 22px;
  border-bottom: 0.5px solid rgba(0,0,0,.06);
  display: flex; gap: 8px; align-items: center; flex-wrap: wrap;
}
.ni-search {
  flex: 1; min-width: 220px;
  padding: 6px 12px;
  border: 0.5px solid rgba(0,0,0,.1);
  border-radius: 6px;
  font-size: 12px; outline: none;
  font-family: inherit;
}
.ni-search:focus { border-color: #7F77DD; }
.ni-check { font-size: 11.5px; color: var(--t3, #5F5E5A); display: inline-flex; align-items: center; gap: 4px; cursor: pointer; }
.ni-divider { width: 1px; height: 18px; background: rgba(0,0,0,.08); }
.ni-prio-label { font-size: 11px; color: var(--t3, var(--t-muted)); }
.ni-prio-btn {
  background: transparent; border: 0.5px solid rgba(0,0,0,.12);
  color: var(--t3, #5F5E5A);
  padding: 4px 9px; border-radius: 5px;
  font-size: 11px; cursor: pointer; font-family: inherit;
}

.ni-err {
  background: rgba(226,75,74,.08); color: var(--sev-critical);
  padding: 10px 22px; font-size: 12px;
}

.ni-bulk-bar {
  background: rgba(127,119,221,.08);
  padding: 8px 22px;
  display: flex; gap: 10px; align-items: center;
  font-size: 12px; color: var(--p-deep);
}

.ni-list { padding: 4px 22px 12px; }
.ni-empty { padding: 60px; text-align: center; color: var(--t3, var(--t-muted)); font-size: 13px; }

.ni-row {
  display: flex; gap: 10px; align-items: flex-start;
  background: var(--bg1, #fff);
  border: 0.5px solid rgba(0,0,0,.05);
  border-radius: 8px;
  padding: 10px 12px;
  margin-bottom: 5px;
  position: relative;
  transition: background .15s;
}
.ni-row { position: relative; overflow: hidden; }
.ni-row:hover { background: rgba(127,119,221,.03); }
.ni-row.unread::before {
  content: ""; position: absolute; top: 0; left: 0; right: 0;
  height: 2px; background: #7F77DD;
  animation: uzaStripeDrawIn .4s var(--ease-standard) both;
  transform-origin: left center;
  pointer-events: none;
}
.ni-row.archived { opacity: .55; }
.ni-row.sel { background: rgba(127,119,221,.06); }
.ni-row-cb { margin-top: 6px; cursor: pointer; }

.ni-icn {
  width: 30px; height: 30px;
  border-radius: 7px;
  display: inline-flex;
  align-items: center; justify-content: center;
  flex-shrink: 0;
}
.ni-icn i { font-size: 15px; }

.ni-content { flex: 1; min-width: 0; cursor: pointer; }
.ni-meta { display: flex; gap: 6px; align-items: center; margin-bottom: 2px; flex-wrap: wrap; }
.ni-prio {
  font-size: 9.5px;
  padding: 1px 6px; border-radius: 3px;
  font-weight: 600; letter-spacing: .04em;
  text-transform: uppercase;
}
.ni-ext {
  background: #D4537E; color: #fff;
  padding: 1px 6px; border-radius: 3px;
  font-size: 9.5px; font-weight: 600; letter-spacing: .04em;
}
.ni-type {
  font-size: 9.5px; color: var(--t3, var(--t-muted));
  font-family: monospace;
}
.ni-time { font-size: 10px; color: var(--t3, var(--t-muted)); }
.ni-archived-tag {
  font-size: 9px; color: var(--t3, var(--t-muted));
  background: rgba(0,0,0,.06);
  padding: 1px 6px; border-radius: 3px;
}

.ni-title-row { display: flex; align-items: center; gap: 6px; }
.ni-title-text { font-size: 13px; color: var(--t1, #1E2A4A); }
.ni-body {
  font-size: 11.5px; color: var(--t3, #5F5E5A);
  line-height: 1.45; margin-top: 3px;
}

.ni-dot {
  position: absolute;
  top: 14px; right: 12px;
  width: 7px; height: 7px;
  border-radius: 50%;
}

.ni-pager {
  display: flex; justify-content: center; align-items: center; gap: 10px;
  padding: 14px;
  font-size: 12px; color: var(--t3, #5F5E5A);
}
.ni-pager button:disabled { opacity: .4; cursor: not-allowed; }
</style>
