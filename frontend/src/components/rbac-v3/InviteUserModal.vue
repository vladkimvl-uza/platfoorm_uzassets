<script setup lang="ts">
/**
 * InviteUserModal — приглашение / создание пользователя (RBAC v3).
 *
 * Логика доступа (Pack 147):
 *   • «Вся платформа» — пользователю назначаются ГЛОБАЛЬНЫЕ роли; при наличии
 *     роли с неограниченным доступом (admin/ceo) он видит ВСЕ компании.
 *   • «Выбранные компании» — пользователь добавляется в группу(ы), привязанные
 *     к компаниям (1 группа = 1 компания), с ОДНОЙ ролью на компанию. Тогда
 *     `allowed_company_ids` возвращает только эти компании → на всех дашбордах
 *     он видит данные только своей компании. Это типовой «пользователь компании».
 *
 * Роли сгруппированы по 6 категориям, с поиском, треем выбранных, описаниями.
 */
import { ref, computed, onMounted } from 'vue';
import {
  rolesApi, groupsApi, rbacV3Api, createUser, generatePassword,
  type RbacV3Role, type RbacV3Group,
} from '@/api/rbacV3';
import { companiesApi, type SectorBrief } from '@/api/companies';
import RoleChip from './RoleChip.vue';

const props = defineProps<{
  prefill?: { full_name?: string; department?: string; role_codes?: string[] };
}>();
const emit = defineEmits<{
  (e: 'close'): void;
  (e: 'created', userId: string): void;
}>();

const email = ref('');
const fullName = ref(props.prefill?.full_name || '');
const department = ref(props.prefill?.department || '');
const password = ref(generatePassword());
const mustChangePassword = ref(true);
const selectedRoles = ref<string[]>(props.prefill?.role_codes || []);

const scopeMode = ref<'global' | 'company' | 'sector'>('company');
const allRoles = ref<RbacV3Role[]>([]);
const companyGroups = ref<RbacV3Group[]>([]);
const selectedCompanyGroupIds = ref<string[]>([]);
const companySearch = ref('');
const sectors = ref<SectorBrief[]>([]);
const selectedSectors = ref<string[]>([]);

const saving = ref(false);
const error = ref<string | null>(null);
const copied = ref(false);
const roleSearch = ref('');

// ─── Мульти-добавление ──────────────────────────────────────────────
const bulkMode = ref(false);
const bulkText = ref('');
const bulkResults = ref<Array<{ email: string; ok: boolean; password?: string; error?: string }> | null>(null);
const bulkCopied = ref(false);

// Парсит строки textarea → [{email, full_name}]. Форматы строки:
//   "email, ФИО" | "email; ФИО" | "email <tab> ФИО" | просто "email"
const parsedBulk = computed(() => {
  const rows: { email: string; full_name: string }[] = [];
  const seen = new Set<string>();
  for (const raw of bulkText.value.split('\n')) {
    const line = raw.trim();
    if (!line) continue;
    const parts = line.split(/[,;\t]/);
    const em = (parts[0] || '').trim().toLowerCase();
    if (!em.includes('@') || seen.has(em)) continue;
    seen.add(em);
    const name = parts.slice(1).join(',').trim() || em.split('@')[0];
    rows.push({ email: em, full_name: name });
  }
  return rows;
});

// ─── Категоризация ролей (по коду; поля category в модели нет) ───────
const ROLE_CATEGORIES: { id: string; label: string; codes: string[] }[] = [
  { id: 'access',     label: 'Доступ и администрирование', codes: ['admin', 'organization', 'viewer', 'audit_viewer'] },
  { id: 'finance',    label: 'Финансы и аналитика',        codes: ['financier', 'finmodel', 'finance_controller', 'monitoring', 'fid', 'debt'] },
  { id: 'treasury',   label: 'Казначейство и CFO',         codes: ['treasure_user', 'cfo_department', 'cfo_committee'] },
  { id: 'procurement', label: 'Закупки',                   codes: ['purchase_department', 'initiator', 'procurement_owner'] },
  { id: 'org',        label: 'Структура организации',      codes: ['department_worker', 'department_head', 'department_director', 'plan_department'] },
  { id: 'special',    label: 'Специальные',                codes: ['lawyer', 'investment', 'mdm_steward'] },
];
const _CODE_TO_CAT: Record<string, string> = {};
for (const c of ROLE_CATEGORIES) for (const code of c.codes) _CODE_TO_CAT[code] = c.id;

onMounted(async () => {
  try {
    const [roles, groups, secs] = await Promise.all([
      rolesApi.list(),
      groupsApi.list().catch(() => []),
      companiesApi.listSectors().catch(() => []),
    ]);
    allRoles.value = roles;
    // Группы, привязанные к компании (1:1) — селектор компаний.
    companyGroups.value = (groups || []).filter(g => g.company_id)
      .sort((a, b) => a.name.localeCompare(b.name, 'ru'));
    sectors.value = secs || [];
  } catch (e: any) { error.value = e?.response?.data?.detail || 'Не удалось загрузить роли/компании'; }
});

const roleByCode = computed<Record<string, RbacV3Role>>(() => {
  const m: Record<string, RbacV3Role> = {};
  for (const r of allRoles.value) m[r.code] = r;
  return m;
});

const isMulti = computed(() => scopeMode.value === 'global' || scopeMode.value === 'sector');

const groupedRoles = computed(() => {
  const q = roleSearch.value.trim().toLowerCase();
  const match = (r: RbacV3Role) =>
    !q || r.name_ru.toLowerCase().includes(q) || r.code.toLowerCase().includes(q)
    || (r.description_ru || '').toLowerCase().includes(q);
  const cats = ROLE_CATEGORIES.map(c => ({
    id: c.id, label: c.label,
    roles: allRoles.value.filter(r => _CODE_TO_CAT[r.code] === c.id && match(r)).sort((a, b) => a.sort_order - b.sort_order),
  }));
  const others = allRoles.value.filter(r => !_CODE_TO_CAT[r.code] && match(r));
  if (others.length) cats.push({ id: 'other', label: 'Прочее', roles: others });
  return cats.filter(c => c.roles.length > 0);
});

const selectedRoleObjs = computed(() =>
  selectedRoles.value.map(code => roleByCode.value[code]).filter(Boolean) as RbacV3Role[]);

const filteredCompanyGroups = computed(() => {
  const q = companySearch.value.trim().toLowerCase();
  return !q ? companyGroups.value
    : companyGroups.value.filter(g => g.name.toLowerCase().includes(q) || g.code.toLowerCase().includes(q));
});

function catSelectedCount(cat: { roles: RbacV3Role[] }): number {
  return cat.roles.filter(r => selectedRoles.value.includes(r.code)).length;
}
function isRoleSelected(code: string): boolean { return selectedRoles.value.includes(code); }
function pickRole(code: string) {
  if (isMulti.value) {
    const i = selectedRoles.value.indexOf(code);
    if (i >= 0) selectedRoles.value.splice(i, 1); else selectedRoles.value.push(code);
  } else {
    selectedRoles.value = selectedRoles.value[0] === code ? [] : [code];  // одна роль на компанию
  }
}
function clearRoles() { selectedRoles.value = []; }
function toggleCompany(gid: string) {
  const i = selectedCompanyGroupIds.value.indexOf(gid);
  if (i >= 0) selectedCompanyGroupIds.value.splice(i, 1); else selectedCompanyGroupIds.value.push(gid);
}
function toggleSector(code: string) {
  const i = selectedSectors.value.indexOf(code);
  if (i >= 0) selectedSectors.value.splice(i, 1); else selectedSectors.value.push(code);
}
function setScope(mode: 'global' | 'company' | 'sector') {
  scopeMode.value = mode;
  // single-режим (company): оставляем максимум одну роль
  if (mode === 'company' && selectedRoles.value.length > 1) selectedRoles.value = [selectedRoles.value[0]];
}

function regenPassword() { password.value = generatePassword(); copied.value = false; }
function copyPassword() {
  navigator.clipboard.writeText(password.value).then(() => { copied.value = true; setTimeout(() => { copied.value = false; }, 2000); });
}

function _validateScope(): boolean {
  if (scopeMode.value === 'company') {
    if (selectedCompanyGroupIds.value.length === 0) { error.value = 'Выберите хотя бы одну компанию'; return false; }
    if (selectedRoles.value.length === 0) { error.value = 'Выберите роль для пользователя компании'; return false; }
  }
  if (scopeMode.value === 'sector') {
    if (selectedSectors.value.length === 0) { error.value = 'Выберите хотя бы один сектор'; return false; }
    if (selectedRoles.value.length === 0) { error.value = 'Выберите роль (определяет права внутри секторов)'; return false; }
  }
  return true;
}

// Создаёт одного пользователя (createUser + членства для scoped). Возвращает id.
async function _createOne(em: string, name: string, pw: string): Promise<string> {
  const u = await createUser({
    email: em, full_name: name, department: department.value.trim() || undefined,
    password: pw, must_change_password: mustChangePassword.value,
    // global и sector → роли как глобальные (дают права); company → роль в группе.
    role_codes: scopeMode.value === 'company' ? [] : selectedRoles.value,
    allowed_sectors: scopeMode.value === 'sector' ? selectedSectors.value : undefined,
  });
  if (scopeMode.value === 'company') {
    const roleCode = selectedRoles.value[0];
    for (const gid of selectedCompanyGroupIds.value) await rbacV3Api.upsertMembership(u.id, gid, roleCode);
  }
  return u.id;
}

async function bulkSubmit() {
  const users = parsedBulk.value;
  if (users.length === 0) { error.value = 'Добавьте хотя бы один email (по одному на строку)'; return; }
  if (!_validateScope()) return;
  saving.value = true; error.value = null;
  const out: NonNullable<typeof bulkResults.value> = [];
  for (const row of users) {
    const pw = generatePassword();
    try {
      await _createOne(row.email, row.full_name, pw);
      out.push({ email: row.email, ok: true, password: pw });
    } catch (e: any) {
      out.push({ email: row.email, ok: false, error: e?.response?.data?.detail || 'ошибка' });
    }
  }
  saving.value = false;
  bulkResults.value = out;
  emit('created', '');   // сигнал родителю обновить список
}

function copyBulkResults() {
  const text = (bulkResults.value || []).filter(r => r.ok)
    .map(r => `${r.email}\t${r.password}`).join('\n');
  navigator.clipboard.writeText(text).then(() => { bulkCopied.value = true; setTimeout(() => { bulkCopied.value = false; }, 2000); });
}

async function submit() {
  if (bulkMode.value) { await bulkSubmit(); return; }
  if (!email.value.trim() || !fullName.value.trim()) { error.value = 'Email и ФИО обязательны'; return; }
  if (!_validateScope()) return;
  saving.value = true; error.value = null;
  try {
    const u = await createUser({
      email: email.value.trim(),
      full_name: fullName.value.trim(),
      department: department.value.trim() || undefined,
      password: password.value,
      must_change_password: mustChangePassword.value,
      // global/sector → роли глобальные; company → роль назначается в группе.
      role_codes: scopeMode.value === 'company' ? [] : selectedRoles.value,
      allowed_sectors: scopeMode.value === 'sector' ? selectedSectors.value : undefined,
    });
    // Режим «Выбранные компании»: членство в группе каждой компании с ролью.
    if (scopeMode.value === 'company') {
      const roleCode = selectedRoles.value[0];
      for (const gid of selectedCompanyGroupIds.value) {
        await rbacV3Api.upsertMembership(u.id, gid, roleCode);
      }
    }
    emit('created', u.id);
    emit('close');
  } catch (e: any) {
    error.value = e?.response?.data?.detail || 'Не удалось создать пользователя';
  } finally {
    saving.value = false;
  }
}
</script>

<template>
  <div class="iu-bd" @click.self="emit('close')">
    <div class="iu-modal">
      <header class="iu-head">
        <h2 class="iu-title">{{ prefill ? 'Создать аналогичного пользователя' : (bulkMode ? 'Пригласить нескольких' : 'Пригласить пользователя') }}</h2>
        <div class="iu-head-right">
          <div v-if="!prefill && !bulkResults" class="iu-modeseg">
            <button type="button" :class="{ on: !bulkMode }" @click="bulkMode = false">Один</button>
            <button type="button" :class="{ on: bulkMode }" @click="bulkMode = true">Несколько</button>
          </div>
          <button class="iu-x" @click="emit('close')" title="Закрыть">×</button>
        </div>
      </header>

      <!-- ═══ Результаты массового создания ═══ -->
      <div v-if="bulkResults" class="iu-body">
        <div class="iu-res-head">
          <span>Создано: <b>{{ bulkResults.filter(r => r.ok).length }}</b> из {{ bulkResults.length }}</span>
          <button class="iu-mini" @click="copyBulkResults" type="button">{{ bulkCopied ? '✓ скопировано' : 'копировать email+пароли' }}</button>
        </div>
        <div class="iu-res-list">
          <div v-for="r in bulkResults" :key="r.email" class="iu-res-row" :class="{ fail: !r.ok }">
            <span class="iu-res-dot">{{ r.ok ? '✓' : '✗' }}</span>
            <span class="iu-res-email">{{ r.email }}</span>
            <code v-if="r.ok" class="iu-res-pwd">{{ r.password }}</code>
            <span v-else class="iu-res-err">{{ r.error }}</span>
          </div>
        </div>
        <p class="iu-foot-hint" style="margin-top:10px">Сохраните пароли (если SMTP не настроен — передайте пользователям лично). Письма-приглашения отправлены автоматически при включённом SMTP.</p>
      </div>

      <!-- ═══ Форма ═══ -->
      <div v-else class="iu-body">
        <!-- ── Профиль: один ── -->
        <div v-if="!bulkMode" class="iu-grid2">
          <label class="iu-field">
            <span class="iu-lbl">Email *</span>
            <input v-model="email" class="iu-in" placeholder="user@uz-assets.uz" autofocus />
          </label>
          <label class="iu-field">
            <span class="iu-lbl">ФИО *</span>
            <input v-model="fullName" class="iu-in" placeholder="Иванов Иван Иванович" />
          </label>
          <label class="iu-field">
            <span class="iu-lbl">Отдел (опционально)</span>
            <input v-model="department" class="iu-in" placeholder="Финансовый блок" />
          </label>
          <div class="iu-field">
            <span class="iu-lbl iu-lbl-row">
              Временный пароль
              <span class="iu-pwd-acts">
                <button class="iu-mini" @click="regenPassword" type="button">↻ новый</button>
                <button class="iu-mini" @click="copyPassword" type="button">{{ copied ? '✓ скопировано' : 'копировать' }}</button>
              </span>
            </span>
            <div class="iu-pwd"><code>{{ password }}</code></div>
          </div>
        </div>

        <!-- ── Профиль: несколько ── -->
        <div v-else>
          <label class="iu-field">
            <span class="iu-lbl iu-lbl-row">
              Пользователи — по одному на строку
              <span v-if="parsedBulk.length" class="iu-count">{{ parsedBulk.length }} распознано</span>
            </span>
            <textarea v-model="bulkText" class="iu-in iu-bulk-ta" rows="5"
                      placeholder="ivanov@uz-assets.uz, Иванов Иван&#10;petrov@uz-assets.uz, Петров Пётр&#10;sidorov@uz-assets.uz"></textarea>
          </label>
          <p class="iu-hint-line">Формат: <code>email, ФИО</code> (ФИО опционально). Пароль генерируется для каждого автоматически.</p>
          <label class="iu-field" style="margin-top:8px">
            <span class="iu-lbl">Отдел для всех (опционально)</span>
            <input v-model="department" class="iu-in" placeholder="Финансовый блок" />
          </label>
        </div>

        <label class="iu-cb-row">
          <input type="checkbox" v-model="mustChangePassword" />
          <span>Требовать смену пароля при первом входе</span>
        </label>

        <!-- ── Область доступа ── -->
        <div class="iu-lbl" style="margin-top:20px;margin-bottom:8px">Область доступа</div>
        <div class="iu-scope iu-scope-3">
          <button type="button" :class="['iu-scope-opt', { on: scopeMode === 'company' }]" @click="setScope('company')">
            <span class="iu-scope-radio"></span>
            <span class="iu-scope-text">
              <span class="iu-scope-name">Выбранные компании</span>
              <span class="iu-scope-desc">Видит данные только своих компаний на всех дашбордах</span>
            </span>
          </button>
          <button type="button" :class="['iu-scope-opt', { on: scopeMode === 'sector' }]" @click="setScope('sector')">
            <span class="iu-scope-radio"></span>
            <span class="iu-scope-text">
              <span class="iu-scope-name">По секторам</span>
              <span class="iu-scope-desc">Видит все компании выбранных секторов</span>
            </span>
          </button>
          <button type="button" :class="['iu-scope-opt', { on: scopeMode === 'global' }]" @click="setScope('global')">
            <span class="iu-scope-radio"></span>
            <span class="iu-scope-text">
              <span class="iu-scope-name">Вся платформа</span>
              <span class="iu-scope-desc">Доступ ко всем компаниям (для админов и общеорг. ролей)</span>
            </span>
          </button>
        </div>

        <!-- ── Секторы (scoped) ── -->
        <template v-if="scopeMode === 'sector'">
          <div class="iu-roles-head" style="margin-top:14px">
            <span class="iu-lbl">Секторы *</span>
            <span class="iu-count" v-if="selectedSectors.length">выбрано {{ selectedSectors.length }}</span>
          </div>
          <div class="iu-companies">
            <div v-if="sectors.length === 0" class="iu-empty">Секторы не загружены</div>
            <button v-for="s in sectors" :key="s.code" type="button"
                    :class="['iu-co', { on: selectedSectors.includes(s.code) }]" @click="toggleSector(s.code)">
              <span class="iu-role-check">
                <svg v-if="selectedSectors.includes(s.code)" width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"/></svg>
              </span>
              <span class="iu-co-name">{{ s.name_ru }}</span>
            </button>
          </div>
        </template>

        <!-- ── Компании (scoped) ── -->
        <template v-if="scopeMode === 'company'">
          <div class="iu-roles-head" style="margin-top:14px">
            <span class="iu-lbl">Компании *</span>
            <span class="iu-count" v-if="selectedCompanyGroupIds.length">выбрано {{ selectedCompanyGroupIds.length }}</span>
          </div>
          <div class="iu-search">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><circle cx="11" cy="11" r="7"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg>
            <input v-model="companySearch" class="iu-search-in" placeholder="Поиск компании…" />
            <button v-if="companySearch" class="iu-search-clr" @click="companySearch = ''" type="button">×</button>
          </div>
          <div class="iu-companies">
            <div v-if="companyGroups.length === 0" class="iu-empty">Нет компаний с группами доступа</div>
            <button v-for="g in filteredCompanyGroups" :key="g.id" type="button"
                    :class="['iu-co', { on: selectedCompanyGroupIds.includes(g.id) }]" @click="toggleCompany(g.id)">
              <span class="iu-role-check">
                <svg v-if="selectedCompanyGroupIds.includes(g.id)" width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"/></svg>
              </span>
              <span class="iu-co-name">{{ g.name }}</span>
            </button>
          </div>
        </template>

        <!-- ── Роли ── -->
        <div class="iu-roles-head">
          <span class="iu-lbl">{{ scopeMode === 'company' ? 'Роль в выбранных компаниях *' : (scopeMode === 'sector' ? 'Роли (права внутри секторов) *' : 'Роли (на всю платформу)') }}</span>
          <span class="iu-roles-meta">
            <span class="iu-count" v-if="selectedRoles.length">выбрано {{ selectedRoles.length }}</span>
            <button v-if="selectedRoles.length && isMulti" class="iu-mini" @click="clearRoles" type="button">очистить</button>
          </span>
        </div>
        <div class="iu-hint-line" v-if="scopeMode === 'company'">Одна роль на компанию — определяет, что пользователь может делать внутри своей компании.</div>

        <div v-if="selectedRoleObjs.length && isMulti" class="iu-tray">
          <button v-for="r in selectedRoleObjs" :key="r.code" class="iu-tray-chip" @click="pickRole(r.code)" type="button" :title="`Убрать «${r.name_ru}»`">
            <RoleChip :code="r.code" size="sm" />
            <span class="iu-tray-name">{{ r.name_ru }}</span>
            <span class="iu-tray-x">×</span>
          </button>
        </div>

        <div class="iu-search">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><circle cx="11" cy="11" r="7"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg>
          <input v-model="roleSearch" class="iu-search-in" placeholder="Поиск роли по названию или коду…" />
          <button v-if="roleSearch" class="iu-search-clr" @click="roleSearch = ''" type="button">×</button>
        </div>

        <div class="iu-roles">
          <div v-if="allRoles.length === 0" class="iu-empty">Загрузка ролей…</div>
          <div v-else-if="groupedRoles.length === 0" class="iu-empty">Ничего не найдено по «{{ roleSearch }}»</div>
          <section v-for="cat in groupedRoles" :key="cat.id" class="iu-cat">
            <div class="iu-cat-head">
              <span class="iu-cat-label">{{ cat.label }}</span>
              <span class="iu-cat-count">{{ catSelectedCount(cat) }}/{{ cat.roles.length }}</span>
            </div>
            <div class="iu-cat-roles">
              <button v-for="r in cat.roles" :key="r.code" type="button"
                      :class="['iu-role', { on: isRoleSelected(r.code), single: !isMulti }]"
                      @click="pickRole(r.code)" :title="r.description_ru || r.name_ru">
                <span class="iu-role-check" :class="{ radio: !isMulti }">
                  <svg v-if="isRoleSelected(r.code)" width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"/></svg>
                </span>
                <RoleChip :code="r.code" size="sm" />
                <span class="iu-role-text">
                  <span class="iu-role-name">{{ r.name_ru }}</span>
                  <span v-if="r.description_ru" class="iu-role-desc">{{ r.description_ru }}</span>
                </span>
              </button>
            </div>
          </section>
        </div>

        <div v-if="error" class="iu-err">{{ error }}</div>
      </div>

      <footer class="iu-foot">
        <span class="iu-foot-hint" v-if="!prefill && !bulkResults">Пользователь получит письмо с паролем (или сообщите лично).</span>
        <div class="iu-foot-btns">
          <template v-if="bulkResults">
            <button class="iu-btn iu-primary" @click="emit('close')">Готово</button>
          </template>
          <template v-else>
            <button class="iu-btn iu-ghost" @click="emit('close')" :disabled="saving">Отмена</button>
            <button class="iu-btn iu-primary" :disabled="saving" @click="submit">
              {{ saving ? 'Создание…' : (prefill ? 'Создать клон' : (bulkMode ? `Пригласить ${parsedBulk.length || ''}` : 'Пригласить')) }}
            </button>
          </template>
        </div>
      </footer>
    </div>
  </div>
</template>

<style scoped>
.iu-bd { position: fixed; inset: 0; z-index: 200; background: rgba(15,18,40,.45); backdrop-filter: blur(8px); display: flex; align-items: center; justify-content: center; padding: 28px; }
.iu-modal { width: min(640px, 100%); max-height: 90vh; background: var(--bg1, #fff); border-radius: 14px; box-shadow: 0 24px 64px rgba(15,23,60,.18), 0 8px 24px rgba(15,23,60,.08); display: flex; flex-direction: column; overflow: hidden; animation: iuIn .32s cubic-bezier(.34,1.2,.64,1); }
@keyframes iuIn { from { opacity:0; transform: translateY(12px) scale(.98); } to { opacity:1; transform:none; } }
.iu-head { display: flex; align-items: center; justify-content: space-between; padding: 18px 22px 14px; border-bottom: 1px solid var(--border-hard, #E5E7EB); }
.iu-title { font-size: 16px; font-weight: 600; letter-spacing: -.01em; color: var(--t1, #1E2A4A); margin: 0; }
.iu-x { background: none; border: none; font-size: 26px; line-height: 1; color: var(--t3, #94A3B8); cursor: pointer; padding: 0 4px; }
.iu-x:hover { color: var(--t1, #1E2A4A); }
.iu-head-right { display: flex; align-items: center; gap: 12px; }
.iu-modeseg { display: inline-flex; background: var(--bg2, #F1F5F9); border-radius: 8px; padding: 2px; }
.iu-modeseg button { border: none; background: transparent; padding: 5px 12px; border-radius: 6px; font-size: 11.5px; font-weight: 600; color: var(--t3, #64748B); cursor: pointer; font-family: inherit; }
.iu-modeseg button.on { background: #fff; color: var(--p-deep, #534AB7); box-shadow: 0 1px 3px rgba(15,23,60,.08); }
.iu-body { padding: 18px 22px; overflow-y: auto; }
.iu-bulk-ta { resize: vertical; line-height: 1.6; font-size: 12.5px; }
.iu-res-head { display: flex; align-items: center; justify-content: space-between; font-size: 13px; color: var(--t1, #1E2A4A); margin-bottom: 12px; }
.iu-res-list { display: flex; flex-direction: column; gap: 6px; }
.iu-res-row { display: flex; align-items: center; gap: 10px; padding: 8px 11px; border: 1px solid var(--border-hard, #E5E7EB); border-radius: 9px; font-size: 12.5px; }
.iu-res-row.fail { background: rgba(226,75,74,.05); border-color: rgba(226,75,74,.25); }
.iu-res-dot { width: 18px; flex-shrink: 0; font-weight: 700; color: var(--green, #1D9E75); }
.iu-res-row.fail .iu-res-dot { color: var(--sev-high, #E24B4A); }
.iu-res-email { flex: 1; color: var(--t1, #1E2A4A); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.iu-res-pwd { font-family: ui-monospace, 'SF Mono', Menlo, monospace; font-size: 12px; color: var(--t2, #475569); background: var(--bg2, #F8FAFC); padding: 2px 7px; border-radius: 6px; user-select: all; }
.iu-res-err { font-size: 11.5px; color: #A82C2B; }

.iu-grid2 { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }
.iu-field { display: flex; flex-direction: column; gap: 5px; min-width: 0; }
.iu-lbl { font-size: 10px; font-weight: 500; color: var(--t3, var(--t-muted)); letter-spacing: .06em; text-transform: uppercase; }
.iu-lbl-row { display: flex; align-items: center; justify-content: space-between; }
.iu-pwd-acts { display: flex; gap: 8px; }
.iu-in { width: 100%; box-sizing: border-box; padding: 8px 11px; border: 1.5px solid var(--border-input, #E2E8F0); border-radius: 8px; font-size: 12.5px; color: var(--t1, #1E2A4A); outline: none; font-family: inherit; background: var(--bg2, #F8FAFC); transition: border-color .14s, box-shadow .14s; }
.iu-in:focus { border-color: var(--p, #7C6FF7); box-shadow: 0 0 0 3px rgba(124,111,247,.14); }
.iu-pwd { padding: 9px 11px; background: var(--bg2, #F8FAFC); border: 1.5px solid var(--border-input, #E2E8F0); border-radius: 8px; }
.iu-pwd code { font-family: ui-monospace, 'SF Mono', Menlo, monospace; font-size: 13px; color: var(--t1, #1E2A4A); letter-spacing: .04em; user-select: all; }
.iu-mini { background: transparent; border: none; color: var(--p-deep, #534AB7); font-size: 10.5px; font-weight: 500; cursor: pointer; font-family: inherit; padding: 1px 2px; }
.iu-mini:hover { text-decoration: underline; }
.iu-cb-row { display: flex; align-items: center; gap: 7px; margin-top: 12px; font-size: 12px; color: var(--t2, #334155); cursor: pointer; }
.iu-cb-row input { accent-color: var(--p, #7C6FF7); width: 15px; height: 15px; }

.iu-scope { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; }
.iu-scope-3 { grid-template-columns: repeat(3, 1fr); }
.iu-scope-opt { display: flex; align-items: flex-start; gap: 9px; padding: 11px 13px; background: var(--bg2, #F8FAFC); border: 1.5px solid var(--border-input, #E2E8F0); border-radius: 11px; cursor: pointer; font-family: inherit; text-align: left; transition: all .14s; }
.iu-scope-opt:hover { border-color: rgba(124,111,247,.4); }
.iu-scope-opt.on { background: rgba(124,111,247,.07); border-color: var(--p, #7C6FF7); }
.iu-scope-radio { flex-shrink: 0; width: 16px; height: 16px; border-radius: 50%; border: 2px solid var(--border-input, #CBD5E1); margin-top: 2px; transition: all .14s; position: relative; }
.iu-scope-opt.on .iu-scope-radio { border-color: var(--p, #7C6FF7); }
.iu-scope-opt.on .iu-scope-radio::after { content: ''; position: absolute; inset: 3px; border-radius: 50%; background: var(--p, #7C6FF7); }
.iu-scope-text { display: flex; flex-direction: column; gap: 2px; }
.iu-scope-name { font-size: 12.5px; font-weight: 600; color: var(--t1, #1E2A4A); }
.iu-scope-desc { font-size: 10.5px; color: var(--t3, #94A3B8); line-height: 1.35; }

.iu-roles-head { display: flex; align-items: center; justify-content: space-between; margin: 18px 0 8px; }
.iu-roles-meta { display: flex; align-items: center; gap: 10px; }
.iu-count { font-size: 11px; font-weight: 600; color: var(--p-deep, #534AB7); background: rgba(124,111,247,.12); padding: 2px 9px; border-radius: 8px; }
.iu-hint-line { font-size: 11px; color: var(--t3, #94A3B8); margin: -2px 0 8px; }

.iu-companies { display: grid; grid-template-columns: 1fr 1fr; gap: 6px; max-height: 168px; overflow-y: auto; padding: 2px; }
.iu-co { display: flex; align-items: center; gap: 8px; padding: 8px 10px; background: var(--bg2, #F8FAFC); border: 1px solid var(--border-hard, #E5E7EB); border-radius: 9px; cursor: pointer; font-family: inherit; text-align: left; transition: all .13s; }
.iu-co:hover { border-color: rgba(124,111,247,.4); background: #fff; }
.iu-co.on { background: rgba(124,111,247,.08); border-color: rgba(124,111,247,.45); }
.iu-co-name { font-size: 12px; font-weight: 500; color: var(--t1, #1E2A4A); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }

.iu-tray { display: flex; flex-wrap: wrap; gap: 6px; padding: 10px; background: rgba(124,111,247,.05); border: 1px solid rgba(124,111,247,.18); border-radius: 10px; margin-bottom: 10px; }
.iu-tray-chip { display: inline-flex; align-items: center; gap: 6px; padding: 3px 8px 3px 5px; background: #fff; border: 1px solid var(--border-hard, #E5E7EB); border-radius: 9px; cursor: pointer; font-family: inherit; transition: all .13s; }
.iu-tray-chip:hover { border-color: var(--sev-high, #E24B4A); }
.iu-tray-name { font-size: 11.5px; color: var(--t1, #1E2A4A); }
.iu-tray-x { font-size: 15px; line-height: 1; color: var(--t3, #94A3B8); }
.iu-tray-chip:hover .iu-tray-x { color: var(--sev-high, #E24B4A); }

.iu-search { display: flex; align-items: center; gap: 8px; padding: 0 11px; border: 1.5px solid var(--border-input, #E2E8F0); border-radius: 8px; background: var(--bg2, #F8FAFC); margin-bottom: 12px; color: var(--t3, #94A3B8); }
.iu-search:focus-within { border-color: var(--p, #7C6FF7); box-shadow: 0 0 0 3px rgba(124,111,247,.14); }
.iu-search-in { flex: 1; border: none; background: transparent; outline: none; padding: 9px 0; font-size: 12.5px; color: var(--t1, #1E2A4A); font-family: inherit; }
.iu-search-clr { background: none; border: none; font-size: 16px; color: var(--t3, #94A3B8); cursor: pointer; }

.iu-roles { display: flex; flex-direction: column; gap: 16px; }
.iu-empty { font-size: 12px; color: var(--t3, var(--t-muted)); font-style: italic; padding: 10px 2px; }
.iu-cat-head { display: flex; align-items: center; justify-content: space-between; margin-bottom: 8px; }
.iu-cat-label { font-size: 10.5px; font-weight: 600; text-transform: uppercase; letter-spacing: .06em; color: var(--t2, #475569); }
.iu-cat-count { font-size: 10.5px; font-weight: 600; color: var(--t3, #94A3B8); font-variant-numeric: tabular-nums; }
.iu-cat-roles { display: grid; grid-template-columns: 1fr 1fr; gap: 6px; }
.iu-role { display: flex; align-items: flex-start; gap: 8px; padding: 8px 10px; background: var(--bg2, #F8FAFC); border: 1px solid var(--border-hard, #E5E7EB); border-radius: 10px; cursor: pointer; font-family: inherit; text-align: left; transition: all .13s; }
.iu-role:hover { border-color: rgba(124,111,247,.4); background: #fff; }
.iu-role.on { background: rgba(124,111,247,.08); border-color: rgba(124,111,247,.45); }
.iu-role-check { flex-shrink: 0; width: 16px; height: 16px; border-radius: 5px; border: 1.5px solid var(--border-input, #CBD5E1); display: flex; align-items: center; justify-content: center; color: #fff; margin-top: 1px; transition: all .13s; }
.iu-role-check.radio { border-radius: 50%; }
.iu-role.on .iu-role-check, .iu-co.on .iu-role-check { background: var(--p, #7C6FF7); border-color: var(--p, #7C6FF7); }
.iu-role-text { display: flex; flex-direction: column; gap: 1px; min-width: 0; }
.iu-role-name { font-size: 12px; font-weight: 500; color: var(--t1, #1E2A4A); }
.iu-role-desc { font-size: 10.5px; color: var(--t3, #94A3B8); line-height: 1.3; overflow: hidden; text-overflow: ellipsis; display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; }

.iu-err { margin-top: 12px; padding: 8px 11px; background: rgba(226,75,74,.08); border: 1px solid rgba(226,75,74,.3); border-radius: 8px; font-size: 11.5px; color: #A82C2B; }

.iu-foot { display: flex; align-items: center; justify-content: space-between; gap: 12px; padding: 14px 22px; border-top: 1px solid var(--border-hard, #E5E7EB); }
.iu-foot-hint { font-size: 10.5px; color: var(--t3, var(--t-muted)); line-height: 1.4; flex: 1; }
.iu-foot-btns { display: flex; gap: 8px; flex-shrink: 0; }
.iu-btn { padding: 9px 18px; border-radius: 8px; font-size: 13px; font-weight: 600; cursor: pointer; font-family: inherit; border: none; transition: all .14s; }
.iu-btn:disabled { opacity: .6; cursor: not-allowed; }
.iu-ghost { background: transparent; border: 1px solid var(--border-input, #E2E8F0); color: var(--t2, #334155); }
.iu-ghost:hover:not(:disabled) { background: var(--bg3, #F1F5F9); }
.iu-primary { background: linear-gradient(135deg, #8B7FFF 0%, #6C5CE7 100%); color: #fff; box-shadow: 0 2px 10px rgba(108,92,231,.32); }
.iu-primary:hover:not(:disabled) { transform: translateY(-1px); box-shadow: 0 4px 16px rgba(108,92,231,.45); }

@media (max-width: 560px) {
  .iu-grid2, .iu-scope, .iu-cat-roles, .iu-companies { grid-template-columns: 1fr; }
}
</style>
