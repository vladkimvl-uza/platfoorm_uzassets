<script setup lang="ts">
/**
 * Журнал аудита — переработка (2026-06): главный экран «по пользователям»,
 * статистика с графиками/таблицами, режимы (Люди / Лента / Модули), модалки.
 * Backend: /admin/audit/{overview,by-user,events,events/:id,export.csv,purge}.
 */
import { ref, computed, onMounted, onUnmounted, watch } from "vue";
import {
  auditApi as auditFeedApi,
  type AuditUserRow,
  type AuditOverviewResponse,
  type AuditEventRead,
  type AuditEventDetail,
} from "@/api/audit";
import { auditApi as rbacAuditApi } from "@/api/rbacV3";
import AuditChart from "@/components/audit/AuditChart.vue";
import UserAffiliationBadge from "@/components/rbac-v3/UserAffiliationBadge.vue";
import UserCardAnchor from "@/components/user/UserCardAnchor.vue";
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

import type { AuditCompanyRow } from "@/api/audit";
const overview = ref<AuditOverviewResponse | null>(null);
const users = ref<AuditUserRow[]>([]);
const companies = ref<AuditCompanyRow[]>([]);
const feed = ref<AuditEventRead[]>([]);
const feedTotal = ref(0);

const ACCENTS = ["#7C6FF7", "#1D9E75", "#0891B2", "#534AB7", "#5B7CFA", "#0F6E56", "#9A6FD4", "#D97706"];
// Единая палитра для баров: бренд-пурпур с убыванием насыщенности по рангу.
function barColor(i: number, n: number): string {
  const a = 0.92 - (n > 1 ? (i / (n - 1)) * 0.52 : 0);
  return `rgba(124, 111, 247, ${a.toFixed(2)})`;
}

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

const lastUpdated = ref<number>(Date.now());
async function load(silent = false) {
  if (!silent) loading.value = true;
  error.value = null;
  try {
    const [ov, us, co] = await Promise.all([
      auditFeedApi.overview(statsHours()),
      auditFeedApi.byUser({ since: sinceIso(), search: search.value || undefined }),
      auditFeedApi.byCompany({ since: sinceIso() }).catch(() => []),
    ]);
    overview.value = ov;
    users.value = us;
    companies.value = co;
    animateKpis();
    trackNew(ov.stats?.events_total ?? 0, silent);
    if (mode.value === "feed") await loadFeed();
    lastUpdated.value = Date.now();
  } catch (e: any) {
    if (!silent) error.value = e?.response?.data?.detail || "Не удалось загрузить журнал";
  } finally {
    if (!silent) loading.value = false;
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

// ─── Real-time: умный polling (только видимая вкладка, тихое обновление) ──
const autoRefresh = ref(true);
const AUTO_MS = 25000;
let pollTimer: ReturnType<typeof setInterval> | null = null;
const nowTick = ref(Date.now());
let tickTimer: ReturnType<typeof setInterval> | null = null;
function startPoll() {
  stopPoll();
  pollTimer = setInterval(() => {
    if (autoRefresh.value && !document.hidden && !drillOpen.value && !selUser.value) load(true);
  }, AUTO_MS);
}
function stopPoll() { if (pollTimer) { clearInterval(pollTimer); pollTimer = null; } }
function onVisibility() { if (!document.hidden && autoRefresh.value) load(true); }
const agoLabel = computed(() => {
  const s = Math.round((nowTick.value - lastUpdated.value) / 1000);
  if (s < 5) return "обновлено только что";
  if (s < 60) return `обновлено ${s} сек назад`;
  return `обновлено ${Math.round(s / 60)} мин назад`;
});

watch(mode, async (m) => { if (m === "feed" && !feed.value.length) await loadFeed(); });
watch(period, () => load());
onMounted(() => {
  load();
  startPoll();
  tickTimer = setInterval(() => { nowTick.value = Date.now(); }, 1000);
  document.addEventListener("visibilitychange", onVisibility);
});
onUnmounted(() => {
  stopPoll();
  if (tickTimer) clearInterval(tickTimer);
  document.removeEventListener("visibilitychange", onVisibility);
});

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
// Дефолтный стиль пайчартов проекта: тонкое кольцо (cutout), белые зазоры
// (borderColor+borderWidth), скруглённые концы (borderRadius), число в центре,
// кастомная HTML-легенда справа (точка · название · значение).
const donutSegments = computed(() => [
  { label: "Изменения", value: typeTotals.value.changes, color: "#7C6FF7" },
  { label: "Просмотры", value: typeTotals.value.views, color: "#0891B2" },
  { label: "Входы", value: typeTotals.value.logins, color: "#1D9E75" },
  { label: "Удаления", value: typeTotals.value.deletions, color: "#EF4444" },
  { label: "Ошибки", value: typeTotals.value.errors, color: "#94A3B8" },
].filter((s) => s.value > 0));
const donutTotal = computed(() => donutSegments.value.reduce((a, s) => a + s.value, 0));
const donutConfig = computed<ChartConfiguration>(() => ({
  type: "doughnut",
  data: {
    labels: donutSegments.value.map((s) => s.label),
    datasets: [{
      data: donutSegments.value.map((s) => s.value),
      backgroundColor: donutSegments.value.map((s) => s.color),
      borderColor: "rgba(255,255,255,0.92)", borderWidth: 3, borderRadius: 6, hoverOffset: 8,
    }],
  },
  options: {
    responsive: true, maintainAspectRatio: false, cutout: "80%",
    plugins: { legend: { display: false }, tooltip: { backgroundColor: "rgba(15,23,60,.95)", padding: 10, cornerRadius: 8 } },
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
      datasets: [{ data: m.map((x) => x.count), backgroundColor: m.map((_, i) => barColor(i, m.length)), borderRadius: 6, maxBarThickness: 26 }],
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
  // Запрос к ИИ-ассистенту — показываем сам текст запроса.
  if (a === "AI_QUERY" || a === "ai.query") {
    const q = String(e.notes || "").replace(/^Запрос:\s*/i, "").trim();
    return q ? `спросил(а) ИИ: «${q}»` : "обратил(ся/ась) к ИИ-ассистенту";
  }
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

// ─── Премиум-аналитика (клиентская, без бэкенда) ────────────────
// Спарклайны/дельты KPI из timeline.buckets.
const kpiSeries = computed<Record<string, number[]>>(() => {
  const b = overview.value?.timeline.buckets || [];
  return {
    total: b.map((x) => x.create + x.update + x.delete + x.view),
    changes: b.map((x) => x.create + x.update + x.delete),
    views: b.map((x) => x.view),
  };
});
function sparkPath(series: number[], w = 60, h = 18): string {
  if (series.length < 2) return "";
  const max = Math.max(1, ...series);
  const step = w / (series.length - 1);
  return series.map((v, i) => `${i ? "L" : "M"}${(i * step).toFixed(1)},${(h - (v / max) * (h - 2) - 1).toFixed(1)}`).join(" ");
}
function kpiDelta(key: string): { pct: number; dir: "up" | "down" | "flat" } | null {
  const s = kpiSeries.value[key];
  if (!s || s.length < 4) return null;
  const half = Math.floor(s.length / 2);
  const a = s.slice(0, half).reduce((x, y) => x + y, 0);
  const b = s.slice(half).reduce((x, y) => x + y, 0);
  if (!a && !b) return null;
  const pct = a === 0 ? 100 : Math.round(((b - a) / a) * 100);
  return { pct: Math.abs(pct), dir: pct > 3 ? "up" : pct < -3 ? "down" : "flat" };
}
// Готовые карточки KPI (со спарклайном и дельтой) — чтобы не звать функции в шаблоне.
const kpiCards = computed(() => KPIS.value.map((k) => ({
  ...k,
  spark: sparkPath(kpiSeries.value[k.key] || []),
  delta: kpiDelta(k.key),
})));

// Подсветка аномалий по человеку (много отказов/удалений).
function userRisk(u: AuditUserRow): { level: "high" | "warn"; reason: string } | null {
  const den = u.errors || 0, del = u.deletions || 0;
  if (den >= 5 || del >= 5) return { level: "high", reason: `${den} отказов · ${del} удалений` };
  if (den >= 2 || (u.total >= 5 && den / Math.max(1, u.total) > 0.15)) return { level: "warn", reason: `${den} отказов` };
  return null;
}

// «Сейчас онлайн» — люди с активностью за последние 6 минут.
const onlineUsers = computed(() =>
  users.value
    .filter((u) => u.last_at && nowTick.value - new Date(u.last_at).getTime() < 6 * 60e3)
    .sort((a, b) => (b.last_at || "").localeCompare(a.last_at || ""))
    .slice(0, 14),
);

// Фильтр списка людей по компании (клик по строке компании).
const companyFilter = ref<string | null>(null);
function toggleCompanyFilter(name: string) {
  companyFilter.value = companyFilter.value === name ? null : name;
  mode.value = "users";
}
const baseUsers = computed(() =>
  companyFilter.value ? users.value.filter((u) => (u.company || "") === companyFilter.value) : users.value,
);

// Сворачивание обзорной зоны (KPI + графики + компании).
const overviewCollapsed = ref(false);
try { overviewCollapsed.value = localStorage.getItem("aud_overview_collapsed") === "1"; } catch { /* ignore */ }
watch(overviewCollapsed, (v) => { try { localStorage.setItem("aud_overview_collapsed", v ? "1" : "0"); } catch { /* ignore */ } });

// Live: счётчик новых событий за последний тихий рефреш.
const newCount = ref(0);
let _prevTotal = 0;
let newCountTimer: ReturnType<typeof setTimeout> | null = null;
function trackNew(total: number, silent: boolean) {
  if (silent && _prevTotal && total > _prevTotal) {
    newCount.value = total - _prevTotal;
    if (newCountTimer) clearTimeout(newCountTimer);
    newCountTimer = setTimeout(() => { newCount.value = 0; }, 6000);
  }
  _prevTotal = total;
}

// ─── Сортировка пользователей ───────────────────────────────────
// Группировка и сортировка списка людей.
type GroupKey = "none" | "company" | "sector" | "department" | "job_title";
type SortKey = "activity" | "recent" | "name";
const groupBy = ref<GroupKey>("none");
const sortBy = ref<SortKey>("activity");
const GROUP_OPTS: { v: GroupKey; l: string }[] = [
  { v: "none", l: "Без группировки" }, { v: "company", l: "По компаниям" },
  { v: "sector", l: "По секторам" }, { v: "department", l: "По отделам" },
  { v: "job_title", l: "По должностям" },
];
const SORT_OPTS: { v: SortKey; l: string }[] = [
  { v: "activity", l: "По активности" }, { v: "recent", l: "По времени" }, { v: "name", l: "По имени" },
];
function _sorted(arr: AuditUserRow[]): AuditUserRow[] {
  const a = [...arr];
  if (sortBy.value === "name") a.sort((x, y) => x.name.localeCompare(y.name));
  else if (sortBy.value === "recent") a.sort((x, y) => (y.last_at || "").localeCompare(x.last_at || ""));
  else a.sort((x, y) => y.total - x.total);
  return a;
}
const sortedUsers = computed(() => _sorted(baseUsers.value));
// Сгруппированные секции (когда groupBy != none).
const groupedUsers = computed(() => {
  if (groupBy.value === "none") return [];
  const key = groupBy.value;
  const map = new Map<string, AuditUserRow[]>();
  for (const u of baseUsers.value) {
    const label = (u as any)[key] || "— Не указано";
    if (!map.has(label)) map.set(label, []);
    map.get(label)!.push(u);
  }
  const groups = [...map.entries()].map(([label, list]) => ({
    label,
    users: _sorted(list),
    total: list.reduce((s, u) => s + u.total, 0),
    people: list.length,
  }));
  groups.sort((a, b) => {
    const au = a.label.startsWith("—"), bu = b.label.startsWith("—");
    if (au !== bu) return au ? 1 : -1;
    return b.total - a.total;
  });
  return groups;
});
// Унифицированные секции для рендера (без группировки = одна безымянная секция).
const userSections = computed(() =>
  groupBy.value === "none"
    ? [{ label: null as string | null, users: sortedUsers.value, total: 0, people: sortedUsers.value.length }]
    : groupedUsers.value,
);

// ─── User modal (персональная аналитика) ───────────────────────
import type { AuditUserActivity } from "@/api/audit";
const selUser = ref<AuditUserRow | null>(null);
const activity = ref<AuditUserActivity | null>(null);
const userLoading = ref(false);
async function openUser(u: AuditUserRow) {
  selUser.value = u;
  activity.value = null;
  userLoading.value = true;
  try {
    activity.value = await auditFeedApi.userActivity(u.actor_id, { since: sinceIso() });
  } finally {
    userLoading.value = false;
  }
}
function closeUser() { selUser.value = null; activity.value = null; }

function fmtDur(sec: number): string {
  if (sec < 60) return `${sec} сек`;
  const m = Math.round(sec / 60);
  if (m < 60) return `${m} мин`;
  const h = Math.floor(m / 60), mm = m % 60;
  return mm ? `${h} ч ${mm} мин` : `${h} ч`;
}
function fmtClock(s: string): string {
  return new Date(s).toLocaleTimeString("ru", { hour: "2-digit", minute: "2-digit" });
}
function fmtDay(s: string): string {
  return new Date(s).toLocaleDateString("ru", { day: "2-digit", month: "short" });
}
function userBars(u: AuditUserRow) {
  const max = Math.max(1, u.changes, u.views, u.logins, u.deletions);
  return [
    { label: "Изменения", v: u.changes, pct: (u.changes / max) * 100, c: "#7C6FF7" },
    { label: "Просмотры", v: u.views, pct: (u.views / max) * 100, c: "#0891B2" },
    { label: "Входы", v: u.logins, pct: (u.logins / max) * 100, c: "#1D9E75" },
    { label: "Удаления", v: u.deletions, pct: (u.deletions / max) * 100, c: "#EF4444" },
  ];
}
// «Где провёл время» — топ-разделы по dwell-времени.
const moduleTime = computed(() => {
  const m = activity.value?.by_module || [];
  const max = Math.max(1, ...m.map((x) => x.seconds || 0), ...m.map((x) => x.count));
  return m.slice(0, 8).map((x) => ({
    ...x,
    pctTime: ((x.seconds || 0) / max) * 100,
  }));
});
const TYPE_DOT: Record<string, string> = {
  changes: "#7C6FF7", views: "#0891B2", logins: "#1D9E75",
  deletions: "#EF4444", errors: "#D97706", other: "#94A3B8",
};
// Сессии, сгруппированные по дням (новые сверху).
const sessionsByDay = computed(() => {
  const groups: { day: string; total: number; count: number; sessions: any[] }[] = [];
  const sorted = [...(activity.value?.sessions || [])].reverse();
  for (const s of sorted) {
    const day = fmtDay(s.start);
    let g = groups.find((x) => x.day === day);
    if (!g) { g = { day, total: 0, count: 0, sessions: [] }; groups.push(g); }
    g.sessions.push(s);
    g.total += s.duration_sec;
    g.count += s.events;
  }
  return groups;
});

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

// ─── Drill-down модалка (клик по KPI / донату / разделу) ────────
const drillOpen = ref(false);
const drillTitle = ref("");
const drillEvents = ref<AuditEventRead[]>([]);
const drillLoading = ref(false);
async function openDrill(title: string, params: { module?: string; action_category?: string; actor_email?: string }) {
  drillTitle.value = title;
  drillOpen.value = true;
  drillLoading.value = true;
  drillEvents.value = [];
  try {
    const r = await auditFeedApi.listEvents({ ...params, hours: statsHours(), per_page: 80 });
    drillEvents.value = r.items;
  } catch { drillEvents.value = []; }
  finally { drillLoading.value = false; }
}
function closeDrill() { drillOpen.value = false; drillEvents.value = []; }
// Клик по KPI-карточке.
function onKpiClick(key: string) {
  if (key === "users" || key === "online") { mode.value = "users"; return; }
  const map: Record<string, { title: string; cat: string }> = {
    total: { title: "Все действия", cat: "" },
    changes: { title: "Изменения", cat: "changes" },
    views: { title: "Просмотры", cat: "views" },
    errors: { title: "Ошибки и отказы", cat: "errors" },
  };
  const m = map[key];
  if (m) openDrill(m.title, m.cat ? { action_category: m.cat } : {});
}
// Клик по сегменту/легенде доната.
function onDonutClick(label: string) {
  const cat: Record<string, string> = {
    "Изменения": "changes", "Просмотры": "views", "Входы": "logins",
    "Удаления": "deletions", "Ошибки": "errors",
  };
  openDrill(label, { action_category: cat[label] || "" });
}

// ─── Модули (mode) ──────────────────────────────────────────────
const moduleRows = computed(() => {
  const m = overview.value?.top_modules || [];
  const max = Math.max(1, ...m.map((x) => x.count));
  return m.map((x, i) => ({ ...x, pct: (x.count / max) * 100, accent: barColor(i, m.length) }));
});
// ─── Активность по компаниям ────────────────────────────────────
const companyRows = computed(() => {
  const max = Math.max(1, ...companies.value.map((c) => c.total));
  return companies.value.map((c, i) => ({ ...c, pct: (c.total / max) * 100, accent: barColor(i, companies.value.length) }));
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
        <button class="aud-live" :class="{ on: autoRefresh }" @click="autoRefresh = !autoRefresh"
                :title="autoRefresh ? 'Авто-обновление включено · ' + agoLabel : 'Включить авто-обновление'">
          <span class="aud-live-dot" /> {{ autoRefresh ? 'Live' : 'Авто off' }}
          <transition name="aud-pop"><span v-if="newCount" class="aud-live-new">+{{ newCount }}</span></transition>
        </button>
        <button class="aud-btn aud-btn-refresh" :disabled="loading" @click="load()" title="Обновить журнал">
          <svg class="aud-refresh-ico" :class="{ spin: loading }" width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round">
            <path d="M21 12a9 9 0 1 1-2.64-6.36" /><path d="M21 3v6h-6" />
          </svg>
          Обновить
        </button>
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

    <!-- Overview header: онлайн-присутствие + свернуть -->
    <div class="aud-ovh">
      <div v-if="onlineUsers.length" class="aud-online">
        <span class="aud-online-lbl"><span class="aud-online-dot" /> Сейчас онлайн</span>
        <div class="aud-online-avas">
          <div v-for="u in onlineUsers" :key="u.actor_id" class="aud-online-ava" :style="{ background: u.accent }" :title="u.name" @click="openUser(u)">{{ u.initials }}</div>
        </div>
      </div>
      <span v-else class="aud-online-empty">Нет активных за последние минуты</span>
      <button class="aud-collapse" type="button" @click="overviewCollapsed = !overviewCollapsed">
        {{ overviewCollapsed ? 'Развернуть обзор' : 'Свернуть обзор' }}
        <svg class="aud-collapse-ic" :class="{ open: !overviewCollapsed }" width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"><path d="M6 9l6 6 6-6"/></svg>
      </button>
    </div>

    <!-- Stats band -->
    <div v-show="!overviewCollapsed" class="aud-kpis">
      <div v-for="(k, i) in kpiCards" :key="k.key" class="aud-kpi aud-kpi-click"
           :class="{ 'aud-kpi-alert': k.key === 'errors' && (kpi.errors || 0) > 0 }"
           :style="{ '--d': i * 60 + 'ms', '--acc': k.accent }" @click="onKpiClick(k.key)">
        <div class="aud-kpi-row">
          <div class="aud-kpi-val">{{ (kpi[k.key] || 0).toLocaleString('ru') }}</div>
          <svg v-if="k.spark" class="aud-kpi-spark" width="60" height="18" viewBox="0 0 60 18" fill="none" aria-hidden="true">
            <path :d="k.spark" :stroke="k.accent" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" opacity="0.85" />
          </svg>
        </div>
        <div class="aud-kpi-foot">
          <div class="aud-kpi-lbl">{{ k.label }}</div>
          <span v-if="k.delta" class="aud-kpi-delta" :class="'d-' + k.delta.dir">
            {{ k.delta.dir === 'up' ? '↑' : k.delta.dir === 'down' ? '↓' : '·' }}{{ k.delta.pct }}%
          </span>
        </div>
      </div>
    </div>

    <div v-show="!overviewCollapsed" class="aud-charts">
      <div class="aud-card aud-chart-card">
        <div class="aud-card-t">Типы действий</div>
        <div v-if="overview && donutTotal" class="aud-donut">
          <div class="aud-donut-ring">
            <AuditChart :config="donutConfig" :height="160" />
            <div class="aud-donut-center"><b>{{ donutTotal.toLocaleString('ru') }}</b><span>действий</span></div>
          </div>
          <ul class="aud-legend">
            <li v-for="s in donutSegments" :key="s.label" class="aud-legend-click" @click="onDonutClick(s.label)">
              <i :style="{ background: s.color }" /><span>{{ s.label }}</span><b>{{ s.value.toLocaleString('ru') }}</b>
            </li>
          </ul>
        </div>
        <div v-else-if="overview" class="aud-empty-s">Нет данных</div>
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

    <!-- Активность по компаниям -->
    <div v-if="overview" v-show="!overviewCollapsed" class="aud-card aud-comp-card">
      <div class="aud-card-t">Активность по компаниям<span class="aud-card-hint"> · клик — фильтр людей</span></div>
      <div v-if="companyRows.length" class="aud-comp-list">
        <div v-for="c in companyRows" :key="c.company" class="aud-comp-row aud-comp-click"
             :class="{ on: companyFilter === c.company }" @click="toggleCompanyFilter(c.company)">
          <div class="aud-comp-name">{{ c.company }}<span v-if="c.sector" class="aud-comp-sec">{{ c.sector }}</span></div>
          <div class="aud-comp-bar"><span :style="{ width: c.pct + '%', background: c.accent }" /></div>
          <div class="aud-comp-meta">{{ c.people }} чел · {{ c.total.toLocaleString('ru') }}</div>
        </div>
      </div>
      <div v-else class="aud-comp-empty">
        Нет данных по компаниям. Активность свяжется с компанией, когда сотрудникам проставят
        организацию (в профиле при первой настройке или администратором).
      </div>
    </div>

    <div v-if="loading && !overview" class="aud-loading">Загрузка журнала…</div>

    <!-- MODE: по людям -->
    <template v-if="mode === 'users'">
      <div v-if="companyFilter" class="aud-filterbar">
        <span class="aud-filterbar-lbl">Фильтр</span>
        <span class="aud-filter-chip">{{ companyFilter }}<button type="button" @click="companyFilter = null">×</button></span>
      </div>
      <div class="aud-grpbar">
        <div class="aud-grpbar-l">
          <span class="aud-grpbar-lbl">Группировка</span>
          <select v-model="groupBy" class="aud-sel">
            <option v-for="o in GROUP_OPTS" :key="o.v" :value="o.v">{{ o.l }}</option>
          </select>
        </div>
        <div class="aud-grpbar-l">
          <span class="aud-grpbar-lbl">Сортировка</span>
          <select v-model="sortBy" class="aud-sel">
            <option v-for="o in SORT_OPTS" :key="o.v" :value="o.v">{{ o.l }}</option>
          </select>
        </div>
      </div>

      <div v-for="(sec, si) in userSections" :key="sec.label || 'all'" class="aud-usec">
        <div v-if="sec.label" class="aud-usec-hd">
          <span class="aud-usec-name">{{ sec.label }}</span>
          <span class="aud-usec-meta">{{ sec.people }} чел · {{ sec.total.toLocaleString('ru') }} действий</span>
        </div>
        <div class="aud-users">
          <div v-for="(u, i) in sec.users" :key="u.actor_id" class="aud-user"
               :class="{ 'aud-user-risk': userRisk(u)?.level === 'high', 'aud-user-warn': userRisk(u)?.level === 'warn' }"
               :style="{ '--d': Math.min(si * 4 + i, 16) * 40 + 'ms' }" @click="openUser(u)">
            <UserCardAnchor :user-id="u.actor_id" :preview="{ full_name: u.name, initials: u.initials, accent: u.accent }">
              <div class="aud-ava" :class="{ ring: !!userRisk(u) }" :style="{ background: u.accent }">{{ u.initials }}</div>
            </UserCardAnchor>
            <div class="aud-user-main">
              <div class="aud-user-name">{{ u.name }}<span v-if="u.role" class="aud-user-role">{{ u.role }}</span><span v-if="userRisk(u)" class="aud-risk-flag" :class="userRisk(u)?.level" :title="userRisk(u)?.reason">риск</span></div>
              <UserAffiliationBadge
                v-if="u.company || u.sector || u.department || u.job_title"
                class="aud-user-aff" size="sm"
                :company="u.company" :sector="u.sector" :department="u.department" :job-title="u.job_title"
              />
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
        </div>
      </div>
      <div v-if="overview && !sortedUsers.length" class="aud-empty">Нет активности за период</div>
    </template>

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
      <div v-for="m in moduleRows" :key="m.module" class="aud-mrow aud-mrow-click" @click="openDrill(m.label, { module: m.module })">
        <div class="aud-mrow-l">{{ m.label }}</div>
        <div class="aud-mrow-bar"><span :style="{ width: m.pct + '%', background: m.accent }" /></div>
        <div class="aud-mrow-c">{{ m.count.toLocaleString('ru') }}</div>
      </div>
      <div v-if="!moduleRows.length" class="aud-empty">Нет данных</div>
    </div>

    <!-- USER MODAL — персональная аналитика -->
    <transition name="aud-modal">
      <div v-if="selUser" class="aud-backdrop" @click.self="closeUser">
        <div class="aud-modal aud-modal-lg">
          <div class="aud-modal-head">
            <div class="aud-ava aud-ava-lg">{{ selUser.initials }}</div>
            <div style="min-width:0">
              <div class="aud-modal-title">{{ selUser.name }}</div>
              <div class="aud-modal-sub">{{ selUser.email }}<span v-if="selUser.role"> · {{ selUser.role }}</span></div>
              <UserAffiliationBadge
                v-if="selUser.company || selUser.sector || selUser.department || selUser.job_title"
                style="margin-top:4px" size="sm"
                :company="selUser.company" :sector="selUser.sector" :department="selUser.department" :job-title="selUser.job_title"
              />
            </div>
            <button class="aud-x" @click="closeUser">×</button>
          </div>

          <div class="aud-um-body">
            <div v-if="userLoading" class="aud-empty-s">Загрузка активности…</div>
            <template v-else-if="activity">
              <!-- Сводка -->
              <div class="aud-um-summary">
                <div class="aud-um-stat"><b>{{ fmtDur(activity.in_system_seconds) }}</b><span>в системе</span></div>
                <div class="aud-um-stat"><b>{{ activity.sessions_count }}</b><span>сессий</span></div>
                <div class="aud-um-stat"><b>{{ activity.total_events.toLocaleString('ru') }}</b><span>действий</span></div>
              </div>

              <!-- Типы (бары) -->
              <div class="aud-um-bars">
                <div v-for="b in userBars(selUser)" :key="b.label" class="aud-mb">
                  <div class="aud-mb-top"><span>{{ b.label }}</span><b>{{ b.v }}</b></div>
                  <div class="aud-mb-track"><span :style="{ width: b.pct + '%', background: b.c }" /></div>
                </div>
              </div>

              <div class="aud-um-cols">
                <!-- Где провёл время -->
                <div class="aud-um-col">
                  <div class="aud-um-h">Где провёл время</div>
                  <div v-if="!moduleTime.length" class="aud-empty-s">—</div>
                  <div v-for="m in moduleTime" :key="m.module" class="aud-um-mod">
                    <div class="aud-um-mod-top">
                      <span class="aud-um-mod-l">{{ m.label }}</span>
                      <span class="aud-um-mod-t">{{ fmtDur(m.seconds) }} · {{ m.count }}</span>
                    </div>
                    <div class="aud-um-mod-bar"><span :style="{ width: m.pctTime + '%' }" /></div>
                  </div>
                </div>

                <!-- Сессии (по дням) -->
                <div class="aud-um-col">
                  <div class="aud-um-h">Сессии за период</div>
                  <div v-if="!sessionsByDay.length" class="aud-empty-s">—</div>
                  <div v-for="g in sessionsByDay" :key="g.day" class="aud-um-day">
                    <div class="aud-um-day-hd">
                      <span class="aud-um-day-l">{{ g.day }}</span>
                      <span class="aud-um-day-t">{{ fmtDur(g.total) }} · {{ g.count }} действий</span>
                    </div>
                    <div v-for="(s, i) in g.sessions" :key="i" class="aud-um-sess">
                      <span class="aud-um-sess-dot" />
                      <div class="aud-um-sess-main">
                        <div class="aud-um-sess-time">{{ fmtClock(s.start) }} — {{ fmtClock(s.end) }}</div>
                        <div class="aud-um-sess-meta">{{ fmtDur(s.duration_sec) }} · {{ s.events }} действий</div>
                      </div>
                    </div>
                  </div>
                </div>
              </div>

              <!-- Лента (схлопнутая) -->
              <div class="aud-um-h" style="margin-top:6px">Последние действия</div>
              <div class="aud-um-feed">
                <div v-for="(r, i) in activity.recent" :key="i" class="aud-ev aud-ev-flat">
                  <span class="aud-ev-dot" :style="{ background: TYPE_DOT[r.type] || '#94A3B8' }" />
                  <div class="aud-ev-main">
                    <div class="aud-ev-line">{{ r.desc }}<span v-if="r.count > 1" class="aud-ev-x">×{{ r.count }}</span></div>
                    <div class="aud-ev-meta">{{ r.label || '' }}<span v-if="r.label"> · </span>{{ fmtRelative(r.last_at) }}</div>
                  </div>
                </div>
                <div v-if="!activity.recent.length" class="aud-empty-s">Нет записей за период</div>
              </div>
            </template>
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

    <!-- DRILL-DOWN MODAL (клик по KPI/донату/разделу) -->
    <transition name="aud-modal">
      <div v-if="drillOpen" class="aud-backdrop" @click.self="closeDrill">
        <div class="aud-modal">
          <div class="aud-modal-head">
            <div class="aud-modal-title">{{ drillTitle }}</div>
            <button class="aud-x" @click="closeDrill">×</button>
          </div>
          <div class="aud-modal-body">
            <div v-if="drillLoading" class="aud-empty-s">Загрузка…</div>
            <div v-else-if="!drillEvents.length" class="aud-empty-s">Нет событий за период</div>
            <div v-for="e in drillEvents" :key="e.id" class="aud-ev aud-ev-flat" @click="openEvent(e)">
              <span class="aud-ev-dot" :style="{ background: severity(e).color }" />
              <div class="aud-ev-main">
                <div class="aud-ev-line"><b>{{ (e.actor_email || 'Система').split('@')[0] }}</b> {{ describe(e) }}</div>
                <div class="aud-ev-meta">{{ whereText(e) }}<span v-if="whereText(e)"> · </span>{{ fmtRelative(e.created_at) }}<span v-if="e.ip_address"> · {{ e.ip_address }}</span></div>
              </div>
            </div>
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
/* Live-индикатор (real-time polling) */
.aud-live { display: inline-flex; align-items: center; gap: 6px; padding: 8px 12px; border-radius: 10px; border: 1px solid rgba(15,23,60,.12); background: #fff; font-size: 12px; font-weight: 600; color: #94A3B8; cursor: pointer; font-family: var(--font); transition: all .15s; }
.aud-live.on { color: #1D9E75; border-color: rgba(29,158,117,.3); background: rgba(29,158,117,.05); }
.aud-live-dot { width: 7px; height: 7px; border-radius: 50%; background: #C7CDD8; }
.aud-live.on .aud-live-dot { background: #1D9E75; animation: audLivePulse 1.8s ease-in-out infinite; }
@keyframes audLivePulse { 0%,100% { box-shadow: 0 0 0 0 rgba(29,158,117,.5); } 50% { box-shadow: 0 0 0 5px rgba(29,158,117,0); } }
/* Кликабельные виджеты */
.aud-kpi-click { cursor: pointer; }
.aud-legend-click { cursor: pointer; border-radius: 7px; padding: 2px 4px; margin: -2px -4px; transition: background .13s; }
.aud-legend-click:hover { background: #F7F6FD; }
.aud-mrow-click { cursor: pointer; }
.aud-search { width: 240px; padding: 8px 12px; border: 1px solid rgba(15,23,60,.12); border-radius: 10px; font-size: 13px; outline: none; }
.aud-search:focus { border-color: #7C6FF7; }
.aud-btn { padding: 8px 13px; border-radius: 10px; border: 1px solid rgba(15,23,60,.12); background: #fff; font-size: 12.5px; font-weight: 600; color: #475569; cursor: pointer; transition: all .15s; }
.aud-btn:hover { border-color: #7C6FF7; color: #534AB7; }
.aud-btn-refresh { display: inline-flex; align-items: center; gap: 6px; background: #7C6FF7; border-color: #7C6FF7; color: #fff; }
.aud-btn-refresh:hover { background: #534AB7; border-color: #534AB7; color: #fff; }
.aud-btn-refresh:disabled { opacity: .6; cursor: default; }
.aud-refresh-ico.spin { animation: audSpin .8s linear infinite; }
@keyframes audSpin { to { transform: rotate(360deg); } }
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
/* Полоска KPI — 1:1 как эталон .kpi2 (draw-in + дыхание + одноразовый блик),
   keyframes kpi2DrawIn/kpi2Breathe/kpi2Shimmer глобальные (main.css). */
.aud-kpi::before { content: ""; position: absolute; left: 0; right: 0; top: 0; height: 3px; z-index: 1; background: var(--acc, #7C6FF7); transform-origin: left center; animation: kpi2DrawIn .8s var(--ease-standard, cubic-bezier(.25,.8,.25,1)) var(--d, 0ms) both, kpi2Breathe 2.8s ease-in-out calc(var(--d, 0ms) + 1s) infinite; }
.aud-kpi::after { content: ""; position: absolute; left: 0; right: 0; top: 0; height: 3px; z-index: 2; pointer-events: none; background: linear-gradient(90deg, transparent, rgba(255,255,255,.55), transparent); transform: translateX(-120%); animation: kpi2Shimmer 6s ease-in-out calc(var(--d, 0ms) + 1.2s) 1; }
.aud-kpi-val { font-family: var(--font); font-size: clamp(26px, 2.2vw, 34px); font-weight: 400; color: var(--t1, #0F172A); font-variant-numeric: tabular-nums; letter-spacing: -.025em; line-height: 1; }
.aud-kpi-lbl { font-size: 11px; font-weight: 600; text-transform: uppercase; letter-spacing: .05em; color: var(--t3, #94A3B8); margin-top: 6px; }

.aud-comp-card { margin-bottom: 16px; }
.aud-comp-list { display: flex; flex-direction: column; gap: 7px; }
.aud-comp-row { display: grid; grid-template-columns: minmax(140px, 1.2fr) 2fr auto; align-items: center; gap: 12px; padding: 7px 8px; border-radius: 9px; }
.aud-comp-row:hover { background: #F7F6FD; }
.aud-comp-name { font-size: 13px; font-weight: 500; color: var(--t1, #0F172A); display: flex; align-items: center; gap: 7px; min-width: 0; }
.aud-comp-name span.aud-comp-sec { font-size: 10px; font-weight: 600; color: #0E7490; background: rgba(8,145,178,.12); border-radius: 999px; padding: 1px 7px; white-space: nowrap; }
.aud-comp-bar { height: 8px; background: #F1F0FB; border-radius: 5px; overflow: hidden; }
.aud-comp-bar span { display: block; height: 100%; border-radius: 5px; transition: width .6s var(--ease-standard, cubic-bezier(.25,.8,.25,1)); }
.aud-comp-meta { text-align: right; font-size: 12px; font-weight: 600; color: var(--t1, #0F172A); font-variant-numeric: tabular-nums; white-space: nowrap; }
.aud-comp-empty { font-size: 12.5px; color: var(--t3, #94A3B8); line-height: 1.55; padding: 14px; background: #F7F6FD; border-radius: 10px; }
.aud-charts { display: grid; grid-template-columns: 1fr 1.6fr 1fr; gap: 12px; margin-bottom: 16px; }
@media (max-width: 1000px) { .aud-charts { grid-template-columns: 1fr; } }
.aud-card { background: #fff; border-radius: 14px; box-shadow: 0 3px 12px rgba(15,23,60,.05); padding: 14px 16px; }
.aud-card-t { font-size: 12px; font-weight: 700; text-transform: uppercase; letter-spacing: .05em; color: var(--t3, #8A94A6); margin-bottom: 10px; }

/* Донат — дефолтный стиль проекта: кольцо + центр + легенда-список */
.aud-donut { display: flex; align-items: center; gap: 14px; }
.aud-donut-ring { position: relative; width: 150px; height: 160px; flex-shrink: 0; }
.aud-donut-center { position: absolute; inset: 0; display: flex; flex-direction: column; align-items: center; justify-content: center; pointer-events: none; }
.aud-donut-center b { font-family: var(--font); font-size: 28px; font-weight: 400; color: var(--t1, #0F172A); letter-spacing: -.025em; line-height: 1; font-variant-numeric: tabular-nums; }
.aud-donut-center span { font-size: 10px; text-transform: uppercase; letter-spacing: .08em; color: var(--t3, #94A3B8); margin-top: 3px; }
.aud-legend { list-style: none; margin: 0; padding: 0; flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 7px; }
.aud-legend li { display: flex; align-items: center; gap: 8px; font-size: 12.5px; color: var(--t2, #334155); }
.aud-legend i { width: 10px; height: 10px; border-radius: 4px; flex-shrink: 0; }
.aud-legend span { flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.aud-legend b { font-weight: 600; color: var(--t1, #0F172A); font-variant-numeric: tabular-nums; }

.aud-grpbar { display: flex; gap: 18px; flex-wrap: wrap; margin-bottom: 14px; }
.aud-grpbar-l { display: flex; align-items: center; gap: 8px; }
.aud-grpbar-lbl { font-size: 11px; font-weight: 600; text-transform: uppercase; letter-spacing: .04em; color: var(--t3, #94A3B8); }
.aud-sel { border: 1px solid rgba(99,102,180,.16); border-radius: 9px; padding: 6px 10px; font-size: 12.5px; font-family: var(--font); background: #fff; color: var(--t1, #0F172A); cursor: pointer; outline: none; }
.aud-sel:focus { border-color: #7C6FF7; }
.aud-usec { margin-bottom: 18px; }
.aud-usec-hd { display: flex; align-items: baseline; justify-content: space-between; gap: 10px; padding: 0 2px 9px; }
.aud-usec-name { font-size: 14px; font-weight: 600; color: var(--t1, #0F172A); }
.aud-usec-meta { font-size: 11.5px; color: var(--t3, #94A3B8); font-variant-numeric: tabular-nums; white-space: nowrap; }
.aud-user-aff { margin: 3px 0 4px; }
.aud-users { display: grid; grid-template-columns: repeat(2, 1fr); gap: 10px; }
@media (max-width: 760px) { .aud-users { grid-template-columns: 1fr; } }
.aud-user { display: flex; align-items: center; gap: 12px; background: #fff; border-radius: 13px; padding: 12px 14px; box-shadow: 0 2px 9px rgba(15,23,60,.05); cursor: pointer; transition: transform .15s, box-shadow .15s; animation: audUp .45s var(--ease-standard, cubic-bezier(.25,.8,.25,1)) var(--d) both; }
.aud-user:hover { transform: translateY(-2px); box-shadow: 0 6px 18px rgba(15,23,60,.1); }
/* Аватар — единый стиль платформы (как UserAvatar.vue): скруглённый квадрат
   8px, пурпурный градиент, белые инициалы 500. */
.aud-ava { width: 42px; height: 42px; border-radius: 8px; display: grid; place-items: center; color: #fff; font-weight: 500; font-size: 15px; flex-shrink: 0; background: linear-gradient(135deg, #7F77DD, var(--p-deep, #534AB7)); letter-spacing: -.01em; }
.aud-ava-lg { width: 52px; height: 52px; font-size: 18px; border-radius: 10px; }
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
.aud-modal-lg { width: min(720px, 100%); }

/* User activity modal */
.aud-um-body { padding: 0 18px 18px; overflow-y: auto; scrollbar-gutter: stable; }
.aud-um-summary { display: grid; grid-template-columns: repeat(3, 1fr); gap: 10px; padding: 14px 0; }
.aud-um-stat { background: #F7F6FD; border-radius: 12px; padding: 12px 14px; text-align: center; }
.aud-um-stat b { display: block; font-family: var(--font); font-size: 21px; font-weight: 400; letter-spacing: -.02em; color: var(--t1, #0F172A); line-height: 1.1; }
.aud-um-stat span { font-size: 10.5px; text-transform: uppercase; letter-spacing: .05em; color: var(--t3, #94A3B8); margin-top: 3px; display: block; }
.aud-um-bars { display: grid; grid-template-columns: 1fr 1fr; gap: 9px 16px; padding-bottom: 14px; border-bottom: 1px solid rgba(15,23,60,.06); }
.aud-um-cols { display: grid; grid-template-columns: 1fr 1fr; gap: 18px; padding: 14px 0; border-bottom: 1px solid rgba(15,23,60,.06); }
@media (max-width: 620px) { .aud-um-cols, .aud-um-bars, .aud-um-summary { grid-template-columns: 1fr; } }
.aud-um-h { font-size: 11px; font-weight: 700; text-transform: uppercase; letter-spacing: .05em; color: var(--t3, #94A3B8); margin-bottom: 10px; }
.aud-um-mod { margin-bottom: 9px; }
.aud-um-mod-top { display: flex; justify-content: space-between; gap: 8px; font-size: 12px; margin-bottom: 3px; }
.aud-um-mod-l { color: var(--t1, #0F172A); font-weight: 500; }
.aud-um-mod-t { color: var(--t3, #94A3B8); font-variant-numeric: tabular-nums; white-space: nowrap; }
.aud-um-mod-bar { height: 6px; background: #F1F0FB; border-radius: 4px; overflow: hidden; }
.aud-um-mod-bar span { display: block; height: 100%; border-radius: 4px; background: linear-gradient(90deg, #7C6FF7, #534AB7); transition: width .5s var(--ease-standard, cubic-bezier(.25,.8,.25,1)); }
.aud-um-day { margin-bottom: 10px; }
.aud-um-day-hd { display: flex; justify-content: space-between; gap: 8px; align-items: baseline; padding: 4px 0 2px; border-bottom: 1px solid rgba(15,23,60,.06); margin-bottom: 4px; }
.aud-um-day-l { font-size: 12px; font-weight: 600; color: var(--t1, #0F172A); }
.aud-um-day-t { font-size: 10.5px; color: var(--t3, #94A3B8); font-variant-numeric: tabular-nums; white-space: nowrap; }
.aud-um-sess { display: flex; gap: 9px; padding: 5px 0 5px 6px; }
.aud-um-sess-dot { width: 7px; height: 7px; border-radius: 50%; background: #1D9E75; margin-top: 5px; flex-shrink: 0; }
.aud-um-sess-time { font-size: 12.5px; color: var(--t1, #0F172A); font-variant-numeric: tabular-nums; }
.aud-um-sess-meta { font-size: 11px; color: var(--t3, #94A3B8); margin-top: 1px; }
.aud-um-feed { max-height: 260px; overflow-y: auto; scrollbar-gutter: stable; margin-top: 4px; }
.aud-ev-x { color: #7C6FF7; font-weight: 700; margin-left: 6px; font-size: 11.5px; }
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

/* ── Премиум-апгрейд: спарклайны/дельты KPI ── */
.aud-kpi-row { display: flex; align-items: flex-end; justify-content: space-between; gap: 8px; }
.aud-kpi-spark { flex-shrink: 0; overflow: visible; margin-bottom: 2px; }
.aud-kpi-foot { display: flex; align-items: center; justify-content: space-between; gap: 8px; margin-top: 6px; }
.aud-kpi-foot .aud-kpi-lbl { margin-top: 0; }
.aud-kpi-delta { font-size: 10.5px; font-weight: 700; letter-spacing: .02em; font-variant-numeric: tabular-nums; padding: 1px 6px; border-radius: 999px; white-space: nowrap; }
.aud-kpi-delta.d-up { color: #0F6E56; background: rgba(29,158,117,.12); }
.aud-kpi-delta.d-down { color: #B91C1C; background: rgba(239,68,68,.10); }
.aud-kpi-delta.d-flat { color: #64748B; background: rgba(100,116,139,.10); }
.aud-kpi-alert { box-shadow: 0 1px 2px rgba(239,68,68,.10), 0 4px 16px rgba(239,68,68,.16); background: linear-gradient(180deg, rgba(239,68,68,.05), #fff 42%); }

/* ── Обзор-хедер: онлайн-присутствие + свернуть ── */
.aud-ovh { display: flex; align-items: center; justify-content: space-between; gap: 12px; margin-bottom: 12px; flex-wrap: wrap; }
.aud-online { display: flex; align-items: center; gap: 10px; min-width: 0; }
.aud-online-lbl { display: inline-flex; align-items: center; gap: 6px; font-size: 11px; font-weight: 700; text-transform: uppercase; letter-spacing: .05em; color: var(--t3, #94A3B8); white-space: nowrap; }
.aud-online-dot { width: 7px; height: 7px; border-radius: 50%; background: #1D9E75; animation: audLivePulse 1.8s ease-in-out infinite; }
.aud-online-avas { display: flex; }
.aud-online-ava { width: 26px; height: 26px; border-radius: 7px; display: grid; place-items: center; color: #fff; font-size: 10px; font-weight: 600; cursor: pointer; margin-left: -6px; border: 2px solid #fff; box-shadow: 0 1px 3px rgba(15,23,60,.12); transition: transform .14s; }
.aud-online-ava:first-child { margin-left: 0; }
.aud-online-ava:hover { transform: translateY(-2px); }
.aud-online-empty { font-size: 12px; color: var(--t3, #94A3B8); }
.aud-collapse { display: inline-flex; align-items: center; gap: 6px; border: 1px solid rgba(15,23,60,.1); background: #fff; border-radius: 9px; padding: 6px 11px; font-size: 12px; font-weight: 600; color: #64748B; cursor: pointer; font-family: var(--font); transition: all .14s; white-space: nowrap; }
.aud-collapse:hover { border-color: #7C6FF7; color: #534AB7; }
.aud-collapse-ic { transition: transform .2s; }
.aud-collapse-ic.open { transform: rotate(180deg); }

/* ── Кросс-фильтр по компании ── */
.aud-comp-click { cursor: pointer; transition: background .13s; }
.aud-comp-row.on { background: rgba(124,111,247,.08); box-shadow: inset 0 0 0 1px rgba(124,111,247,.25); }
.aud-card-hint { font-weight: 500; text-transform: none; letter-spacing: 0; color: #B6BECC; }
.aud-filterbar { display: flex; align-items: center; gap: 8px; margin-bottom: 12px; }
.aud-filterbar-lbl { font-size: 11px; font-weight: 600; text-transform: uppercase; letter-spacing: .04em; color: var(--t3, #94A3B8); }
.aud-filter-chip { display: inline-flex; align-items: center; gap: 6px; font-size: 12.5px; font-weight: 600; color: #534AB7; background: rgba(124,111,247,.12); border-radius: 999px; padding: 4px 6px 4px 11px; }
.aud-filter-chip button { border: none; background: rgba(124,111,247,.18); color: #534AB7; width: 18px; height: 18px; border-radius: 50%; cursor: pointer; font-size: 13px; line-height: 1; display: grid; place-items: center; }
.aud-filter-chip button:hover { background: rgba(124,111,247,.3); }

/* ── Live: +N новых ── */
.aud-live-new { font-size: 10.5px; font-weight: 700; color: #fff; background: #1D9E75; border-radius: 999px; padding: 1px 6px; margin-left: 2px; }
.aud-pop-enter-active, .aud-pop-leave-active { transition: opacity .2s, transform .2s; }
.aud-pop-enter-from, .aud-pop-leave-to { opacity: 0; transform: scale(.6); }

/* ── Подсветка аномалий ── */
.aud-ava.ring { box-shadow: 0 0 0 2px #fff, 0 0 0 4px rgba(239,68,68,.55); }
.aud-user-risk { box-shadow: 0 2px 9px rgba(239,68,68,.12), inset 0 0 0 1px rgba(239,68,68,.28); }
.aud-user-warn { box-shadow: 0 2px 9px rgba(217,119,6,.10), inset 0 0 0 1px rgba(217,119,6,.22); }
.aud-risk-flag { font-size: 9px; font-weight: 700; text-transform: uppercase; letter-spacing: .04em; border-radius: 5px; padding: 1px 6px; }
.aud-risk-flag.high { color: #B91C1C; background: rgba(239,68,68,.13); }
.aud-risk-flag.warn { color: #B45309; background: rgba(217,119,6,.13); }
</style>
