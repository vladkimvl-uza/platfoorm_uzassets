<script setup lang="ts">
/**
 * NotificationToast — премиум-тосты live-уведомлений (вверху справа):
 *  • свайп-вправо для закрытия (drag-to-dismiss);
 *  • iOS-стопка: при нескольких карточки сложены, по наведению раскрываются;
 *  • группировка одинаковых событий («Eldor и ещё N изменили…»);
 *  • действия на наведении (Открыть · Прочитано);
 *  • кольцо обратного отсчёта вокруг аватара (пауза при наведении).
 *
 * Монтируется один раз в корне (AppShell), подписан на toast-callback стора.
 */
import { onMounted, onUnmounted, ref } from "vue";
import { useRouter } from "vue-router";
import { useNotificationsStore } from "@/stores/notifications";
import { useEntityEditor } from "@/composables/useEntityEditor";
import ActorAvatar from "@/components/ActorAvatar.vue";
import { formatRelativeTime, PRIORITY_LABELS, type Notification } from "@/api/notifications";
import { describeNotification, NOTIF_ICON_PATHS } from "@/composables/useNotificationMeta";
import { useNotificationDetail } from "@/composables/useNotificationDetail";
import { api } from "@/api/client";

const router = useRouter();
const store = useNotificationsStore();
const entityEditor = useEntityEditor();
const notifDetail = useNotificationDetail();

const desc = (n: any) => describeNotification(n);
const iconPath = (k: string) => NOTIF_ICON_PATHS[k] || NOTIF_ICON_PATHS.bell;

interface Toast {
  id: string;
  key: string;
  notification: Notification;
  arrivedAt: number;
  ttlMs: number;
  paused: boolean;
  remainingMs?: number;
  actorName: string;
  actorCompany: string;
  actorJob: string;
  actorIds: string[];
  count: number;
  dx: number;
  dragging: boolean;
}

const toasts = ref<Toast[]>([]);
const toastTimers = new Map<string, number>();
const MAX_TOASTS = 5;
const stackHovered = ref(false);

// ─── Автор: имя · компания · должность — через /users/card (как ActorAvatar),
// общий кеш; payload уведомления — фолбэк, если карточка недоступна. ───
function applyCard(t: Toast, card: any): void {
  const p: any = t.notification.payload || {};
  t.actorName = card?.full_name || p.actor_name || "Пользователь";
  t.actorCompany = card?.company || p.actor_company || "";
  t.actorJob = card?.job_title || p.actor_job_title || "";
}
async function resolveActor(t: Toast, id?: string | null): Promise<void> {
  const p: any = t.notification.payload || {};
  if (!id) {
    if (!t.actorName) t.actorName = p.actor_name || "Система";
    return;
  }
  const cache = (window as any).__uhCache || ((window as any).__uhCache = new Map());
  if (cache.has(id)) { applyCard(t, cache.get(id)); return; }
  try {
    const { data } = await api.get("/users/card", { params: { id } });
    cache.set(id, data);
    applyCard(t, data);
  } catch { applyCard(t, null); }
}

function ttlFor(priority: string): number {
  if (priority === "critical") return 12000;
  if (priority === "high")     return 8000;
  if (priority === "normal")   return 5000;
  return 4000;
}

// Ключ группировки — одинаковое действие над одной сущностью сливается в стопку.
function groupKey(n: Notification): string {
  const d = desc(n);
  const p: any = n.payload || {};
  const et = p.entity_type || (n as any).source_entity_type || "";
  const eid = p.entity_id || (n as any).source_entity_id || "";
  return eid ? `${d.verb}|${et}|${eid}` : `id:${n.id}`;
}

function armTimer(t: Toast, ms: number) {
  const old = toastTimers.get(t.id);
  if (old !== undefined) clearTimeout(old);
  toastTimers.set(t.id, window.setTimeout(() => dismiss(t.id), ms));
}

function pushToast(n: Notification) {
  // тот же конкретный нотиф не обрабатываем дважды
  if (toasts.value.some((t) => t.notification.id === n.id)) return;

  const key = groupKey(n);
  const existing = toasts.value.find((t) => t.key === key);
  if (existing) {
    existing.count += 1;
    if (n.source_user_id && !existing.actorIds.includes(n.source_user_id)) {
      existing.actorIds.push(n.source_user_id);
    }
    existing.notification = n;          // показываем последний
    existing.arrivedAt = Date.now();
    existing.remainingMs = undefined;
    existing.paused = stackHovered.value;
    void resolveActor(existing, n.source_user_id);
    // поднимаем наверх стопки
    toasts.value = [existing, ...toasts.value.filter((t) => t !== existing)];
    if (!stackHovered.value) armTimer(existing, existing.ttlMs);
    return;
  }

  const toast: Toast = {
    id: n.id, key,
    notification: n,
    arrivedAt: Date.now(),
    ttlMs: ttlFor(n.priority),
    paused: stackHovered.value,
    actorName: "",
    actorCompany: "",
    actorJob: "",
    actorIds: n.source_user_id ? [n.source_user_id] : [],
    count: 1,
    dx: 0, dragging: false,
  };
  void resolveActor(toast, n.source_user_id);
  toasts.value.unshift(toast);
  if (toasts.value.length > MAX_TOASTS) {
    const removed = toasts.value.pop();
    if (removed) {
      const tid = toastTimers.get(removed.id);
      if (tid !== undefined) clearTimeout(tid);
      toastTimers.delete(removed.id);
    }
  }
  if (!stackHovered.value) armTimer(toast, toast.ttlMs);
}

function dismiss(id: string) {
  const tid = toastTimers.get(id);
  if (tid !== undefined) { clearTimeout(tid); toastTimers.delete(id); }
  toasts.value = toasts.value.filter((t) => t.id !== id);
}

// ─── Пауза автозакрытия на время наведения на стопку (она же раскрывает её) ───
function pauseAll() {
  stackHovered.value = true;
  for (const t of toasts.value) {
    if (t.paused) continue;
    t.paused = true;
    const tid = toastTimers.get(t.id);
    if (tid !== undefined) { clearTimeout(tid); toastTimers.delete(t.id); }
    t.remainingMs = Math.max(0, t.ttlMs - (Date.now() - t.arrivedAt));
  }
}
function resumeAll() {
  stackHovered.value = false;
  for (const t of toasts.value) {
    if (!t.paused) continue;
    t.paused = false;
    const rem = t.remainingMs ?? t.ttlMs;
    t.arrivedAt = Date.now() - (t.ttlMs - rem);
    armTimer(t, rem);
  }
}

// ─── Свайп-вправо для закрытия ───
const dragStartX = new Map<string, number>();
let suppressClickUntil = 0;
function onDown(t: Toast, e: PointerEvent) {
  if ((e.target as HTMLElement)?.closest("button")) return;       // не на кнопках
  if (e.pointerType === "mouse" && e.button !== 0) return;
  t.dragging = true;
  dragStartX.set(t.id, e.clientX);
  (e.currentTarget as HTMLElement).setPointerCapture?.(e.pointerId);
}
function onMove(t: Toast, e: PointerEvent) {
  if (!t.dragging) return;
  const sx = dragStartX.get(t.id) ?? e.clientX;
  t.dx = Math.max(0, e.clientX - sx);
}
function onUp(t: Toast) {
  if (!t.dragging) return;
  t.dragging = false;
  const dist = t.dx;
  dragStartX.delete(t.id);
  if (dist > 5) suppressClickUntil = Date.now() + 250;
  if (dist > 80) { t.dx = 460; window.setTimeout(() => dismiss(t.id), 170); }
  else { t.dx = 0; }
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

function onCardClick(t: Toast) {
  if (Date.now() < suppressClickUntil) return;   // только что свайпали — не открывать
  openNotification(t);
}
function openNotification(t: Toast) {
  store.markRead(t.notification.id);
  const link = deriveLink(t.notification);
  if (link) {
    if (!entityEditor.openFromLink(link)) router.push(link);
  } else {
    notifDetail.open(t.notification as any);
  }
  dismiss(t.id);
}
function markReadDismiss(t: Toast, e: Event) {
  e.stopPropagation();
  store.markRead(t.notification.id);
  dismiss(t.id);
}

function actorLine(t: Toast): string {
  if (t.count > 1) {
    const extra = Math.max(t.actorIds.length - 1, t.count - 1);
    return extra > 0 ? `${t.actorName || "Кто-то"} и ещё ${extra}` : (t.actorName || "");
  }
  return t.actorName;
}
/** Компания и должность автора — контекст рядом с именем («кто именно изменил»). */
function actorSub(t: Toast): string {
  if (t.count > 1) return "";
  return [t.actorCompany, t.actorJob].filter(Boolean).join(" · ");
}

function priorityBg(p: string) { return PRIORITY_LABELS[p as "critical" | "high" | "normal" | "low"]?.bg || ""; }
function priorityColor(p: string) { return PRIORITY_LABELS[p as "critical" | "high" | "normal" | "low"]?.color || "#5F5E5A"; }

let unregister: (() => void) | null = null;
onMounted(() => {
  store.registerToastCallback(pushToast);
  unregister = () => store.registerToastCallback(() => {});
});
onUnmounted(() => {
  toastTimers.forEach((tid) => clearTimeout(tid));
  toastTimers.clear();
  if (unregister) unregister();
});
</script>

<template>
  <Teleport to="body">
    <div class="nt-stack" :class="{ expanded: stackHovered || toasts.length <= 1 }"
         role="region" aria-label="Уведомления"
         @mouseenter="pauseAll" @mouseleave="resumeAll">
      <TransitionGroup name="ntcard" tag="div" class="nt-list">
        <div v-for="(t, i) in toasts" :key="t.id" class="nt-slot"
             :style="{ '--i': i, zIndex: 1000 - i }">
          <div class="nt-toast"
               :class="[`prio-${t.notification.priority}`, { paused: t.paused, dragging: t.dragging }]"
               :style="{ '--nt-accent': desc(t.notification).accent,
                         transform: t.dx ? `translateX(${t.dx}px)` : '',
                         opacity: t.dx ? Math.max(.25, 1 - t.dx / 280) : '' }"
               @pointerdown="onDown(t, $event)" @pointermove="onMove(t, $event)"
               @pointerup="onUp(t)" @pointercancel="onUp(t)"
               @click="onCardClick(t)">
            <!-- Аватар + кольцо обратного отсчёта -->
            <div class="nt-av-wrap">
              <svg class="nt-ring" viewBox="0 0 44 44" aria-hidden="true">
                <circle class="nt-ring-bg" cx="22" cy="22" r="20" />
                <circle class="nt-ring-fg" cx="22" cy="22" r="20"
                        :style="{ stroke: desc(t.notification).accent,
                                  animationDuration: t.ttlMs + 'ms',
                                  animationPlayState: t.paused ? 'paused' : 'running' }" />
              </svg>
              <ActorAvatar :user-id="t.notification.source_user_id" :size="38" :star="false">
                <span class="nt-icn" :style="{ background: desc(t.notification).accent + '16', color: desc(t.notification).accent }">
                  <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" v-html="iconPath(desc(t.notification).icon)" />
                </span>
              </ActorAvatar>
              <span v-if="t.count > 1" class="nt-av-count" :style="{ background: desc(t.notification).accent }">+{{ t.count - 1 }}</span>
              <span v-else-if="t.notification.source_user_id" class="nt-av-badge" :style="{ color: desc(t.notification).accent }">
                <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round" v-html="iconPath(desc(t.notification).icon)" />
              </span>
            </div>

            <div class="nt-content">
              <div class="nt-meta">
                <span class="nt-act" :style="{ color: desc(t.notification).accent, background: desc(t.notification).accent + '14' }">{{ desc(t.notification).verb }}<template v-if="t.count > 1"> · {{ t.count }}</template></span>
                <span v-if="t.notification.priority === 'high' || t.notification.priority === 'critical'" class="nt-prio" :style="{ background: priorityBg(t.notification.priority), color: priorityColor(t.notification.priority) }">
                  {{ PRIORITY_LABELS[t.notification.priority]?.label || t.notification.priority }}
                </span>
                <span v-if="(t.notification.payload as any)?.is_external" class="nt-ext">EXTERNAL</span>
                <span class="nt-time">{{ formatRelativeTime(t.notification.created_at) }}</span>
              </div>
              <div v-if="actorLine(t)" class="nt-actor">
                <span class="nt-actor-name">{{ actorLine(t) }}</span>
                <span v-if="actorSub(t)" class="nt-actor-sub">{{ actorSub(t) }}</span>
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

              <!-- Действия на наведении -->
              <div class="nt-actions">
                <button class="nt-action nt-action-open" @click.stop="openNotification(t)">Открыть</button>
                <button class="nt-action" @click.stop="markReadDismiss(t, $event)">Прочитано</button>
              </div>
            </div>

            <button class="nt-close" @click.stop="dismiss(t.id)" aria-label="Закрыть">
              <svg width="11" height="11" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M3 3l10 10M13 3L3 13"/></svg>
            </button>
          </div>
        </div>
      </TransitionGroup>
    </div>
  </Teleport>
</template>

<style scoped>
.nt-stack {
  position: fixed;
  top: 16px; right: 16px;
  width: 360px; max-width: calc(100vw - 32px);
  /* было z-index:1200 — тост прятался под модалками; поднят в слой тостов */
  z-index: var(--z-toast, 9800);
  pointer-events: none;
  font-family: var(--font, system-ui);
}
.nt-list { display: flex; flex-direction: column; gap: 8px; }
.nt-slot { pointer-events: none; transition: transform .34s var(--ease-standard), opacity .26s ease; }
.nt-slot > * { pointer-events: auto; }

/* iOS-стопка: когда не наведено и карточек >1 — складываем в одну точку,
   задние выглядывают снизу (сдвиг + уменьшение + затемнение). */
.nt-stack:not(.expanded) .nt-list { display: grid; }
.nt-stack:not(.expanded) .nt-slot {
  grid-area: 1 / 1;
  transform-origin: top center;
  transform: translateY(calc(var(--i) * 12px)) scale(calc(1 - var(--i) * 0.05));
}
.nt-stack:not(.expanded) .nt-slot:nth-child(2) { opacity: .92; }
.nt-stack:not(.expanded) .nt-slot:nth-child(3) { opacity: .8; }
.nt-stack:not(.expanded) .nt-slot:nth-child(n+4) { opacity: 0; pointer-events: none; }

.nt-toast {
  background: var(--bg1, #fff);
  border-radius: 12px;
  box-shadow: 0 8px 24px rgba(15,23,60,.18), 0 2px 6px rgba(15,23,60,.06);
  padding: 11px 12px;
  display: flex; gap: 11px;
  align-items: flex-start;
  position: relative;
  pointer-events: auto;
  cursor: pointer;
  overflow: hidden;
  border: 1px solid rgba(15, 23, 60, .05);
  transition: transform .18s var(--ease-standard), box-shadow .18s var(--ease-standard);
  touch-action: pan-y;
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
/* подъём только в раскрытой стопке (когда видно карточку целиком) */
.nt-stack.expanded .nt-toast:hover {
  transform: translateY(-2px);
  box-shadow: 0 16px 40px rgba(15,23,60,.22), 0 4px 10px rgba(15,23,60,.10);
}
.nt-toast.dragging { transition: none; cursor: grabbing; }
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

/* ── Аватар + кольцо обратного отсчёта ── */
.nt-av-wrap { position: relative; flex-shrink: 0; width: 38px; height: 38px; }
.nt-ring { position: absolute; top: -3px; left: -3px; width: 44px; height: 44px; pointer-events: none; transform: rotate(-90deg); z-index: 2; }
.nt-ring-bg { fill: none; stroke: rgba(15,23,60,.08); stroke-width: 2.4; }
.nt-ring-fg {
  fill: none; stroke-width: 2.4; stroke-linecap: round;
  stroke-dasharray: 125.66; stroke-dashoffset: 0;
  animation-name: ntRing; animation-timing-function: linear; animation-fill-mode: forwards;
}
@keyframes ntRing { to { stroke-dashoffset: 125.66; } }

.nt-icn { width: 28px; height: 28px; border-radius: 7px; display: inline-flex; align-items: center; justify-content: center; flex-shrink: 0; }
.nt-av-badge {
  position: absolute; right: -3px; bottom: -3px;
  width: 17px; height: 17px; border-radius: 50%;
  display: inline-flex; align-items: center; justify-content: center;
  background: #fff; box-shadow: 0 1px 4px rgba(15,23,60,.22); z-index: 3;
}
.nt-av-count {
  position: absolute; right: -5px; bottom: -5px;
  min-width: 18px; height: 18px; padding: 0 4px; border-radius: 9px;
  display: inline-flex; align-items: center; justify-content: center;
  color: #fff; font-size: 9.5px; font-weight: 700; line-height: 1;
  border: 2px solid var(--bg1, #fff); box-shadow: 0 1px 4px rgba(15,23,60,.22); z-index: 3;
}

.nt-content { flex: 1; min-width: 0; }
.nt-meta { display: flex; gap: 5px; align-items: center; margin-bottom: 1px; }
.nt-act {
  display: inline-flex; align-items: center;
  font-size: 9.5px; font-weight: 700; letter-spacing: .02em; text-transform: uppercase;
  padding: 2px 8px; border-radius: 999px; white-space: nowrap;
}
.nt-prio { font-size: 8.5px; padding: 1px 5px; border-radius: 3px; font-weight: 600; letter-spacing: .04em; text-transform: uppercase; }
.nt-ext { background: #D4537E; color: #fff; padding: 1px 5px; border-radius: 3px; font-size: 8.5px; font-weight: 600; letter-spacing: .04em; }
.nt-time { font-size: 9.5px; color: var(--t3, var(--t-muted)); margin-left: auto; }
.nt-actor { display: flex; align-items: baseline; gap: 6px; margin-top: 1px; line-height: 1.25; min-width: 0; }
.nt-actor-name { font-size: 11.5px; font-weight: 700; color: var(--t1, #1E2A4A); white-space: nowrap; }
.nt-actor-sub {
  font-size: 10px; font-weight: 500; color: var(--t3, #888780);
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis; min-width: 0;
}
.nt-title {
  font-size: 12px; color: var(--t1, #1E2A4A); font-weight: 500; line-height: 1.35; margin-top: 1px;
  display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden;
}
.nt-detail { display: flex; align-items: center; gap: 5px; flex-wrap: wrap; margin-top: 5px; }
.nt-pill { font-size: 9.5px; font-weight: 600; line-height: 1; padding: 3px 7px; border-radius: 6px; font-variant-numeric: tabular-nums; white-space: nowrap; }
.nt-pill-old { color: var(--t3, #888780); background: #F1F2F6; }
.nt-arrow { color: var(--t4, #B4B2A9); flex-shrink: 0; }
.nt-excerpt {
  font-size: 10.5px; color: var(--t2, #5F5E5A); line-height: 1.4;
  display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden;
  border-left: 2px solid var(--nt-accent, #E5E7EB); padding-left: 7px;
}

/* ── Действия на наведении ── */
.nt-actions {
  display: flex; gap: 7px; margin-top: 0;
  max-height: 0; opacity: 0; overflow: hidden;
  transition: max-height .22s var(--ease-standard), opacity .18s ease, margin-top .22s var(--ease-standard);
}
.nt-stack.expanded .nt-toast:hover .nt-actions { max-height: 40px; opacity: 1; margin-top: 8px; }
.nt-action {
  border: 1px solid rgba(15,23,60,.12); background: var(--bg1, #fff);
  color: var(--t2, #475569); font-family: inherit; font-size: 11px; font-weight: 600;
  padding: 5px 12px; border-radius: 8px; cursor: pointer; transition: all .14s;
}
.nt-action:hover { border-color: var(--nt-accent); color: var(--nt-accent); background: color-mix(in srgb, var(--nt-accent) 8%, #fff); }
.nt-action-open { background: var(--nt-accent); border-color: var(--nt-accent); color: #fff; }
.nt-action-open:hover { filter: brightness(1.06); color: #fff; }

.nt-close {
  background: transparent; border: 0;
  color: var(--t3, var(--t-muted)); cursor: pointer;
  padding: 2px; border-radius: 4px;
  display: inline-flex; align-items: center; justify-content: center; flex-shrink: 0;
}
.nt-close:hover { background: rgba(0,0,0,.04); color: var(--t1, #1E2A4A); }

/* ── Появление / уход / перестановка (TransitionGroup name="ntcard") ── */
.ntcard-enter-active .nt-toast { animation: ntSlideIn .42s cubic-bezier(.22, 1.2, .36, 1); }
.ntcard-leave-active { transition: opacity .24s ease, transform .24s ease; position: absolute; width: 100%; }
.ntcard-leave-to { opacity: 0; transform: translateX(40%); }
.ntcard-move { transition: transform .32s var(--ease-standard); }
@keyframes ntSlideIn {
  0%   { transform: translateX(120%) scale(.96); opacity: 0; }
  55%  { opacity: 1; }
  100% { transform: translateX(0) scale(1);      opacity: 1; }
}

@media (prefers-reduced-motion: reduce) {
  .ntcard-enter-active .nt-toast, .nt-ring-fg, .nt-toast::before { animation: none !important; }
  .nt-slot, .nt-toast { transition: none; }
  .nt-stack.expanded .nt-toast:hover { transform: none; }
  .nt-toast.prio-critical { animation: none; }
}
</style>
