<script setup lang="ts">
/**
 * Журнал аудита — переработка (2026-06): главный экран «по пользователям»,
 * статистика с графиками/таблицами, режимы (Люди / Лента / Модули), модалки.
 * Backend: /admin/audit/{overview,by-user,events,events/:id,export.csv,purge}.
 */
import { ref, computed, onMounted, watch } from "vue";
import {
  auditApi as auditFeedApi,
  type AuditUserRow,
  type AuditOverviewResponse,
  type AuditEventRead,
  type AuditEventDetail,
} from "@/api/audit";
import { auditApi as rbacAuditApi } from "@/api/rbacV3";
import AuditChart from "@/components/audit/AuditChart.vue";
import { useFormatters } from "@/composables/useFormatters";
import { useAuthStore } from "@/stores/auth";
import type { ChartConfiguration } from "@/utils/chartjsRegister";

const fmt = useFormatters();
const auth = useAuthStore();
const isOwner = computed(() => auth.isOwner);

// ─── State ──────────────────────────────────────────────────────
type Mode = "users" | "feed" | "modules";
const mode = ref<Mode>("users");
type Period = "today" | "24h" | "7d" | "30d" | "all";
const period = ref<Period>("today");
const PERIODS: { v: Period; l: string }[] = [
  { v: "today", l: "Сегодня" }, { v: "24h", l: "24 часа" },
  { v: "7d", l: "7 дней" }, { v: "30d", l: "30 дней" }, { v: "all", l: "Всё время" },
];
const search = ref("");
const loading = ref(true);
const error = ref<string | null>(null);

const overview = ref<AuditOverviewResponse | null>(null);
const users = ref<AuditUserRow[]>([]);
const feed = ref<AuditEventRead[]>([]);
const feedTotal = ref(0);

const ACCENTS = ["#7C6FF7", "#1D9E75", "#0891B2", "#534AB7", "#5B7CFA", "#0F6E56", "#9A6FD4", "#D97706"];

function todayStart(): Date {
  const d = new Date();
  d.setHours(0, 0, 0, 0);
  return d;
}
function sinceIso(): string | undefined {
  const now = Date.now();
  if (period.value === "today") return todayStart().toISOString();
  if (period.value === "24h") return new Date(now - 24 * 3600e3).toISOString();
  if (period.value === "7d") return new Date(now - 168 * 3600e3).toISOString();
  if (period.value === "30d") return new Date(now - 720 * 3600e3).toISOString();
  return undefined; // all
}
function statsHours(): number {
  if (period.value === "today") return Math.max(1, Math.ceil((Date.now() - todayStart().getTime()) / 3600e3));
  if (period.value === "24h") return 24;
  if (period.value === "7d") return 168;
  if (period.value === "30d") return 720;
  return 720; // all → графики ограничиваем 30 днями
}

// ─── Load ───────────────────────────────────────────────────────
let searchTimer: ReturnType<typeof setTimeout> | null = null;
function onSearch() {
  if (searchTimer) clearTimeout(searchTimer);
  searchTimer = setTimeout(load, 300);
}

async function load() {
  loading.value = true;
  error.value = null;
  try {
    const [ov, us] = await Promise.all([
      auditFeedApi.overview(statsHours()),
      auditFeedApi.byUser({ since: sinceIso(), search: search.value || undefined }),
    ]);
    overview.value = ov;
    users.value = us;
    animateKpis();
    if (mode.value === "feed") await loadFeed();
  } catch (e: any) {
    error.value = e?.response?.data?.detail || "Не удалось загрузить журнал";
  } finally {
    loading.value = false;
  }
}

async function loadFeed() {
  const r = await auditFeedApi.listEvents({
    hours: statsHours(),
    search: search.value || undefined,
    per_page: 100,
  });
  feed.value = r.items;
  feedTotal.value = r.total;
}

watch(mode, async (m) => { if (m === "feed" && !feed.value.length) await loadFeed(); });
watch(period, load);
onMounted(load);

// ─── KPI count-up animation ─────────────────────────────────────
const kpi = ref<Record<string, number>>({ total: 0, users: 0, online: 0, changes: 0, views: 0, errors: 0 });
function animateKpis() {
  const s = overview.value?.stats;
  if (!s) return;
  const targets: Record<string, number> = {
    total: s.events_total, users: s.unique_users, online: s.online_users,
    changes: s.changes, views: s.views, errors: s.errors,
  };
  for (const k of Object.keys(targets)) tween(k, targets[k]);
}
function tween(key: string, target: number) {
  const from = kpi.value[key] || 0;
  const start = performance.now();
  const dur = 650;
  function step(t: number) {
    const p = Math.min(1, (t - start) / dur);
    const eased = 1 - Math.pow(1 - p, 3);
    kpi.value = { ...kpi.value, [key]: Math.round(from + (target - from) * eased) };
    if (p < 1) requestAnimationFrame(step);
  }
  requestAnimationFrame(step);
}
const KPIS = computed(() => [
  { key: "total", label: "Всего действий", accent: "#7C6FF7" },
  { key: "users", label: "Активных людей", accent: "#1D9E75" },
  { key: "online", label: "Сейчас онлайн", accent: "#0891B2" },
  { key: "changes", label: "Изменений", accent: "#534AB7" },
  { key: "views", label: "Просмотров", accent: "#5B7CFA" },
  { key: "errors", label: "Ошибок/отказов", accent: "#EF4444" },
]);

// ─── Charts ─────────────────────────────────────────────────────
const typeTotals = computed(() => {
  const t = { changes: 0, views: 0, logins: 0, deletions: 0, errors: 0 };
  for (const u of users.value) {
    t.changes += u.changes; t.views += u.views; t.logins += u.logins;
    t.deletions += u.deletions; t.errors += u.errors;
  }
  return t;
});
const donutConfig = computed<ChartConfiguration>(() => ({
  type: "doughnut",
  data: {
    labels: ["Изменения", "Просмотры", "Входы", "Удаления", "Ошибки"],
    datasets: [{
      data: [typeTotals.value.changes, typeTotals.value.views, typeTotals.value.logins, typeTotals.value.deletions, typeTotals.value.errors],
      backgroundColor: ["#7C6FF7", "#0891B2", "#1D9E75", "#EF4444", "#94A3B8"],
      borderWidth: 0, hoverOffset: 6,
    }],
  },
  options: {
    responsive: true, maintainAspectRatio: false, cutout: "62%",
    plugins: { legend: { position: "right", labels: { boxWidth: 10, font: { size: 11 } } } },
    animation: { animateRotate: true, duration: 800 },
  },
}));
const timelineConfig = computed<ChartConfiguration>(() => {
  const b = overview.value?.timeline.buckets || [];
  const labels = b.map((x) => fmt.fmtTime ? shortTs(x.ts) : x.ts);
  return {
    type: "line",
    data: {
      labels,
      datasets: [
        { label: "Изменения", data: b.map((x) => x.create + x.update + x.delete), borderColor: "#7C6FF7", backgroundColor: "rgba(124,111,247,.13)", fill: true, tension: 0.35, pointRadius: 0, borderWidth: 2 },
        { label: "Просмотры", data: b.map((x) => x.view), borderColor: "#0891B2", backgroundColor: "rgba(8,145,178,.10)", fill: true, tension: 0.35, pointRadius: 0, borderWidth: 2 },
      ],
    },
    options: {
      responsive: true, maintainAspectRatio: false,
      plugins: { legend: { position: "top", labels: { boxWidth: 10, font: { size: 11 } } } },
      scales: { x: { grid: { display: false }, ticks: { maxTicksLimit: 8, font: { size: 10 } } }, y: { beginAtZero: true, ticks: { font: { size: 10 } }, grid: { color: "rgba(0,0,0,.05)" } } },
      animation: { duration: 700 },
    },
  };
});
const modulesConfig = computed<ChartConfiguration>(() => {
  const m = overview.value?.top_modules || [];
  return {
    type: "bar",
    data: {
      labels: m.map((x) => x.label),
      datasets: [{ data: m.map((x) => x.count), backgroundColor: m.map((_, i) => ACCENTS[i % ACCENTS.length]), borderRadius: 6, maxBarThickness: 26 }],
    },
    options: {
      responsive: true, maintainAspectRatio: false, indexAxis: "y",
      plugins: { legend: { display: false } },
      scales: { x: { beginAtZero: true, ticks: { font: { size: 10 } }, grid: { color: "rgba(0,0,0,.05)" } }, y: { grid: { display: false }, ticks: { font: { size: 11 } } } },
      animation: { duration: 700 },
    },
  };
});
function shortTs(ts: string): string {
  const d = new Date(ts);
  return overview.value?.timeline.bucket === "day"
    ? d.toLocaleDateString("ru", { day: "2-digit", month: "2-digit" })
    : d.toLocaleTimeString("ru", { hour: "2-digit", minute: "2-digit" });
}

// ─── Helpers (читаемые описания) ────────────────────────────────
function fmtRelative(s: string | null): string {
  if (!s) return "";
  const diff = (Date.now() - new Date(s).getTime()) / 1000;
  if (diff < 60) return "только что";
  if (diff < 3600) return Math.floor(diff / 60) + " мин назад";
  if (diff < 86400) return Math.floor(diff / 3600) + " ч назад";
  const days = Math.floor(diff / 86400);
  if (days === 1) return "вчера";
  if (days < 30) return days + " дн назад";
  return Math.floor(days / 30) + " мес назад";
}
const MODULE_LABELS: Record<string, string> = {
  rbac: "Доступы", users: "Пользователи", roles: "Роли", groups: "Группы",
  kpi: "KPI", bp: "Бизнес-план", business_plan: "Бизнес-план", credit: "Кредитный портфель",
  finance: "Финансы", financials: "Финансы", invest: "Инвест-проекты", investment: "Инвест-проекты",
  procurement: "Закупки", esg: "ESG", governance: "Корп. управление", ratings: "Рейтинги",
  companies: "Компании", tasks: "Задачи", auth: "Вход и сессии", admin: "Администрирование",
  moderation: "Модерация", notification: "Уведомления",
};
const PATH_SECTION: Record<string, string> = {
  "rbac-v3": "Доступы", rbac: "Доступы", users: "Пользователи", roles: "Роли", groups: "Группы",
  audit: "Журнал аудита", companies: "Компании", company: "Компании", kpi: "KPI", bp: "Бизнес-план",
  financials: "Финансы", credit: "Кредитный портфель", procurement: "Закупки", esg: "ESG",
  governance: "Корп. управление", ratings: "Рейтинги", tasks: "Задачи", projects: "Проекты",
  admin: "Администрирование", dashboard: "Дашборд", "invest-projects": "Инвест-проекты",
  consultants: "Консультанты", auth: "Вход и сессии", export: "Экспорт",
};
function moduleLabel(m: string | null): string { return m ? (MODULE_LABELS[m] || m) : ""; }
function prettyPath(path: string | null): string {
  if (!path) return "";
  const segs = path.split("?")[0].split("/").filter((s) => s && s !== "api" && s !== "v1");
  for (const s of segs) if (PATH_SECTION[s]) return PATH_SECTION[s];
  return segs.find((s) => !/^[0-9a-f-]{8,}$/i.test(s) && !/^\d+$/.test(s)) || "";
}
function whereText(e: any): string {
  const mod = moduleLabel(e.module) || prettyPath(e.http_path);
  return mod || "";
}
function severity(e: any): { color: string; ru: string } {
  if (e.is_critical || /delete|delete_permanent|revoke|deactivate/i.test(e.action)) return { color: "#EF4444", ru: "Важное" };
  if (/update|change|grant|assign|create|import|approve|reject|login/i.test(e.action)) return { color: "#7C6FF7", ru: "Изменение" };
  return { color: "#94A3B8", ru: "Просмотр" };
}
function describe(e: any): string {
  const a = e.action as string;
  const entity = e.entity_label || e.entity_type || "";
  const mod = e.module || "";
  const map: Record<string, string> = {
    "user.create": `пригласил(а) пользователя ${entity}`, "user.invite": `пригласил(а) пользователя ${entity}`,
    "user.delete_permanent": `удалил(а) пользователя навсегда: ${entity}`, "user.deactivate": `деактивировал(а) ${entity}`,
    "user.activate": `активировал(а) ${entity}`, "user.update": `изменил(а) данные пользователя ${entity}`,
    "user.password_reset": `сбросил(а) пароль ${entity}`, "user.unlock": `разблокировал(а) ${entity}`,
    "user.assign_role": `назначил(а) роль «${entity}»`, "role.assign": `назначил(а) роль «${entity}»`,
    "user.remove_role": `убрал(а) роль «${entity}»`, "user.assign_group": `добавил(а) в группу «${entity}»`,
    "user.remove_group": `убрал(а) из группы «${entity}»`,
    "role.create": `создал(а) роль «${entity}»`, "role.delete": `удалил(а) роль «${entity}»`,
    "role.update": `изменил(а) роль «${entity}»`, "role.update_permissions": `изменил(а) разрешения роли «${entity}»`,
    "group.create": `создал(а) группу «${entity}»`, "group.delete": `удалил(а) группу «${entity}»`,
    "group.update_permissions": `изменил(а) разрешения группы «${entity}»`,
    "permission.grant": `выдал(а) разрешение «${entity}»`, "permission.revoke": `отозвал(а) разрешение «${entity}»`,
    "auth.login.success": "успешный вход", "login.success": "успешный вход",
    "auth.login.failed": "неудачная попытка входа", "login.failed": "неудачная попытка входа",
    "logout": "вышел(а) из системы", "auth.logout": "вышел(а) из системы",
    "mfa.enabled": "включил(а) MFA", "mfa.disabled": "отключил(а) MFA",
    "session.idle_timeout": "сессия завершена по простою", "session.absolute_timeout": "сессия завершена (срок)",
    "session.revoked_self": "завершил(а) сессию", "session.revoked_others": "завершил(а) другие сессии",
    "oneid.login.success": "вход через One ID",
    "company.create": `создал(а) компанию «${entity}»`, "company.update": `изменил(а) компанию «${entity}»`,
    "company.delete": `удалил(а) компанию «${entity}»`, "kpi.import": `импортировал(а) KPI «${entity}»`,
    "bp.import": `импортировал(а) Бизнес-план «${entity}»`, "financials.import": `импортировал(а) фин. отчёт «${entity}»`,
    "comment.created": entity ? `комментарий в «${entity}»` : "оставил(а) комментарий",
    "status_update.created": entity ? `обновил(а) ход «${entity}»` : "обновил(а) ход",
    "broadcast.send": `отправил(а) рассылку «${entity}»`,
  };
  if (map[a]) return map[a];
  const GEN: Record<string, string> = { VIEW: "открыл(а)", CREATE: "создал(а) запись", UPDATE: "изменил(а)", DELETE: "удалил(а) запись", FAILED: "отказ доступа", ERROR: "ошибка" };
  if (GEN[a]) {
    if (a === "VIEW") return entity ? `открыл(а): «${entity}»` : `просмотрел(а) раздел`;
    if (entity) return `${a === "CREATE" ? "создал(а)" : a === "DELETE" ? "удалил(а)" : "изменил(а)"}: «${entity}»`;
    return GEN[a];
  }
  return `${a}${entity ? ": " + entity : ""}${mod ? " [" + moduleLabel(mod) + "]" : ""}`;
}

// ─── Сортировка пользователей ───────────────────────────────────
const sortedUsers = computed(() => [...users.value].sort((a, b) => b.total - a.total));

// ─── User modal ─────────────────────────────────────────────────
const selUser = ref<AuditUserRow | null>(null);
const userEvents = ref<AuditEventRead[]>([]);
const userLoading = ref(false);
async function openUser(u: AuditUserRow) {
  selUser.value = u;
  userEvents.value = [];
  userLoading.value = true;
  try {
    const r = await auditFeedApi.listEvents({ actor_email: u.email, hours: statsHours(), per_page: 60 });
    userEvents.value = r.items;
  } finally {
    userLoading.value = false;
  }
}
function closeUser() { selUser.value = null; }
function userBars(u: AuditUserRow) {
  const max = Math.max(1, u.changes, u.views, u.logins, u.deletions);
  return [
    { label: "Изменения", v: u.changes, pct: (u.changes / max) * 100, c: "#7C6FF7" },
    { label: "Просмотры", v: u.views, pct: (u.views / max) * 100, c: "#0891B2" },
    { label: "Входы", v: u.logins, pct: (u.logins / max) * 100, c: "#1D9E75" },
    { label: "Удаления", v: u.deletions, pct: (u.deletions / max) * 100, c: "#EF4444" },
  ];
}

// ─── Event detail modal ─────────────────────────────────────────
const selEvent = ref<AuditEventDetail | null>(null);
const eventLoading = ref(false);
async function openEvent(e: AuditEventRead) {
  eventLoading.value = true;
  selEvent.value = null;
  try { selEvent.value = await auditFeedApi.eventDetail(e.id); }
  finally { eventLoading.value = false; }
}
function closeEvent() { selEvent.value = null; }

// ─── Модули (mode) ──────────────────────────────────────────────
const moduleRows = computed(() => {
  const m = overview.value?.top_modules || [];
  const max = Math.max(1, ...m.map((x) => x.count));
  return m.map((x, i) => ({ ...x, pct: (x.count / max) * 100, accent: ACCENTS[i % ACCENTS.length] }));
});

// ─── Очистка (owner) ────────────────────────────────────────────
const purgeOpen = ref(false);
const purgeKeep = ref<number | null>(90);
const purging = ref(false);
const PURGE_OPTS: { v: number | null; l: string }[] = [
  { v: 180, l: "Старше 180 дней" }, { v: 90, l: "Старше 90 дней" },
  { v: 30, l: "Старше 30 дней" }, { v: null, l: "Удалить весь журнал" },
];
async function doPurge() {
  purging.value = true;
  try { await rbacAuditApi.purge(purgeKeep.value); purgeOpen.value = false; await load(); }
  catch (e: any) { error.value = e?.response?.data?.detail || "Не удалось очистить"; }
  finally { purging.value = false; }
}
function exportCsv() { window.open(auditFeedApi.exportCsvUrl(statsHours()), "_blank"); }
</script>

<template>
  <div class="aud">
    <!-- Header -->
    <div class="aud-head">
      <div class="aud-head-l">
        <div class="aud-eyebrow">Безопасность · аудит</div>
        <h1 class="aud-title">Журнал действий</h1>
        <div class="aud-sub">Кто, что и когда делал в системе</div>
      </div>
      <div class="aud-head-r">
        <input v-model="search" class="aud-search" placeholder="Поиск по человеку / разделу…" @input="onSearch" />
        <button class="aud-btn" @click="exportCsv">Экспорт CSV</button>
        <button v-if="isOwner" class="aud-btn aud-btn-danger" @click="purgeOpen = true">Очистить</button>
      </div>
    </div>

    <!-- Period chips + mode -->
    <div class="aud-controls">
      <div class="aud-chips">
        <button v-for="p in PERIODS" :key="p.v" class="aud-chip" :class="{ on: period === p.v }" @click="period = p.v">{{ p.l }}</button>
      </div>
      <div class="aud-modes">
        <button class="aud-mode" :class="{ on: mode === 'users' }" @click="mode = 'users'">По людям</button>
        <button class="aud-mode" :class="{ on: mode === 'feed' }" @click="mode = 'feed'">Лента</button>
        <button class="aud-mode" :class="{ on: mode === 'modules' }" @click="mode = 'modules'">По разделам</button>
      </div>
    </div>

    <div v-if="error" class="aud-error">{{ error }}</div>

    <!-- Stats band -->
    <div class="aud-kpis">
      <div v-for="(k, i) in KPIS" :key="k.key" class="aud-kpi" :style="{ '--d': i * 60 + 'ms', '--acc': k.accent }">
        <div class="aud-kpi-val">{{ (kpi[k.key] || 0).toLocaleString('ru') }}</div>
        <div class="aud-kpi-lbl">{{ k.label }}</div>
      </div>
    </div>

    <div class="aud-charts">
      <div class="aud-card aud-chart-card">
        <div class="aud-card-t">Типы действий</div>
        <AuditChart v-if="overview" :config="donutConfig" :height="200" />
      </div>
      <div class="aud-card aud-chart-card aud-chart-wide">
        <div class="aud-card-t">Активность во времени</div>
        <AuditChart v-if="overview" :config="timelineConfig" :height="200" />
      </div>
      <div class="aud-card aud-chart-card">
        <div class="aud-card-t">По разделам</div>
        <AuditChart v-if="overview && (overview.top_modules.length)" :config="modulesConfig" :height="200" />
        <div v-else-if="overview" class="aud-empty-s">Нет данных</div>
      </div>
    </div>

    <div v-if="loading && !overview" class="aud-loading">Загрузка журнала…</div>

    <!-- MODE: по людям -->
    <div v-if="mode === 'users'" class="aud-users">
      <div v-for="(u, i) in sortedUsers" :key="u.actor_id" class="aud-user" :style="{ '--d': Math.min(i, 16) * 40 + 'ms' }" @click="openUser(u)">
        <div class="aud-ava" :style="{ background: u.accent }">{{ u.initials }}</div>
        <div class="aud-user-main">
          <div class="aud-user-name">{{ u.name }}<span v-if="u.role" class="aud-user-role">{{ u.role }}</span></div>
          <div class="aud-user-meta">{{ u.total.toLocaleString('ru') }} действий · {{ fmtRelative(u.last_at) }}</div>
          <div class="aud-user-bars">
            <span class="aud-ub" :style="{ background: '#7C6FF7', flex: u.changes }" :title="'Изменения: ' + u.changes" />
            <span class="aud-ub" :style="{ background: '#0891B2', flex: u.views }" :title="'Просмотры: ' + u.views" />
            <span class="aud-ub" :style="{ background: '#1D9E75', flex: u.logins }" :title="'Входы: ' + u.logins" />
            <span class="aud-ub" :style="{ background: '#EF4444', flex: u.deletions }" :title="'Удаления: ' + u.deletions" />
          </div>
        </div>
        <div class="aud-user-go">›</div>
      </div>
      <div v-if="overview && !sortedUsers.length" class="aud-empty">Нет активности за период</div>
    </div>

    <!-- MODE: лента -->
    <div v-else-if="mode === 'feed'" class="aud-card aud-feed">
      <div v-for="(e, i) in feed" :key="e.id" class="aud-ev" :style="{ '--d': Math.min(i, 20) * 25 + 'ms' }" @click="openEvent(e)">
        <span class="aud-ev-dot" :style="{ background: severity(e).color }" />
        <div class="aud-ev-main">
          <div class="aud-ev-line"><b>{{ (e.actor_email || 'Система').split('@')[0] }}</b> {{ describe(e) }}</div>
          <div class="aud-ev-meta">{{ whereText(e) }}<span v-if="whereText(e)"> · </span>{{ fmtRelative(e.created_at) }}<span v-if="e.ip_address"> · {{ e.ip_address }}</span></div>
        </div>
      </div>
      <div v-if="!feed.length && !loading" class="aud-empty">Нет событий</div>
    </div>

    <!-- MODE: по разделам -->
    <div v-else class="aud-card aud-modules">
      <div v-for="m in moduleRows" :key="m.module" class="aud-mrow">
        <div class="aud-mrow-l">{{ m.label }}</div>
        <div class="aud-mrow-bar"><span :style="{ width: m.pct + '%', background: m.accent }" /></div>
        <div class="aud-mrow-c">{{ m.count.toLocaleString('ru') }}</div>
      </div>
      <div v-if="!moduleRows.length" class="aud-empty">Нет данных</div>
    </div>

    <!-- USER MODAL -->
    <transition name="aud-modal">
      <div v-if="selUser" class="aud-backdrop" @click.self="closeUser">
        <div class="aud-modal">
          <div class="aud-modal-head">
            <div class="aud-ava aud-ava-lg" :style="{ background: selUser.accent }">{{ selUser.initials }}</div>
            <div>
              <div class="aud-modal-title">{{ selUser.name }}</div>
              <div class="aud-modal-sub">{{ selUser.email }}<span v-if="selUser.role"> · {{ selUser.role }}</span></div>
            </div>
            <button class="aud-x" @click="closeUser">×</button>
          </div>
          <div class="aud-modal-bars">
            <div v-for="b in userBars(selUser)" :key="b.label" class="aud-mb">
              <div class="aud-mb-top"><span>{{ b.label }}</span><b>{{ b.v }}</b></div>
              <div class="aud-mb-track"><span :style="{ width: b.pct + '%', background: b.c }" /></div>
            </div>
          </div>
          <div class="aud-modal-body">
            <div v-if="userLoading" class="aud-empty-s">Загрузка…</div>
            <div v-else-if="!userEvents.length" class="aud-empty-s">Нет записей за период</div>
            <div v-for="e in userEvents" :key="e.id" class="aud-ev aud-ev-flat" @click="openEvent(e)">
              <span class="aud-ev-dot" :style="{ background: severity(e).color }" />
              <div class="aud-ev-main">
                <div class="aud-ev-line">{{ describe(e) }}</div>
                <div class="aud-ev-meta">{{ whereText(e) }}<span v-if="whereText(e)"> · </span>{{ fmtRelative(e.created_at) }}</div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </transition>

    <!-- EVENT MODAL -->
    <transition name="aud-modal">
      <div v-if="selEvent || eventLoading" class="aud-backdrop" @click.self="closeEvent">
        <div class="aud-modal aud-modal-narrow">
          <div class="aud-modal-head">
            <div class="aud-modal-title">Детали события</div>
            <button class="aud-x" @click="closeEvent">×</button>
          </div>
          <div v-if="eventLoading" class="aud-empty-s">Загрузка…</div>
          <div v-else-if="selEvent" class="aud-modal-body">
            <div class="aud-kv"><span>Кто</span><b>{{ selEvent.actor_email || 'Система' }}</b></div>
            <div class="aud-kv"><span>Действие</span><b>{{ describe(selEvent) }}</b></div>
            <div class="aud-kv"><span>Раздел</span><b>{{ whereText(selEvent) || '—' }}</b></div>
            <div class="aud-kv"><span>Когда</span><b>{{ fmt.fmtDateTime(selEvent.created_at) }}</b></div>
            <div class="aud-kv"><span>IP</span><b>{{ selEvent.ip_address || '—' }}</b></div>
            <div class="aud-kv"><span>Статус</span><b>{{ selEvent.http_method }} {{ selEvent.http_status }}</b></div>
            <div v-if="selEvent.diff" class="aud-json"><div class="aud-json-t">Изменения</div><pre>{{ JSON.stringify(selEvent.diff, null, 2) }}</pre></div>
            <div v-if="selEvent.payload" class="aud-json"><div class="aud-json-t">Данные</div><pre>{{ JSON.stringify(selEvent.payload, null, 2) }}</pre></div>
          </div>
        </div>
      </div>
    </transition>

    <!-- PURGE MODAL -->
    <transition name="aud-modal">
      <div v-if="purgeOpen" class="aud-backdrop" @click.self="purgeOpen = false">
        <div class="aud-modal aud-modal-narrow">
          <div class="aud-modal-head"><div class="aud-modal-title">Очистка журнала</div><button class="aud-x" @click="purgeOpen = false">×</button></div>
          <div class="aud-modal-body">
            <p class="aud-purge-warn">Удаление записей необратимо. HMAC-цепочка целостности будет перестроена.</p>
            <label v-for="o in PURGE_OPTS" :key="String(o.v)" class="aud-radio">
              <input type="radio" :value="o.v" v-model="purgeKeep" /> {{ o.l }}
            </label>
            <button class="aud-btn aud-btn-danger aud-purge-go" :disabled="purging" @click="doPurge">{{ purging ? 'Удаляю…' : 'Удалить' }}</button>
          </div>
        </div>
      </div>
    </transition>
  </div>
</template>

<style scoped>
.aud { padding: 22px 26px 60px; max-width: 1320px; margin: 0 auto; font-family: var(--font); }
.aud-head { display: flex; justify-content: space-between; align-items: flex-end; gap: 16px; flex-wrap: wrap; }
.aud-eyebrow { font-size: 11px; font-weight: 700; letter-spacing: .08em; text-transform: uppercase; color: #7C6FF7; }
.aud-title { font-size: 25px; font-weight: 700; color: var(--t1, #1E2A4A); margin: 2px 0 0; }
.aud-sub { font-size: 13px; color: var(--t3, #8A94A6); margin-top: 2px; }
.aud-head-r { display: flex; gap: 8px; align-items: center; }
.aud-search { width: 240px; padding: 8px 12px; border: 1px solid rgba(15,23,60,.12); border-radius: 10px; font-size: 13px; outline: none; }
.aud-search:focus { border-color: #7C6FF7; }
.aud-btn { padding: 8px 13px; border-radius: 10px; border: 1px solid rgba(15,23,60,.12); background: #fff; font-size: 12.5px; font-weight: 600; color: #475569; cursor: pointer; transition: all .15s; }
.aud-btn:hover { border-color: #7C6FF7; color: #534AB7; }
.aud-btn-danger { color: #E24B4A; border-color: rgba(226,75,74,.25); }
.aud-btn-danger:hover { background: rgba(226,75,74,.08); border-color: #E24B4A; color: #E24B4A; }

.aud-controls { display: flex; justify-content: space-between; align-items: center; gap: 12px; margin: 18px 0 14px; flex-wrap: wrap; }
.aud-chips, .aud-modes { display: flex; gap: 6px; }
.aud-chip { padding: 6px 13px; border-radius: 999px; border: 1px solid rgba(15,23,60,.1); background: #fff; font-size: 12.5px; color: #64748B; cursor: pointer; transition: all .15s; }
.aud-chip.on { background: #7C6FF7; border-color: #7C6FF7; color: #fff; font-weight: 600; }
.aud-mode { padding: 6px 14px; border-radius: 9px; border: none; background: transparent; font-size: 13px; font-weight: 600; color: #94A3B8; cursor: pointer; }
.aud-modes { background: #F1F0FB; border-radius: 11px; padding: 3px; }
.aud-mode.on { background: #fff; color: #534AB7; box-shadow: 0 1px 4px rgba(15,23,60,.08); }

.aud-error { background: rgba(226,75,74,.08); color: #E24B4A; padding: 10px 14px; border-radius: 10px; font-size: 13px; margin-bottom: 14px; }
.aud-loading, .aud-empty { text-align: center; color: #94A3B8; font-size: 13px; padding: 40px; }
.aud-empty-s { color: #94A3B8; font-size: 12.5px; padding: 16px; text-align: center; }

.aud-kpis { display: grid; grid-template-columns: repeat(6, 1fr); gap: 12px; margin-bottom: 14px; }
@media (max-width: 900px) { .aud-kpis { grid-template-columns: repeat(3, 1fr); } }
.aud-kpi { position: relative; background: #fff; border-radius: var(--r2, 14px); padding: 15px 16px 14px; box-shadow: var(--sh, 0 1px 2px rgba(15,23,60,.04), 0 4px 16px rgba(15,23,60,.06)); overflow: hidden; animation: audUp .5s var(--ease-standard, cubic-bezier(.25,.8,.25,1)) var(--d) both; }
.aud-kpi::before { content: ""; position: absolute; left: 0; right: 0; top: 0; height: 3px; background: var(--acc, #7C6FF7); transform: scaleX(0); transform-origin: left; animation: audStripe .6s var(--ease-standard, cubic-bezier(.25,.8,.25,1)) var(--d) forwards; }
.aud-kpi-val { font-family: var(--font); font-size: 26px; font-weight: 700; color: var(--t1, #0F172A); font-variant-numeric: tabular-nums; letter-spacing: -.02em; line-height: 1.1; }
.aud-kpi-lbl { font-size: 11.5px; color: var(--t2, #64748B); margin-top: 4px; }

.aud-charts { display: grid; grid-template-columns: 1fr 1.6fr 1fr; gap: 12px; margin-bottom: 16px; }
@media (max-width: 1000px) { .aud-charts { grid-template-columns: 1fr; } }
.aud-card { background: #fff; border-radius: 14px; box-shadow: 0 3px 12px rgba(15,23,60,.05); padding: 14px 16px; }
.aud-card-t { font-size: 12px; font-weight: 700; text-transform: uppercase; letter-spacing: .05em; color: #8A94A6; margin-bottom: 10px; }

.aud-users { display: grid; grid-template-columns: repeat(2, 1fr); gap: 10px; }
@media (max-width: 760px) { .aud-users { grid-template-columns: 1fr; } }
.aud-user { display: flex; align-items: center; gap: 12px; background: #fff; border-radius: 13px; padding: 12px 14px; box-shadow: 0 2px 9px rgba(15,23,60,.05); cursor: pointer; transition: transform .15s, box-shadow .15s; animation: audUp .45s var(--ease-standard, cubic-bezier(.25,.8,.25,1)) var(--d) both; }
.aud-user:hover { transform: translateY(-2px); box-shadow: 0 6px 18px rgba(15,23,60,.1); }
.aud-ava { width: 42px; height: 42px; border-radius: 12px; display: grid; place-items: center; color: #fff; font-weight: 700; font-size: 15px; flex-shrink: 0; }
.aud-ava-lg { width: 52px; height: 52px; font-size: 18px; border-radius: 14px; }
.aud-user-main { flex: 1; min-width: 0; }
.aud-user-name { font-size: 14px; font-weight: 600; color: var(--t1, #1E2A4A); display: flex; align-items: center; gap: 8px; }
.aud-user-role { font-size: 10px; font-weight: 700; text-transform: uppercase; color: #7C6FF7; background: rgba(127,119,221,.1); border-radius: 5px; padding: 1px 6px; }
.aud-user-meta { font-size: 12px; color: #8A94A6; margin: 2px 0 7px; font-variant-numeric: tabular-nums; }
.aud-user-bars { display: flex; height: 6px; border-radius: 4px; overflow: hidden; background: #F1F0FB; }
.aud-ub { min-width: 0; }
.aud-user-go { color: #C7CDD8; font-size: 22px; flex-shrink: 0; }

.aud-feed { padding: 6px 8px; }
.aud-ev { display: flex; gap: 11px; padding: 11px 12px; border-radius: 10px; cursor: pointer; transition: background .12s; animation: audFade .4s ease var(--d) both; }
.aud-ev:hover { background: #F7F6FD; }
.aud-ev-flat { animation: none; }
.aud-ev-dot { width: 8px; height: 8px; border-radius: 50%; margin-top: 6px; flex-shrink: 0; }
.aud-ev-line { font-size: 13.5px; color: var(--t1, #1E2A4A); line-height: 1.4; }
.aud-ev-meta { font-size: 11.5px; color: #9AA3B2; margin-top: 2px; }

.aud-modules { display: flex; flex-direction: column; gap: 4px; }
.aud-mrow { display: grid; grid-template-columns: 160px 1fr 70px; align-items: center; gap: 12px; padding: 9px 10px; border-radius: 9px; }
.aud-mrow:hover { background: #F7F6FD; }
.aud-mrow-l { font-size: 13px; font-weight: 500; color: var(--t1, #1E2A4A); }
.aud-mrow-bar { height: 8px; background: #F1F0FB; border-radius: 5px; overflow: hidden; }
.aud-mrow-bar span { display: block; height: 100%; border-radius: 5px; transition: width .6s var(--ease-standard, cubic-bezier(.25,.8,.25,1)); }
.aud-mrow-c { text-align: right; font-weight: 700; font-size: 13px; font-variant-numeric: tabular-nums; color: var(--t1, #1E2A4A); }

/* Modals */
.aud-backdrop { position: fixed; inset: 0; background: rgba(15,18,40,.5); backdrop-filter: blur(2px); display: grid; place-items: center; z-index: 200; padding: 20px; }
.aud-modal { background: #fff; border-radius: 18px; width: min(640px, 100%); max-height: 86vh; max-height: 86dvh; display: flex; flex-direction: column; overflow: hidden; box-shadow: 0 20px 60px rgba(15,23,60,.3); }
.aud-modal-narrow { width: min(460px, 100%); }
.aud-modal-head { display: flex; align-items: center; gap: 12px; padding: 16px 18px; border-bottom: 1px solid rgba(15,23,60,.07); }
.aud-modal-title { font-size: 16px; font-weight: 700; color: var(--t1, #1E2A4A); }
.aud-modal-sub { font-size: 12px; color: #8A94A6; }
.aud-x { margin-left: auto; width: 30px; height: 30px; border: none; background: #F1F0FB; border-radius: 8px; font-size: 19px; color: #64748B; cursor: pointer; }
.aud-x:hover { background: #E5E3F5; }
.aud-modal-bars { display: grid; grid-template-columns: 1fr 1fr; gap: 10px 16px; padding: 14px 18px; border-bottom: 1px solid rgba(15,23,60,.07); }
.aud-mb-top { display: flex; justify-content: space-between; font-size: 12px; color: #64748B; margin-bottom: 3px; }
.aud-mb-track { height: 7px; background: #F1F0FB; border-radius: 4px; overflow: hidden; }
.aud-mb-track span { display: block; height: 100%; border-radius: 4px; transition: width .6s var(--ease-standard, cubic-bezier(.25,.8,.25,1)); }
.aud-modal-body { padding: 14px 18px; overflow-y: auto; }
.aud-kv { display: flex; justify-content: space-between; gap: 16px; padding: 7px 0; border-bottom: 1px solid rgba(15,23,60,.05); font-size: 13px; }
.aud-kv span { color: #8A94A6; } .aud-kv b { color: var(--t1, #1E2A4A); text-align: right; }
.aud-json { margin-top: 12px; }
.aud-json-t { font-size: 11px; font-weight: 700; text-transform: uppercase; color: #8A94A6; margin-bottom: 5px; }
.aud-json pre { background: #0F1230; color: #C7D0F5; border-radius: 10px; padding: 12px; font-size: 11.5px; overflow-x: auto; margin: 0; max-height: 220px; }
.aud-purge-warn { font-size: 13px; color: #E24B4A; background: rgba(226,75,74,.07); padding: 10px 12px; border-radius: 9px; }
.aud-radio { display: flex; gap: 9px; align-items: center; padding: 8px 0; font-size: 13.5px; cursor: pointer; }
.aud-purge-go { width: 100%; margin-top: 10px; padding: 11px; }

.aud-modal-enter-active, .aud-modal-leave-active { transition: opacity .2s; }
.aud-modal-enter-from, .aud-modal-leave-to { opacity: 0; }
.aud-modal-enter-active .aud-modal { transition: transform .25s var(--ease-standard, cubic-bezier(.25,.8,.25,1)); }
.aud-modal-enter-from .aud-modal { transform: translateY(16px) scale(.98); }

@keyframes audUp { from { opacity: 0; transform: translateY(10px); } to { opacity: 1; transform: translateY(0); } }
@keyframes audFade { from { opacity: 0; } to { opacity: 1; } }
@keyframes audStripe { to { transform: scaleX(1); } }
</style>
