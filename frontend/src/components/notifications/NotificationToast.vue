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
import { iconFor, formatRelativeTime, PRIORITY_LABELS, type Notification } from "@/api/notifications";

const router = useRouter();
const store = useNotificationsStore();

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

function openNotification(t: Toast) {
  store.markRead(t.notification.id);
  if (t.notification.link_url) {
    router.push(t.notification.link_url);
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
             @click="openNotification(t)">
          <span class="nt-icn"
                :style="{ background: priorityBg(t.notification.priority), color: priorityColor(t.notification.priority) }">
            <i :class="`ti ti-${iconFor(t.notification.type)}`" aria-hidden="true"></i>
          </span>
          <div class="nt-content">
            <div class="nt-meta">
              <span class="nt-prio" :style="{ background: priorityBg(t.notification.priority), color: priorityColor(t.notification.priority) }">
                {{ PRIORITY_LABELS[t.notification.priority]?.label || t.notification.priority }}
              </span>
              <span v-if="(t.notification.payload as any)?.is_external" class="nt-ext">EXTERNAL</span>
              <span class="nt-time">{{ formatRelativeTime(t.notification.created_at) }}</span>
            </div>
            <div class="nt-title">{{ t.notification.title }}</div>
            <div v-if="t.notification.body" class="nt-body">{{ t.notification.body }}</div>
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
  animation:
    uzaStripeDrawIn .6s var(--ease-standard) both,
    uzaStripeBreathe 2.8s ease-in-out 1s infinite;
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

.nt-title {
  font-size: 12px; color: var(--t1, #1E2A4A);
  font-weight: 500;
  line-height: 1.35;
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
