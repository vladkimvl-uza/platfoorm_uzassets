<script setup lang="ts">
/**
 * Bell with badge + dropdown panel.
 * Mounts in AppShell topbar area (or sidebar header).
 */
import { computed, onMounted, onUnmounted, ref } from "vue";
import { useRouter } from "vue-router";
import { useNotificationsStore } from "@/stores/notifications";
import { useEntityEditor } from "@/composables/useEntityEditor";
import { iconFor, formatRelativeTime, PRIORITY_LABELS } from "@/api/notifications";
import ActorAvatar from "@/components/ActorAvatar.vue";
import UserCardAnchor from "@/components/user/UserCardAnchor.vue";
import ActorLine from "@/components/user/ActorLine.vue";
import { describeNotification, NOTIF_ICON_PATHS } from "@/composables/useNotificationMeta";
import { useNotificationDetail } from "@/composables/useNotificationDetail";
import { useI18n } from "@/composables/useI18n";
const { t } = useI18n();


const router = useRouter();
const store = useNotificationsStore();
const entityEditor = useEntityEditor();

// Дескриптор «что сделал юзер» (действие/акцент/иконка/деталь).
const desc = (n: any) => describeNotification(n);
const iconPath = (k: string) => NOTIF_ICON_PATHS[k] || NOTIF_ICON_PATHS.bell;

const isOpen = ref(false);
const bellEl = ref<HTMLElement | null>(null);
const dropdownEl = ref<HTMLElement | null>(null);

type FilterTab = "all" | "moderation" | "mentions" | "deadlines";
const activeFilter = ref<FilterTab>("all");

const filteredItems = computed(() => {
  const items = store.recent.filter((n) => !n.is_archived);
  if (activeFilter.value === "moderation") return items.filter((n) => n.type.startsWith("moderation."));
  if (activeFilter.value === "mentions")    return items.filter((n) => n.type === "mention" || n.type === "assignment");
  if (activeFilter.value === "deadlines")   return items.filter((n) => n.type.startsWith("deadline."));
  return items;
});

const filterCounts = computed(() => ({
  moderation: store.recent.filter((n) => n.type.startsWith("moderation.") && !n.is_read).length,
  mentions:    store.recent.filter((n) => (n.type === "mention" || n.type === "assignment") && !n.is_read).length,
  deadlines:   store.recent.filter((n) => n.type.startsWith("deadline.") && !n.is_read).length,
}));

function toggle() {
  isOpen.value = !isOpen.value;
  if (isOpen.value) {
    store.refreshRecent();
    // Pack 12.2 fix: compute fixed-position coords relative to bell, since sidebar
    // has overflow:hidden which would clip an absolutely-positioned dropdown.
    updateDropdownPos();
  }
}

const dropdownPos = ref<{ left: number; top: number | null; bottom: number | null }>({ left: 0, top: null, bottom: null });

function updateDropdownPos() {
  if (!bellEl.value) return;
  const r = bellEl.value.getBoundingClientRect();
  const dropdownWidth = 420;
  const dropdownHeight = 540; // approx
  const margin = 8;

  // Anchor dropdown to the RIGHT edge of the bell — open to the right of sidebar.
  // Bell is in top-right of sidebar, so dropdown sits below+to-the-right.
  let left = r.left - 12; // slight left shift so arrow lines up with bell
  if (left + dropdownWidth > window.innerWidth - margin) {
    left = window.innerWidth - dropdownWidth - margin;
  }
  if (left < margin) left = margin;

  // Open UP or DOWN based on available room — bell is now in sidebar HEADER (top),
  // so by default open DOWN. If insufficient room downward, fall back to UP.
  const spaceBelow = window.innerHeight - r.bottom;
  if (spaceBelow >= dropdownHeight + 16 || spaceBelow >= window.innerHeight / 2) {
    dropdownPos.value = { left, top: r.bottom + 8, bottom: null };
  } else {
    dropdownPos.value = { left, top: null, bottom: window.innerHeight - r.top + 8 };
  }
}

function close() { isOpen.value = false; }

/** Ссылка для открытия: link_url, иначе выводим из source_entity_id (путь). */
function deriveLink(n: any): string | null {
  if (n.link_url) return n.link_url;
  const src: string = (n.source_entity_id || "") + " " + ((n.payload as any)?.entity_id || "");
  const m = src.match(/\/(tasks|projects)\/([0-9a-fA-F-]{36})/);
  if (m) return `/${m[1]}/${m[2]}`;
  // payload.entity_type + entity_id (watch.*)
  const et = (n.payload as any)?.entity_type, eid = (n.payload as any)?.entity_id;
  if ((et === "task" || et === "project") && eid) return `/${et}s/${eid}`;
  return null;
}

const notifDetail = useNotificationDetail();

async function handleItemClick(n: any) {
  await store.markRead(n.id);
  close();
  // Задачи/проекты открываем глобальной модалкой поверх текущей страницы —
  // без навигации на /tasks. openFromLink вернёт true, если ссылка обработана.
  const link = deriveLink(n);
  if (link && entityEditor.openFromLink(link)) return;
  if (link) { router.push(link); return; }
  // Нет сущности для перехода → показываем карточку деталей уведомления.
  notifDetail.open(n);
}

async function quickAction(id: string, action: "approve" | "reject" | "open") {
  if (action === "open") {
    const item = store.recent.find((n) => n.id === id);
    if (item?.link_url && !entityEditor.openFromLink(item.link_url)) {
      router.push(item.link_url);
    }
    close();
    return;
  }
  // Approve/Reject are wired in Pack 11.1 via moderation API.
  await store.markRead(id);
}

function onDocClick(e: MouseEvent) {
  if (!isOpen.value) return;
  const target = e.target as Node;
  if (bellEl.value?.contains(target) || dropdownEl.value?.contains(target)) return;
  close();
}
function onKey(e: KeyboardEvent) { if (e.key === "Escape") close(); }

onMounted(() => {
  document.addEventListener("click", onDocClick);
  document.addEventListener("keydown", onKey);
  window.addEventListener("resize", updateDropdownPos);
  window.addEventListener("scroll", updateDropdownPos, true);
});
onUnmounted(() => {
  document.removeEventListener("click", onDocClick);
  document.removeEventListener("keydown", onKey);
  window.removeEventListener("resize", updateDropdownPos);
  window.removeEventListener("scroll", updateDropdownPos, true);
});

function priorityBgFor(p: string): string { return PRIORITY_LABELS[p as "critical" | "high" | "normal" | "low"]?.bg || ""; }
function priorityColorFor(p: string): string { return PRIORITY_LABELS[p as "critical" | "high" | "normal" | "low"]?.color || "#5F5E5A"; }
</script>

<template>
  <div class="nb-wrap">
    <button ref="bellEl" class="nb-bell" :class="{ active: isOpen, 'has-critical': store.criticalCount > 0 }" @click="toggle" :title="`${store.unreadCount} непрочитанных`">
      <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
        <path d="M18 8a6 6 0 0 0-12 0c0 7-3 9-3 9h18s-3-2-3-9"/>
        <path d="M13.73 21a2 2 0 0 1-3.46 0"/>
      </svg>
      <span v-if="store.unreadCount > 0" class="nb-badge" :class="{ critical: store.criticalCount > 0 }">
        {{ store.unreadCount > 99 ? "99+" : store.unreadCount }}
      </span>
      <span v-if="!store.isConnected" class="nb-offline" :title="t('Подключение к live...')"></span>
    </button>

    <Teleport to="body">
      <Transition name="uza-fade">
        <div v-if="isOpen" ref="dropdownEl" class="nb-dropdown nb-dropdown-fixed"
             :class="{ 'nb-open-up': dropdownPos.bottom !== null }"
             :style="{
               left: dropdownPos.left + 'px',
               top: dropdownPos.top !== null ? dropdownPos.top + 'px' : 'auto',
               bottom: dropdownPos.bottom !== null ? dropdownPos.bottom + 'px' : 'auto',
             }">
          <div class="nb-arrow" :class="dropdownPos.bottom !== null ? 'nb-arrow-bottom' : 'nb-arrow-top'"></div>

        <div class="nb-hd">
          <div class="nb-hd-l">
            <span class="nb-hd-title">{{ t('Уведомления') }}</span>
            <span v-if="store.unreadCount > 0" class="nb-hd-badge">{{ store.unreadCount }} {{ t('новых') }}</span>
          </div>
          <div class="nb-hd-r">
            <button v-if="store.unreadCount > 0" class="nb-act-link" @click="store.markAllRead()">{{ t('Прочитать всё') }}</button>
            <button class="nb-act-icon" @click="router.push('/notifications/settings'); close()" :title="t('Настройки')">
              <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z"/></svg>
            </button>
          </div>
        </div>

        <div class="nb-tabs">
          <button :class="{ active: activeFilter === 'all' }" @click="activeFilter = 'all'">{{ t('Все ·') }} {{ store.unreadCount }}</button>
          <button :class="{ active: activeFilter === 'moderation' }" @click="activeFilter = 'moderation'">
            {{ t('Модерация') }}
            <span v-if="filterCounts.moderation > 0" class="nb-tab-cnt" :style="{ background: '#A32D2D' }">{{ filterCounts.moderation }}</span>
          </button>
          <button :class="{ active: activeFilter === 'mentions' }" @click="activeFilter = 'mentions'">
            {{ t('Упоминания') }}
            <span v-if="filterCounts.mentions > 0" class="nb-tab-cnt">{{ filterCounts.mentions }}</span>
          </button>
          <button :class="{ active: activeFilter === 'deadlines' }" @click="activeFilter = 'deadlines'">
            {{ t('Дедлайны') }}
            <span v-if="filterCounts.deadlines > 0" class="nb-tab-cnt">{{ filterCounts.deadlines }}</span>
          </button>
        </div>

        <div class="nb-list">
          <div v-if="filteredItems.length === 0" class="nb-empty">
            <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="#888780" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
              <path d="M18 8a6 6 0 0 0-12 0c0 7-3 9-3 9h18s-3-2-3-9"/>
              <path d="M13.73 21a2 2 0 0 1-3.46 0"/>
            </svg>
            <div>{{ t('Все уведомления прочитаны') }}</div>
          </div>
          <div v-for="(n, idx) in filteredItems" :key="n.id" class="nb-item"
               :class="[
                 { unread: !n.is_read },
                 `prio-${n.priority}`,
               ]"
               :style="{ animationDelay: `${idx * 40}ms`, '--accent': desc(n).accent }"
               @click="handleItemClick(n)">
            <UserCardAnchor v-if="n.source_user_id" :user-id="n.source_user_id" @click.stop>
              <ActorAvatar :user-id="n.source_user_id" :size="34" />
            </UserCardAnchor>
            <span v-else class="nb-icn" :style="{ background: priorityBgFor(n.priority), color: priorityColorFor(n.priority) }">
              <i :class="`ti ti-${iconFor(n.type)}`" aria-hidden="true"></i>
            </span>
            <div class="nb-content">
              <!-- КТО: имя + бейджи принадлежности (компания/сектор), карточка по ховеру -->
              <div v-if="n.source_user_id" class="nb-actor" @click.stop>
                <ActorLine :user-id="n.source_user_id" show-badges />
              </div>
              <!-- ЧТО СДЕЛАЛ: цветной action-чип + время -->
              <div class="nb-meta">
                <span class="nb-act" :style="{ color: desc(n).accent, background: desc(n).accent + '14' }">
                  <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" v-html="iconPath(desc(n).icon)" />
                  {{ desc(n).verb }}
                </span>
                <span v-if="n.priority === 'high' || n.priority === 'critical'" class="nb-prio" :style="{ background: priorityBgFor(n.priority), color: priorityColorFor(n.priority) }">
                  {{ PRIORITY_LABELS[n.priority]?.label || n.priority }}
                </span>
                <span v-if="n.payload && (n.payload as any).is_external" class="nb-ext">EXTERNAL</span>
                <span class="nb-time">{{ formatRelativeTime(n.created_at) }}</span>
              </div>

              <!-- Сущность (задача/проект) -->
              <div v-if="desc(n).entity" class="nb-entity">{{ desc(n).entity }}</div>
              <div v-else class="nb-title">{{ n.title }}</div>

              <!-- ДЕТАЛЬ: статус old→new / срок / ход -->
              <div v-if="desc(n).detail" class="nb-detail">
                <template v-if="(desc(n).detail as any).kind === 'status'">
                  <span class="nb-pill nb-pill-old">{{ (desc(n).detail as any).from }}</span>
                  <svg class="nb-arrow" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"><path d="M5 12h14M13 6l6 6-6 6"/></svg>
                  <span class="nb-pill nb-pill-new" :style="{ color: desc(n).accent, background: desc(n).accent + '16' }">{{ (desc(n).detail as any).to }}</span>
                </template>
                <template v-else-if="(desc(n).detail as any).kind === 'deadline'">
                  <span class="nb-pill nb-pill-old">{{ (desc(n).detail as any).from }}</span>
                  <svg class="nb-arrow" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"><path d="M5 12h14M13 6l6 6-6 6"/></svg>
                  <span class="nb-pill nb-pill-new" :style="{ color: desc(n).accent, background: desc(n).accent + '16' }">{{ (desc(n).detail as any).to }}</span>
                </template>
                <span v-else class="nb-excerpt">{{ (desc(n).detail as any).text }}</span>
              </div>

              <div v-if="n.type.startsWith('moderation.pending')" class="nb-quick">
                <button class="nb-q-approve" @click.stop="quickAction(n.id, 'approve')">
                  <svg width="10" height="10" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round"><path d="M3 8l4 4 6-8"/></svg>
                  {{ t('Принять') }}
                </button>
                <button class="nb-q-reject" @click.stop="quickAction(n.id, 'reject')">
                  <svg width="10" height="10" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round"><path d="M3 3l10 10M13 3L3 13"/></svg>
                  {{ t('Отклонить') }}
                </button>
                <button class="nb-q-open" @click.stop="quickAction(n.id, 'open')">{{ t('Открыть') }}</button>
              </div>
            </div>
            <span v-if="!n.is_read" class="nb-dot" :style="{ background: priorityColorFor(n.priority) }"></span>
          </div>
        </div>

        <div class="nb-foot">
          <button class="nb-foot-l" @click="router.push('/notifications'); close()">
            {{ t('Все уведомления') }}
            <svg width="11" height="11" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="2"><path d="M5 3l5 5-5 5"/></svg>
          </button>
          <div class="nb-foot-r">
            <span v-if="store.isConnected" class="nb-conn"><span class="nb-conn-dot"></span> live</span>
            <span v-else class="nb-conn offline"><span class="nb-conn-dot"></span> polling</span>
          </div>
        </div>
      </div>
    </Transition>
    </Teleport>
  </div>
</template>

<style scoped>
.nb-wrap { position: relative; display: inline-block; }

.nb-bell {
  position: relative;
  background: rgba(255,255,255,.08);
  border: 0;
  color: rgba(255,255,255,.85);
  width: 30px; height: 30px;
  border-radius: 7px;
  cursor: pointer;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  transition: background .15s, color .15s, transform .15s;
}
.nb-bell:hover    { background: rgba(255,255,255,.15); color: #fff; }
.nb-bell.active   { background: rgba(255,255,255,.18); color: #fff; }
.nb-bell.has-critical { animation: bellShake 1.8s ease-in-out infinite; }
@keyframes bellShake {
  0%, 90%, 100% { transform: rotate(0); }
  92% { transform: rotate(-8deg); }
  94% { transform: rotate(8deg); }
  96% { transform: rotate(-4deg); }
  98% { transform: rotate(4deg); }
}

.nb-badge {
  position: absolute;
  top: -5px; right: -5px;
  background: var(--sev-high); color: #fff;
  min-width: 17px; height: 17px;
  border-radius: 9px;
  padding: 0 4px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  font-size: 10px; font-weight: 600;
  border: 2px solid #1E2A4A;
  font-feature-settings: "tnum";
}
.nb-badge.critical {
  box-shadow: 0 0 0 0 rgba(226,75,74,.4);
  animation: pulseBadge 1.4s infinite;
}
@keyframes pulseBadge {
  0%   { box-shadow: 0 0 0 0    rgba(226,75,74,.45); }
  70%  { box-shadow: 0 0 0 8px  rgba(226,75,74,0);   }
  100% { box-shadow: 0 0 0 0    rgba(226,75,74,0);   }
}

.nb-offline {
  position: absolute;
  bottom: -2px; right: -2px;
  width: 7px; height: 7px;
  border-radius: 50%;
  background: var(--amber);
  border: 2px solid #1E2A4A;
}

/* ─── Dropdown ─── */
.nb-dropdown {
  position: absolute;
  top: calc(100% + 14px);
  right: -6px;
  width: 420px;
  background: var(--bg1, #fff);
  border: 0.5px solid rgba(0,0,0,.06);
  border-radius: 12px;
  box-shadow: 0 12px 40px rgba(15,23,60,.18), 0 4px 12px rgba(15,23,60,.08);
  z-index: 1100;
  overflow: hidden;
  font-family: var(--font, system-ui);
}
/* Pack 12.2 fix: when bell is inside a clipping container (sidebar with overflow:hidden),
   teleport dropdown to body and use fixed positioning anchored to bell rect. */
.nb-dropdown-fixed {
  position: fixed;
  top: auto;
  right: auto;
  /* left + bottom set inline from computed dropdownPos */
  z-index: 5000;
}

.nb-arrow {
  position: absolute;
  width: 14px; height: 8px;
  background: var(--bg1, #fff);
}
/* Arrow pointing UP (dropdown opens DOWN from bell, arrow on top edge) */
.nb-arrow-top {
  top: -8px;
  left: 20px;
  clip-path: polygon(50% 0, 100% 100%, 0 100%);
}
.nb-arrow-bottom {
  bottom: -8px;
  right: 16px;
  /* Flip arrow to point downward (toward bell below) */
  clip-path: polygon(0 0, 100% 0, 50% 100%);
}

.nb-fade-enter-active, .nb-fade-leave-active {
  transition: opacity .18s ease, transform .22s var(--ease-standard);
}
.nb-fade-enter-from { opacity: 0; transform: translateY(-6px) scale(.98); }
.nb-fade-leave-to   { opacity: 0; transform: translateY(-4px); }

.nb-hd {
  padding: 12px 14px;
  border-bottom: 0.5px solid rgba(0,0,0,.05);
  display: flex; align-items: center; justify-content: space-between;
}
.nb-hd-l { display: flex; align-items: center; gap: 8px; }
.nb-hd-title { font-size: 13px; color: var(--t1, #1E2A4A); font-weight: 500; }
.nb-hd-badge {
  background: rgba(226,75,74,.1); color: var(--sev-critical);
  padding: 1px 7px; border-radius: 9px;
  font-size: 10px; font-weight: 600;
}
.nb-hd-r { display: flex; gap: 4px; }
.nb-act-link {
  background: transparent; border: 0;
  color: var(--t3, var(--t-muted)); padding: 4px 8px;
  font-size: 11px; cursor: pointer;
  border-radius: 5px; font-family: inherit;
}
.nb-act-link:hover { color: var(--p-deep); background: rgba(127,119,221,.06); }
.nb-act-icon {
  background: transparent; border: 0;
  color: var(--t3, var(--t-muted)); padding: 4px;
  cursor: pointer; border-radius: 5px;
  display: inline-flex; align-items: center; justify-content: center;
}
.nb-act-icon:hover { background: rgba(0,0,0,.04); color: var(--t1, #1E2A4A); }

.nb-tabs {
  display: flex; gap: 0;
  padding: 0 14px;
  border-bottom: 0.5px solid rgba(0,0,0,.05);
  font-size: 11px;
}
.nb-tabs button {
  background: transparent; border: 0;
  padding: 8px 12px 9px;
  border-bottom: 2px solid transparent;
  color: var(--t3, var(--t-muted)); cursor: pointer;
  font-family: inherit;
  display: inline-flex; align-items: center; gap: 4px;
}
.nb-tabs button:hover { color: var(--t1, #1E2A4A); }
.nb-tabs button.active { color: var(--t1, #1E2A4A); border-bottom-color: #7F77DD; font-weight: 500; }
.nb-tab-cnt {
  background: rgba(226,75,74,.15); color: var(--sev-critical);
  padding: 1px 5px; border-radius: 5px;
  font-size: 9.5px; font-weight: 600;
}

.nb-list {
  max-height: 480px;
  overflow-y: auto;
}
.nb-empty {
  padding: 36px 20px;
  text-align: center;
  color: var(--t3, var(--t-muted));
  font-size: 12px;
  display: flex; flex-direction: column; align-items: center; gap: 8px;
}

.nb-item {
  padding: 11px 14px;
  border-bottom: 0.5px solid rgba(0,0,0,.04);
  display: flex; gap: 10px;
  position: relative;
  transition: background .12s;
  animation: nbItemIn .28s var(--ease-standard) both;
  cursor: pointer;
}
@keyframes nbItemIn {
  from { opacity: 0; transform: translateY(-4px); }
  to   { opacity: 1; transform: translateY(0);    }
}
.nb-item:hover { background: rgba(127,119,221,.03); }
.nb-item.unread { background: rgba(127,119,221,.02); }
.nb-item.prio-critical { background: rgba(226,75,74,.03); position: relative; overflow: hidden; }
.nb-item.prio-critical::before {
  content: ""; position: absolute; top: 0; left: 0; right: 0;
  height: 2px; background: var(--sev-high);
  animation: uzaStripeDrawIn .5s var(--ease-standard) both;
  transform-origin: left center;
  pointer-events: none;
}
.nb-item.prio-high { background: rgba(239,159,39,.03); }

.nb-icn {
  width: 28px; height: 28px;
  border-radius: 6px;
  display: inline-flex;
  align-items: center; justify-content: center;
  flex-shrink: 0;
  font-size: 14px;
}
.nb-icn i { font-size: 14px; }

.nb-content { flex: 1; min-width: 0; cursor: pointer; }
.nb-actor { margin-bottom: 4px; }
.nb-meta { display: flex; gap: 6px; align-items: center; margin-bottom: 2px; }
.nb-prio {
  font-size: 9px;
  padding: 1px 5px; border-radius: 3px;
  font-weight: 600; letter-spacing: .04em;
  text-transform: uppercase;
}
.nb-ext {
  background: #D4537E; color: #fff;
  padding: 1px 5px; border-radius: 3px;
  font-size: 9px; font-weight: 600; letter-spacing: .04em;
}
.nb-time { font-size: 9.5px; color: var(--t3, var(--t-muted)); }

.nb-title {
  font-size: 12px; color: var(--t1, #1E2A4A);
  line-height: 1.4;
}
.nb-body {
  font-size: 11px; color: var(--t3, #5F5E5A);
  line-height: 1.4;
  margin-top: 2px;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

/* ── Премиум-карточка: действие «что сделал» ── */
.nb-item.unread { box-shadow: inset 2px 0 0 var(--accent, #7C6FF7); }
.nb-act {
  display: inline-flex; align-items: center; gap: 4px;
  font-size: 10px; font-weight: 600; letter-spacing: .01em;
  padding: 2px 8px 2px 6px; border-radius: 999px;
  white-space: nowrap; flex-shrink: 0;
}
.nb-act svg { flex-shrink: 0; }
.nb-entity {
  font-size: 12px; font-weight: 500; color: var(--t1, #1E2A4A);
  line-height: 1.35; margin-top: 1px;
  display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden;
}
.nb-detail {
  display: flex; align-items: center; gap: 5px; flex-wrap: wrap;
  margin-top: 5px;
}
.nb-pill {
  font-size: 10px; font-weight: 600; line-height: 1;
  padding: 3px 8px; border-radius: 6px;
  font-variant-numeric: tabular-nums; white-space: nowrap;
}
.nb-pill-old { color: var(--t3, #888780); background: #F1F2F6; }
.nb-arrow { color: var(--t4, #B4B2A9); flex-shrink: 0; }
.nb-excerpt {
  font-size: 11px; color: var(--t2, #5F5E5A); line-height: 1.4;
  display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden;
  border-left: 2px solid var(--accent, #E5E7EB); padding-left: 8px; opacity: .92;
}

.nb-quick { display: flex; gap: 6px; margin-top: 6px; }
.nb-q-approve, .nb-q-reject, .nb-q-open {
  border: 0;
  padding: 3px 9px;
  border-radius: 5px;
  font-size: 10.5px; font-weight: 500;
  cursor: pointer;
  display: inline-flex; align-items: center; gap: 3px;
  font-family: inherit;
  transition: all .12s;
}
.nb-q-approve { background: var(--green); color: #fff; }
.nb-q-approve:hover { background: #0F6E56; }
.nb-q-reject { background: rgba(226,75,74,.12); color: var(--sev-critical); }
.nb-q-reject:hover { background: rgba(226,75,74,.2); }
.nb-q-open { background: transparent; border: 0.5px solid rgba(0,0,0,.12); color: var(--t3, #5F5E5A); }
.nb-q-open:hover { background: rgba(0,0,0,.04); }

.nb-dot {
  position: absolute;
  top: 14px; right: 14px;
  width: 6px; height: 6px;
  border-radius: 50%;
}

.nb-foot {
  padding: 9px 14px;
  border-top: 0.5px solid rgba(0,0,0,.05);
  background: var(--bg2, #FAFAFC);
  display: flex; justify-content: space-between; align-items: center;
}
.nb-foot-l {
  background: transparent; border: 0;
  color: var(--p-deep);
  font-size: 11px; font-weight: 500;
  cursor: pointer;
  font-family: inherit;
  display: inline-flex; align-items: center; gap: 4px;
}
.nb-foot-l:hover { color: #3C3489; }

.nb-conn {
  display: inline-flex; align-items: center; gap: 4px;
  font-size: 10px; color: var(--t3, var(--t-muted));
  text-transform: uppercase;
  letter-spacing: .05em;
}
.nb-conn-dot {
  width: 6px; height: 6px; border-radius: 50%;
  background: var(--green);
}
.nb-conn.offline .nb-conn-dot { background: var(--amber); }
</style>
