<script setup lang="ts">
import { ref, computed, onMounted, watch } from 'vue';
import { auditApi } from '@/api/rbacV3';
import type { RbacV3AuditEvent, RbacV3AuditEventDetail } from '@/api/rbacV3';
import UserAvatar from '@/components/rbac-v3/UserAvatar.vue';
import { useFormatters } from '@/composables/useFormatters';

const fmt = useFormatters();

const events = ref<RbacV3AuditEvent[]>([]);
const total = ref(0);
const loading = ref(false);
const error = ref<string | null>(null);

// Filters
type Period = 24 | 168 | 720 | 0;  // 0 = all
const period = ref<Period>(24);
const moduleFilter = ref<string>('');
const onlyCritical = ref(false);
const search = ref('');
const page = ref(1);

// Anti-spam controls (Pack 11.x extension)
type SortMode = 'newest' | 'oldest' | 'severity' | 'actor';
const sortMode = ref<SortMode>('newest');
const groupSimilar = ref(true);           // collapse consecutive same actor+action+entity
const hideInfo = ref(true);               // по умолчанию скрываем просмотры (VIEW/info) — фокус на изменениях

// Фильтр по пользователю (server-side, по всем страницам) — клик по актору в ленте
// или выбор из выпадающего списка.
const actorFilter = ref<string>('');

// Быстрые чипы-категории (клиентские, мгновенные) — по паттерну action.
type QuickCat = 'all' | 'logins' | 'access' | 'data' | 'deletions';
const quickCat = ref<QuickCat>('all');
const QUICK_CHIPS: { key: QuickCat; label: string }[] = [
  { key: 'all',       label: 'Все' },
  { key: 'logins',    label: 'Входы и сессии' },
  { key: 'access',    label: 'Доступы и роли' },
  { key: 'data',      label: 'Изменения данных' },
  { key: 'deletions', label: 'Удаления' },
];
function actionCategory(a: string): QuickCat | null {
  if (/login|logout|session|mfa|auth|telegram\.(link|unlink)/i.test(a)) return 'logins';
  if (/role|permission|group|user\.(assign|remove|create|invite|delete|deactivate|activate|update|unlock)|email_rule/i.test(a)) return 'access';
  if (/delete|revoke|deactivate|delete_permanent/i.test(a)) return 'deletions';
  if (/create|update|change|grant|assign|import|edit|approve|reject/i.test(a)) return 'data';
  return null;
}

const MODULES = [
  '', 'rbac', 'users', 'roles', 'kpi', 'bp', 'credit', 'invest',
  'procurement', 'esg', 'governance', 'auth', 'admin'
];

async function load() {
  loading.value = true;
  error.value = null;
  try {
    const resp = await auditApi.list({
      hours: period.value || undefined,
      module: moduleFilter.value || undefined,
      actor_email: actorFilter.value || undefined,
      action_category: quickCat.value !== 'all' ? quickCat.value : undefined,
      only_critical: onlyCritical.value || undefined,
      search: search.value.trim() || undefined,
      page: page.value,
      per_page: 50,
    });
    events.value = resp.items;
    total.value = resp.total;
  } catch (e: any) {
    error.value = e?.response?.data?.detail || 'Не удалось загрузить журнал';
  } finally {
    loading.value = false;
  }
}
onMounted(load);
watch([period, moduleFilter, onlyCritical, actorFilter, quickCat], () => { page.value = 1; load(); });

// Список пользователей для выпадающего фильтра — distinct по загруженным событиям.
const actorOptions = computed(() => {
  const m = new Map<string, string>(); // email → отображаемое имя
  for (const e of events.value) {
    if (e.actor_email && !m.has(e.actor_email)) m.set(e.actor_email, actorName(e));
  }
  return Array.from(m.entries()).map(([email, name]) => ({ email, name }))
    .sort((a, b) => a.name.localeCompare(b.name, 'ru'));
});
function filterByActor(e: RbacV3AuditEvent) {
  if (!e.actor_email) return;
  actorFilter.value = actorFilter.value === e.actor_email ? '' : e.actor_email;
}
const actorFilterName = computed(() => {
  if (!actorFilter.value) return '';
  const hit = events.value.find(e => e.actor_email === actorFilter.value);
  return hit ? actorName(hit) : actorFilter.value;
});

let searchTimer: any = null;
function onSearchInput() {
  if (searchTimer) clearTimeout(searchTimer);
  searchTimer = setTimeout(() => { page.value = 1; load(); }, 300);
}

// ─── Helpers ────────────────────────────────────────────────────

function fmtRelative(s: string): string {
  const diff = (Date.now() - new Date(s).getTime()) / 1000;
  if (diff < 60) return 'только что';
  if (diff < 3600) return Math.floor(diff / 60) + ' мин';
  if (diff < 86400) return Math.floor(diff / 3600) + ' ч';
  const days = Math.floor(diff / 86400);
  if (days === 1) return 'вчера';
  if (days < 30) return days + ' дн';
  return Math.floor(days / 30) + ' мес';
}

function fmtAbsolute(s: string): string {
  return fmt.fmtDateTime(s);
}

interface Severity { color: string; label: string; ru: string; }

function severity(e: RbacV3AuditEvent): Severity {
  if (e.is_critical || /delete|delete_permanent|revoke|deactivate/i.test(e.action))
    return { color: '#E24B4A', label: 'critical', ru: 'Важное' };
  if (/update|change|grant|assign|create|import|approve|reject/i.test(e.action))
    return { color: '#EF9F27', label: 'warning', ru: 'Изменение' };
  return { color: '#888780', label: 'info', ru: 'Просмотр' };
}

// Русские названия модулей — «где» произошло событие (вместо слага kpi/bp/...).
const MODULE_LABELS: Record<string, string> = {
  rbac: 'Доступы', users: 'Пользователи', roles: 'Роли', groups: 'Группы',
  kpi: 'KPI', bp: 'Бизнес-план', business_plan: 'Бизнес-план',
  credit: 'Кредитный портфель', finance: 'Финансы', financials: 'Финансы',
  invest: 'Инвест-проекты', investment: 'Инвест-проекты',
  procurement: 'Закупки', esg: 'ESG', governance: 'Корп. управление',
  ratings: 'Рейтинги', companies: 'Компании', tasks: 'Задачи',
  auth: 'Вход и сессии', admin: 'Администрирование', moderation: 'Модерация',
  notification: 'Уведомления',
};
function moduleLabel(m: string | null): string {
  if (!m) return '';
  return MODULE_LABELS[m] || m;
}

// Читаемое «где» из http_path, когда модуль/объект не определены: первые
// смысловые сегменты пути → раздел (по словарю), убираем /api, id-сегменты.
const PATH_SECTION: Record<string, string> = {
  'rbac-v3': 'Доступы', rbac: 'Доступы', users: 'Пользователи', roles: 'Роли',
  groups: 'Группы', audit: 'Журнал аудита', companies: 'Компании', company: 'Компании',
  kpi: 'KPI', bp: 'Бизнес-план', 'business-plan': 'Бизнес-план', financials: 'Финансы',
  credit: 'Кредитный портфель', 'credit-portfolio': 'Кредитный портфель',
  procurement: 'Закупки', esg: 'ESG', governance: 'Корп. управление', ratings: 'Рейтинги',
  tasks: 'Задачи', projects: 'Проекты', notifications: 'Уведомления',
  moderation: 'Модерация', admin: 'Администрирование', dashboard: 'Дашборд',
  'invest-projects': 'Инвест-проекты', consultants: 'Консультанты',
  auth: 'Вход и сессии', presence: 'Присутствие', watches: 'Отслеживание',
  calendar: 'Календарь', settings: 'Настройки',
};
function prettyPath(path: string | null): string {
  if (!path) return '';
  const segs = path.split('?')[0].split('/').filter(s => s && s !== 'api' && s !== 'v1');
  for (const s of segs) {
    if (PATH_SECTION[s]) return PATH_SECTION[s];
  }
  // первый не-id сегмент
  const first = segs.find(s => !/^[0-9a-f-]{8,}$/i.test(s) && !/^\d+$/.test(s));
  return first || '';
}

// «Где» — модуль (рус.) + объект; при отсутствии — раздел из http_path.
function whereText(e: RbacV3AuditEvent): string {
  const mod = moduleLabel(e.module);
  const ent = e.entity_label || '';
  if (mod && ent) return `${mod} · ${ent}`;
  if (mod) return mod;
  if (ent) return ent;
  return prettyPath(e.http_path);
}

// Имя актора из email (локальная часть, до @) — дружелюбнее сырого email.
function actorName(e: RbacV3AuditEvent): string {
  if (!e.actor_email) return 'Система';
  const local = e.actor_email.split('@')[0];
  return local.split(/[._-]/).map(p => p ? p[0].toUpperCase() + p.slice(1) : p).join(' ');
}

// Human-readable description of event (expanded — больше action-cases)
function describe(e: RbacV3AuditEvent): string {
  const a = e.action;
  const entity = e.entity_label || e.entity_type || '';
  const mod = e.module || '';

  // ─── Users ─────────────────────────────────────────────────────
  if (a === 'user.create' || a === 'user.invite')        return `пригласил(а) пользователя ${entity}`;
  if (a === 'user.delete_permanent')                     return `удалил(а) пользователя навсегда: ${entity}`;
  if (a === 'user.deactivate' || a === 'user.disable')   return `деактивировал(а) пользователя ${entity}`;
  if (a === 'user.activate'   || a === 'user.enable')    return `активировал(а) пользователя ${entity}`;
  if (a === 'user.update')                               return `изменил(а) данные пользователя ${entity}`;
  if (a === 'user.password_reset')                       return `сбросил(а) пароль ${entity}`;
  if (a === 'user.password_change')                      return `сменил(а) свой пароль`;
  if (a === 'user.email_change')                         return `сменил(а) email на ${entity}`;
  if (a === 'user.assign_role' || a === 'role.assign')   return `назначил(а) роль «${entity}»`;
  if (a === 'user.remove_role' || a === 'role.unassign') return `убрал(а) роль «${entity}»`;
  if (a === 'user.assign_group' || a === 'group.assign') return `добавил(а) в группу «${entity}»`;
  if (a === 'user.remove_group' || a === 'group.unassign') return `убрал(а) из группы «${entity}»`;
  if (a === 'user.unlock')                               return `разблокировал(а) пользователя ${entity}`;

  // ─── Roles ─────────────────────────────────────────────────────
  if (a === 'role.create')                               return `создал(а) роль «${entity}»`;
  if (a === 'role.delete')                               return `удалил(а) роль «${entity}»`;
  if (a === 'role.update' || a === 'role.rename')        return `переименовал(а) роль «${entity}»`;
  if (a === 'role.update_permissions' || a === 'role.permissions_changed')
                                                         return `изменил(а) разрешения роли «${entity}»`;
  if (a === 'role.clone')                                return `клонировал(а) роль «${entity}»`;

  // ─── Groups ────────────────────────────────────────────────────
  if (a === 'group.create')                              return `создал(а) группу «${entity}»`;
  if (a === 'group.delete')                              return `удалил(а) группу «${entity}»`;
  if (a === 'group.update_members')                      return `изменил(а) состав группы «${entity}»`;
  if (a === 'group.update_permissions')                  return `изменил(а) разрешения группы «${entity}»`;
  if (a === 'group.update')                              return `изменил(а) группу «${entity}»`;

  // ─── Permissions ───────────────────────────────────────────────
  if (a === 'permission.grant')                          return `выдал(а) разрешение «${entity}»`;
  if (a === 'permission.revoke')                         return `отозвал(а) разрешение «${entity}»`;

  // ─── Email rules ───────────────────────────────────────────────
  if (a === 'email_rule.create')                         return `создал(а) email-правило ${entity}`;
  if (a === 'email_rule.delete')                         return `удалил(а) email-правило ${entity}`;
  if (a === 'email_rule.update')                         return `изменил(а) email-правило ${entity}`;

  // ─── Auth / sessions ───────────────────────────────────────────
  if (a === 'auth.login.success' || a === 'login.success')        return `успешный вход в систему`;
  if (a === 'auth.login.failed'  || a === 'login.failed')         return `неудачная попытка входа${entity ? ' (' + entity + ')' : ''}`;
  if (a === 'auth.logout' || a === 'logout')                      return `вышел(а) из системы`;
  if (a === 'auth.token.refresh')                                 return `обновил(а) токен сессии`;
  if (a === 'auth.session.terminate')                             return `завершил(а) сессию ${entity}`;
  if (a === 'auth.session.terminate_all')                         return `завершил(а) все сессии пользователя ${entity}`;

  // ─── MFA ──────────────────────────────────────────────────────
  if (a === 'mfa.enabled')                               return `включил(а) MFA`;
  if (a === 'mfa.disabled')                              return `отключил(а) MFA`;
  if (a === 'mfa.reset' || a === 'mfa.admin_reset')      return `сбросил(а) MFA пользователю ${entity}`;
  if (a === 'mfa.verify.success')                        return `успешная MFA-верификация`;
  if (a === 'mfa.verify.failed')                         return `неудачная MFA-верификация`;
  if (a === 'mfa.recovery.used')                         return `использовал(а) recovery-код`;

  // ─── Telegram link ─────────────────────────────────────────────
  if (a === 'telegram.link')                             return `привязал(а) Telegram`;
  if (a === 'telegram.unlink')                           return `отвязал(а) Telegram`;

  // ─── Companies / KPI / BP / Финансы ────────────────────────────
  if (a === 'company.create')                            return `создал(а) компанию «${entity}»`;
  if (a === 'company.update')                            return `изменил(а) компанию «${entity}»`;
  if (a === 'company.delete')                            return `удалил(а) компанию «${entity}»`;
  if (a === 'kpi.import')                                return `импортировал(а) KPI «${entity}»`;
  if (a === 'kpi.update' || a === 'kpi.edit')            return `изменил(а) KPI «${entity}»`;
  if (a === 'kpi.delete')                                return `удалил(а) KPI «${entity}»`;
  if (a === 'bp.import')                                 return `импортировал(а) Бизнес-план «${entity}»`;
  if (a === 'bp.update'  || a === 'bp.edit')             return `изменил(а) Бизнес-план «${entity}»`;
  if (a === 'financials.import')                         return `импортировал(а) финансовый отчёт «${entity}»`;
  if (a === 'financials.update')                         return `изменил(а) финансовый отчёт «${entity}»`;

  // ─── Moderation ────────────────────────────────────────────────
  if (a === 'moderation.approve')                        return `одобрил(а) на модерации «${entity}»`;
  if (a === 'moderation.reject')                         return `отклонил(а) на модерации «${entity}»`;
  if (a === 'moderation.return')                         return `вернул(а) на доработку «${entity}»`;

  // ─── Notifications / Broadcasts ────────────────────────────────
  if (a === 'broadcast.send')                            return `отправил(а) рассылку «${entity}»`;
  if (a === 'notification.test')                         return `отправил(а) тестовое уведомление`;

  // ─── Generic HTTP-verb actions (из audit-middleware) ───────────
  // VIEW/CREATE/UPDATE/DELETE без конкретной сущности — гуманизируем глагол,
  // «где» (раздел из пути) показывается отдельной строкой whereText().
  const GENERIC: Record<string, string> = {
    VIEW: 'открыл(а)', GET: 'открыл(а)',
    CREATE: 'создал(а) запись', POST: 'создал(а) запись',
    UPDATE: 'изменил(а)', PUT: 'изменил(а)', PATCH: 'изменил(а)',
    DELETE: 'удалил(а) запись',
  };
  if (GENERIC[a]) {
    const loc = entity || prettyPath(e.http_path);
    if (a === 'VIEW' || a === 'GET') return loc ? `открыл(а) раздел «${loc}»` : 'открыл(а) страницу';
    return loc ? `${GENERIC[a]} в разделе «${loc}»` : GENERIC[a];
  }

  // ─── Fallback: action + module + entity ────────────────────────
  return `${a}${entity ? ': ' + entity : ''}${mod ? ' [' + mod + ']' : ''}`;
}

// ───────────────────────────────────────────────────────────────
// Anti-spam grouping: collapse consecutive identical events
// (same actor + same action + same entity within BURST_WINDOW)
// ───────────────────────────────────────────────────────────────
interface ProcessedEvent extends RbacV3AuditEvent {
  burstCount: number;       // 1 = single, >1 = collapsed N consecutive
  burstFirstAt?: string;    // earliest timestamp in burst
  burstLastAt?: string;     // latest timestamp in burst
}

const BURST_WINDOW_MS = 60_000; // 1 minute

function _burstKey(e: RbacV3AuditEvent): string {
  return `${e.actor_id || 'sys'}|${e.action}|${e.entity_id || e.entity_label || ''}`;
}

const processedEvents = computed<ProcessedEvent[]>(() => {
  let arr: ProcessedEvent[] = events.value.map(e => ({ ...e, burstCount: 1 }));

  // Quick-chip категория — теперь server-side (action_category), здесь не фильтруем.

  // Filter: hide info-level
  if (hideInfo.value) {
    arr = arr.filter(e => severity(e).label !== 'info');
  }

  // Group similar (only meaningful when sorted chronologically)
  if (groupSimilar.value && (sortMode.value === 'newest' || sortMode.value === 'oldest')) {
    // Sort by time first (newest desc → so consecutive events of burst are adjacent)
    arr.sort((a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime());
    const out: ProcessedEvent[] = [];
    for (const e of arr) {
      const last = out[out.length - 1];
      if (last && _burstKey(last) === _burstKey(e)) {
        const lastT = new Date(last.created_at).getTime();
        const eT = new Date(e.created_at).getTime();
        if (Math.abs(lastT - eT) < BURST_WINDOW_MS * last.burstCount + BURST_WINDOW_MS) {
          last.burstCount++;
          last.burstFirstAt = e.created_at;          // earlier
          last.burstLastAt = last.burstLastAt || last.created_at;
          continue;
        }
      }
      out.push(e);
    }
    arr = out;
    if (sortMode.value === 'oldest') arr.reverse();
  } else {
    // Sort modes
    if (sortMode.value === 'newest') {
      arr.sort((a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime());
    } else if (sortMode.value === 'oldest') {
      arr.sort((a, b) => new Date(a.created_at).getTime() - new Date(b.created_at).getTime());
    } else if (sortMode.value === 'severity') {
      const sevRank: Record<string, number> = { critical: 0, warning: 1, info: 2 };
      arr.sort((a, b) => sevRank[severity(a).label] - sevRank[severity(b).label]
                          || new Date(b.created_at).getTime() - new Date(a.created_at).getTime());
    } else if (sortMode.value === 'actor') {
      arr.sort((a, b) =>
        (a.actor_email || '').localeCompare(b.actor_email || '', 'ru')
        || new Date(b.created_at).getTime() - new Date(a.created_at).getTime()
      );
    }
  }

  return arr;
});

// ─── Detail rendering helpers (diff as before/after pairs) ───
function formatValue(v: any): string {
  if (v === null || v === undefined) return '∅';
  if (typeof v === 'boolean') return v ? 'да' : 'нет';
  if (typeof v === 'string') return v.length > 80 ? v.slice(0, 77) + '...' : v;
  if (typeof v === 'number') return v.toLocaleString('ru-RU');
  if (Array.isArray(v)) return `[${v.length}]: ` + v.slice(0, 3).map(x => typeof x === 'object' ? '...' : String(x)).join(', ');
  if (typeof v === 'object') return JSON.stringify(v);
  return String(v);
}

interface DiffRow { field: string; before: any; after: any; }

function diffRows(diff: any): DiffRow[] {
  if (!diff || typeof diff !== 'object') return [];
  // Two common formats: {"field": {"before": x, "after": y}} OR {"before": {...}, "after": {...}}
  if (diff.before !== undefined && diff.after !== undefined) {
    const keys = new Set<string>([
      ...Object.keys(diff.before || {}),
      ...Object.keys(diff.after  || {}),
    ]);
    return Array.from(keys).map(k => ({
      field: k,
      before: (diff.before || {})[k],
      after:  (diff.after  || {})[k],
    }));
  }
  // Otherwise: per-field {before, after}
  return Object.entries(diff).map(([field, val]: [string, any]) => ({
    field,
    before: val?.before ?? val?.from ?? null,
    after:  val?.after  ?? val?.to   ?? null,
  }));
}

// Detail expansion
const expandedId = ref<string | null>(null);
const detailCache = ref<Record<string, RbacV3AuditEventDetail>>({});
const detailLoading = ref<string | null>(null);

async function toggleDetail(id: string) {
  if (expandedId.value === id) { expandedId.value = null; return; }
  expandedId.value = id;
  if (!detailCache.value[id]) {
    detailLoading.value = id;
    try {
      detailCache.value[id] = await auditApi.get(id);
    } catch (e) {
      console.error(e);
    } finally {
      detailLoading.value = null;
    }
  }
}

function exportCsv() {
  const url = auditApi.exportCsvUrl({
    hours: period.value || undefined,
    module: moduleFilter.value || undefined,
    actor_email: actorFilter.value || undefined,
    action_category: quickCat.value !== 'all' ? quickCat.value : undefined,
    only_critical: onlyCritical.value || undefined,
    search: search.value.trim() || undefined,
  });
  window.open(url, '_blank');
}

// Group events by day for date-headers in feed (operates on processedEvents)
const grouped = computed(() => {
  const groups: { date: string; label: string; events: ProcessedEvent[] }[] = [];
  const today = new Date(); today.setHours(0, 0, 0, 0);
  const yesterday = new Date(today); yesterday.setDate(yesterday.getDate() - 1);

  for (const e of processedEvents.value) {
    const d = new Date(e.created_at);
    const key = d.toISOString().slice(0, 10);
    let group = groups.find(g => g.date === key);
    if (!group) {
      let label: string;
      const day = new Date(d); day.setHours(0, 0, 0, 0);
      if (day.getTime() === today.getTime()) label = 'Сегодня';
      else if (day.getTime() === yesterday.getTime()) label = 'Вчера';
      else label = day.toLocaleDateString('ru-RU', { day: '2-digit', month: 'long', year: 'numeric' });
      group = { date: key, label, events: [] };
      groups.push(group);
    }
    group.events.push(e);
  }
  return groups;
});

// Сводка по текущей выборке — контекст «сколько / кто / насколько важно».
const summary = computed(() => {
  const actors = new Set<string>();
  let critical = 0;
  for (const e of events.value) {
    if (e.actor_email) actors.add(e.actor_email);
    if (severity(e).label === 'critical') critical++;
  }
  return { total: total.value, actors: actors.size, critical };
});
const periodLabel = computed(() => ({ 24: 'за сутки', 168: 'за 7 дней', 720: 'за 30 дней', 0: 'за всё время' }[period.value] || ''));

const hasMorePages = computed(() => events.value.length === 50 && events.value.length < total.value);
function nextPage() { page.value++; load(); }
function prevPage() { if (page.value > 1) { page.value--; load(); } }
</script>

<template>
  <div class="rv3-audit-shell">
    <!-- LEFT: filters sidebar -->
    <div class="rv3-au-filters">
      <div class="rv3-au-section-title">Период</div>
      <div class="rv3-au-period-list">
        <button :class="['rv3-au-period', { on: period === 24 }]"  @click="period = 24">Сутки</button>
        <button :class="['rv3-au-period', { on: period === 168 }]" @click="period = 168">7 дней</button>
        <button :class="['rv3-au-period', { on: period === 720 }]" @click="period = 720">30 дней</button>
        <button :class="['rv3-au-period', { on: period === 0 }]"   @click="period = 0">Всё</button>
      </div>

      <div class="rv3-au-section-title" style="margin-top:18px">Модуль</div>
      <select v-model="moduleFilter" class="rv3-au-select">
        <option v-for="m in MODULES" :key="m" :value="m">{{ m ? moduleLabel(m) : 'Все модули' }}</option>
      </select>

      <div class="rv3-au-section-title" style="margin-top:18px">Пользователь</div>
      <select v-model="actorFilter" class="rv3-au-select">
        <option value="">Все пользователи</option>
        <option v-for="a in actorOptions" :key="a.email" :value="a.email">{{ a.name }}</option>
      </select>
      <div class="rv3-au-hint">Или кликните по имени в ленте</div>

      <div class="rv3-au-section-title" style="margin-top:18px">Серьёзность</div>
      <label class="rv3-au-cb">
        <input type="checkbox" v-model="onlyCritical" />
        <span class="rv3-au-sw" style="background:#E24B4A"></span>
        <span>Только critical</span>
      </label>
      <label class="rv3-au-cb" style="margin-top:6px" title="Скрывает события-просмотры (открытие страниц), оставляя только изменения">
        <input type="checkbox" v-model="hideInfo" />
        <span class="rv3-au-sw" style="background:#888780"></span>
        <span>Скрыть просмотры</span>
      </label>

      <!-- Sort + grouping (anti-spam) -->
      <div class="rv3-au-section-title" style="margin-top:18px">Сортировка</div>
      <select v-model="sortMode" class="rv3-au-select">
        <option value="newest">Сначала новые</option>
        <option value="oldest">Сначала старые</option>
        <option value="severity">По серьёзности</option>
        <option value="actor">По пользователю</option>
      </select>
      <label class="rv3-au-cb" style="margin-top:10px" title="Объединяет одинаковые подряд идущие действия одного пользователя">
        <input type="checkbox" v-model="groupSimilar" />
        <span class="rv3-au-sw" style="background:#7F77DD"></span>
        <span>Группировать похожие</span>
      </label>

      <button class="rv3-au-export" @click="exportCsv">
        <svg width="11" height="11" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M8 3v10M4 7l4-4 4 4M3 13h10"/></svg>
        Экспорт в CSV
      </button>
    </div>

    <!-- RIGHT: feed -->
    <div class="rv3-au-feed">
      <!-- Summary strip — сколько / кто / насколько важно -->
      <div class="rv3-au-summary">
        <div class="rv3-au-sum-tile">
          <div class="rv3-au-sum-n">{{ summary.total }}</div>
          <div class="rv3-au-sum-l">событий {{ periodLabel }}</div>
        </div>
        <div class="rv3-au-sum-tile">
          <div class="rv3-au-sum-n">{{ summary.actors }}</div>
          <div class="rv3-au-sum-l">пользователей</div>
        </div>
        <div class="rv3-au-sum-tile" :class="{ 'is-critical': summary.critical > 0 }">
          <div class="rv3-au-sum-n">{{ summary.critical }}</div>
          <div class="rv3-au-sum-l">важных действий</div>
        </div>
        <div class="rv3-au-legend">
          <span class="rv3-au-legend-i"><i style="background:#E24B4A"></i>Важное</span>
          <span class="rv3-au-legend-i"><i style="background:#EF9F27"></i>Изменение</span>
          <span class="rv3-au-legend-i"><i style="background:#888780"></i>Просмотр</span>
        </div>
      </div>

      <!-- Quick chips + active actor filter -->
      <div class="rv3-au-chips">
        <button
          v-for="c in QUICK_CHIPS" :key="c.key"
          class="rv3-au-chip" :class="{ on: quickCat === c.key }"
          @click="quickCat = c.key"
        >{{ c.label }}</button>
        <div class="rv3-au-chip-sp"></div>
        <div v-if="actorFilter" class="rv3-au-actorpill">
          <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/><circle cx="12" cy="7" r="4"/></svg>
          <span>{{ actorFilterName }}</span>
          <button class="rv3-au-actorpill-x" @click="actorFilter = ''" title="Сбросить фильтр по пользователю">
            <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
          </button>
        </div>
      </div>

      <!-- Search bar -->
      <div class="rv3-au-search-bar">
        <svg class="rv3-au-search-ic" width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="11" cy="11" r="7"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg>
        <input
          v-model="search"
          @input="onSearchInput"
          placeholder="Поиск: кто (имя/email), что (действие) или объект…"
          class="rv3-au-search"
        />
        <span class="rv3-au-counter">
          показано {{ processedEvents.length }} из {{ total }}
          <span v-if="groupSimilar && processedEvents.length < events.length" class="rv3-au-counter-note">
            (схлопнуто {{ events.length - processedEvents.length }})
          </span>
        </span>
      </div>

      <!-- States -->
      <div v-if="loading && events.length === 0" class="rv3-state">Загрузка...</div>
      <div v-else-if="error" class="rv3-state rv3-state-err">{{ error }}</div>
      <div v-else-if="events.length === 0" class="rv3-empty-card">
        <div class="rv3-empty-icon">
          <svg width="42" height="42" viewBox="0 0 24 24" fill="none" stroke="#D1D5DB" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
            <circle cx="12" cy="12" r="10"/>
            <polyline points="12,6 12,12 16,14"/>
          </svg>
        </div>
        <div class="rv3-empty-title">Событий не найдено</div>
        <div class="rv3-empty-text">Измените период или фильтры</div>
      </div>

      <!-- Feed grouped by day -->
      <template v-else>
        <div v-if="processedEvents.length === 0" class="rv3-empty-card">
          <div class="rv3-empty-title">Под выбранные чипы ничего не подошло</div>
          <div class="rv3-empty-text">Сбросьте быстрый фильтр или «скрыть info-события»</div>
          <button class="rv3-au-reset-chip" @click="quickCat = 'all'; hideInfo = false">Сбросить</button>
        </div>
        <div v-for="group in grouped" :key="group.date" class="rv3-au-group">
          <div class="rv3-au-day">{{ group.label }} · {{ group.events.length }}</div>

          <div v-for="e in group.events" :key="e.id" class="rv3-au-event">
            <div class="rv3-au-avatar-wrap">
              <UserAvatar :email="e.actor_email || ''" :size="30" />
              <span class="rv3-au-dot" :style="{ background: severity(e).color }"></span>
            </div>

            <div class="rv3-au-body">
              <!-- WHO · WHAT -->
              <div class="rv3-au-line">
                <span class="rv3-au-sevchip" :style="{ background: severity(e).color + '1A', color: severity(e).color }">{{ severity(e).ru }}</span>
                <button class="rv3-au-actor" :class="{ on: actorFilter === e.actor_email }"
                        :title="`${e.actor_email || 'Система'} — показать только действия этого пользователя`"
                        @click.stop="filterByActor(e)">{{ actorName(e) }}</button>
                <span v-if="e.actor_role" class="rv3-au-role">{{ e.actor_role }}</span>
                <span class="rv3-au-what">{{ describe(e) }}</span>
                <span v-if="e.burstCount > 1" class="rv3-au-burst" :title="`Серия из ${e.burstCount} одинаковых действий за короткий период`">
                  ×{{ e.burstCount }}
                </span>
              </div>

              <!-- WHERE (модуль рус. + объект) -->
              <div v-if="whereText(e)" class="rv3-au-where">
                <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 10c0 7-9 13-9 13s-9-6-9-13a9 9 0 0 1 18 0z"/><circle cx="12" cy="10" r="3"/></svg>
                <span>{{ whereText(e) }}</span>
              </div>

              <!-- WHEN (+ IP, остальная техника — в подробностях) -->
              <div class="rv3-au-meta">
                <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/></svg>
                <span :title="fmtAbsolute(e.created_at)">{{ fmtRelative(e.created_at) }} назад</span>
                <span v-if="e.burstCount > 1 && e.burstFirstAt" class="rv3-au-sep">·</span>
                <span v-if="e.burstCount > 1 && e.burstFirstAt" :title="`От ${fmtAbsolute(e.burstFirstAt)} до ${fmtAbsolute(e.created_at)}`">
                  серия за {{ fmtRelative(e.burstFirstAt) }}
                </span>
                <span v-if="e.http_status && e.http_status >= 400" class="rv3-au-sep">·</span>
                <span v-if="e.http_status && e.http_status >= 400" class="rv3-au-http-err" title="Ошибка запроса">ошибка {{ e.http_status }}</span>
                <span v-if="e.ip_address" class="rv3-au-sep">·</span>
                <span v-if="e.ip_address" class="rv3-au-ip" :title="`IP-адрес: ${e.ip_address}`">{{ e.ip_address }}</span>
              </div>

              <button
                v-if="e.has_diff || e.has_payload || e.entity_id"
                class="rv3-au-expand"
                @click="toggleDetail(e.id)"
              >
                {{ expandedId === e.id ? '▾ скрыть подробности' : '▸ подробности' }}
              </button>

              <div v-if="expandedId === e.id" class="rv3-au-detail">
                <div v-if="detailLoading === e.id" class="rv3-au-loading">Загрузка...</div>
                <template v-else-if="detailCache[e.id]">
                  <!-- Action context table -->
                  <div class="rv3-au-block">
                    <div class="rv3-au-block-hd">Контекст события</div>
                    <table class="rv3-au-ctx-table">
                      <tbody>
                        <tr><th>ID события</th><td><code>{{ detailCache[e.id].id }}</code></td></tr>
                        <tr v-if="detailCache[e.id].actor_id"><th>ID пользователя</th><td><code>{{ detailCache[e.id].actor_id }}</code></td></tr>
                        <tr v-if="detailCache[e.id].entity_id"><th>ID объекта</th><td><code>{{ detailCache[e.id].entity_id }}</code></td></tr>
                        <tr v-if="detailCache[e.id].entity_type"><th>Тип объекта</th><td>{{ detailCache[e.id].entity_type }}</td></tr>
                        <tr v-if="detailCache[e.id].http_method && detailCache[e.id].http_path">
                          <th>HTTP</th>
                          <td><span class="rv3-au-http-method" :class="`m-${(detailCache[e.id].http_method ?? '').toLowerCase()}`">{{ detailCache[e.id].http_method }}</span> <code>{{ detailCache[e.id].http_path }}</code> → <strong>{{ detailCache[e.id].http_status || '—' }}</strong></td>
                        </tr>
                        <tr v-if="detailCache[e.id].duration_ms"><th>Длительность</th><td>{{ detailCache[e.id].duration_ms }} ms</td></tr>
                        <tr><th>Точное время</th><td>{{ fmtAbsolute(detailCache[e.id].created_at) }}</td></tr>
                      </tbody>
                    </table>
                  </div>

                  <!-- Diff: before → after as table -->
                  <div v-if="detailCache[e.id].diff" class="rv3-au-block">
                    <div class="rv3-au-block-hd">Изменения · до → после</div>
                    <table class="rv3-au-diff-table">
                      <thead>
                        <tr><th>Поле</th><th>Было</th><th>Стало</th></tr>
                      </thead>
                      <tbody>
                        <tr v-for="r in diffRows(detailCache[e.id].diff)" :key="r.field">
                          <td class="rv3-au-diff-key">{{ r.field }}</td>
                          <td class="rv3-au-diff-before">{{ formatValue(r.before) }}</td>
                          <td class="rv3-au-diff-after">{{ formatValue(r.after) }}</td>
                        </tr>
                      </tbody>
                    </table>
                  </div>

                  <!-- Payload (raw JSON, collapsible) -->
                  <details v-if="detailCache[e.id].payload" class="rv3-au-block rv3-au-payload">
                    <summary class="rv3-au-block-hd">Полезная нагрузка (raw payload)</summary>
                    <pre>{{ JSON.stringify(detailCache[e.id].payload, null, 2) }}</pre>
                  </details>
                </template>
              </div>
            </div>

            <div class="rv3-au-time" :title="fmtAbsolute(e.created_at)">{{ fmtRelative(e.created_at) }}</div>
          </div>
        </div>

        <!-- Pagination -->
        <div class="rv3-au-pager" v-if="total > 50">
          <button :disabled="page === 1" @click="prevPage" class="rv3-au-page-btn">← Назад</button>
          <span class="rv3-au-page-num">страница {{ page }} из {{ Math.ceil(total / 50) }}</span>
          <button :disabled="!hasMorePages" @click="nextPage" class="rv3-au-page-btn">Вперёд →</button>
        </div>
      </template>
    </div>
  </div>
</template>

<style scoped>
.rv3-audit-shell {
  display: grid;
  grid-template-columns: 280px 1fr;
  gap: 1px;
  background: var(--border-hard);
  min-height: calc(100vh - 56px);
}
.rv3-au-filters { background: var(--bg1, #fff); padding: 18px; }
.rv3-au-section-title {
  font-size: 10px; font-weight: 500; color: var(--t3, var(--t-muted));
  letter-spacing: .06em; text-transform: uppercase;
  margin-bottom: 8px;
}
.rv3-au-period-list { display: flex; flex-direction: column; gap: 2px; }
.rv3-au-period {
  padding: 6px 10px;
  background: transparent; border: none; border-radius: 6px;
  font-size: 11px; color: var(--t1, #1E2A4A); font-weight: 500;
  text-align: left; cursor: pointer; font-family: inherit;
}
.rv3-au-period:hover { background: var(--bg2, #FAFAFC); }
.rv3-au-period.on { background: rgba(127,119,221,.12); color: var(--p-deep); }
.rv3-au-select {
  width: 100%; padding: 7px 10px;
  background: var(--bg2, #F9FAFB); border: 0.5px solid var(--border-hard); border-radius: 7px;
  font-size: 12px; color: var(--t1, #1E2A4A); outline: none;
  font-family: inherit; cursor: pointer;
}
.rv3-au-cb {
  display: flex; align-items: center; gap: 7px;
  font-size: 11px; color: var(--t1, #1E2A4A); cursor: pointer;
}
.rv3-au-cb input { accent-color: #7F77DD; cursor: pointer; }
.rv3-au-sw { width: 8px; height: 8px; border-radius: 50%; }
.rv3-au-export {
  width: 100%; margin-top: 18px;
  padding: 7px 12px;
  background: transparent; border: 1px solid var(--border-hard); border-radius: 8px;
  color: var(--t1, #1E2A4A); font-size: 11px; font-weight: 500;
  cursor: pointer; font-family: inherit;
  display: flex; align-items: center; justify-content: center; gap: 6px;
}
.rv3-au-export:hover { background: var(--bg2, #FAFAFC); border-color: #D1D5DB; }

.rv3-au-feed { background: var(--bg1, #fff); padding: 0; overflow-y: auto; }

/* Summary strip */
.rv3-au-summary {
  display: flex; align-items: center; gap: 12px;
  padding: 16px 22px 14px;
  border-bottom: 0.5px solid var(--border-hard);
  flex-wrap: wrap;
}
.rv3-au-sum-tile {
  display: flex; flex-direction: column; gap: 2px;
  padding: 8px 16px 8px 0;
  border-right: 1px solid var(--border-hard);
}
.rv3-au-sum-n { font-size: 20px; font-weight: 400; letter-spacing: -.02em; color: var(--t1, #1E2A4A); font-variant-numeric: tabular-nums; line-height: 1; }
.rv3-au-sum-tile.is-critical .rv3-au-sum-n { color: #E24B4A; }
.rv3-au-sum-l { font-size: 10px; font-weight: 500; text-transform: uppercase; letter-spacing: .05em; color: var(--t3, var(--t-muted)); }
.rv3-au-legend { display: flex; gap: 12px; margin-left: auto; flex-wrap: wrap; }
.rv3-au-legend-i { display: inline-flex; align-items: center; gap: 5px; font-size: 11px; color: var(--t3, var(--t-muted)); }
.rv3-au-legend-i i { width: 8px; height: 8px; border-radius: 50%; }

/* Quick chips + actor pill */
.rv3-au-chips {
  display: flex; align-items: center; gap: 7px; flex-wrap: wrap;
  padding: 12px 22px;
  border-bottom: 0.5px solid var(--border-hard);
}
.rv3-au-chip {
  font-size: 11.5px; font-weight: 500; font-family: inherit;
  color: var(--t2, #4B5468); background: var(--bg2, #F9FAFB);
  border: 1px solid var(--border-hard); border-radius: 999px;
  padding: 5px 13px; cursor: pointer; transition: all .14s;
}
.rv3-au-chip:hover { background: rgba(127,119,221,.08); }
.rv3-au-chip.on { background: rgba(127,119,221,.12); border-color: rgba(127,119,221,.4); color: var(--p-deep, #534AB7); }
.rv3-au-chip-sp { flex: 1; }
.rv3-au-actorpill {
  display: inline-flex; align-items: center; gap: 6px;
  font-size: 11.5px; font-weight: 500; color: var(--p-deep, #534AB7);
  background: rgba(127,119,221,.10); border: 1px solid rgba(127,119,221,.30);
  border-radius: 999px; padding: 4px 6px 4px 11px;
}
.rv3-au-actorpill-x {
  display: inline-flex; align-items: center; justify-content: center;
  width: 17px; height: 17px; border: none; background: transparent;
  color: var(--p-deep, #534AB7); cursor: pointer; border-radius: 50%; padding: 0;
}
.rv3-au-actorpill-x:hover { background: rgba(127,119,221,.18); }
.rv3-au-hint { font-size: 10px; color: var(--t3, var(--t-muted)); margin-top: 6px; }
.rv3-au-reset-chip {
  margin-top: 12px; font-size: 11.5px; font-weight: 500; font-family: inherit;
  color: var(--p-deep, #534AB7); background: rgba(127,119,221,.10);
  border: 1px solid rgba(127,119,221,.30); border-radius: 8px;
  padding: 6px 14px; cursor: pointer;
}
.rv3-au-reset-chip:hover { background: rgba(127,119,221,.16); }

.rv3-au-search-bar {
  padding: 14px 22px;
  border-bottom: 0.5px solid var(--border-hard);
  display: flex; gap: 10px; align-items: center;
  position: sticky; top: 0; background: var(--bg1, #fff); z-index: 5;
}
.rv3-au-search-ic { color: var(--t3, var(--t-muted)); flex-shrink: 0; }
.rv3-au-search {
  flex: 1; height: 30px; padding: 0 11px;
  background: var(--bg2, #F9FAFB); border: 0.5px solid var(--border-hard); border-radius: 7px;
  font-size: 12px; outline: none; font-family: inherit;
}
.rv3-au-counter { font-size: 11px; color: var(--t3, var(--t-muted)); }

.rv3-state { padding: 60px; text-align: center; font-size: 13px; color: var(--t3, var(--t-muted)); }
.rv3-state-err { color: var(--sev-high); }
.rv3-empty-card {
  margin: 60px auto; max-width: 480px;
  text-align: center; padding: 32px;
}
.rv3-empty-icon { margin-bottom: 14px; }
.rv3-empty-title { font-size: 14px; font-weight: 500; letter-spacing: -.01em; margin-bottom: 6px; }
.rv3-empty-text { font-size: 12px; color: var(--t3, var(--t-muted)); }

.rv3-au-group { padding: 0 22px; }
.rv3-au-day {
  padding: 14px 0 6px;
  font-size: 10px; font-weight: 500; color: var(--t3, var(--t-muted));
  letter-spacing: .06em; text-transform: uppercase;
}
.rv3-au-event {
  display: grid;
  grid-template-columns: auto 1fr auto;
  gap: 12px; align-items: flex-start;
  padding: 11px 0;
  border-bottom: 0.5px solid #F3F4F8;
}
.rv3-au-event:last-child { border-bottom: none; }
.rv3-au-avatar-wrap { position: relative; flex-shrink: 0; }
.rv3-au-dot {
  position: absolute; bottom: -2px; right: -2px;
  width: 9px; height: 9px;
  border: 1.5px solid #fff; border-radius: 50%;
}
.rv3-au-body { min-width: 0; }
.rv3-au-line { font-size: 12.5px; color: var(--t1, #1E2A4A); line-height: 1.6; display: flex; align-items: center; flex-wrap: wrap; gap: 6px; }
.rv3-au-line strong { font-weight: 600; }
.rv3-au-actor {
  font-family: inherit; font-size: 12.5px; font-weight: 600; color: var(--t1, #1E2A4A);
  background: transparent; border: none; padding: 1px 4px; margin: 0 -2px;
  border-radius: 5px; cursor: pointer; transition: background .12s, color .12s;
}
.rv3-au-actor:hover { background: rgba(127,119,221,.10); color: var(--p-deep, #534AB7); }
.rv3-au-actor.on { background: rgba(127,119,221,.14); color: var(--p-deep, #534AB7); }
.rv3-au-sevchip {
  font-size: 9.5px; font-weight: 600; text-transform: uppercase; letter-spacing: .04em;
  padding: 1px 7px; border-radius: 6px; flex-shrink: 0;
}
.rv3-au-what { color: var(--t2, #4B5468); }
.rv3-au-sep { color: var(--t3, var(--t-muted)); margin: 0 4px; }
.rv3-au-where {
  display: inline-flex; align-items: center; gap: 5px;
  margin-top: 4px;
  font-size: 11px; font-weight: 500; color: var(--p-deep, #534AB7);
  background: rgba(127,119,221,.08); border-radius: 6px;
  padding: 2px 8px 2px 6px; width: fit-content; max-width: 100%;
}
.rv3-au-where svg { flex-shrink: 0; opacity: .8; }
.rv3-au-where span { white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.rv3-au-meta {
  font-size: 10.5px; color: var(--t3, var(--t-muted)); margin-top: 4px;
  display: flex; align-items: center; flex-wrap: wrap; gap: 0;
}
.rv3-au-meta > svg { margin-right: 4px; opacity: .7; flex-shrink: 0; }
.rv3-au-tag {
  padding: 1px 6px;
  background: #F3F4F8; color: var(--t1, #1E2A4A);
  border-radius: 7px;
  font-size: 9.5px; font-weight: 500; letter-spacing: .04em;
}
.rv3-au-http-err {
  padding: 1px 6px;
  background: rgba(226,75,74,.08); color: #A82C2B;
  border-radius: 7px;
  font-size: 9.5px; font-weight: 500;
}
.rv3-au-expand {
  margin-top: 6px;
  background: transparent; border: none;
  color: var(--p-deep); font-size: 10.5px; font-weight: 500;
  cursor: pointer; font-family: inherit;
  padding: 2px 0;
}
.rv3-au-expand:hover { color: #463E9F; }
.rv3-au-detail {
  margin-top: 6px;
  padding: 10px 12px;
  background: var(--bg2, #F9FAFB); border-radius: 7px;
  font-size: 10.5px;
}
.rv3-au-loading { color: var(--t3, var(--t-muted)); font-style: italic; }
.rv3-au-block + .rv3-au-block { margin-top: 8px; }
.rv3-au-block-hd {
  font-size: 9.5px; font-weight: 500; color: var(--t3, var(--t-muted));
  letter-spacing: .06em; text-transform: uppercase;
  margin-bottom: 3px;
}
.rv3-au-block pre {
  margin: 0;
  font-family: ui-monospace, 'SF Mono', Menlo, monospace;
  font-size: 10.5px; color: var(--t1, #1E2A4A);
  white-space: pre-wrap; word-break: break-all;
  line-height: 1.5;
}
.rv3-au-time {
  font-size: 10.5px; color: var(--t3, var(--t-muted)); white-space: nowrap;
  flex-shrink: 0;
}

.rv3-au-pager {
  padding: 18px 22px;
  display: flex; align-items: center; justify-content: center; gap: 14px;
  border-top: 0.5px solid var(--border-hard);
}
.rv3-au-page-btn {
  padding: 5px 11px;
  background: transparent; border: 1px solid var(--border-hard); border-radius: 7px;
  color: var(--t1, #1E2A4A); font-size: 11px; font-weight: 500;
  cursor: pointer; font-family: inherit;
}
.rv3-au-page-btn:hover:not(:disabled) { background: var(--bg2, #FAFAFC); }
.rv3-au-page-btn:disabled { opacity: .45; cursor: not-allowed; }
.rv3-au-page-num { font-size: 11px; color: var(--t3, var(--t-muted)); }

/* ─── Enhanced detail rendering (Pack 11.x: rich audit context) ─── */
.rv3-au-counter-note { color: #7F77DD; margin-left: 4px; }
.rv3-au-role {
  margin-left: 6px;
  padding: 1px 6px;
  background: rgba(127, 119, 221, 0.10);
  color: var(--p-deep);
  border-radius: 7px;
  font-size: 9.5px;
  font-weight: 500;
  text-transform: uppercase;
  letter-spacing: 0.05em;
}
.rv3-au-burst {
  margin-left: 6px;
  padding: 1px 6px;
  background: linear-gradient(135deg, #7F77DD, var(--p-deep));
  color: #fff;
  border-radius: 7px;
  font-size: 10px;
  font-weight: 500;
  font-variant-numeric: tabular-nums;
}
.rv3-au-http-method {
  display: inline-block;
  padding: 1px 5px;
  border-radius: 4px;
  font-size: 9.5px;
  font-weight: 500;
  font-family: ui-monospace, 'SF Mono', Menlo, monospace;
  letter-spacing: 0.04em;
}
.rv3-au-http-method.m-get    { background: rgba(55, 138, 221, 0.10); color: #2563EB; }
.rv3-au-http-method.m-post   { background: rgba(29, 158, 117, 0.10); color: var(--green); }
.rv3-au-http-method.m-put,
.rv3-au-http-method.m-patch  { background: rgba(239, 159, 39, 0.10); color: #D97706; }
.rv3-au-http-method.m-delete { background: rgba(226, 75, 74, 0.10); color: var(--sev-high); }
.rv3-au-http-path {
  margin-left: 4px;
  font-family: ui-monospace, 'SF Mono', Menlo, monospace;
  font-size: 10px;
  color: var(--t3, var(--t-muted));
  max-width: 240px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  display: inline-block;
  vertical-align: middle;
}
.rv3-au-dur, .rv3-au-ip {
  font-variant-numeric: tabular-nums;
  font-family: ui-monospace, 'SF Mono', Menlo, monospace;
  font-size: 10px;
}

/* Context table */
.rv3-au-ctx-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 11px;
}
.rv3-au-ctx-table th {
  width: 130px;
  padding: 4px 8px 4px 0;
  text-align: left;
  font-weight: 500;
  color: var(--t3, var(--t-muted));
  text-transform: uppercase;
  letter-spacing: 0.06em;
  font-size: 10px;
  vertical-align: top;
}
.rv3-au-ctx-table td {
  padding: 4px 0;
  color: var(--t1, #1E2A4A);
  word-break: break-all;
}
.rv3-au-ctx-table code {
  font-family: ui-monospace, 'SF Mono', Menlo, monospace;
  font-size: 10.5px;
  background: var(--bg1, #fff);
  padding: 1px 5px;
  border-radius: 4px;
  border: 0.5px solid var(--border-hard);
}

/* Diff table — before → after side-by-side */
.rv3-au-diff-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 11px;
  margin-top: 4px;
}
.rv3-au-diff-table th {
  padding: 5px 9px;
  text-align: left;
  background: var(--bg1, #fff);
  border-bottom: 1px solid var(--border-hard);
  font-weight: 500;
  font-size: 10px;
  color: var(--t3, var(--t-muted));
  text-transform: uppercase;
  letter-spacing: 0.06em;
}
.rv3-au-diff-table td {
  padding: 5px 9px;
  border-bottom: 0.5px solid var(--border-hard);
  vertical-align: top;
}
.rv3-au-diff-table tr:last-child td { border-bottom: none; }
.rv3-au-diff-key {
  font-weight: 500;
  color: var(--t1, #1E2A4A);
  font-family: ui-monospace, 'SF Mono', Menlo, monospace;
  font-size: 10.5px;
}
.rv3-au-diff-before {
  color: var(--sev-high);
  text-decoration: line-through;
  text-decoration-color: rgba(226, 75, 74, 0.40);
  font-family: ui-monospace, 'SF Mono', Menlo, monospace;
  font-size: 10.5px;
}
.rv3-au-diff-after {
  color: var(--green);
  font-family: ui-monospace, 'SF Mono', Menlo, monospace;
  font-size: 10.5px;
}

/* Raw payload — collapsed by default */
.rv3-au-payload summary {
  cursor: pointer;
  margin-bottom: 4px;
  list-style: none;
}
.rv3-au-payload summary::before {
  content: '▸ ';
  display: inline-block;
  transition: transform 0.18s ease;
}
.rv3-au-payload[open] summary::before {
  transform: rotate(90deg);
}
</style>