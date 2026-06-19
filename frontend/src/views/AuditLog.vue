<script setup lang="ts">
/**
 * Audit Log Dashboard (Pack 9.0)
 *
 * Visible to owner + anyone with audit.view permission.
 * Single `/admin/audit/overview` call hydrates entire page.
 *
 * Layout (1:1 mockup):
 *   Topbar dark navy (live indicator + Export CSV + Settings)
 *   Filter bar (search ⌘K + 4 selects)
 *   6 KPI cards (kpi2 + fin-shimmer)
 *   Mid grid 1.5fr+1fr: Timeline feed + side panels (top users / top modules / security flags)
 *   Bottom: multi-line SVG chart per action type
 *
 * Auto-refresh overview every 30s. Pause when tab hidden.
 */
import { computed, onMounted, onUnmounted, ref, watch } from "vue";
import { useRouter } from "vue-router";
import { useAuthStore } from "@/stores/auth";
import {
  auditApi,
  actionMeta,
  formatTime,
  formatDateShort,
  type AuditEventRead,
  type AuditEventDetail,
  type AuditOverviewResponse,
} from "@/api/audit";
import { useFormatters } from "@/composables/useFormatters";
import { useToast } from "@/composables/useToast";

const fmt = useFormatters();
const toast = useToast();

// Pack 9.2.2: embedded mode — used as a tab inside RBAC v3 (no own topbar)
const props = defineProps<{ embedded?: boolean }>();

const router = useRouter();
const auth = useAuthStore();

// ─── State ─────────────────────────────────────────────────
const overview = ref<AuditOverviewResponse | null>(null);
const loading = ref(false);
const error = ref<string | null>(null);
const hours = ref<number>(24);
const search = ref("");
const filterUser = ref("");
const filterModule = ref("");
const filterAction = ref("");

// Drill detail
const drillEvent = ref<AuditEventDetail | null>(null);
const drillLoading = ref(false);

// Pagination — "Load more"
const extraEvents = ref<AuditEventRead[]>([]);
const extraPage = ref(1);          // last page fetched into extraEvents (overview gave page 1)
const extraLoading = ref(false);
const PAGE_SIZE = 50;

let pollTimer: number | null = null;

// ─── RBAC guard ────────────────────────────────────────────
if (!auth.isOwner && !auth.hasPermission("audit.view")) {
  router.replace("/dashboard");
}

// ─── Load ──────────────────────────────────────────────────
async function load() {
  loading.value = true;
  error.value = null;
  try {
    overview.value = await auditApi.overview(hours.value);
  } catch (e: unknown) {
    const err = e as { response?: { data?: { detail?: string } }; message?: string };
    error.value = err?.response?.data?.detail || err?.message || "Не удалось загрузить журнал";
  } finally {
    loading.value = false;
  }
}

function startPolling() {
  stopPolling();
  pollTimer = window.setInterval(() => {
    if (document.visibilityState === "visible" && !drillEvent.value) load();
  }, 30_000);
}
function stopPolling() {
  if (pollTimer !== null) { clearInterval(pollTimer); pollTimer = null; }
}

onMounted(() => {
  load();
  startPolling();
  document.addEventListener("visibilitychange", onVis);
});
onUnmounted(() => {
  stopPolling();
  document.removeEventListener("visibilitychange", onVis);
});
function onVis() {
  if (document.visibilityState === "visible") load();
}

watch(hours, () => { extraEvents.value = []; extraPage.value = 1; load(); });
// Reset pagination when filters change (we ask backend to re-filter)
watch([search, filterUser, filterModule, filterAction], () => {
  extraEvents.value = [];
  extraPage.value = 1;
});

// ─── Combined events feed: overview's recent_events + paginated extras ───
const allFeedEvents = computed<AuditEventRead[]>(() => {
  const recent = overview.value?.recent_events ?? [];
  if (extraEvents.value.length === 0) return recent;
  // Dedupe by id (overview's recent_events overlap with first page of extraEvents)
  const seen = new Set(recent.map(e => e.id));
  const merged = [...recent];
  for (const e of extraEvents.value) {
    if (!seen.has(e.id)) {
      seen.add(e.id);
      merged.push(e);
    }
  }
  return merged;
});

// ─── Apply client-side filters to combined events ───────────
const filteredEvents = computed<AuditEventRead[]>(() => {
  let items = allFeedEvents.value;
  const q = search.value.trim().toLowerCase();
  if (filterUser.value)   items = items.filter(e => e.actor_email === filterUser.value);
  if (filterModule.value) items = items.filter(e => e.module === filterModule.value);
  if (filterAction.value) items = items.filter(e => e.action === filterAction.value);
  if (q) {
    items = items.filter(e =>
      (e.actor_email || "").toLowerCase().includes(q) ||
      (e.http_path || "").toLowerCase().includes(q) ||
      (e.entity_label || "").toLowerCase().includes(q) ||
      (e.entity_id || "") === q ||
      (e.ip_address || "") === q
    );
  }
  return items;
});

const userOptions = computed(() => {
  const set = new Set<string>();
  allFeedEvents.value.forEach(e => { if (e.actor_email) set.add(e.actor_email); });
  (overview.value?.top_users ?? []).forEach(u => { if (u.email) set.add(u.email); });
  return Array.from(set).sort();
});
const moduleOptions = computed(() => overview.value?.top_modules.map(m => m.module) ?? []);

// ─── Load more (paginated) ─────────────────────────────────
async function loadMoreEvents() {
  if (extraLoading.value) return;
  extraLoading.value = true;
  try {
    extraPage.value += 1;
    const resp = await auditApi.listEvents({
      hours: hours.value,
      actor_email: filterUser.value || undefined,
      module: filterModule.value || undefined,
      action: filterAction.value || undefined,
      search: search.value || undefined,
      page: extraPage.value,
      per_page: PAGE_SIZE,
    });
    extraEvents.value.push(...resp.items);
  } catch (e: unknown) {
    const err = e as { message?: string };
    error.value = err?.message || "Не удалось загрузить дополнительные события";
  } finally {
    extraLoading.value = false;
  }
}

const totalEvents = computed(() => overview.value?.stats.events_total ?? 0);
const hasMore = computed(() => allFeedEvents.value.length < totalEvents.value);

// ─── Drill ─────────────────────────────────────────────────
async function openEvent(id: string) {
  drillLoading.value = true;
  try {
    drillEvent.value = await auditApi.eventDetail(id);
  } catch (e: unknown) {
    error.value = "Не удалось загрузить событие";
  } finally {
    drillLoading.value = false;
  }
}
function closeDrill() { drillEvent.value = null; }

function exportCsv() {
  const token = localStorage.getItem("uza_access_token");
  if (!token) return;
  const url = `/api${auditApi.exportCsvUrl(hours.value)}`;
  fetch(url, { headers: { Authorization: `Bearer ${token}` } })
    .then(r => r.blob())
    .then(b => {
      const a = document.createElement("a");
      a.href = URL.createObjectURL(b);
      a.download = `audit-${hours.value}h.csv`;
      a.click();
    })
    .catch(() => toast.error("Не удалось скачать CSV"));
}

// ─── Chart geometry ────────────────────────────────────────
const chartData = computed(() => {
  const buckets = overview.value?.timeline.buckets ?? [];
  if (!buckets.length) return null;
  const maxVal = Math.max(
    1,
    ...buckets.flatMap(b => [b.view, b.update, b.create, b.delete, b.error])
  );
  const W = 760, H = 100, padL = 40, padR = 10, padT = 10, padB = 14;
  const innerW = W - padL - padR, innerH = H - padT - padB;
  const step = buckets.length > 1 ? innerW / (buckets.length - 1) : 0;
  function mkPath(key: keyof typeof buckets[0]) {
    return buckets.map((b, i) => {
      const v = b[key] as number;
      const x = padL + i * step;
      const y = padT + innerH - (v / maxVal) * innerH;
      return `${i === 0 ? "M" : "L"}${x.toFixed(1)},${y.toFixed(1)}`;
    }).join(" ");
  }
  return {
    W, H, padL, padT, padB, innerH,
    paths: {
      view:   mkPath("view"),
      update: mkPath("update"),
      create: mkPath("create"),
      delete: mkPath("delete"),
      error:  mkPath("error"),
    },
    xLabels: buckets.map((b, i) => ({
      x: padL + i * step,
      label: new Date(b.ts).getHours().toString().padStart(2, "0") + ":00",
      showLabel: i % Math.max(1, Math.floor(buckets.length / 8)) === 0,
    })),
    maxVal,
  };
});

function clearFilters() {
  search.value = "";
  filterUser.value = "";
  filterModule.value = "";
  filterAction.value = "";
}
</script>

<template>
  <div class="au-view">
    <!-- ═══ Topbar (hidden when embedded inside RBAC v3) ═══ -->
    <div v-if="!props.embedded" class="au-topbar">
      <div class="au-tb-l">
        <div class="au-tb-eyebrow">
          <svg width="11" height="11" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="2"><path d="M8 1l6 3v4c0 4-3 7-6 7s-6-3-6-7V4l6-3z"/></svg>
          UzAssets · Owner panel · Аудит
        </div>
        <div class="au-tb-title">Журнал активности портфеля</div>
        <div class="au-tb-sub">
          <span v-if="overview">
            <b>{{ fmt.fmtNumber(overview.stats.events_total) }}</b> событий за {{ hours }}ч
            ·
            <b>{{ overview.stats.online_users }}</b> пользователей онлайн
            <span class="au-live"><span class="au-live-dot"></span> live</span>
          </span>
          <span v-else>загрузка…</span>
        </div>
      </div>
      <div class="au-tb-r">
        <select v-model.number="hours" class="au-in">
          <option :value="1">За 1 час</option>
          <option :value="6">За 6 часов</option>
          <option :value="24">За 24 часа</option>
          <option :value="168">За неделю</option>
          <option :value="720">За месяц</option>
        </select>
        <button
          v-if="auth.isOwner || auth.hasPermission('audit.admin')"
          class="au-btn au-btn-ghost"
          @click="exportCsv"
        >
          <svg width="13" height="13" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M8 1v10M3 7l5 5 5-5M2 14h12"/></svg>
          Экспорт CSV
        </button>
        <button class="au-btn au-btn-primary" @click="router.push('/admin/rbac')">
          <svg width="13" height="13" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="8" cy="8" r="2.5"/></svg>
          RBAC
        </button>
      </div>
    </div>

    <!-- ═══ Compact summary bar when embedded ═══ -->
    <div v-if="props.embedded" class="au-emb-summary">
      <div class="au-emb-stat">
        <span class="au-emb-live"><span class="au-live-dot"></span> live</span>
        <span v-if="overview">
          <b>{{ fmt.fmtNumber(overview.stats.events_total) }}</b> событий за {{ hours }}ч ·
          <b>{{ overview.stats.online_users }}</b> онлайн ·
          <b>{{ overview.stats.unique_users }}</b> уникальных пользователей
        </span>
      </div>
      <div class="au-emb-controls">
        <select v-model.number="hours" class="au-emb-select">
          <option :value="1">1 час</option>
          <option :value="6">6 часов</option>
          <option :value="24">24 часа</option>
          <option :value="168">неделя</option>
          <option :value="720">месяц</option>
        </select>
        <button v-if="auth.isOwner || auth.hasPermission('audit.admin')"
                class="au-emb-btn" @click="exportCsv">
          <svg width="11" height="11" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M8 1v10M3 7l5 5 5-5M2 14h12"/></svg>
          Экспорт CSV
        </button>
      </div>
    </div>

    <!-- ═══ Filter bar ═══ -->
    <div class="au-filterbar">
      <div class="au-search">
        <svg width="13" height="13" viewBox="0 0 16 16" fill="none" stroke="#888780" stroke-width="2" stroke-linecap="round"><circle cx="7" cy="7" r="5"/><path d="M11 11l3 3"/></svg>
        <input v-model="search" placeholder="Поиск по email, IP, endpoint, entity ID…" />
        <span class="au-kbd">⌘K</span>
      </div>
      <select v-model="filterUser" class="au-fl">
        <option value="">Все пользователи</option>
        <option v-for="u in userOptions" :key="u" :value="u">{{ u }}</option>
      </select>
      <select v-model="filterModule" class="au-fl">
        <option value="">Все модули</option>
        <option v-for="m in moduleOptions" :key="m" :value="m">{{ m }}</option>
      </select>
      <select v-model="filterAction" class="au-fl">
        <option value="">Все действия</option>
        <option value="VIEW">VIEW</option>
        <option value="CREATE">CREATE</option>
        <option value="UPDATE">UPDATE</option>
        <option value="DELETE">DELETE</option>
        <option value="EXPORT">EXPORT</option>
        <option value="FAILED">FAILED</option>
        <option value="ERROR">ERROR</option>
      </select>
      <button v-if="search || filterUser || filterModule || filterAction"
              class="au-clear" @click="clearFilters">× очистить</button>
    </div>

    <div v-if="error" class="au-error">{{ error }}</div>

    <div v-if="overview" class="au-body">
      <!-- ═══ 6 KPI cards ═══ -->
      <div class="au-kpi-strip">
        <div
          v-for="(s, i) in overview.stats.stats"
          :key="s.key"
          class="au-kpi fin-shimmer"
          :style="{ '--d': (40 + i * 50) + 'ms', '--ac': s.accent || '#7F77DD' }"
        >
          <div class="au-kpi-lbl">{{ s.label }}</div>
          <div class="au-kpi-v">{{ fmt.fmtNumber(s.value) }}</div>
          <div class="au-kpi-sub">
            {{ s.sub || "" }}
            <span v-if="s.delta_pct != null" :class="['au-delta', s.delta_pct >= 0 ? 'up' : 'down']">
              {{ s.delta_pct >= 0 ? "+" : "" }}{{ s.delta_pct }}%
            </span>
          </div>
        </div>
      </div>

      <!-- ═══ Mid grid: Timeline (left) + Side panels (right) ═══ -->
      <div class="au-mid-grid">

        <!-- Events feed -->
        <div class="au-card au-feed" style="--d:320ms">
          <div class="au-card-hd">
            <span class="au-card-ttl">
              <svg width="12" height="12" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="2"><path d="M3 4h10M3 8h10M3 12h7"/></svg>
              Лента событий · {{ filteredEvents.length }} {{ filteredEvents.length === overview.recent_events.length ? "последних" : "из " + overview.recent_events.length }}
            </span>
            <span class="au-card-meta">обновлено только что</span>
          </div>
          <div class="au-feed-body">
            <div v-if="!filteredEvents.length" class="au-empty">Нет событий по фильтру</div>
            <div
              v-for="(ev, i) in filteredEvents"
              :key="ev.id"
              class="au-feed-row"
              :class="{ critical: ev.is_critical, failed: ev.action === 'FAILED' || (ev.http_status && ev.http_status >= 400) }"
              :style="{ '--d': (i * 30) + 'ms' }"
              @click="openEvent(ev.id)"
            >
              <div class="au-feed-time">
                {{ formatTime(ev.created_at) }}<br>
                <span class="au-feed-date">{{ formatDateShort(ev.created_at) }}</span>
              </div>
              <span class="au-feed-icn" :style="{ background: actionMeta(ev.action).bg, color: actionMeta(ev.action).color }">
                <svg v-if="ev.action === 'VIEW'"   width="11" height="11" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="2"><path d="M1 8s2.5-5 7-5 7 5 7 5-2.5 5-7 5-7-5-7-5z"/><circle cx="8" cy="8" r="2"/></svg>
                <svg v-else-if="ev.action === 'CREATE'" width="11" height="11" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M8 3v10M3 8h10"/></svg>
                <svg v-else-if="ev.action === 'UPDATE'" width="11" height="11" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M11 1l3 3-9 9H2v-3l9-9z"/></svg>
                <svg v-else-if="ev.action === 'DELETE'" width="11" height="11" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M3 4h10M6 4V2h4v2M5 4l1 10h4l1-10"/></svg>
                <svg v-else-if="ev.action === 'EXPORT'" width="11" height="11" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M8 1v10M3 7l5 5 5-5M2 14h12"/></svg>
                <svg v-else width="11" height="11" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M8 1l7 13H1L8 1z"/><path d="M8 6v3M8 11h.01"/></svg>
              </span>
              <div class="au-feed-info">
                <div class="au-feed-main">
                  <b>{{ ev.actor_email || "anonymous" }}</b>
                  ·
                  <span class="au-act-pill" :style="{ color: actionMeta(ev.action).color }">{{ actionMeta(ev.action).label }}</span>
                  <span v-if="ev.module" class="au-mod">{{ ev.module }}</span>
                </div>
                <div class="au-feed-sub">
                  <span v-if="ev.entity_label">{{ ev.entity_label }}</span>
                  <span v-else-if="ev.http_path" class="au-feed-path">{{ ev.http_method }} {{ ev.http_path }}</span>
                  <span v-if="ev.has_diff" class="au-feed-diff">· diff</span>
                </div>
              </div>
              <div class="au-feed-status">
                <span class="au-feed-dur">{{ ev.duration_ms != null ? ev.duration_ms + " ms" : "—" }}</span><br>
                <span class="au-feed-code" :class="{ ok: !ev.http_status || ev.http_status < 400, bad: ev.http_status && ev.http_status >= 400 }">
                  {{ ev.http_status ?? "—" }}
                </span>
              </div>
            </div>
          </div>
          <div class="au-feed-foot">
            <span v-if="extraLoading">Загрузка…</span>
            <span v-else-if="hasMore" @click="loadMoreEvents">
              Загрузить ещё ({{ fmt.fmtNumber(totalEvents - allFeedEvents.length) }} событий) →
            </span>
            <span v-else style="color: var(--t3, #888780);cursor:default">Показаны все события за период</span>
          </div>
        </div>

        <!-- Side panels -->
        <div class="au-side">

          <!-- Top users -->
          <div class="au-card" style="--d:380ms">
            <div class="au-card-hd">
              <span class="au-card-ttl">
                <svg width="12" height="12" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="2"><circle cx="8" cy="5" r="3"/><path d="M2 14c0-3 3-5 6-5s6 2 6 5"/></svg>
                Топ пользователи
              </span>
              <span class="au-card-meta">за {{ hours }}ч</span>
            </div>
            <div class="au-card-body">
              <div v-if="!overview.top_users.length" class="au-empty">Пусто</div>
              <div v-for="u in overview.top_users" :key="u.email" class="au-tu-row">
                <span class="au-tu-av" :style="{ background: u.accent + '22', color: u.accent }">{{ u.initials }}</span>
                <span class="au-tu-em">{{ u.email }}</span>
                <span class="au-tu-c">{{ fmt.fmtNumber(u.count) }}</span>
              </div>
              <div v-for="u in overview.top_users" :key="u.email + '-bar'" class="au-tu-bar-wrap">
                <div class="au-tu-bar" :style="{ width: (u.count / Math.max(1, overview.top_users[0].count) * 100) + '%', background: u.accent }"></div>
              </div>
            </div>
          </div>

          <!-- Top modules -->
          <div class="au-card" style="--d:440ms">
            <div class="au-card-hd">
              <span class="au-card-ttl">
                <svg width="12" height="12" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="2"><rect x="2" y="2" width="5" height="5"/><rect x="9" y="2" width="5" height="5"/><rect x="2" y="9" width="5" height="5"/><rect x="9" y="9" width="5" height="5"/></svg>
                Топ модули
              </span>
              <span class="au-card-meta">по запросам</span>
            </div>
            <div class="au-card-body">
              <div v-if="!overview.top_modules.length" class="au-empty">Пусто</div>
              <div class="au-tm-grid">
                <div v-for="m in overview.top_modules.slice(0, 6)" :key="m.module" class="au-tm-cell">
                  <div class="au-tm-l">{{ m.label }}</div>
                  <div class="au-tm-v">{{ fmt.fmtNumber(m.count) }}</div>
                </div>
              </div>
            </div>
          </div>

          <!-- Security flags -->
          <div class="au-card" style="--d:500ms">
            <div class="au-card-hd">
              <span class="au-card-ttl">
                <svg width="12" height="12" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="2"><path d="M8 1l6 3v4c0 4-3 7-6 7s-6-3-6-7V4l6-3z"/><path d="M8 6v3M8 10v.01"/></svg>
                Security flags
              </span>
              <span class="au-card-meta" :class="{ bad: overview.security_flags.length > 0 }">
                {{ overview.security_flags.length }} активных
              </span>
            </div>
            <div class="au-card-body">
              <div v-if="!overview.security_flags.length" class="au-empty au-empty-ok">
                <svg width="13" height="13" viewBox="0 0 14 14" fill="none" stroke="#0F6E56" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M3 7l3 3 5-6"/></svg>
                Угроз не обнаружено
              </div>
              <div v-for="f in overview.security_flags" :key="f.id" class="au-sf-row" :class="f.severity">
                <div class="au-sf-ttl">{{ f.title }}</div>
                <div class="au-sf-det">{{ f.detail }}</div>
              </div>
            </div>
          </div>

        </div>
      </div>

      <!-- ═══ Bottom: multi-line chart ═══ -->
      <div v-if="chartData" class="au-card" style="--d:560ms">
        <div class="au-card-hd">
          <span class="au-card-ttl">
            <svg width="12" height="12" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="2"><polyline points="1 12 5 8 9 10 15 4"/></svg>
            События по типам · {{ hours }} часов
          </span>
          <div class="au-chart-legend">
            <span><span class="dot" style="background:#378ADD"></span>VIEW</span>
            <span><span class="dot" style="background:#1D9E75"></span>UPDATE</span>
            <span><span class="dot" style="background:#7F77DD"></span>CREATE</span>
            <span><span class="dot" style="background:#D4537E"></span>DELETE</span>
            <span><span class="dot" style="background:#E24B4A"></span>ERROR</span>
          </div>
        </div>
        <div class="au-card-body" style="padding:6px 4px">
          <svg :viewBox="`0 0 ${chartData.W} ${chartData.H}`" style="width:100%;height:130px;display:block">
            <line :x1="chartData.padL" y1="10" :x2="chartData.padL" :y2="chartData.padT + chartData.innerH" stroke="#E2E8F0" stroke-width="0.5"/>
            <line :x1="chartData.padL" :y1="chartData.padT + chartData.innerH" :x2="chartData.W - 10" :y2="chartData.padT + chartData.innerH" stroke="#E2E8F0" stroke-width="0.5"/>
            <text :x="chartData.padL - 5" :y="chartData.padT + 4" text-anchor="end" font-size="9" fill="#888780">{{ chartData.maxVal }}</text>
            <text :x="chartData.padL - 5" :y="chartData.padT + chartData.innerH + 3" text-anchor="end" font-size="9" fill="#888780">0</text>
            <path :d="chartData.paths.view"   fill="none" stroke="#378ADD" stroke-width="1.5"/>
            <path :d="chartData.paths.update" fill="none" stroke="#1D9E75" stroke-width="1.5"/>
            <path :d="chartData.paths.create" fill="none" stroke="#7F77DD" stroke-width="1.5"/>
            <path :d="chartData.paths.delete" fill="none" stroke="#D4537E" stroke-width="1.5"/>
            <path :d="chartData.paths.error"  fill="none" stroke="#E24B4A" stroke-width="1.5"/>
            <template v-for="(l, i) in chartData.xLabels" :key="i">
              <text v-if="l.showLabel" :x="l.x" :y="chartData.padT + chartData.innerH + 12" text-anchor="middle" font-size="9" fill="#888780">{{ l.label }}</text>
            </template>
          </svg>
        </div>
      </div>
    </div>

    <!-- ═══ Drill modal ═══ -->
    <div v-if="drillEvent" class="au-modal-back" @click.self="closeDrill">
      <div class="au-modal">
        <div class="au-modal-hd">
          <div>
            <div class="au-modal-eyebrow">Событие · {{ drillEvent.action }}</div>
            <div class="au-modal-ttl">{{ drillEvent.entity_label || drillEvent.http_path }}</div>
          </div>
          <button class="au-close" @click="closeDrill">×</button>
        </div>
        <div class="au-modal-body">
          <div class="au-kv">
            <div class="au-kv-l">Кто</div>
            <div class="au-kv-v">{{ drillEvent.actor_email || "—" }} <span v-if="drillEvent.actor_role" class="role">{{ drillEvent.actor_role }}</span></div>

            <div class="au-kv-l">Когда</div>
            <div class="au-kv-v">{{ fmt.fmtDateTime(drillEvent.created_at) }}</div>

            <div class="au-kv-l">IP / UA</div>
            <div class="au-kv-v" style="font-size:11px">{{ drillEvent.ip_address || "—" }} · {{ drillEvent.user_agent || "—" }}</div>

            <div class="au-kv-l">HTTP</div>
            <div class="au-kv-v">{{ drillEvent.http_method }} {{ drillEvent.http_path }} → <b :class="drillEvent.http_status && drillEvent.http_status >= 400 ? 'bad' : 'ok'">{{ drillEvent.http_status }}</b> ({{ drillEvent.duration_ms }} ms)</div>

            <div class="au-kv-l">Модуль</div>
            <div class="au-kv-v">{{ drillEvent.module || "—" }} · {{ drillEvent.entity_type || "—" }} #{{ drillEvent.entity_id || "—" }}</div>

            <div class="au-kv-l">HMAC</div>
            <div class="au-kv-v" style="font-size:10.5px;color: var(--t3, #888780);font-family:monospace">prev: {{ (drillEvent.prev_hash || "—").slice(0, 16) }}…<br>this: {{ (drillEvent.entry_hash || "—").slice(0, 16) }}…</div>
          </div>
          <div v-if="drillEvent.diff" class="au-jsbox">
            <div class="au-jsbox-l">Diff</div>
            <pre>{{ JSON.stringify(drillEvent.diff, null, 2) }}</pre>
          </div>
          <div v-if="drillEvent.payload" class="au-jsbox">
            <div class="au-jsbox-l">Payload</div>
            <pre>{{ JSON.stringify(drillEvent.payload, null, 2) }}</pre>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.au-view { background: #F4F3F9; min-height: 100%; font-family: var(--font, system-ui); }

@keyframes auCardIn {
  0% { opacity: 0; transform: translateY(8px); }
  100% { opacity: 1; transform: translateY(0); }
}
@keyframes auShimmer { 0% { left: -60%; } 100% { left: 160%; } }
@keyframes auLivePulse { 0%, 100% { opacity: 1; } 50% { opacity: .3; } }

/* Topbar */
.au-topbar {
  background: linear-gradient(95deg, #1E2A4A 0%, #2D3760 60%, #4B477E 100%);
  padding: 14px 22px; display: flex; align-items: center; justify-content: space-between;
  gap: 18px; flex-wrap: wrap;
}
.au-tb-l { display: flex; flex-direction: column; gap: 3px; }
.au-tb-eyebrow {
  font-size: 10px; font-weight: 500; color: rgba(255,255,255,.55);
  letter-spacing: .08em; text-transform: uppercase;
  display: flex; align-items: center; gap: 6px;
}
.au-tb-title { font-size: 17px; color: #fff; font-weight: 500; letter-spacing: -.005em; }
.au-tb-sub { font-size: 11px; color: rgba(255,255,255,.65); }
.au-tb-sub b { color: #fff; font-weight: 500; }
.au-live { margin-left: 8px; color: var(--green); }
.au-live-dot {
  display: inline-block; width: 6px; height: 6px; border-radius: 50%;
  background: var(--green); margin-right: 3px;
  animation: auLivePulse 1.5s ease-in-out infinite;
}
.au-tb-r { display: flex; gap: 8px; align-items: center; }
.au-in {
  background: rgba(255,255,255,.12); border: 1px solid rgba(255,255,255,.15);
  color: #fff; padding: 5px 10px; border-radius: 8px;
  font-size: 12px; font-family: inherit; cursor: pointer; outline: none;
}
.au-in option { background: #1E2A4A; color: #fff; }
.au-btn {
  border: 0; padding: 6px 12px; border-radius: 8px;
  font-size: 12px; font-family: inherit; font-weight: 500; cursor: pointer;
  display: flex; align-items: center; gap: 6px;
  transition: all .15s;
}
.au-btn-ghost { background: rgba(255,255,255,.12); border: 1px solid rgba(255,255,255,.15); color: #fff; }
.au-btn-ghost:hover { background: rgba(255,255,255,.18); }
.au-btn-primary { background: rgba(127,119,221,.4); border: 1px solid rgba(127,119,221,.6); color: #fff; }
.au-btn-primary:hover { background: rgba(127,119,221,.55); }

/* Filter bar */
.au-emb-summary {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 10px 18px;
  background: linear-gradient(90deg, rgba(127,119,221,.04), rgba(127,119,221,.08));
  border-bottom: 0.5px solid rgba(0,0,0,.06);
  flex-wrap: wrap;
  gap: 10px;
}
.au-emb-stat {
  font-size: 12px;
  color: var(--color-text-secondary, #5F5E5A);
  display: flex;
  align-items: center;
  gap: 10px;
}
.au-emb-stat b {
  color: var(--color-text-primary, #1E2A4A);
  font-weight: 500;
  font-feature-settings: "tnum";
}
.au-emb-live {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  background: rgba(29,158,117,.1);
  color: #0F6E56;
  padding: 2px 8px;
  border-radius: 9px;
  font-size: 10px;
  font-weight: 500;
  letter-spacing: .04em;
  text-transform: uppercase;
}
.au-emb-controls {
  display: flex;
  gap: 6px;
  align-items: center;
}
.au-emb-select {
  border: 0.5px solid rgba(0,0,0,.12);
  background: var(--bg1, #fff);
  padding: 4px 9px;
  border-radius: 6px;
  font-size: 11px;
  font-family: inherit;
  color: var(--t1, #1E2A4A);
  outline: none;
}
.au-emb-btn {
  background: transparent;
  border: 0.5px solid rgba(0,0,0,.12);
  color: var(--t3, #5F5E5A);
  padding: 4px 10px;
  border-radius: 6px;
  font-size: 11px;
  font-family: inherit;
  cursor: pointer;
  display: inline-flex;
  align-items: center;
  gap: 4px;
}
.au-emb-btn:hover {
  background: rgba(127,119,221,.06);
  color: var(--p-deep);
}

.au-filterbar {
  padding: 12px 22px 4px; background: var(--bg2, #FAFAFC);
  border-bottom: 0.5px solid rgba(0,0,0,.05);
  display: flex; gap: 8px; align-items: center; flex-wrap: wrap;
}
.au-search {
  display: flex; align-items: center; gap: 6px;
  background: var(--bg1, #fff); border: 1px solid rgba(0,0,0,.08);
  border-radius: 8px; padding: 5px 10px; flex: 1; min-width: 220px;
}
.au-search input {
  border: 0; background: transparent; flex: 1;
  font-size: 12px; outline: none; color: var(--t1, #1E2A4A); font-family: inherit;
}
.au-kbd {
  font-size: 10px; color: var(--t3, var(--t-muted)); background: #F4F3F9;
  padding: 2px 6px; border-radius: 4px;
}
.au-fl {
  border: 1px solid rgba(0,0,0,.08); background: var(--bg1, #fff);
  padding: 5px 10px; border-radius: 8px;
  font-size: 12px; font-family: inherit; color: var(--t1, #1E2A4A);
  max-width: 180px;
}
.au-clear {
  background: rgba(127,119,221,.08); border: 0;
  color: var(--p-deep); font-size: 11px; padding: 5px 10px;
  border-radius: 7px; cursor: pointer; font-weight: 500;
}

.au-error { padding: 16px 22px; color: var(--sev-critical); font-size: 12px; }

.au-body { padding: 14px 22px 24px; }

/* KPI strip */
.au-kpi-strip {
  display: grid; grid-template-columns: repeat(6, 1fr); gap: 10px;
  margin-bottom: 12px;
}
.au-kpi {
  background: var(--bg1, #fff); border: 1px solid rgba(0,0,0,.05);
  border-radius: 10px; padding: 12px 14px;
  position: relative; overflow: hidden;
  animation: auCardIn .5s var(--ease-standard) var(--d, 0ms) both;
}
.au-kpi::before {
  content: ""; position: absolute; top: 0; left: 0; right: 0;
  height: 2px; background: var(--ac);
}
.au-kpi.fin-shimmer::after {
  content: ""; position: absolute; top: 0; left: -60%;
  width: 60%; height: 100%;
  background: linear-gradient(90deg, transparent, rgba(127,119,221,.06), transparent);
  animation: auShimmer 1.1s ease-out calc(var(--d, 0ms) + 200ms) forwards;
  pointer-events: none;
}
.au-kpi-lbl {
  font-size: 9.5px; color: var(--t3, var(--t-muted));
  text-transform: uppercase; letter-spacing: .06em; font-weight: 500;
}
.au-kpi-v {
  font-size: 22px; font-weight: 400; color: var(--ac);
  letter-spacing: -.025em; margin-top: 4px;
  font-feature-settings: "tnum";
}
.au-kpi-sub {
  font-size: 10px; color: var(--t3, var(--t-muted)); margin-top: 3px;
  display: flex; align-items: center; gap: 4px;
}
.au-delta { font-weight: 500; }
.au-delta.up { color: var(--green); }
.au-delta.down { color: var(--sev-high); }

/* Mid grid */
.au-mid-grid {
  display: grid; grid-template-columns: 1.5fr 1fr; gap: 12px;
  margin-bottom: 12px;
}
.au-side {
  display: flex; flex-direction: column; gap: 12px;
}

/* Card baseline */
.au-card {
  background: var(--bg1, #fff); border: 1px solid rgba(0,0,0,.05);
  border-radius: 12px; overflow: hidden;
  animation: auCardIn .5s var(--ease-standard) var(--d, 0ms) both;
}
.au-card-hd {
  padding: 12px 16px; border-bottom: 0.5px solid rgba(0,0,0,.06);
  display: flex; justify-content: space-between; align-items: center; gap: 8px;
}
.au-card-ttl {
  font-size: 11px; font-weight: 500; color: var(--t3, var(--t-muted));
  text-transform: uppercase; letter-spacing: .07em;
  display: flex; align-items: center; gap: 6px;
}
.au-card-ttl svg { color: var(--t3, var(--t-muted)); }
.au-card-meta { font-size: 10.5px; color: var(--t3, var(--t-muted)); }
.au-card-meta.bad { color: var(--sev-critical); font-weight: 500; }
.au-card-body { padding: 12px 16px; }

.au-empty { padding: 20px; text-align: center; color: var(--t3, var(--t-muted)); font-size: 11px; font-style: italic; }
.au-empty-ok {
  color: #0F6E56; font-style: normal;
  display: flex; align-items: center; justify-content: center; gap: 6px;
}

/* Feed */
.au-feed-body { max-height: 540px; overflow-y: auto; }
.au-feed-row {
  display: grid; grid-template-columns: 70px 30px 1fr 65px;
  gap: 10px; align-items: center;
  padding: 9px 16px;
  border-bottom: 0.5px solid rgba(0,0,0,.04);
  cursor: pointer;
  animation: auCardIn .25s ease var(--d, 0ms) both;
  transition: background .15s;
}
.au-feed-row:hover { background: rgba(127,119,221,.04); }
.au-feed-row.failed { background: rgba(226,75,74,.03); }
.au-feed-row.critical { background: rgba(212,83,126,.04); }

.au-feed-time {
  font-size: 10.5px; color: var(--t3, var(--t-muted));
  font-feature-settings: "tnum"; line-height: 1.3;
}
.au-feed-date { font-size: 9.5px; }

.au-feed-icn {
  width: 22px; height: 22px; border-radius: 5px;
  display: flex; align-items: center; justify-content: center;
  flex-shrink: 0;
}

.au-feed-info { min-width: 0; }
.au-feed-main {
  font-size: 12px; color: var(--t1, #1E2A4A);
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}
.au-feed-main b { font-weight: 500; }
.au-act-pill { font-weight: 500; font-size: 11px; }
.au-mod {
  font-size: 10px; color: var(--t3, var(--t-muted)); margin-left: 4px;
  background: rgba(127,119,221,.08); padding: 1px 6px; border-radius: 4px;
}
.au-feed-sub {
  font-size: 10.5px; color: var(--t3, var(--t-muted)); margin-top: 1px;
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}
.au-feed-path { font-family: monospace; }
.au-feed-diff { color: var(--p-deep); margin-left: 4px; }
.au-feed-status {
  text-align: right; font-size: 10.5px; color: var(--t3, var(--t-muted));
  font-feature-settings: "tnum";
}
.au-feed-code { font-size: 9.5px; }
.au-feed-code.ok { color: var(--green); }
.au-feed-code.bad { color: var(--sev-critical); font-weight: 500; }

.au-feed-foot {
  padding: 10px 16px; text-align: center;
  border-top: 0.5px solid rgba(0,0,0,.06);
  background: var(--bg2, #FAFAFC);
}
.au-feed-foot span {
  font-size: 11px; color: var(--p-deep); cursor: pointer;
}
.au-feed-foot span:hover { text-decoration: underline; }

/* Top users */
.au-tu-row {
  display: flex; align-items: center; gap: 9px;
  margin-bottom: 4px;
}
.au-tu-av {
  width: 24px; height: 24px; border-radius: 50%;
  display: flex; align-items: center; justify-content: center;
  font-size: 10px; font-weight: 500; flex-shrink: 0;
}
.au-tu-em {
  flex: 1; font-size: 11.5px; color: var(--t1, #1E2A4A); font-weight: 500;
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}
.au-tu-c {
  font-size: 11.5px; color: var(--t1, #1E2A4A);
  font-feature-settings: "tnum"; font-weight: 500;
}
.au-tu-bar-wrap {
  height: 3px; background: #F4F3F9;
  border-radius: 2px; overflow: hidden; margin-bottom: 7px;
}
.au-tu-bar { height: 100%; border-radius: 2px; transition: width .8s ease; }

/* Top modules grid */
.au-tm-grid {
  display: grid; grid-template-columns: 1fr 1fr; gap: 6px;
}
.au-tm-cell {
  padding: 7px 9px; background: var(--bg2, #FAFAFC); border-radius: 6px;
}
.au-tm-l { font-size: 10px; color: var(--t3, var(--t-muted)); margin-bottom: 2px; }
.au-tm-v {
  font-size: 15px; color: var(--t1, #1E2A4A); font-weight: 500;
  font-feature-settings: "tnum";
}

/* Security flags */
.au-sf-row {
  padding: 8px 10px; border-radius: 6px; margin-bottom: 5px;
  background: #FFFBEB;
  position: relative; overflow: hidden;
  --au-accent: var(--amber);
}
.au-sf-row::before {
  content: ""; position: absolute; top: 0; left: 0; right: 0;
  height: 2px; background: var(--au-accent);
  animation: uzaStripeDrawIn .4s var(--ease-standard) both;
  transform-origin: left center;
  pointer-events: none;
}
.au-sf-row.critical { background: #FEF2F2; --au-accent: var(--sev-high); }
.au-sf-row.info { background: rgba(55,138,221,.06); --au-accent: var(--blue); }
.au-sf-ttl { font-size: 11.5px; color: var(--t1, #1E2A4A); font-weight: 500; }
.au-sf-det { font-size: 10.5px; color: var(--t3, #5F5E5A); margin-top: 1px; }

/* Chart */
.au-chart-legend {
  display: flex; gap: 12px; font-size: 10.5px;
}
.au-chart-legend span { display: flex; align-items: center; gap: 4px; color: var(--t3, #5F5E5A); }
.au-chart-legend .dot {
  display: inline-block; width: 8px; height: 8px; border-radius: 50%;
}

/* Drill modal */
.au-modal-back {
  position: fixed; inset: 0; background: rgba(15,18,40,.45);
  -webkit-backdrop-filter: blur(8px);
  backdrop-filter: blur(8px); z-index: 1000;
  display: flex; align-items: center; justify-content: center;
  padding: 20px;
}
.au-modal {
  background: var(--bg1, #fff); border-radius: 14px;
  width: 100%; max-width: 720px; max-height: 90vh;
  overflow: auto;
  box-shadow: 0 24px 64px rgba(15,23,60,.18);
}
.au-modal-hd {
  padding: 16px 22px; border-bottom: 0.5px solid rgba(0,0,0,.08);
  display: flex; justify-content: space-between; align-items: center;
}
.au-modal-eyebrow {
  font-size: 10px; color: var(--t3, var(--t-muted)); text-transform: uppercase;
  letter-spacing: .07em; font-weight: 500;
}
.au-modal-ttl { font-size: 15px; color: var(--t1, #1E2A4A); font-weight: 500; margin-top: 2px; }
.au-close {
  background: transparent; border: 0; font-size: 22px;
  color: var(--t3, var(--t-muted)); cursor: pointer; line-height: 1;
}
.au-modal-body { padding: 16px 22px 22px; }
.au-kv {
  display: grid; grid-template-columns: 100px 1fr; gap: 8px 14px;
  font-size: 12px; margin-bottom: 16px;
}
.au-kv-l { color: var(--t3, var(--t-muted)); font-weight: 500; }
.au-kv-v { color: var(--t1, #1E2A4A); }
.au-kv-v b.ok { color: var(--green); }
.au-kv-v b.bad { color: var(--sev-critical); }
.au-kv-v .role {
  margin-left: 6px; font-size: 10px;
  background: rgba(127,119,221,.1); color: var(--p-deep);
  padding: 2px 6px; border-radius: 4px;
}
.au-jsbox {
  background: var(--bg2, #FAFAFC); border: 0.5px solid rgba(0,0,0,.05);
  border-radius: 8px; padding: 10px 12px; margin-bottom: 10px;
}
.au-jsbox-l {
  font-size: 10px; color: var(--t3, var(--t-muted)); text-transform: uppercase;
  letter-spacing: .07em; font-weight: 500; margin-bottom: 6px;
}
.au-jsbox pre {
  margin: 0; font-family: monospace; font-size: 11px;
  color: var(--t1, #1E2A4A); overflow-x: auto; line-height: 1.5;
  max-height: 240px;
}

@media (max-width: 1300px) {
  .au-kpi-strip { grid-template-columns: repeat(3, 1fr); }
  .au-mid-grid { grid-template-columns: 1fr; }
}
@media (max-width: 700px) {
  .au-kpi-strip { grid-template-columns: 1fr 1fr; }
  .au-body { padding: 12px; }
}
</style>
