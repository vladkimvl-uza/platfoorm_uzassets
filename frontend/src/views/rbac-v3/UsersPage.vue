<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue';
import {
  rbacV3Api,
  type RbacV3Overview,
  type RbacV3UserBrief,
  type RbacV3UserCompanyMembership,
} from '@/api/rbacV3';
import { companiesApi, type CompanyListItem } from '@/api/companies';
import BIcon from '@/components/broadcasts/BIcon.vue';
import BulkRolePickerModal from '@/components/rbac-v3/BulkRolePickerModal.vue';
import RoleChip from '@/components/rbac-v3/RoleChip.vue';
import UserAffiliationBadge from '@/components/rbac-v3/UserAffiliationBadge.vue';
import UserAvatar from '@/components/rbac-v3/UserAvatar.vue';
import UserCardAnchor from '@/components/user/UserCardAnchor.vue';
import { useConfirm } from '@/composables/useConfirm';
import { useI18n } from '@/composables/useI18n';
import { presenceStatus } from '@/composables/usePresence';
import { fmtDateTime, fmtRelativeTime, INTL_LOCALE } from '@/locale';
import { companyDisplayName } from '@/utils/displayNames';
import UserDetailDrawer from './UserDetailDrawer.vue';

type Filter = 'all' | 'active' | 'inactive' | 'pwd_change' | 'without_roles';
type SortMode = 'activity' | 'name' | 'created';
type ViewMode = 'list' | 'company';

interface CompanyUserEntry {
  user: RbacV3UserBrief;
  membership: RbacV3UserCompanyMembership | null;
}

interface CompanyUserGroup {
  key: string;
  companyId: string | null;
  name: string;
  entries: CompanyUserEntry[];
  activeCount: number;
  inactiveCount: number;
  attentionCount: number;
}

type RegistryItem =
  | { kind: 'company'; key: string; group: CompanyUserGroup }
  | {
      kind: 'user';
      key: string;
      user: RbacV3UserBrief;
      membership: RbacV3UserCompanyMembership | null;
      rowIndex: number;
    };

const { confirmDialog } = useConfirm();
const { t, locale } = useI18n();

const users = ref<RbacV3UserBrief[]>([]);
const overview = ref<RbacV3Overview | null>(null);
const total = ref(0);
const loading = ref(false);
const refreshing = ref(false);
const error = ref<string | null>(null);
const search = ref('');
const filter = ref<Filter>('all');
const sortMode = ref<SortMode>('activity');
const viewMode = ref<ViewMode>('company');
const selectedIds = ref<Set<string>>(new Set());
const collapsedCompanies = ref<Set<string>>(new Set());
const selectedUser = ref<RbacV3UserBrief | null>(null);
const showBulk = ref(false);
const bulkBusy = ref(false);
const truncated = ref(false);
const companyCatalog = ref<CompanyListItem[]>([]);
const companyById = computed(() => new Map(companyCatalog.value.map(company => [company.id, company])));

const USERS_LIMIT = 500;
const PWD_AGE_WARN_DAYS = 60;
const PWD_AGE_CRIT_DAYS = 90;

function pwdAgeDays(user: RbacV3UserBrief): number | null {
  const value = user.password_changed_at;
  if (!value) return null;
  return Math.floor((Date.now() - new Date(value).getTime()) / 86400000);
}

function pwdNeedsAttention(user: RbacV3UserBrief): boolean {
  if (user.must_change_password) return true;
  const age = pwdAgeDays(user);
  return age !== null && age >= PWD_AGE_WARN_DAYS;
}

function pwdSeverity(user: RbacV3UserBrief): 'critical' | 'warning' | 'ok' | 'unknown' {
  if (user.must_change_password) return 'critical';
  const age = pwdAgeDays(user);
  if (age === null) return 'unknown';
  if (age >= PWD_AGE_CRIT_DAYS) return 'critical';
  if (age >= PWD_AGE_WARN_DAYS) return 'warning';
  return 'ok';
}

function pwdStatusLabel(user: RbacV3UserBrief): string {
  if (user.must_change_password) return t('Требуется смена');
  const age = pwdAgeDays(user);
  if (age === null) return t('Нет данных');
  if (age >= PWD_AGE_CRIT_DAYS) return t('{age} дн. без смены', { age: formatCount(age) });
  if (age >= PWD_AGE_WARN_DAYS) return t('Истекает · {age} дн.', { age: formatCount(age) });
  return t('В норме');
}

async function loadOverview() {
  try {
    overview.value = await rbacV3Api.overview();
  } catch {
    // The registry remains usable if overview is temporarily unavailable.
  }
}

async function loadCompanies() {
  try {
    const response = await companiesApi.list({ per_page: 500 });
    companyCatalog.value = response.items || [];
  } catch {
    // The registry can still use names included in the RBAC response.
  }
}

async function loadUsers(silent = false) {
  if (!silent) loading.value = true;
  error.value = null;
  try {
    const options: { limit: number; search?: string } = { limit: USERS_LIMIT };
    if (search.value.trim()) options.search = search.value.trim();
    const response = await rbacV3Api.listUsers(options);
    users.value = response.items;
    total.value = response.total;
    truncated.value = response.items.length >= USERS_LIMIT || response.total > response.items.length;

    const loadedIds = new Set(response.items.map(user => user.id));
    selectedIds.value = new Set([...selectedIds.value].filter(id => loadedIds.has(id)));
    if (selectedUser.value && !loadedIds.has(selectedUser.value.id)) selectedUser.value = null;
  } catch (requestError: any) {
    error.value = requestError?.response?.data?.detail || t('Не удалось загрузить пользователей');
  } finally {
    if (!silent) loading.value = false;
  }
}

async function refreshAll() {
  if (refreshing.value) return;
  refreshing.value = true;
  await Promise.all([loadUsers(true), loadOverview()]);
  refreshing.value = false;
}

async function onExternalRefresh() {
  await Promise.all([loadUsers(true), loadOverview()]);
}

let presenceTimer: number | undefined;
// number, а не ReturnType<typeof setTimeout>: в проекте подключены @types/node,
// и ReturnType резолвится в NodeJS.Timeout, тогда как window.setTimeout в
// браузере возвращает number — присваивание не проходило проверку типов.
let searchTimer: number | undefined;

onMounted(() => {
  Promise.all([loadUsers(), loadOverview(), loadCompanies()]);
  window.addEventListener('rbac-v3:users-changed', onExternalRefresh);
  presenceTimer = window.setInterval(onExternalRefresh, 45000);
});

onBeforeUnmount(() => {
  window.removeEventListener('rbac-v3:users-changed', onExternalRefresh);
  if (presenceTimer) window.clearInterval(presenceTimer);
  if (searchTimer) window.clearTimeout(searchTimer);
});

const loadedCounts = computed(() => ({
  all: users.value.length,
  active: users.value.filter(user => user.is_active).length,
  inactive: users.value.filter(user => !user.is_active).length,
  pwd_change: users.value.filter(pwdNeedsAttention).length,
  without_roles: users.value.filter(user =>
    user.role_codes.length === 0 && !(user.company_memberships || []).length).length,
}));

const filterOptions = computed(() => [
  {
    id: 'all' as const,
    label: t('Все'),
    count: search.value.trim() ? total.value : (overview.value?.users_total ?? total.value),
  },
  {
    id: 'active' as const,
    label: t('Активные'),
    count: search.value.trim() ? loadedCounts.value.active : (overview.value?.users_active ?? loadedCounts.value.active),
  },
  {
    id: 'inactive' as const,
    label: t('Заблокированные'),
    count: search.value.trim() ? loadedCounts.value.inactive : (overview.value?.users_inactive ?? loadedCounts.value.inactive),
  },
  {
    id: 'pwd_change' as const,
    label: t('Требуют внимания'),
    count: loadedCounts.value.pwd_change,
  },
  {
    // Вкладка нужна, чтобы клик по карточке «Без назначенных ролей» имел
    // видимое состояние в переключателе и его можно было снять обратно.
    id: 'without_roles' as const,
    label: t('Без ролей'),
    count: overview.value?.users_without_roles ?? loadedCounts.value.without_roles,
  },
]);

// Каждая карточка сводки — кнопка: клик включает соответствующий фильтр списка.
// target — значение фильтра, которое карточка представляет.
const summaryMetrics = computed(() => [
  {
    key: 'total',
    target: 'all' as Filter,
    label: t('Всего пользователей'),
    value: overview.value?.users_total ?? total.value,
    icon: 'user-check',
    tone: 'neutral',
  },
  {
    key: 'active',
    target: 'active' as Filter,
    label: t('Активные'),
    value: overview.value?.users_active ?? loadedCounts.value.active,
    icon: 'shield-check',
    tone: 'positive',
  },
  {
    key: 'inactive',
    target: 'inactive' as Filter,
    label: t('Заблокированные'),
    value: overview.value?.users_inactive ?? loadedCounts.value.inactive,
    icon: 'lock',
    tone: 'negative',
  },
  {
    key: 'without_roles',
    target: 'without_roles' as Filter,
    label: t('Без назначенных ролей'),
    value: overview.value?.users_without_roles ?? loadedCounts.value.without_roles,
    icon: 'user-exclamation',
    tone: 'warning',
  },
]);

const visibleUsers = computed(() => {
  let result = users.value.filter((user) => {
    if (filter.value === 'active') return user.is_active;
    if (filter.value === 'inactive') return !user.is_active;
    if (filter.value === 'pwd_change') return pwdNeedsAttention(user);
    if (filter.value === 'without_roles') return user.role_codes.length === 0;
    return true;
  });

  result = [...result].sort((left, right) => {
    if (sortMode.value === 'name') {
      return left.full_name.localeCompare(right.full_name, INTL_LOCALE[locale.value]);
    }
    if (sortMode.value === 'created') {
      return new Date(right.created_at).getTime() - new Date(left.created_at).getTime();
    }
    const leftActivity = left.last_seen_at ? new Date(left.last_seen_at).getTime() : 0;
    const rightActivity = right.last_seen_at ? new Date(right.last_seen_at).getTime() : 0;
    return rightActivity - leftActivity
      || left.full_name.localeCompare(right.full_name, INTL_LOCALE[locale.value]);
  });

  return result;
});

const UNASSIGNED_COMPANY_KEY = '__unassigned__';

function localizedCompanyName(companyId: string | null, fallback: string | null | undefined): string {
  if (!companyId) return fallback || '';
  return companyDisplayName(companyById.value.get(companyId)) || fallback || companyId;
}

const companyGroups = computed<CompanyUserGroup[]>(() => {
  const groups = new Map<
    string,
    {
      companyId: string | null;
      name: string;
      entries: Map<string, CompanyUserEntry>;
    }
  >();

  const addEntry = (
    key: string,
    companyId: string | null,
    name: string,
    user: RbacV3UserBrief,
    membership: RbacV3UserCompanyMembership | null,
  ) => {
    if (!groups.has(key)) groups.set(key, { companyId, name, entries: new Map() });
    groups.get(key)!.entries.set(user.id, { user, membership });
  };

  for (const user of visibleUsers.value) {
    const memberships = user.company_memberships || [];
    if (memberships.length) {
      for (const membership of memberships) {
        addEntry(
          membership.company_id,
          membership.company_id,
          localizedCompanyName(membership.company_id, membership.company_name || membership.group_name),
          user,
          membership,
        );
      }
      continue;
    }

    if (user.organization_id && user.company) {
      addEntry(
        user.organization_id,
        user.organization_id,
        localizedCompanyName(user.organization_id, user.company),
        user,
        null,
      );
    } else {
      addEntry(UNASSIGNED_COMPANY_KEY, null, t('Без привязки к компании'), user, null);
    }
  }

  return Array.from(groups.entries())
    .map(([key, group]) => {
      const entries = Array.from(group.entries.values());
      return {
        key,
        companyId: group.companyId,
        name: group.name,
        entries,
        activeCount: entries.filter(entry => entry.user.is_active).length,
        inactiveCount: entries.filter(entry => !entry.user.is_active).length,
        attentionCount: entries.filter(entry => pwdNeedsAttention(entry.user)).length,
      };
    })
    .sort((left, right) => {
      if (left.key === UNASSIGNED_COMPANY_KEY) return 1;
      if (right.key === UNASSIGNED_COMPANY_KEY) return -1;
      return left.name.localeCompare(right.name, INTL_LOCALE[locale.value]);
    });
});

const registryItems = computed<RegistryItem[]>(() => {
  if (viewMode.value === 'list') {
    return visibleUsers.value.map((user, rowIndex) => ({
      kind: 'user',
      key: user.id,
      user,
      membership: null,
      rowIndex,
    }));
  }

  const items: RegistryItem[] = [];
  let rowIndex = 0;
  for (const group of companyGroups.value) {
    items.push({ kind: 'company', key: `company:${group.key}`, group });
    if (collapsedCompanies.value.has(group.key)) continue;
    for (const entry of group.entries) {
      items.push({
        kind: 'user',
        key: `user:${group.key}:${entry.user.id}`,
        user: entry.user,
        membership: entry.membership,
        rowIndex,
      });
      rowIndex++;
    }
  }
  return items;
});

const allVisibleSelected = computed(() =>
  visibleUsers.value.length > 0 && visibleUsers.value.every(user => selectedIds.value.has(user.id)));
const someVisibleSelected = computed(() =>
  visibleUsers.value.some(user => selectedIds.value.has(user.id)) && !allVisibleSelected.value);

function formatCount(value: number): string {
  return value.toLocaleString(INTL_LOCALE[locale.value]);
}

const registryCaption = computed(() => {
  const values = {
    shown: formatCount(visibleUsers.value.length),
    loaded: formatCount(users.value.length),
    total: formatCount(total.value),
    companies: formatCount(companyGroups.value.length),
  };
  if (search.value.trim()) {
    return viewMode.value === 'company'
      ? t('Найдено: {shown} из {total} · Компаний: {companies}', values)
      : t('Найдено: {shown} из {total}', values);
  }
  if (truncated.value) {
    return viewMode.value === 'company'
      ? t('Показано: {shown} · Загружено: {loaded} из {total} · Компаний: {companies}', values)
      : t('Показано: {shown} · Загружено: {loaded} из {total}', values);
  }
  return viewMode.value === 'company'
    ? t('Показано: {shown} из {total} · Компаний: {companies}', values)
    : t('Показано: {shown} из {total}', values);
});

function onSearchInput() {
  if (searchTimer) window.clearTimeout(searchTimer);
  searchTimer = window.setTimeout(() => loadUsers(), 300);
}

function clearSearch() {
  if (!search.value) return;
  search.value = '';
  loadUsers();
}

function onFilterChange(nextFilter: Filter) {
  filter.value = nextFilter;
  selectedIds.value = new Set();
}

function toggleSelect(id: string) {
  const next = new Set(selectedIds.value);
  if (next.has(id)) next.delete(id);
  else next.add(id);
  selectedIds.value = next;
}

function toggleSelectAllVisible() {
  const next = new Set(selectedIds.value);
  if (allVisibleSelected.value) {
    for (const user of visibleUsers.value) next.delete(user.id);
  } else {
    for (const user of visibleUsers.value) next.add(user.id);
  }
  selectedIds.value = next;
}

function companyUserIds(group: CompanyUserGroup): string[] {
  return [...new Set(group.entries.map(entry => entry.user.id))];
}

function isCompanySelected(group: CompanyUserGroup): boolean {
  const ids = companyUserIds(group);
  return ids.length > 0 && ids.every(id => selectedIds.value.has(id));
}

function isCompanyPartiallySelected(group: CompanyUserGroup): boolean {
  const ids = companyUserIds(group);
  return ids.some(id => selectedIds.value.has(id)) && !isCompanySelected(group);
}

function toggleCompanySelection(group: CompanyUserGroup) {
  const ids = companyUserIds(group);
  const next = new Set(selectedIds.value);
  if (isCompanySelected(group)) ids.forEach(id => next.delete(id));
  else ids.forEach(id => next.add(id));
  selectedIds.value = next;
}

function toggleCompany(groupKey: string) {
  const next = new Set(collapsedCompanies.value);
  if (next.has(groupKey)) next.delete(groupKey);
  else next.add(groupKey);
  collapsedCompanies.value = next;
}

function openUser(user: RbacV3UserBrief) {
  selectedUser.value = user;
}

function closeDrawer() {
  selectedUser.value = null;
}

async function onUserChanged() {
  await Promise.all([loadUsers(true), loadOverview()]);
}

function fmtLastActivity(value: string | null): string {
  return value ? fmtRelativeTime(value, locale.value) : t('Не входил');
}

function lastActivityTitle(user: RbacV3UserBrief): string {
  const seen = user.last_seen_at
    ? t('Последняя активность: {date}', { date: fmtDateTime(user.last_seen_at, locale.value) })
    : t('Активности ещё не было');
  const login = user.last_login_at
    ? t('Последний вход: {date}', { date: fmtDateTime(user.last_login_at, locale.value) })
    : t('Ни разу не входил');
  return `${seen}\n${login}`;
}

function scopeLabel(user: RbacV3UserBrief): string {
  return localizedCompanyName(user.organization_id, user.company) || user.department || t('Не указана');
}

function rowScopeLabel(user: RbacV3UserBrief, membership: RbacV3UserCompanyMembership | null): string {
  if (membership) return user.department || membership.group_name || t('Без подразделения');
  return scopeLabel(user);
}

function rowRoleCodes(
  user: RbacV3UserBrief,
  membership: RbacV3UserCompanyMembership | null,
): string[] {
  return [...new Set([
    ...(membership ? [membership.role_code] : []),
    ...user.role_codes,
  ])];
}

function rowRoleTitle(
  user: RbacV3UserBrief,
  membership: RbacV3UserCompanyMembership | null,
): string {
  const labels = [
    ...(membership ? [`${membership.role_name} · ${localizedCompanyName(membership.company_id, membership.company_name)}`] : []),
    ...user.role_names,
  ];
  return labels.join(', ') || t('Роли не назначены');
}

async function bulkDeactivate() {
  const ids = Array.from(selectedIds.value);
  if (!ids.length) return;
  const confirmed = await confirmDialog({
    message: t('Деактивировать выбранных пользователей: {count}? Активные сессии будут отозваны, пользователей можно реактивировать позже.',
      { count: formatCount(ids.length) },
    ),
    danger: true,
  });
  if (!confirmed) return;

  bulkBusy.value = true;
  let completed = 0;
  const failed: string[] = [];
  for (const id of ids) {
    try {
      await rbacV3Api.deactivate(id);
      completed++;
    } catch (requestError: any) {
      failed.push(requestError?.response?.data?.detail || id);
    }
  }
  bulkBusy.value = false;
  selectedIds.value = new Set();
  await Promise.all([loadUsers(true), loadOverview()]);
  if (failed.length) {
    error.value = t('Деактивировано: {completed}; не удалось: {failed}. Причина: {reason}', {
      completed: formatCount(completed),
      failed: formatCount(failed.length),
      reason: failed[0],
    });
  }
}
</script>

<template>
  <div class="users-page" :class="{ 'detail-open': selectedUser }">
    <main class="users-registry">
      <section class="users-summary" :aria-label="t('Сводка по пользователям')">
        <div class="summary-intro">
          <span class="summary-eyebrow">{{ t('Реестр доступа') }}</span>
          <h1>{{ t('Пользователи') }}</h1>
          <p>{{ t('Учётные записи, роли и состояние безопасности') }}</p>
        </div>
        <div class="summary-metrics">
          <button
            v-for="(metric, index) in summaryMetrics"
            :key="metric.key"
            type="button"
            :class="['summary-metric', `tone-${metric.tone}`, { on: filter === metric.target }]"
            :style="{ animationDelay: `${80 + index * 55}ms` }"
            :aria-pressed="filter === metric.target"
            :title="t('Показать: {label}', { label: metric.label })"
            @click="onFilterChange(metric.target)"
          >
            <span class="metric-icon"><BIcon :name="metric.icon" :size="16" /></span>
            <span class="metric-copy">
              <strong>{{ formatCount(metric.value) }}</strong>
              <small>{{ t(metric.label) }}</small>
            </span>
          </button>
        </div>
      </section>

      <section class="users-toolbar" :aria-label="t('Фильтры пользователей')">
        <div class="filter-tabs" role="tablist" :aria-label="t('Статус пользователей')">
          <button
            v-for="option in filterOptions"
            :key="option.id"
            type="button"
            role="tab"
            :aria-selected="filter === option.id"
            :class="['filter-tab', { on: filter === option.id, attention: option.id === 'pwd_change' }]"
            @click="onFilterChange(option.id)"
          >
            {{ t(option.label) }}
            <span>{{ formatCount(option.count) }}</span>
          </button>
        </div>

        <div class="toolbar-tools">
          <div class="view-mode" role="group" :aria-label="t('Представление пользователей')">
            <button
              type="button"
              :class="{ on: viewMode === 'list' }"
              :aria-pressed="viewMode === 'list'"
              :title="t('Показать единым списком')"
              @click="viewMode = 'list'"
            ><BIcon name="checklist" :size="13" /><span>{{ t('Список') }}</span></button>
            <button
              type="button"
              :class="{ on: viewMode === 'company' }"
              :aria-pressed="viewMode === 'company'"
              :title="t('Сгруппировать по компаниям доступа')"
              @click="viewMode = 'company'"
            ><BIcon name="building-bank" :size="13" /><span>{{ t('Компании') }}</span></button>
          </div>

          <label class="users-search">
            <BIcon name="search" :size="15" />
            <input
              v-model="search"
              type="search"
              name="rbac-users-search"
              autocomplete="off"
              autocorrect="off"
              autocapitalize="off"
              spellcheck="false"
              :placeholder="t('Имя, email, подразделение')"
              @input="onSearchInput"
            />
            <button
              v-if="search"
              type="button"
              :title="t('Очистить поиск')"
              :aria-label="t('Очистить поиск')"
              @click="clearSearch"
            ><BIcon name="x" :size="13" /></button>
          </label>

          <label class="sort-control">
            <span>{{ t('Сортировка') }}</span>
            <select v-model="sortMode" :aria-label="t('Сортировка пользователей')">
              <option value="activity">{{ t('По активности') }}</option>
              <option value="name">{{ t('По имени') }}</option>
              <option value="created">{{ t('Сначала новые') }}</option>
            </select>
          </label>

          <button
            type="button"
            class="refresh-button"
            :class="{ spinning: refreshing }"
            :disabled="refreshing"
            :title="t('Обновить список')"
            :aria-label="t('Обновить список')"
            @click="refreshAll"
          ><BIcon name="refresh" :size="15" /></button>
        </div>
      </section>

      <Transition name="bulk-bar">
        <div v-if="selectedIds.size" class="bulk-actions">
          <div class="bulk-count">
            <span>{{ selectedIds.size }}</span>
            <div><b>{{ t('Выбрано') }}</b><small>{{ t('Действия применятся ко всем отмеченным') }}</small></div>
          </div>
          <div class="bulk-buttons">
            <button type="button" @click="showBulk = true">
              <BIcon name="shield-check" :size="14" /> {{ t('Изменить роли') }}
            </button>
            <button type="button" class="danger" :disabled="bulkBusy" @click="bulkDeactivate">
              <BIcon name="trash" :size="14" /> {{ bulkBusy ? t('Деактивация...') : t('Деактивировать') }}
            </button>
            <button
              type="button"
              class="bulk-clear"
              :title="t('Снять выделение')"
              :aria-label="t('Снять выделение')"
              @click="selectedIds = new Set()"
            ><BIcon name="x" :size="15" /></button>
          </div>
        </div>
      </Transition>

      <div v-if="truncated" class="truncated-notice">
        <BIcon name="info-circle" :size="15" />
        <span>{{ t('Загружено {loaded} из {total} записей. Для точного результата уточните поиск.', {
          loaded: formatCount(users.length),
          total: formatCount(total),
        }) }}</span>
      </div>

      <section class="registry-table" :aria-label="t('Список пользователей')">
        <template v-if="loading">
          <div class="user-grid table-head skeleton-head">
            <span v-for="index in 8" :key="index"></span>
          </div>
          <div class="registry-list skeleton-list">
            <div v-for="index in 8" :key="index" class="user-grid skeleton-row">
              <span class="skeleton-check"></span>
              <span class="skeleton-user"><i></i><b></b></span>
              <span></span><span></span><span></span><span></span><span></span><span></span>
            </div>
          </div>
        </template>

        <div v-else-if="error" class="registry-state error-state">
          <span class="state-icon"><BIcon name="info-circle" :size="22" /></span>
          <h2>{{ t('Не удалось загрузить пользователей') }}</h2>
          <p>{{ error }}</p>
          <button type="button" @click="loadUsers()"><BIcon name="refresh" :size="14" /> {{ t('Повторить') }}</button>
        </div>

        <template v-else>
          <div class="user-grid table-head">
            <label class="select-all" :title="t('Выбрать видимые записи')">
              <input
                type="checkbox"
                :checked="allVisibleSelected"
                :indeterminate="someVisibleSelected"
                :aria-label="t('Выбрать всех видимых пользователей')"
                @change="toggleSelectAllVisible"
              />
            </label>
            <span>{{ t('Пользователь') }}</span>
            <span>{{ viewMode === 'company' ? t('Подразделение') : t('Область') }}</span>
            <span>{{ viewMode === 'company' ? t('Роль в компании') : t('Роли') }}</span>
            <span>{{ t('Активность') }}</span>
            <span>{{ t('Безопасность') }}</span>
            <span>{{ t('Статус') }}</span>
            <span></span>
          </div>

          <div class="registry-list">
            <template v-for="item in registryItems" :key="item.key">
              <div
                v-if="item.kind === 'company'"
                class="company-group-header"
                :class="{ collapsed: collapsedCompanies.has(item.group.key) }"
              >
                <label class="company-check" @click.stop>
                  <input
                    type="checkbox"
                    :checked="isCompanySelected(item.group)"
                    :indeterminate="isCompanyPartiallySelected(item.group)"
                    :aria-label="t('Выбрать пользователей компании {company}', { company: item.group.name })"
                    @change="toggleCompanySelection(item.group)"
                  />
                </label>
                <span class="company-mark"><BIcon name="building-bank" :size="15" /></span>
                <div class="company-heading">
                  <b :title="item.group.name">{{ item.group.name }}</b>
                  <small>{{ t('Пользователей: {count}', { count: formatCount(item.group.entries.length) }) }}</small>
                </div>
                <div class="company-health">
                  <span class="company-active"><i></i>{{ t('Активны: {count}', { count: formatCount(item.group.activeCount) }) }}</span>
                  <span v-if="item.group.inactiveCount" class="company-inactive"><i></i>{{ t('Заблокированы: {count}', { count: formatCount(item.group.inactiveCount) }) }}</span>
                  <span v-if="item.group.attentionCount" class="company-attention"><i></i>{{ t('Требуют внимания: {count}', { count: formatCount(item.group.attentionCount) }) }}</span>
                </div>
                <button
                  type="button"
                  class="company-collapse"
                  :class="{ collapsed: collapsedCompanies.has(item.group.key) }"
                  :aria-expanded="!collapsedCompanies.has(item.group.key)"
                  :aria-label="collapsedCompanies.has(item.group.key)
                    ? t('Развернуть компанию {company}', { company: item.group.name })
                    : t('Свернуть компанию {company}', { company: item.group.name })"
                  @click="toggleCompany(item.group.key)"
                ><BIcon name="chevron-right" :size="15" /></button>
              </div>

              <div
                v-else
                role="button"
                tabindex="0"
                :aria-label="t('Открыть карточку пользователя {name}', { name: item.user.full_name })"
                :class="[
                  'user-grid',
                  'user-row',
                  {
                    selected: selectedUser?.id === item.user.id,
                    checked: selectedIds.has(item.user.id),
                    inactive: !item.user.is_active,
                  },
                ]"
                :style="{ animationDelay: `${Math.min(item.rowIndex, 18) * 18}ms` }"
                @click="openUser(item.user)"
                @keydown.enter="openUser(item.user)"
                @keydown.space.prevent="toggleSelect(item.user.id)"
              >
                <label class="row-check" @click.stop>
                  <input
                    type="checkbox"
                    :checked="selectedIds.has(item.user.id)"
                    :aria-label="t('Выбрать {name}', { name: item.user.full_name })"
                    @change="toggleSelect(item.user.id)"
                  />
                </label>

                <div class="user-identity">
                  <UserCardAnchor :user-id="item.user.id" :preview="{ full_name: item.user.full_name, email: item.user.email }">
                    <UserAvatar
                      :email="item.user.email"
                      :full-name="item.user.full_name"
                      :avatar-url="item.user.avatar_url"
                      :size="36"
                      :status="presenceStatus(item.user.last_seen_at)"
                    />
                  </UserCardAnchor>
                  <div class="identity-copy">
                    <div class="identity-name">
                      <span>{{ item.user.full_name }}</span>
                      <b v-if="item.user.is_owner" class="owner-label">{{ t('Владелец') }}</b>
                    </div>
                    <div class="identity-email">{{ item.user.email }}</div>
                    <UserAffiliationBadge
                      v-if="item.user.job_title"
                      :job-title="item.user.job_title"
                      size="sm"
                      class="identity-title"
                    />
                  </div>
                </div>

                <div class="user-scope" :title="t(rowScopeLabel(item.user, item.membership))">
                  <span class="scope-icon"><BIcon name="building-bank" :size="13" /></span>
                  <span>{{ t(rowScopeLabel(item.user, item.membership)) }}</span>
                </div>

                <div class="user-roles" :title="rowRoleTitle(item.user, item.membership)">
                  <RoleChip
                    v-for="roleCode in rowRoleCodes(item.user, item.membership).slice(0, 2)"
                    :key="roleCode"
                    :code="roleCode"
                    size="sm"
                  />
                  <span v-if="rowRoleCodes(item.user, item.membership).length > 2" class="role-overflow">
                    +{{ rowRoleCodes(item.user, item.membership).length - 2 }}
                  </span>
                  <span v-if="!rowRoleCodes(item.user, item.membership).length" class="no-access">{{ t('Без ролей') }}</span>
                </div>

                <div class="activity-cell" :title="lastActivityTitle(item.user)">
                  <span :class="['activity-dot', `presence-${presenceStatus(item.user.last_seen_at)}`]"></span>
                  <div>
                    <b>{{ fmtLastActivity(item.user.last_seen_at) }}</b>
                    <small>{{ item.user.last_login_at ? t('Есть входы') : t('Нет истории входа') }}</small>
                  </div>
                </div>

                <div :class="['security-cell', `security-${pwdSeverity(item.user)}`]">
                  <BIcon :name="pwdSeverity(item.user) === 'ok' ? 'shield-check' : 'lock'" :size="13" />
                  <span>{{ t(pwdStatusLabel(item.user)) }}</span>
                </div>

                <div :class="['account-status', { off: !item.user.is_active }]">
                  <span></span>{{ item.user.is_active ? t('Активен') : t('Заблокирован') }}
                </div>

                <span class="row-open"><BIcon name="chevron-right" :size="15" /></span>
              </div>
            </template>

            <div v-if="!visibleUsers.length" class="registry-state empty-state">
              <span class="state-icon"><BIcon name="user-check" :size="23" /></span>
              <h2>{{ t('Пользователи не найдены') }}</h2>
              <p>{{ search ? t('Измените запрос или очистите поиск.') : t('Для этого фильтра пока нет записей.') }}</p>
              <button v-if="search" type="button" @click="clearSearch"><BIcon name="x" :size="14" /> {{ t('Очистить поиск') }}</button>
            </div>
          </div>
        </template>
      </section>

      <footer class="registry-footer">
        <span>{{ t(registryCaption) }}</span>
        <span v-if="refreshing" class="sync-status"><BIcon name="refresh" :size="11" /> {{ t('Обновление') }}</span>
        <span v-else class="sync-status ready"><i></i> {{ t('Данные актуальны') }}</span>
      </footer>
    </main>

    <Transition name="drawer-scrim">
      <button
        v-if="selectedUser"
        type="button"
        class="drawer-scrim"
        :aria-label="t('Закрыть карточку пользователя')"
        @click="closeDrawer"
      ></button>
    </Transition>

    <Transition name="user-drawer">
      <UserDetailDrawer
        v-if="selectedUser"
        :user="selectedUser"
        @close="closeDrawer"
        @changed="onUserChanged"
        @open-user="(id) => { const user = users.find(item => item.id === id); if (user) openUser(user); }"
      />
    </Transition>

    <BulkRolePickerModal
      v-if="showBulk"
      :selected-ids="Array.from(selectedIds)"
      @close="showBulk = false"
      @done="() => { selectedIds = new Set(); loadUsers(true); loadOverview(); }"
    />
  </div>
</template>

<style scoped>
.users-page {
  position: relative;
  display: grid;
  grid-template-columns: minmax(0, 1fr);
  height: calc(100dvh - 56px);
  min-height: calc(100dvh - 56px);
  overflow: hidden;
  color: var(--t1, #172033);
  background: #e8eaf0;
  transition: grid-template-columns .34s cubic-bezier(.22, 1, .36, 1);
}
.users-page.detail-open { grid-template-columns: minmax(0, 1fr) 540px; }
.users-page > * { min-height: 0; }
.users-page :deep(.rv3-drawer) { width: 100%; min-width: 0; }
.users-registry {
  min-width: 0;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  background: #f7f8fa;
}

.users-summary {
  min-height: 92px;
  display: grid;
  grid-template-columns: 230px minmax(0, 1fr);
  background: #fff;
  border-bottom: 1px solid #e4e7ed;
  animation: pageReveal .42s cubic-bezier(.22, 1, .36, 1) both;
}
.summary-intro {
  display: flex;
  flex-direction: column;
  justify-content: center;
  padding: 16px 22px;
}
.summary-eyebrow {
  margin-bottom: 3px;
  color: #6257c8;
  font-size: 9px;
  font-weight: 700;
  letter-spacing: 0;
  text-transform: uppercase;
}
.summary-intro h1 { margin: 0; color: #172033; font-size: 18px; font-weight: 680; letter-spacing: 0; }
.summary-intro p { margin: 4px 0 0; color: #7b8498; font-size: 10.5px; line-height: 1.35; }
.summary-metrics { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); }
.summary-metric {
  min-width: 0;
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 14px 18px;
  border-left: 1px solid #eceef2;
  /* Карточка сводки — кнопка-фильтр: сбрасываем стили кнопки и добавляем
     отклик на наведение/фокус, чтобы кликабельность читалась. */
  background: transparent;
  border-top: none; border-right: none; border-bottom: none;
  font: inherit; color: inherit; text-align: left; cursor: pointer;
  transition: background .16s ease, box-shadow .16s ease;
  opacity: 0;
  animation: metricReveal .38s cubic-bezier(.22, 1, .36, 1) forwards;
}
.summary-metric:hover { background: #f5f6f9; }
.summary-metric:focus-visible { outline: 2px solid #7C6FF7; outline-offset: -2px; }
/* Активный фильтр: подсветка карточки и её иконки */
.summary-metric.on { background: #f2f1fd; box-shadow: inset 0 -2px 0 #7C6FF7; }
.summary-metric.on .metric-icon { background: #e6e3fb; color: #5B4FD6; }
.metric-icon {
  width: 32px;
  height: 32px;
  flex: 0 0 32px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  color: #5f6879;
  background: #f0f2f5;
  border-radius: 7px;
}
.tone-positive .metric-icon { color: #18705b; background: #e8f5f1; }
.tone-negative .metric-icon { color: #a6383e; background: #fbecee; }
.tone-warning .metric-icon { color: #95630e; background: #fff4dc; }
.metric-copy { min-width: 0; display: flex; flex-direction: column; gap: 2px; }
.metric-copy strong { color: #20293a; font-size: 18px; font-weight: 680; line-height: 1; font-variant-numeric: tabular-nums; }
.metric-copy small { overflow: hidden; color: #7b8498; font-size: 9.5px; text-overflow: ellipsis; white-space: nowrap; }

.users-toolbar {
  min-height: 58px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  padding: 10px 18px;
  background: #fff;
  border-bottom: 1px solid #e4e7ed;
  animation: toolbarReveal .4s .12s cubic-bezier(.22, 1, .36, 1) both;
}
.filter-tabs { display: flex; align-items: center; gap: 3px; min-width: 0; }
.filter-tab {
  min-height: 32px;
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 0 10px;
  white-space: nowrap;
  color: #667085;
  background: transparent;
  border: 1px solid transparent;
  border-radius: 6px;
  font: inherit;
  font-size: 10.5px;
  font-weight: 580;
  cursor: pointer;
  transition: color .14s, background .14s, border-color .14s;
}
.filter-tab:hover { color: #30394c; background: #f4f5f8; }
.filter-tab.on { color: #5147ad; background: #f0eefb; border-color: #d9d5f3; }
.filter-tab.attention.on { color: #8a5b0b; background: #fff5df; border-color: #edd9a8; }
.filter-tab > span {
  min-width: 18px;
  padding: 1px 5px;
  text-align: center;
  color: inherit;
  background: rgba(23, 32, 51, .06);
  border-radius: 5px;
  font-size: 9px;
  font-variant-numeric: tabular-nums;
}
.toolbar-tools { min-width: 0; display: flex; align-items: center; gap: 7px; }
.view-mode {
  height: 34px;
  flex: 0 0 auto;
  display: inline-flex;
  align-items: center;
  padding: 2px;
  background: #f0f2f5;
  border: 1px solid #dfe3e9;
  border-radius: 7px;
}
.view-mode button {
  height: 28px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 5px;
  padding: 0 8px;
  color: #70798b;
  background: transparent;
  border: 0;
  border-radius: 5px;
  font: inherit;
  font-size: 9.5px;
  font-weight: 600;
  cursor: pointer;
  transition: color .14s, background .14s, box-shadow .14s;
}
.view-mode button:hover { color: #30394c; }
.view-mode button.on { color: #5147ad; background: #fff; box-shadow: 0 1px 3px rgba(23, 32, 51, .12); }
.users-search {
  width: clamp(210px, 24vw, 330px);
  height: 34px;
  display: flex;
  align-items: center;
  gap: 7px;
  padding: 0 9px;
  color: #8a92a3;
  background: #f7f8fa;
  border: 1px solid #dfe3e9;
  border-radius: 7px;
  transition: border-color .14s, box-shadow .14s, background .14s;
}
.users-search:focus-within { color: #6257c8; background: #fff; border-color: #8a82dc; box-shadow: 0 0 0 3px rgba(98, 87, 200, .1); }
.users-search input { min-width: 0; flex: 1; border: 0; outline: 0; color: #30394c; background: transparent; font: inherit; font-size: 11px; }
.users-search button {
  width: 22px;
  height: 22px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  padding: 0;
  color: #8a92a3;
  background: transparent;
  border: 0;
  border-radius: 5px;
  cursor: pointer;
}
.users-search button:hover { color: #30394c; background: #eceef2; }
.sort-control {
  height: 34px;
  display: flex;
  align-items: center;
  gap: 7px;
  padding: 0 8px;
  color: #8a92a3;
  background: #fff;
  border: 1px solid #dfe3e9;
  border-radius: 7px;
}
.sort-control > span { font-size: 9px; font-weight: 650; text-transform: uppercase; }
.sort-control select { max-width: 130px; border: 0; outline: 0; color: #4e586d; background: transparent; font: inherit; font-size: 10.5px; cursor: pointer; }
.refresh-button {
  width: 34px;
  height: 34px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  padding: 0;
  color: #667085;
  background: #fff;
  border: 1px solid #dfe3e9;
  border-radius: 7px;
  cursor: pointer;
}
.refresh-button:hover:not(:disabled) { color: #5147ad; background: #f4f2fc; border-color: #c9c4eb; }
.refresh-button:disabled { opacity: .55; cursor: default; }
.refresh-button.spinning :deep(svg), .sync-status:not(.ready) :deep(svg) { animation: spin .8s linear infinite; }

.bulk-actions {
  min-height: 52px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  padding: 8px 18px;
  color: #fff;
  background: #27334c;
  border-bottom: 1px solid #1e293e;
}
.bulk-count { display: flex; align-items: center; gap: 9px; }
.bulk-count > span {
  width: 30px;
  height: 30px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  color: #27334c;
  background: #fff;
  border-radius: 7px;
  font-size: 11px;
  font-weight: 700;
  font-variant-numeric: tabular-nums;
}
.bulk-count > div { display: flex; flex-direction: column; gap: 1px; }
.bulk-count b { font-size: 11px; font-weight: 650; }
.bulk-count small { color: rgba(255,255,255,.55); font-size: 9px; }
.bulk-buttons { display: flex; align-items: center; gap: 6px; }
.bulk-buttons button {
  min-height: 32px;
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 0 10px;
  color: #fff;
  background: rgba(255,255,255,.08);
  border: 1px solid rgba(255,255,255,.14);
  border-radius: 6px;
  font: inherit;
  font-size: 10.5px;
  font-weight: 600;
  cursor: pointer;
}
.bulk-buttons button:hover:not(:disabled) { background: rgba(255,255,255,.14); }
.bulk-buttons button.danger { color: #ffd8da; background: rgba(213, 66, 75, .18); border-color: rgba(243, 131, 137, .32); }
.bulk-buttons button:disabled { opacity: .5; cursor: default; }
.bulk-buttons .bulk-clear { width: 32px; padding: 0; justify-content: center; color: rgba(255,255,255,.65); background: transparent; border-color: transparent; }
.bulk-bar-enter-active, .bulk-bar-leave-active { transition: opacity .22s, transform .28s cubic-bezier(.22, 1, .36, 1); }
.bulk-bar-enter-from, .bulk-bar-leave-to { opacity: 0; transform: translateY(-10px); }

.truncated-notice {
  min-height: 38px;
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 7px 18px;
  color: #81560e;
  background: #fff7e5;
  border-bottom: 1px solid #edd9a8;
  font-size: 10.5px;
}
.registry-table { min-height: 0; flex: 1; display: flex; flex-direction: column; overflow: hidden; background: #fff; }
.registry-list { min-height: 0; flex: 1; overflow-y: auto; overscroll-behavior: contain; scrollbar-gutter: stable; }
.user-grid {
  display: grid;
  grid-template-columns: 36px minmax(230px, 1.35fr) minmax(130px, .72fr) minmax(170px, .9fr) 118px 128px 104px 24px;
  align-items: center;
  gap: 10px;
  padding: 0 18px;
}
.table-head {
  min-height: 38px;
  flex: 0 0 38px;
  color: #8a92a3;
  background: #f7f8fa;
  border-bottom: 1px solid #dfe3e9;
  font-size: 9px;
  font-weight: 650;
  text-transform: uppercase;
}
.select-all, .row-check { display: inline-flex; align-items: center; justify-content: flex-start; }
.select-all input, .row-check input, .company-check input { width: 14px; height: 14px; margin: 0; accent-color: #6257c8; cursor: pointer; }
.company-group-header {
  min-height: 42px;
  position: sticky;
  z-index: 3;
  top: 0;
  display: grid;
  grid-template-columns: 36px 30px minmax(180px, 1fr) auto 28px;
  align-items: center;
  gap: 8px;
  padding: 0 18px;
  color: #30394c;
  background: rgba(244, 246, 249, .97);
  border-top: 1px solid #d8dde5;
  border-bottom: 1px solid #d8dde5;
  backdrop-filter: blur(8px);
  animation: companyReveal .28s cubic-bezier(.22, 1, .36, 1) both;
}
.company-group-header:first-child { border-top: 0; }
.company-group-header.collapsed { background: rgba(248, 249, 251, .98); }
.company-check { display: inline-flex; align-items: center; }
.company-mark {
  width: 28px;
  height: 28px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  color: #5147ad;
  background: #ebe9f9;
  border-radius: 6px;
}
.company-heading { min-width: 0; display: flex; align-items: baseline; gap: 8px; }
.company-heading b { overflow: hidden; color: #273247; font-size: 11.5px; font-weight: 680; text-overflow: ellipsis; white-space: nowrap; }
.company-heading small { flex: 0 0 auto; color: #858d9c; font-size: 9px; }
.company-health { display: flex; align-items: center; justify-content: flex-end; gap: 11px; }
.company-health > span { display: inline-flex; align-items: center; gap: 5px; color: #6f788a; font-size: 9px; white-space: nowrap; }
.company-health i { width: 6px; height: 6px; border-radius: 50%; background: #268f77; }
.company-health .company-inactive i { background: #aeb5c0; }
.company-health .company-attention { color: #8a5b0b; }
.company-health .company-attention i { background: #d99a2b; }
.company-collapse {
  width: 28px;
  height: 28px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  padding: 0;
  color: #747d8f;
  background: transparent;
  border: 0;
  border-radius: 5px;
  cursor: pointer;
}
.company-collapse:hover { color: #5147ad; background: #e8e6f7; }
.company-collapse :deep(svg) { transform: rotate(90deg); transition: transform .24s cubic-bezier(.22, 1, .36, 1); }
.company-collapse.collapsed :deep(svg) { transform: rotate(0); }
.user-row {
  min-height: 62px;
  position: relative;
  color: #30394c;
  background: #fff;
  border-bottom: 1px solid #eceef2;
  outline: 0;
  cursor: pointer;
  opacity: 0;
  animation: rowReveal .34s cubic-bezier(.22, 1, .36, 1) forwards;
  transition: background .14s, box-shadow .14s, color .14s;
}
.user-row::before {
  content: '';
  position: absolute;
  inset: 8px auto 8px 0;
  width: 3px;
  background: #6257c8;
  border-radius: 0 3px 3px 0;
  opacity: 0;
  transform: scaleY(.4);
  transition: opacity .18s, transform .24s cubic-bezier(.22, 1, .36, 1);
}
.user-row:hover { z-index: 1; background: #fafafe; box-shadow: 0 4px 14px rgba(24, 32, 51, .055); }
.user-row:focus-visible { box-shadow: inset 0 0 0 2px rgba(98,87,200,.45); }
.user-row.selected { background: #f4f2fc; }
.user-row.selected::before { opacity: 1; transform: scaleY(1); }
.user-row.checked:not(.selected) { background: #f8f8fc; }
.user-row.inactive { color: #70798b; background: #fbfbfc; }
.user-row.inactive .user-identity, .user-row.inactive .user-scope, .user-row.inactive .user-roles { opacity: .67; }
.user-identity { min-width: 0; display: flex; align-items: center; gap: 10px; }
.identity-copy { min-width: 0; display: flex; flex-direction: column; gap: 2px; }
.identity-name { min-width: 0; display: flex; align-items: center; gap: 6px; }
.identity-name > span { overflow: hidden; color: #20293a; font-size: 12.5px; font-weight: 640; text-overflow: ellipsis; white-space: nowrap; }
.identity-email { overflow: hidden; color: #7b8498; font-size: 10.5px; text-overflow: ellipsis; white-space: nowrap; }
.owner-label {
  flex: 0 0 auto;
  padding: 2px 5px;
  color: #8a5b0b;
  background: #fff3d7;
  border: 1px solid #ecd59d;
  border-radius: 4px;
  font-size: 8px;
  font-weight: 700;
  text-transform: uppercase;
}
.identity-title { margin-top: 1px; }
.user-scope { min-width: 0; display: flex; align-items: center; gap: 7px; color: #596377; font-size: 10.5px; }
.user-scope > span:last-child { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.scope-icon {
  width: 24px;
  height: 24px;
  flex: 0 0 24px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  color: #687287;
  background: #f0f2f5;
  border-radius: 6px;
}
.user-roles { min-width: 0; display: flex; align-items: center; gap: 4px; overflow: hidden; }
.role-overflow {
  flex: 0 0 auto;
  padding: 2px 6px;
  color: #6257c8;
  background: #f0eefb;
  border-radius: 5px;
  font-size: 9px;
  font-weight: 650;
}
.no-access { color: #9a5d14; font-size: 10px; font-weight: 600; }
.activity-cell { min-width: 0; display: flex; align-items: center; gap: 7px; }
.activity-dot { width: 7px; height: 7px; flex: 0 0 7px; border-radius: 50%; background: #c5cad3; }
.activity-dot.presence-online { background: #268f77; box-shadow: 0 0 0 3px rgba(38,143,119,.1); }
.activity-dot.presence-away { background: #d99a2b; }
.activity-cell > div { min-width: 0; display: flex; flex-direction: column; gap: 2px; }
.activity-cell b { overflow: hidden; color: #4e586d; font-size: 10.5px; font-weight: 600; text-overflow: ellipsis; white-space: nowrap; }
.activity-cell small { color: #9aa1ae; font-size: 8.5px; }
.security-cell { min-width: 0; display: flex; align-items: center; gap: 5px; color: #7b8498; font-size: 9.5px; }
.security-cell span { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.security-ok { color: #21725f; }
.security-warning { color: #95630e; }
.security-critical { color: #a6383e; }
.security-unknown { color: #9199a8; }
.account-status { display: flex; align-items: center; gap: 6px; color: #21725f; font-size: 10px; font-weight: 620; }
.account-status > span { width: 6px; height: 6px; border-radius: 50%; background: #268f77; }
.account-status.off { color: #858d9c; }
.account-status.off > span { background: #b8bec8; }
.row-open { display: inline-flex; align-items: center; justify-content: center; color: #b1b7c2; transition: color .14s, transform .2s; }
.user-row:hover .row-open, .user-row.selected .row-open { color: #6257c8; transform: translateX(2px); }

.registry-footer {
  min-height: 34px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 0 18px;
  color: #858d9c;
  background: #fafbfc;
  border-top: 1px solid #e4e7ed;
  font-size: 9.5px;
}
.sync-status { display: inline-flex; align-items: center; gap: 5px; }
.sync-status.ready i { width: 6px; height: 6px; border-radius: 50%; background: #268f77; }
.registry-state {
  min-height: 280px;
  display: flex;
  flex: 1;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 36px;
  text-align: center;
}
.state-icon {
  width: 44px;
  height: 44px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  margin-bottom: 10px;
  color: #687287;
  background: #f0f2f5;
  border-radius: 7px;
}
.error-state .state-icon { color: #a6383e; background: #fbecee; }
.registry-state h2 { margin: 0; color: #30394c; font-size: 13px; font-weight: 650; letter-spacing: 0; }
.registry-state p { max-width: 420px; margin: 5px 0 13px; color: #858d9c; font-size: 10.5px; line-height: 1.45; }
.registry-state button {
  min-height: 32px;
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 0 11px;
  color: #5147ad;
  background: #f0eefb;
  border: 1px solid #d9d5f3;
  border-radius: 6px;
  font: inherit;
  font-size: 10.5px;
  font-weight: 600;
  cursor: pointer;
}

.skeleton-head span, .skeleton-row > span { height: 10px; background: #eceef2; border-radius: 4px; animation: skeletonPulse 1.35s ease-in-out infinite; }
.skeleton-row { min-height: 62px; border-bottom: 1px solid #eceef2; }
.skeleton-row > .skeleton-check { width: 14px; height: 14px; }
.skeleton-user { display: flex; align-items: center; gap: 10px; background: transparent !important; animation: none !important; }
.skeleton-user i { width: 36px; height: 36px; flex: 0 0 36px; background: #eceef2; border-radius: 50%; animation: skeletonPulse 1.35s ease-in-out infinite; }
.skeleton-user b { width: 55%; height: 10px; background: #eceef2; border-radius: 4px; animation: skeletonPulse 1.35s ease-in-out infinite; }

.drawer-scrim { display: none; }
.user-drawer-enter-active, .user-drawer-leave-active { transition: opacity .24s, transform .34s cubic-bezier(.22, 1, .36, 1); }
.user-drawer-enter-from, .user-drawer-leave-to { opacity: 0; transform: translateX(28px); }
.drawer-scrim-enter-active, .drawer-scrim-leave-active { transition: opacity .2s; }
.drawer-scrim-enter-from, .drawer-scrim-leave-to { opacity: 0; }

@keyframes pageReveal { from { opacity: 0; transform: translateY(-6px); } to { opacity: 1; transform: none; } }
@keyframes metricReveal { from { opacity: 0; transform: translateY(7px); } to { opacity: 1; transform: none; } }
@keyframes toolbarReveal { from { opacity: 0; transform: translateY(-4px); } to { opacity: 1; transform: none; } }
@keyframes companyReveal { from { opacity: 0; transform: translateY(-3px); } to { opacity: 1; transform: none; } }
@keyframes rowReveal { from { opacity: 0; transform: translateY(5px); } to { opacity: 1; transform: none; } }
@keyframes spin { to { transform: rotate(360deg); } }
@keyframes skeletonPulse { 0%, 100% { opacity: .55; } 50% { opacity: 1; } }

@media (max-width: 1500px) {
  .users-page.detail-open .user-grid {
    grid-template-columns: 36px minmax(210px, 1fr) minmax(150px, .8fr) 104px 24px;
  }
  .users-page.detail-open .user-grid > :nth-child(3),
  .users-page.detail-open .user-grid > :nth-child(5),
  .users-page.detail-open .user-grid > :nth-child(6) { display: none; }
  .users-page.detail-open .summary-intro { display: none; }
  .users-page.detail-open .users-summary { grid-template-columns: 1fr; }
}

@media (max-width: 1180px) {
  .users-page, .users-page.detail-open { grid-template-columns: minmax(0, 1fr); }
  .users-page :deep(.rv3-drawer) {
    position: absolute;
    z-index: 6;
    inset: 0 0 0 auto;
    width: min(540px, 100%);
    box-shadow: -20px 0 50px rgba(23,32,51,.16);
  }
  .drawer-scrim {
    position: absolute;
    z-index: 5;
    inset: 0;
    display: block;
    padding: 0;
    background: rgba(23, 32, 51, .24);
    border: 0;
    backdrop-filter: blur(2px);
    cursor: pointer;
  }
  .users-page.detail-open .summary-intro { display: flex; }
  .users-page.detail-open .users-summary { grid-template-columns: 230px minmax(0, 1fr); }
  .user-grid, .users-page.detail-open .user-grid {
    grid-template-columns: 36px minmax(220px, 1.25fr) minmax(160px, .8fr) 118px 104px 24px;
  }
  .user-grid > :nth-child(3), .user-grid > :nth-child(6),
  .users-page.detail-open .user-grid > :nth-child(3),
  .users-page.detail-open .user-grid > :nth-child(6) { display: none; }
  .users-page.detail-open .user-grid > :nth-child(5) { display: flex; }
}

@media (max-width: 940px) {
  .users-summary { grid-template-columns: 190px minmax(0, 1fr); }
  .summary-intro { padding-inline: 16px; }
  .summary-metric { padding-inline: 10px; }
  .metric-icon { display: none; }
  .users-toolbar { align-items: stretch; flex-direction: column; gap: 8px; }
  .filter-tabs { overflow-x: auto; padding-bottom: 1px; }
  .toolbar-tools { width: 100%; }
  .users-search { width: auto; flex: 1; }
  .company-group-header { grid-template-columns: 36px 30px minmax(160px, 1fr) auto 28px; }
  .company-attention { display: none !important; }
  .user-grid, .users-page.detail-open .user-grid {
    grid-template-columns: 36px minmax(210px, 1fr) minmax(160px, .8fr) 104px 24px;
  }
  .user-grid > :nth-child(3), .user-grid > :nth-child(5), .user-grid > :nth-child(6),
  .users-page.detail-open .user-grid > :nth-child(3),
  .users-page.detail-open .user-grid > :nth-child(5),
  .users-page.detail-open .user-grid > :nth-child(6) { display: none; }
}

@media (max-width: 680px) {
  .users-summary { min-height: auto; grid-template-columns: 1fr; }
  .summary-intro { min-height: 64px; padding: 11px 14px; border-bottom: 1px solid #eceef2; }
  .summary-intro p { display: none; }
  .summary-metrics { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .summary-metric { min-height: 52px; padding: 8px 14px; border-bottom: 1px solid #eceef2; }
  .metric-icon { display: inline-flex; width: 28px; height: 28px; flex-basis: 28px; }
  .metric-copy strong { font-size: 15px; }
  .users-toolbar { padding: 9px 12px; }
  .filter-tab { padding-inline: 8px; }
  .sort-control > span { display: none; }
  .sort-control select { width: 108px; }
  .bulk-actions { align-items: stretch; flex-direction: column; gap: 8px; padding: 9px 12px; }
  .bulk-buttons { width: 100%; }
  .bulk-buttons button:not(.bulk-clear) { flex: 1; justify-content: center; }
  .bulk-count small { display: none; }
  .truncated-notice { padding-inline: 12px; }
  .company-group-header {
    min-height: 40px;
    grid-template-columns: 28px 28px minmax(0, 1fr) 28px;
    gap: 7px;
    padding: 0 12px;
  }
  .company-health { display: none; }
  .company-heading { align-items: flex-start; flex-direction: column; gap: 1px; }
  .company-heading b { max-width: 100%; font-size: 10.5px; }
  .company-heading small { font-size: 8.5px; }
  .user-grid, .users-page.detail-open .user-grid {
    grid-template-columns: 28px minmax(0, 1fr) 94px 20px;
    gap: 7px;
    padding: 0 12px;
  }
  .user-grid > :nth-child(3), .user-grid > :nth-child(4), .user-grid > :nth-child(5), .user-grid > :nth-child(6),
  .users-page.detail-open .user-grid > :nth-child(3),
  .users-page.detail-open .user-grid > :nth-child(4),
  .users-page.detail-open .user-grid > :nth-child(5),
  .users-page.detail-open .user-grid > :nth-child(6) { display: none; }
  .user-row { min-height: 58px; }
  .identity-title { display: none; }
  .account-status { justify-self: end; font-size: 9px; }
  .registry-footer { padding-inline: 12px; }
  .sync-status { display: none; }
  .users-page :deep(.rv3-drawer) { width: 100%; }
}

@media (max-width: 460px) {
  .toolbar-tools { display: grid; grid-template-columns: minmax(0, 1fr) auto; }
  .view-mode { width: 100%; grid-column: 1 / -1; box-sizing: border-box; }
  .view-mode button { flex: 1; }
  .users-search { grid-column: 1 / -1; width: 100%; box-sizing: border-box; }
  .sort-control { min-width: 0; }
  .sort-control select { width: 130px; max-width: 100%; }
  .summary-metric { padding-inline: 10px; }
  .metric-icon { display: none; }
}

@media (prefers-reduced-motion: reduce) {
  .users-summary, .users-toolbar, .summary-metric, .company-group-header, .user-row { animation: none; opacity: 1; }
  .users-page, .user-drawer-enter-active, .user-drawer-leave-active,
  .bulk-bar-enter-active, .bulk-bar-leave-active { transition: none; }
}
</style>
