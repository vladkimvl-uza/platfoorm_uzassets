/**
 * useToast.ts -- Singleton composable for toast notifications.
 *
 * Архитектура: shared reactive state на уровне модуля + один <ToastContainer />
 * в корне приложения. Любой компонент может вызвать toast.success("...").
 *
 *   - ok   (#1D9E75) success messages
 *   - err  (#E24B4A) errors
 *   - info (#378ADD) neutral notifications
 *
 * Также сохраняет последние 50 уведомлений в localStorage для NotificationBell.
 */

import { ref, readonly } from "vue";

export type ToastKind = "ok" | "err" | "info";

export interface ToastItem {
  id: number;
  kind: ToastKind;
  message: string;
  duration: number; // ms, 0 = persistent
  timestamp: number;
}

export interface NotificationHistoryItem {
  id: number;
  kind: ToastKind;
  message: string;
  timestamp: number;
  read: boolean;
}

// Module-level singleton state
const toasts = ref<ToastItem[]>([]);
const history = ref<NotificationHistoryItem[]>([]);
const HISTORY_KEY = "uza_notification_history_v1";
const HISTORY_MAX = 50;

let _idCounter = 0;

// Initialize from localStorage
function _loadHistory() {
  try {
    const raw = localStorage.getItem(HISTORY_KEY);
    if (raw) {
      const arr = JSON.parse(raw);
      if (Array.isArray(arr)) {
        history.value = arr.slice(0, HISTORY_MAX);
      }
    }
  } catch (e) {
    // ignore -- corrupted localStorage
  }
}

function _saveHistory() {
  try {
    localStorage.setItem(
      HISTORY_KEY,
      JSON.stringify(history.value.slice(0, HISTORY_MAX)),
    );
  } catch (e) {
    // ignore
  }
}

// Lazy init
let _initialized = false;
function _init() {
  if (_initialized) return;
  _initialized = true;
  _loadHistory();
}

function show(message: string, kind: ToastKind = "info", duration = 3500): number {
  _init();
  const id = ++_idCounter;
  const ts = Date.now();
  const item: ToastItem = { id, kind, message, duration, timestamp: ts };
  toasts.value.push(item);

  // Add to history
  history.value = [
    { id, kind, message, timestamp: ts, read: false },
    ...history.value,
  ].slice(0, HISTORY_MAX);
  _saveHistory();

  if (duration > 0) {
    setTimeout(() => {
      remove(id);
    }, duration);
  }
  return id;
}

function remove(id: number) {
  toasts.value = toasts.value.filter((t) => t.id !== id);
}

function clear() {
  toasts.value = [];
}

// History actions
function markAsRead(id: number) {
  const item = history.value.find((h) => h.id === id);
  if (item) {
    item.read = true;
    _saveHistory();
  }
}

function markAllAsRead() {
  history.value.forEach((h) => {
    h.read = true;
  });
  _saveHistory();
}

function clearHistory() {
  history.value = [];
  _saveHistory();
}

export function useToast() {
  _init();
  return {
    // Active toasts (for ToastContainer)
    toasts: readonly(toasts),
    // Show methods
    show,
    success: (msg: string, dur?: number) => show(msg, "ok", dur),
    error: (msg: string, dur?: number) => show(msg, "err", dur ?? 5000),
    info: (msg: string, dur?: number) => show(msg, "info", dur),
    // Manage active
    remove,
    clear,
    // History (for NotificationBell)
    history: readonly(history),
    unreadCount: () => history.value.filter((h) => !h.read).length,
    markAsRead,
    markAllAsRead,
    clearHistory,
  };
}
