/**
 * Notifications store (Pack 11.0).
 *
 * Live channel:
 *   1. Primary — WebSocket /notifications/ws/{access_token}
 *   2. Fallback — polling /notifications/unread-count every 30s if WS not connected
 *
 * Auto-reconnect with exponential backoff (1s → 30s cap).
 * Toast notifications fired via a callback registered by ToastContainer.vue.
 */
import { defineStore } from "pinia";
import { useAuthStore } from "./auth";
import { notificationsApi, type Notification, type NotificationPreference } from "@/api/notifications";

const WS_PATH = "/notifications/ws";
const POLL_INTERVAL_MS = 30_000;
const WS_PING_INTERVAL_MS = 25_000;
const RECONNECT_INITIAL_MS = 1_000;
const RECONNECT_MAX_MS = 30_000;

type ToastCallback = (n: Notification) => void;

interface State {
  unreadCount: number;
  unreadByPriority: Record<string, number>;
  unreadByType: Record<string, number>;
  recent: Notification[];           // dropdown shows last ~10
  preferences: NotificationPreference[];
  isConnected: boolean;
  connectionMode: "ws" | "polling" | "offline";
  lastSyncAt: string | null;
}

let _ws: WebSocket | null = null;
let _pollTimer: number | null = null;
let _pingTimer: number | null = null;
let _reconnectDelay = RECONNECT_INITIAL_MS;
let _reconnectTimer: number | null = null;
let _toastCb: ToastCallback | null = null;
let _shouldRun = false;     // user logged in?

export const useNotificationsStore = defineStore("notifications", {
  state: (): State => ({
    unreadCount: 0,
    unreadByPriority: {},
    unreadByType: {},
    recent: [],
    preferences: [],
    isConnected: false,
    connectionMode: "offline",
    lastSyncAt: null,
  }),

  getters: {
    hasUnread: (s) => s.unreadCount > 0,
    criticalCount: (s) => s.unreadByPriority["critical"] || 0,
    highCount: (s) => s.unreadByPriority["high"] || 0,
  },

  actions: {
    // ─── Public API ──────────────────────────────────────
    registerToastCallback(cb: ToastCallback) { _toastCb = cb; },

    async start() {
      _shouldRun = true;
      await this.refreshCount();
      await this.refreshRecent();
      this._connectWebSocket();
      this._startPollingFallback();
    },

    stop() {
      _shouldRun = false;
      this._disconnectWebSocket();
      this._stopPollingFallback();
      if (_reconnectTimer !== null) {
        clearTimeout(_reconnectTimer);
        _reconnectTimer = null;
      }
      this.isConnected = false;
      this.connectionMode = "offline";
    },

    async refreshCount() {
      try {
        const data = await notificationsApi.unreadCount();
        this.unreadCount = data.count;
        this.unreadByPriority = data.by_priority || {};
        this.unreadByType = data.by_type || {};
        this.lastSyncAt = new Date().toISOString();
      } catch (e) {
        console.warn("[notifications] refreshCount failed", e);
      }
    },

    async refreshRecent() {
      try {
        const data = await notificationsApi.feed({ per_page: 15 });
        this.recent = data.items;
        this.unreadCount = data.unread_count;
        this.lastSyncAt = new Date().toISOString();
      } catch (e) {
        console.warn("[notifications] refreshRecent failed", e);
      }
    },

    async markRead(id: string) {
      // Optimistic
      const item = this.recent.find((n) => n.id === id);
      if (item && !item.is_read) {
        item.is_read = true;
        item.read_at = new Date().toISOString();
        if (this.unreadCount > 0) this.unreadCount--;
      }
      try { await notificationsApi.readOne(id); }
      catch (e) { console.warn("[notifications] markRead failed", e); await this.refreshCount(); }
    },

    async markAllRead() {
      this.recent.forEach((n) => {
        if (!n.is_read) { n.is_read = true; n.read_at = new Date().toISOString(); }
      });
      this.unreadCount = 0;
      this.unreadByPriority = {};
      this.unreadByType = {};
      try { await notificationsApi.readAll(); }
      catch (e) { console.warn("[notifications] markAllRead failed", e); await this.refreshCount(); }
    },

    async archive(id: string) {
      this.recent = this.recent.filter((n) => n.id !== id);
      try { await notificationsApi.archiveOne(id); }
      catch (e) { console.warn("[notifications] archive failed", e); }
      await this.refreshCount();
    },

    async loadPreferences() {
      try { this.preferences = await notificationsApi.preferences(); }
      catch (e) { console.warn("[notifications] loadPreferences failed", e); }
    },

    // ─── WebSocket ───────────────────────────────────────
    _connectWebSocket() {
      if (!_shouldRun) return;
      const auth = useAuthStore();
      if (!auth.accessToken) {
        this.connectionMode = "offline";
        return;
      }
      this._disconnectWebSocket();

      const base = import.meta.env.VITE_API_BASE_URL || "/api";
      const wsProto = location.protocol === "https:" ? "wss:" : "ws:";
      const wsHost = base.startsWith("http") ? base.replace(/^https?:/, wsProto) : `${wsProto}//${location.host}${base}`;
      const url = `${wsHost}${WS_PATH}/${encodeURIComponent(auth.accessToken)}`;

      try {
        _ws = new WebSocket(url);
      } catch (e) {
        console.warn("[notifications] WS construction failed", e);
        this._scheduleReconnect();
        return;
      }

      _ws.addEventListener("open", () => {
        this.isConnected = true;
        this.connectionMode = "ws";
        _reconnectDelay = RECONNECT_INITIAL_MS;
        this._startPing();
      });

      _ws.addEventListener("message", (evt) => {
        try {
          const data = JSON.parse(evt.data);
          this._handleEvent(data);
        } catch (e) {
          console.warn("[notifications] WS message parse failed", e);
        }
      });

      _ws.addEventListener("close", () => {
        this.isConnected = false;
        this.connectionMode = "polling";
        this._stopPing();
        if (_shouldRun) this._scheduleReconnect();
      });

      _ws.addEventListener("error", () => {
        this.isConnected = false;
      });
    },

    _disconnectWebSocket() {
      if (_ws) {
        try { _ws.close(); } catch {}
        _ws = null;
      }
      this._stopPing();
    },

    _scheduleReconnect() {
      if (_reconnectTimer !== null) clearTimeout(_reconnectTimer);
      _reconnectTimer = window.setTimeout(() => {
        _reconnectTimer = null;
        _reconnectDelay = Math.min(_reconnectDelay * 2, RECONNECT_MAX_MS);
        this._connectWebSocket();
      }, _reconnectDelay);
    },

    _startPing() {
      this._stopPing();
      _pingTimer = window.setInterval(() => {
        if (_ws && _ws.readyState === WebSocket.OPEN) {
          try { _ws.send(JSON.stringify({ type: "ping" })); } catch {}
        }
      }, WS_PING_INTERVAL_MS);
    },

    _stopPing() {
      if (_pingTimer !== null) { clearInterval(_pingTimer); _pingTimer = null; }
    },

    _handleEvent(data: { event: string; notification?: Notification; unread_count?: number }) {
      if (data.event === "notification.new" && data.notification) {
        const n = data.notification;
        if (!this.recent.find((x) => x.id === n.id)) {
          this.recent.unshift(n);
          if (this.recent.length > 30) this.recent.pop();
        }
        if (!n.is_read) this.unreadCount++;
        if (n.priority) {
          this.unreadByPriority[n.priority] = (this.unreadByPriority[n.priority] || 0) + 1;
        }
        if (_toastCb) {
          try { _toastCb(n); } catch (e) { console.warn("[notifications] toast cb failed", e); }
        }
      } else if (data.event === "notification.unread_count" && typeof data.unread_count === "number") {
        this.unreadCount = data.unread_count;
      } else if (data.event === "system.ping") {
        // keepalive — nothing to do
      }
    },

    // ─── Polling fallback ────────────────────────────────
    _startPollingFallback() {
      this._stopPollingFallback();
      _pollTimer = window.setInterval(() => {
        if (!_shouldRun) return;
        // Only poll if WS is not connected
        if (this.connectionMode !== "ws") {
          this.refreshCount();
        }
      }, POLL_INTERVAL_MS);
    },

    _stopPollingFallback() {
      if (_pollTimer !== null) { clearInterval(_pollTimer); _pollTimer = null; }
    },
  },
});
