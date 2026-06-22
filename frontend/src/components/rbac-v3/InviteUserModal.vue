<script setup lang="ts">
/**
 * InviteUserModal — приглашение / создание пользователя (RBAC v3).
 * Премиум пошаговый мастер: 1 Профиль · 2 Доступ · 3 Роль → результат.
 * Минимализм: по одному шагу за раз, плавные слайд-переходы.
 *
 * Доступ (Pack 147): «Выбранные компании» — членство в группах компаний (1 роль/компания);
 * «По секторам» / «Вся платформа» — глобальные роли.
 */
import { ref, computed, onMounted } from 'vue';
import {
  rolesApi, groupsApi, rbacV3Api, createUser, generatePassword,
  type RbacV3Role, type RbacV3Group,
} from '@/api/rbacV3';
import { companiesApi, type SectorBrief } from '@/api/companies';
import RoleChip from './RoleChip.vue';
import ModalShell from '@/components/ModalShell.vue';

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
const jobTitle = ref('');
const organizationId = ref('');
const allCompanies = ref<{ id: string; name: string }[]>([]);
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

// ─── Мастер ──────────────────────────────────────────────────────────
const step = ref(1);            // 1 Профиль · 2 Доступ · 3 Роль
const dir = ref(1);             // направление перехода для анимации
const STEPS = [
  { n: 1, label: 'Профиль' },
  { n: 2, label: 'Доступ' },
  { n: 3, label: 'Роль' },
];
const showExtra = ref(false);   // доп. поля профиля (отдел/должность/орг)

// ─── Мульти-добавление ──────────────────────────────────────────────
const bulkMode = ref(false);
const bulkText = ref('');
const bulkResults = ref<Array<{ email: string; ok: boolean; password?: string; error?: string; emailSent?: boolean | null }> | null>(null);
const bulkCopied = ref(false);

const singleResult = ref<{ email: string; password: string; emailSent: boolean | null } | null>(null);
const resCopied = ref(false);
function copyCreds() {
  const r = singleResult.value; if (!r) return;
  navigator.clipboard.writeText(`${r.email}\t${r.password}`).then(() => { resCopied.value = true; setTimeout(() => { resCopied.value = false; }, 2000); });
}

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
    const [roles, groups, secs, comps] = await Promise.all([
      rolesApi.list(),
      groupsApi.list().catch(() => []),
      companiesApi.listSectors().catch(() => []),
      companiesApi.list({ per_page: 500 } as any).catch(() => null),
    ]);
    allRoles.value = roles;
    const items = (comps as any)?.items || (comps as any)?.companies || (Array.isArray(comps) ? comps : []);
    allCompanies.value = (items || []).map((c: any) => ({ id: c.id, name: c.name_ru || c.name || c.code }))
      .filter((c: any) => c.id)
      .sort((a: any, b: any) => a.name.localeCompare(b.name, 'ru'));
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
    selectedRoles.value = selectedRoles.value[0] === code ? [] : [code];
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
  if (mode === 'company' && selectedRoles.value.length > 1) selectedRoles.value = [selectedRoles.value[0]];
}
function setBulk(on: boolean) { bulkMode.value = on; step.value = 1; error.value = null; }

function regenPassword() { password.value = generatePassword(); copied.value = false; }
function copyPassword() {
  navigator.clipboard.writeText(password.value).then(() => { copied.value = true; setTimeout(() => { copied.value = false; }, 2000); });
}

// ─── Валидация по шагам ──────────────────────────────────────────────
const step1Valid = computed(() => bulkMode.value ? parsedBulk.value.length > 0 : (!!email.value.trim() && !!fullName.value.trim()));
const step2Valid = computed(() =>
  scopeMode.value === 'global' ? true
    : scopeMode.value === 'company' ? selectedCompanyGroupIds.value.length > 0
      : selectedSectors.value.length > 0);
const step3Valid = computed(() => scopeMode.value === 'global' ? true : selectedRoles.value.length > 0);
const stepValid = computed(() => step.value === 1 ? step1Valid.value : step.value === 2 ? step2Valid.value : step3Valid.value);

function goNext() {
  error.value = null;
  if (!stepValid.value) {
    error.value = step.value === 1
      ? (bulkMode.value ? 'Добавьте хотя бы один email' : 'Email и ФИО обязательны')
      : step.value === 2
        ? (scopeMode.value === 'company' ? 'Выберите хотя бы одну компанию' : 'Выберите хотя бы один сектор')
        : 'Выберите роль';
    return;
  }
  if (step.value < 3) { dir.value = 1; step.value++; } else submit();
}
function goBack() { error.value = null; if (step.value > 1) { dir.value = -1; step.value--; } }

async function _createOne(em: string, name: string, pw: string): Promise<{ id: string; emailSent: boolean | null }> {
  const u = await createUser({
    email: em, full_name: name, department: department.value.trim() || undefined,
    password: pw, must_change_password: mustChangePassword.value,
    role_codes: scopeMode.value === 'company' ? [] : selectedRoles.value,
    allowed_sectors: scopeMode.value === 'sector' ? selectedSectors.value : undefined,
  });
  if (scopeMode.value === 'company') {
    const roleCode = selectedRoles.value[0];
    for (const gid of selectedCompanyGroupIds.value) await rbacV3Api.upsertMembership(u.id, gid, roleCode);
  }
  return { id: u.id, emailSent: (u as any).invite_email_sent ?? null };
}

async function submit() {
  if (bulkMode.value) {
    const users = parsedBulk.value;
    if (!users.length) { error.value = 'Добавьте хотя бы один email'; return; }
    saving.value = true; error.value = null;
    const out: NonNullable<typeof bulkResults.value> = [];
    for (const row of users) {
      const pw = generatePassword();
      try {
        const r = await _createOne(row.email, row.full_name, pw);
        out.push({ email: row.email, ok: true, password: pw, emailSent: r.emailSent });
      } catch (e: any) {
        out.push({ email: row.email, ok: false, error: e?.response?.data?.detail || 'ошибка' });
      }
    }
    saving.value = false; bulkResults.value = out; emit('created', '');
    return;
  }
  saving.value = true; error.value = null;
  try {
    const u = await createUser({
      email: email.value.trim(), full_name: fullName.value.trim(),
      department: department.value.trim() || undefined, job_title: jobTitle.value.trim() || undefined,
      organization_id: organizationId.value || undefined,
      password: password.value, must_change_password: mustChangePassword.value,
      role_codes: scopeMode.value === 'company' ? [] : selectedRoles.value,
      allowed_sectors: scopeMode.value === 'sector' ? selectedSectors.value : undefined,
    });
    if (scopeMode.value === 'company') {
      const roleCode = selectedRoles.value[0];
      for (const gid of selectedCompanyGroupIds.value) await rbacV3Api.upsertMembership(u.id, gid, roleCode);
    }
    singleResult.value = { email: email.value.trim(), password: password.value, emailSent: (u as any).invite_email_sent ?? null };
    emit('created', u.id);
  } catch (e: any) {
    error.value = e?.response?.data?.detail || 'Не удалось создать пользователя';
  } finally { saving.value = false; }
}

function copyBulkResults() {
  const text = (bulkResults.value || []).filter(r => r.ok).map(r => `${r.email}\t${r.password}`).join('\n');
  navigator.clipboard.writeText(text).then(() => { bulkCopied.value = true; setTimeout(() => { bulkCopied.value = false; }, 2000); });
}

const hasResult = computed(() => !!singleResult.value || !!bulkResults.value);
</script>

<template>
  <ModalShell :open="true" size="md" @close="emit('close')">
    <template #header>
      <div class="iu-head">
        <h2 class="iu-title">{{ prefill ? 'Создать аналогичного' : 'Пригласить пользователя' }}</h2>
        <div v-if="!prefill && !hasResult" class="iu-seg">
          <button type="button" :class="{ on: !bulkMode }" @click="setBulk(false)">Один</button>
          <button type="button" :class="{ on: bulkMode }" @click="setBulk(true)">Несколько</button>
        </div>
      </div>
    </template>

    <!-- ═══ Результат: один ═══ -->
    <div v-if="singleResult" class="iu-res">
      <div class="iu-res-ico"><svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"/></svg></div>
      <div class="iu-res-ttl">Пользователь создан</div>
      <div v-if="singleResult.emailSent" class="iu-note ok">Письмо с паролем отправлено на <b>{{ singleResult.email }}</b>.</div>
      <div v-else class="iu-note warn"><b>Письмо не отправлено</b> — почта (SMTP) выключена или ошибка. Передайте доступ вручную:</div>
      <div class="iu-creds">
        <div class="iu-cred"><span>Логин</span><code>{{ singleResult.email }}</code></div>
        <div class="iu-cred"><span>Временный пароль</span><code>{{ singleResult.password }}</code></div>
        <button class="iu-link" type="button" @click="copyCreds">{{ resCopied ? 'Скопировано' : 'Копировать логин + пароль' }}</button>
      </div>
    </div>

    <!-- ═══ Результат: несколько ═══ -->
    <div v-else-if="bulkResults" class="iu-res">
      <div class="iu-res-row"><span>Создано <b>{{ bulkResults.filter(r => r.ok).length }}</b> из {{ bulkResults.length }}</span>
        <button class="iu-link" type="button" @click="copyBulkResults">{{ bulkCopied ? 'Скопировано' : 'Копировать email + пароли' }}</button></div>
      <div class="iu-blist">
        <div v-for="r in bulkResults" :key="r.email" class="iu-brow" :class="{ fail: !r.ok }">
          <span class="iu-bdot">{{ r.ok ? '✓' : '✗' }}</span>
          <span class="iu-bemail">{{ r.email }}</span>
          <code v-if="r.ok" class="iu-bpwd">{{ r.password }}</code>
          <span v-if="r.ok && r.emailSent === false" class="iu-bnomail" title="SMTP выключен — передайте вручную">письмо не ушло</span>
          <span v-else-if="!r.ok" class="iu-berr">{{ r.error }}</span>
        </div>
      </div>
      <div class="iu-note" :class="bulkResults.some(r => r.ok && r.emailSent === false) ? 'warn' : 'ok'">
        <template v-if="bulkResults.some(r => r.ok && r.emailSent === false)"><b>Часть писем не отправлена</b> (SMTP) — передайте пароли лично.</template>
        <template v-else>Письма-приглашения отправлены. Пароли можно также передать лично.</template>
      </div>
    </div>

    <!-- ═══ Мастер ═══ -->
    <div v-else class="iu-wiz">
      <!-- Прогресс -->
      <div class="iu-steps">
        <div v-for="s in STEPS" :key="s.n" class="iu-stp" :class="{ on: step === s.n, done: step > s.n }">
          <span class="iu-stp-dot"><svg v-if="step > s.n" width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3.5" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"/></svg><template v-else>{{ s.n }}</template></span>
          <span class="iu-stp-l">{{ s.label }}</span>
        </div>
      </div>

      <Transition :name="dir > 0 ? 'iu-fwd' : 'iu-bwd'" mode="out-in">
        <!-- ── Шаг 1: Профиль ── -->
        <div v-if="step === 1" :key="'s1'" class="iu-step">
          <template v-if="!bulkMode">
            <div class="iu-f"><label>Email</label><input v-model="email" class="iu-in" placeholder="user@uz-assets.uz" autofocus /></div>
            <div class="iu-f"><label>ФИО</label><input v-model="fullName" class="iu-in" placeholder="Иванов Иван Иванович" /></div>

            <button type="button" class="iu-more" @click="showExtra = !showExtra">
              <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" :style="{ transform: showExtra ? 'rotate(90deg)' : '' }"><polyline points="9 18 15 12 9 6"/></svg>
              Дополнительно (отдел, должность, организация)
            </button>
            <div v-if="showExtra" class="iu-extra">
              <div class="iu-f"><label>Отдел</label><input v-model="department" class="iu-in" placeholder="Финансовый блок" /></div>
              <div class="iu-f"><label>Должность</label><input v-model="jobTitle" class="iu-in" placeholder="Финансовый аналитик" /></div>
              <div class="iu-f"><label>Организация (бейдж)</label>
                <select v-model="organizationId" class="iu-in"><option value="">— Не указана</option><option v-for="c in allCompanies" :key="c.id" :value="c.id">{{ c.name }}</option></select>
              </div>
            </div>

            <div class="iu-f">
              <label class="iu-lbl-row">Временный пароль
                <span class="iu-pwd-acts"><button class="iu-link" type="button" @click="regenPassword">Новый</button><button class="iu-link" type="button" @click="copyPassword">{{ copied ? 'Скопировано' : 'Копировать' }}</button></span>
              </label>
              <div class="iu-pwd"><code>{{ password }}</code></div>
            </div>
            <label class="iu-cb"><input type="checkbox" v-model="mustChangePassword" /><span>Требовать смену пароля при первом входе</span></label>
          </template>

          <template v-else>
            <div class="iu-f"><label class="iu-lbl-row">Email — по одному на строку <span v-if="parsedBulk.length" class="iu-pill">{{ parsedBulk.length }}</span></label>
              <textarea v-model="bulkText" class="iu-in iu-ta" rows="6" placeholder="ivanov@uz-assets.uz, Иванов Иван&#10;petrov@uz-assets.uz, Петров Пётр"></textarea>
            </div>
            <p class="iu-hint">Формат: <code>email, ФИО</code> (ФИО опционально). Пароль генерируется автоматически каждому.</p>
            <div class="iu-f"><label>Отдел для всех (опц.)</label><input v-model="department" class="iu-in" placeholder="Финансовый блок" /></div>
            <label class="iu-cb"><input type="checkbox" v-model="mustChangePassword" /><span>Требовать смену пароля при первом входе</span></label>
          </template>
        </div>

        <!-- ── Шаг 2: Доступ ── -->
        <div v-else-if="step === 2" :key="'s2'" class="iu-step">
          <div class="iu-scope">
            <button type="button" :class="['iu-sc', { on: scopeMode === 'company' }]" @click="setScope('company')">
              <span class="iu-sc-rd"></span><span class="iu-sc-t"><b>Выбранные компании</b><i>Видит данные только своих компаний</i></span>
            </button>
            <button type="button" :class="['iu-sc', { on: scopeMode === 'sector' }]" @click="setScope('sector')">
              <span class="iu-sc-rd"></span><span class="iu-sc-t"><b>По секторам</b><i>Все компании выбранных секторов</i></span>
            </button>
            <button type="button" :class="['iu-sc', { on: scopeMode === 'global' }]" @click="setScope('global')">
              <span class="iu-sc-rd"></span><span class="iu-sc-t"><b>Вся платформа</b><i>Доступ ко всем компаниям</i></span>
            </button>
          </div>

          <template v-if="scopeMode === 'company'">
            <div class="iu-pickhead">Компании <span v-if="selectedCompanyGroupIds.length" class="iu-pill">{{ selectedCompanyGroupIds.length }}</span></div>
            <div class="iu-search"><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><circle cx="11" cy="11" r="7"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg><input v-model="companySearch" placeholder="Поиск компании…" /><button v-if="companySearch" @click="companySearch = ''" type="button">×</button></div>
            <div class="iu-list">
              <div v-if="!companyGroups.length" class="iu-empty">Нет компаний с группами доступа</div>
              <button v-for="g in filteredCompanyGroups" :key="g.id" type="button" :class="['iu-item', { on: selectedCompanyGroupIds.includes(g.id) }]" @click="toggleCompany(g.id)">
                <span class="iu-ck"><svg v-if="selectedCompanyGroupIds.includes(g.id)" width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"/></svg></span>{{ g.name }}
              </button>
            </div>
          </template>

          <template v-else-if="scopeMode === 'sector'">
            <div class="iu-pickhead">Секторы <span v-if="selectedSectors.length" class="iu-pill">{{ selectedSectors.length }}</span></div>
            <div class="iu-list">
              <div v-if="!sectors.length" class="iu-empty">Секторы не загружены</div>
              <button v-for="s in sectors" :key="s.code" type="button" :class="['iu-item', { on: selectedSectors.includes(s.code) }]" @click="toggleSector(s.code)">
                <span class="iu-ck"><svg v-if="selectedSectors.includes(s.code)" width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"/></svg></span>{{ s.name_ru }}
              </button>
            </div>
          </template>

          <p v-else class="iu-hint" style="margin-top:14px">Пользователь получит доступ ко всем компаниям. Подходит для админов и общеорганизационных ролей. Роль назначите на следующем шаге.</p>
        </div>

        <!-- ── Шаг 3: Роль ── -->
        <div v-else :key="'s3'" class="iu-step">
          <div class="iu-pickhead">
            {{ scopeMode === 'company' ? 'Роль в компаниях' : (scopeMode === 'sector' ? 'Роли в секторах' : 'Роли на платформу') }}
            <span class="iu-pickhead-r"><span v-if="selectedRoles.length" class="iu-pill">{{ selectedRoles.length }}</span><button v-if="selectedRoles.length && isMulti" class="iu-link" type="button" @click="clearRoles">очистить</button></span>
          </div>
          <p v-if="scopeMode === 'company'" class="iu-hint" style="margin:-4px 0 8px">Одна роль на компанию — что пользователь делает внутри своей компании.</p>

          <div v-if="selectedRoleObjs.length && isMulti" class="iu-tray">
            <button v-for="r in selectedRoleObjs" :key="r.code" class="iu-tchip" @click="pickRole(r.code)" type="button" :title="`Убрать «${r.name_ru}»`"><RoleChip :code="r.code" size="sm" /><span>{{ r.name_ru }}</span><span class="iu-tx">×</span></button>
          </div>

          <div class="iu-search"><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><circle cx="11" cy="11" r="7"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg><input v-model="roleSearch" placeholder="Поиск роли…" /><button v-if="roleSearch" @click="roleSearch = ''" type="button">×</button></div>

          <div class="iu-roles">
            <div v-if="!allRoles.length" class="iu-empty">Загрузка ролей…</div>
            <div v-else-if="!groupedRoles.length" class="iu-empty">Ничего не найдено</div>
            <section v-for="cat in groupedRoles" :key="cat.id" class="iu-cat">
              <div class="iu-cat-h"><span>{{ cat.label }}</span><span class="iu-cat-n">{{ catSelectedCount(cat) }}/{{ cat.roles.length }}</span></div>
              <div class="iu-cat-r">
                <button v-for="r in cat.roles" :key="r.code" type="button" :class="['iu-item iu-role', { on: isRoleSelected(r.code), radio: !isMulti }]" @click="pickRole(r.code)" :title="r.description_ru || r.name_ru">
                  <span class="iu-ck" :class="{ radio: !isMulti }"><svg v-if="isRoleSelected(r.code)" width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"/></svg></span>
                  <RoleChip :code="r.code" size="sm" />
                  <span class="iu-role-t"><span class="iu-role-n">{{ r.name_ru }}</span><span v-if="r.description_ru" class="iu-role-d">{{ r.description_ru }}</span></span>
                </button>
              </div>
            </section>
          </div>
        </div>
      </Transition>

      <div v-if="error" class="iu-err">{{ error }}</div>
    </div>

    <template #footer>
      <div class="iu-foot">
        <template v-if="hasResult">
          <button class="iu-btn iu-primary" @click="emit('close')">Готово</button>
        </template>
        <template v-else>
          <button v-if="step > 1" class="iu-btn iu-ghost" @click="goBack" :disabled="saving">← Назад</button>
          <button v-else class="iu-btn iu-ghost" @click="emit('close')" :disabled="saving">Отмена</button>
          <button class="iu-btn iu-primary" :disabled="saving || !stepValid" @click="goNext">
            <template v-if="step < 3">Далее →</template>
            <template v-else>{{ saving ? 'Создание…' : (bulkMode ? `Пригласить ${parsedBulk.length || ''}` : 'Пригласить') }}</template>
          </button>
        </template>
      </div>
    </template>
  </ModalShell>
</template>

<style scoped>
.iu-head { display: flex; align-items: center; justify-content: space-between; gap: 12px; width: 100%; }
.iu-title { font-size: 15px; font-weight: 600; letter-spacing: -.01em; color: var(--t1, #1E2A4A); margin: 0; }
.iu-seg { display: inline-flex; background: var(--bg2, #F1F5F9); border-radius: 9px; padding: 2px; }
.iu-seg button { border: none; background: transparent; padding: 5px 13px; border-radius: 7px; font-size: 11.5px; font-weight: 600; color: var(--t3, #64748B); cursor: pointer; font-family: inherit; transition: all .14s var(--ease-standard); }
.iu-seg button.on { background: #fff; color: var(--p-deep, #534AB7); box-shadow: 0 1px 3px rgba(15,23,60,.1); }

/* Прогресс */
.iu-steps { display: flex; align-items: center; gap: 6px; margin-bottom: 18px; }
.iu-stp { display: flex; align-items: center; gap: 7px; flex: 1; }
.iu-stp:not(:last-child)::after { content: ''; flex: 1; height: 2px; border-radius: 2px; background: var(--border, rgba(99,102,180,.14)); transition: background .3s; }
.iu-stp.done:not(:last-child)::after { background: var(--p, #7c6ff7); }
.iu-stp-dot { width: 24px; height: 24px; border-radius: 50%; flex-shrink: 0; display: inline-flex; align-items: center; justify-content: center; font-size: 11px; font-weight: 700; background: var(--bg2, #F1F5F9); color: var(--t3, #94a3b8); border: 1.5px solid transparent; transition: all .25s var(--ease-standard); }
.iu-stp.on .iu-stp-dot { background: var(--p, #7c6ff7); color: #fff; box-shadow: 0 0 0 4px rgba(124,111,247,.16); transform: scale(1.05); }
.iu-stp.done .iu-stp-dot { background: rgba(124,111,247,.14); color: var(--p-deep, #534AB7); }
.iu-stp-l { font-size: 11.5px; font-weight: 500; color: var(--t3, #94a3b8); white-space: nowrap; }
.iu-stp.on .iu-stp-l { color: var(--t1, #1E2A4A); font-weight: 600; }

/* Шаг */
.iu-step { display: flex; flex-direction: column; gap: 12px; min-height: 240px; }
.iu-f { display: flex; flex-direction: column; gap: 6px; }
.iu-f label, .iu-lbl-row { font-size: 10px; font-weight: 600; color: var(--t3, #94A3B8); letter-spacing: .06em; text-transform: uppercase; }
.iu-lbl-row { display: flex; align-items: center; justify-content: space-between; }
.iu-pwd-acts { display: flex; gap: 10px; }
.iu-in, .iu-search input, .iu-ta { width: 100%; box-sizing: border-box; padding: 10px 12px; border: 1.5px solid var(--border-input, #E2E8F0); border-radius: 10px; font-size: 13px; color: var(--t1, #1E2A4A); outline: none; font-family: inherit; background: var(--bg2, #F8FAFC); transition: border-color .14s, box-shadow .14s, background .14s; }
.iu-in:focus, .iu-ta:focus { border-color: var(--p, #7C6FF7); box-shadow: 0 0 0 3px rgba(124,111,247,.13); background: #fff; }
.iu-ta { resize: vertical; line-height: 1.6; font-size: 12.5px; }
.iu-pwd { padding: 11px 12px; background: var(--bg2, #F8FAFC); border: 1.5px solid var(--border-input, #E2E8F0); border-radius: 10px; }
.iu-pwd code { font-family: ui-monospace, 'SF Mono', Menlo, monospace; font-size: 14px; color: var(--t1, #1E2A4A); letter-spacing: .04em; user-select: all; }
.iu-link { background: transparent; border: none; color: var(--p-deep, #534AB7); font-size: 11px; font-weight: 600; cursor: pointer; font-family: inherit; padding: 0; }
.iu-link:hover { text-decoration: underline; }
.iu-cb { display: flex; align-items: center; gap: 8px; font-size: 12.5px; color: var(--t2, #334155); cursor: pointer; margin-top: 2px; }
.iu-cb input { accent-color: var(--p, #7C6FF7); width: 16px; height: 16px; }
.iu-more { display: inline-flex; align-items: center; gap: 6px; background: none; border: none; color: var(--p-deep, #534AB7); font-size: 12px; font-weight: 500; cursor: pointer; font-family: inherit; padding: 2px 0; align-self: flex-start; }
.iu-more svg { transition: transform .2s var(--ease-standard); }
.iu-extra { display: flex; flex-direction: column; gap: 12px; padding: 12px; background: var(--bg2, #F8FAFC); border-radius: 11px; animation: iuReveal .28s var(--ease-out); }
@keyframes iuReveal { from { opacity: 0; transform: translateY(-6px); } to { opacity: 1; transform: none; } }
.iu-hint { font-size: 11.5px; color: var(--t3, #94A3B8); line-height: 1.5; margin: 0; }
.iu-hint code { font-family: ui-monospace, monospace; font-size: 11px; }
.iu-pill { font-size: 10.5px; font-weight: 700; color: var(--p-deep, #534AB7); background: rgba(124,111,247,.13); padding: 1px 8px; border-radius: 8px; }

/* Доступ — карточки */
.iu-scope { display: flex; flex-direction: column; gap: 8px; }
.iu-sc { display: flex; align-items: flex-start; gap: 11px; padding: 13px 15px; background: var(--bg2, #F8FAFC); border: 1.5px solid var(--border-input, #E2E8F0); border-radius: 12px; cursor: pointer; font-family: inherit; text-align: left; transition: all .15s var(--ease-standard); }
.iu-sc:hover { border-color: rgba(124,111,247,.4); transform: translateY(-1px); }
.iu-sc.on { background: rgba(124,111,247,.06); border-color: var(--p, #7C6FF7); box-shadow: 0 2px 10px rgba(124,111,247,.12); }
.iu-sc-rd { flex-shrink: 0; width: 18px; height: 18px; border-radius: 50%; border: 2px solid var(--border-input, #CBD5E1); margin-top: 1px; position: relative; transition: all .15s; }
.iu-sc.on .iu-sc-rd { border-color: var(--p, #7C6FF7); }
.iu-sc.on .iu-sc-rd::after { content: ''; position: absolute; inset: 3px; border-radius: 50%; background: var(--p, #7C6FF7); animation: iuPop .2s var(--ease-bounce); }
@keyframes iuPop { from { transform: scale(0); } to { transform: scale(1); } }
.iu-sc-t { display: flex; flex-direction: column; gap: 2px; }
.iu-sc-t b { font-size: 13px; font-weight: 600; color: var(--t1, #1E2A4A); }
.iu-sc-t i { font-size: 11px; color: var(--t3, #94A3B8); font-style: normal; line-height: 1.35; }

.iu-pickhead { display: flex; align-items: center; justify-content: space-between; font-size: 10px; font-weight: 600; text-transform: uppercase; letter-spacing: .06em; color: var(--t3, #94A3B8); margin: 16px 0 8px; }
.iu-pickhead-r { display: flex; align-items: center; gap: 10px; }
.iu-search { display: flex; align-items: center; gap: 8px; padding: 0 12px; border: 1.5px solid var(--border-input, #E2E8F0); border-radius: 10px; background: var(--bg2, #F8FAFC); margin-bottom: 10px; color: var(--t3, #94A3B8); transition: border-color .14s, box-shadow .14s; }
.iu-search:focus-within { border-color: var(--p, #7C6FF7); box-shadow: 0 0 0 3px rgba(124,111,247,.13); }
.iu-search input { border: none; background: transparent; padding: 9px 0; margin: 0; box-shadow: none; }
.iu-search button { background: none; border: none; font-size: 17px; color: var(--t3, #94A3B8); cursor: pointer; }

.iu-list { display: grid; grid-template-columns: 1fr 1fr; gap: 6px; max-height: 200px; overflow-y: auto; padding: 1px; }
.iu-empty { font-size: 12px; color: var(--t3, #94A3B8); font-style: italic; padding: 12px 2px; grid-column: 1 / -1; }
.iu-item { display: flex; align-items: center; gap: 9px; padding: 9px 11px; background: var(--bg2, #F8FAFC); border: 1px solid var(--border-hard, #E5E7EB); border-radius: 10px; cursor: pointer; font-family: inherit; text-align: left; font-size: 12px; font-weight: 500; color: var(--t1, #1E2A4A); transition: all .13s; }
.iu-item:hover { border-color: rgba(124,111,247,.4); background: #fff; }
.iu-item.on { background: rgba(124,111,247,.07); border-color: rgba(124,111,247,.45); }
.iu-ck { flex-shrink: 0; width: 17px; height: 17px; border-radius: 5px; border: 1.5px solid var(--border-input, #CBD5E1); display: flex; align-items: center; justify-content: center; color: #fff; transition: all .13s; }
.iu-ck.radio { border-radius: 50%; }
.iu-item.on .iu-ck { background: var(--p, #7C6FF7); border-color: var(--p, #7C6FF7); }

/* Роли */
.iu-tray { display: flex; flex-wrap: wrap; gap: 6px; padding: 10px; background: rgba(124,111,247,.05); border: 1px solid rgba(124,111,247,.18); border-radius: 11px; margin-bottom: 10px; }
.iu-tchip { display: inline-flex; align-items: center; gap: 6px; padding: 3px 8px 3px 5px; background: #fff; border: 1px solid var(--border-hard, #E5E7EB); border-radius: 9px; cursor: pointer; font-family: inherit; font-size: 11.5px; color: var(--t1, #1E2A4A); transition: border-color .13s; }
.iu-tchip:hover { border-color: var(--sev-high, #E24B4A); }
.iu-tx { font-size: 15px; line-height: 1; color: var(--t3, #94A3B8); }
.iu-tchip:hover .iu-tx { color: var(--sev-high, #E24B4A); }
.iu-roles { display: flex; flex-direction: column; gap: 16px; max-height: 280px; overflow-y: auto; padding: 1px; }
.iu-cat-h { display: flex; align-items: center; justify-content: space-between; margin-bottom: 8px; }
.iu-cat-h span:first-child { font-size: 10.5px; font-weight: 600; text-transform: uppercase; letter-spacing: .06em; color: var(--t2, #475569); }
.iu-cat-n { font-size: 10.5px; font-weight: 600; color: var(--t3, #94A3B8); font-variant-numeric: tabular-nums; }
.iu-cat-r { display: grid; grid-template-columns: 1fr 1fr; gap: 6px; }
.iu-role { align-items: flex-start; }
.iu-role .iu-ck { margin-top: 1px; }
.iu-role-t { display: flex; flex-direction: column; gap: 1px; min-width: 0; }
.iu-role-n { font-size: 12px; font-weight: 500; }
.iu-role-d { font-size: 10.5px; color: var(--t3, #94A3B8); line-height: 1.3; font-weight: 400; overflow: hidden; text-overflow: ellipsis; display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; }

.iu-err { margin-top: 12px; padding: 9px 12px; background: rgba(226,75,74,.08); border: 1px solid rgba(226,75,74,.28); border-radius: 9px; font-size: 11.5px; color: #A82C2B; animation: iuReveal .2s var(--ease-out); }

/* Результат */
.iu-res { display: flex; flex-direction: column; gap: 10px; align-items: stretch; animation: iuReveal .3s var(--ease-out); }
.iu-res-ico { width: 44px; height: 44px; border-radius: 50%; background: var(--green, #1D9E75); color: #fff; display: inline-flex; align-items: center; justify-content: center; align-self: center; box-shadow: 0 0 0 6px rgba(29,158,117,.12); animation: iuPop .35s var(--ease-bounce); }
.iu-res-ttl { font-size: 15px; font-weight: 600; color: var(--t1, #1E2A4A); text-align: center; }
.iu-res-row { display: flex; align-items: center; justify-content: space-between; font-size: 13px; color: var(--t1, #1E2A4A); margin-bottom: 4px; }
.iu-note { padding: 10px 13px; border-radius: 10px; font-size: 12px; line-height: 1.5; }
.iu-note.ok { background: rgba(29,158,117,.08); border: 1px solid rgba(29,158,117,.22); color: #0F6E56; }
.iu-note.warn { background: rgba(217,119,6,.08); border: 1px solid rgba(217,119,6,.28); color: #9A5B00; }
.iu-creds { border: 1px solid var(--border-hard, #E5E7EB); border-radius: 11px; padding: 13px 15px; display: flex; flex-direction: column; gap: 9px; }
.iu-cred { display: flex; align-items: center; gap: 12px; }
.iu-cred span { width: 130px; flex-shrink: 0; color: var(--t3, #94A3B8); font-size: 10px; text-transform: uppercase; letter-spacing: .05em; font-weight: 600; }
.iu-cred code { font-family: ui-monospace, monospace; font-size: 13px; color: var(--t1, #1E2A4A); user-select: all; background: var(--bg2, #F8FAFC); padding: 3px 9px; border-radius: 7px; }
.iu-blist { display: flex; flex-direction: column; gap: 6px; max-height: 300px; overflow-y: auto; }
.iu-brow { display: flex; align-items: center; gap: 10px; padding: 8px 11px; border: 1px solid var(--border-hard, #E5E7EB); border-radius: 9px; font-size: 12.5px; }
.iu-brow.fail { background: rgba(226,75,74,.05); border-color: rgba(226,75,74,.25); }
.iu-bdot { width: 16px; flex-shrink: 0; font-weight: 700; color: var(--green, #1D9E75); }
.iu-brow.fail .iu-bdot { color: var(--sev-high, #E24B4A); }
.iu-bemail { flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.iu-bpwd { font-family: ui-monospace, monospace; font-size: 12px; color: var(--t2, #475569); background: var(--bg2, #F8FAFC); padding: 2px 7px; border-radius: 6px; user-select: all; }
.iu-bnomail { font-size: 9.5px; font-weight: 600; color: #9A5B00; background: rgba(217,119,6,.12); padding: 1px 6px; border-radius: 5px; white-space: nowrap; flex-shrink: 0; }
.iu-berr { font-size: 11px; color: #A82C2B; }

/* Футер + кнопки */
.iu-foot { display: flex; justify-content: flex-end; gap: 8px; width: 100%; }
.iu-btn { padding: 9px 18px; border-radius: 10px; font-size: 13px; font-weight: 600; cursor: pointer; font-family: inherit; border: none; transition: all .14s var(--ease-standard); }
.iu-btn:disabled { opacity: .5; cursor: not-allowed; }
.iu-ghost { background: transparent; border: 1px solid var(--border-input, #E2E8F0); color: var(--t2, #334155); }
.iu-ghost:hover:not(:disabled) { background: var(--bg3, #F1F5F9); }
.iu-primary { background: linear-gradient(135deg, #8B7FFF 0%, #6C5CE7 100%); color: #fff; box-shadow: 0 2px 10px rgba(108,92,231,.3); }
.iu-primary:hover:not(:disabled) { transform: translateY(-1px); box-shadow: 0 5px 16px rgba(108,92,231,.42); }
.iu-primary:active:not(:disabled) { transform: translateY(0); }

/* Слайд-переходы шагов */
.iu-fwd-enter-active, .iu-fwd-leave-active, .iu-bwd-enter-active, .iu-bwd-leave-active { transition: opacity .24s var(--ease-out), transform .24s var(--ease-out); }
.iu-fwd-enter-from { opacity: 0; transform: translateX(24px); }
.iu-fwd-leave-to { opacity: 0; transform: translateX(-24px); }
.iu-bwd-enter-from { opacity: 0; transform: translateX(-24px); }
.iu-bwd-leave-to { opacity: 0; transform: translateX(24px); }

@media (max-width: 560px) {
  .iu-list, .iu-cat-r { grid-template-columns: 1fr; }
  .iu-stp-l { display: none; }
}
</style>
