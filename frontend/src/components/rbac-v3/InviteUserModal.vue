<script setup lang="ts">
import { computed, onMounted, ref } from 'vue';
import {
  createUser,
  generatePassword,
  groupsApi,
  rolesApi,
  rbacV3Api,
  type RbacV3Group,
  type RbacV3Role,
} from '@/api/rbacV3';
import { companiesApi, type CompanyListItem, type SectorBrief } from '@/api/companies';
import ModalShell from '@/components/ModalShell.vue';
import BIcon from '@/components/broadcasts/BIcon.vue';
import { useI18n } from '@/composables/useI18n';
import { INTL_LOCALE } from '@/locale';
import { companyDisplayName, sectorDisplayName } from '@/utils/displayNames';
import RoleAssignmentPicker from './RoleAssignmentPicker.vue';

const props = defineProps<{
  prefill?: { full_name?: string; department?: string; role_codes?: string[] };
}>();

const emit = defineEmits<{
  (e: 'close'): void;
  (e: 'created', userId: string): void;
}>();
const { t, locale } = useI18n();

type ScopeMode = 'company' | 'sector' | 'global';
type BulkResult = {
  email: string;
  ok: boolean;
  password?: string;
  error?: string;
  emailSent?: boolean | null;
};

const email = ref('');
const fullName = ref(props.prefill?.full_name || '');
const department = ref(props.prefill?.department || '');
const jobTitle = ref('');
const organizationId = ref('');
const password = ref(generatePassword());
const mustChangePassword = ref(true);

const bulkMode = ref(false);
const bulkText = ref('');
const scopeMode = ref<ScopeMode>('company');
const selectedRoles = ref<string[]>(props.prefill?.role_codes || []);
const selectedSectors = ref<string[]>([]);

// ─── Маршрутизация модерации ───────────────────────────────────────
// Кому уходят правки этого пользователя (персонально) и какие секторы он
// сам ведёт как согласующий. Пусто в обоих полях — работает общий пул
// (владельцы + держатели moderation.review), как раньше.
const moderatorIds = ref<string[]>([]);
const moderatedSectors = ref<string[]>([]);
const moderatorQuery = ref('');
const moderatorPool = ref<{ id: string; full_name: string; email: string; job_title?: string | null }[]>([]);
const loadingModerators = ref(false);
const moderatorPoolError = ref<string | null>(null);

const moderatorOptions = computed(() => {
  const q = moderatorQuery.value.trim().toLowerCase();
  const rows = moderatorPool.value;
  if (!q) return rows.slice(0, 40);
  return rows.filter((u) =>
    u.full_name.toLowerCase().includes(q) || u.email.toLowerCase().includes(q),
  ).slice(0, 40);
});
const selectedModerators = computed(() =>
  moderatorPool.value.filter((u) => moderatorIds.value.includes(u.id)));

function toggleModerator(id: string) {
  const i = moderatorIds.value.indexOf(id);
  if (i >= 0) moderatorIds.value.splice(i, 1);
  else moderatorIds.value.push(id);
}
function toggleModeratedSector(code: string) {
  const i = moderatedSectors.value.indexOf(code);
  if (i >= 0) moderatedSectors.value.splice(i, 1);
  else moderatedSectors.value.push(code);
}

async function loadModeratorPool() {
  loadingModerators.value = true;
  moderatorPoolError.value = null;
  try {
    // Согласующими могут быть только внутренние сотрудники — внешний автор не
    // должен согласовывать сам себя или коллегу из своей же компании.
    const res = await rbacV3Api.listUsers({ is_active: true, limit: 200 });
    moderatorPool.value = (res.items || [])
      .filter((u: any) => !u.is_external)
      .map((u: any) => ({ id: u.id, full_name: u.full_name, email: u.email, job_title: u.job_title }));
  } catch (e: any) {
    // Тихий провал здесь означал бы «сотрудников нет» — говорим прямо.
    moderatorPoolError.value = e?.response?.data?.detail || t('Не удалось загрузить список сотрудников');
  } finally {
    loadingModerators.value = false;
  }
}
const companyRoleAssignments = ref<Record<string, string>>({});
const defaultCompanyRole = ref(props.prefill?.role_codes?.[0] || 'viewer');

const allRoles = ref<RbacV3Role[]>([]);
const companyGroups = ref<RbacV3Group[]>([]);
const sectors = ref<SectorBrief[]>([]);
const companyCatalog = ref<CompanyListItem[]>([]);
const companyById = computed(() => new Map(companyCatalog.value.map(company => [company.id, company])));
const allCompanies = computed(() => companyCatalog.value
  .map(company => ({ id: company.id, name: companyDisplayName(company) || company.code }))
  .filter(company => company.id)
  .sort((a, b) => a.name.localeCompare(b.name, INTL_LOCALE[locale.value])));
const companySearch = ref('');
const loadingCatalogs = ref(true);
const saving = ref(false);
const error = ref<string | null>(null);
const copied = ref(false);
const resultCopied = ref(false);
const bulkCopied = ref(false);
const singleResult = ref<{ email: string; password: string; emailSent: boolean | null } | null>(null);
const bulkResults = ref<BulkResult[] | null>(null);

onMounted(async () => {
  loadingCatalogs.value = true;
  try {
    const [roles, groups, loadedSectors, companies] = await Promise.all([
      rolesApi.list(),
      groupsApi.list().catch(() => []),
      companiesApi.listSectors().catch(() => []),
      companiesApi.list({ per_page: 500 } as any).catch(() => null),
    ]);
    allRoles.value = roles;
    if (!roles.some(role => role.code === defaultCompanyRole.value)) {
      defaultCompanyRole.value = roles.find(role => role.code === 'viewer')?.code || roles[0]?.code || '';
    }
    companyGroups.value = (groups || [])
      .filter(group => group.company_id)
      .sort((a, b) => a.name.localeCompare(b.name, INTL_LOCALE[locale.value]));
    sectors.value = loadedSectors || [];

    const items = (companies as any)?.items
      || (companies as any)?.companies
      || (Array.isArray(companies) ? companies : []);
    companyCatalog.value = items || [];
    void loadModeratorPool();   // список согласующих грузим независимо от каталогов
  } catch (e: any) {
    error.value = e?.response?.data?.detail || t('Не удалось загрузить роли и области доступа');
  } finally {
    loadingCatalogs.value = false;
  }
});

const roleByCode = computed<Record<string, RbacV3Role>>(() => {
  const result: Record<string, RbacV3Role> = {};
  for (const role of allRoles.value) result[role.code] = role;
  return result;
});

const selectedCompanyGroupIds = computed(() => Object.keys(companyRoleAssignments.value));
const localizedCompanyGroups = computed(() => {
  void locale.value;
  return companyGroups.value.map(group => ({
    ...group,
    name: group.company_id
      ? (companyDisplayName(companyById.value.get(group.company_id)) || group.name)
      : group.name,
  }));
});
const filteredCompanyGroups = computed(() => {
  const intlLocale = INTL_LOCALE[locale.value];
  const query = companySearch.value.trim().toLocaleLowerCase(intlLocale);
  return localizedCompanyGroups.value
    .filter(group => !query || `${group.name} ${group.code}`.toLocaleLowerCase(intlLocale).includes(query))
    .sort((a, b) => {
      const selectedDelta = Number(!!companyRoleAssignments.value[b.id]) - Number(!!companyRoleAssignments.value[a.id]);
      return selectedDelta || a.name.localeCompare(b.name, intlLocale);
    });
});

const parsedBulk = computed(() => {
  const rows: { email: string; full_name: string }[] = [];
  const seen = new Set<string>();
  for (const raw of bulkText.value.split('\n')) {
    const parts = raw.trim().split(/[,;\t]/);
    const rowEmail = (parts.shift() || '').trim().toLowerCase();
    if (!/^\S+@\S+\.\S+$/.test(rowEmail) || seen.has(rowEmail)) continue;
    seen.add(rowEmail);
    rows.push({
      email: rowEmail,
      full_name: parts.join(',').trim() || rowEmail.split('@')[0],
    });
  }
  return rows;
});

const profileValid = computed(() => bulkMode.value
  ? parsedBulk.value.length > 0
  : /^\S+@\S+\.\S+$/.test(email.value.trim()) && !!fullName.value.trim());

const accessValid = computed(() => {
  if (scopeMode.value === 'company') return selectedCompanyGroupIds.value.length > 0;
  if (scopeMode.value === 'sector') return selectedSectors.value.length > 0 && selectedRoles.value.length > 0;
  return selectedRoles.value.length > 0;
});

const creationReady = computed(() => profileValid.value && accessValid.value && !loadingCatalogs.value);
const hasResult = computed(() => !!singleResult.value || !!bulkResults.value);
const hasAdminRole = computed(() => {
  if (scopeMode.value === 'company') {
    return Object.values(companyRoleAssignments.value).includes('admin');
  }
  return selectedRoles.value.includes('admin');
});
const isDirty = computed(() => !!(
  email.value || fullName.value || department.value || jobTitle.value || organizationId.value
  || bulkText.value || selectedRoles.value.length || selectedSectors.value.length
  || selectedCompanyGroupIds.value.length
));

function roleName(code: string): string {
  return roleByCode.value[code]?.name_ru || code;
}

function sectorName(sector: SectorBrief): string {
  return sectorDisplayName(sector) || sector.code;
}

function formatCount(value: number): string {
  return value.toLocaleString(INTL_LOCALE[locale.value]);
}

const accessSummary = computed(() => {
  if (scopeMode.value === 'company') {
    const count = selectedCompanyGroupIds.value.length;
    if (!count) return t('Компании не выбраны');
    const roles = [...new Set(Object.values(companyRoleAssignments.value))].map(roleName);
    return t('Компаний: {count} · Роли: {roles}', {
      count: formatCount(count),
      roles: roles.join(', '),
    });
  }
  if (scopeMode.value === 'sector') {
    const count = selectedSectors.value.length;
    if (!count) return t('Секторы не выбраны');
    return t('Секторов: {count} · Роли: {roles}', {
      count: formatCount(count),
      roles: selectedRoles.value.map(roleName).join(', ') || t('Роль не выбрана'),
    });
  }
  return t('Вся платформа · Роли: {roles}', {
    roles: selectedRoles.value.map(roleName).join(', ') || t('Роль не выбрана'),
  });
});

const validationMessage = computed(() => {
  if (!profileValid.value) {
    return bulkMode.value
      ? t('Добавьте хотя бы один корректный email')
      : t('Заполните ФИО и корректный email');
  }
  if (scopeMode.value === 'company' && !selectedCompanyGroupIds.value.length) {
    return t('Выберите хотя бы одну компанию');
  }
  if (scopeMode.value === 'sector' && !selectedSectors.value.length) {
    return t('Выберите хотя бы один сектор');
  }
  if (scopeMode.value !== 'company' && !selectedRoles.value.length) return t('Выберите роль');
  return accessSummary.value;
});

function setBulkMode(value: boolean) {
  bulkMode.value = value;
  error.value = null;
}

function setScope(value: ScopeMode) {
  scopeMode.value = value;
  error.value = null;
}

function toggleSector(code: string) {
  selectedSectors.value = selectedSectors.value.includes(code)
    ? selectedSectors.value.filter(value => value !== code)
    : [...selectedSectors.value, code];
}

function toggleCompany(groupId: string) {
  const next = { ...companyRoleAssignments.value };
  if (next[groupId]) delete next[groupId];
  else if (defaultCompanyRole.value) next[groupId] = defaultCompanyRole.value;
  companyRoleAssignments.value = next;
}

function setCompanyRole(groupId: string, roleCode: string) {
  if (!companyRoleAssignments.value[groupId]) return;
  companyRoleAssignments.value = {
    ...companyRoleAssignments.value,
    [groupId]: roleCode,
  };
}

function applyDefaultRole() {
  if (!defaultCompanyRole.value) return;
  companyRoleAssignments.value = Object.fromEntries(
    selectedCompanyGroupIds.value.map(groupId => [groupId, defaultCompanyRole.value]),
  );
}

function companyGroupMemberships(): Array<{ group_id: string; role_code: string }> | undefined {
  if (scopeMode.value !== 'company') return undefined;
  return Object.entries(companyRoleAssignments.value).map(([group_id, role_code]) => ({
    group_id,
    role_code,
  }));
}

function regeneratePassword() {
  password.value = generatePassword();
  copied.value = false;
}

async function copyText(value: string, target: 'password' | 'result' | 'bulk') {
  await navigator.clipboard.writeText(value);
  if (target === 'password') copied.value = true;
  if (target === 'result') resultCopied.value = true;
  if (target === 'bulk') bulkCopied.value = true;
  window.setTimeout(() => {
    if (target === 'password') copied.value = false;
    if (target === 'result') resultCopied.value = false;
    if (target === 'bulk') bulkCopied.value = false;
  }, 1800);
}

async function createOne(rowEmail: string, name: string, rowPassword: string) {
  return createUser({
    email: rowEmail,
    full_name: name,
    department: department.value.trim() || undefined,
    job_title: bulkMode.value ? undefined : jobTitle.value.trim() || undefined,
    organization_id: bulkMode.value ? undefined : organizationId.value || undefined,
    password: rowPassword,
    must_change_password: mustChangePassword.value,
    role_codes: scopeMode.value === 'company' ? [] : selectedRoles.value,
    allowed_sectors: scopeMode.value === 'sector' ? selectedSectors.value : undefined,
    moderator_ids: moderatorIds.value.length ? moderatorIds.value : undefined,
    moderated_sector_codes: moderatedSectors.value.length ? moderatedSectors.value : undefined,
    group_memberships: companyGroupMemberships(),
  });
}

async function submit() {
  if (!creationReady.value || saving.value) {
    error.value = validationMessage.value;
    return;
  }

  saving.value = true;
  error.value = null;
  try {
    if (bulkMode.value) {
      const results: BulkResult[] = [];
      for (const row of parsedBulk.value) {
        const rowPassword = generatePassword();
        try {
          const created = await createOne(row.email, row.full_name, rowPassword);
          results.push({
            email: row.email,
            password: rowPassword,
            ok: true,
            emailSent: created.invite_email_sent ?? null,
          });
        } catch (e: any) {
          results.push({
            email: row.email,
            ok: false,
            error: e?.response?.data?.detail || t('Не удалось создать пользователя'),
          });
        }
      }
      bulkResults.value = results;
      emit('created', '');
      return;
    }

    const created = await createOne(email.value.trim(), fullName.value.trim(), password.value);
    singleResult.value = {
      email: created.email,
      password: password.value,
      emailSent: created.invite_email_sent ?? null,
    };
    emit('created', created.id);
  } catch (e: any) {
    error.value = e?.response?.data?.detail || t('Не удалось создать пользователя');
  } finally {
    saving.value = false;
  }
}

function copyCredentials() {
  if (!singleResult.value) return;
  copyText(`${singleResult.value.email}\t${singleResult.value.password}`, 'result');
}

function copyBulkResults() {
  const value = (bulkResults.value || [])
    .filter(result => result.ok)
    .map(result => `${result.email}\t${result.password}`)
    .join('\n');
  copyText(value, 'bulk');
}

function requestClose() {
  if (!saving.value) emit('close');
}
</script>

<template>
  <ModalShell
    :open="true"
    size="xl"
    :dirty="isDirty && !hasResult && !saving"
    :close-on-overlay="!saving"
    :hide-close="saving"
    :confirm-text="t('Закрыть форму? Введённые данные будут потеряны.')"
    @close="requestClose"
  >
    <template #header>
      <div class="iu-header">
        <div>
          <h2>{{ prefill ? t('Создать похожего пользователя') : t('Создать пользователя') }}</h2>
          <p v-if="!hasResult">{{ t('Профиль и доступ сохранятся одной операцией') }}</p>
        </div>
        <div v-if="!prefill && !hasResult" class="iu-mode" :aria-label="t('Режим создания')">
          <button type="button" :class="{ on: !bulkMode }" @click="setBulkMode(false)">{{ t('Один') }}</button>
          <button type="button" :class="{ on: bulkMode }" @click="setBulkMode(true)">{{ t('Несколько') }}</button>
        </div>
      </div>
    </template>

    <div v-if="singleResult" class="iu-success">
      <div class="iu-success-icon"><BIcon name="user-check" :size="26" /></div>
      <h3>{{ t('Пользователь создан') }}</h3>
      <p v-if="singleResult.emailSent === true" class="iu-success-note ok">
        {{ t('Приглашение отправлено на {email}', { email: singleResult.email }) }}
      </p>
      <p v-else-if="singleResult.emailSent === false" class="iu-success-note warn">
        {{ t('Письмо не отправлено. Передайте временный пароль безопасным способом.') }}
      </p>
      <p v-else class="iu-success-note neutral">
        {{ t('Статус доставки письма недоступен. Данные для входа сохранены ниже.') }}
      </p>
      <div class="iu-credentials">
        <div><span>{{ t('Логин') }}</span><code>{{ singleResult.email }}</code></div>
        <div><span>{{ t('Временный пароль') }}</span><code>{{ singleResult.password }}</code></div>
      </div>
      <button type="button" class="iu-copy-result" @click="copyCredentials">
        <BIcon :name="resultCopied ? 'check' : 'copy'" :size="15" />
        {{ resultCopied ? t('Скопировано') : t('Скопировать данные для входа') }}
      </button>
    </div>

    <div v-else-if="bulkResults" class="iu-success iu-success-bulk">
      <div class="iu-success-icon"><BIcon name="user-check" :size="26" /></div>
      <h3>{{ t('Создано: {created} из {total}', {
        created: formatCount(bulkResults.filter(result => result.ok).length),
        total: formatCount(bulkResults.length),
      }) }}</h3>
      <div class="iu-result-list">
        <div
          v-for="result in bulkResults"
          :key="result.email"
          :class="['iu-result-row', { failed: !result.ok }]"
        >
          <BIcon :name="result.ok ? 'check' : 'x'" :size="14" />
          <span class="iu-result-email">{{ result.email }}</span>
          <code v-if="result.ok">{{ result.password }}</code>
          <span v-else class="iu-result-error">{{ result.error }}</span>
        </div>
      </div>
      <button
        v-if="bulkResults.some(result => result.ok)"
        type="button"
        class="iu-copy-result"
        @click="copyBulkResults"
      >
        <BIcon :name="bulkCopied ? 'check' : 'copy'" :size="15" />
        {{ bulkCopied ? t('Скопировано') : t('Скопировать логины и пароли') }}
      </button>
    </div>

    <div v-else class="iu-layout">
      <section class="iu-profile" aria-labelledby="iu-profile-heading">
        <div class="iu-section-head">
          <span class="iu-section-icon"><BIcon name="user-check" :size="17" /></span>
          <div>
            <h3 id="iu-profile-heading">{{ t('Учётная запись') }}</h3>
            <p>{{ bulkMode
              ? t('Распознано: {count}', { count: formatCount(parsedBulk.length) })
              : t('Основные данные пользователя') }}</p>
          </div>
        </div>

        <div v-if="bulkMode" class="iu-field">
          <label for="iu-bulk-users">{{ t('Email и ФИО') }}</label>
          <textarea
            id="iu-bulk-users"
            v-model="bulkText"
            rows="9"
            :placeholder="t('user@company.uz, Имя Фамилия')"
            spellcheck="false"
          ></textarea>
          <span class="iu-field-meta">{{ t('Корректных записей: {count}', { count: formatCount(parsedBulk.length) }) }}</span>
        </div>

        <template v-else>
          <div class="iu-field">
            <label for="iu-full-name">{{ t('ФИО') }} <b>*</b></label>
            <input id="iu-full-name" v-model="fullName" autocomplete="name" :placeholder="t('Имя Фамилия')" />
          </div>
          <div class="iu-field">
            <label for="iu-email">{{ t('Рабочий email') }} <b>*</b></label>
            <input id="iu-email" v-model="email" type="email" autocomplete="email" placeholder="name@company.uz" />
          </div>
          <div class="iu-field-grid">
            <div class="iu-field">
              <label for="iu-department">{{ t('Подразделение') }}</label>
              <input id="iu-department" v-model="department" autocomplete="organization-title" :placeholder="t('Департамент')" />
            </div>
            <div class="iu-field">
              <label for="iu-job-title">{{ t('Должность') }}</label>
              <input id="iu-job-title" v-model="jobTitle" autocomplete="organization-title" :placeholder="t('Должность')" />
            </div>
          </div>
          <div class="iu-field">
            <label for="iu-organization">{{ t('Организация') }}</label>
            <select id="iu-organization" v-model="organizationId">
              <option value="">{{ t('Не выбрана') }}</option>
              <option v-for="company in allCompanies" :key="company.id" :value="company.id">
                {{ company.name }}
              </option>
            </select>
          </div>
        </template>

        <div v-if="bulkMode" class="iu-field">
          <label for="iu-bulk-department">{{ t('Подразделение') }}</label>
          <input id="iu-bulk-department" v-model="department" :placeholder="t('Общее для списка')" />
        </div>

        <div v-if="!bulkMode" class="iu-password">
          <div class="iu-field">
            <label for="iu-password">{{ t('Временный пароль') }}</label>
            <div class="iu-password-control">
              <input id="iu-password" v-model="password" autocomplete="new-password" spellcheck="false" />
              <button
                type="button"
                :title="copied ? t('Скопировано') : t('Скопировать пароль')"
                :aria-label="copied ? t('Скопировано') : t('Скопировать пароль')"
                @click="copyText(password, 'password')"
              ><BIcon :name="copied ? 'check' : 'copy'" :size="14" /></button>
              <button type="button" :title="t('Создать другой пароль')" :aria-label="t('Создать другой пароль')" @click="regeneratePassword">
                <BIcon name="refresh" :size="14" />
              </button>
            </div>
          </div>
        </div>

        <label class="iu-check-row">
          <input v-model="mustChangePassword" type="checkbox" />
          <span>
            <b>{{ t('Сменить пароль при первом входе') }}</b>
            <small>{{ t('Активные разделы откроются после смены') }}</small>
          </span>
        </label>
      </section>

      <section class="iu-access" aria-labelledby="iu-access-heading">
        <div class="iu-section-head iu-access-head">
          <span class="iu-section-icon access"><BIcon name="shield-check" :size="17" /></span>
          <div>
            <h3 id="iu-access-heading">{{ t('Доступ и роли') }}</h3>
            <p>{{ accessSummary }}</p>
          </div>
        </div>

        <div class="iu-scope" role="tablist" :aria-label="t('Область доступа')">
          <button
            type="button"
            role="tab"
            :aria-selected="scopeMode === 'company'"
            :class="{ on: scopeMode === 'company' }"
            @click="setScope('company')"
          >
            <BIcon name="building-bank" :size="17" />
            <span><b>{{ t('Компании') }}</b><small>{{ t('Роль для каждой компании') }}</small></span>
          </button>
          <button
            type="button"
            role="tab"
            :aria-selected="scopeMode === 'sector'"
            :class="{ on: scopeMode === 'sector' }"
            @click="setScope('sector')"
          >
            <BIcon name="route" :size="17" />
            <span><b>{{ t('Секторы') }}</b><small>{{ t('Все компании сектора') }}</small></span>
          </button>
          <button
            type="button"
            role="tab"
            :aria-selected="scopeMode === 'global'"
            :class="{ on: scopeMode === 'global' }"
            @click="setScope('global')"
          >
            <BIcon name="shield-check" :size="17" />
            <span><b>{{ t('Вся платформа') }}</b><small>{{ t('Без ограничения компаний') }}</small></span>
          </button>
        </div>

        <div v-if="scopeMode === 'company'" class="iu-company-access">
          <div class="iu-access-toolbar">
            <label class="iu-search">
              <BIcon name="search" :size="14" />
              <input v-model="companySearch" type="search" autocomplete="off" :placeholder="t('Найти компанию')" />
              <button v-if="companySearch" type="button" :title="t('Очистить поиск')" :aria-label="t('Очистить поиск')" @click="companySearch = ''">
                <BIcon name="x" :size="13" />
              </button>
            </label>
            <div class="iu-bulk-role">
              <span>{{ t('Роль для выбранных') }}</span>
              <select v-model="defaultCompanyRole" :disabled="!selectedCompanyGroupIds.length">
                <option v-for="role in allRoles" :key="role.code" :value="role.code">{{ role.name_ru }}</option>
              </select>
              <button
                type="button"
                :disabled="!selectedCompanyGroupIds.length"
                :title="t('Применить роль ко всем выбранным компаниям')"
                @click="applyDefaultRole"
              >{{ t('Применить') }}</button>
            </div>
          </div>

          <div class="iu-company-list">
            <div v-if="loadingCatalogs" class="iu-empty">{{ t('Загрузка компаний...') }}</div>
            <div v-else-if="!companyGroups.length" class="iu-empty">{{ t('Компании с группами доступа не найдены') }}</div>
            <div v-else-if="!filteredCompanyGroups.length" class="iu-empty">{{ t('Компании не найдены') }}</div>
            <div
              v-for="group in filteredCompanyGroups"
              :key="group.id"
              :class="['iu-company-row', { on: !!companyRoleAssignments[group.id] }]"
            >
              <button type="button" class="iu-company-toggle" @click="toggleCompany(group.id)">
                <span class="iu-select-control">
                  <BIcon v-if="companyRoleAssignments[group.id]" name="check" :size="12" />
                </span>
                <span class="iu-company-copy">
                  <b>{{ group.name }}</b>
                  <small>{{ group.code }}</small>
                </span>
              </button>
              <select
                :value="companyRoleAssignments[group.id] || defaultCompanyRole"
                :disabled="!companyRoleAssignments[group.id]"
                :aria-label="t('Роль в компании {company}', { company: group.name })"
                @change="setCompanyRole(group.id, ($event.target as HTMLSelectElement).value)"
              >
                <option v-for="role in allRoles" :key="role.code" :value="role.code">{{ role.name_ru }}</option>
              </select>
            </div>
          </div>
        </div>

        <div v-else-if="scopeMode === 'sector'" class="iu-sector-access">
          <div class="iu-subheading">
            <span>{{ t('Секторы') }}</span>
            <b>{{ t('Выбрано: {count}', { count: formatCount(selectedSectors.length) }) }}</b>
          </div>
          <div class="iu-sector-list">
            <button
              v-for="sector in sectors"
              :key="sector.code"
              type="button"
              :class="{ on: selectedSectors.includes(sector.code) }"
              @click="toggleSector(sector.code)"
            >
              <span class="iu-select-control"><BIcon v-if="selectedSectors.includes(sector.code)" name="check" :size="12" /></span>
              <span class="iu-sector-dot" :style="{ background: sector.color_hex || '#6257c8' }"></span>
              {{ sectorName(sector) }}
            </button>
            <div v-if="!loadingCatalogs && !sectors.length" class="iu-empty">{{ t('Секторы не найдены') }}</div>
          </div>
          <div class="iu-subheading roles"><span>{{ t('Роли в выбранных секторах') }}</span></div>
          <RoleAssignmentPicker v-model="selectedRoles" :roles="allRoles" compact />
        </div>

        <div v-else class="iu-global-access">
          <!-- Текст правится по факту бэкенда: «вся платформа» НЕ выдаёт данные всех
               компаний сама по себе. app/core/access.py::has_unrestricted_view снимает
               per-company фильтр только для owner и носителей companies.view_all; без
               группы/сектора и без этого права список компаний у пользователя пуст.
               Прежняя формулировка обещала доступ, который бэкенд не даёт. -->
          <div class="iu-global-note">
            <BIcon name="info-circle" :size="16" />
            <span>{{ t('Ограничение по компаниям не задаётся. Данные всех компаний откроются только если выбранная роль несёт право companies.view_all; иначе список компаний останется пустым. Выберите область «Компании» или «Секторы».') }}</span>
          </div>
          <div class="iu-subheading roles"><span>{{ t('Роли на платформе') }}</span></div>
          <RoleAssignmentPicker v-model="selectedRoles" :roles="allRoles" compact />
        </div>

        <div v-if="hasAdminRole" class="iu-admin-warning">
          <BIcon name="lock" :size="15" />
          <span>{{ t('Роль admin даёт полный доступ и может назначаться только владельцем платформы.') }}</span>
        </div>
      </section>

      <!-- Маршрутизация модерации: кто согласует правки и что человек ведёт сам -->
      <section class="iu-section iu-mod">
        <div class="iu-section-head">
          <h3>{{ t('Модерация') }}</h3>
          <span class="iu-section-hint">{{ t('Необязательно') }}</span>
        </div>

        <div class="iu-mod-block">
          <div class="iu-subheading">
            <span>{{ t('Согласующие для этого пользователя') }}</span>
            <b v-if="moderatorIds.length">{{ t('Выбрано: {count}', { count: formatCount(moderatorIds.length) }) }}</b>
          </div>
          <p class="iu-mod-note">{{ t('Правки уйдут именно им. Если никого не выбрать — заявку увидят все, кто ведёт модерацию.') }}</p>
          <div v-if="selectedModerators.length" class="iu-mod-chips">
            <button v-for="m in selectedModerators" :key="m.id" type="button" class="iu-mod-chip"
                    @click="toggleModerator(m.id)">
              {{ m.full_name }}
              <BIcon name="x" :size="11" />
            </button>
          </div>
          <input v-model="moderatorQuery" type="text" class="iu-input"
                 :placeholder="t('Поиск сотрудника по имени или почте')" />
          <div v-if="moderatorPoolError" class="iu-mod-err">{{ moderatorPoolError }}</div>
          <div v-else-if="loadingModerators" class="iu-empty">{{ t('Загрузка…') }}</div>
          <div v-else class="iu-mod-list">
            <button v-for="u in moderatorOptions" :key="u.id" type="button"
                    :class="{ on: moderatorIds.includes(u.id) }" @click="toggleModerator(u.id)">
              <span class="iu-select-control"><BIcon v-if="moderatorIds.includes(u.id)" name="check" :size="12" /></span>
              <span class="iu-mod-person">
                <b>{{ u.full_name }}</b>
                <small>{{ u.job_title || u.email }}</small>
              </span>
            </button>
            <div v-if="!moderatorOptions.length" class="iu-empty">{{ t('Никого не нашлось') }}</div>
          </div>
        </div>

        <div class="iu-mod-block">
          <div class="iu-subheading">
            <span>{{ t('Ведёт модерацию по секторам') }}</span>
            <b v-if="moderatedSectors.length">{{ t('Выбрано: {count}', { count: formatCount(moderatedSectors.length) }) }}</b>
          </div>
          <p class="iu-mod-note">{{ t('Заявки авторов из компаний этих секторов будут приходить этому пользователю. Право «Модерация: рассмотрение» выдастся автоматически.') }}</p>
          <div class="iu-sector-list">
            <button v-for="sector in sectors" :key="sector.code" type="button"
                    :class="{ on: moderatedSectors.includes(sector.code) }"
                    @click="toggleModeratedSector(sector.code)">
              <span class="iu-select-control"><BIcon v-if="moderatedSectors.includes(sector.code)" name="check" :size="12" /></span>
              <span class="iu-sector-dot" :style="{ background: sector.color_hex || '#6257c8' }"></span>
              {{ sectorName(sector) }}
            </button>
            <div v-if="!loadingCatalogs && !sectors.length" class="iu-empty">{{ t('Секторы не найдены') }}</div>
          </div>
        </div>
      </section>
    </div>

    <div v-if="error && !hasResult" class="iu-error" role="alert">
      <BIcon name="info-circle" :size="15" />
      <span>{{ error }}</span>
    </div>

    <template #footer>
      <div class="iu-footer">
        <div v-if="!hasResult" :class="['iu-summary', { ready: creationReady }]">
          <BIcon :name="creationReady ? 'shield-check' : 'info-circle'" :size="16" />
          <span>{{ creationReady ? accessSummary : validationMessage }}</span>
        </div>
        <div class="iu-footer-actions">
          <button type="button" class="iu-btn secondary" :disabled="saving" @click="requestClose">
            {{ hasResult ? t('Закрыть') : t('Отмена') }}
          </button>
          <button
            v-if="!hasResult"
            type="button"
            class="iu-btn primary"
            :disabled="saving || !creationReady"
            @click="submit"
          >
            <BIcon v-if="!saving" name="user-check" :size="15" />
            {{ saving
              ? t('Создание...')
              : (bulkMode
                ? t('Создать пользователей: {count}', { count: formatCount(parsedBulk.length) })
                : t('Создать пользователя')) }}
          </button>
        </div>
      </div>
    </template>
  </ModalShell>
</template>

<style scoped>
.iu-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 20px;
}
.iu-header h2 { margin: 0; color: var(--t1, #172033); font-size: 16px; font-weight: 650; letter-spacing: 0; }
.iu-header p { margin: 3px 0 0; color: var(--t3, #7b8498); font-size: 11px; }
.iu-mode {
  display: inline-grid;
  grid-template-columns: 1fr 1fr;
  padding: 3px;
  background: #eff1f5;
  border-radius: 7px;
}
.iu-mode button {
  min-width: 92px;
  height: 28px;
  padding: 0 12px;
  color: #687287;
  background: transparent;
  border: 0;
  border-radius: 5px;
  font: inherit;
  font-size: 11px;
  font-weight: 600;
  cursor: pointer;
}
.iu-mode button.on { color: #30394c; background: #fff; box-shadow: 0 1px 4px rgba(31, 38, 58, .12); }
.iu-layout {
  display: grid;
  grid-template-columns: minmax(300px, 340px) minmax(0, 1fr);
  min-height: 580px;
  margin: -22px;
}
.iu-profile,
.iu-access { min-width: 0; padding: 22px; }
.iu-profile { background: #fafbfc; border-right: 1px solid var(--border-hard, #e2e5ec); }
.iu-access { background: #fff; }
.iu-section-head {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 18px;
}
.iu-section-icon {
  width: 34px;
  height: 34px;
  flex: 0 0 34px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  color: #286c5d;
  background: rgba(38, 143, 119, .1);
  border-radius: 7px;
}
.iu-section-icon.access { color: #554ab6; background: rgba(98, 87, 200, .1); }
.iu-section-head h3 { margin: 0; color: var(--t1, #172033); font-size: 13px; font-weight: 650; letter-spacing: 0; }
.iu-section-head p {
  max-width: 560px;
  margin: 2px 0 0;
  overflow: hidden;
  color: var(--t3, #7b8498);
  font-size: 10.5px;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.iu-access-head { margin-bottom: 14px; }
.iu-field { display: flex; flex-direction: column; gap: 6px; margin-bottom: 13px; }
.iu-field-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 9px; }
.iu-field label {
  color: #606a7f;
  font-size: 10.5px;
  font-weight: 600;
}
.iu-field label b { color: #c64141; }
.iu-field input,
.iu-field select,
.iu-field textarea {
  width: 100%;
  box-sizing: border-box;
  color: var(--t1, #172033);
  background: #fff;
  border: 1px solid var(--border-hard, #dfe3ea);
  border-radius: 7px;
  outline: 0;
  font: inherit;
  font-size: 12px;
}
.iu-field input,
.iu-field select { height: 36px; padding: 0 10px; }
.iu-field textarea { min-height: 184px; padding: 10px; resize: vertical; line-height: 1.55; }
.iu-field input:focus,
.iu-field select:focus,
.iu-field textarea:focus { border-color: #8a82dc; box-shadow: 0 0 0 3px rgba(98, 87, 200, .1); }
.iu-field-meta { align-self: flex-end; color: var(--t3, #7b8498); font-size: 10px; }
.iu-password { margin-top: 4px; padding-top: 14px; border-top: 1px solid var(--border-hard, #e2e5ec); }
.iu-password-control { display: grid; grid-template-columns: 1fr 34px 34px; }
.iu-password-control input { border-radius: 7px 0 0 7px; font-family: var(--font-mono, ui-monospace, monospace); }
.iu-password-control button {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  padding: 0;
  color: #657087;
  background: #f5f6f9;
  border: 1px solid var(--border-hard, #dfe3ea);
  border-left: 0;
  cursor: pointer;
}
.iu-password-control button:last-child { border-radius: 0 7px 7px 0; }
.iu-password-control button:hover { color: #5147ad; background: #eeecfb; }
.iu-check-row {
  display: flex;
  align-items: flex-start;
  gap: 9px;
  margin-top: 4px;
  color: #30394c;
  cursor: pointer;
}
.iu-check-row input { width: 15px; height: 15px; margin: 1px 0 0; accent-color: #6257c8; }
.iu-check-row span { display: flex; flex-direction: column; gap: 2px; }
.iu-check-row b { font-size: 10.5px; font-weight: 600; }
.iu-check-row small { color: var(--t3, #7b8498); font-size: 9.5px; line-height: 1.35; }
.iu-scope {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 6px;
  margin-bottom: 16px;
}
.iu-scope > button {
  min-width: 0;
  min-height: 58px;
  display: flex;
  align-items: center;
  gap: 9px;
  padding: 9px 10px;
  text-align: left;
  color: #657087;
  background: #f8f9fb;
  border: 1px solid var(--border-hard, #e2e5ec);
  border-radius: 7px;
  font: inherit;
  cursor: pointer;
}
.iu-scope > button:hover { border-color: #b6b1e7; }
.iu-scope > button.on { color: #5147ad; background: rgba(98, 87, 200, .065); border-color: #8a82dc; }
.iu-scope span { min-width: 0; display: flex; flex-direction: column; gap: 2px; }
.iu-scope b { font-size: 11.5px; font-weight: 650; }
.iu-scope small { overflow: hidden; color: #8790a2; font-size: 9.5px; text-overflow: ellipsis; white-space: nowrap; }
.iu-access-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  margin-bottom: 9px;
}
.iu-search {
  width: min(260px, 100%);
  height: 34px;
  display: flex;
  align-items: center;
  gap: 7px;
  padding: 0 9px;
  color: #7b8498;
  background: #f7f8fb;
  border: 1px solid var(--border-hard, #e2e5ec);
  border-radius: 7px;
}
.iu-search:focus-within { color: #6257c8; border-color: #8a82dc; box-shadow: 0 0 0 3px rgba(98, 87, 200, .1); }
.iu-search input { min-width: 0; flex: 1; border: 0; outline: 0; background: transparent; font: inherit; font-size: 11.5px; }
.iu-search button { display: inline-flex; padding: 3px; color: inherit; background: transparent; border: 0; cursor: pointer; }
.iu-bulk-role { display: flex; align-items: center; gap: 6px; white-space: nowrap; }
.iu-bulk-role span { color: #7b8498; font-size: 10px; }
.iu-bulk-role select {
  width: 150px;
  height: 32px;
  padding: 0 7px;
  color: #30394c;
  background: #fff;
  border: 1px solid var(--border-hard, #e2e5ec);
  border-radius: 6px;
  font: inherit;
  font-size: 10.5px;
}
.iu-bulk-role button {
  height: 32px;
  padding: 0 10px;
  color: #5147ad;
  background: rgba(98, 87, 200, .08);
  border: 1px solid rgba(98, 87, 200, .22);
  border-radius: 6px;
  font: inherit;
  font-size: 10.5px;
  font-weight: 600;
  cursor: pointer;
}
.iu-bulk-role button:disabled,
.iu-bulk-role select:disabled { opacity: .45; cursor: default; }
.iu-company-list {
  display: flex;
  flex-direction: column;
  max-height: 390px;
  overflow-y: auto;
  border-top: 1px solid var(--border-hard, #e2e5ec);
}
.iu-company-row {
  min-height: 48px;
  display: grid;
  grid-template-columns: minmax(0, 1fr) 200px;
  align-items: center;
  gap: 12px;
  padding: 7px 8px;
  border-bottom: 1px solid var(--border-hard, #e2e5ec);
}
.iu-company-row.on { background: rgba(98, 87, 200, .045); }
.iu-company-toggle {
  min-width: 0;
  display: flex;
  align-items: center;
  gap: 9px;
  padding: 0;
  text-align: left;
  color: #30394c;
  background: transparent;
  border: 0;
  font: inherit;
  cursor: pointer;
}
.iu-select-control {
  width: 18px;
  height: 18px;
  flex: 0 0 18px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  color: #fff;
  background: #fff;
  border: 1px solid #c7ccd6;
  border-radius: 5px;
}
.on > .iu-select-control,
.iu-company-row.on .iu-select-control { background: #6257c8; border-color: #6257c8; }
.iu-company-copy { min-width: 0; display: flex; flex-direction: column; gap: 2px; }
.iu-company-copy b { overflow: hidden; font-size: 11.5px; font-weight: 600; text-overflow: ellipsis; white-space: nowrap; }
.iu-company-copy small { overflow: hidden; color: #8a92a3; font-size: 9.5px; text-overflow: ellipsis; white-space: nowrap; }
.iu-company-row > select {
  width: 100%;
  height: 32px;
  padding: 0 8px;
  color: #30394c;
  background: #fff;
  border: 1px solid var(--border-hard, #dfe3ea);
  border-radius: 6px;
  font: inherit;
  font-size: 10.5px;
}
.iu-company-row > select:disabled { color: #9ca3b2; background: #f4f5f7; }
.iu-subheading {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin: 2px 0 8px;
  color: #606a7f;
  font-size: 10.5px;
  font-weight: 650;
}
.iu-subheading b { color: #6257c8; font-size: 10px; }
.iu-subheading.roles { margin-top: 17px; padding-top: 14px; border-top: 1px solid var(--border-hard, #e2e5ec); }
.iu-sector-list { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 6px; }
.iu-sector-list > button {
  min-height: 36px;
  display: flex;
  align-items: center;
  gap: 7px;
  padding: 7px 8px;
  text-align: left;
  color: #4e586d;
  background: #fff;
  border: 1px solid var(--border-hard, #e2e5ec);
  border-radius: 6px;
  font: inherit;
  font-size: 10.5px;
  cursor: pointer;
}
.iu-sector-list > button:hover { border-color: #b6b1e7; }
.iu-sector-list > button.on { color: #5147ad; background: rgba(98, 87, 200, .055); border-color: #8a82dc; }
.iu-sector-dot { width: 7px; height: 7px; flex: 0 0 7px; border-radius: 50%; }
.iu-global-note,
.iu-admin-warning {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  padding: 9px 11px;
  color: #4f5d72;
  background: #f3f7fa;
  border: 1px solid #dbe7ee;
  border-radius: 7px;
  font-size: 10.5px;
  line-height: 1.4;
}
.iu-admin-warning { margin-top: 12px; color: #8a5b0b; background: #fff8e8; border-color: #edd9a8; }
.iu-empty { padding: 26px 10px; text-align: center; color: #8a92a3; font-size: 11px; }
.iu-error {
  display: flex;
  align-items: center;
  gap: 8px;
  margin: 14px 0 0;
  padding: 9px 11px;
  color: #a52f34;
  background: #fff3f3;
  border: 1px solid #efc8ca;
  border-radius: 7px;
  font-size: 11px;
}
.iu-footer { width: 100%; display: flex; align-items: center; justify-content: space-between; gap: 16px; }
.iu-summary { min-width: 0; display: flex; align-items: center; gap: 7px; color: #8a5b0b; font-size: 11px; }
.iu-summary.ready { color: #21725f; }
.iu-summary span { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.iu-footer-actions { display: flex; gap: 8px; flex-shrink: 0; }
.iu-btn {
  min-height: 36px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 7px;
  padding: 0 15px;
  border-radius: 7px;
  font: inherit;
  font-size: 11.5px;
  font-weight: 650;
  cursor: pointer;
}
.iu-btn.secondary { color: #4e586d; background: #fff; border: 1px solid var(--border-hard, #dfe3ea); }
.iu-btn.secondary:hover { background: #f5f6f9; }
.iu-btn.primary { color: #fff; background: #6257c8; border: 1px solid #6257c8; }
.iu-btn.primary:hover:not(:disabled) { background: #5147ad; border-color: #5147ad; }
.iu-btn:disabled { opacity: .48; cursor: default; }
.iu-success {
  min-height: 470px;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 12px;
  padding: 32px;
}
.iu-success-icon {
  width: 50px;
  height: 50px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  color: #fff;
  background: #268f77;
  border-radius: 50%;
  box-shadow: 0 0 0 7px rgba(38, 143, 119, .1);
}
.iu-success h3 { margin: 7px 0 0; color: #172033; font-size: 17px; font-weight: 650; letter-spacing: 0; }
.iu-success-note { max-width: 520px; margin: 0; padding: 8px 11px; border-radius: 7px; text-align: center; font-size: 11px; }
.iu-success-note.ok { color: #21725f; background: #eef8f5; }
.iu-success-note.warn { color: #8a5b0b; background: #fff7e5; }
.iu-success-note.neutral { color: #526176; background: #f3f6f8; }
.iu-credentials { width: min(520px, 100%); margin-top: 6px; border-top: 1px solid #e2e5ec; }
.iu-credentials > div {
  display: grid;
  grid-template-columns: 150px minmax(0, 1fr);
  align-items: center;
  gap: 14px;
  min-height: 46px;
  border-bottom: 1px solid #e2e5ec;
}
.iu-credentials span { color: #7b8498; font-size: 10px; font-weight: 600; }
.iu-credentials code { overflow: hidden; color: #30394c; font-size: 12px; text-overflow: ellipsis; user-select: all; }
.iu-copy-result {
  min-height: 34px;
  display: inline-flex;
  align-items: center;
  gap: 7px;
  padding: 0 13px;
  color: #5147ad;
  background: rgba(98, 87, 200, .08);
  border: 1px solid rgba(98, 87, 200, .2);
  border-radius: 7px;
  font: inherit;
  font-size: 11px;
  font-weight: 600;
  cursor: pointer;
}
.iu-success-bulk { justify-content: flex-start; }
.iu-result-list { width: min(720px, 100%); max-height: 310px; overflow-y: auto; border-top: 1px solid #e2e5ec; }
.iu-result-row {
  min-height: 40px;
  display: grid;
  grid-template-columns: 18px minmax(0, 1fr) minmax(140px, auto);
  align-items: center;
  gap: 8px;
  color: #21725f;
  border-bottom: 1px solid #e2e5ec;
  font-size: 11px;
}
.iu-result-row.failed { color: #a52f34; }
.iu-result-email { overflow: hidden; color: #30394c; text-overflow: ellipsis; white-space: nowrap; }
.iu-result-row code { color: #4e586d; font-size: 10.5px; user-select: all; }
.iu-result-error { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }

@media (max-width: 900px) {
  .iu-layout { grid-template-columns: 1fr; margin: -22px; }
  .iu-profile { border-right: 0; border-bottom: 1px solid var(--border-hard, #e2e5ec); }
  .iu-access-toolbar { align-items: stretch; flex-direction: column; }
  .iu-search { width: 100%; box-sizing: border-box; }
  .iu-bulk-role { display: grid; grid-template-columns: auto minmax(0, 1fr) auto; }
  .iu-bulk-role select { width: 100%; }
}

@media (max-width: 620px) {
  .iu-header { align-items: stretch; flex-direction: column; }
  .iu-mode { width: 100%; }
  .iu-mode button { min-width: 0; }
  .iu-field-grid,
  .iu-scope,
  .iu-sector-list { grid-template-columns: 1fr; }
  .iu-company-row { grid-template-columns: 1fr; gap: 6px; }
  .iu-company-row > select { margin-left: 27px; width: calc(100% - 27px); }
  .iu-bulk-role { grid-template-columns: 1fr; }
  .iu-footer { align-items: stretch; flex-direction: column; }
  .iu-summary span { white-space: normal; }
  .iu-footer-actions { width: 100%; }
  .iu-footer-actions .iu-btn { flex: 1; }
  .iu-success { min-height: 380px; padding: 20px 4px; }
  .iu-credentials > div { grid-template-columns: 1fr; gap: 4px; padding: 8px 0; }
}

/* ─── Маршрутизация модерации ─── */
.iu-mod-block { display: flex; flex-direction: column; gap: 7px; margin-top: 10px; }
.iu-mod-note { font-size: 11.5px; line-height: 1.45; color: #7c869b; margin: 0; }
.iu-mod-chips { display: flex; flex-wrap: wrap; gap: 6px; }
.iu-mod-chip {
  display: inline-flex; align-items: center; gap: 5px;
  padding: 4px 9px; border-radius: 999px; font: inherit; font-size: 12px;
  color: #4436a8; background: rgba(124, 111, 247, .10);
  border: 1px solid rgba(124, 111, 247, .26); cursor: pointer;
  transition: background .16s ease, transform .16s ease;
}
.iu-mod-chip:hover { background: rgba(124, 111, 247, .18); transform: translateY(-1px); }
.iu-mod-list {
  display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 6px;
  max-height: 190px; overflow-y: auto; padding-right: 2px;
}
.iu-mod-list > button {
  min-height: 40px; display: flex; align-items: center; gap: 8px;
  padding: 6px 8px; text-align: left; color: #4e586d; background: #fff;
  border: 1px solid var(--border-hard, #e2e5ec); border-radius: 8px;
  font: inherit; cursor: pointer; transition: border-color .16s ease, background .16s ease;
}
.iu-mod-list > button:hover { border-color: rgba(124, 111, 247, .45); }
.iu-mod-list > button.on { border-color: #7c6ff7; background: rgba(124, 111, 247, .07); }
.iu-mod-person { display: flex; flex-direction: column; min-width: 0; }
.iu-mod-person b { font-weight: 500; font-size: 12.5px; color: #2b3348; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.iu-mod-person small { font-size: 10.5px; color: #93a0b4; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.iu-mod-err { font-size: 11.5px; color: #c2410c; }
@media (max-width: 720px) { .iu-mod-list { grid-template-columns: 1fr; } }
</style>
