<script setup lang="ts">
/**
 * CommandPalette — глобальная командная палитра (Cmd/Ctrl+K).
 *
 * Открывается хоткеем или событием window "uza:command-palette".
 * Секции: Недавнее · Переход · Компании · Действия · AI.
 * Fuzzy-поиск, навигация стрелками, уважение прав (auth.hasPermission).
 * Чистый frontend: индекс из роутов + загруженных компаний.
 */
import { ref, computed, onMounted, onBeforeUnmount, nextTick, watch } from "vue";
import { useRouter } from "vue-router";
import { useAuthStore } from "@/stores/auth";
import { companiesApi } from "@/api/companies";

const router = useRouter();
const auth = useAuthStore();

const open = ref(false);
const query = ref("");
const selected = ref(0);
const inputEl = ref<HTMLInputElement | null>(null);
const listEl = ref<HTMLElement | null>(null);

const isMac = typeof navigator !== "undefined" && /Mac/i.test(navigator.platform);

type Kind = "nav" | "company" | "action" | "ai" | "scoped";
interface Cmd {
  id: string;
  title: string;
  subtitle?: string;
  group: string;
  kind: Kind;
  icon: string;
  keywords?: string;
  run: () => void;
}

// ─── SVG-иконки (внутренняя разметка) ───
const ICONS: Record<string, string> = {
  chart: '<path d="M3 3v18h18"/><path d="M18.7 8l-5.1 5.2-2.8-2.7L7 14.3"/>',
  activity: '<path d="M12 2v4M12 18v4M4.9 4.9l2.8 2.8M16.3 16.3l2.8 2.8M2 12h4M18 12h4M4.9 19.1l2.8-2.8M16.3 7.7l2.8-2.8"/><circle cx="12" cy="12" r="3"/>',
  grid: '<rect x="3" y="3" width="7" height="7" rx="1"/><rect x="14" y="3" width="7" height="7" rx="1"/><rect x="3" y="14" width="7" height="7" rx="1"/><rect x="14" y="14" width="7" height="7" rx="1"/>',
  eye: '<path d="M1 12s4-7 11-7 11 7 11 7-4 7-11 7-11-7-11-7z"/><circle cx="12" cy="12" r="3"/>',
  calendar: '<rect x="3" y="4" width="18" height="18" rx="2"/><line x1="16" y1="2" x2="16" y2="6"/><line x1="8" y1="2" x2="8" y2="6"/><line x1="3" y1="10" x2="21" y2="10"/>',
  file: '<path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/>',
  target: '<path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/><polyline points="22 4 12 14.01 9 11.01"/>',
  bars: '<line x1="6" y1="20" x2="6" y2="14"/><line x1="12" y1="20" x2="12" y2="8"/><line x1="18" y1="20" x2="18" y2="11"/>',
  building: '<path d="M3 21h18"/><path d="M5 21V8l7-5 7 5v13"/><path d="M9 21V12h6v9"/>',
  leaf: '<path d="M12 2c4 4 7 8 7 12a7 7 0 1 1-14 0c0-4 3-8 7-12z"/><path d="M12 12v9"/>',
  cart: '<circle cx="9" cy="21" r="1"/><circle cx="20" cy="21" r="1"/><path d="M1 1h4l2.7 13.4a2 2 0 0 0 2 1.6h9.7a2 2 0 0 0 2-1.6L23 6H6"/>',
  users: '<path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M23 21v-2a4 4 0 0 0-3-3.87"/><path d="M16 3.13a4 4 0 0 1 0 7.75"/>',
  star: '<polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2"/>',
  layers: '<polygon points="12 2 2 7 12 12 22 7 12 2"/><polyline points="2 17 12 22 22 17"/><polyline points="2 12 12 17 22 12"/>',
  book: '<path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20"/><path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z"/>',
  sparkles: '<path d="M12 3l1.9 5.1L19 10l-5.1 1.9L12 17l-1.9-5.1L5 10l5.1-1.9z"/><path d="M19 15l.8 2.2L22 18l-2.2.8L19 21l-.8-2.2L16 18l2.2-.8z"/>',
  bell: '<path d="M18 8a6 6 0 0 0-12 0c0 7-3 9-3 9h18s-3-2-3-9"/><path d="M13.7 21a2 2 0 0 1-3.4 0"/>',
  shield: '<path d="M12 2l7 4v6c0 5-3.5 8.5-7 10-3.5-1.5-7-5-7-10V6z"/>',
  plus: '<line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/>',
  logout: '<path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"/><polyline points="16 17 21 12 16 7"/><line x1="21" y1="12" x2="9" y2="12"/>',
  cog: '<circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z"/>',
  dot: '<circle cx="12" cy="12" r="4"/>',
};

const can = (c: string) => auth.hasPermission(c);
const isAdmin = computed(() => {
  const u: any = auth.user;
  return !!(u && (u.is_owner === true || u.is_admin === true || (Array.isArray(u.roles) && u.roles.includes("admin"))));
});

function go(path: string) { router.push(path); close(); }
function logout() { close(); auth.clear(); router.push({ name: "login" }); }

// ─── Навигационные команды (гейтятся теми же правами, что роуты/сайдбар) ───
const navCommands = computed<Cmd[]>(() => {
  // [показывать?, заголовок, подзаголовок, путь, иконка, ключевые слова]
  const defs: Array<[boolean, string, string, string, string, string]> = [
    [can("financials.view"), "Executive Dashboard", "Обзор портфеля", "/executive-dashboard", "chart", "дашборд executive обзор"],
    [isAdmin.value, "Execution Summary", "Мониторинг прогрессов", "/execution-summary", "activity", "control tower live мониторинг"],
    [can("projects.view") || can("tasks.view"), "Проекты трансформации", "Портфель проектов и задач", "/dashboard", "grid", "проекты задачи доска kanban"],
    [can("tasks.view"), "Отслеживаемое", "Подписки на изменения", "/followed", "eye", "watch подписки отслеживание"],
    [can("tasks.view"), "Календарь", "Дедлайны проектов и задач", "/calendar", "calendar", "календарь сроки дедлайны"],
    [can("bp.view"), "Бизнес-план", "", "/business-plan", "file", "бизнес план bp"],
    [can("kpi.view"), "KPI", "Ключевые показатели", "/kpi", "target", "kpi показатели цели"],
    [can("financials.view"), "Финансы · Обзор портфеля", "", "/financials", "bars", "финансы отчётность портфель"],
    [can("finmodel.view"), "Финансовая модель", "Внешний модуль", "/finmodel", "bars", "finmodel финмодель модель"],
    [can("credit.view"), "Кредитный портфель", "Внешний модуль", "/credit-portfolio", "bars", "кредиты займы covenant"],
    [can("investment.view"), "Инвест-проекты", "CAPEX-объекты", "/invest-projects", "bars", "инвестиции capex проекты"],
    [can("governance.view"), "Корпоративное управление", "", "/governance", "building", "governance совет директоров"],
    [can("esg.view"), "ESG", "Экология, общество, управление", "/esg", "leaf", "esg экология устойчивость"],
    [can("procurement.view"), "Закупки и форензик-аудит", "", "/procurement/forensic", "cart", "закупки форензик аудит"],
    [can("procurement.view"), "Анализ закупочной деятельности", "", "/procurement/analysis", "cart", "анализ закупки supplier"],
    [can("consultants.view"), "Консультанты", "", "/consultants", "users", "консультанты советники"],
    [can("ratings.view"), "Рейтинги", "", "/ratings", "star", "рейтинги оценки"],
    [can("companies.view"), "Компании", "Все предприятия портфеля", "/companies", "layers", "компании предприятия soe"],
    [can("companies.view"), "Библиотека · Компании", "MDM-карточки", "/library/companies", "book", "библиотека mdm справочник"],
    [can("ai.chat"), "ИИ-ассистент", "RAG по корпоративным данным", "/ai-chat", "sparkles", "ии ai чат ассистент"],
    [true, "Уведомления", "Входящие", "/notifications", "bell", "уведомления входящие notifications"],
    // admin
    [isAdmin.value || can("admin.users"), "Доступы (RBAC)", "Настройки", "/admin/rbac-v3", "shield", "доступы права rbac роли пользователи"],
    [can("moderation.review"), "Модерация", "Настройки", "/admin/moderation", "shield", "модерация review"],
    [can("companies.edit"), "Компании и сектора", "Настройки", "/admin/companies-legacy", "building", "компании сектора админ"],
    [can("system.config.view"), "Macro Indicators", "Настройки", "/admin/system-config", "bars", "макро константы курс инфляция"],
    [can("notifications.broadcast"), "Кастомные рассылки", "Настройки", "/admin/broadcasts", "bell", "рассылки broadcast"],
    [can("tasks.edit"), "Конструктор задач и проектов", "Массовое заведение", "/project-builder", "plus", "конструктор массовое создание задачи"],
    [isAdmin.value, "База данных", "Настройки", "/admin/database", "layers", "база данных sql консоль"],
    [isAdmin.value, "Почта и уведомления (SMTP)", "Настройки", "/admin/email-settings", "bell", "smtp почта email"],
    [can("api_catalog.read"), "Каталог API", "Настройки", "/admin/api", "book", "api каталог интеграции"],
    [true, "Документация API", "", "/api-docs", "book", "api docs документация"],
    [true, "Безопасность и пароль", "Настройки профиля", "/settings/security", "cog", "безопасность пароль mfa 2fa"],
  ];
  return defs
    .filter(([show]) => show)
    .map(([, title, subtitle, path, icon, keywords]) => ({
      id: `nav:${path}`,
      title, subtitle, icon, keywords,
      group: "Переход", kind: "nav" as Kind,
      run: () => go(path),
    }));
});

// ─── Компании (lazy) ───
const companies = ref<{ id: string; name: string; sub: string; kw: string; code: string }[]>([]);
async function loadCompanies() {
  if (companies.value.length || !can("companies.view")) return;
  try {
    const resp = await companiesApi.list({ limit: 500 } as any);
    companies.value = (resp.items || []).map((c: any) => ({
      id: c.id,
      code: c.code || "",
      name: c.name_ru || c.name_short || c.code || "Компания",
      sub: c.name_short && c.name_short !== (c.name_ru || "") ? c.name_short : (c.code || ""),
      kw: `${c.code || ""} ${c.name_short || ""} ${c.name_en || ""}`.trim(),
    }));
  } catch { /* ignore */ }
}
const companyCommands = computed<Cmd[]>(() =>
  companies.value.map((c) => ({
    id: `co:${c.id}`,
    title: c.name,
    subtitle: c.sub || "Компания",
    keywords: c.kw,
    group: "Компании", kind: "company" as Kind, icon: "building",
    run: () => go(`/library/companies/${c.id}`),
  })),
);

// ─── Scoped: компания + раздел воркспейса (/companies/{code}/workspace?tab=) ───
interface ScopedCmd extends Cmd {
  companyTitle: string; companyText: string; moduleLabel: string; moduleText: string;
}
// id вкладок 1:1 с VALID_TABS в CompanyWorkspace.vue (?tab=…)
const WS_MODULES: Array<{ id: string; label: string; icon: string; kw: string }> = [
  { id: "overview",    label: "Обзор",            icon: "eye",      kw: "обзор overview карточка" },
  { id: "kanban",      label: "Канбан",           icon: "grid",     kw: "канбан kanban доска задачи" },
  { id: "list",        label: "Список задач",     icon: "file",     kw: "список list задачи" },
  { id: "notes",       label: "Календарь",        icon: "calendar", kw: "календарь заметки calendar дедлайны" },
  { id: "ifrs",        label: "МСФО",             icon: "bars",     kw: "мсфо ifrs финансы отчётность" },
  { id: "nsbu",        label: "НСБУ",             icon: "bars",     kw: "нсбу nsbu финансы отчётность" },
  { id: "hlf",         label: "Фин. отчётность",  icon: "bars",     kw: "финансовая отчётность hlf финансы" },
  { id: "bp",          label: "Бизнес-план",      icon: "file",     kw: "бизнес план bp" },
  { id: "kpi",         label: "KPI",              icon: "target",   kw: "kpi показатели цели" },
  { id: "procurement", label: "Закупки",          icon: "cart",     kw: "закупки procurement" },
  { id: "governance",  label: "Корп. управление", icon: "building", kw: "корпоративное управление governance совет" },
  { id: "consultants", label: "Консультанты",     icon: "users",    kw: "консультанты советники" },
  { id: "esg",         label: "ESG",              icon: "leaf",     kw: "esg экология устойчивость" },
];
const scopedCommands = computed<ScopedCmd[]>(() => {
  if (!can("companies.view")) return [];
  const out: ScopedCmd[] = [];
  for (const co of companies.value) {
    if (!co.code) continue;
    const companyText = `${co.name} ${co.kw}`.toLowerCase();
    const code = co.code.toLowerCase();
    for (const m of WS_MODULES) {
      out.push({
        id: `scoped:${code}:${m.id}`,
        title: `${co.name} · ${m.label}`,
        subtitle: "Раздел компании",
        group: "Компания · раздел", kind: "scoped", icon: m.icon,
        companyTitle: co.name.toLowerCase(), companyText,
        moduleLabel: m.label.toLowerCase(), moduleText: `${m.label} ${m.kw}`.toLowerCase(),
        run: () => go(`/companies/${encodeURIComponent(code)}/workspace?tab=${m.id}`),
      });
    }
  }
  return out;
});

// ─── Действия ───
const actionCommands = computed<Cmd[]>(() => {
  const out: Cmd[] = [];
  if (can("tasks.edit"))
    out.push({ id: "act:newtask", title: "Создать задачу или проект", subtitle: "Конструктор", group: "Действия", kind: "action", icon: "plus", keywords: "новая задача проект создать", run: () => go("/project-builder") });
  out.push({ id: "act:notifsettings", title: "Настройки уведомлений", group: "Действия", kind: "action", icon: "cog", keywords: "настройки уведомлений telegram email", run: () => go("/notifications/settings") });
  out.push({ id: "act:logout", title: "Выйти из системы", group: "Действия", kind: "action", icon: "logout", keywords: "выйти logout выход", run: () => logout() });
  return out;
});

// ─── AI-команда (динамическая от запроса) ───
const aiCommand = computed<Cmd | null>(() => {
  const q = query.value.trim();
  if (!q || !can("ai.chat")) return null;
  return {
    id: "ai:ask", title: `Спросить ИИ: «${q}»`, group: "AI", kind: "ai", icon: "sparkles",
    run: () => { router.push({ name: "ai-chat", query: { q } }); close(); },
  };
});

// ─── Недавнее ───
const RECENT_KEY = "uza_cmdk_recent_v1";
const recentIds = ref<string[]>(loadRecent());
function loadRecent(): string[] {
  try { const r = JSON.parse(localStorage.getItem(RECENT_KEY) || "[]"); return Array.isArray(r) ? r : []; } catch { return []; }
}
function pushRecent(id: string) {
  recentIds.value = [id, ...recentIds.value.filter((x) => x !== id)].slice(0, 8);
  try { localStorage.setItem(RECENT_KEY, JSON.stringify(recentIds.value)); } catch { /* ignore */ }
}
const recentCommands = computed<Cmd[]>(() => {
  const pool = new Map<string, Cmd>();
  for (const c of [...navCommands.value, ...companyCommands.value, ...actionCommands.value, ...scopedCommands.value]) pool.set(c.id, c);
  return recentIds.value.map((id) => pool.get(id)).filter(Boolean).slice(0, 6) as Cmd[];
});

// ─── Поиск / скоринг ───
function subseq(q: string, text: string): boolean {
  let i = 0;
  for (let j = 0; j < text.length && i < q.length; j++) if (text[j] === q[i]) i++;
  return i === q.length;
}
function tokenScore(tk: string, title: string, text: string): number {
  let idx = title.indexOf(tk);
  if (idx === 0) return 1000;
  if (idx > 0) return 760 - Math.min(idx, 200);
  idx = text.indexOf(tk);
  if (idx >= 0) return 460 - Math.min(idx, 200);
  if (subseq(tk, text)) return 130;
  return 0;
}
function scoreCmd(q: string, c: Cmd): number {
  const title = c.title.toLowerCase();
  const text = `${c.title} ${c.subtitle || ""} ${c.keywords || ""}`.toLowerCase();
  let total = 0;
  for (const tk of q.split(/\s+/).filter(Boolean)) {
    const s = tokenScore(tk, title, text);
    if (s <= 0) return 0;
    total += s;
  }
  return total;
}
// Scoped матчится только если запрос покрывает И компанию, И модуль —
// каждый токен относим к той части, где совпадение сильнее. Один токен
// → не может покрыть обе части → scoped скрыт (нет «затопления» при «навои»).
function scoreScoped(qTokens: string[], c: ScopedCmd): number {
  let coTotal = 0, modTotal = 0, coHit = false, modHit = false;
  for (const tk of qTokens) {
    const sc = tokenScore(tk, c.companyTitle, c.companyText);
    const sm = tokenScore(tk, c.moduleLabel, c.moduleText);
    if (sc === 0 && sm === 0) return 0;
    if (sc >= sm) { coHit = true; coTotal += sc; } else { modHit = true; modTotal += sm; }
  }
  if (!coHit || !modHit) return 0;
  return coTotal + modTotal + 250;
}

const displayGroups = computed<{ name: string; items: Cmd[] }[]>(() => {
  const q = query.value.trim().toLowerCase();
  if (!q) {
    const groups: { name: string; items: Cmd[] }[] = [];
    const rec = recentCommands.value;
    if (rec.length) groups.push({ name: "Недавнее", items: rec });
    const recSet = new Set(rec.map((c) => c.id));
    const sugg = navCommands.value.filter((c) => !recSet.has(c.id)).slice(0, 7);
    if (sugg.length) groups.push({ name: "Быстрый переход", items: sugg });
    return groups;
  }
  const pool = [...navCommands.value, ...companyCommands.value, ...actionCommands.value];
  const byG = new Map<string, { c: Cmd; s: number }[]>();
  for (const c of pool) {
    const s = scoreCmd(q, c);
    if (s > 0) { if (!byG.has(c.group)) byG.set(c.group, []); byG.get(c.group)!.push({ c, s }); }
  }
  // scoped: компания + раздел (только при совпадении обеих частей запроса)
  const qTokens = q.split(/\s+/).filter(Boolean);
  for (const c of scopedCommands.value) {
    const s = scoreScoped(qTokens, c);
    if (s > 0) { if (!byG.has(c.group)) byG.set(c.group, []); byG.get(c.group)!.push({ c, s }); }
  }
  const groups = [...byG.entries()].map(([name, items]) => {
    items.sort((a, b) => b.s - a.s);
    return { name, items: items.slice(0, 8).map((i) => i.c), best: items[0].s };
  });
  groups.sort((a, b) => b.best - a.best);
  const out = groups.map((g) => ({ name: g.name, items: g.items }));
  if (aiCommand.value) out.push({ name: "AI", items: [aiCommand.value] });
  return out;
});

const flat = computed<Cmd[]>(() => displayGroups.value.flatMap((g) => g.items));
const rows = computed(() => {
  const r: Array<{ type: "header"; name: string } | { type: "item"; cmd: Cmd; index: number }> = [];
  let idx = 0;
  for (const g of displayGroups.value) {
    r.push({ type: "header", name: g.name });
    for (const c of g.items) { r.push({ type: "item", cmd: c, index: idx }); idx++; }
  }
  return r;
});

watch(query, () => { selected.value = 0; });

// ─── Управление ───
function openPalette() {
  open.value = true; query.value = ""; selected.value = 0;
  loadCompanies();
  nextTick(() => inputEl.value?.focus());
}
function close() { open.value = false; }
function toggle() { open.value ? close() : openPalette(); }

function move(d: number) {
  const n = flat.value.length;
  if (!n) return;
  selected.value = (selected.value + d + n) % n;
  nextTick(() => {
    const el = listEl.value?.querySelector<HTMLElement>(`[data-i="${selected.value}"]`);
    el?.scrollIntoView({ block: "nearest" });
  });
}
function exec(c: Cmd) {
  if (c.kind !== "ai") pushRecent(c.id);
  c.run();
}
function onKeydown(e: KeyboardEvent) {
  if (e.key === "ArrowDown") { e.preventDefault(); move(1); }
  else if (e.key === "ArrowUp") { e.preventDefault(); move(-1); }
  else if (e.key === "Enter") { e.preventDefault(); const c = flat.value[selected.value]; if (c) exec(c); }
  else if (e.key === "Escape") { e.preventDefault(); close(); }
}

function onGlobalKey(e: KeyboardEvent) {
  if ((e.metaKey || e.ctrlKey) && (e.key === "k" || e.key === "K")) { e.preventDefault(); toggle(); }
}
function onOpenEvent() { openPalette(); }
onMounted(() => {
  window.addEventListener("keydown", onGlobalKey);
  window.addEventListener("uza:command-palette", onOpenEvent as EventListener);
});
onBeforeUnmount(() => {
  window.removeEventListener("keydown", onGlobalKey);
  window.removeEventListener("uza:command-palette", onOpenEvent as EventListener);
});
</script>

<template>
  <Teleport to="body">
    <Transition name="cmdk">
      <div v-if="open" class="cmdk-overlay" @click.self="close" @keydown="onKeydown">
        <div class="cmdk-panel" role="dialog" aria-label="Командная палитра">
          <!-- Search row -->
          <div class="cmdk-search">
            <svg class="cmdk-search-ic" width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="11" cy="11" r="7"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg>
            <input
              ref="inputEl" v-model="query" type="text"
              class="cmdk-input" placeholder="Куда перейти или что сделать…"
              autocomplete="off" spellcheck="false"
              @keydown="onKeydown"
            />
            <kbd class="cmdk-esc">esc</kbd>
          </div>

          <!-- Results -->
          <div ref="listEl" class="cmdk-list">
            <template v-if="flat.length">
              <template v-for="(row, ri) in rows" :key="ri">
                <div v-if="row.type === 'header'" class="cmdk-group">{{ row.name }}</div>
                <button
                  v-else
                  class="cmdk-item"
                  :class="{ sel: row.index === selected }"
                  :data-i="row.index"
                  @click="exec(row.cmd)"
                  @mousemove="selected = row.index"
                >
                  <span class="cmdk-ic" :class="'k-' + row.cmd.kind">
                    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" v-html="ICONS[row.cmd.icon] || ICONS.dot"></svg>
                  </span>
                  <span class="cmdk-txt">
                    <span class="cmdk-title">{{ row.cmd.title }}</span>
                    <span v-if="row.cmd.subtitle" class="cmdk-sub">{{ row.cmd.subtitle }}</span>
                  </span>
                  <span v-if="row.cmd.kind === 'ai'" class="cmdk-tag">AI</span>
                  <span v-else-if="row.cmd.kind === 'company'" class="cmdk-tag co">Компания</span>
                  <span v-else-if="row.cmd.kind === 'scoped'" class="cmdk-tag sc">Раздел</span>
                  <svg v-if="row.index === selected" class="cmdk-enter" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="9 10 4 15 9 20"/><path d="M20 4v7a4 4 0 0 1-4 4H4"/></svg>
                </button>
              </template>
            </template>
            <div v-else class="cmdk-empty">
              <svg width="26" height="26" viewBox="0 0 24 24" fill="none" stroke="#C7CCD9" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><circle cx="11" cy="11" r="7"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg>
              <span>Ничего не найдено по «{{ query }}»</span>
            </div>
          </div>

          <!-- Footer hints -->
          <div class="cmdk-foot">
            <span><kbd>↑</kbd><kbd>↓</kbd> навигация</span>
            <span><kbd>↵</kbd> выбрать</span>
            <span><kbd>esc</kbd> закрыть</span>
            <span class="cmdk-foot-r">{{ isMac ? "⌘K" : "Ctrl K" }}</span>
          </div>
        </div>
      </div>
    </Transition>
  </Teleport>
</template>

<style scoped>
.cmdk-overlay {
  position: fixed; inset: 0; z-index: 10000;
  background: rgba(15, 18, 40, .45); backdrop-filter: blur(8px);
  display: flex; align-items: flex-start; justify-content: center;
  padding: 14vh 16px 16px;
  --ease: cubic-bezier(.34, 1.2, .64, 1);
}
.cmdk-panel {
  width: 100%; max-width: 600px; max-height: 70vh;
  background: #fff; border-radius: 16px; overflow: hidden;
  display: flex; flex-direction: column;
  box-shadow: 0 32px 80px rgba(15, 23, 60, .32), 0 8px 24px rgba(15, 23, 60, .14);
  border: 1px solid rgba(255, 255, 255, .6);
}

/* Search */
.cmdk-search { display: flex; align-items: center; gap: 11px; padding: 15px 17px; border-bottom: 1px solid rgba(15, 23, 60, .07); }
.cmdk-search-ic { color: var(--p-deep, #534AB7); flex-shrink: 0; }
.cmdk-input { flex: 1; border: none; outline: none; background: transparent; font-size: 15px; font-weight: 500; color: var(--t1, #1E2A4A); letter-spacing: -.01em; }
.cmdk-input::placeholder { color: #B0B6C3; font-weight: 400; }
.cmdk-esc { font-size: 10px; font-weight: 600; color: var(--t3, #94A3B8); background: rgba(15, 23, 60, .05); border-radius: 6px; padding: 3px 7px; letter-spacing: .03em; }

/* List */
.cmdk-list { overflow-y: auto; padding: 7px; scrollbar-width: thin; }
.cmdk-list::-webkit-scrollbar { width: 7px; }
.cmdk-list::-webkit-scrollbar-thumb { background: rgba(15, 23, 60, .14); border-radius: 4px; }
.cmdk-group { font-size: 9.5px; font-weight: 600; text-transform: uppercase; letter-spacing: .08em; color: var(--t3, #94A3B8); padding: 11px 11px 5px; }
.cmdk-item {
  display: flex; align-items: center; gap: 12px; width: 100%;
  padding: 9px 11px; border: none; background: transparent; border-radius: 10px;
  cursor: pointer; text-align: left; font-family: inherit; position: relative;
  transition: background .12s var(--ease);
}
.cmdk-item.sel { background: rgba(127, 119, 221, .10); }
.cmdk-item.sel::before {
  content: ""; position: absolute; left: 0; top: 50%; transform: translateY(-50%);
  width: 3px; height: 18px; border-radius: 0 3px 3px 0;
  background: linear-gradient(180deg, #7F77DD, #B5AEEC);
}
.cmdk-ic {
  width: 30px; height: 30px; border-radius: 8px; flex-shrink: 0;
  display: flex; align-items: center; justify-content: center;
  background: rgba(15, 23, 60, .05); color: var(--t2, #475569);
  transition: background .12s, color .12s, transform .12s var(--ease);
}
.cmdk-item.sel .cmdk-ic { transform: scale(1.05); }
.cmdk-ic.k-nav { color: #534AB7; }
.cmdk-item.sel .cmdk-ic.k-nav { background: rgba(127, 119, 221, .16); }
.cmdk-ic.k-company { color: #378ADD; }
.cmdk-item.sel .cmdk-ic.k-company { background: rgba(55, 138, 221, .14); }
.cmdk-ic.k-action { color: #1D9E75; }
.cmdk-item.sel .cmdk-ic.k-action { background: rgba(29, 158, 117, .14); }
.cmdk-ic.k-ai { color: #fff; background: linear-gradient(135deg, #8B7FF0, #534AB7); }
.cmdk-ic.k-scoped { color: #7F77DD; }
.cmdk-item.sel .cmdk-ic.k-scoped { background: rgba(127, 119, 221, .16); }
.cmdk-txt { flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 1px; }
.cmdk-title { font-size: 13.5px; font-weight: 500; color: var(--t1, #1E2A4A); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.cmdk-sub { font-size: 11px; color: var(--t3, #94A3B8); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.cmdk-tag { font-size: 9px; font-weight: 600; text-transform: uppercase; letter-spacing: .05em; color: var(--p-deep, #534AB7); background: rgba(127, 119, 221, .12); border-radius: 5px; padding: 2px 6px; flex-shrink: 0; }
.cmdk-tag.co { color: #2B6CB0; background: rgba(55, 138, 221, .12); }
.cmdk-tag.sc { color: #534AB7; background: rgba(127, 119, 221, .12); }
.cmdk-enter { color: var(--p-deep, #534AB7); flex-shrink: 0; opacity: .7; }
.cmdk-empty { display: flex; flex-direction: column; align-items: center; gap: 10px; padding: 44px 20px; color: var(--t3, #94A3B8); font-size: 13px; text-align: center; }

/* Footer */
.cmdk-foot { display: flex; align-items: center; gap: 16px; padding: 9px 15px; border-top: 1px solid rgba(15, 23, 60, .07); font-size: 11px; color: var(--t3, #94A3B8); }
.cmdk-foot span { display: inline-flex; align-items: center; gap: 5px; }
.cmdk-foot-r { margin-left: auto; font-weight: 600; }
.cmdk-foot kbd { font-size: 10px; font-weight: 600; color: var(--t2, #475569); background: rgba(15, 23, 60, .05); border-radius: 5px; padding: 2px 6px; min-width: 18px; text-align: center; font-family: inherit; }

/* Transition */
.cmdk-enter-active, .cmdk-leave-active { transition: opacity .2s var(--ease); }
.cmdk-enter-active .cmdk-panel { transition: transform .28s var(--ease); }
.cmdk-leave-active .cmdk-panel { transition: transform .16s; }
.cmdk-enter-from { opacity: 0; }
.cmdk-enter-from .cmdk-panel { transform: translateY(-14px) scale(.97); }
.cmdk-leave-to { opacity: 0; }
.cmdk-leave-to .cmdk-panel { transform: scale(.98); }

@media (max-width: 600px) {
  .cmdk-overlay { padding: 8vh 10px 10px; }
  .cmdk-foot span:not(.cmdk-foot-r) { display: none; }
}
@media (prefers-reduced-motion: reduce) {
  .cmdk-enter-active .cmdk-panel, .cmdk-leave-active .cmdk-panel { transition: none; }
}
</style>
