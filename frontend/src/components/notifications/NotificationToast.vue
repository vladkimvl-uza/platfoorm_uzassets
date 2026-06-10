<script setup lang="ts">
/**
 * Toast container — listens for new notifications and shows them
 * as transient cards top-right with auto-dismiss + manual close.
 *
 * Mounts once at app root (in AppShell). Subscribes to the store's
 * toast callback registry so it picks up only freshly-arrived items.
 */
import { onMounted, onUnmounted, ref } from "vue";
import { useRouter } from "vue-router";
import { useNotificationsStore } from "@/stores/notifications";
import { useEntityEditor } from "@/composables/useEntityEditor";
import ActorAvatar from "@/components/ActorAvatar.vue";
import { iconFor, formatRelativeTime, PRIORITY_LABELS, type Notification } from "@/api/notifications";
import { describeNotification, NOTIF_ICON_PATHS } from "@/composables/useNotificationMeta";

const router = useRouter();
const store = useNotificationsStore();
const entityEditor = useEntityEditor();

const desc = (n: any) => describeNotification(n);
const iconPath = (k: string) => NOTIF_ICON_PATHS[k] || NOTIF_ICON_PATHS.bell;

interface Toast {
  id: string;
  notification: Notification;
  arrivedAt: number;
  ttlMs: number;
  paused: boolean;
}

const toasts = ref<Toast[]>([]);
const MAX_TOASTS = 4;

function ttlFor(priority: string): number {
  if (priority === "critical") return 12000;
  if (priority === "high")     return 8000;
  if (priority === "normal")   return 5000;
  return 4000;
}

function pushToast(n: Notification) {
  // De-duplicate
  if (toasts.value.find((t) => t.id === n.id)) return;

  const toast: Toast = {
    id: n.id,
    notification: n,
    arrivedAt: Date.now(),
    ttlMs: ttlFor(n.priority),
    paused: false,
  };
  toasts.value.unshift(toast);
  if (toasts.value.length > MAX_TOASTS) toasts.value.pop();

  // Auto-dismiss
  setTimeout(() => dismiss(toast.id), toast.ttlMs);
}

function dismiss(id: string) {
  toasts.value = toasts.value.filter((t) => t.id !== id);
}

function deriveLink(n: any): string | null {
  if (n.link_url) return n.link_url;
  const src: string = (n.source_entity_id || "") + " " + ((n.payload as any)?.entity_id || "");
  const m = src.match(/\/(tasks|projects)\/([0-9a-fA-F-]{36})/);
  if (m) return `/${m[1]}/${m[2]}`;
  const et = (n.payload as any)?.entity_type, eid = (n.payload as any)?.entity_id;
  if ((et === "task" || et === "project") && eid) return `/${et}s/${eid}`;
  return null;
}

function openNotification(t: Toast) {
  store.markRead(t.notification.id);
  const link = deriveLink(t.notification);
  // Задачи/проекты — глобальной модалкой поверх страницы, без навигации.
  if (link && !entityEditor.openFromLink(link)) {
    router.push(link);
  }
  dismiss(t.id);
}

function progressStyle(t: Toast): string {
  const elapsed = Date.now() - t.arrivedAt;
  const pct = Math.max(0, 100 - (elapsed / t.ttlMs) * 100);
  return `width: ${pct}%`;
}

function priorityBg(p: string) { return PRIORITY_LABELS[p as "critical" | "high" | "normal" | "low"]?.bg || ""; }
function priorityColor(p: string) { return PRIORITY_LABELS[p as "critical" | "high" | "normal" | "low"]?.color || "#5F5E5A"; }

let unregister: (() => void) | null = null;

onMounted(() => {
  store.registerToastCallback(pushToast);
  unregister = () => store.registerToastCallback(() => {});
});

onUnmounted(() => {
  if (unregister) unregister();
});
</script>

<template>
  <Teleport to="body">
    <div class="nt-stack" role="region" aria-label="Уведомления">
      <TransitionGroup name="uza-toast" tag="div">
        <div v-for="t in toasts" :key="t.id"
             class="nt-toast"
             :class="`prio-${t.notification.priority}`"
             :style="{ '--nt-accent': desc(t.notification).accent }"
             @click="openNotification(t)">
          <ActorAvatar :user-id="t.notification.source_user_id" :size="36">
            <span class="nt-icn"
                  :style="{ background: desc(t.notification).accent + '16', color: desc(t.notification).accent }">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" v-html="iconPath(desc(t.notification).icon)" />
            </span>
          </ActorAvatar>
          <div class="nt-content">
            <div class="nt-meta">
              <span class="nt-act" :style="{ color: desc(t.notification).accent, background: desc(t.notification).accent + '14' }">{{ desc(t.notification).verb }}</span>
              <span v-if="t.notification.priority === 'high' || t.notification.priority === 'critical'" class="nt-prio" :style="{ background: priorityBg(t.notification.priority), color: priorityColor(t.notification.priority) }">
                {{ PRIORITY_LABELS[t.notification.priority]?.label || t.notification.priority }}
              </span>
              <span v-if="(t.notification.payload as any)?.is_external" class="nt-ext">EXTERNAL</span>
              <span class="nt-time">{{ formatRelativeTime(t.notification.created_at) }}</span>
            </div>
            <div class="nt-title">{{ desc(t.notification).entity || t.notification.title }}</div>
            <div v-if="desc(t.notification).detail" class="nt-detail">
              <template v-if="(desc(t.notification).detail as any).kind === 'status' || (desc(t.notification).detail as any).kind === 'deadline'">
                <span class="nt-pill nt-pill-old">{{ (desc(t.notification).detail as any).from }}</span>
                <svg class="nt-arrow" width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"><path d="M5 12h14M13 6l6 6-6 6"/></svg>
                <span class="nt-pill nt-pill-new" :style="{ color: desc(t.notification).accent, background: desc(t.notification).accent + '16' }">{{ (desc(t.notification).detail as any).to }}</span>
              </template>
              <span v-else class="nt-excerpt">{{ (desc(t.notification).detail as any).text }}</span>
            </div>
          </div>
          <button class="nt-close" @click.stop="dismiss(t.id)" aria-label="Закрыть">
            <svg width="11" height="11" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M3 3l10 10M13 3L3 13"/></svg>
          </button>
          <div class="nt-progress" :style="progressStyle(t) + '; background: ' + priorityColor(t.notification.priority)"></div>
        </div>
      </TransitionGroup>
    </div>
  </Teleport>
</template>

<style scoped>
.nt-stack {
  position: fixed;
  top: 16px; right: 16px;
  display: flex; flex-direction: column;
  gap: 8px;
  z-index: 1200;
  pointer-events: none;
  max-width: 380px;
  font-family: var(--font, system-ui);
}
.nt-stack > div { display: flex; flex-direction: column; gap: 8px; pointer-events: none; }

.nt-toast {
  background: var(--bg1, #fff);
  border-radius: 10px;
  box-shadow: 0 8px 24px rgba(15,23,60,.18), 0 2px 6px rgba(15,23,60,.06);
  padding: 11px 12px;
  display: flex; gap: 10px;
  align-items: flex-start;
  position: relative;
  pointer-events: auto;
  cursor: pointer;
  overflow: hidden;
  min-width: 320px;
  /* top-stripe via .nt-toast::before — colour driven by --nt-accent */
  --nt-accent: var(--t-muted);
}
.nt-toast::before {
  content: ""; position: absolute; top: 0; left: 0; right: 0;
  height: 3px;
  background: var(--nt-accent);
  border-top-left-radius: inherit; border-top-right-radius: inherit;
  transform-origin: left center;
  animation: uzaStripeDrawIn .6s var(--ease-standard) both;
  pointer-events: none; z-index: 1;
}
.nt-toast.prio-low      { --nt-accent: var(--t-muted); }
.nt-toast.prio-normal   { --nt-accent: #7F77DD; }
.nt-toast.prio-high     { --nt-accent: var(--amber); }
.nt-toast.prio-critical {
  --nt-accent: var(--sev-high);
  animation: nt-criticalPulse 1.6s ease-in-out infinite;
}
@keyframes nt-criticalPulse {
  0%, 100% { box-shadow: 0 8px 24px rgba(15,23,60,.18), 0 0 0 0   rgba(226,75,74,.3); }
  50%      { box-shadow: 0 8px 24px rgba(15,23,60,.18), 0 0 0 6px rgba(226,75,74,0);  }
}

.nt-icn {
  width: 28px; height: 28px;
  border-radius: 7px;
  display: inline-flex;
  align-items: center; justify-content: center;
  flex-shrink: 0;
}
.nt-icn i { font-size: 14px; }

.nt-content { flex: 1; min-width: 0; }
.nt-meta { display: flex; gap: 5px; align-items: center; margin-bottom: 1px; }
.nt-prio {
  font-size: 8.5px;
  padding: 1px 5px; border-radius: 3px;
  font-weight: 600; letter-spacing: .04em;
  text-transform: uppercase;
}
.nt-ext {
  background: #D4537E; color: #fff;
  padding: 1px 5px; border-radius: 3px;
  font-size: 8.5px; font-weight: 600; letter-spacing: .04em;
}
.nt-time { font-size: 9.5px; color: var(--t3, var(--t-muted)); margin-left: auto; }

.nt-act {
  display: inline-flex; align-items: center;
  font-size: 9.5px; font-weight: 600; letter-spacing: .01em;
  padding: 2px 8px; border-radius: 999px; white-space: nowrap;
}
.nt-title {
  font-size: 12px; color: var(--t1, #1E2A4A);
  font-weight: 500;
  line-height: 1.35;
  margin-top: 1px;
  display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden;
}
.nt-detail { display: flex; align-items: center; gap: 5px; flex-wrap: wrap; margin-top: 5px; }
.nt-pill {
  font-size: 9.5px; font-weight: 600; line-height: 1;
  padding: 3px 7px; border-radius: 6px;
  font-variant-numeric: tabular-nums; white-space: nowrap;
}
.nt-pill-old { color: var(--t3, #888780); background: #F1F2F6; }
.nt-arrow { color: var(--t4, #B4B2A9); flex-shrink: 0; }
.nt-excerpt {
  font-size: 10.5px; color: var(--t2, #5F5E5A); line-height: 1.4;
  display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden;
  border-left: 2px solid var(--nt-accent, #E5E7EB); padding-left: 7px;
}
.nt-body {
  font-size: 10.5px; color: var(--t3, #5F5E5A);
  line-height: 1.4;
  margin-top: 2px;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.nt-close {
  background: transparent; border: 0;
  color: var(--t3, var(--t-muted)); cursor: pointer;
  padding: 2px; border-radius: 4px;
  display: inline-flex; align-items: center; justify-content: center;
  flex-shrink: 0;
}
.nt-close:hover { background: rgba(0,0,0,.04); color: var(--t1, #1E2A4A); }

.nt-progress {
  position: absolute;
  bottom: 0; left: 0;
  height: 2px;
  opacity: .55;
  transition: width 0.05s linear;
}

/* Slide-in transitions */
.nt-toast-enter-active {
  animation: ntSlideIn 0.32s var(--ease-standard);
}
.nt-toast-leave-active {
  animation: ntFadeOut 0.22s ease-in forwards;
}
.nt-toast-move {
  transition: transform 0.3s var(--ease-standard);
}
@keyframes ntSlideIn {
  from { transform: translateX(120%); opacity: 0; }
  to   { transform: translateX(0);     opacity: 1; }
}
@keyframes ntFadeOut {
  to { transform: translateX(40%); opacity: 0; }
}
</style>
