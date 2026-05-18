<script setup lang="ts">
/**
 *
 * Этот компонент НЕ переписывает финансовую модель в Vue — он провайдит
 * затем вызывает window.showFinModelView() который полностью владеет рендером
 * #main-content. Дизайн, анимации, логика, редактор, экспорт PDF/Excel —
 *
 * Поток:
 *   1. onMounted → подготовить globals (window._db, window.S, window.FB_URL, стабы)
 *   2. Загрузить SheetJS (XLSX) с CDN
 *   3. Загрузить /legacy/finmodel.js → определяет window.showFinModelView
 *   4. Загрузить из backend _db.finModel + _db.creditPortfolio + _db.companies
 *
 *   onUnmounted → cleanup global timers/handlers, не выгружаем JS (cache hit)
 */
import { onBeforeUnmount, onMounted } from "vue";
import { api } from "@/api/client";
import { useCompaniesStore } from "@/stores/companies";
import { canonSectorCode } from "@/utils/displayNames";
import { SECTOR_COLORS } from "@/utils/sectorMeta";


// ─── Lifecycle ───
let scriptLoaded = !!(window as any).showFinModelView;
let beforeUnloadCleanup: (() => void) | null = null;

async function ensureXlsxLoaded(): Promise<void> {
  if ((window as any).XLSX) return;
  return new Promise((resolve, reject) => {
    const s = document.createElement("script");
    s.src = "https://cdn.jsdelivr.net/npm/xlsx@0.18.5/dist/xlsx.full.min.js";
    s.onload = () => resolve();
    s.onerror = () => reject(new Error("Failed to load SheetJS"));
    document.head.appendChild(s);
  });
}

async function ensureBridgeCssLoaded(): Promise<void> {
  if (document.getElementById("uza-bridge-css")) return;
  return new Promise((resolve, reject) => {
    const l = document.createElement("link");
    l.id = "uza-bridge-css";
    l.rel = "stylesheet";
    l.href = "/legacy/uza-bridge.css";
    l.onload = () => resolve();
    l.onerror = () => reject(new Error("Failed to load /legacy/uza-bridge.css"));
    document.head.appendChild(l);
  });
}

async function ensureBridgeJsLoaded(): Promise<void> {
  if ((window as any).__uzaBridgeLoaded) return;
  return new Promise((resolve, reject) => {
    const s = document.createElement("script");
    s.src = "/legacy/uza-bridge.js";
    s.onload = () => { (window as any).__uzaBridgeLoaded = true; resolve(); };
    s.onerror = () => reject(new Error("Failed to load /legacy/uza-bridge.js"));
    document.head.appendChild(s);
  });
}

async function ensureLegacyScriptLoaded(): Promise<void> {
  if (scriptLoaded) return;
  return new Promise((resolve, reject) => {
    const s = document.createElement("script");
    s.src = "/legacy/finmodel.js";
    s.onload = () => { scriptLoaded = true; resolve(); };
    s.onerror = () => reject(new Error("Failed to load /legacy/finmodel.js"));
    document.head.appendChild(s);
  });
}

function setupGlobalStubs() {
  const w = window as any;

  // ─── CRITICAL inline CSS injection — bypasses any cache/load issues with uza-bridge.css.
  // This guarantees topbar + edit-menu work correctly even if the bridge.css fails to load
  // or is overridden by other rules. Uses !important to win all specificity battles.
  if (!document.getElementById("uza-fm-critical-css")) {
    const style = document.createElement("style");
    style.id = "uza-fm-critical-css";
    style.textContent = `
      /* ─── Topbar (Pack 142: hidden, replaced by Vue topbar) ─── */
      #main-content .dash-topbar { display: none !important; }
      #main-content .dash-topbar-LEGACY {
        position: relative !important;
        display: grid !important;
        grid-template-columns: auto 1fr auto !important;
        grid-template-rows: 48px !important;
        align-items: center !important;
        gap: 14px !important;
        
        background: linear-gradient(180deg, #1E2A4A 0%, #1A2440 100%) !important;
        padding: 0 20px !important;
        width: 100% !important;
        max-width: 100% !important;
        box-sizing: border-box !important;
        color: #fff !important;
        z-index: 10 !important;
        flex-wrap: nowrap !important;
        gap: 14px !important;
      }
      #main-content .dash-tb-l { display:flex !important; align-items:center !important; gap:10px !important; justify-self:start !important; min-width:0 !important; grid-column:1 !important; grid-row:1 !important; align-self:center !important; }
      #main-content .dash-tb-c { display:flex !important; flex-direction:column !important; align-items:center !important; justify-content:center !important; gap:2px !important; min-width:0 !important; overflow:hidden !important; padding:0 14px !important; text-align:center !important; grid-column:2 !important; grid-row:1 !important; align-self:center !important; height:100% !important; }
      #main-content .dash-tb-r { display:flex !important; align-items:center !important; gap:6px !important; justify-self:end !important; grid-column:3 !important; grid-row:1 !important; align-self:center !important; }

      /* ─── Edit-menu (⋯ button + dropdown) ─── */
      #main-content .edit-menu-wrap { position:relative !important; display:inline-flex !important; }
      #main-content .edit-menu-btn {
        width:34px !important; height:34px !important;
        border:1.5px solid rgba(127,119,221,.55) !important;
        background:rgba(127,119,221,.25) !important;
        border-radius:8px !important;
        cursor:pointer !important;
        display:flex !important; align-items:center !important; justify-content:center !important;
        color:rgba(255,255,255,.7) !important;
        transition:all .15s !important; padding:0 !important;
      }
      #main-content .edit-menu-btn:hover { background:rgba(255,255,255,.14) !important; color:#fff !important; }
      #main-content .edit-menu-btn.open { background:rgba(255,255,255,.2) !important; color:#fff !important; }
      /* Force the SVG ⋮ dots to be visible — original uses stroke-only tiny rings (invisible).
         Fill them solid so they show as 3 clear dots. */
      #main-content .edit-menu-btn svg { width: 18px !important; height: 18px !important; }
      #main-content .edit-menu-btn svg circle {
        fill: currentColor !important;
        stroke: none !important;
        r: 2.2 !important;
      }
      #main-content .edit-menu-dd { transform-origin: top right !important;
        display: none !important;
        position: absolute !important;
        top: calc(100% + 6px) !important;
        right: 0 !important;
        min-width: 240px !important; max-width: calc(100vw - 40px) !important;
        background: #1E2A4A !important;
        border: 1px solid rgba(255,255,255,.12) !important;
        border-radius: 10px !important;
        padding: 5px !important;
        box-shadow: 0 8px 24px rgba(0,0,0,.35), 0 4px 12px rgba(0,0,0,.18) !important;
        z-index: 1000 !important;
      }
      #main-content .edit-menu-dd.show {
        display: block !important;
        animation: editMenuIn .18s cubic-bezier(.34,1.2,.64,1) both;
      }
      @keyframes editMenuIn {
        from { opacity:0; transform:translateY(-4px) scale(.97); }
        to   { opacity:1; transform:translateY(0) scale(1); }
      }
      #main-content .edit-menu-dd button {
        display:flex !important; align-items:center !important; gap:8px !important;
        width:100% !important; padding:9px 12px !important;
        border:none !important; background:transparent !important;
        color:rgba(255,255,255,.82) !important;
        font-size:12px !important; font-weight:500 !important;
        cursor:pointer !important; border-radius:6px !important; text-align:left !important;
        transition:all .1s !important;
      }
      #main-content .edit-menu-dd button:hover { background:rgba(255,255,255,.08) !important; color:#fff !important; }
      #main-content .edit-menu-dd button.danger { color:rgba(226,75,74,.82) !important; }
      #main-content .edit-menu-dd button.danger:hover { background:rgba(226,75,74,.12) !important; color:#E24B4A !important; }
      #main-content .edit-menu-dd .sep { height:1px !important; background:rgba(255,255,255,.1) !important; margin:4px 8px !important; }

      #main-content #fm-header-title { color: #fff !important; font-size: 14px !important; font-weight: 600 !important; letter-spacing: .01em !important; line-height: 1.2 !important; white-space: nowrap !important; overflow: hidden !important; text-overflow: ellipsis !important; }
      #main-content #fm-header-sub { color: rgba(255,255,255,.55) !important; font-size: 10px !important; font-weight: 500 !important; letter-spacing: .08em !important; text-transform: uppercase !important; white-space: nowrap !important; }
      /* ─── Glass-select widget (company picker) ─── */
      #main-content .glass-select { position:relative !important; display:inline-flex !important; }
      #main-content .glass-select-btn {
        background:rgba(255,255,255,.08) !important;
        border:1px solid rgba(255,255,255,.12) !important;
        color:#fff !important;
        border-radius:8px !important;
        cursor:pointer !important;
        display:inline-flex !important; align-items:center !important;
        font-size:12px !important; font-weight:500 !important;
        transition:all .15s !important;
      }
      #main-content .glass-select-btn:hover { background:rgba(255,255,255,.14) !important; }
      #main-content .glass-select-menu {
        display:none !important;
        position:absolute !important;
        top:calc(100% + 6px) !important; left:0 !important;
        background:#1E2A4A !important;
        border:1px solid rgba(255,255,255,.12) !important;
        border-radius:10px !important;
        padding:5px !important;
        box-shadow:0 8px 24px rgba(0,0,0,.35) !important;
        z-index:1000 !important;
      }
      #main-content .glass-select.open .glass-select-menu { display:block !important; }
      #main-content .glass-select-item {
        display:flex !important; align-items:center !important;
        width:100% !important; padding:7px 10px !important;
        border:none !important; background:transparent !important;
        color:rgba(255,255,255,.78) !important;
        font-size:12px !important; cursor:pointer !important;
        border-radius:6px !important; text-align:left !important;
      }
      #main-content .glass-select-item:hover { background:rgba(255,255,255,.08) !important; color:#fff !important; }
      #main-content .glass-select-item.active { background:rgba(127,119,221,.2) !important; color:#fff !important; }
    `;
    document.head.appendChild(style);
  }

  if (!w._db) w._db = {};

  if (!w.S) w.S = {};
  w.S.view = "finmodel";

  // ─── FB_URL: route to backend Firebase RTDB-style endpoint
  // → becomes `${STORAGE_BASE}.json` stripped + `/finModel.json` = `${STORAGE_BASE}/finModel.json`
  w.FB_URL = () => `${STORAGE_BASE}.json`;

  // ─── COMPANIES: filled by seedCompaniesFromStore() from /companies API.
  // Initialize as empty array — the legacy bundle will read it after
  // seedCompaniesFromStore() completes (called by onMounted before the
  if (!w.COMPANIES) w.COMPANIES = [];

  // to inject the bearer token for any request going to STORAGE_BASE.
  const origFetch = w._origFetch || w.fetch;
  if (!w._origFetch) w._origFetch = origFetch;
  w.fetch = function (input: RequestInfo, init?: RequestInit) {
    const url = typeof input === "string" ? input : input.url;
    if (url && url.includes(STORAGE_BASE)) {
      // Pinia auth store stores tokens under "uza_access_token"
      const tk = localStorage.getItem("uza_access_token") || localStorage.getItem("access_token");
      if (tk) {
        init = init || {};
        init.headers = { ...(init.headers || {}), Authorization: `Bearer ${tk}` };
      }
    }
    return origFetch.call(w, input, init);
  };

  if (!w.SECTOR_SOLID) {
    w.SECTOR_SOLID = {
      mining:    "#9B8EC4",
      oilgas:    "#1D9E75",
      energy:    "#EF9F27",
      transport: "#378ADD",
      other:     "#888780",
    };
  }

  // ─── UI stubs (Vue handles sidebar/nav — make these noops)
  w.killCharts = w.killCharts || function() { /* noop */ };
  w.renderSidebar = w.renderSidebar || function() { /* noop */ };
  w.toggleSidebar = w.toggleSidebar || function() { /* noop */ };
  w.logTelemetry = w.logTelemetry || function(_evt: string, _name: string, _meta?: unknown) { /* noop */ };
  w.sbToggleBtnHtml = w.sbToggleBtnHtml || function() { return ""; };
  w._uzaOpenModal = w._uzaOpenModal || function() { /* noop */ };
  w._uzaCloseModal = w._uzaCloseModal || function() { /* noop */ };
  // esc — standard HTML escape helper, used ~50 places in legacy fm code
  if (!w.esc) {
    w.esc = function(s: unknown): string {
      const str = s == null ? "" : String(s);
      return str
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;")
        .replace(/'/g, "&#39;");
    };
  }

  // _isReducedMotion — checks user's motion preference
  if (!w._isReducedMotion) {
    w._isReducedMotion = function(): boolean {
      try {
        return window.matchMedia("(prefers-reduced-motion: reduce)").matches;
      } catch { return false; }
    };
  }
  // cpCompanySectorColor — color for a company's sector (used by drill modal)
  if (!w.cpCompanySectorColor) {
    w.cpCompanySectorColor = function(co: string): string {
      const list = (w.COMPANIES || []) as Array<{name: string; color: string}>;
      const m = list.find(c => c.name === co);
      return m?.color || "#7F77DD";
    };
  }
  // cpDrillLoansTableHtml — drill modal loans table; only used by UAP autofill flow
  if (!w.cpDrillLoansTableHtml) {
    w.cpDrillLoansTableHtml = function(): string { return ""; };
  }

  // ─── Credit-portfolio helpers (used only inside cpCompute → cpDrillOpen, optional flow) ───
  // _ease — animation easing, fallback to linear
  if (!w._ease) w._ease = function(t: number): number { return t; };
  // cpBankShortName — abbreviation for bank, fallback to first 12 chars
  if (!w.cpBankShortName) w.cpBankShortName = function(b: string): string { return String(b || "").substring(0, 12); };
  // cpClassifyLender — lender category bucket, fallback "other"
  if (!w.cpClassifyLender) w.cpClassifyLender = function(): string { return "other"; };
  // cpDaysBetween — date diff in days
  if (!w.cpDaysBetween) w.cpDaysBetween = function(a: Date, b: Date): number {
    return Math.round((+b - +a) / 86400000);
  };
  // cpGetDB — credit portfolio data accessor
  if (!w.cpGetDB) w.cpGetDB = function() { return (w._db && w._db.creditPortfolio) || {loans: [], fxRates: w.CP_RATES_FX}; };
  // cpMatBucket — maturity bucket for a loan
  if (!w.cpMatBucket) w.cpMatBucket = function(): string { return "mid"; };

  if (!w.YearRegistry) {
    w.YearRegistry = {
      all: () => [2024, 2025, 2026, 2027, 2028, 2029, 2030],
      has: (y: number) => true,
      add: () => {}, remove: () => {},
      inflation: (y: number) => 0.10,
      usdRate: (y: number) => 12500,
    };
  }

  if (!w.CP_RATES_FX) {
    w.CP_RATES_FX = { USD: 12078.47, EUR: 14234.48, JPY: 76, UZS: 1 };
  }
}

async function loadDataIntoDb() {
  const w = window as any;

  // Load _db.finModel from backend
  try {
    const { data } = await api.get(`/finmodel-storage/root/finModel.json`);
    w._db.finModel = data || {};
  } catch (e) {
    console.warn("[FinModel host] failed to load finModel:", e);
    w._db.finModel = {};
  }

  // Load companies (for picker) — and build a display-name-keyed sector map
  // so the legacy `_fmExResolveSector(displayName)` never falls through to
  // its hardcoded fallback list (frontend/public/legacy/finmodel.js:6055).
  try {
    const store = useCompaniesStore();
    await store.ensureLoaded();
    w._db.companies = store.companies.map((c: any) => ({
      code: c.code,
      name_ru: c.name_ru || c.name_short,
      sectorCode: c.sector_code,
      sectorName: c.sector_name,
    }));
    w._db.sectorByCo = {};
    for (const c of store.companies) {
      const secLabel = c.sector_name || c.sector_code || "—";
      // Index under every possible display key the legacy code may call with.
      if (c.name_ru)    w._db.sectorByCo[c.name_ru]    = secLabel;
      if (c.name_short) w._db.sectorByCo[c.name_short] = secLabel;
      if (c.code)       w._db.sectorByCo[c.code]       = secLabel;
    }
  } catch (e) {
    console.warn("[FinModel host] failed to load companies:", e);
    w._db.companies = [];
    w._db.sectorByCo = {};
  }

  // Load credit portfolio (for UAP autofill)
  try {
    const { data } = await api.get(`/credit-portfolio/loans`);
    w._db.creditPortfolio = {
      loans: data?.items || data || [],
      fxRates: w.CP_RATES_FX,
      asOf: "2026-01-01",
    };
  } catch (e) {
    console.warn("[FinModel host] credit portfolio not available:", e);
    w._db.creditPortfolio = { loans: [], fxRates: w.CP_RATES_FX, asOf: "2026-01-01" };
  }
}

/**
 * Load the canonical company roster from the backend and project it into
 * `sector` is normalized to one of mining|oilgas|energy|transport|other so the
 * legacy code's sector grouping keeps working when new companies are added.
 */
async function seedCompaniesFromStore(): Promise<void> {
  const store = useCompaniesStore();
  await store.ensureLoaded();
  const w = window as any;
  const rows = store.companies
    .slice()
    .sort((a, b) => (a.sort_order ?? 9999) - (b.sort_order ?? 9999))
    .map(c => {
      const sec = canonSectorCode(c.sector_code) as keyof typeof SECTOR_COLORS;
      return {
        name: c.name_short || c.name_ru,
        abbr: c.code.toUpperCase(),
        sector: sec,
        color: SECTOR_COLORS[sec] || "#888780",
      };
    });
  if (rows.length > 0) w.COMPANIES = rows;
}

onMounted(async () => {
  try {
    setupGlobalStubs();
    await seedCompaniesFromStore();
    await ensureBridgeCssLoaded();
    await ensureXlsxLoaded();
    await ensureBridgeJsLoaded();
    await loadDataIntoDb();
    await ensureLegacyScriptLoaded();

    // Now invoke the entry point.
    if (typeof (window as any).showFinModelView === "function") {
      (window as any).showFinModelView();
    } else {
      console.error("[FinModel host] window.showFinModelView is not defined after script load");
      const mc = document.getElementById("main-content");
      if (mc) {
        mc.innerHTML = '<div style="padding:40px;text-align:center;color:#A32D2D">⚠ Не удалось инициализировать финансовую модель: showFinModelView отсутствует.</div>';
      }
    }
  } catch (e) {
    console.error("[FinModel host] init failed:", e);
    const mc = document.getElementById("main-content");
    if (mc) {
      mc.innerHTML = `<div style="padding:40px;text-align:center;color:#A32D2D">⚠ Ошибка инициализации: ${(e as Error).message}</div>`;
    }
  }
});

onBeforeUnmount(() => {
  const w = window as any;
  if (typeof w._fmBackupTimer === "number") {
    clearInterval(w._fmBackupTimer);
    w._fmBackupTimer = null;
  }
  if (typeof w._fmDetachBeforeUnload === "function") {
    try { w._fmDetachBeforeUnload(); } catch { /* noop */ }
  }
  // Don't restore original fetch — leaving the interceptor active is harmless and
  // avoids race conditions if user navigates back quickly.
});

// Pack 141: Vue topbar state
import { ref, computed, onMounted, onBeforeUnmount, inject } from 'vue';
const toggleSidebar = inject<() => void>('toggleSidebar', () => {});
const fmDdOpen = ref(false);
const fmEditOpen = ref(false);
const fmActions = [
  { code: 'import',  label: 'Импорт шаблона Excel',  icon: '<svg width="13" height="13" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M8 3v8M4.5 7.5L8 11l3.5-3.5M3 13h10"/></svg>' },
  { code: 'export',  label: 'Экспорт Excel',          icon: '<svg width="13" height="13" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M8 13V5M4.5 8.5L8 5l3.5 3.5M3 3h10"/></svg>' },
  { code: 'editor',  label: 'Редактор модели',        icon: '<svg width="13" height="13" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M11.5 2.5l2 2L5 13H3v-2z"/></svg>' },
  { code: 'restore', label: 'Восстановить из черновика', icon: '<svg width="13" height="13" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M3 8a5 5 0 1 0 1.5-3.5M3 3v3h3"/></svg>' },
  { code: 'pdf',     label: 'Экспорт PDF для НС',     icon: '<svg width="13" height="13" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M9 2H4v12h8V5zm0 0v3h3"/></svg>' },
];
function fmFireAction(code: string) {
  fmEditOpen.value = false;
  const w: any = window;
  const fnName = 'fm_action_' + code;
  if (typeof w[fnName] === 'function') {
    try { w[fnName](); return; } catch (e) { console.warn('[fm action]', fnName, e); }
  }
  window.dispatchEvent(new CustomEvent('fm:action', { detail: { code } }));
  console.info('[fm:action]', code);
}
function closeFmEditOutside(e: MouseEvent) {
  if (!fmEditOpen.value) return;
  const t = e.target as HTMLElement;
  if (!t.closest('.fm-edit-btn') && !t.closest('.fm-tb-r > div')) fmEditOpen.value = false;
}
const fmSelectedId = ref<string | null>(null);
const fmCompanies = ref<{id:string;name:string}[]>([]);
const fmSelectedName = computed(() => {
  const c = fmCompanies.value.find(x => x.id === fmSelectedId.value);
  return c?.name || '';
});
function pickFmCompany(id: string, name: string) {
  fmSelectedId.value = id;
  fmDdOpen.value = false;
  const w: any = window;
  if (w._db) {
    w._db._fmSelectedCompanyId = id;
    w._db._fmSelectedCompanyName = name;
  }
  window.dispatchEvent(new CustomEvent('fm:companyChange', { detail: { id, name } }));
}
  const w: any = window;
  const fm = w._db?.finModel;
  if (!fm || typeof fm !== 'object') return [];
  const keys = Object.keys(fm).filter(k => {
    if (!k || k === 'undefined' || k === 'null') return false;
    const v = fm[k];
    return v && typeof v === 'object' && Object.keys(v).length > 0;
  });
  return keys.map(k => ({ id: k, name: k }));
}
async function loadFmCompanies() {
  console.info('[FinModel] === loadFmCompanies START ===');
  const start = Date.now();
  while (Date.now() - start < 15000) {
    if (found.length > 0) {
      fmCompanies.value = found;
      const w: any = window;
      if (w._fmSelCo && found.some(c => c.id === w._fmSelCo)) {
        fmSelectedId.value = w._fmSelCo;
      } else if (found.length > 0) {
        fmSelectedId.value = found[0].id;
      }
      console.info('[FinModel] loaded', found.length, 'companies from _db.finModel; selected:', fmSelectedId.value);
      return;
    }
    await new Promise(r => setTimeout(r, 300));
  }
  console.warn('[FinModel] _db.finModel still empty after 15s');
  fmCompanies.value = [];
}function closeFmDdOutside(e: MouseEvent) {
  if (!fmDdOpen.value) return;
  const t = e.target as HTMLElement;
  if (!t.closest('.fm-glass-select') && !t.closest('.fm-tb-l > div')) fmDdOpen.value = false;
}
onMounted(() => {
  document.addEventListener('click', closeFmDdOutside);
  document.addEventListener('click', closeFmEditOutside);
});
onBeforeUnmount(() => { document.removeEventListener('click', closeFmDdOutside); document.removeEventListener('click', closeFmEditOutside); });
</script>

<template>
  <div class="fm-shell">
    <!-- Pack 141: Vue-rendered topbar (burger + company dropdown + title) -->
    <div class="fm-topbar">
      <div class="fm-tb-l" style="position:relative">
        <button class="fm-sb-toggle" @click="toggleSidebar()" title="Скрыть/показать сайдбар" aria-label="toggle sidebar">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round">
            <line x1="3" y1="6" x2="21" y2="6"/>
            <line x1="3" y1="12" x2="21" y2="12"/>
            <line x1="3" y1="18" x2="21" y2="18"/>
          </svg>
        </button>
        <button
          class="fm-glass-select"
          @click.stop="fmDdOpen = !fmDdOpen"
          style="display:flex;align-items:center;gap:8px;padding:5px 11px;min-width:180px;height:32px;background:rgba(255,255,255,.08);border:1px solid rgba(255,255,255,.12);border-radius:8px;color:#fff;font-size:12px;font-weight:500;cursor:pointer;"
        >
          <span style="width:7px;height:7px;border-radius:50%;flex-shrink:0;background:#9B8EC4;"></span>
          <span style="flex:1;text-align:left;white-space:nowrap;overflow:hidden;text-overflow:ellipsis">{{ fmSelectedName || 'Все компании' }}</span>
          <svg width="10" height="10" viewBox="0 0 12 12" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" :style="{transform: fmDdOpen ? 'rotate(180deg)':'rotate(0deg)', transition:'transform .15s'}"><path d="M2 4.5l4 4 4-4"/></svg>
        </button>
        <div
          v-if="fmDdOpen"
          @click.stop
          style="position:absolute;top:44px;left:56px;z-index:100;min-width:260px;max-height:420px;overflow-y:auto;background:#1E2A4A;border:1px solid rgba(255,255,255,.12);border-radius:10px;padding:4px;display:flex;flex-direction:column;gap:1px;box-shadow:0 12px 32px rgba(15,23,60,.4);"
        >
          <div v-if="fmCompanies.length === 0" style="padding:12px 11px;color:rgba(255,255,255,.5);font-size:11px;font-weight:500;text-align:center">
            Загрузка...
          </div>
          <button
            v-for="c in fmCompanies"
            :key="c.id"
            @click="pickFmCompany(c.id, c.name)"
            :style="{display:'flex',alignItems:'center',gap:'9px',padding:'8px 11px',background: fmSelectedId === c.id ? 'rgba(155,142,196,.18)':'transparent',border:'none',color:'#fff',fontSize:'12px',fontWeight:'500',cursor:'pointer',borderRadius:'6px',textAlign:'left',width:'100%'}"
          >
            <span :style="{width:'7px',height:'7px',borderRadius:'50%',flexShrink:0,background: fmSelectedId === c.id ? '#9B8EC4':'#D1D5DB'}"></span>
            <span style="flex:1;text-align:left;white-space:nowrap;overflow:hidden;text-overflow:ellipsis">{{ c.name }}</span>
          </button>
        </div>
      </div>
      <div class="fm-tb-c">
        <div class="fm-tb-eyebrow">UzAssets · Финансы</div>
        <div class="fm-tb-title">Финансовая модель · {{ fmSelectedName || 'портфель' }}</div>
      </div>
      <div class="fm-tb-r" style="position:relative">
        <button
          class="fm-edit-btn"
          :class="{ open: fmEditOpen }"
          @click.stop="fmEditOpen = !fmEditOpen"
          aria-label="menu"
          style="width:32px;height:32px;border:1px solid rgba(255,255,255,.15);background:rgba(255,255,255,.06);border-radius:8px;cursor:pointer;display:flex;align-items:center;justify-content:center;color:rgba(255,255,255,.7);transition:all .15s;padding:0;"
        >
          <svg width="18" height="18" viewBox="0 0 24 24" fill="currentColor">
            <circle cx="12" cy="5" r="2"/><circle cx="12" cy="12" r="2"/><circle cx="12" cy="19" r="2"/>
          </svg>
        </button>
        <div
          v-if="fmEditOpen"
          @click.stop
          style="position:absolute;top:42px;right:0;z-index:100;min-width:240px;background:#1E2A4A;border:1px solid rgba(255,255,255,.12);border-radius:10px;padding:4px;display:flex;flex-direction:column;gap:1px;box-shadow:0 12px 32px rgba(15,23,60,.4);"
        >
          <button v-for="a in fmActions" :key="a.code" @click="fmFireAction(a.code)"
            :style="{display:'flex',alignItems:'center',gap:'10px',padding:'8px 11px',background:'transparent',border:'none',color:'#fff',fontSize:'12px',fontWeight:'500',cursor:'pointer',borderRadius:'6px',textAlign:'left',width:'100%'}"
          >
            <span style="color:rgba(255,255,255,.55);flex-shrink:0;display:inline-flex;align-items:center;justify-content:center;width:14px;height:14px" v-html="a.icon"></span>
            <span style="flex:1;text-align:left">{{ a.label }}</span>
          </button>
        </div>
      </div>
    </div>
    <div id="main-content" class="fm-host-root" style="width:100%;max-width:100%;overflow-x:hidden;box-sizing:border-box"></div>
  </div>
</template>

<style scoped>
.fm-shell {
  display: flex;
  flex-direction: column;
  min-height: 100vh;
  background: #F4F3F9;
}
.fm-host-root {
  flex: 1;
  width: 100%;
  background: #F4F3F9;
}
.fm-topbar {
  display: grid;
  grid-template-columns: auto 1fr auto;
  grid-template-rows: 56px;
  align-items: center;
  gap: 14px;
  padding: 0 24px;
  background: linear-gradient(180deg, #1E2A4A 0%, #1A2440 100%);
  color: #fff;
  border-bottom: 0.5px solid rgba(255,255,255,0.06);
  position: relative;
  z-index: 10;
}
.fm-tb-l { display: flex; align-items: center; gap: 12px; }
.fm-tb-c {
  display: flex; flex-direction: column; align-items: center; gap: 1px;
  min-width: 0; text-align: center;
}
.fm-tb-r { justify-self: end; }
.fm-tb-eyebrow {
  font-size: 9.5px; font-weight: 500; letter-spacing: .1em;
  text-transform: uppercase; color: rgba(255,255,255,.5);
}
.fm-tb-title {
  font-size: 15px; font-weight: 500; letter-spacing: -.01em;
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
}
.fm-sb-toggle {
  width: 32px; height: 32px;
  border: 1px solid rgba(255,255,255,.15);
  background: rgba(255,255,255,.06);
  border-radius: 8px; cursor: pointer;
  display: flex; align-items: center; justify-content: center;
  color: rgba(255,255,255,.7); transition: all .15s; padding: 0;
  flex-shrink: 0;
}
.fm-sb-toggle:hover { background: rgba(255,255,255,.14); color: #fff; }
.fm-sb-toggle:active { transform: scale(.94); }
.fm-glass-select:hover { background: rgba(255,255,255,.14) !important; }
.fm-edit-btn:hover { background: rgba(255,255,255,.14) !important; color: #fff !important; }
.fm-edit-btn.open { background: rgba(255,255,255,.2) !important; color: #fff !important; }
.fm-tb-r > div button:hover { background: rgba(255,255,255,.08) !important; }
</style>
