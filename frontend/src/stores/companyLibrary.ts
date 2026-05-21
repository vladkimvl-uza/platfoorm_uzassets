/**
 * Pinia store for the Company Library (MDM) — Phase 2.
 *
 * Owns:
 *   • current page state (rows, columns, views, filters, sort)
 *   • optimistic field updates with auto-rollback on backend error
 *   • WebSocket subscription to /ws/companies for live cross-tab sync
 *   • auto-reconnect with exponential back-off
 */
import { defineStore } from "pinia";
import { computed, ref } from "vue";
import {
  companyLibraryApi,
  type FieldDefinition,
  type FieldUpdateEvent,
  type LibraryCompanyRow,
  type LibraryTab,
  type LibraryView,
} from "@/api/companyLibrary";

export const useCompanyLibraryStore = defineStore("companyLibrary", () => {
  // ── State ──────────────────────────────────────────────────────────
  const companies = ref<LibraryCompanyRow[]>([]);
  const total     = ref(0);
  const columns   = ref<FieldDefinition[]>([]);
  const allFields = ref<FieldDefinition[]>([]);
  const views     = ref<LibraryView[]>([]);
  const tabs      = ref<LibraryTab[]>([]);
  const activeViewId = ref<string | null>(null);

  // Filters
  const sectorFilter = ref<string | null>(null);
  const searchQuery  = ref<string>("");
  const sortBy       = ref<string>("name_ru");
  const sortDir      = ref<"asc" | "desc">("asc");

  // Network
  const loading      = ref(false);
  const error        = ref<string | null>(null);
  const lastLoadedAt = ref<number | null>(null);

  // WebSocket
  let ws: WebSocket | null = null;
  let wsReconnectAttempt   = 0;
  let wsReconnectTimer: ReturnType<typeof setTimeout> | null = null;
  const wsConnected = ref(false);

  // ── Computeds ──────────────────────────────────────────────────────
  const activeView = computed(() =>
    activeViewId.value
      ? views.value.find(v => v.id === activeViewId.value) || null
      : views.value.find(v => v.is_default) || null,
  );

  /** Codes of fields that should be visible. Falls back to default-set if
   * the active view has no visible_columns explicitly set. */
  const visibleColumnCodes = computed<string[]>(() => {
    if (activeView.value && activeView.value.visible_columns.length > 0) {
      return activeView.value.visible_columns;
    }
    // Default: first 8 fields by sort_order
    return columns.value.slice(0, 8).map(c => c.code);
  });

  const visibleColumns = computed<FieldDefinition[]>(() => {
    const map = new Map(columns.value.map(c => [c.code, c]));
    return visibleColumnCodes.value
      .map(code => map.get(code))
      .filter((c): c is FieldDefinition => c !== undefined);
  });

  // ── Actions ────────────────────────────────────────────────────────
  async function load() {
    loading.value = true;
    error.value = null;
    try {
      const resp = await companyLibraryApi.list({
        sector: sectorFilter.value || undefined,
        search: searchQuery.value || undefined,
        view_id: activeViewId.value || undefined,
        limit: 500,
        offset: 0,
      });
      // Client-side sort (server returns by sort_order; respect user choice)
      const items = [...resp.items];
      items.sort((a, b) => {
        const av = (a.fields[sortBy.value] ?? a.name_ru) as any;
        const bv = (b.fields[sortBy.value] ?? b.name_ru) as any;
        const cmp = av == null
          ? 1
          : bv == null
            ? -1
            : (typeof av === "number" && typeof bv === "number")
              ? av - bv
              : String(av).localeCompare(String(bv), "ru");
        return sortDir.value === "desc" ? -cmp : cmp;
      });
      companies.value     = items;
      total.value         = resp.total;
      columns.value       = resp.columns;
      views.value         = resp.available_views;
      activeViewId.value  = resp.active_view_id ?? activeViewId.value;
      lastLoadedAt.value  = Date.now();
    } catch (e: any) {
      error.value = e?.response?.data?.detail || e?.message || "Не удалось загрузить библиотеку";
    } finally {
      loading.value = false;
    }
  }

  async function loadAllFields(sector?: string) {
    try {
      allFields.value = await companyLibraryApi.listFields({ sector });
    } catch {
      allFields.value = [];
    }
  }

  async function loadTabs() {
    try {
      tabs.value = await companyLibraryApi.listTabs();
    } catch {
      tabs.value = [];
    }
  }

  /** Optimistic field write with rollback. */
  async function updateField(companyId: string, code: string, value: any) {
    const co = companies.value.find(c => c.id === companyId);
    const prev = co ? co.fields[code] : undefined;
    if (co) {
      co.fields = { ...co.fields, [code]: value };
    }
    try {
      await companyLibraryApi.updateField(companyId, code, value);
    } catch (e: any) {
      // Rollback
      if (co) co.fields = { ...co.fields, [code]: prev };
      throw e;
    }
  }

  function setSectorFilter(code: string | null) { sectorFilter.value = code; }
  function setSearch(q: string)                  { searchQuery.value  = q; }
  function setSort(by: string, dir?: "asc"|"desc") {
    if (sortBy.value === by && !dir) {
      sortDir.value = sortDir.value === "asc" ? "desc" : "asc";
    } else {
      sortBy.value  = by;
      sortDir.value = dir || (typeof companies.value[0]?.fields[by] === "number" ? "desc" : "asc");
    }
  }
  function setActiveView(id: string | null) {
    activeViewId.value = id;
    load();
  }

  // ── WebSocket ──────────────────────────────────────────────────────
  function _applyEvent(msg: FieldUpdateEvent) {
    if (msg.type !== "field_update") return;
    const co = companies.value.find(c => c.id === msg.company_id);
    if (co) {
      co.fields = { ...co.fields, [msg.field_code]: msg.value };
    }
  }

  function connectWebSocket() {
    if (ws && (ws.readyState === WebSocket.OPEN || ws.readyState === WebSocket.CONNECTING)) {
      return;
    }
    if (wsReconnectTimer) {
      clearTimeout(wsReconnectTimer);
      wsReconnectTimer = null;
    }
    try {
      const proto = window.location.protocol === "https:" ? "wss:" : "ws:";
      ws = new WebSocket(`${proto}//${window.location.host}/api/ws/companies`);
      ws.onopen = () => {
        wsConnected.value = true;
        wsReconnectAttempt = 0;
      };
      ws.onmessage = (ev) => {
        try {
          const msg = JSON.parse(ev.data) as FieldUpdateEvent;
          _applyEvent(msg);
        } catch {
          /* ignore malformed */
        }
      };
      ws.onerror = () => { /* onclose follows */ };
      ws.onclose = () => {
        wsConnected.value = false;
        ws = null;
        // Reconnect with exponential back-off up to 30s
        const delay = Math.min(30_000, 1_000 * Math.pow(2, wsReconnectAttempt));
        wsReconnectAttempt++;
        wsReconnectTimer = setTimeout(connectWebSocket, delay);
      };
    } catch {
      wsConnected.value = false;
    }
  }

  function disconnect() {
    if (wsReconnectTimer) {
      clearTimeout(wsReconnectTimer);
      wsReconnectTimer = null;
    }
    if (ws) {
      try { ws.close(); } catch { /* ignore */ }
      ws = null;
    }
    wsConnected.value = false;
  }

  return {
    // state
    companies, total, columns, allFields, views, tabs, activeViewId,
    sectorFilter, searchQuery, sortBy, sortDir,
    loading, error, lastLoadedAt, wsConnected,
    // computeds
    activeView, visibleColumnCodes, visibleColumns,
    // actions
    load, loadAllFields, loadTabs, updateField,
    setSectorFilter, setSearch, setSort, setActiveView,
    connectWebSocket, disconnect,
  };
});
